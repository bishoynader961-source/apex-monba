"""M4 — POS checkout: tax math, FIFO deduction, receipts, concurrency."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Product, Role, RolePermission
from app.core.repositories import BatchRepository, ProductRepository, UserRepository
from app.services.inventory_service import InventoryService
from app.shared.security import hash_password

_PERMS = ["inventory.read", "inventory.write", "inventory.reports", "pos.checkout", "users.write"]


async def _checkout_token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perms: list[Permission] = []
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms.append(p)
    await session.commit()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "adminroot", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _checkout_token(client, session)}"}


@pytest.fixture
async def catalogue(session: AsyncSession) -> dict[str, float]:
    session.add_all(
        [
            Product(name="Paracetamol", price=10.00, internal_unique_barcode="INT-A", vendor_name="Acme", expiry_date="2027-06-01"),
            Product(name="Ibuprofen", price=5.50, internal_unique_barcode="INT-B", vendor_name="Acme", expiry_date="2027-06-01"),
        ]
    )
    await session.commit()
    return {"Paracetamol": 10.00, "Ibuprofen": 5.50}


async def _receive(session: AsyncSession, name: str, qty: int, days: int) -> None:
    from app.services.inventory_service import InventoryService
    await InventoryService(session).receive_batch(
        name, "L-" + name, (date.today() + timedelta(days=days)).isoformat(), qty, 1.0, "Acme"
    )
    await session.commit()


async def test_checkout_success_and_tax(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], catalogue: dict[str, float]
) -> None:
    await _receive(session, "Paracetamol", 4, 30)
    await _receive(session, "Ibuprofen", 10, 90)

    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [
                {"product_name": "Paracetamol", "quantity": 3},
                {"product_name": "Ibuprofen", "quantity": 2},
            ],
            "payment_method": "Cash",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["receipt_number"].startswith(f"RCP-{date.today().year}-")
    # net = 3*10 + 2*5.5 = 41.00 ; tax = round(41*0.14)=5.74 ; total = 46.74
    # Money is serialised as a JSON string (integer-cents contract).
    assert body["net_total"] == "41.00"
    assert body["tax_total"] == "5.74"
    assert body["total_amount"] == "46.74"
    # FIFO consumed from the single Paracetamol lot -> 1 unit remains
    lot_total = await BatchRepository(session).sum_on_hand("Paracetamol")
    assert lot_total == 1

    # receipt + sold_items rows created
    receipts = await session.execute(text("SELECT COUNT(*) FROM receipts"))
    assert receipts.scalar() == 1
    sold = await session.execute(text("SELECT COUNT(*) FROM sold_items"))
    assert sold.scalar() == 2  # one per line


async def test_checkout_unknown_product_returns_404(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={"line_items": [{"product_name": "Nosuch Drug", "quantity": 1}], "payment_method": "Cash"},
        headers=auth,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_checkout_insufficient_stock_returns_400(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    session.add(Product(name="Paracetamol", price=10.00, internal_unique_barcode="INT-A", vendor_name="Acme", expiry_date="2027-06-01"))
    await session.commit()
    await _receive(session, "Paracetamol", 2, 30)
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={"line_items": [{"product_name": "Paracetamol", "quantity": 5}], "payment_method": "Cash"},
        headers=auth,
    )
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "over_sell"
    # stock untouched on failure
    lot_total = await BatchRepository(session).sum_on_hand("Paracetamol")
    assert lot_total == 2


async def test_concurrent_checkouts_serialize_on_single_sku(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    """20 concurrent checkouts of 1 SKU with only 5 units -> exactly 5 succeed, 15 fail."""
    session.add(Product(name="Paracetamol", price=10.00, internal_unique_barcode="INT-A", vendor_name="Acme", expiry_date="2027-06-01"))
    await session.commit()
    await InventoryService(session).receive_batch("Paracetamol", "LOT", "2027-06-01", 5, 1.0, "Acme")
    await session.commit()

    async def one_checkout() -> int:
        resp = await client.post(
            "/api/v1/pos/checkout",
            json={"line_items": [{"product_name": "Paracetamol", "quantity": 1}], "payment_method": "Cash"},
            headers=auth,
        )
        return resp.status_code

    status_codes = await asyncio.gather(*[one_checkout() for _ in range(20)])
    successes = sum(1 for c in status_codes if c == 201)
    failures = sum(1 for c in status_codes if c == 410)
    assert successes == 5
    assert failures == 15
    # final stock is zero
    lot_total = await BatchRepository(session).sum_on_hand("Paracetamol")
    assert lot_total == 0
    # total receipts written == number of successes
    receipts = await session.execute(text("SELECT COUNT(*) FROM receipts"))
    assert receipts.scalar() == 5
