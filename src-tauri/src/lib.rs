// ── Recovery Layer 1: crash handler must be the FIRST module initialized ────
// The panic hook inside is installed before any Tauri/WebView code runs so
// that even a WebView2 startup failure produces a diagnostic + user dialog.
pub mod crash_handler;
// Fix Engine (Step 2.4): verification of signed support fix codes.
pub mod fix_engine;

use tauri::{Manager, WindowEvent};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::net::UdpSocket;
use tokio::time::{sleep, Duration};
use base64::{Engine as _, engine::general_purpose};
use std::fs;
use std::path::PathBuf;
use tracing::{error, info, warn};

static BROADCASTING: AtomicBool = AtomicBool::new(false);
static SIDECAR_NODE: std::sync::Mutex<Option<tauri_plugin_shell::process::CommandChild>> = std::sync::Mutex::new(None);
static SIDECAR_BACKEND: std::sync::Mutex<Option<tauri_plugin_shell::process::CommandChild>> = std::sync::Mutex::new(None);

// ── Windows Job Object: OS-guaranteed sidecar kill ─────────────────────────
// Every sidecar is assigned to a Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
// The job handles are intentionally NEVER closed by us: when the app process
// exits — cleanly, crashed, or force-killed from Task Manager — the kernel
// closes them and terminates the sidecars. This survives every exit path,
// unlike the manual kill_sidecars() which only runs on a graceful close.
#[cfg(windows)]
static JOB_HANDLES: std::sync::Mutex<Vec<isize>> = std::sync::Mutex::new(Vec::new());

#[cfg(windows)]
fn assign_child_to_job(pid: u32) {
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE};

    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            warn!("job object creation failed for pid {pid}; falling back to manual kill only");
            return;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const core::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        ) == 0
        {
            warn!("SetInformationJobObject failed for pid {pid}");
            return;
        }
        let proc = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
        if proc.is_null() {
            warn!("OpenProcess({pid}) failed; child not added to job object");
            return;
        }
        if AssignProcessToJobObject(job, proc) == 0 {
            warn!("AssignProcessToJobObject({pid}) failed");
        } else {
            info!("pid {pid} assigned to kill-on-close job object");
        }
        // Keep the handle open for the lifetime of the app. Closing the LAST
        // handle is what triggers the kill, so these are deliberately leaked
        // into a static; the OS reclaims them on process exit.
        if let Ok(mut guard) = JOB_HANDLES.lock() {
            guard.push(job as isize);
        }
    }
}

#[cfg(not(windows))]
fn assign_child_to_job(_pid: u32) {}

/// Data dir for the fix engine (no AppHandle available).
/// Must match get_data_dir(): %APPDATA%\PharmacySuite first.
pub fn data_dir_for_fixes() -> Result<std::path::PathBuf, String> {
    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            let dir = std::path::PathBuf::from(appdata).join("PharmacySuite");
            if std::fs::create_dir_all(&dir).is_ok() {
                return Ok(dir);
            }
        }
    }
    std::env::current_dir().map_err(|e| format!("no data dir available: {e}"))
}

fn kill_sidecars() {
    if let Ok(mut guard) = SIDECAR_NODE.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            info!("Killed Node.js sidecar process");
        }
    }
    if let Ok(mut guard) = SIDECAR_BACKEND.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            info!("Killed FastAPI backend sidecar process");
        }
    }
}

/// Write one SystemSetting row directly to the SQLite DB.
/// Called only by the fix engine's whitelisted update_setting op.
/// Creates the row if missing (fix codes may need to add defaults).
pub fn update_system_setting(key: &str, value: &str) -> Result<(), String> {
    let data_dir = data_dir_for_fixes()?;
    let db_path = data_dir.join("pharmacy.db");
    if !db_path.exists() {
        return Err("database not found".to_string());
    }
    use sqlite::State;
    let conn = sqlite::open(&db_path).map_err(|e| e.to_string())?;
    // Key and value are bound parameters, never string-interpolated.
    let mut stmt = conn
        .prepare("INSERT INTO system_settings (key, value) VALUES (?1, ?2) ON CONFLICT(key) DO UPDATE SET value = excluded.value")
        .map_err(|e| e.to_string())?;
    // sqlite crate: Bindable is implemented for (index, value) tuples.
    stmt.bind((1, key)).map_err(|e| e.to_string())?;
    stmt.bind((2, value.as_bytes())).map_err(|e| e.to_string())?;
    stmt.next().map_err(|e| e.to_string())?;
    Ok(())
}

// Recovery-window commands (Step 2.3/2.4). Declared HERE (not in the
// fix_engine module) because tauri-build generates the allow-* permissions
// for commands found in this file; logic itself lives in fix_engine.rs.
#[tauri::command]
fn recovery_get_diagnostics() -> String {
    fix_engine::recovery_get_diagnostics()
}

#[tauri::command]
fn recovery_apply_fix(admin_key: String, fix_code: String) -> Result<String, String> {
    fix_engine::recovery_apply_fix(admin_key, fix_code)
}

#[tauri::command]
fn recovery_reset_config(admin_key: String) -> Result<String, String> {
    fix_engine::recovery_reset_config(admin_key)
}

#[tauri::command]
async fn start_udp_broadcast() -> Result<(), String> {
    if BROADCASTING.load(Ordering::SeqCst) {
        return Ok(());
    }
    BROADCASTING.store(true, Ordering::SeqCst);
    
    tauri::async_runtime::spawn(async move {
        let socket = match UdpSocket::bind("0.0.0.0:0").await {
            Ok(s) => s,
            Err(_) => return,
        };
        let _ = socket.set_broadcast(true);
        let target: std::net::SocketAddr = "255.255.255.255:54321".parse().unwrap();
        
        let local_ip = match std::net::UdpSocket::bind("0.0.0.0:0") {
            Ok(s) => {
                if s.connect("8.8.8.8:80").is_ok() {
                    s.local_addr().unwrap().ip().to_string()
                } else {
                    "127.0.0.1".to_string()
                }
            }
            Err(_) => "127.0.0.1".to_string(),
        };
        
        let msg = format!("{{\"instance_id\": \"pharmacy_main_device\", \"ip\": \"{}\"}}", local_ip);
        
        while BROADCASTING.load(Ordering::SeqCst) {
            let _ = socket.send_to(msg.as_bytes(), target).await;
            sleep(Duration::from_secs(2)).await;
        }
    });

    Ok(())
}

#[tauri::command]
fn stop_udp_broadcast() {
    BROADCASTING.store(false, Ordering::SeqCst);
}

#[tauri::command]
async fn scan_udp_broadcast() -> Result<String, String> {
    let socket = UdpSocket::bind("0.0.0.0:54321").await.map_err(|e| e.to_string())?;
    let mut buf = [0u8; 1024];
    
    let res = tokio::time::timeout(Duration::from_secs(5), socket.recv_from(&mut buf)).await;
    match res {
        Ok(Ok((amt, _src))) => {
            let msg = String::from_utf8_lossy(&buf[..amt]).into_owned();
            Ok(msg)
        }
        Ok(Err(e)) => Err(e.to_string()),
        Err(_) => Err("Timeout waiting for server broadcast".to_string()),
    }
}

#[tauri::command]
fn setup_main_device(app: tauri::AppHandle) -> Result<(), String> {
    let log_path = get_log_path(&app);
    log_to_file(&log_path, "[setup] setup_main_device called");

    let data_dir = get_data_dir(&app).map_err(|e| {
        let msg = format!("[setup] get_data_dir failed: {e}");
        log_to_file(&log_path, &msg);
        msg
    })?;

    log_to_file(&log_path, &format!("[setup] data_dir = {}", data_dir.display()));

    std::fs::create_dir_all(&data_dir).map_err(|e| {
        let msg = format!("[setup] create_dir_all({}) failed: {e}", data_dir.display());
        log_to_file(&log_path, &msg);
        msg
    })?;

    let config_path = data_dir.join(".env");
    let env_content = "DB_HOST=127.0.0.1\nDB_PORT=5432\nDB_USER=postgres\nDB_PASS=localpass\n";
    std::fs::write(&config_path, env_content).map_err(|e| {
        let msg = format!("[setup] write {} failed: {e}", config_path.display());
        log_to_file(&log_path, &msg);
        msg
    })?;

    log_to_file(&log_path, &format!("[setup] SUCCESS: .env written to {}", config_path.display()));
    Ok(())
}

#[tauri::command]
fn open_label_window(app: tauri::AppHandle) -> Result<(), String> {
    use tauri::WebviewUrl;
    use tauri::WebviewWindowBuilder;

    info!("open_label_window: called");
    if let Some(win) = app.get_webview_window("label-engine-preview") {
        info!("open_label_window: window already exists, focusing");
        let _ = win.set_focus();
        return Ok(());
    }

    // Use app config or env for base URL instead of hardcoded localhost
    let base_url = std::env::var("TAURI_FRONTEND_URL").unwrap_or_else(|_| "http://127.0.0.1:3000".to_string());
    let url = format!("{}/dashboard/label-engine-preview", base_url);
    info!("open_label_window: creating window with URL = {}", url);

    let parsed_url = url.parse().map_err(|e| {
        error!("open_label_window: failed to parse URL '{}': {}", url, e);
        format!("Invalid URL: {}", e)
    })?;

    let window = WebviewWindowBuilder::new(
        &app,
        "label-engine-preview",
        WebviewUrl::External(parsed_url),
    )
    .title("Label Preview - Pharmacy Suite")
    .inner_size(1200.0, 800.0)
    .resizable(true)
    .build()
    .map_err(|e| {
        error!("open_label_window: WebviewWindowBuilder::build failed: {}", e);
        e.to_string()
    })?;

    info!("open_label_window: window created successfully");
    Ok(())
}

#[tauri::command]
fn close_label_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("label-engine-preview") {
        win.close().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn print_label(image_data: String, _canvas_width: f64, _canvas_height: f64) -> Result<(), String> {
    info!("print_label: received image_data length={}", image_data.len());
    // Decode base64 image data
    let base64_data = image_data.strip_prefix("data:image/png;base64,").unwrap_or(&image_data);
    let image_bytes = general_purpose::STANDARD.decode(base64_data)
        .map_err(|e| {
            error!("print_label: base64 decode failed: {}", e);
            format!("Failed to decode base64 image: {}", e)
        })?;
    info!("print_label: decoded {} bytes", image_bytes.len());

    // Save to temporary file
    let temp_dir = std::env::temp_dir();
    let file_name = format!("label_print_{}.png", uuid::Uuid::new_v4());
    let file_path = temp_dir.join(file_name);
    info!("print_label: temp file path = {}", file_path.display());

    fs::write(&file_path, image_bytes)
        .map_err(|e| {
            error!("print_label: failed to write temp file {}: {}", file_path.display(), e);
            format!("Failed to write temp file: {}", e)
        })?;
    info!("print_label: temp file written successfully");

    // Open system print dialog
    #[cfg(target_os = "windows")]
    {
        use std::ffi::OsStr;
        use std::os::windows::ffi::OsStrExt;
        use std::ptr;
        use windows_sys::Win32::UI::Shell::ShellExecuteW;
        use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOW;

        let file_path_wide: Vec<u16> = OsStr::new(file_path.to_string_lossy().as_ref()).encode_wide().chain(Some(0)).collect();
        let verb_wide: Vec<u16> = OsStr::new("print").encode_wide().chain(Some(0)).collect();

        info!("print_label: calling ShellExecuteW with verb=print, path={}", file_path.display());
        unsafe {
            let result = ShellExecuteW(
                ptr::null_mut(),
                verb_wide.as_ptr(),
                file_path_wide.as_ptr(),
                ptr::null(),
                ptr::null(),
                SW_SHOW,
            );
            // ShellExecuteW returns HINSTANCE (pointer), but values <= 32 indicate errors
            let result_code = result as isize;
            if result_code <= 32 {
                error!("print_label: ShellExecuteW failed with error code {}", result_code);
                return Err(format!("Failed to open print dialog: ShellExecuteW returned error code {}", result_code));
            }
            info!("print_label: ShellExecuteW succeeded (result_code={})", result_code);
        }
    }
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        info!("print_label: calling lpr on macOS");
        Command::new("lpr")
            .arg(&file_path)
            .spawn()
            .map_err(|e| {
                error!("print_label: lpr spawn failed: {}", e);
                format!("Failed to print: {}", e)
            })?;
        info!("print_label: lpr spawned successfully");
    }
    #[cfg(target_os = "linux")]
    {
        use std::process::Command;
        info!("print_label: calling lpr on Linux");
        Command::new("lpr")
            .arg(&file_path)
            .spawn()
            .map_err(|e| {
                error!("print_label: lpr spawn failed: {}", e);
                format!("Failed to print: {}", e)
            })?;
        info!("print_label: lpr spawned successfully");
    }

    // Clean up temp file after a delay
    let path_clone = file_path.clone();
    tauri::async_runtime::spawn(async move {
        sleep(Duration::from_secs(30)).await;
        let _ = fs::remove_file(path_clone);
    });

    info!("print_label: completed successfully");
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Step 2.1: install the panic hook before ANY other initialization.
    // Everything after this line can panic into the crash-report path.
    crash_handler::install_panic_hook();

    // Step 2.3: register the recovery:// protocol before building the app.
    let builder = register_recovery_protocol(tauri::Builder::default());
    builder
        .invoke_handler(tauri::generate_handler![open_label_window, close_label_window, print_label, start_udp_broadcast, stop_udp_broadcast, scan_udp_broadcast, setup_main_device, recovery_get_diagnostics, recovery_apply_fix, recovery_reset_config])
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
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
                    // Kill sidecar processes when main window closes.
                    // CloseRequested handles the graceful path (user clicks X);
                    // Destroyed covers every other way the window can die.
                    let app_handle = app.handle().clone();
                    window.on_window_event(move |event| {
                        if matches!(event, WindowEvent::CloseRequested { .. }) {
                            info!("Main window closing - killing sidecar processes");
                            kill_sidecars();
                        }
                        if matches!(event, WindowEvent::Destroyed) {
                            let _ = &app_handle; // job objects guarantee the kill; this is belt-and-braces
                            info!("Main window destroyed - killing sidecar processes");
                            kill_sidecars();
                        }
                    });
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

/// Resolve the data directory: %APPDATA%\PharmacySuite → app_data_dir → exe dir → current dir
///
/// Must match the backend's ``get_app_data_dir`` (config.py): the MSI backend
/// keeps ``pharmacy.db`` + ``secret.key`` in ``%APPDATA%\PharmacySuite`` on
/// Windows, so terminal-mode reads and the sidecar CWD must point there.
fn get_data_dir(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            let dir = std::path::PathBuf::from(appdata).join("PharmacySuite");
            if std::fs::create_dir_all(&dir).is_ok() {
                return Ok(dir);
            }
            eprintln!("[setup] %APPDATA%\\PharmacySuite not writable, falling back");
        }
    }
    if let Ok(dir) = app.path().app_data_dir() {
        return Ok(dir);
    }
    eprintln!("[setup] app_data_dir failed, trying exe dir");
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            return Ok(parent.to_path_buf());
        }
    }
    eprintln!("[setup] exe dir failed, trying current dir");
    std::env::current_dir().map_err(|e| format!("all path resolutions failed: {e}"))
}

// ── Sidecar orchestration ────────────────────────────────────────────────────
async fn read_terminal_mode(app: &tauri::AppHandle) -> Result<String, String> {
    let data_dir = get_data_dir(app)?;
    let db_path = data_dir.join("pharmacy.db");
    
    if !db_path.exists() {
        // No database yet - default to main server for first-time setup
        return Ok("main".to_string());
    }
    
    // Use sqlite to read the terminal_mode setting
    use sqlite::State;
    let conn = sqlite::open(&db_path).map_err(|e| e.to_string())?;
    let mut stmt = conn.prepare("SELECT value FROM system_settings WHERE key = 'terminal_mode'").map_err(|e| e.to_string())?;
    
    let mode = match stmt.next() {
        Ok(State::Row) => {
            let val: String = stmt.read(0).unwrap_or_default();
            val
        }
        Ok(State::Done) => "main".to_string(), // Default to main if not set
        Err(e) => {
            log_to_file(&get_log_path(app), &format!("[terminal_mode] DB query error: {e}"));
            "main".to_string()
        }
    };
    
    Ok(mode)
}

async fn spawn_servers(app: &tauri::AppHandle) {
    use tauri::Manager;
    use tauri_plugin_shell::process::CommandEvent;
    use tauri_plugin_shell::ShellExt;

    let log_path = get_log_path(app);

    // Read terminal mode from settings (SPEC 07)
    let terminal_mode = read_terminal_mode(app).await.unwrap_or_else(|e| {
        log_to_file(&log_path, &format!("[terminal_mode] read error: {e}, defaulting to main"));
        "main".to_string()
    });
    log_to_file(&log_path, &format!("[terminal_mode] = {}", terminal_mode));

    // ── 1. Find server.js ──
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
            // Step 2.2: fail fast with an actionable log line if :3000 is taken.
            if !port_is_bindable(3000) {
                log_to_file(&log_path, "[node] PORT CONFLICT: 127.0.0.1:3000 is already in use by another process");
            }
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
                        Ok((mut rx, child)) => {
                            log_to_file(&log_path, &format!("[node] sidecar spawned OK (pid {})", child.pid()));
                            assign_child_to_job(child.pid());
                            if let Ok(mut guard) = SIDECAR_NODE.lock() {
                                *guard = Some(child);
                            }
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
                                            if let Ok(mut guard) = SIDECAR_NODE.lock() {
                                                *guard = None;
                                            }
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

    // ── 2. FastAPI backend sidecar on :8000 (only on Main Server) ──
    if terminal_mode == "main" {
        match get_data_dir(app) {
            Ok(data_dir) => {
                let _ = std::fs::create_dir_all(&data_dir);
                log_to_file(&log_path, &format!("[backend] data_dir = {}", data_dir.display()));
                // Step 2.2: fail fast with an actionable log line if :8000 is taken.
                if !port_is_bindable(8000) {
                    log_to_file(&log_path, "[backend] PORT CONFLICT: 127.0.0.1:8000 is already in use (another Pharmacy Suite instance or unrelated service?)");
                }
                match app.shell().sidecar("backend") {
                    Ok(cmd) => match cmd
                        .args(["--host", "127.0.0.1", "--port", "8000"])
                        .current_dir(&data_dir)
                        .spawn()
                    {
                        Ok((mut rx, child)) => {
                            log_to_file(&log_path, &format!("[backend] sidecar spawned OK (pid {})", child.pid()));
                            log_to_file(&log_path, "[backend] listening on 127.0.0.1:8000 (loopback only; other machines cannot connect)");
                            assign_child_to_job(child.pid());
                            if let Ok(mut guard) = SIDECAR_BACKEND.lock() {
                                *guard = Some(child);
                            }
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
                                            if let Ok(mut guard) = SIDECAR_BACKEND.lock() {
                                                *guard = None;
                                            }
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
    } else {
        log_to_file(&log_path, "[backend] SKIPPED: running in Client Terminal mode");
    }

    // ── 3. Wait for Next.js server readiness ──
    log_to_file(&log_path, "[poll] waiting for server on :3000 ...");
    let ready = wait_for_port("127.0.0.1", 3000, 90).await;

    if let Some(window) = app.get_webview_window("main") {
        if ready {
            log_to_file(&log_path, "[poll] server ready - navigating");
            let _ = window.eval("window.location.href = 'http://127.0.0.1:3000'");
        } else {
            log_to_file(&log_path, "[poll] server failed to start within 90 s");
            let _ = window.eval(SHOW_ERROR);
        }
    }

    // ── 4. Step 2.2: HTTP-level health verification of both sidecars ──
    // TCP readiness is not service readiness; verify actual HTTP responses.
    // Only fixed codes reach the recovery UI (invariant #7); detail goes to log.
    match poll_health(3000, "/api/health", 30).await {
        Ok(()) => log_to_file(&log_path, "[poll] frontend /api/health OK"),
        Err(reason) => {
            log_to_file(&log_path, &format!("[poll] FRONTEND HEALTH FAILED: {reason}"));
            show_recovery_window(app, "FRONTEND_UNHEALTHY");
        }
    }
    match poll_health(8000, "/api/v1/health", 30).await {
        Ok(()) => log_to_file(&log_path, "[poll] backend /api/v1/health OK"),
        Err(reason) => {
            log_to_file(&log_path, &format!("[poll] BACKEND HEALTH FAILED: {reason}"));
            show_recovery_window(app, "BACKEND_UNHEALTHY");
        }
    }
}

// ─ Step 2.3: recovery window assets, compiled into the binary ────
// include_str! guarantees these exist even if the resource layout breaks,
// matching the recovery window's zero-dependency guarantee.
const RECOVERY_HTML: &str = include_str!("../recovery.html");
const RECOVERY_JS: &str = include_str!("../recovery-app.js");

/// Serve the recovery window from a dedicated recovery:// scheme so the
/// files never depend on the Next.js server, bundler output, or disk state.
/// CSP-safe: recovery-app.js is served same-origin, satisfying script-src 'self'.
fn register_recovery_protocol(builder: tauri::Builder<tauri::Wry>) -> tauri::Builder<tauri::Wry> {
    // register_asynchronous_uri_scheme_protocol returns Self; hand it back.
    builder.register_asynchronous_uri_scheme_protocol("recovery", move |_ctx, request, responder| {
        let uri = request.uri().to_string();
        // Strip the scheme and serve only the two known files.
        let path = uri.trim_start_matches("recovery://").trim_start_matches('/');
        let (body, content_type) = match path {
            "recovery-app.js" => (RECOVERY_JS, "application/javascript"),
            _ => (RECOVERY_HTML, "text/html"),
        };
        responder.respond(
            http::Response::builder()
                .status(200)
                .header("Content-Type", content_type)
                .header("Access-Control-Allow-Origin", "recovery://localhost")
                .header("Cache-Control", "no-store")
                .body(body.as_bytes().to_vec())
                .unwrap(),
        );
    })
}

// ─ Step 2.2: Sidecar health polling (HTTP-level, not just TCP) ────
// A TCP connect proves a socket is listening; only an HTTP 200 proves the
// service is actually serving. Both matter for recovery decisions, so the
// recovery path triggers on health failure, not merely on port failure.
//
// Security: poll_health and show_recovery_window exchange ONLY fixed error
// codes (invariant #7). Detailed causes (port conflict, spawn error text)
// go to the sidecar log file for support — never into the recovery UI.

/// Minimal HTTP GET check over a raw tokio TcpStream.
/// Deliberately dependency-free: a full HTTP client is unnecessary for
/// asking one endpoint whether it returns 200.
async fn poll_health(port: u16, path: &str, timeout_secs: u64) -> Result<(), String> {
    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(timeout_secs);
    let addr = format!("127.0.0.1:{port}");
    let request = format!(
        "GET {path} HTTP/1.1
Host: 127.0.0.1:{port}
Connection: close

"
    );

    loop {
        let attempt = async {
            let mut stream = tokio::net::TcpStream::connect(&addr)
                .await
                .map_err(|e| format!("connect failed: {e}"))?;
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            stream.write_all(request.as_bytes())
                .await
                .map_err(|e| format!("write failed: {e}"))?;
            let mut buf = [0u8; 64];
            let n = stream.read(&mut buf).await.unwrap_or(0);
            let head = String::from_utf8_lossy(&buf[..n]).to_string();
            // Status line looks like "HTTP/1.1 200 OK" — check the code only.
            if head.starts_with("HTTP/") && head.contains(" 200") {
                Ok(())
            } else {
                Err(head.lines().next().unwrap_or("empty response").to_string())
            }
        };

        match tokio::time::timeout(Duration::from_secs(2), attempt).await {
            Ok(Ok(())) => return Ok(()),
            Ok(Err(reason)) => return Err(format!("HTTP check failed: {reason}")),
            Err(_) => { /* connect/read timed out — retry until budget exhausted */ }
        }

        if start.elapsed() >= timeout {
            return Err("health check timed out".to_string());
        }
        sleep(Duration::from_millis(500)).await;
    }
}

/// Pre-spawn port ownership check: proves the port is bindable BEFORE the
/// sidecar tries, so a port conflict produces an actionable log line instead
/// of a mysterious sidecar exit. The probe listener is dropped immediately,
/// releasing the port for the real sidecar.
fn port_is_bindable(port: u16) -> bool {
    std::net::TcpListener::bind(("127.0.0.1", port)).is_ok()
}

/// Open the bundled recovery window (recovery.html — Step 2.3).
/// Idempotent: a second failure focuses nothing, just logs. The window reads
/// its diagnostics via Tauri IPC; no error detail travels through URLs.
fn show_recovery_window(app: &tauri::AppHandle, code: &str) {
    use tauri::{WebviewUrl, WebviewWindowBuilder};
    if app.get_webview_window("recovery").is_some() {
        return;
    }
    log_to_file(
        &get_log_path(app),
        &format!("[recovery] opening recovery window, code={code}"),
    );
    let built = WebviewWindowBuilder::new(
        app,
        "recovery",
        // Serve the compiled-in recovery UI from the dedicated scheme.
        WebviewUrl::External("http://recovery.localhost/recovery.html".parse().unwrap()),
    )
    .title("Pharmacy Suite Recovery")
    .inner_size(620.0, 540.0)
    .resizable(true)
    .build();
    if let Err(e) = built {
        log_to_file(&get_log_path(app), &format!("[recovery] window build failed: {e}"));
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
