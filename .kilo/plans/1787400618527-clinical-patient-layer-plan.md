# Plan: Clinical / Patient Management Layer (extend existing FastAPI + Next.js stack)

**Status:** Implementation-ready (planning complete)
**Date:** 2026-08-22
**Decision (resolved):** Extend the EXISTING verified backend (`backend_fastapi/`, 11 routers, 237 tests, 90.73% cov, `mypy --strict` clean) and frontend (Next.js 16/React 19, typed API layer) with the missing clinical layer. Do NOT rebuild inventory/POS/auth/sync/license — they already exist and are green.

---

## 1. Context (reconciled reality)

**Already built & verified** (per `PROJECT_MAP.md` M94, `FLOW_LOGIC.md` §16, `VERIFICATION_CHECKLIST.md`):
- `backend_fastapi/`: routers `auth, audit, health, inventory, license, license_file, pos, settings, sync, users, webhook`; async SQLAlchemy 2.0 + aiosqlite on `pharmacy.db` (WAL + `busy_timeout=30000`); RBAC via `require_permission`; hash-chained `audit_logs`; `Base.metadata.create_all` + `migrate_schema` (PRAGMA `user_version`, currently v6).
- Tables exist: `products`, `inventory_extended` (the batches/lots table), `suppliers`, `receiving_log`, `users/roles/permissions/role_permissions`, `receipts` (has `patient_id` FK), `receipt_items`, `sold_items`, `audit_logs`, `sync_*`, `shifts`, `drawer_movements`, `refunds`, `licenses`.
- Frontend: `app/{login,license,portal,dashboard,dashboard/inventory,pos}`, `stores/{auth,inventory,pos,license,ui}`, `lib/api/*`, `types/contracts.ts`, hooks `useBarcodeScanner`/`useLicenseGate`/`useInventory`/`useHydration`. `useCan(perm)` + `useAuthStore` exist.
- Phase 4 partial: `src-tauri/` Tauri bundling + `Caddyfile` + `install.ps1` + `scripts/` exist; periodic `VACUUM INTO` snapshot already runs in `main.py` lifespan (`vacuum_snapshot`).

**Gap vs. your Phase 1–4 spec (the work this plan adds):** `patients`, `insurance_plans`, `members_groups`, `sig_codes`, `price_codes`, dispensing workflow + label hooks, NDC dictionary lookup, dedicated `backup.py` + `audit_log.py` modules, and the NSSM/Caddy thin-client deploy script.

**Spec reconciliation:** your two pasted versions differ only in detail (v1: `/api/v1/dispense`; v2: adds `members_groups` + Billing Info tab). Both are satisfied by the task list below. "inventory"/"inventory_batches" = existing `products`/`inventory_extended` — reused, not recreated. "NDC dictionary" = new lookup over `inventory_extended.ndc_code/ndc_formatted` (the legacy `ndc_dictionary.py` lives only in the Tkinter app and is NOT used here).

---

## 2. Scope decisions (locked)

1. **DB:** new tables land in the same `pharmacy.db` (no new database). New ORM models appended to `models.py`; schema bumped v6→v7 via `migrate_schema` (PRAGMA `user_version`, idempotent `CREATE TABLE IF NOT EXISTS`). Enable `PRAGMA foreign_keys=ON` in `_configure_pragmas` so patient→insurance FKs are enforced.
2. **Layered pattern (unchanged):** API router → service → repository → ORM. Follow `inventory_route.py`/`inventory_service.py`/`repositories.py` exactly.
3. **Audit:** reuse the EXISTING audit write path (so the `prev_hash`/`entry_hash` chain stays intact). If `AuditRepository` exists, call it; else add `app/core/audit_log.py` exposing `async write_audit(session, action, subject_type, subject_id, details)` that wraps the existing hash-chain writer. Do NOT write raw audit rows.
4. **`receipt_engine.py`:** create `app/services/receipt_engine.py` (pure formatting, no I/O) for thermal-label text + fill-date/price-check helpers, consumed by the dispense route. Does not duplicate `pos_service.py` (checkout stays owned by `PosService`).
5. **`backup.py`:** create `app/core/backup.py` with `async vacuum_backup(dest_dir, *, compress=True)` (VACUUM INTO + optional gzip for "compressed local backups") + retention helper; exposed via admin-only `POST /api/v1/admin/backup`. Keeps the existing `vacuum_snapshot` loop intact.
6. **RBAC keys to add:** `patients.read/write/delete`, `insurance.read/write`, `members.read/write`, `dictionaries.read/write`, `dispense.create`, `backup.create`. Add rows to `permissions` + grant admin in `seed_service` (idempotent).
7. **Money:** `Decimal` → Pydantic `Decimal` → JSON string, mirror `Medicine`/`Money` contract; never float.

**Out of scope (explicit):** full Rx/prescription clinical workflow (`prescriptions`/`rx_table` exist only in the Tkinter desktop app, not FastAPI). Patient tab "Rx/Refill" lists dispenses + a free-text Rx number field; integrating a prescriptions table is a separate milestone. Returns/voids reuse existing `pos.refund`.

---

## 3. Data model (new tables, v7)

```sql
-- patients (mirrors Tkinter patients columns + FK)
patients(id PK, name, dob, address, driver_license, sex, employer_id,
         contact_phone, email, insurance_provider, policy_number, group_number,
         insurance_plan_id INTEGER REFERENCES insurance_plans(id),
         patient_allergies TEXT DEFAULT '',   -- B: free-text/tag array, enables later allergy alerts without a 2nd migration
         comments TEXT DEFAULT '',            -- §2 decision: store comments as column (not separate table)
         created_at TEXT, is_deleted INTEGER DEFAULT 0)

insurance_plans(id PK, plan_name, carrier_id, bin, pcn, group_number,
                copay_tier TEXT, copay_amount NUMERIC(10,2), active INTEGER DEFAULT 1,
                created_at TEXT)

members_groups(id PK, patient_id INTEGER REFERENCES patients(id),
               member_name, relationship, dob, created_at TEXT)

sig_codes(id PK, code UNIQUE, full_text)          -- BID -> "Take ... twice daily"
price_codes(id PK, code UNIQUE, description, price NUMERIC(10,2))

dispenses(id PK, patient_id INTEGER REFERENCES patients(id),
          receipt_id INTEGER, product_name, ndc_code, sig_code,
          quantity INTEGER, fill_date TEXT, price_at_time NUMERIC(10,2),
          insurance_copay NUMERIC(10,2), insurance_amount NUMERIC(10,2),
          internal_barcode TEXT, cashier TEXT, server_created_at TEXT)
```
`Base.metadata.create_all` creates these on fresh DBs; `migrate_schema` v7 `CREATE TABLE IF NOT EXISTS` covers existing DBs. Seed a few default `sig_codes` (BID/TID/QID/PRN/PO) + `price_codes` in `seed_service` (idempotent).

---

## 4. Backend tasks (ordered)

**T1 — Models & migration**
- `app/core/models.py`: add `Patient`, `InsurancePlan`, `MembersGroup`, `SigCode`, `PriceCode`, `Dispense` (Mapped, `Base`). `Patient` includes `patient_allergies` (B) and `comments` (§2) TEXT columns. Do NOT edit existing models.
- `app/core/database.py`: bump `SCHEMA_VERSION=7`; add v7 block in `migrate_schema` (`CREATE TABLE IF NOT EXISTS` for the 6 tables, incl. `patient_allergies`/`comments` on `patients`). **#10 (FK siloing):** ensure `PRAGMA foreign_keys=ON` is executed **inside the per-connection `_configure_pragmas` listener** (already attached via `event.listen(engine.sync_engine, "connect", ...)`), NOT only inside `migrate_schema` — SQLite resets FK off on every pooled connection, so running it once at startup leaves later pool connections silently ignoring FK constraints (orphan `patient_id`/`insurance_plan_id`). The listener already runs per connect; just add the pragma there.

**T1.5 — BEGIN IMMEDIATE write path (multi-terminal deadlock fix, #1; corrected per review).** Standard `session.begin()` issues a deferred `BEGIN`; two terminals that each read then upgrade to a write lock deadlock → `SQLITE_BUSY` even with `busy_timeout`. **Do NOT** call `await session.execute(text("BEGIN IMMEDIATE"))` inline — SQLAlchemy 2.0 `AsyncSession` has already opened an implicit transaction, so raw `BEGIN` raises `sqlite3.OperationalError: cannot start a transaction within a transaction`. Correct fix: set **`isolation_level="IMMEDIATE"` on the write engine only** in `build_engine()` (for `sqlite+aiosqlite` write URLs; leave the read/`mode=ro` engine at default so reads stay non-blocking under WAL). SQLAlchemy then issues `BEGIN IMMEDIATE` for every `session.begin()` on a write session, reserving the write lock up front and letting the second terminal queue via `busy_timeout`. **No code change** in `DispenseService.process_dispense` / `PosService.process_checkout` / `InventoryService.receive_batch` — they keep `async with session.begin():`. (If engine-level is undesirable, the only safe in-session alternative is `conn = await session.connection(); await conn.exec_driver_sql("BEGIN IMMEDIATE")` captured *before any query* — but engine isolation level is preferred.)

**T2 — Schemas** (`app/shared/schemas.py`): `PatientCreate/Read/Update`, `InsurancePlanCreate/Read`, `MembersGroupCreate/Read`, `SigCodeCreate/Read`, `PriceCodeCreate/Read`, `DispenseCreate/Read`, plus `SigCodeParseResult` and `InsuranceValidationResult` (active coverage + copay tier). **#5/#6 (date precision & integrity):** enforce **two distinct ISO formats** via Pydantic validators — (a) **date-only** fields `dob`, `fill_date` → strict `YYYY-MM-DD`; (b) **event timestamps** `created_at`, `server_created_at` → strict UTC `YYYY-MM-DDTHH:MM:SSZ`. Reject localized formats (e.g. `DD/MM/YYYY`) and reject a full timestamp where a date-only is expected (so `WHERE fill_date = '2026-08-22'` and range queries match). `server_created_at` is server-generated via `datetime.now(timezone.utc).isoformat()` (already correct in `pos_service`). **#6 (money float pollution):** all currency fields use `Decimal` with an **explicit Pydantic serializer to a 2-decimal string** (e.g. `Field(..., json_schema_extra=...)` + `field_serializer` returning `f"{v:.2f}"`); never serialize money as a JSON number (avoids JS IEEE-754 `19.899999999999998`). **#2 (LAN idempotency):** add `client_tx_id: str` (UUID) to `DispenseCreate` **and** `CheckoutRequest` (extends the existing `CheckoutRequest`); persisted on `dispenses`/`receipts`.

**T3 — Repositories** (`app/core/repositories.py`): `PatientRepository` (CRUD + `search` + soft-delete + `active_count` filtered by `is_deleted=0`), `InsuranceRepository` (CRUD + `validate(plan_id)`), `MembersGroupRepository`, `SigCodeRepository` (CRUD + `parse(code)`), `PriceCodeRepository`, `DispenseRepository`. Follow existing repo signatures (async, `model_validate`). **#4 (soft-delete referential integrity):** any `DispenseRepository` history/aggregation query and `MembersGroupRepository` listing **must JOIN `patients` and filter `patients.is_deleted = 0`** — never count a soft-deleted patient's dispenses into daily revenue / active-patient totals. `PatientRepository.active_count` already excludes `is_deleted=1`.

**T4 — Audit helper** (`app/core/audit_log.py`): `async write_audit(session, action, subject_type, subject_id, details)` reusing the existing hash-chain writer.

**T5 — Services**
- `app/services/patient_service.py`: profile CRUD + insurance binding + members-group aggregation.
- `app/services/insurance_service.py`: `validate_coverage(plan_id)` → active + copay tier (reuse region strategy already in `rx_strategies` if present, else flat copay).
- `app/services/dictionary_service.py`: sig-code parse (BID→full text), price-code lookup.
- `app/services/receipt_engine.py`: pure functions returning **raw printer byte strings** — `format_thermal_label(dispense)` → ESC/POS (or TSPL/ZPL where the device is a label printer), `format_receipt(...)` → ESC/POS, `fill_date_default()` + `compute_price_check(line_items)`. **#3 (thermal printing):** output raw control-byte payloads (sharp vector barcodes), NOT HTML/webview markup. The print path **bypasses `window.print()`** — bytes are sent straight to the thermal printer (Tauri sidecar → raw USB/Serial via `win32print` or raw socket). `dispense_route.GET /{id}/label` returns `application/octet-stream` raw bytes (or a print-now endpoint that forwards to the sidecar). **#11 (raw handle collision):** the sidecar / print service must serialize all raw writes behind a single process-level `asyncio.Lock` (`printer_lock`) with a **100 ms inter-job delay**, so a simultaneous receipt + drug-label job never throws `WinError 5` / Resource Busy on the shared COM/USB handle.
- `app/services/dispense_service.py`: `process_dispense(payload, user)` — **#2 (LAN idempotency):** before executing, check `dispenses.client_tx_id` (and `receipts.client_tx_id`); if a matching id was committed within the last 5 minutes, return the cached successful `DispenseRead`/`CheckoutResult` immediately without re-running FIFO deduction. Otherwise atomic txn: store `client_tx_id`, validate patient + insurance, FIFO-deduct `inventory_extended.on_hand` (reuse `InventoryService`/repo FIFO helper), insert `dispenses` (+ `client_tx_id`), create `receipts`/`receipt_items` (+ `client_tx_id`), write audit; rollback on shortfall (400 + batch detail). Decimal/integer-cents, money as **string** (not float).

**T6 — Routers** (`app/api/routers/`)
- `patients_route.py` prefix `/api/v1/patients`: `GET /` (paginated+search), `GET /{id}`, `POST /`, `PUT /{id}`, `DELETE /{id}`, `GET /{id}/members`, `POST /{id}/members`, `GET /{id}/dispenses`, `GET /{id}/history` (receipts+dispenses joined by patient_id).
- `insurance_route.py` `/api/v1/insurance`: plans CRUD + `POST /plans/validate`.
- `members_route.py` `/api/v1/members-groups`: CRUD.
- `dictionaries_route.py` `/api/v1/dictionaries`: `sig-codes` CRUD + `GET /sig-codes/parse?code=`, `price-codes` CRUD, `GET /ndc/lookup?q=` (over `inventory_extended.ndc_code/ndc_formatted`). **A (NDC fallback):** when no local match, return `200 {found:false, q}` (NOT a bare 404) so the UI can offer "NDC not found in stock — Add to Inventory?" instead of silently blocking the pharmacist (see F5).
- `dispense_route.py` `/api/v1/dispense`: `POST /` (→ `DispenseService.process_dispense`), `GET /{id}`, `GET /{id}/label` (→ `receipt_engine.format_thermal_label`).
- `admin_route.py` (or extend `settings_route.py`): `POST /api/v1/admin/backup` → `app/core/backup.py` (admin-gated).
- Register all in `app/main.py`.

**T7 — Backup module** (`app/core/backup.py`): `vacuum_backup(dest_dir, compress=True)` (VACUUM INTO + optional gzip) + `prune_retained(dest_dir, keep=7)`. **#5 (WAL bloat during backup):** before `VACUUM INTO`, run `PRAGMA wal_checkpoint(PASSIVE)`; after the copy completes, run `PRAGMA wal_checkpoint(TRUNCATE)` so the `-wal` file cannot grow unbounded and block checkpoints during the snapshot. **#12 (WinError 32 file locking):** wrap the gzip + prune/delete steps in a `safe_gzip`/`safe_delete` helper with a retry+backoff loop (e.g. 3 attempts, `time.sleep(0.5)` between) — Windows Defender / search indexers briefly lock the freshly-created snapshot file, so an immediate compress/delete raises `PermissionError: [WinError 32]`. Wrap both in try/except.

**T8 — Seed** (`app/services/seed_service.py`): idempotent insert of new `permissions` rows + admin grants + default `sig_codes`/`price_codes`.

---

## 5. Frontend tasks (ordered)

**F1 — Contracts** (`types/contracts.ts`): add `Patient`, `PatientCreate`, `InsurancePlan`, `MembersGroup`, `SigCode`, `PriceCode`, `Dispense`, `SigCodeParseResult`, `InsuranceValidationResult` (mirror backend; money as `string`).

**F2 — API services** (`lib/api/`): `patients.ts` (list/get/create/update/remove/search, members, dispenses, history), `insurance.ts` (plans CRUD + validate), `dictionaries.ts` (sig/price CRUD + parse + ndc lookup), `dispense.ts` (`dispense`, `getLabel`).

**F3 — Hook** `hooks/usePatients.ts` mirroring `useInventory.ts` (filters, search w/ 300ms debounce, RBAC `canWrite` via `useCan`).

**F4 — Page** `app/patients/page.tsx` (auth-guarded). Co-located sub-components (no micro-files), tabbed `TabViewCompat`-style nav (General, Insurance Plan, Members Group, Rx/Refill, Patient History, Billing Info, Comments). General = demographics form (Name, DOB, Address, Driver License, Sex, Employer ID, Contact) **+ `patient_allergies` field (B: capture now, alert later) + `comments`**. Insurance = plan select + `InsuranceValidationResult` (active/coverage/copay) gating. Members Group = add/list dependents. Rx/Refill = list dispenses + Rx# field. Patient History = receipts+dispenses joined. Billing Info = copay/insurance amounts. Comments = free text persisted to `patients.comments`.

**F5 — POS integration** (`app/pos/page.tsx`): on barcode scan, call `ndcLookup`/`searchMedicines`; add a SIG-code chip selector (parse BID→text) and a "Dispense / Rx" toggle that, when a patient is linked, calls `dispense()` then prints. **#3 (thermal printing):** "Print Label" calls `getLabel()` which returns the **raw ESC/POS/ZPL byte stream** and sends it to the thermal printer through the Tauri sidecar (raw USB/Serial) — **never** `window.print()` (webview rasterizes barcodes → blurry/unscannable on 58/80mm). Reuse `useBarcodeScanner`, `usePosStore`, `decimalCurrency`. Add patient-link selector (search patients). RBAC: `useCan("dispense.create")`. **A (NDC fallback):** when the scan returns `found:false`, surface an inline "NDC not found in stock — Add to Inventory?" action (reuse the existing `StockModal`/receive-batch flow) so a never-stocked drug does not block the pharmacist. **#2 (LAN idempotency):** generate one `client_tx_id` via `crypto.randomUUID()` per submit and keep it stable across retries — on a network error after submit, retry with the **same** `client_tx_id` so the backend returns the cached result instead of double-deducting. **#6 (money float):** all cart/copay math goes through `lib/decimalCurrency` (integer cents) — never raw JS `number` arithmetic on money.

**F6 — Layout/nav:** register `/patients` route (add to `middleware.ts` protected paths) + a nav entry in the dashboard sidebar (reuse existing sidebar component pattern).

---

## 6. Phase 4 — Packaging & Windows services

**P1 — Tauri (verify, don't rebuild):** confirm `src-tauri/tauri.conf.json` bundles `.next/standalone` + FastAPI sidecar (per M94) and `src-tauri/tauri.dev.config.json` test identity works. No new code unless gaps found.

**P2 — NSSM + Caddy deploy script** (`deployment/install-windows-services.ps1`, new). Registers FastAPI + Next.js standalone as persistent Windows services for 4 GB thin clients (zero-config autostart); `Caddyfile` reverse-proxies `:80`→Next.js `:3000`, `/api`→FastAPI `:8000` with local TLS (self-signed). Must include the following thin-client fixes:

- **#2 (deployment topology — SMB hazard).** Restrict to a **master/server topology**: exactly **one** machine hosts `pharmacy.db` and runs the **single** FastAPI instance; client thin clients run **Next.js/browser only** and reach the master over LAN (`http://192.168.x.x:8000`). **Never** mount `pharmacy.db` over an SMB/CIFS share for multiple local FastAPI instances — SQLite SMB locking corrupts the DB and throws constant `SQLITE_BUSY`. Document this as the only supported topology.
- **#3 (venv pathing):** dynamically resolve the venv interpreter (`backend_fastapi/.venv/Scripts/python.exe` or `venv/Scripts/python.exe`) via `Resolve-Path` and pass its **absolute path** to NSSM (`nssm set FastAPIApp Application "C:\...\venv\Scripts\python.exe"` + `nssm set FastAPIApp AppParameters "-m uvicorn app.main:app --port 8000"` + `AppDirectory`). Never rely on a bare `python` (NSSM's service user PATH resolves to system Python → missing deps).
- **#2 (standalone static assets):** before registering Next.js, run `node scripts/prepare-standalone.mjs` (already referenced in the build) **plus** explicitly copy `.next/static` → `.next/standalone/.next/static` and `public` → `.next/standalone/public`. Otherwise the standalone server ships without CSS/JS/images and the kiosk renders unstyled. Register with `AppDirectory` at `.next/standalone` and `AppParameters "server.js --port 3000"`.
- **#4 (4 GB RAM starvation):** cap memory in the NSSM `AppParameters` / service start: Next.js node as `node --max-old-space-size=256 server.js`; set Tauri/Webview2 chromium flags `--disable-gpu-compositing` and `--renderer-process-limit=2` to curb long-shift memory leaks; keep uvicorn to a **single worker** (`--workers 1`, already the app's model). Target <70% RAM under load.
- **#13 (Next.js host binding & dual routing).** `server.js` binds `127.0.0.1:3000` by default; LAN clients and Caddy can't reach it. In the NSSM environment for Next.js set `HOST=0.0.0.0` and `PORT=3000`. Define **dual routing**: client-side fetches use **relative `/api/v1`** (Caddy-proxied to FastAPI); Next.js **Server Actions / SSR** `fetch` calls target internal loopback `http://127.0.0.1:8000` (bypasses the Windows Firewall loopback policy that can block external-IP SSR calls). Set `NEXT_PUBLIC_API_URL` empty/relative for the browser, and a server-only base `http://127.0.0.1:8000` for SSR.

---

## 7. Risks & failure modes

- **FK enforcement:** new patient→insurance FK requires `PRAGMA foreign_keys=ON` on every connection; missing it silently disables FKs (T1).
- **Audit hash chain:** any new audit write MUST go through the existing chain writer or `prev_hash` breaks verification — do not insert `audit_logs` directly (T3/T4).
- **FIFO inventory:** dispense reuses the same per-drug `asyncio.Lock` (`lock_manager.py`) + single-writer commit as POS checkout to avoid lost updates / `database is locked` (T5).
- **C (SQLite multi-terminal concurrency):** under 2+ concurrent POS/dispensing stations, writes to `dispenses`, `inventory_extended`, and `audit_logs` share one SQLite file. WAL + `busy_timeout=30000` + per-drug `asyncio.Lock` are already specified, but the critical discipline is that **every `dispense_service.py` write transaction must be short and atomic** — only FIFO deduction + `dispenses` insert + `receipts`/`receipt_items` + one audit row inside `session.begin()`; no external/HTTP calls inside the txn, so locks release in milliseconds. Reuse the `PosService` commit pattern exactly.
- **Money:** enforce Decimal/integer-cents end-to-end; no float in dispense price/copay (T2/T5).
- **Coverage gate:** new code must hold `fail_under=90` — write direct-`await` service tests + HTTP route tests (T9).

---

## 8. Validation (final gates)

Backend:
```
cd backend_fastapi
python -m pytest -q            # ≥90% coverage, 0 failures (new: test_patients, test_insurance,
                                #   test_dictionaries, test_dispense, test_backup)
python -m mypy app --strict    # 0 errors
```
Frontend:
```
npx tsc --noEmit               # 0 errors
npx next build                 # 15+ routes, exit 0
npx vitest run                 # new: usePatients.test.ts + contracts parity
```
Manual: create patient → bind insurance plan → validate coverage → scan NDC → dispense → confirm FIFO decrement + `dispenses` row + label text; `POST /api/v1/admin/backup` writes a compressed `snapshots/` file; on 4 GB VM, NSSM services start FastAPI+Next.js and Caddy serves locally.

Docs: update `PROJECT_MAP.md` (new tables/routers/milestone), `FLOW_LOGIC.md` (dispense data flow + audit reuse), `VERIFICATION_CHECKLIST.md` (patient UI gates). No `TODO`/`...`/placeholders committed.

---

## 9. Practical considerations (review notes — must be honored)

- **A. Master catalogue vs. local inventory (NDC fallback).** NDC lookups resolve only against `inventory_extended` (drugs you already stock). A scan of a never-stocked drug returns empty and would block the pharmacist. Mitigation is wired into **T6 dictionaries route** (`GET /ndc/lookup` returns `200 {found:false,q}`) and **F5 POS** (inline "Add to Inventory?" action reusing the receive-batch flow). Do not let an unknown NDC dead-end the UI.
- **B. Clinical safety guardrails (allergies/interactions).** Full drug–drug interaction + allergy decision support is deferred (scope discipline — correct). But `patient_allergies` is added to the `patients` schema **now** (T1/T2/F4) as a free-text/tag field so future allergy-alert banners need no further migration. No v1 alert logic required.
- **C. SQLite concurrency under multi-terminal load.** WAL + `busy_timeout=30000` + per-drug `asyncio.Lock` are necessary but not sufficient; the decisive factor is **short, atomic write transactions** in `dispense_service.py` (see §7). Keep the txn to FIFO deduction + dispense/receipt inserts + one audit row; never call external services inside `session.begin()`.

## 10. System-level multi-terminal / thin-client gaps (must be honored)

These close the gaps introduced by running on local Windows thin clients with 2+ concurrent POS terminals. Each is wired into a concrete task above (#N = source concern).

- **#1. SQLite write-lock deadlocks → `BEGIN IMMEDIATE` (corrected).** Deferred `BEGIN` lets two terminals each read then deadlock upgrading to a write lock (`SQLITE_BUSY`, not fixed by `busy_timeout`). **Correction:** do NOT run `await session.execute(text("BEGIN IMMEDIATE"))` inline — SQLAlchemy 2.0 `AsyncSession` already holds an implicit transaction, so raw `BEGIN` raises `sqlite3.OperationalError: cannot start a transaction within a transaction`. Fix: set **`isolation_level="IMMEDIATE"` on the write engine only** (T1.5); SQLAlchemy then issues `BEGIN IMMEDIATE` for every write `session.begin()`.
- **#2. Next.js standalone omits static assets.** `server.js` alone ships without CSS/JS/images. Mitigation: **P2** runs `prepare-standalone.mjs` + copies `.next/static`→`.next/standalone/.next/static` and `public`→`.next/standalone/public`.
- **#3. NSSM resolves system Python, not the venv.** Bare `python` skips the venv → missing-dep crash. Mitigation: **P2** resolves the venv interpreter absolute path (`...\venv\Scripts\python.exe`) and sets `Application`/`AppDirectory`/`AppParameters`.
- **#4. Soft-delete referential integrity.** `members_groups`/`dispenses` don't carry `is_deleted`; a soft-deleted patient's dispenses would inflate revenue / active-patient counts. Mitigation: **T3** — aggregations JOIN `patients` and filter `is_deleted = 0`; `active_count` excludes soft-deleted.
- **#5. Date precision & string comparison (refined).** `server_created_at`/`fill_date` are TEXT. A localized `DD/MM/YYYY` input, or a full timestamp where a date is expected, breaks sorting / `WHERE fill_date = '2026-08-22'` / range queries. Mitigation: **T2** enforces **two distinct formats** — date-only (`dob`, `fill_date`) = `YYYY-MM-DD`; event timestamps (`created_at`, `server_created_at`) = `YYYY-MM-DDTHH:MM:SSZ`; localized input rejected.
- **#6. SMB multi-terminal topology hazard.** If terminals mount `pharmacy.db` over SMB/CIFS and each runs its own FastAPI, SQLite SMB locking corrupts the DB and throws constant `SQLITE_BUSY`. Mitigation: **P2** restricts to a **master/server topology** — one machine hosts `pharmacy.db` + the single FastAPI instance; client thin clients run Next.js/browser only and call the master over LAN (`http://192.168.x.x:8000`). This is the only supported topology.
- **#7. Thermal printing must bypass webview print.** Browser `window.print()` rasterizes content → blurry/unscannable 1D/2D barcodes on 58/80mm and 2×1" labels, plus modal delays. Mitigation: **T5/F5** — `receipt_engine.py` emits **raw ESC/POS / TSPL / ZPL byte strings**; bytes are sent straight to the thermal printer via the Tauri sidecar (raw USB/Serial, `win32print` or raw socket). Never `window.print()`.
- **#8. 4 GB RAM starvation.** Node + Uvicorn + Caddy + Webview2 on 4 GB → swapping/stutter. Mitigation: **P2** caps Node `--max-old-space-size=256`, sets Webview2 `--disable-gpu-compositing --renderer-process-limit=2`, keeps uvicorn single-worker (`--workers 1`).
- **#9. WAL bloat during `VACUUM INTO`.** A long snapshot read holds a read lock, blocking checkpoints → `-wal` grows and slows subsequent writes. Mitigation: **T7** runs `PRAGMA wal_checkpoint(PASSIVE)` before the copy and `PRAGMA wal_checkpoint(TRUNCATE)` after.

## 11. Additional low-level edge cases (driver / LAN / hardware / Windows)

These close lower-level gaps the deployment introduces. Each is wired into a concrete task above.

- **#10. SQLite FK siloing across the pool.** `PRAGMA foreign_keys=ON` resets to OFF on every pooled connection; setting it only in `migrate_schema` leaves later API queries ignoring FKs (orphan `patient_id`/`insurance_plan_id`). Mitigation: **T1** puts the pragma inside the per-connection `_configure_pragmas` listener so every checkout connection enforces it.
- **#11. LAN dispense idempotency.** A LAN flicker after commit-but-before-200 makes the client retry → double stock deduction + duplicate receipts. Mitigation: **T2/T5/F5** add `client_tx_id` (UI `crypto.randomUUID`, stable across retries) persisted on `dispenses`/`receipts`; `DispenseService` returns the cached result if the id repeats within 5 min; `CheckoutRequest` gets the same field.
- **#12. Raw printer handle collision.** Direct ESC/POS/ZPL to a raw COM/USB handle bypasses the spooler; concurrent receipt+label writes throw `WinError 5` / Resource Busy. Mitigation: **T5** wraps all raw writes in a process-level `asyncio.Lock` (`printer_lock`) with a 100 ms inter-job delay in the sidecar/print service.
- **#13. WinError 32 during backup/gzip.** Defender/indexers briefly lock the freshly `VACUUM INTO` file, so immediate gzip/prune raises `PermissionError: [WinError 32]`. Mitigation: **T7** wraps gzip + delete in `safe_gzip`/`safe_delete` retry+backoff (3 tries, 0.5 s).
- **#14. Next.js host binding & dual routing.** `server.js` defaults to `127.0.0.1:3000`; LAN/Caddy can't reach it, and SSR→FastAPI over the external IP can hit the firewall loopback block. Mitigation: **P2** sets `HOST=0.0.0.0`/`PORT=3000` for Next.js and dual-routes: browser fetches use relative `/api/v1` (Caddy), SSR/Server Actions use `http://127.0.0.1:8000`.
- **#15. JSON money float pollution.** JS `JSON.parse` turns numeric JSON into IEEE-754 doubles (`19.899999999999998`). Mitigation: **T2** forces all currency fields to serialize as **2-decimal strings**; **F5** does all money math via `lib/decimalCurrency` (integer cents) — never raw `number` arithmetic.

## 12. Open questions (recommendations noted; safe to proceed)

- **Patient comments storage:** recommendation = add `patients.comments TEXT` in v7 migration (simplest). Alt: separate `patient_notes` table. Plan uses the column.
- **Dispense vs POS checkout overlap:** recommendation = retail OTC stays `/api/v1/pos/checkout`; prescription/Rx items route through `/api/v1/dispense` (patient-linked, sig-code, label). No behavioral change to existing checkout.
- **Prescriptions table:** deferred (out of scope, §2). "Rx/Refill" tab uses `dispenses` + free-text Rx number for now.
