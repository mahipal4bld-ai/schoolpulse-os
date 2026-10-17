"""Milestone 2 Module 6 — examinations integration tests (fictional demo data)."""
from datetime import datetime, timedelta, timezone

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import _teacher_slot

IST = timezone(timedelta(hours=5, minutes=30))


def _d(n=0):
    return (datetime.now(IST).date() + timedelta(days=n)).isoformat()


def _cleanup():
    ids = [str(e["_id"]) for e in db.exams.find({"name": {"$regex": "^TEST "}})]
    db.exam_marks.delete_many({"exam_id": {"$in": ids}})
    db.exams.delete_many({"name": {"$regex": "^TEST "}})


def _school(h):
    return h["X-School-Id"]


def test_full_exam_flow_marks_publish_parent_report_card():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, sub, _ = _teacher_slot(th)
    admin = login("admin@sunrise.demo")
    bad = requests.post(f"{API}/exams", headers=admin, json={"name": "TEST bad", "start_date": _d(5), "end_date": _d(1),
                                                            "section_ids": [sec], "subjects": [{"subject_id": sub, "max_marks": 50, "pass_marks": 17}]})
    assert bad.status_code == 400
    assert requests.post(f"{API}/exams", headers=admin, json={"name": "TEST bad2", "start_date": _d(), "end_date": _d(1), "section_ids": [sec],
                                                              "subjects": [{"subject_id": sub, "max_marks": 50, "pass_marks": 60}]}).status_code == 422
    r = requests.post(f"{API}/exams", headers=admin, json={"name": "TEST Unit Test 1", "term": "Term 1", "start_date": _d(), "end_date": _d(3),
                                                          "section_ids": [sec], "subjects": [{"subject_id": sub, "max_marks": 50, "pass_marks": 17}]})
    assert r.status_code == 201 and r.json()["status"] == "marks_open" and r.json()["progress"] == {"entered": 0, "total": 1}
    eid = r.json()["id"]
    # teacher sees it and enters marks
    assert any(e["id"] == eid for e in requests.get(f"{API}/exams", headers=th).json()["items"])
    sheet = requests.get(f"{API}/exams/{eid}/marks?section_id={sec}&subject_id={sub}", headers=th).json()
    studs = sheet["students"]
    recs = [{"student_id": s["id"], "marks": 40 - i % 30} for i, s in enumerate(studs)]
    recs[1] = {"student_id": studs[1]["id"], "absent": True}
    base = f"{API}/exams/{eid}/marks?section_id={sec}&subject_id={sub}"
    assert requests.put(base, headers=th, json={"records": recs[:-1]}).status_code == 400  # everyone required
    over = [dict(x) for x in recs]
    over[0]["marks"] = 51
    assert requests.put(base, headers=th, json={"records": over}).status_code == 400
    frac = [dict(x) for x in recs]
    frac[0]["marks"] = 10.3
    assert requests.put(base, headers=th, json={"records": frac}).status_code == 400
    ok = requests.put(base, headers=th, json={"records": recs})
    assert ok.status_code == 200 and ok.json()["entered"]
    res = requests.get(f"{API}/exams/{eid}/results?section_id={sec}", headers=admin).json()
    top = min((r for r in res["rows"] if r["rank"]), key=lambda r: r["rank"])
    assert top["rank"] == 1 and top["grade"] and res["class_average"] is not None
    absent_row = next(r for r in res["rows"] if r["student_id"] == studs[1]["id"])
    assert absent_row["result"] == "Fail" and absent_row["subjects"][0]["absent"]
    # parent cannot see before publish
    ph, kid = _parent_for_section(sec)
    assert all(e["id"] != eid for e in requests.get(f"{API}/parent/children/{kid}/exams", headers=ph).json()["items"])
    pdf_url = f"{API}/exams/{eid}/report-card/{kid}.pdf"
    assert requests.get(pdf_url, headers=ph).status_code == 403
    assert requests.post(f"{API}/exams/{eid}/report-card/{kid}/download-grant", headers=ph).status_code == 403
    # teacher cannot publish; admin publishes; marks lock
    assert requests.post(f"{API}/exams/{eid}/status?status=published", headers=th).status_code == 403
    pub = requests.post(f"{API}/exams/{eid}/status?status=published", headers=admin)
    assert pub.status_code == 200 and pub.json()["status"] == "published"
    assert requests.put(base, headers=th, json={"records": recs}).status_code == 400
    pe = next(e for e in requests.get(f"{API}/parent/children/{kid}/exams", headers=ph).json()["items"] if e["id"] == eid)
    assert pe["percentage"] is not None and pe["subjects"][0]["subject"]
    pdf = requests.get(pdf_url, headers=ph)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and "no-store" in pdf.headers["Cache-Control"]
    token = ph["Authorization"].split()[1]
    assert requests.get(f"{pdf_url}?school={_school(ph)}&token={token}").status_code == 401  # URL tokens rejected
    assert requests.get(pdf_url).status_code == 401
    g = requests.post(f"{API}/exams/{eid}/report-card/{kid}/download-grant", headers=ph).json()
    assert token not in g["url"] and g["expires_in"] <= 60
    first = requests.get(f"{API.rsplit('/api', 1)[0]}{g['url']}")
    assert first.status_code == 200 and first.content[:4] == b"%PDF" and first.headers["Referrer-Policy"] == "no-referrer"
    assert requests.get(f"{API.rsplit('/api', 1)[0]}{g['url']}").status_code == 404  # single use
    owner = login("owner@sunrise.demo")
    s = requests.get(f"{API}/exams/summary/recent", headers=owner).json()
    assert any(x["id"] == eid and x["average"] is not None for x in s["items"])
    assert requests.delete(f"{API}/exams/{eid}", headers=admin).status_code == 400  # published
    assert db.audit_logs.find_one({"action": "exam.publish", "entity_id": eid})
    _cleanup()


def test_publish_blocked_until_complete_and_access_rules():
    _cleanup()
    th = login("teacher@sunrise.demo")
    sec, sub, tid = _teacher_slot(th)
    admin = login("admin@sunrise.demo")
    subs = [s["id"] for s in requests.get(f"{API}/subjects?page_size=10", headers=admin).json()["items"]]
    other_sub = next(s for s in subs if s != sub)
    eid = requests.post(f"{API}/exams", headers=admin, json={"name": "TEST Mid", "start_date": _d(), "end_date": _d(2), "section_ids": [sec],
                                                            "subjects": [{"subject_id": sub, "max_marks": 100, "pass_marks": 33},
                                                                         {"subject_id": other_sub, "max_marks": 100, "pass_marks": 33}]}).json()["id"]
    p = requests.post(f"{API}/exams/{eid}/status?status=published", headers=admin)
    assert p.status_code == 400 and "missing" in p.json()["detail"]
    # teacher may only enter subjects they teach (unless class teacher)
    is_ct = db.teacher_assignments.find_one({"teacher_id": tid, "section_id": sec, "is_class_teacher": True})
    code = requests.get(f"{API}/exams/{eid}/marks?section_id={sec}&subject_id={other_sub}", headers=th).status_code
    assert code == (200 if is_ct or db.teacher_assignments.find_one({"teacher_id": tid, "section_id": sec, "subject_id": other_sub}) else 403)
    g = login("owner@greenfield.demo")
    assert requests.get(f"{API}/exams/{eid}", headers=g).status_code == 404
    assert requests.get(f"{API}/exams/{eid}/results?section_id={sec}", headers=g).status_code == 404
    ph = login("parent@sunrise.demo")
    assert requests.get(f"{API}/exams", headers=ph).status_code == 403
    assert requests.post(f"{API}/exams", headers=th, json={"name": "TEST t", "start_date": _d(), "end_date": _d(), "section_ids": [sec],
                                                           "subjects": [{"subject_id": sub, "max_marks": 10, "pass_marks": 3}]}).status_code == 403
    kids = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    stranger = next(s["id"] for s in requests.get(f"{API}/students?page_size=50", headers=admin).json()["items"] if s["id"] not in kids)
    assert requests.get(f"{API}/parent/children/{stranger}/exams", headers=ph).status_code == 403
    assert requests.delete(f"{API}/exams/{eid}", headers=admin).status_code == 200
    _cleanup()
