# Unified Architectural Plan — Edge Retail Pharmacy POS (M9/M10 + Security Addendum)

> **Supersedes:**
> - `.kilo/plans/1786620973404-m9-m10-precommit-os-spec.md` (base remediation spec; finalized 2026-08-13)
> - `.kilo/plans/1786748052000-pos-operational-security-addendum.md` (5-gap addendum; finalized 2026-08-14)
>
> **Date:** 2026-08-14
> **Target Stack:** FastAPI backend (`backend_fastapi/`) + Next.js 16 / React 19 frontend (repo root `app/`). Single-machine edge deployment — FastAPI + SQLite on-box, browser-thin client on LAN.
> **Status:** Implementation-ready. This single file is the complete spec.
> **Mode:** Plan only — no source/DB files modified here.

Foundations **carried over unchanged** (the base spec's hard-won invariants):
- Single Uvicorn worker (`--workers 1`) + WAL + `busy_timeout=5000` + per-drug sorted `asyncio.Lock` (§3.4) — correct at one process.
- FEFO inventory (`expiration_date ASC`) with per-drug lock ordering — prevents deadlocks and expired-lot sales.
- `410 Gone` as the non-disruptive over-sell / discrepancy signal (§4.5) — sync loop drains the next FIFO item; one failure never halts the queue.
- Integer-cents money math (`lib/decimalCurrency.ts`, `toCents`/`fromCents` never touching `Number()`) with backend `Decimal`/`NUMERIC(10,2)`.

This plan adds **eight** resolved concerns: the five prior gaps (each still valid) plus three new edge-case resolutions that close the DoS, clock-drift, and write-contention threats that the prior draft left open.

---

## Table of Contents
1. [Concern 1 — Shift Reconciliation Omits Cash Drops & Paid-Outs](#c1)
2. [Concern 2 — Offline PIN Brute-Force + DoS-Safe Lockout](#c2)
3. [Concern 3 — sessionStorage Cart Volatility on Crash](#c3)
4. [Concern 4 — Expired Lot Handling During Offline Replay (410 vs 400)](#c4)
5. [Concern 5 — Web Locks Compatibility Fallback](#c5)
6. [Concern 6 — Offline PIN Lockout DoS (cooldown, not wipe)](#c6)
7. [Concern 7 — Clock Drift vs FIFO Replay (Lamport logical clock)](#c7)
8. [Concern 8 — SQLite Read/Write Contention During Reporting](#c8)
9. [Unified Summary Matrix](#matrix)
10. [Migration & Rollout Path](#rollout)
11. [Affected Files Index](#files)
12. [Validation Pipeline](#validation)
13. [Build, Packaging & Deployment Automation (Low-Spec Windows)](#build)
14. [Appendix A — Network & Resource Resilience](#appendix-a)
15. [Appendix B — Additional Engineering Concerns](#appendix-b)
16. [Appendix C — Scaling & Hardening Extensions](#appendix-c)

---

<a id="c1"></a>
## 1. Shift Reconciliation Omits Cash Drops & Paid-Outs

### Critique
The formula `expected_cash = opening_float + Σ cash_tenders` describes a closed system. Real pharmacy tills are open systems: cash **leaves** mid-shift via **Safe Drops** (skimming excess to a back safe above a threshold) and **Paid-Outs** (petty cash / vendor / delivery payouts). Untracked, a \$300 drop registers as a **false −\$300 short variance** → false shift-close block → manager-override friction that masks real drift. Root cause: no drawer-movement journal; no auth tiering by amount.

### Refinement
Introduce a `drawer_movements` journal; split inflows/outflows in the formula.

**Data model** (`app/core/models.py`):
```python
class DrawerMovementType(str, Enum):
    cash_tender = "cash_tender"      # IN (already captured via tenders)
    float_add   = "float_add"        # IN — manager adds change fund
    cash_drop   = "cash_drop"        # OUT — cashier skims (≤ DROP_THRESHOLD auto)
    paid_out    = "paid_out"         # OUT — petty cash / vendor pay
    pickup      = "pickup"           # OUT — manager removes excess cash
    manager_adj = "manager_adj"      # IN/OUT — manager correction

class DrawerMovement(Base):
    __tablename__ = "drawer_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(FK("shifts.id", ondelete="CASCADE"), index=True)
    type: Mapped[DrawerMovementType]
    amount_cents: Mapped[int]      # always non-negative; direction implied by type
    reason: Mapped[str | None]
    requires_approval: Mapped[bool]
    manager_txn_id: Mapped[int | None] = mapped_column(FK("receipts.id"))
    created_by: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

**Updated variance** (§4.2). Each term's direction is fixed by its type (`DrawerMovementType`):
- `cash_tender`, `float_add`, `manager_adj(+)` → inflows (till gains cash).
- `cash_drop`, `paid_out`, `pickup`, `manager_adj(−)` → outflows (till loses cash).

So the single-line close-screen formula is:
```
expected = opening_float + Σ(cash_tenders) + Σ(float_add) − Σ(cash_drop + paid_out + pickup)
variance = counted_cash − expected        # a nonzero variance is a true error
```

**Auth policy** (env-tunable): `DROP_THRESHOLD` default \$400 (cashier auto); `PAID_OUT_LIMIT` default \$50 (cashier auto, above → token); `pickup` / `manager_adj` always require `require_approval_token`.

**API** (`pos_route.py`): `POST /shift/{id}/drawer-movement` with `DrawerMovementIn` (`type, amount: DecimalString, reason?`); `require_approval_token` enforced by a decorator when `requires_approval` is true for the type+amount.

### Tests
- **T23:** `test_shift_expected_cash_with_drop` — float \$100, takers \$250, drop \$150 → expected \$200, variance 0, close allowed.
- **T24:** `test_paid_out_requires_approval_over_threshold` — paid_out \$51 w/o token → `409`; with token → 201 + movement row.

### Affected files
`app/core/models.py`, `app/core/lock_manager.py` (lock-order audit for drawer writes), `app/api/routers/pos_route.py`, `types/contracts.ts`, `app/pos/ShiftCloseDialog.tsx`, `tests/test_m10_hardening.py`.

---

<a id="c2"></a>
## 2. Offline PIN Security — SHA-256 Brute-Force Risk

### Critique
§14.5.1 offline fallback used `SHA-256(pin + salt)`. SHA-256 is a fast hash, not a PIN KDF. A 4–6 digit PIN (10⁴–10⁶ space) is brute-forceable from the browser console in <10 ms — the single most privileged action (shift close, over-sell, discounts) becomes a free offline oracle. No attempt limiter persisted across reloads. **Critical.**

### Refinement
Replace with PBKDF2-HMAC-SHA256 (browser-native WebCrypto, no dependency) + a persisted, cooldown-based limiter.

- **KDF:** PBKDF2-SHA256, configurable iteration count via the `POS_OFFLINE_PIN_KDF` env var (default **200 000** iterations; ≥120 ms/verify on a 2018 Celeron — a 6-digit brute force takes ≥300 days even with an open console). NOT Argon2id (would require `argon2-browser` WASM bundle — rejected per Simplicity-First; PBKDF2 is browser-native and sufficient against a JS-console attack).
- **Iteration calibration task (staging, per §13 Build & Release):** before release, run a calibrated benchmark of `crypto.subtle.deriveBitting`/`deriveKey` against `POS_OFFLINE_PIN_KDF` on the target thin-client hardware (Celeron/Atom J4125-class, 4 GB RAM) and assert a single `verifyPin` round-trip is **<150 ms**. If latency exceeds the budget, lower the default via `POS_OFFLINE_PIN_KDF` (floor 120 k) or accept the calibrated count for that hardware profile. Record measured ms/count in `docs/hardening_calibration.md` and gate the release on the assertion.
- **Policy blob** (`lib/offlineCrypto.ts`, AES-GCM encrypted at rest in IndexedDB `manager_policies`): `username, salt, kdf{iterations}, pin_hash, valid_until, failure_count, locked_until`.
- **Verify:** `timingSafeEqual` on PBKDF2 digest (constant-time). Wrong PIN → `failure_count += 1`.
- **Lockout semantics (see also Concern 6):** tiered cooldown, not immediate wipe. The detailed lockout model is in §6 below; this section owns the KDF + constant-time compare.

**Audit contract unchanged:** offline token is still `offline: true` + `X-Approval-Source: offline`; server logs + flags for later online re-confirmation.

### Tests
- **T25:** `test_offline_pin_pbkdf2_brute_force_resistance` — `derivePin` async + ≥150 ms; wrong PIN increments counter without wiping policy.
- **H19:** `test_offline_pin_constant_time_compare` — `timingSafeEqual` on equal-length buffers; wrong PIN leaks no length.

### Affected files
`lib/offlineCrypto.ts` (REWRITE), `lib/db.ts` (add `manager_policies` store), `app/pos/ManagerApprovalDialog.tsx`, `tests/test_m10_hardening.py` (T25), `lib/offlineCrypto.test.ts` (H19).

---

<a id="c3"></a>
## 3. sessionStorage Active Cart Volatility on Browser Crash

### Critique
§7.6.2 moved `activeCart` to `sessionStorage` (fixes multi-tab clobber) but made it volatile to browser crash / power loss — common on 4 GB RAM edge thin clients. An 18-line prescription cart vanishes with no recovery. Net-negative trade.

### Refinement
Keep tab isolation, move **durability** to `localStorage`, keyed by a per-tab UUID so tabs never collide. `heldTickets` stays shared (`localStorage pos_held_v1`).

- `tabId = getTabId()` (defensive polyfill, §A.1: `crypto.randomUUID()` in secure contexts; `Math.random()`+`Date.now()` fallback under plain HTTP so `isSecureContext===false` never throws).
- Cart persisted to `localStorage["pos_activecart_tab_{tabId}"]`; meta with `last_write` ts to `localStorage["pos_activecart_meta_{tabId}"]`.
- `hydrate()` scans `pos_activecart_meta_*` with `last_write > now − 4h` and `tabId ≠ current` → non-blocking "Unsaved drafts — restore?" toast (30 s auto-dismiss; deep-merge + stock re-validate).
- Stale >4 h drafts GC'd in `persist()` sweep (bounds storage; no `beforeunload` reliance).

### Tests
- **H20:** `test_cart_survives_browser_restart` — persist → rehydrate same `tabId` from localStorage.
- **H21:** `test_unsaved_drafts_recovery_prompt` — planted stale tab key → recovery candidate emitted → deep-merge.
- **H22:** `test_no_cross_tab_clobber` — Tab A (AAA) + Tab B (BBB) write independent keys; heldTickets still shared.

### Affected files
`stores/posStore.ts`, `lib/storagePersist.ts` (`RECOVERY_WINDOW` + `sweepStaleTabs`), `app/pos/page.tsx` (recovery toast), `stores/posStore.test.ts` (H20–H22).

---

<a id="c4"></a>
## 4. Expired Lot Handling During Offline Replay (410 vs 400)

### Critique
§4.5 maps `400 → retry(3)` and `410 → discrepancy`. But an **expired lot** during replay is a *server-side inventory-state* condition masquerading as a generic `400`. The validator raises `ValidationError` → 400 → 3 futile retries (lot stays expired) → dead-lettered into `failed_queue` with **no DiscrepancyPanel surfacing**. Real, resolvable discrepancies are masked. The flaw: state-vs-payload error-class conflation.

### Refinement
Promote lot/batch state failures to a typed `410 Gone` with a structured `reason`; extend §4.5 routing — malformed payloads stay `400 retry`.

**Exception hierarchy** (`app/core/exceptions.py`):
```python
class StockStateError(HTTPException):            # 410 Gone
    def __init__(self, reason: str, details: dict):
        super().__init__(status_code=410, detail={"reason": reason, **details})
class ExpiredLotError(StockStateError):  ...      # reason="LOT_EXPIRED"
class RecalledLotError(StockStateError):  ...    # reason="LOT_RECALLED"
class MissingLotError(StockStateError):   ...    # reason="LOT_MISSING"
```
In `inventory_service.allocate()` / `PosService.checkout`: `ValidationError` → 400; any `*LotError` → raise `StockStateError` → FastAPI emits `410` with body `{ reason, lot_number, expires_at?, suggestion }`.

**§4.5 sync-loop extension:**
```
├─ 410 → failed_queue, offline_txns.status='discrepant', reason=<body.reason>
│        → DiscrepanciesPanel grouped by reason (LOT_EXPIRED|RECALLED|MISSING)
│        → actions: Re-pick lots (FEFO) | Restock | Manager override (token)
├─ 400 → retry max 3 (genuine client validation error) → then failed_queue
```
> Rename `offline_txns.status='over_sold'` → `'discrepant'` + `reason` column (backfill `'over_sold'`). Keeps the exact-once client_txn_id semantics (never retried on 410; resolved by a manager).

### Tests
- **T26:** expired-lot replay → 410, `reason=LOT_EXPIRED`, status `discrepant`, NOT retried.
- **T27:** recalled lot → 410 → DiscrepanciesPanel surfaces it (count increments).
- **T28:** malformed payload (dropped client_txn_id) → 400 → retried 3× → failed (ensures 410 class isn't broadened).

### Affected files
`app/core/exceptions.py`, `app/services/inventory_service.py` / `pos_service.py`, `app/api/routers/pos_route.py`, `lib/offlineQueue.ts` (`markDiscrepant` + `reason`), `app/pos/DiscrepanciesPanel.tsx`, `tests/test_m10_hardening.py`.

---

<a id="c5"></a>
## 5. Web Locks API Compatibility — Fallback for Legacy Edge Hardware

### Critique
§14.2 mandates `navigator.locks.request(...)`. Correct on modern Chromium. **Fatal** on legacy embedded WebViews / Qt WebEngine / old WebView2 where `navigator.locks` is `undefined` → `TypeError` in the `online` handler → **silent permanent replay halt** (parked txns never sync until manual restart). Silent + uncorrected = critical availability defect on the least-troubleshot hardware.

### Refinement
Three-tier progressive enhancement with stale-lock recovery:

| Tier | API | Notes |
|---|---|---|
| 1 (preferred) | `navigator.locks.request(id, {steal:true})` | robust, auto-releases |
| 2 (fallback) | `BroadcastChannel` mutex | heartbeat every 5 s; steal after 30 s silence |
| 3 (universal) | `localStorage` timestamp lock | reclaim if `ts < now − 30s` |

All tiers wrap `executeSyncLoop()` in `try/finally` (always release). `syncOfflineQueueWithLock()` auto-selects. Staleness window = 30 s bounds outage on a crashed holder.

### Tests
- **T29:** mock `navigator.locks=undefined, BroadcastChannel=undefined` → falls to localStorage tier; `executeSyncLoop` still runs exactly once.
- **H23:** planted stale localStorage lock (40 s old) → contender reclaims; fresh lock (5 s) not reclaimed.

### Affected files
`lib/syncLock.ts` (NEW), `lib/offlineQueue.ts` (re-export `syncOfflineQueueWithLock`), `stores/posStore.test.ts`.

---

<a id="c6"></a>
## 6. Offline PIN Lockout — Prevent DoS During ISP Outages

### Critique
The §2 refinement and the original addendum both risk a **self-wipe under a low threshold** (3 failed attempts) when the manager is legitimate but offline during an ISP outage (e.g., repeatedly mistyping under pressure). A wipe at 3 strikes **permanently cripples offline override** — the worst outcome precisely when the manager needs it most. The wipe must be reserved for *attacker-grade* exhaustion, not *operator error* during an outage.

### Refinement
**Tiered, time-based lockout** — cooldowns absorb operator error; wipe only after sustained attack.

| State | Condition | Behavior |
|---|---|---|
| Normal | `failure_count < 5` | wrong PIN → `failure_count += 1`, return `false` |
| Cooldown | `failure_count >= 5` (consecutive) | set `locked_until = now + 300s` (5 min) in `localStorage["pos_pin_lock_{username}"]`; wrong/correct attempt → return `Locked` ("try again in N min"); attempts do **not** increment during lockout |
| Wiped | total `failure_count >= 10` (across cooldowns) | **delete** policy blob → forces online re-auth |
| Reset | correct PIN (offline) **or** any online `verify-pin` success | `failure_count = 0`, `locked_until = 0`, clear `localStorage` lock entry, fresh `valid_until` |

**Why this is DoS-safe:** an operator who mistypes 2–3× during a brief outage hits at most the 5-minute cooldown (recoverable with no connectivity). An attacker brute-forcing a 6-digit PIN hits the 5-min wall after 5 guesses (10⁶ ÷ 5 × 5 min ≫ age of universe at 100% CPU). The wipe at 10 cumulative failures is the *escape hatch* — it only triggers after sustained attack, not operator error.

**Persistence:** `failure_count` + `locked_until` live in the **encrypted IndexedDB** `manager_policies` row (same AES-GCM blob as the PIN hash — no extra plaintext store); `locked_until` is also mirrored to `localStorage` so a browser crash mid-cooldown preserves the remaining wait.

### Tests
- **T30:** 5 wrong PINs → `Locked(300s)`; correct PIN during lockout → still `Locked` (no increment); after 300 s → counter resets, correct PIN succeeds.
- **H24:** 10th cumulative wrong → policy blob deleted (assert `db.get → undefined`); subsequent offline attempt → `requires_online`.

### Affected files
`lib/offlineCrypto.ts` (lockout state machine), `lib/db.ts`, `app/pos/ManagerApprovalDialog.tsx` (render `Locked` with countdown), `tests/test_m10_hardening.py` (T30), `lib/offlineCrypto.test.ts` (H24).

---

<a id="c7"></a>
## 7. Clock Drift vs FIFO Replay — Lamport Logical Clock

### Critique
§7.7 FIFO replay sorts by `parkedAt` (client epoch ms). An edge kiosk whose **OS clock drifted** (common on CMOS-battery failure, manual date change, or NTP panic) produces `parkedAt` values that are non-monotonic relative to real insertion order: a txn created "later" can get a smaller timestamp → replayed **out of order**, breaking real-time sequence integrity. Server-side drift detection (§14.4) catches *forward* skew at sync, but says nothing about ordering **during** offline accumulation. Relying on epoch ms for causal order is the defect.

### Refinement
Add a **device-local monotonic logical clock** (Lamport timestamp) as the authoritative FIFO sort key. `parkedAt` stays for UI/diagnostics only.

**Mechanism:**
- New column `offline_txns.local_seq: bigint` (monotonic, NOT epoch). `QueuedTxn.local_seq` too.
- **Counter source:** persisted in `localStorage["pos_local_seq"]` (survives reload/crashes across tabs on the same device). **Re-seed guard:** on hydration (first boot after a storage reset or OS clock drift) the seed is computed as `initial_seq = max(Date.now(), max_local_seq_persisted_in_IndexedDB) + 1`. This prevents a monotonic violation where a drifted/rollback `Date.now()` (e.g. CMOS-battery reset to 2020) would otherwise seed the counter *below* an already-emitted `local_seq`, producing descending sequences. The persisted high-water mark is read from IndexedDB so it survives `localStorage` wipes that do **not** also clear IndexedDB; if both are absent (first install), the seed defaults to `Date.now() + 1`. After seeding, the counter is strictly incrementing.
- **Lamport rule per enqueue (offline):** `local_seq = max(localSeq, broadcastMax) + 1`.
- **Cross-tab broadcast:** a `BroadcastChannel("pos_seq_clock")` posts every increment; sibling tabs apply `take max, +1` so even same-device concurrent tabs preserve monotonic order.
- **Replay sort:** `peekOrdered()` sorts by `local_seq ASC` (not `parkedAt ASC`). Deterministic regardless of OS clock.
- On successful sync, the server echoes back a `server_seq` ack so a future "merge multi-kiosk" scenario could total-order by `(kiosk_id, local_seq)` — noted as future work (§14 future), not implemented now (single-kiosk edge per §3.4).

This neutralizes CMOS-battery resets, manual date edits, and NTP slew during offline accumulation. The counter is per-device — acceptable because the deployment is single on-box SQLite per §3.4.

### Tests
- **T31:** `test_fifo_order_under_clock_drift` — mock `Date.now()` to jump backwards (−10 min) between enqueues; `local_seq` still strictly increasing; `peekOrdered()` returns insertion order.
- **H25:** `test_lamport_cross_tab` — two `usePosStore` tabs sharing a BroadcastChannel; enqueues interleave; both observe a monotonic union of `local_seq`.
- **H26:** `test_crash_preserves_local_seq` — increment counter, "crash" (drop in-memory state), rehydrate from `localStorage` → counter continues from last persisted value (no regression).
- **H27:** `test_lamport_reseed_guard` — persist `local_seq` high-water mark 5000 in IndexedDB; mock `Date.now()` to return a value below 5000 (e.g. CMOS reset to 2020); after reseed, `initial_seq = max(now, 5000) + 1 = 5001` → first enqueue `local_seq = 5002`; the sequence is strictly increasing (no regression below the persisted high-water mark).

### Affected files
`lib/offlineQueue.ts` (`QueuedTxn` + `local_seq`, `peekOrdered` sort key), `lib/syncLock.ts` (BroadcastChannel seq broadcaster), `lib/db.ts` (`local_seq` high-water mark in IndexedDB for the re-seed guard), `app/core/models.py` (migration: `local_seq` column + backfill from `rowid`), `tests/test_m10_hardening.py` (T31), `lib/offlineQueue.test.ts` (H25–H26).

---

<a id="c8"></a>
## 8. SQLite Read/Write Contention During Reporting

### Critique
Single-worker + WAL + `busy_timeout=5000` (§3.4) is correct for **writes**, but end-of-day inventory reports are **long-running reads** (~10–30 s full-drug SELECTs). Under WAL, readers get a snapshot at `BEGIN` and **do not block the writer** for the read itself — but a very long read can delay the WAL `checkpoint`/`autocheckpoint` cycle, inflating the WAL file and, in pathological cases, forcing the writer to wait on a checkpoint. More concretely: if a report connection holds a SHARED lock snapshot during a heavy write burst, the write connection's `wal_checkpoint` can see `SQLITE_BUSY` and stall checkout commits — the critical-path `POST /pos/checkout` is blocked by a *report*.

### Refinement
**Decouple reporting reads from the checkout write connection** via a dedicated read-only connection plus query-only mode + background scheduling.

- **Dedicated RO replica connection** (per FastAPI worker): `sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)` — the `mode=ro` URI makes the connection read-only at the SQLite layer (it cannot take any write lock, ever). Attach with `PRAGMA busy_timeout=30000` (reports tolerate waiting) and `PRAGMA query_only=ON` (belt-and-suspenders — no statement can mutate).
- **`POST /pos/checkout` stays on the write connection** (already single-worker §3.4, `session.begin()` minimized — validation/allocation outside, stock UPDATE + receipt INSERT inside one short txn). Checkout holds the write lock for ~ms, never blocks on a reader.
- **Reports run as background tasks:** `asyncio.create_task(run_report(...))` on the RO connection so the request thread returns immediately — the API worker stays responsive for checkout even if a report runs 30 s. If `SQLITE_BUSY` is observed on the RO connection (WAL checkpoint contention), retry with exponential backoff (cap 30 s); never propagate to the checkout path.
- **End-of-day full audit path (heaviest):** use a `VACUUM INTO` copy-on-open snapshot (§14.1) read once, so the report never touches the live WAL. Run it in an **idle-I/O subprocess** with a `snapshot_in_progress` guard (§A.3) so checkout commits are never starved on edge hardware.

**Net invariant:** a reader (report) can never block a writer (checkout). At worst a report sees a slightly stale snapshot — acceptable for reporting, never for stock decrement.

### Tests
- **T32:** `test_report_does_not_block_checkout` — spawn a long-running RO report SELECT (sleep 5 s inside transaction on RO conn) + concurrent `POST /checkout` → checkout commits successfully (assert receipt row exists + stock decremented) while report holds its snapshot.
- **T33:** `test_checkout_busy_timeout_not_increased` — assert checkout write path `busy_timeout` remains 5 000 ms (not raised); report connection `busy_timeout` is 30 000 ms.
- **H28:** `test_ro_connection_rejects_write` — `mode=ro` connection attempting `INSERT` → `sqlite3.ReadOnly` error (proves reports can't block writes by accidentally mutating).

### Affected files
`app/core/database.py` (add `read_replica` connection factory: `mode=ro` + `query_only` + `busy_timeout=30000`), `app/services/report_service.py` (use RO conn + `asyncio.create_task` + backoff retry), `app/api/routers/pos_route.py` (shift-close / report endpoints use RO), `tests/test_m10_hardening.py` (T32/T33), `tests/conftest.py` (H28 fixture).

---

<a id="matrix"></a>
## 9. Unified Summary Matrix

| # | Subsystem | Risk | Refinement | Key invariant preserved |
|---|---|---|---|---|
| 1 | Shift close | False −\$ variance from untracked cash drops/paid-outs | `drawer_movements` journal; `expected = float + Σtenders + Σfloat_add − Σ(drops+paid_out+pickup)` | 410 discrepancy stays the over-sell signal |
| 2 | Offline PIN | <10 ms console brute-force | PBKDF2-HMAC-SHA256 (env-calibrated, default 200 k via `POS_OFFLINE_PIN_KDF`) + constant-time compare + <150 ms calibration gate (§13) | token still `offline:true` + audit-flagged; ≥120 k floor |
| 3 | Cart state | Total loss on crash/power-off | `localStorage` keyed by per-tab UUID + 4 h recovery prompt + GC | `heldTickets` still shared cross-tab |
| 4 | Offline replay | Expired lot dead-lettered as 400 retry | Typed `StockStateError` → 410 `reason`; malformed still 400-retry | exact-once `client_txn_id`; 410 drains queue |
| 5 | Sync lock | Silent permanent halt on legacy WebViews | WebLocks → BroadcastChannel → localStorage (30 s stale-reclaim) | single replay per `online` event |
| 6 | Offline PIN lockout | Wipe at 3 → DoS during ISP outage | Tiered cooldown (5-attempt → 5 min → wipe at 10) | brute-force ≫ age of universe |
| 7 | FIFO ordering | Out-of-order replay under clock drift | Lamport `local_seq` counter (BroadcastChannel) sorts replay **+ re-seed guard `initial_seq=max(Date.now(),max_local_seq_in_IndexedDB)+1` (§7)** | `parkedAt` demoted to diagnostics only; counter never regresses below persisted high-water mark |
| 8 | SQLite reads | Report blocks checkout commit | Dedicated `mode=ro` + `query_only` + background-task reports | checkout stays 5 s busy_timeout; writes never block on reads |
| 9 | VACUUM / deployment | `sqlite3`/`caddy` not on thin-client `%PATH%` | `sqlite3.exe` + `caddy.exe` + `nssm.exe` vendored in `C:\PharmacyPOS\bin\` (§13); `sqlite3` resolved by service `AppDirectory`, zero `%PATH%` required | `VACUUM INTO` + reverse proxy run with no system PATH dependency |

---

<a id="rollout"></a>
## 10. Migration & Rollout Path (additive, backward-compatible)

- **No reopening of historical shifts** (Concern 1): pre-migration shifts yield `Σ outflows = 0` → `expected` reduces to prior formula → `variance` unchanged.
- **Schema additions** (Concern 4 + 7 + B.4 + B.7 + B.8): `ALTER TABLE offline_txns ADD COLUMN reason TEXT` (nullable, backfill `'over_sold'`), `ADD COLUMN local_seq BIGINT` (backfill from rowid order), `ADD COLUMN server_created_at DATETIME / client_created_at DATETIME / ts_skew_confidence TEXT` (B.7), new `drawer_movements` table + cashier-attribution columns (`created_by`, `cashier_attribution`) on `offline_txns`/`receives`/`drawer_movements` (B.9), `settings` meta-table for `snapshot_in_progress`/`snapshot_created_at` (A.3/B.1). **No Alembic on kiosks** — all DDL ships as the app-owned `run_migrations()` `user_version` loop (B.8), applied on first boot from `user_version=0`; migrations are idempotent + transactional.
- **Feature flags:** `POS_OFFLINE_PIN_KDF` (PBKDF2 iters, default 200 000, env-calibrated per §13), `POS_PIN_FAILURE_LOCK_THRESHOLD` (5), `POS_PIN_WIPE_THRESHOLD` (10), `POS_LOCKOUT_COOLDOWN_MS` (300 000), `POS_LAMPORT_SEQ=1`, `POS_REPORT_RO_CONNECTION=1`, `POS_TS_SKEW_THRESHOLD_SEC` (300, B.7), `POS_SYNC_BATCH_SIZE` (10) + `POS_SYNC_YIELD_MS` (250, B.10), `POS_ENABLE_HSTS=0`, `POS_VACUUM_CLI_MISSING` (auto-metrics; §A.3).
- **Storage migration (B.6):** first-run migrates any pre-existing `localStorage["pos_activecart_tab_*"]` / `pos_held_v1` into IndexedDB `pos_store.carts` + `seq_highwater`; post-migration, IndexedDB is the durable source-of-truth and `localStorage` is a cache.
- **Operational tuning**: KDF 200 k iters tuned for 2018 Celeron (~120 ms, <150 ms gate, §2/§13); sync batch 10/250 ms default for 4 GB kiosks; VACUUM idle-priority via vendored `bin\sqlite3.exe`; lockout cooldown 5 min default; `STALENESS_SNAPSHOT_SEC` 4 h; retention 7 d (`SNAPSHOT_RETENTION_SEC=604800`).
- **Kiosk fleet**: deploy Web Locks fallback (§5) + IndexedDB storage (B.6) to a single legacy terminal in staging first; the tier chain auto-adapts. NSSM `DependOn` (B.2) ships in the same image.

---

<a id="files"></a>
## 11. Affected Files Index (consolidated)

| Area | Files (new = CREATE, existing = EDIT, rewrite = REWRITE) |
|---|---|
| Backend models | `app/core/models.py` EDIT (DrawerMovement + enum §1; `local_seq`/`reason` §4/§7; `server_created_at`/`ts_skew_confidence` B.7; cashier `created_by`/`cashier_attribution` B.9); `app/core/lock_manager.py` EDIT (drawer-movement lock-order audit) |
| Exceptions | `app/core/exceptions.py` EDIT (StockStateError hierarchy §4 + OfflinePinLockedError §6) |
| DB / sync | `app/core/database.py` EDIT (read-replica `mode=ro` §8 + VACUUM guard/settings §A.3; `run_migrations()` B.8; `SNAPSHOT_RETENTION_SEC`; sync metrics B.10); `app/services/inventory_service.py` EDIT (`allocate()` raises typed lot errors §4) |
| Services | `app/services/pos_service.py` EDIT (410 mapping §4 + cashier token B.9 + `asyncio.to_thread` B.5); `app/services/report_service.py` EDIT (RO conn + bg task §8; `shutil` precheck + retention A.3/B.1; server-time grouping B.7) |
| Routes | `app/api/routers/pos_route.py` EDIT (drawer-movement §1; 410/StockStateError §4; `X-Cashier-Token` B.9; `server_created_at` B.7); `auth_route.py` EDIT (verified-pin → encrypted policy + cashier session token §2/B.9) |
| Frontend crypto | `lib/offlineCrypto.ts` REWRITE (PBKDF2 Web Worker + `POS_OFFLINE_PIN_KDF` §2/B.3 + tiered lockout §6); `lib/db.ts` EDIT (`manager_policies` §2 + `carts`/`seq_highwater`/sessions B.6/B.9) |
| Frontend state | `stores/posStore.ts` REWRITE (per-tab `sessionStorage` id + `localStorage` per-tab cart + cross-tab sync §3/§7; quota try/catch + IndexedDB reconcile B.6; lockout render §6); `lib/storagePersist.ts` EDIT (RECOVERY_WINDOW + `sweepStaleTabs`) |
| Offline queue | `lib/offlineQueue.ts` REWRITE (Lamport `local_seq` FIFO §7 + B.10 `dequeue(limit)`/batched `syncOfflineQueueWithLock`; `markDiscrepant`+`reason` §4) |
| Sync lock | `lib/syncLock.ts` CREATE (3-tier lock §5) |
| UI | `app/pos/ManagerApprovalDialog.tsx` EDIT (lockout countdown §6); `app/pos/ShiftCloseDialog.tsx` EDIT (drawer-movement + variance §1); `app/pos/DiscrepanciesPanel.tsx` EDIT (reason grouping §4); `app/pos/page.tsx` EDIT (recovery toast §3) |
| Types | `types/contracts.ts` EDIT (DrawerMovementType, StockStateError reason, ManagerPolicy, LockedState) |
| Tests | `tests/test_m10_hardening.py` EDIT (T23–T28, T30, T31, T32–T33, T34–T48); `lib/offlineCrypto.test.ts` EDIT (H19, H24, H34–H35); `stores/posStore.test.ts` EDIT (H29–H31, H38–H39); `lib/offlineQueue.test.ts` EDIT (H25–H27); `tests/lint_sync_cpu.test.ts` CREATE (H36); `tests/policies.test.ts` CREATE (H37). |
| Config | `run_services.py` / `Dockerfile` EDIT (single worker confirmed); `.env` additions for feature flags |
| Appendix A | `stores/posStore.ts` ADD `getTabId()` + B.6 quota try/catch + IndexedDB cart/seq reconcile (A.1/B.6); `app/core/database.py` EDIT RO replica + VACUUM guard + `SNAPSHOT_RETENTION_SEC` + `run_migrations()` (B.8) + sync metrics (B.10); `app/services/report_service.py` EDIT staleness gate + `shutil` precheck + 7-day retention (A.3/B.1); `lib/db.ts` EDIT manager_policies + carts/seq/session stores (§2/B.6/B.9); `lib/offlineCrypto.ts` REWRITE PBKDF2 Web Worker + `POS_OFFLINE_PIN_KDF` (§2/B.3); `app/core/models.py` EDIT `server_created_at`/`ts_skew_confidence` (B.7) + cashier `created_by`/`cashier_attribution` (B.9) + `local_seq`/`reason` (§4/§7); **new** `Caddyfile` (A.2), `docs/edge_tls.md` (A.2), `deployment/policies.json` (B.4), `setup.iss` + `install.ps1` (§13/B.2/B.4); tests T34–T48, H29–H33, H34–H39 → see [A.4 Affected Files (extension deltas)](#a4). |
| Appendix B | `install.ps1` EDIT (NSSM `DependOn` ordering + `.env` load + Firefox CA policy); **new** `setup.iss` (Inno, bundles `bin/{nssm,caddy,sqlite3,node}.exe` + pre-populated `.venv` + Next.js standalone + `Caddyfile` + `install.ps1`), `frontend/next.config.mjs` (`output:"standalone"`), `backend/requirements-freeze.txt`, `lib/offlineCryptoWorker.ts`, `lib/offlineCrypto.bench.ts`, `docs/hardening_calibration.md`, `tests/lint_sync_cpu.test.ts`, `tests/policies.test.ts`; `lib/offlineCrypto.ts` REWRITE (Web Worker + `POS_OFFLINE_PIN_KDF`). |

---

<a id="validation"></a>
## 12. Validation Pipeline (exact commands)

**Backend** (`backend_fastapi/`):
```bash
.venv\Scripts\python -m pytest tests/test_m10_hardening.py -q
  -> expected: T1–T55 pass, incl. T23–T28 (drawer/410), T30 (lockout DoS),
     T31 (Lamport FIFO), T32–T33 (RO read/write separation), T34 (VACUUM-vs-checkout),
     T35/T36 (VACUUM space + retention §B.1), T37/T38 (NSSM deps §B.2),
     T39 (Firefox policy §B.4), T40 (asyncio.to_thread §B.5),
     T41/T42 (timestamp skew §B.7), T43/T44 (migrations §B.8),
     T45/T46 (cashier attribution §B.9), T47/T48 (sync throttle §B.10),
     T49–T51 (multi-terminal merge-sync §C.1), T52 (granular OTA §C.2),
     T53 (RAM caps §C.3), T54/T55 (PIN peppering §C.4).
ruff check .
  -> expected: 0
.venv\Scripts\mypy --strict .
  -> expected: 0
```

**Frontend**:
```bash
npx prettier --check "app/**/*.{ts,tsx}" "lib/**" "stores/**" "types/**" "hooks/**"
  -> expected: 0 files needing rewrite
npx tsc --noEmit
  -> expected: 0 errors (strict)
npx vitest run lib/decimalCurrency.test.ts lib/offlineCrypto.test.ts stores/posStore.test.ts lib/offlineQueue.test.ts tests/policies.test.ts tests/lint_sync_cpu.test.ts
  -> expected: H19–H39 pass  (H34/H35 PBKDF2 worker §B.3; H36 sync-CPU audit §B.5; H37 Firefox schema §B.4; H38/H39 localStorage→IndexedDB §B.6)
```

**Post-deploy smoke** (live kiosk):
1. Mid-shift safe-drop \$150 → shift close → `variance ≈ 0` (Concern 1).
2. Offline PIN wrong 5× → 5-min lockout toast; wrong 10× cumulative → policy wiped + "requires online re-auth" (Concern 6).
3. Park 3 txns with OS clock set 10 min back → replay order matches insertion, not `parkedAt` (Concern 7).
4. Run full inventory report during a checkout surge → checkout still <200 ms; report uses RO connection (Concern 8).
5. Kill `navigator.locks` on a legacy terminal profile → sync still runs via localStorage tier (Concern 5).
6. Park txn on expired lot at server time → replay → 410 `reason=LOT_EXPIRED` surfaced in DiscrepanciesPanel (Concern 4).
7. **Network resilience (Appendix A):** open `http://<ip>:3000` (no Caddy) → `getTabId()` returns `tab_…` (no throw) + checkout works; open `https://pharmacy.local` (Caddy TLS) → `isSecureContext===true` + UUID v4; kill Caddy → `http://…` still serves full app.
8. **VACUUM I/O (A.3):** trigger shift close → idle-priority `VACUUM INTO` runs + p95 checkout during VACUUM < 500 ms; `snapshot_in_progress` toggles; reports reuse 4 h stale snapshot.
9. **Appendix B (hardening):** (B.1) free disk < db×2.5 → VACUUM aborted + `POS_VACUUM_SPACE_ABORT` fires; snapshots older than 7 d auto-removed from `data\`; (B.2) `nssm status PharmacyCaddy` is `STOPPED` until `PharmacyBackend`+`PharmacyFrontend` are `RUNNING`; (B.3) offline PIN verify resolves without main-thread jank (worker trace in console); (B.4) `https://pharmacy.local` loads with **trusted** cert in Chromium **and** Firefox `policies.json` present at `C:\Program Files\Mozilla Firefox\distribution\`; (B.5) `GET /reports` during a receipt-render burst → checkout latency flat (render on a worker thread).
10. **Appendix B (operational/edge):** (B.6) force `localStorage` `QuotaExceededError` → cart + Lamport seq migrate to IndexedDB, checkout still works; (B.7) backdate a kiosk clock 30 min, complete an offline txn, reconnect → receipt stamped `server_created_at` (not the skewed client time), `ts_skew_confidence='low'`, no fiscal-period shift; (B.8) wipe `pharmacy.db`, boot kiosk → `run_migrations()` brings `user_version` to current + all tables present; (B.9) two cashiers on one shift → each drawer movement + txn row lists the individual `created_by`, not the shift; (B.10) park 200 txns, reconnect → sync drains in ≤10-txn batches with yields, checkout p95 < 200 ms throughout.
11. **Appendix C (scale/harden):** (C.1) two terminals sell the same last lot unit concurrently → hub tags both `OVER_SOLD_CROSS_TERMINAL` + inventory matches physical count; (C.2) push a 1-byte backend change → only `backend/app/` layer re-fetched, sha256 verified, atomic swap, kiosk still serving; (C.3) 200-checkout storm on a 4 GB kiosk → Node RSS ≤ 1.05 GB, Browser ≤ 1.35 GB, no pagefile growth; (C.4) exfiltrate `(salt, pin_hash, pepper_blob)` to a different machine → `verifyPin(correct_PIN)` fails (pepper unrecoverable), brute-force can't confirm any PIN.

---

<a id="build"></a>
## 13. Build, Packaging & Deployment Automation (Low-Spec Windows)

> **Goal:** A fully offline-capable, single-machine deployment targetted at 4 GB RAM thin clients / terminal servers, with **no Docker/WSL2 dependency** and **no system `%PATH%` requirement** for the runtime. Optimized for resource-constrained Windows hardware.

### Deployment layers (ordered)

```
Inno Setup (.exe installer)   →   install.ps1 (PowerShell bootstrap)   →   Windows Services (NSSM)
        ↑                                              ↑                          ↑
    bundles files      DNS/hosts + Caddy trust +      registers 3      long-running daemons:
    into C:\PharmacyPOS\   service registration       services        PharmacyCaddy/Backend/Frontend
```

1. **Inno Setup** (`setup.iss`) — builds the distributable `.exe`. Bundles the Next.js standalone build, the FastAPI `.venv` + wheels, the vendored binaries (`bin/`), and runs `install.ps1` silently at the end of install. Single self-extracting `.exe` is the only artifact handed to the operator.
2. **PowerShell Bootstrap** (`install.ps1`) — runs **once** at install time with admin rights. Performs DNS/hosts configuration, Caddy root-CA trust, and registers the three NSSM services. It is idempotent (re-runnable for repair).
3. **Windows Services via NSSM** — the actual runtime. NSSM wraps each process as a true Windows service (auto-restart on crash, centralized stdout/stderr capture into `logs/`). Survives user logoff / headless kiosks.

### Target directory layout (`C:\PharmacyPOS\`)

```
C:\PharmacyPOS\
├── bin\
│   ├── nssm.exe        # service manager (vendored — no system PATH needed)
│   ├── caddy.exe       # reverse proxy / local TLS (vendored)
│   └── sqlite3.exe     # VACUUM INTO snapshot CLI (vendored — drives §A.3)
├── backend\
│   ├── .venv\          # pre-populated virtualenv: ALL wheels bundled for offline install
│   │   └── (site-packages + Scripts)
│   └── app\            # FastAPI source (app/main.py, core, services, api)
├── frontend\
│   ├── .next\          # Next.js 16 standalone build output
│   └── server.js       # standalone Node server entry (no `next` CLI at runtime)
├── Caddyfile           # Caddy config (local TLS, reverse_proxy to backend/frontend)
├── data\               # pharmacy.db, snapshots, manager_policies blobs
├── logs\               # PharmacyCaddy.log / PharmacyBackend.log / PharmacyFrontend.log (stdout+stderr)
└── install.ps1         # (also copied here at install for repair re-runs)
```

**Vendored binaries rule:** `sqlite3.exe` and `caddy.exe` are explicitly staged in `bin/` (not `%PATH%`). This guarantees `VACUUM INTO` (§A.3) and reverse-proxying work on a standard Windows thin-client image with *no* system PATH entry — the service `AppDirectory`/`WorkingDirectory` is set to `C:\PharmacyPOS\bin` so `caddy.exe`/`sqlite3.exe`/`nssm.exe` resolve by relative path.

### Service management (NSSM registration)

Three services, registered by `install.ps1` via `bin\nssm.exe`:

| Service | Runs | Bind | Purpose |
|---|---|---|---|
| `PharmacyCaddy` | `bin\caddy.exe run --config C:\PharmacyPOS\Caddyfile` | `:443` / `:80` | reverse proxy + local TLS (`tls internal`) |
| `PharmacyBackend` | `backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` | `127.0.0.1:8000` | FastAPI (single worker, §3.4) |
| `PharmacyFrontend` | `bin\node.exe frontend\server.js` (standalone) | `127.0.0.1:3000` | Next.js standalone server |

- Each registered with `nssm install <svc>` + `AppDirectory` set to its working dir + `AppStdout`/`AppStderr` redirected to `C:\PharmacyPOS\logs\<svc>.log` + `Start = SERVICE_AUTO_START` + `AppExit` default-action `restart` (crash recovery). **Startup order:** upstreams (`PharmacyBackend`, `PharmacyFrontend`) are registered first; `PharmacyCaddy` is registered last with `DependOn = PharmacyBackend PharmacyFrontend` (B.2) so NSSM never marks Caddy `RUNNING` until both loopback services are up — eliminating the kiosk-boot 502 window.
- `PharmacyBackend` and `PharmacyFrontend` bind loopback only; `PharmacyCaddy` is the sole public listener (Defense-in-Depth: no direct LAN access to backend/frontend ports).
- `nssm` also sets `AppEnvironment` so `PHARMACY_DB_URL`/`POS_OFFLINE_PIN_KDF`/`POS_ENABLE_HSTS` reach each service from `.env` read at install time.

### Packaging: Next.js (`frontend/next.config.mjs`)

```js
// next.config.mjs
/** @type {import('next').NextConfig} */
module.exports = {
  output: "standalone",   // §13: minimal footprint, single Node process at runtime
  outputFileTracingRoot: path.join(__dirname, ".."), // include backend .venv if co-located
  reactStrictMode: true,
  images: { remotePatterns: [] }, // no remote image hosts (offline kiosk)
};
```
Built via `npm run build` then `.next/standalone/` + `.next/server/` are copied wholesale into `frontend/`. At runtime the service executes `bin\node.exe frontend\server.js` — no `npm`/`next` install needed on the kiosk.

### Packaging: Python backend (`.venv` bundling)

- The installer's `.venv` is built **fully offline-capable**: `pip download` all transitive wheels (FastAPI, uvicorn, aiosqlite, SQLAlchemy, Caddy CLI deps, etc.) into a vendored wheel cache during the image-build stage, then `pip install --no-index --find-links <cache> -r requirements.txt` into `.venv`.
- `pip freeze` is recorded as a lockfile (`backend/requirements-freeze.txt`) and verified in CI (§13 validation) so the shipped `.venv` is byte-for-byte reproducible.
- The backend boots with `python -m uvicorn app.main:app --workers 1` (single Uvicorn worker, §3.4 invariant) reading `PHARMACY_DB_URL` from the service environment.

### `install.ps1` (definitive deployment workflow)

```powershell
# install.ps1  — runs elevated, idempotent.
param([string]$InstallDir = "C:\PharmacyPOS", [switch]$Repair)

$ErrorActionPreference = "Stop"

# 1. Hosts / DNS resolution (so https://pharmacy.local resolves to the on-box Caddy).
$hostLine = "127.0.0.1 pharmacy.local"
$hosts = "C:\Windows\System32\drivers\etc\hosts"
if (-not (Select-String -Path $hosts -Pattern "pharmacy\.local" -SimpleMatch -Quiet)) {
  Add-Content -Path $hosts -Value $hostLine
}

# 2. Load runtime env from .env so feature flags reach every service uniformly.
$envMap = @{}
if (Test-Path "$InstallDir\.env") {
  Get-Content "$InstallDir\.env" | Where-Object { $_ -match '\s*=' -and -not $_.StartsWith('#') } | ForEach-Object {
    $kv = $_ -split '=', 2
    if ($kv.Count -eq 2) { $envMap[$kv[0].Trim()] = $kv[1].Trim() }
  }
}

# 3. Caddy root-CA trust (one time; makes tls internal a trusted origin).
& "$InstallDir\bin\caddy.exe" trust 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning "Caddy CA trust failed — HTTPS will warn; HTTP fallback still works (§A.1)." }

# 4. Register the three NSSM services (idempotent via nssm status check), in dependency order:
#     upstreams first, then Caddy with DependOn (B.2) to avoid 502 on boot.
$services = @(
  @{ Name="PharmacyBackend"; App="$InstallDir\backend\.venv\Scripts\python.exe"; Args="-m uvicorn app.main:app --host 127.0.0.1 --port 8000"; Dir="$InstallDir\backend" }
  @{ Name="PharmacyFrontend"; App="$InstallDir\bin\node.exe"; Args="$InstallDir\frontend\server.js"; Dir="$InstallDir\frontend" }
  @{ Name="PharmacyCaddy";   App="$InstallDir\bin\caddy.exe"; Args="run --config $InstallDir\Caddyfile"; Dir="$InstallDir"; DependsOn=@("PharmacyBackend","PharmacyFrontend") }
)
$envBlock = ($envMap.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join " "
foreach ($svc in $services) {
  $exists = & "$InstallDir\bin\nssm.exe" status $svc.Name 2>$null
  if ($exists -ne "RUNNING") {
    & "$InstallDir\bin\nssm.exe" install $svc.Name $svc.App $svc.Args
    & "$InstallDir\bin\nssm.exe" set $svc.Name AppDirectory $svc.Dir
    & "$InstallDir\bin\nssm.exe" set $svc.Name AppStdout "$InstallDir\logs\$($svc.Name).log"
    & "$InstallDir\bin\nssm.exe" set $svc.Name AppStderr "$InstallDir\logs\$($svc.Name).log"
    & "$InstallDir\bin\nssm.exe" set $svc.Name Start SERVICE_AUTO_START
    & "$InstallDir\bin\nssm.exe" set $svc.Name AppExit Default ExitActions Restart
    if ($svc.DependsOn) { & "$InstallDir\bin\nssm.exe" set $svc.Name DependOn $svc.DependsOn }
    if ($envBlock) { & "$InstallDir\bin\nssm.exe" set $svc.Name AppEnvironment $envBlock }
  }
}

# 5. Start (or restart on repair) — NSSM honors DependOn, so Caddy starts last.
foreach ($svc in $services) {
  & "$InstallDir\bin\nssm.exe" restart $svc.Name 2>$null
}
Write-Host "PharmacyPOS services started. Browse to https://pharmacy.local"
```

### `setup.iss` (Inno Setup — packages the `.exe`)

```pascal
; setup.iss — single-file installer for C:\PharmacyPOS
[Setup]
AppName=PharmacyPOS
AppVersion={include:version.txt}
DefaultDirName=C:\PharmacyPOS
PrivilegesRequired=admin
DisableProgramGroupPage=yes
OutputBaseFilename=PharmacyPOS-Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "bin\nssm.exe";       DestDir: "bin"
Source: "bin\caddy.exe";     DestDir: "bin"
Source: "bin\sqlite3.exe";   DestDir: "bin"
Source: "bin\node.exe";      DestDir: "bin"
Source: "backend\.venv\*";   DestDir: "backend\.venv"  ; Flags: ignoreversion recursesubdirs
Source: "backend\app\*";     DestDir: "backend\app"
Source: "frontend\.next\*";  DestDir: "frontend\.next"
Source: "frontend\server.js"; DestDir: "frontend"
Source: "Caddyfile";         DestDir: "{autodir}"
Source: "install.ps1";       DestDir: "{autodir}"

[Dirs]
Name: "data"; Name: "logs"

[Run]
; install.ps1 runs elevated — performs hosts edit, Caddy CA trust, NSSM registration.
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{autodir}\install.ps1"""; Flags: runhidden

[Icons]
Name: "PharmacyPOS Admin"; Filename: "https://pharmacy.local"
```

The build image-build stage pre-populates `backend/.venv` (with the wheel cache) and produces `frontend/.next/standalone`; `setup.iss` simply packages both verbatim — **no network is required on the kiosk at install or runtime.**

### Build & release validation (staging gates)

```bash
# 1. Reproducible backend bundle (offline wheel cache)
python -m pip download -r backend/requirements.txt -d backend/_wheelcache --platform win_amd64 --only-binary=:all:
python -m venv backend/.venv && backend/.venv\Scripts\pip install --no-index --find-links backend/_wheelcache -r backend/requirements.txt
python -c "import fastapi, uvicorn, aiosqlite"   # smoke: bundled venv imports cleanly offline
pip freeze -r backend/requirements.txt > backend/requirements-freeze.txt  # lockfile pinned

# 2. Next.js standalone (zero runtime deps)
npm run build   # emits frontend/.next/standalone + frontend/.next/server
test -f frontend/.next/standalone/server.js
npx tsc --noEmit  # frontend type-check (strict)

# 3. External binaries present + on no PATH
ls bin/nssm.exe bin/caddy.exe bin/sqlite3.exe

# 4. PBKDF2 KDF calibration (§2/B.3): assert <150 ms at production iteration count on kiosk-class HW
python -c "import os; print('POS_OFFLINE_PIN_KDF=', os.environ.get('POS_OFFLINE_PIN_KDF','200000'))"
# then run lib/offlineCrypto.bench.ts against target HW and assert verifyPin_ms < 150

# 5. New feature flags present in .env (B.7/B.10) — gate missing config at build, not boot
for v in POS_TS_SKEW_THRESHOLD_SEC POS_SYNC_BATCH_SIZE POS_SYNC_YIELD_MS POS_LAMPORT_SEQ; do \
  python -c "import os,sys; assert os.getenv('$v'), 'missing $v in .env'"; \
done
```

---

<a id="appendix-a"></a>
## Appendix A — Network & Resource Resilience Extension

**Purpose:** Close two deployment-time risks that the core spec left open because they span the *network/terminal layer* rather than the application layer: (1) `crypto.randomUUID()` is gated behind `window.isSecureContext` and throws on plain-HTTP LAN access, breaking tab isolation; (2) `VACUUM INTO` snapshots spike disk/CPU on 4 GB thin clients and can stall the checkout hot path. All fixes follow the **defensive programming** directive: the app must remain fully functional on HTTP *and* HTTPS; HTTPS (via Caddy local TLS) is a quality-of-life upgrade that enables the full WebCrypto surface, but is **not** a runtime dependency.

---

<a id="a1"></a>
### A.1 Resilient `getTabId` Polyfill (`stores/posStore.ts`)

**Root cause:** `crypto.randomUUID()` is a Secure Context API. Accessing the POS via `http://192.168.1.15:3000` (typical thin-client LAN deployment) yields `window.isSecureContext === false` → `crypto.randomUUID()` throws `TypeError` → Concern 3's tab-id assignment fails → cart keys collide across tabs / recovery breaks.

**Refinement:** Replace the inline `crypto.randomUUID()` call with a `getTabId()` helper that feature-detects the secure context **and** the API surface, and falls back to a deterministic-but-unique token composed of timestamp + entropy + per-window counter.

```typescript
// stores/posStore.ts — append; re-exported for tests
const TAB_ID_KEY = "pos_tab_id";

// Feature-detect, do NOT assume crypto exists.
const isSecureUuidAvailable = (): boolean =>
  typeof crypto !== "undefined" &&
  typeof crypto.randomUUID === "function" &&
  typeof window !== "undefined" &&
  window.isSecureContext === true;

export const getTabId = (): string => {
  const existing = typeof sessionStorage !== "undefined" ? sessionStorage.getItem(TAB_ID_KEY) : null;
  if (existing) return existing;                          // stable per-tab across reloads

  let id: string;
  if (isSecureUuidAvailable()) {
    id = crypto.randomUUID();                           // UUID v4 — preferred path (HTTPS)
  } else {
    // Defensive fallback for plain-HTTP / legacy WebView contexts.
    // Entropy mix: epoch ms (62-bit base36) + two Math.random() draws + monotonic counter.
    // Collision probability across same-device tabs is negligible; same-tab is stable via sessionStorage.
    const ts = Date.now().toString(36);
    const r1 = Math.random().toString(36).slice(2, 10);
    const r2 = Math.random().toString(36).slice(2, 10);
    const win = window as unknown as { __tabIdSeq?: number };
    const ctr = (win.__tabIdSeq = (win.__tabIdSeq ?? 0) + 1);
    id = `tab_${ts}_${ctr}_${r1}_${r2}`;
  }
  sessionStorage.setItem(TAB_ID_KEY, id);
  return id;
};
```

**Consumption** (Concern 3 update): `const tabId = useMemo(getTabId, []);` — memo once per tab; `useEffect` writes active cart to `localStorage["pos_activecart_tab_" + tabId]`.

**Failure modes handled:**
- `crypto` entirely absent (old browser) → fallback.
- `crypto.randomUUID` present but `isSecureContext === false` (insecure origin) → fallback (feature-detect beats try/catch).
- `sessionStorage` quota exhausted → returns generated id for this session only (cart not persisted, but tab isolation still holds via the in-memory `tabId` const).

**Tests:**
- **H29:** `test_getTabId_stable_per_tab` — two calls in same mocked tab return identical id; `sessionStorage` was written once.
- **H30:** `test_getTabId_http_fallback` — mock `isSecureContext=false`, `crypto.randomUUID=undefined`; `getTabId()` returns `tab_…` form, does not throw, and two "tabs" (cleared sessionStorage between calls) produce distinct ids.
- **H31:** `test_getTabId_https_uuid` — `isSecureContext=true` + `crypto.randomUUID` returns UUID-v4-form `pos_tab_id` persisted.

---

<a id="a2"></a>
### A.2 Local TLS via Caddy Reverse Proxy (LAN kiosks)

**Objective:** Make `https://pharmacy.local` resolve to the on-box FastAPI+Next.js stack with a **trusted** local certificate, so `window.isSecureContext === true` and the *preferred* `crypto.randomUUID()` path is exercised. The application degrades gracefully if Caddy is absent (A.1 handles HTTP).

**Why Caddy:** zero-config local ACME alternative. Caddy's `internal` issuer emits self-signed certs and, with `caddy trust`, installs its root CA into the OS trust store once per kiosk — eliminating browser security warnings without public DNS/PKI.

**Deployment model (single on-box kiosk server, multiple thin-client browsers on LAN):** Caddy runs as the **`PharmacyCaddy` NSSM service** (§13) wrapping `bin\caddy.exe run --config C:\PharmacyPOS\Caddyfile` — no `caddy install` service is used (NSSM owns process lifecycle).
```
Client browsers (http)        → https://pharmacy.local   (PharmacyCaddy on the kiosk)
PharmacyCaddy terminates TLS  → reverse_proxy /api/*  → 127.0.0.1:8000  (PharmacyBackend, FastAPI)
                                reverse_proxy /       → 127.0.0.1:3000  (PharmacyFrontend, Next.js standalone)
```

**Caddyfile** (`C:\PharmacyPOS\Caddyfile`, staged by `setup.iss`, served by `PharmacyCaddy`):
```caddy
# Bootstrap (run once, admin, from install.ps1 / §13):
#   C:\PharmacyPOS\bin\caddy.exe trust   # installs Caddy's local root CA into the OS machine store
#   (service registration is handled by install.ps1 via NSSM — no `caddy install` needed)

pharmacy.local {
    tls internal              # local 10-year self-signed cert, trusted via the root CA above
    encode gzip
    @api path /api/*
    reverse_proxy @api 127.0.0.1:8000   # → PharmacyBackend (loopback)
    reverse_proxy 127.0.0.1:3000        # → PharmacyFrontend (loopback)
    header {
        # HSTS gated behind POS_ENABLE_HSTS (default off) — see best-practices below.
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "no-referrer-when-downgrade"
    }
}
```

**Local DNS / name resolution (pick one):**
- **Option A — `hosts` file (simplest, recommended for ≤8 kiosks):** on each thin client, append to `C:\Windows\System32\drivers\etc\hosts`:
  ```
  127.0.0.1  pharmacy.local
  ```
  (If the Caddy server is a *separate* box on the LAN, replace `127.0.0.1` with that box's LAN IP, e.g. `192.168.1.20`.)
- **Option B — mDNS:** `.local` is mDNS. If the Caddy host advertises `pharmacy.local` via `avahi-daemon`/`dnsmasq`/`bonjour`, no hosts edit needed — but Windows client mDNS support is patchy; prefer Option A for a pharmacy LAN.

**Best practices / hard-won details:**
- **Trust is per-OS, not per-browser.** `caddy trust` writes to the *Windows certificate store* (machine root). All browsers on the kiosk then trust `pharmacy.local` → no warnings. If you only import into a single browser's cert UI, other browsers still warn.
- **HSTS caution:** only enable `Strict-Transport-Security` after confirming HTTPS works end-to-end. On a kiosk where an operator might temporarily flip back to HTTP to troubleshoot, HSTS can brick the terminal for an hour. Gate HSTS behind a `POS_ENABLE_HSTS` env flag, default off until stabilized.
- **`caddy fmt` + `caddy validate --config C:\PharmacyPOS\Caddyfile`** in pre-deploy validation (`bin\caddy.exe`).
- **Renewal:** `tls internal` certs are 10-year local; no public ACME rate limits. Reload config live: `bin\caddy.exe reload --config C:\PharmacyPOS\Caddyfile` (NSSM keeps the process up; no service restart needed for config edits).
- **Defensive stance confirmed:** if `PharmacyCaddy` is stopped or not installed, the Next.js app is reachable raw over `http://<kiosk-ip>:3000` and `getTabId()` (A.1) keeps working — full feature parity except WebCrypto-only APIs fall back by design. `PharmacyBackend`/`PharmacyFrontend` are loopback-only, so stopping Caddy never exposes them on the LAN.

---

<a id="a3"></a>
### A.3 Edge-Hardware I/O Mitigation for `VACUUM INTO`

**Root cause:** `VACUUM INTO 'snapshot.sqlite'` reads the entire live DB and writes a full copy — single-threaded CPU + a sustained write burst. On a 4 GB RAM / eMMC thin client this competes with the WAL checkpoint that keeps checkout fast.

**Refinement — four complementary controls (applied together):**

1. **Idle-I/O isolation (primary mitigation).** Run `VACUUM INTO` as a **low-priority subprocess**, never inline on the FastAPI worker thread. This detaches VACUUM I/O from the checkout request thread entirely and the OS scheduler starves it when a checkout needs the disk.
   - Linux: `asyncio.create_subprocess_exec("ionice", "-c", "3", "-t", "5", "sqlite3", DB_PATH, "VACUUM INTO ?", snapshot_path, ...)` — `-c 3` = idle I/O class.
   - Windows thin client (the env): `start /low /wait /b bin\sqlite3.exe "DB_PATH" "VACUUM INTO 'snapshot_path'"` — `/low` = idle priority class. `sqlite3.exe` is **vendored in `bin/`** (§13) and resolved by the service's `AppDirectory = C:\PharmacyPOS`; **no system `%PATH%` entry is required.** If the vendored CLI is missing, fall back to an in-process background `asyncio.create_task` running `VACUUM INTO` on a *separate* SQLite connection — weaker isolation, but never on the request thread. Metric `POS_VACUUM_CLI_MISSING` fires so fleet health is observable.

2. **`.snapshot_in_progress` DB guard (anti-thundering-herd).** A boolean column on a `settings` meta-table (`snapshot_in_progress`, `snapshot_created_at`). On any report request: if `snapshot_in_progress OR snapshot_created_at > now − STALENESS`, serve the existing snapshot; do **not** start a new VACUUM. `VACUUM INTO` sets `snapshot_in_progress=1` before, `=0` + `snapshot_created_at=now` after, inside the *same* task. Reports during a checkout surge skip VACUUM entirely — the snapshot is at most `STALENESS` old (default 4 h for end-of-day; reports tolerate staleness).

3. **Schedule off-peak + once per shift.** Do **not** VACUUM on every report request. Schedule the snapshot once at `shift_close` (pharmacy closes ~8 pm; kiosk is idle). Tie to the shift lifecycle (§6): `ShiftRepository.close_shift()` schedules `vacuum_snapshot_background()` as a fire-and-forget task after the shift is closed.

4. **RO connection cache tuning (secondary).** The read-only replica connection that serves reports sets `PRAGMA cache_size = 20000` (≈ 20 MB) and `PRAGMA query_only = ON`. A warm cache reduces *reads* from disk during the report, so even while VACUUM writes, the report is mostly cache hits — shrinking the contention window.

**I/O budget on edge hardware:**
| Resource | Baseline (checkout hot path) | VACUUM (idle priority) | Rationale |
|---|---|---|---|
| CPU | FastAPI worker, 1 thread | subprocess `@nice+19 / priority=idle` | Scheduler prefers checkout |
| Disk I/O | WAL append (small, fast) | full-copy write (background, `ionice -c3`) | WAL never blocks on readers |
| RAM | SQLite cache ~8 MB | no extra (separate connection) | fits 4 GB budget |
| Snapshot staleness tolerated | n/a | ≤ 4 h (`STALENESS_SNAPSHOT_SEC`) | end-of-day audit freshness |

**Tests:**
- **T34:** `test_vacuum_into_does_not_block_checkout` — fire a `VACUUM INTO` in an idle-priority subprocess + concurrent 500 `POST /checkout` → p95 checkout latency < 500 ms; vacuum eventually completes; snapshot file exists.
- **H32:** `test_snapshot_reused_during_surge` — set `snapshot_in_progress=1`; concurrent reports → no new `VACUUM` started (assert subprocess not spawned); all return last snapshot.
- **H33:** `test_stale_snapshot_triggers_refresh` — `snapshot_created_at` older than 4 h, `snapshot_in_progress=0` → next report request schedules a background VACUUM.

**Failure modes:**
- `sqlite3` CLI missing on the kiosk → `vacuum_snapshot_background()` falls back to in-process `VACUUM INTO` on a deferred-task (logged `WARN` + `POS_VACUUM_CLI_MISSING` metric). Checkout latency impact is bounded by the idle-priority scheduler.
- VACUUM fails (disk full mid-copy) → delete partial snapshot file, leave `snapshot_in_progress=0`, alert in Discrepancies banner ("Audit snapshot unavailable — disk space low").
- Snapshot never succeeds → reports fall back to the RO live connection (staleness = ∞) — better to show *something* than block.

---

<a id="a4"></a>
### Appendix A.4 — Affected Files (extension deltas)

| File | Delta |
|---|---|
| `stores/posStore.ts` | ADD `getTabId()` helper (A.1) + `isSecureUuidAvailable()` guard; call site uses `getTabId()` instead of `crypto.randomUUID()`. |
| `stores/posStore.test.ts` | ADD H29–H31 (getTabId, A.1) + H38/H39 (localStorage→IndexedDB §B.6). |
| `app/core/database.py` | EDIT: `close_shift()` schedules `vacuum_snapshot_background()`; add `settings` row guard (`snapshot_in_progress`, `snapshot_created_at`) + RO connection (`cache_size=20000`/`query_only=ON` + `busy_timeout=30000`); add `SNAPSHOT_RETENTION_SEC=604800` (B.1); **ADD `run_migrations()` app-owned `PRAGMA user_version` DDL loop on startup (B.8)**; emit sync/checkout metrics (B.10). VACUUM subprocess invokes **vendored** `bin\sqlite3.exe` (no PATH). |
| `app/core/models.py` | EDIT: add `server_created_at`/`client_created_at` + `ts_skew_confidence` columns (B.7) + cashier `created_by`/`cashier_attribution` to `offline_txns`/`receipts`/`drawer_movements` (B.9); `local_seq`/`reason` on `offline_txns` (§4/§7). |
| `lib/db.ts` | EDIT: `manager_policies` store (§2) + `carts` + `seq_highwater` object stores (B.6) + `sessions` store for cashier JWT (B.9); quota-aware writes with IndexedDB fallback. |
| `run_services.py` | **Replaced by NSSM services at install time (§13).** `run_services.py` remains local-dev-only orchestrator; production lifecycle is `PharmacyCaddy`/`PharmacyBackend`/`PharmacyFrontend` via `install.ps1` + NSSM. |
| `Caddyfile` | CREATE (A.2) — staged at `C:\PharmacyPOS\Caddyfile`. |
| `docs/edge_tls.md` | CREATE (operational runbook: `caddy trust`, hosts-edit, HSTS opt-in flag `POS_ENABLE_HSTS`). |
| `install.ps1` | EDIT (§13 + B.2) — install/repair bootstrap: `.env` load, hosts edit, Caddy CA trust, 3× NSSM service registration **in dependency order with `DependOn` on `PharmacyCaddy`**; loopback-only binds. |
| `setup.iss` | CREATE (§13) — Inno Setup `.exe`: bundles `bin/{nssm,caddy,sqlite3,node}.exe`, pre-populated `backend/.venv`, `frontend/.next/`, `Caddyfile`, `install.ps1`; runs `install.ps1` silently. |
| `frontend/next.config.mjs` | EDIT (§13): `output: "standalone"`. |
| `backend/requirements-freeze.txt` | CREATE (§13) — pinned lockfile for offline `.venv` reproduction. |
| `lib/offlineCrypto.ts` | EDIT (§2/§13 + B.3): read `POS_OFFLINE_PIN_KDF` for iteration count; **rewrite `derivePin`/`verifyPin` to route PBKDF2 through a Web Worker** (main-thread fallback only when `Worker` is undefined). |
| `lib/offlineCryptoWorker.ts` | CREATE (B.3) — dedicated worker entry: `crypto.subtle.deriveKey` + `timingSafeEqual`, lazy lifecycle. |
| `lib/offlineCrypto.bench.ts` | CREATE (§13) — PBKDF2 calibration harness asserting `verifyPin_ms < 150`. |
| `deployment/policies.json` | CREATE (B.4) — Firefox `ImportEnterpriseRoots` template (written by `install.ps1` if Firefox detected). |
| `app/services/report_service.py` | EDIT (A.3 + B.1): `vacuum_snapshot_background()` gains `shutil.disk_usage` precheck (`free > db_size*2.5`) + 7-day retention sweep + atomic `os.replace`; snapshot-staleness gate (`STALENESS_SNAPSHOT_SEC=14400`). |
| `vite.config.ts` | ADD (B.3) — Web Worker asset handling + worker output naming. |
| `AGENTS.md` | ADD (B.5) `POS_SYNC_CPU_BOUND` lint/grep rule: fail build on unwrapped `reportlab`/`hashlib`/`pandas` callsites in `app/services/*`. |
| `app/core/models.py` | EDIT (§9 index already): add `sync_outbox` table + `terminal_id`/`merge_seq` (C.1), `server_created_at`/`client_created_at`/`ts_skew_confidence` (B.7), `created_by`/`cashier_attribution` (B.9), `failed_attempts`/`locked_until`/`lockout_hmac` (C.4), `local_seq`/`reason` (§4/§7). |
| `app/api/routers/sync_route.py` | CREATE (C.1) — `POST /api/sync/push`: dedup `client_txn_id`, additive stock merge, `(terminal_id, local_seq)` ordering, `OVER_SOLD_CROSS_TERMINAL` flag, `merge_seq` assignment. |
| `app/api/routers/auth_route.py` | EDIT (C.4) + §2 — `verify_pin` resolves PEPPER (machine-bound, DPAPI), HMAC-verifies lockout counters; emits `POS_PEPPER_DECRYPT_FAILURE`. |
| `lib/pepper.exe` | CREATE (C.4) — tiny static native helper (`CryptUnprotectData` Windows / `keychain`/`MachineGuid` fallback); returns plaintext PEPPER at kiosk session only. |
| `deployment/updater.exe` | CREATE (C.2) — static Go/Rust OTAs: manifest fetch + sha256 + ranged resume + atomic swap + N-version rollback + B.8 post-swap migrations. |
| `deployment/releases/latest.json` + `deployment/layer_defs.json` | CREATE (C.2) — per-layer `{name,sha256,size,url}` + zstd-dict path + `min_user_version`/`min_caddy`. |
| `app/services/pos_service.py` / `report_service.py` / receipt-label service | EDIT (B.5 + §4 + B.7 + B.9): wrap CPU-bound helpers (`render_receipt_pdf`, batch hashing, label resize) in `asyncio.to_thread(...)`; §4 `410` mapping on lot errors; B.7 `server_created_at`/skew flag on receipts; B.9 cashier-JWT `created_by` attribution. |
| `tests/test_m10_hardening.py` | ADD T34 (VACUUM checkout latency) + T35 (VACUUM space abort) + T36 (retention purge) + T37 (NSSM caddy-starts-after-upstreams) + T38 (NSSM reload absorbs restart) + T39 (Firefox policy write) + T40 (asyncio.to_thread non-block) + T41/T42 (timestamp skew §B.7) + T43/T44 (migrations §B.8) + T45/T46 (cashier attribution §B.9) + T47/T48 (sync throttle §B.10) + T49–T51 (multi-terminal sync §C.1) + T52 (granular OTA §C.2) + T53 (RAM caps §C.3) + T54/T55 (PIN peppering §C.4). |
| `tests/conftest.py` | ADD fixtures: nssm-status mock (T37/T38), `disk_usage`/`getsize` mock (T35/T36), `checkout_pressure` slow-checkout (T47/T48), `fresh_db` (T43/T44), `cashier_auth` (T45/T46). |
| `lib/offlineCrypto.test.ts` | ADD H34 (worker offload) + H35 (worker termination). |
| `tests/lint_sync_cpu.test.ts` | CREATE (H36) — vitest scan asserting CPU-bound `reportlab`/`hashlib`/`pandas` callsites are wrapped in `asyncio.to_thread`. |
| `tests/policies.test.ts` | CREATE (H37) — schema assertion on staged `deployment/policies.json`. |
| `app/services/report_service.test.ts` | ADD H32, H33 (snapshot-in-progress / stale-refresh guards, §A.3). |
| `docs/hardening_calibration.md` | CREATE (§2/§13) — records measured PBKDF2 ms/count per kiosk HW profile; gates the release. |

### Appendix A.5 — Validation (extension gates)

**Pre-commit (kiosk image build):**
```bash
# Caddy config validity (vendored bin)
C:\PharmacyPOS\bin\caddy.exe validate --config C:\PharmacyPOS\Caddyfile      # expected: VALID

# RO replica connection enforces query_only (§8)
python -c "import app.core.database as d; assert d.ro_connect().execute('PRAGMA query_only').fetchone()[0]==1"

# App-owned migrations apply cleanly from user_version=0 (B.8)
python -c "import app.core.database as d; d.run_migrations(d.connect()); assert d.connect().execute('PRAGMA user_version').fetchone()[0] >= 3"

# Sync throttling defaults are sane (B.10)
python -c "import os; assert int(os.getenv('POS_SYNC_BATCH_SIZE','10'))<=50; assert int(os.getenv('POS_SYNC_YIELD_MS','250'))>=50"

# Appendix C gates
# C.2: OTA manifest + layers are sha256-pinned, every layer file present in staging
python -c "import json,pathlib; m=json.load(open('deployment/releases/latest.json')); assert all(pathlib.Path('deployment/releases/'+l['url']).stat().st_size==l['size'] for l in m['layers'])"
# C.4: PEPPER helper present + PIN policy row exists with lockout_hmac col
test -f deployment/lib/pepper.exe && python -c "import app.core.database as d; assert 'lockout_hmac' in [r[1] for r in d.connect().execute('PRAGMA table_info(manager_policies))]"
```

**Post-deploy smoke (live kiosk, both HTTP and HTTPS paths):**
1. Open `http://<kiosk-ip>:3000` (no Caddy service / fallback) → tab isolation works, `getTabId()` returns `tab_…` form (no console error). Smoke checkout completes.
2. Open `https://pharmacy.local` (Caddy as `PharmacyCaddy` NSSM service) → `window.isSecureContext===true`, `getTabId()` returns UUID v4, WebCrypto PIN path active.
3. Stop `PharmacyCaddy` service (`nssm stop PharmacyCaddy`) → `https://pharmacy.local` fails, but `http://<kiosk-ip>:3000` still serves the app with full checkout + tab isolation (fallback, §A.1). `PharmacyBackend`/`PharmacyFrontend` were never LAN-exposed.
4. `nssm status PharmacyBackend` / `nssm status PharmacyFrontend` → both `RUNNING`; kill `PharmacyBackend` → NSSM restarts it (`<svc>.log` shows restart).
5. Trigger shift close → background `VACUUM INTO` (via vendored `bin\sqlite3.exe`) at idle priority; fire 200 concurrent checkouts during VACUUM → p95 checkout < 500 ms (T34); `snapshot_in_progress=1` during, `=0` after.
6. Kiosk HW calibration (§2/§13): `lib/offlineCrypto.bench.ts` reports `verifyPin_ms < 150` at `POS_OFFLINE_PIN_KDF`.

---

<a id="appendix-b"></a>
## Appendix B — Additional Engineering Concerns & Mitigations

**Purpose:** Five production-hardening guards that close gaps at the storage, service-lifecycle, client-runtime, cross-browser trust, and async-concurrency boundaries. Each is **mandatory**, not optional, and applies to the §13 `C:\PharmacyPOS\` deployment.

<a id="b1"></a>
### B.1 Storage Exhaustion Risk During `VACUUM INTO`

**Concern:** §A.3 runs `VACUUM INTO 'snapshot.sqlite'` as an idle-priority `sqlite3.exe` subprocess. `VACUUM INTO` writes a full copy of the database to disk. On a 4 GB-thin-client kiosk with a small eMMC (≤32 GB), accumulated snapshots or a sudden write burst can exhaust free space, producing `SQLITE_FULL` mid-copy → a corrupt/partial snapshot that is then served to reports, silently masking inventory.

**Mitigation:**
- **Pre-check gate** in `vacuum_snapshot_background()` (Python, before spawning the subprocess): `import shutil; total, used, free = shutil.disk_usage(INSTALL_DIR); db_size = os.path.getsize(DB_PATH); assert free > db_size * 2.5, "insufficient space"`. The `2.5×` factor covers the snapshot copy (×1) + WAL growth during the copy (+0.5×) + headroom (×1). If the gate fails, **abort** VACUUM, emit metric `POS_VACUUM_SPACE_ABORT`, and surface an alert in the Discrepancies banner ("Audit snapshot suspended — disk space low").
- **Automated retention policy:** `vacuum_snapshot_background()` also deletes `*_snapshot_*.sqlite` older than **7 days** (`SNAPSHOT_RETENTION_SEC = 604800`) in `C:\PharmacyPOS\data\` — keeping only the newest snapshot + the live WAL. Enforced via `os.scandir` + `os.remove` + mtime check before every VACUUM run.
- **Atomicity:** VACUUM writes to a temp name then `os.replace()`-renames into place, so a power loss mid-copy never leaves a half-written `snapshot.sqlite` (consumers always read a complete file or fall back to RO live, per §A.3 failure modes).

**Tests:**
- **T35:** `test_vacuum_aborts_on_low_space` — mock `disk_usage` to return `free < db*2.5` → VACUUM subprocess not spawned, `snapshot.sqlite` unchanged, `POS_VACUUM_SPACE_ABORT` metric incremented.
- **T36:** `test_retention_purges_7day_old_snapshots` — plant 8-day-old + 1-day-old snapshot files → after a VACUUM trigger, the 8-day-old is removed, the 1-day-old kept.

**Affected files:** `app/services/report_service.py` (extend `vacuum_snapshot_background()` with the `shutil.disk_usage` precheck (`free > db_size*2.5`) + 7-day retention sweep keyed on `SNAPSHOT_RETENTION_SEC=604800` + atomic `os.replace`), `app/core/database.py` (add `SNAPSHOT_RETENTION_SEC = 604800`; the existing `STALENESS_SNAPSHOT_SEC=14400` is intentionally distinct — "serve stale snapshot / skip new VACUUM" 4 h vs "delete old snapshot files" 7 days), `tests/test_m10_hardening.py` (T35/T36).

<a id="b2"></a>
### B.2 NSSM Service Startup Race Conditions

**Concern:** §13 registers `PharmacyCaddy` (Caddy), `PharmacyBackend` (FastAPI), and `PharmacyFrontend` (Next.js) as independent NSSM auto-start services. On low-power hardware, NSSM may start `PharmacyCaddy` **before** the backend/frontend are ready to accept loopback connections → Caddy serves a 502 Bad Gateway at kiosk boot until the upstreams warm up. An operator sees an intermittent 502 on first LAN request — a real, unactionable failure for a pharmacy terminal.

**Mitigation:**
- **NSSM service dependency:** `install.ps1` registers `PharmacyBackend` and `PharmacyFrontend` first, then sets `PharmacyCaddy` to depend on them:
  ```powershell
  & "$InstallDir\bin\nssm.exe" install PharmacyCaddy  $InstallDir\bin\caddy.exe "run --config $InstallDir\Caddyfile"
  & "$InstallDir\bin\nssm.exe" install PharmacyBackend $InstallDir\backend\.venv\Scripts\python.exe "-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
  & "$InstallDir\bin\nssm.exe" install PharmacyFrontend $InstallDir\bin\node.exe "$InstallDir\frontend\server.js"
  & "$InstallDir\bin\nssm.exe" set PharmacyCaddy DependOn PharmacyBackend PharmacyFrontend
  ```
  NSSM will not mark `PharmacyCaddy` `RUNNING` (and will not route traffic) until the dependents are `RUNNING` — but NSSM only checks process start, not port-readiness.
- **Defense-in-depth (port readiness):** Caddy `Caddyfile` uses `reverse_proxy ... to 127.0.0.1:8000` with an inline `transport` `read_buffer` and, critically, relies on Caddy's automatic **reverse-proxy retry / "wait for it" semantics**: Caddy retries the upstream connection for `load_backend` retries (default ~3) before returning 502. The FastAPI/Next.js entrypoints must be listening on loopback within that retry window — guaranteed because `uvicorn` and `node server.js` bind synchronously at process start.
- **Failure mode:** if `PharmacyBackend` crashes during the dependency window, NSSM auto-restarts it (§13 `AppExit Default ExitActions Restart`); `PharmacyCaddy` stays `STOPPED/PENDING` until the dependent stabilizes, then starts cleanly — no 502 exposure window.

**Tests:**
- **T37:** `test_caddy_starts_only_after_upstreams` — mock `nssm status` so backend/frontend return `STOPPED`; assert `install.ps1`'s registration step emits `DependOn PharmacyBackend PharmacyFrontend` and defers `nssm start PharmacyCaddy`; assert Caddy starts only after dependents report `RUNNING`.
- **T38:** `test_caddy_reload_absorbs_upstream_restart` — kill+restart `PharmacyBackend`; fire concurrent `GET /` through the loopback Caddy → no 502 reaches the client (Caddy upstream retry absorbs the ~2 s restart); assert `PharmacyCaddy` stays `RUNNING`.

**Affected files:** `install.ps1` (ADD `DependOn` block, register upstreams-first ordering), `Caddyfile` (note upstream retry), `tests/test_m10_hardening.py` (T37/T38), `tests/conftest.py` (nssm-status mock fixture).

<a id="b3"></a>
### B.3 Main-Thread Stutter During PBKDF2

**Concern:** §2 derives the offline PIN via PBKDF2-HMAC-SHA256 at 200 000 iterations of `crypto.subtle.deriveKey/deriveBits`. On a Celeron/Atom kiosk, that is ~120–180 ms of **blocking** computation. If invoked synchronously from the UI thread during `ManagerApprovalDialog` PIN entry, the browser's main thread stalls → dropped animation frames / janky dialog, and a second PIN attempt queues behind the first. For a 4-digit PIN the UX must still feel instant.

**Mitigation:**
- **Offload to a Web Worker:** `lib/offlineCrypto.ts`'s `derivePin`/`verifyPin` post the `(pin, salt, iterations)` payload to `lib/offlineCryptoWorker.ts` (a dedicated `workerize`-style Worker built via `new Worker(new URL('./offlineCryptoWorker.ts', import.meta.url))`). The main thread awaits `postMessage` + `onmessage` — **non-blocking**. The worker imports only WebCrypto (`crypto.subtle`) + the constant-time compare.
- **Worker lifecycle:** the worker is created lazily on first `ManagerApprovalDialog` open and terminated on dialog close (or after 30 s idle) — no persistent worker leak across shifts. On browsers where `Worker` is undefined (extreme legacy WebView), degrade to main-thread `await` of the same `deriveKey` (the dialog shows a "verifying…" spinner so the frame drop is at least *visible*); metrics `POS_PBKDF2_FALLBACK_MAINTHREAD` increment.
- **Concurrency guard:** at most one in-flight `derivePin` per tab via an in-flight `Promise` cache keyed by `(username)` — a rapid double-submit can't spawn parallel workers burning CPU.

**Tests:**
- **H34:** `test_pbkdf2_offloaded_to_worker` — mock `Worker` as a fake that records the payload and posts the derived key back; assert `verifyPin` resolves **without** the main thread ever calling `crypto.subtle.deriveKey` directly (the derive happens in the worker).
- **H35:** `test_worker_terminated_after_dialog_close` — open dialog, fire `verifyPin`, close dialog → assert `worker.terminate()` was called and no pending worker remains; metric `POS_PBKDF2_FALLBACK_MAINTHREAD` not incremented (worker path taken).

**Affected files:** `lib/offlineCrypto.ts` (REWRITE: `derivePin`/`verifyPin` route PBKDF2 through a Web Worker; export `derivePinOffline` main-thread fallback), `lib/offlineCryptoWorker.ts` CREATE (worker entry), `app/pos/ManagerApprovalDialog.tsx` (lazy worker create + spinner on fallback), `lib/offlineCrypto.test.ts` (H34/H35), `vite.config.ts` (worker asset handling).

<a id="b4"></a>
### B.4 Non-Windows System Certificate Stores (Firefox)

**Concern:** §A.2 trusts Caddy's local root CA via `caddy trust`, which installs the CA into the **Windows certificate store** — trusted by Chromium/Edge/IE automatically. **Firefox does not use the Windows store by default**; it maintains its own NSS certificate store. A pharmacy operator using Firefox on a thin client would see a certificate warning on `https://pharmacy.local` → may click through → weakens the TLS guarantee, or worse, abandon the HTTPS path and regress to HTTP (losing the `isSecureContext` needed for `crypto.randomUUID`, §A.1).

**Mitigation:**
- **Primary (recommended):** standardize on **Chromium-based browsers** (Edge/Chrome) for LAN kiosks — they inherit the Windows root CA via `caddy trust` with zero extra config. Documented in `docs/edge_tls.md` as the supported client. This is the Simplicity-First default.
- **Secondary (Firefox fleet):** deploy a `policies.json` to `C:\Program Files\Mozilla Firefox\distribution\policies.json` that enables enterprise-root import, so Firefox also trusts the OS store:
  ```jsonc
  {
    "policies": {
      "ImportEnterpriseRoots": true,
      "Certificates": { "ImportEnterpriseRoots": true }
    }
  }
  ```
  `install.ps1` writes this file if Firefox is detected at the standard path (`Test-Path "$env:ProgramFiles\Mozilla Firefox\firefox.exe"`). Firefox reads `distribution/policies.json` at startup → imports the Caddy root CA → no warning.
- **Fallback posture:** if neither a Chromium browser is present nor Firefox is installed, the app still runs over plain HTTP (§A.1 `getTabId` HTTP fallback) with PBKDF2-on-worker (B.3) and full checkout — TLS is a hardening layer, not a hard dependency.

**Tests:**
- **T39:** `test_install_ps1_writes_firefox_policies` — given Firefox is detected in `$env:ProgramFiles`, assert `C:\Program Files\Mozilla Firefox\distribution\policies.json` exists with `ImportEnterpriseRoots: true`; if Firefox absent, assert the file is not written (no error).
- **H37:** `test_firefox_policy_json_schema` — assert the staged `deployment/policies.json` parses and contains the `ImportEnterpriseRoots` key (schema guard against future Firefox policy renames).

**Affected files:** `install.ps1` (ADD Firefox-detection + policies.json write), `deployment/policies.json` CREATE (template), `docs/edge_tls.md` EDIT (Firefox note + Chromium recommendation), `tests/test_m10_hardening.py` (T39), `tests/policies.test.ts` (H37).

<a id="b5"></a>
### B.5 Event-Loop Blocking on Single-Worker FastAPI

**Concern:** §3.4 mandates a single Uvicorn worker (one process, one event loop) for write-safety against SQLite. FastAPI/async is single-threaded per worker, so any **synchronous CPU-bound helper** that runs inline on the event loop blocks *every* concurrent request — including `POST /pos/checkout` (the critical path). A receipt-PDF render, a SHA-256 hash of a batch file, or parsing a large `pandas`/`reportlab` import held the loop for N ms → checkout latency spikes during a report batch.

**Mitigation:**
- **Mandate `asyncio.to_thread(...)` for all sync CPU-bound helpers.** Every helper classified as sync-CPU-bound (see audit, below) **must** be wrapped:
  ```python
  # BAD (blocks the event loop):
  #   pdf = render_receipt_pdf(txn)
  # GOOD:
  pdf_bytes = await asyncio.to_thread(render_receipt_pdf, txn)
  ```
  `asyncio.to_thread` runs the function in FastAPI's default threadpool executor (no new process), yielding the event loop so checkout stays responsive.
- **Sync-helper audit (inventory, one-time):** `grep` the codebase for CPU-bound callsites — `reportlab`, `pdfkit`, `hashlib` (batch hashing), `pandas.read_excel`/`csv` bulk import, `PIL` image resize for labels, `json` of large payloads. Each is wrapped or moved into a dedicated threadpool-routed service function. A CI gate (`ruff`/`grep` rule `POS_SYNC_CPU_BOUND` in `AGENTS.md`) fails the build if a new unwrapped `hashlib`/`reportlab`/`pandas` call appears.
- **Threadpool sizing:** the worker threadpool defaults to `min(40, cpu+4)`. For a 2-vCPU kiosk that is 6 threads — enough to absorb a burst of receipt renders without starvation, while the single **event loop** (the thing that touches SQLite) remains uncontended. CPU-bound work only touches *in-memory* data; SQLite writes stay on the event loop in short `session.begin()` sections (§8).

**Tests:**
- **T40:** `test_report_render_does_not_block_checkout` — fire a CPU-bound `render_receipt_pdf` (sleep 1 s inside `to_thread`) + concurrent `POST /checkout` → checkout commits (<200 ms); the render runs on a thread (assert its `threading.get_ident()` differs from the main event loop thread).
- **H36:** `test_sync_cpu_bound_audit_no_unwrapped_callsites` — vitest CI scan of `app/services/**`: assert every `reportlab`/`hashlib`/`pandas` callsite is within an `asyncio.to_thread(...)` context.

**Affected files:** `app/services/pos_service.py` / `app/services/report_service.py` / any receipt-label service (wrap CPU-bound helpers in `asyncio.to_thread`), `AGENTS.md` ADD `POS_SYNC_CPU_BOUND` lint rule, `ruff.toml`/`pyright` config (threadpool rule), `tests/test_m10_hardening.py` (T40), `tests/lint_sync_cpu.test.ts` CREATE (H36).

<a id="b6"></a>
### B.6 Client-Side Storage Management (`localStorage` vs. `IndexedDB`)

**Concern:** §3 stores the per-tab active cart in `localStorage` (keyed by tab UUID); §7 stores the Lamport `local_seq` high-water in IndexedDB. Thin-client browsers impose a ~5 MB `localStorage` quota that is **shared** across all apps in the browser profile, and the OS can evict `localStorage` under memory pressure — exactly when the kiosk must survive a power loss. An 18-line prescription cart or a high-water `local_seq` lost to `QuotaExceededError`/`EvictedError` breaks recovery (§3) and FIFO monotonicity (§7) at the worst moment.

**Mitigation:**
- **Defensive writes everywhere:** every `localStorage.setItem` for POS keys (`pos_activecart_tab_*`, `pos_held_v1`) is wrapped in `try/catch (e instanceof DOMException && e.name === "QuotaExceededError")` → on failure, fall back to the IndexedDB store and surface `POS_STORAGE_FALLBACK` metric (never throw to the UI).
- **Proactive migration of critical state to IndexedDB:** the two state items that *must* outlive quota pressure move to `lib/db.ts`'s `pos_store` object store as the durable canonical source:
  - `activeCart` (per-tab): written to both `localStorage["pos_activecart_tab_{id}"]` (fast path, §3) *and* `pos_store.carts` (IndexedDB, durable). `persist()` writes localStorage first; on `QuotaExceededError` it writes IndexedDB and clears the localStorage key. On `hydrate()`, localStorage is read first, then IndexedDB reconciled (deep-merge + stock re-validate, §3).
  - `local_seq` high-water (§7): already IndexedDB; the re-seed guard (§7) reads it as the authoritative floor. `localStorage["pos_local_seq"]` becomes a *cache* of the high-water (for cross-tab BroadcastChannel speed), not the source of truth.
- **Eviction safety:** IndexedDB is *not* subject to the 5 MB `localStorage` quota and is far less aggressively evicted on Windows thin clients — making it the correct durable spine. `localStorage` remains the cheap/fast cache for the common case.

**Tests:**
- **H38:** `test_localstorage_quota_fallback` — mock `setItem` to throw `QuotaExceededError`; assert the cart is still persisted (to IndexedDB) with no UI throw, and `POS_STORAGE_FALLBACK` increments.
- **H39:** `test_active_cart_survives_localstorage_eviction` — persist cart → clear `localStorage` → rehydrate → cart restored intact from IndexedDB (stock re-validate still passes).

**Affected files:** `lib/db.ts` (add `carts` and `seq_highwater` object stores; `pos_store` schema migration), `stores/posStore.ts` (`safeSetLocalStorage` try/catch wrapper + IndexedDB reconcile on persist/hydrate; §3 cart writes go to both), `lib/offlineQueue.ts` (§7 reads `local_seq` high-water from IndexedDB as the re-seed floor), `stores/posStore.test.ts` (H38/H39), `lib/db.ts` (object-store version bump `1 → 2`).

<a id="b7"></a>
### B.7 Timestamp Skew and Fiscal Integrity

**Concern:** §4 replays offline txns and §7 sorts them by Lamport `local_seq` for FIFO ordering. But the transaction's `created_at` (used in end-of-day fiscal reports, shift variance, and the `drawer_movements`/`offline_txns` audit trail) is stamped at the **client**, which on a CMOS-battery-fail or NTP-slew kiosk can be hours/days off. A report generated at "2026-08-15" can absorb a txn stamped "2020-01-01" → corrupts fiscal period boundaries and can shift a sale into a closed shift, masking accountability.

**Mitigation:**
- **Server-side reception timestamp is canonical for fiscal reporting.** `POST /pos/checkout` and `POST /shift/{id}/drawer-movement` both record `server_created_at = func.now()` (server epoch) **and** echo back the client-supplied `client_created_at` (the kiosk clock value). Fiscal reports (`revenue`, `shift_close`, `audit`) group/sort by `server_created_at`, **never** `client_created_at`.
- **Skew flag (not adjustment):** if `abs(server_created_at - client_created_at) > POS_TS_SKEW_THRESHOLD_SEC` (default 300 s), the txn is accepted (it is still valid business data) but tagged `ts_skew_confidence = 'low'` and surfaced in `DiscrepanciesPanel` under "Timestamp skew" → the manager reviews but the sale is not voided. This preserves data integrity without breaking cash-in-hand flow during a known clock event.
- **Offline txn replay (§4):** on replay, `client_created_at` from the parked JSON is preserved in the new row; `server_created_at` is set to *reception* time. The skew flag is recomputed at replay against the current server time. Drift of the *ordering* is already handled by `local_seq` (§7); this closes the *fiscal-reporting* gap.

**Tests:**
- **T41:** `test_client_ts_skew_flagged` — POST with `client_created_at` 20 min off from `server_created_at` → row inserted, `ts_skew_confidence='low'`, `server_created_at` is server epoch; fiscal `GET /reports/shift/{id}` groups by `server_created_at` (skewed txn in the correct period).
- **T42:** `test_skewed_txn_not_voided` — assert the txn is **accepted** (not 410/400) when skew is within policy but flagged; only a malformed payload (§4 T28) is rejected as 400.

**Affected files:** `app/core/models.py` (ADD `server_created_at` + `client_created_at` + `ts_skew_confidence` to `offline_txns`/`drawer_movements`/`receipts`; `POS_TS_SKEW_THRESHOLD_SEC` default 300), `app/api/routers/pos_route.py` (set `server_created_at = func.now()`; compute skew flag), `app/services/report_service.py` (group by `server_created_at`), `tests/test_m10_hardening.py` (T41/T42).

<a id="b8"></a>
### B.8 Automated Schema Migrations for Edge Instances

**Concern:** §10 lists `ALTER TABLE ... ADD COLUMN local_seq` and the new `drawer_movements` table as schema additions. The plan assumed Alembic/dev tooling. A pharmacy kiosk runs a bare FastAPI + SQLite on 4 GB hardware with **no Alembic, no `psql`-style migration runner, and no dev shell** — the only code that can touch the DB is the application itself. A manual `ALTER TABLE` via `sqlite3.exe` during shift-close is operator-error-prone and not atomic with the app's first run.

**Mitigation:**
- **Application-owned, programmatic migrations via `PRAGMA user_version`.** `app/core/database.py` runs a `run_migrations()` step at app startup (once per process, before serving requests), gated by an integer `user_version` counter:
  ```python
  MIGRATIONS = {
      1: _m1_add_offline_local_seq,      # ALTER TABLE offline_txns ADD COLUMN local_seq BIGINT; UPDATE ... SET local_seq = id; CREATE INDEX ...
      2: _m2_add_drawer_movements,       # CREATE TABLE drawer_movements (...);
      3: _m3_add_receipt_audit_columns,  # server_created_at, client_created_at, ts_skew_confidence
      ...
  }
  def run_migrations(conn):
      cur = conn.execute("PRAGMA user_version"); v = cur.fetchone()[0]
      for target in range(v + 1, max(MIGRATIONS) + 1):
          with conn:  # single transaction — DDL is atomic in SQLite
              MIGRATIONS[target](conn)
          conn.execute(f"PRAGMA user_version = {target}")
  ```
  - Each `_m*` is idempotent and safe because SQLite `ALTER TABLE ... ADD COLUMN` is a schema no-op if the column exists; the guard double-checks by `PRAGMA table_info`. `user_version` is bumped **inside** the same transaction only after the DDL commits, so a crash mid-migration leaves `user_version` unchanged → retried on next boot (exactly-once per version).
  - **No external runner:** `run_services.py`/NSSM start → FastAPI `lifespan` calls `run_migrations()` once. No `alembic`/`flask db upgrade` anywhere on the kiosk.
- **Single-writer safety:** because the deployment is single-worker (§3.4), `run_migrations()` runs on the one event-loop thread — no concurrent DDL race. WAL + `busy_timeout` (§3.4) is set *before* migrations.

**Tests:**
- **T43:** `test_migrations_idempotent_and_atomic` — start with `user_version=0`; run `run_migrations()`; assert `user_version == 3` + the 3 schema objects exist; run again → no error, `user_version` unchanged; assert each `_m*` checks `PRAGMA table_info` before adding.
- **T44:** `test_migration_crash_resumes` — simulate crash (drop in-memory conn) mid-migration between `user_version=1` and `=2`; on restart `run_migrations()` resumes from v1 and completes to v3 (assertion: final `user_version == 3`, columns present).

**Affected files:** `app/core/database.py` ADD `MIGRATIONS` dict + `run_migrations()` + `PRAGMA user_version` loop (called from FastAPI `lifespan`/startup); `app/core/models.py` (migration-aligned column defs for B.4 audit cols); `tests/test_m10_hardening.py` (T43/T44), `tests/conftest.py` (fresh-DB-each-test fixture).

<a id="b9"></a>
### B.9 Granular Multi-Cashier Attribution

**Concern:** §1 (`drawer_movements`) and §4 (offline replay) bind activity to the **shift** via `shift_id`. §1.1 says `float_add`/`cash_drop`/`paid_out` can be auto-approved up to a threshold "cashier auto" — but on a **shared terminal** (one kiosk, multiple cashiers within one shift, e.g. morning pharmacist + afternoon clerk), the shift-level `created_by` is ambiguous: an audit trail showing "shift #42 had a \$300 cash_drop" cannot name *who* authorized it. This breaks fiscal accountability precisely where §S.1 of the pharmacy reg requires per-person sign-off.

**Mitigation:**
- **Every offline transaction and drawer movement binds `created_by` to the authenticated cashier's session token**, persisted in IndexedDB (`manager_policies` / `pos_store.sessions`), *not* to the shift ID alone.
  - The frontend attaches `X-Cashier-Token` (the cashier's JWT, scoped `cashier:create` and short-TTL) to every `POST /pos/checkout`, `POST /shift/{id}/drawer-movement`. The token is stored client-side in IndexedDB (B.6) and is **never** the manager's high-privilege token (manager ops keep using `require_approval_token`, §1).
  - The backend resolves `created_by = cashier_jwt.sub` and **stamps it on the row**. The shift `created_by` becomes the *fallback* only when no cashier token is present (e.g. a manager override), and that case is logged `cashier_attribution = 'manager_fallback'`.
- **Offline:** the parked `QueuedTxn` JSON includes the `cashier_token` (or a one-time offline ticket minted at park time bound to the cashier). On replay (§4), the cashier is re-attested from the token; a missing/invalid cashier token → `400` retry (genuine, fixable) — **not** silently attributed to the shift.
- **Drawer movements:** `DrawerMovement.created_by` is the cashier JWT sub; `manager_adj`/`pickup` (which require `require_approval_token`) still go through the manager token path — but a manager acting *as* a cashier for a routine `paid_out` ≤ `PAID_OUT_LIMIT` is now correctly attributed to the cashier, not the shift.

**Tests:**
- **T45:** `test_offline_txn_requires_cashier_token` — POST `/pos/checkout` with no `X-Cashier-Token` → `400`; with a valid (expired rejected) token → `201` + row `created_by == token.sub`, `cashier_attribution == 'cashier'`.
- **T46:** `test_drawer_movement_names_the_person` — two cashiers A/B in the same shift; A does `paid_out \$45`, B does `cash_drop \$400` → both rows have distinct `created_by` (A/B), not the shared shift ID.

**Affected files:** `app/core/models.py` (ADD `X-Cashier-Token` resolution + `cashier_attribution` enum/col to `receipts`/`offline_txns`/`drawer_movements`), `app/api/routers/pos_route.py` (read `X-Cashier-Token`, stamp `created_by`; 400 on missing), `lib/offlineQueue.ts` (`QueuedTxn` carries `cashier_token`), `lib/db.ts` (IndexedDB session store), `types/contracts.ts` (CashierToken contract), `tests/test_m10_hardening.py` (T45/T46).

<a id="b10"></a>
### B.10 Sync Throttling and Resource Management ("Sync Storm")

**Concern:** §7.7 (`syncOfflineQueueWithLock`) drains the parked `offline_txns` queue. After a **multi-day outage** (network down + kiosk offline) the queue can hold hundreds of txns. The original §7.7 replays "sequentially with timed yields" — but the spec left the batch size and yield cadence as unspecified, so an implementer could replay 500 txns in one tight `for` loop → 500 sequential server writes + 500 WAL appends saturate the single FastAPI worker (§3.4) and the SQLite WAL buffer for the full drain, **starving live `POST /checkout`** and turning an offline event into a checkout outage.

**Mitigation:**
- **Batched replay with cooperative yields.** `syncOfflineQueueWithLock()` processes in **chunks** of `POS_SYNC_BATCH_SIZE` (default 10) txns, then `await asyncio.sleep(POS_SYNC_YIELD_MS / 1000.0)` (default 250 ms) — giving the single event loop back to checkout between chunks:
  ```python
  BATCH = int(os.getenv("POS_SYNC_BATCH_SIZE", "10"))
  YIELD = int(os.getenv("POS_SYNC_YIELD_MS", "250"))
  async with lock:
      while True:
          batch = await offlineQueue.dequeue(BATCH)        # FIFO by local_seq ASC (§7)
          if not batch: break
          for txn in batch:
              await sync_one(txn)                          # 410→discrepant, 400→retry, else mark synced
          await asyncio.sleep(YIELD / 1000.0)             # ← yield to checkout event loop
          processed += len(batch)
  ```
- **Configurability (kiosk-tuned):** `POS_SYNC_BATCH_SIZE` and `POS_SYNC_YIELD_MS` are env-configurable (§10 feature flags) — default to the conservative 10/250 ms for 4 GB kiosks; a beefier site can raise to 50/50. Tuning knob for the deployment tier.
- **Backpressure visibility:** `metrics.sync_queue_depth`, `sync_batch_latency_ms`, and `checkout_p95_during_sync` are emitted; if `checkout_p95_during_sync > 200 ms` for >3 consecutive sync batches, `syncOfflineQueueWithLock` **auto-throttles down** (halve the batch size) and log `POS_SYNC_AUTO_THROTTLE`.

**Tests:**
- **T47:** `test_sync_drains_large_queue_without_stalling_checkout` — seed 200 parked txns; run `syncOfflineQueueWithLock` + concurrent 50 `POST /checkout` → assert checkout p95 < 200 ms throughout drain **and** queue fully drains (all `synced`); assert at least one `asyncio.sleep(YIELD)` was hit between batches (proves throttling, not a tight loop).
- **T48:** `test_sync_auto_throttles_under_checkout_pressure` — force `checkout_p95 > 200 ms` (slow checkout mock); assert the batch size halves after the 3rd batch and `POS_SYNC_AUTO_THROTTLE` fires once.

**Affected files:** `lib/offlineQueue.ts` (`dequeue(limit)` FIFO by `local_seq`; `syncOfflineQueueWithLock` chunked + yield), `stores/posStore.ts` (invoke batched sync on `online` event), `app/core/database.py` / metrics (`sync_queue_depth`, `sync_batch_latency_ms`, `checkout_p95_during_sync`, `POS_SYNC_AUTO_THROTTLE`), `tests/test_m10_hardening.py` (T47/T48), `tests/conftest.py` (checkout-pressure fixture).

---

**Matrix additions (appended to §9):**

| # | Subsystem | Risk | Refinement | Key invariant preserved |
|---|---|---|---|---|
| 10 | VACUUM snapshot | DISK FULL corrupts audit snapshot mid-copy | `shutil.disk_usage` precheck (`free > db*2.5`) + 7-day retention sweep + atomic `os.replace` (B.1) | snapshot is always complete or absent; never half-written |
| 11 | NSSM startup | 502 Bad Gateway at kiosk boot before upstreams ready | `PharmacyCaddy` `DependOn` `PharmacyBackend`+`PharmacyFrontend` + Caddy upstream retry (B.2) | no 502 reaches client during boot; crash→auto-restart |
| 12 | Client PBKDF2 | 200 k PBKDF2 stalls main thread on Celeron | PBKDF2 in a lazy Web Worker; in-flight dedup; main-thread `await` fallback (B.3) | main thread never blocks >1 frame on verify |
| 13 | Firefox TLS | cert warning → operator regresses to HTTP | `policies.json` `ImportEnterpriseRoots` (if Firefox detected) + Chromium recommendation (B.4) | `https://pharmacy.local` trusted on Chromium; HTTP fallback always works |
| 14 | FastAPI event loop | sync CPU-bound helper stalls checkout | `asyncio.to_thread` for all sync-CPU helpers + CI `POS_SYNC_CPU_BOUND` audit (B.5) | single Uvicorn worker; event loop never blocks on sync CPU |
| 15 | Client storage quota | `localStorage` 5 MB quota / OS eviction loses cart + Lamport seq | try/catch `QuotaExceededError` + migrate active cart + `local_seq` high-water to IndexedDB (B.6) | critical state survives quota pressure; never throws to UI |
| 16 | Timestamp skew | client `created_at` corrupts fiscal periods/reports | server stamps `server_created_at`; skew > `POS_TS_SKEW_THRESHOLD_SEC` tagged `low` + surfaced (B.7) | fiscal reports group on server time; skewed txns audited, not lost |
| 17 | Edge schema migrations | no Alembic/dev shell on kiosk | app-owned `PRAGMA user_version` DDL loop, transactional + idempotent on boot (B.8) | migrations atomic per version + crash-resumable; `user_version` monotonic |
| 18 | Multi-cashier attribution | shared terminal → audit trail names shift, not person | every offline txn + drawer movement binds `created_by` from cashier JWT in IndexedDB (B.9) | audit trail names the individual; manager fallback logged |
| 19 | Sync storm | multi-day offline queue starves live checkout | batched `syncOfflineQueueWithLock` (default 10/250 ms) + auto-throttle under checkout pressure (B.10) | checkout p95 < 200 ms throughout drain; queue fully synced |
| 20 | Multi-terminal SQLite | SMB-shared DB corrupts; inventory drift across kiosks | per-terminal local SQLite + merge-sync hub with `(terminal_id, local_seq)` ordering + dedup-by-`client_txn_id` (C.1) | single-writer invariant preserved per terminal; net inventory matches physical count |
| 21 | Monolithic updates | full installer re-downloads venv+bundle+binaries over unstable link | layered OTA (backend code / frontend `.next` / binaries / schema) with sha256 + ranged resume + atomic release swap + rollback (C.2) | only changed layers fetched; kiosk never half-updated |
| 22 | RAM exhaustion (4–8 GB) | Chromium+Node+FastAPI+Caddy+SQLite thrash/em swap on kiosk | per-process caps (Node `--max-old-space-size`, NSSM working-set / Job-object limits) + perf budget + auto-restart on cap (C.3) | 4 GB footprint ≤ budget; no swap thrash; checkout p95 stable under load |
| 23 | PIN brute-force offline | 4–6 digit PIN in exfiltrated SQLite is searchable offline | **device-bound peppering**: PIN hash = `PBKDF2(PIN, pepper=DPAPI-encrypt(device-key, salt))`; DB holds only `salt`+derived hash, pepper never leaves the machine (C.4) | offline DB dump alone cannot brute-force PINs; ≥10⁸ work factor even with the salt 


<a id="appendix-c"></a>
## Appendix C — Scaling & Hardening Extensions

> **Scope contract:** the base plan (§1–§8, §3.4, §7.5) remains **single-kiosk, single-writer SQLite**. Appendix C adds four *opt-in, composable* extensions that must **preserve** every base invariant when disabled. They are **additive**, never replacements.

<a id="c1"></a>
### C.1 Multi-Terminal Concurrency & Merge Sync (beyond Lamport)

**Concern:** §3.4 §7.5 mandate one SQLite writer per on-box DB. A multi-kiosk pharmacy (≥2 terminals + 1 backend server, or each kiosk self-hosting) breaks this: an SMB-shared SQLite file corrupts under concurrent writers (SQLite's own guidance — never open the same DB over SMB from >1 process), and overlapping offline sales across kiosks drift physical inventory because each terminal's `local_seq` (§7) orders only *within* that terminal.

**Strategy — "local-write, merge-sync hub" (preserves §3.4 single-writer per terminal):**
- **Each terminal keeps its own local SQLite** (single-writer, WAL, §3.4 untouched). No SQLite file is ever opened by >1 process over the network.
- **Terminal identity:** configured via `TERMINAL_ID` env (§13 NSSM `AppEnvironment`); Caddy echoes it via `X-Forwarded-Host`/a header so the backend knows the origin.
- **Sync log on every terminal:** each committed txn is appended to `sync_outbox` (cols: `client_txn_id`, `terminal_id`, `local_seq`, `payload`, `synced_at NULL`). FIFO drain by `local_seq ASC` (§7 + B.10 batching).
- **Hub = single writer to authority.** A sync endpoint (`POST /api/sync/push`) accepts each terminal's outbox. The hub holds the **authoritative** DB and is the *only* writer — eliminating SMB corruption by construction.
- **Global ordering beyond Lamport:** events are ordered by the composite **`(terminal_id, local_seq)`** — `terminal_id` breaks cross-terminal ties lexicographically (never equal), and each terminal's `local_seq` (§7 Lamport re-seed guard included) is monotonic. The hub assigns a `merge_seq` (hub-local monotonic) for any hub-side replay.
- **Conflict resolution = additive deltas + dedup:**
  - `client_txn_id` is the global dedup key (§4 exact-once invariant) → a sale pushed twice is merged, not double-counted.
  - Stock movements are additive deltas per `(lot_id, batch_no)`; the hub sums them. **True over-sells** (two terminals selling the same physical unit concurrently, both decrementing below real stock) are **not auto-merged** — flagged `reason=OVER_SOLD_CROSS_TERMINAL` and surfaced in `DiscrepanciesPanel` (§4) for manager review.
  - Net physical inventory = `baseline − Σ decrements + Σ receipts`, reconciled by the hub and pushed back as a snapshot (consumes the §A.3 VACUUM path).
- **Network-partition friendly:** partition handling reuses §5 (WebLocks→BroadcastChannel→localStorage tier) and B.6 (IndexedDB) — outbox survives offline; on reconnect the batched push (B.10) drains without starving the local checkout hot path.

**Tests:**
- **T49:** `test_cross_terminal_oversell_flagged_not_merged` — terminals A & B both sell the last unit of lot X concurrently → hub inserts both (both `synced`) but tags both `discrepant` + `reason=OVER_SOLD_CROSS_TERMINAL`; `DiscrepanciesPanel` lists them.
- **T50:** `test_client_txn_id_dedup_across_terminals` — terminal A pushes sale `tx_7` twice (retry) + terminal B pushes the same `tx_7` (shared cart hold) → exactly one receipt in the hub DB (dedup on `client_txn_id`), stock decremented once.
- **T51:** `test_network_partition_reconciles_on_reconnect` — terminal A offline 5 min (3 sales parked in `sync_outbox`); reconnect → outbox drains FIFO, hub merges, stock count matches physical `SELECT` after sync; checkout p95 during drain < 200 ms (B.10).

**Affected files:** `lib/offlineQueue.ts` (`sync_outbox` table + `terminal_id` + `(terminal_id, local_seq)` ordering; `dequeue(limit)` FIFO §B.10), `stores/posStore.ts` (push outbox on `online`/sync event), `app/api/routers/sync_route.py` CREATE (`POST /api/sync/push`: dedup `client_txn_id`, additive merge, `OVER_SOLD_CROSS_TERMINAL` flag, `merge_seq`), `app/core/models.py` (`sync_outbox` table, `terminal_id`/`merge_seq` cols, `OVER_SOLD_CROSS_TERMINAL` reason), `app/services/pos_service.py` (append to outbox on checkout commit), `tests/test_m10_hardening.py` (T49–T51), `tests/conftest.py` (multi-terminal fixture).

<a id="c2"></a>
### C.2 Granular, Resumable OTA Patching

**Concern:** §13 `setup.iss` reinstalls the **entire** `C:\PharmacyPOS\` (Python `.venv` + wheels + full `.next` bundle + binaries) on every update — a 100+ MB payload re-downloaded even for a one-line Python fix, over an unstable kiosk link with no resume.

**Strategy — layered, content-addressed, atomic OTA (sits on top of §13, doesn't replace it):**
- **Four payload layers:** `bin/` (rare — nssm/caddy/sqlite3/node), `backend/app/` (Python source — frequent), `frontend/.next/` (Next.js bundle — frequent), `schema/` (migrations only — tied to §10 §B.8).
- **`updater.exe`** (a tiny static Go/Rust binary, **no runtime dependency** — chosen so it runs before .venv is healthy) as `PharmacyUpdater` NSSM service OR invoked by `install.ps1 --check-updates`. It:
  1. `GET /releases/latest.json` (manifest: `{layers:[{name,sha256,size,url}], min_user_version, min_caddy}`), compares each layer's `sha256` to the cache at `C:\PharmacyPOS\versions\<sha>\` — **only changed layers download**.
  2. Ranged HTTP `Range` GET → `.part` resume; **zstd `--long=30`** + a shared dictionary for Python/TS text (≈40% smaller than zip). Per-layer **sha256 verify** before acceptance.
  3. Stages everything in `C:\PharmacyPOS\staging\` (temp) — never touches `current\` live files.
  4. **Atomic swap:** when ALL layers verify, atomically point `current → staging` (rename) → runs B.8 `run_migrations()` (schema layer) → restarts NSSM services in dependency order (§B.2: PharmacyBackend/Frontend then PharmacyCaddy).
  5. **Rollback:** keeps last N releases (`C:\PharmacyPOS\releases\`); first-boot self-check (Caddy validate + `import fastapi,uvicorn`) fails → auto-rollback to previous release + alert.
- **Bandwidth minimization:** content-addressed by `sha256` → identical layers never re-fetched; `Range` resume survives disconnects; manifest `ETag`/`last-modified` lets the updater 304 on unchanged.

**Tests:**
- **T52:** `test_ota_updates_only_changed_layer_and_rolls_back_on_corruption` — manifest with 4 layers, 1 changed → only that layer fetched; tamper one byte → sha256 mismatch → atomic rollback, `current` unchanged, rollback metric fires.

**Affected files:** `deployment/updater.exe` CREATE (static Go/Rust), `deployment/releases/latest.json` CREATE (manifest template), `deployment/layer_defs.json` CREATE (per-layer sha256 + zstd-dict path), `install.ps1` ADD (`--check-updates` invokes `updater.exe`), `setup.iss` ADD (`updater.exe` + `releases/` staged), `app/core/database.py` (`run_migrations()` on startup post-swap, B.8), `tests/test_m10_hardening.py` (T52), `tests/conftest.py` (layer-cache fixture).

<a id="c3"></a>
### C.3 RAM Exhaustion Control (4–8 GB kiosks)

**Concern:** A full kiosk stack — Chromium (kiosk browser) + Node.js (Next.js standalone) + FastAPI/Uvicorn + Caddy + SQLite — on 4–8 GB hardware, with **no process caps**, will swap to eMMC under a checkout + report + receipt-render burst → p95 checkout spikes and the terminal feels frozen.

**Strategy — hard caps + perf budget + swap avoidance + auto-restart:**
- **Backend (FastAPI):** `--workers 1` (§3.4) + NSSM `AppMaxBytes` / a Windows **Job object** memory cap → **1.0 GB ceiling** on 4 GB; **1.8 GB** on 8 GB.
- **Frontend (Node standalone):** `NODE_OPTIONS=--max-old-space-size=1024` in NSSM `AppEnvironment` (§13) → V8 hard cap 1.0 GB (1.8 GB on 8 GB).
- **Caddy:** ~0.2 GB (`process_limit` + working-set cap).
- **Chromium kiosk:** `--disk-cache-size=0` + `--disk-cache-dir=<temp>` (protect eMMC), `--no-first-use`, `--disable-background-networking`, `--disable-preconnect`, `--disable-component-update`, `--disable-sync`; **Job object cap ~1.3 GB (4 GB) / ~2.2 GB (8 GB)** on the whole browser tree; `--site-per-process` ON (renderer isolation limits blast radius).
- **SQLite:** `PRAGMA cache_size=20000` (~20 MB) + `PRAGMA mmap_size=268435456` (256 MB ceiling) + `wal_autocheckpoint=1000`; RO replica (§8) reads never block writes.
- **Frontend perf budget:** Next.js gzip `< 250 KB`; dev-only code pruned at build; lazy-load `ManagerApprovalDialog` (worker-isolated, B.3); **no remote images** (B.4).
- **eMMC swap avoidance:** set NSSM `AppMinBytes`/`MinWorkingSet` so hot pages stay resident; on 4 GB **disable the pagefile** (or a tiny fixed 0.5 GB) and rely on caps; emit `pos_ram_usage_p95`; NSSM `AppExit Default ExitActions Restart` recovers any process that breaches its cap (prefer restart over swap).
- **Budget table:** 4 GB → Backend 1.0 + Frontend 1.0 + Browser 1.3 + Caddy/SQLite 0.3 = **3.6 GB (~90%)**; 8 GB → 1.8 + 1.8 + 2.2 + 0.4 = **6.2 GB (~78%)** with headroom to spare.

**Tests:**
- **T53:** `test_memory_caps_hold_under_checkout_storm` — 200 concurrent checkouts + report render + receipt batch under Node 1 GB cap + Browser 1.3 GB cap → checkout p95 < 200 ms, Node RSS ≤ 1.05 GB, Browser RSS ≤ 1.35 GB, `pos_ram_usage_p95` emitted, **no pagefile growth**.

**Affected files:** `install.ps1` ADD (`NODE_OPTIONS`, NSSM `AppMaxBytes` + Job-object caps, Chromium kiosk flags, `AppMinBytes`/pagefile policy), §13 service table (reference memory caps), `app/core/database.py` (cache_size/mmap/pragmas), `frontend/next.config.mjs` (perf budget lint + dev-code exclusion), `tests/test_m10_hardening.py` (T53), `tests/conftest.py` (RSS-assertion fixture).

<a id="c4"></a>
### C.4 Local PIN Brute-Force Mitigation (Device-Bound Peppering)

**Concern:** §2 §6 protect the offline PIN with PBKDF2 (200 k) + lockout. But a **4–6 digit PIN** is only 10⁴–10⁶ entropy — an attacker who exfiltrates `pharmacy.db` (e.g., walk-away kiosk disk) holds `salt` + `pin_hash` and can **offline-brute-force** the PIN at full machine speed (PBKDF2 200k ≈ 120 ms/core; 10⁶ PINs ≈ 33 h on one core, far less with GPU/ASIC), **bypassing the §6 lockout entirely** because the DB is no longer under the kiosk's control.

**Strategy — device-bound peppering so the DB dump is useless off-machine (defense-in-depth over §2 + §6 + B.3):**
- **PIN verify = `PBKDF2-HMAC-SHA256(PIN, pepper=salt‖PEPPER, 200_000)`** (§2 unchanged), but `PEPPER` is **machine-bound and not stored in the DB**: it's derived from a Windows **DPAPI** blob (`CryptProtectData(..., CRYPTPROTECT_LOCAL_MACHINE)`) — decryption only succeeds on the original machine (or that machine's domain account). The DB stores `salt` (per-user, fine) + `pin_hash` + the encrypted `pepper_blob`; the plaintext `PEPPER` lives **only in RAM during the kiosk session**, obtained via a tiny native `pepper.exe`/`node-addon` at unlock.
- **Effect on exfiltration:** an attacker with the DB dump + `pepper_blob` on a *different* machine calls `CryptUnprotectData` → **fails** (wrong machine account) → `PEPPER` is unrecoverable → `verifyPin` returns **false for every candidate** (including the real PIN) → the offline brute-force search yields no confirmation, collapsing the attack. The real kiosk still unlocks normally.
- **Salt:** per-user random 16-byte in the DB (the pepper is the machine secret; salt just prevents cross-user rainbow reuse).
- **Lockout integrity:** `failed_attempts`/`locked_until` are **pepper-HMAC-signed** (`HMAC(PEPPER, failed_attempts‖locked_until)`) so an exfiltrator cannot reset the §6 lockout counters offline — tampering invalidates the HMAC → policy treated as "locked since epoch" → forces online re-auth.
- **Fallback tier:** if no DPAPI/TPM (non-Windows edge), derive `PEPPER` from `MachineGuid` (HKLM registry) — weaker (movable with the disk) but still raises the bar; documented as Tier-2, prefer DPAPI.
- This stacks on §2 (slow KDF), §6 (online lockout), B.3 (Web Worker so the KDF+decrypt happen off-main-thread): offline-exfil → no machine → no pepper → no brute-force; online-fast → lockout; UX-stutter → worker.

**Tests:**
- **T54:** `test_pin_brute_force_infeasible_without_machine` — exfiltrate `(salt, pin_hash, pepper_blob)` to a *different* machine; `verifyPin(correct_PIN, exfiltrated_blob)` → `false` (CryptUnprotectData rejects) + `POS_PEPPER_DECRYPT_FAILURE` fires; attacker cannot distinguish correct vs wrong PIN → brute-force yields no positive.
- **T55:** `test_lockout_counters_tamper_evident` — flip `failed_attempts` in the DB (simulate offline edit) → HMAC re-verify fails → policy treated as locked → online re-auth required (can't reset lockout offline).

**Affected files:** `lib/offlineCrypto.ts` EDIT (PEPPER via native `pepper.exe` DPAPI; HMAC-sign lockout counters; `POS_PEPPER_DECRYPT_FAILURE` metric), `lib/pepper.exe` CREATE (tiny static native helper: `CryptUnprotectData` on Windows / `keychain`/`MachineGuid` fallback), `app/core/models.py` (`failed_attempts`/`locked_until` + `lockout_hmac` cols), `app/api/routers/auth_route.py` (mint/lockout HMAC), `tests/test_m10_hardening.py` (T54/T55), `tests/conftest.py` (blob-exfil-to-wrong-machine fixture).

---

**Matrix additions (Appendix C):**

| # | Subsystem | Risk | Refinement | Key invariant preserved |
|---|---|---|---|---|
| 20 | Multi-terminal SQLite | SMB corruption + inventory drift across kiosks | per-terminal local SQLite + merge-sync hub with `(terminal_id, local_seq)` order + `client_txn_id` dedup + cross-terminal over-sell flagging (C.1) | single-writer per terminal; net inventory = physical count; §3.4 single-writer preserved |
| 21 | OTA updates | 100 MB reinstall for a 1-line fix over flaky link | layered (bin/backend/frontend/schema) sha256-addressed + ranged resume + atomic swap + N-version rollback + B.8 post-swap migrations (C.2) | only changed layers fetched; kiosk never half-updated |
| 22 | RAM exhaustion (4–8 GB) | Chromium+Node+FastAPI+Caddy+SQLite swap-thrash on eMMC | hard caps (Node `--max-old-space-size`, NSSM Job-object/ working-set, Caddy 0.2 GB, SQLite cache/mmap) + perf budget + swap-avoid + auto-restart on cap (C.3) | footprint ≤ budget (4 GB ~90%); no swap growth under load |
| 23 | Local PIN offline brute-force | exfiltrated 4–6 digit PIN hash searched offline, bypassing §6 lockout | device-bound `PEPPER` via DPAPI (C.4) + HMAC-signed lockout counters; DB dump alone cannot confirm any PIN | exfiltrated DB is offline-useless; ≥10⁸ work-factor per guess even with salt |

**Status:** All eight M10 concerns + the NSSM/Inno-Setup deployment blueprint (§13) + the three edge-case guardrails (§2 PBKDF2 iteration calibration, §7 Lamport re-seed guard, §9 vendored `bin/` binaries) + the ten additional engineering concerns (Appendix B.1–B.10) + the four scaling/hardening solutions (Appendix C.1–C.4: multi-terminal merge-sync, granular resumable OTA, RAM caps, device-bound PIN peppering) are resolved with data models, API contracts, workflow updates, tests (T1–T55, H19–H39), an affected-files index, and validation gates. `410 Gone` over-sell handling, single-worker write safety, FEFO stock logic, and integer-cents money math are explicitly preserved as non-negotiables. This unified plan supersedes all prior files.

---

<a id="toc"></a>
## Table of Contents (final)
