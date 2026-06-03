<!--
/goal-Prompt — Strom G4: Backend-Services/Workers/DB
WELLE 1 — laeuft parallel mit G1, G2, G3 (app/services + app/workers + app/db, disjunkt von app/api). Worktree/Branch: feature/g4-services-db
Empfehlung: G4 ZUERST mergen (liefert Service-Methoden/Modelle/Hooks, die G1 konsumiert).
Voraussetzung: G0-Settings (FINTS_*) + asn1crypto. Den Text ab "===" als /goal einfügen.
-->

=== GOAL G4 ===

Setze Remediation-Strom G4 (Backend-Services/Workers/DB) im Repo C:\Users\benfi\Ablage_System um. Ziel: gefaehrliche Mock-Pfade absichern, Fraud-/Compliance-Wahrheit herstellen, Celery sauber verdrahten, DB-Hygiene.

SCOPE-GRENZE (strikt einhalten): Du darfst NUR Dateien unter `app/services/**`, `app/workers/**` und `app/db/**` aendern. NICHT anfassen: `app/api/**`, `app/core/config.py`, `alembic/env.py`, die `User`-Klasse in `app/db/models.py`. Settings, die in `app/core/config.py` fehlen, liest du defensiv via `getattr(settings, 'NAME', default)`. `app/workers/celery_app.py` ist eine Bottleneck-Datei (3932 Zeilen) - mache dort NUR die exakt genannten, punktuellen/additiven Edits.

AUFGABEN (Reihenfolge: erst 1-3, dann 8-10 gebuendelt in celery_app.py, dann 4-7, dann 11, zuletzt 12):

1. M9 CRITICAL — `app/services/banking/enhanced_fints_service.py`: In `_sync_connection` (Z.~666-688) vor dem Aufruf von `_generate_mock_transactions` (Z.1187) einen Guard einbauen. Lies `getattr(settings, 'FINTS_ALLOW_MOCK_SYNC', False)`. Wenn False: `transactions=[]` setzen statt Mock zu generieren, strukturiert warnen (`fints_mock_sync_disabled`), damit KEIN Fake-Transaktion mehr `_auto_reconcile` (Z.683) oder die IncomingPayment-Benachrichtigung erreicht. `_generate_mock_transactions` fuer Tests erhalten. Kein PII loggen (keine IBAN/Betraege).

2. M7/M8 — `app/services/banking/auto_transaction_import_service.py`: `_fetch_fints_transactions` (Z.480) mit klarem Warn-Log `fints_auto_sync_outscoped` (bewusst OUTSCOPED, BaFin) versehen, leere Liste. `_fetch_psd2_transactions` (Z.434): NICHT mehr `access_token="placeholder"` an die echte PSD2-API senden — frueh per Guard abbrechen (`psd2_auto_sync_disabled`, leere Liste).

3. Beat-Schedule — `app/workers/celery_app.py` (Z.1828-1833 `banking-fints-sync-daily`): hinter `getattr(settings,'FINTS_AUTO_SYNC_ENABLED',False)` stellen bzw. konditional aus `beat_schedule` nehmen, mit Kommentar (M9-Risiko). Dict-Struktur sonst unveraendert.

4. M10 — `app/services/ai/fraud_detection_service.py`: `detect_self_approval` (Z.556) an `ApprovalRequest`/`ApprovalStep` (`app/db/models_privat_enterprise.py:931/1008`) anbinden (Approver vs. Requester/created_by); `analyze_audit_trail` (Z.623) an `AuditLog` (`app/db/models.py:842`) anbinden (Bulk-Deletes/Off-Hours, company_id-gefiltert). Wo echte Felder fehlen: ehrlicher Warn-Log + `confidence=0.0` statt faelschlich gruenem Ergebnis. `detect_unusual_approval_pattern` (Z.583) bleibt confidence=0.0 + Warn-Log bis echte Anbindung. Immer company_id-Filter, kein PII.

5. M11/M12/M13 — `app/services/accounting/gl_posting_service.py:414` hardcoded `confidence=0.85` durch echten Extraktions-Confidence ersetzen (sonst konservativer Default + Warn-Log). `app/services/ai/explainable_anomaly_service.py` (Z.402-415,459-480) hardcoded occurrences/similar_cases durch echte company_id-gefilterte COUNT-Queries ersetzen oder als 'geschaetzt' labeln. `app/services/ai/cashflow_prediction_service.py` (Z.563-599) Schaetzung transparent kennzeichnen.

6. M14 — `app/services/compliance/tsa_service.py` (Z.578-660): `_build_tsa_request`/`_parse_tsa_response` auf `asn1crypto` (bevorzugt: `asn1crypto.tsp.TimeStampReq/TimeStampResp`) oder `cryptography` umstellen. Bei fehlender Lib: `try/except ImportError` mit klarem deutschem Fehler `tsa_asn1_lib_missing` — KEIN stiller Fallback auf das nicht-konforme Handbau-ASN.1.

7. M15 — `app/services/compliance/gobd_service.py` (Z.250 Sequenz-Gap-Check; auch 409/567/799): echte Sequenz-Luecken-/Berechtigungs-/Aggregations-Checks (company_id-gefiltert) implementieren; wo vollstaendige Pruefung XL ist, Ergebnis ehrlich als WARNING/'teilgeprueft' statt PASSED.

8. Celery-Renames (4) in `app/workers/celery_app.py` — an BEIDEN Stellen (beat_schedule + task_routes): `cleanup_old_query_logs`->`cleanup_old_logs` (Z.1458+2786), `generate_zero_touch_stats`->`generate_zero_touch_statistics` (Z.1450+2781), `process_pending_uploads`->`process_pending_documents` (Z.1440+2777), `generate_all_recommendations`->`generate_smart_recommendations` (Z.989+2628). (Echte def-Namen sind verifiziert.)

9. Celery-Phantomtasks aufloesen: `refresh_query_suggestions` (Z.1463+2787) existiert NICHT in `nlq_tasks.py` -> Eintrag+route entfernen ODER auf `warm_cache` umbiegen. `smart_inbox_tasks.reactivate_snoozed_items` (Z.1486+2794) existiert NICHT -> entfernen ODER auf `app.workers.tasks.banking_tasks.reactivate_snoozed_tasks` (banking_tasks.py:1374) umbiegen. Entscheidung im Code-Kommentar dokumentieren; im Zweifel sauber entfernen.

10. 5 Task-Module sichtbar machen: `active_learning_tasks`, `anomaly_tasks`, `clustering_tasks`, `encryption_tasks`, `summary_tasks` zur `include=[]`-Liste (Z.260-369, additiv am Ende) UND zu `app/workers/tasks/__init__.py` (gleichem Import/Export-Muster folgen) hinzufuegen.

11. DB-Hygiene: NEU `app/db/all_models.py` als zentraler Aggregator anlegen, der ALLE `app/db/models_*`-Module per `import ... # noqa: F401` einbindet (keine Symbol-Re-Exports, um Zirkularitaet zu vermeiden). Verwaiste Modelle `models_categorization_feedback` und `models_knowledge_graph` entscheiden: gebraucht -> in `all_models.py` aufnehmen; tot -> deprecaten/entfernen mit Begruendung. Die Umstellung von `alembic/env.py` ist ausserhalb Scope -> nur als Cross-Stream-Dependency vermerken.

12. G1-Zuarbeit (on-demand): Falls G1 (Dashboard/Fraud-Alert) Service-Lesemethoden braucht, diese in der Service-Schicht bereitstellen (async, Type-Hints, company_id-Pflichtparameter) — KEINE API-Endpoints.

CONSTRAINTS: Alle user-facing Texte und Logs DEUTSCH (UTF-8 Umlaute). mypy strict, KEIN `Any`. KEIN PII-Logging (keine Kundennummern/IBANs/USt-IDs/Namen/Betraege — Rule 1/8). Multi-Tenant: alle Queries `company_id`-gefiltert. On-Premises (keine Cloud-Dienste). Bestehende Utils wiederverwenden (`structlog` logger, `safe_error_log`, vorhandene AsyncSession/select-Queries, `AlertCenterService`).

DEFINITION OF DONE: (a) Kein Mock-Sync loest mehr echte Reconciliation/Buchung aus (Unit-Test mit `FINTS_ALLOW_MOCK_SYNC=False` -> `reconciled==[]`). (b) ALLE `beat_schedule`-Task-Namen sind registriert (Verifikations-Skript unten). (c) Alle 5 Task-Module im Worker sichtbar. (d) TSA RFC-3161-konform via asn1crypto/cryptography. (e) `ruff check` + `mypy app/services app/workers app/db` sauber. (f) `pytest tests/unit/ -k 'fints or fraud or tsa or gobd'` gruen.

VERIFIKATION:
```
ruff check app/services app/workers app/db && mypy app/services app/workers app/db
python -c "from app.workers.celery_app import celery_app; reg=set(celery_app.tasks); print([e['task'] for e in celery_app.conf.beat_schedule.values() if e['task'] not in reg])"  # -> []
python -c "import app.db.all_models; from app.db.models import Base; print(len(Base.metadata.tables))"
pytest tests/unit/ -k "fints or fraud or tsa or gobd or celery" -v
```
Tests MUESSEN vor Commit gruen sein.
