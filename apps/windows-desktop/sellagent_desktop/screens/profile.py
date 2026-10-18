"""Profile page: the local operator. There is no cloud account, sign-in or billing in SELL AGENT."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, KeyValueGrid, avatar, button, caption, chip, mark_invalid


class ProfileScreen(BaseScreen):
    key, title = "profile", "Profile"
    scrollable = True
    subtitle = "Local operator — no cloud account. Everything you do is recorded in the local audit log under this name."

    def build(self) -> None:
        card = Card(gold=True)
        row = QHBoxLayout()
        self.avatar = avatar("")
        row.addWidget(self.avatar)
        col = QVBoxLayout()
        self.name_lbl = caption("")
        self.name_lbl.setProperty("role", "greeting")
        col.addWidget(self.name_lbl)
        col.addWidget(chip("Local operator — no cloud account", "neutral"))
        row.addLayout(col, 1)
        w = QWidget()
        w.setLayout(row)
        card.add(w)
        self.grid = KeyValueGrid()
        card.add(self.grid)
        self.root.addWidget(card)
        edit = Card("Edit")
        self.operator = QLineEdit()
        self.operator.setAccessibleName("Operator name")
        self.business = QLineEdit()
        self.business.setAccessibleName("Business name")
        self.display = QLineEdit()
        self.display.setAccessibleName("App display name")
        for lbl, w in (("Operator name", self.operator), ("Business name", self.business), ("App display name", self.display)):
            edit.add(caption(lbl))
            edit.add(w)
        edit.add(button("Save profile", "primary", self.save))
        self.root.addWidget(edit)
        self.root.addWidget(caption("Sign-in, plans and billing from the mockup are intentionally absent: SELL AGENT runs entirely on this PC."))
        self.root.addStretch(1)

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/settings"), self.api.get("/auth/whoami")), self._show)

    def _show(self, res: tuple) -> None:
        s, who = res
        v = s.get("values", {})
        self.ctx.settings_cache.update(v)
        name = v.get("general.operator_name") or "Operator"
        self.avatar.setText(name[:2].upper())
        self.name_lbl.setText(name)
        self.grid.set_rows([("Business", v.get("general.business_name")), ("App display name", v.get("general.app_display_name")), ("Locale / timezone", f"{v.get('general.locale')} / {v.get('general.timezone')}"), ("Backend actor", f"{who.get('actor')} ({who.get('scope')})"), ("Data directory", str(self.ctx.data_dir))])
        self.operator.setText(name)
        self.business.setText(str(v.get("general.business_name") or ""))
        self.display.setText(str(v.get("general.app_display_name") or "SELL AGENT"))

    def save(self) -> None:
        bad = False
        for w in (self.operator, self.business, self.display):
            invalid = len(w.text().strip()) < 2
            mark_invalid(w, invalid)
            bad = bad or invalid
        if bad:
            self.toast("Names need at least 2 characters", "error")
            return
        vals = {"general.operator_name": self.operator.text().strip(), "general.business_name": self.business.text().strip(), "general.app_display_name": self.display.text().strip()}
        self.run(lambda: self.api.patch("/settings", {"values": vals}), lambda _: (self.toast("Profile saved", "success"), self.refresh()))
