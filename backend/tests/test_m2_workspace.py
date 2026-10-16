"""Milestone 2 Module 7 — teacher workspace consolidation tests."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_homework import _teacher_slot

IST = timezone(timedelta(hours=5, minutes=30))


def test_workspace_reflects_attendance_diary_homework_and_marks():
    th = login("teacher@sunrise.demo")
    sec, sub, tid = _teacher_slot(th)
    today = datetime.now(IST).date()
    day = today.isoformat()
    w = requests.get(f"{API}/teacher/workspace", headers=th)
    assert w.status_code == 200
    w = w.json()
    assert w["date"] == day and all({"period", "subject_name", "section_label", "start"} <= set(s) for s in w["schedule"])
    if today.isoweekday() <= 6:
        assert w["counts"]["periods_today"] == db.timetable_slots.count_documents({"teacher_id": tid, "day": today.isoweekday()})
    # homework draft shows up as a to-do, publishing clears it
    db.homework.delete_many({"title": {"$regex": "^TEST "}})
    hid = requests.post(f"{API}/homework", headers=th, json={"section_id": sec, "subject_id": sub, "title": "TEST ws",
                                                             "due_date": day}).json()["id"]
    w2 = requests.get(f"{API}/teacher/workspace", headers=th).json()
    assert w2["counts"]["homework_drafts"] == w["counts"]["homework_drafts"] + 1
    assert any(t["kind"] == "homework_drafts" for t in w2["todo"])
    requests.post(f"{API}/homework/{hid}/publish", headers=th)
    w3 = requests.get(f"{API}/teacher/workspace", headers=th).json()
    assert w3["counts"]["homework_due_today"] >= 1
    # exam sheet pending count
    admin = login("admin@sunrise.demo")
    eid = requests.post(f"{API}/exams", headers=admin, json={"name": "TEST ws exam", "start_date": day, "end_date": day, "section_ids": [sec],
                                                            "subjects": [{"subject_id": sub, "max_marks": 10, "pass_marks": 3}]}).json()["id"]
    w4 = requests.get(f"{API}/teacher/workspace", headers=th).json()
    assert w4["counts"]["marks_sheets_pending"] == w3["counts"]["marks_sheets_pending"] + 1
    # class-teacher attendance to-do disappears after marking
    ct = db.teacher_assignments.find_one({"teacher_id": tid, "is_class_teacher": True})
    if ct:
        db.attendance.delete_many({"section_id": ct["section_id"], "date": day})
        assert any(t["kind"] == "attendance" and t["section_id"] == ct["section_id"] for t in
                   requests.get(f"{API}/teacher/workspace", headers=th).json()["todo"])
        sheet = requests.get(f"{API}/attendance/sections/{ct['section_id']}", headers=th).json()
        requests.put(f"{API}/attendance/sections/{ct['section_id']}", headers=th,
                     json={"records": [{"student_id": s["id"], "status": "present"} for s in sheet["students"]]})
        assert not any(t["kind"] == "attendance" and t["section_id"] == ct["section_id"] for t in
                       requests.get(f"{API}/teacher/workspace", headers=th).json()["todo"])
        db.attendance.delete_many({"section_id": ct["section_id"], "date": day})
    db.exams.delete_many({"name": {"$regex": "^TEST "}})
    db.exam_marks.delete_many({"exam_id": eid})
    db.homework.delete_many({"title": {"$regex": "^TEST "}})
    # permissions
    assert requests.get(f"{API}/teacher/workspace", headers=admin).status_code == 403
    assert requests.get(f"{API}/teacher/workspace", headers=login("parent@sunrise.demo")).status_code == 403
