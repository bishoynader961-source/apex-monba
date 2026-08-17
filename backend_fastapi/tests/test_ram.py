"""Tests for TASK 2 (SQLite write-safety pragmas) and TASK 3 (bounded lock cache).

TASK 2 — ``build_engine`` must apply ``busy_timeout=30000``, ``journal_mode=wal``,
and ``synchronous=NORMAL`` on a real file-backed connection (in-memory is skipped).

TASK 3 — ``lock_manager._locks`` must stay bounded under eviction pressure and must
never evict a currently-held lock.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest.mark.asyncio
async def test_sqlite_pragmas_applied_on_file_backed_engine(tmp_path) -> None:
    from app.core.database import build_engine

    db_file = tmp_path / "pragma_check.db"
    engine = build_engine(f"sqlite+aiosqlite:///{db_file}")
    try:
        async with engine.connect() as conn:
            busy = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
            journal = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
            synchronous = (await conn.execute(text("PRAGMA synchronous"))).scalar()
    finally:
        await engine.dispose()

    assert busy == 30000, f"busy_timeout expected 30000, got {busy}"
    assert journal == "wal", f"journal_mode expected 'wal', got {journal}"
    # PRAGMA synchronous: 0=OFF, 1=NORMAL, 2=FULL
    assert synchronous == 1, f"synchronous expected NORMAL(1), got {synchronous}"


@pytest.mark.asyncio
async def test_lock_cache_is_bounded() -> None:
    from app.core import lock_manager

    lock_manager.reset_locks()
    maxsize = lock_manager._LOCK_MAXSIZE

    # Hold a lock so it must survive eviction pressure.
    held = await lock_manager.get_lock("HELD")
    await held.acquire()
    try:
        # Far more distinct names than the cap -> forces LRU eviction.
        for i in range(maxsize + 2000):
            await lock_manager.get_lock(f"drug-{i}")

        assert len(lock_manager._locks) <= maxsize
        # The held lock must not have been evicted.
        assert "HELD" in lock_manager._locks
        assert lock_manager._locks["HELD"] is held
    finally:
        held.release()

    lock_manager.reset_locks()
    assert len(lock_manager._locks) == 0


@pytest.mark.asyncio
async def test_lock_cache_lru_recency() -> None:
    from app.core import lock_manager

    lock_manager.reset_locks()
    maxsize = lock_manager._LOCK_MAXSIZE

    # Re-touch the oldest entry (drug-0) so it stays recent under eviction.
    await lock_manager.get_lock("drug-0")
    for i in range(1, maxsize + 500):
        await lock_manager.get_lock(f"drug-{i}")
    # drug-0 was last touched before the burst; it should have been evicted.
    assert "drug-0" not in lock_manager._locks
    # The most-recently touched entries survive.
    assert f"drug-{maxsize + 499}" in lock_manager._locks
    lock_manager.reset_locks()
