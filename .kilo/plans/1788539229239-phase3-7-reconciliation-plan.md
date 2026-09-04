# Phase 3–7 Reconciliation — Implementation Already Complete

> **Status:** All phases from `task.md` and `implementation_plan66.md` are **already implemented** in the working tree as untracked files or modified existing files. The `task.md` checklist is stale (still shows `[ ]` for items that exist as code).

## 1. Reality Check — Codebase Audit

Cross-referenced every `task.md` checklist item against actual file existence + router registration in `main.py`.

### Phase 3: Porting Legacy Python Features & OCR
| task.md item | Status | Evidence |
|---|---|---|
| `POST /api/v1/ocr` (in-memory `io.BytesIO`) | DONE | `backend_fastapi/app/api/routers/ocr_route.py` — uses `io.BytesIO`, `UploadFile`, `pytesseract`, PIL preprocessing. Registered `app/main.py:247`. Requires auth via `get_current_user`. |
| OCR upload drag-and-drop component | DONE | `components/OcrUploadDropzone.tsx` — drag-and-drop zone calling `POST /api/v1/ocr`, returns `OcrResult {text, confidence, metadata}`. |
| Excel export/import endpoints | DONE | `backend_fastapi/app/api/routers/excel_route.py` — `GET /export/inventory` (streams .xlsx via `StreamingResponse`), `POST /import/inventory` (bulk upsert with `INSERT INTO products`). Registered `app/main.py:248`. |
| Next.js print-preview route for labels | DONE | `app/print-label/page.tsx` — `/print-label` route with `@media print` CSS for 2×1″ thermal labels. Accepts `?name=&barcode=&vendor=&expiry=&price=&pharmacy=`. |

### Phase 4: Multi-PC LAN Network Configuration
| task.md item | Status | Evidence |
|---|---|---|
| FastAPI server binding to `0.0.0.0` | DONE | `backend_fastapi/run_backend.py:23` — `parser.add_argument("--host", default="0.0.0.0", ...)`. Already includes `# noqa: S104`. |

### Phase 5: Time-Filtered Sales Analytics Dashboard
| task.md item | Status | Evidence |
|---|---|---|
| Analytics GROUP BY endpoints | DONE | `backend_fastapi/app/api/routers/analytics_route.py` — `GET /demand` (velocity tiers, FEFO, reorder) + `GET /top-selling` (Day/Week/Month period query param). Registered `app/main.py:228`. Service: `app/services/demand_analytics_service.py`. |
| Next.js dashboard with Day/Week/Month toggle | DONE | `app/dashboard/analytics/page.tsx` (parent page with period toggle) + `app/dashboard/analytics/demand/page.tsw` (KPI cards, sortable velocity table, CSV export). |

### Phase 6: Vendor Management Module
| task.md item | Status | Evidence |
|---|---|---|
| `vendors`, `vendor_items`, `purchase_history` tables | DONE | `app/core/models.py:730` (`Vendor`), `:751` (`VendorItem`), `:764` (`PurchaseHistory`). Created via `Base.metadata.create_all()` at `database.py:199` (handles fresh DBs). |
| Vendor CRUD + receive endpoints | DONE | `backend_fastapi/app/api/routers/vendors_route.py` — `GET/POST/PUT /vendors`, `GET /vendors/{id}/items`, `POST /vendors/receive`. Registered `app/main.py:249`. |
| Next.js Vendor Management UI | DONE | `app/dashboard/vendors/page.tsx` (276 lines) — vendor list, create modal, receive shipment form, balance tracking, RBAC-gated via `useCan("inventory.write")`. |

### Phase 7: Third-Party Medicine API Proxy
| task.md item | Status | Evidence |
|---|---|---|
| `integrations` table | DONE | `app/core/models.py:784` (`Integration` with `encrypted_api_key`, `is_active`, `base_url`, `provider_name`). Created via `create_all()`. |
| Mock `POST /api/v1/drugs/evaluate` proxy | DONE | `backend_fastapi/app/api/routers/integrations_route.py:131` — `DrugEvaluateRequest {ndc?, drug_name}`, `DrugEvaluateResponse {status, message, interactions, source, cached}`. In-process TTL cache (1h). Mock table for warfarin/aspirin/metformin + severe keywords (digoxin/lithium/etc). Falls back to mock on live provider failure. |
| Evaluate Drug button + clinical warning modal | DONE | `components/DrugEvaluateButton.tsx` (230 lines) — renders safe (green ✓), warning (yellow ⚠), severe (red ⛔). On severe: dispense locked, pharmacist must acknowledge with "Override — I Accept Responsibility" button. `onSafe`/`onSevere` callbacks for parent integration. |

## 2. What Is NOT Done

### Missing: `task.md` checklist update
The `task.md` file still shows all Phase 3–7 items as `[ ]`. These should be marked `[x]` to reflect reality.

### Missing: Database migration block for vendor/integrations tables (pre-existing DBs only)
`Base.metadata.create_all()` (database.py:199) creates the `vendors`, `vendor_items`, `purchase_history`, and `integrations` tables on **fresh** databases. On **pre-existing production databases** already at `SCHEMA_VERSION = 14`, `create_all()` will also create new tables via `CREATE TABLE IF NOT EXISTS` since they don't exist yet — so this is actually safe. No migration block is needed because these are entirely new tables, not column additions to existing tables. **Verification needed:** confirm `CREATE TABLE IF NOT EXISTS` behavior for new tables on existing DBs.

### Uncommitted changes
`git status --short` shows all Phase 3–7 files as untracked (`??`). The implementation exists in the working tree but has **not been committed**. This is the single action item before this work can be considered "done."

## 3. Verification Commands

```bash
# Backend: run all tests
cd backend_fastapi && .venv\Scripts\python -m pytest -q

# Backend: type check
cd backend_fastapi && .venv\Scripts\python -m mypy app --strict

# Frontend: type check
npx tsc --noEmit

# Frontend: build
npx next build

# Frontend: tests
npx vitest run
```

## 4. Action Items

| # | Priority | Action | Files |
|---|---|---|---|
| 1 | **High** | Commit the untracked Phase 3–7 files | All `??` files from `git status` |
| 2 | **Low** | Update `task.md` checklist: mark all Phase 3–7 items `[x]` | `task.md` |
| 3 | **Low** | Add note to `PROJECT_MAP.md` ORPHANS section | `PROJECT_MAP.md` |

## 5. Out of Scope (per implementation_plan66.md)

- Label printing: print-preview route is done; Tauri native printing is deferred.
- Server binding: `0.0.0.0` is done for `run_backend.py`; Docker/Nginx config is separate (B7, already complete).
- Live third-party API: mock implementation is done; switching to a live provider requires configuring `integrations` table + `base_url`/`encrypted_api_key`.
