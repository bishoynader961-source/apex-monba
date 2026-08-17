# Technical Addendum — Operational & Security Refinements (Edge Retail Pharmacy POS)

> **Parent spec:** `.kilo/plans/1786620973404-m9-m10-precommit-pos-spec.md`
> **Date:** 2026-08-14
> **Scope:** Five operational/security gaps surfaced during review of the M9/M10 spec. This addendum is **additive** and **backward-compatible** — each refinement augments an existing mechanism without altering the proven FEFO/stock logic or the single-worker edge guarantee (§3.4). No source/DB files are modified here; this is a plan for a follow-up implementation agent.
> **Mode:** Plan only.

## 1. Concern 1 — Shift Reconciliation Formula Omits Cash Drops & Paid-Outs

### Critique
The refined formula (§4.2) `expected_cash = opening_float + Σ cash_tenders` is mathematically complete **only as a closed system**. Real pharmacy tills are an open system: cash both enters **and leaves** mid-shift.

- **Safe Drops** (skimming excess bill stock to a back-office safe once the drawer exceeds a threshold, e.g. \$400) are a *dealer-initiated outflow* — the cashier is authorized to remove cash to keep the working float manageable.
- **Paid-Outs / Petty Cash** (paying delivery drivers, restocking change funds, covering COHO/operational floats) are a *dealer-initiated outflow* as well.

Both reduce the physical count at close. If untracked, the variance engine sees `counted = opening + takers − (drops + payouts)` but computes `expected = opening + takers`, producing a **false short variance of −Σ(drops + payouts)**. At \$300 in drops, the system blocks shift close and forces a pointless manager override — a daily friction leak and a reconciliation false-positive that masks *real* drift.

The gap is missing **drawer-movement accounting**. The spec has no movement journal, no auth gate on outflows > threshold, and no classification (cashier-authored drop vs. manager-only paid-out).

### Refinement
Introduce a `drawer_movements` journal and split the formula into inflows vs. outflows.

**Data model** (`app/core/models.py`, new `DrawerMovement`):
```python
class DrawerMovement(Base):
    __tablename__ = "drawer_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"))
    # Type enum: cash_tender | float_add | cash_drop | paid_out | pickup | manager_adj
    type: Mapped[DrawerMovementType]
    amount_cents: Mapped[int]
    reason: Mapped[str | None]            # free-text; required for paid_out/pickup
    requires_approval: Mapped[bool]      # True for paid_out/pickup above threshold
    manager_txn_id: Mapped[int | None]   # FK → receipts.id when manager approval used
    created_by: Mapped[str]              # username
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

**Updated formula** (`§4.2`):
```math
expected\_cash = opening\_float + \sum cash\_tenders + \sum(float\_add,\; manager\_add) \;-\; \sum(cash\_drop,\; paid\_out,\; pickup)
```
Equivalently, net any time a till *loses* money to `cash_drop`/`paid_out`/`pickup` and net any time it *gains* to `float_add`. Closing variance:
```math
variance = counted\_cash - expected\_cash
```
A **true** float shortage (e.g. miscount, dropped bill) still surfaces as `variance < 0` — but only by the *actual* error amount, not the conflated drops+payouts.

**Authorization policy:**
- `cash_drop`: cashier-authored (below `DROP_THRESHOLD`, default \$400), auto-approved, logged.
- `paid_out`: cashier-authored up to `PAID_OUT_LIMIT` (\$50); above that → `ManagerApprovalDialog` (§14.5 token flow).
- `pickup`: manager-authored (always requires approval token).
- `manager_adj`: always requires approval token + reason.

**API** (`app/api/routers/pos_route.py`, new `POST /shift/{id}/drawer-movement`):
```python
class DrawerMovementIn(BaseModel):
    type: DrawerMovementType
    amount: DecimalString
    reason: str | None = None
    # manager_token validated by require_approval_token when type.requires_approval
```
Response writes a `Receipt`-linked record (`manager_txn_id` nullable) so the movement is auditable against the shift's receipt sequence.

### Tests
- **T23:** `test_shift_expected_cash_with_drop` — shift float \$100, tenders \$250 cash, drop \$150 → `expected_cash = 100 + 250 − 150 = 200`; `variance = 0`; close allowed.
- **T24:** `test_paid_out_requires_approval_over_threshold` — paid_out \$51 without `X-Approval-Token` → `409 ApprovalRequiredError`; with token → 201, movement recorded.

### Affected files
`app/core/models.py` (new `DrawerMovement` + enum), `app/api/routers/pos_route.py` (new route + shift-close variance query), `types/contracts.ts` (`DrawerMovementType`, `DrawerMovementIn`), `app/pos/ShiftCloseDialog.tsx` (variance display), `tests/test_m10_hardening.py` (T23/T24).

---

## 2. Offline Manager PIN Security — SHA-256 Brute-Force Risk

### Critique
§14.5.1 specifies an offline manager-approval fallback where the manager PIN is verified against a locally cached SHA-256 digest (`SHA-256(pin + salt)`). This is a **cryptographic misuse**: SHA-256 is a fast general-purpose hash, not a password/PIN derivation function. Consequences:

- **Throughput:** a mid-range laptop computes ~10⁸–10⁹ SHA-256 ops/sec in pure JS; in a browser console an attacker can read the cached digest from IndexedDB and brute-force a **4-digit PIN (10 000 space) in <10 ms**. A 6-digit PIN (~10⁶ space) falls in <1 s.
- **No attempt limiter persisted offline:** a counter reset to zero on every re-verification, so retries are unbounded across refreshes.
- **No lockout side-effect:** a compromised terminal gives the attacker a free offline PIN oracle.
- **Device uniformity:** a raw SHA-256 of the same PIN is identical across devices (modulo salt) — not a device-binding weakness *per se*, but it removes any per-terminal friction that a slow KDF would impose.

The risk is rated **Critical**: manager-override is the single most privileged action (shift close, over-sell, discounts), and the offline path was introduced precisely to keep the POS operable when the server is down — exactly the threat scenario an attacker exploits.

### Refinement
Replace raw-SHA-256 with a **slow, browser-native KDF** and add a **persisted, self-erase attempt limiter**.

**Choice of KDF:** **PBKDF2-HMAC-SHA256** via the WebCrypto `deriveBits` API. Rationale:
- **Built into every browser's WebCrypto** (no extra dependency) — adheres to Simplicity-First (§VI). Argon2id is stronger against GPU/ASIC but requires `argon2-browser` (WASM bundle, ~300 KB gzipped) and is out of scope for an edge pharmacy where a 200 k–600 k iteration PBKDF2 is sufficient against a JS-based console attack.
- Iterations: **200 000** (OWASP 2023 minimum for PBKDF2-SHA256). Each verification ≈ 80–120 ms in-browser — enough friction to make a 6-digit brute force take ≥ 300 days even with an open console.

**Policy blob** (extends §14.5.1, AES-GCM encrypted at rest):
```typescript
interface ManagerPolicy {
  username: string;
  salt: ArrayBuffer;          // per-(manager, device)
  kdf: { name: "PBKDF2"; iterations: number; hash: "SHA-256" };
  pin_hash: ArrayBuffer;      // PBKDF2(pin, salt, 256 bits)
  valid_until: number;        // epoch ms — re-auth online after this
  attempt_counter: number;    // persisted encrypted; self-erases at OFFLINE_MAX_ATTEMPTS
}
```

**Verification** (`lib/offlineCrypto.ts`, replaces current SHA-256 check):
```typescript
export const OFFLINE_MAX_ATTEMPTS = 3;

const derivePin = async (pin: string, salt: ArrayBuffer, iter: number): Promise<ArrayBuffer> => {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pin), "PBKDF2", false, ["deriveBits"]);
  return crypto.subtle.deriveBits({ name: "PBKDF2", salt, iterations: iter, hash: "SHA-256" }, base, 256);
};

export async function verifyPinOffline(pin: string, policy: ManagerPolicy): Promise<boolean> {
  const derived = await derivePin(pin, policy.salt, policy.kdf.iterations);
  const ok = await crypto.subtle.timingSafeEqual(derived, policy.pin_hash);   // constant-time
  if (!ok) {
    policy.attempt_counter += 1;                                  // persist via db.put
    if (policy.attempt_counter >= OFFLINE_MAX_ATTEMPTS) {
      await db.delete("manager_policies", policy.username);    // self-erase → forces online re-auth
      throw new OfflinePinLockedError("policy wiped after max attempts");
    }
    return false;
  }
  policy.attempt_counter = 0;                                     // reset on success
  await db.put("manager_policies", policy);
  return true;
}
```

**Attempt limiter semantics:**
- Encrypted (AES-GCM), persisted in IndexedDB `manager_policies`.
- Resets to 0 on (a) successful offline verification, (b) any *online* `verify-pin` success (server returns fresh policy).
- At `OFFLINE_MAX_ATTEMPTS` (default 3) incorrect attempts → **delete the policy blob entirely** → the terminal requires an online manager re-verification to restore offline override capability. This makes brute-force non-permanent: an attacker who locks the terminal has *reduced* functionality, not gained it.

**Audit note:** the offline `approval_token` continues to carry `offline: true` + `X-Approval-Source: offline` header (§14.5.1) so the server records the approval and flags it for later online reconciliation. No change to the token contract.

### Tests
- **T25:** `test_offline_pin_pbkdf2_brute_force_resistance` — assert `derivePin` is async + ≥150 ms; `verifyPinOffline` wrong PIN 2× → `attempt_counter=2`; 3rd wrong → policy row deleted (assert `db.get → undefined`); correct PIN resets counter to 0.
- **H19:** `test_offline_pin_constant_time_compare` — `timingSafeEqual` called on equal-length buffers; wrong PIN does not leak length via early throw.

### Affected files
`lib/offlineCrypto.ts` (REWRITE — replace SHA-256 with PBKDF2 + attempt-wipe), `lib/db.ts` (add `manager_policies` store), `app/pos/ManagerApprovalDialog.tsx` (wire `verifyPinOffline`), `tests/test_m10_hardening.py` + `lib/offlineCrypto.test.ts` (T25/H19).

---

## 3. sessionStorage Active Cart Volatility on Browser Crash

### Critique
§7.6.2 moves `activeCart` to `sessionStorage` to prevent multi-tab interference (Tab B can't clobber Tab A's draft). Correctness for the multi-tab case: **fixed**. Durability for the single-tab crash case: **regressed**.

`sessionStorage` is scoped to the **tab's browsing context** and is destroyed on **any** of:
- browser process crash (edge kiosks lose power; pharmacy POS runs on Windows thin clients prone to power events),
- "restore closed tab" without explicit restore,
- force-quit of the terminal app,
- renderer process kill by the OS under memory pressure (common on 4 GB RAM edge terminals).

Result: a cashier 18 lines into a 25-drug prescription loses the entire cart with no recovery path — a direct **revenue + workflow** loss and a repeat-of-order liability. The refinement to `sessionStorage` traded an *interference* failure mode for a *loss* failure mode, net-negative for a high-throughput pharmacy lane.

### Refinement
Keep **tab isolation** but move durability to `localStorage`, keyed by a **per-tab UUID** so tabs still never collide.

**Model:** `localStorage` holds `pos_activecart_tab_{tabId}` (and a parallel `pos_activecart_meta_{tabId}` with last-write timestamp). `heldTickets` remains shared under `pos_held_v1`.

**tabId lifecycle:**
- On store `init()` (first call per tab): read `sessionStorage.tab_id`; if absent, generate `crypto.randomUUID()`, store it in `sessionStorage.tab_id` (this re-creates on tab restore, giving the restored tab a fresh session UUID — acceptable; a brand-new cart tab is expected after a crash restore).
- Active cart is read from / written to `localStorage[pos_activecart_tab_{tabId}]`.

**Recovery prompt:** on `hydrate()`, scan `localStorage` for keys matching `pos_activecart_tab_*` whose `meta.last_write > now − RECOVERY_WINDOW (4 h)` and whose `tabId ≠ current tabId`. Surface a non-blocking "Unsaved drafts found — restore?" toast (auto-dismiss in 30 s). Restoring a draft copies it into the **current** tab's cart (deep-merge validated against live stock).

**Crash-cleanup:** tabs cannot reliably `beforeunload`-delete from `localStorage` (fires are throttled/dropped). Instead rely on the 4 h staleness window — drafts older than 4 h are GC'd on next `persist()` sweep (§7.6.1 `runGarbageCollection` extended to cart tabs). This bounds local storage growth without relying on `beforeunload`.

**Trade-off:** the restored-tab-fresh-UUID means a crash-reopened tab starts empty (correct — the old tab is dead) rather than racing its own stale self. True *cross-tab* interference is still impossible because each tab writes only its own key.

### Tests
- **H20:** `test_cart_surives_browser_restart` — `persist()` writes to `localStorage[pos_activecart_tab_{id}]`; mock a "new page load" (call `hydrate()` with same `tabId`) → cart rehydrated from `localStorage`.
- **H21:** `test_unsaved_drafts_recovery_prompt` — plant a `pos_activecart_tab_OLD` key (last_write 1 h ago) + current tab; `hydrate()` emits recovery candidates; selecting one deep-merges into activeCart.
- **H22:** `test_no_cross_tab_clobber` — Tab A (`tabId=AAA`) adds 3 lines; Tab B (`tabId=BBB`) adds 5; both `localStorage` keys independent; `heldTickets` still shared.

### Affected files
`stores/posStore.ts` (REWRITE hydrate/persist: `sessionStorage.tab_id` + `localStorage` per-tab keys), `lib/storagePersist.ts` (add `RECOVERY_WINDOW` + `sweepStaleTabs`), `app/pos/page.tsx` (recovery toast), `stores/posStore.test.ts` (H20–H22).

---

## 4. Expired Lot Handling During Offline Replay

### Critique
§4.5 defines the sync-loop routing: `400 → retry max 3` and `410 → failed_queue / discrepancy`. The flaw is **error-class conflation at the API boundary**: an expired-recalled-missing lot is a *server-side inventory-state* condition, but it is indistinguishable from a *malformed-payload* client error under a generic `400`.

Scenario: a transaction is parked offline on Monday using Lot X (`expires_at = Mon 00:00`). Server sync runs Tuesday. The `allocate()` stock check now sees Lot X as expired. If the validator raises a generic `ValidationError`, the endpoint returns `400` → §4.5 retries 3× (futile — the lot stays expired) → then `failed_queue` **without** hitting the `DiscrepanciesPanel`. The manager never sees it; the transaction is dead-lettered into a generic failure bin. This is a **stockout-masking** defect: a real, resolvable discrepancy (re-pick lots, restock, or manager override) is hidden.

The root cause is that *inventory state staleness* must be a first-class error class distinct from *payload validation*.

### Refinement
Promote lot/batch state failures during replay to a dedicated **HTTP 410 Gone** with a structured `reason`, and extend §4.5 to route that reason into the discrepancy workflow with a category.

**API contract** (`app/api/routers/pos_route.py`, `POST /pos/checkout`, replay path):
Add a domain exception hierarchy:
```python
class StockStateError(HTTPException):        # 410 Gone — server inventory state invalidated
    def __init__(self, reason: str, details: dict):
        super().__init__(status_code=410, detail={"reason": reason, **details})

class ExpiredLotError(StockStateError):      # subclass, reason="LOT_EXPIRED"
    ...
class RecalledLotError(StockStateError):     # reason="LOT_RECALLED"
    ...
class MissingLotError(StockStateError):      # reason="LOT_MISSING"
    ...
```
In `PosService.allocate()` (or `inventory_service.py`), the FEFO dedup check distinguishes:
- `ValidationError` (missing fields, negative qty, malformed `client_txn_id`) → `400` (retryable client fix).
- `ExpiredLotError` / `RecalledLotError` / `MissingLotError` → raise `StockStateError` → `410 Gone` with body `{ reason, lot_number, expires_at?, suggestion: "restock"|"re-pick" }` (fastAPI auto-serializes to JSON).

**§4.5 sync-loop update** (extend the state machine):
```
├─ 410 → move to failed_queue
│        set offline_txns.status='discrepant', reason=<reason from body>,
│        reconciliation_flag=0
│        surface "Inventory Discrepancy Alert" in the UI → DiscrepanciesPanel pre-filtered
│        by reason = LOT_EXPIRED | LOT_RECALLED | LOT_MISSING
```
> Note: `status='over_sold'` is a *narrower* legacy label. Rename the column value to `discrepant` + keep `reason` for classification; the `DiscrepanciesPanel` (§4.4) groups by reason and offers context-appropriate actions: "Re-pick alternate lots (FEFO)", "Restock this lot", "Manager override (token)".

**Idempotency safety:** because the transaction is `410`-routed (not retried), the `client_txn_id` must **not** be auto-removed from `outbox` — it stays `discrepant` until a manager resolves it (restock → server-side re-validate → `200`; or override → `200` with manager token). This preserves the exact-once receipt semantics.

### Tests
- **T26:** `test_expired_lot_replay_returns_410` — park txn against Lot X (`expires_at` in past); replay → `410`, body `reason=LOT_EXPIRED`, `suggestion=restock`; outbox status `discrepant`; NOT retried.
- **T27:** `test_recalled_lot_routes_to_discrepancy_panel` — `POST /pos/checkout` replay with a recalled lot → 410 → `offlineQueue.markDiscrepant` → `DiscrepanciesPanel` query surfaces it (count increments).
- **T28:** `test_malformed_payload_still_400_retry` — drop a `client_txn_id` → `400` → retried (assert POST called 3× then `failed`). Ensures the refinement doesn't broaden 410 routing to genuine validation errors.

### Affected files
`app/core/exceptions.py` (extend `StockStateError` hierarchy), `app/services/inventory_service.py` / `pos_service.py` (`allocate()` raises typed exceptions), `app/api/routers/pos_route.py` (raise → 410 mapping), `lib/offlineQueue.ts` (rename `markOversold`→`markDiscrepant` + `reason` field), `app/pos/DiscrepanciesPanel.tsx` (reason grouping + actions), `tests/test_m10_hardening.py` (T26–T28).

---

## 5. Web Locks API Compatibility — Fallback for Legacy Edge Hardware

### Critique
§14.2 mandates `navigator.locks.request('offline_sync', executeSyncLoop)` to guarantee single-tab replay. **Correct for modern browsers.** **Fatal for legacy hardware.**

Pharmacy POS edge deployments use a heterogeneous fleet:
- Modern Chromium kiosks (Web Locks ✅).
- Legacy Windows-embedded thin clients running a pinned WebView2 or an old Chromium 70 wrapper (Web Locks ❌).
- Some deployments embed a Qt WebEngine or an Electron wrapper that lags — `navigator.locks` may exist but be buggy.

If `navigator.locks` is `undefined`, the current `syncOfflineQueueWithLock()` **throws** `TypeError: Cannot read properties of undefined`, the `online` event handler rejects, and `offlineQueue` replays silently stop. Because the POS only syncs on the `online` event (LAN restore), this manifests as **permanent silent data loss** of parked transactions until a manual restart — a critical availability defect on the exact hardware class least likely to be manually troubleshot.

The failure mode is also **silent**: no UI surfaces "sync blocked", no retry.

### Refinement
Progressive enhancement with a **three-tier lock fallback chain**, each tier releasing on completion/error with stale-recovery for crashed holders.

**TypeScript implementation** (`lib/syncLock.ts` — new module):
```typescript
const SYNC_LOCK_ID = "pharmacy_offline_sync_v1";
const STALE_MS = 30_000;                // reclaim after 30 s of no heartbeat

export async function syncOfflineQueueWithLock(): Promise<void> {
  await acquireSyncLock(SYNC_LOCK_ID, async () => {
    await executeSyncLoop();            // §7.7
  });
}

type LockTier = "weblocks" | "broadcast" | "localstorage";

class SyncMutex implements Disposable {
  private tier: LockTier;
  private heartbeat: any;
  constructor(tier: LockTier) { this.tier = tier; }
  release() { clearInterval(this.heartbeat); /* tier-specific release */ }
  [Symbol.dispose]() { this.release(); }
}

export async function acquireSyncLock(id: string, work: () => Promise<void>): Promise<void> {
  // Tier 1: Web Locks API (preferred)
  if (typeof navigator !== "undefined" && "locks" in navigator && navigator.locks.request) {
    return navigator.locks.request(id, { steal: true, mode: "exclusive" }, (lock) => {
      if (!lock) throw new Error("could not acquire web lock");
      return work();
    });
  }
  // Tier 2: BroadcastChannel mutex (same-origin tabs, older browsers)
  if (typeof BroadcastChannel !== "undefined") {
    return runBroadcastMutex(id, work, STALE_MS);
  }
  // Tier 3: localStorage timestamp lock (universal, degrades under tab crashes)
  return runLocalStorageMutex(id, work, STALE_MS);
}
```

**Stale-lock recovery** (critical for Tier 2/3 since a crashed holder leaves a dead lock):
- **BroadcastChannel:** holder posts `{ cmd: "heartbeat" }` every 5 s; if a contender sees no heartbeat for `> STALE_MS`, it reclaims by broadcasting `{ cmd: "steal", ownerId: contenderId }` and waits for acknowledgment. Holder, on `steal`, releases.
- **localStorage:** contender reads `key`; if `ownerId !== self && ts < now − STALE_MS` → overwrite (claim). On release, `delete key`. On crash, the 30 s staleness window bounds the outage.

**Failure semantics:** the lock `finally` block always releases; `executeSyncLoop` runs exactly once per `online` event across all tabs.

### Tests
- **T29:** `test_lock_fallback_chain` — mock `navigator.locks = undefined`, `BroadcastChannel = undefined`; assert `syncOfflineQueueWithLock()` falls through to localStorage tier and `executeSyncLoop` still invoked exactly once.
- **H23:** `test_stale_lock_reclamation` — plant a `localStorage` lock with `ts = now − 40s` (stale); assert contender reclaims and runs the loop; assert a fresh (non-stale) lock is NOT reclaimed.

### Affected files
`lib/syncLock.ts` (NEW — `acquireSyncLock`, `runBroadcastMutex`, `runLocalStorageMutex`), `lib/offlineQueue.ts` (replace inline `navigator.locks.request` with `syncOfflineQueueWithLock()` re-export), `.feature-detection` note for `BroadcastChannel` polyfill, `tests/test_m10_hardening.py` (T29), `stores/posStore.test.ts` (H23).

---

## Updated Summary Table of Recommendations

| # | Subsystem | Existing Spec | Identified Risk | Recommended Refinement |
|---|---|---|---|---|
| 1 | Shift Reconciliation | `expected = float + Σ cash_tenders` | False short variance from untracked cash drops / paid-outs | `drawer_movements` journal; `expected = float + Σ inflows − Σ(cash_drop + paid_out)`; auth gating by amount |
| 2 | Offline PIN | §14.5.1 WebCrypto SHA-256 | <10 ms console brute-force; no persisted attempt limiter | PBKDF2-HMAC-SHA256 (200 k iters) + constant-time compare + encrypted attempt counter; self-wipe at 3 failures |
| 3 | Cart Persistence | §7.6.2 `sessionStorage` activeCart | Total cart loss on browser crash / power loss; recovery impossible | `localStorage` keyed by per-tab UUID (`pos_activecart_tab_{tabId}`) + recovery prompt + 4 h staleness GC; heldTickets shared |
| 4 | Offline Replay | §4.5: `400 retry / 410 discrepancy` | Expired/recall/missing lot returns generic 400 → futile retries → dead-letter, masked from manager | Typed `StockStateError` → HTTP 410 with `reason`; §4.5 routes reason to `discrepant` + `DiscrepanciesPanel` grouping; malformed payload still 400-retry |
| 5 | Sync Locking | §14.2 `navigator.locks.request` | TypeError on legacy WebViews → silent permanent replay halt | Three-tier fallback: WebLocks → BroadcastChannel (heartbeat/steal) → localStorage timestamp (stale 30 s reclaim) |

## Rollout / Migration Notes
- **Backward compatibility:** all five refinements are additive. The `drawer_movements` table is `NULL`-safe (shifts created before the migration yield `Σ outflows = 0`, so `expected_cash` reduces to the prior formula — no reopening of historical shifts). The `reconciliation_flag` and `reason` columns extend, not replace, existing `outbox`/`offline_txns` schema.
- **Data migration:** `ALTER TABLE offline_txns ADD COLUMN reason TEXT` (nullable) + backfill `'over_sold'` for existing rows. `DrawerMovement` table is new (no backfill needed).
- **Operational:** the KDF iteration count (200 k) is tuned for a 2018-era Celeron thin client (~120 ms per verify — perceptible but acceptable). Re-tune down to 120 k only if field latency reports are adverse.
- **Feature flag:** expose `POS_OFFLINE_PIN_KDF`, `POS_RECOVERY_WINDOW_MS`, `SYNC_LOCK_TIER` as env overrides for staged rollout on the legacy fleet.

## Validation Plan (new gates)
- Pre-commit: `ruff` + `pytest tests/test_m10_hardening.py::test_shift_expected_cash_with_drop test_paid_out_requires_approval_over_threshold test_expired_lot_replay_returns_410 test_recalled_lot_routes_to_discrepancy_panel test_malformed_payload_still_400_retry test_lock_fallback_chain -q` → all pass; `tsc --noEmit` 0; `vitest run lib/offlineCrypto.test.ts stores/posStore.test.ts` → H19–H23 pass.
- Post-deploy smoke: exercise a safe-drop mid-shift → close → `variance ≈ 0`; trigger offline PIN 4× max attempts → assert policy wiped; verify `DiscrepanciesPanel` surfaces a `LOT_EXPIRED` 410 (not a 400 retry loop).
