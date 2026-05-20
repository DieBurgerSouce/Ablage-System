# Email & Folder Import (NEU: Januar 2026)

**Status**: Backend Ready (95%), Frontend Pending
**Migration**: Via IMPORT_BEAT_SCHEDULE in Celery

**Core Services**:
- `EmailImportService` - IMAP/SMTP Email-Abruf, Attachment-Extraktion
- `FolderImportService` - Dateisystem-Ueberwachung, Datei-Import
- `ImportRuleService` - Regelbasierte Verarbeitung (Bedingungen + Aktionen)
- `EmailSenderMatcherService` - Absender -> Entity Zuordnung

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| IMAP Support | Verschluesselte Email-Verbindung (SSL/TLS) |
| Absender-Matching | Automatische Entity-Zuordnung via Absender-Adresse |
| Folder-Watching | Verzeichnis-Ueberwachung mit konfigurierbarem Polling |
| Import Rules | Bedingungsbasierte Aktionen (Tags, Ordner, Auto-OCR) |
| Fehler-Retry | Automatische Wiederholung fehlgeschlagener Imports |

**API Endpoints - Email Configs**:
- `GET /api/v1/imports/email/configs` - Alle Email-Konfigurationen
- `POST /api/v1/imports/email/configs` - Neue Konfiguration erstellen
- `GET /api/v1/imports/email/configs/{id}` - Konfiguration abrufen
- `PATCH /api/v1/imports/email/configs/{id}` - Konfiguration aktualisieren
- `DELETE /api/v1/imports/email/configs/{id}` - Konfiguration loeschen
- `POST /api/v1/imports/email/configs/{id}/test` - IMAP-Verbindung testen
- `POST /api/v1/imports/email/configs/{id}/sync` - Manueller Email-Sync

**API Endpoints - Folder Configs**:
- `GET /api/v1/imports/folder/configs` - Alle Folder-Konfigurationen
- `POST /api/v1/imports/folder/configs` - Neue Konfiguration erstellen
- `PATCH /api/v1/imports/folder/configs/{id}` - Konfiguration aktualisieren
- `DELETE /api/v1/imports/folder/configs/{id}` - Konfiguration loeschen
- `POST /api/v1/imports/folder/configs/{id}/start` - Watcher starten
- `POST /api/v1/imports/folder/configs/{id}/stop` - Watcher stoppen
- `POST /api/v1/imports/folder/configs/{id}/poll` - Manueller Folder-Scan

**API Endpoints - Import Rules**:
- `GET /api/v1/imports/rules` - Alle Regeln auflisten
- `POST /api/v1/imports/rules` - Neue Regel erstellen
- `GET /api/v1/imports/rules/{id}` - Regel abrufen
- `PATCH /api/v1/imports/rules/{id}` - Regel aktualisieren
- `DELETE /api/v1/imports/rules/{id}` - Regel loeschen
- `POST /api/v1/imports/rules/{id}/test` - Regel testen
- `POST /api/v1/imports/rules/reorder` - Regelreihenfolge aendern
- `GET /api/v1/imports/rules/schema` - Verfuegbare Bedingungen/Aktionen

**API Endpoints - Import Logs**:
- `GET /api/v1/imports/logs` - Import-Logs mit Filterung
- `GET /api/v1/imports/logs/{id}` - Log-Details
- `POST /api/v1/imports/logs/{id}/retry` - Import wiederholen
- `GET /api/v1/imports/logs/stats` - Import-Statistiken

**Celery Tasks (IMPORT_BEAT_SCHEDULE)**:
- `import.sync_all_email_configs` - Alle 15 Min
- `import.poll_all_folder_configs` - Alle 5 Min
- `import.retry_failed_imports` - Alle 30 Min
- `import.cleanup_old_logs` - Taeglich 03:00
- `import.check_connection_health` - Alle 30 Min

**Datenmodell (EmailImportConfig)**:
```python
name: str                    # Anzeigename
email_address: str           # IMAP-Adresse
imap_server: str             # z.B. imap.gmail.com
imap_port: int               # 993 (SSL) oder 143 (STARTTLS)
use_ssl: bool                # True fuer Port 993
folder_filter: str           # INBOX, Rechnungen, etc.
subject_filter: Optional[str] # Regex-Filter fuer Betreff
sender_filter: Optional[str]  # Regex-Filter fuer Absender
auto_archive: bool           # Email nach Import archivieren
enabled: bool                # Konfiguration aktiv
last_sync_at: DateTime       # Letzter Sync-Zeitpunkt
```

**Datenmodell (FolderImportConfig)**:
```python
name: str                    # Anzeigename
folder_path: str             # Absoluter Pfad
file_patterns: List[str]     # ["*.pdf", "*.jpg", "*.png"]
recursive: bool              # Unterordner einbeziehen
delete_after_import: bool    # Datei nach Import loeschen
polling_interval: int        # Sekunden zwischen Scans
enabled: bool                # Konfiguration aktiv
watcher_active: bool         # Watcher laeuft aktuell
```

**Datenmodell (ImportRule)**:
```python
name: str                    # Regelname
description: Optional[str]   # Beschreibung
priority: int                # Ausfuehrungsreihenfolge (niedrig = zuerst)
conditions: List[dict]       # Bedingungen (AND-verknuepft)
actions: List[dict]          # Auszufuehrende Aktionen
enabled: bool                # Regel aktiv
apply_to_email: bool         # Auf Email-Imports anwenden
apply_to_folder: bool        # Auf Folder-Imports anwenden
```

**Rule Conditions (Beispiele)**:
- `{"field": "sender", "operator": "contains", "value": "@amazon.de"}`
- `{"field": "subject", "operator": "matches", "value": "Rechnung.*"}`
- `{"field": "filename", "operator": "ends_with", "value": ".pdf"}`
- `{"field": "file_size", "operator": "greater_than", "value": 1048576}`

**Rule Actions (Beispiele)**:
- `{"type": "set_folder", "folder_id": "uuid-..."}`
- `{"type": "add_tags", "tags": ["rechnung", "amazon"]}`
- `{"type": "set_entity", "entity_id": "uuid-..."}`
- `{"type": "trigger_ocr", "ocr_backend": "auto"}`
- `{"type": "send_notification", "channel": "slack"}`

**SECURITY**:
- Email-Passwoerter werden verschluesselt gespeichert (AES-256-GCM)
- Folder-Paths werden gegen Path-Traversal validiert
- NIEMALS Email-Inhalte in Logs
