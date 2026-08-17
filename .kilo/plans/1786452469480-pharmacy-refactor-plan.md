# Pharmacy Suite Refactor — Implementation Plan (Reconciled to Reality)

**Date:** 2026-08-11
**Author:** Planning agent (Tech Lead review)
**Status:** Implementation-ready (Milestone 1 start). Builds on decisions confirmed with the user.

---

## 0. Critical Reality Check (READ FIRST)

The `MASTER_IMPLEMENTATION_PROMPT.md` describes a greenfield Vite+FastAPI system with
separate `inventory.db` (medicines/batches) and a Flask `license_gate.py`. The actual repo
**does not match** that description. Verified facts (introspected live):

| Spec assumption | Reality (verified) |
|---|---|
| `inventory.db` holds `medicines`/`batches`/`suppliers` | `inventory.db` is **0 bytes / empty**. Inventory lives in `pharmacy.db`: `products`, `inventory_extended`, `receiving_log`, `sold_items`, `suppliers`. |
| `license_gate.py` is a Flask microservice on :5000 | Root `license_gate.py` is a **customtkinter desktop GUI client** (offline cache). The real Flask license service is **`backend/app.py`** (Lemon Squeezy webhooks + `/api/validate` + `/api/admin/manage`) backed by **`backend/license_db.sqlite`** `licenses`. |
| Frontend = Vite + React 18 SPA | Repo frontend is **Next.js 16 / React 19** (`app/`, `components/PricingCard.tsx`, Paddle, `tsconfig.json` Next plugin). |
| Python `>=3.12,<3.13` | Installed toolchain is **Python 3.14.3**. `pyproject.toml` says `~=3.12.0`. |
| `pharmacy.db` has `licenses`, `settings` | `pharmacy.db` has **no `licenses`** (that's in `backend/license_db.sqlite`); settings are `system_settings(key,value)`. |

### Decisions locked with user
1. **Reconcile to reality** — model against the real `pharmacy.db`, reuse `backend/app.py` as the isolated Flask license service. Do NOT invent a new `inventory.db`.
2. **Keep Next.js** as the frontend foundation; adapt the spec's React patterns (stores, components, validation) to Next.js App Router.
3. **Inventory modeled in `pharmacy.db`** (`products` + `inventory_extended` + `receiving_log`).

### Additional resolved assumptions (flag if you disagree)
- **Python:** relax version pins to `>=3.12` (allow 3.14). All chosen libs support 3.14.
- **Password hashing:** use the `bcrypt` package directly (>=4.2). Avoid `passlib` (broken with bcrypt 4.x on 3.13+). Inspect existing `users.password_hash` BLOB format at implementation; verify legacy hashes via a compatibility path, hash new/updated via bcrypt cost 12.
- **Receipt number:** derive `RCP-{year}-{id:06d}` from `receipts.id` (no schema change). Do NOT add columns to legacy tables unless explicitly required; if a column truly cannot be avoided, perform it as a documented, reversible migration in `archive/migrate_data.py` style and record in CHANGELOG.
- **Desktop shell (Tauri/Electron):** DEFERRED. Primary deliverable is the FastAPI + Next.js web app. Barcode capture uses keyboard-wedge (focused input) in the browser; `react-hid`/native bridge only if/when a desktop wrapper is added later (Milestone 7 becomes optional).
- **Auth identity:** login by `username` (not email). Permissions derived from `roles`→`role_permissions`→`permissions.feature_key`.

---

## 0.5 Technical Critique — Reviewer Stance & Risk Register

> Source: technical critique of the refactor plan (four critical risks: Concurrency,
> Data Integrity, Hardware Integration, Authentication). Substance integrated below.

### Reviewer stance (summary)
The critique **endorses** the reconciled architecture but raises four must-fix risks the
original plan under-weighted:
- **Flask/FastAPI separation:** Valid and must be preserved (keeps the legacy license
  boundary intact, avoids import coupling). The critique's concern is *operational*: two
  processes require a launch/health-check/orchestration contract, and the FastAPI→Flask proxy
  must degrade gracefully (already covered by `502 license_unreachable`).
- **ORM mirroring:** Correct for preservation, BUT the legacy `products` ↔ `inventory_extended`
  relationship has **no foreign key** (joined by `drug_name`/`ndc_code` text). Mirroring alone
  perpetuates a fragile "soft link"; an explicit, validated mapping + one-time normalization
  is required before inventory logic is trusted.
- **Milestone gating:** Gates are too coarse. High-write, integrity-critical paths (FIFO
  deduction, stock joins, auth hashing) must be *proven in isolation* **before** M4 checkout
  kickoff. Risk-proofing tasks must be inserted into M2/M3 (see §6 amendments).

### R1 — Concurrency (SQLite / aiosqlite for high-write POS)
- **Implication:** Every checkout writes `receipts`, `receipt_items`, `sold_items`, and
  decrements `inventory_extended.on_hand` (possibly several lot rows). SQLite is a
  single-writer engine; under concurrent registers/cashiers writes serialize and contended
  transactions raise `database is locked`. `aiosqlite` is async but still bound to one write
  lock per DB file.
- **Mitigation (WAL + busy_timeout + writer discipline):**
  - Enable `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` on **every** connection
    (SQLAlchemy `connect` event / `aiosqlite` init hook in `core/database.py`).
  - Run checkout mutations inside **one serializable transaction**; keep the write window
    tiny (FIFO loop + inserts only — no external/HTTP calls inside the txn).
  - Serialize cross-register stock writes with an `asyncio.Lock` keyed per drug so concurrent
    checkouts for the same medicine cannot produce lost updates on `on_hand`.
  - Add a concurrency integration test: N concurrent checkouts for one drug assert
    Σ deducted == Σ requested and no negative `on_hand`.

### R2 — Data Integrity (soft-link inventory joins)
- **Implication:** `products.name` vs `inventory_extended.drug_name`/`ndc_code` are free text
  with no FK. Typos/case/whitespace make lots invisible to a product (stock shows 0, FIFO
  skips rows) or split into duplicates — silently corrupting low-stock/expiry alerts and FIFO
  correctness.
- **Mitigation (normalization + enforced mapping):**
  - One-time, **dry-run-first** normalization script (`scripts/normalize_inventory.py`,
    read-only safe) that canonicalizes `drug_name`→`ndc_code`, trims/cases, and reports
    unmatched rows. Never mutates without explicit `--apply`.
  - Enforce a deterministic join key: require a valid `ndc_code` on every received lot
    (no legacy alter). As a follow-up migration, add nullable `product_id INTEGER
    REFERENCES products(id)` to `inventory_extended` for a hard FK.
  - `BatchRepository.receive()` must resolve a product (by `ndc_code`, else exact name) or
    return `validation_error` — no orphan lots.

### R3 — Hardware Integration (keyboard-wedge vs global listener)
- **Implication:** The plan's "focused input" barcode capture only works when an input is
  focused; a naive global `keydown` listener captures scans anywhere but risks reading normal
  typing and double-firing with the focused input.
- **Mitigation (hybrid, scan-prefix discriminated):**
  - Use a **global `keydown` listener** that buffers chars; a scan is detected by fast
    inter-key interval (<50 ms) and terminated by scanner suffix (Enter). Route the payload to
    the active scan handler and suppress those buffered chars from text inputs.
  - Provide a visible **"scan mode" toggle** so ordinary typing is never misread as a barcode.
  - Manual search input remains the primary fallback when no scanner is present.
  - Native HID/printer bridge stays deferred to the (optional) desktop wrapper.

### R4 — Authentication (Legacy Hash Lockout)
- **Implication:** `users.password_hash` is a BLOB of unknown legacy format. Switching login
  to bcrypt-only would **lock out every existing user** until re-hashed — a production outage.
- **Mitigation (lazy upgrade):**
  - At M2, **inspect** the BLOB (length/prefix). If not bcrypt (`$2b$`/`$2a$`), implement
    `verify_legacy()` (sha256/sha512+salt or the monolith scheme in `archive/auth_crypto.py`)
    alongside bcrypt.
  - On successful legacy login, **re-hash with bcrypt cost 12** and store — transparent
    upgrade, no mass migration, no lockout. New/reset passwords are bcrypt-only.
  - Preserve `failed_attempts` / `locked_until` throttling from the schema.
  - Test: seed one legacy-format user + one bcrypt user; both log in; legacy user's hash
    becomes bcrypt after first login.

---

## 1. Target Architecture (Reconciled)

```
Next.js 16 (React 19, TS, Tailwind, Zustand, Axios, Zod)
   │  HTTP/REST (typed JSON, uniform error contract)
   ▼
FastAPI (stateless) :8000
   ├─ Routers (/api/v1/auth, pos, inventory, users, reports, settings, license)
   ├─ Services (auth, pos, inventory, users, reports)
   ├─ Repositories (async SQLAlchemy 2.0)
   └─ Async engine → pharmacy.db  (aiosqlite)
           
Flask license microservice :5000  (backend/app.py)  ← separate process, NEVER imported
   └─ backend/license_db.sqlite  (licenses)
```

CORS allows `FRONTEND_URL` (default `http://localhost:3000`). License routes proxy to
`LICENSE_GATE_URL` (default `http://localhost:5000`) via `httpx.AsyncClient`. Killing the
Flask process → FastAPI returns `502` `{error:{code:"license_unreachable",...}}`.

---

## 2. Authoritative Data Model → Domain Mapping

All ORM models are **read-only mirrors** of these legacy columns (SQLAlchemy 2.0 `Mapped[]`,
`async` sessions). No column renames.

| Domain (spec) | Real table(s) | Key columns |
|---|---|---|
| Medicine / Product | `products` | id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name, dea_schedule, wholesale_price, reorder_threshold |
| Batch / Lot | `inventory_extended` | id, ndc_code, drug_name, strength, dosage_form, ndc_formatted, awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata |
| Supplier | `suppliers` | id, name, contact_*, address, tax_id, preferred, sku, min_stock_level, lead_time_days, edi_* |
| Receiving event | `receiving_log` | id, vendor_name, product_name, date_received, quantity, total_cost, barcode |
| Purchase order | `purchase_orders` + `po_items` | po_number, vendor_*, status, totals, line items |
| User | `users` | id, username, display_name, password_hash(BLOB), pin_hash(BLOB), role_id, is_active, failed_attempts, locked_until, created_at |
| Role / Perm | `roles`, `permissions`, `role_permissions` | roles(id,name,description,is_system); permissions(id,feature_key,description); role_permissions(role_id,permission_id,granted) |
| Receipt | `receipts` | id, timestamp, total_amount, payment_method, patient_id |
| Receipt line | `receipt_items` | id, receipt_id, product_name, quantity, price_at_time, internal_barcode, vendor, expiry_date |
| Sale record | `sold_items` | id, item_name, price, manufacturer_barcode, internal_barcode, timestamp_of_sale, vendor_name |
| Audit | `audit_logs` | id, timestamp, action, user_pin, details, region, category, subject_type, subject_id, rx_id, old_value, new_value, role, gdpr_deleted |
| Settings | `system_settings` | key(TEXT), value(BLOB) |
| License | `backend/license_db.sqlite`.`licenses` | license_key(PK), customer_email, order_id, status, hardware_id, created_at |

**FIFO deduction:** for a product, select `inventory_extended` rows for that drug (match by
`drug_name`/`ndc_code`), order by `expiration_date` ASC, deduct `on_hand` oldest-first until
the requested quantity is satisfied. Record which lots were consumed (for receipt line + audit).

---

## 3. Tech Stack (versions reconciled to installed toolchain)

**Backend (Python 3.12–3.14):**
fastapi>=0.115,<1.0 · uvicorn>=0.30 · sqlalchemy>=2.0,<3.0 · aiosqlite>=0.20 ·
pydantic>=2.9 · pydantic-settings>=2.5 · bcrypt>=4.2 · PyJWT>=2.9 · python-dotenv>=1.0 ·
structlog>=24 · pytest>=8.3 · httpx>=0.27 · pytest-asyncio>=0.24 · mypy>=1.10 (strict).

**Frontend (Node 22, Next.js 16 / React 19):**
next (existing) · react/react-dom (existing 19) · typescript 5.8 · tailwindcss>=3.4 ·
zustand>=4.5 · axios>=1.7 · zod>=3.23 · react-hook-form>=7.52 · @hookform/resolvers ·
date-fns>=3.10 · jspdf>=2.5 · eslint>=9 · prettier>=3.3 · jest>=29 + @testing-library/react.
(Remove the explicit React-18/Vite constraint from the spec; keep React 19.)

---

## 4. API Surface (reconciled routes)

Same paths/permissions/status codes as spec §5, with domain mapping:

- `/api/v1/auth/login` (username+password → JWT pair + user w/ permissions), `/refresh`, `/logout`, `/register` (admin).
- `/api/v1/pos/medicines/search?q=` → search `products`. `/checkout` (atomic FIFO), `/receipts/{id}`, `/receipts/{id}/print`.
- `/api/v1/inventory/medicines` (← `products` CRUD), `/batches` (← `inventory_extended` list+filtbter), `/batches/receive` (insert `inventory_extended` + `receiving_log`), `/alerts/low-stock`, `/alerts/expiring-soon`, `/suppliers` CRUD.
- `/api/v1/users` CRUD + `/me` (admin-gated; soft-deactivate via `is_active=0`).
- `/api/v1/reports/sales-summary`, `/inventory-value`, `/expiry-forecast`, `/audit-log`.
- `/api/v1/settings` get/set `system_settings`.
- `/api/v1/license/validate` → proxy `POST {LICENSE_GATE_URL}/api/validate`; `/activate` → proxy same endpoint (first-use bind); `/status` → admin manage list/lookup. On upstream failure → `502 license_unreachable`.

**Uniform error contract (mandatory):** `{"error":{"code":str,"message":str,"details":{}}}`.
Global `AppException` handler in FastAPI; Axios interceptor on frontend.

---

## 5. Project Layout (new, non-destructive)

```
backend_fastapi/            # new FastAPI service (do NOT touch backend/app.py Flask)
  app/
    main.py                # create FastAPI, CORS, routers, exception handlers, startup
    core/ database.py models.py repositories.py
    api/routers/ auth_route.py pos_route.py inventory_route.py users_route.py reports_route.py settings_route.py license_route.py
    services/ auth_service.py pos_service.py inventory_service.py users_service.py reports_service.py license_gateway.py
    shared/ config.py auth.py exceptions.py schemas.py logging_config.py
  tests/ conftest.py (aiosqlite :memory:), test_*.py
  pyproject.toml  .env.example
frontend/  (extend existing Next.js at repo root instead — see M1)
  -> we build into existing app/ + components/ + lib/ + new src/stores, src/types, src/validation
CHANGELOG.md  (new, updated per milestone)
docs/  (ARCHITECTURE.md, COMPONENT_MAP.md, api.md, DEPLOYMENT.md) — M7
```

> **Asset-preservation rule:** never delete/rename/overwrite `pharmacy.db`, `inventory.db`,
> `backend/license_db.sqlite`, `backend/app.py`, `license_gate.py`, or any image/config.
> Read before any touch. The Flask `backend/app.py` is launched as a **separate process** only.

---

## 6. Milestones (verifiable goals + terminal checks)

### M1 — Scaffold & Core Infra
- Read `PROJECT_MAP.md`, `FLOW_LOGIC.md`, `VERIFICATION_CHECKLIST.md` (AGENTS.md pre-flight).
- Create `backend_fastapi/` FastAPI layered app; `pyproject.toml` (versions §3); `.env.example`
  (PHARMACY_DB_URL, SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, LICENSE_GATE_URL, FASTAPI_*,
  FRONTEND_URL, CORS). Add `.gitignore` entries.
- Async SQLAlchemy models mirroring §2 tables (products, inventory_extended, suppliers,
  receiving_log, users, roles, permissions, role_permissions, receipts, receipt_items,
  sold_items, audit_logs, system_settings) + Pydantic v2 schemas in `shared/schemas.py`.
- Confirm `python backend/app.py` still starts Flask on :5000 independently.
- `conftest.py` with in-memory aiosqlite; skeleton routers returning 200 health.
- Decisions doc: Tauri/Electron deferred; Next.js kept.
- **Verify:** `cd backend_fastapi && python -m pytest -q` (0 errors) · `python -m mypy app --strict` (0) · `cd . && npx tsc --noEmit` (0) · `npx prettier --check "app/**/*.{ts,tsx}"` · `python backend/app.py &` listens on 5000.

### M2 — Auth & RBAC  *(addresses R4)*
- `users`/`roles`/`permissions` repositories; `auth_service` (bcrypt hash/verify, JWT create/decode HS256, permission resolution).
- **R4 — inspect `users.password_hash` BLOB format**; implement `verify_legacy()` if not bcrypt; **lazy upgrade** (re-hash with bcrypt on first successful legacy login). Preserve `failed_attempts`/`locked_until` throttling.
- Routers login/refresh/register/logout; `require_permission` dependency.
- Next.js: `src/stores/authStore.ts`, `lib/api.ts` (Axios + interceptors), `app/login/page.tsx`.
- **Verify:** register→201 (bcrypt hash stored); **legacy-format user logs in AND hash becomes bcrypt after login**; bcrypt user logs in; wrong→401 uniform JSON; no token→401; wrong role→403; refresh→200. `pytest -q` + `tsc --noEmit` clean.

### M3 — Inventory Management  *(addresses R2)*
- `MedicineRepository`(products), `BatchRepository`(inventory_extended), `SupplierRepository`; `InventoryService` with FIFO helper + low-stock (`reorder_threshold`) + expiring-soon.
- **R2 — one-time `scripts/normalize_inventory.py` (dry-run first)** canonicalizing `drug_name`→`ndc_code`; enforce `ndc_code` as the receive-time join key; `BatchRepository.receive()` rejects orphan lots (no resolvable product).
- CRUD routers `/inventory/*`; `src/types/contracts.ts` interfaces; inventory pages + forms in Next.js.
- **Verify:** create product stored; receive batch → `inventory_extended.on_hand>0` linked by `ndc_code`; **orphan lot (no valid ndc_code) rejected with `validation_error`**; FIFO oldest-first; alerts fire; search/pagination. `pytest -q` + `tsc --noEmit` clean.

### M4 — POS Checkout  *(addresses R1, R3)*
- `Receipt`/`ReceiptItem` models; `pos_service.process_checkout()` atomic FIFO deduction + receipt + `sold_items` + `audit_logs`, rollback on shortfall.
- **R1 — WAL + `busy_timeout` enabled in `core/database.py`; single serializable txn; per-drug `asyncio.Lock` for stock writes; no external calls inside the txn.**
- **R3 — global `keydown` scan listener (inter-key <50ms + Enter suffix) with "scan mode" toggle; manual search fallback.**
- **Scope:** v1 = atomic checkout + rollback only. **Returns/voids deferred to M4.1 (fast-follow).** Tax from `system_settings` (14% VAT baseline), item-level rounding before sum.
- POS routers + Next.js `PosPage`, cart, search, barcode input, receipt preview (jsPDF).
- **Verify:** valid cart → correct FIFO deduction; receipt number `RCP-{year}-{id:06d}`; insufficient stock → rollback + 400 w/ batch details; print format OK; scan→search. **Concurrency test: 20 parallel checkouts for one drug → Σ deducted == Σ requested, no negative `on_hand`, no `database is locked`.** `pytest -q` + `tsc --noEmit` clean.

### M5 — Users, Reports, Settings
- User admin routes (CRUD, soft-deactivate, `/me`); reports aggregation (sales-summary, inventory-value, expiry-forecast, audit-log search); settings get/set.
- Next.js UsersPage, ReportsPage, SettingsPage.
- **Verify:** admin CRUD; sales summary correct; inventory value sums; expiry forecast windows; audit log searchable; settings update live. `pytest -q` + `tsc --noEmit` clean.

### M6 — License Proxy & Isolation
- `license_gateway.py` httpx client; proxy routes → `backend/app.py`. `LicenseGatewayError`→502.
- **Isolation (per decision):** keep `backend/app.py` **fully isolated as a separate process** so it can securely process payment-platform webhooks (Lemon Squeezy, Creem) **without entangling core POS checkout logic**. FastAPI never imports it.
- Grace-period/offline cache logic lives in Next.js client (mirror root `license_gate.py` cache rules). `LicensePage` + `licenseStore`.
- **Verify:** validate/activate via proxy returns Flask response; kill Flask → FastAPI 502 `license_unreachable` (no crash); offline grace honored client-side. `pytest -q` + `tsc --noEmit` clean.

### M7 — Docs & Final Verification (desktop deferred)
- `docs/` (ARCHITECTURE, COMPONENT_MAP, api.md, DEPLOYMENT), README updates, launch script
  (start Flask :5000 + FastAPI :8000 + `next dev` :3000).
- **Verify:** `cd backend_fastapi && pytest --cov` ≥90%; `npx tsc --noEmit` clean; `next build` succeeds; `grep -rE "TODO|\.\.\." backend_fastapi app components lib` returns nothing. Playwright E2E optional (note as nice-to-have, not blocking, since desktop deferred).

---

## 7. Cross-Cutting Requirements (from spec, still enforced)
- 100% type coverage: Pydantic v2 backend ↔ TS interfaces `src/types/contracts.ts` ↔ Zod schemas `src/validation/`. No `any` without justification comment.
- No placeholders/TODO/`...`/stub anywhere.
- Secrets from env only; bcrypt cost 12; JWT HS256, 8h/30d; secure headers (nosniff, DENY, HSTS prod, CSP).
- Audit every significant action to `audit_logs`.
- No raw SQL — SQLAlchemy parameterized async only.
- Per milestone: run the verify commands, then update `CHANGELOG.md`.

---

## 7.5 Pharmacy-Domain Gap Analysis (overlooked by the critique)
The critique covers engineering risks but omits domain-specific ones a Pharmacy POS cannot ship
without. These must be scoped (at minimum as M4/M5 follow-ups or explicit out-of-scope calls):

1. **Audit-trail immutability / compliance.** `audit_logs` has a `gdpr_deleted` column, implying
   records can be *removed*. For controlled-substance dispensing (note `products.dea_schedule`
   and the `prescriptions`/`rx_table` tables) many jurisdictions require tamper-evident,
   append-only logs (21 CFR Part 11-style). **Decision needed:** make `audit_logs` append-only
   (no UPDATE/DELETE in app code), drop or ignore `gdpr_deleted` for audit rows, and consider a
   hash-chain/`created_at`+signature for non-repudiation.
2. **Controlled-substance & clinical workflow.** `dea_schedule`, `prescriptions`, `rx_table`,
   `prescriber_table` indicate Rx/controlled dispensing not covered by the 5 user journeys.
   FIFO + audit must extend to dispensing limits, DEA verification, and signature capture.
   Flag as **out of scope for M1–M7** unless explicitly added.
3. **Offline / network-resilience.** Critique's "offline" only covers license grace. A pharmacy
   must sell during LAN/ISP outages. FastAPI+SQLite on the same machine *is* offline-capable,
   but the Next.js frontend needs the server reachable (LAN). Multi-device offline sync and
   conflict resolution are **not addressed** — decide: single-machine/local-server deployment
   (acceptable) vs. multi-site sync (needs design).
4. **Returns / voids / refunds.** No return or void flow exists in the journeys. Reversing FIFO
   and writing correcting audit entries is mandatory for real POS. Add to M4 as a sub-flow.
5. **Tax, rounding & shift/EOD reconciliation.** `tax_rate` appears in the cart UI but there is
   no tax config (store in `system_settings`); `total_amount` must be exact-decimal. Archive has
   EOD reports — add cash-drawer/shift reconciliation to M5.
6. **PHI/PII handling.** `patients`, `prescriptions`, `insurance_table` contain PHI. Need
   encryption-at-rest posture, access scoping, and retention policy (link to `gdpr_deleted`
   semantics). At minimum document the stance.
7. **Backup/restore & time integrity.** `pharmacy.db` is the sole source — document a backup
   procedure (repo already has `archive/backups/`). All timestamps are TEXT; enforce UTC and
   monotonicity across registers to keep audits coherent.

**Status:** Decisions for items **#1 (audit append-only)**, **#3 (offline = local-server)**,
**#4 (returns deferred to M4.1)**, and **#5-adjacent tax (14% VAT, item-level rounding)** are
recorded as resolved in §8. Items **#2 (clinical/controlled-substance workflow)** and **#6 (PHI
posture)** remain OPEN; **#7 (backup/UTC)** is accepted as documentation work in M7.

## 8. Open Questions / Risks
Risk-register items **R1–R4 are now owned by M2/M3/M4** (see §6 amendments) — not open, but tracked.

1. **Audit immutability (gap #1) — RESOLVED:** `audit_logs` is **append-only at the application
   layer** (no UPDATE/DELETE in app code). `gdpr_deleted` is **ignored for rows tied to
   prescriptions or controlled substances** (medical compliance mandates tamper-evident
   retention over right-to-be-forgotten). Enforced before M4 writes audit entries.
2. **Offline scope (gap #3) — RESOLVED:** **Single-machine / local-server deployment** is the
   baseline (FastAPI+SQLite on-box = offline-capable). Multi-site sync is **deferred to a later
   version** (distributed-transaction complexity out of scope for v1).
3. **Returns/voids (gap #4) — RESOLVED (deferred):** Full returns deferred to **M4.1 fast-follow**.
   v1 checkout focuses solely on **atomic rollback if stock falls short mid-transaction**.
4. **Tax config (gap #5) — RESOLVED:** Baseline tax rate (e.g., **14% VAT**) stored dynamically in
   `system_settings`. **Round at item level before summing** the cart to avoid decimal drift.
5. **PHI posture (gap #6) — OPEN:** document encryption-at-rest / access-scoping stance for
   `patients`/`prescriptions`/`insurance_table`. (Recommended: encryption-at-rest + role-scoped
   access; no PHI in logs.)
6. **Desktop shell** — deferred per decision; if required later, choose Tauri (static-export
   Next.js) and add `react-hid`/printer bridge in M7.
7. **Receipt number without schema change** — derived `RCP-{year}-{id:06d}`. If business
   requires gap-free sequential numbers, revisit (migration).
8. **`regional_metadata`** — carry through as opaque JSON/text; do not drop.

## 9. Validation Plan
Each milestone gate = the listed terminal commands returning 0/clean, plus `CHANGELOG.md` entry.
Final gate (M7) = coverage ≥90%, type-check clean, build succeeds, no TODO/`...` in new code.
Follow AGENTS.md protocol: read PROJECT_MAP/FLOW_LOGIC/CHECKLIST before editing; update them as the architecture stabilizes.
