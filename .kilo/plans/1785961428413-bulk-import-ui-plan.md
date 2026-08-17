# Implementation Plan — Bulk Import UI Tab

> **Status:** Planning — Implementation-Ready
> **Scope:** New module `archive/ui_bulk_import.py` + additive wiring in `archive/main_app.py` + i18n keys in `archive/locales/{en,de,es,fr,pt,ar}.json` + doc updates. NO backend files modified (`bulk_import_staging.py` is read-only).
> **Current date:** 2026-08-05 (per system clock)
> **Target Python:** 3.12+ (`X | None` type syntax already used in repo)
> **Plan file:** `.kilo/plans/1785961428413-bulk-import-ui-plan.md`

---

## 1. Context & Existing-Convention Baseline

The codebase is a monolithic CustomTkinter desktop suite in `archive/`. Phase-16 modules are wired via **monkey-patch** in `main_app.py:_wire_rx_extensions()` (NOT by editing `ui.py`/`ui_navigation.py`). This follows the exact same pattern as `ui_status_dashboard.py`, `ui_pos_terminal.py`, and `ui_supplier_order_management.py`.

### Proven patterns to reuse
| Concern | Source | Reuse approach |
|---|---|---|
| Tab wire-in order (icon → `tab_view.add` → `setup_*_tab(self)` → `on_tab_change` elif) | `main_app.py:58-183` | Identical additive insert. |
| `setup_*_tab(self)` body (pack frame into `self.tab_*`, store `self.*_frame`, expose refresh lambda) | `ui_pos_terminal.py:734-752`, `ui_status_dashboard.py:770-794` | Mirror exactly for bulk import. |
| `ttk.Treeview` with vertical `ttk.Scrollbar`, `show="headings"`, row striping | `ui_inventory_management.py:821-867` | Same shape; columns set dynamically from staged data. |
| Treeview theming | `ui_helpers.apply_treeview_style` | `from ui_helpers import apply_treeview_style`. |
| Dialog-free `messagebox`/error handling | `ui_pos_terminal.py:19`, `ui_pos_retail.py` | `from tkinter import ttk, messagebox, filedialog`. |
| i18n | `i18n.t(key, **kwargs)` | **All** user-facing strings via `i18n.t()`. English fallback via `_FALLBACK_LANG = "en"` (`i18n.py:22`). |

### Verified facts about `bulk_import_staging.py` (READ-ONLY, do not modify)
- `import_csv(path: str) -> StagingTable` and `import_excel(path: str, sheet=None) -> StagingTable`.
- Both call `table.auto_map_csv_headers()` internally, so `_column_map` is populated after load.
- `StagingTable.auto_map_csv_headers() -> dict[str,str]` is the **public** mapping getter (returns `{csv_header: known_field}`).
- `StagingTable.preview_rows(limit=5) -> list[dict]` (note: default 5 — caller must pass `20`).
- `StagingTable.columns`, `.rows`, `.row_count`, `.to_product_dicts()`.
- `commit_staged_products(table: StagingTable) -> dict` returns `{"added", "updated", "errors"}`.
- Imports `database` lazily inside `commit_staged_products`.

### Pre-existing tab wiring (already present, do NOT re-add)
- `main_app.py:123` already creates `self.tab_bulk_import = self.tab_view.add(i18n.t("bulk_import_title"))`.
- `main_app.py:79` already registers nav icon `"bulk_import_title" → "📥"`.
- `ui_enterprise_navigation.py:167-168` toolbar button already switches to `bulk_import_title`.
- i18n keys already present in **all 6** locale files: `bulk_import_title`, `bulk_import_subtitle`, `bulk_import_upload`, `bulk_import_mappings`, `bulk_import_preview`, `bulk_import_import`, `bulk_import_status`, `toolbar_bulk_import`.

### i18n gap analysis (must ADD 7 keys to all 6 locale files, en-first, English text)
These are **new** keys used by the new module. Existing bulk_import keys above are reused un-changed.

```
"bulk_import_select_file": "Select File (CSV/Excel)"
"bulk_import_no_file": "No file selected"
"bulk_import_invalid_format": "Please select a valid .csv or .xlsx file."
"bulk_import_empty_preview": "No data rows found in the selected file."
"bulk_import_no_mapping": "No file loaded yet."
"bulk_import_execute": "Execute Bulk Import"
"bulk_import_success": "Bulk import complete: {added} added, {updated} updated, {errors} error(s)."
```

---

## 2. Verifiable Goals (Success Metrics)

| # | Metric | How verified |
|---|---|---|
| G1 | `archive/ui_bulk_import.py` imports cleanly & `BulkImportFrame` + `setup_bulk_import_tab` exist | `python -c "import ui_bulk_import"` from `archive/` |
| G2 | `BulkImportFrame` builds without crash in a headless `CTk` root | `python -c "import customtkinter as ctk; r=ctk.CTk(); import ui_bulk_import as m; f=m.BulkImportFrame(r); f._build_ui()"` (uses `apply_treeview_style`) |
| G3 | `setup_bulk_import_tab` packs a frame into `self.tab_bulk_import` and sets `self.bulk_import_frame` + `self._refresh_bulk_import_tab` | Inspect via `inspect.getsource`/attribute check |
| G4 | `main_app._wire_rx_extensions` source references `setup_bulk_import_tab`, `tab_bulk_import`, `bulk_import_frame`, `.refresh()` | `inspect.getsource(main_app._wire_rx_extensions)` contains all substrings |
| G5 | No new deps; `customtkinter`/`tkinter`/`openpyxl`/`csv` already used in repo | N/A — all present |
| G6 | All 6 locale files remain valid JSON & contain all 7 new keys | `python -c "import json,glob;[json.load(open(f)) for f in glob.glob('archive/locales/*.json')]` + key check |
| G7 | No regression in existing Phase-16 wiring | Existing assertions in `test_phase16.py` still pass |

---

## 3. Step-by-Step Implementation

### Step 3.1 — Create `archive/ui_bulk_import.py`

Write the **complete** file below verbatim. No other edits to this file are needed.

```python
"""
ui_bulk_import.py — Bulk Import module for PharmacyPro.

Provides:
  - BulkImportFrame: CTkFrame with a file-selection area, a 20-row
    Treeview preview of staged data, header-to-product-field mapping
    confirmation, and an "Execute Bulk Import" button that commits the
    staged rows to the `products` table.
  - setup_bulk_import_tab(self): tab-setup function attached to PharmacyApp
    via main_app.py:_wire_rx_extensions().

Integrates with:
  - bulk_import_staging: StagingTable, import_csv, import_excel,
    commit_staged_products
  - ui_helpers.apply_treeview_style (shared Treeview theming)
  - i18n (all user-facing strings)
"""
import logging
from pathlib import Path

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog

import i18n
from ui_helpers import apply_treeview_style
from bulk_import_staging import (
    StagingTable,
    import_csv,
    import_excel,
    commit_staged_products,
)

log = logging.getLogger("ui_bulk_import")

_PREVIEW_LIMIT = 20
_FILETYPES = (
    ("CSV files", "*.csv"),
    ("Excel files", "*.xlsx"),
    ("All files", "*.*"),
)


class BulkImportFrame(ctk.CTkFrame):
    """Bulk import UI: select file -> stage -> preview -> commit."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._staging: StagingTable | None = None
        self._selected_path: str = ""

        self._build_ui()

    # ── UI construction ──

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # Header
        title = ctk.CTkLabel(
            self, text=i18n.t("bulk_import_title"),
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 5))

        subtitle = ctk.CTkLabel(
            self, text=i18n.t("bulk_import_subtitle"),
            font=ctk.CTkFont(size=12), text_color="#94a3b8",
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 15))

        # Top section — file selection area
        file_row = ctk.CTkFrame(self, fg_color="transparent")
        file_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 5))
        file_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            file_row, text=i18n.t("bulk_import_select_file"),
            command=self._on_select_file,
        ).grid(row=0, column=0, sticky="w")

        self._path_label = ctk.CTkLabel(
            file_row, text=i18n.t("bulk_import_no_file"),
            anchor="w", text_color="#94a3b8",
        )
        self._path_label.grid(row=0, column=1, sticky="ew", padx=(12, 0))

        # Middle section — preview grid
        preview_title = ctk.CTkLabel(
            self, text=i18n.t("bulk_import_preview"),
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        preview_title.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 5))

        tree_container = ctk.CTkFrame(self, fg_color="transparent")
        tree_container.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 10))
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            tree_container, show="headings", height=20,
        )
        apply_treeview_style(self._tree)
        self._tree.tag_configure("odd", background="#2D2D2D", foreground="#FFFFFF")
        self._tree.tag_configure("even", background="#1E1E1E", foreground="#FFFFFF")
        self._tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(
            tree_container, orient="vertical", command=self._tree.yview
        )
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns", padx=(0, 2))

        self.grid_rowconfigure(4, weight=1)

        # Bottom section — mapping confirmation + execute
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 20))
        bottom.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bottom, text=i18n.t("bulk_import_mappings"),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self._mapping_var = ctk.StringVar(value=i18n.t("bulk_import_no_mapping"))
        self._mapping_label = ctk.CTkLabel(
            bottom, textvariable=self._mapping_var,
            font=ctk.CTkFont(size=11), justify="left",
            text_color="#cbd5e1", wraplength=600,
        )
        self._mapping_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._execute_btn = ctk.CTkButton(
            bottom, text=i18n.t("bulk_import_execute"),
            command=self._on_execute_import,
        )
        self._execute_btn.grid(row=0, column=1, sticky="e", rowspan=2)

    # ── Event handlers ──

    def _on_select_file(self):
        path = filedialog.askopenfilename(
            title=i18n.t("bulk_import_select_file"),
            filetypes=_FILETYPES,
        )
        if not path:
            return
        self._selected_path = path
        self._path_label.configure(text=path)
        self._load_and_stage(path)

    def _load_and_stage(self, path: str):
        ext = Path(path).suffix.lower()
        self._staging = None
        self._clear_tree()
        self._execute_btn.configure(state="disabled")
        self._mapping_var.set(i18n.t("bulk_import_no_mapping"))
        try:
            if ext == ".csv":
                self._staging = import_csv(path)
            elif ext == ".xlsx":
                self._staging = import_excel(path)
            else:
                messagebox.showwarning(
                    i18n.t("bulk_import_title"),
                    i18n.t("bulk_import_invalid_format"),
                )
                return
        except Exception as exc:
            log.error("Failed to stage file %s: %s", path, exc)
            messagebox.showerror(i18n.t("bulk_import_title"), str(exc))
            self._staging = None
            return

        self._populate_tree(self._staging)
        self._display_mapping(self._staging)
        if self._staging.row_count:
            self._execute_btn.configure(state="normal")

    def _populate_tree(self, staging: StagingTable):
        tree = self._tree
        cols = staging.columns
        tree["columns"] = cols
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=120, minwidth=80, anchor="w", stretch=True)

        tree.delete(*tree.get_children())
        preview = staging.preview_rows(limit=_PREVIEW_LIMIT)[:_PREVIEW_LIMIT]
        for idx, row in enumerate(preview):
            values = [row.get(col, "") for col in cols]
            tree.insert(
                "", "end", values=values,
                tags=("even" if idx % 2 == 0 else "odd"),
            )

        if not cols:
            self._mapping_var.set(i18n.t("bulk_import_empty_preview"))

    def _clear_tree(self):
        self._tree.delete(*self._tree.get_children())
        self._tree["columns"] = ()

    def _display_mapping(self, staging: StagingTable):
        mapping = staging.auto_map_csv_headers()
        if not mapping:
            self._mapping_var.set(i18n.t("bulk_import_no_mapping"))
            return

        lines = [f"{hdr} → {field or '(unmapped)'}" for hdr, field in mapping.items()]
        self._mapping_var.set("\n".join(lines))

    def _on_execute_import(self):
        if self._staging is None or not self._staging.row_count:
            messagebox.showwarning(
                i18n.t("bulk_import_title"), i18n.t("bulk_import_no_file")
            )
            return

        try:
            result = commit_staged_products(self._staging)
        except Exception as exc:
            log.error("Bulk import commit failed: %s", exc)
            messagebox.showerror(i18n.t("bulk_import_title"), str(exc))
            return

        log.info("Bulk import committed: %s", result)
        messagebox.showinfo(
            i18n.t("bulk_import_title"),
            i18n.t("bulk_import_success").format(
                added=result.get("added", 0),
                updated=result.get("updated", 0),
                errors=result.get("errors", 0),
            ),
        )
        self._clear_table()

    def _clear_table(self):
        self._clear_tree()
        self._staging = None
        self._selected_path = ""
        self._path_label.configure(text=i18n.t("bulk_import_no_file"))
        self._mapping_var.set(i18n.t("bulk_import_no_mapping"))
        self._execute_btn.configure(state="disabled")

    # ── Public API ──

    def refresh(self):
        """Re-render the current staging preview — called on tab activation."""
        if self._staging is not None:
            self._populate_tree(self._staging)
            self._display_mapping(self._staging)


# ═════════════════════════════════════════════════════════════════════════════
#  Tab setup (called by main_app.py via monkey-patch)
# ═════════════════════════════════════════════════════════════════════════════

def setup_bulk_import_tab(self):
    """Create the Bulk Import tab content inside PharmacyApp.

    Expects main_app.py to have already created the tab container via:
        self.tab_bulk_import = self.tab_view.add(i18n.t("bulk_import_title"))

    After calling, the PharmacyApp will have:
        self.bulk_import_frame — BulkImportFrame instance
    """
    frame = BulkImportFrame(self.tab_bulk_import, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=4, pady=4)

    self.bulk_import_frame = frame
    self._refresh_bulk_import_tab = lambda: frame.refresh()

    return frame
```

**Layout summary (matches the task's 3-section requirement):**
- Top section (`grid row 2`): `CTkButton` "Select File (CSV/Excel)" + `CTkLabel` path.
- Middle section (`grid row 3-4`): `ttk.Treeview` (preview, first 20 rows) + vertical scrollbar.
- Bottom section (`grid row 5`): mapping confirmation `CTkLabel` + "Execute Bulk Import" `CTkButton`.
- Row 4 (tree container) is `weight=1` so the preview grid expands; tree container has `grid_rowconfigure(0, weight=1)`.

### Step 3.2 — Wire into `archive/main_app.py` (3 additive edits)

**Edit A — import** (after the inventory import at line 113):

Insert after:
```python
    from ui_inventory_management import setup_inventory_management_tab
```
the line:
```python
    from ui_bulk_import import setup_bulk_import_tab
```

**Edit B — setup call** (after the inventory setup call at line 141):

Insert after:
```python
        setup_inventory_management_tab(self)
```
the line:
```python
        setup_bulk_import_tab(self)
```

**Edit C — `bulk_import_title` branch in `_patched_on_tab_change`** (after the inventory `elif` block, lines 179-181):

Insert after:
```python
        elif current == i18n.t("inventory_mgmt_title"):
            if hasattr(self, "inventory_mgmt_frame"):
                self.inventory_mgmt_frame.refresh()
```
the block:
```python
        elif current == i18n.t("bulk_import_title"):
            if hasattr(self, "bulk_import_frame"):
                self.bulk_import_frame.refresh()
```

### Step 3.3 — Add 7 i18n keys to all 6 locale files

In each of `archive/locales/{en,de,es,fr,pt,ar}.json`, insert these 7 keys immediately after the existing `"bulk_import_status": "Import Status",` line (each file already has that exact line followed by `"toolbar_pos":`). Non-English files use English text, consistent with the existing (already-English) bulk_import block in those files.

```json
    "bulk_import_select_file": "Select File (CSV/Excel)",
    "bulk_import_no_file": "No file selected",
    "bulk_import_invalid_format": "Please select a valid .csv or .xlsx file.",
    "bulk_import_empty_preview": "No data rows found in the selected file.",
    "bulk_import_no_mapping": "No file loaded yet.",
    "bulk_import_execute": "Execute Bulk Import",
    "bulk_import_success": "Bulk import complete: {added} added, {updated} updated, {errors} error(s).",
```

The exact `oldString`→`newString` per file (insertion anchor identical across all six):

- `oldString`:
```
    "bulk_import_status": "Import Status",
    "toolbar_pos": "POS",
```
- `newString`:
```
    "bulk_import_status": "Import Status",
    "bulk_import_select_file": "Select File (CSV/Excel)",
    "bulk_import_no_file": "No file selected",
    "bulk_import_invalid_format": "Please select a valid .csv or .xlsx file.",
    "bulk_import_empty_preview": "No data rows found in the selected file.",
    "bulk_import_no_mapping": "No file loaded yet.",
    "bulk_import_execute": "Execute Bulk Import",
    "bulk_import_success": "Bulk import complete: {added} added, {updated} updated, {errors} error(s).",
    "toolbar_pos": "POS",
```

### Step 3.4 — Documentation updates

**`archive/FLOW_LOGIC.md`** (§11, the Bulk Import bullet, currently says "WIRING GAP"): replace the trailing `**WIRING GAP:** ...` sentence with:
> `ui_bulk_import.py` provides `BulkImportFrame` (file selection → `StagingTable` via `import_csv`/`import_excel` → 20-row `ttk.Treeview` preview → mapping confirmation → `commit_staged_products()` with `messagebox.showinfo` success + table clear). Wired into `main_app.py:_wire_rx_extensions()` via `setup_bulk_import_tab(self)` (packs into `self.tab_bulk_import`, sets `self.bulk_import_frame`) and a `bulk_import_title` refresh branch in `_patched_on_tab_change`. 7 new i18n keys added to all locale files.

**`PROJECT_MAP.md`**:
1. Update the Phase 16 milestone row (line 431) status from `Partially Verified (bulk import UI wiring incomplete — see ORPHANS)` to `Verified (bulk import UI wired)`.
2. Add a Phase-16 Files row in the table (after `bulk_import_staging.py`, line 444):
   `| ui_bulk_import.py | BulkImportFrame: file-select / 20-row Treeview preview / mapping / commit + setup_bulk_import_tab() | ~230 |`
3. Move the "Bulk Import tab is empty" row from `ORPHANS & PENDING` → `Active TODO Items` to a closed state, or delete it (it is now resolved). Replace it with: `| Bulk Import UI | Complete | 2026-08-05 |` under a new `### Completed` sub-section, or simply remove the row since `PROJECT_MAP.md` milestone row already tracks it.

---

## 4. Failure Modes & Edge Cases Handled

| Scenario | Behavior |
|---|---|
| User clicks "Execute" before selecting a file | `self._staging is None` → `messagebox.showwarning` ("No file selected"); no DB call. |
| File has no data rows (only headers) | `_populate_tree` clears tree; `row_count == 0` keeps Execute button disabled; mapping shows unmapped/empty. |
| Unsupported extension (e.g. `.xls`, `.txt`) | `messagebox.showwarning` "Please select a valid .csv or .xlsx file."; staging stays `None`. |
| `import_excel`/`import_csv` raises (corrupt file) | `log.error` + `messagebox.showerror` with exception text; staging stays `None`; no crash. |
| Duplicate/missing `internal_unique_barcode` on commit | Handled inside `commit_staged_products` (logs + counts errors). UI just surfaces the `errors` count in the success dialog. |
| Treeview columns vary per file | Columns rebuilt via `tree["columns"] = cols` each load; `_clear_tree` resets to `()`. |
| Tab re-activated while data staged | `refresh()` re-renders the existing staging preview (no re-read from DB). |
| `apply_treeview_style` import missing | `ui_helpers` is a stable shared module already imported by `ui_pos_terminal`/`ui_inventory_management` — no risk. |

## 5. Non-Goals / Scope Guardrails

- No new dependencies (csv/openpyxl/tkinter/ctk already in repo).
- Do NOT modify `bulk_import_staging.py`, `database.py`, `db.py`, or `ui.py`/`ui_navigation.py`.
- Do NOT add extra columns/fields beyond what `StagingTable` exposes.
- No speculative features (no "auto-download sample CSV", no per-row editor).

## 6. Verification Checklist (run after implementation)

```bash
cd /d "E:\my progam pharmacy\archive"
python -c "import ui_bulk_import; print(hasattr(ui_bulk_import,'BulkImportFrame'), hasattr(ui_bulk_import,'setup_bulk_import_tab'))"
python -c "import json,glob; [json.load(open(f)) for f in glob.glob('locales/*.json')]; print('locale JSON OK')"
python -c "import inspect, main_app; s=inspect.getsource(main_app._wire_rx_extensions); assert 'setup_bulk_import_tab' in s; assert 'bulk_import_frame' in s; print('wiring OK')"
python -m pytest -q test_phase16.py            # no regression (>=74 existing tests)
```

G1–G7 above are the acceptance gates; do not consider complete until all pass and `PROJECT_MAP.md` "Verified" status + doc updates are applied.
