# Ablage-System: Enterprise Document Processing Platform

<!-- AUTO-MANAGED: project-header -->
**Status**: 🟡 Substanziell gehärtet, noch NICHT Full Production-Ready (Welle-1-Exploration 2026-06-11). Die historischen Blocker **B1–B4 sind behoben bzw. bewusst gescoped** (B2: PSD2-OAuth2-Token outscoped, BaFin); verbleibend 12× P1 (u. a. Secrets-Rotation, Schemathesis-5xx-Triage, `build:strict` rot). _Frühere Angaben „4 offene Blocker" (2026-06-03) und „Production-Ready (E2E Tests 2026-01-10)" sind überholt._ Details: `.claude/reviews/2026-06-11/WAVE1_EXPLORE_REGISTER.md`, `.claude/memory/KNOWN_ISSUES.md`
**Version**: 1.2
**Philosophy**: Feinpoliert und durchdacht
**Deployment**: On-premises, no cloud dependencies
<!-- /AUTO-MANAGED: project-header -->

> **Schnellreferenz**: Siehe `CLAUDE.md` im Root-Verzeichnis (Disambiguation: Root-`CLAUDE.md` = Claude-Flow-/Tooling-Konfiguration, DIESE Datei = fachliche Projekt-Referenz)
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
| **Lexware Integration** | `.claude/Docs/Integrations/Lexware.md` |
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
| Features | Entity Risk Scoring | `.claude/Docs/Features/Entity-Risk-Scoring.md` |
| | Skonto-Tracking | `.claude/Docs/Features/Skonto-Tracking.md` |
| | Document Lineage | `.claude/Docs/Features/Document-Lineage.md` |
| | Document Chains | `.claude/Docs/Features/Document-Chains.md` |
| | Email & Folder Import | `.claude/Docs/Features/Email-Folder-Import.md` |
| | OCR Self-Learning | `.claude/Docs/Features/OCR-Self-Learning.md` |
| | MLOps Pipeline | `.claude/Docs/Features/MLOps-Pipeline.md` |
| | Alert Center | `.claude/Docs/Features/Alert-Center.md` |
| | **Multi-Tenancy Security** | `.claude/Docs/Features/Multi-Tenancy-Security.md` |
| Integrations | DATEV Connect | `.claude/Docs/Integrations/DATEV-Connect.md` |
| | Lexware | `.claude/Docs/Integrations/Lexware.md` |
| | Slack | `.claude/Docs/Integrations/Slack.md` |
| | Shipment Tracking | `.claude/Docs/Integrations/ShipmentTracking.md` |

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
|  Celery Workers  |  Redis (:6380)  |  PostgreSQL (:5434)    |
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

## Feature & Integration Reference

> Detaillierte Dokumentation zu jedem Feature in `.claude/Docs/Features/` und `.claude/Docs/Integrations/`
>
> ⚠️ **Status = Selbsteinschätzung**, nicht End-to-End-verifiziert. Ehrlicher Gesamtstand inkl. Caveats: `.claude/reviews/2026-06-11/WAVE1_EXPLORE_REGISTER.md` (z. B. W1-011, W1-031).

| Feature | Status | Migration | Core Service | Docs |
|---------|--------|-----------|--------------|------|
| DATEV Connect | Production-Ready | 145 | `datev/connect/datev_connector.py` | `.claude/Docs/Integrations/DATEV-Connect.md` |
| Lexware Import | Production-Ready | 089, 090 | `lexware_import_service.py` | `.claude/Docs/Integrations/Lexware.md` |
| Entity Risk Scoring | 🟡 Scoring-Kern ready; **externe Quellen Stub/Mock** (NorthData/Schufa-B2B/Creditreform liefern None, Bundesanzeiger default Mock, Handelsregister default disabled — W1-011) | 092, 093 | `risk_scoring_service.py` | `.claude/Docs/Features/Entity-Risk-Scoring.md` |
| Skonto-Tracking | Production-Ready | 094 | `banking/skonto_service.py` | `.claude/Docs/Features/Skonto-Tracking.md` |
| Document Lineage | Production-Ready | 147 | `lineage/document_lineage_service.py` | `.claude/Docs/Features/Document-Lineage.md` |
| Document Chains | Production-Ready | 095 | `document_chain_service.py` | `.claude/Docs/Features/Document-Chains.md` |
| Slack | Production-Ready | 100 | `slack_service.py` | `.claude/Docs/Integrations/Slack.md` |
| Shipment Tracking | Production-Ready | 100 | `shipping/carrier_service.py` | `.claude/Docs/Integrations/ShipmentTracking.md` |
| Email & Folder Import | Backend Ready 95% | via Beat | `imports/email_import_service.py` | `.claude/Docs/Features/Email-Folder-Import.md` |
| OCR Self-Learning | Production-Ready | JSONB | `ocr/self_learning_service.py` | `.claude/Docs/Features/OCR-Self-Learning.md` |
| MLOps Pipeline | Production-Ready | JSONB | `mlops/model_registry.py` | `.claude/Docs/Features/MLOps-Pipeline.md` |
| Alert Center | Production-Ready | 117 | `alert_center_service.py` | `.claude/Docs/Features/Alert-Center.md` |

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

## TEAM WORKFLOW PROTOCOL

When `[TEAM_WORKFLOW_ACTIVE]` appears in context (injected by team_router_hook), follow this protocol:

### Step 1: Classify

Run the team executor to get detailed classification:
```bash
python .claude/helpers/team_executor.py classify --task "<full task description>"
```

Die Ausgabe enthaelt eine `workflow_id`. Diese MUSS bei allen Folgebefehlen mitgegeben werden:
```json
{ "workflow_id": "abcd1234", ... }
```

### Step 2: Phase Loop

For each phase N (1 through total_phases):

**a) Get phase instructions:**
```bash
python .claude/helpers/team_executor.py phase --number N --workflow-id <workflow_id>
```

**b) Spawn agent(s):**
- SEQUENTIAL phase: Use `Task(prompt=..., subagent_type=..., model=...)`
- PARALLEL phase: Spawn ALL agents in ONE message with `run_in_background: true`

**c) Save result when agent(s) complete:**
```bash
python .claude/helpers/team_executor.py save-result --phase N --result "<output>" --workflow-id <workflow_id>
# For parallel phases, save each agent separately:
python .claude/helpers/team_executor.py save-result --phase N --agent coder_a --result "<output>" --workflow-id <workflow_id>
python .claude/helpers/team_executor.py save-result --phase N --agent coder_b --result "<output>" --workflow-id <workflow_id>
```

**d) Run quality gate (if phase has one):**
```bash
python .claude/helpers/team_executor.py gate --name gate_X_name --phase N --workflow-id <workflow_id>
```
- PASSED: proceed to phase N+1
- FAILED: fix issues and re-run the phase (see Gate Failure Recovery below)
- WARNING: proceed but note the warnings

**Gate Failure Recovery:**
When a gate returns FAILED:
1. Read the BLOCK findings from the gate output
2. Spawn the phase agent AGAIN with an adjusted prompt:
   - Include the original task description
   - Add: "KORREKTUR ERFORDERLICH: [paste gate BLOCK findings here]"
3. Save the new result (overwrites the old one):
   `python .claude/helpers/team_executor.py save-result --phase N --result "<new_result>" --workflow-id <workflow_id>`
4. Re-run the gate
5. After 2 failed attempts: Inform the user with a summary of the
   gate findings and ask for manual intervention

### Step 3: Phase 6 Integration (Special)

For templates with `requires_shared_file_integration`:
```bash
python .claude/helpers/team_executor.py integrate --phase 3 --workflow-id <workflow_id>
```
This merges parallel coder manifests and returns concrete append-only instructions for bottleneck files.

### Step 4: Complete
```bash
python .claude/helpers/team_executor.py complete --workflow-id <workflow_id>
```

### Critical Rules

- NEVER edit bottleneck files (main.py, models.py, celery_app.py, tasks/__init__.py) outside Phase 6
- Parallel agents MUST stay in their assigned zones
- Satellite models go in `app/db/models_{feature}.py`, NOT in models.py
- Phase 6 integrator does ONLY append operations on shared files
- Quality gates MUST pass before proceeding (BLOCK findings = re-run)

### Team Templates

| Trigger | Team | Phases | Agents |
|---------|------|--------|--------|
| C1 x M1 | No Team (Haiku) | 1 | 1 |
| C1 x M2 | No Team (Sonnet) | 1 | 1 |
| C2 x M1 | Feature Small | 3 | 3 |
| C2 x M2/M3 | Feature Standard | 6 | 6 |
| C3 x M2/M3 | Feature Full | 6 | 6+ |
| C4 | Refactor | 6 | 6 |
| Security keyword | Security Audit | 4 | 5 |
| Review keyword | Review | 1 | 3 (parallel) |

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

## ROADMAP TRACKING PROTOCOL (Cross-Instance)

**Planfile**: `.claude/plans/breezy-napping-hare.md`

### PFLICHT fuer JEDE Claude-Instanz:

1. **VOR Arbeitsbeginn**: Plan lesen, pruefen welche Features/Sub-Features bereits als DONE markiert sind
2. **NACH Abschluss eines Features/Sub-Features**: Im Plan den Status updaten:
   - `[ ]` -> `[x]` fuer abgeschlossene Items
   - Datum + kurze Notiz anhaengen: `[x] Smart Inbox Frontend (2026-03-10, Tests passing)`
3. **BEI TEILARBEIT**: Notiz hinterlassen was gemacht wurde und was noch fehlt
4. **NIEMALS** ein bereits als `[x]` markiertes Feature nochmal anfassen (ausser Bug-Fix)

### Status-Format im Plan:
- `[ ]` = Noch nicht begonnen
- `[~]` = In Arbeit (Instanz hat angefangen aber nicht fertig)
- `[x]` = DONE (Enterprise-Level abgeschlossen, Tests passing)
- `[!]` = Blockiert (mit Erklaerung warum)

---

**Version**: 1.2
**Last Updated**: 2026-06-11
