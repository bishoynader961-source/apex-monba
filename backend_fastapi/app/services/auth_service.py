"""Authentication service: orchestrates user lookup, password verification
(including legacy scrypt lazy-upgrade and lockout throttling), and token issuance.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.models import Role, User
from app.core.repositories import UserRepository
from app.shared.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.shared.schemas import CurrentUser, PinLoginRequest, Token, UserCreate, UserPublic
from app.shared.security import (
    create_access_token,
    create_approval_token,
    create_refresh_token,
    decode_token,
    get_pin_pepper,
    hash_password,
    upgrade_legacy_hash,
    verify_password,
    verify_pin,
    seal_lockout,
    verify_lockout,
    generate_pin_salt,
    hash_pin,
)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
PIN_LOCKOUT_ATTEMPTS = 5
PIN_LOCKOUT_MINUTES = 15


def _parse_locked_until(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def authenticate(self, username: str, password: str) -> User:
        repo = UserRepository(self.session)
        user = await repo.get_by_username(username)
        if user is None or user.is_active != 1:
            raise UnauthorizedError("Invalid username or password")

        locked = _parse_locked_until(user.locked_until)
        if locked is not None and locked > datetime.now(timezone.utc):
            raise ForbiddenError("Account locked due to too many failed attempts")

        if not verify_password(password, user.password_hash):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                ).isoformat()
            await self.session.commit()
            raise UnauthorizedError("Invalid username or password")

        # Successful login: reset throttling counters and lazy-upgrade legacy hashes.
        user.failed_attempts = 0
        user.locked_until = None
        if not user.password_hash.startswith(b"$2"):
            await repo.update_password_hash(user, upgrade_legacy_hash(password))
        await self.session.commit()
        return user

    async def _build_token(self, user: User) -> Token:
        repo = UserRepository(self.session)
        permissions = await repo.permissions_for_role(user.role_id)
        role_result = await self.session.execute(select(Role.name).where(Role.id == user.role_id))
        role_name: Optional[str] = role_result.scalar_one_or_none()
        access = create_access_token(
            str(user.id), role_name or "unknown", permissions, username=user.username
        )
        refresh = create_refresh_token(str(user.id))
        return Token(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))

    async def login(self, username: str, password: str) -> Token:
        user = await self.authenticate(username, password)
        return await self._build_token(user)

    async def refresh(self, refresh_token: str) -> Token:
        claims = decode_token(refresh_token)
        if claims.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")
        user = await self.session.get(User, int(claims["sub"]))
        if user is None or user.is_active != 1:
            raise UnauthorizedError("User no longer active")
        return await self._build_token(user)

    async def register(self, payload: UserCreate) -> UserPublic:
        repo = UserRepository(self.session)
        if await repo.get_by_username(payload.username) is not None:
            raise ConflictError(
                "Username already registered", details={"username": payload.username}
            )
        user = await repo.create(
            username=payload.username,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
            role_id=payload.role_id,
        )
        return UserPublic.model_validate(user)

    async def set_pin(self, username: str, pin: str) -> None:
        """Set/reset a user's device-bound PIN (C.4). Requires the pepper to be
        available on this machine; raises if the DB-only path can't be bound."""
        repo = UserRepository(self.session)
        user = await repo.get_by_username(username)
        if user is None:
            raise UnauthorizedError("Invalid username")
        pepper = get_pin_pepper().derive()
        if pepper is None:
            raise UnauthorizedError("PIN setup unavailable on this device")
        user.pin_salt = generate_pin_salt()
        user.pin_hash = hash_pin(pin, user.pin_salt, pepper)
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        user.lockout_hmac = seal_lockout(0, None, pepper)
        await self.session.commit()

    async def pin_login(self, username: str, pin: str) -> Token:
        """Kiosk PIN login (C.4): device-bound, peppered PBKDF2 with tamper-evident
        lockout. Returns a JWT on success, or raises:
          * UnauthorizedError — unknown user / no PIN / wrong PIN / pepper
            unavailable (DB exfiltrated off-machine can never pass here).
          * ForbiddenError — locked (too many attempts) or tampered counters.
        """
        repo = UserRepository(self.session)
        user = await repo.get_by_username(username)
        if user is None or user.is_active != 1 or not user.pin_hash:
            raise UnauthorizedError("Invalid username or PIN")

        pepper = get_pin_pepper().derive()
        if pepper is None:
            # Pepper unrecoverable off-machine (or DPAPI down) -> cannot verify.
            raise UnauthorizedError("PIN verification unavailable on this device")

        # Tamper-evidence: lockout counters must be HMAC-sealed by the pepper. An
        # offline-edited DB fails this -> force a lock (can't reset lockout offline).
        if not verify_lockout(
            user.pin_failed_attempts or 0, user.pin_locked_until, user.lockout_hmac, pepper
        ):
            user.pin_locked_until = (
                datetime.now(timezone.utc) + timedelta(minutes=PIN_LOCKOUT_MINUTES)
            ).isoformat()
            await self.session.commit()
            raise ForbiddenError("Account locked due to tampered lockout state")

        locked = _parse_locked_until(user.pin_locked_until)
        if locked is not None and locked > datetime.now(timezone.utc):
            raise ForbiddenError("Account locked due to too many failed attempts")

        if not verify_pin(pin, user.pin_salt, user.pin_hash, pepper):
            user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
            if user.pin_failed_attempts >= PIN_LOCKOUT_ATTEMPTS:
                user.pin_locked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=PIN_LOCKOUT_MINUTES)
                ).isoformat()
            user.lockout_hmac = seal_lockout(
                user.pin_failed_attempts, user.pin_locked_until, pepper
            )
            await self.session.commit()
            raise UnauthorizedError("Invalid username or PIN")

        # Success: reset counters + reseal so a later offline tamper is detected.
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        user.lockout_hmac = seal_lockout(0, None, pepper)
        await self.session.commit()
        return await self._build_token(user)

    async def approve_action(self, username: str, pin: str, scope: str) -> str:
        """Manager high-risk action approval (Concern 1): verify the manager PIN
        (device-bound, lockout-throttled) and issue a single-use approval token scoped
        to ``scope``. The caller presents it via the ``X-Approval-Token`` header."""
        repo = UserRepository(self.session)
        user = await repo.get_by_username(username)
        if user is None or user.is_active != 1 or not user.pin_hash:
            raise UnauthorizedError("Invalid username or PIN")

        pepper = get_pin_pepper().derive()
        if pepper is None:
            raise UnauthorizedError("PIN verification unavailable on this device")

        if not verify_lockout(
            user.pin_failed_attempts or 0, user.pin_locked_until, user.lockout_hmac, pepper
        ):
            user.pin_locked_until = (
                datetime.now(timezone.utc) + timedelta(minutes=PIN_LOCKOUT_MINUTES)
            ).isoformat()
            await self.session.commit()
            raise ForbiddenError("Account locked due to tampered lockout state")

        locked = _parse_locked_until(user.pin_locked_until)
        if locked is not None and locked > datetime.now(timezone.utc):
            raise ForbiddenError("Account locked due to too many failed attempts")

        if not verify_pin(pin, user.pin_salt, user.pin_hash, pepper):
            user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
            if user.pin_failed_attempts >= PIN_LOCKOUT_ATTEMPTS:
                user.pin_locked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=PIN_LOCKOUT_MINUTES)
                ).isoformat()
            user.lockout_hmac = seal_lockout(
                user.pin_failed_attempts, user.pin_locked_until, pepper
            )
            await self.session.commit()
            raise UnauthorizedError("Invalid username or PIN")

        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        user.lockout_hmac = seal_lockout(0, None, pepper)
        await self.session.commit()
        return create_approval_token(subject=user.username, scope=scope)


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(session)
