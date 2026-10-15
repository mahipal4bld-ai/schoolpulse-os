"""SchoolPulse OS API — v1. All routes are under /api."""
import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware

import storage
from core import APP_ENV, DEMO_MODE, assert_safe_config, client, ensure_indexes

assert_safe_config()  # blocks startup if production is configured with demo auth
from routes_auth import router as auth_router
from routes_directory import router as directory_router
from routes_school import router as school_router

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


api.include_router(auth_router)
api.include_router(school_router)
api.include_router(directory_router)
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
        logger.info("Demo seed ensured")
    try:
        storage.init_storage()
        logger.info("Object storage ready")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()
