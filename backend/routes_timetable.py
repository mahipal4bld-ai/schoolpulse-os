"""Milestone 2 — Module 5: Timetable (bell schedule, class + teacher timetables, conflict detection)."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from core import Ctx, audit, db, need, now_utc, oid, school_ctx
from routes_attendance import _section_access, today_ist
from routes_directory import _parent_links

router = APIRouter()
DAYS = [1, 2, 3, 4, 5, 6]  # Mon..Sat
DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
DEFAULT_PERIODS = [{"no": i + 1, "start": s, "end": e} for i, (s, e) in enumerate(
    [("08:00", "08:40"), ("08:40", "09:20"), ("09:20", "10:00"), ("10:20", "11:00"),
     ("11:00", "11:40"), ("11:40", "12:20"), ("13:00", "13:40"), ("13:40", "14:20")])]
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


async def get_periods(school_id: str) -> list[dict]:
    s = await db.timetable_settings.find_one({"school_id": school_id})
    return s["periods"] if s else DEFAULT_PERIODS


class Period(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v):
        if not HHMM.match(v):
            raise ValueError("Times must be HH:MM (24-hour)")
        return v


class SettingsIn(BaseModel):
    periods: list[Period] = Field(min_length=1, max_length=12)


@router.get("/timetable/settings")
async def settings(ctx: Ctx = Depends(school_ctx)):
    return {"periods": await get_periods(ctx.school_id), "days": [{"day": d, "name": DAY_NAMES[d]} for d in DAYS]}


@router.put("/timetable/settings")
async def save_settings(body: SettingsIn, ctx: Ctx = Depends(need("academic.manage"))):
    prev_end = "00:00"
    for p in body.periods:
        if p.end <= p.start:
            raise HTTPException(400, "Each period must end after it starts")
        if p.start < prev_end:
            raise HTTPException(400, "Periods must be in order and must not overlap")
        prev_end = p.end
    periods = [{"no": i + 1, **p.model_dump()} for i, p in enumerate(body.periods)]
    await db.timetable_settings.update_one({"school_id": ctx.school_id},
                                           {"$set": {"periods": periods, "updated_at": now_utc(), "updated_by": ctx.user_id}},
                                           upsert=True)
    # slots beyond the new period count are removed
    removed = await db.timetable_slots.delete_many({"school_id": ctx.school_id, "period": {"$gt": len(periods)}})
    await audit(ctx.user_id, "timetable.settings", "timetable", None, ctx.school_id,
                {"periods": len(periods), "slots_removed": removed.deleted_count})
    return await settings(ctx)


async def _names(school_id: str) -> tuple[dict, dict, dict]:
    subs = {str(s["_id"]): s["name"] for s in await db.subjects.find({"school_id": school_id}).to_list(200)}
    tchs = {str(t["_id"]): t["name"] for t in await db.teachers.find({"school_id": school_id}).to_list(500)}
    secs = {str(s["_id"]): f"{s['class_name']} - {s['name']}" for s in await db.sections.find({"school_id": school_id}).to_list(500)}
    return subs, tchs, secs


def _slot_out(s: dict, subs: dict, tchs: dict, secs: dict) -> dict:
    return {"day": s["day"], "period": s["period"], "section_id": s["section_id"], "section_label": secs.get(s["section_id"], "—"),
            "subject_id": s["subject_id"], "subject_name": subs.get(s["subject_id"], "—"),
            "teacher_id": s.get("teacher_id"), "teacher_name": tchs.get(s.get("teacher_id") or "", None),
            "room": s.get("room") or ""}


async def _grid(ctx_school: str, filt: dict) -> dict:
    subs, tchs, secs = await _names(ctx_school)
    slots = await db.timetable_slots.find({"school_id": ctx_school, **filt}).sort([("day", 1), ("period", 1)]).to_list(500)
    return {"periods": await get_periods(ctx_school), "days": [{"day": d, "name": DAY_NAMES[d]} for d in DAYS],
            "slots": [_slot_out(s, subs, tchs, secs) for s in slots], "today": today_ist().isoweekday()}


@router.get("/timetable/sections/{section_id}")
async def section_timetable(section_id: str, ctx: Ctx = Depends(school_ctx)):
    sec = await _section_access(ctx, section_id)
    g = await _grid(ctx.school_id, {"section_id": section_id})
    g["section"] = f"{sec['class_name']} - {sec['name']}"
    if "academic.manage" in ctx.perms:  # teacher choices for the editor
        subs, tchs, _ = await _names(ctx.school_id)
        asg = await db.teacher_assignments.find({"school_id": ctx.school_id, "section_id": section_id}).to_list(100)
        opts: dict[str, dict] = {}
        for a in asg:
            o = opts.setdefault(a["teacher_id"], {"teacher_id": a["teacher_id"], "name": tchs.get(a["teacher_id"], "—"),
                                                  "subject_ids": [], "is_class_teacher": False})
            if a.get("subject_id"):
                o["subject_ids"].append(a["subject_id"])
            o["is_class_teacher"] = o["is_class_teacher"] or a.get("is_class_teacher", False)
        g["teacher_options"] = list(opts.values())
        g["subjects"] = [{"id": k, "name": v} for k, v in subs.items()]
    return g


class SlotIn(BaseModel):
    day: int = Field(ge=1, le=6)
    period: int = Field(ge=1, le=12)
    subject_id: str
    teacher_id: Optional[str] = None
    room: str = Field(default="", max_length=20)


@router.put("/timetable/sections/{section_id}/slots")
async def set_slot(section_id: str, body: SlotIn, ctx: Ctx = Depends(need("academic.manage"))):
    await _section_access(ctx, section_id)
    if body.period > len(await get_periods(ctx.school_id)):
        raise HTTPException(400, "This period does not exist in the bell schedule")
    if not await db.subjects.find_one({"_id": oid(body.subject_id), "school_id": ctx.school_id}):
        raise HTTPException(404, "Subject not found")
    if body.teacher_id:
        if not await db.teachers.find_one({"_id": oid(body.teacher_id), "school_id": ctx.school_id, "status": "active"}):
            raise HTTPException(404, "Teacher not found")
        asg = await db.teacher_assignments.find({"school_id": ctx.school_id, "teacher_id": body.teacher_id,
                                                 "section_id": section_id}).to_list(50)
        if not any(a.get("subject_id") == body.subject_id or a.get("is_class_teacher") for a in asg):
            raise HTTPException(400, "This teacher is not assigned to teach this subject in this section")
        clash = await db.timetable_slots.find_one({"school_id": ctx.school_id, "teacher_id": body.teacher_id,
                                                   "day": body.day, "period": body.period,
                                                   "section_id": {"$ne": section_id}})
        if clash:
            _, tchs, secs = await _names(ctx.school_id)
            raise HTTPException(409, f"Conflict: {tchs.get(body.teacher_id, 'Teacher')} already teaches "
                                     f"{secs.get(clash['section_id'], 'another section')} in period {body.period} on "
                                     f"{DAY_NAMES[body.day]}")
    if body.room:
        room_clash = await db.timetable_slots.find_one({"school_id": ctx.school_id, "room": body.room, "day": body.day,
                                                        "period": body.period, "section_id": {"$ne": section_id}})
        if room_clash:
            raise HTTPException(409, f"Conflict: room {body.room} is already in use in period {body.period} on {DAY_NAMES[body.day]}")
    key = {"school_id": ctx.school_id, "section_id": section_id, "day": body.day, "period": body.period}
    await db.timetable_slots.update_one(key, {"$set": {"subject_id": body.subject_id, "teacher_id": body.teacher_id,
                                                       "room": body.room.strip(), "updated_at": now_utc(),
                                                       "updated_by": ctx.user_id}}, upsert=True)
    await audit(ctx.user_id, "timetable.set", "timetable", f"{section_id}:{body.day}:{body.period}", ctx.school_id)
    return await section_timetable(section_id, ctx)


@router.delete("/timetable/sections/{section_id}/slots")
async def clear_slot(section_id: str, day: int = Query(ge=1, le=6), period: int = Query(ge=1, le=12),
                     ctx: Ctx = Depends(need("academic.manage"))):
    await _section_access(ctx, section_id)
    await db.timetable_slots.delete_one({"school_id": ctx.school_id, "section_id": section_id, "day": day, "period": period})
    await audit(ctx.user_id, "timetable.clear", "timetable", f"{section_id}:{day}:{period}", ctx.school_id)
    return await section_timetable(section_id, ctx)


@router.get("/timetable/conflicts")
async def conflicts(ctx: Ctx = Depends(need("academic.manage"))):
    """Double-bookings (e.g. from data imported before checks existed)."""
    pipe = [{"$match": {"school_id": ctx.school_id, "teacher_id": {"$ne": None}}},
            {"$group": {"_id": {"t": "$teacher_id", "d": "$day", "p": "$period"}, "n": {"$sum": 1},
                        "sections": {"$push": "$section_id"}}}, {"$match": {"n": {"$gt": 1}}}]
    _, tchs, secs = await _names(ctx.school_id)
    return {"items": [{"teacher_name": tchs.get(r["_id"]["t"], "—"), "day": DAY_NAMES[r["_id"]["d"]], "period": r["_id"]["p"],
                       "sections": [secs.get(s, "—") for s in r["sections"]]} async for r in db.timetable_slots.aggregate(pipe)]}


@router.get("/timetable/teacher/me")
async def my_timetable(ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id})
    if not t:
        return {**await _grid(ctx.school_id, {"teacher_id": "__none__"}), "teacher": None}
    return {**await _grid(ctx.school_id, {"teacher_id": str(t["_id"])}), "teacher": t["name"]}


@router.get("/timetable/teachers/{teacher_id}")
async def teacher_timetable(teacher_id: str, ctx: Ctx = Depends(need("academic.manage"))):
    t = await db.teachers.find_one({"_id": oid(teacher_id), "school_id": ctx.school_id})
    if not t:
        raise HTTPException(404, "Teacher not found")
    return {**await _grid(ctx.school_id, {"teacher_id": teacher_id}), "teacher": t["name"]}


@router.get("/parent/children/{student_id}/timetable")
async def parent_timetable(student_id: str, ctx: Ctx = Depends(need("parent.portal"))):
    if student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id})
    g = await _grid(ctx.school_id, {"section_id": st["section_id"]})
    for s in g["slots"]:
        s.pop("teacher_id", None)
    return g


async def seed_demo_timetable():
    """Demo only: fill each school's timetable from teacher assignments without teacher clashes (idempotent)."""
    async for school in db.schools.find({}, {"_id": 1}):
        sid = str(school["_id"])
        if await db.timetable_slots.count_documents({"school_id": sid}):
            continue
        busy: set = set()
        secs = await db.sections.find({"school_id": sid}).to_list(200)
        for sec in secs:
            sec_id = str(sec["_id"])
            asg = [a for a in await db.teacher_assignments.find({"school_id": sid, "section_id": sec_id}).to_list(50)
                   if a.get("subject_id")]
            if not asg:
                continue
            i = 0
            for day in DAYS:
                for p in range(1, 7):
                    for k in range(len(asg)):
                        a = asg[(i + k) % len(asg)]
                        if (a["teacher_id"], day, p) not in busy:
                            busy.add((a["teacher_id"], day, p))
                            await db.timetable_slots.insert_one({"school_id": sid, "section_id": sec_id, "day": day,
                                                                 "period": p, "subject_id": a["subject_id"],
                                                                 "teacher_id": a["teacher_id"], "room": "",
                                                                 "updated_at": now_utc(), "updated_by": None})
                            break
                    i += 1
