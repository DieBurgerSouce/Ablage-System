---
name: backup-ops
description: Backup und Monitoring Operationen fuer das Ablage-System. Nutze diesen Skill fuer Backup-Status, Restore-Prozeduren, Grafana Dashboards, Prometheus Alerts und Disaster Recovery.
---

# Backup & Monitoring Operations (Ablage-System)

Vollautomatisches Backup-System mit Monitoring.

## Quick Status

```bash
# Backup-Status abfragen
curl http://localhost:8000/api/v1/backup/status

# Letzte Backups auflisten
curl http://localhost:8000/api/v1/backup/list
```

## Backup-Komponenten

| Komponente | Methode | Speicherort |
|------------|---------|-------------|
| PostgreSQL | pg_dump + gzip | `/backups/postgres/` |
| Redis | BGSAVE | `/backups/redis/` |
| MinIO | mc mirror | `/backups/minio/` |
| Konfiguration | tar | `/backups/config/` |

## Manuelle Backups

```bash
# Vollstaendiges Backup
curl -X POST http://localhost:8000/api/v1/backup/full

# Nur PostgreSQL
curl -X POST http://localhost:8000/api/v1/backup/postgres

# Nur MinIO (Dokumente)
curl -X POST http://localhost:8000/api/v1/backup/minio
```

## Automatische Backups (Celery Beat)

| Task | Zeitplan |
|------|----------|
| Vollstaendiges Backup | Taeglich 02:30 |
| Retention-Policy | Sonntag 03:00 |
| Remote-Sync | Taeglich 04:00 |
| Metriken-Update | Alle 15 Min |

## Restore-Prozeduren

### PostgreSQL Restore

```bash
# 1. Services stoppen (ausser Postgres)
docker-compose stop backend worker

# 2. Backup finden
ls -la /backups/postgres/

# 3. Restore durchfuehren
docker-compose exec postgres bash -c \
  "gunzip -c /backups/postgres/backup_2024-12-29.sql.gz | psql -U postgres -d ablage"

# 4. Services starten
docker-compose up -d backend worker
```

### Redis Restore

```bash
# 1. Redis stoppen
docker-compose stop redis

# 2. RDB-Datei kopieren
cp /backups/redis/dump.rdb /var/lib/redis/

# 3. Redis starten
docker-compose up -d redis
```

### MinIO Restore

```bash
# Mit mc (MinIO Client)
mc mirror /backups/minio/ local/documents/
```

## Monitoring Dashboards

| Dashboard | URL | Beschreibung |
|-----------|-----|--------------|
| Backup Monitoring | http://localhost:3002/d/ablage-backup-monitoring | Backup-Status |
| System Health | http://localhost:3002/d/system-health | CPU, RAM, Disk |
| OCR Performance | http://localhost:3002/d/ocr-performance | OCR Metriken |
| GPU Monitoring | http://localhost:3002/d/gpu-monitoring | VRAM, Auslastung |

**Grafana Login**: admin / admin123

## Prometheus Alerts

8 vordefinierte Alerts:

1. **BackupFailed** - Backup fehlgeschlagen
2. **BackupOld** - Letztes Backup > 24h alt
3. **DiskSpaceLow** - Festplatte < 10% frei
4. **GPUMemoryHigh** - VRAM > 90%
5. **WorkerDown** - Celery Worker nicht erreichbar
6. **DatabaseConnectionsHigh** - Postgres > 80% Connections
7. **RedisMemoryHigh** - Redis > 80% Memory
8. **APILatencyHigh** - API Response > 5s

## Alert-Status pruefen

```bash
# Aktive Alerts
curl http://localhost:9090/api/v1/alerts

# Alert-Regeln
curl http://localhost:9090/api/v1/rules
```

## Retention Policy

```bash
# Alte Backups loeschen (aelter als 30 Tage)
curl -X POST http://localhost:8000/api/v1/backup/retention

# Retention-Einstellungen (in app/core/config.py)
BACKUP_RETENTION_DAYS = 30
BACKUP_KEEP_WEEKLY = 4   # Woechentliche behalten
BACKUP_KEEP_MONTHLY = 3  # Monatliche behalten
```

## Remote-Sync

```bash
# Manueller Sync zu Remote-Storage
curl -X POST http://localhost:8000/api/v1/backup/sync

# Konfiguration (Environment)
BACKUP_REMOTE_URL=sftp://backup-server/ablage/
BACKUP_REMOTE_KEY=/path/to/ssh/key
```

## Disaster Recovery Checklist

1. **Letztes Backup identifizieren**
   ```bash
   curl http://localhost:8000/api/v1/backup/list | jq '.[0]'
   ```

2. **Integritaet pruefen**
   ```bash
   gunzip -t /backups/postgres/backup_latest.sql.gz
   ```

3. **Services stoppen**
   ```bash
   docker-compose down
   ```

4. **Daten wiederherstellen**
   - PostgreSQL (siehe oben)
   - Redis (siehe oben)
   - MinIO (siehe oben)

5. **Services starten**
   ```bash
   docker-compose up -d
   ```

6. **Verifizieren**
   ```bash
   curl http://localhost:8000/health
   ```

## Backup-Metriken

```bash
# Prometheus Metriken
curl http://localhost:8000/api/v1/metrics/backup

# Wichtige Metriken:
# - backup_last_success_timestamp
# - backup_size_bytes
# - backup_duration_seconds
# - backup_files_count
```

## Log-Analyse

```bash
# Backup-Logs in Loki/Grafana
# Label: {job="backup"}

# Oder direkt in Docker
docker-compose logs worker | grep -i backup
```
