# Recent Changes

## 2026-02-26 (Enterprise Quality Audit - Phase 4 P2 Hardening)
- **refactor(db)**: SoftDeleteMixin in models_base.py - 27 Klassen in 20 Model-Dateien refactored (manuelle deleted_at Definition ersetzt durch Mixin)
- **refactor(db)**: FK ondelete Cascade Audit - 44 ForeignKey-Deklarationen mit ondelete ergaenzt (CASCADE/SET NULL/RESTRICT je nach FK-Typ) + Migration 256
- **refactor(core)**: Dict[str, Any] → JSONDict in exceptions.py (16x) und audit_logger.py (10x) fuer Type Safety
- **fix(frontend)**: React index-as-key Anti-Pattern behoben - 12 Instanzen in 5 Komponenten (FieldDefinitionDialog, GlobalAIAssistantV2, WorkflowMonitor, RecoveryPlaybook)
- **feat(api+services)**: Action Queue, Access Analytics, Banking PSD2, AI Financial Orchestrator Endpoints
- **feat(workers)**: Task Error Handling (45 Tasks) + Transaction Savepoints + Startup Health Gate
- **chore(infra)**: Nginx Security Headers + Docker Digest Pinning + Rate Limits

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


