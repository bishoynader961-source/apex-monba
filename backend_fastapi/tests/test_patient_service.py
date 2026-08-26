"""M7 — PatientService direct-await coverage: get, list, search, create, update, delete, insurance, members, history."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import InsurancePlan, Patient, Receipt, MembersGroup
from app.core.repositories import InsuranceRepository, PatientRepository
from app.services.patient_service import PatientService
from app.shared.exceptions import NotFoundError
from app.shared.schemas import InsurancePlanCreate, PatientCreate, PatientUpdate


# ── Helper ─────────────────────────────────────────────────────────────────────

def _make_patient(name: str = "Test Patient", dob: str = "1990-01-01") -> Patient:
    return Patient(name=name, dob=dob, address="", patient_allergies="", comments="")


# ── get ────────────────────────────────────────────────────────────────────────

async def test_get_patient(session: AsyncSession) -> None:
    p = _make_patient("Get Me")
    session.add(p)
    await session.commit()
    result = await PatientService(session).get(p.id)
    assert result.id == p.id
    assert result.name == "Get Me"


async def test_get_patient_not_found(session: AsyncSession) -> None:
    try:
        await PatientService(session).get(99999)
    except NotFoundError:
        pass


# ── list_patients ─────────────────────────────────────────────────────────────

async def test_list_patients_pagination(session: AsyncSession) -> None:
    for i in range(5):
        session.add(_make_patient(f"List{i}"))
    await session.commit()
    items, total = await PatientService(session).list_patients(page=1, page_size=3)
    assert total >= 5
    assert len(items) == 3
    items2, total2 = await PatientService(session).list_patients(page=2, page_size=3)
    assert total2 == total


async def test_list_patients_with_search(session: AsyncSession) -> None:
    session.add(_make_patient("AlphaSearch"))
    session.add(_make_patient("BetaSearch"))
    await session.commit()
    items, total = await PatientService(session).list_patients(q="Alpha")
    assert total == 1
    assert items[0].name == "AlphaSearch"


async def test_list_patients_empty(session: AsyncSession) -> None:
    items, total = await PatientService(session).list_patients()
    assert total == 0
    assert items == []


# ── search ─────────────────────────────────────────────────────────────────────

async def test_search_patients(session: AsyncSession) -> None:
    session.add(_make_patient("UniqueSearchName"))
    await session.commit()
    results = await PatientService(session).search("UniqueSearch")
    assert len(results) == 1
    assert results[0].name == "UniqueSearchName"


async def test_search_patients_no_match(session: AsyncSession) -> None:
    results = await PatientService(session).search("ZZZ_NO_MATCH")
    assert results == []


# ── create ─────────────────────────────────────────────────────────────────────

async def test_create_patient(session: AsyncSession) -> None:
    data = PatientCreate(name="Created", dob="1985-05-05")
    result = await PatientService(session).create(data)
    assert result.name == "Created"
    assert result.dob == "1985-05-05"


# ── update ─────────────────────────────────────────────────────────────────────

async def test_update_patient(session: AsyncSession) -> None:
    p = _make_patient("Before")
    session.add(p)
    await session.commit()
    result = await PatientService(session).update(p.id, PatientUpdate(name="After", patient_allergies="penicillin"))
    assert result.name == "After"
    assert result.patient_allergies == "penicillin"


# ── soft_delete ─────────────────────────────────────────────────────────────────

async def test_soft_delete_patient(session: AsyncSession) -> None:
    p = _make_patient("Delete Me")
    session.add(p)
    await session.commit()
    result = await PatientService(session).soft_delete(p.id)
    assert result.is_deleted is True
    # Subsequent get should 404 (soft-deleted)
    try:
        await PatientService(session).get(p.id)
        assert False, "should have raised"
    except NotFoundError:
        pass


async def test_soft_delete_patient_not_found(session: AsyncSession) -> None:
    try:
        await PatientService(session).soft_delete(99999)
        assert False, "should have raised"
    except NotFoundError:
        pass


# ── bind_insurance ─────────────────────────────────────────────────────────────

async def test_bind_insurance(session: AsyncSession) -> None:
    p = _make_patient("Insured")
    session.add(p)
    await session.commit()
    plan = await InsuranceRepository(session).create(
        InsurancePlanCreate(plan_name="PPO", carrier_id="C1", copay_tier="T1", copay_amount=Decimal("10.00"))
    )
    result = await PatientService(session).bind_insurance(p.id, plan.id)
    assert result.insurance_plan_id == plan.id


async def test_bind_insurance_plan_not_found(session: AsyncSession) -> None:
    p = _make_patient("NoPlan")
    session.add(p)
    await session.commit()
    try:
        await PatientService(session).bind_insurance(p.id, 99999)
        assert False, "should have raised"
    except NotFoundError:
        pass


async def test_bind_insurance_inactive_plan(session: AsyncSession) -> None:
    p = _make_patient("InactivePlan")
    session.add(p)
    await session.commit()
    plan = await InsuranceRepository(session).create(
        InsurancePlanCreate(plan_name="Inactive", carrier_id="C2", copay_tier="T2", copay_amount=Decimal("0"))
    )
    # Deactivate the plan
    plan.active = 0
    await session.commit()
    try:
        await PatientService(session).bind_insurance(p.id, plan.id)
        assert False, "should have raised"
    except NotFoundError:
        pass


# ── members ────────────────────────────────────────────────────────────────────

async def test_members_for_patient(session: AsyncSession) -> None:
    p = _make_patient("Parent")
    session.add(p)
    await session.commit()
    session.add(MembersGroup(patient_id=p.id, member_name="Child", relationship="child", dob="2010-01-01", created_at="2026-08-22T00:00:00Z"))
    await session.commit()
    results = await PatientService(session).members(p.id)
    assert len(results) == 1
    assert results[0].member_name == "Child"


async def test_members_for_missing_patient(session: AsyncSession) -> None:
    try:
        await PatientService(session).members(99999)
        assert False, "should have raised"
    except NotFoundError:
        pass


# ── history ────────────────────────────────────────────────────────────────────

async def test_history_with_dispenses(session: AsyncSession) -> None:
    p = _make_patient("Hist Patient")
    session.add(p)
    await session.commit()
    receipt = Receipt(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_amount=Decimal("30.00"),
        payment_method="Cash",
        patient_id=p.id,
        server_created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        created_by="test",
    )
    session.add(receipt)
    await session.flush()
    from app.core.models import Dispense, DispenseItem
    dispense = Dispense(
        patient_id=p.id,
        receipt_id=receipt.id,
        product_name="Aspirin",
        ndc_code="123",
        sig_code="BID",
        quantity=30,
        fill_date="2026-08-22",
        price_at_time=Decimal("10.00"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="",
        cashier="test",
        client_tx_id="hist-001",
        server_created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    session.add(dispense)
    await session.flush()
    session.add(DispenseItem(
        dispense_id=dispense.id,
        lot_number="L1",
        expiration_date="2026-12-31",
        quantity=30,
        awp_at_time=Decimal("10.00"),
        mac_at_time=Decimal("5.00"),
    ))
    await session.commit()
    entries = await PatientService(session).history(p.id, limit=100)
    assert len(entries) == 1
    assert entries[0].dispense_ids == [dispense.id]


async def test_history_patient_not_found(session: AsyncSession) -> None:
    try:
        await PatientService(session).history(99999)
        assert False, "should have raised"
    except NotFoundError:
        pass
