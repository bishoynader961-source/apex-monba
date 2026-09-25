# Application Security Hardening — Verification Record

Status of each hardening claim from the Final UX & Security Audit spec, with
the evidence and (where changed) the change made.

## 1. Backend binds loopback only (default install)

**Verified.** `src-tauri/src/lib.rs` spawns the FastAPI sidecar with
`--host 127.0.0.1 --port 8000` (line ~595). The OS refuses connections from
other machines to a loopback-bound socket, so on a default single-terminal
install the API is unreachable from the network regardless of CORS.

Runtime confirmation: `netstat` during desktop verification showed
`TCP 127.0.0.1:8000 ... LISTENING` — bound to the loopback address only.

**Startup log line added** (`lib.rs`): the spawn now logs the bind scope
(`backend listening on 127.0.0.1:8000 (loopback only; other machines cannot
connect)`) so an operator reading logs can confirm the posture.

## 2. CORS scope — why LAN origins exist (do not "tighten" blindly)

`backend_fastapi/app/main.py` allows `localhost:3000`/`127.0.0.1:3000` plus
**private-subnet origins (192.168/10/172.16)** and matches them via regex.
This is deliberate, documented product surface:

- SPEC 07 multi-terminal sync: Client Terminal tablets/PCs call the Main
  Server's LAN IP directly.
- SPEC 08 mobile companion (Expo) calls the desktop over LAN.

CORS is browser-enforced anyway; the real network gate is the loopback bind +
auth. **Terminal Mode flips the bind intentionally** (lib.rs reads
`terminal_mode` from the DB), and every protected route still requires a JWT
with role/permission checks (`role_id==1 → "*" → explicit`).

## 3. Database file permissions

**Verified by Windows inheritance.** The DB lives in
`%APPDATA%\PharmacySuite\` (`config.get_app_data_dir()`), i.e.
`C:\Users\<only this user>\AppData\Roaming\...`. Profiles on Windows are
ACL-restricted to that user + SYSTEM/Administrators by default — other local
users cannot traverse into it. No per-file ACL is added because the parent
already enforces the right policy; adding redundant ACLs risks breaking
restore/backup flows.

Cross-platform note: on macOS/Linux the equivalent is `$HOME/Library/
Application Support` / `$XDG_DATA_HOME`, both 0700 by OS convention.

`secret.key` additionally gets explicit `os.chmod(path, 0o600)`
(`config.py:57`) — meaningful on POSIX, a no-op-where-inapplicable on Windows
(where profile ACLs govern).

## 4. Rate limiting + attack surface

- SlowAPI rate limiter registered app-wide (`main.py:186-187`) with a uniform
  429 handler; login endpoints are covered.
- OpenAPI docs disabled in the packaged app (`docs_url=None, redoc_url=None`)
  — no endpoint map for an attacker to browse.
- Uniform error contract: no tracebacks leak; app exceptions map to status
  codes with safe messages.
- `x-content-type-options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, restrictive CSP on API responses.

## 5. Update/patch channel (cross-ref)

See `docs/UPDATE_STRATEGY.md`: Ed25519-signed updates, public key embedded in
the binary, unsigned/tampered packages rejected before execution. This closes
the "malicious patch delivered as support" social-engineering route: users can
be told to **only** update via the in-app button.

## 6. Residual risks (honest list)

| Risk | Mitigation status |
|---|---|
| Scammer emails mimicking support on free-mail lookalike domains | In-app Security Notice (primary); domain migration recommended (`SUPPORT_EMAIL_SECURITY.md`) |
| User voluntarily sends `pharmacy.db` when asked by a phisher | Notice + diagnostics report carries none of it; nothing in-app can send the DB |
| LAN deployments expose API to subnet | Intentional (SPEC 07/08); JWT + permission gates apply; loopback default on single installs |
| Private updater key loss/compromise | Gitignored, backup guidance + rotation procedure in UPDATE_STRATEGY.md |
