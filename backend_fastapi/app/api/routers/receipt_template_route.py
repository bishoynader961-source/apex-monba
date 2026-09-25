"""Receipt Template routes: CRUD + default management."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.receipt_template_service import ReceiptTemplateService
from app.shared.schemas import (
    CurrentUser,
    ReceiptTemplateCreate,
    ReceiptTemplateRead,
    ReceiptTemplateUpdate,
)

router = APIRouter(prefix="/api/v1/receipt-templates", tags=["receipt-templates"])


@router.get("/", response_model=list[ReceiptTemplateRead], status_code=status.HTTP_200_OK)
async def list_templates(
    template_type: str = Query(default=""),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> list[ReceiptTemplateRead]:
    return await ReceiptTemplateService(session).list_templates(template_type=template_type)


@router.get("/default", response_model=ReceiptTemplateRead | None, status_code=status.HTTP_200_OK)
async def get_default(
    template_type: str = Query(default="receipt"),
    session: AsyncSession = Depends(get_session),
) -> ReceiptTemplateRead | None:
    return await ReceiptTemplateService(session).get_default(template_type=template_type)


@router.get("/{template_id}", response_model=ReceiptTemplateRead, status_code=status.HTTP_200_OK)
async def get_template(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptTemplateRead:
    return await ReceiptTemplateService(session).get_template(template_id)


@router.post("/", response_model=ReceiptTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: ReceiptTemplateCreate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptTemplateRead:
    return await ReceiptTemplateService(session).create_template(payload)


@router.put("/{template_id}", response_model=ReceiptTemplateRead, status_code=status.HTTP_200_OK)
async def update_template(
    template_id: int,
    payload: ReceiptTemplateUpdate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptTemplateRead:
    return await ReceiptTemplateService(session).update_template(template_id, payload)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    await ReceiptTemplateService(session).delete_template(template_id)
