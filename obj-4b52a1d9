"""Async SQLAlchemy 2.0 engine, session dependency, and schema bootstrap.

The engine connects to the single preserved ``pharmacy.db`` in the OS app data
directory. WAL mode and a busy timeout are applied on every connection so
concurrent POS writes serialize safely (see risk R1 in the plan). An in-memory
SQLite URL uses ``StaticPool`` so the connection pool shares one database across
sessions (required for tests).
"""
from __future__ import annotations

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


def _get_database_path() -> str:
    """Get the database path in the per-install OS app data directory.

    Delegates to ``app.shared.config.get_app_data_dir`` (``%APPDATA%``
    ``\\PharmacySuite\\pharmacy.db`` on Windows) so every resolution path —
    ``settings.database_url`` default, frozen sidecar, and dev server — agrees
    on one location. A fresh install therefore starts with zero users and the
    first-run setup wizard appears.
    """
    from app.shared.config import get_app_data_dir

    return str(get_app_data_dir() / "pharmacy.db")


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


def _get_default_database_url() -> str:
    """Get the default database URL using platformdirs."""
    db_path = _get_database_path()
    return f"sqlite+aiosqlite:///{db_path}"

def _configure_pragmas(dbapi_conn: Any, _record: Any) -> None:
    """Per-connection SQLite pragmas (runs once per pooled connection — Concern 10).

    ``PRAGMA foreign_keys=ON`` is set here (not only in ``migrate_schema``) because
    SQLite resets FK enforcement to OFF on every fresh connection; a one-off set at
    startup would leave later pool checkouts silently ignoring FK constraints,
    orphaning ``patient_id`` / ``insurance_plan_id``. ``BEGIN IMMEDIATE`` is applied
    on file-backed write connections (T1.5) to convert the deferred-read-then-upgrade
    deadlock into an up-front RESERVE lock that ``busy_timeout`` queues cleanly.
    In-memory connections (single StaticPool in tests) are left at the default.
    """
    try:  # pragma: no cover - exercised only against real SQLite connections
        # FK enforcement is connection-scoped and must be set outside any active
        # transaction; ``connect`` fires on a fresh connection so this is safe.
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA busy_timeout=30000")
        dsn = str(getattr(dbapi_conn, "name", ""))
        if ":memory:" not in dsn:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            # Force BEGIN IMMEDIATE on file-backed write connections (T1.5) so
            # concurrent writers queue via busy_timeout rather than deadlocking on
            # a read->write lock upgrade.
            dbapi_conn.isolation_level = "IMMEDIATE"
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
    _engine = build_engine(url or _get_default_database_url())
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

    # ── v7: clinical/patient management layer (patients, insurance, members, sig, price, dispenses) ──
    if version < 7:
        # receipts is a pre-existing legacy table; backfill the idempotency key (#11).
        if not await _table_has_column(conn, "receipts", "client_tx_id"):
            await conn.exec_driver_sql("ALTER TABLE receipts ADD COLUMN client_tx_id TEXT")
        # insurance_plans must exist before patients reference it.
        if not await _table_exists(conn, "insurance_plans"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE insurance_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_name TEXT NOT NULL,
                    carrier_id TEXT NOT NULL DEFAULT '',
                    bin TEXT NOT NULL DEFAULT '',
                    pcn TEXT NOT NULL DEFAULT '',
                    group_number TEXT NOT NULL DEFAULT '',
                    copay_tier TEXT NOT NULL DEFAULT '',
                    copay_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT
                )
                """
            )
        if not await _table_exists(conn, "patients"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    dob TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT '',
                    driver_license TEXT NOT NULL DEFAULT '',
                    sex TEXT NOT NULL DEFAULT '',
                    employer_id TEXT NOT NULL DEFAULT '',
                    contact_phone TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    insurance_provider TEXT NOT NULL DEFAULT '',
                    policy_number TEXT NOT NULL DEFAULT '',
                    group_number TEXT NOT NULL DEFAULT '',
                    insurance_plan_id INTEGER REFERENCES insurance_plans(id),
                    patient_allergies TEXT NOT NULL DEFAULT '',
                    comments TEXT NOT NULL DEFAULT '',
                    created_at TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        if not await _table_exists(conn, "members_groups"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE members_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    member_name TEXT NOT NULL,
                    relationship TEXT NOT NULL DEFAULT '',
                    dob TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
        if not await _table_exists(conn, "sig_codes"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE sig_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    full_text TEXT NOT NULL
                )
                """
            )
        if not await _table_exists(conn, "price_codes"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE price_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    price NUMERIC(10,2) NOT NULL DEFAULT 0
                )
                """
            )
        if not await _table_exists(conn, "dispenses"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE dispenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    receipt_id INTEGER,
                    product_name TEXT NOT NULL,
                    ndc_code TEXT NOT NULL DEFAULT '',
                    sig_code TEXT NOT NULL DEFAULT '',
                    quantity INTEGER NOT NULL DEFAULT 0,
                    fill_date TEXT NOT NULL,
                    price_at_time NUMERIC(10,2) NOT NULL DEFAULT 0,
                    insurance_copay NUMERIC(10,2) NOT NULL DEFAULT 0,
                    insurance_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                    internal_barcode TEXT NOT NULL DEFAULT '',
                    cashier TEXT NOT NULL DEFAULT '',
                    client_tx_id TEXT NOT NULL,
                    server_created_at TEXT,
                    UNIQUE(client_tx_id)
                )
                """
            )
        if not await _table_exists(conn, "dispense_items"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE dispense_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dispense_id INTEGER NOT NULL REFERENCES dispenses(id),
                    lot_id INTEGER,
                    lot_number TEXT NOT NULL,
                    expiration_date TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    awp_at_time NUMERIC(10,2),
                    mac_at_time NUMERIC(10,2)
                )
                """
            )
        version = 7

    # ── v8: Movement History & Demand Analytics ────────────────────────────────
    if version < 8:
        if not await _table_has_column(conn, "products", "category"):
            await conn.exec_driver_sql(
                "ALTER TABLE products ADD COLUMN category TEXT NOT NULL DEFAULT 'Uncategorized'"
            )
        if not await _table_exists(conn, "inventory_adjustments"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE inventory_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    quantity_change INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL,
                    user_id INTEGER REFERENCES users(id)
                )
                """
             )
        if not await _table_has_column(conn, "receiving_log", "lot_number"):
            await conn.exec_driver_sql(
                "ALTER TABLE receiving_log ADD COLUMN lot_number TEXT NOT NULL DEFAULT ''"
            )
        version = 8

    # ── v9: Prescriber CRUD + drug file + patient enrichment + Rx refills ──
    if version < 9:
        if not await _table_exists(conn, "prescribers"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE prescribers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL DEFAULT '',
                    last_name TEXT NOT NULL DEFAULT '',
                    npi TEXT UNIQUE,
                    dea_number TEXT,
                    state_license TEXT,
                    spi_number TEXT,
                    medicare_id TEXT,
                    medicaid_id TEXT,
                    ncpdp_id TEXT,
                    phone TEXT,
                    fax TEXT,
                    email TEXT,
                    address_line1 TEXT,
                    address_line2 TEXT,
                    city TEXT,
                    state TEXT,
                    zip TEXT,
                    quick_code TEXT,
                    eps_status TEXT,
                    service_level TEXT,
                    groups TEXT,
                    effective_date TEXT,
                    end_date TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT
                )
                """
            )
        # Product drug-file enrichment columns
        for col, ddl in (
            ("ndc_code", "TEXT"),
            ("lot_number", "TEXT"),
            ("package_size", "TEXT"),
            ("unit_of_measure", "TEXT"),
            ("form", "TEXT"),
            ("strength", "TEXT"),
            ("manufacturer_name", "TEXT"),
            ("therapeutic_class", "TEXT"),
            ("is_generic", "INTEGER NOT NULL DEFAULT 0"),
            ("is_controlled", "INTEGER NOT NULL DEFAULT 0"),
            ("default_sig_code", "TEXT"),
            ("default_qty", "INTEGER"),
            ("default_days_supply", "INTEGER"),
            ("maintenance_medication", "INTEGER NOT NULL DEFAULT 0"),
            ("image_url", "TEXT"),
            ("drug_cost", "NUMERIC(10,2)"),
        ):
            if not await _table_has_column(conn, "products", col):
                await conn.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {col} {ddl}")
        # Patient enrichment columns
        for col, ddl in (
            ("cell_phone", "TEXT"),
            ("work_phone", "TEXT"),
            ("patient_fax", "TEXT"),
            ("emergency_contact_name", "TEXT"),
            ("emergency_contact_phone", "TEXT"),
            ("emergency_contact_relationship", "TEXT"),
            ("delivery_zone", "TEXT"),
            ("delivery_status", "TEXT"),
            ("consent_flag", "INTEGER NOT NULL DEFAULT 0"),
            ("survey_num", "TEXT"),
            ("preferred_language", "TEXT"),
            ("ethnicity", "TEXT"),
            ("race", "TEXT"),
            ("marital_status", "TEXT"),
            ("patient_type", "TEXT"),
            ("pharmacy_home_id", "TEXT"),
            ("prefer_call", "INTEGER NOT NULL DEFAULT 1"),
            ("prefer_text", "INTEGER NOT NULL DEFAULT 0"),
            ("prefer_email", "INTEGER NOT NULL DEFAULT 0"),
            ("is_340b", "INTEGER NOT NULL DEFAULT 0"),
            ("last_fill_date", "TEXT"),
            ("employer_name", "TEXT"),
            ("employer_address", "TEXT"),
            ("employer_phone", "TEXT"),
            ("wc_claim_number", "TEXT"),
            ("wc_injury_date", "TEXT"),
            ("wc_injury_description", "TEXT"),
            ("wc_carrier_id", "TEXT"),
            ("wc_carrier_name", "TEXT"),
            ("prescriber_id", "INTEGER REFERENCES prescribers(id)"),
        ):
            if not await _table_has_column(conn, "patients", col):
                await conn.exec_driver_sql(f"ALTER TABLE patients ADD COLUMN {col} {ddl}")
        # Dispense Rx number + refill tracking
        for col, ddl in (
            ("rx_number", "TEXT"),
            ("refill_count", "INTEGER NOT NULL DEFAULT 0"),
            ("refills_authorized", "INTEGER NOT NULL DEFAULT 0"),
            ("last_fill_date", "TEXT"),
            ("prescriber_id", "INTEGER REFERENCES prescribers(id)"),
            ("days_supply", "INTEGER"),
        ):
            if not await _table_has_column(conn, "dispenses", col):
                await conn.exec_driver_sql(f"ALTER TABLE dispenses ADD COLUMN {col} {ddl}")
        # PriceCode multi-tier pricing
        for col, ddl in (
            ("price_level", "TEXT"),
            ("cost_factor_pct", "NUMERIC(10,2) NOT NULL DEFAULT 100"),
            ("dispensing_fee", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
            ("min_price", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
            ("max_price", "NUMERIC(10,2) NOT NULL DEFAULT 999999.99"),
            ("markup_pct", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
        ):
            if not await _table_has_column(conn, "price_codes", col):
                await conn.exec_driver_sql(f"ALTER TABLE price_codes ADD COLUMN {col} {ddl}")
        # InsurancePlan enrichment
        for col, ddl in (
            ("plan_type", "TEXT NOT NULL DEFAULT 'COMMERCIAL'"),
            ("help_desk_phone", "TEXT"),
            ("processor_id", "TEXT"),
            ("pharmacy_verified", "INTEGER NOT NULL DEFAULT 0"),
            ("deductible", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
            ("ncpcp_copay", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
            ("wc_copay", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
        ):
            if not await _table_has_column(conn, "insurance_plans", col):
                await conn.exec_driver_sql(f"ALTER TABLE insurance_plans ADD COLUMN {col} {ddl}")
        version = 9

    if version < 10:
        # Phase 2: Workers' Compensation claims table
        await conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS workers_comp_claims (
                id INTEGER PRIMARY KEY,
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                claim_number TEXT NOT NULL UNIQUE,
                carrier_id TEXT,
                carrier_name TEXT,
                injury_date TEXT,
                injury_description TEXT,
                employer_name TEXT,
                employer_address TEXT,
                employer_phone TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                dispense_id INTEGER REFERENCES dispenses(id),
                total_charges NUMERIC(10,2) NOT NULL DEFAULT 0,
                insurance_paid NUMERIC(10,2) NOT NULL DEFAULT 0,
                patient_responsibility NUMERIC(10,2) NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_wc_claims_patient ON workers_comp_claims(patient_id)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_wc_claims_status ON workers_comp_claims(status)"
        )
        version = 10

    if version < 11:
        # Phase 3: WAC column on inventory_extended + dispense_items
        if not await _table_has_column(conn, "inventory_extended", "wac"):
            await conn.exec_driver_sql("ALTER TABLE inventory_extended ADD COLUMN wac NUMERIC(10,2)")
        if not await _table_has_column(conn, "dispense_items", "wac_at_time"):
            await conn.exec_driver_sql("ALTER TABLE dispense_items ADD COLUMN wac_at_time NUMERIC(10,2)")
        version = 11

    # ── v12: M103 — 6-Screen Modernization schema extensions ────────────────
    # SigCode: language, days_accumulated, offset for the bilingual Sig Expansion Engine
    if version < 12:
        for col, ddl in (
            ("language", "TEXT NOT NULL DEFAULT 'EN'"),
            ("days_accumulated", "NUMERIC(10,4) NOT NULL DEFAULT 0"),
            ("offset", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if not await _table_has_column(conn, "sig_codes", col):
                await conn.exec_driver_sql(f"ALTER TABLE sig_codes ADD COLUMN {col} {ddl}")
        # WorkersCompClaim: 15 extended employer / Pay-To columns
        for col in (
            "employer_phone_ext",
            "employer_contact_name",
            "employer_addr_line1",
            "employer_addr_line2",
            "employer_city",
            "employer_state",
            "employer_zip",
            "pay_to",
            "pay_to_contact",
            "pay_to_phone",
            "pay_to_addr_line1",
            "pay_to_addr_line2",
            "pay_to_city",
            "pay_to_state",
            "pay_to_zip",
        ):
            if not await _table_has_column(conn, "workers_comp_claims", col):
                await conn.exec_driver_sql(f"ALTER TABLE workers_comp_claims ADD COLUMN {col} TEXT")
        # InsurancePlan: 12 master-file columns
        for col, ddl in (
            ("plan_code", "TEXT"),
            ("fax_number", "TEXT"),
            ("alt_phone", "TEXT"),
            ("contact_name", "TEXT"),
            ("address_line1", "TEXT"),
            ("address_line2", "TEXT"),
            ("city", "TEXT"),
            ("state", "TEXT"),
            ("zip", "TEXT"),
            ("co_insurance_pct", "NUMERIC(5,2) NOT NULL DEFAULT 0"),
            ("standard_copay", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
            ("notes", "TEXT"),
        ):
            if not await _table_has_column(conn, "insurance_plans", col):
                await conn.exec_driver_sql(f"ALTER TABLE insurance_plans ADD COLUMN {col} {ddl}")
        version = 12

    # ── v13: Patient name/address split + new fields + DrugDictionary table ──────
    if version < 13:
        # Patient table: split name and address, add new fields
        for col, ddl in (
            ("first_name", "TEXT"),
            ("last_name", "TEXT"),
            ("middle_initial", "TEXT"),
            ("ssn", "TEXT"),
            ("home_phone", "TEXT"),
            ("city", "TEXT"),
            ("state", "TEXT"),
            ("zip", "TEXT"),
            ("primary_care_physician", "TEXT"),
        ):
            if not await _table_has_column(conn, "patients", col):
                await conn.exec_driver_sql(f"ALTER TABLE patients ADD COLUMN {col} {ddl}")
        # Backfill: attempt to parse existing name and address
        # name -> first_name, last_name (simple split on space)
        await conn.exec_driver_sql("""
            UPDATE patients
            SET first_name = TRIM(SUBSTR(name, 1, INSTR(name || ' ', ' ') - 1)),
                last_name = TRIM(SUBSTR(name, INSTR(name || ' ', ' ') + 1))
            WHERE first_name IS NULL OR first_name = ''
        """)
        # address -> address (street), city, state, zip (simple split on comma)
        if await _table_has_column(conn, "patients", "address") and await _table_has_column(conn, "patients", "city"):
            await conn.exec_driver_sql("""
                UPDATE patients
                SET city = TRIM(SUBSTR(address, 1, INSTR(address || ',', ',') - 1)),
                    state = TRIM(SUBSTR(address, INSTR(address || ',', ',') + 1, 2)),
                    zip = TRIM(SUBSTR(address, INSTR(address || ',', ',') + 4))
                WHERE city IS NULL OR city = ''
            """)
        # Create drug_dictionary table
        if not await _table_exists(conn, "drug_dictionary"):
            await conn.exec_driver_sql("""
                CREATE TABLE drug_dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ndc_code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    strength TEXT,
                    form TEXT,
                    manufacturer TEXT,
                    dea_schedule TEXT,
                    pill_image_url TEXT,
                    source TEXT NOT NULL DEFAULT 'local',
                    last_verified TEXT,
                    created_at TEXT
                )
            """)
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_drug_dict_ndc ON drug_dictionary(ndc_code)")
        version = 13

    # ── v14: Fix patient_fax column name mismatch ──────
    if version < 14:
        has_patient_fax = await _table_has_column(conn, "patients", "patient_fax")
        has_fax = await _table_has_column(conn, "patients", "fax")
        if has_patient_fax and not has_fax:
            await conn.exec_driver_sql("ALTER TABLE patients RENAME COLUMN patient_fax TO fax")
        elif has_patient_fax and has_fax:
            await conn.exec_driver_sql("ALTER TABLE patients DROP COLUMN patient_fax")
        version = 14

    # ── v15: coupons table (Phase 1.9) ────────────────────────────────────
    if version < 15:
        if not await _table_exists(conn, "coupons"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE coupons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    discount_type TEXT NOT NULL DEFAULT '%',
                    discount_value NUMERIC(10,2) NOT NULL DEFAULT 0,
                    min_purchase NUMERIC(10,2) NOT NULL DEFAULT 0,
                    max_uses INTEGER NOT NULL DEFAULT 0,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT,
                    created_at TEXT
                )
                """
            )
        version = 15

    # ── v16: quick_sig_templates table (Phase 2.1) ────────────────────────
    if version < 16:
        if not await _table_exists(conn, "quick_sig_templates"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE quick_sig_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL DEFAULT '',
                    drug_name TEXT NOT NULL DEFAULT '',
                    dose TEXT NOT NULL DEFAULT '',
                    route TEXT NOT NULL DEFAULT '',
                    frequency TEXT NOT NULL DEFAULT '',
                    duration TEXT NOT NULL DEFAULT '',
                    directions TEXT NOT NULL DEFAULT '',
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT
                )
                """
            )
        version = 16

    # ── v17: purchase_orders + po_items tables (Phase 2.2) ─────────────────
    if version < 17:
        if not await _table_exists(conn, "purchase_orders"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE purchase_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    po_number TEXT NOT NULL UNIQUE,
                    vendor_id TEXT,
                    vendor_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Draft',
                    notes TEXT NOT NULL DEFAULT '',
                    subtotal NUMERIC(12,2) NOT NULL DEFAULT 0,
                    tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                    total_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
                    created_at TEXT,
                    submitted_at TEXT,
                    received_at TEXT,
                    closed_at TEXT,
                    created_by TEXT
                )
                """
            )
        if not await _table_exists(conn, "po_items"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE po_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    po_id INTEGER NOT NULL,
                    line_number INTEGER NOT NULL DEFAULT 0,
                    product_name TEXT NOT NULL DEFAULT '',
                    vendor_sku TEXT NOT NULL DEFAULT '',
                    quantity INTEGER NOT NULL DEFAULT 0,
                    unit_price NUMERIC(10,2) NOT NULL DEFAULT 0,
                    line_total NUMERIC(12,2) NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'Pending',
                    received_qty INTEGER NOT NULL DEFAULT 0,
                    received_at TEXT
                )
                """
            )
        version = 17

    # ── v18: receipt_templates table (Phase 3.1) ──────────────────────────
    if version < 18:
        if not await _table_exists(conn, "receipt_templates"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE receipt_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    template_type TEXT NOT NULL DEFAULT 'receipt',
                    paper_width INTEGER NOT NULL DEFAULT 42,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    sections TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
        version = 18

    # ── v19: drug_interactions table (Phase 4.1) ──────────────────────────
    if version < 19:
        if not await _table_exists(conn, "drug_interactions"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE drug_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drug_a TEXT NOT NULL,
                    drug_b TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'moderate',
                    description TEXT NOT NULL DEFAULT '',
                    recommendation TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        version = 19

    # ── v20: quick_sig_templates usage_count column (Phase 4.3) ───────────
    if version < 20:
        if await _table_exists(conn, "quick_sig_templates"):
            cols = {row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(quick_sig_templates)")).fetchall()}
            if "usage_count" not in cols:
                await conn.exec_driver_sql("ALTER TABLE quick_sig_templates ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0")
        version = 20

    # ── v21: label_templates + product_labels tables (Phase 8.1) ─────────
    if version < 21:
        if not await _table_exists(conn, "label_templates"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE label_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    canvas_width INTEGER NOT NULL DEFAULT 400,
                    canvas_height INTEGER NOT NULL DEFAULT 300,
                    elements TEXT NOT NULL DEFAULT '[]',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
        if not await _table_exists(conn, "product_labels"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE product_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL UNIQUE,
                    canvas_width INTEGER NOT NULL DEFAULT 400,
                    canvas_height INTEGER NOT NULL DEFAULT 300,
                    elements TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT
                )
                """
            )
        version = 21

    # ── v22: compound prescriptions tables ──────────────────────────────────
    if version < 22:
        if not await _table_exists(conn, "compounds"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE compounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    total_quantity REAL NOT NULL,
                    total_quantity_unit TEXT NOT NULL DEFAULT 'g',
                    sig_code TEXT NOT NULL DEFAULT 'QD',
                    days_supply INTEGER NOT NULL DEFAULT 30,
                    refills_authorized INTEGER NOT NULL DEFAULT 0,
                    refill_count INTEGER NOT NULL DEFAULT 0,
                    last_fill_date TEXT,
                    prescriber_id INTEGER REFERENCES prescribers(id),
                    price_code TEXT,
                    created_at TEXT
                )
                """
            )
        if not await _table_exists(conn, "compound_ingredients"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE compound_ingredients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compound_id INTEGER NOT NULL REFERENCES compounds(id),
                    product_name TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit TEXT NOT NULL DEFAULT 'g',
                    strength TEXT,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    ingredient_price NUMERIC(10,2) NOT NULL DEFAULT 0
                )
                """
            )
        if not await _table_exists(conn, "compound_dispenses"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE compound_dispenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compound_id INTEGER NOT NULL REFERENCES compounds(id),
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    quantity REAL NOT NULL,
                    fill_date TEXT NOT NULL,
                    total_price NUMERIC(10,2) NOT NULL DEFAULT 0,
                    insurance_copay NUMERIC(10,2) NOT NULL DEFAULT 0,
                    insurance_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                    insurance_plan_id INTEGER REFERENCES insurance_plans(id),
                    price_code TEXT,
                    client_tx_id TEXT NOT NULL UNIQUE,
                    server_created_at TEXT,
                    cashier TEXT NOT NULL DEFAULT ''
                )
                """
            )
        if not await _table_exists(conn, "compound_ingredients"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE compound_ingredients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compound_id INTEGER NOT NULL REFERENCES compounds(id),
                    product_name TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit TEXT NOT NULL DEFAULT 'g',
                    strength TEXT,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    ingredient_price NUMERIC(10,2) NOT NULL DEFAULT 0
                )
                """
            )
        if not await _table_exists(conn, "compound_dispense_items"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE compound_dispense_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compound_dispense_id INTEGER NOT NULL REFERENCES compound_dispenses(id),
                    ingredient_id INTEGER REFERENCES compound_ingredients(id),
                    product_name TEXT NOT NULL,
                    lot_id INTEGER,
                    lot_number TEXT NOT NULL DEFAULT '',
                    expiration_date TEXT NOT NULL DEFAULT '',
                    quantity_used REAL NOT NULL,
                    unit_price NUMERIC(10,2) NOT NULL DEFAULT 0,
                    total_price NUMERIC(10,2) NOT NULL DEFAULT 0
                )
                """
            )
        version = 22

    # ── v23: prior authorization table ──────────────────────────────────────
    if version < 23:
        if not await _table_exists(conn, "prior_auths"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE prior_auths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    prescriber_id INTEGER NOT NULL REFERENCES prescribers(id),
                    product_name TEXT NOT NULL,
                    ndc_code TEXT,
                    quantity INTEGER NOT NULL,
                    days_supply INTEGER NOT NULL,
                    sig_code TEXT NOT NULL,
                    diagnosis_codes TEXT NOT NULL DEFAULT '[]',
                    clinical_rationale TEXT NOT NULL,
                    prior_therapy_failed TEXT NOT NULL DEFAULT '[]',
                    insurance_plan_id INTEGER REFERENCES insurance_plans(id),
                    status TEXT NOT NULL DEFAULT 'SUBMITTED',
                    prior_auth_number TEXT,
                    denial_reason TEXT,
                    approval_duration_days INTEGER,
                    expires_at TEXT,
                    submitted_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    reviewer_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        version = 23

    # ── v24: EPCS (Electronic Prescribing for Controlled Substances) ───────────
    if version < 24:
        if not await _table_exists(conn, "epcs_prescriptions"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE epcs_prescriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    prescriber_id INTEGER NOT NULL REFERENCES prescribers(id),
                    product_name TEXT NOT NULL,
                    ndc_code TEXT,
                    schedule TEXT NOT NULL,  -- C-II, C-III, C-IV, C-V
                    quantity INTEGER NOT NULL,
                    days_supply INTEGER NOT NULL,
                    sig_code TEXT NOT NULL,
                    diagnosis_codes TEXT NOT NULL DEFAULT '[]',
                    refills INTEGER NOT NULL DEFAULT 0,
                    daw_code TEXT NOT NULL DEFAULT '00',
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT, PENDING_SIGNATURE, SIGNED, TRANSMITTED, REJECTED, ARCHIVED
                    signed_at TEXT,
                    signature_hash TEXT,  -- SHA-256 for non-repudiation
                    transmitted_at TEXT,
                    transmission_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by INTEGER NOT NULL REFERENCES users(id)
                )
                """
            )
        version = 24

    # ── v25: Clinical workflow (clinical_notes, allergy_records, clinical_attachments) ──
    if version < 25:
        if not await _table_exists(conn, "clinical_notes"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE clinical_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    dispense_id INTEGER,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
                """
            )
        if not await _table_exists(conn, "allergy_records"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE allergy_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    drug_name TEXT NOT NULL,
                    reaction TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'unknown',
                    recorded_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
                """
            )
        if not await _table_exists(conn, "clinical_attachments"):
            await conn.exec_driver_sql(
                """
                CREATE TABLE clinical_attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id),
                    dispense_id INTEGER,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    storage_path TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    uploaded_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL
                )
                """
            )
        version = 25


    # ── v26: Add custom_fields JSON to patients ───────────
    if version < 26:
        if not await _table_has_column(conn, "patients", "custom_fields"):
            await conn.exec_driver_sql(
                "ALTER TABLE patients ADD COLUMN custom_fields TEXT"
            )
        version = 26

    await conn.exec_driver_sql(f"PRAGMA user_version={SCHEMA_VERSION}")



SCHEMA_VERSION = 26

