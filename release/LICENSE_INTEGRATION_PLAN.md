# LICENSE_INTEGRATION_PLAN.md — Freemius × Tauri stack (Phase 3.4 — PLAN ONLY)

Status: planning document. **No code changed in this phase.** Implementation = Phase 4 (requires P1 done: product ID + keys).

Sources (official, fetched 2026-10-03):
- App/license activation flow: https://freemius.com/help/documentation/saas/app-integration.md and https://freemius.com/help/documentation/saas/integrating-license-key-activation.md
- Checkout options: https://freemius.com/help/documentation/checkout/integration/hosted-checkout.md
- Webhooks/events: https://freemius.com/help/documentation/saas/events-webhooks.md
- Fees: https://freemius.com/help/documentation/getting-started/our-pricing.md (4.7% rev-share + ~3.5% avg gateway; on a $149 sale ≈ $12.22 total ≈ 8.2%, excl. VAT which is not rev-shared)

## 1. Which Freemius SDK/API for this stack

Stack (DISCOVERY.md): Tauri v2 shell + Next.js standalone (local sidecar) + FastAPI sidecar + local SQLite. NOT Electron, NOT a hosted SaaS.

| Concern | Choice | Why |
|---|---|---|
| Checkout | **Freemius Hosted Checkout** (URL) opened in the **system browser** (tauri shell-open), not embedded | Keeps the hardened CSP (L6) untouched; no Freemius JS SDK bundled in the webview; matches the desktop app-integration guide's "open checkout, return to app with license key" flow |
| License activation | Freemius **license-key activation API** called directly by the local FastAPI sidecar using **Product ID + Public Key**; response signature verified with the public key | Secret Key never ships inside the app; mirrors the existing Paddle device-binding model (`activated_device_id` in `lib/license.ts`) |
| Renewal/refund events | Freemius **webhooks** → the cloud-hosted Next deployment (same place the Paddle webhook lives today) | A webhook needs a public URL; the local sidecar can't receive one |
| Trial anchor | Server timestamp at activation/first-online-check; local clock fallback capped by offline grace | Prevents trivial trial reset by clock changes; no new infra |

**Anti-goals:** no Freemius WordPress SDK (wrong platform); no checkout iframe in the Tauri webview (CSP + L6); no secret keys in the client bundle; no Always-Online DRM (perpetual license must run offline forever).

## 2. Exact files to change (Phase 4)

| File | Change |
|---|---|
| `lib/license.ts` | Extend `LicenseRecord.gateway` union with `"freemius"`; add `activateFreemiusLicense(key, device_id)` + `verifyFreemiusLicense()` helpers; keep Paddle path for legacy `PPRO-*` keys |
| `app/api/webhooks/freemius/route.ts` | **NEW** — webhook receiver next to `app/api/webhooks/paddle/route.ts` (renewal, refund, dispute events → update Redis license record) |
| `app/api/license/activate/route.ts` | **NEW** — local endpoint the UI calls; proxies Freemius activation, verifies signature, stores activation + device binding |
| `components/BootGuard.tsx` | Add license-state gate: on boot read local license state → allow / trial countdown banner / read-only mode |
| `components/OnboardingModal.tsx` | Final wizard step: "Start 14-day trial" or "Enter license key" / "Buy" (opens hosted checkout) |
| `app/dashboard/license/page.tsx` (or Settings section) | **NEW** — license status card: state, trial days left, key entry, buy button, "export my data" button |
| `backend_fastapi/app/api/deps.py` | Read-only enforcement: when `app_readonly` SystemSetting is true, write routes return 403 **except** auth, license-check, and export/backup routes |
| `backend_fastapi/app/core/models.py` + migration v33 | New SystemSettings keys: `trial_started_at`, `license_state`, `license_key_hash`, `license_device_id`, `app_readonly`, `last_license_check` |
| `.env.example` | Add `FREEMIUS_PRODUCT_ID`, `FREEMIUS_PUBLIC_KEY`, `FREEMIUS_SECRET_KEY` (cloud webhook route only — never bundled), `FREEMIUS_WEBHOOK_SECRET` |
| `src-tauri/tauri.conf.json` | **No change** (no CSP loosening; updater stays GitHub-hosted) |

## 3. License states to handle

| State | Meaning | App behavior |
|---|---|---|
| `trial_active` | 14 days from first run | Full features; countdown banner ("X days left") |
| `trial_expired` | Trial ended, no purchase | **Read-only + data export only** — view/export everything, no sales/edits. Never a lockout. |
| `license_active` | Valid perpetual license (device-bound) | Full features, **forever, offline**; opportunistic revalidation every 7 days when online (only to catch refunds/chargebacks) |
| `license_invalid` | Wrong/tampered key, or key refunded/revoked by webhook | Re-enter-key UI; if a previously-valid state existed, drop to read-only pending the user's next action (support contact shown) |
| `offline_grace` | Online check impossible | See §4 — grace only applies to trial start/first activation; an activated perpetual license needs no grace |

## 4. Proposed offline grace: 21 days

- **Trial start:** anchored to a server timestamp at the first online check; if the machine is offline at first run, the trial runs on the local clock and must complete one online check within **21 days** (configurable constant `OFFLINE_GRACE_DAYS = 21`) to lock the anchor. After that, the app stays fully usable but shows a one-time "connect once to confirm your trial" notice; nothing is disabled (a pharmacy losing internet must never be bricked).
- **Activated license:** no grace logic at all — activation is one-time; the app runs offline indefinitely.
- Rationale (playbook proposal, confirmed): pharmacies genuinely lose internet; the perpetual license means "online" is only ever needed for activation/refund enforcement.

## 5. Data when license/trial expires — read-only + export, never locked out

- Backend enforces `app_readonly`: all write routes → 403 except auth, license-check, **backup/export routes**.
- Export paths already in the product: encrypted backup (`/admin/backup/encrypted`) + restore; Phase 4 adds a plain **JSON/CSV export** button on the license page for the trial-expired state.
- UX copy commitment (store listing FAQ #3 already promises this): "You are never locked out of your data."

## 6. Paddle coexistence (existing system)

- `lib/license.ts` keeps `gateway: "paddle"` records working (legacy `PPRO-*` keys validate through the existing webhook/Redis flow).
- New sales use Freemius; both gateways accepted at the key-entry UI.
- Paddle removal = separate later cleanup (Phase 5+), only after zero active Paddle licenses remain. Also remove then: `@paddle/paddle-js` / `@paddle/paddle-node-sdk` from `package.json` (confirm `app/dashboard/invoice-parse/page.tsx`'s "Paddle" reference is PaddleOCR, not payments).

## 7. Test plan (Phase 4 definition of done)

1. Fresh install → trial starts, countdown correct.
2. Activate test key (Freemius sandbox) → `license_active`, device bound; second device with same key → handled per license-unit rule (1 per computer).
3. Clock tampering (set clock +30d during trial) → state falls back to server anchor when online.
4. Airplane mode after activation → full function indefinitely.
5. Refund the sandbox purchase → webhook flips state → app read-only on next check, export still works.
6. Expired trial → POS write attempts 403; backup/export succeed.
7. pytest coverage for the new deps/middleware; tsc clean; cargo check unaffected.
