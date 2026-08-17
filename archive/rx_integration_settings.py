"""
rx_integration_settings.py — Secure Rx Workflow settings frame.

Provides RxBillingSettingsFrame: a CTkFrame with region selector,
region-specific credential entry, connection test, and encrypted save.
"""
import os
import logging
import customtkinter as ctk

from rx_config import ConfigManager, get_labels
from rx_strategies import strategy_factory

log = logging.getLogger("rx_integration_settings")

_VALID_REGIONS = ["US", "GB", "DE"]


class RxBillingSettingsFrame(ctk.CTkFrame):
    """Settings frame for the Rx Workflow module.

    Parameters
    ----------
    master : widget
        Parent widget.
    config_path : str
        Path to the JSON config file (e.g. ``config.json``).
    **kwargs
        Passed to ``ctk.CTkFrame``.
    """

    def __init__(self, master, config_path, **kwargs):
        super().__init__(master, **kwargs)
        self.config_path = config_path
        self.cm = ConfigManager()
        self.cm.set_path(config_path)

        self._build_ui()
        self._load_stored_credentials()

    # ── UI Construction ──

    def _build_ui(self):
        self._current_region = self.cm.get_region()

        self.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self, text="Billing Integration Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        # ── Region Selector ──
        region_row = ctk.CTkFrame(self, fg_color="transparent")
        region_row.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 5))
        region_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(region_row, text="Region:", width=80).grid(
            row=0, column=0, sticky="w")

        self.region_selector = ctk.CTkSegmentedButton(
            region_row, values=_VALID_REGIONS,
            command=self._on_region_changed,
        )
        self.region_selector.set(self._current_region)
        self.region_selector.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        # ── Credential Entries (dynamic) ──
        self.cred_container = ctk.CTkFrame(self, fg_color="transparent")
        self.cred_container.grid(row=2, column=0, sticky="nsew", padx=20, pady=5)
        self.cred_container.grid_columnconfigure(1, weight=1)

        # ── Test / Save Buttons ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 20))
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self.test_btn = ctk.CTkButton(
            btn_row, text="Test Connection", width=140,
            command=self._on_test_connection,
        )
        self.test_btn.grid(row=0, column=0, sticky="e", padx=(0, 10))

        self.save_btn = ctk.CTkButton(
            btn_row, text="Save", width=100,
            fg_color="#28a745", hover_color="#218838",
            command=self._on_save,
        )
        self.save_btn.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.status_label.grid(row=4, column=0, sticky="w", padx=20, pady=(0, 10))

        self._rebuild_credential_fields()

    def _rebuild_credential_fields(self):
        """Destroy old credential widgets and create new ones for current region."""
        for child in self.cred_container.winfo_children():
            child.destroy()

        labels = get_labels(self._current_region)
        row = 0

        if self._current_region == "US":
            fields = [
                ("NCPDP API Key", "api_key"),
                ("Switch ID", "switch_id"),
                ("Pharmacy NPI", "pharmacy_npi"),
            ]
        else:
            fields = [
                ("FMD API Key", "fmd_api_key"),
                ("Certificate Path", "cert_path"),
                ("ODS Code", "ods_code"),
            ]

        self._cred_entries = {}

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

                entry = ctk.CTkEntry(entry_row, width=300, show="*")
                entry.grid(row=0, column=0, sticky="ew")
                self._cred_entries[key_name] = entry

                browse_btn = ctk.CTkButton(
                    entry_row, text="Browse", width=80,
                    command=lambda e=entry: self._browse_cert(e),
                )
                browse_btn.grid(row=0, column=1, padx=(8, 0))
            else:
                entry = ctk.CTkEntry(self.cred_container, width=400, show="*")
                entry.grid(row=row, column=1, sticky="ew", pady=4)
                self._cred_entries[key_name] = entry

            row += 1

    def _browse_cert(self, entry_widget):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Certificate File",
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")],
        )
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)

    # ── Event Handlers ──

    def _on_region_changed(self, new_region):
        if new_region not in _VALID_REGIONS:
            return
        self._current_region = new_region
        self.cm.set_region(new_region)
        self._rebuild_credential_fields()
        self._load_stored_credentials()
        self._update_labels()
        log.debug("Region changed to %s", new_region)

    def _update_labels(self):
        labels = get_labels(self._current_region)
        self.status_label.configure(
            text=f"Region: {labels.get('region', self._current_region)} settings loaded")

    def _load_stored_credentials(self):
        for key_name, entry in self._cred_entries.items():
            decrypted = self.cm.get_credential(key_name)
            if decrypted:
                entry.delete(0, "end")
                entry.insert(0, decrypted)

    def _collect_credentials(self):
        return {
            key_name: entry.get().strip()
            for key_name, entry in self._cred_entries.items()
        }

    def _on_test_connection(self):
        creds = self._collect_credentials()
        strategy = strategy_factory(self._current_region)
        success, message = strategy.authenticate(creds)
        if success:
            self.status_label.configure(text=message, text_color="#28a745")
        else:
            self.status_label.configure(text=message, text_color="#dc3545")

    def _on_save(self):
        creds = self._collect_credentials()
        for key_name, value in creds.items():
            if value:
                self.cm.set_credential(key_name, value)
        self.status_label.configure(text="Credentials saved successfully", text_color="#28a745")

    # ── External API ──

    def get_region(self):
        return self._current_region
