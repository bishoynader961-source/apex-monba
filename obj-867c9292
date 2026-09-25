"""Purchase Order routes: CRUD + lifecycle management + auto-reorder."""
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.po_service import PurchaseOrderService
from app.shared.schemas import (
    CurrentUser,
    PurchaseOrderCreate,
    PurchaseOrderRead,
    PurchaseOrderUpdate,
    PurchaseOrderReceiveItem,
)

router = APIRouter(prefix="/api/v1/purchase-orders", tags=["purchase-orders"])


class AutoReorderDraft(BaseModel):
    po_id: int
    po_number: str


class AutoReorderResponse(BaseModel):
    po_count: int
    item_count: int
    low_stock_count: int
    drafts: list[AutoReorderDraft]


@router.get("/", response_model=list[PurchaseOrderRead], status_code=status.HTTP_200_OK)
async def list_pos(
    status_filter: str = Query(default=""),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> list[PurchaseOrderRead]:
    return await PurchaseOrderService(session).list_pos(status_filter=status_filter)


@router.get("/{po_id}", response_model=PurchaseOrderRead, status_code=status.HTTP_200_OK)
async def get_po(
    po_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    return await PurchaseOrderService(session).get_po(po_id)


@router.post("/", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
async def create_po(
    payload: PurchaseOrderCreate,
    user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    return await PurchaseOrderService(session).create_po(payload, user.username)


@router.put("/{po_id}", response_model=PurchaseOrderRead, status_code=status.HTTP_200_OK)
async def update_po(
    po_id: int,
    payload: PurchaseOrderUpdate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    return await PurchaseOrderService(session).update_po(po_id, payload)


@router.post("/{po_id}/items", response_model=PurchaseOrderRead, status_code=status.HTTP_200_OK)
async def add_item(
    po_id: int,
    item: dict,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    return await PurchaseOrderService(session).add_item(po_id, item)


@router.delete("/{po_id}/items/{item_id}", response_model=PurchaseOrderRead, status_code=status.HTTP_200_OK)
async def remove_item(
    po_id: int,
    item_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    return await PurchaseOrderService(session).remove_item(po_id, item_id)


@router.post("/{po_id}/transition", response_model=PurchaseOrderRead, status_code=status.HTTP_200_OK)
async def transition_status(
    po_id: int,
    user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    return await PurchaseOrderService(session).transition_status(po_id, user.username)


@router.post("/{po_id}/receive", response_model=PurchaseOrderRead, status_code=status.HTTP_200_OK)
async def receive_po(
    po_id: int,
    items: list[PurchaseOrderReceiveItem],
    user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    """Receive a PO with per-item received qty, lot number, and expiry date."""
    return await PurchaseOrderService(session).receive_po(po_id, items, user.username)


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_po(
    po_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    await PurchaseOrderService(session).delete_po(po_id)


@router.post("/auto-reorder", response_model=AutoReorderResponse, status_code=status.HTTP_201_CREATED)
async def auto_reorder(
    user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> AutoReorderResponse:
    """Draft consolidated POs for all products below their reorder threshold.

    Groups low-stock products by vendor, creates one Draft PO per vendor
    with suggested reorder quantities (threshold + buffer).
    """
    result = await PurchaseOrderService(session).auto_reorder(username=user.username)
    return AutoReorderResponse(**result)
