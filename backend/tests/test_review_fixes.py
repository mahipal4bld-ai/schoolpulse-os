"""Independent-review fixes: private file caching/role scope, proxy-aware IP resolution, client error
reporting, production config guard."""
import os
import subprocess
import sys
import uuid

import requests
from bson import ObjectId

from test_m11_hardening import API, BACKEND, attempt, db, spawn

sys.path.insert(0, BACKEND)
from ratelimit import _trusted_networks, resolve_client_ip  # noqa: E402



def _login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Demo@1234"},
                      headers={"X-Forwarded-For": f"198.18.{uuid.uuid4().int % 250}.1"})
    d = r.json()
    return {"Authorization": f"Bearer {d['access_token']}", "X-School-Id": d["memberships"][0]["school_id"]}, d


def _private_file(slug):
    s = db.schools.find_one({"slug": slug})
    src = db.files.find_one({"school_id": str(s["_id"]), "visibility": "brand"}) or db.files.find_one({"visibility": "brand"})
    d = {k: v for k, v in src.items() if k != "_id"}
    d.update({"visibility": "private", "purpose": "document", "school_id": str(s["_id"])})
    return str(db.files.insert_one(d).inserted_id)


def test_private_file_headers_and_scope():
    fid = _private_file("greenfield-public")
    try:
        h, _ = _login("owner@greenfield.demo")
        r = requests.get(f"{API}/files/{fid}", headers={"Authorization": h["Authorization"]})
        assert r.status_code == 200
        cc = r.headers["cache-control"]
        assert "no-store" in cc and "private" in cc and "public" not in cc
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["content-disposition"] == "attachment"
        other, _ = _login("owner@sunrise.demo")
        assert requests.get(f"{API}/files/{fid}", headers={"Authorization": other["Authorization"]}).status_code == 403
        parent, _ = _login("parent@greenfield.demo")
        assert requests.get(f"{API}/files/{fid}", headers={"Authorization": parent["Authorization"]}).status_code == 403
        assert requests.get(f"{API}/files/{fid}").status_code == 403
    finally:
        db.files.delete_one({"_id": ObjectId(fid)})


def test_public_brand_asset_keeps_public_cache():
    f = db.files.find_one({"visibility": "brand", "purpose": {"$in": ["logo", "banner", "photo"]}, "is_deleted": False})
    r = requests.get(f"{API}/files/{f['_id']}")
    assert r.status_code == 200 and r.headers["cache-control"].startswith("public")


def test_resolve_client_ip_rules():
    nets = [__import__("ipaddress").ip_network("10.0.0.0/8")]
    assert resolve_client_ip("203.0.113.5", "1.2.3.4", nets) == "203.0.113.5"  # untrusted peer: header ignored
    assert resolve_client_ip("10.0.0.2", "1.2.3.4, 198.51.100.7", nets) == "198.51.100.7"  # right-most untrusted
    assert resolve_client_ip("10.0.0.2", "198.51.100.7, 10.1.1.1", nets) == "198.51.100.7"
    assert resolve_client_ip("10.0.0.2", "garbage", nets) == "10.0.0.2"
    assert resolve_client_ip("10.0.0.2", "", nets) == "10.0.0.2"
    assert _trusted_networks() is not None


def test_spoofed_xff_cannot_bypass_lockout_without_trusted_proxy():
    p = spawn(8014, TRUSTED_PROXY_CIDRS="")
    try:
        base = "http://localhost:8014/api"
        email = f"spoof-{uuid.uuid4().hex[:6]}@example.com"
        codes = [attempt(email, "x", f"198.51.100.{i}", base=base).status_code for i in range(8)]
        assert 429 in codes, codes  # rotating forged IPs did not reset the account+IP bucket
    finally:
        p.kill()


def test_client_error_reporting_scrubbed_and_capped():
    r = requests.post(f"{API}/client-errors", json={"kind": "render", "message": "boom"})
    assert r.status_code == 202
    assert requests.post(f"{API}/client-errors", json={"kind": "render", "message": "x" * 5000}).status_code == 422


def test_production_requires_strong_jwt_secret():
    env = {**os.environ, "APP_ENV": "production", "DEMO_MODE": "false", "JWT_SECRET": "replace-me"}
    r = subprocess.run([sys.executable, "-c", "import server"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "JWT_SECRET" in r.stderr
    env["JWT_SECRET"] = uuid.uuid4().hex * 2
    r = subprocess.run([sys.executable, "-c", "import core; core.assert_safe_config(); print('ok')"], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.stdout.strip() == "ok"
