"""M3 inventory: receive, orphan-lot rejection, FIFO, alerts, CRUD."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.models import (
    InventoryExtended,
    Permission,
    Product,
    Role,
    RolePermission,
)
from app.core.database import Base
from app.core.repositories import BatchRepository, ProductRepository, UserRepository
from app.services.inventory_service import InventoryService
from app.shared.exceptions import OverSellError
from app.shared.security import hash_password
from scripts.normalize_inventory import normalize

_INVENTORY_PERMS = ["inventory.read", "inventory.write", "inventory.reports", "users.write"]


async def _inventory_token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perms: list[Permission] = []
    for key in _INVENTORY_PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms.append(p)
    await session.commit()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "adminroot", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth_headers(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _inventory_token(client, session)
    return {"Authorization": f"Bearer {token}"}


# ── Receive ────────────────────────────────────────────────────────────────────

async def test_receive_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/inventory/batches/receive", json={})
    assert resp.status_code == 401


async def test_receive_creates_batch(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    session.add(Product(name="Paracetamol", price=10.0, internal_unique_barcode="INT-001"))
    await session.commit()
    resp = await client.post(
        "/api/v1/inventory/batches/receive",
        json={
            "product_name": "Paracetamol",
            "lot_number": "LOT-A1",
            "expiry_date": "2026-12-31",
            "quantity": 50,
            "unit_cost": 0.5,
            "supplier": "Acme Pharma",
            "ndc_code": "12345-6789",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["lot_number"] == "LOT-A1"
    assert body["on_hand"] == 50

    # receiving_log entry committed too
    log = await session.execute(text("SELECT COUNT(*) FROM receiving_log"))
    assert log.scalar() == 1


async def test_receive_rejects_orphan_lot(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/inventory/batches/receive",
        json={
            "product_name": "Unknown Drug",
            "lot_number": "ORPHAN-1",
            "expiry_date": "2026-12-31",
            "quantity": 10,
            "unit_cost": 1.0,
            "supplier": "Acme Pharma",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


# ── Medicine CRUD ──────────────────────────────────────────────────────────────

async def test_medicine_crud(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    payload = {
        "name": "Aspirin",
        "price": 5.0,
        "manufacturer_barcode": "MB-AS",
        "internal_unique_barcode": "INT-AS",
        "status": "In Stock",
        "expiry_date": "2026-12-31",
        "manufacture_date": "2024-01-01",
        "vendor_name": "Bayer",
        "dea_schedule": None,
        "wholesale_price": 1.0,
        "reorder_threshold": 10,
    }
    resp = await client.post("/api/v1/inventory/medicines", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    med_id = resp.json()["id"]

    got = await client.get(f"/api/v1/inventory/medicines/{med_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["name"] == "Aspirin"

    # duplicate -> 409
    dup = await client.post("/api/v1/inventory/medicines", json=payload, headers=auth_headers)
    assert dup.status_code == 409

    # update
    payload["price"] = 6.0
    upd = await client.put(f"/api/v1/inventory/medicines/{med_id}", json=payload, headers=auth_headers)
    assert upd.status_code == 200
    assert upd.json()["price"] == "6.00"

    # missing -> 404
    missing = await client.get("/api/v1/inventory/medicines/99999", headers=auth_headers)
    assert missing.status_code == 404


# ── Alerts ─────────────────────────────────────────────────────────────────────

async def test_low_stock_alert(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    # at-threshold product (should alert)
    session.add(Product(name="Amoxicillin", price=2.0, internal_unique_barcode="INT-AM", reorder_threshold=10))
    # above-threshold product (should NOT alert)
    session.add(Product(name="Ibuprofen", price=1.0, internal_unique_barcode="INT-IB", reorder_threshold=10))
    await session.commit()

    amoxicillin = await ProductRepository(session).get_by_name("Amoxicillin")
    ibuprofen = await ProductRepository(session).get_by_name("Ibuprofen")
    assert amoxicillin is not None and ibuprofen is not None
    session.add(InventoryExtended(drug_name="Amoxicillin", lot_number="L1", expiration_date="2027-06-01", on_hand=5, supplier="Acme"))
    session.add(InventoryExtended(drug_name="Ibuprofen", lot_number="L2", expiration_date="2027-06-01", on_hand=20, supplier="Acme"))
    await session.commit()

    resp = await client.get("/api/v1/inventory/batches/low-stock", headers=auth_headers)
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "Amoxicillin" in names
    assert "Ibuprofen" not in names


async def test_expiring_soon_alert(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    soon = (date.today() + timedelta(days=30)).isoformat()
    far = (date.today() + timedelta(days=400)).isoformat()
    session.add(InventoryExtended(drug_name="D", lot_number="S", expiration_date=str(soon), on_hand=10, supplier="Acme"))
    session.add(InventoryExtended(drug_name="D", lot_number="F", expiration_date=str(far), on_hand=10, supplier="Acme"))
    await session.commit()
    resp = await client.get("/api/v1/inventory/batches/expiring-soon?days=90", headers=auth_headers)
    assert resp.status_code == 200
    lots = resp.json()
    assert any(l["lot_number"] == "S" for l in lots)
    assert not any(l["lot_number"] == "F" for l in lots)


# ── FIFO (unit-level, via service) ─────────────────────────────────────────────

async def test_fifo_deduct_consumes_oldest_first(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    session.add(Product(name="Paracetamol", price=10.0, internal_unique_barcode="INT-FIFO"))
    await session.commit()
    service = InventoryService(session)
    # two non-overlapping expiry dates (oldest first)
    older = (date.today() + timedelta(days=10)).isoformat()
    newer = (date.today() + timedelta(days=400)).isoformat()
    batch = await service.receive_batch("Paracetamol", "L-OLD", older, 3, 0.5, "Acme")
    await service.receive_batch("Paracetamol", "L-NEW", newer, 4, 0.5, "Acme")
    await session.commit()

    consumed = await service.fifo_deduct("Paracetamol", 5)
    await session.commit()
    assert sum(c["deducted"] for c in consumed) == 5
    # oldest lot exhausted, newer partially consumed
    lots = {l.lot_number: l.on_hand for l in await BatchRepository(session).get_lots_for_product("Paracetamol")}
    assert lots["L-OLD"] == 0
    assert lots["L-NEW"] == 2


async def test_fifo_deduct_insufficient(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    session.add(Product(name="Paracetamol", price=10.0, internal_unique_barcode="INT-FIFO2"))
    await session.commit()
    service = InventoryService(session)
    exp = (date.today() + timedelta(days=10)).isoformat()
    await service.receive_batch("Paracetamol", "L1", exp, 3, 0.5, "Acme")
    await session.commit()
    with pytest.raises(OverSellError):
        await service.fifo_deduct("Paracetamol", 10)


# ── Normalization script ───────────────────────────────────────────────────────

def _build_script_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "script_test.db")
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Product(name="Paracetamol", price=10.0, internal_unique_barcode="INT", reorder_threshold=5))
        # case-variant of a known product -> fix candidate
        s.add(InventoryExtended(drug_name="paracetamol", lot_number="L-CASE", expiration_date="2027-06-01", on_hand=10, supplier="Acme"))
        # orphan lot -> no resolvable product
        s.add(InventoryExtended(drug_name="Unknown Drug", lot_number="L-ORPHAN", expiration_date="2027-06-01", on_hand=4, supplier="Acme"))
        s.commit()
    return db_path


def test_normalize_dry_run_reports_fix(tmp_path: Path) -> None:
    db_path = _build_script_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        changes = normalize(conn, apply=False)
    finally:
        conn.close()
    assert changes == 1
    # dry-run should not mutate
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT drug_name FROM inventory_extended WHERE lot_number='L-CASE'").fetchone()
    assert row[0] == "paracetamol"


def test_normalize_apply_fixes_case(tmp_path: Path) -> None:
    db_path = _build_script_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        normalize(conn, apply=True)
    finally:
        conn.close()
    conn = sqlite3.connect(db_path)
    fixed = conn.execute("SELECT drug_name FROM inventory_extended WHERE lot_number='L-CASE'").fetchone()
    orphan = conn.execute("SELECT drug_name FROM inventory_extended WHERE lot_number='L-ORPHAN'").fetchone()
    assert fixed[0] == "Paracetamol"
    assert orphan[0] == "Unknown Drug"  # untouched
