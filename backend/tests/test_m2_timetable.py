"""Milestone 2 Module 5 — timetable integration tests (fictional demo data)."""
import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import _teacher_slot


def _free_slot(sec):
    taken = {(s["day"], s["period"]) for s in db.timetable_slots.find({"section_id": sec})}
    return next((d, p) for d in range(1, 7) for p in range(1, 9) if (d, p) not in taken)


def test_admin_sets_slot_teacher_and_parent_see_it_and_conflicts_blocked():
    th = login("teacher@sunrise.demo")
    sec, sub, tid = _teacher_slot(th)
    admin = login("admin@sunrise.demo")
    grid = requests.get(f"{API}/timetable/sections/{sec}", headers=admin).json()
    assert len(grid["periods"]) >= 1 and grid["teacher_options"] and grid["subjects"]
    d, p = _free_slot(sec)
    # make the teacher free at (d,p) elsewhere first
    db.timetable_slots.delete_many({"teacher_id": tid, "day": d, "period": p})
    r = requests.put(f"{API}/timetable/sections/{sec}/slots", headers=admin,
                     json={"day": d, "period": p, "subject_id": sub, "teacher_id": tid, "room": "R-TEST1"})
    assert r.status_code == 200
    assert any(s["day"] == d and s["period"] == p and s["teacher_id"] == tid for s in r.json()["slots"])
    mine = requests.get(f"{API}/timetable/teacher/me", headers=th).json()
    assert any(s["day"] == d and s["period"] == p and s["section_id"] == sec for s in mine["slots"])
    ph, kid = _parent_for_section(sec)
    pt = requests.get(f"{API}/parent/children/{kid}/timetable", headers=ph).json()
    slot = next(s for s in pt["slots"] if s["day"] == d and s["period"] == p)
    assert slot["subject_name"] and "teacher_id" not in slot
    # teacher conflict: same teacher, same time, another section where they also teach
    other = next((a["section_id"] for a in db.teacher_assignments.find({"teacher_id": tid}) if a["section_id"] != sec), None)
    if other:
        a = db.teacher_assignments.find_one({"teacher_id": tid, "section_id": other})
        c = requests.put(f"{API}/timetable/sections/{other}/slots", headers=admin,
                         json={"day": d, "period": p, "subject_id": a["subject_id"], "teacher_id": tid})
        assert c.status_code == 409 and "Conflict" in c.json()["detail"]
    # room conflict
    other_sec = next(s["id"] for s in requests.get(f"{API}/sections?page_size=100", headers=admin).json()["items"] if s["id"] != sec)
    rc = requests.put(f"{API}/timetable/sections/{other_sec}/slots", headers=admin,
                      json={"day": d, "period": p, "subject_id": sub, "room": "R-TEST1"})
    assert rc.status_code == 409
    # teacher not assigned for subject
    unassigned = next(t for t in db.teachers.find({"school_id": grid and db.sections.find_one({})["school_id"]})
                      if not db.teacher_assignments.find_one({"teacher_id": str(t["_id"]), "section_id": sec}))
    bad = requests.put(f"{API}/timetable/sections/{sec}/slots", headers=admin,
                       json={"day": d, "period": p, "subject_id": sub, "teacher_id": str(unassigned["_id"])})
    assert bad.status_code in (400, 404)
    assert requests.get(f"{API}/timetable/conflicts", headers=admin).json()["items"] == []
    clr = requests.delete(f"{API}/timetable/sections/{sec}/slots?day={d}&period={p}", headers=admin)
    assert clr.status_code == 200 and not any(s["day"] == d and s["period"] == p for s in clr.json()["slots"])


def test_settings_validation_and_permissions():
    admin = login("admin@sunrise.demo")
    cur = requests.get(f"{API}/timetable/settings", headers=admin).json()["periods"]
    bad = [{"start": "09:00", "end": "08:00"}]
    assert requests.put(f"{API}/timetable/settings", headers=admin, json={"periods": bad}).status_code == 400
    overlap = [{"start": "08:00", "end": "09:00"}, {"start": "08:30", "end": "09:30"}]
    assert requests.put(f"{API}/timetable/settings", headers=admin, json={"periods": overlap}).status_code == 400
    assert requests.put(f"{API}/timetable/settings", headers=admin, json={"periods": [{"start": "8am", "end": "9"}]}).status_code == 422
    ok = requests.put(f"{API}/timetable/settings", headers=admin, json={"periods": [{"start": p["start"], "end": p["end"]} for p in cur]})
    assert ok.status_code == 200 and len(ok.json()["periods"]) == len(cur)
    th = login("teacher@sunrise.demo")
    sec, sub, tid = _teacher_slot(th)
    assert requests.put(f"{API}/timetable/settings", headers=th, json={"periods": cur}).status_code == 403
    assert requests.put(f"{API}/timetable/sections/{sec}/slots", headers=th, json={"day": 1, "period": 1, "subject_id": sub}).status_code == 403
    assert "teacher_options" not in requests.get(f"{API}/timetable/sections/{sec}", headers=th).json()
    mine = {a["section_id"] for a in db.teacher_assignments.find({"teacher_id": tid})}
    other = next(s["id"] for s in requests.get(f"{API}/sections?page_size=100", headers=admin).json()["items"] if s["id"] not in mine)
    assert requests.get(f"{API}/timetable/sections/{other}", headers=th).status_code == 403
    g = login("owner@greenfield.demo")
    assert requests.get(f"{API}/timetable/sections/{sec}", headers=g).status_code == 404
    assert requests.put(f"{API}/timetable/sections/{sec}/slots", headers=g, json={"day": 1, "period": 1, "subject_id": sub}).status_code == 404
    ph = login("parent@sunrise.demo")
    kids = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    stranger = next(s["id"] for s in requests.get(f"{API}/students?page_size=50", headers=admin).json()["items"] if s["id"] not in kids)
    assert requests.get(f"{API}/parent/children/{stranger}/timetable", headers=ph).status_code == 403
    assert requests.get(f"{API}/timetable/teacher/me", headers=ph).status_code == 403
