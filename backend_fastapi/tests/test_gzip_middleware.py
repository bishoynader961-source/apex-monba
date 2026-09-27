"""Sprint 2C: GZip middleware installed and plain requests unaffected."""
from __future__ import annotations

from httpx import AsyncClient


async def test_gzip_middleware_installed_and_plain_requests_work(client: AsyncClient) -> None:
    from fastapi.middleware.gzip import GZipMiddleware

    from app.main import app as fastapi_app

    # Sprint 2C: the middleware is actually on the stack.
    assert any(m.cls is GZipMiddleware for m in fastapi_app.user_middleware)
    # And plain (unauthenticated) requests still flow through the stack.
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.headers.get("content-type", "").startswith("application/json")
