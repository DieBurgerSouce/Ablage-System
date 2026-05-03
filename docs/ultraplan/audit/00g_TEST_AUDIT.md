# 00g — TEST AUDIT (Pilot-Reality-Check)

**Datum**: 2026-05-03
**Branch**: feature/ocr-performance
**Scope**: Pilot-Readiness der gesamten Test-Suite

---

## 1. Test-Inventur (harte Zahlen)

| Kategorie | Anzahl | Typ |
|-----------|-------:|-----|
| **Unit Tests (Backend)** | **678** `test_*.py` | pytest |
| **Integration Tests** | **53** `test_*.py` | pytest + Postgres/Redis |
| **E2E Tests** | **53 Files** (10 `test_*.py`, 2 `*.js`, 2 `*.json`, Screenshots, MD) | gemischt — Python `httpx`/Mocks, KEIN Playwright |
| **Frontend Tests** | **58** `*.test.tsx` / `*.test.ts` | Vitest (`frontend/vitest.config.ts`) |
| **Security Tests** | 12 (`tests/security/`) | XSS, CSRF, SSRF, Injection, CRLF, PII |
| **Contract Tests** | 1 (`tests/contract/test_openapi_compatibility.py`) | OpenAPI-Diff |
| **Chaos Tests** | 4 (`tests/chaos/`) | GPU/Network/Storage Failures |
| **Performance/Load/GPU/Visual** | ~20 weitere | speziell |

**Gesamt Backend**: ~750 Test-Files. Großzügige Suite — auf den ersten Blick beeindruckend.

---

## 2. Test-Verzeichnis-Struktur

`tests/unit/services/` ist nach **Domain** sauber sortiert (50 Subdirs):
`accounting, admin, ai, analytics, approval, auth, banking, bpmn, collaboration, compliance, contracts, dashboard, datev, dlp, document_intelligence, einvoice, erp, evaluation, event_sourcing, external, extraction, finance, finanzki, imports, insights, integrity, kpi, lineage, matching, mlops, notification, ocr, orchestration, portal, portfolio, predictive, privacy, privat, rag, realtime, reports, rules, security, shipping, signature, tenant, webhooks, workflow, year_end`.

**Stärke**: Jedes große Domain-Modul hat ein eigenes Test-Verzeichnis.
**Schwäche**: Zu viele lose `test_*.py` direkt unter `tests/unit/services/` (40+ Files ohne Subdir) → Inkonsistente Organisation.

`tests/unit/api/`: 102 API-Tests (gut). `tests/integration/` enthält wenige Datei-namen-Cluster wie `test_cash_*.py` (5 Files für Kasse-Modul → indikativ überrepräsentiert).

---

## 3. Service-Test-Mapping (Stichprobe Banking 10/10)

`app/services/` enthält **797** `*.py` Files. `tests/unit/services/` enthält **404** `test_*.py`. Naive Ratio: ~50%, aber viele Services sind `__init__.py`/`models.py`/Helper.

**Stichprobe `app/services/banking/` (erste 10 Services)**:

| Service | Test vorhanden? |
|---------|:---------------:|
| account_connection_service | **MISSING** |
| account_service | OK |
| aging_report_service | OK |
| auto_reconciliation_service | OK |
| auto_transaction_import_service | **MISSING** |
| cash_flow_service | OK |
| dunning_letter_service | OK |
| dunning_service | OK |
| dunning_stage_service | **MISSING** |
| enhanced_fints_service | OK |

→ **70% Coverage in einer der best-getesteten Domains (Banking)**. Real auf gesamter Codebase wahrscheinlich 50–60% Service-Coverage.

---

## 4. Frontend-Test-Status

**FAANG-Behauptung "nur 3 Tests" ist OBSOLET.** Aktuelle Realität: **58 Frontend-Tests**.

Beispiele (nicht mehr nur Auth!):
- `frontend/src/features/banking/__tests__/DunningTable.test.tsx`
- `frontend/src/features/invoices/__tests__/InvoiceTable.test.tsx` (+ 9 weitere Invoice-Tests)
- `frontend/src/features/document-graph/__tests__/DocumentGraphView.test.tsx`
- `frontend/src/components/ui/__tests__/Button.test.tsx`, `Dialog`, `Input`, `responsive-table`, `empty-state`
- `frontend/src/lib/api/__tests__/client.test.ts`, `error-toast-handler.test.ts`
- `frontend/src/__tests__/routes/login.test.tsx`, `forgot-password`, `reset-password`, `index`, `$.test.tsx`

**Stärke-Cluster**: Invoices (10 Tests), Banking (5), Document-Graph (3), UI-Components (5).
**Lücke**: Keine Tests für `dashboard`, `ocr-review`, `upload`, `settings/*` (nur `SecuritySettingsTab`), `privat/*`, `kasse/*`. Frontend-Coverage geschätzt **15–20%**.

---

## 5. E2E-Inhalt (Realität-Check)

**Beispiel: `tests/e2e/test_upload_ocr_flow.py:25-55`** — pures Mocking, kein echter Browser:

```python
with patch("app.services.storage_service.StorageService") as MockStorage:
    mock_storage = AsyncMock()
    mock_storage.upload_file.return_value = {"file_id": "doc_upload_001", ...}
```

→ Diese sogenannten "E2E"-Tests sind **Integration-Tests mit Mocks**, KEIN echtes Playwright/Cypress!

Echte Browser-Tests sind nur in `tests/e2e/console-capture-test-suite.js` und `ultra-browser-diagnostics.js` (2 JS-Files, ad-hoc, kein CI-Hook). Es gibt `privat_full_test.py` mit Playwright-Anflug, aber kein systematisches E2E-Framework.

**KRITISCHE LÜCKE**: Es existiert KEIN `playwright.config.ts`, KEIN `e2e/` mit `.spec.ts`-Files. Trotz `frontend/.claude-flow/` ist E2E-Browser-Testing für den Pilot **nicht produktiv aufgesetzt**.

---

## 6. conftest.py — Mock-Strategie Tier 1

`tests/conftest.py` (Zeilen 13-43): **Mockt `torch`, `torchvision`, `transformers`, `accelerate`, `bitsandbytes`, `sentence_transformers`** wenn lokal nicht installiert. `torch.cuda.is_available() → False`. Gut für Lauffähigkeit ohne GPU, ABER:

→ Das bedeutet ein Großteil der OCR/ML-Tests testet **gegen Mocks, nicht gegen echte Modelle**. OCR-Backend-Tests sind effektiv Schnittstellen-Smoke-Tests.

`APP_AVAILABLE`-Flag (Zeile 67) erlaubt Tests, die App nicht laden — gefährlich, da es stille Skip-Logik gibt.

---

## 7. Mock vs Real-DB

`grep "from unittest.mock|@patch|MagicMock"` → **1837 Vorkommen** in Test-Dateien. Das ist **viel** für 750 Test-Files (Ratio 2.4 Mock-Imports pro File!). Tests sind massiv mock-lastig.

**Echte DB-Tests**: nur `tests/integration/test_cash_real_db.py`, `test_rls_context.py`, `test_multi_tenant_isolation.py` (+ paar weitere) verwenden echte Postgres-Sessions.

→ **Risiko**: Unit-Tests fangen viele reale SQL/Migration/RLS-Bugs nicht ab.

---

## 8. CI-Workflows (`.github/workflows/`)

Test-relevant: `ci.yml` (Job: pre-commit + code-quality + ruff + mypy), `coverage.yml` (mit Postgres+Redis Services), `smoke-tests.yml`, `pr-security.yml`, `dast-scan.yml`, `e2e.yml`, `performance.yml`, `backup-restore-test.yml`.

**`ci.yml:25-50`**: pre-commit als Quality-Gate, danach ruff/mypy. **Echte pytest-Läufe nicht im sichtbaren Snippet — Coverage-Job läuft separat.**

`pytest.ini` (Zeile 5-29): saubere Marker (`unit, integration, contract, e2e, slow, gpu`), `asyncio_mode = auto`, Coverage-Section konfiguriert (`source = app`).

---

## 9. Coverage-Tool-Setup

| Item | Status |
|------|:------:|
| `pytest.ini` | EXISTS (mit `[coverage:run]`-Section) |
| `pyproject.toml` | EXISTS |
| `.coveragerc` | NICHT VORHANDEN (Settings in pytest.ini) |
| `.coverage` (Run-Artefakt) | EXISTS im Root |
| `htmlcov/` | NICHT VORHANDEN |
| `coverage.xml` | NICHT VORHANDEN |

→ **Lokal wurde gerade gelaufen, aber kein veröffentlichter HTML/XML-Report**. CI generiert Coverage über `coverage.yml`, aber kein sichtbarer Badge oder Codecov-Upload im Repo.

**Geschätzte tatsächliche Coverage** (basierend auf Mock-Anteil und Service-Mapping): **40–55% Branch-Coverage backend**, **15–20% frontend**.

---

## 10. Test-Recency

`git log --since="14 days ago" -- tests/` → **0 Commits in den letzten 14 Tagen**.
`git log --since="30 days ago" --diff-filter=A -- tests/` → **0 neue Tests in 30 Tagen**.

Die `?? tests/unit/services/...` Untracked-Files in git status (`test_smart_inbox_api.py`, `test_spotlight_api.py`, `test_document_export_service.py`, `test_document_lifecycle_service.py`, `test_embedding_service.py`, `test_push_notification_service.py`, `test_spotlight_service.py`, `test_umlaut_validation_service.py`) sind ungestaged → Recent Work, aber **noch nicht committed**.

→ **Test-Suite stagniert**. Letzter committeter Test-Commit war `e3b4210a test(services): 5 neue Unit-Tests fuer Security, Shipping, Signature, Tenant, Webhooks` — schon älter als 14 Tage.

---

## 11. GoBD-relevante Tests

| File | Zweck |
|------|-------|
| `tests/integration/test_gobd_api.py` | API-Layer GoBD |
| `tests/unit/services/compliance/test_gobd_service.py` | Service GoBD |
| `tests/unit/services/test_gobd_compliance_service.py` | Duplikat (zwei Services?) |
| `tests/unit/api/test_audit_trail_api.py` | Audit-Trail API |
| `tests/unit/api/admin/test_audit_admin.py` | Admin-Audit |
| `tests/unit/core/test_audit_logger.py` | Logger Unit |
| `tests/unit/services/admin/test_audit_service.py` | Audit Service |
| `tests/unit/services/test_security_audit_service.py` | Security-Audit |

**Lücke**: KEIN expliziter Test für **`hash_chain` (Append-Only)**, **`tamper_detection`**, **`gdpr_deletion_with_audit_preservation`**. Das sind die heikelsten GoBD-Anforderungen für Pilot.

---

## 12. Multi-Tenant-Tests

`grep "tenant" tests/` → **83 Files** referenzieren Tenant-Kontext.

Hauptdatei: `tests/integration/test_multi_tenant_isolation.py:1-40` — verwendet echte DB, deckt CWE-639 (Auth-Bypass) und CWE-200 (Info-Exposure) ab. **Solider Kern**, aber:

→ Nur **EIN Integration-Test** für Tenant-Isolation auf 50+ Domain-Services. Die `tenant`-Erwähnungen in den 82 anderen Files sind meist `tenant_id=...` Fixtures, nicht echte Isolation-Tests.

---

## Coverage-Schätzung pro Modul

| Modul | Status | Begründung |
|-------|:------:|------------|
| Banking (Service-Layer) | **Gut** (70%) | 24 Test-Files, gute Domain-Abdeckung |
| Auth/Security | **Gut** (75%) | tests/security/, test_auth.py, dedicated suite |
| API-Endpoints | **Gut** (102 Tests) | breite API-Coverage |
| OCR-Backends | **Mittel** (50%) | Tests existieren, aber massiv gemockt (kein echter Modell-Run) |
| Compliance/GoBD | **Mittel** (50%) | Tests da, aber hash-chain/append-only fehlt |
| Frontend | **Lückenhaft** (15–20%) | 58 Tests, aber zentrale Module ungetestet |
| E2E (echter Browser) | **Lückenhaft** (~0%) | Kein Playwright, nur Mock-"E2E" |
| Imports (Email/Folder) | **Mittel** | `tests/unit/services/imports/` existiert, aber Pipeline-Tests fehlen |
| Privat/Kasse | **Lückenhaft** | Privat-Module hat ad-hoc-Tests, kein Backend-Test-Cluster |

---

## Top-3 Stärken

1. **Banking-Domain hervorragend abgedeckt**: 24 Service-Tests inkl. CSV-Parser, MT940, CAMT053, FinTS, Reconciliation, Skonto, Partial Payments. **Pilot-tauglich**.
2. **Multi-Tenant-Isolation hat dedicated Integration-Test** (`tests/integration/test_multi_tenant_isolation.py`) mit echter DB und CWE-Mapping — kritisch für SaaS-Pilot.
3. **Security-Suite breit aufgestellt**: 12 dedicated Security-Tests (XSS, CSRF, SSRF, CRLF, PII, Injection, Secrets, Lexware-PII, DATEV-Authz). Gut für Compliance-Sign-Off.

---

## Top-5 Lücken (kritisch für Pilot)

1. **Kein echtes E2E-Browser-Testing**. `tests/e2e/test_*.py` sind verkappte Integration-Tests mit Mocks. Es gibt kein Playwright-Setup, keine `*.spec.ts`. Pilot-Risiko: UI-Regressions werden erst beim Kunden gefunden.
2. **GoBD: hash_chain/append-only/tamper_detection ungetestet**. Compliance-Audit würde stocken — Test 11 zeigt: Audit-Trail-API ist getestet, aber die kryptographische Integrität (Hash-Chain) NICHT.
3. **Frontend ~80% ungetestet**. Dashboards, OCR-Review-UI, Upload-Wizard, Settings, Privat-Modul ohne Tests. Bei UI-Pilot verheerend.
4. **Massive Mock-Lastigkeit (1837 Mock-Imports)**. Echte SQL/Migration/RLS-Bugs werden in Unit-Tests nicht erkannt. Integration-Suite mit nur 53 Tests deckt nicht alle 50 Domain-Services ab.
5. **Test-Stagnation**: 0 Test-Commits in 14 Tagen, 0 neue Test-Files in 30 Tagen, **8 untracked Test-Files in git status**. Die Test-Disziplin hat in der heißen Phase nachgelassen, gerade vor Pilot.

---

## Note: Test-Pilot-Readiness — **6.0 / 10**

**Begründung**:
- **+** Solide Backend-Unit-Tests (678 Files), saubere pytest-Konfig, gute Domain-Strukturierung, dedicated Security & Multi-Tenant-Suiten.
- **+** CI mit pre-commit, ruff, mypy, Coverage-Workflow, separater DAST-Scan.
- **−** Mock-Anteil zu hoch (Ratio 2.4 Mock-Imports/File), echte E2E-Browser-Tests **fehlen komplett**.
- **−** Frontend-Coverage zu niedrig (15-20%) für UI-Pilot.
- **−** GoBD-Hash-Chain, Append-Only-Audit-Trail-Integrität — die GENAU kritischen Compliance-Tests fehlen.
- **−** Test-Stagnation in den letzten 4 Wochen, 8 untracked Tests = uncommitted Arbeit.

**Pilot-Empfehlung**: GO mit Auflagen — Vor Pilot-Start MUSS:
1. Playwright-E2E für Top-5-User-Journeys aufgesetzt werden (Login, Upload, OCR-Review, Banking-Reconciliation, Invoice-Detail).
2. GoBD-Hash-Chain-Test (`test_audit_chain_immutability`) geschrieben werden.
3. Die 8 untracked Test-Files committet & gegruened werden.
4. Coverage-Badge sichtbar im README aktiviert werden (Codecov / GitHub Actions Artifact).
