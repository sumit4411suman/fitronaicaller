"""Screen 9: call queue (jobs list, create/queue/dispatch/cancel, eligibility reasons, route capabilities)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QSplitter, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from sellagent_desktop.api_client import ApiError
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, EmptyState, FormDialog, KeyValueGrid, badge, button, caption, combo, confirm, fmt_dt, info, status_label

STATUSES = ("pending", "blocked", "queued", "dispatched", "in_progress", "completed", "failed", "cancelled")


class JobDialog(FormDialog):
    def __init__(self, parent: QWidget | None, contacts: list[dict], campaigns: list[dict], devices: list[dict], preselect: str | None):
        super().__init__(parent, "Create call job", "Create")
        self.search = QLineEdit()
        self.search.setPlaceholderText("type to filter contacts")
        self.add_field("filter", "Filter", self.search)
        self.contact_cb = QComboBox()
        self._contacts = contacts
        self._fill(contacts)
        if preselect:
            self.contact_cb.setCurrentIndex(max(0, self.contact_cb.findData(preselect)))
        self.search.textChanged.connect(lambda t: self._fill([c for c in contacts if t.lower() in f"{c['business_name']} {c['phone_e164']} {c.get('city') or ''}".lower()]))
        self.add_field("contact_id", "Contact", self.contact_cb, required=True)
        self.add_field("campaign_id", "Campaign", combo([("none (ad-hoc, uses global policy)", None)] + [(f"{c['name']} ({c['status']})", c["id"]) for c in campaigns]))
        self.add_field("mode", "Mode", combo([("campaign/default", None), ("human_assisted", "human_assisted"), ("autonomous (release gate)", "autonomous")]))
        self.add_field("route", "Route", combo([("manual — operator dials own phone", "manual"), ("android_companion — paired phone dials", "android_companion")]))
        self.add_field("device_id", "Device (android route)", combo([("auto (most recent approved)", None)] + [(f"{d['name']} · {d['model']} · {d['status']}", d["id"]) for d in devices]))

    def _fill(self, rows: list[dict]) -> None:
        self.contact_cb.clear()
        for c in rows:
            self.contact_cb.addItem(f"{c['business_name']} · {c['phone_e164']} · consent {c['consent_status']}", c["id"])

    def payload(self) -> dict:
        v = self.values()
        return {"contact_id": v["contact_id"], "campaign_id": v["campaign_id"], "mode": v["mode"], "route": v["route"], "device_id": v["device_id"]}


class CallQueueScreen(BaseScreen):
    key, title = "call_queue", "Call queue"

    def build(self) -> None:
        self.preselect: str | None = None
        bar = QHBoxLayout()
        self.status_filter = combo([("all", None)] + [(s, s) for s in STATUSES])
        self.status_filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(QLabel("Status"))
        bar.addWidget(self.status_filter)
        bar.addWidget(button("Create job", "primary", self.create_job))
        self.queue_btn = button("Queue (re-check eligibility)", None, self.queue_job)
        self.dispatch_btn = button("Dispatch", "primary", self.dispatch_job)
        self.cancel_btn = button("Cancel job", None, self.cancel_job)
        for b in (self.queue_btn, self.dispatch_btn, self.cancel_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        self.root.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.table = DataTable([("Created", lambda r: fmt_dt(r.get("created_at"))), ("Status", "status"), ("Phone", "phone_e164"), ("Mode", "mode"), ("Route", "route"), ("Attempt", "attempt"), ("Scheduled", lambda r: fmt_dt(r.get("scheduled_for"))), ("Error / note", "error")])
        self.table.setObjectName("jobs_table")
        self.table.itemSelectionChanged.connect(self._select)
        ll.addWidget(self.table, 1)
        self.empty = EmptyState("No call jobs. Create one for a contact; eligibility is checked immediately and again when queued.")
        ll.addWidget(self.empty)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        elig = Card("Eligibility result of selected job")
        self.elig_banner = status_label("")
        elig.add(self.elig_banner)
        self.reasons = QListWidget()
        self.reasons.setMaximumHeight(120)
        elig.add(self.reasons)
        self.elig_grid = KeyValueGrid()
        elig.add(self.elig_grid)
        rl.addWidget(elig)
        routes = Card("Routes and what they can PROVE")
        self.routes_box = QVBoxLayout()
        rw = QWidget()
        rw.setLayout(self.routes_box)
        routes.add(rw)
        rl.addWidget(routes)
        rl.addStretch(1)
        split.addWidget(right)
        split.setSizes([640, 460])
        self.root.addWidget(split, 1)
        self._select()

    def set_context(self, contact_id: str | None = None, **_: object) -> None:
        self.preselect = contact_id

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/call-jobs", status=self.status_filter.currentData(), limit=200), self.api.get("/call-jobs/routes")), self._show)

    def _show(self, res: tuple) -> None:
        page, routes = res
        rows = page.get("items", [])
        self.table.set_rows(rows)
        self.empty.setVisible(not rows)
        while self.routes_box.count():
            item = self.routes_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for name, cap in routes.items():
            line = QHBoxLayout()
            line.addWidget(QLabel(f"<b>{name}</b>"))
            for flag in ("can_dial", "reports_call_state", "remote_audio_capture", "audio_injection"):
                line.addWidget(badge(f"{flag}: {'yes' if cap.get(flag) else 'no'}", "pill-gold" if cap.get(flag) else "pill"))
            auto = badge("autonomous: SUPPORTED" if cap.get("autonomous_supported") else "autonomous: NOT SUPPORTED (release gate closed)", "pill-gold" if cap.get("autonomous_supported") else "badge-mock")
            line.addWidget(auto)
            line.addStretch(1)
            w = QWidget()
            w.setLayout(line)
            self.routes_box.addWidget(w)
            for n in cap.get("notes") or []:
                self.routes_box.addWidget(caption("· " + n))
        if self.preselect:
            self.create_job()
        self._select()

    def _select(self) -> None:
        row = self.table.selected_row()
        st = row.get("status") if row else None
        self.queue_btn.setEnabled(st in ("pending", "blocked"))
        self.dispatch_btn.setEnabled(st in ("pending", "queued"))
        self.cancel_btn.setEnabled(st in ("pending", "blocked", "queued", "dispatched", "in_progress"))
        if not row:
            self.elig_banner.setText("Select a job.")
            self.reasons.clear()
            self.elig_grid.set_rows([])
            return
        e = row.get("eligibility_result") or {}
        self.elig_banner.setText(("ELIGIBLE" if e.get("eligible") else "BLOCKED") + f" · checked {fmt_dt(e.get('checked_at'), True)}")
        self.elig_banner.setProperty("role", "success" if e.get("eligible") else "danger")
        self.elig_banner.style().unpolish(self.elig_banner)
        self.elig_banner.style().polish(self.elig_banner)
        self.reasons.clear()
        self.reasons.addItems([f"BLOCK: {r}" for r in e.get("reasons", [])] + [f"warn: {w}" for w in e.get("warnings", [])] or ["no reasons or warnings"])
        self.elig_grid.set_rows([("job id", row["id"]), ("contact", row["contact_id"]), ("device", row.get("device_id") or "—")] + [(k, v) for k, v in (e.get("checks") or {}).items()])

    def create_job(self) -> None:
        pre, self.preselect = self.preselect, None
        self.run(lambda: (self.api.get("/contacts", limit=500), self.api.get("/campaigns"), self.api.get("/devices")), lambda res: self._job_dialog(res, pre))

    def _job_dialog(self, res: tuple, pre: str | None) -> None:
        contacts, camps, devices = res[0].get("items", []), res[1], res[2]
        if not contacts:
            info(self, "No contacts", "Add contacts in the CRM before creating call jobs.")
            return
        dlg = JobDialog(self, contacts, camps, devices, pre)
        if dlg.exec() != JobDialog.DialogCode.Accepted:
            return
        body = dlg.payload()
        self.run(lambda: self.api.post("/call-jobs", body), lambda j: (self.toast(f"Job created with status {j['status']}" + ("" if j["status"] != "blocked" else " — see reasons"), "success" if j["status"] != "blocked" else "warning"), self.refresh()))

    def _sel(self) -> dict | None:
        row = self.table.selected_row()
        if row is None:
            self.toast("Select a job first", "warning")
        return row

    def queue_job(self) -> None:
        row = self._sel()
        if row:
            self.run(lambda: self.api.post(f"/call-jobs/{row['id']}/queue"), lambda j: (self.toast(f"Job is now {j['status']}", "success" if j["status"] == "queued" else "warning"), self.refresh()))

    def dispatch_job(self) -> None:
        row = self._sel()
        if not row:
            return
        text = "Manual route: you will dial the number on your own phone; the backend marks the job in progress and opens the live console." if row["route"] == "manual" else "Android route: a call request is sent to the paired phone, which must acknowledge within 10 s."
        if not confirm(self, "Dispatch call job", f"{text}\n\nNumber: {row['phone_e164']}", "Dispatch"):
            return

        def done(res: dict) -> None:
            self.toast(f"Dispatched: {res.get('message')} — dial {res.get('dial_number')}", "success")
            self.refresh()
            if res.get("call_id"):
                self.ctx.navigate("live_call", call_id=res["call_id"])

        def failed(exc: Exception) -> None:
            self.report_error(exc)
            self.refresh()

        self.run(lambda: self.api.post(f"/call-jobs/{row['id']}/dispatch"), done, failed)

    def cancel_job(self) -> None:
        row = self._sel()
        if row and confirm(self, "Cancel job", "Cancel this call job?", "Cancel job", danger=True):
            self.run(lambda: self.api.post(f"/call-jobs/{row['id']}/cancel", {"reason": "operator_cancel"}), lambda _: self.refresh())
