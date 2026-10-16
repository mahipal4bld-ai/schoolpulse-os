"""Milestone 2 Module 1 — attendance integration tests (fictional demo data)."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db

IST = timezone(timedelta(hours=5, minutes=30))
PW = "Demo@1234"


def login(email):
    d = requests.post(f"{API}/auth/login", json={"email": email, "password": PW},
                      headers={"X-Forwarded-For": "198.51.100.77"}).json()
    return {"Authorization": f"Bearer {d['access_token']}", "X-School-Id": d["memberships"][0]["school_id"]}


def _clear(section_id, day):
    db.attendance.delete_many({"section_id": section_id, "date": day})


def _parent_child_section():
    """Section of parent@sunrise.demo's first verified child and a teacher authorised for it."""
    ph = login("parent@sunrise.demo")
    kid = requests.get(f"{API}/parent/children", headers=ph).json()["items"][0]
    return ph, kid


def test_absent_flows_to_parent_and_owner_and_correction_rules():
    ph, kid = _parent_child_section()
    sec, day = kid["section_id"], datetime.now(IST).date().isoformat()
    _clear(sec, day)
    admin = login("admin@sunrise.demo")  # academic.manage may mark any section
    sheet = requests.get(f"{API}/attendance/sections/{sec}", headers=admin).json()
    assert sheet["submitted"] is False and all(s["status"] is None for s in sheet["students"])
    owner = login("owner@sunrise.demo")
    before = requests.get(f"{API}/attendance/summary/today", headers=owner).json()
    recs = [{"student_id": s["id"], "status": "absent" if s["id"] == kid["id"] else "present"} for s in sheet["students"]]
    partial = requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": recs[:-1]})
    assert partial.status_code == 400  # must mark everyone
    r = requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": recs})
    assert r.status_code == 200 and r.json()["submitted"] and r.json()["submitted_at"]
    # parent sees today's absence
    pa = requests.get(f"{API}/parent/children/{kid['id']}/attendance", headers=ph).json()
    assert pa["today"] == "absent" and pa["absent"] >= 1
    # owner dashboard updates
    after = requests.get(f"{API}/attendance/summary/today", headers=owner).json()
    assert after["sections_marked"] == before["sections_marked"] + 1 and after["absent"] >= 1
    # duplicate submit is idempotent (no duplicate sheet)
    assert requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": recs}).status_code == 200
    assert db.attendance.count_documents({"section_id": sec, "date": day}) == 1
    # correction needs a reason and is logged
    recs2 = [{**x, "status": "late"} if x["student_id"] == kid["id"] else x for x in recs]
    assert requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": recs2}).status_code == 400
    ok = requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": recs2, "reason": "Arrived 9:10"})
    assert ok.status_code == 200 and ok.json()["corrections"] == 1
    assert requests.get(f"{API}/parent/children/{kid['id']}/attendance", headers=ph).json()["today"] == "late"
    rep = requests.get(f"{API}/attendance/reports/monthly?section_id={sec}", headers=admin).json()
    row = next(x for x in rep["rows"] if x["student_id"] == kid["id"])
    assert row["late"] >= 1 and rep["working_days"] >= 1
    _clear(sec, day)


def test_teacher_only_authorised_sections():
    th = login("teacher@sunrise.demo")
    dash = requests.get(f"{API}/teacher/dashboard", headers=th).json()
    mine = {s["section_id"] for s in dash["sections"]}
    assert all("attendance_marked" in s for s in dash["sections"])
    admin = login("admin@sunrise.demo")
    others = [s["id"] for s in requests.get(f"{API}/sections?page_size=100", headers=admin).json()["items"] if s["id"] not in mine]
    assert requests.get(f"{API}/attendance/sections/{others[0]}", headers=th).status_code == 403
    assert requests.put(f"{API}/attendance/sections/{others[0]}", headers=th,
                        json={"records": [{"student_id": "x", "status": "present"}]}).status_code == 403
    sec = sorted(mine)[0]
    sheet = requests.get(f"{API}/attendance/sections/{sec}", headers=th).json()
    assert sheet["section"]["id"] == sec
    # teacher cannot write a past date (correction of history is admin-only)
    y = (datetime.now(IST).date() - timedelta(days=3)).isoformat()
    _clear(sec, y)
    recs = [{"student_id": s["id"], "status": "present"} for s in sheet["students"]]
    assert requests.put(f"{API}/attendance/sections/{sec}?date={y}", headers=th, json={"records": recs}).status_code == 200
    recs[0]["status"] = "absent"
    assert requests.put(f"{API}/attendance/sections/{sec}?date={y}", headers=th, json={"records": recs, "reason": "x"}).status_code == 403
    _clear(sec, y)


def test_future_date_and_foreign_students_rejected():
    admin = login("admin@sunrise.demo")
    sec = requests.get(f"{API}/sections?page_size=1", headers=admin).json()["items"][0]["id"]
    fut = (datetime.now(IST).date() + timedelta(days=2)).isoformat()
    assert requests.get(f"{API}/attendance/sections/{sec}?date={fut}", headers=admin).status_code == 400
    g = login("owner@greenfield.demo")
    gs = requests.get(f"{API}/students?page_size=1", headers=g).json()["items"][0]["id"]
    bad = requests.put(f"{API}/attendance/sections/{sec}", headers=admin, json={"records": [{"student_id": gs, "status": "present"}]})
    assert bad.status_code == 400


def test_cross_school_and_other_family_denied():
    admin = login("admin@sunrise.demo")
    sec = requests.get(f"{API}/sections?page_size=1", headers=admin).json()["items"][0]["id"]
    g = login("owner@greenfield.demo")
    assert requests.get(f"{API}/attendance/sections/{sec}", headers=g).status_code == 404
    assert requests.get(f"{API}/attendance/reports/monthly?section_id={sec}", headers=g).status_code == 404
    ph, kid = _parent_child_section()
    other = next(s for s in requests.get(f"{API}/students?page_size=50", headers=admin).json()["items"] if s["id"] != kid["id"]
                 and s["id"] not in {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]})
    assert requests.get(f"{API}/parent/children/{other['id']}/attendance", headers=ph).status_code == 403
    assert requests.get(f"{API}/attendance/summary/today", headers=ph).status_code == 403
    assert requests.get(f"{API}/attendance/sections/{sec}").status_code == 401
