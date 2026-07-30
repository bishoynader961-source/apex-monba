"""
wsgi.py — WSGI entry point for production (gunicorn / PythonAnywhere).

Usage:
  gunicorn wsgi:app -b 0.0.0.0:8000 --workers 2

PythonAnywhere:
  1. Go to the Web tab.
  2. Set "WSGI configuration file" to the absolute path of THIS file.
     Example: /home/yourusername/myproject/archive/wsgi.py
  3. In the WSGI config file, ensure the code does:
       import sys
       project_home = '/home/yourusername/myproject/archive'
       if project_home not in sys.path:
           sys.path.insert(0, project_home)
       from license_server import app as application
  4. Reload the web app.
"""
import sys
from pathlib import Path

# Ensure the project directory is on sys.path so `license_server` can be found
_project_home = str(Path(__file__).resolve().parent)
if _project_home not in sys.path:
    sys.path.insert(0, _project_home)

from license_server import app, init_db  # noqa: E402

# Ensure DB tables exist on worker startup
init_db()
