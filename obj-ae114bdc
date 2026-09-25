# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the Pharmacy Suite FastAPI backend sidecar.

Produces a single standalone Windows executable (``backend.exe``) that bundles
Uvicorn + the FastAPI ``app`` object so Tauri can run it as a sidecar without a
system Python install. After building, rename the output to
``backend-x86_64-pc-windows-msvc.exe`` and drop it in ``src-tauri/binaries/``.
"""
from __future__ import annotations

import os

import sqlalchemy  # ensure the package (and its greenlet/aiosqlite deps) are collected

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
BACKEND_DIR = SPEC_DIR  # this spec lives inside backend_fastapi/

# App source + the active virtualenv site-packages so third-party imports resolve.
pathex = [BACKEND_DIR]

# Statically-imported app subpackages are auto-collected, but the entries below
# cover anything reached lazily or via string-based imports (the classic
# ModuleNotFoundError-at-runtime freeze gotcha).
hiddenimports = [
    "app",
    "app.main",
    "app.api",
    "app.api.routers",
    "app.api.routers.admin_route",
    "app.api.routers.auth_route",
    "app.api.routers.audit_route",
    "app.api.routers.dictionaries_route",
    "app.api.routers.dispense_route",
    "app.api.routers.health_route",
    "app.api.routers.inventory_route",
    "app.api.routers.analytics_route",
    "app.api.routers.insurance_route",
    "app.api.routers.license_route",
    "app.api.routers.license_file_route",
    "app.api.routers.members_route",
    "app.api.routers.patients_route",
    "app.api.routers.pos_route",
    "app.api.routers.settings_route",
    "app.api.routers.support_route",
    "app.api.routers.sync_route",
    "app.api.routers.users_route",
    "app.api.routers.roles_route",
    "app.api.routers.prescriber_route",
    "app.api.routers.wc_route",
    "app.api.routers.email_route",
    "app.api.routers.webhook_route",
    "app.api.routers.admin_route",
    "app.core",
    "app.core.audit_log",
    "app.core.backup",
    "app.core.database",
    "app.core.lock_manager",
    "app.core.models",
    "app.core.repositories",
    "app.services",
    "app.services.seed_service",
    "app.services.dispense_service",
    "app.services.insurance_service",
    "app.services.email_service",
    "app.services.drug_db",
    "app.services.demand_analytics_service",
    "app.services.movement_service",
    "app.services.patient_service",
    "app.services.ota_service",
    "app.services.receipt_engine",
    "app.services.sync_service",
    "app.services.dictionary_service",
    "app.shared",
    "app.shared.config",
    "app.shared.exceptions",
    "app.shared.logging_config",
    "app.shared.rate_limit",
    "app.shared.security",
    "app.shared.schemas",
    "fastapi",
    "fastapi.middleware.cors",
    "starlette",
    "starlette.staticfiles",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.workers",
    "uvicorn.workers.uvicorn",
    "sqlalchemy",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.dialects.sqlite",
    "aiosqlite",
    "greenlet",
    "pydantic",
    "pydantic_settings",
    "email_validator",
    "bcrypt",
    "jwt",
    "structlog",
    "slowapi",
    "limits",
    "limits.strategies",
    "multipart",
    "python_multipart",
    "anyio",
    "anyio.to_thread",
    "anyio.lowlevel",
    "httpx",
    "jinja2",
    "openpyxl",
]

# Swagger/ReDoc assets are served from app/static via StaticFiles at runtime, so
# the directory must be extracted next to the frozen modules (the import-time
# ``os.path.join(os.path.dirname(__file__), "static")`` resolves under _MEIPASS).
datas = [
    (os.path.join(BACKEND_DIR, "app", "static"), "app/static"),
]

a = Analysis(
    [os.path.join(BACKEND_DIR, "run_backend.py")],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "matplotlib",
        "asyncpg",  # optional Postgres driver; desktop build uses SQLite only
        "pytest",
        "mypy",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
