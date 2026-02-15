# Feature-Roadmap 2026 Q1-Q2: Ablage-System Next Level

**Erstellt**: 2026-02-15
**Quelle**: Ralph Loop Iteration 1 - Interview-gesteuerte Feature Discovery
**Methode**: 5 parallele Explore-Agents + 3-Runden User-Interview
**Status**: Genehmigt

---

## Uebersicht

| Phase | Fokus | Aufwand (geschaetzt) | Abhaengigkeiten |
|-------|-------|----------------------|-----------------|
| 1 | Security Haertung | 1 Sprint (~8-10 Tage) | Keine |
| 2 | Compliance Foundation | 1 Sprint (~10-13 Tage) | Phase 1 (DB SSL) |
| 3 | Integration Pipeline | 1.5 Sprints (~12-15 Tage) | Phase 2 (Event Sourcing) |
| 4 | OCR Intelligence | 0.5 Sprint (~5-7 Tage) | Keine |
| 5 | Frontend Analytics | 1.5 Sprints (~10-14 Tage) | Phase 2 (Events fuer KPIs) |
| 6 | Collaboration & UX | 1.5 Sprints (~12-16 Tage) | Phase 5 (Dashboard) |
| 7 | KI-Intelligence | 2+ Sprints (~15-20 Tage) | Phase 4 + 5 |

---

## Phase 1: Security Haertung

**Prioritaet**: KRITISCH - Vor allen neuen Features
**Geschaetzter Aufwand**: 8-10 Tage

### 1.1 Database SSL/TLS Konfiguration
- PostgreSQL `ssl = on` mit Server-Zertifikaten
- HBA-Rules fuer verschluesselte Verbindungen erzwingen
- Terraform-Modul `database/main.tf` erweitern
- Connection-Strings in allen Services auf `sslmode=require` umstellen
- **Dateien**: `infrastructure/terraform/modules/database/`, `docker-compose.yml`, `app/core/config.py`

### 1.2 HashiCorp Vault Integration
- Vault in Terraform-Module integrieren (Provider konfigurieren)
- Dynamic Secrets fuer DB-Credentials (auto-rotation)
- API Keys ueber Vault statt Env-Vars
- Ansible-Playbooks fuer Vault-Deployment haerten
- **Dateien**: `infrastructure/terraform/`, `infrastructure/ansible/`, `infrastructure/vault/`

### 1.3 API Error Standardisierung
- Standardisiertes ErrorResponse-Schema (error_code, message_de, correlation_id)
- Error-Code Katalog (ERR-DOC-001 bis ERR-API-999) - basierend auf bestehendem `app/core/exceptions.py`
- Middleware fuer automatisches Error-Wrapping (statt manuelle Exception-Handler pro Endpoint)
- Audit: Alle 180+ Endpoints pruefen und standardisieren
- **Dateien**: `app/core/exceptions.py`, `app/api/v1/*.py`, neue Middleware

---

## Phase 2: Compliance Foundation

**Prioritaet**: HOCH - GoBD/DSGVO Pflicht
**Geschaetzter Aufwand**: 10-13 Tage

### 2.1 GoBD Event Sourcing mit kryptographischer Hash-Chain
- Neues Modell `ComplianceEvent` mit SHA-256 Hash-Chain
- Jeder Eintrag referenziert Hash des vorherigen (Manipulationssicherheit)
- Digitale Signatur fuer kritische Events (Zahlungsfreigaben, Loeschungen)
- INSERT-only Policy (kein UPDATE/DELETE auf Event-Tabelle)
- Compliance-Report Generator fuer Steuerpruefer
- **Dateien**: `app/db/models_compliance.py` (neu), `app/services/compliance/event_sourcing_service.py` (neu), Migration

### 2.2 Saga Pattern fuer mehrstufige Workflows
- Saga-Framework mit kompensierenden Transaktionen
- InvoiceProcessingSaga: Rechnung -> DATEV-Export -> Buchung (mit Rollback)
- PaymentSaga: Freigabe -> SEPA -> Bankstatus (mit Kompensation)
- Saga-State in Redis + DB (crash recovery)
- Monitoring: Prometheus Metriken fuer Saga-Erfolg/Fehlschlag
- **Dateien**: `app/services/orchestration/saga_framework.py` (neu), `app/services/orchestration/sagas/` (neu)

---

## Phase 3: Integration Pipeline

**Prioritaet**: HOCH - Automation vervollstaendigen
**Geschaetzter Aufwand**: 12-15 Tage

### 3.1 Folder Import an Import-Rules anbinden (~2-3 Tage)
- `folder_import_service.py` um Import-Rule-Evaluation erweitern
- Polling-Loop durch Celery-Beat Task ersetzen
- EventBus-Integration (Folder-Import Events publizieren)
- Batch-UI fuer Folder-Import Queue im Frontend

### 3.2 Inbound Webhook Receiver (~3-4 Tage)
- `POST /api/v1/webhooks/receive` Endpoint
- HMAC-SHA256 Signatur-Verifizierung (Framework existiert in `app/core/webhook_signature.py`)
- Event-Mapping: Externe Events -> Interne EventBus Events
- Provider-spezifische Adapter: DATEV, DPD, UPS, DHL, GLS
- Dead-Letter-Queue fuer fehlgeschlagene Webhook-Verarbeitung

### 3.3 Visual Workflow Builder (~8-10 Tage)
- BPMN 2.0 kompatible Workflow-Engine im Backend
- Workflow-Modell in DB (versioniert, mit Rollback)
- React Flow oder BPMN.js basierter Drag&Drop Editor im Frontend
- Vordefinierte Nodes: Approval, Routing, Notification, Timer, Condition
- Template-Library: Rechnungsfreigabe, Mahnlauf, Dokumenten-Routing
- **Dateien**: `app/services/workflow/bpmn_engine.py` (neu), `frontend/src/features/workflow-builder/` (erweitern)

---

## Phase 4: OCR Intelligence

**Prioritaet**: MITTEL - Qualitaetsverbesserung
**Geschaetzter Aufwand**: 5-7 Tage

### 4.1 Duplicate Detection (~3-4 Tage)
- SHA-256 Content-Hash fuer exakte Duplikate
- Perceptual Hashing (pHash) fuer visuell aehnliche Dokumente
- Text-Similarity (TF-IDF + Cosine) fuer inhaltliche Duplikate
- Warnung VOR OCR-Processing (GPU-Ressourcen sparen)
- Konfigurierbarer Similarity-Threshold
- **Dateien**: `app/services/ocr/duplicate_detection_service.py` (neu)

### 4.2 Visual Document Diff (~2-3 Tage)
- Side-by-Side Vergleich von Dokumentversionen
- Text-Diff mit Highlighting (hinzugefuegt/entfernt/geaendert)
- Bild-Overlay Diff fuer gescannte Dokumente
- Integration in Document Viewer
- **Dateien**: `app/services/document_diff_service.py` (neu), `frontend/src/features/visual-diff/` (erweitern)

---

## Phase 5: Frontend Analytics

**Prioritaet**: HOCH - CFO/Management-Sichtbarkeit
**Geschaetzter Aufwand**: 10-14 Tage

### 5.1 Operations Tab
- Dokumente verarbeitet (heute/Woche/Monat) mit Sparkline
- OCR Accuracy % (Durchschnitt + Trend)
- Pending Approvals (Anzahl + aelteste)
- Error Rate (Prozent + Top-3 Error-Typen)
- Processing Time (Durchschnitt + P95)
- Drill-Down: Klick auf Metrik -> gefilterte Dokumentenliste

### 5.2 Finance Tab
- Offene Posten (Summe + Anzahl + Faelligkeits-Verteilung)
- Cashflow-Trend (30/60/90 Tage Chart)
- Skonto-Einsparungen (realisiert vs. verpasst)
- Ueberfaellige Rechnungen (Anzahl + Summe + Aging-Buckets)
- Dunning-Pipeline (Mahnstufen-Verteilung)

### 5.3 Team Tab
- Dokumente pro User (Produktivitaet)
- Approval-Zeiten (Durchschnitt pro Genehmiger)
- Quality Scores (OCR-Korrekturen pro User)
- Workload-Verteilung (Heatmap)

### 5.4 Infrastruktur
- Zeitraumfilter (heute/Woche/Monat/Quartal/custom)
- CSV + PDF Export
- Auto-Refresh (konfigurierbares Intervall)
- **Dateien**: `frontend/src/features/analytics/` (neu), Backend-APIs in `app/api/v1/analytics.py` (neu)

---

## Phase 6: Collaboration & UX Polish

**Prioritaet**: MITTEL-HOCH - Benutzer-Erlebnis
**Geschaetzter Aufwand**: 12-16 Tage

### 6.1 Document Annotations (~5-6 Tage)
- PDF/Bild-Bereich markieren -> Kommentar erstellen (wie Google Docs/Figma)
- Annotation-Modell: Position (x, y, width, height), Page, Text, Author, Resolved
- WebSocket-basierte Real-Time Sync
- @Mentions in Annotations
- Resolved/Unresolved Status mit Filter

### 6.2 Collaboration Features (~3-4 Tage)
- Presence-Avatare auf Dokumenten (wer schaut gerade?)
- Typing-Indicators
- Real-Time Cursor Positionen (optional)
- Activity Feed pro Dokument

### 6.3 Onboarding & Education (~2-3 Tage)
- Guided Product Tours (Schritt-fuer-Schritt mit Highlighting)
- Kontextuelle Tooltips ("Was ist das?")
- Checklisten-Onboarding fuer neue User
- Progressive Disclosure (Beginner vs. Power-User Modus)

### 6.4 Notification-System Haertung (~2-3 Tage)
- Notification-History (7 Tage persistiert)
- Action-Buttons in Toasts (Retry, Oeffnen, Snooze)
- Notification-Gruppierung (10x gleicher Error = 1 gruppierte Notification)
- Severity-Badges (INFO/WARNING/CRITICAL)
- Snooze-Funktion (erinnere mich in 1h/morgen)

### 6.5 Search & Filter UX (~2-3 Tage)
- Suchhistorie (letzte 20 Suchen)
- "Meinten Sie?" Vorschlaege bei Tippfehlern
- Saved Search Sharing mit Team
- Search-Result Previews (Hover -> Snippet)
- Suchperformance-Anzeige ("50.000 Dokumente in 2.3s")

---

## Phase 7: KI-Intelligence

**Prioritaet**: VISIONAER - Alleinstellungsmerkmal
**Geschaetzter Aufwand**: 15-20 Tage

### 7.1 KI-Chat-Assistent (~8-10 Tage)
- Chat-Interface im Frontend (Sidebar oder Modal)
- Natural Language Queries: "Zeig mir alle unbezahlten Rechnungen von Firma X"
- RAG-basiert: Dokumentenbestand als Wissensbasis (pgvector + Qdrant)
- Kontext-bewusst: Versteht aktuelle Seite/Filter
- Aktionen ausfuehren: "Genehmige alle Rechnungen unter 500 Euro"
- Deutsche Sprachverarbeitung

### 7.2 Predictive Intelligence (~7-10 Tage)
- Zahlungsprognosen: "Kunde X zahlt voraussichtlich am DD.MM."
- Cashflow-Vorhersage: ML-basierter 30/60/90 Tage Forecast
- Risiko-Scoring Verfeinerung: Historische Zahlungsmuster lernen
- Anomalie-Erkennung: Ungewoehnliche Rechnungen/Betraege flaggen
- Saisonale Muster: Erkennt Zahlungsverhalten nach Monat/Quartal

---

## Analyse-Grundlage

### 5 Explore-Agents (jeweils 100-250K Tokens analysiert)

| Agent | Scope | Score | Top-Gap |
|-------|-------|-------|---------|
| Backend Architecture | FastAPI, Services, DB, Docker | 8.5/10 | Saga Pattern, Event Sourcing |
| Frontend UX | 112 Feature-Dirs, Components, Routing | ~70% | Dashboard KPIs (30%), Onboarding (40%) |
| OCR Pipeline | OCR Services, Workers, ML Pipeline | 8/10 | Duplicate Detection, Document Diff |
| Integrations | DATEV, Lexware, Slack, Banking, Webhooks | 8.8/10 | Inbound Webhooks, Folder Import Rules |
| Security/Compliance | Auth, RBAC, Tests, GDPR, Infra | 80% | DB SSL/TLS, API Error Consistency |

### Interview-Entscheidungen

| Frage | Antwort |
|-------|---------|
| Dashboard-Tiefe | Volles Analytics-Modul (3 Tabs) |
| Compliance-Fokus | Beides parallel (GoBD + Saga) |
| Integration-Reihenfolge | Folder Import -> Webhooks -> Workflow Builder |
| UX-Tiefe | ALLE 4 Bereiche (Collab + Onboarding + Notifications + Search) |
| KPI-Fokus | Alles in Tabs (Operations + Finance + Team) |
| GoBD-Tiefe | Kryptographische SHA-256 Hash-Chain |
| Workflow-Builder UX | Power-User BPMN Drag&Drop UI |
| Kommentar-Tiefe | Annotations direkt im Dokument (Figma-Style) |
| Security-Ansatz | Sofort haerten (vor neuen Features) |
| OCR Intelligence | Beides (Duplicate Detection + Document Diff) |
| Roadmap-Reihenfolge | Security First |
| Wunsch-Features | KI-Assistent + Predictive Intelligence |
