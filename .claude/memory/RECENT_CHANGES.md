# Recent Changes

## 2026-02-22
- **feat(frontend)**: Webhook Admin Frontend (3 Tabs: Endpoints/DLQ/Event-Protokoll, 7 Komponenten, 11 Query Hooks)
- **feat(frontend)**: Custom Fields Admin-Feature implementiert (Admin-Route /admin/custom-fields, CRUD-UI, API-Layer, TypeScript-Typen)
- **feat(db)**: 20 neue Satellite-Model-Dateien fuer alle Domaenen
- **fix(security)**: Migration 251 - company_id zu DocumentGroup (Multi-Tenant Isolation, Backfill via user_companies, FK + Indexes)
- **fix(api)**: DocumentGroup 11 Endpoints + Transactions 6 Endpoints auf company_id Isolation umgestellt
- **fix(security)**: DunningService + ReconciliationService - owner_id -> company_id Multi-Tenant Fix (Banking-Services)
- **fix(security)**: CWE-113 CRLF-Sanitisierung in HTTP-Headern (X-Company-ID in personal-api.ts + client.ts)
- **fix(frontend)**: auth.ts Token-Refresh Mutex (RC1) + refreshToken() Return/Fallback Bug (T1+T2) behoben
- **feat(db)**: Migration 252 - GoBD Audit-Felder (created_by_id, updated_by_id) fuer PaymentBatch und DunningRecord
- **feat(services)**: DunningService GoBD-Audit Integration - user_id Parameter fuer create/escalate/close
- **feat(api)**: Visual Diff - neuer POST /compare/documents Endpunkt fuer Text-Diff per Dokument-ID
- **test**: Webhook Unit-Tests (InboundWebhookService + API) vollstaendig neu erstellt

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


