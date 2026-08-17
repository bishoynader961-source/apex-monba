//! hw_client — Native Rust hardware identification for PharmacyPro.
//!
//! Provides fast, dependency-free hardware fingerprinting to replace Python's
//! subprocess-based WMIC queries.  Functions are called by:
//!     - crash_reporter.py: _get_anonymized_hwid() → tries hw_client.get_anonymized_hwid()
//!     - license_gate.py: get_device_mac() → tries hw_client.get_device_mac()
//!                      _get_device_id() → tries hw_client.get_device_id()
//!
//! All functions return the same format as their Python counterparts.
//! On any failure, callers fall back to the pure-Python implementations.

use pyo3::prelude::*;
use sha2::{Digest, Sha256};
use hex;
use std::process::Command;

/// Generate a hardware ID string (SHA-256 hash).
///
/// Matches license_gate._get_device_id(): combines MAC address, hostname,
/// and processor architecture into a SHA-256 hash.
#[pyfunction]
fn get_device_id() -> PyResult<String> {
    let mut sources: Vec<String> = Vec::new();

    if let Some(mac) = read_mac_address() {
        sources.push(format!("mac={}", mac));
    }
    if let Some(name) = hostname() {
        sources.push(format!("host={}", name));
    }
    sources.push(format!("proc={}", std::env::consts::ARCH));

    let combined = sources.join("|");
    Ok(hash_sha256(&combined))
}

/// Return an anonymized HWID hash (SHA-256, truncated to 16 hex chars).
///
/// Matches crash_reporter._get_anonymized_hwid(): tries to read the Windows
/// machine UUID via WMIC, falls back to MAC+hostname if WMIC fails.
/// The result is always truncated to 16 hex characters.
#[pyfunction]
fn get_anonymized_hwid() -> PyResult<String> {
    let hwid = gather_hwid_components();
    let combined = hwid.join("|");
    let hash = hash_sha256(&combined);
    // Truncate to 16 hex chars (matches Python [:16])
    Ok(hash.chars().take(16).collect())
}

/// Return the machine's MAC address as "AA:BB:CC:DD:EE:FF".
///
/// Matches license_gate.get_device_mac(): returns an empty string if the
/// MAC cannot be determined (Python returns None; we return "" for PyO3
/// simplicity — callers handle both).
#[pyfunction]
fn get_device_mac() -> PyResult<String> {
    match read_mac_address() {
        Some(mac) => Ok(mac),
        None => Ok(String::new()),
    }
}

// ── Internal helpers ─────────────────────────────────────────────────────

/// Gather HWID components matching crash_reporter._get_anonymized_hwid().
fn gather_hwid_components() -> Vec<String> {
    let mut sources: Vec<String> = Vec::new();

    // On Windows: try wmic csproduct get uuid (matches Python subprocess approach)
    if let Some(uuid) = wmic_query("csproduct", "uuid") {
        sources.push(format!("uuid={}", uuid));
    }

    // Always include hostname + processor
    if let Some(name) = hostname() {
        sources.push(format!("host={}", name));
    }
    sources.push(format!("proc={}", std::env::consts::ARCH));

    // Fallback: if wmic didn't produce a UUID, add MAC address
    if sources.iter().all(|s| !s.starts_with("uuid=")) {
        if let Some(mac) = read_mac_address() {
            sources.push(format!("mac={}", mac));
        }
    }

    sources
}

/// Run a WMIC query and return the first non-empty trimmed line.
/// Mirrors the Rust hwid.rs implementation.
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

/// Get the hostname via system call.
fn hostname() -> Option<String> {
    gethostname::gethostname()
        .into_string()
        .ok()
}

/// Read MAC address via system interface.
fn read_mac_address() -> Option<String> {
    // mac_address 1.x: get_mac_address() -> Result<Option<MacAddress>, MacAddressError>
    let mac = mac_address::get_mac_address().ok()??;
    Some(mac.to_string())
}

/// Compute SHA-256 hash of data, return hex string.
fn hash_sha256(input: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    hex::encode(hasher.finalize())
}

/// Python module definition.
#[pymodule]
fn hw_client(m: Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_device_id, &m)?)?;
    m.add_function(wrap_pyfunction!(get_anonymized_hwid, &m)?)?;
    m.add_function(wrap_pyfunction!(get_device_mac, &m)?)?;
    m.add("__version__", "1.0.0")?;
    Ok(())
}
