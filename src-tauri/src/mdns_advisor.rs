//! Step 1.6 (blueprint §1.4.5): mDNS advertisement of the desktop instance so
//! mobile devices on the same WiFi can discover it without typing an IP.
//!
//! Wire format contract (must stay in sync with the QR gateway, Step 1.5):
//! - `instanceId` MUST equal the QR payload's `instance_id` — it is covered by
//!   the QR HMAC. The backend derives it from the `.pharmacy_device_id` marker
//!   file next to the DB (config.py `_stable_device_id`), so this module reads
//!   the same file. SystemSetting `pharmacy_id` is the blueprint's preferred
//!   source but is not seeded anywhere today; when a `pharmacy_id` row exists
//!   it wins, otherwise the marker file is the effective identity (documented
//!   deviation).
//! - TXT records are strictly allow-listed: instanceId, version, apiVersion.
//!   No passwords, tokens, DB path, or qr_secret_key ever leaves this module.

use mdns_sd::{ServiceDaemon, ServiceInfo};
use std::sync::Mutex;
use tauri::AppHandle;

use crate::{get_data_dir, read_system_setting_value};

/// Service type + port are fixed by the blueprint (§1.4.5) and the QR payload
/// (`http://<ip>:8000`).
const SERVICE_TYPE: &str = "_pharmacysuite._tcp.local.";
const SERVICE_PORT: u16 = 8000;

/// Holds the daemon + the fullname we registered, so `stop` can unregister
/// exactly what was announced (mDNS de-registration is per-fullname).
static MDNS: Mutex<Option<(ServiceDaemon, String)>> = Mutex::new(None);

/// Read the SystemSetting `pharmacy_id` row, if any, via the shared helper.
async fn read_pharmacy_id(app: &AppHandle) -> Option<String> {
    read_system_setting_value(app, "pharmacy_id")
        .await
        .ok()
        .flatten()
        .filter(|v| !v.trim().is_empty())
}

/// Read the per-install stable device id — the marker file the backend's
/// `_stable_device_id` (config.py) writes next to the DB. Must stay byte-
/// compatible so mDNS instanceId == QR instanceId (both feed the HMAC).
fn read_marker_device_id(app: &AppHandle) -> Option<String> {
    let data_dir = get_data_dir(app).ok()?;
    let marker = data_dir.join(".pharmacy_device_id");
    let raw = std::fs::read_to_string(&marker).ok()?;
    let trimmed = raw.trim().to_string();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed)
    }
}

/// Start advertising the backend on the LAN. No-ops (with a log line) unless
/// `mobile_access_mode` is explicitly "shared" — independent/unset/cloud must
/// never announce a reachable server. Never returns a fatal error: discovery
/// is best-effort and must not take the app down.
pub async fn start_mdns_advertisement(app: &AppHandle) {
    let mode = match read_system_setting_value(app, "mobile_access_mode").await {
        Ok(v) => v.unwrap_or_default(),
        Err(e) => {
            eprintln!("[mdns] mobile_access_mode read error: {e}; not advertising");
            return;
        }
    };
    if mode != "shared" {
        eprintln!("[mdns] mobile_access_mode = '{mode}' (not shared) — skipping advertisement");
        return;
    }

    // instanceId: SystemSetting pharmacy_id preferred, marker-file device id
    // as the effective fallback (pharmacy_id is not seeded today).
    let instance_id = match read_pharmacy_id(app).await {
        Some(id) => id,
        None => match read_marker_device_id(app) {
            Some(id) => id,
            None => {
                eprintln!("[mdns] no pharmacy_id and no .pharmacy_device_id yet — skipping advertisement (backend seeds it on first run)");
                return;
            }
        },
    };

    let instance_name = format!("PharmacySuite-{instance_id}");
    // mDNS fullnames embed the instance name; keep it DNS-SD safe.
    let fullname = format!("{instance_name}.{SERVICE_TYPE}");
    let host = format!("pharmacysuite-{instance_id}.local.");

    let txt = [
        ("instanceId".to_string(), instance_id.clone()),
        ("version".to_string(), env!("CARGO_PKG_VERSION").to_string()),
        ("apiVersion".to_string(), "v1".to_string()),
    ];

    let daemon = match ServiceDaemon::new() {
        Ok(d) => d,
        Err(e) => {
            eprintln!("[mdns] daemon init failed: {e}");
            return;
        }
    };

    let props: std::collections::HashMap<String, String> = txt.iter().cloned().collect();
    let service = match ServiceInfo::new(
        SERVICE_TYPE,
        &instance_name,
        &host,
        "", // no fixed IP: mdns-sd publishes all local interfaces
        SERVICE_PORT,
        Some(props),
    ) {
        Ok(s) => s.enable_addr_auto(),
        Err(e) => {
            eprintln!("[mdns] service info build failed: {e}");
            return;
        }
    };

    match daemon.register(service) {
        Ok(_receiver) => {
            eprintln!("[mdns] advertising {fullname} on port {SERVICE_PORT} (shared mode)");
            if let Ok(mut guard) = MDNS.lock() {
                *guard = Some((daemon, fullname));
            }
        }
        Err(e) => {
            eprintln!("[mdns] register failed: {e}");
            let _ = daemon.shutdown();
        }
    }
}

/// Unregister the advertisement. Called from the same cleanup path as
/// `kill_sidecars` (WindowEvent::CloseRequested / Destroyed in lib.rs).
/// Best-effort: the OS reclaims the socket on process exit regardless, and
/// stale announcements expire from resolver caches on their own.
pub fn stop_mdns_advertisement() {
    if let Ok(mut guard) = MDNS.lock() {
        if let Some((daemon, fullname)) = guard.take() {
            match daemon.unregister(&fullname) {
                Ok(rx) => {
                    let _ = rx.recv_timeout(std::time::Duration::from_millis(500));
                }
                Err(e) => eprintln!("[mdns] unregister error: {e}"),
            }
            let _ = daemon.shutdown();
            eprintln!("[mdns] advertisement stopped ({fullname})");
        }
    }
}
