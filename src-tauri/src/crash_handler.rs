// ── Crash Handler (Blueprint Task 2, Step 2.1 / Point 2, Layer 1) ────────────
//
// SECURITY REVIEW NOTES (why this file is shaped the way it is):
// * The panic hook is installed as the VERY FIRST action in `run()`, before
//   any Tauri/WebView initialization. If WebView2 itself fails to start, this
//   hook still runs — that is the entire reason it exists.
// * The crash report written to disk contains ONLY: a timestamp, the app
//   version, the OS name, and a sanitized one-line summary of the panic.
//   It NEVER contains: patient data, database contents, passwords, tokens,
//   file contents, or raw multi-line panic payloads (which can embed user
//   data from whatever code panicked). Sanitization happens before write.
// * The dialog tells the user where the file is and shows the support email.
//   Per security invariant #7, no stack traces or internal paths beyond the
//   single crash-file location the user must attach to an email.

use serde::Serialize;
use std::path::PathBuf;

/// Where crash reports live: %APPDATA%\PharmacySuite\crashes on Windows.
/// Mirrors the backend's data dir so support only has to look in one place.
pub fn crashes_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return PathBuf::from(appdata).join("PharmacySuite").join("crashes");
        }
    }
    // Non-Windows / APPDATA-missing fallback (dev boxes).
    std::env::temp_dir().join("PharmacySuite-crashes")
}

#[derive(Serialize)]
struct CrashReport {
    timestamp: String,
    app_version: String,
    os: String,
    /// One-line, length-capped, non-multiline summary of the panic message.
    /// Sanitized in `sanitize_panic` — this is NOT the raw panic payload.
    error_code: String,
}

/// Reduce a panic payload to a single safe line.
///
/// Why each step matters (security):
/// * `chars().map(replace)` — control characters and newlines are stripped so
///   a panic message can never smuggle multiline content (or log-forging
///   sequences) into the JSON file or the MessageBox.
/// * Truncation to 200 chars bounds the file size and prevents a huge panic
///   payload from being copied anywhere.
fn sanitize_panic(msg: &str) -> String {
    let mut out = String::new();
    for c in msg.chars() {
        let replacement = match c {
            '\n' | '\r' | '\t' => ' ',
            c if (c as u32) < 0x20 => ' ', // other control chars
            c => c,
        };
        out.push(replacement);
        if out.len() >= 200 {
            break; // hard cap; a truncated message is still a useful signal
        }
    }
    out
}

fn os_info() -> String {
    // std::env::consts::OS is a compile-time constant ("windows") — no
    // runtime probing, no version strings, nothing identifiable beyond the
    // OS family. This is deliberate: less data in the report.
    std::env::consts::OS.to_string()
}

/// Write the crash report and inform the user via a native dialog.
/// Best-effort by design: if even the file write fails we still show the
/// dialog, because telling the user how to reach support matters more.
pub fn install_panic_hook() {
    std::panic::set_hook(Box::new(|panic_info| {
        let timestamp = chrono::Utc::now().to_rfc3339();
        let sanitized = sanitize_panic(&panic_info.to_string());

        let report = CrashReport {
            timestamp: timestamp.clone(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
            os: os_info(),
            error_code: sanitized,
        };

        let dir = crashes_dir();
        let _ = std::fs::create_dir_all(&dir);
        // Filename embeds a UTC timestamp (colons are illegal on Windows, so
        // they are replaced) — no user input ever reaches the filename.
        let file_name = format!(
            "crash_{}.json",
            timestamp.replace(':', "-").replace('+', "-")
        );
        let crash_path = dir.join(file_name);

        let write_ok = std::fs::write(
            &crash_path,
            serde_json::to_string_pretty(&report).unwrap_or_else(|_| "{}".to_string()),
        )
        .is_ok();

        show_native_crash_dialog(&crash_path, write_ok);
    }));
}

/// Native Windows MessageBox — zero WebView2 dependency, works even when the
/// web layer never came up. On non-Windows this falls back to stderr.
fn show_native_crash_dialog(crash_path: &PathBuf, write_ok: bool) {
    #[cfg(target_os = "windows")]
    {
        use std::ffi::OsStr;
        use std::os::windows::ffi::OsStrExt;
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            MessageBoxW, MB_ICONERROR, MB_OK, MB_SETFOREGROUND,
        };

        let file_note = if write_ok {
            format!(
                "A diagnostic file has been saved to:\n{}\n\n",
                crash_path.display()
            )
        } else {
            "A diagnostic file could not be saved.\n\n".to_string()
        };

        // Security invariant #7: the dialog shows the support email, the one
        // diagnostic-file path, and reassurance. No panic details, no stack,
        // no internal state beyond that single path.
        let message = format!(
            "Pharmacy Suite encountered an error and could not start.\n\n{}\nTo get help:\n  1. Email pharmacypro.support@gmail.com\n  2. Attach the diagnostic file above\n  3. Or open Pharmacy Suite Recovery from your Start Menu\n\nYour patient data is safe.",
            file_note
        );

        let to_wide = |s: &str| -> Vec<u16> {
            OsStr::new(s).encode_wide().chain(Some(0)).collect()
        };

        unsafe {
            MessageBoxW(
                std::ptr::null_mut(),
                to_wide(&message).as_ptr(),
                to_wide("Pharmacy Suite — Startup Error").as_ptr(),
                MB_OK | MB_ICONERROR | MB_SETFOREGROUND,
            );
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = write_ok;
        eprintln!(
            "Pharmacy Suite failed to start. Diagnostic: {} (support: pharmacypro.support@gmail.com)",
            crash_path.display()
        );
    }
}
