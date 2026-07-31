import customtkinter as ctk
from tkinter import ttk, messagebox
import database
import audit_log
import receipt_engine
import barcode_logic
import i18n
from ui_helpers import apply_treeview_style


def setup_checkout_tab(self):
    self.pos_cart = []
    self.pos_patient_id = None

    self.tab_checkout.grid_rowconfigure(1, weight=1)
    self.tab_checkout.grid_columnconfigure(0, weight=2)
    self.tab_checkout.grid_columnconfigure(1, weight=1)

    # ── Left Frame (Cart) ──────────────────────────────────
    left_frame = ctk.CTkFrame(self.tab_checkout, fg_color="transparent")
    left_frame.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")
    left_frame.grid_rowconfigure(1, weight=1)
    left_frame.grid_columnconfigure(0, weight=1)

    header = ctk.CTkFrame(left_frame, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    ctk.CTkLabel(header, text="New Sale (POS)", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")

    add_row = ctk.CTkFrame(left_frame, fg_color="transparent")
    add_row.grid(row=0, column=0, sticky="ew", pady=(36, 0))
    add_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(add_row, text="Barcode:", width=70, anchor="w").grid(row=0, column=0, padx=(0, 5))
    self.checkout_barcode_entry = ctk.CTkEntry(add_row, width=220, placeholder_text="Scan or type barcode...")
    self.checkout_barcode_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

    def on_barcode_enter(event=None):
        barcode = self.checkout_barcode_entry.get().strip()
        if barcode:
            _pos_scan_barcode(self, barcode)
            self.checkout_barcode_entry.delete(0, "end")

    self.checkout_barcode_entry.bind("<Return>", on_barcode_enter)

    # NOTE: Global barcode listener in ui.py handles cross-tab scanning.
    # The local key listener below is kept for backward compatibility
    # with the checkout-specific Return key behavior.
    def global_key_listener(event):
        if self.tab_view.get() != i18n.t("checkout"):
            return
        if event.keysym == "Return":
            on_barcode_enter()
    self.bind("<KeyRelease>", global_key_listener, add="+")

    ctk.CTkButton(add_row, text="Scan", width=90, fg_color="#3B82F6", hover_color="#2563EB", command=on_barcode_enter).grid(row=0, column=2)

    cart_columns = ("Item", "Qty", "Price", "Int. Barcode", "Vendor", "Expiry")
    self.tree_cart = ttk.Treeview(left_frame, columns=cart_columns, show="headings", height=10)
    apply_treeview_style(self.tree_cart)

    for col in cart_columns:
        self.tree_cart.heading(col, text=col)
    self.tree_cart.column("Item", width=170, anchor="w")
    self.tree_cart.column("Qty", width=50, anchor="center")
    self.tree_cart.column("Price", width=80, anchor="e")
    self.tree_cart.column("Int. Barcode", width=120, anchor="w")
    self.tree_cart.column("Vendor", width=100, anchor="w")
    self.tree_cart.column("Expiry", width=95, anchor="center")
    self.tree_cart.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    cart_scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree_cart.yview)
    self.tree_cart.configure(yscroll=cart_scrollbar.set)
    cart_scrollbar.grid(row=1, column=1, sticky="ns", pady=(8, 0))

    cart_btn_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
    cart_btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    cart_btn_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=0)

    ctk.CTkButton(cart_btn_frame, text="Qty +1", width=70, fg_color="#3B82F6", hover_color="#2563EB",
                  command=lambda: _pos_adjust_qty(self, +1)).grid(row=0, column=0, padx=(0, 4))
    ctk.CTkButton(cart_btn_frame, text="Qty -1", width=70, fg_color="#6c757d", hover_color="#5a6268",
                  command=lambda: _pos_adjust_qty(self, -1)).grid(row=0, column=1, padx=(0, 4))
    ctk.CTkButton(cart_btn_frame, text="Remove", width=80, fg_color="#EF4444", hover_color="#DC2626",
                  command=lambda: _pos_remove_selected(self)).grid(row=0, column=2, padx=(0, 4))
    ctk.CTkButton(cart_btn_frame, text="Clear Cart", width=90, fg_color="gray40", hover_color="gray30",
                  command=lambda: _pos_clear_cart(self)).grid(row=0, column=3)

    # ── Right Frame (Summary & Payment) ────────────────────
    right_frame = ctk.CTkFrame(self.tab_checkout, fg_color="#2D2D2D", corner_radius=10)
    right_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="n")
    right_frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(right_frame, text="Order Summary", font=ctk.CTkFont(size=18, weight="bold"), text_color="#FFFFFF").grid(row=0, column=0, padx=20, pady=(16, 12), sticky="w")
    ctk.CTkFrame(right_frame, height=1, fg_color="#555555").grid(row=1, column=0, sticky="ew", padx=20)

    patient_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
    patient_frame.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="ew")
    ctk.CTkLabel(patient_frame, text="Patient:", text_color="#A0A0A0").pack(side="left", padx=(0, 5))
    self.checkout_patient_var = ctk.StringVar()
    self.checkout_patient_combo = ctk.CTkComboBox(patient_frame, variable=self.checkout_patient_var, width=160)
    self.checkout_patient_combo.pack(side="left")

    if hasattr(database, "get_all_patients"):
        _pos_refresh_patients(self)

    self.checkout_patient_combo.bind("<<ComboboxSelected>>", lambda e: _pos_on_patient_select(self))

    self.checkout_total_label = ctk.CTkLabel(right_frame, text="Total: $0.00", font=ctk.CTkFont(size=26, weight="bold"), text_color="#10B981")
    self.checkout_total_label.grid(row=3, column=0, padx=20, pady=(14, 6))

    self.checkout_items_count_label = ctk.CTkLabel(right_frame, text="0 item(s) in cart", font=ctk.CTkFont(size=13), text_color="#A0A0A0")
    self.checkout_items_count_label.grid(row=4, column=0, padx=20, pady=(0, 10))

    ctk.CTkFrame(right_frame, height=1, fg_color="#555555").grid(row=5, column=0, sticky="ew", padx=20)

    ctk.CTkLabel(right_frame, text="Payment Method", font=ctk.CTkFont(size=14, weight="bold"), text_color="#FFFFFF").grid(row=6, column=0, padx=20, pady=(12, 4), sticky="w")
    self.checkout_payment_var = ctk.StringVar(value="Cash")
    self.checkout_payment_seg = ctk.CTkSegmentedButton(right_frame, values=["Cash", "Card", "Insurance"], variable=self.checkout_payment_var, width=260)
    self.checkout_payment_seg.grid(row=7, column=0, padx=20, pady=(0, 10))

    self.checkout_confirm_btn = ctk.CTkButton(right_frame, text="Complete Sale", height=44, font=ctk.CTkFont(size=16, weight="bold"), fg_color="#10B981", hover_color="#059669", command=lambda: _pos_complete_sale(self))
    self.checkout_confirm_btn.grid(row=8, column=0, padx=20, pady=(10, 16), sticky="ew")

    # ── Bottom Right (Receipts) ─────────────────────────────
    receipts_frame = ctk.CTkFrame(self.tab_checkout, fg_color="transparent")
    receipts_frame.grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="nsew")
    receipts_frame.grid_rowconfigure(1, weight=1)
    receipts_frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(receipts_frame, text="Recent Receipts", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))

    receipt_columns = ("ID", "Time", "Total", "Method")
    self.tree_receipts = ttk.Treeview(receipts_frame, columns=receipt_columns, show="headings", height=6)
    apply_treeview_style(self.tree_receipts)

    for col in receipt_columns:
        self.tree_receipts.heading(col, text=col)
    self.tree_receipts.column("ID", width=40, anchor="center")
    self.tree_receipts.column("Time", width=140, anchor="w")
    self.tree_receipts.column("Total", width=80, anchor="e")
    self.tree_receipts.column("Method", width=70, anchor="center")
    self.tree_receipts.grid(row=1, column=0, sticky="nsew")

    receipt_scrollbar = ttk.Scrollbar(receipts_frame, orient="vertical", command=self.tree_receipts.yview)
    self.tree_receipts.configure(yscrollcommand=receipt_scrollbar.set)
    receipt_scrollbar.grid(row=1, column=1, sticky="ns")

    self.tree_receipts.bind("<Double-1>", lambda e: _pos_show_receipt_detail(self))

    self.checkout_barcode_entry.focus()
    _pos_refresh_receipts(self)


# ═════════════════════════════════════════════════════════════════════════════
#  Internal POS Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _pos_scan_barcode(self, barcode: str):
    product = database.get_product_by_internal_barcode(barcode)
    if not product:
        product = database.get_product_by_barcode(barcode)

    if not product:
        messagebox.showwarning("Not Found", f"Product with barcode '{barcode}' not found.", parent=self.tab_checkout)
        return

    int_barcode = product[4]
    for item in self.pos_cart:
        if item.get("internal_barcode") == int_barcode:
            item["quantity"] += 1
            _pos_refresh_cart(self)
            return

    self.pos_cart.append({
        "product_name": product[1],
        "price_at_time": product[2],
        "internal_barcode": int_barcode,
        "vendor": product[8] if product[8] else "N/A",
        "expiry_date": product[6] if product[6] else "N/A",
        "quantity": 1,
    })
    _pos_refresh_cart(self)


def _pos_adjust_qty(self, delta: int):
    selected = self.tree_cart.selection()
    if not selected:
        return
    iid = selected[0]
    idx = self.tree_cart.index(iid)
    if idx >= len(self.pos_cart):
        return
    self.pos_cart[idx]["quantity"] = max(1, self.pos_cart[idx]["quantity"] + delta)
    _pos_refresh_cart(self)


def _pos_remove_selected(self):
    selected = self.tree_cart.selection()
    if not selected:
        messagebox.showwarning("No Selection", "Select a cart item to remove.", parent=self.tab_checkout)
        return
    for iid in reversed([self.tree_cart.index(s) for s in selected]):
        if 0 <= iid < len(self.pos_cart):
            self.pos_cart.pop(iid)
    _pos_refresh_cart(self)


def _pos_clear_cart(self):
    self.pos_cart.clear()
    self.pos_patient_id = None
    self.checkout_patient_var.set("None")
    _pos_refresh_cart(self)


def _pos_refresh_cart(self):
    for item in self.tree_cart.get_children():
        self.tree_cart.delete(item)

    total_qty = 0
    for idx, entry in enumerate(self.pos_cart):
        tag = "even" if idx % 2 == 0 else "odd"
        qty = entry["quantity"]
        total_qty += qty
        self.tree_cart.insert("", "end", values=(
            entry["product_name"],
            qty,
            f"${entry['price_at_time'] * qty:.2f}",
            entry["internal_barcode"],
            entry["vendor"],
            entry["expiry_date"],
        ), tags=(tag,))

    total = sum(e["price_at_time"] * e["quantity"] for e in self.pos_cart)
    self.checkout_total_label.configure(text=f"Total: ${total:.2f}")
    self.checkout_items_count_label.configure(text=f"{total_qty} item(s) in cart")


def _pos_refresh_patients(self):
    try:
        patients = database.get_all_patients()
    except Exception:
        patients = []
    patient_names = ["None"] + [f"{p[1]} (ID: {p[0]})" for p in patients]
    self.checkout_patient_combo.configure(values=patient_names)
    self.checkout_patient_var.set("None")


def _pos_on_patient_select(self):
    val = self.checkout_patient_var.get()
    if val and val != "None":
        try:
            pid = int(val.split("(ID: ")[1].strip(")"))
            self.pos_patient_id = pid
        except Exception:
            self.pos_patient_id = None
    else:
        self.pos_patient_id = None


def _pos_complete_sale(self):
    if not self.pos_cart:
        messagebox.showwarning("Empty Cart", "Add items before completing a sale.", parent=self.tab_checkout)
        return

    method = self.checkout_payment_var.get()
    total = sum(e["price_at_time"] * e["quantity"] for e in self.pos_cart)

    patient_name = ""
    patient_val = self.checkout_patient_var.get()
    if patient_val and patient_val != "None":
        patient_name = patient_val.split("(ID:")[0].strip()

    config = barcode_logic.load_config()
    pharmacy_info = {
        "pharmacy_name": config.get("pharmacy_name", "My Pharmacy"),
        "address": config.get("address", ""),
        "phone": config.get("phone", ""),
    }

    try:
        database.create_receipt(method, self.pos_cart, getattr(self, 'pos_patient_id', None))

        conn = database.sqlite3.connect(database.get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM receipts ORDER BY id DESC LIMIT 1")
        receipt_id = cursor.fetchone()[0]
        conn.close()

        receipt_file = receipt_engine.generate_receipt(
            receipt_id, self.pos_cart, total,
            payment_type=method,
            patient_name=patient_name,
            pharmacy_info=pharmacy_info,
        )

        audit_log.log_action("CHECKOUT", f"Receipt ID {receipt_id} created for ${total:.2f}")

        if messagebox.askyesno("Sale Complete",
                               f"Receipt #{receipt_id} — ${total:.2f}\nPayment: {method}\n\nOpen receipt?",
                               parent=self.tab_checkout):
            receipt_engine.open_receipt_file(receipt_file)

        self.pos_cart.clear()
        self.pos_patient_id = None
        _pos_refresh_cart(self)
        _pos_refresh_receipts(self)
        self.checkout_barcode_entry.focus()
    except Exception as e:
        messagebox.showerror("Error", f"Sale failed: {e}", parent=self.tab_checkout)


def _pos_refresh_receipts(self):
    for item in self.tree_receipts.get_children():
        self.tree_receipts.delete(item)

    try:
        conn = database.sqlite3.connect(database.get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, total_amount, payment_method FROM receipts ORDER BY id DESC LIMIT 50")
        receipts = cursor.fetchall()
        conn.close()

        for idx, r in enumerate(receipts):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree_receipts.insert("", "end", values=(
                r[0], r[1], f"${r[2]:.2f}", r[3]), tags=(tag,))
    except Exception:
        pass


def _pos_show_receipt_detail(self):
    selected = self.tree_receipts.selection()
    if not selected:
        return
    receipt_id = int(self.tree_receipts.item(selected[0], "values")[0])

    try:
        items = database.get_receipt_items(receipt_id)
    except Exception:
        messagebox.showerror("Error", "Could not load receipt items.", parent=self.tab_checkout)
        return

    if not items:
        messagebox.showinfo("Receipt Details", f"Receipt #{receipt_id} has no items.", parent=self.tab_checkout)
        return

    lines = [f"Receipt #{receipt_id}\n"]
    subtotal = 0
    for item in items:
        name = item[2]
        qty = item[3]
        price = item[4]
        line_total = qty * price
        subtotal += line_total
        lines.append(f"  {name}  x{qty}  ${line_total:.2f}")

    lines.append(f"\nTotal: ${subtotal:.2f}")
    messagebox.showinfo("Receipt Details", "\n".join(lines), parent=self.tab_checkout)


# ═════════════════════════════════════════════════════════════════════════════
#  Stubs kept for backward compatibility with ui.py imports
# ═════════════════════════════════════════════════════════════════════════════

def _refresh_checkout_patients(self):
    _pos_refresh_patients(self)

def _on_patient_select(self, event=None):
    _pos_on_patient_select(self)

def _checkout_remove_item(self):
    _pos_remove_selected(self)

def _checkout_clear_cart(self):
    _pos_clear_cart(self)

def _refresh_cart_treeview(self):
    _pos_refresh_cart(self)

def _checkout_confirm(self):
    _pos_complete_sale(self)

def _refresh_receipts_history(self):
    _pos_refresh_receipts(self)

def _on_receipt_double_click(self, event):
    _pos_show_receipt_detail(self)

def _print_receipt(self):
    pass

def _refresh_checkout_stock_dropdown(self):
    _pos_refresh_patients(self)

def _on_checkout_product_change(self, selected_name):
    pass

def _checkout_add_item(self):
    pass

def _checkout_update_change(self, event=None):
    pass
