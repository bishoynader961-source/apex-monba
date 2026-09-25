"""Prior Authorization service: state machine workflow with NCPDP SCRIPT support."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import InsurancePlan, Patient, PriorAuth, Prescriber
from app.core.audit_log import write_audit
from app.core.repositories import PatientRepository, PrescriberRepository
from app.shared.exceptions import NotFoundError, ValidationError
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    CurrentUser,
    PriorAuthCreate,
    PriorAuthFilters,
    PriorAuthListResponse,
    PriorAuthRead,
    PriorAuthStatusTransition,
    PriorAuthUpdate,
    PA_STATUS_TRANSITIONS,
    PA_STATUS_VALUES,
)

logger = get_logger("prior_auth")


class PriorAuthService:
    """Service layer for Prior Authorization management with state machine."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_prior_auth(self, payload: PriorAuthCreate, user: CurrentUser) -> PriorAuthRead:
        """Create a new PA request in SUBMITTED status."""
        # Validate patient exists
        patient = await PatientRepository(self.session).get_strict(payload.patient_id)

        # Validate prescriber exists
        prescriber = await PrescriberRepository(self.session).get_strict(payload.prescriber_id)

        # Validate insurance plan if provided
        if payload.insurance_plan_id:
            plan = await self.session.get(InsurancePlan, payload.insurance_plan_id)
            if plan is None or plan.active != 1:
                raise NotFoundError("InsurancePlan", payload.insurance_plan_id)

        pa = PriorAuth(
            patient_id=payload.patient_id,
            prescriber_id=payload.prescriber_id,
            product_name=payload.product_name,
            ndc_code=payload.ndc_code,
            quantity=payload.quantity,
            days_supply=payload.days_supply,
            sig_code=payload.sig_code,
            diagnosis_codes=json.dumps(payload.diagnosis_codes),
            clinical_rationale=payload.clinical_rationale,
            prior_therapy_failed=json.dumps(payload.prior_therapy_failed or []),
            insurance_plan_id=payload.insurance_plan_id,
            status="SUBMITTED",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.session.add(pa)
        await self.session.commit()
        await self.session.refresh(pa)

        await write_audit(
            self.session,
            "prior_auth.create",
            subject_type="prior_auth",
            subject_id=pa.id,
            details=f"patient={patient.name} drug={payload.product_name} status=SUBMITTED",
            category="prior_auth",
            user=user,
        )

        return await self._build_read(pa)

    async def get_prior_auth(self, pa_id: int) -> PriorAuthRead:
        """Get a PA request by ID."""
        pa = await self.session.get(PriorAuth, pa_id)
        if pa is None:
            raise NotFoundError("PriorAuth", pa_id)
        return await self._build_read(pa)

    async def list_prior_auths(
        self, filters: PriorAuthFilters, user: CurrentUser
    ) -> PriorAuthListResponse:
        """List PA requests with filters and pagination."""
        clause = PriorAuth.status.is_not(None)

        if filters.status:
            clause = clause & (PriorAuth.status == filters.status)
        if filters.patient_id:
            clause = clause & (PriorAuth.patient_id == filters.patient_id)
        if filters.prescriber_id:
            clause = clause & (PriorAuth.prescriber_id == filters.prescriber_id)
        if filters.product_name:
            clause = clause & (PriorAuth.product_name.ilike(f"%{filters.product_name}%"))
        if filters.start_date:
            clause = clause & (PriorAuth.submitted_at >= filters.start_date)
        if filters.end_date:
            clause = clause & (PriorAuth.submitted_at <= filters.end_date)

        total = await self.session.scalar(
            select(func.count()).select_from(PriorAuth).where(clause)
        ) or 0

        offset = (max(1, filters.page) - 1) * filters.page_size
        result = await self.session.execute(
            select(PriorAuth)
            .where(clause)
            .order_by(PriorAuth.submitted_at.desc())
            .limit(filters.page_size)
            .offset(offset)
        )
        pas = result.scalars().all()

        return PriorAuthListResponse(
            items=[await self._build_read(pa) for pa in pas],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def update_prior_auth(
        self, pa_id: int, payload: PriorAuthUpdate, user: CurrentUser
    ) -> PriorAuthRead:
        """Update a PA request (only allowed in SUBMITTED/PENDING_REVIEW)."""
        pa = await self.session.get(PriorAuth, pa_id)
        if pa is None:
            raise NotFoundError("PriorAuth", pa_id)

        if pa.status not in ("SUBMITTED", "PENDING_REVIEW"):
            raise ValidationError(f"Cannot update PA in {pa.status} status")

        updates = payload.model_dump(exclude_unset=True)
        if "diagnosis_codes" in updates:
            updates["diagnosis_codes"] = json.dumps(updates["diagnosis_codes"])
        if "prior_therapy_failed" in updates:
            updates["prior_therapy_failed"] = json.dumps(updates["prior_therapy_failed"])
        if "payer_specific_data" in updates:
            updates["payer_specific_data"] = json.dumps(updates["payer_specific_data"])

        for field, value in updates.items():
            setattr(pa, field, value)

        pa.updated_at = datetime.now(timezone.utc).isoformat()
        self.session.add(pa)
        await self.session.commit()
        await self.session.refresh(pa)

        await write_audit(
            self.session,
            "prior_auth.update",
            subject_type="prior_auth",
            subject_id=pa.id,
            details=f"updates={payload.model_dump(exclude_unset=True)}",
            category="prior_auth",
            user=user,
        )

        return await self._build_read(pa)

    async def transition_status(
        self, pa_id: int, payload: PriorAuthStatusTransition, user: CurrentUser
    ) -> PriorAuthRead:
        """Transition PA status with validation and required documentation."""
        pa = await self.session.get(PriorAuth, pa_id)
        if pa is None:
            raise NotFoundError("PriorAuth", pa_id)

        current_status = pa.status
        new_status = payload.status

        if new_status not in PA_STATUS_TRANSITIONS.get(current_status, []):
            raise ValidationError(f"Invalid status transition: {current_status} -> {new_status}")

        # Validate required fields for transitions
        if new_status == "DENIED" and not payload.denial_reason:
            raise ValidationError("denial_reason is required for DENIED status")
        if new_status == "APPROVED" and not payload.approval_duration_days:
            raise ValidationError("approval_duration_days is required for APPROVED status")
        if new_status == "APPROVED" and not payload.prior_auth_number:
            raise ValidationError("prior_auth_number is required for APPROVED status")

        # Apply transition
        pa.status = new_status
        pa.updated_at = datetime.now(timezone.utc).isoformat()

        if new_status == "PENDING_REVIEW":
            pa.reviewed_at = datetime.now(timezone.utc).isoformat()
            pa.reviewed_by = user.username
        elif new_status in ("APPROVED", "DENIED"):
            pa.reviewed_at = datetime.now(timezone.utc).isoformat()
            pa.reviewed_by = user.username
            pa.reviewer_notes = payload.reviewer_notes
            if new_status == "DENIED":
                pa.denial_reason = payload.denial_reason
            elif new_status == "APPROVED":
                pa.prior_auth_number = payload.prior_auth_number
                pa.approval_duration_days = payload.approval_duration_days
                pa.expires_at = (
                    datetime.now(timezone.utc) + timedelta(days=payload.approval_duration_days)
                ).isoformat()

        self.session.add(pa)
        await self.session.commit()
        await self.session.refresh(pa)

        await write_audit(
            self.session,
            f"prior_auth.{new_status.lower()}",
            subject_type="prior_auth",
            subject_id=pa.id,
            details=f"status={current_status}->{new_status} reviewer={user.username}",
            category="prior_auth",
            user=user,
        )

        return await self._build_read(pa)

    async def withdraw(self, pa_id: int, user: CurrentUser) -> PriorAuthRead:
        """Withdraw a PA request (allowed from SUBMITTED/PENDING_REVIEW)."""
        pa = await self.session.get(PriorAuth, pa_id)
        if pa is None:
            raise NotFoundError("PriorAuth", pa_id)

        if pa.status not in ("SUBMITTED", "PENDING_REVIEW"):
            raise ValidationError(f"Cannot withdraw PA in {pa.status} status")

        pa.status = "WITHDRAWN"
        pa.updated_at = datetime.now(timezone.utc).isoformat()
        self.session.add(pa)
        await self.session.commit()
        await self.session.refresh(pa)

        await write_audit(
            self.session,
            "prior_auth.withdraw",
            subject_type="prior_auth",
            subject_id=pa.id,
            details=f"withdrawn_by={user.username}",
            category="prior_auth",
            user=user,
        )

        return await self._build_read(pa)

    async def _build_read(self, pa: PriorAuth) -> PriorAuthRead:
        # Get patient name
        patient_result = await self.session.execute(
            select(Patient.name).where(Patient.id == pa.patient_id)
        )
        patient_name = patient_result.scalar() or f"Patient #{pa.patient_id}"

        # Get prescriber name
        prescriber_result = await self.session.execute(
            select(Prescriber.first_name, Prescriber.last_name).where(
                Prescriber.id == pa.prescriber_id
            )
        )
        prescriber = prescriber_result.first()
        prescriber_name = (
            f"{prescriber.first_name} {prescriber.last_name}".strip()
            if prescriber
            else f"Prescriber #{pa.prescriber_id}"
        )

        return PriorAuthRead(
            id=pa.id,
            patient_id=pa.patient_id,
            patient_name=patient_name,
            prescriber_id=pa.prescriber_id,
            prescriber_name=prescriber_name,
            product_name=pa.product_name,
            ndc_code=pa.ndc_code,
            quantity=pa.quantity,
            days_supply=pa.days_supply,
            sig_code=pa.sig_code,
            diagnosis_codes=json.loads(pa.diagnosis_codes or "[]"),
            clinical_rationale=pa.clinical_rationale,
            prior_therapy_failed=json.loads(pa.prior_therapy_failed or "[]"),
            insurance_plan_id=pa.insurance_plan_id,
            status=pa.status,
            prior_auth_number=pa.prior_auth_number,
            denial_reason=pa.denial_reason,
            approval_duration_days=pa.approval_duration_days,
            expires_at=pa.expires_at,
            submitted_at=pa.submitted_at,
            reviewed_at=pa.reviewed_at,
            reviewed_by=pa.reviewed_by,
            reviewer_notes=pa.reviewer_notes,
            created_at=pa.created_at,
            updated_at=pa.updated_at,
        )


# Need imports for timedelta
from datetime import timedelta
from sqlalchemy import func