"""Screen 11: call history & outcomes with a detail dialog (events, transcript, notes)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QTabWidget, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import DataTable, EmptyState, KeyValueGrid, button, fmt_dt, pretty_json

PAGE = 100


class CallDetailDialog(QDialog):
    def __init__(self, parent: QWidget | None, d: dict):
        super().__init__(parent)
        c = d["call"]
        self.setWindowTitle(f"Call {c['id'][:8]} — {(d.get('contact') or {}).get('business_name', '')}")
        self.setMinimumSize(760, 520)
        lay = QVBoxLayout(self)
        grid = KeyValueGrid()
        grid.set_rows([(k, fmt_dt(c.get(k), True) if k.endswith("_at") else c.get(k)) for k in ("id", "conversation_state", "outcome", "outcome_detail", "language", "started_at", "connected_at", "ended_at", "duration_seconds", "audio_route", "recorded")] + [("job", f"{(d.get('job') or {}).get('status')} · {(d.get('job') or {}).get('route')} · {(d.get('job') or {}).get('mode')}")])
        lay.addWidget(grid)
        tabs = QTabWidget()
        tr = QListWidget()
        for t in d.get("transcript", []):
            tr.addItem(f"#{t['seq']} {t['speaker']} ({t.get('source')}, {t.get('language') or '-'}): {t['text']}" + (f"  refs={t['knowledge_refs']}" if t.get("knowledge_refs") else ""))
        tabs.addTab(tr, f"Transcript ({len(d.get('transcript', []))})")
        ev = DataTable([("Time", lambda r: fmt_dt(r.get("occurred_at"), True)), ("Event", "event_type"), ("From", "from_state"), ("To", "to_state"), ("Source", "source"), ("Data", lambda r: pretty_json(r.get("data")) if r.get("data") else "")])
        ev.set_rows(d.get("events", []))
        tabs.addTab(ev, f"Events ({len(d.get('events', []))})")
        notes = QListWidget()
        for n in d.get("notes", []):
            notes.addItem(f"{fmt_dt(n.get('created_at'), True)} {n.get('author')}: {n['body']}")
        tabs.addTab(notes, f"Notes ({len(d.get('notes', []))})")
        lay.addWidget(tabs, 1)
        lay.addWidget(button("Close", None, self.accept))


class CallHistoryScreen(BaseScreen):
    key, title = "call_history", "Call history & outcomes"

    def build(self) -> None:
        self.offset, self.total = 0, 0
        self.contact_filter: str | None = None
        self.open_call_id: str | None = None
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Outcome"))
        self.outcome = QComboBox()
        self.outcome.addItem("all", None)
        self.outcome.currentIndexChanged.connect(lambda: self.load(0))
        bar.addWidget(self.outcome)
        self.contact_lbl = QLabel("")
        bar.addWidget(self.contact_lbl)
        self.clear_btn = button("Clear contact filter", None, self._clear_contact)
        self.clear_btn.setVisible(False)
        bar.addWidget(self.clear_btn)
        bar.addStretch(1)
        bar.addWidget(button("Open detail", "primary", self.open_detail))
        bar.addWidget(button("Open in live console", None, lambda: self._with_sel(lambda r: self.ctx.navigate("live_call", call_id=r["id"]))))
        self.root.addLayout(bar)
        self.table = DataTable([("Started", lambda r: fmt_dt(r.get("started_at"))), ("Business", "business_name"), ("Phone", "phone_e164"), ("State", "conversation_state"), ("Outcome", "outcome"), ("Detail", "outcome_detail"), ("Duration s", "duration_seconds"), ("Language", "language"), ("Route", "audio_route")])
        self.table.itemDoubleClicked.connect(lambda *_: self.open_detail())
        self.root.addWidget(self.table, 1)
        self.empty = EmptyState("No calls recorded yet. Calls appear here once a job is dispatched.")
        self.root.addWidget(self.empty)
        pager = QHBoxLayout()
        self.prev_btn = button("◀ Previous", None, lambda: self.load(self.offset - PAGE))
        self.next_btn = button("Next ▶", None, lambda: self.load(self.offset + PAGE))
        self.page_lbl = QLabel("")
        pager.addWidget(self.prev_btn)
        pager.addWidget(self.page_lbl)
        pager.addWidget(self.next_btn)
        pager.addStretch(1)
        self.root.addLayout(pager)

    def set_context(self, contact_id: str | None = None, call_id: str | None = None, **_: object) -> None:
        if contact_id:
            self.contact_filter = contact_id
        if call_id:
            self.open_call_id = call_id

    def _clear_contact(self) -> None:
        self.contact_filter = None
        self.load(0)

    def refresh(self) -> None:
        self.run(lambda: self.api.get("/calls/outcomes"), self._outcomes)

    def _outcomes(self, o: dict) -> None:
        cur = self.outcome.currentData()
        self.outcome.blockSignals(True)
        self.outcome.clear()
        self.outcome.addItem("all", None)
        for x in o.get("outcomes", []):
            self.outcome.addItem(x, x)
        if cur:
            self.outcome.setCurrentIndex(max(0, self.outcome.findData(cur)))
        self.outcome.blockSignals(False)
        self.load(self.offset)

    def load(self, offset: int) -> None:
        offset = max(0, offset)
        params = dict(outcome=self.outcome.currentData(), contact_id=self.contact_filter, limit=PAGE, offset=offset)
        self.run(lambda: self.api.get("/calls", **params), lambda p: self._show(p, offset))

    def _show(self, page: dict, offset: int) -> None:
        rows = page.get("items", [])
        self.offset, self.total = offset, int(page.get("total", 0))
        self.table.set_rows(rows)
        self.empty.setVisible(not rows)
        self.page_lbl.setText(f"{offset + 1 if rows else 0}–{offset + len(rows)} of {self.total}")
        self.prev_btn.setEnabled(offset > 0)
        self.next_btn.setEnabled(offset + PAGE < self.total)
        self.contact_lbl.setText(f"contact filter: {self.contact_filter[:8]}…" if self.contact_filter else "")
        self.clear_btn.setVisible(bool(self.contact_filter))
        if self.open_call_id:
            cid, self.open_call_id = self.open_call_id, None
            self.run(lambda: self.api.get(f"/calls/{cid}"), lambda d: CallDetailDialog(self, d).exec())

    def _with_sel(self, fn) -> None:
        row = self.table.selected_row()
        if not row:
            self.toast("Select a call first", "warning")
            return
        fn(row)

    def open_detail(self) -> None:
        self._with_sel(lambda r: self.run(lambda: self.api.get(f"/calls/{r['id']}"), lambda d: CallDetailDialog(self, d).exec()))
