"""Health check + authenticated diagnostics endpoints.

GET /api/v1/health                 — unauthenticated liveness probe (no data).
GET /api/v1/health/diagnostics     — authenticated support diagnostics:
                                     aggregate counters ONLY. Never exposes
                                     patient records, prescriptions, or
                                     credentials (Spec 08 privacy constraint).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import database
from app.core.database import get_session
from app.core.models import Product, User
from app.shared.schemas import CurrentUser, HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/health/diagnostics")
async def health_diagnostics(
    _current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Aggregate diagnostics for the Support tab report.

    Privacy contract (Spec 08): returns counters only. No patient rows,
    no prescription data, no medication names, no credentials. The counts
    themselves (user_count, medicine_count) are non-identifying aggregates.
    """
    user_count = await db.scalar(select(func.count()).select_from(User))
    medicine_count = await db.scalar(select(func.count()).select_from(Product))

    db_size_mb = 0.0
    try:
        engine = database._engine
        if engine is not None:
            db_path = str(engine.url).replace("sqlite+aiosqlite:///", "")
            if db_path and os.path.exists(db_path):
                db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
    except Exception:  # noqa: BLE001 — diagnostics must never 500
        db_size_mb = 0.0

    return {
        "status": "ok",
        "version": os.getenv("PHARMACY_APP_VERSION", "1.0.0"),
        "env": os.getenv("APP_ENV", "production"),
        "user_count": user_count,
        "medicine_count": medicine_count,
        "db_size_mb": db_size_mb,
    }
