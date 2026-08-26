"""Compressed local backups via VACUUM INTO + gzip with retention (decision 5).

Wraps the existing ``vacuum_snapshot`` semantics with: a ``wal_checkpoint`` before the
copy (so the snapshot is consistent), ``TRUNCATE`` after (so the live ``-wal`` cannot
grow unbounded during a long read), gzip compression, and a 7-file retention sweep.

Concern #12 (WinError 32): Windows Defender / search indexers briefly lock the freshly
written snapshot file, so gzip + delete are wrapped in a retry+backoff loop.
"""
from __future__ import annotations

import asyncio
import gzip
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: F401  # used as a type hint

from app.core.database import _engine, _write_db_path, init_engine
from app.shared.logging_config import get_logger

logger = get_logger("backup")

_KEEP = 7
_GZIP_ATTEMPTS = 3
_BACKOFF_SECONDS = 0.5


def _engine_or_init() -> AsyncEngine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


async def _run_wal_checkpoint(mode: str) -> None:
    eng = _engine_or_init()
    async with eng.begin() as conn:
        await conn.exec_driver_sql(f"PRAGMA wal_checkpoint({mode})")


async def vacuum_backup(dest_dir: str = "snapshots", *, compress: bool = True) -> Optional[str]:
    """Produce a consistent, optionally-compressed point-in-time backup.

    Returns the written path (``.db`` or ``.db.gz``), or ``None`` if no on-disk
    database is configured.
    """
    path = _write_db_path()
    if path is None:
        return None
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_file = dest / f"pharmacy-{stamp}.db"

    eng = _engine_or_init()
    # PASSIVE: flush as much WAL as possible without blocking readers during the copy.
    await _run_wal_checkpoint("PASSIVE")
    async with eng.begin() as conn:
        await conn.exec_driver_sql(f"VACUUM INTO '{dest_file}'")
    # TRUNCATE: reclaim the live -wal so it can't grow during the post-copy gzip.
    await _run_wal_checkpoint("TRUNCATE")

    final: Path = dest_file
    if compress:
        gz = await safe_gzip(dest_file)
        if gz is not None:
            final = gz
    await prune_retained(str(dest), keep=_KEEP)
    logger.info("backup_written", path=str(final))
    return str(final)


async def safe_gzip(source: Path) -> Optional[Path]:
    """Gzip ``source`` -> ``source + .gz`` with retry+backoff (Concern #12/#13)."""
    dest = source.with_suffix(source.suffix + ".gz")
    for attempt in range(1, _GZIP_ATTEMPTS + 1):
        try:
            with open(source, "rb") as fin, gzip.open(dest, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            await safe_delete(source)
            return dest
        except PermissionError as exc:  # WinError 32 — indexer/defender holds the file.
            logger.warning("gzip_retry", attempt=attempt, error=str(exc))
            if attempt == _GZIP_ATTEMPTS:
                return None
            await asyncio.sleep(_BACKOFF_SECONDS)
    return None


async def safe_delete(path: Path) -> bool:
    """Delete ``path`` with retry+backoff (Concern #12/#13)."""
    for attempt in range(1, _GZIP_ATTEMPTS + 1):
        try:
            os.remove(path)
            return True
        except PermissionError as exc:
            logger.warning("delete_retry", attempt=attempt, path=str(path), error=str(exc))
            if attempt == _GZIP_ATTEMPTS:
                logger.error("delete_failed", path=str(path))
                return False
            await asyncio.sleep(_BACKOFF_SECONDS)
    return False


async def prune_retained(dest_dir: str, *, keep: int = _KEEP) -> int:
    """Keep the newest ``keep`` snapshots (db + gz), delete the rest. Returns deleted count."""
    files = sorted(
        (p for p in Path(dest_dir).iterdir() if p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    deleted = 0
    for stale in files[keep:]:
        if await safe_delete(stale):
            deleted += 1
    if deleted:
        logger.info("snapshots_pruned", removed=deleted)
    return deleted
