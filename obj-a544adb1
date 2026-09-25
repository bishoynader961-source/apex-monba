"""Admin routes: server-managed compressed backup (T7/admin, backup.create)."""
from __future__ import annotations

import glob
import os
import shutil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
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
    """Trigger a compressed point-in-time backup of ``pharmacy.db`` (T7)."""
    path = await vacuum_backup(compress=True)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup unavailable for the configured database",
        )
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return BackupResult(path=path, compressed=path.endswith(".gz"), size_bytes=size)


@router.get("/backups")
async def list_backups(
    _auth: CurrentUser = Depends(require_permission("backup.create")),
) -> list[dict[str, Any]]:
    """List recent backup files from the backups directory."""
    from app.core.database import _write_db_path

    db_path = _write_db_path()
    if db_path is None:
        return []

    backups_dir = os.path.join(os.path.dirname(db_path), "backups")
    if not os.path.isdir(backups_dir):
        return []

    files = sorted(glob.glob(os.path.join(backups_dir, "*.gz")) + glob.glob(os.path.join(backups_dir, "*.db")),
                   key=os.path.getmtime, reverse=True)[:20]

    return [
        {
            "path": f,
            "filename": os.path.basename(f),
            "size_bytes": os.path.getsize(f) if os.path.exists(f) else 0,
            "modified": os.path.getmtime(f) if os.path.exists(f) else 0,
        }
        for f in files
    ]


@router.post("/restore", status_code=status.HTTP_200_OK)
async def restore_backup(
    file: UploadFile = File(...),
    _auth: CurrentUser = Depends(require_permission("backup.create")),
) -> dict[str, str]:
    """Restore pharmacy.db from an uploaded backup file (.db or .gz)."""
    from app.core.database import _write_db_path

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    db_path = _write_db_path()
    if db_path is None:
        raise HTTPException(status_code=400, detail="Cannot restore: not using a file-based database")

    contents = await file.read()

    if file.filename.endswith(".gz"):
        import gzip
        try:
            contents = gzip.decompress(contents)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid .gz backup file")
    elif not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="Upload a .db or .gz backup file")

    tmp_path = db_path + ".restore_tmp"
    try:
        with open(tmp_path, "wb") as f:
            f.write(contents)
        shutil.copy2(tmp_path, db_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {"message": "Backup restored successfully. Please restart the application."}
