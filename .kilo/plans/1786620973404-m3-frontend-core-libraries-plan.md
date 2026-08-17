# M3-FL — Frontend Core Libraries (Execution Plan)

> **Milestone label:** `M3-FL` (distinct from the already-✅-verified `M3 — Inventory Management & FIFO Basis`, `CHANGELOG.md:55`). User-selected scope = "Frontend foundation."
> **Spec source:** `MASTER_IMPLEMENTATION_PROMPT.md` §4.3–4.5 (state mgmt, type-contract sync, anti-`AttributeError` guarantee), §5 (API contract). No backend changes — backend contracts (`app/shared/schemas.py`) are the source of truth and stay unchanged.
> **Mode:** Plan only — no source changes here.

---

## 0. Status

- **User choice:** Option 1 — accept the implementation as the deliverable (no speculative rework).
- **Delivery state:** the M3-FL foundation is **delivered and verified** (`tsc --noEmit` → 0 errors; `next build` → 13/13 pages; 0 raw `api.get/post("/api/v1")` string paths in source). `types/contracts.ts`, `hooks/useInventory.ts`, `app/license/page.tsx` refactored; `app/dashboard/inventory/page.tsx` untouched (hook API preserved).
- **Naming deviation (verified against disk):** the planned `stores/cartStore.ts` (`useCartStore`) was delivered as **`stores/posStore.ts` (`usePosStore`)** and is a *superset* of the planned cart store — it adds an offline queue, merge-sync hub replay (exactly-once `client_txn_id`, causal order via Lamport `local_seq`), `SyncLock`, and cash-drawer `recordDrawer`. `app/pos/page.tsx` imports `usePosStore` + `@/lib/decimalCurrency` + `ManagerApprovalDialog`/`OfflineSyncBanner`/`ShiftCloseDialog`.
- **Codebase has advanced past M3-FL:** `lib/api/sync.ts` and `lib/api/approval.ts` also exist on disk (later milestones: Phase 2/3 POS, M9 sync). M3-FL's foundational goal (global stores + typed per-domain service layer + contracts) is met; later work extends it.
- **Backend contracts** (`app/shared/schemas.py`) unchanged — still the source of truth (M2 verified, `CHANGELOG.md:44`).

---

## 1. Context & Current State

**Already delivered (M2 + M8):**
- `types/contracts.ts` — comprehensive TS contracts (Medicine/Batch/StockLevel/Receipt*/Checkout*/SupplierRead/UserPublic/Token/ErrorResponse…).
- `lib/api.ts` — Axios singleton + request (Bearer attach) + response (401→refresh) interceptors.
- `stores/authStore.ts` — the **only** Zustand store present.
- `hooks/useInventory.ts` — inventory data-fetching in **component-local state** (not a global store).
- `hooks/useBarcodeScanner.ts` — keyboard-wedge scanner (local state).
- Pages: `login`, `dashboard`, `dashboard/inventory`, `pos`, `license`.

**Gap vs. spec (`MASTER_IMPLEMENTATION_PROMPT.md §4.4` defines 5 stores):** only `useAuthStore` exists. Missing `useCartStore`, `useInventoryStore`, `useLicenseStore`, `uiStore`. Also missing a **typed per-domain API service layer** — pages/hooks call `api.get("/api/v1/...")` with raw string paths, which works but bypasses the type-level "no dynamic access crosses a boundary" guarantee (§4.5).

**Goal of M3-FL:** deliver the shared frontend foundation (stores + service layer + contract sync + shared hooks) that the inventory / POS / dashboard / license / settings pages consume.

---

## 2. Decisions (recommendations — resolve as written unless flagged)

1. **Inventory state:** Add `useInventoryStore` (Zustand) as the canonical inventory state; refactor `hooks/useInventory.ts` to **read/write the store while preserving its current public return shape** so `app/dashboard/inventory/page.tsx` needs **no changes**.
2. **API service layer:** New `lib/api/<domain>.ts` modules wrapping the shared `api` instance with typed signatures. `lib/api.ts` stays the Axios singleton + interceptors. Pages/hooks/stores call the domain modules instead of raw string paths.
3. **Contract sync:** Extend `types/contracts.ts` with `CartLine`, `LicenseStatus`/`LicenseValidationResult`, `SystemSettingRead`, and promote `InventoryFilters` (currently local to `useInventory.ts`) to contracts. Verify parity against `app/shared/schemas.py` (MedicineRead, BatchRead, StockLevelRead, SupplierRead, ReceiptRead, CheckoutRequest/Result, UserPublic, Token, SystemSettingRead all already present).
4. **Shared hooks:** Keep `useBarcodeScanner`; refactor `useInventory` to back the store (decision 1). No new auth hook (`authStore` suffices).
5. **No backend changes.** This milestone is frontend-only.

---

## 3. Ordered Task List

- **TASK 1 — Contract additions (`types/contracts.ts`)**
  - Add `CartLine { product_name: string; quantity: number; unit_price: number }` (maps to backend `CheckoutLineIn` + `unit_price` for display).
  - Add `LicenseStatus` and `LicenseValidationResult` (loosely typed; confirm shape against Flask `license_gate.py` response at runtime — start with `{ status: string; key?: string; [k: string]: unknown }`).
  - Add `SystemSettingRead { key: string; value?: string | null }` (for the settings service).
  - Promote `InventoryFilters { vendor?; status?; lowStockOnly?; page? }` from `useInventory.ts` into contracts.
  - Keep `ProductRead = Medicine` alias; do **not** rename existing types.

- **TASK 2 — `stores/inventoryStore.ts` (NEW)**
  - State: `medicines: Medicine[] | null`, `stockLevels: StockLevel[] | null`, `suppliers: string[]`, `filters: InventoryFilters`, `isLoading`, `error`.
  - Actions: `loadSuppliers`, `applyFilters`, `search`, `refetch`, `receiveBatch`, `adjustBatch`, `updateMedicine`, `deleteMedicine` (signatures mirror `useInventory` today).
  - Internally use `lib/api/inventory.ts` (TASK 7).

- **TASK 3 — Refactor `hooks/useInventory.ts`**
  - Delegate all state + actions to `useInventoryStore` but **keep the exact current return object** (`medicines, stockLevels, suppliers, canWrite, isLoading, error, search, applyFilters, refetch, receiveBatch, adjustBatch, updateMedicine, deleteMedicine`). This keeps `app/dashboard/inventory/page.tsx` untouched.

- **TASK 4 — `stores/posStore.ts` (delivered as `usePosStore`, superset of planned `cartStore`) + POS adoption**
  - State: `lines: CartLine[]`, `error: string | null`, `result: CheckoutResult | null`, plus `tabId`, `offlineCount`, `syncing`, `hydrated`.
  - Actions: `addLine(product: ProductRead)`, `updateQty(name, delta)`, `remove(name)`, `clear()`, `setError`, `setResult`, `checkout()` (calls `lib/api/pos.ts.checkout`, enqueues offline on failure), `recordDrawer(payload, approvalToken)` (`lib/api/pos.ts.drawerMovement`), `flushQueue()`, `hydrate()`, `refreshOfflineCount()`.
  - Refactor `app/pos/page.tsx`: backed by `usePosStore` (not local `useState<CartLine[]>`); keeps barcode-scanner wiring, adds decimal-safe money (`@/lib/decimalCurrency`) + offline-sync banner + manager-approval/shift-close dialogs.
  - **Note:** name `cartStore.ts`/`useCartStore` in the original spec was realized as `posStore.ts`/`usePosStore`; functionally the cart requirement (TASK 4.1) is satisfied and then extended.

- **TASK 5 — `stores/licenseStore.ts` (NEW) + license adoption**
  - State: `licenseKey`, `hardwareId`, `status: LicenseStatus | null`, `loading`, `error`.
  - Action: `validate()` → `lib/api/license.ts`.
  - Refactor `app/license/page.tsx` to use the store (keep form UI).

- **TASK 6 — `stores/uiStore.ts` (NEW)**
  - State: `theme`, `sidebarOpen`, `activeTab`, `modal: { type?: string; payload?: unknown }`, `toast: { message?: string; kind?: "info"|"error"|"success" } | null`.
  - Actions: `toggleSidebar`, `setActiveTab`, `openModal/closeModal`, `showToast/clearToast`.
  - Optional adoption in existing pages (defer heavy UI work; include minimal modal/toast state now).

- **TASK 7 — Typed API service layer (`lib/api/*.ts`, NEW)**
  - `inventory.ts`: `listMedicines(params)`, `searchMedicines(q)`, `getStockLevels()`, `listSuppliers()`, `receiveBatch(payload)`, `adjustBatch(id, payload)`, `updateMedicine(id, payload)`, `deleteMedicine(id)`.
  - `pos.ts`: `checkout(payload: CheckoutRequest): Promise<CheckoutResult>`.
  - `auth.ts`: `login`, `refresh`, `logout`, `me` (thin wrappers; `authStore` already uses `fetch` for cookie flow — leave as-is or route through here; **do not break the HTTP-only cookie path**).
  - `license.ts`: `validateLicense(key, hwId): Promise<LicenseValidationResult>`.
  - `users.ts`: `listUsers()`, `getUser(id)` (for future admin UI).
  - `settings.ts`: `listSettings()`, `getSetting(key)` (for future settings UI).
  - All wrap the existing `api` instance from `lib/api.ts` with explicit generics.
  - **On disk also present (post-M3-FL, not in original scope):** `lib/api/sync.ts` (`pushSync` — merge-sync hub) and `lib/api/approval.ts` (manager approval). Do not delete; they belong to later milestones.

- **TASK 8 — Migrate raw calls (low-risk)**
  - `app/pos/page.tsx`, `app/license/page.tsx`, `hooks/useInventory.ts` → use the new service modules instead of `api.get("/api/v1/...")` string paths.
  - `app/dashboard/inventory/page.tsx` → unchanged (hook API preserved).

- **TASK 9 — Validation** (all ✅ confirmed pre-delivery)
  - `npx tsc --noEmit` → **0 errors** (frontend, 32 files). Backend `mypy --strict` remains 0.
  - `npx next build` → **compiles successfully** (13/13 pages). The pre-existing SSG `location is not defined` warning is unrelated to these changes.
  - `grep -r "api.get(\"/api/v1" app hooks stores` → **0 matches** (every raw string path migrated to the typed service layer).
  - `grep -rn "useState<CartLine" app/pos` → **0 matches** (POS now backed by `useCartStore`).
  - Manual smoke via `python run_services.py`: login → inventory (search/filter/receive/delete) → pos (scan + checkout) → license (validate). No console/type regressions.

---

## 4. Affected Files

**Create:** `stores/inventoryStore.ts`, `stores/posStore.ts` (was planned `cartStore.ts`), `stores/licenseStore.ts`, `stores/uiStore.ts`, `lib/api/inventory.ts`, `lib/api/pos.ts`, `lib/api/auth.ts`, `lib/api/license.ts`, `lib/api/users.ts`, `lib/api/settings.ts`. _(Also on disk: `lib/api/sync.ts`, `lib/api/approval.ts` — later milestones.)_
**Modify:** `types/contracts.ts`, `hooks/useInventory.ts`, `app/pos/page.tsx`, `app/license/page.tsx` (optional: `app/dashboard/inventory/page.tsx` — only if hook API changes, which it must not).
**Backend:** none.

---

## 5. Risks & Rollback

- **Low risk:** additive files + type-only refactors. Key safety rule — `useInventory` public API stays byte-compatible so the inventory page is untouched.
- **`auth.ts` cookie path:** must not alter the HTTP-only cookie login flow (`app/login/actions.ts`, `app/api/auth/*`). Leave `authStore.login`/`logout` as `fetch`-based; `auth.ts` is optional sugar.
- **Rollback:** delete new store/service files; `git revert` page edits. Backend gates (`pytest`, `mypy`) remain green by construction.

---

## 6. Open Questions (non-blocking — proceed with recommendations)

1. Should `uiStore` include a global toast/notification system now, or defer to a later UI milestone? → **Recommend: include minimal modal/toast state in M3-FL.**
2. `LicenseValidationResult` exact shape → confirm against Flask `license_gate.py` JSON at first runtime test; type loosely until observed.
3. `useInventoryStore` cross-tab cache invalidation → out of scope (single-tab kiosk); note for later multi-terminal work.
4. **Cart store naming:** planned `cartStore.ts`/`useCartStore` was delivered as `posStore.ts`/`usePosStore` and extended (offline sync/drawer). The minimal M3-FL cart contract is satisfied; no action required unless a rename to `cartStore` is desired for naming consistency.

---

# Part 2 — Remaining Actions & Project Completion Roadmap

> **M3-FL is complete and verified** — §0 below; it has **no remaining actions**. Part 2 is the step-by-step breakdown to finish the *entire* project (web app + desktop app + cross-cutting), grounded in `CHANGELOG.md`, the open plan tabs, `MASTER_CODING_PROMPT.md` (G1–G5 journeys, §3 stack), and the `.kilo/plans/*` backlog.

## 0. M3-FL status — DONE (no remaining actions)

Verified this session: `npx tsc --noEmit` → 0 errors; `npx next build` → 13/13 pages (exit 0); `grep api.get/post("/api/v1` across `.ts/.tsx` → 0 matches; `grep useState.*CartLine app/pos` → 0.
Delivered: `types/contracts.ts` additions; `stores/{inventoryStore,posStore,licenseStore,uiStore}.ts`; `lib/api/{inventory,pos,auth,license,users,settings}.ts` (+`sync`,`approval`); `useInventory` hook delegate; `app/pos/page.tsx`→`usePosStore`; `app/license/page.tsx`→`useLicenseStore`; `authStore.fetchCurrentUser` via service. Backend untouched. **Nothing further to do for M3-FL.**

## 1. Sequencing principle

Web app first (active surface with written specs), then desktop parity, then cross-cutting hardening → Definition of Done. Each item is independently shippable and gated.

## 2. PHASE A — Web app: POS Operational Security Addendum (immediate next; fully specified in `.kilo/plans/1786748052000-pos-operational-security-addendum.md`)

Execute the 5 concerns, each as: model/API change → frontend wiring → tests → gate.

1. **Shift reconciliation / drawer movements** — `app/core/models.py`: add `DrawerMovement` + enum (`cash_tender|float_add|cash_drop|paid_out|pickup|manager_adj`). `app/api/routers/pos_route.py`: `POST /shift/{id}/drawer-movement` (amount-gated; `paid_out`/`pickup` require `X-Approval-Token`). Update shift-close variance to `expected = opening_float + Σinflows − Σ(cash_drop+paid_out)`. Types: `DrawerMovementType`/`DrawerMovementIn`. UI: `app/pos/ShiftCloseDialog.tsx`. Tests **T23,T24**.
2. **Offline manager PIN** — Rewrite `lib/offlineCrypto.ts`: replace SHA-256 with **PBKDF2-HMAC-SHA256 (200k iters, WebCrypto)**, `crypto.subtle.timingSafeEqual`, encrypted attempt counter, **self-wipe at 3 failures** (`lib/db.ts` adds `manager_policies` store). Wire `ManagerApprovalDialog.tsx`. Tests **T25,H19**.
3. **Cart persistence durability** — `stores/posStore.ts` + `lib/storagePersist.ts`: persist active cart to `localStorage[pos_activecart_tab_{tabId}]`; recovery prompt for drafts <4 h old; 4 h staleness GC. `app/pos/page.tsx` recovery toast. Tests **H20–H22**.
4. **Expired/recalled/missing lot on replay** — `app/core/exceptions.py`: `StockStateError` hierarchy → **HTTP 410 Gone** with `{reason}`. `PosService.allocate()` raises typed errors; replay routes 410 → `offlineQueue.markDiscrepant(reason)` → `DiscrepanciesPanel` grouping (re-pick/restock/override). Malformed payload stays 400-retry. Tests **T26–T28**.
5. **Sync lock fallback** — New `lib/syncLock.ts`: 3-tier `acquireSyncLock`: WebLocks → BroadcastChannel (heartbeat/steal) → localStorage timestamp (30 s stale reclaim). Replace inline `navigator.locks.request` in `lib/offlineQueue.ts`. Tests **T29,H23**.

**Phase A gate:** `pytest tests/test_m10_hardening.py` (T23–T29) pass; `vitest run lib/offlineCrypto.test.ts stores/posStore.test.ts` (H19–H23) pass; `tsc --noEmit` 0; `next build` green; `mypy app --strict` 0.

## 3. PHASE B — Web app: remaining backlog (ordered; one plan file each in `.kilo/plans/`)

| Order | Plan file | Scope (one line) | Gate |
|---|---|---|---|
| B1 | `pos-hardening-extensions-plan.md` | C1–C5 POS hardening extensions building on A | pytest + vitest green |
| B2 | `pharmacy-backend-hardening-plan.md` / `backend-hardening-plan.md` | Auth/security hardening (RBAC edges, pepper, audit) | mypy 0, pytest green |
| B3 | `m9-m10-precommit-pos-spec.md` + `pos-unified-retail-spec.md` | Consolidate unified POS retail spec | spec→impl parity |
| B4 | `ota-delta-applier-plan.md` | OTA delta updater for field terminals | offline-apply tests |
| B5 | **Carried-forward gaps (CHANGELOG M8 status)** | (a) Returns workflow; (b) Reports CRUD (M5 read-only only); (c) PHI encryption-at-rest + role-scoped access; (d) Audit-log immutability hardening | feature tests + mypy |
| B6 | PostgreSQL path (`MASTER_CODING_PROMPT.md` §3.1) | `asyncpg` + Alembic migrations; `DATABASE_URL` switch | migration up/down + tests |
| B7 | Deployment (`§3.3`) | Docker Compose (FastAPI+Next, optional Flask), Nginx TLS, gunicorn; CI runs all gates | `docker compose up` smoke |
| B8 | Coverage ≥90% + ESLint/Prettier + **Playwright E2E** for G1–G5 | gate before "done" | coverage %, e2e green |

## 4. PHASE C — Desktop app (`archive/`) remaining

- **C1 (next):** `1786104259034-localization-banner-gaps.md` — RegionBanner + persistent nav indicator + `require_permission("settings.manage")` on region dropdown + DB-backed dismissal persistence + audit. Files: `localization_manager.py`, `database.py` (KV helpers), `ui_navigation.py`, `ui_dashboard_tab.py`, `ui_enterprise_settings.py`, `ui_banner.py` (NEW), `test_localization_banner.py`.
- **C2:** Remaining desktop backlog (share backend contracts — do NOT duplicate web work): `bulk-import-ui-plan`, `supplier-order-management-plan`, `epcs-workflow-plan`, `rx-*`, `hardening-roadmap-g5-g8-g9-g4`, `phase18-ui-polish-refactor-plan`, `enterprise-overhaul`, etc. Execute per their gates.
- **C3:** Keep `archive/` desktop and web app **schema/contract-synced** — both consume `app/shared/schemas.py` (web) / `pharmacy.db`; add a contract-drift CI check.

## 5. Cross-cutting Definition of Done (project completion)

All true → project complete:
- **Backend:** `pytest -q` green with coverage ≥90%; `mypy app --strict` 0 errors; `ruff` clean.
- **Frontend:** `tsc --noEmit` 0; `next build` 13/13; `vitest` + **Playwright E2E** (G1 POS, G2 receiving, G3 inventory, G4 RBAC admin, G5 license) green.
- **Security:** no hardcoded secrets (env-only); bcrypt/argon2; JWT expiry; network rate-limit (M10) + offline PIN PBKDF2 (A2) + PHI encryption (B5c); audit immutability (B5d).
- **Deploy:** Docker Compose + Nginx TLS; CI runs backend+frontend+e2e gates per PR.
- **Docs:** every milestone gets a `CHANGELOG.md` ✅ entry; `PROJECT_MAP.md`/`FLOW_LOGIC.md` synced; G1–G5 journeys demonstrably satisfied by E2E.

## 6. Recommended single forward path

1. **A** POS Operational Security Addendum (immediate, fully specced).
2. **B1–B4** hardening / consolidation / OTA.
3. **B5** carried-forward functional + security gaps.
4. **C1–C3** desktop localization + remaining desktop plans + contract sync.
5. **B6–B8** multi-DB, deployment, coverage/e2e → **Definition of Done**.

---

## 7. Verified remaining-work status (corrects Part 2 — verified 2026-08-17)

Cross-checked the addendum against the actual repo. Several concerns are **already implemented and green**; Part 2's "execute all 5" framing is over-broad. Precise status:

| Concern | Backend | Frontend | Tests | Status |
|---|---|---|---|---|
| A1 drawer movements | `DrawerMovement` model + `/drawer/movement` + `record_drawer_movement` (running balance) + `/approve` | `ShiftCloseDialog` (approval flow) | `test_drawer_movement_requires_approval` ✅ | **DONE** — BUT shift-close variance formula (`expected = float + Σinflows − Σoutflows`), paid-out auto-approve threshold (<\$50), T23/T24 ✗ |
| A2 offline PIN | server `requestApproval` only | offline fallback **not** built | H19/T25 ✗ | **NOT STARTED** — `lib/offlineCrypto.ts` has PBKDF2-200k but only for PII AES-GCM; no `verifyPinOffline`/attempt-wipe/`manager_policies` store. **(Scope Q: confirm offline fallback required.)** |
| A3 cart persistence | IndexedDB persistence via `storagePersist`/`posStore.hydrate` (per-tab `tabId`) | hydrate + `online` replay exist | H20–H22 ✗ | **PARTIAL** — durability ✅; recovery prompt for <4 h drafts + 4 h GC sweep ✗ |
| A4 expired-lot 410 | `StockStateError` family (410) + `fifo_deduct` raises + **live** checkout 410 ✅ | `DiscrepanciesPanel` only lists `getQueue()` (no 410/discrepancy reason grouping) | live-checkout 410 ✅; **T26–T28 (offline replay → discrepancy) ✗** | **PARTIAL** — live ✅; **offline-replay 410→markDiscrepant→DiscrepanciesPanel ✗** |
| A5 sync lock | — | `lib/syncLock.ts` (3-tier: in-mem + BroadcastChannel + server probe; does **not** use `navigator.locks`, so the addendum's TypeError risk is already avoided) — wired in `posStore` | T29/H23 ✗ | **FUNCTIONALLY DONE** (different tiering than addendum; localStorage tier optional) |

### Verification evidence
- `cd backend_fastapi && python -m pytest tests/test_pos_hardening.py -q` → **PYTEST_EXIT=0** (7/7 pass).
- `npx tsc --noEmit` → 0 errors; `npx next build` → 13/13 (TSC=0, NEXT=0).
- `grep api.get/post("/api/v1` in `.ts/.tsx` → 0; `grep useState.*CartLine app/pos` → 0.

### Precise remaining implementation list (Phase A)

**A1 (remaining): shift-close variance formula**
1. `app/api/routers/pos_route.py`: `/drawer/movement` — auto-approve small `cash_drop` (< \$400) without token; `paid_out` \$50–\$400 auto-approve; only above limit requires `X-Approval-Token`. (Currently *all* movements require a token.)
2. Backend shift-close RPC: compute `expected = opening_float + Σ float_add/manager_add − Σ(cash_drop/paid_out/pickup)`; return variance.
3. `components/ShiftCloseDialog.tsx`: render variance + over/under.
4. Tests **T23** (`test_shift_expected_cash_with_drop`: float 100 + takers 250 − drop 150 → variance 0), **T24** (`test_paid_out_requires_approval_over_threshold`: paid_out 51 without token → 409; with token → 201). Add to `tests/test_pos_hardening.py`.

**A2 (scope Q): offline manager PIN**
1. `lib/db.ts`: add `STORE_MANAGER_POLICIES = "manager_policies"` object store.
2. `lib/offlineCrypto.ts`: add `verifyPinOffline(pin, policy)` (PBKDF2-200k, `crypto.subtle.timingSafeEqual`, encrypted `attempt_counter`, self-wipe at `OFFLINE_MAX_ATTEMPTS=3`) — **preserve** existing `encryptString`/`decryptString`/`deriveKey` (PII).
3. `components/ManagerApprovalDialog.tsx`: fall back to `verifyPinOffline` when `/approve` is unreachable (502/offline), reading `ManagerPolicy` from IndexedDB.
4. Tests **T25** (brute-force resistance + wipe), **H19** (constant-time compare).
5. ⚠️ **Open design question (blocker):** current code is online-only (no offline approval fallback exists). Implement the offline PIN fallback per the addendum, **or** mark "offline POS approval" explicitly N/A and close A2. *Recommended: implement (POS must operate offline per R1/R6).*

**A3 (remaining): recovery prompt + GC**
1. `lib/storagePersist.ts`: add `RECOVERY_WINDOW_MS` + `sweepStaleTabs(exceptTabId)` (GC drafts older than window).
2. `stores/posStore.ts` `hydrate()`: scan `STORE_KV` for `pos_activecart_tab_*` keys (last-write < 4 h, ≠ current tab) → emit recovery candidates; `app/pos/page.tsx`: non-blocking recovery toast (restore merges against live stock).
3. Tests **H20**, **H21**, **H22**; create `stores/posStore.test.ts` + `lib/offlineCrypto.test.ts`.

**A4 (remaining): offline-replay 410 → discrepancy**
1. `types/contracts.ts`: extend `SyncPushResult` with `discrepancies: {client_txn_id, reason}[]`.
2. Backend sync route (`app/api/routers/sync_route.py`): return per-entry results incl. 410 reasons (LOT_EXPIRED/LOT_RECALLED/LOT_MISSING) — *verify current return shape first*.
3. `lib/offlineQueue.ts`: add `markDiscrepant(id, reason)` (`id` already on `OfflineEntry`).
4. `stores/posStore.ts` `flushQueue()`: for entries the backend reports 410/discrepant → `markDiscrepant` (NOT `removeEntry` — keep `client_txn_id`, do not retry).
5. `components/DiscrepanciesPanel.tsx`: add discrepancy view grouping by `reason` (re-pick / restock / manager-override), fed by `getDiscrepancies()`.
6. Tests **T26** (expired-lot replay → 410, `reason=LOT_EXPIRED`, outbox `discrepant`, no retry), **T27** (recalled 410 → DiscrepanciesPanel count), **T28** (malformed → 400 retry 3×).

### Phase A gate (re-checked against reality)
- Backend: `pytest tests/test_pos_hardening.py` (incl. new T23-T28) → green; `mypy app --strict` 0.
- Frontend: `vitest run lib/offlineCrypto.test.ts stores/posStore.test.ts` → H19-H23 green; `tsc --noEmit` 0; `next build` green.
- Smoke: `python run_services.py` → POS scan + checkout (incl. 410 lot surfaced in DiscrepanciesPanel) → inventory search/filter/receive/delete → license validate.
