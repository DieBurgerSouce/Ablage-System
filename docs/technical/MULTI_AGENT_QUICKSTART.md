# Multi-Agent System - Quick Start Guide

**Status**: ✅ Production-Ready
**Version**: 1.0
**Created**: 2024-11-25

## 🚀 Schnellstart

### Voraussetzungen

```bash
# System
- Docker 24.x+
- Docker Compose
- NVIDIA GPU (RTX 4080) mit CUDA 12.1+
- 32GB RAM (empfohlen)
- Ubuntu 22.04 LTS

# Prüfen
docker --version
docker-compose --version
nvidia-smi
```

### 1. System Starten

```bash
# Komplettes System starten (Backend + GPU-Worker + CPU-Worker + Datenbanken)
docker-compose up -d

# Logs verfolgen
docker-compose logs -f

# Einzelne Services prüfen
docker-compose ps
```

### 2. Gesundheit Prüfen

```bash
# Backend API
curl http://localhost:8000/health

# Agents Status
curl http://localhost:8000/api/v1/agents/status

# Prometheus Metriken
curl http://localhost:8000/api/v1/metrics

# Worker Status
docker exec ablage-worker-gpu celery -A app.workers.celery_app inspect active
docker exec ablage-worker-cpu celery -A app.workers.celery_app inspect active
```

## 📝 Dokument Verarbeiten

### Einfache OCR

```bash
# Dokument hochladen und verarbeiten
curl -X POST http://localhost:8000/api/v1/agents/execute/ocr \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc123",
    "file_path": "/path/to/document.pdf",
    "backend": "auto",
    "priority": 0
  }'

# Response:
# {
#   "status": "submitted",
#   "task_id": "abc-123-def",
#   "document_id": "doc123",
#   "backend": "deepseek",
#   "message": "OCR processing started"
# }
```

### Task-Status Prüfen

```bash
# Task-Fortschritt abfragen
curl http://localhost:8000/api/v1/agents/tasks/abc-123-def

# Response:
# {
#   "task_id": "abc-123-def",
#   "state": "PROCESSING",
#   "progress": 0.65,
#   "message": "Extracting text...",
#   "updated_at": "2024-11-25T10:30:45Z"
# }
```

### Vollständiger Workflow

```bash
# Kompletter Workflow (Classification → Pre → OCR → Post → QA → Storage)
curl -X POST http://localhost:8000/api/v1/agents/execute/workflow \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc456",
    "file_path": "/uploads/invoice.pdf",
    "priority": 1,
    "options": {
      "extract_entities": true,
      "detect_layout": true
    }
  }'
```

### Batch-Verarbeitung

```bash
# Mehrere Dokumente gleichzeitig
curl -X POST http://localhost:8000/api/v1/agents/execute/batch \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": ["doc1", "doc2", "doc3"],
    "file_paths": ["/path/1.pdf", "/path/2.pdf", "/path/3.pdf"],
    "backend": "got_ocr",
    "options": {}
  }'
```

## 🎯 Backend-Auswahl

### Automatische Auswahl

```bash
# Bestes Backend automatisch wählen
curl -X POST http://localhost:8000/api/v1/agents/route/backend \
  -H "Content-Type: application/json" \
  -d '{
    "document_metadata": {
      "document_type": "invoice",
      "complexity": "high",
      "has_tables": true,
      "quality_score": 0.85
    },
    "sla_requirements": {
      "max_processing_time_seconds": 30
    }
  }'

# Response:
# {
#   "backend": "deepseek",
#   "reason": "complex_layout_with_tables",
#   "confidence": 0.95,
#   "alternatives": ["hybrid"]
# }
```

### Verfügbare Backends

```bash
# Alle Backends mit Capabilities
curl http://localhost:8000/api/v1/agents/route/backends

# Response:
# {
#   "backends": [
#     {
#       "name": "deepseek",
#       "best_for": ["complex_layouts", "tables", "handwriting"],
#       "vram_gb": 12,
#       "avg_speed_pages_per_sec": 2.5,
#       "accuracy_score": 0.96
#     },
#     {
#       "name": "got_ocr",
#       "best_for": ["standard_text", "high_throughput"],
#       "vram_gb": 10,
#       "avg_speed_pages_per_sec": 6.0,
#       "accuracy_score": 0.92
#     }
#   ],
#   "by_speed": ["got_ocr", "deepseek", "surya", "hybrid"],
#   "by_accuracy": ["hybrid", "deepseek", "got_ocr", "surya"]
# }
```

## 📊 Monitoring

### Workflow-Status

```bash
# Kompletten Workflow-Zustand abrufen
curl http://localhost:8000/api/v1/agents/workflow/doc123

# Response:
# {
#   "document_id": "doc123",
#   "workflow": {
#     "status": "in_progress",
#     "current_phase": "ocr_processing",
#     "phases": {
#       "classification": {
#         "status": "completed",
#         "result": {"document_type": "invoice", "confidence": 0.95}
#       },
#       "preprocessing": {
#         "status": "completed",
#         "result": {"enhanced": true, "quality_improved": 0.15}
#       },
#       "ocr_processing": {
#         "status": "in_progress",
#         "progress": 0.65
#       }
#     }
#   }
# }
```

### Agent-Status

```bash
# Status aller Agents
curl http://localhost:8000/api/v1/agents/status

# Spezifischer Agent
curl http://localhost:8000/api/v1/agents/status/deepseek_ocr_agent
```

### Prometheus Metriken

```bash
# Alle Metriken (Prometheus-Format)
curl http://localhost:8000/api/v1/metrics

# Business Metriken (JSON)
curl http://localhost:8000/api/v1/metrics/business

# Response:
# {
#   "documents": {
#     "total_processed": 1523,
#     "total_failed": 12,
#     "success_rate_percent": 99.21
#   },
#   "agents": {
#     "deepseek": {
#       "total_processed": 450,
#       "avg_duration_seconds": 2.3
#     }
#   }
# }
```

## 🛠️ Entwicklung

### Lokaler Start (ohne Docker)

```bash
# 1. Dependencies installieren
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Redis & PostgreSQL starten
docker-compose up -d redis postgres minio

# 3. Datenbank migrieren
alembic upgrade head

# 4. Skills laden (optional)
python -c "import asyncio; from app.core.skill_loader import initialize_skills; asyncio.run(initialize_skills())"

# 5. Backend starten
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. GPU Worker starten (separate Terminal)
celery -A app.workers.celery_app worker \
  --queues=ocr_gpu,ocr.deepseek,ocr.got_ocr \
  --loglevel=info \
  --concurrency=1 \
  --pool=solo \
  --hostname=gpu-worker@%h

# 7. CPU Worker starten (separate Terminal)
celery -A app.workers.celery_app worker \
  --queues=ocr_cpu,preprocessing.classification,postprocessing.german \
  --loglevel=info \
  --concurrency=4 \
  --pool=prefork \
  --hostname=cpu-worker@%h
```

### Tests Ausführen

```bash
# Alle Tests
pytest

# Nur Unit-Tests
pytest tests/unit/ -v

# Mit Coverage
pytest --cov=app --cov-report=html

# GPU-Tests (benötigt GPU)
pytest -m gpu
```

## 🔧 Konfiguration

### Umgebungsvariablen

```bash
# .env erstellen
cp .env.example .env

# Wichtige Variablen:
DB_PASSWORD=your_secure_password
SECRET_KEY=your_secret_key
JWT_SECRET=your_jwt_secret

MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=your_minio_password

# OCR-Einstellungen
OCR_DEFAULT_BACKEND=auto  # auto, deepseek, got_ocr, surya, hybrid
OCR_DEFAULT_LANGUAGE=de
GPU_ENABLED=true
```

### Skills Hinzufügen

```bash
# Neues Skill erstellen
cat > Skills/custom/my_skill.yaml <<EOF
name: my_custom_skill
version: 1.0
category: custom
description: My custom agent skill

handler: app.agents.custom.my_agent:MyAgent
async_execution: true

parameters:
  - name: input_text
    type: str
    required: true

gpu_required: false
enabled: true
EOF

# System neu starten um Skills zu laden
docker-compose restart backend worker-gpu worker-cpu
```

## 📈 Performance-Tuning

### GPU-Optimierung

```bash
# GPU-Nutzung überwachen
watch -n 1 nvidia-smi

# Batch-Größe anpassen (docker-compose.yml)
environment:
  GPU_BATCH_SIZE: 4  # Standard
  GPU_MEMORY_FRACTION: 0.85  # 85% VRAM nutzen
```

### Worker Skalierung

```bash
# Mehr CPU-Worker für höheren Durchsatz
docker-compose up -d --scale worker-cpu=4

# Separate Worker für verschiedene Queues
docker-compose run -d worker-cpu celery -A app.workers.celery_app worker \
  --queues=preprocessing.classification \
  --concurrency=8
```

## 🐛 Troubleshooting

### GPU nicht verfügbar

```bash
# Prüfen
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.0-base nvidia-smi

# Lösung: NVIDIA Container Toolkit installieren
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Worker nicht erreichbar

```bash
# Worker-Logs prüfen
docker logs ablage-worker-gpu
docker logs ablage-worker-cpu

# Worker manuell starten
docker exec -it ablage-worker-gpu celery -A app.workers.celery_app worker --loglevel=debug

# Celery Inspector
docker exec ablage-worker-gpu celery -A app.workers.celery_app inspect active
docker exec ablage-worker-gpu celery -A app.workers.celery_app inspect stats
```

### Hohe GPU-Auslastung

```bash
# Batch-Größe reduzieren
# In app/agents/ocr/deepseek_agent.py:
MAX_BATCH_SIZE = 2  # Statt 4

# VRAM-Limit setzen
export CUDA_MEM_FRACTION=0.75

# Container neu starten
docker-compose restart worker-gpu
```

### Langsame Verarbeitung

```bash
# Queue-Längen prüfen
docker exec ablage-redis redis-cli llen ocr_gpu
docker exec ablage-redis redis-cli llen ocr_cpu

# Mehr Worker starten
docker-compose up -d --scale worker-cpu=4

# Priorisierung nutzen
curl -X POST .../execute/ocr -d '{"priority": 2, ...}'  # 2=critical
```

## 📚 Weitere Dokumentation

- [Agent Architecture](docs/AGENT_ARCHITECTURE.md) - Vollständige Architektur
- [Agent Implementation Guide](docs/AGENT_IMPLEMENTATION_GUIDE.md) - Implementierungsdetails
- [API Documentation](http://localhost:8000/docs) - Interaktive API-Docs (Swagger)
- [CLAUDE.md](CLAUDE.md) - Projekt-Kontext für KI-Entwicklung

## 🎯 Best Practices

### 1. Backend-Auswahl
- **DeepSeek**: Komplexe Layouts, Tabellen, Handschrift
- **GOT-OCR**: Hoher Durchsatz, saubere Scans
- **Surya**: Layout-Erhaltung, CPU-only
- **Hybrid**: Kritische Dokumente, maximale Genauigkeit

### 2. Priorisierung
- **0 (Normal)**: Standard-Dokumente
- **1 (High)**: Wichtige Geschäftsdokumente
- **2 (Critical)**: Zeit-kritische Verträge

### 3. Batch-Verarbeitung
- GPU-Batches: 4-8 Dokumente (je nach VRAM)
- CPU-Batches: 10-20 Dokumente
- Große Mengen in mehrere Batches aufteilen

### 4. Monitoring
- Prometheus-Metriken regelmäßig prüfen
- GPU-Auslastung unter 85% VRAM halten
- Queue-Längen überwachen

---

**Version**: 1.0
**Erstellt**: 2024-11-25
**Maintainer**: Ablage-System Team
