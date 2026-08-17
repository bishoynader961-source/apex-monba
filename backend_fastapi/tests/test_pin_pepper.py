"""C.4 — PIN device-bound peppering: offline exfiltration resistance + tamper-evident lockout.

These tests drive the ``env`` pepper backend directly (via ``set_pin_pepper``)
so they never depend on the lru-cached ``settings`` singleton. The two pepper
values simulate "same machine" (K1) vs "DB exfiltrated to a different machine /
pepper unavailable" (K2).
"""
from __future__ import annotations

import os

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Role, User
from app.core.repositories import UserRepository
from app.shared.security import (
    PinPepper,
    generate_pin_salt,
    get_pin_pepper,
    hash_pin,
    seal_lockout,
    set_pin_pepper,
)
from app.shared.schemas import CurrentUser, Token

_PIN_ENV = "PHARMACY_PEPPER_KEY"


def _pepper(pepper_value: str) -> None:
    os.environ[_PIN_ENV] = pepper_value
    # Fresh instance each time so the env flip actually takes effect.
    set_pin_pepper(PinPepper(backend="env", path="", env_key=_PIN_ENV))


async def _seed_user(session: AsyncSession, username: str, pin: str, pepper_value: str) -> User:
    _pepper(pepper_value)
    repo = UserRepository(session)
    user = await repo.create(
        username=username, display_name=username, password_hash=b"x", role_id=3
    )
    await session.flush()
    # Set the PIN through the security primitives the service uses.
    from app.shared.security import get_pin_pepper, hash_pin

    p = get_pin_pepper().derive()
    user.pin_salt = generate_pin_salt()
    user.pin_hash = hash_pin(pin, user.pin_salt, p)
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    user.lockout_hmac = seal_lockout(0, None, p)
    await session.commit()
    return user


async def test_pin_login_happy_path(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, "cashier1", "1234", "machine-key-AAA")
    resp = await client.post("/api/v1/auth/login/pin", json={"username": "cashier1", "pin": "1234"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_pin_login_wrong_pin_lockout(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, "cashier2", "1234", "machine-key-AAA")
    for _ in range(5):
        resp = await client.post("/api/v1/auth/login/pin", json={"username": "cashier2", "pin": "0000"})
        assert resp.status_code in (401, 403)
    # Reset the network rate-limit window so the 6th request reaches the
    # account-lockout check (5 req/min limit would otherwise return 429).
    from app.shared.rate_limit import limiter

    limiter.reset()
    # 6th attempt -> locked (403) even though we now send the correct PIN.
    resp = await client.post("/api/v1/auth/login/pin", json={"username": "cashier2", "pin": "1234"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_pin_login_unknown_user(client: AsyncClient, session: AsyncSession) -> None:
    resp = await client.post("/api/v1/auth/login/pin", json={"username": "ghost", "pin": "1234"})
    assert resp.status_code == 401


# ── T54: exfiltration resistance ─────────────────────────────────────────────
def _pepper_unavailable() -> None:
    """Simulate a DB exfiltrated off-machine: the pepper cannot be resolved
    (DPAPI blob un-decryptable / env var absent) -> derive() returns None."""
    os.environ.pop(_PIN_ENV, None)
    set_pin_pepper(PinPepper(backend="env", path="", env_key=_PIN_ENV))


async def test_T54_exfiltrated_db_cannot_verify_on_wrong_machine(
    client: AsyncClient, session: AsyncSession
) -> None:
    # User PIN hashed with pepper K1 on the legitimate machine.
    await _seed_user(session, "cashier3", "1234", "machine-key-AAA")

    # Attacker exfiltrates only the DB (salt + pin_hash + lockout_hmac) and
    # attempts verification on a machine where the pepper is UNRECOVERABLE.
    _pepper_unavailable()
    assert get_pin_pepper().derive() is None

    # The CORRECT PIN must NOT verify off-machine (no positive confirmation
    # for an offline brute-force to latch onto).
    resp = await client.post("/api/v1/auth/login/pin", json={"username": "cashier3", "pin": "1234"})
    assert resp.status_code == 401, "correct PIN must NOT verify off-machine"

    # And wrong PINs also fail (no info leak to distinguish them).
    resp2 = await client.post("/api/v1/auth/login/pin", json={"username": "cashier3", "pin": "9999"})
    assert resp2.status_code == 401


# ── T55: tamper-evident lockout counters ────────────────────────────────────
async def test_T55_tampered_lockout_forces_lock(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _seed_user(session, "cashier4", "1234", "machine-key-AAA")
    # An offline attacker bumps failed_attempts in the DB but CANNOT forge the
    # pepper-bound HMAC seal (no pepper) -> the sealed lockout_hmac stays as the
    # legitimate value. verify_lockout() must detect the mismatch and force a lock.
    user.pin_failed_attempts = 7  # leave lockout_hmac untouched (unforgeable)
    await session.commit()

    resp = await client.post("/api/v1/auth/login/pin", json={"username": "cashier4", "pin": "1234"})
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "forbidden"


async def test_T55_sealed_counters_pass_when_untampered(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_user(session, "cashier5", "1234", "machine-key-AAA")
    # No manual tampering -> legit login works.
    resp = await client.post("/api/v1/auth/login/pin", json={"username": "cashier5", "pin": "1234"})
    assert resp.status_code == 200
