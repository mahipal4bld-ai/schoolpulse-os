"""Audit remediation — document-level file permissions + one-time download grants (negative-access regression)."""
import time

import requests
from bson import ObjectId

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import PDF, _d, _teacher_slot

ROOT = API.rsplit("/api", 1)[0]


def _auth(h):
    return {"Authorization": h["Authorization"]}


def _setup():
    """Admin publishes homework with an attachment in the demo teacher's section (teacher is NOT the uploader)."""
    th = login("teacher@sunrise.demo")
    sec, sub, tid = _teacher_slot(th)
    admin = login("admin@sunrise.demo")
    fid = requests.post(f"{API}/homework/attachments", headers=admin, files={"file": ("a.pdf", PDF, "application/pdf")}).json()["id"]
    hid = requests.post(f"{API}/homework", headers=admin, json={"section_id": sec, "subject_id": sub, "title": "ACLTEST",
                                                                "due_date": _d(1), "attachments": [fid], "publish": True}).json()["id"]
    return th, admin, sec, sub, tid, fid, hid


TEMP = []  # (collection, _id) created by these tests; isolated from shared demo records used by parallel suites


def _temp_user(school_id, role):
    import uuid

    import bcrypt
    from datetime import datetime, timezone
    email = f"acl-{role}-{uuid.uuid4().hex[:8]}@schoolpulse-acl.com"
    uid = db.users.insert_one({"email": email, "name": f"ACL {role}", "status": "active", "preferred_language": "en",
                               "password_hash": bcrypt.hashpw(b"Demo@1234", bcrypt.gensalt(4)).decode(),
                               "created_at": datetime.now(timezone.utc)}).inserted_id
    mid = db.memberships.insert_one({"school_id": school_id, "user_id": str(uid), "role": role, "status": "active",
                                     "created_at": datetime.now(timezone.utc)}).inserted_id
    TEMP.extend([("users", uid), ("memberships", mid)])
    return email, str(uid), mid


def _temp_parent(school_id, student_id):
    email, uid, mid = _temp_user(school_id, "parent")
    gid = db.guardians.insert_one({"school_id": school_id, "name": "ACL Guardian", "user_id": uid, "email": email}).inserted_id
    lid = db.guardian_links.insert_one({"school_id": school_id, "student_id": student_id, "guardian_id": str(gid),
                                        "relation": "guardian", "verified": True}).inserted_id
    TEMP.extend([("guardians", gid), ("guardian_links", lid)])
    return login(email), lid, mid


def _temp_teacher(school_id, section_id, subject_id):
    email, uid, mid = _temp_user(school_id, "teacher")
    tid = db.teachers.insert_one({"school_id": school_id, "name": "ACL Teacher", "user_id": uid, "status": "active",
                                  "email": email}).inserted_id
    aid = db.teacher_assignments.insert_one({"school_id": school_id, "teacher_id": str(tid), "section_id": section_id,
                                             "subject_id": subject_id, "is_class_teacher": False}).inserted_id
    TEMP.extend([("teachers", tid), ("teacher_assignments", aid)])
    return login(email), aid, mid


def _drop_temp():
    while TEMP:
        c, i = TEMP.pop()
        db[c].delete_one({"_id": i})


def test_role_and_document_level_matrix():
    th, admin, sec, sub, tid, fid, hid = _setup()
    url = f"{API}/files/{fid}"
    try:
        assert requests.get(url, headers=_auth(admin)).status_code == 200  # academic leadership
        assert requests.get(url, headers=_auth(login("principal@sunrise.demo"))).status_code == 200
        assert requests.get(url, headers=_auth(th)).status_code == 200  # assigned teacher (not uploader)
        ph, kid = _parent_for_section(sec)
        assert requests.get(url, headers=_auth(ph)).status_code == 200  # verified guardian of a child in the section
        # accountant / admission / transport staff denied
        acc = login("accountant@sunrise.demo")
        assert requests.get(url, headers=_auth(acc)).status_code == 403
        assert requests.post(f"{API}/files/{fid}/download-grant", headers=acc).status_code == 403  # grants obey policy
        for role in ("transport_coordinator", "admission_coordinator"):
            email, _, _ = _temp_user(th["X-School-Id"], role)
            h = login(email)
            assert requests.get(url, headers=_auth(h)).status_code == 403
            assert requests.post(f"{API}/files/{fid}/download-grant", headers=h).status_code == 403
        # other school
        g = login("owner@greenfield.demo")
        assert requests.get(url, headers=_auth(g)).status_code == 403
        assert requests.post(f"{API}/files/{fid}/download-grant", headers=g).status_code == 404
        # a parent with no child in that section
        others = [x for x in db.guardian_links.find({"verified": True})
                  if db.students.find_one({"_id": ObjectId(x["student_id"]), "section_id": {"$ne": sec}, "school_id": th["X-School-Id"]})]
        stranger = None
        for lk in others:
            gd = db.guardians.find_one({"_id": ObjectId(lk["guardian_id"]), "user_id": {"$ne": None}})
            if gd:
                kids = [x["student_id"] for x in db.guardian_links.find({"guardian_id": lk["guardian_id"], "verified": True})]
                if not db.students.find_one({"_id": {"$in": [ObjectId(k) for k in kids]}, "section_id": sec}):
                    stranger = db.users.find_one({"_id": ObjectId(gd["user_id"])})
                    break
        if stranger:
            assert requests.get(url, headers=_auth(login(stranger["email"]))).status_code == 403
        # teacher not assigned to the section: admin homework in a foreign section
        mine = set(db.teacher_assignments.distinct("section_id", {"teacher_id": tid}))
        other_sec = next(str(s["_id"]) for s in db.sections.find({"school_id": th["X-School-Id"]}) if str(s["_id"]) not in mine)
        f2 = requests.post(f"{API}/homework/attachments", headers=admin, files={"file": ("b.pdf", PDF, "application/pdf")}).json()["id"]
        requests.post(f"{API}/homework", headers=admin, json={"section_id": other_sec, "subject_id": sub, "title": "ACLTEST2",
                                                              "due_date": _d(1), "attachments": [f2], "publish": True})
        assert requests.get(f"{API}/files/{f2}", headers=_auth(th)).status_code == 403
        assert requests.get(f"{API}/files/{f2}", headers=_auth(ph)).status_code in (200, 403)  # depends on sibling sections
        # unknown private purpose: only uploader/owner/principal
        d = {k: v for k, v in db.files.find_one({"_id": ObjectId(fid)}).items() if k != "_id"}
        d.update({"purpose": "student_document", "uploaded_by": "someone-else"})
        f3 = str(db.files.insert_one(d).inserted_id)
        try:
            assert requests.get(f"{API}/files/{f3}", headers=_auth(admin)).status_code == 403
            assert requests.get(f"{API}/files/{f3}", headers=_auth(th)).status_code == 403
            assert requests.get(f"{API}/files/{f3}", headers=_auth(login("owner@sunrise.demo"))).status_code == 200
        finally:
            db.files.delete_one({"_id": ObjectId(f3)})
    finally:
        _drop_temp()
        db.homework.delete_many({"title": {"$regex": "^ACLTEST"}})


def test_revocations_take_effect_immediately():
    th, admin, sec, sub, tid, fid, hid = _setup()
    url = f"{API}/files/{fid}"
    school = th["X-School-Id"]
    kid = str(db.students.find_one({"section_id": sec, "status": "active"})["_id"])
    try:
        ph, lid, pmid = _temp_parent(school, kid)
        assert requests.get(url, headers=_auth(ph)).status_code == 200
        db.guardian_links.update_one({"_id": lid}, {"$set": {"verified": False}})  # link revoked
        assert requests.get(url, headers=_auth(ph)).status_code == 403
        db.guardian_links.update_one({"_id": lid}, {"$set": {"verified": True}})
        assert requests.get(url, headers=_auth(ph)).status_code == 200
        tt, aid, tmid = _temp_teacher(school, sec, sub)
        assert requests.get(url, headers=_auth(tt)).status_code == 200
        grant = requests.post(f"{API}/files/{fid}/download-grant", headers=tt).json()
        db.teacher_assignments.delete_one({"_id": aid})  # assignment revoked after the grant was issued
        assert requests.get(url, headers=_auth(tt)).status_code == 403
        assert requests.get(f"{ROOT}{grant['url']}").status_code == 403
        db.memberships.update_one({"_id": pmid}, {"$set": {"status": "suspended"}})  # membership revoked
        assert requests.get(url, headers=_auth(ph)).status_code == 403
        db.memberships.update_one({"_id": pmid}, {"$set": {"status": "active"}})
        requests.delete(f"{API}/homework/{hid}", headers=admin)  # homework withdrawn -> parent loses access
        assert requests.get(url, headers=_auth(ph)).status_code == 403
    finally:
        _drop_temp()
        db.homework.delete_many({"title": {"$regex": "^ACLTEST"}})


def test_download_grants_are_single_use_short_lived_and_tokenless():
    th, admin, sec, sub, tid, fid, hid = _setup()
    try:
        access = th["Authorization"].split()[1]
        assert requests.get(f"{API}/files/{fid}?token={access}").status_code == 401  # URL access tokens rejected
        g = requests.post(f"{API}/files/{fid}/download-grant", headers=th)
        assert g.status_code == 200
        g = g.json()
        assert access not in g["url"] and g["url"].startswith("/api/downloads/") and g["expires_in"] == 60
        doc = db.download_grants.find_one({"ref.file_id": fid, "used": False})
        assert doc and g["url"].rsplit("/", 1)[1] not in str(doc)  # only the hash is stored
        r = requests.get(f"{ROOT}{g['url']}")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert "no-store" in r.headers["Cache-Control"] and r.headers["Referrer-Policy"] == "no-referrer"
        assert requests.get(f"{ROOT}{g['url']}").status_code == 404  # second use
        g2 = requests.post(f"{API}/files/{fid}/download-grant", headers=th).json()
        db.download_grants.update_one({"ref.file_id": fid, "used": False}, {"$set": {"expires_at": db.download_grants.find_one(
            {"ref.file_id": fid, "used": False})["created_at"]}})
        assert requests.get(f"{ROOT}{g2['url']}").status_code == 404  # expired
        assert requests.get(f"{ROOT}/api/downloads/not-a-real-grant").status_code == 404
        assert requests.post(f"{API}/files/{fid}/download-grant").status_code == 401
        time.sleep(0.2)
        import os
        paths = os.environ.get("BACKEND_LOG_FILES", "/var/log/supervisor/backend.out.log,/var/log/supervisor/backend.err.log")
        log = "".join(open(p).read()[-50000:] for p in paths.split(",") if os.path.exists(p))
        assert log, "backend access log not found (set BACKEND_LOG_FILES)"
        assert "/api/downloads/[redacted]" in log and g["url"].rsplit("/", 1)[1] not in log  # redacted from access logs
    finally:
        db.homework.delete_many({"title": {"$regex": "^ACLTEST"}})
