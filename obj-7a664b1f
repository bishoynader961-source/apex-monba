"""Tests for the Global Receiving Log endpoint (GET /api/v1/receiving-log)."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, ReceivingLog, Role, RolePermission


_PERMS = [
    "inventory.read",
    "inventory.write",
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
    from app.core.repositories import UserRepository
    from app.shared.security import hash_password
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "adminroot", "password": "password123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _seed_receiving_logs(session: AsyncSession) -> None:
    rows = [
        {
            "vendor_name": "Acme Pharma",
            "product_name": "Aspirin 500mg",
            "date_received": date.today().isoformat(),
            "quantity": 100,
            "total_cost": 250.00,
            "barcode": "ACME-001",
            "lot_number": "LT-001",
        },
        {
            "vendor_name": "Acme Pharma",
            "product_name": "Ibuprofen 200mg",
            "date_received": date.today().isoformat(),
            "quantity": 50,
            "total_cost": 150.00,
            "barcode": "ACME-002",
            "lot_number": "LT-002",
        },
        {
            "vendor_name": "Beta Supplies",
            "product_name": "Band-Aids (40ct)",
            "date_received": date.today().isoformat(),
            "quantity": 30,
            "total_cost": 45.00,
            "barcode": "BETA-001",
            "lot_number": "LT-003",
        },
    ]
    await session.execute(insert(ReceivingLog).values(rows))
    await session.commit()


@pytest.mark.asyncio
async def test_list_receiving_log(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _seed_admin(client, session)
    await _seed_receiving_logs(session)

    resp = await client.get(
        "/api/v1/receiving-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    vendors_returned = {item["vendor_name"] for item in body["items"]}
    assert vendors_returned == {"Acme Pharma", "Beta Supplies"}
    assert {item["product_name"] for item in body["items"]} == {"Aspirin 500mg", "Ibuprofen 200mg", "Band-Aids (40ct)"}


@pytest.mark.asyncio
async def test_list_receiving_log_date_filter(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _seed_admin(client, session)
    await _seed_receiving_logs(session)

    today = date.today().isoformat()
    resp = await client.get(
        "/api/v1/receiving-log",
        params={"date": today},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3

    resp2 = await client.get(
        "/api/v1/receiving-log",
        params={"date": "2000-01-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_receiving_log_vendor_filter(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _seed_admin(client, session)
    await _seed_receiving_logs(session)

    resp = await client.get(
        "/api/v1/receiving-log",
        params={"vendor": "Acme"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(item["vendor_name"] == "Acme Pharma" for item in body["items"])


@pytest.mark.asyncio
async def test_list_receiving_log_pagination(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _seed_admin(client, session)
    await _seed_receiving_logs(session)

    resp = await client.get(
        "/api/v1/receiving-log",
        params={"page": 1, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


@pytest.mark.asyncio
async def test_list_receiving_log_vendors(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _seed_admin(client, session)
    await _seed_receiving_logs(session)

    resp = await client.get(
        "/api/v1/receiving-log/vendors",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    vendors = resp.json()
    assert "Acme Pharma" in vendors
    assert "Beta Supplies" in vendors


@pytest.mark.asyncio
async def test_receiving_log_requires_auth(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_receiving_logs(session)

    resp = await client.get("/api/v1/receiving-log")
    assert resp.status_code == 401
