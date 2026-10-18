"""Screen 5: contact detail per the mockup — gold initials avatar, Call / Message (disabled) / Edit / More, lead-stage
dropdown, tabs Details / Call History / Notes plus Permissions, Eligibility and Follow-ups."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QMenu, QPlainTextEdit, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.screens.contacts import LEAD_STAGES, ContactDialog
from sellagent_desktop.widgets import STAGE_CHIP, DataTable, EmptyState, FormDialog, KeyValueGrid, TextInputDialog, avatar, button, caption, chip, combo, confirm, datetime_edit, fmt_dt, set_chip, status_label


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
        self.avatar = avatar("")
        head.addWidget(self.avatar)
        col = QVBoxLayout()
        self.name_lbl = status_label("Select a contact from Contacts.")
        self.name_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
        col.addWidget(self.name_lbl)
        self.sub_lbl = caption("")
        col.addWidget(self.sub_lbl)
        chips = QHBoxLayout()
        self.stage_chip = chip("—", "neutral")
        self.consent_chip = chip("consent —", "neutral")
        self.optout_chip = chip("OPTED OUT", "danger")
        self.optout_chip.setVisible(False)
        for c in (self.stage_chip, self.consent_chip, self.optout_chip):
            chips.addWidget(c)
        chips.addStretch(1)
        col.addLayout(chips)
        head.addLayout(col, 1)
        act = QVBoxLayout()
        row1 = QHBoxLayout()
        self.call_btn = button("Call", "primary", lambda: self.contact and self.ctx.navigate("call_queue", contact_id=self.contact["id"]), tooltip="Create a call job")
        self.msg_btn = button("Message", None, None, tooltip="No SMS/WhatsApp feature in SELL AGENT (voice only)")
        self.msg_btn.setEnabled(False)
        self.edit_btn = button("Edit", None, self.edit_contact)
        self.more_btn = button("More ▾", None, self.more_menu)
        for b in (self.call_btn, self.msg_btn, self.edit_btn, self.more_btn):
            row1.addWidget(b)
        act.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(caption("Lead stage"))
        self.stage_combo = combo([(s, s) for s in LEAD_STAGES])
        self.stage_combo.setAccessibleName("Lead stage")
        self.stage_combo.activated.connect(self.change_stage)
        row2.addWidget(self.stage_combo, 1)
        act.addLayout(row2)
        head.addLayout(act)
        self.root.addLayout(head)
        self.optout_btn = button("Opt-out", "danger", self.opt_out)  # kept for keyboard users; also in More
        self.optout_btn.setVisible(False)
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)

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
        self.tabs.addTab(ov, "Details")

        cl = QWidget()
        cll = QVBoxLayout(cl)
        self.calls_table = DataTable([("Started", lambda r: fmt_dt(r.get("started_at"))), ("State", "conversation_state"), ("Outcome", "outcome"), ("Detail", "outcome_detail"), ("Duration s", "duration_seconds"), ("Language", "language")])
        self.calls_table.itemDoubleClicked.connect(lambda *_: self._open_call())
        cll.addWidget(self.calls_table, 1)
        self.calls_empty = EmptyState("No calls logged for this contact.")
        cll.addWidget(self.calls_empty)
        cll.addWidget(button("Open in call history", None, self._open_call))
        self.tabs.addTab(cl, "Call History")

        nt = QWidget()
        ntl = QVBoxLayout(nt)
        ntl.addWidget(caption("Free-text notes stored on the contact record."))
        self.notes = QPlainTextEdit()
        self.notes.setAccessibleName("Contact notes")
        ntl.addWidget(self.notes, 1)
        ntl.addWidget(button("Save notes", "primary", self.save_notes))
        self.tabs.addTab(nt, "Notes")

        pm = QWidget()
        pml = QVBoxLayout(pm)
        pml.addWidget(caption("Every consent decision is stored with its source and evidence; eligibility uses the summary consent_status."))
        self.perm_table = DataTable([("Recorded", lambda r: fmt_dt(r.get("recorded_at"))), ("Status", "status"), ("Channel", "channel"), ("Source", "source"), ("Evidence", "evidence"), ("By", "recorded_by"), ("Expires", lambda r: fmt_dt(r.get("expires_at")))])
        pml.addWidget(self.perm_table, 1)
        self.perm_empty = EmptyState("No permission records yet. Record consent before calling.")
        pml.addWidget(self.perm_empty)
        pml.addWidget(button("Record consent / permission", "primary", self.add_consent))
        self.tabs.addTab(pm, "Permissions")

        el = QWidget()
        ell = QVBoxLayout(el)
        self.elig_banner = status_label("")
        ell.addWidget(self.elig_banner)
        self.elig_grid = KeyValueGrid()
        ell.addWidget(self.elig_grid)
        ell.addWidget(button("Re-check now", None, self.load_eligibility))
        ell.addStretch(1)
        self.tabs.addTab(el, "Eligibility")

        fu = QWidget()
        ful = QVBoxLayout(fu)
        self.fu_table = DataTable([("Due", lambda r: fmt_dt(r.get("due_at"))), ("Kind", "kind"), ("Status", "status"), ("Note", "note"), ("Completed", lambda r: fmt_dt(r.get("completed_at")))])
        ful.addWidget(self.fu_table, 1)
        self.fu_empty = EmptyState("No follow-ups scheduled.")
        ful.addWidget(self.fu_empty)
        fr = QHBoxLayout()
        fr.addWidget(button("Schedule follow-up", "primary", self.add_followup))
        fr.addWidget(button("Mark done", None, lambda: self._complete_fu("done")))
        fr.addWidget(button("Cancel follow-up", None, lambda: self._complete_fu("cancelled")))
        fr.addStretch(1)
        ful.addLayout(fr)
        self.tabs.addTab(fu, "Follow-ups")
        self.empty = EmptyState("Open a contact from the Contacts list (double-click, 'Open detail' or the row's Open button).")
        self.root.addWidget(self.empty)
        self._set_enabled(False)

    def _set_enabled(self, on: bool) -> None:
        self.tabs.setVisible(on)
        self.empty.setVisible(not on)
        for b in (self.edit_btn, self.more_btn, self.call_btn, self.stage_combo):
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
        self.avatar.setText((c.get("business_name") or "?")[:2].upper())
        self.name_lbl.setText(c["business_name"] + (f" · {c['contact_person']}" if c.get("contact_person") else ""))
        self.sub_lbl.setText(f"{c['phone_e164']} · {c.get('city') or ''} {c.get('state') or ''} · source {c.get('source_verification')}" + ("  · ARCHIVED" if c.get("archived") else ""))
        set_chip(self.stage_chip, c.get("lead_stage", "").replace("_", " "), STAGE_CHIP.get(c.get("lead_stage", ""), "neutral"))
        set_chip(self.consent_chip, f"consent {c.get('consent_status')}", {"granted": "success", "denied": "danger", "withdrawn": "danger"}.get(c.get("consent_status"), "warning"))
        self.optout_chip.setVisible(bool(c.get("opted_out")))
        self.stage_combo.setCurrentIndex(max(0, self.stage_combo.findData(c.get("lead_stage"))))
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

    def more_menu(self) -> None:
        if not self.contact:
            return
        m = QMenu(self)
        m.addAction("Check eligibility & consent", lambda: self.ctx.navigate("eligibility", contact_id=self.contact["id"]))
        m.addAction("Schedule follow-up", self.add_followup)
        m.addAction("Record consent / permission", self.add_consent)
        m.addSeparator()
        m.addAction("Unarchive" if self.contact.get("archived") else "Archive", self.toggle_archive)
        m.addAction("Opt-out (do not call)", self.opt_out)
        m.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def change_stage(self) -> None:
        if not self.contact:
            return
        stage, cid = self.stage_combo.currentData(), self.contact["id"]
        if stage == self.contact.get("lead_stage"):
            return
        self.run(lambda: self.api.patch(f"/contacts/{cid}", {"lead_stage": stage}), lambda _: (self.toast(f"Lead stage set to {stage}", "success"), self.refresh()))

    def edit_contact(self) -> None:
        if not self.contact:
            return
        dlg = ContactDialog(self, existing=self.contact)
        if dlg.exec() != ContactDialog.DialogCode.Accepted:
            return
        payload, cid = dlg.payload(), self.contact["id"]
        self.run(lambda: self.api.patch(f"/contacts/{cid}", payload), lambda _: (self.toast("Contact saved", "success"), self.refresh()))

    def toggle_archive(self) -> None:
        if not self.contact:
            return
        cid = self.contact["id"]
        if self.contact.get("archived"):
            self.run(lambda: self.api.post(f"/contacts/{cid}/unarchive"), lambda _: self.refresh())
        elif confirm(self, "Archive contact", "Archive this contact? It will never be called while archived.", "Archive"):
            self.run(lambda: self.api.delete(f"/contacts/{cid}"), lambda _: self.refresh())

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
