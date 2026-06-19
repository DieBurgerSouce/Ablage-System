# Welle-1 Master-Findings-Register (A-Z Komplett-Exploration) - 2026-06-19

Branch: qa/az-deep-offensive-2026-06-18. Methode: 9 parallele Read-only-Explore-Agents (Backend,
API-Mutationen, Frontend, Daten/DB, Tests/CI, Security, Docs/Obsidian, Git, Infra) + Cross-Verifikation
gegen echte DB (ablage-postgres, Head 268) und laufende Container. Phase 1 (GET-500: 192->0) ist fertig;
dies erfasst ALLES ANDERE. Severity P0 (kaputt/Security) -> P3 (Kosmetik).

## A. P0 - Echte Defekte am laufenden System / Sicherheit
- W2-01 Beat crash-loopt (RestartCount=250): torch->CuPy makedirs auf read-only-Rootfs, kein Cache-Volume
  -> Scheduled Tasks (GDPR-Loeschung/Backups/Retention/SLA) laufen NICHT. (docker logs ablage-beat)
- W2-02 GPU-Worker (solo) 4.5h verkeilt auf escalate_overdue_approvals -> OCR-Pipeline steht (ocr_normal=1).
- W2-03 SMTP ohne Timeout: smtplib.SMTP(host,port) blockiert unbegrenzt -> Ursache W2-02.
  (notification_service.py:628; approval_tasks.py:175,300)
- W2-04 /health/startup 503 = ECHTER Bug: _check_redis() nutzt redis://localhost:6380 ohne AUTH statt
  settings.REDIS_URL. (health.py:182-185, auch :2110)
- W2-05 SSO-Login komplett kaputt: User(company_id=,role=) + user.role= - User hat weder Spalte noch Setter
  -> jeder SSO-Login crasht. (sso.py:924,968-978,1007)
- W2-06 WS-JWT im URL-Query (?token=) -> Log/History-Leak -> Auth-Uebernahme. (websocket.py:77,268)
- W2-07 2FA-Bypass an DEBUG: auf master NOCH OFFEN (P0); im Worktree behoben (rbac.py TESTING). Fix->master.
- W2-08 Portal portal-session-expired hat KEINEN Listener -> Portal-Kunde stille 401, kein Redirect.
- W2-09 SCAN-Cursor-Endlosschleife (Prod-Bug): invalidate_cache cursor='0' (str) vs redis int -> jede
  Such-Cache-Invalidierung lief endlos. Fix nur offensive, nicht master.

## B. P1 - Systemische Korrektheits-/Tenancy-/Daten-Risiken
- W2-10 company_id:UUID=Depends(require_company) Typ-Luege (liefert Company-Objekt) -> 20 Mutations-Endpunkte
  500/404. (smart_tagging.py:127,193,272; audit_trail_visualization.py:257+; tax_advisor_packages.py:279+)
- W2-11 bare Depends(get_current_company_id)/get_company_id (~22 Dateien): None->Insert-500 ODER beliebiger
  X-Company-ID-Header -> Cross-Tenant-Write (IDOR). -> get_user_company_id_dep.
- W2-12 getattr(user,'company_id',None) liefert IMMER None -> Tenancy-Filter uebersprungen (DLP ueber alle
  Mandanten). (dlp.py:149-427; calendar.py; magic_buttons.py; sso.py:1035)
- W2-13 User.company_id-Phantom-Reste: ai_action_service.py 17x, smart_inbox/inbox_aggregator.py:542,
  workflow/workflow_engine_service.py:828.
- W2-14 Weitere Phantom-Spalten: Company.settings (einvoice/receiver_service.py:790), Document.metadata
  (extended_alerts_service.py:662,718; template_tasks.py:315 -> document_metadata).
- W2-15 Enum values_callable-Drift (LATENT, feuert beim ERSTEN Schreibzugriff): BusinessContract.contract_type
  (1118), ContractMilestone.milestone_type (1296), ContractAmendment.status (1465), recurring_invoice
  (interval/status/detection/occurrence), budgets (period/status/line/source/severity), inventory
  (movement_type/status :277,280), po_matching (category/severity), document_templates. DB lowercase.
- W2-16 CrossDBJSON .astext/.contains/.op ohne cast(col,JSONB) (~55 Stellen): Dokumentsuche
  (extracted_data.py:199-310), datev (scan_to_booking, plausibility), banking_tasks.py:70-104,
  entities.py:521+, tags.contains 4+ Services.
- W2-17 Approval-Workflow: Approver-Rolle nicht validiert (Priv-Esc) + kein State-Check; /orchestration/
  decisions/{id}/approve|reject ohne Tenancy; /workflows/trigger/{webhook_path} unauth.
- W2-18 Feature-Stubs liefern leere Daten (F-31 minimal): enhanced_fints get_aggregated_*/pending/list
  (ignoriert persistierte bank_accounts!), fraud_early_warning.get_alerts->[], handelsregister (in-memory+
  md5-Mock), zero_touch.get_pending_reviews, daily_insights (in-memory).
- W2-19 NLQ-SQL company_id per String-Interpolation statt Bind (Cross-Tenant-Leak). sql_sanitizer.py:228+
- W2-20 SSO/OIDC error_description unkodiert in Location-Header (CRLF/Redirect-Injection). sso.py:583
- W2-21 Portal-Auth ohne Rate-Limiting; IMAP-Host/Port ohne SSRF-Validierung (email_import_service.py:190).
- W2-22 Frontend Token-Ablauf ohne Redirect: AuthContext.user wird bei session-expired nie geleert ->
  401-Welle hinter dismissbarem Modal; RAG-Chat/WS umgehen Interceptor (kein Refresh).
- W2-23 Money: VAT net/vat unabhaengig quantisiert (net+vat!=gross); float() auf Numeric(15,2)
  (skonto/partial_payment); DATEV/skonto ohne ROUND_HALF_UP. GoBD/USt-relevant.
- W2-24 Worker-Durability: Backup+DB-Write-Tasks ohne retry/acks_late/time_limit; CPU-Worker
  check_experiment_completion Endlos-"Retry in 0s" (OSError RO-FS).
- W2-25 Tests: Auth-Modul still geskippt (importorskip aiosqlite); Multi-Tenancy DB-gated; 192 GET-500-Fixes
  ohne Regressionstest; Coverage-Gate widerspruechlich (80 vs 50) rot; Schemathesis/ZAP non-blocking;
  Frontend-Tests in KEINER CI.
- W2-26 Worker-/Beat-Healthcheck nur pgrep -> "healthy" trotz Wedge/Crashloop; /health/workers false-kritisch.

## C. P2/P3 - Qualitaet, Observability, Doku, Cleanup
- W2-27 OTEL/Jaeger "OK" dokumentiert, aber kein opentelemetry-Paket -> Tracing tot; Jaeger memory-storage;
  Sentry default aus.
- W2-28 Keine DLQ-/Per-Queue-/Worker-stuck-Alerts; DLQ bei Redis-Broker nur App-getrieben.
- W2-29 Async-Lazy-Load (MissingGreenlet): lazy="dynamic" Document.ocr_feedbacks (hot) u.a.; pervasive
  Default-Lazy auf Hot-Models ohne selectinload.
- W2-30 FK ohne ondelete (RESTRICT->500 bei Parent-Delete) in einvoice/erp_import/fx/inventory/template;
  create_all-Drift (Migration 265 -> Orphan-Enums).
- W2-31 Frontend: 0/302 Routen mit beforeLoad-Guard (admin nur backend-403); 0 errorComponent; ~15
  verwaiste Routen; redundante Bereiche; 80+ Icon-Buttons ohne aria-label; Token in sessionStorage (XSS).
- W2-32 Doku: "Production-Ready"/"Type-Safe" widerlegt (192 GET-500); B1-B4 in 4 widerspruechlichen
  Schichten; alembic head 267 vs real 268; Entity-Risk "Production-Ready" trotz Stubs; init-db.sql nutzt
  ablage_ocr statt ablage_system; Vault POC-Altlast + falsche Ports (5432/6379 vs 5434/6380).
- W2-33 Git: master enthaelt KEINEN P0/P1-Fix der letzten 8 Tage (alles offensive+az-deep ungemergt);
  ungesichert: 3 cursor-Worktrees, ocr-perf (Tag-Backup), 7 Stashes (1/4/6 sichten).
- W2-34 Transaktion/Concurrency: audit_chain sequence_number ohne Lock; auto_matching/approval ohne Rollback.
- W2-35 TODO(G4) worker_control restart unimpl; risk_scoring externe Quellen Stub; FinTS mock-only (PSD2 outscoped).

## Korrigierte Fehlalarme (NICHT bearbeiten)
ESG user.company_id (nutzt get_user_company_id), privacy_analytics, contracts.py:555, classification.py
(nutzen company.id), shadcn Select Rule#7 (eingehalten), Folder.permissions (gepinnt), approval_requests.status
(varchar, aufgeloest), 2FA-Bypass (im Worktree behoben). Echter User.company_id-Phantom NUR in sso/ai_action/
smart_inbox/workflow_engine.

## Welle-2 Aktionsplan (Fix + A-Z-Simulation im Loop)
1. Infra-P0 (W2-01..04): Beat-Cache, SMTP-Timeout+Queue-Trennung, Health-Redis-Probe (Orchestrator selbst).
2. SSO-Crash (W2-05) + WS-Token (W2-06).
3. Mutations-Tenancy (W2-10/11/12) + user.company_id-Reste (W2-13/14) via parallele Fix-Agents.
4. Enum-Drift (W2-15) + CrossDBJSON cast (W2-16, v.a. Dokumentsuche).
5. Feature-Stubs echt/ehrlich (W2-18).
6. A-Z-Simulation: Mutations-Sweep (POST/PUT/DELETE) + Browser-E2E kritischer Flows im Loop, fix+dokumentiert.
7. Security-P1 (W2-19/20/21) + Money (W2-23) + Worker-Durability (W2-24).
8. Regressionstests (W2-25). 9. Doku/Git konsolidieren + Tracing/Alerts.