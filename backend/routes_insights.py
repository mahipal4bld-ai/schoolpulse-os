"""Milestone 2 — Module 9: Owner academic intelligence (all figures derived live from records, no estimates)."""
from datetime import timedelta

from fastapi import APIRouter, Depends

from core import Ctx, db, need
from routes_attendance import today_ist
from routes_exams import compute_results

router = APIRouter()


@router.get("/dashboard/academic")
async def academic_intelligence(days: int = 14, ctx: Ctx = Depends(need("dashboard.owner"))):
    sid = ctx.school_id
    days = max(7, min(days, 60))
    today = today_ist()
    start = (today - timedelta(days=days - 1)).isoformat()
    sections = await db.sections.find({"school_id": sid}).sort([("class_name", 1), ("name", 1)]).to_list(300)
    label = {str(s["_id"]): f"{s['class_name']} - {s['name']}" for s in sections}

    # attendance: daily rate trend + per-section rate over the window
    by_day: dict[str, list[int]] = {}
    by_sec: dict[str, list[int]] = {}
    chronic: dict[str, int] = {}
    async for sh in db.attendance.find({"school_id": sid, "date": {"$gte": start}}):
        for r in sh["records"]:
            ok = r["status"] != "absent"
            for bucket, k in ((by_day, sh["date"]), (by_sec, sh["section_id"])):
                b = bucket.setdefault(k, [0, 0])
                b[0] += ok
                b[1] += 1
            if not ok:
                chronic[r["student_id"]] = chronic.get(r["student_id"], 0) + 1
    trend = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        p, n = by_day.get(d, [0, 0])
        trend.append({"date": d, "rate": round(100 * p / n, 1) if n else None})
    sec_rates = sorted([{"section_id": k, "label": label.get(k, "—"), "rate": round(100 * v[0] / v[1], 1)}
                        for k, v in by_sec.items() if v[1]], key=lambda x: x["rate"])
    absentees = sorted(((k, v) for k, v in chronic.items() if v >= 3), key=lambda x: -x[1])[:5]
    names = {str(s["_id"]): f"{s['first_name']} {s['last_name']}" for s in await db.students.find(
        {"_id": {"$in": [__import__("bson").ObjectId(k) for k, _ in absentees]}}).to_list(10)}

    # homework + diary coverage per section over the window
    hw = {}
    async for h in db.homework.find({"school_id": sid, "status": "published", "assigned_date": {"$gte": start}}, {"section_id": 1}):
        hw[h["section_id"]] = hw.get(h["section_id"], 0) + 1
    diary_days = {}
    async for r in db.diary.aggregate([{"$match": {"school_id": sid, "date": {"$gte": start}, "deleted": {"$ne": True}}},
                                       {"$group": {"_id": {"s": "$section_id", "d": "$date"}}}]):
        diary_days[r["_id"]["s"]] = diary_days.get(r["_id"]["s"], 0) + 1
    working = sum(1 for t in trend if t["rate"] is not None) or None
    coverage = [{"section_id": k, "label": v, "homework": hw.get(k, 0), "diary_days": diary_days.get(k, 0)} for k, v in label.items()]

    # exams: latest published exam averages per section
    exam = await db.exams.find_one({"school_id": sid, "status": "published"}, sort=[("published_at", -1)])
    exam_out = None
    if exam:
        rows = []
        for sec in exam["section_ids"]:
            r = await compute_results(exam, sec)
            rows.append({"section_id": sec, "label": label.get(sec, "—"), "average": r["class_average"],
                         "pass_rate": round(100 * r["pass_count"] / r["students"], 1) if r["students"] else None})
        exam_out = {"id": str(exam["_id"]), "name": exam["name"], "sections": sorted(rows, key=lambda x: -(x["average"] or 0))}

    # staff attendance over the window
    staff = {"present": 0, "late": 0, "absent": 0, "half_day": 0, "on_leave": 0}
    async for r in db.staff_attendance.find({"school_id": sid, "date": {"$gte": start}}, {"status": 1}):
        staff[r["status"]] += 1
    marked = sum(staff.values())
    return {
        "window_days": days, "from": start, "to": today.isoformat(), "working_days_with_attendance": working or 0,
        "attendance": {"trend": trend, "lowest_sections": sec_rates[:5],
                       "overall_rate": round(100 * sum(v[0] for v in by_sec.values()) / sum(v[1] for v in by_sec.values()), 1) if by_sec else None,
                       "frequent_absentees": [{"student_id": k, "name": names.get(k, "—"), "absences": v} for k, v in absentees]},
        "coverage": {"sections": coverage, "sections_without_homework": sum(1 for c in coverage if not c["homework"]),
                     "sections_without_diary": sum(1 for c in coverage if not c["diary_days"]),
                     "homework_published": sum(hw.values())},
        "latest_exam": exam_out,
        "staff": {**staff, "marked": marked,
                  "punctuality": round(100 * staff["present"] / (staff["present"] + staff["late"]), 1) if staff["present"] + staff["late"] else None},
        "leave_pending": await db.leave_requests.count_documents({"school_id": sid, "status": "pending"}),
    }
