"""Screen 3: dashboard from /reports/dashboard (live database only)."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import BarChart, Card, DataTable, StatCard, badge, button, caption, fmt_dt


class DashboardScreen(BaseScreen):
    key, title = "dashboard", "Dashboard"

    def build(self) -> None:
        top = QHBoxLayout()
        self.source_badge = badge("live database", "pill-gold")
        self.source_badge.setToolTip("Every number is an aggregate of rows stored in the local SQLite database.")
        top.addWidget(self.source_badge)
        self.generated = caption("")
        top.addWidget(self.generated)
        top.addStretch(1)
        top.addWidget(button("Refresh", None, self.refresh))
        self.root.addLayout(top)
        grid = QGridLayout()
        self.cards = {}
        for i, (k, t) in enumerate([("contacts_total", "Active contacts"), ("calls_today", "Calls (24 h)"), ("calls_week", "Calls (7 d)"), ("connect_rate_week", "Connect rate (7 d)"), ("followups_due_24h", "Follow-ups due 24 h"), ("followups_overdue", "Follow-ups overdue")]):
            c = StatCard(t)
            self.cards[k] = c
            grid.addWidget(c, i // 3, i % 3)
        self.root.addLayout(grid)
        chart_card = Card("Calls per day (last 7 days)")
        self.chart = BarChart()
        chart_card.add(self.chart)
        self.root.addWidget(chart_card)
        row = QHBoxLayout()
        self.stage_table = DataTable([("Lead stage", "k"), ("Contacts", "v")])
        self.queue_table = DataTable([("Call job status", "k"), ("Jobs", "v")])
        self.camp_table = DataTable([("Campaign status", "k"), ("Campaigns", "v")])
        self.outcome_table = DataTable([("Outcome (7 d)", "k"), ("Calls", "v")])
        for t in (self.stage_table, self.queue_table, self.camp_table, self.outcome_table):
            t.setMaximumHeight(170)
            row.addWidget(t)
        self.root.addLayout(row)

    def refresh(self) -> None:
        self.run(lambda: self.api.get("/reports/dashboard"), self._show)

    def _show(self, d: dict) -> None:
        for k, c in self.cards.items():
            c.set_value(d.get(k))
        self.generated.setText(f"generated {fmt_dt(d.get('generated_at'), True)} · source: {d.get('data_source')}")
        self.chart.set_data([(x.get("date", ""), float(x.get("calls", 0))) for x in d.get("calls_daily", [])])
        kv = lambda m: [{"k": k, "v": v} for k, v in sorted((m or {}).items())]  # noqa: E731
        self.stage_table.set_rows(kv(d.get("contacts_by_stage")))
        self.queue_table.set_rows(kv(d.get("call_queue")))
        self.camp_table.set_rows(kv(d.get("campaigns")))
        self.outcome_table.set_rows(kv(d.get("outcomes_week")))
