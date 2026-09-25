"""Structured JSON logging via structlog + rotating file handler (Spec 09 Pt 1).

Console keeps the JSON output; a ``RotatingFileHandler`` additionally writes
``backend.log`` next to the database (per-install data dir) with:
  - 5 MB per file
  - 3 backup files kept (backend.log.1 … backend.log.3)

Buyers can grab these files and attach them to a support email without any
technical steps.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog

_LOG_FILE_NAME = "backend.log"
_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_LOG_BACKUP_COUNT = 3

_file_handler: logging.handlers.RotatingFileHandler | None = None


def _build_file_handler(log_dir: Path) -> logging.handlers.RotatingFileHandler:
    handler = logging.handlers.RotatingFileHandler(
        log_dir / _LOG_FILE_NAME,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.DEBUG)
    return handler


def configure_logging(*, debug: bool = True, log_dir: Path | None = None) -> None:
    """Configure structlog (console JSON) + rotating file logger.

    ``log_dir`` defaults to the per-install app data dir (same place as
    ``pharmacy.db``). File logging is best-effort: if the directory is
    read-only the app still starts, just console-only.
    """
    root = logging.getLogger()
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    global _file_handler
    if _file_handler is None:
        try:
            if log_dir is None:
                from app.shared.config import get_app_data_dir

                log_dir = get_app_data_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            _file_handler = _build_file_handler(log_dir)
            root.addHandler(_file_handler)
        except OSError:
            _file_handler = None  # read-only dir — console-only logging

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_log_file_path() -> Path | None:
    """Where backend.log lives (for the Support tab 'locate logs' hint)."""
    if _file_handler is None:
        return None
    return Path(_file_handler.baseFilename)


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
