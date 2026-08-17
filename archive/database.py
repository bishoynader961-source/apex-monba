"""
database.py — Phase 2: Thin delegating wrappers around db.py ORM layer.

Each function tries db.py's SQLAlchemy implementation first.
On any failure (missing backend, query error), it falls back to
the original raw sqlite3 code to guarantee zero regression.

Original sqlite3 implementations are preserved below each wrapper
as the graceful-degradation fallback.
"""
import sqlite3
import os
import shutil
import logging
from datetime import datetime, date, timedelta
from collections import defaultdict
import barcode_logic
from path_utils import get_resource_path

import functools

import auth_crypto

log = logging.getLogger("database")

# ── db.py delegation ───────────────────────────────────────────────────
try:
    import db as _db
    _HAS_DB = getattr(_db, "HAS_SQLALCHEMY", False)
except ImportError:
    _db = None
    _HAS_DB = False


def _db_fallback(func):
    """Decorator: try db.py ORM first, fall back to the decorated sqlite3 function."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if _HAS_DB:
            try:
                return getattr(_db, func.__name__)(*args, **kwargs)
            except Exception as e:
                log.debug("db.%s failed, falling back to sqlite3: %s", func.__name__, e)
        return func(*args, **kwargs)
    return wrapper


def get_db_path():
    """Resolve the SQLite path with test/CI isolation and CWD-safe normalization.

    PHARMACY_DB_PATH (set by test_db_fixture.py / CI) overrides everything so
    suites never touch the production archive/pharmacy.db. A relative config
    db_path is anchored to the app root via get_resource_path() so the live
    database is not created relative to the current working directory.
    """
    env = os.environ.get("PHARMACY_DB_PATH")
    if env:
        return env
    config = barcode_logic.load_config()
    p = config.get("db_path", "pharmacy.db")
    return p if os.path.isabs(p) else get_resource_path(p)


def load_config():
    """Load the application config.json (used by localization/settings modules)."""
    return barcode_logic.load_config()


def set_kv(key: str, value) -> None:
    """Set a key/value in the system_settings table (idempotent, INSERT OR REPLACE)."""
    sval = value if isinstance(value, str) else str(value)
    try:
        conn = sqlite3.connect(get_db_path())
        conn.execute(
            "INSERT OR REPLACE INTO system_settings(key, value) VALUES (?, ?)",
            (key, sval),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("database.set_kv(%r) failed: %s", key, e)


def get_kv(key: str, default: str = "") -> str:
    """Read a key from the system_settings table; return default on any error."""
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        if row is None or row[0] is None:
            return default
        val = row[0]
        return val.decode("utf-8") if isinstance(val, bytes) else str(val)
    except Exception as e:
        log.debug("database.get_kv(%r) failed: %s", key, e)
        return default


@_db_fallback
def init_db():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            manufacturer_barcode TEXT NOT NULL,
            internal_unique_barcode TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'In Stock'
        )
    """)
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN status TEXT DEFAULT 'In Stock'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN manufacture_date TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN vendor_name TEXT DEFAULT 'N/A'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN manufacturer_barcode TEXT NOT NULL DEFAULT ''")
        conn.commit()
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM templates")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ("Aspirin 500mg", 5.99),
            ("Band-Aids (40ct)", 3.49),
            ("Ibuprofen 200mg", 6.50),
            ("Cough Syrup", 8.99)
        ]
        cursor.executemany("INSERT INTO templates (name, price) VALUES (?, ?)", defaults)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sold_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            price REAL NOT NULL,
            manufacturer_barcode TEXT NOT NULL,
            internal_barcode TEXT NOT NULL,
            timestamp_of_sale TEXT NOT NULL
        )
    """)

    try:
        cursor.execute("ALTER TABLE sold_items ADD COLUMN vendor_name TEXT DEFAULT 'N/A'")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receiving_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT NOT NULL,
            product_name TEXT NOT NULL,
            date_received TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_cost REAL NOT NULL
        )
    """)

    try:
        cursor.execute("ALTER TABLE receiving_log ADD COLUMN barcode TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'Cash',
            patient_id INTEGER DEFAULT NULL
        )
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receipt_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price_at_time REAL NOT NULL,
            internal_barcode TEXT DEFAULT '',
            vendor TEXT DEFAULT '',
            expiry_date TEXT DEFAULT '',
            FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    # ── Migration: ensure insurance columns exist on patients ─────────
    # These columns were added in a later version for Enterprise POS Retail
    # (InsurancePanel, _select_patient).  Add them idempotently if missing.
    cursor.execute("PRAGMA table_info(patients)")
    _pat_cols = {row[1] for row in cursor.fetchall()}
    for _col in ("insurance_provider", "policy_number", "group_number"):
        if _col not in _pat_cols:
            try:
                cursor.execute(f"ALTER TABLE patients ADD COLUMN {_col} TEXT")
            except sqlite3.OperationalError:
                pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quick_sig_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            drug_name TEXT DEFAULT '',
            dose TEXT DEFAULT '',
            route TEXT DEFAULT '',
            frequency TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            directions TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            field_value TEXT DEFAULT '',
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
    )
""")

    # ── Supplier & Purchase Order tables ──────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL UNIQUE,
            contact_name     TEXT DEFAULT '',
            contact_email    TEXT DEFAULT '',
            contact_phone    TEXT DEFAULT '',
            address          TEXT DEFAULT '',
            tax_id           TEXT DEFAULT '',
            preferred        INTEGER DEFAULT 0,
            sku              TEXT DEFAULT '',
            min_stock_level  INTEGER DEFAULT 0,
            lead_time_days   INTEGER DEFAULT 0,
            edi_endpoint     TEXT DEFAULT '',
            edi_api_key      TEXT DEFAULT '',
            performance_notes TEXT DEFAULT '',
            created_at       TEXT DEFAULT (datetime('now')),
            updated_at       TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_preferred ON suppliers(preferred)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number     TEXT NOT NULL UNIQUE,
            vendor_id     INTEGER NOT NULL,
            vendor_name   TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'Draft',
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            submitted_at  TEXT,
            received_at   TEXT,
            closed_at     TEXT,
            subtotal      REAL DEFAULT 0.0,
            tax_amount    REAL DEFAULT 0.0,
            total_cost    REAL DEFAULT 0.0,
            notes         TEXT DEFAULT ''
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_vendor ON purchase_orders(vendor_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_created ON purchase_orders(created_at)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS po_items (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id             INTEGER NOT NULL,
            line_number       INTEGER NOT NULL,
            product_name      TEXT NOT NULL,
            vendor_sku        TEXT DEFAULT '',
            quantity          INTEGER NOT NULL DEFAULT 1,
            unit_price        REAL NOT NULL DEFAULT 0.0,
            line_total        REAL NOT NULL DEFAULT 0.0,
            status            TEXT DEFAULT 'Pending',
            internal_barcodes TEXT DEFAULT '',
            received_at       TEXT,
            mfg_barcode       TEXT DEFAULT '',
            expiry_date       TEXT DEFAULT '',
            mfg_date          TEXT DEFAULT ''
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_items_po_id ON po_items(po_id)")

    # ── Backfill: register existing vendors as suppliers (idempotent) ──
    cursor.execute("SELECT name FROM suppliers")
    existing_suppliers = {row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT DISTINCT vendor_name FROM receiving_log WHERE vendor_name != '' AND vendor_name != 'N/A' ORDER BY vendor_name")
    for (vendor,) in cursor.fetchall():
        if vendor not in existing_suppliers:
            cursor.execute(
                "INSERT OR IGNORE INTO suppliers (name, preferred) VALUES (?, 0)",
                (vendor,),
            )
            existing_suppliers.add(vendor)

    # ── Migration: ensure tax_id column exists on suppliers (added after v1) ──
    cursor.execute("PRAGMA table_info(suppliers)")
    _sup_cols = {row[1] for row in cursor.fetchall()}
    if "tax_id" not in _sup_cols:
        try:
            cursor.execute("ALTER TABLE suppliers ADD COLUMN tax_id TEXT DEFAULT ''")
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
    expected = {'id', 'name', 'price', 'manufacturer_barcode', 'internal_unique_barcode',
               'status', 'expiry_date', 'manufacture_date', 'vendor_name',
               'dea_schedule', 'wholesale_price', 'reorder_threshold'}
    if not expected.issubset(cols):
        missing = expected - cols
        raise RuntimeError(f"Database schema integrity failure. Missing columns: {missing}")

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

    # Seed feature-level permission catalog
    _RBAC_FEATURES = [
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
        ("pos.price_override", "Override item price at POS"),
        ("pos.void", "Void a sale line or transaction"),
        ("users.manage", "Manage users"),
        ("roles.manage", "Manage roles & permissions"),
        ("settings.manage", "Manage settings"),
        ("settings.view", "View application settings"),
        ("backup.manage", "Create and restore database backups"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO permissions (feature_key, description) VALUES (?, ?)",
        _RBAC_FEATURES,
    )

    # Seed foundational roles and their permission mappings
    _RBAC_ROLES = {
        "owner": {k for k, _ in _RBAC_FEATURES},
        "manager": {
            "sales.view", "sales.modify_report", "audit.view", "audit.export",
            "inventory.view", "inventory.manage", "inventory.receive",
            "reports.view", "pos.sell", "pos.refund", "settings.manage",
            "settings.view", "backup.manage",
            "pos.price_override", "pos.void",
        },
        "pharmacist": {
            "sales.view", "inventory.view", "inventory.receive",
            "pos.sell", "pos.refund", "reports.view",
            "settings.view",
            "pos.price_override", "pos.void",
        },
        "cashier": {"sales.view", "inventory.view", "pos.sell", "settings.view", "reports.view", "pos.price_override", "pos.void"},
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

    # Owner override bootstrap secret (MUST be changed on first run via Admin UI)
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
    conn.close()


# ── RBAC (roles / users / permissions) ──

@_db_fallback
def get_roles():
    """Return all roles as (id, name, description, is_system)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, is_system FROM roles ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_permissions():
    """Return all feature permissions as (id, feature_key, description)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, feature_key, description FROM permissions ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_role_permissions(role_id: int) -> set:
    """Return the set of granted feature keys for a role."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.feature_key
        FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
        WHERE rp.role_id = ? AND rp.granted = 1
    """, (role_id,))
    rows = {r[0] for r in cursor.fetchall()}
    conn.close()
    return rows


@_db_fallback
def get_user_role_id(user_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT role_id FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


@_db_fallback
def get_role_name(role_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM roles WHERE id = ?", (role_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


@_db_fallback
def get_user_display(user_id: int) -> str:
    """Return the user's display name (or username) for UI identity labels."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT display_name, username FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return ""
    display, username = row[0], row[1]
    return (display or "").strip() or (username or "").strip() or ""


@_db_fallback
def get_user_permissions(user_id: int) -> set:
    """Return the set of granted feature keys for a user.

    The ``owner`` role implicitly receives every defined permission.
    """
    role_id = get_user_role_id(user_id)
    if role_id is None:
        return set()
    if get_role_name(role_id) == "owner":
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT feature_key FROM permissions")
        keys = {r[0] for r in cursor.fetchall()}
        conn.close()
        return keys
    return get_role_permissions(role_id)


@_db_fallback
def count_users() -> int:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    n = cursor.fetchone()[0]
    conn.close()
    return n


@_db_fallback
def create_role(name: str, description: str = "") -> int:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO roles (name, description, is_system) VALUES (?, ?, 0)",
        (name, description),
    )
    conn.commit()
    cursor.execute("SELECT id FROM roles WHERE name = ?", (name,))
    role_id = cursor.fetchone()[0]
    conn.close()
    return role_id


@_db_fallback
def assign_role_to_user(user_id: int, role_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role_id = ? WHERE id = ?", (role_id, user_id))
    conn.commit()
    conn.close()


@_db_fallback
def set_role_permissions(role_id: int, feature_keys: set):
    """Replace a role's permissions with exactly ``feature_keys`` (single txn)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        for key in feature_keys:
            cursor.execute("SELECT id FROM permissions WHERE feature_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission_id, granted) VALUES (?, ?, 1)",
                    (role_id, row[0]),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@_db_fallback
def grant_permission(role_id: int, feature_key: str, granted: bool = True):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM permissions WHERE feature_key = ?", (feature_key,))
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "INSERT OR REPLACE INTO role_permissions (role_id, permission_id, granted) VALUES (?, ?, ?)",
            (role_id, row[0], 1 if granted else 0),
        )
        conn.commit()
    conn.close()


@_db_fallback
def toggle_permission(role_id: int, feature_key: str) -> bool:
    """Flip a role's grant state for ``feature_key``; returns the new state."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    new_state = False
    cursor.execute("SELECT id FROM permissions WHERE feature_key = ?", (feature_key,))
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "SELECT granted FROM role_permissions WHERE role_id = ? AND permission_id = ?",
            (role_id, row[0]),
        )
        cur = cursor.fetchone()
        new_state = not bool(cur[0]) if cur else True
        cursor.execute(
            "INSERT OR REPLACE INTO role_permissions (role_id, permission_id, granted) VALUES (?, ?, ?)",
            (role_id, row[0], 1 if new_state else 0),
        )
        conn.commit()
    conn.close()
    return new_state


@_db_fallback
def create_user(username: str, secret: str, role_id: int, display_name: str = "", pin: str = "") -> int:
    """Create a user with a salted-hash password (and optional PIN)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    pw_hash = auth_crypto.hash_secret(secret)
    pin_hash = auth_crypto.hash_secret(pin) if pin else None
    cursor.execute(
        """INSERT INTO users (username, display_name, password_hash, pin_hash, role_id, is_active, created_at)
           VALUES (?, ?, ?, ?, ?, 1, datetime('now'))""",
        (username, display_name, pw_hash, pin_hash, role_id),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


@_db_fallback
def authenticate_user(username: str, secret: str):
    """Authenticate by username/password.

    Enforces ``is_active`` and a temporary lockout after repeated failures.
    Returns the ``user_id`` on success, or ``None`` on any failure.
    """
    from datetime import datetime, timedelta

    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, password_hash, is_active, failed_attempts, locked_until FROM users WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    user_id, pw_hash, is_active, failed, locked_until = row
    if not is_active:
        conn.close()
        return None
    if locked_until:
        try:
            if datetime.fromisoformat(locked_until) > datetime.now():
                conn.close()
                return None
        except ValueError:
            pass
    if auth_crypto.verify_secret(secret, pw_hash):
        cursor.execute("UPDATE users SET failed_attempts = 0, locked_until = '' WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return user_id
    failed = (failed or 0) + 1
    if failed >= 5:
        until = (datetime.now() + timedelta(minutes=15)).isoformat()
        cursor.execute("UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?", (failed, until, user_id))
    else:
        cursor.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (failed, user_id))
    conn.commit()
    conn.close()
    return None


@_db_fallback
def verify_user_pin(user_id: int, pin: str) -> bool:
    """Verify a user's PIN (constant-time). Returns False if no PIN is set."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT pin_hash FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    return auth_crypto.verify_secret(pin, row[0])


@_db_fallback
def user_has_pin(user_id: int) -> bool:
    """True when the user has a PIN configured (enables PIN quick-auth).

    Used by the authorization middleware to decide whether a sensitive action
    can be re-verified with a PIN prompt. Users without a PIN degrade to
    permission-only checks rather than being locked out.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT pin_hash FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0])


@_db_fallback
def set_owner_override_password(new_password: str):
    """Set the Owner override master secret (only after a verified override)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO system_settings (key, value) VALUES ('owner_override_hash', ?)",
        (auth_crypto.hash_secret(new_password),),
    )
    conn.commit()
    conn.close()


@_db_fallback
def verify_owner_override(password: str) -> bool:
    """Verify the Owner override master secret (constant-time)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'owner_override_hash'")
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    return auth_crypto.verify_secret(password, row[0])


_BOOTSTRAP_OVERRIDE = "ChangeMe!Owner"


@_db_fallback
def is_owner_override_default() -> bool:
    """True while the Owner override still uses the shipped bootstrap secret.

    Used by the startup gate (G8) to force a rotation before the UI is usable.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'owner_override_hash'")
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    return auth_crypto.verify_secret(_BOOTSTRAP_OVERRIDE, row[0])


@_db_fallback
def mark_owner_override_rotated() -> None:
    """Record that the Owner override secret has been rotated off the bootstrap."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO system_settings (key, value) VALUES ('owner_override_rotated', '1')",
    )
    conn.commit()
    conn.close()


@_db_fallback
def is_owner_override_rotated() -> bool:
    """True once the Owner override secret has been rotated off the bootstrap."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'owner_override_rotated'")
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == "1")


# ── Products ──

@_db_fallback
def add_product(name: str, price: float, manufacturer_barcode: str, internal_unique_barcode: str,
                expiry_date: str = '', manufacture_date: str = '', vendor_name: str = 'N/A',
                dea_schedule: str = 'OTC', wholesale_price: float = 0.0, reorder_threshold: int = 0):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status,
               expiry_date, manufacture_date, vendor_name, dea_schedule, wholesale_price, reorder_threshold)
        VALUES (?, ?, ?, ?, 'In Stock', ?, ?, ?, ?, ?, ?)
    """, (name, price, manufacturer_barcode, internal_unique_barcode, expiry_date, manufacture_date,
          vendor_name, dea_schedule, wholesale_price, reorder_threshold))
    conn.commit()
    conn.close()


@_db_fallback
def get_all_products():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name FROM products")
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_product_by_id(product_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products WHERE id = ?
    """, (product_id,))
    row = cursor.fetchone()
    conn.close()
    return row


@_db_fallback
def search_products(query: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE manufacturer_barcode LIKE ? 
           OR internal_unique_barcode LIKE ?
           OR name LIKE ?
    """, (like_query, like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_grouped_products():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, COUNT(*) as qty, MIN(price) as min_price, MAX(price) as max_price
        FROM products
        WHERE status = 'In Stock'
        GROUP BY name
        ORDER BY name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_products_with_vendors():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT name, COALESCE(vendor_name, 'N/A') as vendor_name, internal_unique_barcode
        FROM products
        WHERE status = 'In Stock'
        ORDER BY name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_unique_product_names():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT name
        FROM products
        WHERE status = 'In Stock'
        ORDER BY name ASC
    """)
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows


@_db_fallback
def get_product_template(name: str, vendor_name: str = None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if vendor_name and vendor_name.strip() and vendor_name.strip() != 'N/A':
        cursor.execute("""
            SELECT name, price, manufacturer_barcode, expiry_date, manufacture_date
            FROM products WHERE name = ? AND vendor_name = ? AND status = 'In Stock' ORDER BY id DESC LIMIT 1
        """, (name, vendor_name.strip()))
    else:
        cursor.execute("""
            SELECT name, price, manufacturer_barcode, expiry_date, manufacture_date
            FROM products WHERE name = ? AND status = 'In Stock' ORDER BY id DESC LIMIT 1
        """, (name,))
    row = cursor.fetchone()
    conn.close()
    return row


@_db_fallback
def get_products_by_vendor(vendor_name: str = None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if vendor_name and vendor_name.strip() and vendor_name.strip() != 'N/A':
        cursor.execute("""
            SELECT DISTINCT name FROM products
            WHERE vendor_name = ? AND status = 'In Stock'
            ORDER BY name ASC
        """, (vendor_name.strip(),))
    else:
        cursor.execute("""
            SELECT DISTINCT name FROM products
            WHERE status = 'In Stock'
            ORDER BY name ASC
        """)
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


@_db_fallback
def get_batches_by_name(drug_name: str, sort_by: str = 'expiry_date'):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    valid_sorts = {'expiry_date': 'expiry_date ASC', 'manufacture_date': 'manufacture_date DESC'}
    order = valid_sorts.get(sort_by, 'expiry_date ASC')
    cursor.execute(f"""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE name = ? AND status = 'In Stock'
        ORDER BY {order}
    """, (drug_name,))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_all_in_stock_batches(sort_by: str = 'expiry_date'):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    valid_sorts = {
        'expiry_date': 'expiry_date ASC, name ASC',
        'manufacture_date': 'manufacture_date DESC, name ASC',
        'name': 'name ASC, expiry_date ASC',
        'vendor': 'vendor_name ASC, name ASC',
    }
    order = valid_sorts.get(sort_by, 'expiry_date ASC, name ASC')
    cursor.execute(f"""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
        ORDER BY {order}
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def search_all_batches(query: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
          AND (name LIKE ? OR manufacturer_barcode LIKE ? OR internal_unique_barcode LIKE ?
               OR vendor_name LIKE ? OR expiry_date LIKE ?)
        ORDER BY name ASC, expiry_date ASC
    """, (like_query, like_query, like_query, like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_product_by_internal_barcode(internal_barcode: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE internal_unique_barcode = ? AND status = 'In Stock'
    """, (internal_barcode,))
    row = cursor.fetchone()
    conn.close()
    return row


@_db_fallback
def search_grouped_products(query: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute("""
        SELECT name, COUNT(*) as qty, MIN(price) as min_price, MAX(price) as max_price
        FROM products
        WHERE status = 'In Stock'
          AND (name LIKE ? OR manufacturer_barcode LIKE ? OR internal_unique_barcode LIKE ?)
        GROUP BY name
        ORDER BY name ASC
    """, (like_query, like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def update_product_dates(product_id: int, expiry_date: str, manufacture_date: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products SET expiry_date = ?, manufacture_date = ? WHERE id = ?
    """, (expiry_date, manufacture_date, product_id))
    conn.commit()
    conn.close()


@_db_fallback
def update_product_full(product_id: int, name: str, price: float, manufacturer_barcode: str,
                        internal_barcode: str, expiry_date: str, manufacture_date: str,
                        status: str, vendor_name: str = 'N/A', dea_schedule: str = 'OTC',
                        wholesale_price: float = 0.0, reorder_threshold: int = 0):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products SET name = ?, price = ?, manufacturer_barcode = ?,
               internal_unique_barcode = ?, expiry_date = ?, manufacture_date = ?,
               status = ?, vendor_name = ?, dea_schedule = ?, wholesale_price = ?, reorder_threshold = ?
        WHERE id = ?
    """, (name, price, manufacturer_barcode, internal_barcode, expiry_date, manufacture_date,
          status, vendor_name, dea_schedule, wholesale_price, reorder_threshold, product_id))
    cursor.execute("""
        UPDATE receiving_log SET vendor_name = ?, product_name = ? WHERE barcode = ? AND barcode != ''
    """, (vendor_name, name, internal_barcode))
    cursor.execute("""
        UPDATE receiving_log SET total_cost = ? * quantity WHERE barcode = ? AND barcode != ''
    """, (price, internal_barcode))
    conn.commit()
    conn.close()


@_db_fallback
def get_expiring_batches(exclude_names=None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
          AND expiry_date != ''
        ORDER BY expiry_date ASC
    """)
    all_rows = cursor.fetchall()
    conn.close()

    today = date.today()
    result = []
    exclude_set = set(n.lower().strip() for n in exclude_names) if exclude_names else set()
    for row in all_rows:
        if exclude_set and row[1].lower().strip() in exclude_set:
            continue
        raw_expiry = row[6]
        try:
            normalized = raw_expiry.replace('/', '-')
            parts = normalized.split('-')
            exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            result.append((exp_date, row))
        except (ValueError, IndexError):
            continue
    return result


@_db_fallback
def get_batches_expiring_within(days: int, exclude_names=None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
          AND expiry_date != ''
        ORDER BY expiry_date ASC
    """)
    all_rows = cursor.fetchall()
    conn.close()

    today = date.today()
    cutoff = today + timedelta(days=days)
    result = []
    exclude_set = set(n.lower().strip() for n in exclude_names) if exclude_names else set()
    for row in all_rows:
        if exclude_set and row[1].lower().strip() in exclude_set:
            continue
        raw_expiry = row[6]
        try:
            normalized = raw_expiry.replace('/', '-')
            parts = normalized.split('-')
            exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            if exp_date <= cutoff:
                result.append(row)
        except (ValueError, IndexError):
            continue
    return result


@_db_fallback
def get_expiring_counts_by_vendor(days: int, exclude_names=None):
    batches = get_batches_expiring_within(days, exclude_names=exclude_names)
    counts = {}
    for row in batches:
        vendor = row[8] or "N/A"
        counts[vendor] = counts.get(vendor, 0) + 1
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)


@_db_fallback
def get_product_by_barcode(barcode: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE manufacturer_barcode = ? OR internal_unique_barcode = ?
    """, (barcode, barcode))
    row = cursor.fetchone()
    conn.close()
    return row


@_db_fallback
def update_product_status(barcode: str, new_status: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products 
        SET status = ?
        WHERE manufacturer_barcode = ? OR internal_unique_barcode = ?
    """, (new_status, barcode, barcode))
    conn.commit()
    conn.close()


# ── Sales Logic ──

@_db_fallback
def mark_item_as_sold(barcode: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, vendor_name
        FROM products 
        WHERE manufacturer_barcode = ? OR internal_unique_barcode = ?
    """, (barcode, barcode))
    product = cursor.fetchone()
    if not product:
        conn.close()
        raise ValueError("Product not found.")
    product_id, name, price, mfg_barcode, int_barcode, vendor_name = product
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO sold_items (item_name, price, manufacturer_barcode, internal_barcode, timestamp_of_sale, vendor_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, price, mfg_barcode, int_barcode, timestamp, vendor_name or 'N/A'))
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()


@_db_fallback
def reverse_sale(sold_item_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_name, price, manufacturer_barcode, internal_barcode, vendor_name
        FROM sold_items 
        WHERE id = ?
    """, (sold_item_id,))
    sold_item = cursor.fetchone()
    if not sold_item:
        conn.close()
        raise ValueError("Sold item not found.")
    sold_id, name, price, mfg_barcode, int_barcode, vendor_name = sold_item
    cursor.execute("""
        INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status, vendor_name)
        VALUES (?, ?, ?, ?, 'In Stock', ?)
    """, (name, price, mfg_barcode, int_barcode, vendor_name or 'N/A'))
    cursor.execute("DELETE FROM sold_items WHERE id = ?", (sold_item_id,))
    conn.commit()
    conn.close()


@_db_fallback
def get_sold_items():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_name, price, manufacturer_barcode, internal_barcode, timestamp_of_sale,
               COALESCE(vendor_name, 'N/A') as vendor_name
        FROM sold_items
        ORDER BY timestamp_of_sale DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_today_sales_total():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items WHERE timestamp_of_sale LIKE ?", (f"{today}%",))
    total = cursor.fetchone()[0]
    conn.close()
    return total


@_db_fallback
def get_sales_for_date(date_str: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items WHERE timestamp_of_sale LIKE ?", (f"{date_str}%",))
    total = cursor.fetchone()[0]
    conn.close()
    return total


# ── Templates ──

@_db_fallback
def get_templates():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM templates ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def add_template(name: str, price: float):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("INSERT INTO templates (name, price) VALUES (?, ?)", (name, price))
    conn.commit()
    conn.close()


@_db_fallback
def update_template(template_id: int, name: str, price: float):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("UPDATE templates SET name = ?, price = ? WHERE id = ?", (name, price, template_id))
    conn.commit()
    conn.close()


@_db_fallback
def delete_template(template_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    conn.close()


# ── Receiving Log ──

@_db_fallback
def log_shipment(vendor_name: str, product_name: str, date_received: str, quantity: int, total_cost: float, barcode: str = ''):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO receiving_log (vendor_name, product_name, date_received, quantity, total_cost, barcode) VALUES (?, ?, ?, ?, ?, ?)",
        (vendor_name, product_name, date_received, quantity, total_cost, barcode)
    )
    conn.commit()
    conn.close()


@_db_fallback
def receive_inventory_atomically(vendor_name: str, product_name: str, date_received: str,
                                quantity: int, total_cost: float,
                                tpl_price: float, tpl_mfg_barcode: str,
                                tpl_expiry: str, tpl_mfg_date: str,
                                barcode_generator,
                                pre_generated_barcodes=None):
    # Pre-generate all barcodes in a single batch via native_accel (Rust/difflib)
    if pre_generated_barcodes is None:
        try:
            import native_accel
            pre_generated_barcodes = native_accel.generate_batch_barcodes(vendor_name, quantity)
        except ImportError:
            pre_generated_barcodes = None
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    last_barcode = ''
    try:
        cursor.execute("BEGIN TRANSACTION")
        for i in range(quantity):
            if pre_generated_barcodes and i < len(pre_generated_barcodes):
                unique_barcode = pre_generated_barcodes[i]
            else:
                unique_barcode = barcode_generator(vendor_name)
            cursor.execute("""
                INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name)
                VALUES (?, ?, ?, ?, 'In Stock', ?, ?, ?)
            """, (product_name, tpl_price, tpl_mfg_barcode, unique_barcode, tpl_expiry, tpl_mfg_date, vendor_name))
            last_barcode = unique_barcode
        cursor.execute(
            "INSERT INTO receiving_log (vendor_name, product_name, date_received, quantity, total_cost, barcode) VALUES (?, ?, ?, ?, ?, ?)",
            (vendor_name, product_name, date_received, quantity, total_cost, last_barcode)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
    return last_barcode


@_db_fallback
def get_all_receiving_log(filter_date=None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if filter_date:
        cursor.execute(
            "SELECT id, vendor_name, product_name, date_received, quantity, total_cost, COALESCE(barcode, '') as barcode FROM receiving_log WHERE date_received = ? ORDER BY date_received DESC",
            (filter_date,))
    else:
        cursor.execute("SELECT id, vendor_name, product_name, date_received, quantity, total_cost, COALESCE(barcode, '') as barcode FROM receiving_log ORDER BY date_received DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_vendor_total_owed(vendor_name: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(total_cost), 0.0) FROM receiving_log WHERE vendor_name = ?", (vendor_name,))
    total = cursor.fetchone()[0]
    conn.close()
    return total


@_db_fallback
def get_all_vendors():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT vendor_name FROM receiving_log ORDER BY vendor_name ASC")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows


# ── Checkout & Receipts ──

@_db_fallback
def create_receipt(payment_method: str, items: list, patient_id: int = None):
    """Create a receipt with line items. Each item dict:
        {product_name, quantity, price_at_time, internal_barcode, vendor, expiry_date}.
    Atomically: inserts receipt + receipt_items, deletes sold products from inventory.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_amount = sum(item["quantity"] * item["price_at_time"] for item in items)
        cursor.execute(
            "INSERT INTO receipts (timestamp, total_amount, payment_method, patient_id) VALUES (?, ?, ?, ?)",
            (timestamp, total_amount, payment_method, patient_id)
        )
        receipt_id = cursor.lastrowid
        for item in items:
            cursor.execute("""
                INSERT INTO receipt_items
                    (receipt_id, product_name, quantity, price_at_time,
                     internal_barcode, vendor, expiry_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt_id, item["product_name"], item["quantity"], item["price_at_time"],
                item.get("internal_barcode", ""), item.get("vendor", ""),
                item.get("expiry_date", "")
            ))
        for item in items:
            barcode = item.get("internal_barcode", "")
            if barcode:
                cursor.execute("""
                    SELECT id FROM products
                    WHERE internal_unique_barcode = ? AND status = 'In Stock'
                """, (barcode,))
                row = cursor.fetchone()
                if not row:
                    conn.rollback()
                    raise ValueError(
                        f"Batch '{barcode}' for '{item['product_name']}' not found in stock."
                    )
                if item["quantity"] != 1:
                    conn.rollback()
                    raise ValueError(
                        f"Serialized model allows qty=1 per batch. "
                        f"Got qty={item['quantity']} for '{item['product_name']}'."
                    )
                cursor.execute("DELETE FROM products WHERE id = ?", (row[0],))
            else:
                cursor.execute("""
                    SELECT id FROM products
                    WHERE name = ? AND status = 'In Stock'
                    ORDER BY id ASC
                    LIMIT ?
                """, (item["product_name"], item["quantity"]))
                rows = cursor.fetchall()
                if len(rows) < item["quantity"]:
                    conn.rollback()
                    raise ValueError(
                        f"Insufficient stock for '{item['product_name']}': "
                        f"need {item['quantity']}, have {len(rows)}"
                    )
                for row in rows:
                    cursor.execute("DELETE FROM products WHERE id = ?", (row[0],))
        conn.commit()
        return receipt_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


@_db_fallback
def checkout_cart_atomically(payment_method: str, cart_entries: list,
                             patient_id: int = None, tax_rate: float = 0.0,
                             sale_type: str = "OTC", insurance_copay: float = 0.0,
                             insurance_amount: float = 0.0) -> int:
    """Process an entire POS cart within a single SQLite transaction.

    For each cart entry, migrates every staged serialized box from ``products``
    to ``sold_items`` (one ``sold_items`` row per unique ``internal_unique_barcode``),
    deletes the corresponding ``products`` rows, and records ``receipt_items``
    + ``receipts`` for payment/receipt tracking.

    Args:
        payment_method: 'Cash', 'Card', or 'Transfer'.
        cart_entries:  List of dicts, one per product line:
            {product_name, quantity, price_at_time, internal_barcodes: [str],
             vendor, expiry_date}
        patient_id: Optional patient FK.
        tax_rate: Flat tax percentage (0–100) from config ``tax_rate``.
        sale_type: POS sale classification ('OTC', 'Rx OTC', 'Delivery',
                   'Loyalty', 'Gifts').
        insurance_copay: Patient-paid copay amount (0.0 if no insurance).
        insurance_amount: Amount covered by insurance (0.0 if no insurance).

    Returns:
        receipt_id (int) from the newly created ``receipts`` row.

    Raises:
        ValueError: if a staged barcode is not found in stock.
        Exception: any other error — the entire transaction is rolled back.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")

        subtotal = sum(
            entry["price_at_time"] * entry["quantity"]
            for entry in cart_entries
        )
        tax_amount = subtotal * (tax_rate / 100.0) if tax_rate else 0.0
        total_amount = subtotal + tax_amount

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO receipts (timestamp, total_amount, payment_method, patient_id, "
            "sale_type, insurance_copay, insurance_amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (timestamp, total_amount, payment_method, patient_id,
             sale_type, insurance_copay, insurance_amount)
        )
        receipt_id = cursor.lastrowid

        for entry in cart_entries:
            barcodes = entry.get("internal_barcodes", [])
            cursor.execute("""
                INSERT INTO receipt_items
                    (receipt_id, product_name, quantity, price_at_time,
                     internal_barcode, vendor, expiry_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt_id, entry["product_name"], entry["quantity"],
                entry["price_at_time"], ", ".join(barcodes),
                entry.get("vendor", "N/A"), entry.get("expiry_date", "")
            ))

            for barcode in barcodes:
                cursor.execute("""
                    SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                           vendor_name
                    FROM products
                    WHERE internal_unique_barcode = ? AND status = 'In Stock'
                """, (barcode,))
                product = cursor.fetchone()
                if not product:
                    conn.rollback()
                    raise ValueError(
                        f"Batch '{barcode}' for '{entry['product_name']}' "
                        f"not found in stock or already sold."
                    )
                product_id, name, price, mfg_barcode, int_barcode, vendor_name = product
                cursor.execute("""
                    INSERT INTO sold_items
                        (item_name, price, manufacturer_barcode, internal_barcode,
                         timestamp_of_sale, vendor_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, price, mfg_barcode, int_barcode, timestamp,
                      vendor_name or 'N/A'))
                cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))

        conn.commit()
        return receipt_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


@_db_fallback
def get_receipts():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, total_amount, payment_method, sale_type FROM receipts ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_receipt_items(receipt_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, receipt_id, product_name, quantity, price_at_time,
               COALESCE(internal_barcode, '') as internal_barcode,
               COALESCE(vendor, '') as vendor,
               COALESCE(expiry_date, '') as expiry_date
        FROM receipt_items WHERE receipt_id = ?
    """, (receipt_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_all_receipt_items_flat():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ri.id, ri.receipt_id, ri.product_name, ri.quantity, ri.price_at_time,
               (ri.quantity * ri.price_at_time) as line_total,
               r.timestamp, r.payment_method,
               COALESCE(ri.internal_barcode, '') as internal_barcode,
               COALESCE(ri.vendor, '') as vendor,
               COALESCE(ri.expiry_date, '') as expiry_date
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        ORDER BY r.timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_receipt_items_for_date(date_str: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ri.id, ri.receipt_id, ri.product_name, ri.quantity, ri.price_at_time,
               (ri.quantity * ri.price_at_time) as line_total,
               r.timestamp, r.payment_method,
               COALESCE(ri.internal_barcode, '') as internal_barcode,
               COALESCE(ri.vendor, '') as vendor,
               COALESCE(ri.expiry_date, '') as expiry_date
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE r.timestamp LIKE ?
        ORDER BY r.timestamp DESC
    """, (f"{date_str}%",))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_receipt_items_grouped_by_date():
    flat = get_all_receipt_items_flat()
    grouped = defaultdict(list)
    for r in flat:
        date_part = r[6][:10] if r[6] and len(r[6]) >= 10 else "Unknown"
        grouped[date_part].append(r)
    return grouped


@_db_fallback
def get_receipts_total_for_date(date_str: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(SUM(total_amount), 0.0) FROM receipts WHERE timestamp LIKE ?",
        (f"{date_str}%",)
    )
    total = cursor.fetchone()[0]
    conn.close()
    return total


@_db_fallback
def reverse_receipt_item(receipt_item_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            SELECT id, receipt_id, product_name, quantity, price_at_time,
                   COALESCE(internal_barcode, '') as internal_barcode,
                   COALESCE(vendor, '') as vendor,
                   COALESCE(expiry_date, '') as expiry_date
            FROM receipt_items WHERE id = ?
        """, (receipt_item_id,))
        item = cursor.fetchone()
        if not item:
            conn.rollback()
            raise ValueError("Receipt item not found.")
        (_, receipt_id, product_name, quantity, price_at_time,
         stored_barcode, stored_vendor, stored_expiry) = item
        import barcode_logic as _bl
        for _ in range(quantity):
            if stored_barcode:
                unique_barcode = stored_barcode
            else:
                unique_barcode = _bl.generate_internal_barcode(stored_vendor or "N/A")
            cursor.execute("""
                INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode,
                                      status, expiry_date, manufacture_date, vendor_name)
                VALUES (?, ?, '', ?, 'In Stock', ?, '', ?)
            """, (product_name, price_at_time, unique_barcode,
                  stored_expiry, stored_vendor or 'N/A'))
        cursor.execute("DELETE FROM receipt_items WHERE id = ?", (receipt_item_id,))
        line_total = quantity * price_at_time
        cursor.execute(
            "UPDATE receipts SET total_amount = total_amount - ? WHERE id = ?",
            (line_total, receipt_id)
        )
        cursor.execute("SELECT COUNT(*) FROM receipt_items WHERE receipt_id = ?", (receipt_id,))
        remaining = cursor.fetchone()[0]
        if remaining == 0:
            cursor.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ── Backup ──
@_db_fallback
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


# ── Dashboard & Analytics ──

@_db_fallback
def get_dashboard_metrics():
    """Returns a dict with all dashboard KPI metrics.
    Optimized: runs all scalar queries in a single connection, then
    delegates expiry/low-stock to their existing helpers.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'In Stock'")
    total_in_stock = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM products WHERE status = 'In Stock'")
    total_inventory_value = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sold_items")
    total_sold = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items")
    total_revenue = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT name) FROM products WHERE status = 'In Stock'")
    total_products = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT vendor_name) FROM products WHERE status = 'In Stock' AND vendor_name != 'N/A'")
    total_vendors = cursor.fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items WHERE timestamp_of_sale LIKE ?", (f"{today}%",))
    todays_sales = cursor.fetchone()[0]
    conn.close()

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


@_db_fallback
def get_low_stock_products(threshold=5):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, COUNT(*) as qty, MIN(expiry_date) as min_expiry
        FROM products
        WHERE status = 'In Stock'
        GROUP BY name
        HAVING COUNT(*) <= ?
        ORDER BY qty ASC, name ASC
    """, (threshold,))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_top_selling_products(start_date, end_date, limit=10):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ri.product_name, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE date(r.timestamp) BETWEEN ? AND ?
        GROUP BY ri.product_name
        ORDER BY SUM(ri.quantity) DESC
        LIMIT ?
    """, (start_date, end_date, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_sales_analytics(start_date: str, end_date: str) -> dict:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ri.product_name,
               SUM(ri.quantity) as total_qty,
               SUM(ri.quantity * ri.price_at_time) as total_revenue,
               ROUND(SUM(ri.quantity * ri.price_at_time) / SUM(ri.quantity), 2) as avg_price
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE date(r.timestamp) BETWEEN ? AND ?
        GROUP BY ri.product_name
        ORDER BY total_qty DESC
    """, (start_date, end_date))
    raw_products = cursor.fetchall()
    ranked_products = []
    for rank, (name, qty, revenue, avg_price) in enumerate(raw_products, 1):
        ranked_products.append((rank, name, qty, revenue, avg_price))
    cursor.execute("""
        SELECT COALESCE(SUM(ri.quantity), 0),
               COALESCE(SUM(ri.quantity * ri.price_at_time), 0),
               COUNT(DISTINCT ri.product_name),
               COUNT(DISTINCT r.id)
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE date(r.timestamp) BETWEEN ? AND ?
    """, (start_date, end_date))
    total_items, total_rev, unique_prods, total_txns = cursor.fetchone()
    avg_basket = (total_items / total_txns) if total_txns > 0 else 0.0
    conn.close()
    return {
        "ranked_products": ranked_products,
        "total_items_sold": total_items,
        "total_revenue": total_rev,
        "unique_products": unique_prods,
        "total_transactions": total_txns,
        "avg_basket_size": round(avg_basket, 1),
    }


@_db_fallback
def get_sales_by_period(period='month'):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if period == 'day':
        cursor.execute("""
            SELECT date(r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY date(r.timestamp)
            ORDER BY period DESC
        """)
    elif period == 'week':
        cursor.execute("""
            SELECT strftime('%Y-W%W', r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY strftime('%Y-W%W', r.timestamp)
            ORDER BY period DESC
        """)
    elif period == 'year':
        cursor.execute("""
            SELECT strftime('%Y', r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY strftime('%Y', r.timestamp)
            ORDER BY period DESC
        """)
    else:  # month
        cursor.execute("""
            SELECT strftime('%Y-%m', r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY strftime('%Y-%m', r.timestamp)
            ORDER BY period DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ── Patients CRM ──

@_db_fallback
def add_patient(name: str, phone: str = '', email: str = '', custom_fields: dict = None):
    """Insert a new patient with optional custom fields.
    custom_fields: {"Allergies": "Penicillin", "Insurance": "ABC123", ...}
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO patients (name, phone, email, created_at) VALUES (?, ?, ?, ?)",
            (name, phone, email, created_at)
        )
        patient_id = cursor.lastrowid
        if custom_fields:
            for field_name, field_value in custom_fields.items():
                if field_name and field_name.strip():
                    cursor.execute(
                        "INSERT INTO patient_fields (patient_id, field_name, field_value) VALUES (?, ?, ?)",
                        (patient_id, field_name.strip(), field_value)
                    )
        conn.commit()
        return patient_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


@_db_fallback
def get_all_patients(search_query: str = None):
    """Return all patients with their custom fields.
    Returns: [(patient_id, name, phone, email, created_at, {field_name: field_value, ...})]
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if search_query:
        like_query = f"%{search_query}%"
        cursor.execute("""
            SELECT id, name, phone, email, created_at
            FROM patients
            WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?
            ORDER BY name ASC
        """, (like_query, like_query, like_query))
    else:
        cursor.execute("SELECT id, name, phone, email, created_at FROM patients ORDER BY name ASC")
    patients = cursor.fetchall()
    result = []
    for pid, name, phone, email, created_at in patients:
        cursor.execute(
            "SELECT field_name, field_value FROM patient_fields WHERE patient_id = ?",
            (pid,)
        )
        fields = {row[0]: row[1] for row in cursor.fetchall()}
        result.append((pid, name, phone, email, created_at, fields))
    conn.close()
    return result


@_db_fallback
def get_patient_by_id(patient_id: int):
    """Return a single patient with custom fields, or None."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, phone, email, created_at FROM patients WHERE id = ?",
        (patient_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    pid, name, phone, email, created_at = row
    cursor.execute(
        "SELECT field_name, field_value FROM patient_fields WHERE patient_id = ?",
        (pid,)
    )
    fields = {r[0]: r[1] for r in cursor.fetchall()}
    conn.close()
    return (pid, name, phone, email, created_at, fields)


@_db_fallback
def update_patient(patient_id: int, name: str, phone: str = '', email: str = '', custom_fields: dict = None):
    """Update patient core fields and replace all custom fields."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute(
            "UPDATE patients SET name = ?, phone = ?, email = ? WHERE id = ?",
            (name, phone, email, patient_id)
        )
        cursor.execute("DELETE FROM patient_fields WHERE patient_id = ?", (patient_id,))
        if custom_fields:
            for field_name, field_value in custom_fields.items():
                if field_name and field_name.strip():
                    cursor.execute(
                        "INSERT INTO patient_fields (patient_id, field_name, field_value) VALUES (?, ?, ?)",
                        (patient_id, field_name.strip(), field_value)
                    )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


@_db_fallback
def delete_patient(patient_id: int):
    """Delete a patient and all their custom fields (CASCADE)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("DELETE FROM patient_fields WHERE patient_id = ?", (patient_id,))
    cursor.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()


@_db_fallback
def get_distinct_patient_field_names():
    """Return sorted list of distinct custom field names ever used.
    Used to populate the CTkComboBox suggestions in the patient dialog.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT field_name FROM patient_fields ORDER BY field_name ASC")
    names = [r[0] for r in cursor.fetchall()]
    conn.close()
    return names


# ── Suppliers ─────────────────────────────────────────────────────────────


@_db_fallback
def get_suppliers() -> list[tuple]:
    """Return all suppliers ordered by preferred-first then name.

    Columns: id, name, contact_name, contact_email, contact_phone, address,
    preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
    edi_api_key, performance_notes, created_at, updated_at.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, contact_name, contact_email, contact_phone, address,
               preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
               edi_api_key, performance_notes, created_at, updated_at
        FROM suppliers
        ORDER BY preferred DESC, name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_supplier_by_id(supplier_id: int) -> tuple | None:
    """Return a single supplier row by ID, or None."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, contact_name, contact_email, contact_phone, address,
               preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
               edi_api_key, performance_notes, created_at, updated_at
        FROM suppliers WHERE id = ?
    """, (supplier_id,))
    row = cursor.fetchone()
    conn.close()
    return row


@_db_fallback
def add_supplier(
    name: str,
    contact_name: str = "",
    contact_email: str = "",
    contact_phone: str = "",
    address: str = "",
    preferred: int = 0,
    sku: str = "",
    min_stock_level: int = 0,
    lead_time_days: int = 0,
    edi_endpoint: str = "",
    edi_api_key: str = "",
    performance_notes: str = "",
) -> int:
    """Insert a supplier. Raises ValueError if the name already exists."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            INSERT INTO suppliers
                (name, contact_name, contact_email, contact_phone, address,
                 preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
                 edi_api_key, performance_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, contact_name, contact_email, contact_phone, address,
            preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
            edi_api_key, performance_notes,
        ))
        supplier_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError(f"Supplier '{name}' already exists")
    finally:
        conn.close()

    import audit_log
    audit_log.log_action(
        "SUPPLIER_CREATE",
        f"Supplier '{name}' (id={supplier_id}) created.",
    )
    return supplier_id


@_db_fallback
def update_supplier(
    supplier_id: int,
    name: str,
    contact_name: str = "",
    contact_email: str = "",
    contact_phone: str = "",
    address: str = "",
    preferred: int = 0,
    sku: str = "",
    min_stock_level: int = 0,
    lead_time_days: int = 0,
    edi_endpoint: str = "",
    edi_api_key: str = "",
    performance_notes: str = "",
) -> bool:
    """Update an existing supplier. Raises ValueError on duplicate name."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            UPDATE suppliers SET
                name = ?, contact_name = ?, contact_email = ?, contact_phone = ?,
                address = ?, preferred = ?, sku = ?, min_stock_level = ?,
                lead_time_days = ?, edi_endpoint = ?, edi_api_key = ?,
                performance_notes = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (
            name, contact_name, contact_email, contact_phone, address,
            preferred, sku, min_stock_level, lead_time_days, edi_endpoint,
            edi_api_key, performance_notes, supplier_id,
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError(f"Supplier '{name}' already exists")
    finally:
        conn.close()

    import audit_log
    audit_log.log_action(
        "SUPPLIER_UPDATE",
        f"Supplier id={supplier_id} ('{name}') updated.",
    )
    return True


@_db_fallback
def delete_supplier(supplier_id: int) -> bool:
    """Delete a supplier. Raises ValueError if the supplier is marked preferred
    (must be demoted before deletion)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT preferred, name FROM suppliers WHERE id = ?", (supplier_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return False
    if row[0]:
        conn.close()
        raise ValueError(f"Preferred supplier '{row[1]}' cannot be deleted; demote first")
    cursor.execute("BEGIN TRANSACTION")
    cursor.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    conn.commit()
    conn.close()

    import audit_log
    audit_log.log_action(
        "SUPPLIER_DELETE",
        f"Supplier id={supplier_id} ('{row[1]}') deleted.",
    )
    return True


# ── Purchase Orders ───────────────────────────────────────────────────────


@_db_fallback
def get_purchase_orders(status_filter: str | None = None) -> list[tuple]:
    """Return purchase orders ordered by most-recent first.

    Columns: id, po_number, vendor_id, vendor_name, status, created_at,
    submitted_at, received_at, closed_at, subtotal, tax_amount, total_cost, notes.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if status_filter:
        cursor.execute("""
            SELECT id, po_number, vendor_id, vendor_name, status, created_at,
                   submitted_at, received_at, closed_at, subtotal, tax_amount,
                   total_cost, notes
            FROM purchase_orders
            WHERE status = ?
            ORDER BY created_at DESC
        """, (status_filter,))
    else:
        cursor.execute("""
            SELECT id, po_number, vendor_id, vendor_name, status, created_at,
                   submitted_at, received_at, closed_at, subtotal, tax_amount,
                   total_cost, notes
            FROM purchase_orders
            ORDER BY created_at DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_po_by_id(po_id: int) -> tuple | None:
    """Return a single purchase order row by ID, or None."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, po_number, vendor_id, vendor_name, status, created_at,
               submitted_at, received_at, closed_at, subtotal, tax_amount,
               total_cost, notes
        FROM purchase_orders WHERE id = ?
    """, (po_id,))
    row = cursor.fetchone()
    conn.close()
    return row


@_db_fallback
def get_po_items(po_id: int) -> list[tuple]:
    """Return all line items for a PO ordered by line_number.

    Columns: id, line_number, product_name, vendor_sku, quantity, unit_price,
    line_total, status, internal_barcodes, mfg_barcode, expiry_date, mfg_date.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, line_number, product_name, vendor_sku, quantity, unit_price,
               line_total, status, internal_barcodes, mfg_barcode, expiry_date,
               mfg_date
        FROM po_items
        WHERE po_id = ?
        ORDER BY line_number ASC
    """, (po_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


@_db_fallback
def get_next_po_number() -> str:
    """Generate the next sequential PO number: ``PO-{YYYY}-{NNNN}``."""
    year = datetime.now().strftime("%Y")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT po_number FROM purchase_orders "
        "WHERE po_number LIKE ? ORDER BY po_number DESC LIMIT 1",
        (f"PO-{year}-%",),
    )
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            last_seq = int(row[0].rsplit("-", 1)[-1])
            next_seq = last_seq + 1
        except ValueError:
            next_seq = 1
    else:
        next_seq = 1
    return f"PO-{year}-{next_seq:04d}"


# ── Purchase Order Mutation ───────────────────────────────────────────────


_LEGAL_PO_TRANSITIONS: dict[str, set[str]] = {
    "Draft": {"Submitted"},
    "Submitted": {"Draft"},
    "Received": {"Closed"},
}


@_db_fallback
def add_purchase_order(
    vendor_id: int,
    vendor_name: str,
    items: list[dict[str, Any]],
    notes: str = "",
) -> tuple[int, str]:
    """Create a Draft PO with line items in a single transaction.

    *items* entries require: product_name, quantity, unit_price, mfg_barcode,
    expiry_date, mfg_date; vendor_sku is optional.

    Returns ``(po_id, po_number)``.
    """
    po_number = get_next_po_number()
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    total_cost = 0.0
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            INSERT INTO purchase_orders
                (po_number, vendor_id, vendor_name, status, notes)
            VALUES (?, ?, ?, 'Draft', ?)
        """, (po_number, vendor_id, vendor_name, notes))
        po_id = cursor.lastrowid

        for idx, item in enumerate(items, start=1):
            qty = int(item.get("quantity", 0))
            unit_price = float(item.get("unit_price", 0.0))
            line_total = qty * unit_price
            total_cost += line_total
            cursor.execute("""
                INSERT INTO po_items
                    (po_id, line_number, product_name, vendor_sku, quantity,
                     unit_price, line_total, mfg_barcode, expiry_date, mfg_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                po_id, idx, item["product_name"],
                item.get("vendor_sku", ""), qty, unit_price, line_total,
                item.get("mfg_barcode", ""), item.get("expiry_date", ""),
                item.get("mfg_date", ""),
            ))

        cursor.execute(
            "UPDATE purchase_orders SET subtotal = ?, total_cost = ? WHERE id = ?",
            (total_cost, total_cost, po_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    import audit_log
    audit_log.log_action(
        "PO_CREATE",
        f"PO #{po_number} (id={po_id}) created for vendor '{vendor_name}', "
        f"{len(items)} item(s), total=${total_cost:.2f}.",
    )
    return po_id, po_number


@_db_fallback
def update_po_status(po_id: int, status: str) -> bool:
    """Transition a PO to *status* (Draft→Submitted→Received→Closed).

    Raises ValueError on an illegal transition.  Only ``Submit``, ``Un-submit``
    (Submitted→Draft) and ``Close`` are routed here; the Received transition is
    performed by ``receive_po_items``.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM purchase_orders WHERE id = ?", (po_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Purchase order {po_id} not found")

    current = row[0]
    if status == current:
        conn.close()
        return True
    legal = _LEGAL_PO_TRANSITIONS.get(current, set())
    if status not in legal:
        conn.close()
        raise ValueError(f"Illegal PO transition: {current} → {status}")

    ts_col = {
        "Submitted": "submitted_at",
        "Draft": "created_at",
        "Closed": "closed_at",
    }.get(status)
    try:
        cursor.execute("BEGIN TRANSACTION")
        if ts_col:
            cursor.execute(
                f"UPDATE purchase_orders SET status = ?, {ts_col} = datetime('now') "
                "WHERE id = ?",
                (status, po_id),
            )
        else:
            cursor.execute(
                "UPDATE purchase_orders SET status = ? WHERE id = ?",
                (status, po_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    import audit_log
    audit_log.log_action(
        "PO_STATUS",
        f"PO id={po_id} status changed: {current} → {status}.",
    )
    return True


@_db_fallback
def add_po_item(
    po_id: int,
    product_name: str,
    quantity: int,
    unit_price: float,
    vendor_sku: str = "",
    mfg_barcode: str = "",
    expiry_date: str = "",
    mfg_date: str = "",
) -> int:
    """Append a line item to a Draft PO and recompute totals."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT COALESCE(MAX(line_number), 0) FROM po_items WHERE po_id = ?", (po_id,))
        max_line = cursor.fetchone()[0]
        line_number = max_line + 1
        line_total = quantity * unit_price
        cursor.execute("""
            INSERT INTO po_items
                (po_id, line_number, product_name, vendor_sku, quantity, unit_price,
                 line_total, mfg_barcode, expiry_date, mfg_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (po_id, line_number, product_name, vendor_sku, quantity, unit_price,
              line_total, mfg_barcode, expiry_date, mfg_date))
        item_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    update_po_totals(po_id)
    return item_id


@_db_fallback
def update_po_item(
    item_id: int,
    quantity: int,
    unit_price: float,
    product_name: str | None = None,
    mfg_barcode: str | None = None,
    expiry_date: str | None = None,
    mfg_date: str | None = None,
    vendor_sku: str | None = None,
) -> bool:
    """Update an editable PO line item and recompute PO totals."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    line_total = quantity * unit_price
    try:
        cursor.execute("BEGIN TRANSACTION")
        sets: list[str] = ["quantity = ?", "unit_price = ?", "line_total = ?"]
        vals: list[Any] = [quantity, unit_price, line_total]
        if product_name is not None:
            sets.append("product_name = ?")
            vals.append(product_name)
        if vendor_sku is not None:
            sets.append("vendor_sku = ?")
            vals.append(vendor_sku)
        if mfg_barcode is not None:
            sets.append("mfg_barcode = ?")
            vals.append(mfg_barcode)
        if expiry_date is not None:
            sets.append("expiry_date = ?")
            vals.append(expiry_date)
        if mfg_date is not None:
            sets.append("mfg_date = ?")
            vals.append(mfg_date)
        vals.append(item_id)
        cursor.execute(
            f"UPDATE po_items SET {', '.join(sets)} WHERE id = ?",
            tuple(vals),
        )
        conn.commit()
    finally:
        conn.close()
    # Recompute parent PO totals
    conn = sqlite3.connect(get_db_path())
    cur = conn.cursor()
    cur.execute("SELECT po_id FROM po_items WHERE id = ?", (item_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        update_po_totals(row[0])
    return True


@_db_fallback
def delete_po_item(item_id: int) -> bool:
    """Delete a line item and renumber subsequent lines, then recompute totals."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT po_id FROM po_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        po_id = row[0] if row else None
        cursor.execute("DELETE FROM po_items WHERE id = ?", (item_id,))
        if po_id is not None:
            cursor.execute("""
                UPDATE po_items SET line_number = line_number - 1
                WHERE po_id = ? AND line_number > (
                    SELECT line_number FROM po_items WHERE id = ?
                )
            """, (po_id, item_id))
        conn.commit()
    finally:
        conn.close()
    if po_id is not None:
        update_po_totals(po_id)
    return True


@_db_fallback
def update_po_totals(po_id: int) -> None:
    """Recompute subtotal/tax/total for a PO from its line items."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            UPDATE purchase_orders
            SET subtotal = COALESCE((SELECT SUM(line_total) FROM po_items WHERE po_id = ?), 0),
                tax_amount = 0.0,
                total_cost = COALESCE((SELECT SUM(line_total) FROM po_items WHERE po_id = ?), 0)
            WHERE id = ?
        """, (po_id, po_id, po_id))
        conn.commit()
    finally:
        conn.close()
    import audit_log
    audit_log.log_action("PO_TOTALS", f"PO id={po_id} totals recomputed.")


# ── Low-Stock / Auto-Reorder ──────────────────────────────────────────────


@_db_fallback
def get_products_below_reorder_threshold() -> list[tuple]:
    """Return drugs whose in-stock box count has reached or fallen below their
    per-product ``reorder_threshold`` (only rows with threshold > 0).

    Columns: name, qty, min_threshold, vendor_name, wholesale_price.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, COUNT(*) AS qty, MIN(reorder_threshold) AS min_threshold,
               vendor_name, MIN(wholesale_price) AS wholesale_price
        FROM products
        WHERE status = 'In Stock'
        GROUP BY name
        HAVING COUNT(*) <= MIN(reorder_threshold) AND MIN(reorder_threshold) > 0
        ORDER BY qty ASC, name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ── Purchase Order Receiving (inventory update on PO → Received) ──────────

_LEGAL_PO_RECEIVE_STATUS = {"Received"}


@_db_fallback
def receive_po_items(po_id: int, date_received: str | None = None) -> dict[str, Any]:
    """Atomically receive all line items of a PO into inventory.

    For each line item, calls ``database.receive_inventory_atomically`` with a
    pre-generated barcode batch (``native_accel.generate_batch_barcodes``) so
    that no per-box ``uuid4`` syscall is issued inside the DB loop.  The whole
    operation is wrapped in a retry loop (exponential backoff) that catches
    ``sqlite3.OperationalError`` (lock contention) and fails fast on
    ``ValueError`` (stale/invalid data).  On success the PO and its items are
    marked ``Received`` and an audit entry is written.

    Returns ``{"po_number", "vendor_name", "box_count", "items_received"}``.
    """
    import json  # local: database.py has no top-level json import
    import time as _time
    from native_accel import generate_batch_barcodes

    po = get_po_by_id(po_id)
    if po is None:
        raise ValueError(f"Purchase order {po_id} not found")
    po_number = po[1]
    vendor_name = po[3]
    items = get_po_items(po_id)
    if not items:
        raise ValueError(f"PO #{po_number} has no line items to receive")

    date_received = date_received or datetime.now().strftime("%Y-%m-%d")
    total_qty = sum(int(it[4]) for it in items)  # quantity column
    # Pre-generate the entire vendor's barcode allocation in a single native call
    all_barcodes = generate_batch_barcodes(vendor_name, total_qty)

    max_retries = 3
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            # 1 — Inventory insertion (each call owns its own transaction)
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

            # 2 — Mark PO + items as Received (single transaction)
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                cursor.execute("BEGIN TRANSACTION")
                offset = 0
                for item in items:
                    item_id = item[0]
                    qty = int(item[4])
                    item_barcodes = all_barcodes[offset:offset + qty]
                    offset += qty
                    cursor.execute(
                        "UPDATE po_items SET status = 'Received', received_at = ?, "
                        "internal_barcodes = ? WHERE id = ?",
                        (now, json.dumps(item_barcodes), item_id),
                    )
                cursor.execute(
                    "UPDATE purchase_orders SET status = 'Received', "
                    "received_at = datetime('now') WHERE id = ?",
                    (po_id,),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

            import audit_log
            audit_log.log_action(
                "PO_RECEIVE",
                f"PO #{po_number} (id={po_id}) received: {total_qty} box(es) for "
                f"{len(items)} item(s), vendor='{vendor_name}'.",
            )
            return {
                "po_number": po_number,
                "vendor_name": vendor_name,
                "box_count": total_qty,
                "items_received": len(items),
            }

        except ValueError as exc:
            # stale / invalid data — fail fast, no retry
            last_error = exc
            break
        except sqlite3.OperationalError as exc:
            delay = 0.1 * (2 ** attempt)
            log.warning(
                "receive_po_items attempt %d/%d failed (lock): %s — retrying in %.2fs",
                attempt + 1, max_retries, exc, delay,
            )
            last_error = exc
            _time.sleep(delay)

    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to receive PO #{po_id}")
