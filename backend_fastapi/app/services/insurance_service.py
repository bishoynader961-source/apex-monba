"""Insurance coverage validation (F4: Insurance Plan tab binding)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import InsuranceRepository
from app.shared.exceptions import NotFoundError
from app.shared.schemas import InsurancePlanRead, InsuranceValidationResult


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

    async def list_plans(self) -> list[InsurancePlanRead]:
        return [
            InsurancePlanRead.model_validate(p)
            for p in await InsuranceRepository(self.session).all()
        ]
