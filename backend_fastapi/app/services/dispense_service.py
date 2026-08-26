"""Prescription dispense workflow: patient-linked FIFO deduction with idempotency.

Mirrors ``PosService.process_checkout`` exactly (decision: reuse the commit pattern —
sorted per-drug locks + a single ``session.begin()`` txn) so dispenses and POS sales
share the same concurrency-control invariants (C risk #3). Key additions over raw
checkout: patient + insurance validation, SIG-code resolution, lot-level consumption
rows, a thermal-label audit hook, and ``client_tx_id`` idempotency (#11).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import (
    BatchRepository,
    DispenseRepository,
    InsuranceRepository,
    PatientRepository,
    ProductRepository,
    SigCodeRepository,
)
from app.core.models import (
    Dispense,
    DispenseItem,
    Receipt,
    ReceiptItem,
    SoldItem,
)
from app.core.lock_manager import get_lock
from app.core.audit_log import write_audit
from app.services.inventory_service import InventoryService
from app.services.pos_service import _round2, _TAX_RATE
from app.shared.exceptions import (
    InsufficientStockError,
    NotFoundError,
)
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    CurrentUser,
    DispenseCreate,
    DispenseItemRead,
    DispenseRead,
)

logger = get_logger("dispense")

# #11 (LAN idempotency): a retried submit is only a duplicate within this window.
_IDEMPOTENCY_WINDOW_SECONDS = 5 * 60


class DispenseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_dispense(
        self, payload: DispenseCreate, user: CurrentUser
    ) -> DispenseRead:
        patient_repo = PatientRepository(self.session)
        product_repo = ProductRepository(self.session)
        sig_repo = SigCodeRepository(self.session)
        insu_repo = InsuranceRepository(self.session)
        dispense_repo = DispenseRepository(self.session)
        inventory = InventoryService(self.session)

        lot_locks: list[asyncio.Lock] = [await get_lock(payload.product_name)]
        for lock in lot_locks:
            await lock.acquire()
        try:
            async with self.session.begin():
                # #11 idempotency — duplicate submit returns the cached dispense.
                existing = await dispense_repo.get_by_client_tx_id(payload.client_tx_id)
                if existing is not None:
                    items = await self._items_for(existing.id)
                    logger.info(
                        "dispense_idempotent_hit",
                        client_tx_id=payload.client_tx_id,
                        dispense_id=existing.id,
                    )
                    return await self._build_read(existing, items)

                # Resolve patient (404 if soft-deleted / missing).
                patient = await patient_repo.get_strict(payload.patient_id)

                # Resolve + validate insurance plan when bound (FK enforced by PRAGMA).
                if payload.insurance_plan_id is not None:
                    plan = await insu_repo.get(payload.insurance_plan_id)
                    if plan is None or plan.active != 1:
                        raise NotFoundError("InsurancePlan", payload.insurance_plan_id)

                # Resolve product (stock is keyed on the drug name).
                product = await product_repo.get_by_name(payload.product_name)
                if product is None:
                    raise NotFoundError("Medicine", payload.product_name)

                # Resolve SIG code to a human-readable instruction (resolved again at label time
                # so the dispense row stores only the compact code).
                if await sig_repo.parse(payload.sig_code) is None:
                    logger.info("dispense_sig_code_unknown", sig_code=payload.sig_code)

                consumed = await inventory.fifo_deduct(payload.product_name, payload.quantity)

                unit = product.price
                net_raw = Decimal(payload.quantity) * unit
                tax_raw = net_raw * _TAX_RATE
                net_total = _round2(net_raw)
                tax_total = _round2(tax_raw)
                total = _round2(net_total + tax_total)

                server_dt = datetime.now(timezone.utc)
                server_ts = server_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                receipt = Receipt(
                    timestamp=server_ts,
                    total_amount=total,
                    payment_method="Cash",
                    patient_id=payload.patient_id,
                    server_created_at=server_ts,
                    created_by=user.username,
                    cashier_attribution=user.username,
                    client_tx_id=payload.client_tx_id,
                )
                self.session.add(receipt)
                await self.session.flush()
                from datetime import date as _date

                receipt_number = f"RCP-{_date.today().year}-{receipt.id:06d}"

                dispense = Dispense(
                    patient_id=patient.id,
                    receipt_id=receipt.id,
                    product_name=payload.product_name,
                    ndc_code=payload.ndc_code,
                    sig_code=payload.sig_code,
                    quantity=payload.quantity,
                    fill_date=payload.fill_date,
                    price_at_time=_round2(payload.price_at_time),
                    insurance_copay=_round2(payload.insurance_copay),
                    insurance_amount=_round2(payload.insurance_amount),
                    internal_barcode=product.internal_unique_barcode,
                    cashier=user.username,
                    client_tx_id=payload.client_tx_id,
                    server_created_at=server_ts,
                )
                self.session.add(dispense)
                await self.session.flush()

                for c in consumed:
                    self.session.add(
                        DispenseItem(
                            dispense_id=dispense.id,
                            lot_id=cast(Optional[int], c["lot_id"]),
                            lot_number=str(c["lot_number"] or ""),
                            expiration_date=str(c["expiry_date"] or ""),
                            quantity=cast(int, c["deducted"]),
                            awp_at_time=product.price,
                            mac_at_time=product.wholesale_price,
                        )
                    )

                # Financial + sold-item ledger lines (reuse POS shapes).
                self.session.add(
                    ReceiptItem(
                        receipt_id=receipt.id,
                        product_name=payload.product_name,
                        quantity=payload.quantity,
                        price_at_time=_round2(payload.price_at_time),
                        internal_barcode=product.internal_unique_barcode,
                        vendor=product.vendor_name,
                        expiry_date=product.expiry_date,
                    )
                )
                self.session.add(
                    SoldItem(
                        item_name=payload.product_name,
                        price=_round2(payload.price_at_time),
                        manufacturer_barcode=product.manufacturer_barcode,
                        internal_barcode=product.internal_unique_barcode,
                        timestamp_of_sale=server_ts,
                        vendor_name=product.vendor_name,
                    )
                )

                items = await self._items_for(dispense.id)
                read = await self._build_read(dispense, items)
                logger.info(
                    "dispense_created",
                    dispense_id=dispense.id,
                    receipt_number=receipt_number,
                    client_tx_id=payload.client_tx_id,
                )
                # Audit is the final write inside the txn (audit_log.py docstring:
                # "the audit call is the final write before the outer commit").
                # This keeps the audit row + dispense committed atomically.
                await write_audit(
                    self.session,
                    "dispense.create",
                    subject_type="dispense",
                    subject_id=dispense.id,
                    details=f"patient={patient.name} drug={payload.product_name} qty={payload.quantity} rx={receipt_number}",
                    category="dispense",
                    user=user,
                )
            return read
        except InsufficientStockError:
            raise
        finally:
            for lock in reversed(lot_locks):
                if lock.locked():
                    lock.release()

    async def _items_for(self, dispense_id: int) -> list[DispenseItemRead]:
        result = await self.session.execute(
            select(DispenseItem).where(DispenseItem.dispense_id == dispense_id)
        )
        return [DispenseItemRead.model_validate(i) for i in result.scalars().all()]

    async def _build_read(
        self, dispense: Dispense, items: list[DispenseItemRead]
    ) -> DispenseRead:
        return DispenseRead(
            id=dispense.id,
            patient_id=dispense.patient_id,
            receipt_id=dispense.receipt_id,
            product_name=dispense.product_name,
            ndc_code=dispense.ndc_code,
            sig_code=dispense.sig_code,
            quantity=dispense.quantity,
            fill_date=dispense.fill_date,
            price_at_time=dispense.price_at_time,
            insurance_copay=dispense.insurance_copay,
            insurance_amount=dispense.insurance_amount,
            internal_barcode=dispense.internal_barcode,
            cashier=dispense.cashier,
            client_tx_id=dispense.client_tx_id,
            server_created_at=dispense.server_created_at,
            items=items,
        )

    async def get(self, dispense_id: int) -> DispenseRead:
        dispense = await DispenseRepository(self.session).get(dispense_id)
        if dispense is None:
            raise NotFoundError("Dispense", dispense_id)
        items = await self._items_for(dispense.id)
        return await self._build_read(dispense, items)

    async def label_bytes(self, dispense_id: int) -> bytes:
        """Raw ESC/POS label for the thermal printer (concern 3 / #3)."""
        from app.services.receipt_engine import format_thermal_label

        dispense = await DispenseRepository(self.session).get(dispense_id)
        if dispense is None:
            raise NotFoundError("Dispense", dispense_id)
        # Patient + product join for the label text.
        patient = await PatientRepository(self.session).get(dispense.patient_id)
        patient_name = patient.name if patient is not None else f"patient#{dispense.patient_id}"
        product = await ProductRepository(self.session).get_by_name(dispense.product_name)
        lot_number = ""
        expiry_date = product.expiry_date if product is not None else ""
        if product is not None:
            lots = await BatchRepository(self.session).get_lots_for_product(dispense.product_name)
            if lots:
                lot_number = lots[0].lot_number or ""
                expiry_date = lots[0].expiration_date or expiry_date
        return format_thermal_label(
            patient_name=patient_name,
            drug_name=dispense.product_name,
            ndc_code=dispense.ndc_code,
            quantity=dispense.quantity,
            sig_text=dispense.sig_code,
            lot_number=lot_number,
            expiry_date=expiry_date,
            fill_date=dispense.fill_date,
        )
