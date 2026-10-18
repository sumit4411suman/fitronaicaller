"""Screen 18: audio feasibility test console (18-step plan, live device results, operator confirmation, release gate)."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, FormDialog, KeyValueGrid, button, caption, combo, confirm, fmt_dt, status_label


class RecordDialog(FormDialog):
    def __init__(self, parent: QWidget | None, steps: list[dict], devices: list[dict], preselect: str | None):
        super().__init__(parent, "Record a manually observed test result", "Record")
        self.add_field("test_id", "Test session id", QLineEdit("manual-session"), required=True, help_text="Group several steps under one id, e.g. s25-jio-2026-10-18")
        self.add_field("step", "Step", combo([(f"{s['step']} — {s['title']}", s["step"]) for s in steps], preselect), required=True)
        self.add_field("direction", "Direction", combo([(d, d) for d in ("none", "inbound", "outbound", "both")]))
        self.add_field("status", "Observed status", combo([(s, s) for s in ("pass", "fail", "blocked", "not_tested")]), required=True)
        self.add_field("kind", "Kind", combo([("real_device — real phone + SIM, observed by you", "real_device"), ("simulated — emulator/fake; never counts for the gate", "simulated")]), required=True)
        self.add_field("device_id", "Device", combo([("none", None)] + [(f"{d['name']} ({d['model']})", d["id"]) for d in devices]))
        self.add_field("route", "Audio route", combo([("unknown", None)] + [(r, r) for r in ("earpiece", "speaker", "bluetooth", "wired_headset")]))
        self.add_field("api_used", "Android API used", QLineEdit(), help_text="e.g. InCallService + AudioRecord VOICE_CALL (blocked), AudioManager.setMode")
        self.add_field("phone_model", "Phone model", QLineEdit("Samsung Galaxy S25"))
        self.add_field("android_version", "Android version", QLineEdit())
        self.add_field("app_version", "App version", QLineEdit())
        self.add_field("network_config", "Network (SIM / VoWiFi)", QLineEdit("Jio"))
        for k, label in (("steps_performed", "Steps performed"), ("expected", "Expected"), ("actual", "Actual"), ("error_message", "Error message")):
            t = QPlainTextEdit()
            t.setMaximumHeight(60)
            self.add_field(k, label, t)
        self.conf = QCheckBox("I personally observed this on the real device")
        self.add_field("operator_confirmed", "Confirmation", self.conf)

    def validate(self) -> bool:
        ok = super().validate()
        if self.raw_value("kind") == "simulated" and self.raw_value("operator_confirmed"):
            self.set_field_error("operator_confirmed", "Simulated results cannot be operator-confirmed")
            ok = False
        return ok

    def payload(self) -> dict:
        v = self.values()
        for k in ("api_used", "phone_model", "android_version", "app_version", "network_config", "steps_performed", "expected", "actual", "error_message"):
            v[k] = v[k] or None
        return v


class AudioTestsScreen(BaseScreen):
    key, title = "audio_tests", "Audio feasibility test console"
    scrollable = True

    def build(self) -> None:
        self.plan: list[dict] = []
        self.rows_by_step: dict[str, dict] = {}
        self.devices: list[dict] = []
        hdr = QHBoxLayout()
        hdr.addWidget(caption("A step counts only when observed on the real Galaxy S25 + Jio SIM AND confirmed by you here. Simulated rows are badged and never open the gate."))
        hdr.addStretch(1)
        hdr.addWidget(button("Record manual result…", "primary", self.record))
        self.confirm_btn = button("Confirm selected row", None, self.confirm_row)
        hdr.addWidget(self.confirm_btn)
        self.unconfirm_btn = button("Withdraw confirmation", None, lambda: self.confirm_row(False))
        hdr.addWidget(self.unconfirm_btn)
        hdr.addWidget(button("Recompute gate", None, self.recompute))
        self.root.addLayout(hdr)
        gate = Card("Release gate (autonomous calling)", gold=True)
        self.gate_lbl = status_label("")
        self.gate_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        gate.add(self.gate_lbl)
        self.gate_grid = KeyValueGrid()
        gate.add(self.gate_grid)
        self.gate_expl = caption("")
        gate.add(self.gate_expl)
        self.root.addWidget(gate)
        self.rule = caption("")
        self.root.addWidget(self.rule)
        self.table = DataTable([("#", "n"), ("Step", "step"), ("Title", "title"), ("Direction", "direction"), ("Latest status", lambda r: (r.get("latest") or {}).get("status")), ("Kind", lambda r: ((r.get("latest") or {}).get("kind") or "") + (" [SIMULATED]" if (r.get("latest") or {}).get("kind") == "simulated" else "")), ("Confirmed", lambda r: (r.get("latest") or {}).get("confirmed")), ("Date", lambda r: fmt_dt((r.get("latest") or {}).get("date"))), ("Phone / Android", lambda r: f"{(r.get('latest') or {}).get('phone') or ''} {(r.get('latest') or {}).get('android') or ''}"), ("Error", lambda r: (r.get("latest") or {}).get("error"))])
        self.table.setObjectName("audio_tests_table")
        self.table.itemSelectionChanged.connect(self._select)
        self.root.addWidget(self.table, 1)
        self.history = DataTable([("Recorded", lambda r: fmt_dt(r.get("created_at"), True)), ("Test id", "test_id"), ("Step", "step"), ("Dir", "direction"), ("Status", "status"), ("Kind", lambda r: r.get("kind") + (" [SIMULATED]" if r.get("kind") == "simulated" else "")), ("Confirmed", "operator_confirmed"), ("Route", "route"), ("API", "api_used"), ("Error", "error_message")])
        self.history.setMaximumHeight(170)
        self.root.addWidget(self.history)
        self.live_lbl = caption("Live results from the diagnostic APK appear here automatically (audio_test.result over the desktop WebSocket).")
        self.root.addWidget(self.live_lbl)
        self._select()

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/audio-tests/plan"), self.api.get("/audio-tests/report"), self.api.get("/audio-tests"), self.api.get("/settings/release-gate"), self.api.get("/devices")), self._show)

    def _show(self, res: tuple) -> None:
        plan, report, rows, gate, devices = res
        self.plan = plan.get("steps", [])
        self.devices = devices
        self.rule.setText(plan.get("rule", ""))
        self.rows_by_step = {}
        for r in rows:  # ordered newest first
            self.rows_by_step.setdefault(r["step"], r)
        self.table.set_rows([{"n": i + 1, **s} for i, s in enumerate(report.get("steps", []))])
        self.history.set_rows(rows)
        allowed = gate.get("allowed")
        self.gate_lbl.setText("GATE OPEN — autonomous calling may be enabled in Settings" if allowed else "GATE CLOSED — autonomous calling locked")
        self.gate_lbl.setProperty("role", "success" if allowed else "danger")
        self.gate_lbl.style().unpolish(self.gate_lbl)
        self.gate_lbl.style().polish(self.gate_lbl)
        ev = gate.get("evidence") or {}
        self.gate_grid.set_rows([("remote audio capture (inbound) verified", gate.get("remote_audio_capture_verified")), ("AI speech transmission (outbound) verified", gate.get("audio_injection_verified")), ("evidence inbound", ", ".join(ev.get("inbound") or []) or "none"), ("evidence outbound", ", ".join(ev.get("outbound") or []) or "none"), ("setting release_gate.autonomous_calling_allowed", gate.get("setting")), ("calling.autonomous_enabled", gate.get("autonomous_enabled"))])
        self.gate_expl.setText(gate.get("explanation", ""))
        self._select()

    def _select(self) -> None:
        row = self.table.selected_row()
        latest = self.rows_by_step.get(row["step"]) if row else None
        can = bool(latest) and latest.get("kind") == "real_device"
        self.confirm_btn.setEnabled(can and not latest.get("operator_confirmed"))
        self.unconfirm_btn.setEnabled(can and bool(latest.get("operator_confirmed")))
        self.confirm_btn.setToolTip("Only real-device rows can be confirmed" if latest and latest.get("kind") != "real_device" else "")

    def record(self) -> None:
        row = self.table.selected_row()
        dlg = RecordDialog(self, self.plan, self.devices, row["step"] if row else None)
        if dlg.exec() == RecordDialog.DialogCode.Accepted:
            body = dlg.payload()
            self.run(lambda: self.api.post("/audio-tests", body), lambda r: (self.toast(f"Recorded {r['step']} = {r['status']} ({r['kind']})", "success"), self.refresh()))

    def confirm_row(self, confirmed: bool = True) -> None:
        row = self.table.selected_row()
        latest = self.rows_by_step.get(row["step"]) if row else None
        if not latest:
            self.toast("Select a step that has a recorded result", "warning")
            return
        if confirmed and not confirm(self, "Confirm real-device result", f"Confirm that you personally observed '{latest['step']}' = {latest['status'].upper()} on {latest.get('phone_model') or 'the real device'}? Only step 4 (remote speech capture, with the phone's probe evidence) and step 5 (generated speech transmission) can open the autonomous release gate.", "Confirm", danger=True):
            return
        self.run(lambda: self.api.post(f"/audio-tests/{latest['id']}/confirm", params={"confirmed": confirmed}), lambda _: (self.toast("Confirmation saved; gate recomputed", "success"), self.refresh()))

    def recompute(self) -> None:
        self.run(lambda: self.api.post("/settings/release-gate/recompute"), lambda g: (self.toast(f"Gate {'OPEN' if g.get('allowed') else 'closed'}", "info"), self.refresh()))

    def on_ws_event(self, env: dict) -> None:
        if env.get("type") in ("audio_test.result", "audio_test.event"):
            p = env.get("payload") or {}
            self.live_lbl.setText(f"Live: {env.get('type')} step={p.get('step')} status={p.get('status', p.get('message'))} at {fmt_dt(p.get('occurred_at'), True)}")
            if env.get("type") == "audio_test.result":
                self.refresh()
