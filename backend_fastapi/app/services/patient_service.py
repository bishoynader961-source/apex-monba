"""Patient profile CRUD + insurance binding + history aggregation (F4)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Dispense, Patient, Receipt
from app.core.repositories import (
    DispenseRepository,
    InsuranceRepository,
    MembersGroupRepository,
    PatientRepository,
)
from app.shared.exceptions import NotFoundError
from app.shared.schemas import (
    MembersGroupRead,
    PatientCreate,
    PatientHistoryEntry,
    PatientRead,
    PatientUpdate,
)


class PatientService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, patient_id: int) -> PatientRead:
        patient = await PatientRepository(self.session).get_strict(patient_id)
        return PatientRead.model_validate(patient)

    async def list_patients(
        self, page: int = 1, page_size: int = 50, q: Optional[str] = None
    ) -> tuple[list[PatientRead], int]:
        repo = PatientRepository(self.session)
        items, total = await repo.all(page=page, page_size=page_size, q=q)
        return [PatientRead.model_validate(p) for p in items], total

    async def search(self, q: str) -> list[PatientRead]:
        repo = PatientRepository(self.session)
        return [PatientRead.model_validate(p) for p in await repo.search(q)]

    async def create(self, data: PatientCreate) -> PatientRead:
        patient = await PatientRepository(self.session).create(data)
        return PatientRead.model_validate(patient)

    async def update(self, patient_id: int, data: PatientUpdate) -> PatientRead:
        repo = PatientRepository(self.session)
        patient = await repo.get_strict(patient_id)
        patient = await repo.update(patient, data)
        return PatientRead.model_validate(patient)

    async def soft_delete(self, patient_id: int) -> PatientRead:
        repo = PatientRepository(self.session)
        patient = await repo.soft_delete(patient_id)
        if patient is None:
            raise NotFoundError("Patient", patient_id)
        return PatientRead.model_validate(patient)

    async def bind_insurance(self, patient_id: int, plan_id: int) -> PatientRead:
        """Bind (or rebind) an insurance plan to a patient; validates the plan (T3)."""
        repo = PatientRepository(self.session)
        patient = await repo.get_strict(patient_id)
        plan = await InsuranceRepository(self.session).get(plan_id)
        if plan is None or plan.active != 1:
            raise NotFoundError("InsurancePlan", plan_id)
        patient.insurance_plan_id = plan.id
        await repo.update(patient, PatientUpdate())
        return PatientRead.model_validate(patient)

    async def members(self, patient_id: int) -> list[MembersGroupRead]:
        # get_strict enforces that a soft-deleted patient is 404, so dependents only
        # surface for active patients (#4 soft-delete referential integrity).
        await PatientRepository(self.session).get_strict(patient_id)
        members = await MembersGroupRepository(self.session).for_patient(patient_id)
        return [MembersGroupRead.model_validate(m) for m in members]

    async def history(self, patient_id: int, limit: int = 100) -> list[PatientHistoryEntry]:
        """Receipts + their dispatched IDs, joined on patient_id (#4 filters soft-delete)."""
        await PatientRepository(self.session).get_strict(patient_id)
        rows = (
            await self.session.execute(
                select(Receipt.id, Receipt.timestamp, Receipt.total_amount, Receipt.payment_method)
                .where(Receipt.patient_id == patient_id)
                .order_by(Receipt.server_created_at.desc(), Receipt.id.desc())
                .limit(limit)
            )
        ).fetchall()
        entries: list[PatientHistoryEntry] = []
        for r in rows:
            dispense_ids = [
                did
                for did in (
                    await self.session.execute(
                        select(Dispense.id).where(Dispense.receipt_id == r.id)
                    )
                ).scalars().all()
            ]
            try:
                year = datetime.fromisoformat(r.timestamp).year
            except (ValueError, TypeError):
                year = datetime.now(timezone.utc).year
            entries.append(
                PatientHistoryEntry(
                    receipt_id=r.id,
                    receipt_number=f"RCP-{year}-{r.id:06d}",
                    timestamp=r.timestamp,
                    total_amount=r.total_amount,
                    payment_method=r.payment_method,
                    dispense_ids=dispense_ids,
                )
            )
        return entries
