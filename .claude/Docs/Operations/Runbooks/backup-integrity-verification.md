# Backup Integrity Verification Failure Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High) - Disaster Recovery gefährdet
> RTO: 1 Stunde | RPO: Letztes gültiges Backup

## Alert

```
BackupIntegrityCheckFailed - Backup-Verifizierung fehlgeschlagen
BackupRestoreTestFailed - Test-Restore fehlgeschlagen
BackupChecksumMismatch - Prüfsumme stimmt nicht
BackupCorrupted - Backup-Datei beschädigt
```

## Symptome

- Backup-Verifizierungsjob schlägt fehl
- Restore-Tests enden mit Fehlern
- Backup-Dateien sind kleiner als erwartet
- Prüfsummen stimmen nicht überein
- pg_restore meldet Fehler

---

## Sofortmaßnahmen (< 10 Minuten)

### 1. Backup-Status prüfen

```bash
# Letzte Backups auflisten
ls -lah /backup/

# Neuestes Backup prüfen
LATEST=$(ls -t /backup/*.gz 2>/dev/null | head -1)
echo "Latest backup: $LATEST"
ls -lah "$LATEST"

# Backup-Größe plausibel?
# PostgreSQL: Minimum ~10MB für leere DB
# Mit Daten: Proportional zur Dokumentenzahl
```

### 2. Backup-Integrität testen

```bash
# Gzip-Integrität
gunzip -t /backup/postgres_latest.gz

# PostgreSQL-Backup prüfen
pg_restore --list /backup/postgres_latest.dump | head -20

# Prüfsumme verifizieren (falls vorhanden)
if [ -f /backup/postgres_latest.gz.sha256 ]; then
    sha256sum -c /backup/postgres_latest.gz.sha256
fi
```

### 3. Backup-Logs analysieren

```bash
# Letzte Backup-Jobs
docker logs ablage-backend --since 24h 2>&1 | grep -E "backup|Backup|BACKUP"

# Celery-Backup-Tasks
docker exec ablage-worker celery -A app.workers.celery_app inspect query_task backup

# Backup-API-Status
curl -s http://localhost:8000/api/v1/backup/status | jq
```

---

## Diagnose

### 4. Backup-Dateien analysieren

```bash
# Alle Backups mit Größe und Datum
ls -lah /backup/ | sort -k5 -h

# Backup-Größen-Trend
for f in /backup/postgres_*.gz; do
    size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
    date=$(stat -c%y "$f" 2>/dev/null || stat -f%Sm "$f" 2>/dev/null)
    echo "$date: $(numfmt --to=iec $size) - $(basename $f)"
done | tail -10

# Ungewöhnlich kleine Backups identifizieren
find /backup -name "*.gz" -size -1M -ls
```

### 5. PostgreSQL-Backup-Inhalt prüfen

```bash
# Backup entpacken (temporär)
gunzip -k /backup/postgres_latest.gz -c > /tmp/postgres_check.dump

# TOC (Table of Contents) auslesen
pg_restore --list /tmp/postgres_check.dump > /tmp/backup_toc.txt
cat /tmp/backup_toc.txt

# Kritische Tabellen vorhanden?
grep -E "documents|users|audit_logs" /tmp/backup_toc.txt

# Aufräumen
rm /tmp/postgres_check.dump /tmp/backup_toc.txt
```

### 6. Test-Restore durchführen

```bash
# Test-Datenbank erstellen
docker exec ablage-postgres psql -U ablage_admin -c "CREATE DATABASE backup_test;"

# Restore in Test-DB
docker exec -i ablage-postgres pg_restore \
    -U ablage_admin \
    -d backup_test \
    --no-owner \
    --no-privileges \
    < /backup/postgres_latest.dump

# Daten validieren
docker exec ablage-postgres psql -U ablage_admin -d backup_test -c "
SELECT
    (SELECT count(*) FROM documents) as documents,
    (SELECT count(*) FROM users) as users,
    (SELECT max(created_at) FROM documents) as latest_doc;
"

# Test-DB löschen
docker exec ablage-postgres psql -U ablage_admin -c "DROP DATABASE backup_test;"
```

---

## Fehlerbehandlung

### Fehler: "Corrupted archive"

```bash
# Backup erneut erstellen
docker exec ablage-postgres pg_dump \
    -U ablage_admin \
    -d ablage \
    -F c \
    -f /tmp/fresh_backup.dump

# Verifizieren
pg_restore --list /tmp/fresh_backup.dump

# Komprimieren und speichern
gzip /tmp/fresh_backup.dump
mv /tmp/fresh_backup.dump.gz /backup/postgres_$(date +%Y%m%d_%H%M%S).gz
```

### Fehler: "Checksum mismatch"

```bash
# Neue Prüfsumme erstellen
sha256sum /backup/postgres_latest.gz > /backup/postgres_latest.gz.sha256

# Oder: Backup als ungültig markieren und neu erstellen
mv /backup/postgres_latest.gz /backup/INVALID_postgres_$(date +%Y%m%d).gz

# Frisches Backup erstellen
curl -X POST http://localhost:8000/api/v1/backup/full \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Fehler: "Missing tables in backup"

```bash
# Erwartete Tabellen
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
"

# Tabellen im Backup
pg_restore --list /backup/postgres_latest.dump | grep "TABLE"

# Falls Tabellen fehlen: Schema-only + Data-only Backup
docker exec ablage-postgres pg_dump \
    -U ablage_admin \
    -d ablage \
    --schema-only \
    -f /tmp/schema.sql

docker exec ablage-postgres pg_dump \
    -U ablage_admin \
    -d ablage \
    --data-only \
    -f /tmp/data.sql
```

### Fehler: "Insufficient disk space during backup"

```bash
# Disk-Space prüfen
df -h /backup

# Alte Backups löschen
find /backup -name "*.gz" -mtime +30 -delete

# Backup-Verzeichnis bereinigen
du -sh /backup/*

# Backup mit Komprimierung während des Dumps
docker exec ablage-postgres pg_dump \
    -U ablage_admin \
    -d ablage \
    -F c \
    -Z 9 \
    -f /tmp/compressed_backup.dump
```

---

## MinIO-Backup-Verifizierung

### Object Storage Backup prüfen

```bash
# MinIO-Status
docker exec ablage-minio mc admin info local

# Buckets auflisten
docker exec ablage-minio mc ls local/

# Backup-Bucket prüfen
docker exec ablage-minio mc ls local/backups/

# Objekt-Integrität
docker exec ablage-minio mc stat local/backups/latest.tar.gz
```

### MinIO-Backup-Sync

```bash
# Backup zu lokalem Verzeichnis
docker exec ablage-minio mc mirror local/documents /backup/minio/

# Prüfsummen generieren
docker exec ablage-minio mc hash local/documents/ --md5
```

---

## Redis-Backup-Verifizierung

```bash
# RDB-Dump Integrität
docker exec ablage-redis redis-check-rdb /data/dump.rdb

# RDB-Größe
docker exec ablage-redis ls -la /data/dump.rdb

# Manuellen Dump erstellen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD BGSAVE

# AOF-Integrität (falls aktiviert)
docker exec ablage-redis redis-check-aof /data/appendonly.aof
```

---

## Automatische Verifizierung einrichten

### Celery-Beat-Task

```python
# app/workers/tasks/backup_tasks.py
from celery import shared_task
import subprocess

@shared_task
def verify_backup_integrity():
    """Täglich: Backup-Integrität prüfen."""
    import os
    import hashlib

    backup_dir = "/backup"
    latest = max(
        (f for f in os.listdir(backup_dir) if f.endswith('.gz')),
        key=lambda f: os.path.getctime(os.path.join(backup_dir, f))
    )

    backup_path = os.path.join(backup_dir, latest)

    # 1. Gzip-Integrität
    result = subprocess.run(['gunzip', '-t', backup_path], capture_output=True)
    if result.returncode != 0:
        raise ValueError(f"Gzip integrity check failed: {result.stderr}")

    # 2. pg_restore --list
    result = subprocess.run(
        ['pg_restore', '--list', backup_path.replace('.gz', '')],
        capture_output=True
    )
    if result.returncode != 0:
        raise ValueError(f"pg_restore list failed: {result.stderr}")

    # 3. Größenprüfung (Minimum 10MB)
    size = os.path.getsize(backup_path)
    if size < 10 * 1024 * 1024:
        raise ValueError(f"Backup too small: {size} bytes")

    return {"status": "verified", "file": latest, "size": size}
```

### Cron-basierte Verifizierung

```bash
# /etc/cron.daily/verify-backups
#!/bin/bash
set -e

BACKUP_DIR="/backup"
LOG_FILE="/var/log/backup-verify.log"

echo "$(date): Starting backup verification" >> $LOG_FILE

# Neuestes Backup finden
LATEST=$(ls -t $BACKUP_DIR/postgres_*.gz 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "ERROR: No backup found!" >> $LOG_FILE
    curl -X POST $SLACK_WEBHOOK -d '{"text": "⚠️ Kein Backup gefunden!"}'
    exit 1
fi

# Gzip-Test
if ! gunzip -t "$LATEST" 2>> $LOG_FILE; then
    echo "ERROR: Gzip integrity failed!" >> $LOG_FILE
    curl -X POST $SLACK_WEBHOOK -d '{"text": "❌ Backup-Integrität fehlgeschlagen!"}'
    exit 1
fi

# Größenprüfung (min 10MB)
SIZE=$(stat -c%s "$LATEST")
if [ $SIZE -lt 10485760 ]; then
    echo "ERROR: Backup too small ($SIZE bytes)!" >> $LOG_FILE
    curl -X POST $SLACK_WEBHOOK -d '{"text": "⚠️ Backup zu klein: '"$SIZE"' bytes"}'
    exit 1
fi

echo "$(date): Verification successful - $LATEST ($SIZE bytes)" >> $LOG_FILE
```

---

## Monitoring

### Prometheus Alerts

```yaml
groups:
  - name: backup_alerts
    rules:
      - alert: BackupVerificationFailed
        expr: backup_verification_success == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Backup-Verifizierung fehlgeschlagen"

      - alert: BackupTooSmall
        expr: backup_size_bytes < 10000000
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Backup kleiner als 10MB"

      - alert: BackupTooOld
        expr: time() - backup_last_success_timestamp > 86400
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Kein erfolgreiches Backup in 24h"

      - alert: RestoreTestFailed
        expr: backup_restore_test_success == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Restore-Test fehlgeschlagen"
```

### Backup-Metriken

```python
# app/metrics.py
from prometheus_client import Gauge, Counter

backup_verification_success = Gauge(
    'backup_verification_success',
    'Last backup verification result (1=success, 0=failed)'
)

backup_size_bytes = Gauge(
    'backup_size_bytes',
    'Size of latest backup in bytes',
    ['type']  # postgres, minio, redis
)

backup_last_success_timestamp = Gauge(
    'backup_last_success_timestamp',
    'Timestamp of last successful backup'
)
```

---

## Verifikation nach Fix

```bash
# 1. Frisches Backup erstellen
curl -X POST http://localhost:8000/api/v1/backup/full \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Backup-Status prüfen
curl -s http://localhost:8000/api/v1/backup/status | jq

# 3. Integrität prüfen
LATEST=$(ls -t /backup/postgres_*.gz | head -1)
gunzip -t "$LATEST" && echo "Gzip OK"

# 4. Restore-Test
docker exec ablage-postgres psql -U ablage_admin -c "CREATE DATABASE restore_test;"
docker exec -i ablage-postgres pg_restore -U ablage_admin -d restore_test < /backup/postgres_latest.dump
docker exec ablage-postgres psql -U ablage_admin -d restore_test -c "SELECT count(*) FROM documents;"
docker exec ablage-postgres psql -U ablage_admin -c "DROP DATABASE restore_test;"

# 5. Prüfsumme erstellen
sha256sum "$LATEST" > "${LATEST}.sha256"
```

---

## Eskalation

| Problem | Aktion |
|---------|--------|
| Einzelnes korruptes Backup | Neues Backup erstellen |
| Mehrere korrupte Backups | Storage/Disk prüfen, Senior Engineer |
| Restore-Test schlägt fehl | DBA einbeziehen |
| Kein gültiges Backup verfügbar | Disaster Recovery initiieren |

---

## Verwandte Runbooks

- [Database Recovery](database-recovery.md)
- [Host Disk Space Critical](host-disk-space-critical.md)
- [MinIO Failure Recovery](minio-failure-recovery.md)
