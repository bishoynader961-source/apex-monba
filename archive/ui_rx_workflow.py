import tkinter.messagebox as messagebox
import customtkinter as ctk

DEFAULT_FIELD_NAMES = ["Insurance", "Notes", "Allergies", "DOB", "Address"]


def _build_field_combo_choices():
    """Merge DB-distinct field names with defaults, deduplicated and sorted."""
    db_names = rx_database.get_distinct_rx_field_names()
    seen = set()
    merged = []
    for name in DEFAULT_FIELD_NAMES + db_names:
        key = name.lower().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(name)
    return merged


def _open_rx_dialog(self, rx_id=None):
    dialog = ctk.CTkToplevel(self)
    dialog.title("Edit Prescription" if rx_id else "New Prescription")
    dialog.geometry("520x520")
    dialog.resizable(False, False)
    dialog.grab_set()

    prescription = None
    if rx_id:
        prescription = rx_database.get_prescription_by_id(rx_id)
        if not prescription:
            messagebox.showerror("Error", "Prescription not found.")
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

    ctk.CTkLabel(form, text="Drug Name:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
    drug_entry = ctk.CTkEntry(form, width=400, placeholder_text="Drug name")
    drug_entry.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    if prescription:
        drug_entry.insert(0, prescription[1])

    ctk.CTkLabel(form, text="Dosage:", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w")
    dosage_entry = ctk.CTkEntry(form, width=400, placeholder_text="e.g. 500mg")
    dosage_entry.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    if prescription:
        dosage_entry.insert(0, prescription[2])

    ctk.CTkLabel(form, text="Quantity:", font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, sticky="w")
    qty_entry = ctk.CTkEntry(form, width=400, placeholder_text="e.g. 30")
    qty_entry.grid(row=5, column=0, sticky="ew", pady=(0, 8))
    if prescription:
        qty_entry.insert(0, prescription[3])

    # ── Custom Fields section ────────────────────────────────────────────
    ctk.CTkLabel(
        form, text="Custom Fields:",
        font=ctk.CTkFont(weight="bold", size=13),
    ).grid(row=6, column=0, sticky="w", pady=(10, 2))

    fields_container = ctk.CTkFrame(form, fg_color="transparent")
    fields_container.grid(row=7, column=0, sticky="ew")
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
    if prescription and prescription[5]:
        for k, v in prescription[5].items():
            add_field_row(k, v)
    else:
        add_field_row()

    add_field_btn = ctk.CTkButton(
        form, text="+ Add Field", width=120, fg_color="#6c757d", hover_color="#5a6268",
        command=lambda: add_field_row(),
    )
    add_field_btn.grid(row=8, column=0, sticky="w", pady=(6, 0))

    # ── Bottom action buttons (always visible) ───────────────────────────
    btn_bar = ctk.CTkFrame(outer, fg_color="transparent")
    btn_bar.grid(row=1, column=0, sticky="sew", padx=20, pady=(5, 15))
    btn_bar.grid_columnconfigure(0, weight=1)

    cancel_btn = ctk.CTkButton(
        btn_bar, text="Cancel", width=100, fg_color="#6c757d", hover_color="#5a6268",
        command=dialog.destroy,
    )
    cancel_btn.grid(row=0, column=1, padx=(0, 8))

    def on_save():
        drug_name = drug_entry.get().strip()
        if not drug_name:
            messagebox.showwarning("Required", "Drug name is required.", parent=dialog)
            return
        dosage = dosage_entry.get().strip()
        quantity = qty_entry.get().strip()
        custom_fields = {}
        for _, cb, ve in field_rows:
            fn = cb.get().strip() if hasattr(cb, "get") else ""
            fv = ve.get().strip()
            if fn:
                custom_fields[fn] = fv

        try:
            if rx_id:
                rx_database.update_prescription(rx_id, update_fields={
                    "drug_name": drug_name,
                    "dosage": dosage,
                    "quantity": quantity,
                    "custom_fields": custom_fields,
                })
            else:
                rx_database.add_prescription(None, drug_name, dosage, quantity, custom_fields)
        except Exception as e:
            messagebox.showerror("Error", f"Database error:\n{e}", parent=dialog)
            return

        dialog.destroy()
        _load_prescriptions(self)

    save_btn = ctk.CTkButton(
        btn_bar, text="Save", width=100, fg_color="#28a745", hover_color="#218838",
        command=on_save,
    )
    save_btn.grid(row=0, column=2)
