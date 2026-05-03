# 🚨 SPRINT 0 — OFFENE ITEMS (Ben muss aktiv werden)

**Stand:** 2026-05-04
**Datei-Zweck:** Damit du nicht vergisst was noch offen ist. Diese Datei lebt im Root, sodass `git status` + `ls` sie dir täglich vor Augen halten.

---

## 🔴 OFFEN — Slack-Webhook (G01)

**Was fehlt:** Echte Slack-Webhook-URL. Aktuell ist eine Placeholder-URL eingesetzt, sodass `docker-compose` startet — aber Slack-Notifications funktionieren NICHT.

**Was du tun musst (~10 Min):**

1. https://api.slack.com/apps → "Create New App" → "From scratch"
2. App-Name: `Ablage-Alerts`, Workspace wählen
3. Linke Sidebar → "Incoming Webhooks" → Toggle ON
4. In Slack: Channel `#ablage-alerts` erstellen (privat, nur du)
5. In Slack-API: "Add New Webhook to Workspace" → Channel auswählen → "Allow"
6. Webhook-URL kopieren (Format: `https://hooks.slack.com/services/T.../B.../...`)
7. URL einfügen:
   ```bash
   echo "https://hooks.slack.com/services/DEINE-URL" > infrastructure/alerting/slack-webhook.url
   docker-compose restart alertmanager
   ```
8. Test:
   ```bash
   curl -XPOST http://localhost:9093/api/v2/alerts \
     -H "Content-Type: application/json" \
     -d '[{"labels":{"alertname":"SlackTest","severity":"critical","service":"test"},"annotations":{"description":"Sprint 0 G01 final test"}}]'
   ```
9. Erwartet: Slack-Message in `#ablage-alerts` innerhalb 30 Sek

**Verifikation-Datei (zum Abhaken):**
- [ ] Slack-Workspace + App erstellt
- [ ] Webhook-URL in `infrastructure/alerting/slack-webhook.url`
- [ ] Test-Alert erscheint in `#ablage-alerts`

**Sobald erledigt:** Diesen Eintrag aus `SPRINT_0_OPEN.md` löschen.

---

## 🔴 OFFEN — Sentry-DSN (G10)

**Was fehlt:** Echte Sentry-DSN in `.env`. Code-Integration ist fertig, `sentry-sdk` wird beim nächsten Container-Rebuild installiert. **DSN muss du selbst erstellen.**

**Was du tun musst (~5 Min):**

1. https://sentry.io → Account anlegen (oder selfhosted unter `infrastructure/sentry/docker-compose.alerting.yml` starten)
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
- [ ] Sentry-Account + Projekt erstellt
- [ ] `SENTRY_DSN` in `.env` gesetzt
- [ ] Backend-Logs zeigen `sentry_initialized` (statt `sentry_not_configured`)
- [ ] Test-Error erscheint in Sentry-Inbox

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
- [ ] Pro Alert: echtes Problem oder False Positive identifiziert
- [ ] Echte Probleme behoben oder Ticket erstellt
- [ ] False Positives: Alert-Rule-Schwellen angepasst

---

## 📋 Sprint-0-Gesamtfortschritt

| Task | Status | Notes |
|------|--------|-------|
| G01 Slack-Webhook Setup | ✅ Code | Routing-Test bestanden |
| G01 echte URL | 🟡 wartet auf Ben | siehe oben |
| G08 Backup-Restore-Test | ✅ | RTO <2 Min, 427 Tables |
| G02 python-jose → PyJWT (Code) | ✅ | 5 App + 3 Test Files migriert, live verifiziert |
| G02 Container-Rebuild | ⚠️ blockiert | Janus-Repo-Clone-Failure (vor Sprint 0) |
| G04 asyncio.run Bug | ✅ | _export_pdf async, live verifiziert |
| G07 Login-Rate-Limit | ✅ | 10/min → 5/min, Live-Test HTTP 429 ab 5. Versuch |
| G10 Sentry-Code | ✅ | requirements.txt + .env.example |
| G10 echte Sentry-DSN | 🟡 wartet auf Ben | siehe oben |
| Healthcheck-Fix | ✅ | start_period 600s (war 180s) |
| **DB-URL sslmode-Bug** | ✅ | Side-Discovery, Backend startet jetzt sauber |
| **G05 Backend-Watchdog** | ✅ | Crash-Test bestanden, Auto-Restart bei 3 Failures |
| G03 JWT in httpOnly-Cookie | ⏳ Tag 2.2 | Frontend-Refactor nötig |
| Watchdog-Process-Setup | 🟡 wartet auf Ben | Cron / Windows-Task / Background — siehe DR_RUNBOOK §Backend-Watchdog |

## ✅ Sprint 0 — Code-Phase ABGESCHLOSSEN

- 8 von 8 geplanten Tasks code-seitig fertig (G01, G02, G04, G05, G07, G08, G10 + Healthcheck-Fix)
- 1 Bonus-Task: Side-Fix DB sslmode (R01 live bestätigt + behoben)
- 2 wartet auf Ben: echte Slack-URL + echte Sentry-DSN
- 1 Tech-Debt entdeckt: Janus-Repo-Build-Failure (G02-Image-Rebuild blockiert)
- **Tempo:** ~3.5h real vs. 14h geplant (~4× schneller)
