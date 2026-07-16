import sys
import os
import subprocess
import sys

_LABEL_ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "label_engine", "main.py")


def open_label_engine(product_id: str, barcode_value: str,
                      product_name: str = "", product_price: str = "",
                      expiry: str = "", manufacture: str = "",
                      show_name: bool = True, show_price: bool = True,
                      show_expiry: bool = True, show_barcode_text: bool = True):
    cmd = [
        sys.executable, _LABEL_ENGINE,
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
