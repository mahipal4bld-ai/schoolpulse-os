# Milestone 2 — Independent Audit Remediation

Branch: `milestone-2-audit-remediation` (based on Milestone-2). Existing academic modules and school records are unchanged.

## Fix 1 — Secure file downloads (HIGH)
- The server no longer accepts access tokens from URLs: `optional_user` reads the `Authorization` header only, and `?token=` is ignored, so private files return 401.
- **Web:** private files and report cards are fetched with the `Authorization` and `X-School-Id` headers. The browser only ever sees a local `blob:` URL, so no token appears in history, logs or the Referer header (`src/utils/download.ts`, `apiBlob`).
- **Native:** the in-app browser cannot send headers, so the app asks for a download grant first:
  - Endpoints: `POST /api/files/{id}/download-grant`, `POST /api/exams/{eid}/report-card/{sid}/download-grant`.
  - The server returns `/api/downloads/{grant}`. A grant is random (256-bit), usable once, valid for 60 seconds, and tied to one user and one document. Only its SHA-256 hash is stored, and a Mongo TTL index removes it.
  - Access is checked again when the link is used, so a revocation made after the link was issued still applies.
- Response headers: `Cache-Control: private, no-store`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`.
- Access logs: a uvicorn access-log filter replaces grant tokens with `/api/downloads/[redacted]`.
- The report-card endpoint now uses normal header authentication (`school_ctx`) and no longer takes `?school=&token=`.

## Fix 2 — Document-level file permissions (HIGH)
The file permission rules now live in `backend/file_access.py`. Anything not explicitly allowed is denied, and every check reads current data, so revocations apply immediately.

| Requester | Homework attachment | Other private file |
|---|---|---|
| Owner / principal / school admin | ✅ | owner/principal ✅, school admin ❌ (unless uploader) |
| Teacher | ✅ only if uploader, or currently assigned to a section with non-deleted homework referencing the file | ❌ unless uploader |
| Parent | ✅ only if a **verified** child is in a section with **published** homework referencing the file | ❌ |
| Accountant / admission / transport | ❌ | ❌ unless uploader |
| Another school | ❌ | ❌ |

## Fix 3 — Atomic timetable conflicts (MEDIUM)
- Two partial unique indexes now block double-booking at the database level, even when two updates arrive at the same moment:
  - `uniq_teacher_period` on (school, teacher_id, day, period), applied wherever teacher_id is set.
  - `uniq_room_period` on (school, room_key, day, period), applied wherever room_key is set. `room_key` is the room name trimmed and lower-cased.
- The existing check before saving still gives a friendly error message. If two updates race, the database rejects the second one with a duplicate-key error, which the API returns as a 409.
- Index migration happens in `ensure_indexes`: the old non-unique index is dropped and `room_key` is filled in for existing slots.

## Fix 4 — Test totals (exact)
See the commit message and the README table. Skipped tests are never counted as passed.

## Fix 5 — CI (`.github/workflows/ci.yml`)
- **secret-scan:** gitleaks over the full history, and the build fails if any `.env` file is committed.
- **backend:** uses a throwaway `mongo:7` service, a new database name per run, a random JWT secret per run, fictional demo seed data only, and `STORAGE_BACKEND=memory`. Memory storage is only allowed when `APP_ENV=test|ci`; otherwise the server refuses to start. The job runs the critical authorization suites first, then the full suite, then a restart-persistence check run on its own, and uploads the JUnit XML results.
- **frontend:** installs from the lockfile with `--ignore-scripts`, then runs `tsc --noEmit`, Jest and the Hindi catalogue check.
- **dependencies:** `pip-audit` is a warning only for now. `yarn audit` fails the build only on critical vulnerabilities. Dependabot is set up for pip, npm and Actions.

### Not runnable in GitHub Actions (needs a deployment or a real device)
- Real Emergent Object Storage uploads and downloads: CI uses in-memory storage, so check the live storage service on staging.
- Native in-app-browser download grants on iOS/Android: covered by API tests, but opening the file needs a development or production build on a device.
- Expo Go / device keyboard, haptics and document-picker flows.
- Running behind the production ingress, including `TRUSTED_PROXY_CIDRS` and the `X-Forwarded-For` chain.
- The supervisor-managed restart test (`RUN_RESTART_TESTS=1 pytest -n 0 -k restart`): CI runs an equivalent that restarts the process itself.
