import customtkinter as ctk
from tkinter import ttk, messagebox
import logging

import database
import i18n
from ui_helpers import apply_treeview_style
from ui_region_fields import RegionFieldSet

log = logging.getLogger("ui_patients_tab")

DEFAULT_FIELD_NAMES = ["Allergies", "Insurance", "Notes", "Blood Type", "Emergency Contact", "Phone (Alt)"]


def setup_patients_tab(self):
    self.tab_patients.grid_rowconfigure(0, weight=0)
    self.tab_patients.grid_rowconfigure(1, weight=0)
    self.tab_patients.grid_rowconfigure(2, weight=1)
    self.tab_patients.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(self.tab_patients, text=i18n.t("patients"),
                 font=ctk.CTkFont(size=24, weight="bold"), text_color="#f0f0f0").grid(
        row=0, column=0, padx=20, pady=(20, 8), sticky="w")

    top_frame = ctk.CTkFrame(self.tab_patients, fg_color="transparent")
    top_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
    top_frame.grid_columnconfigure(0, weight=1)

    self._patient_search_var = ctk.StringVar()
    self._patient_search_var.trace_add("write", lambda *_: _patient_search(self))
    search_entry = ctk.CTkEntry(
        top_frame, textvariable=self._patient_search_var,
        placeholder_text=i18n.t("search_patients_placeholder"),
        width=300,
    )
    search_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")

    ctk.CTkButton(
        top_frame, text=i18n.t("add_patient"), width=120, fg_color="#28a745", hover_color="#218838",
        command=lambda: _open_patient_dialog(self),
    ).grid(row=0, column=1, padx=(0, 5))

    ctk.CTkButton(
        top_frame, text=i18n.t("edit"), width=80, fg_color="#e67e22", hover_color="#cf6d17",
        command=lambda: _edit_selected_patient(self),
    ).grid(row=0, column=2, padx=(0, 5))

    ctk.CTkButton(
        top_frame, text=i18n.t("delete"), width=80, fg_color="#dc3545", hover_color="#c82333",
        command=lambda: _delete_selected_patient(self),
    ).grid(row=0, column=3)

    columns = (i18n.t("name"), i18n.t("phone"), i18n.t("email"), i18n.t("custom_fields"), i18n.t("created_at"))
    self.tree_patients = ttk.Treeview(self.tab_patients, columns=columns, show="headings")
    self.tree_patients.heading(i18n.t("name"), text=i18n.t("name"))
    self.tree_patients.heading(i18n.t("phone"), text=i18n.t("phone"))
    self.tree_patients.heading(i18n.t("email"), text=i18n.t("email"))
    self.tree_patients.heading(i18n.t("custom_fields"), text=i18n.t("custom_fields"))
    self.tree_patients.heading(i18n.t("created_at"), text=i18n.t("created_at"))

    self.tree_patients.column(i18n.t("name"), width=160, anchor="w")
    self.tree_patients.column(i18n.t("phone"), width=120, anchor="w")
    self.tree_patients.column(i18n.t("email"), width=160, anchor="w")
    self.tree_patients.column(i18n.t("custom_fields"), width=280, anchor="w")
    self.tree_patients.column(i18n.t("created_at"), width=130, anchor="center")

    apply_treeview_style(self.tree_patients)

    self.tree_patients.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

    scrollbar = ttk.Scrollbar(self.tab_patients, orient="vertical", command=self.tree_patients.yview)
    self.tree_patients.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=2, column=1, sticky="ns", pady=(0, 10))

    self.tree_patients.bind("<Double-1>", lambda _: _edit_selected_patient(self))

    _load_patients(self)


def _load_patients(self, search_query=None):
    for item in self.tree_patients.get_children():
        self.tree_patients.delete(item)

    patients = database.get_all_patients(search_query)
    for pid, name, phone, email, created_at, fields in patients:
        fields_str = ", ".join(f"{k}: {v}" for k, v in fields.items()) if fields else ""
        self.tree_patients.insert("", "end", iid=f"patient_{pid}", values=(
            name, phone, email, fields_str, created_at[:10] if created_at else "",
        ))


def _patient_search(self):
    query = self._patient_search_var.get().strip() or None
    _load_patients(self, query)


def _get_selected_patient_id(self):
    selected = self.tree_patients.selection()
    if not selected:
        return None
    iid = selected[0]
    if not iid.startswith("patient_"):
        return None
    return int(iid[len("patient_"):])




def _build_field_combo_choices():
    """Merge DB-distinct field names with defaults, deduplicated and sorted."""
    db_names = database.get_distinct_patient_field_names()
    seen = set()
    merged = []
    for name in DEFAULT_FIELD_NAMES + db_names:
        key = name.lower().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(name)
    return merged


def _open_patient_dialog(self, patient_id=None):
    dialog = ctk.CTkToplevel(self)
    dialog.title(i18n.t("edit_patient") if patient_id else i18n.t("add_patient"))
    dialog.geometry("520x520")
    dialog.resizable(False, False)
    dialog.grab_set()

    patient = None
    if patient_id:
        patient = database.get_patient_by_id(patient_id)
        if not patient:
            messagebox.showerror(i18n.t("error"), i18n.t("patient_not_found"))
            dialog.destroy()
            return

    # ── Outer frame with grid for sticky bottom buttons ──────────────────
    outer = ctk.CTkFrame(dialog, fg_color="transparent")
    outer.pack(fill="both", expand=True)
    outer.grid_rowconfigure(1, weight=1)
    outer.grid_columnconfigure(0, weight=1)

    # ── Scrollable form area ─────────────────────────────────────────────
    form = ctk.CTkScrollableFrame(outer, fg_color="transparent")
    form.grid(row=0, column=0, sticky="nsew", padx=20, pady=(15, 0))
    form.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(form, text=i18n.t("name") + ":", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
    name_entry = ctk.CTkEntry(form, width=400, placeholder_text=i18n.t("patient_full_name"))
    name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    if patient:
        name_entry.insert(0, patient[1])

    ctk.CTkLabel(form, text=i18n.t("phone") + ":", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w")
    phone_entry = ctk.CTkEntry(form, width=400, placeholder_text=i18n.t("phone_number"))
    phone_entry.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    if patient:
        phone_entry.insert(0, patient[2])

    ctk.CTkLabel(form, text=i18n.t("email") + ":", font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, sticky="w")
    email_entry = ctk.CTkEntry(form, width=400, placeholder_text=i18n.t("email_address"))
    email_entry.grid(row=5, column=0, sticky="ew", pady=(0, 8))
    if patient:
        email_entry.insert(0, patient[3])

    # ── Region-specific identifier fields (Standard #4) ───────────────────
    # Wrapped in a scrollable frame so it never clips regardless of region or
    # window size; the dialog stays fixed at 520x520 (D9).
    ctk.CTkLabel(
        form, text=i18n.t("region_fields_label", default="Region-specific fields"),
        font=ctk.CTkFont(weight="bold", size=13),
    ).grid(row=6, column=0, sticky="w", pady=(10, 2))
    _region_scroll = ctk.CTkScrollableFrame(form, fg_color="transparent", height=120)
    _region_scroll.grid(row=7, column=0, sticky="ew", pady=(0, 8))
    _region_init = {}
    if patient and patient[5]:
        # Pull canonical region keys out of the existing custom-fields blob.
        for _k in ("dea_number", "npi", "nhs_number", "gphc_number",
                   "exemption_category", "pzn_code", "insurance_bin",
                   "insurance_pcn", "scheme_pcn", "group_number"):
            if _k in patient[5]:
                _region_init[_k] = patient[5][_k]
    region_fields = RegionFieldSet(_region_scroll, values=_region_init)
    region_fields.pack(fill="x", expand=True)
    try:
        import ui_tooltip
        ui_tooltip.attach_key(region_fields, "tip_region_fields")
    except Exception:
        pass

    # ── Custom Fields section ────────────────────────────────────────────
    ctk.CTkLabel(
        form, text=i18n.t("custom_fields_label"),
        font=ctk.CTkFont(weight="bold", size=13),
    ).grid(row=8, column=0, sticky="w", pady=(10, 2))

    fields_container = ctk.CTkFrame(form, fg_color="transparent")
    fields_container.grid(row=9, column=0, sticky="ew")
    fields_container.grid_columnconfigure(0, weight=1)
    fields_container.grid_columnconfigure(1, weight=1)
    fields_container.grid_columnconfigure(2, weight=0)

    combo_choices = _build_field_combo_choices()

    field_rows = []  # list of (frame, combobox, value_entry)

    def add_field_row(name="", value=""):
        row_idx = len(field_rows)
        row = ctk.CTkFrame(fields_container, fg_color="transparent")
        row.grid(row=row_idx, column=0, columnspan=3, sticky="ew", pady=2)
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)

        cb = ctk.CTkComboBox(
            row, values=combo_choices, width=180,
            state="readonly" if not name else "normal",
        )
        cb.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        if name:
            cb.set(name)
        else:
            cb.set("")

        ve = ctk.CTkEntry(row, width=180, placeholder_text="Value")
        ve.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        if value:
            ve.insert(0, value)

        remove_btn = ctk.CTkButton(
            row, text="\u2715", width=30, fg_color="#dc3545", hover_color="#c82333",
            command=lambda: _remove_field(row),
        )
        remove_btn.grid(row=0, column=2)

        field_rows.append((row, cb, ve))

    def _remove_field(row_frame):
        for r, cb, ve in field_rows:
            if r is row_frame:
                r.grid_forget()
                r.destroy()
                field_rows.remove((r, cb, ve))
                break
        _repack_fields()

    def _repack_fields():
        for i, (r, cb, ve) in enumerate(field_rows):
            r.grid(row=i, column=0, columnspan=3, sticky="ew", pady=2)

    # Load existing fields
    if patient and patient[5]:
        for k, v in patient[5].items():
            add_field_row(k, v)
    else:
        add_field_row()

    add_field_btn = ctk.CTkButton(
        form, text=f"+ {i18n.t('add_field')}", width=120, fg_color="#6c757d", hover_color="#5a6268",
        command=lambda: add_field_row(),
    )
    add_field_btn.grid(row=8, column=0, sticky="w", pady=(6, 0))

    # ── Bottom action buttons (always visible) ───────────────────────────
    btn_bar = ctk.CTkFrame(outer, fg_color="transparent")
    btn_bar.grid(row=1, column=0, sticky="sew", padx=20, pady=(5, 15))
    btn_bar.grid_columnconfigure(0, weight=1)

    cancel_btn = ctk.CTkButton(
        btn_bar, text=i18n.t("cancel"), width=100, fg_color="#6c757d", hover_color="#5a6268",
        command=dialog.destroy,
    )
    cancel_btn.grid(row=0, column=1, padx=(0, 8))

    def on_save():
        name = name_entry.get().strip()
        if not name:
            messagebox.showwarning(i18n.t("info"), i18n.t("name_required"), parent=dialog)
            return
        phone = phone_entry.get().strip()
        email = email_entry.get().strip()
        custom_fields = {}
        for _, cb, ve in field_rows:
            fn = cb.get().strip() if hasattr(cb, "get") else ""
            fv = ve.get().strip()
            if fn:
                custom_fields[fn] = fv
        # Region-specific identifiers (keyed by canonical key, not the label).
        custom_fields.update(region_fields.get_values())

        try:
            if patient_id:
                database.update_patient(patient_id, name, phone, email, custom_fields)
            else:
                database.add_patient(name, phone, email, custom_fields)
        except Exception as e:
            messagebox.showerror(i18n.t("error"), f"Database error:\n{e}", parent=dialog)
            return

        dialog.destroy()
        _load_patients(self)

    save_btn = ctk.CTkButton(
        btn_bar, text=i18n.t("save"), width=100, fg_color="#28a745", hover_color="#218838",
        command=on_save,
    )
    save_btn.grid(row=0, column=2)


def _edit_selected_patient(self):
    pid = _get_selected_patient_id(self)
    if not pid:
        messagebox.showwarning(i18n.t("warning"), i18n.t("select_patient_to_edit"))
        return
    _open_patient_dialog(self, patient_id=pid)


def _delete_selected_patient(self):
    pid = _get_selected_patient_id(self)
    if not pid:
        messagebox.showwarning(i18n.t("warning"), i18n.t("select_patient_to_delete"))
        return
    patient = database.get_patient_by_id(pid)
    if not patient:
        messagebox.showerror(i18n.t("error"), i18n.t("patient_not_found"))
        return
    confirm = messagebox.askyesno(
        i18n.t("confirm_delete"),
        f"Delete patient '{patient[1]}' and all their custom fields?",
    )
    if confirm:
        database.delete_patient(pid)
        _load_patients(self)


def _patients_debug_layout(self) -> dict:
    """Verify layout integrity (VERIFICATION_CHECKLIST Protocol II.A)."""
    results: dict = {"issues": []}
    try:
        self.update_idletasks()
        tab = self.tab_patients
        tab_w = tab.winfo_width()
        results["tab_size"] = (tab_w, tab.winfo_height())

        tree_w = self.tree_patients.winfo_width()
        if tree_w <= 0:
            results["issues"].append("Patient tree has zero width")

        if hasattr(self, "_patient_search_var"):
            sb_x = self.tree_patients.winfo_x()
            sb_w = self.tree_patients.winfo_width()
            if sb_x + sb_w > tab_w:
                results["issues"].append(
                    f"Patient tree clipping: x={sb_x} + w={sb_w} > tab={tab_w}")

        results["status"] = "PASS" if not results["issues"] else "FAIL"
        log.debug("Patients layout geometry: %s", results["status"])
    except Exception as e:
        results["status"] = "ERROR"
        results["issues"].append(str(e))
        log.error("Patients layout geometry debug failed: %s", e)
    return results
