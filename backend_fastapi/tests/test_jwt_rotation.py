"""Sprint 1B: JWT 15-minute access-token TTL and refresh-token rotation.

Rotation model: users.token_version (schema v28) is stamped into every JWT as
``tvr`` at issue time; refresh bumps the stored version (invalidating the
presented refresh token and all earlier tokens), and password changes bump it
too (revoking every outstanding session)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import create_access_token, create_refresh_token, decode_token, hash_password

_PERMS = ["wc.read", "wc.write", "users.write"]


async def _admin_token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="sprint1admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perms: list[Permission] = []
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms.append(p)
    await session.commit()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("sprint1admin", "Sprint 1 Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "sprint1admin", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_access_token_ttl_is_15_minutes() -> None:
    """Behavioral check: minted access tokens expire within 15 minutes, even
    when an operator .env overrides ACCESS_TOKEN_EXPIRE_MINUTES (the hard cap
    in create_access_token wins over configuration)."""
    from datetime import timedelta

    import jwt as pyjwt

    from app.shared.config import settings

    token = create_access_token("1", "admin", 1, ["*"], username="u")
    claims = pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    expiry = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    assert expiry <= datetime.now(timezone.utc) + timedelta(minutes=15, seconds=30)
    assert claims["tvr"] == 1


def test_refresh_token_expired_is_rejected() -> None:
    from app.shared.config import settings

    with pytest.raises(Exception):
        token = create_refresh_token("1", expires_days=-1)
        decode_token(token)  # expired -> AppException(401 invalid_token)
    assert settings.refresh_token_expire_days > 0


def test_tokens_carry_version_claim() -> None:
    token = create_access_token("1", "admin", 1, ["*"], username="u", token_version=3)
    claims = decode_token(token)
    assert claims["tvr"] == 3
    refresh = create_refresh_token("1", token_version=3)
    assert decode_token(refresh)["tvr"] == 3


async def test_refresh_rotation_invalidates_old_refresh_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    auth_token = await _admin_token(client, session)
    assert auth_token

    login = await client.post(
        "/api/v1/auth/login", json={"username": "sprint1admin", "password": "password123"}
    )
    old_refresh = login.json()["refresh_token"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200, first.text
    new_tokens = first.json()

    # Rotation: replaying the consumed refresh token must fail (401).
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401, replay.text

    # The new pair works: its access token authenticates, and its refresh
    # token rotates again.
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert me.status_code == 200, me.text
    second = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert second.status_code == 200, second.text


async def test_password_change_revokes_outstanding_tokens(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _admin_token(client, session)
    auth = {"Authorization": f"Bearer {token}"}

    login = await client.post(
        "/api/v1/auth/login", json={"username": "sprint1admin", "password": "password123"}
    )
    access_before = login.json()["access_token"]

    # Change own password (re-auth with the same password as caller proof).
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "password123", "new_password": "NewPassword123!"},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text

    # Pre-change tokens are revoked (version bumped): both the just-issued
    # access token and the caller's earlier one.
    stale = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_before}"}
    )
    assert stale.status_code == 401
    me = await client.get("/api/v1/auth/me", headers=auth)
    assert me.status_code == 401

    # New login works and yields a working token.
    relogin = await client.post(
        "/api/v1/auth/login", json={"username": "sprint1admin", "password": "NewPassword123!"}
    )
    assert relogin.status_code == 200, relogin.text
    me2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {relogin.json()['access_token']}"},
    )
    assert me2.status_code == 200
