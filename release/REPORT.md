# Release Engineering Report — Phases 0–3 (SELL_PHARMACY_APP_PLAYBOOK)

Branch: `release/launch-prep` (never touches `main`). Format: newest phase on top.

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
