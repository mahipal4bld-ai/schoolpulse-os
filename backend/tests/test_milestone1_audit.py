"""Milestone 1 verification-audit tests: uploads/private assets, logo replacement, demo-mode safety,
suspended tenant, student/teacher edit, persistence across backend restart (see audit report)."""
import os
import uuid

import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

API = "http://localhost:8001/api"
PW = "Demo@1234"
load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360f8cf00000301010018dd8db00000000049454e44ae426082")


def login(email, password=PW):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()


def ctx(email, slug):
    tok, d = login(email)
    sid = next(m["school_id"] for m in d["memberships"] if m["school"]["slug"] == slug)
    return {"Authorization": f"Bearer {tok}", "X-School-Id": sid}, sid, tok


def upload(h, purpose="logo"):
    r = requests.post(f"{API}/uploads?purpose={purpose}", headers=h, files={"file": ("l.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_logo_upload_retrieve_replace_persist():
    h, sid, _ = ctx("owner@greenfield.demo", "greenfield-public")
    orig = requests.get(f"{API}/school", headers=h).json()["brand"]
    a = upload(h)
    assert requests.patch(f"{API}/school/brand", headers=h, json={"logo_file_id": a}).status_code == 200
    assert requests.get(f"{API}/school", headers=h).json()["brand"]["logo_file_id"] == a
    r = requests.get(f"{API}/files/{a}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == PNG
    b = upload(h)
    requests.patch(f"{API}/school/brand", headers=h, json={"logo_file_id": b})
    assert requests.get(f"{API}/school", headers=h).json()["brand"]["logo_file_id"] == b
    # restore original state
    body = {"logo_file_id": orig["logo_file_id"]} if orig.get("logo_file_id") else {"clear_logo": True}
    requests.patch(f"{API}/school/brand", headers=h, json=body)


def test_upload_rejections():
    h, _, _ = ctx("owner@greenfield.demo", "greenfield-public")
    assert requests.post(f"{API}/uploads", headers=h, files={"file": ("x.txt", b"hi", "text/plain")}).status_code == 400
    th, _, _ = ctx("teacher@greenfield.demo", "greenfield-public")
    assert requests.post(f"{API}/uploads", headers=th, files={"file": ("l.png", PNG, "image/png")}).status_code == 403
    assert requests.post(f"{API}/uploads", files={"file": ("l.png", PNG, "image/png")}).status_code == 401


def test_cannot_attach_other_schools_file():
    gh, _, _ = ctx("owner@greenfield.demo", "greenfield-public")
    fid = upload(gh)
    sh, _, _ = ctx("owner@sunrise.demo", "sunrise-valley")
    assert requests.patch(f"{API}/school/brand", headers=sh, json={"logo_file_id": fid}).status_code == 400


def test_private_asset_requires_membership():
    gh, gsid, gtok = ctx("owner@greenfield.demo", "greenfield-public")
    fid = upload(gh)
    src = db.files.find_one({"_id": ObjectId(fid)})
    priv = {k: v for k, v in src.items() if k != "_id"}
    priv["visibility"] = "private"
    pid = str(db.files.insert_one(priv).inserted_id)
    try:
        assert requests.get(f"{API}/files/{pid}").status_code == 403
        _, _, stok = ctx("owner@sunrise.demo", "sunrise-valley")
        assert requests.get(f"{API}/files/{pid}", headers={"Authorization": f"Bearer {stok}"}).status_code == 403
        assert requests.get(f"{API}/files/{pid}?token=garbage").status_code == 403
        assert requests.get(f"{API}/files/{pid}", headers={"Authorization": f"Bearer {gtok}"}).status_code == 200
    finally:
        db.files.delete_one({"_id": ObjectId(pid)})


def test_demo_endpoint_never_issues_tokens():
    r = requests.get(f"{API}/auth/demo-accounts")
    assert r.status_code == 200  # DEMO_MODE=true in preview
    txt = r.text.lower()
    assert "access_token" not in txt and "password_hash" not in txt
    # there is no endpoint that logs in without a password
    for path in ["/auth/demo-login", "/auth/switch-role", "/auth/impersonate"]:
        assert requests.post(f"{API}{path}", json={"email": "owner@sunrise.demo"}).status_code in (404, 405)
    assert requests.post(f"{API}/auth/login", json={"email": "owner@sunrise.demo", "password": ""}).status_code == 422


def test_client_supplied_role_or_school_not_trusted():
    h, sid, tok = ctx("teacher@sunrise.demo", "sunrise-valley")
    h2 = {**h, "X-Role": "owner"}
    assert requests.patch(f"{API}/school/brand", headers=h2, json={"primary": "#000000"}).status_code == 403
    assert requests.get(f"{API}/dashboard/owner", headers=h2).status_code == 403
    assert requests.get(f"{API}/students", headers={"Authorization": f"Bearer {tok}"}).status_code == 400


def test_suspended_school_blocked_and_hidden():
    sa, _ = login("superadmin@schoolpulse.demo")
    sah = {"Authorization": f"Bearer {sa}"}
    slug = f"audit-{uuid.uuid4().hex[:6]}"
    email = f"{slug}@example.com"
    s = requests.post(f"{API}/platform/schools", headers=sah, json={"name": "Audit School", "slug": slug, "city": "Pune",
                                                                    "owner_name": "Audit Owner", "owner_email": email,
                                                                    "owner_password": "Password123"}).json()
    try:
        tok, d = login(email, "Password123")
        h = {"Authorization": f"Bearer {tok}", "X-School-Id": s["id"]}
        assert requests.get(f"{API}/school", headers=h).status_code == 200
        requests.patch(f"{API}/platform/schools/{s['id']}", headers=sah, json={"status": "suspended"})
        assert requests.get(f"{API}/school", headers=h).status_code == 403
        assert requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["memberships"] == []
    finally:
        uid = str(db.users.find_one({"email": email})["_id"])
        db.memberships.delete_many({"school_id": s["id"]})
        db.audit_logs.delete_many({"school_id": s["id"]})
        db.schools.delete_one({"_id": ObjectId(s["id"])})
        db.users.delete_one({"_id": ObjectId(uid)})


def test_student_edit_and_move_section():
    h, sid, _ = ctx("admin@sunrise.demo", "sunrise-valley")
    secs = requests.get(f"{API}/sections?page_size=100", headers=h).json()["items"]
    adm = f"E{uuid.uuid4().hex[:6].upper()}"
    st = requests.post(f"{API}/students", headers=h, json={"admission_no": adm, "first_name": "Edit", "gender": "male",
                                                           "dob": "2016-02-02", "section_id": secs[0]["id"]}).json()
    r = requests.patch(f"{API}/students/{st['id']}", headers=h, json={"first_name": "Edited", "roll_no": 7, "section_id": secs[-1]["id"]})
    assert r.status_code == 200
    got = requests.get(f"{API}/students/{st['id']}", headers=h).json()
    assert got["first_name"] == "Edited" and got["roll_no"] == 7 and got["section_id"] == secs[-1]["id"]
    assert got["class_name"] == secs[-1]["class_name"]
    requests.delete(f"{API}/students/{st['id']}", headers=h)
    archived = requests.get(f"{API}/students?status=archived&q={adm}", headers=h).json()
    assert archived["total"] == 1
    db.students.delete_one({"_id": ObjectId(st["id"])})


def test_teacher_edit_and_deactivate():
    h, _, _ = ctx("principal@sunrise.demo", "sunrise-valley")
    t = requests.post(f"{API}/teachers", headers=h, json={"name": "Audit Teacher", "email": f"a{uuid.uuid4().hex[:6]}@example.com",
                                                          "phone": "9811111111"}).json()
    r = requests.patch(f"{API}/teachers/{t['id']}", headers=h, json={"designation": "HOD", "status": "inactive"})
    assert r.status_code == 200 and r.json()["status"] == "inactive"
    assert requests.delete(f"{API}/teachers/{t['id']}", headers=h).status_code == 200


def test_principal_and_admin_cannot_edit_brand_but_can_manage_academics():
    for email in ["principal@sunrise.demo", "admin@sunrise.demo"]:
        h, _, _ = ctx(email, "sunrise-valley")
        assert requests.patch(f"{API}/school/brand", headers=h, json={"primary": "#000000"}).status_code == 403
        assert requests.get(f"{API}/subjects", headers=h).status_code == 200
    h, _, _ = ctx("admin@sunrise.demo", "sunrise-valley")
    assert requests.get(f"{API}/audit-logs", headers=h).status_code == 403  # admin lacks audit.view
    assert requests.patch(f"{API}/school/settings", headers=h, json={"tagline": "x"}).status_code == 403
