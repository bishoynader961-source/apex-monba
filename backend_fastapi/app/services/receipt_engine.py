"""Receipt/label formatting: pure functions returning raw ESC/POS byte streams.

Per decision 4 / concern 3, these emit **raw control-byte payloads** (sharp vector
barcodes) rather than HTML/webview markup. The HTTP label endpoint returns the bytes
as ``application/octet-stream``; the Tauri sidecar forwards them straight to the
thermal printer (raw USB/Serial) — ``window.print()`` is never used (it rasterizes
barcodes and produces blurry/unscannable output on 58/80mm stock).

No I/O lives here: formatting only, so it is trivially unit-testable.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

# ── ESC/POS control primitives (real Epson/TM-T88V byte sequences) ───────────
ESC = b"\x1b"
GS = b"\x1d"
RESET = ESC + b"@"              # ESC @  — initialize
LF = b"\n"
CENTER = ESC + b"\x61" + b"\x01"   # ESC a 1 — center align
LEFT = ESC + b"\x61" + b"\x00"     # ESC a 0 — left align
BOLD_ON = ESC + b"\x45" + b"\x01"   # ESC E 1 — bold on
BOLD_OFF = ESC + b"\x45" + b"\x00"  # ESC E 0
DOUBLE_ON = ESC + b"\x21" + b"\x30"  # ESC ! 0x30 — double-height + width
DOUBLE_OFF = ESC + b"\x21" + b"\x00"
CUT = GS + b"\x56" + b"\x00"        # GS V 0 — full cut


def _text(line: str = "") -> bytes:
    return line.encode("utf-8", errors="replace") + LF


def _code128(data: str) -> bytes:
    """Code-128 (GS k, m=67) barcode for the NDC/Lot.

    The data is prefixed with ``\\x42`` (subset B) so the printer encodes the
    literal characters; the terminator ``\\x00`` ends the field.
    """
    payload = b"\x42" + data.encode("ascii", errors="replace") + b"\x00"
    return GS + b"k" + bytes([67]) + payload


def format_thermal_label(
    patient_name: str,
    drug_name: str,
    ndc_code: str,
    quantity: int,
    sig_text: str,
    lot_number: str,
    expiry_date: str,
    fill_date: Optional[str] = None,
    rx_number: Optional[str] = None,
) -> bytes:
    """Build a 58mm pharmacy label as raw ESC/POS bytes."""
    lines: list[bytes] = [RESET, CENTER, BOLD_ON, DOUBLE_ON]
    lines.append(_text("PRESCRIPTION"))
    lines.append(DOUBLE_OFF + BOLD_OFF + CENTER)
    lines.append(_text(f"PATIENT: {patient_name}"))
    if rx_number:
        lines.append(_text(f"RX #: {rx_number}"))
    lines.append(LF + LEFT + BOLD_ON)
    lines.append(_text(f"DRUG:  {drug_name}"))
    lines.append(BOLD_OFF)
    lines.append(_text(f"NDC:   {ndc_code}"))
    lines.append(_text(f"QTY:   {quantity}"))
    lines.append(_text(f"SIG:   {sig_text}"))
    lines.append(_text(f"LOT:   {lot_number}"))
    lines.append(_text(f"EXP:   {expiry_date}"))
    lines.append(_text(f"FILL:  {_resolve_fill_date(fill_date)}"))
    lines += [LF, CENTER]
    # Vector barcode of the NDC (scannable).
    lines.append(_code128(ndc_code or "0"))
    lines.append(LF + CENTER + _text("THANK YOU") + LF)
    lines.append(CUT)
    return b"".join(lines)


def format_receipt(
    receipt_number: str,
    patient_name: str,
    lines: list[tuple[str, Decimal]],
    total: Decimal,
    payment_method: str,
    cashier: str,
    server_created_at: Optional[str] = None,
) -> bytes:
    """Build a customer receipt as raw ESC/POS bytes."""
    buf: list[bytes] = [RESET, CENTER, BOLD_ON, DOUBLE_ON]
    buf.append(_text("PHARMACY RECEIPT"))
    buf.append(DOUBLE_OFF + BOLD_OFF + CENTER)
    buf.append(_text(receipt_number))
    buf.append(_text(f"DATE: {server_created_at or _resolve_fill_date(None)}"))
    buf.append(LF + LEFT)
    buf.append(_text(f"PATIENT: {patient_name}"))
    buf.append(_text("-" * 32))
    for name, price in lines:
        buf.append(_text(f"{name:<24}{price:>8}"))
    buf.append(_text("-" * 32))
    buf.append(BOLD_ON + _text(f"TOTAL {total:>22}") + BOLD_OFF)
    buf.append(_text(f"PAYMENT: {payment_method}"))
    buf.append(_text(f"CASHIER: {cashier}"))
    buf.append(LF + CENTER + _text("THANK YOU!") + LF + LF)
    buf.append(CUT)
    return b"".join(buf)


def fill_date_default() -> str:
    """Today's fill date, strict ``YYYY-MM-DD`` (#5 date precision)."""
    return date.today().isoformat()


def _resolve_fill_date(fill_date: Optional[str]) -> str:
    return fill_date or fill_date_default()


def compute_price_check(price_at_time: Decimal, quantity: int, insurance_copay: Decimal) -> Decimal:
    """Patient-payable amount: preferred copay, else full price * qty (#6 money)."""
    if insurance_copay > 0:
        return insurance_copay
    return (price_at_time * Decimal(quantity)).quantize(Decimal("0.01"))
