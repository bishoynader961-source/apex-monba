"""
backend/db.py — SQLite persistence layer for license keys.

Manages the ``licenses`` table: key generation (done in app.py) inserts
new rows, the ``/api/validate`` endpoint reads and updates them, and
tests inject an in-memory database via ``set_db_path(":memory:")``.
"""
import logging
import os
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger("license_db")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "license_db.sqlite")

_db_path = DEFAULT_DB_PATH
_keepalive = None


def set_db_path(path: str) -> None:
    """Override the database path (used by tests to switch to :memory:)."""
    global _db_path
    _db_path = path


def _connect() -> sqlite3.Connection:
    """Return a SQLite connection to the configured database."""
    if _db_path == ":memory:":
        if _keepalive is None:
            raise RuntimeError(
                "init_db() must be called before using :memory: database"
            )
        return _keepalive
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _close(conn: sqlite3.Connection) -> None:
    """Close a connection unless it is the :memory: keepalive."""
    if _db_path != ":memory:":
        conn.close()


def init_db(db_path: str | None = None) -> None:
    """Create the ``licenses`` table if it does not exist."""
    global _db_path, _keepalive
    if db_path is not None:
        _db_path = db_path

    if _db_path == ":memory:":
        if _keepalive is None:
            _keepalive = sqlite3.connect(":memory:", check_same_thread=False)
            _keepalive.row_factory = sqlite3.Row
        conn = _keepalive
    else:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            license_key     TEXT PRIMARY KEY,
            customer_email  TEXT,
            order_id        TEXT,
            status          TEXT DEFAULT 'active',
            hardware_id     TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Backfill created_at for databases created before this column existed.
    try:
        conn.execute(
            "ALTER TABLE licenses ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()
    if _db_path != ":memory:":
        conn.close()
    logger.info(
        "Database initialized: %s",
        "in-memory" if _db_path == ":memory:" else _db_path,
    )


def insert_license(
    license_key: str,
    customer_email: str,
    order_id: str,
    created_at: str | None = None,
) -> None:
    """Insert a new active license with a NULL hardware_id."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    conn.execute(
        "INSERT INTO licenses "
        "(license_key, customer_email, order_id, status, hardware_id, created_at) "
        "VALUES (?, ?, ?, 'active', NULL, ?)",
        (license_key, customer_email, order_id, created_at),
    )
    conn.commit()
    _close(conn)
    logger.info(
        "Inserted license key=%s*** email=%s order_id=%s",
        license_key[:8], customer_email, order_id,
    )


def get_license(license_key: str) -> sqlite3.Row | None:
    """Fetch a single license row by key (or None)."""
    conn = _connect()
    row = conn.execute(
        "SELECT license_key, customer_email, order_id, status, hardware_id, created_at "
        "FROM licenses WHERE license_key = ?",
        (license_key,),
    ).fetchone()
    _close(conn)
    return row


def bind_hardware_id(license_key: str, hardware_id: str) -> None:
    """Bind a hardware_id to an existing license key."""
    conn = _connect()
    conn.execute(
        "UPDATE licenses SET hardware_id = ? WHERE license_key = ?",
        (hardware_id, license_key),
    )
    conn.commit()
    _close(conn)
    logger.info(
        "Bound hardware_id=%s*** to license=%s***",
        hardware_id[:8], license_key[:8],
    )


def update_license_status(license_key: str, status: str) -> None:
    """Update a license's status (e.g. 'active', 'revoked')."""
    conn = _connect()
    conn.execute(
        "UPDATE licenses SET status = ? WHERE license_key = ?",
        (status, license_key),
    )
    conn.commit()
    _close(conn)
    logger.info(
        "Updated status=%s for license=%s***",
        status, license_key[:8],
    )


def clear_licenses() -> None:
    """Delete all license rows (for test isolation)."""
    conn = _connect()
    conn.execute("DELETE FROM licenses")
    conn.commit()
    _close(conn)


def clear_hardware_id(license_key: str) -> None:
    """Reset hardware_id to NULL for the given license key (re-allow binding)."""
    conn = _connect()
    conn.execute(
        "UPDATE licenses SET hardware_id = NULL WHERE license_key = ?",
        (license_key,),
    )
    conn.commit()
    _close(conn)
    logger.info(
        "Cleared hardware_id for license=%s***",
        license_key[:8],
    )


def get_all_licenses() -> list[sqlite3.Row]:
    """Fetch all license rows ordered by created_at descending."""
    conn = _connect()
    rows = conn.execute(
        "SELECT license_key, customer_email, order_id, status, hardware_id, created_at "
        "FROM licenses ORDER BY created_at DESC"
    ).fetchall()
    _close(conn)
    return rows
