"""Screen 8: call eligibility & consent review for one contact (all checks come from the backend)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.screens.contact_detail import ConsentDialog
from sellagent_desktop.widgets import Card, KeyValueGrid, button, caption, combo, fmt_dt, status_label


class EligibilityScreen(BaseScreen):
    key, title = "eligibility", "Eligibility & consent review"
    subtitle = "Every outbound promotional call must pass all checks: emergency stop, number type, suppression, consent, campaign authorization, quiet hours, rate limits, attempts, route capability."

    def build(self) -> None:
        pick = Card("Contact and context")
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("search contacts…")
        self.search.returnPressed.connect(self.load_contacts)
        row.addWidget(self.search, 1)
        self.contact = QComboBox()
        self.contact.setAccessibleName("Contact")
        self.contact.setMinimumWidth(260)
        row.addWidget(self.contact, 2)
        row.addWidget(QLabel("Campaign"))
        self.campaign = QComboBox()
        self.campaign.addItem("none", None)
        row.addWidget(self.campaign, 1)
        row.addWidget(QLabel("Mode"))
        self.mode = combo([("human_assisted", "human_assisted"), ("autonomous", "autonomous")])
        row.addWidget(self.mode)
        row.addWidget(QLabel("Route"))
        self.route = combo([("manual", "manual"), ("android_companion", "android_companion")])
        row.addWidget(self.route)
        rw = QLabel()
        rw.setLayout(row)
        pick.add(rw)
        br = QHBoxLayout()
        br.addWidget(button("Check eligibility", "primary", self.check))
        br.addWidget(button("Record consent for this contact", None, self.record_consent))
        br.addWidget(button("Open contact", None, lambda: self.contact.currentData() and self.ctx.navigate("contact_detail", contact_id=self.contact.currentData())))
        br.addStretch(1)
        bw = QLabel()
        bw.setLayout(br)
        pick.add(bw)
        self.root.addWidget(pick)

        self.banner = status_label("No check run yet.")
        self.banner.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.root.addWidget(self.banner)
        cols = QHBoxLayout()
        rc = Card("Blocking reasons")
        self.reasons = QListWidget()
        self.reasons.setAccessibleName("Blocking reasons")
        rc.add(self.reasons)
        cols.addWidget(rc, 1)
        wc = Card("Warnings")
        self.warnings = QListWidget()
        self.warnings.setAccessibleName("Warnings")
        wc.add(self.warnings)
        cols.addWidget(wc, 1)
        cc = Card("Checks")
        self.checks = KeyValueGrid()
        cc.add(self.checks)
        self.checked_at = caption("")
        cc.add(self.checked_at)
        cols.addWidget(cc, 1)
        self.root.addLayout(cols, 1)
        self._pending_contact: str | None = None

    def set_context(self, contact_id: str | None = None, **_: object) -> None:
        self._pending_contact = contact_id

    def refresh(self) -> None:
        self.load_contacts()

    def load_contacts(self) -> None:
        q = self.search.text().strip() or None
        self.run(lambda: (self.api.get("/contacts", q=q, limit=200), self.api.get("/campaigns")), self._fill)

    def _fill(self, res: tuple) -> None:
        page, camps = res
        cur = self._pending_contact or self.contact.currentData()
        self.contact.clear()
        for c in page.get("items", []):
            self.contact.addItem(f"{c['business_name']} · {c['phone_e164']} · consent {c['consent_status']}", c["id"])
        if cur:
            i = self.contact.findData(cur)
            if i >= 0:
                self.contact.setCurrentIndex(i)
        curc = self.campaign.currentData()
        self.campaign.clear()
        self.campaign.addItem("none", None)
        for c in camps:
            self.campaign.addItem(f"{c['name']} ({c['status']})", c["id"])
        if curc:
            self.campaign.setCurrentIndex(max(0, self.campaign.findData(curc)))
        if self._pending_contact:
            self._pending_contact = None
            self.check()

    def check(self) -> None:
        cid = self.contact.currentData()
        if not cid:
            self.toast("Pick a contact first", "warning")
            return
        params = dict(campaign_id=self.campaign.currentData(), mode=self.mode.currentData(), route=self.route.currentData())
        self.run(lambda: self.api.get(f"/contacts/{cid}/eligibility", **params), self._show)

    def _show(self, e: dict) -> None:
        ok = bool(e.get("eligible"))
        self.banner.setText("ELIGIBLE — all checks passed" if ok else f"NOT ELIGIBLE — {len(e.get('reasons', []))} blocking reason(s)")
        self.banner.setProperty("role", "success" if ok else "danger")
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.reasons.clear()
        self.reasons.addItems(e.get("reasons") or ["none"])
        self.warnings.clear()
        self.warnings.addItems(e.get("warnings") or ["none"])
        self.checks.set_rows([(k, v) for k, v in (e.get("checks") or {}).items()])
        self.checked_at.setText(f"checked {fmt_dt(e.get('checked_at'), True)}")

    def record_consent(self) -> None:
        cid = self.contact.currentData()
        if not cid:
            self.toast("Pick a contact first", "warning")
            return
        dlg = ConsentDialog(self)
        if dlg.exec() != ConsentDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        v["evidence"] = v["evidence"] or None
        self.run(lambda: self.api.post(f"/contacts/{cid}/permissions", v), lambda _: (self.toast("Permission recorded", "success"), self.load_contacts(), self.check()))
