<!--
/goal-Prompt — Strom G5: Test-Wahrheit
WELLE 2 — NACH G1 (+G4) ausführen. Tests duerfen in Welle 1 schon ENTWORFEN werden, gruen erst nach G1.
Worktree/Branch: feature/g5-test-truth (Basis: master mit gemergtem G1+G4)
Den Text ab "===" als /goal in eine Claude-Code-Session einfügen.
-->

=== GOAL G5 ===

Setze STROM G5 "Test-Wahrheit" um. Verwandle die Test-Suite von Schein-Gruen in belegbare Wahrheit: deaktivierte Security-/Isolations-Stubs zu echten Tests machen, Test-Rot abbauen, reale Coverage messen.

WICHTIGE SCOPE-GRENZE (strikt einhalten, wegen paralleler git-worktrees):
- Du darfst NUR `tests/**` und `pytest.ini` anfassen.
- NICHT anfassen: `app/**`, `frontend/**`, `pyproject.toml`, `.github/**`, `docker*`.
- Notwendige Aenderungen ausserhalb dieses Baums NICHT selbst durchfuehren, sondern in deinem Abschlussbericht als Cross-Stream-Dependency melden.

WELLEN-ABHAENGIGKEIT: Dieser Strom ist WELLE 2 und haengt HART an Strom G1 (company_id-Fix). Die Multi-Tenant-/Security-Tests werden erst NACH G1 gruen - vorher schlagen sie mit AttributeError/HTTP 500 fehl (genau das beweist Blocker B1). Entwirf die Tests jetzt, aber verifiziere finale Gruen-Faerbung erst nach G1-Merge.

CONSTRAINTS:
- ALLE user-facing Texte und Test-Begruendungen/Docstrings auf DEUTSCH.
- mypy strict / kein `Any` (gilt auch fuer Test-Code mit Type-Hints).
- KEIN PII-Logging in Tests (Rule 1/8): niemals echte IBAN/USt-ID/Kundennummer in Test-Output/Assertions ausgeben.
- Tests MUESSEN am Ende gruen sein (nach G1). Kein nacktes `@pytest.mark.skip` als Tarnung - statt Stub entweder echter Test, begruendeter `pytest.skip(reason=...)` zur Laufzeit (z.B. DB nicht verfuegbar) oder `xfail` mit technischer Begruendung, oder ersatzloses Loeschen.
- Keine neuen .md-Dateien im Repo-Root; Coverage-Notiz nur unter `tests/`.

AUFGABEN:

1. (CRITICAL, B4/B1) `tests/integration/test_multi_tenant_isolation.py`: Die 6 `@pytest.mark.skip('stub - nicht implementiert')`-Methoden zu echten Cross-Tenant-Tests machen:
   - Z.305 `test_cannot_access_other_company_documents`, Z.317 `..._entities`, Z.327 `..._invoices`: User aus Company A bekommt 403/404 (NIE 200) auf Ressourcen von Company B.
   - Z.413 `test_communication_hub_timeline_filters_sensitive_data`: keine rohe IBAN/USt-ID im Timeline-Output.
   - Z.460 `test_rls_prevents_cross_tenant_access` + Z.473 `test_transaction_rollback_on_authorization_error`: ueber `test_db_session`-Fixture (PostgreSQL); wenn DB fehlt -> `pytest.skip(reason="...")` zur Laufzeit, KEIN statisches mark.skip.
   - Nutze Fixtures `auth_headers_company_a`/`_company_b` (feste company_ids 000...001/002) aus `tests/security/conftest.py`. Vorbild: `tests/integration/test_rls_context.py`, `test_cash_isolation.py`.

2. (CRITICAL, B4) Security-Stubs in `tests/security/`:
   - `test_broken_auth.py`: `test_session_timeout` (Z.153) und `test_refresh_token_reuse_detection` (Z.389) implementieren oder als begruendetes `xfail` markieren.
   - `test_crlf_injection.py`: `test_no_injection_via_ws_header` (Z.369) umsetzen oder loeschen.
   - `test_pii_leakage.py`: `test_email_notification_sanitized` (Z.366) + `test_slack_notification_sanitized` (Z.372): assert dass Notification-Body keine IBAN/USt-ID/Kundennummer enthaelt (Rule 8). Vorbild: `tests/security/test_lexware_pii.py`.
   - Die uebrigen Tests in diesen Dateien sind bereits echt - sie muessen NACH G1 gruen laufen.

3. (B4) WeasyPrint-Collection-Errors entschaerfen: Die Test-Module, die `app.services.templates.template_engine` / `document_template_service` / `procedure_documentation_service` importieren (`tests/unit/services/test_template_engine_service.py`, `tests/unit/services/notification/test_template_engine.py`, `..._send.py` und ggf. weitere), crashen auf Windows bei der Collection, weil der app-seitige `try/except ImportError` den `OSError` (fehlendes libgobject) nicht faengt. Fix testseitig: `pytest.importorskip("weasyprint", reason="libgobject auf Windows nicht verfuegbar")` am Modulanfang ODER `try/except (ImportError, OSError)` um den App-Import mit `pytestmark = pytest.mark.skip(...)`. Den sauberen app-Fix (`except (ImportError, OSError)`) als Cross-Stream-Dependency melden, NICHT selbst in app/** aendern. Vorbild fuer optional-skip: `tests/gpu/conftest.py`.

4. (Test-Rot) Top-Drift-Dateien entrosten - pro Datei erst pruefen ob Endpoint/Service in `app/api` noch existiert (nur lesen!), dann:
   - `tests/unit/api/test_contracts_api.py` (49 skip 'stub'), `test_invoices_api.py` (26 'stub'), `test_document_chains_api.py` (17 'stub'): echte Tests gegen aktuelle Signaturen schreiben oder Karteileichen loeschen.
   - `tests/unit/api/test_training_api.py` (27, 'MagicMock dont validate with Pydantic') und `tests/unit/services/test_validation_*.py`: MagicMock durch valide Pydantic-Instanzen / dict-Payloads ersetzen.
   - Nutze `tests/fixtures/factories.py` und bereits gruene Nachbar-Tests (`test_documents_api.py`) als Vorbild. Ziel: Skip-Zahl deutlich runter, keine Karteileichen.

5. (Marker) `pytest.ini`: Marker `datev`, `services`, `pipeline`, `gdpr`, `banking` unter `[pytest] markers` registrieren (`--strict-markers` ist aktiv). ACHTUNG: `pytest.ini` hat Vorrang vor `pyproject.toml [tool.pytest.ini_options]` - pruefe welche real genutzten Marker (asyncio, database, redis, ...) in pytest.ini fehlen und ergaenze sie, damit `--strict-markers` nicht bei bestehenden Tests bricht. `pyproject.toml` NICHT aendern (out of scope) - falls Konsolidierung dort noetig, als Dependency melden.

6. (Coverage) NACH G1 und nach Aufgaben 1-5: `pytest --cov=app --cov-report=term-missing --cov-report=xml` ueber die gruene Suite laufen lassen. Realen Prozentwert (erwartet ~51%) und Top-Luecken (app/api/v1/dashboard, fraud, banking) in einer kurzen DEUTSCHEN Notiz unter `tests/` (z.B. `tests/COVERAGE_STATUS.md`) dokumentieren, plus gestaffelte Roadmap zu 90%. Da `fail_under=90` in pyproject.toml steht (out of scope), die temporaere realistische Gate-Absenkung als Cross-Stream-Dependency an den CI-/pyproject-Strom melden.

DEFINITION OF DONE:
- `pytest tests/security/ tests/integration/test_multi_tenant_isolation.py -v` laeuft OHNE 'stub - nicht implementiert'-Skips; alle Security-/Isolationstests laufen (nicht skip) und sind gruen NACH G1 (RLS-Tests duerfen mit Laufzeit-Skip wegen fehlender DB uebersprungen werden).
- `pytest --collect-only -q` produziert 0 Collection-Errors (WeasyPrint sauber).
- `pytest --strict-markers --collect-only` meldet keine unbekannten Marker.
- Skip-Gesamtzahl deutlich unter Baseline (Baseline: 500 Skips in 95 Dateien; insbesondere contracts/training/invoices reduziert).
- Realer Coverage-Wert gemessen und unter `tests/` dokumentiert.
- `ruff check tests/` ohne neue Fehler.
- Abschlussbericht listet alle Cross-Stream-Dependencies (G1, app-WeasyPrint-Fix, pyproject fail_under, Marker-Konsolidierung).
