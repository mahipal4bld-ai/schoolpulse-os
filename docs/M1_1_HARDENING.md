# Milestone 1.1 — Hardening

## Auth & sessions
- **Access token**: HS256 JWT, `ACCESS_TOKEN_MINUTES` (default 15), `typ=access`, `jti` = session id. Each request re-checks the session row is not revoked.
- **Refresh token**: 48-byte random opaque value, stored only as HMAC-SHA256 (`sessions.refresh_hash`). `POST /api/auth/refresh` rotates atomically (compare-and-swap on the current hash); the old hash goes to `prev_refresh_hashes`.
- **Reuse detection**: presenting an already-rotated refresh token revokes the whole session (`revoked_reason=refresh_token_reuse`) and writes audit `auth.refresh_reuse_detected`.
- **Logout** revokes the session (access + refresh die immediately). **Logout-all** revokes all of the user's sessions. `GET /api/auth/sessions` lists devices (no hashes), `DELETE /api/auth/sessions/{id}` revokes one device.
- Session rows keep created/last_used/ip/user_agent/rotations/revoked_reason for audit. Refresh lifetime `REFRESH_TOKEN_DAYS` (30).
- Client: single-flight refresh on 401, retry once, else sign out. Tokens in SecureStore (native) / localStorage (web — see limitations).

## Brute-force protection (`backend/ratelimit.py`, collection `login_limits`)
| Key | Free failures | Cooldown | Cap |
|---|---|---|---|
| account + IP | 5 | 30s doubling | 15 min |
| account (all IPs) | 20 | 60s doubling | 15 min |
| IP (all accounts) | 50 | 60s doubling | 15 min |
Stored in MongoDB → survives restarts and is shared by every backend instance. Success clears the account keys. Records expire 1h after the last failure (TTL index), so lockouts are never permanent. Unknown emails are rate-limited too, and a dummy hash keeps response timing similar.

## Demo-mode safety
- `APP_ENV` defaults to `production`, `DEMO_MODE` defaults to `false`.
- `APP_ENV=production` + `DEMO_MODE=true` → server refuses to start (`UnsafeConfigError: UNSAFE CONFIG`).
- With demo off, `/api/auth/demo-accounts` returns 404, so the picker disappears, and no seed runs. Demo mode never adds a password-free login route.
- **Before going live, set `APP_ENV=production` and `DEMO_MODE=false` under Deployment → Secrets.** Preview uses `APP_ENV=development`.

## Files
`routes_school.is_public_asset()` is the only gate for public retrieval: it requires `visibility == "brand"` AND purpose in {logo, banner, photo}. Everything else (including a missing visibility) needs authentication and an active membership in the file's school.

## Backup / restore — `backend/scripts/backup_restore.py`
1. `python scripts/backup_restore.py backup` → `mongodump --gzip` into `/app/backups/<UTC ts>/`, plus a `manifest.json` fingerprint (counts per collection; per-school brand, students, teachers, assignments, verified links, file storage paths, role memberships; a relationship hash).
2. `python scripts/backup_restore.py verify /app/backups/<ts>` → drops and recreates the clean DB `<DB>_restore_verify`, runs `mongorestore`, fingerprints the restored data, compares it with the manifest, writes `restore_report.json`, then drops the scratch DB.
- The object blobs themselves live in Emergent Object Storage (managed, no delete API). The backup covers their metadata and storage paths.
- Evidence (demo/staging data only): `/app/backups/20261015T101954Z/restore_report.json` → **PASS**, 0 mismatches. Sunrise: 72 students / 8 teachers / 15 assignments / 61 verified links / brand #9A3412 / 7 roles. Greenfield: 50 / 6 / 13 / 41 / #14532D / 21 file records / 7 roles.

## i18n
- A central catalogue keyed by the English source (`src/i18n-hi.ts`), with English as the fallback. `Txt` and `Field` translate automatically; the `raw` prop marks user data that must not be translated.
- `node scripts/i18n-check.js` fails if any static UI string lacks Hindi. Current result: 221/221 static strings (100%); 24 dynamic interpolated labels are still English-only (measured, not translated).

## Tests
- Backend: `cd backend && python -m pytest tests -q` (68 + 1 restart test run serially: `RUN_RESTART_TESTS=1 python -m pytest tests/test_m11_hardening.py -n 0 -k restart`).
- Frontend: `cd frontend && npx jest` (24 tests).
- Cleanup after test runs: `python scripts/cleanup_test_data.py`.
