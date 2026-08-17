"""
ui_pos_panels.py - Fully interactive POS side-panel modals for PharmacyPro.

Replaces every messagebox.showinfo placeholder in ui_pos_retail.py with a
real CTkToplevel panel using existing database / receipt_engine APIs.
No new database schema required.

Classes:
    InsurancePanel        - read-only insurance + Edit Patient Profile link
    NotesPanel            - free-text sale memo editor
    CouponPanel           - coupon code + %/$ toggle -> fees list
    ReceiptHistoryPanel   - last 50 receipts treeview + detail + print
    CustomerHistoryPanel  - patient purchase history
    DiscountDialog        - discount %/$ -> fees list
    ReturnDialog          - reverse a sold item
    MemoDialog            - alias for NotesPanel
    SplitPaymentDialog    - Cash + Card split entry
    EODDialog             - end-of-day summary dashboard
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date
from typing import Any, Callable, Optional

import customtkinter as ctk
from tkinter import ttk, messagebox

import database
import i18n
import barcode_logic

try:
    import receipt_engine
    HAS_RECEIPT_ENGINE = True
except ImportError:
    HAS_RECEIPT_ENGINE = False

# ── AsyncUI (optional — graceful fallback to synchronous) ──
try:
    from async_ui import AsyncUI
    HAS_ASYNC: bool = True
except ImportError:
    AsyncUI = None  # type: ignore[assignment]
    HAS_ASYNC = False
    log.warning("async_ui not available; background tasks will run synchronously")

try:
    from path_utils import get_resource_path
except ImportError:
    def get_resource_path(rel: str) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

from ui_navigation import (
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_SIDEBAR_BG, COLOR_SIDEBAR_HOVER,
)

log = logging.getLogger("ui_pos_panels")

# Font helpers
def _FONT_TITLE():  return ctk.CTkFont(size=16, weight="bold")
def _FONT_HEADER(): return ctk.CTkFont(size=13, weight="bold")
def _FONT_BODY():   return ctk.CTkFont(size=12)
def _FONT_SMALL():  return ctk.CTkFont(size=11)

# Palette
_ACCENT  = "#3b82f6"
_SUCCESS = "#22c55e"
_WARN    = "#f59e0b"
_DANGER  = "#ef4444"
_MUTED   = "#64748b"
_PANEL   = "#1e1e2e"


def _sep(parent: Any, pady: tuple = (8, 8)) -> ctk.CTkFrame:
    s = ctk.CTkFrame(parent, height=1, fg_color=_MUTED)
    s.pack(fill="x", padx=16, pady=pady)
    return s


def _sec(parent: Any, text: str) -> ctk.CTkLabel:
    lbl = ctk.CTkLabel(parent, text=text.upper(),
                        font=ctk.CTkFont(size=10, weight="bold"),
                        text_color=_MUTED)
    lbl.pack(anchor="w", padx=20, pady=(12, 2))
    return lbl


def _center(win: ctk.CTkToplevel, w: int, h: int, parent: Any) -> None:
    try:
        root = parent.winfo_toplevel()
        px = root.winfo_x() + (root.winfo_width()  - w) // 2
        py = root.winfo_y() + (root.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{px}+{py}")
    except Exception:
        win.geometry(f"{w}x{h}")


# =============================================================================
# 1. InsurancePanel
# =============================================================================
class InsurancePanel(ctk.CTkToplevel):
    """Read-only insurance info for the selected patient."""

    def __init__(self, parent: Any, patient: Optional[dict] = None,
                 app: Any = None, on_apply: Optional[Callable] = None, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._parent  = parent
        self._patient = patient or {}
        self._app     = app
        self._on_apply = on_apply
        self.title("Insurance Information")
        self.resizable(False, False)
        self.grab_set()
        _center(self, 440, 430, parent)
        self.configure(fg_color=_PANEL)
        self._build()
        self._load()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Insurance Information",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)

        name = self._patient.get("name", "No patient selected")
        cf = ctk.CTkFrame(self, fg_color="transparent")
        cf.pack(fill="x", padx=20, pady=(10, 0))
        ctk.CTkLabel(cf, text=f"Patient:  {name}",
                     font=_FONT_HEADER(), text_color=COLOR_TEXT_PRIMARY).pack(anchor="w")
        _sep(self, (8, 4))

        self._df = ctk.CTkScrollableFrame(self, fg_color="transparent", height=195)
        self._df.pack(fill="x", padx=20, pady=4)
        self._rows: dict[str, ctk.CTkLabel] = {}
        for lbl, key in [("Insurance Provider", "provider"),
                          ("Policy Number",      "policy"),
                          ("Group Number",       "group"),
                          ("Co-pay",             "copay"),
                          ("BIN",                "bin"),
                          ("PCN",                "pcn")]:
            r = ctk.CTkFrame(self._df, fg_color="transparent")
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=lbl + ":", font=_FONT_SMALL(),
                         text_color=_MUTED, width=145, anchor="w").pack(side="left")
            v = ctk.CTkLabel(r, text="...", font=_FONT_BODY(),
                             text_color=COLOR_TEXT_PRIMARY, anchor="w")
            v.pack(side="left", fill="x", expand=True)
            self._rows[key] = v

        _sep(self, (8, 4))
        self._status = ctk.CTkLabel(self, text=i18n.t("insurance_loaded"),
                                     font=_FONT_SMALL(), text_color=COLOR_TEXT_SECONDARY)
        self._status.pack(fill="x", padx=20, pady=(2, 6))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(bf, text="Apply to Sale",
                      font=_FONT_BODY(), fg_color=_ACCENT,
                      command=self._on_apply_click, width=150).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="Edit Patient Profile",
                      font=_FONT_BODY(), fg_color=_ACCENT,
                      command=self._edit, width=185).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="Copy All", font=_FONT_BODY(),
                      fg_color=COLOR_SIDEBAR_BG, hover_color=COLOR_SIDEBAR_HOVER,
                      command=self._copy, width=90).pack(side="left")
        ctk.CTkButton(bf, text="Close", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _load(self) -> None:
        pid = self._patient.get("id")
        if not pid:
            for v in self._rows.values(): v.configure(text="No patient selected")
            return
        try:
            conn = sqlite3.connect(database.get_db_path())
            conn.row_factory = sqlite3.Row
            cur  = conn.cursor()
            cur.execute("SELECT COALESCE(insurance_provider, '') AS insurance_provider, "
                        "COALESCE(policy_number, '') AS policy_number, "
                        "COALESCE(group_number, '') AS group_number "
                        "FROM patients WHERE id = ?", (pid,))
            row = cur.fetchone()
            # Try loading from insurance_table for BIN/PCN/copay if available
            insurance_row = None
            try:
                cur.execute("SELECT bin_number, pcn, group_number, plan_name, carrier "
                            "FROM insurance_table WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (pid,))
                insurance_row = cur.fetchone()
            except Exception:
                pass
            conn.close()
        except Exception as e:
            log.error("InsurancePanel DB: %s", e)
            row = None
            insurance_row = None
        if row is None:
            for v in self._rows.values(): v.configure(text="Not found")
            self._status.configure(text=i18n.t("insurance_apply_disabled"), text_color=_MUTED)
            return

        self._loaded_info = {
            "id": pid,
            "name": row["insurance_provider"],
            "insurance_provider": row["insurance_provider"],
            "policy_number": row["policy_number"],
            "group_number": row["group_number"],
        }
        if insurance_row:
            self._loaded_info["bin"] = insurance_row["bin_number"] or ""
            self._loaded_info["pcn"] = insurance_row["pcn"] or ""
            self._loaded_info["plan_name"] = insurance_row["plan_name"] or ""
            self._loaded_info["carrier"] = insurance_row["carrier"] or ""

        def s(v): return str(v) if v else "—"
        self._rows["provider"].configure(text=s(row["insurance_provider"]))
        self._rows["policy"].configure(text=s(row["policy_number"]))
        self._rows["group"].configure(text=s(row["group_number"]))
        if insurance_row:
            self._rows["copay"].configure(text=s(insurance_row["plan_name"]))
            self._rows["bin"].configure(text=s(insurance_row["bin_number"]))
            self._rows["pcn"].configure(text=s(insurance_row["pcn"]))
        else:
            for k in ("copay", "bin", "pcn"):
                self._rows[k].configure(text="—")
        self._status.configure(text=i18n.t("insurance_loaded"), text_color=_SUCCESS)

    def _on_apply_click(self) -> None:
        """Call the on_apply callback with loaded insurance info."""
        info = getattr(self, "_loaded_info", None) or {
            "id": self._patient.get("id") if self._patient else None,
            "name": self._patient.get("name", "") if self._patient else "",
            "insurance_provider": "",
            "policy_number": "",
            "group_number": "",
        }
        if self._on_apply:
            self._on_apply(info)
        self.destroy()

    def _edit(self) -> None:
        self.destroy()
        app = self._app
        if app is None:
            w = self._parent
            while w:
                if hasattr(w, "_app"): app = w._app; break
                w = getattr(w, "_parent", None)
        if app and hasattr(app, "tab_view"):
            try:
                for t in app.tab_view._tab_dict:
                    if "patient" in t.lower():
                        app.tab_view.set(t); return
            except Exception as e:
                log.warning("InsurancePanel._edit tab navigation failed: %s", e)
        messagebox.showinfo("Navigate", "Open the Patients tab to edit this record.",
                            parent=self._parent)

    def _copy(self) -> None:
        lbls = {"provider": "Insurance Provider", "policy": "Policy Number",
                "group": "Group Number", "copay": "Co-pay", "bin": "BIN", "pcn": "PCN"}
        text = "\n".join(f"{l}: {self._rows[k].cget('text')}" for k, l in lbls.items())
        try:
            self.clipboard_clear(); self.clipboard_append(text)
            self._rows["provider"].configure(text_color=_SUCCESS)
            self.after(1500, lambda: self._rows["provider"].configure(text_color=COLOR_TEXT_PRIMARY))
        except Exception:
            pass


# =============================================================================
# 2. NotesPanel
# =============================================================================
class NotesPanel(ctk.CTkToplevel):
    """Free-text sale memo editor."""

    def __init__(self, parent: Any, existing_memo: str = "",
                 on_save: Optional[Callable[[str], None]] = None, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._on_save = on_save
        self.title("Sale Notes / Memo")
        self.resizable(True, True)
        self.grab_set()
        _center(self, 480, 380, parent)
        self.configure(fg_color=_PANEL)
        self._build(existing_memo)

    def _build(self, memo: str) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Sale Notes / Memo",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        _sec(self, "Memo / Instructions for this sale")
        self._text = ctk.CTkTextbox(self, height=220, font=_FONT_BODY(),
                                     fg_color=COLOR_SIDEBAR_BG, text_color=COLOR_TEXT_PRIMARY,
                                     border_color=_MUTED, border_width=1)
        self._text.pack(fill="both", expand=True, padx=20, pady=(4, 8))
        if memo: self._text.insert("1.0", memo)
        _sep(self, (4, 8))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(bf, text="Save Memo", font=_FONT_BODY(),
                      fg_color=_SUCCESS, hover_color="#16a34a",
                      command=self._save, width=140).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="Clear", font=_FONT_BODY(),
                      fg_color=_DANGER, hover_color="#dc2626",
                      command=lambda: self._text.delete("1.0", "end"),
                      width=90).pack(side="left")
        ctk.CTkButton(bf, text="Cancel", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _save(self) -> None:
        memo = self._text.get("1.0", "end-1c").strip()
        if self._on_save: self._on_save(memo)
        self.destroy()


# =============================================================================
# 3. CouponPanel
# =============================================================================
class CouponPanel(ctk.CTkToplevel):
    """Coupon code entry with %/$ toggle. Pushes negative fee to fees list."""

    def __init__(self, parent: Any, fees: Optional[list] = None,
                 cart_subtotal: float = 0.0,
                 on_apply: Optional[Callable] = None, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._fees     = fees if fees is not None else []
        self._subtotal = cart_subtotal
        self._on_apply = on_apply
        self.title("Apply Coupon")
        self.resizable(False, False)
        self.grab_set()
        _center(self, 400, 350, parent)
        self.configure(fg_color=_PANEL)
        self._dtype = ctk.StringVar(value="percent")
        self._build()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Apply Coupon",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        _sec(body, "Coupon / Promo Code")
        self._code = ctk.CTkEntry(body, placeholder_text="e.g. SAVE10",
                                   font=_FONT_BODY(), width=280, height=38)
        self._code.pack(anchor="w", pady=(4, 12))
        _sec(body, "Discount Type")
        tog = ctk.CTkFrame(body, fg_color="transparent")
        tog.pack(anchor="w", pady=(4, 4))
        ctk.CTkRadioButton(tog, text="Percentage (%)", variable=self._dtype,
                           value="percent", font=_FONT_BODY(),
                           command=self._preview).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(tog, text="Flat Amount ($)", variable=self._dtype,
                           value="flat", font=_FONT_BODY(),
                           command=self._preview).pack(side="left")
        _sec(body, "Discount Value")
        vrow = ctk.CTkFrame(body, fg_color="transparent")
        vrow.pack(anchor="w", pady=(4, 8))
        self._pfx = ctk.CTkLabel(vrow, text="%", font=_FONT_HEADER(),
                                  text_color=_ACCENT, width=20)
        self._pfx.pack(side="left")
        self._val = ctk.CTkEntry(vrow, placeholder_text="10",
                                  font=_FONT_BODY(), width=120, height=36)
        self._val.pack(side="left", padx=(4, 0))
        self._val.bind("<KeyRelease>", lambda _: self._preview())
        self._prev_lbl = ctk.CTkLabel(body, text="Estimated saving: " + self.app.currency.fmt(0),
                                       font=_FONT_BODY(), text_color=_SUCCESS)
        self._prev_lbl.pack(anchor="w", pady=(4, 8))
        _sep(self, (4, 8))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(bf, text="Apply Coupon", font=_FONT_BODY(),
                      fg_color=_SUCCESS, hover_color="#16a34a",
                      command=self._apply, width=150).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="Cancel", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _preview(self) -> None:
        try: val = float(self._val.get().strip() or "0")
        except ValueError: val = 0.0
        dt = self._dtype.get()
        self._pfx.configure(text="%" if dt == "percent" else self.app.currency.symbol())
        saving = (self._subtotal * val / 100) if dt == "percent" else val
        self._prev_lbl.configure(text="Estimated saving: " + self.app.currency.fmt(saving),
                                   text_color=_SUCCESS if saving > 0 else _MUTED)

    def _apply(self) -> None:
        code = self._code.get().strip() or "COUPON"
        try:
            val = float(self._val.get().strip())
            if val <= 0: raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Value",
                                   "Enter a valid positive discount amount.", parent=self)
            return
        dt = self._dtype.get()
        if dt == "percent":
            if val > 100:
                messagebox.showwarning("Invalid", "Percentage cannot exceed 100%.", parent=self)
                return
            amount = self._subtotal * val / 100
            label  = f"Coupon {code} ({val:.0f}%)"
        else:
            amount = val; label = f"Coupon {code} (-{self.app.currency.fmt(val)})"
        self._fees[:] = [f for f in self._fees if "Coupon" not in str(f.get("name", ""))]
        self._fees.append({"name": label, "amount": -round(amount, 2)})
        if self._on_apply: self._on_apply()
        self.destroy()


# =============================================================================
# 4. ReceiptHistoryPanel
# =============================================================================
class ReceiptHistoryPanel(ctk.CTkToplevel):
    """Browse last 50 receipts, view item detail, print."""

    def __init__(self, parent: Any, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._parent = parent
        self.title("Receipt History")
        self.resizable(True, True)
        _center(self, 720, 520, parent)
        self.configure(fg_color=_PANEL)
        self._build()
        self.after(100, self._load)

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Receipt History",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)

        pane = ctk.CTkFrame(self, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=16, pady=8)
        pane.grid_columnconfigure(0, weight=2)
        pane.grid_columnconfigure(1, weight=3)
        pane.grid_rowconfigure(0, weight=1)

        # Left: list
        left = ctk.CTkFrame(pane, fg_color=COLOR_SIDEBAR_BG, corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="Recent Receipts", font=_FONT_HEADER(),
                     text_color=COLOR_TEXT_SECONDARY).grid(row=0, column=0, sticky="w", padx=12, pady=8)
        cols = ("ID", "Date", "Total", "Method")
        self._rtree = ttk.Treeview(left, columns=cols, show="headings", height=16)
        for c in cols:
            self._rtree.heading(c, text=c)
            self._rtree.column(c, width=70 if c != "Date" else 120, anchor="center")
        self._rtree.column("Date", anchor="w")
        self._rtree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._rtree.bind("<<TreeviewSelect>>", self._on_select)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self._rtree.yview)
        self._rtree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=1, column=1, sticky="ns", pady=(0, 8))

        # Right: detail
        right = ctk.CTkFrame(pane, fg_color=COLOR_SIDEBAR_BG, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self._dhdr = ctk.CTkLabel(right, text="<-- Select a receipt",
                                   font=_FONT_HEADER(), text_color=COLOR_TEXT_SECONDARY)
        self._dhdr.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        dcols = ("Item", "Qty", "Unit $", "Line $")
        self._dtree = ttk.Treeview(right, columns=dcols, show="headings", height=16)
        for c in dcols: self._dtree.heading(c, text=c)
        self._dtree.column("Item", width=170, anchor="w")
        self._dtree.column("Qty", width=50, anchor="center")
        self._dtree.column("Unit $", width=80, anchor="e")
        self._dtree.column("Line $", width=90, anchor="e")
        self._dtree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        dvsb = ttk.Scrollbar(right, orient="vertical", command=self._dtree.yview)
        self._dtree.configure(yscrollcommand=dvsb.set)
        dvsb.grid(row=1, column=1, sticky="ns", pady=(0, 8))

        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(ftr, text="Print / Open Receipt", font=_FONT_BODY(),
                      fg_color=_ACCENT, command=self._print, width=180).pack(side="left", padx=(0, 8))
        ctk.CTkButton(ftr, text="Reverse Item...", font=_FONT_BODY(),
                      fg_color=_WARN, hover_color="#d97706",
                      command=self._reverse, width=150).pack(side="left")
        ctk.CTkButton(ftr, text="Close", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _load(self) -> None:
        try: rows = list(database.get_receipts() or [])[:50]
        except Exception as e: log.error("ReceiptHistory load: %s", e); rows = []
        for r in self._rtree.get_children(): self._rtree.delete(r)
        for r in rows:
            self._rtree.insert("", "end", iid=str(r[0]),
                values=(r[0], str(r[1] or "")[:16], self.app.currency.fmt(float(r[2] or 0)), r[3] or "—"))

    def _on_select(self, _=None) -> None:
        sel = self._rtree.selection()
        if not sel: return
        rid = int(sel[0])
        self._dhdr.configure(text=f"Receipt #{rid}  --  Items")
        for r in self._dtree.get_children(): self._dtree.delete(r)
        try: items = database.get_receipt_items(rid) or []
        except Exception as e: log.error("Detail: %s", e); return
        for i in items:
            qty = i[3] if len(i) > 3 else 1
            price = float(i[4] or 0) if len(i) > 4 else 0.0
            self._dtree.insert("", "end", values=(i[2] if len(i) > 2 else "?",
                qty, self.app.currency.fmt(price), self.app.currency.fmt(qty*price)))

    def _print(self) -> None:
        sel = self._rtree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a receipt first.", parent=self); return
        if not HAS_RECEIPT_ENGINE:
            messagebox.showinfo("Print", "receipt_engine not available.", parent=self); return
        rid = int(sel[0])
        try:
            items = database.get_receipt_items(rid) or []
            cart  = [{"product_name": i[2], "quantity": i[3], "price_at_time": float(i[4] or 0)} for i in items]
            sub   = sum(c["quantity"] * c["price_at_time"] for c in cart)
            cfg   = barcode_logic.load_config()
            pi    = {"pharmacy_name": cfg.get("pharmacy_name", "My Pharmacy"),
                     "address": cfg.get("address", ""), "phone": cfg.get("phone", "")}
            path  = receipt_engine.generate_receipt(receipt_id=rid, cart_items=cart,
                                                    subtotal=sub, total=sub, pharmacy_info=pi)
            receipt_engine.open_receipt_file(path)
        except Exception as e:
            messagebox.showerror("Print Error", str(e), parent=self)

    def _reverse(self) -> None:
        p = self._parent; self.destroy(); ReturnDialog(p)


# =============================================================================
# 5. CustomerHistoryPanel
# =============================================================================
class CustomerHistoryPanel(ctk.CTkToplevel):
    """Purchase history for the currently selected patient."""

    def __init__(self, parent: Any, patient: Optional[dict] = None, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._patient = patient or {}
        name = self._patient.get("name", "All Transactions")
        self.title(f"Customer History -- {name}")
        self.resizable(True, True)
        _center(self, 720, 500, parent)
        self.configure(fg_color=_PANEL)
        self._build(name)
        self.after(100, self._load)

    def _build(self, name: str) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"Purchase History -- {name}",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        stats = ctk.CTkFrame(self, fg_color=COLOR_SIDEBAR_BG, corner_radius=6)
        stats.pack(fill="x", padx=16, pady=8)
        self._tlbl = ctk.CTkLabel(stats, text="Total Spent: --",
                                   font=_FONT_HEADER(), text_color=_SUCCESS)
        self._tlbl.pack(side="left", padx=20, pady=8)
        self._clbl = ctk.CTkLabel(stats, text="Transactions: --",
                                   font=_FONT_BODY(), text_color=COLOR_TEXT_SECONDARY)
        self._clbl.pack(side="left", padx=20)
        tf = ctk.CTkFrame(self, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        tf.grid_columnconfigure(0, weight=1); tf.grid_rowconfigure(0, weight=1)
        cols = ("Date", "Receipt #", "Item", "Qty", "Price", "Method")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=18)
        for c, w in zip(cols, (130, 80, 200, 50, 80, 90)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w, anchor="w" if c in ("Item", "Date") else "center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set); vsb.grid(row=0, column=1, sticky="ns")
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(ftr, text="Close", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _load(self) -> None:
        try: items = database.get_all_receipt_items_flat() or []
        except Exception as e: log.error("CustomerHistory: %s", e); return
        for r in self._tree.get_children(): self._tree.delete(r)
        total = 0.0; rids: set = set()
        for i in items:
            ts = str(i[6] or "")[:16]
            total += float(i[5] or 0); rids.add(i[1])
            self._tree.insert("", "end", values=(ts, i[1], i[2] or "—",
                i[3] or 0, self.app.currency.fmt(float(i[4] or 0)), i[7] or "—"))
        self._tlbl.configure(text=f"Total Spent: {self.app.currency.fmt(total)}")
        self._clbl.configure(text=f"Transactions: {len(rids)}")


# =============================================================================
# 6. DiscountDialog
# =============================================================================
class DiscountDialog(ctk.CTkToplevel):
    """One-time discount (%/$) applied to the current cart."""

    def __init__(self, parent: Any, fees: Optional[list] = None,
                 cart_subtotal: float = 0.0,
                 on_apply: Optional[Callable] = None, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._fees     = fees if fees is not None else []
        self._subtotal = cart_subtotal
        self._on_apply = on_apply
        self.title("Apply Discount")
        self.resizable(False, False)
        self.grab_set()
        _center(self, 360, 300, parent)
        self.configure(fg_color=_PANEL)
        self._dtype = ctk.StringVar(value="percent")
        self._build()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Apply Discount",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        _sec(body, "Discount Type")
        tog = ctk.CTkFrame(body, fg_color="transparent")
        tog.pack(anchor="w", pady=(4, 10))
        ctk.CTkRadioButton(tog, text="Percentage (%)", variable=self._dtype,
                           value="percent", font=_FONT_BODY(),
                           command=self._refresh).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(tog, text="Flat ($)", variable=self._dtype,
                           value="flat", font=_FONT_BODY(),
                           command=self._refresh).pack(side="left")
        _sec(body, "Amount")
        r = ctk.CTkFrame(body, fg_color="transparent")
        r.pack(anchor="w", pady=(4, 8))
        self._pfx = ctk.CTkLabel(r, text="%", font=_FONT_HEADER(), text_color=_ACCENT, width=20)
        self._pfx.pack(side="left")
        self._entry = ctk.CTkEntry(r, placeholder_text="10",
                                   font=_FONT_BODY(), width=120, height=36)
        self._entry.pack(side="left", padx=(4, 0))
        self._entry.bind("<KeyRelease>", lambda _: self._refresh())
        self._prev = ctk.CTkLabel(body, text="Saving: " + self.app.currency.fmt(0),
                                   font=_FONT_BODY(), text_color=_SUCCESS)
        self._prev.pack(anchor="w", pady=(4, 0))
        _sep(self, (8, 8))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(bf, text="Apply", font=_FONT_BODY(),
                      fg_color=_SUCCESS, hover_color="#16a34a",
                      command=self._apply, width=130).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="Cancel", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _refresh(self) -> None:
        try: val = float(self._entry.get().strip() or "0")
        except ValueError: val = 0.0
        dt = self._dtype.get()
        self._pfx.configure(text="%" if dt == "percent" else self.app.currency.symbol())
        saving = (self._subtotal * val / 100) if dt == "percent" else val
        self._prev.configure(text="Saving: " + self.app.currency.fmt(saving),
                              text_color=_SUCCESS if saving > 0 else _MUTED)

    def _apply(self) -> None:
        try:
            val = float(self._entry.get().strip())
            if val <= 0: raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid", "Enter a positive amount.", parent=self); return
        dt = self._dtype.get()
        if dt == "percent":
            if val > 100:
                messagebox.showwarning("Invalid", "Percentage cannot exceed 100%.", parent=self); return
            amount = self._subtotal * val / 100; label = f"Discount ({val:.0f}%)"
        else:
            amount = val; label = f"Discount (-{self.app.currency.fmt(val)})"
        self._fees[:] = [f for f in self._fees if "Discount" not in str(f.get("name", ""))]
        self._fees.append({"name": label, "amount": -round(amount, 2)})
        if self._on_apply: self._on_apply()
        self.destroy()


# =============================================================================
# PriceOverrideDialog
# =============================================================================
class PriceOverrideDialog(ctk.CTkToplevel):
    """Modal dialog to override the unit price of a cart item (G4)."""

    def __init__(self, parent: Any, item_name: str = "", old_price: float = 0.0,
                 on_apply: Optional[Callable] = None, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._on_apply = on_apply
        self._old_price = old_price
        self.title("Price Override")
        self.resizable(False, False)
        self.grab_set()
        _center(self, 340, 260, parent)
        self.configure(fg_color=_PANEL)
        self._build()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Price Override",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        _sec(body, "Current Price")
        ctk.CTkLabel(body, text=self.app.currency.fmt(self._old_price),
                     font=_FONT_HEADER(), text_color=_MUTED).pack(anchor="w", pady=(4, 8))

        _sec(body, "New Price")
        self._entry = ctk.CTkEntry(body, placeholder_text=f"{self._old_price:.2f}",
                                   font=_FONT_BODY(), width=200, height=36)
        self._entry.pack(anchor="w", pady=(4, 8))
        self._entry.insert(0, f"{self._old_price:.2f}")

        self._error = ctk.CTkLabel(body, text="", font=_FONT_SMALL(), text_color=_DANGER)
        self._error.pack(anchor="w")

        _sep(self, (8, 8))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(bf, text="Apply", font=_FONT_BODY(),
                      fg_color=_ACCENT, hover_color="#2563eb",
                      width=100, height=36,
                      command=self._on_submit).pack(side="right")
        ctk.CTkButton(bf, text="Cancel", font=_FONT_BODY(),
                      fg_color="transparent", border_width=1,
                      text_color=_MUTED, width=80, height=36,
                      command=self.destroy).pack(side="right", padx=(0, 8))
        self._entry.focus_set()
        self.bind("<Return>", lambda _: self._on_submit())

    def _on_submit(self) -> None:
        try:
            val = float(self._entry.get().strip())
            if val < 0:
                raise ValueError
        except (ValueError, TypeError):
            self._error.configure(text="Enter a valid non-negative price.")
            return
        if self._on_apply:
            self._on_apply(val)
        self.grab_release()
        self.destroy()


# =============================================================================
# VoidConfirmDialog
# =============================================================================
class VoidConfirmDialog(ctk.CTkToplevel):
    """Modal confirmation for voiding a cart item (G4)."""

    def __init__(self, parent: Any, item_name: str = "", qty: int = 1,
                 on_confirm: Optional[Callable] = None, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._on_confirm = on_confirm
        self._item_name = item_name
        self._qty = qty
        self.title("Confirm Void")
        self.resizable(False, False)
        self.grab_set()
        _center(self, 340, 220, parent)
        self.configure(fg_color=_PANEL)
        self._build()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Void Item",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        ctk.CTkLabel(body, text="Are you sure you want to void this item?",
                     font=_FONT_BODY(), text_color=_WARN).pack(anchor="w", pady=(4, 8))
        ctk.CTkLabel(body, text=f"{self._item_name} × {self._qty}",
                     font=_FONT_HEADER()).pack(anchor="w", pady=(0, 4))

        _sep(self, (8, 8))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(bf, text="Void", font=_FONT_BODY(),
                      fg_color=_DANGER, hover_color="#dc2626",
                      width=100, height=36,
                      command=self._on_submit).pack(side="right")
        ctk.CTkButton(bf, text="Cancel", font=_FONT_BODY(),
                      fg_color="transparent", border_width=1,
                      text_color=_MUTED, width=80, height=36,
                      command=self.destroy).pack(side="right", padx=(0, 8))

    def _on_submit(self) -> None:
        if self._on_confirm:
            self._on_confirm()
        self.grab_release()
        self.destroy()


# =============================================================================
# 7. ReturnDialog
# =============================================================================
class ReturnDialog(ctk.CTkToplevel):
    """Select a sold item and reverse the sale back to inventory."""

    def __init__(self, parent: Any, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._parent = parent
        self._rows: list[tuple] = []
        self.title("Process Return")
        self.resizable(True, False)
        self.grab_set()
        _center(self, 640, 440, parent)
        self.configure(fg_color=_PANEL)
        self._build()
        self.after(100, self._load)

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Process Return",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        ctk.CTkLabel(self, text="Select the sold item to return to inventory.",
                     font=_FONT_SMALL(), text_color=_MUTED).pack(anchor="w", padx=20, pady=(6, 4))
        sf = ctk.CTkFrame(self, fg_color="transparent")
        sf.pack(fill="x", padx=20, pady=(0, 8))
        self._sv = ctk.StringVar()
        self._sv.trace_add("write", lambda *_: self._filter())
        ctk.CTkEntry(sf, textvariable=self._sv, placeholder_text="Search by drug name...",
                     font=_FONT_BODY(), width=300, height=34).pack(side="left")
        tf = ctk.CTkFrame(self, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        tf.grid_columnconfigure(0, weight=1); tf.grid_rowconfigure(0, weight=1)
        cols = ("ID", "Drug Name", "Price", "Barcode", "Sold At", "Vendor")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=12)
        for c, w in zip(cols, (40, 200, 70, 100, 130, 100)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w, anchor="w" if c in ("Drug Name", "Sold At") else "center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set); vsb.grid(row=0, column=1, sticky="ns")
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 14))
        ctk.CTkButton(bf, text="Reverse Selected Sale", font=_FONT_BODY(),
                      fg_color=_WARN, hover_color="#d97706",
                      command=self._reverse, width=200).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="Cancel", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _load(self) -> None:
        try: self._rows = list(database.get_sold_items() or [])[:200]
        except Exception as e: log.error("ReturnDialog: %s", e); self._rows = []
        self._filter()

    def _filter(self) -> None:
        q = self._sv.get().lower().strip()
        for r in self._tree.get_children(): self._tree.delete(r)
        for r in self._rows:
            if q and q not in str(r[1] or "").lower(): continue
            self._tree.insert("", "end", iid=str(r[0]),
                values=(r[0], r[1], self.app.currency.fmt(float(r[2] or 0)),
                        r[4] or r[3] or "—", str(r[5] or "")[:16], r[6] or "—"))

    def _reverse(self) -> None:
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a sold item first.", parent=self); return
        sid  = int(sel[0])
        drug = self._tree.item(sel[0], "values")[1] if self._tree.item(sel[0], "values") else "item"
        if not messagebox.askyesno("Confirm Return",
                                   f"Return '{drug}' to inventory?\nThe sale record will be removed.",
                                   parent=self):
            return
        try:
            database.reverse_sale(sid)
            messagebox.showinfo("Return Processed", f"'{drug}' returned to inventory.", parent=self)
            self._load()
        except Exception as e:
            messagebox.showerror("Error", f"Return failed: {e}", parent=self)


# =============================================================================
# 8. MemoDialog
# =============================================================================
class MemoDialog(NotesPanel):
    """Quick-action Add Memo -- identical to NotesPanel."""
    def __init__(self, parent: Any, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self.title("Add Sale Memo")


# =============================================================================
# 9. SplitPaymentDialog
# =============================================================================
class SplitPaymentDialog(ctk.CTkToplevel):
    """Split payment between Cash and Card."""

    def __init__(self, parent: Any, grand_total: float = 0.0,
                 on_confirm: Optional[Callable[[float, float, str], None]] = None,
                 **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._total     = grand_total
        self._on_confirm = on_confirm
        self.title("Split Payment")
        self.resizable(False, False)
        self.grab_set()
        _center(self, 380, 360, parent)
        self.configure(fg_color=_PANEL)
        self._build()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Split Payment",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        ctk.CTkLabel(body, text=f"Grand Total:  {self.app.currency.fmt(self._total)}",
                     font=_FONT_HEADER(), text_color=_SUCCESS).pack(anchor="w", pady=(0, 12))
        _sec(body, "Cash Amount ($)")
        self._cash = ctk.CTkEntry(body, placeholder_text="0.00", font=_FONT_BODY(), width=200, height=38)
        self._cash.pack(anchor="w", pady=(4, 12))
        self._cash.bind("<KeyRelease>", lambda _: self._refresh())
        _sec(body, "Card Amount ($)")
        self._card = ctk.CTkEntry(body, placeholder_text="0.00", font=_FONT_BODY(), width=200, height=38)
        self._card.pack(anchor="w", pady=(4, 8))
        self._card.bind("<KeyRelease>", lambda _: self._refresh())
        self._rem = ctk.CTkLabel(body, text="Remaining:  " + self.app.currency.fmt(0), font=_FONT_BODY(), text_color=_MUTED)
        self._rem.pack(anchor="w", pady=(4, 0))
        _sep(self, (10, 8))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(bf, text="Confirm Split", font=_FONT_BODY(),
                      fg_color=_SUCCESS, hover_color="#16a34a",
                      command=self._confirm, width=150).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="Cancel", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    def _refresh(self) -> None:
        try: cash = float(self._cash.get().strip() or "0")
        except ValueError: cash = 0.0
        try: card = float(self._card.get().strip() or "0")
        except ValueError: card = 0.0
        rem = self._total - cash - card
        self._rem.configure(text=f"Remaining:  {self.app.currency.fmt(max(rem, 0))}",
                             text_color=_SUCCESS if rem <= 0 else _WARN)

    def _confirm(self) -> None:
        try: cash = float(self._cash.get().strip() or "0"); card = float(self._card.get().strip() or "0")
        except ValueError:
            messagebox.showwarning("Invalid", "Enter valid amounts.", parent=self); return
        if cash + card < self._total - 0.005:
            messagebox.showwarning("Insufficient",
                f"Cash + Card ({self.app.currency.fmt(cash+card)}) < Total ({self.app.currency.fmt(self._total)}).", parent=self); return
        label = f"Split: Cash {self.app.currency.fmt(cash)} + Card {self.app.currency.fmt(card)}"
        if self._on_confirm: self._on_confirm(cash, card, label)
        self.destroy()


# =============================================================================
# 10. EODDialog
# =============================================================================
class EODDialog(ctk.CTkToplevel):
    """End-of-Day reconciliation summary (read-only)."""

    def __init__(self, parent: Any, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._parent = parent
        self._today  = date.today().strftime("%Y-%m-%d")
        self.title(f"End of Day -- {self._today}")
        self.resizable(True, True)
        _center(self, 700, 540, parent)
        self.configure(fg_color=_PANEL)
        self._build()
        self.after(100, self._load)

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"End of Day -- {self._today}",
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        kpi = ctk.CTkFrame(self, fg_color=COLOR_SIDEBAR_BG, corner_radius=6)
        kpi.pack(fill="x", padx=16, pady=(8, 4))
        self._ktotal = self._chip(kpi, "Total Revenue", self.app.currency.fmt(0), _SUCCESS)
        self._kcount = self._chip(kpi, "Transactions",  "0",     _ACCENT)
        self._kitems = self._chip(kpi, "Items Sold",    "0",     _WARN)
        _sec(self, "Today's Sales Detail")
        tf = ctk.CTkFrame(self, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        tf.grid_columnconfigure(0, weight=1); tf.grid_rowconfigure(0, weight=1)
        cols = ("Time", "Receipt #", "Item", "Qty", "Unit $", "Line $", "Method")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=14)
        for c, w in zip(cols, (80, 80, 200, 50, 70, 80, 90)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w, anchor="w" if c == "Item" else "center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set); vsb.grid(row=0, column=1, sticky="ns")
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(ftr, text="Export to Text", font=_FONT_BODY(),
                      fg_color=_ACCENT, command=self._export, width=160).pack(side="left", padx=(0, 8))
        ctk.CTkButton(ftr, text="Close", font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

    @staticmethod
    def _chip(parent, label, value, color) -> ctk.CTkLabel:
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side="left", padx=20, pady=10)
        ctk.CTkLabel(f, text=label, font=_FONT_SMALL(), text_color=_MUTED).pack()
        v = ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=22, weight="bold"), text_color=color)
        v.pack()
        return v

    def _load(self) -> None:
        try:
            total = float(database.get_receipts_total_for_date(self._today) or 0)
            items = database.get_receipt_items_for_date(self._today) or []
        except Exception as e: log.error("EOD load: %s", e); return
        for r in self._tree.get_children(): self._tree.delete(r)
        rids: set = set(); cnt = 0
        for i in items:
            ts = str(i[6] or ""); ts_s = ts[11:16] if len(ts) >= 16 else ts[:8]
            rids.add(i[1]); cnt += (i[3] or 0)
            self._tree.insert("", "end", values=(ts_s, i[1], i[2] or "—",
                i[3] or 0, self.app.currency.fmt(float(i[4] or 0)), self.app.currency.fmt(float(i[5] or 0)), i[7] or "—"))
        self._ktotal.configure(text=self.app.currency.fmt(total) if total else "Total Revenue: " + self.app.currency.fmt(0))
        self._kcount.configure(text=str(len(rids)))
        self._kitems.configure(text=str(cnt))

    def _export(self) -> None:
        try:
            out = get_resource_path("receipts"); os.makedirs(out, exist_ok=True)
            fname = os.path.join(out, f"EOD_{self._today}.txt")
            lines = [f"End of Day -- {self._today}", "=" * 40]
            for iid in self._tree.get_children():
                lines.append("  ".join(str(v) for v in self._tree.item(iid, "values")))
            with open(fname, "w", encoding="utf-8") as f: f.write("\n".join(lines))
            if HAS_RECEIPT_ENGINE: receipt_engine.open_receipt_file(fname)
            else: messagebox.showinfo("Exported", f"Saved to:\n{fname}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)


# =============================================================================
# ProductPickerDialog
# =============================================================================
class ProductPickerDialog(ctk.CTkToplevel):
    """Modal dialog for selecting a product from inventory by name or barcode.

    Uses AsyncUI to load products in a background thread, preventing the
    Tkinter event loop from blocking on large inventory tables.

    Args:
        parent:    Parent widget (PharmacyApp or frame).
        on_select: Callback(product_row) when "Add to Cart" is clicked or
                   a row is double-clicked.  ``product_row`` is the tuple
                   from ``database.get_all_products()``.
    """

    def __init__(self, parent: Any, on_select: Optional[Callable] = None,
                 **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._parent = parent
        self._on_select = on_select
        self._products: list = []

        self.title(i18n.t("product_picker_title"))
        self.resizable(True, True)
        self.grab_set()
        _center(self, 640, 480, parent)
        self.configure(fg_color=_PANEL)
        self._build()
        self.after(50, self._load_products)

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(
            hdr, text=i18n.t("product_picker_title"),
            font=_FONT_TITLE(), text_color="white",
        ).pack(anchor="w", padx=20, pady=14)
        ctk.CTkLabel(
            hdr, text=i18n.t("product_picker_subtitle"),
            font=_FONT_SMALL(), text_color=COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        # Search row + loading spinner
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", padx=16, pady=(0, 8))
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        self._search_entry = ctk.CTkEntry(
            search_row, textvariable=self._search_var,
            placeholder_text=i18n.t("product_search_placeholder"),
            width=280,
        )
        self._search_entry.pack(side="left")

        self._spinner = ctk.CTkProgressBar(search_row, orientation="horizontal")
        self._spinner.pack(side="right", fill="x", expand=True, padx=(8, 0))
        self._spinner.start()

        # Product Treeview
        tf = ctk.CTkFrame(self, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        cols = ("Product", "Price", "Vendor", "Internal Barcode")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=16)
        for c, w in zip(cols, (220, 80, 120, 100)):
            self._tree.heading(c, text=i18n.t({
                "Product": "product_name",
                "Price": "product_price_col",
                "Vendor": "product_vendor_col",
                "Internal Barcode": "product_int_barcode_col",
            }[c]))
            self._tree.column(c, width=w, anchor="w" if c == "Product" else "center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<Double-1>", self._on_row_activated)

        # Footer buttons
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(
            ftr, text=i18n.t("add_to_cart"),
            font=_FONT_BODY(), fg_color=_ACCENT, width=120,
            command=self._on_add,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            ftr, text=i18n.t("cancel"),
            font=_FONT_BODY(),
            fg_color="transparent", hover_color=_MUTED,
            width=80, command=self.destroy,
        ).pack(side="right")

    # ── Data loading (async → callback on main thread) ─────────────────────

    def _load_products(self) -> None:
        """Load products in a background thread via AsyncUI."""

        def _load():
            try:
                return database.get_all_products()
            except Exception as e:
                log.error("ProductPickerDialog product load failed: %s", e)
                return []

        def _on_done(products, error=None):
            self._products = products or []
            self._spinner.stop()
            self._spinner.pack_forget()
            self._populate_tree(self._products)

        if HAS_ASYNC and AsyncUI is not None:
            try:
                mgr = AsyncUI.get()
                if mgr._root is not None:
                    mgr.run(_load, callback=_on_done)
                    return
            except Exception as exc:
                log.debug("AsyncUI unavailable for ProductPickerDialog: %s", exc)

        # Synchronous fallback
        products = _load()
        _on_done(products, None)

    def _populate_tree(self, products: list) -> None:
        """Populate the Treeview (must run on main thread)."""
        for item in self._tree.get_children():
            self._tree.delete(item)

        if not products:
            self._tree.insert("", "end", values=(
                i18n.t("no_products_found"), "", "", ""))
            return

        for p in products:
            name = p[1] if len(p) > 1 else "?"
            try:
                price = self.app.currency.fmt(float(p[2] or 0))
            except (TypeError, ValueError):
                price = ""
            vendor = p[8] if len(p) > 8 and p[8] else "N/A"
            int_barcode = p[4] if len(p) > 4 and p[4] else ""
            self._tree.insert("", "end", values=(name, price, vendor, int_barcode))

    # ── Event handlers ─────────────────────────────────────────────────────

    def _on_search_change(self, *args) -> None:
        """Filter products client-side as the user types (no DB query)."""
        term = self._search_var.get().strip().lower()
        if not term:
            self._populate_tree(self._products)
            return

        filtered = [
            p for p in self._products
            if term in str(p[1]).lower()           # name
            or (len(p) > 4 and term in str(p[4]).lower())  # internal barcode
            or (len(p) > 3 and term in str(p[3]).lower())  # manufacturer barcode
        ]
        self._populate_tree(filtered)

    def _on_row_activated(self, event=None) -> None:
        """Add to cart on double-click of a Treeview row."""
        self._on_add()

    def _on_add(self) -> None:
        """Add the selected product to cart via the on_select callback."""
        sel = self._tree.selection()
        if not sel:
            return

        values = self._tree.item(sel[0], "values")
        product_name = values[0]

        # Match by name to find the original product row
        product = None
        for p in self._products:
            if p[1] == product_name:
                product = p
                break

        if product is None:
            return

        if self._on_select:
            self._on_select(product)
        self.destroy()


# =============================================================================
# ReceiptDetailDialog
# =============================================================================
class ReceiptDetailDialog(ctk.CTkToplevel):
    """Modal receipt viewer with line-item table, Print and Close buttons.

    Loads receipt header + items asynchronously via AsyncUI so the UI
    thread is never blocked by database I/O.

    Args:
        parent:    Parent widget.
        receipt_id: The receipt to display.
    """

    def __init__(self, parent: Any, receipt_id: int, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self._parent = parent
        self._receipt_id = receipt_id
        self._items: list = []
        self._receipt_info: dict = {}

        self.title(i18n.t("receipt_detail_title"))
        self.resizable(True, True)
        self.grab_set()
        _center(self, 600, 460, parent)
        self.configure(fg_color=_PANEL)
        self._build()
        self.after(50, self._load_receipt)

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x", padx=4, pady=(4, 0))
        self._hdr_label = ctk.CTkLabel(
            hdr, text=f"{i18n.t('receipt_detail_title')} #{self._receipt_id}",
            font=_FONT_TITLE(), text_color="white",
        )
        self._hdr_label.pack(anchor="w", padx=20, pady=14)
        self._hdr_meta = ctk.CTkLabel(
            hdr, text="", font=_FONT_SMALL(), text_color=COLOR_TEXT_SECONDARY,
        )
        self._hdr_meta.pack(anchor="w", padx=20, pady=(0, 12))

        # Line items Treeview
        tf = ctk.CTkFrame(self, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        cols = ("Item", "Qty", "Unit Price", "Line Total")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=14)
        for c, w in zip(cols, (240, 50, 90, 90)):
            self._tree.heading(c, text=c)
            self._tree.column(c, width=w, anchor="w" if c == "Item" else "center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

        # Totals row
        self._total_label = ctk.CTkLabel(
             tf, text=i18n.t('total_format', total=self.app.currency.fmt(0)),
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#10B981",
            anchor="e",
        )
        self._total_label.grid(row=1, column=0, sticky="e", pady=(8, 0))

        # Buttons
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(
            ftr, text=i18n.t("print_receipt"),
            font=_FONT_BODY(), fg_color=_ACCENT, width=120,
            command=self._on_print,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            ftr, text=i18n.t("cancel"),
            font=_FONT_BODY(),
            fg_color="transparent", hover_color=_MUTED,
            width=80, command=self.destroy,
        ).pack(side="right")

    # ── Data loading (async) ─────────────────────────────────────────────────

    def _load_receipt(self) -> None:
        """Fetch receipt header + items in a background thread."""

        def _load():
            try:
                items = database.get_receipt_items(self._receipt_id) or []
                # Fetch receipt header info
                conn = database.sqlite3.connect(database.get_db_path())
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, timestamp, total_amount, payment_method "
                    "FROM receipts WHERE id = ?",
                    (self._receipt_id,))
                row = cursor.fetchone()
                conn.close()
                header = {
                    "id": row[0] if row else self._receipt_id,
                    "timestamp": row[1] if row else "",
                    "total": float(row[2]) if row and row[2] else 0.0,
                    "method": row[3] if row and row[3] else "",
                }
                return items, header
            except Exception as e:
                log.error("ReceiptDetailDialog load failed: %s", e)
                return [], {}

        def _on_done(result, error=None):
            items, header = result
            self._items = items
            self._receipt_info = header
            self._populate()

        if HAS_ASYNC and AsyncUI is not None:
            try:
                mgr = AsyncUI.get()
                if mgr._root is not None:
                    mgr.run(_load, callback=_on_done)
                    return
            except Exception as exc:
                log.debug("AsyncUI unavailable for ReceiptDetailDialog: %s", exc)

        items, header = _load()
        _on_done((items, header), None)

    def _populate(self) -> None:
        """Populate the Treeview and header (main thread only)."""
        for iid in self._tree.get_children():
            self._tree.delete(iid)

        if not self._items:
            self._tree.insert("", "end", values=(
                i18n.t("receipt_no_items"), "", "", ""))

        subtotal = 0.0
        for idx, item in enumerate(self._items):
            tag = "even" if idx % 2 == 0 else "odd"
            name = item[2] if len(item) > 2 else "?"
            qty = item[3] if len(item) > 3 else 0
            price = float(item[4] or 0) if len(item) > 4 else 0.0
            line_total = qty * price
            subtotal += line_total
            self._tree.insert("", "end", values=(
                name, qty, self.app.currency.fmt(price), self.app.currency.fmt(line_total),
            ), tags=(tag,))

        total = self._receipt_info.get("total", subtotal)
        self._hdr_meta.configure(text=(
            f"{i18n.t('change_due')}: {self.app.currency.fmt(total)}  |  "
            f"Payment: {self._receipt_info.get('method', '')}  |  "
            f"Date: {self._receipt_info.get('timestamp', '')}"
        ))
        self._total_label.configure(
            text=self.app.currency.fmt(total))

    # ── Event handlers ─────────────────────────────────────────────────────

    def _on_print(self) -> None:
        """Regenerate and open the receipt file."""
        if not HAS_RECEIPT_ENGINE:
            messagebox.showinfo("Print", "receipt_engine not available.",
                                parent=self)
            return

        if not self._items:
            messagebox.showinfo(i18n.t("receipt_detail_title"),
                                i18n.t("receipt_no_items"), parent=self)
            return

        try:
            cart = [
                {"product_name": i[2], "quantity": i[3],
                 "price_at_time": float(i[4] or 0)}
                for i in self._items
            ]
            subtotal = sum(
                c["quantity"] * c["price_at_time"] for c in cart)
            filename = receipt_engine.generate_receipt(
                receipt_id=self._receipt_id,
                cart_items=cart,
                subtotal=subtotal,
                total=self._receipt_info.get("total", subtotal),
                payment_type=self._receipt_info.get("method", ""),
            )
            receipt_engine.open_receipt_file(filename)
        except Exception as e:
            messagebox.showerror("Print Error", str(e), parent=self)


# =============================================================================
#  GiftCardPanel (stub — backend schema pending)
# =============================================================================

class GiftCardPanel(ctk.CTkToplevel):
    """Gift card code entry + balance lookup.

    NOTE: The ``gift_cards`` table does not yet exist in ``database.py``.
    Until that schema migration lands, balance lookup and "Apply to Cart"
    are disabled and the panel explains the pending backend hook.
    """

    def __init__(self, parent: Any, **kw: Any) -> None:
        super().__init__(parent, **kw)
        self.title(i18n.t("gift_card"))
        self.resizable(False, False)
        self.grab_set()
        _center(self, 420, 320, parent)
        self.configure(fg_color=_PANEL)
        self._build()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="#252535", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=i18n.t("gift_card"),
                     font=_FONT_TITLE(), text_color="white").pack(anchor="w", padx=20, pady=14)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        _sec(body, i18n.t("gift_card_code"))
        self._code = ctk.CTkEntry(body, placeholder_text="GIFT-XXXX-XXXX",
                                   font=_FONT_BODY(), width=280, height=38)
        self._code.pack(anchor="w", pady=(4, 12))
        self._balance = ctk.CTkLabel(body, text=i18n.t("gift_card_balance_pending"),
                                      font=_FONT_BODY(), text_color=_MUTED)
        self._balance.pack(anchor="w", pady=(4, 8))
        _sep(self, (4, 8))
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(bf, text="Apply",
                      font=_FONT_BODY(), fg_color=_MUTED,
                      state="disabled", width=150).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text=i18n.t("cancel"), font=_FONT_BODY(),
                      fg_color="transparent", hover_color=_MUTED,
                      command=self.destroy, width=80).pack(side="right")

