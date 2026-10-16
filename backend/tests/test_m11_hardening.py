"""Milestone 1.1 hardening tests: persistent/shared rate limiting, rotating refresh sessions,
demo-mode production safety, file-visibility regression. Spawns extra uvicorn instances on the same DB."""
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

BACKEND = "/app/backend"
API = "http://localhost:8001/api"
load_dotenv(f"{BACKEND}/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
sys.path.insert(0, BACKEND)


def ip():
    return f"198.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"


def attempt(email, pw, xff, base=API):
    return requests.post(f"{base}/auth/login", json={"email": email, "password": pw}, headers={"X-Forwarded-For": xff})


@pytest.fixture
def user():
    import bcrypt
    email = f"rl-{uuid.uuid4().hex[:8]}@example.com"
    uid = db.users.insert_one({"email": email, "name": "RL User", "status": "active", "platform_role": None,
                               "password_hash": bcrypt.hashpw(b"Correct123", bcrypt.gensalt()).decode(),
                               "created_at": datetime.now(timezone.utc)}).inserted_id
    yield email
    db.users.delete_one({"_id": uid})
    db.sessions.delete_many({"user_id": str(uid)})


def spawn(port, **env):
    e = {**os.environ, **env}
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--port", str(port), "--no-proxy-headers"], cwd=BACKEND, env=e,
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(60):
        try:
            if requests.get(f"http://localhost:{port}/api/health", timeout=1).ok:
                return p
        except requests.RequestException:
            time.sleep(0.5)
    p.kill()
    raise RuntimeError(p.stderr.read().decode()[-500:])


# ---------------------------------------------------------------- rate limiting
def test_lockout_after_threshold_and_success_resets(user):
    x = ip()
    for _ in range(3):
        assert attempt(user, "wrong", x).status_code == 401
    assert attempt(user, "Correct123", x).status_code == 200  # success resets account+IP counter
    for _ in range(5):
        assert attempt(user, "wrong", x).status_code == 401
    r = attempt(user, "wrong", x)
    assert r.status_code == 401  # 6th failure triggers cooldown
    blocked = attempt(user, "Correct123", x)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    # another IP for the same account is not blocked by the account+IP key
    assert attempt(user, "Correct123", ip()).status_code == 200


def test_progressive_cooldown_and_no_permanent_lock(user):
    x = ip()
    for _ in range(6):
        attempt(user, "wrong", x)
    docs = list(db.login_limits.find({"kind": "acct_ip", "blocked_until": {"$exists": True}}).sort("last_failure_at", -1).limit(1))
    first = docs[0]
    d1 = (first["blocked_until"] - first["last_failure_at"]).total_seconds()
    db.login_limits.update_one({"_id": first["_id"]}, {"$set": {"blocked_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    attempt(user, "wrong", x)  # 7th failure after cooldown expired
    second = db.login_limits.find_one({"_id": first["_id"]})
    d2 = (second["blocked_until"] - second["last_failure_at"]).total_seconds()
    assert d2 > d1  # progressive
    assert d2 <= 15 * 60  # capped
    assert second["expires_at"] > datetime.now()  # TTL record, never permanent
    db.login_limits.update_one({"_id": first["_id"]}, {"$set": {"blocked_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert attempt(user, "Correct123", x).status_code == 200  # legit user gets back in after cooldown


def test_unknown_accounts_are_limited_too():
    email, x = f"ghost-{uuid.uuid4().hex[:6]}@example.com", ip()
    for _ in range(6):
        attempt(email, "x", x)
    assert attempt(email, "x", x).status_code == 429


def test_limit_shared_across_instances():
    p = spawn(8012)
    try:
        email, x = f"shared-{uuid.uuid4().hex[:6]}@example.com", ip()
        for _ in range(6):
            attempt(email, "x", x)  # instance A (8001)
        assert attempt(email, "x", x, base="http://localhost:8012/api").status_code == 429  # instance B
    finally:
        p.kill()


@pytest.mark.skipif(os.environ.get("RUN_RESTART_TESTS") != "1",
                    reason="restarts the shared backend; run serially: RUN_RESTART_TESTS=1 pytest -n 0 -k restart")
def test_limit_survives_restart():
    email, x = f"restart-{uuid.uuid4().hex[:6]}@example.com", ip()
    for _ in range(6):
        attempt(email, "x", x)
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, capture_output=True)
    for _ in range(60):
        try:
            if requests.get(f"{API}/health", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(0.5)
    assert attempt(email, "x", x).status_code == 429


# ---------------------------------------------------------------- sessions
def login(email, pw):
    r = attempt(email, pw, ip())
    assert r.status_code == 200, r.text
    return r.json()


def me(access):
    return requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {access}"})


def refresh(rt):
    return requests.post(f"{API}/auth/refresh", json={"refresh_token": rt})


def test_short_lived_access_and_rotation(user):
    t = login(user, "Correct123")
    payload = jwt.decode(t["access_token"], os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert payload["exp"] - payload["iat"] <= 30 * 60 and t["expires_in"] <= 1800
    r = refresh(t["refresh_token"])
    assert r.status_code == 200 and r.json()["refresh_token"] != t["refresh_token"]
    assert me(r.json()["access_token"]).status_code == 200
    assert db.sessions.find_one({"jti": t["session_id"]})["rotations"] == 1


def test_expired_access_can_refresh(user):
    t = login(user, "Correct123")
    p = jwt.decode(t["access_token"], os.environ["JWT_SECRET"], algorithms=["HS256"])
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({**p, "iat": past - timedelta(minutes=15), "exp": past}, os.environ["JWT_SECRET"], algorithm="HS256")
    r = me(expired)
    assert r.status_code == 401 and "expired" in r.json()["detail"].lower()
    n = refresh(t["refresh_token"])
    assert n.status_code == 200 and me(n.json()["access_token"]).status_code == 200


def test_refresh_reuse_revokes_session(user):
    t = login(user, "Correct123")
    new = refresh(t["refresh_token"]).json()
    reuse = refresh(t["refresh_token"])
    assert reuse.status_code == 401 and "reuse" in reuse.json()["detail"].lower()
    assert refresh(new["refresh_token"]).status_code == 401  # whole session revoked
    assert me(new["access_token"]).status_code == 401
    s = db.sessions.find_one({"jti": t["session_id"]})
    assert s["revoked_reason"] == "refresh_token_reuse"
    assert db.audit_logs.find_one({"action": "auth.refresh_reuse_detected", "entity_id": t["session_id"]})


def test_logout_invalidates_access_and_refresh(user):
    t = login(user, "Correct123")
    assert requests.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {t['access_token']}"}).status_code == 200
    assert me(t["access_token"]).status_code == 401
    assert refresh(t["refresh_token"]).status_code == 401


def test_logout_all_and_session_list(user):
    a, b = login(user, "Correct123"), login(user, "Correct123")
    lst = requests.get(f"{API}/auth/sessions", headers={"Authorization": f"Bearer {a['access_token']}"}).json()["items"]
    assert len(lst) >= 2 and any(s["current"] for s in lst)
    assert all("refresh_hash" not in s for s in lst)
    # revoke one specific device
    assert requests.delete(f"{API}/auth/sessions/{b['session_id']}", headers={"Authorization": f"Bearer {a['access_token']}"}).status_code == 200
    assert me(b["access_token"]).status_code == 401 and me(a["access_token"]).status_code == 200
    c = login(user, "Correct123")
    r = requests.post(f"{API}/auth/logout-all", headers={"Authorization": f"Bearer {a['access_token']}"}).json()
    assert r["revoked"] >= 2
    for t in (a, c):
        assert me(t["access_token"]).status_code == 401 and refresh(t["refresh_token"]).status_code == 401
    assert db.sessions.count_documents({"user_id": str(db.users.find_one({"email": user})["_id"]), "revoked": True}) >= 3


def test_refresh_token_is_not_an_access_token(user):
    t = login(user, "Correct123")
    assert me(t["refresh_token"]).status_code == 401
    assert refresh("x" * 40).status_code == 401


# ---------------------------------------------------------------- demo-mode safety
def test_production_with_demo_mode_fails_startup():
    env = {**os.environ, "APP_ENV": "production", "DEMO_MODE": "true"}
    r = subprocess.run([sys.executable, "-c", "import server"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "UNSAFE CONFIG" in r.stderr


def test_defaults_are_production_safe():
    env = {k: v for k, v in os.environ.items() if k not in ("APP_ENV", "DEMO_MODE")}
    code = "import core; print(core.APP_ENV, core.DEMO_MODE)"
    # core reads .env via load_dotenv; simulate a deployment whose .env lacks the keys
    r = subprocess.run([sys.executable, "-c", "import dotenv; dotenv.load_dotenv = lambda *a, **k: None; " + code],
                       cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.stdout.split() == ["production", "False"], r.stderr


def test_demo_disabled_hides_picker_and_requires_password():
    p = spawn(8013, DEMO_MODE="false", APP_ENV="production")
    try:
        base = "http://localhost:8013/api"
        assert requests.get(f"{base}/auth/demo-accounts").status_code == 404
        assert attempt("owner@sunrise.demo", "nope", ip(), base=base).status_code == 401
        for path in ["/auth/demo-login", "/auth/impersonate", "/auth/switch-role"]:
            assert requests.post(f"{base}{path}", json={"email": "owner@sunrise.demo"}).status_code in (404, 405)
    finally:
        p.kill()


# ---------------------------------------------------------------- file visibility regression
def test_is_public_asset_defaults_private():
    from routes_school import is_public_asset
    assert is_public_asset({"visibility": "brand", "purpose": "logo"})
    assert not is_public_asset({"visibility": "brand", "purpose": "document"})
    assert not is_public_asset({"purpose": "logo"})
    assert not is_public_asset({"visibility": "private", "purpose": "logo"})
    assert not is_public_asset({})


@pytest.mark.parametrize("doc_patch", [{"visibility": None}, {"visibility": "private"}, {"purpose": "report_card"},
                                       {"visibility": "public", "purpose": "student_document"}])
def test_private_variants_not_served_publicly(doc_patch):
    src = db.files.find_one({"visibility": "brand", "is_deleted": False})
    assert src, "needs at least one uploaded brand file"
    d = {k: v for k, v in src.items() if k != "_id"}
    d.update(doc_patch)
    fid = str(db.files.insert_one(d).inserted_id)
    try:
        assert requests.get(f"{API}/files/{fid}").status_code == 403
        assert requests.get(f"{API}/public/schools/sunrise-valley/brand").text.find(fid) == -1
    finally:
        db.files.delete_one({"_id": ObjectId(fid)})


def test_upload_cannot_choose_private_purpose_or_visibility():
    t = login("owner@greenfield.demo", "Demo@1234")
    sid = t["memberships"][0]["school_id"]
    h = {"Authorization": f"Bearer {t['access_token']}", "X-School-Id": sid}
    png = bytes.fromhex("89504e470d0a1a0a")
    assert requests.post(f"{API}/uploads?purpose=document", headers=h, files={"file": ("a.png", png, "image/png")}).status_code == 422
