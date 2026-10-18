"""Screen 2: local AI model manager (Ollama status, catalog, explicit pull, speech engines, network switch)."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel

from sellagent_desktop.api_client import LONG_TIMEOUT
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, KeyValueGrid, button, caption, confirm, mock_badge, status_label


class ModelManagerScreen(BaseScreen):
    key, title = "models", "AI model manager"
    scrollable = True
    subtitle = "Local-only inference (Ollama / llama.cpp, faster-whisper, Piper). Nothing downloads without your explicit acknowledgement."

    def build(self) -> None:
        row = QHBoxLayout()
        self.llm_card = Card("Language model provider")
        self.llm_grid = KeyValueGrid()
        self.llm_card.add(self.llm_grid)
        self.net_lbl = status_label("")
        self.llm_card.add(self.net_lbl)
        self.llm_card.add(button("Open Settings & privacy", None, lambda: self.ctx.navigate("settings")))
        row.addWidget(self.llm_card, 1)
        self.speech_card = Card("Speech engines (PC-local)")
        self.speech_grid = KeyValueGrid()
        self.speech_card.add(self.speech_grid)
        hb = QHBoxLayout()
        hb.addWidget(mock_badge("PC-LOCAL DIAGNOSTIC"))
        hb.addWidget(caption("Says nothing about phone-call audio."))
        hb.addStretch(1)
        w = QLabel()
        w.setLayout(hb)
        self.speech_card.add(w)
        row.addWidget(self.speech_card, 1)
        self.root.addLayout(row)

        installed = Card("Installed models (reported by the provider)")
        self.installed_table = DataTable([("Name", "name"), ("Size", lambda r: r.get("size")), ("Modified", lambda r: r.get("modified_at") or r.get("modified"))])
        self.installed_table.setMaximumHeight(160)
        installed.add(self.installed_table)
        self.root.addWidget(installed)

        cat = Card("Catalog — candidates for a 16 GB CPU-only PC")
        self.catalog_note = caption("")
        cat.add(self.catalog_note)
        self.catalog_table = DataTable([("Model", "name"), ("Params", "params"), ("Download (GB)", "approx_download_gb"), ("RAM (GB)", "approx_ram_gb"), ("License", lambda r: r.get("license", "") + ("  ⚠" if r.get("license_warning") else "")), ("Notes", "notes")])
        self.catalog_table.setMaximumHeight(170)
        self.catalog_table.itemSelectionChanged.connect(self._sync_ack)
        cat.add(self.catalog_table)
        self.ack = QCheckBox("I understand this downloads a model from the internet")
        self.ack.setAccessibleName("Acknowledge download")
        self.ack.stateChanged.connect(self._sync_ack)
        self.license_lbl = QLabel("")
        self.license_lbl.setProperty("role", "chip-danger")
        self.license_lbl.setWordWrap(True)
        self.license_lbl.setVisible(False)
        self.license_ack = QCheckBox("I confirm I have permission to use this model under its licence for commercial FITRON sales")
        self.license_ack.setObjectName("license_ack")
        self.license_ack.setVisible(False)
        self.license_ack.stateChanged.connect(self._sync_ack)
        self.pull_btn = button("Pull selected model", "primary", self.pull_selected)
        self.pull_btn.setEnabled(False)
        self.pull_status = status_label("")
        bar = QHBoxLayout()
        bar.addWidget(self.ack)
        bar.addWidget(self.pull_btn)
        bar.addStretch(1)
        holder = QLabel()
        holder.setLayout(bar)
        cat.add(self.license_lbl)
        cat.add(self.license_ack)
        cat.add(holder)
        cat.add(self.pull_status)
        self.root.addWidget(cat)
        self.root.addStretch(1)
        self.external_allowed = False
        self.provider = "ollama"

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/ai/status"), self.api.get("/ai/catalog"), self.api.get("/speech/status")), self._show)

    def _show(self, res: tuple) -> None:
        st, cat, sp = res
        self.external_allowed = bool(st.get("external_network_allowed"))
        self.provider = st.get("provider")
        self.llm_grid.set_rows([
            ("Provider", st.get("provider")),
            ("Available", "yes" if st.get("available") else f"no — {st.get('message')}"),
            ("Configured model", f"{st.get('configured_model')} ({'installed' if st.get('configured_model_installed') else 'NOT installed'})"),
            ("Offline capable", "yes" if st.get("offline_capable") else "no"),
        ])
        if self.external_allowed:
            self.net_lbl.setText("External network: ALLOWED (privacy.allow_external_network = true). Model downloads can proceed.")
            self.net_lbl.setProperty("role", "warning")
        else:
            self.net_lbl.setText("External network: BLOCKED (default). Model downloads are refused by the backend until you enable 'privacy.allow_external_network' in Settings.")
            self.net_lbl.setProperty("role", "caption")
        self.net_lbl.style().unpolish(self.net_lbl)
        self.net_lbl.style().polish(self.net_lbl)
        self.installed_table.set_rows(st.get("models") or [])
        self.catalog_note.setText(cat.get("note", ""))
        self.catalog_table.set_rows(cat.get("candidates") or [])
        stt, tts, vad = sp.get("stt", {}), sp.get("tts", {}), sp.get("vad", {})
        self.speech_grid.set_rows([
            ("STT", f"{stt.get('engine')} / {stt.get('model')} — {'available' if stt.get('available') else stt.get('message')}"),
            ("TTS", f"{tts.get('engine')} — {'available' if tts.get('available') else tts.get('message')}"),
            ("Voices", ", ".join(map(str, tts.get("voices") or [])) or "none installed"),
            ("VAD self-test", f"{'ok' if vad.get('ok') else 'FAILED'} ({vad.get('kind')}, {vad.get('latency_ms', 0):.1f} ms)"),
            ("Audio devices", str(len(sp.get("audio_devices") or []))),
            ("Models dir", sp.get("models_dir")),
        ])
        self._sync_ack()

    def _sync_ack(self) -> None:
        row = self.catalog_table.selected_row()
        warning = (row or {}).get("license_warning")
        self.license_lbl.setVisible(bool(warning))
        self.license_lbl.setText(f"Licence: {row.get('license')} — {warning}" if warning else "")
        self.license_ack.setVisible(bool(warning))
        if not warning:
            self.license_ack.setChecked(False)
        if row:
            self.ack.setText(f"I understand this downloads ~{row.get('approx_download_gb')} GB ({row.get('name')}) from the internet")
        lic_ok = (not warning) or self.license_ack.isChecked()
        self.pull_btn.setEnabled(bool(row) and self.ack.isChecked() and lic_ok and self.external_allowed and self.provider == "ollama")
        if not self.external_allowed:
            self.pull_btn.setToolTip("Blocked: enable privacy.allow_external_network in Settings first")
        elif self.provider != "ollama":
            self.pull_btn.setToolTip("Pull is only supported through Ollama; place GGUF files manually for llama.cpp")
        else:
            self.pull_btn.setToolTip("Downloads through the local Ollama service")

    def pull_selected(self) -> None:
        row = self.catalog_table.selected_row()
        if not row or not self.ack.isChecked():
            return
        if not confirm(self, "Download model", f"Download {row['name']} (~{row.get('approx_download_gb')} GB) through Ollama now? This can take a long time on a slow connection.", "Download"):
            return
        self.pull_status.setText(f"Pulling {row['name']}… (the backend reports only when the pull finishes)")
        name = row["name"]
        body = {"model": name, "acknowledge_download": True}
        if row.get("license_warning"):
            body["acknowledge_license"] = self.license_ack.isChecked()
        self.run(lambda: self.api.post("/ai/models/pull", body, timeout=LONG_TIMEOUT), self._pulled, self._pull_failed, busy_text="Downloading…")

    def _pulled(self, res: dict) -> None:
        self.pull_status.setText(f"{res.get('model')}: {res.get('status')} ({'done' if res.get('done') else 'not finished'})")
        self.refresh()

    def _pull_failed(self, exc: Exception) -> None:
        self.pull_status.setText(f"Pull failed: {exc}")
        self.report_error(exc)
