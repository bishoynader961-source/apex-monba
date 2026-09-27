"""Tests for demo mode (Task 4 Step 4.7): settings.manage-gated admin routes,
idempotent demo seeding, marker-scoped teardown, and the seeded demo_mode default."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Patient, Product, Receipt, Role, SystemSetting, User
from app.core.repositories import UserRepository
from app.core.seed_demo_data import clear_demo_data, seed_demo_data, set_demo_mode
from app.shared.security import hash_password


async def _seed_admin_user(session: AsyncSession) -> None:
    """Mirror production, where seed_admin_if_absent guarantees users.id == 1
    (EPCSPrescription.created_by references it)."""
    role = Role(name="demoadmin-service", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    await UserRepository(session).create("serviceadmin", "Service Admin", hash_password("password123"), role.id)


async def _token(client: AsyncClient, session: AsyncSession) -> str:
    from app.core.models import Role

    role = Role(name="demoadmin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    await UserRepository(session).create("demoadmin", "Demo Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "demoadmin", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _token(client, session)
    return {"Authorization": f"Bearer {token}"}


# ── Seeded default ────────────────────────────────────────────────────────────


async def test_demo_mode_seeded_false(session: AsyncSession):
    from app.services.seed_service import seed_default_settings

    await seed_default_settings(session)
    setting = await session.get(SystemSetting, "demo_mode")
    assert setting is not None
    assert (setting.value or b"").decode("utf-8") == "false"


# ── Service-level: idempotency + teardown ────────────────────────────────────


async def test_seed_demo_data_idempotent(session: AsyncSession):
    await _seed_admin_user(session)
    first = await seed_demo_data(session)
    assert first["products"] == 5
    assert first["patients"] == 3
    assert first["prescriptions"] == 2
    assert first["receipts"] == 5
    assert first["wc_claims"] == 1

    second = await seed_demo_data(session)
    assert second == {"products": 0, "patients": 0, "prescriptions": 0, "receipts": 0, "wc_claims": 0}

    products = (await session.execute(select(Product).where(Product.name.like("Demo %")))).scalars().all()
    assert len(products) == 5
    patients = (await session.execute(select(Patient).where(Patient.name.like("Demo Patient %")))).scalars().all()
    assert len(patients) == 3


async def test_clear_demo_data_removes_only_demo_rows(session: AsyncSession):
    await _seed_admin_user(session)
    await seed_demo_data(session)
    # User data that must survive teardown.
    session.add(Patient(name="Real Person", dob="1990-01-01"))
    session.add(Product(name="Real Med"))
    await session.commit()

    counts = await clear_demo_data(session)
    assert counts["receipts"] == 5
    assert counts["patients"] == 3
    assert counts["products"] == 5

    names = (await session.execute(select(Patient.name))).scalars().all()
    assert names == ["Real Person"]
    meds = (await session.execute(select(Product.name))).scalars().all()
    assert meds == ["Real Med"]
    receipts = (await session.execute(select(Receipt))).scalars().all()
    assert receipts == []


async def test_set_demo_mode_roundtrip(session: AsyncSession):
    await set_demo_mode(session, True)
    setting = await session.get(SystemSetting, "demo_mode")
    assert (setting.value or b"").decode("utf-8") == "true"
    await set_demo_mode(session, False)
    await session.refresh(setting)
    assert (setting.value or b"").decode("utf-8") == "false"


# ── Route-level: RBAC + flow ─────────────────────────────────────────────────


async def test_demo_routes_require_auth(client: AsyncClient):
    assert (await client.get("/api/v1/admin/demo/status")).status_code == 401
    assert (await client.post("/api/v1/admin/demo/seed")).status_code == 401
    assert (await client.post("/api/v1/admin/demo/reset")).status_code == 401
    assert (await client.post("/api/v1/admin/demo/clear")).status_code == 401


async def test_demo_seed_reset_clear_flow(client: AsyncClient, auth: dict[str, str]):
    status = await client.get("/api/v1/admin/demo/status", headers=auth)
    assert status.status_code == 200
    assert status.json() == {"enabled": False}

    seeded = await client.post("/api/v1/admin/demo/seed", headers=auth)
    assert seeded.status_code == 201, seeded.text
    body = seeded.json()
    assert body["enabled"] is True
    assert body["counts"]["products"] == 5

    # Idempotent re-seed adds nothing.
    again = await client.post("/api/v1/admin/demo/seed", headers=auth)
    assert again.status_code == 201
    assert all(v == 0 for v in again.json()["counts"].values())

    reset = await client.post("/api/v1/admin/demo/reset", headers=auth)
    assert reset.status_code == 200
    assert reset.json()["demo_mode"] is True

    cleared = await client.post("/api/v1/admin/demo/clear", headers=auth)
    assert cleared.status_code == 200
    assert cleared.json() == {
        "enabled": False,
        "counts": {"receipt_items": 5, "receipts": 5, "prescriptions": 2, "wc_claims": 1, "products": 5, "patients": 3},
    }
