"""M99 Movement History: unified stock ledger, date/type filters, RBAC."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    Dispense,
    InventoryAdjustment,
    Patient,
    Product,
    ReceivingLog,
    Role,
    RolePermission,
    SoldItem,
    User,
)
from app.core.repositories import InventoryMovementRepository
from app.services.movement_service import MovementService
from app.shared.security import hash_password

_INVENTORY_READ = ["inventory.read"]


async def _seed_admin(session: AsyncSession, perms: list[str]) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perms_objs = []
    for key in perms:
        from app.core.models import Permission

        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms_objs.append(p)
    await session.commit()
    for p in perms_objs:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    user = User(
        username="adminroot",
        display_name="Admin",
        password_hash=hash_password("password123"),
        role_id=role.id,
    )
    session.add(user)
    await session.commit()
    return user.username


async def _seed_movements(session: AsyncSession) -> None:
    """Seed receiving, sale, dispense, and adjustment events for 'TestMed'."""
    prod = Product(name="TestMed", price=10.0, is_deleted=0)
    session.add(prod)
    await session.flush()

    patient = Patient(
        name="Test Patient",
        dob="1980-01-01",
        address="",
        driver_license="",
        sex="",
        employer_id="",
        contact_phone="",
        email="",
        insurance_provider="",
        policy_number="",
        group_number="",
        patient_allergies="",
        comments="",
    )
    session.add(patient)
    await session.flush()

    session.add(ReceivingLog(
        product_name="TestMed",
        vendor_name="Acme Pharma",
        quantity=100,
        date_received="2025-01-15",
        total_cost=500.0,
        barcode="BC001",
    ))
    await session.flush()

    session.add(SoldItem(
        item_name="TestMed",
        price=12.0,
        manufacturer_barcode="",
        internal_barcode="BC001",
        timestamp_of_sale="2025-01-20 10:30:00",
        vendor_name="N/A",
    ))
    await session.flush()

    session.add(Dispense(
        patient_id=patient.id,
        product_name="TestMed",
        ndc_code="NDC001",
        sig_code="BID",
        quantity=30,
        fill_date="2025-01-25",
        price_at_time=15.0,
        insurance_copay=3.0,
        insurance_amount=0.0,
        internal_barcode="BC001",
        cashier="dr_smith",
        client_tx_id="tx001",
    ))
    await session.flush()

    session.add(InventoryAdjustment(
        product_id=prod.id,
        quantity_change=-5,
        reason="stock take",
        timestamp="2025-01-28T10:00:00Z",
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_movement_history_unified_query(session: AsyncSession) -> None:
    await _seed_movements(session)
    rows, total = await InventoryMovementRepository(session).list_movements()
    assert total == 4
    assert len(rows) == 4
    types = {r["src_type"] for r in rows}
    assert types == {"RECEIVE", "SALE", "DISPENSE", "ADJUSTMENT"}


@pytest.mark.asyncio
async def test_movement_history_date_filter(session: AsyncSession) -> None:
    await _seed_movements(session)
    rows, total = await InventoryMovementRepository(session).list_movements(
        start_date="2025-01-20",
        end_date="2025-01-26",
    )
    assert total == 2
    assert all("2025-01" in r["ts"] for r in rows)


@pytest.mark.asyncio
async def test_movement_history_type_filter(session: AsyncSession) -> None:
    await _seed_movements(session)
    rows, total = await InventoryMovementRepository(session).list_movements(
        movement_type="RECEIVE"
    )
    assert total == 1
    assert rows[0]["src_type"] == "RECEIVE"


@pytest.mark.asyncio
async def test_movement_service_returns_response(session: AsyncSession) -> None:
    await _seed_movements(session)
    resp = await MovementService(session).list_movements()
    assert resp.total == 4
    assert resp.page == 1
    assert resp.page_size == 50
    assert len(resp.items) == 4


@pytest.mark.asyncio
async def test_movement_soft_delete_guard(session: AsyncSession) -> None:
    await _seed_movements(session)
    stmt = update(Product).where(Product.name == "TestMed").values(is_deleted=1)
    await session.execute(stmt)
    await session.commit()
    rows, total = await InventoryMovementRepository(session).list_movements()
    assert total == 0


@pytest.mark.asyncio
async def test_movement_api_rbac_401(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_movements(session)
    resp = await client.get("/api/v1/inventory/movements")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_movement_api_with_auth(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_admin(session, _INVENTORY_READ)
    await _seed_movements(session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "adminroot", "password": "password123"},
    )
    token = resp.json()["access_token"]
    resp = await client.get(
        "/api/v1/inventory/movements",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert len(data["items"]) == 4
