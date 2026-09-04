use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            } else {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.eval(LOADING_HTML);
                }
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    spawn_servers(&handle).await;
                });
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

// ── Loading overlay (injected into about:blank via eval) ─────────────────────
const LOADING_HTML: &str = r#"document.documentElement.innerHTML = `<html><head><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f0f23;color:#e0e0e0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;overflow:hidden}
.c{text-align:center}
.s{width:48px;height:48px;border:3px solid #1a1a3e;border-top-color:#6c63ff;border-radius:50%;animation:r 1s linear infinite;margin:0 auto 24px}
@keyframes r{to{transform:rotate(360deg)}}
h1{font-size:22px;font-weight:300;letter-spacing:.5px;margin-bottom:8px}
p{color:#666;font-size:13px}
.d{display:flex;gap:6px;justify-content:center;margin-top:20px}
.d span{width:6px;height:6px;background:#6c63ff;border-radius:50%;animation:b 1.4s ease-in-out infinite}
.d span:nth-child(2){animation-delay:.2s}
.d span:nth-child(3){animation-delay:.4s}
@keyframes b{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1.2)}}
#err{display:none;color:#ff6b6b;font-size:14px;margin-top:16px;cursor:pointer;text-decoration:underline}
</style></head><body><div class="c"><div class="s"></div><h1>Pharmacy Suite</h1><p id="st">Starting services...</p><div class="d"><span></span><span></span><span></span></div><p id="err" onclick="location.reload()">Failed to start. Click to retry.</p></div></body></html>`;"#;

const SHOW_ERROR: &str = r#"
document.getElementById('st').textContent = 'Failed to connect to server.';
document.getElementById('st').style.color = '#ff6b6b';
document.getElementById('err').style.display = 'block';
document.querySelector('.s').style.animationPlayState = 'paused';
var dots = document.querySelector('.d');
if (dots) dots.style.display = 'none';
"#;

// ── Logging ──────────────────────────────────────────────────────────────────
fn get_log_path(app: &tauri::AppHandle) -> std::path::PathBuf {
    app.path()
        .app_data_dir()
        .ok()
        .unwrap_or(std::env::temp_dir())
        .join("pharmacy_sidecar.log")
}

fn log_to_file(path: &std::path::Path, msg: &str) {
    use std::fs::OpenOptions;
    use std::io::Write;
    let _ = std::fs::create_dir_all(path.parent().unwrap_or(std::path::Path::new(".")));
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{msg}");
    }
}

// ── Sidecar orchestration ────────────────────────────────────────────────────
async fn spawn_servers(app: &tauri::AppHandle) {
    use tauri::Manager;
    use tauri_plugin_shell::process::CommandEvent;
    use tauri_plugin_shell::ShellExt;

    let log_path = get_log_path(app);

    // ── 1. Find server.js ──
    // Tauri's resource_dir() can return unexpected paths on NSIS installs.
    // Build candidates from BOTH resource_dir AND the exe's own directory.
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()));

    let resource_dir = app.path().resource_dir().ok();

    log_to_file(
        &log_path,
        &format!(
            "[path] resource_dir = {:?}",
            resource_dir.as_ref().map(|p| p.to_string_lossy().to_string())
        ),
    );
    log_to_file(
        &log_path,
        &format!("[path] exe_dir = {:?}", exe_dir.as_ref().map(|p| p.to_string_lossy().to_string())),
    );

    // exe_dir is a clean path (no UNC prefix); resource_dir has \\?\ prefix
    // that breaks sidecar args. Prefer exe_dir.
    let search_dirs: Vec<std::path::PathBuf> = [
        exe_dir.as_ref().map(|p| p.to_path_buf()),
        resource_dir.as_ref().map(|p| p.to_path_buf()),
    ]
    .into_iter()
    .flatten()
    .collect();

    let mut found_server_js: Option<std::path::PathBuf> = None;
    for dir in &search_dirs {
        let candidates = [
            dir.join("server.js"),
            dir.join(".next").join("standalone").join("server.js"),
            dir.join("standalone").join("server.js"),
        ];
        for candidate in &candidates {
            log_to_file(&log_path, &format!("[path] checking {:?} exists={}", candidate.to_string_lossy(), candidate.exists()));
            if candidate.exists() && candidate.is_file() {
                found_server_js = Some(candidate.clone());
                break;
            }
        }
        if found_server_js.is_some() {
            break;
        }
    }

    match found_server_js {
        Some(server_js) => {
            let js = server_js.to_string_lossy().to_string();
            let standalone_dir = server_js
                .parent()
                .map(|p| p.to_path_buf());
            log_to_file(&log_path, &format!("[node] using server.js = {js}"));
            log_to_file(&log_path, &format!("[node] standalone_dir = {standalone_dir:?}"));
            match app.shell().sidecar("node") {
                Ok(cmd) => {
                    let mut cmd = cmd
                        .args([&js])
                        .env("PORT", "3000")
                        .env("HOSTNAME", "127.0.0.1");
                    if let Some(ref sd) = standalone_dir {
                        cmd = cmd.current_dir(sd);
                    }
                    match cmd.spawn() {
                        Ok((mut rx, _child)) => {
                            log_to_file(&log_path, "[node] sidecar spawned OK");
                            let lp = log_path.clone();
                            tauri::async_runtime::spawn(async move {
                                while let Some(ev) = rx.recv().await {
                                    match ev {
                                        CommandEvent::Stdout(l) => {
                                            log_to_file(&lp, &format!("[node] {}", String::from_utf8_lossy(&l)));
                                        }
                                        CommandEvent::Stderr(l) => {
                                            log_to_file(&lp, &format!("[node:err] {}", String::from_utf8_lossy(&l)));
                                        }
                                        CommandEvent::Terminated(s) => {
                                            log_to_file(&lp, &format!("[node] exited: {s:?}"));
                                        }
                                        _ => {}
                                    }
                                }
                            });
                        }
                        Err(e) => {
                            log_to_file(&log_path, &format!("[node] spawn error: {e}"));
                        }
                    }
                }
                Err(e) => {
                    log_to_file(&log_path, &format!("[node] resolve error: {e}"));
                }
            }
        }
        None => {
            log_to_file(&log_path, "[node] server.js NOT FOUND in any search dir");
        }
    }

    // ── 2. FastAPI backend sidecar on :8000 ──
    match app.path().app_data_dir() {
        Ok(data_dir) => {
            let _ = std::fs::create_dir_all(&data_dir);
            match app.shell().sidecar("backend") {
                Ok(cmd) => match cmd
                    .args(["--host", "127.0.0.1", "--port", "8000"])
                    .current_dir(&data_dir)
                    .spawn()
                {
                    Ok((mut rx, _child)) => {
                        log_to_file(&log_path, "[backend] sidecar spawned OK");
                        let lp = log_path.clone();
                        tauri::async_runtime::spawn(async move {
                            while let Some(ev) = rx.recv().await {
                                match ev {
                                    CommandEvent::Stdout(l) => {
                                        log_to_file(&lp, &format!("[backend] {}", String::from_utf8_lossy(&l)));
                                    }
                                    CommandEvent::Stderr(l) => {
                                        log_to_file(&lp, &format!("[backend:err] {}", String::from_utf8_lossy(&l)));
                                    }
                                    CommandEvent::Terminated(s) => {
                                        log_to_file(&lp, &format!("[backend] exited: {s:?}"));
                                    }
                                    _ => {}
                                }
                            }
                        });
                    }
                    Err(e) => {
                        log_to_file(&log_path, &format!("[backend] spawn error: {e}"));
                    }
                },
                Err(e) => {
                    log_to_file(&log_path, &format!("[backend] resolve error: {e}"));
                }
            }
        }
        Err(e) => {
            log_to_file(&log_path, &format!("app_data_dir error: {e}"));
        }
    }

    // ── 3. Wait for Next.js server readiness ──
    log_to_file(&log_path, "[poll] waiting for server on :3000 ...");
    let ready = wait_for_port("127.0.0.1", 3000, 90).await;

    if let Some(window) = app.get_webview_window("main") {
        if ready {
            log_to_file(&log_path, "[poll] server ready — navigating");
            let _ = window.eval("window.location.href = 'http://127.0.0.1:3000'");
        } else {
            log_to_file(&log_path, "[poll] server failed to start within 90 s");
            let _ = window.eval(SHOW_ERROR);
        }
    }
}

// ── TCP port readiness poll ──────────────────────────────────────────────────
async fn wait_for_port(host: &str, port: u16, timeout_secs: u64) -> bool {
    use tokio::net::TcpStream;
    use tokio::time::{sleep, Duration};

    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(timeout_secs);
    let addr = format!("{host}:{port}");

    loop {
        match TcpStream::connect(&addr).await {
            Ok(_) => return true,
            Err(_) => {
                if start.elapsed() >= timeout {
                    return false;
                }
                sleep(Duration::from_millis(500)).await;
            }
        }
    }
}
