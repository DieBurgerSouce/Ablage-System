# Disaster Recovery Runbook - Ablage-System

> **Zuletzt aktualisiert**: 2026-05-04 (Sprint 0 / G08)
> **Verantwortlich**: Ben (Solo-Founder)
> **Grafana Dashboard**: [Backup Monitoring](/d/ablage-backup-monitoring/backup-monitoring)

---

## Backend-Watchdog (Sprint 0 / G05)

**Script:** `scripts/watchdog/backend_watchdog.sh`

**Funktion:** Periodischer Health-Check des Backend-Containers. Bei 3 Failures in Folge: automatischer `docker-compose restart backend` + Slack-Notification. Bei 5 Failures: Eskalation (manueller Eingriff).

**Verifiziert (2026-05-04):**

| Test | Ergebnis |
|------|----------|
| Status-Mode | Container/Health/Slack-Status korrekt |
| Single Iteration (healthy) | Exit 0, kein State-File |
| 1. Failure | count=1, kein Restart, Exit 1 |
| 2. Failure | count=2, kein Restart, Exit 1 |
| **3. Failure (Threshold)** | **count=3, Auto-Restart, docker-compose erfolgreich** |
| Recovery | count auf 0 zurueckgesetzt, Slack-Recovery-Notify |

**Befehlszeile:**

```bash
# Status
bash scripts/watchdog/backend_watchdog.sh status

# Single check (fuer Cron)
bash scripts/watchdog/backend_watchdog.sh once

# Endlosschleife (60s interval)
bash scripts/watchdog/backend_watchdog.sh loop

# Manueller Reset des Failure-Counters
bash scripts/watchdog/backend_watchdog.sh reset

# Slack-Test (nach G01-URL-Setup)
bash scripts/watchdog/backend_watchdog.sh --test-slack
```

**Production-Setup (1 von 3 Optionen):**

1. **Cron (Linux)** — alle 60s:
   ```bash
   echo "* * * * * /path/to/scripts/watchdog/backend_watchdog.sh once" | crontab -
   ```

2. **Background-Process (Linux/WSL)**:
   ```bash
   nohup bash scripts/watchdog/backend_watchdog.sh loop > /var/log/ablage-watchdog.log 2>&1 &
   ```

3. **Windows Task-Scheduler** (siehe `--help`-Output):
   - Action: `bash.exe`
   - Args: `<Pfad-zum-Script>` `once`
   - Trigger: every 1 minute

**ENV-Variablen** (Defaults sinnvoll):

- `RESTART_THRESHOLD=3` — Anzahl Failures bis Restart
- `ESCALATE_THRESHOLD=5` — Anzahl Failures bis Eskalation
- `LOOP_INTERVAL=60` — Sekunden im Loop-Mode
- `HEALTH_TIMEOUT=15` — Sekunden curl-Timeout

**Voraussetzung:** Slack-Webhook in `infrastructure/alerting/slack-webhook.url` (Sprint 0 / G01).

---

## Manuelle Restore-Tests (Sprint 0 / G08)

| Datum | Backup-Dauer | Restore-Dauer | DB-Groesse | Tables vor/nach | Ergebnis |
|-------|-------------:|--------------:|-----------:|:---------------:|----------|
| 2026-05-04 | 4.6s | 58.1s | 89 MB | 427 / 427 | OK |

**Methode:** `pg_dump` -> Temp-DB `ablage_restore_test` -> `pg_restore` -> Verify-Tables -> DROP

**Befehlszeile-Reproduktion:**

```bash
# Backup
docker exec ablage-postgres pg_dump -U ablage_admin -d ablage_system > /tmp/dump-$(date +%Y%m%d).sql

# Temp-DB anlegen
docker exec ablage-postgres psql -U ablage_admin -d postgres -c "CREATE DATABASE ablage_restore_test;"

# Restore
cat /tmp/dump-YYYYMMDD.sql | docker exec -i ablage-postgres psql -U ablage_admin -d ablage_restore_test

# Verify (sollte gleich wie Original sein)
docker exec ablage-postgres psql -U ablage_admin -d ablage_restore_test -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';"

# Cleanup
docker exec ablage-postgres psql -U ablage_admin -d postgres -c "DROP DATABASE ablage_restore_test;"
```

**Konkrete Aussagen** (basierend auf 2026-05-04-Test):
- **RPO (Recovery Point Objective):** abhaengig von Backup-Frequenz (aktuell ueber `scripts/backup/backup_all.sh` Cron)
- **RTO (Recovery Time Objective):** **<2 Min** fuer Full-DB-Restore (Backup + Restore + Verify)
- **Datenintegritaet:** 100% (Tables-Count vor/nach identisch)

**Naechster manueller Test:** spaetestens 2026-06-04 (monatlich).
**Trigger fuer Re-Test:** Nach jeder DB-Migration die >10 Tables aendert.

---

## Sofortmassnahmen bei Ausfall

### 1. Schadenseinschaetzung

| Frage | Aktion |
|-------|--------|
| Was ist ausgefallen? | `docker-compose ps` - Status aller Container pruefen |
| Seit wann? | Grafana Dashboard pruefen, Logs sichten |
| Datenverlust? | Letzte Backup-Timestamps in `/backup/logs/` pruefen |
| Nutzer betroffen? | Frontend erreichbar? API Health-Check: `curl http://localhost:8000/health` |

### 2. Kommunikation

- Team ueber Ausfall informieren (Slack / E-Mail)
- Nutzer bei laengerem Ausfall benachrichtigen
- Incident dokumentieren (Startzeit, Symptome, betroffene Systeme)

### 3. Entscheidung: Reparatur vs. Restore

| Situation | Empfehlung |
|-----------|------------|
| Container gestoppt, Daten intakt | **Reparatur** - Container neu starten |
| Datenbank korrupt, letztes Backup <24h alt | **Restore** aus Backup |
| Hardware-Defekt, alle Daten verloren | **Komplett-Restore** (Szenario 3) |
| Einzelne Dateien fehlen/korrupt | **Teilweiser Restore** (MinIO/einzelne Tabellen) |

---

## Szenario 1: PostgreSQL-Ausfall

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

# 3. Volume bereinigen (VORSICHT: loescht alle Daten!)
# docker volume rm ablage_system_postgres_data

# 4. Container mit frischem Volume starten
docker-compose up -d ablage-postgres

# 5. Backup einspielen
gunzip -c /backup/postgres/LATEST_BACKUP.sql.gz | \
  docker-compose exec -T ablage-postgres psql -U ablage_admin -d ablage_system

# 6. Migrationen ausfuehren
docker-compose exec backend alembic upgrade head
```

### Nachbereitung
- [ ] Verify: Alle Tabellen vorhanden (`\dt` in psql)
- [ ] Verify: Kritische Daten pruefen (Dokumente, Benutzer, Entitaeten)
- [ ] Backend-Container neu starten: `docker-compose restart backend`
- [ ] Celery-Worker neu starten: `docker-compose restart celery-worker celery-beat`
- [ ] E2E-Test durchfuehren (optional)

---

## Szenario 2: MinIO/Storage-Ausfall

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

# Dateisystem-Check (wenn Volume auf Host gemountet)
du -sh /var/lib/docker/volumes/ablage_system_minio_data/_data/
```

### Restore aus Backup

```bash
# 1. Letztes MinIO-Backup finden
ls -lt /backup/minio/ | head -5

# 2. MinIO-Client konfigurieren (falls noetig)
docker-compose exec ablage-minio mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD

# 3. Buckets wiederherstellen (Mirror-Reverse)
# Fuer einzelnen Bucket:
mc mirror /backup/minio/LATEST_SNAPSHOT/documents local/documents

# Fuer alle Buckets:
for bucket in documents processed thumbnails; do
  mc mirror /backup/minio/LATEST_SNAPSHOT/${bucket} local/${bucket}
done
```

### Nachbereitung
- [ ] Verify: Buckets vorhanden (`mc ls local/`)
- [ ] Verify: Stichprobe Dokumente herunterladen
- [ ] Backend neu starten: `docker-compose restart backend`

---

## Szenario 3: Komplett-Ausfall (Server)

### Voraussetzungen
- Neuer Server oder reparierter Server bereit
- Docker und Docker Compose installiert
- Zugang zu Backup-Verzeichnis (`/backup/`) oder Off-Site-Backups

### Schritt-fuer-Schritt Wiederherstellung

```bash
# ============================================================
# REIHENFOLGE BEACHTEN: PostgreSQL -> Redis -> MinIO -> Backend -> Frontend
# ============================================================

# 1. Repository klonen und Konfiguration wiederherstellen
git clone <repository-url> /app/Ablage_System
cd /app/Ablage_System

# 2. .env Datei wiederherstellen
# Aus Backup oder Passwort-Manager
cp /backup/config/.env .env
# ODER manuell erstellen (siehe .env.example)

# 3. Docker-Netzwerk und Volumes erstellen
docker-compose down -v  # Falls alte Volumes existieren
docker-compose up -d --no-start  # Nur erstellen, nicht starten

# 4. PostgreSQL starten und wiederherstellen
docker-compose up -d ablage-postgres
sleep 10  # Warten auf Initialisierung

# Backup einspielen
bash scripts/backup/pg_restore.sh --latest
bash scripts/backup/pg_verify.sh

# 5. Redis starten und wiederherstellen
docker-compose up -d ablage-redis
sleep 5

# Redis RDB wiederherstellen (optional - Redis ist Cache)
# Falls kritische Daten in Redis:
# docker cp /backup/redis/LATEST.rdb ablage-redis:/data/dump.rdb
# docker-compose restart ablage-redis

# 6. MinIO starten und wiederherstellen
docker-compose up -d ablage-minio
sleep 10

# Buckets wiederherstellen
for bucket in documents processed thumbnails; do
  mc mirror /backup/minio/LATEST_SNAPSHOT/${bucket} local/${bucket}
done

# 7. Backend und Celery starten
docker-compose up -d backend celery-worker celery-beat
sleep 10

# Health-Check
curl http://localhost:8000/health

# 8. Frontend starten
docker-compose up -d frontend

# 9. Monitoring starten
docker-compose up -d prometheus grafana

# 10. Alle Services verifizieren
docker-compose ps
curl -s http://localhost:8000/health | python -m json.tool
```

### Verifikation aller Services

```bash
# Alle Container laufen?
docker-compose ps

# API erreichbar?
curl -s http://localhost:8000/health

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

## Szenario 4: Datenkorruption

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

# 2. Korruption-Umfang feststellen
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

# 2. Recovery-Konfiguration setzen
# In postgresql.conf oder recovery.conf:
#   restore_command = 'cp /backup/postgres/wal/%f %p'
#   recovery_target_time = '2026-02-22 14:30:00+01'
#   recovery_target_action = 'promote'

# 3. PostgreSQL mit Recovery starten
docker-compose up -d ablage-postgres

# 4. Recovery-Status pruefen
docker-compose logs ablage-postgres | grep "recovery"
```

### Teilweise Wiederherstellung

```bash
# Einzelne Tabelle aus Backup wiederherstellen
gunzip -c /backup/postgres/LATEST_BACKUP.sql.gz | \
  grep -A 1000000 "COPY documents" | \
  grep -m 1 -B 1000000 "^\\\." | \
  docker-compose exec -T ablage-postgres psql -U ablage_admin -d ablage_system
```

---

## Monitoring-Checks

### Grafana Dashboard

- **URL**: http://localhost:3002/d/ablage-backup-monitoring/backup-monitoring
- **Wichtige Panels**:
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

---

## Kontakte & Eskalation

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

## Monatlicher Restore-Test

### Ausfuehrung

```bash
# Automatisiert (empfohlen - per Cron am 1. des Monats)
bash scripts/backup/restore_test.sh

# Ergebnis pruefen
cat /backup/logs/restore_test_report_*.txt | tail -1
```

### Erwartete Ergebnisse

- **PostgreSQL**: Backup in temporaere DB restauriert, kritische Tabellen vorhanden (documents, users, entities)
- **MinIO**: Snapshot vorhanden, Buckets mit Objekten, Dateien lesbar
- **Redis**: RDB-Datei vorhanden, gzip-Integritaet OK, Magic-Bytes valide
- **Volumes**: tar.gz-Archive integer, Dateien extrahierbar

### Was bei Fehlschlag zu tun ist

1. **Bericht analysieren**: `cat /backup/logs/restore_test_report_TIMESTAMP.txt`
2. **Fehler identifizieren**: Welcher Test ist fehlgeschlagen?
3. **Backup-Integritaet pruefen**: Ist das Quell-Backup korrupt?
4. **Backup-Script pruefen**: Laeuft `backup_all.sh` fehlerfrei?
5. **Manuell testen**: Einzelnen Backup-Typ manuell wiederherstellen
6. **Eskalieren**: Wenn Backup-System nicht wiederherstellbar, sofort Team-Lead informieren

### Cron-Konfiguration

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
