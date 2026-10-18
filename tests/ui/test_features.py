"""UI coverage for the blueprint features added in backend commit 4841ae9: users/roles/JWT, workers + events,
campaign start/pause/follow-up/progress, follow-up calendar, daily reports, dashboard comparisons + sentiment,
call sentiment + summary, live transcription gate, streaming AI, model licence gate, PDF/DOCX import, contact
category and database encryption. All run against the real backend subprocess (see conftest.py)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sellagent_desktop.api_client import ApiError
from sellagent_desktop.api_client import wait_for_idle as wait_idle

pytestmark = pytest.mark.ui


def _wait_until(qapp, cond, timeout: float = 15.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def _contact(backend, name: str, phone: str, **extra) -> dict:
    with backend.client() as c:
        r = c.post("/api/v1/contacts", json={"business_name": name, "phone": phone, "consent_status": "granted", "source_verification": "verified", **extra})
        assert r.status_code == 201, r.text
        contact = r.json()
        c.post(f"/api/v1/contacts/{contact['id']}/permissions", json={"status": "granted", "source": "ui feature test"})
        return contact


def _live_call(backend, name: str, phone: str) -> str:
    contact = _contact(backend, name, phone)
    with backend.client() as c:
        job = c.post("/api/v1/call-jobs", json={"contact_id": contact["id"], "route": "manual"}).json()
        r = c.post(f"/api/v1/call-jobs/{job['id']}/dispatch")
        assert r.status_code == 200, r.text
        call_id = r.json()["call_id"]
        assert c.post(f"/api/v1/calls/{call_id}/connected").status_code == 200
        return call_id


# ---------------------------------------------------------------------------- 12. contact category
def test_contact_category_field_and_column(window, backend, monkeypatch):
    from sellagent_desktop.screens import contacts as mod

    dlg = mod.ContactDialog(None)
    assert dlg.fields["category"].currentText() == "Gym / Fitness"
    name = f"Category Studio {int(time.time())}"

    def fake_exec(self):
        self.fields["business_name"].setText(name)
        self.fields["phone"].setText("+91 98444 55667")
        self.fields["category"].setCurrentText("Yoga studio")
        self._on_accept()
        return self.result()

    monkeypatch.setattr(mod.ContactDialog, "exec", fake_exec)
    window.navigate("contacts")
    wait_idle()
    window.screens["contacts"].new_btn.click()
    wait_idle()
    s = window.screens["contacts"]
    row = next(r for r in s.table.rows if r["business_name"] == name)
    assert row["category"] == "Yoga studio"
    headers = [s.table.horizontalHeaderItem(i).text() for i in range(s.table.columnCount())]
    assert "Category" in headers


# ---------------------------------------------------------------------------- 6. dashboard comparisons + sentiment
def test_dashboard_delta_text_rules():
    from sellagent_desktop.screens.dashboard import delta_text

    assert delta_text({"current": 12, "previous": 10}) == ("+20% from last week", "success")
    assert delta_text({"current": 5, "previous": 10}) == ("-50% from last week", "danger")
    assert delta_text({"current": 3, "previous": 0}) == ("new", "success")
    assert delta_text({"current": 0, "previous": 0}) == ("", "neutral")
    assert delta_text(None) == ("", "neutral")


def test_dashboard_shows_real_comparisons_and_sentiment(window, backend):
    window.navigate("dashboard")
    wait_idle()
    d = window.screens["dashboard"]
    with backend.client() as c:
        dash = c.get("/api/v1/reports/dashboard").json()
    comp = dash["comparisons"]["contacts_added_week_vs_previous"]
    assert comp["current"] >= 1  # contacts created by this test session
    chip = d.deltas["contacts_total"]
    assert chip.isVisibleTo(d) and chip.text()
    if comp["previous"] == 0:
        assert chip.text() == f"+{comp['current']} added this week"
    # calls_today vs yesterday: no fake delta when both are zero
    ct = dash["comparisons"]["calls_today_vs_yesterday"]
    assert d.deltas["calls_today"].isVisibleTo(d) == bool(ct["current"] or ct["previous"])
    for k, c in d.senti_chips.items():
        assert c.text() == f"{k} {int(dash['sentiment_week'].get(k, 0))}"


# ---------------------------------------------------------------------------- 3. campaigns
def test_campaign_followup_fields_start_pause_progress(window, backend, monkeypatch):
    from sellagent_desktop.screens import campaigns as mod

    dlg = mod.CampaignDialog(None)
    assert dlg.fields["auto_followup"].isChecked() and dlg.fields["followup_after_days"].value() == 2
    contact = _contact(backend, "Campaign Member Gym", "+91 98555 66778")
    with backend.client() as c:
        camp = c.post("/api/v1/campaigns", json={"name": f"UI start {int(time.time())}", "auto_followup": False, "followup_after_days": 5}).json()
        assert camp["auto_followup"] is False and camp["followup_after_days"] == 5
        c.post(f"/api/v1/campaigns/{camp['id']}/contacts", json={"ids": [contact["id"]]})
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: True)
    window.navigate("campaigns")
    wait_idle()
    s = window.screens["campaigns"]
    s.table.select_data_row(next(i for i, r in enumerate(s.table.rows) if r["id"] == camp["id"]))
    wait_idle()
    assert s.start_btn.isEnabled() and not s.pause_btn.isEnabled()
    s.start_campaign()
    wait_idle()
    assert s.last_error is None
    with backend.client() as c:
        assert c.get(f"/api/v1/campaigns/{camp['id']}").json()["status"] == "active"
        stats = c.get(f"/api/v1/campaigns/{camp['id']}/stats").json()
    s.table.select_data_row(next(i for i, r in enumerate(s.table.rows) if r["id"] == camp["id"]))
    wait_idle()
    assert s.pause_btn.isEnabled()
    assert s.progress.value() == int(round(stats["progress_percent"] * 10))
    assert "% of reachable contacts finished" in s.progress.format()
    s.pause_campaign()
    wait_idle()
    with backend.client() as c:
        assert c.get(f"/api/v1/campaigns/{camp['id']}").json()["status"] == "paused"


# ---------------------------------------------------------------------------- 4. follow-up calendar
def test_followup_month_calendar(window, backend):
    contact = _contact(backend, "Calendar Gym", "+91 98666 77889")
    due = (datetime.now(UTC) + timedelta(days=1)).replace(hour=6, minute=30, second=0, microsecond=0)
    with backend.client() as c:
        assert c.post("/api/v1/followups", json={"contact_id": contact["id"], "due_at": due.isoformat(), "kind": "demo"}).status_code == 201
        cal = c.get("/api/v1/followups/calendar", params={"month": due.astimezone().strftime("%Y-%m")}).json()
    window.navigate("followups")
    wait_idle()
    s = window.screens["followups"]
    s.month = tuple(int(x) for x in cal["month"].split("-"))
    s.views.setCurrentIndex(1)
    wait_idle()
    assert len(s.day_buttons) == cal["days_in_month"]
    day_key = next(k for k, items in cal["days"].items() if any(i["business_name"] == "Calendar Gym" for i in items))
    btn = next(b for b in s.day_buttons if b.objectName() == f"day_{day_key}")
    btn.click()
    texts = [s.day_list.item(i).text() for i in range(s.day_list.count())]
    assert any("Calendar Gym" in t and "demo" in t for t in texts)
    before = s.month_lbl.text()
    s._shift_month(1)
    wait_idle()
    assert s.month_lbl.text() != before
    s.views.setCurrentIndex(0)


# ---------------------------------------------------------------------------- 5. daily reports
def test_daily_reports_generate_open_save(window, backend, monkeypatch, tmp_path):
    from sellagent_desktop.screens import analytics as mod

    opened: list = []
    monkeypatch.setattr(mod.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    window.navigate("analytics")
    wait_idle()
    s = window.screens["analytics"]
    s.generate_report()
    wait_idle()
    assert s.last_error is None
    day = s.report_date.date().toString("yyyy-MM-dd")
    assert any(r["date"] == day for r in s.reports_table.rows)
    s.reports_table.select_data_row(next(i for i, r in enumerate(s.reports_table.rows) if r["date"] == day))
    s.report_file.setCurrentIndex(s.report_file.findData("report.html"))
    s.fetch_report(open_it=True)
    wait_idle()
    assert opened and "<!doctype html" in Path(opened[-1]).read_text(encoding="utf-8").lower()
    target = tmp_path / "calls.csv"
    monkeypatch.setattr(mod.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    s.report_file.setCurrentIndex(s.report_file.findData("calls.csv"))
    s.fetch_report(open_it=False)
    wait_idle()
    assert target.exists() and target.stat().st_size > 0


# ---------------------------------------------------------------------------- 7. sentiment + summary, 8. live transcription
def test_live_call_sentiment_summary_and_history(window, backend, monkeypatch):
    call_id = _live_call(backend, "Sentiment Gym", "+91 98777 88990")
    window.navigate("live_call", call_id=call_id)
    wait_idle()
    live = window.screens["live_call"]
    live.use_llm.setChecked(False)
    live.utterance.setText("Yes, this sounds great, I am interested. What is the price?")
    live.step()
    wait_idle()
    assert live.last_error is None
    with backend.client() as c:
        summary = c.get(f"/api/v1/calls/{call_id}/summary").json()
    assert live.senti_chip.text() == f"sentiment: {summary['sentiment']}"
    tagged = [live.transcript.item(i) for i in range(live.transcript.count()) if live.transcript.item(i).data(256)]
    assert tagged and tagged[0].data(256) in ("positive", "neutral", "negative")
    assert not live.summary_card.isVisibleTo(live)  # summary appears after the outcome is saved
    with backend.client() as c:
        assert c.post(f"/api/v1/calls/{call_id}/outcome", json={"outcome": "interested", "note": "send demo link"}).status_code == 200
    live.load_call()
    wait_idle()
    assert live.summary_card.isVisibleTo(live)
    rows = {live.summary_card.grid.grid.itemAtPosition(r, 0).widget().text(): live.summary_card.grid.grid.itemAtPosition(r, 1).widget().text() for r in range(live.summary_card.grid.grid.rowCount()) if live.summary_card.grid.grid.itemAtPosition(r, 0)}
    assert rows["Result"].startswith("interested")
    from sellagent_desktop.screens import call_history as ch

    monkeypatch.setattr(ch.CallDetailDialog, "exec", lambda self: 0)
    window.navigate("call_history", call_id=call_id)
    wait_idle()
    dlg = window.screens["call_history"].last_dialog
    tabs = dlg.findChild(ch.QTabWidget)
    assert tabs.tabText(0) == "Summary"


def test_live_transcription_gate_consent_and_stream(window, backend, qapp, monkeypatch):
    call_id = _live_call(backend, "Transcribe Gym", "+91 98888 99001")
    window.navigate("live_call", call_id=call_id)
    wait_idle()
    live = window.screens["live_call"]
    # (a) disabled by default -> clear message, no consent recorded
    live.toggle_transcription()
    wait_idle()
    assert "OFF" in live.tx_status.text() and live.tx_thread is None
    # (b) enable, tick consent, stream synthetic PCM (no microphone in CI)
    with backend.client() as c:
        assert c.patch("/api/v1/settings", json={"values": {"privacy.allow_live_transcription": True}}).status_code == 200
    seen_dialog = {}

    def fake_consent(dlg):
        seen_dialog["text"] = dlg.findChildren(type(dlg.read_box))
        assert not dlg.ok.isEnabled()
        dlg.read_box.setChecked(True)
        dlg.agree_box.setChecked(True)
        assert dlg.ok.isEnabled()
        return True

    monkeypatch.setattr(live, "confirm_consent", fake_consent)

    def silence(stop):
        while not stop():
            time.sleep(0.05)
            yield b"\x00\x00" * 1600

    live.frames_source = silence
    live.toggle_transcription()
    assert _wait_until(qapp, lambda: live.mic_chip.text() in ("mic: listening", "mic: error"), 30)
    errored = live.mic_chip.text() == "mic: error"
    if errored:
        # gate + consent passed; only the speech engine may be missing (e.g. CI without faster-whisper)
        assert "not_allowed" not in live.tx_status.text() and "stt_unavailable" in live.tx_status.text()
    live.stop_transcription()
    assert _wait_until(qapp, lambda: live.tx_thread is None, 20)
    # an error stays visible after the thread ends; a clean stop returns to "mic off"
    assert live.mic_chip.text() == ("mic: error" if errored else "mic off")
    with backend.client() as c:
        audit = c.get("/api/v1/audit", params={"action": "call.transcription_consent"}).json()
        assert any(a["entity_id"] == call_id for a in audit)
        c.patch("/api/v1/settings", json={"values": {"privacy.allow_live_transcription": False}})
        c.post(f"/api/v1/calls/{call_id}/outcome", json={"outcome": "not_interested"})


def test_microphone_unavailable_message():
    from sellagent_desktop.transcription import MicUnavailable, microphone_frames

    try:
        gen = microphone_frames(lambda: True)
        next(gen, None)
    except MicUnavailable as exc:
        assert "PortAudio" in str(exc) or "microphone" in str(exc).lower()


# ---------------------------------------------------------------------------- 9. streaming AI
def test_streaming_chat_events_and_cancel_state(window, qapp):
    window.navigate("diagnostics")
    wait_idle()
    d = window.screens["diagnostics"]
    d.prompt.setText("FITRON ka price kya hai?")
    d.chat_test()
    assert d.cancel_btn.isEnabled()
    assert _wait_until(qapp, lambda: any(n == "done" for n, _ in getattr(d, "stream_events", [])), 60)
    wait_idle()
    names = [n for n, _ in d.stream_events]
    assert names[0] == "start" and names[-1] == "done"
    assert d.stream_job_id
    assert not d.cancel_btn.isEnabled() and d.chat_btn.isEnabled()
    r = window.ctx.api.post(f"/system/ai-jobs/{d.stream_job_id}/cancel")
    assert r["cancelled"] is False  # already finished; endpoint wired


# ---------------------------------------------------------------------------- 10. model licence gate, 11. KB import filter
def test_model_licence_gate(window):
    window.navigate("models")
    wait_idle()
    m = window.screens["models"]
    idx = next(i for i, r in enumerate(m.catalog_table.rows) if r["name"] == "qwen2.5:3b")
    m.catalog_table.select_data_row(idx)
    assert m.license_lbl.isVisibleTo(m) and "NON-COMMERCIAL" in m.license_lbl.text()
    assert m.license_ack.isVisibleTo(m)
    m.external_allowed, m.provider = True, "ollama"  # pretend network allowed to test the licence gate alone
    m.ack.setChecked(True)
    m.license_ack.setChecked(False)
    m._sync_ack()
    assert not m.pull_btn.isEnabled()
    m.license_ack.setChecked(True)
    assert m.pull_btn.isEnabled()
    m.ack.setChecked(False)
    m.license_ack.setChecked(False)
    m.refresh()
    wait_idle()


def test_knowledge_import_accepts_pdf_docx(window, monkeypatch):
    from sellagent_desktop.screens import knowledge as mod

    seen = {}
    def fake_open(*a, **k):
        seen["filter"] = a[3] if len(a) > 3 else k.get("filter", "")
        return "", ""

    monkeypatch.setattr(mod.QFileDialog, "getOpenFileName", fake_open)
    window.navigate("knowledge")
    wait_idle()
    window.screens["knowledge"].import_doc()
    assert "*.pdf" in seen["filter"] and "*.docx" in seen["filter"]


# ---------------------------------------------------------------------------- 13. database encryption
def test_database_encryption_chip_and_backup_rule(window, backend):
    with backend.client() as c:
        db = c.get("/api/v1/health").json()["database"]
    window.navigate("logs")
    wait_idle()
    chip = window.screens["logs"].db_chip.text()
    assert chip == ("Database: encrypted (AES-256)" if db["encrypted"] else f"Database: NOT encrypted — {db['encryption']}")
    window.navigate("backup")
    wait_idle()
    b = window.screens["backup"]
    assert b.db_encrypted == db["encrypted"]
    if db["encrypted"]:
        assert b.encrypt and "every backup needs a passphrase" in b.note.text()


# ---------------------------------------------------------------------------- 2. workers + events + bell
def test_workers_screen_run_toggle(window, backend):
    window.navigate("workers")
    wait_idle()
    w = window.screens["workers"]
    names = {r["name"] for r in w.table.rows}
    assert {"call_queue", "campaign_engine", "followup_scheduler", "report"} <= names
    idx = next(i for i, r in enumerate(w.table.rows) if r["name"] == "call_queue")
    runs_before = w.table.rows[idx].get("runs", 0)
    w.table.select_data_row(idx)
    w.run_now()
    wait_idle()
    assert w.last_error is None
    row = next(r for r in w.table.rows if r["name"] == "call_queue")
    assert row["runs"] >= runs_before + 1
    w.table.select_data_row(next(i for i, r in enumerate(w.table.rows) if r["name"] == "report"))
    w.run(lambda: w.api.request("POST", "/system/workers/report/enabled", params={"enabled": False}), lambda _: w.refresh())
    wait_idle()
    assert next(r for r in w.table.rows if r["name"] == "report")["enabled"] is False
    w.run(lambda: w.api.request("POST", "/system/workers/report/enabled", params={"enabled": True}), lambda _: w.refresh())
    wait_idle()


def test_event_envelopes_toast_bell_and_refresh(window):
    window.navigate("followups")
    wait_idle()
    window.unread = 0
    window._bell_text()
    window.on_ws_event({"type": "event", "payload": {"name": "followup.due", "data": {"followup_id": "x", "contact_id": "c", "business_name": "Bell Gym", "due_at": datetime.now(UTC).isoformat(), "kind": "call"}}})
    assert window.unread == 1 and window.bell.text() == "1"
    assert "Follow-up due: Bell Gym" in window.toast_lbl.text()
    assert window.notifications[0]["name"] == "followup.due"
    window.on_ws_event({"type": "event", "payload": {"name": "report.ready", "data": {"date": "2026-10-18", "files": ["report.html"]}}})
    assert window.bell.text() == "2"
    wait_idle()
    window._fill_bell_menu()
    acts = [a.text() for a in window.bell_menu.actions()]
    assert any("Daily report ready" in t for t in acts) and window.bell.text() == ""


# ---------------------------------------------------------------------------- 1. users, roles, JWT, switch user (last: changes identity)
def test_users_roles_switch_user_and_permissions(window, backend, qapp, monkeypatch):
    from sellagent_desktop import main_window as mw
    from sellagent_desktop.screens import users as um

    assert um.pin_problem("111111") and um.pin_problem("123456") and um.pin_problem("12a456") and um.pin_problem("482915") is None
    window.navigate("users")
    wait_idle()
    us = window.screens["users"]
    assert us.matrix.rowCount() >= 10 and us.matrix.columnCount() == 4
    uname = f"viewer{int(time.time()) % 100000}"

    def fake_user_exec(self):
        if self.existing is None:
            self.fields["username"].setText(uname)
            self.fields["display_name"].setText("Read Only")
            self.fields["role"].setCurrentIndex(self.fields["role"].findData("viewer"))
            self.fields["pin"].setText("482915")
        self._on_accept()
        return self.result()

    monkeypatch.setattr(um.UserDialog, "exec", fake_user_exec)
    us.new_user()
    wait_idle()
    assert us.last_error is None and any(u["username"] == uname and u["role"] == "viewer" for u in us.table.rows)

    owner_token = window.ctx.api.owner_token

    def fake_login_exec(self):
        self.username.setText(uname)
        self.pin.setText("482915")
        self.submit()
        wait_idle()
        return self.result()

    monkeypatch.setattr(mw.LoginDialog, "exec", fake_login_exec)
    window.switch_user()
    wait_idle()
    assert window.ctx.role == "viewer" and window.ctx.via == "jwt"
    assert window.ctx.api.token != owner_token and window.role_chip.text() == f"{uname} · viewer"
    assert _wait_until(qapp, lambda: window.ctx.ws.is_connected and window.ctx.api.token in window.ctx.ws.url, 15)
    window.navigate("contacts")
    wait_idle()
    c = window.screens["contacts"]
    assert not c.new_btn.isEnabled() and "Your role (viewer)" in c.new_btn.toolTip()
    c.new_btn.setEnabled(True)  # screen logic re-enabling must not unlock it
    assert not c.new_btn.isEnabled()
    settings_tabs = window.group_tabs["settings"]
    assert not settings_tabs.isTabVisible(settings_tabs.indexOf(window.screens["users"]))
    assert window.stop_btn.isEnabled()  # EMERGENCY STOP stays available for every role
    with pytest.raises(ApiError) as ei:
        window.ctx.api.post("/contacts", {"business_name": "Nope", "phone": "+91 98000 00001"})
    assert ei.value.status == 403 and str(ei.value).startswith("Your role (viewer) can't do this")
    window.return_to_owner()
    wait_idle()
    assert window.ctx.role == "admin" and window.ctx.api.token == owner_token
    window.navigate("contacts")
    wait_idle()
    assert window.screens["contacts"].new_btn.isEnabled()
    assert settings_tabs.isTabVisible(settings_tabs.indexOf(window.screens["users"]))


def test_ai_bridge_controls_on_call_console(window, backend, qapp, monkeypatch):
    """The AI voice bridge is off by default; when the backend refuses, the reason is shown and the operator keeps
    control. Bridge events from the backend drive the AI chip and the Take over button."""
    import sellagent_desktop.screens.live_call as live_mod

    call_id = _live_call(backend, "Bridge Gym", "+91 98999 00112")
    window.navigate("live_call", call_id=call_id)
    wait_idle()
    live = window.screens["live_call"]
    monkeypatch.setattr(live_mod, "confirm", lambda *a, **k: True)
    live.start_bridge()
    wait_idle()
    assert _wait_until(qapp, lambda: "could not start" in live.bridge_status.text(), 15)
    assert "switched off" in live.bridge_status.text()
    assert live.bridge_btn.isEnabled() and not live.takeover_btn.isEnabled() and live.bridge_chip.text() == "AI off"
    live.on_ws_event({"type": "event", "payload": {"name": "bridge.speaking", "data": {"call_id": call_id, "text": "Namaste, this is an automated AI assistant"}}})
    assert live.bridge_chip.text() == "AI on call" and live.takeover_btn.isEnabled() and not live.bridge_btn.isEnabled()
    assert "automated AI assistant" in live.bridge_status.text()
    # events for another call are ignored
    live.on_ws_event({"type": "event", "payload": {"name": "bridge.finished", "data": {"call_id": "other", "status": "finished"}}})
    assert live.bridge_chip.text() == "AI on call"
    live.on_ws_event({"type": "event", "payload": {"name": "bridge.finished", "data": {"call_id": call_id, "status": "stopped", "stop_reason": "operator took over"}}})
    wait_idle()
    assert live.bridge_chip.text() == "AI off" and "operator took over" in live.bridge_status.text() and live.bridge_btn.isEnabled()
    with backend.client() as c:
        c.post(f"/api/v1/calls/{call_id}/outcome", json={"outcome": "not_interested"})
