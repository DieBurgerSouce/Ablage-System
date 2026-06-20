# Manifest Stream w3-tests (Branch `fix/w3-tests`, 2026-06-12)

Zone war `tests/**` + pytest.ini. Alle hier gelisteten Punkte sind ECHTE
App-Bugs, die beim Modernisieren der Tests verifiziert wurden (Code gelesen +
Mini-Repro). Fixes sind OUT-OF-ZONE und gehoeren zu w3-backend/w3-services.
Jeder Bug ist test-seitig mit `@pytest.mark.xfail(strict=True)` dokumentiert —
nach dem App-Fix schlaegt der jeweilige Test als XPASS(strict) an und der
Marker MUSS entfernt werden.

## Echte App-Bugs (xfail strict in fix/w3-tests)

| # | Datei (App) | Bug | Test (xfail strict) | Schwere |
|---|---|---|---|---|
| B1 | `app/services/compliance/autopilot_service.py` | `run_gdpr_check` baut Query mit `Document.metadata.isnot(None)` — `metadata` ist SQLAlchemys MetaData-Registry, echte Spalte heisst `document_metadata` → GDPR-Check crasht bei JEDEM Aufruf (AttributeError). Gleiches Muster in `_check_gobd` (`doc.metadata`). | `tests/unit/services/test_compliance_autopilot_service.py::test_run_gdpr_check` | HOCH (Compliance-Feature tot) |
| B2 | `app/services/fallback_chain.py` (~Z. 450) | Generischer `except`-Block: `logger.error(..., **safe_error_log(e), error_type=error_type)` — `safe_error_log` enthaelt `error_type` bereits → TypeError IM Exception-Handler → Backend-Exception propagiert, KEIN Fallback bei Backend-Fehlern (Kern-Resilienz tot). | `tests/integration/test_ocr_pipeline_integration.py::TestPipelineWorkflows::test_fallback_workflow` | HOCH (OCR-Resilienz) |
| B3 | `app/services/banking/parsers/mt940_parser.py` | Konto-Identifikation wird via `hasattr(statement, "account_id")` gelesen; die mt940-Lib liefert sie nur auf der Transactions-COLLECTION (`transactions.data['account_identification']`) → `account_iban` ist bei JEDEM MT940-Import None → IBAN-basiertes Konto-Matching in `ImportService.import_file` laeuft nie. | `tests/integration/test_banking_workflow.py::TestImportWorkflow::test_mt940_account_iban_extracted` | HOCH (Banking-Matching) |
| B4 | `app/services/einvoice/parser_service.py` (~Z. 321) | `_detect_format`: `version = metadata.get("version", "")` liefert None (Key existiert mit None bei UBL) → `version.startswith` AttributeError → `parse_xml` crasht fuer valide XRechnung-UBL-Dateien. Fix: `metadata.get("version") or ""`. | `tests/integration/test_einvoice_integration.py::TestXRechnungUBLFormat::*` (2 Tests) | HOCH (XRechnung-UBL = Pflichtformat) |
| B5 | `app/services/einvoice/mapping/zugferd_mapper.py` (`_extract_metadata`) | Nicht-XRechnung-CII wird pauschal als `version='2.3.3'` gemeldet; Guideline-URN (z. B. `urn:zugferd:2p0:en16931`) wird nicht ausgewertet, `guideline_id` fehlt → Versions-Misreporting fuer Alt-Dokumente. | `...::TestZUGFeRDVersionSupport::test_detect_zugferd_2_0_version` | MITTEL |
| B6 | `app/core/security_auth.py` (`get_password_hash`) | Roh-Passwort geht direkt an `bcrypt.hashpw`; bcrypt>=4 wirft bei >72 Bytes ValueError, `validate_password_strength` akzeptiert aber beliebige Laenge → Registrierung/PW-Aenderung mit langem Passwort = unbehandelter 500er. Fix: explizite Max-Laenge mit deutscher 422-Meldung ODER Pre-Hashing. | `tests/integration/test_user_lifecycle_integration.py::TestEdgeCases::test_very_long_password` | MITTEL |
| B7 | `app/services/external/handelsregister_service.py` (`get_company_details`) | `_validate_register_id` wird nur tief im Realpfad (`_fetch_details_from_portal`) gerufen; Mock-Pfad (DEFAULT, W1-011!) validiert NIE, und im Realpfad schluckt `except Exception` die ValueError → Mock-Fallback-Daten statt Validierungsfehler (CWE-918-Schutz unwirksam). Fix: Validierung an den Methodenanfang + ValueError nicht schlucken. | `...::TestHandelsregisterSecurity::test_*register_id*` (3 Tests) | MITTEL |
| B8 | `app/services/external/supplier_verification_service.py` (`_check_vies`/`_vies_format_fallback`) | Keine EU-Laendercode-Whitelist: bei VIES-Ausfall greift der Format-Fallback, dessen Default fuer unbekannte Codes (`XX`) nur `len(vat_number)>=2` prueft → `valid=True` fuer Nicht-EU-Codes. | `tests/.../test_vies_integration.py::test_invalid_format_wrong_country_code` | MITTEL |
| B9 | `app/services/external/enrichment_orchestrator.py` | (a) Sauberes Bundesanzeiger-Ergebnis (KEINE Insolvenz = Normalfall) liefert None → Quelle zaehlt nicht als befragt (`sources_queried`) und traegt nicht zur Confidence bei. (b) Confidence-Formel `+=0.5 pro Quelle, /len(sources)` → Maximum 0.5, nie 1.0. | `tests/unit/services/test_enrichment_service.py` (3 Tests) | NIEDRIG-MITTEL |

## Diagnose-Befunde ohne xfail (fuer w3-backend/Orchestrator)

- **Rate-Limiter maskiert lokal ALLES als 503**: `app/middleware/rate_limit.py`
  ist fail-closed (settings.RATE_LIMIT_FAIL_CLOSED) — ohne Redis antwortet
  JEDER TestClient-Request (client-IP `testclient`, nicht whitelisted) mit
  503. Lokale Diagnose der API-Suiten nur mit
  `RATE_LIMIT_FAIL_CLOSED=false RATE_LIMIT_FAIL_CLOSED_CRITICAL=false` moeglich.
- **CSRF-Middleware blockt Test-POSTs**: `bearer_token_bypass` greift nur mit
  `Authorization: Bearer`-Header; Tests mit dependency_overrides senden keinen
  → 403 fuer alle mutierenden Requests (gobd/datev/backup). Test-seitige
  Abhilfe: Dummy-Bearer-Header mitsenden (Auth ist ohnehin ueberschrieben).
- **E-Invoice-Validator 0 Findings** (`test_validate_missing_invoice_number`,
  `test_validate_missing_leitweg_id_xrechnung`): bewusst NICHT angefasst —
  laut W3-Scope macht das w3-backend (KOSIT-Abgleich W1-037).

## pytest.ini (Zone-Ausnahme, umgesetzt)

- `norecursedirs` inkl. `tests/_archived` (Defaults explizit aufgefuehrt).
- Marker `known_issue` registriert (Baseline-Abgrenzung; Orchestrator kann
  mit `-m "not known_issue"` neue Regressionen isolieren).
