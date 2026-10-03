# Release Engineering Report — Phases 0–3 (SELL_PHARMACY_APP_PLAYBOOK)

Branch: `release/launch-prep` (never touches `main`). Format: newest phase on top.

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
