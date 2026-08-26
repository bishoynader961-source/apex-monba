"""M98-B — Clinical Decision Support: allergy alerts + DDI checking.

Unit tests for ``app.services.drug_db`` (no DB needed) + integration tests
verifying that ``DispenseService.process_dispense`` populates ``allergy_flags``
on the returned ``DispenseRead`` response.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import InventoryExtended, Product
from app.services.dispense_service import DispenseService
from app.services.drug_db import (
    check_allergy_match,
    extract_ingredient,
    parse_allergies,
)
from app.shared.schemas import DispenseCreate, PatientRead

# ── Unit tests: drug_db.py ──────────────────────────────────────────────────


def test_parse_allergies_basic() -> None:
    assert parse_allergies("Penicillin, Aspirin, Codeine") == ["penicillin", "aspirin", "codeine"]


def test_parse_allergies_semicolons_and_and() -> None:
    assert parse_allergies("Warfarin; Aspirin and Ibuprofen") == ["warfarin", "aspirin", "ibuprofen"]


def test_parse_allergies_slash_separator() -> None:
    assert parse_allergies("Penicillin/Sulfa") == ["penicillin", "sulfa"]


def test_parse_allergies_empty() -> None:
    assert parse_allergies("") == []
    assert parse_allergies("   ") == []


def test_parse_allergies_dedupes() -> None:
    assert parse_allergies("Aspirin, aspirin, ASPIRIN") == ["aspirin"]


def test_extract_ingredient_known_drug() -> None:
    assert extract_ingredient("Amoxicillin 500mg") == "amoxicillin"
    assert extract_ingredient("Aspirin 81mg") == "aspirin"
    assert extract_ingredient("Warfarin 5mg") == "warfarin"


def test_extract_ingredient_unknown_drug_fallback() -> None:
    assert extract_ingredient("NovelDrug 10mg") == "noveldrug"


def test_extract_ingredient_empty() -> None:
    assert extract_ingredient("") == ""


def test_check_allergy_match_direct() -> None:
    """Patient allergic to the dispensed drug's ingredient."""
    flags = check_allergy_match("Amoxicillin 500mg", "Penicillin, Amoxicillin")
    assert any("Allergy alert" in f and "amoxicillin" in f for f in flags)


def test_check_allergy_match_no_allergies() -> None:
    """Empty allergy list → no flags."""
    assert check_allergy_match("Amoxicillin 500mg", "") == []
    assert check_allergy_match("Amoxicillin 500mg", "   ") == []


def test_check_allergy_match_no_overlap() -> None:
    """Allergies that don't match the dispensed drug → no flags."""
    flags = check_allergy_match("Amoxicillin 500mg", "Penicillin, Sulfa")
    assert flags == []


def test_check_allergy_match_ddi_forward() -> None:
    """Dispensed drug has DDI with a patient-listed drug."""
    flags = check_allergy_match("Aspirin 500mg", "Warfarin")
    assert any("Drug interaction alert" in f and "warfarin" in f.lower() for f in flags)


def test_check_allergy_match_ddi_reverse() -> None:
    """Patient-listed drug has DDI with the dispensed drug's ingredient."""
    flags = check_allergy_match("Warfarin 5mg", "Aspirin")
    assert any("Drug interaction alert" in f and "aspirin" in f.lower() for f in flags)


def test_check_allergy_match_no_false_positive_ddi() -> None:
    """Amoxicillin has no DDI with warfarin."""
    flags = check_allergy_match("Amoxicillin 500mg", "Warfarin")
    assert flags == []


def test_patient_read_allergy_alerts_computed_field() -> None:
    """PatientRead.allergy_alerts is parsed from patient_allergies."""
    p = SimpleNamespace(
        id=1, name="Test", dob="1990-01-01", address="", driver_license="",
        sex="", employer_id="", contact_phone="", email="",
        insurance_provider="", policy_number="", group_number="",
        insurance_plan_id=None, patient_allergies="Penicillin, Aspirin",
        comments="", created_at=None, is_deleted=0,
    )
    read = PatientRead.model_validate(p)
    assert read.allergy_alerts == ["penicillin", "aspirin"]


def test_patient_read_allergy_alerts_empty() -> None:
    p = SimpleNamespace(
        id=1, name="Test", dob="1990-01-01", address="", driver_license="",
        sex="", employer_id="", contact_phone="", email="",
        insurance_provider="", policy_number="", group_number="",
        insurance_plan_id=None, patient_allergies="",
        comments="", created_at=None, is_deleted=0,
    )
    read = PatientRead.model_validate(p)
    assert read.allergy_alerts == []


# ── Integration tests: DispenseService with allergy flags ────────────────────


def _make_user(username: str = "pharmacist") -> object:
    return type("User", (), {"username": username, "role": "pharmacist", "permissions": []})()


@pytest.fixture
async def aspirin_stocked(session: AsyncSession) -> None:
    """Create product 'Aspirin 500mg' with inventory."""
    product = Product(name="Aspirin 500mg", price=Decimal("8.50"))
    session.add(product)
    await session.flush()
    session.add(InventoryExtended(
        drug_name="Aspirin 500mg",
        lot_number="ASP-001",
        expiration_date="2027-01-01",
        on_hand=10,
        supplier="PharmaCorp",
        ndc_code="00069-0002-01",
    ))
    await session.commit()


@pytest.fixture
async def amoxicillin_stocked(session: AsyncSession) -> None:
    """Create product 'Amoxicillin 500mg' with inventory (mirrors test_dispense.py)."""
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


async def test_dispense_allergy_flag_set(
    session: AsyncSession, amoxicillin_stocked: None,
) -> None:
    """Dispense a drug the patient is allergic to → allergy_flags populated (non-blocking)."""
    from app.core.models import Patient

    patient = Patient(name="Allergy Test", dob="1990-01-01", patient_allergies="amoxicillin")
    session.add(patient)
    await session.commit()

    payload = DispenseCreate(
        patient_id=patient.id,
        product_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("12.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-A3F9B2",
        cashier="dr_test",
        client_tx_id="cds-tx-001",
    )
    result = await DispenseService(session).process_dispense(payload, _make_user())
    assert len(result.allergy_flags) > 0
    assert any("Allergy alert" in f and "amoxicillin" in f for f in result.allergy_flags)


async def test_dispense_ddi_flag_set(
    session: AsyncSession, aspirin_stocked: None,
) -> None:
    """Dispense aspirin to a patient listing warfarin → DDI flag populated."""
    from app.core.models import Patient

    patient = Patient(name="DDI Test", dob="1990-01-01", patient_allergies="warfarin")
    session.add(patient)
    await session.commit()

    payload = DispenseCreate(
        patient_id=patient.id,
        product_name="Aspirin 500mg",
        ndc_code="00069-0002-01",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("8.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-B2C1D8",
        cashier="dr_test",
        client_tx_id="cds-tx-002",
    )
    result = await DispenseService(session).process_dispense(payload, _make_user())
    assert len(result.allergy_flags) > 0
    assert any("Drug interaction alert" in f and "warfarin" in f.lower() for f in result.allergy_flags)


async def test_dispense_no_flags_when_no_allergy(
    session: AsyncSession, amoxicillin_stocked: None,
) -> None:
    """Dispense to a patient with no allergies → empty allergy_flags."""
    from app.core.models import Patient

    patient = Patient(name="Clean Test", dob="1990-01-01", patient_allergies="")
    session.add(patient)
    await session.commit()

    payload = DispenseCreate(
        patient_id=patient.id,
        product_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("12.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-A3F9B2",
        cashier="dr_test",
        client_tx_id="cds-tx-003",
    )
    result = await DispenseService(session).process_dispense(payload, _make_user())
    assert result.allergy_flags == []


async def test_dispense_idempotent_keeps_allergy_flags(
    session: AsyncSession, amoxicillin_stocked: None,
) -> None:
    """Retrying a dispense (same client_tx_id) returns the cached result with
    fresh allergy_flags recomputed from the patient's current profile."""
    from app.core.models import Patient

    patient = Patient(name="Retry Test", dob="1990-01-01", patient_allergies="amoxicillin")
    session.add(patient)
    await session.commit()

    payload = DispenseCreate(
        patient_id=patient.id,
        product_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        sig_code="BID",
        quantity=1,
        fill_date="2026-08-22",
        price_at_time=Decimal("12.50"),
        insurance_copay=Decimal("0"),
        insurance_amount=Decimal("0"),
        internal_barcode="MED-A3F9B2",
        cashier="dr_test",
        client_tx_id="cds-tx-004",
    )
    svc = DispenseService(session)
    first = await svc.process_dispense(payload, _make_user())
    assert len(first.allergy_flags) > 0

    # Retry with the same client_tx_id → idempotency hit, flags recomputed.
    second = await svc.process_dispense(payload, _make_user())
    assert second.id == first.id
    assert len(second.allergy_flags) > 0
