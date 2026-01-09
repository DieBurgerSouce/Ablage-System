# Ablage-System OCR - Claude Code Kontext

## WICHTIG: Entwicklungsstruktur

Dieses Projekt verwendet eine **optimierte Claude Code Entwicklungsstruktur**. Beachte diese Ordner:

### `.claude/` Verzeichnis - IMMER NUTZEN!

```
.claude/
├── CLAUDE.md              # Detaillierte Projektdokumentation (2000+ Zeilen)
├── commands/              # Slash Commands - NUTZE DIESE!
│   ├── check-system.md    # /check-system - Systemgesundheit prüfen
│   ├── validate-german.md # /validate-german - Deutsche Texte validieren
│   ├── process-doc.md     # /process-doc - Dokument verarbeiten
│   ├── debug-gpu.md       # /debug-gpu - GPU-Probleme diagnostizieren
│   ├── ocr-benchmark.md   # /ocr-benchmark - OCR-Qualität testen
│   ├── quick-test.md      # /quick-test - Schnelle Tests ausführen
│   └── ...                # Weitere Commands
├── hooks/                 # Automatische Validierung
│   ├── pre-commit.py      # Pre-Commit: Typen, Sicherheit, Deutsche Texte
│   └── post-ocr-change.py # Nach OCR-Änderungen: Tests, GPU-Validierung
└── Docs/                  # Zusätzliche Dokumentation
```

### Wann welchen Command nutzen:

| Situation | Command |
|-----------|---------|
| System starten/prüfen | `/check-system` |
| Deutsche Texte validieren | `/validate-german` |
| Dokument verarbeiten | `/process-doc <pfad>` |
| GPU-Probleme | `/debug-gpu` |
| OCR-Qualität testen | `/ocr-benchmark` |
| Tests ausführen | `/quick-test` |
| Code reviewen | `/review-pr` |
| **WebApp vollständig testen** | **`/test-webapp`** |

### Verfügbare Skills - AUTOMATISCH NUTZEN!

| Situation | Skill | Aktivierung |
|-----------|-------|-------------|
| Frontend/UI testen, Browser-Tests, E2E-Tests | `webapp-tester-mcp` | `@webapp-tester-mcp` |
| OCR debuggen, Textextraktion prüfen | `ocr-debug` | `@ocr-debug` |
| Deutsche Texte, Umlaute validieren | `german-text` | `@german-text` |
| Docker-Entwicklung | `docker-dev` | `@docker-dev` |

**WICHTIG für Frontend-Testing:**
Wenn der User fragt nach: "teste die App", "UI prüfen", "Frontend testen", "E2E Tests", "Browser-Tests", "Screenshots machen", "wie ein QA-Engineer testen" → **IMMER** den `@webapp-tester-mcp` Skill aktivieren! Dieser nutzt den Playwright MCP Server für echte Browser-Automatisierung.

### AUTOMATISCHER Plan-Breakdown Subagent

**KRITISCH - IMMER AUTOMATISCH DELEGIEREN:**

Der `plan-breakdown` Subagent ist in `.claude/agents/plan-breakdown.md` definiert.

**Wann MUSS Claude automatisch an den Subagent delegieren:**

| Situation | Claude sagt... |
|-----------|----------------|
| **ExitPlanMode wird aufgerufen** | "Ich delegiere an den plan-breakdown Subagent um detaillierte Feature-Specs zu generieren..." |
| User akzeptiert einen Plan | "Use the plan-breakdown subagent to expand this plan into detailed feature specifications" |
| Plan-Datei wurde gerade erstellt | "Der Plan ist fertig. Ich lasse den plan-breakdown Subagent die Details generieren..." |
| User oeffnet ROADMAP*.md | "Use the plan-breakdown subagent to analyze this roadmap" |
| User sagt "expandieren", "details" | "Use the plan-breakdown subagent to break this down" |

**WICHTIGSTER TRIGGER: Nach jedem ExitPlanMode automatisch delegieren!**

**Der Subagent:**
- Ist registriert in `.claude/agents/plan-breakdown.md`
- Hat eigene Tools (Read, Grep, Glob, Edit, Write, AskUserQuestion)
- Bekommt frischen Kontext
- Generiert automatisch Feature-Dateien in `.claude/plans/[name]/`
- Stellt Rueckfragen wenn noetig

**Beispiel-Delegation:**
```
"Use the plan-breakdown subagent to analyze the plan I just created
and generate detailed feature specification files with API specs,
DB schema, implementation tasks, and test scenarios."
```

**WICHTIG:** Der User soll NIEMALS selbst den Subagent triggern muessen! Claude erkennt automatisch wann er sinnvoll ist und delegiert.

---

## Projekt-Übersicht

**Status**: Production-Ready Enterprise Platform
**Hardware**: RTX 4080 16GB VRAM
**Sprache**: Deutsch-First (100% Umlaut-Genauigkeit erforderlich)
**Philosophie**: "Feinpoliert und durchdacht"

### Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Ablage-System OCR                        │
├─────────────────────────────────────────────────────────────┤
│  Frontend (Nginx:80)     │  Grafana (:3000)  │  Prometheus  │
├──────────────────────────┴───────────────────┴──────────────┤
│                    FastAPI Backend (:8000)                  │
├─────────────────────────────────────────────────────────────┤
│  Celery Workers  │  Redis (:6380)  │  PostgreSQL (:5433)    │
├─────────────────────────────────────────────────────────────┤
│  OCR Backends: DeepSeek | GOT-OCR | Surya | Surya-GPU       │
├─────────────────────────────────────────────────────────────┤
│                 GPU: NVIDIA RTX 4080 (16GB)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## WICHTIG: Docker-Only Entwicklung

**Ab sofort wird ausschliesslich mit Docker gearbeitet!**
- KEINE lokalen Dev-Server (`npm run dev`, `uvicorn --reload`)
- ALLE Aenderungen werden via Docker-Container getestet
- Frontend-Aenderungen erfordern `docker-compose build frontend && docker-compose up -d frontend`

## Wichtige Befehle

```bash
# Development starten (IMMER mit Docker!)
docker-compose up -d

# Frontend nach Aenderungen neu bauen
docker-compose build frontend && docker-compose up -d frontend

# Backend nach Aenderungen neu bauen
docker-compose build backend && docker-compose up -d backend

# Alle Container neu bauen
docker-compose build && docker-compose up -d

# Tests ausfuehren (in Docker)
docker-compose exec backend pytest tests/unit/ -v
docker-compose exec backend pytest tests/integration/ -v

# GPU-Status
nvidia-smi
python -c "from app.gpu_manager import GPUManager; print(GPUManager().get_detailed_status())"

# Celery Worker
celery -A app.workers.celery_app worker --loglevel=info --concurrency=1 --pool=solo
```

---

## Projektstruktur

```
Ablage_System/
├── CLAUDE.md                 # <- DU BIST HIER (Schnellreferenz)
├── .claude/
│   ├── CLAUDE.md             # Detaillierte Dokumentation
│   ├── commands/             # Slash Commands
│   └── hooks/                # Pre/Post Hooks
├── app/
│   ├── main.py               # FastAPI Entry Point
│   ├── agents/ocr/           # OCR Backends (DeepSeek, GOT, Surya)
│   ├── api/v1/               # API Endpoints
│   ├── core/                 # Config, Security, Logging
│   ├── db/                   # SQLAlchemy Models
│   ├── services/             # Business Logic
│   └── workers/              # Celery Tasks
├── frontend/                 # Web UI (4 Display-Modi)
├── infrastructure/
│   ├── grafana/              # Monitoring Dashboards
│   ├── prometheus/           # Metriken
│   ├── loki/                 # Log-Aggregation
│   ├── nginx/                # Reverse Proxy
│   └── postgres/             # DB Init
├── tests/
│   ├── unit/                 # Unit Tests
│   └── integration/          # Integration Tests
└── docker-compose.yml        # Container-Orchestrierung
```

---

## OCR Backends

| Backend | VRAM | GPU | Stärken |
|---------|------|-----|---------|
| DeepSeek-Janus-Pro | 12GB | Ja | Beste Umlaut-Genauigkeit, Fraktur, komplexe Layouts |
| GOT-OCR 2.0 | 10GB | Nein* | Tabellen, Formeln, schnell |
| Surya + Docling | 0GB | Nein | CPU-Fallback, Layout-Analyse |
| Surya GPU | 4GB | Ja | Schnelle GPU-Variante |

---

## OCR Training & Validation System

Enterprise-System für Ground-Truth-Management, Backend-Vergleich und Self-Learning.

### Features
- **Backend-Vergleich**: 4 OCR-Engines Side-by-Side mit CER/WER/Umlaut-Metriken
- **Self-Learning**: Automatische Backend-Gewichtung aus User-Korrekturen
- **Stichproben-Workflow**: Stratifizierte Zufallsauswahl zur Qualitätskontrolle
- **Ground-Truth-Management**: Editoren annotieren, Admins verifizieren

### Zugriff
- **Frontend**: `/admin/ocr-training`
- **API**: `/api/v1/training/*`

### Komponenten
```
app/services/
├── ocr_training_service.py      # CRUD, Batches, Stats
├── benchmark_runner_service.py   # OCR Benchmarks
├── feedback_learning_service.py  # Self-Learning
└── training_migration_service.py # SQLite Migration

app/workers/tasks/
└── training_tasks.py            # 7 Celery Tasks

frontend/src/features/ocr-training/
├── components/
│   ├── TrainingDashboard.tsx    # Hauptübersicht
│   ├── BackendComparisonChart.tsx # Recharts Visualisierung
│   ├── SamplesList.tsx          # Ground Truth Tabelle
│   └── BatchesList.tsx          # Stichproben-Batches
└── api/training-api.ts          # TypeScript Client
```

### API Endpoints
```
GET  /api/v1/training/samples           # Samples auflisten
POST /api/v1/training/benchmarks/run    # Benchmarks starten
GET  /api/v1/training/benchmarks/compare # Backend-Vergleich
POST /api/v1/training/corrections       # Korrektur einreichen
GET  /api/v1/training/stats/overview    # Dashboard-Statistiken
GET  /api/v1/training/stats/learned-weights # Gelernte Gewichte
POST /api/v1/training/migration/sqlite  # SQLite migrieren
```

### Celery Tasks (Beat Schedule)
| Task | Zeitplan |
|------|----------|
| generate_daily_stats | Täglich 01:00 |
| process_feedback_queue | Stündlich |
| update_learned_weights | Täglich 02:00 |
| run_scheduled_benchmarks | Sonntag 03:00 |
| generate_training_report | Montag 07:00 |

---

## Privat-Modul: Enterprise Vermögensverwaltung

**Status**: Production-Ready (seit Dezember 2024)
**Features**: KI-gestützte Vermögensanalysen, Portfolio-Tracking, automatische Snapshots

### Übersicht

Das Privat-Modul ermöglicht vollautomatische Vermögensverwaltung mit KI-Integration:

- **Portfolio-Tracking**: Immobilien, Fahrzeuge, Anlagen, Kredite
- **KI-Analysen**: Bewertung, Optimierung, Risikoanalyse
- **Historische Snapshots**: Monatliche Vermögensentwicklung
- **Intelligente Insights**: Automatische Trends und Empfehlungen

### Architektur

```
app/services/privat/
├── ki_prompt_service.py      # KI-Analysen mit LLM Integration
├── portfolio_service.py       # Vermögensübersicht und Snapshots
├── financial_health_service.py # Finanzgesundheits-Analysen
└── templates/privat/          # Jinja2 Prompt-Templates
```

### Portfolio Service

**Klasse**: `PortfolioService`
**Zweck**: Aggregierte Vermögensübersichten und historische Snapshots

#### Features
- **Echtzeit-Vermögensberechnung**: Assets, Liabilities, Net Worth
- **Kennzahlen**: Debt-to-Assets Ratio, Liquidity Ratio
- **Asset Allocation**: Prozentuale Verteilung nach Kategorien
- **Trend-Analyse**: Vergleich mit Vormonat
- **Monatliche Snapshots**: Automatische historische Archivierung

#### Datenmodelle

```python
@dataclass
class AssetSummary:
    total_real_estate: Decimal      # Immobilien
    total_vehicles: Decimal         # Fahrzeuge
    total_investments: Decimal      # Anlagen
    total_cash: Decimal             # Bargeld/Konten
    total_other_assets: Decimal     # Sonstige

@dataclass
class LiabilitySummary:
    total_mortgages: Decimal        # Hypotheken
    total_loans: Decimal            # Kredite
    total_other_liabilities: Decimal # Sonstige

@dataclass
class PortfolioAnalysis:
    assets: AssetSummary
    liabilities: LiabilitySummary
    net_worth: Decimal
    debt_to_assets_ratio: Decimal
    liquidity_ratio: Decimal
    asset_allocation: dict[str, float]
    net_worth_change_absolute: Optional[Decimal]
    net_worth_change_percent: Optional[Decimal]
```

### KI-Prompt Service

**Klasse**: `PrivatKIPromptService` (Thread-safe Singleton)
**Zweck**: Domänenspezifische KI-Analysen mit LLM Integration

#### Features
- **Immobilien-Bewertung**: Marktwert-Schätzung, Mietpotenzial, ROI
- **Fahrzeug-Analyse**: Wertverlust, optimaler Verkaufszeitpunkt
- **Anlage-Beratung**: Risikoprofil, Portfolio-Optimierung, Rebalancing
- **Versicherungs-Check**: Coverage-Gaps, Optimierungspotenzial
- **Finanz-Assistent**: Natürlichsprachliche Q&A

#### Technische Details
- **Template-Engine**: Jinja2 für deutsche Prompts (templates/privat/)
- **LLM-Integration**: Nutzt `LLMService` (Anthropic/Ollama)
- **Caching**: In-Memory Cache (24h TTL) mit Thread-safe RLock, deep-copy Pattern
- **Monitoring**: Prometheus-Metriken für Requests, Duration, Cache-Hits
- **Thread-Safety**: Double-Checked Locking Pattern in `__new__`
- **Testing**: Umfassende Unit-Tests inkl. Thread-Safety und Dataclass-Validation

**Wichtige Implementierungsdetails:**
- Alle Attribute werden in `__new__` initialisiert (nicht in `__init__`)
- Cache gibt Deep-Copy zurück um Mutation zu verhindern
- JSON-Response-Parsing mit Markdown-Block-Entfernung
- SHA256-basierte Cache-Keys für Eindeutigkeit

#### Datenmodelle

```python
@dataclass
class PropertyValueAnalysis:
    property_id: UUID
    estimated_value_eur: float
    confidence_percent: int
    reasoning: str
    market_comparison: str
    value_trend: str  # steigend, stabil, fallend
    rental_potential_eur: Optional[float]
    roi_estimate_percent: Optional[float]

@dataclass
class VehicleDepreciationAnalysis:
    vehicle_id: UUID
    current_value_eur: float
    depreciation_percent: float
    optimal_sell_timeframe: str
    market_demand: str  # hoch, mittel, gering

@dataclass
class InvestmentAdvice:
    space_id: UUID
    risk_profile: str  # konservativ, ausgewogen, wachstumsorientiert
    optimization_suggestions: List[str]
    rebalancing_needed: bool
    diversification_score: int  # 0-100

@dataclass
class InsuranceCheckResult:
    space_id: UUID
    coverage_assessment: str  # ausreichend, verbesserungswuerdig, unzureichend
    identified_gaps: List[str]
    recommendations: List[str]
    cost_optimization_potential_eur: Optional[float]
```

#### Prometheus-Metriken

```python
privat_ki_analysis_requests_total  # Counter: Requests nach Typ + Status
privat_ki_analysis_duration_seconds # Histogram: Dauer der Analysen
privat_ki_cache_hits_total          # Counter: Cache-Hits
privat_ki_cache_misses_total        # Counter: Cache-Misses
```

### Wichtige Patterns

#### Singleton Pattern (Thread-Safe)
```python
class PrivatKIPromptService:
    _instance: Optional["PrivatKIPromptService"] = None
    _class_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "PrivatKIPromptService":
        # Double-checked locking
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)

                    # KRITISCH: Alle Attribute hier initialisieren (nicht in __init__)
                    instance._llm_service = LLMService()
                    instance._jinja_env = Environment(...)
                    instance._cache: Dict[str, Any] = {}
                    instance._cache_lock = threading.RLock()
                    instance._initialized = True

                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        """No-op - Initialisierung erfolgt in __new__."""
        pass
```

**Wichtig:** Der Singleton wird über `get_privat_ki_prompt_service()` Factory-Funktion verwendet.
Unit-Tests validieren Thread-Safety mit 100 parallelen Threads.

#### Caching Strategy
- **In-Memory Cache**: Dict mit Thread-Lock (RLock) für schnellen Zugriff
- **TTL**: 24 Stunden für KI-Analysen (automatische Expiration)
- **Cache-Key**: SHA256 Hash von (analysis_type + entity_id + params)
- **Deep-Copy Pattern**: Cache gibt `copy.deepcopy()` zurück um Mutation zu verhindern
- **Thread-Safety**: Alle Cache-Operationen verwenden `with self._cache_lock`

```python
def _get_from_cache(self, cache_key: str) -> Optional[Any]:
    """WICHTIG: Gibt Deep-Copy zurück um Cache-Mutation zu verhindern."""
    import copy
    with self._cache_lock:
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not expired:
                return copy.deepcopy(entry["data"])  # Kopie!
    return None
```

### API Endpoints

```
GET  /api/v1/privat/spaces/{space_id}/portfolio       # Portfolio-Übersicht
GET  /api/v1/privat/spaces/{space_id}/portfolio/trend # Historischer Trend
POST /api/v1/privat/properties/{id}/analyze           # KI-Immobilien-Analyse
POST /api/v1/privat/vehicles/{id}/analyze             # KI-Fahrzeug-Analyse
POST /api/v1/privat/spaces/{id}/investment-advice     # KI-Anlage-Beratung
POST /api/v1/privat/spaces/{id}/insurance-check       # KI-Versicherungs-Check
POST /api/v1/privat/chat                              # Finanz-Assistent Q&A
```

### Celery Tasks (geplant)

| Task | Zeitplan | Beschreibung |
|------|----------|--------------|
| create_monthly_snapshots | 1. des Monats 01:00 | Portfolio-Snapshots für alle Spaces |
| analyze_portfolio_trends | Täglich 02:00 | Trend-Analysen und Alerts |
| update_ki_cache | Täglich 03:00 | Cache-Warm-up für häufige Analysen |

### Sicherheitshinweise

1. **PII-Schutz**: NIEMALS finanzielle Details in Logs
2. **Cache-Isolation**: User-spezifische Cache-Keys
3. **Input-Validation**: Pydantic-Schemas für alle API-Eingaben
4. **Rate-Limiting**: KI-Analysen auf 10/Stunde pro User begrenzt

---

## Kritische Regeln

1. **Deutsche Texte**: ALLE Fehlermeldungen auf Deutsch
2. **GPU-Management**: VRAM unter 85% halten (max 13.6GB von 16GB)
3. **Typ-Annotationen**: Pflicht für alle Python-Funktionen
4. **Sicherheit**: Keine Secrets im Code, keine PII in Logs
5. **Tests**: Muessen vor Commit bestehen
6. **Multi-Model Orchestration**: IMMER befolgen (siehe unten)

---

## KRITISCH: Multi-Model Orchestration System

Dieses Projekt nutzt ein **automatisches Multi-Model Routing System**. Bei JEDEM User-Prompt erhaeltst du einen `ORCHESTRATION ROUTING` Kontext im system-reminder. **DU MUSST DIESEN BEFOLGEN!**

### Wie es funktioniert

1. **UserPromptSubmit Hook** klassifiziert jeden Prompt automatisch
2. Du erhaeltst einen Kontext wie: `Routing zu: OPUS/SONNET/HAIKU`
3. **Du MUSST entsprechend delegieren** um Kosten zu sparen

### Wann du DELEGIEREN musst

| Routing-Empfehlung | Deine Aktion |
|--------------------|--------------|
| `Routing zu: HAIKU` | `Task(subagent_type="haiku-task", model="haiku", prompt="...")` |
| `Routing zu: SONNET` | `Task(subagent_type="sonnet-implementation", model="sonnet", prompt="...")` |
| `Routing zu: OPUS` | Mache es selbst (keine Delegation noetig) |

### Verfuegbare Spezialisierte Agenten

Nutze den MCP Server fuer intelligentes Routing:

```
mcp__orchestration__route_task  - Gibt optimalen Agent/Model zurueck
mcp__orchestration__list_agents - Zeigt alle 15 Agenten
mcp__orchestration__get_metrics - Zeigt Statistiken
```

**Spezialisierte Agenten (automatisch gewaehlt):**

| Agent | Model | Fuer |
|-------|-------|------|
| `refactoring-expert` | opus | Grosse Refactorings, Migrationen |
| `security-auditor` | opus | Security Reviews, Vulnerabilities |
| `ocr-specialist` | opus | OCR Pipeline, GPU-Optimierung |
| `database-expert` | sonnet | SQLAlchemy, Alembic, Schema |
| `testing-expert` | sonnet | pytest, Coverage, Integration |
| `frontend-expert` | sonnet | React, TypeScript, TanStack |
| `api-designer` | sonnet | REST, OpenAPI, Endpoints |
| `bug-hunter` | sonnet | Debugging, Error Analysis |
| `code-reviewer` | haiku | Style Checks, Linting |
| `doc-writer` | haiku | Docstrings, README |

### Beispiel-Delegation

```python
# Wenn Routing "HAIKU" empfiehlt fuer einfache Aufgabe:
Task(
    subagent_type="doc-writer",
    model="haiku",
    prompt="Schreibe Docstrings fuer die Funktion process_document()"
)

# Wenn Routing "SONNET" empfiehlt fuer Tests:
Task(
    subagent_type="testing-expert",
    model="sonnet",
    prompt="Schreibe Unit-Tests fuer den DocumentService"
)
```

### WICHTIG - Immer beachten!

- **Ignoriere NIEMALS** den Orchestration-Kontext
- **Delegiere IMMER** bei Haiku/Sonnet-Empfehlungen
- **Spare Kosten** durch intelligentes Routing
- **Der Hook laeuft automatisch** - du musst nur die Empfehlung befolgen

---

## Bei Änderungen an diesem Projekt

Wenn du Änderungen machst, aktualisiere auch:

1. **`.claude/CLAUDE.md`** - Bei größeren Architekturänderungen
2. **`.claude/commands/`** - Bei neuen Workflows
3. **`.claude/hooks/`** - Bei neuen Validierungsregeln
4. **`tests/`** - Immer Tests hinzufügen/aktualisieren

---

## Backup & Disaster Recovery

Das System verfuegt ueber ein vollautomatisches Backup-System:

### Komponenten
- **PostgreSQL**: pg_dump mit gzip-Komprimierung
- **Redis**: BGSAVE mit Snapshot
- **MinIO**: mc mirror fuer Object Storage
- **Konfiguration**: tar-Archive

### Automatisierung (Celery Beat)
| Task | Zeitplan |
|------|----------|
| Vollstaendiges Backup | Taeglich 02:30 |
| Retention-Policy | Sonntag 03:00 |
| Remote-Sync | Taeglich 04:00 |
| Metriken-Update | Alle 15 Min |

### API Endpoints
```
GET  /api/v1/backup/status     # Status abfragen
GET  /api/v1/backup/list       # Backups auflisten
POST /api/v1/backup/full       # Vollstaendiges Backup
POST /api/v1/backup/postgres   # PostgreSQL Backup
POST /api/v1/backup/retention  # Alte Backups loeschen
POST /api/v1/backup/sync       # Remote-Synchronisation
```

### Monitoring
- **Grafana Dashboard**: `ablage-backup-monitoring`
- **Prometheus Alerts**: 8 vordefinierte Alerts
- **Metriken**: `/api/v1/metrics/backup`

Dokumentation: `.claude/Docs/API/Backup_API.md`

---

## Monitoring & Debugging

- **Grafana**: http://localhost:3002 (admin/admin123) - Port geändert wegen Konflikt
- **Prometheus**: http://localhost:9090
- **Loki**: Logs via Grafana (kein eigenes UI)
- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001
- **Backup Dashboard**: http://localhost:3002/d/ablage-backup-monitoring

---

## ⚠️ Qdrant A/B Testing - WICHTIG FÜR JEDE SESSION!

### Erwartetes Wachstum (Dezember 2024)
| Zeitraum | Dokumente | Vektoren |
|----------|-----------|----------|
| Aktuell | ~100 | 674 |
| Jahr 1 (2025) | 200.000 | 1-2 Mio |
| Danach | +20-30k/Jahr | +100-200k/Jahr |

### 🎯 SKALIERUNGS-ROADMAP (BEI JEDEM BESUCH PRÜFEN!)

| Phase | Dokumente | Traffic Split | Aktion |
|-------|-----------|---------------|--------|
| 1 ✓ | 0 - 10k | 10% Qdrant | Aktuell - Monitoring |
| 2 | 10k - 50k | 25% → 50% | Performance vergleichen |
| 3 | 50k - 100k | 75% → 100% | pgvector als Backup |
| 4 | 100k+ | 100% Qdrant | Full Rollout |

### Befehle
```bash
# Status prüfen
curl http://localhost:8000/api/v1/metrics/ab-testing

# Traffic erhöhen (z.B. auf 25%)
curl -X POST "http://localhost:8000/api/v1/metrics/ab-testing/traffic-split?new_split=25"
```

**Dokumentation**: `.claude/Docs/QDRANT_AB_TESTING_GUIDE.md`

---

## Service-Architektur (Stand: Dezember 2024)

> **Hinweis**: Die Service-Struktur wurde im Dezember 2024 konsolidiert.

### Document Services (Kanonische Implementierung)

Die modularen Services unter `app/services/document_services/` sind die kanonischen Implementierungen:

| Service | Beschreibung |
|---------|--------------|
| `document_services/gdpr_service.py` | GDPR-konforme Soft-Delete, Wiederherstellung |
| `document_services/export_service.py` | Batch Document Export (JSON/CSV/ZIP/PDF) |
| `document_services/batch_service.py` | Bulk-Operationen fuer Dokumente |
| `document_services/crud_service.py` | Basis-CRUD-Operationen |
| `document_services/filter_service.py` | Query-Building und Filterung |

### Deprecated Wrapper (Rueckwaertskompatibilitaet)

Diese Dateien existieren nur als Wrapper fuer Rueckwaertskompatibilitaet:
- `app/services/document_gdpr_service.py` → Nutze `document_services/gdpr_service.py`
- `app/services/document_export_service.py` → Nutze `document_services/export_service.py`
- `app/services/document_batch_service.py` → Nutze `document_services/batch_service.py`

### Spezialisierte Export-Services

| Service | Zweck |
|---------|-------|
| `export_service.py` | Extracted Data Export (Invoice/Order/Contract → CSV/Excel) |
| `data_export_service.py` | GDPR Art. 20 User Data Portabilitaet |
| `document_services/export_service.py` | Batch Document Export |
| `training_dataset_export_service.py` | OCR Training Dataset Export |

### Batch-Services

| Datei | Beschreibung |
|-------|--------------|
| `document_services/batch_service.py` | Document Bulk-Operationen (kanonisch) |
| `batch_job_service.py` | Batch-Job Tracking und Management |

### GDPR-Services

| Datei | Beschreibung | Status |
|-------|--------------|--------|
| `gdpr_service.py` | User-Level GDPR (Art. 17 Loeschung) | Aktiv |
| `gdpr_compliance_service.py` | Compliance-Checks, Audit-Logs | Aktiv |
| `document_services/gdpr_service.py` | Document Soft-Delete, Restore | Kanonisch |
| `document_gdpr_service.py` | Wrapper → `document_services/gdpr_service.py` | Deprecated |

---

## Wichtige Konfigurationsaenderungen (Dezember 2024)

| Aenderung | Wert | Grund |
|-----------|------|-------|
| GPU_LOCK_TIMEOUT | 60s → 180s | Lange OCR-Tasks liefen in Timeout |
| LLM Retry-Logic | MAX_RETRIES=3 | Ollama-Verbindungsabbrueche abfangen |
| File-IDs (Frontend) | Index → UUID | Race Conditions bei File-Entfernung |

---

## Referenzen

- Detaillierte Docs: `.claude/CLAUDE.md`
- API Dokumentation: `.claude/Docs/`
- Slash Commands: `.claude/commands/`
