# Mobile Pharmacy App — Architecture & Implementation Plan

## 1. Objective

Build a **React Native + Expo** mobile application that:
- Reuses the **existing FastAPI backend** (`backend_fastapi/`) — no new backend runtime.
- Preserves the **functional completeness** of the legacy Python/Tkinter desktop suite.
- Adopts the **current web stack's patterns**: async typed API services, Zustand domain stores, offline-first merge-sync (Lamport LWW + `client_txn_id` idempotency), bigint-cents money math, JWT auth.

**Target:** Offline-first mobile POS + inventory management for pharmacy technicians walking the floor.

---

## 2. Key Findings From Source Audit

### 2.1 Legacy Desktop (Python/Tkinter)
- **Inventory model:** Serialized — 1 DB row = 1 physical box. `internal_barcode` is the source-of-truth, format `{VENDOR[:3]}-{uuid6}`.
- **Core workflows:** Add Product, Receive Inventory (queue PO), Inventory browser, POS checkout, Sales Report, Label printing, Backup, Audit trail.
- **File:** `main_app.py`, `ui*.py`, `database.py`, `barcode_logic.py`.

### 2.2 Current Web Stack (FastAPI + Next.js 16)
- **Backend:** Async FastAPI 0.141, SQLAlchemy 2.0/AsyncSession, aiosqlite (dev), asyncpg (prod).
  - 31 routers registered in `main.py` (auth, pos, inventory, pos-shift, license, sync, patients, alerts, etc.).
  - Uniform error contract: `{ error: { code, message, details } }` via `AppException` handler.
  - Services: `pos_service`, `inventory_service`, `movement_service`, `sync_service`, `receipt_engine`, `hybrid_ocr_engine`, etc.
- **Frontend (Next.js 16):**
  - Typed API: `lib/api.ts` (Axios + 401-refresh interceptor) + 31 typed modules in `lib/api/*.ts`.
  - Typed contracts: `types/contracts.ts` — 1:1 mirror of `schemas.py`; money as JSON strings.
  - Offline storage: `lib/db.ts` (promise-based IndexedDB wrapper — **not available in React Native**).
  - Offline queue: `lib/offlineQueue.ts` — Lamport counter (`local_seq`), `client_txn_id` idempotency key, stores in IndexedDB (`STORE_QUEUE`).
  - Merge-sync: `lib/api/sync.ts` → `POST /api/v1/sync/push` with batch entries; `GET /discrepancies`.
  - 3-tier sync lock: `lib/syncLock.ts` — T1 in-memory, T2 BroadcastChannel (browser-only), T3 server probe.
  - POS store: `stores/posStore.ts` — per-tab cart, persisted to IndexedDB, recoverable carts, GC via `storagePersist.ts`.
  - Auth: `lib/api/auth.ts` — OAuth2PasswordBearer, JWT access/refresh tokens, HTTP-only cookie or localStorage.
  - Barcode: **Barcode-wedge** keyboard-input pattern on web kiosk POS (no camera scanning).
  - Money: `lib/decimalCurrency.ts` — bigint-cents, no floating point.

### 2.3 Critical Mobile Adaptations Required
| Web Pattern | Mobile Equivalent |
|---|---|
| IndexedDB (`lib/db.ts`) | `@react-native-async-storage/async-storage` + `react-native-sqlite-storage` (optional for large inventory caches) |
| BroadcastChannel (SyncLock T2) | In-memory lock only (single-process RN); server probe (T3) retained |
| `localStorage` (tokens, device_id) | AsyncStorage |
| Barcode-wedge keyboard input | Camera-based scanning (`expo-camera` + `react-native-vision-camera` + `react-native-camera-codegen` / `zxing`) |
| `window.print()` thermal labels | `react-native-thermal-printer` (ESC/POS) or native print intent |
| Axios interceptors | `axios` with `react-native-polyfill` (URL polyfill) or `fetch` wrapper |

---

## 3. Phase 1: Legacy Feature Matrix & Mobile Requirements

### 3.1 Feature Matrix

| # | Legacy Feature | Current API Endpoint(s) | Mobile UI Requirement | Offline? |
|---|---|---|---|---|
| F1 | **Login / Auth** | `POST /api/v1/auth/login`, `POST /auth/refresh`, `GET /auth/me` | Username/password form, PIN kiosk mode | Token refresh; cached session |
| F2 | **Shift open/close/preview** | `POST /api/v1/pos/shift/open`, `GET /pos/shift/{id}/preview`, `POST /pos/shift/close` | Shift management screen with opening float entry | Local shift state until sync |
| F3 | **Barcode scan (product lookup)** | `GET /api/v1/inventory/by-barcode/{barcode}` | Camera scanner → result → product detail | Recent scans cached |
| F4 | **Add Product (manual)** | `POST /api/v1/inventory/`, `GET /api/v1/inventory/{id}` | Product creation form with all fields from `ProductBase` | Queue if offline |
| F5 | **Receive Inventory (PO queue)** | `POST /api/v1/po/`, `POST /api/v1/receiving/`, `POST /api/v1/inventory/receive` | PO creation, line-item receipt scanning, qty adjustment | Queue + merge on reconnect |
| F6 | **Inventory browser** | `GET /api/v1/inventory/` (paginated), `GET /api/v1/inventory/low-stock` | Searchable product list, infinite scroll, low-stock filter | SQLite cache of last page |
| F7 | **Adjust stock (inventory count)** | `POST /api/v1/inventory/{id}/adjust`, `POST /api/v1/movements` | Batch count mode, reason selector, qty diff | Queue + sync |
| F8 | **POS checkout** | `POST /api/v1/pos/checkout` | Cart screen, barcode add, qty edit, discount, tax-exempt, split payment | **Primary offline use case** — full cart persisted locally, replay on reconnect |
| F9 | **POS returns** | `POST /api/v1/pos/return` | Return item from receipt search | Queue |
| F10 | **Drawer movements** | `POST /api/v1/pos/drawer` | Drop/payout/speed-adjust forms, manager approval PIN | Offline crypto (PBKDF2) for local approval when backend unreachable |
| F11 | **Sales Report / Analytics** | `GET /api/v1/analytics/...` | Period picker, revenue/cogs/profit summary, top products | Read-only (require online) |
| F12 | **Print thermal label** | `GET /api/v1/labels/{id}` (template), `POST /api/v1/labels/render` | Template selector, preview, Bluetooth/ESC-POS print | Template cached |
| F13 | **Patient lookup** | `GET /api/v1/patients/` | Search + detail view for Rx-linked sales | Cache recently viewed |
| F14 | **Audit trail** | `GET /api/v1/audit/` | Filterable event log (date, user, action) | Read-only |
| F15 | **Backup** | N/A (server-side) | Manual trigger via API, or auto-backup on sync | N/A — backend handles |
| F16 | **License check** | `POST /api/v1/license/validate`, `GET /license/status` | App-start license gate (blocking) | Allow grace period |

### 3.2 Mobile-Exclusive Features
- **Barcode scanning** via device camera (F3 expansion).
- **Bluetooth thermal printer** pairing and printing.
- **Push notifications** for low-stock / expiry alerts (using expo-notifications).

---

## 4. Phase 2: Backend Addendums

### 4.1 Existing API — Reused As-Is
All endpoints under `/api/v1/` are available. Key routers:
- `auth_route` — login, refresh, me
- `pos_route` — checkout, return, drawer, shift lifecycle
- `inventory_route` — CRUD, receive, adjust, low-stock, by-barcode
- `sync_route` — `POST /sync/push` (batch merge), `GET /discrepancies`
- `analytics_route`, `audit_route`, `patients_route`, `po_route`, `receiving_route`

### 4.2 New Endpoints To Add (Minimal)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/mobile/offline-ack` | POST | Ack backend receipt of a batch of `client_txn_id`s — lets mobile GC its offline queue |
| `/api/v1/pos/lock` | POST | Server-side sync lock probe (T3 in `SyncLock.serverProbe`) — acquires/releases lock by nonce |
| `/api/v1/inventory/by-barcode/{barcode}` | GET | Single-product lookup by `internal_barcode` (if not already present) |
| `/api/v1/labels/render-mobile` | POST | Render label to a mobile-friendly format (PNG base64 or ESCPOS bytes) |

### 4.3 Backend Changes Summary
- Add 2-4 lightweight endpoints to `pos_route` / `sync_route`.
- No schema changes needed — all required schemas exist in `schemas.py`.

---

## 5. Phase 3: Mobile Frontend Architecture

### 5.1 Tech Stack
| Layer | Library | Notes |
|---|---|---|
| Framework | **Expo SDK 52** / **React Native 0.76** | Per directive |
| Navigation | **React Navigation v7** | Bottom tabs + stack |
| State | **Zustand** (port from web stores) | Same API as web |
| Networking | **axios** + `@react-native-polyfill` | Same interceptor pattern as `lib/api.ts` |
| Storage | **@react-native-async-storage/async-storage** | Replaces IndexedDB for tokens, device_id, small caches |
| Offline DB | **react-native-sqlite-storage** (optional) | Product/inventory LRU cache for large catalogs |
| Barcode | **expo-camera** + `react-native-vision-camera` + `react-native-vision-camera-code-scanner` | Camera-based, not wedge |
| Printing | **react-native-thermal-printer** | ESCPOS via Bluetooth or built-in printer |
| Money | **bigint-cents** (port `lib/decimalCurrency.ts` to TS utility) | No floats |
| Notifications | **expo-notifications** | Low-stock / expiry alerts |
| Device ID | **expo-device** `os.internalId` | Stable per-device identity for sync |

### 5.2 Folder Structure
```
mobile/
├── app/                          # Expo Router (or RN Navigation)
│   ├── _layout.tsx               # Root layout, auth gate
│   ├── (auth)/login.tsx
│   ├── (auth)/pin.tsx            # Kiosk PIN mode
│   ├── (main)/_layout.tsx        # Bottom tab nav
│   ├── (main)/pos/               # POS screens
│   ├── (main)/inventory/
│   ├── (main)/receiving/
│   ├── (main)/shifts/
│   ├── (main)/analytics/
│   ├── (main)/patients/
│   ├── (main)/audit/
│   ├── (main)/settings/
├── api/                          # Typed API services (port from lib/api/*.ts)
│   ├── client.ts                 # Axios instance + interceptors
│   ├── auth.ts
│   ├── pos.ts
│   ├── inventory.ts
│   ├── sync.ts
│   ├── shift.ts
│   └── ...
├── stores/                       # Zustand stores (port from web stores)
│   ├── posStore.ts               # Offline-first cart + sync
│   ├── authStore.ts
│   ├── inventoryStore.ts
│   ├── receivingStore.ts
│   └── ...
├── lib/
│   ├── offlineQueue.ts           # Port: AsyncStorage instead of IndexedDB
│   ├── syncLock.ts               # Port: in-memory + server probe
│   ├── deviceId.ts               # Port: use expo-device
│   ├── decimalCurrency.ts        # Port: bigint-cents
│   └── storagePersist.ts         # Adapt: AsyncStorage key-value
├── types/
│   └── contracts.ts              # Mirror backend schemas (port from web)
├── components/
│   ├── BarcodeScanner.tsx
│   ├── CartItem.tsx
│   ├── MoneyInput.tsx
│   └── ReceiptPrinter.tsx
├── hooks/
│   ├── useBarcodeScanner.ts
│   ├── useSync.ts
│   └── useShift.ts
└── utils/
    └── thermalPrinter.ts        # ESCPOS abstraction
```

### 5.3 Offline-First POS Flow (Core)

```mermaid
sequenceDiagram
    participant Scanner as Camera Scanner
    participant Cart as posStore (Zustand)
    participant Queue as OfflineQueue (AsyncStorage)
    participant Lock as SyncLock
    participant API as FastAPI Backend
    participant Print as Thermal Printer

    Scanner->>Cart: scan barcode
    Cart->>Cart: addLine(product) — immediate local update
    Cart->>Queue: enqueueCheckout(cartSnapshot) — persisted to AsyncStorage
    Cart->>API: POST /pos/checkout (optimistic, background)
    alt Online
        API-->>Cart: CheckoutResult
        Queue->>Queue: removeEntry(id)
        Cart->>Print: print receipt (ESC/POS)
    alt Offline / Network Error
        Queue->>Lock: acquire() — in-memory + server probe
        Lock-->>Queue: granted
        Queue->>API: POST /sync/push {entries[]}
        API-->>Queue: SyncPushResult {server_ack_ids[]}
        Queue->>Queue: GC ack'd entries + bump lamport
        Lock->>Lock: release()
        Cart->>Print: print receipt from local snapshot
    end
```

### 5.4 Data Flow: Offline Queue Persistence
1. **Web app:** `enqueueCheckout()` writes to IndexedDB `STORE_QUEUE`.
2. **Mobile port:** `enqueueCheckout()` writes to AsyncStorage key `offline_queue` as a JSON array.
3. On app start / reconnect / foregrounded: `flushQueue()` attempts replay.
4. **Merge-sync:** `pushSync(entries[])` sends batch to `/api/v1/sync/push`.
   - Each `SyncPushEntry`: `{ client_txn_id, local_seq, device_id, type, payload, enqueued_at }`.
   - Backend applies idempotency: if `client_txn_id` already processed, skip.
   - Backend returns `{ processed: [...]ids, skipped: [...]ids, discrepancies: [...] }`.
5. Mobile GC: remove entries whose `client_txn_id` is in `processed`.

### 5.5 Money Convention
- **All money fields are strings** (bigint cents) on the wire, matching backend `Decimal` serialization.
- `lib/decimalCurrency.ts` provides: `parseMoney(s): bigint`, `addMoney(a, b): string`, `formatMoney(cents: bigint, decimals): string`.
- UI: display formatted, parse to cents on input.

### 5.6 Security
- JWT access token (15 min) + refresh token (7 day) in AsyncStorage.
- 401 interceptor → call `/auth/refresh` → store new tokens → retry request.
- Manager PIN for drawer movements: PBKDF2-derived local hash (`lib/offlineCrypto.ts` port), self-wipes after 5 failed attempts.
- HTTPS only in production.

### 5.7 Barcode Scanning Strategy
- **Primary:** Device camera using `react-native-vision-camera-code-scanner` (ZXing under the hood).
- **Fallback:** Manual entry for `internal_barcode` (format check: `/^[A-Z0-9]{0,3}-[a-f0-9]{6}$/`).
- **Wedge mode:** Not applicable on mobile OS — but can still accept external Bluetooth scanner keyboard input (Android supports HID keyboard).

---

## 6. Phase 4: Algorithmic Workflows

### 6.1 Offline POS Checkout (Algorithmic)
```
ALGORITHM: processCheckoutOfflinely
INPUT: cartLines[], deviceId, shiftId, options{discount, taxExempt, payments}
OUTPUT: checkoutResult OR enqueuedEntry

1. snapshot = { lines, discount, taxExempt, payments, shift_id, device_id }
2. txnId = uuidv4()
3. seq = incrementLamport(deviceId)    // persisted in AsyncStorage
4. TRY:
5.   result = api.post('/pos/checkout', {
6.     ...snapshot,
6.     client_txn_id: txnId,
6.     local_seq: seq
7.   })
8.   return result
9. CATCH (network error / 5xx / timeout):
10.  entry = { client_txn_id: txnId, local_seq: seq, type: 'checkout',
11.              payload: snapshot, enqueued_at: now() }
12.  await enqueueEntry(entry)    // AsyncStorage
13.  scheduleBackgroundFlush()    // AppState / NetInfo listener
14.  return { offline: true, client_txn_id: txnId }
```

### 6.2 Merge-Sync Reconciliation
```
ALGORITHM: reconcileOfflineQueue
INPUT: none (reads from AsyncStorage queue)
OUTPUT: SyncReport { processed, skipped, conflicts }

1. entries = await getQueue() sorted by local_seq ASC
2. IF empty: return
3. lock = new SyncLock(deviceId, serverProbe=/pos/lock)
4. acquired = await lock.acquire()
5. IF !acquired: return (another flush is running)
6. TRY:
7.   result = await api.post('/sync/push', { entries })
8.   for id in result.processed: await removeEntry(id)
9.   for disc in result.discrepancies: surface to UI (resolve/dismiss)
10.  await advanceLamport(result.server_seq)
11. FINALLY: await lock.release()
```

### 6.3 Cart Recovery (Crash Protection)
- On app cold-start: read `cart_registry` from AsyncStorage.
- If a previous cart exists with `count > 0` and `age < 4h`: prompt "Recover unsynced cart?".
- This is a **single-device** model (no multi-tab on mobile), so no cross-process registry needed.

### 6.4 Label Rendering Pipeline (Port from FLOW_LOGIC.md)
1. Fetch template `GET /api/v1/label-templates/{id}` — cached to SQLite.
2. Render server-side via `POST /api/v1/labels/render-mobile` → returns ESCPOS bytes or PNG.
3. Send to paired Bluetooth printer via `react-native-thermal-printer`.

---

## 7. Implementation Roadmap

### Milestone A: Bootstrapping (Week 1)
1. `expo init mobile` — blank TS template, Expo SDK 52.
2. Install core deps: `zustand`, `axios`, `@react-native-async-storage/async-storage`, `react-navigation v7`, `@react-native-community/netinfo`.
3. Port `types/contracts.ts` (subset: auth, product, cart, checkout).
4. Port `lib/decimalCurrency.ts`.
5. Port `lib/api/client.ts` (Axios instance + interceptors).

### Milestone B: Auth + Shift + Inventory (Week 2-3)
1. Login screen, token persistence, 401 refresh interceptor.
2. Kiosk PIN mode.
3. Inventory list (paginated) + search + by-barcode lookup.
4. Product detail / create.
5. Shift open/close/preview.

### Milestone C: Offline POS (Week 3-4) — **Core**
1. Port `lib/offlineQueue.ts` (AsyncStorage → JSON array).
2. Port `lib/syncLock.ts` (in-memory + server probe).
3. Port `stores/posStore.ts` (cart, checkout, queue, recovery).
4. Port `lib/api/sync.ts`.
5. Camera barcode scanner integration.
6. Checkout flow: online + offline + merge-sync reconciliation.
7. Split payment, discount, tax-exempt.

### Milestone D: Receiving + Adjustments (Week 4-5)
1. PO creation + receipt scanning.
2. Stock adjustment / count mode.
3. Low-stock view.

### Milestone E: Analytics + Audit + Admin (Week 5)
1. Sales report with date range.
2. Audit log browser.
3. Settings: printer pairing, device info.

### Milestone F: Polish + License + Notifications (Week 6)
1. Grace-period license check on app start.
2. Expo push notifications for low-stock/expiry.
3. Receipt printing (ESC/POS).
4. Comprehensive offline tests (simulate network loss).

---

## 8. Open Questions

| # | Q | Recommendation |
|---|---|---|
| Q1 | **Barcode scanning:** Camera-based (primary) or also support Bluetooth HID scanner keyboards (Android)? | Both — camera by default; HID passthrough works automatically on Android for external scanners. No iOS HID. |
| Q2 | **Offline DB:** AsyncStorage only, or SQLite for large inventory caches? | AsyncStorage for auth/queue/cart; SQLite optional for inventory lookup if catalog > 5000 items. Defer SQLite until profiling shows need. |
| Q3 | **Navigation:** Expo Router or React Navigation v7? | React Navigation v7 (explicit control, matches web tab model). Switch to Expo Router if file-based routing is preferred. |
| Q4 | **Printing:** Only Bluetooth thermal (ESC/POS)? | Primary: Bluetooth. Secondary: system share intent (for email/PDF fallback). |
| Q5 | **Backend `/sync/push` idempotency:** Does current implementation dedupe by `client_txn_id` across devices? | ✅ **Verified:** `sync_service.py:39` calls `repo.find_by_client_txn_id()` — exact-once enforcement already present. No backend change needed. |

---

## 9. Validation Plan

| Milestone | Validation Criteria |
|---|---|
| A | App boots, login works, token persisted/refreshed. |
| B | Inventory list loads with pagination; barcode lookup returns product. |
| C | Checkout works online; cart survives reload; offline checkout queues; reconnecting flushes queue; exactly-once enforced (check server-side duplicate). |
| D | Receiving PO + qty adjustment queues offline, syncs correctly. |
| E | Analytics filters produce correct totals; audit log filters. |
| F | License gate blocks unlicensed devices; push notif fires; receipt prints. |

### Offline Simulation Test
```
1. Complete 3 checkout actions while online → confirmed on server.
2. Switch to offline mode (disable network).
3. Complete 2 checkout actions → should queue locally.
4. Re-enable network → queue flushes, 2 new sales appear (no duplicates).
5. Simulate crash mid-flush → restart → recovery prompt → reconcile completes.
```

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Camera dependency fails on low-end Android | Always provide manual barcode entry fallback |
| AsyncStorage corrupt on force-kill | Wrap all reads in try/catch + schema validation |
| Backend `/sync/push` not truly idempotent | Add server-side dedupe by `client_txn_id` if missing |
| Thermal printer Bluetooth pairing UX | Use `react-native-ble-manager` for BLE pairing dialog |
| Expo build size bloat | Tree-shake unused routers; lazy-load navigator screens |
