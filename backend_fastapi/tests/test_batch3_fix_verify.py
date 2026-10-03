"""Batch 3 (audit M4): server-side fix-code verification for the desktop engine.

The desktop binary no longer embeds FIX_CODE_SECRET / FIX_ADMIN_KEY; the Rust
fix engine POSTs the raw code + admin key to
``POST /api/v1/admin/fix/verify`` and fails closed on anything but
``{"valid": true}``. These tests pin the fail-closed behaviour.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

from app.api.routers.support_fix_route import sign_payload
from app.shared.config import settings

ADMIN_KEY = "batch3-admin-key-abcdef0123456789"
CODE_SECRET = "batch3-fix-code-secret-0123456789"
CLIENT_VERSION = "1.0.0"
VERIFY_URL = "/api/v1/admin/fix/verify"


def _code(
    *,
    action: str = "update_setting",
    key: str = "terminal_mode",
    value: str = "client",
    secret: str = CODE_SECRET,
    version: str = CLIENT_VERSION,
    expires_in: int = 600,
    tamper_after_signing: bool = False,
) -> str:
    payload = {
        "key": key,
        "value": value,
        "expiresAt": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
        "version": version,
    }
    envelope = {"action": action, "payload": payload, "sig": sign_payload(payload, secret)}
    if tamper_after_signing:
        envelope["payload"]["value"] = "attacker-controlled"
    return json.dumps(envelope)


async def _post(client: AsyncClient, fix_code: str | None, **extra) -> dict:
    body = {"admin_key": ADMIN_KEY, "client_version": CLIENT_VERSION, "fix_code": fix_code, **extra}
    resp = await client.post(VERIFY_URL, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "fix_code_secret", CODE_SECRET)
    monkeypatch.setattr(settings, "fix_admin_key", ADMIN_KEY)


async def test_valid_fix_code_accepted(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    body = await _post(client, _code())
    assert body["valid"] is True
    assert body["action"] == "update_setting"
    assert body["payload"]["key"] == "terminal_mode"
    assert body["ops"] == ["terminal_mode"]


async def test_invalid_signature_rejected(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    body = await _post(client, _code(tamper_after_signing=True))
    assert body == {"valid": False, "action": None, "payload": None, "ops": []}


async def test_wrong_hmac_rejected(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    body = await _post(client, _code(secret="a-different-secret"))
    assert body["valid"] is False
    assert body["ops"] == []


async def test_non_whitelisted_operation_rejected_even_with_valid_hmac(
    client: AsyncClient, monkeypatch
) -> None:
    _enable(monkeypatch)
    # Valid signature, but the setting key is not whitelisted.
    body = await _post(client, _code(key="evil_backdoor_setting"))
    assert body["valid"] is False
    # Valid signature, but the action is not whitelisted at all.
    body = await _post(client, _code(action="run_shell", key="terminal_mode"))
    assert body["valid"] is False


async def test_expired_code_rejected(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    body = await _post(client, _code(expires_in=-60))
    assert body["valid"] is False


async def test_version_mismatch_rejected(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    body = await _post(client, _code(version="9.9.0"))
    assert body["valid"] is False


async def test_wrong_admin_key_rejected(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    resp = await client.post(
        VERIFY_URL,
        json={"admin_key": "wrong-key", "client_version": CLIENT_VERSION, "fix_code": _code()},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


async def test_missing_secret_fails_closed(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "fix_code_secret", CODE_SECRET)
    monkeypatch.setattr(settings, "fix_admin_key", "")
    body = await _post(client, _code())
    assert body["valid"] is False

    monkeypatch.setattr(settings, "fix_admin_key", ADMIN_KEY)
    monkeypatch.setattr(settings, "fix_code_secret", "")
    body = await _post(client, _code())
    assert body["valid"] is False


async def test_admin_key_only_reset_config(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    body = await _post(client, None, requested_action="reset_config")
    assert body["valid"] is True
    assert body["action"] == "reset_config"
    assert body["ops"] == ["reset_config"]

    # Any other admin-key-only request (e.g. an arbitrary action) is denied.
    body = await _post(client, None, requested_action="run_shell")
    assert body["valid"] is False


async def test_malformed_fix_code_rejected(client: AsyncClient, monkeypatch) -> None:
    _enable(monkeypatch)
    assert (await _post(client, "not-json"))["valid"] is False
    assert (await _post(client, json.dumps({"action": 1, "payload": [], "sig": None})))["valid"] is False
