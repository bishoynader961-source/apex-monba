"""M105 — Receipt print preview & thermal text generation endpoint."""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Product, Receipt, ReceiptItem, Role, RolePermission, SystemSetting
from app.shared.security import hash_password

_PERMS = ["inventory.read", "inventory.write", "inventory.reports", "pos.checkout", "users.write"]


async def _checkout_token(client: AsyncClient, session: AsyncSession) -> str:
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
    from app.core.repositories import UserRepository
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "adminroot", "password": "password123"})
    assert resp.status_code == 200
    token: str = resp.json()["access_token"]
    return token


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _checkout_token(client, session)}"}


@pytest.fixture
async def sample_receipt(session: AsyncSession) -> int:
    """Create a receipt with 2 line items directly in the DB."""
    receipt = Receipt(
        timestamp="2026-09-05T10:30:00",
        total_amount=Decimal("46.74"),
        payment_method="Cash",
        patient_id=None,
        server_created_at="2026-09-05T10:30:00",
        cashier_attribution="Cashier1",
        sale_type="OTC",
    )
    session.add(receipt)
    await session.flush()

    session.add(ReceiptItem(
        receipt_id=receipt.id,
        product_name="Paracetamol",
        quantity=3,
        price_at_time=Decimal("10.00"),
        internal_barcode="INT-A",
        vendor="Acme",
        expiry_date="2027-06-01",
    ))
    session.add(ReceiptItem(
        receipt_id=receipt.id,
        product_name="Ibuprofen",
        quantity=2,
        price_at_time=Decimal("5.50"),
        internal_barcode="INT-B",
        vendor="Acme",
        expiry_date="2027-06-01",
    ))
    await session.commit()
    return receipt.id


@pytest.fixture
async def pharmacy_settings(session: AsyncSession) -> None:
    """Insert pharmacy name/address/phone into system_settings."""
    session.add(SystemSetting(key="pharmacy_name", value=b"Test Pharmacy"))
    session.add(SystemSetting(key="pharmacy_address", value=b"123 Main St"))
    session.add(SystemSetting(key="pharmacy_phone", value=b"555-0100"))
    await session.commit()


async def test_receipt_print_success(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    sample_receipt: int, pharmacy_settings: None,
) -> None:
    """GET /receipts/{id}/print returns structured response with thermal text + HTML."""
    resp = await client.get(
        f"/api/v1/pos/receipts/{sample_receipt}/print",
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["receipt_id"] == sample_receipt
    assert body["receipt_number"].startswith("RCP-")
    assert body["payment_method"] == "Cash"
    assert body["cashier_attribution"] == "Cashier1"
    # receipt_text contains pharmacy name and key fields
    assert "Test Pharmacy" in body["receipt_text"]
    assert "123 Main St" in body["receipt_text"]
    assert "555-0100" in body["receipt_text"]
    assert "Thank" in body["receipt_text"].lower() or "THANK" in body["receipt_text"]
    # receipt_text has item lines
    assert "Paracetamol" in body["receipt_text"]
    assert "Ibuprofen" in body["receipt_text"]
    assert "46.74" in body["receipt_text"]
    # printable_html is non-empty HTML
    assert body["printable_html"], "printable_html should not be empty"
    assert "receipt-items" in body["printable_html"]
    assert "Pharmacy" in body["printable_html"] or "Test Pharmacy" in body["printable_html"]
    # items returned
    assert len(body["items"]) == 2
    assert body["items"][0]["product_name"] == "Paracetamol"
    assert body["items"][1]["product_name"] == "Ibuprofen"


async def test_receipt_print_not_found(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
) -> None:
    """GET /receipts/{id}/print with invalid ID returns 404."""
    resp = await client.get(
        "/api/v1/pos/receipts/99999/print",
        headers=auth,
    )
    assert resp.status_code == 404


async def test_receipt_print_unauthorized(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """GET /receipts/{id}/print without auth returns 401."""
    resp = await client.get("/api/v1/pos/receipts/1/print")
    assert resp.status_code == 401


async def test_receipt_print_uses_fallback_pharmacy_name(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    sample_receipt: int,
) -> None:
    """Without pharmacy_name setting, falls back to 'Pharmacy'."""
    resp = await client.get(
        f"/api/v1/pos/receipts/{sample_receipt}/print",
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Pharmacy" in body["receipt_text"] or "Test Pharmacy" in body["receipt_text"]


async def test_receipt_print_thermal_format(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    sample_receipt: int, pharmacy_settings: None,
) -> None:
    """Thermal text has expected fixed-width formatting markers."""
    resp = await client.get(
        f"/api/v1/pos/receipts/{sample_receipt}/print",
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The receipt_text should have separator lines (dashes)
    assert "-" in body["receipt_text"]
    # Should contain payment method
    assert "Payment" in body["receipt_text"] or "CASH" in body["receipt_text"].upper()
