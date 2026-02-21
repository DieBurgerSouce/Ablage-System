# Recent Changes

## 2026-02-21
- **feat(db)**: 13 neue Alembic-Migrationen (238-250): CDC, Partitioning, Optimistic Locking, Encryption, Anomalie, Summaries, Clustering, Active Learning, Morning Briefing, Integration Sync, Dashboard Builder, Webhook Event Platform, Feature Toggle History
- **feat(db)**: 9 neue Satellite-Models (models_cdc, models_clustering, models_partitioning, models_encryption, models_anomaly, models_active_learning, models_webhooks, models_integration_sync, models_dashboard)
- **feat(db)**: Document-Model erweitert (summary, keywords, one_liner, summary_model Felder + Partial Index)
- **feat(api)**: 13 neue API-Router registriert in main.py (webhooks_outbound, role_dashboards, explainability, morning_briefing, ai_chat, dashboard_builder, clustering, anomalies, active_learning, cdc, encryption, feature_toggles, integration_sync)
- **feat(services)**: Document Timeline Service umfangreich erweitert (1476 Zeilen Diff)
- **feat(workers)**: Celery - 2 neue Task-Module (webhook_tasks, partition_maintenance) + Beat-Schedules fuer Webhook-Retry und Partition-Maintenance
- **feat(frontend)**: use-auto-save-draft Hook fuer automatisches Speichern von Entwuerfen

## 2026-02-20
- **feat(api)**: HTTPException Handler - StandardErrorResponse mit correlation_id und Timestamp
- **feat(api)**: Search "Meinten Sie?" Funktion via pg_trgm bei 0 Ergebnissen
- **feat(services)**: GoBD Compliance Service - TypedDict (GoBDFinding, GoBDStatistics), Protocol-Klasse
- **refactor(api)**: build_content_disposition aus security_auth importiert (alle API-Dateien)
- **chore(infra)**: Dockerfile Multi-Stage Build (builder + production, uv fuer schnelle Installation)
- **chore(infra)**: Alertmanager - Email-Routing nach Schweregrad (critical/high/warning), kein null-receiver mehr
- **feat(api)**: app/core/pagination.py - wiederverwendbare Pagination-Utilities
- **test**: 4 neue Unit-Tests (crud_service, dunning_service, retention_service, search_suggestions)
- **feat(frontend)**: InvoiceWorkflowPage - data-tour Attribute fuer Onboarding-Tour (workflow-approval, workflow-review)
- **chore(config)**: ralph-loop Iteration 81 -> 131 aktualisiert

## 2026-02-19
- **feat(services)**: Zero-Touch Pipeline Chain (OCR->Klassifizierung->Kontierung->3-Way-Matching->Ablage) implementiert
- **feat(services)**: Auto-Kontierung Service (DATEV SKR03/SKR04, GoBD-konform) und 3-Way-Matching Service
- **feat(services)**: Image Diff Service fuer pixelweisen Dokumentenvergleich
- **feat(api)**: Knowledge Graph API (Entity-Graph, Shortest-Path, Community Detection)
- **feat(api)**: Saga Monitoring API (7 Endpoints: Liste, Details, Logs, Diagram, Retry, DLQ)
- **feat(api)**: Pipeline API (manueller Trigger und Status-Abfrage)
- **feat(workers)**: Pipeline Tasks, Saga Tasks und Vault Tasks (Secret-Rotation via HashiCorp)
- **feat(db)**: Migration 151 - GoBD INSERT-only Triggers fuer domain_events und gobd_audit_chain
- **feat(security)**: Vault Client Haertung (TTL-Caching, AppRole Auth, Retry mit Backoff)
- **feat(frontend)**: Knowledge Graph UI-Overhaul (GraphCanvas, GraphToolbar, Views), Product Tour (HelpTooltip, UserModeToggle), Visual Diff (ImageDiffViewer)

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

