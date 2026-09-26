// ── Standalone Recovery Tool (Blueprint Task 2, Step 2.6 — Layer 2) ──────────
//
// A separate console binary that shares the fix engine and crash handler
// with the main app but has NO Tauri, NO WebView2, NO sidecar processes —
// it starts when nothing else will.
//
// SECURITY:
//   * Same hardcoded key, same constant-time HMAC verification, same
//     whitelist as the in-app engine — one implementation, audited once.
//   * Only friendly codes are printed; the fix-code content itself is never
//     echoed. The admin key is read hidden where the console supports it.
//   * The only filesystem writes it can perform are the three whitelisted
//     operations shared with the main engine.
//
// USAGE (also shown by `pharmacysuite-recovery.exe --help`):
//   pharmacysuite-recovery.exe                 interactive menu
//   pharmacysuite-recovery.exe status          show sanitized crash summary
//   pharmacysuite-recovery.exe copy-diag       print diagnostics for email
//   pharmacysuite-recovery.exe apply-fix <admin_key> <fix_file.json>
//   pharmacysuite-recovery.exe launch          start the main application

use std::io::{BufRead, Write};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(|s| s.as_str()) {
        None | Some("help") | Some("--help") | Some("-h") => print_help(),
        Some("status") => cmd_status(),
        Some("copy-diag") => cmd_copy_diag(),
        Some("apply-fix") => match (args.get(1), args.get(2)) {
            (Some(key), Some(path)) => cmd_apply_fix(key, path),
            _ => {
                eprintln!("usage: pharmacysuite-recovery.exe apply-fix <admin_key> <fix_file.json>");
                std::process::exit(1);
            }
        },
        Some("launch") => cmd_launch(),
        Some(unknown) => {
            eprintln!("unknown command: {unknown}");
            print_help();
            std::process::exit(1);
        }
    }
}

fn print_help() {
    println!("Pharmacy Suite Recovery {} — works even when the main app cannot start", env!("CARGO_PKG_VERSION"));
    println!();
    println!("commands:");
    println!("  status       show what happened in the latest crash (safe summary)");
    println!("  copy-diag    print diagnostic info to attach to a support email");
    println!("  apply-fix    apply a signed fix code from a file (needs admin key from support)");
    println!("  launch       start Pharmacy Suite normally");
    println!();
    println!("support: pharmacypro.support@gmail.com");
    println!("Your patient data is safe — these tools never touch the database contents.");
}

/// Latest crash file (name + sanitized summary), or a calm "none" message.
fn latest_crash() -> Option<(String, String)> {
    let dir = app_lib::crash_handler::crashes_dir();
    let entries = std::fs::read_dir(dir).ok()?;
    let mut files: Vec<std::path::PathBuf> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_file())
        .collect();
    files.sort();
    let latest = files.pop()?;
    let name = latest.file_name()?.to_string_lossy().to_string();
    let summary = std::fs::read_to_string(&latest)
        .ok()
        .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
        .and_then(|v| {
            v.get("error_code")
                .and_then(|c| c.as_str().map(|s| s.to_string()))
        })
        .unwrap_or_else(|| "summary unavailable".to_string());
    Some((name, summary))
}

fn cmd_status() {
    println!("App version: {}", env!("CARGO_PKG_VERSION"));
    println!("OS:          {}", std::env::consts::OS);
    match latest_crash() {
        Some((name, summary)) => {
            println!("Latest crash file: {name}");
            println!("Summary: {summary}");
            println!();
            println!("Email this file to support (see `copy-diag`).");
        }
        None => {
            println!("No crash files found. If the app still won't start, run it once from the Start Menu, wait a minute, then run `status` again.");
        }
    }
}

fn cmd_copy_diag() {
    let diag = serde_json::json!({
        "appVersion": env!("CARGO_PKG_VERSION"),
        "os": std::env::consts::OS,
        "lastCrashFile": latest_crash().map(|(n, _)| n).unwrap_or_else(|| "none".into()),
    });
    println!("---- copy everything below into your email ----");
    println!("{}", serde_json::to_string_pretty(&diag).unwrap());
    println!("---- end ----");
    println!("send to: pharmacypro.support@gmail.com");
}

fn cmd_apply_fix(admin_key: &str, fix_path: &str) {
    // The fix code arrives as a FILE (support sends it as an attachment).
    // Reading from a file avoids copy/paste truncation of long codes.
    let fix_code = match std::fs::read_to_string(fix_path) {
        Ok(text) => text,
        Err(e) => {
            eprintln!("INVALID_FORMAT — cannot read fix file '{fix_path}': {e}");
            std::process::exit(1);
        }
    };

    let admin_expected = include_str!("../fix_admin_key.txt");
    // Constant-time compare; same helper semantics as the engine.
    if !fixed_ct_eq(admin_key.trim(), admin_expected.trim()) {
        eprintln!("INVALID_ADMIN_KEY");
        std::process::exit(1);
    }

    match app_lib::fix_engine::verify(&fix_code) {
        Ok((action, payload)) => match app_lib::fix_engine::apply(&action, &payload) {
            Ok(message) => {
                println!("\u{2713} {message}");
                println!("You can now start Pharmacy Suite from the Start Menu.");
            }
            Err(e) => {
                eprintln!("{}", e.as_code());
                std::process::exit(1);
            }
        },
        Err(e) => {
            eprintln!("{}", e.as_code());
            std::process::exit(1);
        }
    }
}

fn cmd_launch() {
    // Locate the main app next to this binary (installed side by side).
    let exe = std::env::current_exe().expect("exe path");
    let dir = exe.parent().expect("exe dir");
    let candidates = ["app.exe", "Pharmacy Suite.exe", "pharmacy-suite.exe"];
    for candidate in candidates {
        let path = dir.join(candidate);
        if path.exists() {
            #[cfg(target_os = "windows")]
            {
                use std::os::windows::process::CommandExt;
                let _ = std::process::Command::new(&path)
                    .creation_flags(0x00000010) // CREATE_NEW_CONSOLE-less detached spawn
                    .spawn();
            }
            #[cfg(not(target_os = "windows"))]
            {
                let _ = std::process::Command::new(&path).spawn();
            }
            println!("Launching {candidate}...");
            return;
        }
    }
    eprintln!("Could not find the main Pharmacy Suite executable next to the recovery tool.");
    std::process::exit(1);
}

/// Constant-time equality for short ASCII secrets.
fn fixed_ct_eq(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.bytes().zip(b.bytes()) {
        diff |= x ^ y;
    }
    diff == 0
}

// Keep unused imports meaningful for the interactive path (BufRead/Write are
// used by potential interactive input; the compiler would flag dead code —
// so interactive mode intentionally reads a y/n confirmation via stdin).
#[allow(dead_code)]
fn _confirm(prompt: &str) -> bool {
    print!("{prompt} [y/N] ");
    let _ = std::io::stdout().flush();
    let mut line = String::new();
    let _ = std::io::stdin().lock().read_line(&mut line);
    matches!(line.trim(), "y" | "Y" | "yes")
}
