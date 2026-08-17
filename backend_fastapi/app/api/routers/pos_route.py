"""POS routes: checkout + cash-drawer movements."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_approval_token, require_permission
from app.core.database import get_session
from app.services.auth_service import AuthService, get_auth_service
from app.services.pos_service import PosService
from app.shared.schemas import (
    ApprovalRequest,
    CheckoutRequest,
    CheckoutResult,
    CurrentUser,
    DrawerMovementCreate,
    DrawerMovementRead,
)

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


@router.post("/approve", status_code=status.HTTP_200_OK)
async def approve(
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
    _approval: dict[str, object] = Depends(require_approval_token("drawer.move")),
    user: CurrentUser = Depends(require_permission("pos.drawer")),
    session: AsyncSession = Depends(get_session),
) -> DrawerMovementRead:
    """Record a cash-drawer cash-in/out (Concern 1). Requires an approval token."""
    return await PosService(session).record_drawer_movement(payload, user)
