"""
design_system.py — OCR Cascade UI Design System.

Provides modern, modular UI components for communicating the real-time
progress of the OCR cascade to the user. All components are built with
customtkinter to match the existing PharmacyPro design language.

Components:
    OCRProgressBar       — Horizontal progress bar with tier labels.
    CascadeStatusBadge   — Color-coded badge showing current tier + confidence.
    OCRFeedbackBadge     — Summary badge with result count and needs-review alert.

Usage:
    from design_system import OCRProgressBar, CascadeStatusBadge, OCRFeedbackBadge

    progress = OCRProgressBar(parent)
    progress.frame.pack(padx=10, pady=10)  # caller controls layout
    progress.set_tier(1)           # highlights tier 1
    progress.update_confidence(0.92, i18n.t("ocr_tier_tesseract_standard"))

    badge = CascadeStatusBadge(parent)
    badge.frame.pack(pady=4)            # caller controls layout
    badge.set_status(tier=1, confidence=0.92, passed=True)

    feedback = OCRFeedbackBadge(parent)
    feedback.frame.pack(pady=2)         # caller controls layout
    feedback.update(results=12, needs_review=2)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import i18n

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None
    ttk = None

from ocr_cascade import OCRCascade, CascadeResult, TierResult
from ocr_engine import CONF_HIGH, CONF_MEDIUM, CONF_LOW, CONF_FALLBACK

log = logging.getLogger(__name__)

# ── Color constants (matching PharmacyPro design language) ──────────────

COLOR_BG = "#1a1a2e"
COLOR_PANEL = "#1e1e3a"
COLOR_PANEL_LIGHT = "#2a2a4a"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_SECONDARY = "#a0a0b0"
COLOR_ACCENT = "#3b82f6"
COLOR_SUCCESS = "#22c55e"
COLOR_WARNING = "#f59e0b"
COLOR_ERROR = "#ef4444"
COLOR_BORDER = "#3a3a5a"

TIER_COLORS = {
    1: COLOR_SUCCESS,   # High confidence — green
    2: COLOR_ACCENT,    # Medium confidence — blue
    3: COLOR_WARNING,   # Low confidence — amber
    4: COLOR_ERROR,     # Fallback — red
}

TIER_NAMES = [
    "Tesseract (Standard)",
    "Tesseract (Enhanced)",
    "EasyOCR",
    "Pillow Pattern Analysis",
]

CONFIDENCE_THRESHOLDS = [CONF_HIGH, CONF_MEDIUM, CONF_LOW, CONF_FALLBACK]


def _tier_names():
    return [
        i18n.t("ocr_tier_tesseract_standard"),
        i18n.t("ocr_tier_tesseract_enhanced"),
        i18n.t("ocr_tier_easyocr"),
        i18n.t("ocr_tier_pillow_pattern"),
    ]


class OCRUIError(Exception):
    """Raised when customtkinter is not available for UI components."""


def _require_ctk():
    if ctk is None:
        raise OCRUIError("customtkinter is required for OCR UI components. "
                         "Run: pip install customtkinter")


class OCRProgressBar:
    """Horizontal progress bar showing 4-tier cascade progress with
    per-tier confidence and timing information."""

    def __init__(self, parent, width: int = 400, height: int = 120):
        _require_ctk()
        self._parent = parent
        self._width = width
        self._height = height
        self._current_tier = 0
        self._tier_confidences: list[Optional[float]] = [None, None, None, None]
        self._tier_times: list[float] = [0.0, 0.0, 0.0, 0.0]

        self._frame = ctk.CTkFrame(parent, width=width, height=height,
                                    corner_radius=10,
                                    fg_color=COLOR_PANEL)
        self._frame.pack_propagate(False)

        # Title label
        self._title = ctk.CTkLabel(
            self._frame, text=i18n.t("ocr_progress_bar_title"),
            font=("Segoe UI", 13, "bold"), text_color=COLOR_TEXT,
        )
        self._title.pack(pady=(12, 4))

        # Progress bar canvas
        self._canvas = tk.Canvas(
            self._frame, width=width - 40, height=24,
            bg=COLOR_PANEL_LIGHT, highlightthickness=0,
        )
        self._canvas.pack(pady=4)

        # Tier labels row
        self._tier_labels: list[ctk.CTkLabel] = []
        self._tier_bars: list[int] = []
        self._bar_height = 16
        self._bar_width = (width - 60) // 4

        label_row = ctk.CTkFrame(self._frame, fg_color="transparent")
        label_row.pack(pady=(0, 8))
        for i, name in enumerate(_tier_names()):
            lbl = ctk.CTkLabel(
                label_row, text=name,
                font=("Segoe UI", 8), text_color=COLOR_TEXT_SECONDARY,
            )
            lbl.pack(side="left", padx=2)
            self._tier_labels.append(lbl)

        self._redraw()

    @property
    def frame(self):
        """Expose the underlying CTkFrame for caller-controlled layout."""
        return self._frame

    def _redraw(self):
        self._canvas.delete("all")
        for i in range(4):
            x = 10 + i * self._bar_width
            color = TIER_COLORS[i + 1] if i + 1 <= self._current_tier else COLOR_BORDER
            # Dim completed tiers that didn't pass
            if i + 1 < self._current_tier and self._tier_confidences[i] is not None:
                if not self._tier_passed(i + 1):
                    color = COLOR_WARNING

            self._canvas.create_rectangle(
                x, 4, x + self._bar_width - 4, 4 + self._bar_height,
                fill=color, outline=COLOR_BORDER, width=1,
            )
            # Confidence text inside bar
            conf = self._tier_confidences[i]
            if conf is not None:
                txt = "{:.0f}%".format(conf * 100)
                self._canvas.create_text(
                    x + self._bar_width / 2 - 2, 4 + self._bar_height / 2,
                    text=txt, fill=COLOR_BG, font=("Segoe UI", 7, "bold"),
                )

        # Active tier indicator
        if 0 < self._current_tier <= 4:
            ax = 10 + (self._current_tier - 1) * self._bar_width
            self._canvas.create_rectangle(
                ax, 4, ax + self._bar_width - 4, 4 + self._bar_height,
                outline=COLOR_ACCENT, width=2,
            )

    def _tier_passed(self, tier_num: int) -> bool:
        idx = tier_num - 1
        if self._tier_confidences[idx] is None:
            return False
        return self._tier_confidences[idx] >= CONFIDENCE_THRESHOLDS[idx]

    def set_tier(self, tier_num: int):
        """Set the currently active tier (1-4)."""
        self._current_tier = max(0, min(4, tier_num))
        self._redraw()

    def update_confidence(self, tier_num: int, confidence: float, elapsed_ms: float = 0.0):
        """Update confidence and timing for a specific tier."""
        idx = tier_num - 1
        if 0 <= idx < 4:
            self._tier_confidences[idx] = confidence
            self._tier_times[idx] = elapsed_ms
        self._redraw()

    def reset(self):
        """Reset all tier states."""
        self._current_tier = 0
        self._tier_confidences = [None, None, None, None]
        self._tier_times = [0.0, 0.0, 0.0, 0.0]
        self._redraw()

    def animate_cascade(self, results: list[TierResult]):
        """Animate through tier results (for demo/preview)."""
        self.reset()
        for i, tr in enumerate(results):
            if tr.result is not None:
                self.update_confidence(tr.tier, tr.result.confidence, tr.elapsed_ms)
            self.set_tier(tr.tier + 1 if i < len(results) - 1 else tr.tier)

    def destroy(self):
        self._frame.destroy()


class CascadeStatusBadge:
    """Compact badge showing current cascade tier, confidence, and pass/fail status."""

    def __init__(self, parent, size: int = "small"):
        _require_ctk()
        self._parent = parent
        self._size = size
        self._tier = 0
        self._confidence = 0.0
        self._passed = False

        pad = 6 if size == "small" else 8
        font_sz = 11 if size == "small" else 13
        badge_w = 120 if size == "small" else 160

        self._frame = ctk.CTkFrame(
            parent, width=badge_w, height=28, corner_radius=14,
            fg_color=COLOR_PANEL,
        )
        self._frame.pack_propagate(False)

        self._label = ctk.CTkLabel(
            self._frame, text="—", font=("Segoe UI", font_sz, "bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._label.pack(expand=True)

        self.set_status(tier=0, confidence=0.0, passed=False)

    @property
    def frame(self):
        """Expose the underlying CTkFrame for caller-controlled layout."""
        return self._frame

    def set_status(self, tier: int, confidence: float, passed: bool):
        """Update badge state."""
        self._tier = tier
        self._confidence = confidence
        self._passed = passed

        if tier == 0:
            text = i18n.t("ocr_status_waiting")
            color = COLOR_TEXT_SECONDARY
        elif passed:
            text = i18n.t("ocr_status_tier_format", tier=tier, percent=confidence * 100)
            color = COLOR_SUCCESS
        else:
            text = i18n.t("ocr_status_tier_format", tier=tier, percent=confidence * 100)
            color = TIER_COLORS.get(tier, COLOR_ACCENT)

        self._label.configure(text=text, text_color=color)

        # Update background to reflect tier
        bg = TIER_COLORS.get(tier, COLOR_PANEL) if tier > 0 else COLOR_PANEL
        if not passed and tier > 0:
            bg = COLOR_PANEL_LIGHT
        self._frame.configure(fg_color=bg)

    def destroy(self):
        self._frame.destroy()


class OCRFeedbackBadge:
    """Summary badge showing total results, success count, and needs-review count
    with color-coded alerts."""

    def __init__(self, parent, size: str = "small"):
        _require_ctk()
        self._parent = parent
        self._size = size
        self._total = 0
        self._needs_review = 0

        pad = 8 if size == "small" else 12
        font_sz = 10 if size == "small" else 12
        self._font_sz = font_sz

        self._frame = ctk.CTkFrame(
            parent, height=24, corner_radius=12,
            fg_color=COLOR_PANEL,
        )
        self._frame.pack_propagate(False)

        self._label = ctk.CTkLabel(
            self._frame, text=i18n.t("ocr_feedback_no_results"),
            font=("Segoe UI", font_sz, "bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._label.pack(expand=True)

        self.update(results=0, needs_review=0)

    @property
    def frame(self):
        """Expose the underlying CTkFrame for caller-controlled layout."""
        return self._frame

    def update(self, results: int = 0, needs_review: int = 0):
        """Update the badge with new result counts."""
        self._total = results
        self._needs_review = needs_review

        if results == 0:
            text = i18n.t("ocr_feedback_no_results")
            color = COLOR_TEXT_SECONDARY
        elif needs_review == 0:
            text = i18n.t("ocr_feedback_results_ok", count=results)
            color = COLOR_SUCCESS
        else:
            text = i18n.t("ocr_feedback_results_review", total=results, review=needs_review)
            color = COLOR_ERROR if needs_review > 0 else COLOR_SUCCESS

        self._label.configure(text=text, text_color=color)

    def destroy(self):
        self._frame.destroy()


class OCRCascadeMonitor:
    """High-level controller that ties the cascade engine to the UI components.
    Runs extraction in a background thread and updates UI in real time."""

    def __init__(self, parent, progress_bar: OCRProgressBar,
                 status_badge: CascadeStatusBadge,
                 feedback_badge: OCRFeedbackBadge = None):
        self._parent = parent
        self._progress = progress_bar
        self._status = status_badge
        self._feedback = feedback_badge
        self._cascade = OCRCascade()
        self._current_result: Optional[CascadeResult] = None
        self._callback = None

    def set_complete_callback(self, callback):
        """Called with CascadeResult when extraction completes."""
        self._callback = callback

    def run(self, image_source, cascade_id: str = "auto"):
        """Start cascade extraction in a background thread."""
        self._progress.reset()
        self._status.set_status(tier=0, confidence=0.0, passed=False)
        if self._feedback:
            self._feedback.update(results=0, needs_review=0)

        def _worker():
            result = self._cascade.extract(image_source, cascade_id)
            self._current_result = result

            # Animate UI through each tier result
            for tr in result.all_tier_results:
                self._parent.after(0, self._update_ui_for_tier, tr)
                self._parent.after(0, lambda t=tr.tier: self._progress.set_tier(t))

            self._parent.after(0, self._finalize_ui, result)

            if self._callback:
                self._parent.after(0, lambda: self._callback(result))

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _update_ui_for_tier(self, tier_result: TierResult):
        if tier_result.result is not None:
            self._progress.update_confidence(
                tier_result.tier, tier_result.result.confidence,
                tier_result.elapsed_ms,
            )

    def _finalize_ui(self, result: CascadeResult):
        self._status.set_status(
            tier=result.successful_tier,
            confidence=result.confidence,
            passed=result.is_success,
        )
        if self._feedback:
            review = 1 if result.needs_review else 0
            self._feedback.update(results=1, needs_review=review)
        self._progress.set_tier(result.successful_tier if result.is_success else 4)

    def get_last_result(self) -> Optional[CascadeResult]:
        return self._current_result

    def destroy(self):
        if self._progress:
            self._progress.destroy()
        if self._status:
            self._status.destroy()
        if self._feedback:
            self._feedback.destroy()
