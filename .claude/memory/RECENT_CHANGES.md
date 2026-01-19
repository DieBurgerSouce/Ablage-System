# Recent Changes

## 2026-01-19

### Security Hardening - BusinessContact & CustomerDetection

**Commits**: `63c83318`, `7363ef67`, `91bf95a8`
**Status**: ✅ Production-Ready

#### Multi-Tenant IDOR Prevention

| Fix | Beschreibung |
|-----|--------------|
| **BusinessContact API** | 11 Endpoints auf company_id umgestellt (vorher owner_id) |
| **CustomerDetectionService** | company_id Parameter zu find_similar_contacts, find_or_create_contact, process_document, merge_contacts |
| **Schema Alignment** | BusinessContactListResponse, MergeContactsResponse, DetectContactsResponse angepasst |
| **Defense-in-Depth** | API UND Service validieren company_id |

#### PII-Compliance Fix

| Stelle | Aenderung |
|--------|-----------|
| `find_or_create_contact()` | VAT-ID und Tax-ID aus Logger-Aufrufen entfernt |
| Lines 589, 604 | Nur noch contact_id geloggt (CLAUDE.md Rule 8) |

#### Design-Dokumentation

- CustomerDetection Celery Tasks: Design-Hinweis zu Document-Loading ohne company_id Filter dokumentiert

---

### Enterprise Feature Release - Phase 4

**Commit**: `626a7380`
**Status**: ✅ Production-Ready

#### 6 Neue Enterprise Features

| Feature | Beschreibung |
|---------|--------------|
| **Fraud Detection System** | Duplikat-Erkennung, Preis-Anomalien, Phantom-Lieferanten, Expense-Abuse |
| **Holding Dashboard** | Multi-Company Konsolidierung, Intercompany-Tracking, KPI-Vergleich |
| **Predictive Cash Flow** | ML-basierte Liquiditaets-Prognose (7-90 Tage), What-If Szenarien |
| **Risk Intelligence** | Umfassende Risk-Profile, Branchen-Benchmark, Netzwerk-Analyse |
| **Subscription Management** | Tier-System (Free/Basic/Pro/Enterprise), Feature-Gating |
| **Tenant Rate Limits** | Per-Company API-Limits, Usage-Metrics, Violation-Logging |

#### Fraud Detection Details

| Modul | Funktion |
|-------|----------|
| `duplicate_invoice_detection` | Hash + Fuzzy-Matching fuer doppelte Rechnungen |
| `price_anomaly_detection` | Vergleich mit historischen Preisdaten |
| `phantom_supplier_detection` | Erkennung fiktiver Lieferanten |
| `internal_fraud_patterns` | Expense-Abuse Muster |
| Alert Dashboard | Severity-Levels, Admin-konfigurierbare Schwellwerte |

#### Holding Dashboard Details

- Multi-Company Consolidated View
- Intercompany Transaction Tracking
- Cash Flow Aggregation per Company
- Company Comparison Metrics
- Real-time KPI Overview

#### Predictive Cash Flow Details

- ML-basierte Prognose (7, 14, 30, 90 Tage)
- Payment Prediction per Invoice
- What-If Scenario Analysis
- Skonto Optimization Recommendations
- Early Warning System

#### Risk Intelligence Details

- Comprehensive Risk Profiles per Entity
- Industry Benchmark Comparisons
- Trend Analysis (quarterly)
- Network Analysis (IBAN/Address Matching)
- External Sources: Handelsregister, Insolvenzregister

#### API Endpoints (Auswahl)

```
# Fraud Detection
GET/POST /api/v1/fraud/alerts
POST /api/v1/fraud/scan/{entity_id}
GET /api/v1/fraud/statistics

# Holding
GET /api/v1/holding/dashboard
GET /api/v1/holding/companies/{id}/kpis
GET /api/v1/holding/intercompany

# Predictive Cash Flow
GET /api/v1/cashflow/forecast
POST /api/v1/cashflow/scenario
GET /api/v1/cashflow/recommendations

# Risk Intelligence
GET /api/v1/risk/profile/{entity_id}
GET /api/v1/risk/portfolio
GET /api/v1/risk/benchmarks

# Subscriptions
GET/PATCH /api/v1/subscriptions
GET /api/v1/subscriptions/features
POST /api/v1/subscriptions/upgrade

# Tenant Rate Limits
GET /api/v1/admin/rate-limits
PATCH /api/v1/admin/rate-limits/{company_id}
GET /api/v1/admin/rate-limits/violations
```

---

### OCR Self-Learning System - Production-Ready

**Status**: ✅ Enterprise-Level implementiert
**Betroffene Dateien**:
- `app/services/ocr/self_learning_service.py` - Core Service
- `app/api/v1/ocr_learning.py` - API Endpoints mit Security
- `frontend/src/features/ocr-learning/` - Vollstaendiges Frontend
- `tests/unit/services/ocr/test_self_learning_service.py` - 30 Unit Tests
- `tests/unit/api/test_ocr_learning_api.py` - 34 Validation Tests (inkl. test_id Security Tests)

**Features**:
- Confidence-Kalibrierung mit EMA (Exponential Moving Average)
- A/B Testing fuer Modell-Versionen mit Traffic-Split
- 3 Learning Modes: aggressive, cautious, batch
- Automatischer Rollback bei Qualitaetsverschlechterung
- JSONB-basierte Persistenz (keine Migration erforderlich)

**Security Hardening**:
- Alle Endpoints erfordern Authentifizierung (Auth-Luecke gefixt)
- OCR-Backend Whitelist-Validierung
- Feldname Regex-Pattern gegen Injection
- Admin-only fuer kritische Operationen
- **test_id Validierung** (Review Iteration 3): Regex-Pattern + Laengenbegrenzung 3-64 Zeichen gegen Path-Traversal, SQL-Injection, XSS

**Frontend**:
- Dashboard unter `/admin/ocr-learning`
- LearningStatsCards, ConfidenceAdjustmentsChart, ABTestCard
- Toast-Benachrichtigungen, Loading-States, Error-Handling

---

### Enterprise Feature Release - Phase 3 Complete

**Commit**: `f0d59eae`
**Files Changed**: 211 files, ~19,500 additions, ~5,700 deletions

#### Frontend Features

| Feature | Beschreibung |
|---------|--------------|
| **Dashboard Enhanced** | CSS Grid mit ResizableWidgets, PresetSelector, ActivityFeed |
| **Workflow Builder** | ReactFlow visueller Editor mit NodePalette, Undo/Redo, Validation |
| **Skonto Tracking** | SkontoAlertBadge, SkontoDetailPanel fuer Rabatt-Management |
| **Teilzahlungen** | PaymentHistoryPanel mit Reconciliation-Status |
| **Import UI** | Email/Folder Import mit Rules Builder |
| **Smart Escalation** | KI-gestuetzte Aufgabenzuweisung Hooks |
| **Liquiditaet** | LiquidityForecast mit Recharts Waterfall Charts |

#### API Services (Neu)

| Service | Zeilen | Beschreibung |
|---------|--------|--------------|
| `budgets.ts` | 1048 | Kostenstellen mit Hierarchie, Varianzen, Alerts |
| `predictive-actions.ts` | 523 | Proaktive Aktionsvorschlaege (Mahnung, Skonto, Vertraege) |
| `workflows-api.ts` | 800+ | Workflow CRUD, Execution, Templates, Webhooks |
| `smart-escalation.ts` | 233 | KI-Zuweisungsempfehlungen, Team-Workload |
| `invoice-api.ts` | 200+ | Skonto und Teilzahlungs-Management |

#### Code Quality Fixes

| Datei | Problem | Fix |
|-------|---------|-----|
| `ActivityFeed.tsx` | Unsicherer Type Cast | `typeof` Guard hinzugefuegt |
| `PresetSelector.tsx` | Toter Code | Entfernt (`presetsByRole`, `DropdownMenuGroup`) |
| `dashboard/index.ts` | Fehlender Export | ActivityFeed Export hinzugefuegt |

#### Patterns & Standards

- Snake_case → camelCase Transformer durchgaengig
- TanStack Query mit korrekten staleTime/gcTime
- Zustand Stores mit persist Middleware
- WebSocket mit exponential Backoff
- Deutsche UI-Texte (100%)

---

## 2026-01-18

### SECURITY FIX: Workflow Module - Umfassende Multi-Tenant Isolation

**Status**: ✅ KRITISCH GEFIXT (4 Services, 15+ Methoden)
**Betroffene Dateien**:
- `app/services/workflow/workflow_trigger_service.py`
- `app/services/workflow/workflow_service.py`
- `app/services/workflow/workflow_execution_service.py`
- `app/api/v1/workflows.py`

---

#### 1. WorkflowService Multi-Tenant Fixes

**Problem**: ALLE CRUD-Methoden hatten KEINE company_id Validierung!
- User konnten Workflows anderer Companies lesen/aendern/loeschen

**Gefixte Methoden (7 Stueck)**:
| Methode | Fix |
|---------|-----|
| `get_workflow()` | company_id Filter + Security-Logging bei Cross-Tenant Versuch |
| `update_workflow()` | company_id Parameter, nutzt get_workflow() |
| `delete_workflow()` | company_id Parameter, nutzt get_workflow() |
| `duplicate_workflow()` | company_id Parameter, nutzt get_workflow() |
| `toggle_workflow()` | company_id Parameter, nutzt get_workflow() |
| `validate_workflow()` | user_id + company_id Parameter hinzugefuegt |
| `get_workflow_stats()` | user_id + company_id Parameter hinzugefuegt |

**Security-Logging implementiert**:
```python
# Bei Cross-Tenant Zugriffsversuch:
logger.warning(
    "cross_tenant_workflow_access_blocked",
    workflow_id=str(workflow_id),
    requested_company_id=str(company_id),
    user_id=str(user_id) if user_id else None,
)
```

---

#### 2. WorkflowTriggerService Multi-Tenant Fixes

**Gefixte Methoden (6 Stueck)**:
| Methode | Fix |
|---------|-----|
| `_find_matching_workflows()` | Pflicht-Parameter `company_id: UUID` |
| `on_document_event()` | Dokument-First-Laden fuer company_id |
| `check_condition_triggers()` | company_id aus Dokument extrahieren |
| `handle_webhook()` | company_id Validierung, Workflows ohne company_id abgelehnt |
| `_find_workflow_by_webhook_path()` | company_id Filter |
| `trigger_workflow_manually()` | company_id an _get_workflow() weitergeben |
| `_get_workflow()` | company_id Parameter fuer Isolation |
| `regenerate_webhook_secret()` | company_id an _get_workflow() weitergeben |

---

#### 3. WorkflowExecutionService Multi-Tenant Fix

**Problem**: `start_execution()` lud Workflow NUR nach ID ohne company_id Check

**Fix**: company_id Parameter + Validierung mit Security-Logging

---

#### 4. API Endpoints Multi-Tenant Fixes

**Alle Workflow API Endpoints jetzt mit company_id**:
```python
# Pattern in allen Endpoints:
company_id = await get_user_company_id(db, current_user)
await service.method(..., company_id=company_id)
```

| Endpoint | Fix |
|----------|-----|
| `GET /workflows/{id}` | company_id aus UserCompany |
| `PATCH /workflows/{id}` | company_id aus UserCompany |
| `DELETE /workflows/{id}` | company_id aus UserCompany |
| `POST /workflows/{id}/duplicate` | company_id aus UserCompany |
| `POST /workflows/{id}/toggle` | company_id aus UserCompany |
| `POST /workflows/{id}/validate` | company_id aus UserCompany |
| `GET /workflows/{id}/stats` | company_id aus UserCompany |
| `POST /workflows/{id}/trigger` | company_id aus UserCompany |
| `POST /workflows/{id}/webhook/regenerate` | company_id aus UserCompany |

---

### SECURITY FIX: WorkflowTriggerService Event-Based Triggers

**Status**: ✅ KRITISCH GEFIXT (Frueherer Fix in dieser Session)
**Tests**: `tests/unit/services/workflow/test_workflow_trigger_service.py` (NEU - 15 Tests)

**Problem 1**: `_find_matching_workflows()` filterte NICHT nach `company_id`
- User konnten Workflows anderer Companies triggern (Cross-Tenant Execution)

**Problem 2**: `_find_workflow_by_webhook_path()` und `handle_webhook()` hatten keine company_id Validierung
- Webhooks konnten Workflows ohne company_id ausfuehren

**Unit Tests** (13 passed, 2 skipped):
- Webhook ohne company_id wird abgelehnt ✅
- Webhook mit company_id wird akzeptiert ✅
- on_document_event laedt Document zuerst ✅
- Dokument ohne company_id wird abgelehnt ✅
- check_condition_triggers filtert nach company_id ✅

---

### SECURITY REVIEW: Weitere Findings dokumentiert

**Status**: ⚠️ TEILWEISE NOCH OFFEN

**Verbleibendes Problem**:
| Service | Bug | Risk |
|---------|-----|------|
| `BusinessContact` Model | Existiert nicht in `models.py` obwohl importiert | **MEDIUM** |

**Design-Hinweise** (kein Bug):
- `EmailSenderMatcherService`: Kein `company_id` Filter - aber BusinessEntity ist absichtlich firmenuebergreifend
- `duplicate_detection_service`: `company_id` optional aber bei Verwendung korrekt

**Verifizierte Fixes aus frueherer Session**:
- ✅ `CommentService._find_user_by_username()` - UserCompany JOIN mit company_id
- ✅ `EscalationService._find_user_by_role()` - UserCompany JOIN mit company_id
- ✅ `document_tasks.py:create_task()` - company_id zu get_task() hinzugefuegt

---

### SECURITY FIX: Multi-Tenant Isolation in CommentService @Mentions

**Status**: ✅ KRITISCH GEFIXT
**Datei**: `app/services/collaboration/comment_service.py`

**Problem**: `_find_user_by_username()` hat `company_id` als Parameter erhalten, aber NICHT in den SQL-Queries verwendet. Das war eine **Multi-Tenant Violation** - User aus JEDER Company konnten erwähnt werden!

**Vorher (UNSICHER)**:
```python
result = await self.db.execute(
    select(User).where(
        and_(
            func.lower(User.username) == func.lower(username),
            User.is_active == True,
            # KEINE company_id Filterung!
        )
    )
)
```

**Nachher (SICHER)**:
```python
result = await self.db.execute(
    select(User)
    .join(UserCompany, UserCompany.user_id == User.id)
    .where(
        and_(
            func.lower(User.username) == func.lower(username),
            User.is_active == True,
            UserCompany.company_id == company_id,  # Multi-Tenant Isolation!
        )
    )
)
```

**Aenderungen**:
- Import `UserCompany` hinzugefuegt (Zeile 40)
- `_find_user_by_username()` gefixt mit UserCompany Join (Zeilen 500-538)
- Beide Queries (username + full_name) jetzt company-isoliert

**Neue Tests hinzugefuegt** (`tests/unit/services/collaboration/test_comment_service.py`):
- `TestMultiTenantIsolation::test_find_user_by_username_uses_company_filter` - Prueft UserCompany Join
- `TestMultiTenantIsolation::test_find_user_fullname_uses_company_filter` - Prueft auch full_name Query
- `TestMultiTenantIsolation::test_mention_isolation_no_cross_company_leaks` - Smoke-Test fuer Isolation

**Test-Ergebnis**: 110 Collaboration Tests bestanden (33 CommentService + 21 Digest + 28 Escalation + 28 DocumentTask)

---

### SECURITY FIX: Multi-Tenant Isolation in EscalationService Role Lookup

**Status**: ✅ KRITISCH GEFIXT
**Datei**: `app/services/collaboration/escalation_service.py`

**Problem**: `_find_user_by_role()` hat `company_id` als Parameter erhalten, aber NICHT in den SQL-Queries verwendet. Eskalationen konnten an Admins/Manager aus ANDEREN Firmen geleitet werden!

**Vorher (UNSICHER)**:
```python
result = await self.db.execute(
    select(User.id).where(
        and_(
            User.is_superuser == True,
            User.is_active == True,
            # KEINE company_id Filterung!
        )
    ).limit(1)
)
```

**Nachher (SICHER)**:
```python
result = await self.db.execute(
    select(User.id)
    .join(UserCompany, UserCompany.user_id == User.id)
    .where(
        and_(
            UserCompany.company_id == company_id,
            UserCompany.role.in_(["owner", "admin"]),
            User.is_active == True,
        )
    )
    .limit(1)
)
```

**Aenderungen**:
- Import `UserCompany` hinzugefuegt (Zeile 32)
- `_find_user_by_role()` gefixt mit UserCompany Join (Zeilen 420-490)
- Admin-Suche: erst Company-Admin (owner/admin Rolle), dann Superuser der Company
- Manager-Suche: UserCompany mit role="manager"

**Neue Tests hinzugefuegt** (`tests/unit/services/collaboration/test_escalation_service.py`):
- `test_find_user_by_role_uses_company_filter` - Prueft UserCompany Join
- `test_find_user_by_role_manager` - Prueft Manager-Rolle

**Test-Ergebnis**: 110 Collaboration Tests bestanden (33 Comment + 21 Digest + 28 Escalation + 28 DocumentTask)

---

### FIX: Document Tasks API - company_id Parameter fehlte

**Status**: ✅ GEFIXT
**Datei**: `app/api/v1/document_tasks.py`

**Problem**: In `create_task()` wurde nach dem Erstellen der Task `get_task()` OHNE `company_id` aufgerufen, um die Beziehungen zu laden.

**Vorher (Inkonsistent)**:
```python
# Lade Beziehungen fuer Response
task = await task_service.get_task(task.id)  # OHNE company_id!
```

**Nachher (Korrekt)**:
```python
# Lade Beziehungen fuer Response
# SECURITY: company_id muss IMMER uebergeben werden fuer Multi-Tenant Isolation
task = await task_service.get_task(task.id, company_id=document.company_id)
```

**Risiko-Bewertung**: NIEDRIG - Da die Task gerade erstellt wurde, gab es keinen direkten Leak. Aber Best-Practice ist, company_id IMMER zu uebergeben.

---

## 2026-01-17

### Collaboration Suite: CommentService (VOLLSTAENDIG)

**Status**: ✅ Production-Ready (105 Collaboration Tests bestanden)
**Migration**: 103 (enhance_document_comments)

**Implementierung**:

| Komponente | Datei | Zeilen | Status |
|------------|-------|--------|--------|
| Migration | `alembic/versions/103_enhance_document_comments.py` | 157 | ✅ |
| Service | `app/services/collaboration/comment_service.py` | 943 | ✅ |
| Unit Tests | `tests/unit/services/collaboration/test_comment_service.py` | 814 | ✅ 30 passed |
| API Tests | `tests/unit/api/test_comments_api.py` | ~900 | ✅ 49 passed |

**Model-Erweiterungen** (`app/db/models.py:9478-9538`):
```python
company_id = Column(UUID, ForeignKey("companies.id"), nullable=False)  # Multi-Tenant
field_reference = Column(String(100), nullable=True)  # Inline-Kommentare
deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft-Delete
deleted_by_id = Column(UUID, ForeignKey("users.id"), nullable=True)
```

**CommentService Features**:
- CRUD: create, get, update, delete (soft + hard)
- Threads: `get_comment_thread()`, `create_reply()`, `count_replies()`
- @Mention: `parse_mentions_from_text()` mit Regex `@(\w+(?:\.\w+)?)`
- Feld-Kommentare: `get_field_comments()`, `get_all_field_comments()`
- Reactions: `add_reaction()`, `remove_reaction()` mit JSONB-Array
- Statistiken: `get_comment_statistics()` (total, replies, commenters, mentions, 7/30 Tage)
- Notifications: UserNotification fuer MENTION und COMMENT_REPLY

**API Endpoints** (`app/api/v1/comments.py`):
- `GET/POST /{doc_id}/comments/field/{field_name}` - Feld-Kommentare (Zeile 757)
- `GET /{doc_id}/comments/statistics` - Kommentar-Statistiken (Zeile 878)

**Schemas** (`app/db/schemas.py`):
- `CommentStatistics` (Zeile 7541) - Statistik-Response
- `fieldReference` (Zeile 7483) - Optional in CommentCreate
- `companyId` (Zeilen 7522, 7849, 8014) - In Responses

**Test-Ergebnisse**:
- CommentService: **30 passed**
- Comments API: **49 passed, 7 skipped** (dokumentierte Mock-Komplexitaet)
- Alle Collaboration: **105 passed** (28 DocumentTask + 21 Digest + 26 Escalation + 30 Comment)

**Collaboration Suite Komplett**:
| Service | Tests | Status |
|---------|-------|--------|
| DocumentTaskService | 28 | ✅ |
| DigestService | 21 | ✅ |
| EscalationService | 26 | ✅ |
| CommentService | 30 | ✅ |
| **Gesamt** | **105** | ✅ |

---

### Enterprise Niveau Verifiziert - Alle Features Production-Ready

**Status**: ✅ Enterprise Niveau erreicht

**Verifizierung durchgefuehrt**:
- Import Services: 73/73 Tests passed
- RAG Import: `from app.services.unified_search_service import UnifiedSearchService` - OK
- Celery Beat Schedule: IMPORT_BEAT_SCHEDULE vollstaendig integriert (Zeilen 973-1005)
- EmailSenderMatcher: In email_import_service.py integriert (Zeilen 869-969)
- Import Rules: `_apply_import_rules()` implementiert (Zeilen 971-1089)
- Frontend Import UI: Vollstaendig (`frontend/src/features/imports/`)
- Validation UI: Keyboard-Shortcuts + Mobile-Swipe implementiert

**Enterprise Features (100% Complete)**:
| Feature | Backend | Frontend | Celery |
|---------|---------|----------|--------|
| Email Import | ✅ | ✅ | ✅ 15min |
| Folder Import | ✅ | ✅ | ✅ 5min |
| Import Rules | ✅ | ✅ | - |
| Approval Workflows | ✅ | ✅ | ✅ |
| Validation UI | ✅ | ✅ (Swipe+KB) | - |
| Lexware Integration | ✅ | ✅ | ✅ |
| Risk Scoring | ✅ | ✅ | ✅ 02:00 |
| Invoice Tracking | ✅ | ✅ | ✅ |
| Document Chains | ✅ | ✅ | - |
| Slack Integration | ✅ | ✅ | - |
| Shipment Tracking | ✅ | ✅ | ✅ hourly |
| Knowledge Management | ✅ | ✅ | - |
| Report Scheduling | ✅ | ✅ | ✅ 15min |
| Multi-Tenant RLS | ✅ | ✅ | - |

**Validation UI Features**:
- Keyboard Shortcuts: A (Approve), R (Reject), J/K (Nav), Enter (Open), Esc (Clear)
- Mobile Swipe: Rechts = Genehmigen, Links = Ablehnen
- Threshold-basierte Trigger (100px)
- Animierte Feedback-Hintergruende

---

### FIX: Banking/Dunning Tasks in Celery Beat Schedule integriert

**Status**: ✅ Fixed

**Problem**: Die BANKING_BEAT_SCHEDULE aus `banking_tasks.py` war nicht in den Haupt-Beat-Schedule von `celery_app.py` integriert. Die Dunning-Tasks existierten, wurden aber nicht automatisch ausgefuehrt.

**Loesung**: 9 Banking/Dunning Tasks in `celery_app.py` Beat-Schedule integriert:
- `banking-process-dunning-daily` (09:00) - Automatisches Mahnwesen
- `banking-daily-mahnlauf` (09:00) - Täglicher Mahnlauf
- `banking-reactivate-snoozed-tasks` (08:30) - Snoozed Tasks reaktivieren
- `banking-check-expired-mahnstopp` (08:45) - Abgelaufene Mahnstopp pruefen
- `banking-pre-due-reminders-morning` (07:00) - 3-Tage-Erinnerungen
- `banking-skonto-alerts-morning` (07:30) - Skonto-Deadline-Alerts
- `banking-dunning-daily-report` (18:00) - Tagesabschluss-Report
- `banking-update-cash-flow-4h` (alle 4h) - Cash-Flow-Forecasts
- `banking-tan-cleanup-hourly` (stuendlich) - TAN-Cleanup

**Modifizierte Dateien**:
- `app/workers/celery_app.py`: Beat-Schedule + Task-Routes erweitert

---

### Documentation: Email & Folder Import (Phase 4.3)

**Status**: ✅ Completed

**CLAUDE.md Updates**:
- `.claude/CLAUDE.md`: Neue Sektion "Email & Folder Import (NEU: Januar 2026)"
  - Core Services dokumentiert: EmailImportService, FolderImportService, ImportRuleService, EmailSenderMatcherService
  - API Endpoints fuer Email/Folder Configs, Import Rules, Import Logs
  - Celery Tasks (IMPORT_BEAT_SCHEDULE): sync, poll, retry, cleanup
  - Datenmodelle: EmailImportConfig, FolderImportConfig, ImportRule
  - Rule Conditions/Actions Beispiele
  - Security-Hinweise (AES-256-GCM, Path-Traversal, Logging)
- `CLAUDE.md` (Root): Enterprise Features erweitert mit Email & Folder Import Sektion
- Key Services Tabelle: Import Services hinzugefuegt

**API Dokumentation**:
- `.claude/Docs/API/Import-API.md` (NEU): Vollstaendige Import API Dokumentation
  - Email Import Konfigurationen (CRUD, Test, Sync)
  - Folder Import Konfigurationen (CRUD, Start/Stop/Poll)
  - Import Rules (CRUD, Test, Reorder, Schema)
  - Import Logs (List, Detail, Retry, Stats)
  - Celery Tasks Uebersicht
  - Fehler-Codes und Sicherheitshinweise

**Status Email/Folder Import**:
- Backend: 95% Ready (API, Services, Celery Tasks)
- Frontend: Pending (UI Komponenten fehlen)
- Celery Beat Schedule: IMPORT_BEAT_SCHEDULE in `app/workers/tasks/import_tasks.py`

---

### SECURITY: Shipment Tracking Input Validation (Ralph Loop Review)

**Status**: ✅ Fixed and Tested

**Gefundene Sicherheitslücke**:
- **CRITICAL: Tracking-Nummern wurden ohne Validierung in URLs eingefügt**
  - **Problem**: SSRF/Injection-Risiko durch unvalidierte Benutzereingaben (CWE-20)
  - **Problem**: URL-Injection möglich ohne Encoding (CWE-116)
  - **Fix**: `validate_tracking_number()` mit Whitelist-Pattern (alphanumerisch, 6-30 Zeichen)
  - **Fix**: `safe_url_encode()` für alle URL-Parameter

**Betroffene Dateien**:
- `app/services/shipping/carrier_providers.py` - Security-Funktionen + alle 7 Provider
- `tests/unit/services/test_shipping_service.py` - Neue umfassende Test-Suite

**Security-Implementierung**:
```python
TRACKING_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{6,30}$")

def validate_tracking_number(tracking_number: str) -> str:
    """SECURITY: Whitelist-Validierung gegen Injection (CWE-20)."""
    normalized = tracking_number.strip().replace(" ", "").replace("-", "").upper()
    if not TRACKING_NUMBER_PATTERN.match(normalized):
        raise ValueError("Ungueltige Tracking-Nummer")
    return normalized

def safe_url_encode(value: str) -> str:
    """SECURITY: URL-Encoding gegen Injection (CWE-116)."""
    return quote(value, safe="")
```

**Tests (66 neue Assertions)**:
- Input-Validierung: SQL Injection, XSS, CRLF, Path Traversal abgelehnt
- Unicode-Homoglyphen abgelehnt
- Carrier-Erkennung für alle 7 Provider
- Status-Normalisierung
- Pattern-Matching

---

### P3: Slack Integration (NEU)

**Status**: ✅ Production-Ready
**Migration**: 100 (add_slack_integration)

**Backend**:
- **SlackService** (`app/services/slack_service.py`)
  - Webhook und Bot Token Support
  - Rate Limiting mit Sliding Window (30/min default)
  - Block Kit Message Formatting
  - Retry-Logik bei Fehlern
  - Notification-Typen: document_processed, approval_required, workflow_completed, etc.
  - Prioritaetsstufen: low, normal, high, urgent

- **Models** (`app/db/models.py`):
  - `SlackChannel` - Konfigurierte Kanaele mit Notification-Typen
  - `SlackMessageLog` - Nachrichten-Protokoll mit Status-Tracking
  - `SlackUserMapping` - Benutzer-Verknuepfungen fuer DMs

- **API Endpoints** (`app/api/v1/slack.py`):
  - `GET /api/v1/slack/status` - Verbindungs-Status
  - `GET /api/v1/slack/statistics` - Statistiken
  - `POST/GET/PATCH/DELETE /api/v1/slack/channels/*` - Kanal CRUD
  - `GET /api/v1/slack/messages` - Nachrichten-Log
  - `POST /api/v1/slack/test` - Test-Nachricht senden
  - `POST/GET/DELETE /api/v1/slack/user-mapping` - Benutzer-Verknuepfung
  - `GET /api/v1/slack/notification-types` - Verfuegbare Typen

**Frontend** (`frontend/src/features/slack/`):
- **Types** (`types/index.ts`)
  - SlackChannel, SlackMessageLog, SlackUserMapping, SlackConnectionStatus, etc.
- **API** (`api/slack-api.ts`)
  - Vollstaendige API-Client-Funktionen
- **Hooks** (`hooks/use-slack-queries.ts`)
  - TanStack Query Hooks: useSlackStatus, useSlackChannels, useSendTestMessage, etc.
- **Components**:
  - `SlackSettingsPage` - Admin-Seite mit Status, Kanaelen, Nachrichten, Benutzern
  - `SlackChannelDialog` - Kanal erstellen/bearbeiten
  - `SlackTestDialog` - Test-Nachricht senden
- **Route**: `/admin/slack` mit Sidebar-Navigation (MessageCircle Icon)

**Konfiguration** (`app/core/config.py`):
```python
SLACK_WEBHOOK_URL: Optional[SecretStr]  # Incoming Webhook URL
SLACK_BOT_TOKEN: Optional[SecretStr]    # Bot OAuth Token (xoxb-...)
SLACK_DEFAULT_CHANNEL: str              # Standard-Kanal
SLACK_ENABLED: bool                     # Integration aktiviert
SLACK_RATE_LIMIT_PER_MINUTE: int        # Rate Limit (default 30)
```

**Features**:
- Multi-Tenant Support (company_id auf Kanaelen)
- Konfigurations-UI fuer Kanaele und Benachrichtigungstypen
- Test-Nachrichten zum Pruefen der Integration
- Nachrichten-Protokoll mit Status-Tracking
- Benutzer-Verknuepfungen fuer Direktnachrichten
- Quiet Hours Support fuer Benutzer

---

### CRITICAL Security Fix: DocumentChainService Multi-Tenant Isolation

**Status**: ✅ Fixed and Tested (27/27 Tests Pass)

**Gefundene Sicherheitslücken**:

1. **CRITICAL: `get_chain_discrepancies()` fehlte `company_id` Parameter**
   - **Problem**: Benutzer konnten Discrepancies anderer Firmen sehen
   - **Fix**: `company_id` Parameter hinzugefügt + Filter in Query

2. **CRITICAL: `resolve_discrepancy()` fehlte `company_id` Check**
   - **Problem**: Benutzer konnten Discrepancies anderer Firmen auflösen
   - **Fix**: `company_id` Check via `scalar_one_or_none()` + Security-Guard

3. **CRITICAL: API Endpoints gaben `company_id` nicht weiter**
   - **Problem**: Service hatte Security, aber API nutzte sie nicht
   - **Fix**: Beide Endpoints extrahieren `company_id` aus `current_user`

4. **LOW: `Dict[str, Any]` Type-Safety Verletzung**
   - **Problem**: Verstößt gegen Critical Rule #4 (keine `Any` Types)
   - **Fix**: `DiscrepancyData` TypedDict mit korrekten Typen erstellt

**Betroffene Dateien**:
- `app/services/document_chain_service.py` - Security-Fixes
- `app/api/v1/document_chains.py` - company_id + Response-Feldnamen
- `tests/unit/services/test_document_chain_service.py` - Angepasste Tests

**API Response-Felder korrigiert**:
- `source_value` → `expected_value`
- `target_value` → `actual_value`
- `resolved` → `is_resolved`
- `detected_at` → `created_at`

---

### P3: Automatische Berichte (Report Scheduling)

**Status**: ✅ Production-Ready

**Backend (bereits vorhanden)**:
- **ReportSchedulerService** (`app/services/reports/report_scheduler_service.py`)
  - Cron-basierte Zeitplanung mit croniter
  - Schedule-Presets (taeglich, woechentlich, monatlich, quartalsweise)
  - Execution-Tracking und Status-Updates
  - Cleanup fuer alte Executions

- **Celery Tasks** (`app/workers/tasks/report_tasks.py`)
  - `reports.execute_scheduled_reports` - Alle 15 Minuten
  - `reports.generate_async` - Asynchrone Report-Generierung
  - `reports.send_email` - E-Mail-Versand mit Attachments
  - `reports.cleanup_old_executions` - Taeglich 03:00
  - `reports.cleanup_expired_downloads` - Stuendlich

**Frontend (NEU)**:
- **ScheduleConfig Component** (`frontend/src/features/reports/components/ScheduleConfig.tsx`)
  - Zeitplan aktivieren/deaktivieren
  - Preset-Auswahl (Taeglich 08:00, Woechentlich Montag, Monatlich, etc.)
  - Benutzerdefinierter Cron-Ausdruck
  - Zeitzone-Auswahl (Europe/Berlin, Vienna, Zurich, UTC)
  - Export-Format-Auswahl (Excel, PDF, CSV, JSON)
  - E-Mail-Empfaenger-Verwaltung (Add/Remove)
  - Status-Anzeige (letzte/naechste Ausfuehrung)

- **ReportBuilder Integration**
  - Neuer "Zeitplan" Tab im Report Builder
  - 6-Tab Layout: Basics, Spalten, Filter, Charts, Zeitplan, Vorschau

- **Route**: `/berichte` mit Sidebar-Navigation (BarChart3 Icon)

**Features**:
- Automatische Report-Ausfuehrung nach Cron-Schedule
- E-Mail-Versand an mehrere Empfaenger
- Multiple Export-Formate (Excel, PDF, CSV, JSON)
- Execution-Historie mit Download-Links (7 Tage gueltig)
- Automatisches Cleanup alter Reports

---

### P3: Knowledge Management (Wissensmanagement)

**Status**: ✅ Production-Ready
**Migration**: 099 (add_knowledge_management)

**Datenbank-Tabellen**:
- `knowledge_notes` - Wiki-artige Notizen mit Markdown-Support
- `knowledge_checklists` - Checklisten-Verwaltung
- `knowledge_checklist_items` - Einzelne Checklist-Eintraege
- `knowledge_links` - Knowledge Graph Verknuepfungen
- `knowledge_tags` - Tag-Kategorisierung

**Backend**:
- **Models** (`app/db/models.py`):
  - `KnowledgeNote` - Notizen mit Typ (general, procedure, faq, template, meeting_notes, decision)
  - `KnowledgeChecklist` + `KnowledgeChecklistItem` - Checklisten mit Items
  - `KnowledgeLink` - Polymorphe Verknuepfungen (note ↔ document ↔ entity ↔ checklist)
  - `KnowledgeTag` - Tags mit Farbe und Usage-Count
  - Enums: `NoteType`, `ContentFormat`, `KnowledgeLinkType`, `LinkableType`

- **API Endpoints** (`app/api/v1/knowledge.py`):
  - `POST/GET/PATCH/DELETE /api/v1/knowledge/notes/*` - Notizen CRUD
  - `POST/GET/PATCH/DELETE /api/v1/knowledge/checklists/*` - Checklisten CRUD
  - `POST/GET/PATCH/DELETE /api/v1/knowledge/checklists/{id}/items/*` - Items CRUD
  - `POST/GET/DELETE /api/v1/knowledge/links/*` - Knowledge Links
  - `POST/GET/PATCH/DELETE /api/v1/knowledge/tags/*` - Tags

**Frontend** (`frontend/src/features/knowledge/`):
- **Types** (`types/knowledge-types.ts`)
  - Vollstaendige TypeScript-Interfaces fuer alle Entitaeten
  - `NOTE_TYPE_LABELS`, `LINK_TYPE_LABELS`, `LINKABLE_TYPE_LABELS` Maps
- **API** (`api/knowledge-api.ts`)
  - TanStack Query Hooks: `useNotes`, `useNote`, `useCreateNote`, etc.
  - `useChecklists`, `useChecklist`, `useUpdateChecklistItem`, etc.
  - `useTags`, `useCreateTag`, etc.
- **Components**:
  - `NoteCard` - Notiz-Karte mit Typ-Icons und Tags
  - `NoteFormDialog` - Erstellen/Bearbeiten mit Tags und Optionen
  - `NoteDetailSheet` - Detail-Ansicht mit Verknuepfungen
  - `ChecklistCard` - Checkliste mit Progress-Bar und Item-Toggle
  - `ChecklistFormDialog` - Erstellen/Bearbeiten mit Items
  - `TagBadge` - Tag mit Farbe
- **Page** (`pages/KnowledgePage.tsx`)
  - Tabs: Notizen / Checklisten
  - Filter: Suche, Typ, Angepinnte
  - Pagination
  - CRUD-Dialoge

- **Route**: `/wissen` mit Sidebar-Navigation

**Features**:
- Wiki-artige Notizen mit Markdown/HTML/Plain Format
- 6 Notiz-Typen: Allgemein, Prozess, FAQ, Vorlage, Besprechungsnotiz, Entscheidung
- Anpinnen und Vorlagen-Funktion
- Tag-basierte Kategorisierung mit Farben
- Checklisten mit Deadline-Support
- Polymorphe Verknuepfungen zu Dokumenten, Entities, Firmen
- Knowledge Graph fuer vernetzte Informationen
- Full-Text-Suche (PostgreSQL tsvector)

---

### P3: Multi-Tenant fuer 20+ Mandanten

**Status**: ✅ Production-Ready
**Migration**: 098 (multi_tenant_enhancements)

**Backend Refactoring**:
- **feat**: `CompanyService` (`app/services/company_service.py`) - NEU
  - Zentraler Service fuer dynamische Firmen-Operationen
  - Ersetzt hardcoded "folie"/"messer" Referenzen
  - `get_all_companies()`, `get_company_by_short_name()`, `resolve_company_identifier()`
  - `get_company_short_names()` - Liste aller aktiven short_names
  - `get_company_display_map()` - short_name -> display_name Mapping
  - `validate_company_presence()` - Validierung von company_presence Arrays
  - `get_default_company()` - Standard-Firma abrufen
  - Legacy-Alias-Support ("spargelmesser" -> "messer")

- **refactor**: `entities.py` API-Endpoints
  - 4+ hardcoded `["folie", "messer"]` durch dynamische Abfragen ersetzt
  - Customer-/Supplier-Listen nutzen jetzt CompanyService
  - Cross-Company-View dynamisch fuer alle Firmen
  - Zusammenfassungs-Statistiken per-company dynamisch

- **refactor**: `EntitySearchService` (`app/services/entity_search_service.py`)
  - `find_in_both_companies()` → `find_in_multiple_companies(min_companies=2)`
  - Dynamische JSONB-Array-Laengen-Abfrage statt hardcoded Firmen
  - Legacy-Alias `find_in_both_companies()` fuer Backwards-Kompatibilitaet

**Migration 098**:
- Unique Index auf `companies.short_name`
- GIN-Index auf `business_entities.company_presence` (JSONB-Array-Suche)
- GIN-Index auf `business_entities.lexware_ids` (JSONB-Key-Lookup)
- Seed-Daten fuer Legacy-Firmen (folie, messer)

**Frontend**:
- **feat**: Company Admin Page (`frontend/src/features/admin/companies/`)
  - `CompanyAdminPage.tsx` - Hauptseite mit CRUD-Operationen
  - `CompanyTable.tsx` - Tabelle mit Actions (Edit, Delete, ManageUsers, SetDefault)
  - `CompanyFormDialog.tsx` - 4-Tab-Formular (Allgemein, Rechtlich, Kontakt, Banking)
  - `CompanyUsersDialog.tsx` - User-Verwaltung mit Rollen und Permissions
  - `companies-admin-api.ts` - TanStack Query Hooks
- **feat**: Route `/admin/firmen` mit Sidebar-Navigation
- **fix**: `CompanyContext.tsx` - API Response Parsing (`items` statt `companies`)
- **feat**: Company Types erweitert (`frontend/src/types/models/company.ts`)
  - Vollstaendiges Company-Interface mit allen Feldern
  - COMPANY_ROLE_LABELS, LEGAL_FORM_OPTIONS, KONTENRAHMEN_OPTIONS

**Architektur**:
- Multi-Tenant-Isolation via Row-Level Security (RLS)
- X-Company-ID Header fuer API-Requests (automatisch via CompanyContext)
- SessionStorage fuer current_company_id
- PostgreSQL `app.current_company_id` Session-Variable

**Skalierung**: Bereit fuer 20+ Mandanten (SaaS-fähig)

---

## 2026-01-16

### P0 Enterprise Features - Frontend UI Komponenten (NEU)

**Skonto-Tracking UI** (`frontend/src/features/invoices/`)
- **feat**: Types erweitert (`invoice-types.ts`)
  - `SkontoInfo`, `SkontoUpdate`, `UpcomingSkontoDeadline` Interfaces
  - `PaymentTransaction`, `PaymentCreate`, `PaymentSummary` Interfaces
  - Extended `InvoiceTrackingResponse` mit Skonto/Teilzahlungs-Feldern
  - UI_LABELS fuer Skonto und Teilzahlungen
- **feat**: API Funktionen (`invoice-api.ts`)
  - `getSkonto()`, `updateSkonto()`, `applySkonto()`
  - `getUpcomingSkontoDeadlines()`
  - `listPayments()`, `addPayment()`, `deletePayment()`
- **feat**: TanStack Query Hooks (`use-invoice-queries.ts`)
  - `useSkonto`, `useUpcomingSkontoDeadlines`
  - `useUpdateSkonto`, `useApplySkonto`
  - `usePayments`, `useAddPayment`, `useDeletePayment`
- **feat**: `SkontoAlertBadge` - Farbcodierte Status-Badges (verfuegbar/ablaufend/abgelaufen/genutzt)
- **feat**: `SkontoDetailPanel` - Vollstaendige Skonto-Verwaltung mit Edit/Apply
- **feat**: `PaymentHistoryPanel` - Teilzahlungs-Verwaltung mit Progress-Balken

**Document Chain UI** (`frontend/src/features/document-chains/`)
- **feat**: Types (`chain-types.ts`)
  - `ChainRelationshipType`, `DocumentTypeInChain`, `DiscrepancyType`
  - `ChainDocument`, `DocumentChainInfo`, `ChainRelationship`
  - `ChainDiscrepancy`, `ChainMatchResult`, `ChainFilter`
  - `CHAIN_UI_LABELS`, `DOCUMENT_TYPE_STYLES`, `DISCREPANCY_SEVERITY_STYLES`
- **feat**: API Service (`chain-api.ts`)
  - `listChains()`, `getChain()`, `createChain()`
  - `linkDocuments()`, `autoMatch()`, `removeLink()`
  - `getDiscrepancies()`, `resolveDiscrepancy()`
  - `getDocumentChain()` - Kette by Document ID
- **feat**: TanStack Query Hooks (`use-chain-queries.ts`)
  - `useChains`, `useChain`, `useDocumentChain`
  - `useAutoMatch`, `useDiscrepancies`
  - `useCreateChain`, `useLinkDocuments`, `useRemoveLink`
  - `useResolveDiscrepancy`, `useChainPage`, `useChainMutations`
- **feat**: `ChainCard` - Karten-Ansicht fuer Auftragsketten
- **feat**: `ChainVisualization` - Visueller Dokumentenfluss (Angebot→Auftrag→Lieferschein→Rechnung)
- **feat**: `DiscrepancyPanel` - Abweichungs-Verwaltung mit Aufloesen-Dialog
- **feat**: `AutoMatchDialog` - Automatisches Dokument-Matching mit Confidence-Scores
- **feat**: `CreateChainDialog` - Neue Kette erstellen mit Dokumentenauswahl
- **feat**: `ChainListPage` - Uebersichtsseite mit Filter/Suche/Statistiken
- **feat**: `ChainDetailPage` - Detailseite mit allen Ketten-Informationen

**Utilities**
- **feat**: `formatDaysUntil()` in `banking/utils/format.ts` - Deutsche Tage-Formatierung

---

### P0 Enterprise Features: Skonto, Teilzahlungen, Auftragsketten (Backend)

**Skonto-Tracking** (Migration 094)
- **feat**: `SkontoService` - Skonto-Berechnung mit Deadline-Tracking
  - Automatische Berechnung von Skonto-Betrag und Ablaufdatum
  - Auto-Detection von Skonto-Bedingungen aus OCR-Text ("2% Skonto 14 Tage")
  - `get_upcoming_skonto_deadlines()` - Alert vor ablaufenden Fristen
  - `apply_skonto()` - Skonto bei Zahlung anwenden
- **feat**: Erweiterte API Endpoints (`/api/v1/invoices/*`)
  - `GET/PATCH /{id}/skonto` - Skonto-Informationen verwalten
  - `POST /{id}/apply-skonto` - Skonto anwenden
  - `GET /skonto/upcoming` - Bevorstehende Fristen abrufen

**Teilzahlungs-Tracking** (Migration 094)
- **feat**: `PartialPaymentService` - Teilzahlungs-Management
  - Mehrere Zahlungen pro Rechnung mit automatischem Status-Update
  - Automatische Berechnung des ausstehenden Betrags
  - Bank-Reconciliation Support (Verknuepfung mit Bank-Transaktionen)
  - Toleranz fuer Rundungsdifferenzen (5 Cent)
- **feat**: `PaymentTransaction` Model - Einzelne Zahlungen tracken
- **feat**: API Endpoints
  - `POST /{id}/payments` - Teilzahlung erfassen
  - `GET /{id}/payments` - Zahlungsuebersicht
  - `DELETE /{id}/payments/{payment_id}` - Zahlung loeschen

**Document Chain Tracking** (Migration 095)
- **feat**: `DocumentChainService` - Auftragsketten verfolgen
  - Workflow: Angebot → Auftrag → Lieferschein → Rechnung
  - Auto-Matching ueber Referenznummer, Kundennummer, Betrag
  - Abweichungserkennung (Betraege, Mengen)
- **feat**: `DocumentChainDiscrepancy` Model - Abweichungen erfassen
- **feat**: API Endpoints (`/api/v1/document-chains/*`)
  - `POST /` - Kette erstellen
  - `GET /` - Ketten auflisten
  - `POST /link` - Dokumente verknuepfen
  - `GET /auto-match/{id}` - Passende Dokumente finden
  - `GET /{id}/discrepancies` - Abweichungen abrufen

**Database Models erweitert**
- `InvoiceTracking`: Skonto-Felder (percentage, days, deadline, amount, used)
- `InvoiceTracking`: Teilzahlungs-Felder (outstanding_amount, is_partial_payment)
- `PaymentTransaction`: Neue Tabelle fuer Einzelzahlungen
- `DocumentChainDiscrepancy`: Neue Tabelle fuer Kettenabweichungen

**Tests**
- `test_skonto_service.py` - 15+ Tests fuer Skonto-Berechnung und Alerts
- `test_partial_payment_service.py` - 20+ Tests fuer Teilzahlungen
- `test_document_chain_service.py` - 25+ Tests fuer Auftragsketten

---

### Critical Bug Fixes and Unit Tests (Commit e3564c23)
- **fix**: `approval_rule_service.py` - decimal.InvalidOperation exception handling
- **fix**: `approval_rule_service.py` - _not_in condition logic (must check before _in)
- **fix**: `approval_rule_service.py` - Removed unused imports (User, and_)
- **fix**: `workflow_execution_service.py` - Column names (user_id→triggered_by_id)
- **fix**: `workflow_execution_service.py` - execution_id→workflow_execution_id
- **fix**: `workflow_execution_service.py` - Added missing trigger_type field
- **fix**: `rule_engine.py` - execute_actions counter (increment after success only)
- **test**: `test_approval_rule_service.py` - 40+ neue Tests für Rule Matching
- **test**: `test_workflow_execution_service.py` - 50+ neue Tests für Execution Lifecycle
- **test**: `test_rule_engine.py` - 30+ neue Tests für Notification Rule Engine
- **fix**: `test_approval_service.py` - datetime.utcnow() deprecation behoben
- **fix**: `test_rule_engine.py` - db.add mock fix (synchronous, not async)
- **verified**: 225 Tests bestanden, Enterprise-Level Compliance

### Entity Risk Scoring System (NEU)
- **feat**: Risk Scoring Service (`risk_scoring_service.py`)
  - Berechnet Risiko-Scores für Geschäftspartner (0-100)
  - Payment Behavior Score (0-100, höher = besser)
  - Faktoren: Zahlungsverzögerung, Ausfallrate, Volumen, Frequenz, Beziehungsdauer
  - Gewichteter Score-Algorithmus mit 5 Faktoren
- **feat**: Celery Tasks für Risk Scoring (`risk_scoring_tasks.py`)
  - `calculate_all_risk_scores_task` - Tägliche Batch-Berechnung (02:00)
  - `calculate_single_risk_score_task` - Nach Invoice-Updates
  - `on_invoice_updated_recalculate` - Event-getriggert
  - `check_high_risk_entities_task` - High-Risk Alert (threshold 75)
  - `generate_risk_statistics_task` - Wöchentliche Statistiken
- **feat**: Invoice Tracking API (`/api/v1/invoices/*`)
  - CRUD Endpoints für Rechnungsverfolgung
  - `mark-paid` - Rechnung als bezahlt markieren
  - `increase-dunning` - Mahnstufe erhöhen (max 4)
  - `statistics/summary` - Aggregierte Statistiken
  - Multi-Tenant RLS Security via Document.owner_id
- **feat**: InvoiceTracking Model (Migration 093)
  - Verknüpft mit Document (FK)
  - Status: open, sent, paid, overdue, dunning, cancelled, partial
  - Mahnstufen 0-4 mit last_dunning_at
  - Teilzahlungen: paid_at, paid_amount
- **security**: PII-Leaks in Logs behoben
  - Entity-Namen aus allen Logs entfernt
  - Entity-Namen aus Fehler-Responses entfernt
  - SECURITY-Kommentare an allen kritischen Stellen
- **fix**: Retry-Strategien für alle Celery Tasks
  - `check_high_risk_entities_task`: max_retries=2, delay=120s
  - `generate_risk_statistics_task`: max_retries=2, delay=180s
- **test**: Comprehensive Test Suites
  - `test_risk_scoring_tasks.py` - Task Configuration, Security, Functional
  - `test_invoices_api.py` - API Endpoints, Multi-Tenant, Edge Cases

## 2026-01-11

### Enterprise Document Upload Workflow (NEU)
- **feat**: OCR-Review Upload Flow mit Temp Storage
  - **TempFileStorageService** (`temp_file_storage.py`): Redis-basierte temporäre Datei-Speicherung (1h TTL, max 50MB)
  - **Upload Flow**: 1) OCR/process → temp storage, 2) User review im Modal, 3) upload-complete → MinIO + DB
  - **TTL Extension**: Automatische Verlängerung alle 20min während Review-Modal offen ist
  - **Frontend Hook** (`use-document-upload.ts`): Orchestriert Upload → OCR → Review → Save
  - **DocumentUploadDialog**: Dropzone, OCR-Backend-Auswahl, GPU-Status-Anzeige
  - **OCRReviewModal**: Split-View mit PDF-Preview + Metadaten-Editor, Rename-Vorschlag
  - **Schemas**: `UploadCompleteRequest`, `UploadCompleteResponse` für finales Speichern
  - **API Endpoints**: `/api/v1/ocr/process`, `/api/v1/documents/upload-complete`, `/api/v1/temp-files/{id}/extend-ttl`

### Documentation
- **refactor**: Modularized CLAUDE.md structure
  - Extracted Frontend Patterns to `.claude/Docs/Frontend/Patterns.md` (312 lines)
  - Extracted UI Components to `.claude/Docs/Frontend/Components.md` (96 lines)
  - Reduced CLAUDE.md from 43KB to 11.9KB (363 lines)
  - Reduced RECENT_CHANGES.md to 1.8KB (44 lines)
  - Enhanced memory-updater plugin with routing to Docs/ files

### Frontend
- **refactor**: Ablage API - Centralized HTTP Client Migration
  - Replaced raw `fetch()` calls with `apiClient` from `@/lib/api/client`
  - Migrated endpoints: `fetchEntityName`, `fetchFolderName`, `fetchEntityFolders`, `fetchFolderDocuments`
  - Added pagination support: `fetchCustomersForFrontend`, `fetchSuppliersForFrontend`
  - New types: `PaginatedEntityResponse`, `EntityListFilter`, `SupplierListFilter`
  - Sorting support: `CustomerSortField` (name, customer_number, last_activity)
  - Sorting support: `SupplierSortField` (name, last_activity - NO supplier number)
  - Benefits: Centralized error handling, auth headers, type safety
- **security**: Document Upload Authentication & CSRF Protection (ablage-api.ts)
  - Added `xhr.withCredentials = true` to `uploadDocument()` for session cookies
  - Implemented CSRF token reader (`getCsrfToken()`) for Double-Submit-Cookie pattern
  - Sends `X-CSRF-Token` header with file uploads for CSRF protection
  - Added JWT Bearer token from sessionStorage (`Authorization` header) for XHR uploads
  - Completes authentication fix pattern from commit 25542547

### Infrastructure
- **feat**: Independent Frontend Health Check (nginx.conf)
  - Added dedicated `/health` endpoint for Nginx-native health checks
  - Returns JSON: `{"status":"gesund","service":"frontend","nginx":"running"}`
  - Docker can verify frontend container health independently of backend
  - Keeps existing `/api/health` proxy for deep backend diagnostics

### Backend
- **feat**: GPU Status API Endpoint (`/api/v1/health/gpu`)
  - Returns GPU availability for upload dialog
  - Includes VRAM stats (total, used, free, utilization %)
  - Graceful fallback when CUDA/PyTorch unavailable
- **infra**: Docker GPU Allocation for Backend
  - Backend now gets 1 GPU for health checks
  - Enables `/health/gpu` endpoint to access CUDA stats
  - Worker still primary GPU user for OCR tasks
- **feat**: Expense Reports Soft Delete (Migration 091)
  - Added `deleted_at`, `deleted_by_id` columns to `expense_reports`
  - FK constraint to `users` table with `SET NULL` on delete
  - Partial index for non-deleted records
- **fix**: JSONB query helpers in `ablage_service.py`
  - `jsonb_text()`, `jsonb_numeric()`, `jsonb_exists()` für sichere JSONB-Zugriffe
  - Behebt 500-Fehler auf `/aggregations` Endpoint
- **security**: SQL Injection Prevention für JSONB-Queries (CWE-89)
  - Whitelist für JSONB column/key names (`_ALLOWED_JSONB_COLUMNS`, `_ALLOWED_JSONB_KEYS`)
  - Regex pattern validation (`_SAFE_IDENTIFIER_PATTERN`)
  - Validierung in `jsonb_text()`, `jsonb_numeric()` helpers
- **security**: HTTP Response Splitting Prevention (CWE-113)

### Frontend
- **refactor**: Ablage Types Re-exports
  - Re-export upload types from `./types/ablage-types.ts` in `types.ts`
  - Consolidated import paths for `UploadFile`, `UploadStatus`, `UploadRequest`, `UploadResponse`, `OCRBackend`
  - Utilities: `formatFileSize`, `getStatusColor`, `getStatusLabel`
- **refactor**: CategoryDocumentList UI Responsibilities Cleanup
  - QuickActionsBar: NUR Upload + Export (keine Bulk-Aktionen mehr)
  - BulkActionsToolbar: EINZIGE Quelle für Bulk-Aktionen (Move, Tags, Delete, MarkAsPaid)
  - CategoryTitle: Upload-Button entfernt (jetzt in QuickActionsBar)
  - Conditional Rendering: Aggregations + Filters nur wenn `hasDocuments = true`
  - DocumentsEmptyState: Grosser Upload-CTA wenn keine Dokumente
  - ProactiveInsightsBanner: `onMarkAsPaid` entfernt (in BulkActionsToolbar)
  - DocumentUploadDialog: Modaler Upload statt MoveFolderDialog/TagsEditDialog
- **refactor**: Ablage UI Components Cleanup
  - BulkActionsToolbar: Fixed bottom toolbar mit Bulk-Aktionen
  - QuickActionsBar: Primäre Aktionen (Upload, Export, Mahnung)
  - DocumentUploadDialog: Kategorie-Info, GPU-Status, OCR-Backend
  - Exported alle Smart Features in `index.ts`
- **feat**: CategoryDocumentList Komponenten-Architektur
  - ProactiveInsightsBanner (KI-Insights ganz oben)
  - CategoryBreadcrumb (Navigation-Pfad)
  - CategoryTitle (Seitentitel mit Back-Button)
  - QuickActionsBar (Primäre + Kontext-Aktionen)
  - InvoiceTrackingBanner (Zahlungsstatus bei Rechnungen)
  - CategoryAggregations (Summen-Karten)
  - DocumentFilterBar + DocumentsTable
  - BulkActionsToolbar (fixiert unten)
- **feat**: Breadcrumb-Komponenten getrennt
  - `CategoryBreadcrumb` für Navigation-Pfad
  - `CategoryTitle` für Titel + Actions
  - Konsistentes Styling über alle Ablage-Routen
- **feat**: TransactionTimeline (Vorgänge-Ansicht)
- **refactor**: Nested Routes für Vorgänge (`$folderId/vorgaenge`)

## 2026-01-10

### Backend
- **feat**: Druckdaten-Kategorie für Spargelmesser-Kunden
- **fix**: Entity displayName Konstruktion (Kundennr_Matchcode)
- **feat**: Supplier Sorting + Pagination API
- **fix**: FastAPI Route Ordering (static before dynamic)

### Frontend
- **feat**: Ordner-spezifische Kategorien (Messer vs Folie)
- **feat**: Auto-Navigation bei Single-Folder Entities
- **perf**: Infinite Scroll für Kunden/Lieferanten (100 Items/Page)
- **fix**: German Umlauts (139 Dateien korrigiert)
