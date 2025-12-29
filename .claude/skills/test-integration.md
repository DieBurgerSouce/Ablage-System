---
name: test-integration
description: Integration Tests fuer das Ablage-System. Nutze diesen Skill fuer API-Tests, Datenbank-Integration, Celery Task Tests und End-to-End Workflows. Testet das Zusammenspiel aller Komponenten.
---

# Integration Testing (Ablage-System)

Teste das Zusammenspiel von API, Datenbank, Services und Workers.

## Quick Commands

```bash
# Alle Integration Tests
docker-compose exec backend pytest tests/integration/ -v

# Mit echter Datenbank
docker-compose exec backend pytest tests/integration/ -v --db=postgres

# Bestimmte Kategorie
docker-compose exec backend pytest tests/integration/api/ -v
```

## Test-Struktur

```
tests/integration/
├── conftest.py              # DB Fixtures, API Client
├── api/
│   ├── test_documents.py    # Document Endpoints
│   ├── test_ocr.py          # OCR Endpoints
│   └── test_health.py       # Health Checks
├── services/
│   ├── test_ocr_pipeline.py # Voller OCR Flow
│   └── test_export.py       # Export Service
└── workers/
    ├── test_celery_tasks.py # Celery Integration
    └── test_ocr_tasks.py    # OCR Worker Tasks
```

## Fixtures

```python
# tests/integration/conftest.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.main import app
from app.db.models import Base

# Test-Datenbank
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@postgres:5432/ablage_test"

@pytest.fixture(scope="session")
async def db_engine():
    """Erstellt Test-Datenbank Engine."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session(db_engine):
    """Datenbank-Session pro Test."""
    async with AsyncSession(db_engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
async def client():
    """Async HTTP Client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def sample_pdf():
    """Echtes Test-PDF."""
    with open("tests/fixtures/sample_german.pdf", "rb") as f:
        return f.read()
```

## API Integration Tests

```python
# tests/integration/api/test_documents.py
import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upload_to_database(client: AsyncClient, db_session):
    """Upload sollte Dokument in DB speichern."""
    files = {"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")}

    response = await client.post("/api/v1/documents/", files=files)

    assert response.status_code == 201
    doc_id = response.json()["id"]

    # Verifizieren in DB
    from app.db.models import Document
    doc = await db_session.get(Document, doc_id)
    assert doc is not None
    assert doc.filename == "test.pdf"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_not_found(client: AsyncClient):
    """Nicht existierendes Dokument sollte 404 geben."""
    response = await client.get("/api/v1/documents/nonexistent-id")

    assert response.status_code == 404
    assert "nicht gefunden" in response.json()["nachricht"]
```

## OCR Pipeline Integration

```python
# tests/integration/services/test_ocr_pipeline.py
import pytest
from app.services.ocr.orchestrator import OCROrchestrator
from app.services.storage_service import StorageService

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_ocr_pipeline(sample_pdf, db_session):
    """Vollstaendiger OCR-Workflow: Upload -> Process -> Store."""
    storage = StorageService()
    ocr = OCROrchestrator()

    # 1. Upload zu MinIO
    doc_id = await storage.upload(sample_pdf, "test.pdf")

    # 2. OCR Processing
    result = await ocr.process(doc_id)

    assert result.text is not None
    assert len(result.text) > 0
    assert "ä" in result.text or "ö" in result.text  # Deutsche Umlaute

    # 3. Ergebnis in DB gespeichert
    from app.db.models import Document
    doc = await db_session.get(Document, doc_id)
    assert doc.extracted_text == result.text

@pytest.mark.integration
@pytest.mark.asyncio
async def test_ocr_backend_fallback():
    """Bei GPU-Fehler sollte auf CPU gefallen werden."""
    ocr = OCROrchestrator()

    # Simuliere GPU-Fehler
    with patch('torch.cuda.is_available', return_value=False):
        result = await ocr.process("test-doc-id")

    assert result.backend_used == "surya"  # CPU Fallback
```

## Celery Task Integration

```python
# tests/integration/workers/test_celery_tasks.py
import pytest
from app.workers.ocr_tasks import process_document_task
from celery.result import AsyncResult

@pytest.mark.integration
@pytest.mark.asyncio
async def test_celery_ocr_task(sample_pdf):
    """OCR Task sollte async verarbeitet werden."""
    # Task starten
    result = process_document_task.delay("test-doc-id", backend="deepseek")

    # Warten auf Ergebnis (mit Timeout)
    task_result = result.get(timeout=60)

    assert task_result["status"] == "success"
    assert "text" in task_result

@pytest.mark.integration
async def test_celery_task_retry_on_failure():
    """Task sollte bei Fehler wiederholt werden."""
    with patch('app.services.ocr.deepseek.DeepSeekOCR.process',
               side_effect=Exception("GPU Error")):

        result = process_document_task.delay("test-doc-id")

        # Sollte nach 3 Retries fehlschlagen
        with pytest.raises(Exception):
            result.get(timeout=180)

        assert result.retries == 3
```

## Datenbank Integration

```python
# tests/integration/test_database.py
import pytest
from sqlalchemy import text

@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_connection(db_session):
    """Datenbank sollte erreichbar sein."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_crud(db_session):
    """CRUD Operationen sollten funktionieren."""
    from app.db.models import Document

    # Create
    doc = Document(filename="test.pdf", content_type="application/pdf")
    db_session.add(doc)
    await db_session.commit()

    # Read
    fetched = await db_session.get(Document, doc.id)
    assert fetched.filename == "test.pdf"

    # Update
    fetched.extracted_text = "Test Text"
    await db_session.commit()

    # Delete
    await db_session.delete(fetched)
    await db_session.commit()

    assert await db_session.get(Document, doc.id) is None
```

## End-to-End Workflow

```python
# tests/integration/test_e2e_workflow.py
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_document_workflow(client, sample_pdf):
    """Vollstaendiger Workflow: Upload -> OCR -> Export."""

    # 1. Upload
    files = {"file": ("german_doc.pdf", sample_pdf, "application/pdf")}
    response = await client.post("/api/v1/documents/", files=files)
    assert response.status_code == 201
    doc_id = response.json()["id"]

    # 2. OCR starten
    response = await client.post(f"/api/v1/ocr/{doc_id}/process")
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # 3. Warten auf Completion
    import asyncio
    for _ in range(30):
        response = await client.get(f"/api/v1/jobs/{job_id}")
        if response.json()["status"] == "completed":
            break
        await asyncio.sleep(1)

    assert response.json()["status"] == "completed"

    # 4. Ergebnis abrufen
    response = await client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200
    assert "extracted_text" in response.json()

    # 5. Export
    response = await client.get(f"/api/v1/documents/{doc_id}/export?format=json")
    assert response.status_code == 200
```

## Test-Daten

```
tests/fixtures/
├── sample_german.pdf       # Deutsches Dokument mit Umlauten
├── sample_table.pdf        # PDF mit Tabellen
├── sample_fraktur.pdf      # Fraktur-Schrift
├── sample_invoice.pdf      # Rechnung
└── sample_contract.pdf     # Vertrag
```

## Markers

```python
@pytest.mark.integration    # Integration Test
@pytest.mark.slow           # Langsamer Test (>30s)
@pytest.mark.database       # Braucht echte DB
@pytest.mark.celery         # Braucht Celery Worker
```

## Debugging

```bash
# Verbose mit Logs
docker-compose exec backend pytest tests/integration/ -v -s --log-cli-level=DEBUG

# Einzelner Test
docker-compose exec backend pytest tests/integration/api/test_documents.py::test_document_upload -v
```
