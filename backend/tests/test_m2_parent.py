"""Milestone 2 Module 8 — parent academic overview tests."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import _teacher_slot

IST = timezone(timedelta(hours=5, minutes=30))


def test_overview_aggregates_attendance_homework_diary_and_results():
    th = login("teacher@sunrise.demo")
    sec, sub, _ = _teacher_slot(th)
    ph, kid = _parent_for_section(sec)
    day = datetime.now(IST).date().isoformat()
    db.homework.delete_many({"title": {"$regex": "^TEST "}})
    db.diary.delete_many({"topic": {"$regex": "^TEST "}})
    base = requests.get(f"{API}/parent/children/{kid}/overview", headers=ph)
    assert base.status_code == 200
    b = base.json()
    assert {"attendance", "timetable_today", "homework", "diary_today", "latest_result"} <= set(b)
    hid = requests.post(f"{API}/homework", headers=th, json={"section_id": sec, "subject_id": sub, "title": "TEST ov hw",
                                                             "due_date": day, "publish": True}).json()["id"]
    requests.post(f"{API}/diary", headers=th, json={"section_id": sec, "kind": "lesson", "subject_id": sub, "topic": "TEST ov diary"})
    o = requests.get(f"{API}/parent/children/{kid}/overview", headers=ph).json()
    assert o["homework"]["due_count"] == b["homework"]["due_count"] + 1 and o["homework"]["due_today"] >= 1
    assert any(d["topic"] == "TEST ov diary" for d in o["diary_today"])
    # once marked done for this child it is no longer pending
    requests.put(f"{API}/homework/{hid}/completion", headers=th, json={"records": [{"student_id": kid, "status": "done"}]})
    o2 = requests.get(f"{API}/parent/children/{kid}/overview", headers=ph).json()
    assert o2["homework"]["due_count"] == b["homework"]["due_count"]
    db.homework.delete_many({"title": {"$regex": "^TEST "}})
    db.diary.delete_many({"topic": {"$regex": "^TEST "}})
    # access rules
    admin = login("admin@sunrise.demo")
    kids = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    stranger = next(s["id"] for s in requests.get(f"{API}/students?page_size=50", headers=admin).json()["items"] if s["id"] not in kids)
    assert requests.get(f"{API}/parent/children/{stranger}/overview", headers=ph).status_code == 403
    assert requests.get(f"{API}/parent/children/{kid}/overview", headers=th).status_code == 403
    assert requests.get(f"{API}/parent/children/{kid}/overview", headers=login("parent@greenfield.demo")).status_code in (403, 404)
