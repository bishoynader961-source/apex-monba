"""Label Template + Product Label routes."""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.label_template_service import LabelTemplateService, ProductLabelService
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/label-templates", tags=["label-templates"])

product_router = APIRouter(prefix="/api/v1/product-labels", tags=["product-labels"])


# ── Label Templates ────────────────────────────────────────────────────

class TemplateCreateRequest(BaseModel):
    name: str
    canvas_width: int = 400
    canvas_height: int = 300
    elements: list[dict] = []
    is_default: int = 0


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    canvas_width: int | None = None
    canvas_height: int | None = None
    elements: list[dict] | None = None
    is_default: int | None = None


class TemplateRead(BaseModel):
    id: int
    name: str
    canvas_width: int
    canvas_height: int
    elements: list[dict]
    is_default: int
    created_at: str | None = None
    updated_at: str | None = None


@router.get("/", response_model=list[TemplateRead], status_code=status.HTTP_200_OK)
async def list_templates(
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> list[TemplateRead]:
    return [TemplateRead(**d) for d in await LabelTemplateService(session).list_templates()]


@router.get("/{template_id}", response_model=TemplateRead, status_code=status.HTTP_200_OK)
async def get_template(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> TemplateRead:
    return TemplateRead(**await LabelTemplateService(session).get_template(template_id))


@router.post("/", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreateRequest,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> TemplateRead:
    svc = LabelTemplateService(session)
    return TemplateRead(**await svc.create_template(payload.name, payload.canvas_width, payload.canvas_height, payload.elements, payload.is_default))


@router.put("/{template_id}", response_model=TemplateRead, status_code=status.HTTP_200_OK)
async def update_template(
    template_id: int,
    payload: TemplateUpdateRequest,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> TemplateRead:
    svc = LabelTemplateService(session)
    return TemplateRead(**await svc.update_template(template_id, payload.name, payload.canvas_width, payload.canvas_height, payload.elements, payload.is_default))


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    await LabelTemplateService(session).delete_template(template_id)


# ── Per-Product Labels ─────────────────────────────────────────────────

class ProductLabelSaveRequest(BaseModel):
    canvas_width: int = 400
    canvas_height: int = 300
    elements: list[dict] = []


class ProductLabelRead(BaseModel):
    id: int
    product_id: int
    canvas_width: int
    canvas_height: int
    elements: list[dict]
    updated_at: str | None = None


@product_router.get("/{product_id}", response_model=ProductLabelRead | None, status_code=status.HTTP_200_OK)
async def get_product_label(
    product_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ProductLabelRead | None:
    result = await ProductLabelService(session).get_label(product_id)
    return ProductLabelRead(**result) if result else None


@product_router.put("/{product_id}", response_model=ProductLabelRead, status_code=status.HTTP_200_OK)
async def save_product_label(
    product_id: int,
    payload: ProductLabelSaveRequest,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ProductLabelRead:
    svc = ProductLabelService(session)
    return ProductLabelRead(**await svc.save_label(product_id, payload.canvas_width, payload.canvas_height, payload.elements))


@product_router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_label(
    product_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    await ProductLabelService(session).delete_label(product_id)
