import sys
import customtkinter as ctk
import database
import barcode_logic
import audit_log
import backup
import alert_engine
import i18n
from path_utils import ensure_runtime_directories
from license_gate import LicenseGate, is_dev_mode, is_dev_mac, get_device_mac
from updater import check_for_updates
from ui import PharmacyApp
from crash_reporter import install_crash_reporter

UPDATE_API_URL = "https://inventory1app1NN.pythonanywhere.com/api/check-update"

def main():
    # ── Install crash reporter FIRST (before anything that can crash) ──
    install_crash_reporter()
    ensure_runtime_directories()

    # ── Initialize i18n (load locale files, restore saved language) ──
    i18n.init()

    # ── Dev bypass: skip license gate entirely if dev_config.json present ──
    if is_dev_mode():
        print("[DEV MODE] License gate bypassed — dev_config.json detected.")
    elif is_dev_mac():
        print(f"[DEV MODE] Dev Hardware ID recognized ({get_device_mac()}). Skipping license check.")
    else:
        gate = LicenseGate()
        gate.mainloop()
        if not getattr(gate, "is_valid", False):
            sys.exit(0)

    # ── Auto-update check (non-blocking on failure) ──
    check_for_updates(UPDATE_API_URL)

    # Set the general appearance of the custom tkinter window
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    # Initialize the database (creates tables if missing)
    database.init_db()
    audit_log.init_audit_db()
    
    # Start background database backup
    backup.start_background_backup()
    
    # Start alert engine polling
    alert_engine.start_alert_engine()
    
    # Ensure the labels directory exists
    barcode_logic.init_labels_dir()
    
    # Create and run the application
    app = PharmacyApp()
    app.mainloop()

if __name__ == "__main__":
    main()
