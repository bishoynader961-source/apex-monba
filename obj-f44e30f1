"""Rx Queue routes: 3-tab prescription queue with status workflow.

Endpoints:
- GET  /api/v1/rx-queue              - List all Rx with filters
- GET  /api/v1/rx-queue/counts       - Aggregated counts per group
- PATCH /api/v1/rx-queue/{rx_id}/status - Single status transition
- POST  /api/v1/rx-queue/bulk-status - Bulk status change
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.rx_queue_service import RxQueueService
from app.shared.schemas import (
    CurrentUser,
    PaginatedRxQueue,
    RxBulkStatusRequest,
    RxBulkStatusResult,
    RxQueueCounts,
    RxQueueFilters,
    RxQueueItem,
    RxStatusTransition,
)

router = APIRouter(prefix="/api/v1/rx-queue", tags=["rx-queue"])


@router.get("", response_model=PaginatedRxQueue)
async def list_rx_queue(
    status: str | None = None,
    prescriber_id: int | None = None,
    patient_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: CurrentUser = Depends(require_permission("rx.queue.read")),
    session: AsyncSession = Depends(get_session),
) -> PaginatedRxQueue:
    """List Rx queue with filters and pagination."""
    filters = RxQueueFilters(
        status=status,
        prescriber_id=prescriber_id,
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    service = RxQueueService(session)
    return await service.get_queue(filters, user)


@router.get("/counts", response_model=RxQueueCounts)
async def get_rx_queue_counts(
    user: CurrentUser = Depends(require_permission("rx.queue.read")),
    session: AsyncSession = Depends(get_session),
) -> RxQueueCounts:
    """Get aggregated counts per queue group (Processing/Rejects/Ready)."""
    service = RxQueueService(session)
    return await service.get_counts_by_status()


@router.patch("/{rx_id}/status", response_model=RxQueueItem)
async def transition_rx_status(
    rx_id: int,
    payload: RxStatusTransition,
    user: CurrentUser = Depends(require_permission("rx.queue.write")),
    session: AsyncSession = Depends(get_session),
):
    """Transition a single Rx to a new status."""
    service = RxQueueService(session)
    return await service.transition_status(rx_id, payload.status, user)


@router.post("/bulk-status", response_model=RxBulkStatusResult)
async def bulk_transition_rx_status(
    payload: RxBulkStatusRequest,
    user: CurrentUser = Depends(require_permission("rx.queue.write")),
    session: AsyncSession = Depends(get_session),
) -> RxBulkStatusResult:
    """Bulk transition multiple Rx to a new status."""
    service = RxQueueService(session)
    return await service.bulk_transition(payload, user)