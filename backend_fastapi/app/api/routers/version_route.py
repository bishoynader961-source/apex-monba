"""Version check route: returns current version and checks for updates.

GET /api/v1/version — returns current app version and update status.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_permission
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/version", tags=["version"])

APP_VERSION = os.getenv("PHARMACY_APP_VERSION", "1.0.0")
UPDATE_CHECK_URL = os.getenv("UPDATE_CHECK_URL", "")


class VersionInfo(BaseModel):
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    download_url: str | None = None
    release_notes: str | None = None


@router.get("")
async def check_version(
    _auth: CurrentUser = Depends(require_permission("version.read")),
) -> dict[str, Any]:
    """Return current version and check for updates if configured."""
    result: dict[str, Any] = {
        "current_version": APP_VERSION,
        "update_available": False,
        "latest_version": None,
        "download_url": None,
        "release_notes": None,
    }

    if not UPDATE_CHECK_URL:
        return result

    try:
        import urllib.request
        import json

        req = urllib.request.Request(
            UPDATE_CHECK_URL,
            headers={"User-Agent": f"PharmacySuite/{APP_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            latest = data.get("latest_version", "")
            if latest and latest != APP_VERSION:
                result["update_available"] = True
                result["latest_version"] = latest
                result["download_url"] = data.get("download_url")
                result["release_notes"] = data.get("release_notes")
    except Exception:
        pass

    return result
