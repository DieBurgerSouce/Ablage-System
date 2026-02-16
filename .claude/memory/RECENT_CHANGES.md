# Recent Changes

## 2026-02-16
- **refactor(all)**: Unicode-Normalisierung über 1168 Dateien (ae→ä, oe→ö, ue→ü, ss→ß, fuer→für)

## 2026-02-15
- **feat(frontend)**: 7 Feature-Module (adhoc-reporting, annotations-extended, approval-enhanced, german-finance, ki-pipeline, proactive-assistant, smart-dashboard) mit 115 Komponenten
- **feat(api)**: 12 neue Endpoints für 2026-Q1 Features (adhoc-reports, annotations, approval, automation, finance, webhooks)
- **feat(services)**: 15 neue Feature-Services (Auto-Filing, BWA, Cashflow, OCR-Learning, Proactive Assistant, etc.)
- **feat(workers)**: 10 neue Celery Task-Module für async Feature-Processing
- **feat(db)**: 3 Migrationen (225-227) + 10 Satellite Models (Annotation, Approval, Finance, KI-Pipeline)
- **feat(services)**: Event-driven Import Services (IMPORT_STARTED/COMPLETED Events)
- **feat(services)**: Duplicate Detection (Visual + Text via imagehash + TF-IDF)
- **chore(infra)**: imagehash + scikit-learn Dependencies
- **chore(config)**: 2026-Q1 Feature Roadmap Dokumentation

## 2026-02-14
- **fix(frontend)**: Token trimming + mandatory WebSocket auth validation (13 Dateien, .trim() an allen Token-Stellen)
- **test(frontend)**: 23 WebSocket URL-encoding und Auth-Validierung Tests (6 Dateien)
- **fix(frontend)**: IT10 - 4x `.trim()` an backend-sourced Token-Stellen (auth.ts x2, client.ts x1, portal-api.ts x1) - Bearer-Token-Trim jetzt 19/19 (100%)
- **audit**: IT11 - Senior Review: Null-Safety bewiesen (if-Guards + try-catch + TypeScript strict), 2 pre-existing DEFERRED (T1: refreshToken Return-Type, T2: fehlender || '' Fallback)
- **audit**: IT12 - Meta-Review: 3 Agent-Findings cross-checked (1 False Alarm G1: Loop-Reset, 1 Zaehl-Fehler: 19 korrekt nicht 20), IT11-Implementierung KORREKT und VOLLSTAENDIG bestaetigt
- **feat(frontend)**: Phase 1 - Spotlight Cmd+K Schnellsuche (parallele Dokument/Entity/Autocomplete-Suche)
- **feat(api)**: Spotlight API Endpoint mit Rate Limiting und <200ms Ziel
- **feat(frontend)**: Phase 1 - OCR Batch Correction Admin-Seite mit Inline-Editor
- **feat(frontend)**: Phase 2 - Smart Upload Overlay (Drop & Forget mit Auto-Klassifizierung)
- **feat(frontend)**: Phase 2 - Smart Tags System mit AI-Vorschlaegen
- **feat(frontend)**: Phase 2 - Auto-Learning Dashboard (Daily Review, Stats, Recent Actions)
- **fix(docs)**: 3 Docs von process_document_ocr auf process_document_task aktualisiert (M1-Rest)
- **fix(frontend)**: OcrBatchCorrectionTable Fragment key + Dockerfile Typo
- **feat(db)**: Migrationen 222-223 (Folder Hierarchy, Knowledge Graph Autonomy)
- **feat(services)**: 5 neue Services (Folder, Booking Suggestions, Learning Autonomy, Summarization, Threat Detection)
- **feat(api)**: 5 neue Endpoints (folders, booking_suggestions, comment_threads, learning_autonomy, summarization)
- **feat(frontend)**: Vitest Test-Setup mit Browser API Mocks
- **test**: E2E (10), Integration + Unit Tests + Chaos Engineering Framework
- **feat(infra)**: Compliance Infrastructure (GDPR, GoBD, ISO27001)
- **chore(orchestration)**: Ralph Loop - Critical Review Task

## 2026-02-13
- **refactor(workers)**: Celery Task Names - Full-Path Migration (87 Dateien)
- **feat(api)**: 10 neue Enterprise Endpoints (collaboration, data_quality, digital_twin, document_hints, invoice_pipeline, ml_dashboard, smart_search, trust_dashboard)
- **feat(services)**: 9 neue Enterprise Services (Collaboration, Data Quality, Digital Twin, Document Hints, Invoice Pipeline, ML Dashboard, Smart Search, Trust Dashboard)
- **feat(frontend)**: CEO Dashboard Components (Data Quality, Digital Twin, KPIs, Compliance, Risk)
- **feat(frontend)**: Collaboration Features (ActivityTimeline, DocumentLock, Mentions, Presence)
- **feat(frontend)**: Smart Search mit Autocomplete
- **feat(db)**: Migrationen 220-221 (Collaboration Tables, Merge Heads)
- **refactor(services)**: Portfolio Services entfernt (financial_goals, portfolio)
- **refactor(core)**: Cache cleanup - get_cache_stats deprecated
- **fix(db)**: Alembic Migrations 208, 209, 215, 216 asyncpg-hardened
- **chore(infra)**: requirements.txt updates (aiohttp, reportlab[rlPyCairo])
- **test**: 6 neue Tests (psd2_banking_flow, autonomous_trust_upgrades, smart_search, retention_enforcement)
- **docs**: 2 neue Feature-Docs (Auto-Invoice-Pipeline, Document-Hints)
