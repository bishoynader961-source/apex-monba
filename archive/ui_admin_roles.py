"""ui_admin_roles.py — Owner-facing Roles & Permissions administration.

Launched only by an authenticated Owner (``roles.manage`` + Owner override).
Renders a live permission matrix per role and allows the Owner to change the
master Owner-override password. All mutations are audit-logged.
"""
from __future__ import annotations

from tkinter import messagebox as msgbox

import customtkinter as ctk

import auth_session
import authz
import audit_log
import database as db


def _prompt_new_override(parent) -> str | None:
    """Modal to capture a new Owner override password (validated)."""
    result = {"pw": None}

    dlg = ctk.CTkToplevel(parent)
    dlg.title("New Owner Override Password")
    dlg.resizable(False, False)
    dlg.grab_set()

    ctk.CTkLabel(dlg, text="Set a new Owner override password", font=ctk.CTkFont(size=13)).pack(
        padx=20, pady=(16, 8)
    )
    e1 = ctk.CTkEntry(dlg, placeholder_text="New password (min 8 chars)", show="*", width=280)
    e1.pack(padx=20, pady=(4, 4))
    e2 = ctk.CTkEntry(dlg, placeholder_text="Confirm password", show="*", width=280)
    e2.pack(padx=20, pady=(4, 10))

    def _submit():
        pw = e1.get()
        if len(pw) < 8 or pw != e2.get():
            msgbox.showerror("Invalid", "Password must be at least 8 characters and match confirmation.")
            return
        result["pw"] = pw
        dlg.grab_release()
        dlg.destroy()

    ctk.CTkButton(dlg, text="Save", command=_submit, width=280, height=36).pack(padx=20, pady=(4, 16))
    e1.focus_set()
    dlg.wait_window()
    return result["pw"]


class AdminRolesPanel(ctk.CTkToplevel):
    """Owner RBAC administration window."""

    def __init__(self, app):
        super().__init__(app)
        self.title("Roles & Permissions (Owner)")
        self._app = app
        self._roles = db.get_roles()
        self._perms = db.get_permissions()
        self._role_id = self._roles[0][0]
        self._build()
        self.resizable(True, True)

    def _build(self):
        ctk.CTkLabel(
            self, text="Role-Based Access Control", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(padx=16, pady=(14, 4))

        role_names = [r[1] for r in self._roles]
        self._role_var = ctk.StringVar(value=role_names[0])
        ctk.CTkOptionMenu(
            self, values=role_names, variable=self._role_var, command=self._on_role_change
        ).pack(padx=16, pady=(4, 8))

        self._perm_frame = ctk.CTkScrollableFrame(self, width=560, height=380)
        self._perm_frame.pack(padx=16, pady=(0, 8), fill="both", expand=True)

        self._check_vars: dict = {}
        self._render_perms()

        ctk.CTkButton(
            self, text="Change Owner Override Password", command=self._on_change_override
        ).pack(padx=16, pady=(4, 14))

    def _render_perms(self):
        for child in list(self._perm_frame.winfo_children()):
            child.destroy()
        self._check_vars.clear()
        granted = db.get_role_permissions(self._role_id)
        for _pid, key, desc in self._perms:
            var = ctk.BooleanVar(value=key in granted)
            self._check_vars[key] = var
            ctk.CTkCheckBox(
                self._perm_frame,
                text=f"{key}  —  {desc}",
                variable=var,
                command=lambda k=key, v=var: self._on_toggle(k, v),
            ).pack(anchor="w", padx=8, pady=3)

    def _on_role_change(self, name: str):
        rid = next((r[0] for r in self._roles if r[1] == name), None)
        if rid is not None:
            self._role_id = rid
            self._render_perms()

    def _on_toggle(self, key: str, var: ctk.BooleanVar):
        new_state = db.toggle_permission(self._role_id, key)
        var.set(new_state)
        audit_log.log_action(
            "rbac.permission_toggle",
            f"role_id={self._role_id} feature={key} granted={new_state}",
            user_pin=str(auth_session.current_user_id()),
        )

    def _on_change_override(self):
        if not auth_session.require_owner_override(self):
            return
        new_pw = _prompt_new_override(self)
        if new_pw:
            db.set_owner_override_password(new_pw)
            db.mark_owner_override_rotated()
            audit_log.log_action(
                "rbac.owner_override_rotated", "", user_pin=str(auth_session.current_user_id())
            )
            msgbox.showinfo("Updated", "Owner override password changed.")


def open_admin_roles(app) -> None:
    """Entry point: enforces Owner permission + override, then opens the panel."""
    if not authz.check_permission(auth_session.current_user_id(), "roles.manage"):
        authz.access_denied("roles.manage")
        return
    if not auth_session.require_owner_override(app):
        return
    AdminRolesPanel(app)
