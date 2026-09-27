"""Auth dependencies: bearer-token extraction and permission gating.

``get_current_user`` is an async FastAPI dependency that:
  1. Extracts the JWT via ``OAuth2PasswordBearer``.
  2. Decodes and validates the token (signature + expiration) via ``decode_token``.
  3. Validates the payload structure with ``TokenPayload``.
  4. Rejects refresh tokens (``type != "access"``).
  5. Fetches the user record from the database via ``UserRepository``.
  6. Raises ``HTTPException(401, ...)`` for every authentication failure.

``require_permission`` delegates to ``get_current_user`` via ``Depends()`` and
enforces role-based permissions on top of it.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.models import Device, LockedFeature, Role, SystemSetting
from app.core.repositories import UserRepository
from app.core.ttl_cache import cache_get, cache_invalidate_prefix, cache_set
from app.shared.exceptions import AppException, ForbiddenError
from app.shared.schemas import CurrentUser, TokenPayload
from app.shared.security import consume_approval_token, decode_token, verify_password

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    device_token: Optional[str] = Header(default=None, alias="X-Device-Token"),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Authenticate the current request from a JWT bearer token.

    The ``session`` is resolved *before* the route handler's own ``session``
    dependency (because ``require_permission`` → ``get_current_user`` →
    ``get_session`` runs first in the dependency tree). FastAPI caches the
    result (``use_cache=True`` default), so both this function and the route
    handler share the **same** ``AsyncSession`` instance.

    The user lookup is wrapped in an explicit ``async with session.begin()``
    transaction. This terminates the transaction when the block exits,
    leaving the session in a clean state so the route handler can start
    its own transaction (e.g. ``PosService.process_checkout`` calls
    ``session.begin()``).

    Raises:
        HTTPException: 401 for missing, malformed, expired, or otherwise
            invalid tokens, or when the referenced user no longer exists
            or is inactive.
    """
    # Step 2 — decode & validate signature + expiration.
    # ``decode_token`` raises ``AppException`` on any JWT error; we normalize
    # to ``HTTPException`` per the route-protection specification.
    try:
        claims = decode_token(token)
    except AppException:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Structured payload validation — catches missing/mistyped claims.
    try:
        payload = TokenPayload.model_validate(claims)
    except ValidationError:
        raise HTTPException(status_code=401, detail="Malformed token")

    # Reject refresh tokens mis-used as access tokens.
    if payload.type != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Step 4 — parse user identifier from the ``sub`` claim.
    try:
        user_id = int(payload.sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Malformed token: missing user identifier",
        )

    # Step 5 — verify the user still exists and is active in the database.
    # Wrap in an explicit transaction so it commits/rolls-back cleanly and
    # leaves the shared session ready for the route handler's own transaction.
    async with session.begin():
        user = await UserRepository(session).get(user_id)
    if user is None or user.is_active != 1:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Sprint 1B rotation: a token minted before a token_version bump (password
    # change) is revoked — 401 so clients clear credentials and re-authenticate.
    if int(getattr(payload, "tvr", 1) or 1) != int(user.token_version or 1):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    # ── Device binding (Phase 4 Step 1.5, owner CHECK B) ────────────
    user_device_id: Optional[int] = None
    # When a request presents X-Device-Token, that device must still exist
    # and be un-revoked — checked on EVERY authenticated request, fail-closed.
    # Revoked/unknown devices return 401 (not 403): the mobile client handles
    # 401 by clearing tokens and returning to the login screen. Requests
    # without the header (desktop web session, health probes) are unaffected.
    if device_token:
        matched_device = None
        async with session.begin():
            candidates = await session.execute(
                select(Device).where(Device.revoked == 0)
            )
            for device in candidates.scalars():
                if verify_password(device_token, device.device_token_hash):
                    matched_device = device
                    break
        if matched_device is None:
            raise HTTPException(status_code=401, detail="Device is revoked or unknown")
        async with session.begin():
            matched_device.last_seen_at = datetime.now(timezone.utc).isoformat()
            matched_device.user_id = user_id
            session.add(matched_device)
        user_device_id = matched_device.id

    # Source role name and permissions from the database (not JWT claims)
    # to ensure they reflect current DB state after role/permission changes.
    # Role name + permissions are read per request but change rarely; cache
    # them briefly and invalidate from the roles/permissions write paths.
    perm_cache_key = f"perms:{user.role_id}"
    cached = cache_get(perm_cache_key)
    if cached is not None:
        role_name, permissions = cached
    else:
        async with session.begin():
            role_result = await session.execute(
                select(Role.name).where(Role.id == user.role_id)
            )
            role_name = role_result.scalar_one_or_none() or "unknown"
            permissions = await UserRepository(session).permissions_for_role(user.role_id)
        cache_set(perm_cache_key, (role_name, permissions), ttl_seconds=15.0)

    return CurrentUser(
        id=user.id,
        username=user.username,
        role=role_name,
        role_id=user.role_id,
        permissions=permissions,
        device_id=user_device_id,
    )


def require_permission(permission: str) -> Callable[[CurrentUser], CurrentUser]:
    """Return a dependency that enforces ``permission`` on the current user."""

    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Admin root users bypass permission checks – they have implicit full access.
        # Priority: role_id == 1 (owner) -> wildcard "*" permission -> explicit permission.
        if user.role_id == 1:
            return user
        if "*" in user.permissions:
            return user
        if permission not in user.permissions:
            raise ForbiddenError(f"Missing required permission: {permission}")
        return user

    return _check


def require_approval_token(scope: str) -> Callable[..., dict[str, object]]:
    """Return a dependency that requires a valid, unused, scope-matched approval token.

    The token is presented via the ``X-Approval-Token`` header and is single-use:
    it is invalidated on first successful validation (replay protection).
    """

    def _check(
        user: CurrentUser = Depends(get_current_user),
        x_approval_token: Optional[str] = Header(default=None, alias="X-Approval-Token"),
    ) -> dict[str, object]:
        if not x_approval_token:
            raise ForbiddenError("Approval token required for this action")
        claims = consume_approval_token(x_approval_token)
        if claims.get("scope") != scope:
            raise ForbiddenError(f"Approval token scope mismatch: expected {scope}")
        return claims

    return _check


async def _check_feature_lock(
    feature_key: str,
    x_lock_password: Optional[str],
    session: AsyncSession,
) -> bool:
    """Check if a feature is locked and if the provided password is valid.
    
    Returns True if access is allowed (not locked or valid password).
    """
    locked = await session.get(LockedFeature, feature_key)
    if not locked or not locked.is_locked:
        return True
    
    if not x_lock_password:
        return False
    
    if not locked.lock_password_hash:
        return False
    
    from app.shared.security import verify_password
    return verify_password(x_lock_password, locked.lock_password_hash)


def require_unlocked(feature_key: str):
    """Return a dependency that enforces feature lock check.
    
    If the feature is locked, requires a valid X-Lock-Password header
    (unless the user is role_id=1, which is handled at the route level).
    """
    async def _check(
        user: CurrentUser = Depends(get_current_user),
        x_lock_password: Optional[str] = Header(default=None, alias="X-Lock-Password"),
        session: AsyncSession = Depends(get_session),
    ) -> CurrentUser:
        # role_id=1 (owner) bypasses lock checks entirely
        if user.role_id == 1:
            return user
        
        allowed = await _check_feature_lock(feature_key, x_lock_password, session)
        if not allowed:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature_key}' is locked. Lock password required.",
            )
        return user
    
    return _check


async def require_setup_complete(session: AsyncSession = Depends(get_session)) -> None:
    """First-run gate (Sprint 2D): 503 until the admin completes setup.

    Reads the ``setup_complete`` SystemSetting (seeded ``false`` by
    ``seed_default_settings``); the admin flips it via
    ``POST /api/v1/admin/setup/complete`` once pharmacy identity is configured.
    Exempt routes (health, auth, setup, docs/static) are listed in main.py —
    this dependency is applied app-wide to everything else via dependency
    injection into the catch-all router.
    """
    # Router-level dependencies run BEFORE route-level ones, so this read is
    # the session's first use in the request. Close it with an explicit
    # begin()/commit() — a plain read would leave an implicit transaction open
    # (breaking get_current_user's session.begin() below), and a rollback
    # would discard the caller's pending, not-yet-committed state.
    async with session.begin():
        setting = await session.get(SystemSetting, "setup_complete")
        value = (setting.value or b"").decode("utf-8").strip().lower() if setting else ""
    if value != "true":
        raise HTTPException(
            status_code=503,
            detail={"error": "Setup not complete"},
            headers={"X-Setup-Required": "true"},
        )
