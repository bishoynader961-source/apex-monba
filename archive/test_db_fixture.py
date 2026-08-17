"""test_db_fixture.py — Shared import-time DB/config isolation for the suite.

Importing this module FIRST (before database/db) guarantees that every
connection made by the ORM engine and the sqlite3 fallback targets a disposable
temporary database, never the production archive/pharmacy.db.

Rationale: db.py / rx_db.py resolve DATABASE_URL and the SQLAlchemy engine at
*import time*. The only reliable way to redirect that engine is to set
PHARMACY_DB_PATH in the environment BEFORE the first ``import database`` /
``import db``. This module does exactly that, then initializes both backends.

Usage (top of any test_*.py):
    import test_db_fixture   # must precede `import database` / `import db`
    import database, db, ...

Safe to import multiple times: if PHARMACY_DB_PATH is already set, it reuses the
existing fixture (idempotent).
"""
import atexit
import os
import sys
import tempfile

_DB_PATH = None
_CONFIG_DIR = None


def _ensure_fixture():
    global _DB_PATH, _CONFIG_DIR
    if os.environ.get("PHARMACY_DB_PATH"):
        # Already isolated (e.g. CI set it, or a prior import initialized us).
        _DB_PATH = os.environ["PHARMACY_DB_PATH"]
        _CONFIG_DIR = os.environ.get("PHARMACY_CONFIG_DIR", "")
        return

    fd, db_path = tempfile.mkstemp(prefix="pharmacy_test_", suffix=".db")
    os.close(fd)
    _DB_PATH = db_path
    _CONFIG_DIR = tempfile.mkdtemp(prefix="pharmacy_cfg_")

    os.environ["PHARMACY_DB_PATH"] = _DB_PATH
    os.environ["PHARMACY_CONFIG_DIR"] = _CONFIG_DIR
    os.environ["PHARMACY_DEV_MODE"] = "1"

    # Ensure the archive package is importable.
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    import database  # noqa: F401
    import db  # noqa: F401
    database.init_db()
    db.init_db()


def _cleanup():
    """Release the ORM engine lock, then delete the temp DB and its WAL sidecars."""
    try:
        import db
        db.reconnect_db()  # disposes the engine, releasing the file handle
    except Exception:
        pass
    if _DB_PATH:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(_DB_PATH + suffix)
            except OSError:
                pass


_ensure_fixture()
atexit.register(_cleanup)


def reset_db_fixture() -> None:
    """Re-initialize both backends against the same isolated temp DB."""
    import database
    import db
    database.init_db()
    db.init_db()


def get_db_path() -> str:
    return _DB_PATH or os.environ.get("PHARMACY_DB_PATH", "")


def get_config_dir() -> str:
    return _CONFIG_DIR or os.environ.get("PHARMACY_CONFIG_DIR", "")
