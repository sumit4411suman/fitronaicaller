"""Screen 13: FITRON knowledge base (review queue, approvals with injection flags, versions, retrieval test)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, EmptyState, FormDialog, KeyValueGrid, TextInputDialog, badge, button, caption, combo, confirm, fmt_dt, pretty_json, status_label

STATUSES = ("pending_review", "approved", "rejected", "superseded", "expired")


class KnowledgeDialog(FormDialog):
    def __init__(self, parent: QWidget | None, categories: list[str], existing: dict | None = None):
        super().__init__(parent, "New version" if existing else "New knowledge document", "Save")
        e = existing or {}
        self.add_field("title", "Title", QLineEdit(e.get("title", "")), required=True)
        cat = combo([(c, c) for c in categories], e.get("category", "general"))
        cat.setEnabled(existing is None)
        self.add_field("category", "Category", cat)
        lang = combo([("English", "en"), ("हिन्दी", "hi")], e.get("language", "en"))
        lang.setEnabled(existing is None)
        self.add_field("language", "Language", lang)
        body = QPlainTextEdit(e.get("body", ""))
        body.setMinimumHeight(160)
        self.add_field("body", "Body (facts only; numbers here are what the agent may quote once approved)", body, required=True)
        st = QPlainTextEdit(pretty_json(e.get("structured")) if e.get("structured") else "")
        st.setMaximumHeight(80)
        st.setPlaceholderText('optional JSON, e.g. {"price_inr": 1999, "billing": "monthly"}')
        self.add_field("structured", "Structured JSON", st)

    def validate(self) -> bool:
        ok = super().validate()
        s = self.raw_value("structured")
        if s:
            import json

            try:
                v = json.loads(s)
                if not isinstance(v, dict):
                    raise ValueError
            except ValueError:
                self.set_field_error("structured", "Must be a JSON object")
                ok = False
        return ok

    def payload(self) -> dict:
        import json

        v = self.values()
        v["structured"] = json.loads(v["structured"]) if v["structured"] else None
        return v


class KnowledgeScreen(BaseScreen):
    key, title = "knowledge", "FITRON knowledge base"
    subtitle = "Only APPROVED documents can be injected into agent lines. Imports are untrusted until you review their injection flags."

    def build(self) -> None:
        self.categories: list[str] = []
        bar = QHBoxLayout()
        self.status = combo([("all statuses", None)] + [(s, s) for s in STATUSES])
        self.status.currentIndexChanged.connect(self.refresh)
        self.category = QComboBox()
        self.category.addItem("all categories", None)
        self.category.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.status)
        bar.addWidget(self.category)
        bar.addWidget(button("New document", "primary", self.new_doc))
        bar.addWidget(button("Import .txt/.md…", None, self.import_doc))
        bar.addStretch(1)
        self.root.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.table = DataTable([("Category", "category"), ("Title", "title"), ("v", "version"), ("Status", "status"), ("Lang", "language"), ("Trusted", "trusted"), ("Flags", lambda r: len(r.get("injection_flags") or [])), ("Updated", lambda r: fmt_dt(r.get("updated_at")))])
        self.table.setObjectName("knowledge_table")
        self.table.itemSelectionChanged.connect(self._select)
        ll.addWidget(self.table, 1)
        self.empty = EmptyState("No documents for this filter.")
        ll.addWidget(self.empty)
        rt = Card("Retrieval test (what the agent would see)")
        rr = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("e.g. FITRON price per month")
        self.query.returnPressed.connect(self.retrieve)
        rr.addWidget(self.query, 1)
        self.incl_unapproved = QCheckBox("include unapproved")
        rr.addWidget(self.incl_unapproved)
        rr.addWidget(button("Retrieve", None, self.retrieve))
        rw = QWidget()
        rw.setLayout(rr)
        rt.add(rw)
        self.refs = QListWidget()
        self.refs.setMaximumHeight(130)
        rt.add(self.refs)
        ll.addWidget(rt)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.detail = Card("Document", gold=True)
        self.meta = KeyValueGrid()
        self.detail.add(self.meta)
        self.flags_lbl = status_label("")
        self.detail.add(self.flags_lbl)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setMinimumHeight(180)
        self.detail.add(self.body)
        self.ack = QCheckBox("I reviewed the injection flags and accept this content")
        self.detail.add(self.ack)
        act = QHBoxLayout()
        self.approve_btn = button("Approve", "primary", self.approve)
        self.reject_btn = button("Reject", None, self.reject)
        self.supersede_btn = button("New version (supersede)", None, self.supersede)
        self.delete_btn = button("Delete", "danger", self.delete)
        for b in (self.approve_btn, self.reject_btn, self.supersede_btn, self.delete_btn):
            act.addWidget(b)
        act.addStretch(1)
        aw = QWidget()
        aw.setLayout(act)
        self.detail.add(aw)
        rl.addWidget(self.detail)
        rl.addStretch(1)
        split.addWidget(right)
        split.setSizes([620, 520])
        self.root.addWidget(split, 1)
        self._select()

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/knowledge", status=self.status.currentData(), category=self.category.currentData()), self.api.get("/knowledge/categories")), self._show)

    def _show(self, res: tuple) -> None:
        docs, cats = res
        self.categories = cats.get("categories", [])
        if self.category.count() == 1:
            self.category.blockSignals(True)
            for c in self.categories:
                self.category.addItem(c, c)
            self.category.blockSignals(False)
        self.table.set_rows(docs)
        self.empty.setVisible(not docs)
        self._select()

    def _select(self) -> None:
        d = self.table.selected_row()
        for b in (self.approve_btn, self.reject_btn, self.supersede_btn, self.delete_btn, self.ack):
            b.setEnabled(d is not None)
        if not d:
            self.meta.set_rows([("", "Select a document")])
            self.body.clear()
            self.flags_lbl.setText("")
            return
        self.meta.set_rows([(k, fmt_dt(d.get(k)) if k.endswith("_at") else (pretty_json(d.get(k)) if k == "structured" else d.get(k))) for k in ("id", "title", "category", "language", "status", "version", "supersedes_id", "source", "trusted", "approved_by", "approved_at", "effective_from", "expires_at", "structured")])
        flags = d.get("injection_flags") or []
        self.flags_lbl.setText(("INJECTION FLAGS: " + "; ".join(flags)) if flags else "No injection flags found by the screening pass.")
        self.flags_lbl.setProperty("role", "danger" if flags else "success")
        self.flags_lbl.style().unpolish(self.flags_lbl)
        self.flags_lbl.style().polish(self.flags_lbl)
        self.body.setPlainText(d.get("body", ""))
        self.ack.setVisible(bool(flags))
        self.ack.setChecked(False)
        self.approve_btn.setEnabled(d.get("status") in ("pending_review", "rejected"))
        self.reject_btn.setEnabled(d.get("status") == "pending_review")

    def _sel(self) -> dict | None:
        d = self.table.selected_row()
        if d is None:
            self.toast("Select a document", "warning")
        return d

    def new_doc(self) -> None:
        dlg = KnowledgeDialog(self, self.categories or ["general"])
        if dlg.exec() == KnowledgeDialog.DialogCode.Accepted:
            body = dlg.payload()
            self.run(lambda: self.api.post("/knowledge", body), lambda d: (self.toast(f"Created '{d['title']}' (status {d['status']})", "success"), self.refresh()))

    def import_doc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import knowledge document", "", "Text (*.txt *.md *.csv)")
        if not path:
            return
        p = Path(path)
        data = p.read_bytes()
        cat = self.category.currentData() or "general"
        self.run(lambda: self.api.upload("/knowledge/import", p.name, data, params={"category": cat, "language": "en"}), lambda d: (self.toast(f"Imported as UNTRUSTED pending document with {len(d.get('injection_flags') or [])} flag(s)", "warning"), self.refresh()))

    def approve(self) -> None:
        d = self._sel()
        if not d:
            return
        flags = d.get("injection_flags") or []
        if flags and not self.ack.isChecked():
            self.toast("Tick the acknowledgement checkbox: this document has injection flags", "warning")
            return
        if not confirm(self, "Approve document", f"Approve '{d['title']}' v{d['version']}? Approved facts can be quoted by the agent.", "Approve"):
            return
        self.run(lambda: self.api.post(f"/knowledge/{d['id']}/approve", {"acknowledge_flags": self.ack.isChecked()}), lambda _: (self.toast("Approved", "success"), self.refresh()))

    def reject(self) -> None:
        d = self._sel()
        if not d:
            return
        dlg = TextInputDialog(self, "Reject document", "Reason")
        if dlg.exec() == TextInputDialog.DialogCode.Accepted:
            reason = dlg.value().strip()
            self.run(lambda: self.api.post(f"/knowledge/{d['id']}/reject", {"reason": reason}), lambda _: self.refresh())

    def supersede(self) -> None:
        d = self._sel()
        if not d:
            return
        dlg = KnowledgeDialog(self, self.categories, existing=d)
        if dlg.exec() == KnowledgeDialog.DialogCode.Accepted:
            p = dlg.payload()
            body = {"body": p["body"], "title": p["title"], "structured": p["structured"]}
            self.run(lambda: self.api.post(f"/knowledge/{d['id']}/supersede", body), lambda nd: (self.toast(f"Version {nd['version']} created (pending approval)", "success"), self.refresh()))

    def delete(self) -> None:
        d = self._sel()
        if d and confirm(self, "Delete document", f"Delete '{d['title']}' v{d['version']} permanently?", "Delete", danger=True):
            self.run(lambda: self.api.delete(f"/knowledge/{d['id']}"), lambda _: self.refresh())

    def retrieve(self) -> None:
        q = self.query.text().strip()
        if not q:
            return
        self.run(lambda: self.api.get("/knowledge/retrieve", q=q, limit=8, include_unapproved=self.incl_unapproved.isChecked()), self._refs)

    def _refs(self, rows: list) -> None:
        self.refs.clear()
        if not rows:
            self.refs.addItem("no matching approved knowledge — the agent would say it has no confirmed information")
        for r in rows:
            self.refs.addItem(f"{r['ref']} · {r['category']} · {r['title']} · score {r['score']:.2f}: {r['text'][:140]}")
