"""FastAPI application entrypoint: CORS, uniform error contract, routers, lifespan."""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError

from app.api.routers.admin_route import router as admin_router
from app.api.routers.auth_route import router as auth_router
from app.api.routers.audit_route import router as audit_router
from app.api.routers.dictionaries_route import router as dictionaries_router
from app.api.routers.dispense_route import router as dispense_router
from app.api.routers.health_route import router as health_router
from app.api.routers.inventory_route import router as inventory_router
from app.api.routers.analytics_route import router as analytics_router
from app.api.routers.insurance_route import router as insurance_router
from app.api.routers.license_route import router as license_router
from app.api.routers.license_file_route import router as license_file_router
from app.api.routers.members_route import router as members_router
from app.api.routers.patients_route import router as patients_router
from app.api.routers.pos_route import router as pos_router
from app.api.routers.settings_route import router as settings_router
from app.api.routers.sync_route import router as sync_router
from app.api.routers.users_route import router as users_router
from app.api.routers.webhook_route import router as webhook_router
from app.core import database
from app.core.database import create_schema, init_engine, vacuum_snapshot
from app.services.seed_service import seed_admin_if_absent, seed_clinical_defaults
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

# Paths serving interactive API documentation or locally-vendored doc assets.
# These need a relaxed CSP so the Swagger UI / ReDoc JS + CSS can execute.
_DOCS_PATHS = ("/docs", "/redoc", "/static", "/openapi.json")

_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_engine(settings.database_url)
    await create_schema()
    assert database._sessionmaker is not None
    async with database._sessionmaker() as session:
        try:
            await seed_admin_if_absent(session)
            await seed_clinical_defaults(session)
        except Exception:  # noqa: BLE001 — seed failure must never block startup
            logger.error("seed_lifespan_error", exc_info=True)
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


app = FastAPI(
    title="Pharmacy Suite API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    swagger_ui_oauth2_redirect_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/docs", include_in_schema=False)
async def swagger_ui_html(req: Request) -> HTMLResponse:
    root_path = req.scope.get("root_path", "").rstrip("/")
    openapi_url = root_path + app.openapi_url
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="/static/swagger-ui/favicon-32x32.png",
        swagger_ui_parameters=app.swagger_ui_parameters,
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html(req: Request) -> HTMLResponse:
    root_path = req.scope.get("root_path", "").rstrip("/")
    openapi_url = root_path + app.openapi_url
    return get_redoc_html(
        openapi_url=openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_js_url="/static/redoc/redoc.standalone.js",
        with_google_fonts=False,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        if header == "Content-Security-Policy" and request.url.path.startswith(_DOCS_PATHS):
            response.headers.setdefault("Content-Security-Policy", _DOCS_CSP)
        else:
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
        content=jsonable_encoder(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
                }
            }
        ),
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
app.include_router(analytics_router)
app.include_router(insurance_router)
app.include_router(license_router)
app.include_router(license_file_router)
app.include_router(members_router)
app.include_router(patients_router)
app.include_router(pos_router)
app.include_router(dictionaries_router)
app.include_router(dispense_router)
app.include_router(settings_router)
app.include_router(sync_router)
app.include_router(users_router)
app.include_router(webhook_router)
app.include_router(admin_router)
