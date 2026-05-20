---
name: test-unit
description: Unit Tests fuer das Ablage-System schreiben und ausfuehren. Nutze diesen Skill fuer pytest, Fixtures, Mocking von OCR/GPU, Coverage-Reports und Test-Patterns. Alle Tests laufen in Docker!
---

# Unit Testing (Ablage-System)

Unit Tests isoliert in Docker ausfuehren.

## Quick Commands

```bash
# Alle Unit Tests
docker-compose exec backend pytest tests/unit/ -v

# Mit Coverage
docker-compose exec backend pytest tests/unit/ --cov=app --cov-report=html

# Einzelne Datei
docker-compose exec backend pytest tests/unit/services/test_ocr_service.py -v

# Pattern-Matching
docker-compose exec backend pytest -k "test_german" -v
```

## Test-Struktur

```
tests/
├── unit/
│   ├── conftest.py          # Gemeinsame Fixtures
│   ├── api/
│   │   └── test_documents.py
│   ├── services/
│   │   ├── test_ocr_service.py
│   │   └── test_document_service.py
│   └── utils/
│       └── test_german_text.py
├── integration/              # Siehe /test-integration
└── performance/              # Siehe /test-performance
```

## Fixtures (conftest.py)

```python
# tests/unit/conftest.py
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_db():
    """Mock Datenbank-Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db

@pytest.fixture
def mock_gpu():
    """Mock GPU fuer Tests ohne echte GPU."""
    import torch
    torch.cuda.is_available = Mock(return_value=True)
    torch.cuda.get_device_name = Mock(return_value="Mock RTX 4080")
    return torch

@pytest.fixture
def sample_document():
    """Test-Dokument."""
    return {
        "id": "test-123",
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "language": "de"
    }

@pytest.fixture
def sample_german_text():
    """Deutscher Text mit Umlauten."""
    return "Größe der Übertragung mit äußerster Sorgfalt prüfen"
```

## Test-Pattern: Service Tests

```python
# tests/unit/services/test_ocr_service.py
import pytest
from unittest.mock import Mock, patch
from app.services.ocr.orchestrator import OCROrchestrator

class TestOCROrchestrator:
    """Tests fuer OCR Orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        return OCROrchestrator()

    def test_select_backend_german_document(self, orchestrator):
        """DeepSeek sollte fuer deutsche Dokumente gewaehlt werden."""
        doc = Mock(language="de", has_tables=False)

        backend = orchestrator.select_backend(doc)

        assert backend == "deepseek"

    def test_select_backend_complex_layout(self, orchestrator):
        """DeepSeek sollte fuer komplexe Layouts gewaehlt werden."""
        doc = Mock(language="en", has_tables=True, has_images=True)

        backend = orchestrator.select_backend(doc)

        assert backend == "deepseek"

    @patch('torch.cuda.is_available', return_value=False)
    def test_fallback_to_cpu(self, mock_cuda, orchestrator):
        """Surya sollte ohne GPU gewaehlt werden."""
        doc = Mock(language="en", has_tables=False)

        backend = orchestrator.select_backend(doc)

        assert backend == "surya"
```

## Test-Pattern: API Tests

```python
# tests/unit/api/test_documents.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_upload_document_success(mock_db):
    """Dokument-Upload sollte 201 zurueckgeben."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        files = {"file": ("test.pdf", b"PDF content", "application/pdf")}

        response = await client.post("/api/v1/documents/", files=files)

        assert response.status_code == 201
        assert "id" in response.json()

@pytest.mark.asyncio
async def test_upload_invalid_format():
    """Ungueltiges Format sollte 400 zurueckgeben."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        files = {"file": ("test.exe", b"EXE content", "application/octet-stream")}

        response = await client.post("/api/v1/documents/", files=files)

        assert response.status_code == 400
        assert "Dateityp nicht unterstuetzt" in response.json()["nachricht"]
```

## Test-Pattern: German Text

```python
# tests/unit/utils/test_german_text.py
import pytest
from app.utils.german_text import normalize_german_text, validate_umlauts

class TestGermanText:
    """Tests fuer deutsche Textverarbeitung."""

    @pytest.mark.parametrize("input_text,expected", [
        ("Größe", "Größe"),
        ("Groesse", "Größe"),  # Korrektur
        ("Äpfel", "Äpfel"),
        ("Straße", "Straße"),
    ])
    def test_normalize_umlauts(self, input_text, expected):
        """Umlaute sollten korrekt normalisiert werden."""
        result = normalize_german_text(input_text)
        assert result == expected

    def test_validate_umlauts_correct(self):
        """Korrekte Umlaute sollten validiert werden."""
        text = "Größe der Übertragung"
        assert validate_umlauts(text) == True

    def test_validate_umlauts_suspicious(self):
        """Verdaechtige Muster sollten erkannt werden."""
        text = "Groesse der Uebertragung"
        assert validate_umlauts(text) == False
```

## Mocking OCR Backends

```python
@pytest.fixture
def mock_deepseek():
    """Mock DeepSeek OCR."""
    with patch('app.services.ocr.deepseek.DeepSeekOCR') as mock:
        instance = mock.return_value
        instance.process = AsyncMock(return_value={
            "text": "Erkannter Text mit Ümlauten",
            "confidence": 0.95,
            "processing_time_ms": 150
        })
        yield instance

@pytest.fixture
def mock_got_ocr():
    """Mock GOT-OCR."""
    with patch('app.services.ocr.got_ocr.GOTOCR') as mock:
        instance = mock.return_value
        instance.process = AsyncMock(return_value={
            "text": "Erkannter Text",
            "confidence": 0.90,
            "processing_time_ms": 80
        })
        yield instance
```

## Coverage-Ziele

| Bereich | Minimum | Kritisch |
|---------|---------|----------|
| Overall | 80% | - |
| OCR Pipeline | 95% | Ja |
| API Endpoints | 90% | Ja |
| Authentication | 95% | Ja |
| Utils | 85% | - |

## Coverage-Report

```bash
# HTML Report generieren
docker-compose exec backend pytest --cov=app --cov-report=html

# Report oeffnen
# Siehe: htmlcov/index.html

# Terminal Report
docker-compose exec backend pytest --cov=app --cov-report=term-missing
```

## Markers

```python
# pytest.ini oder pyproject.toml
[pytest]
markers =
    unit: Unit Tests
    slow: Langsame Tests (>5s)
    gpu: Tests die GPU benoetigen

# Nutzung
@pytest.mark.unit
def test_example():
    pass

@pytest.mark.gpu
@pytest.mark.skipif(not torch.cuda.is_available(), reason="GPU required")
def test_gpu_processing():
    pass
```

## Debugging Tests

```bash
# Mit Print-Output
docker-compose exec backend pytest -v -s tests/unit/

# Nur fehlgeschlagene
docker-compose exec backend pytest --lf

# Stoppen bei erstem Fehler
docker-compose exec backend pytest -x

# Debugging mit pdb
docker-compose exec backend pytest --pdb
```
