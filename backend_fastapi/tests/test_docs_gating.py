"""Audit Batch 2 / M2 — API documentation gating behind DEBUG.

/docs, /redoc, and /openapi.json must be unreachable when
``settings.debug`` is false, and reachable when it is true. The /docs and
/redoc handlers and the OpenAPI middleware gate read the settings object at
request time, so tests flip it via monkeypatch without restarting the app.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.shared.config import settings

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


@pytest.mark.parametrize("path", _DOC_PATHS)
async def test_docs_404_when_debug_false(client: AsyncClient, monkeypatch, path: str) -> None:
    monkeypatch.setattr(settings, "debug", False)
    resp = await client.get(path)
    assert resp.status_code == 404, resp.text


@pytest.mark.parametrize("path", _DOC_PATHS)
async def test_docs_200_when_debug_true(client: AsyncClient, monkeypatch, path: str) -> None:
    monkeypatch.setattr(settings, "debug", True)
    resp = await client.get(path)
    assert resp.status_code == 200, resp.text
