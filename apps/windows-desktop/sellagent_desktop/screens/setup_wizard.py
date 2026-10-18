"""Screen 1: first-run setup wizard (QWizard) and the Setup screen that can re-run it."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget, QWizard, QWizardPage

from sellagent_desktop import paths
from sellagent_desktop.api_client import ApiClient, call_async, wait_for_idle
from sellagent_desktop.context import AppContext
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, KeyValueGrid, button, caption, error_label, fmt_bytes, mark_invalid

DEFAULT_OPERATOR = "Operator"
MIN_FREE_DISK = 2 * 1024**3
MIN_RAM = 8 * 1024**3


def needs_first_run(settings_values: dict[str, Any]) -> bool:
    return (settings_values.get("general.operator_name") in (None, "", DEFAULT_OPERATOR)) or not paths.first_run_flag().exists()


class _WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Welcome to SELL AGENT")
        lay = QVBoxLayout(self)
        lay.addWidget(caption(
            "SELL AGENT is a local, privacy-first assistant for FITRON gym-accounting sales calls.\n\n"
            "• Everything (contacts, transcripts, knowledge, models) stays on this PC in %LOCALAPPDATA%\\SellAgent.\n"
            "• No data leaves the machine unless you explicitly enable external network access for model downloads.\n"
            "• Calls are human-assisted by default: you dial and speak, SELL AGENT provides approved script lines, facts and logging.\n"
            "• Autonomous AI calling stays locked until real-device two-way audio tests pass and are confirmed by you."))
        self.ack = QCheckBox("I understand that promotional calls require consent and that I am responsible for lawful use")
        self.ack.setAccessibleName("Acknowledge responsible use")
        lay.addWidget(self.ack)
        self.registerField("ack*", self.ack)


class _SystemPage(QWizardPage):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.setTitle("System check")
        lay = QVBoxLayout(self)
        lay.addWidget(caption("Values come from the backend's /health endpoint on this PC."))
        self.grid = KeyValueGrid()
        lay.addWidget(self.grid)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.loaded = False

    def initializePage(self) -> None:  # noqa: N802
        self.note.setText("Checking…")
        call_async(lambda: self.api.get("/health"), self._show, lambda e: self.note.setText(f"Health check failed: {e}"))

    def _show(self, h: dict) -> None:
        disk = h.get("disk") or {}
        ram = h.get("ram_total")
        rows = [
            ("Backend", f"{h.get('app')} {h.get('version')} (protocol {h.get('protocol_version')})"),
            ("Database", f"revision {h.get('database', {}).get('revision')} — {'up to date' if h.get('database', {}).get('up_to_date') else 'MIGRATION NEEDED'}"),
            ("Free disk", fmt_bytes(disk.get("free"))),
            ("Total RAM", fmt_bytes(ram) if ram else "unknown (psutil not installed)"),
            ("Secret protection", h.get("secret_protection")),
            ("External network", "allowed" if h.get("external_network_allowed") else "blocked (default)"),
        ]
        self.grid.set_rows(rows)
        warnings = []
        if disk.get("free") and disk["free"] < MIN_FREE_DISK:
            warnings.append("Less than 2 GB free: local models need 1.5–3 GB each.")
        if ram and ram < MIN_RAM:
            warnings.append("Less than 8 GB RAM: a 1.7B model is the practical limit.")
        self.note.setText("\n".join(warnings) if warnings else "No blocking issues found.")
        self.note.setProperty("role", "warning" if warnings else "success")
        self.loaded = True


class _ModelsPage(QWizardPage):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.setTitle("Local AI models")
        lay = QVBoxLayout(self)
        lay.addWidget(caption("Nothing is downloaded automatically. The AI model manager screen lets you pull a model through Ollama after you explicitly enable external network access and acknowledge the download size."))
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.open_after = QCheckBox("Open the AI model manager when the wizard finishes")
        self.open_after.setChecked(True)
        lay.addWidget(self.open_after)
        self.registerField("open_models", self.open_after)

    def initializePage(self) -> None:  # noqa: N802
        self.status.setText("Checking provider…")
        call_async(lambda: self.api.get("/ai/status"), lambda s: self.status.setText(f"Provider: {s.get('provider')} — {'available' if s.get('available') else 'not available'}: {s.get('message') or ''}\nConfigured model: {s.get('configured_model')} ({'installed' if s.get('configured_model_installed') else 'not installed'})"), lambda e: self.status.setText(f"Could not query AI status: {e}"))


class _NamesPage(QWizardPage):
    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__()
        self.setTitle("Business and operator")
        form = QFormLayout(self)
        self.business = QLineEdit(str(current.get("general.business_name") or "FITRON"))
        self.business.setAccessibleName("Business name")
        self.operator = QLineEdit("" if current.get("general.operator_name") in (None, DEFAULT_OPERATOR) else str(current.get("general.operator_name")))
        self.operator.setPlaceholderText("Your name, shown in audit logs as the operator")
        self.operator.setAccessibleName("Operator name")
        self.err = error_label()
        form.addRow("Business name", self.business)
        form.addRow("Operator name", self.operator)
        form.addRow("", self.err)
        self.registerField("business_name*", self.business)
        self.registerField("operator_name*", self.operator)

    def validatePage(self) -> bool:  # noqa: N802
        ok = True
        for w in (self.business, self.operator):
            bad = len(w.text().strip()) < 2 or w.text().strip() == DEFAULT_OPERATOR
            mark_invalid(w, bad)
            ok = ok and not bad
        self.err.setVisible(not ok)
        self.err.setText("Enter at least 2 characters; the operator name must not be the default 'Operator'." if not ok else "")
        return ok


class _DonePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Ready")
        lay = QVBoxLayout(self)
        lay.addWidget(caption("Settings will be saved to the local backend when you click Finish. You can change them any time under Settings & privacy.\n\nNext steps: import contacts, record consent, create a campaign, and use the Live call console in human-assisted mode."))


class SetupWizard(QWizard):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("SELL AGENT setup")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(640, 440)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.addPage(_WelcomePage())
        self.addPage(_SystemPage(ctx.api))
        self.addPage(_ModelsPage(ctx.api))
        self.names = _NamesPage(ctx.settings_cache)
        self.addPage(self.names)
        self.addPage(_DonePage())
        self.saved_ok = False
        self.save_error: str | None = None

    def accept(self) -> None:
        values = {"general.business_name": self.names.business.text().strip(), "general.operator_name": self.names.operator.text().strip()}
        try:
            self.ctx.api.patch("/settings", {"values": values})  # wizard is modal; a short blocking call here is acceptable and keeps Finish atomic
            paths.first_run_flag().parent.mkdir(parents=True, exist_ok=True)
            paths.first_run_flag().write_text("done\n", encoding="utf-8")
            self.ctx.settings_cache.update(values)
            self.saved_ok = True
        except Exception as exc:  # noqa: BLE001
            self.save_error = str(exc)
            self.ctx.notify(f"Could not save setup: {exc}", "error")
            return
        super().accept()
        if self.field("open_models"):
            self.ctx.navigate("models")


class SetupScreen(BaseScreen):
    key, title = "setup", "Setup"
    subtitle = "First-run checklist. The wizard runs automatically until an operator name is saved."

    def build(self) -> None:
        card = Card("Status", gold=True)
        self.grid = KeyValueGrid()
        card.add(self.grid)
        self.root.addWidget(card)
        self.root.addWidget(button("Run setup wizard", "primary", self.run_wizard))
        self.root.addWidget(caption(f"Data directory: {self.ctx.data_dir}"))
        self.root.addStretch(1)

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/settings"), self.api.get("/health/ping")), self._show)

    def _show(self, res: tuple) -> None:
        settings, ping = res
        vals = settings.get("values", {})
        self.ctx.settings_cache.update(vals)
        self.grid.set_rows([
            ("Business", vals.get("general.business_name")),
            ("Operator", vals.get("general.operator_name")),
            ("First-run flag", "present" if paths.first_run_flag().exists() else "missing"),
            ("Backend", f"{ping.get('app')} {ping.get('version')} / protocol {ping.get('protocol_version')}"),
            ("Setup required", "yes" if needs_first_run(vals) else "no"),
        ])

    def run_wizard(self) -> None:
        w = SetupWizard(self.ctx, self)
        w.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        w.exec()
        wait_for_idle(3000)
        self.refresh()
