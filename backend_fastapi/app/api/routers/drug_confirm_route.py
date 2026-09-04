"""Drug Confirmation API — GET /api/v1/drugs/confirm/{ndc}"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.drug_confirmation_service import DrugConfirmationService
from app.shared.schemas import DrugConfirmResult

router = APIRouter(prefix="/api/v1/drugs", tags=["drug-confirmation"])


@router.get(
    "/confirm/{ndc}",
    response_model=DrugConfirmResult,
    summary="Confirm NDC against local dictionary + external fallback",
    description=(
        "Validates an NDC (National Drug Code) by checking the local drug dictionary first. "
        "If not found locally, queries the FDA NDC Directory API as a fallback. "
        "Returns drug details including name, strength, form, manufacturer, DEA schedule, "
        "and pill image URL (when available)."
    ),
)
async def confirm_drug(
    ndc: str = Path(..., min_length=1, max_length=13, description="NDC code (11 digits, with or without dashes)"),
    _auth: object = Depends(require_permission("dictionaries.read")),
    session: AsyncSession = Depends(get_session),
) -> DrugConfirmResult:
    service = DrugConfirmationService(session)
    try:
        return await service.confirm_ndc(ndc)
    finally:
        await service.close()