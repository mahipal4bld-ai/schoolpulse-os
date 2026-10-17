"""Fault injection for PTM publication: partial insert failures, duplicate retries, silent short writes and recovery.

Runs `_publish` in-process against the real MongoDB with a fresh Motor client and a wrapped `ptm_slots` collection,
so we can make the database fail mid-insert — something the HTTP API can never be asked to do.
"""
import asyncio
import os
from datetime import date, timedelta

import pytest
import requests
from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import AutoReconnect

import core
import routes_ptm
from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_homework import _teacher_slot

D = (date.today() + timedelta(days=5)).isoformat()


class _Slots:
    """Wraps the real collection; `mode` controls how insert_many misbehaves."""

    def __init__(self, real, mode):
        self.real, self.mode = real, mode

    def __getattr__(self, n):
        return getattr(self.real, n)

    async def insert_many(self, docs, ordered=False):
        if self.mode == "crash_midway":       # half the slots land, then the connection drops
            await self.real.insert_many(docs[: len(docs) // 2], ordered=False)
            raise AutoReconnect("injected: connection reset during insert")
        if self.mode == "silent_short":       # driver reports success but a slot is missing
            await self.real.insert_many(docs[:-1], ordered=False)
            return None
        return await self.real.insert_many(docs, ordered=ordered)


class _DB:
    def __init__(self, real, slots):
        self.real, self.ptm_slots = real, slots

    def __getattr__(self, n):
        return getattr(self.real, n)

    def __getitem__(self, n):
        return self.ptm_slots if n == "ptm_slots" else self.real[n]


def _draft():
    th = login("teacher@sunrise.demo")
    sec, _, tid = _teacher_slot(th)
    pr = login("principal@sunrise.demo")
    year = str(db.academic_years.find_one({"school_id": pr["X-School-Id"], "is_current": True})["_id"])
    r = requests.post(f"{API}/ptm/sessions", headers=pr, json={"name": "PTEST fault", "academic_year_id": year, "section_ids": [sec],
                      "teacher_ids": [tid], "dates": [D], "start_time": "09:00", "end_time": "10:00", "slot_minutes": 10})
    assert r.status_code == 201, r.text
    return pr, r.json()["id"], sec


async def _run(sid, mode):
    real = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    orig_ptm, orig_core = routes_ptm.db, core.db
    routes_ptm.db = _DB(real, _Slots(real.ptm_slots, mode)) if mode else real
    core.db = real
    try:
        s = await real.ptm_sessions.find_one({"_id": ObjectId(sid)})
        u = await real.users.find_one({"email": "principal@sunrise.demo"})
        ctx = core.Ctx(user=u, user_id=str(u["_id"]), school_id=s["school_id"], role="principal", perms={"ptm.manage"})
        await routes_ptm._publish(ctx, s)
    finally:
        routes_ptm.db, core.db = orig_ptm, orig_core


def _publish(sid, mode=None):
    asyncio.run(_run(sid, mode))


@pytest.fixture(autouse=True)
def _clean():
    yield
    sids = [str(s["_id"]) for s in db.ptm_sessions.find({"name": "PTEST fault"})]
    db.ptm_slots.delete_many({"session_id": {"$in": sids}})
    db.ptm_sessions.delete_many({"name": "PTEST fault"})


def _hidden_from_families(sid, sec):
    ph = login("parent@sunrise.demo")
    assert requests.get(f"{API}/ptm/sessions/{sid}", headers=ph).status_code == 404
    assert sid not in {x["id"] for x in requests.get(f"{API}/ptm/sessions", headers=ph).json()["items"]}
    assert not any(i["id"] == sid for i in requests.get(f"{API}/calendar?start={D}&end={D}", headers=ph).json()["items"])


def test_partial_insert_failure_is_not_published_and_retry_recovers():
    pr, sid, sec = _draft()
    with pytest.raises(AutoReconnect):        # unexpected DB error is NOT swallowed
        _publish(sid, "crash_midway")
    s = db.ptm_sessions.find_one({"_id": ObjectId(sid)})
    assert s["status"] == "publishing" and s["published_at"] is None and "injected" in s["publish_error"]
    assert 0 < db.ptm_slots.count_documents({"session_id": sid}) < 6
    _hidden_from_families(sid, sec)
    # parents cannot book a half-generated slot
    slot = db.ptm_slots.find_one({"session_id": sid})
    kid = requests.get(f"{API}/parent/children", headers=login("parent@sunrise.demo")).json()["items"][0]["id"]
    assert requests.post(f"{API}/ptm/bookings", headers=login("parent@sunrise.demo"),
                         json={"slot_id": str(slot["_id"]), "student_id": kid, "client_id": "fault-test-01"}).status_code in (404, 409)
    # retry through the public API: duplicates from the first attempt are tolerated, missing slots are filled
    r = requests.post(f"{API}/ptm/sessions/{sid}/publish", headers=pr)
    assert r.status_code == 200 and r.json()["status"] == "published" and r.json()["slot_count"] == 6
    assert db.ptm_slots.count_documents({"session_id": sid}) == 6
    keys = [(x["teacher_id"], x["start_at"]) for x in db.ptm_slots.find({"session_id": sid})]
    assert len(set(keys)) == 6
    hist = [h["action"] for h in db.ptm_sessions.find_one({"_id": ObjectId(sid)})["history"]]
    assert hist.count("publish_failed") == 1 and hist[-1] == "publish"


def test_silent_short_write_is_detected():
    _pr, sid, sec = _draft()
    with pytest.raises(HTTPException) as e:
        _publish(sid, "silent_short")
    assert e.value.status_code == 503
    s = db.ptm_sessions.find_one({"_id": ObjectId(sid)})
    assert s["status"] == "publishing" and "1 of 6" in s["publish_error"]
    _hidden_from_families(sid, sec)
    _publish(sid)  # recovery in-process
    assert db.ptm_sessions.find_one({"_id": ObjectId(sid)})["status"] == "published"
    assert db.ptm_slots.count_documents({"session_id": sid}) == 6


def test_duplicate_retry_of_complete_publish_is_idempotent_and_refused():
    pr, sid, _ = _draft()
    _publish(sid)
    assert db.ptm_slots.count_documents({"session_id": sid}) == 6
    with pytest.raises(HTTPException) as e:   # second publish of a published session
        _publish(sid)
    assert e.value.status_code == 409
    assert requests.post(f"{API}/ptm/sessions/{sid}/publish", headers=pr).status_code == 409
    assert db.ptm_slots.count_documents({"session_id": sid}) == 6


def test_concurrent_publish_attempts_produce_exactly_one_slot_set():
    pr, sid, _ = _draft()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        codes = list(ex.map(lambda _: requests.post(f"{API}/ptm/sessions/{sid}/publish", headers=pr).status_code, range(4)))
    assert codes.count(200) >= 1 and all(c in (200, 409) for c in codes), codes
    assert db.ptm_sessions.find_one({"_id": ObjectId(sid)})["status"] == "published"
    assert db.ptm_slots.count_documents({"session_id": sid}) == 6


def test_cancel_while_publishing_incomplete():
    pr, sid, _ = _draft()
    with pytest.raises(AutoReconnect):
        _publish(sid, "crash_midway")
    r = requests.post(f"{API}/ptm/sessions/{sid}/cancel?reason=Abandoned", headers=pr)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert db.ptm_slots.count_documents({"session_id": sid, "status": {"$ne": "cancelled"}}) == 0
    assert requests.post(f"{API}/ptm/sessions/{sid}/publish", headers=pr).status_code == 409
