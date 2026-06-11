# PostgreSQL Database Recovery Runbook

**Version:** 1.0
**Letzte Aktualisierung:** 2025-12-18
**Verantwortlich:** Database Team

---

## 1. Übersicht

Dieses Runbook beschreibt die Wiederherstellungsprozeduren für die PostgreSQL-Datenbank des Ablage-Systems.

### Recovery Time Objectives (RTO)
- **Vollständige Wiederherstellung:** < 4 Stunden
- **Point-in-Time Recovery (PITR):** < 2 Stunden
- **Failover (mit Patroni HA):** < 30 Sekunden

### Recovery Point Objectives (RPO)
- **Backups:** Täglich (max. 24h Datenverlust)
- **WAL-Archivierung:** Kontinuierlich (nahezu 0 Datenverlust)

---

## 2. Backup-Verifizierung

### 2.1 Backup-Status prüfen

```bash
# Letzte Backups auflisten
curl http://localhost:8000/api/v1/backup/list | jq .

# Backup-Metriken prüfen
curl http://localhost:8000/api/v1/metrics/backup | jq .

# Backup-Dateien direkt prüfen
ls -la /var/lib/ablage/backups/postgres/

# Neuestes Backup
ls -lt /var/lib/ablage/backups/postgres/ | head -5
```

### 2.2 Backup-Integrität testen

```bash
# Backup entpacken und prüfen (ohne Wiederherstellung)
cd /var/lib/ablage/backups/postgres/
gunzip -t ablage_postgres_$(date +%Y%m%d)*.sql.gz

# pg_restore --list (Struktur prüfen)
gunzip -c ablage_postgres_latest.sql.gz | head -100
```

---

## 3. Wiederherstellungsszenarien

### Szenario A: Kompletter Datenverlust

**Wann:** Postgres-Container zerstört, Volumes gelöscht

```bash
# 1. System stoppen
docker-compose stop backend worker

# 2. Postgres-Container neu erstellen
docker-compose up -d postgres

# 3. Warten bis Postgres bereit ist
until docker exec ablage-postgres pg_isready -U postgres; do
  echo "Warte auf PostgreSQL..."
  sleep 2
done

# 4. Datenbank erstellen
docker exec ablage-postgres psql -U postgres -c "CREATE DATABASE ablage;"

# 5. Backup wiederherstellen
gunzip -c /var/lib/ablage/backups/postgres/ablage_postgres_latest.sql.gz | \
  docker exec -i ablage-postgres psql -U postgres -d ablage_system

# 6. Berechtigungen setzen
docker exec ablage-postgres psql -U postgres -d ablage_system -c "
  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ablage_admin;
  GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ablage_admin;
"

# 7. Migrationen prüfen
docker-compose run --rm backend alembic current
docker-compose run --rm backend alembic upgrade head

# 8. System starten
docker-compose up -d backend worker

# 9. Verifizierung
curl http://localhost:8000/api/v1/health
```

### Szenario B: Point-in-Time Recovery (PITR)

**Wann:** Daten wurden versehentlich gelöscht, spezifischer Zeitpunkt benötigt

```bash
# 1. Zielzeitpunkt festlegen (UTC)
TARGET_TIME="2025-12-18 14:30:00 UTC"

# 2. System stoppen
docker-compose stop backend worker postgres

# 3. Postgres-Datenverzeichnis sichern
mv /var/lib/docker/volumes/ablage_postgres_data/_data \
   /var/lib/docker/volumes/ablage_postgres_data/_data.backup.$(date +%Y%m%d_%H%M%S)

# 4. Basis-Backup wiederherstellen
# (Erfordert pg_basebackup + WAL-Archive)
pg_basebackup -D /var/lib/docker/volumes/ablage_postgres_data/_data \
  -h localhost -p 5432 -U postgres

# 5. recovery.conf erstellen
cat > /var/lib/docker/volumes/ablage_postgres_data/_data/recovery.conf << EOF
restore_command = 'cp /var/lib/ablage/backups/wal/%f %p'
recovery_target_time = '${TARGET_TIME}'
recovery_target_action = 'promote'
EOF

# 6. Postgres starten
docker-compose up -d postgres

# 7. Recovery-Log überwachen
docker-compose logs -f postgres | grep -i recovery
```

### Szenario C: Einzelne Tabelle wiederherstellen

**Wann:** Eine bestimmte Tabelle muss wiederhergestellt werden

```bash
# 1. Tabelle aus Backup extrahieren
gunzip -c /var/lib/ablage/backups/postgres/ablage_postgres_latest.sql.gz | \
  grep -A 1000 "CREATE TABLE documents" | \
  grep -B 1000 "ALTER TABLE documents" > documents_restore.sql

# 2. Alte Tabelle umbenennen (Backup)
docker exec ablage-postgres psql -U postgres -d ablage_system -c "
  ALTER TABLE documents RENAME TO documents_old_$(date +%Y%m%d);
"

# 3. Tabelle wiederherstellen
cat documents_restore.sql | docker exec -i ablage-postgres psql -U postgres -d ablage_system

# 4. Daten verifizieren
docker exec ablage-postgres psql -U postgres -d ablage_system -c "
  SELECT COUNT(*) FROM documents;
"

# 5. Alte Tabelle löschen (nach Verifizierung)
docker exec ablage-postgres psql -U postgres -d ablage_system -c "
  DROP TABLE IF EXISTS documents_old_$(date +%Y%m%d);
"
```

### Szenario D: Korrupte Datenbank reparieren

**Wann:** Postgres startet nicht, "corrupted page" Fehler

```bash
# 1. Im Single-User-Mode starten
docker-compose stop postgres
docker run --rm -it \
  -v ablage_postgres_data:/var/lib/postgresql/data \
  postgres:16-alpine \
  postgres --single -D /var/lib/postgresql/data ablage_system

# 2. VACUUM FULL ausführen
VACUUM FULL;
REINDEX DATABASE ablage_system;
\q

# 3. Oder: pg_resetwal (LETZTE OPTION - Datenverlust möglich!)
docker run --rm -it \
  -v ablage_postgres_data:/var/lib/postgresql/data \
  postgres:16-alpine \
  pg_resetwal -f /var/lib/postgresql/data

# 4. Normal starten
docker-compose up -d postgres
```

---

## 4. Verifizierung nach Wiederherstellung

### 4.1 Datenintegrität prüfen

```bash
# Tabellenanzahl
docker exec ablage-postgres psql -U postgres -d ablage_system -c "
  SELECT schemaname, COUNT(*) as table_count
  FROM pg_tables
  WHERE schemaname = 'public'
  GROUP BY schemaname;
"

# Dokumentenanzahl
docker exec ablage-postgres psql -U postgres -d ablage_system -c "
  SELECT COUNT(*) as documents FROM documents;
  SELECT COUNT(*) as users FROM users;
  SELECT COUNT(*) as ocr_results FROM ocr_results;
"

# Fremdschlüssel-Integrität
docker exec ablage-postgres psql -U postgres -d ablage_system -c "
  SELECT conname, conrelid::regclass
  FROM pg_constraint
  WHERE confrelid IS NOT NULL
  ORDER BY conname;
"
```

### 4.2 Anwendungstest

```bash
# Health Check
curl http://localhost:8000/api/v1/health | jq .

# Dokumenten-API testen
curl http://localhost:8000/api/v1/documents | jq '.total'

# Benutzer-Login testen
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "test"}' | jq .
```

---

## 5. Präventive Maßnahmen

### 5.1 Regelmäßige Backup-Tests

```bash
# Monatlicher Restore-Test (automatisiert)
# Cronjob: 0 3 1 * * /opt/ablage/scripts/test-restore.sh

#!/bin/bash
# /opt/ablage/scripts/test-restore.sh

# 1. Test-Container starten
docker run -d --name postgres-restore-test \
  -e POSTGRES_PASSWORD=testpass \
  postgres:16-alpine

# 2. Backup wiederherstellen
gunzip -c /var/lib/ablage/backups/postgres/ablage_postgres_latest.sql.gz | \
  docker exec -i postgres-restore-test psql -U postgres

# 3. Integrität prüfen
docker exec postgres-restore-test psql -U postgres -d ablage_system -c "\dt"

# 4. Aufräumen
docker rm -f postgres-restore-test

# 5. Ergebnis melden
echo "Restore-Test erfolgreich: $(date)" >> /var/log/ablage/restore-tests.log
```

### 5.2 WAL-Archivierung aktivieren

```sql
-- postgresql.conf
archive_mode = on
archive_command = 'cp %p /var/lib/ablage/backups/wal/%f'
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB
```

---

## 6. Patroni HA-Failover (falls implementiert)

### 6.1 Automatischer Failover

```bash
# Patroni-Status prüfen
patronictl -c /etc/patroni/config.yml list

# Manueller Failover
patronictl -c /etc/patroni/config.yml switchover --master postgres-primary --candidate postgres-replica

# Cluster-Status nach Failover
patronictl -c /etc/patroni/config.yml list
```

### 6.2 Replica hinzufügen

```bash
# Neue Replica provisionieren
pg_basebackup -h postgres-primary -D /var/lib/postgresql/data -U replicator -P -R

# Patroni auf neuer Node starten
systemctl start patroni
```

---

## 7. Wichtige Dateipfade

| Pfad | Beschreibung |
|------|--------------|
| `/var/lib/ablage/backups/postgres/` | PostgreSQL Backups |
| `/var/lib/ablage/backups/wal/` | WAL-Archive |
| `/var/lib/docker/volumes/ablage_postgres_data/` | Live-Daten |
| `/etc/patroni/config.yml` | Patroni-Konfiguration (falls HA) |

---

## 8. Kontakte bei DB-Notfällen

| Rolle | Kontakt |
|-------|---------|
| DBA Primary | [TBD] |
| DBA Secondary | [TBD] |
| External DB Support | [TBD] |
