# Test Fixtures Complete Guide

> **Ablage-System Enterprise Documentation**
> Version: 1.0 | Stand: Januar 2025

## Übersicht

Dieses Dokument beschreibt das vollständige Fixture-System des Ablage-Systems mit über **200 Fixtures** in 7 conftest.py-Dateien, Factory-Pattern-Klassen und Hilfsfunktionen.

---

## 1. Fixture-Hierarchie

### 1.1 Verzeichnisstruktur

```
tests/
├── conftest.py                      # Root: Session-Level Fixtures
├── fixtures/
│   ├── factories.py                 # Factory-Pattern Klassen
│   └── german_docs/                 # Test-Dokumente
│       ├── invoices/
│       ├── fraktur/
│       ├── tables/
│       ├── contracts/
│       ├── forms/
│       ├── handwritten/
│       └── mixed/
├── integration/
│   └── conftest.py                  # Integration: Storage, ML Features
├── e2e/
│   └── conftest.py                  # E2E: Mock Services, German Text
├── gpu/
│   └── conftest.py                  # GPU: Hardware Context, Memory
├── performance/
│   └── conftest.py                  # Performance: Timer, Memory Tracker
├── docker/
│   └── conftest.py                  # Docker: Service Definitions
│   └── helpers/
│       ├── docker_client.py
│       └── log_scanner.py
└── unit/
    └── orchestration/
        └── conftest.py              # Orchestration: Task Routing
```

### 1.2 Fixture-Scope Übersicht

| Scope | Lebensdauer | Verwendung |
|-------|-------------|------------|
| `session` | Gesamte Test-Session | Event Loop, GPU Context, Docker Client |
| `module` | Pro Test-Modul | OCR Agents, Test Images |
| `function` | Pro Test-Funktion | Database, HTTP Clients, Mocks |
| `autouse` | Automatisch | Cleanup, Memory Reset |

---

## 2. Root Conftest.py Fixtures

### 2.1 Konfiguration

```python
# tests/conftest.py

@pytest.fixture(scope="session")
def test_settings():
    """Override settings for testing."""
    return Settings(
        TESTING=True,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        RATE_LIMIT_ENABLED=False,
        GERMAN_VALIDATION_ENABLED=True,
    )
```

### 2.2 Datenbank

```python
@pytest_asyncio.fixture
async def test_db():
    """Create test database with proper cleanup."""
    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://ablage_admin:changeme@localhost:5433/ablage_test"
    )

    engine = create_async_engine(
        db_url,
        poolclass=NullPool,  # Kein Connection Pooling in Tests
        echo=False
    )

    # Tabellen erstellen
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Session bereitstellen
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    # Cleanup: Alle Tabellen droppen
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
```

**Eigenschaften**:
- `NullPool`: Jeder Test bekommt frische Verbindung
- `expire_on_commit=False`: Verhindert Lazy-Loading-Probleme
- Automatisches Cleanup nach Test

### 2.3 HTTP Clients

```python
@pytest.fixture
def client(test_settings):
    """Synchronous test client."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c

@pytest_asyncio.fixture
async def async_client(test_settings):
    """Asynchronous test client."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

### 2.4 Authentifizierung

```python
@pytest_asyncio.fixture
async def test_user(test_db):
    """Create test user in database."""
    from app.db.models import User
    from app.core.security import get_password_hash

    user = User(
        id=uuid4(),
        email="test@ablage-system.local",
        username="testuser",
        hashed_password=get_password_hash("Test123!@#"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user

@pytest.fixture
def auth_headers(test_user):
    """Generate JWT auth headers."""
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}
```

### 2.5 Mock Services

```python
@pytest.fixture
def mock_gpu_manager():
    """Mock GPU manager with RTX 4080 specs."""
    gpu_manager = Mock()
    gpu_manager.get_detailed_status.return_value = {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 4080",
        "device_id": 0,
        "memory_used_mb": 1024,
        "memory_total_mb": 16384,  # 16GB
        "utilization_percent": 10.0
    }
    return gpu_manager

@pytest.fixture
def mock_ocr_service():
    """Mock OCR service with AsyncMock."""
    ocr_service = Mock()
    ocr_service.process_document = AsyncMock(return_value={
        "success": True,
        "text": "Beispieltext mit Umlauten: äöüß",
        "confidence": 0.95,
        "backend_used": "surya",
        "processing_time_ms": 1500,
        "has_umlauts": True,
        "german_validation_score": 0.85
    })
    return ocr_service

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_client = Mock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)
    return redis_client
```

### 2.6 Sample Data Fixtures

```python
@pytest.fixture
def sample_user_data():
    """User registration test data."""
    return {
        "email": "newuser@example.de",
        "password": "SecurePass123!",
        "username": "newuser",
        "full_name": "Max Mustermann"
    }

@pytest.fixture
def sample_document_data():
    """Document metadata test data."""
    return {
        "filename": "test_document.pdf",
        "document_type": "invoice",
        "language": "de",
        "tags": ["rechnung", "2024"]
    }

@pytest.fixture
def sample_german_text():
    """Sample German text with umlauts."""
    return """
    Sehr geehrte Damen und Herren,

    hiermit übersende ich Ihnen die Rechnung Nr. 2024-001.

    Rechnungsdatum: 15.03.2024
    Betrag: 1.234,56 €

    Bankverbindung:
    IBAN: DE89 3704 0044 0532 0130 00
    USt-IdNr.: DE123456789

    Mit freundlichen Grüßen,
    Müller GmbH & Co. KG
    """
```

### 2.7 File Fixtures

```python
@pytest.fixture
def sample_pdf_file(tmp_path):
    """Create sample PDF with reportlab."""
    pdf_path = tmp_path / "test.pdf"

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        c.drawString(100, 750, "Test Document")
        c.drawString(100, 700, "Aepfel, Oel, Ueberpruefung, Strasse")
        c.save()
    except ImportError:
        # Fallback: Minimal valid PDF
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj..."
        pdf_path.write_bytes(pdf_content)

    return pdf_path

@pytest.fixture
def sample_image_file(tmp_path):
    """Create PNG image with PIL."""
    from PIL import Image, ImageDraw

    img_path = tmp_path / "test.png"
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Test Image", fill='black')
    draw.text((50, 100), "Müller, Größe, Überprüfung", fill='black')
    img.save(img_path)

    return img_path
```

### 2.8 Event Loop & Cleanup

```python
@pytest.fixture(scope="session")
def event_loop():
    """Create session event loop for async fixtures."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def cleanup_uploads(tmp_path):
    """Auto-cleanup uploaded files after tests."""
    yield
    # Cleanup passiert automatisch via tmp_path
```

---

## 3. GPU Fixtures

### 3.1 GPU Context

```python
# tests/gpu/conftest.py
from dataclasses import dataclass

@dataclass
class GPUTestContext:
    """Context information for GPU tests."""
    torch_available: bool
    cuda_available: bool
    gpu_name: str
    vram_total_gb: float
    vram_free_gb: float
    cuda_version: str
    cudnn_version: Optional[int]

    @property
    def can_run_deepseek(self) -> bool:
        return self.vram_free_gb >= 12.0

    @property
    def can_run_got_ocr(self) -> bool:
        return self.vram_free_gb >= 10.0

    @property
    def can_run_surya_gpu(self) -> bool:
        return self.vram_free_gb >= 8.0

@pytest.fixture(scope="session")
def gpu_context() -> GPUTestContext:
    """Provide GPU context for tests."""
    if not TORCH_AVAILABLE:
        return GPUTestContext(
            torch_available=False,
            cuda_available=False,
            gpu_name="Not available",
            vram_total_gb=0.0,
            vram_free_gb=0.0,
            cuda_version="",
            cudnn_version=None,
        )

    vram_free = (
        torch.cuda.get_device_properties(0).total_memory -
        torch.cuda.memory_allocated(0)
    ) / (1024**3)

    return GPUTestContext(
        torch_available=True,
        cuda_available=True,
        gpu_name=torch.cuda.get_device_name(0),
        vram_total_gb=torch.cuda.get_device_properties(0).total_memory / (1024**3),
        vram_free_gb=vram_free,
        cuda_version=torch.version.cuda or "",
        cudnn_version=torch.backends.cudnn.version(),
    )
```

### 3.2 Memory Tracking

```python
@pytest.fixture(scope="function")
def gpu_memory_tracker():
    """Track GPU memory usage during test."""
    if not TORCH_AVAILABLE:
        yield None
        return

    class MemoryTracker:
        def __init__(self):
            self.start_allocated = 0.0
            self.peak_allocated = 0.0
            self.end_allocated = 0.0

        def start(self):
            torch.cuda.reset_peak_memory_stats()
            self.start_allocated = torch.cuda.memory_allocated() / (1024**3)

        def stop(self):
            self.peak_allocated = torch.cuda.max_memory_allocated() / (1024**3)
            self.end_allocated = torch.cuda.memory_allocated() / (1024**3)

        @property
        def delta(self) -> float:
            return self.end_allocated - self.start_allocated

        def verify_under_threshold(self, threshold_gb: float = 13.6):
            assert self.peak_allocated < threshold_gb

    tracker = MemoryTracker()
    tracker.start()
    yield tracker
    tracker.stop()

@pytest.fixture(scope="function")
def clean_gpu_memory():
    """Clean GPU memory before and after each test."""
    if not TORCH_AVAILABLE:
        yield
        return

    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    yield

    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    gc.collect()
```

### 3.3 VRAM Skip Fixtures

```python
@pytest.fixture
def requires_12gb_vram(gpu_context):
    """Skip if less than 12GB VRAM (DeepSeek)."""
    if not gpu_context.can_run_deepseek:
        pytest.skip(f"Requires 12GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available")

@pytest.fixture
def requires_10gb_vram(gpu_context):
    """Skip if less than 10GB VRAM (GOT-OCR)."""
    if not gpu_context.can_run_got_ocr:
        pytest.skip(f"Requires 10GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available")

@pytest.fixture
def requires_8gb_vram(gpu_context):
    """Skip if less than 8GB VRAM (Surya GPU)."""
    if not gpu_context.can_run_surya_gpu:
        pytest.skip(f"Requires 8GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available")

@pytest.fixture
def skip_on_windows():
    """Skip on Windows (BitsAndBytes compatibility)."""
    if sys.platform == "win32":
        pytest.skip("BitsAndBytes limited on Windows - use WSL2/Docker")
```

### 3.4 OCR Agent Fixtures

```python
@pytest.fixture(scope="module")
def surya_gpu_agent():
    """Create SuryaGPU agent with cleanup."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")

    from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
    agent = SuryaGPUAgent()
    yield agent

    if hasattr(agent, 'cleanup'):
        asyncio.get_event_loop().run_until_complete(agent.cleanup())

@pytest.fixture(scope="module")
def deepseek_agent():
    """Create DeepSeek agent (requires BitsAndBytes)."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")
    if sys.platform == "win32":
        pytest.skip("DeepSeek requires BitsAndBytes")

    from app.agents.ocr.deepseek_agent import DeepSeekAgent
    agent = DeepSeekAgent()
    yield agent

    if hasattr(agent, 'cleanup'):
        asyncio.get_event_loop().run_until_complete(agent.cleanup())

@pytest.fixture(scope="module")
def got_ocr_agent():
    """Create GOT-OCR agent."""
    # Similar pattern...

@pytest.fixture(scope="module")
def donut_agent():
    """Create Donut OCR agent."""
    # Similar pattern...
```

### 3.5 Test Image Generation

```python
@pytest.fixture(scope="module")
def test_images_dir(tmp_path_factory) -> Path:
    """Create test images for GPU backend testing."""
    from PIL import Image, ImageDraw

    test_dir = tmp_path_factory.mktemp("gpu_test_images")

    # 1. German Text Image
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "RECHNUNG Nr. 2024-001", fill='black')
    draw.text((50, 100), "Müller GmbH & Co. KG", fill='black')
    draw.text((50, 150), "IBAN: DE89 3704 0044 0532 0130 00", fill='black')
    img.save(test_dir / "german_text.png")

    # 2. Simple Text Image
    img2 = Image.new('RGB', (400, 200), color='white')
    draw2 = ImageDraw.Draw(img2)
    draw2.text((50, 50), "Simple Test", fill='black')
    img2.save(test_dir / "simple_text.png")

    # 3. Complex Layout
    img3 = Image.new('RGB', (800, 600), color='white')
    draw3 = ImageDraw.Draw(img3)
    draw3.rectangle([40, 40, 760, 80], outline='black')
    draw3.text((50, 50), "Pos | Artikel | Preis", fill='black')
    img3.save(test_dir / "complex_layout.png")

    # 4. Handwritten Style
    img4 = Image.new('RGB', (600, 400), color='lightyellow')
    draw4 = ImageDraw.Draw(img4)
    draw4.text((30, 30), "Notizen: Müller anrufen", fill='darkblue')
    img4.save(test_dir / "handwritten.png")

    return test_dir
```

---

## 4. E2E Fixtures

### 4.1 Mock Results

```python
# tests/e2e/conftest.py

@pytest.fixture
def mock_ocr_result():
    """Complete OCR result fixture."""
    return {
        "success": True,
        "text": "Dies ist ein Beispieltext mit deutschen Umlauten: ä, ö, ü, ß",
        "confidence": 0.95,
        "processing_time_ms": 1250.0,
        "backend": "deepseek",
        "language": "de",
        "word_count": 11,
        "pages": 1,
        "metadata": {
            "resolution_dpi": 300,
            "image_dimensions": {"width": 2480, "height": 3508}
        }
    }

@pytest.fixture
def mock_entity_extraction_result():
    """Entity extraction fixture."""
    return {
        "entities": [
            {"type": "date", "value": "15.03.2024", "confidence": 0.95},
            {"type": "currency", "value": {"amount": 1190.0, "currency": "EUR"}, "confidence": 0.92},
            {"type": "iban", "value": "DE89370400440532013000", "confidence": 0.98},
            {"type": "vat_id", "value": "DE123456789", "confidence": 0.97},
            {"type": "company", "value": "Müller GmbH", "confidence": 0.94},
            {"type": "address", "value": "Goethestraße 42, 80336 München", "confidence": 0.91}
        ],
        "entity_count": 6,
        "processing_time_ms": 350.0
    }

@pytest.fixture
def mock_classification_result():
    """Document classification fixture."""
    return {
        "document_type": "invoice",
        "confidence": 0.92,
        "language": "de",
        "complexity": "medium",
        "has_tables": True,
        "has_images": False,
        "page_count": 1,
        "recommended_backend": "deepseek"
    }

@pytest.fixture
def mock_qa_result():
    """Quality assurance fixture."""
    return {
        "quality_level": "good",
        "quality_score": 0.88,
        "issues": [],
        "metrics": {
            "umlaut_accuracy": 1.0,
            "date_format_correct": True,
            "currency_format_correct": True
        },
        "recommendations": []
    }

@pytest.fixture
def mock_correction_result():
    """German correction fixture."""
    return {
        "text": "Der korrigierte Text mit Änderung, Öffnung, Übung.",
        "original_text": "Der korrigierte Text mit Aenderung, Oeffnung, Uebung.",
        "corrections_applied": 3,
        "correction_details": [
            {"type": "umlaut", "original": "Aenderung", "corrected": "Änderung", "confidence": 0.95},
            {"type": "umlaut", "original": "Oeffnung", "corrected": "Öffnung", "confidence": 0.94},
            {"type": "umlaut", "original": "Uebung", "corrected": "Übung", "confidence": 0.93}
        ],
        "validation_score": 0.95,
        "umlauts_restored": 3
    }
```

### 4.2 German Text Fixtures

```python
@pytest.fixture
def sample_german_invoice_text():
    """German invoice sample."""
    return """
    RECHNUNG Nr. 2024-5878

    Böhm Elektrotechnik GmbH
    Goethestraße 22
    80336 München

    USt-IdNr.: DE621056220
    IBAN: DE50 1545 7282 2408 8994 28

    Datum: 05.09.2025

    Pos.  Beschreibung          Menge    Preis      Gesamt
    1     Elektromotor 5kW      2        450,00 €   900,00 €
    2     Kabelkanal 2m         10       25,00 €    250,00 €

    Netto:     1.150,00 €
    MwSt 19%:    218,50 €
    Brutto:    1.368,50 €
    """

@pytest.fixture
def sample_contract_text():
    """German contract sample."""
    return """
    MIETVERTRAG

    §1 Vertragsparteien
    Vermieter: Max Müller, Goethestraße 42, 80336 München
    Mieter: Erika Schmöller, Schloßstraße 15, 60311 Frankfurt

    §2 Mietobjekt
    Die Wohnung in der Gärtnerstraße 7, 2. OG rechts.

    §3 Mietdauer
    Beginn: 01.04.2025
    Kündigungsfrist: 3 Monate

    §4 Miete
    Kaltmiete: 1.200,00 EUR
    Nebenkosten: 200,00 EUR
    Kaution: 3.600,00 EUR

    Übergabe erfolgt am 01.04.2025.
    """
```

---

## 5. Integration Fixtures

### 5.1 Temporary Storage

```python
# tests/integration/conftest.py

@pytest.fixture
def temp_storage(tmp_path):
    """Temporary directory with subdirectories."""
    dirs = ["drift", "ab_tests", "shap", "models"]
    for d in dirs:
        (tmp_path / d).mkdir()
    return tmp_path
```

### 5.2 ML Features

```python
@pytest.fixture
def ml_test_features():
    """Standard ML feature dictionary."""
    return {
        "text_length": 500,
        "word_count": 100,
        "umlaut_density": 0.05,
        "has_tables": True,
        "has_images": False,
        "language": "de",
        "document_type": "invoice"
    }

@pytest.fixture
def sample_document_batch():
    """20 documents with varying features."""
    documents = []
    for i in range(20):
        doc = {
            "id": str(uuid4()),
            "text_length": 200 + i * 50,
            "word_count": 40 + i * 10,
            "has_tables": i % 3 == 0,
            "document_type": ["invoice", "contract", "letter"][i % 3]
        }
        documents.append(doc)
    return documents
```

---

## 6. Performance Fixtures

### 6.1 Timer

```python
# tests/performance/conftest.py

@pytest.fixture
def timer():
    """Simple timer for benchmarks."""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.measurements = []

        def start(self):
            self.start_time = datetime.now()

        def stop(self):
            self.end_time = datetime.now()
            if self.start_time:
                elapsed = (self.end_time - self.start_time).total_seconds()
                self.measurements.append(elapsed)
                return elapsed
            return 0

        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time).total_seconds()
            return 0

        @property
        def average(self):
            return sum(self.measurements) / len(self.measurements) if self.measurements else 0

    return Timer()
```

### 6.2 Memory Tracker

```python
@pytest.fixture
def memory_tracker():
    """Memory tracker using tracemalloc."""
    import tracemalloc

    class MemoryTracker:
        def __init__(self):
            self.snapshots = []
            self.peak_memory_mb = 0

        def start(self):
            tracemalloc.start()

        def snapshot(self):
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                self.snapshots.append({
                    "current_mb": current / 1024 / 1024,
                    "peak_mb": peak / 1024 / 1024,
                    "timestamp": datetime.now().isoformat()
                })
                self.peak_memory_mb = max(self.peak_memory_mb, peak / 1024 / 1024)

        def stop(self):
            if tracemalloc.is_tracing():
                tracemalloc.stop()

        def get_peak_mb(self):
            return self.peak_memory_mb

    return MemoryTracker()
```

### 6.3 Mock Document Factory

```python
@pytest.fixture
def mock_document_factory():
    """Factory for mock documents with configurable size."""
    def create_document(
        doc_id=None,
        text_size_kb=10,
        document_type="invoice"
    ):
        doc_id = doc_id or uuid4()

        base_text = (
            "Dies ist ein Testdokument für den Performance-Benchmark. "
            "Es enthält deutsche Umlaute wie äöüß. "
            "Rechnungsnummer: RE-2024-001. Betrag: 1.234,56 EUR. "
        )
        text = (base_text * ((text_size_kb * 1024) // len(base_text) + 1))[:text_size_kb * 1024]

        doc = Mock()
        doc.id = doc_id
        doc.filename = f"test_doc_{doc_id}.pdf"
        doc.document_type = document_type
        doc.status = "processed"
        doc.created_at = datetime.now(timezone.utc)
        doc.file_size = text_size_kb * 1024
        doc.page_count = max(1, text_size_kb // 2)
        doc.ocr_confidence = 0.85
        doc.extracted_text = text
        doc.detected_language = "de"
        doc.has_umlauts = True

        return doc

    return create_document

@pytest.fixture
def small_document_set(mock_document_factory):
    """10 small documents (10KB each)."""
    return [mock_document_factory(text_size_kb=10) for _ in range(10)]

@pytest.fixture
def medium_document_set(mock_document_factory):
    """50 medium documents (50KB each)."""
    return [mock_document_factory(text_size_kb=50) for _ in range(50)]

@pytest.fixture
def large_document_set(mock_document_factory):
    """100 large documents (100KB each)."""
    return [mock_document_factory(text_size_kb=100) for _ in range(100)]
```

---

## 7. Docker Fixtures

### 7.1 Service Definitions

```python
# tests/docker/conftest.py
from dataclasses import dataclass, field

@dataclass
class ServiceDefinition:
    """Docker service definition."""
    name: str
    container_name: str
    category: str
    critical: bool = False
    requires_gpu: bool = False
    optional: bool = False
    health_endpoint: str | None = None
    health_port: int | None = None
    expected_networks: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    known_error_patterns: list[str] = field(default_factory=list)

# Service definitions
SERVICES = {
    "backend": ServiceDefinition(
        name="backend",
        container_name="ablage-backend",
        category="core",
        critical=True,
        health_endpoint="/health",
        health_port=8000,
        depends_on=["postgres", "redis"],
    ),
    "postgres": ServiceDefinition(
        name="postgres",
        container_name="ablage-postgres",
        category="database",
        critical=True,
        health_port=5432,
    ),
    "redis": ServiceDefinition(
        name="redis",
        container_name="ablage-redis",
        category="cache",
        critical=True,
        health_port=6379,
    ),
    # ... more services
}

CRITICAL_SERVICES = [s for s in SERVICES.values() if s.critical]
GPU_SERVICES = [s for s in SERVICES.values() if s.requires_gpu]
```

### 7.2 Docker Client

```python
@pytest.fixture(scope="session")
def docker_client():
    """Provide DockerClient instance."""
    from tests.docker.helpers.docker_client import DockerClient

    client = DockerClient()
    yield client

@pytest.fixture(scope="session")
def all_services():
    """Return all service definitions."""
    return SERVICES

@pytest.fixture(scope="session")
def critical_services():
    """Return critical services."""
    return CRITICAL_SERVICES

@pytest.fixture(scope="session")
def gpu_available():
    """Check if GPU is available."""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
```

---

## 8. Factory Pattern System

### 8.1 Base Factory

```python
# tests/fixtures/factories.py

class BaseFactory:
    """Base class for all factories."""
    _counter: int = 0

    @classmethod
    def _next_id(cls) -> int:
        cls._counter += 1
        return cls._counter

    @classmethod
    def _random_string(cls, length: int = 8) -> str:
        import string
        return ''.join(random.choices(string.ascii_lowercase, k=length))

    @classmethod
    def _random_uuid(cls) -> str:
        return str(uuid4())
```

### 8.2 UserFactory

```python
class UserFactory(BaseFactory):
    """Factory for creating test users (NO database)."""

    GERMAN_FIRST_NAMES = ["Max", "Maria", "Thomas", "Anna", "Klaus", "Petra"]
    GERMAN_LAST_NAMES = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meier"]

    @classmethod
    def create(
        cls,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: str = "user",
        is_active: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Create user dictionary without DB."""
        first = first_name or random.choice(cls.GERMAN_FIRST_NAMES)
        last = last_name or random.choice(cls.GERMAN_LAST_NAMES)

        return {
            "id": cls._random_uuid(),
            "email": email or f"test_{cls._next_id()}@example.de",
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}",
            "role": role,
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

    @classmethod
    def create_admin(cls, **kwargs) -> Dict[str, Any]:
        return cls.create(role="admin", **kwargs)

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> List[Dict]:
        return [cls.create(**kwargs) for _ in range(count)]
```

### 8.3 DocumentFactory

```python
class DocumentFactory(BaseFactory):
    """Factory for creating test documents."""

    DOCUMENT_TYPES = ["invoice", "contract", "letter", "form", "report"]
    GERMAN_TITLES = [
        "Rechnung Nr. {num}",
        "Vertrag vom {date}",
        "Antrag auf {subject}",
        "Bericht über {topic}",
        "Formular {form_type}",
    ]

    @classmethod
    def create(
        cls,
        title: Optional[str] = None,
        document_type: Optional[str] = None,
        file_name: Optional[str] = None,
        status: str = "processed",
        **kwargs
    ) -> Dict[str, Any]:
        doc_id = cls._next_id()
        doc_type = document_type or random.choice(cls.DOCUMENT_TYPES)

        return {
            "id": cls._random_uuid(),
            "title": title or f"Rechnung Nr. {2024000 + doc_id}",
            "document_type": doc_type,
            "file_name": file_name or f"document_{doc_id}.pdf",
            "file_size": random.randint(50000, 5000000),
            "content_hash": hashlib.sha256(cls._random_string(32).encode()).hexdigest(),
            "status": status,
            "page_count": random.randint(1, 10),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

    @classmethod
    def create_invoice(cls, **kwargs) -> Dict:
        return cls.create(document_type="invoice", **kwargs)

    @classmethod
    def create_contract(cls, **kwargs) -> Dict:
        return cls.create(document_type="contract", **kwargs)

    @classmethod
    def create_pending(cls, **kwargs) -> Dict:
        return cls.create(status="pending", **kwargs)
```

### 8.4 OCRResultFactory

```python
class OCRResultFactory(BaseFactory):
    """Factory for OCR results."""

    GERMAN_SAMPLE_TEXTS = [
        "Dies ist ein Testdokument mit deutschem Text und Umlauten: äöüß.",
        "Sehr geehrte Damen und Herren, hiermit übersende ich Ihnen...",
        "Rechnungsbetrag: 1.234,56 EUR inkl. 19% MwSt.",
        "Vertragslaufzeit: 01.01.2025 bis 31.12.2025",
        "Mit freundlichen Grüßen, Max Müller",
    ]
    BACKENDS = ["deepseek", "got_ocr", "surya", "surya_gpu"]

    @classmethod
    def create(
        cls,
        text: Optional[str] = None,
        confidence: Optional[float] = None,
        backend: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return {
            "id": cls._random_uuid(),
            "text": text or random.choice(cls.GERMAN_SAMPLE_TEXTS),
            "confidence": confidence or random.uniform(0.7, 0.99),
            "backend": backend or random.choice(cls.BACKENDS),
            "processing_time_ms": random.randint(500, 5000),
            "word_count": random.randint(50, 500),
            "has_umlauts": True,
            "language": "de",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

    @classmethod
    def create_high_confidence(cls, **kwargs) -> Dict:
        return cls.create(confidence=random.uniform(0.9, 0.99), **kwargs)

    @classmethod
    def create_low_confidence(cls, **kwargs) -> Dict:
        return cls.create(confidence=random.uniform(0.5, 0.7), **kwargs)

    @classmethod
    def create_for_backend(cls, backend: str, **kwargs) -> Dict:
        return cls.create(backend=backend, **kwargs)
```

### 8.5 EntityFactory

```python
class EntityFactory(BaseFactory):
    """Factory for entity extraction results."""

    ENTITY_TYPES = {
        "PERSON": ["Max Müller", "Anna Schmidt", "Klaus Weber"],
        "ORGANIZATION": ["Deutsche Bank AG", "Siemens AG", "Müller GmbH"],
        "LOCATION": ["Berlin", "München", "Frankfurt"],
        "DATE": ["01.01.2025", "15.03.2024", "31.12.2024"],
        "AMOUNT": ["1.234,56 EUR", "500,00 EUR", "10.000,00 EUR"],
        "IBAN": ["DE89 3704 0044 0532 0130 00"],
        "TAX_NUMBER": ["123/456/78901"],
    }

    @classmethod
    def create(
        cls,
        entity_type: Optional[str] = None,
        value: Optional[str] = None,
        confidence: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        etype = entity_type or random.choice(list(cls.ENTITY_TYPES.keys()))

        return {
            "id": cls._random_uuid(),
            "type": etype,
            "value": value or random.choice(cls.ENTITY_TYPES.get(etype, ["Unknown"])),
            "confidence": confidence or random.uniform(0.8, 0.99),
            "start_position": random.randint(0, 500),
            "end_position": random.randint(501, 1000),
            **kwargs
        }

    @classmethod
    def create_person(cls, name: Optional[str] = None, **kwargs) -> Dict:
        return cls.create(entity_type="PERSON", value=name, **kwargs)

    @classmethod
    def create_organization(cls, name: Optional[str] = None, **kwargs) -> Dict:
        return cls.create(entity_type="ORGANIZATION", value=name, **kwargs)
```

### 8.6 FixtureLoader

```python
class FixtureLoader:
    """Load test fixtures from files."""
    FIXTURES_DIR = Path(__file__).parent

    @classmethod
    def get_sample_image_path(cls, category: str, index: int = 1) -> Path:
        """Get path to sample image."""
        return cls.FIXTURES_DIR / "german_docs" / category / f"{category}_{index:03d}.png"

    @classmethod
    def get_sample_json_path(cls, category: str, index: int = 1) -> Path:
        """Get path to annotation JSON."""
        return cls.FIXTURES_DIR / "german_docs" / category / f"{category}_{index:03d}.json"

    @classmethod
    def load_sample_annotation(cls, category: str, index: int = 1) -> Dict:
        """Load JSON annotation."""
        json_path = cls.get_sample_json_path(category, index)
        if json_path.exists():
            return json.loads(json_path.read_text(encoding="utf-8"))
        return {}

    @classmethod
    def list_samples(cls, category: str) -> List[Path]:
        """List all samples in category."""
        category_dir = cls.FIXTURES_DIR / "german_docs" / category
        if category_dir.exists():
            return sorted(category_dir.glob("*.png"))
        return []
```

### 8.7 Convenience Functions

```python
# Shortcut functions for quick access
def create_test_user(**kwargs) -> Dict:
    return UserFactory.create(**kwargs)

def create_test_document(**kwargs) -> Dict:
    return DocumentFactory.create(**kwargs)

def create_test_ocr_result(**kwargs) -> Dict:
    return OCRResultFactory.create(**kwargs)

def create_test_entity(**kwargs) -> Dict:
    return EntityFactory.create(**kwargs)
```

---

## 9. Fixture-Dokumente

### 9.1 Verzeichnisstruktur

```
tests/fixtures/german_docs/
├── invoices/           # 6 Rechnungen
│   ├── invoice_001.png
│   ├── invoice_001.json
│   ├── ...
│   └── invoice_006.json
├── fraktur/           # 6 Fraktur-Samples
├── tables/            # 6 Tabellen
├── contracts/         # 6 Verträge
├── forms/             # 3 Formulare
├── handwritten/       # 3 Handschriften
└── mixed/             # 3 Gemischte Layouts
```

### 9.2 Annotation Format

```json
{
  "filename": "invoice_001.png",
  "category": "invoices",
  "expected_text": "RECHNUNG Nr. 2024-5878...",
  "expected_entities": {
    "invoice_number": ["2024-5878"],
    "iban": ["DE50154572822408899428"],
    "vat_id": ["DE621056220"],
    "date": ["05.09.2025"],
    "total_gross": ["3.661,90"]
  },
  "has_umlauts": true,
  "has_tables": false,
  "language": "de"
}
```

---

## 10. Async Fixture Patterns

### 10.1 pytest_asyncio Fixtures

```python
@pytest_asyncio.fixture
async def test_db():
    """Async database fixture."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, class_=AsyncSession)
    async with async_session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

### 10.2 AsyncMock in Regular Fixtures

```python
@pytest.fixture
def mock_ocr_service():
    """Regular fixture using AsyncMock."""
    from unittest.mock import Mock, AsyncMock

    service = Mock()
    service.process = AsyncMock(return_value={"success": True})
    return service
```

---

## 11. Cleanup Patterns

### 11.1 Context Manager Yield

```python
@pytest.fixture
def sample_file(tmp_path):
    """File with automatic cleanup."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("Test content")
    yield file_path
    # Cleanup via tmp_path
```

### 11.2 Async Cleanup

```python
@pytest.fixture(scope="module")
def ocr_agent():
    """Agent with async cleanup."""
    agent = OCRAgent()
    yield agent

    if hasattr(agent, 'cleanup'):
        asyncio.get_event_loop().run_until_complete(agent.cleanup())
```

### 11.3 Autouse Cleanup

```python
@pytest.fixture(autouse=True)
def reset_counters():
    """Auto-reset factory counters."""
    BaseFactory._counter = 0
    yield
```

---

## 12. Best Practices

### 12.1 Fixture-Scope wählen

| Scope | Verwendung |
|-------|------------|
| `session` | Teure Setups (GPU, Docker) |
| `module` | ML Models, Agents |
| `function` | Database, HTTP Clients |
| `autouse` | Cleanup, Reset |

### 12.2 Factory vs Fixture

- **Factory**: Für Daten ohne Side-Effects
- **Fixture**: Für Ressourcen mit Setup/Teardown

### 12.3 Naming Conventions

- `test_*`: Test-Präfix für Fixtures mit DB
- `sample_*`: Beispieldaten
- `mock_*`: Mock-Objekte
- `*_factory`: Factory-Funktionen

---

## Zusammenfassung

Das Fixture-System bietet:
- **200+ Fixtures** in 7 conftest.py-Dateien
- **4 Factory-Klassen** für datenbankfreie Testdaten
- **30+ Fixture-Dokumente** mit deutschen Beispielen
- **GPU-spezifische Fixtures** mit Memory-Tracking
- **Async-First Design** mit pytest_asyncio
- **Automatische Cleanup-Patterns**
