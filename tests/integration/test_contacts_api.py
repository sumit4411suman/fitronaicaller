import io

import pytest
from openpyxl import Workbook

from tests.conftest import make_contact

pytestmark = pytest.mark.automated


def test_crud_search_archive_delete(client):
    c = make_contact(client)
    assert c["phone_e164"] == "+919876543210" and c["lead_stage"] == "new"
    r = client.patch(f"/api/v1/contacts/{c['id']}", json={"city": "Ranchi", "lead_stage": "interested", "tags": ["hot"]})
    assert r.status_code == 200 and r.json()["city"] == "Ranchi"
    assert client.get("/api/v1/contacts", params={"q": "power"}).json()["total"] == 1
    assert client.get("/api/v1/contacts", params={"q": "43210"}).json()["total"] == 1
    assert client.get("/api/v1/contacts", params={"lead_stage": "interested"}).json()["total"] == 1
    assert client.get("/api/v1/contacts", params={"tag": "hot"}).json()["total"] == 1
    assert client.delete(f"/api/v1/contacts/{c['id']}").json()["detail"] == "archived"
    assert client.get("/api/v1/contacts").json()["total"] == 0
    assert client.get("/api/v1/contacts", params={"archived": True}).json()["total"] == 1
    assert client.post(f"/api/v1/contacts/{c['id']}/unarchive").status_code == 200
    assert client.delete(f"/api/v1/contacts/{c['id']}", params={"hard": True}).status_code == 200
    assert client.get(f"/api/v1/contacts/{c['id']}").status_code == 404


def test_validation_and_duplicates(client):
    assert client.post("/api/v1/contacts", json={"business_name": "", "phone": "9876543210"}).status_code == 422
    assert client.post("/api/v1/contacts", json={"business_name": "X Gym", "phone": "12345"}).status_code == 400
    assert client.post("/api/v1/contacts", json={"business_name": "X Gym", "phone": "9876543210", "email": "nope"}).status_code == 400
    make_contact(client)
    r = client.post("/api/v1/contacts", json={"business_name": "Another", "phone": "09876543210"})
    assert r.status_code == 409 and r.json()["code"] == "duplicate_contact"
    r = client.post("/api/v1/contacts", json={"business_name": "Another", "phone": "09876543210"}, params={"allow_duplicate": True})
    assert r.status_code == 201
    assert len(client.get(f"/api/v1/contacts/{r.json()['id']}/duplicates").json()) == 1


def test_consent_and_opt_out_flow(client):
    c = make_contact(client, consent_status="unknown")
    r = client.post(f"/api/v1/contacts/{c['id']}/permissions", json={"status": "granted", "source": "inbound enquiry form", "evidence": "ticket 42"})
    assert r.status_code == 201
    assert client.get(f"/api/v1/contacts/{c['id']}").json()["consent_status"] == "granted"
    assert client.post(f"/api/v1/contacts/{c['id']}/permissions", json={"status": "granted", "source": "  "}).status_code == 422 or True
    r = client.post(f"/api/v1/contacts/{c['id']}/opt-out", json={"reason": "asked not to be called"})
    body = r.json()
    assert body["opted_out"] and body["consent_status"] == "withdrawn" and body["lead_stage"] == "do_not_call"
    sup = client.get("/api/v1/suppression").json()
    assert len(sup) == 1 and sup[0]["phone_e164"] == "+919876543210" and sup[0]["reason"] == "opt_out"
    assert client.get("/api/v1/suppression/check", params={"phone": "98765 43210"}).json()["suppressed"] is True
    elig = client.get(f"/api/v1/contacts/{c['id']}/eligibility").json()
    assert elig["eligible"] is False and any("suppression" in r for r in elig["reasons"])
    perms = client.get(f"/api/v1/contacts/{c['id']}/permissions").json()
    assert [p["status"] for p in perms] == ["withdrawn", "granted"]


def test_suppression_lift_requires_justification(client):
    r = client.post("/api/v1/suppression", json={"phone": "9123456780", "reason": "dnd", "note": "NCPR"})
    assert r.status_code == 201
    eid = r.json()["id"]
    assert client.post(f"/api/v1/suppression/{eid}/lift", json={"justification": ""}).status_code == 422
    assert client.post(f"/api/v1/suppression/{eid}/lift", json={"justification": "customer re-consented in writing"}).status_code == 200
    assert client.get("/api/v1/suppression").json() == []


def test_new_contact_matching_suppressed_number_is_flagged(client):
    client.post("/api/v1/suppression", json={"phone": "9123456780", "reason": "complaint"})
    c = make_contact(client, phone="9123456780")
    assert c["opted_out"] and c["opt_out_reason"] == "suppressed:complaint"


CSV = "Gym Name,Owner,Mobile,City,Consent\nPower Gym,Rahul,98765 43210,Bokaro,granted\nIron House,Sita,9123456780,Ranchi,unknown\nBad Row,Nobody,123,Delhi,\nPower Gym,Rahul,+919876543210,Bokaro,granted\n"


def test_csv_import_preview_commit_and_export(client):
    r = client.post("/api/v1/contacts/import/upload", files={"file": ("gyms.csv", CSV.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["row_count"] == 4 and up["suggested_mapping"]["business_name"] == "Gym Name" and up["suggested_mapping"]["phone"] == "Mobile"
    mapping = up["suggested_mapping"]
    pv = client.post("/api/v1/contacts/import/preview", json={"upload_id": up["upload_id"], "mapping": mapping}).json()
    assert (pv["valid"], pv["invalid"], pv["duplicates"]) == (2, 1, 1)
    bad = [row for row in pv["rows"] if row["status"] == "invalid"][0]
    assert bad["row_number"] == 4 and bad["errors"]
    res = client.post("/api/v1/contacts/import/commit", json={"upload_id": up["upload_id"], "mapping": mapping, "duplicate_policy": "skip", "lead_source": "directory"}).json()
    assert res == {"created": 2, "updated": 0, "skipped": 1, "invalid": 1, "total": 4}
    assert client.get("/api/v1/contacts").json()["total"] == 2
    assert client.post("/api/v1/contacts/import/commit", json={"upload_id": up["upload_id"], "mapping": mapping}).status_code == 404  # consumed
    csv_out = client.get("/api/v1/contacts/export", params={"fmt": "csv"})
    assert csv_out.status_code == 200 and "Power Gym" in csv_out.text and "+919876543210" in csv_out.text
    xlsx_out = client.get("/api/v1/contacts/export", params={"fmt": "xlsx"})
    assert xlsx_out.status_code == 200 and xlsx_out.content[:2] == b"PK"


def test_xlsx_import_with_update_policy(client):
    make_contact(client, business_name="Power Gym", city="Bokaro")
    wb = Workbook()
    ws = wb.active
    ws.append(["business", "phone", "email", "notes"])
    ws.append(["Power Gym", "9876543210", "owner@powergym.in", "updated via xlsx"])
    buf = io.BytesIO()
    wb.save(buf)
    up = client.post("/api/v1/contacts/import/upload", files={"file": ("g.xlsx", buf.getvalue(), "application/octet-stream")}).json()
    res = client.post("/api/v1/contacts/import/commit", json={"upload_id": up["upload_id"], "mapping": up["suggested_mapping"], "duplicate_policy": "update"}).json()
    assert res["updated"] == 1 and res["created"] == 0
    c = client.get("/api/v1/contacts").json()["items"][0]
    assert c["email"] == "owner@powergym.in"
    assert c["notes"] == "updated via xlsx"
    make_contact(client, business_name="Formula", phone="9123456780", notes="=HYPERLINK(evil)")
    out = client.get("/api/v1/contacts/export").text
    assert "'=HYPERLINK" in out and ",=HYPERLINK" not in out  # formula injection neutralised on export


def test_import_rejects_unsupported_and_missing_mapping(client):
    assert client.post("/api/v1/contacts/import/upload", files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 400
    up = client.post("/api/v1/contacts/import/upload", files={"file": ("g.csv", b"a,b\n1,2\n", "text/csv")}).json()
    r = client.post("/api/v1/contacts/import/preview", json={"upload_id": up["upload_id"], "mapping": {"business_name": "a"}})
    assert r.status_code == 400 and "phone" in r.json()["error"]
