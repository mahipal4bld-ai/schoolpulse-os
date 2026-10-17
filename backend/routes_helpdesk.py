"""Milestone 3 — Module 5: Parent help desk & request management.

Parents raise requests about a verified child; staff triage, assign, reply (public) or add internal notes, and move the
request through a validated lifecycle. Every transition is a conditional update on the current status (no lost updates),
creation is idempotent per (guardian, client_id), and access is re-checked against live data on every request.
"""
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx
from routes_directory import _parent_links
from routes_notices import sanitize
from routes_notifications import notify

router = APIRouter()
Category = Literal["fees", "transport", "academics", "documents", "uniform_books", "technical", "other"]
Status = Literal["open", "assigned", "in_progress", "waiting_on_parent", "resolved", "closed"]
SLA_HOURS = {"urgent": 4, "high": 24, "normal": 48}
ROUTE = {"fees": "accountant", "transport": "school_admin", "documents": "school_admin", "uniform_books": "school_admin",
         "technical": "school_admin", "other": "school_admin"}  # academics -> the section's class teacher
STAFF_ROLES = {"owner", "principal", "school_admin", "accountant", "teacher"}
REOPEN_DAYS = 7
# who may move a ticket from -> to
STAFF_MOVES = {"open": {"in_progress", "resolved", "closed"}, "assigned": {"in_progress", "resolved", "closed"},
               "in_progress": {"waiting_on_parent", "resolved"}, "waiting_on_parent": {"in_progress", "resolved"},
               "resolved": {"closed", "in_progress"}}
PARENT_MOVES = {"open": {"closed"}, "assigned": {"closed"}, "resolved": {"in_progress", "closed"}}


class TicketIn(BaseModel):
    student_id: str
    category: Category
    subject: str = Field(min_length=4, max_length=120)
    body: str = Field(min_length=10, max_length=3000)
    priority: Literal["normal", "high"] = "normal"
    client_id: str = Field(min_length=8, max_length=64)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    internal: bool = False
    client_id: str = Field(min_length=8, max_length=64)


class MoveIn(BaseModel):
    status: Status
    note: str = Field(default="", max_length=500)


class TriageIn(BaseModel):
    priority: Optional[Literal["normal", "high", "urgent"]] = None
    category: Optional[Category] = None
    assignee_user_id: Optional[str] = None


class RateIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


def _hist(ctx: Ctx, action: str, **kw) -> dict:
    return {"at": now_utc(), "by": ctx.user_id, "role": ctx.role, "action": action, **kw}


async def _staff_member(school_id: str, user_id: str) -> Optional[dict]:
    return await db.memberships.find_one({"school_id": school_id, "user_id": user_id, "status": "active", "role": {"$in": list(STAFF_ROLES)}})


async def _route(school_id: str, category: str, section_id: str) -> Optional[str]:
    if category == "academics":
        sec = await db.sections.find_one({"_id": oid(section_id)}, {"class_teacher_id": 1})
        t = sec and sec.get("class_teacher_id") and await db.teachers.find_one({"_id": oid(sec["class_teacher_id"]), "status": "active"})
        return t["user_id"] if t and t.get("user_id") and await _staff_member(school_id, t["user_id"]) else None
    m = await db.memberships.find_one({"school_id": school_id, "role": ROUTE[category], "status": "active"}, sort=[("created_at", 1)])
    return m["user_id"] if m else None


async def _access(ctx: Ctx, t: dict) -> str:
    """'parent' | 'manager' | 'assignee' — or 404 so ticket existence never leaks."""
    if ctx.role == "parent":
        if t["guardian_user_id"] == ctx.user_id and t["student_id"] in {lk["student_id"] for lk in await _parent_links(ctx)}:
            return "parent"
    elif "helpdesk.manage" in ctx.perms:
        return "manager"
    elif ctx.role in STAFF_ROLES and t.get("assignee_user_id") == ctx.user_id:
        return "assignee"
    raise HTTPException(404, "Request not found")


async def _get(ctx: Ctx, tid: str) -> tuple[dict, str]:
    t = await db.tickets.find_one({"_id": oid(tid), "school_id": ctx.school_id})
    if not t:
        raise HTTPException(404, "Request not found")
    return t, await _access(ctx, t)


async def _names(ids) -> dict:
    ids = [i for i in set(ids) if i]
    return {str(u["_id"]): u["name"] for u in await db.users.find({"_id": {"$in": [oid(i) for i in ids]}}, {"name": 1}).to_list(len(ids) or 1)}


def _overdue(t: dict) -> bool:
    due = t.get("sla_due_at")
    if not due or t["status"] in ("resolved", "closed"):
        return False
    return (due if due.tzinfo else due.replace(tzinfo=now_utc().tzinfo)) < now_utc()


async def _ticket_out(t: dict, side: str, names: Optional[dict] = None) -> dict:
    o = out(t)
    names = names if names is not None else await _names([t.get("assignee_user_id"), t["guardian_user_id"]])
    st = await db.students.find_one({"_id": oid(t["student_id"])}, {"first_name": 1, "last_name": 1})
    o.update({"student_name": f"{st['first_name']} {st['last_name']}" if st else "—", "overdue": _overdue(t),
              "assignee_name": names.get(t.get("assignee_user_id") or "", None)})
    o.pop("client_id", None)
    if side == "parent":
        for k in ("assignee_user_id", "history", "internal_count"):
            o.pop(k, None)
        o["history"] = [{"at": h["at"], "action": h["action"], **({"to": h["to"]} if "to" in h else {})} for h in t.get("history", [])]
    else:
        o["guardian_name"] = names.get(t["guardian_user_id"], "—")
        o["history"] = [{**h, "by_name": None} for h in t.get("history", [])]
    if side != "parent" or t["status"] == "resolved":
        res = t.get("resolved_at")
        o["can_reopen"] = side == "parent" and t["status"] == "resolved" and res is not None and \
            (res if res.tzinfo else res.replace(tzinfo=now_utc().tzinfo)) > now_utc() - timedelta(days=REOPEN_DAYS)
    return o


# ---------------------------------------------------------------- parent: create
@router.post("/helpdesk/tickets", status_code=201)
async def create(body: TicketIn, ctx: Ctx = Depends(need("parent.portal"))):
    prior = await db.tickets.find_one({"guardian_user_id": ctx.user_id, "client_id": body.client_id, "school_id": ctx.school_id})
    if prior:
        return await _ticket_out(prior, "parent")
    links = [lk for lk in await _parent_links(ctx) if lk["student_id"] == body.student_id]
    st = links and await db.students.find_one({"_id": oid(body.student_id), "school_id": ctx.school_id, "status": "active"})
    if not st:
        raise HTTPException(404, "Child not found")
    if await db.tickets.count_documents({"school_id": ctx.school_id, "guardian_user_id": ctx.user_id,
                                         "created_at": {"$gt": now_utc() - timedelta(hours=1)}}) >= 5:
        raise HTTPException(429, "You've raised several requests in the last hour. Please wait before raising another.")
    seq = await db.counters.find_one_and_update({"_id": f"ticket:{ctx.school_id}"}, {"$inc": {"n": 1}}, upsert=True,
                                                return_document=ReturnDocument.AFTER)
    t = now_utc()
    assignee = await _route(ctx.school_id, body.category, st["section_id"])
    doc = {"school_id": ctx.school_id, "number": seq["n"], "guardian_user_id": ctx.user_id, "student_id": body.student_id,
           "section_id": st["section_id"], "class_name": st["class_name"], "category": body.category,
           "subject": sanitize(body.subject), "body": sanitize(body.body), "priority": body.priority,
           "status": "assigned" if assignee else "open", "assignee_user_id": assignee,
           "sla_due_at": t + timedelta(hours=SLA_HOURS[body.priority]), "first_response_at": None, "resolved_at": None,
           "closed_at": None, "reopen_count": 0, "rating": None, "client_id": body.client_id, "last_activity_at": t,
           "created_at": t, "updated_at": t, "unread_parent": 0, "unread_staff": 1,
           "history": [_hist(ctx, "created"), *([{"at": t, "by": "system", "role": "system", "action": "auto_assigned", "to": assignee}] if assignee else [])]}
    if len(doc["subject"]) < 4 or len(doc["body"]) < 10:
        raise HTTPException(400, "Please describe your request in a little more detail")
    try:
        r = await db.tickets.insert_one(doc)
    except DuplicateKeyError:
        return await _ticket_out(await db.tickets.find_one({"guardian_user_id": ctx.user_id, "client_id": body.client_id}), "parent")
    await audit(ctx.user_id, "helpdesk.create", "ticket", str(r.inserted_id), ctx.school_id, {"category": body.category})
    await notify(ctx.school_id, assignee, "helpdesk.assigned", f"New help desk request #{doc['number']}", doc["subject"], "ticket", str(r.inserted_id))
    return await _ticket_out({**doc, "_id": r.inserted_id}, "parent")


# ---------------------------------------------------------------- lists & detail
@router.get("/helpdesk/tickets")
async def list_tickets(view: Literal["active", "mine", "overdue", "unassigned", "done", "all"] = "active",
                       category: Optional[Category] = None, limit: int = Query(default=30, ge=1, le=100),
                       before: Optional[str] = None, ctx: Ctx = Depends(school_ctx)):
    filt: dict = {"school_id": ctx.school_id}
    if ctx.role == "parent":
        filt.update({"guardian_user_id": ctx.user_id, "student_id": {"$in": [lk["student_id"] for lk in await _parent_links(ctx)]}})
        side = "parent"
    elif "helpdesk.manage" in ctx.perms:
        side = "manager"
        if view == "mine":
            filt["assignee_user_id"] = ctx.user_id
    elif ctx.role in STAFF_ROLES:
        side = "assignee"
        filt["assignee_user_id"] = ctx.user_id
    else:
        raise HTTPException(403, f"Your role ({ctx.role}) is not permitted to perform this action")
    if view in ("active", "mine", "overdue", "unassigned"):
        filt["status"] = {"$nin": ["resolved", "closed"]}
    elif view == "done":
        filt["status"] = {"$in": ["resolved", "closed"]}
    if view == "overdue":
        filt["sla_due_at"] = {"$lt": now_utc()}
    if view == "unassigned":
        filt["assignee_user_id"] = None
    if category:
        filt["category"] = category
    if before:
        filt["_id"] = {"$lt": oid(before)}
    items = await db.tickets.find(filt).sort("_id", -1).limit(limit + 1).to_list(limit + 1)
    more = len(items) > limit
    items = items[:limit]
    names = await _names([x.get("assignee_user_id") for x in items] + [x["guardian_user_id"] for x in items])
    return {"items": [await _ticket_out(x, side, names) for x in items], "next_cursor": str(items[-1]["_id"]) if more else None}


@router.get("/helpdesk/tickets/{tid}")
async def detail(tid: str, ctx: Ctx = Depends(school_ctx)):
    t, side = await _get(ctx, tid)
    mf = {"ticket_id": tid, **({"internal": False} if side == "parent" else {})}
    msgs = await db.ticket_messages.find(mf).sort("_id", 1).to_list(500)
    names = await _names([m["author_user_id"] for m in msgs] + [t.get("assignee_user_id"), t["guardian_user_id"]])
    await db.tickets.update_one({"_id": t["_id"]}, {"$set": {"unread_parent" if side == "parent" else "unread_staff": 0}})
    o = await _ticket_out(t, side, names)
    o["messages"] = [{"id": str(m["_id"]), "body": m["body"], "internal": m["internal"], "side": m["side"], "created_at": m["created_at"],
                      "author_name": names.get(m["author_user_id"], "—") if m["side"] == "parent" or side != "parent" else "School office",
                      "mine": m["author_user_id"] == ctx.user_id} for m in msgs]
    o["side"] = side
    return o


# ---------------------------------------------------------------- replies
@router.post("/helpdesk/tickets/{tid}/messages", status_code=201)
async def reply(tid: str, body: ReplyIn, ctx: Ctx = Depends(school_ctx)):
    t, side = await _get(ctx, tid)
    dup = await db.ticket_messages.find_one({"ticket_id": tid, "client_id": body.client_id, "author_user_id": ctx.user_id})
    if dup:
        return {"id": str(dup["_id"]), "duplicate": True}
    if side == "parent" and body.internal:
        raise HTTPException(403, "Parents cannot add internal notes")
    if t["status"] == "closed":
        raise HTTPException(409, "This request is closed. Please raise a new one.")
    text = sanitize(body.body)
    if not text:
        raise HTTPException(400, "Message cannot be empty")
    if await db.ticket_messages.count_documents({"author_user_id": ctx.user_id, "created_at": {"$gt": now_utc() - timedelta(minutes=10)}}) >= 20:
        raise HTTPException(429, "You're sending messages too quickly. Please wait a few minutes.")
    t0 = now_utc()
    try:
        r = await db.ticket_messages.insert_one({"school_id": ctx.school_id, "ticket_id": tid, "author_user_id": ctx.user_id,
                                                 "side": "parent" if side == "parent" else "staff", "internal": body.internal,
                                                 "body": text, "client_id": body.client_id, "created_at": t0})
    except DuplicateKeyError:
        return {"id": None, "duplicate": True}
    upd: dict = {"last_activity_at": t0, "updated_at": t0}
    inc: dict = {}
    if side == "parent":
        inc["unread_staff"] = 1
        if t["status"] == "waiting_on_parent":  # parent answered: back to the school
            await db.tickets.update_one({"_id": t["_id"], "status": "waiting_on_parent"},
                                        {"$set": {"status": "in_progress"}, "$push": {"history": _hist(ctx, "status", to="in_progress", auto=True)}})
        await notify(ctx.school_id, t.get("assignee_user_id"), "helpdesk.parent_reply", f"Parent replied on #{t['number']}", text[:120], "ticket", tid)
    elif not body.internal:
        inc["unread_parent"] = 1
        if not t.get("first_response_at"):
            upd["first_response_at"] = t0
        if t["status"] in ("open", "assigned"):
            await db.tickets.update_one({"_id": t["_id"], "status": t["status"]},
                                        {"$set": {"status": "in_progress"}, "$push": {"history": _hist(ctx, "status", to="in_progress", auto=True)}})
        await notify(ctx.school_id, t["guardian_user_id"], "helpdesk.reply", f"Reply on your request #{t['number']}", text[:120], "ticket", tid)
    await db.tickets.update_one({"_id": t["_id"]}, {"$set": upd, **({"$inc": inc} if inc else {})})
    await audit(ctx.user_id, "helpdesk.internal_note" if body.internal else "helpdesk.reply", "ticket", tid, ctx.school_id)
    return {"id": str(r.inserted_id), "duplicate": False}


# ---------------------------------------------------------------- lifecycle
@router.post("/helpdesk/tickets/{tid}/status")
async def move(tid: str, body: MoveIn, ctx: Ctx = Depends(school_ctx)):
    t, side = await _get(ctx, tid)
    cur, to = t["status"], body.status
    allowed = PARENT_MOVES if side == "parent" else STAFF_MOVES
    if to not in allowed.get(cur, set()):
        raise HTTPException(409, f"A {cur.replace('_', ' ')} request cannot be moved to {to.replace('_', ' ')}")
    if side == "assignee" and to == "closed":
        raise HTTPException(403, "Only the school office can close requests directly")
    note = sanitize(body.note)
    if side != "parent" and to in ("waiting_on_parent", "resolved") and not note:
        raise HTTPException(400, "Add a short note for the parent")
    t0 = now_utc()
    st: dict = {"status": to, "updated_at": t0, "last_activity_at": t0}
    inc: dict = {}
    if to == "resolved":
        st["resolved_at"] = t0
    if to == "closed":
        st["closed_at"] = t0
    if side == "parent" and cur == "resolved" and to == "in_progress":
        res = t.get("resolved_at")
        if not res or (res if res.tzinfo else res.replace(tzinfo=t0.tzinfo)) < t0 - timedelta(days=REOPEN_DAYS):
            raise HTTPException(409, f"Requests can be reopened within {REOPEN_DAYS} days of being resolved. Please raise a new one.")
        if not note:
            raise HTTPException(400, "Tell the school what is still unresolved")
        inc["reopen_count"] = 1
        st["resolved_at"] = None
        st["sla_due_at"] = t0 + timedelta(hours=SLA_HOURS[t["priority"]])
    r = await db.tickets.find_one_and_update(
        {"_id": t["_id"], "status": cur},
        {"$set": st, **({"$inc": inc} if inc else {}), "$push": {"history": _hist(ctx, "status", to=to, note=note or None)}},
        return_document=ReturnDocument.AFTER)
    if not r:
        raise HTTPException(409, "This request was updated by someone else. Refresh and try again.")
    if note:
        await db.ticket_messages.insert_one({"school_id": ctx.school_id, "ticket_id": tid, "author_user_id": ctx.user_id,
                                             "side": "parent" if side == "parent" else "staff", "internal": False, "body": note,
                                             "client_id": f"status:{t0.timestamp()}:{to}", "created_at": t0})
        if side != "parent" and not t.get("first_response_at"):
            await db.tickets.update_one({"_id": t["_id"]}, {"$set": {"first_response_at": t0}})
    await audit(ctx.user_id, f"helpdesk.{to}", "ticket", tid, ctx.school_id, {"from": cur})
    if side == "parent":
        await notify(ctx.school_id, t.get("assignee_user_id"), "helpdesk.status", f"Request #{t['number']} {('reopened' if to == 'in_progress' else to.replace('_', ' '))} by parent", note[:120], "ticket", tid)
    elif to in ("waiting_on_parent", "resolved", "closed"):
        label = {"waiting_on_parent": "needs your reply", "resolved": "was resolved", "closed": "was closed"}[to]
        await notify(ctx.school_id, t["guardian_user_id"], "helpdesk.status", f"Your request #{t['number']} {label}", note[:120], "ticket", tid)
    return await _ticket_out(r, side)


@router.post("/helpdesk/tickets/{tid}/triage")
async def triage(tid: str, body: TriageIn, ctx: Ctx = Depends(need("helpdesk.manage"))):
    t, _ = await _get(ctx, tid)
    if t["status"] == "closed":
        raise HTTPException(409, "Closed requests cannot be changed")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "No changes supplied")
    st: dict = {"updated_at": now_utc()}
    if data.get("priority"):
        st["priority"] = data["priority"]
        st["sla_due_at"] = t["created_at"] + timedelta(hours=SLA_HOURS[data["priority"]])
    if data.get("category"):
        st["category"] = data["category"]
    if "assignee_user_id" in data:
        uid = data["assignee_user_id"]
        if uid and not await _staff_member(ctx.school_id, uid):
            raise HTTPException(400, "Assign to an active staff member of this school")
        st["assignee_user_id"] = uid
        if t["status"] in ("open", "assigned"):
            st["status"] = "assigned" if uid else "open"
    r = await db.tickets.find_one_and_update({"_id": t["_id"], "status": t["status"]},
                                             {"$set": st, "$push": {"history": _hist(ctx, "triage", **{k: v for k, v in data.items()})}},
                                             return_document=ReturnDocument.AFTER)
    if not r:
        raise HTTPException(409, "This request was updated by someone else. Refresh and try again.")
    await audit(ctx.user_id, "helpdesk.triage", "ticket", tid, ctx.school_id, data)
    if data.get("assignee_user_id") and data["assignee_user_id"] != t.get("assignee_user_id"):
        await notify(ctx.school_id, data["assignee_user_id"], "helpdesk.assigned", f"Help desk request #{t['number']} assigned to you", t["subject"], "ticket", tid)
    return await _ticket_out(r, "manager")


@router.post("/helpdesk/tickets/{tid}/rate")
async def rate(tid: str, body: RateIn, ctx: Ctx = Depends(need("parent.portal"))):
    t, side = await _get(ctx, tid)
    r = await db.tickets.find_one_and_update(
        {"_id": t["_id"], "status": {"$in": ["resolved", "closed"]}, "rating": None},
        {"$set": {"rating": {"score": body.score, "comment": sanitize(body.comment), "at": now_utc()}}}, return_document=ReturnDocument.AFTER)
    if not r:
        raise HTTPException(409, "You can rate a request once, after it is resolved")
    await audit(ctx.user_id, "helpdesk.rate", "ticket", tid, ctx.school_id, {"score": body.score})
    return await _ticket_out(r, side)


# ---------------------------------------------------------------- staff helpers & insights
@router.get("/helpdesk/assignees")
async def assignees(ctx: Ctx = Depends(need("helpdesk.manage"))):
    ms = await db.memberships.find({"school_id": ctx.school_id, "status": "active", "role": {"$in": list(STAFF_ROLES)}}).to_list(500)
    names = await _names([m["user_id"] for m in ms])
    return {"items": sorted([{"user_id": m["user_id"], "name": names.get(m["user_id"], "—"), "role": m["role"]} for m in ms], key=lambda x: x["name"])}


@router.get("/helpdesk/insights")
async def insights(days: int = Query(default=30, ge=1, le=365), ctx: Ctx = Depends(need("helpdesk.manage"))):
    since = now_utc() - timedelta(days=days)
    base = {"school_id": ctx.school_id}
    open_f = {**base, "status": {"$nin": ["resolved", "closed"]}}
    by_status = {r["_id"]: r["n"] for r in await db.tickets.aggregate([{"$match": open_f}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(10)}
    by_cat = await db.tickets.aggregate([{"$match": {**base, "created_at": {"$gte": since}}}, {"$group": {"_id": "$category", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]).to_list(10)
    times = await db.tickets.aggregate([{"$match": {**base, "created_at": {"$gte": since}}}, {"$group": {
        "_id": None, "n": {"$sum": 1},
        "frt": {"$avg": {"$cond": [{"$ne": ["$first_response_at", None]}, {"$subtract": ["$first_response_at", "$created_at"]}, None]}},
        "res": {"$avg": {"$cond": [{"$ne": ["$resolved_at", None]}, {"$subtract": ["$resolved_at", "$created_at"]}, None]}},
        "resolved": {"$sum": {"$cond": [{"$in": ["$status", ["resolved", "closed"]]}, 1, 0]}},
        "reopened": {"$sum": {"$cond": [{"$gt": ["$reopen_count", 0]}, 1, 0]}},
        "csat": {"$avg": "$rating.score"}, "rated": {"$sum": {"$cond": [{"$ne": ["$rating", None]}, 1, 0]}}}}]).to_list(1)
    a = times[0] if times else {}
    hrs = lambda ms: round(ms / 3_600_000, 1) if ms is not None else None  # noqa: E731
    return {"open": sum(by_status.values()), "by_status": by_status,
            "overdue": await db.tickets.count_documents({**open_f, "sla_due_at": {"$lt": now_utc()}}),
            "unassigned": await db.tickets.count_documents({**open_f, "assignee_user_id": None}),
            "created": a.get("n", 0), "resolved": a.get("resolved", 0), "reopened": a.get("reopened", 0),
            "avg_first_response_hours": hrs(a.get("frt")), "avg_resolution_hours": hrs(a.get("res")),
            "satisfaction": round(a["csat"], 2) if a.get("csat") is not None else None, "ratings": a.get("rated", 0),
            "by_category": [{"category": r["_id"], "count": r["n"]} for r in by_cat], "days": days,
            "definitions": {"overdue": "Not resolved/closed and past the SLA due time (urgent 4h, high 24h, normal 48h; clock hours)",
                            "avg_first_response_hours": "Created → first public staff reply, for requests created in the window",
                            "satisfaction": "Average parent rating (1–5) on resolved requests"}}
