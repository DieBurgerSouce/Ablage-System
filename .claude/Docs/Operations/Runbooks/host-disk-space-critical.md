# Host Disk Space Critical Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-1 (Critical)
> RTO: 30 Minuten | RPO: N/A

## Alert

```
HostDiskSpaceWarning - > 80% Disk Usage
HostDiskSpaceCritical - > 90% Disk Usage
DockerDiskSpaceCritical - Docker Volumes > 90%
```

## Symptome

- Container starten nicht mehr
- Datenbank-Writes schlagen fehl
- Log-Rotation gestoppt
- Backup-Jobs schlagen fehl
- MinIO kann keine Dateien mehr speichern

---

## Sofortmaßnahmen (< 10 Minuten)

### 1. Disk-Status prüfen

```bash
# Übersicht aller Mountpoints
df -h

# Detailliert mit Inodes
df -ih

# Docker-spezifisch
docker system df
```

### 2. Größte Verzeichnisse identifizieren

```bash
# Top 10 größte Verzeichnisse
du -h / --max-depth=3 2>/dev/null | sort -rh | head -20

# Docker Volumes
du -h /var/lib/docker/volumes/ --max-depth=2 | sort -rh | head -10

# Log-Verzeichnisse
du -h /var/log/ --max-depth=2 | sort -rh | head -10
```

### 3. Schnelle Bereinigung (Notfall)

```bash
# Docker: Unbenutzte Ressourcen löschen
docker system prune -f

# Alte Container-Logs (> 7 Tage)
find /var/lib/docker/containers/ -name "*-json.log" -mtime +7 -delete

# Systemd Journal begrenzen
journalctl --vacuum-size=500M
```

---

## Diagnose (10-20 Minuten)

### 4. Docker-Ressourcen analysieren

```bash
# Container-Log-Größen
for container in $(docker ps -q); do
    log_file=$(docker inspect --format='{{.LogPath}}' $container)
    if [ -f "$log_file" ]; then
        size=$(du -h "$log_file" | cut -f1)
        name=$(docker inspect --format='{{.Name}}' $container)
        echo "$size $name"
    fi
done | sort -rh | head -10

# Dangling Images
docker images -f "dangling=true" -q | wc -l

# Unbenutzte Volumes
docker volume ls -f "dangling=true" -q | wc -l
```

### 5. Datenbank-Größe prüfen

```bash
# PostgreSQL Tabellen-Größen
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
"

# PostgreSQL VACUUM-Status
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT relname, n_dead_tup, last_vacuum, last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
"
```

### 6. MinIO-Speicher analysieren

```bash
# Bucket-Größen
docker exec ablage-minio mc du --depth 1 /data/

# Alte temporäre Dateien
docker exec ablage-minio mc find /data/tmp --older-than 7d
```

---

## Bereinigung

### Option A: Docker bereinigen

```bash
# Komplette Bereinigung (vorsicht!)
docker system prune -a --volumes -f

# Nur alte Images (älter als 7 Tage)
docker image prune -a --filter "until=168h" -f

# Nur Build-Cache
docker builder prune -f
```

### Option B: Log-Rotation anpassen

```bash
# Docker Log-Limits setzen
cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  }
}
EOF

# Docker neu starten
systemctl restart docker

# Oder per Container
docker update --log-opt max-size=50m --log-opt max-file=3 ablage-backend
```

### Option C: Datenbank bereinigen

```bash
# VACUUM FULL (blockiert, aber effektiv)
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "VACUUM FULL ANALYZE;"

# Alte Audit-Logs löschen (> 90 Tage)
docker exec ablage-backend python -c "
from app.services.audit_service import AuditService
from datetime import datetime, timedelta

svc = AuditService()
deleted = svc.delete_old_logs(before=datetime.utcnow() - timedelta(days=90))
print(f'{deleted} Audit-Logs gelöscht')
"

# Alte OCR-Ergebnisse komprimieren
docker exec ablage-backend python -c "
from app.services.document_archive_service import DocumentArchiveService
svc = DocumentArchiveService()
archived = svc.archive_old_documents(days=365)
print(f'{archived} Dokumente archiviert')
"
```

### Option D: MinIO bereinigen

```bash
# Temporäre Dateien löschen
docker exec ablage-minio mc rm --older-than 7d --recursive /data/tmp/

# Alte Versionen entfernen (falls Versioning aktiv)
docker exec ablage-minio mc ilm rule add /data/documents --expire-days 365

# Lifecycle-Policy anwenden
docker exec ablage-minio mc ilm rule list /data/documents
```

### Option E: Alte Backups löschen

```bash
# Backup-Retention prüfen
ls -lah /backup/

# Alte Backups manuell löschen (> 30 Tage)
find /backup -name "*.gz" -mtime +30 -delete

# Oder via API
curl -X POST http://localhost:8000/api/v1/backup/retention \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}'
```

---

## Langfristige Maßnahmen

### 1. Monitoring einrichten

```bash
# Prometheus Alert anpassen
cat >> infrastructure/prometheus/rules/disk-alerts.yml << 'EOF'
- alert: HostDiskSpaceWarning
  expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 20
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Host disk space low"
    description: "Disk space is below 20%"
EOF
```

### 2. Automatische Log-Rotation

```bash
# Logrotate für Docker Logs
cat > /etc/logrotate.d/docker << 'EOF'
/var/lib/docker/containers/*/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
```

### 3. Scheduled Cleanup Jobs

```bash
# Cronjob für wöchentliche Bereinigung
cat > /etc/cron.weekly/docker-cleanup << 'EOF'
#!/bin/bash
docker system prune -f
docker image prune -a --filter "until=168h" -f
find /var/log -name "*.gz" -mtime +30 -delete
EOF
chmod +x /etc/cron.weekly/docker-cleanup
```

---

## Verifikation

```bash
# Disk-Status nach Bereinigung
df -h

# Docker-Ressourcen
docker system df

# Freier Speicher pro Container
for vol in $(docker volume ls -q); do
    size=$(docker run --rm -v $vol:/data alpine du -sh /data 2>/dev/null | cut -f1)
    echo "$size $vol"
done | sort -rh | head -10
```

---

## Kapazitätsplanung

### Speicherprognose

```bash
# Wachstumsrate berechnen (letzte 30 Tage)
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT
    date_trunc('day', created_at) as day,
    COUNT(*) as documents,
    SUM(file_size) / 1024 / 1024 as mb_added
FROM documents
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
"
```

### Empfohlene Speichergrößen

| Komponente | Minimum | Empfohlen | Für 100k Dokumente |
|------------|---------|-----------|-------------------|
| PostgreSQL | 20 GB | 50 GB | 100 GB |
| MinIO | 100 GB | 500 GB | 1 TB |
| Docker Volumes | 50 GB | 100 GB | 200 GB |
| Logs | 10 GB | 20 GB | 50 GB |

---

## Eskalation

| Disk Usage | Aktion |
|------------|--------|
| 80-85% | On-Call: Bereinigung planen |
| 85-90% | Sofortige Bereinigung |
| 90-95% | Notfall-Bereinigung, Team informieren |
| 95%+ | Eskalation, ggf. Service stoppen |

---

## Verwandte Runbooks

- [Database Recovery](database-recovery.md)
- [MinIO Storage Recovery](minio-failure-recovery.md)
- [Backup & Retention](backup-retention.md)
