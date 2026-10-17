"""Milestone 3 — Module 2: Secure parent–teacher messaging (scoped, idempotent, cursor-paginated, rate-limited)."""
import uuid
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

import storage
from core import Ctx, audit, db, now_utc, oid, out, school_ctx
from routes_directory import _parent_links
from routes_homework import ATTACH_MAX, ATTACH_TYPES
from routes_notices import sanitize

router = APIRouter()
RATE_N, RATE_WINDOW = 20, timedelta(minutes=10)
LEADERS = {"owner", "principal", "school_admin"}


class StartIn(BaseModel):
    student_id: str
    teacher_id: str
    topic: str = Field(min_length=2, max_length=80)
    body: str = Field(min_length=1, max_length=2000)
    client_id: str = Field(min_length=8, max_length=64)
    attachments: list[str] = Field(default_factory=list, max_length=3)


class MsgIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    client_id: str = Field(min_length=8, max_length=64)
    attachments: list[str] = Field(default_factory=list, max_length=3)


async def _my_teacher(ctx: Ctx) -> Optional[dict]:
    return await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id, "status": "active"})


async def _teachers_for_student(school_id: str, student: dict) -> list[dict]:
    asg = await db.teacher_assignments.find({"school_id": school_id, "section_id": student["section_id"]}).to_list(50)
    ids = list({a["teacher_id"] for a in asg})
    ts = await db.teachers.find({"_id": {"$in": [oid(i) for i in ids]}, "status": "active", "user_id": {"$ne": None}}).to_list(50)
    subs = {str(s["_id"]): s["name"] for s in await db.subjects.find({"school_id": school_id}).to_list(200)}
    res = []
    for t in ts:
        mine = [a for a in asg if a["teacher_id"] == str(t["_id"])]
        res.append({"teacher_id": str(t["_id"]), "name": t["name"], "user_id": t["user_id"],
                    "availability": t.get("availability", "available"),
                    "role": "Class teacher" if any(a.get("is_class_teacher") for a in mine) else
                    ", ".join(sorted({subs.get(a.get("subject_id"), "") for a in mine if a.get("subject_id")}))})
    return res


async def _access(ctx: Ctx, conv: dict) -> str:
    """Returns the viewer's side: parent | teacher | admin. Re-checks live relationships every call."""
    if conv["school_id"] != ctx.school_id:
        raise HTTPException(404, "Conversation not found")
    if ctx.role == "parent" and conv["guardian_user_id"] == ctx.user_id:
        if conv["student_id"] in {lk["student_id"] for lk in await _parent_links(ctx)}:
            return "parent"
    if ctx.role == "teacher" and conv["teacher_user_id"] == ctx.user_id:
        st = await db.students.find_one({"_id": oid(conv["student_id"])})
        t = await _my_teacher(ctx)
        if st and t and await db.teacher_assignments.find_one({"teacher_id": str(t["_id"]), "section_id": st["section_id"]}):
            return "teacher"
    if ctx.role in LEADERS and conv["status"] == "escalated":
        return "admin"
    raise HTTPException(404, "Conversation not found")


async def _conv_out(c: dict, side: str) -> dict:
    o = out(c)
    st = await db.students.find_one({"_id": oid(c["student_id"])}, {"first_name": 1, "last_name": 1})
    t = await db.teachers.find_one({"_id": oid(c["teacher_id"])}, {"name": 1})
    g = await db.users.find_one({"_id": oid(c["guardian_user_id"])}, {"name": 1})
    o["student_name"] = f"{st['first_name']} {st['last_name']}" if st else "—"
    o["teacher_name"] = t["name"] if t else "—"
    o["guardian_name"] = g["name"] if g else "—"
    o["unread"] = c.get("unread", {}).get("parent" if side == "parent" else "teacher", 0)
    o.pop("guardian_user_id", None)
    o.pop("teacher_user_id", None)
    if side == "parent":
        o.pop("follow_up", None)
    return o


async def _rate_limit(ctx: Ctx):
    n = await db.messages.count_documents({"school_id": ctx.school_id, "sender_user_id": ctx.user_id,
                                           "created_at": {"$gte": now_utc() - RATE_WINDOW}})
    if n >= RATE_N:
        raise HTTPException(429, "You are sending messages too quickly. Please wait a few minutes.")


async def _check_files(ctx: Ctx, ids: list[str]):
    for fid in ids:
        if not await db.files.find_one({"_id": oid(fid), "school_id": ctx.school_id, "purpose": "message",
                                        "uploaded_by": ctx.user_id, "is_deleted": False}):
            raise HTTPException(400, "Attachment not found")


async def _post(ctx: Ctx, conv: dict, side: str, body: MsgIn) -> dict:
    text = sanitize(body.body)
    if not text:
        raise HTTPException(400, "Message cannot be empty")
    prev = await db.messages.find_one({"conversation_id": str(conv["_id"]), "client_id": body.client_id})
    if prev:  # idempotent retry
        return out(prev)
    await _rate_limit(ctx)
    await _check_files(ctx, body.attachments)
    t = now_utc()
    doc = {"school_id": ctx.school_id, "conversation_id": str(conv["_id"]), "sender_user_id": ctx.user_id,
           "sender_role": side, "body": text, "attachments": body.attachments, "client_id": body.client_id,
           "created_at": t, "read_at": None, "status": "sent"}
    try:
        r = await db.messages.insert_one(doc)
    except DuplicateKeyError:
        return out(await db.messages.find_one({"conversation_id": str(conv["_id"]), "client_id": body.client_id}))
    other = "teacher" if side == "parent" else "parent"
    upd = {"$set": {"last_message_at": t, "last_preview": text[:80], "updated_at": t}, "$inc": {f"unread.{other}": 1}}
    if side == "parent" and conv["status"] == "closed":
        upd["$set"]["status"] = "open"
    await db.conversations.update_one({"_id": conv["_id"]}, upd)
    return out({**doc, "_id": r.inserted_id})


@router.get("/messaging/teachers")
async def teachers(student_id: str, ctx: Ctx = Depends(school_ctx)):
    ctx.need("parent.portal")
    if student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    st = await db.students.find_one({"_id": oid(student_id), "school_id": ctx.school_id})
    return {"items": [{k: v for k, v in t.items() if k != "user_id"} for t in await _teachers_for_student(ctx.school_id, st)]}


@router.post("/conversations", status_code=201)
async def start(body: StartIn, ctx: Ctx = Depends(school_ctx)):
    ctx.need("parent.portal")
    if body.student_id not in {lk["student_id"] for lk in await _parent_links(ctx)}:
        raise HTTPException(403, "You are not a verified guardian of this student")
    st = await db.students.find_one({"_id": oid(body.student_id), "school_id": ctx.school_id})
    t = next((x for x in await _teachers_for_student(ctx.school_id, st) if x["teacher_id"] == body.teacher_id), None)
    if not t:
        raise HTTPException(403, "You can message only teachers who teach your child")
    key = {"school_id": ctx.school_id, "student_id": body.student_id, "guardian_user_id": ctx.user_id,
           "teacher_id": body.teacher_id, "topic": sanitize(body.topic)}
    conv = await db.conversations.find_one({**key, "status": {"$ne": "closed"}})
    if not conv:
        tnow = now_utc()
        doc = {**key, "teacher_user_id": t["user_id"], "status": "open", "follow_up": False, "unread": {"parent": 0, "teacher": 0},
               "created_at": tnow, "last_message_at": tnow, "reports": []}
        conv = {**doc, "_id": (await db.conversations.insert_one(doc)).inserted_id}
        await audit(ctx.user_id, "conversation.start", "conversation", str(conv["_id"]), ctx.school_id)
    await _post(ctx, conv, "parent", MsgIn(body=body.body, client_id=body.client_id, attachments=body.attachments))
    return await _conv_out(await db.conversations.find_one({"_id": conv["_id"]}), "parent")


@router.get("/conversations")
async def list_convs(box: Literal["mine", "escalated"] = "mine", ctx: Ctx = Depends(school_ctx)):
    if box == "escalated":
        if ctx.role not in LEADERS:
            raise HTTPException(403, "Not permitted")
        filt, side = {"school_id": ctx.school_id, "status": "escalated"}, "admin"
    elif ctx.role == "parent":
        filt, side = {"school_id": ctx.school_id, "guardian_user_id": ctx.user_id}, "parent"
    elif ctx.role == "teacher":
        filt, side = {"school_id": ctx.school_id, "teacher_user_id": ctx.user_id}, "teacher"
    else:
        raise HTTPException(403, "Messaging is available to parents and teachers")
    res = []
    for c in await db.conversations.find(filt).sort("last_message_at", -1).to_list(100):
        try:
            await _access(ctx, c)
        except HTTPException:
            continue  # relationship revoked: hide
        res.append(await _conv_out(c, side))
    return {"items": res}


@router.get("/conversations/{cid}/messages")
async def messages(cid: str, before: Optional[str] = None, limit: int = Query(30, ge=1, le=100), ctx: Ctx = Depends(school_ctx)):
    c = await db.conversations.find_one({"_id": oid(cid)})
    if not c:
        raise HTTPException(404, "Conversation not found")
    side = await _access(ctx, c)
    filt = {"conversation_id": cid, **({"_id": {"$lt": oid(before)}} if before else {})}
    items = await db.messages.find(filt).sort("_id", -1).limit(limit + 1).to_list(limit + 1)
    more = len(items) > limit
    items = items[:limit]
    if side in ("parent", "teacher"):
        await db.messages.update_many({"conversation_id": cid, "sender_role": {"$ne": side}, "read_at": None},
                                      {"$set": {"read_at": now_utc(), "status": "read"}})
        await db.conversations.update_one({"_id": c["_id"]}, {"$set": {f"unread.{side}": 0}})
    fids = [f for m in items for f in m.get("attachments", [])]
    files = {str(f["_id"]): f for f in await db.files.find({"_id": {"$in": [oid(x) for x in fids]}}).to_list(100)}
    res = []
    for m in items:
        o = out(m)
        o["mine"] = m["sender_user_id"] == ctx.user_id
        o.pop("sender_user_id", None)
        o["attachments"] = [{"id": f, "name": files[f].get("original_name", "file"), "content_type": files[f]["content_type"],
                             "size": files[f]["size"]} for f in m.get("attachments", []) if f in files]
        res.append(o)
    return {"conversation": await _conv_out(await db.conversations.find_one({"_id": c["_id"]}), side), "items": res,
            "next_cursor": str(items[-1]["_id"]) if more else None}


@router.post("/conversations/{cid}/messages", status_code=201)
async def send(cid: str, body: MsgIn, ctx: Ctx = Depends(school_ctx)):
    c = await db.conversations.find_one({"_id": oid(cid)})
    if not c:
        raise HTTPException(404, "Conversation not found")
    side = await _access(ctx, c)
    if side == "admin":
        raise HTTPException(403, "School leaders can review escalated conversations but not post in them")
    if side == "teacher" and c["status"] == "closed":
        raise HTTPException(400, "Re-open the conversation to reply")
    return await _post(ctx, c, side, body)


@router.post("/conversations/{cid}/status")
async def set_status(cid: str, act: Literal["close", "reopen", "escalate", "follow_up", "clear_follow_up"], ctx: Ctx = Depends(school_ctx)):
    c = await db.conversations.find_one({"_id": oid(cid)})
    if not c:
        raise HTTPException(404, "Conversation not found")
    side = await _access(ctx, c)
    if side == "parent" and act != "close":
        raise HTTPException(403, "Not permitted")
    upd = {"close": {"status": "closed"}, "reopen": {"status": "open"}, "escalate": {"status": "escalated"},
           "follow_up": {"follow_up": True}, "clear_follow_up": {"follow_up": False}}[act]
    await db.conversations.update_one({"_id": c["_id"]}, {"$set": {**upd, "updated_at": now_utc()}})
    await audit(ctx.user_id, f"conversation.{act}", "conversation", cid, ctx.school_id)
    return await _conv_out(await db.conversations.find_one({"_id": c["_id"]}), side)


class ReportIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/conversations/{cid}/report")
async def report(cid: str, body: ReportIn, ctx: Ctx = Depends(school_ctx)):
    c = await db.conversations.find_one({"_id": oid(cid)})
    if not c:
        raise HTTPException(404, "Conversation not found")
    await _access(ctx, c)
    await db.conversations.update_one({"_id": c["_id"]}, {"$set": {"status": "escalated"}, "$push": {
        "reports": {"by": ctx.user_id, "at": now_utc(), "reason": sanitize(body.reason)}}})
    await audit(ctx.user_id, "conversation.report", "conversation", cid, ctx.school_id)
    return {"ok": True}


class TemplateIn(BaseModel):
    title: str = Field(min_length=2, max_length=60)
    body: str = Field(min_length=2, max_length=1000)


@router.get("/messaging/templates")
async def templates(ctx: Ctx = Depends(school_ctx)):
    ctx.need("teacher.workspace")
    items = await db.message_templates.find({"school_id": ctx.school_id, "user_id": ctx.user_id}).sort("title", 1).to_list(50)
    return {"items": [out(x) for x in items]}


@router.post("/messaging/templates", status_code=201)
async def add_template(body: TemplateIn, ctx: Ctx = Depends(school_ctx)):
    ctx.need("teacher.workspace")
    if await db.message_templates.count_documents({"school_id": ctx.school_id, "user_id": ctx.user_id}) >= 30:
        raise HTTPException(400, "You can save up to 30 templates")
    doc = {"school_id": ctx.school_id, "user_id": ctx.user_id, "title": sanitize(body.title), "body": sanitize(body.body),
           "created_at": now_utc()}
    r = await db.message_templates.insert_one(doc)
    return out({**doc, "_id": r.inserted_id})


@router.post("/messaging/availability")
async def availability(status: Literal["available", "busy", "away"], ctx: Ctx = Depends(school_ctx)):
    ctx.need("teacher.workspace")
    t = await _my_teacher(ctx)
    if not t:
        raise HTTPException(404, "No staff profile linked")
    await db.teachers.update_one({"_id": t["_id"]}, {"$set": {"availability": status}})
    return {"availability": status}


@router.post("/messaging/attachments", status_code=201)
async def upload(file: UploadFile = File(...), ctx: Ctx = Depends(school_ctx)):
    if ctx.role not in ("parent", "teacher"):
        raise HTTPException(403, "Not permitted")
    ctype = file.content_type or ""
    if ctype not in ATTACH_TYPES:
        raise HTTPException(400, "Only PDF, JPG, PNG or WEBP files are allowed")
    data = await file.read()
    if len(data) > ATTACH_MAX:
        raise HTTPException(413, "Attachment must be under 10 MB")
    path = f"{storage.APP_NAME}/schools/{ctx.school_id}/messages/{uuid.uuid4().hex}.{ATTACH_TYPES[ctype]}"
    try:
        res = await run_in_threadpool(storage.put_object, path, data, ctype)
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "Storage is unavailable. Please try again later.")
    r = await db.files.insert_one({"school_id": ctx.school_id, "storage_path": res["path"], "content_type": ctype,
                                   "size": len(data), "original_name": (file.filename or "attachment")[:120],
                                   "purpose": "message", "visibility": "private", "uploaded_by": ctx.user_id,
                                   "is_deleted": False, "created_at": now_utc()})
    return {"id": str(r.inserted_id), "name": file.filename, "content_type": ctype, "size": len(data)}


async def can_read_message_file(user_id: str, role: str, f: dict) -> bool:
    """Only current participants of a conversation whose message references the file (or leaders if escalated)."""
    if f.get("uploaded_by") == user_id:
        return True
    m = await db.messages.find_one({"school_id": f["school_id"], "attachments": str(f["_id"])})
    if not m:
        return False
    c = await db.conversations.find_one({"_id": oid(m["conversation_id"])})
    u = await db.users.find_one({"_id": oid(user_id)})
    from core import PERMISSIONS
    ctx = Ctx(user=u, user_id=user_id, school_id=f["school_id"], role=role, perms=PERMISSIONS.get(role, set()))
    try:
        await _access(ctx, c)
        return True
    except HTTPException:
        return False
