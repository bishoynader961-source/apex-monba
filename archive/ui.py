import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import os
import re
import json
import logging
from datetime import datetime, date, timedelta
from PIL import Image, ImageTk
import tempfile
from collections import defaultdict
import i18n
import database
import barcode_logic
from barcode_listener import BarcodeListener

import database
import barcode_logic
import audit_log
from path_utils import get_resource_path

log = logging.getLogger("ui")

from label_engine.canvas_core import LabelCanvas, LabelElement, draw_elements
from label_engine.export import save_label, load_label, export_to_png, print_label, TEMPLATE_PATH

from ui_helpers import _extract_first_var, _extract_all_vars
from ui_navigation import create_navigation_system

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
    _refresh_po_treeview, _remove_selected_from_queue, _update_invoice_total,
    _print_bulk_labels, _commit_shipment,
    _load_shipment_history, _filter_history_by_date,
    _clear_history_filter, _sort_history_by_date,
    load_receiving_log, calculate_vendor_owed, _print_all_selected_tags,
    _run_ai_extract, _ai_populate_review, _ai_handle_error,
    _ai_add_selected_to_queue, _ai_add_all_to_queue, _ai_clear_review,
    _run_smart_parse,
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
    backup_database_gui, _add_ignore_product,
    _remove_ignore_product, _refresh_ignore_list,
    save_settings, _open_audit_log_viewer,
    _on_language_change,
    _test_pg_connection, _build_pg_url, _load_pg_config,
    _load_email_config, _send_test_email, _save_email_config, _reset_email_ui,
    _refresh_cascade_badge,
)

from ui_patients_tab import (
    setup_patients_tab,
)


class PharmacyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(i18n.t("app_title"))
        self.geometry("1000x700")

        self._set_window_icon()

        # Initialize centralized async task manager with Tkinter root
        from async_ui import init_async_ui
        init_async_ui(self)

        self.apply_design_system()

        # Region-aware money formatting (single source of truth: LocalizationManager)
        import localization_manager
        from currency import CurrencyFormatter
        localization_manager.init(app_root=self)
        self.currency = CurrencyFormatter()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Navigation Drawer + Content Container ───────────────────────────
        self.nav_drawer, self.tab_view, self.nav_container = create_navigation_system(
            self, i18n_module=i18n
        )
        self.nav_container.grid(row=0, column=0, sticky="nsew")

        self.tab_view.configure(command=self.on_tab_change)

        self.tab_dashboard = self.tab_view.add(i18n.t("dashboard"))
        self.tab_add = self.tab_view.add(i18n.t("add_product"))
        self.tab_inventory = self.tab_view.add(i18n.t("inventory"))
        self.tab_expiring = self.tab_view.add(i18n.t("expiring_soon"))
        self.tab_report = self.tab_view.add(i18n.t("sales_report"))
        self.tab_receive = self.tab_view.add(i18n.t("receive_inventory"))
        self.tab_checkout = self.tab_view.add(i18n.t("checkout"))
        self.tab_templates = self.tab_view.add(i18n.t("templates"))
        self.tab_patients = self.tab_view.add(i18n.t("patients"))
        self.tab_settings = self.tab_view.add(i18n.t("settings"))

        # Show dashboard as default tab
        self.tab_view._switch_to(i18n.t("dashboard"))

        self.templates_list = []
        self.receiving_session = {}

        self.setup_dashboard_tab()

        # Persistent dashboard banner (survives setup_dashboard_tab refresh).
        # Row 0 is reserved; content was shifted to rows 1–4 by setup_dashboard_tab.
        self.dashboard_banner_frame = ctk.CTkFrame(
            self.tab_dashboard, fg_color="transparent")
        self.dashboard_banner_frame.grid(
            row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        from ui_banner import RegionBanner
        self.region_banner = RegionBanner(self.dashboard_banner_frame, self)
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

        # ── Global barcode scanner listener ──────────────────────────
        self._barcode_listener = BarcodeListener(self, on_scan=self._handle_global_scan)
        self._barcode_listener.start()

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
        """Refresh navigation drawer badges with alert counts."""
        try:
            low_stock_count, expiring_count = self._calculate_alert_counts()
        except Exception:
            return

        total_alerts = low_stock_count + expiring_count

        try:
            inv_label = i18n.t("inventory")
            badge_text = str(total_alerts) if total_alerts > 0 else ""
            badge_status = "error" if total_alerts > 0 else "neutral"
            self.nav_drawer.update_badge(inv_label, badge_text, badge_status)
        except Exception:
            pass

        try:
            exp_label = i18n.t("expiring_soon")
            badge_text = str(expiring_count) if expiring_count > 0 else ""
            badge_status = "warning" if expiring_count > 0 else "neutral"
            self.nav_drawer.update_badge(exp_label, badge_text, badge_status)
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
        if current_tab == i18n.t("dashboard"):
            self.load_dashboard()
        elif current_tab == i18n.t("add_product"):
            self.refresh_add_tab_templates()
        elif current_tab == i18n.t("inventory"):
            self.load_inventory()
        elif current_tab == i18n.t("expiring_soon"):
            self.load_expiring_items()
        elif current_tab == i18n.t("sales_report"):
            self.load_sales_report()
        elif current_tab == i18n.t("receive_inventory"):
            self.load_receiving_log()
            self.refresh_product_list()
        elif current_tab == i18n.t("checkout"):
            self._refresh_cart_treeview()
            self._refresh_checkout_stock_dropdown()
            self._refresh_receipts_history()
            if hasattr(self, "checkout_cascade_badge"):
                self._refresh_cascade_badge()
        elif current_tab == i18n.t("templates"):
            self.load_templates_grid()
        elif current_tab == i18n.t("patients"):
            pass  # patients tab auto-refreshes on load
        elif current_tab == i18n.t("settings"):
            self._refresh_ignore_list()
            self._refresh_cascade_badge()
            self._notify_config_updated()

    def _handle_global_scan(self, barcode: str) -> None:
        """Route a scanned barcode to the appropriate tab handler."""
        active_tab = self.tab_view.get()

        if active_tab == i18n.t("checkout"):
            # Checkout/POS: add item to cart
            from ui_checkout_tab import _pos_scan_barcode
            _pos_scan_barcode(self, barcode)

        elif active_tab == i18n.t("inventory"):
            # Inventory: populate search field and filter
            if hasattr(self, "search_entry"):
                self.search_entry.delete(0, "end")
                self.search_entry.insert(0, barcode)
                self.perform_search()

        elif active_tab == i18n.t("receive_inventory"):
            # Receiving: auto-fill vendor from scanned product
            product = database.get_product_by_internal_barcode(barcode)
            if not product:
                product = database.get_product_by_barcode(barcode)
            if product and hasattr(self, "vendor_entry"):
                vendor_name = product[5] if len(product) > 5 else ""
                if vendor_name and vendor_name != "N/A":
                    self.vendor_entry.delete(0, "end")
                    self.vendor_entry.insert(0, vendor_name)

        else:
            # Default: search inventory regardless of active tab
            product = database.get_product_by_internal_barcode(barcode)
            if not product:
                product = database.get_product_by_barcode(barcode)
            if product:
                messagebox.showinfo(
                    i18n.t("info"),
                    f"{product[1]}\nBarcode: {product[3]}\nPrice: ${product[2]:.2f}"
                )

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

    def _notify_config_updated(self):
        """Broadcast after config.json changes (tax rate, store details, receipt notes).

        Modeled on _notify_inventory_updated but additionally refreshes the checkout
        balance panel so the live POS re-reads tax_rate without a restart.
        """
        self._notify_inventory_updated()
        if hasattr(self, "tab_checkout"):
            self._refresh_cart_treeview()
            self._checkout_update_change()
        self.load_dashboard()

    def _new_prescription(self):
        """Navigate to Clinical Workflow tab and open the prescription wizard."""
        try:
            target = i18n.t("clinical_workflow_title")
            self.tab_view.set(target)
            if self.tab_view._command:
                self.tab_view._command()
            if hasattr(self, "clinical_workflow_frame") and \
                    hasattr(self.clinical_workflow_frame, "_open_wizard"):
                self.clinical_workflow_frame._open_wizard()
            else:
                messagebox.showinfo("Info",
                                    "Clinical Workflow not yet initialized.",
                                    parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            log.error("New prescription failed: %s", e)

    def _open_database(self):
        """Navigate to the Settings tab and focus the database path section."""
        try:
            self.tab_view.set(i18n.t("settings"))
            if self.tab_view._command:
                self.tab_view._command()
            if hasattr(self, "browse_db_path"):
                self.browse_db_path()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            log.error("Open database settings failed: %s", e)

    def _save_all(self):
        """Save all open tab state and broadcast config update."""
        try:
            if hasattr(self, "save_settings"):
                self.save_settings()
        except Exception as e:
            log.warning("Save settings failed: %s", e)
        self._notify_config_updated()

    def _open_preferences(self):
        """Navigate to the Settings tab and select the preferences section."""
        try:
            self.tab_view.set(i18n.t("settings"))
            if self.tab_view._command:
                self.tab_view._command()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            log.error("Open preferences failed: %s", e)

    def _show_about(self):
        """Show an About dialog with app version, build date, and pharmacy info."""
        import os as _os
        from datetime import datetime as _dt

        version = _os.environ.get("PHARMACYPRO_VERSION", "1.0.0")
        build_date = _dt.now().strftime("%Y-%m-%d")

        config = barcode_logic.load_config()
        pharmacy_name = config.get("pharmacy_name", "My Pharmacy")

        about_win = ctk.CTkToplevel(self)
        about_win.title(i18n.t("about_dialog_title"))
        about_win.resizable(False, False)
        about_win.transient(self)
        about_win.grab_set()

        w, h = 400, 300
        root = self.winfo_toplevel()
        try:
            px = root.winfo_x() + (root.winfo_width() - w) // 2
            py = root.winfo_y() + (root.winfo_height() - h) // 2
            about_win.geometry(f"{w}x{h}+{px}+{py}")
        except Exception:
            about_win.geometry(f"{w}x{h}")

        ctk.CTkLabel(about_win, text=pharmacy_name,
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(30, 8))
        ctk.CTkLabel(about_win, text=f"Pharmacy Management System\n"
                                    f"{i18n.t('version')}: {version}\n"
                                    f"{i18n.t('build_date')}: {build_date}",
                       font=ctk.CTkFont(size=12), justify="center").pack(pady=8)

        ctk.CTkButton(about_win, text=i18n.t("cancel"), width=80,
                      command=about_win.destroy).pack(pady=(0, 30))

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
PharmacyApp._update_invoice_total = _update_invoice_total
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
PharmacyApp._run_ai_extract = _run_ai_extract
PharmacyApp._ai_populate_review = _ai_populate_review
PharmacyApp._ai_handle_error = _ai_handle_error
PharmacyApp._ai_add_selected_to_queue = _ai_add_selected_to_queue
PharmacyApp._ai_add_all_to_queue = _ai_add_all_to_queue
PharmacyApp._ai_clear_review = _ai_clear_review
PharmacyApp._run_smart_parse = _run_smart_parse

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
PharmacyApp.backup_database_gui = backup_database_gui
PharmacyApp._add_ignore_product = _add_ignore_product
PharmacyApp._remove_ignore_product = _remove_ignore_product
PharmacyApp._refresh_ignore_list = _refresh_ignore_list
PharmacyApp.save_settings = save_settings
PharmacyApp._open_audit_log_viewer = _open_audit_log_viewer
PharmacyApp._on_language_change = _on_language_change
PharmacyApp._test_pg_connection = _test_pg_connection
PharmacyApp._build_pg_url = _build_pg_url
PharmacyApp._load_pg_config = _load_pg_config
PharmacyApp._load_email_config = _load_email_config
PharmacyApp._send_test_email = _send_test_email
PharmacyApp._save_email_config = _save_email_config
PharmacyApp._reset_email_ui = _reset_email_ui
PharmacyApp._refresh_cascade_badge = _refresh_cascade_badge
