"""Audit routes: tamper-evidence verification and export (B5/B2)."""
import csv
import io
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import AuditRepository
from app.shared.schemas import AuditVerifyResult, CurrentUser

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/verify", response_model=AuditVerifyResult, status_code=status.HTTP_200_OK)
async def verify_audit(
    user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> AuditVerifyResult:
    """Recompute the audit hash chain and report any tampering."""
    valid, broken_at = await AuditRepository(session).verify_chain()
    return AuditVerifyResult(valid=valid, broken_at=broken_at)


@router.get("/export", status_code=status.HTTP_200_OK)
async def export_audit(
    fmt: Optional[str] = Query(default="json", pattern="^(json|csv)$"),
    limit: int = Query(default=1000, ge=1, le=100000),
    user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export the tamper-evident audit log (json or csv).

    Guarded by ``inventory.read`` to match the verify endpoint (B2)."""
    entries = await AuditRepository(session).export_logs(limit=limit)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["id", "ts", "action", "user_pin", "category", "subject_type", "subject_id", "role", "details", "prev_hash", "entry_hash"]
        )
        for e in entries:
            writer.writerow(
                [e.id, e.timestamp, e.action, e.user_pin, e.category, e.subject_type, e.subject_id, e.role, e.details, e.prev_hash, e.entry_hash]
            )
        return Response(content=buf.getvalue(), media_type="text/csv")
    payload = [
        {
            "id": e.id,
            "ts": e.timestamp,
            "action": e.action,
            "user_pin": e.user_pin,
            "category": e.category,
            "subject_type": e.subject_type,
            "subject_id": e.subject_id,
            "role": e.role,
            "details": e.details,
            "prev_hash": e.prev_hash,
            "entry_hash": e.entry_hash,
        }
        for e in entries
    ]
    return Response(content=_json_dump(payload), media_type="application/json")


def _json_dump(payload: list[dict[str, Any]]) -> str:
    import json

    return json.dumps(payload, separators=(",", ":"), default=str)
