"""M7 — seed_clinical_defaults: permission upsert + admin grants + SIG/price codes."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, RolePermission, SigCode, PriceCode
from app.services.seed_service import seed_clinical_defaults


async def test_seed_creates_clinical_permissions(session: AsyncSession) -> None:
    await seed_clinical_defaults(session)
    perms = (await session.execute(select(Permission.feature_key))).scalars().all()
    for key in ("patients.read", "patients.write", "patients.delete",
                "insurance.read", "insurance.write",
                "members.read", "members.write",
                "dictionaries.read", "dictionaries.write",
                "dispense.create", "backup.create"):
        assert key in perms


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    await seed_clinical_defaults(session)
    count1 = (await session.execute(select(Permission.id))).scalars().all()
    await seed_clinical_defaults(session)
    count2 = (await session.execute(select(Permission.id))).scalars().all()
    assert len(count2) == len(count1)


async def test_seed_grants_all_perms_to_admin(session: AsyncSession) -> None:
    from app.core.models import Role
    role = Role(id=1, name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()

    await seed_clinical_defaults(session)
    grants = (
        await session.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == 1)
        )
    ).scalars().all()
    assert len(grants) >= 11  # all clinical perms granted


async def test_seed_creates_sig_codes(session: AsyncSession) -> None:
    await seed_clinical_defaults(session)
    codes = (await session.execute(select(SigCode.code))).scalars().all()
    assert "BID" in codes
    assert "TID" in codes
    assert "PRN" in codes


async def test_seed_creates_price_codes(session: AsyncSession) -> None:
    await seed_clinical_defaults(session)
    codes = (await session.execute(select(PriceCode.code))).scalars().all()
    assert "GEN" in codes
    assert "BRD" in codes


async def test_seed_swallows_db_error(session: AsyncSession) -> None:
    with patch.object(
        Permission, "__init__", side_effect=SQLAlchemyError("connection lost")
    ):
        await seed_clinical_defaults(session)
