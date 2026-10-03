"""Batch 4 (audit M7): the indexed device-token lookup replaces O(N) bcrypt.

Device auth previously loaded every unrevoked ``devices`` row and ran bcrypt
against each one per request. New pairings store SHA-256(token)[:16] in the
indexed ``devices.token_prefix`` column, so only rows sharing that prefix are
verified. Pre-v31 rows (token_prefix NULL) keep authenticating through the
full-scan fallback.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.device_route import compute_network_key, get_qr_secret
from app.core.models import Device, Role, SystemSetting
from app.core.repositories import UserRepository
from app.shared.security import device_token_prefix, hash_password, verify_password


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _admin_headers(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    """role_id=1 owner user — implicit full access."""
    role = Role(name="owner-m7", description="owner", is_system=1)
    session.add(role)
    await session.commit()
    await UserRepository(session).create(
        "m7admin", "M7 Admin", hash_password("password123"), role.id
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "m7admin", "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _device(token: str, *, revoked: int = 0, legacy: bool = False) -> Device:
    return Device(
        device_name=f"dev-{token[-6:]}",
        device_token_hash=hash_password(token),
        token_prefix=None if legacy else device_token_prefix(token),
        user_id=None,
        created_at=_now(),
        last_seen_at=None,
        revoked=revoked,
    )


@pytest.fixture
def bcrypt_counter(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count bcrypt verifications performed by the device-auth dependency."""
    calls = {"n": 0}
    real = verify_password

    def counting(password: str, hashed: bytes) -> bool:
        calls["n"] += 1
        return real(password, hashed)

    monkeypatch.setattr("app.api.deps.verify_password", counting)
    return calls


async def test_single_device_uses_exactly_one_bcrypt(
    client: AsyncClient, session: AsyncSession, bcrypt_counter: dict[str, int]
) -> None:
    headers = await _admin_headers(client, session)
    session.add(_device("phd_single_token"))
    await session.commit()

    resp = await client.get(
        "/api/v1/auth/me",
        headers={**headers, "X-Device-Token": "phd_single_token"},
    )
    assert resp.status_code == 200, resp.text
    assert bcrypt_counter["n"] == 1


async def test_twenty_devices_only_the_prefix_match_is_verified(
    client: AsyncClient, session: AsyncSession, bcrypt_counter: dict[str, int]
) -> None:
    headers = await _admin_headers(client, session)
    target = "phd_target_token_20_devices"
    filler_hash = hash_password("phd_filler_token")
    filler_prefix = device_token_prefix("phd_filler_token")
    session.add_all(
        [
            Device(
                device_name=f"filler-{i}",
                device_token_hash=filler_hash,
                token_prefix=filler_prefix,
                user_id=None,
                created_at=_now(),
                last_seen_at=None,
                revoked=0,
            )
            for i in range(19)
        ]
    )
    session.add(_device(target))
    await session.commit()

    resp = await client.get(
        "/api/v1/auth/me",
        headers={**headers, "X-Device-Token": target},
    )
    assert resp.status_code == 200, resp.text
    # 19 non-matching rows are excluded by the indexed prefix query.
    assert bcrypt_counter["n"] == 1


async def test_revoked_device_rejected_without_bcrypt(
    client: AsyncClient, session: AsyncSession, bcrypt_counter: dict[str, int]
) -> None:
    headers = await _admin_headers(client, session)
    session.add(_device("phd_revoked_token", revoked=1))
    await session.commit()

    resp = await client.get(
        "/api/v1/auth/me",
        headers={**headers, "X-Device-Token": "phd_revoked_token"},
    )
    assert resp.status_code == 401
    assert bcrypt_counter["n"] == 0


async def test_unknown_prefix_rejected_without_bcrypt(
    client: AsyncClient, session: AsyncSession, bcrypt_counter: dict[str, int]
) -> None:
    headers = await _admin_headers(client, session)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={**headers, "X-Device-Token": "phd_never_paired_token"},
    )
    assert resp.status_code == 401
    assert bcrypt_counter["n"] == 0


async def test_legacy_null_prefix_falls_back_to_full_scan(
    client: AsyncClient, session: AsyncSession, bcrypt_counter: dict[str, int]
) -> None:
    headers = await _admin_headers(client, session)
    session.add(_device("phd_legacy_token", legacy=True))
    await session.commit()

    resp = await client.get(
        "/api/v1/auth/me",
        headers={**headers, "X-Device-Token": "phd_legacy_token"},
    )
    assert resp.status_code == 200, resp.text
    assert bcrypt_counter["n"] == 1


async def test_pairing_stores_the_token_prefix(
    client: AsyncClient, session: AsyncSession
) -> None:
    session.add(SystemSetting(key="mobile_access_mode", value=b"shared"))
    await session.commit()
    headers = await _admin_headers(client, session)

    qr = await client.get("/api/v1/devices/qr-payload", headers=headers)
    assert qr.status_code == 200, qr.text
    payload = qr.json()
    secret = await get_qr_secret(session)
    network_key = compute_network_key(
        payload["url"], payload["instance_id"], payload["expires_at"], secret
    )
    resp = await client.post(
        "/api/v1/auth/mobile-register",
        json={
            "device_id": "m7-device-uuid",
            "device_name": "M7 Phone",
            "qr_payload": {
                "url": payload["url"],
                "networkKey": network_key,
                "instanceId": payload["instance_id"],
                "apiVersion": payload["api_version"],
                "expiresAt": payload["expires_at"],
            },
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["device_token"]

    row = (await session.execute(select(Device).order_by(Device.id.desc()))).scalars().first()
    assert row is not None
    assert row.token_prefix == device_token_prefix(token)
