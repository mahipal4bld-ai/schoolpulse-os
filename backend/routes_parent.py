"""Milestone 2 — Module 8: Parent academic overview (one glanceable summary per child)."""
from fastapi import APIRouter, Depends, HTTPException

from core import Ctx, db, need, oid
from routes_attendance import parent_attendance, today_ist
from routes_directory import _parent_links
from routes_exams import parent_exams
from routes_timetable import _grid

router = APIRouter()


@router.get("/parent/children/{student_id}/overview")
async def overview(student_id: str, ctx: Ctx = Depends(need("parent.portal"))):
    if student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id})
    today = today_ist()
    day = today.isoformat()
    att = await parent_attendance(student_id, None, ctx)
    grid = await _grid(ctx.school_id, {"section_id": st["section_id"], "day": today.isoweekday()})
    times = {p["no"]: p["start"] for p in grid["periods"]}
    periods = [{"period": s["period"], "start": times.get(s["period"]), "subject_name": s["subject_name"]} for s in grid["slots"]]
    hw = await db.homework.find({"school_id": ctx.school_id, "section_id": st["section_id"], "status": "published",
                                 "due_date": {"$gte": day}}).sort("due_date", 1).to_list(50)
    subs = {str(s["_id"]): s["name"] for s in await db.subjects.find({"school_id": ctx.school_id}).to_list(200)}
    pending = [h for h in hw if not any(c["student_id"] == student_id and c["status"] == "done" for c in h.get("completion", []))]
    diary = await db.diary.find({"school_id": ctx.school_id, "section_id": st["section_id"], "date": day,
                                 "deleted": {"$ne": True}}).sort("created_at", 1).to_list(20)
    exams = (await parent_exams(student_id, ctx))["items"]
    latest = exams[0] if exams else None
    return {
        "date": day,
        "attendance": {"today": att["today"], "month_rate": round(100 * (att["present"] + att["late"]) / att["days"], 1) if att["days"] else None,
                       "days": att["days"], "absent": att["absent"]},
        "timetable_today": periods,
        "homework": {"due_count": len(pending), "due_today": sum(1 for h in pending if h["due_date"] == day),
                     "next": [{"id": str(h["_id"]), "title": h["title"], "subject_name": subs.get(h["subject_id"], "—"),
                               "due_date": h["due_date"]} for h in pending[:3]]},
        "diary_today": [{"kind": d["kind"], "topic": d["topic"], "subject_name": subs.get(d.get("subject_id") or "", None)} for d in diary],
        "latest_result": {k: latest[k] for k in ("id", "name", "percentage", "grade", "result", "rank", "class_size")} if latest else None,
    }
