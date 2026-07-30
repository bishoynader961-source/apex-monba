"""
Auto-Updater — Version check, download, and self-replace for PyInstaller .exe.

Workflow:
  1. check_for_updates(api_url) fetches latest version + download URL from server.
  2. If update available, prompts user, downloads new .exe in chunks.
  3. Generates a temporary .bat script that replaces the running .exe after exit.
  4. Launches the .bat, then calls sys.exit(0) to release the file lock.
"""
import os
import sys
import subprocess
import tempfile
import time

try:
    import requests
except ImportError:
    requests = None

CURRENT_VERSION = '1.0.0'
CHUNK_SIZE = 1024 * 256  # 256 KB per chunk
DOWNLOAD_TIMEOUT = 120   # seconds


def _get_app_dir():
    """Return the directory where the running .exe (or script) lives."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_exe_name():
    """Return the filename of the running .exe."""
    if getattr(sys, 'frozen', False):
        return os.path.basename(sys.executable)
    return os.path.basename(__file__)


def _parse_version(v):
    """Convert '1.2.3' into a comparable tuple of ints."""
    try:
        parts = str(v).strip().split('.')
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0,)


def check_for_updates(api_url):
    """Check the server for a newer version.

    Args:
        api_url: Full URL to the version-check endpoint.  The server must
                 return JSON with at minimum:
                   { "version": "1.0.1", "download_url": "https://..." }
                 The ``download_url`` key is optional if the version is current.

    Returns:
        None — this function either replaces the app and exits, or returns
        to the caller so the app can continue launching.
    """
    if requests is None:
        print("[UPDATER] requests library not installed — skipping update check.")
        return

    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[UPDATER] Update check failed (non-fatal): {e}")
        return

    server_version = data.get("version", "")
    download_url = data.get("download_url", "")

    if not server_version:
        return

    if _parse_version(server_version) <= _parse_version(CURRENT_VERSION):
        print(f"[UPDATER] App is up to date (v{CURRENT_VERSION}).")
        return

    if not download_url:
        print("[UPDATER] New version available but no download URL provided.")
        return

    # ── Prompt the user ──
    try:
        import customtkinter as ctk
        from tkinter import messagebox

        root = ctk.CTk()
        root.withdraw()
        root.after(100, root.destroy)
        root.mainloop()
    except Exception:
        pass

    from tkinter import messagebox
    root = None
    try:
        import customtkinter as ctk
        root = ctk.CTk()
        root.withdraw()
    except Exception:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()

    answer = messagebox.askyesno(
        "Update Available",
        f"A new version (v{server_version}) is available.\n\n"
        f"Current version: v{CURRENT_VERSION}\n\n"
        f"Download and install now?"
    )
    root.destroy()

    if not answer:
        print("[UPDATER] User declined update.")
        return

    # ── Download the new .exe ──
    app_dir = _get_app_dir()
    temp_exe = os.path.join(app_dir, "update_temp.exe")

    try:
        print(f"[UPDATER] Downloading v{server_version} from {download_url} ...")
        dl_resp = requests.get(download_url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        dl_resp.raise_for_status()

        total = int(dl_resp.headers.get("content-length", 0))
        downloaded = 0

        with open(temp_exe, "wb") as f:
            for chunk in dl_resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r[UPDATER] Downloaded {pct}% ({downloaded}/{total} bytes)", end="", flush=True)
        print(f"\n[UPDATER] Download complete: {temp_exe}")
    except Exception as e:
        print(f"\n[UPDATER] Download failed: {e}")
        _cleanup(temp_exe)
        return

    # ── Verify the downloaded file is not empty ──
    if not os.path.exists(temp_exe) or os.path.getsize(temp_exe) == 0:
        print("[UPDATER] Downloaded file is empty or missing.")
        _cleanup(temp_exe)
        return

    # ── Generate and launch the self-replace batch script ──
    _launch_updater_bat(app_dir, temp_exe)


def _launch_updater_bat(app_dir, temp_exe):
    """Create a .bat that replaces the running .exe after exit, then run it."""
    app_exe = _get_exe_name()
    temp_bat = os.path.join(app_dir, "_update_apply.bat")

    # The batch script:
    #   1. Waits 2 seconds for the app to fully close and release the file lock.
    #   2. Deletes the old .exe.
    #   3. Renames the downloaded file to the original .exe name.
    #   4. Launches the updated app.
    #   5. Deletes itself.
    bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
del "{app_exe}" 2>nul
rename "{temp_exe}" "{app_exe}" 2>nul
start "" "{app_exe}"
del "%~f0"
"""
    try:
        with open(temp_bat, "w", encoding="utf-8") as f:
            f.write(bat_content)
        print(f"[UPDATER] Batch script created: {temp_bat}")
    except Exception as e:
        print(f"[UPDATER] Failed to create batch script: {e}")
        _cleanup(temp_exe)
        return

    # Launch the batch script detached from the current process
    try:
        subprocess.Popen(
            ["cmd", "/c", temp_bat],
            cwd=app_dir,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            close_fds=True,
        )
    except Exception as e:
        print(f"[UPDATER] Failed to launch batch script: {e}")
        _cleanup(temp_exe)
        return

    print("[UPDATER] Exiting current app — updater will replace and relaunch.")
    sys.exit(0)


def _cleanup(path):
    """Best-effort removal of a temp file."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
