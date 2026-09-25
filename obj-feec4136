"""FastAPI application entrypoint: CORS, uniform error contract, routers, lifespan."""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError
from app.api.routers.admin_route import router as admin_router
from app.api.routers.integrations_route import router as integrations_router
from app.api.routers.auth_route import router as auth_router
from app.api.routers.audit_route import router as audit_router
from app.api.routers.dictionaries_route import router as dictionaries_router
from app.api.routers.dispense_route import router as dispense_router
from app.api.routers.drug_confirm_route import router as drug_confirm_router
from app.api.routers.email_route import router as email_router
from app.api.routers.health_route import router as health_router
from app.api.routers.inventory_route import router as inventory_router
from app.api.routers.analytics_route import router as analytics_router
from app.api.routers.dashboard_route import router as dashboard_router
from app.api.routers.insurance_route import router as insurance_router
from app.api.routers.members_route import router as members_router
from app.api.routers.patients_route import router as patients_router
from app.api.routers.mobile_route import router as mobile_router
from app.api.routers.pos_route import router as pos_router
from app.api.routers.prescriber_route import router as prescriber_router
from app.api.routers.region_route import router as region_router
from app.api.routers.region_strategy_route import router as region_strategy_router
from app.api.routers.prior_auth_route import router as prior_auth_router
from app.api.routers.epcs_route import router as epcs_router
from app.api.routers.compound_route import router as compound_router
from app.api.routers.clinical_route import router as clinical_router
from app.api.routers.roles_route import router as roles_router
from app.api.routers.rx_queue_route import router as rx_queue_router
from app.api.routers.settings_route import router as settings_router
from app.api.routers.setup_route import router as setup_router
from app.api.routers.support_route import router as support_router
from app.api.routers.support_fix_route import router as support_fix_router
from app.api.routers.sync_route import router as sync_router
from app.api.routers.users_route import router as users_router
from app.api.routers.ocr_route import router as ocr_router
from app.api.routers.excel_route import router as excel_router
from app.api.routers.vendors_route import router as vendors_router
from app.api.routers.wc_route import router as wc_router
from app.core import database
from app.core.database import create_schema, init_engine
from app.core.backup import vacuum_backup
from app.services.seed_service import seed_admin_if_absent, seed_admin_role, seed_clinical_defaults, seed_default_locked_features, seed_drug_dictionary, seed_session_settings, seed_product_templates, seed_default_settings
from app.shared.config import settings
from app.shared.logging_config import configure_logging, get_logger

# Import models at module level so Base.metadata is populated for create_schema()
import app.core.models  # noqa: F401

# Initialize structured logging early in the application lifecycle.
logger = get_logger("app")
configure_logging(debug=settings.debug)
from app.shared.exceptions import AppException
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
            await seed_admin_role(session)
            await seed_admin_if_absent(session)
            await seed_clinical_defaults(session)
            await seed_default_locked_features(session)
            await seed_drug_dictionary(session)
            await seed_session_settings(session)
            await seed_product_templates(session)
            await seed_default_settings(session)
            from app.services.receipt_template_service import ReceiptTemplateService
            await ReceiptTemplateService(session).seed_defaults()
            await session.commit()
        except Exception:  # noqa: BLE001 — seed failure must never block startup
            logger.error("seed_lifespan_error", exc_info=True)
    logger.info("startup_complete", database=settings.database_url)

    async def _snapshot_loop() -> None:
        while True:
            await asyncio.sleep(_SNAPSHOT_INTERVAL_SECONDS)
            try:
                dest = await vacuum_backup()
                if dest:
                    logger.info("snapshot_written", path=dest)
            except Exception:  # noqa: BLE001 - snapshot must never crash the app
                logger.warning("snapshot_failed", exc_info=True)

    async def _alert_loop() -> None:
        """Periodic alert check — logs low-stock and expiry counts every 30 minutes."""
        _ALERT_INTERVAL = 30 * 60
        await asyncio.sleep(60)
        while True:
            await asyncio.sleep(_ALERT_INTERVAL)
            try:
                async with database._sessionmaker() as session:
                    from datetime import timedelta as _td
                    from sqlalchemy import text as _text
                    now = datetime.now(timezone.utc)
                    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    cutoff_30 = (today + _td(days=30)).isoformat()
                    today_str = today.isoformat()
                    r = await session.execute(
                        _text("SELECT COUNT(*) FROM inventory_extended WHERE expiration_date < :today AND on_hand > 0"),
                        {"today": today_str},
                    )
                    expired = r.scalar() or 0
                    r = await session.execute(
                        _text("SELECT COUNT(*) FROM inventory_extended WHERE expiration_date >= :today AND expiration_date <= :cutoff AND on_hand > 0"),
                        {"today": today_str, "cutoff": cutoff_30},
                    )
                    critical = r.scalar() or 0
                    r = await session.execute(
                        _text("SELECT COUNT(*) FROM products p JOIN inventory_extended ie ON ie.drug_name = p.name WHERE (p.deleted = 0 OR p.deleted IS NULL) AND p.reorder_threshold IS NOT NULL AND p.reorder_threshold > 0 AND ie.on_hand <= p.reorder_threshold"),
                    )
                    low_stock = r.scalar() or 0
                    if expired or critical or low_stock:
                        logger.warning(
                            "alert_summary",
                            expired=expired,
                            critical_30d=critical,
                            low_stock=low_stock,
                        )
            except Exception:  # noqa: BLE001
                logger.warning("alert_check_failed", exc_info=True)

    snapshot_task = asyncio.create_task(_snapshot_loop())
    alert_task = asyncio.create_task(_alert_loop())
    try:
        yield
    finally:
        snapshot_task.cancel()
        alert_task.cancel()


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
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # LAN access — allow local subnet origins for mobile companion app
        "http://192.168.0.0/16",
        "http://10.0.0.0/8",
        "http://172.16.0.0/12",
        # Expo dev server origins
        "exp://192.168.*.*:*",
        "exp://10.*.*.*:*",
        "exp://172.16.*.*:*",
    ],
    allow_origin_regex=r"^https?://(192\.168|10\.|172\.(1[6-9]|2[0-9]|3[0-1]))\.\d{1,3}\.\d{1,3}(:\d+)?$",
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

# Register all routers with the FastAPI app
app.include_router(admin_router)
# Additional routers
app.include_router(integrations_router)
app.include_router(auth_router)
app.include_router(audit_router)
app.include_router(dictionaries_router)
app.include_router(dispense_router)
app.include_router(drug_confirm_router)
app.include_router(email_router)
app.include_router(health_router)
app.include_router(inventory_router)
app.include_router(analytics_router)
app.include_router(dashboard_router)
app.include_router(insurance_router)
app.include_router(members_router)
app.include_router(patients_router)
app.include_router(mobile_router)
app.include_router(pos_router)
app.include_router(prescriber_router)
app.include_router(region_router)
app.include_router(region_strategy_router)
app.include_router(prior_auth_router)
app.include_router(epcs_router)
app.include_router(compound_router)
app.include_router(clinical_router)
app.include_router(roles_router)
app.include_router(rx_queue_router)
app.include_router(settings_router)
app.include_router(support_router)
app.include_router(support_fix_router)
app.include_router(sync_router)
app.include_router(setup_router)
app.include_router(users_router)
app.include_router(ocr_router)
app.include_router(excel_router)
app.include_router(vendors_router)
app.include_router(wc_router)
# Additional routers
from app.api.routers.coupon_route import router as coupon_router
app.include_router(coupon_router)

from app.api.routers.receiving_route import router as receiving_router
app.include_router(receiving_router)

from app.api.routers.crash_report_route import router as crash_report_router
app.include_router(crash_report_router)

from app.api.routers.quick_sig_route import router as quick_sig_router
app.include_router(quick_sig_router)

from app.api.routers.po_route import router as po_router
app.include_router(po_router)

from app.api.routers.receipt_template_route import router as receipt_template_router
from app.api.routers.receipt_route import router as receipt_router
app.include_router(receipt_template_router)
app.include_router(receipt_router)

from app.api.routers.drug_interaction_route import router as drug_interaction_router
app.include_router(drug_interaction_router)

from app.api.routers.invoice_parse_route import router as invoice_parse_router
app.include_router(invoice_parse_router)

from app.api.routers.label_template_route import router as label_template_router
from app.api.routers.label_template_route import product_router as product_label_router
from app.api.routers.label_assignment_route import router as label_assignment_router
from app.api.routers.barcode_route import router as barcode_router
app.include_router(label_template_router)
app.include_router(product_label_router)
app.include_router(label_assignment_router)
app.include_router(barcode_router)

from app.api.routers.version_route import router as version_router
app.include_router(version_router)

from app.api.routers.templates_route import router as templates_router
app.include_router(templates_router)

from app.api.routers.gift_card_route import router as gift_card_router
app.include_router(gift_card_router)

from app.api.routers.patient_fields_route import router as patient_fields_router
