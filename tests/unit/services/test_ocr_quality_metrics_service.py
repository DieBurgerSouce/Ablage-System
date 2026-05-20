# -*- coding: utf-8 -*-
"""
Unit tests for OCR Quality Metrics Service.

Tests the OCR quality metrics tracking, estimation, and Redis persistence.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.ocr_quality_metrics_service import (
    OCRQualityMetricsService,
    QualityMetricsSample,
    RunningStats,
    get_ocr_quality_metrics_service,
    record_ocr_quality,
)


class TestRunningStats:
    """Tests for RunningStats dataclass."""

    def test_empty_stats(self):
        """Empty stats should return None for averages."""
        stats = RunningStats()
        assert stats.avg is None
        assert stats.p50 is None
        assert stats.p95 is None
        assert stats.count == 0

    def test_add_single_sample(self):
        """Single sample should work correctly."""
        stats = RunningStats()
        stats.add(0.5)

        assert stats.count == 1
        assert stats.avg == 0.5
        assert stats.p50 == 0.5
        assert stats.p95 == 0.5

    def test_add_multiple_samples(self):
        """Multiple samples should calculate correct statistics."""
        stats = RunningStats()
        for val in [0.1, 0.2, 0.3, 0.4, 0.5]:
            stats.add(val)

        assert stats.count == 5
        assert abs(stats.avg - 0.3) < 0.001  # Average of 0.1-0.5
        assert stats.p50 == 0.3  # Median

    def test_rolling_window(self):
        """Stats should maintain rolling window with maxlen."""
        stats = RunningStats()
        # Add more than maxlen samples
        for i in range(1100):
            stats.add(float(i))

        assert len(stats.samples) == 1000  # maxlen
        assert stats.count == 1100  # Total count

    def test_percentile_calculation(self):
        """P95 should be calculated correctly."""
        stats = RunningStats()
        # Add 100 samples (0-99)
        for i in range(100):
            stats.add(float(i))

        # P95 should be around 94-95
        assert stats.p95 >= 94
        assert stats.p95 <= 95


class TestOCRQualityMetricsService:
    """Tests for OCRQualityMetricsService."""

    def test_singleton_pattern(self):
        """Service should use singleton pattern."""
        service1 = OCRQualityMetricsService.get_instance()
        service2 = OCRQualityMetricsService.get_instance()
        assert service1 is service2

    def test_estimate_cer_high_confidence(self):
        """High confidence should estimate low CER."""
        service = OCRQualityMetricsService()

        cer = service.estimate_cer_from_confidence(0.98)
        assert cer == 0.02

    def test_estimate_cer_medium_confidence(self):
        """Medium confidence should estimate moderate CER."""
        service = OCRQualityMetricsService()

        cer = service.estimate_cer_from_confidence(0.75)
        assert cer == 0.10

    def test_estimate_cer_low_confidence(self):
        """Low confidence should estimate higher CER."""
        service = OCRQualityMetricsService()

        cer = service.estimate_cer_from_confidence(0.40)
        assert cer == 0.25

    def test_estimate_wer_higher_than_cer(self):
        """WER should typically be higher than CER."""
        service = OCRQualityMetricsService()

        confidence = 0.85
        cer = service.estimate_cer_from_confidence(confidence)
        wer = service.estimate_wer_from_confidence(confidence)

        assert wer > cer
        assert wer == min(1.0, cer * 1.5)

    def test_estimate_umlaut_accuracy_with_umlauts(self):
        """Umlaut accuracy should combine quality and confidence."""
        service = OCRQualityMetricsService()

        accuracy = service.estimate_umlaut_accuracy(
            has_umlauts=True,
            quality_score=0.9,
            confidence=0.8,
        )

        # Expected: (0.9 * 0.7) + (0.8 * 0.3) = 0.63 + 0.24 = 0.87
        expected = (0.9 * 0.7) + (0.8 * 0.3)
        assert abs(accuracy - expected) < 0.001

    def test_estimate_umlaut_accuracy_without_umlauts(self):
        """Without umlauts, should use confidence as proxy."""
        service = OCRQualityMetricsService()

        accuracy = service.estimate_umlaut_accuracy(
            has_umlauts=False,
            quality_score=0.9,
            confidence=0.75,
        )

        assert accuracy == 0.75

    @pytest.mark.asyncio
    async def test_record_ocr_result_updates_stats(self):
        """Recording OCR result should update statistics."""
        service = OCRQualityMetricsService()

        # Mock Redis persistence
        with patch.object(service, '_persist_to_redis', new_callable=AsyncMock):
            await service.record_ocr_result(
                backend="deepseek",
                confidence=0.95,
                processing_time_ms=1500.0,
                has_umlauts=True,
                german_quality_score=0.92,
                document_type="invoice",
            )

        # Check stats updated
        assert service._total_samples == 1
        assert service._backend_counts.get("deepseek") == 1
        assert "deepseek" in service._cer_stats
        assert "deepseek" in service._time_stats

    @pytest.mark.asyncio
    async def test_record_multiple_backends(self):
        """Recording from multiple backends should track separately."""
        service = OCRQualityMetricsService()

        with patch.object(service, '_persist_to_redis', new_callable=AsyncMock):
            await service.record_ocr_result(
                backend="deepseek",
                confidence=0.95,
                processing_time_ms=1500.0,
            )
            await service.record_ocr_result(
                backend="got_ocr",
                confidence=0.85,
                processing_time_ms=800.0,
            )
            await service.record_ocr_result(
                backend="surya",
                confidence=0.75,
                processing_time_ms=2000.0,
            )

        assert service._total_samples == 3
        assert service._backend_counts.get("deepseek") == 1
        assert service._backend_counts.get("got_ocr") == 1
        assert service._backend_counts.get("surya") == 1

    @pytest.mark.asyncio
    async def test_record_with_ground_truth(self):
        """Recording with ground truth should use actual values."""
        service = OCRQualityMetricsService()

        with patch.object(service, '_persist_to_redis', new_callable=AsyncMock):
            with patch('app.ml.metrics.get_ml_metrics') as mock_metrics:
                mock_instance = MagicMock()
                mock_metrics.return_value = mock_instance

                await service.record_ground_truth_comparison(
                    backend="deepseek",
                    cer=0.03,
                    wer=0.05,
                    umlaut_accuracy=0.98,
                    processing_time_ms=1200.0,
                    document_type="benchmark",
                )

        assert service._total_samples == 1
        # Ground truth values should be used
        assert service._global_cer.avg == 0.03
        assert service._global_wer.avg == 0.05

    def test_get_stats_summary(self):
        """Stats summary should return structured data."""
        service = OCRQualityMetricsService()

        # Add some manual stats
        service._global_cer.add(0.05)
        service._global_wer.add(0.08)
        service._global_umlaut.add(0.95)
        service._total_samples = 1
        service._backend_counts["deepseek"] = 1
        service._cer_stats["deepseek"] = RunningStats()
        service._cer_stats["deepseek"].add(0.05)

        summary = service.get_stats_summary()

        assert "total_samples" in summary
        assert "global" in summary
        assert "by_backend" in summary
        assert summary["total_samples"] == 1
        assert summary["global"]["cer"]["avg"] == 0.05

    @pytest.mark.asyncio
    async def test_persist_to_redis(self):
        """Persistence should write all metrics to Redis."""
        service = OCRQualityMetricsService()

        # Add test data
        service._global_cer.add(0.05)
        service._global_wer.add(0.08)
        service._global_umlaut.add(0.95)
        service._total_samples = 10
        service._backend_counts["deepseek"] = 5
        service._cer_stats["deepseek"] = RunningStats()
        service._cer_stats["deepseek"].add(0.04)

        # Mock Redis
        mock_redis_instance = AsyncMock()
        mock_redis_instance._redis = AsyncMock()
        mock_redis_instance._redis.set = AsyncMock()
        mock_redis_instance._ensure_connection = AsyncMock()

        with patch('app.core.redis_state.get_redis', return_value=mock_redis_instance):
            await service._persist_to_redis()

        # Verify Redis calls
        calls = mock_redis_instance._redis.set.call_args_list
        call_keys = [c[0][0] for c in calls]

        assert "metrics:ocr:cer:avg" in call_keys
        assert "metrics:ocr:wer:avg" in call_keys
        assert "metrics:ocr:umlaut_accuracy:avg" in call_keys
        assert "metric:ocr.quality_samples" in call_keys

    @pytest.mark.asyncio
    async def test_redis_persist_every_10_samples(self):
        """Metrics should persist to Redis every 10 samples."""
        service = OCRQualityMetricsService()
        persist_mock = AsyncMock()
        service._persist_to_redis = persist_mock

        # Record 15 samples
        for i in range(15):
            await service.record_ocr_result(
                backend="deepseek",
                confidence=0.9,
                processing_time_ms=1000.0,
            )

        # Should have persisted at sample 10
        assert persist_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_backend_normalization(self):
        """Backend names should be normalized."""
        service = OCRQualityMetricsService()

        with patch.object(service, '_persist_to_redis', new_callable=AsyncMock):
            await service.record_ocr_result(
                backend="DeepSeek-Janus",
                confidence=0.95,
                processing_time_ms=1500.0,
            )

        # Should be normalized to deepseek_janus
        assert "deepseek_janus" in service._backend_counts


class TestGlobalFunctions:
    """Tests for global helper functions."""

    def test_get_ocr_quality_metrics_service_singleton(self):
        """Global getter should return singleton."""
        service1 = get_ocr_quality_metrics_service()
        service2 = get_ocr_quality_metrics_service()
        assert service1 is service2

    @pytest.mark.asyncio
    async def test_record_ocr_quality_convenience(self):
        """Convenience function should delegate to service."""
        with patch('app.services.ocr_quality_metrics_service._service_instance') as mock_service:
            mock_service.record_ocr_result = AsyncMock()

            # Reset the global instance to use our mock
            import app.services.ocr_quality_metrics_service as module
            original = module._service_instance
            module._service_instance = mock_service

            try:
                await record_ocr_quality(
                    backend="deepseek",
                    confidence=0.9,
                    processing_time_ms=1000.0,
                    has_umlauts=True,
                    german_quality_score=0.85,
                    document_type="letter",
                )

                mock_service.record_ocr_result.assert_called_once()
            finally:
                module._service_instance = original


class TestQualityMetricsSample:
    """Tests for QualityMetricsSample dataclass."""

    def test_default_values(self):
        """Sample should have sensible defaults."""
        sample = QualityMetricsSample(backend="test")

        assert sample.backend == "test"
        assert sample.cer is None
        assert sample.wer is None
        assert sample.umlaut_accuracy == 1.0
        assert sample.confidence == 0.0
        assert sample.processing_time_ms == 0.0
        assert sample.document_type == "unknown"
        assert isinstance(sample.timestamp, datetime)

    def test_custom_values(self):
        """Sample should accept custom values."""
        sample = QualityMetricsSample(
            backend="deepseek",
            cer=0.05,
            wer=0.08,
            umlaut_accuracy=0.95,
            confidence=0.92,
            processing_time_ms=1500.0,
            document_type="invoice",
        )

        assert sample.backend == "deepseek"
        assert sample.cer == 0.05
        assert sample.wer == 0.08
        assert sample.umlaut_accuracy == 0.95
        assert sample.confidence == 0.92
        assert sample.processing_time_ms == 1500.0
        assert sample.document_type == "invoice"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_record_with_zero_confidence(self):
        """Zero confidence should estimate maximum error rates."""
        service = OCRQualityMetricsService()

        with patch.object(service, '_persist_to_redis', new_callable=AsyncMock):
            await service.record_ocr_result(
                backend="deepseek",
                confidence=0.0,
                processing_time_ms=1000.0,
            )

        # With 0 confidence, CER should be at maximum estimated level
        assert service._global_cer.avg == 0.25

    @pytest.mark.asyncio
    async def test_record_with_perfect_confidence(self):
        """Perfect confidence should estimate minimal error rates."""
        service = OCRQualityMetricsService()

        with patch.object(service, '_persist_to_redis', new_callable=AsyncMock):
            await service.record_ocr_result(
                backend="deepseek",
                confidence=1.0,
                processing_time_ms=1000.0,
            )

        # With 100% confidence, CER should be minimal
        assert service._global_cer.avg == 0.02

    @pytest.mark.asyncio
    async def test_redis_failure_doesnt_break_recording(self):
        """Redis failure should not break metric recording."""
        service = OCRQualityMetricsService()
        service._total_samples = 9  # Next sample triggers persist

        with patch('app.core.redis_state.get_redis', side_effect=Exception("Redis down")):
            # Should not raise
            await service.record_ocr_result(
                backend="deepseek",
                confidence=0.9,
                processing_time_ms=1000.0,
            )

        # Recording should still work
        assert service._total_samples == 10
        assert service._backend_counts.get("deepseek") == 1

    @pytest.mark.asyncio
    async def test_empty_backend_name(self):
        """Empty backend should be handled gracefully."""
        service = OCRQualityMetricsService()

        with patch.object(service, '_persist_to_redis', new_callable=AsyncMock):
            await service.record_ocr_result(
                backend="",
                confidence=0.9,
                processing_time_ms=1000.0,
            )

        assert "" in service._backend_counts
