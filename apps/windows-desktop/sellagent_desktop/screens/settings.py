"""Screen 20: settings & privacy controls — typed editors for every /settings key, grouped by prefix."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, button, caption, confirm, mark_invalid, pretty_json, status_label

GROUP_TITLES = {"general": "General", "privacy": "Privacy", "calling": "Calling policy & safety", "network": "Network", "ai": "Local AI", "backup": "Backup", "release_gate": "Release gate (read-only, set by audio evidence)"}
WARN_ON_ENABLE = {
    "privacy.allow_external_network": "Allowing external network lets the backend download models (Ollama/Whisper) from the internet. No contact data is ever sent, but the PC will make outbound connections. Enable?",
    "network.lan_pairing_enabled": "This opens the HTTPS/WSS pairing listener on your Wi-Fi (default port 8766). Only device endpoints are exposed, but anyone on the network can see the port. Enable?",
    "privacy.record_calls": "Recording calls has legal requirements (disclosure/consent) in India. The current routes cannot capture call audio anyway. Enable the flag?",
    "privacy.telemetry": "Telemetry is off by default; this build sends nothing. Enable the flag?",
}


class SettingsScreen(BaseScreen):
    key, title = "settings", "Settings & privacy controls"

    def build(self) -> None:
        self.editors: dict[str, QWidget] = {}
        self.values: dict[str, Any] = {}
        self.defaults: dict[str, Any] = {}
        self.read_only: set[str] = set()
        bar = QHBoxLayout()
        self.save_btn = button("Save changes", "primary", self.save)
        bar.addWidget(self.save_btn)
        bar.addWidget(button("Reload", None, self.refresh))
        bar.addWidget(button("Run retention now", None, self.run_retention, tooltip="Deletes transcripts older than privacy.transcript_retention_days"))
        self.clear_stop_btn = button("Clear emergency stop", "danger", self.clear_stop)
        bar.addWidget(self.clear_stop_btn)
        bar.addStretch(1)
        self.root.addLayout(bar)
        self.gate_lbl = status_label("")
        self.root.addWidget(self.gate_lbl)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_lay = QVBoxLayout(self.inner)
        self.scroll.setWidget(self.inner)
        self.root.addWidget(self.scroll, 1)
        self.gate_open = False

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/settings"), self.api.get("/settings/release-gate")), self._show)

    def _show(self, res: tuple) -> None:
        s, gate = res
        self.values, self.defaults, self.read_only = s.get("values", {}), s.get("defaults", {}), set(s.get("read_only", []))
        self.ctx.settings_cache.update(self.values)
        self.gate_open = bool(gate.get("allowed"))
        self.gate_lbl.setText(("Release gate OPEN: autonomous calling may be enabled." if self.gate_open else "Release gate CLOSED: calling.autonomous_enabled stays off. ") + gate.get("explanation", ""))
        self.gate_lbl.setProperty("role", "success" if self.gate_open else "warning")
        self.gate_lbl.style().unpolish(self.gate_lbl)
        self.gate_lbl.style().polish(self.gate_lbl)
        self.clear_stop_btn.setVisible(bool(self.values.get("calling.emergency_stop_active")))
        while self.inner_lay.count():
            item = self.inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.editors.clear()
        groups: dict[str, list[str]] = {}
        for k in sorted(self.defaults):
            groups.setdefault(k.split(".", 1)[0], []).append(k)
        for g, keys in groups.items():
            card = Card(GROUP_TITLES.get(g, g))
            for k in keys:
                card.add(self._editor_row(k))
            self.inner_lay.addWidget(card)
        self.inner_lay.addStretch(1)

    def _editor_row(self, key: str) -> QWidget:
        default, value = self.defaults.get(key), self.values.get(key)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        name = caption(key, wrap=False)
        name.setMinimumWidth(300)
        lay.addWidget(name)
        w: QWidget
        if key in self.read_only or default is None and not isinstance(value, bool | int | str):
            w = QLineEdit(pretty_json(value) if not isinstance(value, str) else value)
            w.setReadOnly(True)
            w.setToolTip("Set by the release gate from audio test evidence")
        elif isinstance(default, bool):
            w = QCheckBox("enabled")
            w.setChecked(bool(value))
            if key == "calling.autonomous_enabled" and not self.gate_open:
                w.setEnabled(False)
                w.setToolTip("Disabled: the release gate is closed. Real-device inbound AND outbound audio tests must PASS and be operator-confirmed first.")
            if key == "calling.emergency_stop_active":
                w.setEnabled(False)
                w.setToolTip("Use the EMERGENCY STOP button / 'Clear emergency stop'")
            if key in WARN_ON_ENABLE:
                w.clicked.connect(lambda checked, k=key, cb=w: self._warn_toggle(k, cb, checked))
        elif isinstance(default, int):
            w = QSpinBox()
            w.setRange(0, 1_000_000)
            w.setValue(int(value or 0))
        else:
            w = QLineEdit("" if value is None else str(value))
            if key.endswith(("quiet_hours_start", "quiet_hours_end")):
                w.setPlaceholderText("HH:MM")
                w.setToolTip("24-hour HH:MM in general.timezone")
            if key == "ai.llm_provider":
                w.setToolTip("ollama | llamacpp | none")
        w.setAccessibleName(key)
        lay.addWidget(w, 1)
        lay.addWidget(caption(f"default: {default}", wrap=False))
        self.editors[key] = w
        return row

    def _warn_toggle(self, key: str, cb: QCheckBox, checked: bool) -> None:
        if checked and not confirm(self, key, WARN_ON_ENABLE[key], "Enable", danger=True):
            cb.setChecked(False)

    def _current(self, key: str) -> Any:
        w = self.editors[key]
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QSpinBox):
            return w.value()
        if isinstance(w, QLineEdit):
            return w.text()
        return None

    def save(self) -> None:
        changes: dict[str, Any] = {}
        bad = False
        for k, w in self.editors.items():
            if k in self.read_only or not w.isEnabled():
                continue
            v = self._current(k)
            if k.endswith(("quiet_hours_start", "quiet_hours_end")):
                parts = str(v).split(":")
                ok = len(parts) == 2 and all(p.isdigit() for p in parts) and 0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60
                mark_invalid(w, not ok)
                bad = bad or not ok
            if k == "ai.llm_provider":
                ok = v in ("ollama", "llamacpp", "none")
                mark_invalid(w, not ok)
                bad = bad or not ok
            if v != self.values.get(k):
                changes[k] = v
        if bad:
            self.toast("Fix the highlighted fields first", "error")
            return
        if not changes:
            self.toast("Nothing changed", "info")
            return
        self.run(lambda: self.api.patch("/settings", {"values": changes}), lambda r: (self.toast(f"Saved {len(r.get('applied', {}))} setting(s)", "success"), self.refresh()))

    def run_retention(self) -> None:
        if confirm(self, "Run retention", f"Delete transcripts older than {self.values.get('privacy.transcript_retention_days')} days now? (0 = keep forever)", "Run", danger=True):
            self.run(lambda: self.api.post("/settings/retention/run"), lambda r: self.toast(f"Retention removed {r.get('transcripts_removed')} transcript rows (policy {r.get('retention_days')} days)", "success"))

    def clear_stop(self) -> None:
        if confirm(self, "Clear emergency stop", "Clearing allows new call jobs to be queued again. Cancelled jobs are not restored.", "Clear stop"):
            self.run(lambda: self.api.post("/call-jobs/emergency-stop", {"reason": "cleared by operator", "activate": False}), lambda _: (self.toast("Emergency stop cleared", "success"), self.refresh()))
