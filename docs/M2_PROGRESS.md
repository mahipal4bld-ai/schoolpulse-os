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
