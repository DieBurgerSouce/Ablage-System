# Loki Monitoring & Retention Runbook

**Erstellt**: 2026-01-02
**Status**: Aktiv
**Komponente**: Loki Log-Aggregation

## Uebersicht

Dieses Runbook beschreibt das Monitoring und Alerting fuer den Loki Log-Aggregations-Service im Ablage-System OCR.

## Konfiguration

### Aktuelle Retention-Einstellungen

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| `retention_period` | 720h (30 Tage) | Maximale Log-Aufbewahrungsdauer |
| `compaction_interval` | 10m | Haeufigkeit der Compaction-Laeufe |
| `retention_delete_delay` | 2h | Verzoegerung vor dem Loeschen |
| `ingestion_rate_mb` | 16 MB/s | Max. Ingestion-Rate |
| `ingestion_burst_size_mb` | 32 MB | Max. Burst-Groesse |
| `max_streams_per_user` | 10.000 | Max. aktive Log-Streams |
| `max_line_size` | 256 KB | Max. Laenge einer Log-Zeile |

### Dateipfade

- **Loki-Konfiguration**: `infrastructure/loki/loki-config.yml`
- **Prometheus Alert Rules**: `infrastructure/prometheus/rules/loki-alerts.yml`
- **Grafana Dashboard**: `infrastructure/grafana/dashboards/ablage-loki-retention.json`

## Alerts

### Kritische Alerts

| Alert | Schwelle | Beschreibung |
|-------|----------|--------------|
| `LokiDiskUsageHigh` | >80% | Loki-Speicher kritisch voll |
| `LokiCompactorNotRunning` | 30m inaktiv | Retention funktioniert nicht |
| `LokiChunkStoreWriteErrors` | >0 | Log-Datenverlust moeglich |
| `LokiWALWriteErrors` | >0 | Write-Ahead-Log-Fehler |
| `LokiDown` | 1m | Service nicht erreichbar |
| `LokiIngestionRateCritical` | >50 MB/s | Log-Storm erkannt |

### Warn-Alerts

| Alert | Schwelle | Beschreibung |
|-------|----------|--------------|
| `LokiDiskUsageWarning` | >60% | Speicher erhoet |
| `LokiChunkStoreSizeTooLarge` | >100.000 Chunks | Ungewoehnlich viele Chunks |
| `LokiCompactionFailed` | >0 in 1h | Compaction-Fehler |
| `LokiRetentionDeleteFailed` | >0 in 1h | Loeschung fehlgeschlagen |
| `LokiIngestionRateHigh` | >16 MB/s | Rate ueber Limit |
| `LokiTooManyStreams` | >8.000 | Stream-Limit naehert sich |
| `LokiHighLatency` | p99 >5s | Langsame Anfragen |
| `LokiPushRequestsFailing` | >1% | Logs gehen verloren |

### Info-Alerts

| Alert | Schwelle | Beschreibung |
|-------|----------|--------------|
| `LokiCompactionStale` | >2h | Keine Compaction |
| `LokiSlowQueries` | p95 >30s | Langsame Queries |
| `LokiQueryQueueFull` | >50 | Query-Stau |

## Troubleshooting

### Hohe Disk-Auslastung

1. **Pruefen**: Aktuelle Auslastung in Grafana Dashboard
2. **Ursachen**:
   - Retention funktioniert nicht (Compactor pruefen)
   - Zu hohe Ingestion-Rate (Log-Storm)
   - Retention-Periode zu lang
3. **Massnahmen**:
   ```bash
   # Compactor-Status pruefen
   docker-compose logs loki | grep compactor

   # Manuell alte Chunks loeschen (Notfall)
   # ACHTUNG: Nur nach Ruecksprache!
   docker-compose exec loki loki-compactor --config.file=/etc/loki/local-config.yaml
   ```

### Compactor nicht aktiv

1. **Pruefen**: `loki_compactor_running` Metrik
2. **Ursachen**:
   - Loki-Container nicht gestartet
   - Konfigurationsfehler
   - Filesystem-Berechtigungen
3. **Massnahmen**:
   ```bash
   # Container-Status
   docker-compose ps loki

   # Logs pruefen
   docker-compose logs --tail=100 loki

   # Neustart
   docker-compose restart loki
   ```

### Log-Storm (hohe Ingestion-Rate)

1. **Pruefen**: `loki_distributor_bytes_received_total` Rate
2. **Ursachen**:
   - Endlosschleife in Anwendung
   - Debug-Logging versehentlich aktiviert
   - Fehlende Log-Level-Filterung
3. **Massnahmen**:
   ```bash
   # Top-Log-Produzenten identifizieren
   # Im Grafana Dashboard unter "Ingestion nach Container/Service"

   # Log-Level anpassen (app/core/logging.py)
   # DEBUG -> INFO oder WARNING

   # Promtail-Filter hinzufuegen
   ```

### Logs fehlen

1. **Pruefen**: Push-Erfolgsrate in Dashboard
2. **Ursachen**:
   - Rate-Limiting aktiv
   - Stream-Limit erreicht
   - Netzwerkprobleme
3. **Massnahmen**:
   ```bash
   # Promtail-Status pruefen
   docker-compose logs promtail | grep -E "error|failed"

   # Stream-Count pruefen
   curl -s http://localhost:3100/metrics | grep loki_ingester_streams
   ```

## Grafana Dashboard

Das Dashboard "Ablage-System OCR - Loki Retention" (`ablage-loki-retention`) zeigt:

### Sektion: Service Status
- Loki Online/Offline Status
- Compactor aktiv/inaktiv
- Konfigurierte Retention-Periode
- Aktive Chunks und Streams
- Zeit seit letzter Compaction

### Sektion: Speicher & Retention
- Disk-Auslastung (Gauge und Verlauf)
- Compaction-Laeufe (erfolgreich/fehlgeschlagen)

### Sektion: Log-Ingestion
- Aktuelle Ingestion-Rate (MB/s)
- Datenvolumen und Zeilenanzahl heute
- Ingestion-Rate ueber Zeit
- Aufschluesselung nach Container/Service

### Sektion: Performance & Fehler
- Push-Erfolgsrate
- Request-Latenz (p50, p99)
- Fehler nach Typ (Chunk, WAL, Push)

### Sektion: Retention-Details
- Delete-Operationen (letzte 24h)
- Chunks im Speicher (aktiv, flushing)
- Konfigurierte Limits

## Prometheus Scrape-Konfiguration

Loki wird von Prometheus gescraped unter:

```yaml
- job_name: 'loki'
  metrics_path: '/metrics'
  scrape_interval: 30s
  static_configs:
    - targets: ['loki:3100']
```

## Wartungsaufgaben

### Taeglich (automatisch)
- Compaction laeuft alle 10 Minuten
- Retention loescht Logs aelter als 30 Tage

### Woechentlich
- Dashboard auf Trends pruefen
- Disk-Wachstum analysieren

### Monatlich
- Retention-Periode evaluieren
- Ingestion-Limits anpassen falls noetig
- Archivierung aelterer Logs pruefen (S3/MinIO)

## Eskalation

1. **Level 1**: DevOps-Team (Alerts, Container-Restart)
2. **Level 2**: Platform-Team (Konfigurationsaenderungen)
3. **Level 3**: Architektur-Team (Skalierungsentscheidungen)

## Referenzen

- [Loki Dokumentation](https://grafana.com/docs/loki/latest/)
- [Loki Retention Konfiguration](https://grafana.com/docs/loki/latest/operations/storage/retention/)
- [Loki Metriken Referenz](https://grafana.com/docs/loki/latest/operations/observability/)
