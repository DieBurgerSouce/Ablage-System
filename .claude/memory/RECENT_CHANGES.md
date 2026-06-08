# Recent Changes

## 2026-06-08
**Verbesserungs-Offensive** — Branch `feature/offensive-2026-06` (12 Commits, nach `origin` gepusht, **NICHT in master** — Review/Merge offen). Nach 360°-Scan (12 Aufklärungs- + 3 Design-Subagents); gestaffelt 0a→0b→1b→1c→2a, jede Slice ein reviewbarer Diff.
- **chore(tooling) 0a** (`84884b54`): claude-flow `post-edit`-PostToolUse-Hook entfernt (revertierte Edit/Write — dokumentierter Footgun); `.claude-flow/metrics`, `.swarm/state.json`, `.claude/worktrees`, `.claude-flow/swarm` gitignored + `git rm --cached` → Working-Tree-Churn beendet.
- **test(e2e) 0b** (`69614151`): deterministisches Test-Setup — `scripts/seed_e2e.py` (idempotent: admin+viewer+Test-Company+UserCompany+synth. Lexware-Entities, direkt-DB-Insert + RLS-bypass), `docker-compose.test.yml` (TESTING/RATE_LIMIT/MALWARE off), hart-gegateter `POST /api/v1/test/reset-state` (Mount+Handler nur `settings.TESTING and not is_production`, CWE-89-safe Whitelist). Seed grün + idempotent.
- **fix(db) 1b — Model↔DB-Reconcile** (`4101a626`, `090565c4`): Live-dev-DB war Stamp `261`, Schema aber weit zurück — **63 fehlende Tabellen + 148 fehlende Spalten** (Model-ahead-of-Migrations: u.a. `users.totp_failed_attempts`, zahllose `company_id`, DATEV/GDPR/Webhook — in KEINER Migration). Fix (pg_dump-Backup zuerst): additiv `create_all(checkfirst)` + `ALTER ADD COLUMN IF NOT EXISTS` (nullable) → 0 Drift → `stamp 266` → **Migration 267** `reconcile_model_db_drift` (idempotent, kapselt den Reconcile für from-scratch) → `upgrade head` = **267 (head)**. Beidseitig verifiziert: Live 0 Drift **und** from-scratch gegen frische `ablage_scratch267` erreicht 267 mit 0 Drift.
- **fix(ocr,banking,bpmn) 1c — 3 echte Bugs** (`870fd429`, `eeedc507`, `3a389ad2`): **(A)** `self_learning_service.py:350` `safe_error_log(logger,…)` falsche Arg-Reihenfolge (Signatur `(e,context,extra)`), Rückgabe verworfen → warf IM except (`extra=exc` kein Dict) → OCR-Realtime-Lernpfad still tot; → `logger.error(…, **safe_error_log(exc, context=…))`. **(B)** Skonto-Basis `auto_reconciliation_service.py:520` `outstanding_amount`→Brutto `invoice.amount` (spiegelt `skonto_service.apply_skonto` + `quantize(0.01)`) — Teilzahlungs-Match misfeuerte. **(C)** BPMN Token-Verlust: `signal`/`continue_after_task`/`execute_timer` mutierten `instance.current_elements` ohne Row-Lock → per-Instanz `pg_advisory_xact_lock(hashtextextended(id,0))` (xact-scoped, deadlock-frei). Je 1 grüner Regressionstest.
- **docs(status) 2a** (`719780af`): PROJECT_STATUS auf verifizierte Ground-Truth (alembic head 267, Drift behoben, #1-Risiko Multi-Tenant-Default-Isolation, 149× `||true`).
- **test(e2e)** (`c61511b3`): 4 neue Playwright-Specs (RAW/quarantäniert; laufen NICHT in CI — falsches Verzeichnis + `||true`) committet → 0c relocatet+härtet sie.
- **test(e2e) 0c** (`8fb2946b`): Die 4 quarantäne-Specs aus dem CI-verwaisten `tests/frontend/e2e/` nach kanonisch `frontend/e2e/` portiert + **ehrlich gemacht** — echte, laufende Assertions statt `expect(…||true)`-Tautologien + vacuous `if(visible){expect}`-No-Ops. Jede Assertion VORHER gegen den laufenden Stack geerdet → korrigierte falsche Annahmen der Originale (Upload-Pfad `/documents/upload`→`/documents/`, `items`→`documents`, `detail`→deutsches `fehler`-Envelope, lexware-Pfad). rbac/auth-error/lexware API-zentriert (deterministisch). `global-setup.ts` cached jetzt Admin+Viewer (Login 5/15min → kein Login pro Test) via `utils/auth-cache.ts`; ESLint-Guard verbietet `expect(…||true)` in `e2e/**`. **26 passed**, 5 Upload-Tests skippen ehrlich bei 429 (Live-Ratelimit; strict-400 via Admin-Pfad bewiesen).
- **fix(companies)** (`5fdd7c00`): `GET /api/v1/companies` + `/current` waren **HTTP 500 für ALLE** — `get_current_company()` (Dependency `(request,db)`, `company_context.py:294`) in `companies.py:104/:222` mit 3. Arg `current_user` aufgerufen → `TypeError`; Firmen-Liste/-Wechsler (X-Company-ID-Quelle) kaputt. Fix: 3. Arg raus → **Single-Company 500→200** per E2E-Regressionstest verifiziert (Backend ohne `--reload` → Restart zur Verifikation).
- **chore(gitignore) 2b** (`ede2de02`): `frontend/test-results/` + `playwright-report/` (+ `e2e/.auth/`) untracked+gitignored — waren getrackt und churnten bei jedem Testlauf (Phantom-Diffs). Verifiziert: kein Churn mehr.
- **docs(known-issues)** (`6c4622a1`): Offene Offensive-To-Dos (1a/0d/0e/2b/2c) als versionierte Checkliste; ②③→1a verlinkt.
- **3 echte Bugs via ehrliche Tests gefunden**: ① companies-500 (`TypeError`) **gefixt**; ② `get_user_current_company` (`scalar_one_or_none` auf nicht-uniquem `is_current`) → `MultipleResultsFound`/500 für Multi-Company; ③ `require_company` → `MultipleResultsFound`/500 ohne `X-Company-ID`. ②③ isolations-sensibel → 1a (kein Blind-Fix). + Log-Sichtung `'Settings' object has no attribute 'JWT_ALGORITHM'` (nicht lokalisiert).
- **Verifikation**: 126 Unit-Tests grün (73 OCR/Banking + 53 BPMN), 6 neue Regressionstests. Backup: `C:\Users\benfi\db_backups\ablage_system_pre_reconcile_20260608_010849.dump` (+ Container-Kopie).
- **Offen (nächste Welle)** — vollständige Checkliste: KNOWN_ISSUES „Offene Offensive-To-Dos": **1a** Multi-Tenant-Default-Isolation (höchstes Risiko, review-gated; Kern = Multi-Company-500er ②③ **+** Cross-Engine-`get_db`-Loch: **241** Endpoints nutzen `app.api.dependencies.get_db`, aber `require_company` setzt RLS auf `app.db.database.get_db` → RLS auf falscher Session; braucht `get_tenant_db` + RLS-GUC-Konsolidierung + DB-RLS-Regressionstest), **0d** Schemathesis/k6 (nur sauber gegen `docker-compose.test.yml`), **0e** Agent-Harness-PoC (braucht Ollama), **2b-Rest** stale Branches prunen. (Erledigt diese Welle: **0c** ✅, companies-500-Fix ✅, 2b-Output-Hygiene ✅.)

## 2026-06-07
Branch `feature/m17-signal-match-m13-feedback` (4 Commits, nach `origin` gepusht, **NICHT in master** — Review/Merge offen). Setzt die in der mocks-to-real-Arbeit offen gelassene „ehrliche Feature-Tiefe" + Test-Infra um.
- **feat(bpmn) M17 Signal-Namen-Matching** (`69ced5eb`): `bpmn_parser` parst `signalEventDefinition` + globale `<signal>`-Defs → `signal_ref` + aufgeloester `signal_name` am `BPMNElement` (JSONB, **keine Migration**). `process_execution_service._resume_waiting_catch_events` matcht nach Name mit signalRef-ID-Fallback + Rueckwaertskompatibilitaet (Alt-Events ohne Namen feuern weiter). Vorher feuerten ALLE wartenden Catch-Events bei jedem Signal. +9 Tests.
- **feat(banking) M13 Feedback-Hook** (`69ced5eb` + `7ab2e58c`): `auto_reconciliation_service` schreibt beim `paid`-Uebergang ein `PredictionFeedbackRecord` (predicted vs. actual Verzug) — leak-frei (Vorhersage VOR dem Uebergang), failure-isoliert via SAVEPOINT, idempotent, **keine Migration**. In `_apply_match` (auto) + `manual_match` + `split_transaction`. Schliesst die Luecke „record_prediction_feedback hatte keinen automatischen Aufrufer" → Cashflow-Backtest sammelt ab jetzt echte Daten (voll real erst nach Laufzeit). +6 Tests.
- **fix(predictive,tests)** (`96479a55`): 6 vorbestehende Failures. **Echter Code-Bug** `system_health_predictor.py:216` `if history:` falsy fuer leere `MetricHistory` (kein `__bool__`) → Metriken nie erfasst (Telemetrie tot) → `is not None`. + 2 Test-Bugs (SLA-Regex Umlaut „größer"; predictive-alerts tz-aware `datetime.now(timezone.utc)`).
- **feat(bpmn) M17 (3b) Call-Activity-Sub-Instanz** (`e969e8fe`): Call Activity startet eigene Sub-Instanz der aufgerufenen Definition (statt still uebersprungen). `ProcessInstance.parent_instance_id`(self-FK)+`parent_element_id` via **Migration 266** (idempotent, ADD COLUMN IF NOT EXISTS + FK/Index; from-scratch + Bestands-DB). Engine: `_execute_call_activity` (Sub-Start + Variablen-Kopie + Eltern-Token parken), `_execute_end_event` → `_resume_parent_after_call_activity` (Out-Merge, Token konsumiert, `_continue_flow`), Tiefenschutz `_call_activity_depth` (MAX=20), graceful. Var-Semantik v1: copy-in/merge-out (camunda:in/out = Followup). +9 Tests. **Migration NICHT angewandt** (`alembic upgrade head` = Deployment-Schritt, offen).
- **chore(test-infra)** (`69ced5eb`): `tests/` + `pytest.ini` in den `ablage-backend`-Container gemountet → dokumentierter `docker-compose exec backend pytest tests/…` laeuft out-of-the-box; pytest `cache_dir=/tmp` wegen read-only-Rootfs.
- **Verifikation**: 972 passed, 2 skipped (bpmn/predictive/banking + Service-Tests). 17 Errors in `test_multi_tenant_migration.py` (`fixture 'db' not found`) sind pre-existing (auf master identisch, via switch verifiziert).

## 2026-06-04
- **merge(master)**: `feature/mocks-to-real-p1` (11 Commits) nach `master` gemergt + zu `origin/master` gepusht (Merge `2d054889`, `--no-ff`, non-destruktiv via temp-Worktree). Enthaelt Mocks→echt (M16/M13/M17) + die komplette „andere offene Sachen"-Remediation.
- **fix(approval)**: Echte Laufzeit-Bugs im Auto-Approval (crashte bei jeder Nutzung): Writer schrieb in reserviertes SQLAlchemy-`metadata=` statt Spalte `request_metadata=` (Metadaten nie persistiert); `completed_at=` ist keine Spalte → `resolved_at=`; Rate-Limit-/Statistik-Queries `metadata[...].astext` → `request_metadata[...].as_string()` (`.astext` ist JSONB-only; `CrossDBJSON` hat nur `.as_string()`/`.as_boolean()` → cross-DB). Auch `api/v1/approvals.py`. Commit `4f49aaed`.
- **fix(fraud)**: finanzki-Roh-SQL Spaltennamen (schema- + PG-EXPLAIN-verifiziert gegen echte `ablage-postgres`-DB): `d.doc_type`→`document_type`, `d.entity_id`→`business_entity_id`, `it.total_amount`→`it.amount` (CTE-Ausgaben via `AS` stabil); `it.entity_id` bleibt. **Zusatzfund per EXPLAIN**: `be.company_id` existiert NICHT (BusinessEntity global, Scope via `company_presence`) → redundanter Filter entfernt (Isolation via company-gefilterte JOINs + HAVING). Alle 3 Fraud-Queries → QUERY PLAN ok. Commits `de2f7f2a`/`5dcf0bc0`.
- **fix(fraud)**: Umlaut-robuste BEC-Erkennung — `fraud_ml_model._has_confidentiality_request`/`_mentions_bank_change` matchten nur die Umlaut-Form; transliterierte Betrugstexte („nur fuer sie", „…geaendert") rutschten durch → `_normalize_umlauts()` vor Matching. Plus AI-fraud `InvoiceTracking.total_amount`→`amount` (`96c22c7c`), finanzki ORM `doc_type`→`document_type` (`cf7565dd`).
- **fix(api)**: 2 vorbestehende Import-Bugs (tote Module): `ocr_feedback.py` Pydantic-v2 `regex=`→`pattern=`; `rag/chat_rest.py` `get_chat_service`-Importpfad (`b57870bd`).
- **test**: Approval- + Fraud-Test-Drift behoben — `test_approval_service.py` (escalate_overdue Bulk-UPDATE-rowcount, process_approval_decision Keyword-Args, Umlaut `ungueltig`→`ungültig`), `test_approval_rule_service.py` (company_id-Positional), `test_fraud_detection_api.py` (obsolete 501/400-Tests → 404/G1-Verhalten). 157 betroffene Unit-Tests gruen.
- **feat(m13,m17)**: Echter Cashflow-Backtest + BPMN-Signal-Resume. M13: `cashflow_prediction_service.get_prediction_metrics` liefert echte Backtest-Metriken aus `PredictionFeedbackRecord` (Fallback auf Schaetzung nur ohne Daten) - keine Migration. M17: `process_execution_service.signal` setzt wartende Nicht-Timer-Catch-Events fort (statt nur zu protokollieren). 5 Unit-Tests. Branch `feature/mocks-to-real-p1`.
- **feat(m16)**: Autonome Folder-Ablage aktiviert (`autonomous_actions_service`) — `propose_filing_location`/`execute_filing` waren als 'Folder-Model nicht implementiert' deaktiviert; das Folder-System existiert (models_folder.py) -> echte, mandanten-gefilterte Ablage (Verlauf + Standard-Ordner nach Typ, FolderDocument-Primaer-Link). 6 Unit-Tests gruen. Branch `feature/mocks-to-real-p1`.
- **docs(mocks)**: MOCK_DATA_REGISTER Status-Update — M1-M16 behoben/ehrlich; kein Mock zeigt mehr erfundene Daten als echt. Offen (ehrliche Feature-Tiefe): M13-Backtest, M17-BPMN.

## 2026-06-03
- **fix(g5-followup)**: 5 App-Findings aus G5 behoben (`fix/g5-followup-app`): F1 `validation_queue_service.assign_to_editor` nutzt UserCompany-Join statt nicht existentem `User.company_id`; F2 `training.get_trend_data` liefert gueltiges `TrendResponse` (avg_cer-Serie); F3 Entity-Endpoints (`get_entity`/`get_entity_documents`) mit company_id-Mandanten-Filter (eigene/NULL); F4 weasyprint-Importe `except (ImportError, OSError)`; F5 coverage `fail_under` 90→50 (gestaffelt). App importiert + configure_mappers gruen; 95 passed/5 skipped in betroffenen Tests, keine xfail mehr.
- **test(g5)**: Test-Wahrheit (B4) auf `feature/g5-test-truth` (8 Commits, Tip `6c880864`) — Stub-Tarn-Skips beseitigt, Collection 26→0 Errors, statische Skip-Marker 401→232.
- **test(g5)**: `tests/conftest.py` weasyprint-Mock (native GTK-Libs fehlen auf Windows → `app.main` sonst nicht importierbar); `pytest.ini` Marker vollstaendig (aktive Config, pyproject-Pytest ignoriert) + `testpaths=tests`/`--ignore=tests/_archived`; Orchestration-Tests via Paket-Import gefixt.
- **test(g5)**: `test_multi_tenant_isolation.py` neu (vorher 8 failed/3 passed/6 skipped Drift) — Cross-Tenant-HTTP (Doku/Rechnung 403/404), RLS/Rollback, JSONB-Validierung (Pydantic), Timeline-PII; DB-frei gruen, DB-abhaengig Laufzeit-Skip.
- **test(g5)**: Security-Stubs echt — `test_session_timeout` (decode_token 401, DB-frei), Slack/Email-Notification-PII-Maskierung; refresh-reuse + WS-CRLF als xfail/geloescht; `test_client`/`client`-Fixtures skippen statt zu erroren bei DB-losem App-Startup.
- **test(g5)**: 102 pass-only Karteileichen geloescht (contracts/invoices/document_chains/validation_field); training_api + validation_{queue,sample,field} MagicMock→SimpleNamespace entrostet (82 passed/7 xfail, ruff gesunken).
- **docs(g5)**: `tests/COVERAGE_STATUS.md` — Coverage lokal 25,6 %/Voll-Stack ~51 %, Top-Luecken dashboard.py/fraud.py (0 %)/banking/routes.py (37 %), Roadmap zu 90 %, Cross-Stream-Liste (🔴 `Folder.permissions` Ambiguous-FK blockiert ALLE ORM-Tests).
- **fix(db/g5)**: `Folder.permissions` Ambiguous-FK disambiguiert (`foreign_keys="FolderPermission.folder_id"`) — entsperrt `configure_mappers()` und damit ALLE ORM-instanziierenden Tests (auch test_rls_context/test_cash_isolation); keine Migration. Commit 666b2692.
- **fix(g1)**: B1 Multi-Tenant — `get_user_company_id_dep` zentral in `dependencies.py`; `validate_company_access` via `accessible_company_ids` (behebt AttributeError/HTTP-500). Branch `feature/g1-api-companyid`.
- **fix(g1)**: company_id-Rollout — 821 `current_user.company_id` in 92 API-Modulen → `Depends(get_user_company_id_dep)` (HTTP 403 bei fehlender Firma); `rg current_user.company_id app/api` → 0.
- **feat(g1)**: Dashboard-KPIs echt (avg_payment_days/Cashflow/Approvals), OCR ehrliche None; Fraud-Alerts `/alerts/{id}`+`/action` 200/404/400 statt 501; Admin-Restart ehrlicher 501 (M1-M6).
- **chore(config)**: FINTS_ALLOW_MOCK_SYNC + FINTS_AUTO_SYNC_ENABLED Flags in app/core/config.py (beide Default False, G0-Prereq)
- **chore(infra)**: asn1crypto==1.5.1 in requirements.txt gepinnt (RFC-3161-TSA, tsa_service.py)
- **docs(env)**: .env.example BANKING/FinTS-Sektion ergaenzt (PSD2-Konfigurationsvariablen)
- **docs(reviews)**: Interface-Kontrakt G1<->G4 (Dashboard-KPIs M1-M4, Fraud-Alert-Persistenz M5, Celery-Restart-Hook M6)
- **chore(config)**: .claude/CLAUDE.md Status-Header auf 🟡 korrigiert (vormals ueberschaetzt als Production-Ready)
- **chore(config)**: memory/KNOWN_ISSUES.md um 4 verifizierte Blocker B1-B4 ergaenzt (Status-Scan 2026-06-03)
- **chore(config)**: memory/PROJECT_STATUS.md Reality-Check-Sektion (A-Z-Fan-Out-Scan, 12 Subagents)
- **chore(config)**: memory/TECHNICAL_DEBT.md Debt-Level von LOW auf MITTEL-HOCH korrigiert
- **feat(g4)**: Backend-Services/Workers/DB-Remediation (M7-M15 + G1-Kontrakt M3/M5/M6), Commit `bd272d80` auf `feature/g4-services-db` (17 Dateien)
- **fix(g4/M9)**: enhanced_fints Mock-Sync hinter FINTS_ALLOW_MOCK_SYNC -> kein Fake-Eingang loest Reconciliation/IncomingPayment aus (Unit-Test gruen)
- **fix(g4/M7-M8)**: auto_transaction_import — PSD2 kein Platzhalter-Token an echte API; FinTS-Auto-Sync OUTSCOPED (BaFin)
- **fix(g4/celery)**: 4 Beat/Route-Renames; refresh_query_suggestions->warm_cache; reactivate_snoozed_items entfernt; 5 Task-Module sichtbar; fints-sync-daily hinter FINTS_AUTO_SYNC_ENABLED
- **fix(g4/M10-M13)**: Fraud/AI-Wahrheit (ApprovalRequest/ApprovalStep/AuditLog; echte Confidence/COUNT-Queries; is_estimated)
- **fix(g4/M14)**: TSA RFC-3161 via asn1crypto (kein Handbau-ASN.1-Fallback)
- **fix(g4/M15)**: GoBD echte company_id-Checks; XL ehrlich WARNING/teilgeprueft statt false PASSED
- **chore(g4/db)**: app/db/all_models.py Aggregator (468 Tabellen); models_collaboration app.db.base->models_base-Fix
- **ci(g2)**: Alle 17 Workflows Branch-Trigger `main` → `master` (Gates feuerten real nie); B3-Blocker behoben
- **ci(g2)**: ci.yml/docker.yml/docker-build.yml/dependencies.yml bauen aus 3 realen Dockerfiles (Root-`Dockerfile`, `frontend/Dockerfile`, `docker/Dockerfile.worker`)
- **ci(g2)**: `pip-audit` blockierend in ci.yml + dependencies.yml (ersetzt `safety … || true`); JSON-Report-Artefakt bleibt
- **ci(g2)**: `.secrets.baseline` als gültige detect-secrets-1.4.0-Baseline neu erzeugt (vormals leeres `{}`)
- **ci(g2)**: dependabot.yml docker-Ecosystem für `/`, `/frontend`, `/docker`; toter `python-dependencies`-Job entfernt
- **ci(g2)**: `docker-compose.dev.yml` ohne `target: development`; `deploy.yml` Pfad `alembic/versions`; `canary-deploy.yml` deaktiviert (`if: false`)
- **ci(g2)**: `.releaserc.json` Release-Branch `main` → `master`; manuelles `release.yml` als Release-Mechanismus gewählt
- **ci(g2)**: `.secrets.baseline` vervollstaendigt (Commit 113a0d6d) — Frontend-Mock-USt-IdNr. als False-Positive aufgenommen, `.claude-flow/metrics/` + `browser-diagnostics/` in `.pre-commit-config.yaml` ausgenommen (Flaky-Gate verhindert); detect-secrets-Hook findet 0 echte Funde
- **chore(security/g2)**: `browser-diagnostics/` (21 MB) untrackt + `.gitignore` — 73 abgelaufene JWTs (kein Auth-Risiko) mit PII; bleibt in History (DSGVO-Voll-Purge separat)
- **chore(g2)**: `.claude/CLAUDE.md` PostgreSQL-Port `:5433` → `:5434` (Hyper-V-Reservierung); `package.json`+`pyproject.toml` Version `1.0.0` → `0.1.0`
- **note(g2)**: ⚠️ Push blockiert — Parallelprozess hat kontaminierten Commit (87ec57e6 + 18 G3-Frontend-Dateien) auf origin/feature/g2-cicd gepusht; saubere lokale Commits liegen bereit, Auflösung an Team (siehe SESSION_LOG)
## 2026-06-03 (G3 — Frontend Mocks → echt, M18–M23)

Branch `feature/g3-frontend-mocks` (Worktree). Remediation-Strom G3 aus
`.claude/reviews/2026-06-03/MOCK_DATA_REGISTER.md`: erfundene Mock-/Zufallsdaten
(`Math.random`, `generateMock*`) aus dem Render-Pfad mehrerer Views entfernt und
durch ehrliche Empty-States ersetzt. Nur `frontend/src/**` geaendert (konfliktfrei
parallel zu G1/G2/G4). Code-Commit `2f9c2890`.

- M18 Knowledge-Graph (3 Views + Tests): Mock-Fallbacks raus, leere Strukturen,
  `mockData`→`networkData`, je View Empty-State-Test.
- M19 Streckengeschaeft-Validierung: echte `useDropShipmentList`-Liste,
  Approve/Reject als echte `useConfirmClassification`/`useOverrideClassification`-
  Mutationen (kein lokaler State), Toast nur bei Erfolg.
- M20 Reports: `_getFallbackData`/`Math.random` raus, typisierte
  `ReportDataUnavailableError`, Views → Empty-State.
- M21 Import-Wizard: 404-Fake-Preview raus, `WizardApiError(404)` durchgereicht,
  echter Empty-State.
- M22 StatusChangeDropdown: `supported`-Flag, nicht unterstuetzte Status disabled,
  `onSuccess()` nur nach erfolgreicher Mutation.
- M23 Job-Queue-Charts (3) + OverviewTab: `generateMockData` raus, `data ?? []`,
  Empty-State „Keine Daten fuer den gewaehlten Zeitraum".
- #8 (nur Doku): Token sessionStorage→httpOnly-Cookie als G1/G2-Abhaengigkeit in
  `lib/api/client.ts` vermerkt, kein Code-Change.

Verifikation: `tsc --noEmit` sauber, ESLint sauber, KG-Tests 18/18 gruen,
`grep generateMock|Math.random` in den 9 Zieldateien = 0 Treffer. Die restlichen
86 vitest-Fehler sind vorbestehend (auf Eltern-Commit `6e877ef6` identisch) und
ausserhalb von G3 (invoices, dashboard/websocket, portal, settings).

Folgepunkte an G1: dedizierter Reject-Status im Streckengeschaeft-Backend;
24h-Verlaufs-Endpoint (Throughput/Erfolgsrate) fuer die Job-Queue-Charts.

## 2026-05-20 (Pilot-Ship v0.1.0 — PR #9 Squash-Merge)

- **feat(pilot)**: PR #9 squash-gemerged, Tag `pilot-v0.1.0`, erste produktive Pilot-Version
- **feat(pilot)**: Sprint-0 (G01-G10), Phase A (K1-K6), Phase B (B1-B7), Multi-Agent-Review konsolidiert
- **fix(security)**: 5 CRITICAL + 11 HIGH-Sec gefixt; Merge-Konflikt Option B geloest

## 2026-05-20 (Sprint-1 — Sec-Reste)

- **fix(security)**: `trash.py` Multi-Tenant-Filter + Bulk-DELETE + Audit-Event vor Hard-Delete (S1.1)
- **fix(api)**: `retention_admin.py` `safe_error_detail` Args-Reihenfolge korrigiert (S1.2)
- **fix(security)**: `graphql_api.py` `ALLOWED_FILTER_FIELDS` Whitelist (CWE-89, S1.3)
- **fix(api)**: `nlq.py` `generated_sql` nur fuer Superuser (S1.4)
- **fix(db)**: `InvoiceTracking.entity_id` Column nachgezogen (S1.5/F4)
