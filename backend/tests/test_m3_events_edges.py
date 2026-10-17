"""M3M3 extra probes: calendar/upcoming shape, cancel-draft silently, range boundaries, patch cancelled, bad act."""
from datetime import date, timedelta

import requests
from bson import ObjectId

from test_m11_hardening import API, db
from test_m2_attendance import login

D = date.today() + timedelta(days=4)


def _cleanup():
    db.events.delete_many({"title": {"$regex": "^ETEST2"}})


def test_upcoming_limit_shape_and_exclusion_of_cancelled():
    _cleanup()
    pr = login("principal@sunrise.demo")
    # Create and publish an event, then cancel with reason -> should NOT appear in upcoming
    base = {"start_date": D.isoformat(), "category": "sports"}
    pub = requests.post(f"{API}/events", headers=pr, json={**base, "title": "ETEST2 pub", "action": "publish"}).json()
    assert pub["status"] == "published"
    c = requests.post(f"{API}/events/{pub['id']}/action?act=cancel&reason=weather", headers=pr)
    assert c.status_code == 200
    u = requests.get(f"{API}/calendar/upcoming?limit=10", headers=pr)
    assert u.status_code == 200
    ids = [i["id"] for i in u.json()["items"]]
    assert pub["id"] not in ids
    # bounds on limit
    assert requests.get(f"{API}/calendar/upcoming?limit=0", headers=pr).status_code == 422
    assert requests.get(f"{API}/calendar/upcoming?limit=11", headers=pr).status_code == 422
    _cleanup()


def test_draft_cancel_is_allowed_without_reason():
    _cleanup()
    pr = login("principal@sunrise.demo")
    draft = requests.post(f"{API}/events", headers=pr, json={"title": "ETEST2 d", "start_date": D.isoformat()}).json()
    assert draft["status"] == "draft"
    c = requests.post(f"{API}/events/{draft['id']}/action?act=cancel", headers=pr)
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    # cannot patch a cancelled event
    r = requests.patch(f"{API}/events/{draft['id']}", headers=pr, json={"title": "ETEST2 z"})
    assert r.status_code == 400
    # cannot republish cancelled
    r = requests.post(f"{API}/events/{draft['id']}/action?act=publish", headers=pr)
    assert r.status_code == 409
    _cleanup()


def test_calendar_range_boundaries_and_bad_act():
    pr = login("principal@sunrise.demo")
    # start>end -> 400
    r = requests.get(f"{API}/calendar?start={D.isoformat()}&end={(D - timedelta(days=1)).isoformat()}", headers=pr)
    assert r.status_code == 400
    # 93 day span -> 400
    r = requests.get(f"{API}/calendar?start={D.isoformat()}&end={(D + timedelta(days=93)).isoformat()}", headers=pr)
    assert r.status_code == 400
    # Unknown act -> 422
    some = db.events.find_one({"school_id": pr["X-School-Id"], "demo": True})
    if some:
        r = requests.post(f"{API}/events/{some['_id']}/action?act=delete", headers=pr)
        assert r.status_code == 422
    # 404 for non-existent id
    r = requests.post(f"{API}/events/{ObjectId()}/action?act=publish", headers=pr)
    assert r.status_code == 404


def test_teacher_and_parent_cannot_create_or_patch():
    _cleanup()
    th = login("teacher@sunrise.demo")
    ph = login("parent@sunrise.demo")
    body = {"title": "ETEST2 nope", "start_date": D.isoformat()}
    assert requests.post(f"{API}/events", headers=th, json=body).status_code == 403
    assert requests.post(f"{API}/events", headers=ph, json=body).status_code == 403
    pr = login("principal@sunrise.demo")
    e = requests.post(f"{API}/events", headers=pr, json={**body, "action": "publish"}).json()
    assert requests.patch(f"{API}/events/{e['id']}", headers=th, json={"title": "ETEST2 hack"}).status_code == 403
    assert requests.post(f"{API}/events/{e['id']}/action?act=cancel&reason=x", headers=ph).status_code == 403
    _cleanup()
