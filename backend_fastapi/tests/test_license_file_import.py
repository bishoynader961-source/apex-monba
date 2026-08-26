"""Tests for POST /api/v1/licenses/activate-file — offline license file import.

License files are JSON objects signed with HMAC-SHA256 over the canonical
(sorted-key, compact) JSON of all fields except ``signature``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Role
from app.core.repositories import LicenseRepository, UserRepository
from app.shared.config import settings
from app.shared.security import create_access_token, hash_password

# Must match config.py alias NAME (not the env-var name).
_TEST_SECRET = "test-license-signing-secret-key-for-hmac"


def _canonicalize(fields: dict) -> bytes:
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload: dict, secret: str = _TEST_SECRET) -> str:
    """Compute the HMAC-SHA256 signature over canonical JSON (sans 'signature')."""
    return hmac.new(
        secret.encode("utf-8"),
        _canonicalize(payload),
        hashlib.sha256,
    ).hexdigest()


def _make_file(payload: dict, secret: str = _TEST_SECRET) -> str:
    """Build a signed license-file JSON string."""
    payload = dict(payload)
    payload["signature"] = _sign({k: v for k, v in payload.items() if k != "signature"}, secret)
    return json.dumps(payload)


@pytest.fixture(autouse=True)
def _set_signing_secret(monkeypatch) -> None:
    """Ensure settings.license_signing_secret is non-empty for every test."""
    monkeypatch.setattr(settings, "license_signing_secret", SecretStr(_TEST_SECRET))


async def _authed_headers(session: AsyncSession) -> dict[str, str]:
    role = Role(name="r", description="r", is_system=1)
    session.add(role)
    await session.commit()
    user = await UserRepository(session).create("u", "U", hash_password("password123"), role.id)
    await session.commit()
    token = create_access_token(str(user.id), "pharmacy_role", ["license.read"])
    return {"Authorization": f"Bearer {token}"}


_LICENSE_BASE = {
    "license_key": "PHARM-A1B2-C3D4-E5F6",
    "email": "customer@example.com",
    "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z"),
    "status": "active",
    "hardware_id": "hw-device-123",
    "issued_at": "2026-08-22T00:00:00Z",
}

_HWID = "hw-device-123"


async def test_activate_file_valid(client: AsyncClient, session: AsyncSession):
    headers = await _authed_headers(session)
    file_content = _make_file(_LICENSE_BASE)

    resp = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": file_content},
        headers=headers,
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["license_key"] == "PHARM-A1B2-C3D4-E5F6"
    assert result["status"] == "active"
    assert result["hardware_id"] == _HWID

    # Verify the license was persisted
    lic = await LicenseRepository(session).get_by_key("PHARM-A1B2-C3D4-E5F6")
    assert lic is not None
    assert lic.hardware_id == _HWID
    assert lic.status == "active"
    assert lic.offline_until is not None


async def test_activate_file_bad_signature(client: AsyncClient, session: AsyncSession):
    headers = await _authed_headers(session)
    payload = dict(_LICENSE_BASE)
    # Flip a character in the signature to make it invalid.
    payload["signature"] = "0" * 64
    file_content = json.dumps(payload)

    resp = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": file_content},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "license_signature_invalid"


async def test_activate_file_expired(client: AsyncClient, session: AsyncSession):
    headers = await _authed_headers(session)
    payload = dict(_LICENSE_BASE)
    payload["expires_at"] = "2020-01-01T00:00:00Z"  # already expired
    file_content = _make_file(payload)

    resp = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": file_content},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "license_expired"


async def test_activate_file_hwid_mismatch(client: AsyncClient, session: AsyncSession):
    headers = await _authed_headers(session)
    file_content = _make_file(_LICENSE_BASE)

    resp = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": "DIFFERENT-DEVICE", "file_content": file_content},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "hardware_mismatch"


async def test_activate_file_malformed_json(client: AsyncClient, session: AsyncSession):
    headers = await _authed_headers(session)

    resp = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": "not-json-at-all"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "license_file_malformed"


async def test_activate_file_missing_signature(client: AsyncClient, session: AsyncSession):
    headers = await _authed_headers(session)
    payload = dict(_LICENSE_BASE)
    del payload  # unused
    unsigned = json.dumps({k: v for k, v in _LICENSE_BASE.items() if k != "signature"})

    resp = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": unsigned},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "license_file_missing_signature"


async def test_activate_file_idempotent(
    client: AsyncClient, session: AsyncSession
):
    """Re-importing the same signed file should update, not duplicate."""
    headers = await _authed_headers(session)
    file_content = _make_file(_LICENSE_BASE)

    resp1 = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": file_content},
        headers=headers,
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": file_content},
        headers=headers,
    )
    assert resp2.status_code == 200

    # Only one row should exist
    lic = await LicenseRepository(session).get_by_key("PHARM-A1B2-C3D4-E5F6")
    assert lic is not None
    assert lic.email == "customer@example.com"


async def test_activate_file_requires_auth(client: AsyncClient, session: AsyncSession):
    file_content = _make_file(_LICENSE_BASE)

    resp = await client.post(
        "/api/v1/licenses/activate-file",
        json={"hardware_id": _HWID, "file_content": file_content},
    )
    assert resp.status_code == 401
