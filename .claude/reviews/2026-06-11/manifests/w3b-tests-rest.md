# Manifest Stream w3b-tests-rest (Branch `fix/w3b-tests-rest`, 2026-06-12)

Zone war `tests/**` (Queue: datev/backup/gobd-API-Tests + multi_tenant_migration-Fixture).
Out-of-zone-Wuensche fuer w3-backend/Orchestrator:

## Echte App-Luecke (xfail strict in fix/w3b-tests-rest)

| # | Datei (App) | Befund | Test (xfail strict) | Schwere |
|---|---|---|---|---|
| B10 | `app/api/schemas/datev.py` (`DATEVExportRequest`) | KEIN Validator fuer `period_to >= period_from`; auch Handler (`preview_export`/`export_buchungsstapel`) und `datev/export_service.py` pruefen den Zeitraum nicht (nur `steuerberater_package_service` tut das). Invertierter Zeitraum liefert still einen leeren Export statt 400/422. Fix: `model_validator` im Schema (deutsche Meldung), danach xfail-Marker entfernen. | `tests/integration/test_datev_api.py::TestDATEVExportAPI::test_export_preview_validates_date_range` | NIEDRIG-MITTEL (stille Fehlbedienung, kein Datenleck) |

## Diagnose-Notizen (kein App-Fix noetig, fuer die Nachwelt)

- **Archive-Router bindet `get_current_user`**, nicht `get_current_active_user`
  — der W3-Teilfix `1744ec0f3` zielte daneben (Tests blieben 403). In-zone
  korrigiert; falls der Router auf `get_current_active_user` vereinheitlicht
  werden soll, waere das eine w3-backend-Entscheidung (alle anderen Router
  nutzen active_user).
- `require_company`-Override muss ein Objekt mit `.id` liefern (Handler-IDOR
  nutzt `company.id`).
- `patch("...archive_service")` ersetzt das Service-Singleton durch MagicMock:
  jede im Handler awaited Methode muss explizit als `AsyncMock` gesetzt werden
  (Auto-Attribute sind nicht awaitable -> 500).
- Einheitliche Fehler-Response ist `{"fehler","nachricht","status_code",...}`
  — `response.json()["detail"]` existiert nicht mehr; alte Tests prueften
  deutsche Meldungen dadurch vakuum-gruen.
- Queue-Item (4) `test_multi_tenant_migration.py` war auf dem Basis-Branch
  bereits geloest (W0 `acc553d83`, `db`-Alias-Fixture); lokal verifiziert:
  17 saubere Skips ohne DB, die 2 PaymentService-strict-xfails sind intakt.
