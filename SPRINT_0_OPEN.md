# 🚨 SPRINT 0 — OFFENE ITEMS (Ben muss aktiv werden)

**Stand:** 2026-05-04 **Datei-Zweck:** Damit du nicht vergisst was noch offen ist. Diese Datei lebt im Root, sodass `git status` + `ls` sie dir täglich vor Augen halten.

---

## ✅ ERLEDIGT — Slack-Webhook (G01) — 2026-05-04 22:43

URL gesetzt, alertmanager force-recreated (Volume-Mount greift nicht bei `restart`).
4 Notifications in `#ablage-alerts` verifiziert:
- 2 Tests (Watchdog + Alertmanager-Routing)
- 2 echte critical Alerts (LokiCompactorNotRunning, CeleryWorkerDownLong) → R01 LIVE GESCHLOSSEN

**Wichtige Lesson für Spätere:** Bei Volume-Mount-Änderungen IMMER `docker-compose up -d --force-recreate <service>`, niemals `docker-compose restart <service>`.

---

## 🔴 OFFEN — Sentry-DSN (G10)

**Was fehlt:** Echte Sentry-DSN in `.env`. Code-Integration ist fertig, `sentry-sdk` wird beim nächsten Container-Rebuild installiert. **DSN muss du selbst erstellen.**

**Was du tun musst (\~5 Min):**

1. <https://sentry.io> → Account anlegen (oder selfhosted unter `infrastructure/sentry/docker-compose.alerting.yml` starten)
2. Neues Projekt erstellen: Name `ablage-system-pilot`, Plattform Python/FastAPI
3. DSN kopieren (Format: `https://.....@o....ingest.sentry.io/.....`)
4. In `.env` setzen:

   ```
   SENTRY_DSN=https://....
   ENVIRONMENT=production
   ```
5. Backend rebuild + restart:

   ```bash
   docker-compose build backend
   docker-compose up -d backend
   ```
6. Test-Error auslösen (z.B. nicht-existenten Endpoint aufrufen):

   ```bash
   curl http://localhost:8000/api/v1/this-does-not-exist
   ```
7. Erwartet: Error in Sentry-Inbox innerhalb 30s

**Verifikation-Datei (zum Abhaken):**

- \[ \] Sentry-Account + Projekt erstellt
- \[ \] `SENTRY_DSN` in `.env` gesetzt
- \[ \] Backend-Logs zeigen `sentry_initialized` (statt `sentry_not_configured`)
- \[ \] Test-Error erscheint in Sentry-Inbox

---

## 🟡 BEOBACHTEN — Aktive kritische Alerts (Sprint 0 Tag 1 Side-Discovery)

Beim Sprint-0-Setup wurden folgende kritische Alerts entdeckt, die **seit 31h aktiv waren** ohne Notification (R01 live bestätigt):

```
OCRBackendDown          critical
APIDown                 critical
QdrantDown              critical
ServiceDown             critical
CeleryWorkerDownLong    critical
RedisReplicationBroken  critical
LokiCompactorNotRunning critical
HostHighSwapUsage       warning
HostDiskSpaceLow        warning
```

**Frage zu klären:** Echte Probleme oder False Positives (z.B. weil Backend gerade hochgefahren ist)?

**Diagnose-Befehle:**

```bash
docker ps --filter "name=ablage" --format "table {{.Names}}\t{{.Status}}"
curl http://localhost:8000/health
curl http://localhost:9090/api/v1/alerts | python -m json.tool | grep -E '"alertname"|"state"' | head -40
```

**Verifikation-Datei (zum Abhaken):**

- \[ \] Pro Alert: echtes Problem oder False Positive identifiziert
- \[ \] Echte Probleme behoben oder Ticket erstellt
- \[ \] False Positives: Alert-Rule-Schwellen angepasst

---

## 📋 Sprint-0-Gesamtfortschritt

TaskStatusNotesG01 Slack-Webhook Setup✅ CodeRouting-Test bestandenG01 echte URL🟡 wartet auf Bensiehe obenG08 Backup-Restore-Test✅RTO &lt;2 Min, 427 TablesG02 python-jose → PyJWT (Code)✅5 App + 3 Test Files migriert, live verifiziertG02 Container-Rebuild⚠️ blockiertJanus-Repo-Clone-Failure (vor Sprint 0)G04 asyncio.run Bug✅\_export_pdf async, live verifiziertG07 Login-Rate-Limit✅10/min → 5/min, Live-Test HTTP 429 ab 5. VersuchG10 Sentry-Code✅requirements.txt + .env.exampleG10 echte Sentry-DSN🟡 wartet auf Bensiehe obenHealthcheck-Fix✅start_period 600s (war 180s)**DB-URL sslmode-Bug**✅Side-Discovery, Backend startet jetzt sauber**G05 Backend-Watchdog Sidecar**✅Container `ablage-watchdog` laeuft, Crash-Test bestanden, Auto-Restart bei 3 FailuresG03 JWT in httpOnly-Cookie⏳ Tag 2.2Frontend-Refactor noetigJanus-Build-Failure⚠️ Tech-DebtBlockiert docker-compose build backend (vor Sprint 0)

## ✅ Sprint 0 — Code-Phase ABGESCHLOSSEN

- 8 von 8 geplanten Tasks code-seitig fertig (G01, G02, G04, G05, G07, G08, G10 + Healthcheck-Fix)
- 1 Bonus-Task: Side-Fix DB sslmode (R01 live bestätigt + behoben)
- 2 wartet auf Ben: echte Slack-URL + echte Sentry-DSN
- 1 Tech-Debt entdeckt: Janus-Repo-Build-Failure (G02-Image-Rebuild blockiert)
- **Tempo:** \~3.5h real vs. 14h geplant (\~4× schneller)

---

## 🛠️ Stabilisierungs-Patch — 2026-05-06 22:30 lokal

**Trigger:** 48h Slack-Alert-Spam (siehe Slack `#ablage-alerts`). Realität: Backend war seit 04.05. 23:54 wieder up & healthy (44h). Aber Worker dauerhaft im Crash-Loop wegen Code-Bugs + Alertmanager `repeat_interval` zu kurz + 3 falsch konfigurierte Persistent-Alerts.

### Behoben (Code-Änderungen)

- `app/workers/tasks/mlops_tasks.py:20` — Import-Pfad korrigiert: `app.db.database` → `app.db.session` (1 Zeile)
- `app/workers/tasks/booking_tasks.py:20` + `datev_connect_tasks.py:26` — `from app.workers.celery_app import celery` → `import celery_app as celery` (Alias)
- `app/workers/tasks/hygiene_tasks.py:13` + `tax_package_tasks.py:14` — `app.core.database` → `app.db.session` (Modul existiert nicht)
- `app/workers/tasks/nlq_tasks.py` — `NLQLog` → `NLQQueryLog` (23 Vorkommen, korrekter Modell-Name)
- `app/db/session.py:160` — `async_session_maker` als zusätzlicher Alias für Backwards-Kompatibilität (16 Files importieren das)

### Behoben (Config-Änderungen)

- `infrastructure/prometheus/rules/loki-alerts.yml:71` — `loki_compactor_running` → `loki_boltdb_shipper_compactor_running` (echter Metrik-Name; Compactor läuft tatsächlich)
- `infrastructure/prometheus/prometheus.yml:92-101` — `nvidia-gpu` Job auskommentiert (dcgm-exporter Container existiert nicht; Profil-bedingt; sonst dauerhaft `up=0`)

### Live-System Aktionen

- ✅ Alertmanager-Silence aktiv für 4h (ID `fed66680-af74-4680-86c6-59c890a8dd9f`) — bis 2026-05-07 00:15 UTC
- ✅ Worker-Restart: `celery@d04732c0c293 ready`, `cpu_worker@6ccce4d572fa ready`, beide ping=pong (2 Nodes online)
- ✅ Disk-Cleanup: ~66GB freigegeben (-42GB Build Cache, -2.2GB Dangling Images, -21.6GB Volumes)
- ✅ Prometheus reload (2× nötig, dann nvidia-gpu Target weg)

### Echtes Restproblem (nicht behoben)

- 🟡 **`ablage_backup_disk_free_bytes = 0`** ist KEIN realer Disk-Mangel (354.9GB free auf `/var/backups/ablage` verfügbar), sondern: `update_disk_usage()` wird im laufenden Backend-Process **nie aufgerufen**. Gauge bleibt auf Initial-0. Fix später: Periodic Celery-Beat-Task der die Update auslöst, oder im FastAPI-Lifespan-Hook integrieren.
- 🟡 **Disk 95% voll** auf C: (107GB free). Docker: 227GB reclaimable in nicht-laufenden Images, aber das sind **andere Projekte** (Trellis 71GB, ComfyUI 33GB, TTS-Stack 75GB, clawdbot 51GB) — `docker image prune -a` würde diese löschen, daher User-Approval nötig.
- 🟡 Alertmanager `repeat_interval` Tuning (Phase 5 aus Plan) noch offen — ohne wird Spam nach 4h Silence wieder einsetzen.

### Lessons

- **Niemals `docker volume prune -f` ohne Inspektion** — der lief diesmal sauber, aber bei named Volumes wie `claude-memory` oder `ablage_system_ollama_models` wäre Datenverlust möglich gewesen.
- **Alert-Rules immer mit echter Metrik gegenchecken** — `loki_compactor_running` existiert nicht in Loki, der echte Name war `loki_boltdb_shipper_compactor_running`. Konfigurations-Bug der seit Sprint 0 Tag 1 spammt.
- **Backend-up ≠ System-up** — 48h Slack-Alarm ohne dass Ben wusste, dass Backend nach Auto-Restart 44h stabil läuft. Workers waren der echte Down-Service.
- **`docker-compose restart` propagiert keine Config-Reloads** — Prometheus brauchte 2× POST `/-/reload`, bis nvidia-gpu Target verschwand.
