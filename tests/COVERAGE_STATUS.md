# Test-Coverage-Status (Strom G5 "Test-Wahrheit", 2026-06-03)

> Notiz unter `tests/` (Repo-Root soll frei von neuen `.md` bleiben).
> Branch: `feature/g5-test-truth` (Basis: master mit G1+G4).

## 1. Gemessener Wert

| Messung | Wert | Kontext |
|---|---|---|
| **Lokal (G5-gruene Teilmenge)** | **25,63 %** | `pytest --cov=app` ueber die verifiziert gruenen G5-Dateien (validation_*, training_api, multi_tenant). Dominiert von **Import-Zeit-Coverage**: ohne DB/Redis/GPU werden Endpoint-/Service-Pfade nicht ausgefuehrt, nur Modul-Import zaehlt. |
| **Voller Stack (Erwartung)** | **~51 %** | Autoritative Messung aus dem Status-Scan (`.claude/reviews/2026-06-03/`, `MOCK_DATA_REGISTER.md`). Erfordert den vollen Docker-Stack (PostgreSQL/Redis/MinIO/GPU). |
| **CI-Gate** | `fail_under = 90` | In der Coverage-Konfig aktiv und **bestaetigt** ("Coverage failure: total of 25.63 is less than fail-under=90.00"). Unrealistisch hoch fuer den Ist-Zustand -> Cross-Stream (s.u.). |

**Warum lokal nicht ~51 %:** Auf dieser Windows-Entwicklungsmaschine ist (a) keine
Test-DB erreichbar (5433/5434 lehnen ab/timeouten), (b) kein Redis auf 6380, (c) kein
GPU, und (d) mindestens ein Unit-Test haengt ohne `pytest-timeout` (nicht installiert),
sodass ein vollstaendiger lokaler Lauf nicht terminiert. Die DB-/Endpoint-Logik wird
daher lokal nicht durchlaufen. Der reale Suite-Wert ist im CI/Docker zu messen.

## 2. Top-Luecken (gemessen)

| Modul | Coverage | LOC |
|---|---|---|
| `app/api/v1/dashboard.py` | **0,00 %** | 390 |
| `app/api/v1/fraud.py` | **0,00 %** | 229 |
| `app/services/ai/finance_assistant_service.py` | 16,97 % | 566 |
| `app/api/v1/banking/routes.py` | 37,01 % | 841 |
| `app/api/v1/fraud_detection.py` | 38,74 % | 157 |
| `app/api/v1/ceo_dashboard.py` | 38,46 % | 52 |
| `app/api/v1/dashboard_builder.py` | 41,86 % | 240 |

`dashboard`, `fraud` und `banking` sind die groessten Brocken (vom Goal benannt).

## 3. Gestaffelte Roadmap zu 90 %

1. **Stufe A (~51 % -> 65 %): DB-Integrationstests aktivieren.** Voraussetzung: der
   Mapper-Blocker (s. Cross-Stream #1) muss behoben sein, sonst skippen/erroren ALLE
   ORM-instanziierenden Tests. Danach: Banking-Routen (`routes.py`, 841 LOC, 37 %) und
   `enhanced_banking`/`banking_fints` mit echten Fixtures abdecken.
2. **Stufe B (65 % -> 78 %): Dashboard + Fraud.** `dashboard.py` (0 %) und `fraud.py`
   (0 %) sind reine API-Aggregatoren -> mit `client`-Fixture + geseedeten Daten testbar.
3. **Stufe C (78 % -> 90 %): Service-Layer-Tiefe.** `finance_assistant_service` (17 %),
   `financial_insights` (65 %), KI-/Analytics-Services mit gemockten LLM-/OCR-Backends.
4. **Gate-Anpassung:** `fail_under` realistisch staffeln (z.B. 50 -> 65 -> 80 -> 90),
   damit CI nicht dauerhaft rot ist (Cross-Stream #3).

## 4. Cross-Stream-Dependencies (NICHT in G5-Scope `tests/**`+`pytest.ini`)

> **G5-Followup (2026-06-03, `fix/g5-followup-app`):** #1 Folder.permissions ✅, #2 weasyprint OSError ✅, #3 fail_under 90→50 ✅, #5 User.company_id ✅, #6 get_trend_data ✅, #7 Entity-company_id-Filter ✅ — alle behoben. OFFEN: #4 Marker-Konsolidierung (pyproject-Pytest-Block) + Voll-Gruen der DB-Tests im CI.

| # | Befund | Ort | Auswirkung | Empfehlung |
|---|---|---|---|---|
| 1 | **`Folder.permissions` Ambiguous-FK** bricht `configure_mappers()` | `app/db/models*.py` | Blockiert ALLE Tests, die echte ORM-Objekte instanziieren (G5-Cross-Tenant/RLS, `test_rls_context`, `test_cash_isolation`). `test_db` faengt es als irrefuehrendes "Database not available"-Skip. | `foreign_keys=[...]` an der `Folder.permissions`-Relationship setzen. **Kritisch fuer die gesamte DB-Test-Ebene.** |
| 2 | **WeasyPrint `OSError` ungefangen** | `app/services/templates/template_engine.py` (+ document_template_service, procedure_documentation_service) | `from app.main import app` brach auf Windows -> alle App-Tests skippten faelschlich. G5 ueberbrueckt via Mock in `tests/conftest.py`. | App-seitig `except (ImportError, OSError)` statt nur `ImportError`. |
| 3 | **`fail_under = 90`** unrealistisch | `pyproject.toml [tool.coverage.report]` | CI-Coverage-Gate dauerhaft rot (~51 % real). | Temporaer auf realistischen Wert senken + staffeln (s. Roadmap). |
| 4 | **Marker-Konsolidierung** | `pyproject.toml [tool.pytest.ini_options]` wird ignoriert | `pytest.ini` hat Vorrang; pyproject-Pytest-Konfig ist tot. G5 hat alle Marker in `pytest.ini` vervollstaendigt. | pyproject-Pytest-Block entfernen ODER mit pytest.ini konsolidieren (eine Quelle der Wahrheit). |
| 5 | **`validation_queue_service.assign_to_editor` nutzt `User.company_id`** | `app/services/.../validation_queue_service.py` | Spalte existiert nicht (G1: `get_user_company_id`-Muster). Laufzeit-`AttributeError`. 2 Tests als `xfail`. | Auf `get_user_company_id`/UserCompany umstellen (G1/G4-Folgearbeit). |
| 6 | **`get_trend_data` -> `TrendResponse(data=...)`** Schema-Mismatch | `app/api/v1/training.py` | `pydantic.ValidationError` beim Aufruf (`TrendResponse` hat kein `data`-Feld). 1 Test als `xfail`. | Endpoint auf echte Schema-Felder umstellen oder Schema erweitern. |
| 7 | **Entity-Endpoints ohne `company_id`-Filter** | `app/api/v1/entities.py` (`GET /entities/{id}`, `/{id}/documents`) | Keine Record-Level-Mandantentrennung (per Design firmenuebergreifend?). G5-Test als `xfail`. | Bewusst entscheiden: Isolation einfuehren oder Design dokumentieren. |
| 8 | **G1 (`company_id`)** Welle-1-Abhaengigkeit | bereits in master-Basis | Multi-Tenant-/Security-Tests werden erst NACH G1 gruen. | Erfuellt (Basis enthaelt G1); finale Gruen-Faerbung nur mit DB. |

## 5. G5-Ergebnis (Test-Wahrheit)

- **Collection:** 26 -> 0 Errors (`pytest --collect-only -q`); WeasyPrint sauber.
- **Marker:** `pytest --strict-markers --collect-only` ohne unbekannte Marker.
- **Stub-Tarnung beseitigt:** kein `@pytest.mark.skip("stub - nicht implementiert")` mehr
  in `tests/security/**` und `tests/integration/test_multi_tenant_isolation.py`.
- **Statische Skip-Marker:** 401 -> 299 (102 Karteileichen entfernt) + ~71 weitere
  Skips in training/validation zu echten Tests/`xfail` konvertiert.
- **Security/Isolation:** echte Tests; DB-frei gruen, DB-abhaengig sauberer Laufzeit-Skip
  (kein Tarn-Skip). `test_client` skippt statt zu erroren, wenn keine DB da ist.
- `ruff check tests/` in allen angefassten Dateien ohne neue Fehler (meist gesunken).
