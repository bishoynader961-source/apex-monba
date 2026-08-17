"""M5/M6 — users listing, settings read, and license proxy fallback (502)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission, SystemSetting, User
from app.core.repositories import UserRepository
from app.shared.security import hash_password

_PERMS = ["inventory.read", "users.read", "pos.checkout", "license.admin"]


async def _token(client: AsyncClient, session: AsyncSession, perms: list[str]) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    created: list[Permission] = []
    for key in perms:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        created.append(p)
    await session.commit()
    for p in created:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "adminroot", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _token(client, session, _PERMS)
    return {"Authorization": f"Bearer {token}"}


# ── Users list ───────────────────────────────────────────────────────────────

async def test_list_users(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    session.add(User(username="alice", display_name="Alice", password_hash=hash_password("password123"), role_id=1))
    session.add(User(username="bob", display_name="Bob", password_hash=hash_password("password123"), role_id=1))
    await session.commit()
    resp = await client.get("/api/v1/users", headers=auth)
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()]
    assert "adminroot" in usernames
    assert "alice" in usernames


async def test_get_user_not_found(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/users/99999", headers=auth)
    assert resp.status_code == 404


# ── Settings ───────────────────────────────────────────────────────────────────

async def test_list_settings(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    session.add(SystemSetting(key="tax_rate", value=b"0.14"))
    await session.commit()
    resp = await client.get("/api/v1/settings", headers=auth)
    assert resp.status_code == 200
    settings = resp.json()
    assert any(s["key"] == "tax_rate" and s["value"] == "0.14" for s in settings)


# ── License proxy (R1/R6): 502 when Flask license service is unreachable ────────

async def test_license_status_502_when_unreachable(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], monkeypatch
) -> None:
    from app.shared import config as config_mod
    monkeypatch.setattr(config_mod.settings, "license_gate_url", "http://127.0.0.1:1")
    resp = await client.get("/api/v1/license/status", headers=auth)
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "license_unreachable"


async def test_license_validate_502_when_unreachable(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], monkeypatch
) -> None:
    from app.shared import config as config_mod
    monkeypatch.setattr(config_mod.settings, "license_gate_url", "http://127.0.0.1:1")
    resp = await client.post(
        "/api/v1/license/validate",
        json={"license_key": "PHARM-0000-0000-0000", "hardware_id": "hwid-1"},
        headers=auth,
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "license_unreachable"
