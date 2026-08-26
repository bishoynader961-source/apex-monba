"""Admin routes: server-managed compressed backup (T7/admin, backup.create)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.backup import vacuum_backup
from app.core.database import get_session
from app.shared.schemas import BackupResult, CurrentUser

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/backup", response_model=BackupResult, status_code=status.HTTP_201_CREATED)
async def create_backup(
    user: CurrentUser = Depends(require_permission("backup.create")),
    session: AsyncSession = Depends(get_session),
) -> BackupResult:
    """Trigger a compressed point-in-time backup of ``pharmacy.db`` (T7).

    Restricted to the single server/master host: in the thin-client topology only the
    master machine runs FastAPI and owns the DB, so there is exactly one writer to back
    up. (#6 deployment topology.)
    """
    import os

    path = await vacuum_backup(compress=True)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup unavailable for the configured database",
        )
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return BackupResult(path=path, compressed=path.endswith(".gz"), size_bytes=size)
