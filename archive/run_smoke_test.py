"""
run_smoke_test.py — Live smoke-test for the PharmacyPro_Rx executable.

Executes PharmacyPro_Rx.exe, monitors startup for 5 seconds, captures
stdout/stderr diagnostics, and reports whether the application initialized
without fatal exceptions.

Usage:
    python archive/run_smoke_test.py
"""
import os
import sys
import time
import subprocess
import threading
from datetime import datetime

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
EXE_PATH = os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx", "PharmacyPro_Rx.exe")

if not os.path.exists(EXE_PATH):
    EXE_PATH = os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx.exe")


def find_exe():
    candidates = [
        os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx", "PharmacyPro_Rx.exe"),
        os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def run_smoke_test(timeout_seconds=5):
    exe_path = find_exe()
    if not exe_path:
        print("[FAIL] PharmacyPro_Rx.exe not found in archive/dist/")
        print("       Run: python archive/build_rx_app.py")
        return False

    print(f"[INFO] Executable: {exe_path}")
    print(f"[INFO] File size: {os.path.getsize(exe_path) / (1024*1024):.1f} MB")
    print(f"[INFO] Start time: {datetime.now().isoformat()}")
    print(f"[INFO] Monitoring for {timeout_seconds}s...")
    print()

    stdout_lines = []
    stderr_lines = []

    try:
        proc = subprocess.Popen(
            [exe_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
    except Exception as e:
        print(f"[FAIL] Failed to launch executable: {e}")
        return False

    def read_stream(stream, storage):
        for line in iter(stream.readline, ""):
            storage.append(line.rstrip())

    stdout_thread = threading.Thread(target=read_stream, args=(proc.stdout, stdout_lines))
    stderr_thread = threading.Thread(target=read_stream, args=(proc.stderr, stderr_lines))
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    stdout_thread.start()
    stderr_thread.start()

    start = time.time()
    poll_interval = 0.5
    crashed = False

    while time.time() - start < timeout_seconds:
        ret = proc.poll()
        if ret is not None:
            elapsed = time.time() - start
            crashed = True
            print(f"[CRASH] Process exited after {elapsed:.1f}s with code {ret}")
            break
        time.sleep(poll_interval)

    elapsed = time.time() - start

    if not crashed:
        print("[OK] Process still running after {:.1f}s — no fatal crash".format(elapsed))

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    print()
    print("=" * 60)
    print("STDOUT (last 20 lines):")
    print("=" * 60)
    if stdout_lines:
        for line in stdout_lines[-20:]:
            print(line)
    else:
        print("(no stdout captured)")

    print()
    print("=" * 60)
    print("STDERR (last 20 lines):")
    print("=" * 60)
    if stderr_lines:
        for line in stderr_lines[-20:]:
            print(line)
    else:
        print("(no stderr captured)")

    print()
    print("=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)

    fatal_keywords = ["Traceback (most recent call last)", "Fatal", "Error:",
                      "ImportError", "ModuleNotFoundError", "dll load failed",
                      "PermissionError", "FileNotFoundError"]

    all_output = stderr_lines + stdout_lines
    has_fatal = any(
        any(kw in line for kw in fatal_keywords)
        for line in all_output
    )

    if crashed:
        print("Status: CRASHED during startup")
        return False
    elif has_fatal:
        print("Status: Started but fatal errors detected in output")
        return False
    elif not crashed:
        print("Status: PASSED — process alive after {:.1f}s".format(elapsed))
        print("The Rx Workflow application launched successfully.")
        return True

    return not crashed


if __name__ == "__main__":
    success = run_smoke_test(timeout_seconds=5)
    sys.exit(0 if success else 1)
