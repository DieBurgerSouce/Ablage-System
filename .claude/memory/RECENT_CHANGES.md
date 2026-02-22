# Recent Changes

## 2026-02-22
- **feat(frontend)**: Webhook Admin Frontend (3 Tabs: Endpoints/DLQ/Event-Protokoll, 7 Komponenten, 11 Query Hooks)
- **feat(frontend)**: Sidebar-Link "Webhooks" fuer Admin-Benutzer
- **refactor(db)**: models.py auf Satellite-Architektur umgestellt - Basistypen (Base, CrossDBJSON, CrossDBTSVector, CrossDBVector) in models_base.py ausgelagert
- **feat(db)**: 20 neue Satellite-Model-Dateien (models_ai_ml, models_auth_access, models_banking, models_base, models_cash_company, models_datev, models_dropship_tax, models_entity_business, models_erp_import, models_gdpr_compliance, models_hr, models_integration, models_misc, models_notification, models_ocr_validation, models_privat_enterprise, models_privat_space, models_rag, models_report, models_surya_training, models_template_knowledge, models_workflow)
- **feat(frontend)**: Custom Fields Admin-Feature implementiert (Admin-Route /admin/custom-fields, CRUD-UI, API-Layer, TypeScript-Typen)
- **feat(frontend)**: Sidebar-Link "Eigene Felder" fuer Admin-Benutzer ergaenzt
- **feat(frontend)**: DocumentCustomFields-Komponente in SplitDocumentViewer (Cockpit-Tab) integriert
- **feat(frontend)**: TanStack Router routeTree.gen.ts mit AdminCustomFieldsRoute aktualisiert
- **test**: 2 neue Unit-Tests fuer BarcodesPipelineService und DocumentSummaryService
- **fix(security)**: Migration 251 - company_id zu DocumentGroup (Multi-Tenant Isolation, Backfill via user_companies, FK + Indexes)
- **fix(api)**: DocumentGroup 11 Endpoints + Transactions 6 Endpoints auf company_id Isolation umgestellt (groups.py, transactions.py, document_grouping_service.py)
- **fix(frontend)**: auth.ts refreshToken() Return/Fallback Bug behoben (T1+T2 aus Known Issues)

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


