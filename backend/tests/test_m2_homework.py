"""Milestone 2 Module 3 — homework integration tests (fictional demo data)."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login

IST = timezone(timedelta(hours=5, minutes=30))
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _d(n=0):
    return (datetime.now(IST).date() + timedelta(days=n)).isoformat()


def _teacher_slot(th):
    """A (section, subject) the demo teacher teaches where parent@sunrise.demo has a verified child (deterministic)."""
    from bson import ObjectId
    u = db.users.find_one({"email": "teacher@sunrise.demo"})
    t = db.teachers.find_one({"user_id": str(u["_id"])})
    pu = db.users.find_one({"email": "parent@sunrise.demo"})
    gids = [str(g["_id"]) for g in db.guardians.find({"user_id": str(pu["_id"])})]
    kids = [lk["student_id"] for lk in db.guardian_links.find({"guardian_id": {"$in": gids}, "verified": True})]
    secs = {s["section_id"] for s in db.students.find({"_id": {"$in": [ObjectId(k) for k in kids]}})}
    asg = sorted(db.teacher_assignments.find({"teacher_id": str(t["_id"]), "subject_id": {"$ne": None}}),
                 key=lambda a: (a["section_id"] not in secs, str(a["section_id"]), str(a["subject_id"])))
    a = asg[0]
    return a["section_id"], a["subject_id"], str(t["_id"])


def _cleanup():
    db.homework.delete_many({"title": {"$regex": "^TEST "}})


def test_teacher_creates_publishes_and_parent_sees_with_attachment():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, sub, _ = _teacher_slot(th)
    up = requests.post(f"{API}/homework/attachments", headers=th, files={"file": ("sheet.pdf", PDF, "application/pdf")})
    assert up.status_code == 201, up.text
    fid = up.json()["id"]
    bad_type = requests.post(f"{API}/homework/attachments", headers=th, files={"file": ("x.txt", b"hi", "text/plain")})
    assert bad_type.status_code == 400
    assert requests.post(f"{API}/homework", headers=th, json={"section_id": sec, "subject_id": sub, "title": "TEST past",
                                                              "due_date": _d(-1)}).status_code == 400
    r = requests.post(f"{API}/homework", headers=th, json={"section_id": sec, "subject_id": sub, "title": "TEST Fractions",
                                                           "description": "Ex 3.2 Q1-10", "due_date": _d(2), "attachments": [fid]})
    assert r.status_code == 201 and r.json()["status"] == "draft" and r.json()["attachments"][0]["id"] == fid
    hid = r.json()["id"]
    # find a parent of a child in this section (verified link) and give them access via a demo parent if present
    stu_ids = [str(s["_id"]) for s in db.students.find({"section_id": sec, "status": "active"})]
    link = db.guardian_links.find_one({"student_id": {"$in": stu_ids}, "verified": True})
    g = db.guardians.find_one({"_id": __import__("bson").ObjectId(link["guardian_id"])})
    parent_user = db.users.find_one({"_id": __import__("bson").ObjectId(g["user_id"])}) if g.get("user_id") else None
    if parent_user:
        ph = login(parent_user["email"])
        assert all(h["id"] != hid for h in requests.get(f"{API}/parent/children/{link['student_id']}/homework", headers=ph).json()["items"])
        assert requests.get(f"{API}/files/{fid}", headers={"Authorization": ph["Authorization"]}).status_code == 403  # draft
    pub = requests.post(f"{API}/homework/{hid}/publish", headers=th)
    assert pub.status_code == 200 and pub.json()["status"] == "published" and pub.json()["published_at"]
    if parent_user:
        items = requests.get(f"{API}/parent/children/{link['student_id']}/homework", headers=ph).json()["items"]
        mine = next(h for h in items if h["id"] == hid)
        assert mine["subject_name"] and mine["my_status"] is None and "created_by" not in mine
        f = requests.get(f"{API}/files/{fid}", headers={"Authorization": ph["Authorization"]})
        assert f.status_code == 200 and "no-store" in f.headers["Cache-Control"]
    # completion tracking flows to parent
    comp = requests.put(f"{API}/homework/{hid}/completion", headers=th, json={"records": [{"student_id": link["student_id"], "status": "done"}]})
    assert comp.status_code == 200 and comp.json()["completion_counts"]["done"] == 1
    if parent_user:
        items = requests.get(f"{API}/parent/children/{link['student_id']}/homework", headers=ph).json()["items"]
        assert next(h for h in items if h["id"] == hid)["my_status"] == "done"
    owner = login("owner@sunrise.demo")
    s = requests.get(f"{API}/homework/summary", headers=owner).json()
    assert s["published_this_week"] >= 1 and s["sections_with_homework_this_week"] >= 1
    assert db.audit_logs.find_one({"action": "homework.publish", "entity_id": hid})
    _cleanup()


def test_teacher_cannot_assign_outside_their_subjects_and_others_isolated():
    _cleanup()
    th = login("teacher@sunrise.demo")
    _, _, tid = _teacher_slot(th)
    mine = {a["section_id"] for a in db.teacher_assignments.find({"teacher_id": tid})}
    admin = login("admin@sunrise.demo")
    other = next(s["id"] for s in requests.get(f"{API}/sections?page_size=100", headers=admin).json()["items"] if s["id"] not in mine)
    sub = requests.get(f"{API}/subjects?page_size=1", headers=admin).json()["items"][0]["id"]
    assert requests.post(f"{API}/homework", headers=th, json={"section_id": other, "subject_id": sub, "title": "TEST no",
                                                              "due_date": _d(1)}).status_code == 403
    # admin can assign anywhere and teacher cannot read/modify admin's homework in a foreign section
    r = requests.post(f"{API}/homework", headers=admin, json={"section_id": other, "subject_id": sub, "title": "TEST admin",
                                                              "due_date": _d(1), "publish": True})
    assert r.status_code == 201
    hid = r.json()["id"]
    assert requests.get(f"{API}/homework/{hid}", headers=th).status_code == 403
    assert requests.patch(f"{API}/homework/{hid}", headers=th, json={"title": "TEST hack"}).status_code == 403
    assert all(h["id"] != hid for h in requests.get(f"{API}/homework", headers=th).json()["items"])
    assert any(h["id"] == hid for h in requests.get(f"{API}/homework?scope=all", headers=admin).json()["items"])
    # cross-school + parent + unauth
    g = login("owner@greenfield.demo")
    assert requests.get(f"{API}/homework/{hid}", headers=g).status_code == 404
    assert requests.post(f"{API}/homework", headers=g, json={"section_id": other, "subject_id": sub, "title": "TEST x",
                                                             "due_date": _d(1)}).status_code == 404
    ph = login("parent@sunrise.demo")
    assert requests.get(f"{API}/homework", headers=ph).status_code == 403
    assert requests.post(f"{API}/homework/attachments", headers=ph, files={"file": ("a.pdf", PDF, "application/pdf")}).status_code == 403
    assert requests.get(f"{API}/homework").status_code == 401
    # parent cannot see homework of a non-linked child
    kids = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    stranger = next(s["id"] for s in requests.get(f"{API}/students?page_size=50", headers=admin).json()["items"] if s["id"] not in kids)
    assert requests.get(f"{API}/parent/children/{stranger}/homework", headers=ph).status_code == 403
    # delete is soft and hides it
    assert requests.delete(f"{API}/homework/{hid}", headers=admin).status_code == 200
    assert requests.get(f"{API}/homework/{hid}", headers=admin).status_code == 404
    _cleanup()


def test_edit_due_date_validation_and_completion_requires_publish():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, sub, _ = _teacher_slot(th)
    hid = requests.post(f"{API}/homework", headers=th, json={"section_id": sec, "subject_id": sub, "title": "TEST edit",
                                                             "due_date": _d(1)}).json()["id"]
    assert requests.patch(f"{API}/homework/{hid}", headers=th, json={"due_date": _d(-3)}).status_code == 400
    assert requests.patch(f"{API}/homework/{hid}", headers=th, json={"due_date": _d(90)}).status_code == 400
    ok = requests.patch(f"{API}/homework/{hid}", headers=th, json={"due_date": _d(3), "title": "TEST edited"})
    assert ok.status_code == 200 and ok.json()["due_date"] == _d(3) and ok.json()["students"]
    stu = ok.json()["students"][0]["id"]
    assert requests.put(f"{API}/homework/{hid}/completion", headers=th, json={"records": [{"student_id": stu, "status": "done"}]}).status_code == 400
    _cleanup()
