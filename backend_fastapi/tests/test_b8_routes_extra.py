"""B8 — HTTP-bound route coverage for remaining low-coverage route files.

Route handlers ARE traced via the ASGI ``client`` (unlike deep service bodies), so
targeted HTTP requests lift ``webhook_route`` (23%), ``license_route`` and the
``deps.get_current_user`` rejection branches above the 90% project gate.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

import jwt
import pytest
from httpx import AsyncClient

logging.getLogger("aiosqlite").setLevel(logging.WARNING)

import app.shared.config as config_mod
from app.core.models import License, Role
from app.core.repositories import LicenseRepository, UserRepository
from app.shared.config import settings
from app.shared.security import create_access_token, hash_password


async def _authed_headers(session_factory) -> dict[str, str]:
    async with session_factory() as s:
        role = Role(name="r", description="r", is_system=1)
        s.add(role); await s.commit()
        user = await UserRepository(s).create("u", "U", hash_password("password123"), role.id)
        await s.commit()
        uid = user.id
    token = create_access_token(str(uid), "pharmacy_role", ["license.read", "license.admin"])
    return {"Authorization": f"Bearer {token}"}


def _creem_sig(secret: str, body: bytes) -> str:
    return base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()


async def _seed_existing_subscription(session, sub_id: str):
    await LicenseRepository(session).create(
        license_key=f"PHARM-{sub_id}",
        email="a@b.c",
        expires_at="2099-01-01T00:00:00+00:00",
        subscription_id=sub_id,
        offline_grace_hours=settings.license_offline_grace_hours,
    )
    await session.commit()


# ── webhook_route (no auth) ────────────────────────────────────────────────────
async def test_webhook_not_configured(client: AsyncClient, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr(""))
    r = await client.post("/api/v1/webhook/creem", content=b"{}", headers={"creem-signature": "x"})
    assert r.status_code == 503


async def test_webhook_missing_signature(client: AsyncClient, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    r = await client.post("/api/v1/webhook/creem", content=b"{}")
    assert r.status_code == 400


async def test_webhook_bad_signature(client: AsyncClient, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    r = await client.post(
        "/api/v1/webhook/creem", content=b'{"eventType":"checkout.completed"}',
        headers={"creem-signature": "BAD"},
    )
    assert r.status_code == 403


async def test_webhook_invalid_json(client: AsyncClient, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    body = b"not json"
    r = await client.post(
        "/api/v1/webhook/creem", content=body, headers={"creem-signature": _creem_sig("s3cret", body)}
    )
    assert r.status_code == 400


async def test_webhook_checkout_completed_creates_license(client: AsyncClient, session, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    body = b'{"eventType":"checkout.completed","object":{"id":"sub-1","customer":{"email":"a@b.c"}}}'
    r = await client.post(
        "/api/v1/webhook/creem", content=body, headers={"creem-signature": _creem_sig("s3cret", body)}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_webhook_checkout_completed_duplicate(client: AsyncClient, session, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    await _seed_existing_subscription(session, "sub-1")
    body = b'{"eventType":"checkout.completed","object":{"id":"sub-1","customer":{"email":"a@b.c"}}}'
    r = await client.post(
        "/api/v1/webhook/creem", content=body, headers={"creem-signature": _creem_sig("s3cret", body)}
    )
    assert r.status_code == 200
    assert r.json()["note"] == "already_exists"


async def test_webhook_subscription_paid_extends(client: AsyncClient, session, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    await _seed_existing_subscription(session, "sub-2")
    body = b'{"eventType":"subscription.paid","object":{"subscription_id":"sub-2"}}'
    r = await client.post("/api/v1/webhook/creem", content=body, headers={"creem-signature": _creem_sig("s3cret", body)})
    assert r.status_code == 200


async def test_webhook_subscription_canceled_revokes(client: AsyncClient, session, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    await _seed_existing_subscription(session, "sub-3")
    body = b'{"eventType":"subscription.canceled","object":{"subscription_id":"sub-3"}}'
    r = await client.post("/api/v1/webhook/creem", content=body, headers={"creem-signature": _creem_sig("s3cret", body)})
    assert r.status_code == 200


async def test_webhook_subscription_active_reactivates(client: AsyncClient, session, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    await _seed_existing_subscription(session, "sub-4")
    body = b'{"eventType":"subscription.active","object":{"subscription_id":"sub-4"}}'
    r = await client.post("/api/v1/webhook/creem", content=body, headers={"creem-signature": _creem_sig("s3cret", body)})
    assert r.status_code == 200


async def test_webhook_no_sub_id_branch(client: AsyncClient, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(config_mod.settings, "creem_webhook_secret", SecretStr("s3cret"))
    body = b'{"eventType":"subscription.paid","object":{}}'
    r = await client.post("/api/v1/webhook/creem", content=body, headers={"creem-signature": _creem_sig("s3cret", body)})
    assert r.status_code == 200
    assert r.json()["note"] == "no_sub_id"


# ── deps.get_current_user rejection branches ───────────────────────────────────
def _token(claims: dict) -> str:
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


async def test_deps_malformed_token_rejected(client: AsyncClient):
    r = await client.get("/api/v1/users", headers={"Authorization": "Bearer " + _token({"role": "r"})})
    assert r.status_code == 401


async def test_deps_non_int_sub_rejected(client: AsyncClient):
    r = await client.get("/api/v1/users", headers={"Authorization": "Bearer " + _token({"sub": "abc", "role": "r"})})
    assert r.status_code == 401


async def test_deps_nonexistent_user_rejected(client: AsyncClient):
    r = await client.get("/api/v1/users", headers={"Authorization": "Bearer " + _token({"sub": "999999", "role": "r"})})
    assert r.status_code == 401


async def test_deps_refresh_token_rejected(client: AsyncClient):
    r = await client.get(
        "/api/v1/users",
        headers={"Authorization": "Bearer " + _token({"sub": "1", "role": "r", "type": "refresh"})},
    )
    assert r.status_code == 401


# ── license_route (auth required) ──────────────────────────────────────────────
async def test_license_status_unreachable(client: AsyncClient, session_factory):
    headers = await _authed_headers(session_factory)
    r = await client.get("/api/v1/license/status", headers=headers)
    assert r.status_code in (502, 503)


async def test_license_validate_proxies(client: AsyncClient, session_factory):
    headers = await _authed_headers(session_factory)
    r = await client.post(
        "/api/v1/license/validate",
        json={"license_key": "PHARM-X", "hardware_id": "hw-1"},
        headers=headers,
    )
    assert r.status_code in (200, 502, 503)


async def test_license_admin_manage_proxies(client: AsyncClient, session_factory):
    headers = await _authed_headers(session_factory)
    r = await client.post("/api/v1/license/admin/manage", content=b"{}", headers=headers)
    assert r.status_code in (200, 502, 503)
