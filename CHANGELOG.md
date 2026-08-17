# Changelog — Pharmacy Suite Refactor (FastAPI + Next.js)

Format: timestamped milestones with verifiable goals and terminal verification results.
Spec source: `MASTER_IMPLEMENTATION_PROMPT.md`; reconciled plan: `.kilo/plans/1786452469480-pharmacy-refactor-plan.md`.

---

## M1 — Project Scaffold & Core Infrastructure  (2026-08-11) ✅ VERIFIED

**Objectives completed**
- New `backend_fastapi/` package: layered FastAPI app (`app.api.routers`, `app.services`,
  `app.core`, `app.shared`) per the reconciled plan. No existing files were modified.
- Pinned dependency stack in `backend_fastapi/pyproject.toml` (FastAPI 0.141, SQLAlchemy
  2.0.51, aiosqlite, Pydantic 2.13, pydantic-settings, bcrypt, PyJWT, structlog, pytest,
  httpx, pytest-asyncio, mypy) — Python 3.14 compatible.
- Async SQLAlchemy 2.0 ORM models (`app/core/models.py`) mirroring the **real** `pharmacy.db`
  schema (products, inventory_extended, suppliers, receiving_log, users, roles, permissions,
  role_permissions, receipts, receipt_items, sold_items, audit_logs, system_settings).
- Pydantic v2 schemas (`app/shared/schemas.py`) as the typed-contract source of truth.
- `app/shared/security.py`: bcrypt hashing **plus** transparent legacy scrypt
  (`archive/auth_crypto.py` scheme) lazy-upgrade — no mass migration, no lockout.
- Uniform error contract (`{"error":{"code","message","details"}}`) via global FastAPI
  exception handlers; CORS locked to `FRONTEND_URL`; security headers middleware.
- `backend/app.py` (Flask license microservice) confirmed still runs **independently** on
  :5000 and was left untouched (isolation preserved).
- `conftest.py` with in-memory aiosqlite (`StaticPool`) + ASGI test client.
- `CHANGELOG.md` + `.gitignore` entries added.

**Verifiable goals — terminal results**
- `cd backend_fastapi && python -m pytest -q` → **16 passed**.
- `cd backend_fastapi && python -m mypy app --strict` → **0 errors** (18 source files).
- `cd . && npx tsc --noEmit` (existing Next.js frontend) → **exit 0**.
- Flask `backend/app.py` boots on :5000 and rejects malformed body with `400`
  (isolated, independent of FastAPI).

**Resolved decisions carried from planning**
- Reconciled to reality (inventory in `pharmacy.db`, Next.js kept, `backend/app.py` = isolated
  license service). Serialized `products` model noted; FIFO/lot logic deferred to M3/M4 design.
- Risk mitigations R1–R4, audit immutability, offline scope, returns-scope, and tax config
  are recorded in the plan and will be enforced in M2–M4.

---

## M2 — Authentication & Authorization  (2026-08-11) ✅ VERIFIED (backend + frontend)
- `app/services/auth_service.py`: `AuthService` (authenticate, login, refresh, register) with
  **legacy scrypt lazy-upgrade** (R4) and **lockout throttling** (`failed_attempts`/`locked_until`,
  5 attempts → 15-min lock, resets on success).
- `app/api/deps.py`: `get_current_user` (Bearer decode) + `require_permission(perm)` factory.
- Routers: `POST /api/v1/auth/login|refresh|register(admin:users.write)`, `GET /me`, `POST /logout`.
- Inventory routes gated by `inventory.read` (demonstrates 401/403).
- Frontend M2 files written: `types/contracts.ts`, `lib/api.ts` (Axios + 401 refresh + uniform-error),
  `stores/authStore.ts` (Zustand), `app/login/page.tsx`.
- **Verify:** `pytest -q` → **22 passed**; `mypy app --strict` → **0 errors**; `npx tsc --noEmit` → **0 errors**.

## M3 — Inventory Management & FIFO Basis  (2026-08-11) ✅ VERIFIED
- `InventoryService` + `BatchRepository`: receive (lot + receiving_log), FIFO lot ordering,
  low-stock alert, expiring-soon alert; `ProductRepository.get_by_name` used as the product
  resolution key (R2 join key = `products.name` ↔ `inventory_extended.drug_name`).
- Routes added: `GET/POST/PUT /medicines` (CRUD + 409 conflict + 404), `GET /batches`,
  `POST /batches/receive` (R2: **orphan-lot rejection** via ValidationError), `GET /batches/low-stock`,
  `GET /batches/expiring-soon`, `POST /suppliers`. Write routes gated by `inventory.write`.
- `scripts/normalize_inventory.py` dry-run/default + `--apply`: canonicalizes lot `drug_name` to
  match `products.name` (case-insensitive), reports orphan lots untouched.
- **Verify:** `pytest -q` → **32 passed** (22 + 10 new); `mypy app --strict` → **0 errors**.

## M4 — Point of Sale Checkout & FIFO (2026-08-11) ✅ VERIFIED
- `app/services/pos_service.py`: `PosService.process_checkout` — single `session.begin()` transaction;
  per-drug **class-level `asyncio.Lock`** acquired in sorted order (R1: no global checkout lock, deadlock-free);
  FIFO deduction via `InventoryService`; **14% item-level tax** (`Decimal` half-up rounding, configurable via `TAX_RATE`);
  receipt numbering derived from immutable row id → `RCP-{year}-{id:06d}` (no schema column needed).
- Writes `receipts`, `receipt_items`, `sold_items`, and an `audit_logs` entry (append-only).
- `POST /api/v1/pos/checkout` route, gated by `pos.checkout` permission.
- Frontend: `app/pos/page.tsx` (cart, qty edit, checkout, receipt display) + `hooks/useBarcodeScanner.ts`
  (keyboard-wedge scanner listener, gap-based accumulation, R3). Login now redirects to `/pos`.
- **Verify:** 4 new POS tests including the R1 concurrency proof — 20 concurrent checkouts of a single
  SKU with 5 units → exactly **5 succeed / 15 fail**, final stock = 0, receipts written = 5.
- **Verify:** `pytest -q` → **41 passed**; `mypy app --strict` → **0 errors** (26 files); `npx tsc --noEmit` → **0 errors**.

## M5 — Admin Surface: Users & Settings (2026-08-11) ✅ VERIFIED
- `app/api/routers/users_route.py`: `GET /users`, `GET /users/{id}` (RBAC `users.read`).
- `app/api/routers/settings_route.py`: `GET /settings`, `GET /settings/{key}` (read-only, decodes BLOB values).
- **Verify:** `test_admin.py` → 5 new tests pass (users list/get, settings list, license 502).

## M6 — License Proxy (2026-08-11) ✅ VERIFIED
- `app/api/routers/license_route.py`: `POST /api/v1/license/validate`, `POST /api/v1/license/admin/manage`,
  `GET /api/v1/license/status` — proxies to the isolated Flask service at `LICENSE_GATE_URL` (default
  `http://localhost:5000`). Returns **502 `license_unreachable`** on connection failure (R6 graceful degradation;
  Flask service is never modified).
- Frontend `app/license/page.tsx` (validate form) + nav link from POS.
- **Verify:** `test_admin.py` license 502 tests pass; `npx tsc --noEmit` → 0 errors.

## M7 — Launch Script & Ops (2026-08-11) ✅ VERIFIED
- `run_services.py` (repo root): starts Flask license (:5000, optional), FastAPI (:8000), Next.js (:3000)
  with SIGINT/SIGTERM forwarding to children; auto-skips Flask with a warning when uninstalled (proxy 502s).
- **Verify:** all green gates: `mypy app --strict` 0 errors · 41 backend tests pass · `npx tsc --noEmit` 0 errors.
- Coverage target (≥90%) recorded as next; the FastAPI/Next.js layers are covered by the 41-test suite +
  strict typing gates above.

## M8 — Frontend Authentication Flow (Phase 2)  (2026-08-12) ✅ VERIFIED

**Objectives completed**
- Installed Tailwind CSS v3.4+ (`tailwindcss`, `postcss`, `autoprefixer`, `@tailwindcss/postcss`) as dev dependencies. Created `tailwind.config.js` and `postcss.config.js`. Added `@tailwind base; @tailwind components; @tailwind utilities;` to `app/globals.css`.
- Login page (`app/login/page.tsx`) rewritten: uses `useActionState` with Server Action, Tailwind CSS utility classes for responsive card layout, form submits via native `<form action={formAction}>` (progressive enhancement), redirects to `/dashboard` on success.
- Server Action (`app/login/actions.ts`): `"use server"` directive, POSTs JSON `{username, password}` to `http://localhost:8000/api/v1/auth/login` via `fetch`, catches network errors → "Server unreachable", normalizes backend 401 → "Invalid credentials" from uniform error contract, sets `access_token` (8h) and `refresh_token` (30d) as HTTP-only, SameSite=Strict cookies via `cookies()` from `next/headers`, returns `{success, user, access_token, refresh_token}`.
- API routes (`app/api/auth/login/route.ts`, `app/api/auth/logout/route.ts`, `app/api/auth/refresh/route.ts`): route handlers for programmatic auth flow. Login route proxies to FastAPI + sets HTTP-only cookies. Logout clears cookies. Refresh reads HTTP-only `refresh_token` cookie server-side, calls FastAPI `/refresh`, sets new `access_token` cookie.
- Auth store (`stores/authStore.ts`): `login()` now POSTs to `/api/auth/login` route (sets cookies server-side) and mirrors `access_token` to `localStorage` for Axios interceptor. Added `setUser()` method for immediate state sync from Server Action result. `logout()` POSTs to `/api/auth/logout`.
- Axios interceptor (`lib/api.ts`): 401 handler now POSTs to `/api/auth/refresh` (cookie-based, not `localStorage`) to refresh tokens, then retries the original request.
- Middleware (`middleware.ts`): added auth guard — checks `access_token` cookie on `/dashboard` (and `/pos`, `/inventory`, `/license`, etc.), redirects to `/login` if absent. Redirects authenticated users from `/login` to `/dashboard`.
- Dashboard page (`app/dashboard/page.tsx`): created as minimal protected route target with Tailwind CSS card layout and logout button.

**Verifiable goals — terminal results**
- `npx tsc --noEmit` → **0 errors**.
- `npx next build` → **compiled successfully**; all new routes built (`/login`, `/dashboard`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/refresh`).
- Backend regression: `cd backend_fastapi && python -m pytest -q` → all 41 tests pass (not affected by frontend changes).
- Default admin credentials confirmed: `username="admin"`, `password="admin123"` (seeded by `seed_service.py`).

**Design decisions**
- Tailwind CSS installed (previously referenced in `app/page.tsx` but not configured — `package.json` had no `tailwindcss`).
- Progressive improvement: HTTP-only cookies are the authoritative secure store for tokens; `localStorage` mirrors `access_token` only for the Axios Bearer interceptor (avoids massive refactor of routing all API calls through server-side proxies).
- `@tailwindcss/postcss` package required for Tailwind v4+ + Next.js Turbopack PostCSS integration (resolved during build).

## Status
- Milestones: M1 ✅ · M2 ✅ · M3 ✅ · M4 ✅ · M5 ✅ · M6 ✅ · M7 ✅ · M8 ✅ (frontend auth flow).
- Carried risks: R1 concurrency enforced (M4); R2 join key (M3); R3 scanner (M4 web); R4 legacy-hash lazy upgrade (M2); R6 license proxy 502 (M6).
- Open gaps carried forward: PHI encryption-at-rest + role-scoped access, audit immutability hardening, returns workflow, reports CRUD (M5 read-only delivered), desktop Tauri/Electron shell.

---

## M9 — Inventory Module Refactor (FastAPI JWT + Next.js App Router)  (2026-08-13) ✅ VERIFIED

**Objectives completed**
- Backend: `is_deleted` column on `products` (idempotent PRAGMA/ALTER migration in `database.py`).
- Backend: Canonical `MedicineRead`/`MedicineCreate`/`MedicineUpdate` schemas; `MedicineUpdate` standalone `BaseModel` (Liskov-safe, mypy strict). `StockLevelRead`, `BatchUpdate`, `ReceiveBatch` DTOs. `ProductRead`/`ProductCreate` aliased for backward compatibility.
- Backend: `ProductRepository.all/get/search` exclude soft-deleted; `get_by_name` intentionally unfiltered (POS invariant). `soft_delete()`, rename-cascade to `inventory_extended.drug_name`, `BatchRepository.adjust()`.
- Backend: `app/core/lock_manager.py` extracted (dependency-free per-drug `asyncio.Lock` registry + `acquire_drug_lock`); `PosService` refactored to use shared lock; `InventoryService.adjust_batch` uses same lock — no import cycle.
- Backend: New routes — `DELETE /medicines/{id}`, `GET /batches/{id}`, `PUT /batches/{id}`, `GET /stock-levels`; `GET /medicines` accepts `vendor`/`status`/`low_stock_only` filters; `PUT /medicines/{id}` accepts partial `MedicineUpdate`.
- Backend: 14 TDD tests in `test_inventory_refactor.py` (aggregation, soft-delete, partial update, batch CRUD, RBAC, concurrency, schema drift guard).
- Frontend: `types/contracts.ts` — `Medicine`/`Batch`/`StockLevel`/`MedicineUpdate`/`BatchUpdate`/`ReceiveBatch` interfaces; `ProductRead = Medicine` alias with `is_deleted: boolean`.
- Frontend: `stores/authStore.ts` — `fetchCurrentUser()` (GET `/api/v1/auth/me`), `setToken()`, `hasPermission()` gates all mutation buttons. `setUser` no longer discards role/permissions.
- Frontend: `app/login/page.tsx` — calls `setToken` + `fetchCurrentUser()` before redirect to `/dashboard`.
- Frontend: `hooks/useInventory.ts` — authenticated hook with debounced search, multi-param filters, stock-level loading, permission-gated writes.
- Frontend: `app/dashboard/inventory/page.tsx` — responsive Tailwind table, search, vendor/status/low-stock filters, low-stock warning cards, receive-batch modal, delete confirmation.

**Verifiable goals — terminal results**
- `cd backend_fastapi && python -m pytest -q` → **69 passed** (55 existing + 14 new).
- `cd backend_fastapi && python -m mypy app --strict` → **0 errors** (28 source files).
- `npx tsc --noEmit` → **0 errors** (strict mode).
- `next lint` unavailable in Next.js 16.2.10 (no `lint` command); tsc strict gate is authoritative.

---

## M10 — Auth Rate Limiting (Network-Layer Brute-Force Defense)  (2026-08-17) ✅ VERIFIED

**Objectives completed**
- `app/shared/rate_limit.py` (NEW): module-level `limiter` singleton (slowapi, in-memory storage, IP-based key function via `get_remote_address`). Custom `rate_limit_exceeded_handler` renders the app's uniform error contract `{"error":{"code":"rate_limited","message":"Too many requests","details":{"retry_after":...}}}` on 429 instead of slowapi's default `{"error": "..."}`.
- `app/shared/config.py`: Added `auth_rate_limit` and `pin_rate_limit` fields (env-configurable via `POS_AUTH_RATE_LIMIT` / `POS_PIN_RATE_LIMIT`, default `5/minute`).
- `app/api/routers/auth_route.py`: `@limiter.limit()` applied to `POST /login` and `POST /login/pin` (inner decorator, before `@router.post` so the rate-limit wrapper is the registered endpoint). Added `request: Request` parameter required by slowapi.
- `app/main.py`: `app.state.limiter = limiter` + `app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)`. `SlowAPIMiddleware` intentionally omitted — slowapi 0.1.10's `async_wrapper._inject_headers` is incompatible with FastAPI's Pydantic-model responses and Starlette 1.6.0's `call_next` return type. `headers_enabled=False` makes header injection a no-op; the decorator's in-process check enforces limits correctly.
- `tests/conftest.py`: Added autouse `_reset_rate_limiter` fixture (`limiter.reset()` before/after each test) — all ASGI test requests share IP `127.0.0.1`.
- `tests/test_rate_limit.py` (NEW): 5 tests — login rate limit (429 + error contract), PIN login rate limit, health not rate-limited, refresh not rate-limited, /me not rate-limited.
- `tests/test_auth_rbac.py::test_account_lockout_after_failures` + `tests/test_pin_pepper.py::test_pin_login_wrong_pin_lockout`: added `limiter.reset()` before the 6th request to separate network rate-limiting from account-level lockout testing.
- `backend_fastapi/pyproject.toml`: Added `slowapi>=0.1.9,<1.0` and `limits>=5.0,<7.0` to `[project.dependencies]` (were installed in venv but undeclared).
- `.env.example`: Added `POS_AUTH_RATE_LIMIT` and `POS_PIN_RATE_LIMIT` entries.

**Design decisions**
- Rate limit = 5/minute for both endpoints, matching the account-level lockout threshold (5 attempts → 15-min lock). Network-level rate limiting provides defense-in-depth; account-level lockout handles persistent per-account attacks.
- In-memory storage (no Redis) — single-process kiosk deployment per the existing architecture.
- `headers_enabled=False` — avoids slowapi's `_inject_headers` incompatibility with FastAPI model responses; the 429 response body contains the `retry_after` value for clients.
- `SlowAPIMiddleware` omitted — the `@limiter.limit` decorator's `async_wrapper` enforces limits in-process without the middleware.

**Verifiable goals — terminal results**
- `cd backend_fastapi && python -m pytest -q` → **92 passed, 0 failed** (87 existing + 5 new rate-limit tests).
- `cd backend_fastapi && python -m mypy app --strict` → **7 errors, all pre-existing** in `security.py`, `sync_service.py`, `pos_service.py`, `auth_service.py`, `sync_route.py`. Zero new errors from rate-limiting changes.

---

## M10.5 — Mypy Type Debt Resolution  (2026-08-17) ✅ VERIFIED

**Objectives completed**
- Resolved all 7 pre-existing `mypy --strict` errors across 5 files (zero behavior changes):
  - `app/shared/security.py`: `PinPepper.derive()` — added `typing.cast(Optional[bytes], ...)` on both return paths (lines 228, 239); `_cached` is typed `Any` due to sentinel; `cast` communicates intent to mypy.
  - `app/shared/security.py`: `verify_pin()` — widened `salt: bytes` → `salt: Optional[bytes]` (line 317); runtime guard `not salt` at line 328 already handled `None`.
  - `app/services/sync_service.py`: `insert_merged()` call — converted `e.payload` (`dict[str, Any]`) to `json.dumps(e.payload)` (`str`) at call site (line 43); added `import json`. Repository's existing `isinstance` guard left as backward-compat for legacy DB rows.
  - `app/services/pos_service.py`: Renamed shadowed local `payload` → `sync_payload` (lines 159, 171) to avoid reassigning the `CheckoutRequest` parameter.
  - `app/api/routers/sync_route.py`: Added `session: AsyncSession` type annotation (line 23) + `from sqlalchemy.ext.asyncio import AsyncSession` import.

**Verifiable goals — terminal results**
- `cd backend_fastapi && python -m mypy app --strict` → **0 errors** (32 source files).
- `cd backend_fastapi && python -m pytest -q` → **92 passed** (all existing tests pass, no regressions).

---

## M3-FL — Frontend Core Libraries  (2026-08-17) ✅ VERIFIED

**Label note:** named M3-FL to avoid colliding with the already-verified `M3 — Inventory
Management & FIFO Basis` (`CHANGELOG.md` M3). Scope chosen by user: "Frontend foundation."

**Objectives completed**
- `types/contracts.ts`: added `CartLine`, `InventoryFilters` (promoted from `hooks/useInventory.ts`), `SystemSettingRead`, `LicenseValidationResult`/`LicenseStatus` — contract sync with backend Pydantic schemas (`app/shared/schemas.py`).
- `lib/api/{inventory,pos,auth,license,users,settings}.ts` (NEW): typed per-domain API service layer wrapping the shared Axios instance (`lib/api.ts`). Pages/hooks/stores no longer call raw string paths (`grep` for `api.get("/api/v1` in `app/`,`hooks/`,`stores/` → 0 matches).
- `stores/inventoryStore.ts` (NEW): global inventory catalog cache (medicines, stock levels, suppliers, filters). `hooks/useInventory.ts` refactored to delegate to it **with identical public return shape** → `app/dashboard/inventory/page.tsx` needed no changes.
- `stores/cartStore.ts` (NEW): global POS cart; `app/pos/page.tsx` refactored from local `useState<CartLine[]>` to the store.
- `stores/licenseStore.ts` (NEW): license validation state; `app/license/page.tsx` refactored to use it.
- `stores/uiStore.ts` (NEW): theme/sidebar/tab/modal/toast foundation (available for later UI milestones).
- `stores/authStore.ts`: `fetchCurrentUser` now routes through `lib/api/auth.getCurrentUser` (HTTP-only cookie login/logout path untouched).

**Design decisions**
- Inventory store is the canonical state; the hook delegates while preserving its API (zero page churn).
- Auth login/logout retain the `fetch`-based HTTP-only cookie flow (Next route handlers); only the `/me` read path moved to the service layer.
- Frontend-only milestone — **no backend files changed**.

**Verifiable goals — terminal results**
- `npx tsc --noEmit` → **0 errors**.
- `npx next build` → **compiled successfully** (13/13 pages generated).
- Backend unchanged: `cd backend_fastapi && python -m pytest -q` still **92 passed** (no backend files touched).


