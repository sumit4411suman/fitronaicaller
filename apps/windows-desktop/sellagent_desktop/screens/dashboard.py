"""Screen 3: dashboard per the approved mockup. Every number is read from the backend; nothing is invented.
Week-over-week deltas are intentionally omitted because the API does not provide last week's figures."""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import BORDER, DANGER, GOLD, INFO, SUCCESS, WARNING, BarChart, Card, DataTable, DonutChart, EmptyState, KeyValueGrid, StatCard, badge, button, caption, chip, fmt_dt, set_chip, STATUS_CHIP

NOT_CONNECTED = {"none", "no_answer", "busy", "technical_failure", "cancelled"}


def _greeting() -> str:
    h = datetime.now().hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")


class DashboardScreen(BaseScreen):
    key, title = "dashboard", "Dashboard"
    scrollable = True

    def build(self) -> None:
        self.title_lbl.setVisible(False)  # the greeting is the page title on this screen
        head = QHBoxLayout()
        col = QVBoxLayout()
        self.greeting = QLabel("")
        self.greeting.setProperty("role", "greeting")
        self.greeting.setObjectName("greeting")
        col.addWidget(self.greeting)
        self.ready_lbl = QLabel("")
        self.ready_lbl.setObjectName("PageSubtitle")
        col.addWidget(self.ready_lbl)
        head.addLayout(col, 1)
        rc = QVBoxLayout()
        self.clock = caption("")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        rc.addWidget(self.clock)
        hb = QHBoxLayout()
        hb.addStretch(1)
        hb.addWidget(badge("live database", "pill-gold"))
        hb.addWidget(button("+ New Campaign", "primary", lambda: self.ctx.navigate("campaigns", new=True)))
        rc.addLayout(hb)
        head.addLayout(rc)
        self.root.addLayout(head)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(lambda: self.clock.setText(datetime.now().strftime("%A, %d %B %Y · %H:%M")))
        self.clock_timer.start(30_000)
        self.clock.setText(datetime.now().strftime("%A, %d %B %Y · %H:%M"))

        grid = QGridLayout()
        self.cards = {}
        for i, (k, t) in enumerate([("contacts_total", "Total Contacts"), ("calls_today", "Called Today"), ("interested", "Interested"), ("converted", "Conversions")]):
            c = StatCard(t)
            self.cards[k] = c
            grid.addWidget(c, 0, i)
        self.root.addLayout(grid)

        row2 = QHBoxLayout()
        cw = Card("Calls This Week")
        self.chart = BarChart()
        self.chart.setMinimumHeight(200)
        cw.add(self.chart)
        row2.addWidget(cw, 3)
        cr = Card("Connection Rate")
        self.donut = DonutChart()
        cr.add(self.donut)
        self.rate_caption = caption("outcomes of the last 7 days")
        cr.add(self.rate_caption)
        row2.addWidget(cr, 2)
        ai = Card("Live AI Status")
        self.ai_rows: dict[str, QLabel] = {}
        for name in ("LLM", "STT", "TTS", "Knowledge Base"):
            r = QHBoxLayout()
            r.addWidget(QLabel(name))
            r.addStretch(1)
            c = chip("checking", "neutral")
            self.ai_rows[name] = c
            r.addWidget(c)
            w = QWidget()
            w.setLayout(r)
            ai.add(w)
        self.ai_detail = caption("")
        ai.add(self.ai_detail)
        row2.addWidget(ai, 2)
        self.root.addLayout(row2)

        row3 = QHBoxLayout()
        rc_card = Card("Recent Calls")
        self.recent = DataTable([("When", lambda r: fmt_dt(r.get("started_at"))), ("Business", "business_name"), ("Phone", "phone_e164"), ("State", "conversation_state"), ("Outcome", "outcome"), ("Duration s", "duration_seconds")])
        self.recent.setMinimumHeight(200)
        self.recent.setMaximumHeight(260)
        self.recent.itemDoubleClicked.connect(lambda *_: self._open_recent())
        rc_card.add(self.recent)
        self.recent_empty = EmptyState("No calls yet — dispatch a job from the Call Console.")
        rc_card.add(self.recent_empty)
        row3.addWidget(rc_card, 3)
        qa = Card("Quick Actions")
        qg = QGridLayout()
        for i, (text, target) in enumerate([("▶  Start Calling", "call_queue"), ("⬆  Import Contacts", "import_export"), ("◫  Manage Campaigns", "campaigns"), ("☰  Knowledge Base", "knowledge")]):
            b = button(text, "quick", lambda t=target: self.ctx.navigate(t))
            qg.addWidget(b, i // 2, i % 2)
        qw = QWidget()
        qw.setLayout(qg)
        qa.add(qw)
        banner = Card(gold=False)
        banner.setProperty("role", "card-dark")
        bl = QHBoxLayout()
        bt = QLabel("Open Call Console\nHuman-assisted calling with approved script lines and live transcript")
        bt.setProperty("role", "gold")
        bl.addWidget(bt, 1)
        bl.addWidget(button("Open", "primary", lambda: self.ctx.navigate("live_call")))
        bw = QWidget()
        bw.setLayout(bl)
        banner.add(bw)
        qa.add(banner)
        row3.addWidget(qa, 2)
        self.root.addLayout(row3)

        row4 = QHBoxLayout()
        dev = Card("Device Connection")
        self.device_grid = KeyValueGrid()
        dev.add(self.device_grid)
        self.device_note = caption("")
        dev.add(self.device_note)
        dev.add(button("Manage devices", None, lambda: self.ctx.navigate("devices")))
        row4.addWidget(dev, 2)
        camp = Card("Campaigns")
        self.camp_box = QVBoxLayout()
        cbw = QWidget()
        cbw.setLayout(self.camp_box)
        camp.add(cbw)
        self.camp_empty = EmptyState("No campaigns yet.")
        camp.add(self.camp_empty)
        camp.add(button("All campaigns", None, lambda: self.ctx.navigate("campaigns")))
        row4.addWidget(camp, 3)
        self.root.addLayout(row4)
        self.root.addStretch(1)

    def refresh(self) -> None:
        api = self.api

        def fetch() -> dict:
            out = {"dash": api.get("/reports/dashboard"), "calls": api.get("/calls", limit=8), "campaigns": api.get("/campaigns"), "settings": api.get("/settings"), "kb": api.get("/knowledge", status="approved"), "devices": api.get("/devices"), "connected": api.get("/devices/connected")}
            for key, path in (("ai", "/ai/status"), ("speech", "/speech/status")):
                try:
                    out[key] = api.get(path)
                except Exception as exc:  # noqa: BLE001 - optional status must not blank the dashboard
                    out[key] = {"available": False, "message": f"status unavailable: {exc}", "stt": {"available": False, "message": str(exc)}, "tts": {"available": False, "message": str(exc)}}
            return out

        self.run(fetch, self._show)

    def _show(self, res: dict) -> None:
        d, ai, sp, calls, camps, settings = res["dash"], res["ai"], res["speech"], res["calls"], res["campaigns"], res["settings"]
        vals = settings.get("values", {})
        self.ctx.settings_cache.update(vals)
        self.ctx.ai_status = ai
        self.greeting.setText(f"{_greeting()}, {vals.get('general.operator_name') or 'Operator'}!")
        if ai.get("available") and ai.get("configured_model_installed"):
            self.ready_lbl.setText("Your AI Sales Agent is ready")
        elif ai.get("available"):
            self.ready_lbl.setText(f"Local AI online but model {ai.get('configured_model')} is not installed — human-assisted mode with script lines")
        else:
            self.ready_lbl.setText("Local AI not available — human-assisted mode")
        stages = d.get("contacts_by_stage") or {}
        self.cards["contacts_total"].set_value(d.get("contacts_total"))
        self.cards["calls_today"].set_value(d.get("calls_today"))
        self.cards["interested"].set_value(int(stages.get("interested", 0)))
        self.cards["converted"].set_value(int(stages.get("converted", 0)))
        self.chart.set_data([(x.get("date", ""), float(x.get("calls", 0))) for x in d.get("calls_daily", [])])
        outcomes = d.get("outcomes_week") or {}
        week = int(d.get("calls_week") or 0)
        if week == 0:
            self.donut.set_data([], "")
            self.rate_caption.setText("no calls yet in the last 7 days")
        else:
            connected = sum(v for k, v in outcomes.items() if k not in NOT_CONNECTED)
            failed = int(outcomes.get("technical_failure", 0)) + int(outcomes.get("cancelled", 0))
            rate = d.get("connect_rate_week")
            self.donut.set_data([("connected", float(connected), SUCCESS), ("no answer", float(outcomes.get("no_answer", 0)), WARNING), ("busy", float(outcomes.get("busy", 0)), INFO), ("failed", float(failed), DANGER), ("open", float(outcomes.get("none", 0)), BORDER)], f"{rate:.0%}" if isinstance(rate, int | float) else "")
            self.rate_caption.setText(f"{connected} of {week} calls connected in the last 7 days")
        stt, tts = sp.get("stt", {}), sp.get("tts", {})
        set_chip(self.ai_rows["LLM"], "Ready" if ai.get("available") and ai.get("configured_model_installed") else "Not available", "success" if ai.get("available") and ai.get("configured_model_installed") else "danger")
        set_chip(self.ai_rows["STT"], "Ready" if stt.get("available") else "Not available", "success" if stt.get("available") else "danger")
        set_chip(self.ai_rows["TTS"], "Ready" if tts.get("available") and (tts.get("voices") or []) else "Not available", "success" if tts.get("available") and (tts.get("voices") or []) else "danger")
        kb_n = len(res.get("kb") or [])
        set_chip(self.ai_rows["Knowledge Base"], f"Ready · {kb_n} approved" if kb_n else "No approved facts", "success" if kb_n else "warning")
        self.ai_detail.setText(f"{ai.get('provider', '?')}: {ai.get('message') or 'ok'} · STT {stt.get('model')} · TTS voices: {', '.join(map(str, tts.get('voices') or [])) or 'none'}")
        items = calls.get("items", [])
        self.recent.set_rows(items)
        self.recent_empty.setVisible(not items)
        self._device(res["devices"], res["connected"].get("connected", []))
        while self.camp_box.count():
            it = self.camp_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.camp_empty.setVisible(not camps)
        for c in camps[:6]:
            r = QHBoxLayout()
            r.addWidget(QLabel(f"<b>{c['name']}</b>  <span style='color:#6B665A'>{c['calling_mode']} · {c['language']}</span>"), 1)
            r.addWidget(chip(c["status"], STATUS_CHIP.get(c["status"], "neutral")))
            w = QWidget()
            w.setLayout(r)
            self.camp_box.addWidget(w)

    def _device(self, devices: list[dict], connected: list[str]) -> None:
        approved = sorted([x for x in devices if x.get("status") == "approved"], key=lambda x: x.get("last_seen_at") or "", reverse=True)
        if not approved:
            self.device_grid.set_rows([("Status", "Not paired")])
            self.device_note.setText("Pair the Android companion app under Devices to dial from the phone and receive call-state events.")
            return
        dev = approved[0]
        hb = self.ctx.last_heartbeat if self.ctx.last_heartbeat.get("device_id") == dev["id"] else {}
        rows = [("Device", f"{dev.get('name')} ({dev.get('model')})"), ("Android", dev.get("android_version")), ("App", dev.get("app_version")), ("Status", "Connected" if dev["id"] in connected else "Not connected"), ("Last seen", fmt_dt(dev.get("last_seen_at"), True))]
        if hb:
            rows += [("Network", hb.get("network")), ("Battery", f"{hb.get('battery_percent')}%" if hb.get("battery_percent") is not None else "unknown"), ("Wi-Fi calling", {True: "active", False: "inactive"}.get(hb.get("wifi_calling_active"), "unknown")), ("In call", "yes" if hb.get("in_call") else "no"), ("Heartbeat", f"{int(time.time() - hb.get('received_at', time.time()))} s ago")]
            self.device_note.setText("")
        else:
            self.device_note.setText("No heartbeat received in this session yet; battery / network / Wi-Fi calling are shown once the phone reports them.")
        self.device_grid.set_rows(rows)

    def _open_recent(self) -> None:
        row = self.recent.selected_row()
        if row:
            self.ctx.navigate("call_history", call_id=row["id"])
