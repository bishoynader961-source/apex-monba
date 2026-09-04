"""Dictionary routes: SIG codes, price codes, NDC lookup (F5 / A NDC fallback)."""
from __future__ import annotations

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import PriceCodeRepository, SigCodeRepository
from app.services.dictionary_service import DictionaryService
from app.shared.schemas import (
    NDCLookupResult,
    PriceCodeCreate,
    PriceCodeRead,
    PriceCodeUpdate,
    PriceCalculationResult,
    SigCodeCreate,
    SigCodeParseResult,
    SigCodeRead,
    SigCodeUpdate,
)

router = APIRouter(prefix="/api/v1/dictionaries", tags=["dictionaries"])


@router.get("/sig-codes", response_model=List[SigCodeRead])
async def list_sig_codes(
    _auth: object = Depends(require_permission("dictionaries.read")),
    session: AsyncSession = Depends(get_session),
) -> List[SigCodeRead]:
    return await DictionaryService(session).sig_codes()


@router.post("/sig-codes", response_model=SigCodeRead, status_code=status.HTTP_201_CREATED)
async def create_sig_code(
    payload: SigCodeCreate,
    _auth: object = Depends(require_permission("dictionaries.write")),
    session: AsyncSession = Depends(get_session),
) -> SigCodeRead:
    return SigCodeRead.model_validate(await SigCodeRepository(session).create(payload))


@router.put("/sig-codes/{sig_id}", response_model=SigCodeRead)
async def update_sig_code(
    sig_id: int,
    payload: SigCodeUpdate,
    _auth: object = Depends(require_permission("dictionaries.write")),
    session: AsyncSession = Depends(get_session),
) -> SigCodeRead:
    sig = await SigCodeRepository(session).update(sig_id, payload)
    if not sig:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SigCode not found")
    return SigCodeRead.model_validate(sig)


@router.delete("/sig-codes/{sig_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sig_code(
    sig_id: int,
    _auth: object = Depends(require_permission("dictionaries.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    deleted = await SigCodeRepository(session).delete(sig_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SigCode not found")


@router.get("/sig-codes/parse", response_model=SigCodeParseResult)
async def parse_sig_code(
    code: str = Query(..., min_length=1),
    _auth: object = Depends(require_permission("dictionaries.read")),
    session: AsyncSession = Depends(get_session),
) -> SigCodeParseResult:
    return await DictionaryService(session).parse_sig(code)


@router.get("/price-codes", response_model=List[PriceCodeRead])
async def list_price_codes(
    _auth: object = Depends(require_permission("dictionaries.read")),
    session: AsyncSession = Depends(get_session),
) -> List[PriceCodeRead]:
    return await DictionaryService(session).price_codes()


@router.post("/price-codes", response_model=PriceCodeRead, status_code=status.HTTP_201_CREATED)
async def create_price_code(
    payload: PriceCodeCreate,
    _auth: object = Depends(require_permission("dictionaries.write")),
    session: AsyncSession = Depends(get_session),
) -> PriceCodeRead:
    return PriceCodeRead.model_validate(await PriceCodeRepository(session).create(payload))


@router.put("/price-codes/{price_code_id}", response_model=PriceCodeRead)
async def update_price_code(
    price_code_id: int,
    payload: PriceCodeUpdate,
    _auth: object = Depends(require_permission("dictionaries.write")),
    session: AsyncSession = Depends(get_session),
) -> PriceCodeRead:
    pc = await PriceCodeRepository(session).update(price_code_id, payload)
    if not pc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PriceCode not found")
    return PriceCodeRead.model_validate(pc)


@router.delete("/price-codes/{price_code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price_code(
    price_code_id: int,
    _auth: object = Depends(require_permission("dictionaries.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    deleted = await PriceCodeRepository(session).delete(price_code_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PriceCode not found")


@router.get("/price-codes/{price_code_id}/calculate", response_model=PriceCalculationResult)
async def calculate_price(
    price_code_id: int,
    acquisition_cost: float = Query(..., gt=0),
    _auth: object = Depends(require_permission("dictionaries.read")),
    session: AsyncSession = Depends(get_session),
) -> PriceCalculationResult:
    pc = await PriceCodeRepository(session).get(price_code_id)
    if not pc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PriceCode not found")
    computed, clamped = PriceCodeRepository(session).calculate_price(pc, Decimal(str(acquisition_cost)))
    return PriceCalculationResult(computed_price=computed, clamped=clamped)


@router.get("/ndc/lookup", response_model=NDCLookupResult)
async def ndc_lookup(
    q: str = Query(..., min_length=1),
    _auth: object = Depends(require_permission("dictionaries.read")),
    session: AsyncSession = Depends(get_session),
) -> NDCLookupResult:
    return await DictionaryService(session).lookup_ndc(q)
