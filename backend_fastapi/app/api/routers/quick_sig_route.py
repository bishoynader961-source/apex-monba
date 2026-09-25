"""Quick-SIG template routes: CRUD + search + favorites."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.quick_sig_service import QuickSigService
from app.shared.schemas import (
    CurrentUser,
    QuickSigTemplateCreate,
    QuickSigTemplateRead,
    QuickSigTemplateUpdate,
)

router = APIRouter(prefix="/api/v1/quick-sig", tags=["quick-sig"])


@router.get("/", response_model=list[QuickSigTemplateRead], status_code=status.HTTP_200_OK)
async def list_templates(
    favorites_only: bool = Query(default=False),
    q: str = Query(default=""),
    _auth: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> list[QuickSigTemplateRead]:
    return await QuickSigService(session).list_templates(favorites_only=favorites_only, q=q)


@router.get("/{template_id}", response_model=QuickSigTemplateRead, status_code=status.HTTP_200_OK)
async def get_template(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> QuickSigTemplateRead:
    return await QuickSigService(session).get_template(template_id)


@router.post("/", response_model=QuickSigTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: QuickSigTemplateCreate,
    _auth: CurrentUser = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> QuickSigTemplateRead:
    return await QuickSigService(session).create_template(payload)


@router.put("/{template_id}", response_model=QuickSigTemplateRead, status_code=status.HTTP_200_OK)
async def update_template(
    template_id: int,
    payload: QuickSigTemplateUpdate,
    _auth: CurrentUser = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> QuickSigTemplateRead:
    return await QuickSigService(session).update_template(template_id, payload)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    await QuickSigService(session).delete_template(template_id)


@router.post("/{template_id}/favorite", response_model=QuickSigTemplateRead, status_code=status.HTTP_200_OK)
async def toggle_favorite(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> QuickSigTemplateRead:
    return await QuickSigService(session).toggle_favorite(template_id)


@router.post("/{template_id}/use", response_model=QuickSigTemplateRead, status_code=status.HTTP_200_OK)
async def increment_usage(
    template_id: int,
    _auth: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> QuickSigTemplateRead:
    return await QuickSigService(session).increment_usage(template_id)


@router.get("/search/suggestions", response_model=list[QuickSigTemplateRead], status_code=status.HTTP_200_OK)
async def search_suggestions(
    q: str = Query(default=""),
    _auth: CurrentUser = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> list[QuickSigTemplateRead]:
    return await QuickSigService(session).get_suggestions(q)
