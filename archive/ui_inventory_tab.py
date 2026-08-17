import customtkinter as ctk
from tkinter import ttk, messagebox
from tkinter import filedialog
import threading
import os
from datetime import date, timedelta

import database
import barcode_logic
import excel_handler
from ui_helpers import apply_treeview_style
import audit_log

# RBAC middleware (authz imports only `database`; no UI import cycle).
import authz
import auth_session


# ═════════════════════════════════════════════════════════════════════════════
#  Import Wizard Modal
# ═════════════════════════════════════════════════════════════════════════════

class ImportWizardModal(ctk.CTkToplevel):
    """Smart Mapping Wizard for Excel imports.
    Analyzes Excel headers vs DB schema, lets user configure the mapping,
    then calls execute_import() with the final column_map.
    """

    def __init__(self, master, file_path, excel_headers, row_count, on_confirm):
        super().__init__(master)
        self.file_path = file_path
        self.excel_headers = excel_headers
        self.row_count = row_count
        self.on_confirm = on_confirm  # callback(column_map, default_values)

        self.title("Import Mapping Wizard")
        self.geometry("680x560")
        self.resizable(False, False)
        self.grab_set()

        # Auto-map on init
        self._auto_mapping, self._unmatched = excel_handler.auto_map_headers(excel_headers)

        # State: for each DB field, the user's chosen Excel col index (or None)
        self._field_vars = {}  # db_field_key -> (combo_var, combo_widget)
        self._default_entries = {}  # db_field_key -> entry widget
        self._unmatched_toggles = []  # [(idx, header, toggle_var)]

        self._build_ui()

    def _build_ui(self):
        # ── Header info ──────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=15, pady=(12, 4))
        ctk.CTkLabel(
            hdr,
            text=f"File: {self.file_path.split('/')[-1].split(chr(92))[-1]}   |   "
                 f"{len(self.excel_headers)} columns   |   {self.row_count} data rows",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8",
        ).pack(anchor="w")

        ctk.CTkLabel(
            self,
            text="Map each database field to an Excel column, or provide a default value.",
            font=ctk.CTkFont(size=11), text_color="#64748b",
        ).pack(anchor="w", padx=15, pady=(0, 6))

        # ── Scrollable area ──────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", height=320)
        scroll.pack(fill="both", expand=True, padx=15, pady=(0, 8))
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)
        scroll.grid_columnconfigure(2, weight=0)

        row_idx = 0

        # ── Section: Required DB Fields ──────────────────────────────────
        ctk.CTkLabel(
            scroll, text="Database Fields",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#3b82f6",
        ).grid(row=row_idx, column=0, columnspan=3, sticky="w", pady=(4, 6))
        row_idx += 1

        col_headers = [""] + [f"Col {i+1}" for i in range(len(self.excel_headers))]
        for ci, ch in enumerate(["Field", "Map to Excel Column", "Default Value"]):
            ctk.CTkLabel(
                scroll, text=ch,
                font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8",
            ).grid(row=row_idx, column=ci, sticky="w", padx=(8, 4))
        row_idx += 1

        excel_col_labels = [f"{i+1}: {h}" for i, h in enumerate(self.excel_headers)]
        none_label = "-- None (use default) --"
        combo_values = [none_label] + excel_col_labels

        for db_key, info in excel_handler.DB_FIELDS.items():
            req_mark = " *" if info["required"] else ""
            ctk.CTkLabel(
                scroll, text=info["label"] + req_mark,
                font=ctk.CTkFont(size=12, weight="bold" if info["required"] else "normal"),
            ).grid(row=row_idx, column=0, sticky="w", padx=(8, 4), pady=3)

            var = ctk.StringVar(value=none_label)
            if db_key in self._auto_mapping:
                ci = self._auto_mapping[db_key]
                var.set(excel_col_labels[ci])

            combo = ctk.CTkComboBox(
                scroll, values=combo_values, variable=var,
                width=220, state="readonly",
            )
            combo.grid(row=row_idx, column=1, sticky="w", padx=4, pady=3)

            default_val = excel_handler.DB_FIELDS[db_key]["default"]
            entry = ctk.CTkEntry(
                scroll, width=140,
                placeholder_text=f"Default: {default_val}" if default_val else "Default value",
            )
            entry.grid(row=row_idx, column=2, sticky="w", padx=4, pady=3)
            if default_val:
                entry.insert(0, default_val)

            self._field_vars[db_key] = (var, combo)
            self._default_entries[db_key] = entry
            row_idx += 1

        # ── Section: Unmatched Excel Columns ─────────────────────────────
        if self._unmatched:
            row_idx += 1
            ctk.CTkLabel(
                scroll, text="Unmatched Excel Columns (optional)",
                font=ctk.CTkFont(size=13, weight="bold"), text_color="#f59e0b",
            ).grid(row=row_idx, column=0, columnspan=3, sticky="w", pady=(10, 6))
            row_idx += 1

            for ci, ch in enumerate(["Column", "Header", "Action"]):
                ctk.CTkLabel(
                    scroll, text=ch,
                    font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8",
                ).grid(row=row_idx, column=ci, sticky="w", padx=(8, 4))
            row_idx += 1

            for col_idx, header in self._unmatched:
                ctk.CTkLabel(
                    scroll, text=f"Col {col_idx+1}",
                    font=ctk.CTkFont(size=11),
                ).grid(row=row_idx, column=0, sticky="w", padx=(8, 4), pady=2)

                ctk.CTkLabel(
                    scroll, text=header, font=ctk.CTkFont(size=11),
                ).grid(row=row_idx, column=1, sticky="w", padx=4, pady=2)

                toggle_var = ctk.StringVar(value="Ignore")
                toggle = ctk.CTkSegmentedButton(
                    scroll, values=["Ignore", "Create Field"],
                    variable=toggle_var, width=160,
                    font=ctk.CTkFont(size=10),
                )
                toggle.grid(row=row_idx, column=2, sticky="w", padx=4, pady=2)
                self._unmatched_toggles.append((col_idx, header, toggle_var))
                row_idx += 1

        # ── Bottom buttons ───────────────────────────────────────────────
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkLabel(
            btn_bar,
            text="* Required fields must be mapped or have a default value.",
            font=ctk.CTkFont(size=10), text_color="#64748b",
        ).pack(side="left")

        ctk.CTkButton(
            btn_bar, text="Cancel", width=90, fg_color="#6c757d", hover_color="#5a6268",
            command=self.destroy,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_bar, text="Confirm Import", width=130, fg_color="#28a745", hover_color="#218838",
            command=self._on_confirm,
        ).pack(side="right")

    def _on_confirm(self):
        column_map = {}
        default_values = {}
        errors = []

        for db_key, (var, _) in self._field_vars.items():
            label = var.get()
            if label.startswith("--"):
                # Not mapped — check if default is set or field is not required
                default = self._default_entries[db_key].get().strip()
                if excel_handler.DB_FIELDS[db_key]["required"] and not default:
                    errors.append(
                        f"'{excel_handler.DB_FIELDS[db_key]['label']}' is required "
                        f"but not mapped and has no default value."
                    )
                else:
                    default_values[db_key] = default
            else:
                # Extract column index from label like "3: Vendor"
                col_idx = int(label.split(":")[0]) - 1
                column_map[db_key] = col_idx

        if errors:
            messagebox.showwarning(
                "Mapping Errors",
                "Please fix the following:\n\n" + "\n".join(errors),
                parent=self,
            )
            return

        # Validate required fields are covered
        for db_key, info in excel_handler.DB_FIELDS.items():
            if info["required"] and db_key not in column_map and db_key not in default_values:
                messagebox.showwarning(
                    "Missing Required Field",
                    f"'{info['label']}' must be mapped to an Excel column or have a default value.",
                    parent=self,
                )
                return

        self.destroy()
        self.on_confirm(column_map, default_values)


# ═════════════════════════════════════════════════════════════════════════════
#  Label Print Dialog
# ═════════════════════════════════════════════════════════════════════════════

class LabelPrintDialog(ctk.CTkToplevel):
    """Dialog to specify label quantity and generate/preview labels for a product."""

    def __init__(self, master, product_name, price, internal_barcode, expiry="", mfg=""):
        super().__init__(master)
        self.product_name = product_name
        self.price = price
        self.internal_barcode = internal_barcode
        self.expiry = expiry
        self.mfg = mfg
        self.generated_files = []

        self.title("Print Labels")
        self.geometry("380x280")
        self.resizable(False, False)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Generate Barcode Labels",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(16, 4))

        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=20, pady=(8, 4))
        ctk.CTkLabel(info_frame, text=f"Product: {self.product_name}",
                     font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(info_frame, text=f"Barcode: {self.internal_barcode}",
                     font=ctk.CTkFont(size=11), text_color="#A0A0A0", anchor="w").pack(anchor="w")
        ctk.CTkLabel(info_frame, text=f"Price: {self.price}",
                     font=ctk.CTkFont(size=11), text_color="#A0A0A0", anchor="w").pack(anchor="w")

        qty_frame = ctk.CTkFrame(self, fg_color="transparent")
        qty_frame.pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkLabel(qty_frame, text="Label Quantity:", font=ctk.CTkFont(size=13)).pack(side="left")
        self.qty_var = ctk.StringVar(value="1")
        qty_entry = ctk.CTkEntry(qty_frame, width=80, textvariable=self.qty_var)
        qty_entry.pack(side="left", padx=(8, 0))

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="#10B981")
        self.status_label.pack(pady=(8, 4))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(8, 16))

        ctk.CTkButton(
            btn_frame, text="Cancel", width=90, fg_color="#6c757d", hover_color="#5a6268",
            command=self.destroy,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame, text="Open Label Designer", width=150, fg_color="#17a2b8", hover_color="#138496",
            command=self._open_designer,
        ).pack(side="right")

        ctk.CTkButton(
            btn_frame, text="Generate Labels", width=130, fg_color="#3B82F6", hover_color="#2563EB",
            command=self._generate_labels,
        ).pack(side="right")

    def _generate_labels(self):
        try:
            qty = int(self.qty_var.get())
            if qty < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Quantity", "Please enter a positive integer.", parent=self)
            return

        price_val = 0.0
        try:
            price_val = self.master.currency.parse(self.price)
        except (ValueError, TypeError):
            pass

        self.generated_files = []
        for i in range(qty):
            try:
                path = barcode_logic.create_label(price_val, self.internal_barcode)
                if path:
                    self.generated_files.append(path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to generate label {i+1}:\n{e}", parent=self)
                return

        self.status_label.configure(text=f"Generated {qty} label(s) successfully!")

        if self.generated_files:
            if messagebox.askyesno("Labels Ready",
                                   f"{qty} label(s) generated.\nOpen the label folder?",
                                   parent=self):
                labels_dir = os.path.dirname(self.generated_files[0])
                try:
                    if os.name == "nt":
                        os.startfile(labels_dir)
                    else:
                        import subprocess
                        subprocess.Popen(["xdg-open", labels_dir])
                except Exception:
                    pass

    def _open_designer(self):
        try:
            price_val = 0.0
            try:
                price_val = self.master.currency.parse(self.price)
            except (ValueError, TypeError):
                pass
            barcode_logic.open_label_engine(
                "NEW", self.internal_barcode,
                name=self.product_name, price=str(price_val),
                expiry=self.expiry, manufacture=self.mfg,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Label Designer:\n{e}", parent=self)


# ═════════════════════════════════════════════════════════════════════════════
#  Inventory Tab Setup
# ═════════════════════════════════════════════════════════════════════════════

def setup_inventory_tab(self):
    self.tab_inventory.grid_rowconfigure(0, weight=0)
    self.tab_inventory.grid_rowconfigure(1, weight=0)
    self.tab_inventory.grid_rowconfigure(2, weight=0)
    self.tab_inventory.grid_rowconfigure(3, weight=1)
    self.tab_inventory.grid_columnconfigure(0, weight=1)
    self.tab_inventory.grid_columnconfigure(1, weight=0)

    ctk.CTkLabel(self.tab_inventory, text="Inventory Browser",
                 font=ctk.CTkFont(size=24, weight="bold"), text_color="#f0f0f0").grid(
        row=0, column=0, padx=20, pady=(20, 8), sticky="w")

    # ── Expiry alert bar ─────────────────────────────────────────────────
    alert_frame = ctk.CTkFrame(self.tab_inventory, fg_color="transparent")
    alert_frame.grid(row=1, column=0, padx=10, pady=(10, 0), sticky="ew")
    alert_frame.grid_columnconfigure((0, 1, 2), weight=1)

    self.alert_30 = ctk.CTkLabel(alert_frame, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#dc3545")
    self.alert_30.grid(row=0, column=0, padx=5, sticky="w")
    self.alert_60 = ctk.CTkLabel(alert_frame, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#fd7e14")
    self.alert_60.grid(row=0, column=1, padx=5, sticky="w")
    self.alert_90 = ctk.CTkLabel(alert_frame, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#ffc107")
    self.alert_90.grid(row=0, column=2, padx=5, sticky="w")

    self._current_sort = 'expiry_date'
    self._sort_reverse = False
    self._imported_batch_ids = set()
    self._row_counter = 0
    self._inventory_filter = "All"

    # ── Filter toggle ──
    filter_frame = ctk.CTkFrame(self.tab_inventory, fg_color="transparent")
    filter_frame.grid(row=2, column=0, padx=10, pady=(4, 0), sticky="ew")

    ctk.CTkLabel(filter_frame, text="Filter:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(10, 6))
    self._inventory_filter_var = ctk.StringVar(value="All")
    filter_toggle = ctk.CTkSegmentedButton(
        filter_frame,
        values=["All", "Low Stock", "Expiring Soon"],
        variable=self._inventory_filter_var,
        command=lambda v: _on_inventory_filter_change(self, v),
        width=260,
    )
    filter_toggle.pack(side="left")

    # ── Search + action buttons ──────────────────────────────────────────
    search_frame = ctk.CTkFrame(self.tab_inventory, fg_color="transparent")
    search_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
    search_frame.grid_columnconfigure(0, weight=1)

    self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Search by name, int. barcode, mfg. barcode, vendor, or expiry...")
    self.search_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
    self.search_entry.bind("<Return>", self.perform_search)

    ctk.CTkButton(search_frame, text="Search", width=90, command=self.perform_search).grid(row=0, column=1)
    ctk.CTkButton(search_frame, text="Clear", width=80, fg_color="#6c757d", hover_color="#5a6268", command=self.load_inventory).grid(row=0, column=2, padx=(6, 0))
    ctk.CTkButton(search_frame, text="Sell", width=80, fg_color="#c42b1c", hover_color="#9e2216", command=self._send_to_checkout).grid(row=0, column=3, padx=(6, 0))
    ctk.CTkButton(search_frame, text="Edit", width=80, fg_color="#e67e22", hover_color="#cf6d17", command=authz.require_permission("inventory.manage")(self._edit_batch)).grid(row=0, column=4, padx=(6, 0))
    ctk.CTkButton(search_frame, text="Delete", width=80, fg_color="#DC2626", hover_color="#991B1B", command=authz.require_permission("inventory.manage")(self._delete_batch)).grid(row=0, column=5, padx=(6, 0))
    ctk.CTkButton(search_frame, text="Print Label", width=90, fg_color="#17a2b8", hover_color="#138496", command=self._print_label_for_selected).grid(row=0, column=6, padx=(6, 0))
    ctk.CTkButton(search_frame, text="Import", width=80, fg_color="#6f42c1", hover_color="#5a32a3", command=lambda: _import_excel(self)).grid(row=0, column=7, padx=(6, 0))
    ctk.CTkButton(search_frame, text="Export", width=80, fg_color="#0d6efd", hover_color="#0b5ed7", command=lambda: _export_excel(self)).grid(row=0, column=8, padx=(6, 0))

    sort_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
    sort_frame.grid(row=0, column=9, sticky="e", padx=(8, 0))
    ctk.CTkLabel(sort_frame, text="Sort:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 2))
    self.sort_var = ctk.StringVar(value="Expiry Date")
    sort_toggle = ctk.CTkSegmentedButton(
        sort_frame,
        values=["Expiry Date", "Mfg Date", "Name", "Vendor"],
        variable=self.sort_var,
        command=self._on_sort_change,
        width=260,
    )
    sort_toggle.pack(side="left")

    # ── Treeview with professional styling ───────────────────────────────
    columns = ("Name", "Price", "Int. Barcode", "Vendor", "Expiry", "Mfg Date", "Mfg Barcode")
    self.tree_inv = ttk.Treeview(self.tab_inventory, columns=columns, show="headings")
    apply_treeview_style(self.tree_inv)

    # Tag config for striping + import highlight
    self._tree_tags_configured = False

    # Column config: strings left, numbers right, dates center
    col_cfg = {
        "Name":         {"width": 170, "anchor": "w"},
        "Price":        {"width": 75,  "anchor": "e"},
        "Int. Barcode": {"width": 120, "anchor": "w"},
        "Vendor":       {"width": 110, "anchor": "w"},
        "Expiry":       {"width": 95,  "anchor": "center"},
        "Mfg Date":     {"width": 95,  "anchor": "center"},
        "Mfg Barcode":  {"width": 120, "anchor": "w"},
    }
    for col in columns:
        cfg = col_cfg[col]
        self.tree_inv.heading(col, text=col, command=lambda c=col: _header_sort(self, c))
        self.tree_inv.column(col, width=cfg["width"], anchor=cfg["anchor"])

    self.tree_inv.grid(row=3, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))

    scrollbar = ttk.Scrollbar(self.tab_inventory, orient="vertical", command=self.tree_inv.yview)
    self.tree_inv.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=3, column=1, sticky="ns", pady=(0, 10))

    _configure_tree_tags(self)
    self.load_inventory()


# ═════════════════════════════════════════════════════════════════════════════
#  Treeview Tags (striping + import highlight)
# ═════════════════════════════════════════════════════════════════════════════

def _configure_tree_tags(self):
    if self._tree_tags_configured:
        return
    self.tree_inv.tag_configure("odd", background="#2b2b2b")
    self.tree_inv.tag_configure("even", background="#333340")
    self.tree_inv.tag_configure("imported", background="#1a3a2a")
    self._tree_tags_configured = True


def _get_row_tag(self):
    self._row_counter += 1
    return "even" if self._row_counter % 2 == 0 else "odd"


# ═════════════════════════════════════════════════════════════════════════════
#  Column Sorting
# ═════════════════════════════════════════════════════════════════════════════

_COL_SORT_KEYS = {
    "Name":         lambda v: v[0].lower(),
    "Price":        lambda v: currency.parse(v[1]) if v[1] else 0.0,
    "Int. Barcode": lambda v: v[2].lower(),
    "Vendor":       lambda v: v[3].lower(),
    "Expiry":       lambda v: v[4] if v[4] and v[4] != "N/A" else "9999",
    "Mfg Date":     lambda v: v[5] if v[5] and v[5] != "N/A" else "0000",
    "Mfg Barcode":  lambda v: v[6].lower(),
}


def _header_sort(self, col):
    if self._current_sort == col:
        self._sort_reverse = not self._sort_reverse
    else:
        self._current_sort = col
        self._sort_reverse = False

    items = []
    for iid in self.tree_inv.get_children(""):
        vals = self.tree_inv.item(iid, "values")
        items.append((iid, vals))

    key_fn = _COL_SORT_KEYS.get(col, lambda v: v[0].lower())
    items.sort(key=lambda x: key_fn(x[1]), reverse=self._sort_reverse)

    for iid, _ in items:
        self.tree_inv.move(iid, "", "end")

    # Re-apply striping after sort
    self._row_counter = 0
    for iid in self.tree_inv.get_children(""):
        tag = _get_row_tag(self)
        existing_tags = list(self.tree_inv.item(iid, "tags"))
        is_imported = "imported" in existing_tags
        new_tags = [tag]
        if is_imported:
            new_tags.append("imported")
        self.tree_inv.item(iid, tags=tuple(new_tags))

    # Update heading arrow indicator
    for c in self.tree_inv["columns"]:
        txt = self.tree_inv.heading(c)["text"].rstrip(" \u25b2\u25bc")
        if c == col:
            arrow = " \u25b2" if not self._sort_reverse else " \u25bc"
            self.tree_inv.heading(c, text=txt + arrow)
        else:
            self.tree_inv.heading(c, text=txt)


# ═════════════════════════════════════════════════════════════════════════════
#  Data Loading
# ═════════════════════════════════════════════════════════════════════════════

def _refresh_expiry_bar(self):
    from datetime import date, timedelta
    batches = database.get_expiring_batches()
    today = date.today()
    c30 = c60 = c90 = 0
    for exp_date, _row in batches:
        delta = (exp_date - today).days
        if delta <= 30:
            c30 += 1
        elif delta <= 60:
            c60 += 1
        elif delta <= 90:
            c90 += 1
    self.alert_30.configure(text=f"<=30d: {c30}" if c30 else "")
    self.alert_60.configure(text=f"<=60d: {c60}" if c60 else "")
    self.alert_90.configure(text=f"<=90d: {c90}" if c90 else "")


def load_inventory(self):
    self.search_entry.delete(0, 'end')
    for item in self.tree_inv.get_children():
        self.tree_inv.delete(item)

    self._refresh_expiry_bar()
    _configure_tree_tags(self)
    self._row_counter = 0

    batches = database.get_all_in_stock_batches(sort_by=self._current_sort)
    current_filter = getattr(self, '_inventory_filter', 'All')

    config = barcode_logic.load_config()
    low_stock_threshold = config.get("low_stock_threshold", 5)

    today = date.today()
    expiring_cutoff = today + timedelta(days=30)

    for batch in batches:
        batch_id, name, price, mfg_barcode, int_barcode, status, expiry, mfg_date, vendor = batch

        if current_filter == "Low Stock":
            name_count = sum(1 for b in database.get_all_in_stock_batches() if b[1] == name)
            if name_count > low_stock_threshold:
                continue
        elif current_filter == "Expiring Soon":
            if not expiry or expiry == "N/A":
                continue
            try:
                exp_date = date.fromisoformat(expiry.replace('/', '-'))
                if exp_date > expiring_cutoff:
                    continue
            except (ValueError, TypeError):
                continue

        expiry_text = expiry if expiry else "N/A"
        mfg_text = mfg_date if mfg_date else "N/A"
        tag = "imported" if batch_id in self._imported_batch_ids else _get_row_tag(self)
        self.tree_inv.insert("", "end", iid=f"batch_{batch_id}", values=(
            name, self.currency.fmt(price), int_barcode, vendor or "N/A",
            expiry_text, mfg_text, mfg_barcode
        ), tags=(tag,))


def _on_inventory_filter_change(self, choice):
    self._inventory_filter = choice
    self.load_inventory()


def _on_sort_change(self, choice):
    sort_map = {
        "Expiry Date": "expiry_date",
        "Mfg Date":    "manufacture_date",
        "Name":        "name",
        "Vendor":      "vendor",
    }
    self._current_sort = sort_map.get(choice, "expiry_date")
    self._sort_reverse = False
    self.load_inventory()


def perform_search(self, event=None):
    query = self.search_entry.get().strip()
    if not query:
        self.load_inventory()
        return

    exact = database.get_product_by_internal_barcode(query)
    if not exact:
        exact = database.get_product_by_barcode(query)
    if exact and event:
        self.load_inventory()
        batch_iid = f"batch_{exact[0]}"
        if batch_iid in self.tree_inv.get_children(""):
            self.tree_inv.selection_set(batch_iid)
            self.tree_inv.focus(batch_iid)
            self.tree_inv.see(batch_iid)
        return

    for item in self.tree_inv.get_children():
        self.tree_inv.delete(item)

    self._row_counter = 0
    batches = database.search_all_batches(query)
    for batch in batches:
        batch_id, name, price, mfg_barcode, int_barcode, status, expiry, mfg_date, vendor = batch
        expiry_text = expiry if expiry else "N/A"
        mfg_text = mfg_date if mfg_date else "N/A"
        tag = "imported" if batch_id in self._imported_batch_ids else _get_row_tag(self)
        self.tree_inv.insert("", "end", iid=f"batch_{batch_id}", values=(
            name, self.currency.fmt(price), int_barcode, vendor or "N/A",
            expiry_text, mfg_text, mfg_barcode
        ), tags=(tag,))


# ═════════════════════════════════════════════════════════════════════════════
#  Existing Actions (unchanged logic)
# ═════════════════════════════════════════════════════════════════════════════

def _send_to_checkout(self):
    selected = self.tree_inv.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select a batch to sell.")
        return
    iid = selected[0]
    if not iid.startswith("batch_"):
        messagebox.showwarning("Warning", "Please select a batch row.")
        return
    values = self.tree_inv.item(iid, 'values')
    product_name = values[0]
    price_str = self.currency.parse(values[1])
    int_barcode = values[2]
    vendor = values[3] if values[3] and values[3] != "N/A" else ""
    expiry_date = values[4] if values[4] else "N/A"
    try:
        price = float(price_str)
    except ValueError:
        messagebox.showerror("Error", "Could not parse price from the selected batch.")
        return
    product_row = database.get_product_by_internal_barcode(int_barcode)
    if not product_row:
        messagebox.showwarning("Out of Stock", f"'{product_name}' (batch {int_barcode or 'N/A'}) is no longer in stock.")
        return

    for item in self.pos_cart:
        if int_barcode in item.get("internal_barcodes", []):
            messagebox.showwarning("Already in Cart",
                f"'{product_name}' (batch {int_barcode}) is already in the cart.",
                parent=self.tab_inventory)
            return

    for item in self.pos_cart:
        if item["product_name"] == product_name:
            item["internal_barcodes"].append(int_barcode)
            item["quantity"] += 1
            self._refresh_cart_treeview()
            self.tab_view.set("Checkout")
            return
    self.pos_cart.append({
        "product_name": product_name, "quantity": 1, "price_at_time": price,
        "internal_barcodes": [int_barcode], "vendor": vendor, "expiry_date": expiry_date,
    })
    self._refresh_cart_treeview()
    self.tab_view.set("Checkout")


def _edit_batch(self):
    if not authz.check_permission(auth_session.current_user_id(), "inventory.manage"):
        authz.access_denied("inventory.manage")
        return
    selected = self.tree_inv.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select a batch to edit.")
        return
    iid = selected[0]
    if not iid.startswith("batch_"):
        messagebox.showwarning("Warning", "Please select a batch row to edit.")
        return
    batch_id = int(iid[len("batch_"):])
    row = database.get_product_by_id(batch_id)
    if not row:
        messagebox.showerror("Error", "Could not locate this batch in the database.")
        return
    from ui_modals import EditBatchDialog
    EditBatchDialog(self, row)

def _delete_batch(self):
    if not authz.check_permission(auth_session.current_user_id(), "inventory.manage"):
        authz.access_denied("inventory.manage")
        return
    selected = self.tree_inv.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select a batch to delete.")
        return
    iid = selected[0]
    if not iid.startswith("batch_"):
        return
    batch_id = int(iid[len("batch_"):])
    
    dialog = ctk.CTkInputDialog(text="Enter Admin PIN to confirm deletion:", title="Admin Validation")
    pin = dialog.get_input()
    
    if pin == "1234":
        try:
            conn = database.sqlite3.connect(database.get_db_path())
            cursor = conn.cursor()
            cursor.execute("DELETE FROM products WHERE id = ?", (batch_id,))
            conn.commit()
            conn.close()
            audit_log.log_action("DELETE_BATCH", f"Batch ID {batch_id} manually deleted by admin.")
            messagebox.showinfo("Deleted", "Batch successfully deleted.")
            self.load_inventory()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete:\n{str(e)}")
    else:
        if pin is not None:
            messagebox.showerror("Error", "Invalid PIN.")


def _print_label_for_selected(self):
    selected = self.tree_inv.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select a batch to print labels.")
        return
    iid = selected[0]
    if not iid.startswith("batch_"):
        messagebox.showwarning("Warning", "Please select a batch row.")
        return
    values = self.tree_inv.item(iid, 'values')
    name = values[0]
    price_str = values[1]
    barcode = values[2]
    expiry_raw = values[4] if values[4] != "N/A" else ""
    mfg_raw = values[5] if values[5] != "N/A" else ""
    dialog = LabelPrintDialog(self, name, price_str, barcode, expiry_raw, mfg_raw)
    dialog.grab_set()


def open_label_for_selected(self):
    selected = self.tree_inv.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select a batch to print its label.")
        return
    iid = selected[0]
    if not iid.startswith("batch_"):
        messagebox.showwarning("Warning", "Please select a batch row to print.")
        return
    values = self.tree_inv.item(iid, 'values')
    name = values[0]
    price_str = self.currency.parse(values[1])
    barcode = values[2]
    expiry_raw = values[4] if values[4] != "N/A" else ""
    mfg_raw = values[5] if values[5] != "N/A" else ""
    from ui_modals import LabelDesignerPopup
    designer = LabelDesignerPopup(self, name, price_str, barcode, expiry_raw, mfg_raw)
    designer.grab_set()


# ═════════════════════════════════════════════════════════════════════════════
#  Excel Import with Wizard
# ═════════════════════════════════════════════════════════════════════════════

def _import_excel(self):
    file_path = filedialog.askopenfilename(
        title="Import Inventory from Excel",
        filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
    )
    if not file_path:
        return

    try:
        headers, row_count = excel_handler.read_excel_headers(file_path)
    except Exception as e:
        messagebox.showerror("Error", f"Could not read Excel file:\n{e}")
        return

    if not headers:
        messagebox.showwarning("Empty File", "No columns found in the Excel file.")
        return

    def on_wizard_confirm(column_map, default_values):
        loading = ctk.CTkToplevel(self)
        loading.title("Importing...")
        loading.geometry("320x100")
        loading.resizable(False, False)
        loading.grab_set()
        ctk.CTkLabel(
            loading, text="Importing inventory...\nPlease wait.",
            font=ctk.CTkFont(size=14),
        ).pack(expand=True)

        def on_done(count, errors):
            loading.after(0, loading.destroy)
            if errors:
                msg = f"Imported {count} product(s).\n\nErrors:\n" + "\n".join(errors[:10])
                if len(errors) > 10:
                    msg += f"\n...and {len(errors) - 10} more."
                self.after(0, lambda: messagebox.showwarning("Import Complete", msg))
            else:
                self.after(0, lambda: messagebox.showinfo("Import Complete", f"Successfully imported {count} product(s)."))
            self.after(100, lambda: _refresh_after_import(self))

        excel_handler.execute_import(file_path, column_map, default_values=default_values, on_complete=on_done)

    ImportWizardModal(self, file_path, headers, row_count, on_wizard_confirm)


def _refresh_after_import(self):
    """Refresh inventory and tag newly imported rows as highlighted."""
    # Get current batch IDs before reload
    old_ids = {int(iid[len("batch_"):]) for iid in self.tree_inv.get_children("") if iid.startswith("batch_")}

    self.load_inventory()

    # Find new IDs and tag them
    new_ids = {int(iid[len("batch_"):]) for iid in self.tree_inv.get_children("") if iid.startswith("batch_")}
    freshly_imported = new_ids - old_ids
    self._imported_batch_ids.update(freshly_imported)

    for iid in self.tree_inv.get_children(""):
        if iid.startswith("batch_"):
            bid = int(iid[len("batch_"):])
            if bid in freshly_imported:
                self.tree_inv.item(iid, tags=("imported",))

    # Auto-clear highlight after 8 seconds
    def clear_highlights():
        for iid in self.tree_inv.get_children(""):
            if iid.startswith("batch_"):
                bid = int(iid[len("batch_"):])
                if bid in freshly_imported:
                    existing = list(self.tree_inv.item(iid, "tags"))
                    if "imported" in existing:
                        existing.remove("imported")
                    if not existing:
                        existing = [_get_row_tag(self)]
                    self.tree_inv.item(iid, tags=tuple(existing))
        self._imported_batch_ids -= freshly_imported

    self.after(8000, clear_highlights)


# ═════════════════════════════════════════════════════════════════════════════
#  Excel Export
# ═════════════════════════════════════════════════════════════════════════════

def _export_excel(self):
    file_path = filedialog.asksaveasfilename(
        title="Export Inventory to Excel",
        defaultextension=".xlsx",
        filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        initialfile=f"inventory_{date.today().strftime('%Y%m%d')}.xlsx",
    )
    if not file_path:
        return

    loading = ctk.CTkToplevel(self)
    loading.title("Exporting...")
    loading.geometry("320x100")
    loading.resizable(False, False)
    loading.grab_set()
    ctk.CTkLabel(loading, text="Exporting inventory...\nPlease wait.", font=ctk.CTkFont(size=14)).pack(expand=True)

    def on_done(output_path):
        loading.after(0, loading.destroy)
        if output_path:
            self.after(0, lambda: messagebox.showinfo("Export Complete", f"Inventory exported to:\n{output_path}"))
        else:
            self.after(0, lambda: messagebox.showerror("Export Error", "Failed to export inventory."))

    excel_handler.export_inventory(file_path, on_complete=on_done)
