import customtkinter as ctk
from tkinter import ttk

import database
import barcode_logic


def setup_expiring_tab(self):
    self.tab_expiring.grid_rowconfigure(0, weight=0)
    self.tab_expiring.grid_rowconfigure(1, weight=0)
    self.tab_expiring.grid_rowconfigure(2, weight=0)
    self.tab_expiring.grid_rowconfigure(3, weight=1)
    self.tab_expiring.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(self.tab_expiring, text="Expiry Alerts",
                 font=ctk.CTkFont(size=24, weight="bold"), text_color="#f0f0f0").grid(
        row=0, column=0, padx=20, pady=(20, 8), sticky="w")

    controls_frame = ctk.CTkFrame(self.tab_expiring, fg_color="transparent")
    controls_frame.grid(row=1, column=0, padx=10, pady=(10, 5), sticky="ew")

    ctk.CTkLabel(controls_frame, text="Main Threshold (days):",
                 font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(0, 4))
    self.expiring_days_var = ctk.StringVar(value="50")
    ctk.CTkEntry(controls_frame, width=50,
                 textvariable=self.expiring_days_var).pack(side="left", padx=(0, 12))

    ctk.CTkLabel(controls_frame, text="Critical Threshold (days):",
                 font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(0, 4))
    self.critical_days_var = ctk.StringVar(value="7")
    ctk.CTkEntry(controls_frame, width=50,
                 textvariable=self.critical_days_var).pack(side="left", padx=(0, 12))

    ctk.CTkButton(controls_frame, text="Search", width=90,
                  command=self.load_expiring_items).pack(side="left", padx=(0, 8))

    ctk.CTkLabel(controls_frame, text="Filter by Vendor:",
                 font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(16, 4))
    self.vendor_filter_var = ctk.StringVar(value="All Vendors")
    self.vendor_filter_combo = ctk.CTkComboBox(
        controls_frame, width=160, state="readonly",
        variable=self.vendor_filter_var,
        values=["All Vendors"],
        command=lambda _: self.load_expiring_items())
    self.vendor_filter_combo.pack(side="left", padx=(0, 8))

    self.expiring_summary_label = ctk.CTkLabel(
        controls_frame, text="",
        font=ctk.CTkFont(size=13, weight="bold"), text_color="#ffc107")
    self.expiring_summary_label.pack(side="left", padx=(12, 0))

    vendor_bar_frame = ctk.CTkFrame(self.tab_expiring, fg_color="transparent")
    vendor_bar_frame.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")

    vendor_summary_label = ctk.CTkLabel(
        vendor_bar_frame, text="Vendor Summary:",
        font=ctk.CTkFont(size=12, weight="bold"), text_color="#8ab4f8")
    vendor_summary_label.pack(side="left", padx=(0, 6))

    style_vendor = ttk.Style()
    style_vendor.configure("VendorSummary.Treeview",
                          background="#2b2b2b", foreground="white",
                          rowheight=20, fieldbackground="#2b2b2b",
                          bordercolor="#343638", borderwidth=0,
                          font=("Segoe UI", 11))
    style_vendor.map("VendorSummary.Treeview",
                     background=[('selected', '#1f538d')])
    style_vendor.configure("VendorSummary.Treeview.Heading",
                          background="#3a3f44", foreground="#cccccc",
                          relief="flat", font=("Segoe UI", 10, "bold"))
    style_vendor.map("VendorSummary.Treeview.Heading",
                    background=[('active', '#4a5058')])

    self.tree_vendor_summary = ttk.Treeview(
        vendor_bar_frame, columns=("Vendor", "Count"),
        show="headings", style="VendorSummary.Treeview", height=4)
    self.tree_vendor_summary.heading("Vendor", text="Vendor")
    self.tree_vendor_summary.heading("Count", text="Count")
    self.tree_vendor_summary.column("Vendor", width=180, anchor="w")
    self.tree_vendor_summary.column("Count", width=60, anchor="center")
    self.tree_vendor_summary.pack(side="left", fill="x", expand=True, padx=(0, 6))

    vendor_scroll = ttk.Scrollbar(vendor_bar_frame, orient="vertical",
                                   command=self.tree_vendor_summary.yview)
    self.tree_vendor_summary.configure(yscroll=vendor_scroll.set)
    vendor_scroll.pack(side="left", fill="y")

    self.tree_vendor_summary.bind("<<TreeviewSelect>>", self._on_vendor_summary_click)

    style = ttk.Style()
    style.theme_use("default")

    style.configure("Expired.Treeview",
                    background="#2b2b2b", foreground="#888888",
                    rowheight=22, fieldbackground="#2b2b2b",
                    bordercolor="#343638", borderwidth=0)
    style.map("Expired.Treeview", background=[('selected', '#555555')])
    style.configure("Expired.Treeview.Heading",
                    background="#444444", foreground="#aaaaaa", relief="flat")
    style.map("Expired.Treeview.Heading", background=[('active', '#555555')])

    style.configure("Critical.Treeview",
                    background="#2b2b2b", foreground="#ff6b6b",
                    rowheight=22, fieldbackground="#2b2b2b",
                    bordercolor="#343638", borderwidth=0)
    style.map("Critical.Treeview", background=[('selected', '#993333')])
    style.configure("Critical.Treeview.Heading",
                    background="#6b2020", foreground="#ffaaaa", relief="flat")
    style.map("Critical.Treeview.Heading", background=[('active', '#883333')])

    style.configure("Warning.Treeview",
                    background="#2b2b2b", foreground="#ffc107",
                    rowheight=22, fieldbackground="#2b2b2b",
                    bordercolor="#343638", borderwidth=0)
    style.map("Warning.Treeview", background=[('selected', '#886600')])
    style.configure("Warning.Treeview.Heading",
                    background="#665500", foreground="#ffe066", relief="flat")
    style.map("Warning.Treeview.Heading", background=[('active', '#887700')])

    columns = ("Name", "Price", "Int. Barcode", "Vendor", "Expiry", "Mfg Date", "Mfg Barcode")

    expiring_pane = ttk.PanedWindow(self.tab_expiring, orient="vertical")
    expiring_pane.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
    self.tab_expiring.grid_rowconfigure(3, weight=1)

    expired_frame = ttk.Frame(expiring_pane)
    expired_label = ttk.Label(expired_frame, text=" Already Expired",
                              background="#3a3a3a", foreground="#888888",
                              font=ctk.CTkFont(size=13, weight="bold"))
    expired_label.pack(fill="x")
    self.tree_expired = ttk.Treeview(expired_frame, columns=columns,
                                     show="headings", style="Expired.Treeview", height=3)
    for col in columns:
        self.tree_expired.heading(col, text=col)
        w = {"Name": 160, "Price": 65, "Int. Barcode": 115,
             "Vendor": 95, "Expiry": 90, "Mfg Date": 90, "Mfg Barcode": 115}
        self.tree_expired.column(col, width=w.get(col, 80), anchor="w")
    self.tree_expired.column("Price", anchor="e")
    self.tree_expired.column("Expiry", anchor="center")
    self.tree_expired.column("Mfg Date", anchor="center")
    self.tree_expired.pack(fill="both", expand=True, side="left")
    exp_expired_scroll = ttk.Scrollbar(expired_frame, orient="vertical",
                                        command=self.tree_expired.yview)
    self.tree_expired.configure(yscroll=exp_expired_scroll.set)
    exp_expired_scroll.pack(fill="y", side="right")
    expiring_pane.add(expired_frame, weight=1)

    critical_frame = ttk.Frame(expiring_pane)
    critical_label = ttk.Label(critical_frame, text=" Critical / Urgent",
                               background="#5c2020", foreground="#ffaaaa",
                               font=ctk.CTkFont(size=13, weight="bold"))
    critical_label.pack(fill="x")
    self.tree_critical = ttk.Treeview(critical_frame, columns=columns,
                                      show="headings", style="Critical.Treeview", height=3)
    for col in columns:
        self.tree_critical.heading(col, text=col)
        w = {"Name": 160, "Price": 65, "Int. Barcode": 115,
             "Vendor": 95, "Expiry": 90, "Mfg Date": 90, "Mfg Barcode": 115}
        self.tree_critical.column(col, width=w.get(col, 80), anchor="w")
    self.tree_critical.column("Price", anchor="e")
    self.tree_critical.column("Expiry", anchor="center")
    self.tree_critical.column("Mfg Date", anchor="center")
    self.tree_critical.pack(fill="both", expand=True, side="left")
    exp_critical_scroll = ttk.Scrollbar(critical_frame, orient="vertical",
                                         command=self.tree_critical.yview)
    self.tree_critical.configure(yscroll=exp_critical_scroll.set)
    exp_critical_scroll.pack(fill="y", side="right")
    expiring_pane.add(critical_frame, weight=1)

    warning_frame = ttk.Frame(expiring_pane)
    warning_label = ttk.Label(warning_frame, text=" Expiring Soon",
                              background="#665500", foreground="#ffe066",
                              font=ctk.CTkFont(size=13, weight="bold"))
    warning_label.pack(fill="x")
    self.tree_warning = ttk.Treeview(warning_frame, columns=columns,
                                     show="headings", style="Warning.Treeview", height=3)
    for col in columns:
        self.tree_warning.heading(col, text=col)
        w = {"Name": 160, "Price": 65, "Int. Barcode": 115,
             "Vendor": 95, "Expiry": 90, "Mfg Date": 90, "Mfg Barcode": 115}
        self.tree_warning.column(col, width=w.get(col, 80), anchor="w")
    self.tree_warning.column("Price", anchor="e")
    self.tree_warning.column("Expiry", anchor="center")
    self.tree_warning.column("Mfg Date", anchor="center")
    self.tree_warning.pack(fill="both", expand=True, side="left")
    exp_warning_scroll = ttk.Scrollbar(warning_frame, orient="vertical",
                                        command=self.tree_warning.yview)
    self.tree_warning.configure(yscroll=exp_warning_scroll.set)
    exp_warning_scroll.pack(fill="y", side="right")
    expiring_pane.add(warning_frame, weight=1)


def load_expiring_items(self):
    from datetime import date, timedelta

    for tree in (self.tree_expired, self.tree_critical, self.tree_warning):
        for item in tree.get_children():
            tree.delete(item)

    try:
        days = int(self.expiring_days_var.get().strip())
        if days <= 0:
            raise ValueError
    except (ValueError, TypeError):
        self.expiring_summary_label.configure(
            text="Invalid main threshold. Enter a positive integer.")
        return

    try:
        critical_days = int(self.critical_days_var.get().strip())
        if critical_days <= 0:
            raise ValueError
    except (ValueError, TypeError):
        self.expiring_summary_label.configure(
            text="Invalid critical threshold. Enter a positive integer.")
        return

    config = barcode_logic.load_config()
    ignore_list = config.get("expiry_ignore_list", [])
    batches = database.get_batches_expiring_within(days, exclude_names=ignore_list)

    today = date.today()
    critical_cutoff = today + timedelta(days=critical_days)

    expired_items = []
    critical_items = []
    warning_items = []

    for batch in batches:
        batch_id, name, price, mfg_barcode, int_barcode, status, expiry, mfg_date, vendor = batch
        expiry_text = expiry if expiry else "N/A"
        mfg_text = mfg_date if mfg_date else "N/A"
        vendor_text = vendor or "N/A"
        row_vals = (
            name, self.app.currency.fmt(price), int_barcode, vendor_text,
            expiry_text, mfg_text, mfg_barcode
        )

        try:
            normalized = (expiry or "").replace('/', '-')
            parts = normalized.split('-')
            exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            continue

        if exp_date < today:
            expired_items.append((batch_id, row_vals))
        elif exp_date <= critical_cutoff:
            critical_items.append((batch_id, row_vals))
        else:
            warning_items.append((batch_id, row_vals))

    all_vendor_counts = {}
    for _, vals in expired_items + critical_items + warning_items:
        v = vals[3]
        all_vendor_counts[v] = all_vendor_counts.get(v, 0) + 1
    sorted_vendors = sorted(all_vendor_counts.items(), key=lambda x: x[1], reverse=True)

    for item in self.tree_vendor_summary.get_children():
        self.tree_vendor_summary.delete(item)
    for vendor_name, count in sorted_vendors:
        self.tree_vendor_summary.insert("", "end", values=(vendor_name, count))

    vendor_names = [v for v, _ in sorted_vendors]
    combo_values = ["All Vendors"] + vendor_names
    current_filter = self.vendor_filter_var.get()
    self.vendor_filter_combo.configure(values=combo_values)
    if current_filter not in combo_values:
        self.vendor_filter_var.set("All Vendors")

    selected_vendor = self.vendor_filter_var.get()
    if selected_vendor != "All Vendors":
        expired_items = [(bid, vals) for bid, vals in expired_items if vals[3] == selected_vendor]
        critical_items = [(bid, vals) for bid, vals in critical_items if vals[3] == selected_vendor]
        warning_items = [(bid, vals) for bid, vals in warning_items if vals[3] == selected_vendor]

    for batch_id, vals in expired_items:
        self.tree_expired.insert("", "end", iid=f"exp_{batch_id}", values=vals)

    for batch_id, vals in critical_items:
        self.tree_critical.insert("", "end", iid=f"crit_{batch_id}", values=vals)

    for batch_id, vals in warning_items:
        self.tree_warning.insert("", "end", iid=f"warn_{batch_id}", values=vals)

    total = len(expired_items) + len(critical_items) + len(warning_items)
    filter_suffix = f" ({selected_vendor})" if selected_vendor != "All Vendors" else ""
    self.expiring_summary_label.configure(
        text=f"Total: {total} | Expired: {len(expired_items)} | "
             f"Critical: {len(critical_items)} | Warning: {len(warning_items)}{filter_suffix}")


def _on_vendor_summary_click(self, event):
    selected = self.tree_vendor_summary.selection()
    if not selected:
        return
    vendor_name = self.tree_vendor_summary.item(selected[0], "values")[0]
    self.vendor_filter_var.set(vendor_name)
    self.load_expiring_items()
