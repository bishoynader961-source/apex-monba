"""Quick-SIG template service: CRUD + search for structured SIG templates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import QuickSigTemplate
from app.shared.exceptions import NotFoundError
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    QuickSigTemplateCreate,
    QuickSigTemplateRead,
    QuickSigTemplateUpdate,
)

logger = get_logger("quick_sig")


class QuickSigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_templates(self, favorites_only: bool = False, q: str = "") -> list[QuickSigTemplateRead]:
        """List templates, optionally filtering to favorites or searching by name/drug."""
        stmt = select(QuickSigTemplate).order_by(QuickSigTemplate.is_favorite.desc(), QuickSigTemplate.name)
        if favorites_only:
            stmt = stmt.where(QuickSigTemplate.is_favorite == 1)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    QuickSigTemplate.name.ilike(pattern),
                    QuickSigTemplate.drug_name.ilike(pattern),
                    QuickSigTemplate.directions.ilike(pattern),
                )
            )
        result = await self.session.execute(stmt)
        return [QuickSigTemplateRead.model_validate(t) for t in result.scalars().all()]

    async def get_template(self, template_id: int) -> QuickSigTemplateRead:
        t = await self.session.get(QuickSigTemplate, template_id)
        if t is None:
            raise NotFoundError("QuickSigTemplate", str(template_id))
        return QuickSigTemplateRead.model_validate(t)

    async def create_template(self, payload: QuickSigTemplateCreate) -> QuickSigTemplateRead:
        t = QuickSigTemplate(
            name=payload.name,
            drug_name=payload.drug_name,
            dose=payload.dose,
            route=payload.route,
            frequency=payload.frequency,
            duration=payload.duration,
            directions=payload.directions,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.session.add(t)
        await self.session.flush()
        return QuickSigTemplateRead.model_validate(t)

    async def update_template(self, template_id: int, payload: QuickSigTemplateUpdate) -> QuickSigTemplateRead:
        t = await self.session.get(QuickSigTemplate, template_id)
        if t is None:
            raise NotFoundError("QuickSigTemplate", str(template_id))
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(t, field, value)
        await self.session.flush()
        return QuickSigTemplateRead.model_validate(t)

    async def delete_template(self, template_id: int) -> None:
        t = await self.session.get(QuickSigTemplate, template_id)
        if t is None:
            raise NotFoundError("QuickSigTemplate", str(template_id))
        await self.session.delete(t)
        await self.session.flush()

    async def toggle_favorite(self, template_id: int) -> QuickSigTemplateRead:
        t = await self.session.get(QuickSigTemplate, template_id)
        if t is None:
            raise NotFoundError("QuickSigTemplate", str(template_id))
        t.is_favorite = 0 if t.is_favorite else 1
        await self.session.flush()
        return QuickSigTemplateRead.model_validate(t)

    _AUTO_FAVORITE_THRESHOLD = 5

    async def increment_usage(self, template_id: int) -> QuickSigTemplateRead:
        """Increment usage count; auto-favorite after threshold uses."""
        t = await self.session.get(QuickSigTemplate, template_id)
        if t is None:
            raise NotFoundError("QuickSigTemplate", str(template_id))
        t.usage_count += 1
        if t.usage_count >= self._AUTO_FAVORITE_THRESHOLD and not t.is_favorite:
            t.is_favorite = 1
            logger.info("auto_favorited", template_id=template_id, usage_count=t.usage_count)
        await self.session.flush()
        return QuickSigTemplateRead.model_validate(t)

    async def get_suggestions(self, query: str) -> list[QuickSigTemplateRead]:
        """Fuzzy search templates by name, drug, or directions."""
        if not query:
            return await self.list_templates(favorites_only=True)
        return await self.list_templates(q=query)
