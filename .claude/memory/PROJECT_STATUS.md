# Project Status

## Service Health

| Service | Status | Notes |
|---------|--------|-------|
| Backend | ✅ OK | Running on :8000, GPU access enabled |
| Frontend | ✅ OK | Nginx :80 |
| Celery | ✅ OK | Entity linking tasks active, GPU for OCR |
| PostgreSQL | ✅ OK | :5433 |
| Redis | ✅ OK | :6380 |
| GPU | ✅ OK | RTX 4080 (16GB), shared by backend + worker |

## Recent Deployments

| Date | Component | Description |
|------|-----------|-------------|
| 2026-01-11 | Backend | Enterprise Upload Flow - TempFileStorageService (Redis) |
| 2026-01-11 | Frontend | OCR-Review Upload Dialog mit TTL Extension |
| 2026-01-10 | Backend | Lexware integration complete |
| 2026-01-10 | Frontend | Entity API authentication fixed |

## Recent Migrations

| Migration | Description |
|-----------|-------------|
| 091 | Expense reports soft delete (deleted_at, deleted_by_id) |
| 090 | Lexware streckengeschaeft merge |
| 089 | Lexware fields (lexware_ids, company_presence) |
