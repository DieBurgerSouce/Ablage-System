# 04 — Backend Engineer Perspective

**Rolle:** Senior Python/FastAPI/PostgreSQL (20 Jahre).
**Stand:** 2026-05-03, Branch `feature/ocr-performance`.
**Methode:** Code-Evidenz an konkreten Datei:Zeile-Belegen, kein Vibe-Check.

---

## 1-Satz-Verdikt

Solides Mid-Senior-Backend mit Enterprise-Ambitionen (Hash-Chain, Pydantic v2, structlog, Cross-DB-Layer), das aber an drei klassischen Skalierungs-Symptomen krankt — God-Objects, Async/Sync-Vermischung in Celery-Workers und Silent-Catches an Compliance-kritischen Pfaden — und dadurch noch nicht das Niveau "Senior-Engineering-Reife" erreicht, sondern eher "ehrgeizig, aber unter Hardening-Stress".

---

## Top-3 Stärken (was beeindruckend ist)

1. **EventStore Hash-Chain in Senior-Qualität**
   `app/services/event_sourcing/event_store.py:482` (`_calculate_event_hash` mit kanonischem JSON, `sort_keys=True`, `separators=(",", ":")`), `:507` (`_calculate_chain_hash` SHA-256), `:540` (`verify_chain` rekonstruiert Kette). Genesis-Hash `event_store.py:44` definiert. Kombiniert mit `app/db/models_misc.py:814` `DomainEvent` (`event_hash`, `previous_hash`, `chain_hash`, `sequence_number`, `correlation_id`, `causation_id`) und `UniqueConstraint(aggregate_type, aggregate_id, sequence_number)` (Z.853) ein **echtes** auditierbares Event-Sourcing — kein Schaufensterstück. Migration `254_event_store_hash_chain.py` (Feb 2026) ist sauber gepinnt. Das ist Senior-Level-Arbeit.

2. **Pydantic v2 + Cross-DB-Type-Layer ohne Migration-Schulden**
   `grep` auf `from pydantic.v1` liefert **0 Treffer** in `app/`. `BaseSettings` ausschließlich aus `pydantic_settings` (`app/core/config.py:24,45`). Dazu der Cross-DB-Layer in `app/db/models_base.py:37-49` (`CrossDBJSON`, `CrossDBTSVector`, `CrossDBVector`) — dialekt-aware (pgvector auf PG, Text auf SQLite). Ermöglicht SQLite-Tests + PostgreSQL-Production ohne Code-Branches. Das ist der Pattern, den man selten so sauber sieht.

3. **Resilience- und Logging-Hygiene wurde aktiv ausgerollt**
   `app/core/resilience.py` existiert (Circuit Breaker mit State-Machine, Async/Sync-Decorators, Prometheus-Metriken, `circuit_breaker_state_changes_total` Counter). 15 Files nutzen `circuit_breaker`/`CircuitBreaker` — `metrics.py`, `ocr_pipeline.py`, `webhook_dispatcher.py`, `llm_ocr_review_service.py`, `fallback_chain.py`, OCR-Agents (DeepSeek, GOT). Ergänzend: structlog-Migration ist faktisch komplett — nur **2 Files** mit `logging.getLogger` (`app/core/logging_config.py:4`, README, beides erwartet), gegenüber breiter `import structlog`-Adoption. Commit `9385e8e4` (89 Files migriert) hat geliefert.

---

## Top-5 Lücken / Code-Smells (mit Datei:Zeile)

### 1. `asyncio.run()` in Service-Code und massiv in Celery-Workern
**Bug-Magnet erster Ordnung.** Zwar ist Celery klassisch synchron (Worker hat keinen Loop), aber:
- `app/services/adhoc_report_service.py:991` — `asyncio.run(...)` mitten in Service-Methode. Wird ein FastAPI-Endpoint diese Methode synchron aufrufen, wird sie aus dem laufenden Loop heraus crashen (`RuntimeError: asyncio.run() cannot be called from a running event loop`).
- `app/workers/bpmn_tasks.py:88, 162, 200, 315, 373, 448` — sechs Tasks, alle wickeln `async def`-Inneres mit `asyncio.run(...)` ab.
- `app/workers/tasks/cashflow_prediction_tasks.py:145, 258, 354, 489, 655, 816, 932` — sieben weitere.
- `app/workers/task_callbacks.py:45, 60` — sogar im ThreadPoolExecutor (`executor.submit(asyncio.run, coro)`).

Kommentar in `task_callbacks.py:33` rechtfertigt das mit "asyncio.run() handles event loop creation and cleanup properly" — was für Celery-Workers stimmt, aber: jeder dieser Aufrufe baut bei jedem Task-Run einen **frischen Event-Loop**. Connection-Pools, GPU-Manager-Singletons, asynccontextmanager-State werden **nicht wiederverwendet**. Das ist ein Performance- und Ressourcen-Leak. Die saubere Lösung ist ein persistierender Loop pro Worker (`celery_pool=solo` oder `aiohttp.ClientSession`-pattern), nicht 14+ `asyncio.run`-Aufrufe.

### 2. God-Objects in Service-Layer
- `app/services/structured_extraction_service.py` — **118.268 Bytes** (~3.000+ Zeilen). Nicht testbar.
- `app/services/privat/tax_optimization_service.py` — **98.907 Bytes**.
- `app/services/streckengeschaeft/__init__.py` — **87.584 Bytes** Logik im Package-Init. Anti-Pattern par excellence.
- `app/services/quick_classification_service.py` — **78.638 Bytes**.
- `app/api/v1/orchestration.py` — **554 `@router.*`-Decorations** in einer Datei (Audit 00d §1).

Kein Senior-Reviewer durchquert eine 118-KB-Datei in einem PR. Cyclomatic-Complexity wird hier strukturell unwartbar.

### 3. 56 × `except Exception: pass` an Compliance-kritischen Pfaden
Audit 00b §6 hat es konkret:
- `app/services/access_analytics_service.py:840, 861` — Audit-Service schluckt Exceptions stumm (Compliance-Risiko).
- `app/services/imports/email_import_service.py:798, 822, 1111` — Import-Pfad verschluckt 3× Exceptions; Nutzer sieht keinen Fehler.
- `app/services/imports/folder_import_service.py:839, 881, 1078` — gleiches Muster.
- `app/services/ai/fraud_detection_service.py:683` — Fraud-Detection silent.
- `app/services/search_service.py:662, 672` — Index-Update schlägt silent fehl.

Bei einem Pilot mit Lexware-Import + GoBD-Audit-Trail bedeutet das: **Datenverlust ohne Telemetrie**. Mid-Senior-Antipattern. Senior würde mindestens `logger.exception(...)` plus targeted-catch verlangen.

### 4. Transaction-Boundaries quasi nicht vorhanden
`grep -rn "with .*\.begin\(\)\|@with_transaction\|async with.*begin"` in `app/services/`: nur **7 Treffer in 4 Files** (`nlq_orchestrator.py:1`, `job_admin_service.py:3`, `payment_service.py:1`, `partial_payment_service.py:2`). Bei 797 Service-Files. Multi-Step-Mutationen (Invoice-Creation + Audit-Log + Document-Update + Event-Emit) laufen ohne explizite Transaction-Klammer — verlassen sich auf den FastAPI-Request-Scope-Commit. Bei Celery-Tasks (synchron, ohne Request-Scope) ist das eine offene Wunde: halbe Mutation + Crash = inkonsistenter Zustand. Skonto-Buchung + Bank-Reconciliation ohne `BEGIN ... COMMIT` ist GoBD-fragwürdig.

### 5. N+1-Verdacht im latenz-kritischen Spotlight-Service
Audit 00b §5: `app/services/spotlight_service.py` — **kein** `joinedload`/`selectinload`-Import, obwohl Header-Kommentar Latenz <200 ms versprich. Repo-weit nutzen nur ~34 % der Service-Files Eager-Loading (269/797). Ergänzend: nur ~33 % der Endpoints haben dezidiertes Rate-Limiting (Audit 00d §4). Bei 100+ Concurrent Users im Pilot wird das auffallen.

---

## Backend Engineering Quality: **Note 6 / 10**

**Begründung der Note:**

| Dimension | Punkte | Begründung |
|---|---:|---|
| Type-Hygiene (Pydantic v2, JSONDict) | 8 | Sauber durchgezogen |
| Logging-Konsistenz (structlog) | 9 | Migration de facto fertig |
| Compliance-Fundament (Hash-Chain, Audit-Log) | 9 | Senior-Level |
| Async-Hygiene (Workers + Services) | 4 | 14+ `asyncio.run` in Workers, 1 in Service |
| Error-Handling | 4 | 56 silent catches an falschen Stellen |
| Transaction-Discipline | 3 | Quasi keine expliziten Begin-Blocks |
| N+1 / Performance-Hygiene | 5 | Inkonsistent (~34 % Coverage) |
| Modularisierung (God-Object-Quote) | 3 | 118-KB- und 88-KB-Dateien |
| Resilience (Circuit Breaker) | 7 | Existiert, 15 Anwendungen |
| Background-Jobs (Idempotenz) | 7 | `acks_late=True` an kritischen Tasks (`pipeline_tasks.py:56`, `cleanup_tasks.py:39`, `vault_tasks.py:21`, `tasks_data_quality.py:27`); `task_acks_late=True` global in `celery_app.py:387`. Aber: Idempotenz-Keys nicht durchgängig sichtbar. |
| API-Versioning | 5 | Nur `/v1`, plus 1 Ad-hoc-`/v2`-Suffix in `document_chains_v2.py:41`. Keine dokumentierte Strategie für Breaking-Changes. |
| Test-Disziplin (siehe 00g) | 6 | 678 Unit-Tests, aber 1837 Mock-Imports → mock-lastig; Banking 70 %, Frontend 15-20 %. Test-Stagnation 0 Commits in 14 Tagen. |

**Mittelwert ≈ 5,8 → gerundet 6.** Backend ist *ambitioniert mit Compliance-Highlights*, aber die Skalierungs-Smells (God-Objects, Async-Mix, Silent-Catches, Transaction-Lücken) verhindern eine 7+. Eine 7 würde "Senior-Engineering-Reife" signalisieren — die ist **noch nicht** erreicht. Eine 5 wäre zu hart, weil Hash-Chain + Pydantic-v2-Sauberkeit + structlog-Vollmigration echte Senior-Arbeit zeigen.

**Vergleich zu Audit 00b** (das 6/10 Pilot-Readiness vergibt): konsistent. Mein Engineering-Quality-Blickwinkel ist nicht milder, weil Pilot-Readiness und Engineering-Reife sich überlappen.

---

## 3 Hardening-Empfehlungen (priorisiert)

### Empfehlung 1 (P0, < 1 Woche): Async-Worker-Refactor + asyncio.run-Audit
**Aktion:**
1. `app/services/adhoc_report_service.py:991` — Methode auf `async def` umschreiben oder synchronen Wrapper extrahieren. Sofort-Bug, Endpoint-Pfad könnte heute schon crashen.
2. Celery-Worker auf **persistierten Loop** umstellen: pro Worker-Process einen `asyncio.new_event_loop()` in `worker_init`, Tasks rufen `loop.run_until_complete(coro)` statt `asyncio.run()`. Eliminiert Loop-Erstellung pro Task (heute in `bpmn_tasks.py` 6× pro Task-Set, in `cashflow_prediction_tasks.py` 7×). Schont DB-Connection-Pools und GPU-Initialisierung.
3. Linter-Regel ergänzen: `flake8-async` oder `ruff` mit ASYNC-Codes (`ASYNC100`, `ASYNC101`) in CI; `asyncio.run` außerhalb `__main__`-Blöcken bricht den Build.

**Erwartung:** Latenz-Verbesserung 20–40 % bei Worker-Tasks, eliminierter Crash-Vektor in Service-Layer.

### Empfehlung 2 (P1, 2–3 Wochen): Silent-Catch-Audit + Transaction-Boundaries
**Aktion:**
1. Alle 56 `except Exception: pass` durchgehen (Liste in Audit 00b §6). Drei-Klassen-Schema:
   - **Compliance/Audit/Import** (`access_analytics_service.py`, `email_import_service.py`, `folder_import_service.py`, `fraud_detection_service.py`): MUSS `logger.exception(...)` + reraise oder als gezielte Failure-Counter-Increment + sichtbare Telemetrie.
   - **Search-Index-Update** (`search_service.py:662, 672`): retry-mit-backoff + DLQ.
   - **UI-tolerant** (z. B. Fallback-Defaults): explizite `except <SpecificError>:` mit Kommentar warum stumm.
2. Transaction-Wrapper-Decorator etablieren (`@transactional` aus `app/db/transaction.py`) und **alle Multi-Step-Mutationen in `services/banking/`, `services/invoice/`, `services/document_services/`, `services/datev/`** dekorieren. Heute existieren nur 7 Begin-Blocks bei 797 Files — das ist die größte versteckte GoBD-Lücke nach der Hash-Chain-Stärke.

**Erwartung:** Datenkonsistenz-Garantie für Pilot, kein Silent-Data-Loss mehr.

### Empfehlung 3 (P2, 4–6 Wochen): God-Object-Decomposition + N+1-Sweep
**Aktion:**
1. Top-4 God-Objects zerlegen: `structured_extraction_service.py` (118 KB), `tax_optimization_service.py` (99 KB), `streckengeschaeft/__init__.py` (88 KB → in echte Module verschieben), `orchestration.py` (148 KB / 554 Endpoints) in domain-bezogene Subdirectories. Ziel: kein Service-File >30 KB, kein Router-File >50 Endpoints.
2. N+1-Audit für die Latenz-kritischen Pfade: `spotlight_service.py`, `documents.py` (114 Endpoints), `entities.py` (113), `archive.py` (96). Konkret: pytest-fixture mit `event.listens_for(Engine, "before_cursor_execute")` zählt SQL-Statements pro Request, Schwellenwert <10 für List-Endpoints. Failt der Test, wird `selectinload`/`joinedload` verlangt.
3. API-Versioning-Strategie dokumentieren: heute existiert nur `/v1` plus ein einsamer Ad-hoc-`/v2`-Pfad (`document_chains_v2.py:41`) — entweder konsequent semver-API mit Deprecation-Header (`Sunset: <date>`, `Deprecation: <date>`) oder Vertrags-Tests pinnen (`tests/contract/test_openapi_compatibility.py` existiert bereits, aber unklar gepflegt).

**Erwartung:** Reviewbarkeit wiederhergestellt, Latenz-SLA für Spotlight + List-Endpoints belastbar, Pilot-Skalierungs-Pfad offen.

---

**Fazit für Pilot-Entscheidung:**
Backend ist für **Single-Tenant on-premises** beim Familienbetrieb pilot-tauglich, aber unter dem Vorbehalt, dass Empfehlung 1 + 2 vor Go-Live umgesetzt werden. Die Hash-Chain + Append-Only-Cash-Entry-Constraints geben dem Pilot ein echtes Compliance-Gerüst — das ist nicht jeder mid-senior-Codebase gegeben. Die Async/Silent-Catch-Lücken sind reparabel, aber nicht ignorierbar.
