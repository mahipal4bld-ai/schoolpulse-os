"""Milestone 3 Module 4 — PTM edge probes: cross-tenant, parent A vs parent B, invalid ObjectIds,
mass-assignment, invalid state transitions, teacher not in session, invalid session/slot ids."""
from datetime import date, timedelta
import uuid

import pytest
import requests
from bson import ObjectId

from test_audit_file_access import TEMP, _drop_temp, _temp_user
from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_homework import _teacher_slot

D1 = (date.today() + timedelta(days=3)).isoformat()
D2 = (date.today() + timedelta(days=4)).isoformat()


def _cleanup():
    sids = [str(s["_id"]) for s in db.ptm_sessions.find({"name": {"$regex": "^PTEST"}})]
    bids = [str(b["_id"]) for b in db.ptm_bookings.find({"session_id": {"$in": sids}})]
    for c in ("ptm_slots", "ptm_bookings", "ptm_quotas", "ptm_followups"):
        db[c].delete_many({"session_id": {"$in": sids}})
    db.notifications.delete_many({"entity_id": {"$in": bids}})
    db.ptm_sessions.delete_many({"_id": {"$in": [ObjectId(s) for s in sids]}})
    db.ptm_unavailability.delete_many({"reason": {"$regex": "^PTEST"}})


@pytest.fixture(autouse=True)
def _iso():
    db.login_limits.delete_many({})
    _cleanup()
    yield
    _cleanup()
    _drop_temp()


def _ctx():
    th = login("teacher@sunrise.demo")
    sec, _sub, tid = _teacher_slot(th)
    pr = login("principal@sunrise.demo")
    year = str(db.academic_years.find_one({"school_id": pr["X-School-Id"], "is_current": True})["_id"])
    return th, pr, sec, tid, year


def _temp_parent(school, kid):
    email, uid, _ = _temp_user(school, "parent")
    gid = db.guardians.insert_one({"school_id": school, "name": "PTEST Guardian", "user_id": uid, "email": email,
                                   "phone": f"7{uuid.uuid4().int % 10**9:09d}"}).inserted_id
    lid = db.guardian_links.insert_one({"school_id": school, "student_id": kid, "guardian_id": str(gid),
                                        "relation": "guardian", "verified": True}).inserted_id
    TEMP.extend([("guardians", gid), ("guardian_links", lid)])
    return login(email)


def _strangers(school, sec, n):
    demo = [str(g["_id"]) for g in db.guardians.find({"school_id": school, "email": {"$regex": "\\.demo$"}})]
    demo_kids = {lk["student_id"] for lk in db.guardian_links.find({"guardian_id": {"$in": demo}})}
    studs = [str(s["_id"]) for s in db.students.find({"section_id": sec, "status": "active"})
             if str(s["_id"]) not in demo_kids][:n]
    assert len(studs) == n
    return [(_temp_parent(school, k), k) for k in studs]


def _session(pr, year, sec, tid, **kw):
    body = {"name": "PTEST edge", "academic_year_id": year, "section_ids": [sec], "teacher_ids": [tid],
            "dates": [D1], "start_time": "10:00", "end_time": "10:30", "slot_minutes": 10,
            "capacity": 1, "action": "publish", **kw}
    r = requests.post(f"{API}/ptm/sessions", headers=pr, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------ cross-tenant isolation
def test_cross_tenant_session_slot_and_booking_isolation():
    th, pr, sec, tid, year = _ctx()
    s = _session(pr, year, sec, tid)
    slot = str(db.ptm_slots.find_one({"session_id": s["id"]})["_id"])
    g_pr = login("principal@greenfield.demo")
    g_par = login("parent@greenfield.demo")
    # Greenfield admin cannot see Sunrise session or its slots
    assert requests.get(f"{API}/ptm/sessions/{s['id']}", headers=g_pr).status_code == 404
    assert requests.get(f"{API}/ptm/sessions/{s['id']}/slots?teacher_id={tid}", headers=g_pr).status_code == 404
    # cannot cancel/publish/edit someone else's session
    assert requests.post(f"{API}/ptm/sessions/{s['id']}/cancel?reason=hack", headers=g_pr).status_code == 404
    assert requests.post(f"{API}/ptm/sessions/{s['id']}/publish", headers=g_pr).status_code == 404
    # Greenfield parent gets 404 (not 403) when booking Sunrise slot
    r = requests.post(f"{API}/ptm/bookings", headers=g_par,
                      json={"slot_id": slot, "student_id": str(ObjectId()), "client_id": uuid.uuid4().hex})
    assert r.status_code == 404
    # Greenfield parent's /ptm/sessions should not contain Sunrise session
    items = requests.get(f"{API}/ptm/sessions", headers=g_par).json().get("items", [])
    assert s["id"] not in {x["id"] for x in items}
    # Greenfield slot availability act -> 404 (slot not in their tenant)
    r = requests.post(f"{API}/ptm/slots/{slot}/availability?act=block&reason=x", headers=g_pr)
    assert r.status_code == 404


# ------------------------------------------------------------ parent A vs parent B privacy & authorization
def test_parent_a_cannot_touch_parent_b_booking():
    th, pr, sec, tid, year = _ctx()
    s = _session(pr, year, sec, tid)
    (pa, ka), (pb, kb) = _strangers(pr["X-School-Id"], sec, 2)
    sl = requests.get(f"{API}/ptm/sessions/{s['id']}/slots?teacher_id={tid}&student_id={ka}", headers=pa).json()["items"]
    b_a = requests.post(f"{API}/ptm/bookings", headers=pa,
                       json={"slot_id": sl[0]["id"], "student_id": ka, "client_id": uuid.uuid4().hex}).json()
    assert b_a["status"] == "confirmed"
    # Parent B GET A's booking -> 404
    assert requests.get(f"{API}/ptm/bookings/{b_a['id']}", headers=pb).status_code == 404
    # Parent B cancel A's booking -> 404
    assert requests.post(f"{API}/ptm/bookings/{b_a['id']}/cancel", headers=pb).status_code == 404
    # Parent B reschedule A's booking -> 404
    r = requests.post(f"{API}/ptm/bookings/{b_a['id']}/reschedule", headers=pb, json={"slot_id": sl[1]["id"]})
    assert r.status_code == 404
    # Parent B outcome on A's booking -> 403 (parent cannot record outcome)
    r = requests.post(f"{API}/ptm/bookings/{b_a['id']}/outcome", headers=pb, json={"status": "completed"})
    assert r.status_code in (403, 404)
    # Parent B followup -> 403/404
    r = requests.post(f"{API}/ptm/bookings/{b_a['id']}/followups", headers=pb, json={"title": "hack attempt"})
    assert r.status_code in (403, 404)
    # Parent A sees own booking fine
    me = requests.get(f"{API}/ptm/bookings/{b_a['id']}", headers=pa)
    assert me.status_code == 200 and me.json()["id"] == b_a["id"]


# ------------------------------------------------------------ teacher-not-in-session
def test_teacher_not_in_session_cannot_see_or_act():
    th, pr, sec, tid, year = _ctx()
    s = _session(pr, year, sec, tid)
    # Greenfield teacher (not in this school's session at all)
    g_th = login("teacher@greenfield.demo")
    assert requests.get(f"{API}/ptm/sessions/{s['id']}", headers=g_th).status_code == 404
    assert requests.get(f"{API}/ptm/schedule?day={D1}", headers=g_th).json().get("items", []) == []
    # Build a session WITHOUT this school's teacher by using a temp teacher only
    from test_audit_file_access import _temp_teacher
    _tth, _aid, _ = _temp_teacher(pr["X-School-Id"], sec, None)
    t2 = str(TEMP[-2][1])
    s2 = _session(pr, year, sec, t2, name="PTEST tempteach")
    # Original demo teacher is NOT a teacher in s2 -> they should get 404 for the session
    assert requests.get(f"{API}/ptm/sessions/{s2['id']}", headers=th).status_code == 404
    # slot availability as a teacher who doesn't own that slot -> 404
    slot = str(db.ptm_slots.find_one({"session_id": s2["id"]})["_id"])
    r = requests.post(f"{API}/ptm/slots/{slot}/availability?act=block&reason=foo", headers=th)
    assert r.status_code == 404


# ------------------------------------------------------------ invalid ObjectIds / bad ids
def test_invalid_object_ids_return_safe_errors():
    _th, pr, _sec, tid, _year = _ctx()
    # Malformed id -> 400/422 (not 500). FastAPI/pydantic may use either.
    for p in ("/ptm/sessions/not-an-oid",
              f"/ptm/sessions/not-an-oid/slots?teacher_id={tid}",
              "/ptm/bookings/not-an-oid"):
        r = requests.get(f"{API}{p}", headers=pr)
        assert r.status_code in (400, 404, 422), f"{p} -> {r.status_code} {r.text[:200]}"
    # Non-existent but valid ObjectId -> 404
    fake = str(ObjectId())
    assert requests.get(f"{API}/ptm/sessions/{fake}", headers=pr).status_code == 404
    assert requests.get(f"{API}/ptm/bookings/{fake}", headers=pr).status_code == 404
    assert requests.post(f"{API}/ptm/sessions/{fake}/publish", headers=pr).status_code == 404
    assert requests.post(f"{API}/ptm/sessions/{fake}/cancel?reason=none", headers=pr).status_code == 404
    r = requests.post(f"{API}/ptm/slots/{fake}/availability?act=block&reason=x", headers=pr)
    assert r.status_code == 404


# ------------------------------------------------------------ mass-assignment resistance
def test_mass_assignment_fields_are_ignored():
    _th, pr, sec, tid, year = _ctx()
    body = {"name": "PTEST massassign", "academic_year_id": year, "section_ids": [sec], "teacher_ids": [tid],
            "dates": [D1], "start_time": "10:00", "end_time": "10:30",
            # garbage / privileged fields:
            "school_id": "other-tenant", "status": "published", "created_by": "attacker",
            "published_at": "2000-01-01T00:00:00", "history": [{"evil": True}],
            "cancel_reason": "haha", "_id": "x"}
    r = requests.post(f"{API}/ptm/sessions", headers=pr, json=body)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["school_id"] == pr["X-School-Id"]
    assert j["status"] == "draft"  # action defaulted to draft; attacker's "status":"published" ignored
    assert j.get("cancel_reason") in (None, "")
    saved = db.ptm_sessions.find_one({"_id": ObjectId(j["id"])})
    assert saved["created_by"] != "attacker"
    assert all(h.get("action") in ("create", "edit", "publish", "cancel") for h in saved.get("history", []))


# ------------------------------------------------------------ invalid state transitions
def test_invalid_state_transitions():
    _th, pr, sec, tid, year = _ctx()
    s = _session(pr, year, sec, tid)
    # Edit a published session -> 409
    body = {"name": "PTEST edit-pub", "academic_year_id": year, "section_ids": [sec], "teacher_ids": [tid],
            "dates": [D1], "start_time": "10:00", "end_time": "10:30"}
    assert requests.put(f"{API}/ptm/sessions/{s['id']}", headers=pr, json=body).status_code == 409
    # Re-publish a published session -> 409
    assert requests.post(f"{API}/ptm/sessions/{s['id']}/publish", headers=pr).status_code == 409
    # Cancel then try again -> 409
    assert requests.post(f"{API}/ptm/sessions/{s['id']}/cancel?reason=done", headers=pr).status_code == 200
    assert requests.post(f"{API}/ptm/sessions/{s['id']}/cancel?reason=again", headers=pr).status_code == 409
    assert requests.post(f"{API}/ptm/sessions/{s['id']}/publish", headers=pr).status_code in (400, 409)
    # Short cancel reason -> 422 (query validator min_length=3)
    s2 = _session(pr, year, sec, tid, name="PTEST short")
    assert requests.post(f"{API}/ptm/sessions/{s2['id']}/cancel?reason=xx", headers=pr).status_code == 422


# ------------------------------------------------------------ reschedule and outcome edge rules
def test_reschedule_to_same_slot_and_outcome_before_start():
    th, pr, sec, tid, year = _ctx()
    s = _session(pr, year, sec, tid)
    (pa, ka), = _strangers(pr["X-School-Id"], sec, 1)
    sl = requests.get(f"{API}/ptm/sessions/{s['id']}/slots?teacher_id={tid}&student_id={ka}", headers=pa).json()["items"]
    b = requests.post(f"{API}/ptm/bookings", headers=pa,
                      json={"slot_id": sl[0]["id"], "student_id": ka, "client_id": uuid.uuid4().hex}).json()
    assert b["status"] == "confirmed"
    # Reschedule to the same slot -> 400 "choose a different time"
    r = requests.post(f"{API}/ptm/bookings/{b['id']}/reschedule", headers=pa, json={"slot_id": sl[0]["id"]})
    assert r.status_code == 400
    # Outcome before start -> 409
    r = requests.post(f"{API}/ptm/bookings/{b['id']}/outcome", headers=th, json={"status": "completed"})
    assert r.status_code == 409
    # Notes before outcome -> 409
    r = requests.patch(f"{API}/ptm/bookings/{b['id']}/notes", headers=th, json={"shared_note": "x"})
    assert r.status_code == 409
    # Follow-up before outcome -> 409
    r = requests.post(f"{API}/ptm/bookings/{b['id']}/followups", headers=th, json={"title": "nope"})
    assert r.status_code == 409
    # Cross-teacher cannot write notes
    g_th = login("teacher@greenfield.demo")
    r = requests.patch(f"{API}/ptm/bookings/{b['id']}/notes", headers=g_th, json={"shared_note": "foreign"})
    assert r.status_code == 404
