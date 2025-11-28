# Ablage-System Backup & Wiederherstellung

Dieses Dokument beschreibt die Backup- und Wiederherstellungsverfahren für das Ablage-System.

## Übersicht

Das Backup-System sichert automatisch:

- **PostgreSQL-Datenbank**: Alle Dokumentmetadaten und Benutzerinformationen
- **Redis-Daten**: Cache und Warteschlangen-Status
- **MinIO-Speicher**: Alle hochgeladenen Dokumente und OCR-Ergebnisse
- **Konfiguration**: .env-Datei und Docker Compose-Konfiguration

## Backup-Zeitplan

Standardmäßig werden Backups täglich um 02:00 Uhr erstellt:

```
02:00 - Vollständiges Backup
04:00 - Alte Backups aufräumen (> 30 Tage)
```

Der Zeitplan kann in `inventories/<env>/group_vars/all.yml` angepasst werden:

```yaml
backup_schedule: "*-*-* 02:00:00"  # systemd calendar format
backup_retention_days: 30
```

## Manuelles Backup

### Mit Ansible

```bash
# Vollständiges Backup
ansible-playbook -i inventories/production playbooks/backup.yml

# Nur Datenbank
ansible-playbook -i inventories/production playbooks/backup.yml -e "backup_type=db_only"

# Nur Konfiguration
ansible-playbook -i inventories/production playbooks/backup.yml -e "backup_type=config_only"

# Nur Dokumente (MinIO)
ansible-playbook -i inventories/production playbooks/backup.yml -e "backup_type=storage_only"
```

### Direkt auf dem Server

```bash
# Als root oder sudo
/usr/local/bin/ablage-backup --full

# Optionen
/usr/local/bin/ablage-backup --help
```

## Backup-Speicherorte

### Lokales Backup

Standardpfad: `/var/backups/ablage/`

```
/var/backups/ablage/
├── full_backup_20241127_020000.tar.gz    # Vollbackup
├── postgres_20241127_020000.sql.gz       # Datenbank
├── redis_20241127_020000.rdb             # Redis
├── minio_20241127_020000/                # MinIO-Daten
└── config_20241127_020000.tar.gz         # Konfiguration
```

### Remote-Backup (Optional)

Konfiguration in `vault.yml`:

```yaml
backup_remote_enabled: true
vault_backup_remote_user: backup
vault_backup_remote_host: backup-server.example.com
vault_backup_remote_path: /backups/ablage-system
vault_backup_ssh_key: |
  -----BEGIN OPENSSH PRIVATE KEY-----
  ...
  -----END OPENSSH PRIVATE KEY-----
```

## Wiederherstellung

### Mit Ansible (Empfohlen)

```bash
# Vollständige Wiederherstellung
ansible-playbook -i inventories/production playbooks/restore.yml \
  -e "backup_date=20241127" \
  -e "confirm_restore=true"

# Nur Datenbank wiederherstellen
ansible-playbook -i inventories/production playbooks/restore.yml \
  -e "backup_date=20241127" \
  -e "restore_type=db_only" \
  -e "confirm_restore=true"

# Von spezifischer Datei
ansible-playbook -i inventories/production playbooks/restore.yml \
  -e "backup_file=/var/backups/ablage/full_backup_20241127_020000.tar.gz" \
  -e "confirm_restore=true"
```

**WICHTIG**: Die Wiederherstellung erfordert `confirm_restore=true`, da sie bestehende Daten überschreibt!

### Direkt auf dem Server

```bash
# Als root oder sudo
/usr/local/bin/ablage-restore --backup /var/backups/ablage/full_backup_20241127_020000.tar.gz
```

## Wiederherstellungstypen

### Vollständige Wiederherstellung (`full`)

Stellt alle Komponenten wieder her:

1. Stoppt alle Services
2. Stellt PostgreSQL-Datenbank wieder her
3. Stellt Redis-Daten wieder her
4. Stellt MinIO-Dokumente wieder her
5. Stellt Konfiguration wieder her
6. Startet alle Services
7. Führt Gesundheitsprüfung durch

### Datenbank-Wiederherstellung (`db_only`)

Stellt nur die PostgreSQL-Datenbank wieder her:

```bash
ansible-playbook -i inventories/production playbooks/restore.yml \
  -e "backup_date=20241127" \
  -e "restore_type=db_only" \
  -e "confirm_restore=true"
```

### Konfiguration-Wiederherstellung (`config_only`)

Stellt nur .env und Docker Compose-Konfiguration wieder her:

```bash
ansible-playbook -i inventories/production playbooks/restore.yml \
  -e "backup_date=20241127" \
  -e "restore_type=config_only" \
  -e "confirm_restore=true"
```

### Dokumenten-Wiederherstellung (`storage_only`)

Stellt nur MinIO-Dokumente wieder her:

```bash
ansible-playbook -i inventories/production playbooks/restore.yml \
  -e "backup_date=20241127" \
  -e "restore_type=storage_only" \
  -e "confirm_restore=true"
```

## Backup-Rotation

Alte Backups werden automatisch nach der konfigurierten Aufbewahrungsfrist gelöscht.

Standard: 30 Tage

Anpassen in `inventories/<env>/group_vars/all.yml`:

```yaml
backup_retention_days: 30
```

## Remote-Sync

### Konfiguration

1. SSH-Schlüssel auf dem Zielserver hinterlegen
2. In `vault.yml` konfigurieren:

```yaml
backup_remote_enabled: true
vault_backup_remote_user: backup
vault_backup_remote_host: backup.example.com
vault_backup_remote_path: /backups/ablage
```

### Manueller Sync

```bash
# Mit Ansible
ansible-playbook -i inventories/production playbooks/backup.yml -e "force_remote_sync=true"

# Direkt auf dem Server
/usr/local/bin/ablage-backup --sync-remote
```

## Notfall-Wiederherstellung

### Bei komplettem Server-Ausfall

1. **Neuen Server bereitstellen**
   ```bash
   ansible-playbook -i inventories/production playbooks/site.yml
   ```

2. **Backup vom Remote-Server holen**
   ```bash
   scp backup@backup-server:/backups/ablage/full_backup_*.tar.gz /var/backups/ablage/
   ```

3. **Wiederherstellung durchführen**
   ```bash
   ansible-playbook -i inventories/production playbooks/restore.yml \
     -e "backup_date=20241127" \
     -e "confirm_restore=true"
   ```

### Bei Datenbank-Korruption

1. **Nur Datenbank wiederherstellen**
   ```bash
   ansible-playbook -i inventories/production playbooks/restore.yml \
     -e "backup_date=20241127" \
     -e "restore_type=db_only" \
     -e "confirm_restore=true"
   ```

2. **Migrationen prüfen**
   ```bash
   docker compose exec backend alembic current
   docker compose exec backend alembic upgrade head
   ```

## Backup-Überprüfung

### Backup-Integrität testen

```bash
# Backup-Datei testen
tar -tzf /var/backups/ablage/full_backup_20241127_020000.tar.gz

# SQL-Dump testen
gunzip -t /var/backups/ablage/postgres_20241127_020000.sql.gz
```

### In Testumgebung wiederherstellen

Empfohlene Best Practice: Regelmäßig in einer Staging-Umgebung testen!

```bash
ansible-playbook -i inventories/staging playbooks/restore.yml \
  -e "backup_file=/pfad/zu/production/backup.tar.gz" \
  -e "confirm_restore=true"
```

## Überwachung

### Backup-Status prüfen

```bash
# Letzte Backups anzeigen
ls -lht /var/backups/ablage/ | head -10

# Backup-Logs
journalctl -u ablage-backup -f

# Systemd-Timer-Status
systemctl status ablage-backup.timer
```

### Alerts

Bei Backup-Fehlern werden Benachrichtigungen gesendet (wenn konfiguriert):

```yaml
# In all.yml
health_check_alert_enabled: true
health_check_alert_email: admin@example.com
```

## Fehlerbehebung

### Backup fehlgeschlagen

1. **Logs prüfen**
   ```bash
   journalctl -u ablage-backup --since "1 hour ago"
   ```

2. **Speicherplatz prüfen**
   ```bash
   df -h /var/backups/ablage
   ```

3. **Datenbank-Verbindung prüfen**
   ```bash
   docker compose exec postgres pg_isready
   ```

### Wiederherstellung fehlgeschlagen

1. **Backup-Datei überprüfen**
   ```bash
   tar -tzf /var/backups/ablage/full_backup_*.tar.gz | head
   ```

2. **Manuelle Datenbank-Wiederherstellung**
   ```bash
   # Container stoppen
   docker compose stop backend worker

   # Datenbank löschen und neu erstellen
   docker compose exec postgres psql -U ablage_admin -c "DROP DATABASE IF EXISTS ablage_system;"
   docker compose exec postgres psql -U ablage_admin -c "CREATE DATABASE ablage_system;"

   # Backup einspielen
   gunzip -c /var/backups/ablage/postgres_*.sql.gz | docker compose exec -T postgres psql -U ablage_admin -d ablage_system

   # Container starten
   docker compose up -d
   ```

## Datenschutz

- Backups enthalten sensible Daten (Dokumente, Benutzerdaten)
- Verschlüsselung bei Remote-Übertragung (SSH/rsync)
- Zugriffsrechte auf Backup-Verzeichnis einschränken (root only)
- Regelmäßige Überprüfung der Backup-Aufbewahrung gemäß DSGVO
