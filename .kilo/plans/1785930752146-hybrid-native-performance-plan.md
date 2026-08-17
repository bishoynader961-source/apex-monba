# Hybrid Native Performance Plan — PharmacyPro

> **Status:** Planning — Implementation-Ready
> **Scope:** Apply hybrid language constraints (rapidfuzz + Rust/PyO3) to CPU-intensive operations, with pure-Python graceful fallback for all build environments.
> **Current date:** 2026-08-05
> **Target Python:** 3.12–3.14
> **Plan file:** `.kilo/plans/1785930752146-hybrid-native-performance-plan.md`

---

## 1. Context & Constraints

### 1.1. Project Overview
PharmacyPro is a desktop Tkinter/CustomTkinter application for pharmacy inventory management with serialized unit-level tracking. The codebase lives in `archive/` and uses:
- **AsyncUI** thread pool (`async_ui.py`) for non-blocking DB operations
- **SQLite WAL-mode** connections (`SqliteWALConnection` in `ui_pos_retail.py:136`, `ui_inventory_management.py:53`)
- **Rust/PyO3 extensions** already integrated: `rust_crypto` (Fernet encryption), `hw_client` (hardware ID) — both built via `maturin` and bundled as `.pyd` in PyInstaller builds via `build_exe.py:199`
- **Graceful fallback pattern** already established: `try: import module; except ImportError: fallback` (see `crypto_utils.py:177-208`, `license_gate.py:90-116`, `ui_pos_retail.py:50-57`)

### 1.2. Hybrid Language Constraints (from user)

| Constraint | Requirement |
|------------|-------------|
| **Architectural Evaluation** | Identify CPU-intensive operations (fuzzy searches, batch barcode processing) that bottleneck the Python GIL-bound loop |
| **Native Performance Strategy** | Use pre-compiled libraries (rapidfuzz) first; if custom native logic is required, use Rust via PyO3. **No C or C++ extensions (ctypes/cffi).** |
| **Graceful Fallback** | All native calls must have a pure-Python `try/except ImportError` fallback so the app runs in any build environment |

### 1.3. Technology Versions (as of 2026-08-05)

| Technology | Version | Source |
|------------|---------|--------|
| Python | 3.14.3 | system; project venv uses 3.12.7 |
| rapidfuzz | 3.14.5 (latest, released 2026-04-07) | PyPI, pre-built wheels |
| Rust (cargo) | 1.93.1 | system |
| maturin | 1.14.1 | system |
| PyO3 | 0.23 | existing Rust projects use this |
| uuid (Rust) | 1.x | to be added |

---

## 2. Architectural Evaluation — CPU-Intensive Operations

### 2.1. Category A: Python-Side Fuzzy / Multi-Criteria Search

These operations fetch data then filter in Python (bypassing SQLite's indexed lookup), creating O(n*m) bottlenecks on the main thread or in AsyncUI worker threads.

| ID | Location | Current Pattern | Complexity | Impact |
|----|----------|----------------|------------|--------|
| **A** | `ui_clinical_workflow.py:175-188` — `_search_patients()` | Fetches ALL patients via `database.get_all_patients()`, then filters with `query in str(p).lower()` | O(n × m) per keystroke | On 3,600+ patients, each keystroke triggers a full table scan + Python substring search across all fields |
| **A2** | `ui_clinical_workflow.py:625-634` — `_refresh_patient_list()` | Same full-fetch + Python substring filter | O(n × m) | Repetitive refresh on any UI state change |
| **B** | `ui_clinical_workflow.py:466-483` — `_search_drugs_fallback()` | `ndc_dictionary.ndc_lookup(query)` does exact-match only; no fuzzy fallback on miss | O(1) miss → 0 results | Misspelled drug names yield no results — silent poor UX |
| **B2** | `ndc_dictionary.py:173-190` — `name_lookup(drug_name)` | SQLite `LIKE` on unstructured `drug_name` text (no FTS index) | O(n) table scan | Slow on large NDC dictionaries (>100k entries) |
| **C** | `ui_enterprise_settings.py:136-175` — `_fetch_audit_logs()` | Fetches 500 audit rows, SQL `LIKE` across 6 text columns | O(n) with LIKE | Audit trail search is sluggish with verbose log entries |
| **D** | `quick_sig.py:216-231` — `get_sig_suggestions()` | SQL `LIKE` across `name`, `drug_name`, `directions`, `frequency` | O(n) table scan | Template suggestions don't handle typos or partial words |
| **E** | `bulk_import_staging.py:74-126` — `auto_map_csv_headers()` | 8-pass string matching per column: exact → normalized → substring, iterating all aliases | O(cols × fields × aliases × alias_len) | 50-column import × 11 fields × 5 aliases ≈ 2,750 string ops per import |

**Native strategy:** rapidfuzz `process.extract()` / `process.cdist()` with appropriate scorers (WRatio, partial_ratio, token_set_ratio, Tfidf).

### 2.2. Category B: Batch Barcode Generation (UUID syscall bottleneck)

These loop in Python, calling `uuid.uuid4()` per iteration — each call triggers an `os.urandom()` syscall.

| ID | Location | Current Pattern | Complexity | Impact |
|----|----------|----------------|------------|--------|
| **F** | `database.py:754-785` — `receive_inventory_atomically()` | Loops `quantity` times calling `barcode_generator(vendor_name)` → `uuid.uuid4().hex[:6].upper()` | O(n) per shipment | Receiving 500 boxes = 500 `os.urandom` syscalls + Python loop overhead |
| **F2** | `ui_receive_tab.py:617` — `_print_bulk_labels()` | Loops `qty` times calling `barcode_logic.generate_internal_barcode(vendor)` | O(n) | Duplicate barcode generation for label printing |
| **F3** | `ui_receive_tab.py:647` — `_commit_shipment()` | Passes `barcode_logic.generate_internal_barcode` as callback into `receive_inventory_atomically` | O(n) | Same pattern — barcode generated inside DB transaction loop |
| **G** | `excel_handler.py:141` — `execute_import()` | Calls `barcode_logic.generate_internal_barcode(vendor)` per row in background thread | O(n) | 1,000-row Excel import = 1,000 UUID generations |
| **G3** | `migrate_data.py:49` — legacy barcode normalization | Loops over all products, calling `generate_internal_barcode()` per row | O(n) | One-time migration but slow on large DBs |

**Native strategy:** Rust extension via PyO3 that batch-generates N UUIDs using the `uuid` crate's `Uuid::new_v4()` with a single `getrandom` seed, returning a `Vec<String>` to Python in one call.

### 2.3. Operations NOT Requiring Native Acceleration (already efficient)

| ID | Location | Reason |
|----|----------|--------|
| **J** | `database.search_products()`, `database.search_all_batches()` — SQL LIKE on indexed columns | SQLite handles via B-tree index — already fast, not Python-side filtering |
| **K** | `ui_pos_retail._do_search_product()` — indexed PK/lookup query | O(1) indexed query. No improvement from rapidfuzz. |
| **L** | `TaxCalculator.calculate_totals()` — pure arithmetic | O(n) but trivially fast. No improvement from native code. |
| **H** | `label_engine/canvas_core._fit_text_to_width()` — iterative font reduction | Per-element in `draw_elements`; mitigatable with font caching, not a rapidfuzz/Rust target. Lower priority. |
| **I** | `ocr_engine.preprocess_image()` — PIL image transforms | Already async via AsyncUI; PIL is C-backed; bottleneck is OCR engine (Tesseract/EasyOCR), not preprocessing. |

---

## 3. Native Performance Strategy

### 3.1. Strategy A: rapidfuzz (Pre-Compiled C++ Library)

**Target:** All Category A bottlenecks (fuzzy/multi-criteria string search).

**Library:** `rapidfuzz` 3.14.5 — pre-built wheels for Windows x86_64, Linux x86_64, macOS. MIT licensed. No compilation step required at install time.

**Specific rapidfuzz APIs:**

| Bottleneck | rapidfuzz function | Scorer | Rationale |
|------------|-------------------|--------|-----------|
| A, A2 (patient search) | `process.extract(query, choices, limit=50, score_cutoff=60)` | `fuzz.WRatio` | Handles typos, word reordering, partial matches. Returns ranked results. |
| B (drug name fallback) | `process.extract(query, choices, limit=20, score_cutoff=70)` | `fuzz.partial_ratio` | Substring matching for partial drug names like "Amox" → "Amoxicillin" |
| B2 (NDC name_lookup) | `process.cdist(query, names)` | `fuzz.token_sort_ratio` | Batch similarity against NDC drug names |
| C (audit log search) | `process.extract(query, texts, limit=50, score_cutoff=65)` | `fuzz.Tfidf` (if available, else `fuzz.WRatio`) | TF-IDF for free-text matching on audit details |
| D (Quick-SIG suggestions) | `process.extract(query, choices, limit=10, score_cutoff=65)` | `fuzz.partial_ratio` | Template name matching with partial tokens |
| E (header auto-mapping) | `process.cdist(headers, aliases)` | `fuzz.token_set_ratio` | Set-based token matching for header aliases |

**Integration approach:** rapidfuzz acts as a **secondary ranking layer** on top of existing SQL LIKE queries. SQL LIKE provides the initial pre-filter (fast on indexed columns), rapidfuzz provides typo-tolerant ranking. This avoids loading entire tables into memory on every keystroke.

### 3.2. Strategy B: Rust Extension via PyO3 (Custom Native Logic)

**Target:** All Category B bottlenecks (batch UUID barcode generation).

**Why Rust/PyO3 (not rapidfuzz):** UUID generation is not a string-matching problem — it's a syscall-level cryptographic random number generation. The bottleneck is `os.urandom()` + Python loop overhead. A Rust extension using the `uuid` crate can batch-generate UUIDs with a single `getrandom` call and zero Python GIL contention during the loop.

**Follow existing pattern:** The project already has `archive/rust_crypto/` and `archive/hw_client/` — both Rust extensions built with `maturin` and bundled as `.pyd` via `build_exe.py:199`.

**Rust extension spec:**

`archive/barcode_gen/Cargo.toml`:
```toml
[package]
name = "barcode_gen"
version = "1.0.0"
edition = "2021"

[lib]
name = "barcode_gen"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.23", features = ["extension-module", "abi3-py38"] }
uuid = { version = "1", features = ["v4", "std"] }
```

`archive/barcode_gen/src/lib.rs`:
- `#[pyfunction] generate_barcodes(vendor_name: &str, count: usize) -> Vec<String>`
- `#[pyfunction] generate_batch_barcodes_batch(vendor_name: &str, counts: Vec<usize>) -> Vec<Vec<String>>`
- Vendor prefix normalization: `vendor_name.trim()[:3].upper()`, fallback to `"PRD"` for empty/N/A
- Format: `{prefix}-{uuid6_uppercase}` — matches `barcode_logic.generate_internal_barcode()` exactly

**Build workflow:**
```bash
# Development
maturin develop --manifest-path archive/barcode_gen/Cargo.toml
# Production
maturin build --release --manifest-path archive/barcode_gen/Cargo.toml
```

---

## 4. Graceful Fallback Architecture

### 4.1. Shared Module: `archive/native_accel.py`

New module consolidating all native acceleration with pure-Python fallbacks:

```
archive/native_accel.py
├── RapidFuzz Layer
│   ├── import rapidfuzz; from rapidfuzz import process, fuzz
│   ├── _HAS_RAPIDFUZZ flag
│   ├── fuzzy_search(query, choices, limit, cutoff) → list[(str, float, int)]
│   ├── fuzzy_match_one(query, choices, cutoff) → tuple | None
│   └── fuzzy_match_headers(headers, field_aliases) → dict[str, str]
├── Rust Barcode Layer
│   ├── import barcode_gen
│   ├── _HAS_RUST_BARCODE flag
│   └── generate_batch_barcodes(vendor_name, count) → list[str]
├── Pure-Python Fallbacks
│   ├── fuzzy_search_fallback() — uses difflib.SequenceMatcher.ratio()
│   ├── fuzzy_match_headers_fallback() — preserves existing 8-pass logic
│   └── generate_batch_barcodes_fallback() — delegates to barcode_logic.generate_internal_barcode()
└── _native_accel_loaded() → dict of status flags (for diagnostics)
```

### 4.2. Fallback Pattern (following existing codebase convention)

```python
# At module import time:
try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    log.info("rapidfuzz not available; using difflib fallback")

try:
    import barcode_gen
    _HAS_RUST_BARCODE = hasattr(barcode_gen, "generate_barcodes")
except ImportError:
    barcode_gen = None
    _HAS_RUST_BARCODE = False
    log.info("barcode_gen .pyd not available; using Python UUID fallback")
```

This matches the established pattern in:
- `crypto_utils.py:180-187` — `try: import rust_crypto; except ImportError: pass`
- `license_gate.py:100-107` — `try: import hw_client; except ImportError: pass`
- `database.py:25-30` — `try: import db; except ImportError: _db = None`
- `ui_pos_retail.py:51-57` — `try: from async_ui import AsyncUI; except ImportError: HAS_ASYNC = False`

### 4.3. Fallback Semantics

| Dependency | Native Path | Fallback Path | Performance | Functional Equivalence |
|------------|------------|---------------|-------------|----------------------|
| rapidfuzz | C++ compiled wheel | `difflib.SequenceMatcher` (stdlib) | ~10-50x slower | Same ranking semantics |
| barcode_gen | Rust PyO3 .pyd | `barcode_logic.generate_internal_barcode()` per UUID | ~3-5x slower | Same barcode format |

Both fallbacks are **functionally identical** — same return types, same barcode format (`{VND[:3]}-{uuid6}`), same fuzzy ranking results. The fallback is slower but never fails.

---

## 5. Implementation Task List

### Phase 1: Shared Native Acceleration Module (T1–T4)

| # | Task | Output File | Description |
|---|------|-------------|-------------|
| **T1** | Create `native_accel.py` with rapidfuzz import + fallback | `archive/native_accel.py` | `try: from rapidfuzz import process, fuzz; _HAS_RAPIDFUZZ = True` → `except ImportError: _HAS_RAPIDFUZZ = False`. Define `fuzzy_search()`, `fuzzy_match_one()`. Pure-Python fallback using `difflib.SequenceMatcher.ratio()`. |
| **T2** | Add Rust barcode import + fallback to `native_accel.py` | `archive/native_accel.py` | `try: import barcode_gen; _HAS_RUST_BARCODE = hasattr(barcode_gen, 'generate_barcodes')` → `except ImportError: _HAS_RUST_BARCODE = False`. Define `generate_batch_barcodes()` with `barcode_logic.generate_internal_barcode()` fallback. |
| **T3** | Implement `fuzzy_match_headers()` | `archive/native_accel.py` | Replace `bulk_import_staging.auto_map_csv_headers()` 8-pass algorithm with `rapidfuzz.process.cdist()` + `fuzz.token_set_ratio`. Fallback: `difflib.get_close_matches()`. |
| **T4** | Add `_native_accel_loaded()` status function | `archive/native_accel.py` | Returns `{"rapidfuzz": bool, "barcode_gen": bool, "python_fallback": bool}`. Logged at app startup via `log.info()`. |

### Phase 2: Rust Extension — Batch Barcode Generation (T5–T7)

| # | Task | Output File | Description |
|---|------|-------------|-------------|
| **T5** | Create `archive/barcode_gen/Cargo.toml` | `archive/barcode_gen/Cargo.toml` | Follow `archive/rust_crypto/Cargo.toml` pattern. `crate-type = ["cdylib"]`, `pyo3 = { version = "0.23", features = ["extension-module", "abi3-py38"] }`, `uuid = { version = "1", features = ["v4"] }`. |
| **T6** | Implement `archive/barcode_gen/src/lib.rs` | `archive/barcode_gen/src/lib.rs` | PyO3 `#[pyfunction]` for `generate_barcodes(vendor_name, count)`. Matches `barcode_logic.generate_internal_barcode()` format exactly: `{prefix}-{uuid6}`. |
| **T7** | Build .pyd and add to `.gitignore` | `archive/barcode_gen/*.pyd` | Run `maturin develop --release`. Verify `import barcode_gen; barcode_gen.generate_barcodes("MedSupply", 5)` produces 5 unique barcodes. Add `target/` and `*.pyd` to `.gitignore`. |

### Phase 3: rapidfuzz Integration — Fuzzy Search (T8–T12)

> **Note:** rapidfuzz is used as a **ranking layer** on top of existing SQL LIKE queries, not a replacement. SQL LIKE provides the initial pre-filter; rapidfuzz ranks results by fuzzy similarity.

| # | Task | File(s) | Change Description |
|---|------|---------|-------------------|
| **T8** | Patch `_search_patients()` | `archive/ui_clinical_workflow.py:175-188` | Replace Python `query in str(p).lower()` filter with `native_accel.fuzzy_search(query, [p[1] for p in patients], cutoff=60)` for name-based fuzzy ranking. |
| **T9** | Patch `_refresh_patient_list()` | `archive/ui_clinical_workflow.py:625-634` | Same fuzzy search approach as T8. |
| **T10** | Patch `_search_drugs_fallback()` | `archive/ui_clinical_workflow.py:466-483` | When `ndc_lookup(query)` returns None, fall back to `name_lookup(query)` + `native_accel.fuzzy_match_one(query, [r["drug_name"] for r in results], cutoff=70)`. |
| **T11** | Patch `get_sig_suggestions()` | `archive/quick_sig.py:216-231` | Add `native_accel.fuzzy_search(query, template_names, cutoff=65)` as a secondary ranking on the SQL LIKE results. |
| **T12** | Patch `auto_map_csv_headers()` | `archive/bulk_import_staging.py:74-126` | Replace 8-pass alias matching with `native_accel.fuzzy_match_headers()`. Keep existing 8-pass as fallback if rapidfuzz unavailable. |

### Phase 4: Rust Barcode Integration — Batch Generation (T13–T15)

| # | Task | File(s) | Change Description |
|---|------|---------|-------------------|
| **T13** | Patch `receive_inventory_atomically()` (sqlite3 path) | `archive/database.py:760-774` | Before the `for i in range(quantity)` loop, if `_HAS_RUST_BARCODE` and `pre_generated_barcodes` is None: call `native_accel.generate_batch_barcodes(vendor_name, quantity)` once. Then use `pre_generated_barcodes` in the loop. Eliminates per-iteration UUID generation. |
| **T13b** | Patch `receive_inventory_atomically()` (SQLAlchemy path) | `archive/db.py:848-878` | Same logic — pre-generate barcodes via `native_accel.generate_batch_barcodes()` before the loop. |
| **T14** | Patch `ui_receive_tab._print_bulk_labels()` | `archive/ui_receive_tab.py:613-629` | Replace inner loop `barcode_logic.generate_internal_barcode(vendor)` with `native_accel.generate_batch_barcodes(vendor, item["qty"])` — single batch call outside the box-building loop. |
| **T15** | Patch `excel_handler.execute_import()` | `archive/excel_handler.py:141` | Replace per-row `barcode_logic.generate_internal_barcode(vendor)` with `native_accel.generate_batch_barcodes(vendor, len(rows))` (if vendor is uniform across rows) or per-vendor batch if mixed. |

### Phase 5: Build & Packaging Integration (T16–T18)

| # | Task | File(s) | Change Description |
|---|------|---------|-------------------|
| **T16** | Add `barcode_gen.pyd` to PyInstaller binary bundling | `archive/build_exe.py:199` | Add `"barcode_gen.pyd"` to the existing tuple: `for ext_name in ("rust_crypto.pyd", "hw_client.pyd", "barcode_gen.pyd")`. |
| **T17** | Add `barcode_gen` to PyInstaller hidden imports | `archive/build_exe.py:173` | Add `"barcode_gen"` to the `hidden` imports list (alongside `"hw_client"`). |
| **T18** | Add `rapidfuzz` to requirements | `requirements.txt` (root) | Add `rapidfuzz>=3.10.0` to root `requirements.txt` (desktop app dependencies). The `archive/requirements.txt` is for the Flask license server and does not need rapidfuzz. |

### Phase 6: Testing (T19–T22)

| # | Task | Output File | Description |
|---|------|-------------|-------------|
| **T19** | Write fuzzy search tests | `archive/test_native_accel.py` | Test `fuzzy_search("Amoxicilln", ["Amoxicillin", "Aspirin"])` returns Amoxicillin first. Test fallback when rapidfuzz unavailable (mock `sys.modules`). Test `fuzzy_match_headers` with messy CSV headers. |
| **T20** | Write barcode generation tests | `archive/test_native_accel.py` | Test `generate_batch_barcodes("MedSupply", 10)` returns 10 unique strings matching `MED-[A-F0-9]{6}`. Test count=0, N/A vendor → `PRD-` prefix, fallback path. |
| **T21** | Write integration smoke tests | `archive/test_native_accel.py` | Import `native_accel`, verify `_native_accel_loaded()` returns correct status. Verify `fuzzy_search` and `generate_batch_barcodes` are callable. Verify barcode format matches `barcode_logic.generate_internal_barcode()` on both paths. |
| **T22** | Verify zero regression | `archive/test_phase16.py` | Run existing 25 Phase 16 tests — all must still pass. Verify existing Rust extensions (rust_crypto, hw_client) still import correctly. |

---

## 6. Verification Plan

### Pre-build (static analysis)
```bash
cd archive
python -m py_compile native_accel.py
python -c "import native_accel; print(native_accel._native_accel_loaded())"
cargo check --manifest-path barcode_gen/Cargo.toml
```

### Functional tests
```python
import native_accel

# Status check
status = native_accel._native_accel_loaded()
assert "rapidfuzz" in status
assert "barcode_gen" in status

# rapidfuzz fuzzy search
results = native_accel.fuzzy_search(
    "amox", ["Amoxicillin 500mg", "Aspirin 81mg"], limit=5, cutoff=60
)
assert len(results) >= 1
assert "Amoxicillin" in results[0][0]  # results: [(match_str, score, index)]

# Batch barcode generation
barcodes = native_accel.generate_batch_barcodes("MedSupply", 10)
assert len(barcodes) == 10
assert len(set(barcodes)) == 10  # all unique
assert all(b.startswith("MED-") for b in barcodes)

# N/A vendor fallback (matches barcode_logic)
barcodes_na = native_accel.generate_batch_barcodes("N/A", 5)
assert all(b.startswith("PRD-") for b in barcodes_na)

# Empty batch
assert native_accel.generate_batch_barcodes("MedSupply", 0) == []

# Barcode format matches barcode_logic on both paths
from barcode_logic import generate_internal_barcode
single = generate_internal_barcode("MedSupply")
batch = native_accel.generate_batch_barcodes("MedSupply", 1)
assert single.startswith("MED-")
assert batch[0].startswith("MED-")
# Both produce same format: {prefix}-{6_hex_chars}
```

### Zero-regression
```bash
cd archive
python -m pytest test_phase16.py -v       # All 25 tests must pass
python -m pytest test_native_accel.py -v   # All new tests must pass
```

---

## 7. Edge Cases & Failure Modes

| Scenario | Behavior |
|----------|----------|
| rapidfuzz not installed (dev environment, no wheel) | `native_accel.py` falls back to `difflib.SequenceMatcher` — fuzzy search works, just slower. No crash. |
| Rust .pyd not built (development without maturin) | `generate_batch_barcodes()` falls back to `barcode_logic.generate_internal_barcode()` per call — functionally identical, slower on large batches. |
| Rust .pyd present but wrong Python version (ABI mismatch) | `import barcode_gen` raises `ImportError` → caught → `_HAS_RUST_BARCODE = False` → Python fallback. |
| PyInstaller frozen app fails to load .pyd | Same `ImportError` catch → graceful degradation to Python fallback. Application still fully functional. |
| Fuzzy search returns 0 results above cutoff | Returns empty list → calling code shows "no results" messagebox. No crash. |
| Zero-count batch barcode generation | Returns empty list immediately — no syscalls, no iterations. |
| Vendor name contains non-ASCII characters | Same normalization as `barcode_logic.generate_internal_barcode()`: `vendor_name.strip()[:3].upper()`. Rust uses `to_ascii_uppercase()` for prefix, matching Python's `.upper()` behavior for ASCII vendor names. |
| Existing Rust extensions (rust_crypto, hw_client) unaffected | `native_accel.py` only imports `barcode_gen`, not the existing extensions. No interference. |
| `database.py` `@_db_fallback` decorator interaction | The SQLite fallback path and SQLAlchemy path (db.py) both call `native_accel.generate_batch_barcodes()` — works identically in both. The `@_db_fallback` decorator is transparent to this change. |
| rapidfuzz `Tfidf` scorer unavailable in older versions | Code tests for `hasattr(_rf_fuzz, 'Tfidf')` and falls back to `fuzz.WRatio` if not present. |

---

## 8. Dependencies & Build Considerations

### 8.1. New Dependencies

| Package | Version | Source | Build Required? |
|---------|---------|--------|-----------------|
| `rapidfuzz` | >=3.10.0 (latest: 3.14.5) | PyPI (pre-built wheels for Win/Linux/macOS) | No — wheels include compiled C++ |
| `barcode_gen` | 1.0.0 | Local Rust project (`archive/barcode_gen/`) | Yes — built via `maturin` |

### 8.2. Build Workflow

```bash
# 1. Install rapidfuzz (development)
pip install rapidfuzz>=3.10.0

# 2. Build Rust extension (development)
maturin develop --manifest-path archive/barcode_gen/Cargo.toml --release

# 3. Production build (PyInstaller)
maturin build --release --manifest-path archive/barcode_gen/Cargo.toml
# → produces barcode_gen-*.whl in target/wheels/
# Extract barcode_gen.pyd from wheel, place in archive/
# Run: python archive/build_exe.py  (bundles .pyd + rapidfuzz wheel)
```

### 8.3. PyInstaller Integration (build_exe.py changes)

- **Line 173:** Add `"barcode_gen"` to `hidden` list (alongside `"hw_client"`)
- **Line 199:** Extend binary list tuple:
  ```python
  for ext_name in ("rust_crypto.pyd", "hw_client.pyd", "barcode_gen.pyd"):
  ```

### 8.4. .gitignore Updates

Add to root `.gitignore` and `archive/.gitignore` (if exists):
```
# Rust barcode generator
archive/barcode_gen/target/
archive/barcode_gen/*.pyd
archive/*.egg-info/
```

---

## 9. Affected Files Summary

### New Files
| File | Purpose |
|------|---------|
| `archive/native_accel.py` | Shared native acceleration module (rapidfuzz + Rust barcode + difflib/uuid fallbacks) |
| `archive/barcode_gen/Cargo.toml` | Rust project manifest for PyO3 barcode generator |
| `archive/barcode_gen/src/lib.rs` | PyO3 Rust extension: `generate_barcodes(vendor_name, count)` |
| `archive/test_native_accel.py` | Unit tests for native acceleration (fuzzy search + barcode gen + fallback) |

### Modified Files
| File | Tasks | Change |
|------|-------|--------|
| `archive/ui_clinical_workflow.py` | T8, T9, T10 | Replace Python substring filter with `native_accel.fuzzy_search()` |
| `archive/quick_sig.py` | T11 | Add `native_accel.fuzzy_search()` as ranking layer on SQL LIKE |
| `archive/bulk_import_staging.py` | T12 | Replace 8-pass header matching with `native_accel.fuzzy_match_headers()` |
| `archive/database.py` | T13 | Pre-generate barcodes via `native_accel.generate_batch_barcodes()` in `receive_inventory_atomically()` |
| `archive/db.py` | T13b | Same pre-generation in SQLAlchemy path of `receive_inventory_atomically()` |
| `archive/ui_receive_tab.py` | T14 | Batch barcode generation for `_print_bulk_labels()` |
| `archive/excel_handler.py` | T15 | Batch barcode generation for `execute_import()` |
| `archive/build_exe.py` | T16, T17 | Bundle `barcode_gen.pyd` + add `barcode_gen` hidden import |
| `requirements.txt` | T18 | Add `rapidfuzz>=3.10.0` |
| `.gitignore` | T7 | Add Rust build artifacts |

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| rapidfuzz wheel missing on some platform (e.g., ARM Linux) | Pure-Python `difflib` fallback is tested and verified at import time |
| Rust .pyd ABI mismatch with frozen PyInstaller binary | `abi3-py38` feature ensures cross-version .pyd compatibility; `ImportError` → fallback |
| rapidfuzz `fuzz.WRatio` returns different ranking than existing SQL LIKE | rapidfuzz is an **additional layer** on top of SQL LIKE — refines results, doesn't replace the DB query |
| Barcode format mismatch between Rust and Python paths | Unit test (T20) verifies format `MED-[A-F0-9]{6}` on both paths; both use identical normalization logic |
| Performance regression in fallback path | Fallback is only used when native libs absent — acceptable. Primary build environments always have them. |
| Rust extension panics on edge case input | PyO3 catches Rust panics and converts to `Python` exceptions — caught by `try/except` in `native_accel.py` → Python fallback |
| Header mapping misses a field with rapidfuzz but caught by 8-pass | `fuzzy_match_headers()` returns confidence scores; low-confidence matches are filtered, and the 8-pass fallback handles edge cases |
