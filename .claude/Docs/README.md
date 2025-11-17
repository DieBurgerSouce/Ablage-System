# Ablage System - Documentation

**Intelligent Document Processing System with Multi-Backend OCR**

---

## 🎯 Overview

Das Ablage-System ist ein hochmodernes Document Processing System mit intelligenter OCR-Erkennung, das GPU-beschleunigte ML-Modelle mit CPU-Fallback-Optionen kombiniert. Spezialisiert auf deutsche Geschäftsdokumente (Rechnungen, Verträge, etc.) mit vollständiger Unterstützung für Umlaute und komplexe Layouts.

### Key Features

- **🚀 Multi-Backend OCR**: DeepSeek-Janus-Pro, GOT-OCR 2.0, Surya+Docling
- **🧠 Intelligent Routing**: Automatische Backend-Auswahl basierend auf Document-Komplexität
- **⚡ GPU-Beschleunigung**: NVIDIA CUDA-optimiert (RTX 4080, 16GB VRAM)
- **📊 Production-Ready**: FastAPI, PostgreSQL, Redis, MinIO
- **🔒 Enterprise Security**: JWT Auth, 2FA, RBAC, API Keys
- **📈 Monitoring**: Prometheus + Grafana Dashboards
- **🌐 Modern Frontend**: React 18 + TypeScript + Vite

---

## 📚 Documentation Index

### 🏁 Getting Started

| Document | Description |
|----------|-------------|
| [Mission & Vision](./Guides/Mission.md) | Projekt-Vision, Architektur-Übersicht, Ziele |
| [Development Setup](./Guides/Development-Setup.md) | Lokale Entwicklungsumgebung aufsetzen |
| [Tech Stack](./Guides/TechStack.md) | Technologie-Stack im Detail |

### 🏗️ Architecture & Design

| Document | Description |
|----------|-------------|
| [Frontend Architecture](./Frontend-Architecture.md) | React/TypeScript SPA, State Management, Routing |
| [ML Model Management](./ML-Model-Management.md) | GPU/VRAM Management, Quantization, Performance |
| [Data Pipeline Guide](./Guides/Data-Pipeline-Guide.md) | ETL, Preprocessing, OCR Processing, Postprocessing |
| [Scalability Guide](./Guides/Scalability-Guide.md) | Horizontal/Vertical Scaling, Load Balancing |

### 💾 Database & Storage

| Document | Description |
|----------|-------------|
| [Database Schema](./Guides/Database.md) | 44 Tabellen, Relationships, Indizes |
| [SQL Alchemy Models](./Guides/Database_SQL_Alchemy.md) | Pydantic/SQLAlchemy Implementation |
| [Alembic Migrations](./Guides/Database_Alembic_Migrations.md) | Database Migration Setup & Best Practices |
| [Query Performance](./Guides/Database_Query_Performance_Optimization.md) | Index-Strategien, Partitioning |
| [File Storage](./Guides/File-Storage-Management.md) | MinIO/S3, Lifecycle Management |

### 🔐 Security & Authentication

| Document | Description |
|----------|-------------|
| [Security & Authentication](./Guides/Security&Authentication.md) | JWT, OAuth2, 2FA, API Keys, OWASP Protection |
| [Rate Limiting](./Guides/Rate-Limiting-Guide.md) | API Rate Limits, Throttling |

### 📡 API Documentation

| Document | Description |
|----------|-------------|
| [API Documentation](./API/API_Documentation.md) | 50+ Endpoints, OpenAPI/Swagger Spec |
| [API Client SDK](./Guides/API-Client-SDK.md) | Python/JavaScript SDKs, Code Examples |
| [Webhooks Guide](./Guides/Webhooks-Guide.md) | Webhook Integration, Events, Security |

### ⚙️ Operations & DevOps

| Document | Description |
|----------|-------------|
| [Deployment Production](./Guides/Deployment-Production.md) | Docker, Kubernetes, CI/CD Pipelines |
| [Infrastructure as Code](./Guides/Infrastructure-as-Code.md) | Terraform, Ansible, K8s Manifests |
| [Backup & Recovery](./Guides/Backup-Recovery-Guide.md) | Backup Strategies, Restore Procedures |
| [Disaster Recovery](./Guides/Disaster-Recovery.md) | Failover, RTO/RPO, Emergency Procedures |

### 📊 Monitoring & Observability

| Document | Description |
|----------|-------------|
| [Metrics & Monitoring](./Guides/Metrics-Monitoring-Guide.md) | Prometheus, Custom Metrics, Dashboards |
| [Grafana Configuration](./Guides/Grafana_Config.md) | Dashboard Setup, Alert Rules |
| [Error Handling & Logging](./Guides/Error-Handling-Logging.md) | Structured Logging, Error Tracking |
| [Troubleshooting Guide](./Guides/Troubleshooting-Guide.md) | Common Issues, Debug Techniques |

### 🧪 Testing & Quality

| Document | Description |
|----------|-------------|
| [Testing Guide](./Guides/Testing-Guide.md) | Unit, Integration, E2E, Load Testing |
| [Code Quality Standards](./Guides/Code-Quality-Standards.md) | Coding Guidelines, Best Practices |

### 🔄 Background Tasks & Caching

| Document | Description |
|----------|-------------|
| [Background Tasks](./Guides/Background-Tasks.md) | Celery, Task Queues, Retry Strategies |
| [Caching Strategy](./Guides/Caching-Strategy.md) | Redis Caching, Cache Invalidation |
| [Notification System](./Guides/Notification-System.md) | Email, Webhooks, Push Notifications |

### 🔧 Maintenance & Support

| Document | Description |
|----------|-------------|
| [Migration Guide](./Guides/Migration-Guide.md) | Database Migrations, Version Upgrades |
| [CHANGELOG](./CHANGELOG.md) | Version History, Release Notes |
| [CONTRIBUTING](./CONTRIBUTING.md) | Developer Guidelines, PR Process |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20 LTS
- PostgreSQL 16+
- Redis 7.2+
- NVIDIA GPU with CUDA 12.1+ (optional, CPU fallback available)

### 1. Clone Repository

```bash
git clone https://github.com/your-org/ablage-system.git
cd ablage-system
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run migrations
alembic upgrade head

# Start backend
uvicorn backend.main:app --reload
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
pnpm install

# Start dev server
pnpm dev
```

### 4. Access Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Grafana**: http://localhost:3000

---

## 🏗️ Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   FRONTEND (React SPA)                   │
│              TypeScript + Vite + TailwindCSS             │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                   API GATEWAY (FastAPI)                  │
│       Auth, Validation, Rate Limiting, Routing           │
└────────────┬──────────────────────┬──────────────────────┘
             │                      │
             ▼                      ▼
┌─────────────────────┐  ┌──────────────────────────────┐
│  ORCHESTRATOR       │  │   BACKGROUND TASKS           │
│  (Intelligent       │  │   (Celery Workers)           │
│   Router)           │  │                              │
└─────┬───────────────┘  └──────────────────────────────┘
      │
      ├──────────┬──────────┬──────────┐
      ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ GPU-A    │ │ GPU-B    │ │   CPU    │
│DeepSeek  │ │ GOT-OCR  │ │  Surya   │
│Janus-Pro │ │   2.0    │ │ +Docling │
└──────────┘ └──────────┘ └──────────┘
      │          │          │
      └──────────┴──────────┴───────────┐
                                        ▼
                          ┌──────────────────────────┐
                          │  POST-PROCESSING         │
                          │  Validation, Extraction  │
                          └──────────┬───────────────┘
                                     ▼
┌───────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                        │
│  ┌──────────────┐ ┌───────────┐ ┌────────────────┐      │
│  │ PostgreSQL   │ │   Redis   │ │   MinIO/S3     │      │
│  │ (Metadata)   │ │  (Cache)  │ │  (Files)       │      │
│  └──────────────┘ └───────────┘ └────────────────┘      │
└───────────────────────────────────────────────────────────┘
```

---

## 🔄 Processing Flow

```
1. Document Upload
   │
   ├─► File Validation
   │   └─► Format Check (PDF, PNG, JPG, TIFF)
   │
   ├─► Preprocessing
   │   ├─► Image Enhancement
   │   ├─► Deskewing
   │   └─► Thumbnail Generation
   │
   ├─► Complexity Analysis
   │   └─► Route to Optimal Backend
   │
   ├─► OCR Processing
   │   ├─► DeepSeek (Complex Docs)
   │   ├─► GOT-OCR (Simple Docs)
   │   └─► Surya+Docling (CPU Fallback)
   │
   ├─► Postprocessing
   │   ├─► Confidence Scoring
   │   ├─► Data Validation
   │   ├─► Field Extraction
   │   └─► Format Conversion
   │
   └─► Result Storage
       ├─► Database (Metadata)
       ├─► S3 (Files)
       └─► Cache (Results)
```

---

## 📊 System Requirements

### Minimum Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 Cores | 8+ Cores (i9-13900KF) |
| **RAM** | 16 GB | 64 GB |
| **GPU** | None (CPU fallback) | NVIDIA RTX 4080 (16GB VRAM) |
| **Storage** | 100 GB SSD | 500 GB NVMe SSD |
| **OS** | Ubuntu 22.04 | Ubuntu 22.04 LTS |

### Software Requirements

- **Python**: 3.11+
- **Node.js**: 20 LTS
- **PostgreSQL**: 16+
- **Redis**: 7.2+
- **CUDA**: 12.1+ (für GPU)
- **Docker**: 24+ (optional)
- **Kubernetes**: 1.28+ (production)

---

## 🔧 Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/ablage_system

# Redis
REDIS_URL=redis://localhost:6379/0

# S3/MinIO
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key

# OCR Backends
ENABLE_GPU_BACKENDS=true
DEFAULT_OCR_BACKEND=auto  # auto, deepseek, got_ocr, cpu_surya

# API
SECRET_KEY=your_secret_key_here
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Monitoring
ENABLE_METRICS=true
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
```

---

## 📈 Performance Benchmarks

### Processing Speed (Single Page)

| Backend | Complexity | Time | VRAM | Accuracy |
|---------|-----------|------|------|----------|
| **DeepSeek-Janus-Pro** | Complex | 1-2s | 14GB | ⭐⭐⭐⭐⭐ |
| **GOT-OCR 2.0** | Simple | 0.3-0.5s | 11GB | ⭐⭐⭐⭐ |
| **Surya+Docling** | Any | 3-5s | 12GB RAM | ⭐⭐⭐ |

### Throughput (Documents/Hour)

- **GPU-Optimized**: 1800-3600 pages/hour
- **CPU-Only**: 720-1200 pages/hour
- **Mixed (Auto-Routing)**: 2400-3000 pages/hour

---

## 🤝 Contributing

Interessiert an Contributing? Lies unsere [Contributing Guidelines](./CONTRIBUTING.md).

### Development Workflow

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## 📝 License

Proprietary - All rights reserved

---

## 🆘 Support

### Documentation
- [Full Documentation](./Guides/)
- [API Reference](./API/API_Documentation.md)
- [Troubleshooting](./Guides/Troubleshooting-Guide.md)

### Contact
- **Engineering Team**: engineering@ablage-system.com
- **Platform Team**: platform-team@ablage-system.com
- **Emergency**: +49 XXX XXXXXXX (PagerDuty)

---

## 📅 Release Information

**Current Version**: 1.0.0 (Development)

See [CHANGELOG](./CHANGELOG.md) for version history.

---

## 🔗 Related Projects

- [DeepSeek-Janus-Pro](https://huggingface.co/deepseek-ai/Janus-Pro-1B)
- [GOT-OCR 2.0](https://github.com/Ucas-HaoranWei/GOT-OCR2.0)
- [Surya OCR](https://github.com/VikParuchuri/surya)
- [Docling](https://github.com/DS4SD/docling)

---

**Built with ❤️ for intelligent document processing**
