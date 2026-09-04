"""Dispense routes: patient-linked FIFO dispensing + thermal label (F5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.dispense_service import DispenseService
from app.shared.schemas import CurrentUser, DispenseCreate, DispenseRead, DispenseUpdate, TransferResult, VoidResult

router = APIRouter(prefix="/api/v1/dispense", tags=["dispense"])


@router.post("", response_model=DispenseRead, status_code=status.HTTP_201_CREATED)
async def dispense(
    payload: DispenseCreate,
    user: CurrentUser = Depends(require_permission("dispense.create")),
    session: AsyncSession = Depends(get_session),
) -> DispenseRead:
    return await DispenseService(session).process_dispense(payload, user)


@router.get("/rx/{rx_number}", response_model=DispenseRead)
async def get_dispense_by_rx(
    rx_number: str,
    user: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> DispenseRead:
    """Return the most recent dispense for a given Rx number."""
    return await DispenseService(session).get_by_rx_number(rx_number)


@router.get("/rx/{rx_number}/fills", response_model=list[DispenseRead])
async def get_dispense_fills_by_rx(
    rx_number: str,
    user: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> list[DispenseRead]:
    """Return all fills sharing the same Rx number (fill history)."""
    return await DispenseService(session).get_fills_by_rx_number(rx_number)


class VoidRequest(BaseModel):
    reason: str = ""


@router.put("/{dispense_id}", response_model=DispenseRead)
async def update_dispense(
    dispense_id: int,
    payload: DispenseUpdate,
    user: CurrentUser = Depends(require_permission("dispense.create")),
    session: AsyncSession = Depends(get_session),
) -> DispenseRead:
    """Edit an existing dispense (sig, quantity, days supply, refills, prescriber)."""
    return await DispenseService(session).update_dispense(dispense_id, payload, user)


@router.post("/{dispense_id}/reverse", response_model=VoidResult)
async def reverse_dispense(
    dispense_id: int,
    payload: VoidRequest,
    user: CurrentUser = Depends(require_permission("dispense.create")),
    session: AsyncSession = Depends(get_session),
) -> VoidResult:
    """Void/reverse a dispense — restock inventory and mark as voided."""
    return await DispenseService(session).void_dispense(dispense_id, payload.reason, user)


class TransferRequest(BaseModel):
    pharmacy_name: str = ""
    pharmacy_phone: str = ""
    transfer_type: str = "outgoing"  # "outgoing" or "incoming"
    reason: str = ""


@router.post("/{dispense_id}/transfer", response_model=TransferResult)
async def transfer_dispense(
    dispense_id: int,
    payload: TransferRequest,
    user: CurrentUser = Depends(require_permission("dispense.create")),
    session: AsyncSession = Depends(get_session),
) -> TransferResult:
    """Transfer a prescription to/from another pharmacy."""
    return await DispenseService(session).transfer_dispense(
        dispense_id, payload.pharmacy_name, payload.pharmacy_phone,
        payload.transfer_type, payload.reason, user,
    )


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


@router.post("/{dispense_id}/refill", response_model=DispenseRead, status_code=status.HTTP_201_CREATED)
async def refill_dispense(
    dispense_id: int,
    payload: DispenseCreate,
    user: CurrentUser = Depends(require_permission("dispense.create")),
    session: AsyncSession = Depends(get_session),
) -> DispenseRead:
    """Process a refill of an existing prescription."""
    return await DispenseService(session).process_refill(dispense_id, payload, user)
