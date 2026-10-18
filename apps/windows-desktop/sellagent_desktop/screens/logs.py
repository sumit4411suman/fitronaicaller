"""Screen 22: logs, health & version (health JSON, backend log tail, versions, data folder, audit viewer)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from sellagent_desktop import APP_VERSION
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import DataTable, EmptyState, KeyValueGrid, button, caption, chip, combo, fmt_dt, pretty_json, set_chip


def tail(path: Path, lines: int = 300) -> str:
    if not path.exists():
        return f"(no log file at {path})"
    try:
        data = path.read_bytes()[-400_000:]
    except OSError as exc:
        return f"(cannot read {path}: {exc})"
    text = data.decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


class LogsScreen(BaseScreen):
    key, title = "logs", "Logs, health & version"

    def build(self) -> None:
        self.db_chip = chip("Database: checking", "neutral")
        self.db_chip.setObjectName("db_encryption_chip")
        self.root.addWidget(self.db_chip)
        top = QHBoxLayout()
        self.versions = KeyValueGrid()
        top.addWidget(self.versions, 1)
        col = QVBoxLayout()
        col.addWidget(button("Open data folder", "primary", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.data_dir)))))
        col.addWidget(button("Reload", None, self.refresh))
        col.addStretch(1)
        top.addLayout(col)
        self.root.addLayout(top)
        self.tabs = QTabWidget()
        self.health = QPlainTextEdit()
        self.health.setReadOnly(True)
        self.tabs.addTab(self.health, "/health")
        logw = QWidget()
        ll = QVBoxLayout(logw)
        self.log_path_lbl = caption("")
        ll.addWidget(self.log_path_lbl)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        ll.addWidget(self.log_view, 1)
        self.tabs.addTab(logw, "backend.log (tail)")
        aud = QWidget()
        al = QVBoxLayout(aud)
        ar = QHBoxLayout()
        self.action = QLineEdit()
        self.action.setPlaceholderText("action prefix, e.g. call_job. / settings. / pairing.")
        self.action.returnPressed.connect(self.load_audit)
        ar.addWidget(self.action, 1)
        self.severity = combo([("any severity", None), ("info", "info"), ("warning", "warning"), ("critical", "critical")])
        self.severity.currentIndexChanged.connect(self.load_audit)
        ar.addWidget(self.severity)
        ar.addWidget(button("Filter", None, self.load_audit))
        al.addLayout(ar)
        self.audit = DataTable([("Time", lambda r: fmt_dt(r.get("occurred_at"), True)), ("Severity", "severity"), ("Actor", "actor"), ("Action", "action"), ("Entity", lambda r: f"{r.get('entity_type') or ''} {r.get('entity_id') or ''}".strip()), ("Request", "request_id"), ("Data", lambda r: pretty_json(r.get("data")) if r.get("data") else "")])
        al.addWidget(self.audit, 1)
        self.audit_empty = EmptyState("No audit events match.")
        al.addWidget(self.audit_empty)
        self.tabs.addTab(aud, "Audit log")
        self.root.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        log_path = self.ctx.data_dir / "logs" / "backend.log"
        self.run(lambda: (self.api.get("/health"), self.api.get("/health/ping"), tail(log_path)), lambda res: self._show(res, log_path))
        self.load_audit()

    def _show(self, res: tuple, log_path: Path) -> None:
        h, ping, log_text = res
        self.health.setPlainText(pretty_json(h))
        self.log_path_lbl.setText(str(log_path))
        self.log_view.setPlainText(log_text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        self.ctx.health_cache.update(h)
        db = h.get("database") or {}
        if db.get("encrypted"):
            set_chip(self.db_chip, "Database: encrypted (AES-256)", "success")
        else:
            set_chip(self.db_chip, f"Database: NOT encrypted — {db.get('encryption') or 'encryption unavailable'}", "warning")
        self.db_chip.setToolTip(str(db.get("encryption")))
        self.versions.set_rows([
            ("Desktop app", APP_VERSION), ("Backend", f"{ping.get('app')} {ping.get('version')}"), ("Protocol", ping.get("protocol_version")), ("Backend URL", self.ctx.backend_url),
            ("Backend process", "started by this app" if self.ctx.backend_owned else "external (SELLAGENT_BACKEND_URL)"), ("Python (backend)", h.get("python")), ("Platform", h.get("platform")),
            ("Database", f"{db.get('path')} · rev {db.get('revision')} ({'up to date' if db.get('up_to_date') else 'MIGRATE'}) · {db.get('journal_mode')} · fts5 {db.get('fts5')}"),
            ("Uptime", f"{float(h.get('uptime_seconds') or 0) / 60:.1f} min"), ("Secret protection", h.get("secret_protection")), ("Connected devices", len(h.get("connected_devices") or [])), ("Data directory", str(self.ctx.data_dir)),
        ])

    def load_audit(self) -> None:
        params = dict(action=self.action.text().strip() or None, severity=self.severity.currentData(), limit=500)
        self.run(lambda: self.api.get("/audit", **params), lambda rows: (self.audit.set_rows(rows), self.audit_empty.setVisible(not rows)))
