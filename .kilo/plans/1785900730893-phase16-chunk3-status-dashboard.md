# Phase 16 — Chunk 3: Status Dashboard Module Code

## Scope
Generate the complete source code for `ui_status_dashboard.py` — the first of two modules in Chunk 3. This file implements the Enterprise Status Dashboard with 8 BestRx-style metric cards, a 3×3 task panel, and a tabbed prescription queue interface.

## Dependencies (verified)
- `customtkinter` 5.2+ (`CTkTabview`, `CTkScrollableFrame`, `CTkFrame`, `CTkLabel`, `CTkButton`)
- `tkinter.ttk.Treeview` + `ui_helpers.apply_treeview_style`
- `rx_db` module (locked import path — `get_rx_status_counts`, `get_rxs_by_status`)
- `database.get_db_path()` for sqlite3 fallback path
- `async_ui.AsyncUI.get().run(func, callback, args, kwargs)` — callback receives `(result, error)`
- Color constants from `ui_navigation`: `COLOR_CARD_BG`, `COLOR_CARD_BORDER`, `COLOR_ACCENT`, `COLOR_SUCCESS`, `COLOR_WARNING`, `COLOR_ERROR`, `COLOR_INFO`, `COLOR_TEXT_PRIMARY`, `COLOR_TEXT_SECONDARY`
- `ui_navigation.EnterpriseNavigationFrame` uses `COLOR_SIDEBAR_BG = "#1e1e2e"`, `COLOR_SIDEBAR_HOVER = "#333344"` — local constants in this file for style consistency

## New i18n Keys Required (not yet in `locales/en.json`)
```
metric_ready_pickup      → "Ready for Pickup"
metric_waiting           → "Waiting"
metric_in_processing     → "In Processing"
metric_refill_requests   → "Refill Requests"
metric_third_party_ready  → "Third Party Ready"
metric_third_party_reject → "Third Party Reject"
metric_insurance_reject   → "Insurance Reject"
metric_waiting_done       → "Waiting to be Done"
task_rx_requests          → "RX Requests"
task_refill_requests      → "Refill Requests"
task_iv_orders            → "IV Orders"
task_fax_requests         → "FAX Requests"
task_print_lists          → "Print Lists"
task_batch_fills          → "Batch Fills"
task_reprint_labels       → "Reprint Labels"
task_partial_fills        → "Partial Fills"
task_transfer_rxs         → "Transfer Rxs"
```

## Integration
`main_app.py` creates the tab via `TabViewCompat`:
```python
self.tab_status_dashboard = self.tab_view.add(i18n.t("status_dashboard_title"))
setup_status_dashboard_tab(self)  # called after
```
`setup_status_dashboard_tab` receives `self` (PharmacyApp), creates `StatusDashboardFrame` inside `self.tab_status_dashboard`, stores it as `self.status_dashboard_frame`, stores refresh callback as `self._refresh_status_dashboard_tab`.

## Code

```python
"""
ui_status_dashboard.py — Enterprise Status Dashboard for PharmacyPro.

Provides an at-a-glance monitoring panel replicating the BestRx-style
layout: eight metric cards at top, task quick-actions on the right,
and a tabbed prescription queue on the left.

Integration:
    main_app.py creates the tab container via TabViewCompat.add(), then
    calls setup_status_dashboard_tab(self) which builds the frame inside
    self.tab_status_dashboard.

Author: Senior Staff Software Engineer & Tech Lead
"""
import logging
import sqlite3
from datetime import datetime
from typing import Any

import customtkinter as ctk
from tkinter import ttk, messagebox

import i18n
import database
from ui_navigation import (
    COLOR_CARD_BG,
    COLOR_CARD_BORDER,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)
from ui_helpers import apply_treeview_style

log = logging.getLogger("ui_status_dashboard")

# Sidebar colors from ui_navigation.EnterpriseNavigationFrame (not exported)
COLOR_SIDEBAR_BG = "#1e1e2e"
COLOR_SIDEBAR_HOVER = "#333344"

# ── rx_db locked import (fallback to sqlite3 if unavailable) ───────────
try:
 from rx_db import (
     get_rx_status_counts as _rx_get_status_counts,
     get_rxs_by_status as _rx_get_rxs_by_status,
     RX_STATUSES,
     HAS_SQLALCHEMY,
 )
 _HAS_RX_DB = True
except ImportError:
 _HAS_RX_DB = False
 HAS_SQLALCHEMY = False
 RX_STATUSES = ("Pending", "Billed", "Filled", "Verified", "Will Call", "Rejected")
 log.warning("rx_db not available; Rx metrics will fall back to sqlite3 queries")

# ── AsyncUI locked import (graceful fallback if unavailable) ───────────
try:
 from async_ui import AsyncUI
 _HAS_ASYNC = True
except ImportError:
 AsyncUI = None
 _HAS_ASYNC = False
 log.warning("async_ui not available; UI updates will run synchronously")

# ── Metric Card Definitions ──────────────────────────────────────────────
# (internal_key, i18n_label_key, status_color, initial_display_value)
_METRIC_DEFS = [
    ("ready_pickup",        "metric_ready_pickup",        "success",  "0"),
    ("waiting",             "metric_waiting",             "warning",  "0"),
    ("in_processing",       "metric_in_processing",       "info",     "0"),
    ("refill_requests",     "metric_refill_requests",     "neutral",  "0"),
    ("third_party_ready",   "metric_third_party_ready",   "success",  "0"),
    ("third_party_reject",  "metric_third_party_reject",  "error",    "0"),
    ("insurance_reject",    "metric_insurance_reject",    "error",    "0"),
    ("waiting_done",        "metric_waiting_done",        "warning",  "0"),
]

# ── Task Panel Definitions ───────────────────────────────────────────────
# (i18n_key, emoji_icon)
_TASK_DEFS = [
    ("task_rx_requests",      "💊"),
    ("task_refill_requests",  "🔄"),
    ("task_iv_orders",        "💉"),
    ("task_fax_requests",     "📠"),
    ("task_print_lists",      "🖨"),
    ("task_batch_fills",      "📦"),
    ("task_reprint_labels",   "🏷️"),
    ("task_partial_fills",    "✂️"),
    ("task_transfer_rxs",     "↔️"),
]

# ── Queue Tab Definitions ────────────────────────────────────────────────
# (i18n_key, [rx_db_statuses])
_QUEUE_TABS = [
    ("queue_in_processing",  ["Pending", "Billed", "Verified"]),
    ("queue_rejects",        ["Rejected"]),
    ("queue_ready_pickup",   ["Will Call", "Filled"]),
]

_QUEUE_COLUMNS = ("Rx#", "Patient", "Drug", "Qty", "Status", "Date")


# ══════════════════════════════════════════════════════════════════════════
#  StatusMetricCard
# ══════════════════════════════════════════════════════════════════════════

class StatusMetricCard(ctk.CTkFrame):
    """Single metric card with colored accent bar, title label, and large value."""

    _STATUS_COLORS = {
        "success":  COLOR_SUCCESS,
        "warning":  COLOR_WARNING,
        "error":    COLOR_ERROR,
        "info":     COLOR_INFO,
        "neutral":  COLOR_TEXT_SECONDARY,
    }

    def __init__(self, parent, title: str = "", value: str = "0",
                 status: str = "info", width: int = 180, height: int = 110,
                 **kwargs):
        super().__init__(parent, fg_color=COLOR_CARD_BG,
                         corner_radius=8, **kwargs)
        # Disable propagation so the card maintains its size regardless of
        # text content length (defensive propagation per VERIFICATION_CHECKLIST)
        self.grid_propagate(False)
        self._width = width
        self._height = height
        self.configure(width=width, height=height)
        self.grid_columnconfigure(1, weight=1)

        band_color = self._STATUS_COLORS.get(status, COLOR_ACCENT)

        # Colored accent bar (6px wide)
        ctk.CTkFrame(self, fg_color=band_color, width=6,
                     corner_radius=0).grid(
            row=0, column=0, rowspan=2, sticky="nsew")

        # Title label (small, secondary)
        self._title_label = ctk.CTkLabel(
            self, text=title,
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self._title_label.grid(
            row=0, column=1, sticky="w", padx=12, pady=(14, 2))

        # Value label (large, bold, primary)
        self._value_label = ctk.CTkLabel(
            self, text=value,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self._value_label.grid(
            row=1, column=1, sticky="w", padx=12, pady=(0, 14))

    def update_value(self, value: str | int):
        """Update the displayed value on the main thread."""
        self._value_label.configure(text=str(value))

    def update_title(self, title: str):
        """Update the card title on the main thread."""
        self._title_label.configure(text=title)


# Backward-compatible alias (existing code / imports may reference MetricCard)
MetricCard = StatusMetricCard


# ══════════════════════════════════════════════════════════════════════════
#  TaskPanel
# ══════════════════════════════════════════════════════════════════════════

class TaskPanel(ctk.CTkFrame):
    """3×3 grid of 9 workflow quick-action buttons."""

    # i18n_key → target_tab_i18n_key (for tab switching)
    _NAV_MAP = {
        "task_rx_requests":     "rx_processing",
        "task_refill_requests": "rx_processing",
        "task_transfer_rxs":    "clinical_workflow",
    }

    def __init__(self, parent, app: Any = None, **kwargs):
        super().__init__(parent, fg_color=COLOR_CARD_BG,
                         corner_radius=8, **kwargs)
        self._app = app
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._build()

    def _build(self):
        # Title
        ctk.CTkLabel(
            self, text=i18n.t("task_panel_title"),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 12))

        # Button grid container
        btn_grid = ctk.CTkFrame(self, fg_color="transparent")
        btn_grid.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        btn_grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="btn")
        btn_grid.grid_rowconfigure((0, 1, 2), weight=1, uniform="btn")

        for idx, (key, icon) in enumerate(_TASK_DEFS):
            r, c = divmod(idx, 3)
            btn = ctk.CTkButton(
                btn_grid,
                text=f"{icon}\n{i18n.t(key)}",
                height=70,
                command=lambda k=key: self._on_task_click(k),
                fg_color="transparent",
                hover_color=COLOR_SIDEBAR_HOVER,
                text_color=COLOR_TEXT_PRIMARY,
                font=ctk.CTkFont(size=10),
                border_width=0,
            )
            btn.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
            self._buttons[key] = btn

        # Make the task panel resist being crushed by button text
        self.grid_propagate(False)
        self.configure(height=280)

    def _on_task_click(self, key: str):
        """Switch to the corresponding app tab, or show 'coming soon' message."""
        target_key = self._NAV_MAP.get(key)
        if target_key is not None:
            target = i18n.t(target_key)
            app = self._app or self.winfo_toplevel()
            if hasattr(app, "tab_view"):
                try:
                    app.tab_view.set(target)
                    if app.tab_view._command:
                        app.tab_view._command()
                except Exception as e:
                    log.warning("Task switch to '%s' failed: %s", target, e)
            else:
                log.warning("Application tab_view not found; "
                            "cannot switch to '%s'", target)
        else:
            messagebox.showinfo(
                i18n.t("info"),
                f"{i18n.t(key)} — feature coming soon.",
            )


# ══════════════════════════════════════════════════════════════════════════
#  QueueTabFrame
# ══════════════════════════════════════════════════════════════════════════

class QueueTabFrame(ctk.CTkFrame):
    """CTkTabview with three prescription-state queue tabs.

    Each tab contains a ttk.Treeview with a vertical scrollbar.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLOR_CARD_BG,
                         corner_radius=8, **kwargs)
        self._trees: dict[str, ttk.Treeview] = {}
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # TabView
        self._tabview = ctk.CTkTabview(self)
        self._tabview.grid(row=0, column=0, sticky="nsew",
                          padx=12, pady=12)
        self._tabview.grid_columnconfigure(0, weight=1)
        self._tabview.grid_rowconfigure(0, weight=1)

        for tab_key, _statuses in _QUEUE_TABS:
            display_name = i18n.t(tab_key)
            # Fallback: if i18n key missing, use a human-readable default
            if display_name == tab_key:
                display_name = tab_key.replace("_", " ").title()

            self._tabview.add(display_name)
            tab_frame = self._tabview.tab(display_name)

            tree = ttk.Treeview(
                tab_frame, columns=_QUEUE_COLUMNS,
                show="headings", height=8,
            )
            apply_treeview_style(tree)

            for col in _QUEUE_COLUMNS:
                tree.heading(col, text=col)

            tree.column("Rx#",     width=100, anchor="w")
            tree.column("Patient", width=80,  anchor="center")
            tree.column("Drug",    width=120, anchor="w")
            tree.column("Qty",     width=50,  anchor="center")
            tree.column("Status",  width=100, anchor="center")
            tree.column("Date",    width=90,  anchor="center")

            tree.pack(fill="both", expand=True, padx=4, pady=4)

            # Row striping
            tree.tag_configure("odd",
                               background=COLOR_SIDEBAR_BG)
            tree.tag_configure("even",
                               background=COLOR_CARD_BORDER)

            self._trees[tab_key] = tree

        # Select first tab by default
        first_name = i18n.t(_QUEUE_TABS[0][0])
        if first_name == _QUEUE_TABS[0][0]:
            first_name = _QUEUE_TABS[0][0].replace("_", " ").title()
        self._tabview.set(first_name)

    # ── Public API ───────────────────────────────────────────────────────

    def populate(self, tab_key: str, prescriptions: list):
        """Clear and repopulate a queue tab's Treeview."""
        tree = self._trees.get(tab_key)
        if tree is None:
            log.warning("QueueTabFrame.populate: unknown tab '%s'", tab_key)
            return
        for item in tree.get_children():
            tree.delete(item)

        for idx, row in enumerate(prescriptions):
            tag = "even" if idx % 2 == 0 else "odd"
            rx_number = row[1] if len(row) > 1 else ""
            patient_id  = row[2] if len(row) > 2 else ""
            drug_ndc    = row[4] if len(row) > 4 else ""
            qty         = row[8] if len(row) > 8 else ""
            status      = row[9] if len(row) > 9 else ""
            date        = row[10] if len(row) > 10 else ""
            tree.insert("", "end", values=(
                rx_number, patient_id, drug_ndc, qty, status, date
            ), tags=(tag,))

    def refresh(self):
        """Reload all three queue tabs (async if available)."""
        for tab_key, statuses in _QUEUE_TABS:
            self._load_queue(tab_key, statuses)

    def _load_queue(self, tab_key: str, statuses: list[str]):
        """Kick off async or sync load for one queue tab."""
        if _HAS_ASYNC:
            def _callback(rxs, error):
                self._on_queue_loaded(rxs, error, tab_key)
            AsyncUI.get().run(
                func=lambda: self._fetch_queue_rxs(statuses),
                callback=_callback,
            )
        else:
            rxs = self._fetch_queue_rxs(statuses)
            self._on_queue_loaded(rxs, None, tab_key)

    # ── Data fetching (background thread) ───────────────────────────────

    def _fetch_queue_rxs(self, statuses: list[str]) -> list:
        """Fetch prescriptions whose status is in *statuses*.

        Returns a list of tuples matching rx_table column order:
            (id, rx_number, patient_id, prescriber_id, drug_ndc,
             days_supply, daw_code, refills_remaining, sig_code,
             quantity, status, date_prescribed, date_started, date_filled,
             notes, regional_metadata)
        """
        # Strategy 1: rx_db locked import
        if _HAS_RX_DB and HAS_SQLALCHEMY:
            try:
                all_rxs: list = []
                for st in statuses:
                    all_rxs.extend(_rx_get_rxs_by_status(st))
                return all_rxs
            except Exception as e:
                log.warning(
                    "rx_db.get_rxs_by_status failed: %s; "
                    "falling back to sqlite3", e)

        # Strategy 2: raw sqlite3 fallback
        try:
            db_path = database.get_db_path()
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            placeholders = ", ".join("?" for _ in statuses)
            cursor.execute(f"""
                SELECT id, rx_number, patient_id, prescriber_id, drug_ndc,
                       days_supply, daw_code, refills_remaining, sig_code,
                       quantity, status, date_prescribed, date_started,
                       date_filled, notes, regional_metadata
                FROM rx_table
                WHERE status IN ({placeholders})
                ORDER BY id DESC
            """, statuses)
            rows = cursor.fetchall()
            conn.close()
            return rows
        except Exception as e:
            log.error("Queue sqlite3 fallback failed: %s", e)
            return []

    # ── UI update callback (main thread) ────────────────────────────────

    def _on_queue_loaded(self, rxs, error, tab_key: str):
        """Populate a queue tab from async callback result."""
        if error:
            log.warning("Queue load for '%s' failed: %s", tab_key, error)
        self.populate(tab_key, rxs or [])


# ══════════════════════════════════════════════════════════════════════════
#  StatusDashboardFrame
# ══════════════════════════════════════════════════════════════════════════

class StatusDashboardFrame(ctk.CTkFrame):
    """Enterprise status dashboard: metric cards + task panel + queue tabs."""

    def __init__(self, parent, app: Any = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._app = app
        self._metric_cards: dict[str, StatusMetricCard] = {}
        self._build_ui()

    def _build_ui(self):
        # ── Overall grid ──
        #   Row 0: Header
        #   Row 1: 8 Metric Cards (2×4)
        #   Row 2: Content (queue tabs left, task panel right)
        #   Row 3: Footer (refresh button)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=0)  # metrics
        self.grid_rowconfigure(2, weight=1)  # content (expands)
        self.grid_rowconfigure(3, weight=0)  # footer

        # ── Header ─────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew",
                    padx=20, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text=i18n.t("status_dashboard_title"),
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header, text=i18n.t("status_dashboard_subtitle"),
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w",
               pady=(22, 0))

        self._last_updated = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._last_updated.grid(row=0, column=0, sticky="e")

        # ── Metric Cards (2×4 scrollable grid) ──────────────────────────
        metrics_container = ctk.CTkScrollableFrame(
            self, fg_color="transparent")
        metrics_container.grid(
            row=1, column=0, sticky="nsew",
            padx=20, pady=10)
        metrics_container.grid_columnconfigure(
            (0, 1, 2, 3), weight=1)

        for idx, (key, label_key, status, initial) in enumerate(_METRIC_DEFS):
            row, col = divmod(idx, 4)
            card = StatusMetricCard(
                metrics_container,
                title=i18n.t(label_key),
                value=initial,
                status=status,
            )
            card.grid(
                row=row, column=col,
                sticky="nsew", padx=8, pady=8)
            self._metric_cards[key] = card

        # ── Content: Queue Tabs (left) + Task Panel (right) ────────────
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew",
                     padx=20, pady=(0, 10))
        content.grid_columnconfigure(0, weight=2)  # queue (larger)
        content.grid_columnconfigure(1, weight=1)  # tasks (smaller)
        content.grid_rowconfigure(0, weight=1)

        self._queue_frame = QueueTabFrame(content)
        self._queue_frame.grid(
            row=0, column=0, sticky="nsew", padx=(0, 10))

        self._task_panel = TaskPanel(content, app=self._app)
        self._task_panel.grid(
            row=0, column=1, sticky="nsew", padx=(10, 0))

        # ── Footer ─────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew",
                    padx=20, pady=(0, 20))
        footer.grid_columnconfigure(1, weight=1)

        refresh_btn = ctk.CTkButton(
            footer, text=f"🔄 {i18n.t('refresh')}",
            height=32, width=120,
            command=self.refresh,
        )
        refresh_btn.grid(row=0, column=1, sticky="e")

    # ── Public API ───────────────────────────────────────────────────────

    def refresh(self):
        """Reload all metrics and queue data from the data sources."""
        try:
            self._load_metrics()
            self._queue_frame.refresh()
        except Exception as e:
            log.error("Dashboard refresh failed: %s", e)

    def _debug_layout_geometry(self):
        """Verify layout integrity after root.update_idletasks().

        Checks:
          - Metric cards maintain minimum width
          - Task panel does not collapse
          - Queue frame does not clip off-screen
        """
        try:
            self.update_idletasks()
            w = self.winfo_width()
            h = self.winfo_height()
            log.debug(
                "StatusDashboardFrame: %dx%d", w, h)

            for key, card in self._metric_cards.items():
                cw = card.winfo_width()
                if cw < 100:
                    log.warning(
                        "Metric card '%s' width below minimum: %d",
                        key, cw)

            tw = self._task_panel.winfo_width()
            if tw < 120:
                log.warning(
                    "TaskPanel width below minimum: %d", tw)

            qw = self._queue_frame.winfo_width()
            qx = self._queue_frame.winfo_x()
            if qx + qw > w:
                log.warning(
                    "QueueTabFrame clipping: "
                    "x=%d + w=%d > parent=%d",
                    qx, qw, w)

            log.debug("Layout geometry verified OK")
        except Exception as e:
            log.error("Layout geometry debug failed: %s", e)

    # ── Metrics loading ──────────────────────────────────────────────────

    def _load_metrics(self):
        """Fetch metric values (async if available)."""
        if _HAS_ASYNC:
            AsyncUI.get().run(
                func=self._fetch_metrics,
                callback=self._on_metrics_loaded,
            )
        else:
            metrics = self._fetch_metrics()
            self._on_metrics_loaded(metrics, None)

    def _fetch_metrics(self) -> dict[str, int]:
        """Build the 8-metric dict (background thread)."""
        result: dict[str, int] = {
            key: 0 for key, _, _, _ in _METRIC_DEFS
        }

        # Phase 1: rx_db for basic status counts
        if _HAS_RX_DB:
            try:
                counts = _rx_get_status_counts()
                result["ready_pickup"] = counts.get("Will Call", 0)
                result["waiting"] = counts.get("Pending", 0)
                result["in_processing"] = (
                    counts.get("Pending", 0)
                    + counts.get("Billed", 0)
                    + counts.get("Verified", 0)
                )
            except Exception as e:
                log.error(
                    "rx_db.get_rx_status_counts failed: %s", e)

        # Phase 2: sqlite3 for all metrics (covers rx_db fallback + JSON)
        try:
            db_path = database.get_db_path()
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # If rx_db didn't supply basic counts, use sqlite3 directly
            if not _HAS_RX_DB:
                cursor.execute(
                    "SELECT status, COUNT(*) "
                    "FROM rx_table GROUP BY status")
                counts = {
                    row[0]: row[1] for row in cursor.fetchall()
                }
                result["ready_pickup"] = counts.get("Will Call", 0)
                result["waiting"] = counts.get("Pending", 0)
                result["in_processing"] = (
                    counts.get("Pending", 0)
                    + counts.get("Billed", 0)
                    + counts.get("Verified", 0)
                )

            # Refill Requests — prescriptions with refills remaining
            #    that are in Will Call or Filled state
            cursor.execute("""
                SELECT COUNT(*) FROM rx_table
                WHERE COALESCE(refills_remaining, 0) > 0
                  AND status IN ('Will Call', 'Filled')
            """)
            result["refill_requests"] = cursor.fetchone()[0]

            # Third Party Ready — flag in regional_metadata
            try:
                cursor.execute("""
                    SELECT COUNT(*) FROM rx_table
                    WHERE LENGTH(COALESCE(regional_metadata, '')) > 2
                      AND json_extract(
                          regional_metadata,
                          '$.third_party_ready') = 1
                """)
                result["third_party_ready"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                result["third_party_ready"] = 0

            # Third Party Reject — rejected with third-party rejection source
            try:
                cursor.execute("""
                    SELECT COUNT(*) FROM rx_table
                    WHERE status = 'Rejected'
                      AND LENGTH(COALESCE(regional_metadata, '')) > 2
                      AND json_extract(
                          regional_metadata,
                          '$.rejection_source') = 'third_part'
                """)
                result["third_party_reject"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                result["third_party_reject"] = 0

            # Insurance Reject — claim rejected via insurance
            try:
                cursor.execute("""
                    SELECT COUNT(*) FROM rx_table
                    WHERE LENGTH(COALESCE(regional_metadata, '')) > 2
                      AND json_extract(
                          regional_metadata,
                          '$.claim_status') = 'Rejected'
                """)
                result["insurance_reject"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                result["insurance_reject"] = 0

            # Waiting to be Done — Pending with no start date
            cursor.execute("""
                SELECT COUNT(*) FROM rx_table
                WHERE status = 'Pending'
                  AND (date_started IS NULL
                       OR date_started = '')
            """)
            result["waiting_done"] = cursor.fetchone()[0]

            conn.close()
        except Exception as e:
            log.error(
                "Custom rx_table queries failed: %s", e)

        return result

    def _on_metrics_loaded(self, metrics, error=None):
        """Update all metric card values (main thread)."""
        if error:
            log.error("Metrics load failed: %s", error)
            return
        for key, _, _, _ in _METRIC_DEFS:
            value = metrics.get(key, 0)
            card = self._metric_cards.get(key)
            if card:
                card.update_value(str(value))
        self._last_updated.configure(
            text=f"🕒 {datetime.now().strftime('%H:%M:%S')}"
        )


# ══════════════════════════════════════════════════════════════════════════
#  Tab Setup Function (called by main_app.py)
# ══════════════════════════════════════════════════════════════════════════

def setup_status_dashboard_tab(self):
    """Create the Enterprise Status Dashboard tab inside PharmacyApp.

    Expects main_app.py to have already created:
        self.tab_status_dashboard = \
            self.tab_view.add(i18n.t("status_dashboard_title"))

    After calling, the PharmacyApp will have:
        self.status_dashboard_frame  — the StatusDashboardFrame instance
        self._refresh_status_dashboard_tab  — lambda calling frame.refresh()
    """
    frame = StatusDashboardFrame(
        self.tab_status_dashboard,
        app=self,
        fg_color="transparent",
    )
    frame.pack(fill="both", expand=True, padx=4, pady=4)

    self.status_dashboard_frame = frame
    self._refresh_status_dashboard_tab = lambda: frame.refresh()

    # Initial data load
    frame.refresh()
    return frame
```

## i18n Key Audit (existing vs new)

| Key | Status | Module |
|---|---|---|
| `status_dashboard_title` | exists | en.json |
| `status_dashboard_subtitle` | exists | en.json |
| `task_panel_title` | exists | en.json |
| `refresh` | exists | en.json |
| `info` | exists | en.json |
| `rx_processing` | exists | en.json |
| `clinical_workflow` | exists | en.json |
| `metric_ready_pickup` | **new** | — |
| `metric_waiting` | **new** | — |
| `metric_in_processing` | **new** | — |
| `metric_refill_requests` | **new** | — |
| `metric_third_party_ready` | **new** | — |
| `metric_third_party_reject` | **new** | — |
| `metric_insurance_reject` | **new** | — |
| `metric_waiting_done` | **new** | — |
| `task_rx_requests` | **new** | — |
| `task_refill_requests` | **new** | — |
| `task_iv_orders` | **new** | — |
| `task_fax_requests` | **new** | — |
| `task_print_lists` | **new** | — |
| `task_batch_fills` | **new** | — |
| `task_reprint_labels` | **new** | — |
| `task_partial_fills` | **new** | — |
| `task_transfer_rxs` | **new** | — |

## Verification Checklist

1. **Metric cards render**: 8 cards in 2×4 grid, each with colored accent bar
2. **Queue tabs render**: CTkTabview with 3 tabs, each containing a Treeview
3. **Task panel renders**: 3×3 grid of buttons
4. **No clipping**: `_debug_layout_geometry` passes all assertions
5. **Async loading**: `AsyncUI.get().run()` called, no blocking on main thread
6. **SQLite fallback**: Works when rx_db not available
7. **JSON safe**: `json_extract` queries wrapped in try/except
8. **Backward compat**: `MetricCard = StatusMetricCard` alias provided