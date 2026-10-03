"""Batch 4 (audit M9): bounded inventory lists and report queries.

``low_stock`` / ``stock_levels`` return a keyset page ({items, next_cursor})
and the report range is capped at 366 days with the row cap pushed into SQL.
"""
from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Product, Role
from app.core.repositories import UserRepository
from app.shared.security import hash_password


async def _admin_headers(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    role = Role(name="owner-m9", description="owner", is_system=1)
    session.add(role)
    await session.commit()
    await UserRepository(session).create(
        "m9admin", "M9 Admin", hash_password("password123"), role.id
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "m9admin", "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _low_products(count: int, start: int = 0) -> list[Product]:
    return [
        Product(
            name=f"Low Medicine {start + i:04d}",
            price=Decimal("1.00"),
            internal_unique_barcode=f"INT-M9-{start + i:04d}",
            reorder_threshold=10,
            # No inventory rows -> coalesce(sum(on_hand), 0) = 0 <= threshold.
        )
        for i in range(count)
    ]


async def test_low_stock_returns_exactly_200_and_a_next_cursor(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _admin_headers(client, session)
    session.add_all(_low_products(500))
    await session.commit()

    resp = await client.get("/api/v1/inventory/batches/low-stock", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 200
    assert body["next_cursor"] is not None

    # Keyset page 2 continues after the cursor; 500 rows = 200 + 200 + 100.
    second = await client.get(
        f"/api/v1/inventory/batches/low-stock?cursor={body['next_cursor']}",
        headers=headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert len(second_body["items"]) == 200
    assert second_body["next_cursor"] is not None

    third = await client.get(
        f"/api/v1/inventory/batches/low-stock?cursor={second_body['next_cursor']}",
        headers=headers,
    )
    assert third.status_code == 200, third.text
    third_body = third.json()
    assert len(third_body["items"]) == 100
    assert third_body["next_cursor"] is None

    ids = [p["id"] for p in body["items"] + second_body["items"] + third_body["items"]]
    assert ids == sorted(ids) and len(set(ids)) == 500


async def test_low_stock_limit_is_capped_at_1000(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _admin_headers(client, session)
    resp = await client.get(
        "/api/v1/inventory/batches/low-stock?limit=1001", headers=headers
    )
    assert resp.status_code == 422


async def test_stock_levels_is_paginated(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _admin_headers(client, session)
    session.add_all(_low_products(250))
    await session.commit()

    resp = await client.get("/api/v1/inventory/stock-levels", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 200
    assert body["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/inventory/stock-levels?cursor={body['next_cursor']}", headers=headers
    )
    second_body = second.json()
    assert len(second_body["items"]) == 50
    assert second_body["next_cursor"] is None


async def test_sales_report_rejects_ranges_over_366_days(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _admin_headers(client, session)
    resp = await client.get(
        "/api/v1/pos/reports/sales?start_date=2025-01-01&end_date=2026-02-20",
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Date range must be 366 days or less" in resp.text
    assert "Export to Excel for longer ranges" in resp.text


async def test_sales_report_accepts_a_30_day_range(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _admin_headers(client, session)
    resp = await client.get(
        "/api/v1/pos/reports/sales?start_date=2026-01-01&end_date=2026-01-31",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["receipt_count"] == 0
    assert Decimal(body["gross_revenue"]) == Decimal("0")
