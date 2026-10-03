"""Batch 4 (audit M8): v31 adds devices.token_prefix, v32 adds hot-path indexes.

Fresh databases get these from ``Base.metadata.create_all``; these tests
simulate pre-v31/v30 databases and verify ``migrate_schema`` applies both the
column and the indexes, idempotently, and lands on the current schema version.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import SCHEMA_VERSION, Base, migrate_schema

# Audit M8 index set (name, table, column). NOTE: audit_logs exposes the time
# column as ``timestamp`` in this schema — the audit report's ``created_at``
# does not exist, so the index targets the real column.
_INDEXES = [
    ("ix_receipts_timestamp", "receipts"),
    ("ix_receipts_server_created_at", "receipts"),
    ("ix_sold_items_timestamp", "sold_items"),
    ("ix_dispenses_patient_id", "dispenses"),
    ("ix_dispenses_fill_date", "dispenses"),
    ("ix_inventory_expiration", "inventory_extended"),
    ("ix_audit_logs_timestamp", "audit_logs"),
]


async def _index_exists(engine: AsyncEngine, name: str) -> bool:
    async with engine.connect() as conn:
        row = (
            await conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index' AND name = ?", (name,)
            )
        ).fetchone()
    return row is not None


async def _user_version(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int((await conn.exec_driver_sql("PRAGMA user_version")).fetchone()[0])


async def _device_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = (await conn.exec_driver_sql("PRAGMA table_info(devices)")).fetchall()
    return {str(r[1]) for r in rows}


async def test_v31_adds_device_token_prefix_column_and_index(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Simulate a pre-v31 database: recreate the legacy devices table.
        await conn.exec_driver_sql("DROP TABLE IF EXISTS devices")
        await conn.exec_driver_sql(
            """
            CREATE TABLE devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT NOT NULL DEFAULT '',
                device_token_hash BLOB NOT NULL,
                user_id INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                revoked INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await conn.exec_driver_sql("PRAGMA user_version=30")

    assert "token_prefix" not in await _device_columns(engine)

    async with engine.begin() as conn:
        await migrate_schema(conn)

    assert "token_prefix" in await _device_columns(engine)
    assert await _index_exists(engine, "ix_devices_token_prefix") is True
    assert await _user_version(engine) == SCHEMA_VERSION == 32


async def test_v32_creates_all_hot_path_indexes(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for name, _ in _INDEXES:
            await conn.exec_driver_sql(f"DROP INDEX IF EXISTS {name}")
        await conn.exec_driver_sql("PRAGMA user_version=31")

    for name, _ in _INDEXES:
        assert await _index_exists(engine, name) is False

    async with engine.begin() as conn:
        await migrate_schema(conn)

    for name, _ in _INDEXES:
        assert await _index_exists(engine, name) is True, name
    assert await _user_version(engine) == SCHEMA_VERSION


async def test_v32_migration_is_idempotent(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)
        await migrate_schema(conn)

    for name, _ in _INDEXES:
        assert await _index_exists(engine, name) is True, name
    assert await _user_version(engine) == SCHEMA_VERSION
