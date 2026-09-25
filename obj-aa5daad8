"""Label Template + Product Label service: CRUD for label layouts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import LabelTemplate, ProductLabel
from app.shared.logging_config import get_logger

logger = get_logger("label_template")


class LabelTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_templates(self) -> list[dict]:
        result = await self.session.execute(
            select(LabelTemplate).order_by(LabelTemplate.is_default.desc(), LabelTemplate.name)
        )
        return [self._to_dict(t) for t in result.scalars().all()]

    async def get_template(self, template_id: int) -> dict:
        t = await self.session.get(LabelTemplate, template_id)
        if t is None:
            raise ValueError(f"LabelTemplate {template_id} not found")
        return self._to_dict(t)

    async def create_template(self, name: str, canvas_width: int, canvas_height: int,
                               elements: list[dict], is_default: int = 0) -> dict:
        if is_default:
            await self._unset_defaults()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        t = LabelTemplate(
            name=name, canvas_width=canvas_width, canvas_height=canvas_height,
            elements=json.dumps(elements), is_default=is_default,
            created_at=now, updated_at=now,
        )
        self.session.add(t)
        await self.session.flush()
        return self._to_dict(t)

    async def update_template(self, template_id: int, name: str | None = None,
                               canvas_width: int | None = None, canvas_height: int | None = None,
                               elements: list[dict] | None = None, is_default: int | None = None) -> dict:
        t = await self.session.get(LabelTemplate, template_id)
        if t is None:
            raise ValueError(f"LabelTemplate {template_id} not found")
        if is_default:
            await self._unset_defaults()
        if name is not None:
            t.name = name
        if canvas_width is not None:
            t.canvas_width = canvas_width
        if canvas_height is not None:
            t.canvas_height = canvas_height
        if elements is not None:
            t.elements = json.dumps(elements)
        if is_default is not None:
            t.is_default = is_default
        t.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        await self.session.flush()
        return self._to_dict(t)

    async def delete_template(self, template_id: int) -> None:
        t = await self.session.get(LabelTemplate, template_id)
        if t is None:
            raise ValueError(f"LabelTemplate {template_id} not found")
        if t.is_default:
            raise ValueError("Cannot delete the default template")
        await self.session.delete(t)
        await self.session.flush()

    async def _unset_defaults(self) -> None:
        result = await self.session.execute(select(LabelTemplate).where(LabelTemplate.is_default == 1))
        for t in result.scalars().all():
            t.is_default = 0

    def _to_dict(self, t: LabelTemplate) -> dict:
        try:
            elements = json.loads(t.elements)
        except (json.JSONDecodeError, TypeError):
            elements = []
        return {
            "id": t.id, "name": t.name, "canvas_width": t.canvas_width,
            "canvas_height": t.canvas_height, "elements": elements,
            "is_default": t.is_default, "created_at": t.created_at, "updated_at": t.updated_at,
        }


class ProductLabelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_label(self, product_id: int) -> dict | None:
        result = await self.session.execute(
            select(ProductLabel).where(ProductLabel.product_id == product_id)
        )
        pl = result.scalar_one_or_none()
        if pl is None:
            return None
        return self._to_dict(pl)

    async def save_label(self, product_id: int, canvas_width: int, canvas_height: int,
                          elements: list[dict]) -> dict:
        result = await self.session.execute(
            select(ProductLabel).where(ProductLabel.product_id == product_id)
        )
        pl = result.scalar_one_or_none()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if pl:
            pl.canvas_width = canvas_width
            pl.canvas_height = canvas_height
            pl.elements = json.dumps(elements)
            pl.updated_at = now
        else:
            pl = ProductLabel(
                product_id=product_id, canvas_width=canvas_width,
                canvas_height=canvas_height, elements=json.dumps(elements),
                updated_at=now,
            )
            self.session.add(pl)
        await self.session.flush()
        return self._to_dict(pl)

    async def delete_label(self, product_id: int) -> None:
        result = await self.session.execute(
            select(ProductLabel).where(ProductLabel.product_id == product_id)
        )
        pl = result.scalar_one_or_none()
        if pl:
            await self.session.delete(pl)
            await self.session.flush()

    def _to_dict(self, pl: ProductLabel) -> dict:
        try:
            elements = json.loads(pl.elements)
        except (json.JSONDecodeError, TypeError):
            elements = []
        return {
            "id": pl.id, "product_id": pl.product_id,
            "canvas_width": pl.canvas_width, "canvas_height": pl.canvas_height,
            "elements": elements, "updated_at": pl.updated_at,
        }


class LabelAssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_assignment(self, medicine_id: int, quantity: int,
                                label_template_id: int | None = None,
                                canvas_width: int | None = None,
                                canvas_height: int | None = None,
                                elements: list[dict] | None = None,
                                created_by: int | None = None) -> dict:
        from app.core.models import LabelAssignment, LabelTemplate
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        
        # If label_template_id provided, copy its canvas/elements
        canvas_width_val = canvas_width
        canvas_height_val = canvas_height
        elements_val = elements
        
        if label_template_id is not None:
            template = await self.session.get(LabelTemplate, label_template_id)
            if template:
                try:
                    template_elements = json.loads(template.elements) if template.elements else []
                except (json.JSONDecodeError, TypeError):
                    template_elements = []
                canvas_width_val = canvas_width or template.canvas_width
                canvas_height_val = canvas_height or template.canvas_height
                elements_val = elements or template_elements
        
        assignment = LabelAssignment(
            medicine_id=medicine_id,
            quantity=quantity,
            label_template_id=label_template_id,
            canvas_width=canvas_width_val,
            canvas_height=canvas_height_val,
            elements=json.dumps(elements_val) if elements_val is not None else None,
            created_at=now,
            created_by=created_by,
        )
        self.session.add(assignment)
        await self.session.flush()
        return self._to_dict(assignment)

    async def list_assignments(self) -> list[dict]:
        from app.core.models import LabelAssignment
        result = await self.session.execute(
            select(LabelAssignment).order_by(LabelAssignment.created_at.desc())
        )
        return [self._to_dict(a) for a in result.scalars().all()]

    async def get_assignment(self, assignment_id: int) -> dict | None:
        from app.core.models import LabelAssignment
        assignment = await self.session.get(LabelAssignment, assignment_id)
        if assignment is None:
            return None
        return self._to_dict(assignment)

    async def delete_assignment(self, assignment_id: int) -> bool:
        from app.core.models import LabelAssignment
        assignment = await self.session.get(LabelAssignment, assignment_id)
        if assignment is None:
            return False
        await self.session.delete(assignment)
        await self.session.flush()
        return True

    def _to_dict(self, a) -> dict:
        try:
            elements = json.loads(a.elements) if a.elements else None
        except (json.JSONDecodeError, TypeError):
            elements = None
        return {
            "id": a.id,
            "medicine_id": a.medicine_id,
            "quantity": a.quantity,
            "label_template_id": a.label_template_id,
            "canvas_width": a.canvas_width,
            "canvas_height": a.canvas_height,
            "elements": elements,
            "created_at": a.created_at,
            "created_by": a.created_by,
        }
