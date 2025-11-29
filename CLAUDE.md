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

## Referenzen

- Detaillierte Docs: `.claude/CLAUDE.md`
- API Dokumentation: `.claude/Docs/`
- Slash Commands: `.claude/commands/`
