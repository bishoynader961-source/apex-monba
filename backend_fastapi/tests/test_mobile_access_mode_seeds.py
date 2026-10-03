"""Phase 4 Step 1.4 — mobile_access_mode SystemSetting seeds.

The desktop shell reads ``mobile_access_mode`` from ``system_settings`` at
startup to decide the backend bind host (shared → 0.0.0.0, independent/cloud
→ 127.0.0.1). These tests pin the seed contract: the key must exist on fresh
databases with a safe default, and existing values must never be overwritten
by reseeding.

Audit M2: the safe default for NEW installs is now ``independent``
(loopback-only). Existing installs keep whatever value they already store —
seed never overwrites — so deployed ``shared`` instances are unaffected.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SystemSetting
from app.services.seed_service import seed_default_settings


@pytest.mark.asyncio
async def test_mobile_access_mode_seeded_loopback_default(session: AsyncSession) -> None:
    """Audit M2: fresh installs seed 'independent' (loopback-only bind)."""
    await seed_default_settings(session)
    row = await session.get(SystemSetting, "mobile_access_mode")
    assert row is not None, "mobile_access_mode must be seeded on fresh databases"
    assert row.value.decode("utf-8") == "independent"


@pytest.mark.asyncio
async def test_mobile_access_mode_shared_value_not_overwritten(session: AsyncSession) -> None:
    """Auto-migrate: pre-M2 installs seeded 'shared' must keep working (QR)."""
    session.add(SystemSetting(key="mobile_access_mode", value=b"shared"))
    await session.commit()

    await seed_default_settings(session)
    row = await session.get(SystemSetting, "mobile_access_mode")
    assert row is not None
    assert row.value.decode("utf-8") == "shared", "reseeding must not clobber existing 'shared' installs"


@pytest.mark.asyncio
async def test_mobile_access_mode_independent_value_not_overwritten(session: AsyncSession) -> None:
    session.add(SystemSetting(key="mobile_access_mode", value=b"independent"))
    await session.commit()

    await seed_default_settings(session)
    row = await session.get(SystemSetting, "mobile_access_mode")
    assert row is not None
    assert row.value.decode("utf-8") == "independent", "reseeding must not clobber admin-set modes"


@pytest.mark.asyncio
async def test_qr_secret_key_placeholder_seeded_empty(session: AsyncSession) -> None:
    """qr_secret_key is reserved for the Step 1.5 signed-QR gateway; it seeds
    empty so no placeholder value can ever act as a signing key."""
    await seed_default_settings(session)
    row = await session.get(SystemSetting, "qr_secret_key")
    assert row is not None
    assert row.value.decode("utf-8") == ""
