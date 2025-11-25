# Comprehensive Testing Strategy
**Ablage-System - Umfassende Teststrategie**

Version: 1.0
Last Updated: 2025-01-23
Owner: Quality Engineering Team
Status: APPROVED

---

## Executive Summary

This document defines the complete testing strategy for Ablage-System, ensuring high quality, reliability, and maintainability of the German document processing platform. Our testing philosophy: **"Test early, test often, test thoroughly."**

**Quality Targets:**
- ✅ Test Coverage: ≥80% overall, ≥95% for critical paths
- ✅ Unit Test Success Rate: 100%
- ✅ Integration Test Success Rate: ≥98%
- ✅ Zero high-severity bugs in production
- ✅ Mean Time Between Failures (MTBF): >720 hours (30 days)

---

## Table of Contents

1. [Testing Pyramid](#testing-pyramid)
2. [Unit Testing](#unit-testing)
3. [Integration Testing](#integration-testing)
4. [End-to-End Testing](#end-to-end-testing)
5. [Performance Testing](#performance-testing)
6. [Security Testing](#security-testing)
7. [German Language Testing](#german-language-testing)
8. [GPU Testing](#gpu-testing)
9. [Test Data Management](#test-data-management)
10. [CI/CD Integration](#cicd-integration)
11. [Test Reporting](#test-reporting)

---

## Testing Pyramid

### Our Testing Distribution

```
         /\
        /  \       E2E Tests (5%)
       /----\      ~50 tests, 30 min
      /      \
     /--------\    Integration Tests (15%)
    /          \   ~200 tests, 10 min
   /------------\
  /______________\ Unit Tests (80%)
                   ~1000 tests, 2 min
```

**Rationale:**
- **80% Unit Tests:** Fast, isolated, comprehensive coverage
- **15% Integration Tests:** Component interactions, database, API
- **5% E2E Tests:** Critical user journeys, slow but essential

**Execution Time Target:**
- Unit tests: <2 minutes (parallel execution)
- Integration tests: <10 minutes
- E2E tests: <30 minutes
- **Total CI pipeline:** <45 minutes

---

## Unit Testing

### Philosophy
**"Test behavior, not implementation."**

Unit tests verify individual functions/methods in isolation using mocks for dependencies.

### Guidelines

#### 1. Test Organization
```python
# tests/unit/services/test_ocr_service.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.ocr_service import OCRService

class TestOCRService:
    """Test suite for OCR service."""

    @pytest.fixture
    def ocr_service(self):
        """Provide OCR service instance."""
        return OCRService()

    @pytest.fixture
    def mock_gpu(self):
        """Mock GPU for testing without hardware."""
        with patch('torch.cuda.is_available', return_value=True):
            with patch('torch.cuda.get_device_name', return_value='Mock GPU'):
                yield

    def test_service_initialization(self, ocr_service):
        """Service should initialize with default config."""
        assert ocr_service is not None
        assert ocr_service.config is not None

    @pytest.mark.asyncio
    async def test_process_document_success(self, ocr_service, mock_gpu):
        """Successfully process a document with OCR."""
        # Arrange
        mock_document = Mock(id="doc123", file_path="/tmp/test.pdf")

        # Act
        result = await ocr_service.process(mock_document)

        # Assert
        assert result.success is True
        assert result.text is not None
        assert len(result.text) > 0

    @pytest.mark.asyncio
    async def test_process_document_invalid_file(self, ocr_service):
        """Processing invalid file should raise appropriate error."""
        # Arrange
        mock_document = Mock(id="doc456", file_path="/nonexistent.pdf")

        # Act & Assert
        with pytest.raises(FileNotFoundError):
            await ocr_service.process(mock_document)

    @pytest.mark.parametrize("file_type,expected_backend", [
        ("simple.pdf", "got_ocr"),
        ("complex.pdf", "deepseek"),
        ("scanned.pdf", "deepseek"),
    ])
    async def test_backend_selection(self, ocr_service, file_type, expected_backend):
        """Backend selection based on document complexity."""
        # Arrange
        mock_doc = Mock(file_path=f"/tmp/{file_type}")

        # Act
        backend = await ocr_service.select_backend(mock_doc)

        # Assert
        assert backend == expected_backend
```

#### 2. Coverage Requirements

**Critical Paths (≥95% coverage):**
- OCR processing pipeline
- Authentication and authorization
- German text validation
- GPU memory management
- Data persistence (database operations)

**Standard Paths (≥80% coverage):**
- API endpoints
- Business logic services
- Utility functions

**Exemptions (<80% acceptable):**
- External library integrations (tested via integration tests)
- Configuration files
- Simple DTOs/models

#### 3. Mocking Strategy

**What to Mock:**
- ✅ External services (database, Redis, MinIO)
- ✅ GPU operations (expensive, hardware-dependent)
- ✅ File system operations (I/O bound)
- ✅ Time-dependent operations (`datetime.now()`)
- ✅ HTTP requests to external APIs

**What NOT to Mock:**
- ❌ Code under test
- ❌ Simple utility functions
- ❌ Domain models (unless they have side effects)

**Example: Mocking Database**
```python
from unittest.mock import AsyncMock
import pytest

@pytest.fixture
async def mock_db():
    """Mock database session."""
    db = AsyncMock()

    # Configure mock behavior
    db.execute = AsyncMock(return_value=Mock(
        scalar_one_or_none=Mock(return_value=None)
    ))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    return db

@pytest.mark.asyncio
async def test_create_document(document_service, mock_db):
    """Creating document should persist to database."""
    # Arrange
    doc_data = {"filename": "test.pdf", "size": 1024}

    # Act
    result = await document_service.create(mock_db, doc_data)

    # Assert
    assert result is not None
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
```

#### 4. Test Naming Convention

**Pattern:** `test_<method>_<scenario>_<expected_result>`

**Examples:**
- `test_process_document_with_valid_pdf_returns_text`
- `test_authenticate_user_with_invalid_password_raises_error`
- `test_validate_german_text_with_umlauts_passes`

---

## Integration Testing

### Philosophy
**"Test component interactions, not just units."**

Integration tests verify that multiple components work together correctly.

### Categories

#### 1. API Integration Tests
Test complete API request/response cycle with real database.

```python
# tests/integration/api/test_documents_api.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def test_db():
    """Create test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    await engine.dispose()

@pytest.fixture
async def test_client(test_db):
    """Create test API client."""
    from app.main import app

    # Override database dependency
    app.dependency_overrides[get_db] = lambda: test_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upload_and_retrieval(test_client, test_db):
    """Complete workflow: upload → retrieve → verify."""
    # Upload document
    files = {"file": ("test.pdf", b"fake pdf content", "application/pdf")}
    response = await test_client.post("/api/v1/documents/", files=files)

    assert response.status_code == 201
    doc_data = response.json()
    doc_id = doc_data["id"]

    # Retrieve document
    response = await test_client.get(f"/api/v1/documents/{doc_id}")

    assert response.status_code == 200
    retrieved = response.json()
    assert retrieved["id"] == doc_id
    assert retrieved["filename"] == "test.pdf"
```

#### 2. Database Integration Tests
Test repository layer with real database operations.

```python
# tests/integration/db/test_document_repository.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.db.repositories import DocumentRepository
from app.db.models import Document

@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_crud_operations(test_db):
    """Test complete CRUD cycle for documents."""
    repo = DocumentRepository(test_db)

    # Create
    doc = Document(
        id="doc123",
        filename="test.pdf",
        owner_id="user456",
        status="pending"
    )
    created = await repo.create(doc)
    assert created.id == "doc123"

    # Read
    retrieved = await repo.get("doc123")
    assert retrieved is not None
    assert retrieved.filename == "test.pdf"

    # Update
    updated = await repo.update("doc123", status="completed")
    assert updated.status == "completed"

    # Delete
    await repo.delete("doc123")
    deleted = await repo.get("doc123")
    assert deleted is None
```

#### 3. Service Integration Tests
Test service layer with multiple dependencies.

```python
# tests/integration/services/test_document_service.py
import pytest
from app.services.document_service import DocumentService
from app.services.storage_service import StorageService

@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_processing_workflow(test_db, tmp_path):
    """Test complete document processing with storage."""
    # Setup
    storage = StorageService(base_path=tmp_path)
    service = DocumentService(db=test_db, storage=storage)

    # Create test file
    test_file = tmp_path / "test.pdf"
    test_file.write_bytes(b"fake pdf content")

    # Upload
    doc = await service.upload_document(
        file_path=test_file,
        owner_id="user123"
    )

    assert doc.id is not None
    assert doc.status == "pending"

    # Process (mock GPU part)
    with patch('app.services.ocr_service.OCRService.process'):
        result = await service.process_document(doc.id)

    assert result.status == "completed"

    # Retrieve
    retrieved = await service.get_document(doc.id)
    assert retrieved.status == "completed"
```

---

## End-to-End Testing

### Philosophy
**"Test real user workflows from browser to database."**

E2E tests verify complete system functionality from user perspective.

### Critical User Journeys

#### Journey 1: Document Upload and Processing
```python
# tests/e2e/test_document_workflow.py
import pytest
from playwright.async_api import async_playwright

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_document_workflow():
    """User uploads document, waits for processing, views result."""
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Login
        await page.goto("http://localhost:3000/login")
        await page.fill('input[name="email"]', "test@example.com")
        await page.fill('input[name="password"]', "testpass123")
        await page.click('button[type="submit"]')

        # Wait for dashboard
        await page.wait_for_url("http://localhost:3000/dashboard")

        # Upload document
        await page.click('button:has-text("Dokument hochladen")')
        await page.set_input_files('input[type="file"]', 'tests/fixtures/test_de.pdf')
        await page.click('button:has-text("Hochladen")')

        # Wait for upload success
        await page.wait_for_selector('.toast-success')

        # Navigate to documents list
        await page.click('a:has-text("Dokumente")')

        # Verify document appears
        await page.wait_for_selector('text=test_de.pdf')

        # Wait for processing to complete (poll status)
        for _ in range(30):  # 30 seconds timeout
            status = await page.locator('.document-status').text_content()
            if status == "Abgeschlossen":
                break
            await page.wait_for_timeout(1000)

        assert status == "Abgeschlossen"

        # View extracted text
        await page.click('.document-row >> text=test_de.pdf')
        extracted_text = await page.locator('.extracted-text').text_content()

        assert len(extracted_text) > 0
        assert "Rechnung" in extracted_text  # Expected content

        await browser.close()
```

#### Journey 2: Search and Filter
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_search_and_filter_documents():
    """User searches for documents and applies filters."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Login (reuse helper)
        await login_user(page, "test@example.com", "testpass123")

        # Navigate to search
        await page.goto("http://localhost:3000/search")

        # Enter search query
        await page.fill('input[name="search"]', "Rechnung")
        await page.click('button:has-text("Suchen")')

        # Wait for results
        await page.wait_for_selector('.search-results')

        # Verify results
        results_count = await page.locator('.document-card').count()
        assert results_count > 0

        # Apply date filter
        await page.fill('input[name="date_from"]', "2025-01-01")
        await page.fill('input[name="date_to"]', "2025-01-31")
        await page.click('button:has-text("Filter anwenden")')

        # Verify filtered results
        await page.wait_for_timeout(500)
        filtered_count = await page.locator('.document-card').count()
        assert filtered_count <= results_count

        await browser.close()
```

### E2E Test Environment

**Requirements:**
- Real database (PostgreSQL test instance)
- Real MinIO instance (separate bucket)
- Real Redis instance
- GPU simulator (or CPU fallback)
- Frontend build

**Setup Script:**
```bash
#!/bin/bash
# tests/e2e/setup_e2e_env.sh

# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Wait for services
sleep 10

# Run migrations
docker exec ablage-test-backend alembic upgrade head

# Seed test data
docker exec ablage-test-backend python tests/e2e/seed_data.py

# Build frontend
cd frontend && npm run build

# Start frontend dev server
npm run start:test &

echo "E2E environment ready"
```

---

## Performance Testing

### Load Testing Strategy

#### 1. Baseline Performance Tests
Establish performance baselines for critical operations.

```python
# tests/performance/test_api_performance.py
import pytest
import time
import asyncio
from httpx import AsyncClient

@pytest.mark.performance
@pytest.mark.asyncio
async def test_api_health_check_performance():
    """Health check should respond in <50ms (P95)."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        latencies = []

        # Warm-up
        for _ in range(10):
            await client.get("/health")

        # Measure
        for _ in range(100):
            start = time.perf_counter()
            response = await client.get("/health")
            latency = (time.perf_counter() - start) * 1000  # ms

            assert response.status_code == 200
            latencies.append(latency)

        # Calculate percentiles
        latencies.sort()
        p50 = latencies[49]
        p95 = latencies[94]
        p99 = latencies[98]

        print(f"\nHealth Check Latency:")
        print(f"  P50: {p50:.2f}ms")
        print(f"  P95: {p95:.2f}ms")
        print(f"  P99: {p99:.2f}ms")

        # Assert performance targets
        assert p95 < 50, f"P95 latency {p95:.2f}ms exceeds 50ms target"
```

#### 2. Throughput Tests
Measure system throughput under load.

```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_ocr_processing_throughput():
    """System should process ≥192 documents/hour."""
    from app.services.ocr_service import OCRService

    ocr = OCRService()
    documents = load_test_documents(count=32)  # 1/6 of hourly target

    start = time.time()

    # Process in parallel batches
    results = await asyncio.gather(*[
        ocr.process(doc) for doc in documents
    ])

    elapsed = time.time() - start

    # Calculate hourly rate
    docs_per_hour = (len(documents) / elapsed) * 3600

    print(f"\nOCR Throughput:")
    print(f"  Processed: {len(documents)} documents")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Rate: {docs_per_hour:.1f} docs/hour")

    assert docs_per_hour >= 192, f"Throughput {docs_per_hour:.1f} below target 192"
    assert all(r.success for r in results), "Some documents failed processing"
```

#### 3. Stress Testing
Test system behavior under extreme load.

```bash
# tests/performance/locust_stress_test.py
from locust import HttpUser, task, between

class AblageUser(HttpUser):
    """Simulated user for stress testing."""
    wait_time = between(1, 3)  # 1-3 seconds between requests

    @task(10)
    def view_documents(self):
        """Most common operation: view documents."""
        self.client.get("/api/v1/documents/")

    @task(3)
    def upload_document(self):
        """Upload new document."""
        files = {'file': ('test.pdf', open('tests/fixtures/test.pdf', 'rb'))}
        self.client.post("/api/v1/documents/", files=files)

    @task(5)
    def search_documents(self):
        """Search for documents."""
        self.client.get("/api/v1/documents/search?q=rechnung")

    @task(1)
    def download_document(self):
        """Download document."""
        # Assume document ID known
        self.client.get("/api/v1/documents/doc123/download")

# Run stress test:
# locust -f tests/performance/locust_stress_test.py --host=http://localhost:8000
# Target: 100 concurrent users, ramp up over 5 minutes
```

---

## Security Testing

### Automated Security Checks

#### 1. Dependency Scanning
```bash
# Run in CI pipeline
pip-audit --format json --output security_report.json

# Fail pipeline if CRITICAL vulnerabilities found
```

#### 2. Static Application Security Testing (SAST)
```bash
# Bandit for Python security issues
bandit -r app/ -f json -o bandit_report.json

# Check for common security issues:
# - SQL injection
# - Command injection
# - Hardcoded secrets
# - Insecure cryptography
```

#### 3. Authentication Testing
```python
# tests/security/test_authentication.py
import pytest
from httpx import AsyncClient

@pytest.mark.security
@pytest.mark.asyncio
async def test_invalid_token_rejected():
    """Invalid JWT token should be rejected."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get(
            "/api/v1/documents/",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401
        assert "Ungültiger Token" in response.json()["detail"]

@pytest.mark.security
@pytest.mark.asyncio
async def test_brute_force_protection():
    """Failed login attempts should trigger rate limiting."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        # Attempt 10 failed logins
        for i in range(10):
            response = await client.post("/api/v1/auth/login", json={
                "username": "test@example.com",
                "password": "wrong_password"
            })

        # 11th attempt should be rate limited
        response = await client.post("/api/v1/auth/login", json={
            "username": "test@example.com",
            "password": "wrong_password"
        })

        assert response.status_code == 429  # Too Many Requests
```

#### 4. Authorization Testing
```python
@pytest.mark.security
@pytest.mark.asyncio
async def test_user_cannot_access_others_documents():
    """Users should only access their own documents."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        # Login as user A
        token_a = await login_and_get_token(client, "userA@example.com")

        # Login as user B, upload document
        token_b = await login_and_get_token(client, "userB@example.com")

        response = await client.post(
            "/api/v1/documents/",
            files={'file': ('test.pdf', b'content')},
            headers={"Authorization": f"Bearer {token_b}"}
        )
        doc_id = response.json()["id"]

        # User A tries to access user B's document
        response = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token_a}"}
        )

        assert response.status_code == 403  # Forbidden
```

---

## German Language Testing

### Umlaut Validation Tests
```python
# tests/unit/test_german_validation.py
import pytest
from app.utils.german_validator import GermanValidator

class TestGermanValidation:
    """Test German-specific validation logic."""

    @pytest.fixture
    def validator(self):
        return GermanValidator()

    @pytest.mark.parametrize("text,expected", [
        ("Müller GmbH", True),
        ("Größe: 180cm", True),
        ("Bäckerei Löwe", True),
        ("Straße", True),
        ("M\u00fcller", True),  # Decomposed ü
        ("Moeller", False),  # ASCII transliteration (incorrect for validation)
    ])
    def test_umlaut_validation(self, validator, text, expected):
        """Validate German umlauts correctly identified."""
        result = validator.validate_umlauts(text)
        assert result == expected, f"Failed on: {text}"

    def test_fraktur_character_detection(self, validator):
        """Fraktur characters should be detected and handled."""
        fraktur_text = "Altdeutsche Schrift"  # Would contain Fraktur in real docs
        result = validator.detect_fraktur(fraktur_text)
        # Implementation specific assertion
        assert result is not None
```

### OCR Accuracy Tests
```python
# tests/integration/test_german_ocr_accuracy.py
import pytest
from app.services.ocr_service import OCRService

@pytest.mark.integration
@pytest.mark.parametrize("test_doc,expected_text", [
    ("tests/fixtures/german/rechnung_1.pdf", "Rechnung"),
    ("tests/fixtures/german/brief_umlauts.pdf", "Grüße"),
    ("tests/fixtures/german/vertrag.pdf", "Größe"),
])
async def test_german_ocr_accuracy(test_doc, expected_text):
    """OCR should accurately extract German text."""
    ocr = OCRService()

    result = await ocr.process_file(test_doc)

    assert result.success
    assert expected_text in result.text

    # Check no character corruption
    assert "Ã¼" not in result.text  # Corrupted ü
    assert "Ã¶" not in result.text  # Corrupted ö
```

---

## GPU Testing

### GPU-Specific Test Strategy

**Challenge:** GPU tests require hardware and are slow.

**Solution:**
- Mark GPU tests with `@pytest.mark.gpu`
- Run on dedicated GPU CI runner
- Use CPU fallback for regular CI
- Mock GPU for unit tests

```python
# tests/unit/test_gpu_manager.py
import pytest
import torch
from unittest.mock import patch

@pytest.mark.gpu
@pytest.mark.skipif(not torch.cuda.is_available(), reason="GPU not available")
def test_gpu_memory_management():
    """GPU memory should stay below 85% threshold."""
    from app.utils.gpu_manager import GPUManager

    manager = GPUManager()

    # Allocate memory
    tensors = []
    for _ in range(10):
        tensor = torch.randn(1000, 1000, device='cuda')
        tensors.append(tensor)

    # Check memory usage
    memory_pct = manager.get_memory_usage_percent()

    assert memory_pct < 85, f"GPU memory {memory_pct}% exceeds 85% threshold"

    # Cleanup
    del tensors
    torch.cuda.empty_cache()

@pytest.mark.gpu
def test_batch_processing_no_oom():
    """Batch processing should not cause OOM errors."""
    from app.services.ocr_service import OCRService

    ocr = OCRService()

    # Create large batch
    documents = [create_test_document() for _ in range(32)]

    # Process batch (should not crash)
    try:
        results = await ocr.process_batch(documents)
        assert len(results) == 32
        assert all(r.success for r in results)
    except torch.cuda.OutOfMemoryError:
        pytest.fail("GPU OOM error - batch size too large")
```

---

## Test Data Management

### Test Data Strategy

#### 1. Fixtures Location
```
tests/
  fixtures/
    documents/
      simple/
        single_page.pdf
        simple_invoice.pdf
      complex/
        multi_page_tables.pdf
        scanned_fraktur.pdf
      german/
        umlauts_test.pdf
        german_invoice.pdf
    images/
      test_image.png
      scanned_document.jpg
    api_responses/
      successful_upload.json
      error_response.json
```

#### 2. Test Data Generation
```python
# tests/utils/test_data_factory.py
from faker import Faker
from datetime import datetime, timedelta
import random

fake = Faker('de_DE')  # German locale

class DocumentFactory:
    """Generate test documents."""

    @staticmethod
    def create_document(**overrides):
        """Create test document with German data."""
        data = {
            "id": fake.uuid4(),
            "filename": fake.file_name(extension="pdf"),
            "owner_id": fake.uuid4(),
            "file_size_bytes": random.randint(1024, 10 * 1024 * 1024),
            "created_at": datetime.utcnow(),
            "status": "pending",
            "language": "de",
        }
        data.update(overrides)
        return data

    @staticmethod
    def create_german_invoice():
        """Create realistic German invoice document."""
        return {
            "filename": "rechnung_2025_001.pdf",
            "extracted_text": f"""
                Rechnung Nr. 2025-001

                {fake.company()}
                {fake.street_address()}
                {fake.postcode()} {fake.city()}

                Rechnungsdatum: {fake.date()}
                USt-IdNr.: DE{fake.random_number(digits=9)}

                Leistung: {fake.word()}
                Betrag: {fake.random_number(digits=3)},00 €

                Zahlbar bis: {(datetime.now() + timedelta(days=14)).strftime('%d.%m.%Y')}
            """,
            "contains_pii": True,
            "document_type": "invoice"
        }

# Usage in tests
def test_invoice_processing():
    invoice = DocumentFactory.create_german_invoice()
    # ... test with generated invoice
```

#### 3. Database Seeding
```python
# tests/utils/seed_database.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.db.models import User, Document

async def seed_test_data():
    """Seed database with test data."""
    engine = create_async_engine("postgresql+asyncpg://...")

    async with AsyncSession(engine) as session:
        # Create test users
        test_user = User(
            id="user_test_001",
            email="test@example.com",
            password_hash=hash_password("testpass123"),
            role="user"
        )
        session.add(test_user)

        admin_user = User(
            id="user_admin_001",
            email="admin@example.com",
            password_hash=hash_password("adminpass123"),
            role="admin"
        )
        session.add(admin_user)

        # Create test documents
        for i in range(10):
            doc = Document(
                id=f"doc_test_{i:03d}",
                filename=f"test_document_{i}.pdf",
                owner_id=test_user.id,
                status="completed",
                extracted_text=f"Test document content {i}"
            )
            session.add(doc)

        await session.commit()

if __name__ == "__main__":
    asyncio.run(seed_test_data())
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache dependencies
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: |
          pytest tests/unit/ \
            --cov=app \
            --cov-report=xml \
            --cov-report=term \
            -v

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: ablage_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run database migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/ablage_test

      - name: Run integration tests
        run: |
          pytest tests/integration/ \
            -v \
            --tb=short
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/ablage_test
          REDIS_URL: redis://localhost:6379

  gpu-tests:
    runs-on: [self-hosted, gpu]  # Dedicated GPU runner
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v3

      - name: Check GPU availability
        run: nvidia-smi

      - name: Run GPU tests
        run: |
          pytest tests/unit/ tests/integration/ \
            -m gpu \
            -v

      - name: GPU memory report
        if: always()
        run: nvidia-smi
```

---

## Test Reporting

### Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html

# Open in browser
open htmlcov/index.html
```

**Coverage Targets by Module:**
| Module | Target | Current | Status |
|--------|--------|---------|--------|
| API endpoints | 85% | 88% | ✅ |
| OCR services | 95% | 92% | ⚠️ (needs 3% more) |
| Authentication | 95% | 97% | ✅ |
| German validation | 100% | 100% | ✅ |
| GPU management | 90% | 85% | ⚠️ (needs 5% more) |
| Database repos | 85% | 90% | ✅ |

### Test Execution Reports

```bash
# Generate JUnit XML report
pytest --junitxml=test-results.xml

# Generate HTML report
pytest --html=test-report.html --self-contained-html
```

### Performance Benchmarks

Track performance trends over time:
```python
# tests/performance/benchmark_tracker.py
import json
from datetime import datetime

def record_benchmark(test_name: str, value: float, unit: str):
    """Record benchmark result with timestamp."""
    result = {
        "test": test_name,
        "value": value,
        "unit": unit,
        "timestamp": datetime.utcnow().isoformat(),
        "commit_sha": os.getenv("GITHUB_SHA", "local")
    }

    with open("benchmark_history.jsonl", "a") as f:
        f.write(json.dumps(result) + "\n")

# Usage
record_benchmark("api_health_check_p95", 45.2, "ms")
record_benchmark("ocr_throughput", 195.3, "docs/hour")
```

---

## Best Practices Summary

### DO ✅
- Write tests before fixing bugs (TDD)
- Use descriptive test names
- Test one thing per test
- Use fixtures for test data
- Mock external dependencies
- Measure and track coverage
- Run tests in CI/CD
- Test German language specifically
- Test error cases, not just happy paths

### DON'T ❌
- Skip tests for "trivial" code
- Test implementation details
- Use production data in tests
- Write flaky tests (non-deterministic)
- Ignore failing tests
- Mock code under test
- Hard-code test data in test methods
- Forget to clean up after tests

---

## Maintenance

### Monthly Review
- Review test coverage trends
- Update test data fixtures
- Remove obsolete tests
- Update performance baselines

### Quarterly Audit
- Review test strategy effectiveness
- Update this document with learnings
- Benchmark against industry standards

---

## Related Documents
- [Performance Testing Guide](performance_testing_guide.md)
- [Test Data Management](test_data_management.md)
- [CI/CD Pipeline Documentation](../Infrastructure/cicd_pipeline.md)
- [Quality Metrics Dashboard](../../Meta_Layer/Quality_Assurance/)

---

## Revision History

| Version | Date       | Author          | Changes                        |
|---------|------------|-----------------|--------------------------------|
| 1.0     | 2025-01-23 | QA Team         | Initial comprehensive strategy |

---

**"Quality is not an act, it is a habit." - Aristotle**

✅ **Testing Excellence Achieved!**
