"""
async_ui.py — Centralized asynchronous task manager for PharmacyPro.

Provides a single ThreadPoolExecutor-backed task runner that safely dispatches
CPU- or IO-bound work to background threads and marshals results back to the
main Tkinter/CustomTkinter thread via ``root.after()``.

Design decisions:
    - Uses ``concurrent.futures.ThreadPoolExecutor`` (NOT multiprocessing):
      compatible with PyInstaller frozen binaries, no fork-related crashes.
    - All callbacks are invoked via ``root.after(0, callback)`` to guarantee
      thread-safety — Tkinter is not thread-safe; only ``after()`` may be
      called from background threads.
    - Graceful shutdown: ``shutdown()`` cancels pending futures and stops
      threads.  The ``_shutdown`` flag prevents new submissions after
      shutdown.
    - Singleton pattern: ``AsyncUI.get()`` returns the shared instance.
      ``init(root)`` must be called once from the main thread during app
      startup to bind the Tkinter root.

Usage:
    from async_ui import async_run

    # Submit a background task with a UI-thread callback:
    async_run(
        func=compile_metrics,               # runs in background thread
        callback=lambda metrics, err: self._show_metrics(metrics),
        args=("daily",),
    )

    # The callback receives (result, error):
    #   - If success:  callback(result, None)
    #   - If failure:  callback(None, exception)
"""
from __future__ import annotations

import logging
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Optional

log = logging.getLogger("async_ui")
_MAX_WORKERS = 4


class AsyncUI:
    """Centralized async task manager with thread-safe UI callbacks.

    All UI updates must go through ``root.after()``.  This class wraps that
    pattern so background workers never touch Tkinter widgets directly.
    """

    _instance: Optional["AsyncUI"] = None

    def __init__(self, max_workers: int = _MAX_WORKERS):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="AsyncUI",
        )
        self._root: Optional[Any] = None
        self._shutdown: bool = False
        log.debug("AsyncUI initialised (max_workers=%d)", max_workers)

    # ── Singleton access ─────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "AsyncUI":
        """Return the shared AsyncUI singleton (creates if needed)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton instance and shut down any active executor."""
        if cls._instance is not None:
            cls._instance.shutdown()
            cls._instance = None

    def init(self, root: Any) -> None:
        """Bind the Tkinter root for ``after()`` callback marshaling.

        Must be called once from the main thread during application startup.
        """
        self._root = root
        log.debug("AsyncUI root bound")

    # ── Task submission ──────────────────────────────────────────────────

    def run(
        self,
        func: Callable,
        callback: Optional[Callable[[Any, Optional[Exception]], None]] = None,
        args: tuple = (),
        kwargs: Optional[dict] = None,
    ) -> Future:
        """Submit *func* to the background thread pool.

        Args:
            func:      The heavy function to run off-thread.
            callback:  Called on the main thread via ``after(0)`` with
                       ``(result, error)`` where *error* is ``None`` on
                       success.
            args:      Positional arguments passed to *func*.
            kwargs:    Keyword arguments passed to *func*.

        Returns:
            The ``concurrent.futures.Future`` (for optional ``future.result()``
            blocking calls, though ``.after()`` is preferred for UI code).
        """
        if self._shutdown:
            log.warning("AsyncUI: rejecting task after shutdown")
            return Future()  # cancelled future

        kwargs = kwargs or {}
        future = self._executor.submit(func, *args, **kwargs)
        future.add_done_callback(self._make_done_callback(callback))
        return future

    def _make_done_callback(
        self, callback: Optional[Callable[[Any, Optional[Exception]], None]]
    ) -> Callable[[Future], None]:
        """Wrap the user callback so it always runs on the main thread."""

        def _on_done(future: Future) -> None:
            if not callback or self._root is None:
                return
            try:
                result = future.result()
                error: Optional[Exception] = None
            except Exception as exc:
                result = None
                error = exc

            def _invoke():
                try:
                    callback(result, error)
                except Exception as cb_exc:
                    log.error("AsyncUI callback raised: %s", cb_exc)

            try:
                if not self._root.winfo_exists():
                    return
                self._root.after(0, _invoke)
            except (tk.TclError, RuntimeError):
                # Root destroyed or main loop stopped — silently discard
                # the pending UI update without logging to stdout.
                return
            except Exception as after_exc:
                log.error("AsyncUI after() failed (root destroyed?): %s", after_exc)

        return _on_done

    # ── Lifecycle ────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Cancel pending tasks and shut down the thread pool.

        ``wait=False`` ensures the shutdown never blocks the main thread.
        ``cancel_futures=True`` (Python 3.12+) cancels queued tasks.
        """
        if self._shutdown:
            return
        self._shutdown = True
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        except TypeError:
            # Python < 3.9 doesn't support cancel_futures
            self._executor.shutdown(wait=False)
            self._executor = None
        log.info("AsyncUI shutdown complete")

    def __del__(self):
        self.shutdown()


# ── Module-level convenience ─────────────────────────────────────────────

def async_run(
    func: Callable,
    callback: Optional[Callable[[Any, Optional[Exception]], None]] = None,
    args: tuple = (),
    kwargs: Optional[dict] = None,
) -> Future:
    """Module-level shortcut to ``AsyncUI.get().run()``."""
    return AsyncUI.get().run(func, callback=callback, args=args, kwargs=kwargs)


def init_async_ui(root: Any) -> AsyncUI:
    """Initialise the AsyncUI singleton with the Tkinter root."""
    mgr = AsyncUI.get()
    mgr.init(root)
    return mgr
