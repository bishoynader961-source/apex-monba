"""Tests for the JWT-based route protection system.

Covers all authentication paths in ``GET /api/v1/auth/me``:
  - valid token → 200 with user profile
  - missing token → 401
  - tampered token → 401
  - expired token → 401
  - refresh token → 401
  - deleted/inactive user → 401
  - OAuth2PasswordBearer configuration
"""
from __future__ import annotations

from httpx import AsyncClient

from app.api.deps import oauth2_scheme
from app.core.repositories import UserRepository
from app.shared.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)

_TEST_ROLE_ID = 3
_TEST_PERMISSIONS = ["pos.checkout", "inventory.read"]


async def _seed_user(session, username: str = "testuser") -> int:
    repo = UserRepository(session)
    user = await repo.create(
        username=username,
        display_name=username,
        password_hash=hash_password("password123"),
        role_id=_TEST_ROLE_ID,
    )
    return user.id


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Test 1 — valid token
# --------------------------------------------------------------------------- #
async def test_me_returns_user_with_valid_token(client: AsyncClient, session) -> None:
    user_id = await _seed_user(session, "alice")

    token = create_access_token(
        subject=str(user_id),
        role="pharmacist",
        permissions=_TEST_PERMISSIONS,
        username="alice",
    )

    resp = await client.get("/api/v1/auth/me", headers=_auth_header(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert body["role"] == "pharmacist"
    assert "pos.checkout" in body["permissions"]


# --------------------------------------------------------------------------- #
# Test 2 — missing token
# --------------------------------------------------------------------------- #
async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


# --------------------------------------------------------------------------- #
# Test 3 — tampered token (signature invalid)
# --------------------------------------------------------------------------- #
async def test_me_with_tampered_token_returns_401(client: AsyncClient, session) -> None:
    user_id = await _seed_user(session, "bob")

    valid_token = create_access_token(
        subject=str(user_id),
        role="pharmacist",
        permissions=_TEST_PERMISSIONS,
        username="bob",
    )
    tampered_token = valid_token[:-5] + "AAAA" + valid_token[-1:]

    resp = await client.get(
        "/api/v1/auth/me", headers=_auth_header(tampered_token)
    )

    assert resp.status_code == 401
    assert "Invalid or expired token" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Test 4 — expired token
# --------------------------------------------------------------------------- #
async def test_me_with_expired_token_returns_401(client: AsyncClient, session) -> None:
    user_id = await _seed_user(session, "carol")

    expired_token = create_access_token(
        subject=str(user_id),
        role="pharmacist",
        permissions=_TEST_PERMISSIONS,
        username="carol",
        expires_minutes=-1,
    )

    resp = await client.get("/api/v1/auth/me", headers=_auth_header(expired_token))

    assert resp.status_code == 401
    assert "Invalid or expired token" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Test 5 — refresh token instead of access token
# --------------------------------------------------------------------------- #
async def test_me_with_refresh_token_returns_401(client: AsyncClient, session) -> None:
    user_id = await _seed_user(session, "dave")

    refresh_token = create_refresh_token(str(user_id))

    resp = await client.get("/api/v1/auth/me", headers=_auth_header(refresh_token))

    assert resp.status_code == 401
    assert "Invalid token type" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Test 6 — user deleted / deactivated
# --------------------------------------------------------------------------- #
async def test_me_with_valid_token_for_inactive_user_returns_401(
    client: AsyncClient, session
) -> None:
    user_id = await _seed_user(session, "erin")

    token = create_access_token(
        subject=str(user_id),
        role="pharmacist",
        permissions=_TEST_PERMISSIONS,
        username="erin",
    )

    # Deactivate the user in the database.
    user = await UserRepository(session).get(user_id)
    assert user is not None
    user.is_active = 0
    await session.commit()

    resp = await client.get("/api/v1/auth/me", headers=_auth_header(token))

    assert resp.status_code == 401
    assert "User not found or inactive" in resp.json()["detail"]


async def test_me_with_valid_token_for_deleted_user_returns_401(
    client: AsyncClient, session
) -> None:
    user_id = await _seed_user(session, "frank")

    token = create_access_token(
        subject=str(user_id),
        role="pharmacist",
        permissions=_TEST_PERMISSIONS,
        username="frank",
    )

    # Delete the user from the database.
    user = await UserRepository(session).get(user_id)
    assert user is not None
    await session.delete(user)
    await session.commit()

    resp = await client.get("/api/v1/auth/me", headers=_auth_header(token))

    assert resp.status_code == 401
    assert "User not found or inactive" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Test 7 — OAuth2PasswordBearer configuration
# --------------------------------------------------------------------------- #
async def test_oauth2_scheme_token_url_configured() -> None:
    assert oauth2_scheme.model.flows.password.tokenUrl == "api/v1/auth/login"
