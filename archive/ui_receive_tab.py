import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date
from collections import defaultdict
import os

import database
import barcode_logic


def setup_receive_tab(self):
    LEFT_PANEL_WIDTH = 420

    self._recv_left_container = ctk.CTkFrame(self.tab_receive, width=LEFT_PANEL_WIDTH,
                                              fg_color="transparent")
    self._recv_left_container.pack(side="left", fill="y", padx=10, pady=10)
    self._recv_left_container.pack_propagate(False)

    try:
        import customtkinter.windows.widgets.appearance_mode as _am
        _bg = _am.AppearanceModeTracker.appearance_mode
        _canvas_bg = "#2b2b2b" if _bg == "dark" else "#f0f0f0"
    except Exception:
        _canvas_bg = "#2b2b2b"

    self._recv_canvas = tk.Canvas(self._recv_left_container, width=LEFT_PANEL_WIDTH,
                                  highlightthickness=0, bd=0, bg=_canvas_bg,
                                  takefocus=False)
    self._recv_scrollbar = tk.Scrollbar(self._recv_left_container, orient="vertical",
                                        command=self._recv_canvas.yview)
    self._recv_canvas.configure(yscrollcommand=self._recv_scrollbar.set)
    self._recv_scrollbar.pack(side="right", fill="y")
    self._recv_canvas.pack(side="left", fill="both", expand=True)

    self.recv_left_frame = ctk.CTkFrame(self._recv_canvas, fg_color="transparent")
    self._recv_canvas_window = self._recv_canvas.create_window(
        (0, 0), window=self.recv_left_frame, anchor="nw"
    )

    def _on_inner_configure(event):
        self._recv_canvas.configure(
            scrollregion=self._recv_canvas.bbox("all")
        )
    self.recv_left_frame.bind("<Configure>", _on_inner_configure)

    def _on_canvas_configure(event):
        self._recv_canvas.itemconfig(self._recv_canvas_window, width=event.width)
    self._recv_canvas.bind("<Configure>", _on_canvas_configure)

    def _on_mousewheel(event):
        self._recv_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    self._recv_canvas.bind("<Enter>", lambda e: self._recv_canvas.bind("<MouseWheel>", _on_mousewheel))
    self._recv_canvas.bind("<Leave>", lambda e: self._recv_canvas.unbind("<MouseWheel>"))

    self._recv_canvas.bind("<Button-1>", lambda e: self.recv_left_frame.focus_set())

    header_row = ctk.CTkFrame(self.recv_left_frame, fg_color="transparent")
    header_row.pack(fill="x", padx=10, pady=(14, 6))

    ctk.CTkFrame(header_row, width=4, fg_color="#2563EB",
                 corner_radius=2).pack(side="left", fill="y", padx=(0, 10))
    ctk.CTkLabel(header_row, text="Add to Purchase Order",
                 font=ctk.CTkFont(size=17, weight="bold"),
                 anchor="w").pack(side="left", fill="x", expand=True)

    s1_card = ctk.CTkFrame(self.recv_left_frame, fg_color="#2a2a3e",
                           corner_radius=10)
    s1_card.pack(fill="x", padx=10, pady=(0, 8))

    s1_hdr = ctk.CTkFrame(s1_card, fg_color="transparent")
    s1_hdr.pack(fill="x", padx=12, pady=(10, 6))
    ctk.CTkFrame(s1_hdr, width=3, fg_color="#3d5a80",
                 corner_radius=1).pack(side="left", fill="y", padx=(0, 8))
    ctk.CTkLabel(s1_hdr, text="SHIPMENT DETAILS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#8899aa", anchor="w").pack(side="left")

    s1_grid = ctk.CTkFrame(s1_card, fg_color="transparent")
    s1_grid.pack(fill="x", padx=12, pady=(0, 12))
    s1_grid.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(s1_grid, text="Vendor Name", anchor="w",
                 width=110).grid(row=0, column=0, padx=(0, 8), pady=5, sticky="w")
    self.vendor_entry = ctk.CTkEntry(s1_grid, state="normal",
                                     placeholder_text="e.g. MedSupply Co.")
    self.vendor_entry.grid(row=0, column=1, columnspan=2, pady=5, sticky="ew")
    self.vendor_entry.bind("<KeyRelease>", self._on_vendor_change)
    self.vendor_entry.bind("<FocusOut>", self._on_vendor_change)

    ctk.CTkLabel(s1_grid, text="Product", anchor="w",
                 width=110).grid(row=1, column=0, padx=(0, 8), pady=5, sticky="w")
    self.recv_product_var = ctk.StringVar(value="")
    self.recv_product_combo = ctk.CTkComboBox(
        s1_grid, state="normal",
        variable=self.recv_product_var,
        values=[], command=self._on_product_change)
    self.recv_product_combo.grid(row=1, column=1, pady=5, sticky="ew")
    ctk.CTkButton(s1_grid, text="\u21bb", width=32, height=28,
                  fg_color="#374151", hover_color="#4B5563",
                  font=ctk.CTkFont(size=14),
                  command=self.refresh_product_list).grid(
        row=1, column=2, padx=(6, 0), pady=5)

    ctk.CTkLabel(s1_grid, text="Date Received", anchor="w",
                 width=110).grid(row=2, column=0, padx=(0, 8), pady=5, sticky="w")
    self.recv_date_entry = ctk.CTkEntry(s1_grid, state="normal",
                                        placeholder_text="YYYY-MM-DD")
    self.recv_date_entry.grid(row=2, column=1, columnspan=2, pady=5, sticky="ew")
    self.recv_date_entry.insert(0, date.today().strftime("%Y-%m-%d"))

    ctk.CTkLabel(s1_grid, text="Quantity", anchor="w",
                 width=110).grid(row=3, column=0, padx=(0, 8), pady=5, sticky="w")
    self.recv_qty_entry = ctk.CTkEntry(s1_grid, state="normal",
                                       placeholder_text="e.g. 50")
    self.recv_qty_entry.grid(row=3, column=1, columnspan=2, pady=5, sticky="ew")

    ctk.CTkLabel(s1_grid, text="Total Cost ($)", anchor="w",
                 width=110).grid(row=4, column=0, padx=(0, 8), pady=5, sticky="w")
    self.recv_cost_entry = ctk.CTkEntry(s1_grid, state="normal",
                                        placeholder_text="e.g. 250.00")
    self.recv_cost_entry.grid(row=4, column=1, columnspan=2, pady=5, sticky="ew")

    s2_card = ctk.CTkFrame(self.recv_left_frame, fg_color="#252535",
                           corner_radius=10)
    s2_card.pack(fill="x", padx=10, pady=(0, 8))

    s2_hdr = ctk.CTkFrame(s2_card, fg_color="transparent")
    s2_hdr.pack(fill="x", padx=12, pady=(10, 6))
    ctk.CTkFrame(s2_hdr, width=3, fg_color="#6366f1",
                 corner_radius=1).pack(side="left", fill="y", padx=(0, 8))
    ctk.CTkLabel(s2_hdr, text="AUTO-FILL  \u00b7  READ-ONLY",
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

    s3_card = ctk.CTkFrame(self.recv_left_frame, fg_color="transparent")
    s3_card.pack(fill="x", padx=10, pady=(0, 12))

    ctk.CTkButton(s3_card, text="\uff0b  Add to Queue",
                  fg_color="#2563EB", hover_color="#1d4ed8",
                  font=ctk.CTkFont(size=14, weight="bold"),
                  height=42, corner_radius=8,
                  command=self._add_to_queue).pack(fill="x")

    status_container = ctk.CTkFrame(s3_card, fg_color="transparent", height=36)
    status_container.pack(fill="x", pady=(6, 0))
    status_container.pack_propagate(False)

    self.recv_status_label = ctk.CTkLabel(
        status_container, text="",
        font=ctk.CTkFont(size=12), text_color="#22c55e",
        wraplength=360, anchor="center", justify="center")
    self.recv_status_label.pack(fill="both", expand=True)

    self.recv_right_frame = ctk.CTkFrame(self.tab_receive)
    self.recv_right_frame.pack(side="right", fill="both", expand=True, padx=(0, 10), pady=10)
    self.recv_right_frame.grid_rowconfigure(1, weight=1)
    self.recv_right_frame.grid_columnconfigure(0, weight=1)

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

    # ── AI Document Extractor ────────────────────────────────────────
    ai_frame = ctk.CTkFrame(self.recv_right_frame, fg_color="#1a1a2e", corner_radius=10)
    ai_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10), padx=15, sticky="ew")
    ai_frame.grid_columnconfigure(1, weight=1)

    ai_hdr = ctk.CTkFrame(ai_frame, fg_color="transparent")
    ai_hdr.pack(fill="x", padx=12, pady=(10, 4))
    ctk.CTkFrame(ai_hdr, width=3, fg_color="#8b5cf6",
                 corner_radius=1).pack(side="left", fill="y", padx=(0, 8))
    ctk.CTkLabel(ai_hdr, text="AI DOCUMENT PARSER",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#a78bfa", anchor="w").pack(side="left")

    ai_btn_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
    ai_btn_row.pack(fill="x", padx=12, pady=(0, 10))

    self._ai_extract_btn = ctk.CTkButton(
        ai_btn_row, text="Process Supplier Invoice (AI)", width=220, height=36,
        fg_color="#7c3aed", hover_color="#6d28d9",
        font=ctk.CTkFont(size=13, weight="bold"),
        command=self._run_ai_extract,
    )
    self._ai_extract_btn.pack(side="left", padx=(0, 10))

    self._smart_extract_btn = ctk.CTkButton(
        ai_btn_row, text="Smart Parse (Offline)", width=180, height=36,
        fg_color="#059669", hover_color="#047857",
        font=ctk.CTkFont(size=13, weight="bold"),
        command=self._run_smart_parse,
    )
    self._smart_extract_btn.pack(side="left", padx=(0, 10))

    self._ai_status_label = ctk.CTkLabel(ai_btn_row, text="",
                                          font=ctk.CTkFont(size=11),
                                          text_color="#a78bfa")
    self._ai_status_label.pack(side="left")

    # Review table for AI-extracted items
    review_columns = ("product_name", "active_ingredient", "dosage",
                      "qty", "batch", "expiry")
    self._ai_review_tree = ttk.Treeview(
        ai_frame, columns=review_columns, show="headings", height=5
    )
    self._ai_review_tree.heading("product_name", text="Product Name")
    self._ai_review_tree.heading("active_ingredient", text="Active Ingredient")
    self._ai_review_tree.heading("dosage", text="Dosage/Concentration")
    self._ai_review_tree.heading("qty", text="Qty")
    self._ai_review_tree.heading("batch", text="Batch #")
    self._ai_review_tree.heading("expiry", text="Expiry")
    self._ai_review_tree.column("product_name", width=180)
    self._ai_review_tree.column("active_ingredient", width=130)
    self._ai_review_tree.column("dosage", width=120)
    self._ai_review_tree.column("qty", width=50, anchor="center")
    self._ai_review_tree.column("batch", width=100)
    self._ai_review_tree.column("expiry", width=90, anchor="center")
    self._ai_review_tree.pack(fill="x", padx=12, pady=(0, 6))

    ai_action_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
    ai_action_row.pack(fill="x", padx=12, pady=(0, 10))

    ctk.CTkButton(ai_action_row, text="Add Selected to Queue", width=160,
                  fg_color="#10b981", hover_color="#059669",
                  command=self._ai_add_selected_to_queue).pack(side="left", padx=(0, 6))
    ctk.CTkButton(ai_action_row, text="Add All to Queue", width=140,
                  fg_color="#3b82f6", hover_color="#2563eb",
                  command=self._ai_add_all_to_queue).pack(side="left", padx=(0, 6))
    ctk.CTkButton(ai_action_row, text="Clear", width=70,
                  fg_color="#6c757d", hover_color="#5a6268",
                  command=self._ai_clear_review).pack(side="left")

    self._ai_extracted_items: list[dict] = []

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
            self.tree_history.heading(col, text="Date \u25bc",
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

    self.recv_right_frame.grid_rowconfigure(5, weight=1)


def _on_vendor_change(self, event=None):
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

    from ui_modals import BulkLabelPrintDialog
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
    if not hasattr(self, "tree_history"):
        return
    for item in self.tree_history.get_children():
        self.tree_history.delete(item)

    vendor_groups = defaultdict(list)
    for row in database.get_all_receiving_log(filter_date=filter_date):
        vendor_groups[row[1]].append(row)

    suffix = f" \u2014 {filter_date}" if filter_date else ""
    for vendor_name, rows in sorted(vendor_groups.items()):
        total_units = sum(r[4] for r in rows)
        vendor_iid = self.tree_history.insert(
            "", "end", text=f"{vendor_name} ({total_units} units{suffix})", open=True)
        for row in rows:
            self.tree_history.insert(vendor_iid, "end", values=(
                row[2], row[3], row[4], f"${row[5]:.2f}", row[6]
            ))


def _filter_history_by_date(self):
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
    self.hist_date_entry.delete(0, "end")
    self._load_shipment_history()


def _sort_history_by_date(self):
    for parent_iid in self.tree_history.get_children(""):
        children = list(self.tree_history.get_children(parent_iid))
        children.sort(
            key=lambda c: self.tree_history.item(c, "values")[1],
            reverse=not self._history_sort_asc
        )
        for idx, child in enumerate(children):
            self.tree_history.move(child, parent_iid, idx)
    self._history_sort_asc = not self._history_sort_asc
    arrow = "\u25b2" if self._history_sort_asc else "\u25bc"
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


# ── AI Document Extractor Methods ──────────────────────────────────────

def _run_ai_extract(self):
    """Open file dialog and run AI extraction on selected document."""
    from tkinter import filedialog
    from auto_extract import extract_from_file, check_ollama_status

    status = check_ollama_status()
    if not status["running"]:
        messagebox.showerror(
            "Ollama Not Running",
            f"Cannot connect to Ollama at localhost:11434\n\n{status['error'] or 'Start Ollama and try again.'}"
        )
        return

    file_path = filedialog.askopenfilename(
        title="Select Supplier Invoice / Delivery Note",
        filetypes=[
            ("Text files", "*.txt"),
            ("PDF files", "*.pdf"),
            ("All files", "*.*"),
        ],
    )
    if not file_path:
        return

    self._ai_extract_btn.configure(state="disabled", text="Processing...")
    self._ai_status_label.configure(text="Sending document to AI model...")
    self._ai_clear_review()

    def on_result(items: list[dict]):
        self.after(0, lambda: self._ai_populate_review(items))

    def on_error(exc: Exception):
        self.after(0, lambda: self._ai_handle_error(exc))

    extract_from_file(file_path, on_result=on_result, on_error=on_error)


def _ai_populate_review(self, items: list[dict]):
    """Fill the review treeview with AI-extracted items."""
    self._ai_extracted_items = items
    self._ai_review_tree.delete(*self._ai_review_tree.get_children())

    for item in items:
        self._ai_review_tree.insert("", "end", values=(
            item.get("product_name", ""),
            item.get("active_ingredient", ""),
            item.get("dosage_concentration", ""),
            item.get("quantity_received", ""),
            item.get("batch_number", ""),
            item.get("expiration_date", ""),
        ))

    self._ai_extract_btn.configure(state="normal", text="Process Supplier Invoice (AI)")
    self._ai_status_label.configure(text=f"Extracted {len(items)} item(s) — review and add to queue.")


def _ai_handle_error(self, exc: Exception):
    """Handle AI extraction failure."""
    self._ai_extract_btn.configure(state="normal", text="Process Supplier Invoice (AI)")
    self._ai_status_label.configure(text=f"Error: {exc}")
    messagebox.showerror("AI Extraction Failed", str(exc))


def _ai_add_selected_to_queue(self):
    """Add selected AI-extracted items to the purchase order queue."""
    selected = self._ai_review_tree.selection()
    if not selected:
        messagebox.showwarning("No Selection", "Select items from the review table first.")
        return
    vendor = self.vendor_entry.get().strip()
    if not vendor:
        messagebox.showwarning("Missing Vendor", "Enter a vendor name before adding items.")
        return

    if vendor not in self.receiving_session:
        self.receiving_session[vendor] = {
            "total_quantity": 0,
            "vendor_asking_price": 0.0,
            "items": [],
        }

    recv_date = date.today().strftime("%Y-%m-%d")
    added = 0

    for iid in selected:
        vals = self._ai_review_tree.item(iid, "values")
        product_name = vals[0]
        try:
            qty = int(vals[3]) if vals[3] else 1
        except (ValueError, IndexError):
            qty = 1
        batch = vals[4] if len(vals) > 4 else ""
        expiry = vals[5] if len(vals) > 5 else ""

        template = database.get_product_template(product_name, vendor_name=vendor)
        tpl_price = template[1] if template else 0.0
        tpl_mfg_barcode = template[2] if template else ""
        tpl_mfg_date = template[4] if template else ""

        self.receiving_session[vendor]["total_quantity"] += qty
        self.receiving_session[vendor]["items"].append({
            "name": product_name,
            "qty": qty,
            "price": tpl_price,
            "cost": tpl_price * qty,
            "mfg_barcode": tpl_mfg_barcode,
            "internal_barcode": "",
            "mfg_date": tpl_mfg_date or "",
            "exp_date": expiry or tpl_mfg_date or "",
            "date_received": recv_date,
        })
        added += 1

    self._refresh_po_treeview()
    self._ai_status_label.configure(text=f"Added {added} item(s) to queue.")


def _ai_add_all_to_queue(self):
    """Add all AI-extracted items to the purchase order queue."""
    children = self._ai_review_tree.get_children()
    if not children:
        messagebox.showinfo("Empty", "No extracted items to add.")
        return

    # Select all and delegate
    self._ai_review_tree.selection_set(children)
    self._ai_add_selected_to_queue()


def _ai_clear_review(self):
    """Clear the AI review table."""
    self._ai_review_tree.delete(*self._ai_review_tree.get_children())
    self._ai_extracted_items = []


# ── Smart Parse (Offline) Methods ──────────────────────────────────────

def _run_smart_parse(self):
    """Open file dialog and run offline smart parsing on selected document."""
    from tkinter import filedialog
    from smart_parser import parse_invoice_file

    file_path = filedialog.askopenfilename(
        title="Select Supplier Invoice / Delivery Note",
        filetypes=[
            ("Text files", "*.txt"),
            ("All files", "*.*"),
        ],
    )
    if not file_path:
        return

    self._smart_extract_btn.configure(state="disabled", text="Parsing...")
    self._ai_status_label.configure(text="Running offline parser...")
    self._ai_clear_review()

    try:
        items = parse_invoice_file(file_path)
        self._ai_populate_review(items)
        self._ai_status_label.configure(
            text=f"Smart-parsed {len(items)} item(s) — review and add to queue."
        )
    except Exception as exc:
        self._ai_status_label.configure(text=f"Error: {exc}")
        messagebox.showerror("Smart Parse Failed", str(exc))
    finally:
        self._smart_extract_btn.configure(state="normal", text="Smart Parse (Offline)")
