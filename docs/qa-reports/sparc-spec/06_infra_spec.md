# 06 — Infrastruktur (Spec)

## I1: /health/startup 503 (NICHT-BEHOBEN)
### IST (belegt)
GET /api/v1/health/startup -> 503, `"redis": false`, obwohl der redis-Container healthy ist. Ein frueherer
"Fix" (W2-04) stellte `_check_redis()` auf `settings.REDIS_URL` um — die Probe ist aber WEITER rot. Indiz:
REDIS_URL-Wert wird als `redis://localhost:6380/0` gesehen (Connection refused), waehrend der aktive Redis unter
Service `redis:6379` mit Passwort laeuft. D.h. die Probe nutzt zwar REDIS_URL, aber der Wert selbst ist im
betreffenden Kontext falsch (localhost:6380 statt redis:6379+AUTH).
### ZIEL
Probe muss denselben verbundenen Client/URL wie der produktive Pfad (`app/core/redis_state.py`) verwenden.
Reconcile: REDIS_URL im Backend-Kontext == funktionierende Broker-/Cache-URL (`redis://:<pw>@redis:6379/0`).
Quelle der Wahrheit klaeren: `.env` vs `docker-compose.yml`-`environment` vs `app/core/config.py`-Default
(localhost:6380). Default in config.py auf den Container-Namen ausrichten ODER .env/compose verbindlich setzen.
### Pseudocode
```
# _check_redis: identisch zum produktiven Pfad
client = await redis_state.get_client()   # statt eigener from_url mit evtl. falschem Default
await client.ping()
```
### DoD
- [ ] `GET /api/v1/health/startup` -> 200, `checks.redis==true` (Live).
- [ ] `docker exec ablage-backend python -c "import os;print(os.environ['REDIS_URL'])"` zeigt redis:6379(+AUTH).

## I2: Beat + Worker + Worker-CPU EXITED (INFRA-DOWN)
### IST (belegt)
`docker inspect` -> State=exited, Health=unhealthy fuer ablage-beat/worker/worker-cpu (warm shutdown; Logs zeigen
RuntimeError/TypeError vor Shutdown). Damit laufen Scheduled Tasks (GDPR-Loeschung, Backups, Retention) NICHT,
und ein GET-Sweep ist nur eingeschraenkt aussagekraeftig.
### ZIEL
1. Container hochfahren (worktree-compose `up -d --no-deps beat worker worker-cpu`) + Boot-Fehler aus den Logs
   beheben (RuntimeError/TypeError-Ursache identifizieren — kann eigener Defekt sein, nicht nur "down").
2. Healthcheck haerten: aktuell nur `pgrep -f celery` -> meldet "healthy" auch bei haengendem/totem Worker.
   Stattdessen Broker-Ping / Heartbeat-Key pruefen.
### DoD
- [ ] beat/worker/worker-cpu State=running, Health=healthy.
- [ ] `celery -A app.workers.celery_app inspect ping` antwortet.
- [ ] Healthcheck erkennt einen kuenstlich gestoppten Worker als unhealthy (Negativtest).

## I3: WS-Token im URL (W2-06, NICHT-BEHOBEN)
### IST (belegt)
`app/api/v1/websocket.py` Z.77/268/300/335: `token: Optional[str] = Query(None, ...)` -> JWT als `?token=` ->
landet in Access-/Proxy-Logs, Browser-History, Referer (P0-Leak).
### ZIEL (koordinierter FE+BE-Umbau)
Token via `Sec-WebSocket-Protocol`-Subprotokoll ODER erstem Message-Frame uebertragen; Query-Param entfernen
(oder uebergangsweise deprecaten + aus Logs filtern). Frontend `websocket.ts` entsprechend anpassen.
### TDD/DoD
- [ ] WS-Connect ohne Query-Token funktioniert (Subprotokoll/Frame); mit Query-Token -> abgelehnt oder deprecated.
- [ ] `grep -n "token.*Query" app/api/v1/websocket.py` -> 0 (nach Umbau).
- [ ] Realtime-Features (Upload/OCR-Progress) im Browser weiter funktionsfaehig.