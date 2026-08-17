import customtkinter as ctk
from tkinter import ttk, messagebox
from datetime import datetime, date, timedelta
from collections import defaultdict
import csv
import os
import database
import barcode_logic
import currency
import i18n
from ui_helpers import apply_treeview_style

# RBAC middleware (lazy-safe: authz imports only `database`, no UI cycle).
import authz
import auth_session


# ─────────────────────────────────────────────────────────────────────────────
# EXISTING: Sales Report Tab (preserved and enhanced)
# ─────────────────────────────────────────────────────────────────────────────

def setup_report_tab(self):
    self.tab_report.grid_rowconfigure(0, weight=0)
    self.tab_report.grid_rowconfigure(1, weight=0)
    self.tab_report.grid_rowconfigure(2, weight=1)
    self.tab_report.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(self.tab_report, text="Sales Report",
                 font=ctk.CTkFont(size=24, weight="bold"), text_color="#f0f0f0").grid(
        row=0, column=0, padx=20, pady=(20, 8), sticky="w")

    # ── Segmented control to switch Sales / Analytics ────────────────────
    seg_frame = ctk.CTkFrame(self.tab_report, fg_color="transparent")
    seg_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
    seg_frame.grid_columnconfigure(0, weight=1)

    self._report_view_var = ctk.StringVar(value="Sales")
    ctk.CTkSegmentedButton(
        seg_frame, variable=self._report_view_var,
        values=["Sales", "Analytics"],
        command=self._on_report_view_switch,
        font=ctk.CTkFont(size=13, weight="bold"),
    ).grid(row=0, column=0, sticky="w")

    # ── Two switchable frames ───────────────────────────────────────────
    self._sales_frame = ctk.CTkFrame(self.tab_report, fg_color="transparent")
    self._analytics_frame = ctk.CTkFrame(self.tab_report, fg_color="transparent")

    # ── Build Sales Report frame ────────────────────────────────────────
    self._build_sales_frame(self._sales_frame)

    # ── Build Analytics frame ───────────────────────────────────────────
    self.setup_analytics_panel(self._analytics_frame)

    # Show Sales by default
    self._sales_frame.grid(row=2, column=0, sticky="nsew", padx=2, pady=2)


def _on_report_view_switch(self, choice):
    self._sales_frame.grid_forget()
    self._analytics_frame.grid_forget()
    if choice == "Sales":
        self._sales_frame.grid(row=2, column=0, sticky="nsew", padx=2, pady=2)
    else:
        self._analytics_frame.grid(row=2, column=0, sticky="nsew", padx=2, pady=2)


def _build_sales_frame(self, frame):
    frame.grid_rowconfigure(3, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    top_frame = ctk.CTkFrame(frame, fg_color="transparent")
    top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

    self.report_count_label = ctk.CTkLabel(top_frame, text="Total Items Sold: 0", font=ctk.CTkFont(size=16, weight="bold"))
    self.report_count_label.pack(side="left", padx=20)

    self.report_revenue_label = ctk.CTkLabel(top_frame, text=i18n.t("total_revenue_label") + ": " + self.currency.fmt(0), font=ctk.CTkFont(size=16, weight="bold"), text_color="#28a745")
    self.report_revenue_label.pack(side="left", padx=20)

    self.report_today_label = ctk.CTkLabel(top_frame, text=i18n.t("todays_sales") + ": " + self.currency.fmt(0), font=ctk.CTkFont(size=16, weight="bold"), text_color="#17a2b8")
    self.report_today_label.pack(side="left", padx=20)

    refresh_btn = ctk.CTkButton(top_frame, text="Refresh", width=90, fg_color="#6c757d", hover_color="#5a6268",
                                command=self.load_sales_report)
    refresh_btn.pack(side="right", padx=(0, 10))

    export_sales_btn = ctk.CTkButton(top_frame, text="Export Sales Report (CSV)", width=160,
                                     fg_color="#16a34a", hover_color="#15803d",
                                     command=authz.require_permission("sales.modify_report")(self._export_sales_report_csv))
    export_sales_btn.pack(side="right", padx=(0, 10))

    refund_btn = ctk.CTkButton(top_frame, text="Refund Item", fg_color="#ffc107", text_color="black", hover_color="#e0a800",
                               command=authz.require_permission("sales.modify_report")(self.refund_item))
    refund_btn.pack(side="right", padx=(0, 10))

    date_frame = ctk.CTkFrame(frame, fg_color="transparent")
    date_frame.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")

    ctk.CTkLabel(date_frame, text="Query Specific Date:", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(20, 5))

    self.date_entry = ctk.CTkEntry(date_frame, width=130, placeholder_text="YYYY-MM-DD")
    self.date_entry.pack(side="left", padx=5)
    self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))

    ctk.CTkButton(date_frame, text="Check Date", width=100, command=self.calculate_custom_date_sales).pack(side="left", padx=5)

    self.report_custom_date_label = ctk.CTkLabel(date_frame, text=i18n.t("selected_date_sales") + ": " + self.currency.fmt(0), font=ctk.CTkFont(size=14, weight="bold"), text_color="#6f42c1")
    self.report_custom_date_label.pack(side="left", padx=20)

    ctk.CTkLabel(date_frame, text="  |  ", font=ctk.CTkFont(size=14)).pack(side="left", padx=0)

    ctk.CTkLabel(date_frame, text="Search Barcode:", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(10, 5))
    self.refund_search_var = ctk.StringVar()
    self.refund_search_entry = ctk.CTkEntry(date_frame, width=180, placeholder_text="Internal barcode...")
    self.refund_search_entry.pack(side="left", padx=5)
    self.refund_search_entry.bind("<Return>", lambda _: self._search_for_refund())

    ctk.CTkButton(date_frame, text="Find", width=60, fg_color="#17a2b8", hover_color="#138496",
                  command=self._search_for_refund).pack(side="left", padx=2)
    ctk.CTkButton(date_frame, text="Clear", width=60, fg_color="#6c757d", hover_color="#5a6268",
                  command=self._clear_refund_search).pack(side="left", padx=2)

    columns = ("Product", "Qty", "Unit Price", "Total", "Barcode", "Vendor", "Expiry", "Time", "Payment")
    self.tree_report = ttk.Treeview(frame, columns=columns, show="tree headings")
    apply_treeview_style(self.tree_report)

    self.tree_report.heading("#0", text="Date / Item")
    self.tree_report.column("#0", width=180, anchor="w")
    self.tree_report.heading("Product", text="Product")
    self.tree_report.heading("Qty", text="Qty")
    self.tree_report.heading("Unit Price", text="Unit Price")
    self.tree_report.heading("Total", text="Total")
    self.tree_report.heading("Barcode", text="Barcode")
    self.tree_report.heading("Vendor", text="Vendor")
    self.tree_report.heading("Expiry", text="Expiry")
    self.tree_report.heading("Time", text="Time")
    self.tree_report.heading("Payment", text="Payment")

    self.tree_report.column("Product", width=140, anchor="w")
    self.tree_report.column("Qty", width=40, anchor="center")
    self.tree_report.column("Unit Price", width=80, anchor="e")
    self.tree_report.column("Total", width=80, anchor="e")
    self.tree_report.column("Barcode", width=100, anchor="w")
    self.tree_report.column("Vendor", width=80, anchor="w")
    self.tree_report.column("Expiry", width=80, anchor="center")
    self.tree_report.column("Time", width=70, anchor="center")
    self.tree_report.column("Payment", width=70, anchor="center")

    self.tree_report.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))

    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree_report.yview)
    self.tree_report.configure(yscrollcommand=scrollbar.set)
    scrollbar.grid(row=3, column=1, sticky="ns", pady=(0, 10))


def load_sales_report(self):
    """Load sales report data in a background thread; update tree via after()."""
    from async_ui import AsyncUI

    # Clear tree immediately to show UI responsiveness
    for item in self.tree_report.get_children():
        self.tree_report.delete(item)
    self.report_count_label.configure(text="Loading...")

    def _load():
        try:
            return database.get_receipt_items_grouped_by_date()
        except Exception as e:
            return {"error": str(e)}

    def _on_done(grouped, error=None):
        if isinstance(grouped, dict) and "error" in grouped:
            messagebox.showerror("Report Error", f"Failed to load sales report:\n{grouped['error']}")
            self.report_count_label.configure(text="Loading...")
            return

        total_items = 0
        total_revenue = 0.0
        for date_str, rows in sorted(grouped.items(), reverse=True):
            day_qty = sum(r[3] for r in rows)
            day_revenue = sum(r[5] for r in rows)
            total_items += day_qty
            total_revenue += day_revenue

            _rev = self.currency.fmt(day_revenue)
            self.tree_report.insert(
                date_iid, "end", text=date_str, values=(
                f"{date_str}  ({day_qty} items, {_rev})", "", "", "", "", "",
            ), open=(date_str == date.today().strftime("%Y-%m-%d")))

            for r in rows:
                time_part = r[6][11:19] if len(r[6]) > 11 else ""
                self.tree_report.insert(date_iid, "end", text=r[2], values=(
                    r[2], r[3], self.currency.fmt(r[4]),
                    r[8], r[9], r[10], time_part, r[7],
                ))

        today_sales = database.get_receipts_total_for_date(date.today().strftime("%Y-%m-%d"))
        self.report_count_label.configure(text=f"Total Items Sold: {total_items}")
        self.report_revenue_label.configure(text=f"Total Revenue: {self.currency.fmt(total_revenue)}")

    AsyncUI.get().run(_load, callback=_on_done)


def _search_for_refund(self):
    query = self.refund_search_entry.get().strip()
    if not query:
        messagebox.showwarning("Warning", "Please enter an internal barcode to search.")
        return

    for item in self.tree_report.get_children():
        self.tree_report.delete(item)

    all_items = database.get_all_receipt_items_flat()
    matches = [r for r in all_items if query.lower() in (r[8] or "").lower()]

    if not matches:
        self.report_count_label.configure(text="Search: No items found")
        self.report_revenue_label.configure(text="")
        self.report_today_label.configure(text=f"Barcode: {query}")
        return

    grouped = defaultdict(list)
    for r in matches:
        date_part = r[6][:10] if r[6] and len(r[6]) >= 10 else "Unknown"
        grouped[date_part].append(r)

    total_items = 0
    total_revenue = 0.0
    for date_str, rows in sorted(grouped.items(), reverse=True):
        day_qty = sum(r[3] for r in rows)
        day_revenue = sum(r[5] for r in rows)
        total_items += day_qty
        total_revenue += day_revenue

        _rev = self.currency.fmt(day_revenue)
        self.tree_report.insert(
            date_iid, "end", text=date_str, values=(
            f"{date_str}  ({day_qty} items, {_rev})", "", "", "", "", "",
        ), open=True)

        for r in rows:
            time_part = r[6][11:19] if len(r[6]) > 11 else ""
            self.tree_report.insert(date_iid, "end", text=r[2], values=(
                r[2], r[3], self.currency.fmt(r[4]),
                r[8], r[9], r[10], time_part, r[7],
            ))

    self.report_count_label.configure(text=f"Search: {total_items} item(s) found")
    self.report_revenue_label.configure(text=f"Matched Revenue: {self.currency.fmt(total_revenue)}")
    self.report_today_label.configure(text=f"Barcode: {query}")


def _clear_refund_search(self):
    self.refund_search_entry.delete(0, 'end')
    self.load_sales_report()


def calculate_custom_date_sales(self):
    raw = self.date_entry.get().strip()
    if not raw:
        raw = date.today().strftime("%Y-%m-%d")
    try:
        date.fromisoformat(raw)
    except ValueError:
        messagebox.showerror("Invalid Date", "Please enter a valid date in YYYY-MM-DD format.")
        return

    rows = database.get_receipt_items_for_date(raw)
    date_total = sum(r[5] for r in rows)
    self.report_custom_date_label.configure(text=f"Sales for {raw}: {self.currency.fmt(date_total)}")


def refund_item(self):
    if not authz.check_permission(auth_session.current_user_id(), "sales.modify_report"):
        authz.access_denied("sales.modify_report")
        return
    selected = self.tree_report.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select an item to refund.")
        return

    item = selected[0]
    if not self.tree_report.parent(item):
        messagebox.showwarning("Warning", "Please select an individual item row, not a date header.")
        return

    values = self.tree_report.item(item, 'values')
    product_name = values[0]
    qty = int(values[1])
    barcode = values[4]

    all_items = database.get_all_receipt_items_flat()
    target_item = None
    for ri in all_items:
        if ri[2] == product_name and ri[3] == qty and ri[8] == barcode:
            target_item = ri
            break

    if not target_item:
        messagebox.showerror("Error", "Could not locate the receipt item for refund.")
        return

    receipt_item_id = target_item[0]
    receipt_id = target_item[1]

    confirm = messagebox.askyesno(
        "Confirm Refund",
        f"Refund {qty}x '{product_name}' from Receipt #{receipt_id}?\n\n"
        f"Batch: {barcode or 'N/A'}\n"
        f"This will restore the item(s) to inventory.")
    if not confirm:
        return

    try:
        database.reverse_receipt_item(receipt_item_id)
        self.load_sales_report()
        self.load_inventory()
        self._refresh_checkout_stock_dropdown()
        messagebox.showinfo("Refunded", "Item successfully returned to inventory.")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to refund item:\n{str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# NEW: Analytics Panel (Feature 3) — date range filtering + ranked products + CSV
# ─────────────────────────────────────────────────────────────────────────────

def setup_analytics_panel(self, parent_frame):
    """Build the Analytics panel inside the given parent_frame (a CTkFrame).
    Call this from setup_report_tab or as a separate tab section.
    """
    parent_frame.grid_columnconfigure(0, weight=1)
    parent_frame.grid_rowconfigure(2, weight=1)

    # ── Row 0: Date-range controls ───────────────────────────────────────
    ctrl_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
    ctrl_frame.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")

    ctk.CTkLabel(ctrl_frame, text="Analytics Period:",
                 font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(10, 6))

    self._analytics_period_var = ctk.StringVar(value="This Month")
    period_menu = ctk.CTkOptionMenu(
        ctrl_frame, variable=self._analytics_period_var,
        values=["Today", "This Week", "This Month", "Last 30 Days", "This Year", "Custom"],
        command=self._on_analytics_period_change, width=140,
    )
    period_menu.pack(side="left", padx=(0, 8))

    self._analytics_from_label = ctk.CTkLabel(ctrl_frame, text="From:", font=ctk.CTkFont(size=12))
    self._analytics_from_label.pack(side="left", padx=(4, 2))
    self._analytics_from_entry = ctk.CTkEntry(ctrl_frame, width=110, placeholder_text="YYYY-MM-DD")
    self._analytics_from_entry.pack(side="left", padx=(0, 8))

    self._analytics_to_label = ctk.CTkLabel(ctrl_frame, text="To:", font=ctk.CTkFont(size=12))
    self._analytics_to_label.pack(side="left", padx=(4, 2))
    self._analytics_to_entry = ctk.CTkEntry(ctrl_frame, width=110, placeholder_text="YYYY-MM-DD")
    self._analytics_to_entry.pack(side="left", padx=(0, 8))

    # Set default dates
    today = date.today()
    first_of_month = today.replace(day=1)
    self._analytics_from_entry.insert(0, first_of_month.strftime("%Y-%m-%d"))
    self._analytics_to_entry.insert(0, today.strftime("%Y-%m-%d"))

    load_btn = ctk.CTkButton(ctrl_frame, text="Load Analytics", width=130,
                             fg_color="#2563EB", hover_color="#1d4ed8",
                             command=self.load_analytics)
    load_btn.pack(side="left", padx=(4, 4))

    export_btn = ctk.CTkButton(ctrl_frame, text="Export CSV", width=100,
                               fg_color="#16a34a", hover_color="#15803d",
                               command=self._export_analytics_csv)
    export_btn.pack(side="left", padx=(4, 0))

    # ── Row 1: Summary KPIs ─────────────────────────────────────────────
    kpi_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
    kpi_frame.grid(row=1, column=0, padx=10, pady=(4, 4), sticky="ew")
    kpi_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

    self._analytics_kpi = {}
    kpi_defs = [
        ("Total Sold", "#0891b2"),
        ("Revenue", "#16a34a"),
        ("Transactions", "#7c3aed"),
        ("Avg Basket", "#f59e0b"),
        ("Est. Profit", "#22c55e"),
    ]
    for idx, (title, color) in enumerate(kpi_defs):
        card = ctk.CTkFrame(kpi_frame, fg_color="#1e1e2e", corner_radius=8)
        card.grid(row=0, column=idx, padx=4, pady=4, sticky="nsew")
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#94a3b8").pack(anchor="w", padx=10, pady=(8, 0))
        val_lbl = ctk.CTkLabel(card, text="--", font=ctk.CTkFont(size=18, weight="bold"),
                               text_color=color)
        val_lbl.pack(anchor="w", padx=10, pady=(0, 8))
        self._analytics_kpi[title] = val_lbl

    # ── Row 2: Ranked products treeview ──────────────────────────────────
    tree_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
    tree_frame.grid(row=2, column=0, padx=10, pady=(4, 10), sticky="nsew")
    tree_frame.grid_columnconfigure(0, weight=1)
    tree_frame.grid_rowconfigure(0, weight=1)

    cols = ("Rank", "Product", "Qty Sold", "Revenue", "Avg Price")
    self._analytics_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=12)
    apply_treeview_style(self._analytics_tree)
    for c in cols:
        self._analytics_tree.heading(c, text=c)
    self._analytics_tree.column("Rank", width=50, anchor="center")
    self._analytics_tree.column("Product", width=220, anchor="w")
    self._analytics_tree.column("Qty Sold", width=90, anchor="center")
    self._analytics_tree.column("Revenue", width=110, anchor="e")
    self._analytics_tree.column("Avg Price", width=100, anchor="e")
    self._analytics_tree.grid(row=0, column=0, sticky="nsew")

    tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._analytics_tree.yview)
    self._analytics_tree.configure(yscrollcommand=tree_scroll.set)
    tree_scroll.grid(row=0, column=1, sticky="ns")

    self._analytics_data_cache = []  # For CSV export


def _on_analytics_period_change(self, choice):
    """Auto-fill date entries when a preset period is selected."""
    today = date.today()
    presets = {
        "Today": (today, today),
        "This Week": (today - timedelta(days=today.weekday()), today),
        "This Month": (today.replace(day=1), today),
        "Last 30 Days": (today - timedelta(days=30), today),
        "This Year": (today.replace(month=1, day=1), today),
    }
    if choice in presets:
        start, end = presets[choice]
        self._analytics_from_entry.delete(0, "end")
        self._analytics_from_entry.insert(0, start.strftime("%Y-%m-%d"))
        self._analytics_to_entry.delete(0, "end")
        self._analytics_to_entry.insert(0, end.strftime("%Y-%m-%d"))
    # For "Custom" the user edits manually


def load_analytics(self):
    """Fetch and display sales analytics for the selected date range.
    Uses a background thread for the DB query; updates KPIs via after().
    """
    from async_ui import AsyncUI

    start = self._analytics_from_entry.get().strip()
    end = self._analytics_to_entry.get().strip()

    if not start or not end:
        messagebox.showwarning("Missing Dates", "Please enter both From and To dates.")
        return

    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
    except ValueError:
        messagebox.showerror("Invalid Date", "Dates must be in YYYY-MM-DD format.")
        return

    if start > end:
        messagebox.showwarning("Invalid Range", "From date must be before or equal to To date.")
        return

    def _load():
        try:
            return database.get_sales_analytics(start, end)
        except Exception as e:
            return {"error": str(e)}

    def _on_done(result, error=None):
        if result is None or (isinstance(result, dict) and "error" in result):
            msg = result["error"] if isinstance(result, dict) else str(error)
            messagebox.showerror("Analytics Error", f"Failed to load analytics:\n{msg}")
            return

        # Update KPIs
        self._analytics_kpi["Total Sold"].configure(text=str(result["total_items_sold"]))
        self._analytics_kpi["Revenue"].configure(text=self.currency.fmt(result['total_revenue']))
        self._analytics_kpi["Transactions"].configure(text=str(result["total_transactions"]))
        self._analytics_kpi["Avg Basket"].configure(text=f"{result['avg_basket_size']:.1f}")

        config = barcode_logic.load_config()
        tax_rate = config.get("tax_rate", 0.0)
        tax_multiplier = 1 + (tax_rate / 100.0)
        est_profit = result["total_revenue"] * 0.30
        self._analytics_kpi["Est. Profit"].configure(text=f"{self.currency.fmt(est_profit)}")

        # Update treeview
        for item in self._analytics_tree.get_children():
            self._analytics_tree.delete(item)

        self._analytics_data_cache = result["ranked_products"]
        for rank, name, qty, revenue, avg_price in result["ranked_products"]:
            self._analytics_tree.insert("", "end", values=(
                rank, name, qty, f"{self.currency.fmt(revenue)}",
            ))

    AsyncUI.get().run(_load, callback=_on_done)


def _export_analytics_csv(self):
    """Export the current analytics treeview to a CSV file."""
    if not self._analytics_data_cache:
        messagebox.showwarning("No Data", "Load analytics first before exporting.")
        return

    file_path = ctk.filedialog.asksaveasfilename(
        title="Export Analytics to CSV",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialfile=f"pharmacy_analytics_{date.today().strftime('%Y%m%d')}.csv",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Rank", "Product", "Qty Sold", "Revenue", "Avg Price"])
            for rank, name, qty, revenue, avg_price in self._analytics_data_cache:
                writer.writerow([rank, name, qty, f"{revenue:.2f}", f"{avg_price:.2f}"])
        messagebox.showinfo("Export Complete", f"Analytics exported to:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")


def _export_sales_report_csv(self):
    """Export the current sales report treeview to a CSV file."""
    if not authz.check_permission(auth_session.current_user_id(), "sales.modify_report"):
        authz.access_denied("sales.modify_report")
        return
    file_path = ctk.filedialog.asksaveasfilename(
        title="Export Sales Report to CSV",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialfile=f"sales_report_{date.today().strftime('%Y%m%d')}.csv",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Product", "Qty", "Unit Price", "Total",
                             "Barcode", "Vendor", "Expiry", "Time", "Payment"])

            grouped = database.get_receipt_items_grouped_by_date()
            for date_str, rows in sorted(grouped.items(), reverse=True):
                for r in rows:
                    time_part = r[6][11:19] if len(r[6]) > 11 else ""
                    writer.writerow([
                        date_str, r[2], r[3], f"{r[4]:.2f}", f"{r[5]:.2f}",
                        r[8], r[9], r[10], time_part, r[7],
                    ])

        messagebox.showinfo("Export Complete", f"Sales report exported to:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")
