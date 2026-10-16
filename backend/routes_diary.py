"""Milestone 2 — Module 4: Digital class diary (daily lesson summaries + class notes, parent visible)."""
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_attendance import _section_access, parse_day, today_ist
from routes_directory import _parent_links
from routes_homework import _can_assign

router = APIRouter()
TEACHER_BACKDATE_DAYS = 7


def _writer(ctx: Ctx):
    if not ({"academic.manage", "teacher.workspace"} & ctx.perms):
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")


async def _authorise(ctx: Ctx, section_id: str, subject_id: Optional[str]):
    if subject_id:
        await _can_assign(ctx, section_id, subject_id)
    else:
        await _section_access(ctx, section_id)


def _check_day(ctx: Ctx, day: date):
    if "academic.manage" not in ctx.perms and day < today_ist() - timedelta(days=TEACHER_BACKDATE_DAYS):
        raise HTTPException(400, f"Teachers can write diary entries for the last {TEACHER_BACKDATE_DAYS} days only")


async def _out(e: dict) -> dict:
    o = out(e)
    sub = await db.subjects.find_one({"_id": oid(e["subject_id"])}, {"name": 1}) if e.get("subject_id") else None
    o["subject_name"] = sub["name"] if sub else None
    u = await db.users.find_one({"_id": oid(e["created_by"])}, {"name": 1})
    o["author_name"] = u["name"] if u else "—"
    return o


class DiaryIn(BaseModel):
    section_id: str
    kind: Literal["lesson", "note"] = "lesson"
    subject_id: Optional[str] = None
    date: Optional[str] = None
    topic: str = Field(min_length=2, max_length=150)
    summary: str = Field(default="", max_length=2000)


class DiaryPatch(BaseModel):
    topic: Optional[str] = Field(default=None, min_length=2, max_length=150)
    summary: Optional[str] = Field(default=None, max_length=2000)


@router.get("/diary")
async def list_diary(section_id: str, date_: Optional[str] = Query(None, alias="date"), ctx: Ctx = Depends(school_ctx)):
    _writer(ctx)
    sec = await _section_access(ctx, section_id)
    day = parse_day(date_).isoformat()
    items = await db.diary.find({"school_id": ctx.school_id, "section_id": section_id, "date": day,
                                 "deleted": {"$ne": True}}).sort("created_at", 1).to_list(50)
    return {"section": f"{sec['class_name']} - {sec['name']}", "date": day, "items": [await _out(x) for x in items]}


@router.post("/diary", status_code=201)
async def create(body: DiaryIn, ctx: Ctx = Depends(school_ctx)):
    _writer(ctx)
    if body.kind == "lesson" and not body.subject_id:
        raise HTTPException(400, "Choose the subject for a lesson entry")
    await _authorise(ctx, body.section_id, body.subject_id)
    day = parse_day(body.date)
    _check_day(ctx, day)
    t = now_utc()
    doc = {"school_id": ctx.school_id, "section_id": body.section_id, "kind": body.kind, "subject_id": body.subject_id,
           "date": day.isoformat(), "topic": body.topic.strip(), "summary": body.summary.strip(),
           "created_by": ctx.user_id, "created_at": t, "updated_at": t, "deleted": False}
    r = await db.diary.insert_one(doc)
    await audit(ctx.user_id, "diary.create", "diary", str(r.inserted_id), ctx.school_id, {"kind": body.kind})
    return await _out({**doc, "_id": r.inserted_id})


async def _own(ctx: Ctx, rid: str) -> dict:
    _writer(ctx)
    e = await db.diary.find_one({"_id": oid(rid), "school_id": ctx.school_id, "deleted": {"$ne": True}})
    if not e:
        raise HTTPException(404, "Diary entry not found")
    if "academic.manage" not in ctx.perms and e["created_by"] != ctx.user_id:
        raise HTTPException(403, "You can edit only your own diary entries")
    _check_day(ctx, date.fromisoformat(e["date"]))
    return e


@router.patch("/diary/{rid}")
async def patch(rid: str, body: DiaryPatch, ctx: Ctx = Depends(school_ctx)):
    e = await _own(ctx, rid)
    data = {k: v.strip() for k, v in body.model_dump(exclude_none=True).items()}
    if not data:
        raise HTTPException(400, "No changes supplied")
    await db.diary.update_one({"_id": e["_id"]}, {"$set": {**data, "updated_at": now_utc()}})
    await audit(ctx.user_id, "diary.update", "diary", rid, ctx.school_id, {"fields": list(data)})
    return await _out(await db.diary.find_one({"_id": e["_id"]}))


@router.delete("/diary/{rid}")
async def delete(rid: str, ctx: Ctx = Depends(school_ctx)):
    e = await _own(ctx, rid)
    await db.diary.update_one({"_id": e["_id"]}, {"$set": {"deleted": True, "updated_at": now_utc()}})
    await audit(ctx.user_id, "diary.delete", "diary", rid, ctx.school_id)
    return {"ok": True}


@router.get("/diary/summary/today")
async def summary(ctx: Ctx = Depends(need("dashboard.owner"))):
    day = today_ist().isoformat()
    secs = await db.diary.distinct("section_id", {"school_id": ctx.school_id, "date": day, "deleted": {"$ne": True}})
    return {"date": day, "sections_with_diary": len(secs),
            "sections_total": await db.sections.count_documents({"school_id": ctx.school_id}),
            "entries": await db.diary.count_documents({"school_id": ctx.school_id, "date": day, "deleted": {"$ne": True}})}


@router.get("/parent/children/{student_id}/diary")
async def parent_diary(student_id: str, date_: Optional[str] = Query(None, alias="date"),
                       ctx: Ctx = Depends(need("parent.portal"))):
    if student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id})
    day = parse_day(date_).isoformat()
    items = await db.diary.find({"school_id": ctx.school_id, "section_id": st["section_id"], "date": day,
                                 "deleted": {"$ne": True}}).sort("created_at", 1).to_list(50)
    res = []
    for x in items:
        o = await _out(x)
        o.pop("created_by", None)
        res.append(o)
    return {"date": day, "items": res}
