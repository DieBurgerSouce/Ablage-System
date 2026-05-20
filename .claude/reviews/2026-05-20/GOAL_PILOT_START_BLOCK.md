/goal Pilot-Start-Block: Sentry-DSN + 9 Critical Alerts triagieren

Ziel: Nach Squash-Merge pilot-v0.1.0 die letzten zwei User-blocking-Items aus `SPRINT_0_OPEN.md` schliessen. (1) Sentry-DSN scharf, (2) 9 Critical Alerts (seit Sprint-0 Tag 1 spammend) klassifizieren - echtes Problem vs False-Positive. KEINE neuen Features.

**S0 Pre-Check**: `git tag --list pilot-v0.1.0` nicht leer. `git log master -1 --format=%H` == Squash-Commit aus PR #8. `docker ps --filter name=ablage` zeigt Backend healthy. Sonst STOPP, erst GOAL_SQUASH_MERGE.

**S1 (5min, User-Action) — Sentry-DSN**:
1. <https://sentry.io> Projekt `ablage-system-pilot` (Python/FastAPI) anlegen, DSN kopieren.
2. `.env`: `SENTRY_DSN=https://...` und `ENVIRONMENT=production` (NICHT committen).
3. `docker-compose build backend && docker-compose up -d backend`.
4. Verify: `docker logs ablage-backend | grep sentry_initialized` matcht.
5. Verify: `curl http://localhost:8000/api/v1/this-does-not-exist` -> Error in Sentry-Inbox <30s.
6. `SPRINT_0_OPEN.md` G10-Checkboxen abhaken.

**S2 (15min) — Alert-Snapshot**: `mkdir -p docs/operations` und `docs/operations/alert-triage-2026-05-20.md` anlegen mit:
```
curl -s :9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing") | {alertname, severity:.labels.severity, activeAt, summary:.annotations.summary}'
docker ps --filter name=ablage --format "table {{.Names}}\t{{.Status}}"
docker-compose logs --tail=50 backend worker ocr-deepseek | grep -iE "error|fatal|down" | tail -30
```
Pro Alert Tabellenzeile: `| Alertname | echtes Problem? | Wurzelursache | Fix-Pfad |`.

**S3 (30-60min) — Klassifikation**: Bekannte False-Positives bereits in Commits `438f2486` (Slack-Spam-Sweep) und `6de2d89e` (Loki-Fix) adressiert - verify scharf. Verbleibend pro Alert:
- `OCRBackendDown` -> Container + `nvidia-smi`. Echt wenn down.
- `APIDown` -> `curl :8000/health`. `start_period` (180s -> 600s) noch zu kurz?
- `QdrantDown` -> Bearer-Token-File gemountet (siehe `438f2486`).
- `ServiceDown` -> Aggregat ueberlappend. Folge der anderen.
- `CeleryWorkerDownLong` -> `--pool=solo` inkompatibel mit `celery inspect ping`. HTTP-Check via `pgrep + /metrics`.
- `RedisReplicationBroken` -> Single-Node. Rule in `infrastructure/prometheus/rules/redis-alerts.yml` auskommentieren.
- `LokiCompactorNotRunning` -> echter Metric `loki_boltdb_shipper_compactor_running` (gefixt). Verify existiert.
- `HostHighSwapUsage` -> `free -h`. Echt = RAM/Concurrency-Tuning.
- `HostDiskSpaceLow` -> `df -h`. `docker system prune -a` braucht USER-APPROVAL (andere Projekte betroffen).

**S4 — Fix-Pfade**:
- Echte Probleme: GitHub-Issue ODER fix auf Branch `fix/pilot-alerts-2026-05-20` mit `fix(monitoring):` Commits.
- False-Positives: Rule-File anpassen, `curl -X POST :9090/-/reload` (2x bei Job-Changes, Lesson aus `438f2486`).
- Hartnaeckig: temporaere Silence 24h via `amtool silence add alertname=X --duration=24h`. Silence-ID + Ablauf dokumentieren.

**S5 Verifikation** (Definition of Done):
1. `curl -s :9090/api/v1/alerts | jq '[.data.alerts[]|select(.state=="firing")]|length'` = 0 (oder nur Bekannte mit Silence-ID).
2. Sentry-Inbox enthaelt Test-Error aus S1.5.
3. `docker logs ablage-backend | grep sentry_initialized` matcht.
4. `docs/operations/alert-triage-2026-05-20.md` committed mit 9 Klassifikationen.
5. `SPRINT_0_OPEN.md` G10 + P0b vollstaendig abgehakt.
6. `.claude/memory/PROJECT_STATUS.md` neuer Eintrag `| 2026-05-20 | Ops | Pilot-Start-Block geschlossen |`.

**Rollback**: Sentry-DSN aus .env entfernen + Backend rebuild. Rule-Aenderungen via `git revert`. Silences laufen automatisch ab.

**Anti-Pattern**: Sentry-DSN ins Repo committen (Secret-Leak). Pauschal silencen ohne Triage. `docker volume prune -f` ohne Inspektion (claude-memory/ollama-models). Production-Backend ohne SENTRY_DSN. `docker-compose restart` bei Config-Aenderungen statt `up -d --force-recreate` (Volume-Mount-Lesson aus G01).

**Out of Scope**: G06 Backup-Encryption, Phase C/D/E.
