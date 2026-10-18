"""Screen 6: CSV/XLSX import wizard (upload -> mapping -> preview -> commit) and exports via QFileDialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, button, caption, combo, confirm, status_label


class ImportExportScreen(BaseScreen):
    key, title = "import_export", "Import / export"
    subtitle = "Import contacts from CSV or XLSX. Rows are validated and de-duplicated by phone number before anything is written."

    def build(self) -> None:
        self.upload: dict | None = None
        self.preview: dict | None = None
        step1 = Card("1. Choose file")
        row = QHBoxLayout()
        self.file_lbl = QLabel("No file selected")
        row.addWidget(button("Pick CSV / XLSX…", "primary", self.pick_file))
        row.addWidget(self.file_lbl, 1)
        self.upload_info = caption("")
        w = QLabel()
        w.setLayout(row)
        step1.add(w)
        step1.add(self.upload_info)
        self.root.addWidget(step1)

        step2 = Card("2. Map columns")
        step2.add(caption("Pick the source column for each contact field. business_name and phone are required."))
        self.map_table = QTableWidget(0, 2)
        self.map_table.setHorizontalHeaderLabels(["Contact field", "Source column"])
        self.map_table.horizontalHeader().setStretchLastSection(True)
        self.map_table.verticalHeader().setVisible(False)
        self.map_table.setMaximumHeight(240)
        step2.add(self.map_table)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Duplicate policy"))
        self.dup_policy = combo([("skip duplicates", "skip"), ("update existing", "update"), ("import anyway", "import_anyway")])
        self.dup_policy.setAccessibleName("Duplicate policy")
        opts.addWidget(self.dup_policy)
        opts.addWidget(QLabel("Lead source"))
        self.lead_source = QLineEdit()
        self.lead_source.setPlaceholderText("optional label, e.g. JustDial list Oct-2026")
        opts.addWidget(self.lead_source, 1)
        opts.addWidget(QLabel("Campaign"))
        self.campaign = QComboBox()
        self.campaign.addItem("none", None)
        opts.addWidget(self.campaign)
        ow = QLabel()
        ow.setLayout(opts)
        step2.add(ow)
        self.preview_btn = button("Preview", "primary", self.do_preview)
        self.preview_btn.setEnabled(False)
        step2.add(self.preview_btn)
        self.root.addWidget(step2)

        step3 = Card("3. Preview and commit")
        self.counts = status_label("")
        step3.add(self.counts)
        self.rows_table = DataTable([("Row", "row_number"), ("Status", "status"), ("Business", lambda r: (r.get("normalized") or {}).get("business_name")), ("Phone", lambda r: (r.get("normalized") or {}).get("phone_e164") or (r.get("normalized") or {}).get("phone")), ("Errors", "errors"), ("Duplicate of", "duplicate_of")])
        self.rows_table.setMaximumHeight(220)
        step3.add(self.rows_table)
        self.commit_btn = button("Commit import", "primary", self.do_commit)
        self.commit_btn.setEnabled(False)
        self.result = status_label("")
        step3.add(self.commit_btn)
        step3.add(self.result)
        self.root.addWidget(step3)

        exp = Card("Export contacts")
        er = QHBoxLayout()
        er.addWidget(button("Export CSV…", None, lambda: self.export("csv")))
        er.addWidget(button("Export XLSX…", None, lambda: self.export("xlsx")))
        er.addWidget(caption("Active contacts only; archived rows are excluded."))
        er.addStretch(1)
        ew = QLabel()
        ew.setLayout(er)
        exp.add(ew)
        self.root.addWidget(exp)
        self.root.addStretch(1)

    def refresh(self) -> None:
        self.run(lambda: self.api.get("/campaigns"), self._campaigns)

    def _campaigns(self, camps: list) -> None:
        cur = self.campaign.currentData()
        self.campaign.clear()
        self.campaign.addItem("none", None)
        for c in camps:
            self.campaign.addItem(f"{c['name']} ({c['status']})", c["id"])
        if cur:
            i = self.campaign.findData(cur)
            if i >= 0:
                self.campaign.setCurrentIndex(i)

    def pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose contact file", "", "Spreadsheets (*.csv *.xlsx);;All files (*)")
        if not path:
            return
        self.load_file(Path(path))

    def load_file(self, p: Path) -> None:
        self.file_lbl.setText(p.name)
        data = p.read_bytes()
        self.run(lambda: self.api.upload("/contacts/import/upload", p.name, data), self._uploaded, busy_text="Uploading…")

    def _uploaded(self, up: dict) -> None:
        self.upload, self.preview = up, None
        self.upload_info.setText(f"upload {up['upload_id'][:8]}… — {up['row_count']} rows, columns: {', '.join(up['headers'])}")
        fields = up.get("importable_fields", [])
        req = set(up.get("required_fields", []))
        sugg = up.get("suggested_mapping", {})
        self.map_table.setRowCount(len(fields))
        self.map_combos: dict[str, QComboBox] = {}
        for i, f in enumerate(fields):
            item = QTableWidgetItem(f + (" *" if f in req else ""))
            self.map_table.setItem(i, 0, item)
            cb = QComboBox()
            cb.addItem("— not mapped —", None)
            for h in up["headers"]:
                cb.addItem(h, h)
            if sugg.get(f):
                cb.setCurrentIndex(cb.findData(sugg[f]))
            cb.setAccessibleName(f"Source column for {f}")
            self.map_table.setCellWidget(i, 1, cb)
            self.map_combos[f] = cb
        self.preview_btn.setEnabled(True)
        self.commit_btn.setEnabled(False)
        self.counts.setText("")
        self.rows_table.set_rows([])

    def _mapping_body(self) -> dict | None:
        if not self.upload:
            return None
        mapping = {f: cb.currentData() for f, cb in self.map_combos.items()}
        missing = [f for f in self.upload.get("required_fields", []) if not mapping.get(f)]
        if missing:
            self.toast(f"Map the required field(s): {', '.join(missing)}", "warning")
            return None
        return {"upload_id": self.upload["upload_id"], "mapping": mapping, "duplicate_policy": self.dup_policy.currentData(), "lead_source": self.lead_source.text().strip() or None, "campaign_id": self.campaign.currentData()}

    def do_preview(self) -> None:
        body = self._mapping_body()
        if body is None:
            return
        self.run(lambda: self.api.post("/contacts/import/preview", body, params={"limit": 500}), self._previewed, busy_text="Validating…")

    def _previewed(self, pv: dict) -> None:
        self.preview = pv
        self.counts.setText(f"{pv['total_rows']} rows: {pv['valid']} valid · {pv['invalid']} invalid · {pv['duplicates']} duplicates (first {len(pv['rows'])} shown)")
        self.rows_table.set_rows(pv.get("rows", []))
        self.commit_btn.setEnabled(pv["valid"] > 0 or (pv["duplicates"] > 0 and self.dup_policy.currentData() != "skip"))

    def do_commit(self) -> None:
        body = self._mapping_body()
        if body is None or not self.preview:
            return
        if not confirm(self, "Commit import", f"Write {self.preview['valid']} valid rows (duplicates: {self.dup_policy.currentText()}) to the local database?", "Import"):
            return
        self.run(lambda: self.api.post("/contacts/import/commit", body), self._committed, busy_text="Importing…")

    def _committed(self, res: dict) -> None:
        self.result.setText(f"Imported: created {res.get('created')}, updated {res.get('updated')}, skipped {res.get('skipped')}, invalid {res.get('invalid')} of {res.get('total')} rows.")
        self.result.setProperty("role", "success")
        self.result.style().unpolish(self.result)
        self.result.style().polish(self.result)
        self.commit_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.upload = None
        self.toast("Import finished", "success")

    def export(self, fmt: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export contacts", f"contacts.{fmt}", f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        self.run(lambda: self.api.download("/contacts/export", fmt=fmt), lambda res: self._save(path, res[0]), busy_text="Exporting…")

    def _save(self, path: str, data: bytes) -> None:
        Path(path).write_bytes(data)
        self.toast(f"Saved {len(data):,} bytes to {path}", "success")
