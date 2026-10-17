"""Milestone 3 Module 5 — help desk: create/idempotency/routing, privacy (internal notes, other families), lifecycle,
reopen window, rating, triage, concurrency, insights, tenancy."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
import requests
from bson import ObjectId

from test_audit_file_access import TEMP, _drop_temp
from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m3_ptm import _strangers


def _cleanup():
    ids = [str(t["_id"]) for t in db.tickets.find({"subject": {"$regex": "^HTEST"}})]
    db.ticket_messages.delete_many({"ticket_id": {"$in": ids}})
    db.notifications.delete_many({"entity_id": {"$in": ids}})
    db.tickets.delete_many({"subject": {"$regex": "^HTEST"}})


@pytest.fixture(autouse=True)
def _iso():
    db.login_limits.delete_many({})
    _cleanup()
    yield
    _cleanup()
    _drop_temp()


def _new(h, kid, cat="fees", cid=None, **kw):
    return requests.post(f"{API}/helpdesk/tickets", headers=h, json={"student_id": kid, "category": cat, "subject": "HTEST Fee receipt missing",
                         "body": "I paid the term fee but did not get a receipt.", "client_id": cid or uuid.uuid4().hex, **kw})


def _family():
    ph = login("parent@sunrise.demo")
    kid = requests.get(f"{API}/parent/children", headers=ph).json()["items"][0]["id"]
    return ph, kid


def test_create_route_privacy_and_idempotency():
    ph, kid = _family()
    acc = login("accountant@sunrise.demo")
    cid = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(lambda _: _new(ph, kid, cid=cid), range(5)))
    assert all(r.status_code in (200, 201) for r in res), [r.text for r in res]
    assert len({r.json()["id"] for r in res}) == 1 and db.tickets.count_documents({"client_id": cid}) == 1
    t = res[0].json()
    acc_uid = str(db.users.find_one({"email": "accountant@sunrise.demo"})["_id"])
    assert t["status"] == "assigned" and db.tickets.find_one({"_id": ObjectId(t["id"])})["assignee_user_id"] == acc_uid  # fees -> accountant
    assert "assignee_user_id" not in t and t["number"] >= 1
    # assignee can see + reply publicly and add an internal note; parent never sees the note
    assert t["id"] in {x["id"] for x in requests.get(f"{API}/helpdesk/tickets", headers=acc).json()["items"]}
    rc = uuid.uuid4().hex
    assert requests.post(f"{API}/helpdesk/tickets/{t['id']}/messages", headers=acc, json={"body": "Checking ledger", "internal": True, "client_id": uuid.uuid4().hex}).status_code == 201
    r1 = requests.post(f"{API}/helpdesk/tickets/{t['id']}/messages", headers=acc, json={"body": "We are checking this.", "client_id": rc})
    r2 = requests.post(f"{API}/helpdesk/tickets/{t['id']}/messages", headers=acc, json={"body": "We are checking this.", "client_id": rc})
    assert r1.status_code == 201 and r2.json()["duplicate"] is True
    pv = requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=ph).json()
    assert [m["body"] for m in pv["messages"]] == ["We are checking this."] and pv["status"] == "in_progress"
    assert pv["messages"][0]["author_name"] == "School office"  # staff identity not exposed to parents
    sv = requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=acc).json()
    assert len(sv["messages"]) == 2 and any(m["internal"] for m in sv["messages"])
    assert db.tickets.find_one({"_id": ObjectId(t["id"])})["first_response_at"] is not None
    assert requests.post(f"{API}/helpdesk/tickets/{t['id']}/messages", headers=ph, json={"body": "x", "internal": True, "client_id": uuid.uuid4().hex}).status_code == 403
    # other family / unassigned teacher / other school -> 404; child not mine -> 404
    (pb, kb), = _strangers(ph["X-School-Id"], [s["section_id"] for s in db.students.find({"_id": ObjectId(kid)})], 1)
    assert requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=pb).status_code == 404
    assert t["id"] not in {x["id"] for x in requests.get(f"{API}/helpdesk/tickets", headers=pb).json()["items"]}
    assert requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=login("teacher@sunrise.demo")).status_code == 404
    assert requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=login("principal@greenfield.demo")).status_code == 404
    assert _new(pb, kid).status_code == 404
    assert _new(login("accountant@sunrise.demo"), kid).status_code == 403
    assert "helpdesk.reply" in {n["type"] for n in requests.get(f"{API}/notifications", headers=ph).json()["items"]}


def test_lifecycle_reopen_window_rating_and_conflicts():
    ph, kid = _family()
    pr = login("principal@sunrise.demo")
    t = _new(ph, kid, cat="transport").json()
    tid = t["id"]
    mv = lambda h, s, note="": requests.post(f"{API}/helpdesk/tickets/{tid}/status", headers=h, json={"status": s, "note": note})  # noqa: E731
    assert mv(pr, "waiting_on_parent", "x").status_code == 409            # assigned -> waiting not allowed directly
    assert mv(pr, "in_progress").status_code == 200
    assert mv(pr, "waiting_on_parent").status_code == 400                  # note required
    assert mv(pr, "waiting_on_parent", "Which bus stop?").json()["status"] == "waiting_on_parent"
    requests.post(f"{API}/helpdesk/tickets/{tid}/messages", headers=ph, json={"body": "Stop 4, Green Park", "client_id": uuid.uuid4().hex})
    assert db.tickets.find_one({"_id": ObjectId(tid)})["status"] == "in_progress"  # parent reply returns it to the school
    assert mv(ph, "resolved").status_code == 409                           # parent cannot resolve
    assert requests.post(f"{API}/helpdesk/tickets/{tid}/rate", headers=ph, json={"score": 5}).status_code == 409  # not resolved yet
    assert mv(pr, "resolved", "Route updated").json()["status"] == "resolved"
    # concurrent conflicting transitions: exactly one wins
    with ThreadPoolExecutor(max_workers=2) as ex:
        a, b = ex.map(lambda f: f(), [lambda: mv(pr, "closed"), lambda: mv(ph, "in_progress", "Still wrong stop")])
    assert sorted([a.status_code, b.status_code]) == [200, 409], (a.text, b.text)
    s = db.tickets.find_one({"_id": ObjectId(tid)})
    if s["status"] == "in_progress":
        assert s["reopen_count"] == 1
        assert mv(pr, "resolved", "Fixed").status_code == 200
    # reopen window
    db.tickets.update_one({"_id": ObjectId(tid)}, {"$set": {"status": "resolved", "resolved_at": datetime.now(timezone.utc) - timedelta(days=8)}})
    assert mv(ph, "in_progress", "again").status_code == 409
    r = requests.post(f"{API}/helpdesk/tickets/{tid}/rate", headers=ph, json={"score": 4, "comment": "Thanks"})
    assert r.status_code == 200 and r.json()["rating"]["score"] == 4
    assert requests.post(f"{API}/helpdesk/tickets/{tid}/rate", headers=ph, json={"score": 1}).status_code == 409
    assert mv(pr, "closed").status_code == 200
    assert requests.post(f"{API}/helpdesk/tickets/{tid}/messages", headers=ph, json={"body": "hi", "client_id": uuid.uuid4().hex}).status_code == 409
    # parent can withdraw an open request
    t2 = _new(ph, kid, cat="other").json()
    assert requests.post(f"{API}/helpdesk/tickets/{t2['id']}/status", headers=ph, json={"status": "closed", "note": "Sorted"}).json()["status"] == "closed"
    assert db.audit_logs.count_documents({"entity_id": tid, "action": {"$regex": "^helpdesk"}}) >= 5


def test_triage_assign_permissions_insights_and_rate_limit():
    ph, kid = _family()
    pr = login("principal@sunrise.demo")
    th = login("teacher@sunrise.demo")
    t = _new(ph, kid, cat="other").json()
    tuid = str(db.users.find_one({"email": "teacher@sunrise.demo"})["_id"])
    assert requests.post(f"{API}/helpdesk/tickets/{t['id']}/triage", headers=th, json={"priority": "urgent"}).status_code == 403
    assert requests.post(f"{API}/helpdesk/tickets/{t['id']}/triage", headers=pr, json={"assignee_user_id": str(db.users.find_one({"email": "parent@sunrise.demo"})["_id"])}).status_code == 400
    r = requests.post(f"{API}/helpdesk/tickets/{t['id']}/triage", headers=pr, json={"assignee_user_id": tuid, "priority": "urgent", "category": "academics"})
    assert r.status_code == 200 and r.json()["priority"] == "urgent" and r.json()["assignee_name"]
    assert requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=th).status_code == 200      # now assigned
    assert requests.post(f"{API}/helpdesk/tickets/{t['id']}/status", headers=th, json={"status": "closed"}).status_code in (403, 409)
    db.tickets.update_one({"_id": ObjectId(t["id"])}, {"$set": {"sla_due_at": datetime.now(timezone.utc) - timedelta(hours=1)}})
    assert t["id"] in {x["id"] for x in requests.get(f"{API}/helpdesk/tickets?view=overdue", headers=pr).json()["items"]}
    ins = requests.get(f"{API}/helpdesk/insights", headers=pr).json()
    assert ins["overdue"] >= 1 and ins["open"] >= 1 and any(c["category"] == "academics" for c in ins["by_category"])
    for h in (th, ph, login("accountant@sunrise.demo")):
        assert requests.get(f"{API}/helpdesk/insights", headers=h).status_code == 403
    # reassign away -> previous assignee loses access immediately
    requests.post(f"{API}/helpdesk/tickets/{t['id']}/triage", headers=pr, json={"assignee_user_id": None})
    assert requests.get(f"{API}/helpdesk/tickets/{t['id']}", headers=th).status_code == 404
    # validation + rate limit (5/hour)
    assert _new(ph, kid, cat="nope").status_code == 422
    assert requests.post(f"{API}/helpdesk/tickets", headers=ph, json={"student_id": kid, "category": "fees", "subject": "HTEST", "body": "short", "client_id": uuid.uuid4().hex}).status_code == 422
    codes = [_new(ph, kid).status_code for _ in range(6)]
    assert 429 in codes
    assert requests.get(f"{API}/helpdesk/tickets/{'0' * 24}", headers=pr).status_code == 404
    assert requests.get(f"{API}/helpdesk/tickets/bad-id", headers=pr).status_code in (400, 404, 422)
