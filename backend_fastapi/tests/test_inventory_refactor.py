"""Inventory refactor: soft-delete, stock levels, batch CRUD, RBAC, concurrency.

Mirrors the auth/seed pattern from tests/test_inventory.py and tests/test_pos.py so
it runs against the shared in-memory fixtures in conftest.py (fresh DB per test).
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Product, Role, RolePermission
from app.core.repositories import BatchRepository, ProductRepository, UserRepository
from app.services.inventory_service import InventoryService
from app.shared.schemas import MedicineRead, MedicineUpdate
from app.shared.security import hash_password

_ADMIN_PERMS = ["inventory.read", "inventory.write", "inventory.reports", "pos.checkout", "users.write"]
_READ_ONLY_PERMS = ["inventory.read"]


async def _token(
    client: AsyncClient,
    session: AsyncSession,
    perms: list[str],
    username: str,
    password: str = "password123",
) -> str:
    role = Role(name=f"role_{username}", description=username, is_system=1)
    session.add(role)
    await session.commit()
    pobjs: list[Permission] = []
    for key in perms:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        pobjs.append(p)
    await session.commit()
    for p in pobjs:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create(username, username, hash_password(password), role.id)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def admin(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session, _ADMIN_PERMS, 'adminroot')}"}


@pytest.fixture
async def reader(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session, _READ_ONLY_PERMS, 'reader')}"}


async def _add_product(session: AsyncSession, name: str, price: float = 10.0, **kw) -> Product:
    p = Product(name=name, price=price, internal_unique_barcode=f"INT-{name}", **kw)
    session.add(p)
    await session.commit()
    return p


async def _receive(session: AsyncSession, name: str, qty: int, days: int, price: float = 10.0) -> None:
    await _add_product(session, name, price=price)
    await InventoryService(session).receive_batch(
        name, "L-" + name, (date.today() + timedelta(days=days)).isoformat(), qty, 1.0, "Acme"
    )
    await session.commit()


# ── Stock levels (T1, T2) ────────────────────────────────────────────────────────

async def test_stock_levels_shows_aggregate_and_expiring(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    await _receive(session, "Aspirin", 10, 30, price=5.0)  # product + lot qty10 (expires day30, within window)
    # second lot for the SAME product (qty20, expires day400 -> outside 90-day window)
    await InventoryService(session).receive_batch(
        "Aspirin", "L2-Aspirin", (date.today() + timedelta(days=400)).isoformat(), 20, 1.0, "Acme"
    )
    await session.commit()

    await _receive(session, "Ibuprofen", 5, 10, price=1.0)
    ibu = await ProductRepository(session).get_by_name("Ibuprofen")
    ibu.reorder_threshold = 20
    asp = await ProductRepository(session).get_by_name("Aspirin")
    asp.reorder_threshold = 10
    await session.commit()

    resp = await client.get("/api/v1/inventory/stock-levels", headers=admin)
    assert resp.status_code == 200, resp.text
    levels = resp.json()
    by_name = {l["name"]: l for l in levels}
    asp_lvl = by_name["Aspirin"]
    ibu_lvl = by_name["Ibuprofen"]
    assert asp_lvl["total_on_hand"] == 30
    assert asp_lvl["is_low_stock"] is False
    assert asp_lvl["expiring_soon_count"] == 1
    assert asp_lvl["reorder_threshold"] == 10
    assert ibu_lvl["total_on_hand"] == 5
    assert ibu_lvl["is_low_stock"] is True
    assert ibu_lvl["expiring_soon_count"] == 1


async def test_stock_levels_low_stock_filter(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    await _receive(session, "Aspirin", 30, 30, price=5.0)
    asp = await ProductRepository(session).get_by_name("Aspirin")
    asp.reorder_threshold = 10
    await _receive(session, "Ibuprofen", 5, 10, price=1.0)
    ibu = await ProductRepository(session).get_by_name("Ibuprofen")
    ibu.reorder_threshold = 20
    await session.commit()

    resp = await client.get("/api/v1/inventory/stock-levels", params={"low_stock_only": "true"}, headers=admin)
    assert resp.status_code == 200
    names = [l["name"] for l in resp.json()]
    assert names == ["Ibuprofen"]


# ── Soft delete (T3, T4) ────────────────────────────────────────────────────────

async def test_medicine_soft_delete_hidden(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    await _add_product(session, "Paracetamol")
    pid = (await ProductRepository(session).get_by_name("Paracetamol")).id
    assert (await client.delete(f"/api/v1/inventory/medicines/{pid}", headers=admin)).status_code == 200
    # 404 at the read endpoint
    assert (await client.get(f"/api/v1/inventory/medicines/{pid}", headers=admin)).status_code == 404
    # hidden from list + search
    listed = [p["name"] for p in (await client.get("/api/v1/inventory/medicines", headers=admin)).json()["items"]]
    assert "Paracetamol" not in listed
    searched = [p["name"] for p in (await client.get("/api/v1/inventory/medicines/search", params={"q": "Par"}, headers=admin)).json()]
    assert searched == []
    # hidden from stock levels
    assert all(p["name"] != "Paracetamol" for p in (await client.get("/api/v1/inventory/stock-levels", headers=admin)).json())


async def test_soft_deleted_still_resolvable_by_name(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    """R2 invariant: POS receive resolves products by name regardless of soft-delete."""
    await _add_product(session, "Aspirin", price=5.0)
    pid = (await ProductRepository(session).get_by_name("Aspirin")).id
    await client.delete(f"/api/v1/inventory/medicines/{pid}", headers=admin)
    # receive still succeeds (uses unfiltered get_by_name)
    resp = await client.post(
        "/api/v1/inventory/batches/receive",
        json={"product_name": "Aspirin", "lot_number": "L1", "expiry_date": "2027-06-01", "quantity": 12, "unit_cost": 1.0, "supplier": "Acme"},
        headers=admin,
    )
    assert resp.status_code == 201, resp.text


# ── Medicine mutations (T5, T6, T7, drift) ──────────────────────────────────────

async def test_medicine_update_rejects_unknown(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    resp = await client.put(
        "/api/v1/inventory/medicines/99999",
        json=MedicineUpdate(name="Nope").model_dump(exclude_unset=True),
        headers=admin,
    )
    assert resp.status_code == 404


async def test_medicine_partial_update(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    await _add_product(session, "Aspirin", price=5.0)
    pid = (await ProductRepository(session).get_by_name("Aspirin")).id
    resp = await client.put(
        f"/api/v1/inventory/medicines/{pid}",
        json={"price": 9.99},
        headers=admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] == "9.99"
    assert body["name"] == "Aspirin"


async def test_medicine_update_rename_cascades_to_lots(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    await _add_product(session, "Aspirin", price=5.0)
    pid = (await ProductRepository(session).get_by_name("Aspirin")).id
    await client.post(
        "/api/v1/inventory/batches/receive",
        json={"product_name": "Aspirin", "lot_number": "L1", "expiry_date": "2027-06-01", "quantity": 8, "unit_cost": 1.0, "supplier": "Acme"},
        headers=admin,
    )
    resp = await client.put(
        f"/api/v1/inventory/medicines/{pid}", json={"name": "Aspirin Coated"}, headers=admin
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Aspirin Coated"
    lots_renamed = (await client.get("/api/v1/inventory/batches", params={"product_name": "Aspirin Coated"}, headers=admin)).json()
    assert len(lots_renamed) == 1 and lots_renamed[0]["drug_name"] == "Aspirin Coated"
    lots_old = (await client.get("/api/v1/inventory/batches", params={"product_name": "Aspirin"}, headers=admin)).json()
    assert lots_old == []  # old name no longer joined


def test_medicine_update_parity_with_read() -> None:
    """T-drift: MedicineUpdate must mirror MedicineRead's updatable fields."""
    read_fields = set(MedicineRead.model_fields) - {"id", "is_deleted"}
    update_fields = set(MedicineUpdate.model_fields)
    assert read_fields == update_fields
    assert MedicineRead.model_fields["is_deleted"].default is False
    assert all(not f.is_required() for f in MedicineUpdate.model_fields.values())


# ── Batch CRUD (GET/PUT) ─────────────────────────────────────────────────────────

async def test_batch_get_and_adjust(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    await _add_product(session, "Paracetamol")
    lot = await client.post(
        "/api/v1/inventory/batches/receive",
        json={"product_name": "Paracetamol", "lot_number": "L1", "expiry_date": "2027-06-01", "quantity": 10, "unit_cost": 1.0, "supplier": "Acme"},
        headers=admin,
    )
    bid = lot.json()["id"]

    got = await client.get(f"/api/v1/inventory/batches/{bid}", headers=admin)
    assert got.status_code == 200 and got.json()["on_hand"] == 10

    adj = await client.put(f"/api/v1/inventory/batches/{bid}", json={"on_hand": 3}, headers=admin)
    assert adj.status_code == 200 and adj.json()["on_hand"] == 3

    neg = await client.put(f"/api/v1/inventory/batches/{bid}", json={"on_hand": -1}, headers=admin)
    assert neg.status_code == 400 and neg.json()["error"]["code"] == "validation_error"


async def test_get_batch_404(client: AsyncClient, admin: dict[str, str]) -> None:
    resp = await client.get("/api/v1/inventory/batches/99999", headers=admin)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"


# ── Filtering ───────────────────────────────────────────────────────────────────

async def test_medicine_filter_by_vendor(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    await _add_product(session, "Aspirin", vendor_name="Bayer")
    await _add_product(session, "Ibuprofen", vendor_name="Sandoz")
    resp = await client.get("/api/v1/inventory/medicines", params={"vendor": "Bayer"}, headers=admin)
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["items"]]
    assert names == ["Aspirin"]


# ── RBAC (read-only cannot write) ────────────────────────────────────────────────

async def test_add_medicine_requires_write(client: AsyncClient, reader: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/inventory/medicines",
        json={"name": "NewDrug", "price": 1.0, "internal_unique_barcode": "X"},
        headers=reader,
    )
    assert resp.status_code == 403


async def test_update_medicine_requires_write(client: AsyncClient, session: AsyncSession, reader: dict[str, str]) -> None:
    await _add_product(session, "Aspirin")
    pid = (await ProductRepository(session).get_by_name("Aspirin")).id
    resp = await client.put(f"/api/v1/inventory/medicines/{pid}", json={"price": 9.99}, headers=reader)
    assert resp.status_code == 403


async def test_delete_medicine_requires_write(client: AsyncClient, session: AsyncSession, reader: dict[str, str]) -> None:
    await _add_product(session, "Aspirin")
    pid = (await ProductRepository(session).get_by_name("Aspirin")).id
    resp = await client.delete(f"/api/v1/inventory/medicines/{pid}", headers=reader)
    assert resp.status_code == 403


async def test_adjust_batch_requires_write(client: AsyncClient, session: AsyncSession, reader: dict[str, str]) -> None:
    await _add_product(session, "Paracetamol")
    tmp_headers = {"Authorization": f"Bearer {await _token(client, session, _ADMIN_PERMS, 'tmpadmin')}"}
    lot = (
        await client.post(
            "/api/v1/inventory/batches/receive",
            json={"product_name": "Paracetamol", "lot_number": "L1", "expiry_date": "2027-06-01", "quantity": 10, "unit_cost": 1.0, "supplier": "Acme"},
            headers=tmp_headers,
        )
    ).json()
    bid = lot["id"]
    resp = await client.put(f"/api/v1/inventory/batches/{bid}", json={"on_hand": 1}, headers=reader)
    assert resp.status_code == 403


# ── Concurrency (lock_manager shared registry) ───────────────────────────────────

async def test_concurrent_checkouts_serialize_on_single_sku(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    """20 concurrent checkouts of 1 unit each on a 5-unit lot -> exactly 5 succeed."""
    await _add_product(session, "Paracetamol", price=10.0)
    await InventoryService(session).receive_batch("Paracetamol", "LOT", "2027-06-01", 5, 1.0, "Acme")
    await session.commit()

    async def one() -> int:
        resp = await client.post(
            "/api/v1/pos/checkout",
            json={"line_items": [{"product_name": "Paracetamol", "quantity": 1}], "payment_method": "Cash"},
            headers=admin,
        )
        return resp.status_code

    codes = await asyncio.gather(*[one() for _ in range(20)])
    assert sum(1 for c in codes if c == 201) == 5
    assert sum(1 for c in codes if c == 410) == 15
    assert await BatchRepository(session).sum_on_hand("Paracetamol") == 0
