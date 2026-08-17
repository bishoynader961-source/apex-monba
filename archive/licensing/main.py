"""
PharmacyPro — Licensing Gate + Application Launcher
Validates license on startup. Shows activation screen if invalid.
On success, launches the main pharmacy dashboard.
"""
import os
import sys
import json
import uuid
import hashlib
import platform
import webbrowser
from pathlib import Path
from datetime import datetime, timezone

import customtkinter as ctk
import requests
from tkinter import messagebox

# ── Configuration ────────────────────────────────────────────────────────────
LICENSE_API_BASE = "https://licenseserver-1.vercel.app"  # ← Replace with your Vercel URL before deployment
LICENSE_FILE = Path(__file__).parent / "license.json"
BUY_URL = "https://pharmacy-pro.lemonsqueezy.com/checkout/buy/924ce157-aeaa-4bda-b7dc-1b73dace014b"
APP_TITLE = "PharmacyPro"
APP_VERSION = "1.0.0"


# ── Hardware Fingerprint ─────────────────────────────────────────────────────
def get_instance_id() -> str:
    """Generate a stable hardware fingerprint from machine identifiers."""
    raw = f"{platform.node()}-{platform.machine()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ── License Persistence ─────────────────────────────────────────────────────
def load_local_license() -> dict | None:
    """Load saved license from disk."""
    if not LICENSE_FILE.exists():
        return None
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_local_license(license_key: str, email: str = "") -> None:
    """Persist license key to disk."""
    data = {
        "license_key": license_key,
        "email": email,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "instance_id": get_instance_id(),
    }
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Server Validation ────────────────────────────────────────────────────────
def validate_license(license_key: str) -> dict:
    """
    Call the licensing API to validate the key.
    Returns {"valid": True} or {"valid": False, "error": "..."}.
    """
    device_id = get_instance_id()
    url = f"{LICENSE_API_BASE}/validate"
    payload = {"license_key": license_key, "device_id": device_id}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"valid": False, "error": "No internet connection. Please connect and try again."}
    except requests.exceptions.Timeout:
        return {"valid": False, "error": "Server timed out. Please try again."}
    except requests.exceptions.RequestException as e:
        return {"valid": False, "error": f"Validation failed: {str(e)}"}
    except (json.JSONDecodeError, ValueError):
        return {"valid": False, "error": "Invalid response from server."}


# ── Activation Screen GUI ───────────────────────────────────────────────────
class ActivationScreen(ctk.CTk):
    """Beautiful activation window shown when license is missing or invalid."""

    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} — Activation Required")
        self.geometry("520x480")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.configure(fg_color="#1a1a2e")
        self._build_ui()

    def _build_ui(self):
        # ── Header ──
        ctk.CTkLabel(
            self, text=APP_TITLE,
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="#4fc3f7",
        ).pack(pady=(40, 5))

        ctk.CTkLabel(
            self, text="Activation Required",
            font=ctk.CTkFont(size=18),
            text_color="#b0bec5",
        ).pack(pady=(0, 30))

        # ── Card Frame ──
        card = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=16)
        card.pack(padx=40, fill="x")

        ctk.CTkLabel(
            card, text="Enter your license key to activate:",
            font=ctk.CTkFont(size=13),
            text_color="#90a4ae",
        ).pack(pady=(20, 8))

        self.license_entry = ctk.CTkEntry(
            card, width=360, height=42,
            placeholder_text="PHARM-XXXX-XXXX-XXXX",
            font=ctk.CTkFont(size=14),
            corner_radius=8,
        )
        self.license_entry.pack(pady=(0, 6), padx=20)
        self.license_entry.bind("<Return>", lambda e: self._activate())

        self.status_label = ctk.CTkLabel(
            card, text="",
            font=ctk.CTkFont(size=12),
            text_color="#ef5350",
            wraplength=340,
        )
        self.status_label.pack(pady=(0, 10))

        # ── Buttons ──
        self.activate_btn = ctk.CTkButton(
            card, text="Activate", height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#4fc3f7", hover_color="#039be5",
            text_color="#000000",
            command=self._activate,
        )
        self.activate_btn.pack(padx=20, fill="x", pady=(0, 10))

        ctk.CTkButton(
            card, text="Buy Now", height=38,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=1, border_color="#4fc3f7",
            text_color="#4fc3f7",
            hover_color="#1a2744",
            command=lambda: webbrowser.open(BUY_URL),
        ).pack(padx=20, fill="x", pady=(0, 20))

        # ── Footer ──
        ctk.CTkLabel(
            self,
            text=f"v{APP_VERSION}  |  License is bound to this device after first activation.",
            font=ctk.CTkFont(size=11),
            text_color="#546e7a",
        ).pack(side="bottom", pady=20)

    def _activate(self):
        """Validate the entered license key against the API."""
        key = self.license_entry.get().strip()
        if not key:
            self.status_label.configure(text="Please enter a license key.", text_color="#ef5350")
            return

        self.activate_btn.configure(state="disabled", text="Validating...")
        self.status_label.configure(text="Connecting to license server...", text_color="#ffb74d")
        self.update_idletasks()

        result = validate_license(key)

        if result.get("valid"):
            save_local_license(key, result.get("email", ""))
            self.status_label.configure(text="Activation successful!", text_color="#66bb6a")
            self.update_idletasks()
            self.after(800, self._launch_app)
        else:
            error = result.get("error", "Unknown error")
            self.status_label.configure(text=error, text_color="#ef5350")
            self.activate_btn.configure(state="normal", text="Activate")

    def _launch_app(self):
        """Destroy activation screen and launch the main pharmacy app."""
        self.destroy()
        launch_pharmacy_app()


# ── Application Launcher ─────────────────────────────────────────────────────
def launch_pharmacy_app():
    """Import and start the main PharmacyPro dashboard."""
    try:
        # ── THIS IS WHERE YOU IMPORT YOUR MAIN APP ──
        # Example:
        #   from pharmacy_app import PharmacyApp
        #   app = PharmacyApp()
        #   app.mainloop()
        #
        # For now, show a success placeholder:
        app = ctk.CTk()
        app.title(f"{APP_TITLE} — Dashboard")
        app.geometry("1000x700")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        ctk.CTkLabel(
            app, text=f"Welcome to {APP_TITLE}!",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).pack(expand=True)
        ctk.CTkLabel(
            app, text="License validated. Application loaded successfully.",
            font=ctk.CTkFont(size=14), text_color="#90a4ae",
        ).pack(expand=True)
        app.mainloop()
    except Exception as e:
        messagebox.showerror("Launch Error", f"Failed to start {APP_TITLE}:\n{str(e)}")
        sys.exit(1)


# ── Entry Point ──────────────────────────────────────────────────────────────
def main():
    """License gate: check local file → validate online → launch or lock."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Step 1: Check local license file
    local = load_local_license()

    if local and local.get("license_key"):
        # Step 2: Validate against server
        result = validate_license(local["license_key"])
        if result.get("valid"):
            launch_pharmacy_app()
            return
        # Invalid — fall through to activation screen

    # Step 3: Show activation screen
    activation = ActivationScreen()
    activation.mainloop()


if __name__ == "__main__":
    main()
