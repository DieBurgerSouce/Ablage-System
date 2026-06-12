# PostgreSQL Connection Pool Exhaustion Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-1 (Critical)
> RTO: 15 Minuten | RPO: 0 (kein Datenverlust)

## Alert

```
AppDBPoolExhausted (CRITICAL)
AppDBPoolUtilizationHigh (WARNING) - > 80%
```

## Symptome

- API-Endpunkte geben HTTP 503 zurück
- Fehlermeldungen: `QueuePool limit exceeded`
- Lange Response-Zeiten (> 5s)
- Celery-Tasks schlagen mit DB-Fehlern fehl

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Aktive Verbindungen prüfen

```bash
# Verbindungen pro Anwendung
docker exec -it ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT
    application_name,
    state,
    COUNT(*) as count
FROM pg_stat_activity
WHERE datname = 'ablage_system'
GROUP BY application_name, state
ORDER BY count DESC;
"
```

### 2. Idle Connections identifizieren

```bash
# Langlebige idle Verbindungen (> 5 Minuten)
docker exec -it ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT
    pid,
    application_name,
    state,
    query_start,
    now() - query_start as duration,
    LEFT(query, 80) as query
FROM pg_stat_activity
WHERE datname = 'ablage_system'
  AND state = 'idle'
  AND now() - query_start > interval '5 minutes'
ORDER BY duration DESC
LIMIT 20;
"
```

### 3. Idle Connections terminieren

```bash
# Idle Verbindungen älter als 10 Minuten beenden
docker exec -it ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'ablage_system'
  AND state = 'idle'
  AND now() - query_start > interval '10 minutes'
  AND pid <> pg_backend_pid();
"
```

---

## Diagnose (5-10 Minuten)

### 4. Pool-Konfiguration prüfen

```bash
# Backend-Umgebungsvariablen
docker exec ablage-backend printenv | grep -E "(POOL|DB_)"

# Erwartete Werte:
# DB_POOL_SIZE=20
# DB_POOL_MAX_OVERFLOW=40
# DB_POOL_TIMEOUT=30
```

### 5. PgBouncer Status (falls verwendet)

```bash
# PgBouncer Pools
docker exec -it ablage-pgbouncer psql -U ablage_admin -h 127.0.0.1 -p 6432 pgbouncer -c "SHOW POOLS;"

# Client-Statistiken
docker exec -it ablage-pgbouncer psql -U ablage_admin -h 127.0.0.1 -p 6432 pgbouncer -c "SHOW CLIENTS;"
```

### 6. Slow Queries identifizieren

```bash
# Queries die Verbindungen blockieren
docker exec -it ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT
    pid,
    now() - query_start as duration,
    state,
    wait_event_type,
    LEFT(query, 100) as query
FROM pg_stat_activity
WHERE datname = 'ablage_system'
  AND state != 'idle'
  AND now() - query_start > interval '30 seconds'
ORDER BY duration DESC;
"
```

---

## Lösung

### Option A: Backend-Restart (schnell)

```bash
# Backend neustarten (beendet alle Verbindungen)
docker-compose restart backend

# Worker ebenfalls neustarten
docker-compose restart worker
```

### Option B: Pool-Größe temporär erhöhen

```bash
# docker-compose.override.yml
cat >> docker-compose.override.yml << 'EOF'
services:
  backend:
    environment:
      - DB_POOL_SIZE=40
      - DB_POOL_MAX_OVERFLOW=80
EOF

docker-compose up -d backend
```

### Option C: Langfristige Lösung

1. **Connection Pooler (PgBouncer)**:
   ```yaml
   # docker-compose.yml
   pgbouncer:
     image: edoburu/pgbouncer:latest
     environment:
       - DATABASE_URL=postgresql://ablage_admin:${DB_PASSWORD}@postgres:5432/ablage
       - POOL_MODE=transaction
       - MAX_CLIENT_CONN=500
       - DEFAULT_POOL_SIZE=50
   ```

2. **Anwendungs-Optimierung**:
   - Async Sessions mit `expire_on_commit=False`
   - Connection Recycling: `SQLALCHEMY_POOL_RECYCLE=3600`
   - Explizites Session-Management mit Context Manager

---

## Verifikation

```bash
# Pool-Status nach Fix
docker exec -it ablage-postgres psql -U ablage_admin -d ablage_system -c "
SELECT COUNT(*) as connections,
       MAX(CASE WHEN state = 'idle' THEN 1 ELSE 0 END)::int as has_idle
FROM pg_stat_activity
WHERE datname = 'ablage_system';
"

# API Health Check
curl -s http://localhost:8000/api/v1/health | jq .database

# Metriken prüfen
curl -s http://localhost:8000/api/v1/metrics | grep db_pool
```

---

## Prävention

1. **Monitoring**: Dashboard "DB Pool Utilization" in Grafana
2. **Alerting**: Warning bei > 70%, Critical bei > 90%
3. **Connection Timeout**: `statement_timeout = '30s'` in PostgreSQL
4. **Idle Timeout**: `idle_in_transaction_session_timeout = '5min'`

---

## Eskalation

| Zeit | Aktion |
|------|--------|
| 0-5 min | On-Call: Sofortmaßnahmen |
| 5-15 min | Backend-Team: Diagnose |
| 15+ min | Eskalation an DBA/Platform Team |

---

## Verwandte Runbooks

- [Database Recovery](database-recovery.md)
- [Celery Worker Recovery](celery-worker-restart.md)
- [API Error Rate Spike](api-error-rate-spike.md)
