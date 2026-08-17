import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from ui_navigation import CompactCard, BadgeLabel, COLOR_CARD_BG, COLOR_CARD_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY
from design_system import CascadeStatusBadge
import database
import audit_log
import i18n

# RBAC middleware (authz imports only `database`; no UI import cycle).
import authz
import auth_session


def setup_dashboard_tab(self):
    """Build the Dashboard tab with modern KPI cards, quick actions, alerts, and OCR cascade status.

    Row 0 is reserved for the persistent ``dashboard_banner_frame``
    (created once in ``PharmacyApp.__init__``); it is never destroyed here
    so the region banner survives refreshes.
    """
    banner_frame = getattr(self, "dashboard_banner_frame", None)
    for w in self.tab_dashboard.winfo_children():
        if w is banner_frame:
            continue
        w.destroy()

    self.tab_dashboard.grid_columnconfigure(0, weight=1)
    # Row 0 → persistent banner (weight 0, never destroyed)
    self.tab_dashboard.grid_rowconfigure(0, weight=0)
    # Rows 1–4 are content (header, KPI, OCR, bottom) — bottom row expands
    self.tab_dashboard.grid_rowconfigure(4, weight=1)

    # ── Header row ──
    header = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
    header.grid(row=1, column=0, padx=20, pady=(16, 8), sticky="ew")
    header.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        header, text=i18n.t("dashboard"),
        font=ctk.CTkFont(size=24, weight="bold"),
        text_color=COLOR_TEXT_PRIMARY,
    ).grid(row=0, column=0, sticky="w")

    # Quick Action Bar
    quick_actions = ctk.CTkFrame(header, fg_color="transparent")
    quick_actions.grid(row=0, column=1, sticky="e")

    ctk.CTkButton(
        quick_actions, text=i18n.t("add_product"), width=120, fg_color="#3B82F6", hover_color="#2563EB",
        command=lambda: self.tab_view.set("Add Product")
    ).pack(side="left", padx=5)

    ctk.CTkButton(
        quick_actions, text=i18n.t("checkout"), width=120, fg_color="#10B981", hover_color="#059669",
        command=lambda: self.tab_view.set("Checkout")
    ).pack(side="left", padx=5)

    ctk.CTkButton(
        quick_actions, text=i18n.t("refresh"), width=90, fg_color="#6c757d", hover_color="#5a6268",
        command=self.load_dashboard,
    ).pack(side="left", padx=5)

    # ── KPI cards grid ──
    kpi_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
    kpi_frame.grid(row=2, column=0, padx=20, pady=(4, 8), sticky="ew")
    kpi_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

    self._kpi_labels = {}
    kpi_defs = [
        (i18n.t("total_inventory_value"), "total_inventory_value", "${:,.2f}", "#3B82F6"),
        (i18n.t("todays_sales"), "todays_sales", "${:,.2f}", "#10B981"),
        (i18n.t("total_products"), "total_products", "{:}", "#8B5CF6"),
        (i18n.t("low_stock"), "low_stock_count", "{:}", "#F59E0B"),
    ]

    for idx, (title, key, fmt, color) in enumerate(kpi_defs):
        card = CompactCard(kpi_frame, title=title)
        card.grid(row=0, column=idx, padx=6, pady=6, sticky="nsew")

        val_label = ctk.CTkLabel(
            card, text="--", font=ctk.CTkFont(size=22, weight="bold"), text_color=color,
        )
        val_label.grid(row=1, column=0, padx=16, pady=(4, 16), sticky="w")
        self._kpi_labels[key] = (val_label, fmt)

    # ── OCR Cascade Status Bar ──
    ocr_row = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
    ocr_row.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="ew")
    ocr_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        ocr_row, text=i18n.t("ocr_cascade"), font=ctk.CTkFont(size=12, weight="bold"),
        text_color=COLOR_TEXT_SECONDARY,
    ).grid(row=0, column=0, sticky="w")

    self.dashboard_cascade_badge = CascadeStatusBadge(ocr_row, size="small")
    self.dashboard_cascade_badge.frame.grid(row=0, column=1, sticky="e")

    # ── Bottom row: Alerts + Activity ──
    bottom_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
    bottom_frame.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="nsew")
    bottom_frame.grid_columnconfigure((0, 1), weight=1)
    bottom_frame.grid_rowconfigure(0, weight=1)

    # Low-stock panel
    low_frame = CompactCard(bottom_frame, title=i18n.t("low_stock_alerts"), badge_text="", badge_status="error")
    low_frame.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")
    low_frame.grid_columnconfigure(0, weight=1)
    low_frame.grid_rowconfigure(1, weight=1)

    content = ctk.CTkFrame(low_frame, fg_color="transparent")
    content.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
    content.grid_columnconfigure(0, weight=1)

    self._low_stock_textbox = ctk.CTkTextbox(
        content, font=ctk.CTkFont(size=12), fg_color=COLOR_CARD_BG,
        text_color="#FFFFFF", state="disabled", wrap="word",
    )
    self._low_stock_textbox.pack(fill="both", expand=True)

    # Recent Activity Feed
    activity_frame = CompactCard(bottom_frame, title="Recent Activity")
    activity_frame.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")
    activity_frame.grid_columnconfigure(0, weight=1)
    activity_frame.grid_rowconfigure(1, weight=1)

    act_content = ctk.CTkFrame(activity_frame, fg_color="transparent")
    act_content.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
    act_content.grid_columnconfigure(0, weight=1)

    self._activity_textbox = ctk.CTkTextbox(
        act_content, font=ctk.CTkFont(size=12), fg_color=COLOR_CARD_BG,
        text_color="#A0A0A0", state="disabled", wrap="word",
    )
    self._activity_textbox.pack(fill="both", expand=True)


def load_dashboard(self):
    """Refresh all dashboard KPI cards, alert panels, and cascade badge."""
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
        if authz.check_permission(auth_session.current_user_id(), "audit.view"):
            logs = audit_log.get_logs(limit=15)
            if logs:
                for timestamp, action, user_pin, details in logs:
                    self._activity_textbox.insert("end", f"[{timestamp}] {action}: {details}\n")
            else:
                self._activity_textbox.insert("end", "No recent activity.")
        else:
            self._activity_textbox.insert("end", "[Access denied: insufficient permission to view audit logs.]")
    except Exception as e:
        self._activity_textbox.insert("end", f"Failed to load activity logs: {e}")
    self._activity_textbox.configure(state="disabled")
