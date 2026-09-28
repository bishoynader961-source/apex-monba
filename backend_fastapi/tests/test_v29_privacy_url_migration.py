"""v29 migration: backfill privacy_policy_url without clobbering admin-set values.

SystemSetting.value is LargeBinary (utf-8 bytes), so the migration writes the
URL as a hex BLOB literal; these tests decode and compare as text.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import SCHEMA_VERSION, Base, migrate_schema
from app.core.models import SystemSetting

EXPECTED_URL = (
    "https://github.com/bishoynader961-source/apex-monba/blob/master/PRIVACY_POLICY.md"
)


async def _migrated_engine(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)


async def _read_value(engine: AsyncEngine, key: str) -> bytes | None:
    async with engine.connect() as conn:
        result = await conn.execute(
            SystemSetting.__table__.select().where(SystemSetting.key == key)
        )
        row = result.first()
        return row.value if row else None


async def _write_value(engine: AsyncEngine, key: str, value: bytes | None) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            SystemSetting.__table__.insert().values(key=key, value=value)
        )


async def _set_user_version(engine: AsyncEngine, version: int) -> None:
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f"PRAGMA user_version={version}")


async def test_v29_backfills_missing_key(engine: AsyncEngine) -> None:
    """Fresh/simulated-v28 DB without the key: migration inserts the URL."""
    await _migrated_engine(engine)

    value = await _read_value(engine, "privacy_policy_url")
    assert value is not None
    assert value.decode("utf-8") == EXPECTED_URL

    async with engine.connect() as conn:
        version = (await conn.exec_driver_sql("PRAGMA user_version")).fetchone()[0]
    assert version == SCHEMA_VERSION


async def test_v29_preserves_admin_set_url(engine: AsyncEngine) -> None:
    """A URL the admin set manually is never overwritten."""
    custom = "https://example.com/pharmacy/privacy"
    await _write_value(engine, "privacy_policy_url", custom.encode("utf-8"))
    await _set_user_version(engine, 28)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)

    value = await _read_value(engine, "privacy_policy_url")
    assert value is not None
    assert value.decode("utf-8") == custom


async def test_v29_overwrites_empty_value(engine: AsyncEngine) -> None:
    """An existing empty value (seeded default) is filled in."""
    await _write_value(engine, "privacy_policy_url", b"")
    await _set_user_version(engine, 28)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)

    value = await _read_value(engine, "privacy_policy_url")
    assert value is not None
    assert value.decode("utf-8") == EXPECTED_URL


async def test_v29_overwrites_null_value(engine: AsyncEngine) -> None:
    """An existing NULL value is filled in."""
    await _write_value(engine, "privacy_policy_url", None)
    await _set_user_version(engine, 28)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)

    value = await _read_value(engine, "privacy_policy_url")
    assert value is not None
    assert value.decode("utf-8") == EXPECTED_URL


async def test_v29_migration_idempotent(engine: AsyncEngine) -> None:
    """Re-running migrate_schema is a no-op: version stable, value unchanged."""
    await _migrated_engine(engine)
    first = await _read_value(engine, "privacy_policy_url")

    async with engine.begin() as conn:
        await migrate_schema(conn)
        v = (await conn.exec_driver_sql("PRAGMA user_version")).fetchone()[0]

    assert v == SCHEMA_VERSION
    assert await _read_value(engine, "privacy_policy_url") == first == EXPECTED_URL.encode("utf-8")
