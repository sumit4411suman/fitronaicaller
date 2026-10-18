from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import make_contact, open_hours

pytestmark = pytest.mark.automated


def _campaign(client, **over):
    body = {"name": "Oct launch", "calling_mode": "human_assisted"}
    body.update(over)
    r = client.post("/api/v1/campaigns", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_campaign_lifecycle_and_authorization_gate(client):
    c = _campaign(client)
    assert c["status"] == "draft"
    assert client.post(f"/api/v1/campaigns/{c['id']}/transition", json={"status": "active"}).status_code == 400
    assert client.post(f"/api/v1/campaigns/{c['id']}/transition", json={"status": "authorized"}).json()["authorized_by"] == "operator"
    # editing an authorized campaign drops it back to draft
    assert client.patch(f"/api/v1/campaigns/{c['id']}", json={"description": "x"}).json()["status"] == "draft"
    client.post(f"/api/v1/campaigns/{c['id']}/transition", json={"status": "authorized"})
    assert client.post(f"/api/v1/campaigns/{c['id']}/transition", json={"status": "active"}).json()["status"] == "active"
    assert client.post("/api/v1/campaigns", json={"name": "Oct launch"}).status_code == 400


def test_autonomous_campaign_cannot_be_authorized_while_gate_closed(client):
    c = _campaign(client, name="Auto", calling_mode="autonomous")
    r = client.post(f"/api/v1/campaigns/{c['id']}/transition", json={"status": "authorized"})
    assert r.status_code == 400 and "release gate" in r.json()["error"]


def test_campaign_membership_excludes_opted_out(client):
    camp = _campaign(client)
    a = make_contact(client)
    b = make_contact(client, business_name="Iron House", phone="9123456780")
    client.post(f"/api/v1/contacts/{b['id']}/opt-out", json={"reason": "no"})
    res = client.post(f"/api/v1/campaigns/{camp['id']}/contacts", json={"ids": [a["id"], b["id"], "missing"]}).json()
    assert res == {"added": 2, "skipped": 1, "excluded": 1}
    members = client.get(f"/api/v1/campaigns/{camp['id']}/contacts").json()
    statuses = {m["contact"]["id"]: m["membership"]["status"] for m in members}
    assert statuses[a["id"]] == "pending" and statuses[b["id"]] == "excluded"
    assert client.get(f"/api/v1/campaigns/{camp['id']}/stats").json()["total"] == 2


def test_call_job_blocked_without_consent_and_quiet_hours(client):
    open_hours(client)
    c = make_contact(client, consent_status="unknown")
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"]}).json()
    assert job["status"] == "blocked" and any("consent" in r for r in job["eligibility_result"]["reasons"])
    # quiet hours block (set a window covering the whole day)
    client.patch("/api/v1/settings", json={"values": {"calling.quiet_hours_start": "00:00", "calling.quiet_hours_end": "23:59"}})
    c2 = make_contact(client, business_name="B", phone="9123456780")
    job2 = client.post("/api/v1/call-jobs", json={"contact_id": c2["id"]}).json()
    assert job2["status"] == "blocked" and any("quiet hours" in r for r in job2["eligibility_result"]["reasons"])


def test_manual_route_full_call_flow_with_conversation_and_outcome(client):
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "manual"}).json()
    assert job["status"] == "pending" and job["eligibility_result"]["eligible"]
    # idempotent create
    assert client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "route": "manual"}).json()["id"] == job["id"]
    d = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch")
    assert d.status_code == 200, d.text
    call_id = d.json()["call_id"]
    assert d.json()["job"]["status"] == "in_progress" and d.json()["dial_number"] == "+919876543210"
    assert client.post(f"/api/v1/calls/{call_id}/connected").json()["conversation_state"] == "connected"
    t1 = client.post(f"/api/v1/calls/{call_id}/step", json={"utterance": None, "language": "en", "use_llm": False}).json()
    assert t1["state"] == "greeting" and "FITRON" in t1["agent_text"] and "automated" in t1["agent_text"].lower()
    t2 = client.post(f"/api/v1/calls/{call_id}/step", json={"utterance": "yes go ahead", "language": "en", "use_llm": False}).json()
    assert t2["state"] == "permission_to_continue"
    t3 = client.post(f"/api/v1/calls/{call_id}/step", json={"utterance": "how much does it cost?", "language": "en", "use_llm": False}).json()
    assert t3["state"] == "product_explanation" and "₹1,999" in t3["agent_text"] and t3["knowledge_refs"] and t3["knowledge_refs"][0].startswith("kb:")
    detail = client.get(f"/api/v1/calls/{call_id}").json()
    assert len(detail["transcript"]) >= 5 and detail["transcript"][-1]["knowledge_refs"]
    out = client.post(f"/api/v1/calls/{call_id}/outcome", json={"outcome": "demo_scheduled", "followup_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(), "followup_kind": "demo", "note": "wants Tue 5pm"}).json()
    assert out["followup_id"] and out["lead_stage"] == "demo_scheduled"
    assert client.get(f"/api/v1/call-jobs/{job['id']}").json()["status"] == "completed"
    hist = client.get("/api/v1/calls").json()
    assert hist["total"] == 1 and hist["items"][0]["outcome"] == "demo_scheduled"
    fus = client.get("/api/v1/followups").json()
    assert len(fus) == 1 and fus[0]["kind"] == "demo"
    assert client.post(f"/api/v1/followups/{fus[0]['id']}/complete").json()["status"] == "done"
    dash = client.get("/api/v1/reports/dashboard").json()
    assert dash["calls_week"] == 1 and dash["contacts_by_stage"]["demo_scheduled"] == 1 and dash["data_source"] == "live_database"


def test_opt_out_during_call_stops_everything(client):
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"]}).json()
    call_id = client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").json()["call_id"]
    client.post(f"/api/v1/calls/{call_id}/connected")
    client.post(f"/api/v1/calls/{call_id}/step", json={"utterance": None, "language": "hi", "use_llm": False})
    t = client.post(f"/api/v1/calls/{call_id}/step", json={"utterance": "mujhe call mat karo", "language": "hi", "use_llm": False}).json()
    assert t["state"] == "opted_out" and t["terminal"] and "सूची" in t["agent_text"]
    contact = client.get(f"/api/v1/contacts/{c['id']}").json()
    assert contact["opted_out"] and contact["lead_stage"] == "do_not_call"
    assert client.get("/api/v1/suppression").json()[0]["phone_e164"] == "+919876543210"
    assert client.get(f"/api/v1/call-jobs/{job['id']}").json()["status"] == "completed"
    # no further job can be created for this contact
    assert client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "idempotency_key": "second"}).json()["status"] == "blocked"
    assert client.post(f"/api/v1/calls/{call_id}/step", json={"utterance": "hello", "use_llm": False}).status_code == 400


def test_emergency_stop_cancels_jobs_and_blocks_new_ones(client):
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"]}).json()
    client.post(f"/api/v1/call-jobs/{job['id']}/dispatch")
    r = client.post("/api/v1/call-jobs/emergency-stop", json={"reason": "operator pressed stop"}).json()
    assert r["active"] and job["id"] in r["cancelled_jobs"]
    assert client.get(f"/api/v1/call-jobs/{job['id']}").json()["status"] == "cancelled"
    assert client.get("/api/v1/settings").json()["values"]["calling.emergency_stop_active"] is True
    c2 = make_contact(client, business_name="B", phone="9123456780")
    assert client.post("/api/v1/call-jobs", json={"contact_id": c2["id"]}).json()["status"] == "blocked"
    client.post("/api/v1/call-jobs/emergency-stop", json={"reason": "cleared", "activate": False})
    assert client.get("/api/v1/settings").json()["values"]["calling.emergency_stop_active"] is False
    audit = client.get("/api/v1/audit", params={"action": "emergency_stop"}).json()
    assert any(a["severity"] == "critical" for a in audit)


def test_autonomous_and_android_route_blocked_without_evidence(client):
    open_hours(client)
    c = make_contact(client)
    camp = _campaign(client)
    client.post(f"/api/v1/campaigns/{camp['id']}/transition", json={"status": "authorized"})
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"], "campaign_id": camp["id"], "mode": "autonomous", "route": "android_companion"}).json()
    reasons = " | ".join(job["eligibility_result"]["reasons"])
    assert job["status"] == "blocked" and "release gate" in reasons and "Android companion" in reasons
    routes = client.get("/api/v1/call-jobs/routes").json()
    assert routes["android_companion"]["autonomous_supported"] is False and routes["manual"]["autonomous_supported"] is False


def test_rate_limits(client):
    open_hours(client)
    client.patch("/api/v1/settings", json={"values": {"calling.max_calls_per_hour": 1}})
    a = make_contact(client)
    b = make_contact(client, business_name="B", phone="9123456780")
    j1 = client.post("/api/v1/call-jobs", json={"contact_id": a["id"]}).json()
    client.post(f"/api/v1/call-jobs/{j1['id']}/dispatch")
    j2 = client.post("/api/v1/call-jobs", json={"contact_id": b["id"]}).json()
    assert j2["status"] == "blocked" and any("hourly" in r for r in j2["eligibility_result"]["reasons"])


def test_cancel_and_requeue(client):
    open_hours(client)
    c = make_contact(client)
    job = client.post("/api/v1/call-jobs", json={"contact_id": c["id"]}).json()
    assert client.post(f"/api/v1/call-jobs/{job['id']}/queue").json()["status"] == "queued"
    assert client.post(f"/api/v1/call-jobs/{job['id']}/cancel", json={"reason": "changed mind"}).json()["status"] == "cancelled"
    assert client.post(f"/api/v1/call-jobs/{job['id']}/dispatch").status_code == 400
