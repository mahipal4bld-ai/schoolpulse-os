# SchoolPulse OS — Architecture (Milestone 1)

## Platform approach (confirmed)
- This workspace is an **Expo (React Native) + FastAPI + MongoDB** project. The same Expo codebase runs as the native Android/iOS app (Expo Go / EAS builds via Emergent Publish) **and** as the responsive web app (react-native-web). There is ONE backend and ONE database — no duplicated school databases.
- Next.js was deliberately not used. A future school-branded PWA / admissions website will consume the same `/api` (public brand endpoint already exists: `GET /api/public/schools/{slug}/brand`).
- White-label per-school Play Store apps (future) = same codebase with a build-time `school_slug` that pre-selects the tenant; no backend changes needed.

## Backend layout (`/app/backend`)
| File | Purpose |
|---|---|
| `core.py` | DB client, BaseDocument/PyObjectId helpers, bcrypt + JWT sessions (revocable via `sessions.jti`), tenant context (`X-School-Id` + membership check), role→permission map, audit writer, indexes |
| `routes_auth.py` | login (brute-force guard), logout / logout-all (server revocation), me, language preference, dev-only demo list, staff invitations + accept |
| `routes_school.py` | Super-admin tenants, school settings, Brand Studio, uploads (Emergent Object Storage), owner dashboard, audit log |
| `routes_directory.py` | Academic years, classes, sections, subjects, teachers, teacher assignments, students, guardians, guardian links, CSV import, teacher workspace, parent portal |
| `seed.py` | Idempotent fictional seed (only when `DEMO_MODE=true`) |
| `storage.py` | Server-side object storage wrapper (key never reaches the client) |
| `tests/test_milestone1.py` | 16 API tests |

## Multi-tenancy & security
- Every school-owned record carries `school_id`. All queries filter by the `school_id` resolved **server-side** from `X-School-Id` after verifying an active `memberships` row for the user. Referenced IDs (section, class, teacher…) are re-validated to belong to the same school.
- Users are global identities; `memberships(user_id, school_id, role)` grants access. A user may belong to several schools.
- Super admin (`users.platform_role`) has NO implicit access to school data (restricted support access); platform routes expose only tenant metadata & counts.
- Teachers only see students in sections they are assigned to; parents only see children linked through a **verified** guardian link whose guardian record is bound to their user.
- Students are archived (soft delete) for retention; deletion of academic structures is blocked while dependents exist.
- Audit log entry for every mutation and login/logout.
- Demo account picker: `GET /api/auth/demo-accounts` returns 404 unless `DEMO_MODE=true`; it never bypasses password login. **Set DEMO_MODE=false in production.**
- Brand assets (logo/banner/photos) are intentionally public (`visibility: brand`) for the admissions site; future private documents require membership.
- Timestamps stored in UTC; UI renders Asia/Kolkata, en-IN dates, INR.

## Roles → permissions
owner (all incl. brand.manage), principal, school_admin, accountant, admission_coordinator, transport_coordinator, teacher (teacher.workspace), parent (parent.portal). See `PERMISSIONS` in `core.py`.

## Frontend (`/app/frontend`)
- `src/auth.tsx` session + active school; `src/theme.ts` tokens with runtime tenant brand override (`setBrandColors`); `src/i18n.ts` English/Hindi; `src/api.ts` client.
- Route groups: `(staff)` Command Centre / People / Academics / Settings; `(teacher)` Today / Classes / Profile; `(parent)` Home / Updates / Profile; `/platform` super admin; stack screens for Brand Studio, School profile, student/teacher detail & forms, roster, invitations, CSV import, audit.

## API (v1, prefix `/api`)
Auth: `POST /auth/login`, `POST /auth/logout`, `POST /auth/logout-all`, `GET /auth/me`, `PATCH /auth/me/preferences`, `GET /auth/demo-accounts`, `POST /auth/accept-invite`
Platform: `GET|POST /platform/schools`, `PATCH /platform/schools/{id}`, `GET /platform/stats`
School: `GET /school`, `PATCH /school/settings`, `PATCH /school/brand`, `PUT /school/photos`, `GET /public/schools/{slug}/brand`, `POST /uploads`, `GET /files/{id}`, `GET /dashboard/owner`, `GET /audit-logs`
Directory (list endpoints support `page`, `page_size`, `q`): `/academic-years`, `/classes`, `/sections`, `/subjects`, `/teachers`, `/teacher-assignments`, `/students` (+ `POST /students/import`), `/guardians`, `/guardian-links`, `/invitations`
Workspaces: `GET /teacher/dashboard`, `GET /parent/children`, `GET /parent/children/{id}`

## Schema evolution
New fields are additive with defaults read via `.get()`. Future breaking changes go in numbered scripts under `backend/migrations/` (none required yet).

## CSV import
Columns: `admission_no,first_name,last_name,gender,dob,class,section,guardian_name,guardian_phone,guardian_relation`. Validate (`dry_run=true`) returns per-row errors; import only when valid.

## Known limits / next work
- Brute-force guard is in-memory (move to Redis/Mongo for multi-instance). Tokens are 7-day revocable sessions; add refresh rotation & device list UI.
- No email/SMS delivery: invitation codes are shared manually.
- Attendance, homework, timetable, exams, fees, admissions CRM, notices, PTM, transport, AI modules: data model foundations only; UI shows "Coming soon".
- Custom domains, PWA manifest, admissions website, white-label builds: architecture only.
- Production readiness requires: security review/pen test, DPDP Act consent review, backups & restore drill, load testing.
