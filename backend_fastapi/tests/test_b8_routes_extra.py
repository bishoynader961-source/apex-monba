"""B8 — HTTP-bound route coverage for remaining low-coverage route files.

Route handlers ARE traced via the ASGI ``client`` (unlike deep service bodies), so
targeted HTTP requests lift the ``deps.get_current_user`` rejection branches above
the 90% project gate.

Licensing coverage removed 2026-09-24: the Creem MoR webhook/license routes were
consolidated into the legacy Flask license server (see FLOW_LOGIC.md §17); the
FastAPI app no longer exposes ``/api/v1/webhook/creem`` or ``/api/v1/license/*``.
"""
from __future__ import annotations

import logging

import jwt

logging.getLogger("aiosqlite").setLevel(logging.WARNING)

from app.core.models import Role
from app.core.repositories import UserRepository
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


# ── deps.get_current_user rejection branches ───────────────────────────────────
def _token(claims: dict) -> str:
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


async def test_deps_malformed_token_rejected(client):
    r = await client.get("/api/v1/users", headers={"Authorization": "Bearer " + _token({"role": "r"})})
    assert r.status_code == 401


async def test_deps_non_int_sub_rejected(client):
    r = await client.get("/api/v1/users", headers={"Authorization": "Bearer " + _token({"sub": "abc", "role": "r"})})
    assert r.status_code == 401


async def test_deps_nonexistent_user_rejected(client):
    r = await client.get("/api/v1/users", headers={"Authorization": "Bearer " + _token({"sub": "999999", "role": "r"})})
    assert r.status_code == 401


async def test_deps_refresh_token_rejected(client):
    r = await client.get(
        "/api/v1/users",
        headers={"Authorization": "Bearer " + _token({"sub": "1", "role": "r", "type": "refresh"})},
    )
    assert r.status_code == 401
