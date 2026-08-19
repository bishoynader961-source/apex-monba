"""Authentication routes: login, refresh, register (admin), me, logout, pepper rotation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.database import get_session
from app.core.repositories import AuditRepository, UserRepository
from app.services.auth_service import AuthService, get_auth_service
from app.shared.config import settings
from app.shared.rate_limit import get_auth_limit, get_pin_limit, limiter
from app.shared.schemas import (
    CurrentUser,
    LoginRequest,
    PinLoginRequest,
    RefreshRequest,
    Token,
    UserCreate,
    UserPublic,
)
from app.shared.security import rotate_pin_pepper

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=Token)
@limiter.limit(get_auth_limit())
async def login(request: Request, payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> Token:
    return await service.login(payload.username, payload.password)


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
async def refresh(payload: RefreshRequest, service: AuthService = Depends(get_auth_service)) -> Token:
    return await service.refresh(payload.refresh_token)


@router.post("/register", status_code=201, response_model=UserPublic)
async def register(
    payload: UserCreate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    return await service.register(payload)


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user


@router.post("/logout", status_code=200)
async def logout(user: CurrentUser = Depends(get_current_user)) -> dict[str, str]:
    # Stateless JWT: logout is client-side (discard tokens). Endpoint confirms auth.
    return {"status": "ok", "message": f"Logged out {user.username}"}


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
