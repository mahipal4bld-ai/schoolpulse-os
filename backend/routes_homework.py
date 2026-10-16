"""Milestone 2 — Module 3: Homework (subject-wise, attachments, due dates, completion, parent visibility)."""
import uuid
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import storage
from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_attendance import today_ist
from routes_directory import _parent_links

router = APIRouter()
ATTACH_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
ATTACH_MAX = 10 * 1024 * 1024
Completion = Literal["done", "not_done", "late"]


async def _teacher(ctx: Ctx) -> Optional[dict]:
    return await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id})


async def _can_assign(ctx: Ctx, section_id: str, subject_id: str) -> None:
    """Admins: any section/subject. Teachers: subject they teach in the section, or any subject as class teacher."""
    if not await db.sections.find_one({"_id": oid(section_id), "school_id": ctx.school_id}):
        raise HTTPException(404, "Section not found")
    if not await db.subjects.find_one({"_id": oid(subject_id), "school_id": ctx.school_id}):
        raise HTTPException(404, "Subject not found")
    if "academic.manage" in ctx.perms:
        return
    t = await _teacher(ctx) if "teacher.workspace" in ctx.perms else None
    if t:
        asg = await db.teacher_assignments.find({"school_id": ctx.school_id, "teacher_id": str(t["_id"]),
                                                 "section_id": section_id}).to_list(50)
        if any(a.get("subject_id") == subject_id or a.get("is_class_teacher") for a in asg):
            return
    raise HTTPException(403, "You are not assigned to teach this subject in this section")


async def _get(ctx: Ctx, hid: str) -> dict:
    hw = await db.homework.find_one({"_id": oid(hid), "school_id": ctx.school_id, "status": {"$ne": "deleted"}})
    if not hw:
        raise HTTPException(404, "Homework not found")
    if "academic.manage" not in ctx.perms and hw["created_by"] != ctx.user_id:
        await _can_assign(ctx, hw["section_id"], hw["subject_id"])
    return hw


async def _out(hw: dict, with_students: bool = False) -> dict:
    o = out(hw)
    sec = await db.sections.find_one({"_id": oid(hw["section_id"])}, {"class_name": 1, "name": 1})
    sub = await db.subjects.find_one({"_id": oid(hw["subject_id"])}, {"name": 1})
    o["section_label"] = f"{sec['class_name']} - {sec['name']}" if sec else "—"
    o["subject_name"] = sub["name"] if sub else "—"
    files = await db.files.find({"_id": {"$in": [oid(f) for f in hw.get("attachments", [])]}, "is_deleted": False}
                                ).to_list(10)
    o["attachments"] = [{"id": str(f["_id"]), "name": f.get("original_name") or "attachment",
                         "content_type": f["content_type"], "size": f["size"]} for f in files]
    comp = {c["student_id"]: c["status"] for c in hw.get("completion", [])}
    o.pop("completion", None)
    o["completion_counts"] = {k: sum(1 for v in comp.values() if v == k) for k in ("done", "not_done", "late")}
    if with_students:
        studs = await db.students.find({"school_id": hw["school_id"], "section_id": hw["section_id"], "status": "active"}
                                       ).sort("roll_no", 1).to_list(200)
        o["students"] = [{"id": str(s["_id"]), "name": f"{s['first_name']} {s['last_name']}".strip(),
                          "roll_no": s.get("roll_no"), "status": comp.get(str(s["_id"]))} for s in studs]
    return o


class HomeworkIn(BaseModel):
    section_id: str
    subject_id: str
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=3000)
    due_date: date
    attachments: list[str] = Field(default_factory=list, max_length=5)
    publish: bool = False


class HomeworkPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=120)
    description: Optional[str] = Field(default=None, max_length=3000)
    due_date: Optional[date] = None
    attachments: Optional[list[str]] = Field(default=None, max_length=5)


async def _check_files(ctx: Ctx, ids: list[str]) -> list[str]:
    for fid in ids:
        f = await db.files.find_one({"_id": oid(fid), "school_id": ctx.school_id, "purpose": "homework",
                                     "is_deleted": False})
        if not f or f["uploaded_by"] != ctx.user_id and "academic.manage" not in ctx.perms:
            raise HTTPException(400, "Attachment not found")
    return ids


def _check_due(due: date, assigned: date):
    if due < assigned:
        raise HTTPException(400, "Due date cannot be before the assigned date")
    if due > assigned + timedelta(days=60):
        raise HTTPException(400, "Due date must be within 60 days")


@router.post("/homework/attachments", status_code=201)
async def upload_attachment(file: UploadFile = File(...), ctx: Ctx = Depends(school_ctx)):
    if not ({"academic.manage", "teacher.workspace"} & ctx.perms):
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    ctype = file.content_type or ""
    if ctype not in ATTACH_TYPES:
        raise HTTPException(400, "Only PDF, JPG, PNG or WEBP files are allowed")
    data = await file.read()
    if len(data) > ATTACH_MAX:
        raise HTTPException(413, "Attachment must be under 10 MB")
    path = f"{storage.APP_NAME}/schools/{ctx.school_id}/homework/{uuid.uuid4().hex}.{ATTACH_TYPES[ctype]}"
    try:
        res = await run_in_threadpool(storage.put_object, path, data, ctype)
    except Exception as e:  # noqa: BLE001
        code = getattr(getattr(e, "response", None), "status_code", None)
        raise HTTPException(503 if code != 402 else 402, "Storage is unavailable. Please try again later.")
    doc = {"school_id": ctx.school_id, "storage_path": res["path"], "content_type": ctype, "size": len(data),
           "original_name": (file.filename or "attachment")[:120], "purpose": "homework", "visibility": "private",
           "uploaded_by": ctx.user_id, "is_deleted": False, "created_at": now_utc()}
    r = await db.files.insert_one(doc)
    await audit(ctx.user_id, "file.upload", "file", str(r.inserted_id), ctx.school_id, {"purpose": "homework"})
    return {"id": str(r.inserted_id), "name": doc["original_name"], "content_type": ctype, "size": len(data)}


@router.post("/homework", status_code=201)
async def create(body: HomeworkIn, ctx: Ctx = Depends(school_ctx)):
    await _can_assign(ctx, body.section_id, body.subject_id)
    assigned = today_ist()
    _check_due(body.due_date, assigned)
    t = now_utc()
    teacher = await _teacher(ctx)
    doc = {"school_id": ctx.school_id, "section_id": body.section_id, "subject_id": body.subject_id,
           "title": body.title.strip(), "description": body.description.strip(), "assigned_date": assigned.isoformat(),
           "due_date": body.due_date.isoformat(), "attachments": await _check_files(ctx, body.attachments),
           "status": "published" if body.publish else "draft", "published_at": t if body.publish else None,
           "created_by": ctx.user_id, "teacher_id": str(teacher["_id"]) if teacher else None,
           "completion": [], "created_at": t, "updated_at": t}
    r = await db.homework.insert_one(doc)
    await audit(ctx.user_id, "homework.publish" if body.publish else "homework.create", "homework",
                str(r.inserted_id), ctx.school_id)
    return await _out({**doc, "_id": r.inserted_id})


@router.get("/homework")
async def list_homework(section_id: Optional[str] = None, status: Optional[Literal["draft", "published"]] = None,
                        scope: Literal["mine", "all"] = "mine", ctx: Ctx = Depends(school_ctx)):
    if not ({"academic.manage", "teacher.workspace"} & ctx.perms):
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    filt: dict = {"school_id": ctx.school_id, "status": {"$ne": "deleted"}}
    if not ("academic.manage" in ctx.perms and scope == "all"):
        filt["created_by"] = ctx.user_id
    if section_id:
        filt["section_id"] = section_id
    if status:
        filt["status"] = status
    items = await db.homework.find(filt).sort([("due_date", -1), ("created_at", -1)]).to_list(200)
    return {"items": [await _out(h) for h in items]}


@router.get("/homework/summary")
async def summary(ctx: Ctx = Depends(need("dashboard.owner"))):
    today = today_ist()
    week = (today - timedelta(days=today.weekday())).isoformat()
    base = {"school_id": ctx.school_id, "status": "published"}
    total_sections = await db.sections.count_documents({"school_id": ctx.school_id})
    secs_week = await db.homework.distinct("section_id", {**base, "assigned_date": {"$gte": week}})
    return {"published_this_week": await db.homework.count_documents({**base, "assigned_date": {"$gte": week}}),
            "due_today": await db.homework.count_documents({**base, "due_date": today.isoformat()}),
            "drafts": await db.homework.count_documents({"school_id": ctx.school_id, "status": "draft"}),
            "sections_with_homework_this_week": len(secs_week), "sections_total": total_sections}


@router.get("/homework/options")
async def options(ctx: Ctx = Depends(school_ctx)):
    """Sections and subjects the caller may assign homework to."""
    if not ({"academic.manage", "teacher.workspace"} & ctx.perms):
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    subjects = {str(s["_id"]): s["name"] for s in await db.subjects.find({"school_id": ctx.school_id}).sort("name", 1).to_list(100)}
    secs = await db.sections.find({"school_id": ctx.school_id}).sort([("class_name", 1), ("name", 1)]).to_list(300)
    if "academic.manage" in ctx.perms:
        return {"items": [{"section_id": str(s["_id"]), "label": f"{s['class_name']} - {s['name']}",
                           "subjects": [{"id": k, "name": v} for k, v in subjects.items()]} for s in secs]}
    t = await _teacher(ctx)
    asg = await db.teacher_assignments.find({"school_id": ctx.school_id, "teacher_id": str(t["_id"])}).to_list(100) if t else []
    res = []
    for s in secs:
        mine = [a for a in asg if a["section_id"] == str(s["_id"])]
        if not mine:
            continue
        ids = list(subjects) if any(a.get("is_class_teacher") for a in mine) else [a["subject_id"] for a in mine if a.get("subject_id")]
        res.append({"section_id": str(s["_id"]), "label": f"{s['class_name']} - {s['name']}",
                    "subjects": [{"id": i, "name": subjects[i]} for i in ids if i in subjects]})
    return {"items": res}


@router.get("/homework/{hid}")
async def get_one(hid: str, ctx: Ctx = Depends(school_ctx)):
    if not ({"academic.manage", "teacher.workspace"} & ctx.perms):
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    return await _out(await _get(ctx, hid), with_students=True)


@router.patch("/homework/{hid}")
async def patch(hid: str, body: HomeworkPatch, ctx: Ctx = Depends(school_ctx)):
    hw = await _get(ctx, hid)
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No changes supplied")
    if "due_date" in data:
        _check_due(data["due_date"], date.fromisoformat(hw["assigned_date"]))
        data["due_date"] = data["due_date"].isoformat()
    if "attachments" in data:
        await _check_files(ctx, data["attachments"])
    data["updated_at"] = now_utc()
    await db.homework.update_one({"_id": hw["_id"]}, {"$set": data})
    await audit(ctx.user_id, "homework.update", "homework", hid, ctx.school_id, {"fields": list(data)})
    return await _out(await db.homework.find_one({"_id": hw["_id"]}), with_students=True)


@router.post("/homework/{hid}/publish")
async def publish(hid: str, ctx: Ctx = Depends(school_ctx)):
    hw = await _get(ctx, hid)
    if hw["status"] != "published":
        await db.homework.update_one({"_id": hw["_id"]}, {"$set": {"status": "published", "published_at": now_utc(),
                                                                   "updated_at": now_utc()}})
        await audit(ctx.user_id, "homework.publish", "homework", hid, ctx.school_id)
    return await _out(await db.homework.find_one({"_id": hw["_id"]}), with_students=True)


@router.delete("/homework/{hid}")
async def delete(hid: str, ctx: Ctx = Depends(school_ctx)):
    hw = await _get(ctx, hid)
    await db.homework.update_one({"_id": hw["_id"]}, {"$set": {"status": "deleted", "updated_at": now_utc()}})
    await audit(ctx.user_id, "homework.delete", "homework", hid, ctx.school_id, {"was": hw["status"]})
    return {"ok": True}


class CompletionIn(BaseModel):
    records: list[dict] = Field(min_length=1, max_length=200)


class CompletionMark(BaseModel):
    student_id: str
    status: Completion


@router.put("/homework/{hid}/completion")
async def completion(hid: str, body: CompletionIn, ctx: Ctx = Depends(school_ctx)):
    hw = await _get(ctx, hid)
    if hw["status"] != "published":
        raise HTTPException(400, "Publish the homework before tracking completion")
    marks = [CompletionMark(**r) for r in body.records]
    valid = {str(s["_id"]) for s in await db.students.find(
        {"school_id": ctx.school_id, "section_id": hw["section_id"], "status": "active"}, {"_id": 1}).to_list(300)}
    if not {m.student_id for m in marks} <= valid:
        raise HTTPException(400, "Records include students who are not in this section")
    current = {c["student_id"]: c for c in hw.get("completion", [])}
    t = now_utc()
    for m in marks:
        current[m.student_id] = {"student_id": m.student_id, "status": m.status, "by": ctx.user_id, "at": t}
    await db.homework.update_one({"_id": hw["_id"]}, {"$set": {"completion": list(current.values()), "updated_at": t}})
    await audit(ctx.user_id, "homework.completion", "homework", hid, ctx.school_id, {"records": len(marks)})
    return await _out(await db.homework.find_one({"_id": hw["_id"]}), with_students=True)


# ---------------------------------------------------------------- parent
@router.get("/parent/children/{student_id}/homework")
async def parent_homework(student_id: str, scope: Literal["upcoming", "past"] = "upcoming",
                          ctx: Ctx = Depends(need("parent.portal"))):
    if student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id})
    today = today_ist().isoformat()
    filt = {"school_id": ctx.school_id, "section_id": st["section_id"], "status": "published",
            "due_date": {"$gte": today} if scope == "upcoming" else {"$lt": today}}
    items = await db.homework.find(filt).sort("due_date", 1 if scope == "upcoming" else -1).to_list(60)
    res = []
    for h in items:
        mine = next((c["status"] for c in h.get("completion", []) if c["student_id"] == student_id), None)
        o = await _out(h)
        o.pop("completion_counts", None)
        for k in ("created_by", "teacher_id"):
            o.pop(k, None)
        res.append({**o, "my_status": mine})
    return {"scope": scope, "items": res}


async def parent_can_read_file(user_id: str, f: dict) -> bool:
    """Parents may read a homework attachment only if it is on a published homework for their verified child's section."""
    if f.get("purpose") != "homework":
        return False
    hws = await db.homework.find({"school_id": f["school_id"], "status": "published", "attachments": str(f["_id"])},
                                 {"section_id": 1}).to_list(20)
    if not hws:
        return False
    gids = [str(g["_id"]) for g in await db.guardians.find({"school_id": f["school_id"], "user_id": user_id}).to_list(10)]
    links = await db.guardian_links.find({"guardian_id": {"$in": gids}, "verified": True}).to_list(20)
    secs = {s["section_id"] for s in await db.students.find(
        {"_id": {"$in": [oid(lk["student_id"]) for lk in links]}, "status": "active"}, {"section_id": 1}).to_list(20)}
    return any(h["section_id"] in secs for h in hws)
