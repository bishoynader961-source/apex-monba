import customtkinter as ctk
from tkinter import ttk, messagebox
import os
import json
import threading

import database
import barcode_logic
import audit_log
import auth_session
import authz
import i18n
from ui_helpers import apply_treeview_style
import backup
import local_daily_report
import ui_tooltip

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
    scroll = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
    scroll.pack(fill="both", expand=True)
    scroll.grid_columnconfigure((0, 1), weight=1)

    title_label = ctk.CTkLabel(scroll, text=i18n.t("settings"), font=ctk.CTkFont(size=24, weight="bold"))
    title_label.grid(row=0, column=0, columnspan=3, padx=20, pady=(20, 30))

    config = barcode_logic.load_config()

    name_label = ctk.CTkLabel(scroll, text=i18n.t("pharmacy_name") + ":", anchor="w")
    name_label.grid(row=1, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_name_entry = ctk.CTkEntry(scroll, width=300)
    self.set_name_entry.insert(0, config.get("pharmacy_name", "My Pharmacy"))
    self.set_name_entry.grid(row=1, column=1, padx=(10, 100), pady=10, sticky="w")

    addr_label = ctk.CTkLabel(scroll, text=i18n.t("supplier_address") + ":", anchor="w")
    addr_label.grid(row=2, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_address_entry = ctk.CTkEntry(scroll, width=300)
    self.set_address_entry.insert(0, config.get("address", ""))
    self.set_address_entry.grid(row=2, column=1, padx=(10, 100), pady=10, sticky="w")

    phone_label = ctk.CTkLabel(scroll, text=i18n.t("contact_phone") + ":", anchor="w")
    phone_label.grid(row=3, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_phone_entry = ctk.CTkEntry(scroll, width=300)
    self.set_phone_entry.insert(0, config.get("phone", ""))
    self.set_phone_entry.grid(row=3, column=1, padx=(10, 100), pady=10, sticky="w")

    tax_label = ctk.CTkLabel(scroll, text=i18n.t("tax") + " (%):", anchor="w")
    tax_label.grid(row=4, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_tax_entry = ctk.CTkEntry(scroll, width=300)
    self.set_tax_entry.insert(0, str(config.get("tax_rate", 0.0)))
    self.set_tax_entry.grid(row=4, column=1, padx=(10, 100), pady=10, sticky="w")

    font_label = ctk.CTkLabel(scroll, text=i18n.t("pharmacy_name") + " " + i18n.t("font_size") + ":", anchor="w")
    font_label.grid(row=5, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_font_entry = ctk.CTkEntry(scroll, width=300)
    self.set_font_entry.insert(0, str(config.get("font_size", 20)))
    self.set_font_entry.grid(row=5, column=1, padx=(10, 100), pady=10, sticky="w")

    self.set_price_var = ctk.BooleanVar(value=config.get("include_price", True))
    self.set_price_check = ctk.CTkCheckBox(scroll, text=i18n.t("include_price_on_label"), variable=self.set_price_var)
    self.set_price_check.grid(row=6, column=0, columnspan=3, pady=20)

    db_label = ctk.CTkLabel(scroll, text=i18n.t("database_path") + ":", anchor="w")
    db_label.grid(row=7, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_db_entry = ctk.CTkEntry(scroll, width=300)
    self.set_db_entry.insert(0, config.get("db_path", "pharmacy.db"))
    self.set_db_entry.grid(row=7, column=1, padx=(10, 10), pady=10, sticky="w")

    browse_btn = ctk.CTkButton(scroll, text=i18n.t("browse"), width=100, command=self.browse_db_path)
    browse_btn.grid(row=7, column=2, padx=(0, 100), sticky="w")

    # ── PostgreSQL Multi-PC Section ────────────────────────────────────
    pg_header = ctk.CTkFrame(scroll, fg_color="#1a1a2e", corner_radius=8)
    pg_header.grid(row=11, column=0, columnspan=3, padx=100, pady=(15, 5), sticky="ew")

    ctk.CTkLabel(pg_header, text=i18n.t("pg_sync_section"),
                 font=ctk.CTkFont(size=11, weight="bold"),
                 text_color="#a78bfa", anchor="w").pack(fill="x", padx=10, pady=6)

    pg_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    pg_frame.grid(row=12, column=0, columnspan=3, padx=100, pady=(0, 10), sticky="ew")
    pg_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(pg_frame, text=i18n.t("database_url"), anchor="w", width=120).grid(
        row=0, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_db_url_entry = ctk.CTkEntry(pg_frame, width=400,
                                         placeholder_text="postgresql://user:pass@host:5432/pharmacy")
    self.set_db_url_entry.grid(row=0, column=1, columnspan=2, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text=i18n.t("host"), anchor="w", width=120).grid(
        row=1, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_host = ctk.CTkEntry(pg_frame, width=200, placeholder_text="localhost")
    self.set_pg_host.grid(row=1, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text=i18n.t("smtp_port"), anchor="w", width=120).grid(
        row=2, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_port = ctk.CTkEntry(pg_frame, width=100, placeholder_text="5432")
    self.set_pg_port.grid(row=2, column=1, pady=4, sticky="w")

    ctk.CTkLabel(pg_frame, text=i18n.t("database"), anchor="w", width=120).grid(
        row=3, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_dbname = ctk.CTkEntry(pg_frame, width=200, placeholder_text="pharmacy")
    self.set_pg_dbname.grid(row=3, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text=i18n.t("pg_user"), anchor="w", width=120).grid(
        row=4, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_user = ctk.CTkEntry(pg_frame, width=200, placeholder_text="postgres")
    self.set_pg_user.grid(row=4, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text=i18n.t("smtp_password"), anchor="w", width=120).grid(
        row=5, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_pass = ctk.CTkEntry(pg_frame, width=200, show="*",
                                    placeholder_text="(leave blank for no password)")
    self.set_pg_pass.grid(row=5, column=1, pady=4, sticky="ew")

    ctk.CTkLabel(pg_frame, text=i18n.t("ssl_mode"), anchor="w", width=120).grid(
        row=6, column=0, padx=(0, 8), pady=4, sticky="w")
    self.set_pg_ssl = ctk.CTkComboBox(pg_frame, width=200, state="normal",
                                       values=["prefer", "require", "disable", "verify-full"])
    self.set_pg_ssl.grid(row=6, column=1, pady=4, sticky="w")
    self.set_pg_ssl.set("prefer")

    pg_btn_row = ctk.CTkFrame(pg_frame, fg_color="transparent")
    pg_btn_row.grid(row=7, column=0, columnspan=3, pady=(8, 0), sticky="w")

    ctk.CTkButton(pg_btn_row, text=i18n.t("test_connection"), width=140,
                  fg_color="#059669", hover_color="#047857",
                  command=self._test_pg_connection).pack(side="left", padx=(0, 8))
    ctk.CTkButton(pg_btn_row, text=i18n.t("build_url_from_fields"), width=160,
                  fg_color="#6366f1", hover_color="#4f46e5",
                  command=self._build_pg_url).pack(side="left", padx=(0, 8))

    self._pg_status_label = ctk.CTkLabel(pg_btn_row, text="",
                                          font=ctk.CTkFont(size=11),
                                          text_color="#94a3b8")
    self._pg_status_label.pack(side="left")

    # Load saved PostgreSQL fields from config
    self._load_pg_config()

    expiry_alarm_label = ctk.CTkLabel(scroll, text=i18n.t("expiry_alarm_threshold"), anchor="w")
    expiry_alarm_label.grid(row=8, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_expiry_alarm_var = ctk.StringVar(value=str(config.get("expiry_alarm_days", 50)))
    self.set_expiry_alarm_entry = ctk.CTkEntry(scroll, width=300,
                                               textvariable=self.set_expiry_alarm_var)
    self.set_expiry_alarm_entry.grid(row=8, column=1, padx=(10, 100), pady=10, sticky="w")

    exclude_label = ctk.CTkLabel(scroll, text=i18n.t("exclude_from_expiry_alerts"), anchor="w")
    exclude_label.grid(row=9, column=0, padx=(100, 10), pady=(10, 0), sticky="w")
    self.set_ignore_combo = ctk.CTkComboBox(scroll, width=300,
                                             state="normal",
                                             values=database.get_unique_product_names())
    self.set_ignore_combo.grid(row=9, column=1, padx=(10, 10), pady=(10, 0), sticky="w")
    self.btn_ignore_add = ctk.CTkButton(scroll, text="Add", width=60,
                                        command=self._add_ignore_product)
    self.btn_ignore_add.grid(row=9, column=2, padx=(0, 100), sticky="w", pady=(10, 0))

    ignore_list_frame = ctk.CTkFrame(scroll, fg_color="transparent")
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

    # Signed-in identity (replaces the fake Admin/User segmented toggle).
    try:
        _uid = auth_session.current_user_id()
        _role_name = ""
        _user_name = ""
        if _uid is not None:
            _rid = database.get_user_role_id(_uid)
            for _r in database.get_roles():
                if _r[0] == _rid:
                    _role_name = _r[1]
                    break
            _user_name = database.get_user_display(_uid)
        signed_in = ctk.CTkLabel(
            scroll, text=i18n.t("signed_in_as", _user_name or "", _role_name or ""),
            font=ctk.CTkFont(size=12), text_color="#94a3b8",
        )
        signed_in.grid(row=14, column=0, columnspan=3, padx=(100, 10), pady=(10, 0), sticky="w")
    except Exception:
        signed_in = None

    lang_label = ctk.CTkLabel(scroll, text=i18n.t("language") + ":", anchor="w")
    lang_label.grid(row=15, column=0, padx=(100, 10), pady=10, sticky="w")
    available_langs = i18n.get_available_languages()
    lang_display = [name for _, name in available_langs]
    self._lang_codes = [code for code, _ in available_langs]
    current_lang_name = dict(available_langs).get(i18n.get_language(), "English")
    self.lang_var = ctk.StringVar(value=current_lang_name)
    self.lang_dropdown = ctk.CTkOptionMenu(
        scroll, variable=self.lang_var, values=lang_display,
        command=self._on_language_change, width=200
    )
    self.lang_dropdown.grid(row=15, column=1, padx=(10, 100), pady=10, sticky="w")

    # ── Administrative controls (gated by settings.manage) ───────────────
    # Cashiers (settings.view only) keep a lightweight Save for language/theme;
    # the full admin controls (save-all, backup, audit, email send) live in
    # admin_frame, which is hidden without settings.manage. (D8)
    _is_admin = authz.check_permission(auth_session.current_user_id(), "settings.manage")

    if not _is_admin:
        basic_save_btn = ctk.CTkButton(
            scroll, text=i18n.t("save_settings"), command=self.save_settings,
            height=40, font=ctk.CTkFont(size=16),
        )
        basic_save_btn.grid(row=18, column=0, columnspan=3, pady=10)
        ui_tooltip.attach_key(basic_save_btn, "tip_save_settings")

    admin_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    admin_frame.grid(row=19, column=0, columnspan=3, padx=100, pady=(10, 16), sticky="ew")
    admin_frame.grid_columnconfigure(0, weight=1)
    if not _is_admin:
        admin_frame.grid_remove()
    else:
        ui_tooltip.attach_key(admin_frame, "tip_settings_admin_only")

    save_btn = ctk.CTkButton(admin_frame, text=i18n.t("save_settings"), command=self.save_settings, height=40, font=ctk.CTkFont(size=16))
    save_btn.pack(fill="x", pady=(0, 8))
    ui_tooltip.attach_key(save_btn, "tip_save_settings")

    backup_btn = ctk.CTkButton(admin_frame, text=i18n.t("backup_database"), command=self.backup_database_gui, height=40, font=ctk.CTkFont(size=16), fg_color="#17a2b8", hover_color="#138496")
    backup_btn.pack(fill="x", pady=(0, 8))
    ui_tooltip.attach_key(backup_btn, "tip_backup_database")

    audit_btn = ctk.CTkButton(admin_frame, text=i18n.t("audit_log"), command=self._open_audit_log_viewer, height=40, font=ctk.CTkFont(size=16), fg_color="#7c3aed", hover_color="#6d28d9")
    audit_btn.pack(fill="x", pady=(0, 8))
    ui_tooltip.attach_key(audit_btn, "tip_audit_log")

    # "Send Test Email" is also an admin-only action → lives in admin_frame.
    email_test_btn = ctk.CTkButton(admin_frame, text=i18n.t("send_test_email"), command=self._send_test_email, height=40, font=ctk.CTkFont(size=16), fg_color="#0ea5e9", hover_color="#0284c7")
    email_test_btn.pack(fill="x", pady=(0, 8))
    ui_tooltip.attach_key(email_test_btn, "tip_save_settings")

    # ── Receipt Header / Footer Notes ────────────────────────────────────
    receipt_header_label = ctk.CTkLabel(scroll, text=i18n.t("receipt_header_note") + ":", anchor="w")
    receipt_header_label.grid(row=16, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_receipt_header_entry = ctk.CTkEntry(scroll, width=300)
    self.set_receipt_header_entry.insert(0, config.get("receipt_header_note", ""))
    self.set_receipt_header_entry.grid(row=16, column=1, padx=(10, 100), pady=10, sticky="w")

    receipt_footer_label = ctk.CTkLabel(scroll, text=i18n.t("receipt_footer_note") + ":", anchor="w")
    receipt_footer_label.grid(row=17, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_receipt_footer_entry = ctk.CTkEntry(scroll, width=300)
    self.set_receipt_footer_entry.insert(0, config.get("receipt_footer_note", ""))
    self.set_receipt_footer_entry.grid(row=17, column=1, padx=(10, 100), pady=10, sticky="w")

    # ── Daily Report Email Section ────────────────────────────────────
    from design_system import CascadeStatusBadge

    email_card = ctk.CTkFrame(scroll, fg_color="#2d2d3a", corner_radius=10)
    email_card.grid(row=22, column=0, columnspan=3, padx=100, pady=(20, 24), sticky="nsew")
    email_card.grid_columnconfigure(1, weight=1)
    email_card.grid_rowconfigure(0, weight=1)

    # Card header: title + OCR cascade badge
    email_header = ctk.CTkFrame(email_card, fg_color="transparent")
    email_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 4))
    email_header.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        email_header, text=i18n.t("daily_report_email"),
        font=ctk.CTkFont(size=16, weight="bold"), text_color="#FFFFFF",
    ).grid(row=0, column=0, sticky="w")

    # OCR Cascade status badge (Phase 3 integration)
    badge_anchor = ctk.CTkFrame(email_header, fg_color="transparent")
    badge_anchor.grid(row=0, column=1, sticky="e")
    self.email_cascade_badge = CascadeStatusBadge(badge_anchor, size="small")
    self.email_cascade_badge.frame.pack(pady=2)

    # SMTP status indicator
    self.smtp_status_label = ctk.CTkLabel(
        email_header, text=i18n.t("smtp_disconnected"), text_color="#ef4444",
        font=ctk.CTkFont(size=10),
    )
    self.smtp_status_label.grid(row=0, column=1, sticky="e", padx=(0, 80))

    email_frame = ctk.CTkFrame(email_card, fg_color="transparent")
    email_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=(4, 16), sticky="nsew")
    email_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(email_frame, text=i18n.t("recipient_email"), anchor="w", width=120).grid(
        row=0, column=0, padx=(0, 8), pady=6, sticky="w")
    self.email_recipient_var = ctk.StringVar()
    self.email_recipient_entry = ctk.CTkEntry(email_frame, width=300,
                                               textvariable=self.email_recipient_var,
                                               placeholder_text="admin@pharmacy.com")
    self.email_recipient_entry.grid(row=0, column=1, columnspan=2, pady=6, sticky="ew")

    ctk.CTkLabel(email_frame, text=i18n.t("smtp_host"), anchor="w", width=120).grid(
        row=1, column=0, padx=(0, 8), pady=6, sticky="w")
    self.smtp_host_var = ctk.StringVar(value="smtp.gmail.com")
    self.smtp_host_entry = ctk.CTkEntry(email_frame, width=200, textvariable=self.smtp_host_var)
    self.smtp_host_entry.grid(row=1, column=1, pady=6, sticky="ew")

    ctk.CTkLabel(email_frame, text=i18n.t("smtp_port"), anchor="w", width=120).grid(
        row=2, column=0, padx=(0, 8), pady=6, sticky="w")
    self.smtp_port_var = ctk.StringVar(value="587")
    self.smtp_port_entry = ctk.CTkEntry(email_frame, width=100, textvariable=self.smtp_port_var)
    self.smtp_port_entry.grid(row=2, column=1, pady=6, sticky="w")

    ctk.CTkLabel(email_frame, text=i18n.t("smtp_username"), anchor="w", width=120).grid(
        row=3, column=0, padx=(0, 8), pady=6, sticky="w")
    self.smtp_user_var = ctk.StringVar()
    self.smtp_user_entry = ctk.CTkEntry(email_frame, width=200, textvariable=self.smtp_user_var)
    self.smtp_user_entry.grid(row=3, column=1, pady=6, sticky="ew")

    ctk.CTkLabel(email_frame, text=i18n.t("smtp_password"), anchor="w", width=120).grid(
        row=4, column=0, padx=(0, 8), pady=6, sticky="w")
    self.smtp_pass_entry = ctk.CTkEntry(email_frame, width=200, show="*")
    self.smtp_pass_entry.grid(row=4, column=1, pady=6, sticky="ew")
    self.smtp_pass_entry.insert(0, os.environ.get("SMTP_PASSWORD", ""))

    ctk.CTkLabel(email_frame, text=i18n.t("report_period"), anchor="w", width=120).grid(
        row=5, column=0, padx=(0, 8), pady=6, sticky="w")
    self.report_period_var = ctk.StringVar(value="daily")
    self.report_period_combo = ctk.CTkComboBox(
        email_frame, width=160, state="readonly",
        values=["daily", "weekly", "monthly"],
        variable=self.report_period_var,
    )
    self.report_period_combo.grid(row=5, column=1, pady=6, sticky="w")

    self.email_enabled_var = ctk.BooleanVar(value=False)
    self.email_toggle = ctk.CTkCheckBox(
        email_frame, text=i18n.t("enable_automated_report"),
        variable=self.email_enabled_var,
    )
    self.email_toggle.grid(row=6, column=0, columnspan=2, pady=(10, 0), sticky="w")

    # Test email button + status
    btn_row = ctk.CTkFrame(email_frame, fg_color="transparent")
    btn_row.grid(row=7, column=0, columnspan=3, pady=(12, 0), sticky="w")

    # Test email button is now admin-gated in admin_frame (see setup_settings_tab).

    self.email_status_label = ctk.CTkLabel(
        btn_row, text="", font=ctk.CTkFont(size=11),
        text_color="#94a3b8",
    )
    self.email_status_label.pack(side="left")

    self._load_email_config()


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


def backup_database_gui(self):
    if not authz.require_pin_for("backup.manage", self):
        return
    try:
        backup_path = backup.create_backup()
        if backup_path:
            messagebox.showinfo("Backup Success", f"Database successfully backed up to:\n{backup_path}")
            try:
                audit_log.log_action(
                    "backup.created", str(backup_path),
                    user_pin=str(auth_session.current_user_id()),
                )
            except Exception:
                pass
        else:
            messagebox.showerror("Backup Failed", "Database file not found.")
    except Exception as e:
        messagebox.showerror("Backup Failed", str(e))


def _open_audit_log_viewer(self):
    if not authz.require_pin_for("audit.view", self):
        return
    AuditLogViewer(self)


def _load_email_config(self):
    """Load saved email report settings from config.json."""
    config = local_daily_report.load_email_config()
    self.email_recipient_var.set(",".join(config.recipient_emails))
    self.smtp_host_var.set(config.smtp_host or "smtp.gmail.com")
    self.smtp_port_var.set(str(config.smtp_port or 587))
    self.smtp_user_var.set(config.smtp_username or "")
    self.email_enabled_var.set(config.enabled)


def _send_test_email(self):
    """Send a test email using the configured SMTP settings.
    Runs in a background thread to avoid freezing the UI."""
    self.email_status_label.configure(text=i18n.t("preparing_report"), text_color="#f59e0b")

    config = local_daily_report.EmailConfig(
        smtp_host=self.smtp_host_var.get().strip(),
        smtp_port=int(self.smtp_port_var.get() or 587),
        smtp_username=self.smtp_user_var.get().strip(),
        smtp_password=self.smtp_pass_entry.get(),
        sender_email=self.smtp_user_var.get().strip(),
        recipient_emails=[e.strip() for e in self.email_recipient_var.get().split(",") if e.strip()],
        enabled=self.email_enabled_var.get(),
    )

    if not config.is_valid():
        self._reset_email_ui()
        messagebox.showerror("Error", "Please fill in SMTP host, sender, and recipient email.")
        return

    report_period = self.report_period_var.get()

    def _on_complete(result, error=None):
        self._reset_email_ui()
        if result and result.get("success"):
            self.email_status_label.configure(
                text=i18n.t("sent_successfully"), text_color="#22c55e")
        else:
            msg = result["message"][:50] if result else str(error)
            self.email_status_label.configure(
                text=i18n.t("send_failed_format", message=msg), text_color="#ef4444")
            if result and result.get("message"):
                messagebox.showerror(i18n.t("error"), result["message"])

    local_daily_report.send_report_async(config, callback=_on_complete, top_period=report_period)


def _reset_email_ui(self):
    self.email_status_label.configure(text="", text_color="#94a3b8")


def _save_email_config(self):
    """Save email report config to config.json (password via env var)."""
    config = local_daily_report.EmailConfig(
        smtp_host=self.smtp_host_var.get().strip(),
        smtp_port=int(self.smtp_port_var.get() or 587),
        smtp_username=self.smtp_user_var.get().strip(),
        smtp_password=self.smtp_pass_entry.get(),
        sender_email=self.smtp_user_var.get().strip(),
        recipient_emails=[e.strip() for e in self.email_recipient_var.get().split(",") if e.strip()],
        enabled=self.email_enabled_var.get(),
    )
    local_daily_report.save_email_config(config)


def _refresh_cascade_badge(self):
    """Update the OCR cascade status badge in the Settings tab."""
    try:
        from ocr_engine import OCRCascadeEngine
        cascade = OCRCascadeEngine()
        engine_count = len(cascade.available_engines)
        if hasattr(self, 'email_cascade_badge'):
            if engine_count > 0:
                self.email_cascade_badge.set_status(
                    tier=len(cascade.available_tiers),
                    confidence=0.95,
                    passed=True,
                )
            else:
                self.email_cascade_badge.set_status(tier=4, confidence=0.30, passed=False)
    except Exception:
        if hasattr(self, 'email_cascade_badge'):
            self.email_cascade_badge.set_status(tier=0, confidence=0.0, passed=False)


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
    barcode_logic.save_config(config)
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
    self._pg_status_label.configure(text=i18n.t("url_built_from_fields"), text_color="#22c55e")


def _test_pg_connection(self):
    """Test the PostgreSQL connection using the current URL field."""
    import db as _db
    url = self.set_db_url_entry.get().strip()
    if not url:
        self._pg_status_label.configure(text=i18n.t("enter_database_url"), text_color="#ef4444")
        return
    result = _db.test_connection(url)
    if result["ok"]:
        self._pg_status_label.configure(
            text=i18n.t("connected_to", backend=result["backend"]), text_color="#22c55e")
    else:
        self._pg_status_label.configure(
            text=i18n.t("pg_connection_failed", error=result["error"][:60]), text_color="#ef4444")


def save_settings(self):
    # settings.manage required for full configuration writes (defense in depth;
    # the basic Save shown to cashiers only reaches here for language/theme which
    # the backend permits via settings.view).
    if not authz.check_permission(auth_session.current_user_id(), "settings.manage"):
        messagebox.showerror(i18n.t("access_denied_title", default="Access Denied"),
                             i18n.t("permission_required", feature="settings.manage"))
        return
    new_name = self.set_name_entry.get().strip()
    new_address = self.set_address_entry.get().strip()
    new_phone = self.set_phone_entry.get().strip()
    new_tax_str = self.set_tax_entry.get().strip()
    new_font_str = self.set_font_entry.get().strip()
    include_price = self.set_price_var.get()
    new_db_path = self.set_db_entry.get().strip()
    new_receipt_header = self.set_receipt_header_entry.get().strip()
    new_receipt_footer = self.set_receipt_footer_entry.get().strip()

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
    config["pharmacy_name"] = new_name
    config["address"] = new_address
    config["phone"] = new_phone
    config["tax_rate"] = new_tax_rate
    config["font_size"] = new_font
    config["include_price"] = include_price
    config["db_path"] = new_db_path or "pharmacy.db"
    config["expiry_alarm_days"] = new_alarm_days
    config["receipt_header_note"] = new_receipt_header
    config["receipt_footer_note"] = new_receipt_footer
    config["database_url"] = self.set_db_url_entry.get().strip()
    config["pg_host"] = self.set_pg_host.get().strip()
    config["pg_port"] = self.set_pg_port.get().strip()
    config["pg_dbname"] = self.set_pg_dbname.get().strip()
    config["pg_user"] = self.set_pg_user.get().strip()
    config["pg_password"] = self.set_pg_pass.get().strip()
    config["pg_ssl"] = self.set_pg_ssl.get().strip()
    # expiry_ignore_list, license_key, and email_report preserved from loaded config

    try:
        with open(barcode_logic.CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)

        # Save email report settings (password via env var, never in config.json)
        self._save_email_config()

        # Reconnect to database (switches to PostgreSQL if URL was set)
        db_url = config.get("database_url", "")
        if db_url:
            import db as _db
            _db.reconnect_db(db_url)

        database.init_db()

        self._notify_config_updated()

        messagebox.showinfo("Success", "Settings saved successfully! Connected to database.")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save config:\n{str(e)}")
