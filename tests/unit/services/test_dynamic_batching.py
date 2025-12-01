# -*- coding: utf-8 -*-
"""
Unit Tests fuer Dynamic GPU Batch-Size Adjustment.

Testet die dynamische Batch-Groessen-Anpassung:
- VRAM-basierte Berechnung
- OOM-Recovery mit Exponential Backoff
- Memory-Profiling
- Backend-spezifische Schaetzungen
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from app.services.batch_processor import DynamicBatchSizer


class TestDynamicBatchSizerInit:
    """Tests fuer DynamicBatchSizer Initialisierung."""

    def test_init_default_values(self):
        """Standard-Initialisierung funktioniert."""
        sizer = DynamicBatchSizer()
        assert sizer.max_batch_size == 32
        assert sizer.min_batch_size == 1
        assert sizer._current_batch_size == 32
        assert sizer._oom_count == 0
        assert sizer._warmup_completed is False

    def test_init_custom_values(self):
        """Initialisierung mit benutzerdefinierten Werten."""
        sizer = DynamicBatchSizer(max_batch_size=16, min_batch_size=2)
        assert sizer.max_batch_size == 16
        assert sizer.min_batch_size == 2
        assert sizer._current_batch_size == 16


class TestDynamicBatchSizerThresholds:
    """Tests fuer VRAM-Thresholds."""

    def test_vram_thresholds_defined(self):
        """VRAM-Thresholds sind korrekt definiert."""
        assert DynamicBatchSizer.VRAM_SAFE_THRESHOLD == 0.70
        assert DynamicBatchSizer.VRAM_WARNING_THRESHOLD == 0.85
        assert DynamicBatchSizer.VRAM_CRITICAL_THRESHOLD == 0.95

    def test_memory_estimates_defined(self):
        """Memory-Schaetzungen pro Backend sind definiert."""
        estimates = DynamicBatchSizer.MEMORY_PER_DOC_MB
        assert "deepseek" in estimates
        assert "got_ocr" in estimates
        assert "surya_gpu" in estimates
        assert "surya_cpu" in estimates
        assert "default" in estimates
        # DeepSeek sollte am meisten brauchen
        assert estimates["deepseek"] > estimates["got_ocr"]
        assert estimates["surya_cpu"] < estimates["surya_gpu"]


class TestGetOptimalBatchSize:
    """Tests fuer get_optimal_batch_size Methode."""

    @patch("app.services.batch_processor.torch")
    def test_no_cuda_available(self, mock_torch):
        """Ohne CUDA wird konservative Batch-Groesse verwendet."""
        mock_torch.cuda.is_available.return_value = False

        sizer = DynamicBatchSizer(max_batch_size=32)
        batch_size = sizer.get_optimal_batch_size()

        assert batch_size == 4  # min(4, 32)

    @patch("app.services.batch_processor.torch")
    def test_cuda_available_large_vram(self, mock_torch):
        """Mit viel freiem VRAM wird groessere Batch-Groesse berechnet."""
        mock_torch.cuda.is_available.return_value = True

        # Mock GPU mit 16GB total, 2GB belegt
        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3  # 16 GB
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3  # 2 GB allocated
        mock_torch.cuda.memory_reserved.return_value = 2.5 * 1024**3  # 2.5 GB reserved

        sizer = DynamicBatchSizer(max_batch_size=32)
        batch_size = sizer.get_optimal_batch_size(backend="deepseek")

        # Mit 14GB frei und 600MB/doc: (14*0.7)/0.6 = ~16 docs
        assert batch_size > 0
        assert batch_size <= 32

    @patch("app.services.batch_processor.torch")
    def test_cuda_available_low_vram(self, mock_torch):
        """Mit wenig freiem VRAM wird kleinere Batch-Groesse berechnet."""
        mock_torch.cuda.is_available.return_value = True

        # Mock GPU mit 16GB total, 14GB belegt
        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3  # 16 GB
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 14 * 1024**3  # 14 GB allocated
        mock_torch.cuda.memory_reserved.return_value = 14 * 1024**3

        sizer = DynamicBatchSizer(max_batch_size=32)
        batch_size = sizer.get_optimal_batch_size(backend="deepseek")

        # Mit 2GB frei und 600MB/doc: sehr kleine Batch
        assert batch_size >= 1
        assert batch_size <= 5

    @patch("app.services.batch_processor.torch")
    def test_backend_specific_memory_estimate(self, mock_torch):
        """Verschiedene Backends haben unterschiedliche Memory-Schaetzungen."""
        mock_torch.cuda.is_available.return_value = True

        # Mock GPU mit 16GB total, 8GB belegt
        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 8 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 8 * 1024**3

        sizer = DynamicBatchSizer(max_batch_size=32)

        # Surya CPU braucht weniger Memory
        batch_surya_cpu = sizer.get_optimal_batch_size(backend="surya_cpu")
        batch_deepseek = sizer.get_optimal_batch_size(backend="deepseek")

        # Surya CPU sollte groessere Batch erlauben
        assert batch_surya_cpu >= batch_deepseek

    @patch("app.services.batch_processor.torch")
    def test_uses_measured_memory_if_available(self, mock_torch):
        """Gemessener Memory-Verbrauch wird bevorzugt verwendet."""
        mock_torch.cuda.is_available.return_value = True

        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 4 * 1024**3

        sizer = DynamicBatchSizer(max_batch_size=32)

        # Setze gemessenen Wert (sehr niedrig)
        sizer._measured_memory_per_doc["custom_backend"] = 100 * 1024**2  # 100 MB

        batch_size = sizer.get_optimal_batch_size(backend="custom_backend")

        # Mit gemessenem Wert sollte groessere Batch moeglich sein
        assert batch_size > 10


class TestOOMHandling:
    """Tests fuer OOM-Recovery und Exponential Backoff."""

    def test_record_oom_reduces_batch_size(self):
        """OOM reduziert Batch-Groesse um die Haelfte."""
        sizer = DynamicBatchSizer(max_batch_size=32)

        assert sizer._current_batch_size == 32

        new_size = sizer.record_oom()

        assert new_size == 16
        assert sizer._oom_count == 1
        assert sizer._current_batch_size == 16

    def test_multiple_oom_exponential_reduction(self):
        """Mehrere OOMs fuehren zu exponentieller Reduktion."""
        sizer = DynamicBatchSizer(max_batch_size=32)

        sizer.record_oom()  # 32 -> 16
        sizer.record_oom()  # 16 -> 8
        sizer.record_oom()  # 8 -> 4
        sizer.record_oom()  # 4 -> 2
        sizer.record_oom()  # 2 -> 1

        assert sizer._current_batch_size == 1
        assert sizer._oom_count == 5

    def test_oom_respects_min_batch_size(self):
        """OOM-Reduktion stoppt bei min_batch_size."""
        sizer = DynamicBatchSizer(max_batch_size=4, min_batch_size=2)

        sizer.record_oom()  # 4 -> 2
        sizer.record_oom()  # 2 -> bleibt 2

        assert sizer._current_batch_size == 2

    @patch("app.services.batch_processor.torch")
    def test_oom_count_affects_calculation(self, mock_torch):
        """OOM-Count reduziert berechnete Batch-Groesse."""
        mock_torch.cuda.is_available.return_value = True

        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 4 * 1024**3

        sizer = DynamicBatchSizer(max_batch_size=32)

        batch_before = sizer.get_optimal_batch_size()

        # Simuliere OOM
        sizer._oom_count = 2
        batch_after = sizer.get_optimal_batch_size()

        # Mit OOM-Count sollte Batch kleiner sein
        assert batch_after <= batch_before


class TestSuccessRecording:
    """Tests fuer erfolgreiche Verarbeitung und Memory-Profiling."""

    def test_record_success_stores_memory_measurement(self):
        """Erfolgreiche Verarbeitung speichert Memory-Messung."""
        sizer = DynamicBatchSizer()

        memory_used = 1200 * 1024**2  # 1200 MB fuer 2 Dokumente
        sizer.record_success(batch_size=2, backend="deepseek", memory_used=memory_used)

        assert "deepseek" in sizer._measured_memory_per_doc
        # 600 MB pro Dokument
        assert sizer._measured_memory_per_doc["deepseek"] == 600 * 1024**2

    def test_record_success_reduces_oom_count(self):
        """Erfolgreiche Verarbeitung reduziert OOM-Count langsam."""
        sizer = DynamicBatchSizer()
        sizer._oom_count = 3

        sizer.record_success(batch_size=4, backend="got_ocr", memory_used=1000 * 1024**2)

        # OOM-Count sollte reduziert sein (aber nicht auf 0)
        assert sizer._oom_count == 2.9

    def test_record_success_zero_batch_size_ignored(self):
        """Batch-Size 0 wird ignoriert."""
        sizer = DynamicBatchSizer()

        sizer.record_success(batch_size=0, backend="test", memory_used=1000)

        assert "test" not in sizer._measured_memory_per_doc


class TestVRAMStatus:
    """Tests fuer get_vram_status Methode."""

    @patch("app.services.batch_processor.torch")
    def test_vram_status_no_cuda(self, mock_torch):
        """Ohne CUDA wird available=False zurueckgegeben."""
        mock_torch.cuda.is_available.return_value = False

        sizer = DynamicBatchSizer()
        status = sizer.get_vram_status()

        assert status == {"available": False}

    @patch("app.services.batch_processor.torch")
    def test_vram_status_safe(self, mock_torch):
        """VRAM-Status 'safe' bei niedriger Auslastung."""
        mock_torch.cuda.is_available.return_value = True

        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3  # 25%
        mock_torch.cuda.memory_reserved.return_value = 5 * 1024**3

        sizer = DynamicBatchSizer()
        status = sizer.get_vram_status()

        assert status["available"] is True
        assert status["status"] == "safe"
        assert status["usage_percent"] == 25.0

    @patch("app.services.batch_processor.torch")
    def test_vram_status_warning(self, mock_torch):
        """VRAM-Status 'warning' bei hoher Auslastung."""
        mock_torch.cuda.is_available.return_value = True

        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 14 * 1024**3  # 87.5%
        mock_torch.cuda.memory_reserved.return_value = 14 * 1024**3

        sizer = DynamicBatchSizer()
        status = sizer.get_vram_status()

        assert status["status"] == "warning"
        assert status["usage_percent"] == 87.5

    @patch("app.services.batch_processor.torch")
    def test_vram_status_critical(self, mock_torch):
        """VRAM-Status 'critical' bei kritischer Auslastung."""
        mock_torch.cuda.is_available.return_value = True

        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 15.5 * 1024**3  # 96.9%
        mock_torch.cuda.memory_reserved.return_value = 15.5 * 1024**3

        sizer = DynamicBatchSizer()
        status = sizer.get_vram_status()

        assert status["status"] == "critical"
        assert status["usage_percent"] > 95


class TestWarmup:
    """Tests fuer Warmup-Phase."""

    @patch("app.services.batch_processor.torch")
    def test_warmup_without_cuda(self, mock_torch):
        """Warmup ohne CUDA setzt Flag und kehrt zurueck."""
        mock_torch.cuda.is_available.return_value = False

        sizer = DynamicBatchSizer()
        sizer.warmup(backend="deepseek")

        assert sizer._warmup_completed is True

    @patch("app.services.batch_processor.torch")
    def test_warmup_with_cuda(self, mock_torch):
        """Warmup mit CUDA initialisiert Memory-Tracking."""
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.memory_allocated.return_value = 1 * 1024**3

        sizer = DynamicBatchSizer()
        sizer.warmup(backend="deepseek", sample_batch_size=2)

        assert sizer._warmup_completed is True


class TestIntegration:
    """Integration-Tests fuer DynamicBatchSizer."""

    @patch("app.services.batch_processor.torch")
    def test_full_workflow(self, mock_torch):
        """Kompletter Workflow: Warmup -> Processing -> OOM -> Recovery."""
        mock_torch.cuda.is_available.return_value = True

        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 4 * 1024**3

        sizer = DynamicBatchSizer(max_batch_size=16)

        # 1. Warmup
        sizer.warmup(backend="deepseek")
        assert sizer._warmup_completed is True

        # 2. Initial batch size
        batch_1 = sizer.get_optimal_batch_size(backend="deepseek")
        assert batch_1 > 0

        # 3. Successful processing
        sizer.record_success(batch_size=batch_1, backend="deepseek",
                            memory_used=batch_1 * 500 * 1024**2)

        # 4. OOM event
        batch_2 = sizer.record_oom()
        assert batch_2 < sizer.max_batch_size

        # 5. Recovery
        batch_3 = sizer.get_optimal_batch_size(backend="deepseek")
        assert batch_3 <= batch_2  # Should be reduced due to OOM

    @patch("app.services.batch_processor.torch")
    def test_adaptive_memory_learning(self, mock_torch):
        """System lernt tatsaechlichen Memory-Verbrauch."""
        mock_torch.cuda.is_available.return_value = True

        mock_props = MagicMock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 4 * 1024**3

        sizer = DynamicBatchSizer(max_batch_size=32)

        # Anfangs: Default-Schaetzung (600 MB fuer DeepSeek)
        batch_initial = sizer.get_optimal_batch_size(backend="deepseek")

        # Lernen: Tatsaechlich nur 300 MB pro Dokument
        sizer.record_success(batch_size=10, backend="deepseek",
                            memory_used=3000 * 1024**2)

        # Danach: Sollte groessere Batch erlauben
        batch_learned = sizer.get_optimal_batch_size(backend="deepseek")

        # Mit niedrigerem gemessenen Wert kann groessere Batch verwendet werden
        assert batch_learned >= batch_initial
