"""SchoolPulse OS API — v1. All routes are under /api."""
import logging
from typing import Optional

from pydantic import BaseModel, Field

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware

import storage
from core import APP_ENV, DEMO_MODE, assert_safe_config, client, ensure_indexes

assert_safe_config()  # blocks startup if production is configured with demo auth
from routes_attendance import router as attendance_router
from routes_auth import router as auth_router
from routes_directory import router as directory_router
from routes_school import router as school_router
from routes_staff import router as staff_router
from routes_homework import router as homework_router
from routes_diary import router as diary_router
from routes_timetable import router as timetable_router
from routes_exams import router as exams_router
from routes_workspace import router as workspace_router
from routes_parent import router as parent_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("schoolpulse")

app = FastAPI(title="SchoolPulse OS API", version="1.0.0")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "SchoolPulse OS", "api_version": "v1", "milestone": 1}


@api.get("/health")
async def health():
    from core import db
    await db.command("ping")
    return {"ok": True}


class ClientError(BaseModel):
    kind: str = Field(max_length=20)
    message: str = Field(max_length=2000)
    stack: str = Field(default="", max_length=4000)
    platform: str = Field(default="", max_length=20)
    school: Optional[str] = Field(default=None, max_length=40)


@api.post("/client-errors", status_code=202)
async def client_errors(body: ClientError, request: Request):
    """Scrubbed client crash reports (no auth required so crashes before login are captured).
    Capped per IP per hour; TTL 30 days."""
    from core import db, now_utc
    from ratelimit import client_ip
    from datetime import timedelta
    ip = client_ip(request)
    if await db.client_errors.count_documents({"ip": ip, "at": {"$gt": now_utc() - timedelta(hours=1)}}) >= 60:
        return {"accepted": False}
    await db.client_errors.insert_one({**body.model_dump(), "ip": ip, "at": now_utc(), "expires_at": now_utc() + timedelta(days=30)})
    return {"accepted": True}


api.include_router(auth_router)
api.include_router(school_router)
api.include_router(directory_router)
api.include_router(attendance_router)
api.include_router(staff_router)
api.include_router(homework_router)
api.include_router(diary_router)
api.include_router(timetable_router)
api.include_router(exams_router)
api.include_router(workspace_router)
api.include_router(parent_router)
app.include_router(api)


@app.exception_handler(DuplicateKeyError)
async def dup_handler(_: Request, exc: DuplicateKeyError):
    return JSONResponse(status_code=409, content={"detail": "A record with these details already exists"})


app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    logger.info(f"APP_ENV={APP_ENV} DEMO_MODE={DEMO_MODE}")
    if DEMO_MODE:
        logger.warning("DEMO MODE ENABLED: demo picker + fictional seed active. Never use in production.")
        from seed import seed
        await seed()
        from routes_timetable import seed_demo_timetable
        await seed_demo_timetable()
        logger.info("Demo seed ensured")
    try:
        storage.init_storage()
        logger.info("Object storage ready")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()
