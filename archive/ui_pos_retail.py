"""
ui_pos_retail.py — Enterprise POS Retail checkout for PharmacyPro.

Enhanced retail checkout with:
  - Quick-action grid for common operations (prescriptions, OTC, refills, returns)
  - Right-side action panel: Delivery, Gifts, OTC (prominent labeled buttons)
  - Side-panel triggers (patient lookup, insurance, notes, coupon, receipt, history)
  - Tax-exempt toggle with robust TaxCalculator engine
  - F12 payment processing (global binding + dedicated button)
  - Async background operations via AsyncUI thread pool (non-blocking SQLite)
  - SQLite WAL mode with exponential backoff retry on db lock
  - Observer pattern (CartObserver) for cart state management

Integrates with:
  - database.get_product_by_barcode / get_product_by_internal_barcode
  - database.checkout_cart_atomically (expects ``internal_barcodes: list[str]``)
  - database.get_all_patients
  - barcode_logic.load_config (tax_rate 0-100)
  - audit_log.log_action
  - async_ui.AsyncUI (thread-safe ``root.after()`` callback marshaling)

F12 binding:
  - Global ``app.bind("<F12>")`` fires ``_process_payment()`` when tab is
    ``status_dashboard_title`` or ``clinical_workflow_title``.
  - Dedicated Process Payment button also triggers payment on the POS Retail tab.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime
from typing import Any, Callable, TypedDict

import customtkinter as ctk
from tkinter import ttk, messagebox

# ── CTkSpinbox compatibility shim (CTk 6.0 removed CTkSpinbox) ─────────────
if not hasattr(ctk, "CTkSpinbox"):
    class _CTkSpinboxCompat(ctk.CTkEntry):
        """Minimal CTkSpinbox shim backed by CTkEntry.

        Provides the subset of the CTkSpinbox API used by this module:
        ``from_``, ``to``, ``width`` constructor kwargs, ``.set()``,
        ``.get()``, and standard geometry managers (``.grid()``).
        """
        def __init__(self, parent, from_=0, to=100, width=120, **kwargs):
            super().__init__(parent, width=width, **kwargs)

        def set(self, value: Any) -> None:
            super().set(str(value))

    ctk.CTkSpinbox = _CTkSpinboxCompat

import i18n
import database
import audit_log
import auth_session
import authz
import barcode_logic
import ui_pos_panels
import localization_manager
import ui_tooltip
from ui_helpers import apply_treeview_style
from ui_navigation import (
    COLOR_CARD_BG, COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_SIDEBAR_BG, COLOR_SIDEBAR_HOVER,
)

log = logging.getLogger("ui_pos_retail")

# ── Payment method constants (logic uses keys, UI shows translated text) ──
PAYMENT_CASH = "cash"
PAYMENT_CARD = "card"
PAYMENT_TRANSFER = "transfer"
_PAYMENT_KEYS = (PAYMENT_CASH, PAYMENT_CARD, PAYMENT_TRANSFER)

# ── Sale Type constants ───────────────────────────────────────────────────
POS_SALE_TYPES = ("OTC", "Rx OTC", "Delivery", "Loyalty", "Gifts")
_SALE_TYPE_COLORS = {
    "OTC": "#3b82f6",
    "Rx OTC": "#2563eb",
    "Delivery": "#8b5cf6",
    "Loyalty": "#ec4899",
    "Gifts": "#f59e0b",
}

# ── Insurance coverage defaults (region-aware fallback) ──────────────────
_DEFAULT_INSURANCE_COVERAGE = {
    "US": {"copay": 5.0, "coinsurance_rate": 0.2},
    "GB": {"patient_contribution": 0.1, "vat_rate": 0.2},
    "DE": {"patient_contribution": 0.1, "vat_rate": 0.19},
}

# ── AsyncUI (optional — graceful fallback to synchronous) ──
try:
    from async_ui import AsyncUI
    HAS_ASYNC: bool = True
except ImportError:
    AsyncUI = None  # type: ignore[assignment]
    HAS_ASYNC = False
    log.warning("async_ui not available; background tasks will run synchronously")


# ─────────────────────────────────────────────────────────────────────
#  Data Structures
# ─────────────────────────────────────────────────────────────────────


class TaxBreakdown(TypedDict):
    """Immutable breakdown of a cart's financial totals."""
    subtotal: float
    tax_amount: float
    total: float
    item_count: int
    tax_rate: float
    tax_exempt: bool


class TaxCalculator:
    """Pure tax engine with no DB or UI dependencies.

    Tax rate is read from ``barcode_logic.load_config()`` (stored as
    0-100 percentage).  All arithmetic is O(n) over cart lines where n
    = number of cart entries.
    """

    def __init__(self, tax_rate: float = 0.0, tax_exempt: bool = False) -> None:
        self._tax_rate: float = tax_rate
        self._tax_exempt: bool = tax_exempt

    @classmethod
    def from_config(cls, tax_exempt: bool = False) -> "TaxCalculator":
        """Construct a TaxCalculator using the current config ``tax_rate``."""
        try:
            config = barcode_logic.load_config()
            rate = float(config.get("tax_rate", 0.0))
        except Exception:
            rate = 0.0
        return cls(tax_rate=rate, tax_exempt=tax_exempt)

    def is_taxable(self) -> bool:
        return not self._tax_exempt

    def rate(self) -> float:
        """Return tax_rate as a fraction (0.08 instead of 8.0)."""
        if self._tax_exempt:
            return 0.0
        return self._tax_rate / 100.0

    def calculate_line_tax(self, unit_price: float, qty: int) -> float:
        """Calculate tax for a single line.  O(1)."""
        if not self.is_taxable():
            return 0.0
        return unit_price * qty * self.rate()

    def calculate_totals(self, cart: list[dict[str, Any]]) -> TaxBreakdown:
        """Calculate subtotal / tax / total for a cart.  O(n) where n = len(cart)."""
        subtotal = 0.0
        total_tax = 0.0
        item_count = 0

        for item in cart:
            qty = item.get("qty", 1)
            price = item.get("price", 0.0)
            line_total = price * qty
            subtotal += line_total
            total_tax += self.calculate_line_tax(price, qty)
            item_count += qty

        return TaxBreakdown(
            subtotal=round(subtotal, 2),
            tax_amount=round(total_tax, 2),
            total=round(subtotal + total_tax, 2),
            item_count=item_count,
            tax_rate=self._tax_rate,
            tax_exempt=self._tax_exempt,
        )


class SqliteWALConnection:
    """Context manager for SQLite connections with WAL mode and retry.

    Enables ``PRAGMA journal_mode=WAL``, ``busy_timeout``, and
    ``synchronous=NORMAL`` so that reads and writes can proceed
    concurrently without blocking the UI thread.

    Usage::

        with SqliteWALConnection(db_path) as (conn, cur):
            cur.execute("SELECT ... WHERE col = ?", (val,))
            rows = cur.fetchall()
    """

    def __init__(self, db_path: str, max_retries: int = 3,
                 initial_delay: float = 0.1) -> None:
        self._db_path: str = db_path
        self._max_retries: int = max_retries
        self._initial_delay: float = initial_delay
        self._conn: sqlite3.Connection | None = None

    # -- context manager protocol --
    def __enter__(self) -> tuple[sqlite3.Connection, sqlite3.Cursor]:
        for attempt in range(self._max_retries):
            try:
                conn = sqlite3.connect(
                    self._db_path,
                    timeout=30.0,
                    isolation_level=None,  # autocommit; we manage transactions
                    check_same_thread=False,
                )
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("PRAGMA synchronous=NORMAL")
                self._conn = conn
                return conn, conn.cursor()
            except sqlite3.OperationalError as exc:
                delay = self._initial_delay * (2 ** attempt)
                log.warning(
                    "SQLite WAL connect attempt %d/%d failed: %s — retrying in %.2fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                time.sleep(delay)
        raise sqlite3.OperationalError(
            f"Failed to acquire SQLite connection after {self._max_retries} attempts"
        )

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


class CartObserver:
    """Observer pattern for cart state change notifications.

    Decouples the cart model from UI views: any subscriber can register
    a callback that receives ``(event_name, data_dict)``.
    """

    def __init__(self) -> None:
        self._observers: list[Callable[[str, dict[str, Any]], None]] = []

    def register(self, callback: Callable[[str, dict[str, Any]], None]) -> int:
        """Register *callback*; returns its slot index."""
        self._observers.append(callback)
        return len(self._observers) - 1

    def unregister(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Remove a previously-registered callback."""
        try:
            self._observers.remove(callback)
        except ValueError:
            pass

    def notify(self, event: str, data: dict[str, Any]) -> None:
        """Invoke every observer with *event* and *data*."""
        for observer in list(self._observers):
            try:
                observer(event, data)
            except Exception as exc:
                log.error("Cart observer error on '%s': %s", event, exc)


# ─────────────────────────────────────────────────────────────────────
#  Quick-action & trigger definitions
# ─────────────────────────────────────────────────────────────────────

_QUICK_ACTIONS: list[tuple[str, str, str]] = [
    ("quick_action_prescription", "💊", "prescription"),
    ("quick_action_refill", "🔄", "refill"),
    ("quick_action_return", "↩️", "return"),
    ("quick_action_discount", "🏷️", "discount"),
    ("quick_action_price_override", "💲", "price_override"),
    ("quick_action_void", "🚫", "void"),
    ("quick_action_split", "✂️", "split"),
    ("quick_action_gift", "💳", "giftcard"),
    ("quick_action_memo", "📝", "memo"),
    ("quick_action_customer", "👤", "customer"),
    ("quick_action_eod", "🔒", "eod"),
    ("quick_action_delivery", "🚚", "delivery"),
    ("quick_action_gifts", "🎁", "gifts"),
    ("quick_action_otc", "📦", "otc"),
]

_SIDE_TRIGGERS: list[tuple[str, str, str]] = [
    ("trigger_patient_lookup", "👥", "patient_lookup"),
    ("trigger_insurance", "🛡️", "insurance"),
    ("trigger_notes", "📝", "notes"),
    ("trigger_coupon", "🏷️", "coupon"),
    ("trigger_receipt", "🧾", "receipt"),
    ("trigger_history", "📜", "history"),
]

# ---------------------------------------------------------------------------
#  Main Frame
# ---------------------------------------------------------------------------


class EnterprisePosFrame(ctk.CTkFrame):
    """Enterprise POS retail checkout frame.

    Layout (3-column grid):

    Row 0 (fixed height):  Search bar — title, barcode entry, search button
    Row 1 (expands):       Workspace
      Column 0 (weight 3): Quick-action grid + cart Treeview
      Column 1 (weight 1): Balance summary card (subtotal, tax, total,
                           tax-exempt, payment method, tendered, change, F12 pay)
      Column 2 (fixed 180): Right-side action panel — Delivery, Gifts, OTC
                             + side-panel triggers

    Cart entries passed to ``database.checkout_cart_atomically`` use the
    Phase 13 schema with ``internal_barcodes: list[str]`` (plural, list).
    """

    def __init__(self, parent: Any, app: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=kwargs.pop("fg_color", "transparent"), **kwargs)
        # ── App reference (must be set BEFORE any UI layout construction) ──
        self.app: Any = app
        self._app: Any = app

        # ── State ──
        self._cart: list[dict[str, Any]] = []
        self._fees: list[dict[str, Any]] = []
        self._sale_memo: str = ""
        self._tax_exempt: bool = False
        self._payment_method: str = PAYMENT_CASH
        self._amount_tendered: float = 0.0
        self._selected_patient: dict[str, Any] | None = None
        self._sale_type: str = "OTC"
        self._insurance_applied: bool = False
        self._insurance_copay: float = 0.0
        self._insurance_amount: float = 0.0
        self._insurance_label_text: str = ""
        self._observer: CartObserver = CartObserver()

        # Wire internal observer for balance updates
        self._observer.register(self._on_cart_changed)

        self._configure_grid()
        self._build_search_bar()
        self._build_main_workspace()
        self._init_async()

    # ── Layout ───────────────────────────────────────────────────

    def _configure_grid(self) -> None:
        """Set up the 3-column grid on the root frame."""
        self.grid_columnconfigure(0, weight=3)   # quick-actions + cart
        self.grid_columnconfigure(1, weight=2)   # balance summary
        self.grid_columnconfigure(2, weight=0)   # right-side action panel (fixed)
        self.grid_rowconfigure(0, weight=0)      # search bar
        self.grid_rowconfigure(1, weight=1)      # workspace

    def _build_search_bar(self) -> None:
        """Row 0 — title, barcode entry, and search button."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=3, sticky="ew",
                 padx=16, pady=(16, 8))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar,
            text=i18n.t("pos_retail_title"),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctrl = ctk.CTkFrame(bar, fg_color="transparent")
        ctrl.grid(row=0, column=1, sticky="e")
        ctrl.grid_columnconfigure(0, weight=1)

        self._search_entry = ctk.CTkEntry(
            ctrl, width=260,
            placeholder_text=i18n.t("pos_search_placeholder"),
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._search_entry.bind("<Return>", self._on_search_enter)

        ctk.CTkButton(
            ctrl, text=i18n.t("search"), width=80,
            command=self._on_search_enter,
        ).grid(row=0, column=1)

    def _build_main_workspace(self) -> None:
        """Row 1 — quick-actions/cart (left), balance (center), action panel (right)."""
        self._build_left_panel()
        self._build_balance_summary()
        self._build_action_panel()

    def _build_left_panel(self) -> None:
        """Left column: quick-action grid + cart treeview."""
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(16, 0), pady=8)
        left.grid_rowconfigure(3, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # Quick-action header
        ctk.CTkLabel(
            left, text=i18n.t("quick_sig_suggestions"),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        # Quick-action grid (3 × 3)
        grid = ctk.CTkFrame(left, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        grid.grid_columnconfigure(tuple(range(3)), weight=1)
        grid.grid_rowconfigure((0, 1, 2, 3), weight=1)

        for idx, (key, icon, action) in enumerate(_QUICK_ACTIONS):
            r, c = divmod(idx, 3)
            ctk.CTkButton(
                grid,
                text=f"{icon}\n{i18n.t(key)}",
                height=80,
                width=140,
                command=lambda a=action: self._on_quick_action(a),
                fg_color="transparent",
                hover_color=COLOR_SIDEBAR_HOVER,
                text_color=COLOR_TEXT_PRIMARY,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=r, column=c, sticky="nsew", padx=4, pady=4)

        # Cart header
        ctk.CTkLabel(
            left, text=i18n.t("cart_pos"),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=2, column=0, sticky="w", pady=(0, 8))

        # Cart Treeview
        cols = ("Item", "Qty", "Unit Price", "Tax", "Total")
        self._cart_tree = ttk.Treeview(
            left, columns=cols, show="headings", height=8,
        )
        self._cart_tree.heading("Item", text=i18n.t("item"))
        self._cart_tree.heading("Qty", text=i18n.t("quantity"))
        self._cart_tree.heading("Unit Price", text=i18n.t("unit_price"))
        self._cart_tree.heading("Tax", text=i18n.t("pos_tax"))
        self._cart_tree.heading("Total", text=i18n.t("pos_total"))
        apply_treeview_style(self._cart_tree)
        self._cart_tree.column("Item", width=140, anchor="w")
        self._cart_tree.column("Qty", width=50, anchor="center")
        self._cart_tree.column("Unit Price", width=75, anchor="e")
        self._cart_tree.column("Tax", width=60, anchor="e")
        self._cart_tree.column("Total", width=80, anchor="e")
        self._cart_tree.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        self._cart_tree.bind("<Delete>", self._remove_selected)
        self._cart_tree.bind("<<TreeviewSelect>>", self._on_cart_select)

        vsb = ttk.Scrollbar(left, orient="vertical", command=self._cart_tree.yview)
        self._cart_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=3, column=0, sticky="nse", pady=(0, 8))

        # Cart toolbar: qty adjust + clear
        cart_toolbar = ctk.CTkFrame(left, fg_color="transparent")
        cart_toolbar.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        cart_toolbar.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            cart_toolbar, text=f"{i18n.t('quantity')}:",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w")

        self._qty_spinbox = ctk.CTkSpinbox(
            cart_toolbar, from_=1, to=999, width=100,
        )
        self._qty_spinbox.set("1")
        self._qty_spinbox.grid(row=0, column=1, sticky="w")

        ctk.CTkButton(
            cart_toolbar, text=i18n.t("remove_from_cart"), width=100,
            command=self._remove_selected,
        ).grid(row=0, column=2, padx=4)

        ctk.CTkButton(
            cart_toolbar, text=i18n.t("clear_cart"), width=100,
            command=self._clear_cart,
        ).grid(row=0, column=3, sticky="e")

    def _build_balance_summary(self) -> None:
        """Center column: balance summary card with payment controls."""
        card = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=8)
        card.grid(row=1, column=1, sticky="nsew", padx=16, pady=8)
        card.grid_propagate(False)
        card.configure(width=240)
        card.grid_columnconfigure(0, weight=1)

        # Header
        hdr_frame = ctk.CTkFrame(card, fg_color="transparent")
        hdr_frame.pack(fill="x", pady=(16, 4))
        
        ctk.CTkLabel(
            hdr_frame, text=i18n.t("pos_retail_title"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=24)
        
        self._sale_type_badge = ctk.CTkLabel(
            hdr_frame, text="OTC",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="white", fg_color="#3b82f6",
            corner_radius=4, width=40, height=20,
        )
        self._sale_type_badge.pack(side="right", padx=24)

        self._items_count_label = ctk.CTkLabel(
            card, text=i18n.t("pos_items_count", count=0),
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self._items_count_label.pack(fill="x", padx=24, pady=2)

        self._subtotal_label = ctk.CTkLabel(
            card, text=f"{i18n.t('pos_subtotal')}: {self.app.currency.fmt(0)}",
            font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self._subtotal_label.pack(fill="x", padx=24, pady=2)

        self._fees_label = ctk.CTkLabel(
            card, text=i18n.t("pos_retail_fees") + ": " + self.app.currency.fmt(0),
            font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self._fees_label.pack(fill="x", padx=24, pady=2)

        self._tax_label = ctk.CTkLabel(
            card, text=f"{i18n.t('pos_tax')}: {self.app.currency.fmt(0)}",
            font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self._tax_label.pack(fill="x", padx=24, pady=2)

        self._total_label = ctk.CTkLabel(
            card, text=i18n.t("total_format", total="0.00"),
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLOR_SUCCESS, anchor="e",
        )
        self._total_label.pack(fill="x", padx=24, pady=(8, 4))

        # Tax-exempt toggle
        self._tax_exempt_check = ctk.CTkCheckBox(
            card, text=i18n.t("pos_retail_tax_exempt"),
            command=self._on_tax_exempt_toggle,
        )
        self._tax_exempt_check.pack(pady=(8, 0))
        ui_tooltip.attach_key(self._tax_exempt_check, "tip_pos_tax_exempt")

        # Payment method selector
        ctk.CTkLabel(
            card, text=i18n.t("payment_method"),
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY,
        ).pack(pady=(12, 2))

        self._payment_menu = ctk.CTkComboBox(
            card,
            values=[i18n.t(PAYMENT_CASH), i18n.t(PAYMENT_CARD), i18n.t(PAYMENT_TRANSFER)],
            width=180,
            command=self._on_payment_method_change,
        )
        # Force the entry part of the combobox to be read-only so users only pick from dropdown or programmatic updates
        self._payment_menu.configure(state="readonly")
        self._payment_menu.set(i18n.t(PAYMENT_CASH))
        self._payment_menu.pack(pady=2)
        ui_tooltip.attach_key(self._payment_menu, "tip_pos_payment_method")

        # Re-sync combobox display if the user switches language at runtime
        def _on_payment_lang_change(_code):
            if not self.winfo_exists():
                return
            self._payment_menu.configure(
                values=[i18n.t(k) for k in _PAYMENT_KEYS]
            )
            if self._payment_method in _PAYMENT_KEYS:
                self._payment_menu.set(i18n.t(self._payment_method))
            # Keep the patient + change-due labels in sync with the new language
            if getattr(self, "_patient_label", None) and self._patient_label.winfo_exists():
                current = self._patient_label.cget("text")
                # Only re-localize the placeholder (not a selected patient name)
                if current in (i18n.t("select_a_patient"), "—"):
                    self._patient_label.configure(text=i18n.t("select_a_patient"))
            if getattr(self, "_change_due_label", None) and self._change_due_label.winfo_exists():
                self._change_due_label.configure(
                    text=f"{i18n.t('change_due')}: {self.app.currency.fmt(0)}"
                )
        i18n.on_language_change(_on_payment_lang_change)

        # Amount tendered + change due (shown only for Cash)
        self._tendered_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._tendered_frame.pack(fill="x", padx=24, pady=(8, 4))

        ctk.CTkLabel(
            self._tendered_frame, text=i18n.t("amount_tendered"),
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        self._tendered_entry = ctk.CTkEntry(
            self._tendered_frame, width=160, placeholder_text=self.app.currency.fmt(0),
        )
        self._tendered_entry.pack(anchor="w")
        self._tendered_entry.bind("<KeyRelease>", self._on_amount_tendered_change)
        self._tendered_entry.bind("<Return>", self._on_amount_tendered_change)
        ui_tooltip.attach_key(self._tendered_entry, "tip_pos_amount_tendered")

        self._change_due_label = ctk.CTkLabel(
            card, text=i18n.t("change_due") + ": " + self.app.currency.fmt(0),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_WARNING, anchor="e",
        )
        self._change_due_label.pack(fill="x", padx=24, pady=4)

        # Patient display
        self._patient_label = ctk.CTkLabel(
            card, text=i18n.t("select_a_patient"),
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self._patient_label.pack(fill="x", padx=24, pady=(4, 0))

        # Insurance copay / patient cost display (hidden by default)
        self._insurance_cost_label = ctk.CTkLabel(
            card,
            text=i18n.t("insurance_cost") + ": " + self.app.currency.fmt(0),
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self._insurance_cost_label.pack(fill="x", padx=24, pady=2)

        self._patient_cost_label = ctk.CTkLabel(
            card,
            text=i18n.t("patient_cost") + ": " + self.app.currency.fmt(0),
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self._patient_cost_label.pack(fill="x", padx=24, pady=2)

        self._insurance_cost_label.pack_forget()
        self._patient_cost_label.pack_forget()

        # Process payment button
        self._pay_btn = ctk.CTkButton(
            card, text=f"💳 {i18n.t('pos_retail_process_payment')}",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._process_payment,
        )
        self._pay_btn.pack(fill="x", padx=24, pady=(12, 20))
        ui_tooltip.attach_key(self._pay_btn, "tip_pos_process_payment")

    def _build_action_panel(self) -> None:
        """Right column (fixed width): Delivery, Gifts, OTC + side triggers."""
        self._action_panel = ctk.CTkFrame(
            self, fg_color=COLOR_CARD_BG, corner_radius=8,
        )
        self._action_panel.grid(
            row=1, column=2, sticky="ns", padx=(0, 16), pady=8,
        )
        self._action_panel.grid_propagate(False)
        self._action_panel.configure(width=180)
        self._action_panel.grid_columnconfigure(0, weight=1)

        # Patient selection
        self._patient_menu = ctk.CTkComboBox(
            self._action_panel,
            values=[i18n.t("select_a_patient")],
            width=160,
        )
        self._patient_menu.pack(pady=(12, 4))
        self._patient_menu.set(i18n.t("select_a_patient"))

        # ── Side-panel triggers ──
        trigger_header = ctk.CTkLabel(
            self._action_panel, text=i18n.t("toolbar_settings"),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        trigger_header.pack(pady=(12, 6))

        for key, icon, action in _SIDE_TRIGGERS:
            btn = ctk.CTkButton(
                self._action_panel,
                text=f"{icon} {i18n.t(key)}",
                height=32,
                command=lambda a=action: self._on_side_trigger(a),
                fg_color="transparent",
                hover_color=COLOR_SIDEBAR_HOVER,
                text_color=COLOR_TEXT_PRIMARY,
                font=ctk.CTkFont(size=11),
            )
            btn.pack(fill="x", padx=12, pady=2)

    # ── Async helpers ─────────────────────────────────────────

    def _init_async(self) -> None:
        """Bind AsyncUI root if available so callbacks marshal to the main thread."""
        if not HAS_ASYNC:
            return
        try:
            mgr = AsyncUI.get()  # type: ignore[union-attr]
            if mgr._root is None:
                root = self.winfo_toplevel()
                mgr.init(root)
        except Exception as exc:
            log.debug("AsyncUI init deferred: %s", exc)

    def _run_async(
        self,
        func: Callable,
        callback: Callable[[Any, Any], None],
        args: tuple = (),
    ) -> None:
        """Submit *func* to the AsyncUI thread pool; marshal *callback* to main thread."""
        if HAS_ASYNC and AsyncUI is not None:
            try:
                mgr = AsyncUI.get()  # type: ignore[union-attr]
                if mgr._root is not None:
                    mgr.run(func=func, callback=callback, args=args)
                    return
            except Exception as exc:
                log.debug("AsyncUI run unavailable, falling back to sync: %s", exc)
        self._run_sync(func, callback, args)

    def _run_sync(
        self,
        func: Callable,
        callback: Callable[[Any, Any], None],
        args: tuple = (),
    ) -> None:
        """Run *func* synchronously and invoke *callback* via ``after(0)`` on the main thread."""
        try:
            result = func(*args) if args else func()
        except Exception as exc:
            result = None
            log.error("Sync task error: %s", exc)
        self.after(0, lambda: callback(result, None))

    # ── Search ────────────────────────────────────────────────

    def _on_search_enter(self, event: Any = None) -> None:
        """Handle barcode search entry — submit lookup to background thread."""
        barcode = self._search_entry.get().strip()
        if not barcode:
            return
        self._search_entry.configure(state="disabled")
        self._search_entry.set_placeholder_text(i18n.t("loading"))
        self._run_async(
            func=self._do_search_product,
            callback=self._on_search_done,
            args=(barcode,),
        )

    def _do_search_product(self, barcode: str) -> tuple | None:
        """Look up a product by internal barcode then manufacturer barcode.  O(1) per query.

        Uses ``SqliteWALConnection`` for WAL-mode reads with retry.
        """
        try:
            db_path = database.get_db_path()
            with SqliteWALConnection(db_path) as (conn, cur):
                cur.execute(
                    "SELECT id, name, price, manufacturer_barcode, "
                    "internal_unique_barcode, status, expiry_date, "
                    "manufacture_date, vendor_name "
                    "FROM products WHERE internal_unique_barcode = ? "
                    "AND status = 'In Stock'",
                    (barcode,),
                )
                product = cur.fetchone()
                if not product:
                    cur.execute(
                        "SELECT id, name, price, manufacturer_barcode, "
                        "internal_unique_barcode, status, expiry_date, "
                        "manufacture_date, vendor_name "
                        "FROM products WHERE manufacturer_barcode = ? "
                        "AND status = 'In Stock'",
                        (barcode,),
                    )
                    product = cur.fetchone()
                return product
        except sqlite3.OperationalError as exc:
            log.error("Search SQLite error: %s", exc)
            return None
        except Exception as exc:
            log.error("Unexpected search error: %s", exc)
            return None

    def _on_search_done(self, product: tuple | None, error: Any) -> None:
        """Callback (main thread): add found product to cart or warn."""
        self._search_entry.configure(state="normal")
        self._search_entry.set_placeholder_text(i18n.t("pos_search_placeholder"))

        if error:
            log.error("Search failed: %s", error)
            messagebox.showerror(i18n.t("error"), str(error))
            return

        if product:
            self._add_to_cart(product)
            self._search_entry.delete(0, "end")
            self._search_entry.focus_set()
        else:
            barcode = self._search_entry.get().strip()
            messagebox.showwarning(
                i18n.t("info"),
                f"'{barcode}' {i18n.t('no_inventory_found')}",
            )
            self._search_entry.delete(0, "end")
            self._search_entry.focus_set()

    # ── Cart management ──────────────────────────────────────

    def _add_to_cart(self, product: tuple) -> None:
        """Add a product tuple to the cart, consolidating with existing entries.

        Product tuple layout (index): 0=id, 1=name, 2=price, 3=mfg_bc,
        4=int_bc, 5=status, 6=expiry_date, 7=mfg_date, 8=vendor_name.

        Time complexity: O(n) where n = current cart size (for deduplication).
        """
        internal_bc = product[4] if len(product) > 4 else product[3] if len(product) > 3 else ""
        name = product[1] if len(product) > 1 else "Unknown"
        price = float(product[2]) if len(product) > 2 and product[2] else 0.0
        vendor = product[8] if len(product) > 8 and product[8] else "N/A"
        expiry = product[6] if len(product) > 6 and product[6] else "N/A"

        for entry in self._cart:
            if entry["name"] == name and entry.get("vendor") == vendor:
                entry["qty"] += 1
                entry["internal_barcodes"].append(internal_bc)
                self._observer.notify("cart_updated", {"entry": entry})
                self._update_cart_display()
                return

        entry = {
            "name": name,
            "price": price,
            "qty": 1,
            "internal_barcodes": [internal_bc],  # list — matches checkout_cart_atomically
            "vendor": vendor,
            "expiry_date": expiry,
        }
        self._cart.append(entry)
        self._observer.notify("item_added", {"entry": entry})
        self._update_cart_display()

    def _remove_selected(self, event: Any = None) -> None:
        """Remove the selected cart line(s) from the tree and the cart list."""
        selected = self._cart_tree.selection()
        if not selected:
            return
        for item_id in selected:
            values = self._cart_tree.item(item_id, "values")
            name = values[0]
            for entry in self._cart:
                if entry["name"] == name:
                    self._cart.remove(entry)
                    self._observer.notify("item_removed", {"entry": entry})
                    break
        self._update_cart_display()

    def _clear_cart(self) -> None:
        """Clear all items from the cart."""
        if self._cart:
            self._cart.clear()
            self._observer.notify("cart_cleared", {})
            self._update_cart_display()

    def _update_cart_display(self) -> None:
        """Rebuild the Treeview rows and refresh all balance labels.  O(n)."""
        for row in self._cart_tree.get_children():
            self._cart_tree.delete(row)

        calc = TaxCalculator.from_config(tax_exempt=self._tax_exempt)
        breakdown = calc.calculate_totals(self._cart)
        fees_total = sum(f.get("amount", 0.0) for f in self._fees)
        grand_total = breakdown["subtotal"] + breakdown["tax_amount"] + fees_total

        for entry in self._cart:
            qty = entry["qty"]
            price = entry["price"]
            line_total = price * qty
            line_tax = calc.calculate_line_tax(price, qty)
            self._cart_tree.insert("", "end", values=(
                entry["name"], qty,
                self.app.currency.fmt(price),
                self.app.currency.fmt(line_tax),
                self.app.currency.fmt(line_total),
            ))

        self._subtotal_label.configure(
            text=f"{i18n.t('pos_subtotal')}: {self.app.currency.fmt(breakdown['subtotal'])}",
        )
        self._fees_label.configure(
            text=f"{i18n.t('pos_retail_fees')}: {self.app.currency.fmt(fees_total)}",
        )
        self._tax_label.configure(
            text=f"{i18n.t('pos_tax')}: {self.app.currency.fmt(breakdown['tax_amount'])}",
        )
        self._total_label.configure(
            text=i18n.t("total_format", total=self.app.currency.fmt(grand_total)),
        )
        self._items_count_label.configure(
            text=i18n.t("pos_items_count", count=len(self._cart)),
        )

        # Insurance labels
        if self._insurance_applied:
            self._insurance_cost_label.configure(
                text=f"{i18n.t('insurance_cost')}: {self.app.currency.fmt(self._insurance_amount)}",
                text_color=COLOR_TEXT_SECONDARY,
            )
            self._patient_cost_label.configure(
                text=f"{i18n.t('patient_cost')}: {self.app.currency.fmt(self._insurance_copay)}",
                text_color=COLOR_SUCCESS,
            )
            self._insurance_cost_label.pack(fill="x", padx=24, pady=2)
            self._patient_cost_label.pack(fill="x", padx=24, pady=2)
            if self._insurance_label_text:
                self._patient_label.configure(
                    text=f"{i18n.t('patient_label')}: {self._insurance_label_text}"
                )
        else:
            self._insurance_cost_label.pack_forget()
            self._patient_cost_label.pack_forget()

        self._on_amount_tendered_change()

    def _on_cart_changed(self, event: str, data: dict[str, Any]) -> None:
        """Internal CartObserver callback — recomputes balances on every cart change."""
        self._update_cart_display()

    def _on_tax_exempt_toggle(self) -> None:
        """Toggle tax-exempt mode and recompute totals."""
        self._tax_exempt = bool(self._tax_exempt_check.get())
        log.info("Tax-exempt toggled: %s", self._tax_exempt)
        self._update_cart_display()

    def _payment_key_from_display(self, display: str) -> str:
        """Map a combobox display label back to its payment-method key."""
        for key in _PAYMENT_KEYS:
            if i18n.t(key) == display:
                return key
        return PAYMENT_CASH

    def _on_payment_method_change(self, method: str) -> None:
        """Switch payment method; show/hide amount-tendered for Cash."""
        self._payment_method = self._payment_key_from_display(method)
        log.info("Payment method changed: %s", method)
        if self._payment_method == PAYMENT_CASH:
            self._tendered_frame.pack(fill="x", padx=24, pady=(8, 4))
        else:
            self._tendered_frame.pack_forget()
        self._on_amount_tendered_change()

    def _on_amount_tendered_change(self, event: Any = None) -> None:
        """Compute change due from the amount-tendered entry."""
        try:
            raw = self._tendered_entry.get().strip()
            self._amount_tendered = float(raw) if raw else 0.0
        except ValueError:
            self._amount_tendered = 0.0

        calc = TaxCalculator.from_config(tax_exempt=self._tax_exempt)
        breakdown = calc.calculate_totals(self._cart)
        total = breakdown["total"] + sum(f.get("amount", 0.0) for f in self._fees)
        change = self._amount_tendered - total

        if self._amount_tendered > 0:
            if change < 0:
                self._change_due_label.configure(
                    text=f"{i18n.t('insufficient_payment')} {self.app.currency.fmt(abs(change))}",
                    text_color=COLOR_ERROR,
                )
            else:
                self._change_due_label.configure(
                    text=f"{i18n.t('change_due')}: {self.app.currency.fmt(change)}",
                    text_color=COLOR_SUCCESS if change >= 0 else COLOR_ERROR,
                )
        else:
            self._change_due_label.configure(
                text=i18n.t("change_due") + ": " + self.app.currency.fmt(0),
                text_color=COLOR_TEXT_SECONDARY,
            )

    def _set_sale_memo(self, memo: str) -> None:
        self._sale_memo = memo
        log.info("Sale memo set: %s", memo)

    def _update_sale_type_badge(self) -> None:
        color = _SALE_TYPE_COLORS.get(self._sale_type, "#3b82f6")
        self._sale_type_badge.configure(text=self._sale_type, fg_color=color)

    def _on_split_confirm(self, cash: float, card: float, label: str) -> None:
        self._payment_method = "Split"
        # Temporarily allow writing to update the value
        self._payment_menu.configure(state="normal")
        self._payment_menu.set(label)
        self._payment_menu.configure(state="readonly")
        self._amount_tendered = cash + card
        self._tendered_entry.delete(0, "end")
        self._tendered_entry.insert(0, str(self._amount_tendered))
        self._on_amount_tendered_change()

    def _on_side_trigger(self, action: str) -> None:
        """Handle side-panel trigger button clicks."""
        log.info("Side trigger clicked: %s", action)
        if action == "patient_lookup":
            self._select_patient()
        elif action == "insurance":
            ui_pos_panels.InsurancePanel(
                self, patient=self._selected_patient, app=self._app,
                on_apply=self._on_insurance_apply,
            )
        elif action == "notes":
            ui_pos_panels.NotesPanel(self, existing_memo=self._sale_memo, on_save=self._set_sale_memo)
        elif action == "coupon":
            calc = TaxCalculator.from_config(tax_exempt=self._tax_exempt)
            sub = calc.calculate_totals(self._cart)["subtotal"]
            ui_pos_panels.CouponPanel(self, fees=self._fees, cart_subtotal=sub, on_apply=self._update_cart_display)
        elif action == "receipt":
            ui_pos_panels.ReceiptHistoryPanel(self)
        elif action == "history":
            ui_pos_panels.CustomerHistoryPanel(self, patient=self._selected_patient)

    def _on_insurance_apply(self, info: dict[str, Any]) -> None:
        """InsurancePanel 'Apply to Sale' callback.

        Calculates patient copay using the regional billing strategy,
        then updates the balance summary to reflect patient cost vs.
        insurance coverage.  Falls back to default coverage parameters
        when insurance metadata (e.g. copay amount) is not stored.
        """
        if not info or not info.get("id"):
            log.warning("Insurance apply: no patient info provided")
            return

        audit_log.log_action(
            "pos_insurance_apply",
            details=f"patient_id={info.get('id')}",
            user_pin=str(auth_session.current_user_id() or ""),
        )

        subtotal = sum(item["price_at_time"] * item["quantity"] for item in self._cart)
        if subtotal <= 0:
            return

        region = localization_manager.get_manager().region()
        coverage = _DEFAULT_INSURANCE_COVERAGE.get(region, _DEFAULT_INSURANCE_COVERAGE["US"])

        try:
            from rx_strategies import strategy_factory
            strategy = strategy_factory(region)
            patient_cost = strategy.calculate_patient_cost(subtotal, 1, insurance_coverage=coverage)
        except Exception as e:
            log.warning("Insurance copay calculation failed (%s); using default copay", e)
            copay = coverage.get("copay", 5.0)
            patient_cost = min(subtotal, copay)

        self._insurance_applied = True
        self._insurance_copay = round(patient_cost, 2)
        self._insurance_amount = round(subtotal - patient_cost, 2)
        self._insurance_label_text = (
            f"{info.get('insurance_provider', '')} "
            f"#{info.get('policy_number', '')}"
        ).strip()

        log.info("Insurance applied: copay=%.2f, insurance_amount=%.2f",
                 self._insurance_copay, self._insurance_amount)
        self._update_cart_display()

    def _select_patient(self) -> None:
        """Open a patient selection dialog fetched asynchronously."""
        def _do_fetch_patients() -> list[tuple]:
            try:
                db_path = database.get_db_path()
                with SqliteWALConnection(db_path) as (conn, cur):
                    cur.execute(
                        "SELECT id, name, phone, "
                        "COALESCE(insurance_provider, '') AS insurance_provider, "
                        "COALESCE(policy_number, '') AS policy_number, "
                        "COALESCE(group_number, '') AS group_number "
                        "FROM patients ORDER BY name ASC"
                    )
                    return cur.fetchall() or []
            except Exception as exc:
                log.error("Patient fetch failed: %s", exc)
                return []

        def _on_done(patients: list[tuple], error: Any) -> None:
            if error or not patients:
                messagebox.showwarning(
                    i18n.t("info"), i18n.t("no_patients_found"),
                )
                return
            self._patient_menu.configure(values=[p[1] for p in patients])
            self._patient_menu.set(patients[0][1])
            self._selected_patient = {
                "id": patients[0][0],
                "name": patients[0][1],
                "phone": patients[0][2] if len(patients[0]) > 2 else "",
            }
            self._patient_label.configure(
                text=f"{i18n.t('patients')}: {patients[0][1]}",
            )

        self._run_async(
            func=_do_fetch_patients,
            callback=_on_done,
        )

    def _on_quick_action(self, action: str) -> None:
        """Handle quick-action grid button clicks."""
        log.info("Quick action: %s", action)
        try:
            if action == "prescription":
                audit_log.log_action(
                    "pos_prescription_triggered",
                    details=f"patient_id={self._selected_patient.get('id') if self._selected_patient else None}",
                    user_pin=str(auth_session.current_user_id() or ""),
                )
                if self._app and hasattr(self._app, "tab_view"):
                    for tab in self._app.tab_view._tab_dict:
                        if "clinical" in tab.lower():
                            self._app.tab_view.set(tab)
                            break
            elif action == "delivery":
                self._sale_type = "Delivery"
                self._update_sale_type_badge()
            elif action == "gifts":
                self._sale_type = "Gifts"
                self._update_sale_type_badge()
            elif action == "otc":
                self._sale_type = "OTC"
                self._update_sale_type_badge()
            elif action == "refill":
                if self._app and hasattr(self._app, "tab_view"):
                    for tab in self._app.tab_view._tab_dict:
                        if "clinical" in tab.lower():
                            self._app.tab_view.set(tab)
                            break
            elif action == "return":
                ui_pos_panels.ReturnDialog(self)
            elif action == "discount":
                calc = TaxCalculator.from_config(tax_exempt=self._tax_exempt)
                sub = calc.calculate_totals(self._cart)["subtotal"]
                ui_pos_panels.DiscountDialog(self, fees=self._fees, cart_subtotal=sub, on_apply=self._update_cart_display)
            elif action == "price_override":
                if not authz.require_pin_for("pos.price_override", self):
                    return
                selected = self._cart_tree.selection()
                if not selected:
                    messagebox.showwarning("No selection", "Select a cart item to override its price.")
                    return
                values = self._cart_tree.item(selected[0], "values")
                item_name = values[0]
                old_price = float(values[2])
                ui_pos_panels.PriceOverrideDialog(
                    self, item_name=item_name, old_price=old_price,
                    on_apply=lambda new_price: self._apply_price_override(
                        selected[0], item_name, old_price, new_price),
                )
            elif action == "void":
                if not authz.require_pin_for("pos.void", self):
                    return
                selected = self._cart_tree.selection()
                if not selected:
                    messagebox.showwarning("No selection", "Select a cart item to void.")
                    return
                values = self._cart_tree.item(selected[0], "values")
                item_name = values[0]
                qty = int(values[1])
                ui_pos_panels.VoidConfirmDialog(
                    self, item_name=item_name, qty=qty,
                    on_confirm=lambda: self._void_cart_item(selected[0], item_name),
                )
            elif action == "split":
                calc = TaxCalculator.from_config(tax_exempt=self._tax_exempt)
                breakdown = calc.calculate_totals(self._cart)
                total = breakdown["total"] + sum(f.get("amount", 0.0) for f in self._fees)
                ui_pos_panels.SplitPaymentDialog(self, grand_total=total, on_confirm=self._on_split_confirm)
            elif action == "giftcard":
                # TODO: GiftCardPanel requires a gift_cards table in database.py
                # (schema migration pending). Until then, the panel opens but
                # balance lookup and "Apply to Cart" are disabled.
                ui_pos_panels.GiftCardPanel(self)
            elif action == "memo":
                ui_pos_panels.MemoDialog(self, existing_memo=self._sale_memo, on_save=self._set_sale_memo)
            elif action == "customer":
                self._select_patient()
            elif action == "eod":
                ui_pos_panels.EODDialog(self)
        except Exception as exc:
            log.error("Quick action '%s' failed: %s", action, exc)
            messagebox.showerror(i18n.t("error"), str(exc))

    def _on_cart_select(self, event: Any = None) -> None:
        """Sync the qty spinbox to the selected cart line."""
        selected = self._cart_tree.selection()
        if selected:
            values = self._cart_tree.item(selected[0], "values")
            try:
                self._qty_spinbox.set(values[1])
            except (IndexError, ValueError):
                self._qty_spinbox.set("1")
        else:
            self._qty_spinbox.set("1")

    # ── G4: Price Override & Void ──────────────────────────────

    def _apply_price_override(self, tree_item, item_name, old_price, new_price):
        """Apply a PIN-authorized price override to a cart line."""
        import barcode_logic
        threshold = barcode_logic.get_float("price_override_manager_threshold", 0.0, lo=0.0)
        if threshold > 0 and abs(new_price - old_price) > threshold:
            if not auth_session.require_owner_override(self):
                messagebox.showwarning(
                    "Override blocked",
                    "Price change exceeds threshold. Owner override required.",
                )
                return
        for entry in self._cart:
            if entry["product_name"] == item_name and entry["price_at_time"] == old_price:
                entry["price_at_time"] = new_price
                break
        self._refresh_cart_treeview()
        self._pos_update_change()
        audit_log.log_action(
            "pos.price_override",
            f"item={item_name} old={old_price:.2f} new={new_price:.2f}",
            user_pin=str(auth_session.current_user_id()),
        )

    def _void_cart_item(self, tree_item, item_name):
        """Remove a voided item from the cart and audit."""
        for i, entry in enumerate(self._cart):
            if entry["product_name"] == item_name:
                self._cart.pop(i)
                break
        self._cart_tree.delete(tree_item)
        self._pos_update_change()
        audit_log.log_action(
            "pos.void",
            f"item={item_name}",
            user_pin=str(auth_session.current_user_id()),
        )

    # ── Checkout ─────────────────────────────────────────────

    def _build_cart_entries(self) -> list[dict[str, Any]]:
        """Build the list of cart-entry dicts expected by checkout_cart_atomically.

        **Critical:** uses ``internal_barcodes`` (list[str]) — NOT
        ``internal_barcode`` (singular str).  This fixes the original D1 bug.

        Time complexity: O(n) where n = len(self._cart).
        """
        entries: list[dict[str, Any]] = []
        for item in self._cart:
            entry = {
                "product_name": item["name"],
                "quantity": item["qty"],
                "price_at_time": item["price"],
                "internal_barcodes": list(item["internal_barcodes"]),
                "vendor": item.get("vendor", "N/A"),
                "expiry_date": str(item.get("expiry_date", "")),
            }
            assert entry["quantity"] == len(entry["internal_barcodes"]), (
                f"qty mismatch for {entry['product_name']}: "
                f"quantity={entry['quantity']} "
                f"barcodes={len(entry['internal_barcodes'])}"
            )
            entries.append(entry)
        return entries

    def _do_checkout(
        self,
        cart_entries: list[dict[str, Any]],
        payment_method: str,
        tax_rate: float,
        patient_id: int | None,
        sale_type: str,
        insurance_copay: float,
        insurance_amount: float,
    ) -> int | None:
        """Execute checkout in a background thread with retry on lock errors.

        Retries up to 3 times with exponential backoff (0.1 s, 0.2 s, 0.4 s).
        """
        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                receipt_id = database.checkout_cart_atomically(
                    payment_method=payment_method,
                    cart_entries=cart_entries,
                    patient_id=patient_id,
                    tax_rate=tax_rate,
                    sale_type=sale_type,
                    insurance_copay=insurance_copay,
                    insurance_amount=insurance_amount,
                )
                return receipt_id
            except ValueError as exc:
                log.error("Checkout ValueError (stale barcode): %s", exc)
                last_error = exc
                break  # no point retrying stale data
            except sqlite3.OperationalError as exc:
                delay = 0.1 * (2 ** attempt)
                log.warning(
                    "Checkout attempt %d/%d failed: %s — retrying in %.2fs",
                    attempt + 1, max_retries, exc, delay,
                )
                last_error = exc
                time.sleep(delay)
        if last_error:
            raise last_error
        return None

    def _on_checkout_done(
        self, receipt_id: int | None, error: Any
    ) -> None:
        """Callback (main thread): finalize the transaction or report failure."""
        self._pay_btn.configure(state="normal", text=f"💳 {i18n.t('pos_retail_process_payment')}")

        if error:
            log.error("Checkout failed: %s", error)
            messagebox.showerror(i18n.t("error"), f"Payment failed: {error}")
            return

        if receipt_id is None:
            messagebox.showerror(i18n.t("error"), "Payment failed: unknown error")
            return

        calc = TaxCalculator.from_config(tax_exempt=self._tax_exempt)
        breakdown = calc.calculate_totals(self._cart)
        total = breakdown["total"] + sum(f.get("amount", 0.0) for f in self._fees)

        audit_log.log_action(
            "retail_pos_sale",
            details=f"Receipt #{receipt_id}, items={len(self._cart)}, "
                    f"total={self.app.currency.fmt(total)}, method={self._payment_method}",
            user_pin=str(auth_session.current_user_id() or ""),
        )

        if self._insurance_applied:
            msg = (
                f"Receipt #{receipt_id} - {i18n.t('total_format', total=self.app.currency.fmt(total))}\n"
                f"{i18n.t('insurance_cost')}: {self.app.currency.fmt(self._insurance_amount)}\n"
                f"{i18n.t('patient_cost')}: {self.app.currency.fmt(self._insurance_copay)}\n"
                f"Sale Type: {self._sale_type} | Method: {self._payment_method}"
            )
        else:
            msg = i18n.t(
                "transaction_complete_msg",
                id=receipt_id,
                total=f"{total:.2f}",
            )
        messagebox.showinfo(i18n.t("success"), msg)

        self._cart.clear()
        self._fees.clear()
        self._sale_memo = ""
        self._sale_type = "OTC"
        self._insurance_applied = False
        self._insurance_copay = 0.0
        self._insurance_amount = 0.0
        self._insurance_label_text = ""
        self._update_sale_type_badge()
        self._tax_exempt = False
        self._tax_exempt_check.set(False)
        self._amount_tendered = 0.0
        self._tendered_entry.delete(0, "end")
        self._change_due_label.configure(
            text=i18n.t("change_due") + ": " + self.app.currency.fmt(0),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._selected_patient = None
        self._patient_label.configure(text=i18n.t("select_a_patient"))
        self._update_cart_display()

    def _process_payment(self) -> None:
        """Validate cart, build entries, and dispatch checkout to a background thread."""
        if not self._cart:
            messagebox.showwarning(i18n.t("info"), i18n.t("cart_pos"))
            return

        cart_entries = self._build_cart_entries()
        if not cart_entries:
            return

        calc = TaxCalculator.from_config(tax_exempt=self._tax_exempt)
        tax_rate = calc._tax_exempt and 0.0 or calc._tax_rate
        breakdown = calc.calculate_totals(self._cart)
        total = breakdown["total"] + sum(f.get("amount", 0.0) for f in self._fees)

        # For Cash, require sufficient tender
        if self._payment_method == PAYMENT_CASH:
            if self._amount_tendered < total:
                messagebox.showwarning(
                    i18n.t("insufficient_payment"),
                    f"{i18n.t('insufficient_payment')} {self.app.currency.fmt(total - self._amount_tendered)}",
                )
                return

        patient_id = self._selected_patient.get("id") if self._selected_patient else None

        self._pay_btn.configure(state="disabled", text=i18n.t("loading"))

        self._run_async(
            func=self._do_checkout,
            callback=self._on_checkout_done,
            args=(
                cart_entries,
                self._payment_method,
                tax_rate,
                patient_id,
                self._sale_type,
                self._insurance_copay if self._insurance_applied else 0.0,
                self._insurance_amount if self._insurance_applied else 0.0,
            ),
        )

    # ── F12 binding ──────────────────────────────────────────

    def bind_f12(self, app_root: Any) -> None:
        """Bind the F12 key globally to trigger payment processing.

        Guarded by a tab-label check so F12 does not hijack the
        payment shortcut when the user is on unrelated tabs
        (inventory, prescriptions, etc.).
        """
        def _on_f12(event: Any = None) -> None:
            active_tab: str = ""
            try:
                if hasattr(app_root, "tab_view"):
                    active_tab = app_root.tab_view.get()
            except Exception:
                pass
            if active_tab in (
                i18n.t("status_dashboard_title"),
                i18n.t("clinical_workflow_title"),
            ):
                self._process_payment()

        app_root.bind("<F12>", _on_f12)

    # ── Public API ───────────────────────────────────────────

    def refresh(self) -> None:
        """Refresh cart display and re-read config (tax rate, etc.)."""
        self._update_cart_display()

    def get_cart_count(self) -> int:
        """Return the number of distinct items in the cart."""
        return len(self._cart)

    def clear_all(self) -> None:
        """Clear cart, fees, patient, and reset all state."""
        self._cart.clear()
        self._fees.clear()
        self._sale_memo = ""
        self._sale_type = "OTC"
        self._update_sale_type_badge()
        self._tax_exempt = False
        self._tax_exempt_check.set(False)
        self._amount_tendered = 0.0
        self._tendered_entry.delete(0, "end")
        self._selected_patient = None
        self._insurance_applied = False
        self._insurance_copay = 0.0
        self._insurance_amount = 0.0
        self._insurance_label_text = ""
        self._patient_label.configure(text=i18n.t("select_a_patient"))
        self._insurance_cost_label.pack_forget()
        self._patient_cost_label.pack_forget()
        self._update_cart_display()

    def _debug_layout_geometry(self) -> dict[str, Any]:
        """Programmatically assert layout integrity.

        Checks (VERIFICATION_CHECKLIST Protocol II.A):
        - Action panel width >= 170 px (minimum readable).
        - No child widget extends past the root window width.
        - Balance summary card has non-zero dimensions.
        - Cart Treeview has a visible content area.

        Returns a dict of measured dimensions and any issues found.
        """
        self.update_idletasks()
        root = self.winfo_toplevel()
        root_w = root.winfo_width()
        root_h = root.winfo_height()

        results: dict[str, Any] = {
            "root_width": root_w,
            "root_height": root_h,
            "issues": [],
        }

        # Action panel width check
        panel_w = self._action_panel.winfo_width()
        results["action_panel_width"] = panel_w
        if panel_w < 170:
            results["issues"].append(
                f"Action panel width {panel_w}px < 170px minimum"
            )

        # Clip / off-screen check
        for child in self.winfo_toplevel().winfo_children():
            x = child.winfo_x()
            w = child.winfo_width()
            if x + w > root_w + 5:
                results["issues"].append(
                    f"Off-screen: {child.__class__.__name__} "
                    f"x={x} w={w} (root={root_w})"
                )

        # Balance summary dimensions
        results["summary_width"] = self._pay_btn.winfo_width()
        results["summary_height"] = self._pay_btn.winfo_height()

        # Cart tree visibility
        tree_w = self._cart_tree.winfo_width()
        tree_h = self._cart_tree.winfo_height()
        results["cart_tree"] = {"width": tree_w, "height": tree_h}
        if tree_w <= 0 or tree_h <= 0:
            results["issues"].append("Cart Treeview has zero dimensions")

        if results["issues"]:
            log.warning("Layout geometry issues: %s", results["issues"])
        else:
            log.debug("Layout geometry OK: %s", results)

        return results


# ─────────────────────────────────────────────────────────────────────
#  Tab setup (called by main_app.py via monkey-patch)
# ─────────────────────────────────────────────────────────────────────


def setup_pos_retail_tab(self: Any, parent: Any = None) -> EnterprisePosFrame:
    """Tab-setup function attached to ``PharmacyApp`` via monkey-patch.

    Adds the Enterprise POS tab to ``self.tab_view``, wires ``F12``,
    and exposes ``self.pos_retail_frame`` + ``self._refresh_pos_retail_tab``.
    """
    if parent is None:
        parent = self.tab_pos_retail

    frame = EnterprisePosFrame(parent, app=self, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=4, pady=4)

    self.pos_retail_frame = frame
    self._refresh_pos_retail_tab = frame.refresh

    # Bind F12 globally (replaces any previous <F12> binding)
    if hasattr(self, "tab_view"):
        frame.bind_f12(self)

    return frame
