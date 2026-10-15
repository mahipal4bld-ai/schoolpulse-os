# SchoolPulse OS — PRD

## Original problem statement
Premium, multi-tenant, AI-ready school management & parent engagement SaaS for Indian private schools (300–1,500 students, ~₹60k/yr). Five experiences (Parent Connect, Teacher Workspace, Owner Command Centre, School Administration, SaaS Super Admin) on one backend. 22 planned modules; Milestone 1 = foundation: auth, tenancy, roles, school onboarding, Brand Studio, academic directory CRUD, role shells, two fictional branded schools, tests, docs.

## User choices
JWT email/password + dev-only demo picker · Emergent Object Storage for logos/banners · English with Hindi toggle · basic Super Admin school creation & list.

## Architecture
Expo (native + web) → FastAPI `/api` → MongoDB. See `/app/docs/ARCHITECTURE.md`.

## Implemented (Milestone 1 — Oct 2026)
- Auth: bcrypt, revocable JWT sessions, logout/logout-all, brute-force guard, invitations + accept, demo picker gated by DEMO_MODE
- Tenancy: X-School-Id + membership check on every school route; cross-school references rejected; audit log
- 9 roles with server-side permission map; teacher section scoping; parent verified-link scoping
- Super Admin: tenant list/search/usage, create school + owner, suspend/reactivate, stats
- School settings & Brand Studio (colours, monogram, crest shape, logo/banner upload, welcome msg, tagline) with live preview; runtime tenant theming
- CRUD + search + pagination: academic years, classes, sections, subjects, teachers, assignments, students (archive), guardians, guardian links (verify, consent)
- CSV student import with dry-run validation
- Owner Command Centre (live counts), Teacher Today/Classes/Roster, Parent home with child switcher, Updates (coming soon), profiles, EN/HI
- Seed: Sunrise Valley Academy (72 students) & Greenfield Public School (50 students)
- Tests: 39 backend pytest passing (tests/test_milestone1.py + test_milestone1_edges.py); frontend E2E verified by testing agent

## M1 Verification Audit (Oct 2026)
- 49/49 backend tests pass; UI E2E pass (iteration_2). Fixed: student/teacher edit UI, desktop width, suspended-school filtering, more Hindi, test-data cleanup. See /app/docs/M1_AUDIT.md

## Backlog
- P0 (M2): Attendance, homework/diary, timetable & calendar, notices
- P1: Fees & receipts, admissions CRM, exams/report cards, leave/help desk, PTM
- P2: AI teacher/info/owner briefing, transport & pickup, analytics, PWA/admissions site, custom domains, subscription billing, white-label builds
- Hardening: distributed rate limit, refresh-token rotation, DPDP consent review, backups/restore drill, pen test
