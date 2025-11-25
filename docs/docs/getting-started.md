# Schnellstart

Dieser Guide führt Sie durch die Installation und den ersten Einsatz von Ablage-System OCR.

---

## Voraussetzungen

### Hardware-Anforderungen

#### Minimum (Entwicklung)

- **CPU**: 4 Kerne (x86_64)
- **RAM**: 16 GB
- **Disk**: 100 GB SSD
- **GPU**: Optional (CPU-Fallback verfügbar)

#### Empfohlen (Produktion)

- **CPU**: 8+ Kerne (x86_64)
- **RAM**: 32+ GB
- **Disk**: 500+ GB NVMe SSD
- **GPU**: NVIDIA RTX 4080 oder besser (16GB+ VRAM)

### Software-Anforderungen

- **Betriebssystem**:
  - Ubuntu 22.04 LTS (empfohlen)
  - Debian 11+
  - Windows 11 mit WSL2
  - macOS 13+ (nur CPU-Modus)

- **Container Runtime**:
  - Docker 24.0+
  - Docker Compose 2.20+

- **GPU-Support** (optional):
  - NVIDIA Driver 525+
  - CUDA 12.0+
  - cuDNN 8.9+
  - NVIDIA Container Toolkit

- **Entwicklung**:
  - Python 3.11+
  - Git 2.40+
  - Make (optional)

---

## Installation

### Option 1: Docker Compose (empfohlen)

#### 1. Repository klonen

```bash
git clone https://github.com/ablage-system/ablage-system-ocr.git
cd ablage-system-ocr
```

#### 2. Umgebungsvariablen konfigurieren

```bash
# .env-Datei aus Vorlage erstellen
cp .env.example .env

# Bearbeiten Sie die Datei mit Ihren Einstellungen
nano .env
```

Mindestens diese Variablen anpassen:

```bash
# Database
POSTGRES_PASSWORD=your_secure_password
DATABASE_URL=postgresql://ablage_user:your_secure_password@postgres:5432/ablage_system

# MinIO (Object Storage)
MINIO_ROOT_USER=your_minio_user
MINIO_ROOT_PASSWORD=your_secure_minio_password

# Application
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)

# OCR Configuration
OCR_DEFAULT_BACKEND=got_ocr  # oder: deepseek, surya
GPU_ENABLED=true  # false für CPU-Modus
```

#### 3. Services starten

```bash
# Alle Services starten
docker-compose up -d

# Logs verfolgen
docker-compose logs -f

# Status prüfen
docker-compose ps
```

#### 4. Initialisierung abwarten

Erste Startzeit: ~2-5 Minuten (OCR-Modelle werden heruntergeladen)

```bash
# Backend-Health-Check
curl http://localhost:8000/health

# Warten bis Status "healthy"
docker-compose ps | grep healthy
```

#### 5. Zugriff

- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090

---

### Option 2: Lokale Entwicklung

#### 1. Python-Umgebung einrichten

```bash
# Repository klonen
git clone https://github.com/ablage-system/ablage-system-ocr.git
cd ablage-system-ocr

# Virtual Environment erstellen
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Dependencies installieren
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Pre-commit Hooks installieren
pre-commit install
```

#### 2. Services starten (Docker)

Starten Sie die benötigten Services mit Docker:

```bash
# Nur Infrastruktur-Services (ohne Backend)
docker-compose up -d postgres redis minio

# Warten bis Services bereit sind
sleep 10
```

#### 3. Datenbank initialisieren

```bash
# Umgebungsvariablen laden
export $(cat .env | xargs)

# Datenbank-Migrations anwenden
alembic upgrade head

# Testdaten laden (optional)
python scripts/seed_database.py
```

#### 4. Backend starten

```bash
# Development Server mit Hot-Reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Oder mit Auto-Reload auf Code-Änderungen
watchmedo auto-restart -d app -p '*.py' -- uvicorn app.main:app --reload
```

#### 5. Celery Worker starten (separates Terminal)

```bash
# Aktivieren Sie die Virtual Environment
source venv/bin/activate

# Worker starten
celery -A app.celery worker --loglevel=info --concurrency=1 --pool=solo

# Für GPU-Tasks: Sicherstellen dass CUDA verfügbar ist
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

---

### Option 3: Terraform Deployment

Für Produktionsumgebungen mit Infrastructure as Code:

```bash
cd infrastructure/terraform

# Terraform initialisieren
terraform init

# Konfiguration anpassen
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars

# Plan erstellen
terraform plan -out=tfplan

# Infrastruktur bereitstellen
terraform apply tfplan
```

[:octicons-arrow-right-24: Terraform-Dokumentation](infrastructure/terraform/overview.md)

---

## GPU-Setup

### NVIDIA-Treiber installieren

```bash
# Ubuntu 22.04
sudo apt update
sudo apt install -y nvidia-driver-535
sudo reboot

# Nach Neustart: Treiber prüfen
nvidia-smi
```

### CUDA Toolkit installieren

```bash
# CUDA 12.0
wget https://developer.download.nvidia.com/compute/cuda/12.0.0/local_installers/cuda_12.0.0_525.60.13_linux.run
sudo sh cuda_12.0.0_525.60.13_linux.run

# Environment Variables setzen
echo 'export PATH=/usr/local/cuda-12.0/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.0/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# CUDA prüfen
nvcc --version
```

### NVIDIA Container Toolkit

```bash
# Repository hinzufügen
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Installieren
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

# Testen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

[:octicons-arrow-right-24: Detailliertes GPU-Setup](installation/gpu-setup.md)

---

## Erste Schritte

### 1. API-Token generieren

```bash
# Admin-User erstellen
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "SecurePassword123!",
    "full_name": "Admin User"
  }'

# Login und Token erhalten
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=SecurePassword123!"

# Response enthält: {"access_token": "...", "token_type": "bearer"}
export API_TOKEN="your_token_here"
```

### 2. Dokument hochladen

```bash
# PDF hochladen
curl -X POST "http://localhost:8000/api/v1/documents/" \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "file=@sample-document.pdf" \
  -F "language=de" \
  -F "ocr_backend=auto"

# Response:
# {
#   "id": "abc123",
#   "filename": "sample-document.pdf",
#   "status": "queued",
#   "created_at": "2025-01-24T10:00:00Z"
# }
```

### 3. OCR-Verarbeitung starten

```bash
# Automatisch gestartet bei Upload, oder manuell:
curl -X POST "http://localhost:8000/api/v1/ocr/abc123/process" \
  -H "Authorization: Bearer $API_TOKEN"
```

### 4. Ergebnis abrufen

```bash
# Status prüfen
curl "http://localhost:8000/api/v1/documents/abc123" \
  -H "Authorization: Bearer $API_TOKEN"

# Extrahierten Text abrufen
curl "http://localhost:8000/api/v1/documents/abc123/text" \
  -H "Authorization: Bearer $API_TOKEN"
```

### 5. Verarbeitete Dokumente auflisten

```bash
# Alle Dokumente
curl "http://localhost:8000/api/v1/documents/" \
  -H "Authorization: Bearer $API_TOKEN"

# Mit Filtern
curl "http://localhost:8000/api/v1/documents/?status=completed&limit=10" \
  -H "Authorization: Bearer $API_TOKEN"
```

---

## Konfiguration

### Umgebungsvariablen

Vollständige Liste in [Konfigurationsreferenz](reference/environment-variables.md).

#### Wichtigste Einstellungen

```bash
# Application
SECRET_KEY=                    # App secret key (openssl rand -hex 32)
JWT_SECRET=                    # JWT signing key
ENVIRONMENT=development        # development, staging, production

# Database
DATABASE_URL=postgresql://...  # PostgreSQL connection string
DB_POOL_SIZE=20               # Connection pool size
DB_MAX_OVERFLOW=40            # Max overflow connections

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_MAX_CONNECTIONS=50

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET=documents

# OCR
OCR_DEFAULT_BACKEND=got_ocr    # deepseek, got_ocr, surya
OCR_MAX_BATCH_SIZE=32         # GPU batch size
OCR_TIMEOUT_SECONDS=300       # Processing timeout

# GPU
GPU_ENABLED=true
GPU_MEMORY_FRACTION=0.85      # Max VRAM usage (85%)
CUDA_VISIBLE_DEVICES=0        # GPU device IDs

# Monitoring
SENTRY_DSN=...                # Sentry error tracking
PROMETHEUS_ENABLED=true
LOG_LEVEL=info                # debug, info, warning, error
```

### OCR-Backend-Auswahl

```python
# In Python-Code
from app.services.ocr.orchestrator import OCROrchestrator

orchestrator = OCROrchestrator()

# Automatische Auswahl basierend auf Dokument
backend = orchestrator.select_backend(document)

# Manuelle Auswahl
backend = "deepseek"  # für komplexe Layouts
backend = "got_ocr"   # für schnelle Verarbeitung
backend = "surya"     # für CPU-only
```

[:octicons-arrow-right-24: OCR-Backend-Vergleich](ocr-engines/comparison.md)

---

## Troubleshooting

### Docker-Container startet nicht

```bash
# Logs prüfen
docker-compose logs backend

# Häufige Probleme:
# 1. Port bereits belegt
sudo lsof -i :8000

# 2. Insuffizienter Speicher
free -h

# 3. GPU nicht verfügbar
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### GPU wird nicht erkannt

```bash
# NVIDIA-Treiber prüfen
nvidia-smi

# Container Toolkit prüfen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# In Container prüfen
docker exec -it ablage-backend python -c "import torch; print(torch.cuda.is_available())"
```

### Langsame OCR-Verarbeitung

```bash
# GPU-Auslastung überwachen
watch -n 1 nvidia-smi

# Worker-Logs prüfen
docker-compose logs -f worker

# Backend-Auswahl optimieren
# got_ocr ist am schnellsten (5-7 pages/sec)
export OCR_DEFAULT_BACKEND=got_ocr
```

### Datenbank-Verbindungsfehler

```bash
# PostgreSQL-Status prüfen
docker-compose ps postgres

# Verbindung testen
docker exec -it ablage-postgres psql -U ablage_user -d ablage_system

# Connection Pool erhöhen
export DB_POOL_SIZE=40
export DB_MAX_OVERFLOW=80
```

[:octicons-arrow-right-24: Vollständiges Troubleshooting](operations/troubleshooting.md)

---

## Nächste Schritte

Jetzt wo Ablage-System läuft, erkunden Sie:

1. **[API-Dokumentation](api/overview.md)** - Vollständige REST-API-Referenz
2. **[Benutzerhandbuch](user-guide/upload-documents.md)** - Dokumentenverarbeitung im Detail
3. **[OCR-Engines](ocr-engines/overview.md)** - Backend-Auswahl und -Optimierung
4. **[Performance-Tuning](performance/gpu-optimization.md)** - GPU-Optimierung
5. **[Produktion-Deployment](deployment/production.md)** - Production-ready Setup
6. **[Monitoring](operations/monitoring.md)** - Überwachung und Alerting

---

## Hilfe

Brauchen Sie Unterstützung?

- 📖 **Dokumentation**: Durchsuchen Sie die vollständige Dokumentation
- 💬 **Community-Forum**: [forum.ablage-system.local](https://forum.ablage-system.local)
- 🐛 **Bug Report**: [GitHub Issues](https://github.com/ablage-system/ablage-system-ocr/issues)
- 📧 **Email**: [support@ablage-system.local](mailto:support@ablage-system.local)
