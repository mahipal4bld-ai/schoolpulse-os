"""Milestone 3 — Module 4: Parent–teacher meeting (PTM) engine.

Concurrency model (never read-then-write):
  * seat:   ptm_slots.find_one_and_update({status: available, booked < capacity}) -> $inc booked
  * quota:  ptm_quotas conditional $inc with upsert + unique (session_id, key) -> per-child / per-guardian limits
  * unique: ptm_bookings (guardian_user_id, client_id)            -> idempotent retries
            (session_id, student_id, teacher_id) where active     -> one live meeting per child per teacher
            (guardian_user_id, start_at) where active             -> a guardian can't be in two meetings at once
  Every acquired resource is released if a later step fails. Session cancellation flips slots first, then bookings,
  and the booking path re-checks its slot after insert so no confirmed booking can survive a cancelled session.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_directory import _parent_links
from routes_events import _valid_time
from routes_notices import IST, _ist, sanitize
from routes_notifications import notify

router = APIRouter()
ACTIVE = ("confirmed",)
OUTCOMES = {"completed", "no_show"}


class SessionIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    academic_year_id: str
    section_ids: list[str] = Field(min_length=1, max_length=60)
    teacher_ids: list[str] = Field(min_length=1, max_length=60)
    dates: list[date] = Field(min_length=1, max_length=10)
    start_time: str
    end_time: str
    slot_minutes: Literal[5, 10, 15, 20, 30] = 10
    break_minutes: int = Field(default=0, ge=0, le=30)
    capacity: int = Field(default=1, ge=1, le=5)
    booking_opens_at: Optional[datetime] = None
    booking_closes_at: Optional[datetime] = None
    cancel_cutoff_hours: int = Field(default=12, ge=0, le=168)
    reschedule_cutoff_hours: int = Field(default=12, ge=0, le=168)
    max_per_child: int = Field(default=3, ge=1, le=20)
    max_per_guardian: int = Field(default=6, ge=1, le=40)
    teacher_block_needs_approval: bool = True
    mode: Literal["physical", "online"] = "physical"
    location: str = Field(default="", max_length=120)
    meeting_link: str = Field(default="", max_length=300)
    action: Literal["draft", "publish"] = "draft"

    _t = field_validator("start_time", "end_time")(_valid_time)

    @field_validator("meeting_link")
    @classmethod
    def _link(cls, v):
        if v and not v.startswith("https://"):
            raise ValueError("Meeting link must start with https://")
        return v


class BookIn(BaseModel):
    slot_id: str
    student_id: str
    client_id: str = Field(min_length=8, max_length=64)


class RescheduleIn(BaseModel):
    slot_id: str


class OutcomeIn(BaseModel):
    status: Literal["completed", "no_show"]
    shared_note: str = Field(default="", max_length=2000)
    private_note: str = Field(default="", max_length=2000)


class NotesIn(BaseModel):
    shared_note: Optional[str] = Field(default=None, max_length=2000)
    private_note: Optional[str] = Field(default=None, max_length=2000)


class FollowupIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    due_date: Optional[date] = None
    shared: bool = False


class UnavailIn(BaseModel):
    date: date
    start_time: str
    end_time: str
    reason: str = Field(default="", max_length=200)

    _t = field_validator("start_time", "end_time")(_valid_time)


# ---------------------------------------------------------------- helpers
def _at(d: str, t: str) -> datetime:
    return datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=IST).astimezone(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _today() -> str:
    return now_utc().astimezone(IST).date().isoformat()


def _hist(ctx: Ctx, action: str, **extra) -> dict:
    return {"at": now_utc(), "by": ctx.user_id, "role": ctx.role, "action": action, **extra}


async def _my_teacher(ctx: Ctx) -> Optional[dict]:
    return await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id, "status": "active"})


async def _teacher_teaches(school_id: str, teacher_id: str, section_id: str) -> bool:
    return bool(await db.teacher_assignments.find_one({"school_id": school_id, "teacher_id": teacher_id, "section_id": section_id}))


async def _session(ctx: Ctx, sid: str) -> dict:
    s = await db.ptm_sessions.find_one({"_id": oid(sid), "school_id": ctx.school_id})
    if not s:
        raise HTTPException(404, "PTM session not found")
    return s


def _slot_times(s: dict) -> list[tuple[str, str]]:
    res, step = [], s["slot_minutes"] + s["break_minutes"]
    h, m = map(int, s["start_time"].split(":"))
    cur, end = h * 60 + m, sum(x * y for x, y in zip(map(int, s["end_time"].split(":")), (60, 1)))
    while cur + s["slot_minutes"] <= end:
        e = cur + s["slot_minutes"]
        res.append((f"{cur // 60:02d}:{cur % 60:02d}", f"{e // 60:02d}:{e % 60:02d}"))
        cur += step
    return res


async def _validate(ctx: Ctx, b: SessionIn) -> dict:
    if not await db.academic_years.find_one({"_id": oid(b.academic_year_id), "school_id": ctx.school_id}):
        raise HTTPException(400, "Academic year not found")
    secs = await db.sections.find({"_id": {"$in": [oid(x) for x in set(b.section_ids)]}, "school_id": ctx.school_id}).to_list(100)
    if len(secs) != len(set(b.section_ids)):
        raise HTTPException(400, "Sessions can include only sections from this school")
    yr_classes = set(await db.classes.distinct("_id", {"school_id": ctx.school_id, "academic_year_id": b.academic_year_id}))
    if any(oid(s["class_id"]) not in yr_classes for s in secs):
        raise HTTPException(400, "All sections must belong to the selected academic year")
    ts = await db.teachers.find({"_id": {"$in": [oid(x) for x in set(b.teacher_ids)]}, "school_id": ctx.school_id, "status": "active"}).to_list(100)
    if len(ts) != len(set(b.teacher_ids)):
        raise HTTPException(400, "Choose active teachers from this school")
    sec_ids = [str(s["_id"]) for s in secs]
    for t in ts:
        if not await db.teacher_assignments.find_one({"school_id": ctx.school_id, "teacher_id": str(t["_id"]), "section_id": {"$in": sec_ids}}):
            raise HTTPException(400, f"{t['name']} does not teach any of the selected sections")
    dates = sorted({d.isoformat() for d in b.dates})
    if dates[0] < _today():
        raise HTTPException(400, "PTM dates cannot be in the past")
    if b.end_time <= b.start_time:
        raise HTTPException(400, "End time must be after the start time")
    doc = {"name": sanitize(b.name), "academic_year_id": b.academic_year_id, "section_ids": sec_ids,
           "teacher_ids": [str(t["_id"]) for t in ts], "dates": dates, "start_time": b.start_time, "end_time": b.end_time,
           "slot_minutes": b.slot_minutes, "break_minutes": b.break_minutes, "capacity": b.capacity,
           "booking_opens_at": _ist(b.booking_opens_at), "booking_closes_at": _ist(b.booking_closes_at),
           "cancel_cutoff_hours": b.cancel_cutoff_hours, "reschedule_cutoff_hours": b.reschedule_cutoff_hours,
           "max_per_child": b.max_per_child, "max_per_guardian": b.max_per_guardian,
           "teacher_block_needs_approval": b.teacher_block_needs_approval, "mode": b.mode,
           "location": sanitize(b.location), "meeting_link": b.meeting_link if b.mode == "online" else ""}
    if not doc["name"]:
        raise HTTPException(400, "Name cannot be empty")
    if not _slot_times(doc):
        raise HTTPException(400, "The time window is too short for one meeting")
    first = _at(dates[0], b.start_time)
    if doc["booking_closes_at"] and doc["booking_closes_at"] > first:
        raise HTTPException(400, "Booking must close before the first meeting starts")
    if doc["booking_opens_at"] and doc["booking_opens_at"] >= (doc["booking_closes_at"] or first):
        raise HTTPException(400, "Booking must open before it closes")
    return doc


async def _closures(school_id: str, dates: list[str]) -> list[str]:
    bad = []
    for d in dates:
        h = await db.events.find_one({"school_id": school_id, "status": "published", "category": "holiday",
                                      "audience.scope": "school", "start_date": {"$lte": d}, "end_date": {"$gte": d}})
        if h:
            bad.append(f"{d} ({h['title']})")
    return bad


async def _block_reason(school_id: str, sess_id, teacher_id: str, d: str, a: datetime, b: datetime) -> Optional[str]:
    if await db.leave_requests.find_one({"school_id": school_id, "teacher_id": teacher_id, "status": "approved",
                                         "from_date": {"$lte": d}, "to_date": {"$gte": d}}):
        return "Teacher on leave"
    if await db.ptm_unavailability.find_one({"school_id": school_id, "teacher_id": teacher_id, "start_at": {"$lt": b}, "end_at": {"$gt": a}}):
        return "Teacher unavailable"
    if await db.ptm_slots.find_one({"school_id": school_id, "teacher_id": teacher_id, "session_id": {"$ne": sess_id},
                                    "status": {"$ne": "cancelled"}, "start_at": {"$lt": b}, "end_at": {"$gt": a}}):
        return "Another PTM at this time"
    return None


async def _publish(ctx: Ctx, s: dict):
    bad = await _closures(ctx.school_id, s["dates"])
    if bad:
        raise HTTPException(409, f"School is closed on {', '.join(bad)}")
    t = now_utc()
    r = await db.ptm_sessions.update_one({"_id": s["_id"], "status": "draft"},
                                         {"$set": {"status": "published", "published_at": t, "updated_at": t},
                                          "$push": {"history": _hist(ctx, "publish")}})
    if not r.modified_count:
        raise HTTPException(409, "This session is no longer a draft")
    sid = str(s["_id"])
    docs = []
    for tid in s["teacher_ids"]:
        for d in s["dates"]:
            for a, b in _slot_times(s):
                docs.append({"school_id": ctx.school_id, "session_id": sid, "teacher_id": tid, "date": d, "start_time": a,
                             "end_time": b, "start_at": _at(d, a), "end_at": _at(d, b), "capacity": s["capacity"],
                             "booked": 0, "status": "available", "block_reason": None, "created_at": t})
    try:
        await db.ptm_slots.insert_many(docs, ordered=False)
    except Exception:  # noqa: BLE001 — duplicate retries are fine (unique index), others re-raise below
        pass
    # conflicts are evaluated after our own insert so two concurrent publishes always see each other
    async for sl in db.ptm_slots.find({"session_id": sid, "status": "available", "booked": 0}):
        why = await _block_reason(ctx.school_id, sid, sl["teacher_id"], sl["date"], sl["start_at"], sl["end_at"])
        if why:
            await db.ptm_slots.update_one({"_id": sl["_id"], "booked": 0, "status": "available"},
                                          {"$set": {"status": "blocked", "block_reason": why, "blocked_by": "system"}})
    await audit(ctx.user_id, "ptm.publish", "ptm_session", sid, ctx.school_id, {"slots": len(docs)})


def _session_out(s: dict, full: bool) -> dict:
    o = out(s)
    o.pop("history", None)
    if not full:
        for k in ("created_by", "teacher_block_needs_approval", "max_per_guardian"):
            o.pop(k, None)
    return o


# ---------------------------------------------------------------- admin: sessions
@router.get("/ptm/options")
async def options(ctx: Ctx = Depends(need("ptm.manage"))):
    years = await db.academic_years.find({"school_id": ctx.school_id}).sort("start_date", -1).to_list(10)
    secs = await db.sections.find({"school_id": ctx.school_id}).sort([("class_name", 1), ("name", 1)]).to_list(300)
    cls_year = {str(c["_id"]): c["academic_year_id"] for c in await db.classes.find({"school_id": ctx.school_id}).to_list(300)}
    asg = await db.teacher_assignments.find({"school_id": ctx.school_id}).to_list(2000)
    ts = await db.teachers.find({"school_id": ctx.school_id, "status": "active"}).sort("name", 1).to_list(300)
    return {"years": [{"id": str(y["_id"]), "name": y["name"], "is_current": y.get("is_current", False)} for y in years],
            "sections": [{"section_id": str(s["_id"]), "label": f"{s['class_name']} - {s['name']}", "class_name": s["class_name"],
                          "academic_year_id": cls_year.get(s["class_id"])} for s in secs],
            "teachers": [{"teacher_id": str(t["_id"]), "name": t["name"],
                          "section_ids": sorted({a["section_id"] for a in asg if a["teacher_id"] == str(t["_id"])})} for t in ts]}


@router.post("/ptm/sessions", status_code=201)
async def create_session(body: SessionIn, ctx: Ctx = Depends(need("ptm.manage"))):
    doc = await _validate(ctx, body)
    t = now_utc()
    doc.update({"school_id": ctx.school_id, "status": "draft", "created_by": ctx.user_id, "created_at": t, "updated_at": t,
                "published_at": None, "cancel_reason": None, "history": [_hist(ctx, "create")]})
    r = await db.ptm_sessions.insert_one(doc)
    s = {**doc, "_id": r.inserted_id}
    await audit(ctx.user_id, "ptm.create", "ptm_session", str(r.inserted_id), ctx.school_id)
    if body.action == "publish":
        await _publish(ctx, s)
    return _session_out(await db.ptm_sessions.find_one({"_id": r.inserted_id}), True)


@router.put("/ptm/sessions/{sid}")
async def update_session(sid: str, body: SessionIn, ctx: Ctx = Depends(need("ptm.manage"))):
    s = await _session(ctx, sid)
    if s["status"] != "draft":
        raise HTTPException(409, "Only draft sessions can be edited. Cancel and recreate a published session.")
    doc = await _validate(ctx, body)
    r = await db.ptm_sessions.update_one({"_id": s["_id"], "status": "draft"},
                                         {"$set": {**doc, "updated_at": now_utc()}, "$push": {"history": _hist(ctx, "edit")}})
    if not r.modified_count:
        raise HTTPException(409, "This session was changed by someone else")
    await audit(ctx.user_id, "ptm.edit", "ptm_session", sid, ctx.school_id)
    if body.action == "publish":
        await _publish(ctx, await _session(ctx, sid))
    return _session_out(await _session(ctx, sid), True)


@router.post("/ptm/sessions/{sid}/publish")
async def publish_session(sid: str, ctx: Ctx = Depends(need("ptm.manage"))):
    s = await _session(ctx, sid)
    if s["dates"][0] < _today():
        raise HTTPException(400, "PTM dates are in the past")
    await _publish(ctx, s)
    return _session_out(await _session(ctx, sid), True)


@router.post("/ptm/sessions/{sid}/cancel")
async def cancel_session(sid: str, reason: str = Query(min_length=3, max_length=200), ctx: Ctx = Depends(need("ptm.manage"))):
    s = await _session(ctx, sid)
    reason = sanitize(reason)
    t = now_utc()
    r = await db.ptm_sessions.update_one({"_id": s["_id"], "status": {"$in": ["draft", "published"]}},
                                         {"$set": {"status": "cancelled", "cancel_reason": reason, "cancelled_at": t, "updated_at": t},
                                          "$push": {"history": _hist(ctx, "cancel", reason=reason)}})
    if not r.modified_count:
        raise HTTPException(409, f"Cannot cancel a {s['status']} session")
    await db.ptm_slots.update_many({"session_id": sid}, {"$set": {"status": "cancelled"}})
    n = await _cancel_bookings(ctx, {"session_id": sid}, reason, "Session cancelled by school")
    await audit(ctx.user_id, "ptm.cancel", "ptm_session", sid, ctx.school_id, {"bookings_cancelled": n})
    return {**_session_out(await _session(ctx, sid), True), "bookings_cancelled": n}


async def _cancel_bookings(ctx: Ctx, filt: dict, reason: str, title: str) -> int:
    n = 0
    async for b in db.ptm_bookings.find({"school_id": ctx.school_id, "status": "confirmed", **filt}):
        res = await db.ptm_bookings.find_one_and_update(
            {"_id": b["_id"], "status": "confirmed"},
            {"$set": {"status": "cancelled_school", "active": False, "cancel_reason": reason, "updated_at": now_utc()},
             "$push": {"history": _hist(ctx, "cancelled_school", reason=reason)}})
        if res:
            n += 1
            await _release(res)
            await notify(ctx.school_id, b["guardian_user_id"], "ptm.session_cancelled", title,
                         f"{b['date']} {b['start_time']} meeting was cancelled: {reason}", "ptm_booking", str(b["_id"]))
    return n


@router.get("/ptm/sessions")
async def list_sessions(limit: int = Query(default=30, ge=1, le=100), skip: int = Query(default=0, ge=0, le=5000),
                        ctx: Ctx = Depends(school_ctx)):
    filt: dict = {"school_id": ctx.school_id}
    full = "ptm.manage" in ctx.perms
    if ctx.role == "parent":
        secs = {(await db.students.find_one({"_id": oid(lk["student_id"])}) or {}).get("section_id") for lk in await _parent_links(ctx)}
        filt.update({"status": {"$in": ["published", "cancelled"]}, "published_at": {"$ne": None}, "section_ids": {"$in": list(secs - {None})}})
    elif ctx.role == "teacher":
        t = await _my_teacher(ctx)
        filt.update({"status": {"$in": ["published", "cancelled"]}, "teacher_ids": str(t["_id"]) if t else "-"})
    elif not full:
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    items = await db.ptm_sessions.find(filt).sort("dates.0", -1).skip(skip).limit(limit).to_list(limit)
    res = []
    for s in items:
        o = _session_out(s, full)
        if full or ctx.role == "teacher":
            sf = {"session_id": str(s["_id"]), **({} if full else {"teacher_id": filt["teacher_ids"]})}
            agg = await db.ptm_slots.aggregate([{"$match": {**sf, "status": {"$ne": "cancelled"}}},
                                                {"$group": {"_id": None, "cap": {"$sum": "$capacity"}, "booked": {"$sum": "$booked"}}}]).to_list(1)
            o["capacity_total"], o["booked_total"] = (agg[0]["cap"], agg[0]["booked"]) if agg else (0, 0)
        res.append(o)
    return {"items": res}


async def _student_label(sid: str) -> dict:
    st = await db.students.find_one({"_id": oid(sid)}, {"first_name": 1, "last_name": 1, "class_name": 1, "section_name": 1})
    return {"student_name": f"{st['first_name']} {st['last_name']}", "class_label": f"{st['class_name']} - {st['section_name']}"} if st else {}


@router.get("/ptm/sessions/{sid}")
async def get_session(sid: str, ctx: Ctx = Depends(school_ctx)):
    s = await _session(ctx, sid)
    if "ptm.manage" in ctx.perms:
        o = _session_out(s, True)
        names = {str(t["_id"]): t["name"] for t in await db.teachers.find({"_id": {"$in": [oid(x) for x in s["teacher_ids"]]}}).to_list(100)}
        rows = await db.ptm_slots.aggregate([{"$match": {"session_id": sid}}, {"$group": {
            "_id": "$teacher_id", "slots": {"$sum": 1}, "cap": {"$sum": {"$cond": [{"$eq": ["$status", "available"]}, "$capacity", "$booked"]}},
            "booked": {"$sum": "$booked"}, "blocked": {"$sum": {"$cond": [{"$in": ["$status", ["blocked", "block_requested"]]}, 1, 0]}},
            "requests": {"$sum": {"$cond": [{"$eq": ["$status", "block_requested"]}, 1, 0]}}}}]).to_list(100)
        by = {r["_id"]: r for r in rows}
        o["teachers"] = [{"teacher_id": t, "name": names.get(t, "—"), **{k: by.get(t, {}).get(k, 0) for k in ("slots", "cap", "booked", "blocked", "requests")}}
                         for t in s["teacher_ids"]]
        o["section_labels"] = [f"{x['class_name']} - {x['name']}" for x in await db.sections.find({"_id": {"$in": [oid(i) for i in s["section_ids"]]}}).to_list(100)]
        st = {r["_id"]: r["n"] for r in await db.ptm_bookings.aggregate([{"$match": {"session_id": sid}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(10)}
        o["stats"] = {"booked": sum(r["booked"] for r in rows), "capacity": sum(r["cap"] for r in rows), "by_status": st}
        return o
    if ctx.role == "teacher":
        t = await _my_teacher(ctx)
        if not t or str(t["_id"]) not in s["teacher_ids"] or s["status"] == "draft":
            raise HTTPException(404, "PTM session not found")
        return _session_out(s, False)
    if ctx.role != "parent" or s["status"] == "draft" or not s.get("published_at"):
        raise HTTPException(404, "PTM session not found")
    children = []
    for lk in await _parent_links(ctx):
        stu = await db.students.find_one({"_id": oid(lk["student_id"]), "school_id": ctx.school_id, "status": "active"})
        if not stu or stu["section_id"] not in s["section_ids"]:
            continue
        ts = []
        for tid in s["teacher_ids"]:
            if await _teacher_teaches(ctx.school_id, tid, stu["section_id"]):
                t = await db.teachers.find_one({"_id": oid(tid), "status": "active"}, {"name": 1})
                if t:
                    ts.append({"teacher_id": tid, "name": t["name"]})
        children.append({"student_id": str(stu["_id"]), "name": f"{stu['first_name']} {stu['last_name']}", "teachers": ts})
    if not children:
        raise HTTPException(404, "PTM session not found")
    o = _session_out(s, False)
    o.pop("meeting_link", None)  # revealed only on a confirmed booking
    o["children"] = children
    return o


@router.get("/ptm/sessions/{sid}/slots")
async def session_slots(sid: str, teacher_id: str, student_id: Optional[str] = None, ctx: Ctx = Depends(school_ctx)):
    s = await _session(ctx, sid)
    if ctx.role == "parent":
        await _eligible(ctx, s, student_id or "", teacher_id)
    elif ctx.role == "teacher":
        t = await _my_teacher(ctx)
        if not t or str(t["_id"]) != teacher_id or teacher_id not in s["teacher_ids"]:
            raise HTTPException(404, "PTM session not found")
    elif "ptm.manage" not in ctx.perms:
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    slots = await db.ptm_slots.find({"session_id": sid, "teacher_id": teacher_id}).sort("start_at", 1).to_list(1000)
    staff = ctx.role != "parent"
    bk = {}
    if staff:
        async for b in db.ptm_bookings.find({"session_id": sid, "teacher_id": teacher_id, "status": {"$in": ["confirmed", "completed", "no_show"]}}):
            g = await db.users.find_one({"_id": oid(b["guardian_user_id"])}, {"name": 1})
            bk.setdefault(b["slot_id"], []).append({"booking_id": str(b["_id"]), "status": b["status"], "guardian_name": g["name"] if g else "—",
                                                     **await _student_label(b["student_id"])})
    now = now_utc()
    res = []
    for sl in slots:
        o = {"id": str(sl["_id"]), "date": sl["date"], "start_time": sl["start_time"], "end_time": sl["end_time"],
             "available": sl["status"] == "available" and sl["booked"] < sl["capacity"] and _aware(sl["start_at"]) > now}
        if staff:
            o.update({"status": sl["status"], "booked": sl["booked"], "capacity": sl["capacity"], "block_reason": sl.get("block_reason"),
                      "bookings": bk.get(str(sl["_id"]), [])})
        res.append(o)
    return {"items": res}


# ---------------------------------------------------------------- parent booking
async def _guardian(ctx: Ctx, student_id: str) -> dict:
    gids = {lk["guardian_id"] for lk in await _parent_links(ctx) if lk["student_id"] == student_id}
    if not gids:
        raise HTTPException(404, "Child not found")
    return {"guardian_id": sorted(gids)[0]}


async def _eligible(ctx: Ctx, s: dict, student_id: str, teacher_id: str) -> dict:
    if ctx.role != "parent":
        raise HTTPException(403, "Only parents can book PTM appointments")
    await _guardian(ctx, student_id)
    stu = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id, "status": "active"})
    if not stu or s["status"] == "draft" or not s.get("published_at") or stu["section_id"] not in s["section_ids"]:
        raise HTTPException(404, "PTM session not found")
    if teacher_id not in s["teacher_ids"] or not await _teacher_teaches(ctx.school_id, teacher_id, stu["section_id"]):
        raise HTTPException(404, "This teacher is not available for your child in this PTM")
    return stu


def _window(s: dict):
    now = now_utc()
    if s["status"] != "published":
        raise HTTPException(409, "This PTM has been cancelled")
    if s.get("booking_opens_at") and now < _aware(s["booking_opens_at"]):
        raise HTTPException(409, "Booking has not opened yet")
    if s.get("booking_closes_at") and now > _aware(s["booking_closes_at"]):
        raise HTTPException(409, "Booking for this PTM has closed")


async def _acquire_quota(sid: str, key: str, limit: int) -> bool:
    try:
        await db.ptm_quotas.find_one_and_update({"session_id": sid, "key": key, "count": {"$lt": limit}},
                                                {"$inc": {"count": 1}}, upsert=True)
        return True
    except DuplicateKeyError:
        return False


async def _release_quota(sid: str, key: str):
    await db.ptm_quotas.update_one({"session_id": sid, "key": key, "count": {"$gt": 0}}, {"$inc": {"count": -1}})


async def _seat(slot_id: str) -> Optional[dict]:
    return await db.ptm_slots.find_one_and_update(
        {"_id": oid(slot_id), "status": "available", "$expr": {"$lt": ["$booked", "$capacity"]}, "start_at": {"$gt": now_utc()}},
        {"$inc": {"booked": 1}}, return_document=ReturnDocument.AFTER)


async def _unseat(slot_id: str):
    await db.ptm_slots.update_one({"_id": oid(slot_id), "booked": {"$gt": 0}}, {"$inc": {"booked": -1}})


async def _release(b: dict):
    await _unseat(b["slot_id"])
    await _release_quota(b["session_id"], f"s:{b['student_id']}")
    await _release_quota(b["session_id"], f"g:{b['guardian_user_id']}")


async def _booking_out(b: dict, side: str) -> dict:
    o = out(b)
    o.pop("client_id", None)
    s = await db.ptm_sessions.find_one({"_id": oid(b["session_id"])}, {"name": 1, "mode": 1, "location": 1, "meeting_link": 1,
                                                                      "cancel_cutoff_hours": 1, "reschedule_cutoff_hours": 1, "status": 1})
    t = await db.teachers.find_one({"_id": oid(b["teacher_id"])}, {"name": 1})
    o.update({"session_name": s["name"] if s else "—", "mode": s.get("mode") if s else None, "location": s.get("location") if s else "",
              "teacher_name": t["name"] if t else "—", **await _student_label(b["student_id"])})
    if s and b["status"] == "confirmed" and s.get("mode") == "online":
        o["meeting_link"] = s.get("meeting_link")
    if s:
        start = _aware(b["start_at"])
        o["can_cancel"] = b["status"] == "confirmed" and now_utc() <= start - timedelta(hours=s["cancel_cutoff_hours"])
        o["can_reschedule"] = b["status"] == "confirmed" and now_utc() <= start - timedelta(hours=s["reschedule_cutoff_hours"])
        o["cancel_cutoff_hours"], o["reschedule_cutoff_hours"] = s["cancel_cutoff_hours"], s["reschedule_cutoff_hours"]
    fu = await db.ptm_followups.find({"booking_id": str(b["_id"]), **({"shared": True} if side == "parent" else {})}).sort("_id", 1).to_list(50)
    o["followups"] = [out(f) for f in fu]
    if side == "parent":
        o.pop("private_note", None)
        o["history"] = [{"at": h["at"], "action": h["action"]} for h in b.get("history", [])]
    else:
        g = await db.users.find_one({"_id": oid(b["guardian_user_id"])}, {"name": 1})
        o["guardian_name"] = g["name"] if g else "—"
    return o


async def _await_prior(ctx: Ctx, client_id: str) -> Optional[dict]:
    """Idempotent replay: wait (bounded) for a concurrent identical request to finish, then return its result."""
    import asyncio
    for _ in range(40):
        prior = await db.ptm_bookings.find_one({"guardian_user_id": ctx.user_id, "client_id": client_id})
        if not prior:
            return None
        if prior["status"] != "pending":
            return prior
        await asyncio.sleep(0.05)
    raise HTTPException(409, "Your previous booking request is still being processed. Please refresh.")


@router.post("/ptm/bookings", status_code=201)
async def book(body: BookIn, ctx: Ctx = Depends(need("parent.portal"))):
    prior = await _await_prior(ctx, body.client_id)
    if prior:
        if prior["status"] == "failed":
            raise HTTPException(409, prior.get("failure") or "This booking request could not be completed")
        return await _booking_out(prior, "parent")
    slot = await db.ptm_slots.find_one({"_id": oid(body.slot_id), "school_id": ctx.school_id})
    if not slot:
        raise HTTPException(404, "Slot not found")
    s = await _session(ctx, slot["session_id"])
    stu = await _eligible(ctx, s, body.student_id, slot["teacher_id"])
    _window(s)
    g = await _guardian(ctx, body.student_id)
    sid = slot["session_id"]
    t = now_utc()
    doc = {"school_id": ctx.school_id, "session_id": sid, "slot_id": body.slot_id, "teacher_id": slot["teacher_id"],
           "student_id": body.student_id, "guardian_id": g["guardian_id"], "guardian_user_id": ctx.user_id,
           "section_id": stu["section_id"], "class_name": stu["class_name"], "date": slot["date"],
           "start_time": slot["start_time"], "end_time": slot["end_time"], "start_at": slot["start_at"], "end_at": slot["end_at"],
           "status": "pending", "active": False, "client_id": body.client_id, "cancel_reason": None, "reschedules": [],
           "shared_note": "", "private_note": "", "created_by": ctx.user_id, "created_at": t, "updated_at": t, "history": []}
    # 1) claim the idempotency key first: concurrent retries of the same request collapse onto this document
    try:
        r = await db.ptm_bookings.insert_one(doc)
    except DuplicateKeyError:
        prior = await _await_prior(ctx, body.client_id)
        if prior and prior["status"] != "failed":
            return await _booking_out(prior, "parent")
        raise HTTPException(409, (prior or {}).get("failure") or "This booking request could not be completed")
    bid = r.inserted_id

    async def fail(msg: str, release_seat=False, release_quota=(False, False)):
        if release_seat:
            await _unseat(body.slot_id)
        if release_quota[0]:
            await _release_quota(sid, f"s:{body.student_id}")
        if release_quota[1]:
            await _release_quota(sid, f"g:{ctx.user_id}")
        await db.ptm_bookings.update_one({"_id": bid}, {"$set": {"status": "failed", "failure": msg, "updated_at": now_utc()}})
        raise HTTPException(409, msg)

    # 2) per-child / per-guardian limits, 3) seat — each conditional and atomic
    if not await _acquire_quota(sid, f"s:{body.student_id}", s["max_per_child"]):
        await fail(f"Your child already has the maximum of {s['max_per_child']} meetings in this PTM")
    if not await _acquire_quota(sid, f"g:{ctx.user_id}", s["max_per_guardian"]):
        await fail(f"You already have the maximum of {s['max_per_guardian']} meetings in this PTM", release_quota=(True, False))
    if not await _seat(body.slot_id):
        await fail("Sorry, this time was just taken. Please choose another slot.", release_quota=(True, True))
    # 4) go live: partial unique indexes reject a second live meeting with this teacher / at this time
    try:
        await db.ptm_bookings.update_one({"_id": bid, "status": "pending"},
                                         {"$set": {"status": "confirmed", "active": True, "updated_at": now_utc()},
                                          "$push": {"history": _hist(ctx, "booked", slot_id=body.slot_id)}})
    except DuplicateKeyError as e:
        key = str((e.details or {}).get("keyPattern", {}))
        await fail("Your child already has a meeting with this teacher. Reschedule it instead." if "teacher_id" in key
                   else "You already have another meeting at this time", True, (True, True))
    # a concurrent session cancel / block may have landed between seat and insert: never leave a live orphan
    live = await db.ptm_slots.find_one({"_id": oid(body.slot_id)}, {"status": 1})
    if not live or live["status"] == "cancelled":
        await _cancel_bookings(ctx, {"_id": bid}, "Session cancelled", "PTM appointment cancelled")
        raise HTTPException(409, "This PTM has been cancelled")
    await audit(ctx.user_id, "ptm.book", "ptm_booking", str(bid), ctx.school_id, {"slot_id": body.slot_id})
    tname = (await db.teachers.find_one({"_id": oid(slot["teacher_id"])}, {"name": 1, "user_id": 1})) or {}
    await notify(ctx.school_id, ctx.user_id, "ptm.booked", "PTM booking confirmed",
                 f"{tname.get('name', 'Teacher')} · {slot['date']} {slot['start_time']} IST", "ptm_booking", str(bid))
    await notify(ctx.school_id, tname.get("user_id"), "ptm.booked", "New PTM booking",
                 f"{slot['date']} {slot['start_time']} IST", "ptm_booking", str(bid))
    return await _booking_out(await db.ptm_bookings.find_one({"_id": bid}), "parent")


async def _booking_for(ctx: Ctx, bid: str) -> tuple[dict, str]:
    b = await db.ptm_bookings.find_one({"_id": oid(bid), "school_id": ctx.school_id})
    if not b:
        raise HTTPException(404, "Booking not found")
    if b["status"] in ("pending", "failed"):
        raise HTTPException(404, "Booking not found")
    if ctx.role == "parent" and b["guardian_user_id"] == ctx.user_id and b["student_id"] in {lk["student_id"] for lk in await _parent_links(ctx)}:
        return b, "parent"
    if ctx.role == "teacher":
        t = await _my_teacher(ctx)
        if t and str(t["_id"]) == b["teacher_id"] and await _teacher_teaches(ctx.school_id, b["teacher_id"], b["section_id"]):
            return b, "teacher"
    if "ptm.manage" in ctx.perms:
        return b, "admin"
    raise HTTPException(404, "Booking not found")


@router.get("/ptm/bookings/{bid}")
async def get_booking(bid: str, ctx: Ctx = Depends(school_ctx)):
    b, side = await _booking_for(ctx, bid)
    return await _booking_out(b, side)


@router.post("/ptm/bookings/{bid}/cancel")
async def cancel_booking(bid: str, reason: str = Query(default="", max_length=200), ctx: Ctx = Depends(school_ctx)):
    b, side = await _booking_for(ctx, bid)
    if side == "teacher":
        raise HTTPException(403, "Ask the school office to cancel a booked meeting")
    s = await db.ptm_sessions.find_one({"_id": oid(b["session_id"])})
    reason = sanitize(reason)
    if side == "admin":
        if not reason:
            raise HTTPException(400, "Give a reason for cancelling on behalf of the school")
        if not await _cancel_bookings(ctx, {"_id": b["_id"]}, reason, "PTM appointment cancelled by school"):
            raise HTTPException(409, f"Cannot cancel a {b['status']} booking")
        await audit(ctx.user_id, "ptm.booking_cancel_school", "ptm_booking", bid, ctx.school_id)
        return await _booking_out(await db.ptm_bookings.find_one({"_id": b["_id"]}), side)
    if b["status"] != "confirmed":
        raise HTTPException(409, f"Cannot cancel a {b['status'].replace('_', ' ')} booking")
    if now_utc() > _aware(b["start_at"]) - timedelta(hours=s["cancel_cutoff_hours"]):
        raise HTTPException(409, f"Bookings can be cancelled up to {s['cancel_cutoff_hours']} hours before the meeting")
    res = await db.ptm_bookings.find_one_and_update(
        {"_id": b["_id"], "status": "confirmed"},
        {"$set": {"status": "cancelled_parent", "active": False, "cancel_reason": reason or None, "updated_at": now_utc()},
         "$push": {"history": _hist(ctx, "cancelled_parent", reason=reason or None)}}, return_document=ReturnDocument.AFTER)
    if not res:
        raise HTTPException(409, "This booking was already changed")
    await _release(res)
    await audit(ctx.user_id, "ptm.booking_cancel", "ptm_booking", bid, ctx.school_id)
    await notify(ctx.school_id, ctx.user_id, "ptm.cancelled", "PTM appointment cancelled", f"{b['date']} {b['start_time']} IST", "ptm_booking", bid)
    t = await db.teachers.find_one({"_id": oid(b["teacher_id"])}, {"user_id": 1})
    await notify(ctx.school_id, (t or {}).get("user_id"), "ptm.cancelled", "A parent cancelled a PTM booking", f"{b['date']} {b['start_time']} IST", "ptm_booking", bid)
    return await _booking_out(res, side)


@router.post("/ptm/bookings/{bid}/reschedule")
async def reschedule(bid: str, body: RescheduleIn, ctx: Ctx = Depends(need("parent.portal"))):
    b, side = await _booking_for(ctx, bid)
    if b["status"] != "confirmed":
        raise HTTPException(409, "Only confirmed bookings can be rescheduled")
    if body.slot_id == b["slot_id"]:
        raise HTTPException(400, "Choose a different time")
    s = await _session(ctx, b["session_id"])
    _window(s)
    if now_utc() > _aware(b["start_at"]) - timedelta(hours=s["reschedule_cutoff_hours"]):
        raise HTTPException(409, f"Bookings can be rescheduled up to {s['reschedule_cutoff_hours']} hours before the meeting")
    new = await db.ptm_slots.find_one({"_id": oid(body.slot_id), "session_id": b["session_id"], "teacher_id": b["teacher_id"]})
    if not new:
        raise HTTPException(404, "Choose another time with the same teacher in this PTM")
    await _eligible(ctx, s, b["student_id"], b["teacher_id"])
    if not await _seat(body.slot_id):
        raise HTTPException(409, "Sorry, that time was just taken. Your original booking is unchanged.")
    move = {"from": {"slot_id": b["slot_id"], "date": b["date"], "start_time": b["start_time"]},
            "to": {"slot_id": body.slot_id, "date": new["date"], "start_time": new["start_time"]}, "at": now_utc(), "by": ctx.user_id}
    try:
        res = await db.ptm_bookings.find_one_and_update(
            {"_id": b["_id"], "status": "confirmed", "slot_id": b["slot_id"]},
            {"$set": {"slot_id": body.slot_id, "date": new["date"], "start_time": new["start_time"], "end_time": new["end_time"],
                      "start_at": new["start_at"], "end_at": new["end_at"], "updated_at": now_utc()},
             "$push": {"reschedules": move, "history": _hist(ctx, "rescheduled", **move)}}, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        res = None
        await _unseat(body.slot_id)
        raise HTTPException(409, "You already have another meeting at that time. Your original booking is unchanged.")
    if not res:
        await _unseat(body.slot_id)
        raise HTTPException(409, "This booking was changed elsewhere. Your original booking is unchanged.")
    await _unseat(b["slot_id"])
    await audit(ctx.user_id, "ptm.reschedule", "ptm_booking", bid, ctx.school_id, {"to": body.slot_id})
    await notify(ctx.school_id, ctx.user_id, "ptm.rescheduled", "PTM appointment rescheduled", f"Now {new['date']} {new['start_time']} IST", "ptm_booking", bid)
    t = await db.teachers.find_one({"_id": oid(b["teacher_id"])}, {"user_id": 1})
    await notify(ctx.school_id, (t or {}).get("user_id"), "ptm.rescheduled", "A PTM booking was rescheduled", f"Now {new['date']} {new['start_time']} IST", "ptm_booking", bid)
    return await _booking_out(res, side)


@router.get("/ptm/my-bookings")
async def my_bookings(scope: Literal["upcoming", "past"] = "upcoming", limit: int = Query(default=30, ge=1, le=100),
                      skip: int = Query(default=0, ge=0, le=5000), ctx: Ctx = Depends(need("parent.portal"))):
    await ensure_reminders(ctx)
    kids = [lk["student_id"] for lk in await _parent_links(ctx)]
    filt = {"school_id": ctx.school_id, "guardian_user_id": ctx.user_id, "student_id": {"$in": kids}}
    if scope == "upcoming":
        filt.update({"status": "confirmed", "end_at": {"$gte": now_utc()}})
        sort = 1
    else:
        filt["$or"] = [{"status": {"$nin": ["confirmed", "pending", "failed"]}}, {"status": "confirmed", "end_at": {"$lt": now_utc()}}]
        sort = -1
    items = await db.ptm_bookings.find(filt).sort("start_at", sort).skip(skip).limit(limit).to_list(limit)
    return {"items": [await _booking_out(b, "parent") for b in items]}


async def ensure_reminders(ctx: Ctx):
    """Durable 24-hour reminders, generated idempotently when the parent next opens the app."""
    soon = now_utc() + timedelta(hours=24)
    async for b in db.ptm_bookings.find({"school_id": ctx.school_id, "guardian_user_id": ctx.user_id, "status": "confirmed",
                                         "start_at": {"$gt": now_utc(), "$lte": soon}}).limit(20):
        await notify(ctx.school_id, ctx.user_id, "ptm.reminder", "Upcoming PTM reminder", f"{b['date']} {b['start_time']} IST",
                     "ptm_booking", str(b["_id"]), dedupe=f"ptm-reminder:{b['_id']}:{b['start_at'].isoformat()}")


# ---------------------------------------------------------------- teacher: schedule, availability, outcomes, follow-ups
@router.get("/ptm/schedule")
async def teacher_schedule(day: Optional[date] = None, ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    if not t:
        return {"items": []}
    d = (day or now_utc().astimezone(IST).date()).isoformat()
    secs = set(await db.teacher_assignments.distinct("section_id", {"school_id": ctx.school_id, "teacher_id": str(t["_id"])}))
    items = await db.ptm_bookings.find({"school_id": ctx.school_id, "teacher_id": str(t["_id"]), "date": d,
                                        "status": {"$in": ["confirmed", "completed", "no_show"]}, "section_id": {"$in": list(secs)}}).sort("start_at", 1).to_list(200)
    return {"date": d, "items": [await _booking_out(b, "teacher") for b in items]}


@router.post("/ptm/slots/{slot_id}/availability")
async def slot_availability(slot_id: str, act: Literal["block", "unblock", "approve", "reject"],
                            reason: str = Query(default="", max_length=200), ctx: Ctx = Depends(school_ctx)):
    sl = await db.ptm_slots.find_one({"_id": oid(slot_id), "school_id": ctx.school_id})
    if not sl:
        raise HTTPException(404, "Slot not found")
    s = await _session(ctx, sl["session_id"])
    if s["status"] != "published":
        raise HTTPException(409, "This PTM is not active")
    reason = sanitize(reason)
    admin = "ptm.manage" in ctx.perms
    if not admin:
        t = await _my_teacher(ctx)
        if ctx.role != "teacher" or not t or str(t["_id"]) != sl["teacher_id"] or act in ("approve", "reject"):
            raise HTTPException(404, "Slot not found")
    elif not reason:
        raise HTTPException(400, "Give a reason for the override")
    if act == "block":
        new = "block_requested" if (not admin and s["teacher_block_needs_approval"]) else "blocked"
        r = await db.ptm_slots.update_one({"_id": sl["_id"], "status": "available", "booked": 0},
                                          {"$set": {"status": new, "block_reason": reason or "Unavailable", "blocked_by": ctx.user_id}})
        if not r.modified_count:
            raise HTTPException(409, "Only free, unbooked slots can be marked unavailable")
    elif act == "unblock":
        filt = {"_id": sl["_id"], "status": {"$in": ["blocked", "block_requested"]}}
        if not admin:
            filt["blocked_by"] = ctx.user_id
        r = await db.ptm_slots.update_one(filt, {"$set": {"status": "available", "block_reason": None, "blocked_by": None}})
        if not r.modified_count:
            raise HTTPException(409, "This slot cannot be re-opened by you")
    else:
        r = await db.ptm_slots.update_one({"_id": sl["_id"], "status": "block_requested"},
                                          {"$set": {"status": "blocked" if act == "approve" else "available",
                                                    **({} if act == "approve" else {"block_reason": None, "blocked_by": None})}})
        if not r.modified_count:
            raise HTTPException(409, "There is no pending request for this slot")
    await audit(ctx.user_id, f"ptm.slot_{act}", "ptm_slot", slot_id, ctx.school_id, {"reason": reason or None, "override": admin})
    sl = await db.ptm_slots.find_one({"_id": sl["_id"]})
    return {"id": slot_id, "status": sl["status"], "block_reason": sl.get("block_reason")}


@router.get("/ptm/me")
async def ptm_me(ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    return {"teacher_id": str(t["_id"]) if t else None}


@router.post("/ptm/unavailability", status_code=201)
async def add_unavailability(body: UnavailIn, ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    if not t:
        raise HTTPException(403, "Teacher profile not found")
    if body.end_time <= body.start_time:
        raise HTTPException(400, "End time must be after the start time")
    d = body.date.isoformat()
    a, b = _at(d, body.start_time), _at(d, body.end_time)
    r = await db.ptm_unavailability.insert_one({"school_id": ctx.school_id, "teacher_id": str(t["_id"]), "date": d, "start_at": a, "end_at": b,
                                                "start_time": body.start_time, "end_time": body.end_time, "reason": sanitize(body.reason),
                                                "created_by": ctx.user_id, "created_at": now_utc()})
    blocked = requested = 0
    async for sl in db.ptm_slots.find({"school_id": ctx.school_id, "teacher_id": str(t["_id"]), "status": "available", "booked": 0,
                                       "start_at": {"$lt": b}, "end_at": {"$gt": a}}):
        s = await db.ptm_sessions.find_one({"_id": oid(sl["session_id"])}, {"teacher_block_needs_approval": 1})
        new = "block_requested" if s and s.get("teacher_block_needs_approval") else "blocked"
        u = await db.ptm_slots.update_one({"_id": sl["_id"], "status": "available", "booked": 0},
                                          {"$set": {"status": new, "block_reason": sanitize(body.reason) or "Unavailable", "blocked_by": ctx.user_id}})
        blocked += u.modified_count if new == "blocked" else 0
        requested += u.modified_count if new == "block_requested" else 0
    booked = await db.ptm_bookings.count_documents({"school_id": ctx.school_id, "teacher_id": str(t["_id"]), "status": "confirmed",
                                                    "start_at": {"$lt": b}, "end_at": {"$gt": a}})
    await audit(ctx.user_id, "ptm.unavailability", "ptm_unavailability", str(r.inserted_id), ctx.school_id)
    return {"id": str(r.inserted_id), "blocked": blocked, "requested": requested, "booked_conflicts": booked}


@router.post("/ptm/bookings/{bid}/outcome")
async def outcome(bid: str, body: OutcomeIn, ctx: Ctx = Depends(school_ctx)):
    b, side = await _booking_for(ctx, bid)
    if side == "parent":
        raise HTTPException(403, "Only the teacher can record the meeting outcome")
    if now_utc() < _aware(b["start_at"]):
        raise HTTPException(409, "You can record the outcome once the meeting time has started")
    res = await db.ptm_bookings.find_one_and_update(
        {"_id": b["_id"], "status": "confirmed"},
        {"$set": {"status": body.status, "active": False, "shared_note": sanitize(body.shared_note), "private_note": sanitize(body.private_note),
                  "outcome_at": now_utc(), "outcome_by": ctx.user_id, "updated_at": now_utc()},
         "$push": {"history": _hist(ctx, body.status)}}, return_document=ReturnDocument.AFTER)
    if not res:
        raise HTTPException(409, f"Cannot record an outcome for a {b['status'].replace('_', ' ')} booking")
    # meeting happened: the time slot is consumed, but per-child/guardian quotas are kept (no re-booking loop)
    await audit(ctx.user_id, f"ptm.{body.status}", "ptm_booking", bid, ctx.school_id)
    if res["shared_note"]:
        await notify(ctx.school_id, b["guardian_user_id"], "ptm.followup_shared", "PTM notes shared by the teacher", res["shared_note"][:120], "ptm_booking", bid)
    return await _booking_out(res, side)


@router.patch("/ptm/bookings/{bid}/notes")
async def notes(bid: str, body: NotesIn, ctx: Ctx = Depends(school_ctx)):
    b, side = await _booking_for(ctx, bid)
    if side != "teacher":
        raise HTTPException(403, "Only the meeting's teacher can edit notes")
    if b["status"] not in OUTCOMES:
        raise HTTPException(409, "Record the meeting outcome first")
    data = {k: sanitize(v) for k, v in body.model_dump(exclude_none=True).items()}
    if not data:
        raise HTTPException(400, "No changes supplied")
    await db.ptm_bookings.update_one({"_id": b["_id"]}, {"$set": {**data, "updated_at": now_utc()}, "$push": {"history": _hist(ctx, "notes", fields=list(data))}})
    await audit(ctx.user_id, "ptm.notes", "ptm_booking", bid, ctx.school_id, {"fields": list(data)})
    if data.get("shared_note") and data["shared_note"] != b.get("shared_note"):
        await notify(ctx.school_id, b["guardian_user_id"], "ptm.followup_shared", "PTM notes shared by the teacher", data["shared_note"][:120], "ptm_booking", bid)
    return await _booking_out(await db.ptm_bookings.find_one({"_id": b["_id"]}), side)


@router.post("/ptm/bookings/{bid}/followups", status_code=201)
async def add_followup(bid: str, body: FollowupIn, ctx: Ctx = Depends(school_ctx)):
    b, side = await _booking_for(ctx, bid)
    if side != "teacher":
        raise HTTPException(403, "Only the meeting's teacher can add follow-ups")
    if b["status"] not in OUTCOMES:
        raise HTTPException(409, "Record the meeting outcome first")
    doc = {"school_id": ctx.school_id, "booking_id": bid, "session_id": b["session_id"], "teacher_id": b["teacher_id"],
           "student_id": b["student_id"], "class_name": b["class_name"], "section_id": b["section_id"],
           "title": sanitize(body.title), "due_date": body.due_date.isoformat() if body.due_date else None, "shared": body.shared,
           "status": "open", "created_by": ctx.user_id, "created_at": now_utc(), "resolved_at": None}
    r = await db.ptm_followups.insert_one(doc)
    await audit(ctx.user_id, "ptm.followup_add", "ptm_followup", str(r.inserted_id), ctx.school_id, {"shared": body.shared})
    if body.shared:
        await notify(ctx.school_id, b["guardian_user_id"], "ptm.followup_shared", "New PTM follow-up", doc["title"], "ptm_booking", bid)
    return out({**doc, "_id": r.inserted_id})


@router.post("/ptm/followups/{fid}/resolve")
async def resolve_followup(fid: str, ctx: Ctx = Depends(school_ctx)):
    f = await db.ptm_followups.find_one({"_id": oid(fid), "school_id": ctx.school_id})
    if not f:
        raise HTTPException(404, "Follow-up not found")
    _b, side = await _booking_for(ctx, f["booking_id"])
    if side == "parent":
        raise HTTPException(403, "Only school staff can resolve follow-ups")
    r = await db.ptm_followups.update_one({"_id": f["_id"], "status": "open"}, {"$set": {"status": "resolved", "resolved_at": now_utc(), "resolved_by": ctx.user_id}})
    if not r.modified_count:
        raise HTTPException(409, "Already resolved")
    await audit(ctx.user_id, "ptm.followup_resolve", "ptm_followup", fid, ctx.school_id)
    return out(await db.ptm_followups.find_one({"_id": f["_id"]}))


@router.get("/ptm/sessions/{sid}/bookings")
async def session_bookings(sid: str, status: Optional[str] = None, limit: int = Query(default=50, ge=1, le=100),
                           skip: int = Query(default=0, ge=0, le=10000), ctx: Ctx = Depends(need("ptm.manage"))):
    await _session(ctx, sid)
    filt = {"school_id": ctx.school_id, "session_id": sid, **({"status": status} if status else {})}
    items = await db.ptm_bookings.find(filt).sort("start_at", 1).skip(skip).limit(limit).to_list(limit)
    return {"items": [await _booking_out(b, "admin") for b in items], "total": await db.ptm_bookings.count_documents(filt)}


# ---------------------------------------------------------------- insights
@router.get("/ptm/insights")
async def insights(start: Optional[date] = None, end: Optional[date] = None, class_name: Optional[str] = None,
                   section_id: Optional[str] = None, teacher_id: Optional[str] = None, ctx: Ctx = Depends(need("ptm.manage"))):
    sf: dict = {"school_id": ctx.school_id, "status": {"$in": ["published", "cancelled"]}}
    if start or end:
        sf["dates"] = {"$elemMatch": {**({"$gte": start.isoformat()} if start else {}), **({"$lte": end.isoformat()} if end else {})}}
    secs_filter = None
    if section_id:
        secs_filter = [section_id]
    elif class_name:
        secs_filter = [str(x) for x in await db.sections.distinct("_id", {"school_id": ctx.school_id, "class_name": class_name})]
    if secs_filter is not None:
        sf["section_ids"] = {"$in": secs_filter}
    if teacher_id:
        sf["teacher_ids"] = teacher_id
    sessions = await db.ptm_sessions.find(sf).to_list(500)
    sids = [str(s["_id"]) for s in sessions]
    live = [s for s in sessions if s["status"] == "published"]
    # eligible households: distinct active parent accounts with a verified, active child in a live session's (filtered) sections
    secs = set()
    for s in live:
        secs |= set(s["section_ids"]) & set(secs_filter) if secs_filter is not None else set(s["section_ids"])
    studs = [str(x) for x in await db.students.distinct("_id", {"school_id": ctx.school_id, "section_id": {"$in": list(secs)}, "status": "active"})]
    gids = await db.guardian_links.distinct("guardian_id", {"student_id": {"$in": studs}, "verified": True})
    gusers = await db.guardians.distinct("user_id", {"_id": {"$in": [oid(g) for g in gids]}, "user_id": {"$ne": None}})
    households = len(await db.memberships.distinct("user_id", {"school_id": ctx.school_id, "role": "parent", "status": "active", "user_id": {"$in": gusers}}))
    slot_f: dict = {"session_id": {"$in": [str(s["_id"]) for s in live]}, **({"teacher_id": teacher_id} if teacher_id else {})}
    if start or end:
        slot_f["date"] = {**({"$gte": start.isoformat()} if start else {}), **({"$lte": end.isoformat()} if end else {})}
    agg = await db.ptm_slots.aggregate([{"$match": slot_f}, {"$group": {
        "_id": None, "bookable": {"$sum": {"$cond": [{"$eq": ["$status", "available"]}, "$capacity", "$booked"]}},
        "booked": {"$sum": "$booked"},
        "free": {"$sum": {"$cond": [{"$and": [{"$eq": ["$status", "available"]}, {"$gt": ["$start_at", now_utc()]}]}, {"$subtract": ["$capacity", "$booked"]}, 0]}}}}]).to_list(1)
    a = agg[0] if agg else {"bookable": 0, "booked": 0, "free": 0}
    bf: dict = {"school_id": ctx.school_id, "session_id": {"$in": sids}, **({"teacher_id": teacher_id} if teacher_id else {})}
    if secs_filter is not None:
        bf["section_id"] = {"$in": secs_filter}
    if start or end:
        bf["date"] = slot_f["date"]
    by_status = {r["_id"]: r["n"] for r in await db.ptm_bookings.aggregate([{"$match": bf}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(10)}
    kept = {**bf, "status": {"$in": ["confirmed", "completed", "no_show"]}}
    by_class = await db.ptm_bookings.aggregate([{"$match": kept}, {"$group": {"_id": "$class_name", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]).to_list(50)
    by_teacher = await db.ptm_bookings.aggregate([{"$match": kept}, {"$group": {"_id": "$teacher_id", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}, {"$limit": 20}]).to_list(20)
    names = {str(t["_id"]): t["name"] for t in await db.teachers.find({"_id": {"$in": [oid(x["_id"]) for x in by_teacher]}}).to_list(20)}
    pending = await db.ptm_followups.count_documents({"school_id": ctx.school_id, "session_id": {"$in": sids}, "status": "open",
                                                      **({"teacher_id": teacher_id} if teacher_id else {}),
                                                      **({"section_id": {"$in": secs_filter}} if secs_filter is not None else {})})
    booked_total = sum(by_status.get(k, 0) for k in ("confirmed", "completed", "no_show"))
    return {"sessions": len(sessions), "live_sessions": len(live), "eligible_households": households,
            "booked": booked_total, "available": a["free"], "capacity": a["bookable"],
            "utilization": round(a["booked"] / a["bookable"], 3) if a["bookable"] else 0.0,
            "completed": by_status.get("completed", 0), "no_show": by_status.get("no_show", 0),
            "cancelled": by_status.get("cancelled_parent", 0) + by_status.get("cancelled_school", 0),
            "cancelled_by_parent": by_status.get("cancelled_parent", 0), "cancelled_by_school": by_status.get("cancelled_school", 0),
            "followups_pending": pending,
            "by_class": [{"class_name": r["_id"], "bookings": r["n"]} for r in by_class],
            "by_teacher": [{"teacher_id": r["_id"], "name": names.get(r["_id"], "—"), "bookings": r["n"]} for r in by_teacher],
            "definitions": {"booked": "Confirmed + completed + no-show appointments", "available": "Unbooked seats in open future slots of live sessions",
                            "utilization": "Booked seats ÷ bookable seats (open slots + seats already booked)",
                            "eligible_households": "Active parent accounts with a verified, active child in a live session's sections"}}


# ---------------------------------------------------------------- calendar feed hook
async def ptm_calendar_items(ctx: Ctx, secs: Optional[set], s: str, e: str, manager: bool) -> list[dict]:
    filt: dict = {"school_id": ctx.school_id, "dates": {"$elemMatch": {"$gte": s, "$lte": e}}}
    if not manager:
        filt.update({"status": {"$in": ["published", "cancelled"]}, "published_at": {"$ne": None}})
    if ctx.role == "parent":
        filt["section_ids"] = {"$in": list(secs or [])}
    elif ctx.role == "teacher":
        t = await _my_teacher(ctx)
        filt["teacher_ids"] = str(t["_id"]) if t else "-"
    res = []
    async for x in db.ptm_sessions.find(filt).limit(50):
        for d in x["dates"]:
            if s <= d <= e:
                res.append({"id": str(x["_id"]), "kind": "ptm", "title": x["name"], "category": "ptm",
                            "description": "Online meeting" if x["mode"] == "online" else "In person", "start_date": d, "end_date": d,
                            "start_time": x["start_time"], "end_time": x["end_time"], "location": x.get("location", ""),
                            "status": x["status"], "cancel_reason": x.get("cancel_reason")})
    return res
