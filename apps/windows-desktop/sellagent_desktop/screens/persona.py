"""AI sales persona: name, voice, language, pacing, style, greeting/closing, objectives, interruption and hand-off
behaviour, memory. Preview the voice and rehearse a typed conversation (SIMULATION, no phone).

Persona settings change wording and voice only. They cannot override approved facts, guardrails, consent, opt-out,
privacy controls or the emergency stop - those are enforced by the backend whatever is configured here."""

from __future__ import annotations

import base64
from typing import Any

from PySide6.QtWidgets import QCheckBox, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QPlainTextEdit, QSpinBox, QWidget

from sellagent_desktop.audio import play_wav_bytes
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, button, caption, combo

TEXT_KEYS = ("persona.name", "persona.greeting_en", "persona.greeting_hi", "persona.closing_en", "persona.closing_hi", "persona.objectives")
CHOICES = {
    "persona.gender": [("Female", "female"), ("Male", "male")],
    "persona.style": [("Warm & friendly", "warm"), ("Concise", "concise"), ("Formal", "formal")],
    "persona.response_length": [("Short replies", "short"), ("Normal replies", "normal")],
    "persona.default_language": [("Follow the caller (auto)", "auto"), ("हिन्दी", "hi"), ("English", "en")],
    "persona.handoff": [("Arrange a human call back", "callback"), ("Hand the live call to the operator", "operator")],
}
INTS = {"persona.memory_turns": (2, 30), "persona.pause_ms": (0, 1500), "persona.volume_percent": (20, 150), "ai.tts_speed_percent": (50, 200)}
BOOLS = ("persona.enabled", "persona.language_switching", "persona.barge_in")
LABELS = {
    "persona.enabled": "Use the persona", "persona.name": "Persona name", "persona.gender": "Hindi grammatical gender", "persona.style": "Conversation style",
    "persona.response_length": "Response length", "persona.default_language": "Default language", "persona.language_switching": "Switch Hindi/English with the caller",
    "persona.voice_en": "English voice (Piper)", "persona.voice_hi": "Hindi voice (Piper)", "ai.tts_speed_percent": "Speaking speed %", "persona.pause_ms": "Pause after each sentence (ms)",
    "persona.volume_percent": "Volume %", "persona.barge_in": "Stop speaking when the caller interrupts", "persona.handoff": "When the caller asks for a person",
    "persona.memory_turns": "Conversation memory (turns)", "persona.greeting_en": "Greeting (English, optional)", "persona.greeting_hi": "Greeting (Hindi, optional)",
    "persona.closing_en": "Closing (English, optional)", "persona.closing_hi": "Closing (Hindi, optional)", "persona.objectives": "Sales objectives",
}


class PersonaScreen(BaseScreen):
    key, title = "persona", "AI sales persona"

    def build(self) -> None:
        self.values: dict[str, Any] = {}
        self.editors: dict[str, QWidget] = {}
        self.sim_session = "new"
        self.root.addWidget(caption(
            "Shapes how the AI assistant sounds and phrases things. It always introduces itself as an AI, never claims to be human, and can only "
            "state approved FITRON facts. Consent, opt-out, privacy and the emergency stop cannot be changed here. Greetings may use {name}, "
            "{contact_person} and {business_name}; an AI disclosure is added automatically if missing."
        ))
        form_card = Card("Persona")
        form = QFormLayout()
        for key in BOOLS[:1] + ("persona.name", "persona.gender", "persona.style", "persona.response_length", "persona.default_language", "persona.language_switching",
                                 "persona.voice_en", "persona.voice_hi", "ai.tts_speed_percent", "persona.pause_ms", "persona.volume_percent", "persona.barge_in",
                                 "persona.handoff", "persona.memory_turns", "persona.greeting_en", "persona.greeting_hi", "persona.closing_en", "persona.closing_hi", "persona.objectives"):
            if key in BOOLS:
                w: QWidget = QCheckBox()
            elif key in CHOICES:
                w = combo(CHOICES[key])
            elif key in INTS:
                w = QSpinBox()
                w.setRange(*INTS[key])
            elif key in ("persona.voice_en", "persona.voice_hi"):
                w = combo([("(use the Local AI voice)", "")])
                w.setEditable(True)
            elif key == "persona.objectives":
                w = QPlainTextEdit()
                w.setFixedHeight(64)
            else:
                w = QLineEdit()
                w.setMaxLength(500 if key != "persona.name" else 40)
            w.setAccessibleName(LABELS[key])
            self.editors[key] = w
            form.addRow(LABELS[key], w)
        fw = QWidget()
        fw.setLayout(form)
        form_card.add(fw)
        bar = QHBoxLayout()
        self.save_btn = button("Save persona", "primary", self.save)
        self.save_btn.setProperty("perm", "settings:write")
        self.preview_btn = button("Preview voice", None, self.preview, tooltip="Speaks the greeting with the selected voice on this PC (needs Piper and a voice model)")
        bar.addWidget(self.save_btn)
        bar.addWidget(self.preview_btn)
        bar.addStretch(1)
        bw = QWidget()
        bw.setLayout(bar)
        form_card.add(bw)
        self.status = caption("")
        form_card.add(self.status)
        self.root.addWidget(form_card)

        sim = Card("Rehearse a conversation (SIMULATION - typed text, no phone, no contact record)")
        row = QHBoxLayout()
        self.sim_input = QLineEdit()
        self.sim_input.setPlaceholderText("Type what a gym owner might say, e.g. 'abhi busy hoon' or 'we use Excel'")
        self.sim_input.returnPressed.connect(self.sim_send)
        self.sim_lang = combo([("auto", "auto"), ("हिन्दी", "hi"), ("English", "en")])
        row.addWidget(self.sim_input, 1)
        row.addWidget(self.sim_lang)
        row.addWidget(button("Send", None, self.sim_send))
        row.addWidget(button("Restart", None, self.sim_restart))
        rw = QWidget()
        rw.setLayout(row)
        sim.add(rw)
        self.sim_log = QListWidget()
        self.sim_log.setMinimumHeight(160)
        sim.add(self.sim_log)
        self.root.addWidget(sim, 1)

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/settings"), self.api.get("/speech/status")), self._show)

    def _show(self, res: tuple) -> None:
        s, speech = res
        self.values = s.get("values", {})
        voices = [v["name"] for v in (speech.get("tts") or {}).get("voices", [])]
        for key in ("persona.voice_en", "persona.voice_hi"):
            w = self.editors[key]
            w.blockSignals(True)
            w.clear()
            w.addItem("(use the Local AI voice)", "")
            for v in voices:
                w.addItem(v, v)
            w.blockSignals(False)
        for key, w in self.editors.items():
            v = self.values.get(key)
            if isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, QSpinBox):
                w.setValue(int(v or 0))
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(str(v or ""))
            elif isinstance(w, QLineEdit):
                w.setText(str(v or ""))
            else:
                i = w.findData(v or "")
                if i < 0 and v:
                    w.addItem(str(v), v)
                    i = w.count() - 1
                w.setCurrentIndex(max(0, i))
        hi_voice = self.values.get("persona.voice_hi") or self.values.get("ai.piper_voice_hi")
        self.status.setText("Voices found: " + (", ".join(voices) if voices else "none (install Piper voices, see models/README.md)")
                            + ("" if hi_voice else ". No Hindi voice set: Hindi replies cannot be spoken until one is chosen."))

    def _value(self, key: str) -> Any:
        w = self.editors[key]
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QSpinBox):
            return w.value()
        if isinstance(w, QPlainTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        data = w.currentData()
        return data if data is not None else w.currentText().strip()

    def save(self) -> None:
        changes = {k: self._value(k) for k in self.editors if self._value(k) != self.values.get(k)}
        if not changes:
            self.toast("Nothing changed", "info")
            return
        self.run(lambda: self.api.patch("/settings", {"values": changes}), lambda r: (self.toast(f"Saved {len(r.get('applied', {}))} persona setting(s)", "success"), self.refresh()))

    def preview(self) -> None:
        lang = self._value("persona.default_language")
        lang = lang if lang in ("hi", "en") else "en"
        name = self._value("persona.name") or "Priya"
        text = (f"नमस्ते, मैं {name}, FITRON की AI सहायक बोल रही हूँ।" if lang == "hi" else f"Namaste, I'm {name}, an AI assistant calling on behalf of FITRON.")
        self.run(lambda: self.api.post("/speech/tts", {"text": text, "language": lang}), self._play)

    def _play(self, r: dict) -> None:
        how = play_wav_bytes(base64.b64decode(r["wav_base64"]))
        self.status.setText(f"Voice {r.get('voice')}: {r.get('duration_s', 0):.1f} s of audio generated in {r.get('latency_ms', 0):.0f} ms ({how}).")

    # ------------------------------------------------------------------ rehearsal
    def sim_restart(self) -> None:
        self.sim_session = "new"
        self.sim_log.clear()

    def sim_send(self) -> None:
        text = self.sim_input.text().strip()
        sid = self.sim_session
        if self.sim_session == "new":
            self.sim_log.addItem("— SIMULATION started —")
        if text:
            self.sim_log.addItem(f"GYM OWNER: {text}")
        self.sim_input.clear()
        self.run(lambda: self.api.post(f"/ai/simulate/{sid}", {"utterance": text or None, "language": self.sim_lang.currentData() or "auto", "use_llm": False}), self._sim_reply)

    def _sim_reply(self, r: dict) -> None:
        self.sim_session = r.get("session_id", "new")
        cues = f"   [cues: {', '.join(r['cues'])}]" if r.get("cues") else ""
        self.sim_log.addItem(f"{(r.get('persona') or 'AI').upper()} ({r.get('state')}): {r.get('agent_text')}{cues}")
        if r.get("terminal"):
            self.sim_log.addItem(f"— conversation ended: {r.get('outcome')} —")
            self.sim_session = "new"
        self.sim_log.scrollToBottom()
