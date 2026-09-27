# Pharmacy Suite Readiness Audit Report
**Date:** 2026-09-27
**Agent:** Buffy (Codebuff) — Phase 5, Task 4 Steps 4.2–4.5
**Scope:** Post-implementation re-audit across all 9 blueprint domains (§4.2), compared to the Phase 0 baseline recorded in `PROJECT_MAP.md`.
**Files reviewed:** ~60 key files — backend routers/services/core (14), frontend pages/stores/lib/components (25+), mobile app/stores/lib (8), src-tauri (4), config/manifests (6).

---

## Executive Summary

Pharmacy Suite has moved from a Phase 0 baseline of 3 blueprint errors and 4 critical findings to a state where all 3 blueprint errors are verified FIXED and the original critical findings (gift-card floats, mobile token storage, missing privacy policy) are closed. Two new critical gaps were surfaced by this deeper audit: **expired medicine can still be sold at checkout** (expiry is stamped onto receipts but never rejected) and the **patient custom-fields router is mounted with no authentication at all**. Security posture is otherwise strong (RBAC, rate limiting, pepper rotation, hardened mDNS/QR), but token lifetime (480 min), unencrypted backups, and unlogged auth events remain high-priority gaps. Demo readiness was closed today (Step 4.7: demo mode, seeder, onboarding) and UX fixes landed in Step 4.6; with the two criticals and the WC server-side validation fixed, the product is release-ready.

---

## Step 4.3 — Blueprint Error Verification

| Error | Location | Verdict at HEAD |
|---|---|---|
| #1 API error handling (403/500 surface) | `lib/api.ts:108-114` | **FIXED** — status 403/500 → dynamic-import uiStore toast, message surfaced, promise rejected with typed Error |
| #2 Permission guard drift | `backend_fastapi/app/api/deps.py:150-160` | **FIXED** — `role_id == 1` → `"*" in permissions` → explicit permission check, in that order |
| #3 sessionStore union arithmetic | `stores/sessionStore.ts:33` (`toInternal`) | **FIXED** — `string \| undefined → number \| null` conversion in one place; `tick()` consumes `TimeoutValue` with no string/number arithmetic |

No action required.

---

## Phase 0 → Phase 5 Comparison

| Phase 0 finding | Status today |
|---|---|
| 3 blueprint errors (C-tier) | **All FIXED** (verified above) |
| C: gift-card money floats | **Closed** — no `parseFloat` remains in gift-cards page; Numeric columns |
| C: mobile tokens in AsyncStorage | **Closed** — SecureStore (Phase 1) |
| C: CSP unsafe-inline scripts | **Partially closed** — `script-src` clean; `style-src 'unsafe-inline'` remains (documented Phase-1 decision) |
| C: missing privacy policy | **Closed** — `app/privacy/page.tsx` + Support page link |
| H4: sidecar port conflicts | **Closed** — port-conflict pre-check (Phase 2) |
| H6: WC money validation | **Closed for typing** (server-enforced Numeric + 8 tests); **equality check still client-only** → new H-1 |
| M1–M6 | Tracked below in domain findings |

---

## Critical Issues (Block Release)

| # | Domain | File | Issue | Fix Effort |
|---|--------|------|-------|-----------|
| 1 | D8 Data Integrity | `backend_fastapi/app/services/pos_service.py:209,621,657` | **Expired medicine can be sold.** `expiry_date` is copied onto receipt items but no checkout path rejects an expired product. Patient-safety + regulatory exposure. | M (guard is small; validating all checkout paths + regression tests is the bulk) |
| 2 | D1 Backend Security | `backend_fastapi/app/api/routers/patient_fields_route.py:36-67` | **Unauthenticated patient-data endpoints.** Router has zero auth dependencies (`Depends(get_session)` only) and `main.py` mounts it with no auth middleware (`main.py:245` middleware is CORS + security headers only). GET/POST/DELETE on patient EAV fields readable/writable by any LAN peer in shared mode. | S |

## High Priority (Fix Before Customer Demo)

| # | Domain | File | Issue | Fix Effort |
|---|--------|------|-------|-----------|
| 1 | D8 | `app/dashboard/wc-claims/page.tsx` + WC routes | WC `total_charges = insurance_paid + patient_responsibility` is not validated server-side (types are Numeric, equality is not enforced anywhere — the page has no real-time check either; Step 4.6 adds the client-side check only) | S |
| 2 | D5 Security | `backend_fastapi/app/core/backup.py` | Backups are gzip-compressed VACUUM snapshots with **no encryption** — a stolen `pharmacy.db.gz` is the entire patient database. Criterion: encrypted before download, key shown to admin once | M (Fernet + key-once flow in Backup UI) |
| 3 | D1 | `backend_fastapi/app/services/*.py` | **Zero eager loading** — 0 hits for `selectinload`/`joinedload`/`.options`/`lazy="selectin"` across all services; patient/WC/analytics list endpoints risk N+1 as data grows | M |
| 4 | D5 | `backend_fastapi/app/services/auth_service.py` | **No audit log entries for auth events** (0 hits for audit/AuditLog in auth_service or auth_route) — criterion requires login/logout/failed-login/PIN-change all logged | S |
| 5 | D2 | `app/pos/page.tsx:45,54,336` + money-form pages | **15 `parseFloat`/`Number` hits on money-typed values** (price cents, changeDue, form inputs on price-codes/purchase-orders/templates). Contracts use string money; parsing to float violates the ZERO-parseFloat criterion | M (introduce cents helpers) |
| 6 | D5 | `backend_fastapi/app/shared/config.py:143-144` | Access token TTL **480 min** vs criterion ≤ 15 min (refresh is 30d and the client `lib/api.ts` already has a 401→refresh interceptor, so lowering is low-risk) | S |
| 7 | D6 Mobile | `mobile/app/**` | No `KeyboardAvoidingView` anywhere — inputs occluded by keyboard on small screens | M |

## Medium Priority (Fix in Next Sprint)

| # | Domain | File | Issue | Fix Effort |
|---|--------|------|-------|-----------|
| 1 | D2/D4 | `app/dashboard/inventory`, `receipt-history` | No list virtualization (`react-window` absent) for 500+ row tables | M |
| 2 | D7 | `src-tauri/` | No window-state save/restore (position/size lost between sessions; multi-monitor criterion unmet) | S |
| 3 | D4 | `backend_fastapi/app/main.py` | No GZip middleware on API responses | S |
| 4 | D2 | `app/layout.tsx` | `ErrorBoundary` wraps only the root layout, not per-route | S |
| 5 | D3 | `components/Toaster.tsx:20` | Auto-dismiss 5000 ms vs 4s criterion | S |
| 6 | D5 | `lib/api.ts`, 66 localStorage usages | `access_token` persisted in `localStorage` — XSS-readable (sensitivity of remaining keys unverified) | L |
| 7 | D6 | `mobile/app.json` | Branding `name: "mobile"`, no deep-link `scheme`, no `expo-updates` | S |
| 8 | D9 | — | No Terms of Use first-run acceptance | M |
| 9 | D1 | `backend_fastapi/app/api/routers/setup_route.py` | Pre-auth setup surface is intentional bootstrap but unbounded — should refuse when users already exist (verify + gate) | S |
| 10 | D8 | — | Concurrent-checkout criterion ("2 mobile + 1 desktop") never exercised by an actual multi-client test session | S |

## Low Priority

- **Branding drift:** Tauri productName "Pharmacy Suite" vs root package "my-progam-pharmacy" vs mobile "mobile" — unify before Store submission (S; rename risk noted).
- **CSP:** `style-src 'unsafe-inline'` remains (documented decision; Tailwind-injected styles) (S).
- **A11y:** 29 `aria-label` usages — coverage partial across dense POS controls (S, ongoing).
- **D7:** `kill_sidecars` uses `kill()` only — Windows Job Objects already guarantee child reaping, so SIGTERM→SIGKILL escalation is belt-and-braces (S).
- **D1:** CORS includes LAN subnets + `exp://` in addition to 127.0.0.1 — justified by the mobile companion; documented deviation from the "127.0.0.1 only" criterion (N/A-by-design).
- **D9:** Expiry badge count on nav item (page + ⏰ nav exist, badge count does not) (S).
- **D3:** Fix-code textarea has no character counter (blueprint nice-to-have) (S).
- **D6:** No RTL/I18nManager support — relevant only if Arabic-market distribution is pursued (M, defer).

**Closed during Phase 5 (Step 4.6/4.7):** WC Claims modal patient autocomplete, real-time totals validation, submit spinner, cancel-confirm; Support page Copy-Email + diagnostics checkmark (pre-existing) + stray-text-node render bug; demo mode + seeder + DEMO banner + demo reset + first-run onboarding.

---

## Domain Scores

| Domain | Score | Justification |
|---|---|---|
| **1. Backend API Quality & Security** | **7/10** | RBAC via `require_permission` everywhere except one unauthenticated router; slowapi on auth/POS; WAL on; pagination with caps; crash-report authenticated + sanitized + truncated. Loses points for patient_fields auth hole, no eager loading (N+1), and setup-route gating to verify. |
| **2. Frontend Type Safety & React Quality** | **6.5/10** | Zero `@ts-ignore`, zero `console.log`, stable keys, 403/500 handled, loading states present. Loses points for 15 parseFloat-on-money hits, single root ErrorBoundary, no virtualization. |
| **3. UI/UX & Customer Appeal** | **7/10** | Dark theme consistent, toasts on all pages (5s vs 4s), destructive-action confirms, WC modal now has autocomplete/validation/spinner/cancel-confirm (4.6), onboarding + demo banner (4.7). Missing: focus trap/ESC handling in custom modals, expiry badge. |
| **4. Performance & Scalability** | **6/10** | WAL + read-through TTL settings cache + idempotent checkout (client_tx_id) are solid; no gzip, no virtualization, N+1 risk, bundle analyzer never run. |
| **5. Security Audit** | **6.5/10** | Pepper rotation logged, devtools off, CSP script-src clean, fix-key HMAC in-binary (owner invariant), mDNS TXT minimal, QR server-side expiry, users/roles gated. Loses points for 480-min tokens, unencrypted backups, unlogged auth events, token in localStorage. |
| **6. Mobile App Quality** | **7/10** | SecureStore, persisted offline queue with dead-letter safety, biometrics, diagnostics, QR pairing + mode gating. Missing: KAV, RTL, deep links, expo-updates, real branding. |
| **7. Tauri Desktop Shell** | **7.5/10** | Recovery app, crash handler before init, port-conflict pre-check, deep-sleep health polling, mDNS advisor with kill_sidecars integration, NSIS hooks, updater present. Missing: window-state persistence; kill() without escalation (Job Objects mitigate). |
| **8. Data Integrity & Business Logic** | **7.5/10** | 60 Numeric money columns (float only on non-money skew confidence), atomic flush-based checkout, void audit trail, FEFO refunds, negative-stock guards, hash-chained audit log, timezone-aware datetimes (60 tz-aware vs 0 naive). Two gaps: expired-sale rejection absent, WC equality client-only. |
| **9. Sales Readiness** | **6.5/10** | Privacy page, version in Support, 6-locale i18n desktop, demo mode + seeder + onboarding (4.7). Missing: terms acceptance, Arabic/RTL, backup reminder, branding unification, expiry badge. |

**Overall: 6.8/10** — structurally sound and demo-ready today; release-ready once the two criticals and WC server-side validation land.

---

## Top 10 Quick Wins (effort S, severity-sorted, copy-pasteable)

### 1. (Critical) Authenticate the patient-fields router
`backend_fastapi/app/api/routers/patient_fields_route.py` — add RBAC deps to all three handlers:
```python
from app.api.deps import require_permission
from app.shared.schemas import CurrentUser

@router.get("/{patient_id}/fields")
async def list_patient_fields(
    patient_id: int,
    _user: CurrentUser = Depends(require_permission("patients.read")),
    db: AsyncSession = Depends(get_session),
):
    ...
# POST → require_permission("patients.write"); DELETE → require_permission("patients.write")
```
Then extend `backend_fastapi/tests/test_security_hardening.py` with a 401-without-token assertion per endpoint.

### 2. (High) Reject expired stock at checkout
`backend_fastapi/app/services/pos_service.py` — inside the per-item validation loop (before quantity decrement):
```python
from datetime import date

def _parse_expiry(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        return None

exp = _parse_expiry(product.expiry_date)
if exp is not None and exp < date.today():
    raise ValueError(f"EXPIRED: {product.name} expired {exp.isoformat()}")
```
Map the `EXPIRED:` prefix to a 409 response in the router and surface a toast in `app/pos/page.tsx`.

### 3. (High) Enforce WC totals server-side
In the WC create/update route (workers-comp service), after schema validation:
```python
from decimal import Decimal

total = Decimal(str(claim.total_charges))
parts = Decimal(str(claim.insurance_paid)) + Decimal(str(claim.patient_responsibility))
if total != parts:
    raise HTTPException(
        status_code=422,
        detail=f"total_charges ({total}) must equal insurance_paid + patient_responsibility ({parts})",
    )
```
(Clients get the same rule inline from Step 4.6.)

### 4. (High) Shorten access-token TTL
`backend_fastapi/app/shared/config.py:143-144`:
```python
access_token_expire_minutes: int = 15   # was 480 — refresh flow in lib/api.ts covers renewal
refresh_token_expire_days: int = 30
```
Verify the 401→refresh interceptor path in `lib/api.ts` then run the auth test suite.

### 5. (High) Log auth events to the audit trail
`backend_fastapi/app/api/routers/auth_route.py` — on login success/failure and PIN change:
```python
from app.core.models import AuditLog
from datetime import datetime, timezone

async def _auth_audit(session, action: str, username: str, ok: bool) -> None:
    session.add(AuditLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        action=action,
        details=f"user={username} ok={ok}",
        category="auth",
    ))
    await session.commit()

# call after verify: _auth_audit(session, "auth.login.success" | "auth.login.failed", username, ok)
```

### 6. (Medium) Enable gzip on the API
`backend_fastapi/app/main.py` — with the other middleware:
```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)
```

### 7. (Medium) Per-route error boundaries
`components/DashboardLayout.tsx` — wrap the content slot:
```tsx
import { ErrorBoundary } from "@/components/ErrorBoundary";
// ...
<div className="flex-1 p-6">
  <RegionBanner />
  <ErrorBoundary>{children}</ErrorBoundary>
</div>
```

### 8. (Medium) Toaster 4s auto-dismiss
`components/Toaster.tsx:20`:
```tsx
const timer = setTimeout(() => onDismiss(toast.id), 4000); // was 5000 (criterion: 4s)
```

### 9. (Medium) Mobile branding + deep-link scheme
`mobile/app.json`:
```json
{
  "name": "Pharmacy Suite",
  "slug": "pharmacy-suite",
  "scheme": "pharmacysuite"
}
```

### 10. (Medium) Window-state persistence
```bash
cargo add tauri-plugin-window-state --manifest-path src-tauri/Cargo.toml
```
`src-tauri/src/lib.rs`:
```rust
.plugin(tauri_plugin_window_state::Builder::default().build())
```
Add `"window-state:default"` to the permissions allowlist if the capability file gates plugins.

---

## Recommended Sprint Plan (4 sprints × 2 weeks)

**Sprint 1 — Safety & Auth Hardening (release-blocking)**
Quick wins 1–5: patient_fields auth (+tests), expired-sale rejection end-to-end (service guard → 409 → POS toast → regression suite), WC server-side totals validation, JWT 15-min rollout with session-UX verification, auth-event audit logging. Exit criteria: both criticals closed, `pytest` green, POS checkout tests cover the expired path.

**Sprint 2 — Data Protection & Backend Performance**
Backup encryption (Fernet, key shown once in Backup page), eager-loading pass on patients/WC/analytics list endpoints (N+1 audit with SQL echo), GZip middleware, setup-route "no users exist" gate, multi-client concurrent-checkout test session (2 mobile + 1 desktop). Exit criteria: `pharmacy.db.gz` no longer opens without the key; list endpoints show flat query counts.

**Sprint 3 — Frontend Quality & UX Polish**
Cents helpers replacing the 15 parseFloat money sites, virtualization for inventory/receipt-history, per-route ErrorBoundary, toaster 4s, focus-trap + ESC + backdrop-click on all custom modals, mobile KeyboardAvoidingView pass, expiry badge on nav. Exit criteria: zero parseFloat-on-money greps; keyboard never occludes a mobile input.

**Sprint 4 — Release Ops & Store Submission**
Window-state plugin, mobile branding/scheme/expo-updates/deep-links, Terms-of-Use first-run acceptance, RTL/Arabic feasibility spike, branding unification (productName/package/app.json), backup weekly-reminder, final full re-audit against this report. Exit criteria: store checklist green; this report's FAIL list empty or explicitly accepted.

---

*Report generated as part of Phase 5 (Task 4, Steps 4.2–4.5). Steps 4.6 (WC/Support UX) and 4.7 (demo mode + onboarding) were implemented after evidence gathering per the approved execution order; their changes are reflected in the domain scores above.*
