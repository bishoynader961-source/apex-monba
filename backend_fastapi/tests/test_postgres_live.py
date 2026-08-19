"""Live PostgreSQL verification (B6 / R1).

Skips unless ``PHARMACY_DB_URL`` is a ``postgresql://`` URL (provided by the CI
service container). Proves the dialect-agnostic backend actually connects to a
real Postgres, materialises the v{SCHEMA_VERSION} schema via ``create_all``, and
round-trips a row through ``UserRepository`` using the ``asyncpg`` driver.
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import Base, build_engine
from app.core.models import User
from app.core.repositories import UserRepository

PG_URL = os.environ.get("PHARMACY_DB_URL", "")

pytestmark = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"),
    reason="Live Postgres verification requires PHARMACY_DB_URL (CI service container).",
)


@pytest_asyncio.fixture
async def pg_engine():
    engine = build_engine(PG_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def test_live_postgres_user_roundtrip(pg_engine) -> None:
    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        user = await UserRepository(s).create(
            username="pguser", display_name="PG", password_hash=b"x", role_id=3
        )
        await s.commit()
        assert user.id is not None
        fetched = await UserRepository(s).get_by_username("pguser")
        assert fetched is not None and fetched.id == user.id
    # Persistence across sessions proves a real server round-trip (not in-memory).
    async with maker() as s:
        again = await UserRepository(s).get_by_username("pguser")
        assert again is not None and again.pin_pepper_version == 1
