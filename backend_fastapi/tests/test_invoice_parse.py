"""Tests for invoice parse routes and smart parser."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import hash_password


_INVOICE_PERMS = ["inventory.read", "inventory.write"]


async def _invoice_token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.flush()
    perms: list[Permission] = []
    for key in _INVOICE_PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms.append(p)
    await session.flush()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.flush()
    await UserRepository(session).create("invadmin", "Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "invadmin", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth_headers(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _invoice_token(client, session)
    return {"Authorization": f"Bearer {token}"}


# ── Smart Parser Tests ──────────────────────────────────────────────────────

def test_parse_empty_text() -> None:
    from app.services.smart_parser import parse_invoice
    assert parse_invoice("") == []
    assert parse_invoice("   ") == []


def test_parse_single_item() -> None:
    from app.services.smart_parser import parse_invoice
    text = "1. Amoxicillin 500mg Capsules\n   Qty: 100 boxes\n   Batch: AMX-2026-X8\n   Expiry: 2028-12-01"
    items = parse_invoice(text)
    assert len(items) >= 1
    item = items[0]
    assert "Amoxicillin" in item["product_name"]
    assert item["quantity_received"] == 100
    assert item["batch_number"] == "AMX-2026-X8"
    assert item["expiration_date"] == "2028-12-01"


def test_parse_multi_item() -> None:
    from app.services.smart_parser import parse_invoice
    text = (
        "1. Amoxicillin 500mg\n   Qty: 50\n   Batch: AMX-01\n   Exp: 2028-06-01\n\n"
        "2. Paracetamol 250mg\n   Qty: 200\n   Batch: PCM-02\n   Exp: 2029-01-15"
    )
    items = parse_invoice(text)
    assert len(items) == 2
    assert items[0]["batch_number"] == "AMX-01"
    assert items[1]["batch_number"] == "PCM-02"


# ── API Route Tests ─────────────────────────────────────────────────────────

async def test_text_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/invoice-parse/text", json={"text": "test"})
    assert resp.status_code == 401


async def test_parse_text_endpoint(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    text = "1. Ibuprofen 200mg\n   Qty: 75\n   Batch: IBU-100\n   Exp: 2027-03-15"
    resp = await client.post(
        "/api/v1/invoice-parse/text",
        json={"text": text},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "count" in data
    assert data["count"] >= 1


async def test_hardware_status_endpoint(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get(
        "/api/v1/invoice-parse/hardware-status",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "gpu_available" in data
    assert "ram_total_gb" in data
    assert "tier" in data
    assert "recommended_mode" in data
    assert "warnings" in data
