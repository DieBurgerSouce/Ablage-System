# Developer Onboarding Guide

> **Ablage-System - Entwickler-Einstieg**
> Version: 1.0 | Stand: Januar 2025

---

## Willkommen im Ablage-System Team!

Dieses Dokument führt Sie durch die ersten Schritte als Entwickler im Ablage-System Projekt. Nach Abschluss dieses Guides haben Sie:

- ✅ Ihre Entwicklungsumgebung eingerichtet
- ✅ Das System lokal gestartet
- ✅ Die Architektur verstanden
- ✅ Ihren ersten Code-Beitrag gemacht

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#voraussetzungen)
2. [Repository Setup](#repository-setup)
3. [Entwicklungsumgebung](#entwicklungsumgebung)
4. [Systemstart](#systemstart)
5. [Architektur-Übersicht](#architektur-übersicht)
6. [Entwicklungs-Workflow](#entwicklungs-workflow)
7. [Code-Konventionen](#code-konventionen)
8. [Testing](#testing)
9. [Häufige Aufgaben](#häufige-aufgaben)
10. [Ressourcen](#ressourcen)

---

## Voraussetzungen

### Hardware-Anforderungen

| Komponente | Minimum | Empfohlen |
|------------|---------|-----------|
| CPU | 4 Cores | 8+ Cores |
| RAM | 16 GB | 32 GB |
| GPU | - | NVIDIA RTX 3080+ |
| Storage | 50 GB SSD | 200 GB NVMe |

### Software-Anforderungen

```bash
# Prüfen Sie Ihre Versionen
docker --version          # >= 24.0
docker-compose --version  # >= 2.20
python --version          # >= 3.11
node --version            # >= 18.0
git --version             # >= 2.40

# Für GPU-Entwicklung
nvidia-smi                # CUDA >= 12.0
```

### Accounts & Zugänge

Bevor Sie beginnen, benötigen Sie:

- [ ] **GitLab/GitHub Account** - Zugang zum Repository
- [ ] **Slack/Teams** - Team-Kommunikation (#ablage-dev Channel)
- [ ] **Jira/Linear** - Ticket-System
- [ ] **1Password/Vault** - Secrets-Management

---

## Repository Setup

### 1. Repository klonen

```bash
# Via SSH (empfohlen)
git clone git@github.com:ihre-firma/ablage-system.git
cd ablage-system

# Via HTTPS
git clone https://github.com/ihre-firma/ablage-system.git
cd ablage-system
```

### 2. Umgebungsvariablen konfigurieren

```bash
# Vorlage kopieren
cp .env.example .env

# Bearbeiten Sie die .env Datei
# Fragen Sie einen Kollegen nach den Entwicklungs-Secrets
```

Wichtige Variablen für Entwicklung:

```bash
# .env (Entwicklung)
DATABASE_URL=postgresql+asyncpg://ablage_admin:dev_password@localhost:5433/ablage
REDIS_URL=redis://:dev_password@localhost:6380/0
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
SECRET_KEY=dev-secret-key-not-for-production
DEBUG=true
LOG_LEVEL=DEBUG
```

### 3. Git Hooks einrichten

```bash
# Pre-commit hooks installieren
pip install pre-commit
pre-commit install

# Hooks manuell testen
pre-commit run --all-files
```

---

## Entwicklungsumgebung

### Python Backend Setup

```bash
# Virtual Environment erstellen
python3.11 -m venv venv

# Aktivieren
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Dependencies installieren
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Typ-Stubs installieren
pip install types-redis types-requests mypy-extensions
```

### Frontend Setup

```bash
cd frontend

# Node Modules installieren
npm install

# Optional: Globale Tools
npm install -g typescript eslint prettier
```

### IDE-Konfiguration

Siehe separaten Guide: [IDE-Setup-Guide.md](IDE-Setup-Guide.md)

Unterstützte IDEs:
- **VS Code** (empfohlen)
- **PyCharm Professional**
- **Neovim** mit entsprechenden Plugins

---

## Systemstart

### Option 1: Docker-Only (empfohlen für Einsteiger)

```bash
# Alle Services starten
docker-compose up -d

# Status prüfen
docker-compose ps

# Logs verfolgen
docker-compose logs -f backend
```

**Verfügbare Endpunkte:**

| Service | URL |
|---------|-----|
| Frontend | http://localhost:80 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Grafana | http://localhost:3002 |
| MinIO Console | http://localhost:9001 |

### Option 2: Hybrid (Backend lokal, Infra in Docker)

```bash
# Nur Infrastruktur starten
docker-compose up -d postgres redis minio

# Backend lokal starten
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In separatem Terminal: Celery Worker
celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```

### Option 3: Frontend Hot-Reload

```bash
# Infrastruktur + Backend in Docker
docker-compose up -d postgres redis minio backend worker

# Frontend lokal mit Hot-Reload
cd frontend
npm run dev
```

### Erste Schritte nach Start

```bash
# 1. Health-Check
curl http://localhost:8000/api/v1/health

# 2. Datenbank-Migrationen (falls nicht automatisch)
docker-compose exec backend alembic upgrade head

# 3. Test-User erstellen
docker-compose exec backend python -m app.scripts.create_user \
    --email dev@local.test \
    --password devpassword \
    --role admin
```

---

## Architektur-Übersicht

### System-Komponenten

```
┌─────────────────────────────────────────────────────────────┐
│                    Ablage-System OCR                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Frontend  │    │   Backend   │    │   Workers   │     │
│  │  (React)    │───▶│  (FastAPI)  │───▶│  (Celery)   │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │             │
│         │                  ▼                  ▼             │
│         │          ┌─────────────┐    ┌─────────────┐      │
│         │          │ PostgreSQL  │    │    Redis    │      │
│         │          │  (Daten)    │    │   (Queue)   │      │
│         │          └─────────────┘    └─────────────┘      │
│         │                                    │              │
│         │                                    ▼              │
│         │                          ┌─────────────────┐     │
│         │                          │   OCR Backends  │     │
│         │                          │ DeepSeek | GOT  │     │
│         │                          │  Surya | GPU    │     │
│         │                          └─────────────────┘     │
│         ▼                                                   │
│  ┌─────────────┐                                           │
│  │    MinIO    │                                           │
│  │  (Storage)  │                                           │
│  └─────────────┘                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Verzeichnisstruktur

```
ablage-system/
├── app/                      # Backend-Code
│   ├── api/v1/               # REST API Endpoints
│   ├── core/                 # Konfiguration, Sicherheit
│   ├── db/                   # Datenbank-Models, Schemas
│   ├── services/             # Business Logic
│   │   ├── document_services/  # Dokument-Operationen
│   │   └── ocr/              # OCR-Backends
│   ├── workers/              # Celery Tasks
│   └── utils/                # Hilfsfunktionen
├── frontend/                 # React Frontend
│   ├── src/
│   │   ├── components/       # UI-Komponenten
│   │   ├── features/         # Feature-Module
│   │   ├── hooks/            # Custom React Hooks
│   │   └── services/         # API-Clients
├── tests/                    # Tests
│   ├── unit/                 # Unit Tests
│   ├── integration/          # Integration Tests
│   └── fixtures/             # Test-Daten
├── infrastructure/           # IaC (Terraform, Ansible)
├── migrations/               # Alembic Migrationen
├── docs/                     # Dokumentation
└── .claude/                  # AI-Entwicklungshilfen
```

### Wichtige Design-Entscheidungen

| Bereich | Entscheidung | Begründung |
|---------|--------------|------------|
| **API** | REST + OpenAPI | Standard, gut dokumentiert |
| **DB** | PostgreSQL | Robustheit, pgvector für Embeddings |
| **Queue** | Celery + Redis | Skalierbar, GPU-Task-Isolation |
| **Storage** | MinIO | S3-kompatibel, On-Premises |
| **OCR** | Multi-Backend | Flexibilität je nach Dokumenttyp |
| **Frontend** | React + TanStack | Performance, Developer Experience |

---

## Entwicklungs-Workflow

### Git Branching

```
main                    # Produktions-Code
├── develop             # Entwicklungs-Branch
│   ├── feature/ABC-123-beschreibung
│   ├── bugfix/ABC-124-fix-beschreibung
│   └── hotfix/ABC-125-kritisch
```

### Feature-Entwicklung

```bash
# 1. Neuen Branch erstellen
git checkout develop
git pull origin develop
git checkout -b feature/ABC-123-neue-funktion

# 2. Entwickeln mit regelmäßigen Commits
git add .
git commit -m "feat(scope): beschreibung"

# 3. Tests ausführen
pytest

# 4. Push und Pull Request
git push origin feature/ABC-123-neue-funktion
# PR in GitLab/GitHub erstellen
```

### Commit-Konventionen

Wir nutzen [Conventional Commits](https://www.conventionalcommits.org/):

```bash
# Format
<type>(<scope>): <beschreibung>

# Typen
feat     # Neue Funktion
fix      # Bugfix
docs     # Dokumentation
style    # Formatierung (kein Code-Change)
refactor # Code-Umstrukturierung
test     # Tests hinzufügen/ändern
chore    # Build, Dependencies, etc.

# Beispiele
feat(ocr): DeepSeek-Backend für Fraktur hinzufügen
fix(api): Race Condition bei Dokument-Upload beheben
docs(readme): Installationsanleitung aktualisieren
test(services): Unit-Tests für DocumentService erweitern
```

### Code Review

Jeder PR benötigt:

- [ ] Mindestens 1 Approval
- [ ] Alle Tests bestanden
- [ ] Type-Checking ohne Fehler
- [ ] Linting ohne Fehler
- [ ] Dokumentation aktualisiert (falls relevant)

---

## Code-Konventionen

### Python (Backend)

```python
# ✅ Vollständige Type-Hints
async def process_document(
    document_id: str,
    backend: str = "deepseek"
) -> DocumentResult:
    """Verarbeitet ein Dokument mit OCR.

    Args:
        document_id: Eindeutige Dokument-ID
        backend: OCR-Backend (deepseek, got_ocr, surya)

    Returns:
        DocumentResult mit extrahiertem Text

    Raises:
        DocumentNotFoundError: Dokument existiert nicht
    """
    pass

# ❌ Keine Type-Hints
def process_document(document_id, backend="deepseek"):
    pass
```

### TypeScript (Frontend)

```typescript
// ✅ Explizite Typen
interface DocumentUploadProps {
  onSuccess: (documentId: string) => void;
  maxFileSizeMB?: number;
}

const DocumentUpload: React.FC<DocumentUploadProps> = ({
  onSuccess,
  maxFileSizeMB = 50
}) => {
  // ...
};

// ❌ any vermeiden
const DocumentUpload = (props: any) => {
  // ...
};
```

### Wichtige Regeln

1. **Deutsche Sprache** für User-facing Content
2. **Keine Secrets** im Code
3. **Strukturiertes Logging** (kein print())
4. **Error Handling** mit spezifischen Exceptions
5. **GPU-Speicher** überwachen (<85% VRAM)

Vollständige Konventionen: [CONVENTIONS.md](../../../CONVENTIONS.md)

---

## Testing

### Test-Struktur

```
tests/
├── unit/                 # Isolierte Tests
│   ├── services/
│   ├── api/
│   └── utils/
├── integration/          # Service-Integration
│   ├── test_ocr_pipeline.py
│   └── test_document_workflow.py
├── e2e/                  # End-to-End (Playwright)
└── fixtures/             # Test-Daten
```

### Tests ausführen

```bash
# Alle Tests
pytest

# Nur Unit-Tests
pytest tests/unit/ -v

# Mit Coverage
pytest --cov=app --cov-report=html

# Spezifische Tests
pytest -k "test_deepseek" -v

# GPU-Tests (wenn GPU verfügbar)
pytest -m gpu
```

### Test schreiben

```python
# tests/unit/services/test_document_service.py
import pytest
from unittest.mock import Mock, AsyncMock
from app.services.document_service import DocumentService

@pytest.mark.asyncio
async def test_create_document_success():
    """Dokument erfolgreich erstellen."""
    # Arrange
    mock_db = AsyncMock()
    mock_storage = AsyncMock()
    service = DocumentService(db=mock_db, storage=mock_storage)

    # Act
    result = await service.create(
        filename="test.pdf",
        content=b"PDF content",
        user_id="user-123"
    )

    # Assert
    assert result.id is not None
    assert result.filename == "test.pdf"
    mock_storage.upload.assert_called_once()
```

### Test-Coverage

- **Minimum**: 80% overall
- **Kritische Pfade**: 95%+ (OCR, Auth, Datenbank)
- **Neuer Code**: 100% vor Merge

---

## Häufige Aufgaben

### Neuen API-Endpoint hinzufügen

```python
# 1. app/api/v1/neue_ressource.py
from fastapi import APIRouter, Depends
from app.db.schemas import NeueRessourceCreate, NeueRessourceResponse

router = APIRouter(prefix="/neue-ressource", tags=["Neue Ressource"])

@router.post("/", response_model=NeueRessourceResponse)
async def create_neue_ressource(
    data: NeueRessourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> NeueRessourceResponse:
    """Erstellt eine neue Ressource."""
    # Implementation
    pass

# 2. In app/api/v1/__init__.py registrieren
from .neue_ressource import router as neue_ressource_router
api_router.include_router(neue_ressource_router)
```

### Datenbank-Migration erstellen

```bash
# 1. Model ändern in app/db/models.py

# 2. Migration generieren
docker-compose exec backend alembic revision --autogenerate -m "beschreibung"

# 3. Migration prüfen
cat migrations/versions/abc123_beschreibung.py

# 4. Migration anwenden
docker-compose exec backend alembic upgrade head
```

### Neuen Celery-Task hinzufügen

```python
# app/workers/tasks/neue_tasks.py
from celery import shared_task
from app.workers.celery_app import celery_app

@celery_app.task(bind=True, max_retries=3)
def neuer_task(self, document_id: str) -> dict:
    """Beschreibung des Tasks."""
    try:
        # Implementation
        return {"status": "success", "document_id": document_id}
    except Exception as e:
        raise self.retry(exc=e, countdown=60)
```

### Neues OCR-Backend integrieren

Siehe: [OCR-Backend-Integration-Guide.md](OCR-Backend-Integration-Guide.md)

---

## Ressourcen

### Interne Dokumentation

| Dokument | Beschreibung |
|----------|--------------|
| [CLAUDE.md](../../../CLAUDE.md) | Projektkontext für AI-Assistenten |
| [ARCHITECTURE.md](../../../ARCHITECTURE.md) | Architektur-Entscheidungen |
| [CONVENTIONS.md](../../../CONVENTIONS.md) | Code-Standards |
| [API-Dokumentation](http://localhost:8000/docs) | OpenAPI Swagger UI |
| [.claude/Docs/](../) | Erweiterte Dokumentation |

### Externe Ressourcen

| Thema | Link |
|-------|------|
| FastAPI | https://fastapi.tiangolo.com/ |
| SQLAlchemy 2.0 | https://docs.sqlalchemy.org/ |
| Celery | https://docs.celeryq.dev/ |
| React | https://react.dev/ |
| TanStack Query | https://tanstack.com/query |
| Tailwind CSS | https://tailwindcss.com/ |

### Team-Kontakte

| Rolle | Name | Kontakt |
|-------|------|---------|
| Tech Lead | - | @lead im Slack |
| Backend Lead | - | @backend-lead |
| Frontend Lead | - | @frontend-lead |
| DevOps | - | @devops |

### Hilfe bekommen

1. **#ablage-dev** Slack Channel für allgemeine Fragen
2. **#ablage-help** für dringende Probleme
3. **Pair Programming** - Fragen Sie einen Kollegen!
4. **Code Reviews** - Nutzen Sie PRs für Feedback

---

## Checkliste: Erste Woche

### Tag 1-2: Setup
- [ ] Repository geklont
- [ ] Entwicklungsumgebung eingerichtet
- [ ] System lokal gestartet
- [ ] Ersten Health-Check durchgeführt

### Tag 3-4: Verstehen
- [ ] CLAUDE.md gelesen
- [ ] ARCHITECTURE.md gelesen
- [ ] API-Dokumentation erkundet
- [ ] Code-Struktur durchgegangen

### Tag 5: Erster Beitrag
- [ ] Kleines Ticket bearbeitet
- [ ] Tests geschrieben
- [ ] PR erstellt
- [ ] Code Review erhalten

---

## FAQ für neue Entwickler

### "Warum Docker-only Entwicklung?"

Konsistenz und GPU-Isolation. Die OCR-Modelle benötigen spezifische CUDA-Versionen.

### "Wie debugge ich im Container?"

```bash
# Logs verfolgen
docker-compose logs -f backend

# In Container einloggen
docker-compose exec backend bash

# Remote Debugging mit VS Code
# Siehe IDE-Setup-Guide.md
```

### "Warum so strikt mit Type-Hints?"

Produktionssystem mit GPU-Workloads. Typen verhindern Runtime-Fehler und verbessern IDE-Support.

### "Wie teste ich GPU-Code ohne GPU?"

```python
@pytest.mark.skipif(not torch.cuda.is_available(), reason="GPU required")
def test_gpu_feature():
    pass
```

Tests werden auf CI mit GPU ausgeführt.

---

*Letzte Aktualisierung: Januar 2025*
