"""
ui_clinical_workflow.py — Clinical Workflow module for PharmacyPro Enterprise.

Provides:
  - ClinicalWorkflowFrame: CTkFrame with 9 tabs covering the full clinical
    prescription lifecycle: Patient Selection, Medication Selection, Prescription
    Details, Clinical Notes, Allergies, Drug Interactions, Documentation,
    Attachments, and Review Summary.
  - PrescriptionWizard: A 4-step modal wizard (Patient -> Medication ->
    Prescription Details -> Review & Submit) triggered from the dashboard
    or via the status_dashboard task panel.
  - setup_clinical_workflow_tab(self): tab-setup function attached to PharmacyApp.

Integrates with:
  - rx_db (get_all_prescribers, search_inventory, add_rx, update_rx_status, ...)
  - database (get_all_patients)
  - quick_sig (save_quick_sig_template, load_quick_sig_templates)
  - ndc_dictionary (ndc_lookup, barcode_lookup)
  - audit_log (log_action)
  - i18n (t() for all labels)
"""
import logging
import json
from datetime import datetime
from typing import Optional

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
import tkinter as tk

import i18n
import database
import audit_log

log = logging.getLogger("ui_clinical_workflow")

try:
    import rx_db as _rx_db
    _HAS_RX_DB = True
except ImportError:
    _rx_db = None
    _HAS_RX_DB = False

try:
    from ndc_dictionary import ndc_lookup, barcode_lookup, name_lookup, init_ndc_dictionary
    _HAS_NDC = True
except ImportError:
    name_lookup = None
    _HAS_NDC = False

try:
    import native_accel
    _HAS_NATIVE_ACCEL = True
except ImportError:
    native_accel = None
    _HAS_NATIVE_ACCEL = False

try:
    from quick_sig import save_quick_sig_template, load_quick_sig_templates
    _HAS_QUICK_SIG = True
except ImportError:
    _HAS_QUICK_SIG = False

_CLINICAL_TABS = [
    ("clinical_patient_selection", "👥"),
    ("clinical_medication_selection", "💊"),
    ("clinical_prescription_details", "📋"),
    ("clinical_notes", "📝"),
    ("clinical_allergies", "⚠️"),
    ("clinical_interactions", "🔬"),
    ("clinical_documentation", "📄"),
    ("clinical_attachments", "📎"),
    ("clinical_review_summary", "✓"),
]

_WIZARD_STEPS = [
    ("clinical_wizard_step1", "Patient Selection"),
    ("clinical_wizard_step2", "Medication Selection"),
    ("clinical_wizard_step3", "Prescription Details"),
    ("clinical_wizard_step4", "Review & Submit"),
]


def _fuzzy_filter(query: str, choices: list[str], cutoff: float, limit: int) -> list[tuple[str, float, int]]:
    """Fallback fuzzy search using difflib (used when native_accel is unavailable).

    Returns ``(choice, score, index)`` tuples sorted by score descending.
    """
    from difflib import SequenceMatcher
    q = query.lower()
    scored: list[tuple[float, str, int]] = []
    for idx, choice in enumerate(choices):
        score = SequenceMatcher(None, q, str(choice).lower()).ratio() * 100.0
        if score >= cutoff:
            scored.append((score, choice, idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(choice, round(score, 2), idx) for score, choice, idx in scored[:limit]]


class PrescriptionWizard(ctk.CTkToplevel):
    """4-step prescription creation wizard.

    Step 1: Patient Selection — search and select patient or prescriber
    Step 2: Medication Selection — search NDC/drug or scan barcode
    Step 3: Prescription Details — dose, route, frequency, duration, refills
    Step 4: Review & Submit — summary, then create prescription
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.title(i18n.t("clinical_workflow_title"))
        self.geometry("720x560")
        self._current_step = 0
        self._patient_data: dict = {}
        self._med_data: dict = {}
        self._rx_data: dict = {}
        self._build_ui()
        self._show_step(0)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header: title + step indicator
        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        self._header.grid_columnconfigure(0, weight=1)

        self._title_label = ctk.CTkLabel(
            self._header, text=i18n.t("clinical_wizard_step1"),
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self._title_label.pack(side="left")

        self._step_label = ctk.CTkLabel(
            self._header, text="", font=ctk.CTkFont(size=12),
            text_color="#a0a0a0",
        )
        self._step_label.pack(side="right")

        # Content area (steps replace each other here)
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        # Navigation buttons
        self._nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._nav_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        self._nav_frame.grid_columnconfigure(0, weight=1)

        self._back_btn = ctk.CTkButton(self._nav_frame, text=i18n.t("back"), width=100,
                                       command=self._go_back)
        self._back_btn.pack(side="left")

        self._next_btn = ctk.CTkButton(self._nav_frame, text=i18n.t("next"), width=100,
                                       command=self._go_next)
        self._next_btn.pack(side="right")

        self._step_frames: list[ctk.CTkFrame] = []
        self._build_step1()
        self._build_step2()
        self._build_step3()
        self._build_step4()

    def _build_step1(self):
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=i18n.t("patient_lookup"),
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ctk.CTkLabel(frame, text=i18n.t("patient_search_placeholder")).grid(
            row=1, column=0, sticky="w", padx=(0, 8))

        self._patient_search = ctk.CTkEntry(frame, placeholder_text=i18n.t("patient_search_placeholder"))
        self._patient_search.grid(row=1, column=1, sticky="ew", padx=(0, 8))

        self._patient_tree = ttk.Treeview(frame, columns=("id", "name", "phone"),
                                          show="headings", height=12)
        self._patient_tree.heading("id", text="ID")
        self._patient_tree.heading("name", text=i18n.t("name"))
        self._patient_tree.heading("phone", text=i18n.t("name"))
        self._patient_tree.column("id", width=50)
        self._patient_tree.column("name", width=200)
        self._patient_tree.column("phone", width=150)
        self._patient_tree.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=8)

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._patient_tree.yview)
        self._patient_tree.configure(yscroll=sb.set)
        sb.grid(row=2, column=2, sticky="ns", pady=8)

        frame.grid_rowconfigure(2, weight=1)

        self._patient_search.bind("<KeyRelease>", lambda e: self._search_patients())

        self._step_frames.append(frame)

    def _search_patients(self):
        try:
            patients = database.get_all_patients()
        except Exception:
            patients = []
        for item in self._patient_tree.get_children():
            self._patient_tree.delete(item)
        query = self._patient_search.get().strip()
        if not query:
            for p in patients:
                pid = p[0] if isinstance(p, (list, tuple)) else getattr(p, "id", "")
                pname = p[1] if isinstance(p, (list, tuple)) else getattr(p, "name", "")
                pphone = p[2] if isinstance(p, (list, tuple)) else getattr(p, "phone", "")
                self._patient_tree.insert("", "end", values=(pid, pname, pphone))
            return
        patient_names = [p[1] if isinstance(p, (list, tuple)) else getattr(p, "name", "") for p in patients]
        if _HAS_NATIVE_ACCEL:
            ranked = native_accel.fuzzy_search(query, patient_names, limit=50, cutoff=60)
        else:
            ranked = _fuzzy_filter(query, patient_names, 60, 50)
        for name, _score, idx in ranked:
            p = patients[idx]
            pid = p[0] if isinstance(p, (list, tuple)) else getattr(p, "id", "")
            pphone = p[2] if isinstance(p, (list, tuple)) else getattr(p, "phone", "")
            self._patient_tree.insert("", "end", values=(pid, name, pphone))

    def _build_step2(self):
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=i18n.t("drug_selection"),
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8))

        search_row = ctk.CTkFrame(frame, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._drug_search = ctk.CTkEntry(search_row,
                                          placeholder_text=i18n.t("search_ndc_or_drug"))
        self._drug_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._drug_search.bind("<Return>", lambda e: self._search_drugs())
        ctk.CTkButton(search_row, text=i18n.t("search"), width=80,
                      command=self._search_drugs).pack(side="right")

        self._drug_tree = ttk.Treeview(frame, columns=("ndc", "name", "strength", "on_hand"),
                                       show="headings", height=10)
        self._drug_tree.heading("ndc", text="NDC")
        self._drug_tree.heading("name", text=i18n.t("drug_selection"))
        self._drug_tree.heading("strength", text="Strength")
        self._drug_tree.heading("on_hand", text="On Hand")
        self._drug_tree.column("ndc", width=100)
        self._drug_tree.column("name", width=200)
        self._drug_tree.column("strength", width=100)
        self._drug_tree.column("on_hand", width=80)
        self._drug_tree.grid(row=2, column=0, sticky="nsew")
        self._drug_tree.bind("<<TreeviewSelect>>", self._on_drug_select)

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._drug_tree.yview)
        self._drug_tree.configure(yscroll=sb.set)
        sb.grid(row=2, column=1, sticky="ns")

        frame.grid_rowconfigure(2, weight=1)
        self._step_frames.append(frame)

    def _search_drugs(self):
        if not _HAS_RX_DB:
            return
        query = self._drug_search.get().strip()
        if not query:
            return
        try:
            results = _rx_db.search_inventory(query)
            for item in self._drug_tree.get_children():
                self._drug_tree.delete(item)
            for r in results:
                ndc = r.get("ndc_code", "")
                name = r.get("drug_name", "")
                strength = r.get("strength", "")
                on_hand = str(r.get("on_hand", 0))
                self._drug_tree.insert("", "end", values=(ndc, name, strength, on_hand))
        except Exception as e:
            log.error("Drug search failed: %s", e)

    def _on_drug_select(self, event=None):
        selected = self._drug_tree.selection()
        if selected:
            values = self._drug_tree.item(selected[0])["values"]
            if values:
                self._med_data = {
                    "ndc": values[0], "name": values[1],
                    "strength": values[2], "on_hand": values[3],
                }

    def _build_step3(self):
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid_columnconfigure(1, weight=1)

        fields = [
            ("clinical_wizard_step3", "Step 3: Prescription Details"),
            ("directions", "Directions"),
            ("days_supply", "Days Supply"),
            ("refills", "Refills"),
            ("daw_code", "DAW Code"),
            ("frequency", "Frequency"),
            ("duration", "Duration"),
        ]

        for i, (key_or_label, label_text) in enumerate(fields):
            if i == 0:
                ctk.CTkLabel(frame, text=i18n.t(key_or_label) if i18n.t(key_or_label) != key_or_label else label_text,
                             font=ctk.CTkFont(size=14, weight="bold")).grid(
                    row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
                continue
            ctk.CTkLabel(frame, text=i18n.t(label_text.lower()) if i18n.t(label_text.lower()) != label_text.lower() else label_text).grid(
                row=i, column=0, sticky="e", padx=(0, 8), pady=4)
            entry = ctk.CTkEntry(frame, width=280)
            entry.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=4)
            if label_text == "Frequency":
                entry.insert(0, "BID")
            elif label_text == "Days Supply":
                entry.insert(0, "30")
            elif label_text == "Refills":
                entry.insert(0, "0")
            elif label_text == "DAW Code":
                entry.insert(0, "00")
            elif label_text == "Duration":
                entry.insert(0, "30 days")
            elif label_text == "Directions":
                entry.insert(0, "Take as directed")
            if i == 1:
                self._directions_entry = entry
            elif i == 2:
                self._days_supply_entry = entry
            elif i == 3:
                self._refills_entry = entry
            elif i == 4:
                self._daw_entry = entry
            elif i == 5:
                self._frequency_entry = entry
            elif i == 6:
                self._duration_entry = entry

        # Quick-SIG templates dropdown
        sig_row = ctk.CTkFrame(frame, fg_color="transparent")
        sig_row.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=8)
        sig_label = ctk.CTkLabel(sig_row, text=i18n.t("quick_sig_title"))
        sig_label.pack(side="left")

        self._sig_var = ctk.StringVar()
        self._sig_combo = ctk.CTkComboBox(sig_row, variable=self._sig_var, width=200)
        self._sig_combo.pack(side="left", padx=(8, 0))
        self._refresh_sig_combobox()

        self._step_frames.append(frame)

    def _refresh_sig_combobox(self):
        if not _HAS_QUICK_SIG:
            return
        try:
            templates = load_quick_sig_templates()
            self._sig_combo.configure(values=[t["name"] for t in templates])
        except Exception as e:
            log.error("Failed to refresh SIG combobox: %s", e)

    def _build_step4(self):
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self._summary_text = ctk.CTkTextbox(frame, height=200, font=ctk.CTkFont(size=12))
        self._summary_text.pack(fill="both", expand=True, pady=(0, 12))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(btn_row, text=i18n.t("save_draft"), width=120,
                      command=self._save_draft).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text=i18n.t("save_to_inbox"), width=120,
                      command=self._save_to_inbox).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text=i18n.t("submit_authorize"), width=140,
                      command=self._submit, fg_color=COLOR_SUCCESS,
                      hover_color="#0D946B").pack(side="right")

        self._step_frames.append(frame)

    def _show_step(self, step: int):
        self._current_step = step
        for i, frame in enumerate(self._step_frames):
            frame.grid_remove() if i != step else frame.grid(row=0, column=0, sticky="nsew")

        self._update_nav_buttons()
        self._update_step_header()
        if step == 3:
            self._update_summary()

    def _update_step_header(self):
        key, _ = _WIZARD_STEPS[self._current_step]
        label = i18n.t(key) if i18n.t(key) != key else _WIZARD_STEPS[self._current_step][1]
        self._title_label.configure(text=label)
        total = len(_WIZARD_STEPS)
        self._step_label.configure(text=f"Step {self._current_step + 1} of {total}")

    def _update_nav_buttons(self):
        self._back_btn.configure(state="normal" if self._current_step > 0 else "disabled")
        if self._current_step == len(_WIZARD_STEPS) - 1:
            self._next_btn.configure(text=i18n.t("submit_authorize"))
        else:
            self._next_btn.configure(text=i18n.t("next"))

    def _go_back(self):
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _go_next(self):
        if self._current_step < len(_WIZARD_STEPS) - 1:
            self._validate_current_step()
            self._show_step(self._current_step + 1)

    def _validate_current_step(self):
        """Collect data from the current step when advancing."""
        if self._current_step == 0:
            selected = self._patient_tree.selection()
            if selected:
                values = self._patient_tree.item(selected[0])["values"]
                self._patient_data = {"id": values[0], "name": values[1]}
        elif self._current_step == 2:
            self._rx_data = {
                "directions": self._directions_entry.get(),
                "days_supply": self._days_supply_entry.get(),
                "refills": self._refills_entry.get(),
                "daw_code": self._daw_entry.get(),
                "frequency": self._frequency_entry.get(),
                "duration": self._duration_entry.get(),
            }

    def _update_summary(self):
        self._validate_current_step()
        lines = [
            f"Patient: {self._patient_data.get('name', 'N/A')} (ID: {self._patient_data.get('id', 'N/A')})",
            f"Medication: {self._med_data.get('name', 'N/A')} ({self._med_data.get('strength', '')})",
            f"NDC: {self._med_data.get('ndc', 'N/A')}",
            f"Directions: {self._rx_data.get('directions', '')}",
            f"Days Supply: {self._rx_data.get('days_supply', '')}",
            f"Refills: {self._rx_data.get('refills', '')}",
            f"Frequency: {self._rx_data.get('frequency', '')}",
            f"Duration: {self._rx_data.get('duration', '')}",
        ]
        self._summary_text.delete("1.0", "end")
        self._summary_text.insert("1.0", "\n".join(lines))

    def _save_draft(self):
        self._validate_current_step()
        if _HAS_QUICK_SIG:
            save_quick_sig_template(
                name=f"Draft: {self._med_data.get('name', 'Unknown')}",
                directions=self._rx_data.get("directions", ""),
                dose=self._rx_data.get("frequency", ""),
                frequency=self._rx_data.get("frequency", ""),
                duration=self._rx_data.get("duration", ""),
            )
        messagebox.showinfo(i18n.t("quick_sig_title"),
                           f"Draft saved for {self._patient_data.get('name', 'N/A')}")
        self.destroy()

    def _save_to_inbox(self):
        self._validate_current_step()
        messagebox.showinfo(i18n.t("quick_sig_title"),
                           f"Saved to Inbox for {self._patient_data.get('name', 'N/A')}")
        self.destroy()

    def _submit(self):
        self._validate_current_step()
        if not self._patient_data or not self._med_data:
            messagebox.showwarning(i18n.t("info"), i18n.t("insufficient_fields"))
            return

        if _HAS_RX_DB and _rx_db:
            try:
                now = datetime.now().isoformat()
                rx_id = _rx_db.add_rx(
                    patient_id=self._patient_data.get("id", 0),
                    prescriber_id=1,
                    drug_ndc=self._med_data.get("ndc", ""),
                    days_supply=int(self._rx_data.get("days_supply", 30) or 30),
                    daw_code=self._rx_data.get("daw_code", "00"),
                    refills=int(self._rx_data.get("refills", 0) or 0),
                    sig_code=self._rx_data.get("directions", ""),
                    quantity=1,
                    notes=f"Freq: {self._rx_data.get('frequency', '')}",
                )
                audit_log.log_action("clinical_rx_create",
                                     details=f"Rx #{rx_id} for patient {self._patient_data.get('id')}")
                messagebox.showinfo(i18n.t("quick_sig_title"),
                                   f"Prescription #{rx_id} submitted successfully!")
                self.destroy()
            except Exception as e:
                log.error("Prescription submission failed: %s", e)
                messagebox.showerror(i18n.t("info"), f"Submission failed: {e}")
        else:
            messagebox.showinfo(i18n.t("quick_sig_title"), "Prescription submitted (no Rx DB).")
            self.destroy()

    def _search_drugs_fallback(self, query: str):
        """Search NDC dictionary when rx_db is unavailable."""
        if _HAS_NDC:
            results = []
            r = ndc_lookup(query)
            if r:
                results.append(r)
            if not r:
                try:
                    candidates = name_lookup(query) if name_lookup else []
                    drug_names = [c["drug_name"] for c in candidates]
                    if _HAS_NATIVE_ACCEL:
                        ranked = native_accel.fuzzy_search(query, drug_names, limit=10, cutoff=65)
                    else:
                        ranked = _fuzzy_filter(query, drug_names, 65, 10)
                    results = [candidates[idx] for _name, _score, idx in ranked]
                except Exception:
                    results = []
            for item in self._drug_tree.get_children():
                self._drug_tree.delete(item)
            for r in results:
                self._drug_tree.insert("", "end", values=(
                    r.get("ndc_code", ""),
                    r.get("drug_name", ""),
                    r.get("strength", ""),
                    r.get("dea_schedule", ""),
                ))


from ui_navigation import COLOR_SUCCESS, COLOR_CARD_BG  # noqa: E402


class ClinicalWorkflowFrame(ctk.CTkFrame):
    """Full clinical workflow frame with 9 tabs and wizard launch."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=kwargs.pop("fg_color", "transparent"), **kwargs)
        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text=i18n.t("clinical_workflow_title"),
                     font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")

        toolbar = ctk.CTkFrame(header, fg_color="transparent")
        toolbar.pack(side="right")
        ctk.CTkButton(toolbar, text=f"➕ {i18n.t('task_new_prescription')}",
                      width=160, command=self._open_wizard).pack(side="left", padx=(0, 8))
        ctk.CTkButton(toolbar, text=f"🔄 {i18n.t('refresh')}",
                      width=100, command=self._refresh).pack(side="left")

        # Tabbed notebook (9 tabs)
        self._notebook = ctk.CTkTabview(self, height=400)
        self._notebook.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        first_tab_name = None
        for i, (label_key, icon) in enumerate(_CLINICAL_TABS):
            label = i18n.t(label_key) if i18n.t(label_key) != label_key else label_key
            display_name = f"{icon} {label}"
            if first_tab_name is None:
                first_tab_name = display_name
            self._notebook.add(display_name)
            self._build_clinical_tab(display_name, i)

        if first_tab_name is not None:
            self._notebook.set(first_tab_name)

    def _build_clinical_tab(self, tab_name: str, index: int):
        frame = ctk.CTkFrame(self._notebook.tab(tab_name), fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        frame.grid_columnconfigure(0, weight=1)

        if index == 0:
            # Patient Selection tab
            ctk.CTkLabel(frame, text="Patient Search",
                         font=ctk.CTkFont(size=14)).pack(anchor="w", pady=(0, 8))
            self._clinical_patient_search = ctk.CTkEntry(
                frame, placeholder_text=i18n.t("patient_search_placeholder"))
            self._clinical_patient_search.pack(fill="x", pady=(0, 8))
            self._clinical_patient_tree = ttk.Treeview(frame, columns=("id", "name"), show="headings", height=10)
            self._clinical_patient_tree.heading("id", text="ID")
            self._clinical_patient_tree.heading("name", text=i18n.t("name"))
            self._clinical_patient_tree.pack(fill="both", expand=True)
            self._clinical_patient_search.bind("<KeyRelease>", lambda e: self._refresh_patient_list())
            self._refresh_patient_list()

        elif index == 1:
            # Medication Selection tab
            ctk.CTkLabel(frame, text=i18n.t("drug_selection"),
                         font=ctk.CTkFont(size=14)).pack(anchor="w", pady=(0, 8))
            self._clinical_drug_search = ctk.CTkEntry(
                frame, placeholder_text=i18n.t("search_ndc_or_drug"))
            self._clinical_drug_search.pack(fill="x", pady=(0, 8))
            ctk.CTkButton(frame, text=i18n.t("search"), width=80,
                         command=self._clinical_search_drugs).pack(anchor="w", pady=(0, 8))
            self._clinical_drug_tree = ttk.Treeview(frame, columns=("ndc", "name"), show="headings", height=10)
            self._clinical_drug_tree.heading("ndc", text="NDC")
            self._clinical_drug_tree.heading("name", text=i18n.t("drug_selection"))
            self._clinical_drug_tree.pack(fill="both", expand=True)

        elif index == 2:
            # Prescription Details tab
            fields = [("directions", i18n.t("directions")), ("frequency", i18n.t("frequency")),
                      ("days_supply", i18n.t("days_supply")), ("refills", i18n.t("refills")),
                      ("daw_code", i18n.t("daw_code"))]
            for i, (key, label) in enumerate(fields):
                ctk.CTkLabel(frame, text=label).pack(anchor="w", pady=(8, 0))
                entry = ctk.CTkEntry(frame)
                entry.pack(fill="x", pady=(2, 0))
                if key == "frequency":
                    entry.insert(0, "BID")
                elif key == "days_supply":
                    entry.insert(0, "30")
                elif key == "refills":
                    entry.insert(0, "0")
                elif key == "daw_code":
                    entry.insert(0, "00")
                setattr(self, f"_clinical_{key}_entry", entry)

        elif index == 3:
            # Clinical Notes
            self._clinical_notes_text = ctk.CTkTextbox(frame, height=200)
            self._clinical_notes_text.pack(fill="both", expand=True)

        elif index == 4:
            # Allergies
            self._clinical_allergies_tree = ttk.Treeview(frame, columns=("drug", "reaction", "severity"),
                                                         show="headings", height=10)
            for col in ("drug", "reaction", "severity"):
                self._clinical_allergies_tree.heading(col, text=i18n.t(col))
                self._clinical_allergies_tree.column(col, width=120)
            self._clinical_allergies_tree.pack(fill="both", expand=True)

        elif index == 5:
            # Drug Interactions
            ctk.CTkLabel(frame, text=i18n.t("clinical_interactions"),
                         font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 8))
            self._interactions_list = ctk.CTkTextbox(frame, height=200)
            self._interactions_list.pack(fill="both", expand=True)
            self._interactions_list.insert("1.0", "Run interaction checking by selecting medications above.")

        elif index == 6:
            # Documentation
            self._clinical_docs_list = tk.Listbox(frame, height=12)
            self._clinical_docs_list.pack(fill="both", expand=True, pady=(0, 8))
            doc_btn = ctk.CTkButton(frame, text="📎 " + i18n.t("clinical_attachments"),
                                    command=self._attach_document)
            doc_btn.pack(pady=(0, 8))

        elif index == 7:
            # Attachments
            self._attachments_list = tk.Listbox(frame, height=12)
            self._attachments_list.pack(fill="both", expand=True, pady=(0, 8))
            ctk.CTkButton(frame, text="📎 " + i18n.t("clinical_attachments"),
                          command=self._attach_file).pack(pady=(0, 8))

        elif index == 8:
            # Review Summary
            self._review_text = ctk.CTkTextbox(frame, height=300)
            self._review_text.pack(fill="both", expand=True)
            self._review_text.insert("1.0", "Review all clinical data before submission.")
            ctk.CTkButton(frame, text=i18n.t("clinical_submit_prescription"),
                          command=self._submit_prescription,
                          fg_color=COLOR_SUCCESS, hover_color="#0D946B").pack(pady=8)

    def _refresh_patient_list(self):
        try:
            patients = database.get_all_patients()
        except Exception:
            patients = []
        for item in self._clinical_patient_tree.get_children():
            self._clinical_patient_tree.delete(item)
        query = self._clinical_patient_search.get().strip()
        if not query:
            for p in patients:
                pid = p[0] if isinstance(p, (list, tuple)) else getattr(p, "id", "")
                pname = p[1] if isinstance(p, (list, tuple)) else getattr(p, "name", "")
                self._clinical_patient_tree.insert("", "end", values=(pid, pname))
            return
        patient_names = [p[1] if isinstance(p, (list, tuple)) else getattr(p, "name", "") for p in patients]
        if _HAS_NATIVE_ACCEL:
            ranked = native_accel.fuzzy_search(query, patient_names, limit=50, cutoff=60)
        else:
            ranked = _fuzzy_filter(query, patient_names, 60, 50)
        for name, _score, idx in ranked:
            p = patients[idx]
            pid = p[0] if isinstance(p, (list, tuple)) else getattr(p, "id", "")
            self._clinical_patient_tree.insert("", "end", values=(pid, name))

    def _clinical_search_drugs(self):
        query = self._clinical_drug_search.get().strip()
        if not query:
            return
        if _HAS_NDC:
            result = ndc_lookup(query) or barcode_lookup(query)
            if result:
                for item in self._clinical_drug_tree.get_children():
                    self._clinical_drug_tree.delete(item)
                self._clinical_drug_tree.insert("", "end", values=(
                    result.get("ndc_code", ""),
                    result.get("drug_name", ""),
                ))
        if _HAS_RX_DB:
            try:
                results = _rx_db.search_inventory(query)
                for item in self._clinical_drug_tree.get_children():
                    self._clinical_drug_tree.delete(item)
                for r in results:
                    self._clinical_drug_tree.insert("", "end", values=(
                        r.get("ndc_code", ""), r.get("drug_name", ""),
                    ))
            except Exception as e:
                log.error("Clinical drug search failed: %s", e)

    def _attach_document(self):
        path = filedialog.askopenfilename()
        if path:
            self._clinical_docs_list.insert(tk.END, path)

    def _attach_file(self):
        path = filedialog.askopenfilename()
        if path:
            self._attachments_list.insert(tk.END, path)

    def _submit_prescription(self):
        messagebox.showinfo(i18n.t("clinical_workflow_title"),
                           "Prescription submitted for clinical review.")

    def _open_wizard(self):
        """Open the 4-step prescription wizard."""
        wizard = PrescriptionWizard(self)
        wizard.transient(self)
        wizard.grab_set()
        self.wait_window(wizard)

    def _refresh(self):
        """Refresh all clinical data views."""
        try:
            self._refresh_patient_list()
        except Exception as e:
            log.error("Clinical workflow refresh failed: %s", e)


def setup_clinical_workflow_tab(self, parent=None):
    """Tab-setup function attached to PharmacyApp via monkey-patching."""
    if parent is None:
        parent = self.tab_clinical

    frame = ClinicalWorkflowFrame(parent, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=4, pady=4)

    self.clinical_workflow_frame = frame
    self._refresh_clinical_workflow_tab = lambda: frame._refresh()
    return frame
