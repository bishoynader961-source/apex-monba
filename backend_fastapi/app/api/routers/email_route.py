"""Email reporting routes — send daily sales reports via SMTP."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.email_service import send_daily_sales_report
from app.shared.config import settings
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/email", tags=["email"])


class DailyReportRequest(BaseModel):
    to_email: str
    report_date: Optional[str] = None


class DailyReportResponse(BaseModel):
    sent: bool
    message: str


@router.post("/daily-sales", response_model=DailyReportResponse)
async def send_daily_report(
    payload: DailyReportRequest,
    _auth: CurrentUser = Depends(require_permission("analytics.read")),
    session: AsyncSession = Depends(get_session),
) -> DailyReportResponse:
    """Send a daily sales report email to the specified address.

    Requires ``smtp_host`` to be configured in the application settings.
    If ``report_date`` is omitted, defaults to yesterday.
    """
    if not settings.smtp_host:
        raise HTTPException(
            status_code=400,
            detail="SMTP is not configured. Set SMTP_HOST in application settings.",
        )

    sent = await send_daily_sales_report(
        session=session,
        to_email=payload.to_email,
        report_date=payload.report_date,
    )

    if sent:
        return DailyReportResponse(sent=True, message="Daily sales report sent successfully.")
    else:
        raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP configuration.")


@router.get("/health")
async def email_health(
    _auth: CurrentUser = Depends(require_permission("analytics.read")),
) -> dict[str, Any]:
    """Check SMTP configuration status."""
    return {
        "smtp_configured": bool(settings.smtp_host),
        "smtp_host": settings.smtp_host or "(not set)",
        "smtp_port": settings.smtp_port,
        "smtp_tls": settings.smtp_use_tls,
        "from_email": settings.smtp_from_email or "(not set)",
    }
