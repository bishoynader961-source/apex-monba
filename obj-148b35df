# Update Delivery Strategy — Pharmacy Suite Desktop

## Overview

Desktop updates use the **Tauri v2 Updater plugin** with **Ed25519 signature
verification**. The app checks a remote manifest, verifies the update's
signature against a public key embedded in the binary, and only then downloads
and applies it. A tampered or unsigned package is rejected before execution.

```
┌─────────────┐   1. GET latest.json   ┌──────────────────────┐
│ Installed   │ ─────────────────────▶ │ GitHub Releases      │
│ app (v1.0.0)│ ◀───────────────────── │ (latest.json +       │
│             │   2. version + url +   │  signed artifacts)   │
│             │      signature         └──────────────────────┘
│             │
│             │   3. download artifact
│             │   4. verify Ed25519 signature vs embedded pubkey  ← security gate
│             │   5. apply + relaunch (tauri-plugin-process)
└─────────────┘
```

## Components shipped in this change

| Piece | File |
|---|---|
| Updater plugin registration (Rust) | `src-tauri/src/lib.rs` (`tauri_plugin_updater`, `tauri_plugin_process`) |
| Endpoint + embedded public key | `src-tauri/tauri.conf.json` → `plugins.updater` |
| Signing enabled **only** in release builds | `src-tauri/tauri.release.conf.json` (`createUpdaterArtifacts: true`) |
| Check/verify/download/relaunch UI | `components/UpdateChecker.tsx` (Settings → Appearance → App Updates) |
| Capabilities | `src-tauri/capabilities/default.json` (`updater:default`, `process:allow-restart`) |
| Release builder + manifest emitter | `scripts/prepare-release.mjs` |
| Signing keypair (private **never committed**) | `src-tauri/updater-key/` (gitignored; `.pub` is public) |

## Key ceremony (do once, guard forever)

1. Private key: `src-tauri/updater-key/pharmacy-suite.key` — already generated,
   **gitignored** (verified). Back it up to a password manager / offline vault.
   Losing it means publishing updates users can't verify; the remedy is a new
   key + a new app release that embeds it.
2. Public key is embedded in `tauri.conf.json` → compiled into every binary.
   Users are protected even if the update endpoint is fully compromised:
   an attacker who controls the endpoint can serve *anything* except an update
   that verifies against this key.
3. Signing env (release builds only): `TAURI_SIGNING_PRIVATE_KEY_PATH`
   (password empty by default; set `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` if you
   rotate to an encrypted key).
4. If the key is ever suspected compromised: generate a new pair, ship one
   final update signed with the OLD key that embeds the NEW public key, then
   rotate.

## Release runbook

```bash
# version bump first: tauri.conf.json + Cargo.toml + package.json + wix.version
TAURI_SIGNING_PRIVATE_KEY_PATH=src-tauri/updater-key/pharmacy-suite.key \
  node scripts/prepare-release.mjs "Fixes X, adds Y"
# → emits release-updates/latest.json + signed artifacts
# → publish as GitHub Release v<version> (latest.json + artifacts + .sig files)
```

The updater endpoint points at
`…/releases/latest/download/latest.json`, so publishing the release is the
entire deployment. No server to run; GitHub's CDN does the distribution.

## Database schema migration contract (v1.0.0 → v1.0.1 and beyond)

The updater replaces binaries; it never touches `%APPDATA%\PharmacySuite`.
On first launch after an update, the FastAPI sidecar runs startup migrations:

- `backend_fastapi/app/core/database.py::run_migrations` is **versioned,
  idempotent, and restart-safe** via `PRAGMA user_version`: each migration runs
  in a transaction, bumps the version, and is skipped if already applied. A
  crash mid-migration re-runs cleanly on next start.
- Fresh DBs are created at `SCHEMA_VERSION` directly (`create_all` + version
  stamp) — no replay of historical migrations.
- **Rules for any new migration (the contract):**
  1. Additive first (new table/column with default). Column adds use the
     existing `column_exists` guard; never assume presence.
  2. Never destroy or repurpose existing columns in a patch release; widen,
     don't rewrite. Deprecate → migrate data → remove across releases.
  3. No interactive input during migration; failures are logged and the app
     still boots (seed/migration failures never block startup).
  4. Pre-update safety net: the app already writes a `vacuum_backup` snapshot
     on a timer, so a bad update has a recent pre-migration copy to restore.
  5. Bump `SCHEMA_VERSION` once per release; test upgrading a copy of a real
     v(n−1) DB before shipping.

**Why updates are restart-based:** the updater applies and relaunches
(`process:allow-restart`); the FastAPI sidecar is killed with the parent
(Windows Job Object, kill-on-close) and re-spawned on boot — which is exactly
when migrations run. There is no path where old code writes a new schema or
new code reads an un-migrated DB mid-session.

## Failure modes handled

| Failure | Behavior |
|---|---|
| Update endpoint unreachable / offline | `check()` throws → friendly error in Settings; app continues normally |
| Signature mismatch (tampered/hostile artifact) | Plugin refuses before execution; UI shows "Updates are cryptographically verified" |
| Download interrupted | Tauri restarts the download on next check; nothing applied half-built |
| Migration fails after update | Logged, non-fatal; DB left consistent by per-migration transactions; snapshot available |
