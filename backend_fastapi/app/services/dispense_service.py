"""Prescription dispense workflow: patient-linked FIFO deduction with idempotency.

Mirrors ``PosService.process_checkout`` exactly (decision: reuse the commit pattern —
sorted per-drug locks + a single ``session.begin()`` txn) so dispenses and POS sales
share the same concurrency-control invariants (C risk #3). Key additions over raw
checkout: patient + insurance validation, SIG-code resolution, lot-level consumption
rows, a thermal-label audit hook, and ``client_tx_id`` idempotency (#11).
"""
from __future__ import annotations

import asyncio
import secrets
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
    PriceCodeRepository,
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
from app.services.drug_db import check_allergy_match, check_drug_interactions, check_duplicate_therapy
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
    DispenseUpdate,
    TransferResult,
    VoidResult,
)

logger = get_logger("dispense")

# #11 (LAN idempotency): a retried submit is only a duplicate within this window.
_IDEMPOTENCY_WINDOW_SECONDS = 5 * 60

# Rx number format: RX-YYYYMMDD-XXXX (date + 4 random hex chars)
_RX_COUNTER: int = 0


def _generate_rx_number() -> str:
    """Generate a unique Rx number: RX-YYYYMMDD-XXXX."""
    global _RX_COUNTER  # noqa: PLW0603
    _RX_COUNTER += 1
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    rand_part = secrets.token_hex(2).upper()
    return f"RX-{today}-{rand_part}{_RX_COUNTER:02d}"


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
        price_code_repo = PriceCodeRepository(self.session)
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
                    read = await self._build_read(existing, items)
                    # Re-check allergies against the patient's current profile (idempotent hit).
                    existing_patient = await patient_repo.get(existing.patient_id)
                    if existing_patient is not None:
                        read.allergy_flags = check_allergy_match(
                            payload.product_name, existing_patient.patient_allergies
                        )
                    return read

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

                # ── Phase 3: PriceCode-based pricing with AWP/MAC/WAC ──────
                price_code = None
                if payload.price_code:
                    price_code = await price_code_repo.get_by_code(payload.price_code)

                # Fetch lot-level AWP/MAC/WAC from consumed lots
                lot_awp: Optional[Decimal] = None
                lot_mac: Optional[Decimal] = None
                lot_wac: Optional[Decimal] = None
                if consumed:
                    from app.core.models import InventoryExtended
                    first_lot_id = cast(Optional[int], consumed[0].get("lot_id"))
                    if first_lot_id is not None:
                        lot = await self.session.get(InventoryExtended, first_lot_id)
                        if lot is not None:
                            lot_awp = lot.awp
                            lot_mac = lot.mac
                            lot_wac = lot.wac

                # Determine base cost: prefer lot-level, fallback to product catalog
                base_cost = lot_wac or lot_mac or lot_awp or product.wholesale_price or product.price

                # Apply PriceCode formula: base * (markup_pct/100) + dispensing_fee, clamped
                if price_code and price_code.markup_pct:
                    computed = base_cost * (price_code.markup_pct / Decimal("100")) + price_code.dispensing_fee
                elif price_code and price_code.cost_factor_pct:
                    computed = base_cost * (price_code.cost_factor_pct / Decimal("100")) + price_code.dispensing_fee
                else:
                    computed = base_cost + (price_code.dispensing_fee if price_code else Decimal("0"))

                # Clamp to min/max
                if price_code:
                    if price_code.min_price and computed < price_code.min_price:
                        computed = price_code.min_price
                    if price_code.max_price and computed > price_code.max_price:
                        computed = price_code.max_price

                unit = _round2(computed) if price_code else product.price
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
                    price_at_time=unit,
                    insurance_copay=_round2(payload.insurance_copay),
                    insurance_amount=_round2(payload.insurance_amount),
                    internal_barcode=product.internal_unique_barcode,
                    cashier=user.username,
                    client_tx_id=payload.client_tx_id,
                    server_created_at=server_ts,
                    rx_number=_generate_rx_number(),
                    refill_count=0,
                    refills_authorized=payload.refills_authorized,
                    last_fill_date=payload.fill_date,
                    prescriber_id=payload.prescriber_id,
                    days_supply=payload.days_supply,
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
                            awp_at_time=lot_awp or product.price,
                            mac_at_time=lot_mac or product.wholesale_price,
                            wac_at_time=lot_wac,
                        )
                    )

                # Financial + sold-item ledger lines (reuse POS shapes).
                self.session.add(
                    ReceiptItem(
                        receipt_id=receipt.id,
                        product_name=payload.product_name,
                        quantity=payload.quantity,
                        price_at_time=unit,
                        internal_barcode=product.internal_unique_barcode,
                        vendor=product.vendor_name,
                        expiry_date=product.expiry_date,
                    )
                )
                self.session.add(
                    SoldItem(
                        item_name=payload.product_name,
                        price=unit,
                        manufacturer_barcode=product.manufacturer_barcode,
                        internal_barcode=product.internal_unique_barcode,
                        timestamp_of_sale=server_ts,
                        vendor_name=product.vendor_name,
                    )
                )

                items = await self._items_for(dispense.id)
                read = await self._build_read(dispense, items)
                read.allergy_flags = check_allergy_match(
                    payload.product_name, patient.patient_allergies
                )
                # Phase 4: DUR — drug interactions + duplicate therapy
                active_meds = await self._get_active_medications(
                    patient.id, exclude_product=payload.product_name
                )
                ddi_alerts = check_drug_interactions(payload.product_name, active_meds)
                read.ddi_alerts = [a.to_dict() for a in ddi_alerts]
                read.duplicate_therapy = check_duplicate_therapy(
                    payload.product_name, active_meds
                )
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

    async def _get_active_medications(self, patient_id: int, exclude_product: str = "") -> list[str]:
        """Fetch distinct product names from recent dispenses (last 90 days) for DUR."""
        from datetime import date, timedelta

        cutoff = (date.today() - timedelta(days=90)).isoformat()
        stmt = (
            select(Dispense.product_name)
            .where(Dispense.patient_id == patient_id)
            .where(Dispense.fill_date >= cutoff)
            .where(Dispense.product_name != exclude_product)
            .distinct()
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all() if row[0]]

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
            rx_number=dispense.rx_number,
            refill_count=dispense.refill_count,
            refills_authorized=dispense.refills_authorized,
            last_fill_date=dispense.last_fill_date,
            prescriber_id=dispense.prescriber_id,
            days_supply=dispense.days_supply,
        )

    async def get(self, dispense_id: int) -> DispenseRead:
        dispense = await DispenseRepository(self.session).get(dispense_id)
        if dispense is None:
            raise NotFoundError("Dispense", dispense_id)
        items = await self._items_for(dispense.id)
        return await self._build_read(dispense, items)

    async def get_by_rx_number(self, rx_number: str) -> DispenseRead:
        """Return the most recent dispense for a given Rx number."""
        dispense = await DispenseRepository(self.session).get_by_rx_number(rx_number)
        if dispense is None:
            raise NotFoundError("Dispense", rx_number)
        items = await self._items_for(dispense.id)
        return await self._build_read(dispense, items)

    async def get_fills_by_rx_number(self, rx_number: str) -> list[DispenseRead]:
        """Return all fills sharing the same Rx number (fill history)."""
        dispenses = await DispenseRepository(self.session).get_fills_by_rx_number(rx_number)
        result: list[DispenseRead] = []
        for d in dispenses:
            items = await self._items_for(d.id)
            result.append(await self._build_read(d, items))
        return result

    async def update_dispense(
        self, dispense_id: int, payload: DispenseUpdate, user: CurrentUser
    ) -> DispenseRead:
        """Edit an existing dispense (sig, quantity, days supply, refills, prescriber)."""
        async with self.session.begin():
            dispense = await DispenseRepository(self.session).get(dispense_id)
            if dispense is None:
                raise NotFoundError("Dispense", dispense_id)

            if payload.sig_code is not None:
                dispense.sig_code = payload.sig_code
            if payload.quantity is not None:
                dispense.quantity = payload.quantity
            if payload.days_supply is not None:
                dispense.days_supply = payload.days_supply
            if payload.refills_authorized is not None:
                dispense.refills_authorized = payload.refills_authorized
            if payload.prescriber_id is not None:
                dispense.prescriber_id = payload.prescriber_id
            if payload.fill_date is not None:
                dispense.fill_date = payload.fill_date
            self.session.add(dispense)

            await write_audit(
                self.session,
                "dispense.update",
                subject_type="dispense",
                subject_id=dispense.id,
                details=f"rx={dispense.rx_number} edits={payload.model_dump(exclude_unset=True)}",
                category="dispense",
                user=user,
            )

        items = await self._items_for(dispense.id)
        return await self._build_read(dispense, items)

    async def void_dispense(
        self, dispense_id: int, reason: str, user: CurrentUser
    ) -> VoidResult:
        """Void/reverse a dispense — restock inventory and mark as voided."""
        async with self.session.begin():
            dispense = await DispenseRepository(self.session).get(dispense_id)
            if dispense is None:
                raise NotFoundError("Dispense", dispense_id)

            # Restock: add back the dispensed quantity to inventory
            restocked = 0
            await InventoryService(self.session).return_stock(dispense.product_name, dispense.quantity)
            restocked = dispense.quantity

            # Mark dispense as voided by setting a sentinel rx_number
            dispense.rx_number = f"VOID-{dispense.rx_number or dispense.id}"
            dispense.cashier = f"{user.username}|VOIDED"
            self.session.add(dispense)

            await write_audit(
                self.session,
                "dispense.void",
                subject_type="dispense",
                subject_id=dispense.id,
                details=f"rx={dispense.rx_number} reason={reason} restocked={restocked}",
                category="dispense",
                user=user,
            )

        return VoidResult(
            dispense_id=dispense.id,
            rx_number=dispense.rx_number,
            voided=True,
            restocked_quantity=restocked,
            reason=reason,
        )

    async def transfer_dispense(
        self, dispense_id: int, pharmacy_name: str, pharmacy_phone: str,
        transfer_type: str, reason: str, user: CurrentUser,
    ) -> TransferResult:
        """Transfer a prescription to/from another pharmacy."""
        async with self.session.begin():
            dispense = await DispenseRepository(self.session).get(dispense_id)
            if dispense is None:
                raise NotFoundError("Dispense", dispense_id)

            # Mark dispense as transferred
            prefix = "XFER-OUT" if transfer_type == "outgoing" else "XFER-IN"
            dispense.rx_number = f"{prefix}-{dispense.rx_number or dispense.id}"
            dispense.cashier = f"{user.username}|TRANSFERRED"
            self.session.add(dispense)

            # If outgoing, restock inventory (drug leaving our pharmacy)
            restocked = 0
            if transfer_type == "outgoing":
                await InventoryService(self.session).return_stock(dispense.product_name, dispense.quantity)
                restocked = dispense.quantity

            await write_audit(
                self.session,
                "dispense.transfer",
                subject_type="dispense",
                subject_id=dispense.id,
                details=f"rx={dispense.rx_number} type={transfer_type} pharmacy={pharmacy_name} reason={reason}",
                category="dispense",
                user=user,
            )

        return TransferResult(
            dispense_id=dispense.id,
            rx_number=dispense.rx_number,
            transferred=True,
            transfer_type=transfer_type,
            pharmacy_name=pharmacy_name,
            pharmacy_phone=pharmacy_phone,
            reason=reason,
        )

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

    async def process_refill(
        self, dispense_id: int, payload: DispenseCreate, user: CurrentUser
    ) -> DispenseRead:
        """Process a refill of an existing dispense (creates new dispense with incremented refill_count)."""
        lot_locks: list[asyncio.Lock] = [await get_lock(f"refill-{dispense_id}")]
        for lock in lot_locks:
            await lock.acquire()
        try:
            async with self.session.begin():
                original = await DispenseRepository(self.session).get(dispense_id)
                if original is None:
                    raise NotFoundError("Dispense", dispense_id)

                # Check if refills are available
                if original.refill_count >= original.refills_authorized:
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"No refills remaining for Rx {original.rx_number} "
                               f"({original.refill_count}/{original.refills_authorized} used)",
                    )
                # Resolve patient
                patient_repo = PatientRepository(self.session)
                patient = await patient_repo.get_strict(original.patient_id)

                # Resolve product
                product_repo = ProductRepository(self.session)
                product = await product_repo.get_by_name(original.product_name)
                if product is None:
                    raise NotFoundError("Medicine", original.product_name)

                # Deduct stock
                inventory = InventoryService(self.session)
                consumed = await inventory.fifo_deduct(original.product_name, payload.quantity)

                # ── Phase 3: Lot-level pricing for refills ─────────────────
                lot_awp_r: Optional[Decimal] = None
                lot_mac_r: Optional[Decimal] = None
                lot_wac_r: Optional[Decimal] = None
                if consumed:
                    from app.core.models import InventoryExtended
                    first_lot_id = cast(Optional[int], consumed[0].get("lot_id"))
                    if first_lot_id is not None:
                        lot = await self.session.get(InventoryExtended, first_lot_id)
                        if lot is not None:
                            lot_awp_r = lot.awp
                            lot_mac_r = lot.mac
                            lot_wac_r = lot.wac

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
                    patient_id=original.patient_id,
                    server_created_at=server_ts,
                    created_by=user.username,
                    cashier_attribution=user.username,
                    client_tx_id=payload.client_tx_id,
                )
                self.session.add(receipt)
                await self.session.flush()

                # Create new dispense with incremented refill count
                dispense = Dispense(
                    patient_id=original.patient_id,
                    receipt_id=receipt.id,
                    product_name=original.product_name,
                    ndc_code=original.ndc_code,
                    sig_code=original.sig_code,
                    quantity=payload.quantity,
                    fill_date=payload.fill_date,
                    price_at_time=_round2(payload.price_at_time),
                    insurance_copay=_round2(payload.insurance_copay),
                    insurance_amount=_round2(payload.insurance_amount),
                    internal_barcode=product.internal_unique_barcode,
                    cashier=user.username,
                    client_tx_id=payload.client_tx_id,
                    server_created_at=server_ts,
                    rx_number=original.rx_number,  # Same Rx number
                    refill_count=original.refill_count + 1,
                    refills_authorized=original.refills_authorized,
                    last_fill_date=payload.fill_date,
                    prescriber_id=original.prescriber_id,
                    days_supply=payload.days_supply or original.days_supply,
                )
                self.session.add(dispense)
                await self.session.flush()

                # Add dispense items
                for c in consumed:
                    self.session.add(
                        DispenseItem(
                            dispense_id=dispense.id,
                            lot_id=cast(Optional[int], c["lot_id"]),
                            lot_number=str(c["lot_number"] or ""),
                            expiration_date=str(c["expiry_date"] or ""),
                            quantity=cast(int, c["deducted"]),
                            awp_at_time=lot_awp_r or product.price,
                            mac_at_time=lot_mac_r or product.wholesale_price,
                            wac_at_time=lot_wac_r,
                        )
                    )

                # Financial + sold-item ledger lines
                self.session.add(
                    ReceiptItem(
                        receipt_id=receipt.id,
                        product_name=original.product_name,
                        quantity=payload.quantity,
                        price_at_time=_round2(payload.price_at_time),
                        internal_barcode=product.internal_unique_barcode,
                        vendor=product.vendor_name,
                        expiry_date=product.expiry_date,
                    )
                )
                self.session.add(
                    SoldItem(
                        item_name=original.product_name,
                        price=_round2(payload.price_at_time),
                        manufacturer_barcode=product.manufacturer_barcode,
                        internal_barcode=product.internal_unique_barcode,
                        timestamp_of_sale=server_ts,
                        vendor_name=product.vendor_name,
                    )
                )

                items = await self._items_for(dispense.id)
                read = await self._build_read(dispense, items)
                # Phase 4: Refill safety — allergy + DUR checks
                read.allergy_flags = check_allergy_match(
                    original.product_name, patient.patient_allergies
                )
                active_meds = await self._get_active_medications(
                    patient.id, exclude_product=original.product_name
                )
                ddi_alerts = check_drug_interactions(original.product_name, active_meds)
                read.ddi_alerts = [a.to_dict() for a in ddi_alerts]
                read.duplicate_therapy = check_duplicate_therapy(
                    original.product_name, active_meds
                )

                # Audit
                await write_audit(
                    self.session,
                    "dispense.refill",
                    subject_type="dispense",
                    subject_id=dispense.id,
                    details=(
                        f"patient={patient.name} drug={original.product_name} "
                        f"qty={payload.quantity} rx={original.rx_number} "
                        f"refill={dispense.refill_count}/{dispense.refills_authorized}"
                    ),
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
