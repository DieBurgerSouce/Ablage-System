# GPU Testing Guide

> **Ablage-System Enterprise Documentation**
> Version: 1.0 | Stand: Januar 2025

## Übersicht

Dieses Dokument beschreibt die GPU-Teststrategien für das Ablage-System mit RTX 4080 (16GB VRAM). Die Tests stellen sicher, dass alle OCR-Backends effizient arbeiten und die GPU-Ressourcen optimal genutzt werden.

---

## 1. GPU-Test-Konfiguration

### 1.1 Pytest Marker

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "gpu: Tests requiring GPU",
    "gpu_required: Tests that require GPU (will skip if not available)",
    "gpu_optional: GPU tests (skip if no GPU available)",
    "fallback: GPU fallback scenario tests",
    "windows: Windows-specific tests",
    "experimental: Experimental features",
]
```

### 1.2 Test-Verzeichnisstruktur

```
tests/
├── gpu/
│   ├── conftest.py                  # GPU-Fixtures
│   ├── test_batch_processing.py     # Batch-Stabilität
│   ├── test_deepseek_gpu_backend.py # DeepSeek Tests
│   ├── test_got_ocr_gpu_backend.py  # GOT-OCR Tests
│   ├── test_surya_gpu_backend.py    # Surya GPU Tests
│   ├── test_donut_gpu_backend.py    # Donut OCR Tests
│   ├── test_oom_recovery.py         # OOM-Recovery
│   ├── test_memory_leaks.py         # Memory-Leak-Detection
│   ├── test_fallback_scenarios.py   # GPU→CPU Fallback
│   └── test_deepseek_windows.py     # Windows-spezifisch
├── unit/
│   ├── test_gpu_manager.py          # GPUManager Unit Tests
│   ├── test_gpu_stress.py           # Stress Tests
│   └── core/
│       ├── test_gpu_recovery.py     # Recovery Manager
│       └── test_gpu_memory_leak_detection.py
└── performance/
    └── test_ocr_benchmarks.py       # Performance Benchmarks
```

---

## 2. GPU-Fixtures

### 2.1 GPU Context Fixture (Session-Scoped)

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
        """Check if DeepSeek (12GB) can run."""
        return self.vram_free_gb >= 12.0

    @property
    def can_run_got_ocr(self) -> bool:
        """Check if GOT-OCR (10GB) can run."""
        return self.vram_free_gb >= 10.0

    @property
    def can_run_surya_gpu(self) -> bool:
        """Check if SuryaGPU (8GB) can run."""
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
        cudnn_version=torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None,
    )
```

### 2.2 GPU Memory Tracker

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
            """Verify VRAM stays below 85% of 16GB."""
            assert self.peak_allocated < threshold_gb, (
                f"Peak VRAM {self.peak_allocated:.2f}GB exceeded threshold {threshold_gb}GB"
            )

    tracker = MemoryTracker()
    tracker.start()
    yield tracker
    tracker.stop()
```

### 2.3 GPU Memory Cleanup

```python
@pytest.fixture(scope="function")
def clean_gpu_memory():
    """Clean GPU memory before and after each test."""
    if not TORCH_AVAILABLE:
        yield
        return

    # Vor dem Test bereinigen
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    yield

    # Nach dem Test bereinigen
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    # Garbage Collection erzwingen
    import gc
    gc.collect()
```

### 2.4 VRAM-basierte Skip-Fixtures

```python
@pytest.fixture
def requires_12gb_vram(gpu_context):
    """Skip test if less than 12GB VRAM available."""
    if not gpu_context.can_run_deepseek:
        pytest.skip(
            f"Requires 12GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available"
        )

@pytest.fixture
def requires_10gb_vram(gpu_context):
    """Skip test if less than 10GB VRAM available."""
    if not gpu_context.can_run_got_ocr:
        pytest.skip(
            f"Requires 10GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available"
        )

@pytest.fixture
def requires_8gb_vram(gpu_context):
    """Skip test if less than 8GB VRAM available."""
    if not gpu_context.can_run_surya_gpu:
        pytest.skip(
            f"Requires 8GB VRAM, only {gpu_context.vram_free_gb:.1f}GB available"
        )

@pytest.fixture
def skip_on_windows():
    """Skip test on Windows (BitsAndBytes compatibility)."""
    if sys.platform == "win32":
        pytest.skip("BitsAndBytes has limited Windows support - run in WSL2/Docker")
```

---

## 3. Mock-Patterns für GPU-Tests

### 3.1 Standard GPU Mock

```python
# tests/unit/test_gpu_stress.py
@pytest.fixture
def mock_torch():
    """Mock torch.cuda für Tests ohne GPU."""
    with patch('gpu_manager.TORCH_AVAILABLE', True):
        with patch('gpu_manager.torch') as mock:
            mock.cuda.is_available.return_value = True
            mock.cuda.memory_allocated.return_value = 4 * 1024**3  # 4GB
            mock.cuda.memory_reserved.return_value = 6 * 1024**3   # 6GB
            mock.cuda.get_device_properties.return_value = Mock(
                total_memory=16 * 1024**3  # 16GB RTX 4080
            )
            mock.cuda.get_device_name.return_value = "NVIDIA GeForce RTX 4080"
            mock.cuda.empty_cache = Mock()
            mock.cuda.synchronize = Mock()
            mock.cuda.reset_peak_memory_stats = Mock()
            mock.cuda.max_memory_allocated.return_value = 12 * 1024**3
            yield mock
```

### 3.2 High Memory Mock (>85% Auslastung)

```python
@pytest.fixture
def mock_torch_high_memory():
    """Mock torch.cuda mit hoher Speicherauslastung (>85%)."""
    with patch('gpu_manager.TORCH_AVAILABLE', True):
        with patch('gpu_manager.torch') as mock:
            mock.cuda.is_available.return_value = True
            mock.cuda.memory_allocated.return_value = 14 * 1024**3  # 14GB
            mock.cuda.get_device_properties.return_value = Mock(
                total_memory=16 * 1024**3  # 16GB = 87.5% Auslastung
            )
            yield mock
```

### 3.3 OOM Simulation Mock

```python
@pytest.fixture
def mock_torch_oom():
    """Mock für OOM-Simulation."""
    with patch('gpu_manager.TORCH_AVAILABLE', True):
        with patch('gpu_manager.torch') as mock:
            mock.cuda.is_available.return_value = True
            mock.cuda.memory_allocated.return_value = 15.5 * 1024**3  # 15.5GB
            mock.cuda.get_device_properties.return_value = Mock(
                total_memory=16 * 1024**3  # Nahezu voll
            )
            # Simuliere OOM bei Allocation
            mock.cuda.OutOfMemoryError = torch.cuda.OutOfMemoryError
            yield mock
```

---

## 4. Test-Patterns

### 4.1 Memory Leak Detection

```python
@pytest.mark.asyncio
async def test_no_memory_leak_on_repeated_processing(
    self, gpu_context, requires_8gb_vram, test_images_dir
):
    """Test for memory leaks on 10 consecutive runs."""
    agent = SuryaGPUAgent()
    baseline = torch.cuda.memory_allocated() / (1024**3)
    peak_memory = baseline

    for i in range(10):
        await agent.process(test_images_dir / "german_text.png")
        current = torch.cuda.memory_allocated() / (1024**3)
        peak_memory = max(peak_memory, current)

    final = torch.cuda.memory_allocated() / (1024**3)
    growth = final - baseline

    # Erlaube 0.5GB Wachstum für internes Caching
    assert growth < 0.5, f"Memory grew {growth:.2f}GB over 10 runs"
```

### 4.2 Batch Stability Test

```python
@pytest.mark.asyncio
async def test_surya_gpu_batch_stability(
    self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
):
    """Test SuryaGPU batch stability over multiple runs."""
    agent = SuryaGPUAgent()
    initial_memory = torch.cuda.memory_allocated() / (1024**3)

    for batch_num in range(5):
        result = await agent.process(test_images_dir / "german_text.png")
        assert result.get("success") is True or result.get("status") == "success"

    final_memory = torch.cuda.memory_allocated() / (1024**3)
    growth = final_memory - initial_memory

    assert growth < 2.0, f"Memory grew {growth:.2f}GB over 5 batches - possible leak"
```

### 4.3 Throughput Benchmark

```python
@pytest.mark.asyncio
async def test_surya_gpu_throughput(
    self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
):
    """Measure SuryaGPU throughput (pages per second)."""
    agent = SuryaGPUAgent()
    num_iterations = 5

    # Warm up (Kernel Compilation)
    await agent.process(test_images_dir / "german_text.png")

    # Zeitmessung
    start_time = time.perf_counter()
    for i in range(num_iterations):
        await agent.process(test_images_dir / "german_text.png")

    elapsed = time.perf_counter() - start_time
    throughput = num_iterations / elapsed

    print(f"\nSuryaGPU Throughput: {throughput:.2f} pages/second")

    # Mindestens 1 Seite pro Sekunde
    assert throughput >= 1.0
```

### 4.4 VRAM Threshold Test

```python
@pytest.mark.asyncio
async def test_gpu_batch_processing_memory_efficiency(
    self, gpu_context, requires_8gb_vram, test_images_dir
):
    """GPU-Batch-Verarbeitung sollte unter 85% VRAM bleiben."""
    agent = SuryaGPUAgent()

    # Test mit 32 Bildern (großer Batch)
    images = [test_images_dir / f"image_{i}.png" for i in range(32)]

    torch.cuda.reset_peak_memory_stats()

    for image in images:
        if image.exists():
            await agent.process(image)

    peak_memory = torch.cuda.max_memory_allocated() / 1024**3  # GB

    # 85% von 16GB = 13.6GB
    assert peak_memory < 13.6, f"Peak VRAM {peak_memory:.2f}GB exceeded 85% threshold"
```

### 4.5 Backend Batch Size Test

```python
@pytest.mark.asyncio
async def test_gpu_manager_batch_size_calculation(self, gpu_context):
    """Test GPUManager calculates sensible batch sizes."""
    from app.gpu_manager import GPUManager

    manager = GPUManager()

    # Batch-Größen für verschiedene Backends prüfen
    deepseek_batch = manager.get_optimal_batch_size("deepseek")
    got_ocr_batch = manager.get_optimal_batch_size("got_ocr")
    surya_gpu_batch = manager.get_optimal_batch_size("surya_gpu")
    donut_batch = manager.get_optimal_batch_size("donut")

    # Surya sollte größte Batches erlauben (kleinster Memory Footprint)
    assert surya_gpu_batch >= got_ocr_batch

    # DeepSeek sollte kleinste Batches haben (größter Memory Footprint)
    assert deepseek_batch <= got_ocr_batch

    # Alle Batch-Größen sollten positiv sein
    assert all(b > 0 for b in [deepseek_batch, got_ocr_batch, surya_gpu_batch, donut_batch])
```

---

## 5. OCR Agent Fixtures

### 5.1 Module-Scoped Agent Fixtures

```python
@pytest.fixture(scope="module")
def surya_gpu_agent():
    """Create SuryaGPU agent for testing."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")

    try:
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
        agent = SuryaGPUAgent()
        yield agent
        if hasattr(agent, 'cleanup'):
            import asyncio
            asyncio.get_event_loop().run_until_complete(agent.cleanup())
    except ImportError as e:
        pytest.skip(f"SuryaGPU agent not available: {e}")

@pytest.fixture(scope="module")
def deepseek_agent():
    """Create DeepSeek agent for testing (requires BitsAndBytes)."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch/CUDA not available")

    if sys.platform == "win32":
        pytest.skip("DeepSeek requires BitsAndBytes - run in WSL2/Docker")

    try:
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        agent = DeepSeekAgent()
        yield agent
        if hasattr(agent, 'cleanup'):
            import asyncio
            asyncio.get_event_loop().run_until_complete(agent.cleanup())
    except ImportError as e:
        pytest.skip(f"DeepSeek agent not available: {e}")

@pytest.fixture(scope="module")
def got_ocr_agent():
    """Create GOT-OCR agent for testing."""
    # Similar pattern...

@pytest.fixture(scope="module")
def donut_agent():
    """Create Donut OCR agent."""
    # Similar pattern...
```

### 5.2 Test Image Generation

```python
@pytest.fixture(scope="module")
def test_images_dir(tmp_path_factory) -> Path:
    """Create test images for GPU backend testing."""
    from PIL import Image, ImageDraw

    test_dir = tmp_path_factory.mktemp("gpu_test_images")

    # 1. German Text Image (Invoice-style)
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "RECHNUNG Nr. 2024-001", fill='black')
    draw.text((50, 100), "Müller GmbH & Co. KG", fill='black')
    draw.text((50, 150), "Goethestraße 42, 80336 München", fill='black')
    draw.text((50, 200), "USt-IdNr.: DE123456789", fill='black')
    draw.text((50, 250), "IBAN: DE89 3704 0044 0532 0130 00", fill='black')
    draw.text((50, 350), "Betrag: 1.234,56 EUR", fill='black')
    img.save(test_dir / "german_text.png")

    # 2. Simple Text Image
    img2 = Image.new('RGB', (400, 200), color='white')
    draw2 = ImageDraw.Draw(img2)
    draw2.text((50, 50), "Simple Test", fill='black')
    draw2.text((50, 100), "Hello World", fill='black')
    img2.save(test_dir / "simple_text.png")

    # 3. Complex Layout (Table-like)
    img3 = Image.new('RGB', (800, 600), color='white')
    draw3 = ImageDraw.Draw(img3)
    draw3.rectangle([40, 40, 760, 80], outline='black')
    draw3.text((50, 50), "Pos | Artikel | Menge | Preis | Gesamt", fill='black')
    for i, y in enumerate(range(90, 290, 40), start=1):
        draw3.line([(40, y+40), (760, y+40)], fill='gray')
        draw3.text((50, y), f" {i}  | Produkt {i} | {i*2} | {i*10},00 | {i*20},00", fill='black')
    img3.save(test_dir / "complex_layout.png")

    # 4. Handwritten Style (simulated)
    img4 = Image.new('RGB', (600, 400), color='lightyellow')
    draw4 = ImageDraw.Draw(img4)
    draw4.text((30, 30), "Notizen:", fill='darkblue')
    draw4.text((30, 80), "- Termin am 15.03.2025", fill='darkblue')
    draw4.text((30, 120), "- Müller anrufen", fill='darkblue')
    img4.save(test_dir / "handwritten.png")

    return test_dir
```

---

## 6. Skip-Conditions und Collection Modifier

### 6.1 Collection Modifier

```python
# tests/gpu/conftest.py
pytestmark = pytest.mark.gpu

def pytest_collection_modifyitems(config, items):
    """Skip GPU tests if GPU not available."""
    if not TORCH_AVAILABLE:
        skip_gpu = pytest.mark.skip(reason="GPU not available")
        for item in items:
            if "gpu" in item.keywords:
                item.add_marker(skip_gpu)
```

### 6.2 Decorator-basierte Skips

```python
@pytest.mark.skipif(
    True,  # Skip until GOT-OCR transformers image token issue is resolved
    reason="GOT-OCR has image token mismatch issue on Windows - run in WSL2/Docker"
)
async def test_got_ocr_specific_feature(self):
    """Test that requires WSL2/Docker."""
    pass
```

---

## 7. CI/CD GPU-Integration

### 7.1 GitHub Actions Konfiguration

```yaml
# .github/workflows/ci.yml
test-unit:
  name: Unit Tests
  runs-on: ubuntu-latest

  services:
    postgres:
      image: postgres:16-alpine
    redis:
      image: redis:7-alpine

  steps:
    - name: Run Unit Tests (excluding GPU)
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost:5432/ablage_test
        REDIS_URL: redis://localhost:6379/0
        TESTING: true
      run: |
        pytest tests/unit/ -v --tb=short --cov=app --cov-report=xml -m "not gpu"
```

### 7.2 Lokale GPU-Tests

```bash
# Alle GPU-Tests ausführen
pytest tests/gpu/ -v -m gpu

# Spezifisches Backend testen
pytest tests/gpu/test_surya_gpu_backend.py -v

# Mit Memory Tracking
pytest tests/gpu/ -v --tb=long

# GPU-Status vorher prüfen
nvidia-smi
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

---

## 8. Performance Benchmarks

### 8.1 Ziel-Werte

| Backend | Throughput | Latency P95 | VRAM Max |
|---------|------------|-------------|----------|
| DeepSeek | 2-3 pps | 2000ms | 12GB |
| GOT-OCR | 5-7 pps | 1500ms | 10GB |
| Surya GPU | 1-2 pps | 2500ms | 8GB |
| Donut | 3-5 pps | 1800ms | 8GB |

### 8.2 Benchmark-Test

```python
class BenchmarkConfig:
    # Throughput targets (pages/second)
    THROUGHPUT_TARGETS = {
        "deepseek": 2.5,
        "got_ocr": 6.0,
        "surya": 1.5,
    }

    # Latency targets (milliseconds)
    LATENCY_TARGETS = {
        "p50": 1000,
        "p95": 2000,
        "p99": 5000,
    }

    # GPU Memory limit (RTX 4080 optimization)
    GPU_MEMORY_LIMIT_GB = 13.6  # 85% of 16GB
```

---

## 9. GPU Recovery Manager

### 9.1 Backend Konfiguration

```python
from dataclasses import dataclass

@dataclass
class GPUBackendConfig:
    """Configuration for GPU backend memory management."""
    default_batch_size: int
    min_batch_size: int = 1
    max_batch_size: int = 32
    vram_gb: float = 0.0
    reduction_factor: float = 0.5

BACKEND_CONFIGS = {
    "deepseek": GPUBackendConfig(
        default_batch_size=4,
        min_batch_size=1,
        max_batch_size=8,
        vram_gb=12.0,
        reduction_factor=0.5,
    ),
    "got_ocr": GPUBackendConfig(
        default_batch_size=8,
        min_batch_size=1,
        max_batch_size=16,
        vram_gb=10.0,
        reduction_factor=0.5,
    ),
    "surya_gpu": GPUBackendConfig(
        default_batch_size=16,
        min_batch_size=2,
        max_batch_size=32,
        vram_gb=8.0,
        reduction_factor=0.5,
    ),
}

MAX_VRAM_USAGE_GB = 13.6  # 85% of RTX 4080's 16GB
```

### 9.2 Recovery Manager Tests

```python
class TestGPURecoveryManager:

    def test_get_memory_stats(self, gpu_context):
        """Test memory statistics retrieval."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()
        stats = manager.get_memory_stats()

        assert 0 <= stats.utilization_percent <= 100
        assert stats.total_gb > 0

    async def test_clear_gpu_memory(self, gpu_context):
        """Test GPU memory clearing."""
        manager = GPURecoveryManager()

        before = torch.cuda.memory_allocated()
        await manager.clear_gpu_memory()
        after = torch.cuda.memory_allocated()

        assert after <= before

    def test_get_optimal_batch_size(self, gpu_context):
        """Test dynamic batch size calculation."""
        manager = GPURecoveryManager()

        batch = manager.get_optimal_batch_size("surya_gpu")
        assert batch > 0
        assert batch <= BACKEND_CONFIGS["surya_gpu"].max_batch_size
```

---

## 10. Troubleshooting

### 10.1 GPU nicht erkannt

```bash
# NVIDIA Treiber prüfen
nvidia-smi

# CUDA in Python prüfen
python -c "import torch; print(torch.cuda.is_available())"

# Container GPU-Zugriff prüfen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 10.2 OOM-Fehler

```python
# Memory vor Test bereinigen
torch.cuda.empty_cache()
torch.cuda.synchronize()
gc.collect()

# Batch-Größe reduzieren
manager.reduce_batch_size("deepseek")
```

### 10.3 Langsame Tests

```python
# Profiling aktivieren
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()
result = ocr_backend.process(image)
profiler.disable()

stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

---

## 11. Best Practices

### 11.1 Test-Isolation

- Jeder Test sollte GPU-Speicher vor und nach dem Test bereinigen
- Module-scoped Fixtures für OCR-Agents (Model-Loading ist teuer)
- Function-scoped für Memory-Tracking

### 11.2 Skip-Strategie

- Automatisch skippen wenn GPU nicht verfügbar
- VRAM-basierte Skips für speicherintensive Tests
- Plattform-spezifische Skips (Windows vs Linux)

### 11.3 Memory Management

- 85% VRAM-Threshold (13.6GB von 16GB) niemals überschreiten
- Memory Leaks über mehrere Iterationen testen
- Garbage Collection nach großen Operations erzwingen

### 11.4 Warm-Up

- Erste Inference nach Model-Loading ist langsam (Kernel Compilation)
- Warm-Up-Run vor Performance-Messungen
- Model im Inference-Modus setzen

---

## Zusammenfassung

Das GPU-Testing-Framework ermöglicht:
- **Robuste Tests** mit automatischen Skip-Conditions
- **Memory-Tracking** zur Leak-Detection
- **Performance-Benchmarks** mit definierten Ziel-Werten
- **Mock-Patterns** für Unit-Tests ohne GPU
- **CI/CD-Integration** mit graceful degradation

Kritische Schwellwerte:
- **13.6 GB** - Maximale VRAM-Nutzung (85%)
- **1 pps** - Mindest-Throughput
- **5s** - Maximale Latenz P99
