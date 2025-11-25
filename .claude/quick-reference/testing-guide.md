# Testing Quick Reference

## 🧪 Running Tests

### Basic Commands
```bash
# Using Makefile (recommended)
make test                         # All tests
make test-cov                     # With coverage report
make test-unit                    # Unit tests only (fast)
make test-gpu                     # GPU tests only

# Using script
./scripts/test.sh                 # All tests
./scripts/test.sh --coverage      # With coverage
./scripts/test.sh --gpu           # GPU tests
./scripts/test.sh --parallel      # Parallel execution
./scripts/test.sh --verbose       # Verbose output

# Direct pytest
pytest                            # All tests
pytest tests/unit/                # Unit tests only
pytest tests/integration/         # Integration tests only
pytest -v                         # Verbose
pytest -x                         # Stop on first failure
pytest -k "test_document"         # Run tests matching name
```

### Test Markers
```bash
# By marker
pytest -m unit                    # Unit tests
pytest -m integration             # Integration tests
pytest -m gpu                     # GPU tests
pytest -m "not gpu"               # Skip GPU tests
pytest -m "not integration and not gpu"  # Fast tests only
pytest -m slow                    # Long-running tests

# Combine markers
pytest -m "unit and not slow"
pytest -m "integration or gpu"
```

### Coverage Reports
```bash
# HTML report (detailed)
pytest --cov=app --cov-report=html
# Open: htmlcov/index.html

# Terminal report
pytest --cov=app --cov-report=term-missing

# Both
pytest --cov=app --cov-report=html --cov-report=term

# JSON (for CI/CD)
pytest --cov=app --cov-report=json
```

## ✍️ Writing Tests

### Test Structure (AAA Pattern)
```python
import pytest

@pytest.mark.asyncio
async def test_ocr_processes_document_successfully():
    """OCR sollte Dokument erfolgreich verarbeiten."""
    # Arrange (Setup)
    document = create_test_document()
    ocr_service = OCRService()

    # Act (Execute)
    result = await ocr_service.process(document)

    # Assert (Verify)
    assert result.success is True
    assert result.text is not None
    assert len(result.text) > 0
```

### Test Naming Convention
```python
# ✅ GOOD: Clear, descriptive names
def test_document_upload_succeeds_with_valid_pdf():
    pass

def test_ocr_returns_error_when_gpu_unavailable():
    pass

def test_user_cannot_access_others_documents():
    pass

# ❌ BAD: Vague names
def test_upload():
    pass

def test_1():
    pass

def test_case_a():
    pass
```

### Async Tests
```python
import pytest

# Async test (MANDATORY for async code)
@pytest.mark.asyncio
async def test_async_ocr_processing():
    result = await ocr_service.process_async(document)
    assert result is not None

# Sync test
def test_sync_validation():
    result = validator.validate(text)
    assert result is True
```

### Test Markers (Categorization)
```python
import pytest

# Unit test
@pytest.mark.unit
def test_text_validation():
    pass

# Integration test
@pytest.mark.integration
async def test_database_connection():
    pass

# GPU test
@pytest.mark.gpu
def test_cuda_processing():
    pass

# Slow test
@pytest.mark.slow
async def test_full_document_pipeline():
    pass

# Multiple markers
@pytest.mark.integration
@pytest.mark.slow
async def test_batch_processing_1000_documents():
    pass
```

## 🎭 Fixtures & Mocking

### Basic Fixtures
```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture
async def db_session():
    """Provide clean database session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    await engine.dispose()

@pytest.fixture
def sample_document():
    """Load sample document for testing."""
    return {
        "id": "test-doc-1",
        "content": "Test content",
        "language": "de"
    }

# Usage
async def test_document_creation(db_session, sample_document):
    doc = Document(**sample_document)
    db_session.add(doc)
    await db_session.commit()
    assert doc.id == "test-doc-1"
```

### Mocking
```python
from unittest.mock import Mock, AsyncMock, patch

# Mock object
@pytest.mark.asyncio
async def test_ocr_with_mock():
    mock_gpu = Mock()
    mock_gpu.process.return_value = "Extracted text"

    service = OCRService(gpu=mock_gpu)
    result = service.process(document)

    mock_gpu.process.assert_called_once()
    assert result == "Extracted text"

# Async mock
@pytest.mark.asyncio
async def test_async_service_with_mock():
    mock_service = AsyncMock()
    mock_service.process.return_value = {"status": "success"}

    result = await mock_service.process(doc_id="123")

    mock_service.process.assert_called_with(doc_id="123")

# Patch decorator
@patch('app.services.ocr_service.GPUManager')
def test_ocr_fallback_to_cpu(mock_gpu_manager):
    mock_gpu_manager.return_value.is_available.return_value = False

    service = OCRService()
    assert service.use_cpu is True
```

### Parametrized Tests
```python
import pytest

@pytest.mark.parametrize("input_text,expected", [
    ("Müller", True),
    ("Größe", True),
    ("Straße", True),
    ("cafe", True),     # Valid without umlauts
    ("", False),        # Empty string
])
def test_german_text_validation(input_text, expected):
    result = validate_german_text(input_text)
    assert result == expected

# Multiple parameters
@pytest.mark.parametrize("backend,expected_accuracy", [
    ("deepseek", 0.98),
    ("got_ocr", 0.95),
    ("surya", 0.92),
])
async def test_ocr_backend_accuracy(backend, expected_accuracy):
    service = OCRService(backend=backend)
    result = await service.process(test_document)
    assert result.accuracy >= expected_accuracy
```

## 🚨 Testing Best Practices

### Do's ✅
```python
# 1. Test one thing per test
def test_document_upload_creates_database_entry():
    # Test only database creation, not OCR processing
    pass

# 2. Use descriptive assertions
assert result.status == "success", f"Expected success but got {result.status}"

# 3. Clean up resources
@pytest.fixture
async def temp_file():
    file_path = create_temp_file()
    yield file_path
    os.remove(file_path)  # Cleanup

# 4. Use fixtures for setup
def test_with_fixture(db_session, sample_document):
    # Setup handled by fixtures
    pass

# 5. Test edge cases
def test_handles_empty_document():
    pass

def test_handles_very_large_document():
    pass

def test_handles_invalid_encoding():
    pass
```

### Don'ts ❌
```python
# ❌ Testing multiple things
def test_document_upload_and_processing_and_storage():
    # Too broad - split into separate tests
    pass

# ❌ Depending on test order
def test_step_1():
    global state
    state = "initialized"

def test_step_2():  # Breaks if test_step_1 doesn't run first
    assert state == "initialized"

# ❌ Hard-coded paths/URLs
def test_upload():
    file = open("/home/user/test.pdf")  # BAD!
    # Use fixtures or Path(__file__).parent / "test.pdf"

# ❌ No assertions
def test_something():
    result = do_something()
    # Forgot to assert!

# ❌ Too broad exception catching
def test_error_handling():
    with pytest.raises(Exception):  # Too broad!
        # Should be pytest.raises(SpecificException)
        pass
```

## 🎯 Test Coverage Goals

### Minimum Requirements
- **Overall Coverage**: 80%
- **Critical Paths**: 95%+ (OCR pipeline, auth, data persistence)
- **New Code**: 100% (no exceptions)

### Check Coverage
```bash
# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html  # macOS
start htmlcov/index.html # Windows
xdg-open htmlcov/index.html # Linux

# Terminal output shows:
# - Overall percentage
# - Missing lines (with line numbers)
```

### Coverage by Module
```bash
# Specific module
pytest --cov=app.services.ocr_service --cov-report=term-missing

# Multiple modules
pytest --cov=app.services --cov=app.api --cov-report=html
```

## 🔍 Debugging Tests

### Verbose Output
```bash
# Increase verbosity
pytest -v                         # Verbose
pytest -vv                        # Very verbose
pytest -vvv                       # Extremely verbose

# Show print statements
pytest -s                         # Don't capture stdout
pytest -v -s                      # Verbose + stdout

# Show locals on failure
pytest -l                         # Show local variables
pytest --tb=short                 # Short traceback
pytest --tb=long                  # Long traceback
```

### Debug Specific Test
```bash
# Run single test
pytest tests/unit/test_ocr.py::test_deepseek_backend

# Debug with pdb
pytest --pdb                      # Drop into debugger on failure
pytest --pdb-trace                # Drop into debugger at start

# VSCode debugging
# F5 → "pytest: Debug Current File"
# Or set breakpoint and run test
```

### Test Output
```bash
# Capture warnings
pytest -W error                   # Treat warnings as errors
pytest -W ignore                  # Ignore warnings

# Show durations
pytest --durations=10             # Show 10 slowest tests
pytest --durations=0              # Show all test durations
```

## 🏃 Performance Testing

### Timing Tests
```python
import time

def test_ocr_performance():
    start = time.time()
    result = ocr_service.process(document)
    duration = time.time() - start

    assert duration < 2.0, f"Processing took {duration}s, expected <2s"

# Using pytest benchmark
@pytest.mark.benchmark
def test_ocr_benchmark(benchmark):
    result = benchmark(ocr_service.process, document)
    assert result is not None
```

### Load Testing (Manual)
```python
import asyncio

@pytest.mark.slow
@pytest.mark.asyncio
async def test_concurrent_ocr_processing():
    """Test 100 concurrent OCR requests."""
    documents = [create_test_document() for _ in range(100)]

    start = time.time()
    results = await asyncio.gather(
        *[ocr_service.process(doc) for doc in documents]
    )
    duration = time.time() - start

    assert all(r.success for r in results)
    assert duration < 30.0  # 100 docs in <30s
```

## 🔬 Test Data Management

### Test Fixtures Location
```
tests/
├── fixtures/
│   ├── documents/
│   │   ├── sample_invoice.pdf
│   │   ├── sample_receipt.pdf
│   │   └── sample_german_text.pdf
│   ├── images/
│   │   └── test_image.png
│   └── data/
│       └── expected_results.json
└── conftest.py  # Shared fixtures
```

### Loading Test Data
```python
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_pdf():
    """Load sample PDF for testing."""
    pdf_path = FIXTURES_DIR / "documents" / "sample_invoice.pdf"
    return pdf_path.read_bytes()

@pytest.fixture
def expected_ocr_result():
    """Load expected OCR results."""
    json_path = FIXTURES_DIR / "data" / "expected_results.json"
    return json.loads(json_path.read_text())
```

## 🎪 Integration Testing

### Database Tests
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_crud(db_session):
    """Test full CRUD cycle for documents."""
    # Create
    doc = Document(id="test-1", content="Test")
    db_session.add(doc)
    await db_session.commit()

    # Read
    result = await db_session.execute(
        select(Document).where(Document.id == "test-1")
    )
    retrieved = result.scalar_one()
    assert retrieved.content == "Test"

    # Update
    retrieved.content = "Updated"
    await db_session.commit()

    # Delete
    await db_session.delete(retrieved)
    await db_session.commit()
```

### API Tests
```python
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upload_api():
    """Test complete document upload workflow."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Upload
        files = {"file": ("test.pdf", sample_pdf, "application/pdf")}
        response = await client.post("/api/v1/documents/", files=files)

        assert response.status_code == 201
        doc_id = response.json()["id"]

        # Retrieve
        response = await client.get(f"/api/v1/documents/{doc_id}")
        assert response.status_code == 200
        assert response.json()["id"] == doc_id
```

## 📊 CI/CD Testing

### GitHub Actions Example
```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint
        run: |
          ruff check .
          mypy app/

      - name: Run tests
        run: pytest --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          file: ./coverage.xml
```

## 🆘 Common Test Issues

### Issue: Tests pass locally, fail in CI
```bash
# Check for:
# 1. Environment differences
pytest --verbose  # Shows environment details

# 2. Timezone issues
import os
os.environ['TZ'] = 'UTC'  # Set consistent timezone

# 3. Random data
import random
random.seed(42)  # Fix random seed for reproducibility
```

### Issue: Flaky tests (intermittent failures)
```python
# Solution 1: Add retries
@pytest.mark.flaky(reruns=3)
def test_unreliable_external_api():
    pass

# Solution 2: Increase timeouts
@pytest.mark.timeout(10)  # 10 second timeout
async def test_slow_operation():
    pass

# Solution 3: Mock external dependencies
@patch('app.services.external_api.call')
def test_with_mock(mock_call):
    mock_call.return_value = {"status": "success"}
    # Now deterministic!
```

### Issue: Slow tests
```bash
# Find slow tests
pytest --durations=20

# Run in parallel
pytest -n auto  # Uses all CPU cores
pytest -n 4     # Use 4 processes

# Skip slow tests
pytest -m "not slow"
```

---

**Remember**: Tests are documentation! Write clear, descriptive tests that explain what the code should do.

**Coverage Goal**: Aim for 100% on new code, 80%+ overall.

**Test Philosophy**: If it can break, test it. If it's critical, test it thoroughly.
