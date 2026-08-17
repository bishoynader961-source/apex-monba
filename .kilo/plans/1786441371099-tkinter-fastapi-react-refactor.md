# MASTER IMPLEMENTATION PROMPT — Legacy Pharmacy Suite → Decoupled FastAPI + React/TS/Zustand + Tauri

> **TO THE EXECUTING AI:** This is a complete, production-grade specification. Treat it as your single source of truth. Read it in full before writing code. Build the entire refactor end-to-end per the phased protocol. You must NOT skip infrastructure, tests, or verification. Ambiguity resolves via Section 1.4 Explicit Defaults. Placeholders are forbidden (Section 2).

---

## 1. SYSTEM PERSONA & GLOBAL RULES

### 1.1 Identity
You are a **Senior Principal Full-Stack Engineer** (15+ yrs) specializing in regulated pharmacy systems, Python async backends, React/TypeScript SPAs, and desktop packaging (Tauri). You think in failure modes, data integrity, and the real cost of dispensing the wrong drug.

### 1.2 Absolute Constraints (Zero Tolerance)
- **NO PLACEHOLDERS.** Never emit `# TODO`, `# FIXME`, `...` as a body, `NotImplementedError` in shipping paths, `pass` as unfinished stub, or faked results. Every function is fully implemented.
- **NO INCOMPLETE LOGIC.** Calculations, validations, side-effects are implemented completely.
- **NO SILENT FAILURES.** Every external call has explicit, logged error handling.
- **NO SECRETS IN CODE.** All credentials/keys come from env (pydantic-settings / `.env`).
- **NO FRAMEWORK DRIFT.** Use exactly the versions in Section 3.
- **NO FEATURE CREEP.** Implement only what is specified. Simplicity First.
- **NO LOGIC LEAKAGE.** The FastAPI PMS backend and the Flask licensing microservice (`backend/app.py`) share **zero** code, imports, or data paths. They run on separate ports and processes.
- **TESTS MANDATORY.** No module is "done" without passing unit/integration tests.

### 1.3 Coding Paradigms
- **Backend:** Async-first (FastAPI + SQLAlchemy 2.0 async + `aiosqlite`). Dependency Injection via FastAPI `Depends`. Repository pattern, Service layer, strict Pydantic v2 validation at every boundary.
- **Frontend:** React 18 + TypeScript 5.5 (strict mode). Zustand for client state, TanStack Query for server cache. Container/presentational split.
- **Contracts:** Pydantic v2 schemas are the only API contract; TypeScript interfaces are generated from the live OpenAPI spec (`openapi-typescript`) — frontend types cannot drift.
- **Legacy DB:** Backend reads/writes the **existing** `pharmacy.db` and `inventory.db` SQLite files directly. Do NOT recreate or wipe them. Schema is introspected and mapped; migrations are additive only.

### 1.4 Explicit Defaults (resolve ambiguity here, no asking)
- Timezone: **UTC** for storage; display tz per-pharmacy config.
- Money: `Decimal` in Python/Pydantic; SQLite stores `REAL` → round to 2 dp on write, parse to Decimal on read. Never compare floats.
- Quantities: 3-decimal precision (fractional units).
- IDs: UUIDv4 for new entities; legacy integer PKs preserved as-is.
- Soft deletes where the legacy schema lacks them: add `deleted_at` only via additive migration; never alter existing columns destructively.
- Python: **3.12+**. Node: **20 LTS**.

---

## 2. PROJECT SCOPE & ARCHITECTURE BLUEPRINT

### 2.1 Goal
Transform the monolithic, tightly coupled CustomTkinter application (`archive/ui_*.py`, wired through a `PharmacyApp` god-object via `self.app.currency`, `self.app.*`) into a decoupled, type-safe distributed system:
- **Stateless FastAPI backend** = single source of truth (business rules, auth, persistence).
- **Modular React 18 SPA** = thin, type-safe view (Zustand state, React Query cache).
- **Desktop shell (Tauri or Electron)** = hosts the SPA WebView + spawns the FastAPI sidecar + bridges hardware (barcode scanner, thermal printer).
- **Flask licensing microservice (`backend/app.py`)** = preserved, isolated, separate port.

### 2.2 Component Topology
```
┌──────────────────────────────────────────────────────────────┐
│ Desktop Shell (Tauri)                                          │
│  ├─ WebView: React 18 + TS 5.5 SPA (Zustand + React Query)     │
│  ├─ Sidecar: uvicorn FastAPI (localhost:${API_PORT})           │
│  └─ Hardware bridge: scanner (HID/serial), printer (ESC/POS)   │
└───────────────┬───────────────────────────┬───────────────────┘
                │ REST/JSON (axios+JWT)      │ isolated, separate port
                ▼                            ▼
        FastAPI (PMS backend)        Flask (backend/app.py licensing)
          async SQLAlchemy            Lemon-Squeezy webhooks + /api/validate
          ├─ pharmacy.db (aiosqlite)  └─ license_db.sqlite
          └─ inventory.db (aiosqlite)
```
**Zero leakage rule:** FastAPI must never import `backend/app.py`, `license_gate.py`, or any Flask/licensing symbol. Licensing state is consumed by the shell only (e.g., shell calls Flask `/api/validate` before launching/permitting the sidecar).

### 2.3 Exact Directory Structure (create verbatim)
```
pharmacy_suite/
├── README.md
├── .env.example
├── docker-compose.yml            # optional: FastAPI + (reference) Flask
├── backend/                      # NEW FastAPI PMS backend (PMS logic only)
│   ├── pyproject.toml
│   ├── alembic.ini               # additive migrations for the two legacy DBs
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── main.py               # FastAPI app factory, /health, routers
│   │   ├── core/
│   │   │   ├── config.py         # pydantic-settings: DB paths, JWT, CORS
│   │   │   ├── security.py       # JWT, bcrypt, deps
│   │   │   ├── db.py             # 2 async engines (pharmacy, inventory) + aiosqlite + WAL
│   │   │   ├── logging.py        # structlog JSON + request_id
│   │   │   ├── errors.py         # standardized error envelope + handlers
│   │   │   └── dependencies.py   # get_current_user, require_permissions
│   │   ├── models/
│   │   │   ├── pharmacy.py       # maps pharmacy.db tables
│   │   │   └── inventory.py      # maps inventory.db tables
│   │   ├── schemas/              # Pydantic v2 request/response contracts
│   │   │   ├── common.py         # ErrorEnvelope, PageMeta
│   │   │   ├── auth.py
│   │   │   ├── product.py
│   │   │   ├── inventory.py
│   │   │   └── pos.py
│   │   ├── repositories/
│   │   │   ├── base.py
│   │   │   ├── product_repo.py
│   │   │   └── inventory_repo.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── inventory_service.py
│   │   │   ├── config_service.py
│   │   │   └── pos_service.py
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   ├── auth_routes.py
│   │   │   ├── product_routes.py
│   │   │   ├── inventory_routes.py
│   │   │   ├── pos_routes.py
│   │   │   └── config_routes.py
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_auth.py
│   │       ├── test_inventory.py
│   │       └── test_pos.py
│   └── scripts/
│       └── introspect_legacy.py  # prints legacy schema for mapping validation
├── frontend/                     # NEW React 18 + TS 5.5 SPA
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json             # strict: true, noImplicitAny, etc.
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── openapi.ts.config.json    # openapi-typescript config
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── router.tsx
│       ├── api/
│       │   ├── client.ts         # axios + Bearer + error envelope parse
│       │   ├── types.ts          # GENERATED from OpenAPI (do not hand-edit)
│       │   ├── auth.ts
│       │   ├── products.ts
│       │   ├── inventory.ts
│       │   └── pos.ts
│       ├── store/
│       │   ├── authStore.ts      # Zustand
│       │   ├── cartStore.ts      # Zustand (POS line items)
│       │   └── uiStore.ts        # Zustand
│       ├── lib/
│       │   ├── format.ts         # currency/tax from /config
│       │   ├── guards.ts         # RBAC can(user, perm)
│       │   └── zod.ts            # form schemas mirror Pydantic
│       ├── components/
│       │   ├── ui/ (Button, Input, Table, Modal, Badge, Spinner)
│       │   └── layout/ (AppShell, Sidebar, Topbar)
│       ├── features/
│       │   ├── auth/ (LoginPage, ResetPasswordPage)
│       │   ├── pos/ (PosPage, CartPanel, CheckoutDialog)
│       │   └── inventory/ (InventoryListPage, ReceiveDialog, AdjustDialog)
│       └── styles/index.css
└── shell/                        # Tauri (preferred) desktop wrapper
    ├── package.json
    ├── tauri.conf.json           # sidecar config, WebView→frontend/dist
    ├── src/ (shell entry, hardware bridge)
    └── src-tauri/
        ├── Cargo.toml
        ├── tauri.conf.json
        └── src/main.rs           # spawn FastAPI sidecar, health-check /health
```
> NOTE: `backend/app.py` (Flask licensing) and `license_gate.py` (legacy Tkinter gate) are **out of scope for rewrite**. `license_gate.py` is retired when the Tauri shell replaces the desktop launch path. The Flask service keeps running unchanged on its own port.

---

## 3. COMPREHENSIVE TECH STACK & DEPENDENCIES

### 3.1 Backend (Python 3.12+)
| Package | Version | Purpose |
|---|---|---|
| python | 3.12.x | Runtime |
| fastapi | >=0.115,<1.0 (pin latest stable) | HTTP framework |
| uvicorn[standard] | >=0.30 | ASGI server |
| pydantic | 2.7.x+ | Validation (v2) |
| pydantic-settings | 2.3.x+ | Env config |
| sqlalchemy | 2.0.x (async) | ORM |
| aiosqlite | 0.20.x+ | Async SQLite driver |
| alembic | 1.13.x+ | Additive migrations |
| python-jose[cryptography] | 3.3.x | JWT |
| passlib[bcrypt] | 1.7.x | Password hashing |
| bcrypt | 4.1.x | Hash backend |
| slowapi | 0.1.x | Rate limiting |
| httpx | 0.27.x | Outbound (if needed) |
| structlog | 24.1.x | Structured logging |
| mypy | 1.10.x+ | Static typing (100% coverage gate) |
| pytest | 8.2.x+ | Testing |
| pytest-asyncio | 0.23.x+ | Async tests |
| asgi-lifespan | 2.1.x | Test app lifespan |

### 3.2 Frontend (Node 20 LTS)
| Package | Version | Purpose |
|---|---|---|
| vite | 5.3.x | Build/dev |
| react | 18.3.x | UI |
| react-dom | 18.3.x | UI |
| typescript | 5.5.x | Typing (strict) |
| react-router-dom | 6.24.x | Routing |
| zustand | 4.5.x | State |
| @tanstack/react-query | 5.4.x+ | Server cache |
| axios | 1.7.x | HTTP |
| tailwindcss | 3.4.x | Styling |
| postcss / autoprefixer | 8.4 / 10.4 | CSS |
| react-hook-form | 7.52.x | Forms |
| zod | 3.23.x | Validation |
| @headlessui/react | 2.0.x | A11y primitives |
| openapi-typescript | 7.x | Generate `api/types.ts` |
| lucide-react | 0.4xx | Icons |
| date-fns | 3.6.x | Dates |
| tsc / @types | — | Type checking |

### 3.3 Desktop Shell
- **Tauri 1.6+/2.x** (preferred: lightweight, spawns Python sidecar cleanly, native WebView).
- Fallback: **Electron 30.x** if Tauri packaging is blocked (document reason).
- Hardware: barcode scanner via HID (keyboard-wedge → standard input focus) or `@tauri-apps/plugin-serial`; thermal printer via ESC/POS through `@tauri-apps/plugin-shell`/`@tauri-apps/plugin-serial` or `node-thermal-printer` (Electron).

### 3.4 Environment (`.env.example`)
```
PHARMACY_DB_PATH=./pharmacy.db
INVENTORY_DB_PATH=./inventory.db
JWT_SECRET_KEY=change-me
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
CORS_ORIGINS=http://localhost:1420,http://localhost:5173
API_PORT=8000
FLASK_LICENSING_URL=http://localhost:5000
ENVIRONMENT=development
```
Flask service (`backend/app.py`) keeps its own config untouched.

---

## 4. DATA MODELS, SCHEMAS & STATE MANAGEMENT

### 4.1 Legacy Schema Mapping (introspect, do not recreate)
Run `python backend/scripts/introspect_legacy.py` to print live tables. Map:
- **pharmacy.db** tables (e.g., `products`, `system_settings`, `rx_table`, `prescriber_table`, `insurance_table`, `audit_logs`) → `backend/app/models/pharmacy.py` async SQLAlchemy models.
- **inventory.db** tables (e.g., `inventory_extended`, batch/lot, on_hand, expiry) → `backend/app/models/inventory.py`.
- Preserve all existing columns and integer PKs exactly. Additive-only: new columns (e.g., `deleted_at`, `updated_at`) via Alembic with `render_as_batch=True` (SQLite-safe).

### 4.2 Validation Rules (Pydantic v2)
- Email: `EmailStr`. Password: ≥12 chars, upper+lower+digit+symbol (enforced at registration).
- Monetary fields: `Decimal(14,2)`, non-negative; **totals always recomputed server-side**, never trusted from client.
- Quantities: `Decimal(14,3)`, non-negative; stock adjustments reject negative resulting balance (raise `DomainError` → 422).
- `sku`/`barcode` unique → 409 on duplicate.
- Money: parse SQLite `REAL` to `Decimal` on read; round to 2 dp on write.

### 4.3 Contracts & Type Sync (anti-`AttributeError` guarantee)
1. Every endpoint request/response uses a Pydantic v2 schema. FastAPI emits `/openapi.json`.
2. Frontend runs `openapi-typescript` against the running backend to generate `src/api/types.ts` (committed, regenerated in CI). Feature code imports these types — **no `any`**.
3. Runtime form validation via Zod mirrors Pydantic; React Query types responses with generated types.

### 4.4 State Management (Frontend)
- **Zustand:** `authStore` (token/user/permissions, persisted to `localStorage`), `cartStore` (POS line items, discounts), `uiStore` (sidebar/toasts/modals).
- **TanStack Query:** owns all server cache; mutations invalidate on success.
- `lib/format.ts` derives currency/tax formatting from `GET /config` (replaces legacy `self.app.currency.fmt`).

---

## 5. API CONTRACT & ROUTING SPECIFICATIONS

### 5.1 Conventions
- Base `/api/v1`. JSON bodies. ISO-8601 UTC timestamps.
- Auth: Bearer JWT `Authorization: Bearer <token>`.
- **Error envelope (MANDATORY):**
  ```json
  { "error": { "code": "STRING_CODE", "message": "human readable", "details": {} } }
  ```
  Success list: `{ "data": [...], "meta": { "page": int, "limit": int, "total": int } }`.
- **Status codes:** 200, 201, 204, 400 (validation), 401, 403, 404, 409, 422 (business rule), 429, 500. Never leak stack traces. Every response carries `X-Request-ID`.

### 5.2 Endpoints (MVP scope: auth, config, products, inventory, pos)
- `GET /health` → 200 `{status:"ok"}` (used by shell sidecar health-check).
- `POST /auth/login` `{email,password}` → 200 `{access_token, user}`.
- `POST /auth/refresh`, `POST /auth/logout`, `GET /users/me`.
- `GET /config` → 200 `{currency, tax_rate, pharmacy_name, locale}` (replaces `self.app` shared services).
- `GET /products?q=&page=&limit=` → list; `GET /products/{id}`; `POST /products`; `PATCH /products/{id}`.
- `GET /inventory?low_stock=true` → stock levels; `POST /inventory/receive` `{product_id,batch_lot,quantity,unit_cost,expiry_date}`; `POST /inventory/adjust` `{inventory_item_id,delta,reason}` (rejects negative result → 422); `GET /inventory/alerts`.
- `POST /pos/checkout` `{items:[{product_id,quantity}], discounts:[], payment:{method,amount}}` → single async transaction: validate stock → recompute totals → create sale + items → FIFO-decrement inventory (both DBs) → return 201 `{sale, receipt}`. 422 on insufficient stock / over-under payment.

---

## 6. UI/UX & COMPONENT DESIGN SYSTEM

- **Tailwind 3.4** with constrained design tokens in `tailwind.config.js` (clinical teal primary `#0f766e`, danger `#dc2626`). `prefers-color-scheme` dark variant.
- **Layout:** `AppShell` = `Sidebar` (role-filtered) + `Topbar` (user, location, logout). Responsive: icon rail < 1024px, drawer < 640px. POS two-pane desktop, stacked mobile.
- **A11y (WCAG 2.1 AA):** all inputs labelled; contrast ≥4.5:1; `aria-live` toasts; focus traps in modals (`@headlessui/react` Dialog); status conveyed by text+icon, not color alone.
- **Screens:** Login; POS (barcode/SKU search, cart, discount, tender, print receipt via shell printer bridge); Inventory (filterable table, receive/adjust dialogs, alerts).

---

## 7. ERROR HANDLING & SECURITY PROTOCOLS

- **Envelope:** `core/errors.py` translates domain exceptions → `{error:{code,message,details}}` + correct status. `DomainError` → 422 with `code`. Unexpected → 500 with `request_id`, logged, generic message to client.
- **Security:** bcrypt cost 12; JWT HS256 short-lived + refresh; `require_permissions` dependency → 403 when lacking; all SQL via SQLAlchemy parameterized (no string-built SQL); `slowapi` limits `/auth/*` to 10/min/IP; CORS strict allowlist (no wildcard in prod); audit every mutation to `audit_logs`; secrets from env only.
- **Isolation:** FastAPI imports nothing from `backend/app.py` or `license_gate.py`. Shell performs licensing via Flask `/api/validate` independently.
- **Logging:** `structlog` JSON; every line `{timestamp, level, request_id, actor_id, action, message}`; redact password/token/card fields.

---

## 8. PHASED EXECUTION ROADMAP (one phase at a time, verify before next)

Execute phases **sequentially**. Complete and verify each before starting the next. Do not parallelize in a way that skips verification.

### Phase 0 — Scaffold & Isolate
- Create `backend/`, `frontend/`, `shell/` per Section 2.3. Leave `backend/app.py` (Flask) and `license_gate.py` untouched.
- Pin versions (Section 3). `.env.example`.
- Implement `introspect_legacy.py` and run it to capture both schemas.
- **Verify:**
  ```bash
  cd backend && python -m pytest --collect-only -q && mypy app --strict
  cd ../frontend && npm install && npm run build && npm run typecheck
  cd ../shell && npm install && npm run tauri build   # or electron build
  # Confirm Flask service still starts independently:
  cd ../backend && python app.py   # (separate terminal/port)
  ```

### Phase 1 — Data Foundation (kill dual data layer, map legacy)
- Async engines for `pharmacy.db` + `inventory.db` (aiosqlite, WAL `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, pooled `timeout`).
- SQLAlchemy 2.0 async models mapping existing tables; Alembic init (additive migrations, `render_as_batch=True`).
- **Verify:**
  ```bash
  cd backend && python -m pytest tests/test_db_connection.py -q && mypy app --strict
  # Assert both DBs open, tables introspect, WAL enabled.
  ```

### Phase 2 — Auth, Config & Contracts
- `auth_service` (JWT, bcrypt), `GET /config`, `GET /users/me`, error envelope + handlers, `/health`.
- Generate `frontend/src/api/types.ts` from `/openapi.json`; wire axios Bearer + React Query + `authStore`.
- **Verify:**
  ```bash
  cd backend && python -m pytest tests/test_auth.py -q && mypy app --strict
  cd ../frontend && npm run typecheck && npm test
  # Contract parity gate: regenerate types, confirm git diff only expected.
  ```

### Phase 3 — Inventory Module (replaces `ui_inventory_tab.py`)
- `inventory_service`: CRUD, `receive`, `adjust` (negative-guard), `alerts`. All audited.
- React `InventoryListPage`, `ReceiveDialog`, `AdjustDialog` (Zod + a11y).
- **Verify:**
  ```bash
  cd backend && python -m pytest tests/test_inventory.py -q && mypy app --strict
  cd ../frontend && npm run typecheck && npm run build
  # Manual: receive/adjust mutate SQLite to 3-dp; negative rejected; audit row written.
  ```

### Phase 4 — POS Module (replaces `ui_pos_terminal.py`)
- `pos_service.checkout`: async transaction across both DBs; server-computed totals; FIFO decrement; receipt.
- React `PosPage` + `cartStore` + `CheckoutDialog`; barcode search.
- **Verify:**
  ```bash
  cd backend && python -m pytest tests/test_pos.py -q && mypy app --strict
  cd ../frontend && npm run typecheck && npm run build
  # Atomicity: inject failure mid-txn → full rollback; inventory unchanged.
  # Parity: same cart → same total as legacy ui_pos_terminal math.
  ```

### Phase 5 — Desktop Shell Integration
- Tauri: spawn FastAPI sidecar at boot; WebView → `frontend/dist`; shell calls Flask `/api/validate` (isolated) before permitting sidecar; hardware bridge (scanner HID/serial, ESC/POS printer).
- **Verify:**
  ```bash
  cd shell && npm run tauri build
  # Launch packaged app: sidecar /health OK → SPA loads → full POS flow works offline (no external server).
  # Scanner injects barcode into search; printer emits receipt.
  ```

### Phase 6 — Hardening & Cutover
- structlog review, redaction, rate-limit, CORS strictness, RBAC-lite.
- Retire `license_gate.py` launch path (superseded by shell). Archive legacy `archive/` (read-only, do NOT delete).
- **Verify:**
  ```bash
  cd backend && python -m pytest -q && mypy app --strict
  cd ../frontend && npm run typecheck && npm run build
  cd ../shell && npm run tauri build
  # Grep gate: no '# TODO'|'...'|'NotImplementedError' in shipping code.
  # Confirm Flask service still runs untouched on its port.
  ```

---

## COMPONENT RESPONSIBILITY MATRIX
| Concern | FastAPI Backend | React Frontend | Legacy DB | Flask Licensing | Tauri Shell |
|---|---|---|---|---|---|
| Auth/JWT | ✅ source of truth | stores token, sends Bearer | users table | — | validates via Flask pre-launch |
| Business rules/totals | ✅ authoritative | never computes | — | — | — |
| Inventory/stock math | ✅ txn across both DBs | sends lines, shows result | pharmacy.db, inventory.db | — | — |
| Product catalog | ✅ CRUD + search | search UI, cache | products table | — | — |
| Currency/tax/i18n | ✅ `/config` | formats from config | system_settings | — | — |
| Licensing | ❌ isolated | ❌ | — | ✅ only | ✅ calls Flask |
| Hardware (scan/print) | ❌ | triggers via bridge | — | — | ✅ bridges HID/serial/printer |
| Persistence | ✅ async SQLAlchemy | ❌ | SQLite files | SQLite license_db | spawns backend |

---

## FINAL ACCEPTANCE CRITERIA
1. `pytest` green; `mypy --strict` 100% coverage on `backend/app`; `npm run typecheck` + `npm run build` clean; `tauri build` succeeds.
2. `src/api/types.ts` generated from live OpenAPI and compiles — contract parity enforced.
3. End-to-end in packaged shell: login → `/config` → receive stock → POS checkout decrements inventory (both DBs) with server-computed totals + audit row.
4. Flask `backend/app.py` runs unchanged on its own port; FastAPI imports zero licensing symbols (verified by grep).
5. No `# TODO`, `...`, `NotImplementedError`, or placeholder strings in shipping code.
6. Legacy `self.app.*` god-object pattern fully eliminated; no `AttributeError` init crashes.
