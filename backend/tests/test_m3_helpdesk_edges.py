"""Extra help-desk edge probes: cross-tenant, other-family, non-assigned teacher,
invalid status transitions, internal note leakage, mass-assignment on create."""
import os, time, uuid, requests, pytest
from pymongo import MongoClient

API = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"
PWD = "Demo@1234"
TAG = "HTEST-edges-" + uuid.uuid4().hex[:6]
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _flush_htest():
    """Drop HTEST tickets+messages so rate-limit counter is reset between creations."""
    ids = [t["_id"] for t in _db.tickets.find({"subject": {"$regex": "^HTEST"}}, {"_id": 1})]
    if ids:
        _db.tickets.delete_many({"_id": {"$in": ids}})
        _db.ticket_messages.delete_many({"ticket_id": {"$in": [str(i) for i in ids]}})


def _cid(): return "cid-" + uuid.uuid4().hex


def _login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, (email, r.text)
    j = r.json()
    sid = next(m["school_id"] for m in j["memberships"]) if j.get("memberships") else None
    return {"Authorization": f"Bearer {j['access_token']}", "X-School-Id": sid or ""}


def _me(h):
    return requests.get(f"{API}/me", headers=h, timeout=10).json()


@pytest.fixture(scope="module")
def ctx():
    _flush_htest()
    parent_sun = _login("parent@sunrise.demo")
    parent_green = _login("parent@greenfield.demo")
    acc = _login("accountant@sunrise.demo")
    principal = _login("principal@sunrise.demo")
    teacher = _login("teacher@sunrise.demo")
    pm = _me(parent_sun)
    kids = requests.get(f"{API}/parent/children", headers=parent_sun, timeout=10).json()["items"]
    assert kids, "parent has no verified children"
    sid = kids[0]["id"]
    return {"parent_sun": parent_sun, "parent_green": parent_green, "acc": acc,
            "principal": principal, "teacher": teacher, "sid": sid, "parent_me": pm}


def _create_ticket(h, sid, cat="fees", subj=None, body="Please help with this concern raised by parent."):
    _flush_htest()  # keep rate-limit clear between test creations
    payload = {"student_id": sid, "category": cat, "subject": subj or f"{TAG} subject",
               "body": body, "priority": "normal", "client_id": _cid()}
    return requests.post(f"{API}/helpdesk/tickets", headers=h, json=payload, timeout=15)


def test_create_fees_ticket_auto_assigned_to_accountant(ctx):
    r = _create_ticket(ctx["parent_sun"], ctx["sid"], "fees", subj=f"{TAG} fees auto")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "assigned"
    # parent should NOT see assignee_user_id or internal_count
    assert "assignee_user_id" not in t
    assert "internal_count" not in t
    # accountant should see it in list
    lst = requests.get(f"{API}/helpdesk/tickets?view=mine", headers=ctx["acc"], timeout=10).json()
    assert any(x["id"] == t["id"] for x in lst["items"])


def test_cross_tenant_ticket_hidden(ctx):
    r = _create_ticket(ctx["parent_sun"], ctx["sid"], "academics", subj=f"{TAG} cross")
    tid = r.json()["id"]
    # greenfield parent can't see sunrise ticket
    d = requests.get(f"{API}/helpdesk/tickets/{tid}", headers=ctx["parent_green"], timeout=10)
    assert d.status_code in (403, 404)


def test_other_family_cannot_see_ticket(ctx):
    r = _create_ticket(ctx["parent_sun"], ctx["sid"], "transport", subj=f"{TAG} fam")
    tid = r.json()["id"]
    # another same-school parent still with no claim to this ticket
    other = requests.get(f"{API}/helpdesk/tickets/{tid}",
                         headers={**ctx["parent_green"], "X-School-Id": ctx["parent_sun"]["X-School-Id"]},
                         timeout=10)
    assert other.status_code in (403, 404)


def test_non_assigned_teacher_cannot_see(ctx):
    r = _create_ticket(ctx["parent_sun"], ctx["sid"], "fees", subj=f"{TAG} tt")
    tid = r.json()["id"]
    # ordinary teacher is not the fees assignee -> no access
    d = requests.get(f"{API}/helpdesk/tickets/{tid}", headers=ctx["teacher"], timeout=10)
    assert d.status_code in (403, 404)


def test_invalid_transition_rejected(ctx):
    r = _create_ticket(ctx["parent_sun"], ctx["sid"], "fees", subj=f"{TAG} trans")
    tid = r.json()["id"]
    # accountant tries open -> waiting_on_parent (not allowed)
    r2 = requests.post(f"{API}/helpdesk/tickets/{tid}/status", headers=ctx["acc"],
                       json={"status": "waiting_on_parent", "note": "need info"}, timeout=10)
    assert r2.status_code == 409


def test_internal_note_not_leaked_to_parent(ctx):
    r = _create_ticket(ctx["parent_sun"], ctx["sid"], "fees", subj=f"{TAG} int")
    tid = r.json()["id"]
    # accountant adds internal note
    r2 = requests.post(f"{API}/helpdesk/tickets/{tid}/messages", headers=ctx["acc"],
                       json={"body": "INTERNAL-SECRET-XYZ", "internal": True, "client_id": _cid()}, timeout=10)
    assert r2.status_code == 201, r2.text
    # parent detail must not contain the body
    d = requests.get(f"{API}/helpdesk/tickets/{tid}", headers=ctx["parent_sun"], timeout=10).json()
    bodies = [m["body"] for m in d.get("messages", [])]
    assert "INTERNAL-SECRET-XYZ" not in bodies
    assert all(not m.get("internal") for m in d.get("messages", []))
    # parent list payload shouldn't surface internal_count
    lst = requests.get(f"{API}/helpdesk/tickets", headers=ctx["parent_sun"], timeout=10).json()
    for item in lst["items"]:
        assert "internal_count" not in item
        assert "assignee_user_id" not in item


def test_parent_cannot_post_internal_note(ctx):
    r = _create_ticket(ctx["parent_sun"], ctx["sid"], "fees", subj=f"{TAG} pint")
    tid = r.json()["id"]
    r2 = requests.post(f"{API}/helpdesk/tickets/{tid}/messages", headers=ctx["parent_sun"],
                       json={"body": "should not be internal", "internal": True, "client_id": _cid()}, timeout=10)
    assert r2.status_code == 403


def test_mass_assignment_on_create_ignored(ctx):
    extra = {"student_id": ctx["sid"], "category": "fees", "subject": f"{TAG} mass",
             "body": "Testing mass assignment protection please help.", "priority": "normal",
             "client_id": _cid(),
             "status": "resolved", "assignee_user_id": "deadbeefdeadbeefdeadbeef",
             "rating": {"score": 5}, "number": 999999}
    r = requests.post(f"{API}/helpdesk/tickets", headers=ctx["parent_sun"], json=extra, timeout=10)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] in ("assigned", "open")  # not 'resolved'
    assert t.get("rating") in (None, {}) or t.get("rating") is None
    # verify via GET
    d = requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=ctx["parent_sun"], timeout=10).json()
    assert d["status"] in ("assigned", "open")
