"""Local dev orchestrator.

Starts the three Pharmacy Suite services and forwards Ctrl-C to the children:
  * Flask license microservice  -> http://localhost:5000  (backend/app.py)
  * FastAPI backend             -> http://localhost:8000  (backend_fastapi/app/main.py)
  * Next.js frontend            -> http://localhost:3000

Usage:
    python run_services.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_FASTAPI = ROOT / "backend_fastapi"
VENV_PY = BACKEND_FASTAPI / ".venv" / "Scripts" / "python.exe"
ENV = os.environ.copy()
ENV.setdefault("LEMON_SQUEEZEY_SIGNATURE_SECRET", "dev-only-do-not-use-in-prod")
ENV.setdefault("ADMIN_SECRET", "dev-only-do-not-use-in-prod")
ENV.setdefault("PHARMACY_DB_URL", f"sqlite+aiosqlite:///{ROOT / 'pharmacy.db'}")
ENV.setdefault("SECRET_KEY", "dev-only-replace-with-64-random-chars-in-prod")
ENV.setdefault("FRONTEND_URL", "http://localhost:3000")
ENV.setdefault("LICENSE_GATE_URL", "http://localhost:5000")

children: list[subprocess.Popen] = []


def _stop(signum=None, frame=None) -> None:
    for p in children:
        if p.poll() is None:
            p.terminate()
    for p in children:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    sys.exit(0)


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def main() -> None:
    if not VENV_PY.exists():
        sys.exit("ERROR: backend_fastapi/.venv not found. Create it first with:  "
                 f"{sys.executable} -m venv {BACKEND_FASTAPI / '.venv'}")

    procs: dict[str, subprocess.Popen] = {}

    # Flask license microservice is optional for local dev (FastAPI proxies it and
    # returns 502 when it is down). Start it only if Flask is importable.
    flask_ok = subprocess.run(
        [str(VENV_PY), "-c", "import flask"], capture_output=True
    ).returncode == 0
    if flask_ok:
        procs["flask-license"] = subprocess.Popen(
            [str(VENV_PY), "backend/app.py"], cwd=str(ROOT), env=ENV
        )
    else:
        print("WARN: Flask not installed in backend_fastapi/.venv — starting the license "
              "microservice (backend/app.py) is skipped. FastAPI will proxy-license to it and "
              "return 502 until Flask is available. Install with:  "
              f"{VENV_PY} -m pip install flask")

    procs["fastapi"] = subprocess.Popen(
        [str(VENV_PY), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(BACKEND_FASTAPI),
        env=ENV,
    )
    children.extend(procs.values())

    # Next.js dev server uses the root package manager (node/npm).
    npm = "npm"
    if os.name == "nt":
        npm = "npm.cmd"
    procs["nextjs"] = subprocess.Popen([npm, "run", "dev"], cwd=str(ROOT), env=ENV, shell=False)
    children.append(procs["nextjs"])

    print("Pharmacy Suite services starting:")
    print("  - Flask license : http://localhost:5000")
    print("  - FastAPI       : http://localhost:8000")
    print("  - Next.js       : http://localhost:3000")
    print("Press Ctrl-C to stop.")

    time.sleep(12)
    for name, p in procs.items():
        rc = p.poll()
        status = "running" if rc is None else f"exited ({rc})"
        print(f"  [{name}] {status}")
    # Keep alive; signal handler stops children on Ctrl-C.
    try:
        while True:
            for name, p in procs.items():
                if p.poll() is not None:
                    print(f"[{name}] exited unexpectedly", file=sys.stderr)
            time.sleep(5)
    except KeyboardInterrupt:
        _stop()


if __name__ == "__main__":
    main()
