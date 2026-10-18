"""Screen 15: follow-up scheduler grouped by day with overdue/today colouring."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import DANGER, GOLD, SUCCESS, TEXT2, WARNING, EmptyState, FormDialog, button, caption, combo, datetime_edit, fmt_dt, parse_dt


class NewFollowupDialog(FormDialog):
    def __init__(self, parent: QWidget | None, contacts: list[dict]):
        super().__init__(parent, "Schedule follow-up", "Schedule")
        self.search = QLineEdit()
        self.search.setPlaceholderText("filter contacts")
        self.add_field("filter", "Filter", self.search)
        self.cb = QComboBox()
        self._all = contacts
        self._fill(contacts)
        self.search.textChanged.connect(lambda t: self._fill([c for c in contacts if t.lower() in f"{c['business_name']} {c['phone_e164']}".lower()]))
        self.add_field("contact_id", "Contact", self.cb, required=True)
        self.add_field("due_at", "Due", datetime_edit(), required=True)
        self.add_field("kind", "Kind", combo([(k, k) for k in ("call", "demo", "email", "human_handoff")]))
        self.add_field("note", "Note", QLineEdit())

    def _fill(self, rows: list[dict]) -> None:
        self.cb.clear()
        for c in rows:
            self.cb.addItem(f"{c['business_name']} · {c['phone_e164']}", c["id"])


class FollowupsScreen(BaseScreen):
    key, title = "followups", "Follow-up scheduler"

    def build(self) -> None:
        bar = QHBoxLayout()
        self.include_done = QCheckBox("show completed / cancelled")
        self.include_done.stateChanged.connect(self.refresh)
        bar.addWidget(self.include_done)
        bar.addWidget(button("Schedule follow-up", "primary", self.create))
        bar.addWidget(button("Mark done", None, lambda: self.complete("done")))
        bar.addWidget(button("Cancel follow-up", None, lambda: self.complete("cancelled")))
        bar.addWidget(button("Open contact", None, self.open_contact))
        bar.addStretch(1)
        self.root.addLayout(bar)
        legend = QHBoxLayout()
        for text, col in (("overdue", DANGER), ("due today", WARNING), ("upcoming", GOLD), ("done", SUCCESS), ("cancelled", TEXT2)):
            lbl = caption(f"■ {text}")
            lbl.setStyleSheet(f"color: {col};")
            legend.addWidget(lbl)
        legend.addStretch(1)
        self.root.addLayout(legend)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Due", "Kind", "Status", "Contact", "Note"])
        self.tree.setAccessibleName("Follow-ups grouped by day")
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_contact())
        self.root.addWidget(self.tree, 1)
        self.empty = EmptyState("No open follow-ups. Schedule one here or from a call outcome.")
        self.root.addWidget(self.empty)
        self.contacts: dict[str, dict] = {}

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/followups", include_done=self.include_done.isChecked()), self.api.get("/contacts", limit=500)), self._show)

    def _show(self, res: tuple) -> None:
        fus, page = res
        self.contacts = {c["id"]: c for c in page.get("items", [])}
        self.tree.clear()
        self.empty.setVisible(not fus)
        now = datetime.now(UTC)
        today = now.astimezone().date()
        groups: dict[str, QTreeWidgetItem] = {}
        for f in fus:
            due = parse_dt(f.get("due_at"))
            day = due.astimezone().date().isoformat() if due else "unknown"
            if day not in groups:
                g = QTreeWidgetItem([day + (" (today)" if due and due.astimezone().date() == today else ""), "", "", "", ""])
                g.setForeground(0, QColor(GOLD))
                g.setExpanded(True)
                self.tree.addTopLevelItem(g)
                groups[day] = g
            c = self.contacts.get(f["contact_id"], {})
            it = QTreeWidgetItem([fmt_dt(f.get("due_at")), f.get("kind", ""), f.get("status", ""), f"{c.get('business_name', f['contact_id'][:8])} · {c.get('phone_e164', '')}", f.get("note") or ""])
            it.setData(0, Qt.ItemDataRole.UserRole, f)
            if f.get("status") == "done":
                col = SUCCESS
            elif f.get("status") == "cancelled":
                col = TEXT2
            elif due and due < now:
                col = DANGER
            elif due and due.astimezone().date() == today:
                col = WARNING
            else:
                col = GOLD
            for i in range(5):
                it.setForeground(i, QColor(col))
            groups[day].addChild(it)
        for i in range(5):
            self.tree.resizeColumnToContents(i)

    def _sel(self) -> dict | None:
        it = self.tree.currentItem()
        f = it.data(0, Qt.ItemDataRole.UserRole) if it else None
        if not f:
            self.toast("Select a follow-up row", "warning")
        return f

    def create(self) -> None:
        contacts = list(self.contacts.values())
        if not contacts:
            self.toast("No contacts in the CRM yet", "warning")
            return
        dlg = NewFollowupDialog(self, contacts)
        if dlg.exec() == NewFollowupDialog.DialogCode.Accepted:
            v = dlg.values()
            body = {"contact_id": v["contact_id"], "due_at": v["due_at"], "kind": v["kind"], "note": v["note"] or None}
            self.run(lambda: self.api.post("/followups", body), lambda _: (self.toast("Follow-up scheduled", "success"), self.refresh()))

    def complete(self, status: str) -> None:
        f = self._sel()
        if not f:
            return
        if f.get("status") != "open":
            self.toast("Already closed", "warning")
            return
        self.run(lambda: self.api.post(f"/followups/{f['id']}/complete", params={"status": status}), lambda _: self.refresh())

    def open_contact(self) -> None:
        f = self._sel()
        if f:
            self.ctx.navigate("contact_detail", contact_id=f["contact_id"])
