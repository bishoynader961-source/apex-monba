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
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.repositories import UserRepository
from app.shared.exceptions import AppException, ForbiddenError
from app.shared.schemas import CurrentUser, TokenPayload
from app.shared.security import consume_approval_token, decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
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

    # ``role`` and ``permissions`` are sourced from the JWT claims (the
    # signed session artifact), not the database. The DB lookup above
    # validates *existence* and *active status* only.
    return CurrentUser(
        id=user.id,
        username=user.username,
        role=payload.role,
        permissions=payload.permissions,
    )


def require_permission(permission: str) -> Callable[[CurrentUser], CurrentUser]:
    """Return a dependency that enforces ``permission`` on the current user."""

    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
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
