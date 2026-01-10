# Ablage-System OCR - Claude Code Schnellreferenz

> **Detaillierte Dokumentation**: `.claude/CLAUDE.md`
> **Memory-Dateien**: `.claude/memory/` (Auto-Managed)
> **Letzte Aktualisierung**: 2026-01-10

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
