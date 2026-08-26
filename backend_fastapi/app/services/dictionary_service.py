"""Dictionary services: SIG code expansion, price-code lookup, NDC lookup (T6/T8)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import PriceCode, SigCode
from app.core.repositories import PriceCodeRepository, SigCodeRepository
from app.shared.schemas import (
    BatchRead,
    NDCLookupResult,
    PriceCodeRead,
    SigCodeParseResult,
    SigCodeRead,
)


class DictionaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def parse_sig(self, code: str) -> SigCodeParseResult:
        sig = await SigCodeRepository(self.session).parse(code)
        if sig is None:
            return SigCodeParseResult(code=code, matched=False, detail="no matching sig code")
        return SigCodeParseResult(code=code, matched=True, full_text=sig.full_text)

    async def sig_codes(self) -> list[SigCodeRead]:
        return [SigCodeRead.model_validate(s) for s in await SigCodeRepository(self.session).all()]

    async def lookup_price_code(self, code: str) -> Optional[PriceCodeRead]:
        pc = await PriceCodeRepository(self.session).get_by_code(code)
        return PriceCodeRead.model_validate(pc) if pc is not None else None

    async def price_codes(self) -> list[PriceCodeRead]:
        return [PriceCodeRead.model_validate(p) for p in await PriceCodeRepository(self.session).all()]

    async def lookup_ndc(self, q: str) -> NDCLookupResult:
        """Resolve an NDC code against stocked lots (A: returns found=False, not a 404).

        Searches ``inventory_extended.ndc_code`` and ``ndc_formatted`` (case-insensitive,
        normalized). On a miss returns ``found=False`` so the UI can offer to receive the
        never-stocked drug instead of blocking the pharmacist.
        """
        from app.core.repositories import BatchRepository
        from app.core.models import InventoryExtended

        normalized = (q or "").strip()
        result = await self.session.execute(
            select(InventoryExtended).where(
                InventoryExtended.ndc_code == normalized,
                (InventoryExtended.on_hand > 0),
            ).order_by(InventoryExtended.expiration_date)
        )
        lot = result.scalar_one_or_none()
        if lot is None:
            result = await self.session.execute(
                select(InventoryExtended).where(
                    InventoryExtended.ndc_formatted == normalized,
                    (InventoryExtended.on_hand > 0),
                ).order_by(InventoryExtended.expiration_date)
            )
            lot = result.scalar_one_or_none()
        if lot is None:
            return NDCLookupResult(found=False, q=q)
        return NDCLookupResult(found=True, q=q, item=BatchRead.model_validate(lot))
