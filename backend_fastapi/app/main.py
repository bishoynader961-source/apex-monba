"""FastAPI application entrypoint: CORS, uniform error contract, routers, lifespan."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError

from app.api.routers.auth_route import router as auth_router
from app.api.routers.audit_route import router as audit_router
from app.api.routers.health_route import router as health_router
from app.api.routers.inventory_route import router as inventory_router
from app.api.routers.license_route import router as license_router
from app.api.routers.pos_route import router as pos_router
from app.api.routers.settings_route import router as settings_router
from app.api.routers.sync_route import router as sync_router
from app.api.routers.users_route import router as users_router
from app.core import database
from app.core.database import create_schema, init_engine, vacuum_snapshot
from app.services.seed_service import seed_admin_if_absent
from app.shared.config import settings
from app.shared.exceptions import AppException
from app.shared.logging_config import configure_logging, get_logger
from app.shared.rate_limit import limiter, rate_limit_exceeded_handler

# Periodic cold VACUUM snapshot interval (§13 resilience). 6h.
_SNAPSHOT_INTERVAL_SECONDS = 6 * 60 * 60

configure_logging(debug=settings.debug)
logger = get_logger("fastapi")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_engine(settings.database_url)
    await create_schema()
    assert database._sessionmaker is not None
    async with database._sessionmaker() as session:
        try:
            await seed_admin_if_absent(session)
        except Exception:  # noqa: BLE001 — seed failure must never block startup
            logger.error("seed_admin_lifespan_error", exc_info=True)
    logger.info("startup_complete", database=settings.database_url)

    async def _snapshot_loop() -> None:
        while True:
            await asyncio.sleep(_SNAPSHOT_INTERVAL_SECONDS)
            try:
                dest = await vacuum_snapshot()
                if dest:
                    logger.info("snapshot_written", path=dest)
            except Exception:  # noqa: BLE001 - snapshot must never crash the app
                logger.warning("snapshot_failed", exc_info=True)

    snapshot_task = asyncio.create_task(_snapshot_loop())
    try:
        yield
    finally:
        snapshot_task.cancel()


app = FastAPI(title="Pharmacy Suite API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


@app.exception_handler(AppException)
async def handle_app_exception(_request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.error_code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": exc.errors()},
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def handle_db_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("database_error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "database_error", "message": "Database error", "details": {}}},
    )


@app.exception_handler(Exception)
async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("unexpected_error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "app_error", "message": "Internal server error", "details": {}}},
    )


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(audit_router)
app.include_router(inventory_router)
app.include_router(license_router)
app.include_router(pos_router)
app.include_router(settings_router)
app.include_router(sync_router)
app.include_router(users_router)
