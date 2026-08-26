"""M7 — receipt_engine pure functions: ESC/POS thermal label/receipt byte streams."""
from __future__ import annotations

from decimal import Decimal

from app.services.receipt_engine import (
    BOLD_OFF,
    BOLD_ON,
    CENTER,
    CUT,
    DOUBLE_ON,
    LEFT,
    RESET,
    _code128,
    _text,
    _resolve_fill_date,
    compute_price_check,
    fill_date_default,
    format_thermal_label,
    format_receipt,
)


def test_format_thermal_label_contains_patient_and_drug() -> None:
    label = format_thermal_label(
        patient_name="Jane Doe",
        drug_name="Amoxicillin 500mg",
        ndc_code="00069-0168-24",
        quantity=30,
        sig_text="Take one tablet twice daily",
        lot_number="LOT123",
        expiry_date="2026-12-31",
        fill_date="2026-08-22",
    )
    assert isinstance(label, bytes)
    assert b"PRESCRIPTION" in label
    assert b"Jane Doe" in label
    assert b"Amoxicillin 500mg" in label
    assert b"00069-0168-24" in label
    assert b"30" in label
    assert b"LOT123" in label
    assert b"CUT" not in label  # cut marker is raw bytes, not literal text


def test_format_thermal_label_escpos_prefix() -> None:
    label = format_thermal_label(
        patient_name="Test",
        drug_name="Drug",
        ndc_code="123",
        quantity=1,
        sig_text="PO",
        lot_number="L1",
        expiry_date="2026-12-31",
        fill_date="2026-08-22",
    )
    assert label.startswith(RESET)
    assert CUT in label
    assert CENTER in label
    assert _code128("123") == b"\x1d" + b"k" + bytes([67]) + b"\x42" + b"123" + bytes([0])


def test_format_thermal_label_fill_date_default() -> None:
    label = format_thermal_label(
        patient_name="Test",
        drug_name="Drug",
        ndc_code="123",
        quantity=1,
        sig_text="PO",
        lot_number="L1",
        expiry_date="2026-12-31",
        fill_date=None,
    )
    default_date = fill_date_default()
    assert default_date in label.decode("utf-8", errors="replace")


def test_format_receipt_contains_fields() -> None:
    receipt = format_receipt(
        receipt_number="RCP-2026-000001",
        patient_name="John Smith",
        lines=[("Amoxicillin", Decimal("25.50"))],
        total=Decimal("29.07"),
        payment_method="Cash",
        cashier="dr_smith",
        server_created_at="2026-08-22T14:30:00Z",
    )
    assert isinstance(receipt, bytes)
    assert b"PHARMACY RECEIPT" in receipt
    assert b"John Smith" in receipt
    assert b"25.50" in receipt
    assert b"29.07" in receipt
    assert b"CASH" in receipt
    assert b"dr_smith" in receipt
    assert CUT in receipt


def test_format_receipt_no_server_ts_uses_default() -> None:
    receipt = format_receipt(
        receipt_number="RCP-2026-000002",
        patient_name="Jane",
        lines=[("Ibuprofen", Decimal("10.00"))],
        total=Decimal("11.40"),
        payment_method="Card",
        cashier="dr_jane",
    )
    default = _resolve_fill_date(None)
    assert default in receipt.decode("utf-8", errors="replace")


def test_fill_date_default_is_strict_yyyymmdd() -> None:
    d = fill_date_default()
    assert len(d) == 10
    assert d[4] == "-"
    assert d[7] == "-"


def test_compute_price_check_with_insurance_copay() -> None:
    copay = Decimal("15.00")
    result = compute_price_check(Decimal("100.00"), 3, copay)
    assert result == copay


def test_compute_price_check_without_insurance() -> None:
    result = compute_price_check(Decimal("33.20"), 3, Decimal("0"))
    assert result == Decimal("99.60")


def test_text_and_primitives() -> None:
    assert _text("hello") == b"hello\n"
    assert _text("") == b"\n"
    assert LEFT.startswith(b"\x1b")
    assert BOLD_ON.startswith(b"\x1b")
    assert DOUBLE_ON.startswith(b"\x1b")
    assert BOLD_OFF.startswith(b"\x1b")
