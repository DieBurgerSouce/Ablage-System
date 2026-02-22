# Recent Changes

## 2026-02-22 (Session 4)
- **feat(ocr)**: Document DNA + Cross-Validation Services - Layout-Fingerprinting und Feld-Plausibilitaetspruefung in OCR-Pipeline
- **feat(ocr)**: OCR Learning Tasks + Celery Beat (Correction-Queue alle 30min, Pattern-Apply 03:00)
- **feat(api)**: DATEV Zero-Touch-Stats + Steuer-Assistent Endpoints (Kategorisierung, Elster-Export)
- **feat(services)**: Scan-to-Booking Orchestrator + DATEV Plausibility Service (Zero-Touch Pipeline)
- **feat(services)**: Privat P5.1 Contract Management + P5.2 Tax Assistant Service
- **feat(db)**: models_privat_contracts.py (PrivatContract, PrivatContractReminder) + Re-Export in models.py
- **feat(workers)**: booking_tasks.py + send_contract_reminders + datev-batch-auto-booking (15min Beat)
- **feat(frontend)**: OnboardingWizard integriert (P4.1) + Product Tour modularisiert; Backup-Skripte + DR-Runbook

## 2026-02-22 (Session 3)
- **feat(workers)**: Prometheus-Metriken fuer GDPR-Tasks (6 Metriken: gdpr_deletion_requests_pending, gdpr_deletion_processing_duration_seconds, gdpr_deletion_completed_total, gdpr_deletion_errors_total, gdpr_breach_notifications_total, gdpr_compliance_score)
- **feat(workers)**: Prometheus-Metriken fuer Retention-Enforcement-Tasks (7 Metriken: scanned, marked, deleted, errors, scan_duration, documents_by_category, pending_reviews)
- **feat(infra)**: Neues Grafana-Dashboard ablage-retention-enforcement.json fuer Retention-Enforcement-Monitoring
- **test(frontend)**: use-chat-websocket.test.ts - neue Frontend-Tests fuer Chat-WebSocket-Hook
- **test(frontend)**: portal-api.test.ts - neue Frontend-Tests fuer Portal-API

## 2026-02-22 (Session 2)
- **refactor(db)**: Model-Refactoring - 8 Satellite-Models nutzen Re-Exporte statt Duplikat-Definitionen (bpmn_models, annotations, collaboration, clustering, integrity, learning_autonomy, signature)
- **fix(db)**: WebhookDelivery umbenannt in WebhookSubscriptionDelivery (Tablename + Indexes + Relationships)
- **feat(security)**: ConflictError (E409) und ServiceUnavailableError (E503) Exception-Klassen hinzugefuegt
- **fix(api)**: webhooks.py + webhook_dispatcher.py auf WebhookSubscriptionDelivery aktualisiert
- **fix(services)**: PaymentService company_id Fix - 9 Methoden von company_id auf user_id umgestellt (BankAccount.user_id statt company_id)
- **fix(services)**: LiquidityForecastService - ueberfluessiger company_id Parameter in _create_rolling_forecast() und _detect_payment_anomalies() entfernt
- **fix(orchestration)**: team_router_hook.py - Trivial-Pattern-Filter vereinfacht (keine Fragen/Exploration mehr als trivial blockiert)

## 2026-02-22
- **feat(db)**: Migration 253 - GoBD/DSGVO Compliance SQL Views (gobd_audit_summary, gdpr_deletion_status)
- **fix(frontend)**: AppLayout.tsx - id-Prop auf semantisch korrektes main-Element verschoben (statt div)
- **feat(frontend)**: Webhook Admin Frontend (3 Tabs: Endpoints/DLQ/Event-Protokoll, 7 Komponenten, 11 Query Hooks)
- **feat(db)**: Migration 252 - GoBD Audit-Felder (created_by_id, updated_by_id) fuer PaymentBatch und DunningRecord
- **feat(services)**: DunningService GoBD-Audit Integration - user_id Parameter fuer Nachvollziehbarkeit
- **feat(api)**: Visual Diff - neuer POST /compare/documents Endpunkt fuer Text-Diff per Dokument-ID
- **fix(security)**: CWE-113 CRLF-Sanitisierung X-Company-ID Header + Migration 251 DocumentGroup Multi-Tenant Fix
- **test**: Webhook Unit-Tests (InboundWebhookService + API) vollstaendig erstellt

## 2026-02-21
- **feat(db)**: 13 neue Alembic-Migrationen (238-250): CDC, Partitioning, Encryption, Anomalie, Summaries, Clustering, Active Learning, Morning Briefing, Integration Sync, Dashboard Builder, Webhook Platform, Feature Toggle
- **feat(api)**: 13 neue API-Router registriert in main.py
- **feat(services)**: Document Timeline Service umfangreich erweitert (1476 Zeilen Diff)
- **feat(workers)**: Celery - 2 neue Task-Module (webhook_tasks, partition_maintenance) + Beat-Schedules
- **feat(frontend)**: use-auto-save-draft Hook fuer automatisches Speichern von Entwuerfen

## 2026-02-20
- **feat(api)**: HTTPException Handler - StandardErrorResponse mit correlation_id und Timestamp
- **feat(api)**: Search "Meinten Sie?" Funktion via pg_trgm bei 0 Ergebnissen
- **feat(services)**: GoBD Compliance Service - TypedDict, Protocol-Klasse
- **chore(infra)**: Dockerfile Multi-Stage Build + Alertmanager Email-Routing nach Schweregrad
- **test**: 4 neue Unit-Tests (crud_service, dunning_service, retention_service, search_suggestions)

## 2026-02-19
- **feat(services)**: Zero-Touch Pipeline Chain (OCR->Klassifizierung->Kontierung->3-Way-Matching->Ablage)
- **feat(api)**: Knowledge Graph API + Saga Monitoring API (7 Endpoints) + Pipeline API
- **feat(workers)**: Pipeline Tasks, Saga Tasks und Vault Tasks (Secret-Rotation via HashiCorp)
- **feat(frontend)**: Knowledge Graph UI-Overhaul, Product Tour, Visual Diff (ImageDiffViewer)
- **feat(security)**: Vault Client Haertung (TTL-Caching, AppRole Auth, Retry mit Backoff)
