# Ablage-System OCR - Claude Code Kontext

> **📖 Dokumentations-Hierarchie (P2-32 FIX)**:
> - **Diese Datei** = Schnellreferenz & Einstiegspunkt (~300 Zeilen)
> - **`.claude/CLAUDE.md`** = Vollständige Enterprise-Dokumentation (1200+ Zeilen)
> - Bei Widersprüchen gilt IMMER `.claude/CLAUDE.md` als Source of Truth!

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

## Quality Gates (P2-31 FIX)

Jedes Feature muss diese Quality Gates passieren BEVOR es committed wird:

### 1. Lokale Tests (Entwickler-Maschine)

```bash
# 1. Type Checking
mypy app/

# 2. Linting
ruff check .

# 3. Unit Tests
pytest tests/unit/ -v

# 4. Integration Tests (requires Docker)
docker-compose up -d
pytest tests/integration/ -v

# 5. Code Coverage Check
pytest --cov=app --cov-report=term --cov-fail-under=80
```

**Umgebung**: Lokal oder Docker (je nach Test-Typ)
**Zeitpunkt**: Vor jedem Commit
**Automatisiert**: Via pre-commit Hook (`.claude/hooks/pre-commit.py`)

### 2. Docker Build Verification

```bash
# Frontend Build
docker-compose build frontend

# Backend Build
docker-compose build backend

# Full Stack Test
docker-compose up -d
curl http://localhost:8000/health  # Should return 200
curl http://localhost/  # Should return Frontend
```

**Umgebung**: Docker Compose
**Zeitpunkt**: Vor jedem Push
**Automatisiert**: Nein (manuell)

### 3. GPU Tests (falls OCR-Änderungen)

```bash
# GPU Verfügbarkeit prüfen
nvidia-smi

# GPU Memory Test
python -c "from app.gpu_manager import GPUManager; print(GPUManager().get_detailed_status())"

# OCR Backend Tests (requires GPU)
pytest tests/integration/test_ocr_backends.py -v --gpu
```

**Umgebung**: Lokal mit GPU
**Zeitpunkt**: Bei OCR/GPU-Code-Änderungen
**Automatisiert**: Via post-ocr-change Hook

### 4. Performance Benchmarks

```bash
# API Performance
pytest tests/performance/test_api_latency.py -v

# OCR Performance
pytest tests/performance/test_ocr_throughput.py -v

# Database Query Performance
pytest tests/performance/test_db_queries.py -v
```

**Umgebung**: Docker (Prod-ähnliche Config)
**Zeitpunkt**: Vor Major Releases
**Automatisiert**: Nein (manuell, CI geplant)

### 5. Security Scan

```bash
# Dependency Vulnerabilities
pip-audit

# Code Security Issues
bandit -r app/

# Docker Image Scan
docker scan ablage-backend:latest
```

**Umgebung**: Lokal oder CI
**Zeitpunkt**: Wöchentlich
**Automatisiert**: Geplant via CI

### Quality Gate Status Indicators

| Gate | Pass Criteria | Tool |
|------|---------------|------|
| Type Safety | mypy --strict passes | mypy |
| Linting | ruff check passes | ruff |
| Unit Tests | All tests pass | pytest |
| Integration Tests | All tests pass | pytest + Docker |
| Code Coverage | ≥ 80% | pytest-cov |
| Build | Docker build succeeds | docker-compose |
| Performance | API p95 < 500ms | Custom tests |
| Security | No HIGH/CRITICAL vulns | pip-audit, bandit |

### Pre-Commit Checklist

- [ ] `mypy app/` - Keine Type Errors
- [ ] `ruff check .` - Keine Linting Errors
- [ ] `pytest tests/unit/` - Alle Unit Tests grün
- [ ] `pytest --cov=app --cov-fail-under=80` - Coverage OK
- [ ] Deutsche Texte validiert (User-Facing)
- [ ] Secrets entfernt (keine API Keys im Code)

**Diese Checks werden automatisch von `.claude/hooks/pre-commit.py` ausgeführt!**

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
