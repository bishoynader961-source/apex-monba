# Baseline Report: Decoupled Stack Audit

## Executive Summary

The project has migrated from a legacy monolithic Tkinter desktop app (`archive/`) to a **three-service decoupled stack** orchestrated by `run_services.py`:

| Service | Port | Tech | Repo Path |
|---|---|---|---|
| Flask license microservice | 5000 | Flask + SQLite | `backend/` |
| FastAPI pharmacy API | 8000 | FastAPI + SQLAlchemy 2.0 + async SQLite | `backend_fastapi/` |
| Next.js frontend | 3000 | Next.js 16 + React 19 + Zustand 4 | project root |
| Tauri shell (desktop wrapper) | — | Rust/Tauri 2 | `src-tauri/` |

The **FastAPI backend** (`backend_fastapi/`) is a stateless, async Python 3.12 service with 48 router modules, 28 ORM models, 87 Pydantic schemas, and a versioned SQLite migration system (v1–v22). The **Next.js frontend** has 32+ routes, 40+ React components, 25+ typed API client modules, 13 Zustand stores, and 20 hooks, with CSS-in-JS design tokens defined in `globals.css` and `DESIGN_SYSTEM.md`.

---

## 1. Backend Architecture (FastAPI + SQLite)

### 1.1 Project Metadata

| Field | Value |
|---|---|
| Package name | `pharmacy-fastapi` (v1.0.0) |
| Python | >=3.12 |
| Framework | FastAPI >=0.115 |
| ORM | SQLAlchemy 2.0 async (`aiosqlite` for SQLite, `asyncpg` for PostgreSQL) |
| Schema version | 22 (`SCHEMA_VERSION = 22`) |
| Auth | JWT bearer tokens + PIN login (bcrypt/PBKDF2 peppered) |
| Rate limiting | `slowapi` / `limits` (auth & PIN endpoints) |
| Logging | `structlog` async logging |
| Tests | pytest >=9 + pytest-asyncio (mypy strict mode) |
| Coverage gate | `fail_under = 90` |

### 1.2 Dependency List (`backend_fastapi/pyproject.toml`)

**Runtime:** fastapi, httpx, uvicorn, sqlalchemy, aiosqlite, asyncpg, pydantic, pydantic-settings, bcrypt, pyjwt, python-dotenv, structlog, slowapi, limits, pillow, pytesseract

**Dev:** pytest>=9.0.3, pytest-asyncio>=1.3.0, pytest-cov>=5.0, mypy>=1.10 (strict)

### 1.3 Application Structure

```
backend_fastapi/
├── app/
│   ├── main.py                    — FastAPI app: CORS, middleware, routers, lifespan, exception handlers
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py               — get_current_user, require_permission, require_approval_token
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── 48 router files (see §1.5)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py           — async engine, sessions, migrations (v1–v22)
│   │   ├── models.py             — 28 ORM models (SQLAlchemy 2.0 async)
│   │   ├── repositories.py        — 17 repository classes
│   │   ├── lock_manager.py        — async file locks (T1.5)
│   │   ├── backup.py             — backup/restore logic
│   │   └── audit_log.py          — tamper-evident audit hash chain
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── inventory_service.py
│   │   ├── pos_service.py
│   │   ├── patient_service.py
│   │   ├── dispense_service.py
│   │   ├── insurance_service.py
│   │   ├── receipt_engine.py
│   │   ├── sync_service.py
│   │   ├── seed_service.py
│   │   ├── ota_service.py
│   │   ├── drug_db.py
│   │   ├── drug_interaction_service.py
│   │   ├── drug_confirmation_service.py
│   │   ├── smart_parser.py
│   │   ├── ocr_cascade.py
│   │   ├── movement_service.py
│   │   ├── label_template_service.py
│   │   ├── region_strategy_service.py
│   │   ├── region_service.py
│   │   ├── quick_sig_service.py
│   │   ├── po_service.py
│   │   ├── coupon_service.py
│   │   ├── email_service.py
│   │   ├── compound_service.py
│   │   └── demand_analytics_service.py
│   └── shared/
│       ├── __init__.py
│       ├── config.py             — Pydantic BaseSettings (env-driven, alias-mapped)
│       ├── schemas.py            — 87 Pydantic v2 schemas (2061 lines)
│       ├── security.py           — JWT, bcrypt, PBKDF2 PIN hashing, pepper rotation
│       ├── exceptions.py         — AppException, ForbiddenError, NotFoundError, etc.
│       ├── rate_limit.py         — slowapi limiter + error handler
│       └── logging_config.py     — structlog async logger
├── tests/
│   ├── conftest.py
│   └── 35 test files
└── run_backend.py
```

### 1.4 Database Configuration (`config.py`)

| Setting | Env Var | Default |
|---|---|---|
| `app_env` | `APP_ENV` | `development` |
| `database_url` | `PHARMACY_DB_URL` | `sqlite+aiosqlite:///./pharmacy.db` |
| `secret_key` | `SECRET_KEY` | `replace-with-...` (must change in production) |
| `access_token_expire_minutes` | `ACCESS_TOKEN_EXPIRE_MINUTES` | 480 (8h) |
| `refresh_token_expire_days` | `REFRESH_TOKEN_EXPIRE_DAYS` | 30 |
| `license_gate_url` | `LICENSE_GATE_URL` | `http://localhost:5000` |
| `pin_kdf_iters` | `POS_PIN_KDF_ITERS` | 200_000 |
| `pin_lockout_attempts` | `POS_PIN_LOCKOUT_ATTEMPTS` | 5 |
| `pin_lockout_minutes` | `POS_PIN_LOCKOUT_MINUTES` | 15 |
| `pepper_backend` | `POS_PEPPER_BACKEND` | `dpapi-local-machine` |
| `auth_rate_limit` | `POS_AUTH_RATE_LIMIT` | `5/minute` |
| `multi_terminal` | `POS_MULTI_TERMINAL` | `false` |
| `device_id` | `POS_DEVICE_ID` | auto-generated (persists to `.pharmacy_device_id`) |
| `fastapi_port` | `FASTAPI_PORT` | 8000 |
| `tax_rate` | `TAX_RATE` | 0.14 (14%) |
| `creem_api_key` | `CREEM_API_KEY` | (empty) |
| `creem_webhook_secret` | `CREEM_WEBHOOK_SECRET` | (empty) |
| `license_offline_grace_hours` | `LICENSE_OFFLINE_GRACE_HOURS` | 72 |

**Production validation:** If `APP_ENV=production` and `SECRET_KEY` equals the default placeholder, startup raises `ValueError`.

### 1.5 All Registered API Endpoints (48 routers)

All endpoints are mounted under `/api/v1/` unless noted. RBAC permissions listed in `[brackets]`.

| Router File | Prefix | Endpoints |
|---|---|---|
| **health_route.py** | `/api/v1` | `GET /health` → `HealthResponse` [no auth] |
| **auth_route.py** | `/api/v1/auth` | `POST /login` (Token) [rate-limited]<br>`POST /login/pin` (Token) [rate-limited]<br>`POST /pin` [perm: users.write]<br>`POST /refresh` (Token)<br>`POST /register` (UserPublic, 201) [perm: users.write]<br>`GET /me` (CurrentUser) [bearer]<br>`POST /logout`<br>`POST /rotate-pepper` [perm: pos.pepper.rotate] |
| **admin_route.py** | `/api/v1/admin` | `POST /backup` (BackupResult, 201) [perm: backup.create]<br>`GET /backups` [perm: backup.create]<br>`POST /restore` (UploadFile) [perm: backup.create] |
| **users_route.py** | `/api/v1/users` | `GET /` (list[UserPublic]) [perm: users.read]<br>`GET /{id}` [perm: users.read]<br>`PUT /{id}` (UserUpdate→UserPublic) [perm: users.write]<br>`PATCH /{id}/active` [perm: users.write] |
| **inventory_route.py** | `/api/v1/inventory` | `GET /medicines` (PaginatedProducts, query: page, page_size, q, vendor, status, low_stock_only) [perm: inventory.read]<br>`GET /medicines/search?q=` [perm: inventory.read]<br>`GET /medicines/{id}` [perm: inventory.read]<br>`POST /medicines` (ProductCreate→ProductRead, 201) [perm: inventory.write]<br>`PUT /medicines/{id}` (MedicineUpdate→ProductRead) [perm: inventory.write]<br>`DELETE /medicines/{id}` [perm: inventory.write]<br>`GET /batches` (query: product_name, supplier) [perm: inventory.read]<br>`POST /batches/receive` (ReceiveBatch→BatchRead, 201) [perm: inventory.write]<br>`GET /batches/low-stock` [perm: inventory.read]<br>`GET /batches/expiring-soon?days=90` [perm: inventory.read]<br>`GET /batches/{id}` [perm: inventory.read]<br>`PUT /batches/{id}` (BatchUpdate→BatchRead) [perm: inventory.write]<br>`GET /stock-levels` (query: low_stock_only, expiring_days) [perm: inventory.read]<br>`GET /suppliers` [perm: inventory.read]<br>`POST /suppliers` (SupplierCreate→SupplierRead, 201) [perm: inventory.write]<br>`GET /movements` (query: product_id, batch_number, movement_type, start_date, end_date, page, limit) [perm: inventory.read]<br>`POST /adjustments` (query: product_id, quantity_change, reason) [perm: inventory.write] |
| **pos_route.py** | `/api/v1/pos` | `POST /approve` (ApprovalRequest) [no RBAC, rate-limited]<br>`POST /checkout` (CheckoutRequest→CheckoutResult, 201) [perm: pos.checkout]<br>`POST /drawer/movement` (DrawerMovementCreate+X-Approval-Token→DrawerMovementRead, 201) [perm: pos.drawer]<br>`POST /shift/open` (ShiftOpenRequest→ShiftRead, 201) [perm: pos.drawer]<br>`POST /shift/close` (ShiftCloseRequest→ShiftCloseResult) [perm: pos.drawer]<br>`GET /shift/{id}/preview` (ShiftPreviewResult) [perm: pos.drawer]<br>`POST /refund` (RefundRequest→RefundRead) [perm: pos.checkout]<br>`GET /reports/sales` (SalesReport) [perm: inventory.reports]<br>`GET /receipts/recent?limit=50` (list[ReceiptRead]) [perm: pos.checkout]<br>`GET /receipts/{id}` [perm: pos.checkout]<br>`GET /receipts/{id}/print` (ReceiptPrintResponse) [perm: pos.checkout]<br>`GET /eod-summary?date=` (EODSummary) [perm: pos.checkout]<br>`POST /void-item` (VoidItemRequest→VoidItemResult) [perm: pos.void_item] |
| **patients_route.py** | `/api/v1/patients` | `GET /` (query: page, page_size, q→PaginatedPatients) [perm: patients.read]<br>`GET /search?q=` [perm: patients.read]<br>`GET /{id}` [perm: patients.read]<br>`POST /` (PatientCreate→PatientRead, 201) [perm: patients.write]<br>`PUT /{id}` (PatientUpdate→PatientRead) [perm: patients.write]<br>`POST /{id}/insurance` (InsuranceBindRequest→PatientRead) [perm: patients.write]<br>`DELETE /{id}` [perm: patients.delete]<br>`GET /{id}/dispenses` [perm: patients.read]<br>`GET /{id}/history?limit=100` [perm: patients.read] |
| **prescriber_route.py** | `/api/v1/prescribers` | `GET /` (query: page, page_size, search) [perm: patients.read]<br>`GET /{id}` [perm: patients.read]<br>`POST /` (PrescriberCreate→PrescriberRead, 201) [perm: patients.write]<br>`PUT /{id}` [perm: patients.write]<br>`DELETE /{id}` [perm: patients.write] |
| **insurance_route.py** | `/api/v1/insurance` | `GET /plans` [perm: insurance.read]<br>`GET /plans/{id}` [perm: insurance.read]<br>`POST /plans` (InsurancePlanCreate→InsurancePlanRead, 201) [perm: insurance.write]<br>`PUT /plans/{id}` [perm: insurance.write]<br>`DELETE /plans/{id}` [perm: insurance.write]<br>`POST /plans/validate` (InsuranceValidateRequest→InsuranceValidationResult) [perm: insurance.read]<br>`POST /eligibility` (EligibilityRequest→EligibilityCheckResult) [perm: insurance.read] |
| **dispense_route.py** | `/api/v1/dispense` | `POST /` (DispenseCreate→DispenseRead, 201) [perm: dispense.create]<br>`GET /rx/{rx_number}` [perm: patients.read]<br>`GET /rx/{rx_number}/fills` [perm: patients.read]<br>`PUT /{id}` (DispenseUpdate→DispenseRead) [perm: dispense.create]<br>`POST /{id}/reverse` (VoidRequest→VoidResult) [perm: dispense.create]<br>`POST /{id}/transfer` (TransferRequest→TransferResult) [perm: dispense.create]<br>`GET /{id}` [perm: patients.read]<br>`GET /{id}/label` (octet-stream ESC/POS) [perm: patients.read]<br>`POST /{id}/refill` (DispenseCreate→DispenseRead, 201) [perm: dispense.create] |
| **audit_route.py** | `/api/v1/audit` | `GET /verify` (AuditVerifyResult) [perm: inventory.read]<br>`GET /export?fmt=json&limit=1000` (Response) [perm: inventory.read] |
| **dashboard_route.py** | `/api/v1/dashboard` | `GET /metrics` (dict[str,Any]) [perm: inventory.read] |
| **analytics_route.py** | `/api/v1/analytics` | `GET /demand` (query: start_date, end_date, category, min_sales, sort_by, lead_time_days→DemandAnalyticsSummary) [perm: analytics.read]<br>`GET /top-selling` (query: period, start_date, end_date, limit→TopSellingResponse) [perm: analytics.read] |
| **region_route.py** | `/api/v1/region` | `GET /detect` (header X-Vercel-Ip-Country) [bearer]<br>`GET /regions` [bearer]<br>`GET /{code}` [bearer] |
| **region_strategy_route.py** | `/api/v1/region-strategy` | `POST /patient-cost` (PatientCostRequest→PatientCostResult) [perm: insurance.read]<br>`POST /generate-claim` (ClaimGenerationRequest→ClaimGenerationResult) [perm: insurance.write]<br>`POST /validate-prescription` (PrescriptionValidationRequest→...) [perm: dispense.create]<br>`POST /validate-credentials` (CredentialValidationRequest→...) [perm: settings.manage]<br>`GET /supported-regions` (list[str]) [perm: insurance.read] |
| **settings_route.py** | `/api/v1/settings` | `GET /` (list[SystemSettingRead]) [perm: inventory.read]<br>`GET /{key}` [perm: inventory.read]<br>`PUT /{key}` (SettingUpdate→SystemSettingRead) [perm: inventory.write] |
| **roles_route.py** | `/api/v1/roles` | `GET /` (list[RoleRead]) [perm: users.read]<br>`POST /` (RoleCreate→RoleRead, 201) [perm: users.write]<br>`PUT /{id}` (RoleUpdate→RoleRead) [perm: users.write]<br>`GET /{id}/permissions` (list[int]) [perm: users.read]<br>`PUT /{id}/permissions` (RolePermissionUpdate) [perm: users.write]<br>`GET /permissions/all` (list[PermissionRead]) [perm: users.read] |
| **sync_route.py** | `/api/v1/sync` | `POST /push` (SyncPushRequest→SyncPushResult) [gated by multi_terminal setting]<br>`GET /discrepancies?unresolved_only=true` [perm: inventory.read]<br>`POST /discrepancies/{id}/resolve` [perm: inventory.write] |
| **receipt_template_route.py** | `/api/v1/receipt-templates` | `GET /?template_type=` [perm: inventory.write]<br>`GET /default?template_type=receipt` [no RBAC]<br>`GET /{id}` [perm: inventory.write]<br>`POST /` (ReceiptTemplateCreate→ReceiptTemplateRead, 201) [perm: inventory.write]<br>`PUT /{id}` [perm: inventory.write]<br>`DELETE /{id}` (204) [perm: inventory.write] |
| **label_template_route.py** (2 routers) | `/api/v1/label-templates` + `/api/v1/product-labels` | Label Templates: GET/POST/PUT/DELETE [perm: inventory.write]<br>Product Labels: GET/PUT/DELETE by product_id [perm: inventory.write] |
| **webhook_route.py** | `/api/v1/webhook` | `POST /creem` (header: creem-signature, raw JSON body→dict[str,str]) [no auth, HMAC-verified] |
| **wc_route.py** | `/api/v1/wc-claims` | `GET /` (query: patient_id, status, page, page_size) [perm: patients.read]<br>`GET /{id}` [perm: patients.read]<br>`POST /` (WCClaimCreate→WCClaimRead, 201) [perm: patients.write]<br>`PUT /{id}` [perm: patients.write]<br>`DELETE /{id}` (204) [perm: patients.write] |
| **version_route.py** | `/api/v1/version` | `GET /` (VersionInfo) [bearer] |
| **vendors_route.py** | `/api/v1/vendors` | `GET /?active_only=true&q=` [perm: inventory.read]<br>`POST /` (VendorCreate→VendorRead, 201) [perm: inventory.write]<br>`GET /{id}` [perm: inventory.read]<br>`PUT /{id}` [perm: inventory.write]<br>`GET /{id}/items` [perm: inventory.read]<br>`GET /{id}/purchases?limit=50` [perm: inventory.read]<br>`POST /receive` (ReceiveShipmentPayload→dict, 201) [perm: inventory.write] |
| **templates_route.py** | `/api/v1/templates` | `GET /` [perm: inventory.read]<br>`POST /` (TemplateCreate→TemplateRead, 201) [perm: inventory.write]<br>`PUT /{id}` [perm: inventory.write]<br>`DELETE /{id}` (204) [perm: inventory.write] |
| **patient_fields_route.py** | `/api/v1/patients/{patient_id}/fields` | `GET /fields` [no RBAC]<br>`POST /fields` (PatientFieldCreate→PatientFieldRead) [no RBAC]<br>`DELETE /fields/{field_name}` [no RBAC] |
| **ocr_route.py** | `/api/v1/ocr` | `POST /` (file: UploadFile→dict[str,Any]) [bearer] |
| **members_route.py** | `/api/v1/members-groups` | `GET /?patient_id=` [perm: members.read]<br>`GET /{id}` [perm: members.read]<br>`POST /` (MembersGroupCreate→MembersGroupRead, 201) [perm: members.write]<br>`PUT /{id}` [perm: members.write]<br>`DELETE /{id}` [perm: members.write] |
| **license_route.py** | `/api/v1/license` | `POST /validate` (raw JSON: license_key, hardware_id→LicenseValidationResult) [no RBAC]<br>`POST /checkout` (CreemCheckoutRequest→CreemCheckoutResponse, 201) [bearer]<br>`POST /admin/manage` (raw Request) [bearer]<br>`GET /status` [bearer] |
| **license_file_route.py** | `/api/v1/licenses` | `POST /activate-file` (LicenseFileRequest→LicenseValidationResult) [bearer] |
| **invoice_parse_route.py** | `/api/v1/invoice-parse` | `POST /text` (ParseTextRequest→ParseResponse) [perm: inventory.write]<br>`POST /file` (UploadFile→ParseResponse) [perm: inventory.write] |
| **integrations_route.py** | `/api/v1` | `POST /drugs/evaluate` (DrugEvaluateRequest→DrugEvaluateResponse) [perm: inventory.read]<br>`GET /integrations` (list[IntegrationRead]) [perm: settings.read]<br>`POST /integrations` (IntegrationCreate→IntegrationRead, 201) [perm: settings.manage] |
| **gift_card_route.py** | `/api/v1/gift-cards` | `POST /` (GiftCardCreate→GiftCardRead) [no RBAC]<br>`GET /?status=` [no RBAC]<br>`GET /lookup/{code}` [no RBAC]<br>`POST /{id}/redeem` [no RBAC]<br>`POST /{id}/void` [no RBAC] |
| **excel_route.py** | `/api/v1/excel` | `GET /export/inventory` (StreamingResponse .xlsx) [perm: inventory.read]<br>`POST /import/inventory` (UploadFile .xlsx→dict) [perm: inventory.write]<br>`POST /import/csv` (UploadFile .csv→dict) [perm: inventory.write] |
| **email_route.py** | `/api/v1/email` | `POST /daily-sales` (DailyReportRequest→DailyReportResponse) [perm: analytics.read]<br>`GET /health` [perm: analytics.read] |
| **drug_interaction_route.py** | `/api/v1/drug-interactions` | `POST /check` (InteractionCheckRequest→list[InteractionResultRead]) [no RBAC]<br>`GET /` [perm: inventory.write]<br>`POST /` [perm: inventory.write]<br>`PUT /{id}` [perm: inventory.write]<br>`DELETE /{id}` (204) [perm: inventory.write] |
| **drug_confirm_route.py** | `/api/v1/drugs` | `GET /confirm/{ndc}` (DrugConfirmResult) [perm: dictionaries.read] |
| **compound_route.py** | `/api/v1/compounds` | `POST /` (CompoundCreate→CompoundRead, 201) [perm: compounds.write]<br>`GET /` (query: page, page_size) [perm: compounds.read]<br>`GET /{id}` [perm: compounds.read]<br>`PUT /{id}` [perm: compounds.write]<br>`DELETE /{id}` (204) [perm: compounds.write]<br>`POST /{id}/price` [perm: compounds.read]<br>`POST /dispense` (CompoundDispenseRequest→CompoundDispenseResult, 201) [perm: compounds.dispense] |
| **alerts_route.py** | `/api/v1/alerts` | `GET /` (dict[str,Any]: expired, critical, warning, low_stock, total_products, checked_at) [perm: inventory.read] |
| **quick_sig_route.py** | `/api/v1/quick-sig` | `GET /?favorites_only=&q=` [perm: patients.read]<br>`GET /{id}` [perm: patients.read]<br>`POST /` (QuickSigTemplateCreate→QuickSigTemplateRead, 201) [perm: patients.write]<br>`PUT /{id}` [perm: patients.write]<br>`DELETE /{id}` (204) [perm: patients.write]<br>`POST /{id}/favorite` [perm: patients.read]<br>`POST /{id}/use` [perm: patients.read]<br>`GET /search/suggestions?q=` [perm: patients.read] |
| **po_route.py** | `/api/v1/purchase-orders` | `GET /?status_filter=` [perm: inventory.write]<br>`GET /{id}` [perm: inventory.write]<br>`POST /` (PurchaseOrderCreate→PurchaseOrderRead, 201) [perm: inventory.write]<br>`PUT /{id}` [perm: inventory.write]<br>`POST /{id}/items` [perm: inventory.write]<br>`DELETE /{id}/items/{item_id}` [perm: inventory.write]<br>`POST /{id}/transition` [perm: inventory.write]<br>`DELETE /{id}` (204) [perm: inventory.write] |
| **rx_queue_route.py** | `/api/v1/rx-queue` | `GET /` (query: status, prescriber_id, patient_id, start_date, end_date, page, page_size→PaginatedRxQueue) [perm: rx.queue.read]<br>`GET /counts` (RxQueueCounts) [perm: rx.queue.read]<br>`PATCH /{id}/status` (RxStatusTransition→RxQueueItem) [perm: rx.queue.transition]<br>`POST /bulk-status` (RxBulkStatusRequest→RxBulkStatusResult) [perm: rx.queue.bulk] |
| **dictionaries_route.py** | `/api/v1/dictionaries` | `GET /sig-codes` [perm: dictionaries.read]<br>`POST /sig-codes` (SigCodeCreate→SigCodeRead, 201) [perm: dictionaries.write]<br>`PUT /sig-codes/{id}` [perm: dictionaries.write]<br>`DELETE /sig-codes/{id}` (204) [perm: dictionaries.write]<br>`GET /sig-codes/parse?code=` (SigCodeParseResult) [perm: dictionaries.read]<br>`GET /price-codes` [perm: dictionaries.read]<br>`POST /price-codes` (201) [perm: dictionaries.write]<br>`PUT /price-codes/{id}` [perm: dictionaries.write]<br>`DELETE /price-codes/{id}` (204) [perm: dictionaries.write]<br>`GET /price-codes/{id}/calculate?acquisition_cost=` (PriceCalculationResult) [perm: dictionaries.read]<br>`GET /ndc/lookup?q=` (NDCLookupResult) [perm: dictionaries.read] |
| **crash_report_route.py** | `/api/v1/crash-report` | `POST /` (CrashReport→dict) [bearer] |
| **coupon_route.py** | `/api/v1/coupons` | `GET /?active_only=` [perm: inventory.write]<br>`GET /{id}` [perm: inventory.write]<br>`POST /` (CouponCreate→CouponRead, 201) [perm: inventory.write]<br>`PUT /{id}` [perm: inventory.write]<br>`DELETE /{id}` (soft-delete) [perm: inventory.write]<br>`POST /validate` (CouponValidateRequest→CouponValidateResult) [perm: pos.checkout] |

### 1.6 All Pydantic Schemas (87 classes in `schemas.py`)

**Auth & Token:** `LoginRequest`, `PinLoginRequest`, `ApprovalRequest`, `RefreshRequest`, `Token`, `UserCreate`, `UserPublic`, `CurrentUser`, `TokenPayload`
**Product/Inventory:** `ProductBase`, `MedicineBase`, `MedicineRead`, `MedicineCreate`, `MedicineUpdate`, `StockLevelRead`, `BatchUpdate`, `ReceiveBatch`, `SupplierBase`, `SupplierCreate`, `SupplierRead`, `BatchRead`, `PaginatedProducts`, `MovementLogItem`, `MovementLogResponse`
**POS/Checkout:** `CheckoutLineIn`, `PaymentSplit`, `CheckoutItemRead`, `CheckoutRequest`, `CheckoutResult`, `ReceiptItemRead`, `ReceiptRead`, `ReceiptPrintResponse`, `DrawerMovementCreate`, `DrawerMovementRead`, `ShiftOpenRequest`, `ShiftRead`, `ShiftCloseRequest`, `ShiftCloseResult`, `ShiftPreviewResult`, `RefundRequest`, `RefundRead`, `VoidItemRequest`, `VoidItemResult`, `SalesReport`, `EODReceiptLine`, `EODReceiptSummary`, `EODSummary`
**Patient/Clinical:** `PatientBase`, `PatientCreate`, `PatientRead`, `PatientUpdate`, `InsuranceBindRequest`, `PaginatedPatients`, `PatientHistoryEntry`
**Insurance/WC:** `InsurancePlanBase`, `InsurancePlanCreate`, `InsurancePlanRead`, `InsuranceValidateRequest`, `InsuranceValidationResult`, `EligibilityRequest` (local), `EligibilityCheckResult`, `InsuranceCoverage`, `PatientCostRequest`, `PatientCostResult`, `ClaimGenerationRequest`, `ClaimGenerationResult`, `PrescriptionValidationRequest`, `PrescriptionValidationResult`, `CredentialValidationRequest`, `CredentialValidationResult`, `WCClaimBase`, `WCClaimCreate`, `WCClaimRead`, `WCClaimUpdate`
**Dispense:** `DispenseBase`, `DispenseCreate`, `DispenseRead`, `DispenseUpdate`, `DispenseItemRead`, `VoidResult`, `TransferResult`
**Sync:** `SyncPushEntry`, `SyncPushRequest`, `SyncPushResult`, `DiscrepancyRead`
**Rx Queue:** `RxQueueFilters`, `RxQueueItem`, `PaginatedRxQueue`, `RxQueueCounts`, `RxStatusTransition`, `RxBulkStatusRequest`, `RxBulkStatusResult`
**Dictionaries:** `SigCodeBase`, `SigCodeCreate`, `SigCodeRead`, `SigCodeUpdate`, `PriceCodeBase`, `PriceCodeCreate`, `PriceCodeRead`, `PriceCodeUpdate`, `PriceCalculationResult`, `SigCodeParseResult`, `NDCLookupResult`, `DrugConfirmResult`
**Audit/Settings:** `AuditLogRead`, `AuditVerifyResult`, `SystemSettingRead`, `BackupResult`
**Coupons:** `CouponCreate`, `CouponUpdate`, `CouponRead`, `CouponValidateResult`, `CouponValidateRequest` (local in router)
**Receipt Templates:** `ReceiptTemplateSection`, `ReceiptTemplateCreate`, `ReceiptTemplateUpdate`, `ReceiptTemplateRead`
**Prescribers:** `PrescriberBase`, `PrescriberCreate`, `PrescriberRead`
**Members:** `MembersGroupBase`, `MembersGroupCreate`, `MembersGroupRead`, `MembersGroupUpdate`
**Quick SIG:** `QuickSigTemplateCreate`, `QuickSigTemplateUpdate`, `QuickSigTemplateRead`
**Purchase Orders:** `PurchaseOrderItemCreate`, `PurchaseOrderItemRead`, `PurchaseOrderCreate`, `PurchaseOrderUpdate`, `PurchaseOrderRead`
**Label Templates:** `TemplateCreateRequest` (local), `TemplateUpdateRequest` (local), `TemplateRead` (local), `ProductLabelSaveRequest` (local), `ProductLabelRead` (local)
**License:** `CreemCheckoutRequest`, `CreemCheckoutResponse`, `LicenseValidationResult`, `LicenseFileRequest`
**Integrations:** `IntegrationCreate`, `IntegrationRead`, `DrugEvaluateRequest`, `DrugEvaluateResponse`
**Compounds:** `CompoundIngredientCreate`, `CompoundIngredientRead`, `CompoundCreate`, `CompoundUpdate`, `CompoundRead`, `CompoundDispenseRequest`, `CompoundDispenseResult`, `CompoundPriceCalculationRequest`, `CompoundPriceCalculationResult`
**Vendors:** `VendorBase`, `VendorCreate`, `VendorUpdate`, `VendorRead`, `VendorItemRead`, `PurchaseHistoryRead`, `ReceiveShipmentPayload`
**Region Strategies:** `InsuranceCoverage`, `PatientCostRequest`, `PatientCostResult`, `ClaimGenerationRequest`, `ClaimGenerationResult`, `PrescriptionValidationRequest`, `PrescriptionValidationResult`, `CredentialValidationRequest`, `CredentialValidationResult`
**Rx Queue constants:** `RX_STATUSES`, `RX_QUEUE_GROUPS`, `RX_STATUS_TRANSITIONS`
**Error contracts:** `ErrorDetail`, `ErrorResponse`
**Local in routers:** `UserUpdate`, `SettingUpdate`, `RoleRead`, `RoleCreate`, `RoleUpdate`, `PermissionRead`, `RolePermissionUpdate`, `EligibilityRequest`, `TemplateCreate/Update/Read`, `PatientFieldCreate/Update/Read`, `ParseTextRequest`, `ParsedItem`, `ParseResponse`, `CrashReport`, `VersionInfo`, `GiftCardCreate/Read/Redeem`, `InteractionCreate/UpdateRequest`, `InteractionRead`, `InteractionResultRead`, `PayerCoverage` (for insurance)

### 1.7 SQLite Schema (22 migration versions)

**Database URL:** `sqlite+aiosqlite:///./pharmacy.db` (from `PHARMACY_DB_URL` env var)
**Connection config:** WAL mode, `busy_timeout=30000`, `foreign_keys=ON`, `BEGIN IMMEDIATE` on file-backed writes

| Version | Description |
|---|---|
| v1 | Base M9/M10: `products.is_deleted`, `users.pin_salt/pin_failed_attempts/pin_locked/until/lockout_hmac` |
| v2 | Multi-terminal: `sync_outbox`, `discrepancies`, `sync_inventory` tables |
| v3 | Cashier attribution: `receipts.server_created_at/ts_skew_confidence/created_by/cashier_attribution`, `inventory_extended.recalled`, `drawer_movements` table |
| v4 | Shift lifecycle: `shifts` table |
| v5 | B5: `refunds` table, `audit_logs.prev_hash/entry_hash` (hash chain) |
| v6 | PIN pepper version: `users.pin_pepper_version` |
| v7 | Clinical layer: `receipts.client_tx_id`, `insurance_plans`, `patients`, `members_groups`, `sig_codes`, `price_codes`, `dispenses`, `dispense_items` |
| v8 | Movement history: `products.category`, `inventory_adjustments`, `receiving_log.lot_number` |
| v9 | Prescribers + drug file + patient enrichment + Rx refills |
| v10 | WC claims: `workers_comp_claims` table + indexes |
| v11 | WAC columns: `inventory_extended.wac`, `dispense_items.wac_at_time` |
| v12 | M103 modernization: `sig_codes.language/days_accumulated/offset`, WC extended fields, insurance_plan master file fields |
| v13 | Patient name/address split + `drug_dictionary` table |
| v14 | Fix `patient_fax` → `fax` column name |
| v15 | Coupons table |
| v16 | Quick SIG templates table |
| v17 | Purchase orders + PO items tables |
| v18 | Receipt templates table |
| v19 | Drug interactions table |
| v20 | Quick SIG `usage_count` column |
| v21 | Label templates + product labels tables |
| v22 | Compound prescriptions: `compounds`, `compound_ingredients`, `compound_dispenses`, `compound_dispense_items` |

**Core ORM models (28 in `models.py`):** `Product`, `InventoryExtended`, `Supplier`, `ReceivingLog`, `User`, `Role`, `Permission`, `RolePermission`, `Receipt`, `ReceiptItem`, `SoldItem`, `AuditLog`, `SystemSetting`, `SyncOutbox`, `Discrepancy`, `SyncInventory`, `Shift`, `DrawerMovement`, `Refund`, `License`, `Patient`, `DrugDictionary`, `InsurancePlan`, `Prescriber`, `MembersGroup`, `SigCode`, `QuickSigTemplate`, `PriceCode`, `Dispense`, `DispenseItem`, `WorkersCompClaim`, `InventoryAdjustment`, `Vendor`, `VendorItem`, `PurchaseHistory`, `Integration`, `Coupon`, `PurchaseOrder`, `PurchaseOrderItem`, `ReceiptTemplate`, `DrugInteraction`, `LabelTemplate`, `ProductLabel`, `Compound`, `CompoundIngredient`, `CompoundDispense`, `CompoundDispenseItem`

### 1.8 Security Architecture

- **JWT auth:** `OAuth2PasswordBearer` with token URL `api/v1/auth/login`
- **PIN login:** `PinLoginRequest` (4–6 digit PIN) with PBKDF2 + device-bound pepper
- **Pepper management:** `DPAPI` on Windows, env-key fallback; `pin_pepper_version` for lazy re-hash
- **Rate limiting:** 5/minute for auth + PIN endpoints via `slowapi`
- **Approval tokens:** Manager approval for high-risk actions (drawer movements), single-use, scope-bound
- **Audit hash chain:** `prev_hash`/`entry_hash` columns on `audit_logs` for tamper detection
- **CORS:** `allow_origins=["*"]` in dev (permissive for LAN workstations), credentials allowed
- **Security headers:** X-Content-Type-Options, X-Frame-Options: DENY, Referrer-Policy, CSP
- **Read replica:** Read-only SQLite (`mode=ro`, `query_only=ON`) for analytics to avoid write-path contention
- **License proxy:** FastAPI proxies to Flask license microservice at port 5000

### 1.9 Lifecycle (main.py lifespan)

On startup: init engine → create schema → migrate to v22 → seed admin if absent → seed clinical defaults → seed drug dictionary → seed session settings → seed product templates → seed receipt templates. Background tasks: VACUUM snapshot every 6h, alert check every 30min.

---

## 2. Frontend Architecture (Next.js 16 + Zustand)

### 2.1 Project Metadata

| Field | Value |
|---|---|
| Name | `my-progam-pharmacy` (v1.0.0) |
| Framework | Next.js 16.3.3 |
| React | 19.1.0 |
| TypeScript | 5.8.3 |
| State Mgmt | Zustand 4.5.7 |
| HTTP | Axios 1.19 (with retry interceptor) |
| UI | Tailwind CSS v4 + custom CSS vars |
| HTTP Client | Axios + @tanstack/react-query 5.40 |
| Forms | react-hook-form 7.52 |
| Barcode | jsbarcode 3.12 |
| OCR | tesseract.js 7.0 |
| i18n | next-i18next / custom I18nProvider |
| Testing | vitest 4.1 + playwright 1.48 |
| Shell | Tauri 2 |
| Build | `output: "standalone"` (Tauri sidecar) |

### 2.2 Design System

#### CSS Custom Properties (`app/globals.css`)

**Dark theme (default):**
| Variable | Hex | Usage |
|---|---|---|
| `--bg` | `#0f0f1a` | Page background |
| `--bg-card` | `#1a1a2e` | Card surfaces |
| `--bg-input` | `#16162a` | Input backgrounds |
| `--bg-hover` | `#252540` | Hover states |
| `--fg` | `#e5e5e5` | Primary text |
| `--fg-muted` | `#8888aa` | Secondary text |
| `--fg-strong` | `#ffffff` | Strong text |
| `--border` | `#2a2a40` | Borders |
| `--primary` | `#7c3aed` | Primary accent (purple) |
| `--primary-fg` | `#ffffff` | Primary text on accent |
| `--danger` | `#dc2626` | Destructive actions |
| `--success` | `#16a34a` | Success |
| `--warning` | `#d97706` | Warnings |

**Light theme:** `bg=#f5f5f7`, `bg-card=#ffffff`, `bg-input=#f0f0f4`, `bg-hover=#e8e8ee`, `fg=#1a1a2e`, `fg-muted=#555566`, `fg-strong=#000000`, `border=#d0d0d8`, `primary=#6d28d9`

**Design System doc (`DESIGN_SYSTEM.md`):**
- Philosophy: Glassmorphism + Dark Mode First, deep space background with glowing accent colors
- Zone colors: POS=green-600, Inventory=blue-600, Patients=purple-600, Analytics=orange-600, Destructive=red-600
- Spacing: `p-6` card padding, `gap-4` standard gaps, `p-4` modal padding
- Buttons: Primary=`bg-green-600 hover:bg-green-700`, Secondary=`border border-gray-700 text-gray-300`
- Cards: `bg-[#1a1a2e] border border-gray-800 rounded-lg p-6 shadow-xl`
- Inputs: `bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100`
- Font: Inter / system sans-serif, body font = `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

#### `tailwind.config.js`
- Content paths: `app/**`, `components/**`, `hooks/**`, `lib/**`, `stores/**`, `types/**`
- `theme.extend: {}` (no customizations — relies on defaults + CSS vars)

#### Receipt Print Styles (`globals.css`)
- `.pharmacy-receipt`: 64mm width, Courier New monospace, 9px font
- `.receipt-items`: collapsible border table
- `@media print`: hides all except `#receipt-print-area`

### 2.3 Zustand Stores (13 in `stores/`)

| Store | Purpose | Key State | Key Actions |
|---|---|---|---|
| **authStore.ts** | JWT/auth + RBAC | `token`, `user`, `hasPermission()`, `isAuthenticated()` | `login()` (writes httpOnly cookies via BFF), `logout()`, `fetchCurrentUser()` |
| **sessionStore.ts** | Idle + absolute timeout | `lastActivityAt`, `idleMinutes` (15), `absoluteMinutes` (480), `showWarning`, `countdownSeconds` | `init()`, `resetIdle()`, `dismissWarning()`, `tick()`, `expire()` |
| **uiStore.ts** | Global UI state | `theme` (dark), `sidebarOpen`, `activeTab`, `modal`, `toast` | `toggleTheme()`, `toggleSidebar()`, `openModal()`, `showToast()`, `clearToast()` |
| **posStore.ts** | POS cart + checkout | `lines` (CartLine[]), `result`, `offlineCount`, `shiftId`, `recoverable[]`, `discountType/Value`, `taxExempt`, `priceOverrides`, `payments` | `addLine()`, `checkout()` (offline enqueue + sync replay), `openShift()`, `closeShift()`, `recordDrawer()`, `flushQueue()`, `hydrate()` |
| **inventoryStore.ts** | Catalog + inventory | `medicines`, `stockLevels`, `suppliers`, `filters`, `isLoading` | `loadSuppliers()`, `applyFilters()`, `search()`, `receiveBatch()`, `adjustBatch()`, `updateMedicine()`, `deleteMedicine()` |
| **patientStore.ts** | Patient CRUD | `patients` (PaginatedPatients), `selected`, `isLoading` | `loadPatients()`, `search()`, `getPatient()`, `createPatient()`, `updatePatient()`, `deletePatient()` |
| **rxStore.ts** | Rx workflow state machine | `activeModal`, `selectedPatient`, `selectedDrug`, `selectedSigCode`, `selectedPrescriber`, `selectedInsurancePlan`, `quantity`, `daysSupply`, `refillsAuthorized`, `fillDate`, `rxNumber`, `lastDispenseResult`, `isProcessing` | `openModal/closeModal()`, `setPatient/setDrug/setSigCode/setPrescriber/setInsurancePlan()` (with auto-insurance-load + days-supply-calc), `submitNewRx()`, `submitRefill()`, `editDispense()`, `reverseDispense()`, `transferDispense()` |
| **rxQueueStore.ts** | 3-tab Rx queue | `tabs` (processing/rejects/ready), `activeTab`, `items` (per-tab), `counts` | `setActiveTab()`, `fetchTab()`, `refreshAllTabs()`, `transitionStatus()`, `bulkTransition()` |
| **compoundStore.ts** | Compound prescriptions | `compounds`, `selectedCompound`, `isLoading` | `fetchCompounds()`, `getCompound()`, `createCompound()`, `updateCompound()`, `deleteCompound()`, `calculatePrice()`, `dispenseCompound()` |
| **analyticsStore.ts** | Demand analytics | `filters`, `summary`, `isLoading` | `setFilters()`, `fetch()`, `reset()` |
| **alertStore.ts** | Expiry/stock alerts | `counts` (expired/critical/warning/low_stock/total_products/`checked_at`) | `fetchAlerts()` (polls every 5min), `dismiss()`, `reset()` |
| **licenseStore.ts** | License validation | `status` (LicenseValidationResult), `loading`, `error` | `validate()` (stores license key to localStorage), `reset()` |
| **vendorsStore.ts** | Vendor management | `vendors`, `selected`, `purchases`, `isLoading`, `feedback` | `fetchVendors()`, `setSelected()`, `fetchPurchases()`, `addVendor()`, `editVendor()`, `deactivateVendor()`, `receiveStock()` |
| **regionStore.ts** | Regional settings | `region` (RegionInfo), `isLoading`, `detected` | `detect()` (uses X-Vercel-Ip-Country), `setRegion()` |

### 2.4 Hooks (20 in `hooks/`)

| Hook | Wraps Store | Purpose |
|---|---|---|
| `useInventory.ts` | inventoryStore | Initial load + RBAC-gated mutations |
| `usePatients.ts` + `usePatient(id)` | patientStore | Search with 300ms debounce, RBAC gates |
| `useLicenseGate.ts` | (standalone) | License gate decision tree, localStorage key, device-ID validation |
| `useBarcodeScanner.ts` | (standalone) | Barcode wedge scan capture, product resolution by barcode |
| `useDrugConfirm.ts` | (standalone) | Drug confirmation workflow |
| `useAnalytics.ts` | (via analyticsStore) | Demand analytics |
| `useHydration.ts` | (standalone) | SSR/Hydration safety |
| `useGlobalHotkeys.ts` | (standalone) | Global keyboard shortcuts |
| `useKeyboardShortcuts.ts` | (standalone) | POS-specific shortcuts |
| `useSettingsMasterData.ts` | (standalone) | Settings/master data |
| `useSessionTimer.tsx` | sessionStore | Wraps `startSessionTracking()` lifecycle |
| `useVersionCheck.ts` | (standalone) | Version checking against update server |
| `useLicenseGate.test.ts` | (test) | Unit tests for license gate logic |

### 2.5 React Components (40+ in `components/`)

**Layout & Infrastructure:**
- `DashboardLayout.tsx` — Sidebar nav (Operations/Insights/Administration sections), ThemeToggle, LanguageSwitcher
- `BootGuard.tsx` — Boot sequence guard (license + version check)
- `ErrorBoundary.tsx` — React error boundary
- `VersionProvider.tsx` — App version context
- `UpdateBanner.tsx` — Update notification banner
- `RegionProvider.tsx` — Regional settings context
- `I18nProvider.tsx` — i18n provider
- `AlertProvider.tsx` + `AlertBanner.tsx` — Toast/error provider
- `ThemeToggle.tsx` — Light/dark mode toggle
- `LanguageSwitcher.tsx` — EN/ES language switcher
- `LoadingSplash.tsx` — Splash screen during boot
- `OfflineSyncBanner.tsx` — Offline queue status indicator
- `GlobalHotkeys.tsx` — Global keyboard handler
- `SessionTimeoutModal.tsx` — Idle timeout warning modal

**POS-specific:**
- `PricingCard.tsx` — Creem checkout card (pricing tiers)
- `SplitPaymentDialog.tsx` — Multi-tender payment dialog
- `ShiftCloseDialog.tsx` — End-of-day shift close
- `EODSummaryPanel.tsx` — End-of-day summary
- `ReceiptHistoryPanel.tsx` — Recent receipts
- `ReceiptPrintPreview.tsx` — Receipt print preview
- `CouponInput.tsx` — Coupon code entry
- `GiftCardPayment.tsx` + `GiftCardBalanceCheck.tsx` — Gift card workflows
- `DiscountDialog.tsx` — Discount configuration
- `ManagerApprovalDialog.tsx` — Manager PIN approval
- `DrugEvaluateButton.tsx` — Drug interaction check
- `InteractionChecker.tsx` — DDI checker
- `PatientHistoryPanel.tsx` — Patient dispensing history
- `DiscrepanciesPanel.tsx` — Sync discrepancy review

**Rx-specific (`components/rx/`):**
- `NewRxModal.tsx`, `EditRxModal.tsx`, `RefillModal.tsx`, `TransferRxModal.tsx`, `ReverseRxModal.tsx`
- `EligibilityModal.tsx`, `PriceCheckModal.tsx`
- `RxQueueDashboard.tsx` — 3-tab Rx queue
- `SearchableInput.tsx` — Searchable dropdown input
- `DurAlertPanel.tsx` — Drug utilization review alerts
- `DrugEducationModal.tsx` — Patient drug education

**Print/Label:**
- `LabelCanvas.tsx` — Label designer canvas
- `LabelPropertiesPanel.tsx` — Label editor properties

**Other:**
- `InvoiceParsePanel.tsx` — OCR invoice parse results

### 2.6 Application Routes (32+ pages)

| Route | Auth Required | Store Used | Description |
|---|---|---|---|
| `/` | No | — | Landing page with PricingCard (static exportable) |
| `/login` | No | authStore | Username/password or PIN login (via BFF route) |
| `/license` | No | licenseStore | License key entry / validation |
| `/portal` | No | — | App download portal |
| `/pos` | Yes | posStore, authStore, rxStore | POS checkout (barcode wedge input) |
| `/dashboard` | Yes | authStore | Main dashboard (metrics cards) |
| `/dashboard/inventory` | Yes | inventoryStore | Medicine catalog, stock levels, batches |
| `/dashboard/expiry-alerts` | Yes | alertStore | Expired/critical/warning inventory |
| `/dashboard/analytics` | Yes | analyticsStore | Sales analytics |
| `/dashboard/analytics/demand` | Yes | analyticsStore | Demand analytics |
| `/dashboard/audit` | Yes | — | Audit log viewer + hash-chain verification |
| `/dashboard/backup` | Yes | — | Backup/restore interface |
| `/dashboard/email` | Yes | — | Email reports |
| `/dashboard/wc-claims` | Yes | — | Workers' compensation claims |
| `/dashboard/vendors` | Yes | vendorsStore | Vendor/supplier management |
| `/dashboard/gift-cards` | Yes | — | Gift card management |
| `/dashboard/bulk-import` | Yes | — | Bulk import (Excel/CSV) |
| `/dashboard/receipt-templates` | Yes | — | Receipt template designer |
| `/dashboard/label-engine` | Yes | — | Label template designer |
| `/dashboard/settings` | Yes | — | System settings |
| `/dashboard/users` | Yes | — | User management |
| `/dashboard/roles` | Yes | — | RBAC roles & permissions |
| `/dashboard/sig-codes` | Yes | — | SIG code dictionary |
| `/dashboard/price-codes` | Yes | — | Price code management |
| `/dashboard/prescribers` | Yes | — | Prescriber directory |
| `/dashboard/purchase-orders` | Yes | — | PO lifecycle management |
| `/dashboard/templates` | Yes | — | Product template library |
| `/dashboard/roles` | Yes | — | Role management |
| `/patients` | Yes | patientStore | Patient CRUD + search |
| `/prescribers` | Yes | — | Prescriber directory |
| `/rx` | Yes | rxStore | Prescription processing workflow |
| `/print-label` | Yes | — | Label printing interface |

### 2.7 API Client Layer

**`lib/api.ts`** — Axios instance with:
- Base URL: `NEXT_PUBLIC_API_BASE_URL` or `http://localhost:8000`
- Request interceptor: attaches `Bearer` token from `localStorage.access_token`
- Response interceptor: on 401, calls `/api/auth/refresh` (BFF proxy), stores new token, retries once

**`lib/api/*.ts`** — 25+ typed API client modules:
| Module | Base Path | Key Functions |
|---|---|---|
| `auth.ts` | `/api/v1/auth` | `getCurrentUser()`, `pinLogin()`, `setPin()`, `registerUser()`, `logoutUser()`, `rotatePepper()` |
| `pos.ts` | `/api/v1/pos` | `checkout()`, `drawerMovement()`, `refundSale()`, `getSalesReport()`, `getRecentReceipts()`, `getReceiptDetail()`, `getReceiptPrint()`, `getEODSummary()` |
| `inventory.ts` | `/api/v1/inventory` | `listMovements()`, `listMedicines()`, `searchMedicines()`, `getStockLevels()`, `listSuppliers()`, `createSupplier()`, etc. |
| `patients.ts` | `/api/v1/patients` | `listPatients()`, `searchPatients()`, `getPatient()`, `createPatient()`, `updatePatient()`, `deletePatient()`, `getPatientDispenses()`, `getPatientHistory()` |
| `dispense.ts` | `/api/v1/dispense` | `dispense()`, `getDispenseByRx()`, `getFillsByRx()`, `updateDispense()`, `voidDispense()`, `transferDispense()`, `refillDispense()` |
| `prescribers.ts` | `/api/v1/prescribers` | `listPrescribers()`, `getPrescriber()`, `createPrescriber()`, `updatePrescriber()`, `deletePrescriber()` |
| `insurance.ts` | `/api/v1/insurance` | `listPlans()`, `getPlan()`, `createPlan()`, `updatePlan()`, `validatePlan()`, `checkEligibility()`, `bindPlan()` |
| `settings.ts` | `/api/v1/settings` | `getSettings()`, `getSetting()`, `updateSetting()` |
| `users.ts` | `/api/v1/users` | `listUsers()`, `getUser()`, `updateUser()`, `toggleUserActive()` |
| `roles.ts` | `/api/v1/roles` | `listRoles()`, `getRole()`, `createRole()`, `updateRole()`, `getPermissions()`, etc. |
| `sync.ts` | `/api/v1/sync` | `pushSync()` |
| `dashboard.ts` | `/api/v1/dashboard` | `getDashboardMetrics()` |
| `analytics.ts` | `/api/v1/analytics` | `getDemandAnalytics()`, `getTopSelling()` |
| `alerts.ts` | `/api/v1/alerts` | `getAlerts()` |
| `license.ts` | `/api/v1/license` | `validateLicense()`, `createCheckout()`, `checkLicenseStatus()` |
| `vendors.ts` | `/api/v1/vendors` | `listVendors()`, `createVendor()`, `updateVendor()`, `getVendorItems()`, `getVendorPurchases()`, `receiveShipment()` |
| `dictionaries.ts` | `/api/v1/dictionaries` | `listSigCodes()`, `createSigCode()`, `parseSigCode()`, `listPriceCodes()`, `calculatePriceCode()`, `lookupNdc()` |
| `dictionaries.ts` | — | `parseSigCode()`, `ndcLookup()`, `listPriceCodes()` |
| `drugConfirm.ts` | `/api/v1/drugs` | `confirmDrug()` |
| `drugInteractions.ts` | `/api/v1/drug-interactions` | `checkInteractions()`, `listInteractions()`, etc. |
| `receiptTemplates.ts` | `/api/v1/receipt-templates` | `listTemplates()`, `getDefaultTemplate()`, `createTemplate()`, etc. |
| `labelTemplates.ts` | `/api/v1/label-templates` | `listLabelTemplates()`, etc. |
| `coupons.ts` | `/api/v1/coupons` | `listCoupons()`, `validateCoupon()`, etc. |
| `giftCards.ts` | `/api/v1/gift-cards` | `createGiftCard()`, `lookupGiftCard()`, `redeemGiftCard()`, etc. |
| `wc.ts` | `/api/v1/wc-claims` | `listWcClaims()`, `createWcClaim()`, etc. |
| `members.ts` | `/api/v1/members-groups` | `listMembers()`, `createMember()`, etc. |
| `prescribers.ts` | — | `listPrescribers()`, etc. |
| `compound.ts` | `/api/v1/compounds` | `listCompounds()`, `dispenseCompound()`, etc. |
| `rxQueue.ts` | `/api/v1/rx-queue` | `getQueue()`, `getCounts()`, `transitionStatus()`, `bulkTransition()` |
| `quickSig.ts` | `/api/v1/quick-sig` | `listQuickSigs()`, `createQuickSig()`, etc. |
| `purchaseOrders.ts` | `/api/v1/purchase-orders` | `listPOs()`, `createPO()`, etc. |
| `settings.ts` | — | `getSettings()`, etc. |
| `approval.ts` | `/api/v1/pos` | `requestApproval()` |
| `version.ts` | `/api/v1/version` | `getVersionInfo()` |
| `ocr.ts` | `/api/v1/ocr` | `ocrImage()` |
| `excel.ts` | `/api/v1/excel` | `exportInventory()`, `importInventory()`, `importCsv()` |
| `email.ts` | `/api/v1/email` | `sendDailySalesReport()`, `checkEmailHealth()` |
| `region.ts` | `/api/v1/region` | `detectRegion()`, `getRegions()`, `getRegion()` |
| `regionStrategy.ts` | `/api/v1/region-strategy` | `calculatePatientCost()`, `generateClaim()` |

### 2.8 Next.js BFF Route Handlers (`app/api/`)

| Route | Method | Description |
|---|---|---|
| `app/api/auth/login/route.ts` | POST | Proxies to FastAPI `/api/v1/auth/login`, sets httpOnly + sameSite=strict cookies for `access_token` (480min) and `refresh_token` (30 days) |
| `app/api/auth/refresh/route.ts` | POST | Proxy to FastAPI `/api/v1/auth/refresh`, rotates tokens, sets new cookies |
| `app/api/auth/logout/route.ts` | POST | Clears cookies, calls FastAPI logout |
| `app/api/webhooks/paddle/route.ts` | POST | Paddle webhook receiver (verifies Paddle-Signature) |
| `app/api/health/route.ts` | GET | Health check endpoint |
| `app/api/currency/route.ts` | GET | Currency formatting service |

### 2.9 Tauri Configuration (`src-tauri/`)

**Prod config (`tauri.conf.json`):**
- Product: `PharmacySuite` v1.0.0
- Identifier: `com.pharmacy.suite`
- Window: 800×600, resizable, non-fullscreen
- Frontend dist: `../.next/static` (standalone build)
- Dev URL: `http://localhost:3000`
- CSP: `default-src 'self'; img-src 'self' data: https: http://127.0.0.1:3000 http://localhost:3000; style-src ...; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' ...; connect-src 'self' ... http://localhost:8000 ...`
- Bundle: NSIS Windows installer, external binary `binaries/backend`
- Resources: `../.next/standalone`

**Dev config (`tauri.dev.config.json`):**
- Product: `Pharmacy POS Test`
- Window: 800×600

### 2.10 Frontend Supporting Utilities

| File | Purpose |
|---|---|
| `lib/decimalCurrency.ts` | Integer-cents money math (never float) — `parseMoney()`, `formatMoney()`, `mulByQty()`, `sumMoney()` |
| `lib/db.ts` | IndexedDB wrapper for offline POS storage |
| `lib/offlineQueue.ts` | Offline enqueue + replay queue with `client_txn_id` idempotency |
| `lib/storagePersist.ts` | localStorage persistence with tab registry for cart recovery (A3) |
| `lib/syncLock.ts` | Async mutex for preventing concurrent sync operations |
| `lib/deviceId.ts` | Stable hardware device ID generation |
| `lib/regionFormat.ts` | Regional formatting (dates, currency, tax) |
| `lib/monetarySchema.ts` | Monetary validation schemas |
| `lib/license.ts` | License file signing/validation utilities |
| `lib/i18n/` | i18n config + dictionaries (EN/ES) |
| `lib/ocr.ts` | OCR service wrapper |
| `lib/redis.ts` | Redis client (for caching) |
| `lib/validations/` | Zod schemas: patient, insurance, sigCode, priceCode, workersComp |

### 2.11 Type Contracts (`types/contracts.ts`, 1690 lines)

TypeScript interfaces mirroring all backend Pydantic schemas. Key types:
- **Money:** `type Money = string` (backend Decimal serializes as JSON string)
- **Error contracts:** `ErrorDetail { code, message, details }`, `ErrorResponse { error: ErrorDetail }`
- **Auth:** `LoginRequest`, `PinLoginRequest`, `Token`, `UserPublic`, `CurrentUser`, `TokenPayload`
- **Product:** `Medicine`, `MedicineUpdate`, `MedicineCreate`, `Batch`, `BatchUpdate`, `ReceiveBatch`, `StockLevel`, `PaginatedProducts`
- **POS:** `CartLine`, `CheckoutRequest`, `CheckoutResult`, `CheckoutItemRead`, `ReceiptRead`, `ReceiptPrintResponse`, `DrawerMovementCreate/Read`, `ShiftRead/CloseRequest/CloseResult/PreviewResult`, `RefundRead/Request`, `VoidItemRequest/Result`, `SalesReport`, `EODSummary/EODReceiptSummary/EODReceiptLine`
- **Patient:** `PatientRead`, `PatientCreate`, `PatientUpdate`, `PaginatedPatients`, `PatientHistoryEntry`
- **Insurance:** `InsurancePlanRead`, `InsuranceValidateRequest`, `InsuranceValidationResult`, `EligibilityCheckResult`, `InsuranceCoverage`, `PatientCostRequest/Result`, `ClaimGenerationRequest/Result`, `PrescriptionValidationRequest/Result`, `CredentialValidationRequest/Result`
- **Dispense:** `DispenseRead`, `DispenseCreate`, `DispenseUpdate`, `DispenseItemRead`, `VoidResult`, `TransferResult`
- **Rx Queue:** `RxQueueItem`, `PaginatedRxQueue`, `RxQueueCounts`, `RxStatusTransition`, `RxBulkStatusRequest/Result`
- **Dictionaries:** `SigCodeRead`, `PriceCodeRead`, `PriceCalculationResult`, `SigCodeParseResult`, `NDCLookupResult`, `DrugConfirmResult`
- **Compound:** `CompoundCreate/Update/Read`, `CompoundIngredientCreate/Read`, `CompoundDispenseRequest/Result`, `CompoundPriceCalculationRequest/Result`
- **Coupons:** `CouponRead`, `CouponValidateResult`
- **Audit:** `AuditLogRead`, `AuditVerifyResult`
- **Settings:** `SystemSettingRead`
- **Others:** `BackupResult`, `DrugEvaluateRequest/Response`, `IntegrationCreate/Read`

---

## 3. Integration Architecture

### 3.1 Service Orchestration (`run_services.py`)

Three services started as subprocesses:
1. **Flask** (`backend/app.py`) → port 5000 (Lemon Squeezy webhook + license validation)
2. **FastAPI** (`backend_fastapi/app/main.py`) → port 8000 (main pharmacy API)
3. **Next.js** (`npm run dev`) → port 3000 (frontend)

**Environment variables set by `run_services.py`:**
- `LEMON_SQUEEZEY_SIGNATURE_SECRET` = dev-only
- `ADMIN_SECRET` = dev-only
- `PHARMACY_DB_URL` = `sqlite+aiosqlite:///./pharmacy.db`
- `SECRET_KEY` = dev-only
- `FRONTEND_URL` = `http://localhost:3000`
- `LICENSE_GATE_URL` = `http://localhost:5000`

### 3.2 Auth Flow

1. User submits login form (Next.js `app/login/page.tsx`)
2. Next.js BFF route handler `app/api/auth/login/route.ts` proxies to FastAPI `/api/v1/auth/login`
3. FastAPI returns JWT `access_token` (8h expiry) + `refresh_token` (30 days)
4. BFF handler sets `httpOnly` + `sameSite=strict` cookies
5. Zustand `authStore` stores token in localStorage, calls `/me` to fetch `CurrentUser` (id, username, role, permissions[])
6. All subsequent API calls go through Axios interceptor with `Authorization: Bearer <token>`
7. On 401: Axios interceptor calls BFF `/api/auth/refresh` to rotate tokens

### 3.3 Data Flow Pattern

```
Frontend (Next.js page)
  → Zustand store (e.g., `usePosStore`)
    → Typed API client (e.g., `lib/api/pos.ts` → `checkout()`)
      → Axios instance (lib/api.ts with JWT + retry interceptor)
        → FastAPI (backend_fastapi, port 8000)
          → Repository (app/core/repositories.py)
            → SQLAlchemy async session (app/core/database.py)
              → SQLite (pharmacy.db, WAL mode)
```

For license validation:
```
Frontend licenseStore.validate()
  → lib/api/license.ts → /api/v1/license/validate
    → FastAPI license_route.py
      → Checks local SQLite `licenses` table
      → Falls back to Flask license service proxy (port 5000)
```

---

## 4. Key Findings Summary

### 4.1 What IS Built and Functioning

- **3-service dev orchestration** with `run_services.py` (Flask + FastAPI + Next.js)
- **48 FastAPI routers** covering: health, auth, admin (backup/restore), users, inventory, POS (checkout, shift, drawer, refunds), patients (CRUD + insurance binding), prescribers, insurance (plans, eligibility, claims), dispense (with FIFO lot tracking), audit (hash chain verification), dashboard metrics, analytics (demand, top-selling), regions, settings, roles/RBAC, sync (multi-terminal), receipt/templates, label templates, webhooks (Creem + Paddle), WC claims, versioning, vendors, patient fields, OCR, members, license, license-file activation, invoice parse, integrations, gift cards, Excel import/export, email, drug interactions, drug confirmation, compounds, alerts, quick-sig, PO management, Rx queue
- **SQLite schema v22** with 22 versioned migrations covering legacy schema preservation + new feature additions
- **87 Pydantic schemas** for all API contracts
- **28 ORM models** mirroring the legacy `pharmacy.db` schema
- **13 Zustand stores** with clean separation (auth, session, UI, POS, inventory, patients, Rx, Rx queue, compounds, analytics, alerts, license, vendors, regions)
- **React Query** for server state with 5-min stale time
- **Axios retry interceptor** for 401 → refresh → retry
- **Tauri desktop wrapper** with standalone build pipeline
- **Design system** with CSS variables, dark mode (light mode also defined)
- **Next.js BFF** with httpOnly cookies for auth token security
- **Multi-terminal sync hub** with `sync_outbox`, `discrepancies`, `sync_inventory` tables
- **Compound prescription support** with ingredient-level lot tracking

### 4.2 Key Design Decisions

| Decision | Implementation |
|---|---|
| Money handling | Backend: `Decimal` (Pydantic). Frontend: `Money = string` + `decimalCurrency.ts` integer-cents math. NEVER float. |
| Offline support | `posStore` enqueues to IndexedDB, replays via sync hub with `client_txn_id` idempotency |
| RBAC | JWT claims carry `permissions[]`; `require_permission` in `deps.py` + `useCan()` in frontend |
| Schema evolution | `PRAGMA user_version` migration system, idempotent, restart-safe (v1–v22) |
| Read scalability | Read-only SQLite replica (`mode=ro`, `query_only`) for analytics queries |
| Audit security | Hash chain on `audit_logs` (`prev_hash` → `entry_hash`) with `/verify` endpoint |
| License enforcement | FastAPI proxies to Flask license service; offline grace period (72h) via `offline_until` |
| Receipt printing | Dual format: thermal text + HTML, via `ReceiptPrintResponse` |

### 4.3 Architectural Boundaries

**Clean layers within backend_fastapi:**
- `app/api/routers/` — HTTP endpoint definitions (thin, no business logic)
- `app/services/` — Business logic (30+ service modules)
- `app/core/repositories.py` — Data access (ORM abstraction)
- `app/core/models.py` — SQLAlchemy ORM models
- `app/shared/` — Cross-cutting: schemas, security, config, exceptions, rate_limit

**Frontend data flow:**
- `types/contracts.ts` — Type contracts (mirror backend schemas)
- `lib/api/*.ts` — Typed API clients (Axios wrappers)
- `stores/*.ts` — Zustand global state
- `hooks/*.ts` — React hooks wrapping stores
- `components/*.tsx` — Presentational + container components
- `app/**/*.tsx` — Pages (routes, layout)
