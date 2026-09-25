"""Checkout contract tests for the restored privileged fields.

Covers the CheckoutRequest fields that were previously missing from the schema
(tax_exempt / price_overrides / payments / discount_type / discount_value):
  * pos.price_override permission denial + admin (role_id 1) bypass
  * price override applied to line pricing
  * tax exemption zeroes the tax leg
  * percentage and flat-dollar discounts (applied before tax, clamped at net)
  * split payments (multi-tender) recording + under-sum rejection

Tax rate is 0.14 (settings.tax_rate), money is serialised as 2-dp strings and
rounded ROUND_HALF_UP — same contract as test_pos.py.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Product, Role, RolePermission
from app.core.repositories import UserRepository
from app.services.inventory_service import InventoryService
from app.shared.security import create_access_token, hash_password

_TAX_RATE = "0.14"


async def _user_headers(
    session: AsyncSession,
    username: str,
    role_name: str,
    permissions: list[str],
    *,
    as_owner: bool = False,
) -> dict[str, str]:
    """Create a role + user + permission rows and return bearer auth headers.

    Role id 1 is the hardcoded owner bypass in deps.require_permission and
    PosService._has, so ``as_owner`` claims the first-created role; permission
    tests create a placeholder Administrator row first to push the test role
    to id >= 2.
    """
    if not as_owner:
        session.add(Role(name="Administrator", description="owner", is_system=1))
        await session.commit()
    role = Role(name=role_name, description=role_name, is_system=1 if as_owner else 0)
    session.add(role)
    await session.commit()
    for key in permissions:
        perm = Permission(feature_key=key, description=key)
        session.add(perm)
        await session.commit()
        session.add(RolePermission(role_id=role.id, permission_id=perm.id, granted=1))
    await session.commit()
    user = await UserRepository(session).create(username, "Test User", hash_password("password123"), role.id)
    await session.commit()
    token = create_access_token(str(user.id), role_name, role.id, permissions)
    return {"Authorization": f"Bearer {token}"}


async def _seed_catalogue(session: AsyncSession) -> None:
    session.add_all(
        [
            Product(name="Paracetamol", price=10.00, internal_unique_barcode="INT-CK-A", vendor_name="Acme", expiry_date="2027-06-01"),
            Product(name="Ibuprofen", price=5.50, internal_unique_barcode="INT-CK-B", vendor_name="Acme", expiry_date="2027-06-01"),
        ]
    )
    await session.commit()
    await InventoryService(session).receive_batch(
        "Paracetamol", "LOT-A", (date.today() + timedelta(days=365)).isoformat(), 50, 1.0, "Acme"
    )
    await InventoryService(session).receive_batch(
        "Ibuprofen", "LOT-B", (date.today() + timedelta(days=365)).isoformat(), 50, 1.0, "Acme"
    )
    await session.commit()


# ── pos.price_override: denial path (the contract-documented gate) ──────────
async def test_price_override_denied_without_permission(client: AsyncClient, session: AsyncSession) -> None:
    """pos.checkout alone must NOT allow overriding prices: 403 forbidden."""
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 1}],
            "payment_method": "Cash",
            "price_overrides": {"Paracetamol": "7.25"},
        },
        headers=headers,
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "forbidden"
    assert "pos.price_override" in body["error"]["message"]


async def test_price_override_applied_with_permission(client: AsyncClient, session: AsyncSession) -> None:
    """With pos.price_override granted, the overridden unit price is used."""
    await _seed_catalogue(session)
    headers = await _user_headers(
        session, "manager", "manager", ["pos.checkout", "pos.price_override"]
    )
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 2}],
            "payment_method": "Cash",
            "price_overrides": {"Paracetamol": "7.25"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # net = 2 * 7.25 = 14.50 ; tax = round(14.50 * 0.14) = 2.03 ; total = 16.53
    assert body["items"][0]["unit_price"] == "7.25"
    assert body["net_total"] == "14.50"
    assert body["tax_total"] == "2.03"
    assert body["total_amount"] == "16.53"


async def test_price_override_admin_bypasses(client: AsyncClient, session: AsyncSession) -> None:
    """role_id == 1 bypasses the pos.price_override gate."""
    await _seed_catalogue(session)
    headers = await _user_headers(session, "owner", "Administrator", [], as_owner=True)
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 1}],
            "payment_method": "Cash",
            "price_overrides": {"Paracetamol": "7.25"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["items"][0]["unit_price"] == "7.25"


# ── tax_exempt ───────────────────────────────────────────────────────────────
async def test_tax_exempt_zeroes_tax(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    payload = {
        "line_items": [{"product_name": "Paracetamol", "quantity": 3}],
        "payment_method": "Cash",
    }
    taxed = await client.post("/api/v1/pos/checkout", json=payload, headers=headers)
    assert taxed.status_code == 201, taxed.text
    assert taxed.json()["tax_total"] == "4.20"  # round(30 * 0.14)
    assert taxed.json()["total_amount"] == "34.20"

    exempt = await client.post("/api/v1/pos/checkout", json={**payload, "tax_exempt": True}, headers=headers)
    assert exempt.status_code == 201, exempt.text
    body = exempt.json()
    assert body["net_total"] == "30.00"
    assert body["tax_total"] == "0.00"
    assert body["total_amount"] == "30.00"


# ── discounts (applied before tax; clamped at net) ─────────────────────────
async def test_discount_percent_applied_before_tax(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 2}],
            "payment_method": "Cash",
            "discount_type": "%",
            "discount_value": "10",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # net = 20.00 ; discount = 2.00 ; taxable = 18.00 ; tax = round(18 * 0.14) = 2.52
    assert body["net_total"] == "20.00"
    assert body["tax_total"] == "2.52"
    assert body["total_amount"] == "20.52"


async def test_discount_dollar_applied_before_tax(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Ibuprofen", "quantity": 2}],
            "payment_method": "Cash",
            "discount_type": "$",
            "discount_value": "3.25",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # net = 11.00 ; discount = 3.25 ; taxable = 7.75 ; tax = round(7.75*0.14) = 1.09 (half-up)
    assert body["net_total"] == "11.00"
    assert body["tax_total"] == "1.09"
    assert body["total_amount"] == "8.84"


async def test_discount_dollar_clamped_to_net(client: AsyncClient, session: AsyncSession) -> None:
    """A flat discount larger than the basket must never produce a negative total."""
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Ibuprofen", "quantity": 1}],
            "payment_method": "Cash",
            "discount_type": "$",
            "discount_value": "500",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_amount"] == "0.00"
    assert body["tax_total"] == "0.00"


async def test_discount_percent_rejected_over_100(client: AsyncClient, session: AsyncSession) -> None:
    """Service-level clamp caps %-discount at net; >100% must not go negative."""
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Ibuprofen", "quantity": 1}],
            "payment_method": "Cash",
            "discount_type": "%",
            "discount_value": "250",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_amount"] == "0.00"


# ── split payments (multi-tender) ────────────────────────────────────────────
async def test_split_payments_recorded(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 2}],
            "payment_method": "Cash",
            "payments": [
                {"method": "Cash", "amount": "10.00"},
                {"method": "Card", "amount": "12.80"},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # total = 20.00 net + 2.80 tax = 22.80 ; split sum 22.80 covers it
    assert body["total_amount"] == "22.80"
    assert body["payment_method"] == "Split: Cash 10.00 + Card 12.80"


async def test_split_payments_under_sum_rejected(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 2}],
            "payment_method": "Cash",
            "payments": [{"method": "Cash", "amount": "1.00"}],
        },
        headers=headers,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "split_insufficient"


# ── money bounds (schema Field(ge=0)) ────────────────────────────────────────
async def test_negative_discount_value_rejected_by_schema(client: AsyncClient, session: AsyncSession) -> None:
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    resp = await client.post(
        "/api/v1/pos/checkout",
        json={
            "line_items": [{"product_name": "Paracetamol", "quantity": 1}],
            "payment_method": "Cash",
            "discount_type": "$",
            "discount_value": "-5",
        },
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("field", ["tax_exempt", "payments", "discount_type"])
async def test_privileged_fields_absent_in_minimal_payload(client: AsyncClient, session: AsyncSession, field: str) -> None:
    """Legacy clients that omit the new fields entirely still get 201."""
    await _seed_catalogue(session)
    headers = await _user_headers(session, "clerk", "clerk", ["pos.checkout"])
    payload = {
        "line_items": [{"product_name": "Paracetamol", "quantity": 1}],
        "payment_method": "Cash",
    }
    assert field not in payload
    resp = await client.post("/api/v1/pos/checkout", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["total_amount"] == "11.40"  # 10.00 + 1.40 tax
