"""Screen 4: Contacts per the mockup — search, filter chips, table with status chips and quick actions, New contact dialog."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QWidget

from sellagent_desktop.api_client import ApiError
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import STAGE_CHIP, DataTable, EmptyState, FormDialog, button, chip, combo, confirm, fmt_dt

LEAD_STAGES = ("new", "contacted", "interested", "demo_scheduled", "converted", "not_interested", "do_not_call")
CONSENT = ("unknown", "granted", "denied", "withdrawn")
PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{3,39}$")
PAGE = 50
CATEGORIES = ["Gym / Fitness", "Yoga studio", "CrossFit / functional", "Martial arts", "Dance studio", "Sports club", "Other"]
FILTER_CHIPS = [("all", "All"), ("not_called", "Not called"), ("followup", "Follow-up"), ("interested", "Interested"), ("dnc", "Do not call")]


class ContactDialog(FormDialog):
    """Create or edit a contact; validation mirrors the backend ContactIn schema."""

    def __init__(self, parent: QWidget | None, stages: tuple[str, ...] = LEAD_STAGES, existing: dict | None = None):
        super().__init__(parent, "Edit contact" if existing else "New contact", "Save contact" if existing else "Create contact")
        self.setObjectName("ContactDialog")
        e = existing or {}
        self.add_field("business_name", "Business / gym name", QLineEdit(e.get("business_name", "")), required=True)
        self.add_field("contact_person", "Contact person", QLineEdit(e.get("contact_person") or ""))
        cat = QComboBox()
        cat.setEditable(True)
        cat.addItems(CATEGORIES)
        cat.setCurrentText(e.get("category") or "Gym / Fitness")
        cat.setObjectName("category")
        self.add_field("category", "Category", cat, help_text="Business type; default Gym / Fitness")
        ph = QLineEdit(e.get("phone_raw") or e.get("phone_e164") or "")
        ph.setPlaceholderText("+91 98765 43210")
        self.add_field("phone", "Phone", ph, required=True, help_text="Indian numbers may be entered without +91; stored as E.164")
        self.add_field("email", "Email", QLineEdit(e.get("email") or ""))
        self.add_field("city", "City", QLineEdit(e.get("city") or ""))
        self.add_field("district", "District", QLineEdit(e.get("district") or ""))
        self.add_field("state", "State", QLineEdit(e.get("state") or ""))
        self.add_field("source_url", "Source URL", QLineEdit(e.get("source_url") or ""))
        self.add_field("source_verification", "Source verification", combo([(x, x) for x in ("unverified", "verified", "rejected")], e.get("source_verification", "unverified")))
        self.add_field("lead_source", "Lead source", QLineEdit(e.get("lead_source") or ""))
        self.add_field("lead_stage", "Lead stage", combo([(s, s) for s in stages], e.get("lead_stage", "new")))
        self.add_field("consent_status", "Consent status", combo([(c, c) for c in CONSENT], e.get("consent_status", "unknown")), help_text="Record evidence under Permissions on the contact page; this is only the summary flag")
        tags = QLineEdit(", ".join(e.get("tags") or []))
        tags.setPlaceholderText("comma, separated, tags")
        self.add_field("tags", "Tags", tags)
        notes = QPlainTextEdit(e.get("notes") or "")
        notes.setMaximumHeight(80)
        self.add_field("notes", "Notes", notes)
        self.fields["business_name"].setObjectName("business_name")
        self.fields["phone"].setObjectName("phone")

    def validate(self) -> bool:
        ok = super().validate()
        phone = self.raw_value("phone")
        if phone and not PHONE_RE.match(phone):
            self.set_field_error("phone", "Enter digits with optional +, spaces, dashes or brackets")
            ok = False
        email = self.raw_value("email")
        if email and "@" not in email:
            self.set_field_error("email", "Enter a valid email address or leave empty")
            ok = False
        return ok

    def payload(self) -> dict:
        v = self.values()
        v["tags"] = [t.strip() for t in str(v["tags"]).split(",") if t.strip()]
        v["category"] = (self.fields["category"].currentText().strip() or "Gym / Fitness")[:50]
        for k in ("contact_person", "email", "city", "district", "state", "source_url", "lead_source", "notes"):
            if v[k] == "":
                v[k] = None
        return v


class ContactsScreen(BaseScreen):
    key, title = "contacts", "Contacts"

    def build(self) -> None:
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search business, person, phone, city…")
        self.search.setAccessibleName("Search contacts")
        self.search.setObjectName("contacts_search")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.first_page)
        bar.addWidget(self.search, 2)
        bar.addWidget(button("Search", None, self.first_page))
        self.new_btn = button("+ New contact", "primary", self.new_contact)
        self.new_btn.setObjectName("new_contact_btn")
        bar.addWidget(self.new_btn)
        bar.addWidget(button("Import / export", None, lambda: self.ctx.navigate("import_export")))
        self.root.addLayout(bar)

        chips = QHBoxLayout()
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        self.filter_chips: dict[str, QPushButton] = {}
        for key, label in FILTER_CHIPS:
            b = QPushButton(label)
            b.setProperty("role", "chip")
            b.setCheckable(True)
            b.setAccessibleName(f"Filter {label}")
            b.clicked.connect(lambda _=False: self.first_page())
            self.chip_group.addButton(b)
            self.filter_chips[key] = b
            chips.addWidget(b)
        self.filter_chips["all"].setChecked(True)
        chips.addSpacing(16)
        self.stage = combo([("all stages", None)] + [(s, s) for s in LEAD_STAGES])
        self.stage.setAccessibleName("Lead stage filter")
        self.consent = combo([("any consent", None)] + [(c, c) for c in CONSENT])
        self.consent.setAccessibleName("Consent filter")
        self.sort = combo([("updated", "updated_at"), ("created", "created_at"), ("business name", "business_name"), ("city", "city"), ("lead stage", "lead_stage"), ("last contact", "last_contact_at"), ("next follow-up", "next_followup_at")])
        self.sort.setAccessibleName("Sort by")
        self.desc = QCheckBox("newest first")
        self.desc.setChecked(True)
        self.archived = QCheckBox("archived")
        self.archived.setAccessibleName("Show archived contacts")
        for w in (self.stage, self.consent, self.sort, self.desc, self.archived):
            chips.addWidget(w)
            if isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self.first_page)
            else:
                w.stateChanged.connect(self.first_page)
        chips.addStretch(1)
        self.root.addLayout(chips)

        actions = QHBoxLayout()
        self.open_btn = button("Open detail", None, self.open_selected)
        self.archive_btn = button("Archive", None, self.archive_selected)
        self.queue_btn = button("Create call job", None, lambda: self._with_selected(lambda c: self.ctx.navigate("call_queue", contact_id=c["id"])))
        self.elig_btn = button("Check eligibility", None, lambda: self._with_selected(lambda c: self.ctx.navigate("eligibility", contact_id=c["id"])))
        for b in (self.open_btn, self.queue_btn, self.elig_btn, self.archive_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        self.page_lbl = QLabel("")
        self.prev_btn = button("◀", None, lambda: self.load(self.offset - PAGE))
        self.next_btn = button("▶", None, lambda: self.load(self.offset + PAGE))
        actions.addWidget(self.prev_btn)
        actions.addWidget(self.page_lbl)
        actions.addWidget(self.next_btn)
        self.root.addLayout(actions)

        self.table = DataTable([
            ("Business", "business_name"), ("Person", "contact_person"), ("Phone", "phone_e164"), ("City", "city"), ("Status", "lead_stage"),
            ("Category", "category"), ("Consent", "consent_status"), ("Last contact", lambda r: fmt_dt(r.get("last_contact_at"))), ("Next follow-up", lambda r: fmt_dt(r.get("next_followup_at"))), ("Actions", lambda r: ""),
        ])
        self.table.setObjectName("contacts_table")
        self.table.setSortingEnabled(False)  # server-side sort; cell widgets (chips/actions) must stay aligned
        self.table.itemDoubleClicked.connect(lambda *_: self.open_selected())
        self.root.addWidget(self.table, 1)
        self.empty = EmptyState("No contacts match. Create one with '+ New contact' or import a CSV/XLSX under Import / export.")
        self.root.addWidget(self.empty)
        self.offset, self.total = 0, 0

    def set_context(self, query: str | None = None, **_: object) -> None:
        if query is not None:
            self.search.setText(query)
            self.filter_chips["all"].setChecked(True)

    def refresh(self) -> None:
        self.load(self.offset)

    def first_page(self) -> None:
        self.load(0)

    def _filter_key(self) -> str:
        for k, b in self.filter_chips.items():
            if b.isChecked():
                return k
        return "all"

    def load(self, offset: int) -> None:
        offset = max(0, offset)
        f = self._filter_key()
        params = dict(q=self.search.text().strip() or None, lead_stage=self.stage.currentData(), consent_status=self.consent.currentData(), archived=self.archived.isChecked(), sort=self.sort.currentData(), desc=self.desc.isChecked(), limit=PAGE, offset=offset)
        if f == "not_called":
            params["lead_stage"] = "new"
        elif f == "interested":
            params["lead_stage"] = "interested"
        elif f == "dnc":
            params["opted_out"] = True
        elif f == "followup":
            params.update(sort="next_followup_at", desc=False, limit=500, offset=0)
        self.run(lambda: self.api.get("/contacts", **params), lambda page: self._show(page, offset, f))

    def _show(self, page: dict, offset: int, f: str) -> None:
        rows = page.get("items", [])
        total = int(page.get("total", 0))
        if f == "followup":
            rows = [r for r in rows if r.get("next_followup_at")]
            total, offset = len(rows), 0
        self.offset, self.total = offset, total
        self.table.set_rows(rows)
        for i, r in enumerate(rows):
            self.table.setCellWidget(i, 4, chip(("opted out" if r.get("opted_out") else r.get("lead_stage", "")).replace("_", " "), "danger" if r.get("opted_out") else STAGE_CHIP.get(r.get("lead_stage", ""), "neutral")))
            acts = QWidget()
            al = QHBoxLayout(acts)
            al.setContentsMargins(4, 0, 4, 0)
            al.setSpacing(4)
            al.addWidget(button("Call", "primary", lambda c=r: self.ctx.navigate("call_queue", contact_id=c["id"]), tooltip="Create a call job for this contact"))
            al.addWidget(button("Open", None, lambda c=r: self.ctx.navigate("contact_detail", contact_id=c["id"])))
            self.table.setCellWidget(i, 9, acts)
            self.table.setRowHeight(i, 40)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(9, 150)
        self.empty.setVisible(not rows)
        self.page_lbl.setText(f"{offset + 1 if rows else 0}–{offset + len(rows)} of {self.total}")
        self.prev_btn.setEnabled(offset > 0)
        self.next_btn.setEnabled(offset + PAGE < self.total and f != "followup")
        self.archive_btn.setText("Unarchive" if self.archived.isChecked() else "Archive")

    def _with_selected(self, fn) -> None:
        row = self.table.selected_row()
        if row is None:
            self.toast("Select a contact first", "warning")
            return
        fn(row)

    def open_selected(self) -> None:
        self._with_selected(lambda c: self.ctx.navigate("contact_detail", contact_id=c["id"]))

    def archive_selected(self) -> None:
        def go(c: dict) -> None:
            if self.archived.isChecked():
                self.run(lambda: self.api.post(f"/contacts/{c['id']}/unarchive"), lambda _: (self.toast("Contact restored"), self.refresh()))
            elif confirm(self, "Archive contact", f"Archive {c['business_name']}? Archived contacts are never called and can be restored from the archived view.", "Archive"):
                self.run(lambda: self.api.delete(f"/contacts/{c['id']}"), lambda _: (self.toast("Contact archived"), self.refresh()))
        self._with_selected(go)

    def new_contact(self) -> None:
        self._run_contact_dialog(ContactDialog(self))

    def _run_contact_dialog(self, dlg: ContactDialog, allow_duplicate: bool = False) -> None:
        if dlg.exec() != ContactDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()

        def created(c: dict) -> None:
            self.toast(f"Created {c['business_name']} ({c['phone_e164']})", "success")
            self.first_page()

        def failed(exc: Exception) -> None:
            if isinstance(exc, ApiError) and exc.code == "duplicate_contact":
                if confirm(self, "Duplicate phone number", f"{exc.error}\n\nCreate it anyway?", "Create duplicate", danger=True):
                    self.run(lambda: self.api.request("POST", "/contacts", json=payload, params={"allow_duplicate": True}), created)
                return
            self.report_error(exc)
            dlg2 = ContactDialog(self, existing={**payload, "phone_raw": payload["phone"]})
            dlg2.show_error(str(exc))
            self._run_contact_dialog(dlg2)

        self.run(lambda: self.api.request("POST", "/contacts", json=payload, params={"allow_duplicate": allow_duplicate} if allow_duplicate else None), created, failed)
