"""
ui_epcs_workflow.py — Web-Based EPCS & Prescription Creation Workflow module for PharmacyPro.

Provides:
  - EpcsWorkflowFrame: CTkFrame with a 3-step prescription wizard:
      Step 1: Patient Selection & Search (database.get_all_patients())
      Step 2: Product/Medication Selection (rx_db.search_inventory())
      Step 3: Prescription Details & Authorization (qty, frequency, directions,
              duration, refills, special notes, veterinarian/prescriber selection)
  - Four action controls: Save in Draft, Print/Fax, Save to Inbox, Submit/Authorize
  - setup_epcs_workflow_tab(self): tab-setup function attached to PharmacyApp.
  - _refresh_epcs_workflow_tab(self): refresh hook called on tab activation.

This module does NOT modify any backend files. It imports and calls existing
functions from rx_config, rx_strategies, rx_db, database, audit_log,
barcode_logic, ui_helpers, and async_ui.

Integration (wired via main_app.py post-import hook):
  ui_navigation._NAV_ICONS["epcs_workflow"] = "📝"
  self.tab_epcs_workflow = app.tab_view.add(i18n.t("epcs_workflow"))
  setup_epcs_workflow_tab(app)
"""
import os
import sys
import json
import sqlite3
import logging
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
from tkinter import ttk, messagebox

import i18n
import database
import barcode_logic
import audit_log
from ui_helpers import apply_treeview_style

from rx_config import ConfigManager, get_labels
from rx_strategies import strategy_factory
from rx_database import init_rx_tables

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

log = logging.getLogger("ui_epcs_workflow")

_VALID_REGIONS = ["US", "GB", "DE"]

_WIZARD_STEPS = ["step_patient", "step_medication", "step_prescription"]

_FREQUENCY_OPTIONS = [
    "QD", "BID", "TID", "QID", "QHS", "QOD", "QWK",
    "Q2H", "Q4H", "Q6H", "Q8H", "Q12H", "PRN", "Other",
]

DRAFT_SUFFIX = " [DRAFT]"
INBOX_SUFFIX = " [INBOX]"

_COLOR_CARD_DARK = "#1a1a2e"
_COLOR_CARD_MED = "#2d2d3a"
_COLOR_BG = "#2b2b2b"
_COLOR_BG_ALT = "#1e1e1e"
_COLOR_ACCENT = "#3b82f6"
_COLOR_SUCCESS = "#10b981"
_COLOR_WARNING = "#f59e0b"
_COLOR_ERROR = "#ef4444"
_COLOR_TEXT_PRIMARY = "#f0f0f0"
_COLOR_TEXT_SECONDARY = "#a0a0a0"


# ── Module-level helper functions ──────────────────────────────────────────

def _get_archive_dir() -> str:
    """Return the archive directory (where this module lives)."""
    return os.path.dirname(os.path.abspath(__file__))


def _get_rx_region() -> str:
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
    """Ensure Rx tables exist. Idempotent — safe to call multiple times."""
    try:
        init_rx_tables()
    except Exception as e:
        log.warning("init_rx_tables failed (SQLAlchemy may be missing): %s", e)


def _load_patients(search: str = "") -> list:
    """Load patients via database.get_all_patients().

    Returns: [(pid, name, phone, email, created_at, {field_name: field_value})]
    """
    try:
        return database.get_all_patients(search or None)
    except Exception as e:
        log.warning("Failed to load patients: %s", e)
        return []


def _load_inventory(query: str = "") -> list:
    """Load Rx inventory via rx_db.search_inventory() with sqlite3 fallback.

    Returns: [(id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
               awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata_json)]
    """
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


def _load_prescribers(query: str = "") -> list:
    """Search prescribers via rx_db with sqlite3 fallback.

    Returns: [(id, npi, dea_number, state_license, first_name, last_name,
               phone, email, address, dea_expiration, is_active, regional_metadata_json)]
    """
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            if query:
                return _rx_db.search_prescribers(query)
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
                WHERE first_name LIKE :q
                   OR last_name LIKE :q
                   OR npi LIKE :q
                   OR dea_number LIKE :q
                   OR state_license LIKE :q
                ORDER BY last_name ASC, first_name ASC
            """, {"q": like})
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


def _get_prescriber_regional(prescriber_id: int) -> Optional[dict]:
    """Return prescriber row + parsed regional_metadata JSON via rx_db (fallback: sqlite3)."""
    try:
        if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
            row = _rx_db.get_prescriber_regional(prescriber_id)
            if row:
                return row
    except Exception as e:
        log.debug("rx_db.get_prescriber_regional failed: %s", e)
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, npi, dea_number, state_license, first_name, last_name,
                   phone, email, address, dea_expiration, is_active, regional_metadata
            FROM prescriber_table WHERE id = ?
        """, (prescriber_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        try:
            result["regional_metadata"] = json.loads(result["regional_metadata"] or "{}")
        except (ValueError, TypeError):
            result["regional_metadata"] = {}
        return result
    except Exception as e:
        log.error("Prescriber regional fallback failed: %s", e)
        return None


def _resolve_prescriber_display(row: tuple) -> Dict[str, str]:
    """Extract display fields from a prescriber tuple, handling NPI-null (veterinarians).

    Prescriber tuple: (id, npi, dea_number, state_license, first_name, last_name,
                       phone, email, address, dea_expiration, is_active, regional_metadata_json)
    """
    pid = row[0] if len(row) > 0 else None
    npi = row[1] if len(row) > 1 else ""
    dea = row[2] if len(row) > 2 else ""
    license_val = row[3] if len(row) > 3 else ""
    first = row[4] if len(row) > 4 else ""
    last = row[5] if len(row) > 5 else ""
    phone = row[6] if len(row) > 6 else ""
    name = f"{first} {last}".strip() if first or last else str(pid)

    # Primary ID: NPI if present, else DEA, else state license
    if npi:
        id_val = npi
        id_type = "NPI"
    elif dea:
        id_val = dea
        id_type = "DEA"
    else:
        id_val = license_val or "—"
        id_type = "License"

    return {
        "id": pid,
        "name": name,
        "npi": npi or "",
        "dea": dea or "",
        "license": license_val or "",
        "id_value": id_val,
        "id_type": id_type,
        "phone": phone or "",
    }


def _generate_rx_number_sqlite() -> str:
    """Generate RX-YYYY-MM-NNNNNN (sequential per year-month) via sqlite3.

    Mirrors rx_db._generate_rx_number().
    """
    now = datetime.now()
    year_month = now.strftime("%Y-%m")
    prefix = f"RX-{year_month}-"
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT MAX(rx_number) FROM rx_table WHERE rx_number LIKE ?",
            (f"{prefix}%",),
        )
        result = cursor.fetchone()
        conn.close()
        if result and result[0]:
            try:
                seq = int(result[0].split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:06d}"
    except Exception as e:
        log.warning("rx_number generation via sqlite3 failed: %s", e)
        return f"{prefix}000001"


def _create_rx_sqlite(patient_id: int, prescriber_id: int, drug_ndc: str,
                      days_supply: int = 0, daw_code: str = "00",
                      refills: int = 0, sig_code: str = "",
                      quantity: int = 0, date_prescribed: str = "",
                      notes: str = "",
                      regional_metadata: Optional[dict] = None) -> Optional[int]:
    """sqlite3 fallback for rx_db.add_rx() / rx_db.add_rx_regional().

    Inserts into rx_table with auto-generated rx_number.
    """
    rx_number = _generate_rx_number_sqlite()
    now = datetime.now().strftime("%Y-%m-%d")
    meta_json = json.dumps(regional_metadata) if regional_metadata else "{}"
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO rx_table
                (rx_number, patient_id, prescriber_id, drug_ndc,
                 days_supply, daw_code, refills_remaining, sig_code,
                 quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, '', ?, ?)
        """, (
            rx_number, patient_id, prescriber_id, drug_ndc,
            days_supply, daw_code, refills, sig_code,
            quantity, date_prescribed or now, notes, meta_json,
        ))
        conn.commit()
        rx_id = cursor.lastrowid
        conn.close()
        return rx_id
    except Exception as e:
        log.error("SQLite fallback: add_rx failed: %s", e)
        return None


def _update_rx_status_sqlite(rx_id: int, new_status: str, user_pin: str = "",
                             region: str = "US") -> bool:
    """sqlite3 fallback for rx_db.update_rx_status().

    Updates rx_table.status + date_started, and inserts a basic audit log entry.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM rx_table WHERE id = ?", (rx_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        old_status = row[0]
        cursor.execute(
            "UPDATE rx_table SET status = ?, date_started = ? WHERE id = ?",
            (new_status, ts, rx_id),
        )
        conn.commit()
        conn.close()
        audit_log.log_action(
            "RX_STATUS_CHANGE",
            f"Rx #{rx_id} status changed from '{old_status}' to '{new_status}'",
            user_pin,
        )
        return True
    except Exception as e:
        log.error("SQLite fallback: update_rx_status failed: %s", e)
        return False


def _create_prescription_record(region: str, patient_id: int, prescriber_id: int,
                                drug_ndc: str, days_supply: int, daw_code: str,
                                refills: int, sig_code: str, quantity: int,
                                date_prescribed: str, notes: str,
                                regional_metadata: dict) -> Optional[int]:
    """Insert a new prescription via rx_db.add_rx_regional (SQLAlchemy) or sqlite3 fallback.

    Returns the rx_id (int) or None on failure.
    """
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            return _rx_db.add_rx_regional(
                region, patient_id, prescriber_id, drug_ndc,
                days_supply=days_supply,
                daw_code=daw_code,
                refills=refills,
                sig_code=sig_code,
                quantity=quantity,
                date_prescribed=date_prescribed,
                notes=notes,
                regional_metadata=regional_metadata,
            )
        except Exception as e:
            log.debug("rx_db.add_rx_regional failed, falling back to sqlite3: %s", e)
    return _create_rx_sqlite(
        patient_id, prescriber_id, drug_ndc,
        days_supply=days_supply, daw_code=daw_code,
        refills=refills, sig_code=sig_code,
        quantity=quantity, date_prescribed=date_prescribed,
        notes=notes, regional_metadata=regional_metadata,
    )


def _set_rx_status(rx_id: int, new_status: str, region: str = "US",
                   user_pin: str = "") -> bool:
    """Update RX status via rx_db.update_rx_status (SQLAlchemy) or sqlite3 fallback."""
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            return _rx_db.update_rx_status(
                rx_id, new_status,
                user_pin=user_pin, role="user",
                region=region,
                subject_type="rx", subject_id=rx_id,
            )
        except Exception as e:
            log.debug("rx_db.update_rx_status failed, falling back to sqlite3: %s", e)
    return _update_rx_status_sqlite(rx_id, new_status, user_pin=user_pin, region=region)


def _get_prescriber_labels(region: str) -> dict:
    """Get region-aware prescriber labels from rx_db or rx_config.

    Maps sub-region codes (GB, DE) to label groups (EU) so that label
    lookup aligns with both the strategy registry and the REGION_LABELS
    dict in rx_db (which uses "US" and "EU" as keys).
    """
    labels = {}
    label_region = region
    if region in ("GB", "DE"):
        label_region = "EU"
    if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
        try:
            labels = _rx_db.get_prescriber_labels(label_region) or {}
        except Exception:
            pass
    if not labels:
        try:
            labels = get_labels(region)
        except Exception:
            pass
    return labels


def _get_pharmacy_info() -> dict:
    """Read pharmacy info from config."""
    try:
        config = barcode_logic.load_config()
        return {
            "pharmacy_name": config.get("pharmacy_name", ""),
            "address": config.get("address", ""),
            "phone": config.get("phone", ""),
            "pharmacy_npi": config.get("pharmacy_npi", ""),
        }
    except Exception:
        return {}


def _format_prescription_text(prescription_data: dict) -> str:
    """Generate a text-based prescription form suitable for printing/faxing."""
    pharm = _get_pharmacy_info()
    width = 40
    sep = "=" * width
    dash = "-" * width
    lines = []
    lines.append(sep)
    if pharm.get("pharmacy_name"):
        lines.append(pharm["pharmacy_name"].center(width))
    if pharm.get("address"):
        lines.append(pharm["address"].center(width))
    if pharm.get("phone"):
        lines.append(f"Tel: {pharm['phone']}".center(width))
    lines.append(sep)
    if prescription_data.get("rx_number"):
        lines.append(f"Rx #: {prescription_data['rx_number']}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(dash)
    # Patient
    lines.append(f"Patient: {prescription_data.get('patient_name', '')}")
    if prescription_data.get("patient_dob"):
        lines.append(f"DOB: {prescription_data['patient_dob']}")
    if prescription_data.get("patient_phone"):
        lines.append(f"Phone: {prescription_data['patient_phone']}")
    lines.append(dash)
    # Prescriber
    lines.append(f"Prescriber: {prescription_data.get('prescriber_name', '')}")
    if prescription_data.get("prescriber_id_label"):
        lines.append(f"{prescription_data['prescriber_id_label']}: {prescription_data.get('prescriber_id_value', '')}")
    if prescription_data.get("prescriber_license"):
        lines.append(f"License: {prescription_data['prescriber_license']}")
    lines.append(dash)
    # Medication
    lines.append(f"Medication: {prescription_data.get('drug_name', '')}")
    if prescription_data.get("drug_strength"):
        lines.append(f"Strength: {prescription_data['drug_strength']}")
    if prescription_data.get("drug_form"):
        lines.append(f"Form: {prescription_data['drug_form']}")
    lines.append(dash)
    # SIG
    lines.append(f"Directions: {prescription_data.get('directions', '')}")
    lines.append(f"Quantity: {prescription_data.get('quantity', '')}")
    lines.append(f"Frequency: {prescription_data.get('frequency', '')}")
    if prescription_data.get("duration"):
        lines.append(f"Duration: {prescription_data['duration']}")
    if prescription_data.get("refills") is not None:
        lines.append(f"Refills: {prescription_data.get('refills', '')}")
    if prescription_data.get("notes"):
        lines.append(f"Notes: {prescription_data['notes']}")
    lines.append(dash)
    lines.append("Prescriber Signature: ___________________")
    lines.append("Date: " + datetime.now().strftime('%Y-%m-%d'))
    lines.append(sep)
    return "\n".join(lines)


def _debounced_search(widget, var, callback, delay_ms: int = 300):
    """Attach a debounced search callback to a StringVar trace.

    Uses after() to delay execution until the user pauses typing.
    Returns the after() id so it can be cancelled on the next keystroke.
    """
    _timer = [None]

    def _delayed(*_):
        if _timer[0] is not None:
            widget.after_cancel(_timer[0])
        _timer[0] = widget.after(delay_ms, lambda: callback())

    var.trace_add("write", _delayed)
    return _timer


class EpcsWorkflowFrame(ctk.CTkFrame):
    """3-step EPCS prescription wizard: patient → medication → prescription + authorize.

    Uses the same color scheme, treeview styling, and async search patterns as
    ui_rx_processing.py and ui_pos_terminal.py.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._region = _get_rx_region()
        self._labels = get_labels(self._region)

        # ── Wizard navigation state ──
        self._current_step = 0  # index into _WIZARD_STEPS
        self._step_pages: Dict[str, ctk.CTkFrame] = {}

        # ── Selection state ──
        self._selected_patient_id: Optional[int] = None
        self._selected_patient: Optional[tuple] = None
        self._selected_drug_ndc: Optional[str] = None
        self._selected_drug: Optional[tuple] = None
        self._drug_awp: float = 0.0
        self._selected_prescriber_id: Optional[int] = None
        self._selected_prescriber: Optional[tuple] = None
        self._prescriber_display: Dict[str, str] = {}

        # ── Form state (Step 3) ──
        self._qty_var = ctk.StringVar(value="0")
        self._frequency_var = ctk.StringVar(value=_FREQUENCY_OPTIONS[0])
        self._directions_var = ctk.StringVar()
        self._duration_var = ctk.StringVar(value="30")
        self._refills_var = ctk.StringVar(value="0")
        self._daw_var = ctk.StringVar(value="00")
        self._notes_var = ctk.StringVar()

        # ── Computed / result state ──
        self._patient_cost_val: float = 0.0
        self._insurance_cost_val: float = 0.0
        self._claim_data: Optional[dict] = None
        self._strategy = None
        self._draft_rx_id: Optional[int] = None
        self._latest_rx_number: str = ""

        # ── Debounced search timers ──
        self._patient_search_timer = [None]
        self._drug_search_timer = [None]
        self._prescriber_search_timer = [None]

        # Region-aware label references (created in _build_step_prescription)
        self._prescriber_id_label_ref: Optional[ctk.CTkLabel] = None
        self._drug_code_label_ref: Optional[ctk.CTkLabel] = None
        self._daw_label_ref: Optional[ctk.CTkLabel] = None

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
        """Rebuild region-aware labels when region changes."""
        old_region = self._region
        self._region = _get_rx_region()
        if self._region != old_region:
            self._labels = get_labels(self._region)
            self._refresh_labels()
            log.debug("Region changed to %s", self._region)

    def _refresh_labels(self):
        """Update all visible region-aware labels."""
        prescriber_labels = _get_prescriber_labels(self._region)
        if self._prescriber_id_label_ref:
            self._prescriber_id_label_ref.configure(
                text=prescriber_labels.get("prescriber_id_label", "NPI")
            )
        if self._drug_code_label_ref:
            self._drug_code_label_ref.configure(
                text=prescriber_labels.get("drug_code_label", self._labels.get("drug_name", "Drug Name"))
            )
        if self._daw_label_ref:
            if self._region == "US":
                self._daw_label_ref.configure(text=f"{i18n.t('daw_code')}:")
            else:
                self._daw_label_ref.configure(text="")

    # ── UI Construction ──

    def _build_ui(self):
        """Build the full wizard UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)

        self._build_wizard_header()
        self._build_step_indicator()
        self._build_wizard_container()
        self._build_action_bar()

    def _build_wizard_header(self):
        """Header with title and subtitle."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 5))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header, text=i18n.t("epcs_workflow"),
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ctk.CTkLabel(
            header, text=i18n.t("epcs_workflow_subtitle"),
            font=ctk.CTkFont(size=12), text_color=_COLOR_TEXT_SECONDARY,
        )
        subtitle.grid(row=0, column=0, sticky="e")

    def _build_step_indicator(self):
        """Breadcrumb-style step indicator: [1 Patient] [2 Medication] [3 Prescription]."""
        indicator = ctk.CTkFrame(self, fg_color="transparent")
        indicator.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        indicator.grid_columnconfigure((0, 1, 2), weight=1)

        self._step_labels: Dict[str, ctk.CTkLabel] = {}
        for idx, step_key in enumerate(_WIZARD_STEPS):
            step_text = i18n.t(step_key)
            label = ctk.CTkLabel(
                indicator, text=step_text,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_COLOR_TEXT_SECONDARY,
            )
            label.grid(row=0, column=idx, sticky="w")
            self._step_labels[step_key] = label

        self._step_indicator_bar = ctk.CTkFrame(indicator, fg_color=_COLOR_ACCENT, height=4)
        self._step_indicator_bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        self._update_step_indicator()

    def _update_step_indicator(self):
        """Highlight the active step in the breadcrumb."""
        for idx, step_key in enumerate(_WIZARD_STEPS):
            label = self._step_labels[step_key]
            if idx == self._current_step:
                label.configure(text_color=_COLOR_ACCENT)
            elif idx < self._current_step:
                label.configure(text_color=_COLOR_SUCCESS)
            else:
                label.configure(text_color=_COLOR_TEXT_SECONDARY)

        # Progress bar: fill proportionally
        progress = (self._current_step + 1) / len(_WIZARD_STEPS)
        # Use a CTkFrame width to represent progress
        for child in self._step_indicator_bar.winfo_children():
            child.destroy()

    def _build_wizard_container(self):
        """Container holding the three step pages (stacked via tkraise)."""
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=2, column=0, sticky="nsew", padx=20, pady=0)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._wizard_container = container

        # Build each step page (all created upfront, only one visible)
        for idx, step_key in enumerate(_WIZARD_STEPS):
            page = ctk.CTkFrame(container, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            self._step_pages[step_key] = page

            if step_key == "step_patient":
                self._build_step_patient(page)
            elif step_key == "step_medication":
                self._build_step_medication(page)
            elif step_key == "step_prescription":
                self._build_step_prescription(page)

        self._show_step(_WIZARD_STEPS[self._current_step])

    def _show_step(self, step_key: str):
        """Raise the given step page to the front."""
        self._step_pages[step_key].tkraise()
        self._update_step_indicator()

    def _build_step_patient(self, parent):
        """Step 1: Patient Selection & Search."""
        card = ctk.CTkFrame(parent, fg_color=_COLOR_CARD_DARK, corner_radius=10)
        card.pack(fill="both", expand=True, padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("patient_lookup"),
            font=ctk.CTkFont(size=16, weight="bold"), text_color=_COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        ctk.CTkLabel(
            card, text=_get_prescriber_labels(self._region).get(
                "patient_dob_label", "Date of Birth"
            ),
            font=ctk.CTkFont(size=11), text_color=_COLOR_TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(0, 4))

        search_frame = ctk.CTkFrame(card, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)

        self._patient_search_var = ctk.StringVar()
        _debounced_search(search_frame, self._patient_search_var, self._on_patient_search)
        self._patient_search_entry = ctk.CTkEntry(
            search_frame, textvariable=self._patient_search_var,
            placeholder_text=i18n.t("patient_search_placeholder"),
            width=360,
        )
        self._patient_search_entry.grid(row=0, column=0, sticky="ew")

        # Patient results Treeview
        patient_columns = ("Patient", "Phone", "Email", "DOB")
        self._tree_patients = ttk.Treeview(
            card, columns=patient_columns, show="headings", height=6,
        )
        apply_treeview_style(self._tree_patients)
        for col in patient_columns:
            self._tree_patients.heading(col, text=col)
        self._tree_patients.column("Patient", width=180, anchor="w")
        self._tree_patients.column("Phone", width=100, anchor="w")
        self._tree_patients.column("Email", width=140, anchor="w")
        self._tree_patients.column("DOB", width=100, anchor="center")
        self._tree_patients.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))

        patient_scroll = ttk.Scrollbar(card, orient="vertical", command=self._tree_patients.yview)
        self._tree_patients.configure(yscrollcommand=patient_scroll.set)
        patient_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=(0, 12))

        self._tree_patients.bind("<ButtonRelease-1>", self._on_patient_select)
        self._tree_patients.tag_configure("even", background=_COLOR_BG, foreground=_COLOR_TEXT_PRIMARY)
        self._tree_patients.tag_configure("odd", background=_COLOR_BG_ALT, foreground=_COLOR_TEXT_PRIMARY)

        # Patient detail frame
        self._patient_detail_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._patient_detail_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        self._patient_detail_frame.grid_columnconfigure(1, weight=1)

        self._patient_name_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(weight="bold"),
            text_color=_COLOR_TEXT_PRIMARY,
        )
        self._patient_name_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 2))

        self._patient_dob_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._patient_dob_label.grid(row=1, column=0, sticky="w", pady=2)

        self._patient_phone_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._patient_phone_label.grid(row=2, column=0, sticky="w", pady=2)

        self._patient_address_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._patient_address_label.grid(row=3, column=0, sticky="w", pady=2)

        # Insurance detail (right side)
        self._patient_insurance_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_ACCENT,
        )
        self._patient_insurance_label.grid(row=0, column=1, sticky="e", pady=2)

        self._patient_ins_bin_label = ctk.CTkLabel(
            self._patient_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._patient_ins_bin_label.grid(row=1, column=1, sticky="e", pady=2)

        # Load all patients initially
        self._on_patient_search()

    def _build_step_medication(self, parent):
        """Step 2: Product/Medication Selection."""
        card = ctk.CTkFrame(parent, fg_color=_COLOR_CARD_MED, corner_radius=10)
        card.pack(fill="both", expand=True, padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("drug_selection"),
            font=ctk.CTkFont(size=16, weight="bold"), text_color=_COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        search_frame = ctk.CTkFrame(card, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)

        self._drug_search_var = ctk.StringVar()
        _debounced_search(search_frame, self._drug_search_var, self._on_drug_search)
        self._drug_search_entry = ctk.CTkEntry(
            search_frame, textvariable=self._drug_search_var,
            placeholder_text=i18n.t("search_ndc_or_drug"),
            width=360,
        )
        self._drug_search_entry.grid(row=0, column=0, sticky="ew")

        pres_labels = _get_prescriber_labels(self._region)
        self._drug_code_label_ref = ctk.CTkLabel(
            search_frame,
            text=pres_labels.get("drug_code_label", self._labels.get("drug_name", "Drug Name")),
            font=ctk.CTkFont(size=11, weight="bold"), text_color=_COLOR_TEXT_SECONDARY,
        )
        self._drug_code_label_ref.grid(row=0, column=1, sticky="w", padx=(8, 0))

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
        self._tree_drugs.tag_configure("even", background=_COLOR_BG, foreground=_COLOR_TEXT_PRIMARY)
        self._tree_drugs.tag_configure("odd", background=_COLOR_BG_ALT, foreground=_COLOR_TEXT_PRIMARY)

        # Drug detail frame
        self._drug_detail_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._drug_detail_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

        self._drug_name_value_label = ctk.CTkLabel(
            self._drug_detail_frame, text="", font=ctk.CTkFont(weight="bold"),
            text_color=_COLOR_TEXT_PRIMARY,
        )
        self._drug_name_value_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=2)

        self._drug_strength_form_label = ctk.CTkLabel(
            self._drug_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._drug_strength_form_label.grid(row=1, column=0, sticky="w", pady=2)

        self._drug_lot_expiry_label = ctk.CTkLabel(
            self._drug_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._drug_lot_expiry_label.grid(row=2, column=0, sticky="w", pady=2)

        self._drug_supplier_label = ctk.CTkLabel(
            self._drug_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._drug_supplier_label.grid(row=3, column=0, sticky="w", pady=2)

        # Load all inventory initially
        self._on_drug_search()

    def _build_step_prescription(self, parent):
        """Step 3: Prescription Details & Authorization."""
        card = ctk.CTkFrame(parent, fg_color=_COLOR_CARD_DARK, corner_radius=10)
        card.pack(fill="both", expand=True, padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("step_prescription"),
            font=ctk.CTkFont(size=16, weight="bold"), text_color=_COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        # ── Prescriber search ──
        pres_frame = ctk.CTkFrame(card, fg_color="transparent")
        pres_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        pres_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            pres_frame, text=i18n.t("veterinarian_prescriber"),
            font=ctk.CTkFont(size=12, weight="bold"), text_color=_COLOR_ACCENT,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._prescriber_search_var = ctk.StringVar()
        _debounced_search(pres_frame, self._prescriber_search_var, self._on_prescriber_search)
        self._prescriber_search_entry = ctk.CTkEntry(
            pres_frame, textvariable=self._prescriber_search_var,
            placeholder_text=i18n.t("prescriber_search_box_placeholder"),
            width=340,
        )
        self._prescriber_search_entry.grid(row=1, column=0, sticky="w")

        prescriber_columns = ("Veterinarian/Prescriber", "NPI/ID", "License", "Phone")
        self._tree_prescribers = ttk.Treeview(
            pres_frame, columns=prescriber_columns, show="headings", height=4,
        )
        apply_treeview_style(self._tree_prescribers)
        for col in prescriber_columns:
            self._tree_prescribers.heading(col, text=col)
        self._tree_prescribers.column("Veterinarian/Prescriber", width=180, anchor="w")
        self._tree_prescribers.column("NPI/ID", width=100, anchor="w")
        self._tree_prescribers.column("License", width=100, anchor="w")
        self._tree_prescribers.column("Phone", width=100, anchor="w")
        self._tree_prescribers.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        pres_scroll = ttk.Scrollbar(pres_frame, orient="vertical", command=self._tree_prescribers.yview)
        self._tree_prescribers.configure(yscrollcommand=pres_scroll.set)
        pres_scroll.grid(row=2, column=1, sticky="ns", padx=(4, 0))

        self._tree_prescribers.bind("<ButtonRelease-1>", self._on_prescriber_select)
        self._tree_prescribers.tag_configure("even", background=_COLOR_BG, foreground=_COLOR_TEXT_PRIMARY)
        self._tree_prescribers.tag_configure("odd", background=_COLOR_BG_ALT, foreground=_COLOR_TEXT_PRIMARY)

        # Prescriber detail
        self._prescriber_detail_frame = ctk.CTkFrame(pres_frame, fg_color="transparent")
        self._prescriber_detail_frame.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._prescriber_detail_frame.grid_columnconfigure(1, weight=1)

        self._prescriber_name_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(weight="bold"),
            text_color=_COLOR_TEXT_PRIMARY,
        )
        self._prescriber_name_label.grid(row=0, column=0, sticky="w", pady=2)

        pres_labels = _get_prescriber_labels(self._region)
        self._prescriber_id_label_ref = ctk.CTkLabel(
            self._prescriber_detail_frame,
            text=pres_labels.get("prescriber_id_label", "NPI"),
            font=ctk.CTkFont(size=10, weight="bold"), text_color=_COLOR_TEXT_SECONDARY,
        )
        self._prescriber_id_label_ref.grid(row=0, column=1, sticky="e", pady=2)

        self._prescriber_id_value_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_PRIMARY,
        )
        self._prescriber_id_value_label.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=2)

        self._prescriber_license_value_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._prescriber_license_value_label.grid(row=1, column=0, sticky="w", pady=2)

        self._state_license_label_ref = ctk.CTkLabel(
            self._prescriber_detail_frame,
            text=pres_labels.get("state_field_label", "State License"),
            font=ctk.CTkFont(size=10, weight="bold"), text_color=_COLOR_TEXT_SECONDARY,
        )
        self._state_license_label_ref.grid(row=1, column=1, sticky="e", pady=2)

        self._prescriber_phone_value_label = ctk.CTkLabel(
            self._prescriber_detail_frame, text="", font=ctk.CTkFont(size=11),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._prescriber_phone_value_label.grid(row=1, column=2, sticky="e", padx=(8, 0), pady=2)

        # ── Prescription form fields ──
        form_grid = ctk.CTkFrame(card, fg_color="transparent")
        form_grid.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        form_grid.grid_columnconfigure(1, weight=1)

        _form_field = lambda r, label_text, var_widget, pady=(0, 4): None

        # Quantity
        ctk.CTkLabel(
            form_grid, text=f"{i18n.t('quantity')}:", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_COLOR_TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._qty_entry = ctk.CTkEntry(form_grid, width=100, textvariable=self._qty_var)
        self._qty_entry.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 4))

        # Frequency
        ctk.CTkLabel(
            form_grid, text=f"{i18n.t('frequency')}:", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_COLOR_TEXT_SECONDARY,
        ).grid(row=1, column=0, sticky="w", pady=(4, 4))
        self._frequency_combo = ctk.CTkComboBox(
            form_grid, values=_FREQUENCY_OPTIONS, variable=self._frequency_var, width=140,
        )
        self._frequency_combo.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(4, 4))

        # Duration
        ctk.CTkLabel(
            form_grid, text=f"{i18n.t('duration_days')}:", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_COLOR_TEXT_SECONDARY,
        ).grid(row=2, column=0, sticky="w", pady=(4, 4))
        self._duration_entry = ctk.CTkEntry(form_grid, width=100, textvariable=self._duration_var)
        self._duration_entry.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(4, 4))

        # Refills
        ctk.CTkLabel(
            form_grid, text=f"{i18n.t('refills')}:", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_COLOR_TEXT_SECONDARY,
        ).grid(row=3, column=0, sticky="w", pady=(4, 4))
        self._refills_entry = ctk.CTkEntry(form_grid, width=100, textvariable=self._refills_var)
        self._refills_entry.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(4, 4))

        # DAW Code (region-aware)
        self._daw_label_ref = ctk.CTkLabel(
            form_grid, text=f"{i18n.t('daw_code')}:", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_COLOR_TEXT_SECONDARY,
        )
        self._daw_label_ref.grid(row=4, column=0, sticky="w", pady=(4, 4))
        self._daw_entry = ctk.CTkEntry(form_grid, width=100, textvariable=self._daw_var)
        self._daw_entry.grid(row=4, column=1, sticky="w", padx=(12, 0), pady=(4, 4))

        # Directions / SIG
        ctk.CTkLabel(
            form_grid, text=f"{i18n.t('directions')}:", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_COLOR_TEXT_SECONDARY,
        ).grid(row=5, column=0, sticky="nw", pady=(8, 4))
        self._directions_entry = ctk.CTkEntry(
            form_grid, width=340, textvariable=self._directions_var,
            placeholder_text=i18n.t("directions_placeholder"),
        )
        self._directions_entry.grid(row=5, column=1, sticky="ew", padx=(12, 0), pady=(8, 4))

        # Special Notes
        ctk.CTkLabel(
            form_grid, text=f"{i18n.t('special_notes')}:", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_COLOR_TEXT_SECONDARY,
        ).grid(row=6, column=0, sticky="nw", pady=(8, 4))
        self._notes_entry = ctk.CTkEntry(
            form_grid, width=340, textvariable=self._notes_var,
            placeholder_text=i18n.t("notes_placeholder"),
        )
        self._notes_entry.grid(row=6, column=1, sticky="ew", padx=(12, 0), pady=(8, 4))

        # Cost display
        cost_frame = ctk.CTkFrame(card, fg_color="transparent")
        cost_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        cost_frame.grid_columnconfigure(0, weight=1)

        self._patient_cost_label = ctk.CTkLabel(
            cost_frame, text=f"{i18n.t('patient_cost')}: $0.00",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_COLOR_SUCCESS,
        )
        self._patient_cost_label.pack(side="left", padx=(0, 16))

        self._insurance_cost_label = ctk.CTkLabel(
            cost_frame, text=f"{i18n.t('insurance_cost')}: $0.00",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_COLOR_ACCENT,
        )
        self._insurance_cost_label.pack(side="left")

        self._update_cost_display()

    def _build_action_bar(self):
        """Action bar with Back/Next + conditional action buttons."""
        bar = ctk.CTkFrame(self, fg_color=_COLOR_CARD_MED, corner_radius=10, height=64)
        bar.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))
        bar.pack_propagate(False)
        bar.grid_columnconfigure(0, weight=1)

        # Navigation buttons (always visible)
        nav_frame = ctk.CTkFrame(bar, fg_color="transparent")
        nav_frame.grid(row=0, column=0, sticky="w", padx=16, pady=16)

        self._back_btn = ctk.CTkButton(
            nav_frame, text=i18n.t("back"), width=90,
            fg_color="#6c757d", hover_color="#5a6268",
            command=self._on_back,
        )
        self._back_btn.pack(side="left", padx=(0, 8))

        self._next_btn = ctk.CTkButton(
            nav_frame, text=i18n.t("next"), width=90,
            fg_color=_COLOR_ACCENT, hover_color="#2563EB",
            command=self._on_next,
        )
        self._next_btn.pack(side="left")

        # Action buttons (visible only on step 3)
        self._action_buttons_frame = ctk.CTkFrame(bar, fg_color="transparent")
        self._action_buttons_frame.grid(row=0, column=1, sticky="e", padx=(0, 16), pady=16)

        self._btn_save_draft = ctk.CTkButton(
            self._action_buttons_frame, text=i18n.t("save_draft"), width=120,
            fg_color=_COLOR_WARNING, hover_color="#d97706",
            command=self._on_save_draft,
        )
        self._btn_save_draft.pack(side="right", padx=(4, 0))

        self._btn_print_fax = ctk.CTkButton(
            self._action_buttons_frame, text=i18n.t("print_fax"), width=120,
            fg_color="#6c757d", hover_color="#5a6268",
            command=self._on_print_fax,
        )
        self._btn_print_fax.pack(side="right", padx=(4, 0))

        self._btn_save_inbox = ctk.CTkButton(
            self._action_buttons_frame, text=i18n.t("save_to_inbox"), width=120,
            fg_color="#6c757d", hover_color="#5a6268",
            command=self._on_save_inbox,
        )
        self._btn_save_inbox.pack(side="right", padx=(4, 0))

        self._btn_submit_authorize = ctk.CTkButton(
            self._action_buttons_frame, text=i18n.t("submit_authorize"), width=140,
            fg_color=_COLOR_SUCCESS, hover_color="#059669",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_submit_authorize,
        )
        self._btn_submit_authorize.pack(side="right")

        self._update_action_button_visibility()

    def _update_action_button_visibility(self):
        """Enable action buttons only on step 3 (prescription details)."""
        is_step_3 = self._current_step == 2
        state = "normal" if is_step_3 else "disabled"
        self._btn_save_draft.configure(state=state)
        self._btn_print_fax.configure(state=state)
        self._btn_save_inbox.configure(state=state)
        self._btn_submit_authorize.configure(state=state)

    # ── Event Handlers ──

    def _on_patient_search(self, event=None):
        """Search patients by name via database.get_all_patients()."""
        query = self._patient_search_var.get().strip()
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
        """Populate patient search results Treeview (runs on main thread)."""
        if error:
            log.warning("Patient search error: %s", error)
            return
        for item in self._tree_patients.get_children():
            self._tree_patients.delete(item)
        if not results:
            return
        for idx, row in enumerate(results):
            tag = "even" if idx % 2 == 0 else "odd"
            # row: (pid, name, phone, email, created_at, {fields})
            name = row[1] if len(row) > 1 else ""
            phone = row[2] if len(row) > 2 else ""
            email = row[3] if len(row) > 3 else ""
            fields = row[5] if len(row) > 5 else {}
            dob = fields.get("DOB", "") if isinstance(fields, dict) else ""
            self._tree_patients.insert("", "end", values=(
                name, phone, email, dob
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

        name = self._selected_patient[1] if len(self._selected_patient) > 1 else ""
        phone = self._selected_patient[2] if len(self._selected_patient) > 2 else ""
        email = self._selected_patient[3] if len(self._selected_patient) > 3 else ""
        fields = self._selected_patient[5] if len(self._selected_patient) > 5 else {}
        if not isinstance(fields, dict):
            fields = {}

        self._patient_name_label.configure(text=f"  {name}")
        self._patient_dob_label.configure(
            text=f"  DOB: {fields.get('DOB', '')}" if fields.get("DOB") else "  DOB: \u2014"
        )
        self._patient_phone_label.configure(
            text=f"  Phone: {phone}" if phone else "  Phone: \u2014"
        )
        addr = fields.get("Address", "")
        self._patient_address_label.configure(
            text=f"  Address: {addr}" if addr else "  Address: \u2014"
        )

        # Insurance display
        try:
            ins_rows = _rx_db.get_insurance_by_patient(self._selected_patient_id) \
                if (_HAS_RX_DB and _rx_db.HAS_SQLALCHEMY) else []
        except Exception as e:
            log.debug("Insurance lookup failed: %s", e)
            ins_rows = []

        if ins_rows:
            first = ins_rows[0]
            carrier = first[6] if len(first) > 6 else ""
            bin_num = first[2] if len(first) > 2 else ""
            plan = first[5] if len(first) > 5 else ""
            self._patient_insurance_label.configure(
                text=f"  {carrier or plan or 'N/A'}"
            )
            bin_label = _get_prescriber_labels(self._region).get("insurance_bin_label", "BIN")
            self._patient_ins_bin_label.configure(
                text=f"  {bin_label}: {bin_num or '\u2014'}"
            )
        else:
            self._patient_insurance_label.configure(text="  None")
            self._patient_ins_bin_label.configure(text="")

        log.debug("Selected patient: id=%s name=%s", self._selected_patient_id, name)

    def _on_drug_search(self, event=None):
        """Search inventory by NDC/PZN or drug name."""
        query = self._drug_search_var.get().strip()
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
        if error:
            log.warning("Drug search error: %s", error)
            return
        for item in self._tree_drugs.get_children():
            self._tree_drugs.delete(item)
        if not results:
            return
        for idx, row in enumerate(results):
            tag = "even" if idx % 2 == 0 else "odd"
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
        """Load drug details when a drug is selected."""
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
        mac = self._selected_drug[7] if len(self._selected_drug) > 7 else 0.0
        lot = self._selected_drug[8] if len(self._selected_drug) > 8 else ""
        exp = self._selected_drug[9] if len(self._selected_drug) > 9 else ""
        supplier = self._selected_drug[11] if len(self._selected_drug) > 11 else ""

        self._drug_name_value_label.configure(text=name or "\u2014")
        self._drug_strength_form_label.configure(
            text=f"Strength: {strength or '\u2014'}  |  Form: {form or '\u2014'}"
        )
        self._drug_lot_expiry_label.configure(
            text=f"Lot: {lot or '\u2014'}  |  Expiry: {exp or '\u2014'}"
        )
        self._drug_supplier_label.configure(
            text=f"Supplier: {supplier or 'N/A'}  |  AWP: {self.app.currency.fmt(awp)}"
        )
        self._drug_awp = float(awp) if awp else 0.0

        self._calculate_cost_preview()
        log.debug("Selected drug: ndc=%s name=%s", self._selected_drug_ndc, name)

    def _on_prescriber_search(self, event=None):
        """Search prescribers (including veterinarians) by name/NPI/DEA/license."""
        query = self._prescriber_search_var.get().strip()
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
        if error:
            log.warning("Prescriber search error: %s", error)
            return
        for item in self._tree_prescribers.get_children():
            self._tree_prescribers.delete(item)
        if not results:
            return
        for idx, row in enumerate(results):
            tag = "even" if idx % 2 == 0 else "odd"
            display = _resolve_prescriber_display(row)
            self._tree_prescribers.insert("", "end", values=(
                display["name"],
                display["id_value"],
                display["license"] or display["dea"] or "\u2014",
                display["phone"] or "\u2014",
            ), tags=(tag,))

    def _on_prescriber_select(self, event=None):
        """Load prescriber details when selected (handles veterinarian NPI-null)."""
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

        display = _resolve_prescriber_display(self._selected_prescriber)
        self._prescriber_display = display
        self._prescriber_name_label.configure(text=f"  {display['name']}")
        self._prescriber_id_value_label.configure(text=display["id_value"] or "\u2014")
        self._prescriber_license_value_label.configure(
            text=f"License: {display['license'] or '\u2014'}"
        )
        self._prescriber_phone_value_label.configure(text=display["phone"] or "")

        log.debug("Selected prescriber: id=%s name=%s (npi=%s)",
                   self._selected_prescriber_id, display["name"], display["npi"])

    def _on_back(self):
        """Navigate to the previous wizard step."""
        if self._current_step > 0:
            self._current_step -= 1
            self._show_step(_WIZARD_STEPS[self._current_step])
            self._update_action_button_visibility()

    def _on_next(self):
        """Validate current step and advance to the next."""
        step_key = _WIZARD_STEPS[self._current_step]
        if not self._validate_step(step_key):
            return
        if self._current_step < len(_WIZARD_STEPS) - 1:
            self._current_step += 1
            self._show_step(_WIZARD_STEPS[self._current_step])
            self._update_action_button_visibility()
        else:
            messagebox.showinfo(
                i18n.t("epcs_workflow"),
                i18n.t("submit_authorize"),
                parent=self,
            )

    def _validate_step(self, step_key: str) -> bool:
        """Validate that the required fields for the given step are complete."""
        if step_key == "step_patient":
            if self._selected_patient_id is None:
                messagebox.showwarning(
                    i18n.t("warning"), i18n.t("patient_required"), parent=self
                )
                return False
            return True
        elif step_key == "step_medication":
            if self._selected_drug_ndc is None:
                messagebox.showwarning(
                    i18n.t("warning"), i18n.t("drug_required"), parent=self
                )
                return False
            return True
        elif step_key == "step_prescription":
            if self._selected_prescriber_id is None:
                messagebox.showwarning(
                    i18n.t("warning"), i18n.t("prescriber_required"), parent=self
                )
                return False
            qty_str = self._qty_var.get().strip()
            try:
                qty = int(qty_str)
            except ValueError:
                messagebox.showwarning(
                    i18n.t("warning"), i18n.t("insufficient_fields"), parent=self
                )
                return False
            if qty <= 0:
                messagebox.showwarning(
                    i18n.t("warning"), i18n.t("quantity_must_be_positive"), parent=self
                )
                return False
            if not self._directions_var.get().strip():
                messagebox.showwarning(
                    i18n.t("warning"), i18n.t("insufficient_fields"), parent=self
                )
                return False
            return True
        return False

    def _calculate_cost_preview(self):
        """Calculate patient/insurance cost preview based on selected drug + qty."""
        try:
            qty = int(self._qty_var.get().strip() or "0")
        except ValueError:
            qty = 0
        unit_price = self._drug_awp
        base_cost = unit_price * qty
        self._patient_cost_val = 0.0
        self._insurance_cost_val = 0.0
        # Use strategy for cost calc if available
        try:
            self._strategy = strategy_factory(self._region)
            coverage = {"coinsurance_rate": 0.2, "copay": 5.0}
            if self._region != "US":
                coverage = {"vat_rate": 0.2, "patient_contribution": 0.1}
            self._patient_cost_val = self._strategy.calculate_patient_cost(
                unit_price, max(qty, 1), coverage
            )
            self._insurance_cost_val = round(base_cost - self._patient_cost_val, 2)
        except Exception as e:
            log.debug("Cost calculation failed: %s", e)
            self._patient_cost_val = base_cost
        self._update_cost_display()

    def _update_cost_display(self):
        """Update the patient/insurance cost display labels."""
        self._patient_cost_label.configure(
            text=f"{i18n.t('patient_cost')}: {self.app.currency.fmt(self._patient_cost_val)}"
        )
        self._insurance_cost_label.configure(
            text=f"{i18n.t('insurance_cost')}: {self.app.currency.fmt(self._insurance_cost_val)}"
        )

    def _on_save_draft(self):
        """Save the prescription as a draft (status='Pending', not billed)."""
        if not self._validate_step("step_prescription"):
            return
        region = _get_rx_region()
        sig = self._directions_var.get().strip()
        freq = self._frequency_var.get().strip()
        full_sig = f"{sig} ({freq})" if freq else sig
        notes = self._notes_var.get().strip()
        notes_with_tag = f"{notes} {DRAFT_SUFFIX}".strip()
        now_str = datetime.now().strftime("%Y-%m-%d")

        regional_metadata = {"region": region, "source": "epcs_workflow", "status": "draft"}

        rx_id = _create_prescription_record(
            region,
            patient_id=self._selected_patient_id,
            prescriber_id=self._selected_prescriber_id,
            drug_ndc=self._selected_drug_ndc,
            days_supply=self._parse_int(self._duration_var.get()),
            daw_code=self._daw_var.get().strip() or "00",
            refills=self._parse_int(self._refills_var.get()),
            sig_code=full_sig,
            quantity=self._parse_int(self._qty_var.get()),
            date_prescribed=now_str,
            notes=notes_with_tag,
            regional_metadata=regional_metadata,
        )

        if rx_id is None:
            messagebox.showerror(i18n.t("error"), "Failed to save draft.", parent=self)
            return

        self._draft_rx_id = rx_id
        audit_log.log_action(
            "EPCS_DRAFT",
            f"Rx #{rx_id} saved as draft | Patient: {self._selected_patient_id} | "
            f"Drug: {self._selected_drug_ndc}",
        )
        messagebox.showinfo(
            i18n.t("success"),
            i18n.t("draft_saved").format(rx_id=rx_id),
            parent=self,
        )
        self._refresh_all_queues()

    def _on_save_inbox(self):
        """Save the prescription to the inbox (status='Pending', inbox metadata)."""
        if not self._validate_step("step_prescription"):
            return
        region = _get_rx_region()
        sig = self._directions_var.get().strip()
        freq = self._frequency_var.get().strip()
        full_sig = f"{sig} ({freq})" if freq else sig
        notes = self._notes_var.get().strip()
        notes_with_tag = f"{notes} {INBOX_SUFFIX}".strip()
        now_str = datetime.now().strftime("%Y-%m-%d")

        regional_metadata = {
            "region": region,
            "source": "epcs_workflow",
            "status": "inbox",
            "inbox_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        rx_id = _create_prescription_record(
            region,
            patient_id=self._selected_patient_id,
            prescriber_id=self._selected_prescriber_id,
            drug_ndc=self._selected_drug_ndc,
            days_supply=self._parse_int(self._duration_var.get()),
            daw_code=self._daw_var.get().strip() or "00",
            refills=self._parse_int(self._refills_var.get()),
            sig_code=full_sig,
            quantity=self._parse_int(self._qty_var.get()),
            date_prescribed=now_str,
            notes=notes_with_tag,
            regional_metadata=regional_metadata,
        )

        if rx_id is None:
            messagebox.showerror(i18n.t("error"), "Failed to save to inbox.", parent=self)
            return

        self._draft_rx_id = rx_id
        audit_log.log_action(
            "EPCS_INBOX",
            f"Rx #{rx_id} saved to inbox | Patient: {self._selected_patient_id} | "
            f"Drug: {self._selected_drug_ndc}",
        )
        messagebox.showinfo(
            i18n.t("success"),
            i18n.t("inbox_saved").format(rx_id=rx_id),
            parent=self,
        )

    def _on_print_fax(self):
        """Generate a printable/faxable prescription form."""
        if not self._validate_step("step_prescription"):
            return
        prescription_data = self._gather_prescription_data()
        if self._draft_rx_id:
            try:
                rx_rec = (_rx_db.get_rx_by_id(self._draft_rx_id)
                          if (_HAS_RX_DB and _rx_db.HAS_SQLALCHEMY) else None)
                if rx_rec and len(rx_rec) > 1:
                    self._latest_rx_number = rx_rec[1]
            except Exception:
                pass
            prescription_data["rx_number"] = self._latest_rx_number
        else:
            prescription_data["rx_number"] = f"DRAFT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        text_content = _format_prescription_text(prescription_data)

        try:
            if os.name == "nt":
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                )
                tmp.write(text_content)
                tmp.close()
                os.startfile(tmp.name, "open")
            else:
                import subprocess
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                )
                tmp.write(text_content)
                tmp.close()
                subprocess.Popen(["xdg-open", tmp.name],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            audit_log.log_action(
                "EPCS_PRINT_FAX",
                f"Prescription printed/faxed | Patient: {self._selected_patient_id} | "
                f"Drug: {self._selected_drug_ndc}",
            )
        except Exception as e:
            log.error("Print/Fax failed: %s", e)
            messagebox.showerror(i18n.t("error"), f"Print/Fax failed:\n{e}", parent=self)

    def _on_submit_authorize(self):
        """Full EPCS submission: authenticate → validate → claim → persist → authorize."""
        if not self._validate_step("step_prescription"):
            return
        region = _get_rx_region()
        strategy = strategy_factory(region)
        self._strategy = strategy

        sig = self._directions_var.get().strip()
        freq = self._frequency_var.get().strip()
        full_sig = f"{sig} ({freq})" if freq else sig
        qty = self._parse_int(self._qty_var.get())
        duration = self._parse_int(self._duration_var.get())
        refills = self._parse_int(self._refills_var.get())
        daw_code = self._daw_var.get().strip() or "00"
        notes = self._notes_var.get().strip()
        now_str = datetime.now().strftime("%Y-%m-%d")

        # ── Gather prescriber identifier (NPI for US, ODS/license for EU) ──
        prescriber_id_val = ""
        if self._selected_prescriber:
            npi = self._selected_prescriber[1] if len(self._selected_prescriber) > 1 else ""
            dea = self._selected_prescriber[2] if len(self._selected_prescriber) > 2 else ""
            license_val = self._selected_prescriber[3] if len(self._selected_prescriber) > 3 else ""
            prescriber_id_val = npi or dea or license_val

        # ── Gather insurance info ──
        insurance_coverage = None
        insurance_id = ""
        try:
            if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
                ins_rows = _rx_db.get_insurance_by_patient(self._selected_patient_id)
                if ins_rows:
                    first = ins_rows[0]
                    bin_num = first[2] if len(first) > 2 else ""
                    pcn = first[3] if len(first) > 3 else ""
                    plan = first[5] if len(first) > 5 else ""
                    insurance_coverage = {"coinsurance_rate": 0.2, "copay": 5.0}
                    if region == "US":
                        insurance_coverage["bin"] = bin_num
                        insurance_coverage["pcn"] = pcn
                        insurance_coverage["group_number"] = first[4] if len(first) > 4 else ""
                        insurance_coverage["plan_name"] = plan
                        insurance_coverage["carrier"] = first[6] if len(first) > 6 else ""
                    insurance_id = plan or bin_num
        except Exception as e:
            log.debug("Insurance lookup failed: %s", e)

        # ── Build claim_data ──
        drug_name = ""
        try:
            if _HAS_RX_DB and _rx_db.HAS_SQLALCHEMY:
                item = _rx_db.get_inventory_item(self._selected_drug_ndc)
                if item and len(item) > 2:
                    drug_name = item[2]
        except Exception:
            pass
        if not drug_name and self._selected_drug:
            drug_name = self._selected_drug[2] if len(self._selected_drug) > 2 else ""

        claim_data = {
            "drug_name": drug_name,
            "ndc": self._selected_drug_ndc,
            "quantity": qty,
            "days_supply": duration,
            "insurance_id": insurance_id,
            "prescriber_npi": prescriber_id_val if region == "US" else "",
            "pharmacy_npi": _get_pharmacy_info().get("pharmacy_npi", ""),
        }
        if region != "US":
            claim_data["nhs_number"] = ""
            claim_data["prescriber_ods"] = prescriber_id_val

        # ── Build prescription_data for validation ──
        prescription_data = {
            "drug_name": drug_name,
            "dosage": full_sig,
            "quantity": qty,
            "prescriber_npi": prescriber_id_val if region == "US" else "",
        }
        if region != "US":
            prescription_data["prescriber_ods"] = prescriber_id_val

        # ── Step 1: Authenticate via regional strategy ──
        credentials = {}
        try:
            if self._strategy:
                cm = ConfigManager()
                credentials = {
                    "api_key": cm.get_credential("api_key", region) or "",
                    "switch_id": cm.get_credential("switch_id", region) or "",
                    "fmd_api_key": cm.get_credential("fmd_api_key", region) or "",
                    "cert_path": cm.get_credential("cert_path", region) or "",
                    "pharmacy_npi": cm.get_credential("pharmacy_npi", region) or "",
                }
            success, message = strategy.authenticate(credentials)
            if not success:
                messagebox.showerror(
                    i18n.t("error"),
                    f"{i18n.t('authorize_failed').format(error=message)}",
                    parent=self,
                )
                return
        except Exception as e:
            log.error("EPCS authenticate error: %s", e)
            messagebox.showerror(
                i18n.t("error"),
                f"{i18n.t('authorize_failed').format(error=str(e))}",
                parent=self,
            )
            return

        # ── Step 2: Validate prescription ──
        try:
            strategy.validate_prescription(prescription_data)
        except ValueError as ve:
            messagebox.showerror(i18n.t("error"), str(ve), parent=self)
            return
        except Exception as e:
            messagebox.showerror(
                i18n.t("error"),
                f"Prescription validation failed:\n{e}",
                parent=self,
            )
            return

        # ── Step 3: Calculate patient cost ──
        unit_price = self._drug_awp
        try:
            self._patient_cost_val = strategy.calculate_patient_cost(
                unit_price, qty, insurance_coverage
            )
            self._insurance_cost_val = round((unit_price * qty) - self._patient_cost_val, 2)
        except Exception as e:
            log.warning("calculate_patient_cost failed: %s", e)
            self._patient_cost_val = unit_price * qty
            self._insurance_cost_val = 0.0
        self._update_cost_display()

        # ── Step 4: Generate claim ──
        try:
            claim_result = strategy.generate_claim(claim_data)
            self._claim_data = claim_result
        except Exception as e:
            log.warning("generate_claim failed: %s", e)
            self._claim_data = None

        # ── Step 5: Persist prescription via rx_db.add_rx_regional ──
        regional_metadata = {"region": region, "source": "epcs_workflow"}
        if region == "US":
            regional_metadata["claim_id"] = self._claim_data.get("claim_id", "") \
                if self._claim_data else ""
            regional_metadata["pcn"] = insurance_id
        else:
            regional_metadata["fmd_verification"] = ""
            regional_metadata["nhs_number"] = ""

        rx_id = _create_prescription_record(
            region,
            patient_id=self._selected_patient_id,
            prescriber_id=self._selected_prescriber_id,
            drug_ndc=self._selected_drug_ndc,
            days_supply=duration,
            daw_code=daw_code,
            refills=refills,
            sig_code=full_sig,
            quantity=qty,
            date_prescribed=now_str,
            notes=notes,
            regional_metadata=regional_metadata,
        )

        if rx_id is None:
            messagebox.showerror(
                i18n.t("error"), "Failed to create prescription record.", parent=self
            )
            return

        self._draft_rx_id = rx_id
        try:
            rx_rec = (_rx_db.get_rx_by_id(rx_id)
                      if (_HAS_RX_DB and _rx_db.HAS_SQLALCHEMY) else None)
            if rx_rec and len(rx_rec) > 1:
                self._latest_rx_number = rx_rec[1]
        except Exception:
            pass

        # ── Step 6: Update status to Billed (authorized) ──
        _set_rx_status(rx_id, "Billed", region=region)

        # ── Step 7: Audit log ──
        audit_log.log_action(
            "EPCS_SUBMIT",
            f"Rx #{rx_id} ({self._latest_rx_number}) authorized and submitted | "
            f"Patient: {self._selected_patient_id} | Drug: {self._selected_drug_ndc} | "
            f"Qty: {qty} | Patient cost: {self.app.currency.fmt(self._patient_cost_val)} | Region: {region}",
        )

        # ── Step 8: Success ──
        messagebox.showinfo(
            i18n.t("success"),
            i18n.t("claim_generated").format(rx_id=rx_id),
            parent=self,
        )
        self._on_clear_form()

    def _gather_prescription_data(self) -> dict:
        """Collect all form fields into a dict for printing/reporting."""
        return {
            "rx_number": self._latest_rx_number,
            "patient_name": self._selected_patient[1] if self._selected_patient and len(self._selected_patient) > 1 else "",
            "patient_dob": (self._selected_patient[5] or {}).get("DOB", "") if self._selected_patient and len(self._selected_patient) > 5 and isinstance(self._selected_patient[5], dict) else "",
            "patient_phone": self._selected_patient[2] if self._selected_patient and len(self._selected_patient) > 2 else "",
            "prescriber_name": self._prescriber_display.get("name", ""),
            "prescriber_id_label": self._prescriber_display.get("id_type", "NPI"),
            "prescriber_id_value": self._prescriber_display.get("id_value", ""),
            "prescriber_license": self._prescriber_display.get("license", ""),
            "drug_name": self._selected_drug[2] if self._selected_drug and len(self._selected_drug) > 2 else "",
            "drug_strength": self._selected_drug[3] if self._selected_drug and len(self._selected_drug) > 3 else "",
            "drug_form": self._selected_drug[4] if self._selected_drug and len(self._selected_drug) > 4 else "",
            "directions": self._directions_var.get().strip(),
            "frequency": self._frequency_var.get().strip(),
            "quantity": self._qty_var.get().strip(),
            "duration": self._duration_var.get().strip(),
            "refills": self._refills_var.get().strip(),
            "notes": self._notes_var.get().strip(),
        }

    def _on_clear_form(self):
        """Clear all form selections and entries, reset to step 1."""
        self._selected_patient_id = None
        self._selected_patient = None
        self._selected_drug_ndc = None
        self._selected_drug = None
        self._selected_prescriber_id = None
        self._selected_prescriber = None
        self._prescriber_display = {}
        self._drug_awp = 0.0
        self._patient_cost_val = 0.0
        self._insurance_cost_val = 0.0
        self._claim_data = None
        self._draft_rx_id = None
        self._latest_rx_number = ""

        self._directions_var.set("")
        self._frequency_var.set(_FREQUENCY_OPTIONS[0])
        self._qty_var.set("0")
        self._duration_var.set("30")
        self._refills_var.set("0")
        self._daw_var.set("00")
        self._notes_var.set("")

        self._patient_name_label.configure(text="")
        self._patient_dob_label.configure(text="")
        self._patient_phone_label.configure(text="")
        self._patient_address_label.configure(text="")
        self._patient_insurance_label.configure(text="")
        self._patient_ins_bin_label.configure(text="")

        self._prescriber_name_label.configure(text="")
        self._prescriber_id_value_label.configure(text="")
        self._prescriber_license_value_label.configure(text="")
        self._prescriber_phone_value_label.configure(text="")

        self._drug_name_value_label.configure(text="")
        self._drug_strength_form_label.configure(text="")
        self._drug_lot_expiry_label.configure(text="")
        self._drug_supplier_label.configure(text="")

        for item in self._tree_patients.get_children():
            self._tree_patients.delete(item)
        for item in self._tree_prescribers.get_children():
            self._tree_prescribers.delete(item)
        for item in self._tree_drugs.get_children():
            self._tree_drugs.delete(item)

        self._patient_search_var.set("")
        self._drug_search_var.set("")
        self._prescriber_search_var.set("")

        self._update_cost_display()
        self._current_step = 0
        self._show_step(_WIZARD_STEPS[self._current_step])
        self._update_action_button_visibility()
        self._on_patient_search()

    def _refresh_all_queues(self):
        """Refresh any queue displays. No-op by default — allows subclasses
        or integration hooks to extend with queue refreshes."""
        log.debug("EPCS workflow: _refresh_all_queues called (no-op)")

    def _parse_int(self, value: str, default: int = 0) -> int:
        """Safely parse an integer from a string."""
        try:
            return int(value.strip())
        except (ValueError, TypeError):
            return default

    def refresh(self):
        """Refresh the entire frame — called on tab switch."""
        old_region = self._region
        self._region = _get_rx_region()
        if self._region != old_region:
            self._labels = get_labels(self._region)
            self._refresh_labels()
        self._refresh_labels()
        self._update_cost_display()
        self._update_action_button_visibility()


# ── Module-level setup hooks (exact pattern from ui_pos_terminal.py) ──────

def setup_epcs_workflow_tab(self):
    """Create the EPCS Workflow tab inside PharmacyApp."""
    frame = EpcsWorkflowFrame(
        self.tab_epcs_workflow,
        fg_color="transparent",
    )
    frame.pack(fill="both", expand=True, padx=4, pady=4)
    self.epcs_workflow_frame = frame


def _refresh_epcs_workflow_tab(self):
    """Refresh hook called when the EPCS Workflow tab is activated."""
    if hasattr(self, "epcs_workflow_frame"):
        self.epcs_workflow_frame.refresh()
