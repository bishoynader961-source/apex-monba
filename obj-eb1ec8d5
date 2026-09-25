# Pharmacy Suite - Master Architecture Blueprint

## 1. System Overview
*   **Frontend:** React 18, Next.js 15 (App Router, Standalone Output), Zustand (state), Tailwind CSS, TypeScript (strict)
*   **Backend:** FastAPI (Python 3.12+), SQLAlchemy 2.0 (async), Pydantic v2, SQLite (aiosqlite), Uvicorn
*   **Database:** SQLite (file-based, `pharmacy.db`) with WAL mode; migrations via SQLAlchemy `create_schema`
*   **Desktop Shell:** Tauri v2 (Windows NSIS installer), sidecar binaries: Node.js (Next.js) + FastAPI backend
*   **Mobile:** React Native / Expo SDK 57 (separate `mobile/` folder)
*   **Build/Deploy:** `npm run tauri build` → `src-tauri/target/release/bundle/nsis/PharmacySuite_1.0.0_x64-setup.exe`

## 2. Feature Map & Code Pointers

### Authentication & Roles
| Layer | File |
|-------|------|
| **React Page** | `app/login/page.tsx` (server action: `app/login/actions.ts`) |
| **Zustand Store** | `stores/authStore.ts` (`useAuthStore`, `useCan`) |
| **API Client** | `lib/api/auth.ts` (`getCurrentUser`, `login`, `logout`, `refresh`) |
| **FastAPI Router** | `backend_fastapi/app/api/routers/auth_route.py` (`/login`, `/me`, `/refresh`, `/register`, `/logout`, `/verify-password`, `/change-password`, `/rotate-pepper`) |
| **Auth Service** | `backend_fastapi/app/services/auth_service.py` (`AuthService.login`, `pin_login`, `refresh`, `register`, `verify_password`, `change_password`) |
| **Pydantic Schemas** | `backend_fastapi/app/shared/schemas.py` (`CurrentUser`, `Token`, `UserPublic`, `LoginRequest`, `PinLoginRequest`, `TokenPayload`) |
| **SQLAlchemy Models** | `backend_fastapi/app/core/models.py` (`User`, `Role`, `Permission`, `RolePermission`) |
| **Dependencies** | `backend_fastapi/app/api/deps.py` (`get_current_user`, `require_permission`, `require_unlocked`) |

### Inventory & POS
| Layer | File |
|-------|------|
| **React Pages** | `app/pos/page.tsx` (main POS), `app/dashboard/inventory/page.tsx` |
| **Zustand Stores** | `stores/posStore.ts` (cart, checkout, payments, offline queue), `stores/inventoryStore.ts` (medicines, batches, filters) |
| **API Client** | `lib/api/pos.ts` (`processCheckout`, `openShift`, `closeShift`, `voidItem`), `lib/api/inventory.ts` (`listMedicines`, `receiveBatch`, `adjustStock`, `getProductByBarcode`) |
| **FastAPI Routers** | `pos_route.py` (`/checkout`, `/shift/*`, `/receipts/*`, `/drawer`), `inventory_route.py` (`/medicines`, `/batches`, `/movements`, `/receive`, `/adjust`) |
| **Services** | `pos_service.py` (`PosService.process_checkout`, `shift`), `inventory_service.py` (`InventoryService`) |
| **Models** | `Product`, `Batch`, `Receipt`, `ReceiptItem`, `Shift`, `DrawerMovement`, `inventory_extended` |

### Prescription / RX Queue
| Layer | File |
|-------|------|
| **React Pages** | `app/rx/page.tsx`, `app/patients/page.tsx` (Rx tab) |
| **Components** | `components/rx/RxQueueDashboard.tsx`, `components/rx/*Modals.tsx` |
| **Zustand Store** | `stores/rxQueueStore.ts` (`useRxQueueStore`) |
| **API Client** | `lib/api/rxQueue.ts` (`fetchTab`, `transitionStatus`, `bulkTransition`) |
| **FastAPI Router** | `rx_queue_route.py` (`/rx-queue/{tab}`, `/rx-queue/{rx_id}/status`, `/rx-queue/bulk`) |
| **Types** | `types/contracts.ts` (`RxQueueItem`, `RxQueueCounts`, `RxBulkStatusRequest`, `RX_STATUSES`, `RX_STATUS_TRANSITIONS`) |

### Label Engine
| Layer | File |
|-------|------|
| **React Pages** | `app/dashboard/label-engine/page.tsx`, `app/dashboard/label-engine-preview/page.tsx` |
| **Components** | `components/LabelCanvas.tsx`, `components/LabelPropertiesPanel.tsx`, `components/InvoiceParsePanel.tsx` |
| **API Client** | `lib/api/labelTemplates.ts`, `lib/api/invoiceParse.ts` |
| **FastAPI Routers** | `label_template_route.py`, `invoice_parse_route.py` |

### Settings & Session
| Layer | File |
|-------|------|
| **React Page** | `app/dashboard/settings/page.tsx` |
| **Zustand Stores** | `stores/sessionStore.ts` (`useSessionStore`, `startSessionTracking`), `stores/authStore.ts` |
| **Components** | `components/SessionTimeoutModal.tsx`, `hooks/useSessionTimer.tsx` |
| **API Client** | `lib/api/settings.ts` (`listSettings`, `updateSetting`) |
| **FastAPI Router** | `settings_route.py` (`GET /settings`, `PUT /settings/{key}`) |
| **Models** | `SystemSetting` (key/value), seeded defaults: `session_idle_minutes=15`, `session_absolute_minutes=480` |

### Clinical / Patient Management
| Layer | File |
|-------|------|
| **React Pages** | `app/patients/page.tsx`, `app/prescribers/page.tsx`, `app/dashboard/wc-claims/page.tsx` |
| **Components** | `components/rx/ClinicalWorkflowPanel.tsx`, `components/rx/DurAlertPanel.tsx` |
| **Zustand Stores** | `stores/patientStore.ts`, `stores/priorAuthStore.ts` |
| **API Client** | `lib/api/patients.ts`, `lib/api/prescribers.ts`, `lib/api/priorAuth.ts` |
| **FastAPI Routers** | `patients_route.py`, `prescriber_route.py`, `prior_auth_route.py` |

### Analytics / Demand
| Layer | File |
|-------|------|
| **React Pages** | `app/dashboard/analytics/page.tsx`, `app/dashboard/analytics/demand/page.tsx` |
| **Zustand Store** | `stores/dashboardAnalyticsStore.ts` |
| **API Client** | `lib/api/analytics.ts`, `lib/api/dashboard.ts` |
| **FastAPI Router** | `analytics_route.py` (`/demand`, `/top-selling`), `dashboard_route.py` |

### Sync / Multi-terminal
| Layer | File |
|-------|------|
| **API Client** | `lib/api/sync.ts` (`push`, `pull`, `ack`), `lib/api/approval.ts` |
| **FastAPI Router** | `sync_route.py` (`/push`, `/pull`, `/discrepancies`, `/lock`), `approval` in `pos_route.py` |
| **Services** | `sync_service.py` (`SyncService`), `sync_lock_service.py` |

## 3. Data Flow & Contracts

### TypeScript ↔ Pydantic Contract Sync
*   **Single Source of Truth:** `types/contracts.ts` mirrors `backend_fastapi/app/shared/schemas.py`
*   **Money Handling:** All monetary fields are `type Money = string` (JSON string from Decimal). NEVER parse them with floating point; use `lib/decimalCurrency` (bigint cents).
*   **Date Format:** ISO 8601 strings (`YYYY-MM-DD` for dates, `YYYY-MM-DDTHH:MM:SSZ` for timestamps).
*   **Error Contract:** Uniform `{ error: { code, message, details } }` from backend; frontend `AxiosError` interceptor extracts `detail` or `error.message`.

### Key Type Mappings
| TS Interface | Pydantic Schema | SQLAlchemy Model |
|--------------|-----------------|------------------|
| `CurrentUser` | `CurrentUser` | `User` (via `UserRepository`) |
| `UserPublic` | `UserPublic` | `User` |
| `Medicine` / `ProductRead` | `MedicineRead` | `Product` |
| `Batch` / `BatchRead` | `BatchRead` | `Batch` (inventory_extended) |
| `ReceiptRead` | `ReceiptRead` | `Receipt` |
| `DispenseRead` | `DispenseRead` | `Dispense` |
| `PatientRead` | `PatientRead` | `Patient` |
| `RxQueueItem` | (derived) | `rx_queue` view |
| `DispenseRead` | `DispenseRead` | `Dispense` |

## 4. Tauri / Desktop Specifics

*   **Sidecar Processes:** Two sidecars managed in `src-tauri/src/lib.rs`:
    1.  Node.js (`server.js` from `.next/standalone`) on port 3000
    2.  FastAPI (`backend` binary) on port 8000
*   **Process Tracking:** `SIDECAR_NODE` and `SIDECAR_BACKEND` `Mutex<Option<CommandChild>>` for clean shutdown.
*   **Window Close:** `WindowEvent::CloseRequested` triggers `kill_sidecars()`.
*   **CSP:** Restrictive CSP in `tauri.conf.json` — only `self`, `127.0.0.1:3000/8000`, `cdn.paddle.com`.
*   **DevTools:** Disabled (`"devtools": false`) in production window config.

## 5. Microsoft Store Readiness Checklist

| Item | Status | Location / Notes |
|------|--------|------------------|
| AppxManifest / Identity | ⚠️ Needs review | `src-tauri/tauri.conf.json` (`identifier: "com.pharmacy.suite"`, `version: "1.0.0"`) |
| Age Rating / Content | ⚠️ Not configured | Need to add to `package.appxmanifest` (if MSIX) or NSIS metadata |
| Privacy Policy URL | ⚠️ Missing | Required for Store submission |
| Accessibility (Screen Reader) | ⚠️ Partial | Semantic HTML, but no ARIA audit |
| High DPI / Scaling | ✅ | Tauri handles via WebView2 |
| Offline Capability | ✅ | `stores/recovery.ts`, `lib/offlineKey.ts`, `posStore.ts` offline queue |
| Telemetry / Crash Reporting | ✅ | `/api/v1/crash-report`, `ErrorBoundary` |
| Auto-updates | ⚠️ Not implemented | Need Tauri updater plugin |
| Code Signing | ⚠️ Not configured | Required for MS Store (EV cert) |
| Windows App SDK / MSIX | ❌ Not configured | Currently NSIS only; MS Store requires MSIX |
| App Icon Assets | ✅ | `src-tauri/icons/` (32, 128, 256, .ico, .icns) |

## 6. Global Refinement Strategy

1.  **Strict Type Safety:** All TypeScript interfaces must match Pydantic schemas exactly. Any schema change requires updating both `types/contracts.ts` and `backend_fastapi/app/shared/schemas.py`.
2.  **Error Boundaries:** All React routes must be wrapped in error boundaries to prevent white screens (`components/ErrorBoundary.tsx` wraps in `app/layout.tsx`).
3.  **API Consistency:** All frontend API calls must handle 401, 403, and 500 status codes gracefully with user-facing toast notifications (`lib/api.ts` interceptor + `stores/uiStore.ts` toast).
4.  **No Dead Code:** Remove unused variables, imports, and console.logs.
5.  **Money Safety:** All monetary calculations use `lib/decimalCurrency` (bigint cents). NEVER use `parseFloat` or `number` for money.
6.  **Permission Checks:** Frontend `useCan` / `hasPermission` AND backend `require_permission` must BOTH handle `"*"` wildcard for admin (role_id=1).
7.  **Session Security:** `devtools: false` in `tauri.conf.json` for production. Sidecar processes killed on main window close.

---

## 7. Top 3 Structural Errors / Inconsistencies

### #1: Inconsistent API Error Handling — 403/500 Not Surfaced to User
**Location:** `lib/api.ts` (interceptor), `stores/uiStore.ts`, `components/AlertProvider.tsx`
**Problem:** The Axios interceptor only handles **401** (auto-refresh). **403 Forbidden** and **500 Server Error** responses are thrown as generic `Error` objects but **never displayed to the user** — no toast, no alert banner. Pages like Users/Roles/Settings silently fail with "Loading..." forever when permission checks fail.
**Evidence:** `lib/api.ts:64-65` only checks `status !== 401`. `DashboardLayout` shows no error UI. `useAuthStore.logout` clears token on 401 but not on 403.
**Fix:** Extend interceptor to catch 403/500, call `useUiStore.getState().showToast(msg, "error")` or `AlertProvider` action.

### #2: Permission Guard Drift — Frontend vs Backend Wildcard Handling
**Location:** `stores/authStore.ts:78-81` (`hasPermission`), `stores/authStore.ts:98-102` (`useCan`), `backend_fastapi/app/api/deps.py:107-110` (`require_permission`)
**Problem:** 
- **Frontend:** `perms.includes("*") || perms.includes(permission)` ✅ Correct
- **Backend (deps.py):** `if "*" not in user.permissions and permission not in user.permissions and not user.role.lower().startswith("admin")` ⚠️ **Relies on `role` string** ("admin") instead of `role_id === 1` or `"*"` in permissions. JWT `role` claim is `"Administrator"` but check is `startswith("admin")` — works but fragile.
- **Backend (roles_route.py:122-127):** `create_permission` endpoint checks `_user.role_id != 1` (correct) but other endpoints use `require_permission` which uses role string.
**Fix:** Unify on `role_id === 1` OR `"*"` in permissions. Update `require_permission` to check `user.role_id == 1` first, then `"*"` in permissions, then explicit permission.

### #3: SessionStore `tick()` Type Unsoundness — "never" String vs Number Arithmetic
**Location:** `stores/sessionStore.ts:84-145` (`tick` function)
**Problem:** `idleMinutes` and `absoluteMinutes` are typed as `TimeoutValue = number | "never"`. The `tick()` function uses `isNever()` type guard but **still performs arithmetic on the union type** without narrowing in all branches. TypeScript errors suppressed by extracting to local `const` (lines 109, 119), but the logic is brittle — if `isNever` returns false, TypeScript still sees `TimeoutValue` and the multiplication `idleMinutes * 60_000` is technically on `number | "never"`.
**Evidence:** Previous build failures (`TS2362`) required manual local `const` extraction. The type guard `isNever(value): value is "never"` helps but the pattern is error-prone.
**Fix:** Refactor `tick()` to early-return when `"never"` — split into `checkIdleTimeout()` and `checkAbsoluteTimeout()` that only accept `number`. Store `"never"` as `null` or `Infinity` internally to avoid union arithmetic entirely.

---

**Awaiting your permission to fix these three issues.** Once approved, I will:
1. Update `lib/api.ts` interceptor + add toast integration for 403/500
2. Unify permission check logic in `deps.py` and `authStore.ts`  
3. Refactor `sessionStore.ts` to use `null`/`Infinity` for "never" and remove union arithmetic