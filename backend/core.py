"""SchoolPulse OS core: DB, models helpers, auth, tenancy, permissions, audit."""
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Optional

import bcrypt
import jwt
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
ACCESS_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", "30"))
# Safe defaults: production unless told otherwise, demo OFF unless explicitly enabled.
APP_ENV = os.environ.get("APP_ENV", "production").strip().lower()
DEMO_MODE = os.environ.get("DEMO_MODE", "false").strip().lower() == "true"


class UnsafeConfigError(RuntimeError):
    pass


def assert_safe_config():
    """Blocking startup check: demo authentication must never run in production."""
    if APP_ENV == "production" and (len(JWT_SECRET) < 32 or "replace" in JWT_SECRET.lower()):
        raise UnsafeConfigError("UNSAFE CONFIG: JWT_SECRET must be a unique random value of 32+ chars in production.")
    if APP_ENV == "production" and DEMO_MODE:
        raise UnsafeConfigError("UNSAFE CONFIG: DEMO_MODE=true is not allowed when APP_ENV=production. "
                                "Set DEMO_MODE=false (or APP_ENV=staging/development for demos).")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- Mongo models
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        if doc is None:
            return None
        return cls.model_validate(doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=False)
        if data.get("_id") is None:
            data.pop("_id", None)
        return data

    def out(self) -> dict:
        d = self.model_dump(by_alias=False)
        d.pop("password_hash", None)
        return _jsonable(d)


def _jsonable(v: Any):
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items() if k != "_id"}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


class Doc(BaseDocument):
    """Generic document wrapper used for read paths."""


def out(doc: Optional[dict]) -> Optional[dict]:
    m = Doc.from_mongo(doc)
    return m.out() if m else None


def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(404, "Record not found")
    return ObjectId(value)


# ---------------------------------------------------------------- passwords/JWT
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def _hash_refresh(token: str) -> str:
    return hmac.new(JWT_SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()


def _access_jwt(user_id: str, sid: str) -> str:
    t = now_utc()
    return jwt.encode({"sub": user_id, "jti": sid, "iat": t, "exp": t + timedelta(minutes=ACCESS_MINUTES),
                       "typ": "access"}, JWT_SECRET, algorithm=JWT_ALG)


def _tokens(user_id: str, sid: str, refresh: str) -> dict:
    return {"access_token": _access_jwt(user_id, sid), "refresh_token": refresh, "token_type": "bearer",
            "expires_in": ACCESS_MINUTES * 60, "session_id": sid}


async def create_session(user_id: str, user_agent: str = "", ip: str = "") -> dict:
    """New device session: short-lived access JWT + opaque rotating refresh token (stored hashed)."""
    sid = uuid.uuid4().hex
    refresh = secrets.token_urlsafe(48)
    t = now_utc()
    await db.sessions.insert_one({
        "jti": sid, "user_id": user_id, "refresh_hash": _hash_refresh(refresh), "prev_refresh_hashes": [],
        "created_at": t, "last_used_at": t, "expires_at": t + timedelta(days=REFRESH_DAYS), "rotations": 0,
        "revoked": False, "revoked_reason": None, "user_agent": user_agent[:200], "ip": ip[:64]})
    return _tokens(user_id, sid, refresh)


async def rotate_refresh(refresh: str, ip: str = "") -> dict:
    h = _hash_refresh(refresh)
    new = secrets.token_urlsafe(48)
    t = now_utc()
    s = await db.sessions.find_one_and_update(
        {"refresh_hash": h, "revoked": False, "expires_at": {"$gt": t}},
        {"$set": {"refresh_hash": _hash_refresh(new), "last_used_at": t, "last_ip": ip[:64]},
         "$push": {"prev_refresh_hashes": {"$each": [h], "$slice": -20}}, "$inc": {"rotations": 1}})
    if s:
        return _tokens(s["user_id"], s["jti"], new)
    reused = await db.sessions.find_one({"prev_refresh_hashes": h})
    if reused and not reused.get("revoked"):
        await db.sessions.update_one({"_id": reused["_id"]}, {"$set": {
            "revoked": True, "revoked_reason": "refresh_token_reuse", "revoked_at": t}})
        await audit(reused["user_id"], "auth.refresh_reuse_detected", "session", reused["jti"], meta={"ip": ip})
        raise HTTPException(401, "Refresh token reuse detected. Session revoked; please sign in again.")
    raise HTTPException(401, "Invalid or expired refresh token")


async def _user_from_token(token: Optional[str]) -> dict:
    err = HTTPException(401, "Not authenticated")
    if not token:
        raise err
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Access token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid or expired session")
    if payload.get("typ") != "access":
        raise err
    session = await db.sessions.find_one({"jti": payload.get("jti"), "revoked": False})
    if not session:
        raise HTTPException(401, "Session revoked")
    user = await db.users.find_one({"_id": oid(payload["sub"]), "status": "active"})
    if not user:
        raise err
    user["_jti"] = payload["jti"]
    return user


def _bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def current_user(request: Request) -> dict:
    return await _user_from_token(_bearer(request))


async def optional_user(request: Request) -> Optional[dict]:
    token = _bearer(request) or request.query_params.get("token")
    if not token:
        return None
    try:
        return await _user_from_token(token)
    except HTTPException:
        return None


async def require_super_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("platform_role") != "super_admin":
        raise HTTPException(403, "Platform administrator access required")
    return user


# ---------------------------------------------------------------- roles/permissions
ROLES = ["owner", "principal", "school_admin", "accountant", "admission_coordinator",
         "teacher", "transport_coordinator", "parent"]

_ALL_STAFF = {"school.view", "academic.view", "people.view"}
PERMISSIONS: dict[str, set[str]] = {
    "owner": _ALL_STAFF | {"school.manage", "brand.manage", "academic.manage", "people.manage",
                           "staff.manage", "audit.view", "dashboard.owner", "leave.approve"},
    "principal": _ALL_STAFF | {"school.manage", "academic.manage", "people.manage", "staff.manage",
                               "audit.view", "dashboard.owner", "leave.approve"},
    "school_admin": _ALL_STAFF | {"academic.manage", "people.manage", "staff.manage", "dashboard.owner"},
    "accountant": _ALL_STAFF | {"dashboard.owner"},
    "admission_coordinator": _ALL_STAFF | {"people.manage", "dashboard.owner"},
    "transport_coordinator": _ALL_STAFF | {"dashboard.owner"},
    "teacher": {"school.view", "academic.view", "teacher.workspace"},
    "parent": {"school.view", "parent.portal"},
}


class Ctx(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    user: dict
    user_id: str
    school_id: str
    role: str
    perms: set[str]

    def need(self, perm: str):
        if perm not in self.perms:
            raise HTTPException(403, f"Your role ({self.role}) is not permitted to perform this action")


async def school_ctx(user: dict = Depends(current_user),
                     x_school_id: Optional[str] = Header(default=None)) -> Ctx:
    """Resolves tenant from X-School-Id and verifies explicit active membership."""
    if not x_school_id:
        raise HTTPException(400, "X-School-Id header is required")
    user_id = str(user["_id"])
    m = await db.memberships.find_one({"user_id": user_id, "school_id": x_school_id, "status": "active"})
    if not m:
        raise HTTPException(403, "You do not have access to this school")
    school = await db.schools.find_one({"_id": oid(x_school_id)})
    if not school or school.get("status") == "suspended":
        raise HTTPException(403, "This school account is not active")
    return Ctx(user=user, user_id=user_id, school_id=x_school_id, role=m["role"],
               perms=PERMISSIONS.get(m["role"], set()))


def need(perm: str):
    async def dep(ctx: Ctx = Depends(school_ctx)) -> Ctx:
        ctx.need(perm)
        return ctx
    return dep


# ---------------------------------------------------------------- audit
async def audit(actor_id: Optional[str], action: str, entity: str, entity_id: Optional[str] = None,
                school_id: Optional[str] = None, meta: Optional[dict] = None):
    await db.audit_logs.insert_one({
        "school_id": school_id, "actor_user_id": actor_id, "action": action, "entity": entity,
        "entity_id": entity_id, "meta": meta or {}, "at": now_utc(),
    })


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.memberships.create_index([("user_id", 1), ("school_id", 1)], unique=True)
    await db.sessions.create_index("jti", unique=True)
    await db.sessions.create_index("refresh_hash", sparse=True)
    await db.sessions.create_index("prev_refresh_hashes")
    await db.sessions.create_index([("user_id", 1), ("revoked", 1)])
    await db.login_limits.create_index("key", unique=True)
    await db.login_limits.create_index("expires_at", expireAfterSeconds=0)
    await db.schools.create_index("slug", unique=True)
    await db.academic_years.create_index([("school_id", 1), ("name", 1)], unique=True)
    await db.classes.create_index([("school_id", 1), ("academic_year_id", 1), ("name", 1)], unique=True)
    await db.sections.create_index([("school_id", 1), ("class_id", 1), ("name", 1)], unique=True)
    await db.subjects.create_index([("school_id", 1), ("code", 1)], unique=True)
    await db.teachers.create_index([("school_id", 1), ("email", 1)], unique=True)
    await db.students.create_index([("school_id", 1), ("admission_no", 1)], unique=True)
    await db.guardians.create_index([("school_id", 1), ("phone", 1)], unique=True)
    await db.guardian_links.create_index([("student_id", 1), ("guardian_id", 1)], unique=True)
    await db.teacher_assignments.create_index(
        [("school_id", 1), ("teacher_id", 1), ("section_id", 1), ("subject_id", 1)], unique=True)
    await db.audit_logs.create_index([("school_id", 1), ("at", -1)])
    await db.invitations.create_index("token", unique=True)
    await db.attendance.create_index([("school_id", 1), ("section_id", 1), ("date", 1)], unique=True)
    await db.attendance.create_index([("school_id", 1), ("date", 1)])
    await db.client_errors.create_index("expires_at", expireAfterSeconds=0)
    await db.staff_attendance.create_index([("school_id", 1), ("teacher_id", 1), ("date", 1)], unique=True)
    await db.staff_attendance.create_index([("school_id", 1), ("date", 1)])
    await db.leave_requests.create_index([("school_id", 1), ("status", 1), ("from_date", 1)])
    await db.leave_requests.create_index([("school_id", 1), ("teacher_id", 1)])
    await db.homework.create_index([("school_id", 1), ("section_id", 1), ("status", 1), ("due_date", 1)])
    await db.homework.create_index([("school_id", 1), ("created_by", 1)])
    await db.homework.create_index("attachments")
    await db.diary.create_index([("school_id", 1), ("section_id", 1), ("date", 1)])
