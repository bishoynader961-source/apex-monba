// ── Fix Engine (Blueprint Task 2, Step 2.4 — Layer 4, security-critical) ─────
//
// PURPOSE: verify and apply "fix codes" — signed data patches sent by
// PharmacySuite support. A fix code is NOT executable code; it is a small
// JSON envelope whose HMAC-SHA256 signature can only be produced by the
// holder of the signing secret (PharmacySuite support tooling).
//
// KEY MANAGEMENT (audit M4, 2026-10-03):
//   * This binary embeds NO signing key. The HMAC is verified by the FastAPI
//     sidecar at POST /api/v1/admin/fix/verify (FIX_CODE_SECRET and
//     FIX_ADMIN_KEY live only in the backend .env). The previous
//     include_str!("fix_key.txt") / include_str!("fix_admin_key.txt") shipped
//     both secrets inside the exe, where any customer could extract them.
//   * Verification requires the local backend: on any network failure or
//     timeout (5 s) this engine FAILS CLOSED — nothing is applied.
//   * Rotation = change FIX_CODE_SECRET / FIX_ADMIN_KEY in the backend .env
//     and restart; no desktop release is needed.
//
// SECURITY MODEL (why each check exists):
//   1. Signature (server-side constant-time compare): nobody without the
//      secret can mint or alter a patch — this is the anti-forgery core.
//   2. Canonical JSON: the signature covers an exact byte sequence. Python's
//      json.dumps default formatting (", " / ": " separators, sorted keys,
//      ensure_ascii) is the canonical form shared by the backend verifier
//      and the CLI. Any other byte layout would fail the HMAC even with the
//      right key. (`sign_payload` below mirrors it byte-for-byte, and UDP
//      discovery reuses it for its own signatures.)
//   3. Expiry + version match happen server-side, over the signed payload.
//   4. Whitelist: even a validly-signed code can only perform operations
//      this engine explicitly implements; the setting whitelist is re-checked
//      locally before anything is applied. There is no eval, no shell, no
//      arbitrary file I/O, no patient-data access — by construction, not by
//      policy.
//   5. Errors are fixed friendly codes (invariant #7); details go to the
//      sidecar log for support, never to the UI.

use serde::Deserialize;
use serde_json::Value;

/// Backend endpoint that verifies the admin key + fix code (audit M4).
const FIX_VERIFY_URL: &str = "http://127.0.0.1:8000/api/v1/admin/fix/verify";
/// Hard timeout for the verification round-trip; timeout = deny (fail closed).
const FIX_VERIFY_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(5);

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
    /// The backend rejected the admin key / signature / expiry / version.
    /// Deliberately one code for all of them: the response must not become an
    /// oracle for which check failed (mirrors the old verify-local order).
    InvalidSignature,
    /// The backend could not be reached, timed out, or answered nonsense.
    /// Fail closed — the caller must not apply anything.
    VerificationUnavailable,
    UnknownOperation,
    NotApplicable,
}

impl FixError {
    pub fn as_code(self) -> &'static str {
        match self {
            FixError::InvalidFormat => "INVALID_FORMAT",
            FixError::InvalidSignature => "INVALID_SIGNATURE",
            FixError::VerificationUnavailable => "VERIFY_UNAVAILABLE",
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
pub(crate) fn sign_payload(payload: &Value, key: &[u8]) -> String {
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
pub(crate) fn ct_eq(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.bytes().zip(b.bytes()) {
        diff |= x ^ y;
    }
    diff == 0
}

/// The subset of the backend's verify response this engine consumes.
#[derive(Debug, Deserialize)]
struct RemoteVerify {
    valid: bool,
    action: Option<String>,
    payload: Option<Value>,
    #[serde(default)]
    ops: Vec<String>,
}

// ── HTTP transport (audit M4) ───────────────────────────────────────────────
// The sidecar is plain HTTP on loopback. `std` sockets keep the dependency
// tree unchanged (no new crate, no Cargo.lock churn); every failure path maps
// to VerificationUnavailable so callers deny rather than guess.

/// Decode a chunked transfer body (uvicorn normally sends Content-Length, but
/// a proxy/middleware may chunk — an undecodable body must never be trusted).
fn dechunk(body: &str) -> Option<String> {
    let bytes = body.as_bytes();
    let mut pos = 0usize;
    let mut out: Vec<u8> = Vec::new();
    loop {
        let line_end = bytes[pos..]
            .windows(2)
            .position(|w| w == b"\r\n")
            .map(|p| p + pos)?;
        let size_str = std::str::from_utf8(&bytes[pos..line_end]).ok()?;
        let size = usize::from_str_radix(size_str.split(';').next()?.trim(), 16).ok()?;
        pos = line_end + 2;
        if size == 0 {
            return String::from_utf8(out).ok();
        }
        if pos + size > bytes.len() {
            return None;
        }
        out.extend_from_slice(&bytes[pos..pos + size]);
        pos += size;
        if bytes[pos..].starts_with(b"\r\n") {
            pos += 2;
        }
    }
}

/// Split a raw HTTP/1.1 response into (status, body).
fn split_http_response(raw: &str) -> Result<(u16, String), FixError> {
    let (head, body) = raw.split_once("\r\n\r\n").ok_or(FixError::VerificationUnavailable)?;
    let mut lines = head.split("\r\n");
    let status_line = lines.next().ok_or(FixError::VerificationUnavailable)?;
    let status: u16 = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|code| code.parse().ok())
        .ok_or(FixError::VerificationUnavailable)?;
    let chunked = lines.any(|line| {
        let lower = line.to_ascii_lowercase();
        lower.starts_with("transfer-encoding:") && lower.contains("chunked")
    });
    let body = if chunked {
        dechunk(body).ok_or(FixError::VerificationUnavailable)?
    } else {
        body.to_string()
    };
    Ok((status, body))
}

/// POST a JSON body to the loopback verifier and return the response body.
/// Any transport failure, timeout, or non-200 status is VerificationUnavailable.
fn http_post_json(url: &str, body: &Value) -> Result<String, FixError> {
    use std::io::{Read, Write};
    use std::net::{SocketAddr, TcpStream};

    let rest = url
        .strip_prefix("http://")
        .ok_or(FixError::VerificationUnavailable)?;
    let (authority, path) = match rest.find('/') {
        Some(idx) => (&rest[..idx], &rest[idx..]),
        None => (rest, "/"),
    };
    let addr: SocketAddr = authority.parse().map_err(|_| FixError::VerificationUnavailable)?;

    let payload = body.to_string();
    let request = format!(
        "POST {path} HTTP/1.1\r\nHost: {authority}\r\nContent-Type: application/json\r\nContent-Length: {len}\r\nConnection: close\r\n\r\n{payload}",
        len = payload.len(),
    );

    let mut stream = TcpStream::connect_timeout(&addr, FIX_VERIFY_TIMEOUT)
        .map_err(|_| FixError::VerificationUnavailable)?;
    stream
        .set_read_timeout(Some(FIX_VERIFY_TIMEOUT))
        .map_err(|_| FixError::VerificationUnavailable)?;
    stream
        .set_write_timeout(Some(FIX_VERIFY_TIMEOUT))
        .map_err(|_| FixError::VerificationUnavailable)?;
    stream
        .write_all(request.as_bytes())
        .map_err(|_| FixError::VerificationUnavailable)?;
    let mut raw = String::new();
    stream
        .read_to_string(&mut raw)
        .map_err(|_| FixError::VerificationUnavailable)?;

    let (status, response_body) = split_http_response(&raw)?;
    if status != 200 {
        return Err(FixError::VerificationUnavailable);
    }
    Ok(response_body)
}

/// Ask the backend to verify an admin key together with either a raw fix code
/// or an admin-key-only ``requested_action`` (``reset_config``).
fn verify_with_backend_at(
    url: &str,
    admin_key: &str,
    fix_code: Option<&str>,
    requested_action: Option<&str>,
) -> Result<(String, Option<Value>), FixError> {
    if let Some(code) = fix_code {
        // Cheap local format gate (no secrets involved): malformed input never
        // reaches the network, preserving the old INVALID_FORMAT behaviour.
        let _: FixEnvelope = serde_json::from_str(code).map_err(|_| FixError::InvalidFormat)?;
    }
    let body = serde_json::json!({
        "admin_key": admin_key.trim(),
        "fix_code": fix_code,
        "client_version": env!("CARGO_PKG_VERSION"),
        "requested_action": requested_action,
    });
    let raw = http_post_json(url, &body)?;
    let parsed: RemoteVerify =
        serde_json::from_str(&raw).map_err(|_| FixError::VerificationUnavailable)?;
    if !parsed.valid {
        return Err(FixError::InvalidSignature);
    }
    let action = parsed.action.ok_or(FixError::VerificationUnavailable)?;
    if parsed.ops.is_empty() {
        // The server authorized nothing; applying a payload anyway would be
        // trusting an incomplete response.
        return Err(FixError::VerificationUnavailable);
    }
    Ok((action, parsed.payload))
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
    // Audit M4: the admin key and the fix-code HMAC are verified by the
    // backend over loopback. A network failure, timeout, or rejection means
    // nothing is applied (fail closed).
    let (action, payload) =
        match verify_with_backend_at(FIX_VERIFY_URL, &admin_key, Some(&fix_code), None) {
            Ok(result) => result,
            Err(e) => {
                log_fix_event("recovery_apply_fix", e.as_code());
                return Err(e.as_code().to_string());
            }
        };
    let payload = match payload {
        Some(payload) => payload,
        None => {
            log_fix_event("recovery_apply_fix", FixError::VerificationUnavailable.as_code());
            return Err(FixError::VerificationUnavailable.as_code().to_string());
        }
    };
    match apply(&action, &payload) {
        Ok(message) => {
            log_fix_event("recovery_apply_fix", "APPLIED");
            Ok(message.to_string())
        }
        Err(e) => {
            log_fix_event("recovery_apply_fix", e.as_code());
            Err(e.as_code().to_string())
        }
    }
}

pub fn recovery_reset_config(admin_key: String) -> Result<String, String> {
    // Admin-key-only operation: no fix envelope exists for a config reset, so
    // the backend authorizes the action for a valid admin key.
    match verify_with_backend_at(FIX_VERIFY_URL, &admin_key, None, Some("reset_config")) {
        Ok((action, _)) if action == "reset_config" => {}
        Ok(_) => {
            log_fix_event("recovery_reset_config", FixError::UnknownOperation.as_code());
            return Err(FixError::UnknownOperation.as_code().to_string());
        }
        Err(e) => {
            log_fix_event("recovery_reset_config", e.as_code());
            return Err(e.as_code().to_string());
        }
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    /// Bind an ephemeral port and answer exactly one request with `response`.
    fn spawn_mock_server(response: String) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock verifier");
        let addr = listener.local_addr().expect("mock addr");
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let _ = stream.set_read_timeout(Some(std::time::Duration::from_secs(5)));
                let mut buf = [0u8; 4096];
                let _ = stream.read(&mut buf);
                let _ = stream.write_all(response.as_bytes());
            }
        });
        format!("http://{addr}/api/v1/admin/fix/verify")
    }

    fn http_response(status: &str, body: &str) -> String {
        format!(
            "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {len}\r\nConnection: close\r\n\r\n{body}",
            len = body.len()
        )
    }

    #[test]
    fn network_failure_fails_closed() {
        // Port 1 is reserved and never listening: connect fails fast. The
        // engine must deny — never fall back to trusting the code.
        let err = verify_with_backend_at(
            "http://127.0.0.1:1/api/v1/admin/fix/verify",
            "admin-key",
            None,
            Some("reset_config"),
        )
        .expect_err("unreachable backend must deny");
        assert_eq!(err.as_code(), "VERIFY_UNAVAILABLE");
    }

    #[test]
    fn valid_response_returns_verified_action_and_payload() {
        let url = spawn_mock_server(http_response(
            "200 OK",
            r#"{"valid": true, "action": "update_setting", "payload": {"key": "terminal_mode", "value": "client"}, "ops": ["terminal_mode"]}"#,
        ));
        let (action, payload) = verify_with_backend_at(&url, "admin-key", None, Some("reset_config"))
            .expect("valid response accepted");
        assert_eq!(action, "update_setting");
        assert_eq!(payload.expect("payload")["key"], "terminal_mode");
    }

    #[test]
    fn rejected_code_maps_to_invalid_signature() {
        let url = spawn_mock_server(http_response(
            "200 OK",
            r#"{"valid": false, "action": null, "payload": null, "ops": []}"#,
        ));
        let err = verify_with_backend_at(&url, "admin-key", None, Some("reset_config"))
            .expect_err("rejection must deny");
        assert_eq!(err.as_code(), "INVALID_SIGNATURE");
    }

    #[test]
    fn non_200_status_fails_closed() {
        let url = spawn_mock_server(http_response("500 Internal Server Error", "boom"));
        let err = verify_with_backend_at(&url, "admin-key", None, Some("reset_config"))
            .expect_err("non-200 must deny");
        assert_eq!(err.as_code(), "VERIFY_UNAVAILABLE");
    }

    #[test]
    fn malformed_fix_code_rejected_before_any_network_io() {
        // Port 1 is never listening; if the format gate did not run first this
        // would return VERIFY_UNAVAILABLE instead of INVALID_FORMAT.
        let err = verify_with_backend_at(
            "http://127.0.0.1:1/api/v1/admin/fix/verify",
            "admin-key",
            Some("not-json"),
            None,
        )
        .expect_err("malformed code must deny");
        assert_eq!(err.as_code(), "INVALID_FORMAT");
    }

    #[test]
    fn chunked_response_bodies_are_decoded() {
        assert_eq!(
            dechunk("4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n").as_deref(),
            Some("Wikipedia")
        );
        assert_eq!(dechunk("zz\r\n").as_deref(), None);
    }

    #[test]
    fn local_setting_whitelist_is_still_enforced() {
        let payload = serde_json::json!({"key": "evil_backdoor", "value": "1"});
        let err = apply("update_setting", &payload).expect_err("whitelist must hold");
        assert_eq!(err.as_code(), "UNKNOWN_OPERATION");
    }
}
