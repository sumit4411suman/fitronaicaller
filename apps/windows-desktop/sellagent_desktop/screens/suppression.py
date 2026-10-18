"""Screen 19: suppression & opt-out management."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, EmptyState, FormDialog, TextInputDialog, button, combo, fmt_dt, status_label


class SuppressDialog(FormDialog):
    def __init__(self, parent: QWidget | None):
        super().__init__(parent, "Add number to suppression list", "Suppress")
        ph = QLineEdit()
        ph.setPlaceholderText("+91 98765 43210")
        self.add_field("phone", "Phone", ph, required=True)
        self.add_field("reason", "Reason", combo([(r, r) for r in ("do_not_call_request", "wrong_number", "complaint", "legal", "duplicate", "other")]), required=True)
        n = QPlainTextEdit()
        n.setMaximumHeight(70)
        self.add_field("note", "Note", n)

    def payload(self) -> dict:
        v = self.values()
        v["note"] = v["note"] or None
        return v


class SuppressionScreen(BaseScreen):
    key, title = "suppression", "Suppression & opt-out"
    subtitle = "Numbers here are never dialled. Lifting an entry requires a written justification that is kept in the audit log."

    def build(self) -> None:
        bar = QHBoxLayout()
        self.active_only = QCheckBox("active only")
        self.active_only.setChecked(True)
        self.active_only.stateChanged.connect(self.refresh)
        bar.addWidget(self.active_only)
        bar.addWidget(button("Add number", "primary", self.add))
        bar.addWidget(button("Lift selected", None, self.lift))
        bar.addStretch(1)
        self.root.addLayout(bar)
        chk = Card("Check a number")
        cr = QHBoxLayout()
        self.check_edit = QLineEdit()
        self.check_edit.setPlaceholderText("phone number to check")
        self.check_edit.returnPressed.connect(self.check)
        cr.addWidget(self.check_edit, 1)
        cr.addWidget(button("Check", None, self.check))
        cw = QWidget()
        cw.setLayout(cr)
        chk.add(cw)
        self.check_lbl = status_label("")
        chk.add(self.check_lbl)
        self.root.addWidget(chk)
        self.table = DataTable([("Phone", "phone_e164"), ("Reason", "reason"), ("Note", "note"), ("Source", "source"), ("Active", "active"), ("Contact", "contact_id"), ("Added", lambda r: fmt_dt(r.get("created_at")))])
        self.root.addWidget(self.table, 1)
        self.empty = EmptyState("Suppression list is empty.")
        self.root.addWidget(self.empty)

    def refresh(self) -> None:
        self.run(lambda: self.api.get("/suppression", active_only=self.active_only.isChecked()), self._show)

    def _show(self, rows: list) -> None:
        self.table.set_rows(rows)
        self.empty.setVisible(not rows)

    def add(self) -> None:
        dlg = SuppressDialog(self)
        if dlg.exec() == SuppressDialog.DialogCode.Accepted:
            body = dlg.payload()
            self.run(lambda: self.api.post("/suppression", body), lambda r: (self.toast(f"{r['phone_e164']} suppressed", "success"), self.refresh()))

    def lift(self) -> None:
        row = self.table.selected_row()
        if not row:
            self.toast("Select an entry", "warning")
            return
        if not row.get("active"):
            self.toast("Entry is already inactive", "warning")
            return
        dlg = TextInputDialog(self, "Lift suppression", "Justification (min 3 characters; audited)", min_length=3, note=f"Lifting {row['phone_e164']} ({row['reason']}) makes the number callable again.")
        if dlg.exec() == TextInputDialog.DialogCode.Accepted:
            j = dlg.value().strip()
            self.run(lambda: self.api.post(f"/suppression/{row['id']}/lift", {"justification": j}), lambda _: (self.toast("Suppression lifted", "warning"), self.refresh()))

    def check(self) -> None:
        ph = self.check_edit.text().strip()
        if not ph:
            return
        self.run(lambda: self.api.get("/suppression/check", phone=ph), self._checked)

    def _checked(self, r: dict) -> None:
        self.check_lbl.setText(f"{r['phone_e164']}: " + (f"SUPPRESSED ({r.get('reason')})" if r.get("suppressed") else "not suppressed") + f" · checked {fmt_dt(r.get('checked_at'), True)}")
        self.check_lbl.setProperty("role", "danger" if r.get("suppressed") else "success")
        self.check_lbl.style().unpolish(self.check_lbl)
        self.check_lbl.style().polish(self.check_lbl)
