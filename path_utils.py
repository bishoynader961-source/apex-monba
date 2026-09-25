import sys
import os


def get_resource_path(relative_path: str) -> str:
    """Resolve a path relative to the application root.

    When running as a compiled PyInstaller executable, files are extracted
    to a temporary directory accessible via ``sys._MEIPASS``.  This helper
    transparently returns the correct absolute path in both scenarios.

    Args:
        relative_path: Path relative to the archive/ directory
                       (e.g. ``"config.json"`` or ``"receipts"``).

    Returns:
        Absolute path string.
    """
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


def ensure_runtime_directories():
    """Create all runtime directories that the application expects.

    Called once at startup before any file I/O.  Safe to call multiple
    times (no-op if directories already exist).
    """
    dirs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "labels"),
    ]
    for d in dirs:
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)


def get_writable_config_path() -> str:
    """Resolve the writable user-config path (safe under PyInstaller).

    When frozen, the shipped config lives in the read-only ``sys._MEIPASS``
    extraction dir.  User state must therefore live outside it.  Resolution:
        1. ``PHARMACY_CONFIG_DIR`` env var (used by tests / CI for isolation)
        2. ``%LOCALAPPDATA%/PharmacyPro`` (Windows) or ``~/.config/PharmacyPro``
    The directory is created if missing.
    """
    env = os.environ.get("PHARMACY_CONFIG_DIR")
    if env:
        base = env
    else:
        if sys.platform == "win32":
            base = os.environ.get(
                "LOCALAPPDATA",
                os.path.join(os.path.expanduser("~"), "AppData", "Local"),
            )
            base = os.path.join(base, "PharmacyPro")
        else:
            base = os.path.join(os.path.expanduser("~"), ".config", "PharmacyPro")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "config.json")
