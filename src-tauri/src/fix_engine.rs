// ── Fix Engine (Blueprint Task 2, Step 2.4 — Layer 4, security-critical) ─────
//
// PURPOSE: verify and apply "fix codes" — signed data patches sent by
// PharmacySuite support. A fix code is NOT executable code; it is a small
// JSON envelope whose HMAC-SHA256 signature can only be produced by the
// holder of the signing secret (PharmacySuite support tooling).
//
// KEY MANAGEMENT (owner decision, 2026-09-26):
//   * This binary HARD-CODES the signing key as a `const` below. It is not
//     read from any config file the user can edit (invariant #4).
//   * The backend sidecar keeps the identical value in its `.env`
//     (backend_fastapi/.env) — acceptable per the same decision because that
//     file is installed outside the user's reach and is not user-editable.
//   * Both places must hold the SAME bytes so one signed envelope verifies
//     on the desktop engine and on the backend endpoint. The companion CLI
//     (`scripts/make-fix-code.py`) signs with the backend copy.
//   * Rotation = change both places in the same release (KNOWN_ISSUES #11).
//
// SECURITY MODEL (why each check exists):
//   1. Signature (constant-time compare): nobody without the secret can
//      mint or alter a patch — this is the anti-forgery core.
//   2. Canonical JSON: the signature covers an exact byte sequence. Python's
//      json.dumps default formatting (", " / ": " separators, sorted keys,
//      ensure_ascii) is the canonical form shared by the backend verifier
//      and the CLI. Any other byte layout would fail the HMAC even with the
//      right key.
//   3. Expiry: stolen old codes die on their own.
//   4. Version match: a patch written for 1.0.x cannot act on 2.x binaries.
//   5. Whitelist: even a validly-signed code can only perform operations
//      this engine explicitly implements. There is no eval, no shell, no
//      arbitrary file I/O, no network, no patient-data access — by
//      construction, not by policy.
//   6. Errors are fixed friendly codes (invariant #7); details go to the
//      sidecar log for support, never to the UI.

use serde::Deserialize;
use serde_json::Value;

/// The signing key, compiled into this binary.
/// SECURITY: single source of truth on the desktop; see module docs above.
/// Set at build time from the owner's secret store — same bytes as the
/// backend's FIX_CODE_SECRET.
const FIX_CODE_KEY: &str = include_str!("fix_key.txt");

/// Allowed setting keys for UpdateSystemSetting (defense in depth: the
/// backend has its own rules; this engine re-verifies everything locally).
const ALLOWED_SETTING_KEYS: &[&str] = &[
    "session_idle_minutes",
    "session_absolute_minutes",
    "terminal_mode",
    "mobile_access_mode",
    "support_email",
];

/// User-facing error codes (invariant #7 — nothing else ever reaches the UI).
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FixError {
    InvalidFormat,
    InvalidSignature,
    Expired,
    VersionMismatch,
    UnknownOperation,
    NotApplicable,
}

impl FixError {
    pub fn as_code(self) -> &'static str {
        match self {
            FixError::InvalidFormat => "INVALID_FORMAT",
            FixError::InvalidSignature => "INVALID_SIGNATURE",
            FixError::Expired => "EXPIRED",
            FixError::VersionMismatch => "VERSION_MISMATCH",
            FixError::UnknownOperation => "UNKNOWN_OPERATION",
            FixError::NotApplicable => "NOT_APPLICABLE_HERE",
        }
    }
}

impl std::fmt::Display for FixError {
    fn fmt(self: &Self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_code())
    }
}

/// The envelope, exactly as the backend `FixCodeIn` schema defines it:
/// {"action": "...", "payload": {...}, "sig": "<hex>"}.
#[derive(Debug, Deserialize)]
pub struct FixEnvelope {
    pub action: String,
    pub payload: Value,
    pub sig: String,
}

// ── Python-compatible JSON canonicalization ─────────────────────────────────
// json.dumps(obj, sort_keys=True) defaults: separators ", " and ": ",
// ensure_ascii=True (non-ASCII escaped as \uXXXX), floats via repr.
// The HMAC is computed over exactly those bytes; the backend and CLI use
// the same, so byte fidelity here is what makes cross-platform codes work.

fn py_escape_string(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c if (c as u32) > 0x7e => {
                // ensure_ascii: encode as \uXXXX (with surrogate pairs for
                // astral planes, matching Python's behavior).
                let code = c as u32;
                if code > 0xffff {
                    let v = code - 0x1_0000;
                    let hi = 0xd800 + (v >> 10);
                    let lo = 0xdc00 + (v & 0x3ff);
                    out.push_str(&format!("\\u{:04x}\\u{:04x}", hi, lo));
                } else {
                    out.push_str(&format!("\\u{:04x}", code));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn py_json(value: &Value) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(true) => "true".to_string(),
        Value::Bool(false) => "false".to_string(),
        Value::Number(n) => {
            // Integers serialize plainly. For floats, Python uses repr()
            // which round-trips; serde_json's Display for f64 does too.
            n.to_string()
        }
        Value::String(s) => py_escape_string(s),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_json).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => {
            // sort_keys=True: lexicographic by key (byte order on ASCII keys).
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            let parts: Vec<String> = keys
                .into_iter()
                .map(|k| format!("{}: {}", py_escape_string(k), py_json(&map[k])))
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
    }
}

/// HMAC-SHA256 hex digest over canonical JSON — mirrors the backend's
/// `sign_payload` byte-for-byte.
fn sign_payload(payload: &Value, key: &[u8]) -> String {
    use hmac::{Hmac, Mac};
    use sha2::Sha256;
    let message = py_json(payload);
    let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(key).expect("HMAC accepts any key size");
    mac.update(message.as_bytes());
    let bytes = mac.finalize().into_bytes();
    let mut hex = String::with_capacity(bytes.len() * 2);
    for b in bytes.iter() {
        hex.push_str(&format!("{:02x}", b));
    }
    hex
}

/// Constant-time comparison — mirrors `hmac.compare_digest`.
/// SECURITY: a naive == leaks how many bytes matched via timing; a fix-code
/// forger could use that as an oracle to reconstruct signatures.
fn ct_eq(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.bytes().zip(b.bytes()) {
        diff |= x ^ y;
    }
    diff == 0
}

#[derive(Debug, Deserialize)]
struct PatchMetadata {
    #[serde(rename = "expiresAt")]
    expires_at: String,
    version: String,
}

/// Verify one envelope end-to-end. Returns the (action, payload) pair on
/// success; a friendly FixError otherwise. Nothing is applied here.
pub fn verify(envelope_json: &str) -> Result<(String, Value), FixError> {
    // 1. Parse the envelope itself. Anything malformed is INVALID_FORMAT.
    let env: FixEnvelope = serde_json::from_str(envelope_json).map_err(|_| FixError::InvalidFormat)?;

    // 2. Signature check FIRST — before expiry/version so unsigned input
    //    cannot even probe which check would have failed (oracle resistance).
    let expected = sign_payload(&env.payload, FIX_CODE_KEY.as_bytes());
    if !ct_eq(&expected.to_lowercase(), &env.sig.to_lowercase()) {
        return Err(FixError::InvalidSignature);
    }

    // 3. Expiry + version live inside the payload's metadata block.
    //    The CLI embeds them there so the signature covers them too.
    let meta: PatchMetadata = serde_json::from_value(env.payload.clone())
        .map_err(|_| FixError::InvalidFormat)?;

    let now = chrono::Utc::now();
    let exp = chrono::DateTime::parse_from_rfc3339(&meta.expires_at)
        .map_err(|_| FixError::InvalidFormat)?
        .with_timezone(&chrono::Utc);
    if exp < now {
        return Err(FixError::Expired);
    }

    // Version compatibility: patch must target this binary's major.minor.
    // Patch-level drift (1.0.0 vs 1.0.3) is tolerated; cross-minor is not.
    let app_major_minor: Vec<&str> = env!("CARGO_PKG_VERSION").split('.').take(2).collect();
    let patch_major_minor: Vec<&str> = meta.version.split('.').take(2).collect();
    if app_major_minor != patch_major_minor {
        return Err(FixError::VersionMismatch);
    }

    Ok((env.action, env.payload))
}

/// Apply a verified patch. Every operation is whitelisted; anything else is
/// rejected. No shell, no network, no arbitrary filesystem access exists in
/// this function's reachable code — the compiler proves the surface.
pub fn apply(action: &str, payload: &Value) -> Result<&'static str, FixError> {
    match action {
        // ── Whitelisted op 1: update one SystemSetting row ────────────────
        // The desktop sidecar owns the SQLite file, so this engine writes
        // the setting directly (same table the backend's fix route uses).
        "update_setting" => {
            let key = payload
                .get("key")
                .and_then(|v| v.as_str())
                .ok_or(FixError::UnknownOperation)?;
            let value = payload
                .get("value")
                .ok_or(FixError::UnknownOperation)?;
            if !ALLOWED_SETTING_KEYS.contains(&key) {
                return Err(FixError::UnknownOperation);
            }
            let value_str = match value {
                Value::String(s) => s.clone(),
                other => other.to_string(),
            };
            crate::update_system_setting(key, &value_str)
                .map_err(|_| FixError::NotApplicable)?;
            Ok("Fix applied. Please restart the application.")
        }

        // ── Whitelisted op 2: delete crash logs ───────────────────────────
        // Useful after support resolves an issue; bounded to the crashes dir.
        "delete_crash_logs" => {
            let dir = crate::crash_handler::crashes_dir();
            if let Ok(entries) = std::fs::read_dir(dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    // Only files matching our crash filename pattern are
                    // eligible — nothing else in the directory is touched.
                    if path.is_file() {
                        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
                        if name.starts_with("crash_") && name.ends_with(".json") {
                            let _ = std::fs::remove_file(path);
                        }
                    }
                }
            }
            Ok("Crash logs cleared.")
        }

        // ── Whitelisted op 3: reset configuration to defaults ─────────────
        // Deletes only config-ish files in the data dir. pharmacy.db and
        // secret.key are NEVER in this list (invariant: user data untouched).
        "reset_config" => {
            if let Ok(data_dir) = crate::data_dir_for_fixes() {
                for name in [".env", "window-state.json"] {
                    let p = data_dir.join(name);
                    if p.is_file() {
                        let _ = std::fs::remove_file(p);
                    }
                }
            }
            Ok("Configuration reset. Please restart the application.")
        }

        // Everything else is refused by construction.
        _ => Err(FixError::UnknownOperation),
    }
}

// ── Tauri commands exposed to the recovery window ────────────────────────────
// The recovery UI (recovery:// origin) calls these via the global IPC bridge.
// They return friendly codes only; real causes go to the sidecar log.

pub fn recovery_get_diagnostics() -> String {
    // Fixed-shape diagnostic: version, OS family, latest crash file name.
    // The crash-file CONTENTS are never returned to the UI (they contain the
    // sanitized error line; support reads the file itself after the user
    // attaches it to an email).
    let latest = std::fs::read_dir(crate::crash_handler::crashes_dir())
        .ok()
        .and_then(|entries| {
            entries
                .flatten()
                .filter(|e| e.path().is_file())
                .map(|e| e.file_name().to_string_lossy().to_string())
                .max()
        })
        .unwrap_or_else(|| "none".to_string());

    serde_json::json!({
        "appVersion": env!("CARGO_PKG_VERSION"),
        "os": std::env::consts::OS,
        "lastCrashFile": latest,
    })
    .to_string()
}

pub fn recovery_apply_fix(admin_key: String, fix_code: String) -> Result<String, String> {
    // Admin key gate: support issues the key with the fix code, so a stolen
    // code alone is not enough (defense against shoulder-surfing/paste of a
    // code by a third party). Compare in constant time, then wipe nothing —
    // the value is only ever in this call frame.
    let expected = include_str!("fix_admin_key.txt");
    if !ct_eq(admin_key.trim(), expected.trim()) {
        log_fix_event("recovery_apply_fix", "INVALID_ADMIN_KEY");
        return Err("INVALID_ADMIN_KEY".to_string());
    }

    match verify(&fix_code) {
        Ok((action, payload)) => match apply(&action, &payload) {
            Ok(message) => {
                log_fix_event("recovery_apply_fix", "APPLIED");
                Ok(message.to_string())
            }
            Err(e) => {
                log_fix_event("recovery_apply_fix", e.as_code());
                Err(e.as_code().to_string())
            }
        },
        Err(e) => {
            log_fix_event("recovery_apply_fix", e.as_code());
            Err(e.as_code().to_string())
        }
    }
}

pub fn recovery_reset_config(admin_key: String) -> Result<String, String> {
    let expected = include_str!("fix_admin_key.txt");
    if !ct_eq(admin_key.trim(), expected.trim()) {
        log_fix_event("recovery_reset_config", "INVALID_ADMIN_KEY");
        return Err("INVALID_ADMIN_KEY".to_string());
    }
    match apply("reset_config", &Value::Null) {
        Ok(message) => {
            log_fix_event("recovery_reset_config", "APPLIED");
            Ok(message.to_string())
        }
        Err(e) => {
            log_fix_event("recovery_reset_config", e.as_code());
            Err(e.as_code().to_string())
        }
    }
}

/// Append a one-line audit trail to the sidecar log. Contains only the
/// outcome code — never the fix code, the key, or the payload.
fn log_fix_event(operation: &str, outcome: &str) {
    // Best-effort: logging must never crash the recovery path.
    if let Ok(data_dir) = crate::data_dir_for_fixes() {
        let log_path = data_dir.join("pharmacy_sidecar.log");
        let line = format!(
            "[fix-engine] {operation}: {outcome} at {}",
            chrono::Utc::now().to_rfc3339()
        );
        use std::io::Write;
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(log_path) {
            let _ = writeln!(f, "{line}");
        }
    }
}
