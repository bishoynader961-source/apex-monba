"""
ui_enterprise_navigation.py — Top menu bar for PharmacyPro Enterprise.

Provides:
  - EnterpriseMenuBar: tkinter.Menu-based top menu bar (File, Edit, View, Tools, Help)
  - setup_enterprise_navigation(self): Wires the menu bar into the PharmacyApp root.

Integration:
  Called from main_app.py:_wire_rx_extensions() after the original __init__.
  The menu bar is attached via root.config(menu=...). Navigation is provided
  by the left NavigationDrawer; the redundant IconToolbar was removed in
  Phase 18 (Step 13).
"""
import logging
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import i18n
from ui_navigation import COLOR_SIDEBAR_BG, COLOR_ACCENT, COLOR_TEXT_PRIMARY

log = logging.getLogger("ui_enterprise_navigation")


def _open_admin_roles(app):
    """Lazy entry point for the Owner RBAC panel (gated inside open_admin_roles)."""
    import ui_admin_roles
    ui_admin_roles.open_admin_roles(app)


def _open_audit_log(app):
    """Lazy entry point for the audit-log viewer (gated by ``audit.view``)."""
    import auth_session
    import authz
    import audit_log
    import customtkinter as ctk

    def _build():
        if not authz.check_permission(auth_session.current_user_id(), "audit.view"):
            authz.access_denied("audit.view")
            return
        win = ctk.CTkToplevel(app)
        win.title("Audit Log")
        win.geometry("760x500")
        txt = ctk.CTkTextbox(win, wrap="none")
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            for timestamp, action, user_pin, details in audit_log.get_logs(limit=200):
                txt.insert("end", f"[{timestamp}] {action} (user={user_pin}): {details}\n")
        except Exception as e:  # noqa: BLE001
            txt.insert("end", f"Failed to load audit logs: {e}")
        txt.configure(state="disabled")

    # Gate via the require_permission decorator (Access Denied if lacking).
    authz.require_permission("audit.view")(_build)()


def _on_logout(app):
    """Delegate to ui_auth.force_relogin."""
    import ui_auth
    ui_auth.force_relogin(app)


class EnterpriseMenuBar:
    """Top-level application menu bar using tkinter.Menu.

    Menus: File, Edit, View, Tools, Help
    Commands delegate to PharmacyApp methods where available.
    """

    def __init__(self, root: tk.Misc, app=None):
        self._root = root
        self._app = app
        self._menu = tk.Menu(root, tearoff=0)

    def build(self) -> tk.Menu:
        app = self._app
        menu = self._menu

        # ── File ──
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(
            label=i18n.t("nav_menu_new"),
            command=lambda: app._new_prescription() if app and hasattr(app, "_new_prescription") else messagebox.showinfo("Not Available", "This feature is not available.", parent=self._root),
        )
        file_menu.add_command(
            label=i18n.t("nav_menu_open"),
            command=lambda: app._open_database() if app and hasattr(app, "_open_database") else messagebox.showinfo("Not Available", "This feature is not available.", parent=self._root),
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Logout",
            command=lambda: _on_logout(app) if app else None,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label=i18n.t("nav_menu_exit"),
            command=lambda: app.destroy() if app else self._root.destroy(),
        )
        menu.add_cascade(label=i18n.t("nav_menu_file"), menu=file_menu)

        # ── Edit ──
        edit_menu = tk.Menu(menu, tearoff=0)
        edit_menu.add_command(
            label=i18n.t("nav_menu_save"),
            command=lambda: app._save_all() if app and hasattr(app, "_save_all") else messagebox.showinfo("Not Available", "This feature is not available.", parent=self._root),
        )
        edit_menu.add_command(
            label=i18n.t("nav_menu_preferences"),
            command=lambda: app._open_preferences() if app and hasattr(app, "_open_preferences") else messagebox.showinfo("Not Available", "This feature is not available.", parent=self._root),
        )
        menu.add_cascade(label=i18n.t("nav_menu_edit"), menu=edit_menu)

        # ── View ──
        view_menu = tk.Menu(menu, tearoff=0)
        view_menu.add_command(
            label=i18n.t("toolbar_dashboard"),
            command=lambda: app.tab_view.set(i18n.t("dashboard")) if app else None,
        )
        view_menu.add_command(
            label=i18n.t("toolbar_pos"),
            command=lambda: app.tab_view.set(i18n.t("checkout")) if app else None,
        )
        view_menu.add_command(
            label=i18n.t("toolbar_clinical"),
            command=lambda: app.tab_view.set(i18n.t("clinical_workflow_title")) if app else None,
        )
        menu.add_cascade(label=i18n.t("nav_menu_view"), menu=view_menu)

        # ── Tools ──
        tools_menu = tk.Menu(menu, tearoff=0)
        tools_menu.add_command(
            label=i18n.t("bulk_import_title"),
            command=lambda: app.tab_view.set(i18n.t("bulk_import_title")) if app else None,
        )
        tools_menu.add_command(
            label=i18n.t("quick_sig_title"),
            command=lambda: app.tab_view.set(i18n.t("quick_sig_title")) if app else None,
        )
        tools_menu.add_command(
            label=i18n.t("toolbar_reports"),
            command=lambda: app.tab_view.set(i18n.t("sales_report")) if app else None,
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Roles & Permissions",
            command=lambda: _open_admin_roles(app) if app else None,
        )
        tools_menu.add_command(
            label="Audit Log",
            command=lambda: _open_audit_log(app) if app else None,
        )
        menu.add_cascade(label=i18n.t("nav_menu_tools"), menu=tools_menu)

        # ── Help ──
        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(
            label=i18n.t("nav_menu_about"),
            command=lambda: app._show_about() if app and hasattr(app, "_show_about") else messagebox.showinfo("Not Available", "This feature is not available.", parent=self._root),
        )
        menu.add_cascade(label=i18n.t("nav_menu_help"), menu=help_menu)

        return menu


def setup_enterprise_navigation(self):
    """Create the top menu bar, wiring it into the root layout.

    Called from main_app.py after __init__ has set up nav_container.
    - Menu bar is attached to root via config(menu=...)
    - The redundant IconToolbar was removed in Phase 18 (Step 13); navigation
      is provided by the left NavigationDrawer and the View menu below.
    """
    # ── Menu Bar ──
    menubar = EnterpriseMenuBar(self, app=self).build()
    self.config(menu=menubar)
    log.info("Enterprise navigation (menu bar) wired successfully")
