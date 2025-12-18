# Disaster Recovery Objectives

## Ablage-System OCR Platform

**Version**: 1.0
**Erstellt**: 2024-12-18
**Status**: Production

---

## Recovery Objectives

### RTO (Recovery Time Objective)

Die maximale akzeptable Zeit, um das System nach einem Ausfall wiederherzustellen.

| Komponente | RTO | Priorität | Begründung |
|------------|-----|-----------|------------|
| **Vollständiges System** | 4 Stunden | P0 | Geschäftskritisch |
| **PostgreSQL Datenbank** | 1 Stunde | P0 | Kern-Datenbestand |
| **MinIO Dokumente** | 2 Stunden | P1 | Große Datenmenge |
| **Redis Cache** | 15 Minuten | P2 | Kann rebuilt werden |
| **Konfiguration** | 30 Minuten | P1 | Schnell aus Backup |
| **OCR Worker** | 30 Minuten | P2 | Container-Restart |

### RPO (Recovery Point Objective)

Der maximale akzeptable Datenverlust, gemessen in Zeit.

| Komponente | RPO | Methode | Frequenz |
|------------|-----|---------|----------|
| **PostgreSQL** | 15 Minuten | WAL Streaming + pg_dump | Kontinuierlich + täglich |
| **MinIO Dokumente** | 1 Stunde | mc mirror | Stündlich |
| **Redis** | 5 Minuten | AOF (appendfsync everysec) | Jede Sekunde |
| **Konfiguration** | 24 Stunden | tar Archive | Täglich |

---

## Backup-Strategie

### Automatische Backups (Celery Beat)

```
┌─────────────────────────────────────────────────────────────┐
│                    Backup Schedule                          │
├─────────────────────────────────────────────────────────────┤
│ 02:30 UTC │ Vollständiges Backup (PostgreSQL + MinIO + Config)
│ 03:00 UTC │ Retention Policy (Alte Backups löschen)
│ 04:00 UTC │ Remote Sync (MinIO Replikation)
│ Alle 15 Min│ Metriken-Update (Backup Status)
└─────────────────────────────────────────────────────────────┘
```

### Backup-Typen

| Typ | Umfang | Speicherort | Retention |
|-----|--------|-------------|-----------|
| **full** | PostgreSQL + MinIO + Config | `/var/backups/ablage/` | 30 Tage |
| **db_only** | PostgreSQL pg_dump | `/var/backups/ablage/postgres/` | 30 Tage |
| **config_only** | Docker Compose, Nginx, etc. | `/var/backups/ablage/config/` | 90 Tage |
| **storage_only** | MinIO Buckets | `/var/backups/ablage/minio/` | 30 Tage |

### Verschlüsselung

- **Status**: Aktiviert (ab v1.8)
- **Methode**: GPG Encryption
- **Key Management**: Ansible Vault

```yaml
# ansible/group_vars/all.yml
backup_encryption_enabled: true
backup_encryption_key_id: "backup@ablage-system.local"
```

---

## Recovery-Prozeduren

### Vollständige Systemwiederherstellung

**Geschätzte Zeit**: 3-4 Stunden

```bash
# 1. Infrastruktur bereitstellen (30 min)
cd infrastructure/terraform
terraform apply

# 2. Basiskonfiguration (15 min)
cd infrastructure/ansible
ansible-playbook -i inventory/production playbooks/base.yml

# 3. Docker Services starten (15 min)
docker-compose up -d postgres redis minio

# 4. PostgreSQL Restore (60-90 min, abhängig von Datenmenge)
# Letztes Backup finden
ls -la /var/backups/ablage/postgres/
# Restore ausführen
gunzip -c postgres_YYYYMMDD_HHMMSS.sql.gz | \
  docker exec -i ablage-postgres psql -U ablage_admin -d ablage_system

# 5. MinIO Restore (60-90 min, abhängig von Datenmenge)
mc mirror backup/documents minio/documents
mc mirror backup/processed minio/processed

# 6. Konfiguration Restore (15 min)
tar -xzf config_YYYYMMDD_HHMMSS.tar.gz -C /

# 7. Services starten (15 min)
docker-compose up -d

# 8. Validierung (15 min)
curl http://localhost:8000/health
```

### Nur Datenbank-Wiederherstellung

**Geschätzte Zeit**: 60-90 Minuten

```bash
# 1. Aktive Verbindungen trennen
docker-compose stop backend worker worker-cpu

# 2. Datenbank löschen und neu erstellen
docker exec ablage-postgres psql -U ablage_admin -c "DROP DATABASE IF EXISTS ablage_system;"
docker exec ablage-postgres psql -U ablage_admin -c "CREATE DATABASE ablage_system;"

# 3. Backup einspielen
gunzip -c /var/backups/ablage/postgres/postgres_latest.sql.gz | \
  docker exec -i ablage-postgres psql -U ablage_admin -d ablage_system

# 4. Services neu starten
docker-compose up -d backend worker worker-cpu

# 5. Validierung
curl http://localhost:8000/api/v1/documents?limit=1
```

### Point-in-Time Recovery (PITR)

**Voraussetzung**: WAL Archivierung aktiviert

```bash
# 1. WAL-Archiv identifizieren
ls -la /var/backups/ablage/wal/

# 2. Recovery-Ziel definieren
cat > /tmp/recovery.conf << EOF
restore_command = 'cp /var/backups/ablage/wal/%f %p'
recovery_target_time = '2024-12-18 14:30:00 UTC'
recovery_target_action = 'promote'
EOF

# 3. PostgreSQL im Recovery-Modus starten
docker-compose stop postgres
cp /tmp/recovery.conf /var/lib/postgresql/data/
docker-compose up -d postgres

# 4. Recovery-Fortschritt überwachen
docker logs -f ablage-postgres
```

---

## Monitoring & Alerting

### Backup-Metriken (Prometheus)

| Metrik | Beschreibung | Alert Threshold |
|--------|--------------|-----------------|
| `ablage_backup_last_success_timestamp` | Letztes erfolgreiches Backup | > 26 Stunden alt |
| `ablage_backup_size_bytes` | Backup-Größe | Anomalie-Erkennung |
| `ablage_backup_duration_seconds` | Backup-Dauer | > 2x Baseline |
| `ablage_backup_errors_total` | Fehlerzähler | > 0 in 24h |

### Grafana Dashboard

- **Dashboard**: `ablage-backup-monitoring`
- **URL**: http://localhost:3002/d/ablage-backup-monitoring
- **Panels**:
  - Backup Status Timeline
  - Storage Usage Trend
  - Backup Duration History
  - Error Rate

### Alert-Regeln

```yaml
# prometheus/rules/backup-alerts.yml
groups:
  - name: backup_alerts
    rules:
      - alert: BackupMissed
        expr: time() - ablage_backup_last_success_timestamp > 93600  # 26h
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Backup nicht ausgeführt"
          description: "Letztes Backup ist älter als 26 Stunden"

      - alert: BackupFailed
        expr: increase(ablage_backup_errors_total[24h]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Backup-Fehler aufgetreten"
```

---

## Verantwortlichkeiten

### On-Call Rotation

| Rolle | Verantwortung |
|-------|---------------|
| **Primary** | Erste Reaktion, Triage, einfache Recoveries |
| **Secondary** | Eskalation, komplexe Recoveries |
| **Database Admin** | PostgreSQL-spezifische Issues |

### Kommunikation bei Incidents

1. **Erkennung**: Automatischer Alert oder manueller Report
2. **Triage**: Schweregrad bestimmen (P0/P1/P2)
3. **Kommunikation**: Stakeholder informieren
4. **Recovery**: Gemäß diesem Dokument
5. **Post-Mortem**: Incident dokumentieren, Verbesserungen identifizieren

---

## Testplan

### Monatliche Tests

- [ ] Backup-Integrität prüfen (checksum validation)
- [ ] PostgreSQL Restore auf Staging
- [ ] MinIO Restore Stichprobe

### Quartals-Tests

- [ ] Vollständiger DR-Test auf Staging
- [ ] RTO/RPO Validierung
- [ ] Dokumentation aktualisieren

### Jährliche Tests

- [ ] Full Disaster Recovery Drill
- [ ] Cross-Region Failover (falls konfiguriert)
- [ ] Runbook Review

---

## Kontakte

| Rolle | Kontakt | Erreichbarkeit |
|-------|---------|----------------|
| **DevOps Lead** | ops-team@internal.local | 24/7 |
| **Database Admin** | dba@internal.local | Business Hours |
| **Security** | security@internal.local | 24/7 für Incidents |

---

## Änderungshistorie

| Datum | Version | Änderung | Autor |
|-------|---------|----------|-------|
| 2024-12-18 | 1.0 | Initial Release | Claude Code |
