"""Frozen-entry bootstrap for the Pharmacy Suite FastAPI backend.

This module is the PyInstaller entry point. It imports the already-constructed
``app`` object from ``app.main`` and serves it with Uvicorn so the bundled
executable can be launched as a Tauri sidecar without a system Python install.

The host/port default to the loopback addresses used by the Tauri desktop shell
(127.0.0.1:8000); they can be overridden via CLI flags for local debugging.
"""
from __future__ import annotations

import argparse

import uvicorn

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Pharmacy Suite FastAPI backend sidecar")
    parser.add_argument(
        "--host",
        default="0.0.0.0",  # noqa: S104 — binds all interfaces for multi-PC LAN access
        help="Bind host (default: 0.0.0.0 for LAN; use 127.0.0.1 for loopback-only)",
    )
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
