"""Receipt Template service: CRUD + default seeding."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ReceiptTemplate
from app.shared.exceptions import AppException, NotFoundError
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    ReceiptTemplateCreate,
    ReceiptTemplateRead,
    ReceiptTemplateSection,
    ReceiptTemplateUpdate,
)

logger = get_logger("receipt_template")

_DEFAULT_RECEIPT_SECTIONS = [
    {"type": "header", "content": "PHARMACY RECEIPT", "align": "center", "font_bold": True, "visible": True},
    {"type": "text", "content": "{{receipt_number}}", "align": "center", "font_bold": False, "visible": True},
    {"type": "text", "content": "DATE: {{date}}", "align": "center", "font_bold": False, "visible": True},
    {"type": "separator", "content": "-", "align": "center", "font_bold": False, "visible": True},
    {"type": "text", "content": "PATIENT: {{patient_name}}", "align": "left", "font_bold": False, "visible": True},
    {"type": "separator", "content": "-", "align": "center", "font_bold": False, "visible": True},
    {"type": "items_header", "content": "Item                    Price", "align": "left", "font_bold": False, "visible": True},
    {"type": "items", "content": "", "align": "left", "font_bold": False, "visible": True},
    {"type": "separator", "content": "-", "align": "center", "font_bold": False, "visible": True},
    {"type": "total", "content": "TOTAL: {{total}}", "align": "right", "font_bold": True, "visible": True},
    {"type": "text", "content": "PAYMENT: {{payment_method}}", "align": "left", "font_bold": False, "visible": True},
    {"type": "text", "content": "CASHIER: {{cashier}}", "align": "left", "font_bold": False, "visible": True},
    {"type": "footer", "content": "THANK YOU!", "align": "center", "font_bold": False, "visible": True},
]


class ReceiptTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_templates(self, template_type: str = "") -> list[ReceiptTemplateRead]:
        stmt = select(ReceiptTemplate).order_by(ReceiptTemplate.is_default.desc(), ReceiptTemplate.name)
        if template_type:
            stmt = stmt.where(ReceiptTemplate.template_type == template_type)
        result = await self.session.execute(stmt)
        return [self._to_read(t) for t in result.scalars().all()]

    async def get_template(self, template_id: int) -> ReceiptTemplateRead:
        t = await self.session.get(ReceiptTemplate, template_id)
        if t is None:
            raise NotFoundError("ReceiptTemplate", str(template_id))
        return self._to_read(t)

    async def get_default(self, template_type: str = "receipt") -> ReceiptTemplateRead | None:
        result = await self.session.execute(
            select(ReceiptTemplate).where(
                ReceiptTemplate.is_default == 1,
                ReceiptTemplate.template_type == template_type,
            )
        )
        t = result.scalar_one_or_none()
        return self._to_read(t) if t else None

    async def create_template(self, payload: ReceiptTemplateCreate) -> ReceiptTemplateRead:
        # If setting as default, unset other defaults
        if payload.is_default:
            await self._unset_defaults(payload.template_type)
        sections_json = json.dumps([s.model_dump() for s in payload.sections])
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        t = ReceiptTemplate(
            name=payload.name,
            template_type=payload.template_type,
            paper_width=payload.paper_width,
            is_default=payload.is_default,
            sections=sections_json,
            created_at=now,
            updated_at=now,
        )
        self.session.add(t)
        await self.session.flush()
        return self._to_read(t)

    async def update_template(self, template_id: int, payload: ReceiptTemplateUpdate) -> ReceiptTemplateRead:
        t = await self.session.get(ReceiptTemplate, template_id)
        if t is None:
            raise NotFoundError("ReceiptTemplate", str(template_id))
        if payload.is_default:
            await self._unset_defaults(t.template_type)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "sections" and value is not None:
                setattr(t, field, json.dumps([s.model_dump() if isinstance(s, ReceiptTemplateSection) else s for s in value]))
            else:
                setattr(t, field, value)
        t.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        await self.session.flush()
        return self._to_read(t)

    async def delete_template(self, template_id: int) -> None:
        t = await self.session.get(ReceiptTemplate, template_id)
        if t is None:
            raise NotFoundError("ReceiptTemplate", str(template_id))
        if t.is_default:
            raise AppException("Cannot delete the default template", status_code=400, error_code="template_is_default")
        await self.session.delete(t)
        await self.session.flush()

    async def seed_defaults(self) -> None:
        """Create default receipt template if none exists."""
        result = await self.session.execute(
            select(ReceiptTemplate).where(ReceiptTemplate.template_type == "receipt")
        )
        if result.scalar_one_or_none() is None:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            t = ReceiptTemplate(
                name="Default Receipt",
                template_type="receipt",
                paper_width=42,
                is_default=1,
                sections=json.dumps(_DEFAULT_RECEIPT_SECTIONS),
                created_at=now,
                updated_at=now,
            )
            self.session.add(t)
            await self.session.flush()

    async def _unset_defaults(self, template_type: str) -> None:
        result = await self.session.execute(
            select(ReceiptTemplate).where(
                ReceiptTemplate.is_default == 1,
                ReceiptTemplate.template_type == template_type,
            )
        )
        for t in result.scalars().all():
            t.is_default = 0

    def _to_read(self, t: ReceiptTemplate) -> ReceiptTemplateRead:
        try:
            sections = [ReceiptTemplateSection(**s) for s in json.loads(t.sections)]
        except (json.JSONDecodeError, TypeError):
            sections = []
        return ReceiptTemplateRead(
            id=t.id, name=t.name, template_type=t.template_type,
            paper_width=t.paper_width, is_default=t.is_default,
            sections=sections, created_at=t.created_at, updated_at=t.updated_at,
        )
