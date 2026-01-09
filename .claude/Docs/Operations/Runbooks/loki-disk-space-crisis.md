# Loki Disk Space Crisis Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High)
> RTO: 30 Minuten | RPO: Logs können verloren gehen

## Alert

```
LokiDiskSpaceCritical - Loki Storage > 90%
LokiIngestionRateHigh - > 10MB/s Ingestion
LokiChunkStoreFull - Chunk Store voll
```

## Symptome

- Loki akzeptiert keine neuen Logs
- Grafana Explore zeigt "No logs found"
- Backend-Logs werden nicht persistiert
- Loki-Container crasht wiederholt
- Disk-Usage steigt schnell

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Disk-Status prüfen

```bash
# Loki-Datenverzeichnis
du -sh /var/lib/docker/volumes/loki_data/_data/

# Detaillierte Übersicht
du -h /var/lib/docker/volumes/loki_data/_data/ --max-depth=2 | sort -rh | head -20

# Host-Disk
df -h

# Loki Container-Status
docker stats ablage-loki --no-stream
```

### 2. Loki-Status prüfen

```bash
# Loki Ready-Status
curl -s http://localhost:3100/ready

# Loki Metrics
curl -s http://localhost:3100/metrics | grep -E "loki_ingester|loki_chunk"

# Ingestion-Rate
curl -s http://localhost:3100/metrics | grep "loki_distributor_bytes_received_total"
```

### 3. Schnelle Bereinigung

```bash
# Loki stoppen
docker-compose stop loki

# Alte Chunks löschen (> 7 Tage)
find /var/lib/docker/volumes/loki_data/_data/chunks -mtime +7 -delete

# WAL bereinigen
rm -rf /var/lib/docker/volumes/loki_data/_data/wal/*

# Loki starten
docker-compose start loki
```

---

## Diagnose

### 4. Log-Volumen analysieren

```bash
# Welche Labels erzeugen am meisten Logs?
curl -s 'http://localhost:3100/loki/api/v1/label' | jq

# Log-Volumen pro Job
curl -s 'http://localhost:3100/loki/api/v1/query?query=sum(rate({job=~".+"}[1h])) by (job)' | jq

# Chunks pro Stream
curl -s http://localhost:3100/metrics | grep "loki_ingester_chunks_stored_total"
```

### 5. High-Volume-Streams identifizieren

```bash
# Top-10 Log-Produzenten
curl -s 'http://localhost:3100/loki/api/v1/series?match[]={job=~".+"}' | jq '.data | length'

# Logs pro Container (letzte Stunde)
for container in backend worker nginx; do
    count=$(docker logs ablage-$container --since 1h 2>&1 | wc -l)
    echo "$container: $count lines"
done
```

### 6. Retention-Konfiguration prüfen

```bash
# Aktuelle Loki-Config
docker exec ablage-loki cat /etc/loki/local-config.yaml

# Wichtige Einstellungen:
# - limits_config.retention_period
# - table_manager.retention_deletes_enabled
# - table_manager.retention_period
```

---

## Lösung

### Option A: Retention verkürzen

```yaml
# loki-config.yaml
limits_config:
  retention_period: 72h  # Reduziert von 168h (7 Tage)
  max_entries_limit_per_query: 5000

compactor:
  working_directory: /loki/compactor
  shared_store: filesystem
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150

table_manager:
  retention_deletes_enabled: true
  retention_period: 72h
```

```bash
# Anwenden
docker-compose restart loki
```

### Option B: Log-Level anpassen

```bash
# Backend: Nur WARNING und höher
docker exec ablage-backend python -c "
from app.core.config import update_runtime_setting
update_runtime_setting('LOG_LEVEL', 'WARNING')
"

# Oder via Umgebungsvariable
# docker-compose.yml
environment:
  - LOG_LEVEL=WARNING
```

### Option C: Log-Filterung in Promtail

```yaml
# promtail-config.yaml
scrape_configs:
  - job_name: backend
    static_configs:
      - targets: [localhost]
        labels:
          job: backend
          __path__: /var/log/backend/*.log
    pipeline_stages:
      # DEBUG-Logs droppen
      - match:
          selector: '{job="backend"}'
          stages:
            - regex:
                expression: '.*"level":"DEBUG".*'
            - drop:
                source: ""

      # Health-Check Logs droppen
      - match:
          selector: '{job="backend"}'
          stages:
            - regex:
                expression: '.*GET /api/v1/health.*'
            - drop:
                source: ""
```

### Option D: Komprimierung aktivieren

```yaml
# loki-config.yaml
storage_config:
  boltdb_shipper:
    active_index_directory: /loki/boltdb-shipper-active
    cache_location: /loki/boltdb-shipper-cache
    shared_store: filesystem

  filesystem:
    directory: /loki/chunks

chunk_store_config:
  max_look_back_period: 0s

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h
```

### Option E: Alte Daten manuell löschen

```bash
# Loki stoppen
docker-compose stop loki

# Backup erstellen (optional)
tar -czf /backup/loki_$(date +%Y%m%d).tar.gz \
  /var/lib/docker/volumes/loki_data/_data/

# Alte Chunks löschen
find /var/lib/docker/volumes/loki_data/_data/chunks -mtime +3 -delete

# Index-Dateien bereinigen
find /var/lib/docker/volumes/loki_data/_data/boltdb-shipper-active -mtime +3 -delete

# Cache leeren
rm -rf /var/lib/docker/volumes/loki_data/_data/boltdb-shipper-cache/*

# Loki starten
docker-compose start loki
```

---

## Log-Volumen-Reduktion

### Backend-Logging optimieren

```python
# app/core/logging.py
import structlog

def configure_logging():
    structlog.configure(
        processors=[
            # Sampling: Nur 10% der DEBUG-Logs
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        # Filter für Produktion
        wrapper_class=structlog.make_filtering_bound_logger(
            min_level=logging.INFO
        ),
    )
```

### Nginx-Logging reduzieren

```nginx
# nginx.conf
http {
    # Access-Log für Health-Checks deaktivieren
    map $request_uri $loggable {
        ~/health 0;
        ~/ready 0;
        ~/metrics 0;
        default 1;
    }

    access_log /var/log/nginx/access.log combined if=$loggable;

    # Error-Log Level erhöhen
    error_log /var/log/nginx/error.log warn;
}
```

### Celery-Logging reduzieren

```python
# celery_app.py
app.conf.update(
    worker_log_format='[%(asctime)s: %(levelname)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s] %(message)s',
    worker_hijack_root_logger=True,
)

# Nur WARNING und höher für Celery-interne Logs
import logging
logging.getLogger('celery').setLevel(logging.WARNING)
```

---

## Monitoring

### Prometheus Alerts

```yaml
groups:
  - name: loki_alerts
    rules:
      - alert: LokiDiskSpaceWarning
        expr: |
          (node_filesystem_avail_bytes{mountpoint="/var/lib/docker/volumes/loki_data"}
          / node_filesystem_size_bytes{mountpoint="/var/lib/docker/volumes/loki_data"}) < 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Loki Disk Space < 20%"

      - alert: LokiIngestionRateHigh
        expr: rate(loki_distributor_bytes_received_total[5m]) > 10485760
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Loki Ingestion > 10MB/s"

      - alert: LokiDroppedLogs
        expr: rate(loki_distributor_lines_dropped_total[5m]) > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Loki droppt Logs"
```

### Grafana Dashboard

```json
{
  "panels": [
    {
      "title": "Loki Disk Usage",
      "type": "gauge",
      "targets": [
        {
          "expr": "loki_ingester_memory_chunks / 1024 / 1024"
        }
      ]
    },
    {
      "title": "Log Ingestion Rate",
      "type": "graph",
      "targets": [
        {
          "expr": "rate(loki_distributor_bytes_received_total[5m])"
        }
      ]
    }
  ]
}
```

---

## Verifikation

```bash
# Disk-Space nach Bereinigung
df -h /var/lib/docker/volumes/loki_data/_data/

# Loki Status
curl -s http://localhost:3100/ready

# Test-Log senden
echo '{"streams": [{"stream": {"job": "test"}, "values": [["'$(date +%s)000000000'", "Test log entry"]]}]}' | \
  curl -X POST -H "Content-Type: application/json" -d @- http://localhost:3100/loki/api/v1/push

# Log abfragen
curl -s 'http://localhost:3100/loki/api/v1/query?query={job="test"}' | jq

# Ingestion-Rate (sollte stabil sein)
watch -n 5 'curl -s http://localhost:3100/metrics | grep loki_distributor_bytes_received'
```

---

## Langfristige Maßnahmen

### 1. Log-Rotation

```bash
# /etc/logrotate.d/docker-logs
/var/lib/docker/containers/*/*.log {
    daily
    rotate 3
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    maxsize 100M
}
```

### 2. Externe Storage (S3/MinIO)

```yaml
# loki-config.yaml für MinIO
storage_config:
  boltdb_shipper:
    active_index_directory: /loki/boltdb-shipper-active
    cache_location: /loki/boltdb-shipper-cache
    shared_store: s3

  aws:
    s3: s3://minioadmin:minioadmin@localhost:9000/loki
    s3forcepathstyle: true
    insecure: true
```

### 3. Automatische Cleanup-Jobs

```bash
# Cronjob für wöchentliche Bereinigung
cat > /etc/cron.weekly/loki-cleanup << 'EOF'
#!/bin/bash
# Alte Chunks löschen (> 7 Tage)
find /var/lib/docker/volumes/loki_data/_data/chunks -mtime +7 -delete 2>/dev/null

# Disk-Usage loggen
df -h /var/lib/docker/volumes/loki_data/_data/ >> /var/log/loki-disk-usage.log
EOF
chmod +x /etc/cron.weekly/loki-cleanup
```

---

## Eskalation

| Disk-Usage | Aktion |
|------------|--------|
| 70-80% | Retention prüfen, Log-Level anpassen |
| 80-90% | Alte Daten löschen, Team informieren |
| 90%+ | Notfall-Bereinigung, Logging pausieren |
| 100% | Loki stoppen, Daten löschen, Recovery |

---

## Verwandte Runbooks

- [Prometheus OOM Recovery](prometheus-oom-recovery.md)
- [Host Disk Space Critical](host-disk-space-critical.md)
- [Grafana Connection Issues](grafana-connection-issues.md)
