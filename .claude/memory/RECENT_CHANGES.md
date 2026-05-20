# Recent Changes

## 2026-05-20 (Sprint-1 — Sec-Reste aus MASTER_REVIEW)

Branch: `sprint-0-pilot-hardening`, 5 saubere Commits zur Pilot-Reife. Aus
`.claude/reviews/2026-05-19/MASTER_REVIEW_2026-05-19.md` HIGH-Sec Phase B+. Plan
unter `C:\Users\benfi\.claude\plans\guck-dir-bitte-nochmal-recursive-lollipop.md`.

- **S1.2** `59a5702f`: `app/api/v1/retention_admin.py` 3x `safe_error_detail` Args
  geswapped — Signatur ist `(e, context)`, nicht `(context, e)`. Sanity-Grep
  ueber `app/api/v1/` clean; `collaboration.py` hat 12 separate Misuses (kein
  PII-Leak, nur UX-Bug) als Backlog-Task notiert.
- **S1.3** `cf062e80`: `app/api/v1/graphql_api.py` `ALLOWED_FILTER_FIELDS`
  Whitelist pro Entity ergaenzt (CWE-89 Field-Oracle-Schutz). Whitelist
  enthaelt bewusst kein iban/vat_id/tax_id/password_hash/totp_secret.
- **S1.4** `dd693f14`: `app/api/v1/nlq.py` `NLQQueryResponse.generated_sql`
  auf `Optional[str]` und nur fuer `is_superuser` exposed.
- **S1.5** `d56cd145`: `InvoiceTracking.entity_id` Column nachgezogen
  (Migration 094 hatte die DB-Spalte, Model deklarierte sie nicht trotz
  50+ Service-Usages). Drift-Pattern analog Task B. F4-DONE-Block in
  `docs/drift/invoice-model-drift.md`.
- **S1.1** `e8f6badb`: `app/api/v1/trash.py` `permanently_delete_document` und
  `empty_trash` brauchten `company_id`-Filter; `empty_trash` Bulk-DELETE
  statt N+1 `await db.delete(doc)` in Schleife. Audit-Event
  `document_permanently_deleted` VOR Hard-Delete via `emit_domain_event`.
  Defense-in-Depth: `owner_id` bleibt als zweiter Filter.

Tests fuer alle 4 API-Endpoints (test_trash_api.py, test_retention_admin_api.py,
test_graphql_api.py, test_nlq_api.py) als Phase-D-Backlog-Tasks angelegt
(Sprint-1 Scope war NUR die Sec-Fixes, Tests sind Phase D).

Out-of-Scope: Sentry-DSN (G10 User-Action), 9 aktive Critical Alerts (P0b
vor Pilot), Backup-Encryption (G06).

## 2026-05-19 (Multi-Agent Review Follow-Through - Tasks A, B, C, D, F1, F2)

Branch: `sprint-0-pilot-hardening`, 6 saubere Commits zur Pilot-Reife.

- **docs(env)** `74210d8e`: .env.example um 37 undokumentierte Vars ergaenzt (Pilot-Onboarding) - Drift zwischen .env und .env.example geschlossen, 5 neue Sektionen (Infrastructure, MinIO, Qdrant, Vector-AB, OCR/GPU, Security, Monitoring)
- **fix(db)** `37baeb94`: Invoice-Model `company_id` Column nachgezogen - DB-Spalte existiert seit Migration 022, Model deklarierte sie nicht. + Drift-Report `docs/drift/invoice-model-drift.md`
- **fix(api)** `e1e99825`: Invoice-API von `Document.owner_id` (User-Scope) auf `Document.company_id` (Tenant-Scope) - 19 Endpoints via neuem FastAPI-Dependency `get_user_company_id_dep`, 16 Filter + 12 current_user.company_id-Referenzen aufgeloest, 5 dead checks entfernt. Pattern analog zu 2026-01-18 Workflow/Banking-Fixes (F3)
- **fix(alerting)** `1b0c76d3`: Alertmanager SMTP-Auth via file-mount (analog Slack) - 3x leere auth_password='' durch `auth_password_file:/etc/alertmanager/smtp-password` ersetzt, Mount + .gitignore + Setup-Doku
- **fix(db)** `81ff78c1`: business_contact_id Phantom-Column aus Invoice-Model entfernt (F1) - DB hatte die Spalte nie, dead code in Model + relationship + Index. 0 Code-Usage ausserhalb Model.
- **fix(bi)** `7badff26`: business_intelligence_service.py Invoice.entity_id Runtime-Bomben aufgeloest (F2 Option B) - 7 Stellen (5x Invoice.entity_id, 2x Document.entity_id), JOIN Document + business_entity_id genutzt. Code-Path lebt (8 rag-API-Aufrufer), F4 (InvoiceTracking-Drift) als Folge dokumentiert.

Out-of-Scope: Sentry-DSN (user-action, G10), Disk-Cleanup, 9 Live-Alerts triage, Vault aktivieren - alle in SPRINT_0_OPEN.md / Pilot-Log dokumentiert.

## 2026-03-10
- **chore(infra)**: Prometheus Backup + A/B-Testing Scrape-Jobs aktiviert (Token-Auth, kein Superuser noetig)
- **fix(db)**: Migration 260 Domain Constraints - required_columns Idempotenz, confidence_score Spaltenname korrigiert
- **feat(api)**: Prometheus /internal/backup + /internal/ab-testing Endpoints (Token-Auth, graceful degradation)
- **feat(frontend)**: SpotlightDialog in AppLayout integriert + vollstaendiges Spotlight Feature-Modul
- **test(services)**: 5 neue Unit-Tests (Security, Shipping, Signature, Tenant, Webhooks)
- **chore(infra)**: GitHub Actions Digest-Pinning fuer alle Workflows (Supply Chain Security)
- **chore(infra)**: Docker Multi-Stage Builds (worker, backend) - Build-Tools aus Produktions-Images entfernt
- **feat(db)**: Migrationen 257-261 (Missing Constraints, Indexes, Default Roles, Domain Constraints, Query Performance)
- **feat(frontend)**: Dokumenten-Graph Sidebar-Link + Route + Feature-Modul (document-graph)
- **test(services)**: 30+ neue Unit-Tests (OCR, Banking, API, Security, DATEV, Services)

## 2026-02-27 (Enterprise Quality Audit - Phase 5 P2 Langfristig)
- **refactor(logging)**: Migrate 89 files from stdlib `logging` to `structlog` (Phase 5.3 Logging-Konsistenz) - workers, services, API, ML, core, agents
- Transformations: `import logging` -> `import structlog`, `logging.getLogger(__name__)` -> `structlog.get_logger(__name__)`, `extra={}` -> keyword args, `exc_info=True` -> `logger.exception()`
- Only `logging_config.py` retains stdlib logging (bridge config). 100% structlog coverage across app/

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


