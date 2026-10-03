"""Authentication routes: login, refresh, register (admin), me, logout, pepper rotation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.database import get_session
from app.core.repositories import AuditRepository, UserRepository
from app.services.auth_service import AuthService, get_auth_service
from app.shared.config import settings
from app.shared.rate_limit import get_auth_limit, get_pin_limit, limiter
from app.shared.schemas import (
    ChangePasswordRequest,
    CurrentUser,
    LoginRequest,
    PinLoginRequest,
    RefreshRequest,
    Token,
    UserCreate,
    UserPublic,
    VerifyPasswordRequest,
)
from app.shared.security import rotate_pin_pepper

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ── Audit M3: refresh-token cookie (HttpOnly, SameSite=Strict) ───────────────
# The desktop frontend keeps its access token in memory only; the refresh
# token is delivered as an HttpOnly cookie so webview JavaScript can never
# read it. The cookie is scoped to the auth path, so it is not attached to
# unrelated API calls.
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
        # The sidecar is plain HTTP on loopback/LAN (audit M5 tracks TLS);
        # Secure would stop the cookie from ever being sent. HttpOnly +
        # SameSite=Strict + a short path is the control this finding asks for.
        secure=False,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


@router.post("/login", response_model=Token)
@limiter.limit(get_auth_limit())
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> Token:
    token = await service.login(payload.username, payload.password)
    _set_refresh_cookie(response, token.refresh_token)
    return token


@router.post("/login/pin", response_model=Token)
@limiter.limit(get_pin_limit())
async def login_pin(request: Request, payload: PinLoginRequest, service: AuthService = Depends(get_auth_service)) -> Token:
    """Kiosk PIN login (C.4): device-bound, peppered, tamper-evident lockout."""
    return await service.pin_login(payload.username, payload.pin)


@router.post("/pin", status_code=204)
async def set_pin(
    payload: PinLoginRequest,
    _user: CurrentUser = Depends(require_permission("users.write")),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Set/reset a user's PIN (C.4). Admin-gated; requires the pepper on this device."""
    await service.set_pin(payload.username, payload.pin)


@router.post("/refresh", response_model=Token)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    service: AuthService = Depends(get_auth_service),
) -> Token:
    """Refresh the session (audit M3).

    Prefers the HttpOnly ``refresh_token`` cookie (browser path: silent
    refresh after a restart, with no token ever readable by JavaScript). The
    request body remains supported for API clients (mobile, tests). The
    rotated token is written back to the cookie.
    """
    presented = (payload.refresh_token if payload else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    if not presented:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    token = await service.refresh(presented)
    _set_refresh_cookie(response, token.refresh_token)
    return token


@router.post("/register", status_code=201, response_model=UserPublic)
async def register(
    payload: UserCreate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    return await service.register(payload)


@router.get("/me", response_model=CurrentUser)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> CurrentUser:
    """Get current user with fresh role_id and permissions from database."""
    from sqlalchemy import select
    from app.core.models import Role, User
    from app.core.repositories import UserRepository

    user = await db.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # User has no `role` relationship — query the role name explicitly so
    # /me never 500s on `user.role.name` (missing-tabs regression).
    role_name = await db.scalar(select(Role.name).where(Role.id == user.role_id)) or "Unknown"

    permissions = await UserRepository(db).permissions_for_role(user.role_id)

    return CurrentUser(
        id=user.id,
        username=user.username,
        role=role_name,
        role_id=user.role_id,
        permissions=permissions,
        display_name=user.display_name,
        is_active=user.is_active,
    )


@router.post("/logout", status_code=200)
async def logout(
    request: Request,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    # Sprint 1C: the access token is discarded client-side, but the event is
    # audit-logged (user_id + timestamp, IP when the request carries one).
    # Audit M3: the HttpOnly refresh cookie is cleared server-side so a
    # logout cannot be undone by replaying a still-valid refresh token.
    await AuditRepository(session).log(
        action="auth.logout",
        subject_type="user",
        subject_id=user.id,
        details=f"username={user.username} ip={request.client.host if request.client else 'unknown'}",
    )
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return {"status": "ok", "message": f"Logged out {user.username}"}


@router.post("/verify-password", status_code=200)
async def verify_password(
    payload: VerifyPasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Verify the current user's password without issuing new tokens.

    Used for sensitive action confirmation (change password, edit role, delete user).
    Does NOT log out the user or modify session state."""
    await service.verify_password(user.username, payload.password)
    return {"status": "ok", "message": "Password verified"}


@router.post("/change-password", status_code=200)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Change the authenticated user's password (or, for admins, another user's password).

    Requires the *caller's* current password to be verified first (re-auth gate).
    Does NOT invalidate the current session or issue new tokens — the caller stays logged in.

    Body:
        current_password: The currently authenticated user's password (re-auth proof).
        new_password:     The new password to set (min 8 chars).
        target_user_id:   Optional. If provided, admin changes *another* user's password.
                          Requires users.write permission. Defaults to the current user.
    """
    # Verify the caller's own password as re-auth proof
    await service.verify_password(user.username, payload.current_password)

    # Determine which user's password to change
    if payload.target_user_id is not None and payload.target_user_id != user.id:
        # Admin changing another user's password — require users.write permission
        if not ("users.write" in user.permissions or "*" in user.permissions):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail="Changing another user's password requires the users.write permission",
            )
        # Protect User ID 1 from password changes by non-admin callers
        if payload.target_user_id == 1 and user.id != 1:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail="Only the administrator account itself can change its own password",
            )
        target_username = await _get_username(session, payload.target_user_id)
    else:
        target_username = user.username

    if len(payload.new_password) < 8:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters")

    await service.change_password(target_username, payload.new_password)
    return {"status": "ok", "message": "Password changed successfully"}


async def _get_username(session: AsyncSession, user_id: int) -> str:
    from sqlalchemy import select as _select
    from app.core.models import User as _User
    from fastapi import HTTPException
    row = await session.scalar(_select(_User.username).where(_User.id == user_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Target user not found")
    return row


@router.post("/rotate-pepper", status_code=200)
async def rotate_pepper(
    user: CurrentUser = Depends(require_permission("pos.pepper.rotate")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Rotate the device-bound PIN pepper (B2).

    Persists the previous pepper, writes a fresh one, bumps the version, and flags
    all users for a transparent lazy re-hash on their next successful PIN login.
    Requires the ``pos.pepper.rotate`` permission."""
    new_pepper = rotate_pin_pepper()
    await UserRepository(session).mark_all_pins_for_rehash()
    await AuditRepository(session).log(
        action="pin_pepper.rotate",
        details=f"pin_pepper_version={settings.pin_pepper_version}",
    )
    return {"rotated": True, "pin_pepper_version": settings.pin_pepper_version, "pepper_bytes": len(new_pepper)}

