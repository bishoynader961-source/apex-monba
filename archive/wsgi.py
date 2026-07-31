"""
wsgi.py — WSGI entry point for PythonAnywhere production.
"""
import sys
from pathlib import Path

# Add project home to sys.path
_project_home = str(Path(__file__).resolve().parent)
if _project_home not in sys.path:
    sys.path.insert(0, _project_home)

from server_app import app  # noqa: E402
