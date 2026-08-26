"""Tests for offline Swagger UI / ReDoc documentation.

Verifies that /docs and /redoc serve HTML referencing locally-vendored
static assets (no external CDNs), that those assets are served by
StaticFiles, and that the CSP is relaxed only for docs-related paths
while API routes retain the strict default-src 'none' policy.
"""
from __future__ import annotations

from httpx import AsyncClient


async def test_docs_serves_local_swagger_ui(client: AsyncClient) -> None:
    resp = await client.get("/docs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "/static/swagger-ui/swagger-ui-bundle.js" in body
    assert "/static/swagger-ui/swagger-ui.css" in body
    assert "/static/swagger-ui/favicon-32x32.png" in body
    assert "cdn.jsdelivr.net" not in body


async def test_docs_csp_is_relaxed(client: AsyncClient) -> None:
    resp = await client.get("/docs")
    csp = resp.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "default-src 'none'" not in csp


async def test_redoc_serves_local_assets(client: AsyncClient) -> None:
    resp = await client.get("/redoc")
    assert resp.status_code == 200
    body = resp.text
    assert "/static/redoc/redoc.standalone.js" in body
    assert "cdn.jsdelivr.net" not in body


async def test_static_swagger_js_served(client: AsyncClient) -> None:
    resp = await client.get("/static/swagger-ui/swagger-ui-bundle.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert "SwaggerUIBundle" in resp.text[:50000]


async def test_static_redoc_js_served(client: AsyncClient) -> None:
    resp = await client.get("/static/redoc/redoc.standalone.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


async def test_static_swagger_css_served(client: AsyncClient) -> None:
    resp = await client.get("/static/swagger-ui/swagger-ui.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]


async def test_openapi_json_has_relaxed_csp(client: AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert "script-src 'self'" in csp
    assert "default-src 'none'" not in csp


async def test_api_routes_keep_strict_csp(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "script-src 'self'" not in csp
