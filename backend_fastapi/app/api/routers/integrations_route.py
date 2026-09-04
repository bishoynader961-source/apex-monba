"""Drug Evaluation Proxy route — Phase 7.

POST /api/v1/drugs/evaluate
    Accepts { ndc, drug_name } and returns a standardized safety evaluation.
    When a live provider key is configured in the ``integrations`` table the
    request is forwarded via httpx and the response cached for 1 hour.
    Otherwise the built-in mock is used so UI development can proceed
    without external dependencies.

POST /api/v1/integrations           — create / update integration credentials
GET  /api/v1/integrations           — list configured integrations
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.shared.schemas import (
    CurrentUser,
    DrugEvaluateRequest,
    DrugEvaluateResponse,
    IntegrationCreate,
    IntegrationRead,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["integrations"])

# ─── Simple in-process cache (TTL = 1 hour) ──────────────────────────────────
_RESPONSE_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
_CACHE_TTL = timedelta(hours=1)


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    entry = _RESPONSE_CACHE.get(key)
    if entry and datetime.now(timezone.utc) - entry[0] < _CACHE_TTL:
        return entry[1]
    _RESPONSE_CACHE.pop(key, None)
    return None


def _cache_set(key: str, value: dict[str, Any]) -> None:
    _RESPONSE_CACHE[key] = (datetime.now(timezone.utc), value)


# ─── Mock Provider (used when no live key is configured) ─────────────────────

_MOCK_INTERACTIONS: dict[str, dict[str, Any]] = {
    "warfarin": {
        "status": "warning",
        "message": "Warfarin may interact with many common medications. Monitor INR closely.",
        "interactions": [
            "NSAIDs increase bleeding risk",
            "Amiodarone potentiates anticoagulant effect",
        ],
    },
    "aspirin": {
        "status": "warning",
        "message": "Aspirin increases bleeding risk when combined with anticoagulants.",
        "interactions": ["Concurrent warfarin use requires dose adjustment"],
    },
    "metformin": {
        "status": "safe",
        "message": "Metformin is generally well tolerated. Monitor renal function.",
        "interactions": [],
    },
}

_SEVERE_KEYWORDS = {"digoxin", "lithium", "phenytoin", "carbamazepine", "theophylline"}


def _mock_evaluate(drug_name: str) -> dict[str, Any]:
    name_lower = drug_name.lower()
    if name_lower in _MOCK_INTERACTIONS:
        return _MOCK_INTERACTIONS[name_lower]
    if name_lower in _SEVERE_KEYWORDS:
        return {
            "status": "severe",
            "message": f"{drug_name} has a narrow therapeutic index. Severe interaction risk detected.",
            "interactions": [
                "Requires therapeutic drug monitoring",
                "Dose adjustment mandatory with concurrent medications",
            ],
        }
    return {
        "status": "safe",
        "message": f"No known severe interactions identified for {drug_name}.",
        "interactions": [],
    }


# ─── Drug Evaluate Endpoint ───────────────────────────────────────────────────

@router.post("/drugs/evaluate", response_model=DrugEvaluateResponse)
async def evaluate_drug(
    payload: DrugEvaluateRequest,
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> DrugEvaluateResponse:
    """Evaluate a drug for interactions/safety.

    Checks the ``integrations`` table for an active provider. If found,
    proxies the request via httpx and caches the response. Otherwise uses
    the built-in mock response table.
    """
    cache_key = hashlib.sha256(
        f"{payload.ndc or ''}:{payload.drug_name.lower()}".encode()
    ).hexdigest()

    cached = _cache_get(cache_key)
    if cached:
        return DrugEvaluateResponse(**cached, cached=True)

    # Check for active live integration
    row = await session.execute(
        text("""
            SELECT id, base_url, encrypted_api_key
            FROM integrations WHERE is_active = 1
            AND provider_name = 'drug_evaluate'
            LIMIT 1
        """)
    )
    integration = row.mappings().first()

    if integration and integration["encrypted_api_key"]:
        # ── Live proxy path ──
        try:
            # Decrypt the API key (stored as raw bytes for now; swap for Fernet in production)
            raw_key = integration["encrypted_api_key"].decode("utf-8", errors="replace")
            base_url = integration["base_url"] or "https://api.druginteractionapi.example.com"

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{base_url}/evaluate",
                    json={"ndc": payload.ndc, "drug_name": payload.drug_name},
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
                resp.raise_for_status()
                live_data = resp.json()

            result = {
                "status": live_data.get("status", "safe"),
                "message": live_data.get("message", ""),
                "interactions": live_data.get("interactions", []),
                "source": "live",
            }
        except Exception as exc:
            log.warning("Live drug evaluate failed, falling back to mock: %s", exc)
            result = {**_mock_evaluate(payload.drug_name), "source": "mock_fallback"}
    else:
        # ── Mock path ──
        result = {**_mock_evaluate(payload.drug_name), "source": "mock"}

    _cache_set(cache_key, result)
    return DrugEvaluateResponse(**result, cached=False)


# ─── Integration CRUD ─────────────────────────────────────────────────────────

@router.get("/integrations", response_model=list[IntegrationRead])
async def list_integrations(
    _auth: CurrentUser = Depends(require_permission("settings.read")),
    session: AsyncSession = Depends(get_session),
) -> list[IntegrationRead]:
    rows = await session.execute(
        text("SELECT id, provider_name, is_active, base_url, created_at FROM integrations ORDER BY provider_name")
    )
    return [IntegrationRead(**dict(r._mapping)) for r in rows]


@router.post("/integrations", response_model=IntegrationRead, status_code=201)
async def upsert_integration(
    payload: IntegrationCreate,
    _auth: CurrentUser = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_session),
) -> IntegrationRead:
    """Create or update (by provider_name) an integration with its API key."""
    now = datetime.now(timezone.utc).isoformat()
    # Check for existing
    existing = (await session.execute(
        text("SELECT id FROM integrations WHERE provider_name = :name"),
        {"name": payload.provider_name},
    )).mappings().first()

    integration_id = existing["id"] if existing else str(uuid.uuid4())

    # Store api_key as UTF-8 bytes (swap for Fernet encryption in production)
    encrypted_key = payload.api_key.encode("utf-8")

    if existing:
        await session.execute(
            text("""
                UPDATE integrations
                SET encrypted_api_key = :key, base_url = :url,
                    is_active = 1, updated_at = :now
                WHERE id = :id
            """),
            {"key": encrypted_key, "url": payload.base_url, "now": now, "id": integration_id},
        )
    else:
        await session.execute(
            text("""
                INSERT INTO integrations
                    (id, provider_name, encrypted_api_key, is_active, base_url, created_at, updated_at)
                VALUES
                    (:id, :name, :key, 1, :url, :now, :now)
            """),
            {
                "id": integration_id,
                "name": payload.provider_name,
                "key": encrypted_key,
                "url": payload.base_url,
                "now": now,
            },
        )
    await session.commit()

    row = await session.execute(
        text("SELECT id, provider_name, is_active, base_url, created_at FROM integrations WHERE id = :id"),
        {"id": integration_id},
    )
    mapped = row.mappings().first()
    if mapped is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return IntegrationRead(**dict(mapped))
