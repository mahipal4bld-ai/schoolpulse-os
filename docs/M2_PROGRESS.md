# Independent review fixes + Milestone 2 (Module 1: Student Attendance)

## Part A — review findings
| Finding | Fix | Evidence |
|---|---|---|
| A1 private file caching | Private files: `Cache-Control: private, no-store, max-age=0`, `Pragma: no-cache`, `Expires: 0`, `Content-Disposition: attachment`, `Vary: Authorization`, `X-Content-Type-Options: nosniff`. Parents and other tenants are denied. Brand assets keep `public, max-age=86400`. | `tests/test_review_fixes.py::test_private_file_headers_and_scope`, `test_public_brand_asset_keeps_public_cache` |
| A2 IP spoofing | `ratelimit.resolve_client_ip`: X-Forwarded-For is used only when the direct peer is in `TRUSTED_PROXY_CIDRS`. The chain is walked right to left and the first untrusted hop is taken as the client; malformed headers fall back to the peer. | `test_resolve_client_ip_rules`, `test_spoofed_xff_cannot_bypass_lockout_without_trusted_proxy` (separate instance with no trusted proxies; rotating forged IPs still hit 429) |
| A3 LogBox | `ignoreAllLogs` removed; only 2 known-noisy warnings are muted. `src/monitoring.ts` scrubs JWTs, tokens, emails, phone numbers and long digit runs, then posts to `/api/client-errors` (capped at 60 per IP per hour, 30-day expiry). Sources: the ErrorBoundary and a global handler. | `test_client_error_reporting_scrubbed_and_capped`; testing agent confirmed the ErrorBoundary still works |
| A4 production config | `assert_safe_config()` refuses to start when `APP_ENV=production` with `DEMO_MODE=true`, or with a JWT_SECRET that is under 32 characters or a placeholder. Defaults are `production` and demo off. The demo picker returns 404 when demo is off. | `test_production_requires_strong_jwt_secret`, plus the M1.1 demo-mode tests |

### Proxy note — partially validated
- In this preview, the k8s ingress sits on cluster-private ranges, which are configured in `TRUSTED_PROXY_CIDRS`.
- Uvicorn `--proxy-headers` trusts only 127.0.0.1 by default.
- The actual production ingress IPs and its X-Forwarded-For behaviour could not be inspected from the container.
- **Production must set `TRUSTED_PROXY_CIDRS` to the real ingress CIDR.** If it is left empty, X-Forwarded-For is ignored. That is safe, but all users then share the proxy's IP bucket.

### Dev / production isolation
- Production gets its own DB and secrets through Emergent deployment Secrets (`DB_NAME`, `JWT_SECRET`, `APP_ENV=production`, `DEMO_MODE=false`).
- The preview environment was not switched to production.
- Backup and restore: `docs/M1_1_HARDENING.md`.

## Part B — Module 1 Student Attendance (built and tested)
- Collection `attendance`: `{school_id, section_id, date (IST YYYY-MM-DD), records[{student_id,status}], submitted_by, submitted_at, updated_at, corrections[{by, at, reason, changes[{student_id, from, to}]}]}`. Unique index on (school_id, section_id, date).

### Rules
- Statuses: present, absent and late.
- Every active student in the section must be marked, and only students from that section are accepted.
- Future dates are rejected.
- Resubmitting the same sheet is idempotent.
- A correction requires a reason, and only the changed rows are logged.
- Teachers can work only on their assigned sections, and can correct only today's sheet. Admins and principals (academic.manage) can correct past dates.
- Timestamps are set by the server.
- Every submit and correction is recorded in the audit log.

### API
- `GET/PUT /api/attendance/sections/{section_id}?date=`
- `GET /api/attendance/reports/monthly?section_id&month=`
- `GET /api/attendance/summary/today` (owner dashboard, includes a 7-day trend)
- `GET /api/parent/children/{id}/attendance?month=`

### UI
- `/attendance/[sectionId]`: tap to cycle a status, "All present", a sticky submit bar, a reason field for corrections, and a monthly report sheet.
- The teacher Today and Classes screens show whether each section's attendance is pending or marked.
- The parent home has an attendance card.
- The owner Command Centre has a today's-attendance card with the 7-day trend.

## Not yet built (Milestone 2 remaining)
Staff attendance and leave approvals, homework with attachments, class diary, timetable and calendar, examinations and report cards, the full teacher workspace, the full parent academic view, and owner academic intelligence beyond attendance.

## Part B — Module 2 Staff Attendance & Leave (built and tested)
- Collections: `staff_attendance {school_id, teacher_id, date, status(present|absent|late|half_day|on_leave), check_in_at, source(self|admin|leave), marked_by, corrections[]}` (unique school+teacher+date); `leave_requests {school_id, teacher_id, user_id, type, from_date, to_date, days, reason, status(pending|approved|rejected|cancelled), decided_by, decided_at, decision_note}`.
- New permission `leave.approve` (owner, principal). School admin can view the register and leave list but cannot decide.
- Rules: teacher self check-in (late after 08:30 IST, idempotent, blocked on approved leave); register corrections require reason; no overlapping leave; ≤30 days; reject requires note; no self-approval; decisions are one-shot (409); approval writes on_leave rows.
- API: `/api/staff/me/today`, `/api/staff/me/check-in`, `GET/PUT /api/staff/attendance`, `/api/staff/summary/today`, `/api/staff/leave` (+ `/mine`, `/{id}/cancel`, `/{id}/decision`).
- UI: teacher Today check-in card + My leave; Command Centre "Staff today" card + Staff attendance register + Leave requests approvals.
- Tests: `tests/test_m2_staff.py` (5) — full backend 83 passed; jest 24 passed; testing agent PASS.

## Part B — Module 3 Homework (built and tested)
- Collection `homework {school_id, section_id, subject_id, title, description, assigned_date, due_date, attachments[file_id], status(draft|published|deleted), published_at, created_by, teacher_id, completion[{student_id,status(done|not_done|late),by,at}]}`.
- Attachments: `POST /api/homework/attachments` (PDF/JPG/PNG/WEBP ≤10 MB, private object storage). Parents can download only attachments on *published* homework for their verified child's section (`parent_can_read_file`).
- Rules: teachers assign only subjects they teach in a section (class teachers: any subject); admins anywhere; due date between today and +60 days; completion tracking only once published; soft delete; every action audited.
- API: `/api/homework` (list/create), `/options`, `/summary`, `/{id}` (get/patch/delete), `/{id}/publish`, `/{id}/completion`, `/api/parent/children/{id}/homework?scope=upcoming|past`.
- UI: teacher Today → Homework list/new/detail with completion; parent Family homework card + child homework screen; Command Centre homework quick action with weekly summary.
- Tests: `tests/test_m2_homework.py` (3), full backend 86 passed; jest 25; testing agent PASS (iteration_6).

## Part B — Module 4 Class Diary (built and tested)
- Collection `diary {school_id, section_id, kind(lesson|note), subject_id, date, topic, summary, created_by, deleted}`.
- Rules: lesson entries need a subject the teacher teaches; notes need section access; no future dates; teachers ≤7 days back, admins any past date; only author/admin edits; soft delete; audited.
- API: `GET/POST /api/diary`, `PATCH/DELETE /api/diary/{id}`, `/api/diary/summary/today`, `/api/parent/children/{id}/diary?date=`.
- UI: teacher Today → Class diary (section list → day stepper + add/edit/delete); parent Homework & diary card → child diary by day; Command Centre quick action with sections-updated-today.
- Tests: `tests/test_m2_diary.py` (2), full backend 88 passed; testing agent PASS (iteration_7). Added `tests/conftest.py` to clear login rate-limit buckets per session.

## Part B — Module 5 Timetable (built and tested)
- Collections: `timetable_settings {school_id, periods[{no,start,end}]}` (default 8 periods Mon–Sat), `timetable_slots {school_id, section_id, day(1-6), period, subject_id, teacher_id, room}` (unique per section/day/period).
- Conflict detection: teacher double-booking and room double-booking are rejected with 409; teacher must be assigned to the subject (or be class teacher) in the section; `/timetable/conflicts` audits legacy clashes. Bell schedule validated (HH:MM, ordered, non-overlapping); shrinking periods removes orphan slots.
- API: `GET/PUT /api/timetable/settings`, `GET /api/timetable/sections/{id}`, `PUT/DELETE /api/timetable/sections/{id}/slots`, `/api/timetable/conflicts`, `/api/timetable/teacher/me`, `/api/timetable/teachers/{id}`, `/api/parent/children/{id}/timetable`.
- Demo seed: timetable auto-generated clash-free from teacher assignments (DEMO_MODE only, idempotent).
- UI: Command Centre → Timetable (bell schedule editor, class list → day tabs, tap-to-assign editor); teacher My timetable; parent child timetable.
- Tests: `tests/test_m2_timetable.py` (2), full backend 90 passed; testing agent PASS (iteration_8). Cosmetic: shadow*/pointerEvents props migrated to boxShadow / style.pointerEvents.

## Part B — Module 6 Examinations (built and tested)
- Collections: `exams {school_id, name, term, start_date, end_date, section_ids[], subjects[{subject_id,max_marks,pass_marks,date}], status(marks_open|published|deleted), published_at}`, `exam_marks {school_id, exam_id, section_id, subject_id, records[{student_id,marks,absent}], entered_by}` (unique exam+section+subject).
- Rules: only academic.manage creates/publishes; teachers enter marks only for subjects they teach (class teachers any); every student must be marked or absent; 0..max, half-marks allowed; publish blocked until all sheets entered; published exams lock marks (re-open to edit); published exams cannot be deleted; all actions audited.
- Results: totals, percentage, CBSE-style grade (A1…E), pass/fail per subject, competition ranking, class average.
- Branded PDF report card (reportlab): school primary/secondary colours, logo from object storage, student details, subject table, grade, rank, signatures; `Cache-Control: no-store`; parent access only after publish for verified child.
- API: `/api/exams` (+ `/{id}`, `/{id}/marks`, `/{id}/status`, `/{id}/results`, `/summary/recent`, `/{id}/report-card/{student}.pdf`), `/api/parent/children/{id}/exams`.
- UI: Examinations list/create, exam detail with progress + publish/re-open, marks entry, results with expandable subjects + report card; parent Exam results screen.
- Tests: `tests/test_m2_exams.py` (2), full backend 92 passed; testing agent PASS (iteration_9).

## Part B — Module 7 Teacher Workspace (built and tested)
- `GET /api/teacher/workspace`: today's periods from the timetable (with bell times), plus a consolidated to-do list: attendance not marked for class-teacher sections, diary not written for sections taught today, unpublished homework drafts, and empty exam marks sheets. Also counts for homework due today and pending leave.
- UI: teacher Today shows "Today's classes" and "To do" cards; each to-do opens the right screen, and the list refetches when the screen regains focus.
- Tests: `tests/test_m2_workspace.py` (1), full backend 93 passed; testing agent PASS (iteration_10).

## Part B — Module 8 Parent Academic Experience (built and tested)
- `GET /api/parent/children/{id}/overview` returns, per child: today's attendance and this month's rate, today's periods, homework due (excluding work already marked done), today's diary and the latest published result. Verified guardians only.
- UI: a "Today at school" card on the parent Family home with tiles that open homework, timetable, results and diary. It updates when the parent switches child.
- Tests: `tests/test_m2_parent.py` (1), full backend 94 passed; testing agent PASS (iteration_11).

## Part B — Module 9 Owner Academic Intelligence (built and tested)
- `GET /api/dashboard/academic?days=14|30` (clamped to 7–60 days). Every figure is computed live from records: daily attendance trend, lowest-attendance sections, frequent absentees (3+ days), homework and diary coverage per section, latest published exam averages and pass rates per section, staff punctuality, and pending leave.
- UI: Command Centre → Academic insights screen with a 14/30-day toggle.
- Tests: `tests/test_m2_insights.py` (1); testing agent PASS (iteration_12).

## Part C — End-to-end workflow test
- `tests/test_m2_e2e.py` runs one full school day: the teacher checks in, marks attendance, writes the diary and publishes homework with an attachment. The teacher applies for leave and the principal approves it. The principal creates an exam, the teacher enters marks and the principal publishes. The parent then sees the overview, downloads the attachment and gets the PDF report card. The owner's insights and the teacher's to-do list update to match.
- Full backend suite: 96 passed, 1 skipped.

## Part D — GitHub
- This environment has no git remote configured. A local git commit is made after each module. Push to a development branch with the platform's "Save to GitHub" button; it never force-pushes over main.
