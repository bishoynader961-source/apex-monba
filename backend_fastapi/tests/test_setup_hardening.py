"""Audit Batch 2 / M1 — unauthenticated setup-takeover hardening.

POST /api/v1/setup/complete creates the first admin with no credentials, so
it is the one pre-auth takeover surface. Covered here:
  - weak admin passwords are rejected 400 ``weak_password`` (complexity)
  - the endpoint is rate-limited (5/minute → 429)
  - a strong password still completes first-run setup successfully
  - once a user exists, the endpoint returns 403 (no re-takeover)
"""
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import User

_SETUP_URL = "/api/v1/setup/complete"
_STRONG = "Sup3r$ecretKey!"


def _payload(password: str) -> dict:
    return {
        "admin_name": "Owner",
        "username": "admin",
        "password": password,
        "confirm_password": password,
        "pharmacy_name": "Test Pharmacy",
    }


async def test_setup_complete_rejects_weak_password(client: AsyncClient) -> None:
    """12-char password without upper/symbol fails complexity (400 weak_password)."""
    resp = await client.post(_SETUP_URL, json=_payload("password123"))
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "weak_password"


async def test_setup_complete_rejects_sub12_password(client: AsyncClient) -> None:
    """8–11 char password with all character classes passes the schema's
    min_length=8 but fails the ≥12 complexity rule (400 weak_password)."""
    resp = await client.post(_SETUP_URL, json=_payload("Ab1!abcd"))
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "weak_password"


async def test_setup_complete_strong_password_creates_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A strong password completes first-run setup and seeds the role-1 admin."""
    resp = await client.post(_SETUP_URL, json=_payload(_STRONG))
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True

    user = (
        await session.execute(select(User).where(User.username == "admin"))
    ).scalar_one()
    assert user.role_id == 1


async def test_setup_complete_second_call_is_403(client: AsyncClient) -> None:
    """After the admin exists, setup cannot be re-run (takeover closed)."""
    first = await client.post(_SETUP_URL, json=_payload(_STRONG))
    assert first.status_code == 200, first.text

    second = await client.post(_SETUP_URL, json=_payload(_STRONG))
    assert second.status_code == 403, second.text


async def test_setup_complete_is_rate_limited(client: AsyncClient) -> None:
    """6th request within the window returns 429 (uniform error contract)."""
    payload = _payload("password123")  # weak → 400, still counts toward the limit

    for i in range(5):
        resp = await client.post(_SETUP_URL, json=payload)
        assert resp.status_code == 400, f"request {i + 1} should be processed, not rate-limited"

    blocked = await client.post(_SETUP_URL, json=payload)
    assert blocked.status_code == 429, "6th request should be rate-limited"
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["message"] == "Too many requests"
