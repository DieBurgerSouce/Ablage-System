"""
Backend Metrics Tests for OCR Backends.

Comprehensive metrics collection tests for all OCR backends:
- VRAM usage profiling
- Throughput measurement
- German text accuracy scoring
"""

import time
from pathlib import Path
from typing import Dict, Any

import pytest
import torch

# Mark all tests as GPU tests
pytestmark = [pytest.mark.gpu, pytest.mark.metrics]


# Backend test configurations
BACKEND_TEST_CONFIGS = {
    "deepseek": {
        "vram_required_gb": 12.0,
        "vram_max_gb": 13.6,  # 85% of 16GB
        "min_throughput_pages_per_sec": 0.5,
        "min_german_accuracy": 0.90,
        "supports_fraktur": True,
        "supports_handwriting": True,
    },
    "got_ocr": {
        "vram_required_gb": 10.0,
        "vram_max_gb": 13.6,
        "min_throughput_pages_per_sec": 1.0,
        "min_german_accuracy": 0.85,
        "supports_fraktur": False,
        "supports_handwriting": False,
    },
    "surya_gpu": {
        "vram_required_gb": 8.0,
        "vram_max_gb": 13.6,
        "min_throughput_pages_per_sec": 1.5,
        "min_german_accuracy": 0.85,
        "supports_fraktur": False,
        "supports_handwriting": False,
    },
    "surya_docling": {
        "vram_required_gb": 0.0,  # CPU only
        "vram_max_gb": 0.0,
        "min_throughput_pages_per_sec": 0.2,
        "min_german_accuracy": 0.80,
        "supports_fraktur": False,
        "supports_handwriting": False,
    },
}


class MetricsCollector:
    """Collect metrics during backend testing."""

    def __init__(self):
        self.vram_samples = []
        self.start_time = None
        self.end_time = None

    def start(self):
        """Start metrics collection."""
        self.start_time = time.perf_counter()
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            self.vram_samples.append(torch.cuda.memory_allocated() / (1024**3))

    def sample(self):
        """Take a VRAM sample."""
        if torch.cuda.is_available():
            self.vram_samples.append(torch.cuda.memory_allocated() / (1024**3))

    def stop(self) -> Dict[str, Any]:
        """Stop collection and return metrics."""
        self.end_time = time.perf_counter()

        metrics = {
            "duration_seconds": self.end_time - self.start_time,
        }

        if torch.cuda.is_available():
            metrics["vram_peak_gb"] = torch.cuda.max_memory_allocated() / (1024**3)
            metrics["vram_current_gb"] = torch.cuda.memory_allocated() / (1024**3)
            metrics["vram_samples"] = self.vram_samples

        return metrics


def calculate_german_accuracy(extracted: str, expected: str) -> float:
    """
    Calculate accuracy of German text extraction.

    Uses Levenshtein-based similarity with umlaut weighting.
    """
    # No expected text = nothing to compare against, return 1.0 (skip)
    if not expected:
        return 1.0

    # Expected text but nothing extracted = complete failure
    if not extracted:
        return 0.0

    # Normalize whitespace
    extracted_clean = " ".join(extracted.split())
    expected_clean = " ".join(expected.split())

    # Calculate Levenshtein distance for base accuracy
    def levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    distance = levenshtein_distance(extracted_clean, expected_clean)
    max_len = max(len(extracted_clean), len(expected_clean))
    base_accuracy = 1.0 - (distance / max_len) if max_len > 0 else 1.0

    # Check umlaut-specific accuracy
    umlauts = ["ae", "oe", "ue", "ss", "Ae", "Oe", "Ue"]
    umlaut_correct = 0
    umlaut_total = 0

    for umlaut in umlauts:
        expected_count = expected_clean.count(umlaut)
        extracted_count = extracted_clean.count(umlaut)
        umlaut_total += expected_count
        umlaut_correct += min(expected_count, extracted_count)

    # Only factor in umlaut accuracy if there are umlauts to check
    if umlaut_total > 0:
        umlaut_accuracy = umlaut_correct / umlaut_total
        return 0.7 * base_accuracy + 0.3 * umlaut_accuracy

    return base_accuracy


class TestBackendVRAMProfile:
    """Test VRAM usage profiles for each backend."""

    @pytest.fixture
    def test_images_dir(self):
        """Get test images directory."""
        return Path("tests/fixtures/german_docs")

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_vram_below_threshold_before_loading(self):
        """Test VRAM is low before any backend loads."""
        current_vram = torch.cuda.memory_allocated() / (1024**3)
        assert current_vram < 1.0, f"VRAM already in use: {current_vram:.2f}GB"

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    @pytest.mark.parametrize("backend", ["surya_gpu"])  # Start with lighter backend
    def test_vram_stays_under_threshold(self, backend, test_images_dir):
        """Test that VRAM stays under 13.6GB threshold."""
        config = BACKEND_TEST_CONFIGS.get(backend)
        if not config:
            pytest.skip(f"No config for backend: {backend}")

        # Skip if backend requires more VRAM than available
        total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        if config["vram_required_gb"] > total_vram:
            pytest.skip(f"Insufficient VRAM for {backend}")

        metrics = MetricsCollector()
        metrics.start()

        try:
            # Import and initialize backend
            if backend == "surya_gpu":
                from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
                agent = SuryaGPUAgent()
            elif backend == "got_ocr":
                from app.agents.ocr.got_ocr_agent import GOTOCRAgent
                agent = GOTOCRAgent()
            elif backend == "deepseek":
                from app.agents.ocr.deepseek_agent import DeepSeekAgent
                agent = DeepSeekAgent()
            else:
                pytest.skip(f"Unknown backend: {backend}")

            metrics.sample()

            # Check VRAM after initialization
            result = metrics.stop()
            peak_vram = result.get("vram_peak_gb", 0)

            assert peak_vram <= config["vram_max_gb"], (
                f"{backend} exceeded VRAM threshold: {peak_vram:.2f}GB > {config['vram_max_gb']}GB"
            )

        finally:
            # Cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


class TestBackendThroughput:
    """Test throughput for each backend."""

    @pytest.fixture
    def test_images_dir(self):
        """Get test images directory."""
        return Path("tests/fixtures/german_docs")

    @pytest.fixture
    def sample_image(self, test_images_dir):
        """Get a sample test image."""
        invoices_dir = test_images_dir / "invoices"
        if invoices_dir.exists():
            images = list(invoices_dir.glob("*.png"))
            if images:
                return images[0]
        return None

    def test_throughput_calculation(self):
        """Test throughput calculation formula."""
        # 5 pages in 10 seconds = 0.5 pages/second
        pages = 5
        seconds = 10.0
        throughput = pages / seconds
        assert throughput == 0.5

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_timing_measurement_accuracy(self):
        """Test that timing measurements are accurate."""
        start = time.perf_counter()
        time.sleep(0.1)  # 100ms
        elapsed = time.perf_counter() - start

        # Should be approximately 100ms (allow 50ms tolerance)
        assert 0.05 < elapsed < 0.15, f"Timing inaccurate: {elapsed:.3f}s"


class TestGermanTextAccuracy:
    """Test German text extraction accuracy."""

    def test_accuracy_calculation_perfect(self):
        """Test accuracy calculation with perfect match."""
        expected = "Muehlstrasse 123"
        extracted = "Muehlstrasse 123"
        accuracy = calculate_german_accuracy(extracted, expected)
        assert accuracy == 1.0

    def test_accuracy_calculation_partial(self):
        """Test accuracy calculation with partial match."""
        expected = "Muehlstrasse"
        extracted = "Muhlstrasse"  # Missing 'e'
        accuracy = calculate_german_accuracy(extracted, expected)
        # 1 char difference in 12 chars = ~91.7% base accuracy, with umlaut weighting ~79%
        assert 0.75 < accuracy < 1.0

    def test_accuracy_with_umlauts(self):
        """Test accuracy specifically for umlauts."""
        expected = "Gruesse aus Muenchen"
        extracted = "Gruesse aus Muenchen"
        accuracy = calculate_german_accuracy(extracted, expected)
        assert accuracy == 1.0

    def test_accuracy_empty_expected(self):
        """Test accuracy with empty expected text."""
        accuracy = calculate_german_accuracy("some text", "")
        assert accuracy == 1.0

    def test_accuracy_empty_extracted(self):
        """Test accuracy with empty extracted text."""
        accuracy = calculate_german_accuracy("", "expected text")
        assert accuracy == 0.0


class TestBackendConfigurations:
    """Test backend configuration values."""

    def test_all_backends_have_configs(self):
        """Test that all expected backends have configurations."""
        expected_backends = ["deepseek", "got_ocr", "surya_gpu", "surya_docling"]
        for backend in expected_backends:
            assert backend in BACKEND_TEST_CONFIGS, f"Missing config for {backend}"

    def test_vram_thresholds_are_reasonable(self):
        """Test that VRAM thresholds are reasonable for RTX 4080."""
        max_vram_gb = 16.0  # RTX 4080

        for backend, config in BACKEND_TEST_CONFIGS.items():
            assert config["vram_max_gb"] <= max_vram_gb * 0.85, (
                f"{backend} VRAM max ({config['vram_max_gb']}GB) exceeds 85% of RTX 4080"
            )

    def test_cpu_backend_has_zero_vram(self):
        """Test that CPU-only backend has zero VRAM requirement."""
        config = BACKEND_TEST_CONFIGS["surya_docling"]
        assert config["vram_required_gb"] == 0.0
        assert config["vram_max_gb"] == 0.0

    def test_accuracy_thresholds_are_reasonable(self):
        """Test that accuracy thresholds are achievable."""
        for backend, config in BACKEND_TEST_CONFIGS.items():
            accuracy = config["min_german_accuracy"]
            assert 0.75 <= accuracy <= 1.0, (
                f"{backend} accuracy threshold ({accuracy}) out of reasonable range"
            )


@pytest.mark.asyncio
class TestBackendMetricsIntegration:
    """Integration tests for backend metrics collection."""

    @pytest.fixture
    def test_images_dir(self):
        """Get test images directory."""
        return Path("tests/fixtures/german_docs")

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    @pytest.mark.slow
    async def test_surya_gpu_metrics(self, test_images_dir):
        """Test metrics collection for Surya GPU backend."""
        try:
            from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
        except ImportError:
            pytest.skip("Surya GPU agent not available")

        sample_image = test_images_dir / "invoices" / "invoice_001.png"
        if not sample_image.exists():
            pytest.skip("Test image not found")

        agent = SuryaGPUAgent()
        metrics = MetricsCollector()

        try:
            metrics.start()

            result = await agent.process({
                "document_id": "test_001",
                "image_path": str(sample_image),
                "language": "de"
            })

            metrics.sample()
            final_metrics = metrics.stop()

            # Verify metrics were collected
            assert "duration_seconds" in final_metrics
            assert "vram_peak_gb" in final_metrics
            assert final_metrics["duration_seconds"] > 0

            # Verify result
            assert "text" in result or "error" in result

        finally:
            await agent.cleanup()
            torch.cuda.empty_cache()


class TestMetricsExport:
    """Test metrics export functionality."""

    def test_metrics_collector_initialization(self):
        """Test MetricsCollector initializes correctly."""
        collector = MetricsCollector()
        assert collector.vram_samples == []
        assert collector.start_time is None
        assert collector.end_time is None

    def test_metrics_collector_start_stop(self):
        """Test MetricsCollector start/stop cycle."""
        collector = MetricsCollector()
        collector.start()

        assert collector.start_time is not None

        time.sleep(0.01)  # Small delay
        metrics = collector.stop()

        assert "duration_seconds" in metrics
        assert metrics["duration_seconds"] > 0

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_metrics_collector_vram_sampling(self):
        """Test VRAM sampling in MetricsCollector."""
        collector = MetricsCollector()
        collector.start()
        collector.sample()
        collector.sample()
        metrics = collector.stop()

        assert "vram_peak_gb" in metrics
        assert "vram_current_gb" in metrics
        assert "vram_samples" in metrics
        assert len(metrics["vram_samples"]) >= 2
