# 05 - DevOps-Perspektive: Solo-Ops um 3 Uhr nachts

**Rolle:** Senior SRE mit Pager-Trauma. Ich baue Systeme, die niemanden um 3 Uhr nachts wecken.
**Quelle:** `00f_INFRASTRUCTURE_AUDIT.md` + `00j_LIVE_SYSTEM_REPORT.md` + Code-Spot-Checks.
**Stichdatum:** 2026-05-03.

---

## 1-Sentence-Verdict

Die Infrastruktur ist ueberraschend reif - aber der **letzte Mile zu Bens Telefon ist tot**, und das ist bei Solo-Ops der einzige Mile, der zaehlt.

---

## Top-3 Staerken

1. **Observability ist Enterprise-Grade.** 13 Grafana-Dashboards, 15 Prometheus-Alert-Rule-Files, Loki+Promtail+Jaeger im Compose, postgres_exporter + redis_exporter + dcgm-exporter. Das ist nicht improvisiert - das haben viele 100-Personen-Firmen nicht. Wenn Ben sich morgens hinsetzt und schaut, sieht er **alles**.
2. **Backup-Disziplin ist real.** `scripts/backup/backup_all.sh` mit `set -euo pipefail`, `restore_test.sh` der eine Temp-DB anlegt (kein Prod-Risiko), DR_RUNBOOK.md, GitHub-Action `backup-restore-test.yml` als monatlicher Cron. Datenverlust ist strukturell adressiert - das ist 90% der Solo-Founder voraus.
3. **Resource-Limits + Healthchecks systematisch.** 25/28 Services haben `healthcheck:`, ALLE haben `deploy.resources.limits` und `reservations`. Kein "default unbounded". Worker-Hardening (Commit `3b4b014b`) hat einen Startup-Health-Gate eingebaut: `SELECT 1` gegen DB vor Request-Acceptance. Das ist das Niveau, auf dem ich SRE-Reviews bestehen lassen wuerde.

---

## Top-5 Luecken (Solo-Ops-Risiken)

### 1. Bens Pager existiert nicht. Punkt.

`infrastructure/alerting/alertmanager.yml`:
- `smarthost: 'localhost:587'` (kein SMTP-Server konfiguriert auf der Box)
- `to: 'ops-team@internal.local'` (kein realer Mailserver)
- Slack-Webhook-Receiver: **auskommentiert**
- PagerDuty/OpsGenie/Teams-Templates: vorhanden, **nicht aktiviert**

**Wahrscheinlichkeit, dass Ben um 3 Uhr nachts geweckt wird, wenn Backend crashed: 0%.** 15 Prometheus-Rule-Files mit echten Conditions feuern in eine Mail-Pipeline, die ins Leere laeuft. Sentry ist im Compose (`infrastructure/sentry/`), aber `SENTRY_DSN` ist optional - keine Garantie, dass Ben es eingerichtet hat. Push-Notifications aufs Handy: nicht verifiziert.

**Solo-Ops-Realitaet bei DATEV-Export-Crash um 2 Uhr morgens mit 1 zahlendem Pilotkunden:** Der Kunde merkt es um 8 Uhr, schreibt Mail, Ben sieht es um 9:30. Service-Level ~10h Downtime - bei einem Steuerberater-Kunden ist das **Kuendigungsgrund**.

### 2. Live-Walk-Befund: Backend-Container war OFFLINE waehrend Audit.

Aus `00j`: `docker ps` zeigte zum Walk-Zeitpunkt keinen Backend-Container. Das **ist** der Solo-Ops-Albtraum live: das System lief nicht, und niemand wusste es. Frontend-nginx serviert weiter Static-Files (HTTP 200), API-Calls bekommen 502, Toasts erscheinen. Der Pilotkunde sieht nicht "System down" - er sieht **"Server nicht erreichbar"-Toasts**, was er fuer einen Bug seiner Internet-Verbindung haelt. Time-to-Detection durch Ben: stunden. Time-to-Detection durch Kunden: minuten.

**Das ist kein Hypothetisch - das ist passiert, am Audit-Tag.**

### 3. GPU/VRAM-Limit nicht durchgesetzt.

RTX 4080 hat 16 GB VRAM. Compose hat `mem_limit` (Container-RAM), aber **kein VRAM-Limit**. DeepSeek-Janus-Pro: 12 GB. GOT-OCR: 10 GB. Surya-GPU: 4 GB. BGE-Reranker: ~2 GB. Das sind ueber 25 GB VRAM-Bedarf auf einer 16-GB-Karte. Der Code hat `gpu_memory_guard()` und `ModelManager` (siehe CLAUDE.md), aber **bei paralleler Last** wird der Guard nur reaktiv loeschen - das heisst: Erste Anfrage gewinnt, zweite Anfrage wartet oder bekommt OOM. Bei 100 Kunden, die gleichzeitig OCR triggern: Crash-Loop. Dann Restart-Storm. Dann liest Ben morgens 200 Crash-Logs.

### 4. Vault gestartet, App liest weiter `.env`.

99 Variablen in `.env.example`. Vault ist im Compose, `infrastructure/vault/policies/` existiert, `setup-vault.sh` auch. Aber `example_usage.py` deutet an: noch nicht in der App integriert. Solo-Operator hat 99 Geheimnisse auf einer Disk, kein Audit-Log ueber Zugriffe, keine Rotation. Bei einem Server-Diebstahl (Familienbetrieb, kein 24/7-Wachdienst) ist alles weg. **Compliance-Risiko bei DSGVO-Pilot mit Steuerberater-Daten.**

### 5. CI/CD: Digest-Pinning halb-fertig.

Commit `7128e72b` hat Digest-Pinning eingefuehrt, aber `00f` zaehlt ~30 Stellen mit Tag-Pin (`@v3`, `@v4`). Konkrete Beispiele: `docker/login-action@v3`, `actions/setup-node@v4`, `peter-evans/create-pull-request@v6`, `slackapi/slack-github-action@v1.25.0`. Bei einem kompromittierten Maintainer (siehe `tj-actions/changed-files`-Vorfall 2025) landet Schadcode in CI -> alle Secrets exfiltriert. Solo-Operator hat keine Zeit fuer Forensik.

---

## Note: Operations-Readiness

**5.5 / 10**

Begruendung:
- +3 fuer Observability/Monitoring (real Enterprise-Grade)
- +2 fuer Backup/Restore (automatischer Restore-Test, was 90% nicht haben)
- +1.5 fuer Resource-Limits + Healthchecks systematisch
- +0.5 fuer Nginx-Security-Headers + Mehrheit Digest-Pinning
- **-2 fuer fehlenden Out-of-Hours-Alarmweg** (Solo-Ops-K.O.-Kriterium)
- -0.5 fuer Vault gestartet aber nicht integriert
- -0.5 fuer GPU/VRAM-Limit-Loch
- -0.5 fuer Postgres 4 GB RAM-Limit (zu knapp fuer pgvector + 500 Docs/h)
- -0.5 fuer Multi-Target-IaC ohne Solo-Fokus (k8s+k3s+Compose+systemd parallel - Komplexitaet ohne Nutzen)

`00f` hatte 6.5/10 - ich gehe ein Punkt schaerfer, weil der **Live-Walk** beweist, dass Solo-Ops in der Praxis nicht funktioniert (Backend war down ohne dass jemand es bemerkte). Ein Solo-System ohne funktionierende Notification ist **nicht 6.5**, das ist 5.5. Theorie ist gut. Praxis hat versagt.

---

## Was bricht zuerst bei 10 Kunden / 100 Kunden?

### Bei 10 Kunden

1. **Notification-Pipe** (sofort, schon mit 1 Kunden). Erster Crash, Ben merkt es nicht, Kunde ruft an, Ben verliert Vertrauen.
2. **Postgres bei pgvector-Last**: 4 GB RAM-Limit + 10 Kunden mit je 500 Docs/Monat = ~5 GB Embeddings + Indexe. Plan-Cache faellt aus dem RAM, Queries werden 5-10x langsamer. Symptom: "Suche braucht 8 Sekunden statt 0.5".
3. **Restore-Test verlaesst sich auf GH-Action-Cron** - die niemand monitored. Wenn der Cron 3 Monate lang failed, weiss Ben es nicht, und beim ersten realen Restore-Bedarf ist das Backup-Format unverifiziert.

### Bei 100 Kunden

1. **GPU-VRAM-Konkurrenz**: bei parallelen OCR-Anfragen kommt es zu OOM-Restart-Loops. Symptom: 30% der Uploads schlagen mit "Backend nicht erreichbar" fehl, sporadisch.
2. **Single-Box-Architektur**: 32 CPU-Limits + 80 GB RAM-Summe auf einer Workstation - bei 100 aktiven Kunden geht die Box in Swap. Postgres-Latency explodiert, alles wird zaeh.
3. **Vault-noch-nicht-integriert** wird ein Compliance-Audit-Failure. Steuerberater-Kunde fragt nach SOC-Light-Beweis, Ben kann ihn nicht liefern.
4. **Single-Server, Single-GPU**: ein Hardware-Ausfall = Totalausfall. RTO im DR_RUNBOOK ist nicht spezifiziert (`scripts/backup/DR_RUNBOOK.md` existiert, aber kein konkreter "Wiederherstellung in <X Stunden"-SLA). RPO: maximal 24h (taeglicher PG-Dump).
5. **CI-Bottleneck**: 18 GitHub-Actions-Workflows pro PR. Bei 5 Devs (oder mehr Pilot-Kunden = mehr Bug-Reports = mehr PRs) wird die GH-Quota relevant.

---

## 3 konkrete Empfehlungen fuer Ben (Solo-Founder-tauglich)

### 1. Slack-Webhook in Alertmanager - HEUTE, 30 Minuten

In `infrastructure/alerting/alertmanager.yml`:

```yaml
receivers:
  - name: 'slack-critical'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/T.../B.../...'
        channel: '#ablage-ops'
        send_resolved: true
        title: '[{{ .Status | toUpper }}] {{ .CommonLabels.alertname }}'
```

Plus Slack-Mobile-App auf Bens Handy, Push-Notifications fuer den Channel auf "Always". **Das ist der Pager.** Ohne das ist alles andere Theater. Plus: PagerDuty Free-Tier (5 User kostenlos) als Backup-Eskalation fuer Critical-Alerts. Aufwand: 30 Min.

### 2. Vor Pilot-Start: Single-Command-Healthcheck `make pilot-ready`

Ben sollte **vor jedem Pilot-Tag** einen Befehl ausfuehren, der:
- Alle 28 Compose-Services auf `running + healthy` prueft
- Letzten Backup-Timestamp validiert (`find /backup -mtime -1 | wc -l > 0`)
- VRAM-Stand prueft (`< 12 GB used`)
- Slack-Webhook-Test feuert ("Heartbeat from {hostname}")
- Bei FAIL: rote Ausgabe + Exit-Code 1

Das Makefile existiert laut Plan, das `deploy-check.sh` auch. Wrappe beides als `make pilot-ready` - ein Befehl, kein Vergessen. **Der Live-Walk hat genau das gefehlt** - kein Hinweis darauf, dass Backend down war, bis Playwright auf 502 lief.

### 3. Stoppe das IaC-Theater - eine Deployment-Strategie reicht

Aktuell: Terraform + Ansible + Helm + Kubernetes + GitOps + systemd + Compose. Fuer Solo-Pilot mit 1 Server: behalte **nur** Compose + Ansible-Playbook fuer Provision. Loesche oder archiviere `infrastructure/helm/`, `kubernetes/`, `gitops/` in einen `archive/`-Ordner. Begruendung: Jede Zeile Multi-Target-Config ist Code, den Ben nicht versteht und nicht testet, aber die ihn bei "make pilot-ready" verwirrt. Bei 50+ Kunden kann er reaktivieren - vorher ist es Komplexitaets-Schulden, die ihm nichts bringen, aber Zeit kosten.

**Bonus**: Wenn IaC-Reduktion zu radikal scheint, mindestens ein README in jedem Ordner mit "STATUS: NICHT AKTIV - aktiviere bei Skalierung X". Damit weiss zukuenftige-Ben was Live-Code und was Aspirations-Code ist.

---

## Solo-Ops-Schluss-Befund

Die Infrastruktur ist **handwerklich gut**. Backup-Disziplin, Resource-Limits, Observability - das sind Sachen, die viele Solo-Founder einfach nicht machen, und Ben hat sie. Aber die Kette bricht am letzten Glied: **wenn der Pager nicht klingelt, war alles davor egal**.

Der Live-Walk hat das bewiesen. Backend-Container war offline, niemand wusste es, das Audit musste deshalb mit Lueckentext arbeiten. **Genau das passiert beim Pilot um 3 Uhr morgens auch** - nur dass dann nicht ein Audit-Bot wartet, sondern ein zahlender Steuerberater, der DATEV-Export-Termin um 8 Uhr hat.

**Pilot mit 5 Kunden ist machbar - aber nur, wenn der Slack-Webhook in den naechsten 24 Stunden konfiguriert wird.** Ohne das ist "Solo-DevOps-Realitaet" nicht gegeben. Mit dem Webhook (+ Mobile-Push) und einem `make pilot-ready` schafft Ben es. Bei 100 Kunden kommen die strukturellen Themen (GPU-VRAM, Postgres-Tuning, Vault-Integration) - aber das ist Phase 2, nicht Pilot-Blocker.

**Was Ben heute Abend tun sollte:** Slack-Webhook konfigurieren, einen Test-Alert ausloesen, sich aufs Handy senden lassen. Dann schlafen gehen mit dem Wissen, dass das System dich weckt, wenn es brennt. Das ist der Unterschied zwischen "ich habe ein Produkt" und "ich habe einen 24/7-On-Call-Job".
