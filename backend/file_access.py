"""Document-level read policy for private files + one-time download grants.

Policy (deny by default):
- public brand assets (logo/banner/photo with visibility=brand): anyone.
- homework attachments: owner/principal/school_admin (academic leadership); a teacher who uploaded it or is
  currently assigned to a section whose homework references it; a parent whose *verified* child is in a section
  with *published* homework referencing it. Accountants, admission and transport staff: denied.
- any other private file: the uploader, or the owner/principal.
Every check runs against live memberships / assignments / guardian links, so revocation applies immediately.
"""
import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException

from core import db, now_utc, oid

ACADEMIC_LEADERS = {"owner", "principal", "school_admin"}
GRANT_TTL = timedelta(seconds=60)


async def active_membership(user_id: str, school_id: str) -> Optional[dict]:
    return await db.memberships.find_one({"user_id": user_id, "school_id": school_id, "status": "active"})


async def _teacher_can_read_homework_file(user_id: str, f: dict) -> bool:
    if f.get("uploaded_by") == user_id:
        return True
    t = await db.teachers.find_one({"school_id": f["school_id"], "user_id": user_id, "status": "active"})
    if not t:
        return False
    secs = await db.teacher_assignments.distinct("section_id", {"school_id": f["school_id"], "teacher_id": str(t["_id"])})
    return bool(await db.homework.find_one({"school_id": f["school_id"], "attachments": str(f["_id"]),
                                            "status": {"$ne": "deleted"}, "section_id": {"$in": secs}}, {"_id": 1}))


async def can_read_file(user_id: str, role: str, f: dict) -> bool:
    if f.get("purpose") == "homework":
        if role in ACADEMIC_LEADERS:
            return True
        if role == "teacher":
            return await _teacher_can_read_homework_file(user_id, f)
        if role == "parent":
            from routes_homework import parent_can_read_file
            return await parent_can_read_file(user_id, f)
        return False
    return f.get("uploaded_by") == user_id or role in {"owner", "principal"}


async def authorize_file(user_id: str, f: dict) -> dict:
    m = await active_membership(user_id, f["school_id"])
    if not m or not await can_read_file(user_id, m["role"], f):
        raise HTTPException(403, "Not permitted")
    return m


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_grant(user_id: str, school_id: str, kind: str, ref: dict) -> dict:
    """Single-use, 60-second grant scoped to one user + one document. Only the hash is stored."""
    token = secrets.token_urlsafe(32)
    await db.download_grants.insert_one({"token_hash": _hash(token), "user_id": user_id, "school_id": school_id,
                                         "kind": kind, "ref": ref, "used": False, "created_at": now_utc(),
                                         "expires_at": now_utc() + GRANT_TTL})
    return {"url": f"/api/downloads/{token}", "expires_in": int(GRANT_TTL.total_seconds())}


async def consume_grant(token: str) -> dict:
    g = await db.download_grants.find_one_and_update(
        {"token_hash": _hash(token), "used": False, "expires_at": {"$gt": now_utc()}},
        {"$set": {"used": True, "used_at": now_utc()}})
    if not g:
        raise HTTPException(404, "This download link has expired or was already used")
    user = await db.users.find_one({"_id": oid(g["user_id"]), "status": "active"})
    if not user:
        raise HTTPException(403, "Not permitted")
    return {**g, "user": user}
