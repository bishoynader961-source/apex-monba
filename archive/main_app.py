import sys
import os
import subprocess
from path_utils import get_resource_path

_LABEL_ENGINE = get_resource_path(os.path.join("label_engine", "main.py"))


def _find_python_executable():
    """Detect the correct Python executable, preferring the project venv."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_candidates = [
        os.path.join(base_dir, "venv", "Scripts", "python.exe"),
        os.path.join(os.path.dirname(base_dir), "venv", "Scripts", "python.exe"),
        os.path.join(base_dir, ".venv", "Scripts", "python.exe"),
    ]
    for candidate in venv_candidates:
        if os.path.exists(candidate):
            return candidate

    if getattr(sys, 'frozen', False):
        import shutil
        for name in ("python", "python3", "python.exe", "python3.exe"):
            found = shutil.which(name)
            if found:
                return found

    return sys.executable


def open_label_engine(product_id: str, barcode_value: str,
                      product_name: str = "", product_price: str = "",
                      expiry: str = "", manufacture: str = "",
                      show_name: bool = True, show_price: bool = True,
                      show_expiry: bool = True, show_barcode_text: bool = True):
    python_exe = _find_python_executable()
    cmd = [
        python_exe, _LABEL_ENGINE,
        "--id", product_id,
        "--barcode", barcode_value,
        "--name", product_name,
        "--price", product_price,
        "--show-name", str(show_name),
        "--show-price", str(show_price),
        "--show-expiry", str(show_expiry),
        "--show-barcode-text", str(show_barcode_text),
    ]
    if expiry:
        cmd.extend(["--expiry", expiry])
    if manufacture:
        cmd.extend(["--manufacture", manufacture])
    subprocess.Popen(cmd)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from main import main as pharmacy_main
    pharmacy_main()


if __name__ == "__main__":
    main()
