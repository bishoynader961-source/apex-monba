# SPEC 07 — Multi-Terminal Sync & Offline Queue

**Architecture reference:** `APP_BLUEPRINT.md` Section 2 (Sync / Multi-terminal)
**Files:** `lib/api/sync.ts`, `stores/posStore.ts`, `backend_fastapi/app/api/routers/sync_route.py`, `backend_fastapi/app/services/sync_service.py`

## Part 1 — The Offline Queue (Frontend)
The POS system must remain functional if the backend sidecar momentarily drops or the network connection between a secondary terminal and the main server fails.

1. **Update `posStore.ts`:**
   - Add an `offlineQueue: QueuedTransaction[]` array to the store.
   - When `processCheckout` is called, attempt the API call. If it fails with `Network Error` or `503`, push the transaction to `offlineQueue` and return a local success state with a generated temporary Receipt ID (e.g., `OFF-12345`).
   - The UI must show a small yellow warning icon indicating "Working Offline (X queued)".

2. **Background Sync Worker:**
   - Implement a `setInterval` hook in `components/DashboardLayout.tsx` that polls every 15 seconds.
   - If `offlineQueue.length > 0`, iterate through the queue and POST to `/api/v1/sync/push`. On success, remove from the queue.

## Part 2 — Sync Route & Discrepancy Handling (Backend)
1. **Implement `POST /api/v1/sync/push`:**
   - Receives an array of disconnected transactions (sales, inventory adjustments).
   - Validates stock levels retrospectively. 
   - If a queued sale drops inventory below 0, allow it, but flag the `Product` model with `requires_stock_audit = True`.

2. **Implement `GET /api/v1/sync/discrepancies`:**
   - Returns a list of all products flagged for audit due to offline sync conflicts.
   - Requires `role_id=1` permission to resolve.

## Part 3 — Master/Slave Terminal Lock (Tauri)
If deploying across a local LAN (one main PC hosting the DB, other PCs connecting to it):
- Add a configuration in `app/dashboard/settings/page.tsx` for "Terminal Mode" (Main Server vs. Client Terminal).
- If Client Terminal is selected, disable the local FastAPI sidecar spawn in `src-tauri/src/lib.rs` and route `lib/api.ts` base URLs to the Main Server's LAN IP.