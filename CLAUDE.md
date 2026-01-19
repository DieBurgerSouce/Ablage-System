# Ablage-System OCR - Claude Code Schnellreferenz

> **Detaillierte Dokumentation**: `.claude/CLAUDE.md`
> **Memory-Dateien**: `.claude/memory/` (Auto-Managed)
> **Letzte Aktualisierung**: 2026-01-17

---

<!-- AUTO-MANAGED: project-status -->
## Projekt-Status

| Feld | Wert |
|------|------|
| **Status** | Production-Ready |
| **Version** | 1.1 |
| **Hardware** | RTX 4080 16GB VRAM |
| **Sprache** | Deutsch-First (100% Umlaut-Genauigkeit) |

**Aktuelle Issues**: Siehe `.claude/memory/KNOWN_ISSUES.md`
**Aenderungen**: Siehe `.claude/memory/RECENT_CHANGES.md`
<!-- /AUTO-MANAGED: project-status -->

---

## `.claude/` Verzeichnis

```
.claude/
├── CLAUDE.md              # Core Reference (~500 Zeilen)
├── memory/                # AUTO-MANAGED Dateien
│   ├── PROJECT_STATUS.md  # Service Health, Deployments
│   ├── KNOWN_ISSUES.md    # Bugs, Issues
│   ├── RECENT_CHANGES.md  # Changelog
│   └── DEPENDENCIES.md    # Tech Stack
├── commands/              # Slash Commands
├── hooks/                 # Pre/Post Hooks
├── agents/                # Subagents
└── Docs/                  # Themen-Dokumentation (114 Dateien)
```

### Slash Commands

| Situation | Command |
|-----------|---------|
| System pruefen | `/check-system` |
| Deutsche Texte | `/validate-german` |
| Dokument verarbeiten | `/process-doc <pfad>` |
| GPU-Probleme | `/debug-gpu` |
| OCR-Qualitaet | `/ocr-benchmark` |
| Tests ausfuehren | `/quick-test` |
| Code reviewen | `/review-pr` |
| **WebApp testen** | **`/test-webapp`** |

### Verfuegbare Skills

| Situation | Skill |
|-----------|-------|
| Frontend/E2E Tests | `@webapp-tester-mcp` |
| OCR debuggen | `@ocr-debug` |
| Deutsche Texte | `@german-text` |
| Docker-Dev | `@docker-dev` |

---

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Ablage-System OCR                        │
├─────────────────────────────────────────────────────────────┤
│  Frontend (Nginx:80)     │  Grafana (:3002)  │  Prometheus  │
├──────────────────────────┴───────────────────┴──────────────┤
│                    FastAPI Backend (:8000)                  │
├─────────────────────────────────────────────────────────────┤
│  Celery Workers  │  Redis (:6380)  │  PostgreSQL (:5433)    │
├─────────────────────────────────────────────────────────────┤
│  OCR: DeepSeek | GOT-OCR | Surya | Surya-GPU               │
├─────────────────────────────────────────────────────────────┤
│                 GPU: NVIDIA RTX 4080 (16GB)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Docker-Only Entwicklung

```bash
# Starten
docker-compose up -d

# Frontend neu bauen
docker-compose build frontend && docker-compose up -d frontend

# Backend neu bauen
docker-compose build backend && docker-compose up -d backend

# Alles neu bauen
docker-compose build && docker-compose up -d

# Tests
docker-compose exec backend pytest tests/unit/ -v

# GPU-Status
nvidia-smi

# Celery Worker
celery -A app.workers.celery_app worker --loglevel=info --concurrency=1 --pool=solo
```

---

## OCR Backends

| Backend | VRAM | GPU | Staerken |
|---------|------|-----|----------|
| DeepSeek-Janus-Pro | 12GB | Ja | Beste Umlaut-Genauigkeit, Fraktur |
| GOT-OCR 2.0 | 10GB | Nein | Tabellen, Formeln, schnell |
| Surya + Docling | 0GB | Nein | CPU-Fallback, Layout |
| Surya GPU | 4GB | Ja | Schnelle GPU-Variante |

---

<!-- AUTO-MANAGED: enterprise-features -->
## Enterprise Features

### Lexware Integration (Januar 2026)

**Status**: Production-Ready | **Migration**: 089, 090

| Service | Beschreibung |
|---------|--------------|
| `LexwareImportService` | Excel-Import Kunden/Lieferanten (Folie & Messer) |
| `EntitySearchService` | Suche nach Kundennr, IBAN, VAT-ID, Matchcode |
| `DocumentEntityLinkerService` | Auto-Linking Dokumente → Entities (75%+ Confidence) |

**API Endpoints:**
- `POST /api/v1/lexware/import/customers`
- `POST /api/v1/lexware/import/suppliers`
- `POST /api/v1/lexware/link-documents`
- `GET /api/v1/lexware/statistics`

**Celery Tasks:**
- `entity_linking.link_all_documents` - Batch-Linking nach Import
- `entity_linking.link_single_document` - Nach OCR-Completion

**Key Features:**
- Intelligentes Konflikt-Handling (kritisch vs harmlos)
- Namensvarianten-Erkennung (Müller GmbH vs Mueller GmbH)
- Multi-Strategie Matching: Kundennr (99%), Matchcode (95%), IBAN/VAT (90%), Fuzzy-Name (80%), Adresse (75%)
- Pattern-Extraktion aus OCR-Text

**Datenmodell (BusinessEntity):**
```python
lexware_ids: JSONB  # {"folie": {"kd_nr": "12345", "matchcode": "MUELLER"}, ...}
company_presence: JSONB  # ["folie", "messer"]
primary_customer_number: str  # Hauptkundennummer
primary_supplier_number: str  # Hauptlieferantennummer
```

**Details**: Siehe `.claude/Docs/Integrations/Lexware.md`

### Entity Risk Scoring (Januar 2026)

**Status**: Production-Ready | **Migration**: 092, 093

| Service | Beschreibung |
|---------|--------------|
| `RiskScoringService` | Risiko-Score Berechnung (0-100) für Geschäftspartner |
| `InvoiceTracking` | Rechnungsverfolgung mit Mahnstufen (0-4) |

**Risk Faktoren:**
- payment_delay (35%): Zahlungsverzögerung in Tagen
- default_rate (25%): Ausfallrate (überfällig/gesamt)
- invoice_volume (15%): Rechnungsvolumen (höher = weniger Risiko)
- document_frequency (10%): Regelmäßigkeit der Dokumente
- relationship_age (15%): Beziehungsdauer in Monaten

**API Endpoints:**
- `GET/POST/PATCH/DELETE /api/v1/invoices/*` - CRUD
- `POST /api/v1/invoices/{id}/mark-paid` - Rechnung bezahlt
- `POST /api/v1/invoices/{id}/increase-dunning` - Mahnstufe erhöhen

**Celery Tasks:**
- `risk_scoring.calculate_all` - Täglich 02:00 (maintenance queue)
- `risk_scoring.calculate_single` - Nach Invoice-Updates (metadata queue)
- `risk_scoring.check_high_risk_entities` - High-Risk Alert (threshold: 75)

**SECURITY**: NIEMALS Entity-Namen in Logs/Responses (PII-Compliance)

### Skonto & Teilzahlungen (Januar 2026)

**Status**: Production-Ready | **Migration**: 094

| Service | Beschreibung |
|---------|--------------|
| `SkontoService` | Skonto-Berechnung, Deadline-Tracking, Auto-Detection |
| `PartialPaymentService` | Teilzahlungen, Bank-Reconciliation |

**API Endpoints:**
- `GET/PATCH /api/v1/invoices/{id}/skonto` - Skonto verwalten
- `POST /api/v1/invoices/{id}/apply-skonto` - Skonto anwenden
- `GET /api/v1/invoices/skonto/upcoming` - Ablaufende Fristen
- `POST/GET /api/v1/invoices/{id}/payments` - Teilzahlungen

**Features:**
- Auto-Detection von "2% Skonto 14 Tage" aus OCR
- Deadline-Alerts vor Ablauf
- Teilzahlungs-Tracking mit Status-Updates
- Bank-Abgleich (Reconciliation)

### Document Chain Tracking (Januar 2026)

**Status**: Production-Ready | **Migration**: 095

| Service | Beschreibung |
|---------|--------------|
| `DocumentChainService` | Auftragsketten Angebot→Auftrag→Lieferschein→Rechnung |

**API Endpoints:**
- `POST/GET /api/v1/document-chains` - Ketten erstellen/auflisten
- `POST /api/v1/document-chains/link` - Dokumente verknuepfen
- `GET /api/v1/document-chains/auto-match/{id}` - Auto-Matching
- `GET /api/v1/document-chains/{id}/discrepancies` - Abweichungen

**Features:**
- Auto-Matching ueber Referenznummer (95%+), Kunde+Betrag (85%+)
- Abweichungserkennung (Betraege, Mengen)
- Kettenfortschritt-Tracking

### Email & Folder Import (Januar 2026)

**Status**: Production-Ready | **Frontend**: Vollstaendig

| Service | Beschreibung |
|---------|--------------|
| `EmailImportService` | IMAP-Email-Abruf, Attachment-Extraktion, Entity-Matching |
| `FolderImportService` | Dateisystem-Ueberwachung, Auto-Import |
| `ImportRuleService` | Regelbasierte Verarbeitung (Bedingungen + Aktionen) |
| `EmailSenderMatcherService` | Absender → Entity Zuordnung (85%+ Confidence) |

**API Endpoints:**
- `GET/POST/PATCH/DELETE /api/v1/imports/email/configs` - Email-Konfigurationen
- `POST /api/v1/imports/email/configs/{id}/test` - IMAP-Verbindung testen
- `POST /api/v1/imports/email/configs/{id}/sync` - Manueller Email-Sync
- `GET/POST/PATCH/DELETE /api/v1/imports/folder/configs` - Folder-Konfigurationen
- `POST /api/v1/imports/folder/configs/{id}/start|stop|poll` - Watcher-Steuerung
- `GET/POST/PATCH/DELETE /api/v1/imports/rules` - Import-Regeln
- `GET /api/v1/imports/logs` - Import-Logs mit Filterung

**Celery Tasks (IMPORT_BEAT_SCHEDULE):**
- `import.sync_all_email_configs` - Alle 15 Min
- `import.poll_all_folder_configs` - Alle 5 Min
- `import.retry_failed_imports` - Alle 30 Min
- `import.cleanup_old_logs` - Taeglich 03:00
- `import.check_connection_health` - Alle 30 Min

**Features:**
- IMAP Support mit SSL/TLS
- Absender-Matching fuer automatische Entity-Zuordnung
- Folder-Watching mit konfigurierbarem Polling
- Import Rules mit Bedingungen und Aktionen
- Automatischer Retry bei Fehlern

**Frontend Routes:**
- `/admin/imports/` - Import Dashboard
- `/admin/imports/email` - Email-Konfigurationen
- `/admin/imports/folder` - Folder-Konfigurationen
- `/admin/imports/rules` - Import-Regeln Builder
- `/admin/imports/logs` - Import-Logs

**SECURITY**: Email-Passwoerter verschluesselt (AES-256-GCM), NIEMALS Email-Inhalte in Logs

### OCR Self-Learning System (Januar 2026)

**Status**: Production-Ready | **Migration**: Keine (JSONB-basiert)

| Service | Beschreibung |
|---------|--------------|
| `SelfLearningOCRService` | Confidence-Kalibrierung, A/B Testing, Learning Modes |

**Learning Modes:**
- `aggressive`: Jede User-Korrektur fliesst sofort ein
- `cautious`: Nur verifizierte Korrekturen
- `batch`: Taeglich im Batch

**API Endpoints:**
- `POST /api/v1/ocr-learning/feedback` - Korrektur-Feedback
- `POST /api/v1/ocr-learning/calibrate` - Kalibrierte Confidence
- `GET /api/v1/ocr-learning/stats` - Statistiken
- `POST /api/v1/ocr-learning/ab-test/start` - A/B Test starten (Admin)
- `POST /api/v1/ocr-learning/mode/{mode}` - Modus setzen (Admin)

**Frontend:** `/admin/ocr-learning` - Dashboard mit Stats, A/B Tests, Mode Selection

**SECURITY**: Input-Whitelist-Validierung fuer Backends, Feldnamen, Korrektur-Typen, Test-IDs (Regex + Laengenbegrenzung)

### Validation UI (Januar 2026)

**Status**: Production-Ready | **Features**: Keyboard + Swipe

**Keyboard Shortcuts:**
- `A` - Genehmigen (Approve)
- `R` - Ablehnen (Reject)
- `J/K` - Naechstes/Vorheriges Item
- `Enter/Space` - Item oeffnen
- `Escape` - Auswahl aufheben
- `Ctrl+A` - Alle auswaehlen

**Mobile Swipe:**
- Rechts swipen = Genehmigen (gruener Hintergrund)
- Links swipen = Ablehnen (roter Hintergrund)
- Threshold: 100px fuer Trigger
- Animierte Feedback-Anzeige
<!-- /AUTO-MANAGED: enterprise-features -->

---

<!-- AUTO-MANAGED: critical-rules -->
## Kritische Regeln

1. **Deutsche Texte**: ALLE Fehlermeldungen auf Deutsch
2. **GPU-Management**: VRAM unter 85% halten (max 13.6GB)
3. **Typ-Annotationen**: Pflicht fuer alle Python-Funktionen
4. **Sicherheit**: Keine Secrets im Code, keine PII in Logs
5. **Tests**: Muessen vor Commit bestehen
6. **Multi-Model Orchestration**: IMMER befolgen
7. **shadcn/ui Select**: NIEMALS `value=""` nutzen (Crashes!) → `value="auto"` oder `value="all"`
8. **Lexware PII**: NIEMALS Kundennummern, IBANs, VAT-IDs in Logs
<!-- /AUTO-MANAGED: critical-rules -->

---

## Multi-Model Orchestration

Bei jedem Prompt erhaeltst du einen `ORCHESTRATION ROUTING` Kontext. **BEFOLGEN!**

| Routing-Empfehlung | Aktion |
|--------------------|--------|
| `HAIKU` | `Task(subagent_type="haiku-task", model="haiku", ...)` |
| `SONNET` | `Task(subagent_type="sonnet-implementation", model="sonnet", ...)` |
| `OPUS` | Selbst machen |

**MCP Server:**
- `mcp__orchestration__route_task` - Optimalen Agent
- `mcp__orchestration__list_agents` - 15 Agenten anzeigen

---

## Monitoring URLs

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3002 (admin/admin123) |
| Prometheus | http://localhost:9090 |
| API Docs | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |

---

## Dokumentations-Index

| Thema | Pfad |
|-------|------|
| Core Reference | `.claude/CLAUDE.md` |
| Project Status | `.claude/memory/PROJECT_STATUS.md` |
| Known Issues | `.claude/memory/KNOWN_ISSUES.md` |
| Recent Changes | `.claude/memory/RECENT_CHANGES.md` |
| Dependencies | `.claude/memory/DEPENDENCIES.md` |
| API Docs | `.claude/Docs/API/` |
| Architecture | `.claude/Docs/Architecture/` |
| Testing | `.claude/Docs/Testing/` |
| Operations | `.claude/Docs/Operations/` |
| OCR Backends | `.claude/Docs/OCR-Backends/` |

---

## CLAUDE.md Maintenance

Claude SOLL diese Dateien automatisch pflegen:

1. **AUTO-MANAGED Sektionen**: Werden bei relevanten Aenderungen aktualisiert
2. **Memory-Dateien**: `.claude/memory/*.md` fuer dynamische Infos
3. **Wann aktualisieren**:
   - Nach Migrationen (alembic)
   - Nach neuen Features/Services
   - Nach Bug-Fixes
   - Nach Konfigurations-Aenderungen

**Format der AUTO-MANAGED Marker:**
```html
<!-- AUTO-MANAGED: section-name -->
Inhalt...
<!-- /AUTO-MANAGED: section-name -->
```
