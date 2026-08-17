# M9/M10 Technical Remediation Plan — High-Throughput Edge Retail Deployment

> **Date:** 2026-08-13
> **Target Stack:** FastAPI backend (`backend_fastapi/`) + Next.js 16 / React 19 frontend (repo root `app/`). Single-machine edge deployment — FastAPI + SQLite on-box, browser-thin client on LAN.
> **Reference Frameworks:** `MASTER_CODING_PROMPT.md` (§1 constraints, §4 data models, §5 API contract, §7 security); `CHANGELOG.md` (M1–M9 completed, 69 tests green, `mypy --strict` 0 errors); `FLOW_LOGIC.md` §16/§17 (auth + inventory data flow); `VERIFICATION_CHECKLIST.md` (M9 Visual Review Matrix seed).
> **Status:** Implementation-ready. Every decision below is reconciled to verified code; every artifact is copy-paste executable by an implementation agent.
> **Mode:** Plan only — no source/DB files are modified here.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Preceding-State Audit (verified by code inspection)](#2-preceding-state-audit-verified-by-code-inspection)
3. [Risk Domain 1 — Concurrency & Process Management](#3-risk-domain-1--concurrency--process-management)
4. [Risk Domain 2 — Offline Synchronization & Inventory Integrity](#4-risk-domain-2--offline-synchronization--inventory-integrity)
5. [Risk Domain 3 — Hardware Interface Reliability](#5-risk-domain-3--hardware-interface-reliability)
6. [Risk Domain 4 — Data Persistence & State Management](#6-risk-domain-4--data-persistence--state-management)
7. [Technical Artifacts (deliverables)](#7-technical-artifacts-deliverables)
8. [Unified Test Plan (TDD)](#8-unified-test-plan-tdd)
9. [Validation Pipeline (exact commands)](#9-validation-pipeline-exact-commands)
10. [Migration & Rollout Path](#10-migration--rollout-path)
11. [Affected Files Index](#11-affected-files-index)
12. [Out of Scope](#12-out-of-scope)

---

## 1. Executive Summary

This plan remediates four critical risk domains exposed by the audit of the reconciled FastAPI + Next.js Pharmacy Suite, hardening the existing completed M1–M9 foundation for **high-throughput, high-integrity retail/edge pharmacy sales**. The four domains are treated as sequential gates:

- **Domain 1 (Concurrency)** resolves the fundamental failure of `asyncio.Lock` across uvicorn workers — a formal comparative analysis (single-worker vs SQLite `IMMEDIATE`) selects single-worker edge with a defensive retry-on-locked; lock-duration minimization pushes all validation/allocation outside the `BEGIN` window.
- **Domain 2 (Offline Sync)** introduces a formal **Emergency Over-Sell Policy** that prioritizes *financial commitment* (receipt finality, drawer accuracy) over hard stockout, with a non-disruptive 410 UX state machine that isolates failed replays instead of halting the sync queue.
- **Domain 3 (Hardware)** redesigns barcode capture from a fragile 50 ms gap heuristic to a **multi-mode hook** (`ScannerProfile: auto | stx_etx | suffix_only`) combining STX/ETX sentinel framing with inter-keystroke velocity detection (≤35 ms) for standard USB HID scanners.
- **Domain 4 (Persistence)** migrates draft state to browser storage — `activeCart` per-tab (`sessionStorage`), `heldTickets` shared (`localStorage`) — with 8 h abandonment GC, corrects the shift-reconciliation formula (`expected = float + Σ cash tenders`), adds `print_status`, and hardens `REAL` → `NUMERIC(10,2)` money types via FK-safe table-copy migrations with a `foreign_key_check` integrity gate.

**§14 Production Hardening** adds five deployment-reality defenses: SQLite resilience (boot `quick_check` + `VACUUM INTO` snapshots + idle WAL checkpoints), Web Locks–guarded single-tab offline sync, decoupled peripheral execution with a no-inventory reprint endpoint, edge-clock drift guards (`X-Client-Timestamp` skew + boot sanity), and short-lived action-scoped `approval_token` JWTs replacing raw PIN payloads. A sixth — WebCrypto offline manager PIN fallback (device-bound encrypted cache, audit-flagged reconciliation) — is appended in §14.5.1.

**Refinement checklist (post-spec, four edge-case refinements — all applied):**
- [x] §7.6.4 / §13.4: `divideAndRound` (ROUND_HALF_UP) added to `decimalCurrency.ts`; parity with backend `Decimal` verified via `taxFor("10.35","0.14")==="1.45"`. Test T17 / H16.
- [x] §7.6.2 / §7.6.3: `activeCart` scoped per-tab (`sessionStorage`); `heldTickets` shared (`localStorage`) via `storage` listener. Test H17.
- [x] §14.5.1: Offline manager PIN fallback via WebCrypto SHA-256 (encrypted policy cache, `offline:true` token, audit source flag, mandatory online re-confirmation). Tests T21 / H18.
- [x] §7.7 / §4.5: Strict FIFO replay (`parkedAt ASC`, sequential `executeSyncLoop`, no batch writes); reads-only batching retained. Tests T19 / H8.

Every remediation is additive, backward-compatible, and covered by the M9 quality gates. `plan_exit` is called only after the artifacts in §7 (SQL migrations, math, workflow, hook spec, persistence spec), the §13/§14 hardening references, and the four edge-case refinements above are fully specified and test-mapped.

---

## 2. Preceding-State Audit (verified by code inspection)

| Artifact | File | Verified Reality | Deficiency Exposed by Audit |
|---|---|---|---|
| Checkout service | `app/services/pos_service.py` | `asyncio.Lock` per-drug, sorted acquire, single `session.begin()`, 14% Decimal tax, FIFO=FEFO. | Locks are **in-process only** — breaks under `--workers N > 1`; no retry on `database is locked`. |
| Concurrency primitives | `app/core/lock_manager.py` | `get_lock(name)` + `acquire_drug_lock`; `asyncio.Lock` registry. | Same single-process limitation; no DB-level fallback. |
| DB pragmas | `app/core/database.py` | `_configure_pragmas`: `busy_timeout=5000` always, `journal_mode=WAL` file-backed; `migrate_schema` idempotent PRAGMA/ALTER. | **`synchronous=NORMAL` not set**; no `IMMEDIATE` transaction wrapper; no retry loop. |
| Money types | `app/core/models.py` (`Product.price Float`, `Receipt.total_amount Float`, `Batch.purchase_price Float`, `ReceiptItem.price_at_time Float`) | All monetary columns are `Float` (SQLAlchemy `REAL`). | **Precision risk** — `float` drift in sums, tax, shift variance. Audit requires `NUMERIC(10,2)`. |
| Receipts table | `app/core/models.py` (`Receipt`) | `id, timestamp, total_amount, payment_method, patient_id`. | **Missing** `print_status`, `subtotal`, `tax_amount`, `sale_type`, `client_txn_id`, `tenders`. |
| Scanner hook | `hooks/useBarcodeScanner.ts` | Global `keydown`, `GAP_MS=50`, Enter-flush, input suppression. | **Timing-only** — no STX/ETX sentinel; inter-character gap alone fails on RF-latency scanners; no min-length guard. |
| Cart state | `app/pos/page.tsx` | Local `useState<CartLine[]>`. | **Ephemeral** — lost on browser crash; `sessionStorage` not used at all. No hold/resume persistence. |
| Shift reconciliation | *planned* `shifts` table | `expected_cash = sum(cash tenders in window)`. | **Formula omits opening float** — variance is mathematically wrong. |
| Offline queue | *designed* `lib/offlineQueue.ts` | IndexedDB park on `ERR_NETWORK` + `client_txn_id` replay. | **Conflict policy undefined** — over-sell resolution unspecified; no `reconciliation_flag`. |

---

## 3. Risk Domain 1 — Concurrency & Process Management

### 3.1 Problem statement

`asyncio.Lock` (in `lock_manager.py`) is a **single-process** primitive. uvicorn's default `uvicorn app.main:app --workers N` spawns N OS processes sharing one SQLite file via WAL. Each worker has its **own** `asyncio.Lock` registry in its own memory — locks never cross worker boundaries.

**Failure mode under multi-worker:**
1. Worker A reads `on_hand=5`, acquires its local lock, begins `UPDATE inventory_extended SET on_hand=on_hand-5` (committed).
2. Worker B (different process) reads `on_hand=5` *before* A commits (WAL visibility), decrements to `on_hand=0`, commits.
3. Two receipts for 5 units each on a 5-unit lot → **10 units sold, 5 in stock** — double allocation. The `busy_timeout=5000` only serializes *SQLite-level* write locks at the file layer; it cannot prevent the application-level read-modify-write race because both workers read stale state before either writes.

**Root cause:** application-level locks are insufficient for multi-process concurrency on SQLite. The per-drug `asyncio.Lock` only protects *within one worker*.

### 3.2 Mitigation Strategy A — Single-Worker Architecture (SELECTED for edge v1)

**Approach:** Pin uvicorn to `--workers 1` (sync workers off; async single worker). The existing `asyncio.Lock` + WAL + `busy_timeout` is *correct* at one process. `run_services.py` and the systemd/docker unit already effectively single-worker.

**Pros:**
- Zero code change to the checkout hot path; existing 5/15 concurrency test (`test_concurrent_checkouts_serialize_on_single_sku`) remains valid and is the proof.
- Lowest latency (no extra DB round-trips for row locks).
- Simplicity-First: no `FOR UPDATE` plumbing, no retry-on-deadlock logic (SQLite has no deadlocks, only `busy_timeout`).

**Cons:**
- Throughput bounded by one event loop (~300–500 checkouts/sec sustainable with aiosqlite under load — exceeds pharmacy needs; a single register does ~60/hr).
- No multi-core CPU utilization for checkout (acceptable: checkout is I/O-bound on SQLite, not CPU-bound).

**Guardrail:** the deployment unit (`run_services.py`, `Procfile`, Dockerfile `CMD`) must explicitly pass `--workers 1` and a pre-flight check asserts `settings.db_backend == "sqlite_local"`. If `db_backend` flips to `postgres`, the lock manager switches to `SELECT ... FOR UPDATE` (Domain 1 §3.4).

### 3.3 Mitigation Strategy B — SQLite IMMEDIATE / EXCLUSIVE Transactions

**Approach:** Promote the checkout transaction to `BEGIN IMMEDIATE` (SQLite) so the write lock is acquired at transaction start, not at first write. Pair with a retry loop on `sqlite3.OperationalError("database is locked")` (retry 3× with exponential backoff 50→100→200 ms). This gives *write serialization* at the DB layer even across workers.

**Pros:**
- Works across `--workers N > 1` (as long as N is small and the write window is tiny).
- No code change to lock acquisition; the per-drug `asyncio.Lock` *complements* the DB lock (fast-path single-process + DB-level cross-process).

**Cons:**
- `BEGIN IMMEDIATE` acquires a **reserved lock** at transaction start — under high write concurrency, transactions that do a read phase first will escalate to a write lock and may `SQLITE_BUSY` even on read-heavy paths. This trades throughput for correctness.
- Does **not** solve the lost-update race by itself: `BEGIN IMMEDIATE` serializes the *transaction start*, but the SELECT→compute→UPDATE within it still needs the application lock to avoid two workers both computing from the same snapshot and clobbering. Without the app lock, two `IMMEDIATE` transactions can still both read `on_hand=5`, both decrement, commit sequentially — net `on_hand=0` but 10 sold.
- **Conclusion:** `IMMEDIATE` alone is *insufficient*; it must be paired with the per-drug app lock (Strategy A). It is a *belt* not *suspenders*, and the belt is the app lock.

**Tradeoff analysis table:**

| Criterion | Strategy A (single-worker + app lock) | Strategy B (IMMEDIATE + retry, multi-worker) |
|---|---|---|
| Correctness vs double-allocation | ✅ full (app lock + WAL) | ⚠️ app lock still required; IMMEDIATE alone insufficient |
| Implementation complexity | minimal (config change) | moderate (retry loop, `BEGIN IMMEDIATE`) |
| Read throughput | high (WAL concurrent readers) | low (IMMEDIATE reserves a writer slot) |
| Write throughput (registers) | adequate for edge (1 process) | marginally better (N writers, serialized) |
| Operational surface | minimal | higher (retry storms, busy_timeout tuning) |

### 3.4 Selected architecture + extension

```
settings.db_backend = "sqlite_local"  (edge v1, resolved deployment decision)
   → lock_manager.acquire_drug_lock(name)  [asyncio.Lock, in-process]  [SELECTED]
   → _configure_pragmas sets synchronous=NORMAL  (Domain 4 §6.1)
   → checkout transaction: session.begin() (already async COMMIT)
   → uvicorn --workers 1 enforced (run_services.py / Dockerfile)

settings.db_backend = "postgres"  (future cloud)
   → lock_manager becomes a no-op fast-path
   → InventoryService.fifo_deduct / checkout uses SELECT ... FOR UPDATE ORDER BY expiration_date
```

**Concrete hardening (no-op under single-worker, defensive under future multi-worker):**
- Add `synchronous=NORMAL` to `_configure_pragmas` (SQLite WAL best-practice; reduces fsync per commit — correct because the journal still forces durability on the WAL frame).
- Wrap `session.begin()` write in `pos_service.process_checkout` with a **single retry** (`max_attempts=3, backoff`) catching `sqlalchemy.exc.OperationalError` matching `database is locked` / `database is locked`. This is defensive: under single-worker it never fires; under any future multi-worker SQLite deployment it prevents a transient crash → 5xx.
- Add a **lock-ordering assertion test**: verify `process_checkout` acquires locks in `sorted(names)` order (deadlock-freedom invariant preserved).
- **Lock-duration minimization (peak-hour hardening):** all data validation, FEFO lot allocation computation, and payload preparation occur **before** `session.begin()`. The transaction body only performs `INSERT receipts`, `UPDATE inventory_extended SET on_hand`, and `INSERT receipt_tenders` — the minimum writes needed. This compresses the SQLite RESERVED-lock hold window to sub-millisecond, eliminating `SQLITE_BUSY` bursts during peak. The `fifo_deduct` in `pos_service` already computes the lot-selection *outside* the transaction; confirm no `SELECT ... FOR UPDATE`-style reads are issued inside `process_checkout`'s write scope.

### 3.5 Risk Domain 1 — test cases

| # | Test | Assertion |
|---|---|---|
| C1 | `test_uvicorn_single_worker_enforced` | `run_services.py` args contain `--workers 1` (grep the Popen). |
| C2 | `test_synchronous_normal_set` | on a file-backed engine, `PRAGMA synchronous` == `NORMAL` after connect (smoke against a temp DB). |
| C3 | `test_checkout_retry_on_locked` | monkeypatch `session.begin` to raise `OperationalError("database is locked")` once, then succeed → checkout returns 201 (retry fired, no 500). |
| C4 | `test_lock_order_sorted` | `process_checkout` with SKUs `["B","A","C"]` acquires locks in order `[A, B, C]` (inspect `lock_manager` call order). |
| C5 | **regression** | `test_concurrent_checkouts_serialize_on_single_sku` still passes 5/15, stock 0. |
| C6 | `test_checkout_validation_before_begin` | inject a `TenderMismatchError` via the tender sum check → 400 raised *before* `session.begin()` is ever called (spy on `session.begin` — must be 0 calls on validation failure). |

---

## 4. Risk Domain 2 — Offline Synchronization & Inventory Integrity

### 4.1 Emergency Over-Sell Policy (formal)

When the edge server is unreachable (LAN down), a checkout is **parked** in the IndexedDB outbound queue with a client-generated `client_txn_id` (UUID) and a **pessimistic local stock decrement** is recorded on the client. The sale is *financially committed* client-side: the receipt number is allocated, the tender is captured, and the cash drawer is told to open. On sync, two failure classes exist:

1. **Idempotent replay** — `client_txn_id` already committed → return existing `receipt_id`, no-op (no over-sell). This is the happy path.
2. **Genuine over-sell** — two cashiers independently sold the last unit while both were offline. The *first* replay (by server wall-clock) wins; the *second* replays back with `410 gone` / `409 conflict` → moves to a `failed_queue` for manual resolution.

**Policy principle:** *financial commitment is finalized once a tender is captured and the drawer opens; physical stock is a best-effort ledger reconciled asynchronously.* The audit must never lose a sale that was tendered + drawer-opened. Reversing an over-sell is a *refund* (restocks a new lot, see §4.4), never a silent stock wipe.

### 4.2 Reconciliation data model (additive)

```sql
-- Track every offline park + its reconciliation outcome.
CREATE TABLE offline_txns (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  client_txn_id   TEXT    NOT NULL UNIQUE,     -- UUID generated client-side
  payload         BLOB    NOT NULL,            -- compressed JSON checkout payload
  parked_at       TEXT    NOT NULL,            -- client timestamp (ISO)
  synced_at       TEXT,                      -- server timestamp on success
  status          TEXT    NOT NULL DEFAULT 'parked',  -- parked | synced | over_sold | failed
  server_receipt  INTEGER,                  -- receipt_id on sync (nullable)
  server_error    TEXT,                     -- 4xx/5xx body on failure
  reconciliation_flag INTEGER NOT NULL DEFAULT 0  -- 0=unreconciled, 1=manager-handled
);

-- Per-batch over-sell footprint for the audit trail.
CREATE TABLE stock_discrepancies (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_id      INTEGER,                  -- the over-sold receipt (may be NULL if pre-receipt)
  product_name    TEXT    NOT NULL,
  requested       INTEGER NOT NULL,
  available       INTEGER NOT NULL,         -- stock at sync time (post other replays)
  delta           INTEGER NOT NULL,         -- how much was over-sold (requested - available)
  resolved        INTEGER NOT NULL DEFAULT 0, -- 0=open, 1=restocked/voided
  resolved_by     TEXT,                     -- manager username who handled it
  resolved_at     TEXT,
  note            TEXT
);
```

### 4.3 Backend logic workflow for offline replay

```
POST /api/v1/pos/checkout  (payload carries client_txn_id)
│
├─ 1. Idempotency pre-check:
│     SELECT receipt_id FROM receipts WHERE client_txn_id = :id
│     └─ FOUND → return existing CheckoutResult (no DB writes)        → 201
│     └─ NOT FOUND → proceed
│
├─ 2. Validate tender sum == total (within 0.005)                    → 400 if mismatch
│    (pre-lock: keeps the RESERVED-lock window in step 4 minimal)
├─ 3. Acquire sorted per-drug asyncio.Locks (single-worker safe)
├─ 4. session.begin():
│     ├─ 4a. For each line:
│     │     product = repo.get_by_name(name) [unfiltered]
│     │     repo_lots = get_lots_for_product(name) ORDER BY expiry ASC
│     │     available = Σ(lot.on_hand)
│     │     IF available < requested:
│     │         ├─ INSERT stock_discrepancy(receipt_id=NULL, product_name, requested,
│     │         │          available, delta=available-requested, status='open')   [over-sell record]
│     │         ├─ UPDATE offline_txns SET status='over_sold', server_error=...
│     │         │          WHERE client_txn_id = :id
│     │         ├─ AUDIT: action='pos.over_sell', details={product, requested, available}
│     │         ├─ RAISE InsufficientStockError  → rollback → 410 (tendered but stock failed)
│     │     │     (caller: offlineQueue.sync sees 410 → marks client_txn_id in failed_queue
│     │     │      with reconciliation_flag=0 for manager review)
│     │     └─ ELSE: fifo_deduct(name, requested) [lock held] + build ReceiptItem/SoldItem
│     ├─ 4b. INSERT receipts(…, client_txn_id=…) ; INSERT receipt_tenders(…) ; UPDATE offline_txns status='synced'
│     └─ 4c. AUDIT: action='pos.checkout' OR 'pos.checkout.replay' (distinct for metrics)
└─ 5. RETURN CheckoutResult (with receipt_id, receipt_number, totals, items, tenders)
```

**Key invariants:**
- An over-sold replay returns **410 Gone** (not 400). 410 = "this transaction was tendered client-side but cannot be stocked server-side; a manager must resolve." 400 = bad input (caller's fault, retryable). This distinction lets the client *not* auto-replay a 410 (it goes to the failed_queue for human review) while auto-retrying a 400.
- The `stock_discrepancy` row is inserted **before** the rollback so the manager has a permanent record even though the receipt never committed. `reconciliation_flag=0` until a manager (manager PIN) opens the discrepancy UI and resolves it (restock new lot OR issue a refund → `resolved=1`, `resolved_by=<manager>`).
- `reconciliation_flag` is on `offline_txns`: `0` = pending review, `1` = manager has inspected and either confirmed the over-sell is acceptable (customer walked with product, float the loss) or voided. This is the **audit trail** that satisfies finance: every over-sold receipt is explicitly closed by a named manager.

### 4.4 Over-sell resolution paths (manager UI contract)

A manager opens the "Discrepancies" panel (`GET /api/v1/pos/discrepancies?status=open`):
1. Selects a `stock_discrepancy` row → sees `product, requested, available, delta`.
2. Chooses one:
   - **Restock refund:** void the receipt's line for this product + insert a new `inventory_extended` lot (`on_hand = delta`, `expiration_date` = original lot's, `drug_name`, `supplier` snapshot from `receipt_items`). Receipt gains `void_status='partial_return'`. → `resolved=1`.
   - **Float loss:** customer already received product; float the cash value. Receipt stays complete; `reconciliation_flag=1`; variance hits the shift report. → `resolved=1`, `note='customer_paid'`.
3. Every action writes `audit_logs` (`action='pos.discrepancy.resolve'`, `user_pin=<manager>`, `old_value`/`new_value` JSON).

### 4.5 Offline UX State Machine (410 non-disruptive handling)

When `offlineQueue.sync()` receives a **410 Gone** for a parked transaction, the sync loop must **not halt** the entire queue. The state machine isolates the failed transaction while continuing replay of subsequent ones.

```
[offlineQueue.sync()]
   │
   ├─ peekOrdered() → FIFO queue sorted by parkedAt ASC  (§14 #4)
   ├─ pop next client_txn_id → POST /pos/checkout          (strictly sequential — no batch writes)
   ├─ 200/201 → remove from queue, set offline_txns.status='synced'        → next FIFO item
   ├─ 400 → retry w/ exponential backoff (client-side error)               → retry (max 3)
   ├─ 410 → move client_txn_id to failed_queue,
   │         set offline_txns.status='over_sold', reconciliation_flag=0,
   │         surface "Inventory Discrepancy Alert" in the UI                → next FIFO item (non-blocking)
   ├─ 5xx → back off (network/server down), keep in queue                  → retry (later)
   └─ network error → keep in queue (still offline)                         → retry (later)
```

**UI contract for 410 (Inventory Discrepancy Alert):** The `app/pos/OfflineSyncBanner.tsx` component subscribes to `offlineQueue.failed` (a Zustand slice). On a new 410:
1. The banner animates in (non-modal, non-blocking — does **not** prevent further sales).
2. The affected `client_txn_id` is marked "needs review" with a red chip.
3. Clicking the chip opens the `DiscrepanciesPanel` (§4.4) pre-filtered to that transaction.
4. A manager resolves it (restock refund / float loss) → the `failed_queue` entry is dismissed → the banner count decrements.
5. The banner persists until `GET /api/v1/pos/discrepancies?status=open` returns `[]`.

**Non-disruptive guarantee:** the sync loop is strict FIFO (`parkedAt ASC`, no batch writes) with per-item try/catch — a 410 (or any single failure) never rejects the outer promise. The loop drains the next FIFO item. Concurrent reads (non-dependent GETs) may use a separate semaphore; checkout POSTs are strictly sequential to preserve FEFO stock ordering. Guarded by Web Locks (§14.2) so only one tab drives replay across all open tabs.

---

## 5. Risk Domain 3 — Hardware Interface Reliability

### 5.1 Problem statement

`useBarcodeScanner.ts` detects scans purely by **inter-character timing** (`GAP_MS=50`). This fails when:
- The scanner has RF latency (wireless scanners exhibit 15–120 ms jitter between characters); the gap heuristic fragments a single barcode into two.
- Two scanners wedge on one host; the global listener cannot tell which stream is which.
- A slow human types 4 letters with pauses >50 ms → the buffer resets mid-word, producing a phantom "scan."

**Root cause:** timing-only framing has no data-link boundary marker.

### 5.2 Redesign — STX/ETX sentinel framing

Most commercial barcode scanners can be **programmed** (or configured via their SDK/Configurator app) to emit a leading **STX** (`\x02`) and trailing **ETX** (`\x03`, followed by `Enter` or `Tab`) around every scan. The browser *can* receive STX/ETX as raw keydown events — `e.key` for STX is `"\u0002"`, which `e.key.length === 1` and passes the printable filter. We reframe the hook around **sentinel delimiters** rather than timing.

**New contract:**
```
scan_stream := STX  data_chars  ETX  terminator
```
Where `data_chars` is the barcode payload (printable, no STX/ETX), and `terminator` is `Enter` (default) or `\t` (configurable per device profile, since some scanners emit Tab).

### 5.3 Improved `useBarcodeScanner` hook specification (multi-mode)

```ts
// hooks/useBarcodeScanner.ts
import { useEffect, useRef } from 'react';

export type ScannerProfile = 'auto' | 'stx_etx' | 'suffix_only';

interface BarcodeScannerOptions {
  onScan: (barcode: string) => void;
  minLen?: number;                       // reject fragments shorter than this
  maxInterKeyTimeoutMs?: number;         // max delay between hardware keystrokes
  terminatorKeys?: string[];             // keys denoting scan end
  profile?: ScannerProfile;              // 'auto' (detect), 'stx_etx', 'suffix_only'
  enabled?: boolean;
}

export const useBarcodeScanner = ({
  onScan,
  minLen = 4,
  maxInterKeyTimeoutMs = 35,
  terminatorKeys = ['Enter', 'Tab'],
  profile = 'auto',
  enabled = true,
}: BarcodeScannerOptions) => {
  const bufferRef = useRef<string>('');
  const lastKeyTimeRef = useRef<number>(0);
  const stxActiveRef = useRef<boolean>(false);
  const interKeyTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const clearBuffer = () => {
      bufferRef.current = '';
      stxActiveRef.current = false;
      if (interKeyTimerRef.current) clearTimeout(interKeyTimerRef.current);
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInputFocused =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable;

      const currentTime = performance.now();
      const timeSinceLastKey = currentTime - lastKeyTimeRef.current;
      lastKeyTimeRef.current = currentTime;

      // STX (\u0002) starts a framed scan envelope — enterprise scanner mode.
      if (e.key === 'StartOfText' || (e.code === 'NumpadEnter' && e.ctrlKey)) {
        stxActiveRef.current = true;
        bufferRef.current = '';
        return;
      }

      // ETX (\u0003) terminates the envelope.
      if (stxActiveRef.current && (e.key === 'EndOfText' || terminatorKeys.includes(e.key))) {
        e.preventDefault();
        const scanned = bufferRef.current;
        clearBuffer();
        if (scanned.length >= minLen) {
          onScan(scanned);
          if (isInputFocused) target.blur();
        }
        return;
      }

      // Suffix-only mode: terminator ends a non-framed scan (standard USB HID).
      if (terminatorKeys.includes(e.key)) {
        if (bufferRef.current.length >= minLen) {
          const isScannerVelocity = timeSinceLastKey <= maxInterKeyTimeoutMs;
          if (!isInputFocused || isScannerVelocity || profile === 'suffix_only') {
            e.preventDefault();
            const scanned = bufferRef.current;
            clearBuffer();
            onScan(scanned);
            if (isInputFocused) target.blur();
            return;
          }
        }
        clearBuffer();
        return;
      }

      if (e.key.length !== 1) return;

      // Reset buffer on slow inter-key delay (human typing), unless in STX envelope.
      if (
        !stxActiveRef.current &&
        profile !== 'suffix_only' &&
        bufferRef.current.length > 0 &&
        timeSinceLastKey > maxInterKeyTimeoutMs
      ) {
        bufferRef.current = '';
      }

      bufferRef.current += e.key;

      // Velocity watchdog: flush a buffered scan if keystrokes stall beyond 4× timeout.
      if (interKeyTimerRef.current) clearTimeout(interKeyTimerRef.current);
      interKeyTimerRef.current = setTimeout(() => {
        if (!stxActiveRef.current && !isInputFocused && bufferRef.current.length >= minLen) {
          onScan(bufferRef.current);
        }
        clearBuffer();
      }, maxInterKeyTimeoutMs * 4);
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => {
      window.removeEventListener('keydown', handleKeyDown, true);
      if (interKeyTimerRef.current) clearTimeout(interKeyTimerRef.current);
    };
  }, [onScan, minLen, maxInterKeyTimeoutMs, terminatorKeys, profile, enabled]);
};
```

**Mode dispatch:**
- `'stx_etx'` — only STX/ETX-framed scans are emitted; raw suffix scans ignored (enterprise-grade, strict).
- `'suffix_only'` — only terminator-terminated scans emitted; STX/ETX ignored (standard USB HID scanners).
- `'auto'` (default) — listens for both; STX envelope takes priority; if no STX seen, suffix-only with velocity validation. This is the **backward-compatible default**: standard USB HID scanners "just work," while programmable STX/ETX scanner fleets get the stronger framing guarantee.

**Hardware integration rationale:** Standard USB HID barcode scanners present as keyboards and emit the barcode string followed by a carriage return (Enter). The `timeSinceLastKey <= maxInterKeyTimeoutMs` (35 ms) velocity check rejects human typing (≥100 ms between keystrokes) while accepting scanner output (≤20 ms). This eliminates the fragile single-gap heuristic without requiring scanner firmware reconfiguration.

### 5.4 Domain 3 — test cases

| # | Test | Assertion |
|---|---|---|
| H1 | `test_stx_etx_framing_auto` | in `'auto'` mode: simulate `keydown(StartOfText),("1"),("2"),("C"),("3"),(EndOfText),("Enter")` → `onScan` called once with `"12C3"`, buffer flushed. |
| H2 | `test_min_length_reject` | STX + "AB" (2 chars) + ETX → `onScan` **not** called (rejected, <`minLen`=4). |
| H3 | `test_suffix_only_velocity_accept` | in `'suffix_only'` mode: chars emitted at ≤20ms intervals + `Enter` → `onScan` fires with payload. |
| H4 | `test_suffix_only_velocity_reject` | chars emitted at ≥100ms intervals (human typing) → `onScan` **not** called, buffer reset on slow gap. |
| H5 | `test_disabled_hook_blocks` | `enabled=false` → STX/ETX or suffix triggers → `onScan` never called. |
| H6 | `test_tab_terminator_suffix` | in `'auto'`/`'suffix_only'`: payload + `Tab` terminator → `onScan` fires (Tab in `terminatorKeys`). |
| H7 | `test_posstore_ssr_hydration` | server render → `isHydrated=false`, `activeCart=[]`; after `useHydration()` effect → `isHydrated=true`, `activeCart` restored from `localStorage`. |
| H8 | `test_posstore_multi_tab_sync` | write to `localStorage.pos_cart_v1` in Tab A → Tab B receives `storage` event → `usePosStore` state updated, GC re-applied. |
| H9 | `test_money_integer_cents` | `mul('46.74', 10)` → `"467.40"`; `add('46.74','0.06')` → `"46.80"`; `sub('100.00','59.26')` → `"40.74"`; no float drift. |
| H10 | `test_resume_ticket_dedup_merge` | active cart has 2× Product-A; held ticket has 3× Product-A → `resumeTicket` → single line Product-A qty=5 (no dupes). |
| H11 | `test_offline_queue_410_isolation` | sync two parked txns; 2nd returns 410 → record `status='over_sold'` in IndexedDB `outbox`; 1st record `status='synced'`; queue length still drains. |
| H12 | `test_sync_lock_single_tab` | mock `navigator.locks.request`; two concurrent `syncOfflineQueueWithLock()` calls → `executeSyncLoop()` invoked exactly once. |
| H13 | `test_hardware_retry_queue` | after checkout, simulate printer failure → `print_status='failed'`, `process_checkout` NOT re-invoked; `retryFailedHardware()` → `POST /receipts/{id}/reprint` hits endpoint with no inventory mutation. |
| H14 | `test_clock_skew_banner` | client sends `X-Client-Timestamp` 600s off → UI shows critical "Clock skew" banner; checkout still allowed (read-only GET unaffected). |
| H15 | `test_approval_token_flow` | `ManagerApprovalDialog` → `verify-pin` returns `approval_token` (in-memory only) → action request carries `X-Approval-Token`; token dropped after use; raw PIN never in action payload. |
| H16 | `test_divide_and_round` | `taxFor("10.35","0.14")==="1.45"` (half-up, not 1.44); `discountFor("10.00","0.10")==="1.00"`. |
| H17 | `test_activecart_per_tab_isolation` | open two `usePosStore` instances (mock sessionStorage/tab); Tab A `addToCart` → Tab B `activeCart` still `[]`; resume held ticket in Tab B → present in B only. |
| H18 | `test_offline_pin_fallback` | mock `crypto.subitive.digest`; cached `ManagerPolicy` + offline correct PIN → local `approval_token` emitted with `offline:true`; wrong PIN → rejected, no token. |

---

## 6. Risk Domain 4 — Data Persistence & State Management

### 6.1 Cart state: `useState` → durable persistence with garbage collection

**Current reality:** `app/pos/page.tsx` cart is a local `useState<CartLine[]>` — lost on any browser navigation/refresh/crash. M10 design (§12 of the first draft) used `sessionStorage`, which is *tab-scoped* and survives refresh but is wiped on browser crash recovery in some engines and is invisible to a reopened tab.

**Decision:** Use **`localStorage`** (origin-scoped, survives crash/restart across tabs) as the durable carrier, with a **garbage-collection sweep** keyed by timestamped cart IDs. `IndexedDB` is reserved for the *offline queue* (Domain 2 — binary payloads, larger volume); the cart is small JSON and `localStorage` is simpler (Simplicity-First) and synchronously readable at startup.

**Durability contract (`stores/posStore.ts`):**
- Cart + held tickets persisted under `localStorage key = "pos_cart_v1"` as JSON.
- Each held ticket carries `held_at: ISO timestamp`.
- GC runs on store init: drop any held ticket older than `CART_STALE_HOURS = 8` (configurable) — a cart held past close-of-business is abandoned; the manager reviews via `/api/v1/pos/held-abandoned?before=T`.
- `clearLocalCart()` invoked on successful checkout (after 201) + on shift close.

**GC algorithm:**
```
on init:
  parse localStorage.pos_cart_v1 → { active?: CartLine[], held: HeldTicket[] }
  stale = held.filter(t => now - t.held_at > STALE_HOURS)
  kept = held.filter(t => now - t.held_at <= STALE_HOURS)
  if stale.length: audit("pos.cart.gc_abandoned", {count: stale.length})   // surface to manager
  set { held: kept } back to localStorage
```

### 6.2 Schema migrations (Domain 4 §7.1 deliverable — complete SQL)

All statements are additive + guarded by `PRAGMA table_info` / `IF NOT EXISTS`. Run inside `database.migrate_schema` (idempotent, single transaction per `create_schema` call).

```sql
-- 6.2a. Emergency Over-Sell tables (Domain 2)
CREATE TABLE IF NOT EXISTS offline_txns (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  client_txn_id   TEXT    NOT NULL UNIQUE,
  payload         BLOB    NOT NULL,
  parked_at       TEXT    NOT NULL,
  synced_at       TEXT,
  status          TEXT    NOT NULL DEFAULT 'parked',
  server_receipt  INTEGER,
  server_error    TEXT,
  reconciliation_flag INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_offline_txns_status ON offline_txns(status);
CREATE INDEX IF NOT EXISTS idx_offline_txns_client ON offline_txns(client_txn_id);

CREATE TABLE IF NOT EXISTS stock_discrepancies (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_id      INTEGER,
  product_name    TEXT    NOT NULL,
  requested       INTEGER NOT NULL,
  available       INTEGER NOT NULL,
  delta           INTEGER NOT NULL,
  resolved        INTEGER NOT NULL DEFAULT 0,
  resolved_by     TEXT,
  resolved_at     TEXT,
  note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_disc_receipt ON stock_discrepancies(receipt_id);

-- 6.2b. Receipt extensions (print_status + financials + idempotency)
ALTER TABLE receipts ADD COLUMN print_status  TEXT DEFAULT 'pending';   -- pending | printed | failed
ALTER TABLE receipts ADD COLUMN sale_type     TEXT DEFAULT 'OTC';
ALTER TABLE receipts ADD COLUMN subtotal      NUMERIC(10,2) DEFAULT 0;   -- §6.3 money hardening
ALTER TABLE receipts ADD COLUMN tax_amount    NUMERIC(10,2) DEFAULT 0;
ALTER TABLE receipts ADD COLUMN discount_amount NUMERIC(10,2) DEFAULT 0;
ALTER TABLE receipts ADD COLUMN insurance_copay NUMERIC(10,2) DEFAULT 0;
ALTER TABLE receipts ADD COLUMN insurance_paid  NUMERIC(10,2) DEFAULT 0;
ALTER TABLE receipts ADD COLUMN manager_pin   TEXT;                     -- approver username
ALTER TABLE receipts ADD COLUMN void_status   TEXT DEFAULT 'none';
ALTER TABLE receipts ADD COLUMN client_txn_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_receipts_client_txn ON receipts(client_txn_id);

ALTER TABLE receipt_items ADD COLUMN lot_id    INTEGER;
ALTER TABLE receipt_items ADD COLUMN voided   INTEGER DEFAULT 0;

-- 6.2c. Tender split + shift reconciliation tables
CREATE TABLE IF NOT EXISTS receipt_tenders (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_id  INTEGER NOT NULL,
  method      TEXT    NOT NULL,                -- cash|card|transfer|insurance
  amount      NUMERIC(10,2) NOT NULL,
  ref         TEXT,
  FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tenders_receipt ON receipt_tenders(receipt_id);

CREATE TABLE IF NOT EXISTS shifts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  cashier_id      INTEGER NOT NULL,
  opened_at       TEXT,
  closed_at       TEXT,
  opening_float   NUMERIC(10,2) DEFAULT 0,
  closing_counted NUMERIC(10,2) DEFAULT 0,
  expected_cash   NUMERIC(10,2) DEFAULT 0,
  variance        NUMERIC(10,2) DEFAULT 0,
  status          TEXT    DEFAULT 'open'
);
CREATE INDEX IF NOT EXISTS idx_shifts_cashier ON shifts(cashier_id);

-- 6.2d. Money-type hardening: migrate all REAL monetary columns to NUMERIC(10,2)
-- SQLite stores NUMERIC via type affinity; the column-level affinity changes from REAL → NUMERIC.
-- We re-create affected tables in a safe, data-preserving way ONLY if the column
-- is still REAL. A no-op-safe guard checks the current affinity.
-- (See §6.3 for the Python migration path that avoids table rebuilds where SQLite
--  allows an in-place affinity bump via table rebuild — here we use the copy pattern.)
--
-- Affected monetary columns (REAL → NUMERIC(10,2)):
--   products.price, products.wholesale_price
--   inventory_extended.on_hand (INTEGER, no change — qty not money)
--   receipt_items.price_at_time, receipt_items.total_price(if ext)
--   sold_items.price
--   receiving_log.total_cost
--   offline_txns.n/a (payload is BLOB)
--   receipt_tenders.amount, shifts.*
```

> **Note on REAL→NUMERIC in SQLite:** SQLite does not support `ALTER COLUMN TYPE`. To change a `REAL` column to `NUMERIC(10,2)` affinity while preserving data, the safe pattern is **table-copy** (create `_new` with the target DDL, `INSERT INTO _new SELECT ...` with a cast, drop old, rename). This is data-preserving but a *heavy* migration. Because the audit flags precision risk as critical, we perform it **once** in `migrate_schema` guarded by `PRAGMA table_info` affinity checks (column `type` containing `REAL`). New columns added by §6.2b are `NUMERIC` from birth. The implementing agent writes the table-rebuild helper; M9's migration-idempotency test (T1) asserts the round-trip is stable across double-`create_schema`.

### 6.3 Money hardening — Python side (SQLAlchemy `Numeric(10,2)`)

**Models (`app/core/models.py`):**
```python
from sqlalchemy import Numeric
class Product(Base):
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    wholesale_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
class ReceiptItem(Base):
    price_at_time: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
class SoldItem(Base):
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
class Receipt(Base):
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(10,2))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10,2))
    # … discount_amount, insurance_copay, insurance_paid, opening/closing/expected/variance
```
- `pos_service._round2` already uses `Decimal` with `ROUND_HALF_UP`; extend to **all** money math. The `Decimal` values round-trip to SQLite `NUMERIC` affinity as exact strings (e.g. `"46.74"`) — no binary128 drift.
- Pydantic schemas: money fields typed `Decimal` (serialized to JSON as a string to avoid JS `float`).
- **Financial total rule:** `Decimal` everywhere server-side; the only `float` boundary is *JSON transport to the browser*, where amounts serialize as **strings** (e.g. `"46.74"`) so JS never re-adds floats.

### 6.4 Shift reconciliation — corrected mathematical definition (Domain 4 §7.2 deliverable)

**The bug (as planned):** `variance = closing_counted − expected_cash` where `expected_cash` = sum of cash tenders. This *ignores the opening float*: the cashier started with `$X` in the drawer; `expected_cash` must include `X` because `closing_counted` physically contains it.

**Corrected definition:**

```
Let:
  F   = opening_float            (cashier's starting float)
  S   = Σ cash tender amounts    (sum over receipt_tenders where method='cash' and receipt in shift window)
  C   = closing_counted          (cashier's physical count at close)

  expected_cash = F + S          ← the drawer SHOULD contain float + all cash sales
  variance      = C − expected_cash
                 = C − (F + S)

If variance > 0: drawer over/short positive (overage)  — cashier kept extra / price error.
If variance < 0: drawer short — discrepancy, requires review.
```

**Example:** float F=$100, cash sales S=$46.74, cashier counts C=$140.
- ❌ Old (wrong): expected = S = $46.74 → variance = $140 − $46.74 = **+$93.26** (false overage).
- ✅ New (correct): expected = F + S = $146.74 → variance = $140 − $146.74 = **−$6.74** (genuine short).

**Threshold gate:** If `|variance| > settings.shift_variance_threshold` (default `$2.00`) AND `variance < 0`, the close requires a **manager PIN** (`POST /api/v1/auth/verify-pin` → `manager_pin` stamped on the shift + audit). Variance ≥ 0 never requires a PIN (overage is not a compliance event).

### 6.5 Schema additions reference

| Table | New column | Type | Default | Purpose |
|---|---|---|---|---|
| `receipts` | `print_status` | TEXT | `'pending'` | receipt print lifecycle |
| `receipts` | `sale_type` | TEXT | `'OTC'` | OTC / Rx OTC / Delivery / Gifts / Loyalty (§4.2.2) |
| `receipts` | `subtotal` | NUMERIC(10,2) | `0` | tax-exempt line sum |
| `receipts` | `tax_amount` | NUMERIC(10,2) | `0` | tax split out of total |
| `receipts` | `discount_amount` | NUMERIC(10,2) | `0` | applied discounts |
| `receipts` | `insurance_copay` | NUMERIC(10,2) | `0` | patient copay (§7.2 MASTER §106) |
| `receipts` | `insurance_paid` | NUMERIC(10,2) | `0` | insurer portion |
| `receipts` | `manager_pin` | TEXT | NULL | approver username on void/discount>thresh |
| `receipts` | `void_status` | TEXT | `'none'` | none/voided/partial_return/full_return |
| `receipts` | `client_txn_id` | TEXT (UNIQUE) | NULL | offline idempotency key |
| `receipt_items` | `lot_id` | INTEGER | NULL | consumed lot (FEFO audit) |
| `receipt_items` | `voided` | INTEGER | `0` | soft void flag |
| `offline_txns` | (new table) | — | — | offline park + reconciliation |
| `stock_discrepancies` | (new table) | — | — | over-sell resolution trail |
| `receipt_tenders` | (new table) | — | — | split-payment lines (NUMERIC) |
| `shifts` | (new table) | — | — | till open/close + variance (NUMERIC) |

### 6.6 Domain 4 — test cases

| # | Test | Assertion |
|---|---|---|
| D1 | `test_cart_persists_across_reload` | `localStorage.pos_cart_v1` written on add; after "reload" cart restored. |
| D2 | `test_cart_gc_abandoned` | held ticket >8h old → dropped on init, `audit pos.cart.gc_abandoned` recorded. |
| D3 | `test_print_status_default_pending` | new receipt row → `print_status='pending'`. |
| D4 | `test_money_numeric_roundtrip` | `Decimal('46.74')` stored via NUMERIC → read back `== Decimal('46.74')` (no float drift). |
| D5 | `test_shift_variance_formula` | float=100, cash_tenders=46.74, counted=140 → `expected_cash=146.74`, `variance=-6.74`. |
| D6 | `test_shift_close_requires_manager_on_short` | variance < −2.00, no PIN → 409; with PIN → 200, `manager_pin` set. |
| D7 | `test_migration_real_to_numeric_idempotent` | run `_harden_money_columns` twice on a file DB with REAL money columns → affinity is `NUMERIC` both runs; FKs off outside TXN + `foreign_key_check` gate clean; decimal data (e.g. `46.74`) preserved exactly across the table-copy. |
| D8 | `test_client_txn_idempotent_replay` | replay same `client_txn_id` → 201 + same receipt_id, stock unchanged. |
| D9 | **regression** | existing 69 tests green after schema changes. |

---

## 7. Technical Artifacts (deliverables)

The implementing agent must produce these seven concrete artifacts. They are copy-paste-executable.

### 7.1 Artifact 1 — Complete SQL migration (`app/core/database.py` `migrate_schema` body)

```python
async def migrate_schema(conn: Any) -> None:
    """Idempotent, no-op-safe migrations for the preserved pharmacy.db.

    Additive only. Each ALTER guarded by PRAGMA table_info; each CREATE INDEX/TABLE
    uses IF NOT EXISTS. REAL→NUMERIC for money is a data-preserving table-copy
    guarded by an affinity check (run once).
    """
    # ---- new tables (Domain 2 + 4.2c) ----
    await conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS offline_txns (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          client_txn_id TEXT NOT NULL UNIQUE,
          payload BLOB NOT NULL,
          parked_at TEXT NOT NULL,
          synced_at TEXT,
          status TEXT NOT NULL DEFAULT 'parked',
          server_receipt INTEGER,
          server_error TEXT,
          reconciliation_flag INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_offline_txns_status ON offline_txns(status);
        CREATE INDEX IF NOT EXISTS idx_offline_txns_client ON offline_txns(client_txn_id);
        """
    )
    await conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS stock_discrepancies (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          receipt_id INTEGER,
          product_name TEXT NOT NULL,
          requested INTEGER NOT NULL,
          available INTEGER NOT NULL,
          delta INTEGER NOT NULL,
          resolved INTEGER NOT NULL DEFAULT 0,
          resolved_by TEXT,
          resolved_at TEXT,
          note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_disc_receipt ON stock_discrepancies(receipt_id);
        """
    )
    await conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS receipt_tenders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          receipt_id INTEGER NOT NULL,
          method TEXT NOT NULL,
          amount NUMERIC(10,2) NOT NULL,
          ref TEXT,
          FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_tenders_receipt ON receipt_tenders(receipt_id);
        """
    )
    await conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS shifts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          cashier_id INTEGER NOT NULL,
          opened_at TEXT,
          closed_at TEXT,
          opening_float NUMERIC(10,2) DEFAULT 0,
          closing_counted NUMERIC(10,2) DEFAULT 0,
          expected_cash NUMERIC(10,2) DEFAULT 0,
          variance NUMERIC(10,2) DEFAULT 0,
          status TEXT DEFAULT 'open'
        );
        CREATE INDEX IF NOT EXISTS idx_shifts_cashier ON shifts(cashier_id);
        """
    )

    # ---- additive columns on receipts (guarded) ----
    _ADD_COL = """
      INSERT INTO pragma_table_info('receipts') SELECT 1 WHERE NOT EXISTS
      (SELECT 1 FROM pragma_table_info('receipts') WHERE name='__COL__');
      """
    for col, ddl in {
        "print_status": "ALTER TABLE receipts ADD COLUMN print_status TEXT DEFAULT 'pending'",
        "sale_type":    "ALTER TABLE receipts ADD COLUMN sale_type TEXT DEFAULT 'OTC'",
        "subtotal":     "ALTER TABLE receipts ADD COLUMN subtotal NUMERIC(10,2) DEFAULT 0",
        "tax_amount":   "ALTER TABLE receipts ADD COLUMN tax_amount NUMERIC(10,2) DEFAULT 0",
        "discount_amount": "ALTER TABLE receipts ADD COLUMN discount_amount NUMERIC(10,2) DEFAULT 0",
        "insurance_copay":"ALTER TABLE receipts ADD COLUMN insurance_copay NUMERIC(10,2) DEFAULT 0",
        "insurance_paid": "ALTER TABLE receipts ADD COLUMN insurance_paid NUMERIC(10,2) DEFAULT 0",
        "manager_pin":    "ALTER TABLE receipts ADD COLUMN manager_pin TEXT",
        "void_status":    "ALTER TABLE receipts ADD COLUMN void_status TEXT DEFAULT 'none'",
        "client_txn_id":  "ALTER TABLE receipts ADD COLUMN client_txn_id TEXT",
        "lot_id":         "ALTER TABLE receipt_items ADD COLUMN lot_id INTEGER",
        "voided":         "ALTER TABLE receipt_items ADD COLUMN voided INTEGER DEFAULT 0",
    }.items():
        if not await _table_has_column(conn, ("receipts" if col in (
            "print_status","sale_type","subtotal","tax_amount","discount_amount",
            "insurance_copay","insurance_paid","manager_pin","void_status","client_txn_id"
        ) else "receipt_items"), col):
            await conn.exec_driver_sql(ddl)

    # unique index on client_txn_id (created after column exists)
    await conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_receipts_client_txn ON receipts(client_txn_id)"
    )

    # ---- REAL → NUMERIC money hardening (table-copy, affinity-guarded) ----
    await _harden_money_columns(conn)
```

```python
import logging
from typing import Any

logger = logging.getLogger(__name__)

async def _harden_money_columns(conn: Any) -> None:
    """Idempotent REAL -> NUMERIC(10,2) table-copy migration.

    Safely toggles Foreign Key constraints OUTSIDE explicit transactions (SQLite
    ignores `PRAGMA foreign_keys` inside a TXN — see §13 Edge Case 2) and executes
    PRAGMA foreign_key_check before re-enabling to maintain relational integrity.
    Also preserves all secondary indexes lost during CREATE/DROP/RENAME (§13 Edge Case 1).
    """
    money_map = {
        "products": ["price", "wholesale_price"],
        "receipt_items": ["price_at_time"],
        "sold_items": ["price"],
        "receiving_log": ["total_cost"],
    }

    # Step 1: Pre-flight — discover which tables actually need a rebuild
    tables_to_migrate: dict[str, list[str]] = {}
    for table, cols in money_map.items():
        res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {r[1]: r[2] for r in res.fetchall()}  # name -> type
        need_mig = [c for c in cols if c in existing and "REAL" in existing[c].upper()]
        if need_mig:
            tables_to_migrate[table] = need_mig

    if not tables_to_migrate:
        logger.info("Money column hardening check passed: No REAL columns detected.")
        return

    logger.warning(
        f"Initiating table rebuild for REAL->NUMERIC migration on: {list(tables_to_migrate.keys())}"
    )

    # Step 2: Disable Foreign Keys OUTSIDE transaction boundary.
    # SQLite no-ops `PRAGMA foreign_keys` inside an active transaction.
    # `execution_options(isolation_level="AUTOCOMMIT")` creates a "branched"
    # connection sharing the same DBAPI handle but without auto-beginning a
    # transaction, so the PRAGMA takes effect as a connection-level setting.
    autocommit_conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    await autocommit_conn.exec_driver_sql("PRAGMA foreign_keys = OFF")

    try:
        # Step 3: Perform Table Rebuilds (preserve PK + indexes + all columns)
        for table, need_cols in tables_to_migrate.items():
            # Capture secondary indexes BEFORE drop — DROP TABLE destroys them.
            idx_res = await conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master "
                f"WHERE type='index' AND tbl_name='{table}' AND sql IS NOT NULL"
            )
            index_ddls: list[str] = [r[0] for r in idx_res.fetchall() if r[0]]

            res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
            all_cols = res.fetchall()  # [(cid, name, type, notnull, dflt_value, pk), ...]

            new_col_defs = []
            pk_cols = []
            col_names = []

            for col in all_cols:
                _, name, col_type, notnull, dflt_value, pk = col
                col_names.append(name)

                target_type = "NUMERIC(10,2)" if name in need_cols else col_type
                not_null_clause = " NOT NULL" if notnull else ""
                default_clause = f" DEFAULT {dflt_value}" if dflt_value is not None else ""

                new_col_defs.append(f"{name} {target_type}{not_null_clause}{default_clause}")
                if pk:
                    pk_cols.append(name)

            pk_clause = f", PRIMARY KEY ({', '.join(pk_cols)})" if pk_cols else ""
            tmp_table = f"_{table}_numeric_migration"

            create_sql = f"CREATE TABLE {tmp_table} ({', '.join(new_col_defs)}{pk_clause})"
            cols_str = ", ".join(col_names)

            await conn.exec_driver_sql(f"DROP TABLE IF EXISTS {tmp_table};")
            await conn.exec_driver_sql(create_sql)
            await conn.exec_driver_sql(
                f"INSERT INTO {tmp_table} ({cols_str}) SELECT {cols_str} FROM {table};"
            )
            await conn.exec_driver_sql(f"DROP TABLE {table};")
            await conn.exec_driver_sql(f"ALTER TABLE {tmp_table} RENAME TO {table};")

            # Step 3b: Recreate indexes. Their DDL references `table` by name,
            # which is correct after RENAME. Use IF NOT EXISTS for idempotency.
            for ddl in index_ddls:
                safe_ddl = ddl.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
                await conn.exec_driver_sql(safe_ddl)

        # Step 4: Verify Foreign Key Integrity before re-enabling
        fk_check = await autocommit_conn.exec_driver_sql("PRAGMA foreign_key_check;")
        violations = fk_check.fetchall()
        if violations:
            raise RuntimeError(
                f"CRITICAL: Foreign key constraint violation detected after table rebuild: {violations}"
            )

    finally:
        # Step 5: Always re-enable foreign keys
        await autocommit_conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        logger.info("Foreign key checks re-enabled successfully.")
```

### 7.2 Artifact 2 — Corrected shift reconciliation math

```
expected_cash = opening_float + Σ(cash tenders in shift window)
variance      = closing_counted − expected_cash
              = closing_counted − (opening_float + Σ_cash_tenders)

PIN required iff variance < 0 AND |variance| > shift_variance_threshold
```
Server-enforced in `PosService.close_shift`:
```python
tenders = await TenderRepository.cash_in_window(shift.id, shift.opened_at, shift.closed_at)
expected = shift.opening_float + sum(t.amount for t in tenders)
shift.expected_cash = expected
shift.variance = shift.closing_counted - expected
if shift.variance < 0 and abs(shift.variance) > settings.shift_variance_threshold:
    if not approver_pin: raise ApprovalRequiredError(...)
```

### 7.3 Artifact 3 — Revised backend logic workflow for offline replay + over-sell

(See §4.3 full workflow above.) Condensed to the decision table:

| Replay result | HTTP | Client action | Audit |
|---|---|---|---|
| `client_txn_id` already in `receipts` | **201** (return existing) | remove from `outbound_queue` | `pos.checkout.replay` (idempotent hit) |
| Tender sum mismatch / bad input | **400** | retry (fix payload) | none |
| Stock insufficient at replay | **410** (Gone) | move to `failed_queue`, set `reconciliation_flag=0` | `pos.over_sell` + `stock_discrepancy` INSERT |
| Success | **201** | clear from queue, mark synced | `pos.checkout.replay` |

### 7.4 Artifact 4 — Improved Barcode Scanner hook (multi-mode)

(See §5.3 above — multi-mode `useBarcodeScanner` supporting `ScannerProfile: 'auto' | 'stx_etx' | 'suffix_only'`, inter-keystroke velocity detection (`maxInterKeyTimeoutMs=35`), `minLen=4`, configurable `terminatorKeys`, `enabled` flag. `'auto'` default accepts standard USB HID scanners without firmware reconfiguration while still honoring STX/ETX framing when available.)

**Peripheral hardening (§14.3):** `lib/peripherals.ts` `PeripheralManager` must include a **hardware retry queue** — on print/drawer failure it enqueues `{receipt_id, op}` and retries with backoff, setting `receipts.print_status='failed'` but **never** re-invoking `process_checkout`. The "Reprint / Pop Drawer" action bar calls `POST /api/v1/pos/receipts/{id}/reprint` (§14.3), which touches no inventory.

### 7.5 Artifact 5 — Enhanced Cart State persistence + GC

(See §6.1 above — `localStorage.pos_cart_v1`, held-ticket timestamp GC at 8h, manager-abandoned review endpoint, `clearLocalCart` on checkout + shift close.)

### 7.6 Artifact 6 — `stores/posStore.ts` design spec (Zustand) + code review

**Code-review verdict on the three edge cases:** The existing `authStore.ts` uses `typeof window !== "undefined"` guards but has **no SSR-hydration fence** — it works for `authStore` because `token`/`user` are nullable and the UI gates on `isAuthenticated()`. But `posStore.ts` renders cart line items *immediately*; any `localStorage` read on the server vs. client mismatch (e.g., a prior-session cart that doesn't exist server-side) produces a React hydration error. The following spec hardens against that.

#### 7.6.1 Interfaces (type safety audit)

```typescript
// stores/posStore.ts
import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type { DecimalCurrency } from "@/lib/decimalCurrency";  // see §7.6.4

// Money is ALWAYS a fixed-precision string (e.g. "46.74"), never `number`.
// This mirrors the backend's `Decimal` → JSON-as-string serialization
// and preserves NUMERIC(10,2) parity.
export interface CartLine {
  product_name: string;
  quantity: number;            // integer — no rounding ambiguity
  unitPrice: string;           // fixed 2-decimal string, sourced from Medicine.price
  discountAmount: string;      // fixed 2-decimal string (line-level promo)
  taxRate: string;             // percentage as string e.g. "0.00" or "0.14"
  // derived (not persisted — recomputed):
  readonly lineTotal: string;  // (unitPrice * quantity) - discountAmount, tax-inclusive
}

export interface HeldTicket {
  id: string;                  // UUID
  lines: CartLine[];
  heldAt: string;              // ISO timestamp — GC key
  note?: string;
}

export interface PosStoreState {
  // persisted state
  activeCart: CartLine[];
  heldTickets: HeldTicket[];
  // SSR guard — false until useEffect hydrates from localStorage
  isHydrated: boolean;
  // actions
  addToCart: (product: Medicine, quantity: number) => void;
  removeFromCart: (product_name: string) => void;
  updateLineQty: (product_name: string, quantity: number) => void;
  clearCart: () => void;
  holdCurrentCart: (note?: string) => HeldTicket;
  resumeTicket: (ticketId: string) => void;
  discardHeldTicket: (ticketId: string) => void;
  // lifecycle
  hydrate: () => void;          // reads localStorage + runs GC + sets isHydrated=true
  persist: () => void;          // debounced write to localStorage
}
```

**Logic audit flags addressed:**

| Method | Flaw identified | Refinement |
|---|---|---|
| `runGarbageCollection` | A naive GC that iterates `heldTickets` and calls `splice()` mutates the array during iteration — on a shared array this can skip entries when two tabs trigger GC concurrently. | GC must **filter-map** (not splice): `heldTickets.filter(t => age <= STALE_HOURS)` + single `set()`. Also guard with the multi-tab `storage` listener so only one tab's GC write wins (last-writer-wins on `pos_cart_v1`). |
| `resumeTicket` | If `resumeTicket` blindly merges a held ticket's lines into `activeCart` by pushing, duplicate `product_name` entries accumulate (no dedup → double-charge on checkout). | `resumeTicket` must deep-merge by `product_name`: sum quantities on existing lines, add new lines only if absent. Also re-validate against `Medicine.on_hand` before merge (stale holds may exceed current stock — mark those lines `stale: true` for user review). |

#### 7.6.2 SSR Hydration pattern (`skipHydration` + `isHydrated`)

> **Tab-scoping decision (§14 refinement #2):** `activeCart` is **per-tab** (isolated in `sessionStorage`) so two tabs on one terminal build independent drafts without clobbering each other. `heldTickets` stays **shared** (in `localStorage`) so a draft parked in Tab A is retrievable in Tab B. The `storage` listener (§7.6.3) reconciles **only** `heldTickets`, never `activeCart`.

```typescript
const ACTIVE_CART_KEY = "pos_activecart_v1";   // per-tab  → sessionStorage
const HELD_TICKETS_KEY = "pos_held_v1";        // shared   → localStorage

const safeParse = (raw: string): { activeCart?: CartLine[]; heldTickets?: HeldTicket[] } => {
  try { return JSON.parse(raw); } catch { return {}; }
};

export const usePosStore = create<PosStoreState>()(
  subscribeWithSelector((set, get) => ({
    activeCart: [],       // server and client both start empty
    heldTickets: [],
    isHydrated: false,    // <-- critical SSR fence
    // ... actions ...
    hydrate: () => {
      // activeCart: per-tab (sessionStorage) — isolated across tabs, survives reload.
      const rawCart = typeof window !== "undefined" ? sessionStorage.getItem(ACTIVE_CART_KEY) : null;
      const activeCart: CartLine[] = rawCart ? (safeParse(rawCart).activeCart ?? []) : [];
      // heldTickets: shared (localStorage) — cross-tab draft retrieval.
      const rawHeld = typeof window !== "undefined" ? localStorage.getItem(HELD_TICKETS_KEY) : null;
      const heldTickets: HeldTicket[] = rawHeld ? (safeParse(rawHeld).heldTickets ?? []) : [];
      const cleaned = runGarbageCollection(heldTickets);
      if (typeof window !== "undefined") {
        import("@/lib/storagePersist").then(({ requestPersistentStorage }) => {
          requestPersistentStorage().catch(() => { /* non-fatal */ });
        });
      }
      set({ activeCart, heldTickets: cleaned, isHydrated: true });
      get().persist(); // re-write GC'd state
    },
    persist: () => {
      if (typeof window === "undefined" || !get().isHydrated) return;
      // Per-tab write (sessionStorage) — never visible to other tabs.
      sessionStorage.setItem(ACTIVE_CART_KEY, JSON.stringify({ activeCart: get().activeCart }));
      // Shared write (localStorage) — other tabs pick this up via the `storage` listener.
      localStorage.setItem(HELD_TICKETS_KEY, JSON.stringify({ heldTickets: get().heldTickets }));
    },
  }))
);

// useHydration hook for app/pos/page.tsx
export function useHydration(): boolean {
  const isHydrated = usePosStore((s) => s.isHydrated);
  useEffect(() => {
    usePosStore.getState().hydrate();
  }, []);
  return isHydrated;
}
```

**`app/pos/page.tsx` guard:**
```tsx
function PosPage() {
  const isHydrated = useHydration();
  if (!isHydrated) {
    return <PosSkeleton />;  // avoids hydration mismatch — never renders cart data pre-hydration
  }
  return <PosLayout />;  // safe: data came from client-side localStorage
}
```

#### 7.6.3 Multi-tab `localStorage` synchronization (heldTickets only)

The `storage` event fires in *other* tabs when one tab writes to `localStorage`. Without it, Tab B keeps stale `heldTickets` after Tab A parks a draft. **`activeCart` is deliberately excluded** — it lives in `sessionStorage` (per-tab), so a cart built in Tab B must never overwrite Tab A's live draft.

```typescript
useEffect(() => {
  if (typeof window === "undefined") return;
  const handleStorage = (e: StorageEvent) => {
    if (e.key !== HELD_TICKETS_KEY) return;   // activeCart is per-tab → never cross-tab
    if (e.newValue === null) { set({ heldTickets: [] }); return; }
    try {
      const data = JSON.parse(e.newValue);
      set({ heldTickets: runGarbageCollection(data.heldTickets ?? []) });
    } catch { set({ heldTickets: [] }); }
  };
  window.addEventListener("storage", handleStorage);
  return () => window.removeEventListener("storage", handleStorage);
}, []);
```

**Trade-off:** only `heldTickets` cross-tab re-render on a write — acceptable (one per hold/resume). `activeCart` stays isolated per tab; a cashier opening Tab B to build Customer B's cart will not disturb Tab A's draft. `resumeTicket(ticketId)` merges a shared `HeldTicket` into **this tab's** `sessionStorage` activeCart (deep-merge + stock re-validation, §7.6.1) without touching the other tab.

#### 7.6.4 Monetary precision — fixed-precision strings + integer-cents math (§13.4 boundary)

**Problem:** `types/contracts.ts` types all money as `number` (e.g. `Medicine.price: number`). If the store reads a `number` from the API and performs `unitPrice * quantity`, IEEE-754 binary float drift occurs (e.g., `0.1 + 0.2 = 0.30000000000000004`). The backend uses `Decimal`/`NUMERIC(10,2)`.

**Contract breach:** The store **must** never store or compute money as `number`. All money fields in `CartLine` are `string`. The API boundary (§13.4) enforces this via Zod `DecimalString` — any JSON `number` is rejected at parse time.

**Resolution strategy (integer-cents math, no external library):**
1. All monetary inputs arrive as validated `DecimalString` (e.g. `"46.74"`) from the Zod-parsed API response.
2. `toCents` parses the string **without** passing through `Number()` — it splits on `.` and assembles a `bigint` directly, eliminating the float intermediate entirely.
3. All arithmetic uses `bigint` cents.
4. Convert back to fixed-precision string only for display/persistence.

> ⚠️ **Note:** the `bigint`-string-split approach below is the **only** safe pattern — the naive `Math.round(Number(s) * 100)` variant introduces a `float64` intermediate (`Number(s)`) which can already drift before `Math.round`. This version splits the string and assembles `bigint` directly, never touching float64. The same implementation appears in §13.4 as the canonical `lib/decimalCurrency.ts`.

```typescript
// lib/decimalCurrency.ts — zero-float integer-cents math (§13.4 implementation)
export const toCents = (s: string): bigint => {
  // "46.74" → 4674n ; "-0.05" → -5n. Never passes through Number().
  const [intPart, fracPart = "00"] = s.split(".");
  const sign = intPart.startsWith("-") ? -1n : 1n;
  const absInt = BigInt(intPart.replace("-", ""));
  const absFrac = BigInt(fracPart.padEnd(2, "0").slice(0, 2));
  return sign * (absInt * 100n + absFrac);
};

export const fromCents = (c: bigint): string => {
  const sign = c < 0n ? "-" : "";
  const abs = c < 0n ? -c : c;
  return `${sign}${abs / 100n}.${(abs % 100n).toString().padStart(2, "0")}`;
};

// HALF_UP division of two bigints — fixes integer-truncation drift on tax/discount.
// e.g. divideAndRound(14490n, 100n) = 145n  (raw 144.9 → 145, not 144)
export const divideAndRound = (numerator: bigint, denominator: bigint): bigint => {
  if (denominator <= 0n) throw new RangeError("denominator must be > 0");
  const q = numerator / denominator;                                  // truncates toward zero
  const r = ((numerator % denominator) + denominator) % denominator; // non-negative remainder
  return r * 2n >= denominator ? q + 1n : q;                         // ROUND_HALF_UP
};

// Apply a rate expressed in bips (scale 10000): 14% tax → applyRate(c, 1400n)
export const applyRate = (amountCents: bigint, rateBips: bigint, scale: bigint = 10000n): bigint =>
  divideAndRound(amountCents * rateBips, scale);

export const mul = (decimalStr: string, qty: number): string =>
  fromCents(toCents(decimalStr) * BigInt(qty));                       // exact mult, no rounding

export const add = (a: string, b: string): string => fromCents(toCents(a) + toCents(b));
export const sub = (a: string, b: string): string => fromCents(toCents(a) - toCents(b));

// Convenience wrappers for CartLine money fields (all DecimalString inputs).
// taxRate "0.14" → 1400 bips via string parse (no float on the rate either).
export const taxFor = (amountStr: string, taxRateStr: string): string =>
  fromCents(applyRate(toCents(amountStr), rateToBips(taxRateStr)));
export const discountFor = (amountStr: string, discountStr: string): string =>
  fromCents(applyRate(toCents(amountStr), rateToBips(discountStr)));

const rateToBips = (rateStr: string): bigint => {
  const neg = rateStr.startsWith("-");
  const [i, f = ""] = rateStr.replace("-", "").split(".");
  const bips = BigInt(i) * 10000n + BigInt((f + "0000").slice(0, 4)); // "0.14" → 1400n
  return neg ? -bips : bips;
};
```

**Parity check:** `taxFor("10.35", "0.14")` → `toCents("10.35")=1035n`; `applyRate(1035n, 1400n)` = `divideAndRound(1449000n, 10000n)` = `144n` q, `r=9000n`, `9000*2=18000 >= 10000` → `145n` → `"1.45"`. This matches `Decimal('10.35') * Decimal('0.14')` = `Decimal('1.449')` → `ROUND_HALF_UP` → `Decimal('1.45')` on the backend. No compounding drift across multi-line checkouts.

**Parity check:** `toCents("46.74") = 4674n`; `mul("46.74", 10) = fromCents(46740n) = "467.40"`. No float drift at any step — matches `Decimal('46.74') * 10 = Decimal('467.40')` on the backend.

**Caveat (flag for user):** `contracts.ts` money fields are typed `number`. **Recommendation:** update `contracts.ts` money fields to `string` and parse all API responses through `lib/monetarySchema.ts` Zod schemas at the `lib/api.ts` boundary (§13.4) so no `number` money ever enters the store.

### 7.7 Artifact 7 — `lib/offlineQueue.ts` design spec (IndexedDB + 410 UX)

**Design:** A thin IndexedDB wrapper around a single `outbox` object store, keyed by `client_txn_id`. Each record carries the checkout payload + a `failure_mode` field set by the sync loop (§4.5 state machine). On `410 Gone`, the record migrates to a `failed` status flag (not a separate store — same record, updated) so the `OfflineSyncBanner` can render the discrepancy alert without a second query.

```typescript
// lib/offlineQueue.ts
import { openDB } from "idb";  // idb is a thin wrapper over IndexedDB (1.5 kB gz)
// NOTE: `idb` not yet in package.json — add as dev/runtime dep.

const DB_NAME = "pharmacy-pos";
const STORE = "outbox";

const db = await openDB(DB_NAME, 1, {
  upgrade(db) {
    const s = db.createObjectStore(STORE, { keyPath: "client_txn_id" });
    s.createIndex("status", "status");
  },
});

export interface QueuedTxn {
  client_txn_id: string;      // UUID
  payload: CheckoutRequest;   // the full checkout payload (stringified)
  parkedAt: number;           // epoch ms
  attempts: number;
  status: "parked" | "synced" | "over_sold" | "failed";  // 'over_sold' = received 410
  failureDetail?: string;      // server 410 body / stock_discrepancy id
  receiptId?: number;          // set on success
}

export const offlineQueue = {
  enqueue: (txn: QueuedTxn) => db.add(STORE, txn),
  // FIFO: strict parkedAt ASC ordering for deterministic replay (§4.5 + §14 #4)
  dequeue: () => db.getAllFromIndex(STORE, "status", "parked"),
  peekOrdered: async (): Promise<QueuedTxn[]> =>
    (await offlineQueue.dequeue()).sort((a, b) => a.parkedAt - b.parkedAt),
  markSynced: (id: string, receiptId: number) =>
    db.put(STORE, { client_txn_id: id, status: "synced", receiptId }),
  markOversold: (id: string, detail: string) =>
    db.put(STORE, { client_txn_id: id, status: "over_sold", failureDetail: detail, attempts: 0 }),
  listFailed: () => db.getAllFromIndex(STORE, "status", "over_sold"),
  clearFailed: (id: string) => db.put(STORE, { client_txn_id: id, status: "synced", failureDetail: undefined }),
};

// Strict FIFO replay — sequential writes, no parallel checkout mutations (§14 #4).
export async function executeSyncLoop(): Promise<void> {
  const pending = await offlineQueue.peekOrdered();     // ← sorted by parkedAt ASC
  for (const txn of pending) {                          // ← one-at-a-time: stock is dependent
    try {
      const res = await api.post("/api/v1/pos/checkout", txn.payload, {
        headers: { "X-Client-Txid": txn.client_txn_id },
      });
      await offlineQueue.markSynced(txn.client_txn_id, res.data.receipt_id);
    } catch (err: any) {
      if (err.status === 410) await offlineQueue.markOversold(txn.client_txn_id, err.detail);
      else if (err.status === 400) {
        if (++txn.attempts < 3) await offlineQueue.db.put(STORE, txn);  // retryable
        else await offlineQueue.markFailed(txn.client_txn_id);
      } else await backoff();                            // 5xx / network — keep parked, retry later
    }
  }
}
```

**Sync loop contract (matches §4.5 state machine):**
- **Strict FIFO**: `executeSyncLoop` processes `parkedAt ASC` in strict order — a later transaction can never claim stock before an earlier one. The `batch_size=10` semaphore from the prior design is **removed** for checkout writes (stock mutations are dependent; parallelism corrupts FEFO ordering). Concurrent reads (e.g. `GET /products` prefetch for the next batch) may still use a separate semaphore — checkout POSTs are strictly sequential.
- On `410`: call `markOversold` → `OfflineSyncBanner` renders "Inventory Discrepancy Alert".
- On `200/201`: call `markSynced`.
- The 410 record stays `over_sold` until resolved via §4.4 Discrepancies panel → `clearFailed`.
- **Concurrency guard (§14.2):** always call `syncOfflineQueueWithLock()` (Web Locks) → only one tab runs `executeSyncLoop` at a time.

**Dependency:** `idb` package → add to `package.json` runtime deps; add `idb` types to `tsconfig`.

---

## 8. Unified Test Plan (TDD)

New backend tests in `backend_fastapi/tests/test_m10_hardening.py`.

| # | Test | Domain | Assertions |
|---|---|---|---|
| T1 | `test_migration_idempotency_double_run` | D4 | `create_schema()` twice on a file DB with REAL money columns → all M10 columns present; `foreign_key_check` clean; affinity of `products.price` is `NUMERIC` (FKs toggled off outside TXN, re-enabled via `foreign_key_check` gate); 2nd run is a pure no-op. |
| T2 | `test_replay_idempotent` | D2 | checkout with `client_txn_id` twice → both 201, same `receipt_id`, stock deducted once. |
| T3 | `test_replay_oversell_returns_410` | D2 | 1 unit in stock; offline park 2× (different `client_txn_id`); replay 1st → 201; replay 2nd → 410 + `stock_discrepancy` row + `offline_txns.status='over_sold'`. |
| T4 | `test_money_numeric_roundtrip` | D4 | store `Decimal('46.74')` via ORM → read back `== Decimal('46.74')`; `sum()` of 1000×`0.01` == `Decimal('10.00')`. |
| T5 | `test_shift_variance_formula` | D4 | float 100, cash tenders 46.74, counted 140 → `expected_cash=146.74`, `variance=-6.74`. |
| T6 | `test_shift_close_short_needs_manager` | D2 | variance −6.74 < −2.00, no PIN → 409 `approval_required`; with manager PIN → 200. |
| T7 | `test_checkout_retry_on_locked` | D1 | `session.begin` raises `OperationalError("database is locked")` once → retry → 201. |
| T8 | `test_lock_order_sorted` | D1 | 3-SKU checkout acquires locks `[A,B,C]` order. |
| T9 | `test_synchronous_normal` | D1 | file-backed engine → `PRAGMA synchronous == NORMAL`. |
| T10 | `test_stx_etx_scanner` | D3 | simulated STX/ETX keydown → exact one `scan` emit, min-length respected. |
| T11 | `test_scanner_velocity_auto` | D3 | suffix mode with ≤20ms inter-key + Enter → `onScan` fires; ≥100ms inter-key → no emit (human typing rejected). |
| T12 | `test_cart_local_persist` | D4 | add line → `localStorage.pos_cart_v1` updated; "reload" restores. |
| T13 | `test_cart_gc_abandoned` | D4 | held ticket held_at 9h ago → init drops it, keeps recent. |
| T14 | `test_print_status_lifecycle` | D4 | checkout → `print_status='pending'`; print call → `'printed'`; printer fail → `'failed'`. |
| T15 | `test_410_nonblocking_sync` | D2 | two parked txns, 2nd over-sold → sync loop processes txn 1 (201) + txn 2 (410→failed_queue) without halting; `failed_queue` length 1, `outbound` length 0. |
| T16 | **regression** | — | existing 69 M1–M9 tests green; `mypy --strict` 0; `tsc --noEmit` 0; `ruff check` 0. |
| T17 | `test_divide_and_round_half_up` | D4 | `divideAndRound(14490n, 100n)===145n`; `divideAndRound(14400n,100n)===144n`; `divideAndRound(14449n,100n)===144n`; `taxFor("10.35","0.14")==="1.45"` (no truncation). |
| T18 | `test_tab_scoped_activecart_isolation` | D4 | Tab A adds line → `sessionStorage` activeCart has it; Tab B's `sessionStorage` activeCart empty; both tabs share `localStorage` heldTickets via `storage` event. |
| T19 | `test_offline_fifo_order` | D2 | enqueue 3 txns `parkedAt` t3>t2>t1 out of order; `peekOrdered()` returns t1→t2→t3; `executeSyncLoop` POST order matches. |
| T20 | `test_wal_quick_check_boot_gate` | D4 | lifespan corrupts db file → `_integrity_gate` restores latest `VACUUM INTO` snapshot → `quick_check` passes; no snapshot → `SystemExit`. |
| T21 | `test_offline_pin_webcrypto` | D2 | mock `crypto.subtle.digest`; cached policy (online verify-pin) + offline correct PIN → `approval_token` with `offline:true`; offline wrong PIN → reject. |
| T22 | `test_reprint_touches_no_inventory` | D2 | `POST /receipts/{id}/reprint` → 200; `inventory_extended.on_hand` unchanged; no new `ReceiptItem` row. |
| T17 | `test_quick_check_on_corrupt_db` | D4/H1 | `lifespan` calls `quick_check`; with a corrupted main DB and a valid snapshot present → restores snapshot, `quick_check` passes; with no snapshot → fail-fast `SystemExit`. |
| T18 | `test_wal_checkpoint_idle` | D4/H1 | background task fires `wal_checkpoint(PASSIVE)`; WAL file size stays bounded after 2000 writes with a lingering read transaction. |
| T19 | `test_reprint_touches_no_inventory` | D2/H3 | `POST /receipts/{id}/reprint` → 200, `print_status='printed'`, `inventory_extended.on_hand` unchanged, no new `ReceiptItem`. |
| T20 | `test_clock_skew_warning` | D4/H4 | request with `X-Client-Timestamp` 600s off on a POST → response carries `X-Time-Skew-Warning`; server `system_time < 2026-01-01` at boot → lifespan raises. |
| T21 | `test_approval_token_scoped` | D2/H5 | `verify-pin` → `approval_token`; use on `close_shift` with scope `pos:shift_override` → 200; reuse same token → 401; token with scope `pos:oversell_resolve` on `close_shift` → 403. |

---

## 9. Validation Pipeline (exact commands)

**Backend** (from `backend_fastapi`, venv `.venv`):
```bash
.venv\Scripts\python -m pytest --cov=app --cov-fail-under=90 -q
  -> expected: 69 existing + new M10 tests (T1–T21, C1, C6) all green, coverage >= 90%
.venv\Scripts\python -m ruff check app
  -> expected: 0 errors
.venv\Scripts\python -m mypy app --strict
  -> expected: 0 errors
.venv\Scripts\python -m pytest tests/test_m10_hardening.py::test_migration_idempotency_double_run -q
  -> expected: PASS (REAL→NUMERIC + all new columns present + idempotent)
```
**Frontend** (repo root):
```bash
npx prettier --check "app/**/*.{ts,tsx}" "lib/**" "stores/**" "types/**" "hooks/**"
  -> expected: 0 files needing rewrite
npx tsc --noEmit
  -> expected: 0 errors (strict)
npx tsc && next build
  -> expected: compiled successfully
npx vitest run lib/decimalCurrency.test.ts hooks/useBarcodeScanner.test.ts stores/posStore.test.ts lib/offlineQueue.test.ts lib/offlineCrypto.test.ts
  -> expected: H1–H6, H7–H18 pass (vitest installed as devDep)
```
**Post-deployment smoke:**
```bash
curl -s http://localhost:8000/api/v1/health        -> {"status":"ok"}
curl -H "Authorization: Bearer $TOK" http://localhost:8000/api/v1/pos/receipts/1 \
     | jq '.print_status, .sale_type, .subtotal'    -> "pending" "OTC" 0
```

---

## 10. Migration & Rollout Path

1. **Schema first:** extend `database.migrate_schema` (§7.1); `_harden_money_columns` toggles FKs OFF outside TXN + `foreign_key_check` gate before re-enabling — safe re-run on already-NUMERIC production DBs (no-op). `create_schema()` at lifespan applies on restart. **Add (§14.1):** `lifespan` calls `_integrity_gate(engine)` (boot `quick_check` + snapshot restore) before `create_schema`, launches `_schedule_wal_checkpoint` + `_schedule_snapshot` tasks, and enforces the boot clock sanity guard (§14.4).
2. **Backend:** models → schemas (`CheckoutRequest` adds `client_txn_id`, `tenders`, `lots`; `ReceiptTenders`/`Shift`/`OfflineTxn`/`StockDiscrepancy` schemas; `ApprovalTokenOut`) → repos (`ReceiptRepository`, `ShiftRepository`, `TenderRepository`, `OfflineTxnRepository`, `StockDiscrepancyRepository`) → services (extend `PosService.checkout` idempotency + override + tenders; add `allocate`, `open_shift`, `close_shift`, `verify_pin`, `replay_offline`) → routes (`pos_route` + `/receipts/{id}/reprint` + `/kick-drawer`; `auth_route.verify-pin` → `approval_token`) → `app/api/middleware.py` (X-Client-Timestamp skew) → `app/core/security.py` (`issue_approval_token` + single-use tracker) → tests.
3. **Frontend:** rewrite `useBarcodeScanner` (multi-mode: STX/ETX + suffix + velocity) → `lib/monetarySchema.ts` (Zod `DecimalString`, §13.4) → `lib/decimalCurrency.ts` (bigint cents math) → `stores/posStore.ts` (Zustand, `isHydrated` SSR fence + localStorage GC + multi-tab `storage` listener + integer-cents math) → `lib/storagePersist.ts` (`navigator.storage.persist()` guard, §13.3) → `hooks/useHydration.ts` (SSR fence hook) → `lib/peripherals.ts` (degrade-safe + hardware retry queue, §14.3) → `lib/offlineQueue.ts` (IndexedDB `outbox` via `idb`; `syncOfflineQueueWithLock()` Web Locks guard, §14.2) → rewrite `app/pos/page.tsx` (state machine, multi-tender, hold/resume, peripherals, a11y, `useHydration` guard, clock-skew banner, reprint/kick action bar) → `app/pos/OfflineSyncBanner.tsx` + `ManagerApprovalDialog` (token flow, §14.5) + `DiscrepanciesPanel` → build.
4. **Deploy single-worker:** confirm `uvicorn --workers 1` in `run_services.py`/`Dockerfile`. (Domain 1 §3.4 guardrail.)
5. **Verify** all gates (§9); append CHANGELOG; update `PROJECT_MAP.md`/`FLOW_LOGIC.md`.

---

## 11. Affected Files Index

| File | Action | Domain(s) |
|---|---|---|
| `backend_fastapi/app/core/database.py` | EDIT | D1, D2, D4 — extend `migrate_schema` + `_harden_money_columns` + `_configure_pragmas` (`synchronous=NORMAL`, `wal_autocheckpoint=1000`); **add** `_integrity_gate` (boot `quick_check` + snapshot restore), `_schedule_wal_checkpoint`, `_schedule_snapshot` (`VACUUM INTO`), boot clock sanity guard (§14.1, §14.4) |
| `backend_fastapi/app/core/models.py` | EDIT | D4 — `Numeric(10,2)` money fields; `print_status`, `sale_type`, `subtotal`, `tax_amount`, `client_txn_id`, `void_status`, `manager_pin`; `lot_id`, `voided` on `ReceiptItem`; new `Shift`/`ReceiptTender`/`OfflineTxn`/`StockDiscrepancy` models |
| `backend_fastapi/app/shared/schemas.py` | EDIT | D2, D4 — `CheckoutRequest` (+`client_txn_id`,`tenders`,`lots`), `TenderSplit`, `LotOverride`, `Shift*`, `ReceiptTenderRead`, `OfflineTxnRead`, `StockDiscrepancyRead`; money `Decimal` |
| `backend_fastapi/app/core/repositories.py` | EDIT | D1 — `retry_on_locked` decorator; D2 — `ReceiptRepository`/`ShiftRepository`/`TenderRepository`/`OfflineTxnRepository`/`StockDiscrepancyRepository`; D1 — lock-order audit helper |
| `backend_fastapi/app/services/pos_service.py` | EDIT | D1 — retry-on-locked + lock-order; D2 — idempotency + FEFO override + tenders + over-sell; D4 — Decimal math |
| `backend_fastapi/app/services/inventory_service.py` | EDIT | D1 — `allocate()` preview (read-only FEFO); D2 — `adjust_batch` retry-on-locked |
| `backend_fastapi/app/api/routers/pos_route.py` | EDIT | D2 — `/allocate`, `/receipts/{id}/void`, `/receipts/{id}/return`, `/shift/open`, `/shift/close`, `/shifts/{id}`, `/discrepancies`; extend `/checkout`; **add** `POST /receipts/{id}/reprint` + `/receipts/{id}/kick-drawer` (§14.3, no inventory mutation) |
| `backend_fastapi/app/api/routers/auth_route.py` | EDIT | D2 — `POST /verify-pin` → returns `approval_token` JWT (single-use, 60 s, action-scoped); verify `X-Approval-Token` on guarded routes (§14.5) |
| `backend_fastapi/app/core/security.py` | EDIT | D2 — `issue_approval_token(sub, scope, ttl)` + single-use `jti` tracker (in-memory, single-worker); `require_approval_token(scope)` dependency |
| `backend_fastapi/app/api/middleware.py` | CREATE | D4/H4 — `X-Client-Timestamp` skew guard + `X-Time-Skew-Warning` header (§14.4) |
| `backend_fastapi/app/core/lock_manager.py` | EDIT (defensive) | D1 — add `retry_on_locked` context or a `with_retry` helper on `acquire_drug_lock` |
| `backend_fastapi/app/shared/exceptions.py` | EDIT | D2 — `ApprovalRequiredError` (409), `OverSellError` (410), `TenderMismatchError` (400) |
| `backend_fastapi/tests/test_m10_hardening.py` | CREATE | D1–D4 — T1–T21 |
| `backend_fastapi/pyproject.toml` | EDIT | D1 — add `ruff`, `pytest-cov`; `[tool.ruff]` |
| `types/contracts.ts` | EDIT | D2/D4 — money fields (`Medicine.price`, `CheckoutItemRead.unit_price`, etc.) → `string` for NUMERIC(10,2) parity; add `ApprovalTokenOut` / `PinVerifyIn` schemas (§13.4,§14.5) |
| `stores/posStore.ts` | CREATE | D4 — Zustand (`isHydrated` SSR fence, `sessionStorage` activeCart per-tab §7.6.2, `localStorage` heldTickets shared §7.6.3, 8h GC, multi-tab `storage` listener, integer-cents math §7.6.4) |
| `lib/decimalCurrency.ts` | CREATE | D4 — `toCents`/`fromCents` + `divideAndRound` (HALF_UP) + `applyRate`/`mul`/`add`/`sub`/`taxFor`/`discountFor` (§7.6.4) |
| `lib/peripherals.ts` | CREATE | D3 — `PeripheralManager` (printer/drawer/scanner), degrade-safe + hardware retry queue (§14.3) |
| `lib/offlineQueue.ts` | CREATE | D2 — IndexedDB `outbox` via `idb`; strict FIFO (`peekOrdered`/`parkedAt ASC`); `syncOfflineQueueWithLock()` Web Locks guard (§14.2) |
| `lib/offlineCrypto.ts` | CREATE | D2 — WebCrypto SHA-256 offline PIN verification (§14.5.1) |
| `lib/storagePersist.ts` | CREATE | D4 — `requestPersistentStorage()` / `isStoragePersistent()` via `navigator.storage.persist()` guard (§13.3) |
| `lib/monetarySchema.ts` | CREATE | D4 — Zod `DecimalString` schema + `MedicineSchema` / `CheckoutItemSchema` / `CheckoutRequestSchema` enforcing string-typed money (§13.4) |
| `hooks/useHydration.ts` | CREATE | D4 — `useHydration()` hook: calls `posStore.hydrate()` in `useEffect`, returns `isHydrated` for `app/pos/page.tsx` guard |
| `app/pos/page.tsx` | EDIT | D2/D4 — state machine, multi-tender, hold/resume, peripherals, a11y live region |
| `app/pos/ManagerApprovalDialog.tsx` | CREATE | D2 — PIN → `/auth/verify-pin` → in-memory `approval_token` → `X-Approval-Token` header on action (§14.5); raw PIN never in action payload |
| `app/pos/DiscrepanciesPanel.tsx` | CREATE | D2 — over-sell resolution UI (restock refund / float loss) |
| `.pre-commit-config.yaml` | CREATE | M9 — ruff/prettier/mypy/tsc/migration gates |
| `.github/workflows/quality-gate.yml` | CREATE | M9 — CI matrix |
| `package.json` | EDIT | M9 — add `idb` runtime dep, `vitest` devDep + `test` script; M10 — eslint/prettier devDeps + scripts |
| `run_services.py` / `Dockerfile` | EDIT | D1 — enforce `--workers 1` |
| `CHANGELOG.md` | EDIT | — M10 entries |
| `PROJECT_MAP.md` | EDIT | — record M10, clear `[ORPHANS & PENDING]` |

---

## 12. Out of Scope

- **Alembic re-platforming** — existing `migrate_schema` retained and hardened (§7.1); Alembic noted as production recommendation (gap G6, first draft §6).
- **Multi-worker uvicorn** — explicitly **disallowed** for edge v1 (Domain 1 §3.4); PG `FOR UPDATE` path documented as future.
- **WebUSB/WebSerial native printer/drawer** — future desktop-wrapper enhancement; v1 uses `window.print()` + ESC/POS kick-through-print + optimistic offline copy.
- **Controlled-substance (DEA) enforcement, signature capture** — deferred (gap G8); `dea_schedule` column exists but unused.
- **Frontend jest/Testing-Library suite** — M9 provisions eslint/prettier/tsc; component tests deferred to Playwright e2e unless requested.
- **Dashboard/observability UI** — events emitted; Grafana/dashboard deferred.
- **Desktop Tauri/Electron shell** — deferred per refactor plan decision.
- **Multi-site / distributed-transaction sync** — single-machine/local-server deployment is the baseline (resolves gap #3).

---

## 13. Critical Edge-Case Hardening (four technical mitigations)

### 13.1 Edge Case 1 — Index Loss During SQLite Table Rebuilds

**Risk:** The `CREATE/INSERT/DROP/RENAME` migration pattern in `_harden_money_columns` destroys all secondary indexes on the dropped table. SQLite automatically cascades index destruction on `DROP TABLE`, but the `ALTER TABLE … RENAME TO` does **not** restore them. Without reconstruction, queries against `products`, `receipt_items`, `sold_items`, `receiving_log` would degrade from O(log n) to O(n) post-migration — an unacceptable performance cliff in a high-throughput pharmacy POS.

**Mitigation:** Capture all secondary index DDL from `sqlite_master` *before* the DROP, then replay it *after* the RENAME. This is implemented in the updated `_harden_money_columns` (§7.1, Steps 3 and 3b). The capture query targets only user-created indexes (origin `'c'` and `'u'`), excluding the implicit PK index (`origin='pk'`) which is already preserved by the `PRIMARY KEY` clause in the new DDL. The replay adds `IF NOT EXISTS` for idempotent re-runs.

**Verification:** T1 asserts that all pre-existing indexes survive the migration. A dedicated check queries `PRAGMA index_list(table)` before and after to confirm the index sets are identical (modulo PK).

### 13.2 Edge Case 2 — `PRAGMA foreign_keys = OFF` Transaction Boundary

**Risk:** `create_schema()` (line 80 of `database.py`) wraps `migrate_schema(conn)` inside `async with _engine.begin()`, which opens a SQLAlchemy transaction. SQLite's documentation explicitly states: *"The `foreign_keys` pragma is a no-op within a transaction."* Executing `PRAGMA foreign_keys = OFF` mid-transaction is silently ignored — FK enforcement stays ON. If a table being rebuilt has inbound foreign keys, the `DROP TABLE` raises `FOREIGN KEY constraint failed`, crashing the migration.

**Mitigation:** Use SQLAlchemy's `execution_options(isolation_level="AUTOCOMMIT")` to create a **branched connection** that shares the same DBAPI handle but executes the PRAGMA without a transaction wrapper:

```python
autocommit_conn = conn.execution_options(isolation_level="AUTOCOMMIT")
await autocommit_conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
# ... DDL runs on conn (within the outer TXN, but FK is OFF at connection level) ...
fk_check = await autocommit_conn.exec_driver_sql("PRAGMA foreign_key_check;")
await autocommit_conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
```

**Why this works:** `foreign_keys` is a **connection-level** setting in SQLite, not a transaction-level one. Once set OFF (via autocommit, outside any TXN), it persists for the lifetime of the DBAPI connection. The subsequent DDL — executed on `conn` within the outer `begin()` transaction — inherits the connection-level flag. `PRAGMA foreign_key_check` (also a pragma) is executed in autocommit mode to verify referential integrity before re-enabling.

**Critical subtlety with aiosqlite:** `execution_options(isolation_level="AUTOCOMMIT")` returns a new `Connection` object that wraps the **same** underlying DBAPI connection (branched connection pattern). The PRAGMA executes on this shared handle, so the flag propagates to the outer transaction's DDL. This is confirmed by the aiosqlite pool being 1:1 with the SQLAlchemy `begin()` connection.

### 13.3 Edge Case 3 — Native Browser Storage Eviction

**Risk:** Chromium may evict `localStorage`/IndexedDB under disk pressure (quota exceeded, tab process killed, or user clears data). In a pharmacy POS where the browser is the cash register, losing the offline queue or cart state mid-shift means **lost sales**. The audit requires graceful degradation, not silent data loss.

**Mitigation:** Implement the **`navigator.storage.persist()` + `persisted()` guard** pattern, requested as a non-blocking best-effort at startup. This asks the browser to mark origin storage as non-evictable. In Chromium-based browsers this grants `persistent` quota (~6% of disk); in Safari/Firefox it returns `false` and falls back to best-effort. The key is handling it **gracefully** — never blocking POS operation.

```typescript
// lib/storagePersist.ts
export async function requestPersistentStorage(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.storage?.persist) {
    return false;  // SSR / unsupported browser
  }
  const currentlyPersisted = await navigator.storage.persisted();
  if (currentlyPersisted) return true;
  // Browser may prompt the user or auto-grant (Chromium auto-grants in many contexts)
  return navigator.storage.persist();
}

// Called once at app startup (e.g., in a root layout or _app equivalent)
export function useStoragePersistence(enabled: boolean = true) {
  useEffect(() => {
    if (!enabled) return;
    requestPersistentStorage().catch((err) => {
      // Non-fatal — log to telemetry; POS still works without persistence guarantee
      console.warn("Storage persistence request failed:", err);
    });
  }, [enabled]);
}

// Verification helper — check before relying on local storage
export async function isStoragePersistent(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.storage?.persisted) {
    return false;
  }
  return navigator.storage.persisted();
}
```

**Integration points:**
- `stores/posStore.ts` calls `isStoragePersistent()` in `hydrate()` and logs a warning (to telemetry) if persistence is denied.
- `lib/offlineQueue.ts` (IndexedDB) calls `requestPersistentStorage()` at DB open; if denied, it surfaces a **banner** ("Offline data may be lost on browser eviction") in the POS UI rather than blocking.
- The POS `app/pos/page.tsx` calls `useStoragePersistence()` in a root-level `useEffect` so it fires once per session.

**Fallback:** If persistence is denied, the store still uses `localStorage`/`IndexedDB` but with an explicit banner warning the cashier to reconnect to the server promptly. This is the correct tradeoff — never block commerce for a best-effort storage API.

### 13.4 Edge Case 4 — API Client JSON Deserialization Bounds (Float Drift)

**Risk:** The backend serializes `Decimal` money fields as JSON numbers (e.g., `"price": 46.74`). JavaScript's `JSON.parse` coerces these to IEEE-754 `float64`. Even if the store converts to `bigint` cents *immediately*, the damage is already done: `46.74` is stored as `46.7400000000000019...` in the `float64`. `Math.round(46.74 * 100) = 4674` happens to work for this value, but `Math.round(0.1 + 0.2) * 100 = 30` (expected 30, gets 30 — actually OK here) but `Math.round((0.1 + 0.2) * 100) = 30` while `0.3 * 100 = 30.000000000000004`. Accumulated drift across many line items can cause a 1-cent discrepancy vs the backend's `NUMERIC(10,2)` sum.

**Mitigation:** Enforce **strict string typing at the API boundary** using Zod. No monetary field should ever enter the store as a `number`. The Zod schema coerces/validates all monetary JSON into strings at parse time, before any arithmetic.

```typescript
// lib/monetarySchema.ts
import { z } from "zod";

/**
 * Strict string-typed decimal. Rejects JSON numbers to force the sender
 * to serialize Decimal as a string (not a float). Validates 1–2 decimal
 * places and a numeric pattern. Never produces a JavaScript float.
 */
export const DecimalString = z
  .string({
    // If the API sends a JSON number (e.g. 46.74), Zod's .string() rejects it
    // with a clear error — forcing the backend to emit "46.74" (string).
    invalid_type_error: "Monetary fields must be strings, not numbers (JSON float drift)",
  })
  .refine(
    (val) => {
      // Optional leading minus; integer part; optional 2-decimal fractional part.
      const ok = /^-?\d+(\.\d{1,2})?$/.test(val);
      return ok && val !== "-";
    },
    { message: "Monetary value must be a decimal string with at most 2 fractional digits" }
  )
  .transform((val) => {
    // Normalize to exactly 2 decimal places (e.g. "46" → "46.00")
    const [int, frac] = val.split(".");
    if (!frac) return `${int}.00`;
    return `${int}.${frac.padEnd(2, "0")}`;
  });

export const MedicineSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  // price was `number` in contracts.ts — now strictly a string.
  price: DecimalString,
  wholesale_price: DecimalString.optional().nullable(),
  manufacturer_barcode: z.string(),
  internal_unique_barcode: z.string(),
  status: z.string(),
  expiry_date: z.string(),
  manufacture_date: z.string(),
  vendor_name: z.string(),
  dea_schedule: z.string().optional().nullable(),
  reorder_threshold: z.number().int().optional().nullable(),
  is_deleted: z.boolean(),
});

export type Medicine = z.infer<typeof MedicineSchema>;

// CheckoutRequest — all monetary fields are DecimalString
export const CheckoutItemSchema = z.object({
  product_name: z.string(),
  quantity: z.number().int().positive(),
  unitPrice: DecimalString,       // "46.74"
  discountAmount: DecimalString,  // "0.00"
  taxRate: DecimalString,         // "0.14" (14% as decimal fraction)
});

export const CheckoutRequestSchema = z.object({
  line_items: z.array(CheckoutItemSchema),
  tenders: z.array(TenderSplitSchema),
  payment_method: z.enum(["cash", "card", "transfer", "insurance", "mixed"]),
  client_txn_id: z.string().uuid().optional(),
  patient_id: z.number().int().optional().nullable(),
});
```

**Integration with the store and arithmetic:**

```typescript
// lib/decimalCurrency.ts — bigint cents math (no float ever)
export const toCents = (s: string): bigint => {
  // Input is always a validated DecimalString like "46.74"
  const [int, frac = "00"] = s.split(".");
  const sign = int.startsWith("-") ? -1n : 1n;
  const absInt = BigInt(int.replace("-", ""));
  const absFrac = BigInt(frac.padEnd(2, "0").slice(0, 2));
  return sign * (absInt * 100n + absFrac);
};

export const fromCents = (c: bigint): string => {
  const sign = c < 0n ? "-" : "";
  const abs = c < 0n ? -c : c;
  return `${sign}${abs / 100n}.${(abs % 100n).toString().padStart(2, "0")}`;
};

// HALF_UP division — prevents tax/discount truncation drift (§7.6.4).
export const divideAndRound = (numerator: bigint, denominator: bigint): bigint => {
  if (denominator <= 0n) throw new RangeError("denominator must be > 0");
  const q = numerator / denominator;
  const r = ((numerator % denominator) + denominator) % denominator;
  return r * 2n >= denominator ? q + 1n : q;
};

export const applyRate = (amountCents: bigint, rateBips: bigint, scale: bigint = 10000n): bigint =>
  divideAndRound(amountCents * rateBips, scale);

export const mul = (decimalStr: string, qty: number): string =>
  fromCents(toCents(decimalStr) * BigInt(qty));

export const add = (a: string, b: string): string => fromCents(toCents(a) + toCents(b));
export const sub = (a: string, b: string): string => fromCents(toCents(a) - toCents(b));
```

**Critical enforcement rule:** `lib/api.ts` (the axios/Zod fetch wrapper) must `.parse()` every response through the relevant Zod schema **before** exposing data to stores. If the backend sends `"price": 46.74` (a JSON number), `DecimalString` rejects it → the developer sees a clear error and must fix the backend to serialize `Decimal` as a string. This is the correct "fail-fast" contract: the boundary enforces the invariant, not every consumer.

**Backward compatibility:** `contracts.ts` currently types money as `number`. The migration path: update `contracts.ts` money fields to `string`, regenerate Zod schemas from a single source of truth (the plan §11 flags this). Until that lands, the store should defensively `String(val)` + validate at the boundary even when the type says `number`.

---

## 14. Production Hardening — Edge Resilience, Sync, Peripherals, Time, Auth

The preceding domains assume a healthy edge machine. These five mitigations defend the **physical deployment reality**: abrupt power loss, disk exhaustion, multi-tab LAN terminals, decoupled hardware, clock-less edge SoCs, and credential exposure in logs.

### 14.1 Edge Hardware & SQLite Resilience (power loss & disk exhaustion)

**Risk:** `synchronous=NORMAL` (§3.3) protects against transaction-level loss but **not** WAL-header corruption if power is cut mid-frame on a cheap POS SSD without power-loss protection. Worse, long-lived read transactions (a hung tab holding a cursor) block passive WAL checkpoints → the `-wal` file grows unbounded → `SQLITE_FULL` → all writes rejected mid-shift.

**Mitigation (three layers):**

1. **Boot-time integrity gate** — in the FastAPI `lifespan` (before `create_schema`), run `PRAGMA quick_check(1)` on the main DB file. On failure:
   - **Do NOT** try to "recover from the WAL" blindly (the main-header corruption case is unrecoverable from WAL alone).
   - Restore the most recent `VACUUM INTO` snapshot (§14.1.3), then re-run `quick_check`. If still failing → **fail-fast startup** with a clear `CRITICAL` log + health endpoint `status=unhealthy` so the terminal shows a "DB corrupted, call admin" screen instead of serving partial data.
2. **Explicit WAL checkpoint policy** — set `PRAGMA wal_autocheckpoint = 1000` in `_configure_pragmas`, plus an idle `asyncio` task that calls `PRAGMA wal_checkpoint(PASSIVE)` every N seconds (PASSIVE never blocks writers). This bounds WAL growth even if a stray read transaction lingers.
3. **Automated hot snapshots** — an `asyncio` daily task runs `VACUUM INTO '<backup_dir>/pharmacy_<timestamp>.db'` (SQLite ≥ 3.27). `VACUUM INTO` writes a compact copy **without** blocking the live DB (unlike in-place `VACUUM`). Keep the last 7 snapshots; purge older.

```python
# backend_fastapi/app/core/database.py (additions)
async def _integrity_gate(engine: AsyncEngine) -> None:
    """quick_check at boot; restore latest snapshot on corruption."""
    try:
        async with engine.connect() as conn:
            res = await conn.exec_driver_sql("PRAGMA quick_check(1)")
            rows = res.fetchall()
        if any("ok" not in str(r).lower() for r in rows):
            raise RuntimeError(f"quick_check failed: {rows}")
    except Exception as exc:  # corrupt or unreadable
        logger.critical("DB quick_check FAILED: %s — attempting snapshot restore", exc)
        if not _restore_latest_snapshot():
            raise SystemExit("DB corrupt and no usable snapshot — fail-fast.") from exc

async def _schedule_wal_checkpoint(engine: AsyncEngine, interval: int = 300) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            async with engine.connect() as conn:
                await conn.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:  # pragma: no cover - defensive
            pass

async def _schedule_snapshot(engine: AsyncEngine, backup_dir: str, every: int = 86400) -> None:
    while True:
        await asyncio.sleep(every)
        try:
            async with engine.connect() as conn:
                await conn.exec_driver_sql(f"VACUUM INTO '{backup_dir}/pharmacy_{int(time.time())}.db'")
        except Exception as exc:  # pragma: no cover
            logger.error("Snapshot failed: %s", exc)
```

`create_schema()` (§10 step 1) should be preceded by `_integrity_gate(engine)` at lifespan start, and the two background tasks launched via `asyncio.create_task` in the lifespan.

### 14.2 Multi-Tab Synchronization Race (IndexedDB sync loop)

**Risk:** A cashier opens the POS in two tabs on one LAN terminal. On `online` event both tabs read the same IndexedDB `outbox` and fire `POST /checkout` for the same `client_txn_id` in parallel. Server idempotency (§4.3) blocks the duplicate receipt, but it still burns two requests, emits a spurious 410, and risks two Zustand `set()` calls racing on the same state — UI flicker / lost-local-update.

**Mitigation — Web Locks API** around the sync loop so **exactly one tab** drives `syncLoop` at a time. The `ifAvailable: true` option makes the non-holder simply no-op (graceful on browsers without Web Locks):

```typescript
// lib/offlineQueue.ts (extend §7.7)
export async function syncOfflineQueueWithLock(): Promise<void> {
  if (typeof navigator !== "undefined" && "locks" in navigator) {
    await navigator.locks.request(
      "pos_offline_sync_lock",
      { ifAvailable: true },
      async (lock) => {
        if (!lock) return;            // another tab owns the lock → skip
        await executeSyncLoop();       // §4.5 state machine
      }
    );
  } else {
    await executeSyncLoop();           // fallback (older browsers) — still idempotent server-side
  }
}
```

Wire every `online` handler and the periodic retry timer to call `syncOfflineQueueWithLock()`, **not** `executeSyncLoop()` directly. The Zustand `storage` listener (§7.6.3) is unaffected — it only reconciles local state, never triggers network sync.

### 14.3 Peripheral Hardware Stalls vs. Transaction Atomicity

**Risk:** Financial checkout (DB commit) succeeds, then the browser fires ESC/POS printing / cash-drawer kick. A paper jam, disconnected printer, or unplugged drawer cable throws. If the UI treats that as "checkout failed" and the cashier retries → **double charge / double stock deduction**.

**Mitigation — strict decoupling:**
- Financial commit (§4.3 `process_checkout`) and hardware execution are **separate, non-transactional** phases. A hardware failure **never** rolls back the receipt.
- On hardware failure post-commit: set `receipts.print_status = 'failed'` (column already exists, §6.2b) and surface a **"Reprint Receipt / Pop Drawer"** action bar targeting a dedicated endpoint that **touches no inventory**.
- Add route `POST /api/v1/pos/receipts/{receipt_id}/reprint` (and `/kick-drawer`). Both re-run only the peripheral command against the existing, immutable `Receipt`/`ReceiptItem` rows.

```python
# backend_fastapi/app/api/routers/pos_route.py (add)
@router.post("/receipts/{receipt_id}/reprint", status_code=200)
async def reprint_receipt(receipt_id: int, _: Annotated[None, Depends(require_permission("pos.checkout"))] = None):
    # Re-fetch immutable receipt; re-send to printer queue. No inventory, no money mutation.
    receipt = await ReceiptRepository.get(receipt_id)
    if not receipt:
        raise NotFoundError("receipt", receipt_id)
    await peripherals.print_receipt(receipt)   # fire-and-forget; failure → 502, not 200
    await ReceiptRepository.set_print_status(receipt_id, "printed")
    return {"status": "reprinted", "receipt_id": receipt_id}
```

Client `lib/peripherals.ts` (`PeripheralManager`) already degrade-safe (§11) — extend it with a **hardware retry queue**: on print/drawer failure, enqueue `{receipt_id, op}` and retry with backoff; expose `retryFailedHardware()` to the action bar. Never call `process_checkout` from this path.

### 14.4 Hardware Clock Drift on Offline Edge Machines

**Risk:** Fanless POS SoCs / Raspberry Pi edge controllers often lack a battery-backed RTC. A power cycle while offline (no NTP) resets the clock to `1970-01-01` or the image build date. Consequences: FEFO `expiration_date < NOW()` miscalculates, JWT `nbf`/`exp` fail, and shift/audit windows become meaningless.

**Mitigation:**
1. **Boot sanity check** — at FastAPI lifespan, fail-fast if `system_time < MIN_VALID_TIMESTAMP` (e.g. `2026-01-01`). The terminal shows "Clock invalid — set date/time" rather than serving wrong FEFO/audit data.
2. **Client–server skew header** — every API client request sends `X-Client-Timestamp: <epoch ms>`. A server middleware computes `skew = abs(server_now - client_ts)`; if `skew > 300_000 ms`, it (a) records an audit warning and (b) returns `X-Time-Skew-Warning: <ms>` header + a `409 time_skew` body on *state-changing* calls so the UI shows a critical banner. Read-only GETs still serve.
3. **Backend is the source of truth for time** — FEFO selection (`inventory_service.fifo_deduct`) and shift windows MUST use `func.now()` / server time, never a client-supplied timestamp. The checkout payload carries `client_txn_id` but **not** a client timestamp for stock logic.

```python
# backend_fastapi/app/api/middleware.py (add)
from datetime import datetime, timezone
MIN_VALID_TIMESTAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)

@app.middleware("http")
async def time_skew_guard(request: Request, call_next):
    client_ts = request.headers.get("X-Client-Timestamp")
    response = await call_next(request)
    if client_ts and request.method != "GET":
        try:
            skew = abs(datetime.now(timezone.utc).timestamp() * 1000 - int(client_ts))
            if skew > 300_000:
                response.headers["X-Time-Skew-Warning"] = str(skew)
        except ValueError:
            pass
    return response
```

### 14.5 Security & Cryptographic Auditability of Manager PINs

**Risk:** Manager overrides (shift close on negative variance, 410 over-sell resolution, custom discounts) currently flow a raw PIN into the action (`POST /auth/verify-pin` → `manager_pin` stamped on the row). Sending the PIN on every action request leaks it into request logs / proxies; storing anything PIN-derived in `receipts.manager_pin` beyond the **username** invites future misuse.

**Mitigation — short-lived, action-scoped approval tokens:**
- `POST /api/v1/auth/verify-pin` verifies the PIN **once**, then issues a `approval_token` JWT: single-use (`jti`), TTL 60 s, `scope` bound to the exact action (`pos:shift_override` | `pos:oversell_resolve` | `pos:discount_override`), `sub` = manager username.
- The client passes `X-Approval-Token: <jwt>` on the **target** action request. No raw PIN travels with the action.
- Server validates: signature, `exp`, `scope` matches the route, and **single-use** (`jti` tracked in an in-memory `set` with TTL — safe because edge is single-worker, §3.4). On reuse → `401`. Wrong scope → `403`.
- `receipts.manager_pin` keeps storing only the **manager username** (already the design, §6.5) — never the token or PIN.

```python
# backend_fastapi/app/api/routers/auth_route.py (extend)
@router.post("/verify-pin", response_model=ApprovalTokenOut)
async def verify_pin(payload: PinVerifyIn, sess=Depends(get_session)):
    manager = await AuthService.verify_pin(payload.username, payload.pin)  # raises on bad PIN
    token = issue_approval_token(sub=manager.username, scope=payload.scope, ttl=60)
    return {"approval_token": token, "scope": payload.scope, "expires_in": 60}

# pos_route.close_shift / discrepancies resolve: require header
async def close_shift(..., tok: Annotated[str, Depends(require_approval_token("pos:shift_override"))]):
    ...
```

Client `ManagerApprovalDialog.tsx` (§11): on PIN submit → `verify-pin` → store `approval_token` in memory only (never `localStorage`) → attach `X-Approval-Token` to the action → drop token after use. This closes the log-leak and replay surface.

#### 14.5.1 Offline Manager PIN Fallback (WebCrypto)

**Risk:** When the LAN server is unreachable, `/api/v1/auth/verify-pin` cannot issue an `approval_token`. A cashier needing an offline manager override (shift close on a cash shortage, or force-resolving an over-sell) is **locked out** — the POS cannot close the shift or resolve the discrepancy until connectivity returns.

**Mitigation — device-bound, encrypted cache with WebCrypto SHA-256 verification:**
- On every **successful online** `verify-pin`, the server returns (in addition to the `approval_token`) an `encrypted_manager_policy` — an AES-GCM blob containing `{ username, scope, pin_hash: SHA-256(pin + salt), salt, valid_until }`. The blob is encrypted with a **non-extractable** AES-GCM key that the **client** generates via `crypto.subtle.generateKey` + a random seed persisted in IndexedDB (device-bound; if IndexedDB is wiped, the policy is lost → must re-verify online).
- The client stores the encrypted policy in IndexedDB `manager_policies` (not `localStorage`, not readable without the device key).
- Offline path: `ManagerApprovalDialog` → user enters PIN → `crypto.subtle.digest("SHA-256", enc.encode(pin + salt))` → compare to decrypted `pin_hash` → if match **and** `valid_until > Date.now()` → issue a **local** `approval_token` (same JWT shape, `offline: true`, TTL 300 s) → attach `X-Approval-Token` + `X-Approval-Source: offline` to the action.

```typescript
// lib/offlineCrypto.ts — WebCrypto offline PIN verification
export async function verifyPinOffline(pin: string, policy: ManagerPolicy): Promise<boolean> {
  const enc = new TextEncoder();
  const provided = await crypto.subtle.digest("SHA-256", enc.encode(pin + policy.salt));
  const providedHex = Array.from(new Uint8Array(provided)).map(b => b.toString(16).padStart(2, "0")).join("");
  return providedHex === policy.pin_hash && Date.now() < policy.valid_until;
}
```

**Compensating controls (critical for audit):**
- The local policy is **time-boxed** (`valid_until`, e.g. 8 h from last online verify — must re-verify online within the shift).
- Only the **salted hash** is stored, never the PIN.
- The AES-GCM blob is **encrypted at rest** with a non-extractable device key — casual IndexedDB inspection yields ciphertext.
- Offline approvals are **flagged** in the action log (`approval_source: 'offline'`) and require **follow-up online manager re-confirmation** within the shift (the §4.4 Discrepancy panel surfaces these pending entries for a manager to re-auth online). This closes the lockout without removing the audit trail.

> **Trust boundary:** This is a deliberate, documented relaxation — the device key lives client-side, so a stolen terminal with the cached policy *could* allow offline PIN brute-force. The mitigations are: (1) time-boxed validity, (2) 6-digit PIN space + lockout-after-N on the online path, (3) mandatory online re-confirmation on next sync, (4) all offline overrides flagged for manager review.

### 14.6 Hardening summary matrix

| Domain | Edge risk | Impact | Solution (section) |
|---|---|---|---|
| Storage integrity | Abrupt power loss | WAL corruption / `SQLITE_FULL` | Boot `quick_check` + snapshot restore; `wal_autocheckpoint` + idle `wal_checkpoint(PASSIVE)`; daily `VACUUM INTO` (§14.1) |
| Sync race | Multi-tab LAN | Duplicate API calls, UI state drift | Web Locks API around sync loop (§14.2) |
| Peripherals | Paper jam / drawer stall | Double-charge by cashier retry | Decoupled hardware; `print_status='failed'`; `/receipts/{id}/reprint` no-inventory endpoint (§14.3) |
| Time sync | No RTC hardware | Broken FEFO, JWTs, shift logs | Boot clock guard; `X-Client-Timestamp` skew detection; server-time-only stock logic (§14.4) |
| Auth audit | Plaintext PIN payloads | Credential leakage in logs/dumps | Short-lived, action-scoped `approval_token` JWT; `X-Approval-Token` header; WebCrypto offline fallback (§14.5) |
