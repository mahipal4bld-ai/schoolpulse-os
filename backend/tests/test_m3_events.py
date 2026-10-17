"""Milestone 3 Module 3 — events & calendar: lifecycle, targeting, exam merge, validation, permissions, tenancy."""
from datetime import date, timedelta

import requests
from bson import ObjectId

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import _teacher_slot

D = date.today() + timedelta(days=3)
RANGE = f"start={(D - timedelta(days=5)).isoformat()}&end={(D + timedelta(days=30)).isoformat()}"


def _cleanup():
    db.events.delete_many({"title": {"$regex": "^ETEST"}})


def _ids(h, extra=""):
    r = requests.get(f"{API}/calendar?{RANGE}{extra}", headers=h)
    assert r.status_code == 200, r.text
    return {i["id"]: i for i in r.json()["items"]}


def test_event_lifecycle_targeting_and_visibility():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, _, _ = _teacher_slot(th)
    ph, kid = _parent_for_section(sec)
    pr = login("principal@sunrise.demo")
    kids = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    kid_secs = {s["section_id"] for s in db.students.find({"_id": {"$in": [ObjectId(k) for k in kids]}})}
    t = db.teachers.find_one({"user_id": str(db.users.find_one({"email": "teacher@sunrise.demo"})["_id"])})
    t_secs = set(db.teacher_assignments.distinct("section_id", {"teacher_id": str(t["_id"])}))
    other = next(str(s["_id"]) for s in db.sections.find({"school_id": pr["X-School-Id"]})
                 if str(s["_id"]) not in kid_secs | t_secs)
    base = {"start_date": D.isoformat(), "start_time": "09:00", "end_time": "11:00", "category": "sports"}
    r = requests.post(f"{API}/events", headers=pr, json={**base, "title": "ETEST <b>Sports</b>", "location": "Ground",
                                                          "audience": {"scope": "sections", "section_ids": [sec]}, "action": "publish"})
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["status"] == "published" and ev["end_date"] == D.isoformat() and "<" not in ev["title"]
    hidden = requests.post(f"{API}/events", headers=pr, json={**base, "title": "ETEST other", "action": "publish",
                                                               "audience": {"scope": "sections", "section_ids": [other]}}).json()
    draft = requests.post(f"{API}/events", headers=pr, json={**base, "title": "ETEST draft"}).json()
    assert draft["status"] == "draft"
    # parent: targeted visible, other section + drafts hidden, admin fields stripped
    p = _ids(ph)
    assert ev["id"] in p and hidden["id"] not in p and draft["id"] not in p
    assert "audience" not in p[ev["id"]] and "created_by" not in p[ev["id"]]
    # teacher sees own section's event only
    tv = _ids(th)
    assert ev["id"] in tv and hidden["id"] not in tv and draft["id"] not in tv
    # manager sees everything incl. drafts
    m = _ids(pr)
    assert {ev["id"], hidden["id"], draft["id"]} <= set(m) and m[draft["id"]]["status"] == "draft"
    # accountant (non-manager staff) sees published only, cannot create
    acc = login("accountant@sunrise.demo")
    assert draft["id"] not in _ids(acc)
    assert requests.post(f"{API}/events", headers=acc, json={**base, "title": "ETEST no"}).status_code == 403
    assert requests.post(f"{API}/events", headers=th, json={**base, "title": "ETEST no"}).status_code == 403
    assert requests.post(f"{API}/events", headers=ph, json={**base, "title": "ETEST no"}).status_code == 403
    # draft cancelled silently -> never visible to parents; publish then cancel requires reason
    assert requests.post(f"{API}/events/{draft['id']}/action?act=publish", headers=pr).status_code == 200
    assert requests.post(f"{API}/events/{draft['id']}/action?act=publish", headers=pr).status_code == 409
    assert requests.post(f"{API}/events/{ev['id']}/action?act=cancel", headers=pr).status_code == 400
    c = requests.post(f"{API}/events/{ev['id']}/action?act=cancel&reason=Rain", headers=pr)
    assert c.status_code == 200 and c.json()["status"] == "cancelled" and c.json()["cancel_reason"] == "Rain"
    pc = _ids(ph)[ev["id"]]
    assert pc["status"] == "cancelled" and pc["cancel_reason"] == "Rain"
    assert ev["id"] not in {i["id"] for i in requests.get(f"{API}/calendar/upcoming?limit=10", headers=ph).json()["items"]}
    assert requests.patch(f"{API}/events/{ev['id']}", headers=pr, json={"title": "ETEST x"}).status_code == 400
    assert db.audit_logs.count_documents({"action": "event.cancelled", "entity_id": ev["id"]}) == 1
    # child filter: unrelated student -> 404
    stranger = db.students.find_one({"school_id": pr["X-School-Id"], "_id": {"$nin": [ObjectId(k) for k in kids]}})
    assert requests.get(f"{API}/calendar?{RANGE}&student_id={stranger['_id']}", headers=ph).status_code == 404
    assert ev["id"] in _ids(ph, f"&student_id={kid}")
    _cleanup()


def test_validation_edit_and_tenancy():
    _cleanup()
    pr = login("principal@sunrise.demo")
    ok = {"title": "ETEST v", "start_date": D.isoformat()}
    bad = [{**ok, "end_date": (D - timedelta(days=1)).isoformat()},
           {**ok, "end_date": (D + timedelta(days=90)).isoformat()},
           {**ok, "start_time": "25:00"},
           {**ok, "start_time": "10:00", "end_time": "09:00"},
           {**ok, "end_time": "09:00"},
           {**ok, "audience": {"scope": "sections", "section_ids": []}}]
    for b in bad:
        assert requests.post(f"{API}/events", headers=pr, json=b).status_code in (400, 422), b
    e = requests.post(f"{API}/events", headers=pr, json={**ok, "category": "holiday", "end_date": (D + timedelta(days=2)).isoformat(), "action": "publish"}).json()
    r = requests.patch(f"{API}/events/{e['id']}", headers=pr, json={"location": "Hall", "start_date": (D + timedelta(days=4)).isoformat()})
    assert r.status_code == 200 and r.json()["end_date"] == (D + timedelta(days=4)).isoformat()
    assert requests.get(f"{API}/calendar?start=2026-01-01&end=2026-12-31", headers=pr).status_code == 400
    # cross-tenant: Greenfield cannot see or act on Sunrise events
    g = login("owner@greenfield.demo")
    assert e["id"] not in _ids(g)
    assert requests.post(f"{API}/events/{e['id']}/action?act=cancel&reason=x", headers=g).status_code == 404
    assert requests.patch(f"{API}/events/{e['id']}", headers=g, json={"title": "ETEST hack"}).status_code == 404
    gp = login("parent@greenfield.demo")
    assert e["id"] not in _ids(gp)
    _cleanup()


def test_exams_appear_in_calendar_scoped():
    pr = login("principal@sunrise.demo")
    ex = db.exams.find_one({"school_id": pr["X-School-Id"], "status": {"$ne": "deleted"}})
    if not ex:
        return
    rng = f"start={ex['start_date']}&end={ex['start_date']}"
    items = requests.get(f"{API}/calendar?{rng}", headers=pr).json()["items"]
    x = next(i for i in items if i["id"] == str(ex["_id"]))
    assert x["kind"] == "exam" and isinstance(x["papers"], list)
    # a parent sees the exam only when a child's section is in it
    ph = login("parent@sunrise.demo")
    kids = [k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]]
    secs = {s["section_id"] for s in db.students.find({"_id": {"$in": [ObjectId(k) for k in kids]}})}
    seen = str(ex["_id"]) in {i["id"] for i in requests.get(f"{API}/calendar?{rng}", headers=ph).json()["items"]}
    assert seen == bool(secs & set(ex["section_ids"]))


def test_leader_cannot_post_in_escalated_conversation():
    h = login("principal@sunrise.demo")
    cid = db.conversations.insert_one({"school_id": h["X-School-Id"], "status": "escalated", "guardian_user_id": "x",
                                       "teacher_user_id": "y", "student_id": str(ObjectId()), "teacher_id": str(ObjectId()),
                                       "etest": True}).inserted_id
    try:
        r = requests.post(f"{API}/conversations/{cid}/messages", headers=h, json={"body": "hi", "client_id": "leader-test-01"})
        assert r.status_code == 403, r.text
        assert db.messages.count_documents({"conversation_id": str(cid)}) == 0
    finally:
        db.conversations.delete_one({"_id": cid})
