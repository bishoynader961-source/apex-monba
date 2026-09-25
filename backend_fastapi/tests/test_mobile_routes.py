"""Tests for mobile-specific backend endpoints (§2.1–§2.3).

T60: sync lock acquire/release round-trip via /api/v1/pos/lock
T61: offline-ack marks SyncOutbox rows and returns purge count
T62: label render produces valid ESC/POS base64 with barcode
T63: sync lock deny when held by another nonce
"""
from __future__ import annotations

import base64

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SyncOutbox, Product
from app.shared.config import settings
from app.services.sync_lock_service import get_lock_service


@pytest.fixture
def multi_terminal():
    prev = settings.multi_terminal
    settings.multi_terminal = True
    yield
    settings.multi_terminal = False
    settings.multi_terminal = prev


@pytest.fixture
def _reset_lock_service():
    svc = get_lock_service()
    svc._locks.clear()
    yield
    svc._locks.clear()


async def _admin_auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    from app.core.models import Permission, Role, RolePermission, User
    from app.core.repositories import UserRepository
    from app.shared.security import hash_password

    role = Role(name="admin2", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    for key in ["pos.checkout", "inventory.read"]:
        session.add(Permission(feature_key=key, description=key))
    await session.commit()
    perms = (await session.execute(select(Permission))).scalars().all()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("admin2root", "Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin2root", "password": "password123"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_T60_sync_lock_acquire_release(
    client: AsyncClient, session: AsyncSession, multi_terminal, _reset_lock_service
) -> None:
    auth = await _admin_auth(client, session)
    payload = {"device_id": "DEV-1", "nonce": "n1", "action": "ACQUIRE", "ttl_seconds": 10}
    resp = await client.post("/api/v1/pos/lock", json=payload, headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["acquired"] is True
    assert body["current_holder"] == "DEV-1"
    assert body["expires_at"] is not None

    # Release
    resp2 = await client.post(
        "/api/v1/pos/lock",
        json={"device_id": "DEV-1", "nonce": "n1", "action": "RELEASE"},
        headers=auth,
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["acquired"] is False  # released → acquired=False


async def test_T63_sync_lock_deny_when_held(
    client: AsyncClient, session: AsyncSession, multi_terminal, _reset_lock_service
) -> None:
    auth = await _admin_auth(client, session)
    # Client A acquires
    await client.post(
        "/api/v1/pos/lock",
        json={"device_id": "DEV-A", "nonce": "na", "action": "ACQUIRE", "ttl_seconds": 30},
        headers=auth,
    )
    # Client B tries with a different nonce → denied
    resp = await client.post(
        "/api/v1/pos/lock",
        json={"device_id": "DEV-B", "nonce": "nb", "action": "ACQUIRE", "ttl_seconds": 30},
        headers=auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["acquired"] is False
    assert body["current_holder"] == "DEV-A"


async def test_T61_offline_ack_purges_outbox(
    client: AsyncClient, session: AsyncSession, multi_terminal
) -> None:
    auth = await _admin_auth(client, session)
    # Seed outbox rows for a device
    session.add(SyncOutbox(device_id="DEV-1", local_seq=1, client_txn_id="TXN-1", payload="{}", status="pending", created_at="2026-01-01T00:00:00"))
    session.add(SyncOutbox(device_id="DEV-1", local_seq=2, client_txn_id="TXN-2", payload="{}", status="merged", created_at="2026-01-01T00:00:01"))
    session.add(SyncOutbox(device_id="DEV-2", local_seq=1, client_txn_id="TXN-3", payload="{}", status="pending", created_at="2026-01-01T00:00:02"))
    await session.commit()

    resp = await client.post(
        "/api/v1/mobile/offline-ack",
        json={"device_id": "DEV-1", "ack_client_txn_ids": ["TXN-1", "TXN-2"]},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purged_count"] == 2

    rows = (await session.execute(select(SyncOutbox))).scalars().all()
    dev1 = [r for r in rows if r.device_id == "DEV-1"]
    assert all(r.status == "acked" for r in dev1)


async def test_T62_label_render_escp_pos(
    client: AsyncClient, session: AsyncSession, multi_terminal
) -> None:
    auth = await _admin_auth(client, session)
    # Seed a product
    session.add(Product(name="TestMed", price=12.50, manufacturer_barcode="123", internal_unique_barcode="456", status="In Stock", category="Test"))
    await session.commit()
    product_id = session.commit.__self__  # just use the last insert id
    # Re-fetch
    products = (await session.execute(select(Product).where(Product.name == "TestMed"))).scalars().all()
    pid = products[0].id

    resp = await client.post(
        "/api/v1/labels/render-mobile",
        json={"product_id": pid, "barcode_value": "0123456789"},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "ESCPOS_BASE64"
    raw = base64.b64decode(body["payload"])
    assert raw[0:1] == b"\x1b"  # ESC initialize
    assert b"\x1d" in raw  # GS for feed-and-cut
    assert body["byte_length"] > 0


async def test_T62b_label_render_fallback_only_barcode(
    client: AsyncClient, session: AsyncSession, multi_terminal, _reset_lock_service
) -> None:
    """No product_id or template_id → bare barcode label."""
    auth = await _admin_auth(client, session)
    resp = await client.post(
        "/api/v1/labels/render-mobile",
        json={"barcode_value": "9876543210"},
        headers=auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    raw = base64.b64decode(body["payload"])
    assert b"\x1d" in raw


async def test_T64_product_lookup_by_barcode(
    client: AsyncClient, session: AsyncSession, multi_terminal
) -> None:
    """GET /api/v1/inventory/by-barcode/{barcode} returns product (mobile scan support)."""
    auth = await _admin_auth(client, session)
    session.add(Product(name="BarcodeMed", price=9.99, manufacturer_barcode="MB123", internal_unique_barcode="SCAN-ABC-123", status="In Stock", category="Test"))
    await session.commit()

    resp = await client.get("/api/v1/inventory/by-barcode/SCAN-ABC-123", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "BarcodeMed"
    assert body["price"] == "9.99"

    # 404 on unknown barcode
    resp2 = await client.get("/api/v1/inventory/by-barcode/UNKNOWN-BARCODE", headers=auth)
    assert resp2.status_code == 404
