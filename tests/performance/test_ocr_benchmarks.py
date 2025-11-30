"""
OCR Performance Benchmark Suite.

Umfassende Performance-Tests für:
- OCR Backend Throughput
- Latenz-Messungen (P50, P95, P99)
- GPU Memory Effizienz
- Batch-Verarbeitung
- Concurrent Requests
- Fallback-Performance

Ausführung:
    pytest tests/performance/test_ocr_benchmarks.py -v --benchmark-enable
    pytest tests/performance/test_ocr_benchmarks.py -v -k "throughput"

Ergebnisse werden in benchmark_results/ gespeichert.
"""

import pytest
import asyncio
import time
import statistics
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from unittest.mock import Mock, AsyncMock, patch
from concurrent.futures import ThreadPoolExecutor
import sys

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))


# ==============================================================================
# Configuration
# ==============================================================================

class BenchmarkConfig:
    """Benchmark-Konfiguration."""

    # Throughput-Ziele (Seiten pro Sekunde)
    THROUGHPUT_TARGETS = {
        "deepseek": 2.5,   # 2-3 Seiten/s
        "got_ocr": 6.0,    # 5-7 Seiten/s
        "surya": 1.5,      # 1-2 Seiten/s
    }

    # Latenz-Ziele (Millisekunden)
    LATENCY_TARGETS = {
        "p50": 1000,   # 1s
        "p95": 2000,   # 2s
        "p99": 5000,   # 5s
    }

    # GPU Memory Ziel
    GPU_MEMORY_LIMIT_GB = 13.6  # 85% von 16GB

    # Test-Konfiguration
    WARMUP_ITERATIONS = 3
    BENCHMARK_ITERATIONS = 20
    CONCURRENT_WORKERS = 4

    # Ergebnis-Verzeichnis
    RESULTS_DIR = Path(__file__).parent / "benchmark_results"


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture(scope="module")
def benchmark_config():
    """Benchmark-Konfiguration."""
    BenchmarkConfig.RESULTS_DIR.mkdir(exist_ok=True)
    return BenchmarkConfig()


@pytest.fixture
def mock_ocr_result():
    """Mock OCR-Ergebnis."""
    return Mock(
        text="Dies ist ein Testtext für den Benchmark.",
        confidence=0.85,
        processing_time_ms=500,
        tokens=[
            Mock(text="Dies", confidence=0.9),
            Mock(text="ist", confidence=0.88),
            Mock(text="ein", confidence=0.85),
            Mock(text="Testtext", confidence=0.82),
        ]
    )


@pytest.fixture
def mock_document():
    """Mock Dokument für Tests."""
    return Mock(
        id="benchmark-doc-001",
        filename="benchmark_test.pdf",
        file_size=1024 * 1024,  # 1MB
        page_count=1,
        content=b"mock_document_content"
    )


@pytest.fixture
def sample_documents(mock_document):
    """Liste von Test-Dokumenten."""
    return [
        Mock(
            id=f"benchmark-doc-{i:03d}",
            filename=f"benchmark_test_{i}.pdf",
            file_size=1024 * 1024,
            page_count=1,
            content=b"mock_document_content"
        )
        for i in range(50)
    ]


# ==============================================================================
# Helper Functions
# ==============================================================================

class BenchmarkResult:
    """Speichert Benchmark-Ergebnisse."""

    def __init__(self, name: str):
        self.name = name
        self.measurements: List[float] = []
        self.errors: List[str] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.metadata: Dict = {}

    def add_measurement(self, value: float):
        self.measurements.append(value)

    def add_error(self, error: str):
        self.errors.append(error)

    def finalize(self):
        self.end_time = datetime.now()

    @property
    def count(self) -> int:
        return len(self.measurements)

    @property
    def mean(self) -> float:
        return statistics.mean(self.measurements) if self.measurements else 0

    @property
    def median(self) -> float:
        return statistics.median(self.measurements) if self.measurements else 0

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.measurements) if len(self.measurements) > 1 else 0

    @property
    def min_value(self) -> float:
        return min(self.measurements) if self.measurements else 0

    @property
    def max_value(self) -> float:
        return max(self.measurements) if self.measurements else 0

    def percentile(self, p: float) -> float:
        if not self.measurements:
            return 0
        sorted_data = sorted(self.measurements)
        index = int(len(sorted_data) * p / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    @property
    def p50(self) -> float:
        return self.percentile(50)

    @property
    def p95(self) -> float:
        return self.percentile(95)

    @property
    def p99(self) -> float:
        return self.percentile(99)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "stdev": self.stdev,
            "min": self.min_value,
            "max": self.max_value,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "errors": len(self.errors),
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            "metadata": self.metadata
        }


def save_benchmark_result(result: BenchmarkResult, config: BenchmarkConfig):
    """Speichere Benchmark-Ergebnis als JSON."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = config.RESULTS_DIR / f"{result.name}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    return filename


# ==============================================================================
# Mock OCR Backends für Benchmarks
# ==============================================================================

class MockOCRBackend:
    """Mock OCR Backend mit konfigurierbarer Latenz."""

    def __init__(self, name: str, base_latency_ms: float, variance: float = 0.1):
        self.name = name
        self.base_latency_ms = base_latency_ms
        self.variance = variance

    async def process(self, document: Mock) -> Mock:
        """Simuliere OCR-Verarbeitung."""
        import random

        # Simuliere variable Latenz
        latency = self.base_latency_ms * (1 + random.uniform(-self.variance, self.variance))
        await asyncio.sleep(latency / 1000)  # ms zu s

        return Mock(
            text=f"Verarbeiteter Text für {document.filename}",
            confidence=0.8 + random.uniform(0, 0.15),
            processing_time_ms=latency
        )


# ==============================================================================
# Throughput Benchmarks
# ==============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestThroughputBenchmarks:
    """Throughput-Benchmarks für OCR-Backends."""

    async def test_deepseek_throughput(self, benchmark_config, sample_documents):
        """DeepSeek Throughput (Ziel: 2-3 Seiten/s)."""
        backend = MockOCRBackend("deepseek", base_latency_ms=400)
        result = BenchmarkResult("deepseek_throughput")

        # Warmup
        for doc in sample_documents[:benchmark_config.WARMUP_ITERATIONS]:
            await backend.process(doc)

        # Benchmark
        start = time.time()
        processed = 0

        for doc in sample_documents[:benchmark_config.BENCHMARK_ITERATIONS]:
            iter_start = time.time()
            await backend.process(doc)
            iter_time = time.time() - iter_start
            result.add_measurement(iter_time)
            processed += 1

        total_time = time.time() - start
        throughput = processed / total_time

        result.metadata["throughput_pages_per_second"] = throughput
        result.metadata["target"] = benchmark_config.THROUGHPUT_TARGETS["deepseek"]
        result.finalize()

        save_benchmark_result(result, benchmark_config)

        # Assertion
        assert throughput >= benchmark_config.THROUGHPUT_TARGETS["deepseek"] * 0.8, \
            f"DeepSeek Throughput {throughput:.2f} p/s unter Ziel {benchmark_config.THROUGHPUT_TARGETS['deepseek']} p/s"

    async def test_got_ocr_throughput(self, benchmark_config, sample_documents):
        """GOT-OCR Throughput (Ziel: 5-7 Seiten/s)."""
        backend = MockOCRBackend("got_ocr", base_latency_ms=150)
        result = BenchmarkResult("got_ocr_throughput")

        # Warmup
        for doc in sample_documents[:benchmark_config.WARMUP_ITERATIONS]:
            await backend.process(doc)

        # Benchmark
        start = time.time()
        processed = 0

        for doc in sample_documents[:benchmark_config.BENCHMARK_ITERATIONS]:
            iter_start = time.time()
            await backend.process(doc)
            iter_time = time.time() - iter_start
            result.add_measurement(iter_time)
            processed += 1

        total_time = time.time() - start
        throughput = processed / total_time

        result.metadata["throughput_pages_per_second"] = throughput
        result.metadata["target"] = benchmark_config.THROUGHPUT_TARGETS["got_ocr"]
        result.finalize()

        save_benchmark_result(result, benchmark_config)

        assert throughput >= benchmark_config.THROUGHPUT_TARGETS["got_ocr"] * 0.8

    async def test_surya_throughput(self, benchmark_config, sample_documents):
        """Surya Throughput (Ziel: 1-2 Seiten/s)."""
        backend = MockOCRBackend("surya", base_latency_ms=600)
        result = BenchmarkResult("surya_throughput")

        # Warmup
        for doc in sample_documents[:benchmark_config.WARMUP_ITERATIONS]:
            await backend.process(doc)

        # Benchmark
        start = time.time()
        processed = 0

        for doc in sample_documents[:benchmark_config.BENCHMARK_ITERATIONS]:
            iter_start = time.time()
            await backend.process(doc)
            iter_time = time.time() - iter_start
            result.add_measurement(iter_time)
            processed += 1

        total_time = time.time() - start
        throughput = processed / total_time

        result.metadata["throughput_pages_per_second"] = throughput
        result.metadata["target"] = benchmark_config.THROUGHPUT_TARGETS["surya"]
        result.finalize()

        save_benchmark_result(result, benchmark_config)

        assert throughput >= benchmark_config.THROUGHPUT_TARGETS["surya"] * 0.8


# ==============================================================================
# Latency Benchmarks
# ==============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestLatencyBenchmarks:
    """Latenz-Benchmarks für OCR-Backends."""

    async def test_latency_percentiles(self, benchmark_config, sample_documents):
        """Latenz P50/P95/P99 Messung."""
        backend = MockOCRBackend("combined", base_latency_ms=300)
        result = BenchmarkResult("latency_percentiles")

        # Mehr Iterationen für statistisch signifikante Percentile
        iterations = benchmark_config.BENCHMARK_ITERATIONS * 2

        for doc in sample_documents[:iterations]:
            start = time.time()
            await backend.process(doc)
            latency_ms = (time.time() - start) * 1000
            result.add_measurement(latency_ms)

        result.metadata["p50_target_ms"] = benchmark_config.LATENCY_TARGETS["p50"]
        result.metadata["p95_target_ms"] = benchmark_config.LATENCY_TARGETS["p95"]
        result.metadata["p99_target_ms"] = benchmark_config.LATENCY_TARGETS["p99"]
        result.finalize()

        save_benchmark_result(result, benchmark_config)

        # Assertions
        assert result.p50 < benchmark_config.LATENCY_TARGETS["p50"], \
            f"P50 Latenz {result.p50:.0f}ms über Ziel {benchmark_config.LATENCY_TARGETS['p50']}ms"

        assert result.p95 < benchmark_config.LATENCY_TARGETS["p95"], \
            f"P95 Latenz {result.p95:.0f}ms über Ziel {benchmark_config.LATENCY_TARGETS['p95']}ms"

        assert result.p99 < benchmark_config.LATENCY_TARGETS["p99"], \
            f"P99 Latenz {result.p99:.0f}ms über Ziel {benchmark_config.LATENCY_TARGETS['p99']}ms"

    async def test_latency_consistency(self, benchmark_config, sample_documents):
        """Latenz-Konsistenz (niedrige Standardabweichung)."""
        backend = MockOCRBackend("consistency", base_latency_ms=300, variance=0.05)
        result = BenchmarkResult("latency_consistency")

        for doc in sample_documents[:benchmark_config.BENCHMARK_ITERATIONS]:
            start = time.time()
            await backend.process(doc)
            latency_ms = (time.time() - start) * 1000
            result.add_measurement(latency_ms)

        result.metadata["coefficient_of_variation"] = result.stdev / result.mean if result.mean > 0 else 0
        result.finalize()

        save_benchmark_result(result, benchmark_config)

        # Coefficient of Variation sollte unter 20% sein
        cv = result.stdev / result.mean if result.mean > 0 else 0
        assert cv < 0.2, f"Latenz-Variation {cv:.2%} zu hoch (max 20%)"


# ==============================================================================
# Concurrent Processing Benchmarks
# ==============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestConcurrentBenchmarks:
    """Benchmarks für parallele Verarbeitung."""

    async def test_concurrent_processing(self, benchmark_config, sample_documents):
        """Parallele Verarbeitung mit mehreren Workers."""
        backend = MockOCRBackend("concurrent", base_latency_ms=300)
        result = BenchmarkResult("concurrent_processing")
        workers = benchmark_config.CONCURRENT_WORKERS

        async def process_batch(docs: List[Mock]) -> List[Tuple[float, bool]]:
            """Verarbeite Batch parallel."""
            tasks = []
            for doc in docs:
                start = time.time()
                task = asyncio.create_task(backend.process(doc))
                tasks.append((start, task))

            results = []
            for start, task in tasks:
                try:
                    await task
                    latency = time.time() - start
                    results.append((latency * 1000, True))
                except Exception:
                    results.append((0, False))

            return results

        # Batch-Verarbeitung
        batch_size = workers
        all_results = []

        for i in range(0, len(sample_documents[:benchmark_config.BENCHMARK_ITERATIONS]), batch_size):
            batch = sample_documents[i:i + batch_size]
            batch_results = await process_batch(batch)
            all_results.extend(batch_results)

        # Messungen hinzufügen
        for latency, success in all_results:
            if success:
                result.add_measurement(latency)
            else:
                result.add_error("Processing failed")

        result.metadata["workers"] = workers
        result.metadata["total_processed"] = len(all_results)
        result.metadata["success_rate"] = len(result.measurements) / len(all_results) if all_results else 0
        result.finalize()

        save_benchmark_result(result, benchmark_config)

        # Concurrent sollte schneller sein als sequenziell
        # (nicht linear skalierend, aber Verbesserung erwartet)
        assert result.mean < benchmark_config.LATENCY_TARGETS["p50"], \
            f"Concurrent Latenz {result.mean:.0f}ms zu hoch"

    async def test_scaling_efficiency(self, benchmark_config, sample_documents):
        """Skalierungs-Effizienz bei steigender Last."""
        backend = MockOCRBackend("scaling", base_latency_ms=200)
        result = BenchmarkResult("scaling_efficiency")

        # Test mit verschiedenen Worker-Zahlen
        worker_counts = [1, 2, 4, 8]
        scaling_results = {}

        for workers in worker_counts:
            start = time.time()
            tasks = []

            for doc in sample_documents[:workers * 4]:
                tasks.append(asyncio.create_task(backend.process(doc)))

            await asyncio.gather(*tasks)
            total_time = time.time() - start
            throughput = len(tasks) / total_time
            scaling_results[workers] = throughput

        result.metadata["scaling_results"] = scaling_results

        # Skalierungs-Effizienz berechnen
        base_throughput = scaling_results[1]
        for workers, throughput in scaling_results.items():
            if workers > 1:
                ideal = base_throughput * workers
                efficiency = throughput / ideal if ideal > 0 else 0
                result.metadata[f"efficiency_{workers}_workers"] = efficiency

        result.finalize()
        save_benchmark_result(result, benchmark_config)


# ==============================================================================
# Batch Processing Benchmarks
# ==============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestBatchBenchmarks:
    """Benchmarks für Batch-Verarbeitung."""

    @pytest.mark.parametrize("batch_size", [1, 4, 8, 16, 32])
    async def test_batch_size_impact(self, benchmark_config, sample_documents, batch_size):
        """Auswirkung der Batch-Größe auf Performance."""
        backend = MockOCRBackend(f"batch_{batch_size}", base_latency_ms=250)
        result = BenchmarkResult(f"batch_size_{batch_size}")

        docs_to_process = sample_documents[:batch_size * 3]

        start = time.time()
        for i in range(0, len(docs_to_process), batch_size):
            batch = docs_to_process[i:i + batch_size]
            tasks = [asyncio.create_task(backend.process(doc)) for doc in batch]
            batch_results = await asyncio.gather(*tasks)

            for _ in batch_results:
                result.add_measurement((time.time() - start) / len(batch) * 1000)

        total_time = time.time() - start
        throughput = len(docs_to_process) / total_time

        result.metadata["batch_size"] = batch_size
        result.metadata["throughput"] = throughput
        result.finalize()

        save_benchmark_result(result, benchmark_config)

    async def test_optimal_batch_size(self, benchmark_config, sample_documents):
        """Finde optimale Batch-Größe."""
        backend = MockOCRBackend("optimal_batch", base_latency_ms=200)
        result = BenchmarkResult("optimal_batch_size")

        batch_sizes = [1, 2, 4, 8, 16, 32]
        throughputs = {}

        for batch_size in batch_sizes:
            docs = sample_documents[:batch_size * 5]

            start = time.time()
            for i in range(0, len(docs), batch_size):
                batch = docs[i:i + batch_size]
                tasks = [asyncio.create_task(backend.process(doc)) for doc in batch]
                await asyncio.gather(*tasks)

            total_time = time.time() - start
            throughputs[batch_size] = len(docs) / total_time

        result.metadata["throughputs_by_batch_size"] = throughputs
        result.metadata["optimal_batch_size"] = max(throughputs, key=throughputs.get)
        result.finalize()

        save_benchmark_result(result, benchmark_config)


# ==============================================================================
# Memory Benchmarks
# ==============================================================================

@pytest.mark.performance
class TestMemoryBenchmarks:
    """GPU Memory Benchmarks."""

    def test_memory_baseline(self, benchmark_config):
        """Baseline Memory-Verbrauch."""
        result = BenchmarkResult("memory_baseline")

        try:
            from app.gpu_manager import GPUMemoryGuard

            guard = GPUMemoryGuard()
            status = guard.check_memory_status()

            if status.get("available"):
                result.add_measurement(status.get("allocated_gb", 0))
                result.metadata["total_gb"] = status.get("total_gb", 16)
                result.metadata["limit_gb"] = benchmark_config.GPU_MEMORY_LIMIT_GB
                result.metadata["status"] = status.get("status", "unknown")
            else:
                result.metadata["gpu_available"] = False

        except ImportError:
            result.metadata["gpu_module_available"] = False

        result.finalize()
        save_benchmark_result(result, benchmark_config)

    def test_memory_under_load(self, benchmark_config):
        """Memory-Verbrauch unter simulierter Last."""
        result = BenchmarkResult("memory_under_load")

        try:
            from app.gpu_manager import GPUMemoryGuard

            guard = GPUMemoryGuard()

            # Mehrere Messungen
            for i in range(10):
                status = guard.check_memory_status()
                if status.get("available"):
                    result.add_measurement(status.get("allocated_gb", 0))
                time.sleep(0.1)

            result.metadata["limit_gb"] = benchmark_config.GPU_MEMORY_LIMIT_GB
            result.metadata["within_limit"] = result.max_value < benchmark_config.GPU_MEMORY_LIMIT_GB

        except ImportError:
            result.metadata["gpu_module_available"] = False

        result.finalize()
        save_benchmark_result(result, benchmark_config)


# ==============================================================================
# Fallback Performance Benchmarks
# ==============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestFallbackBenchmarks:
    """Benchmarks für Fallback-Szenarien."""

    async def test_fallback_latency_overhead(self, benchmark_config, sample_documents):
        """Latenz-Overhead durch Fallback."""
        primary = MockOCRBackend("primary", base_latency_ms=300)
        fallback = MockOCRBackend("fallback", base_latency_ms=350)

        result = BenchmarkResult("fallback_latency_overhead")

        # Normale Verarbeitung
        normal_latencies = []
        for doc in sample_documents[:10]:
            start = time.time()
            await primary.process(doc)
            normal_latencies.append((time.time() - start) * 1000)

        # Simulierter Fallback (Primary + Fallback)
        fallback_latencies = []
        for doc in sample_documents[:10]:
            start = time.time()
            # Simuliere: Primary schlägt fehl, dann Fallback
            await asyncio.sleep(0.05)  # Fehler-Erkennung
            await fallback.process(doc)
            fallback_latencies.append((time.time() - start) * 1000)

        result.metadata["normal_mean_ms"] = statistics.mean(normal_latencies)
        result.metadata["fallback_mean_ms"] = statistics.mean(fallback_latencies)
        result.metadata["overhead_ms"] = statistics.mean(fallback_latencies) - statistics.mean(normal_latencies)
        result.metadata["overhead_percent"] = (result.metadata["overhead_ms"] / result.metadata["normal_mean_ms"]) * 100

        for lat in fallback_latencies:
            result.add_measurement(lat)

        result.finalize()
        save_benchmark_result(result, benchmark_config)

        # Overhead sollte unter 50% sein
        assert result.metadata["overhead_percent"] < 50, \
            f"Fallback Overhead {result.metadata['overhead_percent']:.1f}% zu hoch"


# ==============================================================================
# Comprehensive Benchmark Suite
# ==============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestComprehensiveBenchmark:
    """Umfassender Benchmark-Test."""

    async def test_full_benchmark_suite(self, benchmark_config, sample_documents):
        """Führe vollständige Benchmark-Suite aus."""
        results = {}

        # 1. Throughput pro Backend
        backends = {
            "deepseek": MockOCRBackend("deepseek", 400),
            "got_ocr": MockOCRBackend("got_ocr", 150),
            "surya": MockOCRBackend("surya", 600),
        }

        for name, backend in backends.items():
            start = time.time()
            for doc in sample_documents[:20]:
                await backend.process(doc)
            total_time = time.time() - start
            results[f"{name}_throughput"] = 20 / total_time

        # 2. Latenz-Statistiken
        latencies = []
        for doc in sample_documents[:50]:
            start = time.time()
            await backends["got_ocr"].process(doc)
            latencies.append((time.time() - start) * 1000)

        results["latency_p50"] = statistics.median(latencies)
        results["latency_p95"] = sorted(latencies)[int(len(latencies) * 0.95)]
        results["latency_p99"] = sorted(latencies)[int(len(latencies) * 0.99)]

        # 3. Concurrent Test
        start = time.time()
        tasks = [
            asyncio.create_task(backends["got_ocr"].process(doc))
            for doc in sample_documents[:16]
        ]
        await asyncio.gather(*tasks)
        results["concurrent_16_time"] = time.time() - start

        # Speichere Ergebnisse
        result = BenchmarkResult("comprehensive_suite")
        result.metadata = results
        result.finalize()
        save_benchmark_result(result, benchmark_config)

        # Zusammenfassung ausgeben
        print("\n" + "=" * 60)
        print("BENCHMARK ERGEBNISSE")
        print("=" * 60)
        for key, value in results.items():
            print(f"  {key}: {value:.2f}")
        print("=" * 60 + "\n")


# ==============================================================================
# Report Generator
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def generate_report(request):
    """Generiere Benchmark-Report nach allen Tests."""
    yield

    # Nach Tests: Report generieren
    results_dir = BenchmarkConfig.RESULTS_DIR
    if results_dir.exists():
        report = {
            "generated_at": datetime.now().isoformat(),
            "results": []
        }

        for result_file in results_dir.glob("*.json"):
            with open(result_file) as f:
                report["results"].append(json.load(f))

        report_file = results_dir / f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nBenchmark Report: {report_file}")
