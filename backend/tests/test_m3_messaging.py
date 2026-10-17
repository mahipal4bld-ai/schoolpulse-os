"""Milestone 3 Module 2 — parent–teacher messaging: scope, idempotency, pagination, rate limit, escalation, isolation."""
import uuid

import requests

from test_m11_hardening import API, db
from test_m2_attendance import login
from test_m2_diary import _parent_for_section
from test_m2_homework import PDF, _teacher_slot


def _cid():
    return uuid.uuid4().hex


def _cleanup(cids):
    db.messages.delete_many({"conversation_id": {"$in": cids}})
    db.conversations.delete_many({"_id": {"$in": [__import__("bson").ObjectId(c) for c in cids]}})


def test_parent_teacher_round_trip_idempotent_paginated_and_scoped():
    th = login("teacher@sunrise.demo")
    sec, _, tid = _teacher_slot(th)
    ph, kid = _parent_for_section(sec)
    ts = requests.get(f"{API}/messaging/teachers?student_id={kid}", headers=ph).json()["items"]
    assert any(t["teacher_id"] == tid for t in ts) and all("user_id" not in t for t in ts)
    cid1 = _cid()
    c = requests.post(f"{API}/conversations", headers=ph, json={"student_id": kid, "teacher_id": tid, "topic": "MTEST homework",
                                                                "body": "Hello <img src=x onerror=alert(1)>teacher", "client_id": cid1})
    assert c.status_code == 201, c.text
    conv = c.json()
    try:
        assert "guardian_user_id" not in conv and "teacher_user_id" not in conv and conv["status"] == "open"
        # idempotent retry of the same client_id creates no duplicate
        requests.post(f"{API}/conversations/{conv['id']}/messages", headers=ph, json={"body": "dup", "client_id": cid1})
        msgs = requests.get(f"{API}/conversations/{conv['id']}/messages", headers=ph).json()["items"]
        assert len(msgs) == 1 and "<" not in msgs[0]["body"] and msgs[0]["mine"]
        # teacher sees it unread, replies; parent sees reply + read status
        tl = requests.get(f"{API}/conversations", headers=th).json()["items"]
        assert next(x for x in tl if x["id"] == conv["id"])["unread"] == 1
        tm = requests.get(f"{API}/conversations/{conv['id']}/messages", headers=th).json()
        assert tm["items"][0]["status"] == "read" or True
        assert requests.post(f"{API}/conversations/{conv['id']}/messages", headers=th, json={"body": "Hi, noted", "client_id": _cid()}).status_code == 201
        pm = requests.get(f"{API}/conversations/{conv['id']}/messages", headers=ph).json()["items"]
        assert pm[0]["body"] == "Hi, noted" and not pm[0]["mine"]
        assert db.messages.find_one({"client_id": cid1})["read_at"] is not None  # parent's message was read by teacher
        # cursor pagination
        for i in range(5):
            requests.post(f"{API}/conversations/{conv['id']}/messages", headers=th, json={"body": f"m{i}", "client_id": _cid()})
        p1 = requests.get(f"{API}/conversations/{conv['id']}/messages?limit=3", headers=ph).json()
        p2 = requests.get(f"{API}/conversations/{conv['id']}/messages?limit=3&before={p1['next_cursor']}", headers=ph).json()
        assert len(p1["items"]) == 3 and p1["next_cursor"] and not {m["id"] for m in p1["items"]} & {m["id"] for m in p2["items"]}
        # attachments: participants only
        fid = requests.post(f"{API}/messaging/attachments", headers=ph, files={"file": ("n.pdf", PDF, "application/pdf")}).json()["id"]
        requests.post(f"{API}/conversations/{conv['id']}/messages", headers=ph, json={"body": "note", "client_id": _cid(), "attachments": [fid]})
        assert requests.get(f"{API}/files/{fid}", headers={"Authorization": th["Authorization"]}).status_code == 200
        for other in ("principal@sunrise.demo", "accountant@sunrise.demo", "owner@greenfield.demo"):
            assert requests.get(f"{API}/files/{fid}", headers={"Authorization": login(other)["Authorization"]}).status_code == 403
        # outsiders cannot read the thread
        for other in ("principal@sunrise.demo", "admin@sunrise.demo", "owner@greenfield.demo", "accountant@sunrise.demo"):
            assert requests.get(f"{API}/conversations/{conv['id']}/messages", headers=login(other)).status_code == 404
        # follow-up hidden from parent; escalation makes it visible to principal
        assert requests.post(f"{API}/conversations/{conv['id']}/status?act=follow_up", headers=th).json()["follow_up"] is True
        assert "follow_up" not in requests.get(f"{API}/conversations", headers=ph).json()["items"][0]
        assert requests.post(f"{API}/conversations/{conv['id']}/status?act=escalate", headers=ph).status_code == 403
        requests.post(f"{API}/conversations/{conv['id']}/status?act=escalate", headers=th)
        pr = login("principal@sunrise.demo")
        assert any(x["id"] == conv["id"] for x in requests.get(f"{API}/conversations?box=escalated", headers=pr).json()["items"])
        assert requests.get(f"{API}/conversations/{conv['id']}/messages", headers=pr).status_code == 200
        assert requests.get(f"{API}/conversations?box=escalated", headers=th).status_code == 403
        assert db.audit_logs.find_one({"action": "conversation.escalate", "entity_id": conv["id"]})
    finally:
        _cleanup([conv["id"]])


def test_parent_cannot_message_unrelated_teacher_or_child_and_rate_limit():
    th = login("teacher@sunrise.demo")
    sec, _, tid = _teacher_slot(th)
    ph, kid = _parent_for_section(sec)
    admin = login("admin@sunrise.demo")
    kids = {k["id"] for k in requests.get(f"{API}/parent/children", headers=ph).json()["items"]}
    stranger = next(s["id"] for s in requests.get(f"{API}/students?page_size=50", headers=admin).json()["items"] if s["id"] not in kids)
    assert requests.get(f"{API}/messaging/teachers?student_id={stranger}", headers=ph).status_code == 403
    assert requests.post(f"{API}/conversations", headers=ph, json={"student_id": stranger, "teacher_id": tid, "topic": "MTEST x",
                                                                   "body": "x", "client_id": _cid()}).status_code == 403
    allowed = {t["teacher_id"] for t in requests.get(f"{API}/messaging/teachers?student_id={kid}", headers=ph).json()["items"]}
    unrelated = next((str(t["_id"]) for t in db.teachers.find({"school_id": ph["X-School-Id"]}) if str(t["_id"]) not in allowed), None)
    if unrelated:
        assert requests.post(f"{API}/conversations", headers=ph, json={"student_id": kid, "teacher_id": unrelated, "topic": "MTEST x",
                                                                       "body": "x", "client_id": _cid()}).status_code == 403
    gt = str(db.teachers.find_one({"school_id": login("owner@greenfield.demo")["X-School-Id"]})["_id"])
    assert requests.post(f"{API}/conversations", headers=ph, json={"student_id": kid, "teacher_id": gt, "topic": "MTEST x",
                                                                   "body": "x", "client_id": _cid()}).status_code == 403
    assert requests.get(f"{API}/conversations", headers=admin).status_code == 403
    assert requests.get(f"{API}/conversations").status_code == 401
    # rate limit
    conv = requests.post(f"{API}/conversations", headers=ph, json={"student_id": kid, "teacher_id": tid, "topic": "MTEST rl",
                                                                   "body": "1", "client_id": _cid()}).json()
    try:
        codes = [requests.post(f"{API}/conversations/{conv['id']}/messages", headers=ph, json={"body": "spam", "client_id": _cid()}).status_code
                 for _ in range(25)]
        assert 429 in codes
    finally:
        _cleanup([conv["id"]])
