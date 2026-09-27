"""Admin routes: server-managed compressed backup (T7/admin, backup.create) +
AES-256-GCM encrypted backup (Sprint 2A) + demo mode (Task 4 Step 4.7)."""
from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.backup import vacuum_backup
from app.core.backup_crypto import (
    DecryptError,
    decode_key,
    decrypt_to_gzip_bytes,
    encode_key,
    generate_key,
    gunzip_to_db_bytes,
    write_encrypted_backup,
)
from app.core.database import get_session
from app.core.models import SystemSetting
from app.core.seed_demo_data import clear_demo_data, is_demo_mode, reset_demo_data, seed_demo_data, set_demo_mode
from app.shared.schemas import BackupResult, CurrentUser, EncryptedBackupResult

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
    await _touch_last_backup_at(session)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return BackupResult(path=path, compressed=path.endswith(".gz"), size_bytes=size)


# ── Encrypted backup (Sprint 2A) ────────────────────────────────────────────


async def _touch_last_backup_at(session: AsyncSession) -> None:
    """Sprint 4D: stamp the backup reminder clock (idempotent upsert)."""
    from datetime import datetime, timezone

    setting = await session.get(SystemSetting, "last_backup_at")
    stamp = datetime.now(timezone.utc).isoformat()
    if setting is None:
        session.add(SystemSetting(key="last_backup_at", value=stamp.encode("utf-8")))
    else:
        setting.value = stamp.encode("utf-8")
    await session.commit()


@router.post("/backup/encrypted", response_model=EncryptedBackupResult, status_code=status.HTTP_201_CREATED)
async def create_encrypted_backup(
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_permission("backup.create")),
) -> EncryptedBackupResult:
    """Create an AES-256-GCM encrypted snapshot (``.backup.enc``).

    A fresh random key is generated per backup and returned exactly once in
    this response — it is never stored on disk or in the database. Lose the
    key, lose the backup.
    """
    gz_path = await vacuum_backup(compress=True)
    if gz_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup unavailable for the configured database",
        )
    key = generate_key()
    enc_path = await write_encrypted_backup(os.path.dirname(gz_path) or "snapshots", Path(gz_path), key)
    size = enc_path.stat().st_size
    await _touch_last_backup_at(session)
    return EncryptedBackupResult(
        path=str(enc_path),
        filename=enc_path.name,
        size_bytes=size,
        recovery_key=encode_key(key),
    )


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


@router.post("/restore/encrypted", status_code=status.HTTP_200_OK)
async def restore_encrypted_backup(
    file: UploadFile = File(...),
    key: str = Form(...),
    _auth: CurrentUser = Depends(require_permission("backup.create")),
) -> dict[str, str]:
    """Restore an AES-256-GCM encrypted backup (``.backup.enc``) + admin key.

    Wrong key / tampered / non-encrypted file → 400. On success the decrypted
    ``.db`` flows through the same replace-then-restart path as plain restore.
    """
    from app.core.database import _write_db_path

    if not file.filename or not file.filename.endswith(".backup.enc"):
        raise HTTPException(status_code=400, detail="Upload a .backup.enc file")
    db_path = _write_db_path()
    if db_path is None:
        raise HTTPException(status_code=400, detail="Cannot restore: not using a file-based database")

    try:
        decryption_key = decode_key(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    blob = await file.read()
    try:
        gz_data = decrypt_to_gzip_bytes(blob, decryption_key)
        plaintext = gunzip_to_db_bytes(gz_data)
    except DecryptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    tmp_path = db_path + ".restore_tmp"
    try:
        with open(tmp_path, "wb") as f:
            f.write(plaintext)
        shutil.copy2(tmp_path, db_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {"message": "Encrypted backup restored successfully. Please restart the application."}


# ── Demo mode (Task 4 Step 4.7) — settings.manage gate, DB session per call ──


@router.get("/demo/status")
async def demo_status(
    session: AsyncSession = Depends(get_session),
    _auth: CurrentUser = Depends(require_permission("settings.manage")),
) -> dict[str, bool]:
    """Whether demo mode is currently enabled (SystemSetting demo_mode)."""
    return {"enabled": await is_demo_mode(session)}


@router.post("/demo/seed", status_code=status.HTTP_201_CREATED)
async def demo_seed(
    session: AsyncSession = Depends(get_session),
    _auth: CurrentUser = Depends(require_permission("settings.manage")),
) -> dict[str, Any]:
    """Seed sample data (idempotent) and enable demo mode."""
    counts = await seed_demo_data(session)
    await set_demo_mode(session, True)
    return {"enabled": True, "counts": counts}


@router.post("/demo/reset")
async def demo_reset(
    session: AsyncSession = Depends(get_session),
    _auth: CurrentUser = Depends(require_permission("settings.manage")),
) -> dict[str, Any]:
    """Clear all demo-marked rows, then re-seed; leaves demo mode ON."""
    return await reset_demo_data(session)


@router.post("/demo/clear")
async def demo_clear(
    session: AsyncSession = Depends(get_session),
    _auth: CurrentUser = Depends(require_permission("settings.manage")),
) -> dict[str, Any]:
    """Clear all demo-marked rows and disable demo mode (back to real data)."""
    counts = await clear_demo_data(session)
    await set_demo_mode(session, False)
    return {"enabled": False, "counts": counts}
