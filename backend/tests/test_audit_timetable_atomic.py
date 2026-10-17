"""Audit remediation — concurrent conflicting timetable writes must never double-book a teacher or room."""
from concurrent.futures import ThreadPoolExecutor

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login


def _two_sections_one_teacher(school_id):
    """A teacher assigned (subject) to two different sections."""
    for t in db.teachers.find({"school_id": school_id, "status": "active"}):
        asg = [a for a in db.teacher_assignments.find({"teacher_id": str(t["_id"])}) if a.get("subject_id")]
        secs = {}
        for a in asg:
            secs.setdefault(a["section_id"], a)
        if len(secs) >= 2:
            a1, a2 = list(secs.values())[:2]
            return str(t["_id"]), a1, a2
    raise AssertionError("demo data needs a teacher in two sections")


def test_concurrent_teacher_double_booking_is_atomic():
    admin = login("admin@sunrise.demo")
    tid, a1, a2 = _two_sections_one_teacher(admin["X-School-Id"])
    day, period = 6, 8  # Sat P8 — free in the demo seed
    keys = [{"section_id": a["section_id"], "day": day, "period": period} for a in (a1, a2)]
    saved = [db.timetable_slots.find_one(k) for k in keys]
    db.timetable_slots.delete_many({"$or": keys + [{"teacher_id": tid, "day": day, "period": period}]})
    try:
        for _ in range(5):  # repeat to shake out races
            def put(a):
                return requests.put(f"{API}/timetable/sections/{a['section_id']}/slots", headers=admin,
                                    json={"day": day, "period": period, "subject_id": a["subject_id"], "teacher_id": tid}).status_code
            with ThreadPoolExecutor(max_workers=8) as ex:
                codes = list(ex.map(put, [a1, a2] * 4))
            assert db.timetable_slots.count_documents({"teacher_id": tid, "day": day, "period": period}) == 1
            assert set(codes) <= {200, 409} and 409 in codes
            db.timetable_slots.delete_many({"$or": keys})
    finally:
        db.timetable_slots.delete_many({"$or": keys})
        for s in saved:
            if s:
                db.timetable_slots.insert_one(s)


def test_concurrent_room_double_booking_is_atomic():
    admin = login("admin@sunrise.demo")
    secs = [str(s["_id"]) for s in db.sections.find({"school_id": admin["X-School-Id"]}).limit(6)]
    sub = db.subjects.find_one({"school_id": admin["X-School-Id"]})
    day, period = 6, 8
    keys = [{"section_id": s, "day": day, "period": period} for s in secs]
    saved = [db.timetable_slots.find_one(k) for k in keys]
    db.timetable_slots.delete_many({"$or": keys})
    try:
        def put(s):
            return requests.put(f"{API}/timetable/sections/{s}/slots", headers=admin,
                                json={"day": day, "period": period, "subject_id": str(sub["_id"]), "room": "Lab-RACE"}).status_code
        with ThreadPoolExecutor(max_workers=6) as ex:
            codes = list(ex.map(put, secs))
        assert codes.count(200) == 1 and codes.count(409) == len(secs) - 1
        assert db.timetable_slots.count_documents({"room_key": "lab-race", "day": day, "period": period}) == 1
        # case/whitespace variants of the same room are the same room
        other = next(s for s in secs if not db.timetable_slots.find_one({"section_id": s, "day": day, "period": period}))
        assert requests.put(f"{API}/timetable/sections/{other}/slots", headers=admin,
                            json={"day": day, "period": period, "subject_id": str(sub["_id"]), "room": " lab-race "}).status_code == 409
    finally:
        db.timetable_slots.delete_many({"$or": keys})
        for s in saved:
            if s:
                db.timetable_slots.insert_one(s)


def test_unique_indexes_exist():
    info = db.timetable_slots.index_information()
    assert info["uniq_teacher_period"]["unique"] and info["uniq_room_period"]["unique"]
