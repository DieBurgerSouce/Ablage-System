# Recent Changes

## 2026-02-18
- **fix(security)**: Multi-Tenant Enforcement - Duplicate Detection API leitet company_id aus Auth ab (IDOR-Prevention)
- **fix(security)**: Banking FinTS API - user_id Parameter auf company_id korrigiert (12 Call-Sites)
- **fix(api)**: Transactions API - Pydantic v2 Modernisierung (ConfigDict statt Config-Klasse)
- **fix(workers)**: Approval Tasks - structlog Migration, TypedDict Return Types, soft/hard Zeitlimits
- **fix(workers)**: Folder Import Rule Tasks - safe_error_log, Celery Zeitlimits (soft 300s, hard 360s)

## 2026-02-16
- **refactor(all)**: Unicode-Normalisierung über 1168 Dateien (ae→ä, oe→ö, ue→ü, ss→ß, fuer→für)

## 2026-02-15
- **feat(frontend)**: 7 Feature-Module (adhoc-reporting, annotations-extended, approval-enhanced, german-finance, ki-pipeline, proactive-assistant, smart-dashboard) mit 115 Komponenten
- **feat(api)**: 12 neue Endpoints für 2026-Q1 Features
- **feat(services)**: 15 neue Feature-Services + Duplicate Detection + Event-driven Import
- **feat(workers)**: 10 neue Celery Task-Module für async Feature-Processing
- **feat(db)**: 3 Migrationen (225-227) + 10 Satellite Models
- **chore(infra)**: imagehash + scikit-learn Dependencies

## 2026-02-14
- **fix(frontend)**: Token trimming + WebSocket auth (13 Dateien, Bearer-Token-Trim 19/19 100%)
- **test(frontend)**: 23 WebSocket URL-encoding und Auth-Validierung Tests (6 Dateien)
- **feat(frontend)**: Spotlight Cmd+K, OCR Batch Correction, Smart Upload, Smart Tags, Auto-Learning
- **feat(api)**: Spotlight API Endpoint mit Rate Limiting und <200ms Ziel
- **feat(db)**: Migrationen 222-223 (Folder Hierarchy, Knowledge Graph Autonomy)
- **feat(services)**: 5 neue Services (Folder, Booking, Learning Autonomy, Summarization, ThreatDetection)
- **test**: E2E (10), Integration + Unit Tests + Chaos Engineering Framework
- **feat(infra)**: Compliance Infrastructure (GDPR, GoBD, ISO27001)

## 2026-02-13
- **refactor(workers)**: Celery Task Names - Full-Path Migration (87 Dateien)
- **feat(api)**: 10 neue Enterprise Endpoints (collaboration, data_quality, digital_twin, etc.)
- **feat(services)**: 9 neue Enterprise Services (Collaboration, Data Quality, Digital Twin, etc.)
- **feat(frontend)**: CEO Dashboard Components, Collaboration Features, Smart Search
- **feat(db)**: Migrationen 220-221 (Collaboration Tables, Merge Heads)
- **fix(db)**: Alembic Migrations 208, 209, 215, 216 asyncpg-hardened
