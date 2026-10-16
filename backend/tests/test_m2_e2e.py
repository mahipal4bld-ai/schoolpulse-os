"""Milestone 2 Part C — end-to-end academic workflow: teacher → principal → parent → owner."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import PDF, _teacher_slot

IST = timezone(timedelta(hours=5, minutes=30))


def test_full_academic_day():
    day = datetime.now(IST).date()
    d = day.isoformat()
    th = login("teacher@sunrise.demo")
    sec, sub, tid = _teacher_slot(th)
    ph, kid = _parent_for_section(sec)
    pr = login("principal@sunrise.demo")
    owner = login("owner@sunrise.demo")
    db.attendance.delete_many({"section_id": sec, "date": d})
    db.staff_attendance.delete_many({"teacher_id": tid})
    db.leave_requests.delete_many({"teacher_id": tid})
    for c, f in (("homework", "title"), ("diary", "topic"), ("exams", "name")):
        db[c].delete_many({f: {"$regex": "^E2E "}})
    try:
        # 1. teacher checks in, marks attendance, writes diary, publishes homework with attachment
        assert requests.post(f"{API}/staff/me/check-in", headers=th).status_code == 200
        sheet = requests.get(f"{API}/attendance/sections/{sec}", headers=th)
        if sheet.status_code == 200:  # class teacher of this section
            recs = [{"student_id": s["id"], "status": "absent" if s["id"] == kid else "present"} for s in sheet.json()["students"]]
            assert requests.put(f"{API}/attendance/sections/{sec}", headers=th, json={"records": recs}).status_code == 200
        else:
            admin = login("admin@sunrise.demo")
            s2 = requests.get(f"{API}/attendance/sections/{sec}", headers=admin).json()
            recs = [{"student_id": s["id"], "status": "absent" if s["id"] == kid else "present"} for s in s2["students"]]
            assert requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": recs}).status_code == 200
        assert requests.post(f"{API}/diary", headers=th, json={"section_id": sec, "kind": "lesson", "subject_id": sub,
                                                               "topic": "E2E Lesson"}).status_code == 201
        fid = requests.post(f"{API}/homework/attachments", headers=th, files={"file": ("w.pdf", PDF, "application/pdf")}).json()["id"]
        hw = requests.post(f"{API}/homework", headers=th, json={"section_id": sec, "subject_id": sub, "title": "E2E Homework",
                                                                "due_date": (day + timedelta(days=1)).isoformat(), "attachments": [fid], "publish": True})
        assert hw.status_code == 201
        # 2. teacher applies for leave, principal approves
        lv = requests.post(f"{API}/staff/leave", headers=th, json={"type": "casual", "from_date": (day + timedelta(days=20)).isoformat(),
                                                                   "to_date": (day + timedelta(days=20)).isoformat(), "reason": "E2E family"}).json()
        assert requests.post(f"{API}/staff/leave/{lv['id']}/decision", headers=pr, json={"approve": True}).json()["status"] == "approved"
        # 3. principal runs an exam; teacher enters marks; principal publishes
        ex = requests.post(f"{API}/exams", headers=pr, json={"name": "E2E Exam", "start_date": d, "end_date": d, "section_ids": [sec],
                                                             "subjects": [{"subject_id": sub, "max_marks": 20, "pass_marks": 7}]}).json()
        ms = requests.get(f"{API}/exams/{ex['id']}/marks?section_id={sec}&subject_id={sub}", headers=th).json()
        marks = [{"student_id": s["id"], "marks": 15 if s["id"] == kid else 10} for s in ms["students"]]
        assert requests.put(f"{API}/exams/{ex['id']}/marks?section_id={sec}&subject_id={sub}", headers=th, json={"records": marks}).status_code == 200
        assert requests.post(f"{API}/exams/{ex['id']}/status?status=published", headers=pr).status_code == 200
        # 4. parent sees everything
        ov = requests.get(f"{API}/parent/children/{kid}/overview", headers=ph).json()
        assert ov["attendance"]["today"] == "absent"
        assert any(h["title"] == "E2E Homework" for h in ov["homework"]["next"])
        assert any(x["topic"] == "E2E Lesson" for x in ov["diary_today"])
        assert ov["latest_result"]["name"] == "E2E Exam" and ov["latest_result"]["percentage"] == 75.0 and ov["latest_result"]["rank"] == 1
        assert requests.get(f"{API}/files/{fid}", headers={"Authorization": ph["Authorization"]}).status_code == 200
        pdf = requests.get(f"{API}/exams/{ex['id']}/report-card/{kid}.pdf?school={ph['X-School-Id']}", headers={"Authorization": ph["Authorization"]})
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        # 5. owner intelligence + staff summary reflect the day
        intel = requests.get(f"{API}/dashboard/academic", headers=owner).json()
        assert next(c for c in intel["coverage"]["sections"] if c["section_id"] == sec)["homework"] >= 1
        assert intel["latest_exam"]["name"] == "E2E Exam"
        assert requests.get(f"{API}/staff/summary/today", headers=owner).json()["present"] + \
            requests.get(f"{API}/staff/summary/today", headers=owner).json()["late"] >= 1
        # 6. teacher workspace: diary for taught sections done, nothing for this exam pending
        ws = requests.get(f"{API}/teacher/workspace", headers=th).json()
        assert not any(t["kind"] == "diary" and t.get("section_id") == sec for t in ws["todo"])
    finally:
        db.attendance.delete_many({"section_id": sec, "date": d})
        db.staff_attendance.delete_many({"teacher_id": tid})
        db.leave_requests.delete_many({"teacher_id": tid})
        ids = [str(e["_id"]) for e in db.exams.find({"name": {"$regex": "^E2E "}})]
        db.exam_marks.delete_many({"exam_id": {"$in": ids}})
        for c, f in (("homework", "title"), ("diary", "topic"), ("exams", "name")):
            db[c].delete_many({f: {"$regex": "^E2E "}})
