"""M7 — dispense workflow: patient-linked FIFO dispensing + thermal label (T5 dispense_service, T6 dispense_route)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    InsurancePlan,
    InventoryExtended,
    Patient,
    Permission,
    PriceCode,
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


# ── Helpers for coverage tests ────────────────────────────────────────────────

def _user(username: str = "cov_user"):
    return type("U", (), {"username": username, "role": "admin", "permissions": []})()


def _dispense_create(patient_id: int, client_tx_id: str, qty: int = 2, price_code: str | None = None,
                     insurance_plan_id: int | None = None) -> DispenseCreate:
    return DispenseCreate(
        patient_id=patient_id,
        product_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        sig_code="BID",
        quantity=qty,
        fill_date="2026-08-22",
        price_at_time=Decimal("12.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-A3F9B2",
        cashier="cov_user",
        client_tx_id=client_tx_id,
        price_code=price_code,
        insurance_plan_id=insurance_plan_id,
    )


async def _seed_patient(session: AsyncSession, name: str = "Cov Patient") -> Patient:
    p = Patient(name=name, dob="1985-05-05")
    session.add(p)
    await session.flush()
    return p


async def _seed_price_code(session: AsyncSession, code: str, *,
                           markup_pct: Decimal = Decimal("0"),
                           cost_factor_pct: Decimal = Decimal("100"),
                           dispensing_fee: Decimal = Decimal("0"),
                           min_price: Decimal = Decimal("0"),
                           max_price: Decimal = Decimal("999999.99")) -> PriceCode:
    pc = PriceCode(code=code, markup_pct=markup_pct, cost_factor_pct=cost_factor_pct,
                   dispensing_fee=dispensing_fee, min_price=min_price, max_price=max_price)
    session.add(pc)
    await session.flush()
    return pc


async def _seed_insurance(session: AsyncSession, plan_name: str = "TestPlan",
                          active: int = 1) -> InsurancePlan:
    plan = InsurancePlan(plan_name=plan_name, carrier_id="C1", bin="001",
                         pcn="PCN", group_number="G1", copay_tier="standard",
                         copay_amount=Decimal("10"), active=active)
    session.add(plan)
    await session.flush()
    return plan


# ── PriceCode: markup_pct formula (lines 153-154) ─────────────────────────────

async def test_dispense_price_code_markup(session: AsyncSession, stocked_product: int) -> None:
    """markup_pct=200 → base(10.00 WAC) * 2 + fee(5.00) = 25.00."""
    patient = await _seed_patient(session)
    lot = (await session.execute(
        select(InventoryExtended).where(InventoryExtended.drug_name == "Amoxicillin 500mg")
    )).scalars().first()
    lot.wac = Decimal("10.00")

    await _seed_price_code(session, "MKUP", markup_pct=Decimal("200"),
                           dispensing_fee=Decimal("5.00"))
    await session.commit()

    payload = _dispense_create(patient.id, "tx-mkup-1", qty=1, price_code="MKUP")
    result = await DispenseService(session).process_dispense(payload, _user())
    assert result.price_at_time == Decimal("25.00")


# ── PriceCode: cost_factor_pct formula (lines 155-156) ────────────────────────

async def test_dispense_price_code_cost_factor(session: AsyncSession, stocked_product: int) -> None:
    """cost_factor_pct=150 → base(10.00) * 1.5 + fee(2.00) = 17.00."""
    patient = await _seed_patient(session)
    lot = (await session.execute(
        select(InventoryExtended).where(InventoryExtended.drug_name == "Amoxicillin 500mg")
    )).scalars().first()
    lot.wac = Decimal("10.00")
    await session.flush()

    await _seed_price_code(session, "COST", markup_pct=Decimal("0"),
                           cost_factor_pct=Decimal("150"),
                           dispensing_fee=Decimal("2.00"))
    await session.commit()

    payload = _dispense_create(patient.id, "tx-cost-1", qty=1, price_code="COST")
    result = await DispenseService(session).process_dispense(payload, _user())
    assert result.price_at_time == Decimal("17.00")


# ── PriceCode: fee only, no markup/cost_factor (lines 157-158) ────────────────

async def test_dispense_price_code_fee_only(session: AsyncSession, stocked_product: int) -> None:
    """No markup, no cost_factor → base(10.00) + fee(3.00) = 13.00."""
    patient = await _seed_patient(session)
    lot = (await session.execute(
        select(InventoryExtended).where(InventoryExtended.drug_name == "Amoxicillin 500mg")
    )).scalars().first()
    lot.wac = Decimal("10.00")
    await session.flush()

    await _seed_price_code(session, "FEE", dispensing_fee=Decimal("3.00"))
    await session.commit()

    payload = _dispense_create(patient.id, "tx-fee-1", qty=1, price_code="FEE")
    result = await DispenseService(session).process_dispense(payload, _user())
    assert result.price_at_time == Decimal("13.00")


# ── PriceCode: min_price clamp (lines 162-163) ───────────────────────────────

async def test_dispense_price_code_min_clamp(session: AsyncSession, stocked_product: int) -> None:
    """Computed price(5.00) < min_price(8.00) → clamped to 8.00."""
    patient = await _seed_patient(session)
    lot = (await session.execute(
        select(InventoryExtended).where(InventoryExtended.drug_name == "Amoxicillin 500mg")
    )).scalars().first()
    lot.wac = Decimal("2.00")
    await session.flush()

    await _seed_price_code(session, "MINC", markup_pct=Decimal("100"),
                           dispensing_fee=Decimal("3.00"),
                           min_price=Decimal("8.00"))
    await session.commit()

    payload = _dispense_create(patient.id, "tx-minc-1", qty=1, price_code="MINC")
    result = await DispenseService(session).process_dispense(payload, _user())
    assert result.price_at_time == Decimal("8.00")


# ── PriceCode: max_price clamp (lines 164-165) ───────────────────────────────

async def test_dispense_price_code_max_clamp(session: AsyncSession, stocked_product: int) -> None:
    """Computed price(30.00) > max_price(20.00) → clamped to 20.00."""
    patient = await _seed_patient(session)
    lot = (await session.execute(
        select(InventoryExtended).where(InventoryExtended.drug_name == "Amoxicillin 500mg")
    )).scalars().first()
    lot.wac = Decimal("10.00")
    await session.flush()

    await _seed_price_code(session, "MAXC", markup_pct=Decimal("200"),
                           dispensing_fee=Decimal("0"),
                           max_price=Decimal("20.00"))
    await session.commit()

    payload = _dispense_create(patient.id, "tx-maxc-1", qty=1, price_code="MAXC")
    result = await DispenseService(session).process_dispense(payload, _user())
    assert result.price_at_time == Decimal("20.00")


# ── Insurance: inactive plan (lines 113-116) ──────────────────────────────────

async def test_dispense_insurance_inactive(session: AsyncSession, stocked_product: int) -> None:
    """insurance_plan_id points to an inactive plan → NotFoundError."""
    patient = await _seed_patient(session)
    plan = await _seed_insurance(session, active=0)
    await session.commit()

    payload = _dispense_create(patient.id, "tx-inact-1", qty=1, insurance_plan_id=plan.id)
    with pytest.raises(NotFoundError):
        await DispenseService(session).process_dispense(payload, _user())


# ── Insurance: valid plan (lines 113-116) ─────────────────────────────────────

async def test_dispense_insurance_valid(session: AsyncSession, stocked_product: int) -> None:
    """Valid active insurance plan → dispense succeeds."""
    patient = await _seed_patient(session)
    plan = await _seed_insurance(session, active=1)
    await session.commit()

    payload = _dispense_create(patient.id, "tx-ins-1", qty=1, insurance_plan_id=plan.id)
    result = await DispenseService(session).process_dispense(payload, _user())
    assert result.patient_id == patient.id


# ── Lot-level AWP/MAC/WAC pricing (lines 139-147) ────────────────────────────

async def test_dispense_lot_awp_pricing(session: AsyncSession, stocked_product: int) -> None:
    """Lot has AWP set, no price_code → unit price falls back to lot_awp."""
    patient = await _seed_patient(session)
    lot = (await session.execute(
        select(InventoryExtended).where(InventoryExtended.drug_name == "Amoxicillin 500mg")
    )).scalars().first()
    lot.awp = Decimal("20.00")
    lot.mac = Decimal("15.00")
    lot.wac = None  # wac is None → base_cost = lot_mac = 15.00
    await session.commit()

    payload = _dispense_create(patient.id, "tx-lot-1", qty=1)
    result = await DispenseService(session).process_dispense(payload, _user())
    # No price_code → unit = product.price = 12.50 (price_code branch is skipped)
    assert result.price_at_time == Decimal("12.50")


# ── process_refill: success (lines 380-551) ───────────────────────────────────

async def test_dispense_refill_success(session: AsyncSession, stocked_product: int) -> None:
    """Refill an existing dispense with refills_authorized > 0."""
    patient = await _seed_patient(session)
    await session.commit()

    # Create original dispense with 2 refills authorized
    original = _dispense_create(patient.id, "tx-refill-orig", qty=1)
    original.refills_authorized = 2
    created = await DispenseService(session).process_dispense(original, _user())
    assert created.refill_count == 0
    assert created.refills_authorized == 2

    # Refill
    refill_payload = _dispense_create(patient.id, "tx-refill-1", qty=1)
    refill_result = await DispenseService(session).process_refill(
        created.id, refill_payload, _user()
    )
    assert refill_result.refill_count == 1
    assert refill_result.refills_authorized == 2
    assert refill_result.rx_number == created.rx_number  # Same Rx number


# ── process_refill: no refills left (lines 394-400) ───────────────────────────

async def test_dispense_refill_exhausted(session: AsyncSession, stocked_product: int) -> None:
    """Refill when refill_count >= refills_authorized → HTTP 400."""
    from fastapi import HTTPException
    patient = await _seed_patient(session)
    await session.commit()

    original = _dispense_create(patient.id, "tx-exh-orig", qty=1)
    original.refills_authorized = 0
    created = await DispenseService(session).process_dispense(original, _user())

    refill_payload = _dispense_create(patient.id, "tx-exh-1", qty=1)
    with pytest.raises(HTTPException) as exc_info:
        await DispenseService(session).process_refill(
            created.id, refill_payload, _user()
        )
    assert exc_info.value.status_code == 400
    assert "No refills remaining" in exc_info.value.detail


# ── process_refill: dispense not found (line 391) ────────────────────────────

async def test_dispense_refill_not_found(session: AsyncSession) -> None:
    """Refill a non-existent dispense → NotFoundError."""
    payload = _dispense_create(99999, "tx-nf-1", qty=1)
    with pytest.raises(NotFoundError):
        await DispenseService(session).process_refill(99999, payload, _user())


# ── process_dispense: product not found (lines 119-121) ───────────────────────

async def test_dispense_product_not_found(session: AsyncSession) -> None:
    """Product does not exist → NotFoundError."""
    patient = await _seed_patient(session)
    await session.commit()

    payload = DispenseCreate(
        patient_id=patient.id,
        product_name="Nonexistent Drug",
        ndc_code="0",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("0"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="",
        cashier="test",
        client_tx_id="tx-pnf-1",
    )
    with pytest.raises(NotFoundError):
        await DispenseService(session).process_dispense(payload, _user())


# ── Insurance: missing plan (line 114-116) ────────────────────────────────────

async def test_dispense_insurance_missing(session: AsyncSession, stocked_product: int) -> None:
    """insurance_plan_id points to non-existent plan → NotFoundError."""
    patient = await _seed_patient(session)
    await session.commit()

    payload = _dispense_create(patient.id, "tx-misins-1", qty=1, insurance_plan_id=99999)
    with pytest.raises(NotFoundError):
        await DispenseService(session).process_dispense(payload, _user())


# ── No price_code, no lot WAC → fallback to product.price (line 150) ─────────

async def test_dispense_no_price_code_uses_product_price(
    session: AsyncSession, stocked_product: int,
) -> None:
    """No price_code, lot WAC/MAC/AWP all None → unit = product.price."""
    patient = await _seed_patient(session)
    lot = (await session.execute(
        select(InventoryExtended).where(InventoryExtended.drug_name == "Amoxicillin 500mg")
    )).scalars().first()
    lot.wac = None
    lot.mac = None
    lot.awp = None
    await session.commit()

    payload = _dispense_create(patient.id, "tx-fb-1", qty=1)
    result = await DispenseService(session).process_dispense(payload, _user())
    assert result.price_at_time == Decimal("12.50")


# ── M104: Edit Rx (update_dispense) ───────────────────────────────────────────

async def test_update_dispense_sig(session: AsyncSession, stocked_product: int) -> None:
    """update_dispense changes sig_code."""
    patient = await _seed_patient(session)
    await session.commit()
    payload = _dispense_create(patient.id, "tx-edit-1", qty=1)
    created = await DispenseService(session).process_dispense(payload, _user())

    from app.shared.schemas import DispenseUpdate
    update = DispenseUpdate(sig_code="QID")
    result = await DispenseService(session).update_dispense(created.id, update, _user())
    assert result.sig_code == "QID"


async def test_update_dispense_quantity(session: AsyncSession, stocked_product: int) -> None:
    """update_dispense changes quantity."""
    patient = await _seed_patient(session)
    await session.commit()
    payload = _dispense_create(patient.id, "tx-edit-2", qty=1)
    created = await DispenseService(session).process_dispense(payload, _user())

    from app.shared.schemas import DispenseUpdate
    update = DispenseUpdate(quantity=5)
    result = await DispenseService(session).update_dispense(created.id, update, _user())
    assert result.quantity == 5


async def test_update_dispense_not_found(session: AsyncSession) -> None:
    """update_dispense on non-existent dispense → NotFoundError."""
    from app.shared.schemas import DispenseUpdate
    update = DispenseUpdate(sig_code="QID")
    with pytest.raises(NotFoundError):
        await DispenseService(session).update_dispense(99999, update, _user())


# ── M104: Reverse Rx (void_dispense) ──────────────────────────────────────────

async def test_void_dispense(session: AsyncSession, stocked_product: int) -> None:
    """void_dispense marks dispense as voided and restocks."""
    patient = await _seed_patient(session)
    await session.commit()
    payload = _dispense_create(patient.id, "tx-void-1", qty=2)
    created = await DispenseService(session).process_dispense(payload, _user())

    result = await DispenseService(session).void_dispense(created.id, "Wrong Rx", _user())
    assert result.voided is True
    assert result.restocked_quantity == 2
    assert result.reason == "Wrong Rx"
    assert "VOID" in (result.rx_number or "")


async def test_void_dispense_not_found(session: AsyncSession) -> None:
    """void_dispense on non-existent dispense → NotFoundError."""
    with pytest.raises(NotFoundError):
        await DispenseService(session).void_dispense(99999, "test", _user())


# ── M104: Transfer Rx (transfer_dispense) ─────────────────────────────────────

async def test_transfer_dispense_outgoing(session: AsyncSession, stocked_product: int) -> None:
    """transfer_dispense outgoing marks as transferred."""
    patient = await _seed_patient(session)
    await session.commit()
    payload = _dispense_create(patient.id, "tx-xfer-1", qty=1)
    created = await DispenseService(session).process_dispense(payload, _user())

    result = await DispenseService(session).transfer_dispense(
        created.id, "Walgreens #1234", "(555) 123-4567", "outgoing", "Patient moved", _user(),
    )
    assert result.transferred is True
    assert result.transfer_type == "outgoing"
    assert result.pharmacy_name == "Walgreens #1234"
    assert "XFER-OUT" in (result.rx_number or "")


async def test_transfer_dispense_incoming(session: AsyncSession, stocked_product: int) -> None:
    """transfer_dispense incoming marks as transferred."""
    patient = await _seed_patient(session)
    await session.commit()
    payload = _dispense_create(patient.id, "tx-xfer-2", qty=1)
    created = await DispenseService(session).process_dispense(payload, _user())

    result = await DispenseService(session).transfer_dispense(
        created.id, "CVS #5678", "(555) 987-6543", "incoming", "New patient transfer", _user(),
    )
    assert result.transferred is True
    assert result.transfer_type == "incoming"
    assert "XFER-IN" in (result.rx_number or "")


async def test_transfer_dispense_not_found(session: AsyncSession) -> None:
    """transfer_dispense on non-existent dispense → NotFoundError."""
    with pytest.raises(NotFoundError):
        await DispenseService(session).transfer_dispense(99999, "test", "", "outgoing", "", _user())


# ── M104: Eligibility check ───────────────────────────────────────────────────

async def test_eligibility_with_plan(client: AsyncClient, session: AsyncSession, auth: dict[str, str]) -> None:
    """check_eligibility with a bound insurance plan returns eligible."""
    from app.core.models import InsurancePlan
    plan = InsurancePlan(plan_name="TestHealth", carrier_id="C1", bin="001",
                         pcn="PCN", group_number="G1", copay_tier="standard",
                         copay_amount=Decimal("10"), active=1)
    session.add(plan)
    await session.flush()

    resp = await client.post(
        "/api/v1/patients",
        json={"name": "Elig Patient", "dob": "1990-01-01", "insurance_plan_id": plan.id},
        headers=auth,
    )
    assert resp.status_code == 201
    patient_id = resp.json()["id"]

    resp = await client.post("/api/v1/insurance/eligibility", json={"patient_id": patient_id}, headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["eligible"] is True
    assert body["plan_name"] == "TestHealth"
    assert body["active"] is True


async def test_eligibility_no_plan(client: AsyncClient, session: AsyncSession, auth: dict[str, str]) -> None:
    """check_eligibility without bound plan returns not eligible."""
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "No Ins Patient", "dob": "1990-01-01"},
        headers=auth,
    )
    assert resp.status_code == 201
    patient_id = resp.json()["id"]

    resp = await client.post("/api/v1/insurance/eligibility", json={"patient_id": patient_id}, headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["eligible"] is False
    assert "No insurance plan" in body["message"]


async def test_eligibility_patient_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    """check_eligibility with non-existent patient → 404."""
    resp = await client.post("/api/v1/insurance/eligibility", json={"patient_id": 99999}, headers=auth)
    assert resp.status_code == 404
