# Alert-Triage 2026-05-20 (P0b Pilot-Start-Block)

**Goal**: `.claude/reviews/2026-05-20/GOAL_PILOT_START_BLOCK.md`
**Trigger**: 9 Critical Alerts seit Sprint-0 Tag 1 spammend (siehe `SPRINT_0_OPEN.md`)
**Status**: TEMPLATE (zu befuellen sobald Docker-Stack laeuft)

## Snapshot-Befehle (nach Docker-Up ausfuehren)

**Vereinfacht via Skript**: `bash scripts/operations/pilot-start-block.sh <command>` (siehe `--help`).

```bash
# Empfohlener Workflow nach Docker-Up + Sentry-DSN in .env:
bash scripts/operations/pilot-start-block.sh status     # Snapshot
bash scripts/operations/pilot-start-block.sh reload     # Prometheus reload (2x)
bash scripts/operations/pilot-start-block.sh status     # Erneut pruefen
bash scripts/operations/pilot-start-block.sh sentry     # Sentry verify
bash scripts/operations/pilot-start-block.sh silences   # Copy-Paste Silences fuer NEEDS_VERIFY
bash scripts/operations/pilot-start-block.sh tbd        # Daten fuer die 4 echten TBDs
```

Manuell aequivalent (falls Skript nicht laeuft):

```bash
# 1. Aktuell feuernde Alerts
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing") | {alertname, severity:.labels.severity, activeAt, summary:.annotations.summary}' | tee firing-alerts.json

# 2. Container-Status
docker ps --filter "name=ablage" --format "table {{.Names}}\t{{.Status}}"

# 3. Error-Logs der letzten 50 Zeilen aus Kernservices
docker-compose logs --tail=50 backend worker ocr-deepseek 2>&1 | grep -iE "error|fatal|down" | tail -30

# 4. Prometheus Rule-Reload (lt. Lesson aus 438f2486 zweimal noetig!)
curl -X POST http://localhost:9090/-/reload && sleep 2 && curl -X POST http://localhost:9090/-/reload
```

## Pre-Analyse (Code-Stand verifiziert ohne Docker)

Bereits in fruheren Commits adressiert - bei Triage zuerst Rule-Reload pruefen:

| Alert | Rule-Status (Code) | Fix-Commit | Reload noetig? |
|-------|--------------------|------------|----------------|
| RedisReplicationBroken | ✅ Auskommentiert in `redis-alerts.yml:148-153` | 438f2486 | Ja, falls Prometheus alte Rule cached |
| LokiCompactorNotRunning | ✅ Metric umgestellt auf `loki_boltdb_shipper_compactor_running` in `loki-alerts.yml:71-72` | 6de2d89e | Ja, falls Prometheus alte Rule cached |
| QdrantDown | ✅ `bearer_token_file: /etc/prometheus/qdrant_metrics_token` in `prometheus.yml:125`. Token-File `infrastructure/prometheus/qdrant_metrics_token` lokal vorhanden + gitignored | 438f2486 | Nein, sollte direkt funktionieren |
| CeleryWorkerDownLong | ✅ Healthcheck umgestellt auf `curl /metrics + pgrep` in `docker-compose.yml:801`. Lesson aus 438f2486: `celery inspect ping` inkompatibel mit `--pool=solo` waehrend laufender Task | 438f2486 | Nein, Container-Restart noetig |
| APIDown | ✅ Backend-Healthcheck `start_period: 600s` (von 180s erhoeht) in `docker-compose.yml`. Sprint-0/G05. 10 Min Init-Zeit fuer 797 Services | (Sprint-0) | Nein, container restart noetig |
| BackendSentry | ✅ Backend hat `SENTRY_DSN: ${SENTRY_DSN:-}` env-var in `docker-compose.yml:552` (Sprint-0/G10). Initialisierung wartet auf DSN aus `.env` | (Sprint-0) | Nein, nur DSN in .env setzen |

## Klassifikations-Tabelle — ERGEBNIS (Triage durchgefuehrt 2026-05-20 16:00)

**Endstand: 0 firing Alerts.** `curl :9090/api/v1/alerts | jq '[.data.alerts[]|select(.state=="firing")]|length'` = 0.

Triage-Ablauf: Docker-Stack hochgefahren -> 7 firing Alerts (alle Cold-Start,
seit 15:34). Prometheus 2x reloaded. Backend-Crash-Loop entdeckt (RestartCount=10,
`NameError: ConfigDict`) -> Root-Cause-Fix in 4 Files. Backend force-recreated ->
healthy, RestartCount=0. Danach: 0 firing Alerts.

| # | Alertname | echtes Problem? | Wurzelursache | Aufloesung | Status |
|---|-----------|-----------------|---------------|------------|--------|
| 1 | OCRBackendDown | Folge von #4 (Backend-Crash) | Backend crashte -> OCR-Health-Endpoint nicht erreichbar | ConfigDict-Fix (Commit 0b1b391e) | RESOLVED |
| 2 | APIDown | **ECHT** - Backend-Crash-Loop | `NameError: ConfigDict` in cashflow_prediction.py:65 + 3 weitere Files (B3-Codemod-Restbestand). Backend RestartCount=10, ExitCode=0 | ConfigDict-Import nachgezogen (Commit 0b1b391e), Backend force-recreated -> healthy | RESOLVED |
| 3 | QdrantDown | False-Positive | bearer_token_file korrekt, Qdrant healthy | Selbst-aufgeloest nach Stack-Start + Reload | RESOLVED |
| 4 | ServiceDown | Folge von #2 | Aggregat-Rule, feuerte wegen Backend-Down | ConfigDict-Fix | RESOLVED |
| 5 | CeleryWorkerDownLong | False-Positive | Healthcheck-Fix (438f2486) griff, Worker healthy | Selbst-aufgeloest | RESOLVED |
| 6 | RedisReplicationBroken | False-Positive | Single-Node, Rule auskommentiert (redis-alerts.yml:148-153) | Prometheus-Reload | RESOLVED |
| 7 | LokiCompactorNotRunning | False-Positive | Metric-Name in 6de2d89e gefixt | Prometheus-Reload | RESOLVED |
| 8 | HostHighSwapUsage | False-Positive (Cold-Start) | RAM-Druck waehrend Stack-Hochfahren | Selbst-aufgeloest nach Stabilisierung | RESOLVED |
| 9 | HostDiskSpaceLow | False-Positive (Cold-Start) | kurzzeitig waehrend Image-Pull/Container-Start | Selbst-aufgeloest | RESOLVED |
| + | HostRebooted (info) | Erwartet | Docker-Stack-Neustart | Selbst-aufgeloest | RESOLVED |

**Kern-Erkenntnis**: Die "9 spammenden Alerts seit Sprint-0 Tag 1" waren zum
grossen Teil **Folge eines echten Backend-Crash-Loops** — `ConfigDict` ohne
Import (Pydantic-v2-Codemod B3 unvollstaendig). Kein bloesses Alert-Tuning-
Problem. Der Fix (Commit `0b1b391e`) behebt die Wurzel. Die 5 als NEEDS_VERIFY
vorklassifizierten Alerts waren tatsaechlich code-seitig schon gefixt und
brauchten nur den Prometheus-Reload.

## Fix-Pfad-Entscheidungsbaum

- **Echtes Problem**: GitHub-Issue ODER sofort fix auf Branch `fix/pilot-alerts-2026-05-20` mit `fix(monitoring):` Commits
- **False-Positive (Code bereits gefixt)**: `curl -X POST :9090/-/reload` (2x, dann Alerts pruefen)
- **False-Positive (Rule-Anpassung noetig)**: Rule-File in `infrastructure/prometheus/rules/*.yml` editieren, dann Reload
- **Hartnaeckig (Triage haengt, blockiert nicht kritisch)**: Temporaere Silence 24h via `amtool silence add alertname=X --duration=24h --comment="Pilot-Start Triage in Progress" --author=ben`. Silence-ID + Ablauf hier dokumentieren

## Silences-Log (aktive temporaere Silences)

| Datum | Alertname | Silence-ID | Ablauf | Begruendung |
|-------|-----------|------------|--------|-------------|
| - | - | - | - | (noch keine) |

## Definition of Done

- [x] Snapshot durchgefuehrt (7 firing Cold-Start-Alerts erfasst)
- [x] Klassifikations-Tabelle: alle 9 Alerts + HostRebooted mit Status RESOLVED
- [x] `curl -s :9090/api/v1/alerts | jq '[.data.alerts[]|select(.state=="firing")]|length'` = **0**
- [x] Root-Cause gefixt: ConfigDict-Import-Bug (Commit `0b1b391e`)
- [x] `SPRINT_0_OPEN.md` P0b-Checkliste abgehakt
- [x] `.claude/memory/PROJECT_STATUS.md` Eintrag ergaenzt

**Offen (bewusst vertagt)**: G10 Sentry-DSN — User-Entscheidung, kein Triage-Blocker. Backend laeuft mit `sentry_not_configured` (kein Crash, graceful).
