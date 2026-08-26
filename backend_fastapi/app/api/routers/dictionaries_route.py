"""Dictionary routes: SIG codes, price codes, NDC lookup (F5 / A NDC fallback)."""
from __future__ import annotations

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
    SigCodeCreate,
    SigCodeParseResult,
    SigCodeRead,
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


@router.get("/ndc/lookup", response_model=NDCLookupResult)
async def ndc_lookup(
    q: str = Query(..., min_length=1),
    _auth: object = Depends(require_permission("dictionaries.read")),
    session: AsyncSession = Depends(get_session),
) -> NDCLookupResult:
    return await DictionaryService(session).lookup_ndc(q)
