# Baseline Report: Decoupled Pharmacy Stack (Next.js 16 + FastAPI + Tauri)

> Generated from a full read of `E:\my progam pharmacy` (workspace root).
> This is a **baseline inventory** — not an implementation plan. No source changes have been made.

---

## 0. Architecture Overview

| Layer | Path | Tech |
|---|---|---|
| Frontend (Next.js 16) | `./app/`, `./components/`, `./hooks/`, `./lib/`, `./store/` | Next.js App Router, React 18, TypeScript, Tailwind CSS 3, TanStack Query, Zustand 5 |
| Backend (FastAPI) | `./backend_fastapi/` | FastAPI, Pydantic v2, SQLAlchemy 2.0 (async aiosqlite), Alembic-style inline `migrate_schema` |
| Desktop Shell | `./tauri/` (config), `./src-tauri/` | Tauri 2, Rust, single-window, context-isolated |
| Shared config | `./DESIGN_SYSTEM.md`, `./tailwind.config.js`, `./package.json` | Design tokens + CSS pipeline |

**Request flow:** Tauri window → Next.js renderer → `@/lib/api/*` (typed fetch client) → FastAPI `app/main.py` → SQLAlchemy `AsyncSession` → SQLite (WAL). The backend runs embedded (child process or in-process), not as a standalone server.

---

## 1. Pydantic Schema Map (`backend_fastapi/app/schemas.py` — 1,731 lines)

The schema layer is the **single source of truth** for API contracts. All request/response models inherit from an `AbstractBaseModel` with `model_config = ConfigDict(from_attributes=True)`.

### 1.1 Domain Schemas by Area

**Auth & Security**
| Schema | Purpose |
|---|---|
| `LoginRequest` | username, password |
| `PinLoginRequest` | username, pin (kiosk PIN login) |
| `RefreshRequest` | refresh_token |
| `Token` | access_token, refresh_token, token_type, expires_in |
| `TokenPayload` | sub, exp, permissions, etc. (JWT claims) |
| `UserCreate` / `UserPublic` / `UserRead` | Registration, public view, full read |
| `CurrentUser` | Authenticated user with permissions & role info |
| `RoleRead` / `PermissionRead` | RBAC model objects |
| `ChangePasswordRequest` | Current + new password |
| `PinPepperAudit` | Pepper rotation audit trail |

**Patients**
| Schema | Fields |
|---|---|
| `PatientRead` | id, mrn, first_name, last_name, dob, gender, phones, address, insurance_id |
| `PatientCreate` / `PatientUpdate` | Write payloads |
| `PatientHistoryEntry` | Dispensing history per patient |

**Inventory**
| Schema | Fields |
|---|---|
| `ProductRead` | product_code, ndc, name, strength, form, supplier info |
| `ProductCreate` / `ProductUpdate` | Write payloads |
| `BatchRead` | lot_number, expiry, on_hand, reserved, available_to_dispense |
| `BatchCreate` / `BatchUpdate` | Write payloads |
| `StockLevelRead` | product-level on-hand across all batches |
| `SupplierRead` / `SupplierCreate` / `SupplierUpdate` | Vendor entity |
| `SupplierItemRead` | supplier-specific pricing/conversion |
| `MovementLogResponse` | Audit trail of stock movements |
| `InventoryAdjustmentRequest` | Reason + quantity change |

**POS / Dispensing**
| Schema | Fields |
|---|---|
| `CartItem` | product, quantity, days_supply, refills |
| `CheckoutResult` | receipt_id, total, change, dispensed_items |
| `DispenseRead` | rx_number, patient, drug, qty, days_supply, refills_remaining |
| `DispenseCreate` / `DispenseUpdate` | Write payloads |
| `TransferResult` | Inter-pharmacy transfer outcome |
| `RefundRead` | Refund record |
| `VoidItemResult` | Voided line-item |
| `ShiftRead` / `ShiftCloseResult` / `ShiftPreviewResult` | Cash-registershift lifecycle |
| `EODSummary` | End-of-day reconciliation |
| `SalesReport` / `ReceiptRead` | Reporting outputs |
| `CheckoutRequest` | Cart + payments + patient context |

**Insurance**
| Schema | Fields |
|---|---|
| `InsurancePlanRead` | plan_code, pbm, copay, formulary rules |
| `InsurancePlanCreate` / `Update` | Write payloads |
| `EligibilityCheckResult` | Coverage + copay + prior-auth requirements |
| `InsuranceValidationResult` | Plan validity check |

**Prescribers**
| Schema | Fields |
|---|---|
| `PrescriberRead` | npi, name, dea, phone, fax |
| `PrescriberCreate` / `Update` | Write payloads |

**System & Admin**
| Schema | Fields |
|---|---|
| `SystemSettingRead` | key, value, type, section |
| `BackupResult` / `RestoreRequest` | Admin DB operations |
| `LicenseValidationResult` / `CreemCheckoutResponse` | Licensing flow |
| `ParseResponse` / `ParseRequest` | Invoice OCR parsing |
| `DrugEvaluateResponse` | External drug evaluation API |
| `InteractionRead` / `InteractionResultRead` | Drug-drug interaction records |
| `QuickSigTemplateRead` | Sig code shortcuts |
| `TemplateRead` | Label/receipt templates |
| `RegionDetectResult` / `RegionInfo` | Geographic region detection |

**Cross-Cutting**
| Schema | Purpose |
|---|---|
| `PaginatedResponse[T]` | Generic pagination wrapper |
| `PaginatedProducts` / `PaginatedPatients` | Typed paginated responses |
| `HealthResponse` | API health + version |
| `VersionInfo` | App version metadata |
| `AuditVerifyResult` | Audit trail verification |
| `WebhookPayload` | Incoming webhook data |

### 1.2 Schema Count & Patterns
- **~100 active Pydantic schemas** in `schemas.py`
- Inheritance: `AbstractBaseModel` → all models use `from_attributes=True` for ORM compatibility
- Pagination: generic `PaginatedResponse[T]` pattern used by Product, Patient, and other list endpoints
- All enum types defined as `Enum` subclasses (e.g., `GenderEnum`, `ShiftStatus`, `PermissionScope`)

---

## 2. API Endpoint Registry (28 router files, 41 `APIRouter` prefixes, 187 route decorators)

### 2.1 Router Prefix Map

| File | Prefix | Tag | Description |
|---|---|---|---|
| `health_route.py` | `/api/v1` | health | `GET /health` |
| `integrations_route.py` | `/api/v1` | integrations | `POST /drugs/evaluate`, `GET/POST /integrations` |
| `auth_route.py` | `/api/v1/auth` | auth | Login, PIN, refresh, register, me, logout, pepper rotation |
| `dashboard_route.py` | `/api/v1/dashboard` | dashboard | `GET /metrics` |
| `audit_route.py` | `/api/v1/audit` | audit | `GET /verify`, `GET /export` |
| `alerts_route.py` | `/api/v1/alerts` | alerts | `GET /` (alerts list) |
| `analytics_route.py` | `/api/v1/analytics` | analytics | `GET /demand`, `GET /top-selling` |
| `drug_interaction_route.py` | `/api/v1/drug-interactions` | drug-interactions | CRUD + `POST /check` |
| `excel_route.py` | `/api/v1/excel` | excel | `GET /export/inventory`, `POST /import/inventory`, `POST /import/csv` |
| `license_file_route.py` | `/api/v1/licenses` | license-file | `POST /activate-file` |
| `coupon_route.py` | `/api/v1/coupons` | coupons | Full CRUD + `POST /validate` |
| `admin_route.py` | `/api/v1/admin` | admin | `POST /backup`, `GET /backups`, `POST /restore` |
| `crash_report_route.py` | `/api/v1/crash-report` | crash-report | `POST /` |
| `members_route.py` | `/api/v1/members-groups` | members | Full CRUD |
| `insurance_route.py` | `/api/v1/insurance` | insurance | Plan CRUD + `POST /validate`, `POST /eligibility` |
| `label_template_route.py` | `/api/v1/label-templates` | label-templates | Template CRUD |
| `label_template_route.py` | `/api/v1/product-labels` | product-labels | Product label CRUD |
| `dictionaries_route.py` | `/api/v1/dictionaries` | dictionaries | Sig codes, price codes, NDC lookup |
| `dispense_route.py` | `/api/v1/dispense` | dispense | Full CRUD + rx search, fills, reverse, transfer, label, refill |
| `invoice_parse_route.py` | `/api/v1/invoice-parse` | invoice-parse | `POST /text`, `POST /file` |
| `ocr_route.py` | `/api/v1/ocr` | ocr | `POST /` (OCR extraction) |
| `pos_route.py` | `/api/v1/pos` | pos | Checkout, approve, shift open/close, refund, reports, receipts, EOD, void-item |
| `drug_confirm_route.py` | `/api/v1/drugs` | drug-confirmation | `GET /` (drug confirmation) |
| `license_route.py` | `/api/v1/license` | license | `POST /validate`, `POST /checkout`, `POST /admin/manage`, `GET /status` |
| `inventory_route.py` | `/api/v1/inventory` | inventory | Medicines CRUD, batches CRUD, stock-levels, suppliers CRUD, movements, adjustments |
| `po_route.py` | `/api/v1/purchase-orders` | purchase-orders | PO CRUD, item CRUD, transition, delete |
| `patients_route.py` | `/api/v1/patients` | patients | Patient CRUD + insurance, dispenses, history |
| `email_route.py` | `/api/v1/email` | email | `POST /daily-sales`, `GET /health` |
| `prescriber_route.py` | `/api/v1/prescribers` | prescribers | Full CRUD |
| `quick_sig_route.py` | `/api/v1/quick-sig` | quick-sig | Template CRUD + favorite, use, search-suggestions |
| `receipt_template_route.py` | `/api/v1/receipt-templates` | receipt-templates | Template CRUD + default |
| `region_route.py` | `/api/v1/region` | region | `GET /detect`, `GET /regions`, `GET /{code}` |
| `settings_route.py` | `/api/v1/settings` | settings | `GET /`, `GET /{key}`, `PUT /{key}` |
| `roles_route.py` | `/api/v1/roles` | roles | Role CRUD + permissions sub-routes |
| `users_route.py` | `/api/v1/users` | users | User list/read/update + `PATCH /{id}/active` |
| `templates_route.py` | `/api/v1/templates` | templates | Template CRUD (generic) |
| `sync_route.py` | `/api/v1/sync` | sync | `POST /push`, `GET /pull`, `POST /pull` |
| `version_route.py` | `/api/v1/version` | version | `GET /` |
| `webhook_route.py` | `/api/v1/webhook` | webhook | `POST /creem` |
| `vendors_route.py` | `/api/v1/vendors` | vendors | Vendor CRUD + items, purchases, receive |
| `wc_route.py` | `/api/v1/wc-claims` | workers-compensation | WC claim CRUD |

### 2.2 Key Endpoint Details

**Auth** (`/api/v1/auth`):
- `POST /login` → `Token`
- `POST /login/pin` → `Token` (kiosk PIN, device-bound pepper)
- `POST /pin` → 204 (set/reset PIN, requires `users.write`)
- `POST /refresh` → `Token`
- `POST /register` → `UserPublic` (requires `users.write`)
- `GET /me` → `CurrentUser`
- `POST /logout` → `{status, message}`
- `POST /rotate-pepper` → `{rotated, pin_pepper_version, pepper_bytes}` (requires `pos.pepper.rotate`)

**POS** (`/api/v1/pos`):
- `POST /approve` → 200
- `POST /checkout` → `CheckoutResult` 201
- `POST /void` (inferred from 187 decorator list, line 76) → `VoidItemResult` 200
- `POST /shift/open` → `ShiftRead` 201
- `POST /shift/close` → `ShiftCloseResult` 200
- `GET /shift/{shift_id}/preview` → `ShiftPreviewResult` 200
- `POST /refund` → `RefundRead` 200
- `GET /reports/sales` → `SalesReport` 200
- `GET /receipts/recent` → `list[ReceiptRead]` 200
- `GET /receipts/{receipt_id}` → `ReceiptRead` 200
- `GET /eod-summary` → `EODSummary` 200
- `POST /void-item` → `VoidItemResult` 200

**Sync** (`/api/v1/sync`):
- `POST /push` → `SyncPushResult` 200
- `GET /pull` (line 37, GET decorator) → sync data 200
- `POST /pull` (line 51, POST decorator) → sync data 200

**Inventory** (`/api/v1/inventory`):
- Medicines: `GET /medicines`, `GET /medicines/search`, `GET /medicines/{id}`, `POST`, `PUT`, `DELETE`
- Batches: `GET /batches`, `POST /batches/receive`, `GET /low-stock`, `GET /expiring-soon`, `GET /{id}`, `PUT`
- `GET /stock-levels`, `GET/POST /suppliers`, `GET /movements`, `POST /adjustments`

### 2.3 API Contract Patterns
- **Response models**: Every endpoint declares `response_model=` explicitly (Pydantic serialization enforcement)
- **Status codes**: Explicit `status_code=` (e.g., 201 for creates, 204 for deletes, 200 for updates)
- **Rate limiting**: `auth` endpoints use `@limiter.limit(get_auth_limit())` and `get_pin_limit()`
- **RBAC**: `require_permission(...)` dependency gates admin/mutation routes

---

## 3. Database Schema (SQLite WAL)

### 3.1 ORM Models (`backend_fastapi/app/models.py`)

12 SQLAlchemy ORM tables mapped from `models.py`:

| Table | Key Fields |
|---|---|
| `users` | id, username, email, password_hash, role_id, is_active, PIN columns (salt, failed_attempts, locked_until, lockout_hmac) |
| `roles` | id, name, description |
| `permissions` | id, code, name, scope |
| `role_permissions` | (join) role_id, permission_id |
| `patients` | id, mrn, first_name, last_name, dob, gender, phones (JSON), address (JSON), insurance_plan_id |
| `prescribers` | id, npi, name, dea, phone, fax |
| `products` | id, product_code, ndc, name, strength, form, supplier_id |
| `batches` | id, product_id, lot_number, expiry_date, on_hand, reserved, available_to_dispense |
| `suppliers` | id, name, contact_info (JSON), address |
| `dispenses` | id, rx_number, patient_id, prescriber_id, product_id, batch_id, quantity, days_supply, refills_remaining |
| `receipts` | id, shift_id, receipt_number, total_amount, payment_method, timestamp |
| `sync_outbox` | id, entity_type, entity_id, operation, payload (JSON), processed, error_count |
| `audit_logs` | id, user_id, action, details, timestamp, ip_address |

### 3.2 Migration System (`database.py` → `migrate_schema`)

The migration system is **inline Python** — each migration is a numbered `IF` block in `migrate_schema()`, versioned via `PRAGMA user_version`. There is no Alembic.

- **Current migration version: 21** (highest `IF version < N` block in `migrate_schema`)
- Migration 21 adds `pin_salt`, `pin_failed_attempts`, `pin_locked_until`, `lockout_hmac` columns to `users` table
- Migration pattern: `IF version < N: <ALTER TABLE / CREATE TABLE statements>; version = N;`
- WAL mode is enabled for all file-backed databases
- `busy_timeout=5000` (5 seconds) — noted in prior plan as wanting 30000ms

### 3.3 Database Configuration
- **Engine**: `aiosqlite` async engine (SQLAlchemy 2.0 `AsyncSession`)
- **Mode**: `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`
- **Session factory**: `async_session_factory` via `get_session` dependency (AsyncSession)
- **Connection lifecycle**: `async with async_session()` pattern throughout services

---

## 4. Design System & Tokens

### 4.1 `DESIGN_SYSTEM.md` (2,813 lines — comprehensive design system)

**Color Palette**
- Primary: `#10B981` (emerald-500) — pharmacy/healthcare association
- Semantic tokens: `--pharmacy-primary-50` through `--pharmacy-primary-900`
- Status: success (green), warning (amber), error (red), info (blue)
- Dark mode: native Tailwind `dark:` variant support

**Typography**
- Font family: Inter (custom `--font-sans` via Next.js font system)
- Scale: base text, headings (h1–h6), caption, micro
- Line heights: 1.5 (body) through 1.2 (tight)

**Spacing System**
- 4px baseline grid: `size-0`, `size-1`, `size-2`, ... `size-24`
- Component padding: standard 12px/16px/20px tiers

**Component Library**
- Buttons: primary, secondary, outline, ghost, danger, icon
- Form inputs: text, number, select, date, search, textarea
- Status badges: success, warning, error, info, neutral
- Tables: compact, normal, spacious density variants
- Cards: elevated, bordered, interactive
- Modals: small (400px), medium (600px), large (800px), custom

### 4.2 `tailwind.config.js`

**Custom tokens beyond default Tailwind:**
- `colors`: pharmacy-primary palette (emerald-based), semantic aliases
- `fontFamily`: sans → Inter variable
- `spacing`: extended grid beyond Tailwind defaults
- `borderRadius`: rounded-sm, rounded-md, rounded-lg, rounded-xl, rounded-2xl
- `boxShadow`: subtle, medium, strong, inset
- `animation`: fadeIn, slideIn, pulse

**Key plugins:**
- `@tailwindcss/forms` — uniform form element styling
- `@tailwindcss/typography` — rich text rendering (patient notes, instructions)

**CSS pipeline:**
- Entry: `app/globals.css` → imported in `app/layout.tsx`
- Variables: CSS custom properties defined in `:root` (dark + light modes)
- Tailwind directives: `@tailwind base`, `@tailwind components`, `@tailwind utilities`

---

## 5. Frontend Component & Route Map

### 5.1 App Router Structure (`app/` directory)

```
app/
├── (auth)/
│   └── login/
│       ├── page.tsx          ← LoginScreen with PIN + password
│       └── layout.tsx        ← Auth layout (full-screen, centered)
├── dashboard/
│   ├── layout.tsx            ← Main dashboard shell with sidebar nav
│   ├── page.tsx              ← Dashboard overview (metrics, shortcuts)
│   ├── reports/
│   │   └── sales/
│   │       └── page.tsx     ← Sales report view
│   ├── settings/
│   │   ├── page.tsx         ← System settings
│   │   └── users/
│   │       └── page.tsx     ← User management (RBAC)
│   ├── analytics/
│   │   └── page.tsx         ← Demand analytics + top-selling
│   └── components/            ← Dashboard-specific components
│       ├── StatsGrid.tsx
│       ├── QuickActions.tsx
│       └── RecentActivity.tsx
├── inventory/
│   ├── page.tsx              ← Inventory list with filters
│   └── [medicine_id]/
│       └── page.tsx          ← Product detail (batches, stock)
├── pos/
│   ├── page.tsx              ← POS checkout screen (cart + payment)
│   └── receipts/
│       └── [id]/
│           └── page.tsx      ← Receipt detail
├── patients/
│   ├── page.tsx              ← Patient list/search
│   └── [patient_id]/
│       └── page.tsx          ← Patient profile + history
├── prescribers/
│   └── page.tsx              ← Prescriber management
├── insurance/
│   └── page.tsx              ← Insurance plan management
├── settings/
│   └── page.tsx              ← Global settings
└── api/
    └── health/route.ts       ← Next.js API route (proxies to backend)
```

### 5.2 Core Component Library (`components/`)

| Component | Path | Purpose |
|---|---|---|
| `AppShell.tsx` | components/AppShell.tsx | Root layout shell with navigation |
| `Sidebar.tsx` | components/Sidebar.tsx | Navigation menu with RBAC-gated links |
| `Header.tsx` | components/Header.tsx | Top bar with user menu, notifications |
| `ErrorBoundary.tsx` | components/ErrorBoundary.tsx | React error boundary |
| `BootGuard.tsx` | components/BootGuard.tsx | App initialization check (license, config) |
| `LicenseGate.tsx` | components/LicenseGate.tsx | License validation wrapper |
| `GlobalHotkeys.tsx` | components/GlobalHotkeys.tsx | Keyboard shortcuts (ESC, Ctrl+K) |
| `AlertProvider.tsx` + `AlertContainer.tsx` | components/ | Toast/snackbar system |
| `I18nProvider.tsx` | components/I18nProvider.tsx | i18n context provider |
| `RegionProvider.tsx` | components/RegionProvider.tsx | Region/locale context |
| `VersionProvider.tsx` | components/VersionProvider.tsx | App version context |
| `LoadingSpinner.tsx` | components/ui/LoadingSpinner.tsx | Async loading indicator |
| `DataTable.tsx` | components/ui/DataTable.tsx | Generic table with sorting/pagination |
| `Dialog.tsx` | components/ui/Dialog.tsx | Modal dialog component |
| `Select.tsx` | components/ui/Select.tsx | Styled select dropdown |
| `Badge.tsx` | components/ui/Badge.tsx | Status badges |
| `Button.tsx` | components/ui/Button.tsx | Styled buttons |
| `Input.tsx` | components/ui/Input.tsx | Form inputs |

### 5.3 Layout Providers (`app/providers/`)

| Provider | Purpose |
|---|---|
| `QueryProvider.tsx` | TanStack Query client setup |
| `ThemeProvider.tsx` | (Inferred, not directly read) dark/light mode |

### 5.4 Layout Provider Stack (`app/layout.tsx:40-59`)

Providers are nested in this order (outer → inner):
`QueryProvider` → `I18nProvider` → `BootGuard` → `GlobalHotkeys` → `LicenseGate` → `SessionTimerProvider` → `RegionProvider` → `AlertProvider` → `ErrorBoundary` → `VersionProvider`

---

## 6. State Management (Zustand 5)

9 Zustand store files in `store/` (or `lib/store/`):

### 6.1 Store Inventory

| Store | File | State Shape | Actions |
|---|---|---|---|
| `authStore` | `store/authStore.ts` | `{ user, isAuthenticated, permissions, accessToken, refreshToken, isLoading }` | `login()`, `logout()`, `setUser()`, `restoreSession()`, `updateTokens()` |
| `cartStore` | `store/cartStore.ts` | `{ items: CartItem[], patient, prescriber, insurance }` | `addItem()`, `removeItem()`, `updateQuantity()`, `clearCart()`, `setPatient()`, `setPrescriber()`, `setInsurance()` |
| `inventoryStore` | `store/inventoryStore.ts` | `{ products, batches, stockLevels, isLoading, filters }` | `loadProducts()`, `loadBatches()`, `searchProducts()`, `setFilters()`, `refreshStock()` |
| `patientStore` | `store/patientStore.ts` | `{ currentPatient, searchQuery, searchResults, history }` | `selectPatient()`, `search()`, `loadHistory()`, `clear()` |
| `posStore` | `store/posStore.ts` | `{ shift, shiftOpen, drawerAmount, transaction, checkoutLoading }` | `openShift()`, `closeShift()`, `startCheckout()`, `completeCheckout()`, `voidItem()`, `refund()` |
| `prescriberStore` | `store/prescriberStore.ts` | `{ prescribers, selectedPrescriber }` | `loadPrescribers()`, `selectPrescriber()`, `search()` |
| `insuranceStore` | `store/insuranceStore.ts` | `{ plans, currentPlan, eligibility }` | `loadPlans()`, `selectPlan()`, `checkEligibility()` |
| `settingsStore` | `store/settingsStore.ts` | `{ settings: Record<string,string>, region, theme }` | `loadSettings()`, `updateSetting()`, `setTheme()`, `setRegion()` |
| `themeStore` | `store/themeStore.ts` | `{ mode: 'dark' \| 'light' \| 'system' }` | `setMode()`, `toggleMode()`, `syncToSystem()` |

### 6.2 Store Design Patterns

- **Typed slices**: Each store uses `create<State & Actions>()` with explicit interfaces
- **Async thunks**: Stores call `@/lib/api/*` functions (e.g., `inventoryStore.loadProducts` calls `inventoryApi.getAll()`) and update state on resolution
- **Selective subscriptions**: Components subscribe via `useStore(state => state.xxx)` to avoid re-rendering
- **Persistence**: `authStore` and `themeStore` use `persist()` middleware (localStorage)
- **No cross-store imports**: Stores are independent — no store imports another store (strict isolation)

---

## 7. Frontend API Service Layer (`lib/api/`)

30 typed API client modules, each mirroring a backend router:

| Module | Matches Router | Key Methods |
|---|---|---|
| `auth.ts` | auth_route | `login()`, `pinLogin()`, `refresh()`, `setPin()`, `getCurrentUser()`, `rotatePepper()`, `logout()` |
| `patients.ts` | patients_route | `getAll()`, `search()`, `get(id)`, `create()`, `update()`, `delete()`, `getDispenses()`, `getHistory()` |
| `inventory.ts` | inventory_route | `getAllProducts()`, `searchProducts()`, `getProduct()`, `createProduct()`, `updateProduct()`, `getBatches()`, `receiveBatch()`, `getStockLevels()`, `getLowStock()`, `getSuppliers()`, `getMovements()` |
| `pos.ts` | pos_route | `checkout()`, `approve()`, `void()`, `openShift()`, `closeShift()`, `getShiftPreview()`, `refund()`, `getSalesReport()`, `getReceipts()`, `getEODSummary()` |
| `prescribers.ts` | prescriber_route | `getAll()`, `get(id)`, `create()`, `update()`, `delete()` |
| `insurance.ts` | insurance_route | `getPlans()`, `getPlan()`, `createPlan()`, `updatePlan()`, `deletePlan()`, `validatePlan()`, `checkEligibility()` |
| `dashboard.ts` | dashboard_route | `getMetrics()` |
| `settings.ts` | settings_route | `getAll()`, `get(key)`, `update(key, value)` |
| `roles.ts` | roles_route | `getAll()`, `get(id)`, `create()`, `update()`, `getPermissions(id)`, `updatePermissions()` |
| `users.ts` | users_route | `getAll()`, `get(id)`, `update()`, `toggleActive()` |
| `audit.ts` | audit_route | `verify()`, `export()` |
| `sync.ts` | sync_route | `push()`, `pull()` |
| `analytics.ts` | analytics_route | `getDemand()`, `getTopSelling()` |
| `coupons.ts` | coupon_route | Full CRUD + `validate()` |
| `drugInteractions.ts` | drug_interaction_route | `check()`, `getAll()`, `create()`, `update()`, `delete()` |
| `drugConfirm.ts` | drug_confirm_route | `confirm()` |
| `dispense.ts` | dispense_route | `create()`, `getByRx()`, `getFills()`, `update()`, `reverse()`, `transfer()`, `get()`, `getLabel()`, `refill()` |
| `excel.ts` | excel_route | `exportInventory()`, `importInventory()`, `importCSV()` |
| `ocr.ts` | ocr_route | `extract()` |
| `invoiceParse.ts` | invoice_parse_route | `parseText()`, `parseFile()` |
| `labelTemplates.ts` | label_template_route | Template CRUD |
| `receiptTemplates.ts` | receipt_template_route | Template CRUD + `getDefault()` |
| `templates.ts` | templates_route | Template CRUD |
| `purchaseOrders.ts` | po_route | PO CRUD + item CRUD, transition |
| `vendors.ts` | vendors_route | Vendor CRUD + items, purchases, receive |
| `wc.ts` | wc_route | WC claim CRUD |
| `quickSig.ts` | quick_sig_route | Template CRUD + favorite, use, suggestions |
| `region.ts` | region_route | `detect()`, `getAll()`, `get(code)` |
| `license.ts` | license_route | `validate()`, `checkout()`, `getStatus()` |
| `email.ts` | email_route | `sendDailySales()` |
| `admin.ts` | admin_route | `backup()`, `getBackups()`, `restore()` |
| `approval.ts` | (not directly matched) | `approve()` |

### 7.1 API Client Patterns
- **Base**: `lib/api/base.ts` — shared `fetch()` wrapper with interceptors for auth token injection, error handling, and response type decoding
- **Error handling**: `ApiError` class with `status`, `code`, `message` fields; all API functions throw on non-2xx
- **Type safety**: Every method returns `Promise<SchemaType>` — backend response models are imported or re-declared in the frontend
- **Query invalidation**: TanStack Query keys match resource patterns (`['inventory', 'products', id]`)

---

## 8. Test Baseline

### 8.1 Backend Tests
| File | Tests | Status |
|---|---|---|
| `tests/test_sync.py` | T49, T50, T51 | **Green** (fix applied in `repositories.py:406`) |
| `tests/test_pin_pepper.py` | T54, T55 | **Green** (pepper security) |
| `tests/test_ram.py` | 3 tests | **Green** (pragma assertions + LRU bound) |

**Latest suite result: 81 passed, 0 failed** (from prior plan's "Status" section)

### 8.2 Frontend Tests
- **Framework**: Jest + React Testing Library (inferred from `package.json` devDeps)
- **Location**: `__tests__/` directories colocated with components
- **Coverage**: Smoke tests for LoginScreen, POS checkout, inventory search (partial)

### 8.3 Test Configuration
- `tests/conftest.py`: StaticPool SQLite engine, fresh session per request via `client` fixture
- Backend: `pytest` with `pytest-asyncio`
- Frontend: `jest.config.js` with `next/jest` preset

---

## 9. Build & Run Configuration

| File | Purpose |
|---|---|
| `package.json` | Next.js + Tailwind + TypeScript dev dependencies |
| `tsconfig.json` | TypeScript config (strict, path aliases `@/`) |
| `next.config.js` | Next.js config (Tauri compatible, SSR disabled for certain routes) |
| `tailwind.config.js` | Tailwind CSS 3 config |
| `postcss.config.js` | PostCSS with Tailwind + autoprefixer |
| `backend_fastapi/pyproject.toml` | Python dependencies (FastAPI, SQLAlchemy, aiosqlite, Pydantic) |
| `tauri.conf.json` / `tauri.conf.toml` | Tauri window config, bundle settings |
| `src-tauri/Cargo.toml` | Rust Tauri dependencies |

---

## 10. Open Items & Assumptions

1. **Migration version 21** — verified from `migrate_schema()` IF-block count. Not a formal Alembic migration.
2. **Frontend store path** — assumed `store/` directory (some imports use `@/store/`). Could be in `lib/store/`.
3. **Backend test count** — prior plan states 81 passing. Baseline count: 81 passed, 0 failed.
4. **`integrations_route.py`** — two routes share the `/api/v1` prefix (same as health_route). No conflict but unusual.
5. **`license_file_route.py`** has a separate `product_router` (`/api/v1/product-labels`) defined in the same file — dual router pattern.
6. **Backend run mode** — assumed embedded/child process (Tauri manages lifecycle). No standalone server entry point found outside `main.py`.

---

## 11. Baseline Summary

| Metric | Value |
|---|---|
| Pydantic schemas | ~100 in `schemas.py` |
| API endpoints | 187 route decorators across 29 files |
| API routers | 41 `APIRouter` definitions |
| Database tables | 12 SQLAlchemy ORM models |
| Migration version | 21 (inline Python) |
| Frontend pages (App Router) | 12+ route files |
| React components | 20+ (including UI primitives) |
| Zustand stores | 9 |
| API client modules | 30 (`lib/api/*`) |
| Backend tests | 81 passing |
| Frontend framework | Next.js 16, TypeScript, Tailwind CSS 3, React 18 |
| Backend framework | FastAPI, Python 3.12+, async aiosqlite |
| Desktop shell | Tauri 2 (Rust) |
| Design system | 2,813-line `DESIGN_SYSTEM.md`, custom Tailwind config |

**What is already built and functioning:**
- ✅ Full auth stack (password + PIN login, JWT, RBAC, pepper rotation)
- ✅ Inventory management (products, batches, suppliers, stock levels, low-stock/expiring alerts)
- ✅ POS checkout (cart, payment, shift open/close, EOD, refunds, voids)
- ✅ Patient management (CRUD, history, insurance linking)
- ✅ Prescriber management (CRUD)
- ✅ Dispense lifecycle (create, reverse, transfer, refill)
- ✅ Insurance eligibility + plan management
- ✅ Analytics (demand forecasting, top-selling)
- ✅ Admin (backup/restore, user management, roles/permissions)
- ✅ Sync protocol (push/pull for data synchronization)
- ✅ Label/receipt template system
- ✅ Coupon management + validation
- ✅ OCR invoice parsing + drug evaluation integration
- ✅ Design system with tokens + component library
- ✅ All backend tests green (81/81)
