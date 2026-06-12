# Integration-Failures Triage (W1-009)

**Datum:** 2026-06-12 (Stream w2-tests, Branch `fix/w2-tests`)
**Basis:** Snapshot `.claude/cache/w1_branch_failures.txt` (196 Eintraege: 147 FAILED + 49 ERROR, bitidentisch zu master laut W1 1a)
**Methode:** Statische Analyse aller betroffenen Dateien + lokale Reproduktion mit Host-Python 3.12 (Mock-basierte Dateien; DB-gebundene mit bewusst unerreichbarer `TEST_DATABASE_URL`, KEIN Stack-Kontakt). Lokale Reproduktion deckte mehrere Cluster bitidentisch (Anzahl + Fehlerart).

## Querschnitts-Befunde (betreffen mehrere Dateien)

1. **conftest-Bug `app`-Shadowing (GEFIXT, fix/w2-tests):** `import app.db.bpmn_models.bpmn` in `tests/conftest.py` ueberschrieb den Namen `app` (FastAPI-Instanz) mit dem Paket-Modul → `client`/`async_client` erhielten ein Modul → `TypeError: 'module' object is not callable`. Fix: `importlib.import_module(...)`. Behebt direkt 3 Failures in `test_documents_api.py` (lokal verifiziert) und entschaerft `test_datev_connect_api`/`test_tunes_upload_flow` bis zur naechsten Drift-Ebene.
2. **Hardcodierte Test-DB-URLs (GEFIXT, fix/w2-tests):** 5 Dateien ignorierten `TEST_DATABASE_URL` (`postgres:postgres@localhost:5433` fest verdrahtet) → 49 ERRORs im Container. Jetzt env-gesteuert + sauberes Skip bei unerreichbarer DB.
3. **Latenter App-Bug (out of zone, NICHT gefixt):** `app/db/database.py` uebergibt `poolclass=QueuePool` an `create_async_engine`. SQLAlchemy >= 2.0.30 wirft dafuer `ArgumentError` beim Import von `app.api.dependencies` (DatabaseManager auf Modulebene). Container pinnt 2.0.25 (toleriert) — Upgrade-Blocker. Test-seitiger Kompat-Shim in `tests/conftest.py` dokumentiert den noetigen App-Fix (`AsyncAdaptedQueuePool`).
4. **DB-Health-Gate → 503:** API-Tests mit gemockten Services (gobd/datev/backup) benoetigen trotzdem eine erreichbare DB, sonst antwortet die App pauschal 503 — exakte Drift-Diagnose nur im Container moeglich.

## Triage-Tabelle

| Datei | Cluster | Anforderung | Verdacht | Empfehlung |
|---|---|---|---|---|
| test_ocr_pipeline_integration.py | 23 F + 5 E | keine (reine Mocks) | Spec-Drift: Tests gegen alte Service-API (`ConfidenceService.determine_confidence_level/make_quality_decision`, `FallbackChain.select_backend/get_backend_priority` existieren nicht mehr; `FallbackResult`/`ConfidenceMetrics`/`BackendConfig`-Signaturen geaendert). Lokal bitidentisch reproduziert (23F+5E) | Tests gegen aktuelle Pipeline-API modernisieren (groessere Rewrite-Einheit) oder archivieren; kein App-Bug |
| test_autonomous_trust_upgrades.py | 17 F | keine (Mocks) | Patch-Ziel-Drift: `patch("...autonomous_trust_tasks.asyncio...")` — Modul nutzt kein modulglobales `asyncio` mehr. Lokal bitidentisch (17F) | Patch-Ziele auf aktuelle Modul-Interna umstellen; mechanischer Test-Fix |
| test_index_verification.py | 17 E | echte DB auf alembic-Head (Indizes/Constraints stammen aus Migrationen, NICHT aus create_all) | Fixture `db_session` existierte nirgends → ERROR in Setup (gleiches Muster wie acc553d8) | **GEFIXT**: sync `db_session`-Fixture in `tests/integration/conftest.py` (TEST_DATABASE_URL, Skip ohne DB). Im Container gegen migrierte DB laufen lassen — gegen create_all-DB schlagen migrations-eigene Indizes ehrlich fehl |
| test_gobd_api.py | 16 F | **KORREKTUR (W3, 2026-06-12): KEIN DB-Gate.** Lokales 503 kommt vom fail-closed RATE-LIMITER (Redis unerreichbar; TestClient-IP `testclient` nicht whitelisted). Mit `RATE_LIMIT_FAIL_CLOSED=false` lokal voll diagnostizierbar | 3 Schichten: (1) Fixture ueberschrieb `get_current_user`, Router verlangt `get_current_active_user` → **GEFIXT (fix/w3-tests, 1744ec0f3)**; (2) POSTs scheitern an CSRF-Middleware-403 (kein `Authorization: Bearer`-Header → kein bearer_bypass); (3) danach Service-Mock-Drift (6x 500) + Inhalts-Drift (Retention-Kategorie 'invoice' fehlt) | (2) test-seitig: Dummy-Bearer-Header in Fixtures; (3) einzeln nacharbeiten. Diagnose-Lauf: `DEBUG=true RATE_LIMIT_FAIL_CLOSED=false RATE_LIMIT_FAIL_CLOSED_CRITICAL=false` |
| test_datev_api.py | 16 F | **KORREKTUR (W3): KEIN DB-Gate**, gleiches Rate-Limiter-503 wie gobd | Mit fail-open Rate-Limiter lokal: 401 statt 422/201/204 — `patch('app.api.dependencies.get_current_active_user')` wirkt NICHT auf Depends-Referenzen (beim Import gebunden); Tests brauchen `app.dependency_overrides` (Muster siehe test_tunes_upload_flow-Fix in fix/w3-tests) | Patches auf dependency_overrides umstellen; 401/403-Konvention: 403 BLEIBT (Nutzer-Entscheidung W3) — Tests entsprechend |
| test_vision_2_features_db.py | 15 F | keine (Mocks) | Konstruktor-Drift: alle 4 Services (CommunicationHub/IndustryBenchmark/AIMentor/LiquidityScenario) verlangen jetzt 1 zusaetzliches Pflichtargument (company_id-Rollout G1). Lokal bitidentisch (15F) | Tests auf neue Signaturen heben; mechanisch, aber 15 Stellen |
| test_jobs_admin_e2e.py | 13 E | echte DB + App | Hardcodierte DB-URL ignorierte TEST_DATABASE_URL → Connection-ERROR | **GEFIXT** (env-Honor + Skip). Im Container erneut laufen lassen |
| test_user_lifecycle_integration.py | 8 F | teils Redis/DB (503-Pfade), teils keine | Mischcluster: veraltete Patch-Ziele auf `app.core.security` (blacklist-Interna), 503-vs-401 (DB-Gate), bcrypt-72-Byte-ValueError (passlib→bcrypt-Drift, `test_very_long_password`), RoleManagement-Assert | Einzeln nacharbeiten; bcrypt-Verhalten ist eine echte Verhaltensfrage (lange Passwoerter muessen sauber abgelehnt/truncated werden — Backend pruefen) |
| test_cash_isolation.py | 8 E | echte DB | Hardcodierte DB-URL | **GEFIXT** (env-Honor + Skip) |
| test_einvoice_integration.py | 7 F | keine (echte Services) | Gemischt: XML-Deklarations-Brittleness (`'` vs `"`), ZUGFeRD-Version 2.3.3 vs erwartete 2.0, Validator liefert 0 Findings (Severity-/Rule-Drift), UBL-Detection `None` | Tests an aktuelle Generator-/Validator-Realitaet anpassen; Validator-0-Findings koennte echte Regression sein → gegen KOSIT-Thema (W1-037) gegenpruefen |
| test_backup_api.py | 7 F | **KORREKTUR (W3): KEIN DB-Gate**, Rate-Limiter-503 wie gobd | Mit fail-open Rate-Limiter lokal: POSTs (postgres/full/retention/sync) liefern 401 — Endpoints haben neben `get_current_superuser` offenbar weitere/abweichende Auth-Dependency bzw. CSRF-403/401-Mix; plus deutsche-Message-Assertions erst danach pruefbar | Fixture um Bearer-Dummy-Header + korrektes Override-Ziel ergaenzen, dann Message-Drift einzeln |
| test_rate_limit_e2e.py | 7 E | echte DB + Redis | Hardcodierte DB-/Redis-URLs | **GEFIXT** (env-Honor TEST_DATABASE_URL/TEST_REDIS_URL + Skip + Redis-Ping) |
| test_cash_real_db.py | 7 E | echte DB | Hardcodierte DB-URL | **GEFIXT** (env-Honor + Skip) |
| test_ocr_backends_complete.py | 6 F | keine (german_validator direkt) | API-Drift: GOT-OCR `_postprocess_german` liefert jetzt dict statt Objekt mit `.text` | Tests auf dict-API umstellen; mechanisch |
| test_personal_api_security.py | 4 F | eigene Mini-App (keine echte DB) | Container: 4 spezifische Drifts (IBAN/BIC-invalid-Validierung, expired-token-401, Rate-Limit-Header) | Einzeln nacharbeiten; Input-Validierungs-Failures koennten echte Luecken sein (CWE-relevant) → zuerst Backend pruefen |
| test_cash_concurrent.py | 4 E | echte DB | Hardcodierte DB-URL | **GEFIXT** (env-Honor + Skip) |
| test_notification_rules.py | 3 F | keine | `RuleConditionMatcher`-Semantik-Drift (gt-Operator False, and/or invertiert) — Verdacht Feldnamen-/Schema-Drift in Conditions ODER echter Engine-Bug | Matcher-Implementierung gegen Tests stellen; wenn Engine falsch matcht → echter Bug (Benachrichtigungen!) |
| test_documents_api.py | 3 F | keine | conftest `app`-Shadowing (s.o.) | **GEFIXT** via conftest; lokal 3/3 gruen |
| test_banking_workflow.py | 3 F | keine (Mocks) | MT940-Parser liefert `account=None` (Parser- oder Fixture-Drift) + `ImportService.import_file()`-Signatur-Drift | Signatur-Drift = Test-Fix; MT940-None zuerst gegen Parser pruefen (potenziell echter Bug) |
| test_tunes_upload_flow.py | 1 F | keine | Test mockt `get_current_superuser` via `patch()` statt `app.dependency_overrides` → 403 (nach conftest-Fix sichtbar gewordene eigentliche Ursache) | Test auf dependency_overrides umstellen |
| test_surya_docling_pipeline.py | 1 F | keine | Backend-Auswahl-Drift (`test_pdf_selects_surya_enhanced`) | Auswahl-Logik im BackendManager pruefen, Test anpassen |
| test_lineage_api.py | 1 F | keine | Test erwartete ASCII-Transliteration, App liefert korrekte Umlaute | **GEFIXT** (Assertion auf echte Umlaute, Critical Rule 2) |
| test_folder_api.py | 1 F | keine | dito (`geschaeftlich` vs `geschäftlich`) | **GEFIXT** |
| test_erp_sync.py | 1 F | keine | Task-Namen-Drift: registriert `app.workers.tasks...sync_connection`, Test erwartet Kurzname `erp.sync_connection` | Klaeren welche Namenskonvention gilt (Beat nutzt teils explizite Kurznamen); dann Test ODER Task-Registrierung angleichen |
| test_datev_connect_api.py | 1 F | keine | 403 statt 401 bei fehlender Auth (HTTPBearer `auto_error`-Default?) — API-Konventionsfrage, Repo-Standard ist 401 | Backend-Konvention entscheiden (401 vs 403) — NICHT test-seitig aufweichen |
| test_alembic_migrations.py | 1 F | keine (liest Dateinamen) | 10 Legacy-Migrationsnamen (019b-031b-Serie + streckengeschaeft_NNN) ueberschritten Toleranz 5 | **GEFIXT**: Legacy-Serien explizit gewhitelistet, Toleranz auf 0 verschaerft (neue Migrationen muessen NNN_ folgen) |

## W3-Nachtrag (2026-06-12, Branch `fix/w3-tests`, Stream w3-tests)

- **~85 Spec-Drift-Tests modernisiert** (alle lokal gruen, Host-Python 3.12):
  ocr_pipeline (33), autonomous_trust (20), vision_2 (16), ocr_backends (6),
  einvoice-Drift-Teile, banking_workflow, tunes (inkl. expliziter 403-ohne-
  Auth-Test, Konvention bestaetigt), user_lifecycle (100 passed, 1 xfail).
- **Pre-existing Unit-Baseline (40) triagiert+behoben**: daily_insights (15,
  komplett neu gegen echten Vertrag), jsonb_validation (7), compliance_
  autopilot (2), external/enrichment (16).
- **9 ECHTE App-Bugs** verifiziert und als `xfail(strict=True)` dokumentiert —
  Details + Fix-Hinweise: `manifests/w3-tests.md` (u. a. GDPR-Check tot
  [Document.metadata], FallbackChain-Fallback tot [doppeltes error_type-Kwarg],
  MT940-IBAN immer None, XRechnung-UBL-Parser crasht, bcrypt-72-Byte-500er).
- **Querschnitts-Korrektur**: Das lokale "DB-503-Gate" war in Wahrheit der
  fail-closed Rate-Limiter (Redis); Diagnose-Runs brauchen
  `RATE_LIMIT_FAIL_CLOSED=false`. CSRF-Middleware blockt Test-POSTs ohne
  Bearer-Dummy-Header.
- **pytest.ini**: `norecursedirs` + `tests/_archived`; Marker `known_issue`
  registriert.

## Bilanz

- **Direkt gefixt (fix/w2-tests):** 49 ERRORs (hardcoded URLs + fehlende Fixture) in lauffaehig/skip-sauber ueberfuehrt; 3+1+1+1 FAILED-Tests gruen (documents_api, lineage, folder, alembic-naming); conftest-`app`-Shadowing behoben (wirkt repo-weit auf client/async_client-Tests).
- **Mechanische Test-Modernisierung (separater Folgeauftrag, ~85 Tests):** ocr_pipeline (28), autonomous_trust (17), vision_2 (15), ocr_backends (6), einvoice (7), banking_workflow (2/3), tunes (1), user_lifecycle (Teil).
- **Container-Diagnose noetig (~39):** gobd (16), datev (16), backup (7) — lokal maskiert das DB-503-Gate die echte Ursache.
- **Potenzielle ECHTE Bugs (vorrangig pruefen):** RuleConditionMatcher-Semantik (Notifications), MT940-Parser account=None, E-Invoice-Validator 0 Findings, bcrypt-72-Byte-Handling, 401/403-Inkonsistenz, QueuePool-async (SQLAlchemy-Upgrade-Blocker).
- **Empfehlung Marker:** Fuer die verbleibenden bekannten Failures `@pytest.mark.known_issue` (in pytest.ini registrieren) statt Skip, damit neue Regressionen von der Baseline unterscheidbar bleiben.
