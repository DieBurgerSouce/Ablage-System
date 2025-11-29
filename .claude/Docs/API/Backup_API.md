# Backup API Dokumentation

## Uebersicht

Die Backup-API ermoeglicht die Verwaltung und Ausfuehrung von System-Backups fuer PostgreSQL, Redis, MinIO und Konfigurationsdateien.

**Basis-URL:** `/api/v1/backup`

**Authentifizierung:** Alle Endpoints erfordern Admin-Rechte (`is_superuser=true`)

---

## Endpoints

### GET /api/v1/backup/status

Gibt den aktuellen Status des Backup-Systems zurueck.

**Response:**
```json
{
  "service_aktiv": true,
  "encryption_aktiviert": true,
  "remote_sync_aktiviert": true,
  "remote_ziel": "user@backup:/backups",
  "retention_tage": 30,
  "speicherplatz": {
    "total_bytes": 536870912000,
    "verwendet_bytes": 214748364800,
    "frei_bytes": 322122547200,
    "verwendung_prozent": 40.0
  },
  "dateien": {
    "postgres": 5,
    "redis": 5,
    "minio": 3,
    "config": 10
  }
}
```

---

### GET /api/v1/backup/list

Listet alle vorhandenen Backup-Dateien auf.

**Query Parameter:**
- `backup_type` (optional): Filtert nach Typ (`postgres`, `redis`, `minio`, `config`)

**Response:**
```json
{
  "anzahl": 23,
  "backups": [
    {
      "typ": "postgres",
      "name": "postgres_20231128_120000.sql.gz",
      "pfad": "/var/backups/ablage/postgres/postgres_20231128_120000.sql.gz",
      "groesse_bytes": 104857600,
      "groesse_mb": 100.0,
      "erstellt": "2023-11-28T12:00:00",
      "verschluesselt": true
    }
  ]
}
```

---

### POST /api/v1/backup/postgres

Erstellt ein PostgreSQL-Datenbank-Backup.

**Request Body:**
```json
{
  "encrypt": true  // Optional, Standard: aus Konfiguration
}
```

**Response:**
```json
{
  "erfolg": true,
  "backup_typ": "postgres",
  "pfad": "/var/backups/ablage/postgres/postgres_20231128_143022.sql.gz",
  "groesse_bytes": 104857600,
  "dauer_sekunden": 45.2,
  "validiert": true,
  "verschluesselt": true,
  "nachricht": "PostgreSQL-Backup erfolgreich erstellt"
}
```

---

### POST /api/v1/backup/redis

Erstellt ein Redis-Datenbank-Backup.

**Response:**
```json
{
  "erfolg": true,
  "backup_typ": "redis",
  "pfad": "/var/backups/ablage/redis/redis_20231128_143022.rdb.gz",
  "groesse_bytes": 52428800,
  "dauer_sekunden": 12.5,
  "validiert": true,
  "nachricht": "Redis-Backup erfolgreich erstellt"
}
```

---

### POST /api/v1/backup/minio

Erstellt ein MinIO Object Storage Backup.

**Response:**
```json
{
  "erfolg": true,
  "backup_typ": "minio",
  "pfad": "/var/backups/ablage/minio/minio_20231128_143022.tar.gz",
  "groesse_bytes": 1073741824,
  "dauer_sekunden": 180.3,
  "nachricht": "MinIO-Backup erfolgreich erstellt"
}
```

---

### POST /api/v1/backup/config

Erstellt ein Konfigurations-Backup (Umgebungsvariablen, Docker-Compose, etc.).

**Response:**
```json
{
  "erfolg": true,
  "backup_typ": "config",
  "pfad": "/var/backups/ablage/config/config_20231128_143022.tar.gz",
  "groesse_bytes": 1048576,
  "dauer_sekunden": 2.1,
  "nachricht": "Konfigurations-Backup erfolgreich erstellt"
}
```

---

### POST /api/v1/backup/full

Erstellt ein vollstaendiges Backup aller Komponenten (PostgreSQL, Redis, MinIO, Konfiguration).

**Response:**
```json
{
  "erfolg": true,
  "erfolgreich": 4,
  "fehlgeschlagen": 0,
  "nachricht": "Vollstaendiges Backup erfolgreich. 4/4 Komponenten gesichert.",
  "details": [
    {
      "typ": "postgres",
      "erfolg": true,
      "pfad": "/var/backups/ablage/postgres/postgres_20231128_143022.sql.gz",
      "groesse_mb": 100.0
    },
    {
      "typ": "redis",
      "erfolg": true,
      "pfad": "/var/backups/ablage/redis/redis_20231128_143022.rdb.gz",
      "groesse_mb": 50.0
    },
    {
      "typ": "minio",
      "erfolg": true,
      "pfad": "/var/backups/ablage/minio/minio_20231128_143022.tar.gz",
      "groesse_mb": 1024.0
    },
    {
      "typ": "config",
      "erfolg": true,
      "pfad": "/var/backups/ablage/config/config_20231128_143022.tar.gz",
      "groesse_mb": 1.0
    }
  ]
}
```

---

### POST /api/v1/backup/full/async

Startet ein vollstaendiges Backup als Hintergrund-Task (Celery).

**Response:**
```json
{
  "task_id": "abc123-def456-ghi789",
  "status": "gestartet",
  "nachricht": "Vollstaendiges Backup als Hintergrund-Task gestartet"
}
```

---

### POST /api/v1/backup/retention

Wendet die Retention-Policy an und loescht alte Backups.

**Response:**
```json
{
  "erfolg": true,
  "geloescht_gesamt": 12,
  "details": {
    "postgres": 3,
    "redis": 3,
    "minio": 2,
    "config": 4
  },
  "nachricht": "Retention-Policy angewendet. 12 alte Backups geloescht."
}
```

---

### POST /api/v1/backup/sync

Synchronisiert lokale Backups zum konfigurierten Remote-Server.

**Response (Erfolg):**
```json
{
  "erfolg": true,
  "ziel": "user@backup.server.local:/backups/ablage",
  "synchronisiert": true,
  "nachricht": "Backup-Synchronisation zum Remote-Server erfolgreich"
}
```

**Response (Deaktiviert):**
```json
{
  "erfolg": false,
  "nachricht": "Remote-Synchronisation ist nicht aktiviert"
}
```

---

### GET /api/v1/backup/remote/list

Listet Backups auf dem Remote-Server auf (nur wenn Remote aktiviert).

**Response:**
```json
{
  "erfolg": true,
  "ziel": "user@backup.server.local:/backups/ablage",
  "dateien": [
    {
      "name": "postgres_20231128_120000.sql.gz.gpg",
      "groesse_bytes": 104857600
    }
  ]
}
```

---

## Fehler-Responses

Alle Endpoints verwenden deutsche Fehlermeldungen:

```json
{
  "detail": "Nur Administratoren haben Zugriff auf diese Funktion"
}
```

**HTTP Status Codes:**
- `200 OK` - Anfrage erfolgreich
- `400 Bad Request` - Ungueltige Anfrage (z.B. Remote-Sync deaktiviert)
- `401 Unauthorized` - Nicht authentifiziert
- `403 Forbidden` - Keine Admin-Rechte
- `500 Internal Server Error` - Backup fehlgeschlagen

---

## Konfiguration

Die Backup-Konfiguration erfolgt ueber Umgebungsvariablen:

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `BACKUP_DIR` | `/var/backups/ablage` | Backup-Verzeichnis |
| `BACKUP_RETENTION_DAYS` | `30` | Aufbewahrungsdauer in Tagen |
| `BACKUP_COMPRESSION` | `true` | gzip-Komprimierung aktivieren |
| `BACKUP_ENCRYPTION` | `false` | GPG-Verschluesselung aktivieren |
| `BACKUP_GPG_RECIPIENT` | - | GPG-Empfaenger fuer Verschluesselung |
| `BACKUP_REMOTE_ENABLED` | `false` | Remote-Sync aktivieren |
| `BACKUP_REMOTE_TARGET` | - | rsync-Ziel (user@host:/pfad) |

---

## Celery Beat Schedule

Automatisierte Backup-Tasks:

| Task | Zeitplan | Beschreibung |
|------|----------|--------------|
| `backup_full_task` | Taeglich 02:30 | Vollstaendiges Backup |
| `apply_retention_task` | Sonntag 03:00 | Alte Backups loeschen |
| `sync_to_remote_task` | Taeglich 04:00 | Remote-Synchronisation |
| `update_backup_metrics_task` | Alle 15 Min | Metriken aktualisieren |

---

## Prometheus Metriken

Die Backup-API exportiert folgende Metriken unter `/api/v1/metrics/backup`:

- `ablage_backup_success_total` - Erfolgreiche Backups (Counter)
- `ablage_backup_failure_total` - Fehlgeschlagene Backups (Counter)
- `ablage_backup_duration_seconds` - Backup-Dauer (Histogram)
- `ablage_backup_size_bytes` - Backup-Groesse (Gauge)
- `ablage_backup_disk_usage_bytes` - Speicherplatz belegt (Gauge)
- `ablage_backup_disk_free_bytes` - Speicherplatz frei (Gauge)
- `ablage_backup_file_count` - Anzahl Backup-Dateien (Gauge)
- `ablage_backup_last_success_timestamp` - Letztes erfolgreiches Backup (Gauge)

---

## Grafana Dashboard

Das Backup-Monitoring-Dashboard ist unter `ablage-backup-monitoring` verfuegbar und zeigt:

- Backup-Status (Zeit seit letztem Backup)
- Erfolgs-/Fehlerrate (24h)
- Speicherplatz-Nutzung
- Komponenten-Status (PostgreSQL, Redis, MinIO, Config)
- Retention & Aufraeumung
- Remote-Sync Status
- Backup-Historie

---

## Beispiel: cURL Requests

```bash
# Status abfragen
curl -X GET "http://localhost:8000/api/v1/backup/status" \
  -H "Authorization: Bearer $TOKEN"

# Vollstaendiges Backup starten
curl -X POST "http://localhost:8000/api/v1/backup/full" \
  -H "Authorization: Bearer $TOKEN"

# Backup-Liste abrufen
curl -X GET "http://localhost:8000/api/v1/backup/list?backup_type=postgres" \
  -H "Authorization: Bearer $TOKEN"

# Retention-Policy anwenden
curl -X POST "http://localhost:8000/api/v1/backup/retention" \
  -H "Authorization: Bearer $TOKEN"
```
