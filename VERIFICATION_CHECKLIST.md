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
- [ ] **Build cleanliness:** `next build` exits 0 (12/12 pages); two benign    `location is not defined` warnings are a Next.js 16.2.10 framework-internal artifact, not app code.

## 4. Test Coverage Gate (FastAPI backend)

Quality gate: `backend_fastapi/pyproject.toml` `[tool.coverage.report] fail_under = 90`.

- [x] **Coverage gate:** `python -m pytest -q` exits 0 only when total line coverage ≥ 90%.
- [x] **Async-trace correctness:** async service bodies (pos/auth/inventory/sync) and repository methods are covered via direct `await` in `async def` tests (the ASGI `AsyncClient` path under-coverage bodies are traced there), and route-handler lines via the existing HTTP `client` tests.
- [x] **mypy:** `python -m mypy app --strict` → Success (0 issues), no regressions from added tests.