"""Demo mode sample data seeder (Task 4 Step 4.7).

Seeds a small, realistic dataset for sales demos: 5 medicines, 3 patients,
2 prescriptions, 1 open shift with 5 receipts, and 1 workers'-comp claim.

Design rules (mirroring seed_service):
  * Idempotent — every row carries a stable demo marker (name / barcode /
    client_tx_id / claim_number / opened_by) and is skipped if already present.
  * Marker-scoped teardown — ``clear_demo_data`` deletes only rows carrying
    demo markers, never user data.
  * No migrations — the ``demo_mode`` SystemSetting is seeded as ``false`` by
    ``seed_default_settings`` and toggled at runtime via the admin routes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    EPCSPrescription,
    Patient,
    Prescriber,
    Product,
    Receipt,
    ReceiptItem,
    Shift,
    SystemSetting,
    WorkersCompClaim,
)
from app.shared.logging_config import get_logger

logger = get_logger("seed_demo_data")

DEMO_MODE_KEY = "demo_mode"
_DEMO_PRESCRIBER_NPI = "1000000009"  # demo marker (NPIs starting 1 are fake by spec)
_DEMO_USER = "demo"

_DEMO_PRODUCTS: list[tuple[str, str, str, str, str, str]] = [
    # name, price, barcode, category, strength, form
    ("Demo Aspirin 100mg", "4.99", "400000000001", "Analgesic", "100mg", "Tablet"),
    ("Demo Ibuprofen 200mg", "6.49", "400000000002", "NSAID", "200mg", "Tablet"),
    ("Demo Amoxicillin 500mg", "12.75", "400000000003", "Antibiotic", "500mg", "Capsule"),
    ("Demo Zolpidem 5mg", "18.20", "400000000004", "Hypnotic", "5mg", "Tablet"),
    ("Demo Tramadol 50mg", "15.30", "400000000005", "Analgesic", "50mg", "Capsule"),
]

_DEMO_PATIENTS: list[tuple[str, str, str, str, str]] = [
    # name, dob, sex, phone, insurance
    ("Demo Patient A", "1980-01-15", "F", "555-0101", "Demo Health Plan"),
    ("Demo Patient B", "1972-06-30", "M", "555-0102", ""),
    ("Demo Patient C", "1995-11-02", "F", "555-0103", "Demo Comp Insurance"),
]

_DEMO_RX: list[tuple[str, str, int, int]] = [
    # product_name, schedule, quantity, days_supply (sig fixed below)
    ("Demo Zolpidem 5mg", "C-IV", 30, 30),
    ("Demo Tramadol 50mg", "C-IV", 20, 10),
]

_DEMO_RECEIPT_COUNT = 5
_DEMO_WC_CLAIM_NUMBER = "DEMO-WC-0001"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def is_demo_mode(session: AsyncSession) -> bool:
    setting = await session.get(SystemSetting, DEMO_MODE_KEY)
    if setting is None:
        return False
    return (setting.value or b"").decode("utf-8").strip().lower() == "true"


async def set_demo_mode(session: AsyncSession, enabled: bool) -> None:
    value = ("true" if enabled else "false").encode("utf-8")
    setting = await session.get(SystemSetting, DEMO_MODE_KEY)
    if setting is None:
        session.add(SystemSetting(key=DEMO_MODE_KEY, value=value))
    else:
        setting.value = value
    await session.commit()


async def seed_demo_data(session: AsyncSession) -> dict[str, int]:
    """Idempotently seed demo rows; returns per-type counts of rows ADDED."""
    counts: dict[str, int] = {
        "products": 0,
        "patients": 0,
        "prescriptions": 0,
        "receipts": 0,
        "wc_claims": 0,
    }
    now = _now_iso()

    # -- Products -------------------------------------------------------------
    product_names = [p[0] for p in _DEMO_PRODUCTS]
    have = set(
        (
            await session.execute(select(Product.name).where(Product.name.in_(product_names)))
        ).scalars().all()
    )
    products: dict[str, Product] = {}
    for name, price, barcode, category, strength, form in _DEMO_PRODUCTS:
        if name in have:
            continue
        product = Product(
            name=name,
            price=Decimal(price),
            manufacturer_barcode=barcode,
            internal_unique_barcode=f"DEMO-{barcode}",
            status="In Stock",
            category=category,
            strength=strength,
            form=form,
            vendor_name="Demo Vendor",
        )
        session.add(product)
        products[name] = product
        counts["products"] += 1
    await session.flush()

    # -- Patients -------------------------------------------------------------
    patient_names = [p[0] for p in _DEMO_PATIENTS]
    have_patients = set(
        (await session.execute(select(Patient.name).where(Patient.name.in_(patient_names))))
        .scalars()
        .all()
    )
    patients: list[Patient] = []
    for name, dob, sex, phone, insurance in _DEMO_PATIENTS:
        if name in have_patients:
            existing = (
                await session.execute(select(Patient).where(Patient.name == name))
            ).scalar_one()
            patients.append(existing)
            continue
        patient = Patient(
            name=name,
            dob=dob,
            sex=sex,
            contact_phone=phone,
            insurance_provider=insurance,
            created_at=now,
        )
        session.add(patient)
        patients.append(patient)
        counts["patients"] += 1
    await session.flush()
    if not patients:
        patients = list(
            (
                await session.execute(select(Patient).where(Patient.name.in_(patient_names)))
            ).scalars().all()
        )

    # -- Prescriber (shared master record; kept on teardown) ------------------
    prescriber = (
        await session.execute(select(Prescriber).where(Prescriber.npi == _DEMO_PRESCRIBER_NPI))
    ).scalar_one_or_none()
    if prescriber is None:
        prescriber = Prescriber(
            first_name="Demo",
            last_name="Physician",
            npi=_DEMO_PRESCRIBER_NPI,
            phone="555-0100",
        )
        session.add(prescriber)
        await session.flush()

    # -- Prescriptions (EPCS table; user id 1 = seeded admin) -----------------
    rx_names = [r[0] for r in _DEMO_RX]
    have_rx = set(
        (
            await session.execute(
                select(EPCSPrescription.product_name).where(
                    EPCSPrescription.product_name.in_(rx_names)
                )
            )
        ).scalars().all()
    )
    for product_name, schedule, quantity, days_supply in _DEMO_RX:
        if product_name in have_rx:
            continue
        session.add(
            EPCSPrescription(
                patient_id=patients[0].id,
                prescriber_id=prescriber.id,
                product_name=product_name,
                schedule=schedule,
                quantity=quantity,
                days_supply=days_supply,
                sig_code="1 tab PO qHS",
                refills=0,
                status="PENDING_SIGNATURE",
                created_at=now,
                updated_at=now,
                created_by=1,
            )
        )
        counts["prescriptions"] += 1

    # -- Open shift + receipts (client_tx_id "demo-N" is the teardown marker) --
    shift = (
        await session.execute(
            select(Shift).where(Shift.status == "open", Shift.opened_by == _DEMO_USER)
        )
    ).scalar_one_or_none()
    if shift is None:
        shift = Shift(
            opening_float=Decimal("100.00"),
            opened_at=now,
            status="open",
            opened_by=_DEMO_USER,
        )
        session.add(shift)
        await session.flush()

    have_receipts = set(
        (
            await session.execute(
                select(Receipt.client_tx_id).where(Receipt.client_tx_id.like("demo-%"))
            )
        ).scalars().all()
    )
    price_by_name = {name: Decimal(price) for name, price, *_ in _DEMO_PRODUCTS}
    for i in range(_DEMO_RECEIPT_COUNT):
        tx_id = f"demo-{i}"
        if tx_id in have_receipts:
            continue
        item_name = product_names[i % len(product_names)]
        total = price_by_name.get(item_name, Decimal("0"))
        ts = (datetime.now(timezone.utc) - timedelta(days=i)).isoformat()
        receipt = Receipt(
            timestamp=ts,
            total_amount=total,
            payment_method="Cash" if i % 2 == 0 else "Card",
            patient_id=patients[i % len(patients)].id,
            server_created_at=ts,
            created_by=_DEMO_USER,
            cashier_attribution=_DEMO_USER,
            client_tx_id=tx_id,
            sale_type="OTC",
        )
        session.add(receipt)
        await session.flush()
        session.add(
            ReceiptItem(
                receipt_id=receipt.id,
                product_name=item_name,
                quantity=1,
                price_at_time=total,
                internal_barcode=f"DEMO-40000000000{(i % len(_DEMO_PRODUCTS)) + 1}",
                vendor="Demo Vendor",
                expiry_date="",
            )
        )
        counts["receipts"] += 1

    # -- Workers' comp claim --------------------------------------------------
    wc_exists = (
        await session.execute(
            select(WorkersCompClaim.id).where(
                WorkersCompClaim.claim_number == _DEMO_WC_CLAIM_NUMBER
            )
        )
    ).scalar_one_or_none()
    if wc_exists is None:
        session.add(
            WorkersCompClaim(
                patient_id=patients[0].id,
                claim_number=_DEMO_WC_CLAIM_NUMBER,
                carrier_name="Demo Comp Insurance",
                injury_date="2026-08-15",
                injury_description="Lower back strain (demo)",
                employer_name="Demo Employer LLC",
                status="open",
                total_charges=Decimal("150.00"),
                insurance_paid=Decimal("100.00"),
                patient_responsibility=Decimal("50.00"),
                created_at=now,
                updated_at=now,
            )
        )
        counts["wc_claims"] += 1

    await session.commit()
    logger.info("seed_demo_data_complete", **counts)
    return counts


async def clear_demo_data(session: AsyncSession) -> dict[str, int]:
    """Delete only demo-marked rows (children before parents)."""
    counts: dict[str, int] = {}
    try:
        demo_receipt_ids = select(Receipt.id).where(Receipt.client_tx_id.like("demo-%"))
        result = await session.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id.in_(demo_receipt_ids)))
        counts["receipt_items"] = result.rowcount or 0
        result = await session.execute(delete(Receipt).where(Receipt.client_tx_id.like("demo-%")))
        counts["receipts"] = result.rowcount or 0
        result = await session.execute(
            delete(EPCSPrescription).where(EPCSPrescription.product_name.like("Demo %"))
        )
        counts["prescriptions"] = result.rowcount or 0
        result = await session.execute(
            delete(WorkersCompClaim).where(WorkersCompClaim.claim_number.like("DEMO-%"))
        )
        counts["wc_claims"] = result.rowcount or 0
        result = await session.execute(delete(Product).where(Product.name.like("Demo %")))
        counts["products"] = result.rowcount or 0
        result = await session.execute(delete(Patient).where(Patient.name.like("Demo Patient %")))
        counts["patients"] = result.rowcount or 0
        await session.commit()
        logger.info("clear_demo_data_complete", **counts)
        return counts
    except SQLAlchemyError as exc:
        logger.error("clear_demo_data_db_error", error=str(exc))
        await session.rollback()
        raise


async def reset_demo_data(session: AsyncSession) -> dict[str, Any]:
    """Clear and re-seed demo data; leaves demo_mode ON."""
    await clear_demo_data(session)
    counts = await seed_demo_data(session)
    await set_demo_mode(session, True)
    return {"demo_mode": True, "counts": counts}
