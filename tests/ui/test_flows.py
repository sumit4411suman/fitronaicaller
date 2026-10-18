"""End-to-end UI flows against the real backend: contact creation dialog, validation, job + live console, emergency stop."""

from __future__ import annotations

import time

import pytest

from sellagent_desktop.api_client import wait_for_idle as wait_idle

pytestmark = pytest.mark.ui


def _fill(dlg, **values):
    from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit

    for k, v in values.items():
        w = dlg.fields[k]
        if isinstance(w, QLineEdit):
            w.setText(v)
        elif isinstance(w, QPlainTextEdit):
            w.setPlainText(v)
        elif isinstance(w, QComboBox):
            w.setCurrentIndex(max(0, w.findData(v)))


def test_contact_dialog_validation_marks_invalid(qapp):
    from sellagent_desktop.screens.contacts import ContactDialog

    dlg = ContactDialog(None)
    dlg._on_accept()
    assert dlg.result() != ContactDialog.DialogCode.Accepted
    assert dlg.fields["business_name"].property("invalid") == "true"
    assert dlg.fields["phone"].property("invalid") == "true"
    assert dlg.errors["phone"].isVisible() is False or dlg.errors["phone"].text() == "This field is required"
    _fill(dlg, business_name="Iron Paradise", phone="abc")
    dlg._on_accept()
    assert dlg.fields["business_name"].property("invalid") == "false"
    assert dlg.fields["phone"].property("invalid") == "true"
    assert "digits" in dlg.errors["phone"].text()


def test_create_contact_via_dialog_appears_in_table(window, backend, monkeypatch):
    from sellagent_desktop.screens import contacts as contacts_mod

    name = f"UI Gym {int(time.time())}"

    def fake_exec(self):  # fill the real dialog widgets, then accept through the real validation path
        _fill(self, business_name=name, contact_person="Priya", phone="+91 98111 22333", city="Pune", consent_status="granted")
        self._on_accept()
        return self.result()

    monkeypatch.setattr(contacts_mod.ContactDialog, "exec", fake_exec)
    window.navigate("contacts")
    wait_idle()
    screen = window.screens["contacts"]
    screen.new_btn.click()
    assert wait_idle()
    assert screen.last_error is None
    names = [r["business_name"] for r in screen.table.rows]
    assert name in names
    with backend.client() as c:
        r = c.get("/api/v1/contacts", params={"q": name})
        assert r.status_code == 200 and r.json()["total"] == 1
        created = r.json()["items"][0]
        assert created["phone_e164"] == "+919811122333"
    # opening the detail screen with context loads the record
    window.navigate("contact_detail", contact_id=created["id"])
    wait_idle()
    det = window.screens["contact_detail"]
    assert det.last_error is None and name in det.name_lbl.text()
    assert det.tabs.isVisible()


def test_manual_call_job_and_live_console(window, backend):
    """Create contact -> job -> dispatch (manual) -> live console step -> outcome; all through the UI screens."""
    with backend.client() as c:
        r = c.post("/api/v1/contacts", json={"business_name": "Console Gym", "contact_person": "Amit", "phone": "+91 98222 33444", "consent_status": "granted", "source_verification": "verified"})
        assert r.status_code == 201, r.text
        contact = r.json()
        c.post(f"/api/v1/contacts/{contact['id']}/permissions", json={"status": "granted", "source": "ui test", "evidence": "pytest"})
        r = c.post("/api/v1/call-jobs", json={"contact_id": contact["id"], "route": "manual"})
        assert r.status_code == 201, r.text
        job = r.json()
        assert job["status"] == "pending", job["eligibility_result"]
    window.navigate("call_queue")
    wait_idle()
    q = window.screens["call_queue"]
    assert any(j["id"] == job["id"] for j in q.table.rows)
    with backend.client() as c:
        r = c.post(f"/api/v1/call-jobs/{job['id']}/dispatch")
        assert r.status_code == 200, r.text
        call_id = r.json()["call_id"]
    window.navigate("live_call", call_id=call_id)
    wait_idle()
    live = window.screens["live_call"]
    assert live.last_error is None
    assert live.picker.currentData() == call_id
    assert live.state_lbl.text() == "DIAL REQUEST"
    assert live.connected_btn.isEnabled()
    live.mark_connected()
    wait_idle()
    assert live.state_lbl.text() == "CONNECTED"
    live.use_llm.setChecked(False)
    live.step()  # greeting from the built-in script (no LLM configured in tests)
    wait_idle()
    assert live.last_error is None
    assert "FITRON" in live.agent_line.text()
    assert live.source_badge.text() == "source: script"
    assert live.transcript.count() >= 1
    assert "HUMAN-ASSISTED" in live.mode_banner.text()
    with backend.client() as c:
        r = c.post(f"/api/v1/calls/{call_id}/outcome", json={"outcome": "interested", "note": "ui test"})
        assert r.status_code == 200, r.text
    window.navigate("call_history")
    wait_idle()
    h = window.screens["call_history"]
    assert any(row["id"] == call_id and row["outcome"] == "interested" for row in h.table.rows)


def test_emergency_stop_button_hits_endpoint(window, backend):
    window.navigate("dashboard")
    wait_idle()
    window.stop_btn.click()
    assert wait_idle()
    with backend.client() as c:
        vals = c.get("/api/v1/settings").json()["values"]
        assert vals["calling.emergency_stop_active"] is True
    assert window.stop_banner.isVisible()
    assert "ACTIVE" in window.stop_lbl.text()
    # clear through the settings screen action (the only place the UI allows it) and verify
    window.navigate("settings")
    wait_idle()
    s = window.screens["settings"]
    assert s.clear_stop_btn.isVisible()
    s.run(lambda: s.api.post("/call-jobs/emergency-stop", {"reason": "test cleanup", "activate": False}), lambda _: window.set_emergency_state(False))
    wait_idle()
    with backend.client() as c:
        assert c.get("/api/v1/settings").json()["values"]["calling.emergency_stop_active"] is False


def test_knowledge_script_overrides_roundtrip(window, backend):
    window.navigate("scripts")
    wait_idle()
    s = window.screens["scripts"]
    s.editors[("greeting", "en")].setPlainText("Hello {contact_person}, this is an automated assistant for FITRON. Price is 1999")  # digits -> rejected
    s.save()
    assert s.editors[("greeting", "en")].property("invalid") == "true"
    s.editors[("greeting", "en")].setPlainText("Hello {contact_person}, this is an automated assistant calling for FITRON.")
    s.save()
    wait_idle()
    assert s.last_error is None
    assert s.doc is not None and s.doc["title"] == "Sales script overrides"
    with backend.client() as c:
        docs = [d for d in c.get("/api/v1/knowledge", params={"category": "general"}).json() if d["title"] == "Sales script overrides"]
        assert docs and docs[-1]["structured"]["scripts"]["greeting"]["en"].startswith("Hello")
        assert docs[-1]["status"] == "pending"


def test_audio_test_manual_record_and_gate_stays_closed(window, backend):
    with backend.client() as c:
        r = c.post("/api/v1/audio-tests", json={"test_id": "ui-sim", "step": "remote_speech_capture", "direction": "inbound", "status": "pass", "kind": "simulated"})
        assert r.status_code == 201
    window.navigate("audio_tests")
    wait_idle()
    a = window.screens["audio_tests"]
    assert "GATE CLOSED" in a.gate_lbl.text()
    row = next(r for r in a.table.rows if r["step"] == "remote_speech_capture")
    assert row["latest"]["kind"] == "simulated"
    a.table.selectRow(a.table.rows.index(row))
    assert not a.confirm_btn.isEnabled()  # simulated rows can never be confirmed
