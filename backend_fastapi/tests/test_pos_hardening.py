"""Phase 1 hardening tests: money integrity, 410 stock-state errors, drawer approval,
server-time/cashier attribution, migration idempotency, read-replica fallback."""
from __future__ import annotations

import os
import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, build_engine, init_engine, migrate_schema
from app.core.models import Permission, Product, Role, RolePermission
from app.core.repositories import SyncRepository, UserRepository
from app.services.auth_service import AuthService
from app.services.inventory_service import InventoryService
from app.shared import config as config_mod
from app.shared.security import PinPepper, create_approval_token, hash_password, set_pin_pepper


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
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "adminroot", "password": "password123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _seed_admin(client, session)}"}


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


async def test_money_serialised_as_string(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    await _add_product(session, "Paracetamol", 10.0)
    await InventoryService(session).receive_batch("Paracetamol", "L1", "2030-01-01", 4, Decimal("1.0"), "Acme")
    await session.commit()
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={"line_items": [{"product_name": "Paracetamol", "quantity": 2}]},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 2 * 10.00 = 20.00 ; tax = 2.80 ; total = 22.80 — always a JSON string.
    assert body["total_amount"] == "22.80"
    assert isinstance(body["total_amount"], str)


async def test_checkout_records_server_time_and_cashier(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    await _add_product(session, "Paracetamol", 10.0)
    await InventoryService(session).receive_batch("Paracetamol", "L1", "2030-01-01", 4, Decimal("1.0"), "Acme")
    await session.commit()
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 1}],
            "client_timestamp": "2020-01-01T00:00:00+00:00",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["server_created_at"]
    assert body["cashier_attribution"] == "adminroot"
    assert body["ts_skew_confidence"] is not None

    row = (
        await session.execute(text("SELECT server_created_at, cashier_attribution FROM receipts"))
    ).fetchone()
    assert row[0] and row[1] == "adminroot"


async def test_drawer_movement_requires_approval(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/pos/drawer/movement",
        json={"amount": "50.00", "reason": "cash-in", "cashier": "adminroot"},
        headers=auth,
    )
    assert resp.status_code == 403

    token = create_approval_token("adminroot", "drawer.move")
    resp2 = await client.post(
        "/api/v1/pos/drawer/movement",
        json={"amount": "50.00", "reason": "cash-in", "cashier": "adminroot"},
        headers={**auth, "X-Approval-Token": token},
    )
    assert resp2.status_code == 201, resp2.text
    body = resp2.json()
    assert body["amount"] == "50.00"
    assert body["prior_balance"] in ("0", "0.00")
    assert body["new_balance"] == "50.00"

    # Single-use: reuse must fail.
    resp3 = await client.post(
        "/api/v1/pos/drawer/movement",
        json={"amount": "10.00", "reason": "cash-in", "cashier": "adminroot"},
        headers={**auth, "X-Approval-Token": token},
    )
    assert resp3.status_code in (401, 403)


async def test_expired_lot_checkout_returns_410(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    await _add_product(session, "Paracetamol", 10.0)
    await InventoryService(session).receive_batch("Paracetamol", "L1", "2000-01-01", 5, Decimal("1.0"), "Acme")
    await session.commit()
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={"line_items": [{"product_name": "Paracetamol", "quantity": 1}]},
        headers=auth,
    )
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "expired_lot"


async def test_recalled_lot_checkout_returns_410(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    await _add_product(session, "Paracetamol", 10.0)
    await InventoryService(session).receive_batch("Paracetamol", "L1", "2030-01-01", 5, Decimal("1.0"), "Acme")
    await session.execute(
        text("UPDATE inventory_extended SET recalled = 1 WHERE lot_number = 'L1'")
    )
    await session.commit()
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={"line_items": [{"product_name": "Paracetamol", "quantity": 1}]},
        headers=auth,
    )
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "recalled_lot"


async def test_migration_idempotent(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)
        v1 = (await conn.exec_driver_sql("PRAGMA user_version")).fetchone()[0]
        await migrate_schema(conn)
        v2 = (await conn.exec_driver_sql("PRAGMA user_version")).fetchone()[0]
        tables = {
            r[0]
            for r in (await conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        }
    assert v1 == 3 and v2 == 3
    assert {"drawer_movements", "receipts", "sync_outbox", "discrepancies"} <= tables


def test_read_session_fallback_for_memory(monkeypatch) -> None:
    import app.core.database as database

    monkeypatch.setattr(config_mod.settings, "database_url", "sqlite+aiosqlite:///:memory:")
    init_engine("sqlite+aiosqlite:///:memory:")
    assert database._read_engine is None
    assert database._read_sessionmaker is database._sessionmaker


async def test_over_sell_discrepancy_is_surfaced(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    """A persisted sync discrepancy is surfaced via the discrepancies API (A4).

    Inserts a discrepancy directly (the over-sell path already records one via
    SyncService.push), then exercises the new list + resolve surface to prove the
    manager can see and close it.
    """
    repo = SyncRepository(session)
    await repo.insert_discrepancy(
        "OVER_SOLD_CROSS_TERMINAL", "dev-1", 1, "txn-abc", "over-sell recorded"
    )
    await session.commit()

    resp = await client.get("/api/v1/sync/discrepancies", headers=auth)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert any(d["client_txn_id"] == "txn-abc" and d["reason"] == "OVER_SOLD_CROSS_TERMINAL" for d in items)

    disc_id = next(d["id"] for d in items if d["client_txn_id"] == "txn-abc")

    resp2 = await client.post(f"/api/v1/sync/discrepancies/{disc_id}/resolve", headers=auth)
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["resolved"] == 1

    resp3 = await client.get("/api/v1/sync/discrepancies?unresolved_only=true", headers=auth)
    assert resp3.status_code == 200
    assert not any(d["client_txn_id"] == "txn-abc" for d in resp3.json())


async def test_manager_approval_issues_token_and_gates_drawer(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    """R2/R3: manager PIN -> single-use approval token -> drawer movement; reuse denied."""
    # Make the PIN pepper deterministic for the test (env backend).
    os.environ["PHARMACY_PEPPER_KEY"] = "test-pepper-secret-0123456789"
    set_pin_pepper(PinPepper(backend="env", env_key="PHARMACY_PEPPER_KEY", path="pepper_test.bin"))
    try:
        await AuthService(session).set_pin("adminroot", "1234")

        # Wrong PIN must not yield a token.
        bad = await client.post(
            "/api/v1/pos/approve",
            json={"username": "adminroot", "pin": "0000", "scope": "drawer.move"},
        )
        assert bad.status_code in (401, 403)

        # Correct PIN yields a single-use approval token.
        ok = await client.post(
            "/api/v1/pos/approve",
            json={"username": "adminroot", "pin": "1234", "scope": "drawer.move"},
        )
        assert ok.status_code == 200, ok.text
        token = ok.json()["approval_token"]
        assert token

        # Token gates the drawer movement.
        resp = await client.post(
            "/api/v1/pos/drawer/movement",
            json={"amount": "25.00", "reason": "cash-in", "cashier": "adminroot"},
            headers={**auth, "X-Approval-Token": token},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["amount"] == "25.00"

        # Single-use: reuse must be rejected.
        reuse = await client.post(
            "/api/v1/pos/drawer/movement",
            json={"amount": "1.00", "reason": "x", "cashier": "adminroot"},
            headers={**auth, "X-Approval-Token": token},
        )
        assert reuse.status_code in (401, 403)
    finally:
        set_pin_pepper(None)


async def test_sync_push_dedups_on_client_txn_id(
    client: AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    """R2: merge-sync hub accepts a sale once and dedups the same client_txn_id."""
    monkeypatch.setattr(config_mod.settings, "multi_terminal", True)
    entry = {
        "device_id": "test-device",
        "local_seq": 1,
        "client_txn_id": "r2-dedup-1",
        "payload": {"items": [{"product_name": "Paracetamol", "quantity": 1}]},
    }
    first = await client.post("/api/v1/sync/push", json={"entries": [entry]})
    assert first.status_code == 200, first.text
    assert first.json()["accepted"] == 1
    assert first.json()["deduped"] == 0

    second = await client.post("/api/v1/sync/push", json={"entries": [entry]})
    assert second.status_code == 200, second.text
    assert second.json()["deduped"] == 1
    assert second.json()["accepted"] == 0
