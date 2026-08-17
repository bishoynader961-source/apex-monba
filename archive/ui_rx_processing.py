"""
ui_rx_processing.py — Rx Processing module for PharmacyPro.

Provides:
  - RxProcessingFrame: CTkFrame with patient lookup, drug selection,
    SIG entry, insurance billing via strategy_factory(), and a
    tabbed queue management interface.
  - setup_rx_processing_tab(self): tab-setup function attached to PharmacyApp.
  - _refresh_rx_processing_tab(self): refresh hook called on tab activation.

This module does NOT modify any backend files. It imports and calls existing
functions from rx_config, rx_strategies, rx_db, rx_database, database,
audit_log, barcode_logic, ui_helpers, and async_ui.

Integration (wired via main_app.py post-import hook):
  ui_navigation._NAV_ICONS["rx_processing"] = "💊"
  self.tab_rx_processing = self.tab_view.add(i18n.t("rx_processing"))
  setup_rx_processing_tab(self)
"""
import os
import sys
import json
import sqlite3
import logging
from datetime import datetime

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox

import i18n

from ui_helpers import apply_treeview_style

from rx_config import ConfigManager, get_labels
from rx_strategies import strategy_factory
from rx_database import init_rx_tables

import database
import barcode_logic
import audit_log

try:
    import rx_db as _rx_db
    _HAS_RX_DB = True
except Exception:
    _rx_db = None
    _HAS_RX_DB = False

try:
    from async_ui import AsyncUI
    _HAS_ASYNC = True
except ImportError:
    AsyncUI = None
    _HAS_ASYNC = False

log = logging.getLogger("ui_rx_processing")

_VALID_REGIONS = ["US", "GB", "DE"]

_QUEUE_STATUS_MAP = {
    "queue_in_processing": ["Pending", "Billed", "Verified"],
    "queue_rejects": ["Rejected"],
    "queue_ready_pickup": ["Will Call", "Filled"],
}

_QUEUE_TABS = ["queue_in_processing", "queue_rejects", "queue_ready_pickup"]

COLOR_CARD_DARK = "#1a1a2e"
COLOR_CARD_MED = "#2d2d3a"
COLOR_BG = "#2b2b2b"
COLOR_BG_ALT = "#1e1e1e"
COLOR_ACCENT = "#3b82f6"
COLOR_SUCCESS = "#10b981"
COLOR_WARNING = "#f59e0b"
COLOR_ERROR = "#ef4444"
COLOR_TEXT_PRIMARY = "#f0f0f0"
COLOR_TEXT_SECONDARY = "#a0a0a0"


def _get_archive_dir():
    """Return the archive directory (where this module lives)."""
    return os.path.dirname(os.path.abspath(__file__))


def _get_rx_region():
    """Return the current region: ConfigManager > rx_db.get_region_config > 'US'."""
    try:
        region = ConfigManager().get_region()
        if region:
            return region
    except Exception as e:
        log.debug("ConfigManager region lookup failed: %s", e)
    try:
        if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
            cfg = _rx_db.get_region_config()
            if cfg:
                return cfg
    except Exception as e:
        log.debug("rx_db.get_region_config() failed: %s", e)
    return "US"


def _ensure_rx_tables():
    """Ensure Rx tables (including audit_logs extensions) exist."""
    try:
        init_rx_tables()
    except Exception as e:
        log.warning("init_rx_tables failed (SQLAlchemy may be missing): %s", e)


def _load_patients(search=""):
    """Load patients from database.get_all_patients()."""
    try:
        return database.get_all_patients(search or None)
    except Exception as e:
        log.warning("Failed to load patients: %s", e)
        return []


def _load_inventory(query=""):
    """Load Rx inventory from rx_db.search_inventory() with sqlite3 fallback."""
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            return _rx_db.search_inventory(query)
        except Exception as e:
            log.debug("rx_db.search_inventory failed, falling back to sqlite3: %s", e)
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        like = f"%{query}%"
        cursor.execute("""
            SELECT id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                   awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata
            FROM inventory_extended
            WHERE ndc_code LIKE ? OR drug_name LIKE ? OR ndc_formatted LIKE ?
            ORDER BY drug_name ASC
        """, (like, like, like))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        log.error("Inventory fallback query failed: %s", e)
        return []


def _load_prescribers(query=""):
    """Search prescribers via rx_db with sqlite3 fallback."""
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            if query:
                return _rx_db.search_prescribers(query)
            else:
                return _rx_db.get_all_prescribers()
        except Exception as e:
            log.debug("rx_db prescriber query failed, falling back to sqlite3: %s", e)
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if query:
            like = f"%{query}%"
            cursor.execute("""
                SELECT id, npi, dea_number, state_license, first_name, last_name,
                       phone, email, address, dea_expiration, is_active, regional_metadata
                FROM prescriber_table
                WHERE first_name LIKE ?
                   OR last_name LIKE ?
                   OR npi LIKE ?
                   OR dea_number LIKE ?
                   OR state_license LIKE ?
                ORDER BY last_name ASC, first_name ASC
            """, (like, like, like, like, like))
        else:
            cursor.execute("""
                SELECT id, npi, dea_number, state_license, first_name, last_name,
                       phone, email, address, dea_expiration, is_active, regional_metadata
                FROM prescriber_table WHERE is_active = 1
                ORDER BY last_name ASC, first_name ASC
            """)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        log.error("Prescriber fallback query failed: %s", e)
        return []


def _load_insurance(patient_id):
    """Load insurance records for a patient via rx_db."""
    if patient_id is None:
        return []
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            return _rx_db.get_insurance_by_patient(patient_id)
        except Exception as e:
            log.debug("rx_db.get_insurance_by_patient failed: %s", e)
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata
            FROM insurance_table WHERE patient_id = ?
            ORDER BY id DESC
        """, (patient_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        log.error("Insurance fallback query failed: %s", e)
        return []


def _fetch_rxs_by_status(status):
    """Fetch Rx records by status via rx_db with sqlite3 fallback."""
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            return _rx_db.get_rxs_by_status(status)
        except Exception as e:
            log.debug("rx_db.get_rxs_by_status failed: %s", e)
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, rx_number, patient_id, prescriber_id, drug_ndc,
                   days_supply, daw_code, refills_remaining, sig_code,
                   quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata
            FROM rx_table WHERE status = ?
            ORDER BY id DESC
        """, (status,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        log.error("Rx status fallback query failed: %s", e)
        return []


def _fetch_rxs_for_queue(queue_name):
    """Fetch all Rx records belonging to a queue (maps queue name to statuses)."""
    statuses = _QUEUE_STATUS_MAP.get(queue_name, [])
    if not statuses:
        return []
    all_rows = []
    for status in statuses:
        rows = _fetch_rxs_by_status(status)
        for row in rows:
            all_rows.append(row)
    return all_rows


def _move_rx_status(rx_id, new_status, user_pin=""):
    """Update Rx status via rx_db.update_rx_status with sqlite3 fallback."""
    region = _get_rx_region()
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            return _rx_db.update_rx_status(rx_id, new_status,
                                           user_pin=user_pin, role="user",
                                           region=region)
        except Exception as e:
            log.debug("rx_db.update_rx_status failed, falling back to sqlite3: %s", e)
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE rx_table SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rx_id)
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
    except Exception as e:
        log.error("Rx status update fallback failed: %s", e)
        return False


def _add_rx_db(patient_id, prescriber_id, drug_ndc, days_supply, daw_code,
               refills, sig_code, quantity, date_prescribed, notes, regional_metadata):
    """Insert a new Rx via rx_db.add_rx with sqlite3 fallback."""
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            return _rx_db.add_rx(
                patient_id, prescriber_id, drug_ndc,
                days_supply=days_supply, daw_code=daw_code,
                refills=refills, sig_code=sig_code,
                quantity=quantity, date_prescribed=date_prescribed,
                notes=notes, regional_metadata=regional_metadata
            )
        except Exception as e:
            log.debug("rx_db.add_rx failed, falling back to sqlite3: %s", e)
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d")
        meta_json = json.dumps(regional_metadata) if regional_metadata else "{}"
        prefix = f"RX-{now[:7]}-"
        cursor.execute("SELECT MAX(rx_number) FROM rx_table WHERE rx_number LIKE ?", (f"{prefix}%",))
        result = cursor.fetchone()
        if result and result[0]:
            try:
                seq = int(result[0].split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        rx_number = f"{prefix}{seq:06d}"

        cursor.execute("""
            INSERT INTO rx_table
                (rx_number, patient_id, prescriber_id, drug_ndc,
                 days_supply, daw_code, refills_remaining, sig_code,
                 quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, '', ?, ?)
        """, (
            rx_number, patient_id, prescriber_id, drug_ndc,
            days_supply, daw_code, refills, sig_code,
            quantity, date_prescribed or now, notes, meta_json
        ))
        conn.commit()
        rx_id = cursor.lastrowid
        conn.close()
        return rx_id
    except Exception as e:
        log.error("Rx insert fallback failed: %s", e)
        return None


def _get_patient_name(patient_id):
    """Resolve patient name from database.get_patient_by_id()."""
    if patient_id is None:
        return ""
    try:
        patient = database.get_patient_by_id(patient_id)
        if patient and len(patient) > 1:
            return patient[1]
    except Exception as e:
        log.debug("Patient name lookup failed: %s", e)
    return ""


def _get_prescriber_name(prescriber_id):
    """Resolve prescriber name from rx_db.get_prescriber_by_id()."""
    if prescriber_id is None:
        return ""
    try:
        if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
            row = _rx_db.get_prescriber_by_id(prescriber_id)
            if row and len(row) > 5:
                return f"{row[4]} {row[5]}"
    except Exception as e:
        log.debug("Prescriber name lookup failed: %s", e)
    return ""


class RxProcessingFrame(ctk.CTkFrame):
    """Rx processing frame: patient lookup, drug selection, SIG entry,
    insurance billing via strategy_factory(), and tabbed queue management."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._region = _get_rx_region()
        self._labels = get_labels(self._region)

        self._selected_patient_id = None
        self._selected_patient = None
        self._selected_prescriber_id = None
        self._selected_prescriber = None
        self._selected_drug_ndc = None
        self._selected_drug = None

        self._sig_var = ctk.StringVar()
        self._qty_var = ctk.StringVar(value="0")
        self._days_supply_var = ctk.StringVar(value="0")
        self._refills_var = ctk.StringVar(value="0")
        self._daw_var = ctk.StringVar(value="00")
        self._notes_var = ctk.StringVar()

        self._patient_cost_val = 0.0
        self._insurance_cost_val = 0.0

        self._queue_trees = {}
        self._queue_tabview = None
        self._queue_selection = _QUEUE_TABS[0]
        self._drug_awp = 0.0
        self._claim_data = None

        _ensure_rx_tables()
        self._build_ui()
        self._register_region_listener()

    def _register_region_listener(self):
        """Listen for region changes from the Enterprise Settings module."""
        try:
            def _on_region_change(old_region, new_region):
                self._on_region_changed()
            ConfigManager().register_listener(_on_region_change)
        except Exception as e:
            log.warning("Failed to register region listener: %s", e)

    def _on_region_changed(self):
        """Rebuild labels and refresh queues when region changes."""
        old_region = self._region
        self._region = _get_rx_region()
        if self._region != old_region:
            self._labels = get_labels(self._region)
            self._refresh_form_labels()
            self._refresh_queue_views()
            log.debug("Region changed to %s, UI rebuilt", self._region)

    def _refresh_form_labels(self):
        """Update region-specific labels on visible form controls."""
        try:
            prescriber_labels = _rx_db.get_prescriber_labels(self._region) \
                if _HAS_RX_DB else {}
        except Exception:
            prescriber_labels = {}

        self._drug_code_label.configure(
            text=prescriber_labels.get("drug_code_label", self._labels.get("drug_name", "Drug Name"))
        )
        self._prescriber_id_label.configure(
            text=prescriber_labels.get("prescriber_id_label", "NPI")
        )
        self._ins_bin_label.configure(
            text=prescriber_labels.get("insurance_bin_label", "BIN")
        )
        self._state_license_label.configure(
            text=prescriber_labels.get("state_field_label", "State License")
        )
        self._daw_label.configure(text=i18n.t("daw_code"))

    # ── UI Construction ──

    def _build_ui(self):
        """Build the full Rx Processing UI layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        # ── Title Bar ──
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 5))
        title_row.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            title_row, text=i18n.t("rx_processing"),
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ctk.CTkLabel(
            title_row, text=i18n.t("rx_processing_subtitle"),
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY,
        )
        subtitle.grid(row=0, column=1, sticky="e")

        # ── Main Workspace ──
        workspace = ctk.CTkFrame(self, fg_color="transparent")
        workspace.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        workspace.grid_columnconfigure(0, weight=3)
        workspace.grid_columnconfigure(1, weight=1)
        workspace.grid_rowconfigure(0, weight=1)

        self._build_left_panel(workspace)
        self._build_right_panel(workspace)

        # ── Queue Tabbed Interface ──
        self._build_queue_tabs(self, row=2)

    def _build_left_panel(self, parent):
        """Left panel: patient lookup, prescriber, drug selection, SIG entry, action bar."""
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_rowconfigure(4, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self._build_patient_lookup_panel(left, row=0)
        self._build_prescriber_panel(left, row=1)
        self._build_drug_selection_panel(left, row=2)
        self._build_sig_entry_panel(left, row=3)
        self._build_action_bar(left, row=5)

    def _build_right_panel(self, parent):
        """Right panel: region/insurance quick reference summary."""
        right = ctk.CTkFrame(parent, fg_color=COLOR_CARD_MED, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right, text="Summary",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=20, pady=(16, 12), sticky="w")

        info_frame = ctk.CTkFrame(right, fg_color="transparent")
        info_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        info_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            info_frame, text="Region:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w", pady=4)

        self._region_display_label = ctk.CTkLabel(
            info_frame, text=self._region,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT,
        )
        self._region_display_label.grid(row=0, column=1, sticky="e", pady=4)

        ctk.CTkLabel(
            info_frame, text="Compliance:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=1, column=0, sticky="w", pady=4)

        self._compliance_label = ctk.CTkLabel(
            info_frame,
            text="HIPAA" if self._region == "US" else "GDPR",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_SUCCESS if self._region == "US" else COLOR_WARNING,
        )
        self._compliance_label.grid(row=1, column=1, sticky="e", pady=4)

    def _build_patient_lookup_panel(self, parent, row):
        """Patient lookup card with search + demographic details."""
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD_DARK, corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("patient_lookup"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        search_frame = ctk.CTkFrame(card, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)

        self._patient_search_var = ctk.StringVar()
        self._patient_search_var.trace_add("write", lambda *_: self._on_patient_search())
        self._patient_search_entry = ctk.CTkEntry(
            search_frame, textvariable=self._patient_search_var,
            placeholder_text=i18n.t("patient_search_placeholder"),
            width=360,
        )
        self._patient_search_entry.grid(row=0, column=0, sticky="ew")

        patient_columns = ("Patient", "Phone", "Email", "Insurance")
        self._tree_patients = ttk.Treeview(
            card, columns=patient_columns, show="headings", height=5,
        )
        apply_treeview_style(self._tree_patients)
        for col in patient_columns:
            self._tree_patients.heading(col, text=col)
        self._tree_patients.column("Patient", width=180, anchor="w")
        self._tree_patients.column("Phone", width=100, anchor="w")
        self._tree_patients.column("Email", width=140, anchor="w")
        self._tree_patients.column("Insurance", width=100, anchor="center")
        self._tree_patients.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))

        patient_scroll = ttk.Scrollbar(card, orient="vertical", command=self._tree_patients.yview)
        self._tree_patients.configure(yscrollcommand=patient_scroll.set)
        patient_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=(0, 12))

        self._tree_patients.bind("<ButtonRelease-1>", self._on_patient_select)

        self._tree_patients.tag_configure("even", background=COLOR_BG, foreground=COLOR_TEXT_PRIMARY)
        self._tree_patients.tag_configure("odd", background=COLOR_BG_ALT, foreground=COLOR_TEXT_PRIMARY)

        # ── Patient detail frame (below search results) ──
        self._patient_detail_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._patient_detail_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._patient_detail_frame.grid_columnconfigure(1, weight=1)

        self._patient_name_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self._patient_name_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 2))

        self._patient_dob_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._patient_dob_label.grid(row=1, column=0, sticky="w", pady=2)

        self._patient_phone_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._patient_phone_label.grid(row=2, column=0, sticky="w", pady=2)

        # Insurance section
        ctk.CTkLabel(
            self._patient_detail_frame, text=i18n.t("active_insurance"),
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_ACCENT,
        ).grid(row=0, column=1, sticky="e", pady=(4, 2))

        self._patient_insurance_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._patient_insurance_label.grid(row=1, column=1, sticky="e", pady=2)

        self._patient_ins_bin_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._patient_ins_bin_label.grid(row=2, column=1, sticky="e", pady=2)

    def _build_prescriber_panel(self, parent, row):
        """Prescriber lookup card."""
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD_MED, corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("prescriber_lookup"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        search_frame = ctk.CTkFrame(card, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)

        self._prescriber_search_var = ctk.StringVar()
        self._prescriber_search_var.trace_add("write", lambda *_: self._on_prescriber_search())
        self._prescriber_search_entry = ctk.CTkEntry(
            search_frame, textvariable=self._prescriber_search_var,
            placeholder_text=i18n.t("prescriber_search_placeholder"),
            width=360,
        )
        self._prescriber_search_entry.grid(row=0, column=0, sticky="ew")

        prescriber_columns = ("Prescriber", "NPI/ID", "License", "Phone")
        self._tree_prescribers = ttk.Treeview(
            card, columns=prescriber_columns, show="headings", height=5,
        )
        apply_treeview_style(self._tree_prescribers)
        for col in prescriber_columns:
            self._tree_prescribers.heading(col, text=col)
        self._tree_prescribers.column("Prescriber", width=180, anchor="w")
        self._tree_prescribers.column("NPI/ID", width=100, anchor="w")
        self._tree_prescribers.column("License", width=100, anchor="w")
        self._tree_prescribers.column("Phone", width=100, anchor="w")
        self._tree_prescribers.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))

        pres_scroll = ttk.Scrollbar(card, orient="vertical", command=self._tree_prescribers.yview)
        self._tree_prescribers.configure(yscrollcommand=pres_scroll.set)
        pres_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=(0, 12))

        self._tree_prescribers.bind("<ButtonRelease-1>", self._on_prescriber_select)

        self._tree_prescribers.tag_configure("even", background=COLOR_BG, foreground=COLOR_TEXT_PRIMARY)
        self._tree_prescribers.tag_configure("odd", background=COLOR_BG_ALT, foreground=COLOR_TEXT_PRIMARY)

        # Prescriber detail labels
        self._prescriber_detail_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._prescriber_detail_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._prescriber_detail_frame.grid_columnconfigure(1, weight=1)

        self._prescriber_name_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self._prescriber_name_label.grid(row=0, column=0, sticky="w", pady=2)

        self._prescriber_id_value_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._prescriber_id_value_label.grid(row=1, column=0, sticky="w", pady=2)

        # Region-aware labels
        try:
            prescriber_labels = _rx_db.get_prescriber_labels(self._region) if _HAS_RX_DB else {}
        except Exception:
            prescriber_labels = {}
        self._prescriber_id_label = ctk.CTkLabel(
            self._prescriber_detail_frame,
            text=prescriber_labels.get("prescriber_id_label", "NPI"),
            font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        )
        self._state_license_label = ctk.CTkLabel(
            self._prescriber_detail_frame,
            text=prescriber_labels.get("state_field_label", "State License"),
            font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_SECONDARY,
        )
        self._prescriber_id_label.grid(row=0, column=1, sticky="e", pady=2)
        self._state_license_label.grid(row=1, column=1, sticky="e", pady=2)

        self._prescriber_id_value_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self._prescriber_id_value_label.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=2)

        self._prescriber_license_value_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self._prescriber_license_value_label.grid(row=1, column=2, sticky="e", padx=(8, 0), pady=2)

    def _build_drug_selection_panel(self, parent, row):
        """Drug selection card linked to rx_db inventory."""
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD_DARK, corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("drug_selection"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        search_frame = ctk.CTkFrame(card, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)

        self._drug_search_var = ctk.StringVar()
        self._drug_search_var.trace_add("write", lambda *_: self._on_drug_search())
        self._drug_search_entry = ctk.CTkEntry(
            search_frame, textvariable=self._drug_search_var,
            placeholder_text=i18n.t("search_ndc_or_drug"),
            width=360,
        )
        self._drug_search_entry.grid(row=0, column=0, sticky="ew")

        try:
            prescriber_labels = _rx_db.get_prescriber_labels(self._region) if _HAS_RX_DB else {}
        except Exception:
            prescriber_labels = {}

        self._drug_code_label = ctk.CTkLabel(
            search_frame,
            text=prescriber_labels.get("drug_code_label", self._labels.get("drug_name", "Drug Name")),
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        )
        self._drug_code_label.grid(row=0, column=1, sticky="w", padx=(8, 0))

        drug_columns = ("NDC/PZN", "Drug Name", "Strength", "Form", "AWP", "On Hand", "Lot", "Expiry")
        self._tree_drugs = ttk.Treeview(
            card, columns=drug_columns, show="headings", height=6,
        )
        apply_treeview_style(self._tree_drugs)
        for col in drug_columns:
            self._tree_drugs.heading(col, text=col)
        self._tree_drugs.column("NDC/PZN", width=100, anchor="w")
        self._tree_drugs.column("Drug Name", width=170, anchor="w")
        self._tree_drugs.column("Strength", width=70, anchor="center")
        self._tree_drugs.column("Form", width=70, anchor="center")
        self._tree_drugs.column("AWP", width=70, anchor="e")
        self._tree_drugs.column("On Hand", width=60, anchor="center")
        self._tree_drugs.column("Lot", width=90, anchor="w")
        self._tree_drugs.column("Expiry", width=90, anchor="center")
        self._tree_drugs.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))

        drug_scroll = ttk.Scrollbar(card, orient="vertical", command=self._tree_drugs.yview)
        self._tree_drugs.configure(yscrollcommand=drug_scroll.set)
        drug_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=(0, 12))

        self._tree_drugs.bind("<ButtonRelease-1>", self._on_drug_select)

        self._tree_drugs.tag_configure("even", background=COLOR_BG, foreground=COLOR_TEXT_PRIMARY)
        self._tree_drugs.tag_configure("odd", background=COLOR_BG_ALT, foreground=COLOR_TEXT_PRIMARY)

        # Drug detail frame
        self._drug_detail_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._drug_detail_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._drug_detail_frame.grid_columnconfigure(1, weight=1)

        self._drug_name_value_label = ctk.CTkLabel(
            self._drug_detail_frame, text="", font=ctk.CTkFont(weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self._drug_name_value_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        self._drug_strength_label = ctk.CTkLabel(
            self._drug_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._drug_strength_label.grid(row=1, column=0, sticky="w", pady=2)

        self._drug_form_label = ctk.CTkLabel(
            self._drug_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._drug_form_label.grid(row=2, column=0, sticky="w", pady=2)

    def _build_sig_entry_panel(self, parent, row):
        """SIG entry card: directions, quantity, days supply, refills, DAW."""
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD_MED, corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("sig_entry"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(12, 8), sticky="w")

        # Directions / SIG (multiline)
        ctk.CTkLabel(
            card, text=i18n.t("directions") + ":",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(4, 2))

        self._sig_entry = ctk.CTkEntry(
            card, width=380, textvariable=self._sig_var,
            placeholder_text="e.g. Take 1 tablet by mouth twice daily",
        )
        self._sig_entry.grid(row=1, column=1, sticky="ew", padx=(12, 16), pady=(4, 8))

        # Quantity
        ctk.CTkLabel(
            card, text=i18n.t("quantity") + ":",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 4))

        self._qty_entry = ctk.CTkEntry(card, width=100, textvariable=self._qty_var)
        self._qty_entry.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 8))

        # Days Supply
        ctk.CTkLabel(
            card, text=i18n.t("days_supply") + ":",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=3, column=0, sticky="w", padx=16, pady=(0, 4))

        self._days_supply_entry = ctk.CTkEntry(card, width=100, textvariable=self._days_supply_var)
        self._days_supply_entry.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(0, 8))

        # Refills
        ctk.CTkLabel(
            card, text=i18n.t("refills") + ":",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=4, column=0, sticky="w", padx=16, pady=(0, 4))

        self._refills_entry = ctk.CTkEntry(card, width=100, textvariable=self._refills_var)
        self._refills_entry.grid(row=4, column=1, sticky="w", padx=(12, 0), pady=(0, 8))

        # DAW Code
        ctk.CTkLabel(
            card, text=i18n.t("daw_code") + ":",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=5, column=0, sticky="w", padx=16, pady=(0, 4))

        self._daw_entry = ctk.CTkEntry(card, width=100, textvariable=self._daw_var)
        self._daw_entry.grid(row=5, column=1, sticky="w", padx=(12, 0), pady=(0, 8))

        # Notes
        ctk.CTkLabel(
            card, text="Notes:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=6, column=0, sticky="w", padx=16, pady=(0, 4))

        self._notes_entry = ctk.CTkEntry(card, width=380, textvariable=self._notes_var)
        self._notes_entry.grid(row=6, column=1, sticky="ew", padx=(12, 16), pady=(0, 12))

    def _build_action_bar(self, parent, row):
        """Action bar with Process/Bill button and cost display."""
        bar = ctk.CTkFrame(parent, fg_color=COLOR_CARD_DARK, corner_radius=10, height=64)
        bar.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        bar.pack_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_columnconfigure(1, weight=0)
        bar.grid_columnconfigure(2, weight=0)

        self._cost_frame = ctk.CTkFrame(bar, fg_color="transparent")
        self._cost_frame.grid(row=0, column=0, sticky="w", padx=16, pady=16)

        self._patient_cost_label = ctk.CTkLabel(
            self._cost_frame, text=f"{i18n.t('patient_cost')}: $0.00",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_SUCCESS,
        )
        self._patient_cost_label.pack(side="left", padx=(0, 16))

        self._insurance_cost_label = ctk.CTkLabel(
            self._cost_frame, text=f"{i18n.t('insurance_cost')}: $0.00",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT,
        )
        self._insurance_cost_label.pack(side="left")

        self._process_btn = ctk.CTkButton(
            bar, text=i18n.t("process_bill"),
            font=ctk.CTkFont(size=14, weight="bold"), height=40,
            fg_color=COLOR_SUCCESS, hover_color="#059669",
            command=self._on_process_bill,
        )
        self._process_btn.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=16)

        self._clear_btn = ctk.CTkButton(
            bar, text=i18n.t("clear_form"),
            font=ctk.CTkFont(size=13), height=40,
            fg_color="#6c757d", hover_color="#5a6268",
            command=self._on_clear_form,
        )
        self._clear_btn.grid(row=0, column=2, sticky="e", padx=(0, 16), pady=16)

    def _build_queue_tabs(self, parent, row):
        """Tabbed interface at the bottom for queue management."""
        queue_card = ctk.CTkFrame(parent, fg_color=COLOR_CARD_DARK, corner_radius=10)
        queue_card.grid(row=row, column=0, sticky="nsew", padx=20, pady=(0, 20))
        queue_card.grid_columnconfigure(0, weight=1)
        queue_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            queue_card, text="Rx Queue",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        queue_columns = ("Rx #", "Patient", "Drug", "Qty", "Status", "Prescriber", "Date")

        tab = ctk.CTkTabview(queue_card, fg_color="transparent",
                             segmented_button_fg_color=COLOR_CARD_MED,
                             segmented_button_selected_color=COLOR_ACCENT,
                             command=self._on_queue_tab_changed)
        tab.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

        for label_text in _QUEUE_TABS:
            tab.add(i18n.t(label_text))

            tree = ttk.Treeview(
                tab.tab(i18n.t(label_text)),
                columns=queue_columns, show="headings", height=8,
            )
            apply_treeview_style(tree)
            for col in queue_columns:
                tree.heading(col, text=col)
            tree.column("Rx #", width=90, anchor="w")
            tree.column("Patient", width=130, anchor="w")
            tree.column("Drug", width=150, anchor="w")
            tree.column("Qty", width=50, anchor="center")
            tree.column("Status", width=90, anchor="center")
            tree.column("Prescriber", width=130, anchor="w")
            tree.column("Date", width=90, anchor="center")

            tree_scroll = ttk.Scrollbar(tab.tab(i18n.t(label_text)), orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=tree_scroll.set)
            tree.grid(row=0, column=0, sticky="nsew")
            tree_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 4))

            tab.tab(i18n.t(label_text)).grid_columnconfigure(0, weight=1)
            tab.tab(i18n.t(label_text)).grid_rowconfigure(0, weight=1)

            tree.tag_configure("even", background=COLOR_BG, foreground=COLOR_TEXT_PRIMARY)
            tree.tag_configure("odd", background=COLOR_BG_ALT, foreground=COLOR_TEXT_PRIMARY)
            tree.tag_configure("rejected", background=COLOR_ERROR, foreground="#ffffff")
            tree.tag_configure("will_call", background=COLOR_WARNING, foreground="#000000")

            self._queue_trees[label_text] = tree

        self._queue_tabview = tab
        tab.set(i18n.t(_QUEUE_TABS[0]))

    # ── Event Handlers ──

    def _on_patient_search(self, event=None):
        """Search patients by name/phone/insurance."""
        query = self._patient_search_var.get().strip()
        if not query:
            self._tree_patients.delete(*self._tree_patients.get_children())
            return
        if _HAS_ASYNC:
            AsyncUI.get().run(
                func=lambda q: _load_patients(q),
                callback=self._on_patient_search_done,
                args=(query,),
            )
        else:
            results = _load_patients(query)
            self._on_patient_search_done(results, None)

    def _on_patient_search_done(self, results, error=None):
        """Populate patient search results Treeview."""
        for item in self._tree_patients.get_children():
            self._tree_patients.delete(item)
        if error:
            log.warning("Patient search error: %s", error)
            return
        if not results:
            return
        for idx, row in enumerate(results):
            tag = "even" if idx % 2 == 0 else "odd"
            # row: (pid, name, phone, email, created_at, fields dict)
            name = row[1] if len(row) > 1 else ""
            phone = row[2] if len(row) > 2 else ""
            email = row[3] if len(row) > 3 else ""
            fields = row[5] if len(row) > 5 else {}
            insurance = fields.get("Insurance", "") if isinstance(fields, dict) else ""
            self._tree_patients.insert("", "end", values=(
                name, phone, email, insurance
            ), tags=(tag,))

    def _on_patient_select(self, event=None):
        """Load patient details when a patient is selected."""
        selected = self._tree_patients.selection()
        if not selected:
            return
        idx = self._tree_patients.index(selected[0])
        query = self._patient_search_var.get().strip()
        patients = _load_patients(query)
        if idx >= len(patients):
            return
        self._selected_patient = patients[idx]
        self._selected_patient_id = self._selected_patient[0]

        self._patient_name_label.configure(text=f"  {self._selected_patient[1]}")
        fields = self._selected_patient[5] if len(self._selected_patient) > 5 else {}
        if not isinstance(fields, dict):
            fields = {}
        dob = fields.get("DOB", "")
        phone = self._selected_patient[2] if len(self._selected_patient) > 2 else ""
        email = self._selected_patient[3] if len(self._selected_patient) > 3 else ""
        self._patient_dob_label.configure(text=f"  DOB: {dob}" if dob else "  DOB: —")
        self._patient_phone_label.configure(text=f"  Phone: {phone}" if phone else "  Phone: —")

        # Load insurance
        insurance_rows = _load_insurance(self._selected_patient_id)
        if insurance_rows:
            first = insurance_rows[0]
            carrier = first[6] if len(first) > 6 else ""
            bin_num = first[2] if len(first) > 2 else ""
            pcn = first[3] if len(first) > 3 else ""
            plan = first[5] if len(first) > 5 else ""
            self._patient_insurance_label.configure(
                text=f"  {carrier or plan or 'N/A'}"
            )
            bin_label_text = self._labels.get("insurance_bin_label", "BIN")
            try:
                pres_labels = _rx_db.get_prescriber_labels(self._region) if _HAS_RX_DB else {}
                bin_label_text = pres_labels.get("insurance_bin_label", "BIN")
            except Exception:
                pass
            self._patient_ins_bin_label.configure(
                text=f"  {bin_label_text}: {bin_num or '—'}"
            )
        else:
            self._patient_insurance_label.configure(text="  None")
            self._patient_ins_bin_label.configure(text="")

        log.debug("Selected patient: id=%s name=%s", self._selected_patient_id, self._selected_patient[1])

    def _on_prescriber_search(self, event=None):
        """Search prescribers by name/NPI/DEA."""
        query = self._prescriber_search_var.get().strip()
        if not query:
            self._tree_prescribers.delete(*self._tree_prescribers.get_children())
            return
        if _HAS_ASYNC:
            AsyncUI.get().run(
                func=lambda q: _load_prescribers(q),
                callback=self._on_prescriber_search_done,
                args=(query,),
            )
        else:
            results = _load_prescribers(query)
            self._on_prescriber_search_done(results, None)

    def _on_prescriber_search_done(self, results, error=None):
        """Populate prescriber search results Treeview."""
        for item in self._tree_prescribers.get_children():
            self._tree_prescribers.delete(item)
        if error:
            log.warning("Prescriber search error: %s", error)
            return
        if not results:
            return
        for idx, row in enumerate(results):
            tag = "even" if idx % 2 == 0 else "odd"
            first = row[4] if len(row) > 4 else ""
            last = row[5] if len(row) > 5 else ""
            npi = row[1] if len(row) > 1 else ""
            license_val = row[3] if len(row) > 3 else ""
            phone = row[6] if len(row) > 6 else ""
            name = f"{first} {last}".strip()
            self._tree_prescribers.insert("", "end", values=(
                name, npi, license_val, phone
            ), tags=(tag,))

    def _on_prescriber_select(self, event=None):
        """Load prescriber details when a prescriber is selected."""
        selected = self._tree_prescribers.selection()
        if not selected:
            return
        idx = self._tree_prescribers.index(selected[0])
        query = self._prescriber_search_var.get().strip()
        prescribers = _load_prescribers(query)
        if idx >= len(prescribers):
            return
        self._selected_prescriber = prescribers[idx]
        self._selected_prescriber_id = self._selected_prescriber[0]

        first = self._selected_prescriber[4] if len(self._selected_prescriber) > 4 else ""
        last = self._selected_prescriber[5] if len(self._selected_prescriber) > 5 else ""
        npi = self._selected_prescriber[1] if len(self._selected_prescriber) > 1 else ""
        dea = self._selected_prescriber[2] if len(self._selected_prescriber) > 2 else ""
        license_val = self._selected_prescriber[3] if len(self._selected_prescriber) > 3 else ""
        phone = self._selected_prescriber[6] if len(self._selected_prescriber) > 6 else ""

        self._prescriber_name_label.configure(text=f"  {first} {last}".strip())
        self._prescriber_id_value_label.configure(text=npi or dea or "—")
        self._prescriber_license_value_label.configure(text=license_val or "—")

        log.debug("Selected prescriber: id=%s", self._selected_prescriber_id)

    def _on_drug_search(self, event=None):
        """Search inventory by NDC/PZN or drug name."""
        query = self._drug_search_var.get().strip()
        if not query:
            self._tree_drugs.delete(*self._tree_drugs.get_children())
            return
        if _HAS_ASYNC:
            AsyncUI.get().run(
                func=lambda q: _load_inventory(q),
                callback=self._on_drug_search_done,
                args=(query,),
            )
        else:
            results = _load_inventory(query)
            self._on_drug_search_done(results, None)

    def _on_drug_search_done(self, results, error=None):
        """Populate drug search results Treeview."""
        for item in self._tree_drugs.get_children():
            self._tree_drugs.delete(item)
        if error:
            log.warning("Drug search error: %s", error)
            return
        if not results:
            return
        for idx, row in enumerate(results):
            tag = "even" if idx % 2 == 0 else "odd"
            # row: (id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
            #       awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata)
            ndc = row[1] if len(row) > 1 else ""
            name = row[2] if len(row) > 2 else ""
            strength = row[3] if len(row) > 3 else ""
            form = row[4] if len(row) > 4 else ""
            awp = row[6] if len(row) > 6 else 0.0
            on_hand = row[10] if len(row) > 10 else 0
            lot = row[8] if len(row) > 8 else ""
            expiry = row[9] if len(row) > 9 else ""
            self._tree_drugs.insert("", "end", values=(
                ndc, name, strength, form, self.app.currency.fmt(awp), on_hand, lot, expiry
            ), tags=(tag,))

    def _on_drug_select(self, event=None):
        """Load drug details when a drug is selected from inventory."""
        selected = self._tree_drugs.selection()
        if not selected:
            return
        idx = self._tree_drugs.index(selected[0])
        query = self._drug_search_var.get().strip()
        drugs = _load_inventory(query)
        if idx >= len(drugs):
            return
        self._selected_drug = drugs[idx]
        self._selected_drug_ndc = self._selected_drug[1]

        name = self._selected_drug[2] if len(self._selected_drug) > 2 else ""
        strength = self._selected_drug[3] if len(self._selected_drug) > 3 else ""
        form = self._selected_drug[4] if len(self._selected_drug) > 4 else ""
        awp = self._selected_drug[6] if len(self._selected_drug) > 6 else 0.0
        lot = self._selected_drug[8] if len(self._selected_drug) > 8 else ""
        expiry = self._selected_drug[9] if len(self._selected_drug) > 9 else ""

        self._drug_name_value_label.configure(text=name or "—")
        self._drug_strength_label.configure(text=f"Strength: {strength}" if strength else "Strength: —")
        self._drug_form_label.configure(text=f"Form: {form}" if form else "Form: —")

        # Store AWP for cost calculation
        self._drug_awp = float(awp) if awp else 0.0

        log.debug("Selected drug: ndc=%s name=%s", self._selected_drug_ndc, name)

    def _on_process_bill(self):
        """Process/bill the prescription using strategy_factory()."""
        if self._selected_patient_id is None:
            messagebox.showwarning("Warning", i18n.t("select_patient_first"), parent=self)
            return
        if self._selected_prescriber_id is None:
            messagebox.showwarning("Warning", "Please select a prescriber.", parent=self)
            return
        if self._selected_drug_ndc is None:
            messagebox.showwarning("Warning", "Please select a drug.", parent=self)
            return

        sig = self._sig_var.get().strip()
        qty_str = self._qty_var.get().strip()
        days_str = self._days_supply_var.get().strip()
        refills_str = self._refills_var.get().strip()

        try:
            qty = int(qty_str)
            days_supply = int(days_str)
            refills = int(refills_str)
        except ValueError:
            messagebox.showwarning("Warning", i18n.t("missing_fields_error"), parent=self)
            return

        if not sig or qty <= 0:
            messagebox.showwarning("Warning", i18n.t("missing_fields_error"), parent=self)
            return

        region = _get_rx_region()

        try:
            strategy = strategy_factory(region)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to resolve billing strategy:\n{e}", parent=self)
            log.error("strategy_factory failed: %s", e)
            return

        unit_price = getattr(self, '_drug_awp', 0.0)
        insurance_coverage = None
        try:
            if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
                ins_rows = _rx_db.get_insurance_by_patient(self._selected_patient_id)
                if ins_rows:
                    first = ins_rows[0]
                    insurance_coverage = {"coinsurance_rate": 0.2, "copay": 5.0}
                    if region == "US":
                        bin_num = first[2] if len(first) > 2 else ""
                    meta_json = first[7] if len(first) > 7 else "{}"
                    try:
                        meta = json.loads(meta_json or "{}")
                        if region == "US":
                            insurance_coverage["bin"] = bin_num
                            insurance_coverage["pcn"] = first[3] if len(first) > 3 else ""
                            insurance_coverage["group_number"] = first[4] if len(first) > 4 else ""
                            insurance_coverage["plan_name"] = first[5] if len(first) > 5 else ""
                            insurance_coverage["carrier"] = first[6] if len(first) > 6 else ""
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
        except Exception as e:
            log.debug("Insurance coverage lookup failed: %s", e)

        claim_data = {
            "drug_name": _get_drug_name(self._selected_drug_ndc),
            "ndc": self._selected_drug_ndc,
            "quantity": qty,
            "days_supply": days_supply,
            "insurance_id": "",
            "prescriber_npi": self._selected_prescriber[1] if self._selected_prescriber else "",
            "pharmacy_npi": self._get_pharmacy_npi(),
        }
        if region != "US":
            claim_data["nhs_number"] = ""
            claim_data["prescriber_ods"] = self._selected_prescriber[3] if self._selected_prescriber else ""

        prescription_data = {
            "drug_name": _get_drug_name(self._selected_drug_ndc),
            "dosage": self._sig_var.get().strip(),
            "quantity": qty,
        }
        if region == "US":
            prescription_data["prescriber_npi"] = self._selected_prescriber[1] if self._selected_prescriber else ""
        else:
            prescription_data["prescriber_ods"] = self._selected_prescriber[3] if self._selected_prescriber else ""

        try:
            strategy.validate_prescription(prescription_data)
        except ValueError as ve:
            messagebox.showerror("Validation Error", str(ve), parent=self)
            return
        except Exception as e:
            messagebox.showerror("Error", f"Prescription validation failed:\n{e}", parent=self)
            log.error("validate_prescription error: %s", e)
            return

        try:
            patient_cost = strategy.calculate_patient_cost(unit_price, qty, insurance_coverage)
        except Exception as e:
            log.warning("calculate_patient_cost failed: %s", e)
            patient_cost = unit_price * qty
        self._patient_cost_val = patient_cost
        self._insurance_cost_val = round((unit_price * qty) - patient_cost, 2)

        try:
            claim_result = strategy.generate_claim(claim_data)
            self._claim_data = claim_result
        except Exception as e:
            log.warning("generate_claim failed: %s", e)
            self._claim_data = None

        regional_metadata = {"region": region}
        if region == "US":
            regional_metadata["claim_id"] = self._claim_data.get("npi", "") if self._claim_data else ""
            regional_metadata["pcn"] = claim_data.get("insurance_id", "")

        rx_id = _add_rx_db(
            patient_id=self._selected_patient_id,
            prescriber_id=self._selected_prescriber_id,
            drug_ndc=self._selected_drug_ndc,
            days_supply=days_supply,
            daw_code=self._daw_var.get().strip() or "00",
            refills=refills,
            sig_code=sig,
            quantity=qty,
            date_prescribed=datetime.now().strftime("%Y-%m-%d"),
            notes=self._notes_var.get().strip(),
            regional_metadata=regional_metadata,
        )

        if rx_id is None:
            messagebox.showerror("Error", "Failed to create prescription record.", parent=self)
            return

        try:
            _rx_db.update_rx_status(rx_id, "Billed",
                                     user_pin="", role="user",
                                     region=region) if (_HAS_RX_DB and _rx_db.HAS_SQLALCHEMY) \
                else _move_rx_status(rx_id, "Billed")
        except Exception as e:
            log.warning("Failed to set Rx status to Billed: %s", e)

        audit_log.log_action(
            "RX_PROCESS_BILL",
            f"Rx #{rx_id} processed | Patient: {self._selected_patient_id} | "
            f"Drug: {self._selected_drug_ndc} | Qty: {qty} | "
            f"Patient cost: {self.app.currency.fmt(patient_cost)} | Region: {region}",
        )

        messagebox.showinfo(
            "Success",
            i18n.t("process_success").format(
                rx_number=rx_id, cost=f"{patient_cost:.2f}"
            ),
            parent=self,
        )

        self._update_cost_labels()
        self._refresh_all_queues()
        self._on_clear_form()

    def _on_clear_form(self):
        """Clear all form selections and entries."""
        self._selected_patient_id = None
        self._selected_patient = None
        self._selected_prescriber_id = None
        self._selected_prescriber = None
        self._selected_drug_ndc = None
        self._selected_drug = None

        self._sig_var.set("")
        self._qty_var.set("0")
        self._days_supply_var.set("0")
        self._refills_var.set("0")
        self._daw_var.set("00")
        self._notes_var.set("")

        self._patient_name_label.configure(text="")
        self._patient_dob_label.configure(text="")
        self._patient_phone_label.configure(text="")
        self._patient_insurance_label.configure(text="")
        self._patient_ins_bin_label.configure(text="")
        self._prescriber_name_label.configure(text="")
        self._prescriber_id_value_label.configure(text="")
        self._prescriber_license_value_label.configure(text="")
        self._drug_name_value_label.configure(text="")
        self._drug_strength_label.configure(text="")
        self._drug_form_label.configure(text="")

        self._patient_cost_val = 0.0
        self._insurance_cost_val = 0.0
        self._update_cost_labels()

        for item in self._tree_patients.get_children():
            self._tree_patients.delete(item)
        for item in self._tree_prescribers.get_children():
            self._tree_prescribers.delete(item)
        for item in self._tree_drugs.get_children():
            self._tree_drugs.delete(item)

        self._patient_search_var.set("")
        self._prescriber_search_var.set("")
        self._drug_search_var.set("")

        log.debug("Form cleared")

    def _update_cost_labels(self):
        """Update the patient/insurance cost display labels."""
        self._patient_cost_label.configure(
            text=f"{i18n.t('patient_cost')}: {self.app.currency.fmt(self._patient_cost_val)}"
        )
        self._insurance_cost_label.configure(
            text=f"{i18n.t('insurance_cost')}: {self.app.currency.fmt(self._insurance_cost_val)}"
        )

    def _on_queue_tab_changed(self, event=None):
        """Handle queue tab selection change."""
        try:
            current_tab = self._queue_tabview.get()
            for key, tree in self._queue_trees.items():
                if i18n.t(key) == current_tab:
                    self._queue_selection = key
                    self._refresh_queue(key)
                    break
        except Exception as e:
            log.debug("Queue tab change handler error: %s", e)

    def _refresh_queue(self, queue_key):
        """Refresh a single queue Treeview."""
        tree = self._queue_trees.get(queue_key)
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)

        rx_rows = _fetch_rxs_for_queue(queue_key)
        for idx, row in enumerate(rx_rows):
            tag = "even" if idx % 2 == 0 else "odd"
            status_val = row[10] if len(row) > 10 else ""
            if status_val == "Rejected":
                tag = "rejected"
            elif status_val == "Will Call":
                tag = "will_call"

            rx_number = row[1] if len(row) > 1 else ""
            patient_id = row[2] if len(row) > 2 else None
            drug_ndc = row[4] if len(row) > 4 else ""
            qty = row[9] if len(row) > 9 else 0
            status = row[10] if len(row) > 10 else ""
            date_prescribed = row[11] if len(row) > 11 else ""
            prescriber_id = row[3] if len(row) > 3 else None

            patient_name = _get_patient_name(patient_id)
            drug_name = _get_drug_name(drug_ndc)
            prescriber_name = _get_prescriber_name(prescriber_id)

            tree.insert("", "end", values=(
                rx_number, patient_name, drug_name, qty,
                status, prescriber_name, date_prescribed
            ), tags=(tag,))

    def _refresh_all_queues(self):
        """Refresh all three queue Treeviews."""
        for key in self._queue_trees:
            self._refresh_queue(key)

    def _refresh_queue_views(self):
        """Alias for _refresh_all_queues — called on region change."""
        self._refresh_all_queues()

    def refresh(self):
        """Refresh the entire frame — called on tab switch."""
        self._region = _get_rx_region()
        self._labels = get_labels(self._region)
        try:
            prescriber_labels = _rx_db.get_prescriber_labels(self._region) if _HAS_RX_DB else {}
            self._drug_code_label.configure(
                text=prescriber_labels.get("drug_code_label", self._labels.get("drug_name", "Drug Name"))
            )
            self._prescriber_id_label.configure(
                text=prescriber_labels.get("prescriber_id_label", "NPI")
            )
            self._state_license_label.configure(
                text=prescriber_labels.get("state_field_label", "State License")
            )
        except Exception as e:
            log.debug("Label refresh failed: %s", e)

        self._region_display_label.configure(text=self._region)
        cm = None
        try:
            cm = ConfigManager()
        except Exception:
            pass
        if cm:
            is_hipaa = cm.is_hipaa()
            self._compliance_label.configure(
                text="HIPAA" if is_hipaa else "GDPR",
                text_color=COLOR_SUCCESS if is_hipaa else COLOR_WARNING,
            )

        self._refresh_all_queues()


def _get_drug_name(ndc_code):
    """Resolve drug name from ndc_code via rx_db or sqlite3."""
    if not ndc_code:
        return ""
    try:
        if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
            item = _rx_db.get_inventory_item(ndc_code)
            if item and len(item) > 2:
                return item[2]
    except Exception:
        pass
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT drug_name FROM inventory_extended WHERE ndc_code = ?", (ndc_code,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0]
    except Exception:
        pass
    return ""


def _get_pharmacy_npi():
    """Read pharmacy NPI from config."""
    try:
        config = barcode_logic.load_config()
        return config.get("pharmacy_npi", "")
    except Exception:
        return ""


# ── Context Menu for Queue Actions ──

def _create_queue_context_menu(self, tree, queue_key):
    """Create a right-click context menu for queue Treeview actions."""
    menu = tk.Menu(tree, tearoff=0)
    menu.add_command(label=i18n.t("mark_filled"),
                     command=lambda: _on_queue_action(self, tree, queue_key, "Filled"))
    menu.add_command(label=i18n.t("mark_rejected"),
                     command=lambda: _on_queue_action(self, tree, queue_key, "Rejected"))
    if queue_key != "queue_rejects":
        menu.add_command(label=i18n.t("move_to_ready"),
                         command=lambda: _on_queue_action(self, tree, queue_key, "Will Call"))
    if queue_key == "queue_rejects":
        menu.add_command(label=i18n.t("reprocess"),
                         command=lambda: _on_queue_action(self, tree, queue_key, "Pending"))
    if queue_key == "queue_ready_pickup":
        menu.add_command(label=i18n.t("mark_picked_up"),
                         command=lambda: _on_queue_action(self, tree, queue_key, "Filled"))
    return menu


def _on_queue_action(self, tree, queue_key, new_status):
    """Handle a context menu queue action."""
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select an item first.", parent=self)
        return
    idx = tree.index(selected[0])
    rx_rows = _fetch_rxs_for_queue(queue_key)
    if idx >= len(rx_rows):
        return
    row = rx_rows[idx]
    rx_id = row[0]
    rx_number = row[1] if len(row) > 1 else ""

    try:
        region = _get_rx_region()
        if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
            _rx_db.update_rx_status(rx_id, new_status,
                                     user_pin="", role="user",
                                     region=region)
        else:
            _move_rx_status(rx_id, new_status)

        audit_log.log_action(
            "RX_QUEUE_ACTION",
            f"Rx #{rx_number} (id={rx_id}) moved from '{queue_key}' to '{new_status}'",
        )
    except Exception as e:
        messagebox.showerror("Error", f"Failed to update status:\n{e}", parent=self)
        log.error("Queue action error: %s", e)
        return

    self._refresh_all_queues()


# Attach context menu to queue trees after creation
_original_build_queue_tabs = RxProcessingFrame._build_queue_tabs


def _patched_build_queue_tabs(self, parent, row):
    """Wrapper that builds the queue tabs with context menus."""
    _original_build_queue_tabs(self, parent, row)

    for queue_key, tree in self._queue_trees.items():
        menu = _create_queue_context_menu(self, tree, queue_key)
        def _show_menu(event, m=menu):
            try:
                m.tk_popup(event.x_root, event.y_root)
            finally:
                m.grab_release()
        tree.bind("<Button-3>", _show_menu)


RxProcessingFrame._build_queue_tabs = _patched_build_queue_tabs


def setup_rx_processing_tab(self):
    """Create the Rx Processing tab inside PharmacyApp."""
    frame = RxProcessingFrame(
        self.tab_rx_processing,
        fg_color="transparent",
    )
    frame.pack(fill="both", expand=True, padx=4, pady=4)
    self.rx_processing_frame = frame


def _refresh_rx_processing_tab(self):
    """Refresh hook called when the Rx Processing tab is activated."""
    if hasattr(self, "rx_processing_frame"):
        self.rx_processing_frame.refresh()
