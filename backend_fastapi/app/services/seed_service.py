"""Default admin user seeding — idempotent, best-effort, startup-safe."""
from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, RolePermission, SigCode, PriceCode
from app.core.repositories import UserRepository
from app.shared.logging_config import get_logger
from app.shared.security import hash_password

logger = get_logger("seeder")

DEFAULT_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "admin123")
DEFAULT_ADMIN_DISPLAY_NAME = "Admin User"
DEFAULT_ADMIN_ROLE_ID = 1

# Canonical permission surface: existing platform perms + the new clinical perms
# (decision 6). Upserted + granted to the admin role so a fresh DB is usable.
_ALL_PERMISSIONS = [
    # platform
    "inventory.read",
    "inventory.write",
    "inventory.reports",
    "pos.checkout",
    "pos.drawer",
    "pos.pepper.rotate",
    "users.read",
    "users.write",
    # clinical / patient management (new)
    "patients.read",
    "patients.write",
    "patients.delete",
    "insurance.read",
    "insurance.write",
    "members.read",
    "members.write",
    "dictionaries.read",
    "dictionaries.write",
    "dispense.create",
    "backup.create",
]

_DEFAULT_SIG_CODES = [
    ("BID", "Take one tablet twice daily"),
    ("TID", "Take one tablet three times daily"),
    ("QID", "Take one tablet four times daily"),
    ("QD", "Take one tablet once daily"),
    ("QHS", "Take one tablet at bedtime"),
    ("PRN", "Take as needed"),
    ("PO", "Take by mouth"),
]

_DEFAULT_PRICE_CODES = [
    ("GEN", "Generic", 0),
    ("BRD", "Brand", 0),
]



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

        if (
            os.getenv("APP_ENV", "development") == "production"
            and DEFAULT_ADMIN_PASSWORD == "admin123"
        ):
            logger.warning(
                "seed_admin_using_default_credentials_in_production",
                hint="set INITIAL_ADMIN_USER/INITIAL_ADMIN_PASSWORD env to override",
            )
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


async def seed_clinical_defaults(session: AsyncSession) -> None:
    """Idempotently upsert the clinical permission rows, grant them (and the
    existing platform perms) to the admin role, and seed default SIG/price codes.
    Best-effort: never raises (mirrors ``seed_admin_if_absent`` startup safety).
    """
    try:
        # ── Permissions: upsert by feature_key ─────────────────────────────
        existing = {
            row[1]: row[0]
            for row in (
                await session.execute(select(Permission.id, Permission.feature_key))
            ).all()
        }
        granted: set[int] = set()
        for key in _ALL_PERMISSIONS:
            pid = existing.get(key)
            if pid is None:
                perm = Permission(feature_key=key, description=key)
                session.add(perm)
                await session.flush()
                pid = perm.id
            granted.add(int(pid))
        # ── Grant every permission to the admin role (idempotent) ────────
        rows = (
            await session.execute(
                select(RolePermission.permission_id).where(RolePermission.role_id == DEFAULT_ADMIN_ROLE_ID)
            )
        ).scalars().all()
        already = set(int(r) for r in rows)
        for pid in granted - already:
            session.add(RolePermission(role_id=DEFAULT_ADMIN_ROLE_ID, permission_id=pid, granted=1))
        # ── Default SIG codes ────────────────────────────────────────────
        for code, text in _DEFAULT_SIG_CODES:
            exists = await session.scalar(select(SigCode.id).where(SigCode.code == code))
            if exists is None:
                session.add(SigCode(code=code, full_text=text))
        # ── Default price codes ──────────────────────────────────────────
        for code, desc, price in _DEFAULT_PRICE_CODES:
            exists = await session.scalar(select(PriceCode.id).where(PriceCode.code == code))
            if exists is None:
                session.add(PriceCode(code=code, description=desc, price=price))
        await session.commit()
        logger.info("seed_clinical_complete", permissions=len(granted))
    except SQLAlchemyError as exc:
        logger.error("seed_clinical_db_error", error=str(exc))
        await session.rollback()
    except Exception as exc:  # noqa: BLE001 — startup safety
        logger.error("seed_clinical_unexpected_error", error=str(exc))

