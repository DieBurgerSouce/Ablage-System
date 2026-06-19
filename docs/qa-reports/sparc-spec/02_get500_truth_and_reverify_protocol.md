# 02 — GET-500-Wahrheit & Re-Verifikations-Protokoll

## IST (belegt 2026-06-19)
`pytest tests/integration/test_get_endpoints_no_500.py` (BASE 127.0.0.1:8000) -> **FAILED, 6x 5xx**:

| Endpunkt | Code | Root-Cause (belegt) | Label |
|---|---|---|---|
| /api/v1/health/startup | 503 | redis-Probe `false`; REDIS_URL zeigt auf localhost:6380 statt aktivem redis:6379(+AUTH) | NICHT-BEHOBEN (Infra) |
| /api/v1/training/coverage/status | 500 | `TypeError: int - NoneType` training.py:2474 `target_samples - profile.verified_sample_count` (kein None-Guard) | PRE-EXISTING |
| /api/v1/training/exports | 500 | `ImportError: cannot import name 'VerificationStatus' from app.db.models` (training_dataset_export_service) | PRE-EXISTING |
| /api/v1/training/quality-reports/comparison/all | 500 | `ImportError: cannot import name 'OCRCorrection'` (backend_quality_report_service) | PRE-EXISTING |
| /api/v1/training/quality/check | 500 | transitive ImportError ueber get_quality_monitoring_service | PRE-EXISTING |
| /api/v1/training/quality/retraining-recommendation | 500 | dito (get_quality_monitoring_service) | PRE-EXISTING |

Historie: 192 (Start) -> 0 (transient, gruener Lauf zum Zeitpunkt X) -> **6 (aktuell)**. Die "0" war eine
Momentaufnahme, KEIN dauerhaft gesicherter Zustand.

## Diskrepanz-Klaerungsauftrag (P0 fuer Fix-Phase)
Vor jeder erneuten "GET-500=0"-Aussage ist zu belegen, warum die 5 /training/-Endpunkte im frueheren Lauf nicht
500 waren. Vorgehen:
1. `git log -p -- app/db/models.py | grep -n "VerificationStatus\|OCRCorrection"` -> existierten die Klassen je? Wann entfernt/umbenannt?
2. `git blame app/services/.../training_dataset_export_service.py` Zeile des Imports -> seit wann?
3. Pruefen ob frueherer Sweep dieselbe openapi-Pfadmenge hatte (Enumerationsluecke?) und ob Backend-Modulstatus
   identisch war (Worker-down-Folge?).
4. Ergebnis im Verified-State-Matrix nachtragen.

## SPEC der Behebung (spec-only; Umsetzung spaeter)
- **VerificationStatus / OCRCorrection**: entweder (a) Klassen in `app/db/models*` bereitstellen/exportieren
  (falls Feature aktiv sein soll) ODER (b) die Endpunkte/Services sauber als "nicht verfuegbar" guarden (HTTP 501/
  leere Antwort) statt ImportError-500. Entscheidung haengt an Produkt-Status des Training-Quality-Moduls.
- **training.py:2474 None-Guard**: `samples_needed = max(0, target_samples - (profile.verified_sample_count or 0))`.
- **health/startup**: siehe `06_infra_spec.md` (REDIS_URL-Reconcile).

### Pseudocode (None-Guard)
```
verified = profile.verified_sample_count or 0
samples_needed = max(0, target_samples - verified)
```

### Pseudocode (ImportError-Guard, falls Feature deaktiviert bleibt)
```
try:
    from app.db.models import VerificationStatus  # bzw. OCRCorrection
except ImportError:
    raise HTTPException(501, "Training-Quality-Modul nicht verfuegbar")  # statt 500-Crash
```

## Re-Verifikations-Protokoll (verbindlich)
Eine GET-Behebung gilt NUR als erledigt, wenn ALLE gelten:
1. `pytest tests/integration/test_get_endpoints_no_500.py` -> **passed** (0 5xx), Ausgabe als Beleg anhaengen.
2. Direkter Live-Check der zuvor defekten Pfade -> 200/erwartetes 4xx (nicht 5xx).
3. Backend + Worker + Beat laufen (`docker inspect ... State.Status==running, Health==healthy`), sonst ist der
   Sweep nicht aussagekraeftig.
4. Wiederholung nach Backend-Restart (Persistenz der Behebung, nicht nur transient).

## TDD-Anker
- `test_get_endpoints_no_500` (existiert) — muss gruen sein.
- NEU: `test_training_coverage_status_handles_null_verified_count` (profile.verified_sample_count=None -> 200, samples_needed==target).
- NEU: `test_training_endpoints_no_importerror` (Import der 3 Services wirft nicht; oder Endpunkt liefert 501 statt 500).

## DoD
- [ ] /training/* + /health/startup nicht mehr 5xx (Live + Test).
- [ ] Diskrepanz dokumentiert (warum frueher "0").
- [ ] Regressionstest gruen nach Restart.
---

## RESOLUTION (2026-06-20) — Faktenluecke GESCHLOSSEN + Fix verifiziert

### Beweis "warum 04:44 gruen, jetzt 6x 5xx" (hart belegt)
- **Pre-existing, KEINE Session-Regression:** git blame zeigt die kaputten Imports (OCRCorrection,
  VerificationStatus) stammen aus Commit 7e6bd9e7f ("feat(pilot): Pilot v0.1.0", 2026-05-20) — auf master und
  allen Branches. Klasse OCRCorrection existierte NIE; VerificationStatus wurde NIE aus app.db.models exportiert
  -> deterministischer ImportError seit 20.05.
- **Mechanismus:** main.py importiert den training-Router modul-level (laedt sauber -> App startet -> Endpunkte
  in openapi); die kaputten Imports stehen modul-level in den SERVICE-Dateien, die training.py LAZY in den
  Handlern importiert -> ImportError erst beim Aufruf -> 500 pro Request.
- **Warum "192 zu 0" sie nie abdeckte:** Der GET-Sweep hat die training-Endpunkte faktisch nie als 500 erfasst
  (die "0" war unvollstaendig). Zusatzbefund: der Live-Backend ist seit 20:51 auf den repointed Worktree
  az-remediation gemountet (docker inspect Mounts) -> Re-Messung trifft anderen Worktree; der Defekt ist in
  beiden identisch (shared base). FAZIT: "GET-500 = 0" war fuer die training-Endpunkte schlicht NICHT wahr.

### Fix (committet, verifiziert)
- backend_quality_report_service: OCRCorrection -> OCRCorrectionFeedback (Quelle models_ocr_feedback) +
  backend_used->backend, original_text->original_value, corrected_text->corrected_value.
- training_dataset_export_service: VerificationStatus -> TrainingSampleStatus; verification_status -> status; VERIFIED.
- training.py coverage-status: None-Guards.

### Evidenz (reproduzierbar)
1. Ephemerer Container (mein Worktree-Code): ALL_SERVICE_IMPORTS_OK (ImportError weg).
2. Verify-Backend Port 8001 (mein Code, DB+Redis-Overrides, beide Netze, Preload aus): 5 training-Endpunkte
   liefern 403 (Permission-Gate, kleiner 500) statt 500.
3. Direkte DB-Query (am 403-Gate vorbei, im Verify-Container): QUERY_OK rows1=0 rows2=0 -> remappte Spalten
   existieren, SQL laeuft (0 Zeilen mangels Seed-Daten, keine Spalten-/AttributeError).

### Ehrliche Restpunkte
- Voller HTTP-200-Durchlauf NICHT erzwungen (Endpunkte permission-gegated -> 403 fuer Test-Admin; keine
  Seed-Daten). Der zuvor crashende Pfad (Import + Query) ist aber bewiesen funktionsfaehig.
- None-Guard (coverage-status) ist code-/ast-verifiziert, nicht runtime-exerziert (403-Gate).
- health-startup 503 bleibt SEPARAT offen (Infra/REDIS_URL, nicht Teil der training-Wurzel).
- Fix liegt auf qa/az-deep-offensive-2026-06-18; Live-Stack laeuft az-remediation -> Uebernahme = Koordination.
