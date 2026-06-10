# Schemathesis-Baseline-Lauf (W2 / Plan-Item 0d)

**Datum:** 2026-06-10
**Setup:** `make api-fuzz` gegen lokalen Test-Stack (docker-compose.test.yml), Check `not_a_server_error`, max-examples 25, DELETE ausgeschlossen
**Umfang:** 1163 generierte Testfälle über 47 Operationen in 112 s — **Failure-Limit (10) erreicht, es gibt vermutlich weitere Funde.**
**Hinweis Coverage:** 2767 von 2814 Operationen wurden geskippt („No examples in schema") — Response-Models/Examples nachziehen erhöht die Abdeckung massiv.

## Funde: 10 reproduzierbare 5xx-Server-Errors

Alle mit Admin-Token reproduzierbar (Token/Cookies aus Repro entfernt):

| # | Endpoint | Auslöser |
|---|----------|----------|
| 1 | `POST /api/v1/accounting/fx-gain-loss/calculate` | Denormal-Float `5e-324` als Kurs, Währung `"000"` |
| 2 | `POST /api/v1/activity/filter` | Leerer Body `{}` |
| 3 | `POST /api/v1/admin/integration-sync/datev/writeback` | Leere Strings in Pflichtfeldern (`document_id: ""`, `betrag: false`) |
| 4 | `POST /api/v1/admin/jobs/queue/clear?status=AAA` | Ungültiger Status-Enum-Wert |
| 5 | `POST /api/v1/admin/rate-limits/bulk/reset` | UUID-Liste mit nicht existenter ID |
| 6 | `POST /api/v1/admin/roles` | 49-Zeichen-Name / Mini-Displayname |
| 7 | `POST /api/v1/admin/system/gpu/clear-cache` | Aufruf ohne GPU-Kontext |
| 8 | `POST /api/v1/ai/contracts/analyze` | Minimal-Text `"00"` |
| 9 | `POST /api/v1/cashflow-prediction/scenario` | Szenario mit fremder/nicht existenter `entity_id` |
| 10 | `POST /api/v1/lifecycle/destruction-protocols` | (siehe Log) |

Repro-Kommandos: vollständige `curl`-Befehle im Lauf-Log (lokal `.claude/cache/schemathesis_run1.log`, Seed `93957217039113324990469434691854993135`).

## Warnungen (Hinweise auf Spec-Drift)

- 8 Operationen liefern auf valide generierte Daten durchgehend 404 → fehlende Seed-Abdeckung oder tote Endpoints.
- 17 Operationen lehnen generierte Daten fast immer ab → OpenAPI-Constraints strenger dokumentieren (Schema ↔ Validierung driftet).

## Nächste Schritte

1. Die 10 Funde triagieren (vermutlich Cluster: fehlende Input-Validierung → 422 statt 500, fehlende Not-Found-Behandlung → 404 statt 500).
2. Nach Triage-Fixes: `MAX_FAILURES` erhöhen und erneut laufen lassen (Funde 11+).
3. Response-Models/Examples ergänzen → Coverage von 47 auf einen relevanten Teil der 2814 Operationen heben.
4. Nach 2 Wochen stabilem Nightly: `continue-on-error` in `api-fuzz.yml` entfernen (blocking).
