"""Product templates route: CRUD for reusable product quick-add templates.

GET    /api/v1/templates          — list all templates
POST   /api/v1/templates          — create template
PUT    /api/v1/templates/{id}     — update template
DELETE /api/v1/templates/{id}     — delete template
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import ProductTemplate
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


class TemplateCreate(BaseModel):
    name: str
    price: float = 0.0
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    dea_schedule: Optional[str] = None
    reorder_threshold: Optional[int] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    dea_schedule: Optional[str] = None
    reorder_threshold: Optional[int] = None


class TemplateRead(BaseModel):
    id: int
    name: str
    price: float
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    dea_schedule: Optional[str] = None
    reorder_threshold: Optional[int] = None
    created_at: Optional[str] = None


@router.get("", response_model=list[TemplateRead])
async def list_templates(
    _auth: CurrentUser = Depends(require_permission("templates.read")),
    session: AsyncSession = Depends(get_session),
) -> list[TemplateRead]:
    rows = (await session.execute(
        select(ProductTemplate).order_by(ProductTemplate.name)
    )).scalars().all()
    return [
        TemplateRead(
            id=t.id, name=t.name, price=float(t.price),
            vendor_name=t.vendor_name, category=t.category,
            dea_schedule=t.dea_schedule, reorder_threshold=t.reorder_threshold,
            created_at=t.created_at,
        )
        for t in rows
    ]


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    _auth: CurrentUser = Depends(require_permission("templates.write")),
    session: AsyncSession = Depends(get_session),
) -> TemplateRead:
    now = datetime.now(timezone.utc).isoformat()
    tmpl = ProductTemplate(
        name=body.name,
        price=body.price,
        vendor_name=body.vendor_name,
        category=body.category,
        dea_schedule=body.dea_schedule,
        reorder_threshold=body.reorder_threshold,
        created_at=now,
    )
    session.add(tmpl)
    await session.commit()
    await session.refresh(tmpl)
    return TemplateRead(
        id=tmpl.id, name=tmpl.name, price=float(tmpl.price),
        vendor_name=tmpl.vendor_name, category=tmpl.category,
        dea_schedule=tmpl.dea_schedule, reorder_threshold=tmpl.reorder_threshold,
        created_at=tmpl.created_at,
    )


@router.put("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: int,
    body: TemplateUpdate,
    _auth: CurrentUser = Depends(require_permission("templates.write")),
    session: AsyncSession = Depends(get_session),
) -> TemplateRead:
    tmpl = await session.get(ProductTemplate, template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if body.name is not None:
        tmpl.name = body.name
    if body.price is not None:
        tmpl.price = body.price
    if body.vendor_name is not None:
        tmpl.vendor_name = body.vendor_name
    if body.category is not None:
        tmpl.category = body.category
    if body.dea_schedule is not None:
        tmpl.dea_schedule = body.dea_schedule
    if body.reorder_threshold is not None:
        tmpl.reorder_threshold = body.reorder_threshold
    await session.commit()
    await session.refresh(tmpl)
    return TemplateRead(
        id=tmpl.id, name=tmpl.name, price=float(tmpl.price),
        vendor_name=tmpl.vendor_name, category=tmpl.category,
        dea_schedule=tmpl.dea_schedule, reorder_threshold=tmpl.reorder_threshold,
        created_at=tmpl.created_at,
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("templates.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    tmpl = await session.get(ProductTemplate, template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    await session.delete(tmpl)
    await session.commit()
