"""Phase 7: Integrations route tests — drug evaluate (mock + cache) + CRUD."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission, User
from app.shared.security import hash_password


async def _seed_user(session: AsyncSession, perms: list[str]) -> str:
    role = Role(name="test_role", description="test", is_system=1)
    session.add(role)
    await session.flush()
    perms_objs = []
    for key in perms:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms_objs.append(p)
    await session.flush()
    for p in perms_objs:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.flush()
    user = User(
        username="test_integ",
        display_name="Test",
        password_hash=hash_password("password123"),
        role_id=role.id,
    )
    session.add(user)
    await session.commit()
    return "test_integ"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ─── Drug Evaluate — Mock Path ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluate_drug_safe(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["inventory.read"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    res = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": "Metformin"},
        headers=_auth_header(token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "safe"
    assert data["source"] == "mock"
    assert data["cached"] is False
    assert isinstance(data["interactions"], list)


@pytest.mark.asyncio
async def test_evaluate_drug_warning(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["inventory.read"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    res = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": "Warfarin"},
        headers=_auth_header(token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "warning"
    assert len(data["interactions"]) > 0


@pytest.mark.asyncio
async def test_evaluate_drug_severe(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["inventory.read"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    res = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": "Digoxin"},
        headers=_auth_header(token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "severe"


@pytest.mark.asyncio
async def test_evaluate_drug_unknown_returns_safe(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["inventory.read"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    res = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": "NonExistentDrug"},
        headers=_auth_header(token),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "safe"


@pytest.mark.asyncio
async def test_evaluate_drug_cache_hit(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["inventory.read"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    # First call — not cached
    r1 = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": "Aspirin"},
        headers=_auth_header(token),
    )
    assert r1.json()["cached"] is False

    # Second call — should be cached
    r2 = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": "Aspirin"},
        headers=_auth_header(token),
    )
    assert r2.status_code == 200
    assert r2.json()["cached"] is True
    assert r2.json()["status"] == r1.json()["status"]


@pytest.mark.asyncio
async def test_evaluate_drug_empty_name_rejected(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["inventory.read"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    res = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": ""},
        headers=_auth_header(token),
    )
    assert res.status_code == 422


# ─── Integration CRUD ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_integration(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["settings.manage"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    res = await client.post(
        "/api/v1/integrations",
        json={"provider_name": "drug_evaluate", "api_key": "test-key-123", "base_url": "https://api.example.com"},
        headers=_auth_header(token),
    )
    assert res.status_code == 201
    data = res.json()
    assert data["provider_name"] == "drug_evaluate"
    assert data["is_active"] == 1


@pytest.mark.asyncio
async def test_list_integrations(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["settings.read"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    res = await client.get("/api/v1/integrations", headers=_auth_header(token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_upsert_integration_updates_existing(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, ["settings.manage"])
    login = await client.post("/api/v1/auth/login", json={"username": "test_integ", "password": "password123"})
    token = login.json()["access_token"]

    # Create
    await client.post(
        "/api/v1/integrations",
        json={"provider_name": "test_provider", "api_key": "key1"},
        headers=_auth_header(token),
    )

    # Upsert with same provider_name
    res = await client.post(
        "/api/v1/integrations",
        json={"provider_name": "test_provider", "api_key": "key2", "base_url": "https://new.example.com"},
        headers=_auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["base_url"] == "https://new.example.com"


# ─── Auth Rejection ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluate_drug_unauthorized(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/drugs/evaluate",
        json={"drug_name": "Aspirin"},
    )
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_integrations_list_unauthorized(client: AsyncClient) -> None:
    res = await client.get("/api/v1/integrations")
    assert res.status_code in (401, 403)
