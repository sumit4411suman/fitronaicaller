"""Screen 5: contact detail & history (edit, permissions/consent, opt-out, eligibility, calls, notes, follow-ups)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.screens.contacts import ContactDialog
from sellagent_desktop.widgets import Card, DataTable, EmptyState, FormDialog, KeyValueGrid, TextInputDialog, button, caption, combo, confirm, datetime_edit, fmt_dt, status_label


class ConsentDialog(FormDialog):
    def __init__(self, parent: QWidget | None):
        super().__init__(parent, "Record consent / permission", "Record")
        self.add_field("status", "Status", combo([("granted", "granted"), ("denied", "denied"), ("withdrawn", "withdrawn")]), required=True)
        src = QLineEdit()
        src.setPlaceholderText("e.g. inquiry form #123, existing customer, verbal on 2026-10-01")
        self.add_field("source", "Source of consent", src, required=True)
        self.add_field("channel", "Channel", combo([(c, c) for c in ("voice", "sms", "email", "form", "in_person")]))
        ev = QPlainTextEdit()
        ev.setMaximumHeight(70)
        self.add_field("evidence", "Evidence (optional)", ev)


class FollowupDialog(FormDialog):
    def __init__(self, parent: QWidget | None):
        super().__init__(parent, "Schedule follow-up", "Schedule")
        self.add_field("due_at", "Due", datetime_edit(), required=True)
        self.add_field("kind", "Kind", combo([(k, k) for k in ("call", "demo", "email", "human_handoff")]))
        self.add_field("note", "Note", QLineEdit())


class ContactDetailScreen(BaseScreen):
    key, title = "contact_detail", "Contact detail"

    def build(self) -> None:
        self.contact_id: str | None = None
        self.contact: dict | None = None
        head = QHBoxLayout()
        self.name_lbl = status_label("Select a contact from CRM contacts.")
        self.name_lbl.setStyleSheet("font-size: 16px; font-weight: 600; color: #D4AF37;")
        head.addWidget(self.name_lbl, 1)
        self.edit_btn = button("Edit", None, self.edit_contact)
        self.optout_btn = button("Opt-out", "danger", self.opt_out)
        self.job_btn = button("Create call job", "primary", lambda: self.contact and self.ctx.navigate("call_queue", contact_id=self.contact["id"]))
        for b in (self.edit_btn, self.job_btn, self.optout_btn):
            head.addWidget(b)
        self.root.addLayout(head)
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)

        # Overview
        ov = QWidget()
        ovl = QVBoxLayout(ov)
        self.grid = KeyValueGrid()
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.addWidget(self.grid)
        il.addStretch(1)
        sc.setWidget(inner)
        ovl.addWidget(sc)
        self.tabs.addTab(ov, "Overview")

        # Permissions
        pm = QWidget()
        pml = QVBoxLayout(pm)
        pml.addWidget(caption("Every consent decision is stored with its source and evidence. Eligibility uses the contact's consent_status summary, which the backend updates from these records."))
        self.perm_table = DataTable([("Recorded", lambda r: fmt_dt(r.get("recorded_at"))), ("Status", "status"), ("Channel", "channel"), ("Source", "source"), ("Evidence", "evidence"), ("By", "recorded_by"), ("Expires", lambda r: fmt_dt(r.get("expires_at")))])
        pml.addWidget(self.perm_table, 1)
        self.perm_empty = EmptyState("No permission records yet. Record consent before calling.")
        pml.addWidget(self.perm_empty)
        pml.addWidget(button("Record consent / permission", "primary", self.add_consent))
        self.tabs.addTab(pm, "Permissions")

        # Eligibility
        el = QWidget()
        ell = QVBoxLayout(el)
        self.elig_banner = status_label("")
        ell.addWidget(self.elig_banner)
        self.elig_grid = KeyValueGrid()
        ell.addWidget(self.elig_grid)
        ell.addWidget(button("Re-check now", None, self.load_eligibility))
        ell.addStretch(1)
        self.tabs.addTab(el, "Eligibility")

        # Calls
        cl = QWidget()
        cll = QVBoxLayout(cl)
        self.calls_table = DataTable([("Started", lambda r: fmt_dt(r.get("started_at"))), ("State", "conversation_state"), ("Outcome", "outcome"), ("Detail", "outcome_detail"), ("Duration s", "duration_seconds"), ("Language", "language")])
        self.calls_table.itemDoubleClicked.connect(lambda *_: self._open_call())
        cll.addWidget(self.calls_table, 1)
        self.calls_empty = EmptyState("No calls logged for this contact.")
        cll.addWidget(self.calls_empty)
        cll.addWidget(button("Open in call history", None, self._open_call))
        self.tabs.addTab(cl, "Call history")

        # Notes
        nt = QWidget()
        ntl = QVBoxLayout(nt)
        ntl.addWidget(caption("Free-text notes stored on the contact record (PATCH /contacts/{id})."))
        self.notes = QPlainTextEdit()
        self.notes.setAccessibleName("Contact notes")
        ntl.addWidget(self.notes, 1)
        ntl.addWidget(button("Save notes", "primary", self.save_notes))
        self.tabs.addTab(nt, "Notes")

        # Follow-ups
        fu = QWidget()
        ful = QVBoxLayout(fu)
        self.fu_table = DataTable([("Due", lambda r: fmt_dt(r.get("due_at"))), ("Kind", "kind"), ("Status", "status"), ("Note", "note"), ("Completed", lambda r: fmt_dt(r.get("completed_at")))])
        ful.addWidget(self.fu_table, 1)
        self.fu_empty = EmptyState("No follow-ups scheduled.")
        ful.addWidget(self.fu_empty)
        row = QHBoxLayout()
        row.addWidget(button("Schedule follow-up", "primary", self.add_followup))
        row.addWidget(button("Mark done", None, lambda: self._complete_fu("done")))
        row.addWidget(button("Cancel follow-up", None, lambda: self._complete_fu("cancelled")))
        row.addStretch(1)
        ful.addLayout(row)
        self.tabs.addTab(fu, "Follow-ups")
        self.empty = EmptyState("Open a contact from the CRM list (double-click or 'Open detail').")
        self.root.addWidget(self.empty)
        self._set_enabled(False)

    def _set_enabled(self, on: bool) -> None:
        self.tabs.setVisible(on)
        self.empty.setVisible(not on)
        for b in (self.edit_btn, self.optout_btn, self.job_btn):
            b.setEnabled(on)

    def set_context(self, contact_id: str | None = None, **_: object) -> None:
        if contact_id:
            self.contact_id = contact_id

    def refresh(self) -> None:
        if not self.contact_id:
            self._set_enabled(False)
            return
        cid = self.contact_id
        self.run(lambda: (self.api.get(f"/contacts/{cid}"), self.api.get(f"/contacts/{cid}/permissions"), self.api.get("/calls", contact_id=cid, limit=200), self.api.get("/followups", contact_id=cid, include_done=True)), self._show)

    def _show(self, res: tuple) -> None:
        c, perms, calls, fus = res
        self.contact = c
        self._set_enabled(True)
        flags = []
        if c.get("opted_out"):
            flags.append("OPTED OUT")
        if c.get("archived"):
            flags.append("ARCHIVED")
        self.name_lbl.setText(f"{c['business_name']} — {c['phone_e164']}" + (f"   [{' · '.join(flags)}]" if flags else ""))
        self.grid.set_rows([(k.replace("_", " "), c.get(k) if not str(k).endswith("_at") else fmt_dt(c.get(k))) for k in ("id", "business_name", "contact_person", "phone_e164", "phone_raw", "email", "city", "district", "state", "country", "source_url", "source_verification", "lead_source", "lead_stage", "campaign_id", "consent_status", "opted_out", "opt_out_reason", "opted_out_at", "tags", "last_contact_at", "next_followup_at", "archived", "created_at", "updated_at")])
        self.perm_table.set_rows(perms)
        self.perm_empty.setVisible(not perms)
        items = calls.get("items", [])
        self.calls_table.set_rows(items)
        self.calls_empty.setVisible(not items)
        self.notes.setPlainText(c.get("notes") or "")
        self.fu_table.set_rows(fus)
        self.fu_empty.setVisible(not fus)
        self.load_eligibility()

    def load_eligibility(self) -> None:
        if not self.contact_id:
            return
        cid = self.contact_id
        self.run(lambda: self.api.get(f"/contacts/{cid}/eligibility"), self._show_elig)

    def _show_elig(self, e: dict) -> None:
        ok = e.get("eligible")
        self.elig_banner.setText("ELIGIBLE for a human-assisted manual call" if ok else "NOT ELIGIBLE: " + "; ".join(e.get("reasons", [])))
        self.elig_banner.setProperty("role", "success" if ok else "danger")
        self.elig_banner.style().unpolish(self.elig_banner)
        self.elig_banner.style().polish(self.elig_banner)
        rows = [("Checked at", fmt_dt(e.get("checked_at"), True)), ("Warnings", "\n".join(e.get("warnings", [])) or "none")]
        rows += [(f"check: {k}", v) for k, v in (e.get("checks") or {}).items()]
        self.elig_grid.set_rows(rows)

    def edit_contact(self) -> None:
        if not self.contact:
            return
        dlg = ContactDialog(self, existing=self.contact)
        if dlg.exec() != ContactDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()
        cid = self.contact["id"]
        self.run(lambda: self.api.patch(f"/contacts/{cid}", payload), lambda _: (self.toast("Contact saved", "success"), self.refresh()))

    def save_notes(self) -> None:
        if not self.contact_id:
            return
        cid, text = self.contact_id, self.notes.toPlainText().strip() or None
        self.run(lambda: self.api.patch(f"/contacts/{cid}", {"notes": text}), lambda _: self.toast("Notes saved", "success"))

    def add_consent(self) -> None:
        if not self.contact_id:
            return
        dlg = ConsentDialog(self)
        if dlg.exec() != ConsentDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        v["evidence"] = v["evidence"] or None
        cid = self.contact_id
        self.run(lambda: self.api.post(f"/contacts/{cid}/permissions", v), lambda _: (self.toast("Permission recorded", "success"), self.refresh()))

    def opt_out(self) -> None:
        if not self.contact:
            return
        dlg = TextInputDialog(self, "Opt-out", "Reason (required, stored in the audit log)", placeholder="e.g. asked not to be called on 2026-10-18", note="The number is added to the suppression list and the contact can no longer be queued.")
        if dlg.exec() != TextInputDialog.DialogCode.Accepted:
            return
        cid, reason = self.contact["id"], dlg.value().strip()
        self.run(lambda: self.api.post(f"/contacts/{cid}/opt-out", {"reason": reason, "source": "operator"}), lambda _: (self.toast("Contact opted out", "warning"), self.refresh()))

    def add_followup(self) -> None:
        if not self.contact_id:
            return
        dlg = FollowupDialog(self)
        if dlg.exec() != FollowupDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        body = {"contact_id": self.contact_id, "due_at": v["due_at"], "kind": v["kind"], "note": v["note"] or None}
        self.run(lambda: self.api.post("/followups", body), lambda _: (self.toast("Follow-up scheduled", "success"), self.refresh()))

    def _complete_fu(self, status: str) -> None:
        row = self.fu_table.selected_row()
        if not row:
            self.toast("Select a follow-up first", "warning")
            return
        if row.get("status") != "open":
            self.toast("Follow-up is already closed", "warning")
            return
        fid = row["id"]
        self.run(lambda: self.api.post(f"/followups/{fid}/complete", params={"status": status}), lambda _: self.refresh())

    def _open_call(self) -> None:
        row = self.calls_table.selected_row()
        if row:
            self.ctx.navigate("call_history", call_id=row["id"])
        elif self.contact_id:
            self.ctx.navigate("call_history", contact_id=self.contact_id)
