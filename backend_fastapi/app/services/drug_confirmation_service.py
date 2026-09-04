"""Drug Confirmation Service — hybrid local + external NDC validation.

Queries local drug_dictionary first; on miss, falls back to FDA NDC Directory API.
Caches external results locally for subsequent lookups.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import DrugDictionary
from app.shared.schemas import DrugConfirmResult


FDA_NDC_API_URL = "https://api.fda.gov/drug/ndc.json"


class DrugConfirmationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=5.0)
        return self._http_client

    @staticmethod
    def _normalize_ndc(ndc: str) -> str:
        """Strip non-digits from NDC."""
        return re.sub(r"[^0-9]", "", ndc)

    async def _lookup_local(self, ndc: str) -> Optional[DrugDictionary]:
        normalized = self._normalize_ndc(ndc)
        result = await self.session.execute(
            select(DrugDictionary).where(DrugDictionary.ndc_code == normalized)
        )
        return result.scalar_one_or_none()

    async def _lookup_external(self, ndc: str) -> dict[str, Any] | None:
        """Query FDA NDC Directory API."""
        normalized = self._normalize_ndc(ndc)
        if len(normalized) != 11:
            return None

        # FDA NDC API expects 11-digit NDC without dashes
        # Format for query: search for product_ndc:"12345678901"
        client = await self._get_http_client()
        try:
            response = await client.get(
                FDA_NDC_API_URL,
                params={
                    "search": f'product_ndc:"{normalized}"',
                    "limit": 1,
                },
            )
            if response.status_code != 200:
                return None
            data = response.json()
            results: list[dict[str, Any]] = data.get("results", [])
            if not results:
                return None
            return results[0]
        except Exception:
            return None

    @staticmethod
    def _parse_fda_result(fda_data: dict[str, Any]) -> dict[str, Any]:
        """Extract relevant fields from FDA NDC API response."""
        # FDA NDC response structure varies; extract common fields safely
        openfda = fda_data.get("openfda", {})
        return {
            "name": fda_data.get("brand_name")
                or (openfda.get("brand_name", [None])[0])
                or fda_data.get("generic_name")
                or (openfda.get("generic_name", [None])[0])
                or "Unknown Drug",
            "strength": fda_data.get("active_ingredients", [{}])[0].get("strength")
                if fda_data.get("active_ingredients") else None,
            "form": (openfda.get("dosage_form", [None])[0]),
            "manufacturer": fda_data.get("labeler_name")
                or (openfda.get("manufacturer_name", [None])[0]),
            "dea_schedule": (openfda.get("dea_schedule", [None])[0]),
            "pill_image_url": None,  # FDA doesn't provide pill images directly
        }

    async def _upsert_local(self, ndc: str, data: dict[str, Any]) -> DrugDictionary:
        """Insert or update local drug dictionary entry."""
        normalized = self._normalize_ndc(ndc)
        existing = await self._lookup_local(ndc)
        now = datetime.now(timezone.utc).isoformat()

        if existing:
            existing.name = data.get("name", existing.name)
            existing.strength = data.get("strength", existing.strength)
            existing.form = data.get("form", existing.form)
            existing.manufacturer = data.get("manufacturer", existing.manufacturer)
            existing.dea_schedule = data.get("dea_schedule", existing.dea_schedule)
            existing.pill_image_url = data.get("pill_image_url", existing.pill_image_url)
            existing.last_verified = now
            existing.source = data.get("source", "external")
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        new_entry = DrugDictionary(
            ndc_code=normalized,
            name=data.get("name", "Unknown Drug"),
            strength=data.get("strength"),
            form=data.get("form"),
            manufacturer=data.get("manufacturer"),
            dea_schedule=data.get("dea_schedule"),
            pill_image_url=data.get("pill_image_url"),
            source=data.get("source", "external"),
            last_verified=now,
            created_at=now,
        )
        self.session.add(new_entry)
        await self.session.commit()
        await self.session.refresh(new_entry)
        return new_entry

    async def confirm_ndc(self, ndc: str) -> DrugConfirmResult:
        """Confirm an NDC code — local first, then external fallback."""
        normalized = self._normalize_ndc(ndc)

        if len(normalized) != 11:
            return DrugConfirmResult(
                found=False,
                ndc=ndc,
                source="invalid_format",
            )

        # 1. Check local dictionary
        local = await self._lookup_local(ndc)
        if local:
            return DrugConfirmResult(
                found=True,
                ndc=ndc,
                name=local.name,
                strength=local.strength,
                form=local.form,
                manufacturer=local.manufacturer,
                dea_schedule=local.dea_schedule,
                pill_image_url=local.pill_image_url,
                source=local.source,
            )

        # 2. Fallback to external API
        external = await self._lookup_external(ndc)
        if external:
            parsed = self._parse_fda_result(external)
            parsed["source"] = "fda"
            await self._upsert_local(ndc, parsed)
            return DrugConfirmResult(found=True, ndc=ndc, **parsed)

        # 3. Not found anywhere
        return DrugConfirmResult(found=False, ndc=ndc, source="not_found")

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None