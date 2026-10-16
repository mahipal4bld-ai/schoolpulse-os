"""Milestone 2 — Module 7: Teacher workspace (one call consolidating today's classes and pending work)."""
from fastapi import APIRouter, Depends

from core import Ctx, db, need
from routes_attendance import today_ist
from routes_timetable import _grid

router = APIRouter()


@router.get("/teacher/workspace")
async def workspace(ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id})
    today = today_ist()
    day = today.isoformat()
    if not t:
        return {"date": day, "schedule": [], "todo": [], "counts": {}}
    tid = str(t["_id"])
    grid = await _grid(ctx.school_id, {"teacher_id": tid, "day": today.isoweekday()})
    times = {p["no"]: p for p in grid["periods"]}
    schedule = [{**s, "start": times.get(s["period"], {}).get("start"), "end": times.get(s["period"], {}).get("end")}
                for s in grid["slots"]]
    asg = await db.teacher_assignments.find({"school_id": ctx.school_id, "teacher_id": tid}).to_list(200)
    my_sections = sorted({a["section_id"] for a in asg})
    class_sections = sorted({a["section_id"] for a in asg if a.get("is_class_teacher")})
    labels = {str(s["_id"]): f"{s['class_name']} - {s['name']}" for s in await db.sections.find(
        {"_id": {"$in": [__import__("bson").ObjectId(x) for x in my_sections]}}).to_list(200)}
    todo = []
    for sec in class_sections:
        if not await db.attendance.find_one({"school_id": ctx.school_id, "section_id": sec, "date": day}, {"_id": 1}):
            todo.append({"kind": "attendance", "section_id": sec, "title": f"Mark attendance · {labels.get(sec, '')}"})
    diary_done = set(await db.diary.distinct("section_id", {"school_id": ctx.school_id, "date": day, "created_by": ctx.user_id,
                                                            "deleted": {"$ne": True}}))
    taught_today = sorted({s["section_id"] for s in schedule})
    for sec in taught_today:
        if sec not in diary_done:
            todo.append({"kind": "diary", "section_id": sec, "title": f"Write class diary · {labels.get(sec, '')}"})
    drafts = await db.homework.count_documents({"school_id": ctx.school_id, "created_by": ctx.user_id, "status": "draft"})
    if drafts:
        todo.append({"kind": "homework_drafts", "title": f"{drafts} homework draft(s) not published"})
    due_today = await db.homework.count_documents({"school_id": ctx.school_id, "created_by": ctx.user_id,
                                                   "status": "published", "due_date": day})
    # exam sheets this teacher can enter that are still empty
    teach = {(a["section_id"], a.get("subject_id")) for a in asg}
    pending_sheets = 0
    async for e in db.exams.find({"school_id": ctx.school_id, "status": "marks_open", "section_ids": {"$in": my_sections}}):
        done = {(m["section_id"], m["subject_id"]) async for m in db.exam_marks.find({"exam_id": str(e["_id"])})}
        for sec in e["section_ids"]:
            for s in e["subjects"]:
                ok = (sec, s["subject_id"]) in teach or sec in class_sections
                if ok and (sec, s["subject_id"]) not in done:
                    pending_sheets += 1
    if pending_sheets:
        todo.append({"kind": "marks", "title": f"{pending_sheets} exam marks sheet(s) to enter"})
    pending_leave = await db.leave_requests.count_documents({"school_id": ctx.school_id, "teacher_id": tid, "status": "pending"})
    return {"date": day, "weekday": today.isoweekday(), "schedule": schedule, "todo": todo,
            "counts": {"periods_today": len(schedule), "homework_due_today": due_today, "homework_drafts": drafts,
                       "marks_sheets_pending": pending_sheets, "pending_leave": pending_leave,
                       "diary_written_today": len(diary_done)}}
