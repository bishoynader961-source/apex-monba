"""Crash report route: receives client-side error telemetry.

POST /api/v1/crash-report — stores structured error reports from the frontend.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_session
from app.shared.schemas import CurrentUser

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/crash-report", tags=["crash-report"])


class CrashReport(BaseModel):
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    component_stack: Optional[str] = None
    url: Optional[str] = None
    user_agent: Optional[str] = None
    user_id: Optional[str] = None
    app_version: Optional[str] = None
    timestamp: Optional[str] = None


@router.post("")
async def submit_crash_report(
    report: CrashReport,
    _auth: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Store a client-side crash report in the audit log."""
    now = datetime.now(timezone.utc).isoformat()

    details = (
        f"CRASH REPORT: {report.error_type}: {report.error_message}\n"
        f"URL: {report.url or 'N/A'}\n"
        f"Component: {report.component_stack or 'N/A'}\n"
        f"Version: {report.app_version or 'N/A'}\n"
        f"UA: {report.user_agent or 'N/A'}"
    )

    try:
        await session.execute(
            text("""
                INSERT INTO audit_logs (action, details, created_at)
                VALUES (:action, :details, :ts)
            """),
            {"action": "crash_report", "details": details[:2000], "ts": now},
        )
        await session.commit()
    except Exception as e:
        log.warning("Failed to store crash report: %s", e)

    log.warning(
        "crash_report received type=%s msg=%s url=%s",
        report.error_type,
        report.error_message[:200],
        report.url,
    )

    return {"status": "ok", "timestamp": now}
