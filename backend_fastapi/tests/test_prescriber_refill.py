"""Tests for prescriber CRUD routes and dispense refill endpoint."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import PatientRepository, ProductRepository
from app.shared.schemas import PatientCreate, ProductCreate


@pytest.fixture()
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    from app.services.seed_service import seed_admin_if_absent, seed_clinical_defaults

    await seed_admin_if_absent(session)
    await seed_clinical_defaults(session)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    data = resp.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_patient(session: AsyncSession) -> int:
    repo = PatientRepository(session)
    p = await repo.create(
        PatientCreate(
            name="Test Patient Rx",
            dob="1990-01-01",
            address="123 Main St",
            contact_phone="555-0001",
        )
    )
    return p.id


async def _create_product(session: AsyncSession) -> None:
    from app.core.models import InventoryExtended

    repo = ProductRepository(session)
    await repo.create(
        ProductCreate(
            name="TestDrug Rx",
            price="10.00",
            manufacturer_barcode="MFG-RX-001",
            internal_unique_barcode=f"MED-{uuid.uuid4().hex[:6].upper()}",
        )
    )
    # Ensure inventory_extended has stock for FIFO deduction
    session.add(
        InventoryExtended(
            drug_name="TestDrug Rx",
            on_hand=100,
            lot_number="LOT-RX-001",
            expiration_date="2027-12-31",
            ndc_code="12345-678-90",
            supplier="TestSupplier",
        )
    )
    await session.commit()


# ── Prescriber CRUD ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prescriber_create_and_list(client: AsyncClient, auth: dict[str, str]) -> None:
    payload = {
        "first_name": "John",
        "last_name": "Smith",
        "npi": "1234567890",
        "dea_number": "AB1234567",
        "phone": "555-1234",
    }
    resp = await client.post("/api/v1/prescribers", json=payload, headers=auth)
    assert resp.status_code == 201
    data = resp.json()
    assert data["first_name"] == "John"
    assert data["last_name"] == "Smith"
    assert data["npi"] == "1234567890"
    prescriber_id = data["id"]

    # List
    resp = await client.get("/api/v1/prescribers", headers=auth)
    assert resp.status_code == 200
    items = resp.json()
    assert any(p["id"] == prescriber_id for p in items)

    # Get by id
    resp = await client.get(f"/api/v1/prescribers/{prescriber_id}", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["npi"] == "1234567890"


@pytest.mark.asyncio
async def test_prescriber_update(client: AsyncClient, auth: dict[str, str]) -> None:
    payload = {"first_name": "Jane", "last_name": "Doe"}
    resp = await client.post("/api/v1/prescribers", json=payload, headers=auth)
    pid = resp.json()["id"]

    update = {"first_name": "Janet", "last_name": "Doe", "npi": "9999999999"}
    resp = await client.put(f"/api/v1/prescribers/{pid}", json=update, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Janet"
    assert resp.json()["npi"] == "9999999999"


@pytest.mark.asyncio
async def test_prescriber_delete(client: AsyncClient, auth: dict[str, str]) -> None:
    payload = {"first_name": "Delete", "last_name": "Me"}
    resp = await client.post("/api/v1/prescribers", json=payload, headers=auth)
    pid = resp.json()["id"]

    resp = await client.delete(f"/api/v1/prescribers/{pid}", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["is_deleted"] is True

    resp = await client.get(f"/api/v1/prescribers/{pid}", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_prescriber_npi_conflict(client: AsyncClient, auth: dict[str, str]) -> None:
    payload = {"first_name": "A", "last_name": "B", "npi": "1111111111"}
    resp = await client.post("/api/v1/prescribers", json=payload, headers=auth)
    assert resp.status_code == 201

    payload2 = {"first_name": "C", "last_name": "D", "npi": "1111111111"}
    resp = await client.post("/api/v1/prescribers", json=payload2, headers=auth)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_prescriber_search(client: AsyncClient, auth: dict[str, str]) -> None:
    await client.post(
        "/api/v1/prescribers",
        json={"first_name": "Alpha", "last_name": "Searchable"},
        headers=auth,
    )
    resp = await client.get("/api/v1/prescribers?search=Searchable", headers=auth)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_prescriber_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/prescribers/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_prescriber_delete_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.delete("/api/v1/prescribers/99999", headers=auth)
    assert resp.status_code == 404


# ── Dispense Refill ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispense_refill(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    await _create_product(session)
    patient_id = await _create_patient(session)

    # Create initial dispense
    dispense_payload = {
        "patient_id": patient_id,
        "product_name": "TestDrug Rx",
        "ndc_code": "12345-678-90",
        "sig_code": "TAB-1-QD",
        "quantity": 30,
        "fill_date": "2026-09-01",
        "price_at_time": "10.00",
        "client_tx_id": str(uuid.uuid4()),
        "refills_authorized": 3,
        "days_supply": 30,
    }
    resp = await client.post("/api/v1/dispense", json=dispense_payload, headers=auth)
    assert resp.status_code == 201
    dispense_id = resp.json()["id"]
    rx_number = resp.json()["rx_number"]
    assert rx_number is not None
    assert resp.json()["refill_count"] == 0
    assert resp.json()["refills_authorized"] == 3

    # Refill
    refill_payload = {
        "patient_id": patient_id,
        "product_name": "TestDrug Rx",
        "ndc_code": "12345-678-90",
        "sig_code": "TAB-1-QD",
        "quantity": 30,
        "fill_date": "2026-10-01",
        "price_at_time": "10.00",
        "client_tx_id": str(uuid.uuid4()),
    }
    resp = await client.post(
        f"/api/v1/dispense/{dispense_id}/refill", json=refill_payload, headers=auth
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rx_number"] == rx_number  # Same Rx
    assert data["refill_count"] == 1
    assert data["refills_authorized"] == 3


@pytest.mark.asyncio
async def test_dispense_refill_exhausted(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    await _create_product(session)
    patient_id = await _create_patient(session)

    # Create dispense with 0 refills
    dispense_payload = {
        "patient_id": patient_id,
        "product_name": "TestDrug Rx",
        "ndc_code": "12345-678-90",
        "sig_code": "TAB-1-QD",
        "quantity": 30,
        "fill_date": "2026-09-01",
        "price_at_time": "10.00",
        "client_tx_id": str(uuid.uuid4()),
        "refills_authorized": 0,
    }
    resp = await client.post("/api/v1/dispense", json=dispense_payload, headers=auth)
    assert resp.status_code == 201
    dispense_id = resp.json()["id"]

    # Try to refill — should fail with 400 or 500 (no refills remaining)
    refill_payload = {
        "patient_id": patient_id,
        "product_name": "TestDrug Rx",
        "ndc_code": "12345-678-90",
        "sig_code": "TAB-1-QD",
        "quantity": 30,
        "fill_date": "2026-10-01",
        "price_at_time": "10.00",
        "client_tx_id": str(uuid.uuid4()),
    }
    resp = await client.post(
        f"/api/v1/dispense/{dispense_id}/refill", json=refill_payload, headers=auth
    )
    # Should fail because no refills remaining (400 or 500 depending on error handling)
    assert resp.status_code in (400, 422, 500)


@pytest.mark.asyncio
async def test_dispense_refill_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    refill_payload = {
        "patient_id": 1,
        "product_name": "Fake",
        "ndc_code": "",
        "sig_code": "TAB-1-QD",
        "quantity": 30,
        "fill_date": "2026-10-01",
        "price_at_time": "10.00",
        "client_tx_id": str(uuid.uuid4()),
    }
    resp = await client.post(
        "/api/v1/dispense/99999/refill", json=refill_payload, headers=auth
    )
    assert resp.status_code == 404
