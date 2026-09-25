"""POS checkout: atomic receipt creation with FIFO deduction and concurrency control.

Concurrency (R1): each drug is guarded by a shared, class-level ``asyncio.Lock``
acquired in a deterministic (sorted) order so concurrent checkouts serialize only on
the drugs they touch. The entire receipt + stock mutation runs in a single
``session.begin()`` transaction.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import DrawerMovement, Patient, Receipt, ReceiptItem, Refund, Shift, SoldItem, SystemSetting
from app.core.lock_manager import get_lock
from app.core.repositories import AuditRepository, ProductRepository, SyncRepository
from app.services.inventory_service import InventoryService
from app.shared.config import settings
from app.shared.exceptions import AppException, ForbiddenError, NotFoundError
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    CheckoutItemRead,
    CheckoutRequest,
    CheckoutResult,
    CurrentUser,
    DrawerMovementCreate,
    DrawerMovementRead,
    EODReceiptLine,
    EODReceiptSummary,
    EODSummary,
    ReceiptPrintResponse,
    ReceiptRead,
    ReceiptItemRead,
    RefundRead,
    RefundRequest,
    SalesReport,
    ShiftCloseRequest,
    ShiftCloseResult,
    ShiftOpenRequest,
    ShiftPreviewResult,
    ShiftRead,
    VoidItemRequest,
    VoidItemResult,
)

logger = get_logger("pos")

_TAX_RATE = Decimal(str(settings.tax_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
_CENTS = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _skew_seconds(client_ts: Optional[str], server_dt: datetime) -> Optional[float]:
    """Absolute client→server clock delta in seconds, or None if unparseable."""
    if not client_ts:
        return None
    try:
        client_dt = datetime.fromisoformat(client_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return abs((server_dt - client_dt).total_seconds())


@dataclass
class _LineResult:
    product_name: str
    quantity: int
    unit_price: Decimal
    net_total: Decimal
    tax: Decimal


class PosService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_checkout(
        self,
        payload: CheckoutRequest,
        user: CurrentUser,
    ) -> CheckoutResult:
        aggregated: dict[str, int] = {}
        for line in payload.line_items:
            aggregated[line.product_name] = aggregated.get(line.product_name, 0) + line.quantity
        names = sorted(aggregated)

        # Privileged checkout inputs are permission-gated (docs in contracts.ts):
        # price overrides, tax exemption, and split payments. Admin (role_id 1 / "*")
        # bypasses via has_permission.
        def _has(perm: str) -> bool:
            return user.role_id == 1 or "*" in user.permissions or perm in user.permissions

        if payload.price_overrides and not _has("pos.price_override"):
            raise ForbiddenError("Price override requires pos.price_override permission")
        if payload.tax_exempt and not _has("pos.checkout"):
            raise ForbiddenError("Tax exemption requires manager approval")
        if payload.payments and not _has("pos.checkout"):
            raise ForbiddenError("Split payments require pos.checkout permission")

        acquired: list[asyncio.Lock] = []
        try:
            for name in names:
                lock = await get_lock(name)
                await lock.acquire()
                acquired.append(lock)

            async with self.session.begin():
                product_repo = ProductRepository(self.session)
                audit_repo = AuditRepository(self.session)
                inventory = InventoryService(self.session)

                net_raw = Decimal("0")
                tax_raw = Decimal("0")
                results: list[_LineResult] = []
                consumed_rows: list[dict[str, object]] = []

                for name in names:
                    qty = aggregated[name]
                    product = await product_repo.get_by_name(name)
                    if product is None:
                        raise NotFoundError("Medicine", name)
                    consumed = await inventory.fifo_deduct(name, qty)
                    consumed_rows.extend(consumed)
                    # Price override: use caller-supplied price when present.
                    overrides = payload.price_overrides or {}
                    unit = overrides.get(name, product.price)
                    net_line = Decimal(qty) * unit
                    tax_line = net_line * _TAX_RATE
                    net_raw += net_line
                    tax_raw += tax_line
                    results.append(
                        _LineResult(
                            product_name=name,
                            quantity=qty,
                            unit_price=unit,
                            net_total=_round2(net_line),
                            tax=_round2(tax_line),
                        )
                    )

                net_total = _round2(net_raw)

                # Discount: applied before tax (percentage or flat dollar).
                discount_total = Decimal("0")
                if payload.discount_type and payload.discount_value is not None and payload.discount_value > 0:
                    if payload.discount_type == "%":
                        discount_total = _round2(net_total * payload.discount_value / Decimal("100"))
                        if discount_total > net_total:
                            discount_total = net_total
                    elif payload.discount_type == "$":
                        discount_total = _round2(min(payload.discount_value, net_total))

                taxable = net_total - discount_total
                # Money contract: always emit 2-dp decimals, even for a zero tax leg.
                tax_total = Decimal("0.00") if payload.tax_exempt else _round2(taxable * _TAX_RATE)
                total = _round2(taxable + tax_total)

                # Split payment: validate amounts sum ≥ total.
                payment_method = payload.payment_method
                if payload.payments:
                    split_sum = sum(p.amount for p in payload.payments)
                    if split_sum < total:
                        raise AppException(
                            f"Split payments sum {split_sum} is less than total {total}",
                            status_code=400,
                            error_code="split_insufficient",
                        )
                    parts = [f"{p.method} {_round2(p.amount)}" for p in payload.payments]
                    payment_method = "Split: " + " + ".join(parts)

                server_dt = datetime.now(timezone.utc)
                skew = _skew_seconds(payload.client_timestamp, server_dt)
                receipt = Receipt(
                    timestamp=server_dt.isoformat(timespec="seconds"),
                    total_amount=total,
                    payment_method=payment_method,
                    patient_id=payload.patient_id,
                    server_created_at=server_dt.isoformat(timespec="seconds"),
                    ts_skew_confidence=skew,
                    created_by=user.username,
                    cashier_attribution=user.username,
                )
                self.session.add(receipt)
                await self.session.flush()
                # Receipt number is derived from the immutable row id + year (no extra column).
                receipt_number = f"RCP-{date.today().year}-{receipt.id:06d}"

                now = receipt.timestamp
                for r in results:
                    product = await product_repo.get_by_name(r.product_name)
                    assert product is not None  # resolved above
                    self.session.add(
                        ReceiptItem(
                            receipt_id=receipt.id,
                            product_name=r.product_name,
                            quantity=r.quantity,
                            price_at_time=r.unit_price,
                            internal_barcode=product.internal_unique_barcode,
                            vendor=product.vendor_name,
                            expiry_date=product.expiry_date,
                        )
                    )
                    self.session.add(
                        SoldItem(
                            item_name=r.product_name,
                            price=r.unit_price,
                            manufacturer_barcode=product.manufacturer_barcode,
                            internal_barcode=product.internal_unique_barcode,
                            timestamp_of_sale=now,
                            vendor_name=product.vendor_name,
                        )
                    )

                await audit_repo.log(
                    action="pos.checkout",
                    details=f"receipt={receipt_number} items={len(results)} total={total}"
                    + (" tax_exempt" if payload.tax_exempt else ""),
                    category="sales",
                    subject_type="receipt",
                    subject_id=receipt.id,
                    user_pin=user.username,
                    role=user.role,
                )

                # C.1: append to the terminal's local sync_outbox so the merge-sync
                # hub can reconcile cross-terminal stock. Fire-and-forget: a sync
                # logging failure must NEVER roll back or block the sale.
                if settings.multi_terminal:
                    try:
                        sync_payload = json.dumps(
                            {
                                "client_txn_id": receipt_number,
                                "items": [
                                    {"product_name": r.product_name, "quantity": r.quantity}
                                    for r in results
                                ],
                                "total_amount": str(total),
                                "device_id": settings.device_id,
                            }
                        )
                        await SyncRepository(self.session).append_outbox(
                            settings.device_id, receipt.id, receipt_number, sync_payload
                        )
                    except Exception:  # noqa: BLE001 - sync must not fail the checkout
                        logger.warning("sync_outbox_append_failed", receipt=receipt_number)

                return CheckoutResult(
                    receipt_id=receipt.id,
                    receipt_number=receipt_number,
                    payment_method=receipt.payment_method,
                    net_total=net_total,
                    tax_total=tax_total,
                    total_amount=total,
                    discount_total=discount_total,
                    server_created_at=receipt.server_created_at,
                    ts_skew_confidence=receipt.ts_skew_confidence,
                    cashier_attribution=receipt.cashier_attribution,
                    items=[
                        CheckoutItemRead(
                            product_name=r.product_name,
                            quantity=r.quantity,
                            unit_price=r.unit_price,
                            net_total=r.net_total,
                            tax=r.tax,
                        )
                        for r in results
                    ],
                )
        finally:
            for lock in reversed(acquired):
                if lock.locked():
                    lock.release()

    async def record_drawer_movement(
        self, payload: DrawerMovementCreate, user: CurrentUser
    ) -> DrawerMovementRead:
        """Persist a cash-drawer movement with running balance (Concern 1)."""
        server_dt = datetime.now(timezone.utc)
        prior = (
            await self.session.execute(
                select(func.coalesce(func.sum(DrawerMovement.amount), 0)).select_from(
                    DrawerMovement
                )
            )
        ).scalar() or Decimal("0")
        new_balance = prior + payload.amount
        movement = DrawerMovement(
            cashier=payload.cashier or user.username,
            amount=payload.amount,
            reason=payload.reason,
            prior_balance=prior,
            new_balance=new_balance,
            server_created_at=server_dt.isoformat(timespec="seconds"),
            ts_skew_confidence=_skew_seconds(payload.client_timestamp, server_dt),
            created_by=user.username,
            client_created_at=payload.client_timestamp,
        )
        self.session.add(movement)
        await self.session.commit()
        return DrawerMovementRead.model_validate(movement)

    async def open_shift(self, payload: ShiftOpenRequest, user: CurrentUser) -> ShiftRead:
        """Open a cash-drawer shift with the counted opening float (A1)."""
        server_dt = datetime.now(timezone.utc)
        shift = Shift(
            opening_float=payload.opening_float,
            opened_at=server_dt.isoformat(timespec="seconds"),
            status="open",
            opened_by=user.username,
        )
        self.session.add(shift)
        await self.session.commit()
        return ShiftRead.model_validate(shift)

    async def close_shift(self, payload: ShiftCloseRequest) -> ShiftCloseResult:
        """Close a shift against a physically counted till and compute the variance.

        ``expected = opening_float + cash_sales + float_add - drops - payouts - pickups``
        where the cash flows are those recorded since the shift opened.
        """
        shift = await self.session.get(Shift, payload.shift_id)
        if shift is None:
            raise NotFoundError("Shift", str(payload.shift_id))
        if shift.status == "closed":
            raise AppException("Shift already closed", status_code=409, error_code="shift_closed")

        opened_at = shift.opened_at
        cash_sales = (
            await self.session.execute(
                select(func.coalesce(func.sum(Receipt.total_amount), 0)).where(
                    Receipt.payment_method == "Cash",
                    Receipt.server_created_at >= opened_at,
                )
            )
        ).scalar() or Decimal("0")
        movement_sum = (
            await self.session.execute(
                select(func.coalesce(func.sum(DrawerMovement.amount), 0)).where(
                    DrawerMovement.server_created_at >= opened_at,
                    DrawerMovement.reason.in_(["float_add", "cash_drop", "paid_out", "pickup"]),
                )
            )
        ).scalar() or Decimal("0")

        expected = _round2(shift.opening_float + cash_sales + movement_sum)
        variance = _round2(payload.counted_cash - expected)

        server_dt = datetime.now(timezone.utc)
        shift.status = "closed"
        shift.closed_at = server_dt.isoformat(timespec="seconds")
        await self.session.commit()
        return ShiftCloseResult(
            shift_id=shift.id,
            opening_float=_round2(shift.opening_float),
            expected_cash=expected,
            counted_cash=_round2(payload.counted_cash),
            variance=variance,
            status="closed",
        )

    async def preview_shift(self, shift_id: int) -> ShiftPreviewResult:
        """Compute the expected till for an open shift without closing it (A1)."""
        shift = await self.session.get(Shift, shift_id)
        if shift is None:
            raise NotFoundError("Shift", str(shift_id))

        opened_at = shift.opened_at
        cash_sales = (
            await self.session.execute(
                select(func.coalesce(func.sum(Receipt.total_amount), 0)).where(
                    Receipt.payment_method == "Cash",
                    Receipt.server_created_at >= opened_at,
                )
            )
        ).scalar() or Decimal("0")
        movement_sum = (
            await self.session.execute(
                select(func.coalesce(func.sum(DrawerMovement.amount), 0)).where(
                    DrawerMovement.server_created_at >= opened_at,
                    DrawerMovement.reason.in_(["float_add", "cash_drop", "paid_out", "pickup"]),
                )
            )
        ).scalar() or Decimal("0")

        expected = _round2(shift.opening_float + cash_sales + movement_sum)
        return ShiftPreviewResult(
            shift_id=shift.id,
            opening_float=_round2(shift.opening_float),
            expected_cash=expected,
            status=shift.status,
        )

    async def refund(self, payload: RefundRequest, user: CurrentUser) -> RefundRead:
        """Reverse a sale: restock inventory (FEFO), record a refund ledger entry.

        A receipt may be refunded at most once (``refunds.receipt_id`` is UNIQUE).
        """
        receipt = await self.session.get(Receipt, payload.receipt_id)
        if receipt is None:
            raise NotFoundError("Receipt", str(payload.receipt_id))
        existing = (
            await self.session.execute(
                select(Refund).where(Refund.receipt_id == payload.receipt_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise AppException(
                "Receipt already refunded", status_code=409, error_code="already_refunded"
            )

        items = (
            await self.session.execute(
                select(ReceiptItem).where(ReceiptItem.receipt_id == payload.receipt_id)
            )
        ).scalars().all()
        inventory = InventoryService(self.session)
        for item in items:
            await inventory.return_stock(item.product_name, item.quantity)

        server_dt = datetime.now(timezone.utc).isoformat(timespec="seconds")
        refund = Refund(
            receipt_id=receipt.id,
            total_amount=_round2(-receipt.total_amount),
            reason=payload.reason,
            cashier=user.username,
            server_created_at=server_dt,
        )
        self.session.add(refund)
        # Negative ledger receipt so financial reports net the reversal correctly.
        ledger = Receipt(
            timestamp=server_dt,
            total_amount=_round2(-receipt.total_amount),
            payment_method="Refund",
            server_created_at=server_dt,
            created_by=user.username,
            cashier_attribution=user.username,
        )
        self.session.add(ledger)
        await self.session.flush()
        await AuditRepository(self.session).log(
            action="pos.refund",
            details=f"receipt={payload.receipt_id} amount={-receipt.total_amount}",
            category="refund",
            subject_type="receipt",
            subject_id=payload.receipt_id,
            user_pin=user.username,
            role=user.role,
        )
        await self.session.commit()
        return RefundRead.model_validate(refund)

    async def void_item(self, payload: VoidItemRequest, user: CurrentUser) -> VoidItemResult:
        """Void a single receipt item: restock inventory and create a partial refund.

        The receipt item is deleted and a refund ledger entry is created for the
        item's line total. The parent receipt's total is *not* mutated (it remains
        as an audit trail); the negative ledger entry nets it in reports.
        """
        item = await self.session.get(ReceiptItem, payload.receipt_item_id)
        if item is None:
            raise NotFoundError("ReceiptItem", str(payload.receipt_item_id))
        receipt = await self.session.get(Receipt, item.receipt_id)
        if receipt is None:
            raise NotFoundError("Receipt", str(item.receipt_id))
        # Restock inventory
        inventory = InventoryService(self.session)
        await inventory.return_stock(item.product_name, item.quantity)
        # Calculate refund amount for this line
        refund_amount = _round2(Decimal(str(item.quantity)) * item.price_at_time)
        # Delete the receipt item
        await self.session.delete(item)
        # Create a partial refund ledger entry
        server_dt = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ledger = Receipt(
            timestamp=server_dt,
            total_amount=_round2(-refund_amount),
            payment_method="Void",
            server_created_at=server_dt,
            created_by=user.username,
            cashier_attribution=user.username,
        )
        self.session.add(ledger)
        await self.session.flush()
        await AuditRepository(self.session).log(
            action="pos.void_item",
            details=f"receipt={item.receipt_id} item={payload.receipt_item_id} product={item.product_name} qty={item.quantity} amount={refund_amount}",
            category="void",
            subject_type="receipt_item",
            subject_id=payload.receipt_item_id,
            user_pin=user.username,
            role=user.role,
        )
        await self.session.commit()
        return VoidItemResult(
            receipt_id=item.receipt_id,
            restocked_product=item.product_name,
            quantity_restocked=item.quantity,
            refund_amount=refund_amount,
        )

    async def sales_report(self) -> SalesReport:
        """Aggregated sales + refunds for the reporting view (B5)."""
        rows = (
            await self.session.execute(select(Receipt))
        ).scalars().all()
        by_method: dict[str, Decimal] = {}
        gross = Decimal("0")
        count = 0
        for r in rows:
            if r.total_amount < 0:
                continue  # ledger reversal rows are netted via refunds below
            count += 1
            gross += r.total_amount
            by_method[r.payment_method] = by_method.get(r.payment_method, Decimal("0")) + r.total_amount
        refunds = (
            await self.session.execute(select(func.coalesce(func.sum(Refund.total_amount), 0)))
        ).scalar() or Decimal("0")
        net = _round2(gross + refunds)
        return SalesReport(
            receipt_count=count,
            gross_revenue=_round2(gross),
            refund_total=_round2(refunds),
            net_revenue=net,
            by_payment_method={k: _round2(v) for k, v in by_method.items()},
        )

    async def eod_summary(self, target_date: str | None = None) -> EODSummary:
        """End-of-Day summary for *target_date* (default: today UTC)."""
        if target_date is None:
            target_date = date.today().isoformat()
        # Fetch all receipts, filter by date prefix.
        result = await self.session.execute(select(Receipt))
        all_receipts = result.scalars().all()
        day_receipts = [r for r in all_receipts if r.timestamp and r.timestamp[:10] == target_date]
        by_method: dict[str, Decimal] = {}
        total = Decimal("0")
        items_sold = 0
        receipt_summaries: list[EODReceiptSummary] = []
        for r in day_receipts:
            if r.total_amount < 0:
                continue
            total += r.total_amount
            by_method[r.payment_method] = by_method.get(r.payment_method, Decimal("0")) + r.total_amount
            # Fetch items for this receipt.
            items_result = await self.session.execute(
                select(ReceiptItem).where(ReceiptItem.receipt_id == r.id)
            )
            items = items_result.scalars().all()
            lines: list[EODReceiptLine] = []
            for i in items:
                items_sold += i.quantity
                lines.append(EODReceiptLine(
                    product_name=i.product_name,
                    quantity=i.quantity,
                    price_at_time=i.price_at_time,
                ))
            try:
                year = datetime.fromisoformat(r.timestamp).year
            except (ValueError, TypeError):
                year = datetime.now(timezone.utc).year
            receipt_summaries.append(EODReceiptSummary(
                receipt_id=r.id,
                receipt_number=f"RCP-{year}-{r.id:06d}",
                timestamp=r.timestamp,
                total_amount=r.total_amount,
                payment_method=r.payment_method,
                items=lines,
            ))
        return EODSummary(
            date=target_date,
            total_revenue=_round2(total),
            transaction_count=len(receipt_summaries),
            items_sold=items_sold,
            by_payment_method={k: _round2(v) for k, v in by_method.items()},
            receipts=receipt_summaries,
        )

    # ── Receipt History ─────────────────────────────────────────────────────

    async def recent_receipts(self, limit: int = 50) -> list[ReceiptRead]:
        """Return the last *limit* receipts (newest first) with line items."""
        result = await self.session.execute(
            select(Receipt).order_by(Receipt.id.desc()).limit(limit)
        )
        receipts = result.scalars().all()
        out: list[ReceiptRead] = []
        for r in receipts:
            items_result = await self.session.execute(
                select(ReceiptItem).where(ReceiptItem.receipt_id == r.id)
            )
            items = items_result.scalars().all()
            out.append(
                ReceiptRead(
                    id=r.id,
                    receipt_number=f"RCP-{r.timestamp[:4]}-{r.id:06d}" if r.timestamp else f"RCP-{r.id:06d}",
                    timestamp=r.timestamp,
                    total_amount=r.total_amount,
                    payment_method=r.payment_method,
                    patient_id=r.patient_id,
                    server_created_at=r.server_created_at,
                    cashier_attribution=r.cashier_attribution,
                    client_tx_id=r.client_tx_id,
                    items=[
                        ReceiptItemRead(
                            id=i.id,
                            receipt_id=i.receipt_id,
                            product_name=i.product_name,
                            quantity=i.quantity,
                            price_at_time=i.price_at_time,
                            internal_barcode=i.internal_barcode,
                            vendor=i.vendor,
                            expiry_date=i.expiry_date,
                        )
                        for i in items
                    ],
                )
            )
        return out

    async def receipt_detail(self, receipt_id: int) -> ReceiptRead:
        """Return a single receipt with its line items."""
        r = await self.session.get(Receipt, receipt_id)
        if r is None:
            raise NotFoundError("Receipt", str(receipt_id))
        items_result = await self.session.execute(
            select(ReceiptItem).where(ReceiptItem.receipt_id == r.id)
        )
        items = items_result.scalars().all()
        return ReceiptRead(
            id=r.id,
            receipt_number=f"RCP-{r.timestamp[:4]}-{r.id:06d}" if r.timestamp else f"RCP-{r.id:06d}",
            timestamp=r.timestamp,
            total_amount=r.total_amount,
            payment_method=r.payment_method,
            patient_id=r.patient_id,
            server_created_at=r.server_created_at,
            cashier_attribution=r.cashier_attribution,
            client_tx_id=r.client_tx_id,
            items=[
                ReceiptItemRead(
                    id=i.id,
                    receipt_id=i.receipt_id,
                    product_name=i.product_name,
                    quantity=i.quantity,
                    price_at_time=i.price_at_time,
                    internal_barcode=i.internal_barcode,
                    vendor=i.vendor,
                    expiry_date=i.expiry_date,
                )
                for i in items
            ],
        )

    async def format_receipt_print(self, receipt_id: int) -> ReceiptPrintResponse:
        """Return a receipt in both thermal-text and browser-printable HTML formats."""
        detail = await self.receipt_detail(receipt_id)

        pharmacy_name = await self._get_setting("pharmacy_name") or "Pharmacy"
        pharmacy_address = await self._get_setting("pharmacy_address") or ""
        pharmacy_phone = await self._get_setting("pharmacy_phone") or ""

        patient_name = ""
        if detail.patient_id is not None:
            patient = await self.session.get(Patient, detail.patient_id)
            if patient is not None:
                patient_name = patient.name

        subtotal = sum((i.price_at_time * i.quantity for i in detail.items), Decimal("0"))
        tax_total = detail.total_amount - subtotal

        receipt_text = self._render_thermal(
            pharmacy_name, pharmacy_address, pharmacy_phone,
            detail, patient_name, subtotal, tax_total,
        )
        printable_html = self._render_printable_html(
            pharmacy_name, pharmacy_address, pharmacy_phone,
            detail, patient_name, subtotal, tax_total,
        )

        return ReceiptPrintResponse(
            receipt_id=detail.id,
            receipt_number=detail.receipt_number,
            receipt_text=receipt_text,
            printable_html=printable_html,
            items=detail.items,
            total_amount=detail.total_amount,
            payment_method=detail.payment_method,
            timestamp=detail.timestamp,
            cashier_attribution=detail.cashier_attribution,
            patient_name=patient_name or None,
            sale_type=detail.sale_type if hasattr(detail, "sale_type") else None,
            tax_total=tax_total,
            subtotal=subtotal,
        )

    async def _get_setting(self, key: str) -> str | None:
        """Read a SystemSetting value, decoding from stored bytes."""
        row = await self.session.get(SystemSetting, key)
        if row is None or row.value is None:
            return None
        return row.value.decode("utf-8")

    @staticmethod
    def _fmt_amount(value: Decimal) -> str:
        """Format a Decimal as a display string with up to 2 decimal places."""
        q = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{q}"

    @staticmethod
    def _render_thermal(
        pharmacy_name: str,
        pharmacy_address: str,
        pharmacy_phone: str,
        receipt: ReceiptRead,
        patient_name: str,
        subtotal: Decimal,
        tax_total: Decimal,
    ) -> str:
        """Build a 32-char-wide ESC/POS-compatible thermal text receipt."""
        w = 32
        lines: list[str] = []

        lines.append(pharmacy_name.center(w).rstrip())
        if pharmacy_address:
            for addr_line in pharmacy_address.split("\n"):
                if addr_line.strip():
                    lines.append(addr_line.strip().center(w).rstrip())
        if pharmacy_phone:
            lines.append(pharmacy_phone.strip().center(w).rstrip())
        lines.append("=" * w)

        lines.append(receipt.receipt_number.center(w).rstrip())
        lines.append(receipt.timestamp.center(w).rstrip())
        if receipt.cashier_attribution:
            lines.append(f"cashier: {receipt.cashier_attribution}".center(w).rstrip())
        if patient_name:
            lines.append(f"patient: {patient_name}".center(w).rstrip())
        lines.append("-" * w)

        for item in receipt.items:
            name = item.product_name[:24]
            qty_total = item.quantity * item.price_at_time
            lines.append(f"{name:<24}{item.quantity:>2}x")
            price_str = f"{PosService._fmt_amount(item.price_at_time):>7}"
            total_str = f"{PosService._fmt_amount(qty_total):>7}"
            lines.append(f"{price_str}{total_str:>11}")

        lines.append("-" * w)
        sub_str = f"{PosService._fmt_amount(subtotal):>10}"
        tax_str = f"{PosService._fmt_amount(tax_total):>10}"
        total_str = f"{PosService._fmt_amount(receipt.total_amount):>10}"
        lines.append(f"subtotal:{sub_str}")
        if tax_total != Decimal("0"):
            lines.append(f"tax:{tax_str}")
        lines.append(f"total:{total_str}")
        lines.append(f"Payment: {receipt.payment_method}".rstrip())
        lines.append("")
        lines.append("THANK YOU".center(w).rstrip())
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _render_printable_html(
        pharmacy_name: str,
        pharmacy_address: str,
        pharmacy_phone: str,
        receipt: ReceiptRead,
        patient_name: str,
        subtotal: Decimal,
        tax_total: Decimal,
    ) -> str:
        """Build a minimal HTML string for browser print preview."""
        import html

        esc = html.escape

        def fmt(v: Decimal) -> str:
            return esc(PosService._fmt_amount(v))

        parts: list[str] = [
            "<div class='pharmacy-receipt'>",
            f"<div class='pharmacy-header'><div class='pharmacy-name'>{esc(pharmacy_name)}</div>",
        ]
        if pharmacy_address:
            parts.append(f"<div class='pharmacy-address'>{esc(pharmacy_address)}</div>")
        if pharmacy_phone:
            parts.append(f"<div class='pharmacy-phone'>{esc(pharmacy_phone)}</div>")
        parts.append("</div>")

        parts.append("<div class='receipt-meta'>")
        parts.append(f"<div class='receipt-number'>{esc(receipt.receipt_number)}</div>")
        parts.append(f"<div class='receipt-date'>{esc(receipt.timestamp)}</div>")
        if receipt.cashier_attribution:
            parts.append(f"<div class='cashier'>Cashier: {esc(receipt.cashier_attribution)}</div>")
        if patient_name:
            parts.append(f"<div class='patient'>Patient: {esc(patient_name)}</div>")
        parts.append("</div>")

        parts.append("<table class='receipt-items'>")
        parts.append("<thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>")
        parts.append("<tbody>")
        for item in receipt.items:
            line_total = item.quantity * item.price_at_time
            parts.append(
                "<tr>"
                f"<td>{esc(item.product_name)}</td>"
                f"<td class='right'>{item.quantity}</td>"
                f"<td class='right'>{fmt(item.price_at_time)}</td>"
                f"<td class='right'>{fmt(line_total)}</td>"
                "</tr>"
            )
        parts.append("</tbody>")
        parts.append("</table>")

        parts.append("<div class='receipt-totals'>")
        parts.append(f"<div class='total-row'><span>Subtotal</span><span class='right'>{fmt(subtotal)}</span></div>")
        if tax_total != Decimal("0"):
            parts.append(f"<div class='total-row'><span>Tax</span><span class='right'>{fmt(tax_total)}</span></div>")
        parts.append(f"<div class='total-row grand-total'><span>Total</span><span class='right'>{fmt(receipt.total_amount)}</span></div>")
        parts.append(f"<div class='payment-method'>Payment: {esc(receipt.payment_method)}</div>")
        parts.append("</div>")

        parts.append("<div class='receipt-footer'>THANK YOU FOR YOUR BUSINESS</div>")
        parts.append("</div>")

        return "".join(parts)
