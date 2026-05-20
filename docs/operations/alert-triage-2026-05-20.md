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

## Klassifikations-Tabelle (zu befuellen)

| # | Alertname | echtes Problem? | Wurzelursache | Fix-Pfad | Status |
|---|-----------|-----------------|---------------|----------|--------|
| 1 | OCRBackendDown | TBD | Container-Status + nvidia-smi | TBD | OPEN |
| 2 | APIDown | False-Positive (Code) | start_period bereits auf 600s in docker-compose.yml | Container-Restart + 10min warten | NEEDS_VERIFY |
| 3 | QdrantDown | False-Positive (Code) | bearer_token_file + Token-File vorhanden | Container-Restart Prometheus | NEEDS_VERIFY |
| 4 | ServiceDown | TBD | Aggregat - Folge der anderen? | Nach 1-3 nochmal pruefen | OPEN |
| 5 | CeleryWorkerDownLong | False-Positive (Code) | Healthcheck umgestellt auf curl/pgrep | Container-Restart Worker | NEEDS_VERIFY |
| 6 | RedisReplicationBroken | False-Positive (Code) | Single-Node, Rule auskommentiert | Reload Prometheus | NEEDS_VERIFY |
| 7 | LokiCompactorNotRunning | False-Positive (Code) | Metric-Name gefixt | Reload Prometheus | NEEDS_VERIFY |
| 8 | HostHighSwapUsage | TBD | `free -h` lokal | RAM erhoehen / Worker-Concurrency runter | OPEN |
| 9 | HostDiskSpaceLow | TBD | `df -h` - 107GB frei auf C: | `docker system prune -a` (USER-APPROVAL!) | OPEN |

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

- [ ] Snapshot-Befehle ausgefuehrt, `firing-alerts.json` hier oder im Repo committed
- [ ] Klassifikations-Tabelle: alle 9 Zeilen mit Status `FIXED`/`SILENCED`/`ACCEPTED` statt `OPEN`
- [ ] `curl -s :9090/api/v1/alerts | jq '[.data.alerts[]|select(.state=="firing")]|length'` = 0 (oder nur Eintraege mit Silence-ID)
- [ ] `SPRINT_0_OPEN.md` P0b-Checkliste abgehakt
- [ ] `.claude/memory/PROJECT_STATUS.md` Eintrag `| 2026-05-20 | Ops | Pilot-Start-Block geschlossen |`
