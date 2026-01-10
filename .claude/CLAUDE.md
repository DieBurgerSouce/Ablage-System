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
