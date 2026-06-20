# Runbook: Redis Cluster Recovery

> Wiederherstellung bei Redis-Ausfaellen

## Uebersicht

| Metrik | Wert |
|--------|------|
| Severity | HIGH |
| RTO | 15 Minuten |
| RPO | 0 (Cache) / 1 Stunde (Queue) |
| On-Call | Backend Team |

## Symptome

- API gibt 503 zurueck
- Rate Limiting nicht funktional
- Celery Tasks werden nicht verarbeitet
- Login schlaegt fehl (Token-Blacklist nicht erreichbar)

## Diagnose

### 1. Redis-Status pruefen

```bash
# Container-Status
docker compose ps redis

# Redis-Logs
docker compose logs --tail=100 redis

# Redis-Verbindung testen
docker compose exec redis redis-cli ping
# Erwartete Antwort: PONG

# Memory-Status
docker compose exec redis redis-cli INFO memory
```

### 2. Verbindung vom Backend testen

```bash
# In Backend-Container
docker compose exec backend python -c "
import redis
r = redis.Redis(host='redis', port=6379)
print(r.ping())
"
```

### 3. Haeufige Fehler

| Fehler | Ursache |
|--------|---------|
| `Connection refused` | Redis nicht gestartet |
| `OOM command not allowed` | Speicher erschoepft |
| `LOADING Redis is loading` | Startup nach Crash |
| `MISCONF` | Schreibschutz wegen Speicher |

## Recovery-Schritte

### Fall 1: Redis Container gestoppt

```bash
# Neustart
docker compose restart redis

# Warten auf Start
sleep 5

# Verifizieren
docker compose exec redis redis-cli ping
```

### Fall 2: Out of Memory

```bash
# Memory-Status pruefen
docker compose exec redis redis-cli INFO memory

# Cache leeren (nur Caches, nicht Queue!)
docker compose exec redis redis-cli FLUSHDB

# Oder: Nur bestimmte Keys loeschen
docker compose exec redis redis-cli KEYS "cache:*" | xargs -L 1 docker compose exec redis redis-cli DEL
```

### Fall 3: Korrupte Daten (RDB/AOF)

```bash
# Redis stoppen
docker compose stop redis

# RDB-Backup pruefen
ls -la /var/lib/docker/volumes/ablage_redis_data/_data/

# Korrupte RDB loeschen (ACHTUNG: Datenverlust!)
sudo rm /var/lib/docker/volumes/ablage_redis_data/_data/dump.rdb

# AOF reparieren
docker compose run --rm redis redis-check-aof --fix /data/appendonly.aof

# Redis neu starten
docker compose up -d redis
```

### Fall 4: Netzwerk-Problem

```bash
# Netzwerk pruefen
docker network inspect ablage_backend-network

# Container neu verbinden
docker network disconnect ablage_backend-network ablage-redis
docker network connect ablage_backend-network ablage-redis

# Neustart
docker compose restart redis backend worker
```

## Rollback

Bei persistenten Problemen: Daten aus Backup wiederherstellen.

```bash
# Redis stoppen
docker compose stop redis

# Backup wiederherstellen
cp /backups/redis/dump.rdb /var/lib/docker/volumes/ablage_redis_data/_data/

# Redis starten
docker compose up -d redis
```

## Verifizierung

Nach Recovery:

```bash
# 1. Redis-Health
docker compose exec redis redis-cli ping

# 2. API-Health
curl http://localhost:8000/health

# 3. Celery-Worker testen
docker compose exec backend celery -A app.workers.celery_app inspect active

# 4. Rate-Limiting testen
for i in {1..10}; do curl -s http://localhost:8000/api/v1/health; done
```

## Eskalation

| Zeit | Aktion |
|------|--------|
| 5 min | Redis neugestartet |
| 15 min | Eskalation an Backend Lead |
| 30 min | Eskalation an CTO |

## Praevention

- Redis Memory-Limit setzen (`maxmemory 2gb`)
- AOF aktivieren (`appendonly yes`)
- Redis Sentinel fuer HA (falls Multi-Node)
- Monitoring-Alerts fuer Memory-Nutzung

---

*Letzte Aktualisierung: 2024-12*
