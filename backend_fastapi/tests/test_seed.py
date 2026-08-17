"""Tests for admin user seeding — creation, hashing, idempotency, startup safety."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import bcrypt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import UserRepository
from app.services.seed_service import seed_admin_if_absent


async def test_seed_creates_admin_if_absent(session: AsyncSession) -> None:
    result = await seed_admin_if_absent(session)
    assert result is True
    user = await UserRepository(session).get_by_username("admin")
    assert user is not None
    assert user.display_name == "Admin User"
    assert user.role_id == 1
    assert user.is_active == 1


async def test_seed_password_is_bcrypt_hashed(session: AsyncSession) -> None:
    await seed_admin_if_absent(session)
    user = await UserRepository(session).get_by_username("admin")
    assert user is not None
    assert user.password_hash.startswith(b"$2")
    assert bcrypt.checkpw(b"admin123", user.password_hash)


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    await seed_admin_if_absent(session)
    user1 = await UserRepository(session).get_by_username("admin")
    assert user1 is not None
    original_hash = user1.password_hash
    result = await seed_admin_if_absent(session)
    assert result is False
    user2 = await UserRepository(session).get_by_username("admin")
    assert user2 is not None
    assert user2.password_hash == original_hash


async def test_seed_swallows_db_error(session: AsyncSession) -> None:
    """A SQLAlchemyError during lookup must not propagate — returns False only."""
    with patch.object(
        UserRepository,
        "get_by_username",
        new_callable=AsyncMock,
        side_effect=SQLAlchemyError("connection lost"),
    ):
        result = await seed_admin_if_absent(session)
    assert result is False
