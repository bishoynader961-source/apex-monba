import os
import subprocess
from datetime import datetime
from path_utils import get_resource_path
import currency

RECEIPTS_DIR = get_resource_path("receipts")


def init_receipts_dir():
    if not os.path.exists(RECEIPTS_DIR):
        os.makedirs(RECEIPTS_DIR)


def generate_receipt(receipt_id: int, cart_items: list, subtotal: float, total: float,
                     tax: float = 0.0, payment_type: str = "Cash", patient_name: str = "",
                     pharmacy_info: dict = None):
    """Generate a formatted receipt as a .txt file.

    Args:
        receipt_id: Unique receipt identifier.
        cart_items: List of dicts with keys: product_name, quantity, price_at_time.
        subtotal: Sum of (quantity × price_at_time) before tax.
        total: Grand total (subtotal + tax).
        tax: Tax amount applied to the subtotal.
        payment_type: Payment method string.
        patient_name: Optional patient name for the receipt.
        pharmacy_info: Optional dict with keys: pharmacy_name, address, phone.

    Returns:
        Path to the generated receipt file.
    """
    init_receipts_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(RECEIPTS_DIR, f"receipt_{receipt_id}_{timestamp}.txt")

    if pharmacy_info is None:
        pharmacy_info = {}

    pharm_name = pharmacy_info.get("pharmacy_name", "My Pharmacy")
    pharm_addr = pharmacy_info.get("address", "")
    pharm_phone = pharmacy_info.get("phone", "")
    pharm_header_note = pharmacy_info.get("receipt_header_note", "")
    pharm_footer_note = pharmacy_info.get("receipt_footer_note", "")

    width = 40
    sep = "=" * width
    dash = "-" * width

    lines = []
    lines.append(sep)
    lines.append(pharm_name.center(width))
    if pharm_addr:
        lines.append(pharm_addr.center(width))
    if pharm_phone:
        lines.append(f"Tel: {pharm_phone}".center(width))
    lines.append(sep)
    if pharm_header_note:
        lines.append(pharm_header_note.center(width))
        lines.append(sep)
    lines.append(f"Receipt #: {receipt_id}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Payment: {payment_type}")
    if patient_name:
        lines.append(f"Patient: {patient_name}")
    lines.append(dash)
    lines.append("Items:")
    lines.append("")

    for item in cart_items:
        name = item["product_name"]
        qty = item["quantity"]
        price = item["price_at_time"]
        line_total = qty * price
        lines.append(f"  {name}")
        lines.append(f"    x{qty}  @{currency.fmt(price)}  =  {currency.fmt(line_total)}")
    lines.append(sep)
    lines.append("Thank you for your purchase!".center(width))
    if pharm_footer_note:
        lines.append(sep)
        lines.append(pharm_footer_note.center(width))
    lines.append(sep)

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filename


def open_receipt_file(filepath: str):
    """Open a receipt text file with the system default viewer."""
    if not os.path.exists(filepath):
        return
    try:
        if os.name == "nt":
            os.startfile(filepath)
        else:
            subprocess.Popen(["xdg-open", filepath],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception:
        pass
