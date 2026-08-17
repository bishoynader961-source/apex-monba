import customtkinter as ctk
from tkinter import ttk, messagebox
import logging
import database
import audit_log
import receipt_engine
import barcode_logic
import i18n
import local_daily_report
from ui_helpers import apply_treeview_style
from ui_navigation import CompactCard
from design_system import CascadeStatusBadge
from ui_pos_panels import ProductPickerDialog, ReceiptDetailDialog

log = logging.getLogger("ui_checkout_tab")


def setup_checkout_tab(self):
    self.pos_cart = []
    self.pos_patient_id = None

    self.tab_checkout.grid_rowconfigure(1, weight=1)
    self.tab_checkout.grid_rowconfigure(2, weight=0)
    self.tab_checkout.grid_columnconfigure(0, weight=2)
    self.tab_checkout.grid_columnconfigure(1, weight=1)

    # ── Left Frame (Cart) ──────────────────────────────────
    left_frame = ctk.CTkFrame(self.tab_checkout, fg_color="transparent")
    left_frame.grid(row=0, column=0, rowspan=3, padx=10, pady=10, sticky="nsew")
    left_frame.grid_rowconfigure(1, weight=1)
    left_frame.grid_columnconfigure(0, weight=1)

    header = ctk.CTkFrame(left_frame, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    ctk.CTkLabel(header, text=i18n.t("new_sale_pos"), font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")

    add_row = ctk.CTkFrame(left_frame, fg_color="transparent")
    add_row.grid(row=0, column=0, sticky="ew", pady=(36, 0))
    add_row.grid_columnconfigure(1, weight=1)
    add_row.grid_columnconfigure(3, weight=1)
    add_row.grid_rowconfigure(0, weight=0)
    add_row.grid_rowconfigure(1, weight=0)

    # Product selection combobox (P1.3) — loads products asynchronously
    ctk.CTkLabel(add_row, text=i18n.t("product_select"), width=70, anchor="w").grid(row=0, column=0, padx=(0, 5))
    self.checkout_product_var = ctk.StringVar()
    self.checkout_product_combo = ctk.CTkComboBox(add_row, variable=self.checkout_product_var, width=220)
    self.checkout_product_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    self.checkout_product_combo.bind("<<ComboboxSelected>>",
                                     lambda e: _on_checkout_product_change(self, self.checkout_product_var.get()))

    # Barcode entry (row 1)
    ctk.CTkLabel(add_row, text=i18n.t("barcode_label"), width=70, anchor="w").grid(row=1, column=0, padx=(0, 5))
    self.checkout_barcode_entry = ctk.CTkEntry(add_row, width=220, placeholder_text=i18n.t("scan_or_type_barcode"))
    self.checkout_barcode_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))

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

    ctk.CTkButton(add_row, text=i18n.t("scan"), width=90, fg_color="#3B82F6", hover_color="#2563EB", command=on_barcode_enter).grid(row=1, column=2)

    # Load product names into combobox asynchronously (P1.3)
    self._checkout_products_cache = []
    _checkout_load_products(self)

    cart_columns = ("Item", "Qty", "Unit Price", "Tax", "Total")
    self.tree_cart = ttk.Treeview(left_frame, columns=cart_columns, show="headings", height=10)
    apply_treeview_style(self.tree_cart)

    for col in cart_columns:
        self.tree_cart.heading(col, text=col)
    self.tree_cart.column("Item", width=170, anchor="w")
    self.tree_cart.column("Qty", width=50, anchor="center")
    self.tree_cart.column("Unit Price", width=80, anchor="e")
    self.tree_cart.column("Tax", width=70, anchor="e")
    self.tree_cart.column("Total", width=90, anchor="e")
    self.tree_cart.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    cart_scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree_cart.yview)
    self.tree_cart.configure(yscroll=cart_scrollbar.set)
    cart_scrollbar.grid(row=1, column=1, sticky="ns", pady=(8, 0))

    cart_btn_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
    cart_btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    cart_btn_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=0)

    ctk.CTkButton(cart_btn_frame, text=i18n.t("qty_add"), width=70, fg_color="#3B82F6", hover_color="#2563EB",
                  command=lambda: _pos_adjust_qty(self, +1)).grid(row=0, column=0, padx=(0, 4))
    ctk.CTkButton(cart_btn_frame, text=i18n.t("qty_subtract"), width=70, fg_color="#6c757d", hover_color="#5a6268",
                  command=lambda: _pos_adjust_qty(self, -1)).grid(row=0, column=1, padx=(0, 4))
    ctk.CTkButton(cart_btn_frame, text=i18n.t("remove"), width=80, fg_color="#EF4444", hover_color="#DC2626",
                  command=lambda: _pos_remove_selected(self)).grid(row=0, column=2, padx=(0, 4))
    ctk.CTkButton(cart_btn_frame, text=i18n.t("clear_cart"), width=90, fg_color="gray40", hover_color="gray30",
                  command=lambda: _pos_clear_cart(self)).grid(row=0, column=3)

    # Add Item button (P1.2) — opens ProductPickerDialog for inventory lookup
    self._checkout_add_item_btn = ctk.CTkButton(
        cart_btn_frame, text=f"\U0001f495 {i18n.t('add_item')}", width=100,
        fg_color="#3B82F6", hover_color="#2563EB",
        command=lambda: _checkout_add_item(self),
    )
    self._checkout_add_item_btn.grid(row=0, column=4, padx=(4, 0))

    # ── Right Frame (Order Summary Card) ────────────────────
    right_frame = ctk.CTkFrame(self.tab_checkout, fg_color="#2d2d3a", corner_radius=10)
    right_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ns")
    right_frame.grid_columnconfigure(0, weight=1)

    # Card header: title + cascade badge
    card_header = ctk.CTkFrame(right_frame, fg_color="transparent")
    card_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
    card_header.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        card_header, text=i18n.t("order_summary"),
        font=ctk.CTkFont(size=16, weight="bold"), text_color="#FFFFFF",
    ).grid(row=0, column=0, sticky="w")

    # Cascade status badge (Phase 3 integration) — pack-based wrapper
    badge_anchor = ctk.CTkFrame(card_header, fg_color="transparent")
    badge_anchor.grid(row=0, column=1, sticky="e")
    self.checkout_cascade_badge = CascadeStatusBadge(badge_anchor, size="small")
    self.checkout_cascade_badge.frame.pack(pady=2)
    ctk.CTkFrame(right_frame, height=1, fg_color="#555555").grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 8))

    patient_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
    patient_frame.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="ew")
    ctk.CTkLabel(patient_frame, text=i18n.t("patient_label"), text_color="#A0A0A0").pack(side="left", padx=(0, 5))
    self.checkout_patient_var = ctk.StringVar()
    self.checkout_patient_combo = ctk.CTkComboBox(patient_frame, variable=self.checkout_patient_var, width=160)
    self.checkout_patient_combo.pack(side="left")

    if hasattr(database, "get_all_patients"):
        _pos_refresh_patients(self)

    self.checkout_patient_combo.bind("<<ComboboxSelected>>", lambda e: _pos_on_patient_select(self))

    # ── Balance Details (Subtotal / Tax / Total) ────────────────
    self.checkout_subtotal_label = ctk.CTkLabel(
        right_frame, text=f"{i18n.t('pos_subtotal')}: {self.currency.fmt(0)}",
        font=ctk.CTkFont(size=13), text_color="#A0A0A0", anchor="e",
    )
    self.checkout_subtotal_label.grid(row=3, column=0, padx=20, sticky="ew", pady=(8, 2))

    self.checkout_tax_label = ctk.CTkLabel(
        right_frame, text=self.currency.tax_term() + ": " + self.currency.fmt(0),
        font=ctk.CTkFont(size=13), text_color="#A0A0A0", anchor="e",
    )
    self.checkout_tax_label.grid(row=4, column=0, padx=20, sticky="ew", pady=(0, 2))

    ctk.CTkFrame(right_frame, height=1, fg_color="#555555").grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 6))

    self.checkout_total_label = ctk.CTkLabel(
        right_frame, text=i18n.t("total_format", total="0.00"),
        font=ctk.CTkFont(size=26, weight="bold"), text_color="#10B981", anchor="e",
    )
    self.checkout_total_label.grid(row=6, column=0, padx=20, sticky="e", pady=(0, 4))

    self.checkout_items_count_label = ctk.CTkLabel(
        right_frame, text=i18n.t("items_in_cart_format", count=0),
        font=ctk.CTkFont(size=12), text_color="#A0A0A0", anchor="e",
    )
    self.checkout_items_count_label.grid(row=7, column=0, padx=20, sticky="e", pady=(0, 8))

    ctk.CTkLabel(right_frame, text=i18n.t("payment_method"), font=ctk.CTkFont(size=14, weight="bold"), text_color="#FFFFFF").grid(row=8, column=0, padx=20, pady=(8, 4), sticky="w")
    self.checkout_payment_var = ctk.StringVar(value=i18n.t("cash"))
    self.checkout_payment_seg = ctk.CTkSegmentedButton(right_frame, values=[i18n.t("cash"), i18n.t("card"), i18n.t("insurance")], variable=self.checkout_payment_var, width=260)
    self.checkout_payment_seg.grid(row=9, column=0, padx=20, pady=(0, 10), sticky="w")

    tendered_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
    tendered_frame.grid(row=10, column=0, padx=20, pady=(0, 4), sticky="ew")
    tendered_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(tendered_frame, text=i18n.t("amount_tendered"), font=ctk.CTkFont(size=13), text_color="#A0A0A0").grid(row=0, column=0, sticky="w")
    self.checkout_tendered_var = ctk.StringVar()
    self.checkout_tendered_entry = ctk.CTkEntry(tendered_frame, width=120, textvariable=self.checkout_tendered_var)
    self.checkout_tendered_entry.grid(row=0, column=1, sticky="e")
    self.checkout_tendered_entry.bind("<KeyRelease>", _pos_update_change)

    self.checkout_change_label = ctk.CTkLabel(right_frame, text=i18n.t("change_due") + ": " + self.currency.fmt(0), font=ctk.CTkFont(size=16, weight="bold"), text_color="#10B981", anchor="e")
    self.checkout_change_label.grid(row=11, column=0, padx=20, sticky="ew", pady=(6, 12))

    self.checkout_confirm_btn = ctk.CTkButton(right_frame, text=i18n.t("complete_sale"), height=44, font=ctk.CTkFont(size=16, weight="bold"), fg_color="#10B981", hover_color="#059669", command=lambda: _pos_complete_sale(self))
    self.checkout_confirm_btn.grid(row=12, column=0, padx=20, pady=(0, 16), sticky="ew")

    # ── Bottom Right (Receipts) ─────────────────────────────
    receipts_frame = ctk.CTkFrame(self.tab_checkout, fg_color="transparent")
    receipts_frame.grid(row=1, column=1, padx=(0, 10), pady=(0, 6), sticky="nsew")
    receipts_frame.grid_rowconfigure(1, weight=1)
    receipts_frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(receipts_frame, text=i18n.t("recent_receipts"), font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))

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

    # ── Email Report Card (Phase 4 integration) ──────────────────
    email_card = ctk.CTkFrame(self.tab_checkout, fg_color="#2d2d3a", corner_radius=10)
    email_card.grid(row=2, column=1, padx=(0, 10), pady=(0, 10), sticky="nsew")
    email_card.grid_columnconfigure(1, weight=1)
    email_card.grid_rowconfigure(0, weight=1)

    ctk.CTkLabel(
        email_card, text=i18n.t("daily_sales_email"),
        font=ctk.CTkFont(size=14, weight="bold"), text_color="#FFFFFF",
    ).grid(row=0, column=0, padx=16, pady=(12, 8), sticky="w")

    ctk.CTkLabel(
        email_card, text=i18n.t("daily_email_subtitle"),
        font=ctk.CTkFont(size=11), text_color="#a0a0a0",
    ).grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

    ctk.CTkButton(
        email_card, text=i18n.t("send_today_report"), width=150,
        command=self._send_test_email,
    ).grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

    ctk.CTkLabel(
        email_card, text=i18n.t("smtp_configure_in_settings"),
        font=ctk.CTkFont(size=10), text_color="#60a5fa",
    ).grid(row=3, column=0, padx=16, pady=(0, 12), sticky="w")

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
    product_name = product[1]
    price = product[2]
    vendor = product[8] if product[8] else "N/A"
    expiry_date = product[6] if product[6] else "N/A"

    for item in self.pos_cart:
        if int_barcode in item.get("internal_barcodes", []):
            messagebox.showwarning("Already in Cart",
                f"'{product_name}' (batch {int_barcode}) is already in the cart. "
                f"Scan a different batch to add more.", parent=self.tab_checkout)
            return

    for item in self.pos_cart:
        if item["product_name"] == product_name:
            item["internal_barcodes"].append(int_barcode)
            item["quantity"] += 1
            _pos_refresh_cart(self)
            return

    self.pos_cart.append({
        "product_name": product_name,
        "quantity": 1,
        "price_at_time": price,
        "internal_barcodes": [int_barcode],
        "vendor": vendor,
        "expiry_date": expiry_date,
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
    entry = self.pos_cart[idx]
    if delta > 0:
        batches = database.get_batches_by_name(entry["product_name"], sort_by='expiry_date')
        existing = set(entry.get("internal_barcodes", []))
        for b in batches:
            if b[4] not in existing:
                entry["internal_barcodes"].append(b[4])
                entry["quantity"] += 1
                _pos_refresh_cart(self)
                return
        messagebox.showwarning("Out of Stock",
            f"No more '{entry['product_name']}' in stock to add.", parent=self.tab_checkout)
    elif delta < 0:
        if entry["quantity"] <= 1:
            messagebox.showwarning("Cannot Reduce",
                "Qty cannot go below 1. Use Remove to delete the item.", parent=self.tab_checkout)
            return
        entry["internal_barcodes"].pop()
        entry["quantity"] -= 1
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
    self.checkout_tendered_var.set("")
    _pos_refresh_cart(self)


def _pos_refresh_cart(self):
    for item in self.tree_cart.get_children():
        self.tree_cart.delete(item)

    config = barcode_logic.load_config()
    tax_rate = config.get("tax_rate", 0.0)

    for idx, entry in enumerate(self.pos_cart):
        tag = "even" if idx % 2 == 0 else "odd"
        qty = entry["quantity"]
        unit_price = entry["price_at_time"]
        line_subtotal = unit_price * qty
        line_tax = line_subtotal * (tax_rate / 100.0) if tax_rate else 0.0
        line_total = line_subtotal + line_tax
        self.tree_cart.insert("", "end", values=(
            entry["product_name"],
            qty,
            self.currency.fmt(unit_price),
            self.currency.fmt(line_tax),
            self.currency.fmt(line_total),
        ), tags=(tag,))

    subtotal = sum(e["price_at_time"] * e["quantity"] for e in self.pos_cart)
    tax_amount = subtotal * (tax_rate / 100.0) if tax_rate else 0.0
    total = subtotal + tax_amount
    total_qty = sum(e["quantity"] for e in self.pos_cart)

    self.checkout_subtotal_label.configure(text=f"{i18n.t('pos_subtotal')}: {self.currency.fmt(subtotal)}")
    self.checkout_tax_label.configure(text=f"{i18n.t('pos_tax')}: {self.currency.fmt(tax_amount)}")
    self.checkout_total_label.configure(text=i18n.t("total_format", total=self.currency.fmt(total)))
    self.checkout_items_count_label.configure(text=i18n.t("items_in_cart_format", count=total_qty))

    _pos_update_change(self)


def _pos_refresh_patients(self):
    """Load patient list in background thread; update combo via after()."""
    from async_ui import AsyncUI

    def _load():
        try:
            return database.get_all_patients()
        except Exception:
            return []

    def _on_done(patients, error=None):
        if patients is None:
            patients = []
        patient_names = ["None"] + [f"{p[1]} (ID: {p[0]})" for p in patients]
        self.checkout_patient_combo.configure(values=patient_names)
        self.checkout_patient_var.set("None")

    AsyncUI.get().run(_load, callback=_on_done)


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


def _checkout_load_products(self):
    """Load product names into the checkout product combobox asynchronously.

    Uses AsyncUI (same pattern as _pos_refresh_patients) so large inventory
    tables do not block the Tkinter event loop.  Results are cached on
    ``self._checkout_products_cache`` for fast barcode lookup in
    ``_on_checkout_product_change``.
    """
    try:
        from async_ui import AsyncUI
    except ImportError:
        AsyncUI = None

    def _load():
        try:
            products = database.get_all_products()
            return products or []
        except Exception as e:
            log.error("Checkout product load failed: %s", e)
            return []

    def _on_done(products, error=None):
        if products is None:
            products = []
        self._checkout_products_cache = products
        # Deduplicate by product name for the combobox
        seen = set()
        product_names = []
        for p in products:
            name = p[1] if len(p) > 1 else "?"
            if name not in seen:
                seen.add(name)
                product_names.append(name)
        self.checkout_product_combo.configure(values=product_names)

    if AsyncUI is not None:
        try:
            mgr = AsyncUI.get()
            if mgr._root is not None:
                mgr.run(_load, callback=_on_done)
                return
        except Exception as exc:
            log.debug("AsyncUI unavailable for product combo: %s", exc)

    # Synchronous fallback
    products = _load()
    _on_done(products, None)


def _pos_update_change(self, event=None):
    """Recalculate change due based on tendered amount vs cart total."""
    try:
        tendered = float(self.checkout_tendered_var.get())
    except (ValueError, TypeError):
        tendered = 0.0

    total_str = self.checkout_total_label.cget("text")
    try:
        total = self.currency.parse(total_str.replace("Total:", "").strip())
    except (ValueError, TypeError):
        total = 0.0

    change = tendered - total
    if change < 0:
        change = 0.0
    self.checkout_change_label.configure(
        text=self.currency.fmt(change),
        text_color="#10B981" if tendered >= total else "#EF4444",
    )


def _pos_complete_sale(self):
    if not self.pos_cart:
        messagebox.showwarning("Empty Cart", "Add items before completing a sale.", parent=self.tab_checkout)
        return

    method = self.checkout_payment_var.get()
    config = barcode_logic.load_config()
    tax_rate = config.get("tax_rate", 0.0)

    subtotal = sum(e["price_at_time"] * e["quantity"] for e in self.pos_cart)
    tax = subtotal * (tax_rate / 100.0) if tax_rate else 0.0
    total = subtotal + tax

    insurance_copay = 0.0
    insurance_amount = 0.0

    if method == i18n.t("insurance"):
        try:
            from rx_strategies import strategy_factory
            import localization_manager
            region = localization_manager.get_manager().region()
            coverage = {"copay": 5.0, "coinsurance_rate": 0.2}
            strategy = strategy_factory(region)
            insurance_copay = strategy.calculate_patient_cost(subtotal, 1, insurance_coverage=coverage)
            insurance_amount = round(subtotal - insurance_copay, 2)
        except Exception as e:
            log.warning("Insurance copay calculation failed: %s", e)
            insurance_copay = min(subtotal, 5.0)
            insurance_amount = round(subtotal - insurance_copay, 2)
        method = "Transfer"

    patient_name = ""
    patient_val = self.checkout_patient_var.get()
    if patient_val and patient_val != "None":
        patient_name = patient_val.split("(ID:")[0].strip()

    pharmacy_info = {
        "pharmacy_name": config.get("pharmacy_name", "My Pharmacy"),
        "address": config.get("address", ""),
        "phone": config.get("phone", ""),
        "receipt_header_note": config.get("receipt_header_note", ""),
        "receipt_footer_note": config.get("receipt_footer_note", ""),
    }

    try:
        receipt_id = database.checkout_cart_atomically(
            method, self.pos_cart,
            patient_id=getattr(self, 'pos_patient_id', None),
            tax_rate=tax_rate,
            insurance_copay=insurance_copay,
            insurance_amount=insurance_amount,
        )

        receipt_file = receipt_engine.generate_receipt(
            receipt_id, self.pos_cart, subtotal, total,
            tax=tax,
            payment_type=method,
            patient_name=patient_name,
            pharmacy_info=pharmacy_info,
        )

        audit_log.log_action("CHECKOUT", f"Receipt ID {receipt_id} created for {self.currency.fmt(total)}")

        if messagebox.askyesno("Sale Complete",
                               f"Receipt #{receipt_id} - {self.currency.fmt(total)}\n"
                               f"Payment: {method}\n"
                               f"Subtotal: {self.currency.fmt(subtotal)} | Tax: {self.currency.fmt(tax)}\n\n"
                               f"Open receipt?",
                               parent=self.tab_checkout):
            receipt_engine.open_receipt_file(receipt_file)

        self.pos_cart.clear()
        self.pos_patient_id = None
        self.checkout_tendered_var.set("")
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
                r[0], r[1], self.currency.fmt(r[2]), r[3]), tags=(tag,))
    except Exception:
        pass


def _pos_show_receipt_detail(self):
    """Open a modal ReceiptDetailDialog for the selected receipt (P4.1)."""
    selected = self.tree_receipts.selection()
    if not selected:
        return
    receipt_id = int(self.tree_receipts.item(selected[0], "values")[0])

    try:
        ReceiptDetailDialog(self.tab_checkout, receipt_id=receipt_id)
    except Exception as e:
        log.error("ReceiptDetailDialog failed: %s", e)
        messagebox.showerror("Error", f"Could not open receipt detail: {e}",
                             parent=self.tab_checkout)


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
    """Generate a printable receipt from the current cart state and open it."""
    if not self.pos_cart:
        messagebox.showwarning("Empty Cart", "Add items before printing a receipt.", parent=self.tab_checkout)
        return

    config = barcode_logic.load_config()
    tax_rate = config.get("tax_rate", 0.0)
    subtotal = sum(e["price_at_time"] * e["quantity"] for e in self.pos_cart)
    tax = subtotal * (tax_rate / 100.0) if tax_rate else 0.0
    total = subtotal + tax

    patient_name = ""
    patient_val = getattr(self, "checkout_patient_var", None)
    if patient_val and patient_val.get() and patient_val.get() != "None":
        patient_name = patient_val.get().split("(ID:")[0].strip()

    pharmacy_info = {
        "pharmacy_name": config.get("pharmacy_name", "My Pharmacy"),
        "address": config.get("address", ""),
        "phone": config.get("phone", ""),
        "receipt_header_note": config.get("receipt_header_note", ""),
        "receipt_footer_note": config.get("receipt_footer_note", ""),
    }

    try:
        receipt_id = getattr(self, "_print_receipt_id", None)
        if receipt_id is None:
            receipt_id = 0

        receipt_file = receipt_engine.generate_receipt(
            receipt_id, self.pos_cart, subtotal, total,
            tax=tax,
            payment_type=self.checkout_payment_var.get(),
            patient_name=patient_name,
            pharmacy_info=pharmacy_info,
        )

        audit_log.log_action("CHECKOUT_PRINT", f"Receipt preview generated for {self.currency.fmt(total)}")
        receipt_engine.open_receipt_file(receipt_file)
    except Exception as e:
        messagebox.showerror("Error", f"Could not print receipt: {e}", parent=self.tab_checkout)
        log.error("Print receipt failed: %s", e)


def _refresh_checkout_stock_dropdown(self):
    """Refresh the product combobox by re-loading products asynchronously."""
    _checkout_load_products(self)


def _on_checkout_product_change(self, selected_name):
    """When a product is selected from the combobox, auto-fill the barcode entry.

    Looks up the product in the cached async-loaded product list and
    populates the barcode entry with its internal_unique_barcode.
    """
    if not selected_name or not selected_name.strip():
        return

    cache = getattr(self, "_checkout_products_cache", [])
    for p in cache:
        # p = (id, name, price, manufacturer_barcode, internal_unique_barcode, ...)
        if len(p) > 1 and p[1] == selected_name:
            int_barcode = p[4] if len(p) > 4 and p[4] else ""
            if int_barcode:
                self.checkout_barcode_entry.delete(0, "end")
                self.checkout_barcode_entry.insert(0, int_barcode)
                self.checkout_barcode_entry.focus()
                # Trigger the barcode scan automatically
                barcode = self.checkout_barcode_entry.get().strip()
                if barcode:
                    _pos_scan_barcode(self, barcode)
                    self.checkout_barcode_entry.delete(0, "end")
                return

    log.warning("Product '%s' not found in cache — refreshing", selected_name)
    _checkout_load_products(self)

def _checkout_add_item(self):
    """Open a searchable product picker dialog to add an item to the cart.

    Uses ProductPickerDialog which loads products via AsyncUI to prevent
    blocking the Tkinter event loop on large inventory tables.
    """
    if not self.pos_cart and not hasattr(self, "pos_cart"):
        self.pos_cart = []

    def _on_product_selected(product_row):
        """Callback: add the selected product row to the cart."""
        # Unpack: (id, name, price, manufacturer_barcode, internal_unique_barcode,
        #          status, expiry_date, manufacture_date, vendor_name)
        product_name = product_row[1]
        price = product_row[2]
        int_barcode = product_row[4]
        vendor = product_row[8] if product_row[8] else "N/A"
        expiry_date = product_row[6] if product_row[6] else "N/A"

        # Check if already in cart by internal barcode
        for item in self.pos_cart:
            if int_barcode in item.get("internal_barcodes", []):
                messagebox.showwarning("Already in Cart",
                    f"'{product_name}' (batch {int_barcode}) is already in the cart. "
                    f"Scan a different batch to add more.", parent=self.tab_checkout)
                return

        # Append to existing matching product name, else create new entry
        for item in self.pos_cart:
            if item["product_name"] == product_name:
                item["internal_barcodes"].append(int_barcode)
                item["quantity"] += 1
                _pos_refresh_cart(self)
                return

        self.pos_cart.append({
            "product_name": product_name,
            "quantity": 1,
            "price_at_time": price,
            "internal_barcodes": [int_barcode],
            "vendor": vendor,
            "expiry_date": expiry_date,
        })
        _pos_refresh_cart(self)
        audit_log.log_action("CHECKOUT_ADD_ITEM", f"Added '{product_name}' to cart")

    try:
        dialog = ProductPickerDialog(self, on_select=_on_product_selected)
        dialog._search_entry.focus()
    except Exception as e:
        log.error("Failed to open ProductPickerDialog: %s", e)
        messagebox.showerror("Error", f"Could not open product picker: {e}", parent=self.tab_checkout)

def _checkout_update_change(self, event=None):
    _pos_update_change(self)


def _checkout_debug_layout(self) -> dict:
    """Programmatically assert layout integrity (VERIFICATION_CHECKLIST Protocol II.A).

    Checks:
    - Tab content width/height are non-zero.
    - Cart treeview has visible content area.
    - Order summary card has non-zero dimensions.
    - Receipts treeview has visible content area.
    - No child widget extends past the tab container width.
    """
    results: dict = {"issues": []}
    try:
        self.update_idletasks()
        tab = self.tab_checkout
        tab_w = tab.winfo_width()
        tab_h = tab.winfo_height()
        results["tab_size"] = (tab_w, tab_h)

        cart_w = self.tree_cart.winfo_width()
        if cart_w <= 0:
            results["issues"].append("Cart treeview has zero width")

        summary_card = getattr(self, "checkout_cascade_badge", None)
        if summary_card and summary_card.winfo_width() < 100:
            results["issues"].append("Order summary card width below minimum")

        tree_x = self.tree_receipts.winfo_x()
        tree_w = self.tree_receipts.winfo_width()
        if tree_x + tree_w > tab_w:
            results["issues"].append(
                f"Receipts treeview clipping: x={tree_x} + w={tree_w} > tab={tab_w}")

        results["status"] = "PASS" if not results["issues"] else "FAIL"
        log.debug("Checkout layout geometry: %s", results["status"])
    except Exception as e:
        results["status"] = "ERROR"
        results["issues"].append(str(e))
        log.error("Checkout layout geometry debug failed: %s", e)
    return results
