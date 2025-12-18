# Runbook: MinIO Object Storage Recovery

> Wiederherstellung bei MinIO-Ausfaellen

## Uebersicht

| Metrik | Wert |
|--------|------|
| Severity | CRITICAL |
| RTO | 30 Minuten |
| RPO | Letztes Backup |
| On-Call | Infrastructure Team |

## Symptome

- Dokument-Upload schlaegt fehl
- Bilder werden nicht angezeigt
- OCR-Verarbeitung startet nicht
- 500er Fehler bei `/api/v1/documents/`

## Diagnose

### 1. MinIO-Status pruefen

```bash
# Container-Status
docker compose ps minio

# MinIO-Logs
docker compose logs --tail=100 minio

# Health-Check
curl -f http://localhost:9000/minio/health/live
curl -f http://localhost:9000/minio/health/ready
```

### 2. MinIO Client (mc) verwenden

```bash
# mc konfigurieren
docker compose exec minio mc alias set local http://localhost:9000 ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY}

# Buckets auflisten
docker compose exec minio mc ls local/

# Bucket-Status
docker compose exec minio mc admin info local/
```

### 3. Disk-Space pruefen

```bash
# Host-Disk
df -h

# MinIO Volume
docker system df -v | grep minio
```

### 4. Haeufige Fehler

| Fehler | Ursache |
|--------|---------|
| `Access Denied` | Falsche Credentials |
| `NoSuchBucket` | Bucket existiert nicht |
| `disk not found` | Volume nicht gemounted |
| `XMinioStorageFull` | Speicher voll |

## Recovery-Schritte

### Fall 1: MinIO Container gestoppt

```bash
# Neustart
docker compose up -d minio

# Warten auf Start
sleep 10

# Verifizieren
curl -f http://localhost:9000/minio/health/live
```

### Fall 2: Buckets nicht vorhanden

```bash
# Buckets erstellen
docker compose exec minio mc mb local/documents --ignore-existing
docker compose exec minio mc mb local/processed --ignore-existing
docker compose exec minio mc mb local/thumbnails --ignore-existing

# Bucket-Policy setzen (falls noetig)
docker compose exec minio mc anonymous set download local/thumbnails
```

### Fall 3: Speicher voll

```bash
# Alte Dateien identifizieren
docker compose exec minio mc find local/ --older-than 365d --name "*.tmp"

# Temporaere Dateien loeschen
docker compose exec minio mc rm --recursive --force local/temp/

# Alte Thumbnails loeschen (regenerierbar)
docker compose exec minio mc rm --recursive --force --older-than 180d local/thumbnails/
```

### Fall 4: Korrupte Daten

```bash
# MinIO stoppen
docker compose stop minio

# Volume sichern
sudo tar -czf /backups/minio_volume_$(date +%Y%m%d).tar.gz \
  /var/lib/docker/volumes/ablage_minio_data/

# MinIO Data loeschen (ACHTUNG: Datenverlust!)
sudo rm -rf /var/lib/docker/volumes/ablage_minio_data/_data/*

# Aus Backup wiederherstellen
./scripts/restore.sh minio /backups/minio_backup_latest.tar.gz

# MinIO starten
docker compose up -d minio
```

### Fall 5: Authentifizierung schlaegt fehl

```bash
# Credentials pruefen
grep MINIO_ .env

# Credentials in MinIO zuruecksetzen
docker compose exec minio mc admin user add local ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY}
docker compose exec minio mc admin policy attach local readwrite --user ${MINIO_ACCESS_KEY}
```

## Daten aus Backup wiederherstellen

```bash
# 1. MinIO stoppen
docker compose stop minio

# 2. Volume leeren
sudo rm -rf /var/lib/docker/volumes/ablage_minio_data/_data/*

# 3. Backup entpacken
sudo tar -xzf /backups/minio_backup_latest.tar.gz \
  -C /var/lib/docker/volumes/ablage_minio_data/_data/

# 4. MinIO starten
docker compose up -d minio

# 5. Verifizieren
docker compose exec minio mc ls local/documents/ | head -10
```

## Verifizierung

Nach Recovery:

```bash
# 1. Health-Checks
curl -f http://localhost:9000/minio/health/live
curl -f http://localhost:9000/minio/health/ready

# 2. Bucket-Zugriff
docker compose exec minio mc ls local/documents/

# 3. Upload-Test
echo "test" > /tmp/test.txt
docker compose exec minio mc cp /tmp/test.txt local/documents/test.txt
docker compose exec minio mc rm local/documents/test.txt

# 4. API-Test
curl -X POST http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer <token>" \
  -F "file=@test.pdf"
```

## Eskalation

| Zeit | Aktion |
|------|--------|
| 10 min | MinIO neugestartet |
| 30 min | Eskalation an Infrastructure Lead |
| 60 min | Eskalation an CTO |

## Praevention

- MinIO Erasure Coding (Multi-Disk)
- Regelmaessige Backups (taeglich)
- Disk-Space Monitoring (Alert bei >80%)
- Object Versioning aktivieren
- Object Lifecycle Policies

---

*Letzte Aktualisierung: 2024-12*
