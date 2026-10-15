"""Authentication: login, logout (session revocation), me, demo accounts, invitations."""
import secrets
import time
from collections import defaultdict
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from core import (DEMO_MODE, PERMISSIONS, ROLES, Ctx, audit, create_session, current_user, db,
                  hash_password, need, now_utc, oid, out, verify_password)

router = APIRouter()

_FAILS: dict[str, list[float]] = defaultdict(list)  # in-memory brute-force guard (per process)
MAX_FAILS, WINDOW = 5, 15 * 60


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


async def build_me(user: dict) -> dict:
    user_id = str(user["_id"])
    memberships = await db.memberships.find({"user_id": user_id, "status": "active"}).to_list(100)
    schools = []
    for m in memberships:
        s = await db.schools.find_one({"_id": oid(m["school_id"])})
        if not s or s.get("status") == "suspended":
            continue
        schools.append({
            "school_id": m["school_id"], "role": m["role"],
            "permissions": sorted(PERMISSIONS.get(m["role"], set())),
            "school": public_school(s),
        })
    return {
        "user": {"id": user_id, "email": user["email"], "name": user.get("name"),
                 "phone": user.get("phone"), "platform_role": user.get("platform_role"),
                 "preferred_language": user.get("preferred_language", "en")},
        "memberships": schools,
    }


def public_school(s: dict) -> dict:
    d = out(s)
    return {k: d.get(k) for k in ["id", "name", "slug", "status", "tagline", "description", "brand",
                                  "contact", "academic_session_label", "preferred_language", "board",
                                  "operating", "custom_domain", "photos", "campuses", "plan"]}


@router.post("/auth/login")
async def login(body: LoginIn, request: Request):
    email = body.email.lower()
    now = time.time()
    _FAILS[email] = [t for t in _FAILS[email] if now - t < WINDOW]
    if len(_FAILS[email]) >= MAX_FAILS:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email})
    if not user or user.get("status") != "active" or not verify_password(body.password, user["password_hash"]):
        _FAILS[email].append(now)
        raise HTTPException(401, "Incorrect email or password")
    _FAILS.pop(email, None)
    token = await create_session(str(user["_id"]), request.headers.get("user-agent", ""))
    await audit(str(user["_id"]), "auth.login", "user", str(user["_id"]))
    return {"access_token": token, "token_type": "bearer", **(await build_me(user))}


@router.post("/auth/logout")
async def logout(user: dict = Depends(current_user)):
    await db.sessions.update_one({"jti": user["_jti"]}, {"$set": {"revoked": True, "revoked_at": now_utc()}})
    await audit(str(user["_id"]), "auth.logout", "user", str(user["_id"]))
    return {"ok": True}


@router.post("/auth/logout-all")
async def logout_all(user: dict = Depends(current_user)):
    r = await db.sessions.update_many({"user_id": str(user["_id"]), "revoked": False},
                                      {"$set": {"revoked": True, "revoked_at": now_utc()}})
    await audit(str(user["_id"]), "auth.logout_all", "user", str(user["_id"]))
    return {"ok": True, "revoked": r.modified_count}


@router.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return await build_me(user)


class PrefIn(BaseModel):
    preferred_language: Literal["en", "hi"]


@router.patch("/auth/me/preferences")
async def prefs(body: PrefIn, user: dict = Depends(current_user)):
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"preferred_language": body.preferred_language}})
    return {"ok": True}


@router.get("/auth/demo-accounts")
async def demo_accounts():
    """Developer-only helper. Disabled unless DEMO_MODE=true. Never grants access by itself;
    the client still performs a normal password login."""
    if not DEMO_MODE:
        raise HTTPException(404, "Not found")
    users = await db.users.find({"is_demo": True}).sort("demo_order", 1).to_list(50)
    return {"password": "Demo@1234", "accounts": [
        {"email": u["email"], "name": u.get("name"), "label": u.get("demo_label")} for u in users]}


# ---------------------------------------------------------------- invitations
class InviteIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    role: Literal["principal", "school_admin", "accountant", "admission_coordinator",
                  "teacher", "transport_coordinator"]


@router.post("/invitations", status_code=201)
async def create_invite(body: InviteIn, ctx: Ctx = Depends(need("staff.manage"))):
    email = body.email.lower()
    existing = await db.invitations.find_one({"school_id": ctx.school_id, "email": email, "status": "pending"})
    if existing:
        raise HTTPException(409, "A pending invitation already exists for this email")
    doc = {"school_id": ctx.school_id, "email": email, "name": body.name, "role": body.role,
           "token": secrets.token_urlsafe(9), "status": "pending", "invited_by": ctx.user_id,
           "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=14)}
    r = await db.invitations.insert_one(doc)
    doc["_id"] = r.inserted_id
    await audit(ctx.user_id, "invitation.create", "invitation", str(r.inserted_id), ctx.school_id, {"role": body.role})
    return out(doc)


@router.get("/invitations")
async def list_invites(ctx: Ctx = Depends(need("staff.manage"))):
    docs = await db.invitations.find({"school_id": ctx.school_id}).sort("created_at", -1).to_list(200)
    return {"items": [out(d) for d in docs]}


@router.delete("/invitations/{invite_id}")
async def revoke_invite(invite_id: str, ctx: Ctx = Depends(need("staff.manage"))):
    r = await db.invitations.update_one({"_id": oid(invite_id), "school_id": ctx.school_id, "status": "pending"},
                                        {"$set": {"status": "revoked"}})
    if not r.matched_count:
        raise HTTPException(404, "Pending invitation not found")
    await audit(ctx.user_id, "invitation.revoke", "invitation", invite_id, ctx.school_id)
    return {"ok": True}


class AcceptIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = None


@router.post("/auth/accept-invite")
async def accept_invite(body: AcceptIn, request: Request):
    inv = await db.invitations.find_one({"token": body.token, "status": "pending"})
    if not inv or inv["expires_at"].replace(tzinfo=None) < now_utc().replace(tzinfo=None):
        raise HTTPException(400, "Invitation is invalid or expired")
    user = await db.users.find_one({"email": inv["email"]})
    if not user:
        doc = {"email": inv["email"], "name": body.name or inv["name"], "password_hash": hash_password(body.password),
               "status": "active", "platform_role": None, "preferred_language": "en", "created_at": now_utc()}
        r = await db.users.insert_one(doc)
        user = {**doc, "_id": r.inserted_id}
    elif not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "This email already has an account. Enter its existing password to accept.")
    uid = str(user["_id"])
    await db.memberships.update_one({"user_id": uid, "school_id": inv["school_id"]},
                                    {"$setOnInsert": {"role": inv["role"], "status": "active", "created_at": now_utc()}},
                                    upsert=True)
    if inv["role"] == "teacher":
        await db.teachers.update_one({"school_id": inv["school_id"], "email": inv["email"]},
                                     {"$set": {"user_id": uid},
                                      "$setOnInsert": {"name": user.get("name"), "status": "active",
                                                       "designation": "Teacher", "created_at": now_utc()}},
                                     upsert=True)
    await db.invitations.update_one({"_id": inv["_id"]}, {"$set": {"status": "accepted", "accepted_at": now_utc()}})
    await audit(uid, "invitation.accept", "invitation", str(inv["_id"]), inv["school_id"])
    token = await create_session(uid, request.headers.get("user-agent", ""))
    return {"access_token": token, "token_type": "bearer", **(await build_me(user))}


assert set(PERMISSIONS) == set(ROLES)
