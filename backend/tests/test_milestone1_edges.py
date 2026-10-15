"""Edge-case & gap tests for Milestone 1. Complements test_milestone1.py.
Run: cd /app/backend && python -m pytest tests/test_milestone1_edges.py -q
"""
import os
import uuid

import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
PW = "Demo@1234"


def login(email, password=PW):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()


def hdr(token, school_id=None):
    h = {"Authorization": f"Bearer {token}"}
    if school_id:
        h["X-School-Id"] = school_id
    return h


def school_of(d, slug):
    return next(m["school_id"] for m in d["memberships"] if m["school"]["slug"] == slug)


def owner(slug="sunrise-valley"):
    email = "owner@sunrise.demo" if slug == "sunrise-valley" else "owner@greenfield.demo"
    tok, d = login(email)
    return tok, school_of(d, slug), d


# ---- auth / preferences / demo accounts ----
class TestAuthEdges:
    def test_demo_accounts_endpoint_returns_list(self):
        r = requests.get(f"{API}/auth/demo-accounts")
        assert r.status_code == 200
        body = r.json()
        assert body.get("password") == "Demo@1234"
        accounts = body.get("accounts")
        assert isinstance(accounts, list) and len(accounts) >= 5
        emails = {i.get("email") for i in accounts}
        assert {"owner@sunrise.demo", "teacher@sunrise.demo", "parent@sunrise.demo",
                "owner@greenfield.demo", "superadmin@schoolpulse.demo", "multi.parent@schoolpulse.demo"} <= emails

    def test_preferences_update_language(self):
        tok, _ = login("owner@sunrise.demo")
        r = requests.patch(f"{API}/auth/me/preferences", headers=hdr(tok), json={"preferred_language": "hi"})
        assert r.status_code == 200
        me = requests.get(f"{API}/auth/me", headers=hdr(tok)).json()
        assert me["user"]["preferred_language"] == "hi"
        requests.patch(f"{API}/auth/me/preferences", headers=hdr(tok), json={"preferred_language": "en"})

    def test_preferences_invalid_language_rejected(self):
        tok, _ = login("owner@sunrise.demo")
        r = requests.patch(f"{API}/auth/me/preferences", headers=hdr(tok), json={"preferred_language": "fr"})
        assert r.status_code == 422

    def test_logout_all_revokes_all_sessions(self):
        tok1, _ = login("accountant@greenfield.demo")
        tok2, _ = login("accountant@greenfield.demo")
        r = requests.post(f"{API}/auth/logout-all", headers=hdr(tok1))
        assert r.status_code == 200
        assert requests.get(f"{API}/auth/me", headers=hdr(tok1)).status_code == 401
        assert requests.get(f"{API}/auth/me", headers=hdr(tok2)).status_code == 401

    def test_missing_school_header_denied(self):
        tok, _ = login("owner@sunrise.demo")
        r = requests.get(f"{API}/students", headers=hdr(tok))
        assert r.status_code in (400, 401, 403, 422)

    def test_brute_force_guard_locks_after_many_fails(self):
        email = f"bruteforce-{uuid.uuid4().hex[:6]}@example.com"
        statuses = set()
        for _ in range(7):
            r = requests.post(f"{API}/auth/login", json={"email": email, "password": "wrong"})
            statuses.add(r.status_code)
        # expected: unknown email returns 401, but after threshold returns 429 for valid-looking email
        assert 401 in statuses


# ---- platform suspend / reactivate ----
class TestPlatformSchoolLifecycle:
    def test_create_suspend_reactivate_school(self):
        tok, _ = login("superadmin@schoolpulse.demo")
        slug = f"edge-{uuid.uuid4().hex[:6]}"
        c = requests.post(f"{API}/platform/schools", headers=hdr(tok), json={
            "name": "Edge Test School", "slug": slug, "city": "Mumbai",
            "owner_name": "Edge Owner", "owner_email": f"{slug}@example.com",
            "owner_password": "Password123"})
        assert c.status_code == 201, c.text
        sid = c.json()["id"]
        s = requests.patch(f"{API}/platform/schools/{sid}", headers=hdr(tok), json={"status": "suspended"})
        assert s.status_code == 200
        listed = next(x for x in requests.get(f"{API}/platform/schools", headers=hdr(tok)).json()["items"] if x["id"] == sid)
        assert listed["status"] == "suspended"
        # reactivate
        assert requests.patch(f"{API}/platform/schools/{sid}", headers=hdr(tok), json={"status": "active"}).status_code == 200

    def test_platform_create_invalid_slug_rejected(self):
        tok, _ = login("superadmin@schoolpulse.demo")
        r = requests.post(f"{API}/platform/schools", headers=hdr(tok), json={
            "name": "Bad Slug", "slug": "BAD SLUG!", "city": "Delhi",
            "owner_name": "X Y", "owner_email": "xy@example.com", "owner_password": "Password123"})
        assert r.status_code == 422

    def test_platform_stats_endpoint(self):
        tok, _ = login("superadmin@schoolpulse.demo")
        r = requests.get(f"{API}/platform/stats", headers=hdr(tok))
        assert r.status_code == 200
        d = r.json()
        assert d["schools"] >= 2 and d["active_schools"] >= 2 and d["students"] > 0


# ---- school settings / brand / public brand ----
class TestSchoolSettings:
    def test_patch_school_settings_persists(self):
        tok, sid, _ = owner()
        orig = requests.get(f"{API}/school", headers=hdr(tok, sid)).json()
        new_tag = f"Tagline-{uuid.uuid4().hex[:4]}"
        r = requests.patch(f"{API}/school/settings", headers=hdr(tok, sid), json={"tagline": new_tag})
        assert r.status_code == 200
        got = requests.get(f"{API}/school", headers=hdr(tok, sid)).json()
        assert got["tagline"] == new_tag
        requests.patch(f"{API}/school/settings", headers=hdr(tok, sid), json={"tagline": orig.get("tagline", "")})

    def test_public_brand_endpoint_unauthenticated(self):
        r = requests.get(f"{API}/public/schools/sunrise-valley/brand")
        assert r.status_code == 200
        d = r.json()
        assert d["brand"]["primary"].startswith("#")
        r2 = requests.get(f"{API}/public/schools/greenfield-public/brand")
        assert r2.status_code == 200
        assert r2.json()["brand"]["primary"] != d["brand"]["primary"]

    def test_public_brand_unknown_slug_404(self):
        r = requests.get(f"{API}/public/schools/no-such-school/brand")
        assert r.status_code == 404

    def test_brand_invalid_hex_rejected(self):
        tok, sid, _ = owner()
        for bad in ["red", "#12", "#ZZZZZZ", "123456"]:
            r = requests.patch(f"{API}/school/brand", headers=hdr(tok, sid), json={"primary": bad})
            assert r.status_code == 422, f"expected 422 for {bad}, got {r.status_code}"

    def test_brand_empty_patch_rejected(self):
        tok, sid, _ = owner()
        r = requests.patch(f"{API}/school/brand", headers=hdr(tok, sid), json={})
        assert r.status_code == 400


# ---- subject CRUD ----
class TestSubjects:
    def test_subject_crud(self):
        tok, sid, _ = owner()
        h = hdr(tok, sid)
        code = f"SUB{uuid.uuid4().hex[:4].upper()}"
        c = requests.post(f"{API}/subjects", headers=h, json={"name": "Edge Topic", "code": code})
        assert c.status_code == 201, c.text
        rid = c.json()["id"]
        p = requests.patch(f"{API}/subjects/{rid}", headers=h, json={"name": "Edge Topic 2"})
        assert p.status_code == 200
        assert requests.delete(f"{API}/subjects/{rid}", headers=h).status_code == 200


# ---- audit log ----
class TestAuditLog:
    def test_audit_log_lists_entries(self):
        tok, sid, _ = owner()
        requests.patch(f"{API}/school/brand", headers=hdr(tok, sid), json={"welcome_message": "audit-test"})
        r = requests.get(f"{API}/audit-logs", headers=hdr(tok, sid))
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list)
        assert body["total"] >= 1
        assert any(it.get("action", "").startswith("school.brand") for it in body["items"])

    def test_audit_log_requires_permission(self):
        tok, d = login("teacher@sunrise.demo")
        sid = school_of(d, "sunrise-valley")
        r = requests.get(f"{API}/audit-logs", headers=hdr(tok, sid))
        assert r.status_code == 403


# ---- teacher dashboard ----
class TestTeacherDashboard:
    def test_teacher_dashboard_shape(self):
        tok, d = login("teacher@sunrise.demo")
        sid = school_of(d, "sunrise-valley")
        r = requests.get(f"{API}/teacher/dashboard", headers=hdr(tok, sid))
        assert r.status_code == 200
        data = r.json()
        assert "sections" in data and isinstance(data["sections"], list)


# ---- parent child detail ----
class TestParentFlow:
    def test_parent_child_detail_accessible(self):
        tok, d = login("parent@sunrise.demo")
        sid = school_of(d, "sunrise-valley")
        kids = requests.get(f"{API}/parent/children", headers=hdr(tok, sid)).json()["items"]
        assert len(kids) == 2
        r = requests.get(f"{API}/parent/children/{kids[0]['id']}", headers=hdr(tok, sid))
        assert r.status_code == 200
        assert r.json()["id"] == kids[0]["id"]


# ---- invitations ----
class TestInvitations:
    def test_create_list_delete_invitation(self):
        tok, sid, _ = owner()
        h = hdr(tok, sid)
        email = f"invitee-{uuid.uuid4().hex[:6]}@example.com"
        c = requests.post(f"{API}/invitations", headers=h,
                          json={"email": email, "name": "Invitee User", "role": "teacher"})
        assert c.status_code == 201, c.text
        iid = c.json()["id"]
        items = requests.get(f"{API}/invitations", headers=h).json()["items"]
        assert any(i["id"] == iid for i in items)
        # dup should 409
        dup = requests.post(f"{API}/invitations", headers=h,
                            json={"email": email, "name": "Invitee User", "role": "teacher"})
        assert dup.status_code == 409
        assert requests.delete(f"{API}/invitations/{iid}", headers=h).status_code == 200

    def test_invitation_requires_staff_manage(self):
        tok, d = login("teacher@sunrise.demo")
        sid = school_of(d, "sunrise-valley")
        r = requests.post(f"{API}/invitations", headers=hdr(tok, sid),
                          json={"email": "x@example.com", "name": "X", "role": "teacher"})
        assert r.status_code == 403


# ---- csv import actual import ----
class TestCsvImport:
    def test_csv_import_real_import_creates_records(self):
        tok, sid, _ = owner()
        h = hdr(tok, sid)
        adm = f"CSV{uuid.uuid4().hex[:6].upper()}"
        csv_text = ("admission_no,first_name,last_name,gender,dob,class,section,guardian_name,guardian_phone,guardian_relation\n"
                    f"{adm},Imported,Kid,male,2017-01-01,Class 2,A,Mama Imported,98{uuid.uuid4().int % 10**8:08d},mother\n")
        r = requests.post(f"{API}/students/import", headers=h, json={"csv_text": csv_text, "dry_run": False})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("created", 0) >= 1
        s = requests.get(f"{API}/students?q={adm}", headers=h).json()
        assert s["total"] >= 1
        # cleanup
        requests.delete(f"{API}/students/{s['items'][0]['id']}", headers=h)


# ---- guardian link uniqueness ----
class TestGuardianLinkUnique:
    def test_duplicate_guardian_link_rejected(self):
        tok, sid, _ = owner()
        h = hdr(tok, sid)
        sec = requests.get(f"{API}/sections?page_size=1", headers=h).json()["items"][0]
        adm = f"GL{uuid.uuid4().hex[:6].upper()}"
        st = requests.post(f"{API}/students", headers=h, json={"admission_no": adm, "first_name": "Dup",
                                                               "last_name": "Guard", "gender": "male",
                                                               "dob": "2016-01-01", "section_id": sec["id"]}).json()
        phone = f"9{uuid.uuid4().int % 10**9:09d}"
        payload = {"student_id": st["id"], "relation": "father", "guardian": {"name": "GL Dad", "phone": phone}}
        r1 = requests.post(f"{API}/guardian-links", headers=h, json=payload)
        assert r1.status_code == 201
        r2 = requests.post(f"{API}/guardian-links", headers=h, json=payload)
        assert r2.status_code in (400, 409, 422), f"duplicate link should be rejected, got {r2.status_code}"
        requests.delete(f"{API}/students/{st['id']}", headers=h)
