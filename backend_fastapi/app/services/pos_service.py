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

from app.core.models import DrawerMovement, Receipt, ReceiptItem, SoldItem
from app.core.lock_manager import get_lock
from app.core.repositories import AuditRepository, ProductRepository, SyncRepository
from app.services.inventory_service import InventoryService
from app.shared.config import settings
from app.shared.exceptions import NotFoundError
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    CheckoutItemRead,
    CheckoutRequest,
    CheckoutResult,
    CurrentUser,
    DrawerMovementCreate,
    DrawerMovementRead,
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
                    unit = product.price
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
                tax_total = _round2(tax_raw)
                total = _round2(net_total + tax_total)

                server_dt = datetime.now(timezone.utc)
                skew = _skew_seconds(payload.client_timestamp, server_dt)
                receipt = Receipt(
                    timestamp=server_dt.isoformat(timespec="seconds"),
                    total_amount=total,
                    payment_method=payload.payment_method,
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
                    details=f"receipt={receipt_number} items={len(results)} total={total}",
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
        async with self.session.begin():
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
            await self.session.flush()
            return DrawerMovementRead.model_validate(movement)
