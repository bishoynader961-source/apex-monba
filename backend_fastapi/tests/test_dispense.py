"""M7 — dispense workflow: patient-linked FIFO dispensing + thermal label (T5 dispense_service, T6 dispense_route)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    InventoryExtended,
    Permission,
    Product,
    Role,
    RolePermission,
)
from app.core.repositories import UserRepository
from app.services.dispense_service import DispenseService
from app.shared.exceptions import NotFoundError
from app.shared.schemas import DispenseCreate
from app.shared.security import hash_password

_ALL = [
    "patients.read",
    "patients.write",
    "patients.delete",
    "dispense.create",
    "dictionaries.read",
    "dictionaries.write",
    "insurance.read",
    "insurance.write",
    "members.read",
    "members.write",
]


async def _token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    for key in _ALL:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        await session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("rxuser", "Rx", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "rxuser", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session)}"}


@pytest.fixture
async def patient(client: AsyncClient, auth: dict[str, str]) -> int:
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "Dispenser Test", "dob": "1990-01-01"},
        headers=auth,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
async def stocked_product(session: AsyncSession) -> int:
    """Create a product with inventory lots for FIFO testing."""
    product = Product(name="Amoxicillin 500mg", price=Decimal("12.50"))
    session.add(product)
    await session.flush()

    session.add(InventoryExtended(
        drug_name="Amoxicillin 500mg",
        lot_number="OLD1",
        expiration_date="2026-12-31",
        on_hand=10,
        supplier="MedSupply",
        ndc_code="00069-0168-24",
    ))
    await session.commit()
    return product.id


def _dispense_payload(patient_id: int, qty: int = 3) -> dict:
    return {
        "patient_id": patient_id,
        "product_name": "Amoxicillin 500mg",
        "ndc_code": "00069-0168-24",
        "sig_code": "BID",
        "quantity": qty,
        "fill_date": "2026-08-22",
        "price_at_time": "12.50",
        "insurance_copay": "0.00",
        "insurance_amount": "0.00",
        "internal_barcode": "MED-A3F9B2",
        "cashier": "dr_smith",
        "client_tx_id": f"tx-{datetime.now(timezone.utc).timestamp()}",
    }


# ── HTTP route tests ──

async def test_dispense_missing_insurance_plan(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    patient: int, stocked_product: int,
) -> None:
    payload = _dispense_payload(patient, qty=1)
    payload["insurance_plan_id"] = 99999
    resp = await client.post("/api/v1/dispense", json=payload, headers=auth)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"

async def test_dispense_success(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    patient: int, stocked_product: int,
) -> None:
    resp = await client.post(
        "/api/v1/dispense",
        json=_dispense_payload(patient, qty=3),
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["product_name"] == "Amoxicillin 500mg"
    assert body["quantity"] == 3
    assert body["patient_id"] == patient
    assert body["cashier"] == "rxuser"
    assert len(body["items"]) == 1
    assert body["items"][0]["lot_number"] == "OLD1"
    assert body["items"][0]["quantity"] == 3


async def test_dispense_insufficient_stock(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    patient: int, stocked_product: int,
) -> None:
    resp = await client.post(
        "/api/v1/dispense",
        json=_dispense_payload(patient, qty=999),
        headers=auth,
    )
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "over_sell"


async def test_dispense_missing_patient(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    stocked_product: int,
) -> None:
    payload = _dispense_payload(99999, qty=1)
    resp = await client.post("/api/v1/dispense", json=payload, headers=auth)
    assert resp.status_code == 404


async def test_dispense_idempotency(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    patient: int, stocked_product: int,
) -> None:
    payload = _dispense_payload(patient, qty=2)
    first = await client.post("/api/v1/dispense", json=payload, headers=auth)
    assert first.status_code == 201
    first_id = first.json()["id"]

    # Re-use the same client_tx_id — should return the cached result.
    second = await client.post("/api/v1/dispense", json=payload, headers=auth)
    assert second.status_code == 201
    assert second.json()["id"] == first_id
    # Stock should only be deducted once (10 -> 8, not 10 -> 6).


async def test_dispense_label_endpoint(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    patient: int, stocked_product: int,
) -> None:
    create = await client.post(
        "/api/v1/dispense", json=_dispense_payload(patient, qty=1), headers=auth
    )
    assert create.status_code == 201
    dispense_id = create.json()["id"]

    label = await client.get(f"/api/v1/dispense/{dispense_id}/label", headers=auth)
    assert label.status_code == 200
    assert label.headers["content-type"] == "application/octet-stream"
    assert len(label.content) > 0


async def test_get_dispense_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/dispense/99999", headers=auth)
    assert resp.status_code == 404


async def test_get_dispense_soft_deleted_patient_hides(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str],
    stocked_product: int,
) -> None:
    # Create a dispense for a patient, then soft-delete the patient.
    create = await client.post(
        "/api/v1/patients", json={"name": "Ghost Rx", "dob": "1980-01-01"}, headers=auth
    )
    pid = create.json()["id"]
    disp = await client.post(
        "/api/v1/dispense", json=_dispense_payload(pid, qty=1), headers=auth
    )
    assert disp.status_code == 201
    did = disp.json()["id"]

    await client.delete(f"/api/v1/patients/{pid}", headers=auth)
    hidden = await client.get(f"/api/v1/dispense/{did}", headers=auth)
    assert hidden.status_code == 404


# ── Direct-await service tests ──────────────────────────────────────────────────

async def test_dispense_service_process_success(
    session: AsyncSession, stocked_product: int,
) -> None:
    from app.core.models import Patient
    patient = Patient(name="Svc Patient", dob="1985-05-05")
    session.add(patient)
    await session.commit()

    payload = DispenseCreate(
        patient_id=patient.id,
        product_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        sig_code="BID",
        quantity=2,
        fill_date="2026-08-22",
        price_at_time=Decimal("12.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-A3F9B2",
        cashier="dr_svc",
        client_tx_id="svc-tx-001",
    )
    user = type("U", (), {"username": "dr_svc", "role": "admin", "permissions": []})()
    result = await DispenseService(session).process_dispense(payload, user)  # type: ignore[arg-type]
    assert result.product_name == "Amoxicillin 500mg"
    assert result.quantity == 2
    assert len(result.items) == 1


async def test_dispense_service_missing_patient(session: AsyncSession) -> None:
    payload = DispenseCreate(
        patient_id=99999,
        product_name="X",
        ndc_code="x",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("0"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="",
        cashier="test",
        client_tx_id="tx-miss-1",
    )
    user = type("U", (), {"username": "test", "role": "admin", "permissions": []})()
    with pytest.raises(NotFoundError):
        await DispenseService(session).process_dispense(payload, user)  # type: ignore[arg-type]


async def test_dispense_service_label_bytes(
    session: AsyncSession, stocked_product: int,
) -> None:
    from app.core.models import Patient
    p = Patient(name="Label Svc", dob="1980-01-01")
    session.add(p)
    await session.commit()
    payload = DispenseCreate(
        patient_id=p.id,
        product_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("12.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-A3F9B2",
        cashier="dr_svc",
        client_tx_id="label-tx-001",
    )
    user = type("U", (), {"username": "dr_svc", "role": "admin", "permissions": []})()
    result = await DispenseService(session).process_dispense(payload, user)  # type: ignore[arg-type]
    label = await DispenseService(session).label_bytes(result.id)
    assert b"PRESCRIPTION" in label
    assert b"Label Svc" in label
    assert b"Amoxicillin 500mg" in label


async def test_dispense_service_get_by_client_tx_id(
    session: AsyncSession, stocked_product: int,
) -> None:
    from app.core.models import Patient
    p = Patient(name="Dup Svc", dob="1980-01-01")
    session.add(p)
    await session.commit()
    payload = DispenseCreate(
        patient_id=p.id,
        product_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("12.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-A3F9B2",
        cashier="dr_svc",
        client_tx_id="dup-tx-001",
    )
    user = type("U", (), {"username": "dr_svc", "role": "admin", "permissions": []})()
    first = await DispenseService(session).process_dispense(payload, user)  # type: ignore[arg-type]
    cached = await DispenseService(session).process_dispense(payload, user)  # type: ignore[arg-type]
    assert cached.id == first.id
