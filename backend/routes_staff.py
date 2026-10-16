"""Milestone 2 — Module 2: Teacher & staff attendance + leave with principal approval."""
from datetime import date, datetime, time, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import Ctx, audit, db, need, now_utc, oid, out
from routes_attendance import IST, parse_day, today_ist

router = APIRouter()
StaffStatus = Literal["present", "absent", "late", "half_day", "on_leave"]
LeaveType = Literal["casual", "sick", "earned", "other"]
LATE_AFTER = time(8, 30)  # IST self check-in cutoff
MAX_LEAVE_DAYS = 30


async def _my_teacher(ctx: Ctx) -> dict:
    t = await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id, "status": "active"})
    if not t:
        raise HTTPException(404, "No staff profile is linked to your account")
    return t


async def _leave_on(school_id: str, day: str) -> dict[str, dict]:
    """teacher_id -> approved leave covering the day."""
    res = {}
    async for lv in db.leave_requests.find({"school_id": school_id, "status": "approved",
                                            "from_date": {"$lte": day}, "to_date": {"$gte": day}}):
        res[lv["teacher_id"]] = lv
    return res


# ---------------------------------------------------------------- self check-in (teacher)
@router.get("/staff/me/today")
async def my_today(ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    day = today_ist().isoformat()
    rec = await db.staff_attendance.find_one({"school_id": ctx.school_id, "teacher_id": str(t["_id"]), "date": day})
    leave = (await _leave_on(ctx.school_id, day)).get(str(t["_id"]))
    pending = await db.leave_requests.count_documents({"school_id": ctx.school_id, "teacher_id": str(t["_id"]),
                                                       "status": "pending"})
    return {"date": day, "status": rec["status"] if rec else ("on_leave" if leave else None),
            "check_in_at": out(rec).get("check_in_at") if rec else None, "on_leave": bool(leave),
            "pending_leave": pending}


@router.post("/staff/me/check-in")
async def check_in(ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    tid, day = str(t["_id"]), today_ist().isoformat()
    if str(t["_id"]) in await _leave_on(ctx.school_id, day):
        raise HTTPException(400, "You are on approved leave today")
    key = {"school_id": ctx.school_id, "teacher_id": tid, "date": day}
    if await db.staff_attendance.find_one(key):
        return await my_today(ctx)  # idempotent
    tnow = now_utc()
    status = "late" if datetime.now(IST).time() > LATE_AFTER else "present"
    try:
        await db.staff_attendance.insert_one({**key, "status": status, "check_in_at": tnow, "source": "self",
                                              "marked_by": ctx.user_id, "updated_at": tnow, "corrections": []})
    except Exception as e:  # concurrent double tap
        if "duplicate" not in str(e).lower():
            raise
    await audit(ctx.user_id, "staff_attendance.check_in", "staff_attendance", f"{tid}:{day}", ctx.school_id,
                {"status": status})
    return await my_today(ctx)


# ---------------------------------------------------------------- register (admin / principal)
class StaffMark(BaseModel):
    teacher_id: str
    status: StaffStatus


class RegisterIn(BaseModel):
    records: list[StaffMark] = Field(min_length=1, max_length=300)
    reason: Optional[str] = Field(default=None, max_length=300)


@router.get("/staff/attendance")
async def register(date_: Optional[str] = Query(None, alias="date"), ctx: Ctx = Depends(need("staff.manage"))):
    day = parse_day(date_).isoformat()
    staff = await db.teachers.find({"school_id": ctx.school_id, "status": "active"}).sort("name", 1).to_list(300)
    recs = {r["teacher_id"]: r async for r in db.staff_attendance.find({"school_id": ctx.school_id, "date": day})}
    leaves = await _leave_on(ctx.school_id, day)
    rows = []
    for s in staff:
        sid = str(s["_id"])
        r = recs.get(sid)
        rows.append({"teacher_id": sid, "name": s["name"], "designation": s.get("designation", ""),
                     "employee_code": s.get("employee_code", ""),
                     "status": r["status"] if r else ("on_leave" if sid in leaves else None),
                     "source": r.get("source") if r else ("leave" if sid in leaves else None),
                     "check_in_at": out(r).get("check_in_at") if r else None,
                     "leave_type": leaves[sid]["type"] if sid in leaves else None})
    counts = {k: sum(1 for x in rows if x["status"] == k) for k in ("present", "late", "absent", "half_day", "on_leave")}
    return {"date": day, "rows": rows, "counts": counts, "unmarked": sum(1 for x in rows if x["status"] is None)}


@router.put("/staff/attendance")
async def save_register(body: RegisterIn, date_: Optional[str] = Query(None, alias="date"),
                        ctx: Ctx = Depends(need("staff.manage"))):
    day = parse_day(date_).isoformat()
    ids = [m.teacher_id for m in body.records]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "Each staff member can appear only once")
    valid = {str(s["_id"]) for s in await db.teachers.find({"school_id": ctx.school_id, "status": "active"},
                                                           {"_id": 1}).to_list(300)}
    if not set(ids) <= valid:
        raise HTTPException(400, "Records include staff who are not in this school")
    existing = {r["teacher_id"]: r async for r in db.staff_attendance.find(
        {"school_id": ctx.school_id, "date": day, "teacher_id": {"$in": ids}})}
    changes = [m for m in body.records if m.teacher_id in existing and existing[m.teacher_id]["status"] != m.status]
    if changes and not (body.reason or "").strip():
        raise HTTPException(400, "A reason is required to change attendance that is already recorded")
    t = now_utc()
    for m in body.records:
        key = {"school_id": ctx.school_id, "teacher_id": m.teacher_id, "date": day}
        prev = existing.get(m.teacher_id)
        if not prev:
            await db.staff_attendance.update_one(key, {"$setOnInsert": {
                "status": m.status, "check_in_at": None, "source": "admin", "marked_by": ctx.user_id,
                "updated_at": t, "corrections": []}}, upsert=True)
        elif prev["status"] != m.status:
            await db.staff_attendance.update_one({"_id": prev["_id"]}, {
                "$set": {"status": m.status, "updated_at": t},
                "$push": {"corrections": {"by": ctx.user_id, "at": t, "from": prev["status"], "to": m.status,
                                          "reason": body.reason.strip()}}})
    await audit(ctx.user_id, "staff_attendance.save", "staff_attendance", day, ctx.school_id,
                {"records": len(body.records), "corrections": len(changes)})
    return await register(day, ctx)


@router.get("/staff/summary/today")
async def staff_today(ctx: Ctx = Depends(need("dashboard.owner"))):
    reg = await register(None, Ctx(**{**ctx.model_dump(), "perms": ctx.perms | {"staff.manage"}}))
    pending = await db.leave_requests.count_documents({"school_id": ctx.school_id, "status": "pending"})
    return {"date": reg["date"], "total": len(reg["rows"]), **reg["counts"], "unmarked": reg["unmarked"],
            "pending_leave": pending}


# ---------------------------------------------------------------- leave
class LeaveIn(BaseModel):
    type: LeaveType
    from_date: date
    to_date: date
    reason: str = Field(min_length=3, max_length=500)


class Decision(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=300)


async def _leave_out(lv: dict) -> dict:
    o = out(lv)
    t = await db.teachers.find_one({"_id": oid(lv["teacher_id"])}, {"name": 1, "designation": 1})
    o["teacher_name"] = t["name"] if t else "—"
    o["designation"] = (t or {}).get("designation", "")
    return o


@router.post("/staff/leave", status_code=201)
async def apply_leave(body: LeaveIn, ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    if body.to_date < body.from_date:
        raise HTTPException(400, "End date must be on or after the start date")
    if body.from_date < today_ist() - timedelta(days=7):
        raise HTTPException(400, "Leave can be applied at most 7 days in the past")
    days = (body.to_date - body.from_date).days + 1
    if days > MAX_LEAVE_DAYS:
        raise HTTPException(400, f"A single request can cover at most {MAX_LEAVE_DAYS} days")
    f, to = body.from_date.isoformat(), body.to_date.isoformat()
    if await db.leave_requests.find_one({"school_id": ctx.school_id, "teacher_id": str(t["_id"]),
                                         "status": {"$in": ["pending", "approved"]},
                                         "from_date": {"$lte": to}, "to_date": {"$gte": f}}):
        raise HTTPException(409, "You already have a leave request covering these dates")
    doc = {"school_id": ctx.school_id, "teacher_id": str(t["_id"]), "user_id": ctx.user_id, "type": body.type,
           "from_date": f, "to_date": to, "days": days, "reason": body.reason.strip(), "status": "pending",
           "decided_by": None, "decided_at": None, "decision_note": None, "created_at": now_utc()}
    r = await db.leave_requests.insert_one(doc)
    await audit(ctx.user_id, "leave.apply", "leave_request", str(r.inserted_id), ctx.school_id, {"days": days})
    return await _leave_out({**doc, "_id": r.inserted_id})


@router.get("/staff/leave/mine")
async def my_leave(ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    items = await db.leave_requests.find({"school_id": ctx.school_id, "teacher_id": str(t["_id"])}
                                         ).sort("created_at", -1).to_list(100)
    year = str(today_ist().year)
    used = sum(x["days"] for x in items if x["status"] == "approved" and x["from_date"].startswith(year))
    return {"items": [await _leave_out(x) for x in items], "approved_days_this_year": used}


@router.post("/staff/leave/{rid}/cancel")
async def cancel_leave(rid: str, ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await _my_teacher(ctx)
    lv = await db.leave_requests.find_one_and_update(
        {"_id": oid(rid), "school_id": ctx.school_id, "teacher_id": str(t["_id"]), "status": "pending"},
        {"$set": {"status": "cancelled", "decided_at": now_utc()}}, return_document=True)
    if not lv:
        raise HTTPException(404, "Pending leave request not found")
    await audit(ctx.user_id, "leave.cancel", "leave_request", rid, ctx.school_id)
    return await _leave_out(lv)


@router.get("/staff/leave")
async def list_leave(status: Optional[Literal["pending", "approved", "rejected", "cancelled"]] = None,
                     ctx: Ctx = Depends(need("staff.manage"))):
    filt = {"school_id": ctx.school_id, **({"status": status} if status else {})}
    items = await db.leave_requests.find(filt).sort([("status", -1), ("from_date", 1)]).to_list(200)
    return {"items": [await _leave_out(x) for x in items],
            "pending": await db.leave_requests.count_documents({"school_id": ctx.school_id, "status": "pending"})}


@router.post("/staff/leave/{rid}/decision")
async def decide_leave(rid: str, body: Decision, ctx: Ctx = Depends(need("leave.approve"))):
    if not body.approve and not (body.note or "").strip():
        raise HTTPException(400, "Add a note explaining why the leave is rejected")
    lv = await db.leave_requests.find_one({"_id": oid(rid), "school_id": ctx.school_id})
    if not lv:
        raise HTTPException(404, "Leave request not found")
    if lv["user_id"] == ctx.user_id:
        raise HTTPException(403, "You cannot approve your own leave")
    t = now_utc()
    upd = await db.leave_requests.find_one_and_update(
        {"_id": lv["_id"], "status": "pending"},
        {"$set": {"status": "approved" if body.approve else "rejected", "decided_by": ctx.user_id, "decided_at": t,
                  "decision_note": (body.note or "").strip() or None}}, return_document=True)
    if not upd:
        raise HTTPException(409, f"This request is already {lv['status']}")
    if body.approve:  # reflect leave in the staff register (existing self check-ins are kept)
        d = date.fromisoformat(lv["from_date"])
        while d <= date.fromisoformat(lv["to_date"]):
            await db.staff_attendance.update_one(
                {"school_id": ctx.school_id, "teacher_id": lv["teacher_id"], "date": d.isoformat()},
                {"$setOnInsert": {"status": "on_leave", "check_in_at": None, "source": "leave", "marked_by": ctx.user_id,
                                  "updated_at": t, "corrections": [], "leave_id": rid}}, upsert=True)
            d += timedelta(days=1)
    await audit(ctx.user_id, "leave.approve" if body.approve else "leave.reject", "leave_request", rid, ctx.school_id,
                {"days": lv["days"]})
    return await _leave_out(upd)
