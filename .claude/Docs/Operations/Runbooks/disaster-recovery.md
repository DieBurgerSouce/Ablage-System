# Disaster Recovery Runbook - Ablage-System

**Version:** 1.0
**Letzte Aktualisierung:** 2026-02-22
**Verantwortlich:** Platform-Team
**Grafana Dashboard:** [Backup Monitoring](/d/ablage-backup-monitoring/backup-monitoring)
**Severity:** SEV-1 (Kritisch) - Systemausfall oder Datenverlust

---

## 1. Recovery Objectives

### RTO (Recovery Time Objective)

| Szenario | RTO | Beschreibung |
|----------|-----|--------------|
| Container-Neustart | < 5 Minuten | Service-Restart ohne Datenverlust |
| PostgreSQL Restore | < 30 Minuten | Wiederherstellung aus taeglichem Backup |
| MinIO Restore | < 1 Stunde | Bucket-Mirror zurueckspielen |
| Komplett-Restore | < 4 Stunden | Alle Komponenten auf neuem Server |
| Point-in-Time Recovery | < 2 Stunden | WAL-basierte Wiederherstellung |

### RPO (Recovery Point Objective)

| Komponente | RPO | Backup-Frequenz |
|------------|-----|-----------------|
| PostgreSQL | < 24 Stunden | Taeglich 02:00 Uhr |
| PostgreSQL (WAL) | ~ 0 | Kontinuierliche WAL-Archivierung |
| MinIO (Dokumente) | < 24 Stunden | Taeglich 02:00 Uhr |
| Redis (Cache) | Akzeptabler Verlust | Taeglich (Redis ist Cache) |
| Konfiguration | < 24 Stunden | Taeglich + Git-versioniert |

---

## 2. Sofortmassnahmen bei Ausfall

### 2.1 Schadenseinschaetzung

| Frage | Aktion |
|-------|--------|
| Was ist ausgefallen? | `docker-compose ps` - Status aller Container pruefen |
| Seit wann? | Grafana Dashboard pruefen, Logs sichten |
| Datenverlust? | Letzte Backup-Timestamps in `/backup/logs/` pruefen |
| Nutzer betroffen? | Frontend erreichbar? API Health-Check: `curl http://localhost:8000/health` |

### 2.2 Kommunikation

- Team ueber Ausfall informieren (Slack / E-Mail)
- Nutzer bei laengerem Ausfall benachrichtigen
- Incident dokumentieren (Startzeit, Symptome, betroffene Systeme)
- Siehe auch: [Incident Response Runbook](incident-response.md)

### 2.3 Entscheidung: Reparatur vs. Restore

| Situation | Empfehlung |
|-----------|------------|
| Container gestoppt, Daten intakt | **Reparatur** - Container neu starten |
| Datenbank korrupt, letztes Backup <24h alt | **Restore** aus Backup |
| Hardware-Defekt, alle Daten verloren | **Komplett-Restore** (Szenario 3) |
| Einzelne Dateien fehlen/korrupt | **Teilweiser Restore** (MinIO/einzelne Tabellen) |

---

## 3. Szenario 1: PostgreSQL-Ausfall

> Siehe auch: [Database Recovery Runbook](database-recovery.md) fuer detaillierte DB-spezifische Verfahren

### Symptome
- Backend liefert HTTP 500 oder Datenbankfehler
- `docker-compose ps` zeigt PostgreSQL als `unhealthy` oder `exited`
- Logs: `connection refused` oder `database system is not yet ready`

### Sofort: Container neu starten

```bash
# Status pruefen
docker-compose ps ablage-postgres

# Container neu starten
docker-compose restart ablage-postgres

# Logs pruefen (letzte 50 Zeilen)
docker-compose logs --tail=50 ablage-postgres

# Warten bis bereit (max 60 Sekunden)
timeout 60 bash -c 'until docker-compose exec ablage-postgres pg_isready; do sleep 2; done'
```

### Wenn Datenverlust: Restore aus Backup

```bash
# 1. Letztes Backup finden
ls -lt /backup/postgres/ | head -5

# 2. Restore mit dem neuesten Backup
bash scripts/backup/pg_restore.sh --latest

# 3. Verifikation
bash scripts/backup/pg_verify.sh
```

### Manuelle Wiederherstellung (bei Problemen mit pg_restore.sh)

```bash
# 1. Aktuelle DB sichern (falls moeglich)
docker-compose exec ablage-postgres pg_dump -U ablage_admin ablage_system > /tmp/emergency_backup.sql

# 2. Container stoppen
docker-compose stop ablage-postgres

# 3. Container mit frischem Volume starten (VORSICHT: loescht Daten)
# docker volume rm ablage_system_postgres_data
docker-compose up -d ablage-postgres

# 4. Backup einspielen
gunzip -c /backup/postgres/LATEST_BACKUP.sql.gz | \
  docker-compose exec -T ablage-postgres psql -U ablage_admin -d ablage_system

# 5. Migrationen ausfuehren
docker-compose exec backend alembic upgrade head
```

### Nachbereitung
- [ ] Alle Tabellen vorhanden pruefen (`\dt` in psql)
- [ ] Kritische Daten pruefen (Dokumente, Benutzer, Entitaeten)
- [ ] Backend-Container neu starten: `docker-compose restart backend`
- [ ] Celery-Worker neu starten: `docker-compose restart celery-worker celery-beat`
- [ ] E2E-Test durchfuehren (optional)

---

## 4. Szenario 2: MinIO/Storage-Ausfall

### Symptome
- Dokument-Upload schlaegt fehl
- Thumbnails werden nicht geladen
- `docker-compose ps` zeigt MinIO als `unhealthy`

### Sofort: Container pruefen

```bash
# Status pruefen
docker-compose ps ablage-minio

# Container neu starten
docker-compose restart ablage-minio

# MinIO Health-Check
curl -s http://localhost:9000/minio/health/live

# MinIO Console pruefen
# Browser: http://localhost:9001
```

### Volume-Integritaet pruefen

```bash
# Docker Volume pruefen
docker volume inspect ablage_system_minio_data

# Dateisystem-Check
du -sh /var/lib/docker/volumes/ablage_system_minio_data/_data/
```

### Restore: Nur Dateien (MinIO)

```bash
# 1. Letztes MinIO-Backup finden
ls -lt /backup/minio/ | head -5

# 2. MinIO-Client konfigurieren (falls noetig)
docker-compose exec ablage-minio mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD

# 3. Einzelnen Bucket wiederherstellen
mc mirror /backup/minio/LATEST_SNAPSHOT/documents local/documents

# 4. Alle Buckets wiederherstellen
for bucket in documents processed thumbnails; do
  mc mirror /backup/minio/LATEST_SNAPSHOT/${bucket} local/${bucket}
done
```

### Nachbereitung
- [ ] Buckets vorhanden pruefen (`mc ls local/`)
- [ ] Stichprobe: Dokumente herunterladen und pruefen
- [ ] Backend neu starten: `docker-compose restart backend`

---

## 5. Szenario 3: Komplett-Ausfall (Server)

### Voraussetzungen
- Neuer Server oder reparierter Server bereit
- Docker und Docker Compose installiert
- Zugang zu Backup-Verzeichnis (`/backup/`) oder Off-Site-Backups

### Wiederherstellungsreihenfolge

**REIHENFOLGE BEACHTEN:** PostgreSQL -> Redis -> MinIO -> Backend -> Frontend -> Monitoring

```bash
# ============================================================
# Schritt 1: Repository und Konfiguration
# ============================================================
git clone <repository-url> /app/Ablage_System
cd /app/Ablage_System

# .env Datei wiederherstellen (aus Backup oder Passwort-Manager)
cp /backup/config/.env .env

# Docker-Netzwerk und Volumes erstellen
docker-compose up -d --no-start

# ============================================================
# Schritt 2: PostgreSQL starten und wiederherstellen
# ============================================================
docker-compose up -d ablage-postgres
sleep 10  # Warten auf Initialisierung

bash scripts/backup/pg_restore.sh --latest
bash scripts/backup/pg_verify.sh

# ============================================================
# Schritt 3: Redis starten
# ============================================================
docker-compose up -d ablage-redis
sleep 5

# Redis RDB wiederherstellen (optional - Redis ist Cache)
# docker cp /backup/redis/LATEST.rdb ablage-redis:/data/dump.rdb
# docker-compose restart ablage-redis

# ============================================================
# Schritt 4: MinIO starten und wiederherstellen
# ============================================================
docker-compose up -d ablage-minio
sleep 10

for bucket in documents processed thumbnails; do
  mc mirror /backup/minio/LATEST_SNAPSHOT/${bucket} local/${bucket}
done

# ============================================================
# Schritt 5: Backend und Celery starten
# ============================================================
docker-compose up -d backend celery-worker celery-beat
sleep 10

curl http://localhost:8000/health

# ============================================================
# Schritt 6: Frontend starten
# ============================================================
docker-compose up -d frontend

# ============================================================
# Schritt 7: Monitoring starten
# ============================================================
docker-compose up -d prometheus grafana
```

### Verifikation aller Services

```bash
# Alle Container laufen?
docker-compose ps

# API erreichbar?
curl -s http://localhost:8000/health | python -m json.tool

# Frontend erreichbar?
curl -s -o /dev/null -w "%{http_code}" http://localhost:80

# PostgreSQL ok?
docker-compose exec ablage-postgres pg_isready

# Redis ok?
docker-compose exec ablage-redis redis-cli ping

# MinIO ok?
curl -s http://localhost:9000/minio/health/live

# Grafana erreichbar?
curl -s -o /dev/null -w "%{http_code}" http://localhost:3002
```

---

## 6. Szenario 4: Datenkorruption

### Erkennung

| Anzeichen | Moegliche Ursache |
|-----------|-------------------|
| Fehlerhafte OCR-Ergebnisse | Modell-Dateien korrupt |
| Fehlende Dokumente in Suche | PostgreSQL Index korrupt |
| Bilder nicht ladbar | MinIO Object korrupt |
| Inkonsistente Metadaten | Unvollstaendige Transaktion |

### Isolation

```bash
# 1. Backend in Wartungsmodus (keine neuen Anfragen)
docker-compose stop celery-worker celery-beat

# 2. Korruptions-Umfang feststellen
docker-compose exec ablage-postgres psql -U ablage_admin -d ablage_system \
  -c "SELECT count(*) FROM documents WHERE metadata IS NULL OR content IS NULL;"

# 3. Betroffene Datensaetze identifizieren
docker-compose exec ablage-postgres psql -U ablage_admin -d ablage_system \
  -c "SELECT id, filename, created_at FROM documents WHERE updated_at > 'ZEITPUNKT_DER_KORRUPTION';"
```

### Point-in-Time Recovery (WAL)

Falls WAL-Archivierung aktiviert ist:

```bash
# 1. PostgreSQL stoppen
docker-compose stop ablage-postgres

# 2. Recovery-Konfiguration setzen (in postgresql.conf):
#   restore_command = 'cp /backup/postgres/wal/%f %p'
#   recovery_target_time = '2026-02-22 14:30:00+01'
#   recovery_target_action = 'promote'

# 3. PostgreSQL mit Recovery starten
docker-compose up -d ablage-postgres

# 4. Recovery-Status pruefen
docker-compose logs ablage-postgres | grep "recovery"
```

### Teilweise Wiederherstellung: Nur Datenbank

```bash
# Einzelne Tabelle aus Backup wiederherstellen
gunzip -c /backup/postgres/LATEST_BACKUP.sql.gz | \
  grep -A 1000000 "COPY documents" | \
  grep -m 1 -B 1000000 "^\\\." | \
  docker-compose exec -T ablage-postgres psql -U ablage_admin -d ablage_system
```

---

## 7. Monitoring-Checks

### Grafana Dashboard

- **URL:** http://localhost:3002/d/ablage-backup-monitoring/backup-monitoring
- **Wichtige Panels:**
  - "Backup-Status" Zeile: Stunden seit letztem Backup pro Typ
  - "Backup-Gesundheit": Gesamtscore (sollte >80% sein)
  - "Restore-Test": Tage seit letztem Test (rot wenn >35 Tage)

### Wichtige Metriken

| Metrik | Schwellenwert | Beschreibung |
|--------|---------------|--------------|
| `backup_last_success_timestamp` | <25h alt | Letztes erfolgreiches Backup |
| `backup_restore_test_success` | = 1 | Letzter Restore-Test bestanden |
| `backup_restore_test_timestamp` | <35 Tage | Wann wurde zuletzt getestet |
| `ablage_backup_disk_free_bytes` | >20GB | Freier Backup-Speicher |
| `ablage_backup_encryption_enabled` | = 1 | GPG-Verschluesselung aktiv |

### Alert-Schwellenwerte

| Alert | Schwellenwert | Schweregrad |
|-------|---------------|-------------|
| Backup fehlgeschlagen | >0 Fehler in 24h | Kritisch |
| Backup veraltet | >26h seit letztem Erfolg | Kritisch |
| Keine Aktivitaet | 0 Versuche in 24h | Kritisch |
| Speicherplatz niedrig | <20GB frei | Warnung |
| Speicherplatz kritisch | <10GB frei | Kritisch |
| Validierung fehlgeschlagen | >0 Fehler in 24h | Warnung |
| Restore-Test fehlgeschlagen | >0 Fehler in 7d | Warnung |
| Verschluesselung deaktiviert | = 0 | Info |

Alert-Konfiguration: `infrastructure/grafana/provisioning/alerting/backup-alerts.yml`

---

## 8. Kontakte & Eskalation

| Rolle | Kontakt | Eskalation |
|-------|---------|------------|
| Platform-Team | [E-Mail / Slack eintragen] | Primaer |
| Datenbank-Admin | [E-Mail eintragen] | Bei PostgreSQL-Problemen |
| Systemadmin | [E-Mail eintragen] | Bei Hardware/Netzwerk |
| Management | [E-Mail eintragen] | Bei Datenverlust >24h |

### Eskalationsmatrix

| Dauer | Aktion |
|-------|--------|
| 0-15 Min | On-Call prueft, Sofortmassnahmen |
| 15-60 Min | Team-Lead informieren |
| 1-4 Std | Management informieren |
| >4 Std | Notfall-Meeting, externe Hilfe pruefen |

---

## 9. Monatlicher Restore-Drill

### Checkliste

Diese Checkliste ist monatlich am 1. des Monats durchzufuehren:

- [ ] **Vorbereitung**
  - [ ] Team ueber geplanten Drill informieren
  - [ ] Sicherstellen, dass aktuelle Backups vorhanden sind (`ls -lt /backup/postgres/ | head -3`)
  - [ ] Genuegend Speicherplatz fuer temporaere Test-DB (`df -h /backup/`)

- [ ] **Automatisierter Restore-Test**
  - [ ] Script ausfuehren: `bash scripts/backup/restore_test.sh`
  - [ ] Ergebnis pruefen: `cat /backup/logs/restore_test_report_*.txt | tail -20`
  - [ ] Alle Tests BESTANDEN?

- [ ] **Manuelle Verifikation**
  - [ ] PostgreSQL: Kritische Tabellen vorhanden (documents, users, entities)
  - [ ] PostgreSQL: Zeilenanzahl plausibel
  - [ ] MinIO: Stichprobe - 3 Dokumente herunterladen und oeffnen
  - [ ] Redis: RDB-Datei vorhanden und valide

- [ ] **Metriken aktualisieren**
  - [ ] `bash scripts/backup/backup_metrics.sh`
  - [ ] Grafana Dashboard pruefen: Restore-Test Panel gruen?

- [ ] **Dokumentation**
  - [ ] Drill-Ergebnis in Incident-Log dokumentieren
  - [ ] Bei Fehlern: Ticket erstellen und priorisieren
  - [ ] Bei Erfolg: Naechsten Drill-Termin bestaetigen

### Erwartete Ergebnisse

| Test | Erwartung |
|------|-----------|
| PostgreSQL | Backup in temporaere DB restauriert, kritische Tabellen vorhanden |
| MinIO | Snapshot vorhanden, Buckets mit Objekten, Dateien lesbar |
| Redis | RDB-Datei vorhanden, gzip-Integritaet OK, Magic-Bytes valide |
| Volumes | tar.gz-Archive integer, Dateien extrahierbar |

### Was bei Fehlschlag zu tun ist

1. **Bericht analysieren:** `cat /backup/logs/restore_test_report_TIMESTAMP.txt`
2. **Fehler identifizieren:** Welcher Test ist fehlgeschlagen?
3. **Backup-Integritaet pruefen:** Ist das Quell-Backup korrupt?
4. **Backup-Script pruefen:** Laeuft `backup_all.sh` fehlerfrei?
5. **Manuell testen:** Einzelnen Backup-Typ manuell wiederherstellen
6. **Eskalieren:** Wenn Backup-System nicht wiederherstellbar -> sofort Team-Lead informieren

---

## 10. Cron-Konfiguration

```cron
# Taeglich um 02:00 Uhr: Komplett-Backup
0 2 * * * /app/scripts/backup/backup_all.sh >> /backup/logs/cron_backup.log 2>&1

# Nach jedem Backup: Metriken aktualisieren
30 2 * * * /app/scripts/backup/backup_metrics.sh >> /backup/logs/cron_metrics.log 2>&1

# Monatlich am 1. um 04:00 Uhr: Restore-Test
0 4 1 * * /app/scripts/backup/restore_test.sh >> /backup/logs/cron_restore_test.log 2>&1
```

---

## Anhang: Backup-Verzeichnisstruktur

```
/backup/
├── postgres/           # PostgreSQL-Backups (pg_dump)
│   ├── daily/          # 7 taeglich
│   ├── weekly/         # 4 woechentlich
│   └── monthly/        # 3 monatlich
├── minio/              # MinIO-Bucket-Snapshots
├── redis/              # Redis RDB + AOF
├── volumes/            # Docker-Volume-Backups
├── logs/               # Backup-Logs und -Berichte
│   ├── backup_all.log
│   ├── pg_backup.log
│   ├── restore_test.log
│   └── backup_summary_*.txt
└── metrics/            # Prometheus-Textfile-Metriken
    └── backup_metrics.prom
```

## Verwandte Runbooks

- [Database Recovery](database-recovery.md) - Detaillierte PostgreSQL-Wiederherstellung
- [Backup Integrity Verification](backup-integrity-verification.md) - Backup-Validierung bei Fehlschlag
- [MinIO Failure Recovery](minio-failure-recovery.md) - MinIO-spezifische Probleme
- [Redis Cluster Recovery](redis-cluster-recovery.md) - Redis-spezifische Probleme
- [Incident Response](incident-response.md) - Allgemeines Incident-Handling
