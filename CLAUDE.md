# Ablage-System OCR - Claude Code Schnellreferenz

> **Detaillierte Dokumentation**: `.claude/CLAUDE.md`
> **Memory-Dateien**: `.claude/memory/` (Auto-Managed)
> **Letzte Aktualisierung**: 2026-01-20

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

### MLOps Pipeline (Januar 2026)

**Status**: Production-Ready | **Migration**: Keine (JSONB-basiert)

| Service | Beschreibung |
|---------|--------------|
| `ModelRegistry` | Model Versioning mit Rollback-Capability |
| `RetrainingService` | Automatisches Retraining bei 100+ Korrekturen |

**Model Lifecycle**: DRAFT → CANDIDATE → ACTIVE → DEPRECATED/ROLLED_BACK

**Celery Tasks:**
- `mlops.check_retraining_threshold` - Taeglich 03:00
- `mlops.run_retraining` - GPU-Queue, max 1h
- `mlops.evaluate_model` - Entscheidet Promotion/Rejection
- `mlops.rollback_if_degraded` - Automatisch bei >5% Degradation
- `mlops.cleanup_old_versions` - Woechentlich, archiviert >90 Tage

**Details**: Siehe `.claude/CLAUDE.md` - MLOps Pipeline Sektion

### Help System (Januar 2026)

**Status**: Production-Ready | **Migration**: Keine (JSONB in User.preferences)

| Service | Beschreibung |
|---------|--------------|
| `Help System API` | Kontextuelle Hilfe, Onboarding, Tooltips, Video-Tutorials |

**API Endpoints:**
- `GET /api/v1/help/articles` - Hilfe-Artikel (mit Kategorie/Context-Filter)
- `GET /api/v1/help/articles/{article_id}` - Einzelner Artikel
- `GET /api/v1/help/articles/context/{context}` - Artikel fuer spezifische Seite
- `GET /api/v1/help/search?q=query` - Volltextsuche
- `GET /api/v1/help/tooltips/{feature_id}` - Feature-Tooltip
- `GET /api/v1/help/onboarding` - Onboarding-Status
- `PATCH /api/v1/help/onboarding/step/{step_id}` - Schritt als erledigt
- `POST /api/v1/help/onboarding/skip` - Onboarding ueberspringen
- `GET /api/v1/help/videos` - Video-Tutorials
- `GET/PATCH /api/v1/help/preferences` - User-Praeferenzen

**Features:**
- Kontextuelle Hilfe nach Seite/Feature
- 5-Schritt Onboarding-Tour mit Progress-Tracking
- Feature-Tooltips mit Dismiss-Funktion
- Video-Tutorial-Verknuepfungen
- Volltext-Suche mit Score-Ranking (Titel 1.0, Tags 0.7, Content 0.5)

**Frontend:** Alle Texte auf Deutsch, Markdown-Support fuer Artikel-Content

**Details**: Siehe `.claude/Docs/API/Help-API.md`

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

### Fraud Detection System (Januar 2026)

**Status**: Production-Ready

| Modul | Beschreibung |
|-------|--------------|
| `duplicate_invoice_detection` | Hash + Fuzzy-Matching fuer Duplikate |
| `price_anomaly_detection` | Historischer Preisvergleich |
| `phantom_supplier_detection` | Fiktive Lieferanten erkennen |
| `internal_fraud_patterns` | Expense-Abuse Muster |

**API Endpoints:** `/api/v1/fraud/*`

### Holding Dashboard (Januar 2026)

**Status**: Production-Ready

- Multi-Company Consolidated View
- Intercompany Transaction Tracking
- Cash Flow Aggregation per Company
- Company Comparison Metrics

**API Endpoints:** `/api/v1/holding/*`

### Predictive Cash Flow (Januar 2026)

**Status**: Production-Ready

- ML-basierte Prognose (7-90 Tage)
- What-If Scenario Analysis
- Skonto Optimization Recommendations
- Early Warning System

**API Endpoints:** `/api/v1/cashflow/*`

### Risk Intelligence (Januar 2026)

**Status**: Production-Ready

- Comprehensive Risk Profiles per Entity
- Industry Benchmark Comparisons
- Network Analysis (IBAN/Address)
- External Sources: Handelsregister, Insolvenzregister

**API Endpoints:** `/api/v1/risk/*`

### Subscription Management (Januar 2026)

**Status**: Production-Ready

- Tiers: Free, Basic, Professional, Enterprise
- Feature-Gating per Tier
- Upgrade/Downgrade Flows

**API Endpoints:** `/api/v1/subscriptions/*`

### Tenant Rate Limits (Januar 2026)

**Status**: Production-Ready

- Per-Company API Rate Limiting
- Usage Metrics Tracking
- Violation Logging

**API Endpoints:** `/api/v1/admin/rate-limits/*`

### Multi-Factor Authentication (Januar 2026)

**Status**: Production-Ready | **Migration**: Keine (JSONB in User-Model)

| Service | Beschreibung |
|---------|--------------|
| `MFAService` | TOTP (RFC 6238) basierte 2FA mit Backup-Codes |

**Features:**
- TOTP via Authenticator-Apps (Google, Microsoft, Authy)
- 10 Backup-Codes (bcrypt-gehashed)
- AES-256-GCM verschluesselte Secrets
- QR-Code Setup mit manuellem Secret-Fallback

**API Endpoints:**
- `GET /api/v1/mfa/status` - 2FA-Status abrufen
- `POST /api/v1/mfa/setup` - Setup initiieren (QR + Secret)
- `POST /api/v1/mfa/verify` - Setup verifizieren
- `POST /api/v1/mfa/disable` - 2FA deaktivieren
- `POST /api/v1/mfa/regenerate` - Backup-Codes neu generieren
- `POST /api/v1/mfa/validate` - TOTP-Code validieren
- `POST /api/v1/mfa/backup` - Backup-Code verwenden

**Frontend:** `/settings/security` - MFA Setup Wizard mit 4 Steps

**SECURITY**: TOTP-Secrets AES-256-GCM verschluesselt, Backup-Codes bcrypt-gehashed

### Data Loss Prevention (Januar 2026)

**Status**: Production-Ready | **Migration**: Keine (In-Memory Policies)

| Service | Beschreibung |
|---------|--------------|
| `DLPService` | Policy-basierte Zugriffskontrollen fuer Dokumente |

**Features:**
- Download-Restriktionen (Rollen, Zeitfenster, Tags)
- Automatische Wasserzeichen (Text, Position, Opacity)
- Sensitive Data Detection (Kreditkarte, IBAN, SSN, Email, etc.)
- Audit-Logging aller Zugriffe
- Benachrichtigungen bei Policy-Verletzungen

**DLP Actions:**
- `allow` - Zugriff erlauben
- `block` - Zugriff blockieren
- `watermark` - Mit Wasserzeichen erlauben
- `notify` - Erlauben + Admin benachrichtigen
- `audit_only` - Nur protokollieren

**API Endpoints:**
- `GET/POST/PATCH/DELETE /api/v1/dlp/policies` - Policy CRUD (Admin)
- `POST /api/v1/dlp/check` - Zugriffspruefung durchfuehren
- `POST /api/v1/dlp/scan` - Text auf sensible Daten scannen
- `GET /api/v1/dlp/sensitive-data-types` - Verfuegbare Typen

**Frontend:** `/admin/dlp` - Policy Management + Scanner Tool

**Sensitive Data Types:**
- Kreditkarten (Luhn-Algorithmus)
- IBAN (DE-Format)
- Sozialversicherungsnummer (US SSN)
- Steuer-IDs
- Email, Telefon, Geburtsdatum

### Bundesbank Basiszins-API (Januar 2026)

**Status**: Production-Ready | **Feature 18**

| Service | Beschreibung |
|---------|--------------|
| `BundesbankRateService` | Automatischer Abruf des Basiszinssatzes von der Bundesbank |

**Features:**
- SDMX-REST API Anbindung zur Deutschen Bundesbank
- Redis-Caching mit 6-Monats-TTL
- Fallback-Wert bei API-Ausfall (3.62% seit 01.07.2024)
- §288 BGB Verzugszins-Berechnung (B2B +9%, B2C +5%)

**API Endpoints:**
- `GET /api/v1/banking/dunning/interest-rates` - Aktuelle Verzugszinssaetze
- `GET /api/v1/banking/dunning/interest-rates/history` - Historische Basiszinssaetze
- `GET /api/v1/banking/dunning/interest-rates/calculate` - Verzugszins-Berechnung

**Datenmodell (BasiszinsData):**
```python
rate: Decimal           # Basiszinssatz (z.B. 3.62)
valid_from: str         # Gueltig ab (z.B. "2024-07-01")
valid_until: Optional[str]
source: BasiszinsSource # api, cache, fallback
```

### LaTeX Formula Parsing (Januar 2026)

**Status**: Production-Ready | **Feature 19**

| Service | Beschreibung |
|---------|--------------|
| `FormulaExtractionService` | LaTeX-Formeln aus OCR-Output extrahieren und parsen |

**Features:**
- Erkennung von Inline ($...$), Display ($$...$$) und equation-Formeln
- Formeltyp-Klassifikation (Gleichung, Bruch, Summe, Integral, Matrix)
- Kontext-Erkennung (Finanziell, Wissenschaftlich, Statistisch)
- Syntax-Validierung mit OCR-Fehler-Erkennung
- MathML-Konvertierung
- Numerische Wertextraktion mit Einheiten

**API Endpoints:**
- `POST /api/v1/ocr/formulas/extract` - Formeln aus Text extrahieren
- `POST /api/v1/ocr/formulas/parse` - Einzelne Formel parsen
- `POST /api/v1/ocr/formulas/validate` - Formel-Syntax validieren

### Tax Authority Export (Januar 2026)

**Status**: Production-Ready | **Feature 20**

| Service | Beschreibung |
|---------|--------------|
| `TaxAuthorityExportService` | GDPdU-konformer Export fuer Steuerpruefungen (§90 III AO) |

**Features:**
- GDPdU-konformer Export (XML + CSV)
- index.xml und DTD-Generierung fuer IDEA/ACL
- Tabellendefinitionen: Rechnungen, Bankbewegungen, Belege, Aenderungsprotokoll
- ZIP-Archiv mit MD5-Pruefsummen
- UTF-8 Encoding

**Kategorien:**
- `invoices_outgoing` / `invoices_incoming` - Rechnungen
- `bank_transactions` - Bankbewegungen
- `documents` - Belege
- `audit_log` - Aenderungsprotokoll

### Intercompany Reconciliation (Januar 2026)

**Status**: Production-Ready | **Feature 15**

| Service | Beschreibung |
|---------|--------------|
| `IntercompanyReconciliationService` | IC-Transaktionen abstimmen und Eliminierungen generieren |

**Features:**
- IC-Transaktionen zwischen Konzernfirmen
- Automatische Saldenabstimmung
- Differenzerkennung (Betrag, Datum, fehlendes Gegenkonto)
- Eliminierungsbuchungen fuer Konzernabschluss
- Multi-Tenant mit Company-Isolation

**API Endpoints:**
- `GET /api/v1/holding/ic/summary` - IC-Zusammenfassung
- `GET /api/v1/holding/ic/transactions` - IC-Transaktionen
- `GET /api/v1/holding/ic/balances` - IC-Salden
- `POST /api/v1/holding/ic/reconcile` - Abstimmung durchfuehren
- `GET /api/v1/holding/ic/eliminations` - Eliminierungsbuchungen
- `GET /api/v1/holding/ic/report` - Vollstaendiger Bericht

**Frontend:** `/holding/reconciliation` - Vollstaendige React-UI mit 4 Tabs

### Alert Center (Januar 2026)

**Status**: Production-Ready | **Migration**: 117

| Service | Beschreibung |
|---------|--------------|
| `AlertCenterService` | Zentrales Alert-Management mit Kategorisierung und Workflows |

**Alert-Kategorien:**
- `fraud` - Betrugsverdacht (Duplikate, Preisanomalien)
- `risk` - Risikowarnungen (High-Risk Entities, Zahlungsverzoegerungen)
- `compliance` - Compliance-Verletzungen (GDPR, GoBD, DLP)
- `deadline` - Fristwarnungen (Skonto, Rechnungen, Vertraege)
- `system` - Systemwarnungen (GPU, Disk, OCR-Fehlerrate)
- `security` - Sicherheitswarnungen (Login-Versuche, API-Missbrauch)
- `quality` - Qualitaetswarnungen (OCR-Confidence, Umlaute)
- `workflow` - Workflow-Alerts (Eskalation, Delegation)

**Schweregrade:** info, low, medium, high, critical

**API Endpoints:**
- `GET /api/v1/alerts` - Alert-Liste mit Filterung
- `GET /api/v1/alerts/stats` - Dashboard-Statistiken
- `POST /api/v1/alerts/{id}/acknowledge` - Als gelesen markieren
- `POST /api/v1/alerts/{id}/dismiss` - Verwerfen
- `POST /api/v1/alerts/{id}/resolve` - Als geloest markieren
- `POST /api/v1/alerts/{id}/escalate` - Eskalieren
- `POST /api/v1/alerts/bulk` - Massenaktionen

**Frontend:** `/alerts` - Dashboard mit Filtern, Statistiken, Quick-Actions

### AI Conversations Persistence (Januar 2026)

**Status**: Production-Ready | **Migration**: 120

| Service | Beschreibung |
|---------|--------------|
| `AIConversation` | Chat-Sessions mit dem KI-Finanzassistenten |
| `AIConversationMessage` | Einzelne Nachrichten (User/Assistant/System) |
| `AIConversationAction` | Vorgeschlagene/Ausgefuehrte Aktionen |
| `AIConversationFeedback` | Benutzer-Feedback zu Antworten |

**Features:**
- Chat-History Persistenz fuer Kontext-Bewahrung
- Intent-Erkennung (search, execute_action, explain, suggest_booking, etc.)
- Aktions-Tracking mit Bestaetigungs-Workflow
- Feedback-Sammlung fuer kontinuierliche Verbesserung
- Multi-Tenant Isolation via RLS Policies

**API Endpoints:**
- `GET /api/v1/ai/conversations` - Konversationen auflisten
- `POST /api/v1/ai/conversations` - Neue Konversation starten
- `GET /api/v1/ai/conversations/{id}` - Konversation abrufen
- `PATCH /api/v1/ai/conversations/{id}` - Konversation aktualisieren
- `DELETE /api/v1/ai/conversations/{id}` - Konversation loeschen
- `POST /api/v1/ai/conversations/{id}/messages` - Nachricht senden
- `GET /api/v1/ai/conversations/{id}/messages` - Nachrichten abrufen
- `POST /api/v1/ai/conversations/{id}/feedback` - Feedback geben
- `GET /api/v1/ai/conversations/{id}/actions` - Aktionen abrufen
- `POST /api/v1/ai/conversations/{id}/actions/{action_id}/confirm` - Aktion bestaetigen
- `POST /api/v1/ai/conversations/{id}/actions/{action_id}/cancel` - Aktion abbrechen
- `GET /api/v1/ai/conversations/stats/summary` - Statistiken

**Datenmodell:**
```python
# AIConversation
session_id: str           # Eindeutige Frontend-Session-ID
user_id: UUID             # Benutzer
company_id: UUID          # Multi-Tenant
title: str                # Automatisch generiert
context_page: str         # Seite wo gestartet
message_count: int        # Anzahl Nachrichten
action_count: int         # Anzahl Aktionen
is_starred: bool          # Favorit markiert
context_data: JSONB       # Zusaetzlicher Kontext

# AIConversationMessage
role: Enum                # user, assistant, system
content: str              # Markdown-formatiert
intent: Enum              # search, execute_action, etc.
confidence: float         # Intent-Konfidenz (0.0-1.0)
processing_time_ms: int   # Verarbeitungszeit
tokens_used: int          # Token-Nutzung
referenced_documents: JSONB

# AIConversationAction
action_type: str          # payment_run, approve_invoices, etc.
status: Enum              # proposed, confirmed, executed, cancelled, failed
parameters: JSONB         # Aktionsparameter
result: JSONB             # Ergebnis
requires_confirmation: bool
confirmed_by_id: UUID

# AIConversationFeedback
feedback_type: Enum       # helpful, not_helpful, incorrect, confusing
rating: int               # 1-5 Sterne
comment: str              # Freitext
correction: str           # Korrigierte Antwort
expected_intent: str      # Falls falsch erkannt
```

**SECURITY**: Konversationen sind Benutzer- und Company-isoliert via RLS
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
