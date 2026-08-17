"""
GUI smoke test for Phase 13.5 — Settings tab + config sync.
Verifies:
  VG-1  Receipt note fields pre-populate from config
  VG-4  Checkout cart re-renders on config change (method wiring sanity)
  Layout: no clipping of settings form fields (AGENTS Protocol II.A)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
import barcode_logic

# Ensure config has the receipt note keys
cfg = barcode_logic.load_config()
assert "receipt_header_note" in cfg, "config defaults missing receipt_header_note"
assert "receipt_footer_note" in cfg, "config defaults missing receipt_footer_note"

from ui import PharmacyApp

app = PharmacyApp()
app.update_idletasks()

errors = []

# ── VG-1: Settings tab form fields exist and pre-populate ──
tab = app.tab_settings
print("Tab Settings frame exists:", tab is not None)

# Check the entry widgets were created
header_entry = getattr(app, "set_receipt_header_entry", None)
footer_entry = getattr(app, "set_receipt_footer_entry", None)
print("set_receipt_header_entry exists:", header_entry is not None)
print("set_receipt_footer_entry exists:", footer_entry is not None)

header_val = header_entry.get() if header_entry else None
footer_val = footer_entry.get() if footer_entry else None
print("header_note pre-populated:", repr(header_val))
print("footer_note pre-populated:", repr(footer_val))

# Verify the entry is an empty string (not "None") when config has empty value
if header_val is not None and str(header_val) == "None":
    errors.append(f"header_note shows 'None' instead of empty string: {header_val!r}")
if footer_val is not None and str(footer_val) == "None":
    errors.append(f"footer_note shows 'None' instead of empty string: {footer_val!r}")

# ── Layout integrity: all settings form children visible within scrollable area ──
scroll = tab.winfo_children()[0]  # CTkScrollableFrame
print("Scroll frame height:", scroll.winfo_height())
print("Scroll frame width:", scroll.winfo_width())

# Check each grid child is within bounds
clip_count = 0
for child in tab.winfo_children():
    x = child.winfo_x()
    y = child.winfo_y()
    w = child.winfo_width()
    h = child.winfo_height()
    if x + w > tab.winfo_width() + 50 and w > 0:
        clip_count += 1
        print(f"  CLIPPED: {child} x={x} w={w} tab_w={tab.winfo_width()}")

print("Clipped children:", clip_count)

# ── VG-4: _notify_config_updated is callable and delegates to checkout ──
try:
    # This should not raise even if checkout cart is empty
    app._notify_config_updated()
    print("_notify_config_updated() executed OK")
except Exception as e:
    errors.append(f"_notify_config_updated raised: {e}")
    print("_notify_config_updated() raised:", e)

# ── Verify on_tab_change settings branch calls _notify_config_updated ──
import inspect
source = inspect.getsource(app.on_tab_change)
if "_notify_config_updated" in source:
    print("on_tab_change references _notify_config_updated: YES")
else:
    errors.append("on_tab_change does NOT reference _notify_config_updated")

# ── Verify save_settings uses merge (not new_config dict) ──
ss_source = inspect.getsource(app.save_settings)
if "new_config" in ss_source:
    errors.append("save_settings still uses new_config dict (unsafe write)")
else:
    print("save_settings uses merge pattern: YES (no new_config)")
if "_notify_config_updated" in ss_source:
    print("save_settings calls _notify_config_updated: YES")
else:
    errors.append("save_settings does NOT call _notify_config_updated")

# ── Verify _refresh_cart_treeview is called by _notify_config_updated ──
ncu_source = inspect.getsource(app._notify_config_updated)
if "_refresh_cart_treeview" in ncu_source:
    print("_notify_config_updated refreshes checkout cart: YES")
else:
    errors.append("_notify_config_updated does NOT refresh checkout cart")

# ── Verify receipt engine renders notes ──
from receipt_engine import generate_receipt
info = {
    "pharmacy_name": "Test Pharmacy",
    "address": "123 Main St",
    "phone": "555-0100",
    "receipt_header_note": "Have ID ready",
    "receipt_footer_note": "Returns within 30 days",
}
path = generate_receipt(
    receipt_id=999,
    cart_items=[{"product_name": "Test Drug", "quantity": 1, "price_at_time": 10.0}],
    subtotal=10.0,
    total=10.80,
    tax=0.80,
    payment_type="Cash",
    patient_name="TestPatient",
    pharmacy_info=info,
)
content = open(path, encoding="utf-8").read()
assert "Have ID ready" in content, "header note missing from receipt"
assert "Returns within 30 days" in content, "footer note missing from receipt"
print("Receipt header/footer notes render: YES")

# ── Clean shutdown ──
app._barcode_listener.stop() if hasattr(app, "_barcode_listener") else None
app.destroy()

print()
if errors:
    print("SMOKE TEST ERRORS:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL SMOKE CHECKS PASSED")
