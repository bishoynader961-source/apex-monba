"""Rx Queue Service: manages prescription queue with status workflow.

Implements the legacy 3-tab queue (Processing / Rejects / Ready for Pickup)
with status transitions, bulk operations, and dashboard counts.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import ColumnElement, and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Dispense, Patient, Prescriber
from app.core.repositories import DispenseRepository
from app.shared.exceptions import NotFoundError, ValidationError
from app.shared.schemas import (
    CurrentUser,
    PaginatedRxQueue,
    RxBulkStatusRequest,
    RxBulkStatusResult,
    RxQueueCounts,
    RxQueueFilters,
    RxQueueItem,
    RxQueueItem,
    RxStatusTransition,
    RX_QUEUE_GROUPS,
    RX_STATUSES,
    RX_STATUS_TRANSITIONS,
)


class RxQueueService:
    """Service layer for Rx queue management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dispense_repo = DispenseRepository(session)

    async def get_queue(
        self,
        filters: RxQueueFilters,
        user: CurrentUser,
    ) -> PaginatedRxQueue:
        """Get paginated Rx queue with filters."""
        clause: ColumnElement[bool] = Dispense.rx_number.is_not(None)

        if filters.status:
            clause = and_(clause, Dispense.status == filters.status)
        if filters.prescriber_id:
            clause = and_(clause, Dispense.prescriber_id == filters.prescriber_id)
        if filters.patient_id:
            clause = and_(clause, Dispense.patient_id == filters.patient_id)
        if filters.start_date:
            clause = and_(clause, Dispense.fill_date >= filters.start_date)
        if filters.end_date:
            clause = and_(clause, Dispense.fill_date <= filters.end_date)

        # Total count
        total = await self.session.scalar(
            select(func.count()).select_from(Dispense).where(clause)
        ) or 0

        # Paginated results with joins for patient/prescriber names
        offset = (filters.page - 1) * filters.page_size
        stmt = (
            select(
                Dispense.id,
                Dispense.rx_number,
                Dispense.patient_id,
                Patient.name.label("patient_name"),
                Dispense.product_name,
                Dispense.ndc_code,
                Dispense.quantity,
                Dispense.fill_date,
                Dispense.status,
                Dispense.prescriber_id,
                Prescriber.first_name.label("prescriber_first"),
                Prescriber.last_name.label("prescriber_last"),
                Dispense.refill_count,
                Dispense.refills_authorized,
                Dispense.server_created_at,
            )
            .join(Patient, Patient.id == Dispense.patient_id)
            .outerjoin(Prescriber, Prescriber.id == Dispense.prescriber_id)
            .where(clause)
            .order_by(Dispense.server_created_at.desc().nullslast(), Dispense.id.desc())
            .limit(filters.page_size)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all()

        items = [
            RxQueueItem(
                id=row["id"],
                rx_number=row["rx_number"],
                patient_id=row["patient_id"],
                patient_name=row["patient_name"],
                product_name=row["product_name"],
                ndc_code=row["ndc_code"],
                quantity=row["quantity"],
                fill_date=row["fill_date"],
                status=row["status"] or "Pending",
                prescriber_id=row["prescriber_id"],
                prescriber_name=(
                    f"{row['prescriber_first']} {row['prescriber_last']}".strip()
                    if row["prescriber_first"] or row["prescriber_last"]
                    else None
                ),
                refill_count=row["refill_count"],
                refills_authorized=row["refills_authorized"],
                server_created_at=row["server_created_at"],
                fill_date_iso=row["fill_date"],
            )
            for row in rows
        ]

        return PaginatedRxQueue(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def get_counts_by_status(self) -> RxQueueCounts:
        """Get aggregated counts per queue group for dashboard badges."""
        # Processing: Pending + Billed + Verified
        processing = await self.session.scalar(
            select(func.count())
            .select_from(Dispense)
            .where(
                Dispense.rx_number.is_not(None),
                Dispense.status.in_(RX_QUEUE_GROUPS["processing"]),
            )
        ) or 0

        # Rejects
        rejects = await self.session.scalar(
            select(func.count())
            .select_from(Dispense)
            .where(
                Dispense.rx_number.is_not(None),
                Dispense.status.in_(RX_QUEUE_GROUPS["rejects"]),
            )
        ) or 0

        # Ready: Filled + Will Call
        ready = await self.session.scalar(
            select(func.count())
            .select_from(Dispense)
            .where(
                Dispense.rx_number.is_not(None),
                Dispense.status.in_(RX_QUEUE_GROUPS["ready"]),
            )
        ) or 0

        return RxQueueCounts(
            processing=processing,
            rejects=rejects,
            ready=ready,
        )

    async def transition_status(
        self,
        rx_id: int,
        new_status: str,
        user: CurrentUser,
    ) -> RxQueueItem:
        """Transition a single Rx to a new status with validation."""
        if new_status not in RX_STATUSES:
            raise ValidationError(f"Invalid status: {new_status}")

        dispense = await self.dispense_repo.get(rx_id)
        if dispense is None:
            raise NotFoundError("Dispense", rx_id)

        current_status = dispense.status or "Pending"
        if new_status not in RX_STATUS_TRANSITIONS.get(current_status, []):
            raise ValidationError(
                f"Invalid status transition: {current_status} -> {new_status}"
            )

        # Update dispense status
        async with self.session.begin():
            dispense.status = new_status
            if new_status == "Filled" and dispense.fill_date is None:
                dispense.fill_date = date.today().isoformat()
            if new_status == "Filled" and dispense.refill_count == 0:
                dispense.refill_count = 1
            elif new_status == "Filled":
                dispense.refill_count += 1

            # If rejecting, void the dispense
            if new_status == "Rejected":
                dispense.rx_number = f"REJECTED-{dispense.rx_number or dispense.id}"
                dispense.cashier = f"{user.username}|REJECTED"

            self.session.add(dispense)

            # Audit log
            from app.core.audit_log import write_audit
            await write_audit(
                self.session,
                "rx.status_transition",
                subject_type="dispense",
                subject_id=dispense.id,
                details=f"rx={dispense.rx_number} {current_status} -> {new_status}",
                category="dispense",
                user=user,
            )

        # Return updated item
        items = await self._items_for(dispense.id)
        return await self._build_read(dispense, items)

    async def bulk_transition(
        self,
        payload: RxBulkStatusRequest,
        user: CurrentUser,
    ) -> RxBulkStatusResult:
        """Bulk transition multiple Rx to a new status."""
        result = RxBulkStatusResult()

        for rx_id in payload.rx_ids:
            try:
                await self.transition_status(rx_id, payload.status, user)
                result.updated += 1
            except Exception as e:
                result.failed += 1
                result.errors.append(f"Rx {rx_id}: {str(e)}")

        return result

    async def _items_for(self, dispense_id: int) -> list[Any]:
        from app.core.models import DispenseItem
        from app.shared.schemas import DispenseItemRead

        result = await self.session.execute(
            select(DispenseItem).where(DispenseItem.dispense_id == dispense_id)
        )
        return [DispenseItemRead.model_validate(i) for i in result.scalars().all()]

    async def _build_read(self, dispense: Dispense, items: list) -> RxQueueItem:
        # Get patient name
        patient_result = await self.session.execute(
            select(Patient.name).where(Patient.id == dispense.patient_id)
        )
        patient_name = patient_result.scalar() or f"Patient #{dispense.patient_id}"

        # Get prescriber name
        prescriber_name = None
        if dispense.prescriber_id:
            prescriber_result = await self.session.execute(
                select(Prescriber.first_name, Prescriber.last_name).where(
                    Prescriber.id == dispense.prescriber_id
                )
            )
            prescriber = prescriber_result.first()
            if prescriber:
                prescriber_name = f"{prescriber.first_name} {prescriber.last_name}".strip()

        return RxQueueItem(
            id=dispense.id,
            rx_number=dispense.rx_number,
            patient_id=dispense.patient_id,
            patient_name=patient_name,
            product_name=dispense.product_name,
            ndc_code=dispense.ndc_code,
            quantity=dispense.quantity,
            fill_date=dispense.fill_date,
            status=dispense.status or "Pending",
            prescriber_id=dispense.prescriber_id,
            prescriber_name=prescriber_name,
            refill_count=dispense.refill_count,
            refills_authorized=dispense.refills_authorized,
            server_created_at=dispense.server_created_at,
            fill_date_iso=dispense.fill_date,
        )