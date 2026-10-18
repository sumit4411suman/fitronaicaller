"""Screen 15: follow-up scheduler grouped by day with overdue/today colouring."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

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
        self.empty = EmptyState("No open follow-ups. Schedule one here or from a call outcome.")
        self.views = QTabWidget()
        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.addWidget(self.tree, 1)
        ll.addWidget(self.empty)
        self.views.addTab(lw, "List")
        self.views.addTab(self._build_calendar(), "Calendar")
        self.views.currentChanged.connect(lambda i: i == 1 and self.load_month())
        self.root.addWidget(self.views, 1)
        self.contacts: dict[str, dict] = {}

    # ------------------------------------------------------------------ month calendar
    def _build_calendar(self) -> QWidget:
        now = datetime.now()
        self.month = (now.year, now.month)
        w = QWidget()
        lay = QVBoxLayout(w)
        nav = QHBoxLayout()
        nav.addWidget(button("◀ Previous", None, lambda: self._shift_month(-1)))
        self.month_lbl = QLabel("")
        self.month_lbl.setObjectName("calendar_month")
        self.month_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        nav.addWidget(self.month_lbl)
        nav.addWidget(button("Next ▶", None, lambda: self._shift_month(1)))
        nav.addWidget(button("Today", None, self._this_month))
        nav.addStretch(1)
        legend = QLabel(f"<span style='color:{GOLD}'>●</span> open &nbsp;&nbsp; <span style='color:{DANGER}'>●</span> overdue &nbsp;&nbsp; ✓ done")
        legend.setProperty("role", "caption")
        nav.addWidget(legend)
        lay.addLayout(nav)
        self.cal_grid = QGridLayout()
        self.cal_grid.setSpacing(4)
        for i, d in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            h = caption(d, wrap=False)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setFixedHeight(22)
            self.cal_grid.addWidget(h, 0, i)
        self.cal_grid.setRowStretch(0, 0)
        for r in range(1, 7):
            self.cal_grid.setRowStretch(r, 1)
        self.day_buttons: list[QPushButton] = []
        gw = QWidget()
        gw.setLayout(self.cal_grid)
        lay.addWidget(gw, 3)
        self.day_title = QLabel("Click a day to see its follow-ups")
        self.day_title.setStyleSheet("font-weight: 700;")
        lay.addWidget(self.day_title)
        self.day_list = QListWidget()
        self.day_list.setObjectName("calendar_day_list")
        self.day_list.setMaximumHeight(160)
        lay.addWidget(self.day_list, 1)
        self.cal_data: dict = {}
        return w

    def _this_month(self) -> None:
        now = datetime.now()
        self.month = (now.year, now.month)
        self.load_month()

    def _shift_month(self, delta: int) -> None:
        y, m = self.month
        m += delta
        y, m = (y + (m - 1) // 12, (m - 1) % 12 + 1)
        self.month = (y, m)
        self.load_month()

    def load_month(self) -> None:
        y, m = self.month
        self.run(lambda: self.api.get("/followups/calendar", month=f"{y:04d}-{m:02d}"), self._show_month)

    def _show_month(self, cal: dict) -> None:
        import calendar as _cal

        self.cal_data = cal
        y, m = (int(x) for x in cal["month"].split("-"))
        self.month = (y, m)
        self.month_lbl.setText(f"{_cal.month_name[m]} {y}")
        for b in self.day_buttons:
            self.cal_grid.removeWidget(b)
            b.deleteLater()
        self.day_buttons = []
        first, n = int(cal.get("first_weekday", 0)), int(cal.get("days_in_month", 30))
        today = datetime.now().date().isoformat()
        for day in range(1, n + 1):
            key = f"{y:04d}-{m:02d}-{day:02d}"
            items = (cal.get("days") or {}).get(key, [])
            open_n = sum(1 for i in items if i.get("status") == "open" and not i.get("overdue"))
            over_n = sum(1 for i in items if i.get("overdue") and i.get("status") == "open")
            done_n = len(items) - open_n - over_n
            parts = []
            if open_n:
                parts.append(f"<span style='color:{GOLD}'>●</span> {open_n}")
            if over_n:
                parts.append(f"<span style='color:{DANGER}'>●</span> {over_n}")
            if done_n:
                parts.append(f"✓ {done_n}")
            b = QPushButton()
            b.setObjectName(f"day_{key}")
            b.setMinimumHeight(54)
            b.setAccessibleName(f"{key}: {len(items)} follow-up(s), {over_n} overdue")
            lbl = QLabel(f"<b>{day}</b><br>{'  '.join(parts)}")
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lbl.setStyleSheet("background: transparent;")
            bl = QVBoxLayout(b)
            bl.setContentsMargins(6, 4, 6, 4)
            bl.addWidget(lbl)
            border = DANGER if over_n else (GOLD if open_n else "#E6E2D6")
            b.setStyleSheet(f"QPushButton {{ text-align: left; border: {'2px' if key == today else '1px'} solid {border}; border-radius: 8px; background: #FFFFFF; }}")
            b.setProperty("readonly_ok", True)
            b.clicked.connect(lambda _=False, k=key: self.show_day(k))
            pos = first + day - 1
            self.cal_grid.addWidget(b, 1 + pos // 7, pos % 7)
            self.day_buttons.append(b)

    def show_day(self, key: str) -> None:
        items = (self.cal_data.get("days") or {}).get(key, [])
        self.day_title.setText(f"{key}: {len(items)} follow-up(s)")
        self.day_list.clear()
        for i in items:
            flag = "OVERDUE · " if i.get("overdue") and i.get("status") == "open" else ""
            self.day_list.addItem(f"{i.get('time', '')}  {flag}{i.get('kind')} · {i.get('status')} · {i.get('business_name')}")
        if not items:
            self.day_list.addItem("No follow-ups on this day")

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/followups", include_done=self.include_done.isChecked()), self.api.get("/contacts", limit=500)), self._show)
        if self.views.currentIndex() == 1:
            self.load_month()

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
