"""Persistent, instance-shared login rate limiting (MongoDB `login_limits`).

Keys (stored hashed): account+IP (primary), account across all IPs (distributed attack),
IP across all accounts (password spraying). Each key gets progressive cooldowns once its
threshold is passed; cooldowns are capped and records expire, so users are never locked permanently.
"""
import hashlib
from datetime import timedelta

from fastapi import HTTPException, Request
from pymongo import ReturnDocument

from core import JWT_SECRET, db, now_utc

# kind: (free failures before cooldown, base cooldown seconds, max cooldown seconds)
RULES = {
    "acct_ip": (5, 30, 15 * 60),
    "acct": (20, 60, 15 * 60),
    "ip": (50, 60, 15 * 60),
}
RECORD_TTL = timedelta(hours=1)  # failure history forgotten after 1h of no failures


def client_ip(request: Request) -> str:
    # Behind the platform ingress the first X-Forwarded-For hop is the client.
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown"))[:64]


def _key(kind: str, email: str, ip: str) -> str:
    raw = {"acct_ip": f"{email}|{ip}", "acct": email, "ip": ip}[kind]
    return f"{kind}:" + hashlib.sha256(f"{JWT_SECRET}|{raw}".encode()).hexdigest()


async def check(email: str, ip: str):
    t = now_utc()
    keys = [_key(k, email, ip) for k in RULES]
    async for r in db.login_limits.find({"key": {"$in": keys}, "blocked_until": {"$gt": t}}):
        wait = int((r["blocked_until"].replace(tzinfo=t.tzinfo) - t).total_seconds()) + 1
        raise HTTPException(429, f"Too many failed attempts. Try again in {max(wait, 1)} seconds.",
                            headers={"Retry-After": str(max(wait, 1))})


async def record_failure(email: str, ip: str):
    t = now_utc()
    for kind, (free, base, cap) in RULES.items():
        doc = await db.login_limits.find_one_and_update(
            {"key": _key(kind, email, ip)},
            {"$inc": {"failures": 1}, "$set": {"kind": kind, "last_failure_at": t, "expires_at": t + RECORD_TTL},
             "$setOnInsert": {"created_at": t}},
            upsert=True, return_document=ReturnDocument.AFTER)
        over = doc["failures"] - free
        if over > 0:
            cooldown = min(cap, base * (2 ** (over - 1)))
            await db.login_limits.update_one({"_id": doc["_id"]},
                                             {"$set": {"blocked_until": t + timedelta(seconds=cooldown)}})


async def record_success(email: str, ip: str):
    await db.login_limits.delete_many({"key": {"$in": [_key("acct_ip", email, ip), _key("acct", email, ip)]}})
