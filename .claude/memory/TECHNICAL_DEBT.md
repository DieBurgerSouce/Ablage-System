# Technical Debt Tracking

**Last Updated**: 2026-02-13
**Overall Debt Level**: 🟢 LOW

---

## Debt Categories

| Category | Level | Priority | Estimated Effort |
|----------|-------|----------|------------------|
| Code Quality | None | - | 0 days |
| Security | None | - | 0 days |
| Architecture | None | - | 0 days |
| Testing | Low-Medium | Medium | 5-10 days |
| Documentation | Minimal | Low | 1-2 days |

**Total Estimated Effort to Zero Debt**: 2-3 Sprints

---

## Medium Priority Issues

### ✅ M1: Celery Task Naming Convention
**Category**: Code Quality
**Impact**: Monitoring & Debugging
**Effort**: 2 days
**Status**: ✅ ERLEDIGT (2026-02-13)

**Ergebnis**: Alle ~180+ Task-Dekoratoren und ~80+ Beat-Schedule-Eintraege auf Full Path
Naming standardisiert (`app.workers.tasks.<module>.<function>`). Zusaetzlich ~125
Task-Routes-Eintraege in `celery_app.py` aktualisiert. Keine Short-Form-Namen mehr vorhanden.

Senior Review (2026-02-13): 4 uebersehene `send_task()` Short-Form-Aufrufe in
`import_tasks.py` korrigiert (`import.retry_single_email/file` -> Full Path).
4 Referenzen auf nicht-existierendes `process_document_ocr` in `ocr.py`,
`ai_action_service.py`, `workflow_step_executor.py` auf `process_document_task` korrigiert.
`test_banking_tasks.py` bereinigt (TestBankingBeatSchedule Klasse entfernt, importierte
geloeschte BANKING_BEAT_SCHEDULE Konstante).

Ralph Loop Review (2026-02-13): KRITISCHEN Parameter-Mismatch in `ocr.py` gefunden und behoben.
`send_task()` nutzte positionale `args=[]` - dabei wurde `request.priority` (int 1-10) als
3. Argument an `language` statt `priority` uebergeben. Fix: `args` -> `kwargs` mit expliziten
Schluesselwort-Argumenten + `_int_to_priority_str()` Konverter (int -> high/normal/low).
Betrifft beide Stellen: Single-OCR (Zeile ~575) und Batch-OCR (Zeile ~1210).
4 YAML Design-Dokumente mit veraltetem `process_document_ocr` auf Full Path korrigiert.

- [x] Audit alle Task Namen (30+ Dateien geprueft)
- [x] Standardisiere auf Full Path Pattern
- [x] Update Celery Beat Schedules (81 Eintraege)
- [x] Update Task Routes (125 Eintraege)
- [x] Senior Review: 4 send_task() Short-Form-Aufrufe in import_tasks.py korrigiert
- [x] Senior Review: 4 process_document_ocr Referenzen korrigiert
- [x] Senior Review: test_banking_tasks.py BANKING_BEAT_SCHEDULE Tests entfernt
- [x] Ralph Loop: ocr.py send_task() positional args -> kwargs (Parameter-Mismatch priority->language)
- [x] Ralph Loop: _int_to_priority_str() Konverter (OCRStartRequest.priority int -> Task str)
- [x] Ralph Loop: 4 YAML Design-Dokumente process_document_ocr -> Full Path korrigiert
- [x] Ralph Loop Deep Review: _int_to_priority_str() nach app/core/priority.py extrahiert (shared utility)
- [x] Ralph Loop BUG 6: document_tasks.py user_id=user_id entfernt (Parameter existiert nicht -> TypeError)
- [x] Ralph Loop BUG 7: documents.py priority int -> int_to_priority_str() in task kwargs (war nur broker priority)
- [x] LOW: 3 Docs process_document_ocr -> process_document_task korrigiert (API_Documentation, Background-Tasks, Testing-Guide)

---

### M2: Test Coverage für Enterprise Features
**Category**: Testing
**Impact**: Production Safety
**Effort**: 5 days
**Status**: 🟡 Open

**Current Coverage**:
- Core Features: >80% ✅
- Enterprise Features (Migrations 202-208): ~60% ⚠️

**Missing Tests**:
- [ ] `tests/unit/services/accounting/test_fx_rate_service.py`
- [ ] `tests/unit/services/accounting/test_gl_posting_service.py`
- [ ] `tests/unit/services/accounting/test_euer_report_service.py`
- [ ] `tests/unit/workers/test_retention_enforcement_tasks.py`
- [ ] `tests/integration/test_psd2_banking_flow.py`
- [ ] `tests/integration/test_autonomous_trust_upgrades.py`

**Target**: 80%+ Coverage für alle Enterprise Features

---

### ✅ M3: Celery Beat Schedule Consolidation
**Category**: Architecture
**Impact**: Maintainability
**Effort**: 2 days
**Status**: ✅ ERLEDIGT (2026-02-13)

**Ergebnis**: Alle 18 toten `*_BEAT_SCHEDULE`-Konstanten aus Task-Dateien entfernt.
Diese waren Dead Code - definiert in Task-Dateien, exportiert via `__init__.py`,
aber nie von `celery_app.py` importiert (welches seine eigene inline Beat-Schedule hat).
`__init__.py` Imports und `__all__`-Eintraege ebenfalls bereinigt.

Entscheidung: Keine separate `config/celery_beat.py` noetig - `celery_app.py` ist bereits
die zentrale Single Source of Truth fuer alle Beat Schedules.

- [x] Dead Code BEAT_SCHEDULE Konstanten entfernt (18 Dateien)
- [x] `__init__.py` Exports bereinigt (7 Imports + 7 `__all__` Eintraege)
- [x] Zentrale Beat-Konfiguration bestaetigt (celery_app.py Lines 540-1964)

---

## Low Priority Optimizations

### ✅ L1: Retention Task Batch Sizes
**Category**: Configuration
**Impact**: Performance Tuning
**Effort**: -
**Status**: ✅ NICHT ZUTREFFEND (2026-02-13)

**Ergebnis**: `retention_enforcement_tasks.py` enthaelt kein hardcoded `batch_size=100`.
`gdpr_tasks.py` hat `RETENTION_CHECK_BATCH_SIZE = 500` (angemessen).
TECHNICAL_DEBT.md war veraltet - Issue existiert nicht.

---

### ✅ L2: FX Rate Service Enhancement
**Category**: Business Logic
**Impact**: Feature Completeness
**Effort**: 3 days
**Status**: ✅ ERLEDIGT (2026-02-13)

**Ergebnis**: `month_end_revaluation()` ist VOLL IMPLEMENTIERT in `fx_rate_service.py`.
Implementierung umfasst: Position Query, ECB-Kurse, unrealisierte Gewinne/Verluste,
Journal Entry Generierung. TECHNICAL_DEBT.md war veraltet.

---

### L3: Monitoring Dashboard für Retention Enforcement
**Category**: Observability
**Impact**: Compliance Visibility
**Effort**: 2 days
**Status**: 🟢 Open

**Current**: CLI-only Reports
**Recommendation**: Grafana Dashboard

**Metrics zu tracken**:
- Ablaufende Archive (30/60/90 Tage)
- Integrity Check Failures
- Auto-Delete Statistics
- Compliance Score per Company

**Action Items**:
- [ ] Create Grafana Dashboard JSON
- [ ] Add Prometheus Metrics zu `retention_enforcement_tasks.py`
- [ ] Setup Alerts für Critical Compliance Failures
- [ ] Document Dashboard in Operations Runbooks

---

## Completed Debt Items (2026-02-13)

### ✅ M1: Celery Task Naming Convention
**Completed**: 2026-02-13
**Effort**: 1 day
- [x] ~180+ Task-Dekoratoren auf Full Path standardisiert (30+ Dateien)
- [x] 81 Beat-Schedule-Eintraege in celery_app.py aktualisiert
- [x] ~125 Task-Routes-Eintraege in celery_app.py aktualisiert

### ✅ M3: Celery Beat Schedule Consolidation
**Completed**: 2026-02-13
**Effort**: 1 day
- [x] 18 tote BEAT_SCHEDULE-Konstanten aus Task-Dateien entfernt
- [x] 5 kommentierte BEAT_SCHEDULE-Bloecke entfernt (gobd, lexware, privat, retention x2)
- [x] 7 Imports + 7 __all__-Eintraege in __init__.py bereinigt
- [x] celery_app.py als zentrale Single Source of Truth bestaetigt

## Completed Debt Items (2026-02-08)

### ✅ C1: Asyncpg Migration Hardening
**Completed**: 2026-02-08
**Effort**: 3 days
- [x] 17 Migrations asyncpg-kompatibel gemacht
- [x] SQL Splitting Workaround in `alembic/env.py`
- [x] Lazy Model Loading (RAM-Optimierung)

### ✅ C2: PII Leak Prevention (CWE-532)
**Completed**: 2026-01-30
**Effort**: 5 days
- [x] 388 Dateien mit `safe_error_detail()` gesichert
- [x] `app/core/safe_errors.py` Utility erstellt
- [x] Automatisches PII-Masking in allen Services

### ✅ C3: Type Safety Enforcement
**Completed**: 2026-01-30
**Effort**: 2 days
- [x] All `Any` Types entfernt
- [x] Full Type Hints in allen Services
- [x] Mypy Strict Mode ready

---

## Debt Metrics History

| Date | Overall Level | Notes |
|------|---------------|-------|
| 2026-02-13 | 🟢 LOW | M1+M3 Celery Consolidation erledigt |
| 2026-02-08 | 🟢 LOW | After Enterprise Review |
| 2026-01-30 | 🟡 MEDIUM | Before PII/Type Safety Fixes |
| 2026-01-25 | 🟡 MEDIUM | Vision 2.0 Implementation Phase |

---

## Prevention Strategy

### Code Review Checklist
- [ ] Type Hints vollständig
- [ ] Tests geschrieben (>80% coverage)
- [ ] PII-Filtering in Error Logs
- [ ] German User Messages
- [ ] Security Audit (SQL Injection, CRLF)
- [ ] Documentation aktualisiert

### CI/CD Gates
- Type checking (mypy)
- Test coverage >80%
- Security scan (Bandit)
- Dependency audit
- Migration tests

---

**Next Review**: Nach Test Coverage Improvements (Target: 2026-02-15)
