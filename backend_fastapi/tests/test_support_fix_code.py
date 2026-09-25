"""Tests for POST /api/v1/support/fix-code/verify (SPEC-09 Stage 2.3).

Covers the HMAC signature contract end-to-end: route registration (the
endpoint previously 404'd because the router was never included), the success
path (signed code applied to system_settings), tamper rejection (403),
fail-closed behavior with no secret configured, unknown setting (404), bad
envelope (400), and reload_permissions.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SystemSetting
from app.core.repositories import UserRepository
from app.shared.security import hash_password

URL = "/api/v1/support/fix-code/verify"


async def _admin_token(client: AsyncClient, session: AsyncSession) -> str:
    """Admin user (role_id=1 → wildcard permissions bypass)."""
    await UserRepository(session).create(
        "fixadmin", "Fix Admin", hash_password("password123"), 1
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "fixadmin", "password": "password123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _admin_token(client, session)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Deterministic signing secret injected into the route module."""
    value = "test-fix-code-secret"

    class _Cfg:
        fix_code_secret = value

    monkeypatch.setattr(
        "app.api.routers.support_fix_route.get_settings", lambda: _Cfg()
    )
    return value


def _signed(payload: dict, secret: str) -> dict:
    from app.api.routers.support_fix_route import sign_payload

    return {
        "action": "update_setting",
        "payload": payload,
        "sig": sign_payload(payload, secret),
    }


# ── Registration (the 404 regression guard) ──────────────────────────────────


@pytest.mark.anyio
async def test_route_is_registered(client: AsyncClient) -> None:
    resp = await client.post(
        URL, json={"action": "x", "payload": {}, "sig": "y"}
    )
    # Registered: auth runs before anything else. An unregistered route 404s.
    assert resp.status_code == 401, f"expected 401 (unauthenticated), got {resp.status_code}"


# ── Success path ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_valid_code_updates_setting(
    client: AsyncClient, auth: dict, session: AsyncSession, secret: str
) -> None:
    session.add(SystemSetting(key="session_idle_minutes", value=b"30"))
    await session.commit()

    code = _signed({"key": "session_idle_minutes", "value": "60"}, secret)
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "action": "update_setting",
        "payload": {"key": "session_idle_minutes", "value": "60"},
    }

    session.expire_all()  # sync method; drop cached state, re-read committed row
    row = await session.get(SystemSetting, "session_idle_minutes")
    assert row.value.decode() == "60"


# ── Tamper / fail-closed ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tampered_payload_rejected_403(
    client: AsyncClient, auth: dict, secret: str
) -> None:
    code = _signed({"key": "session_idle_minutes", "value": "60"}, secret)
    code["payload"]["value"] = "9999"  # flip the value after signing
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 403
    assert "signature" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_tampered_signature_rejected_403(
    client: AsyncClient, auth: dict, secret: str
) -> None:
    code = _signed({"key": "session_idle_minutes", "value": "60"}, secret)
    code["sig"] = "0" * 64  # valid hex, wrong digest
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_fail_closed_without_secret(
    client: AsyncClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Cfg:
        fix_code_secret = ""

    monkeypatch.setattr(
        "app.api.routers.support_fix_route.get_settings", lambda: _Cfg()
    )
    code = _signed({"key": "k", "value": "v"}, "any-secret")
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 403


# ── Envelope / payload validation ────────────────────────────────────────────


@pytest.mark.anyio
async def test_unknown_setting_404(
    client: AsyncClient, auth: dict, secret: str
) -> None:
    code = _signed({"key": "no_such_setting", "value": "1"}, secret)
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 404
    assert "no_such_setting" in resp.json()["detail"]


@pytest.mark.anyio
async def test_update_setting_missing_value_400(
    client: AsyncClient, auth: dict, secret: str
) -> None:
    code = _signed({"key": "only_key"}, secret)
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_unknown_action_400(
    client: AsyncClient, auth: dict, session: AsyncSession, secret: str
) -> None:
    code = _signed({"key": "k", "value": "v"}, secret)
    code["action"] = "drop_tables"
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_reload_permissions_ok(
    client: AsyncClient, auth: dict, secret: str
) -> None:
    code = _signed({"key": "unused", "value": "unused"}, secret)
    code["action"] = "reload_permissions"
    resp = await client.post(URL, json=code, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["action"] == "reload_permissions"


# ── Auth gate ────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_unauthenticated_401(client: AsyncClient, secret: str) -> None:
    code = _signed({"key": "session_idle_minutes", "value": "60"}, secret)
    resp = await client.post(URL, json=code)
    assert resp.status_code == 401
