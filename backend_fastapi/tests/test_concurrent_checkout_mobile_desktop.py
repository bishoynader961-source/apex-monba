"""Sprint 2E: multi-client checkout concurrency (audit D8 criterion:
"Concurrent checkout: SQLite WAL handles, but test with 2 mobile + 1 desktop").

Two simultaneous checkouts of the SAME product's LAST unit — exactly one must
succeed (201); the loser must get an explicit 400-family stock error, never a
5xx and never a double-sell."""
from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Product, Role, RolePermission
from app.core.repositories import BatchRepository, UserRepository
from app.services.inventory_service import InventoryService
from app.shared.security import hash_password


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    role = Role(name="raceadmin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perm = Permission(feature_key="pos.checkout", description="pos.checkout")
    session.add(perm)
    await session.commit()
    session.add(RolePermission(role_id=role.id, permission_id=perm.id, granted=1))
    await session.commit()
    await UserRepository(session).create("raceadmin", "Race Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "raceadmin", "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_two_clients_race_for_last_unit(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    # One product, one batch, exactly 1 unit on hand.
    session.add(Product(name="RaceMed", price=10.00, internal_unique_barcode="INT-RACE", vendor_name="Acme", expiry_date="2027-06-01"))
    await session.commit()
    await InventoryService(session).receive_batch("RaceMed", "LOT-1", "2027-06-01", 1, 1.0, "Acme")
    await session.commit()

    async def checkout(device: str) -> int:
        resp = await client.post(
            "/api/v1/pos/checkout",
            json={"line_items": [{"product_name": "RaceMed", "quantity": 1}], "payment_method": "Cash"},
            headers={**auth, "X-Device-Name": device},
        )
        return resp.status_code

    desktop, mobile = await asyncio.gather(checkout("desktop"), checkout("mobile"))

    statuses = sorted([desktop, mobile])
    # Exactly one winner; the loser gets an explicit stock-state 4xx (410
    # over_sell or 400), never 5xx and never a second 201.
    assert statuses[0] == 201, f"expected exactly one success, got {statuses}"
    assert statuses[1] in (400, 409, 410), f"loser must get an explicit stock error, got {statuses}"

    # And the stock ledger agrees: 0 units left, exactly 1 receipt.
    assert await BatchRepository(session).sum_on_hand("RaceMed") == 0
    from sqlalchemy import text

    receipts = (await session.execute(text("SELECT COUNT(*) FROM receipts"))).scalar()
    assert receipts == 1
