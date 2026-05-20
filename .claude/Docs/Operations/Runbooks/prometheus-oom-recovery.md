# Prometheus Out of Memory Recovery Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High)
> RTO: 15 Minuten | RPO: Metriken (max. 2h Datenverlust möglich)

## Alert

```
PrometheusOOMKilled - Prometheus Container OOM-killed
PrometheusHighMemory - Memory > 80%
PrometheusRestarting - Mehrere Restarts in 10 Minuten
```

## Symptome

- Prometheus-Container startet neu
- Grafana zeigt "No data" oder Lücken
- Alertmanager empfängt keine Alerts
- Docker logs zeigen "OOMKilled"
- Metriken fehlen für bestimmte Zeiträume

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Container-Status prüfen

```bash
# Prometheus-Status
docker ps -a | grep prometheus

# OOM-Kill prüfen
docker inspect ablage-prometheus --format='{{.State.OOMKilled}}'

# Letzte Logs
docker logs ablage-prometheus --tail 50

# Container-Statistiken
docker stats ablage-prometheus --no-stream
```

### 2. Memory-Nutzung analysieren

```bash
# Host-Memory
free -h

# Docker Memory-Limits
docker inspect ablage-prometheus --format='{{.HostConfig.Memory}}'

# Prometheus-interne Metriken (falls erreichbar)
curl -s http://localhost:9090/api/v1/status/runtimeinfo | jq

# TSDB-Status
curl -s http://localhost:9090/api/v1/status/tsdb | jq
```

### 3. Prometheus neustarten

```bash
# Einfacher Neustart
docker-compose restart prometheus

# Falls Container nicht startet: Logs prüfen
docker logs ablage-prometheus --since 5m

# Falls Memory-Limit zu niedrig: Limit erhöhen
docker update --memory 4g --memory-swap 6g ablage-prometheus
docker-compose restart prometheus
```

---

## Diagnose

### 4. TSDB-Größe analysieren

```bash
# Prometheus Datenverzeichnis
du -sh /var/lib/docker/volumes/prometheus_data/_data/

# TSDB-Blöcke
ls -lah /var/lib/docker/volumes/prometheus_data/_data/

# WAL-Größe (Write-Ahead Log)
du -sh /var/lib/docker/volumes/prometheus_data/_data/wal/
```

### 5. Kardinalität prüfen

```bash
# Metriken mit höchster Kardinalität
curl -s http://localhost:9090/api/v1/label/__name__/values | jq '.data | length'

# Top-10 Serien pro Metrik
curl -s 'http://localhost:9090/api/v1/query?query=topk(10,count by(__name__)({__name__=~".+"}))' | jq

# Gesamt-Zeitreihen
curl -s http://localhost:9090/api/v1/status/tsdb | jq '.data.headStats.numSeries'
```

### 6. Scrape-Targets analysieren

```bash
# Aktive Targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets | length'

# Targets mit vielen Serien
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.lastSampleCount > 1000)'

# Fehlerhafte Targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up")'
```

---

## Lösung

### Option A: Memory-Limit erhöhen

```yaml
# docker-compose.yml anpassen
services:
  prometheus:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

```bash
# Oder via docker update
docker update --memory 4g ablage-prometheus
docker-compose restart prometheus
```

### Option B: Retention reduzieren

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Oder via Command-Line-Flags
command:
  - '--config.file=/etc/prometheus/prometheus.yml'
  - '--storage.tsdb.path=/prometheus'
  - '--storage.tsdb.retention.time=7d'    # Reduziert von 15d
  - '--storage.tsdb.retention.size=10GB'  # Max. Größe begrenzen
```

```bash
# Anwenden
docker-compose down prometheus
docker-compose up -d prometheus
```

### Option C: Scrape-Intervall erhöhen

```yaml
# prometheus.yml - Für ressourcenintensive Targets
scrape_configs:
  - job_name: 'node_exporter'
    scrape_interval: 30s  # Erhöht von 15s

  - job_name: 'cadvisor'
    scrape_interval: 60s  # Container-Metriken seltener

  - job_name: 'application'
    scrape_interval: 15s  # Kritische App-Metriken normal
```

### Option D: Hochkardinalitäts-Metriken droppen

```yaml
# prometheus.yml - Metric Relabeling
scrape_configs:
  - job_name: 'backend'
    metric_relabel_configs:
      # Hochkardinalitäts-Labels entfernen
      - source_labels: [path]
        regex: '/api/v1/documents/[0-9a-f-]+.*'
        action: drop

      # Histogramm-Buckets reduzieren
      - source_labels: [__name__]
        regex: '.*_bucket'
        action: drop

      # Unwichtige Metriken entfernen
      - source_labels: [__name__]
        regex: 'go_.*|process_.*'
        action: drop
```

### Option E: Remote Write aktivieren (Langfristig)

```yaml
# prometheus.yml - Daten zu Remote-Storage
remote_write:
  - url: "http://thanos-receive:10908/api/v1/receive"
    write_relabel_configs:
      - source_labels: [__name__]
        regex: 'job:.*|instance:.*'  # Nur aggregierte Metriken
        action: keep

# Lokale Retention minimal
command:
  - '--storage.tsdb.retention.time=6h'
```

---

## TSDB-Bereinigung

### Alte Daten löschen

```bash
# Prometheus stoppen
docker-compose stop prometheus

# Backup erstellen
cp -r /var/lib/docker/volumes/prometheus_data/_data/ /backup/prometheus_$(date +%Y%m%d)/

# WAL bereinigen (vorsichtig!)
rm -rf /var/lib/docker/volumes/prometheus_data/_data/wal/*

# Alte Blöcke löschen (älter als Retention)
find /var/lib/docker/volumes/prometheus_data/_data/ -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;

# Prometheus starten
docker-compose start prometheus
```

### Kompaktierung erzwingen

```bash
# Prometheus Admin API (falls aktiviert)
curl -X POST http://localhost:9090/api/v1/admin/tsdb/clean_tombstones

# Snapshot erstellen (reduziert WAL)
curl -X POST http://localhost:9090/api/v1/admin/tsdb/snapshot
```

---

## Monitoring-Optimierung

### Query-Optimierung

```bash
# Langsame Queries identifizieren
docker logs ablage-prometheus --since 1h 2>&1 | grep "slow query"

# Query-Log aktivieren
# prometheus.yml
query_log_file: /prometheus/query.log
```

### Recording Rules hinzufügen

```yaml
# /etc/prometheus/rules/recording.yml
groups:
  - name: aggregations
    interval: 1m
    rules:
      # Voraggregierte Metriken statt Live-Berechnung
      - record: job:http_requests:rate5m
        expr: sum(rate(http_requests_total[5m])) by (job)

      - record: job:http_request_duration_seconds:p99
        expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (job, le))
```

---

## Verifikation

```bash
# Prometheus erreichbar?
curl -s http://localhost:9090/-/healthy

# TSDB-Status nach Bereinigung
curl -s http://localhost:9090/api/v1/status/tsdb | jq '.data.headStats'

# Memory-Nutzung
docker stats ablage-prometheus --no-stream

# Metriken-Lücken prüfen (in Grafana)
# Query: up{job="backend"}
# Erwartung: Keine Lücken in letzter Stunde
```

---

## Präventivmaßnahmen

### 1. Memory-Alerts

```yaml
# Prometheus Alert Rules
- alert: PrometheusHighMemory
  expr: process_resident_memory_bytes{job="prometheus"} / 1024 / 1024 / 1024 > 3
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Prometheus Memory > 3GB"

- alert: PrometheusTSDBFull
  expr: prometheus_tsdb_storage_blocks_bytes / 1024 / 1024 / 1024 > 8
  for: 5m
  labels:
    severity: warning
```

### 2. Kardinalitäts-Monitoring

```yaml
- alert: HighCardinality
  expr: prometheus_tsdb_head_series > 1000000
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Mehr als 1M aktive Zeitreihen"
```

### 3. Automatische Retention

```bash
# Cronjob für TSDB-Bereinigung
cat > /etc/cron.weekly/prometheus-cleanup << 'EOF'
#!/bin/bash
# Alte Snapshots löschen
find /prometheus/snapshots -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
EOF
chmod +x /etc/cron.weekly/prometheus-cleanup
```

---

## Eskalation

| Memory-Nutzung | Aktion |
|----------------|--------|
| 60-80% | Beobachten, Kardinalität prüfen |
| 80-90% | Retention/Scrape-Intervall anpassen |
| 90%+ | Memory-Limit erhöhen, alte Daten löschen |
| OOM-Kill | Sofort-Neustart, Datenbereinigung |

---

## Metriken & Dashboards

- **Grafana Dashboard**: "Prometheus Internal Metrics"
- **Wichtige Metriken**:
  ```promql
  # Memory-Nutzung
  process_resident_memory_bytes{job="prometheus"}

  # TSDB-Größe
  prometheus_tsdb_storage_blocks_bytes

  # Aktive Zeitreihen
  prometheus_tsdb_head_series

  # Scrape-Duration
  prometheus_target_scrape_pool_sync_total
  ```

---

## Verwandte Runbooks

- [Loki Disk Space Crisis](loki-disk-space-crisis.md)
- [Grafana Connection Issues](grafana-connection-issues.md)
- [Host Disk Space Critical](host-disk-space-critical.md)
