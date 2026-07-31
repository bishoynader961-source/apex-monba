use sha2::{Digest, Sha256};
use std::process::Command;

/// Gather low-level system identifiers and compute a SHA-256 HWID.
///
/// Sources (Windows):
///   - `wmic cpu get ProcessorId`   (CPU serial)
///   - `wmic baseboard get SerialNumber` (motherboard serial)
///   - `wmic diskdrive get SerialNumber` (primary disk serial)
///
/// Falls back to hostname + MAC if any command fails.
pub fn generate_hwid() -> String {
    let mut sources: Vec<String> = Vec::new();

    // CPU ProcessorId
    if let Some(val) = wmic_query("cpu", "ProcessorId") {
        sources.push(format!("cpu={}", val));
    }

    // Motherboard SerialNumber
    if let Some(val) = wmic_query("baseboard", "SerialNumber") {
        sources.push(format!("mb={}", val));
    }

    // Disk SerialNumber
    if let Some(val) = wmic_query("diskdrive", "SerialNumber") {
        sources.push(format!("disk={}", val));
    }

    // Fallback: hostname + MAC
    if sources.is_empty() {
        if let Some(name) = hostname() {
            sources.push(format!("host={}", name));
        }
        if let Some(mac) = mac_address() {
            sources.push(format!("mac={}", mac));
        }
    }

    let combined = sources.join("|");
    let mut hasher = Sha256::new();
    hasher.update(combined.as_bytes());
    hex::encode(hasher.finalize())
}

/// Run a WMIC query and return the first non-empty trimmed line.
fn wmic_query(class: &str, field: &str) -> Option<String> {
    let output = Command::new("wmic")
        .args([class, "get", field])
        .output()
        .ok()?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    for line in stdout.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() && trimmed != field {
            return Some(trimmed.to_string());
        }
    }
    None
}

fn hostname() -> Option<String> {
    Command::new("hostname")
        .output()
        .ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
}

fn mac_address() -> Option<String> {
    let output = Command::new("getmac")
        .args(["/fo", "csv", "/nh"])
        .output()
        .ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    for line in stdout.lines() {
        // CSV format: "AA-BB-CC-DD-EE-FF","..."
        if let Some(mac) = line.split(',').next() {
            let mac = mac.trim_matches('"').replace('-', ":");
            if mac.len() == 17 {
                return Some(mac);
            }
        }
    }
    None
}
