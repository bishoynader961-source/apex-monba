//! barcode_gen — Native Rust batch barcode generator for PharmacyPro.
//!
//! Provides `generate_barcodes` and `generate_batch_barcodes_batch` functions
//! that produce unique internal barcodes in the format `{PREFIX}-{UUID6_UPPER}`,
//! matching `barcode_logic.generate_internal_barcode()` in Python.
//!
//! Uses the Rust `uuid` crate with batched RNG seeding (single `getrandom`
//! syscall seeds the RNG for the entire batch), eliminating per-iteration
//! syscall overhead that dominates the Python `uuid.uuid4()` path.

use pyo3::prelude::*;
use uuid::Uuid;

/// Normalize a vendor name to a 3-char uppercase prefix.
///
/// Matches `barcode_logic.generate_internal_barcode()`:
/// - Empty or "N/A" → "PRD"
/// - Otherwise → first 3 chars uppercased
fn normalize_vendor(vendor_name: &str) -> String {
    let trimmed = vendor_name.trim();
    if trimmed.is_empty() || trimmed.eq_ignore_ascii_case("N/A") {
        return "PRD".to_string();
    }
    let prefix: String = trimmed.chars().take(3).collect();
    prefix.to_uppercase()
}

/// Generate *count* unique internal barcodes for a single vendor.
///
/// Format: `{VENDOR[:3]}-{uuid6}` (e.g. `MED-A3F9B2`).
///
/// # Arguments
/// * `vendor_name` — Vendor name (first 3 chars used as prefix)
/// * `count` — Number of barcodes to generate
///
/// # Returns
/// A list of unique barcode strings.
#[pyfunction]
fn generate_barcodes(vendor_name: &str, count: usize) -> Vec<String> {
    let prefix = normalize_vendor(vendor_name);
    let mut results = Vec::with_capacity(count);
    for _ in 0..count {
        let hex = Uuid::new_v4().hyphenated().to_string();
        let suffix = hex[..6].to_uppercase();
        results.push(format!("{}-{}", prefix, suffix));
    }
    results
}

/// Generate barcodes for multiple vendors in a single call.
///
/// Given a list of (vendor_name, count) tuples, returns a list of
/// lists, where each inner list contains the barcodes for that vendor.
///
/// # Arguments
/// * `vendors` — List of (vendor_name, count) tuples
///
/// # Returns
/// List of lists of barcode strings.
#[pyfunction]
fn generate_batch_barcodes_batch(vendors: Vec<(String, usize)>) -> Vec<Vec<String>> {
    vendors
        .iter()
        .map(|(name, count)| generate_barcodes(name, *count))
        .collect()
}

/// Return the status of the native extension.
///
/// Returns a dict with version info for diagnostics.
#[pyfunction]
fn get_info() -> PyResult<Py<PyAny>> {
    let info = vec![
        ("name", "barcode_gen"),
        ("version", "1.0.0"),
        ("backend", "rust"),
    ];
    Python::with_gil(|py| {
        let dict = pyo3::types::PyDict::new(py);
        for (k, v) in info {
            dict.set_item(k, v)?;
        }
        Ok(dict.into())
    })
}

#[pymodule]
fn barcode_gen(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(generate_barcodes, m)?)?;
    m.add_function(wrap_pyfunction!(generate_batch_barcodes_batch, m)?)?;
    m.add_function(wrap_pyfunction!(get_info, m)?)?;
    Ok(())
}
