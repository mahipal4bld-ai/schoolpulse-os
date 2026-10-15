# GitHub & release workflow

- Repo: private `schoolpulse-os` on the owner's personal GitHub, pushed via Emergent **Save to GitHub** (manual push; no force pushes).
- Branches: `main` = tested, released milestones. `development` = ongoing milestone work.
- Tags: `v0.1.1-foundation` = Milestone 1.1 (create on GitHub → Releases → "Draft a new release" → tag on `main`).
- Never committed: `backend/.env`, `frontend/.env`, `/backups` (DB dumps), node_modules, caches. Use the `.env.example` files as templates.
- Before each push: `cd backend && python -m pytest tests -q`, `cd frontend && npx jest && node scripts/i18n-check.js`, then run the secret scan:
  `git grep -nE "sk-emergent|JWT_SECRET=[a-f0-9]{20}|mongodb\+srv://" -- . ':!*.example' ':!docs'`
