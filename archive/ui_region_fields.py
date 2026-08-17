"""ui_region_fields.py — Reusable region-aware identifier field set.

Renders only the patient/pharmacy identifier fields valid for the active
region (US: DEA/NPI, GB: NHS/GPhC, DE: PZN) and re-renders automatically when
the region changes. Values are keyed by canonical field key (not the localized
label) so data survives a region or language switch.

Standard #4 proof-of-life consumer: the patient add/edit dialog wires this in.
Other modules (Rx Processing prescriber panel, Enterprise Settings pharmacy
identifiers) reuse the same widget in Modules 5/6.
"""
from __future__ import annotations

import customtkinter as ctk

import localization_manager as lm
import i18n


class RegionFieldSet(ctk.CTkFrame):
    """A frame showing only the identifier fields for the current region."""

    def __init__(self, master, values: dict[str, str] | None = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._mgr = lm.get_manager()
        self._build()
        if values:
            self.set_values(values)
        # Re-render on region change; unregister on destroy to avoid leaks.
        self._mgr.register_listener(self._on_region)
        self.bind("<Destroy>", lambda _e: self._cleanup(), add="+")

    def _build(self) -> None:
        for child in list(self.winfo_children()):
            child.destroy()
        self._entries.clear()
        for key in self._mgr.visible_fields():
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(0, weight=0, minsize=150)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=self._mgr.field_label(key), anchor="w").grid(
                row=0, column=0, padx=(0, 8), sticky="w"
            )
            entry = ctk.CTkEntry(row, width=240)
            entry.grid(row=0, column=1, sticky="ew")
            self._entries[key] = entry

    def _on_region(self, _old, _new) -> None:
        self._build()

    def _cleanup(self) -> None:
        try:
            self._mgr.unregister_listener(self._on_region)
        except Exception:
            pass

    def get_values(self) -> dict[str, str]:
        return {k: e.get().strip() for k, e in self._entries.items()}

    def set_values(self, data: dict[str, str]) -> None:
        for k, e in self._entries.items():
            e.delete(0, "end")
            if data.get(k):
                e.insert(0, str(data[k]))
