# Execution Plan — Schritt-für-Schritt Cookbook

**Erstellt:** 2026-05-03 auf Basis der Ultraplan-Mission **Owner:** Ben (Solo-Founder) **Zweck:** Operatives Cookbook. Du arbeitest es Tag für Tag durch. Keine Markdown-Theorie — Commands, Dateien, Verifications, Stop-Conditions.

> ## ⚠️ OFFENE SPRINT-0-ITEMS
>
> Siehe `SPRINT_0_OPEN.md` im Repo-Root für aktive Reminder.
> ****Aktuell offen:** Slack-Webhook-URL einsetzen (G01) — Setup ist fertig, nur die echte URL fehlt.

---

## Wie du diesen Plan benutzt

1. **Linear lesen, sequenziell abarbeiten.** Reihenfolge ist nicht zufällig — Dependencies sind real.
2. **Pro Task: Definition of Done (DoD) abhaken.** Wenn DoD nicht erfüllt ist: NICHT zum nächsten Task springen.
3. **Stop-Conditions ernst nehmen.** Wenn etwas nicht klappt, lieber 1 Tag mehr investieren als drüber wegtun.
4. **Daily-Routine während Pilot:** siehe §7. Vor Pilot-Tag täglich 10 Min Telemetrie + Slack-Check.
5. **Bei Unklarheit:** Lies das passende Audit-/Perspektiv-Dokument (Referenzen in jedem Task).

---

## 0. Pre-Flight (Heute, \~30 Minuten)

**Vor Sprint 0 Tag 1.** Stelle sicher dass deine Arbeitsumgebung sauber ist.

### 0.1 Repo-Stand prüfen

```bash
cd C:\Users\benfi\Ablage_System
git status
git log --oneline -5
```

**DoD:** Keine ungewollten Modifications. Aktueller Branch klar.

### 0.2 Sprint-0-Branch erstellen

```bash
# Falls nicht schon auf feature/ocr-performance:
git stash  # bestehende Änderungen sichern
git checkout master
git pull
git checkout -b sprint-0-pilot-hardening
```

**DoD:** Branch `sprint-0-pilot-hardening` existiert, basiert auf master.

### 0.3 Externes Sentry-Projekt anlegen

Gehe zu <https://sentry.io> (oder selfhosted-Sentry, falls schon im Compose). Erstelle Projekt `ablage-system-pilot`. Notiere DSN.

**DoD:** Sentry-DSN als Umgebungsvariable bereit (für Tag 3).

### 0.4 Slack-Workspace + Channel + Webhook

- Slack-Workspace: dein eigener oder Familie
- Channel: `#ablage-alerts` (privat, nur du)
- Incoming Webhook: <https://api.slack.com/messaging/webhooks> → Webhook-URL kopieren

**DoD:** Slack-Webhook-URL kopiert, Test-Nachricht via `curl` bereits gesendet.

### 0.5 Test-Account für Pilot-Setup vorbereiten

```bash
# Falls noch nicht vorhanden:
docker-compose up -d postgres
# Wenn Backend läuft, User per Admin-API erstellen oder per SQL:
# Test-Account: pilot-test@familie.de
```

**DoD:** Du kannst dich später in Sprint 1 mit `pilot-test@familie.de` einloggen.

---

## 1. Sprint 0 — Stop-the-Bleeding (Woche 1, 5 Personentage)

**Ziel:** 5 Pilot-Blocker eliminieren, sodass das System einen 4-Wochen-Pilot überleben würde.

**Stop-Condition:** Wenn am Ende von Tag 5 nicht alle DoDs grün sind → Pilot-Datum **um 1 Woche verschieben**. Nicht "irgendwie weitermachen".

---

### Tag 1 — Slack-Notification + Backup-Restore (5 Stunden)

#### Task 1.1 — Slack-Webhook in Alertmanager (30 Min) — G01

**Warum:** Live-Walk hat bewiesen — Backend war offline und niemand wusste es. Höchstes Tier-1-Risiko (R01).

**Datei:** `infrastructure/alerting/alertmanager.yml`

**Schritte:**

1. Datei öffnen
2. Block `receivers:` finden (existiert bereits mit `email-receiver`)
3. Neuen Receiver hinzufügen:

```yaml
  # Slack-Empfänger
  - name: 'slack-receiver'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'  # aus .env
        channel: '#ablage-alerts'
        send_resolved: true
        title: '{{ .GroupLabels.alertname }}'
        text: |
          *Severity:* {{ .CommonLabels.severity }}
          *Cluster:* {{ .CommonLabels.cluster }}
          *Service:* {{ .CommonLabels.service }}
          {{ range .Alerts }}{{ .Annotations.description }}{{ end }}
```

4. Im `route:` Block Default-Receiver auf `slack-receiver` setzen (oder ergänzen via `receivers: [email-receiver, slack-receiver]`)
5. `.env` ergänzen: `SLACK_WEBHOOK_URL=<deine-url-aus-Pre-Flight>`
6. Restart: `docker-compose restart alertmanager`
7. Test-Alert auslösen via:

   ```bash
   curl -XPOST http://localhost:9093/api/v2/alerts -H "Content-Type: application/json" -d '[{"labels":{"alertname":"SprintZeroTest","severity":"critical","service":"test"},"annotations":{"description":"Test alert from Sprint 0"}}]'
   ```
   ```

**DoD:**
- [ ] Test-Alert kommt in Slack-Channel `#ablage-alerts` an
- [ ] `send_resolved: true` getestet (zweiter curl mit `endsAt` in Vergangenheit)
- [ ] `.env`-Variable ist NICHT in git committed (`.gitignore` checken)

**Rollback:** Slack-Receiver-Block löschen, Alertmanager restart.

**Referenz:** `docs/ultraplan/perspectives/05_devops.md` §1, `docs/ultraplan/audit/00f_INFRASTRUCTURE_AUDIT.md`

---

#### Task 1.2 — Backup-Restore-Test ausführen + protokollieren (4 Stunden) — G08

**Warum:** Restore-Test wird per GH-Action-Cron ausgeführt, niemand monitort den Cron. Erstmal manuell verifizieren.

**Schritte:**
1. `cat scripts/backup/backup_all.sh` lesen — verstehen was es tut
2. `cat scripts/backup/restore_test.sh` lesen — verstehen was es tut (Temp-DB)
3. Manuell ausführen:
   ```bash
   bash scripts/backup/backup_all.sh
   bash scripts/backup/restore_test.sh
   ```
4. Output protokollieren in `scripts/backup/DR_RUNBOOK.md` (Datum + Erfolg)
5. Falls Fehler: **STOP**. Erst Restore reparieren, dann weiter.

**DoD:**
- [ ] Backup erstellt (Datum-Stempel in Backup-Verzeichnis)
- [ ] Restore-Test grün (Temp-DB hat Daten)
- [ ] `DR_RUNBOOK.md` hat aktuellen Eintrag mit Datum
- [ ] Backup-Größe in DR_RUNBOOK protokolliert (für Trend-Beobachtung)

**Stop-Condition:** Wenn Restore fehlschlägt → restliche Sprint-0-Tasks pausieren, erst Backup reparieren.

**Zeit-Box:** 4h, falls länger benötigt → eskalieren.

---

### Tag 2 — Security-Hardening Block (8 Stunden)

#### Task 2.1 — `python-jose` → `pyjwt` Migration (4 Stunden) — G02

**Warum:** CVE-2024-33664 (algorithm confusion). `pyjwt` ist bereits Dependency.

**Files (zu ändern):**
- `requirements.txt` (Zeile 85)
- `requirements-dev.txt` (Zeile 29)
- `app/core/security_auth.py` (JWT-Encode/Decode)
- evtl. `app/core/totp.py` falls Referenzen

**Schritte:**

1. Aktuelle Verwendung scannen:
   ```bash
   grep -rn "from jose\|import jose" app/ --include="*.py"
   ```

2. Pro Treffer ersetzen:
   ```python
   # ALT:
   from jose import jwt, JWTError
   # NEU:
   import jwt  # PyJWT
   from jwt.exceptions import InvalidTokenError as JWTError
   ```

3. API-Differenzen pyJWT vs jose:
   - `jwt.encode(payload, key, algorithm="HS256")` — gleich
   - `jwt.decode(token, key, algorithms=["HS256"])` — `algorithms` ist Liste in pyjwt (jose erlaubt einzelnen String)
   - Exception-Klassen: jose `JWTError` → pyJWT `InvalidTokenError`

4. `requirements.txt`:
   ```diff
   - python-jose[cryptography]==3.3.0
   + # pyjwt[crypto]>=2.8.0  # falls noch nicht da
   ```

5. `requirements-dev.txt`: `types-python-jose` entfernen

6. Container neu bauen:
   ```bash
   docker-compose build backend
   docker-compose restart backend
   ```

7. Tests ausführen:
   ```bash
   docker-compose exec backend pytest tests/unit/api/test_auth.py -v
   docker-compose exec backend pytest tests/unit -k "totp" -v
   ```

**DoD:**
- [ ] `pip-audit` zeigt KEINEN python-jose-Eintrag
- [ ] Auth-Tests grün (Login, Logout, Refresh, 2FA)
- [ ] Manueller Login mit Test-Account funktioniert
- [ ] Manueller 2FA-Setup funktioniert

**Rollback:** Branch löschen + `requirements.txt` wiederherstellen, Container rebuild.

**Stop-Condition:** Auth-Tests rot → Migration zurücknehmen, Issue dokumentieren, alternative Lib evaluieren (`authlib`).

**Referenz:** `docs/ultraplan/audit/00h_SECURITY_AUDIT.md` §A06

---

#### Task 2.2 — JWT in httpOnly-Cookie statt Response-Body (4 Stunden) — G03

**Warum:** Code/Doku-Drift (`api/v1/README.md:13` sagt httpOnly, Code sagt Body). XSS-Token-Diebstahl-Risiko.

**Datei:** `app/api/v1/auth.py` (Zeile 166)

**Schritte:**

1. Aktuellen Login-Endpoint öffnen
2. Response-Body anpassen:

```python
from fastapi import Response

@router.post("/login")
async def login(..., response: Response):
    # ... Auth-Logik ...
    access_token = create_access_token(...)
    refresh_token = create_refresh_token(...)
    
    # NEU: Cookies setzen
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,           # HTTPS pflicht in Prod
        samesite="strict",
        max_age=15 * 60,       # 15 Min
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600, # 7 Tage
        path="/api/v1/auth/refresh",  # nur an Refresh-Endpoint senden
    )
    
    # Body: keine Tokens mehr, nur Status
    return {
        "status": "success",
        "user": {"id": user.id, "email": user.email}
    }
```

3. `app/core/security_auth.py` — `oauth2_scheme` durch Cookie-Reader ersetzen:

```python
from fastapi import Cookie, HTTPException

async def get_current_user_from_cookie(
    access_token: Annotated[str | None, Cookie()] = None,
    db: AsyncSession = Depends(get_async_session),
) -> User:
    if not access_token:
        raise HTTPException(401, "Not authenticated")
    return await _decode_and_get_user(access_token, db)
```

4. Logout-Endpoint: `response.delete_cookie("access_token")` etc.

5. Frontend (`frontend/src/lib/api/`): `localStorage.setItem` für Tokens entfernen, `credentials: 'include'` in fetch-Calls. Cookie-Axios via `withCredentials: true`.

6. Nginx (Reverse-Proxy): `proxy_pass_header` für Set-Cookie

7. CSRF-Token bleibt im Body (für Double-Submit-Pattern)

8. Test:
   ```bash
   docker-compose exec backend pytest tests/unit/api/test_auth.py -v
   # Manuell: Login → DevTools Application → Cookies → access_token sichtbar
   # localStorage.getItem('access_token') → null
   ```

**DoD:**
- [ ] DevTools zeigt `access_token` als httpOnly-Cookie
- [ ] `localStorage.getItem('access_token')` returns null
- [ ] Auth-Tests grün
- [ ] Manuell: Login → API-Call → 200 (Cookie wird auto-mitgeschickt)
- [ ] `api/v1/README.md:13`-Aussage stimmt jetzt mit Code überein

**Rollback:** `git revert` der Commits in diesem Task. Branches möglichst clean halten.

**Stop-Condition:** Falls Frontend nicht mit Cookies umgehen kann → tieferer Frontend-Refactor nötig, ggf. eigenen Sprint-Tag spendieren.

**Referenz:** `docs/ultraplan/audit/00h_SECURITY_AUDIT.md` §A07

---

### Tag 3 — Backend-Stabilität + Observability (6 Stunden)

#### Task 3.1 — `asyncio.run()` Bug in `adhoc_report_service.py:991` (2 Stunden) — G04

**Warum:** `asyncio.run()` aus laufendem Event-Loop crasht mit `RuntimeError: This event loop is already running`. Lauert auf ersten echten Report-Auftrag.

**Datei:** `app/services/adhoc_report_service.py` Zeile ~991

**Schritte:**

1. Code-Stelle finden:
   ```bash
   grep -n "asyncio.run" app/services/adhoc_report_service.py
   ```

2. Kontext lesen (40 Zeilen davor + danach)

3. Refactoring-Pattern: Methode async machen, statt sync zu wrappen
   ```python
   # ALT (synchron, dann asyncio.run):
   def generate_pdf(self, ...):
       pdf_bytes = asyncio.run(self._render_async(...))
       return pdf_bytes
   
   # NEU (async durchgängig):
   async def generate_pdf(self, ...):
       pdf_bytes = await self._render_async(...)
       return pdf_bytes
   ```

4. Aufrufer-Stellen finden + anpassen:
   ```bash
   grep -rn "generate_pdf\|adhoc.*report" app/api/v1/ app/services/ app/workers/
   ```

5. Test schreiben (falls nicht vorhanden):
   ```python
   # tests/unit/services/test_adhoc_report.py
   import pytest
   
   @pytest.mark.asyncio
   async def test_generate_pdf_no_event_loop_crash():
       service = AdhocReportService(...)
       result = await service.generate_pdf(...)
       assert result is not None
   ```

6. `pytest tests/unit/services/test_adhoc_report.py -v`

**DoD:**
- [ ] `grep -n "asyncio.run" app/services/adhoc_report_service.py` → 0 Treffer
- [ ] Test grün
- [ ] Manueller Adhoc-Report-Aufruf via API funktioniert (Swagger-UI)

**Bonus (optional, falls Zeit):** Audit aller anderen 13 `asyncio.run`-Stellen in `app/workers/*` (siehe `00b_BACKEND_AUDIT.md` §4 + Backend-Engineer-Perspektive 04). Pro Stelle: in Celery-Worker akzeptabel (siehe Senior-BE-Perspektive), aber als Tech-Debt-Ticket dokumentieren.

**Referenz:** `docs/ultraplan/audit/00b_BACKEND_AUDIT.md` §4

---

#### Task 3.2 — Sentry-DSN aktivieren (2 Stunden) — G10

**Warum:** Self-rolled `/api/v1/errors`-POST hat keine Source-Map-Symbolisierung, kein Session-Replay, kein Release-Tracking.

**Schritte:**

1. Sentry-DSN aus Pre-Flight 0.3 in `.env`:
   ```
   SENTRY_DSN=https://...@sentry.io/...
   SENTRY_ENVIRONMENT=production
   SENTRY_RELEASE=$(git rev-parse --short HEAD)
   ```

2. Backend-Integration prüfen — sollte bereits in `app/main.py` oder `app/core/sentry.py` sein. Falls nicht:
   ```python
   import sentry_sdk
   sentry_sdk.init(
       dsn=settings.SENTRY_DSN,
       environment=settings.SENTRY_ENVIRONMENT,
       release=settings.SENTRY_RELEASE,
       traces_sample_rate=0.1,
       profiles_sample_rate=0.1,
   )
   ```

3. Frontend-Integration in `frontend/src/main.tsx`:
   ```typescript
   import * as Sentry from "@sentry/react";
   Sentry.init({
       dsn: import.meta.env.VITE_SENTRY_DSN,
       environment: import.meta.env.MODE,
       release: import.meta.env.VITE_RELEASE,
       integrations: [Sentry.browserTracingIntegration()],
       tracesSampleRate: 0.1,
   });
   ```

4. Source-Map-Upload in CI: `vite.config.ts` hat bereits Source-Maps. Sentry-CLI hinzufügen:
   ```yaml
   # .github/workflows/deploy.yml
   - name: Upload Source Maps to Sentry
     run: |
       npx @sentry/cli releases new $RELEASE
       npx @sentry/cli releases files $RELEASE upload-sourcemaps frontend/dist
       npx @sentry/cli releases finalize $RELEASE
   ```

5. Test-Error auslösen:
   ```bash
   # Backend
   curl http://localhost:8000/api/v1/test-error  # falls existiert, sonst manuell
   # Frontend
   # In DevTools-Konsole: throw new Error("Sprint 0 Test")
   ```

**DoD:**
- [ ] Backend-Test-Error erscheint in Sentry-Inbox
- [ ] Frontend-Test-Error erscheint in Sentry-Inbox mit Source-Map-Stack-Trace
- [ ] Slack-Notification von Sentry kommt (Sentry-Slack-Integration!)

**Stop-Condition:** Falls Frontend-Source-Maps nicht symbolisiert werden → Sentry-CLI-Upload-Step debuggen, ggf. zusätzlichen Tag spendieren.

---

#### Task 3.3 — Login-Rate-Limit verschärfen (2 Stunden) — G07

**Warum:** Aktuell `10/minute` per IP = 14400/Tag = trivial Credential-Stuffing.

**Datei:** `app/api/v1/auth.py` Zeile ~93

**Schritte:**

1. Rate-Limit-Config finden:
   ```bash
   grep -n "10/minute\|rate_limit" app/api/v1/auth.py
   ```

2. Verschärfen auf BSI-Empfehlung:
   ```python
   # ALT:
   @router.post("/login")
   @limiter.limit("10/minute")
   
   # NEU:
   @router.post("/login")
   @limiter.limit("5/15minutes")  # IP-basiert
   ```

3. Account-Lockout nach 5 Fehlversuchen pro Username (User-basiert):
   - Neue Spalte in User-Model: `failed_login_attempts`, `locked_until` (falls noch nicht da)
   - In Login-Service: bei Fehler increment, bei 5 → lock 15 Min
   - Bei erfolgreichem Login: reset

4. Tests:
   ```bash
   pytest tests/unit/api/test_auth.py::test_login_rate_limit -v
   pytest tests/unit/services/test_account_lockout.py -v  # neu schreiben
   ```

**DoD:**
- [ ] 6. Login-Versuch in 15 Min wird mit 429 abgelehnt
- [ ] 5 falsche Passwort-Versuche → Account 15 Min gesperrt
- [ ] User-Sicht: "Konto vorübergehend gesperrt — versuchen Sie es in 15 Min erneut"

**Referenz:** `docs/ultraplan/audit/00h_SECURITY_AUDIT.md` §A07, BSI-Empfehlung

---

### Tag 4 — Backend-Watchdog + System-Hardening (8 Stunden)

#### Task 4.1 — Backend-Container Auto-Start + Watchdog (1 Tag) — G05

**Warum:** Live-Walk-Beweisführung. Ohne Auto-Restart bei Crash = Pilot-Killer.

**Schritte:**

1. **docker-compose.yml** prüfen — alle kritischen Services brauchen `restart: unless-stopped`:
   ```yaml
   backend:
     restart: unless-stopped  # NICHT "no" oder fehlend
   postgres:
     restart: unless-stopped
   redis:
     restart: unless-stopped
   nginx:
     restart: unless-stopped
   ```

2. **Healthcheck verschärfen** für Backend:
   ```yaml
   backend:
     healthcheck:
       test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
       interval: 30s
       timeout: 5s
       retries: 3
       start_period: 60s
   ```

3. **Systemd-Service** für Docker-Compose-Auto-Start nach Server-Reboot:
   ```bash
   # /etc/systemd/system/ablage-system.service
   [Unit]
   Description=Ablage-System Docker Compose
   Requires=docker.service
   After=docker.service
   
   [Service]
   Type=oneshot
   RemainAfterExit=yes
   WorkingDirectory=/path/to/Ablage_System
   ExecStart=/usr/local/bin/docker-compose up -d
   ExecStop=/usr/local/bin/docker-compose down
   TimeoutStartSec=300
   
   [Install]
   WantedBy=multi-user.target
   ```
   
   ```bash
   sudo systemctl enable ablage-system.service
   sudo systemctl start ablage-system.service
   ```

4. **Watchdog-Skript** als Cron-Job (alle 1 Min Backend-Health prüfen):
   ```bash
   # scripts/watchdog/backend_watchdog.sh
   #!/bin/bash
   set -euo pipefail
   
   if ! curl -sf http://localhost:8000/health > /dev/null; then
     echo "$(date -Iseconds) Backend unhealthy, restarting" >> /var/log/ablage-watchdog.log
     docker-compose restart backend
     # Slack-Alert via Webhook
     curl -XPOST "${SLACK_WEBHOOK_URL}" -d '{"text":"Backend wurde via Watchdog restartet"}'
   fi
   ```
   
   ```bash
   chmod +x scripts/watchdog/backend_watchdog.sh
   # Cron:
   echo "* * * * * /path/to/scripts/watchdog/backend_watchdog.sh" | crontab -
   ```

5. **Prometheus-Alert** für Backend-Down:
   - In `infrastructure/prometheus/alerts/` neue Rule:
   ```yaml
   - alert: BackendDown
     expr: up{job="backend"} == 0
     for: 2m
     labels:
       severity: critical
     annotations:
       description: "Backend ist seit 2 Minuten offline"
   ```

6. **Crash-Test:**
   ```bash
   docker-compose stop backend
   sleep 70  # Watchdog hat 1 Min Cycle + Restart-Zeit
   docker-compose ps backend  # sollte wieder "Up" sein
   # Slack-Channel checken: Notification?
   ```

**DoD:**
- [ ] Server-Reboot → Container starten automatisch (über Systemd)
- [ ] `docker stop backend` → Watchdog restartet in <90s
- [ ] Slack-Notification kommt bei Restart
- [ ] Prometheus-Alert feuert bei 2min-Downtime
- [ ] Watchdog-Log unter `/var/log/ablage-watchdog.log` nachvollziehbar

**Stop-Condition:** Falls Container nach Crash nicht startet (z.B. wegen DB-Migration-Lock) → Restart-Logik um "wait for postgres" erweitern (existiert bereits via depends_on healthcheck, prüfen).

---

### Tag 5 — Sprint-0-Review + Dokumentation (4 Stunden)

#### Task 5.1 — Smoke-Test der gesamten Sprint-0-Arbeit (2 Stunden)

**Schritte:**

1. **Komplett-Restart:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

2. **Manueller End-to-End-Test:**
   - [ ] Login mit Test-Account (sieht httpOnly-Cookie)
   - [ ] Logout (Cookie wird gelöscht)
   - [ ] 6 falsche Login-Versuche → 6. wird abgelehnt
   - [ ] 1 Dokument hochladen → OCR läuft
   - [ ] Adhoc-Report auslösen → kein asyncio.run-Crash
   - [ ] Frontend `throw new Error("Smoke-Test")` → in Sentry sichtbar
   - [ ] Backend `docker stop` → Watchdog restartet, Slack-Alert kommt

3. **Pip-audit:**
   ```bash
   docker-compose exec backend pip-audit
   # Erwartet: 0 critical CVEs
   ```

4. **Test-Suite vollständig:**
   ```bash
   docker-compose exec backend pytest tests/unit -v
   # Erwartet: alle grün, ggf. einzelne pre-existing red ok
   ```

**DoD:**
- [ ] Alle 7 Smoke-Test-Punkte abgehakt
- [ ] `pip-audit` ohne kritische CVEs
- [ ] Test-Suite ohne neue Regressions

#### Task 5.2 — Sprint-0-Doku schreiben (1 Stunde)

Erstelle `docs/sprint-reports/sprint-0-2026-W18.md`:

```markdown
# Sprint 0 — Stop-the-Bleeding (KW18 2026)

## Erledigt
- G01: Slack-Webhook in Alertmanager (30 Min)
- G02: python-jose → pyjwt Migration (4h)
- G03: JWT in httpOnly-Cookie (4h)
- G04: asyncio.run-Bug `adhoc_report_service.py:991` (2h)
- G05: Backend-Watchdog + Auto-Restart (8h)
- G07: Login-Rate-Limit verschärft (2h)
- G08: Backup-Restore-Test (4h)
- G10: Sentry-DSN aktiviert (2h)

## Abgelehnt / Verschoben
- (falls etwas)

## Kennzahlen
- Crash-Recovery-Time: <Xs (gemessen)
- pip-audit critical CVEs: 0
- Sprint-0-Aufwand effektiv: X PT (geschätzt 5)

## Findings für nächsten Sprint
- (z.B. weitere asyncio.run-Stellen in app/workers/)
- (z.B. Frontend-Cookie-Refactor war komplexer als gedacht)

## Pilot-Datum
- Aktuell anvisiert: <Datum>
- Aktuell geblockt durch: NICHTS (oder: Frontend-Cookie-Refactor)
```

#### Task 5.3 — PR + Review (1 Stunde)

```bash
git add -A
git commit -m "feat(sprint-0): Pilot-Hardening abgeschlossen (G01-G10)

- G01: Slack-Webhook in Alertmanager
- G02: python-jose → pyjwt (CVE-2024-33664)
- G03: JWT in httpOnly-Cookie
- G04: asyncio.run-Bug fix
- G05: Backend-Watchdog
- G07: Login-Rate-Limit verschärft
- G08: Backup-Restore-Test verifiziert
- G10: Sentry-DSN aktiviert

Closes #G01-G10"
git push origin sprint-0-pilot-hardening
```

PR auf master öffnen. Selbst reviewen (mit Sprint-0-Doku als Beweisführung).

**DoD:**
- [ ] PR gemerged
- [ ] Sprint-0-Doku committed
- [ ] master-Branch zeigt grünes CI

---

### Sprint 0 Erfolgsmetriken

Am Ende von Tag 5 sollten folgende Werte gelten:

| Metrik | Ziel | Wie messen |
|--------|------|-----------|
| Slack-Notification-Test | Bestanden | curl-Test in Tag 1 + manuell in Smoke-Test |
| pip-audit critical CVEs | 0 | `pip-audit` Output |
| Backend-Crash-Recovery-Time | <90s | Stopp-Test in Tag 4 |
| Backup-Restore-Doku-Datum | <30 Tage alt | DR_RUNBOOK.md Datum |
| Login-Rate-Limit | 5/15min | Manueller Test |
| Sentry-Test-Errors | 2 (Backend + Frontend) | Sentry-Inbox |

**Wenn 6/6 erfüllt:** Sprint 1 starten, Pilot-Datum hält.
**Wenn <6:** Sprint 0 verlängern, Pilot-Datum **um 1 Woche verschieben**, NICHT durchwinken.

---

## 2. Sprint 1 — Pilot-Hardening Auth + UX (Woche 2)

**Ziel:** Auth-Flow härten + UX-Pilot-Blocker schließen.

**Tasks (Reihenfolge, parallel-fähig):**

| Tag | Task | Effort | Gap |
|-----|------|--------|-----|
| Mo | "Zuruck"-Umlaut + i18n-Lint-Rule | 4h | G06, G22 |
| Mo+Di | Pilot-Workflow E2E-Test schreiben | 3T | G09 |
| Di+Mi | Onboarding-Konsolidierung 4→1 | 1W | G11 |
| Mi+Do | 56 Silent-Catches sweepen | 1W | G15 |
| Fr | Pilot-Telemetrie-Dashboard | 1T | G21 |

**Daily-Routine während Sprint 1:**
- 09:00 — Sentry-Inbox checken (5 Min)
- 09:05 — Slack `#ablage-alerts` checken (5 Min)
- 17:00 — Tag-Notiz: was hat blockiert?

**Sprint 1 Erfolgsmetriken:**
- E2E-Test-SLA: Pilot-Workflow <2min p95 — automatisch gemessen
- `grep -c "except Exception:[ \n]*pass" app/services/` → 0
- Onboarding-Drop-off-Rate <30% (gemessen via Telemetrie)

### Sprint-1-Detail-Tasks

#### S1.1 — "Zuruck"-Umlaut + i18n-Lint (4h) — G06, G22

```bash
# Find all umlaut-violations:
grep -rn "Zuruck\|zuruck\|Ueber\b\|ueber\|Strasse\|Schluss\|schluss" frontend/src --include="*.tsx" --include="*.ts"

# Common candidates: "Zuruck" → "Zurück", "Ueber" → "Über", "Strasse" → "Straße"
# Pro Treffer: manuell ersetzen (oder via sed wenn 100% sicher)

# Lint-Rule (eslint-plugin-i18n-text):
npm install --save-dev eslint-plugin-i18n-text
# In .eslintrc.json:
{
  "rules": {
    "i18n-text/no-en": "error"  # blockiert hardcoded English
  }
}

# Oder eigene Custom-Rule die typische Umlaut-Patterns flaggt
```

**DoD:** `grep -rn "Zuruck\|Ueber\b" frontend/src` → 0 Treffer in produktiven Files.

#### S1.4 — Silent-Catches sweepen (1W) — G15

```bash
# Inventur:
grep -rn "except Exception:[ \n]*pass" app/services/ | tee /tmp/silent_catches.txt
wc -l /tmp/silent_catches.txt  # Erwartet: 56

# Pro Treffer: Logger ergänzen
# ALT: except Exception: pass
# NEU: except Exception as e: logger.exception("Context-Beschreibung", error=str(e))

# Bei Compliance-kritischen Pfaden zusätzlich reraise:
# except Exception as e: 
#     logger.exception("...")
#     raise  # weiter nach oben

# Verification:
grep -rn "except Exception:[ \n]*pass" app/services/ | wc -l  # → 0
```

**DoD:** 0 Silent-Catches im Service-Layer; alle ersetzt durch `logger.exception` (+ optional reraise an Compliance-Pfaden).

#### S1.2 — Pilot-Workflow E2E-Test (3T) — G09

Neue Datei `tests/e2e/test_pilot_workflow.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test('Pilot-Workflow: Eingangsrechnung → OCR → Buchen → Archiv', async ({ page }) => {
  test.setTimeout(120_000);  // SLA: 2 Min
  const start = Date.now();
  
  await page.goto('/login');
  await page.fill('[name="email"]', 'pilot-test@familie.de');
  await page.fill('[name="password"]', process.env.PILOT_TEST_PW!);
  await page.click('button:has-text("Anmelden")');
  await page.waitForURL(/dashboard/);
  
  // Upload
  await page.goto('/upload');
  await page.setInputFiles('input[type="file"]', 'tests/e2e/fixtures/sample-invoice.pdf');
  await page.click('button:has-text("Hochladen")');
  
  // OCR-Wait
  await page.waitForSelector('[data-status="ocr-completed"]', { timeout: 60_000 });
  
  // Buchen
  await page.click('button:has-text("Verbuchen")');
  await page.waitForSelector('text=Erfolgreich verbucht');
  
  // Archiv
  await page.click('button:has-text("Archivieren")');
  await page.waitForURL(/archiv/);
  
  const elapsed = (Date.now() - start) / 1000;
  expect(elapsed).toBeLessThan(120);  // SLA: <2 Min
  console.log(`Pilot-Workflow Total: ${elapsed}s`);
});
```

**DoD:** Test grün; Output zeigt Workflow-Dauer; `playwright.config.ts` hat `repeatEach: 3` für Median-Messung.

---

## 3. Sprint 2 — Compliance + Security-Hardening (Woche 3)

**Tasks:**

| Tag | Task | Effort | Gap |
|-----|------|--------|-----|
| Mo-Mi | Verfahrensdokumentation als signiertes PDF | 2W | G19 |
| Do | Art. 30 DSGVO-Verzeichnis Seed-Migration + UI | 1W | G20 |
| Do | TSE/KassenSichV-Klärung (Steuerberater + Anwalt anrufen!) | 1W | G35 |
| Fr | CSP `unsafe-inline` entfernen | 1W | G16 |
| Fr | `pip-audit` + `gitleaks` + `bandit` in CI | 1T | G24 |
| (parallel) | Vault-Integration für Secrets | 1W | G25 |
| (parallel) | training_migration_service Whitelist | 4h | G17 |

**Daily-Routine wie Sprint 1.**

**Sprint 2 Erfolgsmetriken:**
- Verfahrensdokumentation als signiertes PDF in `docs/compliance/`
- CSP-Score auf securityheaders.com: A (von D)
- Schriftliche Steuerberater-Statement zu TSE liegt vor
- CI zeigt `pip-audit`-Status pro PR

---

## 4. Sprint 3-4 — UX-Polish + Test-Coverage (Wochen 4-5)

**Tasks:**

| Sprint | Task | Effort | Gap |
|--------|------|--------|-----|
| 3 | Tooltip/Help in Top-20-Routes | 1W | G12 |
| 3 | Glossar-Seite (`/help/glossar`) | 3T | G13 |
| 3 | Sandbox-/Read-Only-Mode | 1W | G14 |
| 4 | A11y-CI-Gate mit axe-core | 1W | G28 |
| 4 | 93 axe-Violations beheben | 2W | G28 |
| 4 | Component-Tests Risk-Scoring + Spotlight | 2W | G26 |
| 4 | KOSIT-Validator integrieren | 1W | G18 |

**Stop-Condition Sprint 4:** Wenn Pilot-Datum nach Sprint 4 nicht erreicht wird → re-priorisieren oder Pilot 1 Woche schieben.

---

## 5. Pilot-Vorbereitung (Sprint 5, Woche 6)

**Ein-Wochen-Checkliste:**

### Mo: Pilot-Kick-off-Meeting (4h)

- 4 Stakeholder einladen: Prokurist, 3 Azubis, externe Steuerberaterin (telefonisch ok)
- Erwartungen abstimmen: was kann das System, was nicht (siehe Founder-Perspektive!)
- Pilot-Versprechen schriftlich:
  - Eingangsrechnung in <2 Min
  - Dokument in <10 Sek findbar
  - DATEV-Export in <15 Min
  - 0 verpasste Skonto-Fristen
- KEINE neuen Versprechen über das hinaus

### Di-Mi: Pilot-Daten-Migration (2T)

```bash
# 3 Monate Lexware-Daten exportieren
# Per Lexware-Export-Funktion (CSV oder XML)

# In Ablage-System importieren
# Über Admin-Bulk-Import-Endpoint oder Skript:
docker-compose exec backend python -m scripts.import_lexware --from-date=2026-02-01

# Validierung: Stichprobe 20 Dokumente manuell prüfen
```

### Do: Onboarding-Workshop (3h, Live mit Pilot-Team)

- 9:00-9:30: Was ist das System? (Demo)
- 9:30-10:30: Pilot-Team probiert selbst (mit Sandbox-Mode!)
- 10:30-11:00: Q&A
- 11:00-11:30: Pilot-Phase-Plan + Daily-Check-in-Termin festlegen

### Fr: Hot-Fix-Prozess + SLA-Doku (4h)

`docs/pilot/hot-fix-sla.md`:
```markdown
## Hot-Fix-SLA Pilot-Phase

| Severity | Definition | Reaktionszeit | Behebungszeit |
|----------|-----------|---------------|---------------|
| P0 | Pilot kann nicht arbeiten | <30 Min | <2h |
| P1 | Workflow blockiert, Workaround vorhanden | <2h | <1 Werktag |
| P2 | Annoyance, kein Block | <1 Werktag | <1 Woche |

## Eskalationspfad

1. Pilot-Team meldet via Slack `#ablage-pilot` ODER Mail an ben@...
2. Ben bestätigt Eingang in <30 Min
3. Ben prüft Severity, kommuniziert ETA
4. Bei P0: tägliches Update bis Fix
```

**DoD Sprint 5:**
- [ ] Pilot-Team kann Workflow ohne Ben durchführen (im Workshop bewiesen)
- [ ] Daily-Slack-Channel etabliert
- [ ] Hot-Fix-SLA als signiertes Dokument
- [ ] 3 Monate historische Daten in Ablage-System importiert
- [ ] Lexware-Abschalt-Datum verbindlich definiert (z.B. 2 Wochen nach Pilot-Start)

---

## 6. Pilot Live (Sprints 6-7, Wochen 7-8)

**Daily-Routine während Pilot:**

```
09:00-09:10 — Telemetrie-Check (Grafana)
   - TTFV (Time to First Value)
   - Workflow-Errors letzte 24h
   - OCR-Latenz p95
   - Login-Failures
   
09:10-09:20 — Daily-Standup mit Pilot-Team (Slack-Huddle)
   - 1) Was wurde gestern verarbeitet?
   - 2) Wo gab es Blocker?
   - 3) Was ist heute geplant?

09:20-09:30 — Sentry-Inbox + Slack #ablage-alerts
   - Neue Errors triagieren
   - P0-Bugs sofort fixen
   
17:00-17:15 — Tag-Notiz
   - Was wurde gefixt?
   - Welche Findings für Post-Pilot?
   - NPS-Score-Schätzung (1-10)
```

**Wöchentliche Retrospektive (Freitags 16:00, 30 Min):**
- Was lief gut?
- Was lief schief?
- Was probieren wir nächste Woche?
- NPS-Score-Update

**Pilot-Erfolgsmetriken (gemessen über 4 Wochen):**

| Metrik | Ziel | Wie messen |
|--------|------|-----------|
| TTFV (Eingangsrechnung→archiviert) | <2 Min p50, <5 Min p95 | Telemetrie-Dashboard |
| Verpasste Skonto-Fristen | 0 | Manuelle Wochen-Auswertung |
| Datenverluste | 0 | Sentry + Backup-Verify |
| GoBD-Violations | 0 | AuditLog-Hash-Chain-Verify |
| NPS-Score Pilot-Team | ≥7/10 | Wöchentliche Umfrage |
| Hot-Fix-MTTR P0 | <2h | SLA-Tracker |

### Pilot-Wrap-Up (Sprint 8 / Woche 9)

| Tag | Task |
|-----|------|
| Mo | Pilot-Retrospective Meeting (2h, mit gesamtem Pilot-Team) |
| Di | Findings-Doc schreiben (1T): mind. 10 Lessons-Learned konkret |
| Mi | TCO-Vergleich erstellen: ist (Ablage) vs. vorher (Lexware+StarMoney+...) |
| Do | Pilot-Kunden-Testimonial einholen (schriftlich, ggf. Foto) |
| Fr | **Markt-Decision-Meeting (Solo): Multi-Tenant ja/nein? ICP-Reframe ja/nein?** |

**Decision-Tree am Ende des Pilots:**

```
Pilot erfolgreich?
├── JA (NPS ≥7, alle Metriken erreicht)
│   ├── Familie als Referenz-Case
│   ├── ICP-Reframe abschließen (Family-Office-Light?)
│   ├── Sprint M3-6 starten (Markt-Eintritt)
│   └── 2-3 weitere Pilot-Kunden akquirieren
│
├── TEILWEISE (NPS 5-7, Hauptmetriken erreicht)
│   ├── Pilot 4 Wochen verlängern
│   ├── 5 wichtigste Findings fixen
│   └── Re-Evaluation nach Verlängerung
│
└── NEIN (NPS <5, Workflow-Failures häuften sich)
    ├── PIVOT-Decision: Stoppe Markt-Plan
    ├── Spin-Off-Evaluation (siehe ROADMAP M12)
    └── Karriere-Decision: Ben mit Job + Side-Project, oder Hire-Out?
```

---

## 7. Post-Pilot: Monate 3-12

**Siehe `ROADMAP.md` §"Monate 3-6" + §"Monate 6-12" für Detail.**

**Top-3 Decision-Punkte:**

### Decision 1 (Anfang Monat 3): ICP-Reframe

**Frage:** Bleibt es bei "KMU-Cloud-Alternative" oder Pivot zu "Family-Office-Light"?

**Entscheidungs-Kriterien:**
- Pilot-NPS ≥8 → KMU-Markt funktioniert mit Familie als Beweis
- Pilot-NPS 6-7 → Family-Office-Light wahrscheinlich besser (Privatvermögen-Modul war stark genutzt?)
- Pilot-NPS <6 → STOP, neu denken

**Owner:** Ben (Solo-Decision)

**Deadline:** Tag 14 nach Pilot-Ende

### Decision 2 (Mitte Monat 4): Multi-Tenancy

**Frage:** Single-Tenant-pro-Instanz (on-prem) oder Multi-Tenant-SaaS?

**Entscheidungs-Kriterien:**
- Wenn 80%+ Interessenten "wir wollen On-Prem" sagen → Single-Tenant
- Wenn 50%+ "wir wollen Cloud" → Multi-Tenant-Refactor (8 Wochen)

**Sprint M5 startet basierend auf dieser Decision.**

### Decision 3 (Monat 9): Hire #2

**Frage:** Senior-Dev oder Sales-Person?

**Trigger:**
- 3+ zahlende Kunden
- Ben >50% Zeit in Support → Velocity sinkt
- Bus-Faktor 1 wird bedrohlich (siehe RISK_REGISTER R03, R20)

**Entscheidungs-Kriterien:**
- Bei strukturellem Code-Debt (God-Objects akut) → Senior-Dev
- Bei Lead-Generation-Engpass → Sales-Person

---

## 8. Quality-Gates und Stop-Conditions

**Wann du diesen Plan UNTERBRECHEN sollst:**

| Bedingung | Aktion |
|-----------|--------|
| Sprint 0 nach 5 Tagen NICHT abgeschlossen | Pilot-Datum 1 Woche schieben |
| pip-audit zeigt neue critical CVEs | Sofort patchen, alles andere parken |
| Backend-Crash >2× pro Woche während Pilot | Pilot pausieren, Root-Cause analysieren |
| Du arbeitest >50h/Woche über 4 Wochen | Pflicht-Pause 3 Tage, NICHT verhandelbar (R20) |
| NPS-Score Pilot-Team <5 | Pivot-Entscheidung sofort, nicht erst nach 4 Wochen |
| Ein Sprint-Task >2× Effort-Schätzung | Stop, neu schätzen, ggf. Sprint umplanen |

---

## 9. Daily-Routine (Sprint 0 bis Pilot-Ende)

**Morgens (10 Min):**
1. Sentry-Inbox prüfen
2. Slack `#ablage-alerts` checken
3. `git pull` falls von anderem Gerät gearbeitet

**Während Arbeit:**
- Pomodoro: 25 Min Focus + 5 Min Pause
- Pro Sprint-Task max 2× geschätzten Effort, dann re-evaluieren
- Bei Frustration → 15 Min Pause, dann weiter ODER Task wechseln

**Abends (10 Min):**
1. `git status` prüfen — keine ungewollten Modifications?
2. Tag-Notiz: was war fertig, was hängt, was kommt morgen
3. Slack-Channel-Stille → ok, kein Crash heute

**Wöchentlich (Freitag, 30 Min):**
1. Sprint-Review: Tasks fertig vs. geplant (Velocity)
2. Risk-Register-Watch-Liste durchgehen
3. NPS-Score von Pilot-Team einsammeln

---

## 10. Quick-Reference: Wichtigste Datei-Pfade

```
docs/ultraplan/
├── EXECUTIVE_DASHBOARD.md           ← 1× pro Woche lesen
├── RISK_REGISTER.md                 ← Watch-Liste wöchentlich prüfen
├── ROADMAP.md                       ← Sprint-Planung
├── EXECUTION_PLAN.md                ← Diese Datei (operatives Cookbook)
└── audit/00j_LIVE_SYSTEM_REPORT.md  ← Bei Frontend-Bugs prüfen

infrastructure/alerting/alertmanager.yml  ← Slack-Webhook
infrastructure/prometheus/alerts/         ← Alert-Rules
docker-compose.yml                        ← Service-Config + Healthchecks
scripts/backup/                           ← Backup + Restore-Test
scripts/watchdog/backend_watchdog.sh      ← Crash-Recovery
.env                                      ← Secrets (NICHT committed)

app/api/v1/auth.py                        ← JWT-Cookie-Logik
app/services/adhoc_report_service.py      ← asyncio.run-Bug
app/core/security_auth.py                 ← Auth-Helpers
requirements.txt                          ← Dependencies (pip-audit-Targets)
```

---

## 11. Bekenntnis-Klausel

Dieser Plan funktioniert nur, wenn du:

1. **Linear vorgehst.** Nicht "ach das mach ich später, jetzt erst RAG-Layer ausbauen" (Founder 10 §"FAANG-Mode aus")
2. **Stop-Conditions ernst nimmst.** Auch wenn es weh tut.
3. **Daily-Routine lebst.** Sentry-Check + Slack-Check sind nicht optional während Pilot.
4. **Decision-Punkte triffst.** Nicht aufschieben — Decision 1 (ICP) Tag 14 nach Pilot, nicht Tag 60.
5. **Hilfe holst, wenn überfordert.** Bei Decision 2 + 3 (Multi-Tenant + Hire) — sprich mit Ehepartner / Freund / Mentor. Bus-Faktor-1 bedeutet auch: Wissen-Faktor-1.

---

**Wenn du diesen Plan in 12 Monaten nochmal liest:**

Dann hast du:
- Einen erfolgreichen Pilot (oder eine ehrliche Pivot-Decision)
- 3-5 zahlende Kunden (oder eine Lifestyle-Cap-Akzeptanz)
- Hire #2 ausgeschrieben (oder Pivot zu Spin-Off)
- Bus-Faktor 1 abgemildert (oder Bewusstsein darüber)

Egal welcher Pfad: dieser Plan war der Anker.

---

**Erstellt: 2026-05-03**
**Update: pro Sprint-Ende (in `docs/sprint-reports/`)**
**Vollständige Mission-Dokumentation: `docs/ultraplan/`**
