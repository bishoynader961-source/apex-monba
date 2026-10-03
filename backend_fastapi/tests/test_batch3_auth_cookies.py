"""Batch 3 (audit M3): the desktop refresh token lives in an HttpOnly cookie.

The frontend keeps only the access token, in memory. These tests pin the
server half of that contract: login/refresh set an HttpOnly, SameSite=Strict,
path-scoped refresh cookie; a cookie alone (no body token, no localStorage)
refreshes the session; logout clears the cookie server-side.
"""
from __future__ import annotations

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.auth_route import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from app.core.models import Role
from app.core.repositories import UserRepository
from app.shared.security import hash_password


async def _login(
    client: AsyncClient, session: AsyncSession, username: str = "cookieuser"
) -> Response:
    role = Role(name=f"{username}-role", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    await UserRepository(session).create(
        username, "Cookie User", hash_password("password123"), role.id
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return resp


def _refresh_set_cookie(resp: Response) -> str:
    """The Set-Cookie header for the refresh cookie (may appear more than once)."""
    for header in resp.headers.get_list("set-cookie"):
        if header.startswith(f"{REFRESH_COOKIE_NAME}="):
            return header
    raise AssertionError(
        f"no {REFRESH_COOKIE_NAME} Set-Cookie header in {resp.headers.get_list('set-cookie')}"
    )


async def test_login_sets_httponly_samesite_strict_cookie(
    client: AsyncClient, session: AsyncSession
) -> None:
    resp = await _login(client, session)
    assert resp.json()["refresh_token"]
    header = _refresh_set_cookie(resp)
    lowered = header.lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert f"path={REFRESH_COOKIE_PATH}" in lowered


async def test_refresh_with_cookie_only_after_restart(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Simulated app restart: no body token (browser JS cannot read the
    HttpOnly cookie), so the cookie alone must mint a new access token."""
    tokens = (await _login(client, session)).json()

    # A fresh client with ONLY the cookie (what a restarted app looks like).
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE_NAME, tokens["refresh_token"], path=REFRESH_COOKIE_PATH)
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    # The rotated refresh token is handed back via the cookie, not the body.
    assert _refresh_set_cookie(resp)


async def test_refresh_without_cookie_or_body_is_401(client: AsyncClient) -> None:
    client.cookies.clear()
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


async def test_logout_clears_cookie(client: AsyncClient, session: AsyncSession) -> None:
    tokens = (await _login(client, session)).json()
    resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    header = _refresh_set_cookie(resp)
    assert f'{REFRESH_COOKIE_NAME}=""' in header
    lowered = header.lower()
    assert "max-age=0" in lowered or "expires=thu, 01 jan 1970" in lowered
    assert f"path={REFRESH_COOKIE_PATH}" in lowered
