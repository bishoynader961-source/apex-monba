import sys
import os
import logging
import subprocess
from path_utils import get_resource_path

import database
import auth_session
import authz
import audit_log
import ui_auth
import ui_admin_roles

_LOG = logging.getLogger("main_app")

_LABEL_ENGINE = get_resource_path(os.path.join("label_engine", "main.py"))


def _find_python_executable():
    """Detect the correct Python executable, preferring the project venv."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_candidates = [
        os.path.join(base_dir, "venv", "Scripts", "python.exe"),
        os.path.join(os.path.dirname(base_dir), "venv", "Scripts", "python.exe"),
        os.path.join(base_dir, ".venv", "Scripts", "python.exe"),
    ]
    for candidate in venv_candidates:
        if os.path.exists(candidate):
            return candidate

    if getattr(sys, 'frozen', False):
        import shutil
        for name in ("python", "python3", "python.exe", "python3.exe"):
            found = shutil.which(name)
            if found:
                return found

    return sys.executable


def open_label_engine(product_id: str, barcode_value: str,
                      product_name: str = "", product_price: str = "",
                      expiry: str = "", manufacture: str = "",
                      show_name: bool = True, show_price: bool = True,
                      show_expiry: bool = True, show_barcode_text: bool = True):
    python_exe = _find_python_executable()
    cmd = [
        python_exe, _LABEL_ENGINE,
        "--id", product_id,
        "--barcode", barcode_value,
        "--name", product_name,
        "--price", product_price,
        "--show-name", str(show_name),
        "--show-price", str(show_price),
        "--show-expiry", str(show_expiry),
        "--show-barcode-text", str(show_barcode_text),
    ]
    if expiry:
        cmd.extend(["--expiry", expiry])
    if manufacture:
        cmd.extend(["--manufacture", manufacture])
    subprocess.Popen(cmd)


def _wire_rx_extensions():
    """Monkey-patch the existing PharmacyApp to add Enterprise Settings,
    POS Terminal, Rx Processing, EPCS Workflow, Status Dashboard, Clinical
    Workflow, Quick-SIG, Enterprise POS Retail, and Bulk Import tabs
    without modifying ui.py or ui_navigation.py."""
    import i18n
    import ui_navigation
    import ui

    PharmacyApp = ui.PharmacyApp
    _orig_init = PharmacyApp.__init__

    # ── Nav icons for all tabs (including pre-existing ones) ──
    ui_navigation._NAV_ICONS.setdefault("enterprise_settings", "🏢")
    ui_navigation._NAV_ICONS.setdefault("pos_terminal", "🔢")
    ui_navigation._NAV_ICONS.setdefault("rx_processing", "💊")
    ui_navigation._NAV_ICONS.setdefault("epcs_workflow", "📝")
    ui_navigation._NAV_ICONS.setdefault("status_dashboard", "📊")
    ui_navigation._NAV_ICONS.setdefault("pos_retail_title", "🛒")
    ui_navigation._NAV_ICONS.setdefault("clinical_workflow_title", "🏥")
    ui_navigation._NAV_ICONS.setdefault("quick_sig_title", "✒️")
    ui_navigation._NAV_ICONS.setdefault("bulk_import_title", "📥")
    ui_navigation._NAV_ICONS.setdefault("inventory_mgmt_title", "📋")

    # ── Backend initialization ──
    try:
        from rx_database import init_rx_tables
        init_rx_tables()
    except Exception as e:
        _LOG.warning("Rx table init failed: %s", e)

    try:
        from rx_migrations import run_rx_migrations
        applied = run_rx_migrations()
        if applied:
            _LOG.info("Rx migrations applied: %s", applied)
    except Exception as e:
        _LOG.warning("Rx migrations failed: %s", e)

    try:
        from ndc_dictionary import init_ndc_dictionary
        init_ndc_dictionary()
    except Exception as e:
        _LOG.warning("NDC dictionary init failed: %s", e)

    # ── Import all extension modules ──
    from ui_enterprise_settings import setup_enterprise_settings_tab
    from ui_pos_terminal import setup_pos_terminal_tab
    from ui_rx_processing import setup_rx_processing_tab
    from ui_epcs_workflow import setup_epcs_workflow_tab
    from ui_status_dashboard import setup_status_dashboard_tab
    from ui_pos_retail import setup_pos_retail_tab
    from ui_clinical_workflow import setup_clinical_workflow_tab
    from ui_enterprise_navigation import setup_enterprise_navigation
    from quick_sig import setup_quick_sig_tab
    from ui_inventory_management import setup_inventory_management_tab
    from ui_bulk_import import setup_bulk_import_tab

    def _patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)

        # ── New Enterprise Tabs ──
        self.tab_status_dashboard = self.tab_view.add(i18n.t("status_dashboard_title"))
        self.tab_pos_retail = self.tab_view.add(i18n.t("pos_retail_title"))
        self.tab_clinical = self.tab_view.add(i18n.t("clinical_workflow_title"))
        self.tab_quick_sig = self.tab_view.add(i18n.t("quick_sig_title"))
        self.tab_bulk_import = self.tab_view.add(i18n.t("bulk_import_title"))
        self.tab_inventory_mgmt = self.tab_view.add(i18n.t("inventory_mgmt_title"))

        # ── Existing Enterprise Tabs ──
        self.tab_enterprise = self.tab_view.add(i18n.t("enterprise_settings"))
        self.tab_pos = self.tab_view.add(i18n.t("pos_terminal"))
        self.tab_rx_processing = self.tab_view.add(i18n.t("rx_processing"))
        self.tab_epcs_workflow = self.tab_view.add(i18n.t("epcs_workflow"))

        # ── Setup tab content ──
        setup_status_dashboard_tab(self)
        setup_pos_retail_tab(self)
        setup_clinical_workflow_tab(self)
        setup_quick_sig_tab(self)
        setup_enterprise_settings_tab(self)
        setup_pos_terminal_tab(self)
        setup_rx_processing_tab(self)
        setup_epcs_workflow_tab(self)
        setup_inventory_management_tab(self)
        setup_bulk_import_tab(self)

        # ── Enterprise navigation (menu bar + icon toolbar) ──
        setup_enterprise_navigation(self)

        # ── Global F12 binding ──
        def _on_f12(event=None):
            active_tab = self.tab_view.get()
            if active_tab in (i18n.t("status_dashboard_title"), i18n.t("clinical_workflow_title")):
                if hasattr(self, "pos_retail_frame") and hasattr(self.pos_retail_frame, "_process_payment"):
                    self.pos_retail_frame._process_payment()
        self.bind("<F12>", _on_f12)

    PharmacyApp.__init__ = _patched_init

    _orig_on_tab_change = PharmacyApp.on_tab_change

    def _patched_on_tab_change(self):
        _orig_on_tab_change(self)
        current = self.tab_view.get()
        if current == i18n.t("enterprise_settings"):
            if hasattr(self, "enterprise_settings_frame"):
                self.enterprise_settings_frame.refresh()
        elif current == i18n.t("pos_terminal"):
            if hasattr(self, "pos_terminal_frame"):
                self.pos_terminal_frame.refresh()
        elif current == i18n.t("rx_processing"):
            if hasattr(self, "rx_processing_frame"):
                self.rx_processing_frame.refresh()
        elif current == i18n.t("epcs_workflow"):
            if hasattr(self, "epcs_workflow_frame"):
                self.epcs_workflow_frame.refresh()
        elif current == i18n.t("status_dashboard_title"):
            if hasattr(self, "status_dashboard_frame"):
                self.status_dashboard_frame.refresh()
        elif current == i18n.t("clinical_workflow_title"):
            if hasattr(self, "clinical_workflow_frame"):
                self.clinical_workflow_frame._refresh()
        elif current == i18n.t("inventory_mgmt_title"):
            if hasattr(self, "inventory_mgmt_frame"):
                self.inventory_mgmt_frame.refresh()
        elif current == i18n.t("bulk_import_title"):
            if hasattr(self, "bulk_import_frame"):
                self.bulk_import_frame.refresh()

    PharmacyApp.on_tab_change = _patched_on_tab_change


def _safe_grab(win):
    """grab_set() can throw on a withdrawn/unrealized parent or headless CI.

    Swallowing keeps the modal functional without crashing the gate (§7.1).
    """
    try:
        win.grab_set()
    except Exception:
        pass


def run_startup_gate(app) -> bool:
    """Blocking pre-mainloop gate (§7.1).

    Returns True only when an Owner session is authenticated AND (when
    applicable) the bootstrap override secret has been rotated. The gate
    runs inside ``PharmacyApp.__init__`` — before ``mainloop()`` — so it is
    synchronous via ``wait_window()`` per modal; it must never call
    ``after()`` or ``mainloop()``.

    Returns False (process should exit) if the operator refuses owner
    creation past the retry cap.
    """
    retries = 0
    while database.count_users() == 0:
        ui_auth.maybe_show_create_owner(app)      # blocks until owner exists / exit
        retries += 1
        if retries > 10:                           # CI / abort safety
            return False
    uid = None
    while uid is None:
        uid = ui_auth.show_login(app)              # dismissed => re-prompt (no skip)
    auth_session.login(uid)
    # NOTE: the login audit is emitted by LoginDialog._on_submit (and again by
    # force_relogin on re-auth). Do NOT log here to avoid a duplicate row.

    # G8 (Force Bootstrap Secret Rotation): if the Owner override still uses the
    # shipped bootstrap secret, block the UI until the Owner rotates it.
    if database.is_owner_override_default():
        ui_auth.force_rotate_owner_override(app)
    return True


def _wire_rbac():
    """Monkey-patch PharmacyApp.__init__ to enforce the RBAC startup flow:
    first-run Owner creation (if no users exist) and a login gate that
    establishes the in-memory session. Also binds Ctrl+Shift+A so an Owner can
    re-open the Roles & Permissions panel.

    Mirrors the monkey-patch approach used by ``_wire_rx_extensions``; this must
    run after that function so the login gate executes once all tabs exist.
    """
    from ui import PharmacyApp

    _orig_init = PharmacyApp.__init__

    def _rbac_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)

        # Idempotent schema/seed (creates RBAC tables if missing).
        database.init_db()

        # §7.1: realize the root, then hide it so the half-built UI cannot be
        # click-through behind the blocking modals.
        self.update_idletasks()
        self.withdraw()

        if not run_startup_gate(self):
            self.destroy()
            sys.exit(1)

        # Gate succeeded: reveal the fully authenticated UI.
        self.deiconify()
        self.lift()

        # G9: start the session expiry timer (auto-logout on idle).
        auth_session.start_session_timer(self, on_expire=lambda: ui_auth.force_relogin(self))

        # RBAC nav gating (D3/D8): hide tabs whose required permission the
        # authenticated user lacks. Re-applied after every re-login.
        _apply_nav_permissions(self, auth_session.current_user_id())

        # Owner shortcut to re-open the Roles & Permissions panel.
        def _on_ctrl_shift_a(event=None):
            ui_admin_roles.open_admin_roles(self)

        self.bind("<Control-Shift-A>", _on_ctrl_shift_a)

    PharmacyApp.__init__ = _rbac_init


def _apply_nav_permissions(app, uid) -> None:
    """Hide navigation buttons the current user is not permitted to open.

    Mirrors the handler-level gates: hiding a button stops clicks, but
    ``tab_view.set()`` (e.g. the region banner) is still blocked by the
    handler-side ``require_permission`` checks.
    """
    try:
        import i18n
        import authz
        from ui_navigation import NAV_PERMISSIONS
    except Exception:
        return
    if uid is None or not hasattr(app, "nav_drawer"):
        return
    for i18n_key, feature in NAV_PERMISSIONS.items():
        label = i18n.t(i18n_key)
        allowed = authz.check_permission(uid, feature)
        app.nav_drawer.set_button_visible(label, allowed)


def _on_relogin(app) -> None:
    """Re-apply RBAC state after a forced re-login (idle timeout / Owner rotate)."""
    _apply_nav_permissions(app, auth_session.current_user_id())



def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Ensure locales are loaded before any widget (and its tooltip) is built,
    # so i18n.t() resolves real strings rather than falling back to keys.
    try:
        import i18n
        i18n.init()
    except Exception:
        pass

    # Import main BEFORE _wire_rx_extensions to prevent label_engine/export.py
    # from polluting sys.path[0] (it inserts archive/label_engine/ at position 0,
    # which would shadow archive/main.py with label_engine/main.py).
    from main import main as pharmacy_main
    
    _wire_rx_extensions()
    _wire_rbac()
    pharmacy_main()


if __name__ == "__main__":
    main()
