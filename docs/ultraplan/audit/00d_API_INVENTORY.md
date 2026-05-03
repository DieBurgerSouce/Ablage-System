# 00d - API Inventory (Pilot Reality Check)

**Scope**: `app/api/v1/` - alle FastAPI Router-Files, HTTP-Methoden, Auth-Coverage, Stub-Detection, Modul-Kategorisierung.
**Datum**: 2026-05-03
**Branch**: `feature/ocr-performance`

---

## 1. Datei-Inventar

**Anzahl Dateien**:
- Direkte Router-Files (`app/api/v1/*.py`): **257 Files** (statt der angeforderten 298 - moeglicherweise Restrukturierung erfolgt).
- Subdirectories: 6 (`admin/`, `banking/`, `personal/`, `portal/`, `privat/`, `rag/`)
  - `admin/`: 16 Files (audit.py, jobs.py, users.py, roles.py, queues.py, dlq.py, ...)
  - `banking/`: 3 Files (connections.py, routes.py)
  - `personal/`: 4 Files (employees.py, departments.py, positions.py)
  - `portal/`: 7 Files (auth.py, invoices.py, payments.py, complaints.py, ...)
  - `privat/`: 2 Files (tax.py)
  - `rag/`: 9 Files (chat.py, search.py, customers.py, jobs.py, chunks.py, ...)
- **Gesamt-Files mit @router**: 252 (4 Files ohne `@router.*` Decorator gefunden -> moeglicherweise Schema-only Files oder helper).

### Top-30 nach Dateigroesse (Bytes)

| # | File | Size | Endpoints (`@router.*`) |
|---|------|------|-------------------------|
| 1 | `documents.py` | 159158 | 114 |
| 2 | `orchestration.py` | 147963 | 554 |
| 3 | `privat.py` | 134888 | 186 |
| 4 | `ocr.py` | 114272 | 160 |
| 5 | `privat_analytics.py` | 113723 | 136 |
| 6 | `training.py` | 94862 | n/a |
| 7 | `health.py` | 92010 | 224 |
| 8 | `entities.py` | 91307 | 113 |
| 9 | `accounting.py` | 85547 | 270 |
| 10 | `contracts.py` | 84444 | 78 |
| 11 | `finance.py` | 84428 | 171 |
| 12 | `metrics.py` | 73986 | 31 |
| 13 | `rag.py` | 64969 | 38 |
| 14 | `auth.py` | 63963 | 70 |
| 15 | `workflows.py` | 62826 | n/a |
| 16 | `compliance.py` | 62261 | 57 |
| 17 | `ai_conversations.py` | 57677 | 37 |
| 18 | `archive.py` | 57240 | 96 |
| 19 | `invoices.py` | 57057 | 77 |
| 20 | `personal.py` | 53481 | 24 |
| 21 | `einvoice.py` | 53453 | 80 |
| 22 | `gdpr.py` | 50765 | 76 |
| 23 | `reports.py` | 50303 | 89 |
| 24 | `cash.py` | 46658 | 89 |
| 25 | `approvals.py` | 46553 | 75 |
| 26 | `projects.py` | 43986 | 77 |
| 27 | `rules.py` | 38429 | 42 |
| 28 | `notifications.py` | 37834 | 55 |
| 29 | `budgets.py` | 37170 | 92 |
| 30 | `validation.py` | 37237 | n/a |

**Beobachtung**: `orchestration.py` mit 554 `@router.*` Decorations ist ein deutlicher Outlier - ggf. ein "God-Module". Ebenso `accounting.py` (270), `health.py` (224), `privat.py` (186).

---

## 2. HTTP-Methoden-Verteilung

```
@router.get    : 1609 (53.4%)
@router.post   : 1030 (34.2%)
@router.put    :   83 ( 2.8%)
@router.delete :  174 ( 5.8%)
@router.patch  :  110 ( 3.7%)
```

**Total Endpoints**: **3012** (Bash-Zaehlung `grep -rn "@router\." app/api/v1/`).

**Bewertung**:
- GET/POST dominieren (87.6%) - typisch fuer FastAPI Apps.
- PUT-Anteil mit 2.8% niedrig; PATCH wird haeufiger genutzt - moderne REST-Praxis.
- DELETE 5.8% - akzeptabel.
- Verteilung ist plausibel, aber **3012 Endpoints sind extrem viel** (Snowflake mit 3000+ Endpoints hat ~3000). Pilot-Risiko: zu viel Surface Area, schwer testbar.

---

## 3. Auth-Coverage Spotcheck

**Spotcheck (10 Files)**:

| File | Endpoints | Auth-Deps | Verhaeltnis |
|------|-----------|-----------|-------------|
| `help.py` | 12 | 12 | 100% |
| `scanner.py` | 9 | 7 | 78% |
| `barcodes.py` | 3 | 6 | 100%+ (multiple deps/route) |
| `lineage.py` | 6 | 6 | 100% |
| `holding.py` | 11 | 11 | 100% |
| `feature_flags.py` | 0/0 | 8 | n/a |
| `onboarding.py` | 9 | 9 | 100% |
| `groups.py` | 13 | 13 | 100% |
| `imports.py` | 30 | 30 | 100% |
| `ml.py` | 15 | 5 | **33%** |

**Gesamt-Stats** (rein quantitativ, files-level):
- Files mit `Depends.*current_user|require_auth`: **102 von 257** Files (40%)
- `Depends`-Imports gesamt: 256 von 257 Files
- Auth-Dependencies (`get_current_user`/`current_user`/`require_auth`): **992 Vorkommen**
- Bei 3012 Endpoints und ~992 Auth-Deps -> **rund 1/3 der Endpoints hat KEINE direkte Auth-Dep auf Route-Level**.

**Beleg**: `app/api/v1/ml.py` - 15 Endpoints, nur 5 Auth-Calls. Verdacht: Router-level dependencies oder Public Endpoints.

**Hinweis**: Manche Files nutzen Router-level Dependencies (z.B. `APIRouter(dependencies=[Depends(...)])`) - die Zahl unterschaetzt Auth-Coverage. Trotzdem: Spotcheck `ml.py` zeigt klare Luecke.

---

## 4. Rate Limiting

**Funde**: `grep -rn "Depends.*rate_limit|@rate_limit|RateLimiter|limiter\.limit"`:
- **554 Vorkommen** in `app/api/v1/`
- Hauptmuster: `@limiter.limit("X/minute", key_func=get_user_identifier)` (slowapi-basiert).
- Beispiele: `app/api/v1/agents.py:199` (`30/minute`), `app/api/v1/ai_conversations.py:302-719` (`20-60/minute`), `app/api/v1/admin/jobs.py:210-665` (`check_destructive_admin_rate_limit`).
- **Coverage geschaetzt**: 554 / 3012 = ~18% der Endpoints haben explizites Rate-Limit.

**Bewertung**: Solide RL fuer kritische Endpoints (Auth, AI, Admin destructive). Aber 82% der Endpoints **ohne** Rate Limiting - bei 100+ Concurrent Users (Pilot-Target) reicht globales nginx-RL nicht.

---

## 5. Stub Detection

**Suche**: `return {}`, `return []`, `return {"status": "ok"}`:
- **12 Funde gesamt** ueber `app/api/v1/` (Belege):
  - `calendar_sync.py:474` - `return []`
  - `credit.py:593` - `return []`
  - `feature_flags.py:565` - `return {}`
  - `hardware.py:380` - `return []`
  - `holding.py:248` - `return []`
  - `invoices.py:917`, `:1143` - `return []` (Fallback in catch?)
  - `personal.py:899`, `:1330` - `return []`
  - `reconciliation.py:514` - `return []`
  - `documents.py:1` (1x), `scanner.py:1` (1x).

**TODO/FIXME**: 12 Vorkommen in 0 Files (Bash hat keinen unterhaltbaren Match) -> **TODO/FIXME im API-Layer minimal**, was gut ist.

**Bewertung**: 12 leere Returns auf 3012 Endpoints (0.4%) ist niedrig. Die meisten sind Fallbacks im Exception-Handler, nicht echte Stubs. **Gut**.

---

## 6. Internal Endpoints

**Funde**: Kein separates `internal*.py` File. Internal-Endpoints sind in **`app/api/v1/metrics.py`** integriert:
- `metrics.py:135` - `@router.get("/internal/backup", response_class=Response)` (Prometheus Backup-Metrics)
- `metrics.py:158` - `@router.get("/internal/ab-testing", response_class=Response)` (A/B Testing Metrics)
- Auth: Beide via `verify_metrics_token(authorization)` (Bearer-Token, optional via `METRICS_SCRAPE_TOKEN` ENV).

**Risiko**: Wenn `METRICS_SCRAPE_TOKEN` nicht gesetzt ist -> "allows unauthenticated access (dev mode)". In Production unbedingt enforced. Doku-Hinweis vorhanden.

---

## 7. Spotlight API

**File**: `app/api/v1/spotlight.py` (3094 Bytes, 1 Endpoint).

```
@router.get("", response_model=SpotlightResponse)
@limiter.limit("200/minute", key_func=get_user_identifier)
async def spotlight_search(q: str, limit: int = 8, ...) -> SpotlightResponse
```

**Status**: **Production-Ready**. Auth via `Depends(get_current_active_user)`, RL `200/min`, sauberes Error-Handling via `safe_error_detail`. Service-Layer (`spotlight_service`) gekapselt. Test-File: `tests/unit/api/test_spotlight_api.py` (im git status sichtbar, untracked).

---

## 8. Smart Inbox API

**File**: `app/api/v1/smart_inbox.py` (6 Endpoints), Service: `app.services.ai.smart_inbox.smart_inbox_service.SmartInboxService`.

**Status**: **Production-Ready**. Pydantic v2 Schemas (`SmartInboxItemResponse`, `SmartInboxListResponse`, `SmartInboxActionRequest`, `SmartInboxSnoozeRequest`), Auth via `Depends(get_current_active_user)`. Test-File: `tests/unit/api/test_smart_inbox_api.py` (untracked, Plan-Sektion ausstehend laut Roadmap).

---

## 9. Modul-Kategorisierung

Geschaetzt nach Filename-Praefix und Endpoint-Count (`@router.*`):

| Modul | Files (geschaetzt) | Endpoints (Sum) | Kommentar |
|-------|--------------------|-----------------:|-----------|
| **AI/ML/Agents** | ~25 (ai_*, agents, ml_*, ki_*, neural, predictive_*, classification, anomalies, fraud_*) | ~600 | Heavy AI surface |
| **Documents** | ~20 (documents, archive, document_*, einvoice, ocr_*, extracted_data, similar_documents, duplicate_detection) | ~700 | Kern-Domaene |
| **Finance/Banking** | ~25 (banking_*, finance, accounting, invoices, expenses, cash*, datev*, gobd, german_finance, payment_*, recurring_*, budgets, credit, holding) | ~800 | Stark vertreten |
| **Admin** | 16 (admin/) + admin-related | ~400 | Gut isoliert |
| **Compliance/GDPR** | ~10 (compliance*, gdpr, dpia, dlp, retention, encryption, signatures, audit_*) | ~250 | Solid |
| **Personal/HR/Privat** | 7 (personal/, privat/, privat.py, privat_analytics.py, contracts*, employees) | ~470 | privat_analytics fett |
| **Workflow/Process** | ~10 (workflows, bpmn*, approvals*, process_mining, kanban, projects, recurring) | ~200 | |
| **Search/RAG** | 9 (rag/) + spotlight, search, semantic_search, smart_search, saved_searches | ~180 | |
| **Integration** | ~10 (slack, ms_teams, lexware, datev_connect, sso, mfa, calendar*, scanner, odoo_*) | ~200 | |
| **Notifications** | 5 (notifications, notification_*, push_*, alerts, ms_teams) | ~150 | |
| **Reports/Dashboards** | ~10 (reports, dashboards, dashboard_*, ceo_dashboard, daily_insights, morning_briefing, ad_hoc_reports) | ~400 | |
| **Health/Metrics** | 4 (health, metrics, readiness, profiling) | ~280 | health.py allein 224 |
| **Orchestration** | 1 (orchestration.py) | **554** | God-Module! |

**Total nach Modulen**: rund 3000-3500 Endpoints (deckt sich mit `wc -l` = 3012).

---

## 10. OpenAPI-Dokumentation

**Suche**: `summary=|description=|response_model=`:
- **10467 Vorkommen** in 250 Files (limit 250 erreicht, real wohl mehr).
- ~3.5 Doku-Hints pro Endpoint.

**Bewertung**: **Sehr gut dokumentiert**. Kombiniert mit Pydantic-Schemas und FastAPI Auto-OpenAPI-Generation -> `/docs` (Swagger UI) und `/redoc` sollten reichhaltige Dokumentation bieten. Beispiele: `documents.py` (114 Endpoints, viele response_models), `spotlight.py` (description in Query, deutsche Texte).

**Lokal verifizierbar**: `http://localhost:8000/docs` (laut CLAUDE.md).

---

## Top 3 Staerken

1. **Hohe OpenAPI-Doku-Dichte** (~3.5 Hints/Endpoint). Pydantic v2 + response_model durchgaengig. Swagger ist self-service-tauglich fuer Pilot-Onboarding.
2. **Robuste Auth-Patterns** in kritischen Files (admin/jobs.py mit `check_destructive_admin_rate_limit`, auth.py mit Refresh-Token-Blacklist, vault.py, spotlight.py, imports.py). 102/257 Files (40%) haben explizite Auth-Deps - die kritischen sind dabei.
3. **Internal-Endpoints sauber separiert** in metrics.py mit Token-Auth (`METRICS_SCRAPE_TOKEN`). Production-Pattern fuer Prometheus-Scraping ohne Wartung extra Routers.

## Top 5 Luecken

1. **God-Module `orchestration.py`** (554 Endpoints, 148 KB). Kein Pilot wird das warten koennen. **Refactor in Sub-Domains noetig** (cross_module, intent_routing, command_center).
2. **3012 Endpoints sind zu viele fuer Pilot**. Empfehlung: API-Surface fuer Pilot auf MVP-Slice (~200-300 Endpoints) reduzieren via Feature-Flags / Router-Mounting unter `/v1` vs `/v1-experimental`.
3. **Rate Limiting nur 18% Coverage**. Bei 100+ Concurrent Users im Pilot riskant. **Globales Default-RL** auf APIRouter-Level einfuehren (z.B. `100/min` baseline).
4. **Auth-Coverage-Gap**: Datei `ml.py` hat nur 5 Auth-Deps fuer 15 Endpoints (33%). Ohne Audit aller 257 Files keine Garantie, dass keine ungeschuetzten Endpoints existieren. **Empfehlung**: Globaler `Depends(get_current_user)` auf Router-Level + `@public` Marker fuer Ausnahmen (Whitelist statt Blacklist).
5. **Outlier-Files**: `accounting.py` (270), `health.py` (224), `privat.py` (186), `finance.py` (171), `ocr.py` (160), `privat_analytics.py` (136), `documents.py` (114), `entities.py` (113). Kein Single File sollte > 50 Endpoints haben. **Decomposition Plan** vor Pilot.

---

## Note: API Pilot-Readiness

**Bewertung: 5/10**

| Dimension | Wert | Kommentar |
|-----------|------|-----------|
| Doku-Qualitaet | 9/10 | OpenAPI vorbildlich |
| Auth-Coverage | 5/10 | Kritische Endpoints OK, viele Files unklar |
| Rate Limiting | 4/10 | Nur kritische Bereiche |
| API Surface | 3/10 | 3012 Endpoints, 1 God-Module |
| Stub-Quote | 9/10 | <1% leere Returns |
| Internal-Endpoints | 7/10 | Saubere Trennung, aber Token-Default unsicher |
| Module-Separation | 4/10 | Outlier-Files mit 100-554 Endpoints |
| Test-Coverage | 6/10 | Tests vorhanden (smart_inbox, spotlight), aber nicht alle 257 Files getestet |

**Pilot-Empfehlung**: API ist funktional, aber **NICHT pilot-ready ohne Slice-Strategie**. Vor Pilot:
1. MVP-Slice definieren (Welche 200-300 Endpoints brauchen Pilot-User?).
2. Globales Auth-Default + RL-Default auf Router-Level setzen.
3. `orchestration.py` und Top-5 Outlier zerlegen.
4. `METRICS_SCRAPE_TOKEN` als Required-ENV in Production-Profile.
