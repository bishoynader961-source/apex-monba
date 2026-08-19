"""B5 gap tests: returns/refunds, sales report, tamper-evident audit chain."""
from __future__ import annotations

from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    AuditLog,
    InventoryExtended,
    Permission,
    Product,
    Role,
    RolePermission,
    SyncInventory,
)
from app.core.repositories import AuditRepository, UserRepository
from app.shared.security import hash_password


_PERMS = [
    "inventory.read",
    "inventory.write",
    "inventory.reports",
    "pos.checkout",
    "pos.drawer",
    "users.write",
]


async def _seed_admin(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perms = [Permission(feature_key=k, description=k) for k in _PERMS]
    session.add_all(perms)
    await session.commit()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "adminroot", "password": "password123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _add_product(session: AsyncSession, name: str, price: float) -> None:
    session.add(
        Product(
            name=name,
            price=Decimal(str(price)),
            internal_unique_barcode=f"INT-{name[:3].upper()}",
            vendor_name="Acme",
            expiry_date="2030-01-01",
        )
    )
    await session.commit()


async def _seed_stock(session: AsyncSession, name: str, qty: int) -> None:
    session.add(InventoryExtended(drug_name=name, on_hand=qty))
    session.add(SyncInventory(product_name=name, on_hand=qty))
    await session.commit()


async def test_refund_reverses_stock_and_ledger(client: AsyncClient, session: AsyncSession) -> None:
    token = await _seed_admin(client, session)
    headers = {"Authorization": f"Bearer {token}"}
    await _add_product(session, "Aspirin", 5.00)
    await _seed_stock(session, "Aspirin", 10)

    resp = await client.post(
        "/api/v1/pos/checkout",
        headers=headers,
        json={"line_items": [{"product_name": "Aspirin", "quantity": 2}], "payment_method": "Cash"},
    )
    assert resp.status_code == 201
    receipt_id = resp.json()["receipt_id"]
    receipt_total = Decimal(resp.json()["total_amount"])

    on_hand = (await session.execute(
        select(func.sum(InventoryExtended.on_hand)).where(InventoryExtended.drug_name == "Aspirin")
    )).scalar() or 0
    assert on_hand == 8

    r = await client.post(
        "/api/v1/pos/refund",
        headers=headers,
        json={"receipt_id": receipt_id, "reason": "customer return"},
    )
    assert r.status_code == 200
    assert Decimal(r.json()["total_amount"]) == -receipt_total

    on_hand = (await session.execute(
        select(func.sum(InventoryExtended.on_hand)).where(InventoryExtended.drug_name == "Aspirin")
    )).scalar() or 0
    assert on_hand == 10

    # Refunding the same receipt twice is rejected.
    dup = await client.post(
        "/api/v1/pos/refund", headers=headers, json={"receipt_id": receipt_id}
    )
    assert dup.status_code == 409


async def test_sales_report_aggregates(client: AsyncClient, session: AsyncSession) -> None:
    token = await _seed_admin(client, session)
    headers = {"Authorization": f"Bearer {token}"}
    await _add_product(session, "Ibuprofen", 3.00)
    await _seed_stock(session, "Ibuprofen", 20)
    await client.post(
        "/api/v1/pos/checkout",
        headers=headers,
        json={"line_items": [{"product_name": "Ibuprofen", "quantity": 1}], "payment_method": "Cash"},
    )
    # Refund the sale above via direct refund of receipt id 1.
    await client.post("/api/v1/pos/refund", headers=headers, json={"receipt_id": 1})

    rep = await client.get("/api/v1/pos/reports/sales", headers=headers)
    assert rep.status_code == 200
    body = rep.json()
    assert body["receipt_count"] == 1
    assert Decimal(body["gross_revenue"]) > 0
    assert Decimal(body["refund_total"]) < 0
    assert Decimal(body["net_revenue"]) == Decimal(body["gross_revenue"]) + Decimal(
        body["refund_total"]
    )


async def test_audit_chain_is_tamper_evident(client: AsyncClient, session: AsyncSession) -> None:
    token = await _seed_admin(client, session)
    headers = {"Authorization": f"Bearer {token}"}

    # A logged action establishes chain entries.
    await AuditRepository(session).log(action="test.event", details="original", category="test")
    await session.commit()

    verify = await client.get("/api/v1/audit/verify", headers=headers)
    assert verify.status_code == 200
    assert verify.json()["valid"] is True

    # Tamper with a persisted audit row's details.
    row = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().first()
    row.details = "tampered"
    await session.commit()

    verify2 = await client.get("/api/v1/audit/verify", headers=headers)
    assert verify2.json()["valid"] is False
    assert verify2.json()["broken_at"] is not None
