# Ablage-System OCR - Claude Code Schnellreferenz

> **Detaillierte Dokumentation**: `.claude/CLAUDE.md` (2000+ Zeilen)
> **Letzte Aktualisierung**: 2026-01-10

---

## Projekt-Status

| Feld | Wert |
|------|------|
| **Status** | ✅ Production-Ready (E2E Bugs gefixt 2026-01-10) |
| **Hardware** | RTX 4080 16GB VRAM |
| **Sprache** | Deutsch-First (100% Umlaut-Genauigkeit) |
| **Philosophie** | "Feinpoliert und durchdacht" |

### ✅ E2E BUGS GEFIXT (2026-01-10)

| Bug | Problem | Status |
|-----|---------|--------|
| BUG-001 | Tunes & Kontext Edit Modal | ✅ Gefixt |
| BUG-002 | OCR Training Ground Truth Tab | ✅ Gefixt (SelectItem value) |
| BUG-003 | OCR Review Permissions | ✅ Gefixt (DEBUG=true) |
| Settings | Falsch als Placeholder markiert | ✅ War bereits implementiert (Modal) |

**E2E Report**: `tests/e2e/E2E_TEST_FINDINGS_2026-01-10.md`
**Modul-Score**: 22/22 working (100%)

---

## `.claude/` Verzeichnis - NUTZEN!

```
.claude/
├── CLAUDE.md              # Detaillierte Dokumentation
├── commands/              # Slash Commands
├── hooks/                 # Pre/Post Hooks
├── agents/                # Subagents (plan-breakdown)
└── Docs/                  # Themen-Dokumentation
```

### Slash Commands

| Situation | Command |
|-----------|---------|
| System prüfen | `/check-system` |
| Deutsche Texte | `/validate-german` |
| Dokument verarbeiten | `/process-doc <pfad>` |
| GPU-Probleme | `/debug-gpu` |
| OCR-Qualität | `/ocr-benchmark` |
| Tests ausführen | `/quick-test` |
| Code reviewen | `/review-pr` |
| **WebApp testen** | **`/test-webapp`** |

### Verfügbare Skills

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

| Backend | VRAM | GPU | Stärken |
|---------|------|-----|---------|
| DeepSeek-Janus-Pro | 12GB | ✓ | Beste Umlaut-Genauigkeit, Fraktur |
| GOT-OCR 2.0 | 10GB | - | Tabellen, Formeln, schnell |
| Surya + Docling | 0GB | - | CPU-Fallback, Layout |
| Surya GPU | 4GB | ✓ | Schnelle GPU-Variante |

---

## Kritische Regeln

1. **Deutsche Texte**: ALLE Fehlermeldungen auf Deutsch
2. **GPU-Management**: VRAM unter 85% halten (max 13.6GB)
3. **Typ-Annotationen**: Pflicht für alle Python-Funktionen
4. **Sicherheit**: Keine Secrets im Code, keine PII in Logs
5. **Tests**: Müssen vor Commit bestehen
6. **Multi-Model Orchestration**: IMMER befolgen

---

## Multi-Model Orchestration

Bei jedem Prompt erhältst du einen `ORCHESTRATION ROUTING` Kontext. **BEFOLGEN!**

| Routing-Empfehlung | Aktion |
|--------------------|--------|
| `HAIKU` | `Task(subagent_type="haiku-task", model="haiku", ...)` |
| `SONNET` | `Task(subagent_type="sonnet-implementation", model="sonnet", ...)` |
| `OPUS` | Selbst machen |

**MCP Server nutzen:**
- `mcp__orchestration__route_task` - Optimalen Agent
- `mcp__orchestration__list_agents` - 15 Agenten anzeigen

---

## Plan-Breakdown Subagent

**Automatisch delegieren nach ExitPlanMode!**

```
Task(subagent_type="plan-breakdown", prompt="Analyze plan and generate feature specs...")
```

Generiert automatisch Feature-Dateien in `.claude/plans/[name]/`

---

## Monitoring URLs

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3002 (admin/admin123) |
| Prometheus | http://localhost:9090 |
| API Docs | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |

---

## Module-Übersicht

| Modul | Status | Details |
|-------|--------|---------|
| OCR Training | ✓ | `.claude/CLAUDE.md` → OCR Training |
| Privat-Modul | ✓ | Portfolio, KI-Analysen |
| Orchestration | ✓ | Cross-Module, Decision Engine |
| Lexware | ✓ | Import, Entity-Linking |
| Backup | ✓ | PostgreSQL, Redis, MinIO |
| Qdrant A/B | ✓ | Phase 1: 10% Traffic |

---

## Service-Architektur

### Kanonische Services (Document)

| Service | Pfad |
|---------|------|
| GDPR | `document_services/gdpr_service.py` |
| Export | `document_services/export_service.py` |
| Batch | `document_services/batch_service.py` |
| CRUD | `document_services/crud_service.py` |
| Filter | `document_services/filter_service.py` |

### Deprecated Wrapper (Rückwärtskompatibilität)

- `document_gdpr_service.py` → nutze `document_services/gdpr_service.py`
- `document_export_service.py` → nutze `document_services/export_service.py`
- `document_batch_service.py` → nutze `document_services/batch_service.py`

---

## Projektstruktur

```
Ablage_System/
├── CLAUDE.md                 # ← DU BIST HIER (Schnellreferenz)
├── .claude/
│   ├── CLAUDE.md             # Detaillierte Dokumentation
│   ├── commands/             # Slash Commands
│   ├── hooks/                # Pre/Post Hooks
│   └── Docs/                 # Themen-Dokumentation
├── app/
│   ├── main.py               # FastAPI Entry Point
│   ├── agents/ocr/           # OCR Backends
│   ├── api/v1/               # API Endpoints
│   ├── core/                 # Config, Security, Logging
│   ├── db/                   # SQLAlchemy Models
│   ├── services/             # Business Logic
│   └── workers/              # Celery Tasks
├── frontend/                 # React + TypeScript
├── infrastructure/           # Terraform, Ansible, Grafana
├── tests/                    # Unit + Integration
└── docker-compose.yml
```

---

## Wichtige Konfigurationen

| Einstellung | Wert | Grund |
|-------------|------|-------|
| GPU_LOCK_TIMEOUT | 180s | Lange OCR-Tasks |
| LLM MAX_RETRIES | 3 | Ollama-Abbrüche |
| File-IDs | UUID | Race Conditions |

---

## Referenzen

| Thema | Dokument |
|-------|----------|
| Detaillierte Doku | `.claude/CLAUDE.md` |
| API Dokumentation | `.claude/Docs/API/` |
| Architektur | `.claude/Docs/Architecture/` |
| Testing | `.claude/Docs/Testing/` |
| Operations | `.claude/Docs/Operations/` |
| OCR Backends | `.claude/Docs/OCR-Backends/` |
| Qdrant A/B | `.claude/Docs/QDRANT_AB_TESTING_GUIDE.md` |
| Backup API | `.claude/Docs/API/Backup_API.md` |

---

## Bei Änderungen

1. **`.claude/CLAUDE.md`** - Bei Architekturänderungen
2. **`.claude/commands/`** - Bei neuen Workflows
3. **`.claude/hooks/`** - Bei neuen Validierungen
4. **`tests/`** - Immer Tests aktualisieren
