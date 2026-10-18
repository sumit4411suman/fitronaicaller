"""Screen 12: local AI conversation & speech diagnostics. Everything here is a PC-local test or a SIMULATION."""

from __future__ import annotations

import base64

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QSpinBox, QTabWidget, QVBoxLayout, QWidget

from sellagent_desktop import audio
from sellagent_desktop.api_client import LONG_TIMEOUT
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, KeyValueGrid, badge, button, caption, combo, mock_badge, pretty_json, status_label


class DiagnosticsScreen(BaseScreen):
    key, title = "diagnostics", "Local AI & speech diagnostics"

    def build(self) -> None:
        hdr = QHBoxLayout()
        hdr.addWidget(mock_badge("DIAGNOSTIC / SIMULATION"))
        hdr.addWidget(caption("Nothing on this screen places a call or touches phone audio. Metrics are measured on this PC only."))
        hdr.addStretch(1)
        self.root.addLayout(hdr)
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)
        self.sim_session = "new"

        # --- chat test
        chat = QWidget()
        cl = QVBoxLayout(chat)
        row = QHBoxLayout()
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("Prompt for the local model (Hindi or English)…")
        self.prompt.setAccessibleName("Chat test prompt")
        self.prompt.returnPressed.connect(self.chat_test)
        row.addWidget(self.prompt, 1)
        self.chat_lang = combo([("auto", "auto"), ("हिन्दी", "hi"), ("English", "en")])
        row.addWidget(self.chat_lang)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(1, 1024)
        self.max_tokens.setValue(128)
        self.max_tokens.setPrefix("max tokens ")
        row.addWidget(self.max_tokens)
        row.addWidget(button("Run chat test", "primary", self.chat_test))
        cl.addLayout(row)
        self.chat_out = QPlainTextEdit()
        self.chat_out.setReadOnly(True)
        cl.addWidget(self.chat_out, 1)
        self.chat_metrics = KeyValueGrid()
        cl.addWidget(self.chat_metrics)
        self.tabs.addTab(chat, "Chat test")

        # --- simulation
        sim = QWidget()
        sl = QVBoxLayout(sim)
        sh = QHBoxLayout()
        big = mock_badge("SIMULATION")
        big.setStyleSheet("font-size: 16px; padding: 6px 14px;")
        sh.addWidget(big)
        sh.addWidget(caption("Exercises the conversation state machine with typed text for a fictional 'Demo Gym'. No phone, no audio, no contact record is touched."))
        sh.addStretch(1)
        sh.addWidget(button("New simulation", None, self.new_sim))
        sl.addLayout(sh)
        self.sim_state = QLabel("state: —")
        self.sim_state.setProperty("role", "pill-gold")
        sl.addWidget(self.sim_state)
        self.sim_log = QListWidget()
        sl.addWidget(self.sim_log, 1)
        sr = QHBoxLayout()
        self.sim_input = QLineEdit()
        self.sim_input.setPlaceholderText("Prospect says… (leave empty for the agent's next line)")
        self.sim_input.setAccessibleName("Simulation utterance")
        self.sim_input.returnPressed.connect(self.sim_step)
        sr.addWidget(self.sim_input, 1)
        self.sim_lang = combo([("auto", "auto"), ("हिन्दी", "hi"), ("English", "en")])
        sr.addWidget(self.sim_lang)
        self.sim_llm = QCheckBox("use local LLM")
        self.sim_llm.setChecked(False)
        self.sim_llm.setToolTip("Off = deterministic script lines; On = local model may rephrase (guardrails apply)")
        sr.addWidget(self.sim_llm)
        sr.addWidget(button("Step", "primary", self.sim_step))
        sl.addLayout(sr)
        self.tabs.addTab(sim, "Conversation SIMULATION")

        # --- speech
        sp = QWidget()
        spl = QVBoxLayout(sp)
        self.speech_grid = KeyValueGrid()
        spc = Card("Speech status (PC-local)")
        spc.add(self.speech_grid)
        spl.addWidget(spc)
        tts = Card("Text-to-speech test (Piper on this PC)")
        tr = QHBoxLayout()
        self.tts_text = QLineEdit("नमस्ते, मैं FITRON की ओर से बोल रहा हूँ।")
        self.tts_text.setAccessibleName("TTS text")
        tr.addWidget(self.tts_text, 1)
        self.tts_lang = combo([("हिन्दी", "hi"), ("English", "en")])
        tr.addWidget(self.tts_lang)
        tr.addWidget(button("Synthesize & play", "primary", self.tts))
        trw = QWidget()
        trw.setLayout(tr)
        tts.add(trw)
        self.tts_status = status_label("")
        tts.add(self.tts_status)
        spl.addWidget(tts)
        lb = Card("Loopback: Piper → VAD → Whisper")
        lh = QHBoxLayout()
        lh.addWidget(mock_badge("SIMULATED LOOPBACK"))
        lh.addWidget(caption("Proves the local pipeline works; it is NOT phone-call audio."))
        self.lb_lang = combo([("English", "en"), ("हिन्दी", "hi")])
        lh.addWidget(self.lb_lang)
        lh.addWidget(button("Run loopback", None, self.loopback))
        lh.addStretch(1)
        lw = QWidget()
        lw.setLayout(lh)
        lb.add(lw)
        self.lb_table = DataTable([("Phrase", lambda r: r.get("phrase") or r.get("text")), ("Transcribed", lambda r: r.get("transcribed") or r.get("stt_text")), ("Match", lambda r: r.get("match") or r.get("similarity")), ("TTS ms", "tts_latency_ms"), ("STT ms", "stt_latency_ms"), ("Error", "error")])
        self.lb_table.setMaximumHeight(160)
        lb.add(self.lb_table)
        spl.addWidget(lb)
        spl.addStretch(1)
        self.tabs.addTab(sp, "Speech")

        # --- runs
        runs = QWidget()
        rl = QVBoxLayout(runs)
        rl.addWidget(caption("Every model/TTS/STT invocation is logged with its latency (/ai/runs)."))
        self.runs_table = DataTable([("Time", lambda r: r.get("created_at")), ("Kind", "kind"), ("Provider", "provider"), ("Model", "model"), ("First token ms", "first_token_ms"), ("Total ms", "total_ms"), ("tok/s", "tokens_per_second"), ("OK", "success"), ("Error", "error"), ("Offline", "offline")])
        rl.addWidget(self.runs_table, 1)
        self.tabs.addTab(runs, "AI runs")

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/speech/status"), self.api.get("/ai/runs", limit=200)), self._show)

    def _show(self, res: tuple) -> None:
        sp, runs = res
        stt, tts, vad = sp.get("stt", {}), sp.get("tts", {}), sp.get("vad", {})
        self.speech_grid.set_rows([
            ("Label", sp.get("label")),
            ("STT", f"{stt.get('engine')} {stt.get('model')}: {'available' if stt.get('available') else stt.get('message')}"),
            ("TTS", f"{tts.get('engine')}: {'available' if tts.get('available') else tts.get('message')} · voices: {', '.join(map(str, tts.get('voices') or [])) or 'none'} · en={tts.get('voice_en') or '-'} hi={tts.get('voice_hi') or '-'}"),
            ("VAD self-test", pretty_json(vad)),
            ("Audio devices", pretty_json(sp.get("audio_devices")) if sp.get("audio_devices") else "none detected"),
        ])
        self.runs_table.set_rows(runs)

    def chat_test(self) -> None:
        p = self.prompt.text().strip()
        if not p:
            self.toast("Enter a prompt", "warning")
            return
        body = {"prompt": p, "language": self.chat_lang.currentData(), "max_tokens": self.max_tokens.value()}
        self.run(lambda: self.api.post("/ai/chat-test", body, timeout=120), self._chat_done, busy_text="Generating…")

    def _chat_done(self, r: dict) -> None:
        self.chat_out.setPlainText(r.get("text", ""))
        g = r.get("guardrail") or {}
        self.chat_metrics.set_rows([("label", r.get("label")), ("detected language", r.get("detected_language")), ("first token", f"{r.get('first_token_ms')} ms"), ("total", f"{r.get('total_ms')} ms"), ("tokens/s", r.get("tokens_per_second")), ("guardrail", pretty_json(g))])
        self.refresh()

    def new_sim(self) -> None:
        self.sim_session = "new"
        self.sim_log.clear()
        self.sim_state.setText("state: (new) — press Step for the greeting")

    def sim_step(self) -> None:
        body = {"utterance": self.sim_input.text().strip() or None, "language": self.sim_lang.currentData(), "use_llm": self.sim_llm.isChecked()}
        if body["utterance"]:
            self.sim_log.addItem(f"PROSPECT: {body['utterance']}")
        self.sim_input.clear()
        sess = self.sim_session
        self.run(lambda: self.api.post(f"/ai/simulate/{sess}", body, timeout=120), self._sim_done, busy_text="Simulating…")

    def _sim_done(self, r: dict) -> None:
        self.sim_session = r.get("session_id", self.sim_session)
        self.sim_state.setText(f"{r.get('label')} · state: {r.get('state')} · source: {r.get('source')} · lang: {r.get('language')}" + (" · TERMINAL" if r.get("terminal") else ""))
        if r.get("agent_text"):
            self.sim_log.addItem(f"AGENT ({r.get('source')}): {r['agent_text']}" + (f"   refs={r.get('knowledge_refs')}" if r.get("knowledge_refs") else ""))
        if r.get("guardrail"):
            self.sim_log.addItem(f"   guardrail: {pretty_json(r['guardrail'])}")
        self.sim_log.scrollToBottom()

    def tts(self) -> None:
        text = self.tts_text.text().strip()
        if not text:
            return
        body = {"text": text, "language": self.tts_lang.currentData()}
        self.run(lambda: self.api.post("/speech/tts", body, timeout=120), self._tts_done, lambda e: (self.tts_status.setText(f"TTS failed: {e}"), self.report_error(e)), busy_text="Synthesizing…")

    def _tts_done(self, r: dict) -> None:
        data = base64.b64decode(r.get("wav_base64", ""))
        how = audio.play_wav_bytes(data)
        self.tts_status.setText(f"voice {r.get('voice')} · {r.get('sample_rate')} Hz · {r.get('duration_s', 0):.2f} s · latency {r.get('latency_ms')} ms · {how}")
        self.refresh()

    def loopback(self) -> None:
        lang = self.lb_lang.currentData()
        self.run(lambda: self.api.post("/speech/loopback", params={"language": lang}, timeout=LONG_TIMEOUT), self._lb_done, busy_text="Running loopback…")

    def _lb_done(self, r: dict) -> None:
        self.lb_table.set_rows(r.get("results", []))
        self.toast(f"{r.get('label')} finished ({len(r.get('results', []))} phrases)", "info")
        self.refresh()
