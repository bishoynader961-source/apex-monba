"""Async SQLAlchemy 2.0 engine, session dependency, and schema bootstrap.

The engine connects to the single preserved ``pharmacy.db``. WAL mode and a busy
timeout are applied on every connection so concurrent POS writes serialize safely
(see risk R1 in the plan). An in-memory SQLite URL uses ``StaticPool`` so the
connection pool shares one database across sessions (required for tests).
"""
from __future__ import annotations

import os
import urllib.parse
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.shared.config import settings


class Base(DeclarativeBase):
    pass


_BCRYPT_PREFIX = b"$2"

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None
_read_engine: Optional[AsyncEngine] = None
_read_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _write_db_path() -> Optional[str]:
    """Best-effort extraction of the on-disk DB path from the configured URL.

    Returns ``None`` for in-memory databases (no file to open read-only).
    """
    url = settings.database_url
    # Only SQLite uses an on-disk file path; PostgreSQL/others use a DSN.
    if not url.startswith("sqlite") or ":memory:" in url:
        return None
    # sqlite+aiosqlite:///./pharmacy.db  ->  ./pharmacy.db
    path = url.split("///", 1)[-1]
    return str(Path(path).resolve())

def _configure_pragmas(dbapi_conn: Any, _record: Any) -> None:
    """Enable WAL + busy_timeout + synchronous=NORMAL on file-backed connections (skip in-memory)."""
    try:  # pragma: no cover - exercised only against real SQLite connections
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA busy_timeout=30000")
        dsn = str(getattr(dbapi_conn, "name", ""))
        if ":memory:" not in dsn:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
    except Exception:  # pragma: no cover - defensive: never break a connection
        pass


def build_engine(url: str) -> AsyncEngine:
    is_sqlite = url.startswith("sqlite")
    if url == "sqlite+aiosqlite:///:memory:":
        engine: AsyncEngine = create_async_engine(
            url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    elif is_sqlite:
        engine = create_async_engine(url, connect_args={"check_same_thread": False})
    else:
        # PostgreSQL / other server databases (B6). The driver is selected by the
        # URL scheme, e.g. ``postgresql+asyncpg://user:pass@host:5432/db``.
        engine = create_async_engine(url)
    if is_sqlite:
        from sqlalchemy import event

        event.listen(engine.sync_engine, "connect", _configure_pragmas)
    return engine


def build_read_engine() -> Optional[AsyncEngine]:
    """Build a read-only replica engine for reporting/analytics reads (Concern 8).

    Opens the same on-disk database with ``mode=ro`` + ``query_only`` so heavy
    reads can never contend with (or accidentally mutate) the checkout write
    path. Returns ``None`` for in-memory databases — callers fall back to the
    write sessionmaker in that case.
    """
    path = _write_db_path()
    if path is None:
        return None
    ro_url = f"sqlite+aiosqlite:///file:{urllib.parse.quote(path)}?mode=ro&uri=true"
    engine = create_async_engine(
        ro_url,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
    )

    def _ro_pragmas(dbapi_conn: Any, _record: Any) -> None:
        try:  # pragma: no cover - defensive
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA query_only=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
        except Exception:  # pragma: no cover - defensive
            pass

    from sqlalchemy import event

    event.listen(engine.sync_engine, "connect", _ro_pragmas)
    return engine


def init_engine(url: Optional[str] = None) -> None:
    global _engine, _sessionmaker, _read_engine, _read_sessionmaker
    _engine = build_engine(url or settings.database_url)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    _read_engine = build_read_engine()
    # In-memory / unsupported RO: reuse the write sessionmaker for reads too.
    _read_sessionmaker = (
        async_sessionmaker(_read_engine, expire_on_commit=False)
        if _read_engine is not None
        else _sessionmaker
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        init_engine()
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        yield session


async def get_read_session() -> AsyncIterator[AsyncSession]:
    """Read-only session for reporting/analytics (Concern 8 / §13).

    Uses the ``mode=ro`` replica so heavy SELECTs never touch the checkout write
    path. Falls back to the write sessionmaker for in-memory databases.
    """
    if _read_sessionmaker is None:
        init_engine()
    assert _read_sessionmaker is not None
    async with _read_sessionmaker() as session:
        yield session


async def vacuum_snapshot(dest_dir: str = "snapshots") -> Optional[str]:
    """Cold ``VACUUM INTO`` snapshot of the live database (§13 resilience).

    Produces an atomic point-in-time copy without blocking writers (WAL). The
    destination file is timestamped; callers are responsible for retention.
    Returns the written path, or ``None`` if a snapshot is not possible (e.g.
    in-memory database).
    """
    path = _write_db_path()
    if path is None or _engine is None:
        return None
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = str(Path(dest_dir) / f"pharmacy-{stamp}.db")
    async with _engine.begin() as conn:
        await conn.exec_driver_sql(f"VACUUM INTO '{dest}'")
    return dest


async def create_schema() -> None:
    if _engine is None:
        init_engine()
    assert _engine is not None
    dialect = _engine.dialect.name
    async with _engine.begin() as conn:
        # Materialise every table/column declared on the ORM models. For a fresh
        # database this alone produces the current schema (v{SCHEMA_VERSION}).
        await conn.run_sync(Base.metadata.create_all)
        if dialect == "sqlite":
            # SQLite has no ALTER-heavy migration framework here, so the PRAGMA
            # user_version routine back-fills columns on pre-existing production
            # databases and stamps the schema version.
            await migrate_schema(conn)
        # PostgreSQL (and other server RDBMS) are created at the latest schema by
        # create_all above; no PRAGMA-based migration is required for a fresh DB.


async def _table_has_column(conn: Any, table: str, column: str) -> bool:
    """True if ``column`` already exists on ``table`` (idempotent migration guard)."""
    res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in res)


async def _table_exists(conn: Any, name: str) -> bool:
    """True if ``name`` already exists as a table (idempotent migration guard)."""
    cur = await conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:n",
        {"n": name},
    )
    return cur.fetchone() is not None


async def migrate_schema(conn: Any) -> None:
    """Versioned, idempotent, restart-safe migrations (PRAGMA user_version).

    ``Base.metadata.create_all`` (run just before this in ``create_schema``)
    already materialises every column/table declared on the ORM models for *fresh*
    databases, so the ALTERs below only run against *pre-existing* production
    databases. Versioning via ``PRAGMA user_version`` makes the routine safe to
    re-run after a crash mid-migration.
    """
    cur = await conn.exec_driver_sql("PRAGMA user_version")
    row = cur.fetchone()
    version = int(row[0]) if row else 0

    # ── v1: base M9/M10 hardening columns ──────────────────────────────────
    if version < 1:
        if not await _table_has_column(conn, "products", "is_deleted"):
            await conn.exec_driver_sql(
                "ALTER TABLE products ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"
            )
        if not await _table_has_column(conn, "users", "pin_salt"):
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN pin_salt BLOB NOT NULL DEFAULT ''")
        if not await _table_has_column(conn, "users", "pin_failed_attempts"):
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN pin_failed_attempts INTEGER NOT NULL DEFAULT 0")
        if not await _table_has_column(conn, "users", "pin_locked_until"):
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN pin_locked_until TEXT")
        if not await _table_has_column(conn, "users", "lockout_hmac"):
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN lockout_hmac BLOB")
        version = 1

    # ── v2: multi-terminal merge-sync hub (C.1) ────────────────────────────
    if version < 2:
        if not await _table_exists(conn, "sync_outbox"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE sync_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    local_seq INTEGER NOT NULL,
                    client_txn_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    merged_seq INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    merged_at TEXT,
                    UNIQUE(device_id, local_seq),
                    UNIQUE(client_txn_id)
                )
                """
            )
        if not await _table_exists(conn, "discrepancies"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE discrepancies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reason TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    local_seq INTEGER NOT NULL,
                    client_txn_id TEXT NOT NULL,
                    details TEXT,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
        if not await _table_exists(conn, "sync_inventory"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE sync_inventory (
                    product_name TEXT PRIMARY KEY,
                    on_hand INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        version = 2

    # ── v3: cashier attribution, server time, drawer movements, recall flag ──
    if version < 3:
        for col, ddl in (
            ("receipts", "server_created_at TEXT"),
            ("receipts", "ts_skew_confidence REAL"),
            ("receipts", "created_by TEXT"),
            ("receipts", "cashier_attribution TEXT"),
            ("inventory_extended", "recalled INTEGER NOT NULL DEFAULT 0"),
        ):
            if not await _table_has_column(conn, col, ddl.split()[0]):
                await conn.exec_driver_sql(f"ALTER TABLE {col} ADD COLUMN {ddl}")
        if not await _table_exists(conn, "drawer_movements"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE drawer_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cashier TEXT NOT NULL,
                    amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL,
                    prior_balance NUMERIC(10,2) NOT NULL DEFAULT 0,
                    new_balance NUMERIC(10,2) NOT NULL DEFAULT 0,
                    server_created_at TEXT NOT NULL,
                    ts_skew_confidence REAL,
                    created_by TEXT,
                    client_created_at TEXT
                )
                """
            )
        # Backfill legacy money columns to 2-decimal NUMERIC affinity where present.
        for table, col in (
            ("products", "price"),
            ("products", "wholesale_price"),
            ("receipts", "total_amount"),
            ("receipt_items", "price_at_time"),
            ("sold_items", "price"),
            ("inventory_extended", "awp"),
            ("inventory_extended", "mac"),
            ("receiving_log", "total_cost"),
        ):
            if await _table_has_column(conn, table, col):
                await conn.exec_driver_sql(
                    f"UPDATE {table} SET {col} = ROUND({col}, 2) WHERE {col} IS NOT NULL"
                )
        version = 3

    # ── v4: cash-drawer shift lifecycle (A1) ────────────────────────────────
    if version < 4:
        if not await _table_exists(conn, "shifts"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE shifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opening_float NUMERIC(10,2) NOT NULL DEFAULT 0,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    opened_by TEXT
                )
                """
            )
        version = 4

    # ── v5: B5 — refund ledger + tamper-evident audit hash chain ──────────
    if version < 5:
        if not await _table_exists(conn, "refunds"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE refunds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_id INTEGER NOT NULL UNIQUE,
                    total_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                    reason TEXT,
                    cashier TEXT,
                    server_created_at TEXT
                )
                """
            )
        for col in ("prev_hash", "entry_hash"):
            if not await _table_has_column(conn, "audit_logs", col):
                await conn.exec_driver_sql(
                    f"ALTER TABLE audit_logs ADD COLUMN {col} TEXT"
                )
        version = 5

    # ── v6: B2 — PIN pepper version column (lazy re-hash after pepper rotation) ──
    if version < 6:
        if not await _table_has_column(conn, "users", "pin_pepper_version"):
            await conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN pin_pepper_version INTEGER NOT NULL DEFAULT 1"
            )
        version = 6

    await conn.exec_driver_sql(f"PRAGMA user_version={SCHEMA_VERSION}")


SCHEMA_VERSION = 6

