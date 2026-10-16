"""Milestone 2 Module 9 — owner academic intelligence: figures must match the underlying records."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_homework import _teacher_slot

IST = timezone(timedelta(hours=5, minutes=30))


def test_intelligence_is_derived_from_records():
    owner = login("owner@sunrise.demo")
    sid = owner["X-School-Id"]
    th = login("teacher@sunrise.demo")
    sec, sub, _ = _teacher_slot(th)
    day = datetime.now(IST).date().isoformat()
    db.attendance.delete_many({"section_id": sec, "date": day})
    db.homework.delete_many({"title": {"$regex": "^TEST "}})
    before = requests.get(f"{API}/dashboard/academic", headers=owner)
    assert before.status_code == 200
    b = before.json()
    assert len(b["attendance"]["trend"]) == 14 and b["window_days"] == 14
    # mark one section all absent today -> today's trend point reflects it
    admin = login("admin@sunrise.demo")
    sheet = requests.get(f"{API}/attendance/sections/{sec}", headers=admin).json()
    requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": [{"student_id": s["id"], "status": "absent"} for s in sheet["students"]]})
    requests.post(f"{API}/homework", headers=th, json={"section_id": sec, "subject_id": sub, "title": "TEST intel", "due_date": day, "publish": True})
    a = requests.get(f"{API}/dashboard/academic", headers=owner).json()
    # recompute today's rate straight from the DB
    p = n = 0
    for sh in db.attendance.find({"school_id": sid, "date": day}):
        for r in sh["records"]:
            n += 1
            p += r["status"] != "absent"
    assert a["attendance"]["trend"][-1]["rate"] == round(100 * p / n, 1)
    cov = next(c for c in a["coverage"]["sections"] if c["section_id"] == sec)
    assert cov["homework"] == next(c for c in b["coverage"]["sections"] if c["section_id"] == sec)["homework"] + 1
    assert a["coverage"]["homework_published"] == db.homework.count_documents(
        {"school_id": sid, "status": "published", "assigned_date": {"$gte": a["from"]}})
    assert any(x["section_id"] == sec for x in a["attendance"]["lowest_sections"])
    assert requests.get(f"{API}/dashboard/academic?days=200", headers=owner).json()["window_days"] == 60
    db.attendance.delete_many({"section_id": sec, "date": day})
    db.homework.delete_many({"title": {"$regex": "^TEST "}})
    # permissions + tenancy
    assert requests.get(f"{API}/dashboard/academic", headers=th).status_code == 403
    assert requests.get(f"{API}/dashboard/academic", headers=login("parent@sunrise.demo")).status_code == 403
    g = requests.get(f"{API}/dashboard/academic", headers=login("owner@greenfield.demo")).json()
    assert all(c["section_id"] != sec for c in g["coverage"]["sections"])
