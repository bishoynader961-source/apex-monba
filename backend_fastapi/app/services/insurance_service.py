"""Insurance coverage validation (F4: Insurance Plan tab binding)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import InsuranceRepository, PatientRepository
from app.shared.exceptions import NotFoundError
from app.shared.schemas import (
    EligibilityCheckResult,
    InsurancePlanRead,
    InsuranceValidationResult,
)


class InsuranceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def validate_coverage(self, plan_id: int) -> InsuranceValidationResult:
        plan = await InsuranceRepository(self.session).validate(plan_id)
        if plan is None:
            raise NotFoundError("InsurancePlan", plan_id)
        return InsuranceValidationResult(
            plan_id=plan.id,
            plan_name=plan.plan_name,
            active=True,
            copay_tier=plan.copay_tier,
            copay_amount=plan.copay_amount,
            coverage_percentage=80,
        )

    async def check_eligibility(self, patient_id: int) -> EligibilityCheckResult:
        """Real-time eligibility check for a patient's bound insurance plan."""
        patient = await PatientRepository(self.session).get(patient_id)
        if patient is None:
            raise NotFoundError("Patient", patient_id)

        if not patient.insurance_plan_id:
            return EligibilityCheckResult(
                patient_id=patient.id,
                patient_name=patient.name,
                eligible=False,
                active=False,
                message="No insurance plan bound to this patient",
            )

        plan = await InsuranceRepository(self.session).get(patient.insurance_plan_id)
        if plan is None:
            return EligibilityCheckResult(
                patient_id=patient.id,
                patient_name=patient.name,
                eligible=False,
                active=False,
                message="Bound insurance plan not found",
            )

        active = bool(plan.active)
        deductible = plan.deductible or Decimal("0")
        copay = plan.copay_amount or Decimal("0")
        coinsurance = plan.co_insurance_pct or 0
        ncpcp_copay = plan.ncpcp_copay or Decimal("0")

        return EligibilityCheckResult(
            patient_id=patient.id,
            patient_name=patient.name,
            plan_id=plan.id,
            plan_name=plan.plan_name,
            eligible=active,
            active=active,
            copay_tier=plan.copay_tier or "",
            copay_amount=ncpcp_copay if ncpcp_copay > 0 else copay,
            deductible=deductible,
            deductible_met=Decimal("0"),
            deductible_remaining=deductible,
            coinsurance_pct=int(coinsurance),
            coverage_percentage=80,
            message=f"Eligible — {plan.plan_name}" if active else f"Inactive — {plan.plan_name}",
        )

    async def list_plans(self) -> list[InsurancePlanRead]:
        return [
            InsurancePlanRead.model_validate(p)
            for p in await InsuranceRepository(self.session).all()
        ]
