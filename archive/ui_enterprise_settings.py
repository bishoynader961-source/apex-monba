"""
ui_enterprise_settings.py — Enterprise Settings & Compliance module for PharmacyPro.

Provides:
  - EnterpriseSettingsFrame: full-settings CTkFrame with region selector,
    Fernet-encrypted credential persistence to rx_secrets.json, connection
    testing via strategy.authenticate(), and a compliance audit log viewer.
  - setup_enterprise_settings_tab(self): tab-setup function attached to PharmacyApp.
  - _refresh_enterprise_tab(self): refresh hook called from on_tab_change.

This module does NOT modify any backend files. It imports and calls existing
functions from rx_config, rx_strategies, rx_db, rx_database, audit_log, database,
and barcode_logic.

Integration (wired via main_app.py post-import hook):
  PharmacyApp.tab_enterprise = app.tab_view.add(i18n.t("enterprise_settings"))
  setup_enterprise_settings_tab(app)
"""
import os
import sys
import json
import sqlite3
import logging

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog

import i18n
from ui_helpers import apply_treeview_style

from rx_config import (
    ConfigManager,
    get_labels,
    encrypt_secret,
    decrypt_secret,
)
from rx_strategies import strategy_factory
from rx_database import init_rx_tables
import database
import barcode_logic
import authz
import auth_session

try:
    import rx_db as _rx_db
    _HAS_RX_DB = True
except Exception:
    _rx_db = None
    _HAS_RX_DB = False

log = logging.getLogger("ui_enterprise_settings")

_VALID_REGIONS = ["US", "GB", "DE"]

# Region-specific credential field labels and keys
_REGION_CRED_FIELDS = {
    "US": [
        ("NCPDP API Key", "api_key"),
        ("Switch ID", "switch_id"),
        ("Pharmacy NPI", "pharmacy_npi"),
    ],
    "GB": [
        ("FMD API Key", "fmd_api_key"),
        ("Certificate Path", "cert_path"),
        ("ODS Code", "ods_code"),
    ],
    "DE": [
        ("PZN API Key", "fmd_api_key"),
        ("Certificate Path", "cert_path"),
        ("Provider ID", "ods_code"),
    ],
}


def _get_archive_dir():
    """Return the archive directory (where rx_config.json lives)."""
    return os.path.dirname(os.path.abspath(__file__))


def _get_secrets_file_path(config_path):
    """Resolve the rx_secrets.json path from the config."""
    try:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                raw = json.load(f)
            secrets_name = raw.get("rx_secrets_file", "rx_secrets.json")
            base_dir = os.path.dirname(os.path.abspath(config_path))
            resolved = os.path.join(base_dir, secrets_name)
            return resolved
    except Exception as e:
        log.warning("Could not resolve secrets file path: %s", e)
    return os.path.join(_get_archive_dir(), "rx_secrets.json")


def _ensure_rx_tables():
    """Ensure Rx tables (audit_logs extensions, rx_config) exist."""
    try:
        from rx_database import init_rx_tables
        init_rx_tables()
    except Exception as e:
        log.warning("init_rx_tables failed (SQLAlchemy may be missing): %s", e)


def _get_config_manager(config_path):
    """Get a ConfigManager singleton with the correct path."""
    cm = ConfigManager()
    cm.set_path(config_path)
    return cm


def _load_secrets_file(secrets_path):
    """Load encrypted credentials from rx_secrets.json.

    Returns a dict: {region: {service: encrypted_token}}
    """
    if not os.path.exists(secrets_path):
        return {}
    try:
        with open(secrets_path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load secrets file %s: %s", secrets_path, e)
    return {}


def _save_secrets_file(secrets_path, data):
    """Write encrypted credentials to rx_secrets.json."""
    try:
        with open(secrets_path, "w") as f:
            json.dump(data, f, indent=4)
        log.debug("Secrets file saved to %s", secrets_path)
    except OSError as e:
        log.error("Failed to save secrets file: %s", e)


def _fetch_audit_logs(limit=500, search_query=""):
    """Fetch audit log entries with full compliance columns.

    Tries the SQLAlchemy session (rx_db.get_session) first, then falls
    back to raw sqlite3 via database.get_db_path().

    Returns list of tuples:
    (id, timestamp, action, user_pin, details,
     region, category, subject_type, subject_id,
     rx_id, old_value, new_value, role, gdpr_deleted)
    """
    cols = [
        "id", "timestamp", "action", "user_pin", "details",
        "region", "category", "subject_type", "subject_id",
        "rx_id", "old_value", "new_value", "role", "gdpr_deleted",
    ]
    col_list = ", ".join(cols)

    # --- SQLAlchemy path ---
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            from sqlalchemy import text
            with _rx_db.get_session() as s:
                if search_query:
                    like = f"%{search_query}%"
                    stmt = text(f"""
                        SELECT {col_list}
                        FROM audit_logs
                        WHERE action LIKE :q
                           OR details LIKE :q
                           OR user_pin LIKE :q
                           OR subject_type LIKE :q
                           OR CAST(subject_id AS TEXT) LIKE :q
                           OR CAST(rx_id AS TEXT) LIKE :q
                        ORDER BY id DESC LIMIT :limit
                    """)
                    result = s.execute(stmt, {"q": like, "limit": limit})
                else:
                    stmt = text(f"""
                        SELECT {col_list}
                        FROM audit_logs
                        ORDER BY id DESC LIMIT :limit
                    """)
                    result = s.execute(stmt, {"limit": limit})
                return [tuple(r) for r in result.fetchall()]
        except Exception as e:
            log.debug("SQLAlchemy audit query failed, falling back to sqlite3: %s", e)

    # --- SQLite fallback ---
    db_path = database.get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        if search_query:
            like = f"%{search_query}%"
            cursor.execute(f"""
                SELECT {col_list}
                FROM audit_logs
                WHERE action LIKE ?
                   OR details LIKE ?
                   OR user_pin LIKE ?
                   OR subject_type LIKE ?
                   OR CAST(subject_id AS TEXT) LIKE ?
                   OR CAST(rx_id AS TEXT) LIKE ?
                ORDER BY id DESC LIMIT ?
            """, (like, like, like, like, like, like, limit))
        else:
            cursor.execute(f"""
                SELECT {col_list}
                FROM audit_logs
                ORDER BY id DESC LIMIT ?
            """, (limit,))
        rows = cursor.fetchall()
        return [tuple(r) for r in rows]
    finally:
        conn.close()


class EnterpriseSettingsFrame(ctk.CTkFrame):
    """Enterprise settings frame with region-based credential management,
    Fernet-encrypted persistence to rx_secrets.json, connection testing,
    and a compliance audit log viewer."""

    def __init__(self, master, config_path=None, **kwargs):
        super().__init__(master, **kwargs)

        self._archive_dir = _get_archive_dir()
        if config_path is None:
            config_path = os.path.join(self._archive_dir, "rx_config.json")
        self.config_path = os.path.abspath(config_path)

        self.cm = _get_config_manager(self.config_path)
        self.secrets_path = _get_secrets_file_path(self.config_path)

        _ensure_rx_tables()

        self._current_region = self.cm.get_region()
        self._cred_entries = {}

        self._build_ui()
        self._load_stored_credentials()


    def _build_ui(self):
        """Build the full Enterprise Settings UI."""
        self.grid_columnconfigure(0, weight=1)

        # ── Title ──
        title = ctk.CTkLabel(
            self, text=i18n.t("enterprise_settings"),
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 5))

        subtitle = ctk.CTkLabel(
            self, text=i18n.t("enterprise_settings_subtitle"),
            font=ctk.CTkFont(size=12), text_color="#94a3b8",
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 20))

        # ── Region & Compliance Card ──
        self._build_region_card(row=2)

        # ── Billing Credentials Card ──
        self._build_credentials_card(row=3)

        # ── Connection Test Card ──
        self._build_connection_card(row=4)

        # ── Action Buttons ──
        self._build_action_buttons(row=5)

        # ── Compliance Audit Log Card ──
        self._build_audit_log_card(row=6)


    def _build_region_card(self, row):
        """Region selector + compliance policy indicator."""
        card = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", padx=20, pady=10)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text="Region",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#e0e0e0",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        self.region_selector = ctk.CTkOptionMenu(
            card, values=_VALID_REGIONS,
            command=authz.require_permission("settings.manage", parent=card)(self._on_region_changed),
        )
        self.region_selector.set(self.cm.get_region())
        self.region_selector.grid(row=0, column=1, sticky="ew", padx=16, pady=(12, 8))

        compliance_row = ctk.CTkFrame(card, fg_color="transparent")
        compliance_row.grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))

        self.compliance_policy_label = ctk.CTkLabel(
            compliance_row, text="", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#60a5fa",
        )
        self.compliance_policy_label.pack(side="left", padx=(0, 16))

        self.unit_system_label = ctk.CTkLabel(
            compliance_row, text="", font=ctk.CTkFont(size=11),
            text_color="#a0a0a0",
        )
        self.unit_system_label.pack(side="left")

        self._update_compliance_display()


    def _build_credentials_card(self, row):
        """Credential entry fields (dynamic per region)."""
        card = ctk.CTkFrame(self, fg_color="#2d2d3a", corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", padx=20, pady=10)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text="Billing Credentials",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8))

        self.cred_container = ctk.CTkFrame(card, fg_color="transparent")
        self.cred_container.grid(row=1, column=0, columnspan=2, sticky="nsew",
                                 padx=16, pady=(0, 12))
        self.cred_container.grid_columnconfigure(1, weight=1)

        self._rebuild_credential_fields()


    def _build_connection_card(self, row):
        """Test connection button + status indicator."""
        card = ctk.CTkFrame(self, fg_color="#2d2d3a", corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", padx=20, pady=10)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text="Connection Test",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        btn_row.grid_columnconfigure(1, weight=1)

        self.test_btn = ctk.CTkButton(
            btn_row, text=i18n.t("test_connection"), width=140,
            command=self._on_test_connection,
        )
        self.test_btn.grid(row=0, column=0, sticky="w")

        self.conn_status_label = ctk.CTkLabel(
            btn_row, text="", font=ctk.CTkFont(size=11), text_color="#94a3b8",
        )
        self.conn_status_label.grid(row=0, column=1, sticky="e")


    def _build_action_buttons(self, row):
        """Save credentials + Export audit report buttons."""
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=row, column=0, sticky="ew", padx=20, pady=(10, 10))
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self.save_btn = ctk.CTkButton(
            btn_row, text=i18n.t("save_credentials"), width=140,
            fg_color="#28a745", hover_color="#218838",
            command=self._on_save_credentials,
        )
        self.save_btn.grid(row=0, column=0, sticky="e", padx=(0, 8))

        self.export_audit_btn = ctk.CTkButton(
            btn_row, text=i18n.t("export_audit_report"), width=160,
            fg_color="#6366f1", hover_color="#4f46e5",
            command=self._on_export_audit,
        )
        self.export_audit_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))


    def _build_audit_log_card(self, row):
        """Compliance audit log viewer with full column set."""
        card = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=10)
        card.grid(row=row, column=0, sticky="nsew", padx=20, pady=(10, 20))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("audit_log_compliance"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        # Search bar
        search_frame = ctk.CTkFrame(card, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 8))
        search_frame.grid_columnconfigure(1, weight=1)

        self.audit_search_var = ctk.StringVar()
        self.audit_search_entry = ctk.CTkEntry(
            search_frame, width=300, textvariable=self.audit_search_var,
            placeholder_text="Search audit logs...",
        )
        self.audit_search_entry.grid(row=0, column=0, sticky="w")
        self.audit_search_entry.bind("<Return>", lambda _: self._on_audit_refresh())

        ctk.CTkButton(
            search_frame, text=i18n.t("search"), width=80,
            command=self._on_audit_refresh,
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        ctk.CTkButton(
            search_frame, text=i18n.t("clear"), width=80,
            fg_color="#6c757d", hover_color="#5a6268",
            command=self._on_audit_clear,
        ).grid(row=0, column=2, sticky="w", padx=(4, 0))

        self.audit_count_label = ctk.CTkLabel(
            search_frame, text="", font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
        )
        self.audit_count_label.grid(row=0, column=3, sticky="e")

        # Audit log Treeview
        columns = ("Time", "Action", "Category", "Subject", "Role", "Details")
        self.tree_audit = ttk.Treeview(
            card, columns=columns, show="headings", height=15,
        )
        apply_treeview_style(self.tree_audit)

        for col in columns:
            self.tree_audit.heading(col, text=col)

        self.tree_audit.column("Time", width=130, anchor="w")
        self.tree_audit.column("Action", width=130, anchor="w")
        self.tree_audit.column("Category", width=100, anchor="center")
        self.tree_audit.column("Subject", width=160, anchor="w")
        self.tree_audit.column("Role", width=70, anchor="center")
        self.tree_audit.column("Details", width=300, anchor="w")

        tree_frame = ctk.CTkFrame(card, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self.tree_audit.grid(row=0, column=0, sticky="nsew")
        audit_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_audit.yview)
        self.tree_audit.configure(yscrollcommand=audit_scroll.set)
        audit_scroll.grid(row=0, column=1, sticky="ns")

        self.tree_audit.tag_configure("even", background="#2b2b2b", foreground="#ffffff")
        self.tree_audit.tag_configure("odd", background="#1e1e1e", foreground="#ffffff")
        self.tree_audit.tag_configure("gdpr_deleted", background="#450a0a", foreground="#fca5a5")


    # ── Credential field management ──

    def _rebuild_credential_fields(self):
        """Destroy old credential widgets and create new ones for current region."""
        for child in self.cred_container.winfo_children():
            child.destroy()

        labels = get_labels(self._current_region)
        fields = _REGION_CRED_FIELDS.get(self._current_region, _REGION_CRED_FIELDS["US"])

        self._cred_entries = {}
        row = 0

        for label_text, key_name in fields:
            lbl = ctk.CTkLabel(
                self.cred_container, text=label_text + ":",
                font=ctk.CTkFont(weight="bold"),
            )
            lbl.grid(row=row, column=0, sticky="w", pady=4)

            if key_name == "cert_path":
                entry_row = ctk.CTkFrame(self.cred_container, fg_color="transparent")
                entry_row.grid(row=row, column=1, sticky="ew", pady=4)
                entry_row.grid_columnconfigure(0, weight=1)

                entry = ctk.CTkEntry(entry_row, width=280, show="*")
                entry.grid(row=0, column=0, sticky="ew")
                self._cred_entries[key_name] = entry

                browse_btn = ctk.CTkButton(
                    entry_row, text="Browse", width=70,
                    command=lambda e=entry: self._browse_cert(e),
                )
                browse_btn.grid(row=0, column=1, padx=(8, 0))
            else:
                entry = ctk.CTkEntry(self.cred_container, width=380, show="*")
                entry.grid(row=row, column=1, sticky="ew", pady=4)
                self._cred_entries[key_name] = entry

            row += 1


    def _browse_cert(self, entry_widget):
        path = filedialog.askopenfilename(
            title="Select Certificate File",
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")],
        )
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)


    # ── Credential persistence ──

    def _load_stored_credentials(self):
        """Load encrypted credentials from rx_secrets.json into ConfigManager,
        then populate the UI entry fields."""
        secrets = _load_secrets_file(self.secrets_path)
        for region, services in secrets.items():
            if not isinstance(services, dict):
                continue
            for service, enc_token in services.items():
                try:
                    decrypted = decrypt_secret(enc_token)
                    if decrypted:
                        self.cm._credentials.setdefault(region, {})[service] = enc_token
                except Exception as e:
                    log.warning("Failed to decrypt credential %s/%s: %s", region, service, e)

        # Populate visible entries
        for key_name, entry in self._cred_entries.items():
            decrypted = self.cm.get_credential(key_name, region=self._current_region)
            if decrypted:
                entry.delete(0, "end")
                entry.insert(0, decrypted)


    def _collect_credentials(self):
        """Collect plaintext credentials from UI entry fields."""
        return {
            key_name: entry.get().strip()
            for key_name, entry in self._cred_entries.items()
        }


    def _sync_credentials_to_manager(self, creds):
        """Encrypt and store credentials via ConfigManager (in-memory)."""
        for key_name, value in creds.items():
            if value:
                self.cm.set_credential(key_name, value, region=self._current_region)


    def _persist_secrets(self):
        """Write all encrypted credentials from ConfigManager to rx_secrets.json."""
        secrets = dict(self.cm._credentials)
        _save_secrets_file(self.secrets_path, secrets)


    # ── Event handlers ──

    def _on_region_changed(self, new_region):
        if new_region not in _VALID_REGIONS:
            return
        old_region = self._current_region
        self._current_region = new_region
        self.cm.set_region(new_region)
        self._rebuild_credential_fields()
        self._load_stored_credentials()
        self._update_compliance_display()
        self.conn_status_label.configure(text="")
        log.debug("Region changed to %s", new_region)
        try:
            uid = auth_session.current_user_id()
            audit_log.log_action(
                "settings.region_change",
                f"region={new_region} by {uid}",
            )
        except Exception as e:
            log.warning("audit log for region change failed: %s", e)


    def _update_compliance_display(self):
        policy = i18n.t("hipaa_compliance") if self.cm.is_hipaa() else i18n.t("gdpr_compliance")
        unit_sys = self.cm.get_unit_system()
        self.compliance_policy_label.configure(
            text=f"Policy: {policy}",
            text_color="#22c55e" if self.cm.is_hipaa() else "#f59e0b",
        )
        self.unit_system_label.configure(
            text=f"Units: {unit_sys.capitalize()}"
        )


    def _on_test_connection(self):
        """Test connection via strategy.authenticate()."""
        creds = self._collect_credentials()
        strategy = strategy_factory(self._current_region)
        try:
            success, message = strategy.authenticate(creds)
            if success:
                self.conn_status_label.configure(text=message, text_color="#22c55e")
            else:
                self.conn_status_label.configure(text=message, text_color="#ef4444")
        except Exception as e:
            self.conn_status_label.configure(
                text=f"Test failed: {e}", text_color="#ef4444"
            )
            log.error("Connection test error: %s", e)


    def _on_save_credentials(self):
        """Save credentials to ConfigManager + persist to rx_secrets.json."""
        creds = self._collect_credentials()
        if not any(creds.values()):
            messagebox.showwarning("Warning", "No credentials entered to save.", parent=self)
            return

        try:
            self._sync_credentials_to_manager(creds)
            self._persist_secrets()
            import audit_log
            audit_log.log_action(
                "RX_CREDENTIAL_SAVE",
                f"Credentials saved for region {self._current_region}",
            )
            self.save_status_label = ctk.CTkLabel(
                self, text="Credentials saved successfully",
                font=ctk.CTkFont(size=12), text_color="#22c55e",
            )
            self.save_status_label.grid(row=5, column=0, sticky="w", padx=20, pady=(0, 10))
            self.after(3000, lambda: self.save_status_label.configure(text=""))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save credentials:\n{e}", parent=self)
            log.error("Credential save error: %s", e)


    def _on_export_audit(self):
        """Export audit log to CSV file."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Audit Log",
        )
        if not filepath:
            return
        try:
            import csv
            logs = _fetch_audit_logs(limit=10000)
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "Action", "User/PIN", "Details",
                    "Region", "Category", "Subject Type", "Subject ID",
                    "Rx ID", "Old Value", "New Value", "Role", "GDPR Deleted",
                ])
                for row in logs:
                    writer.writerow(row)
            messagebox.showinfo("Success", f"Audit log exported to:\n{filepath}", parent=self)
            import audit_log
            audit_log.log_action("EXPORT_AUDIT", f"Audit log exported to {filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed:\n{e}", parent=self)
            log.error("Audit export error: %s", e)


    # ── Audit log management ──

    def _on_audit_refresh(self):
        """Reload the audit log Treeview."""
        query = self.audit_search_var.get().strip()
        logs = _fetch_audit_logs(limit=500, search_query=query)

        for item in self.tree_audit.get_children():
            self.tree_audit.delete(item)

        for idx, row in enumerate(logs):
            tag = "even" if idx % 2 == 0 else "odd"
            if row[13] == 1:
                tag = "gdpr_deleted"

            # row: (id, timestamp, action, user_pin, details,
            #       region, category, subject_type, subject_id,
            #       rx_id, old_value, new_value, role, gdpr_deleted)
            self.tree_audit.insert("", "end", values=(
                row[1] or "",       # Time
                row[2] or "",       # Action
                row[6] or "access",  # Category
                f"{row[7] or '—'} (ID: {row[8] or '—'})",  # Subject
                row[12] or "user",   # Role
                row[4] or "",        # Details
            ), tags=(tag,))

        self.audit_count_label.configure(
            text=f"{len(logs)} log entr{'y' if len(logs) == 1 else 'ies'} found"
        )


    def _on_audit_clear(self):
        self.audit_search_var.set("")
        self._on_audit_refresh()


    def refresh(self):
        """Refresh the entire frame — called on tab switch."""
        self._update_compliance_display()
        self._on_audit_refresh()


    def _on_audit_detail(self, event=None):
        """Show full audit log entry details on double-click."""
        selected = self.tree_audit.selection()
        if not selected:
            return
        idx = self.tree_audit.index(selected[0])
        logs = _fetch_audit_logs(limit=500, search_query=self.audit_search_var.get().strip())
        if idx >= len(logs):
            return
        row = logs[idx]
        details = (
            f"ID: {row[0]}\n"
            f"Timestamp: {row[1]}\n"
            f"Action: {row[2]}\n"
            f"User/PIN: {row[3] or 'N/A'}\n"
            f"Details: {row[4]}\n"
            f"Region: {row[5]}\n"
            f"Category: {row[6]}\n"
            f"Subject Type: {row[7]}\n"
            f"Subject ID: {row[8]}\n"
            f"Rx ID: {row[9]}\n"
            f"Old Value: {row[10]}\n"
            f"New Value: {row[11]}\n"
            f"Role: {row[12]}\n"
            f"GDPR Deleted: {'Yes' if row[13] == 1 else 'No'}"
        )
        messagebox.showinfo("Audit Entry Details", details, parent=self)


def setup_enterprise_settings_tab(self):
    """Create the Enterprise Settings tab inside PharmacyApp."""
    config_path = os.path.join(_get_archive_dir(), "rx_config.json")

    frame = EnterpriseSettingsFrame(
        self.tab_enterprise,
        config_path=config_path,
        fg_color="transparent",
    )
    frame.pack(fill="both", expand=True, padx=4, pady=4)
    frame._on_audit_refresh()
    self.enterprise_settings_frame = frame


def _refresh_enterprise_tab(self):
    """Refresh hook called when the Enterprise Settings tab is activated."""
    if hasattr(self, "enterprise_settings_frame"):
        self.enterprise_settings_frame.refresh()
