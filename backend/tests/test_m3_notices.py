"""Milestone 3 Module 1 — notices: targeting, scheduling, read vs acknowledge, attachments, edits, tenancy."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import PDF, _teacher_slot

IST = timezone(timedelta(hours=5, minutes=30))


def _cleanup():
    ids = [str(n["_id"]) for n in db.notices.find({"title": {"$regex": "^NTEST"}})]
    db.notice_receipts.delete_many({"notice_id": {"$in": ids}})
    db.notices.delete_many({"title": {"$regex": "^NTEST"}})


def test_targeted_notice_read_ack_stats_and_attachment():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, _, _ = _teacher_slot(th)
    ph, kid = _parent_for_section(sec)
    pr = login("principal@sunrise.demo")
    other_sec = next(str(s["_id"]) for s in db.sections.find({"school_id": pr["X-School-Id"]}) if str(s["_id"]) != sec
                     and not db.students.find_one({"section_id": str(s["_id"]), "_id": {"$in": [
                         x["_id"] for x in db.students.find({"section_id": sec})]}}))
    fid = requests.post(f"{API}/notices/attachments", headers=pr, files={"file": ("c.pdf", PDF, "application/pdf")}).json()["id"]
    r = requests.post(f"{API}/notices", headers=pr, json={
        "title": "NTEST <b>Sports day</b>", "body": "Bring <script>alert(1)</script>shoes", "priority": "important",
        "category": "event", "audience": {"scope": "sections", "section_ids": [sec]}, "attachments": [fid], "action": "publish"})
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["status"] == "published" and n["requires_ack"] and "<" not in n["title"] + n["body"]
    hidden = requests.post(f"{API}/notices", headers=pr, json={"title": "NTEST other", "body": "x", "action": "publish",
                                                               "audience": {"scope": "sections", "section_ids": [other_sec]}}).json()
    items = requests.get(f"{API}/parent/notices", headers=ph).json()["items"]
    mine = next(x for x in items if x["id"] == n["id"])
    assert not mine["read"] and "audience" not in mine and "created_by" not in mine
    pid = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    if not db.students.find_one({"section_id": other_sec, "_id": {"$in": [__import__("bson").ObjectId(k) for k in pid]}}):
        assert all(x["id"] != hidden["id"] for x in items)
        assert requests.post(f"{API}/parent/notices/{hidden['id']}/read", headers=ph).status_code == 404
    assert requests.get(f"{API}/files/{fid}", headers={"Authorization": ph["Authorization"]}).status_code == 200
    assert requests.get(f"{API}/files/{fid}", headers={"Authorization": login("accountant@sunrise.demo")["Authorization"]}).status_code == 403
    # read is not acknowledgement
    assert requests.post(f"{API}/parent/notices/{n['id']}/read", headers=ph).status_code == 200
    s = requests.get(f"{API}/notices/{n['id']}", headers=pr).json()["stats"]
    assert s["read"] == 1 and s["acknowledged"] == 0 and s["audience"] >= 1
    assert requests.post(f"{API}/parent/notices/{n['id']}/ack", headers=ph).status_code == 200
    assert requests.post(f"{API}/parent/notices/{n['id']}/ack", headers=ph).status_code == 200  # idempotent
    owner = login("owner@sunrise.demo")
    assert requests.get(f"{API}/notices/{n['id']}", headers=owner).json()["stats"]["acknowledged"] == 1
    assert db.audit_logs.count_documents({"action": "notice.acknowledge", "entity_id": n["id"]}) == 1
    # edits after publish need a reason and keep revisions
    assert requests.patch(f"{API}/notices/{n['id']}", headers=pr, json={"body": "Updated"}).status_code == 400
    e = requests.patch(f"{API}/notices/{n['id']}", headers=pr, json={"body": "Updated", "reason": "Venue change"})
    assert e.status_code == 200 and e.json()["revision_count"] == 1
    assert requests.get(f"{API}/notices/{n['id']}", headers=pr).json()["revisions"][0]["reason"] == "Venue change"
    # cancel -> disappears for parent
    assert requests.post(f"{API}/notices/{n['id']}/action?act=cancel", headers=pr).json()["status"] == "cancelled"
    assert all(x["id"] != n["id"] for x in requests.get(f"{API}/parent/notices", headers=ph).json()["items"])
    assert requests.post(f"{API}/notices/{n['id']}/action?act=publish", headers=pr).status_code == 409
    _cleanup()


def test_scheduling_expiry_drafts_and_permissions():
    _cleanup()
    pr = login("principal@sunrise.demo")
    ph = login("parent@sunrise.demo")
    future = (datetime.now(IST) + timedelta(hours=2)).replace(tzinfo=None).isoformat()  # naive = IST
    sch = requests.post(f"{API}/notices", headers=pr, json={"title": "NTEST scheduled", "body": "b", "publish_at": future,
                                                            "action": "publish"}).json()
    assert sch["status"] == "scheduled"
    assert all(x["id"] != sch["id"] for x in requests.get(f"{API}/parent/notices", headers=ph).json()["items"])
    db.notices.update_one({"_id": __import__("bson").ObjectId(sch["id"])}, {"$set": {"publish_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    assert any(x["id"] == sch["id"] for x in requests.get(f"{API}/parent/notices", headers=ph).json()["items"])  # auto-published
    db.notices.update_one({"_id": __import__("bson").ObjectId(sch["id"])}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert all(x["id"] != sch["id"] for x in requests.get(f"{API}/parent/notices", headers=ph).json()["items"])  # expired
    assert requests.get(f"{API}/notices/{sch['id']}", headers=pr).json()["status"] == "archived"
    d = requests.post(f"{API}/notices", headers=pr, json={"title": "NTEST draft", "body": "b", "action": "draft"}).json()
    assert d["status"] == "draft" and all(x["id"] != d["id"] for x in requests.get(f"{API}/parent/notices", headers=ph).json()["items"])
    assert requests.post(f"{API}/notices/{d['id']}/action?act=submit_review", headers=pr).json()["status"] == "review"
    # permissions + tenancy + validation
    for email in ("teacher@sunrise.demo", "accountant@sunrise.demo", "parent@sunrise.demo"):
        assert requests.post(f"{API}/notices", headers=login(email), json={"title": "NTEST x", "body": "b"}).status_code == 403
    assert requests.get(f"{API}/notices", headers=ph).status_code == 403
    g = login("owner@greenfield.demo")
    assert requests.get(f"{API}/notices/{d['id']}", headers=g).status_code == 404
    gs = str(db.sections.find_one({"school_id": g["X-School-Id"]})["_id"])
    assert requests.post(f"{API}/notices", headers=pr, json={"title": "NTEST x", "body": "b", "audience": {"scope": "sections", "section_ids": [gs]}}).status_code == 400
    assert all(x["id"] != d["id"] for x in requests.get(f"{API}/notices", headers=g).json()["items"])
    assert requests.get(f"{API}/parent/notices").status_code == 401
    _cleanup()
