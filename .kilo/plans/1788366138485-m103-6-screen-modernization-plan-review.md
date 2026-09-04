# Review: 6-Screen Modernization Plan (M103)

## Executive Summary

**The plan describes M103 (6-Screen Modernization), which has already been implemented and verified** per `PROJECT_MAP.md` line 458 ("Verified 2026-09-02"). A thorough audit of the codebase confirms virtually every proposed change is already in the working tree. However, several **remaining gaps and issues** prevent the milestone from being fully production-ready.

---

## 1. Implementation Status: All Proposed Changes Are Present

### Backend — ORM Models (`models.py`)
| Proposed Change | Status | Location |
|---|---|---|
| SigCode: `language`, `days_accumulated`, `offset` | DONE | `models.py:548-550` |
| WorkersCompClaim: 15 employer/pay-to columns | DONE | `models.py:645-660` |
| InsurancePlan: 12 master-file columns (plan_code, fax, alt_phone, contact, address, copay, co-insurance, notes, processor_verified) | DONE | `models.py:473-486` |

### Backend — Schemas (`schemas.py`)
| Proposed Change | Status | Location |
|---|---|---|
| SigCodeBase/Read/Create with language/DA/offset | DONE | `schemas.py:901-928` |
| SigCodeUpdate (all-optional) | DONE | `schemas.py:923-928` |
| InsurancePlanRead unified with enrichment fields | DONE | `schemas.py:785-816` |
| WCClaimBase/Read/Update with 15 extended fields | DONE | `schemas.py:1189-1294` |
| PriceCalculationResult | DONE | `schemas.py:976-978` |

### Backend — Repositories (`repositories.py`)
| Proposed Change | Status | Location |
|---|---|---|
| SigCodeRepository.update (partial) | DONE | `repositories.py:891-900` |
| SigCodeRepository.delete (hard) | DONE | `repositories.py:902-909` |
| PriceCodeRepository.calculate_price (clamping formula) | DONE | `repositories.py:965-995` |
| PriceCodeRepository.update | DONE | `repositories.py:947-955` |
| PriceCodeRepository.delete | DONE | `repositories.py:957-963` |
| InsuranceRepository.update | DONE | `repositories.py:800-806` |
| WCClaimRepository.update (with extended fields) | DONE | `repositories.py:1402-1413` |

### Backend — API Routes
| Proposed Change | Status | Location |
|---|---|---|
| PUT `/sig-codes/{id}` | DONE | `dictionaries_route.py:45-55` |
| DELETE `/sig-codes/{id}` | DONE | `dictionaries_route.py:58-66` |
| GET `/price-codes/{id}/calculate` | DONE | `dictionaries_route.py:119-139` |
| PUT `/price-codes/{id}` | DONE | `dictionaries_route.py:95-105` |
| DELETE `/price-codes/{id}` | DONE | `dictionaries_route.py:108-116` |
| Insurance route returns enriched InsurancePlanRead | DONE | `insurance_route.py:60-68` |
| PUT `/insurance/plans/{plan_id}` | DONE | `insurance_route.py:60-68` |
| Routes registered in `main.py` | DONE | `main.py:224-225, 217` |

### Frontend — Contracts (`contracts.ts`)
| Proposed Change | Status |
|---|---|
| SigCodeBase/Read/Create/Update with language/days_accumulated/offset | DONE (lines 741-766) |
| InsurancePlanRead with all enrichment + master-file fields | DONE (lines 684-715) |
| InsurancePlanReadExtended merged as alias | DONE (line 1048: `type InsurancePlanReadExtended = InsurancePlanRead`) |
| WCClaimBase/Read/Update with 15 extended fields | DONE (lines 1051-1120) |
| PriceCalculationResult | DONE (lines 822-825) |
| SigCodeUpdate | DONE (lines 760-766) |

### Frontend — API Service Layer
| Proposed Change | Status | Location |
|---|---|---|
| `lib/api/dictionaries.ts` with 10 functions | DONE | `lib/api/dictionaries.ts:1-80` |
| WC frontend service with PUT | DONE | `lib/api/wc.ts:35-37` |

### Frontend — Global Hotkeys
| Proposed Change | Status | Location |
|---|---|---|
| `hooks/useGlobalHotkeys.ts` (F1-F6) | DONE | `hooks/useGlobalHotkeys.ts:1-51` |
| `components/GlobalHotkeys.tsx` wrapper | DONE | `components/GlobalHotkeys.tsx:1-7` |

### Frontend — New Pages
| Page | Status | Location |
|---|---|---|
| Insurance Plan Master File (`app/dashboard/insurance/page.tsx`) | DONE — 6 tabs, General + 5 placeholder tabs, action bar | `app/dashboard/insurance/page.tsx:1-259` |
| Sig Code Engine (`app/dashboard/sig-codes/page.tsx`) | DONE — LIST + ADD modes, search, D.A./Offset fields | `app/dashboard/sig-codes/page.tsx:1-195` |
| Rx Processing Toolbar (`app/rx/page.tsx`) | DONE — 14 system menus, metadata bar, 15 ribbon buttons, quick-launch | `app/rx/page.tsx:1-148` |
| Price Code Engine (`app/dashboard/price-codes/page.tsx`) | DONE — editable grid, live computed preview, clamping display | `app/dashboard/price-codes/page.tsx:1-274` |
| Master Drug File (`app/dashboard/drugs/page.tsx`) | DONE — NDC 11-digit validation, strength/form/DEA/class fields | `app/dashboard/drugs/page.tsx:1-282` |

### Frontend — Workers' Comp Tab
| Proposed Change | Status | Location |
|---|---|---|
| 15 extended employer/pay-to fields | DONE | `app/patients/page.tsx:397-513` |
| Employer Address: contact, ext, line1/2, city, state, zip | DONE | `patients/page.tsx:460-475` |
| Pay To section: dropdown, contact, phone, address | DONE | `patients/page.tsx:479-494` |
| `Save & Close` → `updateWCClaim` | DONE | `patients/page.tsx:440-447` (PUT via `wcApi.updateWCClaim`) |

### Verified in PROJECT_MAP.md
Line 458 confirms: "TypeScript 0 errors. Next.js build 30 routes. NSIS installer rebuilt."

---

## 2. Remaining Gaps & Issues

### Issue 1 — CRITICAL: Missing Database Migration (v12)
**File:** `backend_fastapi/app/core/database.py`
**Problem:** `SCHEMA_VERSION = 11` (line 707). The `migrate_schema()` function has versioned blocks v1–v11 but **no v12 block** for the M103 columns. `Base.metadata.create_all()` only creates tables/columns for *fresh* databases. For **existing production databases**, the 30 new columns across `sig_codes`, `workers_comp_claims`, and `insurance_plans` will NOT be added by migration. The ORM models reference these columns, but queries will fail with `no such column` on existing DBs.
**Impact:** Data integrity / production deployment failure on existing databases.
**Fix:** Add a `v12` migration block in `migrate_schema()` with idempotent `ALTER TABLE ... ADD COLUMN` for all 30 columns, then bump `SCHEMA_VERSION = 12`.

### Issue 2 — Debug Code in `calculate_price` Endpoint
**File:** `backend_fastapi/app/api/routers/dictionaries_route.py:127-135`
**Problem:** The endpoint contains developer thinking-out-loud comments and a dead `get_by_code` call that is immediately overwritten:
```python
    pc = await PriceCodeRepository(session).get_by_code(str(price_code_id))
    # wait, get_by_code expects the string code. If price_code_id is the primary key id, we need get(id).
    # Oh, PriceCodeRepository doesn't have get(id). But in the frontend we have the id.
    # Let's add get(id) to PriceCodeRepository, or just use code.
    # The requirement says GET /api/v1/dictionaries/price-codes/{id}/calculate
    # Actually wait. Let's just resolve it directly via session.
    from app.core.models import PriceCode
    pc = await session.get(PriceCode, price_code_id)
```
**Impact:** Sloppy production code; violates clean-code discipline; the `get_by_code` call at line 127 is a wasted DB query.
**Fix:** Remove debug comments and dead `get_by_code` call; add a `get(id)` method to `PriceCodeRepository` and call it instead of `session.get` directly.

### Issue 3 — No Test Coverage for New M103 Endpoints
**File:** `backend_fastapi/tests/`
**Problem:** `test_dictionaries.py` (10 tests) covers create/list/parse for sig codes and create/list for price codes, but does NOT test:
- PUT `/sig-codes/{id}` (update with language/days_accumulated/offset)
- DELETE `/sig-codes/{id}`
- GET `/price-codes/{id}/calculate` (clamping, clamped flag)
- PriceCodeRepository.calculate_price unit test
- `test_insurance.py` does not test extended fields (plan_code, fax_number, etc.) persistence
- No test for WC extended fields (employer_addr_line1, pay_to, etc.) persistence

**Impact:** 90% coverage gate may hold, but the new functionality has zero automated verification. Future regressions on these endpoints would go undetected.
**Fix:** Add tests for all new endpoints and repository methods.

### Issue 4 — Missing `PriceCodeRepository.get(id)` Method
**File:** `backend_fastapi/app/core/repositories.py:928-995`
**Problem:** Unlike every other repository (Product, Supplier, User, Patient, InsurancePlan, MembersGroup, Prescriber, WCClaim all have `get(id)`), `PriceCodeRepository` has no `get(id)` method. The calculate endpoint works around this by calling `session.get(PriceCode, ...)` directly, breaking the repository pattern.
**Fix:** Add `async def get(self, code_id: int) -> Optional[PriceCode]` to `PriceCodeRepository`.

### Issue 5 — New Pages Not in Sidebar Navigation
**File:** `components/DashboardLayout.tsx`
**Problem:** The sidebar navigation (`NAV_SECTIONS`) lists only: `/pos`, `/dashboard/inventory`, `/patients`, `/prescribers`, `/dashboard/wc-claims`, `/dashboard/analytics/demand`, `/dashboard/audit`, `/dashboard/email`, `/dashboard/users`, `/dashboard/roles`, `/dashboard/backup`, `/dashboard/settings`. It does **not** include the 4 new M103 pages:
- `/dashboard/insurance` (Insurance Plan Master)
- `/dashboard/sig-codes` (Sig Code Engine)
- `/dashboard/price-codes` (Price Code Engine)
- `/dashboard/drugs` (Master Drug File)

Users can reach these only via F1-F6 hotkeys or by typing the URL. The plan's verification scenario #6 ("Drug File: `/dashboard/drugs` → verify NDC validation passes") implies direct URL access works, but discoverability is poor.
**Fix:** Add the 4 new pages to the DashboardLayout sidebar under an appropriate section (e.g., "Operations" or a new "Clinical" section).

### Issue 6 — Frontend Preview Formula Diverges from Documented Spec
**File:** `app/dashboard/price-codes/page.tsx:11-32`
**Problem:** The plan documents: `clamp((cost * (1 + cost_factor)) * (1 + markup) + fee, min_price, max_price)`. The actual frontend `computePreview` and backend `PriceCodeRepository.calculate_price` use an **either/or** approach (if `markup_pct` is non-zero → use markup formula; elif `cost_factor_pct` is non-zero → use cost_factor formula; else → cost + fee). This is consistent between frontend and backend, and matches `dispense_service.py:153-167`, but **contradicts the plan's documented formula**. The spec formula multiplies by both `(1+cost_factor)` AND `(1+markup)`, while the implementation uses only one.
**Impact:** Not a code inconsistency (FE/BE agree), but the plan spec is wrong. Should be corrected for documentation accuracy.

### Issue 7 — WC Route URL Discrepancy
**Problem:** The plan states `PATCH /api/v1/wc/claims/{id}`. The actual route is `PUT /api/v1/wc-claims/{claim_id}` (`wc_route.py:74-86`), and the frontend calls it via `PUT` (`lib/api/wc.ts:35-37`).
**Impact:** Not a functional bug — PUT works correctly. But the plan's documented URL and HTTP method are inaccurate.
**Fix:** Update plan spec: `PUT /api/v1/wc-claims/{id}` (not PATCH).

### Issue 8 — `useGlobalHotkeys` Mounting Location
**Problem:** The plan says "Mounted once in `DashboardLayout`" but the hook is actually mounted via `<GlobalHotkeys />` in `app/layout.tsx:23` (the **root** layout). This is arguably better (hotkeys work on all pages including login/license), but the plan documentation is inaccurate.
**Fix:** Update plan to reflect root-layout mounting.

### Issue 9 — `InsurancePlanRead.active` Type Mismatch (Already Fixed)
**Note:** The plan mentions a fix (`active: boolean → number`). This fix is **already applied** — `schemas.py:795` has `active: bool` in `InsurancePlanRead`, but `contracts.ts:693` has `active: number`. The backend serializes `active` as a Python `int` (from `Integer` column), Pydantic coerces to `bool`, and the frontend treats it as `number`. The `InsurancePlanBase` in schemas uses `active: int = 1` (line 758). This works because Pydantic v2 coerces int→bool on the read model, but the type annotation discrepancy in `contracts.ts` (number vs bool) is a latent type-safety issue. Not critical.

---

## 3. Remaining Steps (Action Items)

| # | Priority | Description | Files |
|---|---|---|---|
| 1 | **Critical** | Add v12 migration block for 30 M103 columns in `database.py`; bump `SCHEMA_VERSION` to 12 | `backend_fastapi/app/core/database.py` |
| 2 | **High** | Clean up debug comments + dead `get_by_code` call in `calculate_price` endpoint; add `PriceCodeRepository.get(id)` | `dictionaries_route.py:127-135`, `repositories.py:928` |
| 3 | **High** | Add test coverage: PUT/DELETE sig-codes, calculate endpoint, price calc clamping, insurance extended field persistence, WC extended field persistence | `tests/test_dictionaries.py`, `tests/test_insurance.py`, new `tests/test_wc.py` (or extend existing) |
| 4 | **Medium** | Add the 4 new M103 pages to DashboardLayout sidebar navigation | `components/DashboardLayout.tsx` |
| 5 | **Low** | Update plan spec: correct WC route URL (`PUT /api/v1/wc-claims/{id}` not `PATCH /api/v1/wc/claims/{id}`); correct hotkey mount location (root layout, not DashboardLayout); correct price formula to either/or logic | This plan file |

### Out of Scope / Already Done
- All ORM model columns: DONE
- All schema fields: DONE
- All repository methods: DONE (except `PriceCodeRepository.get(id)`)
- All API route handlers: DONE
- All frontend pages: DONE
- `Contracts.ts` synchronization: DONE
- `lib/api/dictionaries.ts`: DONE
- `hooks/useGlobalHotkeys.ts`: DONE
- WorkersCompTab extended fields: DONE
- `active` type fix: Already applied
- `lucide-react` dependency: Already installed
