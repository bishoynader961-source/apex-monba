"""Coverage tests for app/core/database.py and app/main.py paths (B8).

The main suite runs against an in-memory SQLite database, so the file-backed
read replica, the VACUUM snapshot, the PRAGMA migrate path, and the app
lifespan startup/shutdown are never exercised. These tests close that gap to
keep total backend coverage >= 90%.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.core import database as db
from app.core.database import (
    Base,
    build_engine,
    build_read_engine,
    create_schema,
    get_read_session,
    get_session,
    vacuum_snapshot,
)


def test_write_db_path_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db.settings, "database_url", "sqlite+aiosqlite:///./pharmacy.db")
    assert db._write_db_path() is not None

    monkeypatch.setattr(db.settings, "database_url", "postgresql+asyncpg://u:p@h/db")
    assert db._write_db_path() is None

    monkeypatch.setattr(db.settings, "database_url", "sqlite+aiosqlite:///:memory:")
    assert db._write_db_path() is None


def test_build_engine_variants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mem = build_engine("sqlite+aiosqlite:///:memory:")
    assert mem is not None
    mem.dispose()

    file_url = f"sqlite+aiosqlite:///{tmp_path / 'b8_file.db'}"
    file_eng = build_engine(file_url)
    assert file_eng is not None
    file_eng.dispose()

    # asyncpg is not a test dependency, so stub the driver import for the
    # non-SQLite branch of build_engine.
    class _FakeEngine:
        pass

    monkeypatch.setattr(db, "create_async_engine", lambda u, **kw: _FakeEngine())
    pg = build_engine("postgresql+asyncpg://u:p@h/db")
    assert isinstance(pg, _FakeEngine)


@pytest.mark.asyncio
async def test_read_engine_file_backed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'b8_read.db'}"
    monkeypatch.setattr(db.settings, "database_url", url)

    eng = build_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await eng.dispose()

    ro = build_read_engine()
    assert ro is not None
    async with ro.connect() as c:
        rows = (
            await c.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        ).fetchall()
        assert rows
    await ro.dispose()


@pytest.mark.asyncio
async def test_vacuum_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'b8_vac.db'}"
    monkeypatch.setattr(db.settings, "database_url", url)

    eng = build_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await eng.dispose()

    snapshot_eng = build_engine(url)
    db._engine = snapshot_eng
    try:
        dest = await vacuum_snapshot(str(tmp_path / "snaps"))
        assert dest is not None and Path(dest).exists()
    finally:
        db._engine = None
        await snapshot_eng.dispose()


@pytest.mark.asyncio
async def test_create_schema_file_backed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'b8_schema.db'}"
    monkeypatch.setattr(db.settings, "database_url", url)
    db._engine = None
    db._sessionmaker = None
    db._read_engine = None
    db._read_sessionmaker = None

    db.init_engine(url)
    await create_schema()
    async with db._engine.begin() as conn:
        version = (await conn.exec_driver_sql("PRAGMA user_version")).fetchone()[0]
        assert version == db.SCHEMA_VERSION
    await db._engine.dispose()
    db._engine = None
    db._sessionmaker = None
    db._read_engine = None
    db._read_sessionmaker = None


@pytest.mark.asyncio
async def test_session_factories_trigger_init() -> None:
    db._engine = None
    db._sessionmaker = None
    db._read_engine = None
    db._read_sessionmaker = None

    async for _ in get_session():
        break
    assert db._sessionmaker is not None

    # Force the read-session factory's lazy-init branch.
    db._read_sessionmaker = None
    async for _ in get_read_session():
        break

    await db._engine.dispose()
    db._engine = None
    db._sessionmaker = None
    db._read_engine = None
    db._read_sessionmaker = None


@pytest.mark.asyncio
async def test_app_lifespan_startup_and_shutdown() -> None:
    from app.main import app

    try:
        async with app.router.lifespan_context(app):
            assert db._engine is not None
    finally:
        db._engine = None
        db._sessionmaker = None
        db._read_engine = None
        db._read_sessionmaker = None
