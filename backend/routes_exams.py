"""Milestone 2 — Module 6: Examinations (assessments, marks entry, validation, results, branded PDF report cards)."""
import io
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

import storage
from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_attendance import _section_access
from routes_directory import _parent_links
from routes_homework import _can_assign

router = APIRouter()
GRADES = [(91, "A1"), (81, "A2"), (71, "B1"), (61, "B2"), (51, "C1"), (41, "C2"), (33, "D"), (0, "E")]


def grade(pct: Optional[float]) -> Optional[str]:
    if pct is None:
        return None
    return next(g for lo, g in GRADES if pct >= lo)


class ExamSubject(BaseModel):
    subject_id: str
    max_marks: float = Field(gt=0, le=1000)
    pass_marks: float = Field(ge=0)
    date: Optional[date] = None

    @model_validator(mode="after")
    def _pass(self):
        if self.pass_marks > self.max_marks:
            raise ValueError("Pass marks cannot exceed maximum marks")
        return self


class ExamIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    term: str = Field(default="", max_length=40)
    start_date: date
    end_date: date
    section_ids: list[str] = Field(min_length=1, max_length=100)
    subjects: list[ExamSubject] = Field(min_length=1, max_length=20)


class Mark(BaseModel):
    student_id: str
    marks: Optional[float] = None
    absent: bool = False


class MarksIn(BaseModel):
    records: list[Mark] = Field(min_length=1, max_length=200)


async def _exam(ctx: Ctx, eid: str) -> dict:
    e = await db.exams.find_one({"_id": oid(eid), "school_id": ctx.school_id, "status": {"$ne": "deleted"}})
    if not e:
        raise HTTPException(404, "Exam not found")
    return e


async def _sections_for(ctx: Ctx) -> Optional[set]:
    """None = all sections (admins); otherwise sections the teacher is assigned to."""
    if "academic.manage" in ctx.perms:
        return None
    t = await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id})
    if not t:
        return set()
    return {a["section_id"] for a in await db.teacher_assignments.find({"school_id": ctx.school_id,
                                                                         "teacher_id": str(t["_id"])}).to_list(200)}


async def _exam_out(e: dict, ctx: Ctx) -> dict:
    o = out(e)
    subs = {str(s["_id"]): s["name"] for s in await db.subjects.find({"school_id": e["school_id"]}).to_list(200)}
    secs = {str(s["_id"]): f"{s['class_name']} - {s['name']}" for s in await db.sections.find(
        {"_id": {"$in": [oid(x) for x in e["section_ids"]]}}).to_list(200)}
    for s in o["subjects"]:
        s["subject_name"] = subs.get(s["subject_id"], "—")
    sheets = {(m["section_id"], m["subject_id"]): m async for m in db.exam_marks.find({"exam_id": str(e["_id"])})}
    allowed = await _sections_for(ctx)
    o["sheets"] = [{"section_id": sec, "section_label": secs.get(sec, "—"), "subject_id": s["subject_id"],
                    "subject_name": subs.get(s["subject_id"], "—"), "entered": (sec, s["subject_id"]) in sheets}
                   for sec in e["section_ids"] if allowed is None or sec in allowed for s in e["subjects"]]
    o["sections"] = [{"id": s, "label": secs.get(s, "—")} for s in e["section_ids"] if allowed is None or s in allowed]
    o["progress"] = {"entered": sum(1 for x in o["sheets"] if x["entered"]), "total": len(o["sheets"])}
    return o


@router.post("/exams", status_code=201)
async def create_exam(body: ExamIn, ctx: Ctx = Depends(need("academic.manage"))):
    if body.end_date < body.start_date:
        raise HTTPException(400, "End date must be on or after the start date")
    if len({s.subject_id for s in body.subjects}) != len(body.subjects):
        raise HTTPException(400, "Each subject can appear only once")
    for sid in set(body.section_ids):
        if not await db.sections.find_one({"_id": oid(sid), "school_id": ctx.school_id}):
            raise HTTPException(404, "Section not found")
    for s in body.subjects:
        if not await db.subjects.find_one({"_id": oid(s.subject_id), "school_id": ctx.school_id}):
            raise HTTPException(404, "Subject not found")
        if s.date and not body.start_date <= s.date <= body.end_date:
            raise HTTPException(400, "Subject exam dates must fall within the exam period")
    t = now_utc()
    doc = {"school_id": ctx.school_id, "name": body.name.strip(), "term": body.term.strip(),
           "start_date": body.start_date.isoformat(), "end_date": body.end_date.isoformat(),
           "section_ids": list(dict.fromkeys(body.section_ids)),
           "subjects": [{**s.model_dump(), "date": s.date.isoformat() if s.date else None} for s in body.subjects],
           "status": "marks_open", "created_by": ctx.user_id, "created_at": t, "updated_at": t, "published_at": None}
    r = await db.exams.insert_one(doc)
    await audit(ctx.user_id, "exam.create", "exam", str(r.inserted_id), ctx.school_id)
    return await _exam_out({**doc, "_id": r.inserted_id}, ctx)


@router.get("/exams")
async def list_exams(ctx: Ctx = Depends(school_ctx)):
    if not ({"academic.manage", "teacher.workspace", "academic.view"} & ctx.perms) or "parent.portal" in ctx.perms:
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    allowed = await _sections_for(ctx)
    filt = {"school_id": ctx.school_id, "status": {"$ne": "deleted"}}
    if allowed is not None:
        filt["section_ids"] = {"$in": list(allowed)}
    items = await db.exams.find(filt).sort("start_date", -1).to_list(100)
    return {"items": [await _exam_out(e, ctx) for e in items]}


@router.get("/exams/{eid}")
async def get_exam(eid: str, ctx: Ctx = Depends(school_ctx)):
    e = await _exam(ctx, eid)
    allowed = await _sections_for(ctx)
    if allowed is not None and not allowed & set(e["section_ids"]):
        raise HTTPException(403, "You are not assigned to any section in this exam")
    return await _exam_out(e, ctx)


@router.post("/exams/{eid}/status")
async def set_status(eid: str, status: Literal["marks_open", "published"] = Query(...),
                     ctx: Ctx = Depends(need("academic.manage"))):
    e = await _exam(ctx, eid)
    if status == "published":
        o = await _exam_out(e, ctx)
        missing = [f"{x['section_label']} {x['subject_name']}" for x in o["sheets"] if not x["entered"]]
        if missing:
            raise HTTPException(400, f"Marks are missing for: {', '.join(missing[:5])}{'…' if len(missing) > 5 else ''}")
    await db.exams.update_one({"_id": e["_id"]}, {"$set": {"status": status, "updated_at": now_utc(),
                                                           "published_at": now_utc() if status == "published" else None}})
    await audit(ctx.user_id, "exam.publish" if status == "published" else "exam.reopen", "exam", eid, ctx.school_id)
    return await _exam_out(await db.exams.find_one({"_id": e["_id"]}), ctx)


@router.delete("/exams/{eid}")
async def delete_exam(eid: str, ctx: Ctx = Depends(need("academic.manage"))):
    e = await _exam(ctx, eid)
    if e["status"] == "published":
        raise HTTPException(400, "Unpublish the exam before deleting it")
    await db.exams.update_one({"_id": e["_id"]}, {"$set": {"status": "deleted", "updated_at": now_utc()}})
    await audit(ctx.user_id, "exam.delete", "exam", eid, ctx.school_id)
    return {"ok": True}


async def _sheet_access(ctx: Ctx, e: dict, section_id: str, subject_id: str) -> dict:
    if section_id not in e["section_ids"]:
        raise HTTPException(404, "This section is not part of the exam")
    subj = next((s for s in e["subjects"] if s["subject_id"] == subject_id), None)
    if not subj:
        raise HTTPException(404, "This subject is not part of the exam")
    await _can_assign(ctx, section_id, subject_id)
    return subj


@router.get("/exams/{eid}/marks")
async def get_marks(eid: str, section_id: str, subject_id: str, ctx: Ctx = Depends(school_ctx)):
    e = await _exam(ctx, eid)
    subj = await _sheet_access(ctx, e, section_id, subject_id)
    sheet = await db.exam_marks.find_one({"exam_id": eid, "section_id": section_id, "subject_id": subject_id})
    recs = {r["student_id"]: r for r in (sheet or {}).get("records", [])}
    studs = await db.students.find({"school_id": ctx.school_id, "section_id": section_id, "status": "active"}
                                   ).sort("roll_no", 1).to_list(200)
    sub = await db.subjects.find_one({"_id": oid(subject_id)})
    sec = await db.sections.find_one({"_id": oid(section_id)})
    return {"exam": e["name"], "status": e["status"], "subject": sub["name"], "section": f"{sec['class_name']} - {sec['name']}",
            "max_marks": subj["max_marks"], "pass_marks": subj["pass_marks"], "entered": bool(sheet),
            "students": [{"id": str(s["_id"]), "name": f"{s['first_name']} {s['last_name']}".strip(), "roll_no": s.get("roll_no"),
                          "marks": recs.get(str(s["_id"]), {}).get("marks"), "absent": recs.get(str(s["_id"]), {}).get("absent", False)}
                         for s in studs]}


@router.put("/exams/{eid}/marks")
async def save_marks(eid: str, body: MarksIn, section_id: str, subject_id: str, ctx: Ctx = Depends(school_ctx)):
    e = await _exam(ctx, eid)
    subj = await _sheet_access(ctx, e, section_id, subject_id)
    if e["status"] != "marks_open":
        raise HTTPException(400, "Results are published; marks are locked. Re-open the exam to edit marks.")
    valid = {str(s["_id"]) for s in await db.students.find(
        {"school_id": ctx.school_id, "section_id": section_id, "status": "active"}, {"_id": 1}).to_list(300)}
    ids = [r.student_id for r in body.records]
    if len(set(ids)) != len(ids) or not set(ids) <= valid:
        raise HTTPException(400, "Records include students who are not in this section")
    if set(ids) != valid:
        raise HTTPException(400, "Enter marks (or mark absent) for every student before saving")
    for r in body.records:
        if r.absent:
            r.marks = None
        elif r.marks is None:
            raise HTTPException(400, "Enter marks (or mark absent) for every student before saving")
        elif not 0 <= r.marks <= subj["max_marks"]:
            raise HTTPException(400, f"Marks must be between 0 and {subj['max_marks']:g}")
        elif round(r.marks * 2) != r.marks * 2:
            raise HTTPException(400, "Marks can have at most one half (e.g. 42.5)")
    key = {"school_id": ctx.school_id, "exam_id": eid, "section_id": section_id, "subject_id": subject_id}
    prev = await db.exam_marks.find_one(key)
    await db.exam_marks.update_one(key, {"$set": {"records": [r.model_dump() for r in body.records], "entered_by": ctx.user_id,
                                                  "updated_at": now_utc()},
                                         "$setOnInsert": {"created_at": now_utc()}}, upsert=True)
    await audit(ctx.user_id, "exam.marks_update" if prev else "exam.marks_enter", "exam", eid, ctx.school_id,
                {"section_id": section_id, "subject_id": subject_id})
    return await get_marks(eid, section_id, subject_id, ctx)


async def compute_results(e: dict, section_id: str) -> dict:
    subs = {str(s["_id"]): s["name"] for s in await db.subjects.find({"school_id": e["school_id"]}).to_list(200)}
    sheets = {m["subject_id"]: {r["student_id"]: r for r in m["records"]}
              async for m in db.exam_marks.find({"exam_id": str(e["_id"]), "section_id": section_id})}
    studs = await db.students.find({"school_id": e["school_id"], "section_id": section_id, "status": "active"}
                                   ).sort("roll_no", 1).to_list(200)
    rows = []
    for s in studs:
        sid, total, maxt, failed, lines = str(s["_id"]), 0.0, 0.0, False, []
        for sub in e["subjects"]:
            r = sheets.get(sub["subject_id"], {}).get(sid)
            m = None if not r or r.get("absent") else r.get("marks")
            if r is not None:
                maxt += sub["max_marks"]
                total += m or 0
            passed = m is not None and m >= sub["pass_marks"]
            failed = failed or (r is not None and not passed)
            lines.append({"subject_id": sub["subject_id"], "subject": subs.get(sub["subject_id"], "—"), "max": sub["max_marks"],
                          "marks": m, "absent": bool(r and r.get("absent")), "entered": r is not None,
                          "grade": grade(100 * m / sub["max_marks"]) if m is not None else None, "passed": passed})
        pct = round(100 * total / maxt, 1) if maxt else None
        rows.append({"student_id": sid, "name": f"{s['first_name']} {s['last_name']}".strip(), "roll_no": s.get("roll_no"),
                     "admission_no": s["admission_no"], "total": total, "max_total": maxt, "percentage": pct,
                     "grade": grade(pct), "result": None if pct is None else ("Fail" if failed else "Pass"), "subjects": lines})
    ranked = sorted([r for r in rows if r["percentage"] is not None], key=lambda r: -r["percentage"])
    for r in rows:
        r["rank"] = 1 + sum(1 for x in ranked if x["percentage"] > r["percentage"]) if r["percentage"] is not None else None
    vals = [r["percentage"] for r in ranked]
    return {"rows": rows, "class_average": round(sum(vals) / len(vals), 1) if vals else None,
            "pass_count": sum(1 for r in rows if r["result"] == "Pass"), "students": len(rows)}


@router.get("/exams/{eid}/results")
async def results(eid: str, section_id: str, ctx: Ctx = Depends(school_ctx)):
    e = await _exam(ctx, eid)
    if section_id not in e["section_ids"]:
        raise HTTPException(404, "This section is not part of the exam")
    sec = await _section_access(ctx, section_id)
    return {"exam": e["name"], "status": e["status"], "section": f"{sec['class_name']} - {sec['name']}",
            **await compute_results(e, section_id)}


@router.get("/exams/summary/recent")
async def exam_summary(ctx: Ctx = Depends(need("dashboard.owner"))):
    items = []
    async for e in db.exams.find({"school_id": ctx.school_id, "status": {"$ne": "deleted"}}).sort("start_date", -1).limit(3):
        expected = len(e["section_ids"]) * len(e["subjects"])
        entered = await db.exam_marks.count_documents({"exam_id": str(e["_id"])})
        avg = None
        if e["status"] == "published":
            pcts = [r["percentage"] for sec in e["section_ids"] for r in (await compute_results(e, sec))["rows"]
                    if r["percentage"] is not None]
            avg = round(sum(pcts) / len(pcts), 1) if pcts else None
        items.append({"id": str(e["_id"]), "name": e["name"], "status": e["status"], "entered": entered,
                      "expected": expected, "average": avg})
    return {"items": items}


# ---------------------------------------------------------------- parent + report card
@router.get("/parent/children/{student_id}/exams")
async def parent_exams(student_id: str, ctx: Ctx = Depends(need("parent.portal"))):
    if student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id})
    res = []
    async for e in db.exams.find({"school_id": ctx.school_id, "status": "published", "section_ids": st["section_id"]}
                                 ).sort("start_date", -1):
        rows = (await compute_results(e, st["section_id"]))["rows"]
        me = next((r for r in rows if r["student_id"] == student_id), None)
        if me:
            res.append({"id": str(e["_id"]), "name": e["name"], "term": e.get("term", ""),
                        "published_at": out(e)["published_at"], **{k: me[k] for k in
                        ("total", "max_total", "percentage", "grade", "result", "rank", "subjects")},
                        "class_size": len(rows)})
    return {"items": res}


def _render_pdf(school: dict, logo: Optional[bytes], exam: dict, row: dict, student: dict, section: str, class_size: int) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle

    primary = colors.HexColor(school.get("brand", {}).get("primary") or "#0A192F")
    secondary = colors.HexColor(school.get("brand", {}).get("secondary") or "#0D9488")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setTitle(f"Report card - {row['name']} - {exam['name']}")
    c.setFillColor(primary)
    c.rect(0, h - 38 * mm, w, 38 * mm, fill=1, stroke=0)
    x = 18 * mm
    if logo:
        try:
            c.drawImage(ImageReader(io.BytesIO(logo)), x, h - 31 * mm, 22 * mm, 22 * mm, preserveAspectRatio=True, mask="auto")
            x += 27 * mm
        except Exception:  # noqa: BLE001 — a broken logo must not block the report card
            pass
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x, h - 18 * mm, school["name"][:60])
    c.setFont("Helvetica", 10)
    contact = school.get("contact", {})
    c.drawString(x, h - 24 * mm, ", ".join(filter(None, [contact.get("address"), contact.get("phone")]))[:95])
    c.drawString(x, h - 29 * mm, f"Report Card · {exam['name']}{' · ' + exam['term'] if exam.get('term') else ''}"[:95])
    c.setFillColor(colors.black)
    y = h - 50 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(18 * mm, y, row["name"])
    c.setFont("Helvetica", 10)
    c.drawString(18 * mm, y - 6 * mm, f"Admission no: {row['admission_no']}    Class: {section}    Roll no: {row.get('roll_no') or '—'}")
    c.drawString(18 * mm, y - 12 * mm, f"Date of birth: {student.get('dob') or '—'}    Session: {school.get('academic_session_label') or '—'}")
    data = [["Subject", "Max", "Marks", "Grade", "Status"]]
    for s in row["subjects"]:
        data.append([s["subject"], f"{s['max']:g}", "AB" if s["absent"] else ("—" if s["marks"] is None else f"{s['marks']:g}"),
                     s["grade"] or "—", "Pass" if s["passed"] else ("Absent" if s["absent"] else "—" if not s["entered"] else "Fail")])
    data.append(["Total", f"{row['max_total']:g}", f"{row['total']:g}", row["grade"] or "—", row["result"] or "—"])
    t = Table(data, colWidths=[70 * mm, 22 * mm, 25 * mm, 22 * mm, 30 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), secondary), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                           ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    tw, th = t.wrapOn(c, w, h)
    t.drawOn(c, 18 * mm, y - 22 * mm - th)
    yy = y - 32 * mm - th
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, yy, f"Percentage: {row['percentage'] if row['percentage'] is not None else '—'}%    "
                              f"Grade: {row['grade'] or '—'}    Rank: {row['rank'] or '—'} of {class_size}")
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(18 * mm, yy - 8 * mm, "Grades: A1 91-100 · A2 81-90 · B1 71-80 · B2 61-70 · C1 51-60 · C2 41-50 · D 33-40 · E below 33")
    c.setFillColor(colors.black)
    c.line(18 * mm, 40 * mm, 70 * mm, 40 * mm)
    c.line(w - 70 * mm, 40 * mm, w - 18 * mm, 40 * mm)
    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, 35 * mm, "Class Teacher")
    c.drawString(w - 70 * mm, 35 * mm, "Principal")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(18 * mm, 15 * mm, f"Generated by SchoolPulse OS on {now_utc().strftime('%d %b %Y')} · computer-generated from published results")
    c.showPage()
    c.save()
    return buf.getvalue()


async def render_report_card(ctx: Ctx, eid: str, student_id: str) -> tuple[bytes, str]:
    """Authorise + render. Staff with section access, or a verified guardian once results are published."""
    e = await _exam(ctx, eid)
    st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id})
    if not st or st["section_id"] not in e["section_ids"]:
        raise HTTPException(404, "Student is not part of this exam")
    if "parent.portal" in ctx.perms:
        if e["status"] != "published" or student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
            raise HTTPException(403, "Report card is not available")
    elif not ({"academic.manage", "teacher.workspace"} & ctx.perms):
        raise HTTPException(403, "Report card is not available")
    else:
        await _section_access(ctx, st["section_id"])
    res = await compute_results(e, st["section_id"])
    row = next(r for r in res["rows"] if r["student_id"] == student_id)
    sch = await db.schools.find_one({"_id": oid(ctx.school_id)})
    logo = None
    fid = sch.get("brand", {}).get("logo_file_id")
    if fid:
        f = await db.files.find_one({"_id": oid(fid)})
        if f:
            try:
                logo, _ = await run_in_threadpool(storage.get_object, f["storage_path"])
            except Exception:  # noqa: BLE001
                logo = None
    sec = await db.sections.find_one({"_id": oid(st["section_id"])})
    pdf = await run_in_threadpool(_render_pdf, sch, logo, e, row, st, f"{sec['class_name']} - {sec['name']}", res["students"])
    await audit(ctx.user_id, "exam.report_card", "exam", eid, ctx.school_id, {"student_id": student_id})
    return pdf, f"report-card-{row['admission_no']}.pdf"


def pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


@router.get("/exams/{eid}/report-card/{student_id}.pdf")
async def report_card(eid: str, student_id: str, ctx: Ctx = Depends(school_ctx)):
    """Header-authenticated download (Authorization + X-School-Id). Tokens are never accepted in the URL."""
    return pdf_response(*await render_report_card(ctx, eid, student_id))


@router.post("/exams/{eid}/report-card/{student_id}/download-grant")
async def report_card_grant(eid: str, student_id: str, ctx: Ctx = Depends(school_ctx)):
    """For native in-app browsers: authorise now, return a single-use 60 s URL (no access token in it)."""
    from file_access import issue_grant
    await render_report_card(ctx, eid, student_id)  # fail fast with the same rules
    return await issue_grant(ctx.user_id, ctx.school_id, "report_card", {"exam_id": eid, "student_id": student_id})
