import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime

import database
import barcode_logic


def setup_add_tab(self):
    self.tab_add.grid_columnconfigure((0, 1), weight=1)

    title_label = ctk.CTkLabel(self.tab_add, text="Add New Product", font=ctk.CTkFont(size=24, weight="bold"), text_color="#f0f0f0")
    title_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 30))

    tpl_label = ctk.CTkLabel(self.tab_add, text="Use Template (Optional):", anchor="w")
    tpl_label.grid(row=1, column=0, padx=(100, 10), pady=10, sticky="w")

    self.template_var = ctk.StringVar(value="Select a template...")
    self.template_combo = ctk.CTkComboBox(self.tab_add, width=300, variable=self.template_var, command=self.on_template_selected)
    self.template_combo.grid(row=1, column=1, padx=(10, 100), pady=10, sticky="w")
    self.refresh_add_tab_templates()

    name_label = ctk.CTkLabel(self.tab_add, text="Product Name:", anchor="w")
    name_label.grid(row=2, column=0, padx=(100, 10), pady=10, sticky="w")
    self.name_entry = ctk.CTkEntry(self.tab_add, width=300)
    self.name_entry.grid(row=2, column=1, padx=(10, 100), pady=10, sticky="w")

    price_label = ctk.CTkLabel(self.tab_add, text="Price ($):", anchor="w")
    price_label.grid(row=3, column=0, padx=(100, 10), pady=10, sticky="w")
    self.price_entry = ctk.CTkEntry(self.tab_add, width=300)
    self.price_entry.grid(row=3, column=1, padx=(10, 100), pady=10, sticky="w")

    mfg_label = ctk.CTkLabel(self.tab_add, text="Manufacturer Barcode:", anchor="w")
    mfg_label.grid(row=4, column=0, padx=(100, 10), pady=10, sticky="w")
    self.mfg_entry = ctk.CTkEntry(self.tab_add, width=300, placeholder_text="Scan or type barcode")
    self.mfg_entry.grid(row=4, column=1, padx=(10, 100), pady=10, sticky="w")
    self.mfg_entry.bind("<Return>", self.save_product)

    expiry_label = ctk.CTkLabel(self.tab_add, text="Expiry Date:", anchor="w")
    expiry_label.grid(row=5, column=0, padx=(100, 10), pady=10, sticky="w")
    self.expiry_entry = ctk.CTkEntry(self.tab_add, width=300, placeholder_text="YYYY-MM-DD")
    self.expiry_entry.grid(row=5, column=1, padx=(10, 100), pady=10, sticky="w")

    mfg_date_label = ctk.CTkLabel(self.tab_add, text="Manufacture Date:", anchor="w")
    mfg_date_label.grid(row=6, column=0, padx=(100, 10), pady=10, sticky="w")
    self.mfg_date_entry = ctk.CTkEntry(self.tab_add, width=300, placeholder_text="YYYY-MM-DD")
    self.mfg_date_entry.grid(row=6, column=1, padx=(10, 100), pady=10, sticky="w")

    vendor_label = ctk.CTkLabel(self.tab_add, text="Vendor:", anchor="w")
    vendor_label.grid(row=7, column=0, padx=(100, 10), pady=10, sticky="w")
    self.vendor_name_entry = ctk.CTkEntry(self.tab_add, width=300, placeholder_text="e.g. MedSupply Co.")
    self.vendor_name_entry.grid(row=7, column=1, padx=(10, 100), pady=10, sticky="w")

    btn_frame = ctk.CTkFrame(self.tab_add, fg_color="transparent")
    btn_frame.grid(row=8, column=0, columnspan=2, pady=40)
    save_btn = ctk.CTkButton(btn_frame, text="Save & Generate Tag", command=self.save_product, height=40, font=ctk.CTkFont(size=16))
    save_btn.pack(side="left", padx=(0, 10))

    bulk_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
    bulk_frame.pack(side="left")
    self.queue_send_var = ctk.BooleanVar(value=False)
    queue_btn = ctk.CTkCheckBox(bulk_frame, text="Send to Pending PO Queue", variable=self.queue_send_var, height=40, font=ctk.CTkFont(size=14))
    queue_btn.pack(side="left", padx=(10, 0))
    self.bulk_submit_btn = ctk.CTkButton(bulk_frame, text="Quick Receive (Bulk)", command=self._open_bulk_add_modal, height=40, font=ctk.CTkFont(size=16), fg_color="#7c3aed", hover_color="#6d28d9", state="disabled", width=180)
    self.bulk_submit_btn.pack(side="left", padx=(5, 0))
    self.queue_send_var.trace_add("write", self._update_bulk_button_state)


def refresh_add_tab_templates(self):
    self.templates_list = database.get_templates()
    combo_values = ["Select a template..."] + [tpl[1] for tpl in self.templates_list]
    self.template_combo.configure(values=combo_values)


def on_template_selected(self, choice):
    if choice == "Select a template...":
        return
    for tpl in self.templates_list:
        if tpl[1] == choice:
            tpl_name = tpl[1]
            tpl_price = str(tpl[2])
            ctx = {"NAME": tpl_name, "PRICE": tpl_price}
            resolved_name = self._resolve_template_vars(tpl_name, ctx)
            self.name_entry.delete(0, 'end')
            self.name_entry.insert(0, resolved_name)
            self.price_entry.delete(0, 'end')
            self.price_entry.insert(0, tpl_price)
            break


def _resolve_template_vars(self, text, context):
    import re
    def replacer(m):
        key = m.group(1)
        return str(context.get(key, m.group(0)))
    return re.sub(r'\{\{(\w+)\}\}', replacer, text)


def save_product(self, event=None):
    name = self.name_entry.get().strip()
    price_str = self.price_entry.get().strip()
    mfg_barcode = self.mfg_entry.get().strip()
    expiry_date = self.expiry_entry.get().strip()
    manufacture_date = self.mfg_date_entry.get().strip()
    vendor_name = self.vendor_name_entry.get().strip() or 'N/A'

    if not name or not price_str or not mfg_barcode:
        messagebox.showerror("Error", "All fields are required!")
        return

    try:
        price = float(price_str)
    except ValueError:
        messagebox.showerror("Error", "Price must be a valid number!")
        return

    if expiry_date and not self._validate_date(expiry_date, "Expiry Date"):
        return
    if manufacture_date and not self._validate_date(manufacture_date, "Manufacture Date"):
        return

    today = datetime.now().date()
    if expiry_date:
        exp = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        if exp < today:
            messagebox.showerror("Error", "Expiry Date cannot be in the past!")
            return
    if manufacture_date:
        mfg = datetime.strptime(manufacture_date, "%Y-%m-%d").date()
        if mfg > today:
            messagebox.showerror("Error", "Manufacture Date cannot be in the future!")
            return
    if expiry_date and manufacture_date:
        if exp <= mfg:
            messagebox.showerror("Error", "Expiry Date must be after Manufacture Date!")
            return

    internal_barcode = barcode_logic.generate_internal_barcode(vendor_name)

    try:
        database.add_product(name, price, mfg_barcode, internal_barcode, expiry_date, manufacture_date, vendor_name)
        database.log_shipment(
            vendor_name, name, datetime.now().strftime('%Y-%m-%d'),
            1, price, internal_barcode
        )

        self.name_entry.delete(0, 'end')
        self.price_entry.delete(0, 'end')
        self.mfg_entry.delete(0, 'end')
        self.expiry_entry.delete(0, 'end')
        self.mfg_date_entry.delete(0, 'end')
        self.vendor_name_entry.delete(0, 'end')
        self.template_var.set("Select a template...")

        messagebox.showinfo("Success", "Product saved successfully! Opening Label Designer...")

        from ui_modals import LabelDesignerPopup
        designer = LabelDesignerPopup(self, name, price_str, internal_barcode, expiry=expiry_date, mfg=manufacture_date)
        designer.grab_set()

        self._notify_inventory_updated()

    except Exception as e:
        messagebox.showerror("Error", f"Failed to save product:\n{str(e)}")


def _update_bulk_button_state(self, *args, **kwargs):
    if not hasattr(self, 'queue_send_var') or not hasattr(self, 'bulk_submit_btn'):
        return

    if self.queue_send_var.get():
        self.bulk_submit_btn.configure(state="normal")
    else:
        self.bulk_submit_btn.configure(state="disabled")


def _open_bulk_add_modal(self):
    name = self.name_entry.get().strip()
    price_str = self.price_entry.get().strip()
    mfg_barcode = self.mfg_entry.get().strip()
    expiry_date = self.expiry_entry.get().strip()
    manufacture_date = self.mfg_date_entry.get().strip()
    vendor_name = self.vendor_name_entry.get().strip() or 'N/A'

    if not name:
        messagebox.showerror("Error", "Product Name is required for bulk receive.")
        return
    if not price_str:
        messagebox.showerror("Error", "Price is required for bulk receive.")
        return
    try:
        price = float(price_str)
    except ValueError:
        messagebox.showerror("Error", "Price must be a valid number.")
        return

    self._update_bulk_button_state()
    if not self.queue_send_var.get():
        messagebox.showinfo(
            "Queue Batch",
            "Set 'Send to Pending PO Queue' checkbox to true to queue items.\n\nRemember to send all queued items to the Receive Inventory tab for processing."
        )

    from ui_modals import BulkAddModal
    BulkAddModal(self, name, price, mfg_barcode, expiry_date, manufacture_date, vendor_name)
