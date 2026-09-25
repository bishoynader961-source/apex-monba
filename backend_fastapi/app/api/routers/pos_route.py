"""POS routes: checkout + cash-drawer movements + shift lifecycle (A1)."""
import base64
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Body, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.auth_service import AuthService, get_auth_service
from app.services.pos_service import PosService
from app.services.sync_lock_service import get_lock_service
from app.shared.exceptions import AppException, ForbiddenError
from app.shared.rate_limit import get_pin_limit, limiter
from app.shared.schemas import (
    ApprovalRequest,
    CheckoutRequest,
    CheckoutResult,
    CurrentUser,
    DrawerMovementCreate,
    DrawerMovementRead,
    EODSummary,
    ReceiptPrintResponse,
    ReceiptRead,
    RefundRead,
    RefundRequest,
    SalesReport,
    ShiftCloseRequest,
    ShiftCloseResult,
    ShiftOpenRequest,
    ShiftPreviewResult,
    ShiftRead,
    SyncLockRequest,
    SyncLockResponse,
    VoidItemRequest,
    VoidItemResult,
)
from app.shared.security import consume_approval_token

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])

# A1: routine till movements are auto-approved; only large cash drops, payouts,
# pickups, and any non-routine reason require a manager approval token.
_CASH_DROP_APPROVE_THRESHOLD = Decimal("400")
_PAID_OUT_APPROVE_THRESHOLD = Decimal("50")
_AUTO_APPROVE_REASONS = {"cash_tender", "float_add"}


def _requires_approval(reason: str, amount: Decimal) -> bool:
    r = (reason or "").strip().lower()
    if r in _AUTO_APPROVE_REASONS:
        return False
    if r == "cash_drop":
        return abs(amount) >= _CASH_DROP_APPROVE_THRESHOLD
    if r == "paid_out":
        return abs(amount) > _PAID_OUT_APPROVE_THRESHOLD
    # pickup + any unknown reason (incl. legacy "cash-in") always require approval.
    return True


@router.post("/approve", status_code=status.HTTP_200_OK)
@limiter.limit(get_pin_limit())
async def approve(
    request: Request,
    payload: ApprovalRequest,
    auth: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Verify a manager PIN and issue a single-use approval token (Concern 1)."""
    token = await auth.approve_action(payload.username, payload.pin, payload.scope)
    return {"approval_token": token}


@router.post("/checkout", response_model=CheckoutResult, status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutRequest,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> CheckoutResult:
    return await PosService(session).process_checkout(payload, user)


@router.post(
    "/drawer/movement",
    response_model=DrawerMovementRead,
    status_code=status.HTTP_201_CREATED,
)
async def drawer_movement(
    payload: DrawerMovementCreate,
    user: CurrentUser = Depends(require_permission("pos.drawer")),
    x_approval_token: str | None = Header(default=None, alias="X-Approval-Token"),
    session: AsyncSession = Depends(get_session),
) -> DrawerMovementRead:
    """Record a cash-drawer cash-in/out (Concern 1).

    Most routine till movements are auto-approved; only large cash drops, payouts,
    pickups, and non-routine reasons require a single-use ``X-Approval-Token``.
    """
    if _requires_approval(payload.reason, payload.amount):
        if not x_approval_token:
            raise ForbiddenError("Approval token required for this drawer movement")
        claims = consume_approval_token(x_approval_token)
        if claims.get("scope") != "drawer.move":
            raise ForbiddenError("Approval token scope mismatch: expected drawer.move")
    return await PosService(session).record_drawer_movement(payload, user)


@router.post("/shift/open", response_model=ShiftRead, status_code=status.HTTP_201_CREATED)
async def open_shift(
    payload: ShiftOpenRequest,
    user: CurrentUser = Depends(require_permission("pos.drawer")),
    session: AsyncSession = Depends(get_session),
) -> ShiftRead:
    """Open a cash-drawer shift with the counted opening float (A1)."""
    return await PosService(session).open_shift(payload, user)


@router.post("/shift/close", response_model=ShiftCloseResult, status_code=status.HTTP_200_OK)
async def close_shift(
    payload: ShiftCloseRequest,
    user: CurrentUser = Depends(require_permission("pos.drawer")),
    session: AsyncSession = Depends(get_session),
) -> ShiftCloseResult:
    """Close a shift against a physically counted till and compute the variance (A1)."""
    return await PosService(session).close_shift(payload)


@router.get("/shift/{shift_id}/preview", response_model=ShiftPreviewResult, status_code=status.HTTP_200_OK)
async def preview_shift(
    shift_id: int,
    user: CurrentUser = Depends(require_permission("pos.drawer")),
    session: AsyncSession = Depends(get_session),
) -> ShiftPreviewResult:
    """Preview the expected till for an open shift (A1)."""
    return await PosService(session).preview_shift(shift_id)


@router.post("/refund", response_model=RefundRead, status_code=status.HTTP_200_OK)
async def refund(
    payload: RefundRequest,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> RefundRead:
    """Reverse a sale (B5): restock inventory and record a refund ledger entry."""
    return await PosService(session).refund(payload, user)


@router.get("/reports/sales", response_model=SalesReport, status_code=status.HTTP_200_OK)
async def sales_report(
    user: CurrentUser = Depends(require_permission("inventory.reports")),
    session: AsyncSession = Depends(get_session),
) -> SalesReport:
    """Aggregated sales + refunds summary (B5)."""
    return await PosService(session).sales_report()


@router.get("/receipts/recent", response_model=list[ReceiptRead], status_code=status.HTTP_200_OK)
async def recent_receipts(
    limit: int = 50,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> list[ReceiptRead]:
    """Return the last *limit* receipts (newest first) with line items."""
    return await PosService(session).recent_receipts(limit)


@router.get("/receipts/{receipt_id}", response_model=ReceiptRead, status_code=status.HTTP_200_OK)
async def receipt_detail(
    receipt_id: int,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptRead:
    """Return a single receipt with its line items."""
    return await PosService(session).receipt_detail(receipt_id)


@router.get("/receipts/{receipt_id}/print", response_model=ReceiptPrintResponse, status_code=status.HTTP_200_OK)
async def receipt_print(
    receipt_id: int,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptPrintResponse:
    """Return a receipt in thermal-text and browser-printable HTML formats."""
    return await PosService(session).format_receipt_print(receipt_id)


@router.get("/eod-summary", response_model=EODSummary, status_code=status.HTTP_200_OK)
async def eod_summary(
    date: str | None = None,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> EODSummary:
    """End-of-Day reconciliation summary for *date* (default: today UTC)."""
    return await PosService(session).eod_summary(date)


@router.post("/void-item", response_model=VoidItemResult, status_code=status.HTTP_200_OK)
async def void_item(
    payload: VoidItemRequest,
    user: CurrentUser = Depends(require_permission("pos.void_item")),
    session: AsyncSession = Depends(get_session),
) -> VoidItemResult:
    """Void a single receipt item: restock inventory and create a partial refund."""
    return await PosService(session).void_item(payload, user)


@router.post("/lock", response_model=SyncLockResponse, status_code=status.HTTP_200_OK)
async def sync_lock(
    payload: SyncLockRequest,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
) -> SyncLockResponse:
    """Distributed sync-lock probe (Tier-3 concurrency control, §2.1).

    Coordinates the offline→online merge replay so two terminals never
    double-submit the sync queue simultaneously.
    """
    svc = get_lock_service()
    action = (payload.action or "").strip().upper()

    if action == "ACQUIRE":
        entry = await svc.acquire("sync", payload.device_id, payload.nonce, payload.ttl_seconds)
        if entry.nonce == payload.nonce:
            return SyncLockResponse(
                acquired=True,
                current_holder=payload.device_id,
                expires_at=datetime.fromtimestamp(entry.expires_at, tz=timezone.utc).isoformat(),
            )
        return SyncLockResponse(acquired=False, current_holder=entry.device_id)

    if action == "RELEASE":
        ok = await svc.release("sync", payload.nonce)
        return SyncLockResponse(acquired=not ok, current_holder=None)

    if action == "HEARTBEAT":
        ok = await svc.heartbeat("sync", payload.nonce, payload.ttl_seconds)
        return SyncLockResponse(acquired=ok, current_holder=payload.device_id)

    raise AppException(f"Invalid lock action: {action}", status_code=400, error_code="invalid_lock_action")

