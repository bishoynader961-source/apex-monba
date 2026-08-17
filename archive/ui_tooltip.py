import logging
import customtkinter as ctk
import i18n

log = logging.getLogger("ui_tooltip")

_DELAY_MS = 420
_WRAP = 300


class Tooltip:
    def __init__(self, widget, text, delay=_DELAY_MS, wraplength=_WRAP):
        self._widget = widget
        self._text = text
        self._delay = delay
        self._wraplength = wraplength
        self._tip = None
        self._after_id = None
        self._on_lang = None
        # Bind by ID so we can reliably unbind later (no identity ambiguity).
        self._enter_id = widget.bind("<Enter>", self._schedule, add="+")
        self._leave_id = widget.bind("<Leave>", self._unschedule, add="+")
        self._press_id = widget.bind("<ButtonPress>", self._unschedule, add="+")
        widget.bind("<Destroy>", self._cleanup, add="+")

    def _schedule(self, event=None):
        self._unschedule()
        self._after_id = self._widget.after(self._delay, self._show)

    def _unschedule(self, event=None):
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self):
        if self._tip or not self._text:
            return
        try:
            x = self._widget.winfo_rootx() + 24
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 8
            if x + _WRAP > self._widget.winfo_screenwidth():
                x = self._widget.winfo_screenwidth() - _WRAP - 8
            self._tip = ctk.CTkToplevel(self._widget)
            self._tip.wm_overrideredirect(True)
            self._tip.wm_geometry(f"+{x}+{y}")
            label = ctk.CTkLabel(
                self._tip, text=self._text, wraplength=self._wraplength,
                justify="left", fg_color="#1e293b", text_color="#e5e7eb",
            )
            label.pack(ipadx=8, ipady=5)
        except ctk.TclError:
            self._tip = None

    def _hide(self):
        tip = self._tip
        self._tip = None
        if tip and tip.winfo_exists():
            tip.destroy()

    def set_text(self, text):
        """Update the tooltip text (re-localization on language change)."""
        self._text = text
        if self._tip and self._tip.winfo_exists():
            for child in self._tip.winfo_children():
                try:
                    child.configure(text=text)
                except Exception:
                    pass

    def refresh(self, text=None):
        if text is not None:
            self._text = text
        self._hide()
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None

    def _cleanup(self, event=None):
        self._unschedule()
        self._hide()
        try:
            if self._on_lang is not None:
                i18n.unregister_listener(self._on_lang)
                self._on_lang = None
        except Exception:
            pass
        for bid in (self._enter_id, self._leave_id, self._press_id):
            try:
                if bid:
                    self._widget.unbind("<Enter>", bid)
                    self._widget.unbind("<Leave>", bid)
                    self._widget.unbind("<ButtonPress>", bid)
            except Exception:
                pass

    def destroy(self):
        self._cleanup()

    def __del__(self):
        try:
            self._cleanup()
        except Exception:
            pass


def attach(widget, text):
    return Tooltip(widget, text)


def attach_key(widget, i18n_key: str) -> Tooltip:
    """Attach a tooltip whose text tracks the given i18n key.

    Re-localizes automatically on language switch and unregisters its listener
    on widget destruction so it never leaks into ``i18n._LISTENERS``.
    """
    tip = Tooltip(widget, i18n.t(i18n_key))

    def _on_lang(_code):
        if widget.winfo_exists():
            tip.set_text(i18n.t(i18n_key))

    tip._on_lang = _on_lang
    i18n.on_language_change(_on_lang)
    return tip


def attach_many(mapping):
    return [Tooltip(w, t) for w, t in mapping.items()]
