"""Default admin user seeding — idempotent, best-effort, startup-safe."""
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import UserRepository
from app.shared.logging_config import get_logger
from app.shared.security import hash_password

logger = get_logger("seeder")

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_DISPLAY_NAME = "Admin User"
DEFAULT_ADMIN_ROLE_ID = 1


async def seed_admin_if_absent(session: AsyncSession) -> bool:
    """Seed a default admin user if none exists.

    Returns True if a new admin was created, False if it already existed.
    Never raises — all errors are logged and swallowed so startup is not blocked.
    """
    try:
        repo = UserRepository(session)
        existing = await repo.get_by_username(DEFAULT_ADMIN_USERNAME)
        if existing is not None:
            logger.info("seed_admin_skipped", reason="user_exists", username=DEFAULT_ADMIN_USERNAME)
            return False

        password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
        await repo.create(
            username=DEFAULT_ADMIN_USERNAME,
            display_name=DEFAULT_ADMIN_DISPLAY_NAME,
            password_hash=password_hash,
            role_id=DEFAULT_ADMIN_ROLE_ID,
        )
        logger.info(
            "seed_admin_created",
            username=DEFAULT_ADMIN_USERNAME,
            role_id=DEFAULT_ADMIN_ROLE_ID,
        )
        return True
    except SQLAlchemyError as exc:
        logger.error("seed_admin_db_error", error=str(exc), username=DEFAULT_ADMIN_USERNAME)
        await session.rollback()
        return False
    except Exception as exc:  # noqa: BLE001 — last line of defense for startup safety
        logger.error("seed_admin_unexpected_error", error=str(exc), username=DEFAULT_ADMIN_USERNAME)
        return False
