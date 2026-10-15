"""Milestone 1 API tests. Run: cd /app/backend && python -m pytest tests/test_milestone1.py -q
Runs against the live local server (http://localhost:8001) using the fictional demo seed."""
import uuid

import requests

API = "http://localhost:8001/api"
PW = "Demo@1234"


def login(email, password=PW):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["access_token"], d


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
    return tok, school_of(d, slug)


# 1. school creation and retrieval
def test_super_admin_creates_and_lists_school():
    tok, _ = login("superadmin@schoolpulse.demo")
    slug = f"test-{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/platform/schools", headers=hdr(tok), json={
        "name": "Test Tenant School", "slug": slug, "city": "Delhi", "owner_name": "T Owner",
        "owner_email": f"{slug}@example.com", "owner_password": "Password123"})
    assert r.status_code == 201, r.text
    lst = requests.get(f"{API}/platform/schools", headers=hdr(tok)).json()
    assert any(s["slug"] == slug for s in lst["items"])
    # duplicate slug rejected
    r2 = requests.post(f"{API}/platform/schools", headers=hdr(tok), json={
        "name": "Dup", "slug": slug, "city": "Delhi", "owner_name": "XX", "owner_email": "x@example.com",
        "owner_password": "Password123"})
    assert r2.status_code == 409
    # new owner can log in and see own school
    t2, d2 = login(f"{slug}@example.com", "Password123")
    assert d2["memberships"][0]["role"] == "owner"


def test_non_admin_cannot_create_school():
    tok, _ = owner()
    r = requests.post(f"{API}/platform/schools", headers=hdr(tok), json={})
    assert r.status_code == 403


# 2. brand persistence
def test_brand_configuration_persists():
    tok, sid = owner()
    orig = requests.get(f"{API}/school", headers=hdr(tok, sid)).json()["brand"]
    r = requests.patch(f"{API}/school/brand", headers=hdr(tok, sid), json={"primary": "#123456", "welcome_message": "Test hello"})
    assert r.status_code == 200
    again = requests.get(f"{API}/school", headers=hdr(tok, sid)).json()["brand"]
    assert again["primary"] == "#123456" and again["welcome_message"] == "Test hello"
    bad = requests.patch(f"{API}/school/brand", headers=hdr(tok, sid), json={"primary": "red"})
    assert bad.status_code == 422
    requests.patch(f"{API}/school/brand", headers=hdr(tok, sid), json={"primary": orig["primary"], "welcome_message": orig["welcome_message"]})


def test_teacher_cannot_edit_brand():
    tok, d = login("teacher@sunrise.demo")
    sid = school_of(d, "sunrise-valley")
    r = requests.patch(f"{API}/school/brand", headers=hdr(tok, sid), json={"primary": "#000000"})
    assert r.status_code == 403


# 3. academic year & class creation
def test_year_class_section_subject_crud():
    tok, sid = owner()
    h = hdr(tok, sid)
    name = f"20{uuid.uuid4().int % 50 + 40}-{uuid.uuid4().int % 90 + 10}"
    y = requests.post(f"{API}/academic-years", headers=h, json={"name": name, "start_date": "2040-04-01", "end_date": "2041-03-31"})
    assert y.status_code in (201, 409), y.text
    if y.status_code == 409:
        return
    yid = y.json()["id"]
    c = requests.post(f"{API}/classes", headers=h, json={"name": "Class X", "academic_year_id": yid})
    assert c.status_code == 201
    cid = c.json()["id"]
    assert requests.post(f"{API}/classes", headers=h, json={"name": "Class X", "academic_year_id": yid}).status_code == 409
    s = requests.post(f"{API}/sections", headers=h, json={"class_id": cid, "name": "a"})
    assert s.status_code == 201 and s.json()["name"] == "A"
    assert requests.delete(f"{API}/classes/{cid}", headers=h).status_code == 409  # has section
    assert requests.delete(f"{API}/sections/{s.json()['id']}", headers=h).status_code == 200
    assert requests.delete(f"{API}/classes/{cid}", headers=h).status_code == 200
    assert requests.delete(f"{API}/academic-years/{yid}", headers=h).status_code == 200
    bad = requests.post(f"{API}/academic-years", headers=h, json={"name": "bad", "start_date": "2040-04-01", "end_date": "2039-01-01"})
    assert bad.status_code == 422


# 4. student creation and guardian linking
def test_student_create_and_guardian_link():
    tok, sid = owner()
    h = hdr(tok, sid)
    sec = requests.get(f"{API}/sections?page_size=1", headers=h).json()["items"][0]
    adm = f"T{uuid.uuid4().hex[:6].upper()}"
    st = requests.post(f"{API}/students", headers=h, json={"admission_no": adm, "first_name": "Test", "last_name": "Kid",
                                                           "gender": "female", "dob": "2016-05-05", "section_id": sec["id"]})
    assert st.status_code == 201, st.text
    sid_ = st.json()["id"]
    assert requests.post(f"{API}/students", headers=h, json={"admission_no": adm, "first_name": "Dup", "gender": "male",
                                                             "dob": "2016-05-05", "section_id": sec["id"]}).status_code == 409
    phone = f"9{uuid.uuid4().int % 10**9:09d}"
    ln = requests.post(f"{API}/guardian-links", headers=h, json={"student_id": sid_, "relation": "mother",
                                                                 "guardian": {"name": "Test Mom", "phone": phone}})
    assert ln.status_code == 201, ln.text
    detail = requests.get(f"{API}/students/{sid_}", headers=h).json()
    assert detail["guardians"][0]["guardian"]["phone"] == phone and detail["guardians"][0]["verified"] is False
    v = requests.patch(f"{API}/guardian-links/{ln.json()['id']}", headers=h, json={"verified": True})
    assert v.json()["verified"] is True
    assert requests.delete(f"{API}/students/{sid_}", headers=h).json()["status"] == "archived"


def test_student_validation():
    tok, sid = owner()
    r = requests.post(f"{API}/students", headers=hdr(tok, sid), json={"admission_no": "X1", "first_name": "", "gender": "x",
                                                                     "dob": "2999-01-01", "section_id": "nope"})
    assert r.status_code == 422


# 5. teacher-to-class assignment and teacher scoping
def test_teacher_assignment_and_scope():
    tok, sid = owner()
    h = hdr(tok, sid)
    email = f"t{uuid.uuid4().hex[:6]}@example.com"
    t = requests.post(f"{API}/teachers", headers=h, json={"name": "New Teacher", "email": email, "phone": "9876543210"})
    assert t.status_code == 201, t.text
    sec = requests.get(f"{API}/sections?page_size=1", headers=h).json()["items"][0]
    a = requests.post(f"{API}/teacher-assignments", headers=h, json={"teacher_id": t.json()["id"], "section_id": sec["id"]})
    assert a.status_code == 201
    got = requests.get(f"{API}/teachers/{t.json()['id']}", headers=h).json()
    assert got["assignments"][0]["section_id"] == sec["id"]
    # demo teacher only sees assigned sections
    tt, td = login("teacher@sunrise.demo")
    th = hdr(tt, school_of(td, "sunrise-valley"))
    dash = requests.get(f"{API}/teacher/dashboard", headers=th).json()
    allowed = {s["section_id"] for s in dash["sections"]}
    studs = requests.get(f"{API}/students?page_size=100", headers=th).json()["items"]
    assert studs and all(s["section_id"] in allowed for s in studs)
    other = [s for s in requests.get(f"{API}/sections?page_size=100", headers=h).json()["items"] if s["id"] not in allowed][0]
    assert requests.get(f"{API}/students?section_id={other['id']}", headers=th).status_code == 403


# 6. role permissions
def test_role_permissions():
    tok, d = login("accountant@sunrise.demo")
    sid = school_of(d, "sunrise-valley")
    assert requests.get(f"{API}/students", headers=hdr(tok, sid)).status_code == 200
    sec = requests.get(f"{API}/sections?page_size=1", headers=hdr(tok, sid)).json()["items"][0]
    r = requests.post(f"{API}/students", headers=hdr(tok, sid), json={"admission_no": "ACC1", "first_name": "A", "gender": "male",
                                                                     "dob": "2016-01-01", "section_id": sec["id"]})
    assert r.status_code == 403
    ptok, pd = login("parent@sunrise.demo")
    psid = school_of(pd, "sunrise-valley")
    assert requests.get(f"{API}/students", headers=hdr(ptok, psid)).status_code == 403
    kids = requests.get(f"{API}/parent/children", headers=hdr(ptok, psid)).json()["items"]
    assert len(kids) == 2
    allst = requests.get(f"{API}/students?page_size=100", headers=hdr(*owner())).json()["items"]
    foreign = next(s for s in allst if s["id"] not in {k["id"] for k in kids})
    assert requests.get(f"{API}/parent/children/{foreign['id']}", headers=hdr(ptok, psid)).status_code == 403


# 7. unauthenticated denial
def test_unauthenticated_denied():
    for path in ["/auth/me", "/students", "/school", "/dashboard/owner", "/platform/schools"]:
        assert requests.get(f"{API}{path}").status_code == 401, path
    assert requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert requests.post(f"{API}/auth/login", json={"email": "owner@sunrise.demo", "password": "wrong"}).status_code == 401


def test_logout_revokes_session():
    tok, _ = login("principal@sunrise.demo")
    assert requests.post(f"{API}/auth/logout", headers=hdr(tok)).status_code == 200
    assert requests.get(f"{API}/auth/me", headers=hdr(tok)).status_code == 401


# 8. cross-school denial
def test_cross_school_denied():
    tok, _ = owner("sunrise-valley")
    _, green_sid = owner("greenfield-public")
    assert requests.get(f"{API}/students", headers=hdr(tok, green_sid)).status_code == 403
    gtok, gsid = owner("greenfield-public")
    g_student = requests.get(f"{API}/students?page_size=1", headers=hdr(gtok, gsid)).json()["items"][0]
    _, sun_sid = owner("sunrise-valley")
    assert requests.get(f"{API}/students/{g_student['id']}", headers=hdr(tok, sun_sid)).status_code == 404
    # Sunrise owner cannot reference a Greenfield section
    g_sec = requests.get(f"{API}/sections?page_size=1", headers=hdr(gtok, gsid)).json()["items"][0]
    r = requests.post(f"{API}/students", headers=hdr(tok, sun_sid), json={"admission_no": "XS1", "first_name": "X", "gender": "male",
                                                                         "dob": "2016-01-01", "section_id": g_sec["id"]})
    assert r.status_code == 400
    # each school lists only its own records
    assert all(s["school_id"] == sun_sid for s in requests.get(f"{API}/students?page_size=100", headers=hdr(tok, sun_sid)).json()["items"])


def test_multi_school_parent_isolated_per_school():
    tok, d = login("multi.parent@schoolpulse.demo")
    assert len(d["memberships"]) == 2
    for m in d["memberships"]:
        kids = requests.get(f"{API}/parent/children", headers=hdr(tok, m["school_id"])).json()["items"]
        assert len(kids) == 1 and kids[0]["school_id"] == m["school_id"]


# 9. dashboard totals match records
def test_dashboard_totals_match_records():
    from pymongo import MongoClient
    import os
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for slug in ["sunrise-valley", "greenfield-public"]:
        tok, sid = owner(slug)
        c = requests.get(f"{API}/dashboard/owner", headers=hdr(tok, sid)).json()["counts"]
        assert c["students"] == db.students.count_documents({"school_id": sid, "status": "active"})
        assert c["teachers"] == db.teachers.count_documents({"school_id": sid, "status": "active"})
        assert c["sections"] == db.sections.count_documents({"school_id": sid})
        assert c["guardians"] == db.guardians.count_documents({"school_id": sid})
        listed = requests.get(f"{API}/students?page_size=1", headers=hdr(tok, sid)).json()["total"]
        assert listed == c["students"]


def test_csv_import_dry_run_and_errors():
    tok, sid = owner()
    csv_text = ("admission_no,first_name,last_name,gender,dob,class,section,guardian_name,guardian_phone,guardian_relation\n"
                "CSV1,Asha,Rao,female,2017-01-01,Class 2,A,Ravi Rao,9876512345,father\n"
                "CSV2,Bad,Row,female,2017-01-01,Class 99,A,Ravi Rao,9876512345,father\n")
    r = requests.post(f"{API}/students/import", headers=hdr(tok, sid), json={"csv_text": csv_text, "dry_run": True}).json()
    assert r["rows"] == 2 and r["valid"] == 1 and r["errors"][0]["row"] == 3 and r["created"] == 0


def test_pagination_and_search():
    tok, sid = owner()
    p1 = requests.get(f"{API}/students?page=1&page_size=10", headers=hdr(tok, sid)).json()
    p2 = requests.get(f"{API}/students?page=2&page_size=10", headers=hdr(tok, sid)).json()
    assert len(p1["items"]) == 10 and not {s["id"] for s in p1["items"]} & {s["id"] for s in p2["items"]}
    name = p1["items"][0]["first_name"]
    s = requests.get(f"{API}/students?q={name}", headers=hdr(tok, sid)).json()
    assert s["total"] >= 1 and all(name.lower() in (x["first_name"] + x["last_name"] + x["admission_no"]).lower() for x in s["items"])
