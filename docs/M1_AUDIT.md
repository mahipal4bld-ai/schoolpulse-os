# Milestone 1 Verification Audit — Oct 2026

## Evidence
- Backend pytest: 49/49 PASS (`tests/test_milestone1.py` 16, `test_milestone1_edges.py` 23, `test_milestone1_audit.py` 10)
- Testing-agent UI regression: iteration_1 + iteration_2 (`/app/test_reports/`) — all flows PASS on mobile, plus manual desktop/tablet screenshots
- Persistence: DB counts & brand identical before/after backend restart

## Defects found & fixed in audit
1. No UI to edit students → edit sheet added (name, roll, move section)
2. No UI to edit/deactivate teachers → edit sheet added
3. Desktop web stretched full width → app column 1080px, login 520px, sheets 640px
4. Suspended schools still listed in memberships → filtered server-side
5. Command Centre headings English-only → Hindi strings added
6. Test runs polluted demo data → `scripts/cleanup_test_data.py`; demo data reset to seed baseline

## Known remaining items
- Hindi covers navigation, headings and key actions; many subtitles/helper text remain English
- No frontend unit-test suite; UI verified by automated browser E2E only
- Brute-force limiter in-memory; 7-day revocable tokens without refresh rotation
- Invitation codes shared manually (no email/SMS)
- Native-only paths (image picker permission flow, NativeTabs on iOS 26) not testable in web preview
