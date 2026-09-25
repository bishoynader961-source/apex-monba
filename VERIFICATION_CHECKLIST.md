# UI & Structural Quality Gate Checklist

## 1. Boundary & Data Stretch Stress-Test
- [ ] **Extreme Value Test:** Inject a product name with 50+ characters (e.g., "Aspirin Coated Tablets USP 500mg Extra Strength Non-Drowsy Max"). Does the text wrap cleanly, or does it blowout widget boundaries?
- [ ] **Viewport Boundary Test:** Resize the application window to its minimum allowed size. Are all buttons, entries, and sidebar controls completely visible and reachable via scrolling?
- [ ] **Dynamic Scaling Test:** Open the window on a lower-resolution layout. Is the properties panel completely intact?

## 2. Process Independence & Subprocesses
- [ ] **Asynchronous Lock Check:** Ensure the main application UI thread remains 100% responsive (no spinning cursor/freeze) while a barcode or label template is processing or printing.
- [ ] **Console Leak Check:** Verify that no hidden command prompt windows spawn when launching secondary windows or subprocesses.

## 3. Web / Kiosk (Next.js POS) — ADDED
The legacy checks above target the Tkinter desktop app. For the edge kiosk web POS
(`app/pos/page.tsx` + `stores/posStore.ts`) the equivalent gates are:
- [x] **Responsive layout:** POS terminal renders at 1024×600 (common kiosk res) with no boundary blowout; long drug names wrap (no horizontal scroll/clip).
- [x] **No leaked subprocess:** All I/O is in-browser (IndexedDB, Web Crypto, BroadcastChannel) or via the FastAPI loopback — no child process / console window.
- [x] **Hydration:** `useHydration` gates render until the offline queue loads; no empty-flash of a stale cart.
- [x] **Offline banner:** `OfflineSyncBanner` is visible whenever `offlineCount > 0`; manual "Sync now" triggers `flushQueue`.
- [x] **Money safety:** pricing/tax/totals use `lib/decimalCurrency` (bigint cents) — no `float` in the money path (proven by grep + `decimalCurrency.test.ts`).
- [x] **Manager approval:** drawer movement / shift close require `ManagerApprovalDialog` → `/api/v1/pos/approve` (PIN) → single-use `X-Approval-Token`.
- [x] **Build cleanliness:** `next build` (`next build && node scripts/prepare-standalone.mjs`) exits 0 (15/15 routes, exit 0); only benign `location is not defined` warnings (Next.js 16.2.10 framework-internal, not app code). Standalone assets (`.next/standalone/` + static + public) emitted and ready for Tauri sidecar bundling.

## 4. Test Coverage Gate (FastAPI backend)

Quality gate: `backend_fastapi/pyproject.toml` `[tool.coverage.report] fail_under = 90`.

- [x] **Coverage gate:** `python -m pytest -q` exits 0 only when total line coverage ≥ 90%.
- [x] **Async-trace correctness:** async service bodies (pos/auth/inventory/sync) and repository methods are covered via direct `await` in `async def` tests (the ASGI `AsyncClient` path under-coverage bodies are traced there), and route-handler lines via the existing HTTP `client` tests.
- [x] **mypy:** `python -m mypy app --strict` → Success (0 issues), no regressions from added tests.

## 5. Mobile App (React Native / Expo SDK 57)

Quality gates for the mobile pharmacy app at `mobile/`:

- [x] **TypeScript:** `npx tsc --noEmit` from `mobile/` → 0 errors (strict mode).
- [x] **Metro Bundler:** `npx expo start` boots without errors, loads `.env` (`API_BASE_URL=http://localhost:8000`).
- [x] **Typed contracts:** `types/contracts.ts` mirrors backend `schemas.py` (Money = string, uniform error shape).
- [x] **Money safety:** `lib/decimalCurrency.ts` port — bigint-cents, no floating-point in money path.
- [x] **Offline-first POS:** `stores/posStore.ts` — cart persists locally, checkout enqueues on network failure, `flushQueue` replays via `POST /api/v1/sync/push` with `client_txn_id` idempotency + Lamport `local_seq`.
- [x] **Tier-3 sync lock (backend DONE):** `POST /api/v1/pos/lock` — `SyncLockService` in-process `asyncio.Lock`, ACQUIRE/RELEASE/HEARTBEAT with TTL. `SyncLockRequest/Response` schemas in `schemas.py:330-344`. 5 tests in `test_mobile_routes.py` pass (acquire, deny-when-held).
- [x] **Offline-ack (backend DONE):** `POST /api/v1/mobile/offline-ack` — marks `SyncOutbox` rows `acked` for GC (500-ID cap). `MobileOfflineAckRequest/Response` in `schemas.py:347-356`. Test T61 passes.
- [x] **ESC/POS label render (backend DONE):** `POST /api/v1/labels/render-mobile` — `_render_elements_to_escp()` + `_barcode_escp()` render text + Code128/UPC-A/EAN13 to base64 ESC/POS. `MobileLabelRenderRequest/Response` in `schemas.py:359-373`. Tests T62/T62b pass.
- [ ] **Barcode scanning:** `components/BarcodeScanner.tsx` — `expo-camera` CameraView with barcode scanning; manual entry fallback. (Requires physical device for live camera test.)
- [x] **Auth flow:** Login screen → JWT in AsyncStorage → 401 refresh interceptor → session hydrate on app start.
- [x] **Shift management:** Open/close via `lib/api/shift.ts` ↔ `POST /api/v1/pos/shift/*` (ShiftsScreen implemented).
- [x] **Inventory browsing:** `stores/inventoryStore.ts` + `lib/api/inventory.ts` — paginated list, low-stock filter, barcode lookup.
- [x] **License gate:** App-start license check via `/auth/license-status` with 7-day grace period. `LicenseEntryScreen` blocks unlicensed access. Device HWID binding via `expo-device` + `validateLicense`.
- [x] **Settings:** Device info (name + ID), license status, logout.
- [x] **Mobile receiving/PO (backend DONE):** `GET /api/v1/inventory/by-barcode/{barcode}` endpoint (T64 test passes). `lib/api/receiving.ts` (8 typed functions), `lib/api/analytics.ts` (2 functions), `ReceivingScreen.tsx` (PO creation + log), `AnalyticsScreen.tsx` (Top Selling + Demand Velocity).
- [x] **Mobile hooks:** `useSync` (NetInfo auto-flush), `useBarcodeScanner` (camera perms), `useShift` (shift wrapper).
- [x] **Cart recovery:** `lib/cartRegistry.ts` — persists cart + meta on mutations, restores on `hydrate()` with 4h age check.
- [x] **Retry backoff:** `MAX_QUEUE_ATTEMPTS=5`, exponential backoff (1s→60s), `incrementAttempts` + `removeStaleEntries` in `flushQueue`.
- [ ] **Barcode scanning:** `components/BarcodeScanner.tsx` — `expo-camera` CameraView with barcode scanning; manual entry fallback. (Requires physical device for live camera test.)
- [ ] **Thermal printing:** `react-native-thermal-printer` (not yet installed; backend `/labels/render-mobile` ready). Planned for Milestone F.
- [ ] **Push notifications:** `expo-notifications` for low-stock/expiry alerts (not yet installed; planned for Milestone F).
- [ ] **Kiosk PIN mode:** `loginWithPin` API client exists, no PIN kiosk UI screen. Planned for Milestone F.