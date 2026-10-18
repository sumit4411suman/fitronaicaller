"""Screen 16: analytics & reports (dashboard aggregates, per-campaign report, CSV export of call history)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import BarChart, Card, DataTable, KeyValueGrid, badge, button, caption, fmt_dt


class AnalyticsScreen(BaseScreen):
    key, title = "analytics", "Analytics & reports"

    def build(self) -> None:
        hdr = QHBoxLayout()
        hdr.addWidget(badge("live database", "pill-gold"))
        self.gen = caption("")
        hdr.addWidget(self.gen)
        hdr.addStretch(1)
        hdr.addWidget(button("Export call history CSV…", "primary", self.export_calls))
        self.root.addLayout(hdr)
        row = QHBoxLayout()
        c1 = Card("Contacts by lead stage")
        self.stage = DataTable([("Stage", "k"), ("Contacts", "v")])
        c1.add(self.stage)
        c2 = Card("Call outcomes (last 7 days)")
        self.outcomes = DataTable([("Outcome", "k"), ("Calls", "v")])
        c2.add(self.outcomes)
        c3 = Card("Totals")
        self.totals = KeyValueGrid()
        c3.add(self.totals)
        row.addWidget(c1, 1)
        row.addWidget(c2, 1)
        row.addWidget(c3, 1)
        self.root.addLayout(row)
        chart = Card("Calls per day")
        self.chart = BarChart()
        chart.add(self.chart)
        self.root.addWidget(chart)
        camp = Card("Campaign report")
        cr = QHBoxLayout()
        cr.addWidget(QLabel("Campaign"))
        self.campaign = QComboBox()
        self.campaign.currentIndexChanged.connect(self.load_campaign)
        cr.addWidget(self.campaign, 1)
        w = QLabel()
        w.setLayout(cr)
        camp.add(w)
        cr2 = QHBoxLayout()
        self.camp_jobs = DataTable([("Job status", "k"), ("Jobs", "v")])
        self.camp_out = DataTable([("Outcome", "k"), ("Calls", "v")])
        cr2.addWidget(self.camp_jobs)
        cr2.addWidget(self.camp_out)
        w2 = QLabel()
        w2.setLayout(cr2)
        camp.add(w2)
        self.root.addWidget(camp, 1)

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/reports/dashboard"), self.api.get("/campaigns")), self._show)

    def _show(self, res: tuple) -> None:
        d, camps = res
        kv = lambda m: [{"k": k, "v": v} for k, v in sorted((m or {}).items())]  # noqa: E731
        self.stage.set_rows(kv(d.get("contacts_by_stage")))
        self.outcomes.set_rows(kv(d.get("outcomes_week")))
        rate = d.get("connect_rate_week")
        self.totals.set_rows([("contacts", d.get("contacts_total")), ("calls 24 h", d.get("calls_today")), ("calls 7 d", d.get("calls_week")), ("connect rate 7 d", f"{rate:.0%}" if isinstance(rate, int | float) else "n/a (no calls)"), ("follow-ups due 24 h", d.get("followups_due_24h")), ("follow-ups overdue", d.get("followups_overdue"))] + [(f"queue {k}", v) for k, v in (d.get("call_queue") or {}).items()])
        self.gen.setText(f"generated {fmt_dt(d.get('generated_at'), True)} · {d.get('data_source')}")
        self.chart.set_data([(x.get("date", ""), float(x.get("calls", 0))) for x in d.get("calls_daily", [])])
        cur = self.campaign.currentData()
        self.campaign.blockSignals(True)
        self.campaign.clear()
        self.campaign.addItem("— select —", None)
        for c in camps:
            self.campaign.addItem(f"{c['name']} ({c['status']})", c["id"])
        if cur:
            self.campaign.setCurrentIndex(max(0, self.campaign.findData(cur)))
        self.campaign.blockSignals(False)
        self.load_campaign()

    def load_campaign(self) -> None:
        cid = self.campaign.currentData()
        if not cid:
            self.camp_jobs.set_rows([])
            self.camp_out.set_rows([])
            return
        self.run(lambda: self.api.get(f"/reports/campaign/{cid}"), lambda r: (self.camp_jobs.set_rows([{"k": k, "v": v} for k, v in (r.get("jobs") or {}).items()]), self.camp_out.set_rows([{"k": k, "v": v} for k, v in (r.get("outcomes") or {}).items()])))

    def export_calls(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export call history", "call_history.csv", "CSV (*.csv)")
        if not path:
            return

        def fetch() -> bytes:
            rows: list[dict] = []
            offset = 0
            while True:
                page = self.api.get("/calls", limit=500, offset=offset)
                items = page.get("items", [])
                rows.extend(items)
                offset += len(items)
                if not items or offset >= page.get("total", 0):
                    break
            buf = io.StringIO()
            cols = ["id", "started_at", "connected_at", "ended_at", "business_name", "phone_e164", "conversation_state", "outcome", "outcome_detail", "duration_seconds", "language", "audio_route", "recorded", "call_job_id", "contact_id"]
            w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
            return buf.getvalue().encode("utf-8-sig")

        self.run(fetch, lambda data: (Path(path).write_bytes(data), self.toast(f"Saved {path}", "success")), busy_text="Exporting…")
