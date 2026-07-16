import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import os
import re
import json
from datetime import datetime, date
from PIL import Image, ImageTk
import tempfile
from collections import defaultdict

import database
import barcode_logic

from label_engine.canvas_core import LabelCanvas, LabelElement, draw_elements
from label_engine.export import save_label, load_label, export_to_png, print_label, TEMPLATE_PATH


def _extract_first_var(text):
    m = re.search(r'\{\{(\w+)\}\}', text)
    return m.group(1) if m else None


def _extract_all_vars(text):
    return re.findall(r'\{\{(\w+)\}\}', text)


class PharmacyApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Pharmacy Inventory System")
        self.geometry("1000x700")
        
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Create TabView
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        self.tab_view.configure(command=self.on_tab_change)
        
        self.tab_add = self.tab_view.add("Add Product")
        self.tab_inventory = self.tab_view.add("Inventory")
        self.tab_report = self.tab_view.add("Sales Report")
        self.tab_receive = self.tab_view.add("Receive Inventory")
        self.tab_templates = self.tab_view.add("Templates")
        self.tab_settings = self.tab_view.add("Settings")
        
        self.templates_list = []
        self.receiving_session = {}
        
        self.setup_add_tab()
        self.setup_inventory_tab()
        self.setup_report_tab()
        self.setup_receive_tab()
        self.load_receiving_log()
        self.refresh_product_list()
        self.setup_templates_tab()
        self.setup_settings_tab()

        self.after(500, self._check_startup_expiry)

    # -------------------------------------------------------------------------
    # DIAGNOSTIC: Focus Inspector — drop-in tool to identify interaction lock
    # -------------------------------------------------------------------------
    def _debug_focus(self, event=None):
        """Diagnostic: prints the widget currently holding keyboard focus.
        Call via self._debug_focus() or bind to a button for live inspection.
        Usage: self.after(100, self._debug_focus)  — polls focus 100ms after click.
        """
        focused = self.focus_get()
        if focused is None:
            print("[DEBUG-FOCUS] focus_get() = None — no widget owns focus")
        else:
            w_class  = focused.winfo_class()
            w_name   = str(focused)
            w_master = str(focused.master) if focused.master else "<root>"
            print(f"[DEBUG-FOCUS] widget={w_name} | class={w_class} | master={w_master}")
        return focused

    def on_tab_change(self):
        current_tab = self.tab_view.get()
        if current_tab == "Add Product":
            self.refresh_add_tab_templates()
        elif current_tab == "Inventory":
            self.load_inventory()
        elif current_tab == "Sales Report":
            self.load_sales_report()
        elif current_tab == "Receive Inventory":
            self.load_receiving_log()
            self.refresh_product_list()
        elif current_tab == "Templates":
            self.load_templates_grid()

    def _check_startup_expiry(self):
        counts = database.get_expiring_batches()
        c30 = counts['30']
        if c30 > 0:
            messagebox.showwarning(
                "Expiry Alert",
                f"{c30} batch(es) expiring within 30 days!\n\nPlease review your inventory."
            )
            
    # --- Add Product Tab ---
    def setup_add_tab(self):
        self.tab_add.grid_columnconfigure((0, 1), weight=1)
        
        title_label = ctk.CTkLabel(self.tab_add, text="Add New Product", font=ctk.CTkFont(size=24, weight="bold"))
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
                
    def _validate_date(self, date_str, field_name, allow_empty=True):
        if not date_str:
            if allow_empty:
                return True
            messagebox.showerror("Error", f"{field_name} is required!")
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", f"{field_name} must be in YYYY-MM-DD format!\nExample: 2027-06-15")
            return False
        return True

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

        BulkAddModal(self, name, price, mfg_barcode, expiry_date, manufacture_date, vendor_name)

    # --- Inventory Tab ---
    def setup_inventory_tab(self):
        self.tab_inventory.grid_rowconfigure(2, weight=1)
        self.tab_inventory.grid_columnconfigure(0, weight=1)

        self._expanded_groups = set()
        self._current_sort = 'expiry_date'

        alert_frame = ctk.CTkFrame(self.tab_inventory, fg_color="transparent")
        alert_frame.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="ew")
        alert_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.alert_30 = ctk.CTkLabel(alert_frame, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#dc3545")
        self.alert_30.grid(row=0, column=0, padx=5, sticky="w")
        self.alert_60 = ctk.CTkLabel(alert_frame, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#fd7e14")
        self.alert_60.grid(row=0, column=1, padx=5, sticky="w")
        self.alert_90 = ctk.CTkLabel(alert_frame, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#ffc107")
        self.alert_90.grid(row=0, column=2, padx=5, sticky="w")

        search_frame = ctk.CTkFrame(self.tab_inventory, fg_color="transparent")
        search_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Search by name, mfg barcode, or internal barcode...")
        self.search_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.search_entry.bind("<Return>", self.perform_search)

        search_btn = ctk.CTkButton(search_frame, text="Search", width=100, command=self.perform_search)
        search_btn.grid(row=0, column=1)

        clear_btn = ctk.CTkButton(search_frame, text="Clear", width=100, fg_color="gray", hover_color="darkgray", command=self.load_inventory)
        clear_btn.grid(row=0, column=2, padx=(10, 10))

        sell_btn = ctk.CTkButton(search_frame, text="Sell Item", width=100, fg_color="#c42b1c", hover_color="#9e2216", command=self.sell_product)
        sell_btn.grid(row=0, column=3, padx=(10, 0))
        self.btn_sell = sell_btn

        edit_btn = ctk.CTkButton(search_frame, text="Edit Batch", width=100, fg_color="#e67e22", hover_color="#cf6d17", command=self._edit_batch)
        edit_btn.grid(row=0, column=4, padx=(10, 0))
        self.btn_edit_batch = edit_btn

        print_label_btn = ctk.CTkButton(
            search_frame,
            text="Print Label",
            width=100,
            fg_color="#17a2b8",
            hover_color="#138496",
            command=self.open_label_for_selected
        )
        print_label_btn.grid(row=0, column=5, padx=(10, 0))
        self.btn_print = print_label_btn

        self.sort_var = ctk.StringVar(value="Expiry Date")
        sort_toggle = ctk.CTkSegmentedButton(
            search_frame,
            values=["Expiry Date", "Mfg Date"],
            variable=self.sort_var,
            command=self._on_sort_change,
            width=220,
        )
        sort_toggle.grid(row=0, column=6, padx=(10, 0))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#2b2b2b",
                        foreground="white",
                        rowheight=25,
                        fieldbackground="#2b2b2b",
                        bordercolor="#343638",
                        borderwidth=0)
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading",
                        background="#565b5e",
                        foreground="white",
                        relief="flat")
        style.map("Treeview.Heading",
                  background=[('active', '#3484F0')])

        columns = ("Drug Name", "Qty / Expiry", "Price / Mfg Date", "Mfg Barcode", "Int. Barcode", "Status", "Vendor")
        self.tree_inv = ttk.Treeview(self.tab_inventory, columns=columns, show="headings")

        for col in columns:
            self.tree_inv.heading(col, text=col)

        self.tree_inv.column("Drug Name", width=180, anchor="w")
        self.tree_inv.column("Qty / Expiry", width=120, anchor="center")
        self.tree_inv.column("Price / Mfg Date", width=140, anchor="center")
        self.tree_inv.column("Mfg Barcode", width=110, anchor="center")
        self.tree_inv.column("Int. Barcode", width=110, anchor="center")
        self.tree_inv.column("Status", width=80, anchor="center")
        self.tree_inv.column("Vendor", width=120, anchor="w")

        self.tree_inv.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        scrollbar = ttk.Scrollbar(self.tab_inventory, orient="vertical", command=self.tree_inv.yview)
        self.tree_inv.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=(0, 10))

        self.tree_inv.bind("<Double-1>", self._on_tree_double_click)

        self.load_inventory()

    def _refresh_expiry_bar(self):
        counts = database.get_expiring_batches()
        c30, c60, c90 = counts['30'], counts['60'], counts['90']
        self.alert_30.configure(text=f"<=30d: {c30}" if c30 else "")
        self.alert_60.configure(text=f"<=60d: {c60}" if c60 else "")
        self.alert_90.configure(text=f"<=90d: {c90}" if c90 else "")

    def load_inventory(self):
        self.search_entry.delete(0, 'end')
        self._expanded_groups.clear()
        for item in self.tree_inv.get_children():
            self.tree_inv.delete(item)

        self._refresh_expiry_bar()

        groups = database.get_grouped_products()
        for name, qty, min_price, max_price in groups:
            price_text = f"${min_price:.2f}" if min_price == max_price else f"${min_price:.2f} - ${max_price:.2f}"
            self.tree_inv.insert("", "end", iid=f"group_{name}", values=(
                name, str(qty), price_text, "", "", "In Stock", ""
            ))

    def _on_tree_double_click(self, event):
        selected = self.tree_inv.selection()
        if not selected:
            return
        iid = selected[0]
        if iid.startswith("group_"):
            drug_name = iid[len("group_"):]
            self._toggle_group(drug_name)

    def _toggle_group(self, drug_name):
        group_iid = f"group_{drug_name}"
        if drug_name in self._expanded_groups:
            self._expanded_groups.discard(drug_name)
            for child in self.tree_inv.get_children(group_iid):
                self.tree_inv.delete(child)
        else:
            self._expanded_groups.add(drug_name)
            batches = database.get_batches_by_name(drug_name, sort_by=self._current_sort)
            for batch in batches:
                batch_id, name, price, mfg_barcode, int_barcode, status, expiry, mfg_date, vendor = batch
                expiry_text = expiry if expiry else "N/A"
                mfg_text = mfg_date if mfg_date else "N/A"
                vendor_prefix = int_barcode.split('-')[0] if '-' in int_barcode else ''
                self.tree_inv.insert(group_iid, "end", iid=f"batch_{batch_id}", values=(
                    "", f"Exp: {expiry_text}", f"Mfg: {mfg_text}", mfg_barcode, int_barcode, f"${price:.2f}", vendor_prefix or vendor or "N/A"
                ))

    def _on_sort_change(self, choice):
        self._current_sort = 'manufacture_date' if choice == "Mfg Date" else 'expiry_date'
        expanded = list(self._expanded_groups)
        self._expanded_groups.clear()
        for child in self.tree_inv.get_children():
            self.tree_inv.delete(child)
        groups = database.get_grouped_products()
        for name, qty, min_price, max_price in groups:
            price_text = f"${min_price:.2f}" if min_price == max_price else f"${min_price:.2f} - ${max_price:.2f}"
            self.tree_inv.insert("", "end", iid=f"group_{name}", values=(
                name, str(qty), price_text, "", "", "In Stock", ""
            ))
        for drug_name in expanded:
            self._toggle_group(drug_name)

    def perform_search(self, event=None):
        query = self.search_entry.get().strip()
        if not query:
            self.load_inventory()
            return

        exact_match = database.get_product_by_barcode(query)
        if exact_match and event:
            self.search_entry.delete(0, 'end')
            self.load_inventory()
            drug_name = exact_match[1]
            group_iid = f"group_{drug_name}"
            if group_iid in self.tree_inv.get_children(""):
                self._toggle_group(drug_name)
                self.tree_inv.selection_set(group_iid)
                self.tree_inv.focus(group_iid)
                self.tree_inv.see(group_iid)
            return

        for item in self.tree_inv.get_children():
            self.tree_inv.delete(item)
        self._expanded_groups.clear()

        groups = database.search_grouped_products(query)
        for name, qty, min_price, max_price in groups:
            price_text = f"${min_price:.2f}" if min_price == max_price else f"${min_price:.2f} - ${max_price:.2f}"
            self.tree_inv.insert("", "end", iid=f"group_{name}", values=(
                name, str(qty), price_text, "", "", "In Stock", ""
            ))

    def sell_product(self):
        selected = self.tree_inv.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an item to sell.")
            return

        iid = selected[0]
        if not iid.startswith("batch_"):
            messagebox.showwarning("Warning", "Please expand a drug group and select a specific batch to sell.")
            return

        values = self.tree_inv.item(iid, 'values')
        mfg_code = values[3]

        try:
            database.mark_item_as_sold(mfg_code)
            self.load_inventory()
            messagebox.showinfo("Success", "Item marked as sold and moved to Sales Report.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to mark item as sold:\n{str(e)}")

    def _edit_batch(self):
        selected = self.tree_inv.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a batch to edit.")
            return

        iid = selected[0]
        if not iid.startswith("batch_"):
            messagebox.showwarning("Warning", "Please expand a drug group and select a specific batch to edit.")
            return

        batch_id = int(iid[len("batch_"):])
        row = database.get_product_by_id(batch_id)
        if not row:
            messagebox.showerror("Error", "Could not locate this batch in the database.")
            return

        EditBatchDialog(self, row)

    def open_label_for_selected(self):
        selected = self.tree_inv.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an item to print its label.")
            return

        iid = selected[0]
        if not iid.startswith("batch_"):
            messagebox.showwarning("Warning", "Please expand a drug group and select a specific batch to print.")
            return

        values = self.tree_inv.item(iid, 'values')
        parent_iid = self.tree_inv.parent(iid)
        name = self.tree_inv.item(parent_iid, 'values')[0]
        price_str = values[5].replace('$', '')
        barcode = values[4]
        expiry_raw = values[1].replace("Exp: ", "") if values[1].startswith("Exp:") else ""
        mfg_raw = values[2].replace("Mfg: ", "") if values[2].startswith("Mfg:") else ""

        designer = LabelDesignerPopup(self, name, price_str, barcode, expiry_raw, mfg_raw)
        designer.grab_set()    
    # --- Sales Report Tab ---
    def setup_report_tab(self):
        self.tab_report.grid_rowconfigure(2, weight=1)
        self.tab_report.grid_columnconfigure(0, weight=1)
        
        top_frame = ctk.CTkFrame(self.tab_report, fg_color="transparent")
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        self.report_count_label = ctk.CTkLabel(top_frame, text="Total Items Sold: 0", font=ctk.CTkFont(size=16, weight="bold"))
        self.report_count_label.pack(side="left", padx=20)
        
        self.report_revenue_label = ctk.CTkLabel(top_frame, text="Total Revenue: $0.00", font=ctk.CTkFont(size=16, weight="bold"), text_color="#28a745")
        self.report_revenue_label.pack(side="left", padx=20)

        self.report_today_label = ctk.CTkLabel(top_frame, text="Today's Sales: $0.00", font=ctk.CTkFont(size=16, weight="bold"), text_color="#17a2b8")
        self.report_today_label.pack(side="left", padx=20)
        
        refund_btn = ctk.CTkButton(top_frame, text="Refund Item", fg_color="#ffc107", text_color="black", hover_color="#e0a800", command=self.refund_item)
        refund_btn.pack(side="right", padx=20)

        date_frame = ctk.CTkFrame(self.tab_report, fg_color="transparent")
        date_frame.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")

        ctk.CTkLabel(date_frame, text="Query Specific Date:", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(20, 5))

        self.date_entry = ctk.CTkEntry(date_frame, width=130, placeholder_text="YYYY-MM-DD")
        self.date_entry.pack(side="left", padx=5)
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))

        ctk.CTkButton(date_frame, text="Check Date", width=100, command=self.calculate_custom_date_sales).pack(side="left", padx=5)

        self.report_custom_date_label = ctk.CTkLabel(date_frame, text="Selected Date Sales: $0.00", font=ctk.CTkFont(size=14, weight="bold"), text_color="#6f42c1")
        self.report_custom_date_label.pack(side="left", padx=20)
        
        columns = ("ID", "Name", "Price", "Mfg Barcode", "Internal Barcode", "Timestamp", "Vendor")
        self.tree_report = ttk.Treeview(self.tab_report, columns=columns, show="headings")
        
        for col in columns:
            self.tree_report.heading(col, text=col)
            
        self.tree_report.column("ID", width=50, anchor="center")
        self.tree_report.column("Name", width=180, anchor="w")
        self.tree_report.column("Price", width=70, anchor="center")
        self.tree_report.column("Mfg Barcode", width=110, anchor="center")
        self.tree_report.column("Internal Barcode", width=110, anchor="center")
        self.tree_report.column("Timestamp", width=140, anchor="center")
        self.tree_report.column("Vendor", width=120, anchor="w")
        
        self.tree_report.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        scrollbar = ttk.Scrollbar(self.tab_report, orient="vertical", command=self.tree_report.yview)
        self.tree_report.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=(0, 10))
        
    def load_sales_report(self):
        for item in self.tree_report.get_children():
            self.tree_report.delete(item)
            
        sold_items = database.get_sold_items()
        
        total_count = len(sold_items)
        total_revenue = sum(item[2] for item in sold_items)
        today_sales = database.get_today_sales_total()
        
        self.report_count_label.configure(text=f"Total Items Sold: {total_count}")
        self.report_revenue_label.configure(text=f"Total Revenue: ${total_revenue:.2f}")
        self.report_today_label.configure(text=f"Today's Sales: ${today_sales:.2f}")
        
        for item in sold_items:
            self.tree_report.insert("", "end", values=(item[0], item[1], f"${item[2]:.2f}", item[3], item[4], item[5], item[6]))
            
    def calculate_custom_date_sales(self):
        raw = self.date_entry.get().strip()
        if not raw:
            raw = date.today().strftime("%Y-%m-%d")
        try:
            date.fromisoformat(raw)
        except ValueError:
            messagebox.showerror("Invalid Date", "Please enter a valid date in YYYY-MM-DD format.")
            return
        total = database.get_sales_for_date(raw)
        self.report_custom_date_label.configure(text=f"Sales for {raw}: ${total:.2f}")

    # --- Receive Inventory Tab (Purchase Order & Receiving Dashboard) ---
    def setup_receive_tab(self):
        # --- Left Frame: Zone A — Direct Add Panel (scrollable) ---
        # ROOT-CAUSE FIX (Interaction Lock):
        # CTkScrollableFrame uses bind_all() for MouseWheel/Shift keys AND embeds
        # itself via Canvas.create_window(). On Windows this breaks the focus chain
        # for child CTkEntry widgets — clicks land on the Canvas coordinate space,
        # not the Entry. Replaced with a canonical tk.Canvas + tk.Frame pattern:
        # no bind_all(), no create_window focus anomaly.
        LEFT_PANEL_WIDTH = 420

        # Outer container that the Canvas and scrollbar live inside
        self._recv_left_container = ctk.CTkFrame(self.tab_receive, width=LEFT_PANEL_WIDTH,
                                                  fg_color="transparent")
        self._recv_left_container.pack(side="left", fill="y", padx=10, pady=10)
        self._recv_left_container.pack_propagate(False)  # lock width

        # Native tk.Canvas — no bind_all, no create_window focus side-effects.
        # Background color: query CTK's current appearance mode to blend seamlessly.
        try:
            import customtkinter.windows.widgets.appearance_mode as _am
            _bg = _am.AppearanceModeTracker.appearance_mode  # "dark" or "light"
            _canvas_bg = "#2b2b2b" if _bg == "dark" else "#f0f0f0"
        except Exception:
            _canvas_bg = "#2b2b2b"  # safe CTK dark-mode default

        self._recv_canvas = tk.Canvas(self._recv_left_container, width=LEFT_PANEL_WIDTH,
                                      highlightthickness=0, bd=0, bg=_canvas_bg,
                                      takefocus=False)
        self._recv_scrollbar = tk.Scrollbar(self._recv_left_container, orient="vertical",
                                            command=self._recv_canvas.yview)
        self._recv_canvas.configure(yscrollcommand=self._recv_scrollbar.set)
        self._recv_scrollbar.pack(side="right", fill="y")
        self._recv_canvas.pack(side="left", fill="both", expand=True)

        # The real content frame — placed directly inside the canvas window.
        # CTkFrame with fg_color="transparent" inherits _canvas_bg automatically.
        self.recv_left_frame = ctk.CTkFrame(self._recv_canvas, fg_color="transparent")
        self._recv_canvas_window = self._recv_canvas.create_window(
            (0, 0), window=self.recv_left_frame, anchor="nw"
        )

        # Keep scroll region in sync with content size
        def _on_inner_configure(event):
            self._recv_canvas.configure(
                scrollregion=self._recv_canvas.bbox("all")
            )
        self.recv_left_frame.bind("<Configure>", _on_inner_configure)

        # Stretch inner frame to fill canvas width
        def _on_canvas_configure(event):
            self._recv_canvas.itemconfig(self._recv_canvas_window, width=event.width)
        self._recv_canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse-wheel scrolling scoped only to this panel (no bind_all)
        def _on_mousewheel(event):
            self._recv_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._recv_canvas.bind("<Enter>", lambda e: self._recv_canvas.bind("<MouseWheel>", _on_mousewheel))
        self._recv_canvas.bind("<Leave>", lambda e: self._recv_canvas.unbind("<MouseWheel>"))

        # Ensure clicks on canvas background focus the embedded frame so entries receive input
        self._recv_canvas.bind("<Button-1>", lambda e: self.recv_left_frame.focus_set())

        # ── Panel header ────────────────────────────────────────────────────
        # Accent left-border stripe + title, packed at top of scrollable frame
        header_row = ctk.CTkFrame(self.recv_left_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=10, pady=(14, 6))

        ctk.CTkFrame(header_row, width=4, fg_color="#2563EB",
                     corner_radius=2).pack(side="left", fill="y", padx=(0, 10))
        ctk.CTkLabel(header_row, text="Add to Purchase Order",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     anchor="w").pack(side="left", fill="x", expand=True)

        # ── SECTION 1 — Shipment Details ─────────────────────────────────────
        s1_card = ctk.CTkFrame(self.recv_left_frame, fg_color="#2a2a3e",
                               corner_radius=10)
        s1_card.pack(fill="x", padx=10, pady=(0, 8))

        # Section 1 header label with left-border accent
        s1_hdr = ctk.CTkFrame(s1_card, fg_color="transparent")
        s1_hdr.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkFrame(s1_hdr, width=3, fg_color="#3d5a80",
                     corner_radius=1).pack(side="left", fill="y", padx=(0, 8))
        ctk.CTkLabel(s1_hdr, text="SHIPMENT DETAILS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#8899aa", anchor="w").pack(side="left")

        # Inner grid frame — 2-col layout (label | widget)
        s1_grid = ctk.CTkFrame(s1_card, fg_color="transparent")
        s1_grid.pack(fill="x", padx=12, pady=(0, 12))
        s1_grid.grid_columnconfigure(1, weight=1)

        # Row 0 — Vendor Name
        ctk.CTkLabel(s1_grid, text="Vendor Name", anchor="w",
                     width=110).grid(row=0, column=0, padx=(0, 8), pady=5, sticky="w")
        self.vendor_entry = ctk.CTkEntry(s1_grid, state="normal",
                                         placeholder_text="e.g. MedSupply Co.")
        self.vendor_entry.grid(row=0, column=1, columnspan=2, pady=5, sticky="ew")
        # Bind vendor change to filter product combobox
        self.vendor_entry.bind("<KeyRelease>", self._on_vendor_change)
        self.vendor_entry.bind("<FocusOut>", self._on_vendor_change)

        # Row 1 — Product Name + Refresh button
        ctk.CTkLabel(s1_grid, text="Product", anchor="w",
                     width=110).grid(row=1, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_product_var = ctk.StringVar(value="")
        self.recv_product_combo = ctk.CTkComboBox(
            s1_grid, state="normal",
            variable=self.recv_product_var,
            values=[], command=self._on_product_change)
        self.recv_product_combo.grid(row=1, column=1, pady=5, sticky="ew")
        ctk.CTkButton(s1_grid, text="↻", width=32, height=28,
                      fg_color="#374151", hover_color="#4B5563",
                      font=ctk.CTkFont(size=14),
                      command=self.refresh_product_list).grid(
            row=1, column=2, padx=(6, 0), pady=5)

        # Row 2 — Date Received
        ctk.CTkLabel(s1_grid, text="Date Received", anchor="w",
                     width=110).grid(row=2, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_date_entry = ctk.CTkEntry(s1_grid, state="normal",
                                            placeholder_text="YYYY-MM-DD")
        self.recv_date_entry.grid(row=2, column=1, columnspan=2, pady=5, sticky="ew")
        self.recv_date_entry.insert(0, date.today().strftime("%Y-%m-%d"))

        # Row 3 — Quantity
        ctk.CTkLabel(s1_grid, text="Quantity", anchor="w",
                     width=110).grid(row=3, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_qty_entry = ctk.CTkEntry(s1_grid, state="normal",
                                           placeholder_text="e.g. 50")
        self.recv_qty_entry.grid(row=3, column=1, columnspan=2, pady=5, sticky="ew")

        # Row 4 — Total Cost
        ctk.CTkLabel(s1_grid, text="Total Cost ($)", anchor="w",
                     width=110).grid(row=4, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_cost_entry = ctk.CTkEntry(s1_grid, state="normal",
                                            placeholder_text="e.g. 250.00")
        self.recv_cost_entry.grid(row=4, column=1, columnspan=2, pady=5, sticky="ew")

        # ── SECTION 2 — Product Verification (read-only auto-fill) ───────────
        s2_card = ctk.CTkFrame(self.recv_left_frame, fg_color="#252535",
                               corner_radius=10)
        s2_card.pack(fill="x", padx=10, pady=(0, 8))

        s2_hdr = ctk.CTkFrame(s2_card, fg_color="transparent")
        s2_hdr.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkFrame(s2_hdr, width=3, fg_color="#6366f1",
                     corner_radius=1).pack(side="left", fill="y", padx=(0, 8))
        ctk.CTkLabel(s2_hdr, text="AUTO-FILL  ·  READ-ONLY",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#8899aa", anchor="w").pack(side="left")

        s2_grid = ctk.CTkFrame(s2_card, fg_color="transparent")
        s2_grid.pack(fill="x", padx=12, pady=(0, 12))
        s2_grid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(s2_grid, text="Manufacture Date", anchor="w",
                     width=110).grid(row=0, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_mfg_date_display = ctk.CTkEntry(s2_grid, state="disabled")
        self.recv_mfg_date_display.grid(row=0, column=1, pady=5, sticky="ew")

        ctk.CTkLabel(s2_grid, text="Expiry Date", anchor="w",
                     width=110).grid(row=1, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_expiry_display = ctk.CTkEntry(s2_grid, state="disabled")
        self.recv_expiry_display.grid(row=1, column=1, pady=5, sticky="ew")

        ctk.CTkLabel(s2_grid, text="Unit Price", anchor="w",
                     width=110).grid(row=2, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_price_display = ctk.CTkEntry(s2_grid, state="disabled")
        self.recv_price_display.grid(row=2, column=1, pady=5, sticky="ew")

        ctk.CTkLabel(s2_grid, text="Mfg Barcode", anchor="w",
                     width=110).grid(row=3, column=0, padx=(0, 8), pady=5, sticky="w")
        self.recv_mfg_barcode_display = ctk.CTkEntry(s2_grid, state="disabled")
        self.recv_mfg_barcode_display.grid(row=3, column=1, pady=5, sticky="ew")

        # ── SECTION 3 — Action ───────────────────────────────────────────────
        s3_card = ctk.CTkFrame(self.recv_left_frame, fg_color="transparent")
        s3_card.pack(fill="x", padx=10, pady=(0, 12))

        ctk.CTkButton(s3_card, text="＋  Add to Queue",
                      fg_color="#2563EB", hover_color="#1d4ed8",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      height=42, corner_radius=8,
                      command=self._add_to_queue).pack(fill="x")

        # Stable status label container — prevents layout shift on text appear/clear
        status_container = ctk.CTkFrame(s3_card, fg_color="transparent", height=36)
        status_container.pack(fill="x", pady=(6, 0))
        status_container.pack_propagate(False)

        self.recv_status_label = ctk.CTkLabel(
            status_container, text="",
            font=ctk.CTkFont(size=12), text_color="#22c55e",
            wraplength=360, anchor="center", justify="center")
        self.recv_status_label.pack(fill="both", expand=True)

        # --- Right Frame ---
        self.recv_right_frame = ctk.CTkFrame(self.tab_receive)
        self.recv_right_frame.pack(side="right", fill="both", expand=True, padx=(0, 10), pady=10)
        self.recv_right_frame.grid_rowconfigure(1, weight=1)
        self.recv_right_frame.grid_columnconfigure(0, weight=1)

        # --- Zone B: Pending Purchase Orders Treeview ---
        ctk.CTkLabel(self.recv_right_frame, text="Pending Purchase Orders",
                     font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, pady=(10, 5), padx=20, sticky="w")

        po_columns = ("Vendor", "Qty", "Product", "Unit Price", "Line Total", "Mfg Date", "Expiry", "Barcode")
        self.tree_po = ttk.Treeview(self.recv_right_frame, columns=po_columns,
                                    show="tree", selectmode="extended")
        self.tree_po.heading("#0", text="Vendor / Item", anchor="w")
        self.tree_po.column("#0", width=200, anchor="w")
        self.tree_po.heading("Vendor", text="Vendor")
        self.tree_po.heading("Qty", text="Qty")
        self.tree_po.heading("Product", text="Product")
        self.tree_po.heading("Unit Price", text="Unit Price")
        self.tree_po.heading("Line Total", text="Line Total")
        self.tree_po.heading("Mfg Date", text="Mfg Date")
        self.tree_po.heading("Expiry", text="Expiry")
        self.tree_po.heading("Barcode", text="Barcode")
        self.tree_po.column("Vendor", width=100, anchor="w")
        self.tree_po.column("Qty", width=50, anchor="center")
        self.tree_po.column("Product", width=140, anchor="w")
        self.tree_po.column("Unit Price", width=75, anchor="e")
        self.tree_po.column("Line Total", width=80, anchor="e")
        self.tree_po.column("Mfg Date", width=85, anchor="center")
        self.tree_po.column("Expiry", width=85, anchor="center")
        self.tree_po.column("Barcode", width=100, anchor="center")
        self.tree_po.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))

        scrollbar = ttk.Scrollbar(self.recv_right_frame, orient="vertical",
                                  command=self.tree_po.yview)
        self.tree_po.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 5))

        # --- Zone C: Reconciliation & Commit ---
        commit_frame = ctk.CTkFrame(self.recv_right_frame, fg_color="transparent")
        commit_frame.grid(row=2, column=0, columnspan=2, pady=(5, 10), padx=15, sticky="ew")
        commit_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(commit_frame, text="Invoice Total ($):").grid(
            row=0, column=0, padx=(0, 5), pady=5, sticky="w")
        self.invoice_total_entry = ctk.CTkEntry(commit_frame, width=120,
                                                 placeholder_text="0.00")
        self.invoice_total_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkButton(commit_frame, text="Remove Selected", width=120,
                      fg_color="#dc3545", hover_color="#c82333",
                      command=self._remove_selected_from_queue).grid(
            row=0, column=2, padx=5, pady=5)

        ctk.CTkButton(commit_frame, text="Commit Shipment", width=160,
                      fg_color="#28a745", hover_color="#218838",
                      command=self._commit_shipment).grid(
            row=0, column=3, padx=5, pady=5)

        self.btn_print_labels = ctk.CTkButton(commit_frame, text="Print Labels", width=120,
                      fg_color="#7c3aed", hover_color="#6d28d9",
                      command=self._print_bulk_labels, state="disabled")
        self.btn_print_labels.grid(row=0, column=4, padx=5, pady=5)

        self.commit_status_label = ctk.CTkLabel(commit_frame, text="",
                                                 font=ctk.CTkFont(size=12),
                                                 text_color="#28a745", wraplength=500)
        self.commit_status_label.grid(row=1, column=0, columnspan=5, pady=(2, 0), sticky="w")

        # --- Vendor Payables (bottom) ---
        payables_frame = ctk.CTkFrame(self.recv_right_frame, fg_color="transparent")
        payables_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10), padx=15, sticky="ew")
        payables_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(payables_frame, text="Vendor Payables",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=(0, 5), pady=(5, 0), sticky="w")

        ctk.CTkLabel(payables_frame, text="Vendor:").grid(
            row=1, column=0, padx=(0, 5), pady=5, sticky="w")
        self.vendor_select_entry = ctk.CTkEntry(payables_frame, width=180,
                                                placeholder_text="Vendor name")
        self.vendor_select_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(payables_frame, text="Calculate Total Owed", width=160,
                      command=self.calculate_vendor_owed).grid(
            row=1, column=2, padx=5, pady=5)

        self.vendor_owed_label = ctk.CTkLabel(payables_frame, text="Total Owed: $0.00",
                                              font=ctk.CTkFont(size=14, weight="bold"),
                                              text_color="#dc3545")
        self.vendor_owed_label.grid(row=2, column=0, columnspan=3, pady=(5, 0), sticky="w")

        # --- New: Print All Tags Button ---
        print_all_tags_frame = ctk.CTkFrame(payables_frame, fg_color="transparent")
        print_all_tags_frame.grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky="w")
        self.print_all_tags_btn = ctk.CTkButton(
            print_all_tags_frame,
            text="Print All Tags (Selected)",
            width=200,
            fg_color="#4f46e5", 
            hover_color="#4338ca",
            command=self._print_all_selected_tags,
            state="disabled"
        )
        self.print_all_tags_btn.pack(side="left")
        
        tag_status_label = ctk.CTkLabel(
            print_all_tags_frame,
            text="Print individual tags from queued items",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            wraplength=300
        )
        tag_status_label.pack(side="left", padx=(10, 0))

        # --- Zone D: Shipment History (from receiving_log) ---
        hist_header_frame = ctk.CTkFrame(self.recv_right_frame, fg_color="transparent")
        hist_header_frame.grid(row=4, column=0, pady=(10, 5), padx=20, sticky="ew")

        ctk.CTkLabel(hist_header_frame, text="Shipment History",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")

        ctk.CTkLabel(hist_header_frame, text="Filter by date:").pack(side="left", padx=(20, 4))
        self.hist_date_entry = ctk.CTkEntry(hist_header_frame, width=110,
                                            placeholder_text="YYYY-MM-DD")
        self.hist_date_entry.pack(side="left", padx=(0, 4))
        ctk.CTkButton(hist_header_frame, text="Filter", width=60,
                      fg_color="#2563EB", hover_color="#1d4ed8",
                      command=self._filter_history_by_date).pack(side="left", padx=(0, 4))
        ctk.CTkButton(hist_header_frame, text="Clear", width=50,
                      fg_color="#6b7280", hover_color="#4b5563",
                      command=self._clear_history_filter).pack(side="left")

        hist_columns = ("Product", "Date", "Qty", "Total Cost", "Barcode")
        self._history_sort_asc = False
        self.tree_history = ttk.Treeview(self.recv_right_frame, columns=hist_columns,
                                          show="tree headings", selectmode="browse")
        self.tree_history.column("#0", width=160, anchor="w")
        self.tree_history.heading("#0", text="Vendor")
        for col in hist_columns:
            if col == "Date":
                self.tree_history.heading(col, text="Date ▼",
                    command=lambda: self._sort_history_by_date())
            else:
                self.tree_history.heading(col, text=col)
        self.tree_history.column("Product", width=180, anchor="w")
        self.tree_history.column("Date", width=100, anchor="center")
        self.tree_history.column("Qty", width=50, anchor="center")
        self.tree_history.column("Total Cost", width=90, anchor="e")
        self.tree_history.column("Barcode", width=120, anchor="center")
        self.tree_history.grid(row=5, column=0, sticky="nsew", padx=10, pady=(0, 10))

        hist_scrollbar = ttk.Scrollbar(self.recv_right_frame, orient="vertical",
                                       command=self.tree_history.yview)
        self.tree_history.configure(yscroll=hist_scrollbar.set)
        hist_scrollbar.grid(row=5, column=1, sticky="ns", pady=(0, 10))

        # Configure grid weights for history
        self.recv_right_frame.grid_rowconfigure(5, weight=1)

    def _on_vendor_change(self, event=None):
        """Filter product combobox based on vendor entry."""
        vendor = self.vendor_entry.get().strip()
        if vendor:
            names = database.get_products_by_vendor(vendor)
        else:
            names = database.get_unique_product_names()
        self.recv_product_combo.configure(values=names if names else [])
        current = self.recv_product_var.get()
        if current not in names:
            self.recv_product_var.set("")

    def _print_all_selected_tags(self):
        import logging
        logging.debug("UI_EVENT: _print_all_selected_tags executed")
        pass

    def _on_product_change(self, choice):
        if not choice:
            self._set_disabled_text(self.recv_mfg_date_display, "")
            self._set_disabled_text(self.recv_expiry_display, "")
            self._set_disabled_text(self.recv_price_display, "")
            self._set_disabled_text(self.recv_mfg_barcode_display, "")
            return
        # Pass vendor name to get vendor-specific template
        vendor = self.vendor_entry.get().strip()
        template = database.get_product_template(choice, vendor_name=vendor)
        if template:
            tpl_name, tpl_price, tpl_mfg_barcode, tpl_expiry, tpl_mfg_date = template
            self._set_disabled_text(self.recv_mfg_date_display, tpl_mfg_date or "")
            self._set_disabled_text(self.recv_expiry_display, tpl_expiry or "")
            self._set_disabled_text(self.recv_price_display, f"${tpl_price:.2f}" if tpl_price else "")
            self._set_disabled_text(self.recv_mfg_barcode_display, tpl_mfg_barcode or "")
        else:
            self._set_disabled_text(self.recv_mfg_date_display, "")
            self._set_disabled_text(self.recv_expiry_display, "")
            self._set_disabled_text(self.recv_price_display, "")
            self._set_disabled_text(self.recv_mfg_barcode_display, "")

    def _set_disabled_text(self, entry, text):
        entry.configure(state="normal")
        entry.delete(0, "end")
        if text:
            entry.insert(0, text)
        entry.configure(state="disabled")

    def refresh_product_list(self):
        """Populates the product combobox with distinct drug names.
        Uses get_unique_product_names() as single source of truth — mirrors
        the Inventory tab exactly (same WHERE status='In Stock' + DISTINCT name).
        """
        vendor = self.vendor_entry.get().strip()
        if vendor:
            names = database.get_products_by_vendor(vendor)
        else:
            names = database.get_unique_product_names()
        self.recv_product_combo.configure(values=names if names else [])
        current = self.recv_product_var.get()
        if current not in names:
            self.recv_product_var.set("")

    def _add_to_queue(self):
        vendor = self.vendor_entry.get().strip()
        product_display = self.recv_product_var.get().strip()
        recv_date = self.recv_date_entry.get().strip()
        qty_str = self.recv_qty_entry.get().strip()
        cost_str = self.recv_cost_entry.get().strip()

        if not vendor or not product_display or not recv_date or not qty_str or not cost_str:
            messagebox.showwarning("Missing Fields", "Please fill in all fields.")
            return

        try:
            date.fromisoformat(recv_date)
        except ValueError:
            messagebox.showerror("Invalid Date", "Please enter a valid date in YYYY-MM-DD format.")
            return

        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Quantity must be a positive whole number.")
            return

        try:
            cost = float(cost_str)
        except ValueError:
            messagebox.showerror("Invalid Cost", "Total Cost must be a number.")
            return

        # product_display is now a plain drug name from the combobox (no vendor suffix)
        product_name = product_display

        template = database.get_product_template(product_name, vendor_name=vendor)
        if not template:
            messagebox.showerror("Error", f"No existing product found named '{product_name}'.\nPlease add the product first via the Add Product tab.")
            return

        tpl_name, tpl_price, tpl_mfg_barcode, tpl_expiry, tpl_mfg_date = template

        if vendor not in self.receiving_session:
            self.receiving_session[vendor] = {
                "total_quantity": 0,
                "vendor_asking_price": 0.0,
                "items": []
            }

        self.receiving_session[vendor]["total_quantity"] += qty
        self.receiving_session[vendor]["items"].append({
            "name": product_name,
            "qty": qty,
            "price": tpl_price,
            "cost": cost,
            "mfg_barcode": tpl_mfg_barcode,
            "internal_barcode": "",
            "mfg_date": tpl_mfg_date or "",
            "exp_date": tpl_expiry or "",
            "date_received": recv_date,
        })

        self.vendor_entry.delete(0, "end")
        self.recv_product_var.set("")
        self.recv_qty_entry.delete(0, "end")
        self.recv_cost_entry.delete(0, "end")
        self.recv_date_entry.delete(0, "end")
        self.recv_date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        self._set_disabled_text(self.recv_mfg_date_display, "")
        self._set_disabled_text(self.recv_expiry_display, "")

        self._refresh_po_treeview()

        item_count = len(self.receiving_session[vendor]["items"])
        self.recv_status_label.configure(
            text=f"Queued {qty}x {product_name} for {vendor} ({item_count} item(s) pending).",
            text_color="#007bff")

        def _clear_status():
            if self.recv_status_label.winfo_exists():
                self.recv_status_label.configure(text="")

        self.recv_status_label.after(5000, _clear_status)

    def _refresh_po_treeview(self):
        for item in self.tree_po.get_children():
            self.tree_po.delete(item)

        has_items = bool(self.receiving_session)
        if hasattr(self, 'btn_print_labels'):
            self.btn_print_labels.configure(state="normal" if has_items else "disabled")

        for vendor, data in self.receiving_session.items():
            total_qty = data["total_quantity"]
            total_cost = sum(i["cost"] for i in data["items"])
            vendor_iid = self.tree_po.insert("", "end", text=f"{vendor}  ({total_qty} units)",
                                              values=("", "", "", "", f"${total_cost:.2f}", "", "", ""),
                                              open=True)
            for item in data["items"]:
                line_total = item["qty"] * item["price"]
                self.tree_po.insert(vendor_iid, "end", text=item["name"],
                                     values=(vendor, item["qty"], item["name"], f"${item['price']:.2f}",
                                             f"${line_total:.2f}", item["mfg_date"], item["exp_date"],
                                             ""))

    def _remove_selected_from_queue(self):
        selected = self.tree_po.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a vendor or item row to remove.")
            return

        for iid in selected:
            parent_iid = self.tree_po.parent(iid)
            if parent_iid:
                child_text = self.tree_po.item(iid, "text")
                for vendor, data in self.receiving_session.items():
                    data["items"] = [i for i in data["items"] if i["name"] != child_text]
                    data["total_quantity"] = sum(i["qty"] for i in data["items"])
            else:
                vendor_text = self.tree_po.item(iid, "text")
                vendor_name = vendor_text.rsplit("  (", 1)[0] if "  (" in vendor_text else vendor_text
                self.receiving_session.pop(vendor_name, None)

        self.receiving_session = {v: d for v, d in self.receiving_session.items() if d["items"]}
        self._refresh_po_treeview()

    # -------------------------------------------------------------------------
    # OBSERVER / EVENT-BUS: Cross-tab sync signal
    # -------------------------------------------------------------------------
    def _notify_inventory_updated(self):
        """Central observer method. Call this whenever the products or receiving_log
        tables change. Refreshes all dependent tab views in dependency order.
        This is the single sync point — no tab needs to know about any other tab.
        """
        self.load_inventory()           # Inventory tab — pulls live product rows
        self.load_sales_report()        # Sales Report tab — reflects any refund/sale side-effects
        self.refresh_add_tab_templates()  # Add Product tab — keeps template combobox current
        self.refresh_product_list()     # Receive tab product combobox — stays in sync

    def _print_bulk_labels(self):
        if not self.receiving_session:
            messagebox.showinfo("Nothing to Print", "The pending queue is empty.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        today = datetime.now().strftime("%Y-%m-%d")
        batch_folder = os.path.abspath(os.path.join(barcode_logic.LABELS_DIR, f"batch_{today}_{timestamp}"))
        os.makedirs(batch_folder, exist_ok=True)

        boxes = []
        for vendor, data in self.receiving_session.items():
            for item in data["items"]:
                for _ in range(item["qty"]):
                    bc = barcode_logic.generate_internal_barcode(vendor)
                    boxes.append({
                        "name": item["name"],
                        "price": item["price"],
                        "mfg_barcode": item["mfg_barcode"],
                        "expiry": item.get("exp_date", ""),
                        "mfg_date": item.get("mfg_date", ""),
                        "vendor": vendor,
                        "barcode": bc,
                    })

        BulkLabelPrintDialog(self, boxes, batch_folder)

    def _commit_shipment(self):
        if not self.receiving_session:
            messagebox.showwarning("Empty Queue", "No pending items to commit.")
            return

        committed_vendors = []
        try:
            for vendor, data in self.receiving_session.items():
                for item in data["items"]:
                    pre_barcodes = item.get("pre_barcodes", [])
                    database.receive_inventory_atomically(
                        vendor, item["name"], item["date_received"],
                        item["qty"], item["cost"],
                        item["price"], item["mfg_barcode"],
                        item["exp_date"], item["mfg_date"],
                        barcode_logic.generate_internal_barcode,
                        pre_generated_barcodes=pre_barcodes if pre_barcodes else None
                    )
                committed_vendors.append(vendor)
        except Exception as e:
            messagebox.showerror("Transaction Failed",
                                 f"Partial commit may have occurred.\n\n{str(e)}")
            return

        vendor_summary = ", ".join(committed_vendors)
        total_items = sum(d["total_quantity"] for d in self.receiving_session.values())
        self.receiving_session.clear()

        self._refresh_po_treeview()
        self.invoice_total_entry.delete(0, "end")

        # ARCH FIX: emit the inventory-updated signal to sync ALL tabs at once
        self._notify_inventory_updated()
        self.load_receiving_log()

        self.commit_status_label.configure(
            text=f"Committed {total_items} unit(s) from {vendor_summary}.",
            text_color="#28a745")

        def _clear_commit_status():
            if self.commit_status_label.winfo_exists():
                self.commit_status_label.configure(text="")

        self.commit_status_label.after(5000, _clear_commit_status)

    def _load_shipment_history(self, filter_date=None):
        """Load historical shipments grouped by vendor into tree_history."""
        if not hasattr(self, "tree_history"):
            return
        for item in self.tree_history.get_children():
            self.tree_history.delete(item)

        vendor_groups = defaultdict(list)
        for row in database.get_all_receiving_log(filter_date=filter_date):
            vendor_groups[row[1]].append(row)

        suffix = f" — {filter_date}" if filter_date else ""
        for vendor_name, rows in sorted(vendor_groups.items()):
            total_units = sum(r[4] for r in rows)
            vendor_iid = self.tree_history.insert(
                "", "end", text=f"{vendor_name} ({total_units} units{suffix})", open=True)
            for row in rows:
                self.tree_history.insert(vendor_iid, "end", values=(
                    row[2], row[3], row[4], f"${row[5]:.2f}", row[6]
                ))

    def _filter_history_by_date(self):
        """Filter shipment history to show only entries from the entered date."""
        raw = self.hist_date_entry.get().strip()
        if not raw:
            self._load_shipment_history()
            return
        try:
            date.fromisoformat(raw)
        except ValueError:
            messagebox.showerror("Invalid Date", "Please enter a valid date in YYYY-MM-DD format.")
            return
        self._load_shipment_history(filter_date=raw)

    def _clear_history_filter(self):
        """Clear date filter and show all shipments."""
        self.hist_date_entry.delete(0, "end")
        self._load_shipment_history()

    def _sort_history_by_date(self):
        """Sort child rows within each vendor group by date column."""
        for parent_iid in self.tree_history.get_children(""):
            children = list(self.tree_history.get_children(parent_iid))
            children.sort(
                key=lambda c: self.tree_history.item(c, "values")[1],
                reverse=not self._history_sort_asc
            )
            for idx, child in enumerate(children):
                self.tree_history.move(child, parent_iid, idx)
        self._history_sort_asc = not self._history_sort_asc
        arrow = "▲" if self._history_sort_asc else "▼"
        self.tree_history.heading("Date", text=f"Date {arrow}")

    def load_receiving_log(self):
        if not hasattr(self, "tree_po"):
            return
        self._refresh_po_treeview()
        self._load_shipment_history()

    def calculate_vendor_owed(self):
        vendor = self.vendor_select_entry.get().strip()
        if not vendor:
            messagebox.showwarning("Missing Vendor", "Please enter a vendor name.")
            return
        total = database.get_vendor_total_owed(vendor)
        self.vendor_owed_label.configure(text=f"Total Owed to {vendor}: ${total:.2f}")

    def refund_item(self):
        selected = self.tree_report.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an item to refund.")
            return
            
        item = selected[0]
        sold_id = self.tree_report.item(item, 'values')[0]
        
        try:
            database.reverse_sale(sold_id)
            self.load_sales_report()
            messagebox.showinfo("Refunded", "Item successfully returned to inventory.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refund item:\n{str(e)}")

    # --- Templates Tab ---
    def setup_templates_tab(self):
        self.tab_templates.grid_rowconfigure(1, weight=1)
        self.tab_templates.grid_columnconfigure(0, weight=1)
        
        add_frame = ctk.CTkFrame(self.tab_templates, fg_color="transparent")
        add_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Name:").pack(side="left", padx=(0, 5))
        self.tpl_name_entry = ctk.CTkEntry(add_frame, width=200)
        self.tpl_name_entry.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(add_frame, text="Price:").pack(side="left", padx=(0, 5))
        self.tpl_price_entry = ctk.CTkEntry(add_frame, width=100)
        self.tpl_price_entry.pack(side="left", padx=(0, 15))
        
        add_btn = ctk.CTkButton(add_frame, text="Add Template", command=self.add_template_gui)
        add_btn.pack(side="left")
        
        edit_btn = ctk.CTkButton(add_frame, text="Update Selected", fg_color="#28a745", hover_color="#218838", command=self.update_template_gui)
        edit_btn.pack(side="left", padx=10)
        
        del_btn = ctk.CTkButton(add_frame, text="Delete Selected", fg_color="#c42b1c", hover_color="#9e2216", command=self.delete_template_gui)
        del_btn.pack(side="right", padx=10)
        
        columns = ("ID", "Name", "Price")
        self.tree_tpl = ttk.Treeview(self.tab_templates, columns=columns, show="headings")
        
        for col in columns:
            self.tree_tpl.heading(col, text=col)
            
        self.tree_tpl.column("ID", width=50, anchor="center")
        self.tree_tpl.column("Name", width=400, anchor="w")
        self.tree_tpl.column("Price", width=100, anchor="center")
        
        self.tree_tpl.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        scrollbar = ttk.Scrollbar(self.tab_templates, orient="vertical", command=self.tree_tpl.yview)
        self.tree_tpl.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        
        self.tree_tpl.bind("<<TreeviewSelect>>", self.on_template_tree_select)
        
    def load_templates_grid(self):
        for item in self.tree_tpl.get_children():
            self.tree_tpl.delete(item)
            
        templates = database.get_templates()
        for tpl in templates:
            self.tree_tpl.insert("", "end", values=(tpl[0], tpl[1], f"${tpl[2]:.2f}"))

    def on_template_tree_select(self, event):
        selected = self.tree_tpl.selection()
        if not selected:
            return
        item = selected[0]
        values = self.tree_tpl.item(item, 'values')
        
        self.tpl_name_entry.delete(0, 'end')
        self.tpl_name_entry.insert(0, values[1])
        
        self.tpl_price_entry.delete(0, 'end')
        price = values[2].replace('$', '')
        self.tpl_price_entry.insert(0, price)

    def add_template_gui(self):
        name = self.tpl_name_entry.get().strip()
        price_str = self.tpl_price_entry.get().strip()
        
        if not name or not price_str:
            messagebox.showwarning("Warning", "Name and Price required.")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            messagebox.showwarning("Warning", "Price must be a number.")
            return
            
        database.add_template(name, price)
        self.tpl_name_entry.delete(0, 'end')
        self.tpl_price_entry.delete(0, 'end')
        self.load_templates_grid()
        self.refresh_add_tab_templates()
        
    def update_template_gui(self):
        selected = self.tree_tpl.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a template to update.")
            return
            
        item = selected[0]
        tpl_id = self.tree_tpl.item(item, 'values')[0]
        
        name = self.tpl_name_entry.get().strip()
        price_str = self.tpl_price_entry.get().strip()
        
        if not name or not price_str:
            messagebox.showwarning("Warning", "Name and Price required.")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            messagebox.showwarning("Warning", "Price must be a number.")
            return
            
        database.update_template(tpl_id, name, price)
        self.tpl_name_entry.delete(0, 'end')
        self.tpl_price_entry.delete(0, 'end')
        self.load_templates_grid()
        self.refresh_add_tab_templates()

    def delete_template_gui(self):
        selected = self.tree_tpl.selection()
        if not selected:
            return
            
        item = selected[0]
        tpl_id = self.tree_tpl.item(item, 'values')[0]
        database.delete_template(tpl_id)
        self.load_templates_grid()
        self.refresh_add_tab_templates()

    # --- Settings Tab ---
    def setup_settings_tab(self):
        self.tab_settings.grid_columnconfigure((0, 1), weight=1)
        
        title_label = ctk.CTkLabel(self.tab_settings, text="Application Settings", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.grid(row=0, column=0, columnspan=3, padx=20, pady=(20, 30))
        
        config = barcode_logic.load_config()
        
        # Label Settings
        name_label = ctk.CTkLabel(self.tab_settings, text="Pharmacy Name:", anchor="w")
        name_label.grid(row=1, column=0, padx=(100, 10), pady=10, sticky="w")
        self.set_name_entry = ctk.CTkEntry(self.tab_settings, width=300)
        self.set_name_entry.insert(0, config.get("pharmacy_name", "My Pharmacy"))
        self.set_name_entry.grid(row=1, column=1, padx=(10, 100), pady=10, sticky="w")
        
        font_label = ctk.CTkLabel(self.tab_settings, text="Pharmacy Name Font Size:", anchor="w")
        font_label.grid(row=2, column=0, padx=(100, 10), pady=10, sticky="w")
        self.set_font_entry = ctk.CTkEntry(self.tab_settings, width=300)
        self.set_font_entry.insert(0, str(config.get("font_size", 20)))
        self.set_font_entry.grid(row=2, column=1, padx=(10, 100), pady=10, sticky="w")
        
        self.set_price_var = ctk.BooleanVar(value=config.get("include_price", True))
        self.set_price_check = ctk.CTkCheckBox(self.tab_settings, text="Include Price on Label", variable=self.set_price_var)
        self.set_price_check.grid(row=3, column=0, columnspan=3, pady=20)
        
        # Database Path
        db_label = ctk.CTkLabel(self.tab_settings, text="Database Path:", anchor="w")
        db_label.grid(row=4, column=0, padx=(100, 10), pady=10, sticky="w")
        self.set_db_entry = ctk.CTkEntry(self.tab_settings, width=300)
        self.set_db_entry.insert(0, config.get("db_path", "pharmacy.db"))
        self.set_db_entry.grid(row=4, column=1, padx=(10, 10), pady=10, sticky="w")
        
        browse_btn = ctk.CTkButton(self.tab_settings, text="Browse...", width=100, command=self.browse_db_path)
        browse_btn.grid(row=4, column=2, padx=(0, 100), sticky="w")
        
        save_btn = ctk.CTkButton(self.tab_settings, text="Save Settings", command=self.save_settings, height=40, font=ctk.CTkFont(size=16))
        save_btn.grid(row=5, column=0, columnspan=3, pady=20)
        
        backup_btn = ctk.CTkButton(self.tab_settings, text="Backup Database", command=self.backup_database_gui, height=40, font=ctk.CTkFont(size=16), fg_color="#17a2b8", hover_color="#138496")
        backup_btn.grid(row=6, column=0, columnspan=3, pady=10)

        role_label = ctk.CTkLabel(self.tab_settings, text="User Role:", anchor="w")
        role_label.grid(row=7, column=0, padx=(100, 10), pady=10, sticky="w")
        self.role_var = ctk.StringVar(value="Admin")
        self.role_segmented = ctk.CTkSegmentedButton(
            self.tab_settings, values=["Admin", "User"], variable=self.role_var,
            command=self._on_role_change
        )
        self.role_segmented.grid(row=7, column=1, padx=(10, 100), pady=10, sticky="w")

        self.user_role = "Admin"
        self._update_role_controls()
        
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
        is_admin = self.user_role == "Admin"
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
        folder = ctk.filedialog.askdirectory(title="Select Backup Destination Folder")
        if folder:
            try:
                backup_path = database.backup_database(folder)
                messagebox.showinfo("Backup Success", f"Database successfully backed up to:\n{backup_path}")
            except Exception as e:
                messagebox.showerror("Backup Failed", str(e))
        
    def save_settings(self):
        new_name = self.set_name_entry.get().strip()
        new_font_str = self.set_font_entry.get().strip()
        include_price = self.set_price_var.get()
        new_db_path = self.set_db_entry.get().strip()
        
        if not new_name:
            messagebox.showerror("Error", "Pharmacy Name cannot be empty.")
            return
            
        try:
            new_font = int(new_font_str)
            if new_font <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Font size must be a positive integer.")
            return
            
        new_config = {
            "pharmacy_name": new_name,
            "font_size": new_font,
            "include_price": include_price,
            "db_path": new_db_path or "pharmacy.db"
        }
        
        try:
            with open(barcode_logic.CONFIG_FILE, "w") as f:
                json.dump(new_config, f, indent=4)
                
            # Initialize DB at new path if it doesn't exist
            database.init_db()
            
            # Refresh all tabs to use the newly connected database
            self.load_inventory()
            self.load_sales_report()
            self.load_templates_grid()
            self.refresh_add_tab_templates()
            
            messagebox.showinfo("Success", "Settings saved successfully! Connected to database.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config:\n{str(e)}")

class LabelDesignerPopup(ctk.CTkToplevel):
    def __init__(self, parent, name, price, barcode, expiry="", mfg="", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        self.title("Label Designer")
        self.geometry("800x500")
        self.product_name = name
        self.internal_barcode = barcode
        self.price = price
        self.product_expiry = expiry
        self.product_mfg = mfg
        
        # Grid layout: 2 columns
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1, minsize=300)
        self.grid_rowconfigure(0, weight=1)
        
        # Left Canvas with Scrollbars
        self.canvas_frame = ctk.CTkFrame(self)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient="vertical")
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient="horizontal")
        
        self.preview_canvas = tk.Canvas(
            self.canvas_frame, bg="white",
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
        )
        
        self.h_scroll.config(command=self.preview_canvas.xview)
        self.v_scroll.config(command=self.preview_canvas.yview)
        
        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.preview_canvas.pack(side="left", fill="both", expand=True)
        
        self.preview_canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.preview_canvas.bind("<Shift-MouseWheel>", self._on_canvas_shift_mousewheel)
        
        # Internal LabelCanvas for rendering
        self._label_canvas = LabelCanvas(self, 400, 300)
        self._label_canvas.var_context = {}
        
        # Right Controls
        self.controls_frame = ctk.CTkFrame(self)
        self.controls_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        
        self._dynamic_entries = {}
        self._build_controls(name, price, expiry)
        
        self.current_img = None

        def _safe_preview():
            if self.winfo_exists():
                self.update_preview()

        self.after(100, _safe_preview)
        
    def _build_controls(self, name, price, expiry):
        ctk.CTkLabel(self.controls_frame, text="Design Overrides", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 10))
        
        template_loaded = False
        if os.path.exists(TEMPLATE_PATH):
            try:
                with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                    template_data = json.load(f)
                template_loaded = True
            except Exception:
                template_loaded = False
        
        if template_loaded:
            self._label_canvas.clear()
            load_label(TEMPLATE_PATH, self._label_canvas)
            self._build_dynamic_fields(template_data)
        else:
            self._build_default_fields(name, price, expiry)
        
        # Buttons at bottom
        print_btn = ctk.CTkButton(self.controls_frame, text="Quick Print", command=self.print_label, height=40, font=ctk.CTkFont(size=16, weight="bold"))
        print_btn.pack(pady=(10, 30), padx=20, fill="x", side="bottom")

        adv_btn = ctk.CTkButton(self.controls_frame, text="Open Label Designer", command=self.launch_m8_engine, height=40, fg_color="#1f538d", font=ctk.CTkFont(size=16, weight="bold"))
        adv_btn.pack(pady=(10, 0), padx=20, fill="x", side="bottom")
        
    def _build_dynamic_fields(self, template_data):
        scroll_frame = ctk.CTkScrollableFrame(self.controls_frame, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        
        ctk.CTkLabel(scroll_frame, text="Template Fields", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(5, 10))
        
        defaults = {
            "NAME": self.product_name or "",
            "BARCODE": self.internal_barcode or "",
            "PHARMACY_NAME": "My Pharmacy",
            "PHARMACY_ADDRESS": "",
            "DRUG_NAME": "",
            "BATCH_NO": "",
            "MANUFACTURER": "",
            "QTY": "",
            "PRICE": f"${float(self._get_numeric_price()):.2f}" if self._get_numeric_price() else "$0.00",
            "EXPIRY": self.product_expiry or "",
            "MFG_DATE": self.product_mfg or "",
        }
        
        for elem_data in template_data.get("elements", []):
            if elem_data.get("type") != "text":
                continue
            elem_id = elem_data.get("id", "")
            props = elem_data.get("props", {})
            raw_text = props.get("text", "")
            
            label_text = raw_text.replace("{{", "").replace("}}", "")
            if len(label_text) > 30:
                label_text = label_text[:27] + "..."

            default_val = raw_text
            if raw_text in defaults:
                default_val = defaults[raw_text]
            else:
                var_match = _extract_first_var(raw_text)
                if var_match and var_match in defaults:
                    default_val = defaults[var_match]

            ctk.CTkLabel(scroll_frame, text=label_text, anchor="w", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=15, pady=(8, 2))
            entry = ctk.CTkEntry(scroll_frame, width=200)
            entry.insert(0, default_val)
            entry.pack(padx=15, pady=(0, 2), fill="x")
            entry.bind("<KeyRelease>", lambda e: self.update_preview())
            
            self._dynamic_entries[elem_id] = entry
            
    def _build_default_fields(self, name, price, expiry):
        ctk.CTkLabel(self.controls_frame, text="Text Edits", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 5))
        
        self.name_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.name_entry.insert(0, name)
        self.name_entry.pack(padx=20, pady=5)
        self.name_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        
        self.price_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.price_entry.insert(0, f"${float(price):.2f}" if price else "$0.00")
        self.price_entry.pack(padx=20, pady=5)
        self.price_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        
        self.expiry_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.expiry_entry.insert(0, expiry or "")
        self.expiry_entry.pack(padx=20, pady=5)
        self.expiry_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        
        self.mfg_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.mfg_entry.insert(0, self.product_mfg or "")
        self.mfg_entry.pack(padx=20, pady=5)
        self.mfg_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        
    def _get_numeric_price(self):
        try:
            return float(self.price)
        except (ValueError, TypeError):
            return None
        
    def launch_m8_engine(self):
        ctx = self._build_context()
        current_name = ctx.get("NAME", "")
        current_price = ctx.get("PRICE", "")
        current_expiry = ctx.get("EXPIRY", self.product_expiry)
        current_mfg = ctx.get("MFG_DATE", self.product_mfg)

        try:
            barcode_logic.open_label_engine(
                "NEW", self.internal_barcode, current_name, current_price,
                expiry=current_expiry, manufacture=current_mfg,
                show_name=True,
                show_price=True,
                show_expiry=True,
                show_barcode_text=True,
            )

        except Exception as e:
            messagebox.showerror("Error", f"Could not open Label Designer:\n{str(e)}")
            
    def _get_field_value(self, field, default=""):
        if hasattr(self, "name_entry") and field == "name":
            return self.name_entry.get()
        if hasattr(self, "price_entry") and field == "price":
            return self.price_entry.get()
        if hasattr(self, "expiry_entry") and field == "expiry":
            return self.expiry_entry.get()
        if hasattr(self, "mfg_entry") and field == "mfg":
            return self.mfg_entry.get()
        return default
            
    def update_preview(self):
        context = self._build_context()
        self._label_canvas.var_context = context
        
        self.preview_canvas.delete("all")
        draw_elements(self.preview_canvas, self._label_canvas.elements, scale=1.0, context=context)
        
        self.preview_canvas.config(scrollregion=self.preview_canvas.bbox("all"))
        self.preview_canvas.xview_moveto(0)
        self.preview_canvas.yview_moveto(0)
        
    def _build_context(self):
        if self._dynamic_entries:
            ctx = {}
            for elem_id, entry in self._dynamic_entries.items():
                elem = self._label_canvas.get_element(elem_id)
                if elem and elem.type == "text":
                    raw_text = elem.props.get("text", "")
                    for var_name in _extract_all_vars(raw_text):
                        ctx[var_name] = entry.get()
            ctx["BARCODE"] = self.internal_barcode
            return ctx
        else:
            ctx = {}
            if hasattr(self, "name_entry"):
                ctx["NAME"] = self.name_entry.get()
            if hasattr(self, "price_entry"):
                ctx["PRICE"] = self.price_entry.get()
            if hasattr(self, "expiry_entry"):
                ctx["EXPIRY"] = self.expiry_entry.get()
            if hasattr(self, "mfg_entry"):
                ctx["MFG_DATE"] = self.mfg_entry.get()
            ctx["BARCODE"] = self.internal_barcode
            return ctx
        
    def _on_canvas_mousewheel(self, event):
        self.preview_canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _on_canvas_shift_mousewheel(self, event):
        self.preview_canvas.xview_scroll(-1 * (event.delta // 120), "units")

    def print_label(self):
        try:
            self._label_canvas.var_context = self._build_context()
            temp_path = os.path.join(tempfile.gettempdir(), f"print_{self.internal_barcode}.png")
            export_to_png(temp_path, self._label_canvas)
            os.startfile(temp_path, "print")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print:\n{str(e)}")


class QuickReceiveModal(ctk.CTkToplevel):
    def __init__(self, parent, product_name: str, vendor_name: str, barcode: str):
        super().__init__(parent)
        self.title("Quick Receive Inventory")
        self.geometry("380x240")
        self.grab_set()

        self.parent = parent
        self.product_name = product_name
        self.vendor_name = vendor_name
        self.barcode = barcode

        ctk.CTkLabel(self, text=f"Receive {product_name} from {vendor_name}",
                      font=ctk.CTkFont(size=15, weight="bold"), wraplength=340
                      ).pack(padx=20, pady=(18, 12))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Quantity:", anchor="w").grid(row=0, column=0, padx=(0, 8), pady=5, sticky="w")
        self.qty_entry = ctk.CTkEntry(form, placeholder_text="e.g. 10")
        self.qty_entry.grid(row=0, column=1, sticky="ew", pady=5)

        ctk.CTkLabel(form, text="Total Cost ($):", anchor="w").grid(row=1, column=0, padx=(0, 8), pady=5, sticky="w")
        self.cost_entry = ctk.CTkEntry(form, placeholder_text="0.00")
        self.cost_entry.grid(row=1, column=1, sticky="ew", pady=5)
        self.cost_entry.insert(0, "0.00")

        self.qty_entry.focus_set()
        self.bind("<Return>", lambda e: self._submit())

        ctk.CTkButton(self, text="Submit", command=self._submit, height=36,
                       font=ctk.CTkFont(size=14)).pack(padx=20, pady=(10, 15), fill="x")

    def _submit(self):
        qty_str = self.qty_entry.get().strip()
        cost_str = self.cost_entry.get().strip()

        if not qty_str:
            messagebox.showwarning("Missing Quantity", "Please enter a quantity.", parent=self)
            return
        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Quantity must be a positive whole number.", parent=self)
            return

        try:
            cost = float(cost_str) if cost_str else 0.0
        except ValueError:
            messagebox.showerror("Invalid Cost", "Cost must be a number.", parent=self)
            return

        existing = database.get_product_by_barcode(self.barcode)
        if not existing:
            messagebox.showerror("Error", f"Could not find product with barcode {self.barcode}.", parent=self)
            return

        _, tpl_name, tpl_price, tpl_mfg_barcode, _, _, tpl_expiry, tpl_mfg_date, _ = existing

        try:
            database.receive_inventory_atomically(
                self.vendor_name, self.product_name, date.today().isoformat(), qty, qty * tpl_price,
                tpl_price, tpl_mfg_barcode, tpl_expiry, tpl_mfg_date,
                barcode_logic.generate_internal_barcode
            )
        except Exception as e:
            messagebox.showerror("Transaction Failed",
                                 f"No inventory was saved.\n\n{str(e)}", parent=self)
            return

        parent = self.parent
        self.destroy()

        def _refresh():
            if parent.winfo_exists():
                parent.load_inventory()
                parent.load_receiving_log()

        parent.after(100, _refresh)
        messagebox.showinfo("Success",
                            f"Received {qty}x {self.product_name} from {self.vendor_name}.")


class BulkAddModal(ctk.CTkToplevel):
    def __init__(self, parent, name, price, mfg_barcode, expiry_date, manufacture_date, vendor_name):
        super().__init__(parent)
        self.title("Quick Receive (Bulk)")
        self.geometry("420x420")
        self.grab_set()

        self.parent = parent
        self.name = name
        self.price = price
        self.mfg_barcode = mfg_barcode
        self.expiry_date = expiry_date
        self.manufacture_date = manufacture_date
        self.vendor_name = vendor_name

        ctk.CTkLabel(self, text="Bulk Receive Product",
                      font=ctk.CTkFont(size=16, weight="bold")).pack(padx=20, pady=(16, 10))

        info_frame = ctk.CTkFrame(self, fg_color="#2a2a3e", corner_radius=8)
        info_frame.pack(fill="x", padx=20, pady=(0, 10))
        info_frame.grid_columnconfigure(1, weight=1)

        fields = [
            ("Name:", name),
            ("Price:", f"${price:.2f}"),
            ("Vendor:", vendor_name),
            ("Mfg Barcode:", mfg_barcode or "—"),
            ("Expiry:", expiry_date or "—"),
            ("Mfg Date:", manufacture_date or "—"),
        ]
        for i, (label, value) in enumerate(fields):
            ctk.CTkLabel(info_frame, text=label, font=ctk.CTkFont(size=12),
                         text_color="#8899aa", anchor="w").grid(row=i, column=0, padx=(12, 8), pady=3, sticky="w")
            ctk.CTkLabel(info_frame, text=value, font=ctk.CTkFont(size=12),
                         anchor="w").grid(row=i, column=1, padx=(0, 12), pady=3, sticky="w")

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Quantity:", anchor="w").grid(row=0, column=0, padx=(0, 8), pady=8, sticky="w")
        self.qty_entry = ctk.CTkEntry(form, placeholder_text="e.g. 50")
        self.qty_entry.grid(row=0, column=1, sticky="ew", pady=8)

        ctk.CTkLabel(form, text="Total Wholesale Cost ($):", anchor="w").grid(row=1, column=0, padx=(0, 8), pady=8, sticky="w")
        self.cost_entry = ctk.CTkEntry(form, placeholder_text="e.g. 250.00")
        self.cost_entry.grid(row=1, column=1, sticky="ew", pady=8)
        self.cost_entry.insert(0, "0.00")

        self.qty_entry.focus_set()
        self.bind("<Return>", lambda e: self._submit())

        ctk.CTkButton(self, text="Add to Queue",
                      command=self._submit, height=40,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color="#2563EB", hover_color="#1d4ed8"
                      ).pack(padx=20, pady=(14, 16), fill="x")

    def _submit(self):
        qty_str = self.qty_entry.get().strip()
        cost_str = self.cost_entry.get().strip()

        if not qty_str:
            messagebox.showwarning("Missing Quantity", "Please enter a quantity.", parent=self)
            return
        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Quantity must be a positive whole number.", parent=self)
            return

        try:
            total_cost = float(cost_str) if cost_str else 0.0
        except ValueError:
            messagebox.showerror("Invalid Cost", "Total Cost must be a number.", parent=self)
            return

        vendor = self.vendor_name
        if vendor not in self.parent.receiving_session:
            self.parent.receiving_session[vendor] = {
                "total_quantity": 0,
                "vendor_asking_price": 0.0,
                "items": []
            }

        self.parent.receiving_session[vendor]["total_quantity"] += qty
        self.parent.receiving_session[vendor]["items"].append({
            "name": self.name,
            "qty": qty,
            "price": self.price,
            "cost": total_cost,
            "mfg_barcode": self.mfg_barcode,
            "internal_barcode": "",
            "mfg_date": self.manufacture_date or "",
            "exp_date": self.expiry_date or "",
            "date_received": datetime.now().strftime('%Y-%m-%d'),
        })

        parent = self.parent
        qty_ref = qty
        self.destroy()

        parent.name_entry.delete(0, 'end')
        parent.price_entry.delete(0, 'end')
        parent.mfg_entry.delete(0, 'end')
        parent.expiry_entry.delete(0, 'end')
        parent.mfg_date_entry.delete(0, 'end')
        parent.vendor_name_entry.delete(0, 'end')
        parent.template_var.set("Select a template...")

        parent.tab_view.set("Receive Inventory")
        parent.vendor_entry.delete(0, "end")
        parent.vendor_entry.insert(0, vendor)
        parent._refresh_po_treeview()
        parent.recv_status_label.configure(
            text=f"Queued {qty_ref}x {self.name} for {vendor}.",
            text_color="#007bff")

        def _clear_status():
            if parent.recv_status_label.winfo_exists():
                parent.recv_status_label.configure(text="")
        parent.recv_status_label.after(5000, _clear_status)
        messagebox.showinfo("Success", f"Queued {qty_ref}x {self.name} for {vendor} in Pending PO.")


class BulkLabelPrintDialog(ctk.CTkToplevel):
    def __init__(self, parent, boxes, batch_folder):
        super().__init__(parent)
        self.title(f"Bulk Label Printer — {len(boxes)} boxes pending")
        self.geometry("960x620")
        self.grab_set()

        self._parent = parent
        self._boxes = boxes
        self._save_dir = batch_folder
        self._current_img = None

        self.grid_columnconfigure(0, weight=3, minsize=420)
        self.grid_columnconfigure(1, weight=2, minsize=300)
        self.grid_rowconfigure(1, weight=1)

        # ── Header: clickable save path ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=15, pady=(12, 0))

        ctk.CTkLabel(header, text="Save Path:",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#8899aa").pack(side="left")
        path_lbl = ctk.CTkLabel(header, text=batch_folder,
                     font=ctk.CTkFont(size=11),
                     text_color="#60a5fa", cursor="hand2")
        path_lbl.pack(side="left", padx=(6, 0))
        path_lbl.bind("<Button-1>", lambda e: self._copy_path())
        ctk.CTkLabel(header, text="(click to open folder)",
                     font=ctk.CTkFont(size=10),
                     text_color="#666").pack(side="left", padx=(6, 0))

        # ── Left: Treeview ──
        tree_frame = ctk.CTkFrame(self)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)

        cols = ("Name", "Vendor", "Barcode", "Price")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("#0", text="#")
        self.tree.column("#0", width=40, anchor="center")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("Name", width=160, anchor="w")
        self.tree.column("Vendor", width=100, anchor="w")
        self.tree.column("Barcode", width=110, anchor="center")
        self.tree.column("Price", width=70, anchor="e")

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=tree_scroll.set)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        for idx, box in enumerate(self._boxes, 1):
            self.tree.insert("", "end", iid=str(idx - 1),
                             text=str(idx),
                             values=(box["name"], box["vendor"],
                                     box["barcode"], f"${box['price']:.2f}"))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Right: Controls ──
        right = ctk.CTkFrame(self)
        right.grid(row=1, column=1, sticky="nsew", padx=(0, 15), pady=10)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right, text="Label Controls",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, pady=(12, 5), padx=15, sticky="w")

        self.preview_canvas = tk.Canvas(right, bg="white", highlightthickness=0)
        self.preview_canvas.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))

        btn_col = ctk.CTkFrame(right, fg_color="transparent")
        btn_col.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 12))
        btn_col.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btn_col, text="Open Label Designer",
                      fg_color="#1f538d", hover_color="#17406b",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._open_designer).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        ctk.CTkButton(btn_col, text="Export All PNG",
                      fg_color="#2563EB", hover_color="#1d4ed8",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._export_all).grid(
            row=1, column=0, sticky="ew", padx=(0, 3), pady=(0, 6))

        ctk.CTkButton(btn_col, text="Print All",
                      fg_color="#7c3aed", hover_color="#6d28d9",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._print_all).grid(
            row=1, column=1, sticky="ew", padx=(3, 0), pady=(0, 6))

        ctk.CTkButton(btn_col, text="Close", height=32,
                      fg_color="#6b7280", hover_color="#4b5563",
                      command=self.destroy).grid(
            row=3, column=0, columnspan=2, sticky="ew")

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        box = self._boxes[idx]
        self._render_preview(box)

    def _render_preview(self, box):
        self.preview_canvas.delete("all")
        try:
            from label_engine.canvas_core import LabelCanvas
            from label_engine.export import load_template, export_to_png as _exp, TEMPLATE_PATH as _TP

            if not os.path.exists(_TP):
                self.preview_canvas.create_text(
                    10, 10, anchor="nw",
                    text="No label template found.\nDesign one in the Label Designer first.",
                    fill="#888", font=("Arial", 12))
                return

            lbl = LabelCanvas(None, 400, 300)
            load_template(lbl)
            lbl.var_context = {
                "NAME": box["name"],
                "PRICE": f"${box['price']:.2f}" if box["price"] else "$0.00",
                "BARCODE": box["barcode"],
                "EXPIRY": box.get("expiry", ""),
                "MFG_DATE": box.get("mfg_date", ""),
            }
            import tempfile as _tmp
            tmp = os.path.join(_tmp.gettempdir(), f"_preview_{box['barcode']}.png")
            _exp(tmp, lbl)

            from PIL import Image, ImageTk
            img = Image.open(tmp)
            cw = max(self.preview_canvas.winfo_width(), 200)
            ch = max(self.preview_canvas.winfo_height(), 150)
            scale = min(cw / img.width, ch / img.height)
            rw, rh = int(img.width * scale), int(img.height * scale)
            img = img.resize((rw, rh), Image.LANCZOS)
            self._current_img = ImageTk.PhotoImage(img)
            ox = (cw - rw) // 2
            oy = (ch - rh) // 2
            self.preview_canvas.create_image(ox, oy, anchor="nw", image=self._current_img)
            self.preview_canvas.config(scrollregion=self.preview_canvas.bbox("all"))
            img.close()
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception as e:
            self.preview_canvas.create_text(
                10, 10, anchor="nw",
                text=f"Preview error:\n{e}", fill="#f55", font=("Arial", 11))

    def _open_designer(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a box from the list first.", parent=self)
            return
        box = self._boxes[int(sel[0])]
        LabelDesignerPopup(self, box["name"], f"{box['price']:.2f}",
                           box["barcode"], box.get("expiry", ""), box.get("mfg_date", ""))

    def _export_all(self):
        try:
            from label_engine.canvas_core import LabelCanvas
            from label_engine.export import load_template, export_to_png, TEMPLATE_PATH

            if not os.path.exists(TEMPLATE_PATH):
                messagebox.showinfo("No Template",
                    "No label template found. Design one in the Label Designer first.", parent=self)
                return

            lbl = LabelCanvas(None, 400, 300)
            load_template(lbl)

            for box in self._boxes:
                lbl.var_context = {
                    "NAME": box["name"],
                    "PRICE": f"${box['price']:.2f}" if box["price"] else "$0.00",
                    "BARCODE": box["barcode"],
                    "EXPIRY": box.get("expiry", ""),
                    "MFG_DATE": box.get("mfg_date", ""),
                }
                png_path = os.path.join(self._save_dir, f"{box['barcode']}.png")
                export_to_png(png_path, lbl)

            messagebox.showinfo("Export Complete",
                f"{len(self._boxes)} label(s) saved to:\n{self._save_dir}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export labels:\n{str(e)}", parent=self)

    def _print_all(self):
        try:
            from label_engine.canvas_core import LabelCanvas
            from label_engine.export import load_template, export_to_png, print_label, TEMPLATE_PATH

            if not os.path.exists(TEMPLATE_PATH):
                messagebox.showinfo("No Template",
                    "No label template found. Design one in the Label Designer first.", parent=self)
                return

            lbl = LabelCanvas(None, 400, 300)
            load_template(lbl)

            for box in self._boxes:
                lbl.var_context = {
                    "NAME": box["name"],
                    "PRICE": f"${box['price']:.2f}" if box["price"] else "$0.00",
                    "BARCODE": box["barcode"],
                    "EXPIRY": box.get("expiry", ""),
                    "MFG_DATE": box.get("mfg_date", ""),
                }
                print_label(lbl)

            messagebox.showinfo("Print Sent",
                f"{len(self._boxes)} label(s) sent to printer.", parent=self)
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print labels:\n{str(e)}", parent=self)

    def _copy_path(self):
        if os.path.isdir(self._save_dir):
            os.startfile(self._save_dir, "open")
        else:
            self.clipboard_clear()
            self.clipboard_append(self._save_dir)


class EditBatchDialog(ctk.CTkToplevel):
    def __init__(self, parent, row):
        super().__init__(parent)
        batch_id, name, price, mfg_barcode, int_barcode, status, expiry, mfg_date, vendor = row
        self.title(f"Edit Batch: {name}")
        self.geometry("460x620")
        self.grab_set()

        self.parent = parent
        self.batch_id = batch_id
        self.int_barcode = int_barcode
        self._original_vendor = vendor or "N/A"

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text=f"Edit: {name}", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text=f"Batch ID: {batch_id}  |  Internal: {int_barcode}",
                      text_color="gray").pack(anchor="w")

        sep = ctk.CTkFrame(self, height=1, fg_color="gray50")
        sep.pack(fill="x", padx=20, pady=(5, 10))

        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=(0, 5))
        form.grid_columnconfigure(1, weight=1)

        fields = [
            ("Name:", "name_var", name),
            ("Price ($):", "price_var", f"{price:.2f}"),
            ("Mfg Barcode:", "mfg_barcode_var", mfg_barcode),
            ("Internal Barcode:", "int_barcode_var", int_barcode),
            ("Expiry Date:", "expiry_var", expiry or ""),
            ("Mfg Date:", "mfg_var", mfg_date or ""),
            ("Vendor:", "vendor_var", vendor or "N/A"),
        ]

        for i, (label, var_name, value) in enumerate(fields):
            ctk.CTkLabel(form, text=label, anchor="w").grid(row=i, column=0, padx=(0, 10), pady=5, sticky="w")
            var = ctk.StringVar(value=value)
            setattr(self, var_name, var)
            entry = ctk.CTkEntry(form, textvariable=var)
            entry.grid(row=i, column=1, sticky="ew", pady=5)
            if var_name == "int_barcode_var":
                entry.configure(state="disabled")
                ctk.CTkLabel(form, text="(Auto-Generated)", text_color="gray",
                             font=ctk.CTkFont(size=11)).grid(row=i, column=2, padx=(6, 0), pady=5, sticky="w")

        status_row = len(fields)
        ctk.CTkLabel(form, text="Status:", anchor="w").grid(row=status_row, column=0, padx=(0, 10), pady=5, sticky="w")
        self.status_var = ctk.StringVar(value=status or "In Stock")
        ctk.CTkSegmentedButton(form, values=["In Stock", "Sold"], variable=self.status_var
        ).grid(row=status_row, column=1, sticky="ew", pady=5)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(btn_frame, text="Save Changes", command=self._save, height=38,
                       font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10), fill="x", expand=True)
        ctk.CTkButton(btn_frame, text="Open Label Designer", command=self._open_label_engine, height=38,
                       fg_color="#1f538d", font=ctk.CTkFont(size=14)).pack(side="left", fill="x", expand=True)

    def _save(self):
        name = self.name_var.get().strip()
        price_str = self.price_var.get().strip()
        mfg_barcode = self.mfg_barcode_var.get().strip()
        expiry = self.expiry_var.get().strip()
        mfg = self.mfg_var.get().strip()
        status = self.status_var.get()
        vendor = self.vendor_var.get().strip() or "N/A"

        if not name:
            messagebox.showerror("Error", "Name is required.")
            return
        if not mfg_barcode:
            messagebox.showerror("Error", "Manufacturer barcode is required.")
            return

        try:
            price = float(price_str)
        except ValueError:
            messagebox.showerror("Error", "Price must be a valid number.")
            return

        if expiry and not self.parent._validate_date(expiry, "Expiry Date", allow_empty=True):
            return
        if mfg and not self.parent._validate_date(mfg, "Manufacture Date", allow_empty=True):
            return

        if expiry and mfg:
            try:
                exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
                mfg_dt = datetime.strptime(mfg, "%Y-%m-%d")
                if mfg_dt >= exp_dt:
                    messagebox.showerror("Error", "Manufacture date must be before expiry date.")
                    return
            except ValueError:
                return

        try:
            database.update_product_full(
                self.batch_id, name, price, mfg_barcode, self.int_barcode,
                expiry, mfg, status, vendor
            )
            vendor_changed = (self._original_vendor in (None, '', 'N/A')
                              and vendor not in (None, '', 'N/A'))
            if vendor_changed:
                database.log_shipment(
                    vendor, name, datetime.now().strftime('%Y-%m-%d'),
                    1, price, self.int_barcode
                )
            parent = self.parent
            self.destroy()

            def _refresh():
                if parent.winfo_exists():
                    parent.load_inventory()
                    parent.load_receiving_log()

            parent.after(100, _refresh)
            if vendor_changed:
                QuickReceiveModal(parent, name, vendor, self.int_barcode)
            else:
                messagebox.showinfo("Success", "Batch updated successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update batch:\n{str(e)}")

    def _open_label_engine(self):
        expiry = self.expiry_var.get().strip()
        mfg = self.mfg_var.get().strip()
        price = self.price_var.get().strip()
        name = self.name_var.get().strip()
        try:
            barcode_logic.open_label_engine(
                "NEW", self.int_barcode, name, price,
                expiry=expiry, manufacture=mfg
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Label Designer:\n{str(e)}")
