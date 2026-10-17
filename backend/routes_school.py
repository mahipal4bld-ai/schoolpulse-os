"""Platform (super admin), school settings, brand studio, uploads, dashboards, audit."""
import re
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo.errors import DuplicateKeyError

import storage
from core import (Ctx, audit, db, hash_password, need, now_utc, oid, optional_user, out,
                  require_super_admin, school_ctx)
from routes_auth import public_school

router = APIRouter()
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ---------------------------------------------------------------- platform
class CreateSchoolIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    slug: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9-]+$")
    city: str = Field(min_length=2, max_length=60)
    owner_name: str = Field(min_length=2, max_length=100)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=128)
    plan: Literal["growth", "trial"] = "trial"
    student_quota: int = Field(default=1500, ge=50, le=10000)


def default_school(name: str, slug: str, city: str, plan: str, quota: int) -> dict:
    words = [w for w in re.split(r"\s+", name) if w]
    mono = "".join(w[0] for w in words[:2]).upper()
    return {
        "name": name, "slug": slug, "status": "active", "plan": plan, "student_quota": quota,
        "tagline": "", "description": "",
        "brand": {"primary": "#0A192F", "secondary": "#0D9488", "logo_file_id": None, "banner_file_id": None,
                  "monogram": mono, "logo_style": "circle", "welcome_message": f"Welcome to {name}"},
        "contact": {"phone": "", "email": "", "address": "", "city": city, "state": "", "pincode": "",
                    "website": "", "map_url": ""},
        "custom_domain": "", "preferred_language": "en", "academic_session_label": "", "board": "CBSE",
        "operating": {"start_time": "08:00", "end_time": "14:00", "working_days": "Mon-Sat"},
        "photos": [], "campuses": [{"id": uuid.uuid4().hex[:8], "name": "Main Campus"}],
        "timezone": "Asia/Kolkata", "features": {"growth_edition": True}, "created_at": now_utc(),
    }


@router.get("/platform/schools")
async def platform_schools(q: str = "", _: dict = Depends(require_super_admin)):
    filt = {"name": {"$regex": re.escape(q), "$options": "i"}} if q else {}
    schools = await db.schools.find(filt).sort("created_at", 1).to_list(500)
    items = []
    for s in schools:
        sid = str(s["_id"])
        d = public_school(s)
        d["student_quota"] = s.get("student_quota")
        d["created_at"] = out(s)["created_at"]
        d["usage"] = {
            "students": await db.students.count_documents({"school_id": sid, "status": "active"}),
            "teachers": await db.teachers.count_documents({"school_id": sid}),
            "members": await db.memberships.count_documents({"school_id": sid}),
        }
        items.append(d)
    return {"items": items, "total": len(items)}


@router.post("/platform/schools", status_code=201)
async def platform_create_school(body: CreateSchoolIn, admin: dict = Depends(require_super_admin)):
    if await db.schools.find_one({"slug": body.slug}):
        raise HTTPException(409, "A school with this slug already exists")
    doc = default_school(body.name, body.slug, body.city, body.plan, body.student_quota)
    r = await db.schools.insert_one(doc)
    sid = str(r.inserted_id)
    email = body.owner_email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        u = await db.users.insert_one({"email": email, "name": body.owner_name,
                                       "password_hash": hash_password(body.owner_password), "status": "active",
                                       "platform_role": None, "preferred_language": "en", "created_at": now_utc()})
        uid = str(u.inserted_id)
    else:
        uid = str(user["_id"])
    await db.memberships.insert_one({"user_id": uid, "school_id": sid, "role": "owner", "status": "active",
                                     "created_at": now_utc()})
    await audit(str(admin["_id"]), "platform.school.create", "school", sid, sid, {"owner": email})
    return public_school(await db.schools.find_one({"_id": r.inserted_id}))


class SchoolStatusIn(BaseModel):
    status: Literal["active", "suspended", "trial"]


@router.patch("/platform/schools/{school_id}")
async def platform_update_school(school_id: str, body: SchoolStatusIn, admin: dict = Depends(require_super_admin)):
    r = await db.schools.update_one({"_id": oid(school_id)}, {"$set": {"status": body.status}})
    if not r.matched_count:
        raise HTTPException(404, "School not found")
    await audit(str(admin["_id"]), "platform.school.status", "school", school_id, school_id, {"status": body.status})
    return {"ok": True}


@router.get("/platform/stats")
async def platform_stats(_: dict = Depends(require_super_admin)):
    return {
        "schools": await db.schools.count_documents({}),
        "active_schools": await db.schools.count_documents({"status": "active"}),
        "students": await db.students.count_documents({"status": "active"}),
        "users": await db.users.count_documents({}),
    }


# ---------------------------------------------------------------- school settings & brand
@router.get("/school")
async def get_school(ctx: Ctx = Depends(school_ctx)):
    s = await db.schools.find_one({"_id": oid(ctx.school_id)})
    return {**public_school(s), "role": ctx.role, "permissions": sorted(ctx.perms)}


class ContactIn(BaseModel):
    phone: str = Field(default="", max_length=20)
    email: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=60)
    state: str = Field(default="", max_length=60)
    pincode: str = Field(default="", max_length=10)
    website: str = Field(default="", max_length=200)
    map_url: str = Field(default="", max_length=300)


class OperatingIn(BaseModel):
    start_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(default="14:00", pattern=r"^\d{2}:\d{2}$")
    working_days: str = Field(default="Mon-Sat", max_length=40)


class SettingsIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    tagline: Optional[str] = Field(default=None, max_length=140)
    description: Optional[str] = Field(default=None, max_length=1000)
    academic_session_label: Optional[str] = Field(default=None, max_length=20)
    board: Optional[str] = Field(default=None, max_length=40)
    preferred_language: Optional[Literal["en", "hi"]] = None
    custom_domain: Optional[str] = Field(default=None, max_length=120)
    contact: Optional[ContactIn] = None
    operating: Optional[OperatingIn] = None


@router.patch("/school/settings")
async def update_settings(body: SettingsIn, ctx: Ctx = Depends(need("school.manage"))):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No changes supplied")
    await db.schools.update_one({"_id": oid(ctx.school_id)}, {"$set": {**data, "updated_at": now_utc()}})
    await audit(ctx.user_id, "school.settings.update", "school", ctx.school_id, ctx.school_id, {"fields": list(data)})
    return public_school(await db.schools.find_one({"_id": oid(ctx.school_id)}))


class BrandIn(BaseModel):
    primary: Optional[str] = None
    secondary: Optional[str] = None
    monogram: Optional[str] = Field(default=None, min_length=1, max_length=3)
    logo_style: Optional[Literal["circle", "shield", "square"]] = None
    welcome_message: Optional[str] = Field(default=None, max_length=140)
    logo_file_id: Optional[str] = None
    banner_file_id: Optional[str] = None
    clear_logo: bool = False
    clear_banner: bool = False

    @field_validator("primary", "secondary")
    @classmethod
    def _hex(cls, v):
        if v is not None and not HEX.match(v):
            raise ValueError("Colour must be a hex value like #1A2B3C")
        return v.upper() if v else v


async def _own_file(file_id: str, school_id: str):
    f = await db.files.find_one({"_id": oid(file_id), "school_id": school_id, "is_deleted": False})
    if not f:
        raise HTTPException(400, "Uploaded file not found for this school")


@router.patch("/school/brand")
async def update_brand(body: BrandIn, ctx: Ctx = Depends(need("brand.manage"))):
    upd = {}
    for k in ["primary", "secondary", "monogram", "logo_style", "welcome_message"]:
        v = getattr(body, k)
        if v is not None:
            upd[f"brand.{k}"] = v.upper() if k == "monogram" else v
    for k in ["logo_file_id", "banner_file_id"]:
        v = getattr(body, k)
        if v:
            await _own_file(v, ctx.school_id)
            upd[f"brand.{k}"] = v
    if body.clear_logo:
        upd["brand.logo_file_id"] = None
    if body.clear_banner:
        upd["brand.banner_file_id"] = None
    if not upd:
        raise HTTPException(400, "No changes supplied")
    await db.schools.update_one({"_id": oid(ctx.school_id)}, {"$set": {**upd, "updated_at": now_utc()}})
    await audit(ctx.user_id, "school.brand.update", "school", ctx.school_id, ctx.school_id, {"fields": list(upd)})
    return public_school(await db.schools.find_one({"_id": oid(ctx.school_id)}))


class PhotosIn(BaseModel):
    photos: list[str] = Field(max_length=12)


@router.put("/school/photos")
async def update_photos(body: PhotosIn, ctx: Ctx = Depends(need("brand.manage"))):
    for fid in body.photos:
        await _own_file(fid, ctx.school_id)
    await db.schools.update_one({"_id": oid(ctx.school_id)}, {"$set": {"photos": body.photos}})
    await audit(ctx.user_id, "school.photos.update", "school", ctx.school_id, ctx.school_id)
    return {"ok": True}


@router.get("/public/schools/{slug}/brand")
async def public_brand(slug: str):
    """Public, non-sensitive brand info for admissions website / PWA manifest. No student data."""
    s = await db.schools.find_one({"slug": slug, "status": {"$ne": "suspended"}})
    if not s:
        raise HTTPException(404, "School not found")
    p = public_school(s)
    return {k: p[k] for k in ["name", "slug", "tagline", "description", "brand", "contact", "board"]}


# ---------------------------------------------------------------- uploads
ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_BYTES = 5 * 1024 * 1024


@router.post("/uploads", status_code=201)
async def upload(file: UploadFile = File(...), purpose: Literal["logo", "banner", "photo"] = Query("logo"),
                 ctx: Ctx = Depends(need("brand.manage"))):
    ctype = file.content_type or ""
    if ctype not in ALLOWED:
        raise HTTPException(400, "Only JPG, PNG or WEBP images are allowed")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image must be under 5 MB")
    path = f"{storage.APP_NAME}/schools/{ctx.school_id}/brand/{uuid.uuid4().hex}.{ALLOWED[ctype]}"
    try:
        res = await run_in_threadpool(storage.put_object, path, data, ctype)
    except Exception as e:  # noqa: BLE001
        code = getattr(getattr(e, "response", None), "status_code", None)
        raise HTTPException(503 if code != 402 else 402, "Storage is unavailable. Please try again later.")
    doc = {"school_id": ctx.school_id, "storage_path": res["path"], "content_type": ctype, "size": len(data),
           "original_name": file.filename, "purpose": purpose, "visibility": "brand", "uploaded_by": ctx.user_id,
           "is_deleted": False, "created_at": now_utc()}
    r = await db.files.insert_one(doc)
    await audit(ctx.user_id, "file.upload", "file", str(r.inserted_id), ctx.school_id, {"purpose": purpose})
    return {"id": str(r.inserted_id), "purpose": purpose, "size": len(data)}


PUBLIC_PURPOSES = {"logo", "banner", "photo"}


def is_public_asset(f: dict) -> bool:
    """Single source of truth for public retrieval. Both conditions required; default is private."""
    return f.get("visibility") == "brand" and f.get("purpose") in PUBLIC_PURPOSES


@router.get("/files/{file_id}")
async def get_file(file_id: str, user: Optional[dict] = Depends(optional_user)):
    f = await db.files.find_one({"_id": oid(file_id), "is_deleted": False})
    if not f:
        raise HTTPException(404, "File not found")
    public = is_public_asset(f)
    if not public:
        # Private: bearer header only (never ?token=), active membership + document-level policy (file_access.py).
        if not user:
            raise HTTPException(401, "Not authenticated")
        from file_access import authorize_file
        await authorize_file(str(user["_id"]), f)
    data, ctype = await run_in_threadpool(storage.get_object, f["storage_path"])
    headers = {"X-Content-Type-Options": "nosniff"}
    if public:
        headers["Cache-Control"] = "public, max-age=86400"
    else:
        headers.update({"Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache", "Expires": "0",
                        "Content-Disposition": "attachment", "Vary": "Authorization",
                        "Referrer-Policy": "no-referrer"})
    return Response(content=data, media_type=f.get("content_type") or ctype, headers=headers)


# ---------------------------------------------------------------- dashboards
@router.get("/dashboard/owner")
async def owner_dashboard(ctx: Ctx = Depends(need("dashboard.owner"))):
    sid = ctx.school_id
    year = await db.academic_years.find_one({"school_id": sid, "is_current": True})
    classes = await db.classes.find({"school_id": sid}).sort("order", 1).to_list(200)
    by_class = []
    for c in classes:
        by_class.append({"class_id": str(c["_id"]), "name": c["name"],
                         "students": await db.students.count_documents(
                             {"school_id": sid, "class_id": str(c["_id"]), "status": "active"}),
                         "sections": await db.sections.count_documents({"school_id": sid, "class_id": str(c["_id"])})})
    gender = {}
    async for g in db.students.aggregate([{"$match": {"school_id": sid, "status": "active"}},
                                          {"$group": {"_id": "$gender", "n": {"$sum": 1}}}]):
        gender[g["_id"] or "unspecified"] = g["n"]
    recent = await db.audit_logs.find({"school_id": sid}).sort("at", -1).limit(6).to_list(6)
    links_total = await db.guardian_links.count_documents({"school_id": sid})
    return {
        "academic_year": out(year),
        "counts": {
            "students": await db.students.count_documents({"school_id": sid, "status": "active"}),
            "teachers": await db.teachers.count_documents({"school_id": sid, "status": "active"}),
            "staff_members": await db.memberships.count_documents({"school_id": sid, "role": {"$ne": "parent"}}),
            "guardians": await db.guardians.count_documents({"school_id": sid}),
            "classes": len(classes),
            "sections": await db.sections.count_documents({"school_id": sid}),
            "subjects": await db.subjects.count_documents({"school_id": sid}),
            "verified_guardian_links": await db.guardian_links.count_documents({"school_id": sid, "verified": True}),
            "guardian_links": links_total,
            "pending_invitations": await db.invitations.count_documents({"school_id": sid, "status": "pending"}),
        },
        "gender": gender,
        "by_class": by_class,
        "recent_activity": [out(a) for a in recent],
    }


@router.get("/audit-logs")
async def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                     ctx: Ctx = Depends(need("audit.view"))):
    filt = {"school_id": ctx.school_id}
    total = await db.audit_logs.count_documents(filt)
    docs = await db.audit_logs.find(filt).sort("at", -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    names = {}
    items = []
    for d in docs:
        uid = d.get("actor_user_id")
        if uid and uid not in names:
            u = await db.users.find_one({"_id": oid(uid)}, {"name": 1})
            names[uid] = u.get("name") if u else None
        items.append({**out(d), "actor_name": names.get(uid)})
    return {"items": items, "total": total, "page": page, "page_size": page_size}


_ = DuplicateKeyError
