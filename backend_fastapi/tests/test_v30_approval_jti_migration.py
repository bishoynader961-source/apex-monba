"""v30 migration: the ``approval_jti`` table exists on pre-existing databases.

Fresh databases get the table from ``Base.metadata.create_all``; this test
simulates a v29 database (table dropped, ``PRAGMA user_version=29``) and
verifies ``migrate_schema`` recreates it and lands on the current version.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import SCHEMA_VERSION, Base, migrate_schema


async def _table_exists(engine: AsyncEngine, name: str) -> bool:
    async with engine.connect() as conn:
        row = (
            await conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,)
            )
        ).fetchone()
    return row is not None


async def _user_version(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int((await conn.exec_driver_sql("PRAGMA user_version")).fetchone()[0])


async def test_v30_creates_approval_jti_table(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql("DROP TABLE IF EXISTS approval_jti")
        await conn.exec_driver_sql("PRAGMA user_version=29")

    assert await _table_exists(engine, "approval_jti") is False

    async with engine.begin() as conn:
        await migrate_schema(conn)

    assert await _table_exists(engine, "approval_jti") is True
    assert await _user_version(engine) == SCHEMA_VERSION == 30


async def test_v30_migration_idempotent(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)
        await migrate_schema(conn)

    assert await _table_exists(engine, "approval_jti") is True
    assert await _user_version(engine) == SCHEMA_VERSION
