"""Screen 10: Call Console per the mockup. Human-assisted: the OPERATOR speaks the agent line. The state chip always
shows the REAL conversation_state. 'AI Speaking' is never shown in this release (autonomous mode is release-gated)."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter, QTabWidget, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.transcription import TranscriptionThread, microphone_frames
from sellagent_desktop.widgets import DANGER, SUCCESS, TEXT2, Card, DangerBanner, KeyValueGrid as _KVG, FormDialog, TextInputDialog, avatar, badge, button, caption, chip, combo, confirm, datetime_edit, fmt_dt, parse_dt, pretty_json, set_chip, status_label

LIVE_STATES = {"connected", "greeting", "permission_to_continue", "needs_discovery", "product_explanation", "objection_handling", "demo_invitation", "human_handoff", "followup_scheduling"}
PRE_STATES = {"dial_request", "dialing", "ringing"}
SENTI_KIND = {"positive": "success", "neutral": "neutral", "negative": "danger"}
SENTI_COLOR = {"positive": SUCCESS, "negative": DANGER, "neutral": TEXT2}


class SummaryCard(Card):
    """Call Summary (mockup screen 16): deterministic, built by the backend from transcript + outcome."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Call Summary", gold=True, parent=parent)
        self.setObjectName("call_summary")
        self.grid = _KVG()
        self.add(self.grid)
        self.points = QListWidget()
        self.points.setMaximumHeight(110)
        self.add(self.points)
        self.src = caption("")
        self.add(self.src)

    def set_summary(self, sm: dict) -> None:
        nxt = sm.get("next_action") or {}
        secs = sm.get("duration_seconds")
        self.grid.set_rows([
            ("Duration", f"{int(secs) // 60:02d}:{int(secs) % 60:02d}" if secs is not None else "—"),
            ("Result", (sm.get("result") or "not recorded") + (f" — {sm['result_detail']}" if sm.get("result_detail") else "")),
            ("Sentiment", sm.get("sentiment") or "unknown (no prospect lines)"),
            ("Next action", f"{nxt.get('kind')} on {fmt_dt(nxt.get('due_at'))} ({nxt.get('status')})" if nxt else "none scheduled"),
            ("Knowledge used", ", ".join(sm.get("knowledge_used") or []) or "none"),
            ("Turns", f"{(sm.get('turns') or {}).get('prospect', 0)} prospect / {(sm.get('turns') or {}).get('agent', 0)} agent"),
        ])
        self.points.clear()
        for k in sm.get("key_points") or []:
            self.points.addItem("• " + k)
        for n in sm.get("notes") or []:
            self.points.addItem("Note: " + n)
        if self.points.count() == 0:
            self.points.addItem("No key points detected in the transcript")
        self.src.setText(f"source: {sm.get('source', 'backend')}")


class ConsentDialog(QDialog):
    """Live transcription consent: the operator must read the disclosure to the prospect and tick both boxes."""

    def __init__(self, parent: QWidget | None, disclosure: str):
        super().__init__(parent)
        self.setWindowTitle("Live transcription consent")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(caption("Read this to the prospect before starting live transcription:"))
        d = QLabel(f"“{disclosure}”")
        d.setWordWrap(True)
        d.setProperty("role", "agent-line")
        lay.addWidget(d)
        self.read_box = QCheckBox("I read the disclosure to the prospect")
        self.read_box.setObjectName("consent_read")
        self.agree_box = QCheckBox("The prospect agreed to live transcription")
        self.agree_box.setObjectName("consent_agreed")
        lay.addWidget(self.read_box)
        lay.addWidget(self.agree_box)
        lay.addWidget(caption("Audio is processed in memory and not stored; only the text lines are saved to the transcript."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Record consent")
        self.ok.setProperty("role", "primary")
        self.ok.setEnabled(False)
        for b in (self.read_box, self.agree_box):
            b.toggled.connect(lambda _=False: self.ok.setEnabled(self.read_box.isChecked() and self.agree_box.isChecked()))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


STATE_KIND = {"dial_request": "info", "dialing": "info", "ringing": "info", "connected": "success", "completed": "neutral", "no_answer": "warning", "busy": "warning", "technical_failure": "danger", "cancelled": "neutral", "opted_out": "danger"}


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
    key, title = "live_call", "Live call"

    def build(self) -> None:
        self.call_id: str | None = None
        self.call: dict | None = None
        self.outcomes: list[str] = []
        self.stop_banner = DangerBanner("EMERGENCY STOP ACTIVE — conversation steps are refused until it is cleared in Settings.")
        self.root.addWidget(self.stop_banner)
        split = QSplitter(Qt.Orientation.Horizontal)

        # ---- left: queue
        left = QWidget()
        left.setMinimumWidth(230)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        qc = Card("Queue")
        self.picker = QListWidget()
        self.picker.setAccessibleName("Open calls and queued jobs")
        self.picker.setObjectName("call_queue_list")
        self.picker.itemSelectionChanged.connect(self._picked)
        qc.add(self.picker)
        self.queue_note = caption("Open calls are selectable. Queued jobs are dispatched from the Call queue tab.")
        qc.add(self.queue_note)
        qr = QHBoxLayout()
        qr.addWidget(button("Reload", None, self.refresh))
        qr.addWidget(button("Call queue", None, lambda: self.ctx.navigate("call_queue")))
        qw = QWidget()
        qw.setLayout(qr)
        qc.add(qw)
        ll.addWidget(qc, 1)
        split.addWidget(left)

        # ---- centre: live card
        centre = QWidget()
        cl = QVBoxLayout(centre)
        cl.setContentsMargins(0, 0, 0, 0)
        card = Card(gold=True)
        head = QHBoxLayout()
        self.avatar = avatar("")
        head.addWidget(self.avatar)
        nc = QVBoxLayout()
        self.name_lbl = QLabel("No call selected")
        self.name_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.phone_lbl = caption("")
        nc.addWidget(self.name_lbl)
        nc.addWidget(self.phone_lbl)
        head.addLayout(nc, 1)
        sc = QVBoxLayout()
        self.state_lbl = chip("—", "neutral")
        self.state_lbl.setAccessibleName("Conversation state")
        self.state_lbl.setObjectName("state_chip")
        self.mode_chip = chip("Human-assisted: operator speaks", "info")
        self.senti_chip = chip("sentiment: —", "neutral")
        self.senti_chip.setObjectName("call_sentiment_chip")
        self.timer_lbl = QLabel("00:00")
        self.timer_lbl.setProperty("role", "state")
        self.timer_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        for w in (self.state_lbl, self.mode_chip, self.senti_chip):
            sc.addWidget(w, 0, Qt.AlignmentFlag.AlignRight)
        sc.addWidget(self.timer_lbl)
        head.addLayout(sc)
        hw = QWidget()
        hw.setLayout(head)
        card.add(hw)
        self.mode_banner = status_label("HUMAN-ASSISTED MODE: you dial on your phone and YOU speak the agent line below to the prospect. Nothing is spoken automatically.")
        self.mode_banner.setProperty("role", "warning")
        card.add(self.mode_banner)
        self.state_caption = caption("")
        card.add(self.state_caption)
        self.agent_line = QLabel("The next agent line appears here after 'Send / next line' or a prospect utterance.")
        self.agent_line.setProperty("role", "agent-line")
        self.agent_line.setWordWrap(True)
        self.agent_line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.agent_line.setAccessibleName("Agent line to speak")
        card.add(self.agent_line)
        meta = QHBoxLayout()
        self.source_badge = badge("source: —")
        self.guard_badge = badge("guardrail: —")
        self.lang_badge = badge("language: —")
        for b in (self.source_badge, self.guard_badge, self.lang_badge):
            meta.addWidget(b)
        meta.addStretch(1)
        mw = QWidget()
        mw.setLayout(meta)
        card.add(mw)
        inp = QHBoxLayout()
        self.utterance = QLineEdit()
        self.utterance.setPlaceholderText("Type what the prospect said (Hindi / English / Hinglish) and press Enter…")
        self.utterance.setAccessibleName("Prospect utterance")
        self.utterance.returnPressed.connect(self.step)
        inp.addWidget(self.utterance, 1)
        self.language = combo([("auto", "auto"), ("हिन्दी", "hi"), ("English", "en")])
        self.language.setAccessibleName("Language")
        inp.addWidget(self.language)
        self.use_llm = QCheckBox("local LLM")
        self.use_llm.setChecked(True)
        self.use_llm.setToolTip("Unchecked: script-only lines. Checked: the local model may rephrase; guardrails still apply.")
        inp.addWidget(self.use_llm)
        self.step_btn = button("Send / next line", "primary", self.step)
        inp.addWidget(self.step_btn)
        iw = QWidget()
        iw.setLayout(inp)
        card.add(iw)
        ctl = QHBoxLayout()
        self.connected_btn = button("Connected", "success", self.mark_connected, tooltip="The prospect answered")
        self.noans_btn = button("No answer", None, lambda: self.mark_no_answer(False))
        self.busy_btn = button("Busy", None, lambda: self.mark_no_answer(True))
        self.mute_btn = button("Mute", None, None, tooltip="Available on the paired phone")
        self.keypad_btn = button("Keypad", None, None, tooltip="Available on the paired phone")
        self.mute_btn.setEnabled(False)
        self.keypad_btn.setEnabled(False)
        self.outcome_btn = button("Record outcome…", "primary", self.record_outcome)
        self.cancel_btn = button("End call / cancel", "danger", self.cancel_call)
        for b in (self.connected_btn, self.noans_btn, self.busy_btn, self.mute_btn, self.keypad_btn):
            ctl.addWidget(b)
        ctl.addStretch(1)
        ctl.addWidget(self.outcome_btn)
        ctl.addWidget(self.cancel_btn)
        cw = QWidget()
        cw.setLayout(ctl)
        card.add(cw)
        cl.addWidget(card)
        tc = Card("Live transcription (PC microphone) - audio is not stored")
        tc.setObjectName("live_transcription_card")
        tr_row = QHBoxLayout()
        self.tx_btn = button("Start transcription", None, self.toggle_transcription, tooltip="Off by default; needs privacy.allow_live_transcription and the prospect's consent")
        self.tx_btn.setObjectName("transcription_btn")
        self.tx_btn.setProperty("perm", "calls:write")
        tr_row.addWidget(self.tx_btn)
        tr_row.addWidget(caption("Speaker"))
        self.tx_speaker = combo([("prospect", "prospect"), ("operator", "operator")])
        self.tx_speaker.setAccessibleName("Transcription speaker")
        self.tx_speaker.currentIndexChanged.connect(lambda: self.tx_thread and self.tx_thread.set_speaker(self.tx_speaker.currentData()))
        tr_row.addWidget(self.tx_speaker)
        self.mic_chip = chip("mic off", "neutral")
        self.mic_chip.setObjectName("mic_chip")
        tr_row.addWidget(self.mic_chip)
        tr_row.addStretch(1)
        trw = QWidget()
        trw.setLayout(tr_row)
        tc.add(trw)
        self.tx_status = caption("Disabled by default (Settings › privacy.allow_live_transcription). Uses the PC microphone or line-in; audio stays in memory.")
        tc.add(self.tx_status)
        cl.addWidget(tc)
        self.summary_card = SummaryCard()
        self.summary_card.setVisible(False)
        cl.addWidget(self.summary_card)
        cl.addStretch(1)
        split.addWidget(centre)
        self.tx_thread: TranscriptionThread | None = None
        self.frames_source = microphone_frames  # tests inject a synthetic source
        self.line_sentiment: dict[int, str] = {}

        # ---- right: transcript / AI notes / device
        right = QWidget()
        right.setMinimumWidth(320)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.transcript = QListWidget()
        self.transcript.setAccessibleName("Transcript")
        self.tabs.addTab(self.transcript, "Transcript")
        notes = QWidget()
        nl = QVBoxLayout(notes)
        self.refs = caption("knowledge refs: —")
        nl.addWidget(self.refs)
        self.guard_detail = caption("")
        nl.addWidget(self.guard_detail)
        self.llm_metrics = caption("")
        nl.addWidget(self.llm_metrics)
        self.notes_list = QListWidget()
        nl.addWidget(self.notes_list, 1)
        self.note_btn = button("Add note", None, self.add_note)
        nl.addWidget(self.note_btn)
        self.tabs.addTab(notes, "AI notes")
        dev = QWidget()
        dl = QVBoxLayout(dev)
        self.device_events = QListWidget()
        dl.addWidget(self.device_events, 1)
        self.device_note = caption("Device call-state events arrive over the desktop WebSocket for jobs dispatched to a paired Android phone.")
        dl.addWidget(self.device_note)
        self.tabs.addTab(dev, "Device events")
        rl.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setSizes([250, 620, 360])
        split.setChildrenCollapsible(False)
        self.root.addWidget(split, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._enable(False)

    def _enable(self, on: bool) -> None:
        for b in (self.connected_btn, self.noans_btn, self.busy_btn, self.step_btn, self.note_btn, self.outcome_btn, self.cancel_btn, self.utterance):
            b.setEnabled(on)

    def set_context(self, call_id: str | None = None, **_: object) -> None:
        if call_id:
            self.call_id = call_id

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/calls", limit=100), self.api.get("/calls/outcomes"), self.api.get("/settings"), self.api.get("/call-jobs", limit=100)), self._fill_queue)

    def _fill_queue(self, res: tuple) -> None:
        page, outs, settings, jobs = res
        self.outcomes = outs.get("outcomes", [])
        self.ctx.settings_cache.update(settings.get("values", {}))
        self.stop_banner.setVisible(bool(settings.get("values", {}).get("calling.emergency_stop_active")))
        live = [c for c in page.get("items", []) if not c.get("outcome")]
        queued = [j for j in jobs.get("items", []) if j.get("status") in ("queued", "pending")]
        self.picker.blockSignals(True)
        self.picker.clear()
        for c in live:
            it = QListWidgetItem(f"● {c['business_name']}\n   {c['phone_e164']} · {c['conversation_state']} · {fmt_dt(c.get('started_at'))}")
            it.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.picker.addItem(it)
            if c["id"] == self.call_id:
                it.setSelected(True)
        for j in queued:
            it = QListWidgetItem(f"○ {j['phone_e164']} · job {j['status']} · {j['route']}")
            it.setData(Qt.ItemDataRole.UserRole, None)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.picker.addItem(it)
        if self.call_id and self.call_id not in [c["id"] for c in live]:
            it = QListWidgetItem(f"● (selected call) {self.call_id[:8]}…")
            it.setData(Qt.ItemDataRole.UserRole, self.call_id)
            self.picker.insertItem(0, it)
            it.setSelected(True)
        self.picker.blockSignals(False)
        self.queue_note.setText(f"{len(live)} open call(s) · {len(queued)} queued job(s)")
        if self.call_id:
            self.load_call()
        else:
            self._enable(False)
            set_chip(self.state_lbl, "no call selected", "neutral")
            self.state_caption.setText("Dispatch a job from the Call queue tab (manual route) to open a call here." if not live else "Pick an open call in the queue.")

    def _picked(self) -> None:
        items = self.picker.selectedItems()
        cid = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        if cid and cid != self.call_id:
            self.stop_transcription()
            self.call_id = cid
            self.line_sentiment = {}
            self.load_call()

    def load_call(self) -> None:
        cid = self.call_id
        if cid:
            self.run(lambda: (self.api.get(f"/calls/{cid}"), self.api.get(f"/calls/{cid}/summary")), self._show_call_and_summary)

    def _show_call_and_summary(self, res: tuple) -> None:
        d, sm = res
        prospect = [t for t in d.get("transcript", []) if t["speaker"] == "prospect"]
        for t, lab in zip(prospect, sm.get("sentiment_by_turn") or [], strict=False):
            if lab:
                self.line_sentiment.setdefault(t["seq"], lab)
        self.summary = sm
        self._show_call(d)
        overall = sm.get("sentiment")
        set_chip(self.senti_chip, f"sentiment: {overall or '—'}", SENTI_KIND.get(overall or "", "neutral"))
        has_outcome = bool(d["call"].get("outcome"))
        self.summary_card.setVisible(has_outcome)
        if has_outcome:
            self.summary_card.set_summary(sm)

    def _show_call(self, d: dict) -> None:
        self.call = d
        c, job, contact = d["call"], d.get("job") or {}, d.get("contact") or {}
        self.avatar.setText((contact.get("business_name") or "?")[:2].upper())
        self.name_lbl.setText(f"{contact.get('business_name', '?')} · {contact.get('contact_person') or ''}".rstrip(" ·"))
        self.phone_lbl.setText(f"{contact.get('phone_e164')} · {contact.get('city') or ''} · consent {contact.get('consent_status')} · stage {contact.get('lead_stage')} · job {job.get('status')} / {job.get('route')}")
        st = c.get("conversation_state") or "unknown"
        set_chip(self.state_lbl, st.replace("_", " ").upper(), STATE_KIND.get(st, "success" if st in LIVE_STATES else "neutral"))
        live = st in LIVE_STATES
        self.state_caption.setText("Live conversation — type the prospect's words, read the agent line aloud." if live else ("Waiting for the prospect to answer. Press Connected when they do." if st in PRE_STATES else "Call ended — record the outcome if not done."))
        self._enable(True)
        for b in (self.connected_btn, self.noans_btn, self.busy_btn):
            b.setEnabled(st in PRE_STATES)
        self.step_btn.setEnabled(live)
        self.utterance.setEnabled(live)
        self.outcome_btn.setEnabled(not c.get("outcome"))
        self.cancel_btn.setEnabled(not c.get("outcome"))
        auto = job.get("mode") == "autonomous"
        set_chip(self.mode_chip, "Autonomous (release-gated)" if auto else "Human-assisted: operator speaks", "warning" if auto else "info")
        self.mode_banner.setText("AUTONOMOUS MODE: only possible when the release gate is open." if auto else "HUMAN-ASSISTED MODE: you dial on your phone and YOU speak the agent line below to the prospect. Nothing is spoken automatically.")
        self.transcript.clear()
        for t in d.get("transcript", []):
            refs = f"  [{', '.join(t.get('knowledge_refs') or [])}]" if t.get("knowledge_refs") else ""
            senti = self.line_sentiment.get(t["seq"]) if t["speaker"] == "prospect" else None
            item = QListWidgetItem(f"{t['speaker'].upper():9s} ({t.get('source')}): {t['text']}{refs}" + (f"   [{senti}]" if senti else ""))
            if senti:
                item.setForeground(QColor(SENTI_COLOR.get(senti, TEXT2)))
                item.setData(Qt.ItemDataRole.UserRole, senti)
            self.transcript.addItem(item)
        self.transcript.scrollToBottom()
        self.notes_list.clear()
        for n in d.get("notes", []):
            self.notes_list.addItem(f"{fmt_dt(n.get('created_at'), True)} {n.get('author')}: {n['body']}")
        self.device_events.clear()
        for ev in d.get("events", []):
            if str(ev.get("event_type", "")).startswith("device."):
                self.device_events.addItem(f"{fmt_dt(ev.get('occurred_at'), True)} {ev['event_type']} → {ev.get('to_state')} {pretty_json(ev.get('data')) if ev.get('data') else ''}")
        last_agent = [t for t in d.get("transcript", []) if t["speaker"] == "agent"]
        if last_agent:
            self.agent_line.setText(last_agent[-1]["text"])
        self._tick()

    def _tick(self) -> None:
        c = (self.call or {}).get("call") or {}
        start = parse_dt(c.get("connected_at") or c.get("started_at"))
        end = parse_dt(c.get("ended_at"))
        if not start:
            self.timer_lbl.setText("00:00")
            return
        secs = int(((end or datetime.now(UTC)) - start).total_seconds())
        self.timer_lbl.setText(f"{secs // 60:02d}:{secs % 60:02d}")

    # ------------------------------------------------------------------ actions
    def mark_connected(self) -> None:
        cid = self.call_id
        self.run(lambda: self.api.post(f"/calls/{cid}/connected"), lambda _: (self.toast("Marked connected; press 'Send / next line' for the greeting.", "success"), self.load_call()))

    def mark_no_answer(self, busy: bool) -> None:
        cid = self.call_id
        self.run(lambda: self.api.post(f"/calls/{cid}/no-answer", params={"busy": busy}), lambda r: (self.toast(f"Outcome recorded: {r.get('outcome')}", "success"), self.refresh()))

    def step(self) -> None:
        cid = self.call_id
        if not cid:
            return
        body = {"utterance": self.utterance.text().strip() or None, "language": self.language.currentData(), "use_llm": self.use_llm.isChecked()}
        self.utterance.clear()
        self.run(lambda: self.api.post(f"/calls/{cid}/step", body, timeout=90), self._stepped, busy_text="Thinking…")

    def _stepped(self, r: dict) -> None:
        if r.get("sentiment"):
            self.toast(f"Prospect sentiment: {r['sentiment']} · call overall: {r.get('call_sentiment') or '—'}", "info")
        if r.get("call_sentiment"):
            set_chip(self.senti_chip, f"sentiment: {r['call_sentiment']}", SENTI_KIND.get(r["call_sentiment"], "neutral"))
        self.agent_line.setText(r.get("agent_text") or "(no agent line for this state)")
        self.source_badge.setText(f"source: {r.get('source')}")
        self.source_badge.setProperty("role", "badge-mock" if r.get("source") == "llm" else "pill-gold")
        self.source_badge.style().unpolish(self.source_badge)
        self.source_badge.style().polish(self.source_badge)
        g = r.get("guardrail") or {}
        self.guard_badge.setText(f"guardrail: {'pass' if g.get('ok', g.get('passed', True)) else 'BLOCKED'}" if g else "guardrail: script (n/a)")
        self.guard_detail.setText(("guardrail: " + pretty_json(g)) if g else "")
        self.lang_badge.setText(f"language: {r.get('language')}")
        self.refs.setText("knowledge refs: " + (", ".join(r.get("knowledge_refs") or []) or "none (no approved fact injected)"))
        llm = r.get("llm") or {}
        self.llm_metrics.setText(f"LLM {llm.get('model')}: first token {llm.get('first_token_ms')} ms · total {llm.get('total_ms')} ms · {llm.get('tokens_per_second')} tok/s" if llm else "LLM: not used for this line (script source)")
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
        self.run(lambda: self.api.post(f"/calls/{cid}/outcome", body), lambda r: (self.toast(f"Outcome {r.get('outcome')} saved; lead stage {r.get('lead_stage')}" + (f"; follow-up {r.get('followup_id')}" if r.get("followup_id") else ""), "success"), self.refresh()))

    def cancel_call(self) -> None:
        cid = self.call_id
        if cid and confirm(self, "End call", "End this call and cancel its job? Record an outcome instead if the conversation happened.", "End call", danger=True):
            self.run(lambda: self.api.post(f"/calls/{cid}/cancel", {"reason": "operator_cancel"}), lambda _: self.refresh())

    # ------------------------------------------------------------------ live transcription
    def toggle_transcription(self) -> None:
        if self.tx_thread is not None:
            self.stop_transcription()
            return
        if not self.call_id or not self.call:
            self.toast("Select a live call first", "warning")
            return
        if self.call["call"].get("conversation_state") not in LIVE_STATES:
            self.toast("Transcription works only while the call is live (press Connected first)", "warning")
            return
        self.run(lambda: self.api.get("/settings"), self._tx_check_settings)

    def _tx_check_settings(self, s: dict) -> None:
        vals = s.get("values", {})
        if not vals.get("privacy.allow_live_transcription"):
            self.tx_status.setText("Live transcription is OFF in Settings › Privacy (privacy.allow_live_transcription). An admin must enable it first.")
            self.tx_status.setProperty("role", "warning")
            self.tx_status.style().unpolish(self.tx_status)
            self.tx_status.style().polish(self.tx_status)
            self.toast("Live transcription is disabled in privacy settings", "warning")
            return
        dlg = ConsentDialog(self, str(vals.get("privacy.recording_disclosure_text") or ""))
        if not self.confirm_consent(dlg):
            return
        cid = self.call_id
        self.run(lambda: self.api.post(f"/calls/{cid}/transcription-consent", {"prospect_consented": True, "disclosure_text_read": True}), lambda _: self.start_transcription())

    def confirm_consent(self, dlg: ConsentDialog) -> bool:
        """Separated so tests can tick the boxes; returns True when consent was confirmed."""
        return dlg.exec() == QDialog.DialogCode.Accepted and dlg.read_box.isChecked() and dlg.agree_box.isChecked()

    def start_transcription(self) -> None:
        url = self.api.ws_url("/api/v1/ws/transcribe", call_id=self.call_id or "", language=self.language.currentData() or "auto", speaker=self.tx_speaker.currentData() or "prospect")
        self.tx_thread = TranscriptionThread(url, self.frames_source)
        self.tx_thread.message.connect(self._tx_message)
        self.tx_thread.status.connect(lambda st: self.tx_status.setText(f"Live transcription: {st}"))
        self.tx_thread.finished_ok.connect(self._tx_finished)
        self.tx_btn.setText("Stop transcription")
        self.tx_error = None
        set_chip(self.mic_chip, "mic: connecting", "info")
        self.tx_thread.start()

    def stop_transcription(self) -> None:
        if self.tx_thread is not None:
            self.tx_thread.stop()

    def _tx_finished(self) -> None:
        if self.tx_thread is not None:
            self.tx_thread.wait(2000)
        self.tx_thread = None
        self.tx_btn.setText("Start transcription")
        # keep an error visible so the operator can see WHY transcription stopped (e.g. speech model not installed)
        if getattr(self, "tx_error", None):
            set_chip(self.mic_chip, "mic: error", "danger")
        else:
            set_chip(self.mic_chip, "mic off", "neutral")
        if self.call_id:
            self.load_call()

    def _tx_message(self, m: dict) -> None:
        t = m.get("type")
        if t == "ready":
            set_chip(self.mic_chip, "mic: listening", "success")
            self.tx_status.setText(f"Listening (model {m.get('model')}, {m.get('sample_rate')} Hz, audio stored: {'yes' if m.get('audio_stored') else 'no'})")
        elif t == "vad":
            set_chip(self.mic_chip, "mic: speech" if m.get("speech") else "mic: listening", "warning" if m.get("speech") else "success")
        elif t == "final":
            if m.get("sentiment") and m.get("seq") is not None:
                self.line_sentiment[int(m["seq"])] = m["sentiment"]
            item = QListWidgetItem(f"{(self.tx_speaker.currentData() or 'prospect').upper():9s} (stt): {m.get('text')}" + (f"   [{m['sentiment']}]" if m.get("sentiment") else ""))
            if m.get("sentiment"):
                item.setForeground(QColor(SENTI_COLOR.get(m["sentiment"], TEXT2)))
            self.transcript.addItem(item)
            self.transcript.scrollToBottom()
        elif t == "error":
            self.tx_error = m.get("code") or "error"
            set_chip(self.mic_chip, "mic: error", "danger")
            self.tx_status.setText(f"Transcription stopped: {m.get('error')} [{m.get('code')}]")
            self.tx_status.setProperty("role", "danger")
            self.tx_status.style().unpolish(self.tx_status)
            self.tx_status.style().polish(self.tx_status)
            self.toast(f"Live transcription: {m.get('error')}", "error")

    def on_ws_event(self, env: dict) -> None:
        t = env.get("type")
        if t == "call.state":
            p = env.get("payload") or {}
            if self.call and (self.call.get("job") or {}).get("id") == p.get("call_job_id"):
                self.device_events.addItem(f"{fmt_dt(p.get('occurred_at'), True)} device → {p.get('state')} route={p.get('audio_route')} cause={p.get('disconnect_cause') or ''}")
                self.load_call()
        elif t == "safety.emergency_stop":
            self.stop_banner.setVisible(True)
            if self.call_id:
                self.load_call()
