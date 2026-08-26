"""M99 Demand Analytics: item velocity, revenue, reorder intelligence, RBAC."""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    Dispense,
    Patient,
    Product,
    ReceivingLog,
    Role,
    RolePermission,
    SoldItem,
)
from app.core.repositories import DemandAnalyticsRepository, UserRepository
from app.services.demand_analytics_service import DemandAnalyticsService
from app.shared.schemas import DemandAnalyticsSummary
from app.shared.security import hash_password

_ANALYTICS_READ = ["analytics.read"]


async def _seed_admin(session: AsyncSession, perms: list[str]) -> str:
    role = Role(name="analytics_admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    from app.core.models import Permission

    perms_objs = []
    for key in perms:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms_objs.append(p)
    await session.commit()
    for p in perms_objs:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create(
        "analytics_admin", "Admin", hash_password("password123"), role.id
    )
    return "analytics_admin"


async def _seed_demand(session: AsyncSession) -> None:
    """Seed POS sales and clinical dispenses for demand analytics."""
    prod = Product(name="FastMoving", price=10.0, category="OTC", is_deleted=0)
    session.add(prod)
    prod2 = Product(name="SlowMoving", price=20.0, category="PRESCRIPTION", is_deleted=0)
    session.add(prod2)
    await session.flush()

    patient = Patient(
        name="Demand Patient",
        dob="1990-01-01",
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

    # 3 POS sales for FastMoving on Jan 20
    for i in range(3):
        session.add(SoldItem(
            item_name="FastMoving",
            price=12.0,
            manufacturer_barcode="",
            internal_barcode="FM001",
            timestamp_of_sale="2025-01-20 10:00:00",
            vendor_name="N/A",
        ))

    # 2 dispenses for FastMoving on Jan 21
    for i in range(2):
        session.add(Dispense(
            patient_id=patient.id,
            product_name="FastMoving",
            ndc_code="NDC001",
            sig_code="BID",
            quantity=1,
            fill_date="2025-01-21",
            price_at_time=15.0,
            insurance_copay=3.0,
            insurance_amount=0.0,
            internal_barcode="FM001",
            cashier="dr_smith",
            client_tx_id=f"tx_fast_{i}",
        ))

    # 1 POS sale + 1 dispense for SlowMoving on Jan 22
    session.add(SoldItem(
        item_name="SlowMoving",
        price=22.0,
        manufacturer_barcode="",
        internal_barcode="SM001",
        timestamp_of_sale="2025-01-22 14:00:00",
        vendor_name="N/A",
    ))
    session.add(Dispense(
        patient_id=patient.id,
        product_name="SlowMoving",
        ndc_code="NDC002",
        sig_code="QD",
        quantity=1,
        fill_date="2025-01-22",
        price_at_time=25.0,
        insurance_copay=5.0,
        insurance_amount=0.0,
        internal_barcode="SM001",
        cashier="dr_smith",
        client_tx_id="tx_slow_0",
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_demand_aggregates_date_filter(session: AsyncSession) -> None:
    await _seed_demand(session)
    repo = DemandAnalyticsRepository(session)

    # Full window (Jan 20-22)
    rows = await repo.demand_aggregates("2025-01-20", "2025-01-22")
    assert len(rows) == 2
    names = {r["product_name"] for r in rows}
    assert names == {"FastMoving", "SlowMoving"}

    # Filtered to Jan 20 only (3 POS sales only)
    rows = await repo.demand_aggregates("2025-01-20", "2025-01-20")
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_demand_aggregates_category_filter(session: AsyncSession) -> None:
    await _seed_demand(session)
    repo = DemandAnalyticsRepository(session)

    rows = await repo.demand_aggregates("2025-01-20", "2025-01-22", category="OTC")
    assert len(rows) == 1
    assert rows[0]["product_name"] == "FastMoving"


@pytest.mark.asyncio
async def test_demand_service_math_accuracy(session: AsyncSession) -> None:
    await _seed_demand(session)
    svc = DemandAnalyticsService(session)
    summary: DemandAnalyticsSummary = await svc.compute(
        start_date="2025-01-20", end_date="2025-01-22", lead_time_days=7
    )
    total_qty = sum(it.total_quantity_demanded for it in summary.items)
    assert total_qty == 7  # 3 POS + 2 dispense (Fast) + 1 POS + 1 dispense (Slow)
    rev = sum((it.total_revenue for it in summary.items), Decimal("0"))
    assert rev == Decimal("113.00").quantize(Decimal("0.01"))  # 3*12 + 2*15 + 22 + 25


@pytest.mark.asyncio
async def test_demand_service_velocity_classification(session: AsyncSession) -> None:
    await _seed_demand(session)
    svc = DemandAnalyticsService(session)
    summary = await svc.compute(
        start_date="2025-01-20", end_date="2025-01-22"
    )
    by_name = {it.product_name: it for it in summary.items}
    assert by_name["FastMoving"].velocity_category in ("FAST_MOVING", "MODERATE_MOVING", "SLOW_MOVING")
    assert by_name["SlowMoving"].velocity_category in ("FAST_MOVING", "MODERATE_MOVING", "SLOW_MOVING", "NON_MOVING")
    # FastMoving should be higher velocity than SlowMoving
    velocity_order = ("FAST_MOVING", "MODERATE_MOVING", "SLOW_MOVING")
    fast_idx = velocity_order.index(by_name["FastMoving"].velocity_category)
    slow_idx = velocity_order.index(by_name["SlowMoving"].velocity_category)
    assert fast_idx <= slow_idx


@pytest.mark.asyncio
async def test_demand_service_reorder_suggestion(session: AsyncSession) -> None:
    await _seed_demand(session)
    svc = DemandAnalyticsService(session)
    summary = await svc.compute(
        start_date="2025-01-20", end_date="2025-01-22", lead_time_days=7
    )
    by_name = {it.product_name: it for it in summary.items}
    # FastMoving: 5 units over 3 days => avg ~1.67/day * 7 = 11.67 - on_hand(0) = ~12
    # The reorder_suggestion is a float (from the schema)
    assert by_name["FastMoving"].reorder_suggestion > 0


@pytest.mark.asyncio
async def test_demand_api_rbac_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/analytics/demand")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_demand_api_with_auth(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_admin(session, _ANALYTICS_READ)
    await _seed_demand(session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "analytics_admin", "password": "password123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    resp = await client.get(
        "/api/v1/analytics/demand",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Default: 30 days back from today
    assert "window_start" in data
    assert len(data["items"]) == 2
