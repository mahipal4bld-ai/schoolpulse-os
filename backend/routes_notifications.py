"""Durable in-app notification records (Milestone 3 Module 8 will build the full centre on top of this)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from core import Ctx, db, now_utc, oid, out, school_ctx

router = APIRouter()


async def notify(school_id: str, user_id: Optional[str], type_: str, title: str, body: str, entity: str,
                 entity_id: str, dedupe: Optional[str] = None):
    """Insert one in-app notification. `dedupe` makes the write idempotent per user (e.g. reminders)."""
    if not user_id:
        return
    doc = {"school_id": school_id, "user_id": user_id, "type": type_, "title": title[:140], "body": body[:400],
           "entity": entity, "entity_id": entity_id, "read_at": None, "created_at": now_utc(), "channel": "in_app"}
    if dedupe:
        doc["dedupe"] = dedupe
    try:
        await db.notifications.insert_one(doc)
    except DuplicateKeyError:
        pass


@router.get("/notifications")
async def list_notifications(limit: int = Query(default=30, ge=1, le=100), before: Optional[str] = None,
                             ctx: Ctx = Depends(school_ctx)):
    if ctx.role == "parent":
        from routes_ptm import ensure_reminders
        await ensure_reminders(ctx)
    filt: dict = {"school_id": ctx.school_id, "user_id": ctx.user_id}
    if before:
        filt["_id"] = {"$lt": oid(before)}
    items = await db.notifications.find(filt).sort("_id", -1).limit(limit + 1).to_list(limit + 1)
    more = len(items) > limit
    items = items[:limit]
    unread = await db.notifications.count_documents({"school_id": ctx.school_id, "user_id": ctx.user_id, "read_at": None})
    return {"items": [out(n) for n in items], "unread": unread, "next_cursor": str(items[-1]["_id"]) if more else None}


@router.post("/notifications/{nid}/read")
async def read_one(nid: str, ctx: Ctx = Depends(school_ctx)):
    r = await db.notifications.update_one({"_id": oid(nid), "school_id": ctx.school_id, "user_id": ctx.user_id},
                                          [{"$set": {"read_at": {"$ifNull": ["$read_at", now_utc()]}}}])
    if not r.matched_count:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


@router.post("/notifications/read-all")
async def read_all(ctx: Ctx = Depends(school_ctx)):
    r = await db.notifications.update_many({"school_id": ctx.school_id, "user_id": ctx.user_id, "read_at": None},
                                           {"$set": {"read_at": now_utc()}})
    return {"updated": r.modified_count}
