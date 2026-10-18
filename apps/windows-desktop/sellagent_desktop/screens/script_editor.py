"""Screen 14: sales script editor. Overrides live in a knowledge document (category 'general',
title 'Sales script overrides', structured {"scripts": {state: {"hi": ..., "en": ...}}}). Built-in defaults shown read-only."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import caption, status_label, button, confirm

OVERRIDE_TITLE = "Sales script overrides"
SCRIPT_STATES = ["greeting", "permission_to_continue", "needs_discovery", "product_explanation", "objection_handling", "demo_invitation", "human_handoff", "followup_scheduling", "opted_out", "completed"]


def builtin_scripts() -> dict[str, dict[str, str]]:
    try:
        from sellagent_ai.conversation.scripts import SCRIPTS

        return {str(k.value if hasattr(k, "value") else k): dict(v) for k, v in SCRIPTS.items()}
    except Exception:  # noqa: BLE001 - ai-engine not importable in this install
        return {}


class ScriptEditorScreen(BaseScreen):
    key, title = "scripts", "Sales script editor"
    subtitle = "Left: built-in approved lines (read-only). Right: your overrides, saved as a knowledge document that must be APPROVED before use. Prices and numbers are NEVER typed here — they are injected only from approved pricing facts."

    def build(self) -> None:
        self.doc: dict | None = None
        self.builtin = builtin_scripts()
        self.table = QTableWidget(len(SCRIPT_STATES), 5)
        self.table.setHorizontalHeaderLabels(["State", "Built-in हिन्दी", "Built-in English", "Override हिन्दी", "Override English"])
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
        self.editors: dict[tuple[str, str], QPlainTextEdit] = {}
        for i, st in enumerate(SCRIPT_STATES):
            item = QTableWidgetItem(st)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, item)
            for j, lang in ((1, "hi"), (2, "en")):
                ro = QPlainTextEdit(self.builtin.get(st, {}).get(lang, "(built-in defaults unavailable)"))
                ro.setReadOnly(True)
                ro.setMaximumHeight(90)
                self.table.setCellWidget(i, j, ro)
            for j, lang in ((3, "hi"), (4, "en")):
                ed = QPlainTextEdit()
                ed.setMaximumHeight(90)
                ed.setPlaceholderText(f"optional override ({lang})")
                ed.setAccessibleName(f"{st} override {lang}")
                self.editors[(st, lang)] = ed
                self.table.setCellWidget(i, j, ed)
            self.table.setRowHeight(i, 96)
        self.root.addWidget(self.table, 1)
        self.status_lbl = status_label("")
        self.root.addWidget(self.status_lbl)
        row = QHBoxLayout()
        row.addWidget(button("Save overrides (creates a pending version)", "primary", self.save))
        row.addWidget(button("Open knowledge base to approve", None, lambda: self.ctx.navigate("knowledge")))
        row.addWidget(button("Reload", None, self.refresh))
        row.addStretch(1)
        self.root.addLayout(row)
        self.root.addWidget(caption("Placeholders you may keep: {contact_person}, {business_name}, {pricing_line}, {objection_line}. Digits are rejected to stop unapproved prices from entering the script."))

    def refresh(self) -> None:
        self.run(lambda: self.api.get("/knowledge", category="general"), self._show)

    def _show(self, docs: list) -> None:
        cands = [d for d in docs if d.get("title") == OVERRIDE_TITLE]
        cands.sort(key=lambda d: (d.get("status") == "approved", d.get("version", 0)))
        self.doc = cands[-1] if cands else None
        scripts = ((self.doc or {}).get("structured") or {}).get("scripts") or {}
        for (st, lang), ed in self.editors.items():
            ed.setPlainText(str(scripts.get(st, {}).get(lang, "")))
        if self.doc:
            self.status_lbl.setText(f"Override document v{self.doc['version']} — status {self.doc['status'].upper()}" + ("" if self.doc["status"] == "approved" else " (not used by the agent until approved in the knowledge base)"))
            self.status_lbl.setProperty("role", "success" if self.doc["status"] == "approved" else "warning")
        else:
            self.status_lbl.setText("No override document yet — built-in lines are in use.")
            self.status_lbl.setProperty("role", "caption")
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

    def save(self) -> None:
        scripts: dict[str, dict[str, str]] = {}
        for (st, lang), ed in self.editors.items():
            t = ed.toPlainText().strip()
            if any(ch.isdigit() for ch in t):
                ed.setProperty("invalid", "true")
                ed.style().unpolish(ed)
                ed.style().polish(ed)
                self.toast(f"{st}/{lang}: remove digits — prices come only from approved pricing facts", "error")
                return
            ed.setProperty("invalid", "false")
            ed.style().unpolish(ed)
            ed.style().polish(ed)
            if t:
                scripts.setdefault(st, {})[lang] = t
        body_text = "Sales script overrides (per conversation state, hi/en). Managed by the desktop script editor.\n\n" + json.dumps(scripts, ensure_ascii=False, indent=2)
        structured = {"scripts": scripts, "kind": "sales_script_overrides"}
        if self.doc and not confirm(self, "Save overrides", f"Create version {self.doc['version'] + 1} of the override document? It stays pending until approved.", "Save"):
            return
        if self.doc:
            did = self.doc["id"]
            self.run(lambda: self.api.post(f"/knowledge/{did}/supersede", {"body": body_text, "title": OVERRIDE_TITLE, "structured": structured}), lambda d: (self.toast(f"Saved v{d['version']} (pending)", "success"), self.refresh()))
        else:
            self.run(lambda: self.api.post("/knowledge", {"title": OVERRIDE_TITLE, "body": body_text, "category": "general", "language": "en", "source": "desktop_script_editor", "structured": structured}), lambda d: (self.toast("Override document created (pending approval)", "success"), self.refresh()))
