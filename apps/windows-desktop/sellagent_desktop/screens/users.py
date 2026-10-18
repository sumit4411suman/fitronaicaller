"""Settings › Users & Roles (admin only): local users with PIN sign-in, roles and the permission matrix."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, EmptyState, FormDialog, TextInputDialog, button, caption, combo, confirm, fmt_dt, mark_invalid

ROLES = ("admin", "manager", "operator", "viewer")
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,50}$")


def pin_problem(pin: str) -> str | None:
    """Mirror of the backend rule so the dialog can show the problem before sending."""
    if not re.fullmatch(r"\d{6,12}", pin or ""):
        return "PIN must be 6 to 12 digits"
    if len(set(pin)) == 1 or pin in "0123456789012" or pin in "9876543210987":
        return "PIN is too easy to guess (repeated or sequential digits)"
    return None


class UserDialog(FormDialog):
    def __init__(self, parent: QWidget | None, existing: dict | None = None):
        super().__init__(parent, "Edit user" if existing else "New user", "Save" if existing else "Create user")
        e = existing or {}
        self.existing = existing
        un = QLineEdit(e.get("username", ""))
        un.setEnabled(existing is None)
        un.setPlaceholderText("lowercase letters, digits, . _ -")
        self.add_field("username", "Username", un, required=existing is None)
        self.add_field("display_name", "Display name", QLineEdit(e.get("display_name", "")), required=True)
        self.add_field("role", "Role", combo([(r, r) for r in ROLES], e.get("role", "operator")))
        if existing is None:
            pin = QLineEdit()
            pin.setEchoMode(QLineEdit.EchoMode.Password)
            pin.setPlaceholderText("6–12 digits, not repeated or sequential")
            self.add_field("pin", "PIN", pin, required=True)
        else:
            act = QCheckBox("active (can sign in)")
            act.setChecked(bool(e.get("active", True)))
            self.add_field("active", "Status", act)

    def validate(self) -> bool:
        ok = super().validate()
        if self.existing is None:
            if not USERNAME_RE.match(self.raw_value("username") or ""):
                self.set_field_error("username", "3–50 characters: a-z, 0-9, dot, underscore, dash")
                ok = False
            prob = pin_problem(self.raw_value("pin"))
            if prob:
                self.set_field_error("pin", prob)
                ok = False
        return ok


class UsersScreen(BaseScreen):
    key, title = "users", "Users & Roles"
    subtitle = "Local users sign in with a PIN (Switch user in the header menu). The desktop itself always starts as the built-in owner (admin)."

    def build(self) -> None:
        bar = QHBoxLayout()
        self.new_btn = button("+ New user", "primary", self.new_user)
        self.edit_btn = button("Edit / role", None, self.edit_user)
        self.toggle_btn = button("Disable", None, self.toggle_active)
        self.pin_btn = button("Reset PIN", None, self.reset_pin)
        self.del_btn = button("Delete", "danger", self.delete_user)
        for b in (self.new_btn, self.edit_btn, self.toggle_btn, self.pin_btn, self.del_btn):
            b.setProperty("perm", "users:write")
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(button("Reload", None, self.refresh))
        self.root.addLayout(bar)
        self.table = DataTable([("Username", "username"), ("Display name", "display_name"), ("Role", "role"), ("Active", "active"), ("Last login", lambda r: fmt_dt(r.get("last_login_at"))), ("Locked until", lambda r: fmt_dt(r.get("locked_until"))), ("Created", lambda r: fmt_dt(r.get("created_at")))])
        self.table.setObjectName("users_table")
        self.table.itemSelectionChanged.connect(self._select)
        self.root.addWidget(self.table, 1)
        self.empty = EmptyState("No users yet. Create one per person who should sign in with their own PIN.")
        self.root.addWidget(self.empty)
        mc = Card("Permission matrix (read-only, from /auth/roles)")
        mc.add(caption("'*' = everything. read = view (GET); write = change. EMERGENCY STOP can be activated by every role; clearing it needs calls:write."))
        self.matrix = QTableWidget(0, len(ROLES))
        self.matrix.setObjectName("permission_matrix")
        self.matrix.setHorizontalHeaderLabels(list(ROLES))
        self.matrix.setMinimumHeight(220)
        mc.add(self.matrix)
        self.root.addWidget(mc, 1)
        self._select()

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/users"), self.api.get("/auth/roles")), self._show)

    def _show(self, res: tuple) -> None:
        users, roles = res
        self.table.set_rows(users)
        self.empty.setVisible(not users)
        perms = roles.get("roles", {})
        areas = sorted({p.split(":")[0] for ps in perms.values() for p in ps if ":" in p})
        self.matrix.setColumnCount(len(perms))
        self.matrix.setHorizontalHeaderLabels(list(perms))
        self.matrix.setRowCount(len(areas))
        self.matrix.setVerticalHeaderLabels(areas)
        for c, (_role, ps) in enumerate(perms.items()):
            pset = set(ps)
            for r, area in enumerate(areas):
                if "*" in pset:
                    txt = "read · write"
                else:
                    txt = " · ".join(x for x in ("read", "write") if f"{area}:{x}" in pset) or "—"
                self.matrix.setItem(r, c, QTableWidgetItem(txt))
        self.matrix.resizeColumnsToContents()
        self._select()
        self.apply_permissions()

    def _select(self) -> None:
        u = self.table.selected_row()
        for b in (self.edit_btn, self.toggle_btn, self.pin_btn, self.del_btn):
            b.setEnabled(u is not None)
        self.toggle_btn.setText("Enable" if u and not u.get("active") else "Disable")

    def _sel(self) -> dict | None:
        u = self.table.selected_row()
        if u is None:
            self.toast("Select a user", "warning")
        return u

    def new_user(self) -> None:
        dlg = UserDialog(self)
        if dlg.exec() == UserDialog.DialogCode.Accepted:
            body = {k: dlg.raw_value(k) for k in ("username", "display_name", "role", "pin")}
            self.run(lambda: self.api.post("/users", body), lambda u: (self.toast(f"User {u['username']} created ({u['role']})", "success"), self.refresh()))

    def edit_user(self) -> None:
        u = self._sel()
        if not u:
            return
        dlg = UserDialog(self, existing=u)
        if dlg.exec() == UserDialog.DialogCode.Accepted:
            body = {"display_name": dlg.raw_value("display_name"), "role": dlg.raw_value("role"), "active": dlg.raw_value("active")}
            self.run(lambda: self.api.patch(f"/users/{u['id']}", body), lambda _: (self.toast("User saved — their sessions were signed out if role/status changed", "success"), self.refresh()))

    def toggle_active(self) -> None:
        u = self._sel()
        if not u:
            return
        new = not u.get("active")
        if not new and not confirm(self, "Disable user", f"Disable {u['username']}? Their open sessions end immediately.", "Disable", danger=True):
            return
        self.run(lambda: self.api.patch(f"/users/{u['id']}", {"active": new}), lambda _: self.refresh())

    def reset_pin(self) -> None:
        u = self._sel()
        if not u:
            return
        dlg = TextInputDialog(self, "Reset PIN", f"New PIN for {u['username']}", password=True, min_length=6, note="6–12 digits, not repeated or sequential. Their open sessions end.")
        if dlg.exec() != TextInputDialog.DialogCode.Accepted:
            return
        pin = dlg.value().strip()
        prob = pin_problem(pin)
        if prob:
            mark_invalid(dlg.edit, True)
            self.toast(prob, "error")
            return
        self.run(lambda: self.api.post(f"/users/{u['id']}/reset-pin", {"pin": pin}), lambda _: self.toast("PIN reset", "success"))

    def delete_user(self) -> None:
        u = self._sel()
        if u and confirm(self, "Delete user", f"Delete {u['username']} permanently? (Disabling keeps their audit trail readable by name.)", "Delete", danger=True):
            self.run(lambda: self.api.delete(f"/users/{u['id']}"), lambda _: self.refresh())
