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

## Wichtige Befehle

```bash
# Development starten
docker-compose up -d

# API Server (lokal)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Tests ausführen
pytest tests/unit/ -v
pytest tests/integration/ -v

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

## Kritische Regeln

1. **Deutsche Texte**: ALLE Fehlermeldungen auf Deutsch
2. **GPU-Management**: VRAM unter 85% halten (max 13.6GB von 16GB)
3. **Typ-Annotationen**: Pflicht für alle Python-Funktionen
4. **Sicherheit**: Keine Secrets im Code, keine PII in Logs
5. **Tests**: Müssen vor Commit bestehen

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

- **Grafana**: http://localhost:3000 (admin/admin123)
- **Prometheus**: http://localhost:9090
- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001
- **Backup Dashboard**: http://localhost:3000/d/ablage-backup-monitoring

---

## Bekannte Service-Duplikate (Technische Schulden)

> **Hinweis**: Diese Service-Duplikate wurden bei einer Codeanalyse im Dezember 2024 identifiziert.
> Sie sollten bei Gelegenheit konsolidiert werden.

### Export-Services (3x)
| Datei | Beschreibung | Nutzung |
|-------|--------------|---------|
| `app/services/export_service.py` | Allgemeiner Export | Hauptexport-Logik |
| `app/services/data_export_service.py` | Daten-Export | CSV/JSON Export |
| `app/services/document_services/export_service.py` | Dokument-Export | Dokumentspezifischer Export |

**Empfehlung**: Zu einem einheitlichen `ExportService` mit Strategien konsolidieren.

### Batch-Services (2x)
| Datei | Beschreibung |
|-------|--------------|
| `app/services/batch_service.py` | Batch-Verarbeitung |
| `app/services/batch_job_service.py` | Batch-Job-Management |

**Empfehlung**: Pruefen ob Zusammenfuehrung moeglich.

### GDPR-Services (3x)
| Datei | Beschreibung |
|-------|--------------|
| `app/services/gdpr_service.py` | GDPR-Compliance |
| `app/services/gdpr_compliance_service.py` | Compliance-Checks |
| `app/services/document_services/gdpr_service.py` | Dokument-GDPR |

**Empfehlung**: Zu einem einheitlichen `GDPRService` konsolidieren.

### Konsolidierungsstrategie
1. **Phase 1**: Mapping erstellen welche Funktionen wo genutzt werden
2. **Phase 2**: Tests fuer alle Services schreiben
3. **Phase 3**: Schrittweise Migration mit Deprecation-Warnungen
4. **Phase 4**: Alte Services entfernen

---

## Referenzen

- Detaillierte Docs: `.claude/CLAUDE.md`
- API Dokumentation: `.claude/Docs/`
- Slash Commands: `.claude/commands/`
