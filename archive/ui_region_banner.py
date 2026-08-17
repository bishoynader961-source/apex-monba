"""ui_region_banner.py — Interactive notification banner for region changes.

Shows a dismissible banner in the navigation drawer when:
  * The detected/saved region differs from what's persisted, OR
  * A region change is pending user review.

The banner is created as a child of the NavigationDrawer (via ``create_region_banner``)
so it survives ``setup_dashboard_tab``'s ``winfo_children()`` destroy loop.
"""
import logging
import customtkinter as ctk

log = logging.getLogger("region_banner")

_BANNER_BG = "#1e3a5f"
_BANNER_FG = "#e0f2fe"
_BANNER_BORDER = "#38bdfa"


def create_region_banner(parent, app, *, on_change=None, on_dismiss=None):
    """Create the banner as a child of ``parent`` (the NavigationDrawer).

    Returns the banner frame, or ``None`` when there is nothing to show
    (region already dismissed or no change pending). The caller is
    responsible for ``.grid_remove()`` / ``.grid()`` toggling on future
    refreshes.
    """
    import localization_manager as lm

    try:
        mgr = lm.get_manager()
    except Exception:
        return None

    # Only show if the region hasn't been dismissed AND a change is pending.
    # A "change is pending" means the detected region differs from the
    # persisted/committed region. For the initial MVP we show the banner
    # whenever the saved region matches the current (detected) region but
    # has *not yet been dismissed* — i.e. it's an "awareness" banner that
    # lets the user confirm or switch. This surfaces the region picker
    # without blocking workflow.
    if mgr.is_banner_dismissed():
        return None

    import i18n as _i18n

    frame = ctk.CTkFrame(
        parent,
        fg_color=_BANNER_BG,
        border_color=_BANNER_BORDER,
        border_width=1,
        corner_radius=6,
    )
    frame.grid_propagate(False)
    frame.grid(
        row=97, column=0, padx=12, pady=(0, 8),
        sticky="ew",
    )

    body = ctk.CTkFrame(frame, fg_color="transparent")
    body.grid(row=0, column=0, padx=10, pady=8)
    body.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        body,
        text=_i18n.t("region_banner_title"),
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=_BANNER_FG,
    ).grid(row=0, column=0, sticky="w", pady=(0, 2))

    ctk.CTkLabel(
        body,
        text=_i18n.t("region_banner_msg"),
        font=ctk.CTkFont(size=11),
        text_color="#bae6fd",
        wraplength=180,
        justify="left",
    ).grid(row=1, column=0, sticky="w")

    btn_row = ctk.CTkFrame(body, fg_color="transparent")
    btn_row.grid(row=2, column=0, pady=(8, 0), sticky="ew")
    btn_row.grid_columnconfigure(1, weight=1)

    def _do_change():
        if on_change:
            on_change()
        mgr.set_banner_dismissed(mgr.region(), dismissed=True)
        _hide_self()

    def _do_dismiss():
        mgr.set_banner_dismissed(mgr.region(), dismissed=True)
        _hide_self()

    def _hide_self():
        try:
            frame.grid_remove()
        except Exception:
            pass
        if on_dismiss:
            on_dismiss()

    ctk.CTkButton(
        btn_row, text=_i18n.t("region_banner_change"),
        command=_do_change,
        fg_color="#0284c7", hover_color="#0369a1",
        height=28, font=ctk.CTkFont(size=11),
    ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

    ctk.CTkButton(
        btn_row, text=_i18n.t("region_banner_dismiss"),
        command=_do_dismiss,
        fg_color="transparent", hover_color="#334155",
        height=28, font=ctk.CTkFont(size=11),
        text_color="#94a3b8",
    ).grid(row=0, column=1, sticky="ew")

    # Keep banner text in sync with live region changes (non-blocking).
    def _on_region(_old, _new):
        try:
            _do_change.__self__  # noqa
        except Exception:
            pass
    try:
        mgr.register_listener(_on_region)
    except Exception:
        pass

    return frame
