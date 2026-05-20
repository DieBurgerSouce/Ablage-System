# 00f - Infrastructure Audit (Solo-DevOps Pilot-Reality-Check)

Stand: 2026-05-03. Branch: feature/ocr-performance.
Brutale Bewertung der Infrastruktur fuer den Pilot mit Ben als Solo-Operator.

---

## 1. docker-compose.yml (1581 Zeilen, 32 Services)

**Services**: postgres, pgbouncer, redis, redis-replica, redis-sentinel-1/2/3, minio, clamav,
qdrant, reranker, einvoice-mustang, backend, worker, worker-cpu, beat, frontend, prometheus,
grafana, loki, alertmanager, jaeger, postgres_exporter, redis_exporter, promtail, vault,
dcgm-exporter, node-exporter (28 Hauptservices + 4 Sentinel/Replica).

**Healthchecks**: 25 von 28 Services besitzen `healthcheck:`. Fehlend: `redis-sentinel-1/2/3`,
`reranker`. Das ist akzeptabel, weil Sentinels Redis-internes Quorum sprechen, aber Reranker
sollte einen `/healthz` haben.

**Ressourcen-Limits**: ALLE Services haben `deploy.resources.limits` und `reservations`. Das
ist ueberdurchschnittlich gut. Konkrete Werte:

- postgres: 2 CPU / 4 GB RAM (limit) -- **knapp** bei pgvector + 500 Docs/h
- redis: 1 CPU / 5 GB RAM (Master) + Replica 5 GB
- backend: 4 CPU / 8 GB RAM
- worker (GPU): 4 CPU / 16 GB RAM, GPU `driver: nvidia` `capabilities: [gpu]`
- worker-cpu: 4 CPU / 8 GB RAM
- clamav: 2 CPU / 4 GB RAM
- qdrant: 2 CPU / 4 GB RAM
- prometheus/grafana/loki: jeweils 1-2 GB

**Aber**: Es gibt KEIN GPU-Memory-Limit (nur Container-RAM). Wenn DeepSeek 12 GB VRAM zieht und
Surya parallel laeuft -> OOM-Crash. Code-seitig existiert `gpu_memory_guard()` Pattern (laut
CLAUDE.md), aber compose-seitig keine Schranke. **VRAM-Konkurrenz** zwischen worker (DeepSeek)
und Reranker (BGE-Reranker) ist nicht durchgesetzt.

**Sanity-Check**: 28 Services + Postgres-HA + Redis-HA + ClamAV + Qdrant + Vault + komplettes
Monitoring auf einer einzigen RTX-4080-Box -- das ist realistisch fuer 5-10 Pilotkunden, aber
**kein Headroom** fuer 100 Kunden. Resource-Budget summiert: ~32 CPU-Limits, ~80 GB RAM-Limits.
Eine Workstation mit 64 GB RAM faehrt unter Volllast in den Swap.

---

## 2. GitHub Actions (18 Workflows, 1 README)

Inventar (1-Satz pro File):

- `ci.yml` -- Lint, Typecheck, Unit-Tests, Coverage, Docker-Build-Smoke.
- `coverage.yml` -- Coverage-Report mit Codecov-Upload + PR-Kommentar.
- `e2e.yml` -- Playwright End-to-End Tests gegen Compose-Stack.
- `dast-scan.yml` -- ZAP Dynamic Security Scan gegen laufendes API.
- `pr-security.yml` -- Trivy/Bandit/SAST + License-Check fuer PRs.
- `security-scan.yml` -- Container-Image- und Dependency-CVE-Scan (Cron).
- `dependencies.yml` -- Wochentlich Renovate/Dependabot-aehnlich, oeffnet PRs.
- `docker.yml` / `docker-build.yml` -- Multi-Arch Image-Build mit SBOM (anchore).
- `deploy.yml` -- Deployment-Pipeline (vermutlich auf Staging/Prod Server).
- `canary-deploy.yml` -- Canary-Rollout mit Health-Watch.
- `k8s-deploy.yml` -- Helm/Kubeconform/Kubesec Validierung + Helm-Apply.
- `terraform.yml` -- TF Format-Check, Plan, Apply mit tfsec.
- `release.yml` -- Tag-basierter Release mit GH-Release-Erstellung.
- `smoke-tests.yml` -- Smoke-Tests nach Deploy.
- `performance.yml` -- k6 Load-Tests gegen Staging.
- `backup-restore-test.yml` -- **Automatischer monatlicher Restore-Test (gut)**.

**Action-Pinning**: GROSSTEILS Digest-gepinnt (`@11bd71...684 # v4.2.2`). Vorbildlich.
Aber ~30 Stellen mit Tag-Pin (`@v3`, `@v4`, `@v6`) -- z.B. `docker/login-action@v3`,
`actions/setup-node@v4`, `peter-evans/create-pull-request@v6`, `azure/setup-helm@v3`,
`slackapi/slack-github-action@v1.25.0`. Supply-Chain-Risiko nicht voll geschlossen.

---

## 3. Backup / Restore

`scripts/backup/` enthaelt: `backup_all.sh`, `pg_backup.sh`, `pg_restore.sh`, `pg_verify.sh`,
`redis_backup.sh`, `minio_backup.sh`, `volume_backup.sh`, `restore_test.sh`, `DR_RUNBOOK.md`,
`backup_metrics.sh`. Plus `scripts/backup-metrics-collector.sh` und `scripts/restore.sh` im Root.

**Code-Inspektion**: `backup_all.sh` ist sauber: `set -euo pipefail`, Logging in
`/backup/logs/backup_all.log`, optionale Slack-Webhook-Benachrichtigung. `restore_test.sh`
nutzt Temp-Datenbank `restore_test_${TIMESTAMP}` (kein Risiko fuer Prod).

**Letzte Aktualisierung**: 2026-02-22 (Commit `1d344a6c`, vor 2.5 Monaten). Noch im
Funktionsfenster, aber **keine Evidenz, dass Restore-Test seitdem MANUELL gelaufen ist**.
Der Workflow `backup-restore-test.yml` existiert -- wenn der Cron tatsaechlich laeuft, ist
das gut, aber niemand schaut die Run-Outputs an.

---

## 4. Monitoring Configs

| Komponente | Pfad | Inhalt |
|---|---|---|
| Prometheus | `infrastructure/prometheus/` | `prometheus.yml` + `rules/` (15 Alert-Files) |
| Grafana | `infrastructure/grafana/dashboards/` | **13 Dashboards** |
| Loki | `infrastructure/loki/loki-config.yml` | konfiguriert |
| Promtail | `infrastructure/promtail/` | konfiguriert |
| Alertmanager | `infrastructure/alerting/alertmanager.yml` + 5 Templates | konfiguriert |
| Tracing | Jaeger Service in compose | aktiv |

**15 Alert-Rule-Files**: api/backup/business/celery/cert/database/docker/loki/minio/node/ocr/qdrant/redis/security/system-slo. Vollstaendige Abdeckung.

**13 Dashboards**: ab-testing, backup, gpu-profiling, loki-retention, ml-routing, ocr-pipeline,
retention-enforcement, system-overview, gpu-utilization, ocr-performance, ocr-self-learning,
slo-compliance, system-health.

Substanziell. Das ist **kein 1-Mann-Hack**, das ist eine ernsthafte Observability-Infrastruktur.

---

## 5. Secrets-Management

`infrastructure/vault/` existiert mit `vault_client.py`, `policies/`, `setup-vault.sh`,
`docker-compose.vault.yml`, `cert-rotation.sh`. HashiCorp Vault ist im Compose integriert.

`.env.example` hat **99 Variablen**. Plus `.env.production.example` und `.env.rag.example`.
99 Secrets fuer einen Solo-Operator zu verwalten -- ohne Vault-Migration ist das ein
massiver toil-Faktor. Vault-Policies existieren, aber `example_usage.py` deutet darauf hin,
dass Vault noch nicht in der App integriert ist (Vault wird gestartet, aber die App liest
weiterhin `.env`).

---

## 6. Scripts-Inventur (Top-10)

1. `backup/backup_all.sh` -- Master-Backup (PG + Redis + MinIO + Volumes).
2. `backup/restore_test.sh` -- Monatlicher automatisierter Restore-Test.
3. `deploy-check.sh` -- Pre-Deployment Readiness-Check.
4. `validate_docker_gpu.py` -- GPU-Sichtbarkeit im Container pruefen.
5. `vram_monitor.py` -- VRAM-Live-Monitor (kritisch fuer OCR).
6. `worker_healthcheck.py` -- Celery-Worker-Health.
7. `data-consistency-check.py` -- DB-Konsistenz (Foreign Keys, Orphans).
8. `db-migrate-check.sh` -- Alembic-Status vor Deploy.
9. `security-scan.sh` -- Lokaler Security-Scan-Wrapper.
10. `validate_system.py` -- E2E-System-Validierung.

Plus: 4 OCR-Benchmarks, 2 SSL/mTLS-Skripte, 3 Release-Skripte. Insgesamt ~50 Skripte. Gut
strukturiert, aber Solo-Operator wird das nie alles im Kopf haben.

---

## 7. Nginx-Konfiguration

`infrastructure/nginx/` mit `Dockerfile`, `nginx.conf`, `conf.d/ablage-system.conf`,
`snippets/security-headers.conf`, `SSL_SETUP.md`.

**Security-Headers (snippets/security-headers.conf)**: VOLLSTAENDIG vorhanden:
`X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`,
`X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Content-Security-Policy: default-src 'self'; ...`, `Permissions-Policy: ...`,
`Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`.

Commit `fd35c0a3` hat die Hardening sauber durchgezogen. Note: Die CSP enthaelt
`'unsafe-inline'` fuer script-src und style-src -- das ist eine Schwaeche, die fuer eine
React-App haeufig vorkommt, aber CSP-Audit-Score nicht 10/10.

---

## 8. Resource-Limits (Konkrete Werte)

Bereits in #1 abgedeckt. Zusatzdetail:

- **Worker GPU**: limit 16 GB RAM, reservation 4 GB RAM, GPU 1x. Kein VRAM-Limit -- Risiko.
- **Worker CPU**: limit 8 GB / 4 CPU. Beat: 512 MB / 0.5 CPU.
- **Postgres**: 4 GB / 2 CPU -- bei pgvector + 100 Kunden zu wenig. Empfehlung: 8 GB.
- **Redis**: 5 GB / 1 CPU + Replica 5 GB. Sentinel-Quorum aktiv.
- **MinIO**: 4 GB / 2 CPU.
- **GPU**: NVIDIA RTX 4080 16 GB VRAM -- shared zwischen DeepSeek-Janus (12 GB),
  GOT-OCR (10 GB), Surya-GPU (4 GB), BGE-Reranker. Realitaet: **nur 1 grosses Modell zur
  Zeit ladbar**.

---

## 9. Deployment-Strategie

Kein `deployment/` Ordner. Stattdessen:

- **Terraform**: `infrastructure/terraform/` mit Modules (compute, database, load_balancer,
  backend). Kein .tfstate -> remote state vermutlich.
- **Ansible**: `infrastructure/ansible/` mit 10 Playbooks (provision, deploy, backup, restore,
  health-check, k3s-install, gitops-install, monitoring-setup, maintenance, docker-setup) und
  10 Rollen.
- **Helm**: `infrastructure/helm/`, `kubernetes/`, `gitops/` -- Multi-Cluster-fertig.
- **Systemd**: `infrastructure/systemd/` -- bare-metal Fallback.

Die Infrastruktur ist **multi-target** (k8s, k3s, Compose, bare-metal). Fuer Solo-Pilot ist
das Overhead. Realistisch: nur Compose + Ansible-Deploy auf 1 Server, der Rest ist Theater.

---

## 10. Zero-Downtime-Deploy

Commit `3b4b014b` "feat(workers): Task error handling + startup health gate". Der Health-Gate
ist in `app/main.py` lifespan: Vor dem Akzeptieren von Requests wird `SELECT 1` gegen die DB
ausgefuehrt; bei Fehler `RuntimeError` -> Container crashed -> Compose restartet.

Optional: `WAIT_FOR_MODEL_PRELOAD` blockiert Startup bis Modelle geladen (default 120s
Timeout). Das verhindert "Worker akzeptiert Tasks bevor GPU-Modell warm ist".

Aber: **Kein Rolling-Deploy in Compose**. `docker-compose up -d` killt Container und startet
neu -> 30-90 Sekunden Downtime pro Deploy. Canary-Workflow existiert in `.github/workflows/`,
aber nur fuer K8s sinnvoll.

---

## 11. Solo-Ops-Realitaet (2 Uhr nachts)

**Brutale Antwort**: Wenn Production crashed waehrend Ben schlaeft, passiert Folgendes:

1. **Alertmanager ist konfiguriert**, aber Receiver = `email-receiver` (`smarthost: localhost:587`,
   `to: ops-team@internal.local`). Slack-Receiver ist **auskommentiert**. PagerDuty/OpsGenie/Teams-
   Templates existieren, sind aber **nicht aktiviert**.
2. Email-SMTP `localhost:587` ohne Auth -> Mails landen nicht in Bens Inbox. Wahrscheinlichkeit,
   dass Ben um 2 Uhr nachts geweckt wird: **0%**.
3. Compose hat `restart: unless-stopped` (vermutlich) -> Container restartet sich selbst.
   Bei DB-Korruption oder GPU-OOM endlosschleifig restart-Crash-Loop -> kein Alarm an Ben.
4. Sentry ist im Compose (`infrastructure/sentry/`), aber `SENTRY_DSN` ist optional -- nicht
   sichergestellt, dass Ben Push-Notifications eingerichtet hat.
5. Kunden bemerken um 8 Uhr morgens, dass Upload nicht funktioniert. Ben sieht es um 9:30 Uhr.

**Existierende Alarme**: 15 Prometheus-Rule-Files mit echten Conditions (api, db, ocr,
celery, system-slo). Die Regeln SIND da. Aber der **letzte Mile** zur Notification ist tot.

---

## Top-3 Staerken

1. **Observability ist Enterprise-Grade**: 13 Grafana-Dashboards, 15 Alert-Rule-Sets,
   Loki+Promtail+Jaeger -- das ist nicht improvisiert. Ein Single-Pane-of-Glass-Setup, das viele
   100-Mitarbeiter-Firmen nicht haben.
2. **Backup/Restore ist diszipliniert**: Master-Skript, monatlicher automatischer Restore-Test
   via GH-Action, DR_RUNBOOK.md, Slack-Webhook-Hook. Datenverlust-Risiko strukturell adressiert.
3. **Resource-Limits & Healthchecks ueberall**: 25/28 Services mit `healthcheck`, ALLE mit
   CPU/RAM-Limits. Kein vergessenes "default unbounded".

## Top-5 Luecken (Pilot-bedrohend)

1. **KEINE 24/7-Notification**: Slack/PagerDuty in Alertmanager auskommentiert; SMTP zeigt auf
   `localhost:587` mit `ops-team@internal.local`. Bei Nacht-Crash bekommt Ben **nichts mit**.
   Das ist **der** kritische Defekt fuer Pilot-Realitaet. (Aufwand: 30 Min Slack-Webhook
   konfigurieren.)
2. **GPU/VRAM-Limit nicht durchgesetzt im Compose**: 16 GB RTX 4080 wird von DeepSeek (12 GB) +
   Surya + Reranker geteilt. Ohne Hard-Limit -> OOM-Crash bei parallelem Last. Code hat
   `gpu_memory_guard`, aber Compose nicht. Bei 100 Kunden bricht das zuerst.
3. **Vault gestartet, aber nicht integriert**: 99 Variablen in `.env.example`. App liest noch
   aus `.env`. Vault-Policies+Setup existieren -- Migration unfertig. Solo-Operator hat 99
   geheime Strings auf einer Disk, kein Rotation, kein Audit-Log.
4. **Postgres-Limit zu niedrig fuer 100-Kunden-Pilot**: 4 GB RAM bei pgvector-Workload + 500
   Docs/h reicht nicht. Empfehlung: 8 GB + `shared_buffers` Tuning. Aktuell wird PG bei Last
   den Plan-Cache verlieren -> langsame Queries.
5. **Action-Pinning unvollstaendig**: ~30 GH-Action-Stellen nutzen `@v3`/`@v4` Tags statt
   SHA-Digest. Supply-Chain-Risiko ist klein, aber bei einem kompromittierten Action-Maintainer
   landet Schadcode in CI -> Secrets exfiltriert.

---

## Note: Infrastructure Pilot-Readiness

**6.5 / 10**

Begruendung:
- +3 Punkte fuer Observability/Monitoring (Enterprise-Grade)
- +2 Punkte fuer Backup/Restore-Disziplin (automatischer Restore-Test)
- +1.5 Punkte fuer Resource-Limits + Healthchecks systematisch
- +1 Punkt fuer Nginx-Security-Headers + SHA-Pinning Mehrheit
- -1 Punkt fuer fehlende Out-of-Hours-Notification (kritisch)
- -0.5 fuer Vault gestartet aber unintegriert
- -0.5 fuer GPU/VRAM-Limit-Loch
- -0.5 fuer Postgres-Tuning fehlt
- -0.5 fuer Multi-Target-IaC ohne Solo-Fokus (Komplexitaet ohne Nutzen)

Pilot mit 5-10 Kunden: machbar, **wenn** Slack-Webhook in 30 Min eingebaut wird. Ohne das ist
"Solo-DevOps-Realitaet" nicht gegeben -- Ben merkt Ausfaelle erst morgens. Pilot mit 100
Kunden: nicht ohne PG-Tuning + VRAM-Disziplin + Vault-Integration.

**Brutale Bottom-Line**: Die Infrastruktur ist ueberraschend reif fuer Solo-Built. Die zwei
realen Risiken sind (a) Notifications gehen ins Leere und (b) GPU-VRAM ist ungeschuetzt. Beide
loesbar in einem Tag. Alles andere ist Tuning, nicht Show-Stopper.
