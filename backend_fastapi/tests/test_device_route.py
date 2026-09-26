"""Phase 4 Step 1.5 — QR gateway, device model, mobile pairing.

Covers the two owner-mandated checks:
  CHECK A — QR expiry is enforced exactly once, at pairing time
            (POST /api/v1/auth/mobile-register). Expired or unsigned QR
            payloads are rejected with 401; after pairing the QR is never
            re-validated.
  CHECK B — device revocation is enforced on EVERY authenticated request
            that presents X-Device-Token: revoked or unknown device → 401
            (the mobile client clears tokens and returns to login on 401).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.device_route import compute_network_key, get_qr_secret
from app.core.models import Role
from app.core.repositories import UserRepository
from app.main import app
from app.shared.security import hash_password


async def _admin_token(client: AsyncClient, session: AsyncSession) -> str:
    """role_id=1 owner user — implicit full access."""
    role = Role(name="owner", description="owner", is_system=1)
    session.add(role)
    await session.commit()
    await UserRepository(session).create(
        "pairadmin", "Pair Admin", hash_password("password123"), role.id
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "pairadmin", "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _admin_token(client, session)}"}


def _bearer(auth: dict[str, str]) -> str:
    return auth["Authorization"].split(" ", 1)[1]


async def _pair_device(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> str:
    """Pair via the real endpoints, mirroring the server's HMAC computation.

    The signing secret is read from the same test session the API uses (the
    API itself never returns it). Returns the one-time device token.
    """
    qr = await client.get("/api/v1/devices/qr-payload", headers=auth)
    assert qr.status_code == 200, qr.text
    payload = qr.json()
    assert "qr_secret" not in payload and "secret" not in payload

    secret = await get_qr_secret(session)
    network_key = compute_network_key(
        payload["url"], payload["instance_id"], payload["expires_at"], secret
    )
    resp = await client.post(
        "/api/v1/auth/mobile-register",
        json={
            "instance_id": payload["instance_id"],
            "device_id": "test-device-uuid",
            "device_name": "Test Phone",
            "url": payload["url"],
            "network_key": network_key,
            "qr_expires_at": payload["expires_at"],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["device_token"]


# ── qr_secret_key lifecycle ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_qr_payload_shape_and_no_secret(client: AsyncClient, auth: dict[str, str]) -> None:
    r1 = await client.get("/api/v1/devices/qr-payload", headers=auth)
    r2 = await client.get("/api/v1/devices/qr-payload", headers=auth)
    assert r1.status_code == 200 and r2.status_code == 200
    p1, p2 = r1.json(), r2.json()
    assert set(p1) == {"url", "instance_id", "api_version", "expires_at", "network_key"}
    assert p1["instance_id"] == p2["instance_id"]
    assert p1["expires_at"] != p2["expires_at"], "each fetch mints a fresh 24h window"


# ── CHECK A: expiry + signature checked once, at pairing ────────────────────
@pytest.mark.asyncio
async def test_pair_rejects_expired_qr(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    payload = (await client.get("/api/v1/devices/qr-payload", headers=auth)).json()
    secret = await get_qr_secret(session)
    network_key = compute_network_key(
        payload["url"], payload["instance_id"], payload["expires_at"], secret
    )
    resp = await client.post(
        "/api/v1/auth/mobile-register",
        json={
            "instance_id": payload["instance_id"],
            "device_id": "test-device-uuid",
            "device_name": "Test Phone",
            "url": payload["url"],
            "network_key": network_key,
            "qr_expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        },
        headers=auth,
    )
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pair_rejects_bad_signature(client: AsyncClient, auth: dict[str, str]) -> None:
    payload = (await client.get("/api/v1/devices/qr-payload", headers=auth)).json()
    resp = await client.post(
        "/api/v1/auth/mobile-register",
        json={
            "instance_id": payload["instance_id"],
            "device_id": "test-device-uuid",
            "device_name": "Test Phone",
            "url": payload["url"],
            "network_key": "0" * 64,
            "qr_expires_at": payload["expires_at"],
        },
        headers=auth,
    )
    assert resp.status_code == 401
    assert "signature" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pair_succeeds_and_token_listed_never_plaintext(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    token = await _pair_device(client, auth, session)
    assert token.startswith("phd_") and len(token) >= 60

    devices = (await client.get("/api/v1/devices", headers=auth)).json()
    assert len(devices) == 1
    assert devices[0]["device_name"] == "Test Phone"
    assert devices[0]["revoked"] == 0
    assert not any("token" in k.lower() for k in devices[0]), (
        "plain device token must never appear in device listings"
    )


# ── CHECK B: revocation enforced on every authenticated request ─────────────
@pytest.mark.asyncio
async def test_revoked_device_gets_401_on_every_request(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    device_token = await _pair_device(client, auth, session)
    probe_headers = {
        "Authorization": f"Bearer {_bearer(auth)}",
        "X-Device-Token": device_token,
    }
    ok = await client.get("/api/v1/auth/me", headers=probe_headers)
    assert ok.status_code == 200, ok.text

    devices = (await client.get("/api/v1/devices", headers=auth)).json()
    revoke = await client.delete(f"/api/v1/devices/{devices[0]['id']}", headers=auth)
    assert revoke.status_code == 204

    after = await client.get("/api/v1/auth/me", headers=probe_headers)
    assert after.status_code == 401, after.text
    assert "revoked" in after.json()["detail"].lower()

    # CHECK B is a dependency-level guarantee: EVERY route, not just /auth/me.
    other = await client.get("/api/v1/patients?page_size=1", headers=probe_headers)
    assert other.status_code == 401


@pytest.mark.asyncio
async def test_unknown_device_token_is_401(client: AsyncClient, auth: dict[str, str]) -> None:
    probe_headers = {
        "Authorization": f"Bearer {_bearer(auth)}",
        "X-Device-Token": "phd_unknown",
    }
    resp = await client.get("/api/v1/auth/me", headers=probe_headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_requests_without_device_header_unaffected(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    """Desktop (no X-Device-Token) auth is untouched by the device gate."""
    resp = await client.get("/api/v1/auth/me", headers=auth)
    assert resp.status_code == 200


# ── Device management ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_devices_list_requires_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A non-admin user with no permissions gets 403 on the device list."""
    # Conftest restarts role ids per test DB: insert a filler first so the
    # clerk's role is NOT id 1 (id 1 = owner bypass in require_permission).
    session.add(Role(name="filler", description="id-1 filler", is_system=1))
    await session.commit()
    role = Role(name="clerk_pair", description="clerk", is_system=1)
    session.add(role)
    await session.commit()
    await UserRepository(session).create(
        "pairclerk", "Pair Clerk", hash_password("password123"), role.id
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "pairclerk", "password": "password123"}
    )
    token = resp.json()["access_token"]
    r = await client.get("/api/v1/devices", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# app import is required so the routers register before the client fixture runs.
assert app is not None
