"""Drug Confirmation API tests — GET /api/v1/drugs/confirm/{ndc}."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import DrugDictionary, Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import hash_password

_PERMS = ["dictionaries.read"]


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
    await UserRepository(session).create("druguser", "Drug", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "druguser", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session)}"}


# --- Unit tests (service layer) ---

async def test_confirm_ndc_local_found(session: AsyncSession) -> None:
    """Confirm NDC returns local entry when it exists in the drug_dictionary."""
    from app.services.drug_confirmation_service import DrugConfirmationService

    entry = DrugDictionary(
        ndc_code="00000000001", name="Aspirin", strength="500mg",
        form="Tablet", manufacturer="Bayer", dea_schedule=None,
        pill_image_url=None, source="local", last_verified="2026-01-01T00:00:00",
        created_at="2026-01-01T00:00:00",
    )
    session.add(entry)
    await session.commit()

    service = DrugConfirmationService(session)
    try:
        result = await service.confirm_ndc("00000-0000-01")
        assert result.found is True
        assert result.name == "Aspirin"
        assert result.strength == "500mg"
        assert result.source == "local"
    finally:
        await service.close()


async def test_confirm_ndc_not_found_calls_external(session: AsyncSession) -> None:
    """Confirm NDC falls back to FDA API when not found locally, then caches result."""
    from app.services.drug_confirmation_service import DrugConfirmationService

    service = DrugConfirmationService(session)
    try:
        mock_fda_data = {
            "brand_name": "TestDrug",
            "active_ingredients": [{"strength": "100mg"}],
            "labeler_name": "TestPharma",
            "openfda": {
                "dosage_form": ["Tablet"],
                "manufacturer_name": ["TestPharma"],
                "dea_schedule": ["CII"],
            },
        }
        with patch.object(service, '_lookup_external', new_callable=AsyncMock, return_value=mock_fda_data):
            result = await service.confirm_ndc("99999999999")
            assert result.found is True
            assert result.name == "TestDrug"
            assert result.source == "fda"

        # Verify it was cached locally
        local = await service._lookup_local("99999999999")
        assert local is not None
        assert local.name == "TestDrug"
    finally:
        await service.close()


async def test_confirm_ndc_invalid_format(session: AsyncSession) -> None:
    """Confirm NDC returns source='invalid_format' for NDCs not 11 digits."""
    from app.services.drug_confirmation_service import DrugConfirmationService

    service = DrugConfirmationService(session)
    try:
        result = await service.confirm_ndc("123")
        assert result.found is False
        assert result.source == "invalid_format"
    finally:
        await service.close()


async def test_confirm_ndc_not_found_anywhere(session: AsyncSession) -> None:
    """Confirm NDC returns source='not_found' when not in local DB and FDA returns nothing."""
    from app.services.drug_confirmation_service import DrugConfirmationService

    service = DrugConfirmationService(session)
    try:
        with patch.object(service, '_lookup_external', new_callable=AsyncMock, return_value=None):
            result = await service.confirm_ndc("00000000001")
            assert result.found is False
            assert result.source == "not_found"
    finally:
        await service.close()


async def test_parse_fda_result() -> None:
    """FDA result parser extracts correct fields."""
    from app.services.drug_confirmation_service import DrugConfirmationService

    fda_data = {
        "brand_name": "TestDrug",
        "active_ingredients": [{"strength": "100mg"}],
        "labeler_name": "TestPharma",
        "openfda": {
            "dosage_form": ["Tablet"],
            "manufacturer_name": ["TestPharma"],
            "dea_schedule": ["CII"],
        },
    }
    parsed = DrugConfirmationService._parse_fda_result(fda_data)
    assert parsed["name"] == "TestDrug"
    assert parsed["strength"] == "100mg"
    assert parsed["form"] == "Tablet"
    assert parsed["manufacturer"] == "TestPharma"
    assert parsed["dea_schedule"] == "CII"
    assert parsed["pill_image_url"] is None


# --- HTTP tests (route layer) ---

async def test_confirm_drug_route_local_hit(client: AsyncClient, session: AsyncSession, auth: dict[str, str]) -> None:
    """GET /api/v1/drugs/confirm/{ndc} returns 200 with local entry."""
    entry = DrugDictionary(
        ndc_code="12345678901", name="Ibuprofen", strength="200mg",
        form="Tablet", manufacturer="Advil", dea_schedule=None,
        pill_image_url=None, source="local", last_verified="2026-01-01T00:00:00",
        created_at="2026-01-01T00:00:00",
    )
    session.add(entry)
    await session.commit()

    resp = await client.get("/api/v1/drugs/confirm/12345-6789-01", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["name"] == "Ibuprofen"
    assert data["source"] == "local"


async def test_confirm_drug_route_invalid_ndc(client: AsyncClient, auth: dict[str, str]) -> None:
    """GET /api/v1/drugs/confirm/{ndc} returns 200 with found=False for invalid NDC."""
    resp = await client.get("/api/v1/drugs/confirm/123", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert data["source"] == "invalid_format"


async def test_confirm_drug_route_unauthorized(client: AsyncClient) -> None:
    """GET /api/v1/drugs/confirm/{ndc} returns 401 without token."""
    resp = await client.get("/api/v1/drugs/confirm/12345678901")
    assert resp.status_code in (401, 403)


async def test_confirm_drug_route_fda_fallback(client: AsyncClient, session: AsyncSession, auth: dict[str, str]) -> None:
    """GET /api/v1/drugs/confirm/{ndc} falls back to FDA when not in local DB."""
    mock_fda_data = {
        "brand_name": "FDA Drug",
        "active_ingredients": [{"strength": "50mg"}],
        "labeler_name": "FDA Corp",
        "openfda": {
            "dosage_form": ["Tablet"],
            "manufacturer_name": ["FDA Corp"],
            "dea_schedule": ["CIII"],
        },
    }

    from app.services.drug_confirmation_service import DrugConfirmationService
    with patch.object(DrugConfirmationService, '_lookup_external', new_callable=AsyncMock, return_value=mock_fda_data):
        resp = await client.get("/api/v1/drugs/confirm/55555555555", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["name"] == "FDA Drug"
        assert data["source"] == "fda"
