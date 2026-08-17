"""
rx_db.py — SQLAlchemy ORM layer for PharmacyPro Rx Processing Workflow tables.

Provides ORM models and query functions for the enterprise-level Rx tables:
prescriber_table, inventory_extended, rx_table, insurance_table.
Also extends audit_logs with Rx-specific compliance columns for RBAC
(HIPAA / GDPR dual-policy) and introduces an rx_config table for region
preferences.

Mirrors the architecture of db.py — uses the same DATABASE_URL resolution
and session factory pattern so it operates on the same SQLite database
(pharmacy.db) already used by the existing pharmacy inventory system.

Usage:
    from rx_db import init_rx_tables, get_rx_status_counts, add_rx

    init_rx_tables()
    counters = get_rx_status_counts()
"""
import os
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)

try:
    from sqlalchemy import (
        create_engine, Column, Integer, Float, String, Text, ForeignKey, event, text,
    )
    from sqlalchemy.orm import declarative_base, sessionmaker, relationship
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

from path_utils import get_resource_path

try:
    from database import get_db_path
except Exception:
    def get_db_path():
        env = os.environ.get("PHARMACY_DB_PATH")
        if env:
            return env
        try:
            import barcode_logic
            config = barcode_logic.load_config()
            p = config.get("db_path", "pharmacy.db")
        except Exception:
            p = "pharmacy.db"
        return p if os.path.isabs(p) else get_resource_path("pharmacy.db")


# ── Database URL Resolution ────────────────────────────────────────────

def _resolve_rx_database_url() -> str:
    """Resolve the same DATABASE_URL used by db.py so both layers
    operate on the identical pharmacy.db file."""
    db_path_env = os.environ.get("PHARMACY_DB_PATH")
    if db_path_env:
        return "sqlite:///{}".format(db_path_env.replace("\\", "/"))

    try:
        from db import DATABASE_URL as _db_url
        if _db_url:
            return _db_url
    except Exception:
        pass

    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    try:
        config_path = get_resource_path("config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            pg_url = config.get("database_url", "")
            if pg_url:
                return pg_url
            db_path = config.get("db_path", "")
            if db_path:
                return "sqlite:///{}".format(db_path.replace("\\", "/"))
    except Exception:
        pass

    return "sqlite:///{}".format(get_db_path().replace("\\", "/"))


DATABASE_URL = _resolve_rx_database_url()


def _sqlite_path_from_url() -> str:
    """Extract the SQLite file path from DATABASE_URL.

    Falls back to ``get_db_path()`` (config.json) when the URL is not a
    recognised SQLite path or when the engine resolved via db.py.
    """
    if DATABASE_URL.startswith("sqlite:///"):
        path = DATABASE_URL[len("sqlite:///"):]
        if path:
            return path.replace("/", os.sep)
    return get_db_path()


# ── Engine & Session Factory ───────────────────────────────────────────

def _build_engine(url: str):
    if "sqlite" in url:
        eng = create_engine(
            url, echo=False, pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
        @event.listens_for(eng, "connect")
        def _set_rx_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            log.debug("Rx DB: SQLite pragmas set (WAL + FK)")
        return eng
    return create_engine(
        url, echo=False, pool_pre_ping=True,
        pool_size=5, max_overflow=10, pool_timeout=30, pool_recycle=1800,
    )


if HAS_SQLALCHEMY:
    engine = _build_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base = declarative_base()
else:
    engine = None
    SessionLocal = None
    Base = None


@contextmanager
def get_session():
    """Yield a transactional session, auto-committing on success,
    rolling back on any exception. Mirrors db.py's contract."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── ORM Models ─────────────────────────────────────────────────────────

if HAS_SQLALCHEMY:

    class Prescriber(Base):
        __tablename__ = "prescriber_table"
        id = Column(Integer, primary_key=True, autoincrement=True)
        npi = Column(String(20), nullable=True)        # nullable for EU
        dea_number = Column(String(20), nullable=True) # nullable for EU
        state_license = Column(String(50), nullable=False)
        first_name = Column(String(100), nullable=False)
        last_name = Column(String(100), nullable=False)
        phone = Column(String(20), default="")
        email = Column(String(100), default="")
        address = Column(Text, default="")
        dea_expiration = Column(String(10), default="")
        is_active = Column(Integer, default=1)
        regional_metadata = Column(Text, default="{}")

        def __repr__(self):
            return f"<Prescriber(id={self.id}, name='{self.first_name} {self.last_name}', npi='{self.npi}')>"


    class InventoryExtended(Base):
        __tablename__ = "inventory_extended"
        id = Column(Integer, primary_key=True, autoincrement=True)
        ndc_code = Column(String(20), unique=True, nullable=False)
        drug_name = Column(String(200), nullable=False)
        strength = Column(String(50), default="")
        dosage_form = Column(String(50), default="")
        ndc_formatted = Column(String(20), default="")
        awp = Column(Float, default=0.0)
        mac = Column(Float, default=0.0)
        lot_number = Column(String(50), default="")
        expiration_date = Column(String(10), default="")
        on_hand = Column(Integer, default=0)
        supplier = Column(String(100), default="")
        regional_metadata = Column(Text, default="{}")

        def __repr__(self):
            return f"<InventoryExtended(ndc='{self.ndc_code}', name='{self.drug_name}')>"


    class RxTable(Base):
        __tablename__ = "rx_table"
        id = Column(Integer, primary_key=True, autoincrement=True)
        rx_number = Column(String(30), unique=True, nullable=False)
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
        prescriber_id = Column(Integer, ForeignKey("prescriber_table.id"), nullable=False)
        drug_ndc = Column(String(20), ForeignKey("inventory_extended.ndc_code"), nullable=False)
        days_supply = Column(Integer, default=0)
        daw_code = Column(String(10), default="00")
        refills_remaining = Column(Integer, default=0)
        sig_code = Column(Text, default="")
        quantity = Column(Integer, default=0)
        status = Column(String(20), default="Pending")
        date_prescribed = Column(String(20), default="")
        date_started = Column(String(20), default="")
        date_filled = Column(String(20), default="")
        notes = Column(Text, default="")
        regional_metadata = Column(Text, default="{}")

        def __repr__(self):
            return f"<RxTable(id={self.id}, rx_number='{self.rx_number}', status='{self.status}')>"


    class Insurance(Base):
        __tablename__ = "insurance_table"
        id = Column(Integer, primary_key=True, autoincrement=True)
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
        bin_number = Column(String(20), nullable=True)  # nullable for EU
        pcn = Column(String(50), nullable=True)         # nullable for EU
        group_number = Column(String(50), nullable=True) # nullable for EU
        plan_name = Column(String(100), default="")
        carrier = Column(String(100), default="")
        regional_metadata = Column(Text, default="{}")

        def __repr__(self):
            return f"<Insurance(id={self.id}, patient_id={self.patient_id})>"


    class AuditLogEntry(Base):
        """Extended audit log model covering HIPAA retention and GDPR erasure."""
        __tablename__ = "audit_logs"
        id = Column(Integer, primary_key=True, autoincrement=True)
        timestamp = Column(String, default="")
        action = Column(String, default="")
        user_pin = Column(String, default="")
        details = Column(Text, default="")
        # Rx-specific compliance extensions
        region = Column(String, default="US")
        category = Column(String, default="")        # access|modify|delete|export
        subject_type = Column(String, default="")   # patient|rx|prescriber|inventory|insurance
        subject_id = Column(Integer, nullable=True)
        rx_id = Column(Integer, nullable=True)
        old_value = Column(Text, default="")
        new_value = Column(Text, default="")
        role = Column(String, default="user")
        gdpr_deleted = Column(Integer, default=0)   # GDPR: hard-delete flag


    class RxConfigEntry(Base):
        """Key-value store for Rx workflow runtime preferences (e.g. region)."""
        __tablename__ = "rx_config"
        key = Column(String(50), primary_key=True)
        value = Column(Text, default="")


# ── Initialization & Migration ─────────────────────────────────────────

_RX_AUDIT_COLUMNS = [
    ("region", "TEXT", "'US'"),
    ("category", "TEXT", "''"),
    ("subject_type", "TEXT", "''"),
    ("subject_id", "INTEGER", ""),
    ("rx_id", "INTEGER", ""),
    ("old_value", "TEXT", "''"),
    ("new_value", "TEXT", "''"),
    ("role", "TEXT", "'user'"),
    ("gdpr_deleted", "INTEGER", "0"),
]


def init_rx_tables():
    """Create all Rx tables via raw DDL, then run SQLite ALTER TABLE
    migrations to extend audit_logs with Rx-specific compliance columns and
    create the rx_config table.

    Raw DDL is used instead of Base.metadata.create_all() because the rx_table
    and insurance_table ORM models reference patients(id) which lives in db.py's
    separate declarative Base — SQLAlchemy cannot resolve cross-Base FKs during
    metadata sorting.  This mirrors database.py:init_db()'s CREATE TABLE IF NOT
    EXISTS + ALTER TABLE pattern.

    Safe to call multiple times (CREATE IF NOT EXISTS + try/except on ALTER).
    """
    if not HAS_SQLALCHEMY:
        raise ImportError("SQLAlchemy is required for rx_db.py. Run: pip install sqlalchemy>=2.0")

    # For non-SQLite backends, attempt ORM metadata creation first.
    if "sqlite" not in DATABASE_URL:
        try:
            Base.metadata.create_all(engine)
        except Exception as e:
            log.warning("Rx DB: create_all failed on %s, falling back to raw DDL: %s",
                        DATABASE_URL, e)

    # Derive the SQLite file path from DATABASE_URL so the raw DDL and the
    # SQLAlchemy engine operate on the SAME database file.
    db_path = _sqlite_path_from_url()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")

        # Ensure the patients table exists (created by database.py / db.py).
        # If this is a fresh DB where init_db() hasn't run yet, create a
        # minimal patients table so FK constraints resolve.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        # ── Migration: ensure insurance columns exist on patients ──
        cursor.execute("PRAGMA table_info(patients)")
        _pat_cols = {row[1] for row in cursor.fetchall()}
        for _col in ("insurance_provider", "policy_number", "group_number"):
            if _col not in _pat_cols:
                try:
                    cursor.execute(f"ALTER TABLE patients ADD COLUMN {_col} TEXT")
                except sqlite3.OperationalError:
                    pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prescriber_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                npi TEXT,
                dea_number TEXT,
                state_license TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                address TEXT DEFAULT '',
                dea_expiration TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                regional_metadata TEXT DEFAULT '{}'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_extended (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ndc_code TEXT UNIQUE NOT NULL,
                drug_name TEXT NOT NULL,
                strength TEXT DEFAULT '',
                dosage_form TEXT DEFAULT '',
                ndc_formatted TEXT DEFAULT '',
                awp REAL DEFAULT 0.0,
                mac REAL DEFAULT 0.0,
                lot_number TEXT DEFAULT '',
                expiration_date TEXT DEFAULT '',
                on_hand INTEGER DEFAULT 0,
                supplier TEXT DEFAULT '',
                regional_metadata TEXT DEFAULT '{}'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rx_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rx_number TEXT UNIQUE NOT NULL,
                patient_id INTEGER NOT NULL,
                prescriber_id INTEGER NOT NULL,
                drug_ndc TEXT NOT NULL,
                days_supply INTEGER DEFAULT 0,
                daw_code TEXT DEFAULT '00',
                refills_remaining INTEGER DEFAULT 0,
                sig_code TEXT DEFAULT '',
                quantity INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Pending',
                date_prescribed TEXT DEFAULT '',
                date_started TEXT DEFAULT '',
                date_filled TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                regional_metadata TEXT DEFAULT '{}',
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                FOREIGN KEY (prescriber_id) REFERENCES prescriber_table(id),
                FOREIGN KEY (drug_ndc) REFERENCES inventory_extended(ndc_code)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insurance_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                bin_number TEXT,
                pcn TEXT,
                group_number TEXT,
                plan_name TEXT DEFAULT '',
                carrier TEXT DEFAULT '',
                regional_metadata TEXT DEFAULT '{}',
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        """)

        # Conditional unique indexes for NPI/DEA (SQLite partial indexes
        # — ORM cannot express partial uniqueness)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_prescriber_npi
            ON prescriber_table(npi) WHERE npi IS NOT NULL AND npi != ''
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_prescriber_dea
            ON prescriber_table(dea_number) WHERE dea_number IS NOT NULL AND dea_number != ''
        """)

        # Ensure audit_logs table exists (created by audit_log.py:init_audit_db).
        # CREATE TABLE IF NOT EXISTS is idempotent — safe to call here.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                user_pin TEXT DEFAULT '',
                details TEXT DEFAULT ''
            )
        """)

        # Extend audit_logs with Rx-specific compliance columns
        for col_name, col_type, default in _RX_AUDIT_COLUMNS:
            try:
                ddl = f"ALTER TABLE audit_logs ADD COLUMN {col_name} {col_type}"
                if default:
                    ddl += f" DEFAULT {default}"
                cursor.execute(ddl)
                log.debug("Audit log extended with column: %s", col_name)
            except sqlite3.OperationalError as e:
                op_msg = str(e).lower()
                if "duplicate column" in op_msg:
                    log.debug("Rx DB: audit_logs column %s already exists — skipping", col_name)
                else:
                    raise

        # rx_config table for region preferences
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rx_config (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )
        """)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    log.info(
        "Rx tables initialized (DATABASE_URL=%s)",
        DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL,
    )


# ── Rx Number Generation ───────────────────────────────────────────────

_RX_NUMBER_PREFIX = "RX"


def _generate_rx_number() -> str:
    """Generate a unique Rx number: RX-YYYY-MM-NNNNNN (sequential per year-month)."""
    with get_session() as s:
        today = datetime.now()
        year_month = today.strftime("%Y-%m")
        prefix = f"{_RX_NUMBER_PREFIX}-{year_month}-"
        result = s.execute(text("""
            SELECT MAX(rx_number) FROM rx_table
            WHERE rx_number LIKE :prefix
        """), {"prefix": f"{prefix}%"}).scalar()
        if result:
            try:
                seq = int(result.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:06d}"


# ── Prescriber CRUD ────────────────────────────────────────────────────

def add_prescriber(npi: str, dea_number: str, state_license: str,
                   first_name: str, last_name: str, phone: str = "",
                   email: str = "", address: str = "", dea_expiration: str = "",
                   regional_metadata: Optional[Dict[str, Any]] = None) -> int:
    """Add a prescriber.  *regional_metadata* is stored as a JSON-serialised
    TEXT column (US defaults to ``{}``)."""
    meta_json = json.dumps(regional_metadata) if regional_metadata else "{}"
    with get_session() as s:
        result = s.execute(text("""
            INSERT INTO prescriber_table
                (npi, dea_number, state_license, first_name, last_name,
                 phone, email, address, dea_expiration, is_active, regional_metadata)
            VALUES (:npi, :dea, :lic, :fn, :ln, :phone, :email, :addr, :dea_exp, 1, :meta)
        """), {
            "npi": npi, "dea": dea_number, "lic": state_license,
            "fn": first_name, "ln": last_name, "phone": phone,
            "email": email, "addr": address, "dea_exp": dea_expiration,
            "meta": meta_json,
        })
        return result.lastrowid


def add_prescriber_regional(region: str, **fields) -> int:
    """Insert a prescriber with region-appropriate regional_metadata.

    For EU, fields like ``registration_id`` and ``qualification`` are stored
    inside the JSON metadata; for US, ``npi``/``dea_number`` live in their
    own columns but are mirrored in metadata for audit completeness.
    """
    metadata: Dict[str, Any] = {"region": region}
    metadata.update(fields.pop("regional_metadata", {}))
    if region == "EU":
        metadata.setdefault("registration_id", fields.get("registration_id", ""))
        metadata.setdefault("qualification", fields.get("qualification", ""))
    else:
        metadata.setdefault("npi", fields.get("npi") or "")
        metadata.setdefault("dea_number", fields.get("dea_number") or "")
    meta_json = json.dumps(metadata)
    with get_session() as s:
        result = s.execute(text("""
            INSERT INTO prescriber_table
                (npi, dea_number, state_license, first_name, last_name,
                 phone, email, address, dea_expiration, is_active, regional_metadata)
            VALUES (:npi, :dea, :lic, :fn, :ln, :phone, :email, :addr, :dea_exp, 1, :meta)
        """), {
            "npi": fields.get("npi"), "dea": fields.get("dea_number"),
            "lic": fields.get("state_license"),
            "fn": fields.get("first_name"), "ln": fields.get("last_name"),
            "phone": fields.get("phone", ""),
            "email": fields.get("email", ""),
            "addr": fields.get("address", ""),
            "dea_exp": fields.get("dea_expiration", ""),
            "meta": meta_json,
        })
        return result.lastrowid


def get_prescriber_by_id(prescriber_id: int):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, npi, dea_number, state_license, first_name, last_name,
                   phone, email, address, dea_expiration, is_active, regional_metadata
            FROM prescriber_table WHERE id = :pid
        """), {"pid": prescriber_id})
        row = result.fetchone()
        return tuple(row) if row else None


def get_prescriber_regional(prescriber_id: int):
    """Return prescriber row + parsed regional_metadata JSON."""
    row = get_prescriber_by_id(prescriber_id)
    if not row:
        return None
    col_names = [
        "id", "npi", "dea_number", "state_license", "first_name", "last_name",
        "phone", "email", "address", "dea_expiration", "is_active", "regional_metadata",
    ]
    result = dict(zip(col_names, row))
    try:
        result["regional_metadata"] = json.loads(result["regional_metadata"] or "{}")
    except (ValueError, TypeError):
        result["regional_metadata"] = {}
    return result


def get_prescriber_by_npi(npi: str):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, npi, dea_number, state_license, first_name, last_name,
                   phone, email, address, dea_expiration, is_active, regional_metadata
            FROM prescriber_table WHERE npi = :npi
        """), {"npi": npi})
        row = result.fetchone()
        return tuple(row) if row else None


def search_prescribers(query: str):
    like = f"%{query}%"
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, npi, dea_number, state_license, first_name, last_name,
                   phone, email, address, dea_expiration, is_active, regional_metadata
            FROM prescriber_table
            WHERE first_name LIKE :q
               OR last_name LIKE :q
               OR npi LIKE :q
               OR dea_number LIKE :q
               OR state_license LIKE :q
            ORDER BY last_name ASC, first_name ASC
        """), {"q": like})
        return [tuple(r) for r in result.fetchall()]


def get_all_prescribers():
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, npi, dea_number, state_license, first_name, last_name,
                   phone, email, address, dea_expiration, is_active, regional_metadata
            FROM prescriber_table WHERE is_active = 1
            ORDER BY last_name ASC, first_name ASC
        """))
        return [tuple(r) for r in result.fetchall()]


# ── Inventory Extended CRUD ────────────────────────────────────────────

def add_inventory_item(ndc_code: str, drug_name: str, strength: str = "",
                       dosage_form: str = "", ndc_formatted: str = "",
                       awp: float = 0.0, mac: float = 0.0,
                       lot_number: str = "", expiration_date: str = "",
                       on_hand: int = 0, supplier: str = "",
                       regional_metadata: Optional[Dict[str, Any]] = None) -> int:
    meta_json = json.dumps(regional_metadata) if regional_metadata else "{}"
    with get_session() as s:
        result = s.execute(text("""
            INSERT INTO inventory_extended
                (ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                 awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata)
            VALUES (:ndc, :name, :strength, :form, :ndc_fmt,
                    :awp, :mac, :lot, :exp, :oh, :sup, :meta)
        """), {
            "ndc": ndc_code, "name": drug_name, "strength": strength,
            "form": dosage_form, "ndc_fmt": ndc_formatted,
            "awp": awp, "mac": mac, "lot": lot_number,
            "exp": expiration_date, "oh": on_hand, "sup": supplier,
            "meta": meta_json,
        })
        return result.lastrowid


def add_inventory_item_regional(region: str, **fields) -> int:
    """Insert an inventory item with region-appropriate regional_metadata.

    Metadata records the code format (NDC vs PZN) and any region-specific
    verification data (e.g. PZN check digit for EU).
    """
    metadata: Dict[str, Any] = {"region": region}
    metadata.update(fields.pop("regional_metadata", {}))
    if region == "US":
        metadata.setdefault("code_format", "NDC")
    else:
        metadata.setdefault("code_format", "PZN")
        metadata.setdefault("pzn_check_digit", fields.get("pzn_check_digit", ""))
    meta_json = json.dumps(metadata)
    with get_session() as s:
        result = s.execute(text("""
            INSERT INTO inventory_extended
                (ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                 awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata)
            VALUES (:ndc, :name, :strength, :form, :ndc_fmt,
                    :awp, :mac, :lot, :exp, :oh, :sup, :meta)
        """), {
            "ndc": fields.get("ndc_code"), "name": fields.get("drug_name"),
            "strength": fields.get("strength", ""),
            "form": fields.get("dosage_form", ""),
            "ndc_fmt": fields.get("ndc_formatted", ""),
            "awp": fields.get("awp", 0.0),
            "mac": fields.get("mac", 0.0),
            "lot": fields.get("lot_number", ""),
            "exp": fields.get("expiration_date", ""),
            "oh": fields.get("on_hand", 0),
            "sup": fields.get("supplier", ""),
            "meta": meta_json,
        })
        return result.lastrowid


def get_inventory_item(ndc_code: str):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                   awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata
            FROM inventory_extended WHERE ndc_code = :ndc
        """), {"ndc": ndc_code})
        row = result.fetchone()
        return tuple(row) if row else None


def search_inventory(query: str):
    """Search inventory by NDC/PZN code or drug name."""
    like = f"%{query}%"
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                   awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata
            FROM inventory_extended
            WHERE ndc_code LIKE :q
               OR drug_name LIKE :q
               OR ndc_formatted LIKE :q
            ORDER BY drug_name ASC
        """), {"q": like})
        return [tuple(r) for r in result.fetchall()]


def get_all_inventory():
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                   awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata
            FROM inventory_extended ORDER BY drug_name ASC
        """))
        return [tuple(r) for r in result.fetchall()]


def update_inventory_on_hand(ndc_code: str, on_hand: int) -> bool:
    with get_session() as s:
        result = s.execute(text("""
            UPDATE inventory_extended SET on_hand = :oh WHERE ndc_code = :ndc
        """), {"oh": on_hand, "ndc": ndc_code})
        return result.rowcount > 0


# ── Rx Table CRUD ─────────────────────────────────────────────────────

RX_STATUSES = ("Pending", "Billed", "Filled", "Verified", "Will Call", "Rejected")


def add_rx(patient_id: int, prescriber_id: int, drug_ndc: str,
           days_supply: int = 0, daw_code: str = "00", refills: int = 0,
           sig_code: str = "", quantity: int = 0,
           date_prescribed: str = "", notes: str = "",
           regional_metadata: Optional[Dict[str, Any]] = None) -> int:
    rx_number = _generate_rx_number()
    now = datetime.now().strftime("%Y-%m-%d")
    meta_json = json.dumps(regional_metadata) if regional_metadata else "{}"
    with get_session() as s:
        result = s.execute(text("""
            INSERT INTO rx_table
                (rx_number, patient_id, prescriber_id, drug_ndc,
                 days_supply, daw_code, refills_remaining, sig_code,
                 quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata)
            VALUES (:rxn, :pid, :prid, :ndc, :ds, :daw, :ref, :sig,
                    :qty, 'Pending', :dp, :ds2, '', :notes, :meta)
        """), {
            "rxn": rx_number,
            "pid": patient_id, "prid": prescriber_id, "ndc": drug_ndc,
            "ds": days_supply, "daw": daw_code, "ref": refills,
            "sig": sig_code, "qty": quantity,
            "dp": date_prescribed or now,
            "ds2": date_prescribed or now,
            "notes": notes,
            "meta": meta_json,
        })
        return result.lastrowid


def add_rx_regional(region: str, patient_id: int, prescriber_id: int,
                    drug_ndc: str, **fields) -> int:
    """Insert a prescription with region-appropriate regional_metadata.

    For US metadata stores claim_id/pcn; for EU it stores fmd_verification
    and nhs_number.
    """
    metadata: Dict[str, Any] = {"region": region}
    metadata.update(fields.pop("regional_metadata", {}))
    if region == "US":
        metadata.setdefault("claim_id", fields.get("claim_id", ""))
        metadata.setdefault("pcn", fields.get("pcn", ""))
    else:
        metadata.setdefault("fmd_verification", fields.get("fmd_verification", ""))
        metadata.setdefault("nhs_number", fields.get("nhs_number", ""))
    meta_json = json.dumps(metadata)
    rx_number = _generate_rx_number()
    now = datetime.now().strftime("%Y-%m-%d")
    with get_session() as s:
        result = s.execute(text("""
            INSERT INTO rx_table
                (rx_number, patient_id, prescriber_id, drug_ndc,
                 days_supply, daw_code, refills_remaining, sig_code,
                 quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata)
            VALUES (:rxn, :pid, :prid, :ndc, :ds, :daw, :ref, :sig,
                    :qty, 'Pending', :dp, :ds2, '', :notes, :meta)
        """), {
            "rxn": rx_number,
            "pid": patient_id, "prid": prescriber_id, "ndc": drug_ndc,
            "ds": fields.get("days_supply", 0),
            "daw": fields.get("daw_code", "00"),
            "ref": fields.get("refills", 0),
            "sig": fields.get("sig_code", ""),
            "qty": fields.get("quantity", 0),
            "dp": fields.get("date_prescribed", now),
            "ds2": fields.get("date_prescribed", now),
            "notes": fields.get("notes", ""),
            "meta": meta_json,
        })
        return result.lastrowid


def get_rx_by_id(rx_id: int):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, rx_number, patient_id, prescriber_id, drug_ndc,
                   days_supply, daw_code, refills_remaining, sig_code,
                   quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata
            FROM rx_table WHERE id = :rid
        """), {"rid": rx_id})
        row = result.fetchone()
        return tuple(row) if row else None


def get_rx_by_number(rx_number: str):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, rx_number, patient_id, prescriber_id, drug_ndc,
                   days_supply, daw_code, refills_remaining, sig_code,
                   quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata
            FROM rx_table WHERE rx_number = :rxn
        """), {"rxn": rx_number})
        row = result.fetchone()
        return tuple(row) if row else None


def get_rxs_by_patient(patient_id: int):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, rx_number, patient_id, prescriber_id, drug_ndc,
                   days_supply, daw_code, refills_remaining, sig_code,
                   quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata
            FROM rx_table WHERE patient_id = :pid
            ORDER BY id DESC
        """), {"pid": patient_id})
        return [tuple(r) for r in result.fetchall()]


def get_rxs_by_status(status: str):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, rx_number, patient_id, prescriber_id, drug_ndc,
                   days_supply, daw_code, refills_remaining, sig_code,
                   quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata
            FROM rx_table WHERE status = :status
            ORDER BY id DESC
        """), {"status": status})
        return [tuple(r) for r in result.fetchall()]


def get_rx_status_counts() -> dict:
    """Return {status_name: count, total: N} for all Rx statuses.
    Used by the Right Sidebar Dashboard for real-time counters."""
    with get_session() as s:
        result = s.execute(text("""
            SELECT status, COUNT(*) FROM rx_table GROUP BY status
        """))
        counts = {status: 0 for status in RX_STATUSES}
        for row in result.fetchall():
            counts[row[0]] = row[1]
        counts["total"] = sum(counts.values())
        return counts


def update_rx_status(rx_id: int, new_status: str, user_pin: str = "", role: str = "user",
                     region: str = "US", subject_type: str = "rx", subject_id: int = None) -> bool:
    """Update Rx status and log the change to audit_logs for RBAC compliance.

    Mirrors the existing mark_item_as_sold / audit_log.log_action pattern.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_session() as s:
        row = s.execute(text("""
            SELECT status FROM rx_table WHERE id = :rid
        """), {"rid": rx_id}).fetchone()
        if not row:
            return False
        old_status = row[0]

        s.execute(text("""
            UPDATE rx_table SET status = :new_status, date_started = :now
            WHERE id = :rid
        """), {
            "new_status": new_status,
            "now": ts,
            "rid": rx_id,
        })

        s.execute(text("""
            INSERT INTO audit_logs (timestamp, action, user_pin, details,
                                     region, category, subject_type, subject_id,
                                     rx_id, old_value, new_value, role)
            VALUES (:ts, :action, :pin, :details,
                    :region, :category, :st, :sid, :rid, :old, :new, :role)
        """), {
            "ts": ts,
            "action": "RX_STATUS_CHANGE",
            "pin": user_pin,
            "details": f"Rx #{rx_id} status changed from '{old_status}' to '{new_status}'",
            "region": region,
            "category": "modify",
            "st": subject_type,
            "sid": subject_id if subject_id is not None else rx_id,
            "rid": rx_id,
            "old": old_status,
            "new": new_status,
            "role": role,
        })
        return True


def update_rx_filled(rx_id: int, user_pin: str = "", role: str = "user",
                     region: str = "US") -> bool:
    """Mark a prescription as Filled, recording the fill timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_session() as s:
        row = s.execute(text("""
            SELECT status FROM rx_table WHERE id = :rid
        """), {"rid": rx_id}).fetchone()
        if not row:
            return False
        old_status = row[0]

        s.execute(text("""
            UPDATE rx_table SET status = 'Filled', date_filled = :ts
            WHERE id = :rid
        """), {"ts": ts, "rid": rx_id})

        s.execute(text("""
            INSERT INTO audit_logs (timestamp, action, user_pin, details,
                                     region, category, subject_type, subject_id,
                                     rx_id, old_value, new_value, role)
            VALUES (:ts, :action, :pin, :details,
                    :region, :category, :st, :sid, :rid, :old, :new, :role)
        """), {
            "ts": ts,
            "action": "RX_FILLED",
            "pin": user_pin,
            "details": f"Rx #{rx_id} filled (was '{old_status}')",
            "region": region,
            "category": "modify",
            "st": "rx",
            "sid": rx_id,
            "rid": rx_id,
            "old": old_status,
            "new": "Filled",
            "role": role,
        })
        return True


def get_rx_audit_log(rx_id: int, limit: int = 100):
    """Return audit trail entries for a specific Rx, newest first."""
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, timestamp, action, user_pin, details,
                   region, category, subject_type, subject_id,
                   rx_id, old_value, new_value, role
            FROM audit_logs
            WHERE rx_id = :rid
            ORDER BY id DESC LIMIT :limit
        """), {"rid": rx_id, "limit": limit})
        return [tuple(r) for r in result.fetchall()]


# ── Insurance CRUD ─────────────────────────────────────────────────────

def add_insurance(patient_id: int, bin_number: str, pcn: str,
                  group_number: str, plan_name: str = "", carrier: str = "",
                  regional_metadata: Optional[Dict[str, Any]] = None) -> int:
    meta_json = json.dumps(regional_metadata) if regional_metadata else "{}"
    with get_session() as s:
        result = s.execute(text("""
            INSERT INTO insurance_table
                (patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata)
            VALUES (:pid, :bin, :pcn, :gn, :pn, :car, :meta)
        """), {
            "pid": patient_id, "bin": bin_number, "pcn": pcn,
            "gn": group_number, "pn": plan_name, "car": carrier,
            "meta": meta_json,
        })
        return result.lastrowid


def get_insurance_by_patient(patient_id: int):
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata
            FROM insurance_table WHERE patient_id = :pid
            ORDER BY id DESC
        """), {"pid": patient_id})
        return [tuple(r) for r in result.fetchall()]


def get_all_insurance():
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata
            FROM insurance_table ORDER BY id DESC
        """))
        return [tuple(r) for r in result.fetchall()]


def search_insurance(query: str):
    like = f"%{query}%"
    with get_session() as s:
        result = s.execute(text("""
            SELECT id, patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata
            FROM insurance_table
            WHERE bin_number LIKE :q
               OR pcn LIKE :q
               OR group_number LIKE :q
               OR plan_name LIKE :q
               OR carrier LIKE :q
            ORDER BY id DESC
        """), {"q": like})
        return [tuple(r) for r in result.fetchall()]


# ── Region Config ──────────────────────────────────────────────────────

def set_region_config(region: str):
    """Store region preference in the rx_config table."""
    with get_session() as s:
        s.execute(text("""
            INSERT OR REPLACE INTO rx_config (key, value) VALUES ('region', :val)
        """), {"val": region})


def get_region_config() -> Optional[str]:
    """Read the current region from the rx_config table."""
    with get_session() as s:
        result = s.execute(text(
            "SELECT value FROM rx_config WHERE key = 'region'"
        )).scalar()
        return result if result else None


# ── GDPR / HIPAA Compliance ────────────────────────────────────────────

def gdpr_hard_delete_patient(patient_id: int):
    """Physically delete audit_logs rows for a patient (GDPR right to erasure).

    This contrasts with HIPAA retention — the ``region`` column on audit_logs
    determines which policy applies.  Call only when region == 'EU'.
    """
    with get_session() as s:
        s.execute(text("""
            DELETE FROM audit_logs
            WHERE subject_type = 'patient' AND subject_id = :pid
        """), {"pid": patient_id})


def hipaa_log_access(subject_type: str, subject_id: int,
                     role: str = "user", pin: str = ""):
    """HIPAA-compliant access log entry.

    Honours the current region from ``rx_config`` so that the ``region``
    column on audit_logs is always set correctly.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    region = get_region_config()
    if not region:
        region = "US"
    with get_session() as s:
        s.execute(text("""
            INSERT INTO audit_logs
                (timestamp, action, user_pin, details,
                 region, category, subject_type, subject_id,
                 old_value, new_value, role)
            VALUES (:ts, :action, :pin, :details,
                    :region, :category, :st, :sid,
                    :old, :new, :role)
        """), {
            "ts": ts,
            "action": "ACCESS",
            "pin": pin,
            "details": f"Accessed {subject_type} id={subject_id}",
            "region": region,
            "category": "access",
            "st": subject_type,
            "sid": subject_id,
            "old": "",
            "new": "",
            "role": role,
        })


# ── Region-Aware Labels ────────────────────────────────────────────────

REGION_LABELS = {
    "US": {
        "prescriber_id_label": "NPI Number",
        "patient_dob_label": "Date of Birth (MM/DD/YYYY)",
        "weight_label": "Weight (lb)",
        "height_label": "Height (in)",
        "drug_code_label": "NDC Code",
        "insurance_bin_label": "BIN Number",
        "state_field_label": "State License",
    },
    "EU": {
        "prescriber_id_label": "Prescriber Reg #",
        "patient_dob_label": "Date of Birth (DD/MM/YYYY)",
        "weight_label": "Weight (kg)",
        "height_label": "Height (cm)",
        "drug_code_label": "PZN Code",
        "insurance_bin_label": "Scheme/PCN",
        "state_field_label": "Professional Register",
    },
}


def get_prescriber_labels(region: str = "US") -> dict:
    """Return region-appropriate field labels.

    Used by the UI to dynamically relabel form fields based on the
    ConfigManager region.
    """
    return REGION_LABELS.get(region, REGION_LABELS["US"])


# ── Stubs for when SQLAlchemy is not available ─────────────────────────

if not HAS_SQLALCHEMY:
    def init_rx_tables():
        raise ImportError("SQLAlchemy is required for rx_db.py. Run: pip install sqlalchemy>=2.0")

    _NOT_AVAILABLE_NAMES = [
        "get_session",
        "add_prescriber", "add_prescriber_regional",
        "get_prescriber_by_id", "get_prescriber_regional",
        "get_prescriber_by_npi", "search_prescribers", "get_all_prescribers",
        "add_inventory_item", "add_inventory_item_regional",
        "get_inventory_item", "search_inventory", "get_all_inventory",
        "update_inventory_on_hand",
        "add_rx", "add_rx_regional",
        "get_rx_by_id", "get_rx_by_number", "get_rxs_by_patient",
        "get_rxs_by_status", "get_rx_status_counts", "update_rx_status",
        "update_rx_filled", "get_rx_audit_log",
        "add_insurance", "get_insurance_by_patient", "get_all_insurance",
        "search_insurance", "_generate_rx_number",
        "set_region_config", "get_region_config",
        "gdpr_hard_delete_patient", "hipaa_log_access",
        "get_prescriber_labels", "REGION_LABELS",
        "RxConfigEntry", "AuditLogEntry",
    ]

    def _not_available(*a, **kw):
        raise ImportError("SQLAlchemy is required for rx_db.py. Run: pip install sqlalchemy>=2.0")

    for _name in _NOT_AVAILABLE_NAMES:
        globals()[_name] = _not_available
