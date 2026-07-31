import customtkinter as ctk
from tkinter import ttk, messagebox
import os
import json

import database
import barcode_logic
import audit_log
import i18n
from ui_helpers import apply_treeview_style
import backup


class AuditLogViewer(ctk.CTkToplevel):
    """Searchable Treeview for inspecting system audit logs."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Audit Trail Viewer")
        self.geometry("800x500")
        self.resizable(True, True)
        self.grab_set()
        self._build_ui()
        self._load_logs()

    def _build_ui(self):
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(search_frame, text="Search:", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(0, 6))
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(search_frame, width=300, textvariable=self.search_var)
        self.search_entry.pack(side="left", padx=(0, 8))
        self.search_entry.bind("<Return>", lambda _: self._load_logs())

        ctk.CTkButton(search_frame, text="Search", width=80, command=self._load_logs).pack(side="left", padx=(0, 4))
        ctk.CTkButton(search_frame, text="Clear", width=80, fg_color="#6c757d", hover_color="#5a6268",
                      command=self._clear_search).pack(side="left")

        self.count_label = ctk.CTkLabel(search_frame, text="", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        self.count_label.pack(side="right")

        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        columns = ("Timestamp", "Action", "User/PIN", "Details")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20)
        apply_treeview_style(self.tree)

        self.tree.heading("Timestamp", text="Timestamp")
        self.tree.heading("Action", text="Action")
        self.tree.heading("User/PIN", text="User/PIN")
        self.tree.heading("Details", text="Details")

        self.tree.column("Timestamp", width=150, anchor="w")
        self.tree.column("Action", width=140, anchor="w")
        self.tree.column("User/PIN", width=80, anchor="center")
        self.tree.column("Details", width=400, anchor="w")

        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _load_logs(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        query = self.search_var.get().strip()
        logs = audit_log.get_logs(limit=500, search_query=query)

        for idx, (timestamp, action, user_pin, details) in enumerate(logs):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(timestamp, action, user_pin or "", details), tags=(tag,))

        self.tree.tag_configure("even", background="#2b2b2b")
        self.tree.tag_configure("odd", background="#333340")
        self.count_label.configure(text=f"{len(logs)} log(s) found")

    def _clear_search(self):
        self.search_var.set("")
        self._load_logs()


def setup_settings_tab(self):
    self.tab_settings.grid_columnconfigure((0, 1), weight=1)

    title_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("settings"), font=ctk.CTkFont(size=24, weight="bold"))
    title_label.grid(row=0, column=0, columnspan=3, padx=20, pady=(20, 30))

    config = barcode_logic.load_config()

    name_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("pharmacy_name") + ":", anchor="w")
    name_label.grid(row=1, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_name_entry = ctk.CTkEntry(self.tab_settings, width=300)
    self.set_name_entry.insert(0, config.get("pharmacy_name", "My Pharmacy"))
    self.set_name_entry.grid(row=1, column=1, padx=(10, 100), pady=10, sticky="w")

    addr_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("supplier_address") + ":", anchor="w")
    addr_label.grid(row=2, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_address_entry = ctk.CTkEntry(self.tab_settings, width=300)
    self.set_address_entry.insert(0, config.get("address", ""))
    self.set_address_entry.grid(row=2, column=1, padx=(10, 100), pady=10, sticky="w")

    phone_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("contact_phone") + ":", anchor="w")
    phone_label.grid(row=3, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_phone_entry = ctk.CTkEntry(self.tab_settings, width=300)
    self.set_phone_entry.insert(0, config.get("phone", ""))
    self.set_phone_entry.grid(row=3, column=1, padx=(10, 100), pady=10, sticky="w")

    tax_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("tax") + " (%):", anchor="w")
    tax_label.grid(row=4, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_tax_entry = ctk.CTkEntry(self.tab_settings, width=300)
    self.set_tax_entry.insert(0, str(config.get("tax_rate", 0.0)))
    self.set_tax_entry.grid(row=4, column=1, padx=(10, 100), pady=10, sticky="w")

    font_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("pharmacy_name") + " " + i18n.t("font_size") + ":", anchor="w")
    font_label.grid(row=5, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_font_entry = ctk.CTkEntry(self.tab_settings, width=300)
    self.set_font_entry.insert(0, str(config.get("font_size", 20)))
    self.set_font_entry.grid(row=5, column=1, padx=(10, 100), pady=10, sticky="w")

    self.set_price_var = ctk.BooleanVar(value=config.get("include_price", True))
    self.set_price_check = ctk.CTkCheckBox(self.tab_settings, text=i18n.t("include_price_on_label"), variable=self.set_price_var)
    self.set_price_check.grid(row=6, column=0, columnspan=3, pady=20)

    db_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("database_path") + ":", anchor="w")
    db_label.grid(row=7, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_db_entry = ctk.CTkEntry(self.tab_settings, width=300)
    self.set_db_entry.insert(0, config.get("db_path", "pharmacy.db"))
    self.set_db_entry.grid(row=7, column=1, padx=(10, 10), pady=10, sticky="w")

    browse_btn = ctk.CTkButton(self.tab_settings, text=i18n.t("browse"), width=100, command=self.browse_db_path)
    browse_btn.grid(row=7, column=2, padx=(0, 100), sticky="w")

    # ── PostgreSQL Multi-PC Section ────────────────────────────────────
    pg_header = ctk.CTkFrame(self.tab_settings, fg_color="#1a1a2e", corner_radius=8)
    pg_header.grid(row=11, column=0, columnspan=3, padx=100, pady=(15, 5), sticky="ew")

    ctk.CTkLabel(pg_header, text="  POSTGRESQL MULTI-PC SYNC",
                 font=ctk.CTkFont(size=11, weight="bold"),
                 text_color="#a78bfa", anchor="w").pack(fill="x", padx=10, pady=6)

    pg_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
    pg_frame.grid(row=12, column=0, columnspan=3, padx=100, pady=(0, 10), sticky="ew")
    pg_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(pg_frame, text="Database URL:", anchor="w", width=120).grid(
        row=0, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_db_url_entry = ctk.CTkEntry(pg_frame, width=400,
                                         placeholder_text="postgresql://user:pass@host:5432/pharmacy")
    self.set_db_url_entry.grid(row=0, column=1, columnspan=2, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text="Host:", anchor="w", width=120).grid(
        row=1, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_host = ctk.CTkEntry(pg_frame, width=200, placeholder_text="localhost")
    self.set_pg_host.grid(row=1, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text="Port:", anchor="w", width=120).grid(
        row=2, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_port = ctk.CTkEntry(pg_frame, width=100, placeholder_text="5432")
    self.set_pg_port.grid(row=2, column=1, pady=4, sticky="w")

    ctk.CTkLabel(pg_frame, text="Database:", anchor="w", width=120).grid(
        row=3, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_dbname = ctk.CTkEntry(pg_frame, width=200, placeholder_text="pharmacy")
    self.set_pg_dbname.grid(row=3, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text="User:", anchor="w", width=120).grid(
        row=4, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_user = ctk.CTkEntry(pg_frame, width=200, placeholder_text="postgres")
    self.set_pg_user.grid(row=4, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text="Password:", anchor="w", width=120).grid(
        row=5, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_pass = ctk.CTkEntry(pg_frame, width=200, show="*",
                                    placeholder_text="(leave blank for no password)")
    self.set_pg_pass.grid(row=5, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text="SSL Mode:", anchor="w", width=120).grid(
        row=6, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_ssl = ctk.CTkComboBox(pg_frame, width=200, state="normal",
                                       values=["prefer", "require", "disable", "verify-full"])
    self.set_pg_ssl.grid(row=6, column=1, pady=4, sticky="w")
    self.set_pg_ssl.set("prefer")

    pg_btn_row = ctk.CTkFrame(pg_frame, fg_color="transparent")
    pg_btn_row.grid(row=7, column=0, columnspan=3, pady=(8, 0), sticky="w")

    ctk.CTkButton(pg_btn_row, text="Test Connection", width=140,
                  fg_color="#059669", hover_color="#047857",
                  command=self._test_pg_connection).pack(side="left", padx=(0, 8))
    ctk.CTkButton(pg_btn_row, text="Build URL from Fields", width=160,
                  fg_color="#6366f1", hover_color="#4f46e5",
                  command=self._build_pg_url).pack(side="left", padx=(0, 8))

    self._pg_status_label = ctk.CTkLabel(pg_btn_row, text="",
                                          font=ctk.CTkFont(size=11),
                                          text_color="#94a3b8")
    self._pg_status_label.pack(side="left")

    # Load saved PostgreSQL fields from config
    self._load_pg_config()

    expiry_alarm_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("expiry_alarm_threshold"), anchor="w")
    expiry_alarm_label.grid(row=8, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_expiry_alarm_var = ctk.StringVar(value=str(config.get("expiry_alarm_days", 50)))
    self.set_expiry_alarm_entry = ctk.CTkEntry(self.tab_settings, width=300,
                                               textvariable=self.set_expiry_alarm_var)
    self.set_expiry_alarm_entry.grid(row=8, column=1, padx=(10, 100), pady=10, sticky="w")

    exclude_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("exclude_from_expiry_alerts"), anchor="w")
    exclude_label.grid(row=9, column=0, padx=(100, 10), pady=(10, 0), sticky="w")
    self.set_ignore_combo = ctk.CTkComboBox(self.tab_settings, width=300,
                                             state="normal",
                                             values=database.get_unique_product_names())
    self.set_ignore_combo.grid(row=9, column=1, padx=(10, 10), pady=(10, 0), sticky="w")
    self.btn_ignore_add = ctk.CTkButton(self.tab_settings, text="Add", width=60,
                                        command=self._add_ignore_product)
    self.btn_ignore_add.grid(row=9, column=2, padx=(0, 100), sticky="w", pady=(10, 0))

    ignore_list_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
    ignore_list_frame.grid(row=10, column=0, columnspan=3, padx=(100, 100), pady=(0, 10), sticky="ew")

    self.ignore_list_tree = ttk.Treeview(ignore_list_frame, columns=("Product Name",),
                                         show="headings", height=4)
    apply_treeview_style(self.ignore_list_tree)
    self.ignore_list_tree.heading("Product Name", text="Product Name")
    self.ignore_list_tree.column("Product Name", width=350, anchor="w")
    self.ignore_list_tree.pack(side="left", fill="both", expand=True)

    ignore_scroll = ttk.Scrollbar(ignore_list_frame, orient="vertical",
                                   command=self.ignore_list_tree.yview)
    self.ignore_list_tree.configure(yscroll=ignore_scroll.set)
    ignore_scroll.pack(side="left", fill="y")

    self.btn_ignore_remove = ctk.CTkButton(ignore_list_frame, text="Remove", width=70,
                                            fg_color="#dc3545", hover_color="#a71d2a",
                                            command=self._remove_ignore_product)
    self.btn_ignore_remove.pack(side="left", padx=(8, 0))

    self._refresh_ignore_list()

    save_btn = ctk.CTkButton(self.tab_settings, text=i18n.t("save_settings"), command=self.save_settings, height=40, font=ctk.CTkFont(size=16))
    save_btn.grid(row=17, column=0, columnspan=3, pady=20)

    backup_btn = ctk.CTkButton(self.tab_settings, text=i18n.t("backup_database"), command=self.backup_database_gui, height=40, font=ctk.CTkFont(size=16), fg_color="#17a2b8", hover_color="#138496")
    backup_btn.grid(row=18, column=0, columnspan=3, pady=10)

    audit_btn = ctk.CTkButton(self.tab_settings, text="View Audit Logs", command=self._open_audit_log_viewer, height=40, font=ctk.CTkFont(size=16), fg_color="#7c3aed", hover_color="#6d28d9")
    audit_btn.grid(row=19, column=0, columnspan=3, pady=10)

    role_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("user_role") + ":", anchor="w")
    role_label.grid(row=14, column=0, padx=(100, 10), pady=10, sticky="w")
    self.role_var = ctk.StringVar(value=i18n.t("admin"))
    self.role_segmented = ctk.CTkSegmentedButton(
        self.tab_settings, values=[i18n.t("admin"), i18n.t("user")], variable=self.role_var,
        command=self._on_role_change
    )
    self.role_segmented.grid(row=14, column=1, padx=(10, 100), pady=10, sticky="w")

    self.user_role = i18n.t("admin")
    self._update_role_controls()

    lang_label = ctk.CTkLabel(self.tab_settings, text=i18n.t("language") + ":", anchor="w")
    lang_label.grid(row=15, column=0, padx=(100, 10), pady=10, sticky="w")
    available_langs = i18n.get_available_languages()
    lang_display = [name for _, name in available_langs]
    self._lang_codes = [code for code, _ in available_langs]
    current_lang_name = dict(available_langs).get(i18n.get_language(), "English")
    self.lang_var = ctk.StringVar(value=current_lang_name)
    self.lang_dropdown = ctk.CTkOptionMenu(
        self.tab_settings, variable=self.lang_var, values=lang_display,
        command=self._on_language_change, width=200
    )
    self.lang_dropdown.grid(row=15, column=1, padx=(10, 100), pady=10, sticky="w")


def _on_language_change(self, choice):
    available = i18n.get_available_languages()
    code_map = {name: code for code, name in available}
    new_code = code_map.get(choice)
    if new_code and new_code != i18n.get_language():
        i18n.set_language(new_code)
        messagebox.showinfo(
            i18n.t("language_changed"),
            i18n.t("restart_required")
        )


def browse_db_path(self):
    folder = ctk.filedialog.askdirectory(title="Select Database Folder")
    if folder:
        db_path = os.path.join(folder, "pharmacy.db")
        self.set_db_entry.delete(0, 'end')
        self.set_db_entry.insert(0, db_path)


def _on_role_change(self, value):
    self.user_role = value
    self._update_role_controls()


def _update_role_controls(self):
    is_admin = self.user_role == i18n.t("admin")
    try:
        if hasattr(self, 'btn_sell'):
            self.btn_sell.configure(state="normal" if is_admin else "disabled")
        if hasattr(self, 'btn_print'):
            self.btn_print.configure(state="normal" if is_admin else "disabled")
        if hasattr(self, 'btn_edit_batch'):
            self.btn_edit_batch.configure(state="normal" if is_admin else "disabled")
    except Exception:
        pass


def backup_database_gui(self):
    try:
        backup_path = backup.create_backup()
        if backup_path:
            messagebox.showinfo("Backup Success", f"Database successfully backed up to:\n{backup_path}")
        else:
            messagebox.showerror("Backup Failed", "Database file not found.")
    except Exception as e:
        messagebox.showerror("Backup Failed", str(e))


def _open_audit_log_viewer(self):
    AuditLogViewer(self)


def _add_ignore_product(self):
    name = self.set_ignore_combo.get().strip()
    if not name:
        messagebox.showwarning("Warning", "Please enter or select a product name.")
        return
    config = barcode_logic.load_config()
    ignore_list = config.get("expiry_ignore_list", [])
    if not isinstance(ignore_list, list):
        ignore_list = []
    if name.lower() in [n.lower() for n in ignore_list]:
        messagebox.showinfo("Info", f"'{name}' is already in the ignore list.")
        return
    ignore_list.append(name)
    with open(barcode_logic.CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    self.set_ignore_combo.set("")
    self._refresh_ignore_list()


def _remove_ignore_product(self):
    selected = self.ignore_list_tree.selection()
    if not selected:
        return
    for item_id in selected:
        name = self.ignore_list_tree.item(item_id, "values")[0]
        config = barcode_logic.load_config()
        ignore_list = config.get("expiry_ignore_list", [])
        ignore_list = [n for n in ignore_list if n != name]
        config["expiry_ignore_list"] = ignore_list
        with open(barcode_logic.CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    self._refresh_ignore_list()


def _refresh_ignore_list(self):
    for item in self.ignore_list_tree.get_children():
        self.ignore_list_tree.delete(item)
    config = barcode_logic.load_config()
    ignore_list = config.get("expiry_ignore_list", [])
    if not isinstance(ignore_list, list):
        ignore_list = []
    for name in ignore_list:
        self.ignore_list_tree.insert("", "end", values=(name,))
    if hasattr(self, 'set_ignore_combo'):
        current_names = database.get_unique_product_names()
        self.set_ignore_combo.configure(values=current_names)


def _load_pg_config(self):
    """Load saved PostgreSQL connection fields from config.json."""
    config = barcode_logic.load_config()
    self.set_db_url_entry.delete(0, "end")
    self.set_db_url_entry.insert(0, config.get("database_url", ""))
    self.set_pg_host.delete(0, "end")
    self.set_pg_host.insert(0, config.get("pg_host", "localhost"))
    self.set_pg_port.delete(0, "end")
    self.set_pg_port.insert(0, config.get("pg_port", "5432"))
    self.set_pg_dbname.delete(0, "end")
    self.set_pg_dbname.insert(0, config.get("pg_dbname", "pharmacy"))
    self.set_pg_user.delete(0, "end")
    self.set_pg_user.insert(0, config.get("pg_user", "postgres"))
    self.set_pg_pass.delete(0, "end")
    self.set_pg_pass.insert(0, config.get("pg_password", ""))
    ssl_val = config.get("pg_ssl", "prefer")
    self.set_pg_ssl.set(ssl_val)


def _build_pg_url(self):
    """Construct a PostgreSQL URL from the individual fields."""
    host = self.set_pg_host.get().strip() or "localhost"
    port = self.set_pg_port.get().strip() or "5432"
    dbname = self.set_pg_dbname.get().strip() or "pharmacy"
    user = self.set_pg_user.get().strip() or "postgres"
    password = self.set_pg_pass.get().strip()
    ssl = self.set_pg_ssl.get().strip() or "prefer"

    if password:
        url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode={ssl}"
    else:
        url = f"postgresql://{user}@{host}:{port}/{dbname}?sslmode={ssl}"

    self.set_db_url_entry.delete(0, "end")
    self.set_db_url_entry.insert(0, url)
    self._pg_status_label.configure(text="URL built from fields.", text_color="#22c55e")


def _test_pg_connection(self):
    """Test the PostgreSQL connection using the current URL field."""
    import db as _db
    url = self.set_db_url_entry.get().strip()
    if not url:
        self._pg_status_label.configure(text="Enter a Database URL first.", text_color="#ef4444")
        return
    result = _db.test_connection(url)
    if result["ok"]:
        self._pg_status_label.configure(
            text=f"Connected to {result['backend']}!", text_color="#22c55e")
    else:
        self._pg_status_label.configure(
            text=f"Failed: {result['error'][:60]}", text_color="#ef4444")


def save_settings(self):
    new_name = self.set_name_entry.get().strip()
    new_address = self.set_address_entry.get().strip()
    new_phone = self.set_phone_entry.get().strip()
    new_tax_str = self.set_tax_entry.get().strip()
    new_font_str = self.set_font_entry.get().strip()
    include_price = self.set_price_var.get()
    new_db_path = self.set_db_entry.get().strip()

    if not new_name:
        messagebox.showerror("Error", "Pharmacy Name cannot be empty.")
        return

    try:
        new_tax_rate = float(new_tax_str)
        if new_tax_rate < 0 or new_tax_rate > 100:
            raise ValueError
    except (ValueError, TypeError):
        messagebox.showerror("Error", "Tax rate must be a number between 0 and 100.")
        return

    try:
        new_font = int(new_font_str)
        if new_font <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Error", "Font size must be a positive integer.")
        return

    try:
        new_alarm_days = int(self.set_expiry_alarm_var.get().strip())
        if new_alarm_days <= 0:
            raise ValueError
    except (ValueError, TypeError):
        messagebox.showerror("Error", "Expiry alarm threshold must be a positive integer.")
        return

    config = barcode_logic.load_config()
    new_config = {
        "pharmacy_name": new_name,
        "address": new_address,
        "phone": new_phone,
        "tax_rate": new_tax_rate,
        "font_size": new_font,
        "include_price": include_price,
        "db_path": new_db_path or "pharmacy.db",
        "expiry_alarm_days": new_alarm_days,
        "expiry_ignore_list": config.get("expiry_ignore_list", []),
        "database_url": self.set_db_url_entry.get().strip(),
        "pg_host": self.set_pg_host.get().strip(),
        "pg_port": self.set_pg_port.get().strip(),
        "pg_dbname": self.set_pg_dbname.get().strip(),
        "pg_user": self.set_pg_user.get().strip(),
        "pg_password": self.set_pg_pass.get().strip(),
        "pg_ssl": self.set_pg_ssl.get().strip(),
    }

    try:
        with open(barcode_logic.CONFIG_FILE, "w") as f:
            json.dump(new_config, f, indent=4)

        # Reconnect to database (switches to PostgreSQL if URL was set)
        db_url = new_config.get("database_url", "")
        if db_url:
            import db as _db
            _db.reconnect_db(db_url)

        database.init_db()

        self.load_inventory()
        self.load_sales_report()
        self.load_templates_grid()
        self.refresh_add_tab_templates()

        messagebox.showinfo("Success", "Settings saved successfully! Connected to database.")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save config:\n{str(e)}")
