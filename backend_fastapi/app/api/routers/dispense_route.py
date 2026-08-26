"""Dispense routes: patient-linked FIFO dispensing + thermal label (F5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.dispense_service import DispenseService
from app.shared.schemas import CurrentUser, DispenseCreate, DispenseRead

router = APIRouter(prefix="/api/v1/dispense", tags=["dispense"])


@router.post("", response_model=DispenseRead, status_code=status.HTTP_201_CREATED)
async def dispense(
    payload: DispenseCreate,
    user: CurrentUser = Depends(require_permission("dispense.create")),
    session: AsyncSession = Depends(get_session),
) -> DispenseRead:
    return await DispenseService(session).process_dispense(payload, user)


@router.get("/{dispense_id}", response_model=DispenseRead)
async def get_dispense(
    dispense_id: int,
    user: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> DispenseRead:
    return await DispenseService(session).get(dispense_id)


@router.get("/{dispense_id}/label")
async def dispense_label(
    dispense_id: int,
    user: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> FastAPIResponse:
    """Raw ESC/POS label bytes for the thermal printer (concern 3 / #3)."""
    label = await DispenseService(session).label_bytes(dispense_id)
    return FastAPIResponse(
        content=label,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "inline; filename=label.raw"},
    )
