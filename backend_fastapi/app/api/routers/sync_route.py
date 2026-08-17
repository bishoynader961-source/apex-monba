"""Multi-terminal merge-sync routes (C.1).

``POST /api/v1/sync/push`` is the hub endpoint terminals call to merge their
committed sales. It is gated by ``settings.multi_terminal`` so single-kiosk
deployments never expose cross-terminal reconciliation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.auth_service import AuthService, get_auth_service
from app.services.pos_service import PosService
from app.services.sync_service import SyncService
from app.shared.config import settings
from app.shared.exceptions import ForbiddenError
from app.shared.schemas import (
    ApprovalRequest,
    CheckoutRequest,
    CheckoutResult,
    CurrentUser,
    DiscrepancyRead,
    DrawerMovementCreate,
    DrawerMovementRead,
    SyncPushRequest,
    SyncPushResult,
)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.post("/push", response_model=SyncPushResult, status_code=status.HTTP_200_OK)
async def push(
    payload: SyncPushRequest,
    session: AsyncSession = Depends(get_session),
) -> SyncPushResult:
    if not settings.multi_terminal:
        raise ForbiddenError("multi-terminal sync is disabled")
    return await SyncService(session).push(payload.entries)


@router.get(
    "/discrepancies",
    response_model=list[DiscrepancyRead],
    status_code=status.HTTP_200_OK,
)
async def list_discrepancies(
    unresolved_only: bool = True,
    _user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[DiscrepancyRead]:
    """List persisted sync discrepancies surfaced for manager review (A4)."""
    return await SyncService(session).list_discrepancies(unresolved_only)


@router.post(
    "/discrepancies/{discrepancy_id}/resolve",
    response_model=DiscrepancyRead,
    status_code=status.HTTP_200_OK,
)
async def resolve_discrepancy(
    discrepancy_id: int,
    _user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> DiscrepancyRead:
    """Mark a discrepancy as resolved by a manager (A4)."""
    return await SyncService(session).resolve_discrepancy(discrepancy_id)
