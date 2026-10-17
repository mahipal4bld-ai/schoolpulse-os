"""Milestone 3 — Module 1: School notices & announcements (targeting, scheduling IST, revisions, read vs acknowledge)."""
import html
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import storage
from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_directory import _parent_links
from routes_homework import ATTACH_MAX, ATTACH_TYPES

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
Category = Literal["general", "circular", "class", "academic", "holiday", "exam", "fee", "emergency", "event"]
Priority = Literal["normal", "important", "urgent"]
_TAG = re.compile(r"<[^>]*>")


def sanitize(text: str) -> str:
    """Notices are stored as plain text (+ **bold** / line breaks rendered client-side). All HTML is stripped."""
    return _TAG.sub("", html.unescape(text or "")).replace("\x00", "").strip()


class Audience(BaseModel):
    scope: Literal["school", "classes", "sections"] = "school"
    class_names: list[str] = Field(default_factory=list, max_length=30)
    section_ids: list[str] = Field(default_factory=list, max_length=100)


class NoticeIn(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    body: str = Field(min_length=1, max_length=5000)
    category: Category = "general"
    priority: Priority = "normal"
    audience: Audience = Audience()
    attachments: list[str] = Field(default_factory=list, max_length=5)
    publish_at: Optional[datetime] = None  # naive values are interpreted as IST
    expires_at: Optional[datetime] = None
    requires_ack: Optional[bool] = None
    action: Literal["draft", "review", "publish"] = "draft"


class NoticePatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=140)
    body: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    priority: Optional[Priority] = None
    expires_at: Optional[datetime] = None
    reason: Optional[str] = Field(default=None, max_length=200)


def _ist(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=IST)).astimezone(timezone.utc)


async def _promote(school_id: str):
    """Lazy state machine: scheduled -> published at publish_at; published -> archived at expires_at."""
    t = now_utc()
    await db.notices.update_many({"school_id": school_id, "status": "scheduled", "publish_at": {"$lte": t}},
                                 [{"$set": {"status": "published", "published_at": "$publish_at"}}])
    await db.notices.update_many({"school_id": school_id, "status": "published", "expires_at": {"$ne": None, "$lte": t}},
                                 {"$set": {"status": "archived", "archived_at": t}})


async def _validate_audience(ctx: Ctx, a: Audience) -> dict:
    if a.scope == "sections":
        if not a.section_ids:
            raise HTTPException(400, "Choose at least one section")
        n = await db.sections.count_documents({"_id": {"$in": [oid(s) for s in a.section_ids]}, "school_id": ctx.school_id})
        if n != len(set(a.section_ids)):
            raise HTTPException(400, "Audience includes sections outside this school")
    if a.scope == "classes":
        if not a.class_names:
            raise HTTPException(400, "Choose at least one class")
        have = set(await db.sections.distinct("class_name", {"school_id": ctx.school_id}))
        if not set(a.class_names) <= have:
            raise HTTPException(400, "Audience includes classes that do not exist")
    return {"scope": a.scope, "class_names": a.class_names if a.scope == "classes" else [],
            "section_ids": list(dict.fromkeys(a.section_ids)) if a.scope == "sections" else []}


async def audience_sections(n: dict) -> list[str]:
    a = n["audience"]
    if a["scope"] == "school":
        return await db.sections.distinct("_id", {"school_id": n["school_id"]})
    if a["scope"] == "classes":
        return await db.sections.distinct("_id", {"school_id": n["school_id"], "class_name": {"$in": a["class_names"]}})
    return [oid(s) for s in a["section_ids"]]


async def audience_parent_users(n: dict) -> set[str]:
    """Verified guardian user accounts with an active child in the audience (denominator for read/ack rates)."""
    secs = [str(s) for s in await audience_sections(n)]
    studs = [str(s["_id"]) for s in await db.students.find({"school_id": n["school_id"], "section_id": {"$in": secs},
                                                            "status": "active"}, {"_id": 1}).to_list(5000)]
    gids = await db.guardian_links.distinct("guardian_id", {"student_id": {"$in": studs}, "verified": True})
    users = await db.guardians.distinct("user_id", {"_id": {"$in": [oid(g) for g in gids]}, "user_id": {"$ne": None}})
    active = await db.memberships.distinct("user_id", {"school_id": n["school_id"], "role": "parent", "status": "active",
                                                       "user_id": {"$in": users}})
    return set(active)


async def _check_files(ctx: Ctx, ids: list[str]):
    for fid in ids:
        if not await db.files.find_one({"_id": oid(fid), "school_id": ctx.school_id, "purpose": "notice", "is_deleted": False}):
            raise HTTPException(400, "Attachment not found")


async def _files(ids: list[str]) -> list[dict]:
    fs = await db.files.find({"_id": {"$in": [oid(f) for f in ids]}, "is_deleted": False}).to_list(10)
    return [{"id": str(f["_id"]), "name": f.get("original_name") or "attachment", "content_type": f["content_type"],
             "size": f["size"]} for f in fs]


async def _out(n: dict, staff: bool) -> dict:
    o = out(n)
    o["attachments"] = await _files(n.get("attachments", []))
    if not staff:
        for k in ("revisions", "created_by", "audience", "status_history"):
            o.pop(k, None)
    else:
        o["revision_count"] = len(n.get("revisions", []))
        o.pop("revisions", None)
    return o


@router.post("/notices/attachments", status_code=201)
async def upload(file: UploadFile = File(...), ctx: Ctx = Depends(need("notices.manage"))):
    ctype = file.content_type or ""
    if ctype not in ATTACH_TYPES:
        raise HTTPException(400, "Only PDF, JPG, PNG or WEBP files are allowed")
    data = await file.read()
    if len(data) > ATTACH_MAX:
        raise HTTPException(413, "Attachment must be under 10 MB")
    path = f"{storage.APP_NAME}/schools/{ctx.school_id}/notices/{uuid.uuid4().hex}.{ATTACH_TYPES[ctype]}"
    try:
        res = await run_in_threadpool(storage.put_object, path, data, ctype)
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "Storage is unavailable. Please try again later.")
    r = await db.files.insert_one({"school_id": ctx.school_id, "storage_path": res["path"], "content_type": ctype,
                                   "size": len(data), "original_name": (file.filename or "attachment")[:120],
                                   "purpose": "notice", "visibility": "private", "uploaded_by": ctx.user_id,
                                   "is_deleted": False, "created_at": now_utc()})
    return {"id": str(r.inserted_id), "name": file.filename, "content_type": ctype, "size": len(data)}


@router.post("/notices", status_code=201)
async def create(body: NoticeIn, ctx: Ctx = Depends(need("notices.manage"))):
    aud = await _validate_audience(ctx, body.audience)
    await _check_files(ctx, body.attachments)
    pub, exp, t = _ist(body.publish_at), _ist(body.expires_at), now_utc()
    if exp and exp <= (pub or t):
        raise HTTPException(400, "Expiry must be after the publish time")
    status = {"draft": "draft", "review": "review"}.get(body.action) or ("scheduled" if pub and pub > t else "published")
    doc = {"school_id": ctx.school_id, "title": sanitize(body.title), "body": sanitize(body.body), "category": body.category,
           "priority": body.priority, "audience": aud, "attachments": body.attachments,
           "requires_ack": body.requires_ack if body.requires_ack is not None else body.priority != "normal",
           "status": status, "publish_at": pub, "expires_at": exp,
           "published_at": t if status == "published" else None, "created_by": ctx.user_id, "created_at": t,
           "updated_at": t, "revisions": [], "status_history": [{"status": status, "by": ctx.user_id, "at": t}]}
    if not doc["title"] or not doc["body"]:
        raise HTTPException(400, "Title and message cannot be empty")
    r = await db.notices.insert_one(doc)
    await audit(ctx.user_id, f"notice.{status}", "notice", str(r.inserted_id), ctx.school_id, {"priority": body.priority})
    return await _out({**doc, "_id": r.inserted_id}, True)


async def _get(ctx: Ctx, nid: str) -> dict:
    n = await db.notices.find_one({"_id": oid(nid), "school_id": ctx.school_id})
    if not n:
        raise HTTPException(404, "Notice not found")
    return n


@router.patch("/notices/{nid}")
async def edit(nid: str, body: NoticePatch, ctx: Ctx = Depends(need("notices.manage"))):
    n = await _get(ctx, nid)
    if n["status"] in ("archived", "cancelled"):
        raise HTTPException(400, f"A {n['status']} notice cannot be edited")
    data = body.model_dump(exclude_none=True, exclude={"reason"})
    for k in ("title", "body"):
        if k in data:
            data[k] = sanitize(data[k])
    if "expires_at" in data:
        data["expires_at"] = _ist(data["expires_at"])
    if not data:
        raise HTTPException(400, "No changes supplied")
    if n["status"] == "published" and not (body.reason or "").strip():
        raise HTTPException(400, "Give a reason for editing a published notice")
    rev = {"at": now_utc(), "by": ctx.user_id, "title": n["title"], "body": n["body"], "priority": n["priority"],
           "reason": (body.reason or "").strip() or None}
    await db.notices.update_one({"_id": n["_id"]}, {"$set": {**data, "updated_at": now_utc()}, "$push": {"revisions": rev}})
    await audit(ctx.user_id, "notice.edit", "notice", nid, ctx.school_id, {"fields": list(data), "was": n["status"]})
    return await _out(await db.notices.find_one({"_id": n["_id"]}), True)


@router.post("/notices/{nid}/action")
async def action(nid: str, act: Literal["submit_review", "publish", "archive", "cancel"], ctx: Ctx = Depends(need("notices.manage"))):
    n = await _get(ctx, nid)
    allowed = {"submit_review": {"draft"}, "publish": {"draft", "review", "scheduled"},
               "archive": {"published"}, "cancel": {"draft", "review", "scheduled", "published"}}
    if n["status"] not in allowed[act]:
        raise HTTPException(409, f"Cannot {act.replace('_', ' ')} a {n['status']} notice")
    new = {"submit_review": "review", "publish": "published", "archive": "archived", "cancel": "cancelled"}[act]
    t = now_utc()
    st = {"status": new, "updated_at": t, **({"published_at": t} if new == "published" else {})}
    await db.notices.update_one({"_id": n["_id"], "status": n["status"]},
                                {"$set": st, "$push": {"status_history": {"status": new, "by": ctx.user_id, "at": t}}})
    await audit(ctx.user_id, f"notice.{new}", "notice", nid, ctx.school_id)
    return await _out(await db.notices.find_one({"_id": n["_id"]}), True)


@router.get("/notices")
async def list_staff(status: Optional[str] = None, ctx: Ctx = Depends(need("notices.manage"))):
    await _promote(ctx.school_id)
    filt = {"school_id": ctx.school_id, **({"status": status} if status else {})}
    items = await db.notices.find(filt).sort("updated_at", -1).to_list(100)
    return {"items": [await _out(n, True) for n in items]}


@router.get("/notices/{nid}")
async def get_staff(nid: str, ctx: Ctx = Depends(need("notices.manage"))):
    await _promote(ctx.school_id)
    n = await _get(ctx, nid)
    o = await _out(n, True)
    o["audience"] = n["audience"]
    o["revisions"] = [{**r, "at": r["at"].isoformat()} for r in n.get("revisions", [])]
    if n["status"] in ("published", "archived"):
        users = await audience_parent_users(n)
        rec = await db.notice_receipts.find({"notice_id": nid}).to_list(10000)
        o["stats"] = {"audience": len(users), "read": sum(1 for r in rec if r.get("read_at") and r["user_id"] in users),
                      "acknowledged": sum(1 for r in rec if r.get("ack_at") and r["user_id"] in users)}
    return o


# ---------------------------------------------------------------- parent
async def _parent_scope(ctx: Ctx) -> tuple[set, set]:
    kids = [lk["student_id"] for lk in await _parent_links(ctx)]
    studs = await db.students.find({"_id": {"$in": [oid(k) for k in kids]}, "school_id": ctx.school_id,
                                    "status": "active"}).to_list(20)
    secs = {s["section_id"] for s in studs}
    classes = set(await db.sections.distinct("class_name", {"_id": {"$in": [oid(s) for s in secs]}}))
    return secs, classes


def _parent_filter(ctx: Ctx, secs: set, classes: set) -> dict:
    return {"school_id": ctx.school_id, "status": "published",
            "$or": [{"audience.scope": "school"}, {"audience.scope": "classes", "audience.class_names": {"$in": list(classes)}},
                    {"audience.scope": "sections", "audience.section_ids": {"$in": list(secs)}}]}


async def parent_can_see_notice(ctx: Ctx, nid: str) -> dict:
    secs, classes = await _parent_scope(ctx)
    if not secs:
        raise HTTPException(404, "Notice not found")
    n = await db.notices.find_one({"_id": oid(nid), **_parent_filter(ctx, secs, classes)})
    if not n:
        raise HTTPException(404, "Notice not found")
    return n


@router.get("/parent/notices")
async def parent_list(ctx: Ctx = Depends(need("parent.portal"))):
    await _promote(ctx.school_id)
    secs, classes = await _parent_scope(ctx)
    if not secs:
        return {"items": [], "unread": 0}
    items = await db.notices.find(_parent_filter(ctx, secs, classes)).sort([("published_at", -1)]).to_list(100)
    rec = {r["notice_id"]: r async for r in db.notice_receipts.find({"user_id": ctx.user_id, "school_id": ctx.school_id})}
    res = []
    for n in items:
        o = await _out(n, False)
        r = rec.get(str(n["_id"]), {})
        o["read"], o["acknowledged"] = bool(r.get("read_at")), bool(r.get("ack_at"))
        res.append(o)
    return {"items": res, "unread": sum(1 for x in res if not x["read"])}


@router.post("/parent/notices/{nid}/read")
async def mark_read(nid: str, ctx: Ctx = Depends(need("parent.portal"))):
    await parent_can_see_notice(ctx, nid)
    await db.notice_receipts.update_one({"notice_id": nid, "user_id": ctx.user_id},
                                        {"$setOnInsert": {"school_id": ctx.school_id, "read_at": now_utc(), "ack_at": None}},
                                        upsert=True)
    return {"ok": True}


@router.post("/parent/notices/{nid}/ack")
async def acknowledge(nid: str, ctx: Ctx = Depends(need("parent.portal"))):
    n = await parent_can_see_notice(ctx, nid)
    if not n.get("requires_ack"):
        raise HTTPException(400, "This notice does not need an acknowledgement")
    t = now_utc()
    await db.notice_receipts.update_one({"notice_id": nid, "user_id": ctx.user_id},
                                        {"$setOnInsert": {"school_id": ctx.school_id, "read_at": t}}, upsert=True)
    r = await db.notice_receipts.update_one({"notice_id": nid, "user_id": ctx.user_id, "ack_at": None}, {"$set": {"ack_at": t}})
    if r.modified_count:
        await audit(ctx.user_id, "notice.acknowledge", "notice", nid, ctx.school_id)
    return {"ok": True}
