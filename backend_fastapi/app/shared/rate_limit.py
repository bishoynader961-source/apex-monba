"""Rate limiting (slowapi) for auth endpoints.

Provides a module-level ``limiter`` singleton and a custom
``RateLimitExceeded`` handler that renders the app's uniform error contract
``{"error": {"code", "message", "details"}}`` instead of slowapi's default
``{"error": "..."}`` shape.

Storage is in-memory (single-process kiosk deployment). The limiter is wired
into the FastAPI app in ``app/main.py`` via ``app.state.limiter`` + the
exception handler. ``SlowAPIMiddleware`` is intentionally NOT registered: the
``@limiter.limit`` decorator enforces route limits in-process, and the
``async_wrapper``'s post-endpoint ``_inject_headers`` call is incompatible with
FastAPI Pydantic-model responses (it expects a ``Response`` instance).
``headers_enabled=False`` makes ``_inject_headers`` a no-op so the decorator
safely returns the model for FastAPI's normal serialization.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.shared.config import settings
from app.shared.logging_config import get_logger

logger = get_logger("rate_limit")

DEFAULT_AUTH_LIMIT = "5/minute"
DEFAULT_PIN_LIMIT = "5/minute"


def _build_limiter() -> Limiter:
    """Create the Limiter singleton.

    ``storage_uri=None`` selects the in-memory storage backend (sufficient for
    a single-process kiosk). ``default_limits=[]`` so no global default applies;
    each route opts in via ``@limiter.limit(...)``. ``headers_enabled=False``
    avoids slowapi's ``_inject_headers`` no-op issue with FastAPI's model
    responses (see module docstring).
    """
    return Limiter(
        key_func=get_remote_address,
        default_limits=[],
        storage_uri=None,
        headers_enabled=False,
    )


limiter: Limiter = _build_limiter()


def rate_limit_exceeded_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Custom handler: renders the app error contract on 429 responses.

    Preserves the ``Retry-After`` value from the slowapi exception detail so
    clients know when to retry. Typed as ``Exception`` to satisfy Starlette's
    ``add_exception_handler`` signature; the runtime value is always
    ``RateLimitExceeded``.
    """
    headers = getattr(exc, "headers", None) or {}
    retry_after = headers.get("Retry-After", "") if hasattr(headers, "get") else ""
    details: dict[str, Any] = {}
    if retry_after:
        details["retry_after"] = retry_after
    detail = getattr(exc, "detail", str(exc))
    logger.warning("rate_limit_exceeded", detail=str(detail), retry_after=retry_after)
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": "Too many requests",
                "details": details,
            }
        },
    )


def get_auth_limit() -> str:
    """Return the auth login rate limit string from settings (env-configurable)."""
    return getattr(settings, "auth_rate_limit", DEFAULT_AUTH_LIMIT) or DEFAULT_AUTH_LIMIT


def get_pin_limit() -> str:
    """Return the PIN login rate limit string from settings (env-configurable)."""
    return getattr(settings, "pin_rate_limit", DEFAULT_PIN_LIMIT) or DEFAULT_PIN_LIMIT
