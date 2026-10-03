# HUMAN TODO — actions only the owner can take

Items here are deliberately **not** automated: they are irreversible, or they
require credentials/systems the agent does not have. Each item names the audit
finding it closes.

## URGENT — Do before announcing PR #32 is merged

The old FIX_CODE_SECRET shipped inside the compiled binary and is in git
history. Rotate it now:
1. Generate a new secret: python -c "import secrets; print(secrets.token_hex(32))"
2. Update FIX_CODE_SECRET in the .env file on every installed machine
   (yours + any customer installs).
3. Restart the FastAPI sidecar on each machine.
4. Old fix codes signed with the old key will stop working — this is correct.
5. Update your support tool that generates fix codes to use the new key.
6. Also rotate FIX_ADMIN_KEY by the same process.

## Batch 3 — Secrets & trust (M4, M3, L4, L5)

### 1. Rotate FIX_CODE_SECRET on every production install (audit M4) — REQUIRED

**Rotate FIX_CODE_SECRET in production .env files on all installs, since the old
key shipped in the binary.** (`src-tauri/src/fix_key.txt`, compiled via
`include_str!`, was extractable from `app.exe`; treat it as compromised.) The
desktop no longer embeds any key; verification now happens online against the
backend.

Per install (each main device):

1. Generate a new secret: `openssl rand -hex 32`.
2. In that install's backend `.env` (the sidecar's working directory, e.g.
   `%APPDATA%\PharmacySuite\.env` when present, or `backend_fastapi/.env` for a
   dev/QA checkout) set the value:
   `FIX_CODE_SECRET=<new value>`
3. Add the admin key used together with fix codes (the desktop no longer
   embeds it either):
   `FIX_ADMIN_KEY=<openssl rand -hex 24>`
   Support tooling must sign/issue fix codes with the same values.
4. Restart the app so the sidecar re-reads `.env`.
5. Old fix codes are rejected (fail closed) after rotation — regenerate any
   outstanding ones with the new secret.

Operational note: applying a fix code now requires the local backend to be
running (the recovery engine fails closed with `VERIFY_UNAVAILABLE` when it
cannot reach `127.0.0.1:8000`). Support instructions should say: start Pharmacy
Suite once, then retry the fix.

### 2. Delete local key copies (audit M4) — RECOMMENDED

`src-tauri/src/fix_key.txt` and `src-tauri/src/fix_admin_key.txt` are already
gitignored and are no longer compiled in. Delete them from developer machines so
they cannot accidentally be copied into a build or reused after rotation.

### 3. Clear legacy localStorage tokens on existing installs (audit M3) — OPTIONAL

Devices that ran an older version may still hold `access_token` /
`refresh_token` entries in the webview's localStorage. The new frontend never
reads them, so they are inert; clearing them would need a one-time cleanup pass
(DevTools → Application → Local Storage). If any of those machines ever ran an
untrusted extension, rotate the affected admin passwords as the safe follow-up.

### 4. L4 / L5 need no manual step (audit L4, L5) — NO ACTION

- Signed UDP discovery self-migrates: the next broadcast from an updated main
  device carries the signature; legacy unsigned packets are ignored. Manual IP
  entry remains available for mixed-version networks.
- The `approval_jti` table is additive (schema v30) and self-prunes rows older
  than 120 s; no data migration or cleanup is required.
