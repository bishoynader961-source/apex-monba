import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime

import database
import audit_log

def setup_dashboard_tab(self):
    """Build the Dashboard tab with KPI cards, quick actions, and recent activity."""
    for w in self.tab_dashboard.winfo_children():
        w.destroy()

    self.tab_dashboard.grid_columnconfigure(0, weight=1)
    self.tab_dashboard.grid_rowconfigure(2, weight=1)

    # ── Header row ──────────────────────────────────────────────────────
    header = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
    header.grid(row=0, column=0, padx=20, pady=(16, 8), sticky="ew")
    header.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        header, text="Dashboard",
        font=ctk.CTkFont(size=24, weight="bold"),
    ).grid(row=0, column=0, sticky="w")

    # Quick Action Bar
    quick_actions = ctk.CTkFrame(header, fg_color="transparent")
    quick_actions.grid(row=0, column=1, sticky="e")
    
    ctk.CTkButton(
        quick_actions, text="Add Product", width=120, fg_color="#3B82F6", hover_color="#2563EB",
        command=lambda: self.tab_view.set("Add Product")
    ).pack(side="left", padx=5)
    
    ctk.CTkButton(
        quick_actions, text="Checkout", width=120, fg_color="#10B981", hover_color="#059669",
        command=lambda: self.tab_view.set("Checkout")
    ).pack(side="left", padx=5)

    ctk.CTkButton(
        quick_actions, text="Refresh", width=90, fg_color="#6c757d", hover_color="#5a6268",
        command=self.load_dashboard,
    ).pack(side="left", padx=5)

    # ── KPI cards grid ──────────────────────────────────────────────────
    kpi_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
    kpi_frame.grid(row=1, column=0, padx=20, pady=(4, 8), sticky="ew")
    kpi_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

    self._kpi_labels = {}
    kpi_defs = [
        ("Inventory Value", "total_inventory_value", "${:,.2f}", "#3B82F6"),
        ("Today's Revenue", "todays_sales", "${:,.2f}", "#10B981"),
        ("Active Products", "total_products", "{:}", "#8B5CF6"),
        ("Low Stock Items", "low_stock_count", "{:}", "#F59E0B"),
    ]

    for idx, (title, key, fmt, color) in enumerate(kpi_defs):
        card = ctk.CTkFrame(kpi_frame, fg_color="#2D2D2D", corner_radius=10)
        card.grid(row=0, column=idx, padx=6, pady=6, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color="#A0A0A0",
        ).grid(row=0, column=0, padx=14, pady=(12, 2), sticky="w")

        val_label = ctk.CTkLabel(
            card, text="--", font=ctk.CTkFont(size=22, weight="bold"), text_color=color,
        )
        val_label.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="w")
        self._kpi_labels[key] = (val_label, fmt)

    # ── Bottom row ───────────────────────────────
    bottom_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
    bottom_frame.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="nsew")
    bottom_frame.grid_columnconfigure((0, 1), weight=1)
    bottom_frame.grid_rowconfigure(0, weight=1)

    # Low-stock panel
    low_frame = ctk.CTkFrame(bottom_frame, fg_color="#2D2D2D", corner_radius=10)
    low_frame.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")
    low_frame.grid_columnconfigure(0, weight=1)
    low_frame.grid_rowconfigure(1, weight=1)

    ctk.CTkLabel(
        low_frame, text="Low Stock Alerts", font=ctk.CTkFont(size=14, weight="bold"), text_color="#EF4444",
    ).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

    self._low_stock_textbox = ctk.CTkTextbox(
        low_frame, font=ctk.CTkFont(size=12), fg_color="#2D2D2D", text_color="#FFFFFF", state="disabled", wrap="word",
    )
    self._low_stock_textbox.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

    # Recent Activity Feed
    activity_frame = ctk.CTkFrame(bottom_frame, fg_color="#2D2D2D", corner_radius=10)
    activity_frame.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")
    activity_frame.grid_columnconfigure(0, weight=1)
    activity_frame.grid_rowconfigure(1, weight=1)

    ctk.CTkLabel(
        activity_frame, text="Recent Activity", font=ctk.CTkFont(size=14, weight="bold"), text_color="#FFFFFF",
    ).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

    self._activity_textbox = ctk.CTkTextbox(
        activity_frame, font=ctk.CTkFont(size=12), fg_color="#2D2D2D", text_color="#A0A0A0", state="disabled", wrap="word",
    )
    self._activity_textbox.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

def load_dashboard(self):
    """Refresh all dashboard KPI cards and alert panels."""
    try:
        m = database.get_dashboard_metrics()
    except Exception as e:
        messagebox.showerror("Dashboard Error", f"Failed to load metrics:\n{e}")
        return

    for key, (label, fmt) in self._kpi_labels.items():
        value = m.get(key, 0)
        try:
            label.configure(text=fmt.format(value))
        except (KeyError, ValueError):
            label.configure(text=str(value))

    # Low-stock text
    self._low_stock_textbox.configure(state="normal")
    self._low_stock_textbox.delete("1.0", "end")
    low_items = m.get("low_stock", [])
    if low_items:
        for name, qty, min_exp in low_items:
            exp_display = min_exp if min_exp else "N/A"
            self._low_stock_textbox.insert("end", f"• {qty}x {name} (Exp: {exp_display})\n")
    else:
        self._low_stock_textbox.insert("end", "All products are well-stocked.")
    self._low_stock_textbox.configure(state="disabled")

    # Recent Activity
    self._activity_textbox.configure(state="normal")
    self._activity_textbox.delete("1.0", "end")
    try:
        logs = audit_log.get_logs(limit=15)
        if logs:
            for timestamp, action, details in logs:
                self._activity_textbox.insert("end", f"[{timestamp}] {action}: {details}\n")
        else:
            self._activity_textbox.insert("end", "No recent activity.")
    except Exception as e:
        self._activity_textbox.insert("end", "Failed to load activity logs.")
    self._activity_textbox.configure(state="disabled")
