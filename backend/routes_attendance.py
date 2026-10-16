"""Milestone 2 — Module 1: Student attendance (tenant-scoped, server-timestamped, auditable)."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_directory import _parent_links, teacher_section_ids

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
Status = Literal["present", "absent", "late"]


def today_ist() -> date:
    return datetime.now(IST).date()


def parse_day(d: Optional[str]) -> date:
    if not d:
        return today_ist()
    try:
        day = date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "Date must be YYYY-MM-DD")
    if day > today_ist():
        raise HTTPException(400, "Attendance cannot be recorded for a future date")
    return day


async def _section_access(ctx: Ctx, section_id: str) -> dict:
    sec = await db.sections.find_one({"_id": oid(section_id), "school_id": ctx.school_id})
    if not sec:
        raise HTTPException(404, "Section not found")
    if "academic.manage" in ctx.perms:
        return sec
    if "teacher.workspace" in ctx.perms and section_id in await teacher_section_ids(ctx):
        return sec
    raise HTTPException(403, "You are not assigned to this section")


class Mark(BaseModel):
    student_id: str
    status: Status


class SubmitIn(BaseModel):
    records: list[Mark] = Field(min_length=1, max_length=200)
    reason: Optional[str] = Field(default=None, max_length=300)


@router.get("/attendance/sections/{section_id}")
async def get_sheet(section_id: str, date_: Optional[str] = Query(None, alias="date"), ctx: Ctx = Depends(school_ctx)):
    sec = await _section_access(ctx, section_id)
    day = parse_day(date_)
    students = await db.students.find({"school_id": ctx.school_id, "section_id": section_id, "status": "active"}
                                      ).sort([("roll_no", 1), ("first_name", 1)]).to_list(200)
    sheet = await db.attendance.find_one({"school_id": ctx.school_id, "section_id": section_id, "date": day.isoformat()})
    marks = {r["student_id"]: r["status"] for r in (sheet or {}).get("records", [])}
    return {
        "section": {"id": section_id, "label": f"{sec['class_name']} - {sec['name']}"},
        "date": day.isoformat(), "submitted": bool(sheet),
        "submitted_at": out(sheet)["submitted_at"] if sheet else None,
        "corrections": len((sheet or {}).get("corrections", [])),
        "students": [{"id": str(s["_id"]), "name": f"{s['first_name']} {s['last_name']}".strip(),
                      "roll_no": s.get("roll_no"), "admission_no": s["admission_no"],
                      "status": marks.get(str(s["_id"]))} for s in students],
    }


@router.put("/attendance/sections/{section_id}")
async def submit(section_id: str, body: SubmitIn, date_: Optional[str] = Query(None, alias="date"),
                 ctx: Ctx = Depends(school_ctx)):
    await _section_access(ctx, section_id)
    day = parse_day(date_).isoformat()
    ids = [m.student_id for m in body.records]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "Each student can appear only once")
    valid = {str(s["_id"]) for s in await db.students.find(
        {"school_id": ctx.school_id, "section_id": section_id, "status": "active"}, {"_id": 1}).to_list(300)}
    if not set(ids) <= valid:
        raise HTTPException(400, "Records include students who are not in this section")
    if set(ids) != valid:
        raise HTTPException(400, "Mark every student in the section before submitting")
    t = now_utc()
    records = [m.model_dump() for m in body.records]
    key = {"school_id": ctx.school_id, "section_id": section_id, "date": day}
    existing = await db.attendance.find_one(key)
    if not existing:
        try:
            await db.attendance.insert_one({**key, "records": records, "submitted_by": ctx.user_id, "submitted_at": t,
                                            "updated_at": t, "corrections": []})
            await audit(ctx.user_id, "attendance.submit", "attendance", f"{section_id}:{day}", ctx.school_id,
                        {"absent": sum(r["status"] == "absent" for r in records)})
            return await get_sheet(section_id, day, ctx)
        except Exception as e:  # concurrent first submit -> treat as correction path below
            if "duplicate" not in str(e).lower():
                raise
            existing = await db.attendance.find_one(key)
    # Correction: only changed rows are logged, a reason is mandatory, teachers may correct only today's sheet.
    if "academic.manage" not in ctx.perms and day != today_ist().isoformat():
        raise HTTPException(403, "Only school administrators can correct past attendance")
    before = {r["student_id"]: r["status"] for r in existing["records"]}
    changes = [{"student_id": r["student_id"], "from": before.get(r["student_id"]), "to": r["status"]}
               for r in records if before.get(r["student_id"]) != r["status"]]
    if not changes:
        return await get_sheet(section_id, day, ctx)  # idempotent repeat
    if not (body.reason or "").strip():
        raise HTTPException(400, "A reason is required to correct submitted attendance")
    await db.attendance.update_one({"_id": existing["_id"]}, {"$set": {"records": records, "updated_at": t},
                                   "$push": {"corrections": {"by": ctx.user_id, "at": t, "reason": body.reason.strip(),
                                                             "changes": changes}}})
    await audit(ctx.user_id, "attendance.correct", "attendance", f"{section_id}:{day}", ctx.school_id,
                {"changes": len(changes)})
    return await get_sheet(section_id, day, ctx)


def _month_range(month: Optional[str]) -> tuple[str, str]:
    m = month or today_ist().strftime("%Y-%m")
    try:
        first = date.fromisoformat(f"{m}-01")
    except ValueError:
        raise HTTPException(400, "Month must be YYYY-MM")
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first.isoformat(), nxt.isoformat()


async def _summaries(filt: dict, student_ids: Optional[set] = None) -> dict:
    res: dict[str, dict] = {}
    async for sh in db.attendance.find(filt):
        for r in sh["records"]:
            if student_ids is not None and r["student_id"] not in student_ids:
                continue
            e = res.setdefault(r["student_id"], {"present": 0, "absent": 0, "late": 0, "days": 0, "history": []})
            e[r["status"]] += 1
            e["days"] += 1
            e["history"].append({"date": sh["date"], "status": r["status"]})
    return res


@router.get("/attendance/reports/monthly")
async def monthly(section_id: str, month: Optional[str] = None, ctx: Ctx = Depends(school_ctx)):
    sec = await _section_access(ctx, section_id)
    start, end = _month_range(month)
    sums = await _summaries({"school_id": ctx.school_id, "section_id": section_id, "date": {"$gte": start, "$lt": end}})
    students = await db.students.find({"school_id": ctx.school_id, "section_id": section_id, "status": "active"}
                                      ).sort("roll_no", 1).to_list(200)
    days = await db.attendance.count_documents({"school_id": ctx.school_id, "section_id": section_id,
                                                "date": {"$gte": start, "$lt": end}})
    rows = []
    for s in students:
        e = sums.get(str(s["_id"]), {"present": 0, "absent": 0, "late": 0, "days": 0})
        rows.append({"student_id": str(s["_id"]), "name": f"{s['first_name']} {s['last_name']}".strip(),
                     "roll_no": s.get("roll_no"), **{k: e[k] for k in ("present", "absent", "late", "days")},
                     "rate": round(100 * (e["present"] + e["late"]) / e["days"], 1) if e["days"] else None})
    return {"section": f"{sec['class_name']} - {sec['name']}", "month": start[:7], "working_days": days, "rows": rows}


@router.get("/attendance/summary/today")
async def today_summary(ctx: Ctx = Depends(need("dashboard.owner"))):
    day = today_ist().isoformat()
    total_sections = await db.sections.count_documents({"school_id": ctx.school_id})
    counts = {"present": 0, "absent": 0, "late": 0}
    marked = 0
    async for sh in db.attendance.find({"school_id": ctx.school_id, "date": day}):
        marked += 1
        for r in sh["records"]:
            counts[r["status"]] += 1
    seen = sum(counts.values())
    trend = []
    for i in range(6, -1, -1):
        d = (today_ist() - timedelta(days=i)).isoformat()
        p = a = 0
        async for sh in db.attendance.find({"school_id": ctx.school_id, "date": d}):
            for r in sh["records"]:
                p += r["status"] != "absent"
                a += r["status"] == "absent"
        trend.append({"date": d, "rate": round(100 * p / (p + a), 1) if p + a else None})
    return {"date": day, "sections_marked": marked, "sections_total": total_sections, **counts,
            "rate": round(100 * (counts["present"] + counts["late"]) / seen, 1) if seen else None, "trend": trend}


@router.get("/parent/children/{student_id}/attendance")
async def parent_attendance(student_id: str, month: Optional[str] = None, ctx: Ctx = Depends(need("parent.portal"))):
    if student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    start, end = _month_range(month)
    sums = await _summaries({"school_id": ctx.school_id, "date": {"$gte": start, "$lt": end},
                             "records.student_id": student_id}, {student_id})
    e = sums.get(student_id, {"present": 0, "absent": 0, "late": 0, "days": 0, "history": []})
    today = next((h["status"] for h in e["history"] if h["date"] == today_ist().isoformat()), None)
    return {"month": start[:7], "today": today, **{k: e[k] for k in ("present", "absent", "late", "days")},
            "history": sorted(e["history"], key=lambda h: h["date"], reverse=True)[:31]}
