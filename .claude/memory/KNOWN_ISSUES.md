# Known Issues

## Active Issues

(None currently tracked)

## Notes

- **MultiStepForm SessionStorage**: Fix applied for QuotaExceededError in privacy mode/large forms
- **Banking Reconciliation**: Match suggestion UI ready for backend integration

## Resolved

| Date | Issue | Fix |
|------|-------|-----|
| 2026-01-10 | MultiStepForm SessionStorage QuotaExceededError in privacy mode | Added 500KB limit check, auto-cleanup, and synchronous persistKey tracking in MultiStepForm.tsx |
| 2026-01-10 | N+1 queries in entity list endpoints causing slow page loads | Removed folder stats calculation from list endpoints, load on-demand via `/{entity_id}/folders` |
| 2026-01-10 | Entity API authentication failing with 401 errors | Added `credentials: "include"` to all fetch calls in ablage-api.ts (commit 25542547) |
| 2026-01-10 | FastAPI route ordering causing 403/422 for `/customers`, `/suppliers` | Moved static routes before dynamic `/{entity_id}` route (commit 665ca1cc) |
