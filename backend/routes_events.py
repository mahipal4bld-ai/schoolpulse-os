"""Milestone 3 — Module 3: School events & calendar (targeted events + exam schedule in one role-scoped feed)."""
import re
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_notices import IST, Audience, _parent_scope, _validate_audience, sanitize

router = APIRouter()
Category = Literal["academic", "holiday", "exam", "sports", "cultural", "meeting", "ptm", "other"]
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_SPAN, MAX_RANGE = 60, 92


def _valid_time(v):
    if v in (None, ""):
        return None
    if not _HHMM.match(v):
        raise ValueError("Time must be HH:MM (24-hour)")
    return v


class EventIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=2000)
    category: Category = "academic"
    start_date: date
    end_date: Optional[date] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: str = Field(default="", max_length=120)
    audience: Audience = Audience()
    action: Literal["draft", "publish"] = "draft"

    _t = field_validator("start_time", "end_time")(_valid_time)


class EventPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    location: Optional[str] = Field(default=None, max_length=120)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    _t = field_validator("start_time", "end_time")(_valid_time)


def _check_dates(d: dict):
    if d["end_date"] < d["start_date"]:
        raise HTTPException(400, "End date must be on or after the start date")
    if (date.fromisoformat(d["end_date"]) - date.fromisoformat(d["start_date"])).days > MAX_SPAN:
        raise HTTPException(400, f"An event can span at most {MAX_SPAN} days")
    if d.get("end_time") and not d.get("start_time"):
        raise HTTPException(400, "Add a start time before an end time")
    if d.get("start_time") and d.get("end_time") and d["start_date"] == d["end_date"] and d["end_time"] <= d["start_time"]:
        raise HTTPException(400, "End time must be after the start time")


async def _get(ctx: Ctx, eid: str) -> dict:
    e = await db.events.find_one({"_id": oid(eid), "school_id": ctx.school_id})
    if not e:
        raise HTTPException(404, "Event not found")
    return e


def _event_out(e: dict, manager: bool) -> dict:
    o = out(e)
    o["kind"] = "event"
    if not manager:
        for k in ("created_by", "audience", "status_history"):
            o.pop(k, None)
    return o


@router.post("/events", status_code=201)
async def create(body: EventIn, ctx: Ctx = Depends(need("notices.manage"))):
    aud = await _validate_audience(ctx, body.audience)
    t = now_utc()
    doc = {"school_id": ctx.school_id, "title": sanitize(body.title), "description": sanitize(body.description),
           "category": body.category, "start_date": body.start_date.isoformat(),
           "end_date": (body.end_date or body.start_date).isoformat(), "start_time": body.start_time,
           "end_time": body.end_time, "location": sanitize(body.location), "audience": aud,
           "status": "published" if body.action == "publish" else "draft",
           "published_at": t if body.action == "publish" else None, "cancel_reason": None,
           "created_by": ctx.user_id, "created_at": t, "updated_at": t,
           "status_history": [{"status": "published" if body.action == "publish" else "draft", "by": ctx.user_id, "at": t}]}
    if not doc["title"]:
        raise HTTPException(400, "Title cannot be empty")
    _check_dates(doc)
    r = await db.events.insert_one(doc)
    await audit(ctx.user_id, f"event.{doc['status']}", "event", str(r.inserted_id), ctx.school_id, {"category": body.category})
    return _event_out({**doc, "_id": r.inserted_id}, True)


@router.patch("/events/{eid}")
async def edit(eid: str, body: EventPatch, ctx: Ctx = Depends(need("notices.manage"))):
    e = await _get(ctx, eid)
    if e["status"] == "cancelled":
        raise HTTPException(400, "A cancelled event cannot be edited")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "No changes supplied")
    for k in ("title", "description", "location"):
        if k in data:
            data[k] = sanitize(data[k] or "")
    if "title" in data and not data["title"]:
        raise HTTPException(400, "Title cannot be empty")
    for k in ("start_date", "end_date"):
        if data.get(k):
            data[k] = data[k].isoformat()
        elif k in data:
            data.pop(k)
    if "start_date" in data and "end_date" not in data and e["end_date"] < data["start_date"]:
        data["end_date"] = data["start_date"]
    _check_dates({**e, **data})
    await db.events.update_one({"_id": e["_id"], "status": e["status"]}, {"$set": {**data, "updated_at": now_utc()}})
    await audit(ctx.user_id, "event.edit", "event", eid, ctx.school_id, {"fields": list(data), "was": e["status"]})
    return _event_out(await db.events.find_one({"_id": e["_id"]}), True)


@router.post("/events/{eid}/action")
async def action(eid: str, act: Literal["publish", "cancel"], reason: Optional[str] = Query(default=None, max_length=200),
                 ctx: Ctx = Depends(need("notices.manage"))):
    e = await _get(ctx, eid)
    allowed = {"publish": {"draft"}, "cancel": {"draft", "published"}}
    if e["status"] not in allowed[act]:
        raise HTTPException(409, f"Cannot {act} a {e['status']} event")
    reason = sanitize(reason or "") or None
    if act == "cancel" and e["status"] == "published" and not reason:
        raise HTTPException(400, "Give a reason so families know why the event was cancelled")
    t = now_utc()
    new = "published" if act == "publish" else "cancelled"
    st = {"status": new, "updated_at": t, **({"published_at": t} if new == "published" else {"cancel_reason": reason, "cancelled_at": t})}
    r = await db.events.update_one({"_id": e["_id"], "status": e["status"]},
                                   {"$set": st, "$push": {"status_history": {"status": new, "by": ctx.user_id, "at": t}}})
    if not r.modified_count:
        raise HTTPException(409, "This event was changed by someone else. Refresh and try again.")
    await audit(ctx.user_id, f"event.{new}", "event", eid, ctx.school_id)
    return _event_out(await db.events.find_one({"_id": e["_id"]}), True)


# ---------------------------------------------------------------- unified calendar feed
async def _teacher_scope(ctx: Ctx) -> tuple[set, set]:
    t = await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id, "status": "active"})
    if not t:
        return set(), set()
    secs = set(await db.teacher_assignments.distinct("section_id", {"school_id": ctx.school_id, "teacher_id": str(t["_id"])}))
    classes = set(await db.sections.distinct("class_name", {"_id": {"$in": [oid(s) for s in secs]}}))
    return secs, classes


def _audience_or(secs: set, classes: set) -> list[dict]:
    return [{"audience.scope": "school"}, {"audience.scope": "classes", "audience.class_names": {"$in": list(classes)}},
            {"audience.scope": "sections", "audience.section_ids": {"$in": list(secs)}}]


async def _exam_items(ctx: Ctx, secs: Optional[set], start: str, end: str) -> list[dict]:
    filt = {"school_id": ctx.school_id, "status": {"$ne": "deleted"}, "start_date": {"$lte": end}, "end_date": {"$gte": start}}
    if secs is not None:
        filt["section_ids"] = {"$in": list(secs)}
    subs = {str(s["_id"]): s["name"] for s in await db.subjects.find({"school_id": ctx.school_id}).to_list(300)}
    res = []
    async for x in db.exams.find(filt).sort("start_date", 1).limit(50):
        papers = sorted(({"subject": subs.get(s["subject_id"], "Subject"), "date": s["date"]} for s in x.get("subjects", [])
                         if s.get("date")), key=lambda p: p["date"])
        res.append({"id": str(x["_id"]), "kind": "exam", "title": x["name"], "category": "exam", "description": x.get("term", ""),
                    "start_date": x["start_date"], "end_date": x["end_date"], "start_time": None, "end_time": None,
                    "location": "", "status": "published", "papers": papers})
    return res


@router.get("/calendar")
async def calendar(start: date, end: date, student_id: Optional[str] = None, ctx: Ctx = Depends(school_ctx)):
    if end < start or (end - start).days > MAX_RANGE:
        raise HTTPException(400, f"Choose a range of up to {MAX_RANGE} days")
    s, e = start.isoformat(), end.isoformat()
    manager = "notices.manage" in ctx.perms
    filt: dict = {"school_id": ctx.school_id, "start_date": {"$lte": e}, "end_date": {"$gte": s}}
    secs: Optional[set] = None
    if ctx.role == "parent":
        secs, classes = await _parent_scope(ctx)
        if student_id:
            st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id, "status": "active"})
            if not st or st["section_id"] not in secs:
                raise HTTPException(404, "Child not found")
            secs = {st["section_id"]}
            classes = set(await db.sections.distinct("class_name", {"_id": oid(st["section_id"])}))
        if not secs:
            return {"items": []}
        filt["$or"] = _audience_or(secs, classes)
    elif ctx.role == "teacher":
        secs, classes = await _teacher_scope(ctx)
        filt["$or"] = _audience_or(secs, classes)
    if not manager:
        # families/staff see live events, plus cancellations of events that had been announced
        filt["$and"] = [{"$or": [{"status": "published"}, {"status": "cancelled", "published_at": {"$ne": None}}]}]
    events = [_event_out(x, manager) for x in await db.events.find(filt).sort([("start_date", 1), ("start_time", 1)]).to_list(300)]
    items = events + await _exam_items(ctx, secs, s, e)
    items.sort(key=lambda i: (i["start_date"], i.get("start_time") or ""))
    return {"items": items}


@router.get("/calendar/upcoming")
async def upcoming(limit: int = Query(default=3, ge=1, le=10), ctx: Ctx = Depends(school_ctx)):
    today = now_utc().astimezone(IST).date()
    res = await calendar(today, today + timedelta(days=60), None, ctx)
    return {"items": [i for i in res["items"] if i["status"] != "cancelled"][:limit]}


async def seed_demo_events():
    """Idempotent fictional school-wide events (demo mode only) so calendars aren't empty."""
    today = now_utc().astimezone(IST).date()
    demo = [("Annual Sports Day", "sports", 6, 6, "08:30", "13:00", "Main ground"),
            ("Parent-Teacher Meeting", "ptm", 12, 12, "10:00", "13:00", "Classrooms"),
            ("Summer break", "holiday", 20, 24, None, None, ""),
            ("Science Exhibition", "cultural", 30, 30, "09:30", "12:30", "Auditorium")]
    async for sch in db.schools.find({"status": {"$ne": "suspended"}}, {"_id": 1}):
        sid = str(sch["_id"])
        if await db.events.find_one({"school_id": sid, "demo": True}):
            continue
        t = now_utc()
        await db.events.insert_many([{
            "school_id": sid, "title": title, "description": "", "category": cat,
            "start_date": (today + timedelta(days=a)).isoformat(), "end_date": (today + timedelta(days=b)).isoformat(),
            "start_time": st, "end_time": et, "location": loc, "audience": {"scope": "school", "class_names": [], "section_ids": []},
            "status": "published", "published_at": t, "cancel_reason": None, "created_by": None, "created_at": t,
            "updated_at": t, "status_history": [], "demo": True} for title, cat, a, b, st, et, loc in demo])
