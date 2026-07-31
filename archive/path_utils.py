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
