"""Milestone 2 Module 4 — class diary integration tests (fictional demo data)."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_homework import _teacher_slot

IST = timezone(timedelta(hours=5, minutes=30))


def _d(n=0):
    return (datetime.now(IST).date() + timedelta(days=n)).isoformat()


def _cleanup():
    db.diary.delete_many({"topic": {"$regex": "^TEST "}})


def _parent_for_section(sec):
    """A seeded parent account (not temp ACL users) with a verified child in the section."""
    from bson import ObjectId
    stu_ids = [str(s["_id"]) for s in db.students.find({"section_id": sec, "status": "active"})]
    for link in db.guardian_links.find({"student_id": {"$in": stu_ids}, "verified": True}).sort("_id", 1):
        g = db.guardians.find_one({"_id": ObjectId(link["guardian_id"]), "user_id": {"$ne": None}})
        u = g and db.users.find_one({"_id": ObjectId(g["user_id"]), "email": {"$regex": "\\.demo$"}})
        if u:
            return login(u["email"]), link["student_id"]
    raise AssertionError("no demo parent account for this section")


def test_teacher_writes_lesson_and_note_parent_reads():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, sub, _ = _teacher_slot(th)
    assert requests.post(f"{API}/diary", headers=th, json={"section_id": sec, "kind": "lesson", "topic": "TEST no subj"}).status_code == 400
    r = requests.post(f"{API}/diary", headers=th, json={"section_id": sec, "kind": "lesson", "subject_id": sub,
                                                        "topic": "TEST Photosynthesis", "summary": "Covered chlorophyll and light"})
    assert r.status_code == 201 and r.json()["date"] == _d() and r.json()["subject_name"]
    eid = r.json()["id"]
    n = requests.post(f"{API}/diary", headers=th, json={"section_id": sec, "kind": "note", "topic": "TEST Bring crayons tomorrow"})
    assert n.status_code == 201
    lst = requests.get(f"{API}/diary?section_id={sec}", headers=th).json()
    assert {eid, n.json()["id"]} <= {x["id"] for x in lst["items"]}
    ph, kid = _parent_for_section(sec)
    pd = requests.get(f"{API}/parent/children/{kid}/diary", headers=ph).json()
    assert any(x["id"] == eid and x["summary"] for x in pd["items"]) and all("created_by" not in x for x in pd["items"])
    up = requests.patch(f"{API}/diary/{eid}", headers=th, json={"summary": "Updated summary"})
    assert up.status_code == 200 and up.json()["summary"] == "Updated summary"
    owner = login("owner@sunrise.demo")
    s = requests.get(f"{API}/diary/summary/today", headers=owner).json()
    assert s["sections_with_diary"] >= 1 and s["entries"] >= 2
    assert requests.delete(f"{API}/diary/{eid}", headers=th).status_code == 200
    assert all(x["id"] != eid for x in requests.get(f"{API}/parent/children/{kid}/diary", headers=ph).json()["items"])
    assert db.audit_logs.find_one({"action": "diary.create", "entity_id": eid})
    _cleanup()


def test_date_rules_and_permissions():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, sub, tid = _teacher_slot(th)
    body = {"section_id": sec, "kind": "lesson", "subject_id": sub, "topic": "TEST dated"}
    assert requests.post(f"{API}/diary", headers=th, json={**body, "date": _d(1)}).status_code == 400  # future
    assert requests.post(f"{API}/diary", headers=th, json={**body, "date": _d(-10)}).status_code == 400  # too old for teacher
    assert requests.post(f"{API}/diary", headers=th, json={**body, "date": _d(-2)}).status_code == 201
    admin = login("admin@sunrise.demo")
    assert requests.post(f"{API}/diary", headers=admin, json={**body, "date": _d(-10)}).status_code == 201
    # teacher cannot edit admin's entry, nor write to a foreign section
    aid = requests.post(f"{API}/diary", headers=admin, json={**body, "topic": "TEST admin"}).json()["id"]
    assert requests.patch(f"{API}/diary/{aid}", headers=th, json={"topic": "TEST hack"}).status_code == 403
    mine = {a["section_id"] for a in db.teacher_assignments.find({"teacher_id": tid})}
    other = next(s["id"] for s in requests.get(f"{API}/sections?page_size=100", headers=admin).json()["items"] if s["id"] not in mine)
    assert requests.post(f"{API}/diary", headers=th, json={"section_id": other, "kind": "note", "topic": "TEST x"}).status_code == 403
    assert requests.get(f"{API}/diary?section_id={other}", headers=th).status_code == 403
    # cross-school, parent and other-family checks
    g = login("owner@greenfield.demo")
    assert requests.get(f"{API}/diary?section_id={sec}", headers=g).status_code == 404
    assert requests.patch(f"{API}/diary/{aid}", headers=g, json={"topic": "TEST g"}).status_code == 404
    ph = login("parent@sunrise.demo")
    assert requests.get(f"{API}/diary?section_id={sec}", headers=ph).status_code == 403
    kids = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    stranger = next(s["id"] for s in requests.get(f"{API}/students?page_size=50", headers=admin).json()["items"] if s["id"] not in kids)
    assert requests.get(f"{API}/parent/children/{stranger}/diary", headers=ph).status_code == 403
    assert requests.get(f"{API}/diary/summary/today", headers=th).status_code == 403
    _cleanup()
