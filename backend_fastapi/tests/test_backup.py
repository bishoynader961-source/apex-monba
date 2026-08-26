"""M7 — backup module (T7): compressed VACUUM INTO + gzip + retention + admin route."""
from __future__ import annotations

import gzip
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.core.backup import (
    _engine_or_init,
    prune_retained,
    safe_delete,
    safe_gzip,
    vacuum_backup,
)
from app.shared.security import hash_password

_PERMS = ["backup.create"]


async def _token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        await session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("bkuser", "Bk", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "bkuser", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session)}"}


async def test_vacuum_backup_in_memory_returns_none() -> None:
    """In-memory DBs have no file path → backup is a no-op returning None."""
    from app.shared import config as config_mod
    with patch.object(config_mod.settings, "database_url", "sqlite+aiosqlite:///:memory:"):
        result = await vacuum_backup()
    assert result is None


async def test_vacuum_backup_no_db_path_returns_none() -> None:
    """When no on-disk DB is configured, vacuum_backup returns None."""
    from app.shared import config as config_mod
    with patch.object(config_mod.settings, "database_url", "sqlite+aiosqlite:///:memory:"):
        result = await vacuum_backup()
    assert result is None


async def test_safe_gzip_creates_gz_and_deletes_source() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"test backup content")
        src = Path(f.name)
    try:
        gz = await safe_gzip(src)
        assert gz is not None
        assert gz.exists()
        assert not src.exists()
        with gzip.open(gz, "rb") as decompressed:
            assert decompressed.read() == b"test backup content"
    finally:
        if src.exists():
            src.unlink()
        if gz and gz.exists():
            gz.unlink()


async def test_safe_delete_succeeds() -> None:
    with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as f:
        f.write(b"temp")
        p = Path(f.name)
    assert p.exists()
    result = await safe_delete(p)
    assert result is True
    assert not p.exists()


async def test_prune_retained_keeps_newest() -> None:
    d = tempfile.mkdtemp()
    try:
        for i in range(10):
            Path(d, f"file-{i:03d}.db").touch()
        deleted = await prune_retained(d, keep=5)
        assert deleted == 5
        remaining = sorted(p.name for p in Path(d).iterdir())
        assert len(remaining) == 5
        assert remaining[-1] == "file-009.db"
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def test_prune_retained_empty_dir() -> None:
    d = tempfile.mkdtemp()
    try:
        deleted = await prune_retained(d, keep=7)
        assert deleted == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def test_engine_or_init_returns_engine() -> None:
    from app.core import backup as backup_mod
    mock_engine = MagicMock()
    with patch.object(backup_mod, "_engine", mock_engine):
        eng = _engine_or_init()
        assert eng is mock_engine


async def test_run_wal_checkpoint() -> None:
    from app.core.backup import _run_wal_checkpoint
    from app.core import backup as backup_mod
    mock_conn = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_cm
    with patch.object(backup_mod, "_engine", mock_engine):
        await _run_wal_checkpoint("TRUNCATE")
    mock_conn.exec_driver_sql.assert_called_once_with("PRAGMA wal_checkpoint(TRUNCATE)")


async def test_safe_gzip_retry_then_succeeds() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"retry content")
        src = Path(f.name)
    gz = None
    try:
        original_open = open
        attempts = {"n": 0}

        def flaky_open(path, mode="r", *args, **kwargs):
            if path is src and "rb" in mode:
                attempts["n"] += 1
                if attempts["n"] == 1:
                    raise PermissionError("file in use")
            return original_open(path, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=flaky_open):
            gz = await safe_gzip(src)
        assert gz is not None
        assert gz.exists()
        assert not src.exists()
    finally:
        if src.exists():
            src.unlink()
        if gz and gz.exists():
            gz.unlink()


async def test_safe_delete_retry_then_succeeds() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"temp")
        p = Path(f.name)
    try:
        original_remove = os.remove
        attempts = {"n": 0}

        def flaky_remove(path):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise PermissionError("file in use")
            original_remove(path)

        with patch("os.remove", side_effect=flaky_remove):
            ok = await safe_delete(p)
        assert ok is True
        assert not p.exists()
    finally:
        if p.exists():
            p.unlink()


async def test_safe_gzip_all_attempts_fail() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"fail content")
        src = Path(f.name)
    gz = None
    try:
        with patch("builtins.open", side_effect=PermissionError("file in use")):
            gz = await safe_gzip(src)
        assert gz is None
    finally:
        if src.exists():
            src.unlink()
        if gz and gz.exists():
            gz.unlink()


async def test_safe_delete_all_attempts_fail() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"fail")
        p = Path(f.name)
    try:
        with patch("os.remove", side_effect=PermissionError("file in use")):
            ok = await safe_delete(p)
        assert ok is False
        assert p.exists()
    finally:
        if p.exists():
            p.unlink()


# ── HTTP route tests ──

async def test_admin_backup_unavailable_for_memory_db(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    """In-memory DB → backup returns 503 (no file to back up)."""
    from app.shared import config as config_mod
    with patch.object(config_mod.settings, "database_url", "sqlite+aiosqlite:///:memory:"):
        resp = await client.post("/api/v1/admin/backup", headers=auth)
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


async def test_admin_backup_requires_permission(
    client: AsyncClient, session: AsyncSession
) -> None:
    """No auth token → 401."""
    resp = await client.post("/api/v1/admin/backup")
    assert resp.status_code == 401
