"""Milestone 2 Module 2 — staff attendance + leave approval integration tests (fictional demo data)."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login

IST = timezone(timedelta(hours=5, minutes=30))


def _today():
    return datetime.now(IST).date()


def _teacher_id(email="teacher@sunrise.demo"):
    u = db.users.find_one({"email": email})
    return str(db.teachers.find_one({"user_id": str(u["_id"])})["_id"])


def _reset(tid):
    db.staff_attendance.delete_many({"teacher_id": tid})
    db.leave_requests.delete_many({"teacher_id": tid})


def test_self_check_in_idempotent_and_visible_to_principal():
    tid = _teacher_id()
    _reset(tid)
    th = login("teacher@sunrise.demo")
    me = requests.get(f"{API}/staff/me/today", headers=th).json()
    assert me["status"] is None and me["check_in_at"] is None
    r = requests.post(f"{API}/staff/me/check-in", headers=th)
    assert r.status_code == 200 and r.json()["status"] in ("present", "late") and r.json()["check_in_at"]
    assert requests.post(f"{API}/staff/me/check-in", headers=th).status_code == 200
    assert db.staff_attendance.count_documents({"teacher_id": tid, "date": _today().isoformat()}) == 1
    pr = login("principal@sunrise.demo")
    reg = requests.get(f"{API}/staff/attendance", headers=pr).json()
    row = next(x for x in reg["rows"] if x["teacher_id"] == tid)
    assert row["source"] == "self" and row["status"] in ("present", "late")
    owner = login("owner@sunrise.demo")
    s = requests.get(f"{API}/staff/summary/today", headers=owner).json()
    assert s["total"] >= 1 and s["present"] + s["late"] >= 1
    _reset(tid)


def test_register_save_and_correction_requires_reason():
    tid = _teacher_id()
    _reset(tid)
    admin = login("admin@sunrise.demo")
    reg = requests.get(f"{API}/staff/attendance", headers=admin).json()
    others = [x["teacher_id"] for x in reg["rows"] if x["teacher_id"] != tid][:2]
    db.staff_attendance.delete_many({"teacher_id": {"$in": others}, "date": _today().isoformat()})
    recs = [{"teacher_id": tid, "status": "absent"}] + [{"teacher_id": o, "status": "present"} for o in others]
    r = requests.put(f"{API}/staff/attendance", headers=admin, json={"records": recs})
    assert r.status_code == 200
    assert next(x for x in r.json()["rows"] if x["teacher_id"] == tid)["status"] == "absent"
    recs[0]["status"] = "half_day"
    assert requests.put(f"{API}/staff/attendance", headers=admin, json={"records": recs}).status_code == 400
    ok = requests.put(f"{API}/staff/attendance", headers=admin, json={"records": recs, "reason": "Left at noon"})
    assert ok.status_code == 200
    doc = db.staff_attendance.find_one({"teacher_id": tid, "date": _today().isoformat()})
    assert doc["status"] == "half_day" and doc["corrections"][0]["reason"] == "Left at noon"
    # future date / foreign staff rejected
    fut = (_today() + timedelta(days=1)).isoformat()
    assert requests.put(f"{API}/staff/attendance?date={fut}", headers=admin, json={"records": recs}).status_code == 400
    gt = _teacher_id("teacher@greenfield.demo")
    assert requests.put(f"{API}/staff/attendance", headers=admin,
                        json={"records": [{"teacher_id": gt, "status": "present"}]}).status_code == 400
    db.staff_attendance.delete_many({"teacher_id": {"$in": others + [tid]}, "date": _today().isoformat()})


def test_leave_apply_approve_reflects_in_register_and_blocks_check_in():
    tid = _teacher_id()
    _reset(tid)
    th = login("teacher@sunrise.demo")
    d0, d1 = _today().isoformat(), (_today() + timedelta(days=1)).isoformat()
    bad = requests.post(f"{API}/staff/leave", headers=th, json={"type": "sick", "from_date": d1, "to_date": d0, "reason": "Fever"})
    assert bad.status_code == 400
    r = requests.post(f"{API}/staff/leave", headers=th, json={"type": "sick", "from_date": d0, "to_date": d1, "reason": "Fever"})
    assert r.status_code == 201 and r.json()["status"] == "pending" and r.json()["days"] == 2
    lid = r.json()["id"]
    overlap = requests.post(f"{API}/staff/leave", headers=th, json={"type": "casual", "from_date": d1, "to_date": d1, "reason": "Errand"})
    assert overlap.status_code == 409
    # admin can view but cannot approve; teacher cannot approve
    admin = login("admin@sunrise.demo")
    lst = requests.get(f"{API}/staff/leave?status=pending", headers=admin).json()
    assert any(x["id"] == lid for x in lst["items"]) and lst["pending"] >= 1
    assert requests.post(f"{API}/staff/leave/{lid}/decision", headers=admin, json={"approve": True}).status_code == 403
    assert requests.post(f"{API}/staff/leave/{lid}/decision", headers=th, json={"approve": True}).status_code == 403
    pr = login("principal@sunrise.demo")
    ok = requests.post(f"{API}/staff/leave/{lid}/decision", headers=pr, json={"approve": True, "note": "Get well soon"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    again = requests.post(f"{API}/staff/leave/{lid}/decision", headers=pr, json={"approve": False, "note": "x"})
    assert again.status_code == 409
    reg = requests.get(f"{API}/staff/attendance", headers=pr).json()
    assert next(x for x in reg["rows"] if x["teacher_id"] == tid)["status"] == "on_leave"
    assert requests.post(f"{API}/staff/me/check-in", headers=th).status_code == 400
    mine = requests.get(f"{API}/staff/leave/mine", headers=th).json()
    assert mine["items"][0]["status"] == "approved" and mine["items"][0]["decision_note"] == "Get well soon"
    assert db.audit_logs.find_one({"action": "leave.approve", "entity_id": lid})
    _reset(tid)


def test_reject_needs_note_and_cancel_rules():
    tid = _teacher_id()
    _reset(tid)
    th = login("teacher@sunrise.demo")
    d = (_today() + timedelta(days=10)).isoformat()
    lid = requests.post(f"{API}/staff/leave", headers=th, json={"type": "casual", "from_date": d, "to_date": d, "reason": "Family function"}).json()["id"]
    owner = login("owner@sunrise.demo")
    assert requests.post(f"{API}/staff/leave/{lid}/decision", headers=owner, json={"approve": False}).status_code == 400
    assert requests.post(f"{API}/staff/leave/{lid}/decision", headers=owner, json={"approve": False, "note": "Exam week"}).json()["status"] == "rejected"
    assert requests.post(f"{API}/staff/leave/{lid}/cancel", headers=th).status_code == 404  # not pending anymore
    lid2 = requests.post(f"{API}/staff/leave", headers=th, json={"type": "casual", "from_date": d, "to_date": d, "reason": "Family function"}).json()["id"]
    assert requests.post(f"{API}/staff/leave/{lid2}/cancel", headers=th).json()["status"] == "cancelled"
    _reset(tid)


def test_staff_endpoints_permissions_and_tenancy():
    th = login("teacher@sunrise.demo")
    ph = login("parent@sunrise.demo")
    for h in (th, ph):
        assert requests.get(f"{API}/staff/attendance", headers=h).status_code == 403
        assert requests.get(f"{API}/staff/leave", headers=h).status_code == 403
    assert requests.post(f"{API}/staff/me/check-in", headers=ph).status_code == 403
    assert requests.get(f"{API}/staff/summary/today", headers=th).status_code == 403
    # cross-school: greenfield principal cannot decide a sunrise leave
    tid = _teacher_id()
    _reset(tid)
    d = (_today() + timedelta(days=12)).isoformat()
    lid = requests.post(f"{API}/staff/leave", headers=th, json={"type": "earned", "from_date": d, "to_date": d, "reason": "Travel"}).json()["id"]
    g = login("principal@greenfield.demo")
    assert requests.post(f"{API}/staff/leave/{lid}/decision", headers=g, json={"approve": True}).status_code == 404
    assert all(x["id"] != lid for x in requests.get(f"{API}/staff/leave", headers=g).json()["items"])
    assert requests.get(f"{API}/staff/attendance").status_code == 401
    _reset(tid)
