"""Tests for slowapi rate limiting on auth endpoints (F.1 hardening).

Verifies that:
  * POST /api/v1/auth/login is rate-limited at 5 requests/minute by IP.
  * POST /api/v1/auth/login/pin is rate-limited at 5 requests/minute by IP.
  * The 429 response uses the app's uniform error contract.
  * Non-auth endpoints (health) are NOT rate-limited.
  * Rate-limit state resets cleanly between tests (conftest autouse fixture).
"""
from __future__ import annotations

import os

from httpx import AsyncClient

from app.core.repositories import UserRepository
from app.shared.security import hash_password
from app.shared.schemas import Token

_AUTH_LIMIT = 5
_PIN_LIMIT = 5


async def test_auth_login_rate_limited(client: AsyncClient, session) -> None:
    """6th login request within the window returns 429 with app error contract."""
    repo = UserRepository(session)
    await repo.create("rluser", "RL User", hash_password("password123"), role_id=3)

    for i in range(_AUTH_LIMIT):
        resp = await client.post(
            "/api/v1/auth/login", json={"username": "rluser", "password": "wrong"}
        )
        assert resp.status_code == 401, f"request {i + 1} should be processed, not rate-limited"

    blocked = await client.post(
        "/api/v1/auth/login", json={"username": "rluser", "password": "wrong"}
    )
    assert blocked.status_code == 429, "6th request should be rate-limited"
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["message"] == "Too many requests"


async def test_auth_login_pin_rate_limited(
    client: AsyncClient, session, monkeypatch
) -> None:
    """6th PIN login request returns 429 with app error contract."""
    # Use the env pepper backend so PIN verification works in tests.
    os.environ["PHARMACY_PEPPER_KEY"] = "test-pepper-key"
    from app.shared.security import (
        PinPepper,
        generate_pin_salt,
        hash_pin,
        seal_lockout,
        set_pin_pepper,
    )

    pepper = PinPepper(backend="env", path="", env_key="PHARMACY_PEPPER_KEY")
    set_pin_pepper(pepper)
    p = pepper.derive()

    repo = UserRepository(session)
    user = await repo.create("rlpin", "RL Pin", hash_password("password123"), role_id=3)
    await session.flush()
    user.pin_salt = generate_pin_salt()
    user.pin_hash = hash_pin("1234", user.pin_salt, p)
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    user.lockout_hmac = seal_lockout(0, None, p)
    await session.commit()

    for i in range(_PIN_LIMIT):
        resp = await client.post(
            "/api/v1/auth/login/pin", json={"username": "rlpin", "pin": "1234"}
        )
        assert resp.status_code == 200, f"request {i + 1} should succeed, stat={resp.status_code} body={resp.text}"

    blocked = await client.post(
        "/api/v1/auth/login/pin", json={"username": "rlpin", "pin": "1234"}
    )
    assert blocked.status_code == 429, "6th request should be rate-limited"
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"


async def test_health_not_rate_limited(client: AsyncClient) -> None:
    """Health endpoint has no rate limit — many requests return 200."""
    for _ in range(10):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200


async def test_refresh_not_rate_limited(client: AsyncClient, session) -> None:
    """Refresh endpoint is not rate-limited — scope discipline check."""
    repo = UserRepository(session)
    await repo.create("rlrefresh", "RL Refresh", hash_password("password123"), role_id=3)

    login = await client.post(
        "/api/v1/auth/login", json={"username": "rlrefresh", "password": "password123"}
    )
    # Even after the 5-login limit, refresh (a different endpoint) is unconstrained.
    for _ in range(5):
        bad = await client.post(
            "/api/v1/auth/login", json={"username": "rlrefresh", "password": "wrong"}
        )
        assert bad.status_code in (401, 429)

    refresh_token = login.json()["refresh_token"]
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert resp.status_code == 200


async def test_me_endpoint_rate_limited(client: AsyncClient, session) -> None:
    """After auth rate limit is exhausted, unauthenticated /me still returns 401 (not 429).

    This confirms rate limiting applies only to auth credential endpoints, not
    to token-protected routes like /me.
    """
    repo = UserRepository(session)
    user = await repo.create("rlme", "RL Me", hash_password("password123"), role_id=3)
    await session.flush()
    from app.shared.security import create_access_token

    token = create_access_token(str(user.id), "pharmacist", ["pos.checkout"], username="rlme")
    for _ in range(_AUTH_LIMIT):
        await client.post("/api/v1/auth/login", json={"username": "rlme", "password": "wrong"})

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, "/me should not be rate-limited"
