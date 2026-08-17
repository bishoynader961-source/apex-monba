"""ui_banner.py — Dashboard-level interactive notification banner for region changes.

Shows a dismissible banner at the top of the Dashboard tab when the detected
region has not been dismissed by the user.  The banner persists across
``setup_dashboard_tab`` refreshes because it lives in a parent frame created
once in ``PharmacyApp.__init__``.

Dependencies: localization_manager (lazy import to avoid cycles), i18n.
"""
import logging

import customtkinter as ctk

log = logging.getLogger("region_banner")

_BANNER_BG = "#1e293b"
_BANNER_TEXT = "#e0f2fe"
_BANNER_BORDER = "#38bdfa"


class RegionBanner(ctk.CTkFrame):
    """Interactive notification banner that survives dashboard refreshes.

    The banner is placed inside a persistent ``dashboard_banner_frame``
    (created once in ``PharmacyApp.__init__``) so that
    ``setup_dashboard_tab`` — which destroys and rebuilds the dashboard
    content widgets — never tears it down.
    """

    def __init__(self, master, app, **kw):
        super().__init__(master, fg_color=_BANNER_BG, corner_radius=8,
                         border_color=_BANNER_BORDER, border_width=1, **kw)
        # Lazy import to avoid import-order cycles with database / rx_config.
        # Note: bind to the LocalizationManager *instance* (singleton), not the
        # bare module — region(), register_listener(), etc. are instance methods.
        import localization_manager as lm
        self._lm = lm.get_manager()
        self._app = app

        self._label = ctk.CTkLabel(self, anchor="w", text_color=_BANNER_TEXT)
        self._label.pack(side="left", fill="x", expand=True, padx=12, pady=8)

        ctk.CTkButton(
            self, text="[Change Region]", width=120,
            command=self._go_settings,
        ).pack(side="right", padx=8)

        ctk.CTkButton(
            self, text="✕", width=28,
            command=self.dismiss,
        ).pack(side="right", padx=(0, 8))

        self._lm.register_listener(self._on_region)
        self._render()

    def _render(self):
        r = self._lm.region()
        self._label.configure(
            text=f"Region auto-detected: {self._lm.display_region()} "
                 f"({self._lm.currency_symbol()} · {self._lm.tax_term()})")
        self._set_visible(not self._lm.is_banner_dismissed(r))

    def _set_visible(self, show: bool):
        if show:
            self.pack(fill="x", padx=10, pady=(0, 8))
        else:
            self.pack_forget()

    def dismiss(self):
        """Persist dismissal for the current region and hide the banner."""
        self._lm.set_banner_dismissed(self._lm.region(), True)
        self._set_visible(False)

    def _go_settings(self):
        """Navigate to the Enterprise Settings tab where the region control lives."""
        import i18n
        try:
            self._app.tab_view.set(i18n.t("enterprise_settings"))
            if self._app.tab_view._command:
                self._app.tab_view._command()
        except Exception as e:
            log.warning("banner _go_settings failed: %s", e)

    def _on_region(self, _old, _new):
        """Re-render when the region changes (e.g. user picks a new one in Settings)."""
        self._render()

    def destroy(self):
        try:
            self._lm.unregister_listener(self._on_region)
        except Exception:
            pass
        super().destroy()
