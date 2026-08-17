"""ui_auth.py — Owner account creation dialog (CustomTkinter).

Implements Option A of the RBAC plan: when the system detects that no users
exist (fresh database), the application launches ``CreateOwnerAccountDialog``
to mint the initial ``owner`` account. The actual creation is delegated to
``authz.create_first_owner``, which enforces the anti-escalation guard
(only permitted when zero users exist).
"""
from __future__ import annotations

from tkinter import messagebox as msgbox

import customtkinter as ctk

import auth_session
import authz
import audit_log
import database as db

MIN_PASSWORD_LEN = 8


class CreateOwnerAccountDialog(ctk.CTkToplevel):
    """Modal dialog to create the first Owner account on a fresh system."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Create Owner Account")
        self.result: int | None = None
        self._build()
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build(self):
        pad = {"padx": 24, "pady": (10, 4)}
        ctk.CTkLabel(
            self,
            text="No user accounts found",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(padx=24, pady=(20, 2))
        ctk.CTkLabel(
            self,
            text="Create the system Owner account to continue.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(padx=24, pady=(0, 12))

        self._username = ctk.CTkEntry(self, placeholder_text="Username", width=320)
        self._username.pack(**pad)
        self._display = ctk.CTkEntry(self, placeholder_text="Display name (optional)", width=320)
        self._display.pack(**pad)
        self._password = ctk.CTkEntry(self, placeholder_text="Password (min 8 chars)", show="*", width=320)
        self._password.pack(**pad)
        self._confirm = ctk.CTkEntry(self, placeholder_text="Confirm password", show="*", width=320)
        self._confirm.pack(**pad)
        self._pin = ctk.CTkEntry(self, placeholder_text="Owner PIN (optional, for quick-auth)", show="*", width=320)
        self._pin.pack(**pad)

        ctk.CTkButton(
            self,
            text="Create Owner Account",
            command=self._on_submit,
            width=320,
            height=40,
        ).pack(padx=24, pady=(14, 20))

        # Focus the first field for fast data entry.
        self._username.focus_set()

    def _on_submit(self):
        username = self._username.get().strip()
        password = self._password.get()
        confirm = self._confirm.get()
        display = self._display.get().strip()
        pin = self._pin.get()

        if not username:
            msgbox.showerror("Invalid input", "A username is required.")
            return
        if len(password) < MIN_PASSWORD_LEN:
            msgbox.showerror("Invalid input", f"Password must be at least {MIN_PASSWORD_LEN} characters.")
            return
        if password != confirm:
            msgbox.showerror("Invalid input", "Passwords do not match.")
            return

        try:
            uid = authz.create_first_owner(username, password, display_name=display, pin=pin)
        except Exception as exc:  # surface middleware/validation errors to the user
            msgbox.showerror("Cannot create Owner", str(exc))
            return

        self.result = uid
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        # Disallow dismissing the mandatory first-run setup.
        msgbox.showwarning("Required", "An Owner account must be created to use the system.")
        # Keep the dialog open; do not set a result.
        self.lift()
        self.focus_force()


def maybe_show_create_owner(parent=None) -> int | None:
    """If the system has no users, show the Create Owner dialog and return the
    new user id. Returns ``None`` (and does nothing) when users already exist.
    """
    if db.count_users() != 0:
        return None
    dialog = CreateOwnerAccountDialog(parent)
    dialog.wait_window()
    return dialog.result


class LoginDialog(ctk.CTkToplevel):
    """Modal username/password login. On success sets the session and returns
    the user id via ``self.result``; ``None`` if cancelled/closed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Login")
        self.result: int | None = None
        self._build()
        self.resizable(False, False)
        self.grab_set()

    def _build(self):
        ctk.CTkLabel(self, text="PharmacyPro Login", font=ctk.CTkFont(size=16, weight="bold")).pack(
            padx=24, pady=(20, 12)
        )
        self._username = ctk.CTkEntry(self, placeholder_text="Username", width=300)
        self._username.pack(padx=24, pady=(4, 4))
        self._password = ctk.CTkEntry(self, placeholder_text="Password", show="*", width=300)
        self._password.pack(padx=24, pady=(4, 4))
        ctk.CTkButton(self, text="Sign in", command=self._on_submit, width=300, height=38).pack(
            padx=24, pady=(12, 20)
        )
        self._username.focus_set()
        self.bind("<Return>", lambda _e: self._on_submit())

    def _on_submit(self):
        import auth_session
        import authz
        import audit_log

        username = self._username.get().strip()
        password = self._password.get()
        if not username or not password:
            msgbox.showerror("Login failed", "Username and password are required.")
            return
        uid = db.authenticate_user(username, password)
        if uid is None:
            msgbox.showerror("Login failed", "Invalid credentials or account locked.")
            audit_log.log_action("auth.login_failed", f"username={username}")
            return
        auth_session.login(uid)
        audit_log.log_action("auth.login", f"user_id={uid}", user_pin=str(uid))
        self.result = uid
        self.grab_release()
        self.destroy()


class PinPrompt(ctk.CTkToplevel):
    """Modal PIN re-entry for PIN quick-auth. On success caches the PIN."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Confirm PIN")
        self.result = False
        self._build()
        self.resizable(False, False)
        self.grab_set()

    def _build(self):
        ctk.CTkLabel(self, text="Re-enter your PIN to continue", font=ctk.CTkFont(size=13)).pack(
            padx=24, pady=(18, 10)
        )
        self._pin = ctk.CTkEntry(self, placeholder_text="PIN", show="*", width=240)
        self._pin.pack(padx=24, pady=(4, 10))
        ctk.CTkButton(self, text="Confirm", command=self._on_submit, width=240, height=36).pack(
            padx=24, pady=(4, 16)
        )
        self._pin.focus_set()
        self.bind("<Return>", lambda _e: self._on_submit())

    def _on_submit(self):
        import auth_session
        uid = auth_session.current_user_id()
        if uid is None:
            msgbox.showerror("PIN required", "No active session.")
            return
        if db.verify_user_pin(uid, self._pin.get()):
            auth_session.cache_pin()
            self.result = True
            self.grab_release()
            self.destroy()
        else:
            msgbox.showerror("PIN incorrect", "The PIN you entered is incorrect.")


class OwnerOverridePrompt(ctk.CTkToplevel):
    """Modal Owner override master-password prompt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Owner Override")
        self.result = False
        self._build()
        self.resizable(False, False)
        self.grab_set()

    def _build(self):
        ctk.CTkLabel(
            self, text="Enter the Owner override password", font=ctk.CTkFont(size=13)
        ).pack(padx=24, pady=(18, 10))
        self._pw = ctk.CTkEntry(self, placeholder_text="Override password", show="*", width=280)
        self._pw.pack(padx=24, pady=(4, 10))
        ctk.CTkButton(self, text="Confirm", command=self._on_submit, width=280, height=36).pack(
            padx=24, pady=(4, 16)
        )
        self._pw.focus_set()
        self.bind("<Return>", lambda _e: self._on_submit())

    def _on_submit(self):
        if db.verify_owner_override(self._pw.get()):
            self.result = True
            self.grab_release()
            self.destroy()
        else:
            msgbox.showerror("Override denied", "The Owner override password is incorrect.")


def show_login(parent=None) -> int | None:
    dlg = LoginDialog(parent)
    dlg.wait_window()
    return dlg.result


def force_rotate_owner_override(parent=None) -> bool:
    """G8 forced gate: rotate the bootstrap Owner override before the UI is usable.

    Loops until the Owner (a) verifies the *current* (bootstrap) override secret
    via ``OwnerOverridePrompt`` and (b) supplies a new secret via the existing
    ``_prompt_new_override`` flow. Each successful rotation is persisted and
    audited. Returns True once rotated; the loop only exits on success.
    """
    from ui_admin_roles import _prompt_new_override

    while True:
        verify = OwnerOverridePrompt(parent)
        verify.wait_window()
        if not verify.result:
            # Must verify the current (default) secret before proceeding.
            continue
        new_pw = _prompt_new_override(parent)
        if not new_pw:
            # Cancelled the new-password step — re-prompt from the top.
            continue
        db.set_owner_override_password(new_pw)
        db.mark_owner_override_rotated()
        audit_log.log_action(
            "rbac.owner_override_rotated", "", user_pin=str(auth_session.current_user_id())
        )
        return True


def show_pin_prompt(parent=None) -> bool:
    dlg = PinPrompt(parent)
    dlg.wait_window()
    return dlg.result


def show_owner_override(parent=None) -> bool:
    dlg = OwnerOverridePrompt(parent)
    dlg.wait_window()
    return dlg.result


def force_relogin(app=None) -> None:
    """Logout the current session and re-show the login dialog.

    If the operator dismisses the login, the app is destroyed and the
    process exits — no unauthenticated state is ever reachable.
    """
    auth_session.logout()
    uid = show_login(app)
    if uid is None:
        if app and app.winfo_exists():
            app.destroy()
        import sys
        sys.exit(0)
    auth_session.login(uid)
    audit_log.log_action("auth.login", f"user_id={uid}", user_pin=str(uid))
    auth_session.start_session_timer(app, on_expire=lambda: force_relogin(app))
    # Re-apply RBAC-driven UI (e.g. nav button visibility) for the new session.
    try:
        from main_app import _apply_nav_permissions
        _apply_nav_permissions(app, uid)
    except Exception:
        pass


# Register the UI prompts with the session layer (no circular import: auth_session
# has no dependency on ui_auth).
import auth_session as _auth_session  # noqa: E402

_auth_session.set_owner_override_prompt(show_owner_override)
_auth_session.set_pin_prompt(show_pin_prompt)
