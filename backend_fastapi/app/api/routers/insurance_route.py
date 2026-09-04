"""Insurance plan routes: CRUD + coverage validation (F4 Insurance tab)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import InsuranceRepository
from app.services.insurance_service import InsuranceService
from app.shared.schemas import (
    EligibilityCheckResult,
    InsurancePlanCreate,
    InsurancePlanRead,
    InsuranceValidateRequest,
    InsuranceValidationResult,
)

router = APIRouter(prefix="/api/v1/insurance", tags=["insurance"])


@router.get("/plans", response_model=List[InsurancePlanRead])
async def list_plans(
    _auth: object = Depends(require_permission("insurance.read")),
    session: AsyncSession = Depends(get_session),
) -> List[InsurancePlanRead]:
    return [
        InsurancePlanRead.model_validate(p)
        for p in await InsuranceRepository(session).all()
    ]


@router.get("/plans/{plan_id}", response_model=InsurancePlanRead)
async def get_plan(
    plan_id: int,
    _auth: object = Depends(require_permission("insurance.read")),
    session: AsyncSession = Depends(get_session),
) -> InsurancePlanRead:
    plan = await InsuranceRepository(session).get(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance plan not found")
    return InsurancePlanRead.model_validate(plan)


@router.post("/plans", response_model=InsurancePlanRead, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: InsurancePlanCreate,
    _auth: object = Depends(require_permission("insurance.write")),
    session: AsyncSession = Depends(get_session),
) -> InsurancePlanRead:
    existing = await InsuranceRepository(session).get_by_name(payload.plan_name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Plan '{payload.plan_name}' already exists"
        )
    return InsurancePlanRead.model_validate(await InsuranceRepository(session).create(payload))


@router.put("/plans/{plan_id}", response_model=InsurancePlanRead)
async def update_plan(
    plan_id: int,
    payload: InsurancePlanCreate,
    _auth: object = Depends(require_permission("insurance.write")),
    session: AsyncSession = Depends(get_session),
) -> InsurancePlanRead:
    repo = InsuranceRepository(session)
    plan = await repo.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance plan not found")
    return InsurancePlanRead.model_validate(await repo.update(plan, payload))


@router.delete("/plans/{plan_id}", response_model=InsurancePlanRead)
async def delete_plan(
    plan_id: int,
    _auth: object = Depends(require_permission("insurance.write")),
    session: AsyncSession = Depends(get_session),
) -> InsurancePlanRead:
    plan = await InsuranceRepository(session).deactivate(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance plan not found")
    return InsurancePlanRead.model_validate(plan)


@router.post("/plans/validate", response_model=InsuranceValidationResult)
async def validate_plan(
    payload: InsuranceValidateRequest,
    _auth: object = Depends(require_permission("insurance.read")),
    session: AsyncSession = Depends(get_session),
) -> InsuranceValidationResult:
    return await InsuranceService(session).validate_coverage(payload.plan_id)


class EligibilityRequest(BaseModel):
    patient_id: int


@router.post("/eligibility", response_model=EligibilityCheckResult)
async def check_eligibility(
    payload: EligibilityRequest,
    _auth: object = Depends(require_permission("insurance.read")),
    session: AsyncSession = Depends(get_session),
) -> EligibilityCheckResult:
    """Real-time insurance eligibility check for a patient."""
    return await InsuranceService(session).check_eligibility(payload.patient_id)
