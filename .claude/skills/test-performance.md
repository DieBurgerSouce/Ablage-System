---
name: test-performance
description: Performance und Load Tests fuer das Ablage-System. Nutze diesen Skill fuer OCR Benchmarks, GPU Memory Profiling, Locust Load Tests und Performance-Metriken. Identifiziere Bottlenecks und optimiere.
---

# Performance Testing (Ablage-System)

Performance, Load und Stress Tests fuer das Ablage-System.

## Quick Commands

```bash
# Performance Tests
docker-compose exec backend pytest tests/performance/ -v

# OCR Benchmark
docker-compose exec backend python -m pytest tests/performance/test_ocr_benchmark.py -v

# GPU Memory Profiling
docker-compose exec worker python -m torch.utils.bottleneck app/services/ocr_service.py
```

## Test-Struktur

```
tests/performance/
├── conftest.py              # Performance Fixtures
├── test_ocr_benchmark.py    # OCR Speed Tests
├── test_api_latency.py      # API Response Times
├── test_gpu_memory.py       # VRAM Nutzung
└── locustfile.py            # Load Tests
```

## OCR Benchmarks

```python
# tests/performance/test_ocr_benchmark.py
import pytest
import time
from app.services.ocr.orchestrator import OCROrchestrator

@pytest.mark.benchmark
@pytest.mark.parametrize("backend", ["deepseek", "got_ocr", "surya"])
def test_ocr_speed_single_page(benchmark, backend, sample_pdf_page):
    """Benchmark: Einzelne Seite pro Backend."""
    ocr = OCROrchestrator()

    def process():
        return ocr.process(sample_pdf_page, backend=backend)

    result = benchmark(process)

    assert result.text is not None
    # Erwartete Zeiten (RTX 4080):
    # - DeepSeek: < 500ms
    # - GOT-OCR: < 200ms
    # - Surya GPU: < 300ms

@pytest.mark.benchmark
def test_ocr_batch_throughput(benchmark, sample_pdf_pages):
    """Benchmark: Batch-Verarbeitung (32 Seiten)."""
    ocr = OCROrchestrator()

    def process_batch():
        return [ocr.process(page) for page in sample_pdf_pages[:32]]

    result = benchmark(process_batch)

    assert len(result) == 32

@pytest.mark.benchmark
def test_german_text_accuracy(sample_german_documents):
    """Benchmark: Umlaut-Genauigkeit."""
    ocr = OCROrchestrator()
    expected_umlauts = ["ä", "ö", "ü", "ß"]

    results = []
    for doc in sample_german_documents:
        text = ocr.process(doc).text
        accuracy = sum(1 for u in expected_umlauts if u in text) / len(expected_umlauts)
        results.append(accuracy)

    avg_accuracy = sum(results) / len(results)
    assert avg_accuracy >= 0.95  # 95% Umlaut-Genauigkeit
```

## GPU Memory Tests

```python
# tests/performance/test_gpu_memory.py
import pytest
import torch

@pytest.mark.gpu
def test_gpu_memory_stays_under_limit():
    """VRAM sollte unter 85% (13.6GB) bleiben."""
    from app.services.ocr.deepseek import DeepSeekOCR

    ocr = DeepSeekOCR()
    images = load_test_images(count=32)  # Grosser Batch

    torch.cuda.reset_peak_memory_stats()

    # Verarbeiten
    results = ocr.process_batch(images)

    peak_memory_gb = torch.cuda.max_memory_allocated() / 1024**3

    assert peak_memory_gb < 13.6  # 85% von 16GB
    assert len(results) == 32

@pytest.mark.gpu
def test_gpu_memory_cleanup():
    """GPU-Speicher sollte nach Verarbeitung freigegeben werden."""
    initial_memory = torch.cuda.memory_allocated()

    # Schwere Operation
    from app.services.ocr.deepseek import DeepSeekOCR
    ocr = DeepSeekOCR()
    _ = ocr.process(large_image)

    # Cleanup
    torch.cuda.empty_cache()

    final_memory = torch.cuda.memory_allocated()

    # Sollte nicht mehr als 500MB ueber Initial sein
    assert (final_memory - initial_memory) / 1024**3 < 0.5
```

## API Latency Tests

```python
# tests/performance/test_api_latency.py
import pytest
import asyncio
import time

@pytest.mark.performance
@pytest.mark.asyncio
async def test_api_health_latency(client):
    """Health Endpoint sollte < 50ms antworten."""
    times = []

    for _ in range(100):
        start = time.perf_counter()
        response = await client.get("/health")
        elapsed = (time.perf_counter() - start) * 1000  # ms

        assert response.status_code == 200
        times.append(elapsed)

    p95 = sorted(times)[94]  # 95th percentile
    assert p95 < 50  # < 50ms

@pytest.mark.performance
@pytest.mark.asyncio
async def test_api_document_retrieval_latency(client, sample_documents):
    """Dokument-Abruf sollte < 100ms (cached) / < 300ms (DB) sein."""
    times = []

    for doc_id in sample_documents[:50]:
        start = time.perf_counter()
        response = await client.get(f"/api/v1/documents/{doc_id}")
        elapsed = (time.perf_counter() - start) * 1000

        times.append(elapsed)

    p95 = sorted(times)[47]
    assert p95 < 300  # < 300ms (95th percentile)
```

## Locust Load Tests

```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between

class AblageUser(HttpUser):
    """Simulierter Benutzer fuer Load Tests."""
    wait_time = between(1, 3)

    @task(3)
    def get_documents(self):
        """Dokumente auflisten (haeufig)."""
        self.client.get("/api/v1/documents/")

    @task(2)
    def get_single_document(self):
        """Einzelnes Dokument abrufen."""
        self.client.get("/api/v1/documents/test-id")

    @task(1)
    def upload_document(self):
        """Dokument hochladen (selten)."""
        files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
        self.client.post("/api/v1/documents/", files=files)

    @task(1)
    def health_check(self):
        """Health Check."""
        self.client.get("/health")
```

## Locust ausfuehren

```bash
# Lokal (mit Docker)
docker-compose exec backend locust -f tests/performance/locustfile.py \
    --host=http://backend:8000 \
    --users=100 \
    --spawn-rate=10 \
    --run-time=5m

# Web UI
# http://localhost:8089
```

## Performance-Ziele

| Metrik | Ziel | Kritisch |
|--------|------|----------|
| Health Check | < 50ms (p95) | Ja |
| Document Retrieval | < 300ms (p95) | Ja |
| OCR Single Page | < 2s (GPU) | Ja |
| OCR Batch (32) | < 30s (GPU) | Ja |
| API RPS | > 1000 | Ja |
| GPU Memory | < 85% (13.6GB) | Ja |

## Profiling

```bash
# Python Profiling
docker-compose exec backend python -m cProfile -o profile.stats app/main.py

# GPU Profiling
docker-compose exec worker python -m torch.profiler ...

# Memory Profiling
docker-compose exec backend python -m memory_profiler app/services/ocr_service.py
```

## Metriken sammeln

```python
# Performance-Metriken mit Prometheus
from prometheus_client import Histogram

ocr_duration = Histogram(
    'ocr_processing_duration_seconds',
    'OCR processing time',
    ['backend'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Nutzung
with ocr_duration.labels(backend='deepseek').time():
    result = ocr.process(document)
```

## Grafana Dashboards

- **API Performance**: http://localhost:3002/d/api-performance
- **OCR Benchmarks**: http://localhost:3002/d/ocr-benchmarks
- **GPU Metrics**: http://localhost:3002/d/gpu-metrics

## Stress Tests

```python
# tests/performance/test_stress.py
import pytest
import asyncio

@pytest.mark.stress
@pytest.mark.asyncio
async def test_concurrent_uploads(client):
    """100 gleichzeitige Uploads."""
    async def upload():
        files = {"file": ("test.pdf", b"PDF", "application/pdf")}
        return await client.post("/api/v1/documents/", files=files)

    tasks = [upload() for _ in range(100)]
    results = await asyncio.gather(*tasks)

    success_rate = sum(1 for r in results if r.status_code == 201) / 100
    assert success_rate >= 0.95  # 95% Erfolgsrate

@pytest.mark.stress
@pytest.mark.asyncio
async def test_sustained_load(client):
    """Dauerlast ueber 5 Minuten."""
    import time
    start = time.time()
    errors = 0

    while time.time() - start < 300:  # 5 Minuten
        response = await client.get("/health")
        if response.status_code != 200:
            errors += 1
        await asyncio.sleep(0.1)

    error_rate = errors / 3000  # ~3000 Requests in 5 Min
    assert error_rate < 0.01  # < 1% Fehlerrate
```

## Markers

```python
@pytest.mark.benchmark    # Benchmark Test
@pytest.mark.performance  # Performance Test
@pytest.mark.stress       # Stress Test
@pytest.mark.gpu          # Braucht GPU
@pytest.mark.slow         # Laeuft > 30s
```
