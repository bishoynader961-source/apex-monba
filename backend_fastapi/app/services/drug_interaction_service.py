"""Drug Interaction service: check pairs against known interactions."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import DrugInteraction
from app.shared.schemas import CurrentUser


@dataclass
class InteractionResult:
    drug_a: str
    drug_b: str
    severity: str
    description: str
    recommendation: str


class DrugInteractionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_interactions(self, drug_names: list[str]) -> list[InteractionResult]:
        """Check a list of drug names against known interactions."""
        if len(drug_names) < 2:
            return []

        normalized = sorted(set(d.strip().lower() for d in drug_names if d.strip()))
        if len(normalized) < 2:
            return []

        # Fetch all active interactions
        result = await self.session.execute(
            select(DrugInteraction).where(DrugInteraction.is_active == 1)
        )
        all_interactions = result.scalars().all()

        # Build lookup by normalized pair
        pair_map: dict[tuple[str, str], DrugInteraction] = {}
        for interaction in all_interactions:
            key = tuple(sorted([interaction.drug_a.strip().lower(), interaction.drug_b.strip().lower()]))
            pair_map[key] = interaction

        # Check all combinations
        found: list[InteractionResult] = []
        for a, b in combinations(normalized, 2):
            key = (a, b)
            if key in pair_map:
                ix = pair_map[key]
                found.append(InteractionResult(
                    drug_a=ix.drug_a, drug_b=ix.drug_b,
                    severity=ix.severity, description=ix.description,
                    recommendation=ix.recommendation,
                ))

        severity_order = {"contraindicated": 0, "severe": 1, "moderate": 2, "mild": 3}
        found.sort(key=lambda r: severity_order.get(r.severity, 99))
        return found

    async def list_interactions(self) -> list[DrugInteraction]:
        result = await self.session.execute(
            select(DrugInteraction).order_by(DrugInteraction.drug_a)
        )
        return list(result.scalars().all())

    async def create_interaction(
        self, drug_a: str, drug_b: str, severity: str,
        description: str, recommendation: str,
    ) -> DrugInteraction:
        ix = DrugInteraction(
            drug_a=drug_a.strip(), drug_b=drug_b.strip(),
            severity=severity, description=description,
            recommendation=recommendation,
        )
        self.session.add(ix)
        await self.session.flush()
        return ix

    async def update_interaction(
        self, interaction_id: int, severity: str | None = None,
        description: str | None = None, recommendation: str | None = None,
        is_active: int | None = None,
    ) -> DrugInteraction:
        ix = await self.session.get(DrugInteraction, interaction_id)
        if ix is None:
            raise ValueError(f"Interaction {interaction_id} not found")
        if severity is not None:
            ix.severity = severity
        if description is not None:
            ix.description = description
        if recommendation is not None:
            ix.recommendation = recommendation
        if is_active is not None:
            ix.is_active = is_active
        await self.session.flush()
        return ix

    async def delete_interaction(self, interaction_id: int) -> None:
        ix = await self.session.get(DrugInteraction, interaction_id)
        if ix is None:
            raise ValueError(f"Interaction {interaction_id} not found")
        await self.session.delete(ix)
        await self.session.flush()
