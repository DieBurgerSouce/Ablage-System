# Recent Changes

## 2026-02-24
- **feat(db)**: DomainEvent SHA-256 Hash-Chain (event_hash, previous_hash, chain_hash) - Migration 254 + models_misc.py + models_predictions.py
- **feat(db)**: Migration 255 - EntitySeasonalPattern fuer saisonale Zahlungsmuster (Cashflow Monte Carlo)
- **feat(services)**: EventStore SHA-256 Hash-Chain-Berechnung bei jedem append() - event_emitter.py + __init__.py Export
- **feat(services)**: CashflowPredictionService - saisonale Verzoegerungsfaktoren (SEASONAL_DELAY_FACTORS) in Monte Carlo Simulation
- **feat(workers)**: recompute_seasonal_patterns Task + Celery Beat (woechentlich Sonntag 03:00)
- **feat(api)**: Domain Events in documents.py (document_created, document_deleted, document_exported), entities.py (entity_modified), invoices.py (invoice_status_changed)
- **feat(frontend)**: WebSocket onRawMessage() Handler + sendMessage() Methode + useRawMessage() Hook
- **feat(frontend)**: TypingIndicator Komponente + useTypingIndicator Hook + SplitDocumentViewer Integration

## 2026-02-22 (Session 5)
- **feat(workers)**: trigger_auto_filing_pipeline_task - vollautomatische Ablage-Pipeline nach OCR-Abschluss (Redis Pub/Sub Progress, DSGVO-konform)
- **feat(workers)**: ocr_tasks.py - Auto-Filing Pipeline nach OCR success getriggert (filing_pipeline_task_id im Result)
- **feat(api)**: review_queue.py - GET /review-queue + POST /documents/{id}/confirm-filing (Pipeline-Ergebnisse bestaetigen)
- **feat(api)**: main.py - review_queue_router registriert
- **feat(services)**: DocumentPipelineOrchestrator - Smart Document Matching (Step 2b) via SmartMatchingService
- **feat(services)**: event_broadcaster.py - 10 neue Pipeline-Event-Typen + broadcast_pipeline_progress() Helper
- **feat(frontend)**: websocket.ts - 5 neue Pipeline-EventTypes + Invalidation-Mapping fuer review-queue
- **feat(frontend)**: use-auto-filing-progress.ts - Hook fuer Echtzeit-Pipeline-Fortschritt

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


