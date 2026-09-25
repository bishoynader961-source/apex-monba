"""EPCS routes: DEA CFR 1311 compliant electronic prescribing for controlled substances."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.epcs_service import EPCSService
from app.shared.schemas import (
    CurrentUser,
    EPCSPrescriptionCreate,
    EPCSPrescriptionListResponse,
    EPCSPrescriptionRead,
    EPCSPrescriptionUpdate,
    EPCSFilters,
    EPCSIdentityProofingRequest,
    EPCSIdentityProofingResult,
    EPCSIdentityProofingStatus,
    EPCSSignRequest,
    EPCSSignResult,
    EPCSTransmitRequest,
    EPCSTransmitResult,
)

router = APIRouter(prefix="/api/v1/epcs", tags=["epcs"])


@router.post("", response_model=EPCSPrescriptionRead, status_code=status.HTTP_201_CREATED)
async def create_epcs_prescription(
    payload: EPCSPrescriptionCreate,
    user: CurrentUser = Depends(require_permission("epcs.create")),
    session: AsyncSession = Depends(get_session),
) -> EPCSPrescriptionRead:
    """Create a new EPCS prescription (C-II through C-V)."""
    service = EPCSService(session)
    return await service.create_prescription(payload, user)


@router.get("", response_model=EPCSPrescriptionListResponse)
async def list_epcs_prescriptions(
    status: str | None = None,
    schedule: str | None = None,
    patient_id: int | None = None,
    prescriber_id: int | None = None,
    product_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: CurrentUser = Depends(require_permission("epcs.read")),
    session: AsyncSession = Depends(get_session),
) -> EPCSPrescriptionListResponse:
    """List EPCS prescriptions with filters and pagination."""
    filters = EPCSFilters(
        status=status,
        schedule=schedule,
        patient_id=patient_id,
        prescriber_id=prescriber_id,
        product_name=product_name,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    service = EPCSService(session)
    return await service.list_prescriptions(filters, user)


@router.get("/{rx_id}", response_model=EPCSPrescriptionRead)
async def get_epcs_prescription(
    rx_id: int,
    user: CurrentUser = Depends(require_permission("epcs.read")),
    session: AsyncSession = Depends(get_session),
) -> EPCSPrescriptionRead:
    """Get an EPCS prescription by ID."""
    service = EPCSService(session)
    return await service.get_prescription(rx_id)


@router.put("/{rx_id}", response_model=EPCSPrescriptionRead)
async def update_epcs_prescription(
    rx_id: int,
    payload: EPCSPrescriptionUpdate,
    user: CurrentUser = Depends(require_permission("epcs.write")),
    session: AsyncSession = Depends(get_session),
) -> EPCSPrescriptionRead:
    """Update an EPCS prescription (only in DRAFT status)."""
    service = EPCSService(session)
    return await service.update_prescription(rx_id, payload, user)


@router.patch("/{rx_id}/status", response_model=EPCSPrescriptionRead)
async def transition_epcs_status(
    rx_id: int,
    new_status: str,
    user: CurrentUser = Depends(require_permission("epcs.review")),
    session: AsyncSession = Depends(get_session),
) -> EPCSPrescriptionRead:
    """Transition EPCS prescription status (DRAFT -> PENDING_SIGNATURE -> SIGNED -> TRANSMITTED -> ARCHIVED)."""
    service = EPCSService(session)
    return await service.transition_status(rx_id, new_status, user)


@router.post("/{rx_id}/sign", response_model=EPCSSignResult)
async def sign_epcs_prescription(
    rx_id: int,
    payload: EPCSSignRequest,
    user: CurrentUser = Depends(require_permission("epcs.sign")),
    session: AsyncSession = Depends(get_session),
) -> EPCSSignResult:
    """Sign an EPCS prescription with 2FA (DEA CFR 1311 compliant)."""
    service = EPCSService(session)
    payload.prescription_id = rx_id
    return await service.sign_prescription(payload, user)


@router.post("/{rx_id}/transmit", response_model=EPCSTransmitResult)
async def transmit_epcs_prescription(
    rx_id: int,
    payload: EPCSTransmitRequest,
    user: CurrentUser = Depends(require_permission("epcs.transmit")),
    session: AsyncSession = Depends(get_session),
) -> EPCSTransmitResult:
    """Transmit signed EPCS to pharmacy via NCPDP SCRIPT, fax, or print."""
    service = EPCSService(session)
    payload.prescription_id = rx_id
    return await service.transmit_prescription(payload, user)


@router.get("/prescriber/{prescriber_id}/identity", response_model=EPCSIdentityProofingStatus)
async def get_identity_proofing_status(
    prescriber_id: int,
    user: CurrentUser = Depends(require_permission("epcs.read")),
    session: AsyncSession = Depends(get_session),
) -> EPCSIdentityProofingStatus:
    """Get 2FA/identity proofing status for a prescriber."""
    service = EPCSService(session)
    return await service.get_identity_proofing_status(prescriber_id, user)


@router.post("/prescriber/{prescriber_id}/identity", response_model=EPCSIdentityProofingResult)
async def enroll_identity_proofing(
    prescriber_id: int,
    payload: EPCSIdentityProofingRequest,
    user: CurrentUser = Depends(require_permission("epcs.identity_proofing")),
    session: AsyncSession = Depends(get_session),
) -> EPCSIdentityProofingResult:
    """Enroll prescriber in identity proofing (2FA setup for DEA compliance)."""
    service = EPCSService(session)
    payload.prescriber_id = prescriber_id
    return await service.enroll_identity_proofing(payload, user)