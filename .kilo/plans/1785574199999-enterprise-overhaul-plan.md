# PharmacyPro Enterprise Overhaul — Implementation Plan

## 1. Overview & Goals

Transform PharmacyPro from a flat-tab Tkinter desktop app + Flask license server into an
elite, commercial-grade, multi-language pharmacy enterprise suite — **without removing or
degrading any existing feature, tab, API route, or license verification logic.**

### Resolved Design Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | OCR engine | Local-first pytesseract + Pillow → Ollama vision/cloud fallback | Offline-capable, HIPAA-friendly, Section 4.2 compliant (no heavy ML bundled) |
| 2 | Daily sales email source | Local `pharmacy.db` sales report | Pharmacist needs daily sales summary, not license metrics |
| 3 | SQLAlchemy migration | Gradual adapter-layer (`database.py` delegates to `db.py`) | `db.py` ORM models already exist; preserves all 57 functions and 8 tab modules |
| 4 | Crash payload encryption | Full Fernet via `cryptography>=42.0` | True encryption (AES-128-CBC + HMAC), not just signing |
| 5 | UI redesign scope | Scoped overhaul (drawer + Dashboard/Settings/Checkout) | 3 high-impact tabs rebuilt; 6 tabs get design-system updates |
| 6 | Rust extensions | Phase 1: HWID + Fernet crypto as PyO3 `.pyd`; Phase 2: barcode | Build pipeline proven via existing `build-rust.yml` |
| 7 | Async wrapping scope | Selective (heavy DB ops only — 10 functions) | Matches existing threading patterns; avoids refactoring 47 light queries |

---

## 2. Architecture Impact

```
┌─────────────────────────────────────────────────────────┐
│  Desktop App (archive/main.py → main_app.py)            │
│  PyInstaller --onefile, customtkinter, Pillow, pytesseract│
├─────────────────────────────────────────────────────────┤
│  Navigation Drawer (NEW — ui.py)                        │
│  ┌─────┬──────────────────────────────────────┐         │
│  │ ←   │ Content Area (swaps between pages)  │         │
│  │Nav  │                                      │         │
│  │     │ Dashboard · Add · Inventory · ...   │         │
│  │     │ Settings · Checkout · etc.          │         │
│  └─────┴──────────────────────────────────────┘         │
├─────────────────────────────────────────────────────────┤
│  Data Layer (database.py → db.py ORM adapter)           │
│  ┌──────────────────────────────────────────┐           │
│  │  database.py (57 functions, thin adapter)│           │
│  │  → delegates to→                          │           │
│  │  db.py (SQLAlchemy models + sessions)     │           │
│  └──────────────────────────────────────────┘           │
│  SQLite (default) | PostgreSQL (DATABASE_URL)           │
├─────────────────────────────────────────────────────────┤
│  OCR Cascade (NEW — ocr_cascade.py)                    │
│  ┌→ TesseractEngine (pytesseract + Pillow)             │
│  ├→ OllamaVisionEngine (fallback, async)               │
│  ├→ CloudOCREngine (optional fallback)                 │
│  └→ ConfidenceGate (≥85% → parse; <85% → AI route)     │
├─────────────────────────────────────────────────────────┤
│  Daily Report (NEW — local_daily_report.py)            │
│  Settings tab "Automated Reports" section              │
├─────────────────────────────────────────────────────────┤
│  Crash Reporter (UPDATED — crash_reporter.py)            │
│  sys.excepthook → Fernet encrypt → POST /api/report-error│
│             → AI Debug Agent workflow (exists)          │
├─────────────────────────────────────────────────────────┤
│  Rust Extensions (NEW — hwid-client PyO3)               │
│  ├── hw_client.pyd → HWID generation (replaces license_gate.py)│
│  └── rust_crypto.pyd → Fernet encrypt/decrypt          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Backend (archive/server_app.py — Flask)                 │
│  /api/report-error → Fernet decrypt → GitHub Issue       │
│                    → KNOWN_FIXES → SMTP fix email       │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Implementation Phases

### Phase 1: Crash Encryption Enhancement (§2.1)

**Goal**: Encrypt crash telemetry payloads at the payload level (not just HTTPS).

**Files to create**:
- `archive/crypto_utils.py` — Fernet wrapper with static app key derivation (PBKDF2 + app secret), `encrypt_payload()` and `decrypt_payload()` functions, structured logging, PyInstaller-safe path resolution.

**Files to modify**:
- `requirements.txt` — Add `cryptography>=42.0`
- `archive/crash_reporter.py` — Import `crypto_utils`, call `encrypt_payload()` before `_send_report()` POST. Keep existing exception hook, payload structure, and non-blocking daemon thread. Log cascade trigger events.
- `archive/server_app.py` `/api/report-error` (line 1569) — Decrypt incoming Fernet payload, then process as before. Add decryption failure handling (log + 400 response).
- `archive/PharmacyPro_Enterprise.spec` + `archive/build_exe.py` — Add `cryptography` to hidden imports.
- `README.md` — Update if it lists dependencies.

**Verification**:
- `test_crash_crypto.py` — Encrypt → decrypt round-trip test, tamper detection test, large payload test.
- Existing `exhaustive_verify.py` crash tests must still pass.
- `crash_reporter.py` must work in both dev and frozen (`sys._MEIPASS`) modes.

---

### Phase 2: SQLAlchemy Adapter Layer (§3.4)

**Goal**: Migrate `database.py` (raw sqlite3, 57 functions) to delegate to `db.py` (SQLAlchemy ORM) without breaking existing tab imports.

**Audit**: All 8 tab modules import `database` directly:
- `ui_dashboard_tab.py` → `get_dashboard_metrics()`
- `ui_add_tab.py` → `add_product()`, `get_product_template()`
- `ui_inventory_tab.py` → `get_all_in_stock_batches()`, `search_products()`, `get_groups()`, etc.
- `ui_expiring_tab.py` → `get_expiring_batches()`, `get_expiring_counts_by_vendor()`
- `ui_report_tab.py` → `get_sales_analytics()`, `get_top_selling_products()`, `get_sold_items()`, etc.
- `ui_receive_tab.py` → `receive_inventory_atomically()`, `log_shipment()`, `get_all_receiving_log()`, etc.
- `ui_checkout_tab.py` → `mark_item_as_sold()`, `create_receipt()`, `reverse_receipt_item()`
- `ui_settings_tab.py` → `save_settings()` already calls `db.reconnect_db()` at line 501

**Approach**: In `database.py`, each function becomes a thin wrapper that calls the equivalent `db.py` ORM function. Signatures and return types stay identical (tuples, not ORM objects — convert with `.to_tuple()` or manual mapping).

**Key functions to migrate first** (used by most tabs):
1. `get_all_in_stock_batches()` → `db.py` Product.query
2. `search_products()` → already in db.py
3. `add_product()` → already in db.py
4. `get_dashboard_metrics()` → db.py aggregate queries
5. `get_sales_analytics()` → db.py aggregate queries
6. `receive_inventory_atomically()` → db.py session transaction
7. `create_receipt()` → db.py session transaction
8. `get_product_by_internal_barcode()` / `get_product_by_barcode()` → db.py
9. `get_expiring_batches()` → db.py
10. `get_sold_items()` / `get_receipts()` → db.py

**Files to modify**:
- `database.py` — Wrap each function body: `from db import Product, get_session, ...` → use ORM → convert results to match original return format (list of tuples). Add `DATABASE_URL` support via `config.json`.
- `archive/PharmacyPro_Enterprise.spec` + `build_exe.py` — Ensure `sqlalchemy>=2.0` is in hidden imports.

**Files to verify already complete**:
- `db.py` — Models and session factory already exist (lines 240-457). Verify all 12+ tables are mapped.
- `ui_settings_tab.py:501` — Already calls `_db.reconnect_db(db_url)` for PostgreSQL switching.

**Verification**:
- All 57 functions must return identical data types to original sqlite3 versions.
- `exhaustive_verify.py` must pass all existing checks.
- Run `database.init_db()` after migration to verify schema compatibility.

---

### Phase 3: OCR Cascade System (§3.1 + §4.2)

**Goal**: Image-to-text OCR pipeline for paper invoices/prescriptions with confidence-based fallback.

**Files to create**:

1. `archive/ocr_engine.py` — Abstract base class + concrete engines:
   - `OCREngine` (ABC): `extract(image_path: str) -> OcrResult`, `get_confidence() -> float`
   - `OcrResult` (dataclass): `text: str`, `boxes: list[dict]`, `confidence: float`, `engine: str`
   - `TesseractEngine(OCREngine)`: pytesseract + Pillow preprocessing (grayscale → Gaussian blur → Otsu binarization → non-local means denoising). Returns word-level bounding boxes via `image_to_data()`.
   - `OllamaVisionEngine(OCREngine)`: Sends image to local Ollama vision model via `auto_extract.py` pattern. Uses `ThreadPoolExecutor` for non-blocking execution.
   - `CloudOCREngine(OCREngine)`: Optional — configures AWS Textract / Google Vision via env vars (`OCR_CLOUD_PROVIDER`, `OCR_API_KEY`).

2. `archive/ocr_cascade.py` — 4-step cascade orchestrator:
   - **Step 1 (Fast)**: `TesseractEngine.extract()` — fast baseline OCR with Pillow preprocessing.
   - **Step 2 (Gatekeeper)**: Evaluate confidence. If `>= 0.85`, parse via `smart_parser.parse_invoice()` and return.
   - **Step 3 (AI Failover)**: If confidence `< 0.85`, dispatch to `OllamaVisionEngine` async (ThreadPoolExecutor). If Ollama unavailable, try `CloudOCREngine` if configured.
   - **Step 4 (Graceful Degradation)**: If all fail, return Tesseract text + emit `OCR_LOW_CONFIDENCE` event with confidence score for UI warning.

3. `archive/design_system.py` — Centralized design tokens:
   - Color constants: slate blue (`#3B82F6`), cyan (`#06B6D4`), muted dark (`#1E1E1E`), slate backgrounds
   - Typography: heading (18px bold), body (13px), caption (11px)
   - Card styles: `fg_color`, `corner_radius`, `border_width`
   - Status badge colors (green/yellow/red)
   - Light/dark mode palette

**Files to modify**:
- `archive/ui_receive_tab.py` — Add "Scan Document" button next to existing "Process Supplier Invoice (AI)" button. On click: file dialog for image (PNG/JPG), run `ocr_cascade.process_image()`, route results to `_ai_populate_review()` (reuse existing review UI). Handle `OCR_LOW_CONFIDENCE` event with styled notification.
- `build_exe.py` + `PharmacyPro_Enterprise.spec` — Add `pytesseract`, `cryptography`, `sqlalchemy` to hidden imports. Ensure Tesseract binary can be found via `path_utils.get_resource_path()` (check `sys._MEIPASS` first for frozen builds).
- `archive/requirements.txt` (root) — Add `pytesseract>=0.3.10`, `cryptography>=42.0`

**Dependencies**:
- `pytesseract` (Python wrapper) + system Tesseract binary (~15MB)
- `Pillow` already available (used in barcode_logic.py, canvas_core.py)
- `numpy` for image preprocessing (check if already available; if not, add)

**Verification**:
- `test_ocr_cascade.py` — Mock invoice image test, confidence threshold test, fallback trigger test, graceful degradation test.
- `exhaustive_verify.py` — Add OCR engine import check (like the existing smart_parser check at line 673).

---

### Phase 4: Daily Sales Email System (§1.3)

**Goal**: Settings tab "Automated Reports" section with email config + test button.

**Files to create**:

1. `archive/local_daily_report.py` — Queries `pharmacy.db` for sales metrics:
   - `generate_yesterday_report()` — Total revenue, unique patients, top-selling item, itemized list of all products sold yesterday
   - `generate_periodic_trends(period='week'|'month')` — Top-selling items, accumulated revenue for configurable timeframe
   - `get_low_stock_alerts()` — Items below `low_stock_threshold` from `config.json`
   - `build_html_email(report: dict) -> str` — Professional HTML email template with cards, tables, status indicators (reuse patterns from `daily_sales_report.py` HTML builder at line 121)
   - `send_report(smtp_config: dict, to_email: str, report: dict) -> bool` — SMTP delivery with async support
   - `schedule_daily_report(checkpoint_callback)` — Background daemon thread that sends report at configured time daily

2. Functions query these tables:
   - `sold_items` (item_name, price, timestamp_of_sale, vendor_name)
   - `receipts` (id, timestamp, total_amount, patient_id)
   - `products` (name, vendor_name)
   - `patients` (id, name, phone)

**Files to modify**:
- `archive/ui_settings_tab.py` — Add "Automated Reports" section after PostgreSQL section (after line 206):
  - `CTkSwitch` (enable/disable daily reports)
  - `CTkEntry` (daily report email address)
  - SMTP configuration: host (Entry), port (Entry, default 587), user (Entry), password (Entry, show="*")
  - `CTkButton` ("Send Test Email") → calls `local_daily_report.send_test_email()`
  - `CTkButton` ("Verify SMTP") → tests connection without sending
  - Save config to `config.json` (keys: `report_email`, `report_enabled`, `smtp_host`, `smtp_port`, `smtp_user`, `smtp_pass`)
- `archive/config.json` — Add new config keys with defaults

**Verification**:
- `test_local_report.py` — Generate report from test DB, validate HTML structure, verify email sending (dry-run mode).
- `exhaustive_verify.py` — Add daily report generation + email format checks.

---

### Phase 5: UI Redesign — Navigation Drawer + Card Layouts (§1.1, §1.2)

**Goal**: Replace flat CTkTabview with left-side navigation drawer. Redesign Dashboard, Settings, and Checkout tabs with card-based layouts.

**Files to create**:

1. `archive/design_system.py` — (Created in Phase 3)
   - `COLORS` dict: `slate_blue`, `cyan`, `dark_bg`, `card_bg`, `border`, etc.
   - `TYPOGRAPHY` dict: font sizes and weights
   - `StatusBadge` helper class — colored circular indicator with text
   - `Card` helper — CTkFrame factory with consistent padding/styling
   - `BadgeCounter` helper — overlay badge on nav items

**Files to modify**:

1. `archive/ui.py` — **Core structural change**:
   - Replace `self.tab_view = ctk.CTkTabview(self)` (line 110) with:
     - Left sidebar `CTkFrame` (width 60px collapsed, 200px expanded) with `CTkButton` nav items
     - Main content `CTkFrame` that shows/hides page frames
   - `_show_page(page_name)` method replaces `self.tab_view.set()` calls
   - `_update_nav_badges()` replaces `_update_tab_badges()` (line 169)
   - `on_page_change()` replaces `on_tab_change()` (line 261) — same tab switch logic
   - Preserve ALL 9 page frames and their setup methods (lines 130-141)
   - Badge counters: use canvas/overlay on nav button labels (like existing `_update_tab_badges` logic at line 178-192)

   **CRITICAL**: Every `self.tab_view.set("X")` call in tab modules must be replaced with `self._show_page("X")`. Every `self.tab_view.get()` with `self._current_page`.

2. `archive/ui_dashboard_tab.py` — Redesign with cards:
   - Quick Stats card (4 KPI values in a grid)
   - Inventory Actions card (Add Product, Import, Export buttons)
   - System Diagnostics card (DB path, version, last backup, sync status)
   - Low Stock Alerts card (with status badges)
   - Recent Activity feed (scrollable)
   - All cards: `corner_radius=10`, `fg_color=COLORS.card_bg`, consistent padding

3. `archive/ui_settings_tab.py` — Add Automated Reports card (from Phase 4):
   - Wrap existing settings in cards: "Pharmacy Info", "Database", "PostgreSQL", "Reports"
   - New "Automated Reports" card with SMTP config + email toggle + test button
   - Light/dark theme toggle switch at top of Settings

4. `archive/ui_checkout_tab.py` — Modern card layout:
   - Product lookup card (barcode scanner input + search button)
   - Cart summary card (Treeview with status badges per item)
   - Payment card (total, discount, payment method, change due, confirm/refund buttons)
   - Receipt history card (Treeview with column sorting)

5. **Design system updates for remaining 6 tabs** (ui_add_tab, ui_inventory_tab, ui_expiring_tab, ui_report_tab, ui_receive_tab, ui_templates_tab, ui_patients_tab):
   - Import and use `design_system.COLORS` and `design_system.Typography`
   - Add column sorting to all Treeviews (click column header to sort)
   - Add status badge coloring (In Stock = green, Expired = red, etc.)
   - Consistent `corner_radius=8` on all frames
   - Consistent font sizes and colors

**Files to update for PyInstaller**:
- `build_exe.py` — Add `design_system` to hidden imports

**Verification**:
- `_debug_layout_geometry()` function in `ui.py` (per AGENTS.md Protocol II.A) — runtime assertions after `root.update_idletasks()`
- Verify sidebar width ≥ 200px, no widget clipping
- All 9 pages must load without AttributeError/NameError

---

### Phase 6: Rust Extension Integration (§4.1, Phase 1)

**Goal**: Expose HWID generation and Fernet encryption as compiled Rust `.pyd` extensions.

**Files to create**:

1. `hwid-client/src/lib.rs` — PyO3 module wrapping existing `hwid.rs`:
   - `#[pyfunction] fn generate_hwid_py() -> PyResult<String>` — calls `hwid::generate_hwid()`
   - `#[pymodule] fn hw_client(py, m)` — register module
   - Uses `pyo3 = { version = "0.22", features = ["extension-module"] }`

2. `hwid-client/src/crypto.rs` — Rust Fernet implementation:
   - `fn encrypt_payload(payload: &[u8], key: &[u8]) -> String` — AES-128-CBC + HMAC-SHA256
   - `fn decrypt_payload(encrypted: &str, key: &[u8]) -> Vec<u8>` — verify + decrypt
   - `fn derive_key(app_secret: &str, salt: &str) -> [u8; 32]` — PBKDF2 key derivation
   - Matches `cryptography.fernet.Fernet` output format for interoperability

3. `hwid-client/src/lib.rs` — Add `crypto` module:
   - `#[pyfunction] fn encrypt_py(payload: String, key: String) -> PyResult<String]`
   - `#[pyfunction] fn decrypt_py(token: String, key: String) -> PyResult<String]`

**Files to modify**:

1. `hwid-client/Cargo.toml` — Add:
   ```toml
   [lib]
   name = "hw_client"
   crate-type = ["cdylib"]

   [dependencies]
   pyo3 = { version = "0.22", features = ["extension-module"] }
   aes = "0.8"
   hmac = "0.12"
   sha2 = "0.10"
   base64 = "0.22"
   pbkdf2 = "0.12"
   ```

2. `.github/workflows/build-rust.yml` — Add build step for `.pyd`:
   - `cargo build --release` for the lib target (cdylib)
   - Upload `hw_client.pyd` as artifact for Windows
   - Add `maturin` build step

3. `archive/license_gate.py` — Replace Python `_get_anonymized_hwid()` (line 35-53) with Rust `hw_client.generate_hwid()`:
   - `try: import hw_client; hwid = hw_client.generate_hwid()` (fallback to Python if .pyd not found)

4. `archive/crash_reporter.py` — Use `crypto_utils.py` which tries Rust `rust_crypto.encrypt()` first, falls back to Python `cryptography.fernet.Fernet` if `.pyd` not available.

5. `archive/PharmacyPro_Enterprise.spec` + `build_exe.py` — Add `hw_client.pyd` / `rust_crypto.pyd` as binaries.

**Verification**:
- `test_rust_extensions.py` — HWID consistency test (Rust vs Python fallback), encrypt/decrypt round-trip, cross-platform path handling.
- `exhaustive_verify.py` — Add Rust module availability check.

---

### Phase 7: Async Non-Blocking UI (§3.3)

**Goal**: Wrap heavy database operations in `ThreadPoolExecutor` to maintain 60 FPS.

**Functions to wrap** (in `database.py`):
1. `init_db()` — runs at startup (line 13)
2. `add_product()` — product creation
3. `receive_inventory_atomically()` — batch receiving
4. `create_receipt()` — checkout confirmation
5. `get_dashboard_metrics()` — dashboard load
6. `get_sales_analytics()` — analytics tab
7. `get_all_receiving_log()` — receiving tab load
8. `backup_database()` — backup operation
9. `get_sold_items()` — report tab data
10. `search_products()` — inventory search

**Pattern** (matching existing `excel_handler.py:165` and `auto_extract.py:103`):
```python
def get_dashboard_metrics_async(callback):
    def _worker():
        result = get_dashboard_metrics()
        # Schedule callback on UI thread
    t = threading.Thread(target=_worker, daemon=True, name="db-worker")
    t.start()
```

Each tab module calls the `_async` variant → gets result via `self.after(0, callback)`.

**Files to modify**:
- `database.py` — Add `_async` wrapper variants for the 10 heavy functions above
- Tab modules (`ui_dashboard_tab.py`, `ui_checkout_tab`, etc.) — Switch calls from sync to async variants where blocking is perceptible

**Verification**:
- UI must not freeze for >0.1s during any DB operation
- All existing tab functionality must work identically with async variants

---

### Phase 8: i18n & Multi-Language Expansion (§4)

**Goal**: Ensure all new UI elements are translatable; add language keys for OCR, reports, and redesign.

**Files to modify**:
- `archive/locales/en.json` — Add new keys for: OCR cascade UI, Automated Reports, error messages, navigation drawer labels
- All locale files (`ar`, `de`, `es`, `fr`, `pt`) — Add matching keys with translations

**Verification**:
- `exhaustive_verify.py` line 673+ already tests i18n loading; add checks for new keys.

---

## 4. Files Created/Modified (Summary)

### New files:
| File | Phase | Purpose |
|------|-------|---------|
| `archive/crypto_utils.py` | 1 | Fernet encryption wrapper |
| `archive/ocr_engine.py` | 3 | ABC + Tesseract/Ollama/Cloud engines |
| `archive/ocr_cascade.py` | 3 | 4-step confidence cascade |
| `archive/local_daily_report.py` | 4 | Pharmacy sales email report |
| `archive/design_system.py` | 3/5 | Centralized design tokens |
| `hwid-client/src/lib.rs` | 6 | PyO3 module entry |
| `hwid-client/src/crypto.rs` | 6 | Rust Fernet implementation |
| `test_ocr_cascade.py` | 3 | OCR tests |
| `test_local_report.py` | 4 | Report tests |
| `test_crash_crypto.py` | 1 | Encryption tests |
| `test_rust_extensions.py` | 6 | Rust extension tests |

### Modified files:
| File | Phase | Change |
|------|-------|--------|
| `requirements.txt` (root) | 1,3 | Add `cryptography`, `pytesseract` |
| `archive/requirements.txt` | — | SQLAlchemy already present |
| `archive/crash_reporter.py` | 1 | Encrypt payloads before POST |
| `archive/server_app.py` | 1 | Decrypt in `/api/report-error` |
| `archive/database.py` | 2 | Wrap functions to delegate to ORM |
| `archive/ui.py` | 5 | Replace CTkTabview with nav drawer |
| `archive/ui_dashboard_tab.py` | 5 | Card-based layout |
| `archive/ui_settings_tab.py` | 4,5 | Add Automated Reports card |
| `archive/ui_checkout_tab.py` | 5 | Card-based layout |
| `archive/ui_receive_tab.py` | 3 | Add OCR scan button |
| `archive/ui_*.py` (6 tabs) | 5 | Design system updates |
| `build_exe.py` | Multiple | Add dependencies to build |
| `PharmacyPro_Enterprise.spec` | Multiple | Update hidden imports + binaries |
| `hwid-client/Cargo.toml` | 6 | Add PyO3 + crypto deps |
| `.github/workflows/build-rust.yml` | 6 | Add PyO3 build step |
| `hwid-client/src/main.rs` | — | Move logic to lib.rs (no changes needed) |
| `archive/locales/*.json` | 8 | New i18n keys |
| `PROJECT_MAP.md` | End | Update with new architecture |
| `VERIFICATION_CHECKLIST.md` | End | Update with new checks |

---

## 5. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Full UI rewrite breaks tabs | Scoped approach: only 3 tabs redesigned, 6 tabs get incremental updates. `_show_page()` maintains same `on_tab_change` logic. |
| Database migration breaks queries | Adapter layer preserves return types. `database.py` functions delegate to `db.py` ORM — existing callers see identical data. |
| OCR pipeline fails on prescriptions | Graceful degradation: return Tesseract text + UI warning notification. No blocking, no crash. |
| RSA/Rust extension fails to compile | Fallback to Python implementations. `try: import hw_client; except: use Python fallback` |
| Crash encryption breaks report flow | Server `/api/report-error` handles both encrypted and legacy payloads during transition |
| PyInstaller `--onefile` can't find Tesseract | Use `path_utils.get_resource_path()` for binary discovery, check `sys._MEIPASS` |
| New dependencies bloat executable | Only add `pytesseract`, `cryptography` — Tesseract binary ~15MB, cryptography ~4MB. UPX compression already enabled. |
| Async threading causes race conditions | All UI updates via `self.after(0, callback)`. Database sessions are thread-local (`check_same_thread=False` for SQLite). |

---

## 6. Validation & Testing Plan

### Existing test infrastructure (must remain 100% passing):
1. **`archive/test_server.py`** — 55-test unittest suite (server endpoints, license flow, i18n, smart_parser)
2. **`archive/exhaustive_verify.py`** — 120+ checks across 10 categories (env config, Paddle API, webhooks, OCR/AI pipeline, i18n, etc.)
3. **`archive/test_ai_pipeline.py`** — AI extraction tests
4. **`archive/test_security.py`** — License security tests

### New tests to add:
1. **`test_crash_crypto.py`** — Fernet encrypt/decrypt round-trip, tamper detection, fallback test
2. **`test_ocr_cascade.py`** — Mock invoice image, confidence threshold, fallback trigger, degradation
3. **`test_local_report.py`** — Report generation from test DB, HTML format validation, SMTP (dry-run)
4. **`test_rust_extensions.py`** — HWID consistency, crypto round-trip, fallback to Python

### Validation gates:
1. Run `python archive/test_server.py` — must pass all 55 tests
2. Run `python archive/exhaustive_verify.py` — must pass 100% of checks
3. Run `python archive/test_ai_pipeline.py` — must pass (if Ollama running)
4. Run new test files — must pass
5. Verify `crash_reporter.py` installs via `sys.excepthook`
6. Verify `ocr_cascade.py` processes a mock invoice image end-to-end
7. Verify `local_daily_report.py` generates HTML email from test DB
8. Verify navigation drawer loads all 9 pages without errors
9. Verify `build_exe.py` runs successfully (PyInstaller builds)

---

## 7. Post-Implementation Updates

- Update `PROJECT_MAP.md` — Add new modules, update architecture diagram, mark milestones
- Update `VERIFICATION_CHECKLIST.md` — Add new visual and operational constraints
- Update `FLOW_LOGIC.md` — Document OCR cascade flow and crash encryption flow
- Update `AGENTS.md` — Add new commands (e.g., `test-ocr`, `test-report`)
- Update `README.md` — Add OCR, daily reports, Rust extensions documentation
- Ensure all new files are added to `PharmacyPro_Enterprise.spec` hiddenimports
- Ensure `--onefile` compatibility maintained throughout

---

## 8. Execution Order (Chronological)

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 7 → Phase 8 → Phase 6 → Phase 2.5
```

Rationale:
- Phase 1 (crypto) is independent and low-risk; do first to unblock Phase 6 (Rust crypto)
- Phase 2 (ORM) must come before Phase 7 (async) since async wraps the ORM functions
- Phase 3 (OCR) is high-value new feature; do before UI redesign so we can design the receive tab UI around it
- Phase 4 (daily report) is quick to implement and integrates with Settings; do before UI redesign
- Phase 5 (UI) is the biggest change; do after all data/backend changes are stable
- Phase 7 (async) wraps the ORM functions from Phase 2; comes after ORM is stable
- Phase 8 (i18n) touches all files; do last after all UI changes are settled
- Phase 6 (Rust) is last because it depends on Phase 1 (encryption) being defined and Phase 1's crypto_utils pattern

---

## 9. Success Metrics

1. **No regressions**: All 55 existing tests + 120+ verification checks pass
2. **Performance**: UI thread never blocks >0.1s for any DB operation (selective async)
3. **Encryption**: Crash payloads encrypted with Fernet; server decrypts successfully
4. **OCR**: Can extract medication names, quantities, batch numbers from a mock invoice image
5. **Email**: Daily sales report generates and sends (dry-run) with correct metrics
6. **UI**: Navigation drawer loads all 9 pages, no clipping, sidebar width ≥ 200px
7. **Rust**: `hw_client.generate_hwid()` produces same format as Python fallback
8. **Build**: `python build_exe.py` produces `--onefile` executable successfully
