import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import os
import re
import json
from datetime import datetime, date, timedelta
from PIL import Image, ImageTk
import tempfile
from collections import defaultdict

import database
import barcode_logic
import audit_log
from path_utils import get_resource_path

from label_engine.canvas_core import LabelCanvas, LabelElement, draw_elements
from label_engine.export import save_label, load_label, export_to_png, print_label, TEMPLATE_PATH

from ui_helpers import _extract_first_var, _extract_all_vars

from ui_modals import (
    LabelDesignerPopup, QuickReceiveModal,
    BulkAddModal, BulkLabelPrintDialog, EditBatchDialog,
)

from ui_add_tab import (
    setup_add_tab, refresh_add_tab_templates,
    on_template_selected, _resolve_template_vars,
    save_product, _update_bulk_button_state, _open_bulk_add_modal,
)
from ui_inventory_tab import (
    setup_inventory_tab, _refresh_expiry_bar, load_inventory,
    _on_sort_change, _on_inventory_filter_change, perform_search,
    _send_to_checkout, _edit_batch, _delete_batch,
    open_label_for_selected, _print_label_for_selected,
    _import_excel, _export_excel,
)
from ui_expiring_tab import (
    setup_expiring_tab, load_expiring_items, _on_vendor_summary_click,
)
from ui_dashboard_tab import setup_dashboard_tab, load_dashboard

from ui_report_tab import (
    setup_report_tab, load_sales_report,
    _on_report_view_switch, _build_sales_frame, _on_analytics_period_change,
    _search_for_refund, _clear_refund_search,
    calculate_custom_date_sales, refund_item,
    setup_analytics_panel, load_analytics, _export_analytics_csv,
    _export_sales_report_csv,
)
from ui_receive_tab import (
    setup_receive_tab, _on_vendor_change, _on_product_change,
    _set_disabled_text, refresh_product_list, _add_to_queue,
    _refresh_po_treeview, _remove_selected_from_queue,
    _print_bulk_labels, _commit_shipment,
    _load_shipment_history, _filter_history_by_date,
    _clear_history_filter, _sort_history_by_date,
    load_receiving_log, calculate_vendor_owed, _print_all_selected_tags,
)
from ui_checkout_tab import (
    setup_checkout_tab, _refresh_checkout_patients, _on_patient_select,
    _refresh_checkout_stock_dropdown,
    _on_checkout_product_change, _checkout_add_item,
    _checkout_remove_item, _checkout_clear_cart,
    _refresh_cart_treeview, _checkout_update_change,
    _checkout_confirm, _refresh_receipts_history,
    _on_receipt_double_click, _print_receipt,
)
from ui_templates_tab import (
    setup_templates_tab, load_templates_grid,
    on_template_tree_select, add_template_gui,
    update_template_gui, delete_template_gui,
)
from ui_settings_tab import (
    setup_settings_tab, browse_db_path,
    _on_role_change, _update_role_controls,
    backup_database_gui, _add_ignore_product,
    _remove_ignore_product, _refresh_ignore_list,
    save_settings, _open_audit_log_viewer,
)
from ui_patients_tab import (
    setup_patients_tab,
)


class PharmacyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Pharmacy Inventory System")
        self.geometry("1000x700")

        self._set_window_icon()

        self.apply_design_system()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

        self.tab_view.configure(command=self.on_tab_change)

        self.tab_dashboard = self.tab_view.add("Dashboard")
        self.tab_add = self.tab_view.add("Add Product")
        self.tab_inventory = self.tab_view.add("Inventory")
        self.tab_expiring = self.tab_view.add("Expiring Soon")
        self.tab_report = self.tab_view.add("Sales Report")
        self.tab_receive = self.tab_view.add("Receive Inventory")
        self.tab_checkout = self.tab_view.add("Checkout")
        self.tab_templates = self.tab_view.add("Templates")
        self.tab_patients = self.tab_view.add("Patients")
        self.tab_settings = self.tab_view.add("Settings")

        self.templates_list = []
        self.receiving_session = {}
        self.cart = []

        self.setup_dashboard_tab()
        self.setup_add_tab()
        self.setup_inventory_tab()
        self.setup_expiring_tab()
        self.setup_report_tab()
        self.setup_receive_tab()
        self.load_receiving_log()
        self.refresh_product_list()
        self.setup_checkout_tab()
        self.setup_templates_tab()
        self.setup_patients_tab()
        self.setup_settings_tab()

        self.after(500, self._check_startup_expiry)
        self.after(300, self._update_tab_badges)

    def _calculate_alert_counts(self):
        """Calculate low-stock and expiring alert counts."""
        config = barcode_logic.load_config()
        low_stock_threshold = config.get("low_stock_threshold", 5)
        low_stock = database.get_low_stock_products(threshold=low_stock_threshold)

        expiring_30 = 0
        try:
            batches = database.get_expiring_batches()
            today = date.today()
            cutoff = today + timedelta(days=30)
            for exp_date, _row in batches:
                if exp_date <= cutoff:
                    expiring_30 += 1
        except Exception:
            pass

        return len(low_stock), expiring_30

    def _update_tab_badges(self):
        """Refresh tab header badges with alert counts."""
        try:
            low_stock_count, expiring_count = self._calculate_alert_counts()
        except Exception:
            return

        total_alerts = low_stock_count + expiring_count

        try:
            self.tab_view.tab("Inventory").configure(
                text=f"Inventory  [{total_alerts} Alerts]" if total_alerts > 0 else "Inventory"
            )
        except Exception:
            pass

        try:
            self.tab_view.tab("Expiring Soon").configure(
                text=f"Expiring Soon  [{expiring_count}]" if expiring_count > 0 else "Expiring Soon"
            )
        except Exception:
            pass

    def _debug_focus(self, event=None):
        focused = self.focus_get()
        if focused is None:
            print("[DEBUG-FOCUS] focus_get() = None")
        else:
            w_class = focused.winfo_class()
            w_name = str(focused)
            w_master = str(focused.master) if focused.master else "<root>"
            print(f"[DEBUG-FOCUS] widget={w_name} | class={w_class} | master={w_master}")
        return focused

    def _set_window_icon(self):
        """Set the window title bar icon from assets/logo.ico if present."""
        search_names = ["logo.ico", "app.ico", "pharmacy.ico", "icon.ico"]
        base = os.path.dirname(os.path.abspath(__file__))

        for name in search_names:
            for subdir in ("assets", "."):
                candidate = os.path.join(base, subdir, name)
                if os.path.isfile(candidate):
                    try:
                        self.iconbitmap(candidate)
                    except Exception:
                        pass
                    return

        # Fallback: glob for any .ico in assets/
        assets = os.path.join(base, "assets")
        if os.path.isdir(assets):
            for f in os.listdir(assets):
                if f.lower().endswith(".ico"):
                    try:
                        self.iconbitmap(os.path.join(assets, f))
                    except Exception:
                        pass
                    return

    def apply_design_system(self):
        """Global UI/UX Design System styling."""
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        style = ttk.Style(self)
        style.theme_use("default")

        bg_color = "#2D2D2D"
        fg_color = "#FFFFFF"
        selected_bg = "#3B82F6"

        style.configure("Treeview",
                        background=bg_color,
                        foreground=fg_color,
                        fieldbackground=bg_color,
                        borderwidth=0,
                        rowheight=30,
                        font=("Roboto", 11))

        style.map('Treeview', background=[('selected', selected_bg)])

        style.configure("Treeview.Heading",
                        background="#1E1E1E",
                        foreground=fg_color,
                        font=("Roboto", 12, "bold"),
                        relief="flat")
        style.map("Treeview.Heading", background=[('active', '#3B82F6')])

    def on_tab_change(self):
        current_tab = self.tab_view.get()
        if current_tab == "Dashboard":
            self.load_dashboard()
        elif current_tab == "Add Product":
            self.refresh_add_tab_templates()
        elif current_tab == "Inventory":
            self.load_inventory()
        elif current_tab == "Expiring Soon":
            self.load_expiring_items()
        elif current_tab == "Sales Report":
            self.load_sales_report()
        elif current_tab == "Receive Inventory":
            self.load_receiving_log()
            self.refresh_product_list()
        elif current_tab == "Checkout":
            self._refresh_checkout_stock_dropdown()
            self._refresh_receipts_history()
        elif current_tab == "Templates":
            self.load_templates_grid()
        elif current_tab == "Patients":
            pass  # patients tab auto-refreshes on load
        elif current_tab == "Settings":
            self._refresh_ignore_list()

    def _check_startup_expiry(self):
        from datetime import date, timedelta
        config = barcode_logic.load_config()
        alarm_days = config.get("expiry_alarm_days", 50)
        if not isinstance(alarm_days, int) or alarm_days <= 0:
            alarm_days = 50
        ignore_list = config.get("expiry_ignore_list", [])
        if not isinstance(ignore_list, list):
            ignore_list = []

        batches = database.get_expiring_batches(exclude_names=ignore_list)
        today = date.today()
        critical_cutoff = today + timedelta(days=min(7, alarm_days // 5))

        critical_items = []
        warning_items = []
        for exp_date, row in batches:
            if exp_date <= critical_cutoff:
                critical_items.append((exp_date, row))
            elif exp_date <= today + timedelta(days=alarm_days):
                warning_items.append((exp_date, row))

        if critical_items:
            msg_lines = [f"CRITICAL: {len(critical_items)} batch(es) require immediate attention!\n"]
            for exp_date, row in critical_items[:20]:
                name = row[1]
                barcode_val = row[4] or "N/A"
                exp_str = exp_date.strftime("%Y-%m-%d")
                msg_lines.append(f"  - {name} | {barcode_val} | Expires: {exp_str}")
            if len(critical_items) > 20:
                msg_lines.append(f"\n  ...and {len(critical_items) - 20} more.")
            messagebox.showwarning("Critical Expiry Alert", "\n".join(msg_lines))

        if warning_items:
            msg_lines = [f"WARNING: {len(warning_items)} batch(es) expiring within {alarm_days} days.\n"]
            for exp_date, row in warning_items[:20]:
                name = row[1]
                barcode_val = row[4] or "N/A"
                exp_str = exp_date.strftime("%Y-%m-%d")
                msg_lines.append(f"  - {name} | {barcode_val} | Expires: {exp_str}")
            if len(warning_items) > 20:
                msg_lines.append(f"\n  ...and {len(warning_items) - 20} more.")
            messagebox.showinfo("Expiry Warning", "\n".join(msg_lines))

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

    def _notify_inventory_updated(self):
        self.load_inventory()
        self.load_sales_report()
        self.refresh_add_tab_templates()
        self.refresh_product_list()
        self._refresh_checkout_stock_dropdown()
        self._update_tab_badges()

    def setup_dashboard_tab(self):
        setup_dashboard_tab(self)

    def load_dashboard(self):
        load_dashboard(self)


# ── Attach tab methods to PharmacyApp ──────────────────────────────────────
PharmacyApp.setup_add_tab = setup_add_tab
PharmacyApp.refresh_add_tab_templates = refresh_add_tab_templates
PharmacyApp.on_template_selected = on_template_selected
PharmacyApp._resolve_template_vars = _resolve_template_vars
PharmacyApp.save_product = save_product
PharmacyApp._update_bulk_button_state = _update_bulk_button_state
PharmacyApp._open_bulk_add_modal = _open_bulk_add_modal

PharmacyApp.setup_inventory_tab = setup_inventory_tab
PharmacyApp._refresh_expiry_bar = _refresh_expiry_bar
PharmacyApp.load_inventory = load_inventory
PharmacyApp._on_sort_change = _on_sort_change
PharmacyApp._on_inventory_filter_change = _on_inventory_filter_change
PharmacyApp.perform_search = perform_search
PharmacyApp._send_to_checkout = _send_to_checkout
PharmacyApp._edit_batch = _edit_batch
PharmacyApp._delete_batch = _delete_batch
PharmacyApp.open_label_for_selected = open_label_for_selected
PharmacyApp._print_label_for_selected = _print_label_for_selected
PharmacyApp._import_excel = _import_excel
PharmacyApp._export_excel = _export_excel

PharmacyApp.setup_expiring_tab = setup_expiring_tab
PharmacyApp.load_expiring_items = load_expiring_items
PharmacyApp._on_vendor_summary_click = _on_vendor_summary_click

PharmacyApp.setup_report_tab = setup_report_tab
PharmacyApp._on_report_view_switch = _on_report_view_switch
PharmacyApp._build_sales_frame = _build_sales_frame
PharmacyApp.load_sales_report = load_sales_report
PharmacyApp._search_for_refund = _search_for_refund
PharmacyApp._clear_refund_search = _clear_refund_search
PharmacyApp.calculate_custom_date_sales = calculate_custom_date_sales
PharmacyApp.refund_item = refund_item
PharmacyApp.setup_analytics_panel = setup_analytics_panel
PharmacyApp._on_analytics_period_change = _on_analytics_period_change
PharmacyApp.load_analytics = load_analytics
PharmacyApp._export_analytics_csv = _export_analytics_csv
PharmacyApp._export_sales_report_csv = _export_sales_report_csv

PharmacyApp.setup_receive_tab = setup_receive_tab
PharmacyApp._on_vendor_change = _on_vendor_change
PharmacyApp._on_product_change = _on_product_change
PharmacyApp._set_disabled_text = _set_disabled_text
PharmacyApp.refresh_product_list = refresh_product_list
PharmacyApp._add_to_queue = _add_to_queue
PharmacyApp._refresh_po_treeview = _refresh_po_treeview
PharmacyApp._remove_selected_from_queue = _remove_selected_from_queue
PharmacyApp._print_bulk_labels = _print_bulk_labels
PharmacyApp._commit_shipment = _commit_shipment
PharmacyApp._load_shipment_history = _load_shipment_history
PharmacyApp._filter_history_by_date = _filter_history_by_date
PharmacyApp._clear_history_filter = _clear_history_filter
PharmacyApp._sort_history_by_date = _sort_history_by_date
PharmacyApp.load_receiving_log = load_receiving_log
PharmacyApp.calculate_vendor_owed = calculate_vendor_owed
PharmacyApp._print_all_selected_tags = _print_all_selected_tags

PharmacyApp.setup_checkout_tab = setup_checkout_tab
PharmacyApp._refresh_checkout_patients = _refresh_checkout_patients
PharmacyApp._on_patient_select = _on_patient_select
PharmacyApp._refresh_checkout_stock_dropdown = _refresh_checkout_stock_dropdown
PharmacyApp._on_checkout_product_change = _on_checkout_product_change
PharmacyApp._checkout_add_item = _checkout_add_item
PharmacyApp._checkout_remove_item = _checkout_remove_item
PharmacyApp._checkout_clear_cart = _checkout_clear_cart
PharmacyApp._refresh_cart_treeview = _refresh_cart_treeview
PharmacyApp._checkout_update_change = _checkout_update_change
PharmacyApp._checkout_confirm = _checkout_confirm
PharmacyApp._refresh_receipts_history = _refresh_receipts_history
PharmacyApp._on_receipt_double_click = _on_receipt_double_click
PharmacyApp._print_receipt = _print_receipt

PharmacyApp.setup_templates_tab = setup_templates_tab
PharmacyApp.load_templates_grid = load_templates_grid
PharmacyApp.on_template_tree_select = on_template_tree_select
PharmacyApp.add_template_gui = add_template_gui
PharmacyApp.update_template_gui = update_template_gui
PharmacyApp.delete_template_gui = delete_template_gui

PharmacyApp.setup_settings_tab = setup_settings_tab
PharmacyApp.setup_patients_tab = setup_patients_tab
PharmacyApp.browse_db_path = browse_db_path
PharmacyApp._on_role_change = _on_role_change
PharmacyApp._update_role_controls = _update_role_controls
PharmacyApp.backup_database_gui = backup_database_gui
PharmacyApp._add_ignore_product = _add_ignore_product
PharmacyApp._remove_ignore_product = _remove_ignore_product
PharmacyApp._refresh_ignore_list = _refresh_ignore_list
PharmacyApp.save_settings = save_settings
PharmacyApp._open_audit_log_viewer = _open_audit_log_viewer
