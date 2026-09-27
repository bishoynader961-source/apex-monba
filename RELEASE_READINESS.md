# Pharmacy Suite — Release Readiness (v1)

**Date:** 2026-09-27 · **Status:** Feature-complete for v1; Store submission blocked only on external items (EV cert, Partner Center account, public privacy URL).

This document closes the Pharmacy Suite Expansion Blueprint. All blueprint phases
(0–5) and all four post-audit sprints are executed; the remaining work is external
procurement and manual verification, itemized below.

---

## 1. Overall Status

### Done and verified

| Area | State |
|---|---|
| Blueprint Errors #1–#3 | FIXED and re-verified in the Phase 5 audit |
| Criticals (expired-sale checkout, unauthenticated patient_fields) | FIXED with regression tests |
| WC totals identity | Enforced server-side on create **and** update (H6) + client-side inline validation (Step 4.6) |
| JWT | 15-min access TTL (hard code-level cap) + refresh-token rotation + credential-change revocation (schema v28) |
| Auth audit trail | login success/failure, logout, PIN change, password change — all hash-chained with server timestamps |
| Backups | AES-256-GCM encrypted snapshots (`.backup.enc`), key shown once, restore-with-key endpoint; reminder banner at >7 days |
| Performance | Receipt history 1+N → 2 queries; low-stock 1+N → 1; EPCS list 2N → constant; GZip enabled |
| First-run experience | Setup gate (503 until complete) + onboarding modal wired to `setup_complete` |
| Desktop shell | Window-state persistence + off-screen validation, deep-sleep sidecar watchdog, recovery app, updater stub (endpoint-gated) |
| Accessibility | 0 Critical/Serious on POS/inventory/RX (eslint-plugin-jsx-a11y gate) |
| i18n / RTL | 6 locales incl. 100%-complete Arabic; `dir` switching pre-paint; logical CSS properties on audited pages |
| Mobile | SecureStore, offline queue (dead-letter safety), QR/mDNS pairing, biometrics, diagnostics |
| Data integrity | Integer-cents money (Numeric), void audit trail, FEFO, hash-chained audit log |
| Test gates | pytest 852+ passed / 0 failed · desktop tsc 0 · mobile tsc 0 · cargo check 0 errors |

### Remaining before v1 release

See §2 and §5 — every open item is external (certificates, accounts, manual
testing) or an accepted, tracked backlog item. **Nothing critical remains open.**

---

## 2. Microsoft Store Checklist (blueprint §5, current status)

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | EV code-signing certificate | ☐ open | Blocks signing + MSIX repack. Publisher CN placeholder in `src-tauri/package.appxmanifest`. |
| 2 | Partner Center account | ☐ open | Company account recommended. |
| 3 | Privacy policy **public URL** | ☐ open | In-app page exists; `privacy_policy_url` SystemSetting seeded, waiting on a hosted URL. |
| 4 | Age rating | ☐ open | Questionnaire in Partner Center; expected Everyone/3+ (placeholder comment in manifest). |
| 5 | MSIX package | ☐ open | Tauri 2 has no native msix target — repack WiX `.msi` via MSIX Packaging Tool (`MSIX_SUBMISSION_CHECKLIST.md`). |
| 6 | Store icons/screenshots | ☐ open | Icon sizes + POS/inventory screenshots. |
| 7 | Accessibility statement | ☐ partial | Automated gate green (Sprint 3D); manual screen-reader pass outstanding. |
| 8 | In-app privacy policy link | ☒ done | Support page → `/privacy`. |
| 9 | Crash diagnostics | ☒ done | Recovery app + crash reports; no silent data collection. |
| 10 | Auto-update story | ☒ done (stub) | Self-updater endpoint-gated; Store builds distribute updates via Store. |
| 11 | Windows-compatible sidecars | ☒ done | Node + FastAPI sidecars, Job-Object cleanup, port pre-checks. |
| 12 | Data-encryption disclosure | ☒ done | AES-256-GCM backups; DPAPI machine-bound PIN pepper + PHI fields. |

---

## 3. Known Limitations (tracked, accepted)

1. **Offline-queue duality (mobile):** `mobile/lib/offlineQueue.ts` (drawer movements, legacy) coexists with `mobile/stores/offlineQueue.ts` (checkouts, spec). Unify or document separation before v1.1.
2. **Audit timestamps before `4c3c9bf`:** rows written before that commit have `timestamp = null` (pre-fix); not retroactively fixable.
3. **CSP `style-src 'unsafe-inline'`:** required by the current styling pipeline; script-src is fully locked.
4. **`pharmacy_id` not seeded:** setup wizard populates it (Phase-5 backlog note); harmless until multi-site features.
5. **`initialize()` fan-out:** hardening candidate pre-v1 (PROJECT_MAP backlog).
6. **Fix-code key rotation runbook:** `FIX_CODE_SECRET` lives in two places (backend `.env` + `src-tauri/src/fix_key.txt`) — rotate atomically.
7. **Server bundle >300 KB stat (route chunks):** all chunks < 300 KB gzip (Sprint 3C) — acceptable as-is.

---

## 4. Pre-Release Manual Testing Checklist (pharmacist walkthrough)

**POS & Shifts**
1. Open a shift with a float; sell an OTC item with cash and with card; verify receipt prints (Windows print dialog) and change-due math.
2. Attempt to sell a medicine with an expired lot on the shelf → expect the explicit "Cannot sell expired stock" rejection (never silently substitutes a fresh lot).
3. Race two checkouts (desktop + paired mobile) for the last unit → exactly one succeeds.
4. Void an item on a receipt → verify the audit trail entry and stock restoration.

**Inventory**
5. Receive a batch with a near-expiry date → verify the expiry badge/alert counts.
6. Trigger low stock on an item → verify the dashboard low-stock card.

**Patients / WC**
7. Create a WC claim with total ≠ insurance + patient → blocked client-side *and* server-side (422).
8. Use the WC claim patient autocomplete (type 2+ characters).

**Backups & Recovery**
9. Create an encrypted backup → save the shown key; delete data; restore with the key; then attempt restore with a wrong key (expect 400).
10. Check the amber reminder appears after 7+ days without backup and disappears after a new backup.

**Desktop Shell**
11. Move/resize the window, quit, relaunch → position/size restored.
12. Disconnect the external monitor (if used), relaunch → window recenters (not off-screen).
13. Put the PC to sleep mid-session, resume → app self-recovers within ~40 s (watchdog).

**Access & i18n**
14. Log in as cashier → no admin pages; onboarding "Explore" path does not error.
15. Switch language to العربية → layout mirrors; all pages readable.
16. Leave the app idle past the session timeout → re-auth required.

---

## 5. Estimated Remaining Work

| Item | Estimate |
|---|---|
| EV certificate procurement + Partner Center setup | 2–4 h effort (+ external lead time) |
| Store icon set + screenshots | 3 h |
| MSIX repack + signed local install test | 3 h |
| Public privacy-policy hosting + setting | 1 h |
| Manual a11y pass (screen reader) | 4 h |
| Manual pharmacist walkthrough (§4) | 6 h |
| Store listing copy + submission | 3 h |
| **Total** | **~22 h + review lead time** |

---

*Generated by the blueprint execution agent at the close of Sprint 4. Gates at time of writing: pytest 852+/0 failed · desktop tsc 0 · mobile tsc 0 · cargo check 0 errors (6 pre-existing warnings).*
