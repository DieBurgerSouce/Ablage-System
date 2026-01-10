# Testing Requirements

## Coverage Standards

| Category | Minimum Coverage |
|----------|------------------|
| Overall | 80% |
| Critical Paths (OCR, Auth, DB) | 95%+ |
| New Code | 100% before merge |

## Unit Tests

```python
# tests/unit/services/test_ocr_orchestrator.py
import pytest
from unittest.mock import Mock, AsyncMock
from app.services.ocr.orchestrator import OCROrchestrator

@pytest.mark.asyncio
async def test_backend_selection_deepseek_for_complex_layout():
    """DeepSeek sollte fuer komplexe Layouts ausgewaehlt werden."""
    orchestrator = OCROrchestrator()

    # Mock document with complex layout
    doc = Mock(has_tables=True, has_images=True, language="de")

    backend = await orchestrator.select_backend(doc)

    assert backend == "deepseek"
    assert orchestrator.last_selection_reason == "complex_layout"

# CORRECT: Clear test names in German or English
# WRONG: Vague names like test_1(), test_case_a()
```

## Integration Tests

```python
# tests/integration/test_ocr_pipeline.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upload_and_processing_end_to_end():
    """Vollstaendiger Workflow: Upload -> OCR -> Speicherung."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Upload document
        files = {"file": ("test.pdf", open("tests/fixtures/sample_de.pdf", "rb"))}
        response = await client.post("/api/v1/documents/", files=files)
        assert response.status_code == 201
        doc_id = response.json()["id"]

        # Start OCR processing
        response = await client.post(f"/api/v1/ocr/{doc_id}/process")
        assert response.status_code == 202

        # Verify extracted text
        response = await client.get(f"/api/v1/documents/{doc_id}")
        assert "extracted_text" in response.json()
        assert len(response.json()["extracted_text"]) > 0
```

## GPU Tests

```python
@pytest.mark.gpu
@pytest.mark.skipif(not torch.cuda.is_available(), reason="GPU not available")
def test_gpu_batch_processing_memory_efficiency():
    """GPU-Batch-Verarbeitung sollte unter 85% VRAM bleiben."""
    import torch
    from app.services.ocr.deepseek import DeepSeekOCR

    ocr = DeepSeekOCR()
    images = load_test_images(count=32)  # Large batch

    torch.cuda.reset_peak_memory_stats()
    results = ocr.process_batch(images)
    peak_memory = torch.cuda.max_memory_allocated() / 1024**3  # GB

    assert peak_memory < 13.6  # 85% of 16GB
    assert len(results) == 32
```

## Testing Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test category
pytest -m unit            # Unit tests only
pytest -m integration     # Integration tests
pytest -m gpu             # GPU tests (requires GPU)

# Run tests in parallel
pytest -n auto

# Run specific test file
pytest tests/unit/services/test_ocr_orchestrator.py -v

# Run tests matching pattern
pytest -k "test_deepseek" -v
```

## Test Fixtures

Define in `tests/conftest.py`:
- `db_session`: Async SQLite in-memory
- `sample_german_document`: PDF bytes for testing
- `mock_ocr_backend`: Mocked OCR service
- `authenticated_client`: HTTP client with auth headers

## Test Categories (pytest markers)

| Marker | Description |
|--------|-------------|
| `@pytest.mark.unit` | Unit tests (fast, isolated) |
| `@pytest.mark.integration` | Integration tests |
| `@pytest.mark.gpu` | GPU-required tests |
| `@pytest.mark.slow` | Long-running tests |
| `@pytest.mark.asyncio` | Async tests |
