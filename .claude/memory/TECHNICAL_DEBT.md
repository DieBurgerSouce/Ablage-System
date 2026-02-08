# Technical Debt Tracking

**Last Updated**: 2026-02-08
**Overall Debt Level**: 🟢 LOW

---

## Debt Categories

| Category | Level | Priority | Estimated Effort |
|----------|-------|----------|------------------|
| Code Quality | Minimal | Low | 1-2 days |
| Security | None | - | 0 days |
| Architecture | Minimal | Low | 2-3 days |
| Testing | Low-Medium | Medium | 5-10 days |
| Documentation | Minimal | Low | 1-2 days |

**Total Estimated Effort to Zero Debt**: 2-3 Sprints

---

## Medium Priority Issues

### M1: Celery Task Naming Convention
**Category**: Code Quality
**Impact**: Monitoring & Debugging
**Effort**: 2 days
**Status**: 🟡 Open

**Issue**: Tasks nutzen verschiedene Naming-Patterns
```python
# Gemischt:
"app.workers.tasks.fx_rate_tasks.fetch_ecb_rates_daily"  # Full path
"retention_enforcement.enforce_retention_daily_scan"     # Short form
```

**Recommendation**: Standardisiere auf Full Path Naming

**Action Items**:
- [ ] Audit alle 414 Task Namen
- [ ] Standardisiere auf Full Path Pattern
- [ ] Update Celery Beat Schedules
- [ ] Update Monitoring Dashboards

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

### M3: Celery Beat Schedule Consolidation
**Category**: Architecture
**Impact**: Maintainability
**Effort**: 2 days
**Status**: 🟡 Open

**Issue**: Beat Schedules über 12+ Dateien verteilt
```python
# Current:
CELERY_BEAT_TRAINING_SCHEDULE    # training_tasks.py
REPORT_BEAT_SCHEDULE             # report_tasks.py
ENTITY_LINKING_BEAT_SCHEDULE     # entity_linking_tasks.py
CHAIN_BEAT_SCHEDULE              # chain_tasks.py
FRAUD_DETECTION_BEAT_SCHEDULE    # fraud_detection_tasks.py
PSD2_BANKING_BEAT_SCHEDULE       # banking_psd2_tasks.py
EINVOICE_BEAT_SCHEDULE           # einvoice_tasks.py
```

**Recommendation**: Zentrale Beat-Konfiguration
```python
# Proposed:
config/celery_beat.py  # Alle Schedules zentral
```

**Action Items**:
- [ ] Create `config/celery_beat.py`
- [ ] Migrate all Beat Schedules
- [ ] Remove individual schedule constants
- [ ] Update `celery_app.py` imports

---

## Low Priority Optimizations

### L1: Retention Task Batch Sizes
**Category**: Configuration
**Impact**: Performance Tuning
**Effort**: 1 hour
**Status**: 🟢 Open

**Current**: Hardcoded `batch_size=100`
**Recommendation**: Environment Variable
```python
BATCH_SIZE = int(os.getenv("RETENTION_INTEGRITY_BATCH_SIZE", "100"))
```

---

### L2: FX Rate Service Enhancement
**Category**: Business Logic
**Impact**: Feature Completeness
**Effort**: 3 days
**Status**: 🟢 Open

**Current**: `month_end_revaluation` ist Stub
```python
# TODO: Implementation
return {"entries_processed": 0}
```

**Required Implementation**:
1. Query offener Fremdwährungspositionen
2. Get aktueller ECB-Kurs für jede Währung
3. Berechne unrealisierte Kursgewinne/-verluste
4. Erstelle Journal Entries für materielle Differenzen

**Action Items**:
- [ ] Design FX Revaluation Algorithm
- [ ] Implement Position Query
- [ ] Implement G/L Calculation
- [ ] Create Journal Entry Generation
- [ ] Add Unit Tests (>80% coverage)

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
