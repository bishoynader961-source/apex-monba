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

        lines = [f"{hdr} -> {field or '(unmapped)'}" for hdr, field in mapping.items()]
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
