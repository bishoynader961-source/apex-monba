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
        // In release we bundle the Next.js standalone server and launch it as a
        // sidecar so the BFF (httpOnly-cookie auth) and frontend run locally.
        let handle = app.handle().clone();
        tauri::async_runtime::spawn(async move {
          spawn_servers(&handle);
        });
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

/// Launch the bundled Next.js standalone server (frontend + BFF on :3000) and,
/// best-effort, the FastAPI backend on :8000 (requires Python + installed app).
fn spawn_servers(app: &tauri::AppHandle) {
  use tauri::Manager;
  use tauri_plugin_shell::ShellExt;

  let resource_dir = match app.path().resource_dir() {
    Ok(d) => d,
    Err(e) => {
      eprintln!("resource_dir error: {e}");
      return;
    }
  };

  // Next standalone `server.js` may be copied to the resource root or under a
  // `.next/standalone` subpath depending on the Tauri bundling layout.
  let candidates = [
    resource_dir.join("server.js"),
    resource_dir.join(".next").join("standalone").join("server.js"),
    resource_dir.join("standalone").join("server.js"),
  ];
  if let Some(server_js) = candidates.into_iter().find(|p| p.exists()) {
    let server_js = server_js.to_string_lossy().to_string();
    if let Ok(sidecar) = app.shell().sidecar("node") {
      let _ = sidecar
        .args([server_js])
        .env("PORT", "3000")
        .env("HOST", "127.0.0.1")
        .spawn();
    } else {
      eprintln!("failed to resolve node sidecar");
    }
  } else {
    eprintln!("Next standalone server.js not found in bundled resources");
  }

  // FastAPI backend — bundled PyInstaller sidecar: backend-x86_64-pc-windows-msvc.exe
  // (produced by backend_fastapi/build_backend.spec). Run from the app data dir so the
  // SQLite DB + pepper/device-id files land in a stable, writable location instead of the
  // sidecar's temp extraction folder. Tauri kills sidecar children when the app exits,
  // giving a clean shutdown.
  match app.path().app_data_dir() {
    Ok(app_data) => {
      let _ = std::fs::create_dir_all(&app_data);
      if let Ok(sidecar) = app.shell().sidecar("backend") {
        let _ = sidecar
          .args(["--host", "127.0.0.1", "--port", "8000"])
          .current_dir(&app_data)
          .spawn();
      } else {
        eprintln!("failed to resolve backend sidecar");
      }
    }
    Err(e) => eprintln!("app_data_dir error: {e}"),
  }
}
