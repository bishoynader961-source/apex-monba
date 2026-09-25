"""Tests for auto-reorder: low-stock grouping and PO draft creation."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    InventoryExtended,
    Permission,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Role,
    RolePermission,
)
from app.core.repositories import UserRepository
from app.services.po_service import PurchaseOrderService
from app.shared.security import hash_password


_PO_PERMS = ["inventory.read", "inventory.write"]


async def _po_token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.flush()
    perms: list[Permission] = []
    for key in _PO_PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms.append(p)
    await session.flush()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.flush()
    await UserRepository(session).create("poadmin", "Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "poadmin", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth_headers(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _po_token(client, session)
    return {"Authorization": f"Bearer {token}"}


# ── Service: compute_low_stock_groups ───────────────────────────────────────

async def test_compute_low_stock_groups_empty(session: AsyncSession) -> None:
    svc = PurchaseOrderService(session)
    groups = await svc.compute_low_stock_groups()
    assert groups == []


async def test_compute_low_stock_groups_with_low_stock(session: AsyncSession) -> None:
    # Insert product with reorder_threshold
    product = Product(
        name="Amoxicillin 500mg",
        price=10.0,
        vendor_name="Acme Pharma",
        wholesale_price=5.0,
        reorder_threshold=50,
    )
    session.add(product)
    await session.flush()

    # Insert inventory_extended row with on_hand below threshold
    inv = InventoryExtended(
        drug_name="Amoxicillin 500mg",
        on_hand=20,
        ndc_code="12345-6789",
    )
    session.add(inv)
    await session.flush()

    svc = PurchaseOrderService(session)
    groups = await svc.compute_low_stock_groups()
    assert len(groups) == 1
    assert groups[0]["vendor_name"] == "Acme Pharma"
    assert len(groups[0]["items"]) == 1
    item = groups[0]["items"][0]
    assert item["name"] == "Amoxicillin 500mg"
    assert item["current_qty"] == 20
    assert item["threshold"] == 50
    assert item["suggested_qty"] == 100  # 50 + max(50, 1)


async def test_compute_low_stock_groups_ignores_above_threshold(session: AsyncSession) -> None:
    product = Product(
        name="Paracetamol",
        price=5.0,
        vendor_name="GenericCo",
        reorder_threshold=10,
    )
    session.add(product)
    await session.flush()

    inv = InventoryExtended(drug_name="Paracetamol", on_hand=50, ndc_code="99999-0000")
    session.add(inv)
    await session.flush()

    svc = PurchaseOrderService(session)
    groups = await svc.compute_low_stock_groups()
    assert groups == []


# ── Service: auto_reorder ──────────────────────────────────────────────────

async def test_auto_reorder_creates_drafts(session: AsyncSession) -> None:
    product = Product(
        name="Ibuprofen 200mg",
        price=8.0,
        vendor_name="PainCo",
        wholesale_price=3.0,
        reorder_threshold=30,
    )
    session.add(product)
    await session.flush()

    inv = InventoryExtended(drug_name="Ibuprofen 200mg", on_hand=10, ndc_code="11111-1111")
    session.add(inv)
    await session.flush()

    svc = PurchaseOrderService(session)
    result = await svc.auto_reorder(username="test_user")

    assert result["po_count"] == 1
    assert result["item_count"] == 1
    assert result["low_stock_count"] == 1
    assert len(result["drafts"]) == 1
    assert result["drafts"][0]["po_number"].startswith("PO-")

    # Verify PO was created in DB
    po = await session.get(PurchaseOrder, result["drafts"][0]["po_id"])
    assert po is not None
    assert po.status == "Draft"
    assert po.vendor_name == "PainCo"
    assert po.created_by == "test_user"


async def test_auto_reorder_no_low_stock(session: AsyncSession) -> None:
    svc = PurchaseOrderService(session)
    result = await svc.auto_reorder()
    assert result["po_count"] == 0
    assert result["item_count"] == 0
    assert result["drafts"] == []


async def test_auto_reorder_groups_by_vendor(session: AsyncSession) -> None:
    # Two products from same vendor
    p1 = Product(name="Drug A", price=10.0, vendor_name="SameVendor", wholesale_price=5.0, reorder_threshold=20)
    p2 = Product(name="Drug B", price=20.0, vendor_name="SameVendor", wholesale_price=8.0, reorder_threshold=15)
    session.add_all([p1, p2])
    await session.flush()

    inv1 = InventoryExtended(drug_name="Drug A", on_hand=5, ndc_code="00001-0001")
    inv2 = InventoryExtended(drug_name="Drug B", on_hand=3, ndc_code="00002-0002")
    session.add_all([inv1, inv2])
    await session.flush()

    svc = PurchaseOrderService(session)
    result = await svc.auto_reorder()

    # Should create 1 PO with 2 items (same vendor grouped)
    assert result["po_count"] == 1
    assert result["item_count"] == 2


# ── API Route: auto-reorder ────────────────────────────────────────────────

async def test_auto_reorder_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/purchase-orders/auto-reorder")
    assert resp.status_code == 401


async def test_auto_reorder_endpoint(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/purchase-orders/auto-reorder",
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "po_count" in data
    assert "item_count" in data
    assert "low_stock_count" in data
    assert "drafts" in data
