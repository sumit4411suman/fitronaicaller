"""Screen 21: backup & restore (encrypted when backup.encrypt is on; restore needs the typed word RESTORE)."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from sellagent_desktop.api_client import LONG_TIMEOUT
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import DataTable, EmptyState, TextInputDialog, button, caption, confirm, fmt_bytes, fmt_dt, pretty_json, status_label, warn


class BackupScreen(BaseScreen):
    key, title = "backup", "Backup & restore"

    def build(self) -> None:
        self.encrypt = True
        bar = QHBoxLayout()
        bar.addWidget(button("Create backup", "primary", self.create))
        bar.addWidget(button("Verify selected", None, self.verify))
        bar.addWidget(button("Restore selected…", "danger", self.restore))
        bar.addWidget(button("Reload", None, self.refresh))
        bar.addStretch(1)
        self.root.addLayout(bar)
        self.note = caption("")
        self.root.addWidget(self.note)
        self.table = DataTable([("Name", "name"), ("Encrypted", "encrypted"), ("Size", lambda r: fmt_bytes(r.get("size"))), ("Created", lambda r: fmt_dt(r.get("created_at"))), ("App version", "app_version"), ("SHA-256", "sha256"), ("Path", "path")])
        self.root.addWidget(self.table, 1)
        self.empty = EmptyState("No backups yet. Backups are written to <data_dir>/backups and rotated by backup.retention_count.")
        self.root.addWidget(self.empty)
        self.result = status_label("")
        self.root.addWidget(self.result)

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/backup"), self.api.get("/settings"), self.api.get("/health")), self._show)

    def _show(self, res: tuple) -> None:
        rows, s, h = res
        self.db_encrypted = bool((h.get("database") or {}).get("encrypted"))
        self.encrypt = bool(s.get("values", {}).get("backup.encrypt")) or self.db_encrypted
        self.note.setText(("Database is encrypted (AES-256): every backup needs a passphrase. " if self.db_encrypted else "") + f"Encryption: {'ON — a passphrase (>= 8 chars) is required and must be kept safe; it cannot be recovered' if self.encrypt else 'OFF — plain SQLite copies with a JSON manifest'} · keep last {s.get('values', {}).get('backup.retention_count')} · folder {self.ctx.data_dir / 'backups'}")
        self.table.set_rows(rows)
        self.empty.setVisible(not rows)

    def _passphrase(self, title: str) -> str | None:
        dlg = TextInputDialog(self, title, "Passphrase (min 8 characters)", min_length=8, password=True)
        return dlg.value() if dlg.exec() == TextInputDialog.DialogCode.Accepted else None

    def create(self) -> None:
        body: dict = {}
        if self.encrypt:
            p = self._passphrase("Backup passphrase")
            if p is None:
                return
            body["passphrase"] = p
        self.run(lambda: self.api.post("/backup", body, timeout=LONG_TIMEOUT), lambda r: (self._result(f"Backup written: {r.get('path')} ({fmt_bytes(r.get('size'))}, sha256 {str(r.get('sha256'))[:16]}…)"), self.refresh()), busy_text="Backing up…")

    def _sel(self) -> dict | None:
        row = self.table.selected_row()
        if not row:
            self.toast("Select a backup", "warning")
        return row

    def verify(self) -> None:
        row = self._sel()
        if not row:
            return
        body = {"path": row["path"], "confirm": "RESTORE", "passphrase": None}
        if row.get("encrypted"):
            p = self._passphrase("Passphrase of this backup")
            if p is None:
                return
            body["passphrase"] = p
        self.run(lambda: self.api.post("/backup/verify", body, timeout=LONG_TIMEOUT), lambda r: self._result("Verify OK: " + pretty_json(r)), busy_text="Verifying…")

    def restore(self) -> None:
        row = self._sel()
        if not row:
            return
        warn(self, "Restore replaces the live database", "All current contacts, calls and settings will be replaced by the backup. Take a fresh backup first if in doubt. After the restore the backend reopens the database and the desktop app should be restarted.")
        dlg = TextInputDialog(self, "Confirm restore", "Type RESTORE to continue", required_literal="RESTORE", note=f"Restoring {row['name']}")
        if dlg.exec() != TextInputDialog.DialogCode.Accepted:
            return
        body = {"path": row["path"], "confirm": "RESTORE", "passphrase": None}
        if row.get("encrypted"):
            p = self._passphrase("Passphrase of this backup")
            if p is None:
                return
            body["passphrase"] = p
        if not confirm(self, "Last chance", "Restore now? The application will ask you to restart afterwards.", "Restore", danger=True):
            return
        self.run(lambda: self.api.post("/backup/restore", body, timeout=LONG_TIMEOUT), self._restored, busy_text="Restoring…")

    def _restored(self, r: dict) -> None:
        self._result("Restored: " + pretty_json(r))
        warn(self, "Restart recommended", "The backup was restored and migrations re-applied. Close and reopen SELL AGENT so every screen reloads from the restored database.")

    def _result(self, text: str) -> None:
        self.result.setText(text)
        self.toast(text.split("\n")[0], "success")
