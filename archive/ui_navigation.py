"""
ui_navigation.py — Left-side navigation drawer for PharmacyPro.

Replaces the CTkTabview's visual tab bar with a sleek, collapsible navigation drawer.
The TabViewCompat shim preserves the full CTkTabview API (add, tab, get, set, configure)
so existing code in ui.py and ui_tab_*.py modules continues to work unchanged.

Components:
    - NavigationDrawer: Styled left-side button panel with badge support
    - TabViewCompat: Full API-level replacement for ctk.CTkTabview
    - CompactCard: Reusable card widget for modern layouts
    - BadgeLabel: Status badge widget with configurable colors

Usage in ui.py:
    from ui_navigation import create_navigation_system

    nav_drawer, tab_view_compat, content_area = create_navigation_system(self)
    self.tab_view = tab_view_compat  # Transparent drop-in replacement
"""
import customtkinter as ctk
from typing import Optional, Callable, Dict

import i18n

# ── Design System Colors ─────────────────────────────────────────────────

COLOR_SIDEBAR_BG = "#1e1e2e"
COLOR_SIDEBAR_HOVER = "#333344"
COLOR_SIDEBAR_SELECTED = "#3b82f6"
COLOR_CARD_BG = "#2d2d3a"
COLOR_CARD_BORDER = "#3a3a4a"
COLOR_ACCENT = "#3b82f6"
COLOR_SUCCESS = "#10b981"
COLOR_WARNING = "#f59e0b"
COLOR_ERROR = "#ef4444"
COLOR_TEXT_PRIMARY = "#f0f0f0"
COLOR_TEXT_SECONDARY = "#a0a0a0"
COLOR_TEXT_BADGE = "#ffffff"


# ── Badge Label ─────────────────────────────────────────────────────────

class BadgeLabel(ctk.CTkLabel):
    """Compact status badge with configurable color themes."""

    def __init__(self, parent, text="", status="info", **kwargs):
        colors = {
            "success": COLOR_SUCCESS,
            "warning": COLOR_WARNING,
            "error": COLOR_ERROR,
            "info": COLOR_ACCENT,
            "neutral": COLOR_TEXT_SECONDARY,
        }
        text_color = COLOR_TEXT_BADGE if status not in ("info", "neutral") else COLOR_TEXT_SECONDARY
        bg = colors.get(status, COLOR_ACCENT)
        super().__init__(
            parent, text=text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=text_color,
            fg_color=bg,
            corner_radius=10,
            width=24,
            height=20,
        )


# ── Compact Card ─────────────────────────────────────────────────────────

class CompactCard(ctk.CTkFrame):
    """Reusable content card with title header and optional badge."""

    def __init__(self, parent, title="", badge_text="", badge_status="info", **kwargs):
        super().__init__(parent, fg_color=COLOR_CARD_BG, corner_radius=10, **kwargs)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        if badge_text:
            BadgeLabel(header, text=badge_text, status=badge_status).grid(
                row=0, column=1, sticky="e")

        self.content_row = 1
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

    def add_content(self, row, column=0, widget=None, **grid_kwargs):
        """Add content widget at the specified grid row."""
        if widget:
            widget.grid(row=row, column=column, **grid_kwargs)
        self.content_row = max(self.content_row, row + 1)

    def content_container(self):
        """Return a transparent sub-frame for placing content."""
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        return frame


# ── Navigation Drawer ───────────────────────────────────────────────────

class NavigationDrawer(ctk.CTkFrame):
    """Left-side navigation drawer with buttons and badge support."""

    def __init__(self, parent, button_data: list, command: Callable = None, **kwargs):
        super().__init__(parent, fg_color=COLOR_SIDEBAR_BG, corner_radius=0, **kwargs)
        self._command = command
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._current_tab: Optional[str] = None
        self._badge_labels: Dict[str, BadgeLabel] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, pady=(20, 24), padx=12, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame, text=i18n.t("app_brand_name"),
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            header_frame, text=i18n.t("app_subtitle"),
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=1, column=0, sticky="ew")

        # Separator
        ctk.CTkFrame(self, fg_color=COLOR_CARD_BORDER, height=1).grid(
            row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        # Button container (scrollable so all entries are reachable on short windows)
        self._btn_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._btn_container.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._btn_container.grid_columnconfigure(0, weight=1)

        self._row_counter = 0
        for key, name, icon in button_data:
            self._add_button(name, icon, nav_key=key)

        # Spacer at bottom
        ctk.CTkFrame(self, fg_color="transparent").grid(
            row=99, column=0, pady=(16, 0))

        # Persistent region/currency indicator (row 98, before spacer).
        # Lives on the NavigationDrawer so it survives dashboard refreshes.
        self._region_indicator = ctk.CTkLabel(
            self, text="", fg_color="transparent",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w", height=30,
        )
        self._region_indicator.grid(row=98, column=0, padx=12, pady=(8, 0), sticky="ew")
        self._region_indicator.grid_columnconfigure(0, weight=1)
        self._refresh_region_indicator()

        # Interactive notification banner (row 97, survives dashboard refresh).
        # Only created if there is a pending/un-dismissed region to show.
        self._region_banner = None
        self._create_region_banner()

    def _add_button(self, name: str, icon: str = "", nav_key: str = None):
        row = self._row_counter
        self._row_counter += 1

        btn_frame = ctk.CTkFrame(self._btn_container, fg_color="transparent")
        btn_frame.grid(row=row, column=0, pady=2, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)

        text = f"  {icon}  {name}" if icon else f"  {name}"
        btn = ctk.CTkButton(
            btn_frame, text=text,
            command=lambda n=name: self._on_click(n),
            fg_color="transparent",
            hover_color=COLOR_SIDEBAR_HOVER,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
            height=38,
            font=ctk.CTkFont(size=13),
        )
        btn.grid(row=0, column=0, sticky="ew")

        # Tooltip: reuse the navigation i18n key so it tracks language switches
        # and stays valid even when the display name is localized.
        if nav_key:
            tip_key = f"tip_nav_{nav_key}"
            try:
                import i18n as _i18n
                if _i18n.t(tip_key) != tip_key:
                    import ui_tooltip
                    ui_tooltip.attach_key(btn, tip_key)
            except Exception:
                pass

        badge = BadgeLabel(btn_frame, text="", status="neutral")
        badge.grid(row=0, column=1, sticky="e", padx=(4, 0))
        badge.grid_remove()

        self._buttons[name] = btn
        self._badge_labels[name] = badge

    def _on_click(self, name: str):
        self._current_tab = name
        for n, b in self._buttons.items():
            if n == name:
                b.configure(
                    fg_color=COLOR_SIDEBAR_SELECTED,
                    text_color=COLOR_TEXT_PRIMARY,
                )
            else:
                b.configure(
                    fg_color="transparent",
                    text_color=COLOR_TEXT_SECONDARY,
                )
        if self._command:
            self._command(name)

    def set_current(self, name: str):
        """Set current tab without triggering command callback."""
        self._current_tab = name
        for n, b in self._buttons.items():
            if n == name:
                b.configure(
                    fg_color=COLOR_SIDEBAR_SELECTED,
                    text_color=COLOR_TEXT_PRIMARY,
                )
            else:
                b.configure(
                    fg_color="transparent",
                    text_color=COLOR_TEXT_SECONDARY,
                )

    def _refresh_region_indicator(self, _old=None, _new=None):
        """Rebuild the region/currency text in the sidebar footer."""
        import localization_manager as lm
        try:
            mgr = lm.get_manager()
            region = mgr.display_region()
            sym = mgr.currency_symbol()
            code = mgr.currency_code()
            text = f"{i18n.t('region_indicator')}: {region}  {sym} ({code})"
        except Exception:
            text = f"{i18n.t('region_indicator')}: US  $ (USD)"
        if self._region_indicator.winfo_exists():
            self._region_indicator.configure(text=text)
        # Subscribe once to live updates.
        if not getattr(self, "_region_listener_registered", False):
            try:
                mgr = lm.get_manager()
                mgr.register_listener(self._refresh_region_indicator)
                self._region_listener_registered = True
            except Exception:
                pass

    def get_current(self) -> Optional[str]:
        return self._current_tab

    def _create_region_banner(self):
        """Create the interactive notification banner (RBAC-gated)."""
        try:
            from ui_region_banner import create_region_banner
            self._region_banner = create_region_banner(
                self,
                app=None,
                on_change=self._on_banner_change_region,
                on_dismiss=self._on_banner_dismiss,
            )
        except Exception as e:
            log.debug("region banner not created: %s", e)
            self._region_banner = None

    def _on_banner_change_region(self):
        """Open Settings > Region selector (audit-logged, RBAC-gated at source)."""
        try:
            import audit_log
            audit_log.log_action("REGION_BANNER", "User clicked banner 'Change Region' — navigating to Settings")
        except Exception:
            pass
        # Flip to the Settings tab, then let the user pick a region.
        if self._command:
            self._command("Settings")
        # The SettingsFrame region selector is wired with require_permission.

    def _on_banner_dismiss(self):
        try:
            import audit_log
            import localization_manager as lm
            mgr = lm.get_manager()
            audit_log.log_action("REGION_BANNER", f"User dismissed region banner for region={mgr.region()}")
        except Exception:
            pass
        if self._region_banner and self._region_banner.winfo_exists():
            self._region_banner.grid_remove()

    def set_command(self, cmd: Callable):
        self._command = cmd

    def update_badge(self, name: str, badge_text: str = "", status: str = "warning"):
        """Update the badge text for a navigation button."""
        badge = self._badge_labels.get(name)
        if badge is None:
            return
        if badge_text:
            badge.configure(text=badge_text)
            bg_colors = {
                "success": COLOR_SUCCESS,
                "warning": COLOR_WARNING,
                "error": COLOR_ERROR,
                "info": COLOR_ACCENT,
                "neutral": COLOR_TEXT_SECONDARY,
            }
            badge.configure(fg_color=bg_colors.get(status, COLOR_WARNING))
            badge.grid()
        else:
            badge.grid_remove()

    def destroy(self):
        """Unsubscribe region listener to avoid orphaned references (G5.2)."""
        try:
            import localization_manager as lm
            mgr = lm.get_manager()
            mgr.unregister_listener(self._refresh_region_indicator)
        except Exception:
            pass
        super().destroy()

    def set_button_visible(self, name: str, visible: bool) -> None:
        """Show or hide a navigation button by its (localized) tab name.

        The button lives inside a per-row ``btn_frame``; toggling that frame's
        grid removes the entry from the scrollable list without disturbing the
        other rows. No-op for unknown names.
        """
        btn = self._buttons.get(name)
        if btn is None:
            return
        frame = btn.master
        if visible:
            frame.grid()
        else:
            frame.grid_remove()


# ── TabViewCompat — Drop-in Replacement for CTkTabview ──────────────────

class TabViewCompat:
    """Compatibility shim for legacy code that references self.tab_view.

    Provides CTkTabview-compatible API (add, tab, get, set, configure)
    but manages visibility via a ContentContainer instead of tab bar.

    Attributes:
        drawer: NavigationDrawer instance
        frames: Dict mapping tab name -> frame
    """

    class _TabProxy:
        """Proxy returned by tab(name) — supports configure(text=...)."""
        def __init__(self, compat, name):
            self._compat = compat
            self._name = name

        def configure(self, text=None, **kwargs):
            """Update the drawer button label text."""
            if text is not None:
                # Strip badge from text to get clean name, update drawer button
                clean = text.replace("  [", "[").strip()
                # Try to extract just the name part
                if "[" in text and "]" in text:
                    badge_part = text.split("[", 1)[1].split("]", 1)[0]
                    self._compat.drawer.update_badge(self._name, badge_part)
                else:
                    self._compat.drawer.update_badge(self._name, "")
                self._compat.drawer._buttons[self._name].configure(text=text)

    def __init__(self, drawer: NavigationDrawer, content_area: ctk.CTkFrame):
        self.drawer = drawer
        self._content = content_area
        self.frames: Dict[str, ctk.CTkFrame] = {}
        self._current: Optional[str] = None
        self._command: Optional[Callable] = None
        drawer.set_command(self._on_drawer_click)

    @property
    def _tab_dict(self):
        """Compatibility shim for legacy CTkTabview code.

        The original ``ctk.CTkTabview`` stores tabs in ``_tab_dict`` mapping
        tab-name strings to internal ``_CTkTab`` objects.  Legacy code in
        ``ui_pos_panels.py`` and ``ui_pos_retail.py`` iterates
        ``app.tab_view._tab_dict`` to enumerate tab names and then calls
        ``app.tab_view.set(name)``.

        ``TabViewCompat`` manages visibility via ``self.frames`` (a dict
        of tab-name → content frame).  Iterating a dict yields its keys,
        so returning ``self.frames`` satisfies the iteration protocol and
        all tab-name lookup patterns used by legacy callers.
        """
        return self.frames

    def add(self, name: str) -> ctk.CTkFrame:
        """Create a new content frame and register it in the navigation drawer."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        self.frames[name] = frame
        frame.grid_columnconfigure(0, weight=1)
        return frame

    def tab(self, name: str) -> _TabProxy:
        """Return a proxy for badge/label updates."""
        return self._TabProxy(self, name)

    def get(self) -> str:
        """Return the currently visible tab name (localized string)."""
        return self._current or ""

    def set(self, name: str):
        """Switch to the named tab (programmatic call — does NOT trigger command)."""
        self._switch_to(name, notify=False)

    def configure(self, command: Callable = None, **kwargs):
        """Set the tab-change callback (called when user clicks a drawer button)."""
        self._command = command

    def _on_drawer_click(self, name: str):
        """Called when user clicks a drawer button."""
        self._switch_to(name, notify=True)

    def _switch_to(self, name: str, notify: bool = False):
        """Show the frame for `name`, hide others."""
        if name not in self.frames:
            return

        for n, frame in self.frames.items():
            if n == name:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()

        self._current = name
        self.drawer.set_current(name)

        if notify and self._command:
            self._command()

    def show_first(self):
        """Make the first registered frame visible."""
        if self.frames:
            first = list(self.frames.keys())[0]
            self._switch_to(first, notify=False)
            self.drawer.set_current(first)

    def get_tab_count(self) -> int:
        return len(self.frames)


# ── Factory ─────────────────────────────────────────────────────────────

# Maps localization keys to icon glyphs
_NAV_ICONS = {
    "dashboard": "📊",
    "add_product": "➕",
    "inventory": "📦",
    "expiring_soon": "⏰",
    "receive_inventory": "📥",
    "bulk_import_title": "📥",
    "sales_report": "📈",
    "checkout": "💳",
    "templates": "📄",
    "patients": "👥",
    "settings": "⚙️",
    "enterprise_settings": "🏢",
    "pos_terminal": "🔢",
    "rx_processing": "💊",
    "epcs_workflow": "📝",
    "status_dashboard": "📊",
    "pos_retail_title": "🛒",
    "clinical_workflow_title": "🏥",
    "quick_sig_title": "✒️",
    "inventory_mgmt_title": "📋",
}

# RBAC: which permission (if any) gates visibility of each nav entry.
# Keyed by i18n key so it survives language switches. A missing key means
# the tab is visible to every authenticated user.
NAV_PERMISSIONS = {
    "settings": "settings.view",
    "enterprise_settings": "settings.manage",
    "status_dashboard": "reports.view",
}


def create_navigation_system(parent, i18n_module=None):
    """Create a navigation drawer + content container + TabViewCompat shim.

    Args:
        parent: The CTk root or container widget.
        i18n_module: The i18n module for resolving tab labels. If None,
                     raw strings from the key list are used.

    Returns:
        Tuple of (NavigationDrawer, TabViewCompat, container_frame).
        The container_frame should be gridded/packed by the caller to fill
        the available space.
    """
    # Container with two columns: drawer (left) + content (right)
    container = ctk.CTkFrame(parent, fg_color="transparent")
    container.grid_columnconfigure(0, weight=0, minsize=220)
    container.grid_columnconfigure(1, weight=1)
    container.grid_rowconfigure(0, weight=1)

    # Build button data from known tab keys
    if i18n_module is not None:
        button_data = [(key, i18n_module.t(key), icon) for key, icon in _NAV_ICONS.items()]
    else:
        button_data = [(key, key, icon) for key, icon in _NAV_ICONS.items()]

    # Navigation drawer
    drawer = NavigationDrawer(container, button_data=button_data)
    drawer.grid(row=0, column=0, sticky="nsew", pady=14)

    # Content area
    content_area = ctk.CTkFrame(container, fg_color="transparent")
    content_area.grid(row=0, column=1, sticky="nsew", padx=(14, 0), pady=14)
    content_area.grid_columnconfigure(0, weight=1)
    content_area.grid_rowconfigure(0, weight=1)

    # Compat shim
    tab_view = TabViewCompat(drawer, content_area)

    return drawer, tab_view, container
