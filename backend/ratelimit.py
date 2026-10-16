"""Persistent, instance-shared login rate limiting (MongoDB `login_limits`).

Keys (stored hashed): account+IP (primary), account across all IPs (distributed attack),
IP across all accounts (password spraying). Each key gets progressive cooldowns once its
threshold is passed; cooldowns are capped and records expire, so users are never locked permanently.
"""
import hashlib
import ipaddress
import os
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


def _trusted_networks():
    raw = os.environ.get("TRUSTED_PROXY_CIDRS", "")
    return [ipaddress.ip_network(c.strip(), strict=False) for c in raw.split(",") if c.strip()]


def _is_trusted(addr: str, nets) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in n for n in nets)


def resolve_client_ip(peer: str, xff: str, nets) -> str:
    """X-Forwarded-For is honoured ONLY when the direct peer is a configured trusted proxy.
    We then walk the chain right-to-left, skipping trusted proxies; the first untrusted hop is the
    client. Client-supplied (left-most) values cannot override the address the proxy appended."""
    if not xff or not _is_trusted(peer, nets):
        return peer
    for hop in reversed([h.strip() for h in xff.split(",") if h.strip()]):
        if not _is_trusted(hop, nets):
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                return peer  # malformed header: fall back to the proxy address
    return peer


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for", ""), _trusted_networks())[:64]


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
