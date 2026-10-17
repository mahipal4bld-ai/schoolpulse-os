"""Milestone 3 Module 4 — PTM engine: lifecycle, eligibility, atomic booking under real concurrency, reschedule safety,
privacy, teacher workflow, calendar integration, insights, tenancy."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import uuid

import pytest
import requests
from bson import ObjectId

from test_audit_file_access import TEMP, _drop_temp, _temp_teacher, _temp_user
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
    sec, sub, tid = _teacher_slot(th)
    pr = login("principal@sunrise.demo")
    year = str(db.academic_years.find_one({"school_id": pr["X-School-Id"], "is_current": True})["_id"])
    return th, pr, sec, sub, tid, year


def _session(pr, year, sec, tid, **kw):
    body = {"name": "PTEST Class PTM", "academic_year_id": year, "section_ids": [sec], "teacher_ids": [tid], "dates": [D1],
            "start_time": "10:00", "end_time": "10:30", "slot_minutes": 10, "break_minutes": 0, "capacity": 1,
            "cancel_cutoff_hours": 1, "reschedule_cutoff_hours": 1, "action": "publish", **kw}
    r = requests.post(f"{API}/ptm/sessions", headers=pr, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _slots(h, sid, tid, kid=None):
    r = requests.get(f"{API}/ptm/sessions/{sid}/slots?teacher_id={tid}" + (f"&student_id={kid}" if kid else ""), headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _book(h, slot, kid, cid=None):
    return requests.post(f"{API}/ptm/bookings", headers=h, json={"slot_id": slot, "student_id": kid, "client_id": cid or uuid.uuid4().hex})


def _temp_parent(school, kid):
    email, uid, _ = _temp_user(school, "parent")
    gid = db.guardians.insert_one({"school_id": school, "name": "PTEST Guardian", "user_id": uid, "email": email,
                                   "phone": f"7{uuid.uuid4().int % 10**9:09d}"}).inserted_id
    lid = db.guardian_links.insert_one({"school_id": school, "student_id": kid, "guardian_id": str(gid),
                                        "relation": "guardian", "verified": True}).inserted_id
    TEMP.extend([("guardians", gid), ("guardian_links", lid)])
    return login(email), lid, None


def _strangers(school, sec, n):
    """n distinct active students in `sec` (not demo-parent children) with fresh temp guardian accounts."""
    demo = [str(g["_id"]) for g in db.guardians.find({"school_id": school, "email": {"$regex": "\\.demo$"}})]
    demo_kids = {lk["student_id"] for lk in db.guardian_links.find({"guardian_id": {"$in": demo}})}
    secs = sec if isinstance(sec, list) else [sec]
    studs = [str(s["_id"]) for s in db.students.find({"section_id": {"$in": secs}, "status": "active"}) if str(s["_id"]) not in demo_kids][:n]
    assert len(studs) == n
    return [(_temp_parent(school, k)[0], k) for k in studs]


def test_publish_eligibility_book_cancel_restore_and_privacy():
    th, pr, sec, _, tid, year = _ctx()
    s = _session(pr, year, sec, tid)
    assert s["status"] == "published"
    assert db.ptm_slots.count_documents({"session_id": s["id"]}) == 3
    (pa, ka), (pb, kb) = _strangers(pr["X-School-Id"], sec, 2)
    # eligibility: parent sees session + only applicable teachers; other school/teacher-less parents cannot
    det = requests.get(f"{API}/ptm/sessions/{s['id']}", headers=pa).json()
    assert [c["student_id"] for c in det["children"]] == [ka] and det["children"][0]["teachers"][0]["teacher_id"] == tid
    assert s["id"] in {x["id"] for x in requests.get(f"{API}/ptm/sessions", headers=pa).json()["items"]}
    g = login("parent@greenfield.demo")
    assert requests.get(f"{API}/ptm/sessions/{s['id']}", headers=g).status_code == 404
    assert requests.get(f"{API}/ptm/sessions/{s['id']}", headers=login("principal@greenfield.demo")).status_code == 404
    sl = _slots(pa, s["id"], tid, ka)
    assert all(set(x) == {"id", "date", "start_time", "end_time", "available"} for x in sl)  # no other-family data
    assert _book(pa, sl[0]["id"], kb).status_code == 404  # not my child
    r = _book(pa, sl[0]["id"], ka)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "confirmed" and "private_note" not in b and b["can_cancel"]
    assert not next(x for x in _slots(pb, s["id"], tid, kb) if x["id"] == sl[0]["id"])["available"]
    # parent B cannot see A's booking; second booking with same teacher for same child is refused
    assert requests.get(f"{API}/ptm/bookings/{b['id']}", headers=pb).status_code == 404
    assert _book(pa, sl[1]["id"], ka).status_code == 409
    # cancel within policy restores availability + quota
    c = requests.post(f"{API}/ptm/bookings/{b['id']}/cancel", headers=pa)
    assert c.status_code == 200 and c.json()["status"] == "cancelled_parent"
    assert db.ptm_slots.find_one({"_id": ObjectId(sl[0]["id"])})["booked"] == 0
    assert db.ptm_quotas.find_one({"session_id": s["id"], "key": f"s:{ka}"})["count"] == 0
    assert requests.post(f"{API}/ptm/bookings/{b['id']}/cancel", headers=pa).status_code == 409
    assert _book(pb, sl[0]["id"], kb).status_code == 201  # freed slot is bookable again
    types = {n["type"] for n in requests.get(f"{API}/notifications", headers=pa).json()["items"]}
    assert {"ptm.booked", "ptm.cancelled"} <= types
    # calendar shows the PTM date for the eligible parent and the teacher, not for an unrelated school
    rng = f"start={D1}&end={D1}"
    assert any(i["kind"] == "ptm" and i["id"] == s["id"] for i in requests.get(f"{API}/calendar?{rng}", headers=pa).json()["items"])
    assert any(i["kind"] == "ptm" for i in requests.get(f"{API}/calendar?{rng}", headers=th).json()["items"])
    assert not any(i["id"] == s["id"] for i in requests.get(f"{API}/calendar?{rng}", headers=g).json()["items"])


def test_concurrent_last_slot_and_idempotent_retries():
    th, pr, sec, _, tid, year = _ctx()
    secs = sorted(set(db.teacher_assignments.distinct("section_id", {"teacher_id": tid})))
    s = _session(pr, year, sec, tid, end_time="10:10", section_ids=secs)  # exactly one slot, capacity 1
    slot = db.ptm_slots.find_one({"session_id": s["id"]})
    parents = _strangers(pr["X-School-Id"], secs, 6)
    with ThreadPoolExecutor(max_workers=6) as ex:
        codes = list(ex.map(lambda p: _book(p[0], str(slot["_id"]), p[1]).status_code, parents))
    assert sorted(codes) == [201] + [409] * 5, codes
    assert db.ptm_slots.find_one({"_id": slot["_id"]})["booked"] == 1
    assert db.ptm_bookings.count_documents({"session_id": s["id"], "status": "confirmed"}) == 1
    # capacity 2 group slot: 6 concurrent -> exactly 2
    s2 = _session(pr, year, sec, tid, name="PTEST cap2", end_time="10:10", capacity=2, dates=[D2], section_ids=secs)
    slot2 = db.ptm_slots.find_one({"session_id": s2["id"]})
    with ThreadPoolExecutor(max_workers=6) as ex:
        codes = list(ex.map(lambda p: _book(p[0], str(slot2["_id"]), p[1]).status_code, parents))
    assert codes.count(201) == 2 and db.ptm_slots.find_one({"_id": slot2["_id"]})["booked"] == 2
    # the same request retried concurrently creates exactly one booking
    s3 = _session(pr, year, sec, tid, name="PTEST idem", dates=[D2], start_time="11:00", end_time="11:30", section_ids=secs)
    sl3 = str(db.ptm_slots.find_one({"session_id": s3["id"]}, sort=[("start_at", 1)])["_id"])
    p, k = parents[0]
    cid = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(lambda _: _book(p, sl3, k, cid), range(5)))
    assert all(r.status_code in (200, 201) for r in res), [r.text for r in res]
    assert len({r.json()["id"] for r in res}) == 1
    assert db.ptm_bookings.count_documents({"session_id": s3["id"]}) == 1
    assert db.ptm_slots.find_one({"_id": ObjectId(sl3)})["booked"] == 1


def test_reschedule_atomic_and_guardian_overlap_and_quota():
    th, pr, sec, _, tid, year = _ctx()
    s = _session(pr, year, sec, tid, max_per_child=1)
    sl = _slots(pr, s["id"], tid)
    (pa, ka), (pb, kb) = _strangers(pr["X-School-Id"], sec, 2)
    a = _book(pa, sl[0]["id"], ka).json()
    assert _book(pb, sl[1]["id"], kb).status_code == 201
    # target taken -> 409 and the original booking is untouched
    r = requests.post(f"{API}/ptm/bookings/{a['id']}/reschedule", headers=pa, json={"slot_id": sl[1]["id"]})
    assert r.status_code == 409
    keep = db.ptm_bookings.find_one({"_id": ObjectId(a["id"])})
    assert keep["status"] == "confirmed" and keep["slot_id"] == sl[0]["id"]
    assert db.ptm_slots.find_one({"_id": ObjectId(sl[0]["id"])})["booked"] == 1
    assert db.ptm_slots.find_one({"_id": ObjectId(sl[1]["id"])})["booked"] == 1
    ok = requests.post(f"{API}/ptm/bookings/{a['id']}/reschedule", headers=pa, json={"slot_id": sl[2]["id"]})
    assert ok.status_code == 200 and ok.json()["slot_id"] == sl[2]["id"] and len(ok.json()["reschedules"]) == 1
    assert db.ptm_slots.find_one({"_id": ObjectId(sl[0]["id"])})["booked"] == 0
    assert db.ptm_slots.find_one({"_id": ObjectId(sl[2]["id"])})["booked"] == 1
    # per-child quota (1) blocks a second meeting for the same child with another teacher in the same session
    tmp_t, _aid, _ = _temp_teacher(pr["X-School-Id"], sec, None)
    t2 = str(db.teachers.find_one({"_id": TEMP[-2][1]})["_id"]) if TEMP[-2][0] == "teachers" else None
    s2 = requests.post(f"{API}/ptm/sessions", headers=pr, json={"name": "PTEST two", "academic_year_id": year, "section_ids": [sec],
                       "teacher_ids": [tid, t2], "dates": [D2], "start_time": "12:00", "end_time": "12:20", "slot_minutes": 10,
                       "max_per_child": 1, "action": "publish"}).json()
    x1 = _slots(pa, s2["id"], tid, ka)
    x2 = _slots(pa, s2["id"], t2, ka)
    assert _book(pa, x1[0]["id"], ka).status_code == 201
    assert _book(pa, x2[1]["id"], ka).status_code == 409  # quota
    assert db.ptm_quotas.find_one({"session_id": s2["id"], "key": f"s:{ka}"})["count"] == 1
    # guardian cannot be in two meetings at the same moment (two children, same start)
    s3 = requests.post(f"{API}/ptm/sessions", headers=pr, json={"name": "PTEST overlap", "academic_year_id": year, "section_ids": [sec],
                       "teacher_ids": [tid, t2], "dates": [D2], "start_time": "13:00", "end_time": "13:10", "slot_minutes": 10,
                       "action": "publish"}).json()
    other_kid = next(str(x["_id"]) for x in db.students.find({"section_id": sec, "status": "active"}) if str(x["_id"]) not in (ka, kb))
    gid = db.guardians.find_one({"user_id": db.guardian_links.find_one({"student_id": ka, "verified": True, "relation": "guardian"}) and
                                 db.guardians.find_one({"_id": ObjectId(db.guardian_links.find_one({"student_id": ka, "relation": "guardian"})["guardian_id"])})["user_id"]})
    lid = db.guardian_links.insert_one({"school_id": pr["X-School-Id"], "student_id": other_kid, "guardian_id": str(gid["_id"]),
                                        "relation": "guardian", "verified": True}).inserted_id
    TEMP.append(("guardian_links", lid))
    assert _book(pa, _slots(pa, s3["id"], tid, ka)[0]["id"], ka).status_code == 201
    r = _book(pa, _slots(pa, s3["id"], t2, other_kid)[0]["id"], other_kid)
    assert r.status_code == 409 and "another meeting" in r.json()["detail"]


def test_teacher_conflicts_unavailability_and_override():
    th, pr, sec, _, tid, year = _ctx()
    s1 = _session(pr, year, sec, tid)
    s2 = _session(pr, year, sec, tid, name="PTEST overlap teacher", start_time="10:05", end_time="10:45")
    blocked = list(db.ptm_slots.find({"session_id": s2["id"], "status": "blocked"}))
    assert blocked and all(b["block_reason"] == "Another PTM at this time" for b in blocked)
    # every (teacher, time) has at most one bookable slot across sessions
    live = list(db.ptm_slots.find({"teacher_id": tid, "status": "available", "session_id": {"$in": [s1["id"], s2["id"]]}}))
    for x in live:
        for y in live:
            if x["_id"] != y["_id"]:
                assert not (x["start_at"] < y["end_at"] and y["start_at"] < x["end_at"])
    # teacher marks a free slot unavailable -> needs approval by default; admin approves with reason
    sl = _slots(th, s1["id"], tid)[0]
    r = requests.post(f"{API}/ptm/slots/{sl['id']}/availability?act=block&reason=PTEST", headers=th)
    assert r.status_code == 200 and r.json()["status"] == "block_requested"
    assert requests.post(f"{API}/ptm/slots/{sl['id']}/availability?act=approve", headers=pr).status_code == 400  # reason needed
    assert requests.post(f"{API}/ptm/slots/{sl['id']}/availability?act=approve&reason=ok", headers=pr).json()["status"] == "blocked"
    assert db.audit_logs.count_documents({"action": "ptm.slot_approve", "entity_id": sl["id"]}) == 1
    assert requests.post(f"{API}/ptm/slots/{sl['id']}/availability?act=approve&reason=ok", headers=th).status_code == 404
    # booked slots cannot be blocked
    (pa, ka), = _strangers(pr["X-School-Id"], sec, 1)
    sl2 = _slots(pa, s1["id"], tid, ka)[1]
    assert _book(pa, sl2["id"], ka).status_code == 201
    assert requests.post(f"{API}/ptm/slots/{sl2['id']}/availability?act=block&reason=x", headers=pr).status_code == 409
    # unavailability period blocks overlapping free slots and reports booked conflicts
    u = requests.post(f"{API}/ptm/unavailability", headers=th, json={"date": D1, "start_time": "10:00", "end_time": "10:30", "reason": "PTEST dentist"}).json()
    assert u["booked_conflicts"] == 1
    # school holiday blocks publishing
    hol = requests.post(f"{API}/events", headers=pr, json={"title": "ETEST holiday", "category": "holiday", "start_date": D2, "action": "publish"}).json()
    try:
        r = requests.post(f"{API}/ptm/sessions", headers=pr, json={"name": "PTEST holiday", "academic_year_id": year, "section_ids": [sec],
                          "teacher_ids": [tid], "dates": [D2], "start_time": "09:00", "end_time": "09:30", "action": "publish"})
        assert r.status_code == 409 and "closed" in r.json()["detail"]
    finally:
        db.events.delete_one({"_id": ObjectId(hol["id"])})


def test_outcome_notes_followups_schedule_insights_and_session_cancel():
    th, pr, sec, _, tid, year = _ctx()
    s = _session(pr, year, sec, tid)
    (pa, ka), (pb, kb) = _strangers(pr["X-School-Id"], sec, 2)
    sl = _slots(pa, s["id"], tid, ka)
    a = _book(pa, sl[0]["id"], ka).json()
    b = _book(pb, sl[1]["id"], kb).json()
    assert requests.post(f"{API}/ptm/bookings/{a['id']}/outcome", headers=th, json={"status": "completed"}).status_code == 409  # not started
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.ptm_bookings.update_one({"_id": ObjectId(a["id"])}, {"$set": {"start_at": past}})
    assert requests.post(f"{API}/ptm/bookings/{a['id']}/outcome", headers=pa, json={"status": "completed"}).status_code == 403
    o = requests.post(f"{API}/ptm/bookings/{a['id']}/outcome", headers=th, json={"status": "completed", "shared_note": "Reading practice daily",
                                                                               "private_note": "Discussed sibling concern"})
    assert o.status_code == 200 and o.json()["status"] == "completed" and o.json()["private_note"]
    f1 = requests.post(f"{API}/ptm/bookings/{a['id']}/followups", headers=th, json={"title": "Share reading list", "shared": True, "due_date": D2}).json()
    requests.post(f"{API}/ptm/bookings/{a['id']}/followups", headers=th, json={"title": "Internal: check with counsellor", "shared": False})
    pv = requests.get(f"{API}/ptm/bookings/{a['id']}", headers=pa).json()
    assert "private_note" not in pv and pv["shared_note"] == "Reading practice daily" and [f["title"] for f in pv["followups"]] == ["Share reading list"]
    assert len(requests.get(f"{API}/ptm/bookings/{a['id']}", headers=th).json()["followups"]) == 2
    assert requests.get(f"{API}/ptm/bookings/{a['id']}", headers=pb).status_code == 404
    assert "ptm.followup_shared" in {n["type"] for n in requests.get(f"{API}/notifications", headers=pa).json()["items"]}
    # teacher daily schedule
    sch = requests.get(f"{API}/ptm/schedule?day={D1}", headers=th).json()
    assert {x["id"] for x in sch["items"]} >= {a["id"], b["id"]} and all("guardian_name" in x for x in sch["items"])
    # insights are database-derived
    ins = requests.get(f"{API}/ptm/insights?teacher_id={tid}&start={D1}&end={D1}", headers=pr).json()
    assert ins["completed"] >= 1 and ins["booked"] >= 2 and ins["followups_pending"] >= 2 and ins["eligible_households"] >= 2
    assert requests.get(f"{API}/ptm/insights", headers=th).status_code == 403
    assert requests.post(f"{API}/ptm/followups/{f1['id']}/resolve", headers=th).status_code == 200
    # revoked teacher assignment removes access immediately (temp teacher)
    tt, aid, _ = _temp_teacher(pr["X-School-Id"], sec, None)
    t2 = str(TEMP[-2][1])
    s2 = _session(pr, year, sec, t2, name="PTEST revoke", dates=[D2])
    x = _book(pa, _slots(pa, s2["id"], t2, ka)[0]["id"], ka).json()
    assert requests.get(f"{API}/ptm/bookings/{x['id']}", headers=tt).status_code == 200
    db.teacher_assignments.delete_one({"_id": aid})
    assert requests.get(f"{API}/ptm/bookings/{x['id']}", headers=tt).status_code == 404
    # session cancellation cascades to every live booking + calendar status
    c = requests.post(f"{API}/ptm/sessions/{s['id']}/cancel?reason=Election%20duty", headers=pr)
    assert c.status_code == 200 and c.json()["bookings_cancelled"] == 1
    assert db.ptm_bookings.find_one({"_id": ObjectId(b["id"])})["status"] == "cancelled_school"
    assert db.ptm_bookings.find_one({"_id": ObjectId(a["id"])})["status"] == "completed"
    assert db.ptm_slots.count_documents({"session_id": s["id"], "status": {"$ne": "cancelled"}}) == 0
    assert _book(pa, sl[2]["id"], ka).status_code == 409
    cal = [i for i in requests.get(f"{API}/calendar?start={D1}&end={D1}", headers=pb).json()["items"] if i["id"] == s["id"]]
    assert cal and cal[0]["status"] == "cancelled"
    assert "ptm.session_cancelled" in {n["type"] for n in requests.get(f"{API}/notifications", headers=pb).json()["items"]}


def test_validation_permissions_and_draft():
    th, pr, sec, _, tid, year = _ctx()
    base = {"name": "PTEST v", "academic_year_id": year, "section_ids": [sec], "teacher_ids": [tid], "dates": [D1],
            "start_time": "10:00", "end_time": "10:30"}
    bad = [{**base, "end_time": "09:00"}, {**base, "dates": ["2020-01-01"]}, {**base, "slot_minutes": 7},
           {**base, "section_ids": [str(ObjectId())]}, {**base, "teacher_ids": [str(ObjectId())]},
           {**base, "academic_year_id": str(ObjectId())}, {**base, "start_time": "10:00", "end_time": "10:05"},
           {**base, "mode": "online", "meeting_link": "http://x"}, {**base, "booking_closes_at": f"{D1}T11:00:00"},
           {**base, "status": "published", "school_id": "x"}]
    for x in bad[:-1]:
        assert requests.post(f"{API}/ptm/sessions", headers=pr, json=x).status_code in (400, 422), x
    d = requests.post(f"{API}/ptm/sessions", headers=pr, json=bad[-1]).json()  # mass-assignment fields ignored
    assert d["status"] == "draft" and d["school_id"] == pr["X-School-Id"]
    for h in (th, login("accountant@sunrise.demo"), login("parent@sunrise.demo")):
        assert requests.post(f"{API}/ptm/sessions", headers=h, json=base).status_code == 403
    assert requests.get(f"{API}/ptm/sessions/{d['id']}", headers=login("parent@sunrise.demo")).status_code == 404  # draft hidden
    assert requests.put(f"{API}/ptm/sessions/{d['id']}", headers=pr, json={**base, "name": "PTEST v2"}).json()["name"] == "PTEST v2"
    assert requests.post(f"{API}/ptm/sessions/{d['id']}/publish", headers=pr).status_code == 200
    assert requests.post(f"{API}/ptm/sessions/{d['id']}/publish", headers=pr).status_code == 409
    assert requests.put(f"{API}/ptm/sessions/{d['id']}", headers=pr, json=base).status_code == 409
    # booking window closed
    s = _session(pr, year, sec, tid, name="PTEST closed", dates=[D2], booking_closes_at=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"))
    (pa, ka), = _strangers(pr["X-School-Id"], sec, 1)
    r = _book(pa, _slots(pa, s["id"], tid, ka)[0]["id"], ka)
    assert r.status_code == 409 and "closed" in r.json()["detail"]
    assert requests.post(f"{API}/ptm/bookings", headers=pa, json={"slot_id": "bad", "student_id": ka, "client_id": "x" * 10}).status_code in (400, 404, 422)
