"""Region Strategy routes: patient cost calculation, claim generation, validation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.region_strategy_service import RegionStrategyService
from app.shared.schemas import (
    ClaimGenerationRequest,
    ClaimGenerationResult,
    CredentialValidationRequest,
    CredentialValidationResult,
    CurrentUser,
    PatientCostRequest,
    PatientCostResult,
    PrescriptionValidationRequest,
    PrescriptionValidationResult,
)

router = APIRouter(prefix="/api/v1/region-strategy", tags=["region-strategy"])


@router.post(
    "/patient-cost",
    response_model=PatientCostResult,
    status_code=status.HTTP_200_OK,
)
async def calculate_patient_cost(
    payload: PatientCostRequest,
    user: CurrentUser = Depends(require_permission("insurance.read")),
    session: AsyncSession = Depends(get_session),
) -> PatientCostResult:
    """Calculate patient out-of-pocket cost for a given region.

    Uses the regional billing strategy (US Medicare Part D, EU AMTS, or MOCK).
    """
    service = RegionStrategyService()
    return service.calculate_patient_cost(payload)


@router.post(
    "/generate-claim",
    response_model=ClaimGenerationResult,
    status_code=status.HTTP_200_OK,
)
async def generate_claim(
    payload: ClaimGenerationRequest,
    user: CurrentUser = Depends(require_permission("insurance.write")),
    session: AsyncSession = Depends(get_session),
) -> ClaimGenerationResult:
    """Generate a regional insurance claim payload for submission."""
    service = RegionStrategyService()
    return service.generate_claim(payload)


@router.post(
    "/validate-prescription",
    response_model=PrescriptionValidationResult,
    status_code=status.HTTP_200_OK,
)
async def validate_prescription(
    payload: PrescriptionValidationRequest,
    user: CurrentUser = Depends(require_permission("dispense.create")),
    session: AsyncSession = Depends(get_session),
) -> PrescriptionValidationResult:
    """Validate a prescription against regional rules."""
    service = RegionStrategyService()
    return service.validate_prescription(payload)


@router.post(
    "/validate-credentials",
    response_model=CredentialValidationResult,
    status_code=status.HTTP_200_OK,
)
async def validate_credentials(
    payload: CredentialValidationRequest,
    user: CurrentUser = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_session),
) -> CredentialValidationResult:
    """Validate credentials for a regional billing gateway."""
    service = RegionStrategyService()
    return service.authenticate_credentials(payload)


@router.get(
    "/supported-regions",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
)
async def get_supported_regions(
    user: CurrentUser = Depends(require_permission("insurance.read")),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """Get list of supported region codes."""
    service = RegionStrategyService()
    return service.get_supported_regions()