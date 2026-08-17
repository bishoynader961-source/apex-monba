"""
Default-admin database seeder for the Pharmacy Suite backend.

Creates (if missing) a `users` table and inserts exactly one default administrator
row, idempotently. Safe to re-run: an existing ``admin`` row is left in place.

Usage:
    python seed_admin.py
    DATABASE_URL="sqlite+aiosqlite:///./seed_admin.db" python seed_admin.py

Configuration:
    DATABASE_URL  SQLAlchemy async URL of the target DB.
                  Default: "sqlite+aiosqlite:///./seed_admin.db" (isolated, never touches
                  the live pharmacy.db — see PROJET_MAP/PLAN D4).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

import bcrypt
from sqlalchemy import Integer, String, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ── Logging (stderr; never print) ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("seed_admin")

# bcrypt work factor. Cost 12 matches the application's security policy (MASTER_CODING_PROMPT.md §4.1).
_BCRYPT_ROUNDS = 12

# Seed fixture values. The plain-text password is a documented dev fixture, not a prod secret.
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
ADMIN_DISPLAY_NAME = "Admin User"
ADMIN_ROLE_ID = 1


# ── Declarative model (self-contained, creates the table if absent) ─────────────
class Base(DeclarativeBase):
    pass


class User(Base):
    """Minimal admin table for seeding (standalone; not the app's live schema)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, nullable=False)


def get_database_url() -> str:
    """Resolve the target DB URL from the environment, defaulting to an isolated SQLite file."""
    return os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./seed_admin.db")


def create_engine() -> AsyncEngine:
    """Build the async engine.

    SQLite connections used across threads require ``check_same_thread=False``;
    ``pool_pre_ping`` guards against stale connections.
    """
    engine = create_async_engine(
        get_database_url(),
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    logger.info("Engine created for database: %s", get_database_url())
    return engine


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (cost 12) and return a str digest.

    Step 1: ``bcrypt.gensalt(rounds=12)`` produces the salt.
    Step 2: ``bcrypt.hashpw`` produces the bcrypt digest bytes.
    Step 3: decode to ``str`` for storage in a String column — never store plaintext.
    """
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    digest = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return digest.decode("utf-8")


async def seed_admin(session: AsyncSession) -> bool:
    """Idempotently insert the default admin.

    Returns True if a row was inserted, False if it was skipped (already present).
    """
    # Idempotency pre-check: skip insertion if the admin row already exists.
    existing = await session.execute(
        select(User).where(User.username == ADMIN_USERNAME)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info("Admin user '%s' already exists — skipping insert.", ADMIN_USERNAME)
        return False

    # Hashing step: only the bcrypt digest is stored, never the plaintext.
    admin = User(
        username=ADMIN_USERNAME,
        password=hash_password(ADMIN_PASSWORD),
        display_name=ADMIN_DISPLAY_NAME,
        role_id=ADMIN_ROLE_ID,
    )
    session.add(admin)
    try:
        await session.commit()
        logger.info(
            "Seeded default admin: username='%s', display_name='%s', role_id=%d.",
            ADMIN_USERNAME,
            ADMIN_DISPLAY_NAME,
            ADMIN_ROLE_ID,
        )
        return True
    except IntegrityError:
        # Defensive backstop for the UNIQUE(username) constraint race.
        await session.rollback()
        logger.warning("Concurrent insert of admin row detected (IntegrityError) — rolled back.")
        return False


async def run() -> int:
    engine = create_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # Create the table if it does not exist (CREATE TABLE IF NOT EXISTS semantics).
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OperationalError as exc:
        logger.error("Database connection failure: %s", exc)
        await engine.dispose()
        return 1

    try:
        # open commit/rollback close lifecycle via async context manager.
        async with async_session() as session:
            await seed_admin(session)
    except SQLAlchemyError as exc:
        logger.error("Unexpected database error during seeding: %s", exc)
        await engine.dispose()
        return 1
    finally:
        # Guarantee the engine (and its connection pool) is released.
        await engine.dispose()
    return 0


def main() -> Optional[int]:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
