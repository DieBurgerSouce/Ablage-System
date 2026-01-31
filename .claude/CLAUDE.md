# Ablage-System: Enterprise Document Processing Platform

<!-- AUTO-MANAGED: project-header -->
**Status**: Production-Ready (E2E Tests 2026-01-10)
**Version**: 1.1
**Philosophy**: Feinpoliert und durchdacht
**Deployment**: On-premises, no cloud dependencies
<!-- /AUTO-MANAGED: project-header -->

> **Schnellreferenz**: Siehe `CLAUDE.md` im Root-Verzeichnis
> **Memory-Dateien**: `.claude/memory/` (automatisch gepflegt)

---

## CRITICAL RULES

<!-- AUTO-MANAGED: critical-rules -->
| # | Rule | Requirement |
|---|------|-------------|
| 1 | **Security** | NEVER log sensitive content, API keys, PII. Secrets only in env vars |
| 2 | **German** | ALL user-facing text MUST be German. UTF-8 for umlauts |
| 3 | **GPU** | Monitor VRAM <85%. Graceful CPU fallback on OOM |
| 4 | **Type Safety** | NEVER use `Any` type. Use mypy strict mode |
| 5 | **Testing** | Tests MUST pass before commit. No exceptions |
| 6 | **On-Premises** | NO cloud services (AWS, GCP, Azure) |
| 7 | **shadcn/ui Select** | NIEMALS `value=""` nutzen (Crashes!) -> `value="auto"` oder `value="all"` |
| 8 | **Lexware PII** | NEVER log customer numbers, IBANs, VAT-IDs from Lexware imports |
| 9 | **SQL Injection** | ALWAYS validate JSONB column/key names. Use whitelists + regex patterns (CWE-89) |
| 10 | **HTTP Headers** | ALWAYS sanitize user input in headers. Prevent CRLF injection (CWE-113) |
<!-- /AUTO-MANAGED: critical-rules -->

---

## Documentation Index

### Memory Files (Auto-Managed)

| File | Content |
|------|---------|
| `.claude/memory/PROJECT_STATUS.md` | Service health, deployments |
| `.claude/memory/KNOWN_ISSUES.md` | Bugs, issues tracking |
| `.claude/memory/RECENT_CHANGES.md` | Changelog |
| `.claude/memory/DEPENDENCIES.md` | Tech stack versions |

### Detailed Documentation

| Category | Path |
|----------|------|
| **Coding Standards** | `.claude/Docs/Guides/Coding-Standards.md` |
| **Testing Requirements** | `.claude/Docs/Testing/Requirements.md` |
| **Lexware Integration** | See "Lexware Integration (NEU: Januar 2026)" section below |
| **API Documentation** | `.claude/Docs/API/` |
| **Architecture** | `.claude/Docs/Architecture/` |
| **Operations/Runbooks** | `.claude/Docs/Operations/` |
| **OCR Backends** | `.claude/Docs/OCR-Backends/` |
| **GPU Management** | `.claude/Docs/Architecture/GPU-Resource-Management.md` |

### Full Documentation Index

| Kategorie | Dokument | Pfad |
|-----------|----------|------|
| Architektur | Celery Task Orchestration | `.claude/Docs/Architecture/Celery-Task-Orchestration.md` |
| | Database Schema ERD | `.claude/Docs/Architecture/Database-Schema-ERD.md` |
| | Event-Driven Architecture | `.claude/Docs/Architecture/Event-Driven-Architecture-Guide.md` |
| | GPU Resource Management | `.claude/Docs/Architecture/GPU-Resource-Management.md` |
| API | API Dokumentation | `.claude/Docs/API/API_Documentation.md` |
| | Admin API Complete | `.claude/Docs/API/Admin-API-Complete.md` |
| | Error Catalog | `.claude/Docs/API/ErrorCatalog.md` |
| Testing | E2E Testing (Playwright) | `.claude/Docs/Testing/E2E-Testing-Playwright.md` |
| | GPU Testing Guide | `.claude/Docs/Testing/GPU-Testing-Guide.md` |
| Operations | Rollback Strategies | `.claude/Docs/Operations/Rollback-Strategies.md` |
| | Runbooks (19 Stueck) | `.claude/Docs/Operations/Runbooks/*.md` |
| Compliance | GDPR Checklist | `.claude/Docs/Compliance/gdpr-checklist.md` |
| Guides | Development Setup | `.claude/Docs/Guides/Development-Setup.md` |
| | Troubleshooting | `.claude/Docs/Guides/Troubleshooting-Guide.md` |
| **Integrations** | **Lexware Integration** | **See dedicated section: "Lexware Integration (NEU: Januar 2026)"** |

---

## Project Overview

Ablage-System is an intelligent document processing platform for German document digitization with multiple OCR backends. Built for enterprise on-premises deployment with GPU acceleration (RTX 4080).

### Architecture

```
+-------------------------------------------------------------+
|                    Ablage-System OCR                        |
+-------------------------------------------------------------+
|  Frontend (Nginx:80)     |  Grafana (:3002)  |  Prometheus  |
+-------------------------------------------------------------+
|                    FastAPI Backend (:8000)                  |
+-------------------------------------------------------------+
|  Celery Workers  |  Redis (:6380)  |  PostgreSQL (:5433)    |
+-------------------------------------------------------------+
|  OCR: DeepSeek | GOT-OCR | Surya | Surya-GPU               |
+-------------------------------------------------------------+
|                 GPU: NVIDIA RTX 4080 (16GB)                 |
+-------------------------------------------------------------+
```

### Core Capabilities

- **Multi-Backend OCR**: DeepSeek-Janus-Pro, GOT-OCR 2.0, Surya+Docling
- **German Optimization**: Fraktur support, 100% umlaut accuracy
- **4 Display Modes**: Dark, Light, Whitescreen, Blackscreen
- **GPU Acceleration**: RTX 4080 with CUDA 12.x
- **Cross-Module Orchestration**: Event-driven coordination
- **Lexware Integration**: Customer/supplier import with auto-linking

---

## Technology Stack

### Backend

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI 0.110+ |
| Python | 3.11+ |
| Database | PostgreSQL 16 + pgvector |
| Cache/Queue | Redis 7.x |
| Storage | MinIO (S3-compatible) |
| Task Queue | Celery 5.3+ |
| ORM | SQLAlchemy 2.0+ (async) |
| Validation | Pydantic v2 |

### OCR Backends

| Backend | VRAM | Strengths |
|---------|------|-----------|
| DeepSeek-Janus-Pro | 12GB | Best umlaut accuracy, Fraktur |
| GOT-OCR 2.0 | 10GB | Tables, formulas, fast |
| Surya + Docling | CPU | Layout analysis, fallback |
| Surya GPU | 4GB | Fast GPU variant |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | React 18 + TypeScript 5.x |
| Router | TanStack Router |
| State | TanStack Query |
| UI | shadcn/ui + Tailwind CSS |

#### Frontend Patterns

> **Detaillierte Dokumentation**: `.claude/Docs/Frontend/Patterns.md`

**Kernmuster**:
- TanStack Query + API Layer Pattern
- Infinite Scroll mit Pagination
- Auto-Navigation bei Single-Folder Entities
- Folder-spezifische Kategorien (Messer vs Folie)
- Nested Routes mit TanStack Router

#### Reusable UI Components

> **Detaillierte Dokumentation**: `.claude/Docs/Frontend/Components.md`

**Core Components**: EditableField, EnterpriseDataTable, MultiStepForm
**Ablage Components**: MoveFolderDialog, InvoiceTrackingBanner, TransactionTimeline
**Accessibility**: WCAG 2.1 AA, Keyboard-Navigation, German Loading/Error States

---

## Development Commands

```bash
# Docker Development (REQUIRED)
docker-compose up -d
docker-compose build frontend && docker-compose up -d frontend
docker-compose build backend && docker-compose up -d backend

# Tests
docker-compose exec backend pytest tests/unit/ -v
pytest --cov=app --cov-report=html

# Code Quality
ruff check . && mypy app/

# Database
alembic upgrade head
alembic revision --autogenerate -m "description"

# GPU
nvidia-smi
```

---

## Project Structure

```
Ablage_System/
+-- CLAUDE.md                 # Quick Reference
+-- .claude/
|   +-- CLAUDE.md             # This file (Core Reference)
|   +-- memory/               # AUTO-MANAGED files
|   +-- commands/             # Slash Commands
|   +-- hooks/                # Pre/Post Hooks
|   +-- agents/               # Subagents
|   +-- Docs/                 # Detailed Documentation
+-- app/
|   +-- main.py               # FastAPI Entry
|   +-- api/v1/               # API Endpoints
|   +-- core/                 # Config, Security
|   +-- db/                   # SQLAlchemy Models
|   +-- services/             # Business Logic
|   +-- workers/              # Celery Tasks
+-- frontend/                 # React + TypeScript
+-- infrastructure/           # Terraform, Ansible
+-- tests/                    # Unit + Integration
+-- docker-compose.yml
```

---

## Key Services

### Document Services (Canonical)

| Service | Path |
|---------|------|
| GDPR | `document_services/gdpr_service.py` |
| Export | `document_services/export_service.py` |
| Batch | `document_services/batch_service.py` |
| CRUD | `document_services/crud_service.py` |

### Enterprise Features

| Feature | Service |
|---------|---------|
| Cross-Module Orchestration | `orchestration/cross_module_orchestrator.py` |
| Financial Health | `privat/financial_health_service.py` |
| Portfolio Management | `privat/portfolio_service.py` |
| Lexware Import | `lexware_import_service.py` |
| Entity Linking | `document_entity_linker_service.py` |
| Entity Search | `entity_search_service.py` |
| **Risk Scoring** | `risk_scoring_service.py` |
| **Invoice Tracking** | API: `api/v1/invoices.py` |
| **Skonto-Tracking** | `banking/skonto_service.py` |
| **Teilzahlungen** | `banking/partial_payment_service.py` |
| **Document Chains** | `document_chain_service.py` |
| **Slack Integration** | `slack_service.py` |
| **Shipment Tracking** | `shipping/carrier_service.py` |
| **Email Import** | `imports/email_import_service.py` |
| **Folder Import** | `imports/folder_import_service.py` |
| **Import Rules** | `imports/import_rule_service.py` |
| **Alert Center** | `alert_center_service.py` |
| **DATEV Connect** | `datev/connect/datev_connector.py` |

---

## DATEV Connect Integration (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: 145 (add_datev_connect)

**Core Services** (`app/services/datev/connect/`):
- `DATEVConnector` - ERPConnector-basiert, OAuth2-Authentifizierung
- `DATEVAuthService` - OAuth2-Flow, Token-Refresh, CSRF-Schutz
- `KontierungsvorschlagService` - ML-basierte Kontierungsvorschlaege
- `GoBDComplianceService` - Festschreibung mit SHA-256 Hash

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| OAuth2 | DATEVconnect OAuth2-Authentifizierung mit Token-Refresh |
| Stammdaten | Bidirektionale Sync von Kunden/Lieferanten/Konten |
| Buchungsstapel | Push zu DATEV mit GoBD-konformer Festschreibung |
| Belegbilder | Upload zu DATEV Unternehmen Online (DUO) |
| Kontierung | ML-basierte Vorschlaege mit Learning-Loop |
| GoBD | SHA-256 Hash, Unveraenderbarkeit, Audit-Trail |

**API Endpoints**: `/api/v1/datev-connect/*`

**Celery Tasks** (automatisch):
- `datev.refresh_all_tokens` - Alle 4 Stunden
- `datev.sync_all_stammdaten` - Taeglich 06:45
- `datev.sync_kontenplan` - Taeglich 06:50
- `datev.push_buchungsstapel` - Alle 2 Stunden
- `datev.upload_pending_belege` - Stuendlich
- `datev.gobd_compliance_check` - Taeglich 05:55
- `datev.auto_festschreibung` - Monatlich am 5.

**Datenmodell** (6 neue Tabellen):
- `datev_connections` - OAuth2-Verbindungen
- `datev_kontenplan` - SKR03/SKR04 Cache
- `datev_buchungen` - GoBD-konforme Buchungssaetze
- `datev_beleglinks` - Belegbild-Verknuepfungen
- `datev_kontierung_patterns` - ML-Lernmuster
- `datev_sync_history` - Sync-Audit-Trail

**SECURITY**: Alle Credentials verschluesselt (AES-256-GCM), GoBD-Hash unveraenderbar.

**Frontend** (`/admin/datev-connect/*`):
- `ConnectionsPage` - Verbindungs-Verwaltung mit OAuth2-Flow
- `SyncStatusPage` - Sync-Dashboard mit manuellen Triggers
- `BuchungenPage` - Buchungen-Liste mit Festschreibung
- `KontierungPage` - ML-Kontierungsvorschlaege
- `KontenplanPage` - Kontenrahmen-Ansicht

**Tests**:
- Unit Tests: `tests/unit/services/datev/test_datev_connect.py`
- Integration Tests: `tests/integration/test_datev_connect_api.py`

---

## Lexware Integration (NEU: Januar 2026)

> **Detaillierte Dokumentation**: `.claude/Docs/Integrations/Lexware.md`

**Status**: ✅ Production-Ready (commit 5f9b5e55)
**Migration**: 089, 090

**Core Services**:
- `LexwareImportService` - Excel-Import, Konflikt-Erkennung
- `EntitySearchService` - Multi-Strategie-Suche (Kundennr, IBAN, VAT-ID)
- `DocumentEntityLinkerService` - Auto-Linking nach OCR (>75% Confidence)

**API Endpoints**: `/api/v1/lexware/*`, `/api/v1/entities/*`

**Frontend**: KundenPage, LieferantenPage mit Infinite Scroll (100 Items/Page)

---

## Entity Risk Scoring (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: 092 (entity_risk_scoring), 093 (invoice_tracking)

**Core Services**:
- `RiskScoringService` - Score-Berechnung (0-100) basierend auf 5 Faktoren
- `InvoiceTracking` - Rechnungsverfolgung mit Mahnstufen

**Risk Faktoren (Gewichtung)**:
| Faktor | Gewicht | Beschreibung |
|--------|---------|--------------|
| payment_delay | 35% | Durchschnittliche Zahlungsverzögerung |
| default_rate | 25% | Ausfallrate (überfällige/gesamt) |
| invoice_volume | 15% | Gesamtvolumen (höher = weniger Risiko) |
| document_frequency | 10% | Dokumente/Monat (regelmäßig = weniger Risiko) |
| relationship_age | 15% | Beziehungsdauer (länger = weniger Risiko) |

**Celery Tasks (automatisch)**:
- `risk_scoring.calculate_all` - Täglich 02:00 (maintenance queue)
- `risk_scoring.calculate_single` - Nach Invoice-Updates (metadata queue)
- `risk_scoring.check_high_risk_entities` - Nach Batch (threshold: 75)
- `risk_scoring.generate_statistics` - Wöchentlich (Reporting)

**API Endpoints**: `/api/v1/invoices/*` (CRUD + mark-paid + increase-dunning)

**SECURITY**: NIEMALS Entity-Namen in Logs oder Responses (PII)!

---

## Skonto-Tracking (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: 094 (skonto_and_partial_payments)

**Core Services**:
- `SkontoService` - Skonto-Berechnung, Deadline-Tracking, Auto-Detection
- `PartialPaymentService` - Teilzahlungs-Verwaltung, Bank-Reconciliation

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Skonto-Berechnung | Automatische Berechnung von Skonto-Betrag und Deadline |
| Deadline-Alerts | Warnungen vor ablaufenden Skonto-Fristen |
| Auto-Detection | Erkennung von Skonto-Bedingungen aus OCR-Text |
| Teilzahlungen | Mehrere Zahlungen pro Rechnung, Status-Updates |
| Bank-Reconciliation | Verknuepfung mit Bank-Transaktionen |

**API Endpoints**:
- `GET /api/v1/invoices/{id}/skonto` - Skonto-Informationen abrufen
- `PATCH /api/v1/invoices/{id}/skonto` - Skonto-Bedingungen aktualisieren
- `POST /api/v1/invoices/{id}/apply-skonto` - Skonto anwenden
- `GET /api/v1/invoices/skonto/upcoming` - Bevorstehende Skonto-Fristen
- `POST /api/v1/invoices/{id}/payments` - Teilzahlung erfassen
- `GET /api/v1/invoices/{id}/payments` - Zahlungsuebersicht

**Datenmodell (InvoiceTracking erweitert)**:
```
skonto_percentage: Float    # z.B. 2.0 fuer 2%
skonto_days: Integer        # Tage fuer Skonto-Frist
skonto_deadline: DateTime   # Berechnete Frist
skonto_amount: Float        # Berechneter Betrag
skonto_used: Boolean        # True wenn genutzt
outstanding_amount: Float   # Ausstehender Betrag
is_partial_payment: Boolean # True bei Teilzahlungen
```

---

## Document Chain Tracking (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: 095 (document_chain_tracking)

**Core Service**: `DocumentChainService`

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Auftragsketten | Angebot → Auftrag → Lieferschein → Rechnung |
| Auto-Matching | Automatische Erkennung zusammengehoeriger Dokumente |
| Abweichungserkennung | Warnung bei Differenzen (Betraege, Mengen) |
| Chain-Status | Uebersicht ueber Kettenfortschritt |

**Relationship Types**:
- `QUOTE_TO_ORDER` - Angebot zu Auftrag
- `ORDER_TO_DELIVERY` - Auftrag zu Lieferschein
- `DELIVERY_TO_INVOICE` - Lieferschein zu Rechnung
- `QUOTE_TO_INVOICE` - Direktverknuepfung Angebot zu Rechnung

**API Endpoints**:
- `POST /api/v1/document-chains` - Neue Kette erstellen
- `GET /api/v1/document-chains` - Ketten auflisten
- `GET /api/v1/document-chains/{chain_id}` - Ketten-Details
- `POST /api/v1/document-chains/link` - Dokumente verknuepfen
- `GET /api/v1/document-chains/auto-match/{document_id}` - Auto-Match
- `GET /api/v1/document-chains/{chain_id}/discrepancies` - Abweichungen

**Matching-Kriterien (Confidence)**:
- Referenznummer identisch: 95%+ Confidence
- Kundennummer + Betrag: 85%+ Confidence
- Nur Betrag aehnlich: 70%+ Confidence

---

## Slack Integration (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: 100 (add_slack_integration)

**Core Service**: `SlackService` (`app/services/slack_service.py`)

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Webhook Support | Incoming Webhooks fuer einfache Nachrichten |
| Bot Token | Full Bot API mit erweiterten Funktionen |
| Rate Limiting | Sliding Window (30/min default) |
| Block Kit | Rich Message Formatting |
| Multi-Tenant | Company-spezifische Kanaele |

**Notification Types**:
- `document_processed` - Dokument verarbeitet
- `approval_required` - Genehmigung erforderlich
- `workflow_completed` - Workflow abgeschlossen
- `system_alert` - System-Benachrichtigung
- `payment_reminder` - Zahlungserinnerung
- `error_notification` - Fehlermeldung

**API Endpoints**: `/api/v1/slack/*`

**Frontend**: Admin-Seite unter `/admin/slack`

**Konfiguration**:
```python
SLACK_WEBHOOK_URL: SecretStr   # Incoming Webhook URL
SLACK_BOT_TOKEN: SecretStr     # Bot OAuth Token (xoxb-...)
SLACK_DEFAULT_CHANNEL: str     # Standard-Kanal
SLACK_ENABLED: bool            # Integration aktiviert
```

---

## Shipment Tracking (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: 100 (add_shipment_tracking)

**Core Service**: `CarrierService` (`app/services/shipping/carrier_service.py`)

**Unterstuetzte Carrier**:
| Carrier | Pattern | API |
|---------|---------|-----|
| DHL | `00340...`, `JJD...` | DHL Geschaeftskundenportal |
| DPD | 14-stellig, `01...` | DPD myDPD Business |
| Hermes | `H...` Prefix | Hermes ProfiPaketService |
| UPS | `1Z...` (18 Zeichen) | UPS Developer Kit (OAuth2) |
| GLS | 11-stellig | GLS Web API |
| FedEx | 12/15/20-stellig | FedEx Web Services (OAuth2) |
| Deutsche Post | `RR...DE`, `LX...` | Brief-API via DHL |

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Auto-Detection | Automatische Carrier-Erkennung via Tracking-Nummer-Pattern |
| Status-Normalisierung | Einheitliche Status ueber alle Carrier |
| Benachrichtigungen | Bei Zustellung, Problemen, Ruecksendung |
| Celery Tasks | Stuendlich aktive Sendungen, taeglich Verspaetungen |
| Multi-Tenant | Company-Isolation via RLS |

**API Endpoints**: `/api/v1/shipments/*`

**SECURITY**: Tracking-Nummern werden validiert (CWE-20) und URL-encoded (CWE-116).

**Celery Tasks**:
- `shipment_tracking.refresh_active` - Stuendlich um :15
- `shipment_tracking.check_delayed` - Taeglich um 09:00

**Konfiguration** (optional, Mock wenn nicht gesetzt):
```python
DHL_API_KEY: SecretStr          # DHL Geschaeftskundenportal
DPD_API_USER: str               # DPD myDPD User
DPD_API_PASSWORD: SecretStr     # DPD myDPD Password
UPS_CLIENT_ID: str              # UPS OAuth Client ID
UPS_CLIENT_SECRET: SecretStr    # UPS OAuth Secret
GLS_API_USER: str               # GLS API User
GLS_API_PASSWORD: SecretStr     # GLS API Password
FEDEX_CLIENT_ID: str            # FedEx OAuth Client ID
FEDEX_CLIENT_SECRET: SecretStr  # FedEx OAuth Secret
HERMES_API_KEY: SecretStr       # Hermes ProfiPaket Key
```

---

## Email & Folder Import (NEU: Januar 2026)

**Status**: ⚠️ Backend Ready (95%), Frontend Pending
**Migration**: Via IMPORT_BEAT_SCHEDULE in Celery

**Core Services**:
- `EmailImportService` - IMAP/SMTP Email-Abruf, Attachment-Extraktion
- `FolderImportService` - Dateisystem-Ueberwachung, Datei-Import
- `ImportRuleService` - Regelbasierte Verarbeitung (Bedingungen + Aktionen)
- `EmailSenderMatcherService` - Absender → Entity Zuordnung

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

---

## OCR Self-Learning System (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: Keine DB-Migration erforderlich (JSONB-basiert)

**Core Service**: `SelfLearningOCRService` (`app/services/ocr/self_learning_service.py`)

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Confidence-Kalibrierung | EMA-basierte Anpassung basierend auf User-Korrekturen |
| A/B Testing | Vergleich von Modell-Versionen mit Traffic-Split |
| Learning Modes | Aggressive (sofort), Cautious (verifiziert), Batch (taeglich) |
| Rollback | Automatischer Rollback bei Qualitaetsverschlechterung |

**Learning Modes**:
- `aggressive`: Jede User-Korrektur fliesst sofort ins System ein
- `cautious`: Nur verifizierte Korrekturen werden uebernommen
- `batch`: Korrekturen werden taeglich im Batch verarbeitet

**API Endpoints** (alle erfordern Authentifizierung):
- `POST /api/v1/ocr-learning/feedback` - Korrektur-Feedback uebermitteln
- `POST /api/v1/ocr-learning/calibrate` - Kalibrierte Confidence abrufen
- `GET /api/v1/ocr-learning/confidence-stats` - Confidence-Statistiken
- `POST /api/v1/ocr-learning/ab-test/start` - A/B Test starten (Admin)
- `GET /api/v1/ocr-learning/ab-test/{test_id}` - Test-Ergebnis abrufen
- `POST /api/v1/ocr-learning/ab-test/{test_id}/end` - Test beenden (Admin)
- `GET /api/v1/ocr-learning/stats` - Learning-Statistiken
- `POST /api/v1/ocr-learning/mode/{mode}` - Learning-Modus setzen (Admin)
- `GET /api/v1/ocr-learning/model-version` - Aktuelle Modell-Version

**Datenmodell (JSONB in AppConfig)**:
```python
CONFIDENCE_ADJUSTMENTS_KEY = "ocr_confidence_adjustments"
# Struktur:
{
    "backend": {"deepseek": -0.05, "got_ocr": 0.02},
    "field": {"deepseek": {"invoice_number": -0.03}},  # [backend][field] = adjustment
    "learning_mode": "aggressive",
    "updated_at": "2026-01-19T12:00:00Z"
}
```

**Frontend**:
- Route: `/admin/ocr-learning`
- Dashboard mit Statistiken, A/B Test Management, Mode Selection
- Komponenten: LearningStatsCards, ConfidenceAdjustmentsChart, ABTestCard, etc.

**SECURITY (Input-Validierung)**:
- OCR-Backends: Whitelist-Validierung (`ALLOWED_OCR_BACKENDS`)
- Feldnamen: Regex-Pattern (`^[a-zA-Z][a-zA-Z0-9_]{0,63}$`)
- Korrektur-Typen: Whitelist (`text`, `amount`, `date`, `entity`)
- Confidence-Werte: Range-Validierung (0.0 - 1.0)
- Test-IDs: Regex-Pattern (`^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$`) - Laengenbegrenzung 3-64 Zeichen, Path-Traversal-Schutz

---

## MLOps Pipeline (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: Keine (JSONB in AppConfig)

**Core Services**:
- `ModelRegistry` (`app/services/mlops/model_registry.py`) - Model Versioning, Rollback
- `RetrainingService` (`app/services/mlops/retraining_service.py`) - Retraining Orchestration

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Model Versioning | Versionierte Modelle mit Lineage-Tracking |
| Automatic Retraining | Bei 100+ Korrekturen oder wöchentlich |
| Quality Monitoring | Automatische Rollback bei >5% Degradation |
| Model Lifecycle | DRAFT → CANDIDATE → ACTIVE → DEPRECATED |

**Model Types**:
- `ocr_confidence` - OCR Confidence Calibration
- `ocr_backend_router` - Backend Selection Router
- `document_classifier` - Document Type Classification
- `entity_matcher` - Entity Matching Model
- `amount_extractor` - Amount/Currency Extraction
- `date_extractor` - Date Extraction

**Retraining Triggers**:
- `threshold` - 100+ unverarbeitete Korrekturen
- `scheduled` - Wöchentlich Sonntag 02:00
- `drift` - Qualitäts-Drift erkannt
- `manual` - Admin-Trigger
- `ab_test_winner` - A/B Test Gewinner

**Celery Tasks**:
- `mlops.check_retraining_threshold` - Täglich 03:00 (maintenance queue)
- `mlops.run_retraining` - GPU queue, max 1h
- `mlops.evaluate_model` - Nach Training, entscheidet Promotion
- `mlops.rollback_if_degraded` - Automatisch bei Qualitätsverlust
- `mlops.cleanup_old_versions` - Wöchentlich, archiviert >90 Tage
- `mlops.get_stats` - MLOps Statistiken abrufen

**Model Lifecycle**:
```
DRAFT → CANDIDATE → ACTIVE → DEPRECATED
                  ↓
            ROLLED_BACK → ARCHIVED
```

**Datenmodell (JSONB in AppConfig)**:
```python
MODEL_REGISTRY_KEY = "mlops_model_registry"
RETRAINING_CONFIG_KEY = "mlops_retraining_config"
RETRAINING_JOBS_KEY = "mlops_retraining_jobs"
```

---

## Alert Center (NEU: Januar 2026)

**Status**: ✅ Production-Ready
**Migration**: 117 (add_alerts_center)

**Core Service**: `AlertCenterService` (`app/services/alert_center_service.py`)

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Kategorisierung | 8 Alert-Kategorien (fraud, risk, compliance, deadline, system, security, quality, workflow) |
| Schweregrade | 5 Stufen (info, low, medium, high, critical) |
| Status-Workflow | new → acknowledged → in_progress → resolved/dismissed/escalated |
| Bulk Actions | Massenaktionen auf mehrere Alerts |
| Email-Digest | Konfigurierbare Zusammenfassungen (taeglich/woechentlich) |

**Alert-Kategorien**:
- `fraud` - Betrugsverdacht (FRAUD_001 bis FRAUD_004)
- `risk` - Risikowarnungen (RISK_001 bis RISK_004)
- `compliance` - Compliance-Verletzungen (COMP_001 bis COMP_005)
- `deadline` - Fristwarnungen (DEAD_001 bis DEAD_004)
- `system` - Systemwarnungen (SYS_001 bis SYS_005)
- `security` - Sicherheitswarnungen (SEC_001 bis SEC_004)
- `quality` - Qualitaetswarnungen (QUAL_001 bis QUAL_003)
- `workflow` - Workflow-Alerts (WORK_001 bis WORK_003)

**API Endpoints**:
- `GET /api/v1/alerts` - Alert-Liste mit Filterung und Paginierung
- `GET /api/v1/alerts/stats` - Dashboard-Statistiken
- `GET /api/v1/alerts/counts` - Zaehler nach Kategorie/Schweregrad/Status
- `GET /api/v1/alerts/{id}` - Einzelner Alert
- `POST /api/v1/alerts` - Manuellen Alert erstellen
- `POST /api/v1/alerts/{id}/acknowledge` - Als gelesen markieren
- `POST /api/v1/alerts/{id}/dismiss` - Verwerfen
- `POST /api/v1/alerts/{id}/resolve` - Als geloest markieren
- `POST /api/v1/alerts/{id}/escalate` - An Benutzer eskalieren
- `POST /api/v1/alerts/{id}/assign` - Benutzer zuweisen
- `POST /api/v1/alerts/bulk` - Massenaktionen

**Frontend**: `/alerts` - Vollstaendiges Dashboard mit:
- Statistik-Karten (total, new, critical, 24h)
- Kategorie-Zusammenfassung
- Filterbare Alert-Liste
- Quick-Actions (Acknowledge, Dismiss, Resolve)
- Detail-Dialog mit Kontext und Metadaten
- Bulk-Selection und Massenaktionen

**Datenmodell (Alert)**:
```python
id: UUID
alert_code: str              # z.B. FRAUD_001, RISK_002
title: str
message: str
category: AlertCategory      # fraud, risk, compliance, ...
severity: AlertSeverity      # info, low, medium, high, critical
status: AlertStatus          # new, acknowledged, resolved, ...
document_id: Optional[UUID]  # Verknuepftes Dokument
entity_id: Optional[UUID]    # Verknuepfter Geschaeftspartner
company_id: UUID             # Multi-Tenant
metadata: JSONB              # Kategorie-spezifische Daten
context: JSONB               # UI-Kontext
```

---

## Security Guidelines

| Area | Requirement |
|------|-------------|
| JWT Tokens | httpOnly cookies + CSRF |
| Token Expiration | Access: 15min, Refresh: 7 days |
| Password Hashing | bcrypt, cost factor 12 |
| Rate Limiting | Login: 5/15min, API: 100/min |
| Document Access | Owner check + sharing permissions |
| GDPR | Deletion within 30 days, audit logging |

**Detailed**: See `.claude/Docs/Compliance/` and `.claude/Docs/API/RateLimits.md`

---

## GPU Optimization

| Metric | Target |
|--------|--------|
| VRAM Usage | <85% (13.6GB of 16GB) |
| Batch Size | Dynamic based on available VRAM |
| Fallback | Automatic CPU fallback on OOM |

**Key Patterns**: `gpu_memory_guard()`, `GPUBatchProcessor`, `ModelManager`

**Detailed**: See `.claude/Docs/Architecture/GPU-Resource-Management.md`

---

## German Language Processing

```python
# User-facing messages MUST be German
ERROR_MESSAGES = {
    "document_not_found": "Dokument nicht gefunden",
    "processing_failed": "Verarbeitung fehlgeschlagen",
    "invalid_format": "Ungueltiges Dateiformat"
}
```

---

## Monitoring

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3002 |
| Prometheus | http://localhost:9090 |
| API Docs | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |

---

## Performance Targets

| Metric | Target |
|--------|--------|
| API Health Check | <50ms |
| Document Upload | <500ms |
| OCR (single page) | <2s GPU, <10s CPU |
| Concurrent Users | 100+ |
| Documents/Hour | 500+ GPU |

---

## Checklist for AI Assistant

Before completing any task:

- [ ] All code has type hints
- [ ] Tests written and passing
- [ ] German language for user-facing content
- [ ] GPU resources managed properly
- [ ] Security considerations addressed

---

## CLAUDE.md Maintenance

Claude SOLL diese Dateien automatisch pflegen:

1. **AUTO-MANAGED Sektionen**: Bei relevanten Aenderungen aktualisieren
2. **Memory-Dateien**: `.claude/memory/*.md` fuer dynamische Infos

### Wann aktualisieren:

- Nach Migrationen (alembic)
- Nach neuen Features/Services
- Nach Bug-Fixes
- Nach Konfigurations-Aenderungen

### AUTO-MANAGED Format:

```html
<!-- AUTO-MANAGED: section-name -->
Inhalt...
<!-- /AUTO-MANAGED: section-name -->
```

---

**Version**: 1.1
**Last Updated**: 2026-01-10
