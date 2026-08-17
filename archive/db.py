"""
db.py — Database Abstraction Layer for PharmacyPro.

Provides SQLAlchemy ORM models, a session factory, and query functions
that return identical tuple structures to the original database.py.
Supports both SQLite (local) and PostgreSQL (networked) via DATABASE_URL.

Usage:
    from db import init_db, get_session, get_all_products

    init_db()
    with get_session() as s:
        rows = s.execute(text("SELECT ...")).fetchall()
"""
import os
import json
import shutil
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from typing import Optional
from collections import defaultdict

try:
    from sqlalchemy import (
        create_engine, Column, Integer, Float, String, Text, ForeignKey, event, text,
    )
    from sqlalchemy.orm import declarative_base, sessionmaker, relationship
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

from path_utils import get_resource_path

log = logging.getLogger(__name__)

# ── Database URL Resolution ────────────────────────────────────────────

def _sqlite_url(path: str) -> str:
    """Build a SQLAlchemy SQLite URL from a file path, handling Windows
    absolute paths (drive letter) with the correct number of slashes."""
    norm = path.replace("\\", "/")
    if len(norm) >= 2 and norm[1] == ":" and (len(norm) == 2 or norm[2] == "/"):
        return "sqlite:///" + norm  # 4 leading slashes for Windows absolute
    return "sqlite:///" + norm  # relative path

def _resolve_database_url() -> str:
    """Resolve the DATABASE_URL from env var, config.json (database_url or
    db_path), or SQLite fallback."""
    db_path_env = os.environ.get("PHARMACY_DB_PATH")
    if db_path_env:
        return _sqlite_url(db_path_env)
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
                return _sqlite_url(db_path)
    except Exception:
        pass

    return _sqlite_url(get_resource_path("pharmacy.db"))


DATABASE_URL = _resolve_database_url()


# ── Engine & Session Factory ───────────────────────────────────────────

def _build_engine(url: str):
    if "sqlite" in url:
        return create_engine(
            url, echo=False, pool_pre_ping=True,
            connect_args={"check_same_thread": False, "uri": True},
        )
    return create_engine(
        url, echo=False, pool_pre_ping=True,
        pool_size=5, max_overflow=10, pool_timeout=30, pool_recycle=1800,
    )


def reconnect_db(new_url: Optional[str] = None):
    global engine, SessionLocal, DATABASE_URL
    if new_url is None:
        DATABASE_URL = _resolve_database_url()
    else:
        DATABASE_URL = new_url
    if engine is not None:
        engine.dispose()
    engine = _build_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    if "sqlite" in DATABASE_URL:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    log.info("Database reconnected to: %s", DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL)


def test_connection(url: str) -> dict:
    backend = "postgresql" if "postgresql" in url else "sqlite"
    try:
        test_eng = create_engine(url, pool_pre_ping=True,
            connect_args={"check_same_thread": False} if "sqlite" in url else {})
        with test_eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_eng.dispose()
        return {"ok": True, "error": None, "backend": backend}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "backend": backend}


def get_db_path() -> str:
    """Return the SQLite database file path (backward compat with database.py).

    Resolution order: PHARMACY_DB_PATH (test/CI isolation) -> config.db_path
    (normalized to the app root when relative) -> bundled pharmacy.db.
    Relative db_path values are anchored to get_resource_path() so the live
    database is never created relative to the current working directory.
    """
    env = os.environ.get("PHARMACY_DB_PATH")
    if env:
        return env
    try:
        import barcode_logic
        config = barcode_logic.load_config()
        p = config.get("db_path", "pharmacy.db")
    except Exception:
        p = "pharmacy.db"
    return p if os.path.isabs(p) else get_resource_path(p)


# ── Module-level defaults ──────────────────────────────────────────────

engine = None
SessionLocal = None
Base = None
Product = SoldItem = Template = ReceivingLog = None
Receipt = ReceiptItem = Patient = PatientField = AuditLog = None


if not HAS_SQLALCHEMY:
    def init_db():
        raise ImportError("SQLAlchemy is required for db.py. Run: pip install sqlalchemy>=2.0")

    @contextmanager
    def get_session():
        raise ImportError("SQLAlchemy is required for db.py. Run: pip install sqlalchemy>=2.0")

    def reconnect_db(new_url=None):
        raise ImportError("SQLAlchemy is required for db.py. Run: pip install sqlalchemy>=2.0")

    def test_connection(url):
        return {"ok": False, "error": "SQLAlchemy not installed", "backend": "unknown"}

    def _not_available(*a, **kw):
        raise ImportError("SQLAlchemy is required for db.py. Run: pip install sqlalchemy>=2.0")

    for _name in [
        "get_db_path", "find_product_by_barcode", "add_product", "get_all_products",
        "get_product_by_id", "search_products", "get_grouped_products",
        "get_products_with_vendors", "get_unique_product_names", "get_product_template",
        "get_products_by_vendor", "get_batches_by_name", "get_all_in_stock_batches",
        "search_all_batches", "get_product_by_internal_barcode", "search_grouped_products",
        "update_product_dates", "update_product_full", "get_expiring_batches",
        "get_batches_expiring_within", "get_expiring_counts_by_vendor",
        "get_product_by_barcode", "update_product_status", "mark_item_as_sold",
        "reverse_sale", "get_sold_items", "get_today_sales_total", "get_sales_for_date",
        "get_templates", "add_template", "update_template", "delete_template",
        "log_shipment", "receive_inventory_atomically", "get_all_receiving_log",
        "get_vendor_total_owed", "get_all_vendors",          "create_receipt", "checkout_cart_atomically", "get_receipts",
        "get_receipt_items", "get_all_receipt_items_flat", "get_receipt_items_for_date",
        "get_receipt_items_grouped_by_date", "get_receipts_total_for_date",
        "reverse_receipt_item", "backup_database", "get_dashboard_metrics",
        "get_low_stock_products", "get_top_selling_products", "get_sales_analytics",
        "get_sales_by_period", "add_patient", "get_all_patients", "get_patient_by_id",
        "update_patient", "delete_patient", "get_distinct_patient_field_names",
        "get_suppliers", "get_supplier_by_id", "add_supplier", "update_supplier",
        "delete_supplier", "get_purchase_orders", "get_po_by_id", "get_po_items",
        "get_next_po_number", "add_purchase_order", "update_po_status", "add_po_item",
        "update_po_item", "delete_po_item", "update_po_totals",
        "get_products_below_reorder_threshold", "receive_po_items",
    ]:
        globals()[_name] = _not_available

else:
    engine = _build_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base = declarative_base()

    @contextmanager
    def get_session():
        """Yield a transactional session, auto-committing on success."""
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── ORM Models (matching database.py schema exactly) ─────────────────

    class Product(Base):
        __tablename__ = "products"
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False)
        price = Column(Float, nullable=False)
        manufacturer_barcode = Column(String, nullable=False, default="")
        internal_unique_barcode = Column(String, nullable=False, unique=True)
        status = Column(String, default="In Stock")
        expiry_date = Column(String, default="")
        manufacture_date = Column(String, default="")
        vendor_name = Column(String, default="N/A")
        dea_schedule = Column(String(10), default="OTC")
        wholesale_price = Column(Float, default=0.0)
        reorder_threshold = Column(Integer, default=0)

        def __repr__(self):
            return f"<Product(id={self.id}, name='{self.name}', barcode='{self.internal_unique_barcode}')>"


    class Template(Base):
        __tablename__ = "templates"
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False)
        price = Column(Float, nullable=False)

        def __repr__(self):
            return f"<Template(id={self.id}, name='{self.name}')>"


    class SoldItem(Base):
        __tablename__ = "sold_items"
        id = Column(Integer, primary_key=True, autoincrement=True)
        item_name = Column(String, nullable=False)
        price = Column(Float, nullable=False)
        manufacturer_barcode = Column(String, nullable=False)
        internal_barcode = Column(String, nullable=False)
        timestamp_of_sale = Column(String, nullable=False)
        vendor_name = Column(String, default="N/A")

        def __repr__(self):
            return f"<SoldItem(id={self.id}, item_name='{self.item_name}')>"


    class ReceivingLog(Base):
        __tablename__ = "receiving_log"
        id = Column(Integer, primary_key=True, autoincrement=True)
        vendor_name = Column(String, nullable=False)
        product_name = Column(String, nullable=False)
        date_received = Column(String, nullable=False)
        quantity = Column(Integer, nullable=False)
        total_cost = Column(Float, nullable=False)
        barcode = Column(String, default="")

        def __repr__(self):
            return f"<ReceivingLog(id={self.id}, vendor='{self.vendor_name}')>"


    class Receipt(Base):
        __tablename__ = "receipts"
        id = Column(Integer, primary_key=True, autoincrement=True)
        timestamp = Column(String, nullable=False)
        total_amount = Column(Float, nullable=False)
        payment_method = Column(String, default="Cash")
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
        sale_type = Column(String, default="OTC")
        insurance_copay = Column(Float, default=0.0)
        insurance_amount = Column(Float, default=0.0)

        items = relationship("ReceiptItem", back_populates="receipt", lazy="dynamic")
        patient = relationship("Patient", back_populates="receipts")

        def __repr__(self):
            return f"<Receipt(id={self.id}, total={self.total_amount})>"


    class ReceiptItem(Base):
        __tablename__ = "receipt_items"
        id = Column(Integer, primary_key=True, autoincrement=True)
        receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)
        product_name = Column(String, nullable=False)
        quantity = Column(Integer, nullable=False)
        price_at_time = Column(Float, nullable=False)
        internal_barcode = Column(String, default="")
        vendor = Column(String, default="")
        expiry_date = Column(String, default="")

        receipt = relationship("Receipt", back_populates="items")

        def __repr__(self):
            return f"<ReceiptItem(id={self.id}, name='{self.product_name}')>"


    class Patient(Base):
        __tablename__ = "patients"
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False)
        phone = Column(String, default="")
        email = Column(String, default="")
        created_at = Column(String, nullable=False)
        insurance_provider = Column(String, default="")
        policy_number = Column(String, default="")
        group_number = Column(String, default="")

        receipts = relationship("Receipt", back_populates="patient", lazy="dynamic")
        custom_fields = relationship("PatientField", back_populates="patient", lazy="dynamic")

        def __repr__(self):
            return f"<Patient(id={self.id}, name='{self.name}')>"


    class PatientField(Base):
        __tablename__ = "patient_fields"
        id = Column(Integer, primary_key=True, autoincrement=True)
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
        field_name = Column(String, nullable=False)
        field_value = Column(String, default="")

        patient = relationship("Patient", back_populates="custom_fields")


    class QuickSigTemplate(Base):
        __tablename__ = "quick_sig_templates"
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False)
        drug_name = Column(String, default="")
        dose = Column(String, default="")
        route = Column(String, default="")
        frequency = Column(String, default="")
        duration = Column(String, default="")
        directions = Column(String, default="")
        is_favorite = Column(Integer, default=0)
        created_at = Column(String, nullable=False)

        def __repr__(self):
            return f"<QuickSigTemplate(id={self.id}, name='{self.name}')>"


    class AuditLog(Base):
        __tablename__ = "audit_logs"
        id = Column(Integer, primary_key=True, autoincrement=True)
        timestamp = Column(String, default="")
        action = Column(String, default="")
        user_pin = Column(String, default="")
        details = Column(Text, default="")


    class Supplier(Base):
        __tablename__ = "suppliers"
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False, unique=True)
        contact_name = Column(String, default="")
        contact_email = Column(String, default="")
        contact_phone = Column(String, default="")
        address = Column(String, default="")
        tax_id = Column(String, default="")
        preferred = Column(Integer, default=0)
        sku = Column(String, default="")
        min_stock_level = Column(Integer, default=0)
        lead_time_days = Column(Integer, default=0)
        edi_endpoint = Column(String, default="")
        edi_api_key = Column(String, default="")
        performance_notes = Column(Text, default="")
        created_at = Column(String, default="")
        updated_at = Column(String, default="")


    class PurchaseOrder(Base):
        __tablename__ = "purchase_orders"
        id = Column(Integer, primary_key=True, autoincrement=True)
        po_number = Column(String, nullable=False, unique=True)
        vendor_id = Column(Integer, ForeignKey("suppliers.id"))
        vendor_name = Column(String, nullable=False)
        status = Column(String, default="Draft")
        created_at = Column(String, nullable=False, server_default=text("datetime('now')"))
        submitted_at = Column(String)
        received_at = Column(String)
        closed_at = Column(String)
        subtotal = Column(Float, default=0.0)
        tax_amount = Column(Float, default=0.0)
        total_cost = Column(Float, default=0.0)
        notes = Column(Text, default="")


    class PoItem(Base):
        __tablename__ = "po_items"
        id = Column(Integer, primary_key=True, autoincrement=True)
        po_id = Column(Integer, ForeignKey("purchase_orders.id"))
        line_number = Column(Integer, nullable=False)
        product_name = Column(String, nullable=False)
        vendor_sku = Column(String, default="")
        quantity = Column(Integer, default=0)
        unit_price = Column(Float, default=0.0)
        line_total = Column(Float, default=0.0)
        status = Column(String, default="Pending")
        internal_barcodes = Column(Text, default="")
        received_at = Column(String)
        mfg_barcode = Column(String, default="")
        expiry_date = Column(String, default="")
        mfg_date = Column(String, default="")


    # ── Initialization & Migration ─────────────────────────────────────

    def init_db():
        """Create all tables (via ORM metadata) and run SQLite migrations
        for backward compatibility with databases created by database.py.
        Seeds default templates if the templates table is empty.
        """
        Base.metadata.create_all(engine)
        # Ensure DDL is committed before opening a raw sqlite3 connection,
        # otherwise the PRAGMA checks below can see a stale schema snapshot.
        try:
            engine.dispose()
        except Exception:
            pass

        if "sqlite" in DATABASE_URL:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            try:
                for col, col_type, default in [
                    ("status", "TEXT", "'In Stock'"),
                    ("expiry_date", "TEXT", "''"),
                    ("manufacture_date", "TEXT", "''"),
                    ("vendor_name", "TEXT", "'N/A'"),
                    ("manufacturer_barcode", "TEXT", "''"),
                ]:
                    try:
                        cursor.execute(f"ALTER TABLE products ADD COLUMN {col} {col_type} DEFAULT {default}")
                    except sqlite3.OperationalError:
                        pass

                try:
                    cursor.execute("ALTER TABLE sold_items ADD COLUMN vendor_name TEXT DEFAULT 'N/A'")
                except sqlite3.OperationalError:
                    pass

                try:
                    cursor.execute("ALTER TABLE receiving_log ADD COLUMN barcode TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass

                try:
                    cursor.execute("ALTER TABLE receipts ADD COLUMN patient_id INTEGER DEFAULT NULL")
                except sqlite3.OperationalError:
                    pass

                for _col_def in (
                    "sale_type TEXT DEFAULT 'OTC'",
                    "insurance_copay REAL DEFAULT 0.0",
                    "insurance_amount REAL DEFAULT 0.0",
                ):
                    try:
                        cursor.execute(f"ALTER TABLE receipts ADD COLUMN {_col_def}")
                    except sqlite3.OperationalError:
                        pass

                cursor.execute("PRAGMA table_info(receipt_items)")
                ri_cols = {row[1] for row in cursor.fetchall()}
                for col, default in [("internal_barcode", ""), ("vendor", ""), ("expiry_date", "")]:
                    if col not in ri_cols:
                        try:
                            cursor.execute(f"ALTER TABLE receipt_items ADD COLUMN {col} TEXT DEFAULT '{default}'")
                        except sqlite3.OperationalError:
                            pass

                cursor.execute("PRAGMA table_info(products)")
                cols = {row[1] for row in cursor.fetchall()}
                for col, col_type, default in [
                    ("dea_schedule", "TEXT", "'OTC'"),
                    ("wholesale_price", "REAL", "0.0"),
                    ("reorder_threshold", "INTEGER", "0"),
                ]:
                    if col not in cols:
                        try:
                            cursor.execute(f"ALTER TABLE products ADD COLUMN {col} {col_type} DEFAULT {default}")
                        except sqlite3.OperationalError:
                            pass
                cursor.execute("PRAGMA table_info(products)")
                cols = {row[1] for row in cursor.fetchall()}
                expected = {'id', 'name', 'price', 'manufacturer_barcode', 'internal_unique_barcode',
                           'status', 'expiry_date', 'manufacture_date', 'vendor_name',
                           'dea_schedule', 'wholesale_price', 'reorder_threshold'}
                if not expected.issubset(cols):
                    missing = expected - cols
                    raise RuntimeError(f"Database schema integrity failure. Missing columns: {missing}")

                # ── Migration: ensure insurance columns exist on patients ─
                cursor.execute("PRAGMA table_info(patients)")
                _pat_cols = {row[1] for row in cursor.fetchall()}
                for _col in ("insurance_provider", "policy_number", "group_number"):
                    if _col not in _pat_cols:
                        try:
                            cursor.execute(f"ALTER TABLE patients ADD COLUMN {_col} TEXT")
                        except sqlite3.OperationalError:
                            pass

                cursor.execute("SELECT COUNT(*) FROM templates")
                if cursor.fetchone()[0] == 0:
                    defaults = [
                        ("Aspirin 500mg", 5.99),
                        ("Band-Aids (40ct)", 3.49),
                        ("Ibuprofen 200mg", 6.50),
                        ("Cough Syrup", 8.99),
                    ]
                    cursor.executemany("INSERT INTO templates (name, price) VALUES (?, ?)", defaults)

                # ── Backfill: register existing vendors as suppliers (idempotent) ──
                cursor.execute("SELECT name FROM suppliers")
                _existing = {row[0] for row in cursor.fetchall()}
                cursor.execute(
                    "SELECT DISTINCT vendor_name FROM receiving_log "
                    "WHERE vendor_name != '' AND vendor_name != 'N/A' ORDER BY vendor_name"
                )
                for (_vendor,) in cursor.fetchall():
                    if _vendor not in _existing:
                        cursor.execute(
                            "INSERT OR IGNORE INTO suppliers (name, preferred) VALUES (?, 0)",
                            (_vendor,),
                        )
                        _existing.add(_vendor)

                # ── RBAC: roles / users / permissions / role_permissions / settings ──
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS roles (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        name        TEXT NOT NULL UNIQUE,
                        description TEXT DEFAULT '',
                        is_system   INTEGER DEFAULT 0
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        username        TEXT NOT NULL UNIQUE,
                        display_name    TEXT DEFAULT '',
                        password_hash   BLOB NOT NULL,
                        pin_hash        BLOB DEFAULT NULL,
                        role_id         INTEGER REFERENCES roles(id),
                        is_active       INTEGER DEFAULT 1,
                        failed_attempts INTEGER DEFAULT 0,
                        locked_until    TEXT DEFAULT '',
                        created_at      TEXT DEFAULT (datetime('now'))
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS permissions (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        feature_key TEXT NOT NULL UNIQUE,
                        description TEXT DEFAULT ''
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS role_permissions (
                        role_id       INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                        permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
                        granted       INTEGER DEFAULT 1,
                        PRIMARY KEY (role_id, permission_id)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key   TEXT PRIMARY KEY,
                        value BLOB DEFAULT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_perms_role ON role_permissions(role_id)")

                import auth_crypto
                cursor.executemany(
                    "INSERT OR IGNORE INTO permissions (feature_key, description) VALUES (?, ?)",
                    [
                        ("sales.view", "View sales"),
                        ("sales.modify_report", "Modify daily sales reports"),
                        ("audit.view", "Access audit logs"),
                        ("audit.export", "Export audit logs"),
                        ("inventory.view", "View inventory"),
                        ("inventory.manage", "Manage inventory"),
                        ("inventory.receive", "Receive inventory"),
                        ("reports.view", "View reports"),
                        ("pos.sell", "Process sales"),
                        ("pos.refund", "Process refunds"),
                        ("users.manage", "Manage users"),
                        ("roles.manage", "Manage roles & permissions"),
                        ("settings.manage", "Manage settings"),
                        ("settings.view", "View application settings"),
                        ("backup.manage", "Create and restore database backups"),
                    ],
                )
                _RBAC_ROLES = {
                    "owner": {
                        "sales.view", "sales.modify_report", "audit.view", "audit.export",
                        "inventory.view", "inventory.manage", "inventory.receive",
                        "reports.view", "pos.sell", "pos.refund",
                        "pos.price_override", "pos.void",
                        "users.manage", "roles.manage", "settings.manage",
                    },
                    "manager": {
                        "sales.view", "sales.modify_report", "audit.view", "audit.export",
                        "inventory.view", "inventory.manage", "inventory.receive",
                        "reports.view", "pos.sell", "pos.refund",
                        "pos.price_override", "pos.void", "settings.manage",
                        "settings.view", "backup.manage",
                    },
                    "pharmacist": {
                        "sales.view", "inventory.view", "inventory.receive",
                        "pos.sell", "pos.refund", "reports.view",
                        "pos.price_override", "pos.void", "settings.view",
                    },
                    "cashier": {"sales.view", "inventory.view", "pos.sell",
                                "pos.price_override", "pos.void", "settings.view", "reports.view"},
                }
                for _role_name, _keys in _RBAC_ROLES.items():
                    _is_system = 1 if _role_name == "owner" else 0
                    cursor.execute(
                        "INSERT OR IGNORE INTO roles (name, description, is_system) VALUES (?, ?, ?)",
                        (_role_name, f"Seed role: {_role_name}", _is_system),
                    )
                    cursor.execute("SELECT id FROM roles WHERE name = ?", (_role_name,))
                    _rid = cursor.fetchone()[0]
                    for _key in _keys:
                        cursor.execute("SELECT id FROM permissions WHERE feature_key = ?", (_key,))
                        _pid = cursor.fetchone()
                        if _pid:
                            cursor.execute(
                                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id, granted) VALUES (?, ?, 1)",
                                (_rid, _pid[0]),
                            )
                cursor.execute("SELECT value FROM system_settings WHERE key = 'owner_override_hash'")
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT OR IGNORE INTO system_settings (key, value) VALUES ('owner_override_hash', ?)",
                        (auth_crypto.hash_secret("ChangeMe!Owner"),),
                    )

                # Rotation flag: '0' until the Owner overrides the bootstrap secret (G8).
                cursor.execute("SELECT value FROM system_settings WHERE key = 'owner_override_rotated'")
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT OR IGNORE INTO system_settings (key, value) VALUES ('owner_override_rotated', '0')",
                    )

                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            Base.metadata.create_all(engine)

    # ── RBAC (roles / users / permissions) — SQLAlchemy-backed parity ──
    # These mirror archive/database.py exactly so both backends behave
    # identically. They run on the same SQLite file (raw SQL via session).

    def count_users() -> int:
        with get_session() as s:
            return s.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]

    def get_roles():
        with get_session() as s:
            rows = s.execute(
                text("SELECT id, name, description, is_system FROM roles ORDER BY id")
            ).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def get_permissions():
        with get_session() as s:
            rows = s.execute(
                text("SELECT id, feature_key, description FROM permissions ORDER BY id")
            ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def get_role_permissions(role_id: int) -> set:
        with get_session() as s:
            rows = s.execute(text(
                "SELECT p.feature_key FROM role_permissions rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :rid AND rp.granted = 1"
            ), {"rid": role_id}).fetchall()
        return {r[0] for r in rows}

    def get_user_role_id(user_id: int):
        with get_session() as s:
            row = s.execute(
                text("SELECT role_id FROM users WHERE id = :uid"), {"uid": user_id}
            ).fetchone()
        return row[0] if row else None

    def get_role_name(role_id: int):
        with get_session() as s:
            row = s.execute(
                text("SELECT name FROM roles WHERE id = :rid"), {"rid": role_id}
            ).fetchone()
        return row[0] if row else None

    def get_user_display(user_id: int) -> str:
        with get_session() as s:
            row = s.execute(
                text("SELECT display_name, username FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).fetchone()
        if not row:
            return ""
        display, username = row[0], row[1]
        return (display or "").strip() or (username or "").strip() or ""

    def get_user_permissions(user_id: int) -> set:
        role_id = get_user_role_id(user_id)
        if role_id is None:
            return set()
        if get_role_name(role_id) == "owner":
            with get_session() as s:
                rows = s.execute(text("SELECT feature_key FROM permissions")).fetchall()
            return {r[0] for r in rows}
        return get_role_permissions(role_id)

    def create_role(name: str, description: str = "") -> int:
        with get_session() as s:
            s.execute(
                text("INSERT OR IGNORE INTO roles (name, description, is_system) VALUES (:n, :d, 0)"),
                {"n": name, "d": description},
            )
            rid = s.execute(
                text("SELECT id FROM roles WHERE name = :n"), {"n": name}
            ).fetchone()[0]
        return rid

    def assign_role_to_user(user_id: int, role_id: int):
        with get_session() as s:
            s.execute(
                text("UPDATE users SET role_id = :rid WHERE id = :uid"),
                {"rid": role_id, "uid": user_id},
            )

    def set_role_permissions(role_id: int, feature_keys: set):
        with get_session() as s:
            s.execute(
                text("DELETE FROM role_permissions WHERE role_id = :rid"), {"rid": role_id}
            )
            for key in feature_keys:
                pid = s.execute(
                    text("SELECT id FROM permissions WHERE feature_key = :k"), {"k": key}
                ).fetchone()
                if pid:
                    s.execute(
                        text("INSERT OR IGNORE INTO role_permissions (role_id, permission_id, granted) "
                             "VALUES (:rid, :pid, 1)"),
                        {"rid": role_id, "pid": pid[0]},
                    )

    def grant_permission(role_id: int, feature_key: str, granted: bool = True):
        with get_session() as s:
            pid = s.execute(
                text("SELECT id FROM permissions WHERE feature_key = :k"), {"k": feature_key}
            ).fetchone()
            if pid:
                s.execute(
                    text("INSERT OR REPLACE INTO role_permissions (role_id, permission_id, granted) "
                         "VALUES (:rid, :pid, :g)"),
                    {"rid": role_id, "pid": pid[0], "g": 1 if granted else 0},
                )

    def toggle_permission(role_id: int, feature_key: str) -> bool:
        new_state = False
        with get_session() as s:
            pid = s.execute(
                text("SELECT id FROM permissions WHERE feature_key = :k"), {"k": feature_key}
            ).fetchone()
            if pid:
                cur = s.execute(
                    text("SELECT granted FROM role_permissions WHERE role_id = :rid AND permission_id = :pid"),
                    {"rid": role_id, "pid": pid[0]},
                ).fetchone()
                new_state = not bool(cur[0]) if cur else True
                s.execute(
                    text("INSERT OR REPLACE INTO role_permissions (role_id, permission_id, granted) "
                         "VALUES (:rid, :pid, :g)"),
                    {"rid": role_id, "pid": pid[0], "g": 1 if new_state else 0},
                )
        return new_state

    def create_user(username: str, secret: str, role_id: int, display_name: str = "", pin: str = "") -> int:
        import auth_crypto
        pw_hash = auth_crypto.hash_secret(secret)
        pin_hash = auth_crypto.hash_secret(pin) if pin else None
        with get_session() as s:
            s.execute(text(
                "INSERT INTO users (username, display_name, password_hash, pin_hash, role_id, is_active, created_at) "
                "VALUES (:u, :dn, :pw, :ph, :rid, 1, datetime('now'))"
            ), {"u": username, "dn": display_name, "pw": pw_hash, "ph": pin_hash, "rid": role_id})
            uid = s.execute(
                text("SELECT id FROM users WHERE username = :u"), {"u": username}
            ).fetchone()[0]
        return uid

    def authenticate_user(username: str, secret: str):
        from datetime import datetime, timedelta
        import auth_crypto
        with get_session() as s:
            row = s.execute(text(
                "SELECT id, password_hash, is_active, failed_attempts, locked_until "
                "FROM users WHERE username = :u"
            ), {"u": username}).fetchone()
            if not row:
                return None
            user_id, pw_hash, is_active, failed, locked_until = row
            if not is_active:
                return None
            if locked_until:
                try:
                    if datetime.fromisoformat(locked_until) > datetime.now():
                        return None
                except ValueError:
                    pass
            if auth_crypto.verify_secret(secret, pw_hash):
                s.execute(
                    text("UPDATE users SET failed_attempts = 0, locked_until = '' WHERE id = :uid"),
                    {"uid": user_id},
                )
                return user_id
            failed = (failed or 0) + 1
            if failed >= 5:
                until = (datetime.now() + timedelta(minutes=15)).isoformat()
                s.execute(
                    text("UPDATE users SET failed_attempts = :f, locked_until = :u WHERE id = :uid"),
                    {"f": failed, "u": until, "uid": user_id},
                )
            else:
                s.execute(
                    text("UPDATE users SET failed_attempts = :f WHERE id = :uid"),
                    {"f": failed, "uid": user_id},
                )
            return None

    def verify_user_pin(user_id: int, pin: str) -> bool:
        import auth_crypto
        with get_session() as s:
            row = s.execute(
                text("SELECT pin_hash FROM users WHERE id = :uid"), {"uid": user_id}
            ).fetchone()
        if not row or not row[0]:
            return False
        return auth_crypto.verify_secret(pin, row[0])

    def user_has_pin(user_id: int) -> bool:
        with get_session() as s:
            row = s.execute(
                text("SELECT pin_hash FROM users WHERE id = :uid"), {"uid": user_id}
            ).fetchone()
        return bool(row and row[0])

    def set_owner_override_password(new_password: str):
        import auth_crypto
        with get_session() as s:
            s.execute(
                text("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('owner_override_hash', :v)"),
                {"v": auth_crypto.hash_secret(new_password)},
            )

    def verify_owner_override(password: str) -> bool:
        import auth_crypto
        with get_session() as s:
            row = s.execute(
                text("SELECT value FROM system_settings WHERE key = 'owner_override_hash'")
            ).fetchone()
        if not row or not row[0]:
            return False
        return auth_crypto.verify_secret(password, row[0])

    _BOOTSTRAP_OVERRIDE = "ChangeMe!Owner"

    def is_owner_override_default() -> bool:
        import auth_crypto
        with get_session() as s:
            row = s.execute(
                text("SELECT value FROM system_settings WHERE key = 'owner_override_hash'")
            ).fetchone()
        if not row or not row[0]:
            return False
        return auth_crypto.verify_secret(_BOOTSTRAP_OVERRIDE, row[0])

    def mark_owner_override_rotated() -> None:
        with get_session() as s:
            s.execute(
                text("INSERT OR REPLACE INTO system_settings (key, value) "
                     "VALUES ('owner_override_rotated', '1')")
            )

    def is_owner_override_rotated() -> bool:
        with get_session() as s:
            row = s.execute(
                text("SELECT value FROM system_settings WHERE key = 'owner_override_rotated'")
            ).fetchone()
        return bool(row and row[0] == "1")

    # ── Query Functions (return tuples matching database.py) ────────────

    def find_product_by_barcode(barcode: str):
        """Look up a product by internal or manufacturer barcode.
        Returns an ORM Product object (used by ui_settings_tab.py)."""
        with get_session() as s:
            p = s.query(Product).filter_by(internal_unique_barcode=barcode).first()
            if p:
                return p
            return s.query(Product).filter_by(manufacturer_barcode=barcode).first()

    def add_product(name: str, price: float, manufacturer_barcode: str,
                    internal_unique_barcode: str, expiry_date: str = '',
                    manufacture_date: str = '', vendor_name: str = 'N/A'):
        with get_session() as s:
            s.execute(text("""
                INSERT INTO products
                    (name, price, manufacturer_barcode, internal_unique_barcode,
                     status, expiry_date, manufacture_date, vendor_name)
                VALUES (:name, :price, :mfg_barcode, :int_barcode,
                        'In Stock', :expiry, :mfg_date, :vendor)
            """), {
                "name": name, "price": price, "mfg_barcode": manufacturer_barcode,
                "int_barcode": internal_unique_barcode, "expiry": expiry_date,
                "mfg_date": manufacture_date, "vendor": vendor_name,
            })

    def get_all_products():
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
            """))
            return [tuple(r) for r in result.fetchall()]

    def get_product_by_id(product_id: int):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products WHERE id = :pid
            """), {"pid": product_id})
            row = result.fetchone()
            return tuple(row) if row else None

    def search_products(query: str):
        with get_session() as s:
            like = f"%{query}%"
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE manufacturer_barcode LIKE :q
                   OR internal_unique_barcode LIKE :q
                   OR name LIKE :q
            """), {"q": like})
            return [tuple(r) for r in result.fetchall()]

    def get_grouped_products():
        with get_session() as s:
            result = s.execute(text("""
                SELECT name, COUNT(*) as qty, MIN(price) as min_price, MAX(price) as max_price
                FROM products
                WHERE status = 'In Stock'
                GROUP BY name
                ORDER BY name ASC
            """))
            return [tuple(r) for r in result.fetchall()]

    def get_products_with_vendors():
        with get_session() as s:
            result = s.execute(text("""
                SELECT DISTINCT name, COALESCE(vendor_name, 'N/A') as vendor_name, internal_unique_barcode
                FROM products
                WHERE status = 'In Stock'
                ORDER BY name ASC
            """))
            return [tuple(r) for r in result.fetchall()]

    def get_unique_product_names():
        with get_session() as s:
            result = s.execute(text("""
                SELECT DISTINCT name
                FROM products
                WHERE status = 'In Stock'
                ORDER BY name ASC
            """))
            return [r[0] for r in result.fetchall()]

    def get_product_template(name: str, vendor_name: str = None):
        with get_session() as s:
            if vendor_name and vendor_name.strip() and vendor_name.strip() != 'N/A':
                result = s.execute(text("""
                    SELECT name, price, manufacturer_barcode, expiry_date, manufacture_date
                    FROM products
                    WHERE name = :name AND vendor_name = :vendor AND status = 'In Stock'
                    ORDER BY id DESC LIMIT 1
                """), {"name": name, "vendor": vendor_name.strip()})
            else:
                result = s.execute(text("""
                    SELECT name, price, manufacturer_barcode, expiry_date, manufacture_date
                    FROM products
                    WHERE name = :name AND status = 'In Stock'
                    ORDER BY id DESC LIMIT 1
                """), {"name": name})
            row = result.fetchone()
            return tuple(row) if row else None

    def get_products_by_vendor(vendor_name: str = None):
        with get_session() as s:
            if vendor_name and vendor_name.strip() and vendor_name.strip() != 'N/A':
                result = s.execute(text("""
                    SELECT DISTINCT name FROM products
                    WHERE vendor_name = :vendor AND status = 'In Stock'
                    ORDER BY name ASC
                """), {"vendor": vendor_name.strip()})
            else:
                result = s.execute(text("""
                    SELECT DISTINCT name FROM products
                    WHERE status = 'In Stock'
                    ORDER BY name ASC
                """))
            return [r[0] for r in result.fetchall()]

    def get_batches_by_name(drug_name: str, sort_by: str = 'expiry_date'):
        with get_session() as s:
            valid = {'expiry_date': 'expiry_date ASC', 'manufacture_date': 'manufacture_date DESC'}
            order = valid.get(sort_by, 'expiry_date ASC')
            result = s.execute(text(f"""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE name = :name AND status = 'In Stock'
                ORDER BY {order}
            """), {"name": drug_name})
            return [tuple(r) for r in result.fetchall()]

    def get_all_in_stock_batches(sort_by: str = 'expiry_date'):
        with get_session() as s:
            valid = {
                'expiry_date': 'expiry_date ASC, name ASC',
                'manufacture_date': 'manufacture_date DESC, name ASC',
                'name': 'name ASC, expiry_date ASC',
                'vendor': 'vendor_name ASC, name ASC',
            }
            order = valid.get(sort_by, 'expiry_date ASC, name ASC')
            result = s.execute(text(f"""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE status = 'In Stock'
                ORDER BY {order}
            """))
            return [tuple(r) for r in result.fetchall()]

    def search_all_batches(query: str):
        with get_session() as s:
            like = f"%{query}%"
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE status = 'In Stock'
                  AND (name LIKE :q OR manufacturer_barcode LIKE :q OR internal_unique_barcode LIKE :q
                       OR vendor_name LIKE :q OR expiry_date LIKE :q)
                ORDER BY name ASC, expiry_date ASC
            """), {"q": like})
            return [tuple(r) for r in result.fetchall()]

    def get_product_by_internal_barcode(internal_barcode: str):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE internal_unique_barcode = :bc AND status = 'In Stock'
            """), {"bc": internal_barcode})
            row = result.fetchone()
            return tuple(row) if row else None

    def search_grouped_products(query: str):
        with get_session() as s:
            like = f"%{query}%"
            result = s.execute(text("""
                SELECT name, COUNT(*) as qty, MIN(price) as min_price, MAX(price) as max_price
                FROM products
                WHERE status = 'In Stock'
                  AND (name LIKE :q OR manufacturer_barcode LIKE :q OR internal_unique_barcode LIKE :q)
                GROUP BY name
                ORDER BY name ASC
            """), {"q": like})
            return [tuple(r) for r in result.fetchall()]

    def update_product_dates(product_id: int, expiry_date: str, manufacture_date: str):
        with get_session() as s:
            s.execute(text("""
                UPDATE products SET expiry_date = :expiry, manufacture_date = :mfg
                WHERE id = :pid
            """), {"expiry": expiry_date, "mfg": manufacture_date, "pid": product_id})

    def update_product_full(product_id: int, name: str, price: float, manufacturer_barcode: str,
                            internal_barcode: str, expiry_date: str, manufacture_date: str,
                            status: str, vendor_name: str = 'N/A'):
        with get_session() as s:
            s.execute(text("""
                UPDATE products SET name = :name, price = :price,
                    manufacturer_barcode = :mfg_barcode,
                    internal_unique_barcode = :int_barcode,
                    expiry_date = :expiry,
                    manufacture_date = :mfg_date,
                    status = :status,
                    vendor_name = :vendor
                WHERE id = :pid
            """), {
                "name": name, "price": price, "mfg_barcode": manufacturer_barcode,
                "int_barcode": internal_barcode, "expiry": expiry_date,
                "mfg_date": manufacture_date, "status": status,
                "vendor": vendor_name, "pid": product_id,
            })
            s.execute(text("""
                UPDATE receiving_log SET vendor_name = :vendor, product_name = :pname
                WHERE barcode = :bc AND barcode != ''
            """), {"vendor": vendor_name, "pname": name, "bc": internal_barcode})
            s.execute(text("""
                UPDATE receiving_log SET total_cost = :price * quantity
                WHERE barcode = :bc AND barcode != ''
            """), {"price": price, "bc": internal_barcode})

    def get_expiring_batches(exclude_names=None):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE status = 'In Stock'
                  AND expiry_date != ''
                ORDER BY expiry_date ASC
            """))
            all_rows = [tuple(r) for r in result.fetchall()]

        today = date.today()
        exclude_set = set(n.lower().strip() for n in exclude_names) if exclude_names else set()
        out = []
        for row in all_rows:
            if exclude_set and row[1].lower().strip() in exclude_set:
                continue
            raw = row[6]
            try:
                normalized = raw.replace('/', '-')
                parts = normalized.split('-')
                exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                out.append((exp_date, row))
            except (ValueError, IndexError):
                continue
        return out

    def get_batches_expiring_within(days: int, exclude_names=None):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE status = 'In Stock'
                  AND expiry_date != ''
                ORDER BY expiry_date ASC
            """))
            all_rows = [tuple(r) for r in result.fetchall()]

        today = date.today()
        cutoff = today + timedelta(days=days)
        exclude_set = set(n.lower().strip() for n in exclude_names) if exclude_names else set()
        out = []
        for row in all_rows:
            if exclude_set and row[1].lower().strip() in exclude_set:
                continue
            raw = row[6]
            try:
                normalized = raw.replace('/', '-')
                parts = normalized.split('-')
                exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                if exp_date <= cutoff:
                    out.append(row)
            except (ValueError, IndexError):
                continue
        return out

    def get_expiring_counts_by_vendor(days: int, exclude_names=None):
        batches = get_batches_expiring_within(days, exclude_names=exclude_names)
        counts = {}
        for row in batches:
            vendor = row[8] or "N/A"
            counts[vendor] = counts.get(vendor, 0) + 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)

    def get_product_by_barcode(barcode: str):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE manufacturer_barcode = :bc OR internal_unique_barcode = :bc
            """), {"bc": barcode})
            row = result.fetchone()
            return tuple(row) if row else None

    def update_product_status(barcode: str, new_status: str):
        with get_session() as s:
            s.execute(text("""
                UPDATE products
                SET status = :status
                WHERE manufacturer_barcode = :bc OR internal_unique_barcode = :bc
            """), {"status": new_status, "bc": barcode})

    def mark_item_as_sold(barcode: str):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, vendor_name
                FROM products
                WHERE manufacturer_barcode = :bc OR internal_unique_barcode = :bc
            """), {"bc": barcode})
            product = result.fetchone()
            if not product:
                raise ValueError("Product not found.")

            product_id, name, price, mfg_barcode, int_barcode, vendor_name = product
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            s.execute(text("""
                INSERT INTO sold_items
                    (item_name, price, manufacturer_barcode, internal_barcode,
                     timestamp_of_sale, vendor_name)
                VALUES (:name, :price, :mfg_barcode, :int_barcode, :ts, :vendor)
            """), {
                "name": name, "price": price, "mfg_barcode": mfg_barcode,
                "int_barcode": int_barcode, "ts": ts,
                "vendor": vendor_name or 'N/A',
            })
            s.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": product_id})

    def reverse_sale(sold_item_id: int):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, item_name, price, manufacturer_barcode, internal_barcode, vendor_name
                FROM sold_items
                WHERE id = :sid
            """), {"sid": sold_item_id})
            sold_item = result.fetchone()
            if not sold_item:
                raise ValueError("Sold item not found.")

            _id, name, price, mfg_barcode, int_barcode, vendor_name = sold_item
            s.execute(text("""
                INSERT INTO products
                    (name, price, manufacturer_barcode, internal_unique_barcode,
                     status, vendor_name)
                VALUES (:name, :price, :mfg_barcode, :int_barcode, 'In Stock', :vendor)
            """), {
                "name": name, "price": price, "mfg_barcode": mfg_barcode,
                "int_barcode": int_barcode, "vendor": vendor_name or 'N/A',
            })
            s.execute(text("DELETE FROM sold_items WHERE id = :sid"), {"sid": sold_item_id})

    def get_sold_items():
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, item_name, price, manufacturer_barcode, internal_barcode,
                       timestamp_of_sale, COALESCE(vendor_name, 'N/A') as vendor_name
                FROM sold_items
                ORDER BY timestamp_of_sale DESC
            """))
            return [tuple(r) for r in result.fetchall()]

    def get_today_sales_total():
        today = datetime.now().strftime("%Y-%m-%d")
        with get_session() as s:
            result = s.execute(text("""
                SELECT COALESCE(SUM(price), 0.0) FROM sold_items
                WHERE timestamp_of_sale LIKE :today
            """), {"today": f"{today}%"})
            return result.scalar()

    def get_sales_for_date(date_str: str):
        with get_session() as s:
            result = s.execute(text("""
                SELECT COALESCE(SUM(price), 0.0) FROM sold_items
                WHERE timestamp_of_sale LIKE :ds
            """), {"ds": f"{date_str}%"})
            return result.scalar()

    def get_templates():
        with get_session() as s:
            result = s.execute(text("SELECT id, name, price FROM templates ORDER BY name ASC"))
            return [tuple(r) for r in result.fetchall()]

    def add_template(name: str, price: float):
        with get_session() as s:
            s.execute(text("INSERT INTO templates (name, price) VALUES (:name, :price)"),
                      {"name": name, "price": price})

    def update_template(template_id: int, name: str, price: float):
        with get_session() as s:
            s.execute(text("UPDATE templates SET name = :name, price = :price WHERE id = :tid"),
                      {"name": name, "price": price, "tid": template_id})

    def delete_template(template_id: int):
        with get_session() as s:
            s.execute(text("DELETE FROM templates WHERE id = :tid"), {"tid": template_id})

    def log_shipment(vendor_name: str, product_name: str, date_received: str,
                     quantity: int, total_cost: float, barcode: str = ''):
        with get_session() as s:
            s.execute(text("""
                INSERT INTO receiving_log
                    (vendor_name, product_name, date_received, quantity, total_cost, barcode)
                VALUES (:vendor, :pname, :date, :qty, :cost, :barcode)
            """), {
                "vendor": vendor_name, "pname": product_name,
                "date": date_received, "qty": quantity,
                "cost": total_cost, "barcode": barcode,
            })

    def receive_inventory_atomically(vendor_name: str, product_name: str,
                                     date_received: str, quantity: int, total_cost: float,
                                     tpl_price: float, tpl_mfg_barcode: str,
                                     tpl_expiry: str, tpl_mfg_date: str,
                                     barcode_generator, pre_generated_barcodes=None):
        if pre_generated_barcodes is None:
            try:
                import native_accel
                pre_generated_barcodes = native_accel.generate_batch_barcodes(vendor_name, quantity)
            except ImportError:
                pre_generated_barcodes = None
        last_barcode = ''
        with get_session() as s:
            for i in range(quantity):
                if pre_generated_barcodes and i < len(pre_generated_barcodes):
                    unique_barcode = pre_generated_barcodes[i]
                else:
                    unique_barcode = barcode_generator(vendor_name)
                s.execute(text("""
                    INSERT INTO products
                        (name, price, manufacturer_barcode, internal_unique_barcode,
                         status, expiry_date, manufacture_date, vendor_name)
                    VALUES (:name, :price, :mfg_barcode, :int_barcode,
                            'In Stock', :expiry, :mfg_date, :vendor)
                """), {
                    "name": product_name, "price": tpl_price,
                    "mfg_barcode": tpl_mfg_barcode, "int_barcode": unique_barcode,
                    "expiry": tpl_expiry, "mfg_date": tpl_mfg_date,
                    "vendor": vendor_name,
                })
                last_barcode = unique_barcode
            s.execute(text("""
                INSERT INTO receiving_log
                    (vendor_name, product_name, date_received, quantity, total_cost, barcode)
                VALUES (:vendor, :pname, :date, :qty, :cost, :barcode)
            """), {
                "vendor": vendor_name, "pname": product_name,
                "date": date_received, "qty": quantity,
                "cost": total_cost, "barcode": last_barcode,
            })
        return last_barcode

    def get_all_receiving_log(filter_date=None):
        with get_session() as s:
            if filter_date:
                result = s.execute(text("""
                    SELECT id, vendor_name, product_name, date_received, quantity, total_cost,
                           COALESCE(barcode, '') as barcode
                    FROM receiving_log
                    WHERE date_received = :dt
                    ORDER BY date_received DESC
                """), {"dt": filter_date})
            else:
                result = s.execute(text("""
                    SELECT id, vendor_name, product_name, date_received, quantity, total_cost,
                           COALESCE(barcode, '') as barcode
                    FROM receiving_log
                    ORDER BY date_received DESC
                """))
            return [tuple(r) for r in result.fetchall()]

    def get_vendor_total_owed(vendor_name: str):
        with get_session() as s:
            result = s.execute(text("""
                SELECT COALESCE(SUM(total_cost), 0.0) FROM receiving_log
                WHERE vendor_name = :vendor
            """), {"vendor": vendor_name})
            return result.scalar()

    def get_all_vendors():
        with get_session() as s:
            result = s.execute(text("""
                SELECT DISTINCT vendor_name FROM receiving_log ORDER BY vendor_name ASC
            """))
            return [r[0] for r in result.fetchall()]

    def create_receipt(payment_method: str, items: list[dict], patient_id: int = None):
        """Create a receipt with line items. Atomically inserts receipt +
        receipt_items, deducts stock from products."""
        with get_session() as s:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            total_amount = sum(item["quantity"] * item["price_at_time"] for item in items)
            result = s.execute(text("""
                INSERT INTO receipts (timestamp, total_amount, payment_method, patient_id)
                VALUES (:ts, :total, :method, :pid)
            """), {
                "ts": ts, "total": total_amount,
                "method": payment_method, "pid": patient_id,
            })
            receipt_id = result.lastrowid
            for item in items:
                s.execute(text("""
                    INSERT INTO receipt_items
                        (receipt_id, product_name, quantity, price_at_time,
                         internal_barcode, vendor, expiry_date)
                    VALUES (:rid, :pn, :qty, :pt, :bc, :ven, :exp)
                """), {
                    "rid": receipt_id, "pn": item["product_name"],
                    "qty": item["quantity"], "pt": item["price_at_time"],
                    "bc": item.get("internal_barcode", ""),
                    "ven": item.get("vendor", ""),
                    "exp": item.get("expiry_date", ""),
                })
            for item in items:
                barcode = item.get("internal_barcode", "")
                if barcode:
                    row = s.execute(text("""
                        SELECT id FROM products
                        WHERE internal_unique_barcode = :bc AND status = 'In Stock'
                    """), {"bc": barcode}).fetchone()
                    if not row:
                        raise ValueError(
                            f"Batch '{barcode}' for '{item['product_name']}' not found in stock."
                        )
                    if item["quantity"] != 1:
                        raise ValueError(
                            f"Serialized model allows qty=1 per batch. "
                            f"Got qty={item['quantity']} for '{item['product_name']}'."
                        )
                    s.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": row[0]})
                else:
                    rows = s.execute(text("""
                        SELECT id FROM products
                        WHERE name = :pn AND status = 'In Stock'
                        ORDER BY id ASC
                        LIMIT :qty
                    """), {"pn": item["product_name"], "qty": item["quantity"]}).fetchall()
                    if len(rows) < item["quantity"]:
                        raise ValueError(
                            f"Insufficient stock for '{item['product_name']}': "
                            f"need {item['quantity']}, have {len(rows)}"
                        )
                    for row in rows:
                        s.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": row[0]})
            return receipt_id

    def checkout_cart_atomically(payment_method: str, cart_entries: list,
                                 patient_id: int = None, tax_rate: float = 0.0,
                                 sale_type: str = "OTC", insurance_copay: float = 0.0,
                                 insurance_amount: float = 0.0) -> int:
        """Process an entire POS cart within a single SQLAlchemy session transaction.

        Mirrors database.py:checkout_cart_atomically — migrates each staged
        ``internal_unique_barcode`` from ``products`` to ``sold_items``,
        creates ``receipts`` + ``receipt_items``, commits atomically.
        """
        with get_session() as s:
            subtotal = sum(
                entry["quantity"] * entry["price_at_time"]
                for entry in cart_entries
            )
            tax_amount = subtotal * (tax_rate / 100.0) if tax_rate else 0.0
            total_amount = subtotal + tax_amount

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result = s.execute(text("""
                INSERT INTO receipts (timestamp, total_amount, payment_method, patient_id,
                                      sale_type, insurance_copay, insurance_amount)
                VALUES (:ts, :total, :method, :pid, :st, :ic, :ia)
            """), {
                "ts": ts, "total": total_amount,
                "method": payment_method, "pid": patient_id,
                "st": sale_type, "ic": insurance_copay, "ia": insurance_amount,
            })
            receipt_id = result.lastrowid

            for entry in cart_entries:
                barcodes = entry.get("internal_barcodes", [])
                s.execute(text("""
                    INSERT INTO receipt_items
                        (receipt_id, product_name, quantity, price_at_time,
                         internal_barcode, vendor, expiry_date)
                    VALUES (:rid, :pn, :qty, :pt, :bc, :ven, :exp)
                """), {
                    "rid": receipt_id, "pn": entry["product_name"],
                    "qty": entry["quantity"], "pt": entry["price_at_time"],
                    "bc": ", ".join(barcodes), "ven": entry.get("vendor", "N/A"),
                    "exp": entry.get("expiry_date", ""),
                })

                for barcode in barcodes:
                    row = s.execute(text("""
                        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                               vendor_name
                        FROM products
                        WHERE internal_unique_barcode = :bc AND status = 'In Stock'
                    """), {"bc": barcode}).fetchone()
                    if not row:
                        raise ValueError(
                            f"Batch '{barcode}' for '{entry['product_name']}' "
                            f"not found in stock or already sold."
                        )
                    product_id, name, price, mfg_barcode, int_barcode, vendor_name = row
                    s.execute(text("""
                        INSERT INTO sold_items
                            (item_name, price, manufacturer_barcode, internal_barcode,
                             timestamp_of_sale, vendor_name)
                        VALUES (:name, :price, :mfg_bc, :int_bc, :ts, :vendor)
                    """), {
                        "name": name, "price": price, "mfg_bc": mfg_barcode,
                        "int_bc": int_barcode, "ts": ts,
                        "vendor": vendor_name or 'N/A',
                    })
                    s.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": product_id})

            return receipt_id

    def get_receipts():
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, timestamp, total_amount, payment_method, sale_type
                FROM receipts ORDER BY id DESC
            """))
            return [tuple(r) for r in result.fetchall()]

    def get_receipt_items(receipt_id: int):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, receipt_id, product_name, quantity, price_at_time,
                       COALESCE(internal_barcode, '') as internal_barcode,
                       COALESCE(vendor, '') as vendor,
                       COALESCE(expiry_date, '') as expiry_date
                FROM receipt_items WHERE receipt_id = :rid
            """), {"rid": receipt_id})
            return [tuple(r) for r in result.fetchall()]

    def get_all_receipt_items_flat():
        with get_session() as s:
            result = s.execute(text("""
                SELECT ri.id, ri.receipt_id, ri.product_name, ri.quantity, ri.price_at_time,
                       (ri.quantity * ri.price_at_time) as line_total,
                       r.timestamp, r.payment_method,
                       COALESCE(ri.internal_barcode, '') as internal_barcode,
                       COALESCE(ri.vendor, '') as vendor,
                       COALESCE(ri.expiry_date, '') as expiry_date
                FROM receipt_items ri
                JOIN receipts r ON ri.receipt_id = r.id
                ORDER BY r.timestamp DESC
            """))
            return [tuple(r) for r in result.fetchall()]

    def get_receipt_items_for_date(date_str: str):
        with get_session() as s:
            result = s.execute(text("""
                SELECT ri.id, ri.receipt_id, ri.product_name, ri.quantity, ri.price_at_time,
                       (ri.quantity * ri.price_at_time) as line_total,
                       r.timestamp, r.payment_method,
                       COALESCE(ri.internal_barcode, '') as internal_barcode,
                       COALESCE(ri.vendor, '') as vendor,
                       COALESCE(ri.expiry_date, '') as expiry_date
                FROM receipt_items ri
                JOIN receipts r ON ri.receipt_id = r.id
                WHERE r.timestamp LIKE :ds
                ORDER BY r.timestamp DESC
            """), {"ds": f"{date_str}%"})
            return [tuple(r) for r in result.fetchall()]

    def get_receipt_items_grouped_by_date():
        flat = get_all_receipt_items_flat()
        grouped = defaultdict(list)
        for r in flat:
            date_part = r[6][:10] if r[6] and len(r[6]) >= 10 else "Unknown"
            grouped[date_part].append(r)
        return grouped

    def get_receipts_total_for_date(date_str: str):
        with get_session() as s:
            result = s.execute(text("""
                SELECT COALESCE(SUM(total_amount), 0.0) FROM receipts
                WHERE timestamp LIKE :ds
            """), {"ds": f"{date_str}%"})
            return result.scalar()

    def reverse_receipt_item(receipt_item_id: int):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, receipt_id, product_name, quantity, price_at_time,
                       COALESCE(internal_barcode, '') as internal_barcode,
                       COALESCE(vendor, '') as vendor,
                       COALESCE(expiry_date, '') as expiry_date
                FROM receipt_items WHERE id = :rid
            """), {"rid": receipt_item_id})
            item = result.fetchone()
            if not item:
                raise ValueError("Receipt item not found.")

            (_id, receipt_id, product_name, quantity, price_at_time,
             stored_barcode, stored_vendor, stored_expiry) = item

            import barcode_logic as _bl
            for _ in range(quantity):
                if stored_barcode:
                    unique_barcode = stored_barcode
                else:
                    unique_barcode = _bl.generate_internal_barcode(stored_vendor or "N/A")
                s.execute(text("""
                    INSERT INTO products
                        (name, price, manufacturer_barcode, internal_unique_barcode,
                         status, expiry_date, manufacture_date, vendor_name)
                    VALUES (:name, :price, '', :bc, 'In Stock', :exp, '', :vendor)
                """), {
                    "name": product_name, "price": price_at_time,
                    "bc": unique_barcode, "exp": stored_expiry,
                    "vendor": stored_vendor or 'N/A',
                })

            s.execute(text("DELETE FROM receipt_items WHERE id = :rid"), {"rid": receipt_item_id})

            line_total = quantity * price_at_time
            s.execute(text("""
                UPDATE receipts SET total_amount = total_amount - :lt
                WHERE id = :rid
            """), {"lt": line_total, "rid": receipt_id})

            remaining = s.execute(text("""
                SELECT COUNT(*) FROM receipt_items WHERE receipt_id = :rid
            """), {"rid": receipt_id}).scalar()
            if remaining == 0:
                s.execute(text("DELETE FROM receipts WHERE id = :rid"), {"rid": receipt_id})

    def backup_database(dest_folder: str):
        db_path = get_db_path()
        if not os.path.exists(db_path):
            raise FileNotFoundError("Database file does not exist yet. Please add a product first.")
        date_str = datetime.now().strftime("%Y%m%d")
        filename = os.path.basename(db_path)
        if not filename:
            filename = "pharmacy.db"
        name, ext = os.path.splitext(filename)
        backup_filename = f"{name}_{date_str}{ext}"
        backup_path = os.path.join(dest_folder, backup_filename)
        shutil.copy2(db_path, backup_path)
        return backup_path

    def get_dashboard_metrics():
        """Returns a dict with all dashboard KPI metrics."""
        with get_session() as s:
            total_in_stock = s.execute(text(
                "SELECT COUNT(*) FROM products WHERE status = 'In Stock'")).scalar()
            total_inventory_value = s.execute(text(
                "SELECT COALESCE(SUM(price), 0.0) FROM products WHERE status = 'In Stock'")).scalar()
            total_sold = s.execute(text(
                "SELECT COUNT(*) FROM sold_items")).scalar()
            total_revenue = s.execute(text(
                "SELECT COALESCE(SUM(price), 0.0) FROM sold_items")).scalar()
            total_products = s.execute(text(
                "SELECT COUNT(DISTINCT name) FROM products WHERE status = 'In Stock'")).scalar()
            total_vendors = s.execute(text(
                "SELECT COUNT(DISTINCT vendor_name) FROM products "
                "WHERE status = 'In Stock' AND vendor_name != 'N/A'")).scalar()

            today = datetime.now().strftime("%Y-%m-%d")
            todays_sales = s.execute(text(
                "SELECT COALESCE(SUM(price), 0.0) FROM sold_items "
                "WHERE timestamp_of_sale LIKE :today"
            ), {"today": f"{today}%"}).scalar()

        expiring = get_expiring_batches()
        today_date = date.today()
        c30 = c60 = c90 = 0
        for exp_date, _row in expiring:
            delta = (exp_date - today_date).days
            if delta <= 30:
                c30 += 1
            elif delta <= 60:
                c60 += 1
            elif delta <= 90:
                c90 += 1

        low_stock = get_low_stock_products()

        return {
            "total_in_stock": total_in_stock,
            "total_inventory_value": total_inventory_value,
            "total_sold": total_sold,
            "total_revenue": total_revenue,
            "total_products": total_products,
            "total_vendors": total_vendors,
            "todays_sales": todays_sales,
            "expiring_30": c30,
            "expiring_60": c60,
            "expiring_90": c90,
            "low_stock": low_stock,
            "low_stock_count": len(low_stock),
        }

    def get_low_stock_products(threshold=5):
        with get_session() as s:
            result = s.execute(text("""
                SELECT name, COUNT(*) as qty, MIN(expiry_date) as min_expiry
                FROM products
                WHERE status = 'In Stock'
                GROUP BY name
                HAVING COUNT(*) <= :threshold
                ORDER BY qty ASC, name ASC
            """), {"threshold": threshold})
            return [tuple(r) for r in result.fetchall()]

    def get_top_selling_products(start_date, end_date, limit=10):
        with get_session() as s:
            result = s.execute(text("""
                SELECT ri.product_name, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
                FROM receipt_items ri
                JOIN receipts r ON ri.receipt_id = r.id
                WHERE date(r.timestamp) BETWEEN :start AND :end
                GROUP BY ri.product_name
                ORDER BY SUM(ri.quantity) DESC
                LIMIT :limit
            """), {"start": start_date, "end": end_date, "limit": limit})
            return [tuple(r) for r in result.fetchall()]

    def get_sales_analytics(start_date: str, end_date: str) -> dict:
        with get_session() as s:
            result = s.execute(text("""
                SELECT ri.product_name,
                       SUM(ri.quantity) as total_qty,
                       SUM(ri.quantity * ri.price_at_time) as total_revenue,
                       ROUND(SUM(ri.quantity * ri.price_at_time) / SUM(ri.quantity), 2) as avg_price
                FROM receipt_items ri
                JOIN receipts r ON ri.receipt_id = r.id
                WHERE date(r.timestamp) BETWEEN :start AND :end
                GROUP BY ri.product_name
                ORDER BY total_qty DESC
            """), {"start": start_date, "end": end_date})
            raw_products = [tuple(r) for r in result.fetchall()]

            ranked_products = []
            for rank, (name, qty, revenue, avg_price) in enumerate(raw_products, 1):
                ranked_products.append((rank, name, qty, revenue, avg_price))

            totals = s.execute(text("""
                SELECT COALESCE(SUM(ri.quantity), 0),
                       COALESCE(SUM(ri.quantity * ri.price_at_time), 0),
                       COUNT(DISTINCT ri.product_name),
                       COUNT(DISTINCT r.id)
                FROM receipt_items ri
                JOIN receipts r ON ri.receipt_id = r.id
                WHERE date(r.timestamp) BETWEEN :start AND :end
            """), {"start": start_date, "end": end_date}).fetchone()

            total_items, total_rev, unique_prods, total_txns = totals
            avg_basket = (total_items / total_txns) if total_txns > 0 else 0.0

        return {
            "ranked_products": ranked_products,
            "total_items_sold": total_items,
            "total_revenue": total_rev,
            "unique_products": unique_prods,
            "total_transactions": total_txns,
            "avg_basket_size": round(avg_basket, 1),
        }

    def get_sales_by_period(period='month'):
        with get_session() as s:
            if period == 'day':
                sql = text("""
                    SELECT date(r.timestamp) as period, SUM(ri.quantity),
                           SUM(ri.quantity * ri.price_at_time)
                    FROM receipt_items ri
                    JOIN receipts r ON ri.receipt_id = r.id
                    GROUP BY date(r.timestamp)
                    ORDER BY period DESC
                """)
            elif period == 'week':
                sql = text("""
                    SELECT strftime('%Y-W%W', r.timestamp) as period, SUM(ri.quantity),
                           SUM(ri.quantity * ri.price_at_time)
                    FROM receipt_items ri
                    JOIN receipts r ON ri.receipt_id = r.id
                    GROUP BY strftime('%Y-W%W', r.timestamp)
                    ORDER BY period DESC
                """)
            elif period == 'year':
                sql = text("""
                    SELECT strftime('%Y', r.timestamp) as period, SUM(ri.quantity),
                           SUM(ri.quantity * ri.price_at_time)
                    FROM receipt_items ri
                    JOIN receipts r ON ri.receipt_id = r.id
                    GROUP BY strftime('%Y', r.timestamp)
                    ORDER BY period DESC
                """)
            else:  # month
                sql = text("""
                    SELECT strftime('%Y-%m', r.timestamp) as period, SUM(ri.quantity),
                           SUM(ri.quantity * ri.price_at_time)
                    FROM receipt_items ri
                    JOIN receipts r ON ri.receipt_id = r.id
                    GROUP BY strftime('%Y-%m', r.timestamp)
                    ORDER BY period DESC
                """)
            result = s.execute(sql)
            return [tuple(r) for r in result.fetchall()]

    def add_patient(name: str, phone: str = '', email: str = '', custom_fields: dict = None):
        with get_session() as s:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result = s.execute(text("""
                INSERT INTO patients (name, phone, email, created_at)
                VALUES (:name, :phone, :email, :created_at)
            """), {"name": name, "phone": phone, "email": email, "created_at": created_at})
            patient_id = result.lastrowid
            if custom_fields:
                for field_name, field_value in custom_fields.items():
                    if field_name and field_name.strip():
                        s.execute(text("""
                            INSERT INTO patient_fields (patient_id, field_name, field_value)
                            VALUES (:pid, :fname, :fval)
                        """), {
                            "pid": patient_id, "fname": field_name.strip(),
                            "fval": field_value,
                        })
            return patient_id

    def get_all_patients(search_query: str = None):
        with get_session() as s:
            if search_query:
                like = f"%{search_query}%"
                result = s.execute(text("""
                    SELECT id, name, phone, email, created_at
                    FROM patients
                    WHERE name LIKE :q OR phone LIKE :q OR email LIKE :q
                    ORDER BY name ASC
                """), {"q": like})
            else:
                result = s.execute(text("""
                    SELECT id, name, phone, email, created_at
                    FROM patients ORDER BY name ASC
                """))
            patients = result.fetchall()
            out = []
            for row in patients:
                pid = row[0]
                fields_result = s.execute(text("""
                    SELECT field_name, field_value FROM patient_fields
                    WHERE patient_id = :pid
                """), {"pid": pid})
                fields = {r[0]: r[1] for r in fields_result.fetchall()}
                out.append((pid, row[1], row[2], row[3], row[4], fields))
            return out

    def get_patient_by_id(patient_id: int):
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, phone, email, created_at FROM patients WHERE id = :pid
            """), {"pid": patient_id})
            row = result.fetchone()
            if not row:
                return None
            pid = row[0]
            fields_result = s.execute(text("""
                SELECT field_name, field_value FROM patient_fields WHERE patient_id = :pid
            """), {"pid": pid})
            fields = {r[0]: r[1] for r in fields_result.fetchall()}
            return (pid, row[1], row[2], row[3], row[4], fields)

    def update_patient(patient_id: int, name: str, phone: str = '', email: str = '',
                       custom_fields: dict = None):
        with get_session() as s:
            s.execute(text("""
                UPDATE patients SET name = :name, phone = :phone, email = :email
                WHERE id = :pid
            """), {"name": name, "phone": phone, "email": email, "pid": patient_id})
            s.execute(text("DELETE FROM patient_fields WHERE patient_id = :pid"), {"pid": patient_id})
            if custom_fields:
                for field_name, field_value in custom_fields.items():
                    if field_name and field_name.strip():
                        s.execute(text("""
                            INSERT INTO patient_fields (patient_id, field_name, field_value)
                            VALUES (:pid, :fname, :fval)
                        """), {
                            "pid": patient_id, "fname": field_name.strip(),
                            "fval": field_value,
                        })

    def delete_patient(patient_id: int):
        with get_session() as s:
            s.execute(text("DELETE FROM patient_fields WHERE patient_id = :pid"), {"pid": patient_id})
            s.execute(text("DELETE FROM patients WHERE id = :pid"), {"pid": patient_id})

    def get_distinct_patient_field_names():
        with get_session() as s:
            result = s.execute(text("""
                SELECT DISTINCT field_name FROM patient_fields ORDER BY field_name ASC
            """))
            return [r[0] for r in result.fetchall()]

    # ── Suppliers ─────────────────────────────────────────────────────────

    def get_suppliers() -> list[tuple]:
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, contact_name, contact_email, contact_phone, address,
                       preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
                       edi_api_key, performance_notes, created_at, updated_at
                FROM suppliers
                ORDER BY preferred DESC, name ASC
            """))
            return [tuple(r) for r in result.fetchall()]

    def get_supplier_by_id(supplier_id: int) -> tuple | None:
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, name, contact_name, contact_email, contact_phone, address,
                       preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
                       edi_api_key, performance_notes, created_at, updated_at
                FROM suppliers WHERE id = :sid
            """), {"sid": supplier_id})
            row = result.fetchone()
            return tuple(row) if row else None

    def add_supplier(name: str, contact_name: str = "", contact_email: str = "",
                     contact_phone: str = "", address: str = "", preferred: int = 0,
                     sku: str = "", min_stock_level: int = 0, lead_time_days: int = 0,
                     edi_endpoint: str = "", edi_api_key: str = "",
                      performance_notes: str = "") -> int:
        import audit_log
        from sqlalchemy.exc import IntegrityError as _SAIE
        with get_session() as s:
            try:
                result = s.execute(text("""
                    INSERT INTO suppliers
                        (name, contact_name, contact_email, contact_phone, address,
                         preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
                         edi_api_key, performance_notes)
                    VALUES (:name, :cn, :ce, :cp, :addr, :pref, :sku, :msl, :lt, :ep, :ek, :pn)
                """), {
                    "name": name, "cn": contact_name, "ce": contact_email,
                    "cp": contact_phone, "addr": address, "pref": preferred,
                    "sku": sku, "msl": min_stock_level, "lt": lead_time_days,
                    "ep": edi_endpoint, "ek": edi_api_key, "pn": performance_notes,
                })
                supplier_id = result.lastrowid
            except (sqlite3.IntegrityError, _SAIE):
                raise ValueError(f"Supplier '{name}' already exists")
        audit_log.log_action("SUPPLIER_CREATE",
                             f"Supplier '{name}' (id={supplier_id}) created.")
        return supplier_id

    def update_supplier(supplier_id: int, name: str, contact_name: str = "",
                        contact_email: str = "", contact_phone: str = "",
                        address: str = "", preferred: int = 0, sku: str = "",
                        min_stock_level: int = 0, lead_time_days: int = 0,
                        edi_endpoint: str = "", edi_api_key: str = "",
                        performance_notes: str = "") -> bool:
        import audit_log
        from sqlalchemy.exc import IntegrityError as _SAIE
        with get_session() as s:
            try:
                s.execute(text("""
                    UPDATE suppliers SET
                        name = :name, contact_name = :cn, contact_email = :ce,
                        contact_phone = :cp, address = :addr, preferred = :pref,
                        sku = :sku, min_stock_level = :msl, lead_time_days = :lt,
                        edi_endpoint = :ep, edi_api_key = :ek,
                        performance_notes = :pn, updated_at = datetime('now')
                    WHERE id = :sid
                """), {
                    "name": name, "cn": contact_name, "ce": contact_email,
                    "cp": contact_phone, "addr": address, "pref": preferred,
                    "sku": sku, "msl": min_stock_level, "lt": lead_time_days,
                    "ep": edi_endpoint, "ek": edi_api_key, "pn": performance_notes,
                    "sid": supplier_id,
                })
            except (sqlite3.IntegrityError, _SAIE):
                raise ValueError(f"Supplier '{name}' already exists")
        audit_log.log_action("SUPPLIER_UPDATE",
                             f"Supplier id={supplier_id} ('{name}') updated.")
        return True

    def delete_supplier(supplier_id: int) -> bool:
        import audit_log
        with get_session() as s:
            row = s.execute(text(
                "SELECT preferred, name FROM suppliers WHERE id = :sid"
            ), {"sid": supplier_id}).fetchone()
            if not row:
                return False
            if row[0]:
                raise ValueError(f"Preferred supplier '{row[1]}' cannot be deleted; demote first")
            s.execute(text("DELETE FROM suppliers WHERE id = :sid"), {"sid": supplier_id})
        audit_log.log_action("SUPPLIER_DELETE", f"Supplier id={supplier_id} ('{row[1]}') deleted.")
        return True

    # ── Purchase Orders ───────────────────────────────────────────────────

    _LEGAL_PO_TRANSITIONS = {
        "Draft": {"Submitted"},
        "Submitted": {"Draft"},
        "Received": {"Closed"},
    }

    def get_purchase_orders(status_filter: str | None = None) -> list[tuple]:
        with get_session() as s:
            if status_filter:
                result = s.execute(text("""
                    SELECT id, po_number, vendor_id, vendor_name, status, created_at,
                           submitted_at, received_at, closed_at, subtotal, tax_amount,
                           total_cost, notes
                    FROM purchase_orders
                    WHERE status = :st
                    ORDER BY created_at DESC
                """), {"st": status_filter})
            else:
                result = s.execute(text("""
                    SELECT id, po_number, vendor_id, vendor_name, status, created_at,
                           submitted_at, received_at, closed_at, subtotal, tax_amount,
                           total_cost, notes
                    FROM purchase_orders
                    ORDER BY created_at DESC
                """))
            return [tuple(r) for r in result.fetchall()]

    def get_po_by_id(po_id: int) -> tuple | None:
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, po_number, vendor_id, vendor_name, status, created_at,
                       submitted_at, received_at, closed_at, subtotal, tax_amount,
                       total_cost, notes
                FROM purchase_orders WHERE id = :pid
            """), {"pid": po_id})
            row = result.fetchone()
            return tuple(row) if row else None

    def get_po_items(po_id: int) -> list[tuple]:
        with get_session() as s:
            result = s.execute(text("""
                SELECT id, line_number, product_name, vendor_sku, quantity, unit_price,
                       line_total, status, internal_barcodes, mfg_barcode, expiry_date,
                       mfg_date
                FROM po_items
                WHERE po_id = :pid
                ORDER BY line_number ASC
            """), {"pid": po_id})
            return [tuple(r) for r in result.fetchall()]

    def get_next_po_number() -> str:
        year = datetime.now().strftime("%Y")
        with get_session() as s:
            result = s.execute(text("""
                SELECT po_number FROM purchase_orders
                WHERE po_number LIKE :pat ORDER BY po_number DESC LIMIT 1
            """), {"pat": f"PO-{year}-%"})
            row = result.fetchone()
        if row and row[0]:
            try:
                next_seq = int(row[0].rsplit("-", 1)[-1]) + 1
            except ValueError:
                next_seq = 1
        else:
            next_seq = 1
        return f"PO-{year}-{next_seq:04d}"

    def add_purchase_order(vendor_id: int, vendor_name: str,
                           items: list[dict], notes: str = "") -> tuple[int, str]:
        import audit_log
        po_number = get_next_po_number()
        total_cost = 0.0
        with get_session() as s:
            result = s.execute(text("""
                INSERT INTO purchase_orders
                    (po_number, vendor_id, vendor_name, status, notes)
                VALUES (:num, :vid, :vn, 'Draft', :notes)
            """), {"num": po_number, "vid": vendor_id, "vn": vendor_name, "notes": notes})
            po_id = result.lastrowid
            for idx, item in enumerate(items, start=1):
                qty = int(item.get("quantity", 0))
                unit_price = float(item.get("unit_price", 0.0))
                line_total = qty * unit_price
                total_cost += line_total
                s.execute(text("""
                    INSERT INTO po_items
                        (po_id, line_number, product_name, vendor_sku, quantity,
                         unit_price, line_total, mfg_barcode, expiry_date, mfg_date)
                    VALUES (:pid, :ln, :pn, :sku, :qty, :up, :lt, :mbc, :exp, :mfg)
                """), {
                    "pid": po_id, "ln": idx, "pn": item["product_name"],
                    "sku": item.get("vendor_sku", ""), "qty": qty, "up": unit_price,
                    "lt": line_total, "mbc": item.get("mfg_barcode", ""),
                    "exp": item.get("expiry_date", ""), "mfg": item.get("mfg_date", ""),
                })
            s.execute(text("""
                UPDATE purchase_orders SET subtotal = :sub, total_cost = :tot
                WHERE id = :pid
            """), {"sub": total_cost, "tot": total_cost, "pid": po_id})
        audit_log.log_action("PO_CREATE", f"PO #{po_number} (id={po_id}) created for vendor "
                            f"'{vendor_name}', {len(items)} item(s), total=${total_cost:.2f}.")
        return po_id, po_number

    def update_po_status(po_id: int, status: str) -> bool:
        import audit_log
        legal = _LEGAL_PO_TRANSITIONS
        with get_session() as s:
            row = s.execute(text("SELECT status FROM purchase_orders WHERE id = :pid"),
                            {"pid": po_id}).fetchone()
            if not row:
                raise ValueError(f"Purchase order {po_id} not found")
            current = row[0]
            if status == current:
                return True
            if status not in legal.get(current, set()):
                raise ValueError(f"Illegal PO transition: {current} → {status}")
            ts_col = {"Submitted": "submitted_at", "Draft": "created_at",
                      "Closed": "closed_at"}.get(status)
            params = {"sid": status, "pid": po_id}
            if ts_col:
                s.execute(text(
                    f"UPDATE purchase_orders SET status = :sid, {ts_col} = datetime('now') "
                    "WHERE id = :pid"
                ), params)
            else:
                s.execute(text("UPDATE purchase_orders SET status = :sid WHERE id = :pid"), params)
        audit_log.log_action("PO_STATUS", f"PO id={po_id} status changed: {current} → {status}.")
        return True

    def add_po_item(po_id: int, product_name: str, quantity: int, unit_price: float,
                    vendor_sku: str = "", mfg_barcode: str = "",
                    expiry_date: str = "", mfg_date: str = "") -> int:
        line_total = quantity * unit_price
        with get_session() as s:
            max_line = s.execute(text(
                "SELECT COALESCE(MAX(line_number), 0) FROM po_items WHERE po_id = :pid"
            ), {"pid": po_id}).fetchone()[0]
            result = s.execute(text("""
                INSERT INTO po_items
                    (po_id, line_number, product_name, vendor_sku, quantity, unit_price,
                     line_total, mfg_barcode, expiry_date, mfg_date)
                VALUES (:pid, :ln, :pn, :sku, :qty, :up, :lt, :mbc, :exp, :mfg)
            """), {
                "pid": po_id, "ln": max_line + 1, "pn": product_name, "sku": vendor_sku,
                "qty": quantity, "up": unit_price, "lt": line_total, "mbc": mfg_barcode,
                "exp": expiry_date, "mfg": mfg_date,
            })
            item_id = result.lastrowid
        update_po_totals(po_id)
        return item_id

    def update_po_item(item_id: int, quantity: int, unit_price: float,
                       product_name: str | None = None, mfg_barcode: str | None = None,
                       expiry_date: str | None = None, mfg_date: str | None = None,
                       vendor_sku: str | None = None) -> bool:
        line_total = quantity * unit_price
        sets = ["quantity = :qty", "unit_price = :up", "line_total = :lt"]
        params = {"qty": quantity, "up": unit_price, "lt": line_total, "iid": item_id}
        if product_name is not None:
            sets.append("product_name = :pn"); params["pn"] = product_name
        if vendor_sku is not None:
            sets.append("vendor_sku = :sku"); params["sku"] = vendor_sku
        if mfg_barcode is not None:
            sets.append("mfg_barcode = :mbc"); params["mbc"] = mfg_barcode
        if expiry_date is not None:
            sets.append("expiry_date = :exp"); params["exp"] = expiry_date
        if mfg_date is not None:
            sets.append("mfg_date = :mfg"); params["mfg"] = mfg_date
        with get_session() as s:
            s.execute(text(f"UPDATE po_items SET {', '.join(sets)} WHERE id = :iid"), params)
            row = s.execute(text("SELECT po_id FROM po_items WHERE id = :iid"),
                            {"iid": item_id}).fetchone()
        if row:
            update_po_totals(row[0])
        return True

    def delete_po_item(item_id: int) -> bool:
        with get_session() as s:
            row = s.execute(text("SELECT po_id, line_number FROM po_items WHERE id = :iid"),
                            {"iid": item_id}).fetchone()
            if not row:
                return False
            po_id, line_num = row[0], row[1]
            s.execute(text("DELETE FROM po_items WHERE id = :iid"), {"iid": item_id})
            s.execute(text("""
                UPDATE po_items SET line_number = line_number - 1
                WHERE po_id = :pid AND line_number > :ln
            """), {"pid": po_id, "ln": line_num})
        update_po_totals(po_id)
        return True

    def update_po_totals(po_id: int) -> None:
        import audit_log
        with get_session() as s:
            s.execute(text("""
                UPDATE purchase_orders
                SET subtotal = COALESCE((SELECT SUM(line_total) FROM po_items WHERE po_id = :pid), 0),
                    tax_amount = 0.0,
                    total_cost = COALESCE((SELECT SUM(line_total) FROM po_items WHERE po_id = :pid), 0)
                WHERE id = :pid
            """), {"pid": po_id})
        audit_log.log_action("PO_TOTALS", f"PO id={po_id} totals recomputed.")

    # ── Low-Stock / Auto-Reorder ─────────────────────────────────────────

    def get_products_below_reorder_threshold() -> list[tuple]:
        with get_session() as s:
            result = s.execute(text("""
                SELECT name, COUNT(*) AS qty, MIN(reorder_threshold) AS min_threshold,
                       vendor_name, MIN(wholesale_price) AS wholesale_price
                FROM products
                WHERE status = 'In Stock'
                GROUP BY name
                HAVING COUNT(*) <= MIN(reorder_threshold) AND MIN(reorder_threshold) > 0
                ORDER BY qty ASC, name ASC
            """))
            return [tuple(r) for r in result.fetchall()]

    # ── Purchase Order Receiving (inventory update on PO → Received) ───

    def receive_po_items(po_id: int, date_received: str | None = None) -> dict[str, Any]:
        import json, time as _time, audit_log, barcode_logic
        from native_accel import generate_batch_barcodes
        try:
            from sqlalchemy.exc import OperationalError as _SAOpErr
            _lock_errors = (sqlite3.OperationalError, _SAOpErr)
        except ImportError:
            _lock_errors = (sqlite3.OperationalError,)

        po = get_po_by_id(po_id)
        if po is None:
            raise ValueError(f"Purchase order {po_id} not found")
        po_number = po[1]
        vendor_name = po[3]
        items = get_po_items(po_id)
        if not items:
            raise ValueError(f"PO #{po_number} has no line items to receive")

        date_received = date_received or datetime.now().strftime("%Y-%m-%d")
        total_qty = sum(int(it[4]) for it in items)
        all_barcodes = generate_batch_barcodes(vendor_name, total_qty)

        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                offset = 0
                for item in items:
                    (item_id, _line, product_name, _sku, qty, unit_price,
                     line_total, _status, _barcodes, mfg_barcode,
                     expiry_date, mfg_date) = item
                    item_barcodes = all_barcodes[offset:offset + int(qty)]
                    offset += int(qty)
                    receive_inventory_atomically(
                        vendor_name=vendor_name,
                        product_name=product_name,
                        date_received=date_received,
                        quantity=int(qty),
                        total_cost=float(line_total),
                        tpl_price=float(unit_price),
                        tpl_mfg_barcode=mfg_barcode or "",
                        tpl_expiry=expiry_date or "",
                        tpl_mfg_date=mfg_date or "",
                        barcode_generator=barcode_logic.generate_internal_barcode,
                        pre_generated_barcodes=item_barcodes,
                    )
                # Mark PO + items Received
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                offset = 0
                with get_session() as s:
                    for item in items:
                        item_id = item[0]
                        qty = int(item[4])
                        item_barcodes = all_barcodes[offset:offset + qty]
                        offset += qty
                        s.execute(text(
                            "UPDATE po_items SET status = 'Received', received_at = :now, "
                            "internal_barcodes = :bc WHERE id = :iid"
                        ), {"now": now, "bc": json.dumps(item_barcodes), "iid": item_id})
                    s.execute(text(
                        "UPDATE purchase_orders SET status = 'Received', "
                        "received_at = datetime('now') WHERE id = :pid"
                    ), {"pid": po_id})
                audit_log.log_action("PO_RECEIVE", f"PO #{po_number} (id={po_id}) received: "
                                    f"{total_qty} box(es) for {len(items)} item(s).")
                return {"po_number": po_number, "vendor_name": vendor_name,
                        "box_count": total_qty, "items_received": len(items)}
            except ValueError:
                # stale / invalid data — fail fast, no retry
                raise
            except _lock_errors as exc:
                delay = 0.1 * (2 ** attempt)
                log.warning("receive_po_items attempt %d/%d failed (lock): %s",
                            attempt + 1, max_retries, exc)
                last_error = exc
                _time.sleep(delay)

        raise last_error if last_error else RuntimeError(f"Failed to receive PO #{po_id}")
