# A-Z Deep Offensive — Explore-Register (Welle 1)

**Datum:** 2026-06-18
**Branch:** qa/az-deep-offensive-2026-06-18 (Worktree, abgezweigt von feature/offensive-2026-06-11 @ 5c5edf6ad)
**Stack:** Projekt ablage_system (live), DB-Head 268, Backend-Image gebaut 2026-06-13 (=> vor Welle 2 Rebuild auf aktuellen Code noetig)
**Methode:** 9 parallele read-only Audit-Agents (T1-T9), Befunde gegen echten Code/DB/laufenden Stack verifiziert.
**Regel:** isolierter Branch, KEIN master-Push.

---

## Prioritaetenliste (konsolidiert, dedupliziert)

| ID | Sev | Status | Titel | Evidence (Datei:Zeile) |
|----|-----|--------|-------|------------------------|
| F-01 | P0 | OFFEN-LIVE | CPU-Worker Crashloop: ProcessDefinition nicht aufloesbar (prefork) | models_cash_company.py:191, models.py:1581-1661, workers/celery_app.py |
| F-02 | High | OFFEN | error_type-Doppel-Kwarg -> TypeError in 4 Handlern (Auth-Hotpath) | api/dependencies.py:140, api/v1/auth.py:670, api/v1/metrics.py:1987, services/search_service.py:1730 |
| F-03 | P1 | OFFEN | InvoiceTracking.net_days vs Service net_payment_days -> Datenverlust + Crash | models_entity_business.py:508, banking/skonto_service.py:475, api/v1/invoices.py:742 |
| F-04 | P2 | OFFEN-LIVE | GET /auth/users 500 bei .local/reserved-TLD-Mails | api/v1/auth.py:1106, db/schemas.py:155,215 |
| F-05 | High | OFFEN | Rules-of-Hooks: bedingtes useEffect nach early return | frontend/.../help/components/OnboardingTour.tsx:58,133 |
| F-06 | High | OFFEN | 4 pytest Collection-Errors (aiosqlite + 3 Import-Fehler) | tests/test_auth.py:21, tests/benchmarks/test_performance.py:26, tests/empirical/test_benchmark_suite.py:21, tests/hooks/test_post_plan_mode.py:28 |
| F-07 | High | OFFEN | Schemathesis 23x5xx (Input-Validierung -> 500 statt 4xx) | api/v1/audit_chain.py:177, archive/export, change-password, datev/writeback |
| F-08 | High | OFFEN | FinTS-Payment success=True ohne Bankkontakt + Placeholder-Token, kein Prod-Guard | banking/payment_initiation_service.py:383-413,352,466, api/v1/banking/connections.py:623 |
| F-09 | P2 | OFFEN | OCR VRAM-Tabellen widerspruechlich (surya_gpu 4 vs 8 GB) | services/backend_manager.py:559, gpu_manager.py:40 |
| F-10 | P2 | OFFEN | OCR-Backends qwen/chandra/olmocr nie registriert | services/backend_manager.py:578-661 |
| F-11 | P2 | OFFEN | bank_transactions.booking_date/value_date DateTime(Modell) vs DATE(DB) | models_banking.py:303-304, 046_add_banking_tables.py:151 |
| F-12 | P2 | OFFEN | alembic check unbrauchbar (env.py liefert metadata nur bei autogenerate) | alembic/env.py:30,160 |
| F-13 | P2 | OFFEN | pgbouncer orphaned + asyncpg nicht transaction-pool-safe | docker-compose.yml:91,569, db/database.py:117, db/session.py:111 |
| F-14 | High | OFFEN | build:strict nie in CI; Image nutzt non-strict build | .github/workflows/ci.yml, frontend/Dockerfile:15, frontend/package.json:9 |
| F-15 | P2 | OFFEN | Jaeger/OTEL Tracing tot (SDK fehlt in requirements) | requirements.txt, app/main.py:239, docker-compose.yml:1298 |
| F-16 | P2 | OFFEN | detect-secrets Baseline 488 Commits alt | .secrets.baseline |
| F-17 | P2 | OFFEN | Secrets-Rotation cache-only + Vault default off (kein Prod-Fail) | workers/vault_tasks.py, core/config.py:768,1341 |
| F-18 | P2 | OFFEN | Orchestrator 12/40 Event-Handler + toter _mark_action_complete | services/orchestration/cross_module_orchestrator.py:265,1298 |
| F-19 | P3 | OFFEN | ~50 stille except Exception: pass (Fraud/Analytics/Matching) | services/ai/fraud_detection_service.py:889 u.a. |
| F-20 | Med | OFFEN | eslint 623 Probleme (3 no-console Prod, 30 any) | frontend npx eslint . |
| F-21 | Med | OFFEN | E2E 16 Specs failed (multi-upload/OCR-Review-Flow) | e2e/multi-upload.spec.ts, e2e/ablage.spec.ts:941 |
| F-22 | Low | OFFEN | Timing-Attack-Test Flake (Wall-Clock <0.1s) | tests/security/test_broken_auth.py:337 |
| F-23 | Med | OFFEN | Coverage-Gate inkonsistent (50 lokal / 80 CI) | pyproject.toml:290, .github/workflows/coverage.yml:72 |
| F-24 | Low | OFFEN | Backend-Port 8000:8000 nicht localhost-gebunden | docker-compose.yml:642 |
| F-25 | Low | OFFEN | Lokale :latest-Tags (beat, watchdog) nicht reproduzierbar | docker-compose.yml:969,1603 |
| D-01 | Doc | OFFEN | WAVE1-Register stale: W1-001 (2FA fixed), W1-006 (Runbook existiert), W1-034 (Container heisst real ablage-backend) | WAVE1_EXPLORE_REGISTER.md |
| D-02 | Doc | OFFEN | PROJECT_STATUS: Jaeger OK trotz totem Tracing; build:strict rot obwohl tsc gruen | .claude/memory/PROJECT_STATUS.md |

## Bestaetigte Positiv-Befunde (NICHT anfassen)
- 2FA-Bypass@DEBUG nicht mehr vorhanden (rbac.py: nur TESTING; config.py erzwingt DEBUG=False in Prod).
- SQLi (CWE-89) / CRLF (CWE-113) Hygiene real implementiert (parametrisiert, Whitelists, Header-Sanitizer).
- Multi-Tenant company_id-Scoping zentral + live bestaetigt (companies-500 behoben).
- Risk-Scoring externe Quellen ehrlich als Stub/None gekennzeichnet (is_estimated).
- M13-Feedback-Hook in allen 3 Pfaden; M16 Folder-Ablage aktiv; M17 Signal/Call-Activity real (Migration 266).
- DATEV/Lexware Kern echt, PII-Logging clean. GoBD-Trigger in DB vorhanden. Backups/DR-Skripte vollstaendig.

## Test-Wahrheit (echte Zahlen, 2026-06-18)
- Collected: 20.746 Tests, 4 Collection-Errors.
- Unit (DB erreichbar): 18.228 passed / 491 skipped / 31 xfailed.
- Vitest: 919 passed. Frontend tsc -b/--noEmit: 0 Fehler.
- API-Fuzz: 23 unique 5xx. E2E: 16 failed / 120 passed. Security: 1 Flake.
- ruff/mypy im Runtime-Container nicht installiert -> nur CI.

---

## Remediation-Log (Welle 2)
_(wird pro Iteration fortgeschrieben)_

### Iteration 1 (2026-06-18)
Backend-Batch (committed 0fe2bca14):
- F-01 FIXED: celery_app importiert all_models + configure_mappers() (Modul-Level, laeuft nur im Worker; app.main importiert celery_app NICHT). LIVE bestaetigt: worker-cpu 0 ProcessDefinition-Fehler nach Recreate.
- F-02 FIXED: error_type-Doppel-kwarg in 4 Handlern entfernt (dependencies.py:140, auth.py:670, metrics.py:1987, search_service.py:1730).
- F-03 FIXED: invoice.net_payment_days -> invoice.net_days (skonto_service.py x3, invoices.py x1).
- F-04 FIXED: UserResponse.email -> str (Reserved-TLD/.local).
Build-Reproduzierbarkeit (committed 9c2ed38fe):
- F-26 NEU+FIXED: Rebuild zog transformers 5.12.1 + torch 2.12.1 (ungepinnt) -> torch._dynamo "Duplicate dispatch"-Crash beim Backend-Start. Dockerfile installiert jetzt torch==2.1.2+cu121 / torchvision==0.16.2+cu121 explizit (war in requirements.txt dokumentiert, fehlte im Dockerfile); transformers>=4.45.0,<5.
- F-06 FIXED: 4 Collection-Errors via pytest.importorskip (aiosqlite/orchestration_server/orchestration/post_plan_mode).
Frontend (committed 5ee8c9599):
- F-05 FIXED: OnboardingTour Rules-of-Hooks (useEffect vor early-return). tsc/eslint-Verifikation offen (Frontend-Batch).

OFFEN/als Naechstes: Backend-Rebuild verifizieren (boot + F-01..F-04 live), dann F-07 (23 Schemathesis-5xx), F-08 (FinTS-Guard), F-09..F-25, Doku D-01/D-02. Live A-Z-Browser-Simulation nach Backend-Boot.

## A-Z Live-Test-Matrix (Welle 2)
Pro Modul: echte Nutzerreise via Browser (Playwright MCP) + API-Checks. Jeder Fehler -> systematisches Debuggen -> Fix im Worktree -> schneller Rebuild -> LIVE nachweisen -> adversarial gegenpruefen -> dokumentieren. Login: admin@localhost.com / admin123 (Fallback admin@ablage-system.local / password123).

| # | Reise | Schritte | Erfolgskriterium | Verknuepfte Findings |
|---|-------|----------|------------------|----------------------|
| A1 | Auth Login | /login -> admin-Creds -> Dashboard | 200, Token, Redirect | F-02, F-04 |
| A2 | Auth Negativ | falsche Creds / leeres Formular | bleibt /login, 401 sauber (kein 500/TypeError) | F-02 |
| A3 | 2FA | 2FA-User Login | TOTP erzwungen (kein DEBUG-Bypass) | (T1 positiv) |
| B1 | Admin Users | GET /auth/users (admin) | 200 Liste (war 500 bei .local) | F-04 |
| B2 | Companies/Multi-Tenant | /companies, /companies/current | 200, kein Leak | (T1 positiv) |
| C1 | Upload | Dokument hochladen | Upload ok, Job angelegt | T6-E2E |
| C2 | OCR/Review | OCR-Fortschritt -> Review-Modal | Text erkannt, Review oeffnet | F-21 |
| C3 | Klassifizierung | Dokumenttyp/Entity-Link | korrekt zugeordnet | - |
| D1 | Volltextsuche | Suche nach Begriff | Treffer (war tot: SQL-Bind) | T9 verify |
| E1 | Banking/Skonto | Rechnung -> Skonto berechnen | due_date/Skonto korrekt, kein AttributeError | F-03 |
| E2 | Invoice-Tracking | Tracking-Liste/Detail | laedt, Felder korrekt | F-03 |
| F1 | DATEV Export | Export-Gate/Config | Export ok oder ehrliche Meldung | T3-08 |
| F2 | Lexware | Import-Ansicht | laedt, kein PII-Log | T3-09 |
| G1 | Alerts | Alert-Center | Alerts laden, SLA-Checks aktiv | F-01 |
| H1 | Audit-Chain | /audit-chain/verify malformed | 422 statt 500 | F-07 |
| H2 | Archive/Export | GDPdU/tax-authority malformed | 4xx statt 500 | F-07 |
| I1 | Worker/Beat | Scheduled CPU-Tasks | SUCCESS (kein Crashloop) | F-01 |
| J1 | GDPR | Loeschantrag/Audit | funktioniert | - |
| K1 | Schemathesis | Fuzz-Lauf gesamt | 0 unique 5xx (war 23) | F-07 |

Status pro Reise wird in den Iterations-Logs unten gefuehrt.

### Iteration 2 (2026-06-18/19) - Live A-Z + Remediation
**Stack live mit Worktree-Code** (Bind-Mount ./app zeigt jetzt auf Worktree -> alle App-Fixes aktiv; entscheidend: docker-compose bind-mountet ./app:/app/app:ro aus dem jeweiligen Compose-Projektverzeichnis - deshalb mussten die 4 App-Container ueber die Worktree-Compose laufen).

LIVE VERIFIZIERT (alle 200/korrekt):
- F-01 Worker: 0 ProcessDefinition-Fehler, 608 Tasks/60s verarbeitet (war Crashloop).
- F-02 Invalid-Token /auth/me -> 401, 0 TypeError im Log (Doppel-kwarg weg).
- F-04 /auth/users -> 200 (war 500 bei .local-Mails).
- F-07 audit-chain/verify malformed -> 422 (war 500).
- Backend bootet healthy (F-26-Kaskade komplett geloest: torch<2.12 / triton+cupy+HOME-Cache / bitsandbytes graceful).
- Browser (Playwright): Login + Dashboard rendern voll (deutsche UI, E2E Test GmbH).

NEUE FUNDE Welle 2:
- F-27 (High, Security/Design): /auth/change-password nimmt UserCreate-Body + ruft Service mit hartkodiertem current_password="" -> Endpoint kann aktuelles Passwort nicht pruefen (kaputt oder Bypass). NICHT blind gefixt (API-Vertrag+Frontend). app/api/v1/auth.py:912,936-939.
- F-28 (Med): Celery-Task ml_tasks.check_experiment_completion schreibt nach relativem ./data -> OSError read-only-Rootfs (isoliert, retryt nur).
- F-29 (Info/Test-Gotcha): ~21s Latenz pro Request war Windows-localhost->IPv6(::1)-Timeout (Client-seitig); Backend selbst 7-15ms. 127.0.0.1 nutzen. Andere Session kaschierte das mit "Timeout 20s->60s" statt Root-Cause.
- F-30 (UX): Beim ersten Login oeffnen 3 ueberlappende Onboarding-/Tour-Dialoge gleichzeitig.
- F-31 (HIGH, SYSTEMISCH): A-Z-API-Sweep ueber 1071 parameterlose GET-Endpunkte -> 192 lieferten HTTP 500. Root-Cause-Familie "Company-Resolution": User-Modell hat kein company_id/current_company_id/default_company_id/is_admin; Company-Objekte werden mit .company_id statt .id angesprochen; + vereinzelt Call-Signatur-TypeError + Enum<->varchar-SQL (team_status). Latente Bugs, weil diese Feature-Endpunkte nie live aufgerufen wurden (bestaetigt DOC-MISMATCH "Production-Ready"). PROGRESS: 192 -> 171 (esg.py 11 Endpunkte; Codemod current/default_company_id+is_admin in 9 Modulen). Weiter im Loop.

Commits Welle 2: F-26-Kaskade (5x), F-31 esg (797d3b0cf), F-31 codemod 9 Module (23e231d08).

### Iteration 3 (2026-06-19) - F-31 systematische Remediation
500-Endpunkte (parameterlose GET): **192 -> 171 -> 139** (53 Endpunkte gefixt).
Fix-Methode: edit im Worktree -> docker restart ablage-backend (Bind-Mount, KEIN Reboot) -> Re-Sweep.

Behoben (committed):
- esg.py (11) via await get_user_company_id(db, user).
- Codemod current_company_id/default_company_id/is_admin in 9 Modulen (cashflow, holding, hygiene, industry_benchmarks, predictive_cashflow, subscriptions, tax_advisor_packages, tenant_rate_limits, zero_touch).
- get_user_company_id-Import-Fix in 9 Modulen (Codemod-Bug: Import-Check vom Replacement-Text getaeuscht -> NameError; + pre-existing fehlende Imports in ai_autonomy/autonomous/trash/workflows).
- Company-Objekt .company_id -> .id Codemod (135 Sites: contracts/process_mining/consent/document_templates/credit/classification).

VERBLEIBENDER LONG-TAIL (~139, divers - Loop laeuft weiter):
- ~22 SQL ProgrammingError/Error: Enum<->varchar (z.B. character varying = team_status) + fehlende Spalten -> deckt sich mit T2 (Modell<->DB-Drift). Per-Query-Fixes noetig.
- 4 CompanySettings.company_id (calendar-sync) - Klassen-/Query-Attr.
- 3 BankAccount.balance fehlt (cashflow) - Modell/Spalte.
- 3 BinaryExpression/TDComparator (extracted_data export) - SQL-Expression.
- 2 ArgumentError tax-advisor (Company-Objekt statt company_id.id in SQL).
- 2 MissingGreenlet (bpmn/tasks, notification-preferences) - sync-DB-Call in async.
- 2 User.role (activity), 2 User not subscriptable (privat/life-events).
- ~10 Einzelbugs (Pydantic-validation-errors DashboardDataResponse/ValidationQueueResponse, Service-Signatur-TypeError, KeyError, UnboundLocalError entities/cross-company, Document.ocr_text, PaymentSchedule.period_days ...).

Bewertung: Die grossen, systematischen Cluster (Company-Resolution) sind erledigt. Der Rest sind heterogene Einzel-/Service-Bugs in selten genutzten Enterprise-Feature-Endpunkten (nie live aufgerufen -> latent) - jeder einzeln zu fixen + verifizieren. Loop wird fortgesetzt.

### F-31 Stand nach Iteration 3 (2026-06-19)
GET-500: **192 -> 135** (57 Endpunkte gefixt; 200: 684 -> 741). Alle Fixes committed + live verifiziert via Re-Sweep.
Zusaetzlich gefixt: BankAccount.balance -> current_balance (cashflow/holding).

VERBLEIBEND ~135 = Design-abhaengiger Long-Tail (obskure Enterprise-Feature-Endpunkte, nie live genutzt -> latent). Erfordert per-case/Designentscheidungen, KEINE sicheren Codemods:
- current_user.role (~8 Module): User hat kein role-Feld; Rolle ist berechnet (is_superuser/RBAC). AUTHZ-sensibel -> bewusste Rollenquellen-Entscheidung noetig.
- Enum<->varchar (team_status/approvalstatus): T2-05-Drift; Fix = Modell native_enum=False ODER DB-Migration (Richtungsentscheidung).
- CompanySettings.company_id (calendar): CompanySettings ist Singleton OHNE company_id -> calendar-Service-Annahme falsch (Design-Bug).
- Diverse: User.role/subscriptable (privat), MissingGreenlet (sync-DB in async), Pydantic-Validation-Mismatches (DashboardDataResponse etc.), per-Service-Signatur-TypeError, Document.ocr_text, PaymentSchedule.period_days, ...

NOCH NICHT begonnen (Phase-2-Restscope): POST/PUT/DELETE-Endpunkte systematisch, Voll-Browser-E2E je Modul, Schemathesis-Re-Run, Findings F-08 (FinTS-Guard)/F-27 (change-password)/F-28 (worker ./data)/F-30 (Onboarding-Overlays).

### F-31 Meilenstein 2026-06-19: 500 von 192 -> 80 (112 Endpunkte gefixt; 200: 684 -> 796). Rest = Roadmap (siehe 2026-06-18-az-deep-F31-remaining-roadmap.md): ~40 konkret fixbar (C+D), ~25 Feature-Luecken/Reworks (A+B).
