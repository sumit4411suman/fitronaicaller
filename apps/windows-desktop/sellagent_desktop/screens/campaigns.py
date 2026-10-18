"""Screen 7: campaign management (list, create/edit, status transitions, membership, stats)."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QSpinBox, QSplitter, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, EmptyState, FormDialog, KeyValueGrid, button, caption, combo, confirm, fmt_dt, status_label

TRANSITIONS = {"draft": ["authorized", "archived"], "authorized": ["active", "draft", "archived"], "active": ["paused", "completed"], "paused": ["active", "completed", "archived"], "completed": ["archived"], "archived": []}


class CampaignDialog(FormDialog):
    def __init__(self, parent: QWidget | None, existing: dict | None = None, gate_open: bool = False):
        super().__init__(parent, "Edit campaign" if existing else "New campaign")
        e = existing or {}
        self.add_field("name", "Name", QLineEdit(e.get("name", "")), required=True)
        d = QPlainTextEdit(e.get("description") or "")
        d.setMaximumHeight(70)
        self.add_field("description", "Description", d)
        mode = combo([("human_assisted (operator speaks)", "human_assisted"), ("autonomous (locked by release gate)", "autonomous")], e.get("calling_mode", "human_assisted"))
        if not gate_open:
            mode.model().item(1).setEnabled(False)
            mode.setToolTip("Autonomous campaigns cannot be authorized until real-device two-way audio evidence opens the release gate.")
        self.add_field("calling_mode", "Calling mode", mode)
        self.add_field("language", "Language", combo([("auto", "auto"), ("Hindi", "hi"), ("English", "en")], e.get("language", "auto")))
        mcd = QSpinBox()
        mcd.setRange(1, 500)
        mcd.setValue(int(e.get("max_calls_per_day", 50)))
        self.add_field("max_calls_per_day", "Max calls per day", mcd)
        mac = QSpinBox()
        mac.setRange(1, 10)
        mac.setValue(int(e.get("max_attempts_per_contact", 3)))
        self.add_field("max_attempts_per_contact", "Max attempts per contact", mac)
        self.add_field("quiet_hours_start", "Quiet hours start (HH:MM, optional)", QLineEdit(e.get("quiet_hours_start") or ""))
        self.add_field("quiet_hours_end", "Quiet hours end (HH:MM, optional)", QLineEdit(e.get("quiet_hours_end") or ""))
        rc = QCheckBox("Only call contacts with recorded consent")
        rc.setChecked(bool(e.get("requires_consent", True)))
        self.add_field("requires_consent", "Consent", rc)

    def validate(self) -> bool:
        ok = super().validate()
        for k in ("quiet_hours_start", "quiet_hours_end"):
            v = self.raw_value(k)
            if v:
                parts = v.split(":")
                if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60):
                    self.set_field_error(k, "Use HH:MM (24 h)")
                    ok = False
        return ok

    def payload(self) -> dict:
        v = self.values()
        for k in ("description", "quiet_hours_start", "quiet_hours_end"):
            v[k] = v[k] or None
        return v


class AddContactsDialog(QDialog):
    def __init__(self, parent: QWidget | None, contacts: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Add contacts to campaign")
        self.setMinimumSize(560, 460)
        lay = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name / phone / city")
        self.filter.textChanged.connect(self._filter)
        lay.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for c in contacts:
            it = QListWidgetItem(f"{c['business_name']} · {c['phone_e164']} · {c.get('city') or ''} · consent {c['consent_status']}" + (" · OPTED OUT" if c.get("opted_out") else ""))
            it.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        lay.addWidget(caption("Opted-out or archived contacts are added as 'excluded' and never queued."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setProperty("role", "primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _filter(self, text: str) -> None:
        t = text.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(t not in it.text().lower())

    def ids(self) -> list[str]:
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.list.selectedItems()]


class CampaignsScreen(BaseScreen):
    key, title = "campaigns", "Campaigns"

    def build(self) -> None:
        self.gate_open = False
        bar = QHBoxLayout()
        self.status_filter = combo([("all statuses", None)] + [(s, s) for s in TRANSITIONS])
        self.status_filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.status_filter)
        bar.addWidget(button("New campaign", "primary", self.new_campaign))
        bar.addStretch(1)
        self.root.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.table = DataTable([("Name", "name"), ("Status", "status"), ("Mode", "calling_mode"), ("Lang", "language"), ("Consent req.", "requires_consent"), ("Max/day", "max_calls_per_day"), ("Updated", lambda r: fmt_dt(r.get("updated_at")))])
        self.table.setObjectName("campaigns_table")
        self.table.itemSelectionChanged.connect(self._select)
        ll.addWidget(self.table, 1)
        self.empty = EmptyState("No campaigns yet. A campaign groups contacts, holds the calling policy and must be authorized before jobs can run.")
        ll.addWidget(self.empty)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.detail = Card("Selected campaign", gold=True)
        self.detail_grid = KeyValueGrid()
        self.detail.add(self.detail_grid)
        self.trans_row = QHBoxLayout()
        tw = QWidget()
        tw.setLayout(self.trans_row)
        self.detail.add(tw)
        act = QHBoxLayout()
        self.edit_btn = button("Edit", None, self.edit_campaign)
        self.add_btn = button("Add contacts from CRM…", None, self.add_contacts)
        act.addWidget(self.edit_btn)
        act.addWidget(self.add_btn)
        act.addStretch(1)
        aw = QWidget()
        aw.setLayout(act)
        self.detail.add(aw)
        self.gate_note = status_label("")
        self.detail.add(self.gate_note)
        rl.addWidget(self.detail)
        stats = Card("Membership & outcomes")
        self.stats_grid = KeyValueGrid()
        stats.add(self.stats_grid)
        rl.addWidget(stats)
        self.members = DataTable([("Business", lambda r: r["contact"]["business_name"]), ("Phone", lambda r: r["contact"]["phone_e164"]), ("Membership", lambda r: r["membership"]["status"]), ("Attempts", lambda r: r["membership"]["attempts"]), ("Last outcome", lambda r: r["membership"]["last_outcome"]), ("Eligible (snapshot)", lambda r: (r["membership"].get("eligibility_snapshot") or {}).get("eligible"))])
        rl.addWidget(self.members, 1)
        split.addWidget(right)
        split.setSizes([520, 560])
        self.root.addWidget(split, 1)
        self.current: dict | None = None
        self._select()

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/campaigns", status=self.status_filter.currentData()), self.api.get("/settings/release-gate")), self._show)

    def _show(self, res: tuple) -> None:
        camps, gate = res
        self.gate_open = bool(gate.get("allowed"))
        self.table.set_rows(camps)
        self.empty.setVisible(not camps)
        if self.current:
            for i, c in enumerate(camps):
                if c["id"] == self.current["id"]:
                    self.table.selectRow(i)
                    break
        self._select()

    def _select(self) -> None:
        row = self.table.selected_row()
        self.current = row
        while self.trans_row.count():
            item = self.trans_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for b in (self.edit_btn, self.add_btn):
            b.setEnabled(row is not None)
        if not row:
            self.detail_grid.set_rows([("", "Select a campaign")])
            self.stats_grid.set_rows([])
            self.members.set_rows([])
            self.gate_note.setText("")
            return
        self.detail_grid.set_rows([(k.replace("_", " "), fmt_dt(row.get(k)) if k.endswith("_at") else row.get(k)) for k in ("id", "name", "description", "status", "calling_mode", "language", "requires_consent", "max_calls_per_day", "max_attempts_per_contact", "quiet_hours_start", "quiet_hours_end", "authorized_by", "authorized_at", "starts_at", "ends_at", "created_at")])
        for target in TRANSITIONS.get(row["status"], []):
            b = button(f"→ {target}", "primary" if target in ("authorized", "active") else None, lambda _=False, t=target: self.transition(t))
            self.trans_row.addWidget(b)
        self.trans_row.addStretch(1)
        self.gate_note.setText("Autonomous mode: release gate CLOSED — this campaign cannot be authorized." if row["calling_mode"] == "autonomous" and not self.gate_open else "")
        self.gate_note.setProperty("role", "danger")
        cid = row["id"]
        self.run(lambda: (self.api.get(f"/campaigns/{cid}/stats"), self.api.get(f"/campaigns/{cid}/contacts")), self._show_stats)

    def _show_stats(self, res: tuple) -> None:
        st, members = res
        rows = [(k, st.get(k)) for k in ("total", "pending", "queued", "called", "done", "excluded")]
        rows += [(f"jobs {k}", v) for k, v in (st.get("jobs") or {}).items()]
        rows += [(f"outcome {k}", v) for k, v in (st.get("outcomes") or {}).items()]
        self.stats_grid.set_rows(rows)
        self.members.set_rows(members)

    def new_campaign(self) -> None:
        dlg = CampaignDialog(self, gate_open=self.gate_open)
        if dlg.exec() == CampaignDialog.DialogCode.Accepted:
            body = dlg.payload()
            self.run(lambda: self.api.post("/campaigns", body), lambda c: (self.toast(f"Campaign '{c['name']}' created", "success"), self.refresh()))

    def edit_campaign(self) -> None:
        if not self.current:
            return
        dlg = CampaignDialog(self, existing=self.current, gate_open=self.gate_open)
        if dlg.exec() == CampaignDialog.DialogCode.Accepted:
            body, cid = dlg.payload(), self.current["id"]
            if self.current["status"] == "authorized" and not confirm(self, "Edit authorized campaign", "Editing resets the campaign to draft; you will need to authorize it again.", "Edit anyway"):
                return
            self.run(lambda: self.api.patch(f"/campaigns/{cid}", body), lambda _: (self.toast("Campaign saved", "success"), self.refresh()))

    def transition(self, target: str) -> None:
        if not self.current:
            return
        cid = self.current["id"]
        msg = {"authorized": "Authorizing records you as the person approving these promotional calls.", "active": "Activating allows call jobs for this campaign to be queued and dispatched.", "archived": "Archived campaigns cannot be reopened."}.get(target)
        if msg and not confirm(self, f"Move to {target}", msg, target.capitalize()):
            return
        self.run(lambda: self.api.post(f"/campaigns/{cid}/transition", {"status": target}), lambda _: (self.toast(f"Campaign is now {target}", "success"), self.refresh()))

    def add_contacts(self) -> None:
        if not self.current:
            return
        cid = self.current["id"]
        self.run(lambda: self.api.get("/contacts", limit=500, archived=False), lambda page: self._pick_contacts(cid, page.get("items", [])))

    def _pick_contacts(self, cid: str, contacts: list[dict]) -> None:
        if not contacts:
            self.toast("No contacts in the CRM yet", "warning")
            return
        dlg = AddContactsDialog(self, contacts)
        if dlg.exec() != AddContactsDialog.DialogCode.Accepted or not dlg.ids():
            return
        ids = dlg.ids()
        self.run(lambda: self.api.post(f"/campaigns/{cid}/contacts", {"ids": ids}), lambda r: (self.toast(f"Added {r.get('added')}, skipped {r.get('skipped')}, excluded {r.get('excluded')}", "success"), self._select()))
