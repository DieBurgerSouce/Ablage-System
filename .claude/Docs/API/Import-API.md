# Import API Documentation

**Version**: 1.0
**Status**: Backend Ready (95%), Frontend Pending
**Last Updated**: 2026-01-17

---

## Uebersicht

Die Import API ermoeglicht den automatisierten Import von Dokumenten aus Email-Postfaechern und Dateisystem-Ordnern. Sie unterstuetzt regelbasierte Verarbeitung und automatische Entity-Zuordnung.

### Basis-URL

```
/api/v1/imports
```

### Authentifizierung

Alle Endpoints erfordern JWT-Authentication. Einige Endpoints erfordern Admin-Rechte.

---

## Email Import Konfigurationen

### GET /imports/email/configs

Listet alle Email-Import-Konfigurationen des aktuellen Benutzers.

**Response**:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Rechnungs-Postfach",
      "email_address": "rechnungen@firma.de",
      "imap_server": "imap.provider.de",
      "imap_port": 993,
      "use_ssl": true,
      "folder_filter": "INBOX/Rechnungen",
      "subject_filter": "Rechnung|Invoice",
      "sender_filter": null,
      "auto_archive": true,
      "enabled": true,
      "last_sync_at": "2026-01-17T10:30:00Z",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

### POST /imports/email/configs

Erstellt eine neue Email-Import-Konfiguration.

**Request Body**:
```json
{
  "name": "Rechnungs-Postfach",
  "email_address": "rechnungen@firma.de",
  "imap_server": "imap.provider.de",
  "imap_port": 993,
  "imap_password": "geheim",
  "use_ssl": true,
  "folder_filter": "INBOX",
  "subject_filter": "Rechnung.*",
  "sender_filter": "@lieferant.de$",
  "auto_archive": true,
  "enabled": true
}
```

**Felder**:
| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| name | string | Ja | Anzeigename der Konfiguration |
| email_address | string | Ja | Email-Adresse fuer IMAP-Login |
| imap_server | string | Ja | IMAP-Server-Adresse |
| imap_port | int | Nein | Port (Standard: 993) |
| imap_password | string | Ja | IMAP-Passwort (wird verschluesselt gespeichert) |
| use_ssl | bool | Nein | SSL verwenden (Standard: true) |
| folder_filter | string | Nein | IMAP-Ordner (Standard: INBOX) |
| subject_filter | string | Nein | Regex-Filter fuer Betreff |
| sender_filter | string | Nein | Regex-Filter fuer Absender |
| auto_archive | bool | Nein | Email nach Import archivieren |
| enabled | bool | Nein | Konfiguration aktiv (Standard: true) |

**Response**: 201 Created
```json
{
  "id": "uuid",
  "name": "Rechnungs-Postfach",
  ...
}
```

### GET /imports/email/configs/{config_id}

Ruft eine einzelne Email-Konfiguration ab.

**Response**: 200 OK oder 404 Not Found

### PATCH /imports/email/configs/{config_id}

Aktualisiert eine Email-Konfiguration.

**Request Body**: Partielle Aktualisierung moeglich (nur geaenderte Felder)
```json
{
  "enabled": false,
  "subject_filter": "Neue.*Rechnung"
}
```

### DELETE /imports/email/configs/{config_id}

Loescht eine Email-Konfiguration.

**Response**: 204 No Content

### POST /imports/email/configs/{config_id}/test

Testet die IMAP-Verbindung einer Konfiguration.

**Response**:
```json
{
  "success": true,
  "message": "Verbindung erfolgreich",
  "mailbox_count": 42,
  "unread_count": 5
}
```

**Fehler-Response**:
```json
{
  "success": false,
  "message": "Verbindung fehlgeschlagen: Authentication failed",
  "error_code": "IMAP_AUTH_ERROR"
}
```

### POST /imports/email/configs/{config_id}/sync

Fuehrt einen manuellen Email-Sync durch.

**Query Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| limit | int | Maximale Anzahl zu importierender Emails (Standard: 50) |
| since_date | date | Nur Emails seit diesem Datum |

**Response**:
```json
{
  "status": "started",
  "task_id": "celery-task-uuid",
  "message": "Email-Sync gestartet"
}
```

---

## Folder Import Konfigurationen

### GET /imports/folder/configs

Listet alle Folder-Import-Konfigurationen.

**Response**:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Scanner-Ordner",
      "folder_path": "/scans/eingang",
      "file_patterns": ["*.pdf", "*.jpg", "*.png"],
      "recursive": false,
      "delete_after_import": false,
      "polling_interval": 60,
      "enabled": true,
      "watcher_active": true,
      "last_poll_at": "2026-01-17T10:35:00Z"
    }
  ],
  "total": 1
}
```

### POST /imports/folder/configs

Erstellt eine neue Folder-Import-Konfiguration.

**Request Body**:
```json
{
  "name": "Scanner-Ordner",
  "folder_path": "/scans/eingang",
  "file_patterns": ["*.pdf", "*.jpg"],
  "recursive": true,
  "delete_after_import": false,
  "polling_interval": 60,
  "enabled": true
}
```

**Felder**:
| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| name | string | Ja | Anzeigename der Konfiguration |
| folder_path | string | Ja | Absoluter Pfad zum Ordner |
| file_patterns | list | Nein | Glob-Patterns (Standard: ["*.pdf"]) |
| recursive | bool | Nein | Unterordner einbeziehen (Standard: false) |
| delete_after_import | bool | Nein | Datei nach Import loeschen (Standard: false) |
| polling_interval | int | Nein | Polling-Intervall in Sekunden (Standard: 60) |
| enabled | bool | Nein | Konfiguration aktiv (Standard: true) |

### PATCH /imports/folder/configs/{config_id}

Aktualisiert eine Folder-Konfiguration.

### DELETE /imports/folder/configs/{config_id}

Loescht eine Folder-Konfiguration.

### POST /imports/folder/configs/{config_id}/start

Startet den Folder-Watcher.

**Response**:
```json
{
  "status": "started",
  "message": "Folder-Watcher gestartet"
}
```

### POST /imports/folder/configs/{config_id}/stop

Stoppt den Folder-Watcher.

**Response**:
```json
{
  "status": "stopped",
  "message": "Folder-Watcher gestoppt"
}
```

### POST /imports/folder/configs/{config_id}/poll

Fuehrt einen manuellen Folder-Scan durch.

**Response**:
```json
{
  "status": "started",
  "task_id": "celery-task-uuid",
  "files_found": 3,
  "message": "Folder-Scan gestartet"
}
```

---

## Import Rules

### GET /imports/rules

Listet alle Import-Regeln (sortiert nach Prioritaet).

**Query Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| enabled | bool | Nur aktive/inaktive Regeln |
| apply_to | string | Filter: "email", "folder", oder "both" |

**Response**:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Amazon-Rechnungen",
      "description": "Rechnungen von Amazon automatisch taggen",
      "priority": 10,
      "conditions": [
        {"field": "sender", "operator": "contains", "value": "@amazon.de"}
      ],
      "actions": [
        {"type": "add_tags", "tags": ["rechnung", "amazon"]},
        {"type": "set_folder", "folder_id": "uuid"}
      ],
      "enabled": true,
      "apply_to_email": true,
      "apply_to_folder": false,
      "match_count": 47,
      "last_match_at": "2026-01-16T14:22:00Z"
    }
  ],
  "total": 1
}
```

### POST /imports/rules

Erstellt eine neue Import-Regel.

**Request Body**:
```json
{
  "name": "Amazon-Rechnungen",
  "description": "Rechnungen von Amazon automatisch taggen",
  "priority": 10,
  "conditions": [
    {"field": "sender", "operator": "contains", "value": "@amazon.de"}
  ],
  "actions": [
    {"type": "add_tags", "tags": ["rechnung", "amazon"]}
  ],
  "enabled": true,
  "apply_to_email": true,
  "apply_to_folder": false
}
```

### GET /imports/rules/schema

Gibt verfuegbare Bedingungen und Aktionen zurueck.

**Response**:
```json
{
  "conditions": {
    "fields": [
      {"name": "sender", "type": "string", "applies_to": ["email"]},
      {"name": "subject", "type": "string", "applies_to": ["email"]},
      {"name": "filename", "type": "string", "applies_to": ["email", "folder"]},
      {"name": "file_size", "type": "number", "applies_to": ["email", "folder"]},
      {"name": "file_extension", "type": "string", "applies_to": ["email", "folder"]}
    ],
    "operators": [
      {"name": "equals", "types": ["string", "number"]},
      {"name": "not_equals", "types": ["string", "number"]},
      {"name": "contains", "types": ["string"]},
      {"name": "not_contains", "types": ["string"]},
      {"name": "starts_with", "types": ["string"]},
      {"name": "ends_with", "types": ["string"]},
      {"name": "matches", "types": ["string"], "description": "Regex-Match"},
      {"name": "greater_than", "types": ["number"]},
      {"name": "less_than", "types": ["number"]}
    ]
  },
  "actions": [
    {"type": "set_folder", "params": ["folder_id"]},
    {"type": "add_tags", "params": ["tags"]},
    {"type": "set_entity", "params": ["entity_id"]},
    {"type": "trigger_ocr", "params": ["ocr_backend"]},
    {"type": "send_notification", "params": ["channel", "message"]},
    {"type": "skip_import", "params": []}
  ]
}
```

### PATCH /imports/rules/{rule_id}

Aktualisiert eine Import-Regel.

### DELETE /imports/rules/{rule_id}

Loescht eine Import-Regel.

### POST /imports/rules/{rule_id}/test

Testet eine Regel gegen Beispieldaten.

**Request Body**:
```json
{
  "test_data": {
    "sender": "rechnung@amazon.de",
    "subject": "Ihre Amazon-Rechnung",
    "filename": "rechnung_2026_01.pdf",
    "file_size": 125000
  }
}
```

**Response**:
```json
{
  "matches": true,
  "matched_conditions": [
    {"field": "sender", "operator": "contains", "value": "@amazon.de", "matched": true}
  ],
  "actions_to_execute": [
    {"type": "add_tags", "tags": ["rechnung", "amazon"]}
  ]
}
```

### POST /imports/rules/reorder

Aendert die Reihenfolge der Regeln.

**Request Body**:
```json
{
  "rule_ids": ["uuid-1", "uuid-2", "uuid-3"]
}
```

---

## Import Logs

### GET /imports/logs

Listet Import-Logs mit Filterung.

**Query Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| source | string | Filter: "email" oder "folder" |
| status | string | Filter: "success", "failed", "pending", "processing" |
| config_id | uuid | Filter nach Konfiguration |
| since | datetime | Logs seit Zeitpunkt |
| until | datetime | Logs bis Zeitpunkt |
| limit | int | Maximale Anzahl (Standard: 50, Max: 500) |
| offset | int | Offset fuer Pagination |

**Response**:
```json
{
  "items": [
    {
      "id": "uuid",
      "source": "email",
      "config_id": "uuid",
      "config_name": "Rechnungs-Postfach",
      "status": "success",
      "filename": "rechnung_amazon.pdf",
      "file_size": 125000,
      "document_id": "uuid",
      "entity_id": "uuid",
      "entity_name": "Amazon EU S.a.r.l.",
      "rules_applied": ["uuid-1"],
      "error_message": null,
      "metadata": {
        "email_subject": "Ihre Amazon-Rechnung",
        "email_sender": "rechnung@amazon.de",
        "email_date": "2026-01-16T12:00:00Z"
      },
      "started_at": "2026-01-16T12:01:00Z",
      "completed_at": "2026-01-16T12:01:05Z",
      "created_at": "2026-01-16T12:01:00Z"
    }
  ],
  "total": 1,
  "has_more": false
}
```

### GET /imports/logs/{log_id}

Ruft Details eines Import-Logs ab.

### POST /imports/logs/{log_id}/retry

Wiederholt einen fehlgeschlagenen Import.

**Response**:
```json
{
  "status": "queued",
  "task_id": "celery-task-uuid",
  "message": "Import wird wiederholt"
}
```

### GET /imports/logs/stats

Gibt Import-Statistiken zurueck.

**Query Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| period | string | "day", "week", "month" (Standard: "week") |
| source | string | Filter: "email", "folder", oder "all" |

**Response**:
```json
{
  "period": "week",
  "source": "all",
  "summary": {
    "total_imports": 156,
    "successful": 148,
    "failed": 8,
    "success_rate": 94.87,
    "total_size_bytes": 45678900,
    "avg_processing_time_ms": 3200
  },
  "by_day": [
    {"date": "2026-01-11", "total": 22, "successful": 21, "failed": 1},
    {"date": "2026-01-12", "total": 18, "successful": 18, "failed": 0}
  ],
  "by_source": {
    "email": {"total": 120, "successful": 115, "failed": 5},
    "folder": {"total": 36, "successful": 33, "failed": 3}
  },
  "top_errors": [
    {"message": "IMAP connection timeout", "count": 3},
    {"message": "File format not supported", "count": 2}
  ]
}
```

---

## Celery Tasks

Die folgenden Celery Tasks werden automatisch via Beat Schedule ausgefuehrt:

| Task | Intervall | Beschreibung |
|------|-----------|--------------|
| `import.sync_all_email_configs` | Alle 15 Min | Sync aller aktiven Email-Konfigurationen |
| `import.poll_all_folder_configs` | Alle 5 Min | Poll aller aktiven Folder-Konfigurationen |
| `import.retry_failed_imports` | Alle 30 Min | Automatischer Retry fehlgeschlagener Imports |
| `import.cleanup_old_logs` | Taeglich 03:00 | Bereinigung alter Logs (> 90 Tage) |
| `import.check_connection_health` | Alle 30 Min | Prueft Verbindungen, sendet Alerts |

---

## Fehler-Codes

| Code | HTTP Status | Beschreibung |
|------|-------------|--------------|
| IMPORT_CONFIG_NOT_FOUND | 404 | Konfiguration nicht gefunden |
| IMPORT_CONFIG_EXISTS | 409 | Email-Adresse/Ordner bereits konfiguriert |
| IMPORT_RULE_NOT_FOUND | 404 | Regel nicht gefunden |
| IMPORT_LOG_NOT_FOUND | 404 | Log-Eintrag nicht gefunden |
| IMAP_AUTH_ERROR | 400 | IMAP-Authentifizierung fehlgeschlagen |
| IMAP_CONNECTION_ERROR | 400 | IMAP-Verbindung fehlgeschlagen |
| FOLDER_NOT_FOUND | 400 | Ordner nicht gefunden |
| FOLDER_ACCESS_DENIED | 403 | Keine Berechtigung fuer Ordner |
| INVALID_RULE_CONDITION | 400 | Ungueltige Regelbedingung |
| INVALID_RULE_ACTION | 400 | Ungueltige Regelaktion |

---

## Sicherheitshinweise

1. **Email-Passwoerter**: Werden mit AES-256-GCM verschluesselt gespeichert
2. **Folder-Paths**: Werden gegen Path-Traversal-Angriffe validiert
3. **Rate Limiting**: Email-Sync max. 10/Stunde pro Konfiguration
4. **Logging**: NIEMALS Email-Inhalte oder Passwoerter in Logs
5. **Multi-Tenant**: Konfigurationen sind Company-isoliert via RLS
