"""
barcode_listener.py — Global HID Barcode Scanner Listener for CustomTkinter.

Listens for rapid keyboard input (barcode scanners send characters at high speed
followed by Enter). When a barcode sequence is detected, fires a callback with
the scanned code, regardless of which tab is active.

Usage:
    from barcode_listener import BarcodeListener
    listener = BarcodeListener(app, on_scan=handle_scan)
    listener.start()
"""
import time
import threading
from typing import Callable, Optional


class BarcodeListener:
    """Attach to a CTk window to detect HID barcode scanner input globally.

    Barcode scanners behave like keyboards: they type characters rapidly
    (typically <5ms per char) and finish with Enter. This listener buffers
    keystrokes and distinguishes scanner input from human typing by measuring
    inter-key timing.
    """

    def __init__(
        self,
        app,
        on_scan: Callable[[str], None],
        max_scan_interval: float = 0.05,
        min_code_length: int = 3,
    ):
        """
        Args:
            app: The CTk/CTk instance to bind to.
            on_scan: Callback invoked with the scanned barcode string.
            max_scan_interval: Max seconds between keystrokes to count as
                               scanner input (default 50ms).
            min_code_length: Minimum barcode length to trigger a callback.
        """
        self._app = app
        self._on_scan = on_scan
        self._max_interval = max_scan_interval
        self._min_length = min_code_length

        self._buffer: list[str] = []
        self._last_key_time: float = 0.0
        self._lock = threading.Lock()
        self._active = False

    def start(self) -> None:
        """Bind global key listener to the application window."""
        if self._active:
            return
        self._active = True
        self._app.bind("<Key>", self._on_key, add="+")
        self._app.bind("<Return>", self._on_return, add="+")

    def stop(self) -> None:
        """Unbind the global key listener."""
        if not self._active:
            return
        self._active = False
        try:
            self._app.unbind("<Key>")
            self._app.unbind("<Return>")
        except Exception:
            pass

    def inject(self, code: str) -> None:
        """Programmatically inject a barcode (for testing or manual entry)."""
        self._on_scan(code)

    # ── internal handlers ──────────────────────────────────────────────

    def _on_key(self, event) -> None:
        """Buffer keystrokes and detect scanner-speed input."""
        now = time.monotonic()
        char = event.char

        with self._lock:
            # If gap too long, reset buffer (human typing)
            if self._buffer and (now - self._last_key_time) > self._max_interval:
                self._buffer.clear()

            self._last_key_time = now

            # Only buffer printable characters (ignore control keys)
            if char and len(char) == 1 and char.isprintable():
                self._buffer.append(char)

    def _on_return(self, event) -> None:
        """On Enter: if buffer looks like a scanner code, fire callback."""
        with self._lock:
            code = "".join(self._buffer).strip()
            self._buffer.clear()

        if len(code) >= self._min_length:
            # Dispatch on the CTk main thread via after()
            self._app.after(0, self._on_scan, code)
