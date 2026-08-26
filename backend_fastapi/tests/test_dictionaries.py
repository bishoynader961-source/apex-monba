"""M7 — dictionary routes: SIG codes, price codes, NDC lookup (T6 dictionaries_route)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    InventoryExtended,
    Permission,
    Product,
    Role,
    RolePermission,
)
from app.core.repositories import SigCodeRepository, UserRepository
from app.services.dictionary_service import DictionaryService
from app.shared.schemas import PriceCodeCreate, SigCodeCreate
from app.shared.security import hash_password

_PERMS = [    "dictionaries.read",
    "dictionaries.write",
]


async def _token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        await session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("dictuser", "Dict", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "dictuser", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session)}"}


async def test_parse_sig_found(session: AsyncSession) -> None:
    repo = SigCodeRepository(session)
    await repo.create(SigCodeCreate(code="BID", full_text="Take twice daily"))
    result = await DictionaryService(session).parse_sig("BID")
    assert result.matched is True
    assert result.full_text == "Take twice daily"


async def test_parse_sig_not_found(session: AsyncSession) -> None:
    result = await DictionaryService(session).parse_sig("XYZ")
    assert result.matched is False
    assert result.detail is not None


async def test_lookup_price_code_found(session: AsyncSession) -> None:
    from app.core.repositories import PriceCodeRepository
    pc = await PriceCodeRepository(session).create(
        PriceCodeCreate(code="GEN", description="Generic", price=Decimal("0.00"))
    )
    result = await DictionaryService(session).lookup_price_code("GEN")
    assert result is not None
    assert result.code == pc.code


async def test_lookup_price_code_missing(session: AsyncSession) -> None:
    result = await DictionaryService(session).lookup_price_code("NOPE")
    assert result is None


async def test_ndc_lookup_not_found(session: AsyncSession) -> None:
    result = await DictionaryService(session).lookup_ndc("00000-0000-00")
    assert result.found is False
    assert result.q == "00000-0000-00"


async def test_ndc_lookup_found(session: AsyncSession) -> None:
    session.add(Product(name="Amox", price=Decimal("10")))
    await session.flush()
    session.add(
        InventoryExtended(
            drug_name="Amox",
            ndc_code="00069-0168-24",
            lot_number="L1",
            expiration_date="2026-12-31",
            on_hand=30,
        )
    )
    await session.commit()
    result = await DictionaryService(session).lookup_ndc("00069-0168-24")
    assert result.found is True
    assert result.item is not None
    assert result.item.lot_number == "L1"


# ── HTTP route tests ─────────────────────────────────────────────────────────────

async def test_sig_codes_crud(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/dictionaries/sig-codes", headers=auth)
    assert resp.status_code == 200
    assert resp.json() == []

    created = await client.post(
        "/api/v1/dictionaries/sig-codes",
        json={"code": "BID", "full_text": "Twice daily"},
        headers=auth,
    )
    assert created.status_code == 201
    assert created.json()["code"] == "BID"

    listed = await client.get("/api/v1/dictionaries/sig-codes", headers=auth)
    assert len(listed.json()) == 1


async def test_parse_sig_code_route(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    await client.post(
        "/api/v1/dictionaries/sig-codes",
        json={"code": "TID", "full_text": "Three times daily"},
        headers=auth,
    )
    resp = await client.get("/api/v1/dictionaries/sig-codes/parse?code=TID", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["matched"] is True
    assert "three times" in resp.json()["full_text"].lower()

    miss = await client.get("/api/v1/dictionaries/sig-codes/parse?code=ZZZ", headers=auth)
    assert miss.json()["matched"] is False


async def test_price_codes_crud(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/dictionaries/price-codes", headers=auth)
    assert resp.status_code == 200

    created = await client.post(
        "/api/v1/dictionaries/price-codes",
        json={"code": "GEN", "description": "Generic", "price": "0.00"},
        headers=auth,
    )
    assert created.status_code == 201
    assert created.json()["code"] == "GEN"
    assert created.json()["price"] == "0.00"


async def test_ndc_lookup_route_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/dictionaries/ndc/lookup?q=00000-0000-00", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["found"] is False
    assert resp.json()["q"] == "00000-0000-00"
