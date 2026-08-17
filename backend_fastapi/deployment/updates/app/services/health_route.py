"""Staged health_route.py (v1) — OTA delta payload example.

Part of deployment/updates/; referenced by deployment/ota_manifest.json for the C.2
granular OTA applier. Not imported at runtime — it is a staged payload.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}
