# Release Engineering Report — Phases 0–3 (SELL_PHARMACY_APP_PLAYBOOK)

Branch: `release/launch-prep` (never touches `main`). Format: newest phase on top.

---

# FINAL SUMMARY — Phases 0–3 COMPLETE (2026-10-03)

## What was completed
- **Phase 0 Discovery** → [`DISCOVERY.md`](DISCOVERY.md): stack confirmed (Tauri v2 + Next.js 16 + FastAPI + SQLite, offline-capable Windows desktop); PHI stored plaintext in live DB (DPAPI `phi_encrypt` defined but unwired — backups ARE AES-256-GCM encrypted); auth/RBAC + first-run wizard (no default creds); single-branch; 6 locales with Arabic RTL; preliminary license scan. Owner answered all gating questions.
- **Phase 1 Pre-sale audit** → [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) + [`AUDIT.md`](AUDIT.md) + [`demo/`](demo/README.md): **no GPL/AGPL blockers** across 1,120 deps (npm/Python/Rust); pytest 917/1 ✅, cargo check 0 err ✅, tsc clean ✅, vitest 54/54 ✅; no hardcoded paths/timezones; backup→restore round-trip **MATCH: True**; demo dataset (20 drugs/5 patients/10 receipts/2 suppliers) + verified loader.
- **Phase 2 Decisions** → [`DECISIONS.md`](DECISIONS.md): one-time **$149** + optional $59/yr renewal; 14-day trial; 14-day no-questions refund; 1-year updates; email support 48h; "Pharmacy Suite" by "Apex Software"; support pharmacypro.support@gmail.com; market Egypt+Arab world, USD base. All owner-approved.
- **Phase 3 Freemius setup** → store copy + screenshot plan + integration plan + owner steps: [`store-copy/freemius_listing.md`](store-copy/freemius_listing.md), [`store-copy/screenshot_plan.md`](store-copy/screenshot_plan.md), [`LICENSE_INTEGRATION_PLAN.md`](LICENSE_INTEGRATION_PLAN.md), HUMAN_TODO §P1.

## Official-source confirmations (verified 2026-10-03, per hard rule 9)
1. **Egypt is on Freemius' supported payout-countries list** ("Supported Countries for Payouts" — Egypt listed; payouts via Payoneer/Wise/PayPal/wire): https://freemius.com/help/documentation/selling-with-freemius/supported-countries.md
2. **Pharmacy management software is not prohibited** — "Downloadable Software … desktop and mobile apps" is an explicitly accepted category; no pharmacy/healthcare-management restriction exists. Caveat honored: products giving *medical/diagnostic advice* are restricted, so the listing describes record-keeping/management features only (FAQ/feature copy wording). Sources: https://freemius.com/help/documentation/selling-with-freemius/allowed-prohibited-products.md + llms.txt index https://freemius.com/help/llms.txt
3. **Fees for a desktop app (SaaS & Software plan): 4.7% revenue share per successful transaction + ~3.5% average gateway fee; no setup, monthly, payout, currency-conversion, or VAT-rev-share fees**; growth pricing drops rev-share from $50k/mo. Source: https://freemius.com/help/documentation/getting-started/our-pricing.md (on a $149 sale ≈ $12.22 total ≈ 8.2%, excl. VAT).
4. Payout mechanics (Payoneer/Wise/PayPal/wire; 10th monthly, $100 minimum, ~2-month first-payout delay): https://freemius.com/help/documentation/selling-with-freemius/your-earnings.md

## Waiting for owner input
1. **Logo 512×512 PNG** (HUMAN_TODO §L2) — blocks Freemius product creation.
2. **2FA on pharmacypro.support@gmail.com** (§L1 remainder).
3. **Clean-machine install test** (§L3) — pre-sale gate.
4. **8 screenshots incl. 2 Arabic-RTL** (§L4) after loading the demo dataset.
5. **Freemius account + product + keys** (§P1, 11 click-by-click steps) — KYC/payout/legal steps are owner-only by rule.
6. Phase 4 go-ahead after P1 (product ID + keys via local .env).

## HUMAN_TODO items added by launch prep (numbered)
- **L1** Support inbox — RESOLVED (email chosen; 2FA remains).
- **L2** Logo 512×512 PNG — OPEN, blocks P1 step 7.
- **L3** Clean-machine install test — OPEN, **pre-sale gate**.
- **L4** Arabic/RTL screenshot confirmation — OPEN, folds into screenshots.
- **P1** Freemius account/product/pricing/keys — OPEN (11 steps, cited URLs).

## BLOCKERS
**None.** (Clean-machine test L3 is a manual gate, tracked in HUMAN_TODO — not a code blocker. Non-blocking observations recorded in AUDIT.md: `backup.py` by-value `_engine` import; PHI-at-rest unwired; cosmetic license fields.)

## What comes next
**Phase 4 — Freemius license integration** (implementation per [`LICENSE_INTEGRATION_PLAN.md`](LICENSE_INTEGRATION_PLAN.md)) once P1 delivers the product ID + keys. Then: screenshots, store publishing, and the release build.

---

---

## Phase 3 — SELLING PLATFORM SETUP ✅ COMPLETE (2026-10-03)

**Did:**
- Fetched https://freemius.com/help/llms.txt (mandated first step) and confirmed all three gates from official pages (URLs cited in the FINAL SUMMARY above): Egypt payouts ✅, product category allowed ✅, fees 4.7% + ~3.5% gateway ✅.
- 3.1 → [`store-copy/freemius_listing.md`](store-copy/freemius_listing.md): name, EN+AR tagline (≤12 words), EN+AR short description, 10 verified feature bullets EN+AR (each mapped to code from DISCOVERY/AUDIT), system requirements (Windows 10+/4 GB/500 MB — consistent with the Tauri+sidecar stack), 5-question EN+AR FAQ, 10 EN + 10 AR keywords.
- 3.2 → [`store-copy/screenshot_plan.md`](store-copy/screenshot_plan.md): exactly 8 screenshots (screen, demo-data state, buyer rationale); capture = owner step (HUMAN_TODO §L4).
- 3.3 → HUMAN_TODO **§P1**: 11 click-by-click Freemius account/product steps with direct URLs (Get Started → SaaS & Software plan → 2FA → identity verification → Payoneer/Wise payout → product from listing copy → pricing per DECISIONS → 14-day trial + 14-day refund → sandbox test → copy Product ID + keys to local .env).
- 3.4 → [`LICENSE_INTEGRATION_PLAN.md`](LICENSE_INTEGRATION_PLAN.md) (plan only, no code): **Hosted Checkout in system browser + direct license-key activation API from the FastAPI sidecar (public-key verified, secret never ships) + webhooks to the cloud Next app**; 9 exact files to change (reconciling `lib/license.ts` Paddle gateway — Freemius added as new gateway, Paddle kept for legacy keys); 6 license states incl. `offline_grace`; **21-day offline grace** (trial anchor only — activated perpetual license runs offline forever); expired = read-only + export, never lockout; 7-item Phase 4 test plan.

**Official docs > playbook deviations (rule 7):** (a) plan selection is "SaaS & Software" (desktop apps), not the playbook's literal "Desktop / Web App" button label; (b) fees verified as 4.7% rev-share + ~3.5% gateway, not a flat per-transaction number. Both cited above.

**Left / next:** everything in "Waiting for owner input"; then Phase 4 implementation.

---

## Phase 2 — PRODUCT DECISIONS ✅ COMPLETE (2026-10-03) — commit 095b656

**Did:** Confirmed all playbook defaults with the owner via structured questions (each explicitly approved, none invented) → [`DECISIONS.md`](DECISIONS.md): pricing A one-time **$149** + optional $59/yr renewal; trial **14d**; refund **14d no-questions**; updates **1 year**; support **email 48h**; name **Pharmacy Suite**; publisher **Apex Software**; email **pharmacypro.support@gmail.com**; market **Egypt + Arab world**; currency **USD** base.

**Decisions made:** all values owner-approved; logo still pending (§L2) — recorded as a blocker only for P1 step 7, not for Phase 3 artifacts.

---

## Phase 1 — PRE-SALE AUDIT ✅ COMPLETE (2026-10-03) — commit 426dd47

**Did:**
- **License scan** (`license-checker`, `pip-licenses`, `cargo-license` — 1,120 components): **no GPL/AGPL blockers**. Notables: libvips LGPL-3.0 via sharp binaries (dynamically loaded → notice + replaceability only), `jszip` dual MIT/GPL (MIT side), PyInstaller GPLv2 **with bootloader exception** (commercial bundling allowed), `webpki-root-certs` CDLA-Permissive-2.0 → [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
- **First-run setup verified in code**: fresh-DB-only endpoint, server-side password complexity, 5/min rate limit, no default creds; all routes 503-gated until setup completes.
- **Hardcoded paths**: 0 hits for `C:\Users\` / `/home/` in app code.
- **Demo dataset** shipped at [`release/demo/`](demo/README.md): 20 fake drugs w/ expiry, 5 fake patients, 2 fake suppliers, 10 receipts (21 items) — loader mirrors the backend lifespan; verified exit 0, receipt totals consistent, `--clean` idempotent reload. Demo DB gitignored (regenerable).
- **Quality gates**: pytest **917/1** ✅, cargo check **0 errors** (6 known warnings) ✅, tsc **clean** ✅, vitest **54/54** ✅.
- **Backup→restore E2E**: automated test (backup 201 → restore 200 → wrong key 400) **plus** file-level round-trip on the demo dataset — decrypted restore into a fresh DB matched counts/totals/content (**MATCH: True**). Restore IS implemented — no blocker.
- **Arabic/RTL**: implemented (RTL pre-paint + on-switch, 6-locale key-parity test); visual RTL check folds into screenshot capture (HUMAN_TODO §L4).
- **HUMAN_TODO**: added §L3 clean-machine install test (**pre-sale gate**) and §L4 Arabic-RTL screenshot confirmation.

**BLOCKERS: none.** Observations (non-blocking): `backup.py` by-value `_engine` import (latent trap, benign in packaged app), PHI-at-rest still unwired (B5) — copy guidance in DISCOVERY §3.

**Next:** Phase 2 product decisions (owner confirmations) → Phase 3 Freemius setup.

---

## Phase 0 — DISCOVERY ✅ COMPLETE (2026-10-03)

**Did:**
- Created `release/launch-prep` from `fix/batch5-correctness` @ 9bbe97a (hardening leftovers committed & pushed first).
- Inspected repo and answered playbook Q1–Q5 from code → [`DISCOVERY.md`](DISCOVERY.md):
  - Stack confirmed: Tauri v2 + Next.js 16 + FastAPI + SQLite (aiosqlite, PRAGMA user_version v32); Windows desktop, offline-capable.
  - Patient PHI stored **plaintext** in live SQLite (`phi_encrypt` defined but unwired); AES-256-GCM encrypted backups + restore exist. Marketing copy must not claim at-rest encryption until B5 ships.
  - Auth/RBAC (Role+RolePermission), first-run wizard creates the owner's own admin password (fresh-DB-only endpoint, rate-limited, server-side complexity check; no default creds). Single-branch (no branch model). 6 locales, Arabic RTL implemented.
  - License scan: **no GPL/AGPL blockers**; 2 LGPL-3.0+ npm packages to identify in Phase 1.1; PyInstaller GPLv2+bootloader-exception (commercial bundling allowed); Rust direct deps permissive.
- Drafted 2 pricing options (one-time $149 vs subscription $9/mo–$89/yr) with pros/cons → asked owner to choose.

**Waiting on owner (Phase 0 gate — Phase 1 blocked until answered):**
1. Pricing model choice (A/B) 2. Target market 3. Buyer currency 4. App display name 5. Publisher name 6. Support email 7. Logo 512×512 ready?

**Decisions made:** executed from the prompt's playbook text (`SELL_PHARMACY_APP_PLAYBOOK.md` not found in repo); recommendation recorded for Option A but nothing decided without owner.

**Fee/country/policy claims:** none made this phase (no external services touched).

**Left / next:** Phase 1 (license deep-scan incl. `cargo-license`, clean-machine install test → HUMAN_TODO, demo dataset, AUDIT.md) — **starts after owner answers**.
