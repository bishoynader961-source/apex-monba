"""Prior Authorization routes: state machine workflow with NCPDP SCRIPT support."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.prior_auth_service import PriorAuthService
from app.shared.schemas import (
    CurrentUser,
    PriorAuthCreate,
    PriorAuthFilters,
    PriorAuthListResponse,
    PriorAuthRead,
    PriorAuthStatusTransition,
    PriorAuthUpdate,
)

router = APIRouter(prefix="/api/v1/prior-auth", tags=["prior-auth"])


@router.post("", response_model=PriorAuthRead, status_code=status.HTTP_201_CREATED)
async def create_prior_auth(
    payload: PriorAuthCreate,
    user: CurrentUser = Depends(require_permission("prior_auth.create")),
    session: AsyncSession = Depends(get_session),
) -> PriorAuthRead:
    """Create a new Prior Authorization request."""
    service = PriorAuthService(session)
    return await service.create_prior_auth(payload, user)


@router.get("", response_model=PriorAuthListResponse)
async def list_prior_auths(
    status: str | None = None,
    patient_id: int | None = None,
    prescriber_id: int | None = None,
    product_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: CurrentUser = Depends(require_permission("prior_auth.read")),
    session: AsyncSession = Depends(get_session),
) -> PriorAuthListResponse:
    """List PA requests with filters and pagination."""
    filters = PriorAuthFilters(
        status=status,
        patient_id=patient_id,
        prescriber_id=prescriber_id,
        product_name=product_name,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    service = PriorAuthService(session)
    return await service.list_prior_auths(filters, user)


@router.get("/{pa_id}", response_model=PriorAuthRead)
async def get_prior_auth(
    pa_id: int,
    user: CurrentUser = Depends(require_permission("prior_auth.read")),
    session: AsyncSession = Depends(get_session),
) -> PriorAuthRead:
    """Get a PA request by ID."""
    service = PriorAuthService(session)
    return await service.get_prior_auth(pa_id)


@router.put("/{pa_id}", response_model=PriorAuthRead)
async def update_prior_auth(
    pa_id: int,
    payload: PriorAuthUpdate,
    user: CurrentUser = Depends(require_permission("prior_auth.write")),
    session: AsyncSession = Depends(get_session),
) -> PriorAuthRead:
    """Update a PA request (only in SUBMITTED/PENDING_REVIEW)."""
    service = PriorAuthService(session)
    return await service.update_prior_auth(pa_id, payload, user)


@router.patch("/{pa_id}/status", response_model=PriorAuthRead)
async def transition_prior_auth_status(
    pa_id: int,
    payload: PriorAuthStatusTransition,
    user: CurrentUser = Depends(require_permission("prior_auth.review")),
    session: AsyncSession = Depends(get_session),
) -> PriorAuthRead:
    """Transition PA status (reviewer action)."""
    service = PriorAuthService(session)
    return await service.transition_status(pa_id, payload, user)


@router.post("/{pa_id}/withdraw", response_model=PriorAuthRead)
async def withdraw_prior_auth(
    pa_id: int,
    user: CurrentUser = Depends(require_permission("prior_auth.write")),
    session: AsyncSession = Depends(get_session),
) -> PriorAuthRead:
    """Withdraw a PA request (from SUBMITTED/PENDING_REVIEW)."""
    service = PriorAuthService(session)
    return await service.withdraw(pa_id, user)