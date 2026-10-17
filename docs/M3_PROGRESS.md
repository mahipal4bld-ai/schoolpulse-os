# Milestone 3 — Parent Connect: progress
Branch: `milestone-3-parent-connect`, based on `milestone-2-audit-remediation` / Milestone-2.

## Module 1 — Notices & announcements: DONE, tested
- **Collections:**
  - `notices {school_id, title, body (sanitised plain text), category, priority, audience{scope school|classes|sections, class_names, section_ids}, attachments, requires_ack, status draft|review|scheduled|published|archived|cancelled, publish_at, expires_at (UTC; input interpreted as IST), revisions[], status_history[]}`
  - `notice_receipts {notice_id, user_id, read_at, ack_at}`, unique per notice + user.
- **Status changes:** scheduled notices publish at their set time, and published notices archive when they expire. Both changes run when notices are next fetched; there is no background worker. Editing a published notice requires a reason and saves a revision.
- **Read vs acknowledged:** opening a notice counts as read. Acknowledging is a separate, explicit tap.
- **Stats:** the denominator is verified guardian accounts with an active parent membership and an active child in the audience.
- **API:** `/api/notices` (CRUD, actions, attachments), `/api/parent/notices` (+ `/read`, `/ack`).
- **Attachments:** governed by document-level rules in `file_access.py` (purpose `notice`).
- **Permission:** a new `notices.manage` permission for owner, principal and school_admin.
- **Tests:** `tests/test_m3_notices.py` (2); testing agent iteration_14 PASS.

## Module 2 — Parent–teacher messaging: DONE, tested
- **Collections:**
  - `conversations {school_id, student_id, guardian_user_id, teacher_id, teacher_user_id, topic, status open|closed|escalated, follow_up, unread{parent,teacher}, reports[]}`
  - `messages {conversation_id, sender_user_id, sender_role, body, attachments, client_id (unique per conversation → idempotent), read_at, status}`
  - `message_templates`
- **Access:** checked against current data on every request. A parent needs a verified guardian link to the child. A teacher needs a current assignment to the child's section. Owner, principal and school admin can see a conversation only once it is escalated. Anyone else gets a 404.
- **Limits and pagination:** at most 20 messages per user per 10 minutes. Long threads load older messages by cursor (`?before=`).
- **Updates:** the app polls, every 5 s in an open thread and every 15 s on the conversation list. There is no real-time socket.
- **Office replies:** after escalation, owner/principal/school admin can also reply in the thread (stored as `sender_role=admin`). This is the intended escalation flow.
- **Not done yet:**
  - The school hours shown to parents are guidance only; messages are not blocked outside those hours.
  - Retention purge is not implemented.
  - The app has no attachment picker in the compose box yet. The API supports attachments.
- **Tests:** `tests/test_m3_messaging.py` (2); testing agent iteration_15 PASS.

## Remaining (not started)
Module 3 Events & calendar · Module 4 PTM booking (atomic slots) · Module 5 Help desk · Module 6 Student leave & digital forms · Module 7 Classroom moments (consent-gated media) · Module 8 Notifications centre (outbox) · Module 9 AI assistant (provider-gated, human approval) · Module 10 Parent engagement intelligence · Final acceptance journeys.

## Test totals at this checkpoint
Backend `pytest tests -q`: 106 passed, 0 failed, 1 skipped. The skipped test is restart persistence; run separately with `RUN_RESTART_TESTS=1 pytest -n 0 -k restart`, it passes (1 of 1). Frontend Jest: 26 passed. TypeScript: clean. Hindi strings: 434/434.
