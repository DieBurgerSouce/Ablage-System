# MASTER REVIEW — Ablage-System

**Datum:** 2026-05-19
**Branch:** `sprint-0-pilot-hardening`
**Scope:** 6 parallele Spezial-Reviews (Security, Code-Quality, Tests, Frontend, Infra, Docs)
**Codebase:** 257 API-Module, ~235 Services, 1556 .tsx, 261 Alembic-Migrationen, 17 GitHub-Workflows, ~22 Docker-Services

## Executive Summary

Das System ist **fundamental gesund** (gut gehärteter Docker-Stack, Sentry/Loki/Jaeger live, 50+ Multi-Tenant-Bugs in den letzten Monaten gefixt) **aber nicht pilot-ship-ready**. Sechs unabhängige Reviews identifizieren konvergent **5 kritische Blocker** (Migration-Drift, Deploy-Gate, 2 AuthZ-Bugs, 1 Import-Bug) und systemische Drift in Frontend-Code-Discipline (71 `console.*`, 305 `as any`, 0% i18n), Pydantic-Modernisierung (84 v1-Reste), Test-Coverage (71% API-Module ungetestet) und Docs (Formatter zerstörte 20 Dateien, 343 Zeilen Content in ANALYSIS_*.md verloren).

**Empfehlung:** 1 Tag Bug-Fix-Sprint (Blocker), 1 Woche Discipline-Sprint (Logger/Types/Tests), dann Pilot-Release-Window öffnen.

---

## Severity Matrix

| Severity | Security | Quality | Tests | Frontend | Infra | Docs | TOTAL |
|----------|----------|---------|-------|----------|-------|------|-------|
| 🔴 **Kritisch** | 4 | 0 | 0 | 0 | 2 | 0 | **6** |
| 🟠 **Hoch** | 8 | 4 | 23 | 4 | 3 | 0 | **42** |
| 🟡 **Mittel** | 8 | 8 | 5 | 3 | 4 | 17 | **45** |
| 🟢 **Niedrig** | 7 | 6 | — | 5 | 2 | 5 | **25** |

---

## 🔴 Kritische Blocker (vor Pilot-Ship)

| # | Finding | Bereich | Datei:Zeile | Fix-Aufwand |
|---|---------|---------|-------------|-------------|
| **K1** | **20 Alembic-Heads** — `alembic upgrade head` schlägt mit "Multiple head revisions" fehl; `deploy.yml:120` läuft das ungeschützt. Heads: 014, 021, 054, 066, 074, 089, 100, 111, 115, 137, 147, 151, 203, 208, 211, 213, 261, streckengeschaeft_002/003/004. | Infra | `alembic/versions/` | 2-4h (Merge-Revisions) |
| **K2** | **`deploy.yml` ohne Test-Gate** — keine `workflow_run`-Abhängigkeit auf `ci.yml`; `pre-deploy-checks` ist ein leerer `# TODO`-Stub. Einziges Gate: GitHub-Environment-Approval. | Infra | `.github/workflows/deploy.yml:71` | 1h |
| **K3** | **`privat.py:29` ImportError** — `from app.core.security import build_content_disposition`, aber die Funktion ist in `security_auth.py:1106` definiert. Ladefehler → **kompletter Privat-Router unverfügbar** oder Runtime-AttributeError bei PDF/iCal-Exports. | Security | `app/api/v1/privat.py:29` | 5min |
| **K4** | **`dpia.py` Multi-Tenant-Bypass** — `service.get_by_id()` lädt ohne `company_id`-WHERE, prüft erst in Python; bei `dpia.company_id IS NULL` (Legacy-Rows) lässt `if dpia.company_id and ...`-Shortcircuit Zugriff durch. Gleicher Pattern in `update_status`, `add_dpo_consultation`, `get_recommendations`, `get_audit_trail`. | Security | `app/api/v1/dpia.py:294-424` | 30min |
| **K5** | **`notification_rules.py:493` DoS** — `POST /test` akzeptiert beliebige `conditions`/`event_data`-JSON ohne Size/Depth/Operator-Limits, ohne Rate-Limit. Deeply nested oder Regex-Operator → Worker-DoS. | Security | `app/api/v1/notification_rules.py:493-513` | 15min |
| **K6** | **`event_sourcing.py` keine Whitelist** — `aggregate_type`-Pfadparameter ohne Validierung an `EventStore.get_events`. Injection-Vektor + IDOR-Enumeration-Vektor. | Security | `app/api/v1/event_sourcing.py:93-211` | 20min |

**Sofortmaßnahme:** Diese 6 Blocker = ein halber Arbeitstag. Reihenfolge K3 → K4 → K5 → K6 → K2 → K1.

---

## 🟠 Hoch-Priorität

### Backend Security (4)
- **`trash.py:244-360`** — DELETE-Endpoints filtern nur `owner_id`, nicht `company_id`. User nach Company-Wechsel kann fremde Dokumente hart löschen. Plus N+1 `await db.delete(doc)` in Schleife.
- **`retention_admin.py:164,263,366`** — `safe_error_detail(<str>, e)` Argumente vertauscht (Signatur ist `(e, context)`). PII-Schutz greift nicht.
- **`graphql_api.py:266-301`** — `_apply_filters` ohne Allow-List → beliebige Spalten (auch `iban`, `vat_id`, `password_hash`) als Filter nutzbar → Field-Oracle-Attacks.
- **`nlq.py:80-143`** — Kein Rate-Limit auf NLQ-Endpoints; `generated_sql` wird zurückgegeben (Injection-Iteration ermöglicht).

### Frontend Discipline (4)
- **71 `console.*` in Production-Code** — leakt Document-IDs, Template-Inhalte, AI-Action-Params. **Rule 1 verletzt.**
- **305 `as any` Casts** — Rule 4 verletzt. Top-Offender: `RuleTestingPanel.tsx`, `DataQualityDashboard.tsx`, `CreateDashboard.tsx`.
- **5 Mutation-Hooks ohne `invalidateQueries`** → stale UI: `use-duplicate-check.ts`, `use-elster-queries.ts`, audit-api, dunning-templates, audit-chain-api.
- **`key={index}` in dynamischen Listen** (10+ Stellen, nicht nur Skeletons): `FraudAlertsTable.tsx:143`, `ImportWizard.tsx:519`, `ClassificationDetail.tsx:549`.

### Test Coverage (5 absolute Prio-Lücken)
- **`mfa.py`** ungetestet — Account-Takeover-Risiko
- **`encryption.py`** ungetestet — GDPR Art. 32
- **`dpia.py` / `dlp.py` / `consent.py`** ungetestet — GDPR Art. 7/35
- **`retention_admin.py`** ungetestet — GoBD 10-Jahre + GDPR-Löschung
- **`audit_chain.py`** ungetestet — Tamper-Evidence kann silent brechen
- (+12 weitere High-Risk-Endpoints, siehe `test_gaps.md`)

### Infra (3)
- **GPU-Thermal-Alerts deaktiviert** trotz laufendem dcgm-exporter (`ocr-alerts.yml:210-252`, 4 Rules). Sicherheitslücke auf einem GPU-only-OCR-System.
- **15+ mutable Action-Refs** in Workflows (`@v3`, `@v4` ohne SHA), `edoburu/pgbouncer:latest` in prod-compose, `:latest` für minio/ollama/grafana/prometheus in airgap-compose.
- **Backend-Quality `class Config:` × 73** in 33 API-Files + 11 `@validator` (Pydantic v1) — bricht auf v3.

---

## 🟡 Mittel-Priorität

| Bereich | Finding | Aufwand |
|---------|---------|---------|
| Quality | **86 `Dict[str, Any]`** in 20 Services (Rule 4); Worst: `backend_manager.py:17`. Lösung: TypedDicts pro Service. | 2-3 Tage |
| Quality | **`cash_flow_service._get_payment_probability:525`** — ignoriert Parameter, return-default. Cashflow-Forecasts uniform falsch. | 1 Tag |
| Quality | **`BaseInsightGenerator` / `BaseAction`** raisen `NotImplementedError` ohne `@abstractmethod`. | 30min |
| Quality | **`einvoice/generator_service._create_simple_pdf`** — IST implementiert (Spec war veraltet), aber überschreibt **immer** Customer-PDFs statt Pass-Through. | 1h |
| Frontend | **i18n-Infrastruktur unbenutzt** (`lib/i18n/` + `de.json`/`en.json` existieren, 0 `.tsx` nutzen `useTranslation`). Entscheidung: droppen oder migrieren. | Entscheidung + ~Wochen |
| Frontend | **10 Komponenten >900 LOC** (`ValidationQueueDashboard.tsx` 1516, `GlobalAIAssistantV2.tsx` 1147, `BudgetDashboard.tsx` 1063, …). | iterativ |
| Tests | **`tests/integration/` fehlt** Upload→OCR→Search-Pipeline, vollständige GDPR-Art-17-Kaskade, Cross-Tenant-Attack-Matrix. | 2-3 Tage |
| Tests | **8 frisch committete Tests** decken Happy-Path gut, **fehlen Adversarial**: Injection, Oversize, Concurrency, GPU-OOM, German-Edge-Cases (Fraktur, Eigennamen). | 1-2 Tage |
| Infra | **`docker-compose.airgap.yml`** mit `:latest` für minio/ollama/grafana/prometheus — inkompatibel mit Offline-Reproduzierbarkeit. | 1h |
| Infra | **Backup-Encryption-Alert deaktiviert**, Feature ungebaut (Sprint-0 G06). Entweder fertig bauen oder Metric entfernen. | 0.5-2 Tage |
| Infra | **Postgres-Entrypoint** kopiert SSL-Certs bei jedem Start (`/tmp/ssl/`→`/var/lib/postgresql/`), schlägt silent fehl wenn Certs fehlen. | 1h |
| Docs | **20 Doc-Dateien Formatter-Schaden** (Tabellen flachgelegt, HTML-Entities escaped, stray ```-Fences, `<http://documents.py>` Auto-Link-Korruption). | 2-3h revert + Config-Fix |
| Docs | **343 Zeilen Content verloren** in ANALYSIS_DETAILED_FINDINGS.md (−185), ANALYSIS_ENTERPRISE_ROADMAP.md (−77), ANALYSIS_EXECUTIVE_SUMMARY.md (−81). Full revert nötig. | 30min |
| Security | **Rate-Limiting fehlt** auf 12 von 14 reviewten Routern (nlq, dlp, audit_chain, event_sourcing, graphql, trash, dpia, ai_decisions, compliance_autopilot, notification_rules, smart_escalation, supplier_verification). | 2-3h (Router-Decorator) |
| Security | **`notification_rules.py:317`** IDOR-Pattern: `db.get(NotificationRule, rule_id)` ohne `user_id`-Filter, nur Post-Fetch-Check. Gleicher Pattern in `update/delete/toggle/statistics`. | 30min |

---

## 🟢 Niedrig-Priorität / Tech-Debt

- **22 Services >1500 LOC** Refactor-Kandidaten (`streckengeschaeft/__init__.py` 2189 = Anti-Pattern; `notification_service` 1551 + `notification/unified_hub` 1549 = 3100 LOC Duplikat-Konzept).
- **40+ `except Exception: pass`** in Services — meiste legitim, ~10 problematisch (`access_analytics_service:841,862`, `auto_filing_service:317`, `trust_level_service:366,593,604`).
- **Accessibility schwach** — nur 15 `aria-label`-Vorkommen im ganzen Frontend, ~30 `<img>` ohne `alt` zu prüfen, WCAG 2.1 AA-Risiko.
- **Stale Docs**: `ANALYSIS_*.md` (2025-12-31, "92-95% Production-Ready") inzwischen 5 Monate alt; `docs/INFRASTRUCTURE_STATUS.md` (2026-01-05) zeigt 19 Container, Realität 21.
- **RAG-Plan-Drift**: PlanRAGAblage.md v1.0.0 vs ~85% implementiert. Drei echte Lücken: PDF-Report-Generator (Excel + Word sind da), Beat-Schedule für Customer-Card-Sync, nie validierte Perf-Benchmarks (<500ms search, <15s 8B-LLM, <60s 14B-LLM).
- **`dlp.py:344`** ReDoS-Risiko (kein Timeout auf Regex über 100k Char Text).

---

## Vorgeschlagener Sprint-1 Backlog (nach Pilot-Hardening)

### Phase A — Blocker beheben (0.5 Tage)
1. K3: `privat.py:29` Import-Fix → Smoke-Test
2. K4: `dpia.py` company_id-Filter (5 Endpoints)
3. K5: `notification_rules.py /test` Size+Operator+RateLimit
4. K6: `event_sourcing.py` aggregate_type Whitelist
5. K2: `deploy.yml` mit `workflow_run: workflows: [CI]` + `conclusion == success` gaten
6. K1: Alembic-Heads mergen (oder Branches dokumentieren) + CI-Gate `alembic heads | wc -l == 1`

### Phase B — Discipline-Sweep (3-5 Tage)
7. **Rate-Limiting-Decorator** auf 12 ungeschützte Router (60/min default, tighter für NLQ/Audit/Supplier)
8. **Frontend Logger-Sweep**: 71 `console.*` → `lib/logger.ts` + ESLint-`no-console`
9. **Pydantic-v2-Codemod**: 73 `class Config:` + 11 `@validator` + 1 `.dict()` (skript-bar)
10. **Doc-Revert**: 20 formatter-zerstörte Dateien (`git checkout`), 4 intent-tragende sauber committen, `.prettierignore` fixen
11. **Test-Top-5**: `test_mfa_api.py`, `test_encryption_api.py`, `test_gdpr_deletion_e2e.py` (integration), `test_payment_service.py`, `test_document_ingestion_pipeline.py` (integration)
12. **GPU-Thermal-Alerts** wieder aktivieren (`ocr-alerts.yml:210-252`)
13. **Mutable Tags pinnen** (15+ Actions + `edoburu/pgbouncer:latest` + airgap-`:latest`)

### Phase C — Type-Safety + Refactor (1-2 Wochen, iterativ)
14. `as any` Budget: 305 → 0 in 3 Sprints (50% pro Sprint)
15. `Dict[str, Any]` → TypedDicts in 20 Top-Services
16. Mutation-Hooks: `invalidateQueries` in den 5 betroffenen Files
17. `cash_flow_service._get_payment_probability` echte ML-Implementation
18. Top-5 große Files >1500 LOC splitten (streckengeschaeft/__init__, tax_optimization, finance_assistant, backup, quick_classification)
19. i18n-Entscheidung: droppen oder Migration starten (high-traffic Routes zuerst)

### Phase D — Test-Edge-Cases + Integration (parallel, 1 Woche)
20. EdgeCases-Klasse pro 8 frische Tests (Injection, Oversize, Concurrency, GPU-OOM, German-Edges)
21. Restliche kritische API-Tests: `dpia`, `dlp`, `consent`, `audit_chain`, `retention_admin`, `cross_tenant_reports`
22. Cross-Tenant-Attack-Matrix als Integration-Test

### Phase E — RAG-Spec abschließen (3-5 Tage)
23. PDF-Report-Generator (`pdf_generator.py`)
24. Customer-Card Beat-Schedule registrieren
25. Performance-Benchmarks gegen v1.0.0-Targets messen, dokumentieren
26. `PlanRAGAblage.md` auf v1.1 mit Implementation-Status-Appendix

---

## Antworten auf die Fragen

**Wo stehen wir?** Sprint-0 Pilot-Hardening läuft sauber (Alerting-Spam gefixt, Sentry aktiviert). Die "Feinpoliert"-Roadmap (Step 0-9) ist komplett, 654+121 = 775 neue Tests in 2 Monaten. Infrastruktur ist eine der disziplinierteren On-Prem-Setups (no-new-privileges, Read-only-FS, Localhost-Binding, Secret-Mandatory). Backend ist 95% Production-Ready laut alter Analyse — durch den heutigen Review reduziert auf realistisch **~92%**.

**Was ist noch offen?** 6 kritische Blocker (s.o., ein halber Tag), dann die Discipline-Phase (Logger, Pydantic-v2, Doc-Revert, Top-5-Tests). Plus 17 Mittel-Prio-Items. RAG-Layer fehlen 3 konkrete Stücke (PDF-Gen, Beat, Benchmarks). Sprint-0-Hardening-Items: BackupEncryption (G06), GPU-Thermal-Alerts reaktivieren.

**Wo sind Fehler und Bugs?** Konkret reproduzierbar: `privat.py:29` Import → Router lädt evtl. nicht; `dpia.py` lässt bei Legacy-NULL-Rows Cross-Tenant-Zugriff durch; `notification_rules.py /test` DoS-bar; `event_sourcing.py` Injection-Vektor; `cash_flow_service._get_payment_probability` liefert immer Default → alle Forecasts falsch; `retention_admin.py` `safe_error_detail` Args vertauscht → PII-Schutz bricht; `trash.py` löscht ohne company_id; 71 `console.*` in Frontend leaken Document-IDs/Template-Inhalte.

**Was können wir noch machen?** Phase C–E aus dem Backlog: Type-Safety-Cleanup, große File-Splits, i18n-Migration (oder Drop), RAG-Spec abschließen, Cross-Tenant-Attack-Matrix als Integration-Test, WCAG 2.1 AA-Sweep, Performance-Benchmarks.

**Was ist als Nächstes dran?** **Phase A (heute/morgen)**: 6 kritische Blocker. Danach **Phase B (diese Woche)**: Discipline-Sweep. Mein Vorschlag: ich starte Phase A direkt, sobald du grünes Licht gibst. Phase B können wir entweder seriell oder mit parallelem Coder-Swarm (3-5 Background-Agents pro Item-Cluster) angehen.

---

## Reports (Detailansicht)

- 🔐 `backend_security.md` — 27 Findings über 14 ungetestete kritische Endpoints
- 🧹 `backend_quality.md` — Pydantic-v1-Inventur, Stubs, 22 Refactor-Kandidaten
- 🧪 `test_gaps.md` — 183 ungetestete API-Module, 117 ungetestete Services, 5 Integration-Lücken
- 🎨 `frontend_review.md` — Console/Any/i18n/Keys/Größe-Inventur über 1556 .tsx
- 🐳 `infra_ops.md` — Container, CI/CD, Monitoring, 261 Migrationen, Sentry/Loki/Jaeger
- 📚 `doc_drift.md` — 22 uncommitted Docs analysiert, RAG-Spec-vs-Code-Gap
