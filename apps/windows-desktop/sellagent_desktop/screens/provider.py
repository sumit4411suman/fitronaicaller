"""Telephony provider configuration & diagnostics (Exotel AgentStream / Asterisk).

Configures the production calling route: which provider, the approved caller ID (ExoPhone), the AgentStream
stream rate, and the public StreamUrl the provider connects to. API credentials are NOT entered here - they live
in the environment (EXOTEL_API_KEY / EXOTEL_API_TOKEN / EXOTEL_SID / EXOTEL_STREAM_TOKEN), so they never touch the
settings database. Enabling a provider never bypasses the release gate; a real streamed call must be verified
before autonomous calling is allowed (see docs/EXOTEL_EVALUATION.md)."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QCheckBox, QFormLayout, QHBoxLayout, QLineEdit, QSpinBox, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, button, caption, combo

CHOICES = {"provider.kind": [("Exotel AgentStream", "exotel"), ("Asterisk + AudioSocket", "asterisk")],
           "provider.sample_rate": [("8000 Hz (default)", 8000), ("16000 Hz", 16000), ("24000 Hz", 24000)]}
LABELS = {
    "provider.enabled": "Enable the telephony provider", "provider.kind": "Provider",
    "provider.caller_id": "Caller ID / ExoPhone (NOT your Jio number)", "provider.sample_rate": "AgentStream sample rate",
    "provider.stream_public_url": "Public StreamUrl (wss, via an authenticated tunnel)",
}
ORDER = ("provider.enabled", "provider.kind", "provider.caller_id", "provider.sample_rate", "provider.stream_public_url")


class ProviderScreen(BaseScreen):
    key, title = "provider", "Telephony provider"

    def build(self) -> None:
        self.values: dict[str, Any] = {}
        self.editors: dict[str, QWidget] = {}
        self.root.addWidget(caption(
            "The provider places the real cellular call and streams both sides of the live audio to Priya; all AI "
            "stays local. Credentials are set in the environment, never here. Promotional campaigns stay disabled "
            "until Indian DLT/TRAI requirements and the provider's caller-ID confirmation are in place."
        ))
        card = Card("Provider configuration")
        form = QFormLayout()
        for key in ORDER:
            if key == "provider.enabled":
                w: QWidget = QCheckBox()
            elif key in CHOICES:
                w = combo(CHOICES[key])
            else:
                w = QLineEdit()
                w.setMaxLength(300)
            w.setAccessibleName(LABELS[key])
            self.editors[key] = w
            form.addRow(LABELS[key], w)
        fw = QWidget()
        fw.setLayout(form)
        card.add(fw)
        bar = QHBoxLayout()
        self.save_btn = button("Save provider", "primary", self.save)
        self.save_btn.setProperty("perm", "settings:write")
        self.test_btn = button("Test provider readiness", None, self.test)
        bar.addWidget(self.save_btn)
        bar.addWidget(self.test_btn)
        bar.addStretch(1)
        bw = QWidget()
        bw.setLayout(bar)
        card.add(bw)
        self.status = caption("")
        card.add(self.status)
        self.root.addWidget(card)
        self.root.addStretch(1)

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/settings"), self.api.get("/call-jobs/routes")), self._show)

    def _show(self, res: tuple) -> None:
        s, routes = res
        self.values = s.get("values", {})
        for key, w in self.editors.items():
            v = self.values.get(key)
            if isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, QLineEdit):
                w.setText(str(v or ""))
            elif isinstance(w, QSpinBox):
                w.setValue(int(v or 0))
            else:
                i = w.findData(v)
                w.setCurrentIndex(max(0, i))
        self._render_status(routes)

    def _render_status(self, routes: dict) -> None:
        exo = (routes or {}).get("exotel") or {}
        notes = "; ".join(exo.get("notes", [])) or "ready"
        ready = "READY to dial" if exo.get("can_dial") else "NOT ready"
        auto = "autonomous allowed" if exo.get("autonomous_supported") else "autonomous blocked (release gate)"
        self.status.setText(f"Exotel route: {ready} · {auto}. {notes}")

    def _value(self, key: str) -> Any:
        w = self.editors[key]
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QSpinBox):
            return w.value()
        return w.currentData()

    def save(self) -> None:
        changes = {k: self._value(k) for k in self.editors if self._value(k) != self.values.get(k)}
        if not changes:
            self.toast("Nothing changed", "info")
            return
        self.run(lambda: self.api.patch("/settings", {"values": changes}), lambda r: (self.toast(f"Saved {len(r.get('applied', {}))} setting(s)", "success"), self.refresh()))

    def test(self) -> None:
        self.run(lambda: self.api.get("/call-jobs/routes"), self._render_status)
