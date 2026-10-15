"""SchoolPulse OS core: DB, models helpers, auth, tenancy, permissions, audit."""
import os
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
JWT_HOURS = int(os.environ["JWT_EXPIRES_HOURS"])
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"


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


async def create_session(user_id: str, user_agent: str = "") -> str:
    jti = uuid.uuid4().hex
    exp = now_utc() + timedelta(hours=JWT_HOURS)
    await db.sessions.insert_one(
        {"jti": jti, "user_id": user_id, "created_at": now_utc(), "expires_at": exp,
         "revoked": False, "user_agent": user_agent[:200]}
    )
    return jwt.encode({"sub": user_id, "jti": jti, "iat": now_utc(), "exp": exp, "typ": "access"},
                      JWT_SECRET, algorithm=JWT_ALG)


async def _user_from_token(token: Optional[str]) -> dict:
    err = HTTPException(401, "Not authenticated")
    if not token:
        raise err
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid or expired session")
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
                           "staff.manage", "audit.view", "dashboard.owner"},
    "principal": _ALL_STAFF | {"school.manage", "academic.manage", "people.manage", "staff.manage",
                               "audit.view", "dashboard.owner"},
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
