# API Error Rate Spike Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-1 bis SEV-2 (abhängig von Error-Rate)
> RTO: 15 Minuten | RPO: N/A

## Alert

```
APIErrorRateWarning - > 1% Fehlerrate
APIErrorRateCritical - > 5% Fehlerrate
HighResponseLatency - P95 > 2s
```

## Symptome

- HTTP 5xx Fehler im Frontend
- API-Timeouts
- Langsame oder fehlgeschlagene Dokumentenverarbeitung
- Benutzer können sich nicht anmelden
- Grafana zeigt Error-Spike

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Error-Rate und -Typen prüfen

```bash
# Aktuelle Error-Rate
curl -s http://localhost:8000/api/v1/metrics | grep -E "http_requests_total|http_errors_total"

# Fehler nach Status-Code (letzte 5 Minuten)
docker logs ablage-backend --since 5m 2>&1 | grep -E "HTTP/1.1\" [45]" | \
  awk '{print $9}' | sort | uniq -c | sort -rn
```

### 2. Fehlermuster identifizieren

```bash
# Die häufigsten Fehler
docker logs ablage-backend --since 5m 2>&1 | grep -i "error\|exception" | \
  tail -20

# Strukturierte Logs (falls Loki verfügbar)
curl -G http://localhost:3100/loki/api/v1/query \
  --data-urlencode 'query={container="ablage-backend"} |= "ERROR"' \
  --data-urlencode 'limit=20'
```

### 3. Upstream-Abhängigkeiten prüfen

```bash
# Schneller Health-Check aller Services
for service in postgres redis minio; do
    echo -n "$service: "
    docker exec ablage-$service echo "OK" 2>/dev/null || echo "FAILED"
done

# Backend Health-Endpoint
curl -s http://localhost:8000/api/v1/health | jq
```

---

## Diagnose (5-15 Minuten)

### 4. Betroffene Endpunkte identifizieren

```bash
# Error-Rate pro Endpunkt
docker logs ablage-backend --since 15m 2>&1 | \
  grep -E "HTTP/1.1\" [45]" | \
  awk '{print $7}' | sort | uniq -c | sort -rn | head -10
```

### 5. Slow Queries prüfen

```bash
# Langsame Requests (> 2s)
docker logs ablage-backend --since 15m 2>&1 | \
  grep -E "request_time=[0-9]+\.[0-9]+" | \
  awk -F'request_time=' '{if($2 > 2.0) print $0}'

# PostgreSQL Slow Queries
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT query, calls, mean_time::numeric(10,2) as avg_ms
FROM pg_stat_statements
WHERE mean_time > 1000
ORDER BY mean_time DESC
LIMIT 10;
"
```

### 6. Resource-Nutzung prüfen

```bash
# Container-Ressourcen
docker stats --no-stream ablage-backend ablage-worker ablage-postgres ablage-redis

# Host-Ressourcen
free -h && df -h / && uptime
```

---

## Lösung nach Fehlertyp

### Fehler: Database Connection Errors

```bash
# Connection Pool prüfen
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT count(*) FROM pg_stat_activity WHERE datname='ablage';
"

# → Siehe: postgresql-connection-pool-exhaustion.md
```

### Fehler: Redis Timeouts

```bash
# Redis Status
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD INFO | grep -E "connected_clients|used_memory"

# Redis neu starten
docker-compose restart redis
```

### Fehler: OOM/Memory Errors

```bash
# Container-Memory
docker inspect ablage-backend --format '{{.HostConfig.Memory}}'

# Memory-Limit erhöhen (temporär)
docker update --memory 4g --memory-swap 6g ablage-backend
```

### Fehler: Rate Limiting

```bash
# Rate Limit Status
curl -s http://localhost:8000/api/v1/admin/rate-limits | jq

# Rate Limits temporär erhöhen
curl -X POST http://localhost:8000/api/v1/admin/rate-limits/increase \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"factor": 2, "duration_minutes": 30}'
```

### Fehler: Authentication Errors

```bash
# JWT-Key Status
docker exec ablage-backend python -c "
from app.core.security import verify_jwt_key
print('JWT Key valid:', verify_jwt_key())
"

# Redis Session Store prüfen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD KEYS "session:*" | wc -l
```

---

## Notfall-Maßnahmen

### Backend-Restart

```bash
# Graceful Restart
docker-compose restart backend

# Falls hanging:
docker-compose kill backend && docker-compose up -d backend
```

### Traffic Throttling

```bash
# Nginx Rate Limiting aktivieren
docker exec ablage-nginx nginx -s reload

# Oder: API-seitiges Throttling
curl -X POST http://localhost:8000/api/v1/admin/throttle/enable \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"requests_per_second": 50}'
```

### Maintenance Mode

```bash
# Maintenance Mode aktivieren
curl -X POST http://localhost:8000/api/v1/admin/maintenance/enable \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"message": "Wartungsarbeiten - bitte warten"}'

# Nur Health-Endpoints bleiben erreichbar
```

---

## Verifikation

```bash
# Error-Rate prüfen (sollte sinken)
watch -n 10 'curl -s http://localhost:8000/api/v1/metrics | grep http_errors_total'

# Latenz prüfen
curl -s http://localhost:8000/api/v1/health -w "\nTime: %{time_total}s\n"

# Erfolgreiche Requests
curl -s http://localhost:8000/api/v1/documents?limit=1 | jq '.total'
```

---

## Metriken & Dashboards

- **Grafana Dashboard**: "API Performance"
- **Prometheus Queries**:
  ```promql
  # Error-Rate
  sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

  # Latenz P95
  histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

  # Requests pro Endpunkt
  topk(10, sum by (path) (rate(http_requests_total[5m])))
  ```

---

## Eskalation

| Error-Rate | Aktion |
|------------|--------|
| 1-5% | On-Call: Diagnose & Fix |
| 5-10% | Team-Lead informieren |
| 10-25% | Maintenance Mode erwägen |
| 25%+ | Eskalation an CTO |

---

## Post-Incident

1. **Logs sichern**: `docker logs ablage-backend > incident_$(date +%Y%m%d).log`
2. **Metriken exportieren**: Grafana Snapshot erstellen
3. **Post-Mortem**: Incident-Report erstellen

---

## Verwandte Runbooks

- [PostgreSQL Connection Pool](postgresql-connection-pool-exhaustion.md)
- [Redis Cluster Recovery](redis-cluster-recovery.md)
- [Incident Response](incident-response.md)
