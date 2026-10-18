"""System Status › Workers: background schedulers (call queue, campaign engine, follow-ups, daily report) and the
AI / speech job queues. Data comes from /system/workers; nothing is estimated."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, KeyValueGrid, button, caption, confirm, fmt_dt, pretty_json

LABELS = {"call_queue": "Call queue dispatcher", "campaign_engine": "Campaign engine", "followup_scheduler": "Follow-up scheduler", "report": "Daily report"}


class WorkersScreen(BaseScreen):
    key, title = "workers", "Workers"
    subtitle = "Background workers run inside the local backend. 'Run now' executes one cycle immediately; disabling pauses the schedule until the backend restarts."

    def build(self) -> None:
        bar = QHBoxLayout()
        self.run_btn = button("Run now", "primary", self.run_now)
        self.toggle_btn = button("Disable", None, self.toggle)
        bar.addWidget(self.run_btn)
        bar.addWidget(self.toggle_btn)
        bar.addStretch(1)
        bar.addWidget(button("Reload", None, self.refresh))
        self.root.addLayout(bar)
        self.table = DataTable([("Worker", lambda r: LABELS.get(r["name"], r["name"])), ("Enabled", "enabled"), ("Runs", "runs"), ("Errors", "errors"), ("Items", "items"), ("Last run", lambda r: fmt_dt(r.get("last_run_at"), True)), ("Duration ms", "last_duration_ms"), ("Last error", "last_error"), ("Last result", lambda r: pretty_json(r.get("last_result")) if r.get("last_result") else "")])
        self.table.setObjectName("workers_table")
        self.table.itemSelectionChanged.connect(self._select)
        self.root.addWidget(self.table, 1)
        row = QHBoxLayout()
        ai = Card("AI job queue (one CPU inference at a time)")
        self.ai_grid = KeyValueGrid()
        ai.add(self.ai_grid)
        sp = Card("Speech job queue")
        self.sp_grid = KeyValueGrid()
        sp.add(self.sp_grid)
        row.addWidget(ai)
        row.addWidget(sp)
        w = QWidget()
        w.setLayout(row)
        self.root.addWidget(w)
        self.root.addWidget(caption("Running AI jobs (e.g. a streaming chat test) can be cancelled from AI Settings › diagnostics."))
        self._select()

    def refresh(self) -> None:
        self.run(lambda: self.api.get("/system/workers"), self._show)

    def _show(self, d: dict) -> None:
        rows = [{"name": k, **v} for k, v in (d.get("periodic") or {}).items()]
        sel = self.table.selected_row()
        self.table.set_rows(rows)
        if sel:
            for i, r in enumerate(self.table.rows):
                if r["name"] == sel["name"]:
                    self.table.select_data_row(i)
        for grid, key in ((self.ai_grid, "ai"), (self.sp_grid, "speech")):
            q = d.get(key) or {}
            grid.set_rows([(k.replace("_", " "), (f"{v:.0f}" if isinstance(v, float) else v)) for k, v in q.items()] or [("status", "no data")])
        self._select()

    def _select(self) -> None:
        r = self.table.selected_row()
        self.run_btn.setEnabled(r is not None)
        self.toggle_btn.setEnabled(r is not None)
        self.toggle_btn.setText("Enable" if r and not r.get("enabled", True) else "Disable")

    def run_now(self) -> None:
        r = self.table.selected_row()
        if not r:
            return
        self.run(lambda: self.api.post(f"/system/workers/{r['name']}/run", timeout=300), lambda res: (self.toast(f"{LABELS.get(r['name'], r['name'])}: {pretty_json(res.get('result'))[:150]}", "success"), self.refresh()), busy_text="Running…")

    def toggle(self) -> None:
        r = self.table.selected_row()
        if not r:
            return
        enable = not r.get("enabled", True)
        if not enable and not confirm(self, "Disable worker", f"Pause {LABELS.get(r['name'], r['name'])}? It resumes when re-enabled or when the backend restarts.", "Disable"):
            return
        self.run(lambda: self.api.request("POST", f"/system/workers/{r['name']}/enabled", params={"enabled": enable}), lambda _: self.refresh())
