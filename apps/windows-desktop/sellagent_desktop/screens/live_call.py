"""Screen 10: live call console. Human-assisted: the OPERATOR speaks the agent line. Android route shows device call.state events."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DangerBanner, FormDialog, KeyValueGrid, TextInputDialog, badge, button, caption, combo, confirm, datetime_edit, fmt_dt, mock_badge, pretty_json, status_label

LIVE_STATES = {"connected", "greeting", "permission_to_continue", "needs_discovery", "product_explanation", "objection_handling", "demo_invitation", "human_handoff", "followup_scheduling"}
PRE_STATES = {"dial_request", "dialing", "ringing"}


class OutcomeDialog(FormDialog):
    def __init__(self, parent: QWidget | None, outcomes: list[str]):
        super().__init__(parent, "Record call outcome", "Save outcome")
        self.add_field("outcome", "Outcome", combo([(o, o) for o in outcomes]), required=True)
        self.add_field("detail", "Detail", QLineEdit())
        self.sched = QCheckBox("Schedule a follow-up")
        self.add_field("schedule", "Follow-up", self.sched)
        self.add_field("followup_at", "Follow-up due", datetime_edit())
        self.add_field("followup_kind", "Follow-up kind", combo([(k, k) for k in ("call", "demo", "email", "human_handoff")]))
        n = QPlainTextEdit()
        n.setMaximumHeight(70)
        self.add_field("note", "Note", n)

    def payload(self) -> dict:
        v = self.values()
        body = {"outcome": v["outcome"], "detail": v["detail"] or None, "note": v["note"] or None, "followup_kind": v["followup_kind"]}
        if v["schedule"]:
            body["followup_at"] = v["followup_at"]
        return body


class LiveCallScreen(BaseScreen):
    key, title = "live_call", "Live call console"

    def build(self) -> None:
        self.call_id: str | None = None
        self.call: dict | None = None
        self.outcomes: list[str] = []
        top = QHBoxLayout()
        top.addWidget(QLabel("Active call"))
        self.picker = QComboBox()
        self.picker.setMinimumWidth(360)
        self.picker.setAccessibleName("Active call picker")
        self.picker.currentIndexChanged.connect(self._picked)
        top.addWidget(self.picker, 1)
        top.addWidget(button("Reload", None, self.refresh))
        top.addWidget(button("Go to call queue", None, lambda: self.ctx.navigate("call_queue")))
        self.root.addLayout(top)
        self.mode_banner = status_label("HUMAN-ASSISTED MODE: you dial and YOU speak the agent line shown below to the prospect. Nothing is spoken automatically.")
        self.mode_banner.setProperty("role", "warning")
        self.root.addWidget(self.mode_banner)
        self.stop_banner = DangerBanner("EMERGENCY STOP ACTIVE — all jobs cancelled; conversation steps are refused until cleared in Settings.")
        self.root.addWidget(self.stop_banner)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        cc = Card("Prospect", gold=True)
        self.contact_grid = KeyValueGrid()
        cc.add(self.contact_grid)
        ll.addWidget(cc)
        sc = Card("Conversation state")
        self.state_lbl = QLabel("—")
        self.state_lbl.setProperty("role", "state")
        self.state_lbl.setAccessibleName("Conversation state")
        sc.add(self.state_lbl)
        self.state_caption = caption("")
        sc.add(self.state_caption)
        row = QHBoxLayout()
        self.connected_btn = button("Connected (answered)", "primary", self.mark_connected)
        self.noans_btn = button("No answer", None, lambda: self.mark_no_answer(False))
        self.busy_btn = button("Busy", None, lambda: self.mark_no_answer(True))
        for b in (self.connected_btn, self.noans_btn, self.busy_btn):
            row.addWidget(b)
        rw = QWidget()
        rw.setLayout(row)
        sc.add(rw)
        ll.addWidget(sc)
        dc = Card("Device call events (android_companion route)")
        self.device_events = QListWidget()
        self.device_events.setMaximumHeight(120)
        dc.add(self.device_events)
        self.device_note = caption("Only shown for jobs dispatched to a paired Android phone; events arrive over the desktop WebSocket.")
        dc.add(self.device_note)
        ll.addWidget(dc)
        ll.addStretch(1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.agent_line = QLabel("Agent line will appear here after 'Next line' or a prospect utterance.")
        self.agent_line.setProperty("role", "agent-line")
        self.agent_line.setWordWrap(True)
        self.agent_line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.agent_line.setAccessibleName("Agent line to speak")
        rl.addWidget(self.agent_line)
        meta = QHBoxLayout()
        self.source_badge = badge("source: —")
        self.guard_badge = badge("guardrail: —")
        self.lang_badge = badge("language: —")
        for b in (self.source_badge, self.guard_badge, self.lang_badge):
            meta.addWidget(b)
        meta.addStretch(1)
        rl.addLayout(meta)
        self.refs = caption("knowledge refs: —")
        rl.addWidget(self.refs)
        self.guard_detail = caption("")
        rl.addWidget(self.guard_detail)
        rl.addWidget(QLabel("Transcript"))
        self.transcript = QListWidget()
        self.transcript.setAccessibleName("Transcript")
        rl.addWidget(self.transcript, 1)
        inp = QHBoxLayout()
        self.utterance = QLineEdit()
        self.utterance.setPlaceholderText("Type what the prospect said (Hindi/English/Hinglish) and press Enter…")
        self.utterance.setAccessibleName("Prospect utterance")
        self.utterance.returnPressed.connect(self.step)
        inp.addWidget(self.utterance, 1)
        self.language = combo([("auto", "auto"), ("हिन्दी", "hi"), ("English", "en")])
        self.language.setAccessibleName("Language")
        inp.addWidget(self.language)
        self.use_llm = QCheckBox("use local LLM")
        self.use_llm.setChecked(True)
        self.use_llm.setToolTip("Unchecked: script-only responses. Checked: the local model may rephrase; guardrails still apply.")
        inp.addWidget(self.use_llm)
        self.step_btn = button("Send / next line", "primary", self.step)
        inp.addWidget(self.step_btn)
        rl.addLayout(inp)
        act = QHBoxLayout()
        self.note_btn = button("Add note", None, self.add_note)
        self.outcome_btn = button("Record outcome…", "primary", self.record_outcome)
        self.cancel_btn = button("Cancel call", "danger", self.cancel_call)
        for b in (self.note_btn, self.outcome_btn, self.cancel_btn):
            act.addWidget(b)
        act.addStretch(1)
        rl.addLayout(act)
        split.addWidget(right)
        split.setSizes([420, 700])
        self.root.addWidget(split, 1)
        self._enable(False)

    def _enable(self, on: bool) -> None:
        for b in (self.connected_btn, self.noans_btn, self.busy_btn, self.step_btn, self.note_btn, self.outcome_btn, self.cancel_btn, self.utterance):
            b.setEnabled(on)

    def set_context(self, call_id: str | None = None, **_: object) -> None:
        if call_id:
            self.call_id = call_id

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/calls", limit=100), self.api.get("/calls/outcomes"), self.api.get("/settings")), self._fill_picker)

    def _fill_picker(self, res: tuple) -> None:
        page, outs, settings = res
        self.outcomes = outs.get("outcomes", [])
        self.ctx.settings_cache.update(settings.get("values", {}))
        self.stop_banner.setVisible(bool(settings.get("values", {}).get("calling.emergency_stop_active")))
        live = [c for c in page.get("items", []) if not c.get("outcome")]
        self.picker.blockSignals(True)
        self.picker.clear()
        self.picker.addItem("— select an open call —", None)
        for c in live:
            self.picker.addItem(f"{c['business_name']} · {c['phone_e164']} · {c['conversation_state']} · {fmt_dt(c.get('started_at'))}", c["id"])
        if self.call_id:
            i = self.picker.findData(self.call_id)
            if i >= 0:
                self.picker.setCurrentIndex(i)
            else:
                self.picker.addItem(f"(selected) {self.call_id}", self.call_id)
                self.picker.setCurrentIndex(self.picker.count() - 1)
        self.picker.blockSignals(False)
        if self.call_id:
            self.load_call()
        else:
            self._enable(False)
            self.state_lbl.setText("no call selected")
            self.state_caption.setText("Dispatch a job from the call queue (manual route) to open a call here." if not live else "Pick an open call above.")

    def _picked(self) -> None:
        cid = self.picker.currentData()
        if cid and cid != self.call_id:
            self.call_id = cid
            self.load_call()

    def load_call(self) -> None:
        cid = self.call_id
        if not cid:
            return
        self.run(lambda: self.api.get(f"/calls/{cid}"), self._show_call)

    def _show_call(self, d: dict) -> None:
        self.call = d
        c, job, contact = d["call"], d.get("job") or {}, d.get("contact") or {}
        self.contact_grid.set_rows([("business", contact.get("business_name")), ("person", contact.get("contact_person")), ("phone", contact.get("phone_e164")), ("city", contact.get("city")), ("consent", contact.get("consent_status")), ("stage", contact.get("lead_stage")), ("job", f"{job.get('status')} · {job.get('mode')} · {job.get('route')}"), ("call id", c["id"])])
        st = c.get("conversation_state") or "unknown"
        self.state_lbl.setText(st.replace("_", " ").upper())
        live = st in LIVE_STATES
        self.state_caption.setText("Live conversation — type the prospect's words, read the agent line aloud." if live else ("Waiting for the prospect to answer. Press Connected when they do." if st in PRE_STATES else "Call ended — record the outcome if not done."))
        self._enable(True)
        self.connected_btn.setEnabled(st in PRE_STATES)
        self.noans_btn.setEnabled(st in PRE_STATES)
        self.busy_btn.setEnabled(st in PRE_STATES)
        self.step_btn.setEnabled(live)
        self.utterance.setEnabled(live)
        self.outcome_btn.setEnabled(not c.get("outcome"))
        self.cancel_btn.setEnabled(not c.get("outcome"))
        self.mode_banner.setText("HUMAN-ASSISTED MODE: you dial and YOU speak the agent line shown below to the prospect. Nothing is spoken automatically." if job.get("mode") != "autonomous" else "AUTONOMOUS MODE (release gate must be open).")
        self.transcript.clear()
        for t in d.get("transcript", []):
            refs = f"  [{', '.join(t.get('knowledge_refs') or [])}]" if t.get("knowledge_refs") else ""
            self.transcript.addItem(f"{t['speaker'].upper():9s} ({t.get('source')}): {t['text']}{refs}")
        for n in d.get("notes", []):
            self.transcript.addItem(f"NOTE      ({n.get('author')}): {n['body']}")
        self.transcript.scrollToBottom()
        self.device_events.clear()
        for ev in d.get("events", []):
            if str(ev.get("event_type", "")).startswith("device."):
                self.device_events.addItem(f"{fmt_dt(ev.get('occurred_at'), True)} {ev['event_type']} → {ev.get('to_state')} {pretty_json(ev.get('data')) if ev.get('data') else ''}")
        self.device_note.setVisible(job.get("route") == "android_companion" or self.device_events.count() == 0)
        last_agent = [t for t in d.get("transcript", []) if t["speaker"] == "agent"]
        if last_agent:
            self.agent_line.setText(last_agent[-1]["text"])

    # ------------------------------------------------------------------ actions
    def mark_connected(self) -> None:
        cid = self.call_id
        self.run(lambda: self.api.post(f"/calls/{cid}/connected"), lambda _: (self.toast("Marked connected; press 'Send / next line' for the greeting.", "success"), self.load_call()))

    def mark_no_answer(self, busy: bool) -> None:
        cid = self.call_id
        self.run(lambda: self.api.post(f"/calls/{cid}/no-answer", params={"busy": busy}), lambda r: (self.toast(f"Outcome recorded: {r.get('outcome')}", "success"), self.load_call()))

    def step(self) -> None:
        cid = self.call_id
        if not cid:
            return
        body = {"utterance": self.utterance.text().strip() or None, "language": self.language.currentData(), "use_llm": self.use_llm.isChecked()}
        self.utterance.clear()
        self.run(lambda: self.api.post(f"/calls/{cid}/step", body, timeout=90), self._stepped, busy_text="Thinking…")

    def _stepped(self, r: dict) -> None:
        self.agent_line.setText(r.get("agent_text") or "(no agent line for this state)")
        self.source_badge.setText(f"source: {r.get('source')}")
        self.source_badge.setProperty("role", "badge-mock" if r.get("source") == "llm" else "pill-gold")
        self.source_badge.style().unpolish(self.source_badge)
        self.source_badge.style().polish(self.source_badge)
        g = r.get("guardrail") or {}
        self.guard_badge.setText(f"guardrail: {'pass' if g.get('ok', g.get('passed', True)) else 'BLOCKED'}" if g else "guardrail: script (n/a)")
        self.guard_detail.setText(pretty_json(g) if g else "")
        self.lang_badge.setText(f"language: {r.get('language')}")
        self.refs.setText("knowledge refs: " + (", ".join(r.get("knowledge_refs") or []) or "none (no approved fact injected)"))
        llm = r.get("llm") or {}
        if llm:
            self.toast(f"LLM {llm.get('model')}: first token {llm.get('first_token_ms')} ms, total {llm.get('total_ms')} ms", "info")
        if r.get("terminal"):
            self.toast(f"Conversation reached terminal state {r.get('state')} (outcome {r.get('outcome')})", "warning")
        self.load_call()

    def add_note(self) -> None:
        cid = self.call_id
        dlg = TextInputDialog(self, "Add note", "Note", multiline=True)
        if cid and dlg.exec() == TextInputDialog.DialogCode.Accepted:
            body = dlg.value().strip()
            self.run(lambda: self.api.post(f"/calls/{cid}/notes", {"body": body}), lambda _: self.load_call())

    def record_outcome(self) -> None:
        cid = self.call_id
        if not cid:
            return
        dlg = OutcomeDialog(self, self.outcomes or ["completed"])
        if dlg.exec() != OutcomeDialog.DialogCode.Accepted:
            return
        body = dlg.payload()
        self.run(lambda: self.api.post(f"/calls/{cid}/outcome", body), lambda r: (self.toast(f"Outcome {r.get('outcome')} saved; lead stage {r.get('lead_stage')}" + (f"; follow-up {r.get('followup_id')}" if r.get("followup_id") else ""), "success"), self.load_call()))

    def cancel_call(self) -> None:
        cid = self.call_id
        if cid and confirm(self, "Cancel call", "Cancel this live call and its job?", "Cancel call", danger=True):
            self.run(lambda: self.api.post(f"/calls/{cid}/cancel", {"reason": "operator_cancel"}), lambda _: self.load_call())

    def on_ws_event(self, env: dict) -> None:
        t = env.get("type")
        if t == "call.state":
            p = env.get("payload") or {}
            if self.call and self.call.get("job", {}).get("id") == p.get("call_job_id"):
                self.device_events.addItem(f"{fmt_dt(p.get('occurred_at'), True)} device → {p.get('state')} route={p.get('audio_route')} cause={p.get('disconnect_cause') or ''}")
                self.load_call()
        elif t == "safety.emergency_stop":
            self.stop_banner.setVisible(True)
            if self.call_id:
                self.load_call()
