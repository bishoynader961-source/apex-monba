# SPEC 09 — Remote Diagnostics: File Logging + Opt-in Reporting + Version Ping

**Purpose:** Close the gap found in the Spec 07 Part 4 audit: today there is **no way
to help a buyer remotely**. Crash reports, backend logs, and the audit trail are all
local-only. This spec layers three capabilities — in increasing order of effort — so
a buyer issue can be triaged from an email instead of a screen-share.

**Depends on:** Spec 08 (Support tab + diagnostic report) — already implemented.

---

## PART 1 — Local File Logging (backend)

**Problem:** `backend_fastapi/app/shared/logging_config.py` writes structured JSON
to **stdout only**. In the packaged app the sidecar's stdout goes to
`%APPDATA%\com.pharmacysuite.app\pharmacy_sidecar.log` (via Tauri's pipe), which
works — but only while the app spawns the backend through that pipe, and the log
has no rotation.

**Change (small):** add a `logging.handlers.RotatingFileHandler` in
`configure_logging()`:

- Path: `%APPDATA%\PharmacySuite\logs\backend.log` (reuse `get_app_data_dir()`)
- Rotation: 5 MB per file, keep 3 backups
- Format: the existing structlog JSON line, unchanged
- Result: a durable, bounded log file a user can attach to a support email

**Acceptance:** run the app 10 minutes, confirm `backend.log` exists, is JSON per
line, and rotates when forced over 5 MB.

---

## PART 2 — Opt-in "Send Diagnostics" (frontend + collector)

**Problem:** Spec 08's crash report button is hidden unless
`NEXT_PUBLIC_CRASH_REPORT_URL` is set, and no collector exists. Buyers currently
copy/paste diagnostics into email — fine to start, but high-friction.

**Change:**

1. **Collector** (choose when ready; both are <100 lines):
   - **Cheapest:** a FastAPI function on any PaaS free tier:
     `POST /crash-report` → append JSON line to SQLite + optional SMTP email.
     Store only: report_text, app_version, pharmacy_name (optional), user_id
     (local ID only), submitted_at, and a random report_id.
   - **Or:** a GitHub Issue via a repo-scoped token from a tiny proxy
     (never embed the token in the app).

2. **Frontend:** set `NEXT_PUBLIC_CRASH_REPORT_URL` at build time; Spec 08's
   button and privacy notice are already wired and CSP-documented.

3. **Consent UX (required):** the Send button must remain **user-initiated
   per-report** (it already is). Never auto-send. The privacy notice under the
   button is already implemented and must be kept.

**Acceptance:** a buyer clicks Send; a structured report arrives with report_id;
no PHI/PII beyond pharmacy name (which the buyer can blank in Settings).

---

## PART 3 — Version Ping (update awareness)

**Problem:** `GET /api/v1/version` exists but returns `update_available: false`
unless `UPDATE_CHECK_URL` is set; nothing calls it on a schedule.

**Change:**

1. Deploy a static JSON: `{ "latest_version": "1.0.1", "download_url": "...",
   "release_notes": "..." }` on any static host.
2. Set `UPDATE_CHECK_URL` in the packaged backend environment.
3. Frontend `useVersionCheck` hook already exists — confirm it surfaces
   "update available" as a **non-blocking banner** on the dashboard, once per
   session. No auto-download, no forced updates.

**Acceptance:** bump `latest_version` on the host → the banner appears on next
app start.

---

## Privacy constraints (apply to ALL parts)

- Never transmit: patient names, prescription/medication data, addresses,
  phone numbers, passwords, tokens, or the full DB.
- Allowed: app version, platform, DB size, aggregate counts, error log lines
  (status/method/URL only), pharmacy name, local user_id.
- The diagnostic report generator (`app/dashboard/support/page.tsx` →
  `generateDiagnosticReport()`) is the single choke point — audit it whenever
  it changes.
- Crash-report collector retention: 90 days, then delete.

---

## Roadmap order

1. Part 1 (file logging) — no external deps, do first
2. Part 3 (version ping) — static host + existing endpoint, trivial
3. Part 2 (collector + Send button) — deploy when you want real telemetry
