# -*- coding: utf-8 -*-
"""
OCR Quality Metrics Service.

Erfasst und aggregiert OCR-Qualitaetsmetriken:
- Character Error Rate (CER)
- Word Error Rate (WER)
- Umlaut-Genauigkeit
- Backend-spezifische Metriken

Schreibt Metriken in Redis fuer das /api/v1/metrics/ocr-quality Endpoint.

Feinpoliert und durchdacht - Production-ready Metriken-Erfassung.
"""

import asyncio
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Deque

import structlog

logger = structlog.get_logger(__name__)

# Maximum samples to keep in memory for percentile calculations
MAX_SAMPLES = 1000


@dataclass
class QualityMetricsSample:
    """Single quality metrics sample."""

    backend: str
    cer: Optional[float] = None  # Character Error Rate (0-1)
    wer: Optional[float] = None  # Word Error Rate (0-1)
    umlaut_accuracy: float = 1.0  # Umlaut accuracy (0-1)
    confidence: float = 0.0  # OCR confidence score
    processing_time_ms: float = 0.0
    document_type: str = "unknown"
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RunningStats:
    """Running statistics for a metric."""

    samples: Deque[float] = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    count: int = 0
    sum: float = 0.0

    def add(self, value: float) -> None:
        """Add a sample and update statistics."""
        if len(self.samples) >= MAX_SAMPLES:
            # Remove oldest sample from sum
            oldest = self.samples[0]
            self.sum -= oldest
        self.samples.append(value)
        self.sum += value
        self.count += 1

    @property
    def avg(self) -> Optional[float]:
        """Calculate average."""
        if not self.samples:
            return None
        return self.sum / len(self.samples)

    @property
    def p50(self) -> Optional[float]:
        """Calculate 50th percentile (median)."""
        if not self.samples:
            return None
        sorted_samples = sorted(self.samples)
        return sorted_samples[len(sorted_samples) // 2]

    @property
    def p95(self) -> Optional[float]:
        """Calculate 95th percentile."""
        if len(self.samples) < 2:
            return self.avg
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]


class OCRQualityMetricsService:
    """
    Service fuer OCR-Qualitaetsmetriken.

    Erfasst Metriken waehrend OCR-Verarbeitung und schreibt
    aggregierte Werte in Redis fuer Monitoring-Endpoints.
    """

    _instance: Optional["OCRQualityMetricsService"] = None

    def __init__(self):
        """Initialisiere Metrics Service."""
        # Running statistics for all backends
        self._cer_stats: Dict[str, RunningStats] = {}
        self._wer_stats: Dict[str, RunningStats] = {}
        self._umlaut_stats: Dict[str, RunningStats] = {}
        self._time_stats: Dict[str, RunningStats] = {}

        # Global statistics
        self._global_cer = RunningStats()
        self._global_wer = RunningStats()
        self._global_umlaut = RunningStats()

        # Sample counts
        self._backend_counts: Dict[str, int] = {}
        self._total_samples = 0

        # Known backends
        self._backends = ["deepseek", "got_ocr", "surya", "surya_gpu", "donut"]

        logger.info("ocr_quality_metrics_service_initialized")

    @classmethod
    def get_instance(cls) -> "OCRQualityMetricsService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_backend_stats(self, backend: str, stats_dict: Dict[str, RunningStats]) -> RunningStats:
        """Get or create backend-specific stats."""
        if backend not in stats_dict:
            stats_dict[backend] = RunningStats()
        return stats_dict[backend]

    def estimate_cer_from_confidence(self, confidence: float) -> float:
        """
        Schaetze CER aus Konfidenzwert.

        Heuristik: CER korreliert invers mit Konfidenz.
        Bei 100% Konfidenz: CER ~0
        Bei 50% Konfidenz: CER ~0.10
        Bei 0% Konfidenz: CER ~0.30

        Args:
            confidence: OCR-Konfidenz (0-1)

        Returns:
            Geschaetzte CER (0-1)
        """
        # Inverse relationship with some floor
        if confidence >= 0.95:
            return 0.02  # Very high confidence = very low error
        elif confidence >= 0.85:
            return 0.05  # High confidence
        elif confidence >= 0.70:
            return 0.10  # Good confidence
        elif confidence >= 0.50:
            return 0.15  # Medium confidence
        else:
            return 0.25  # Low confidence

    def estimate_wer_from_confidence(self, confidence: float) -> float:
        """
        Schaetze WER aus Konfidenzwert.

        WER ist typischerweise hoeher als CER da ganze Woerter
        betroffen sein koennen.

        Args:
            confidence: OCR-Konfidenz (0-1)

        Returns:
            Geschaetzte WER (0-1)
        """
        # WER typically 1.5-2x CER
        cer = self.estimate_cer_from_confidence(confidence)
        return min(1.0, cer * 1.5)

    def estimate_umlaut_accuracy(
        self,
        has_umlauts: bool,
        quality_score: float,
        confidence: float,
    ) -> float:
        """
        Schaetze Umlaut-Genauigkeit.

        Args:
            has_umlauts: Wurden Umlaute erkannt?
            quality_score: Deutsche Validierungs-Score
            confidence: OCR-Konfidenz

        Returns:
            Geschaetzte Umlaut-Genauigkeit (0-1)
        """
        if not has_umlauts:
            # No umlauts detected - could be correct or missing
            # Use confidence as proxy
            return confidence

        # Umlauts detected - use quality score weighted by confidence
        return (quality_score * 0.7) + (confidence * 0.3)

    async def record_ocr_result(
        self,
        backend: str,
        confidence: float,
        processing_time_ms: float,
        has_umlauts: bool = False,
        german_quality_score: float = 1.0,
        cer: Optional[float] = None,
        wer: Optional[float] = None,
        document_type: str = "unknown",
    ) -> None:
        """
        Erfasse OCR-Ergebnis fuer Qualitaetsmetriken.

        Wird nach jeder erfolgreichen OCR-Verarbeitung aufgerufen.

        Args:
            backend: Verwendetes OCR-Backend
            confidence: OCR-Konfidenz (0-1)
            processing_time_ms: Verarbeitungszeit
            has_umlauts: Wurden Umlaute erkannt?
            german_quality_score: Deutsche Validierungs-Score (0-1)
            cer: Character Error Rate (wenn Ground Truth verfuegbar)
            wer: Word Error Rate (wenn Ground Truth verfuegbar)
            document_type: Dokumenttyp
        """
        # Normalize backend name
        backend = backend.lower().replace("-", "_")

        # Estimate metrics if not provided
        if cer is None:
            cer = self.estimate_cer_from_confidence(confidence)
        if wer is None:
            wer = self.estimate_wer_from_confidence(confidence)

        umlaut_accuracy = self.estimate_umlaut_accuracy(
            has_umlauts, german_quality_score, confidence
        )

        # Update backend-specific stats
        self._get_backend_stats(backend, self._cer_stats).add(cer)
        self._get_backend_stats(backend, self._wer_stats).add(wer)
        self._get_backend_stats(backend, self._umlaut_stats).add(umlaut_accuracy)
        self._get_backend_stats(backend, self._time_stats).add(processing_time_ms)

        # Update global stats
        self._global_cer.add(cer)
        self._global_wer.add(wer)
        self._global_umlaut.add(umlaut_accuracy)

        # Update counts
        self._backend_counts[backend] = self._backend_counts.get(backend, 0) + 1
        self._total_samples += 1

        # Write to Redis periodically (every 10 samples)
        if self._total_samples % 10 == 0:
            await self._persist_to_redis()

        logger.debug(
            "ocr_quality_recorded",
            backend=backend,
            cer=round(cer, 4),
            wer=round(wer, 4),
            umlaut_accuracy=round(umlaut_accuracy, 4),
            confidence=round(confidence, 4),
        )

    async def record_ground_truth_comparison(
        self,
        backend: str,
        cer: float,
        wer: float,
        umlaut_accuracy: float,
        processing_time_ms: float,
        document_type: str = "benchmark",
    ) -> None:
        """
        Erfasse Ground-Truth-basierte Qualitaetsmetriken.

        Fuer Benchmark-Tests mit bekanntem Referenztext.

        Args:
            backend: Verwendetes OCR-Backend
            cer: Tatsaechliche Character Error Rate
            wer: Tatsaechliche Word Error Rate
            umlaut_accuracy: Tatsaechliche Umlaut-Genauigkeit
            processing_time_ms: Verarbeitungszeit
            document_type: Dokumenttyp
        """
        # Record with actual values
        await self.record_ocr_result(
            backend=backend,
            confidence=1.0 - cer,  # Approximate confidence from CER
            processing_time_ms=processing_time_ms,
            has_umlauts=True,
            german_quality_score=umlaut_accuracy,
            cer=cer,
            wer=wer,
            document_type=document_type,
        )

        # Also record to Prometheus metrics
        try:
            from app.ml.metrics import get_ml_metrics

            metrics = get_ml_metrics()
            metrics.record_quality_metrics(
                backend=backend,
                cer=cer,
                wer=wer,
                umlaut_accuracy=umlaut_accuracy,
                document_type=document_type,
            )
        except ImportError:
            logger.debug("prometheus_metrics_not_available")

    async def _persist_to_redis(self) -> None:
        """Persist aggregated metrics to Redis."""
        try:
            from app.core.redis_state import get_redis


            redis = await get_redis()
            await redis._ensure_connection()

            # Global CER metrics
            if self._global_cer.avg is not None:
                await redis._redis.set(
                    "metrics:ocr:cer:avg",
                    str(round(self._global_cer.avg, 4))
                )
            if self._global_cer.p50 is not None:
                await redis._redis.set(
                    "metrics:ocr:cer:p50",
                    str(round(self._global_cer.p50, 4))
                )
            if self._global_cer.p95 is not None:
                await redis._redis.set(
                    "metrics:ocr:cer:p95",
                    str(round(self._global_cer.p95, 4))
                )

            # Global WER metrics
            if self._global_wer.avg is not None:
                await redis._redis.set(
                    "metrics:ocr:wer:avg",
                    str(round(self._global_wer.avg, 4))
                )
            if self._global_wer.p50 is not None:
                await redis._redis.set(
                    "metrics:ocr:wer:p50",
                    str(round(self._global_wer.p50, 4))
                )
            if self._global_wer.p95 is not None:
                await redis._redis.set(
                    "metrics:ocr:wer:p95",
                    str(round(self._global_wer.p95, 4))
                )

            # Global Umlaut metrics
            if self._global_umlaut.avg is not None:
                await redis._redis.set(
                    "metrics:ocr:umlaut_accuracy:avg",
                    str(round(self._global_umlaut.avg, 4))
                )

            # Per-backend metrics
            for backend in self._backends:
                if backend in self._cer_stats:
                    cer_stats = self._cer_stats[backend]
                    if cer_stats.avg is not None:
                        await redis._redis.set(
                            f"metrics:ocr:cer:{backend}:avg",
                            str(round(cer_stats.avg, 4))
                        )

                if backend in self._wer_stats:
                    wer_stats = self._wer_stats[backend]
                    if wer_stats.avg is not None:
                        await redis._redis.set(
                            f"metrics:ocr:wer:{backend}:avg",
                            str(round(wer_stats.avg, 4))
                        )

                if backend in self._umlaut_stats:
                    umlaut_stats = self._umlaut_stats[backend]
                    if umlaut_stats.avg is not None:
                        await redis._redis.set(
                            f"metrics:ocr:umlaut:{backend}:avg",
                            str(round(umlaut_stats.avg, 4))
                        )

                if backend in self._time_stats:
                    time_stats = self._time_stats[backend]
                    if time_stats.avg is not None:
                        await redis._redis.set(
                            f"metrics:ocr:time:{backend}:avg",
                            str(round(time_stats.avg, 2))
                        )

                # Backend document counts
                if backend in self._backend_counts:
                    await redis._redis.set(
                        f"metric:ocr.processed.{backend}",
                        str(self._backend_counts[backend])
                    )

            # Total samples count
            await redis._redis.set(
                "metric:ocr.quality_samples",
                str(self._total_samples)
            )

            logger.debug(
                "ocr_metrics_persisted_to_redis",
                total_samples=self._total_samples,
                backends=list(self._backend_counts.keys()),
            )

        except Exception as e:
            logger.warning("ocr_metrics_redis_persist_failed", **safe_error_log(e))

    def get_stats_summary(self) -> Dict[str, Any]:
        """Get summary of all collected stats."""
        return {
            "total_samples": self._total_samples,
            "global": {
                "cer": {
                    "avg": self._global_cer.avg,
                    "p50": self._global_cer.p50,
                    "p95": self._global_cer.p95,
                },
                "wer": {
                    "avg": self._global_wer.avg,
                    "p50": self._global_wer.p50,
                    "p95": self._global_wer.p95,
                },
                "umlaut_accuracy": {
                    "avg": self._global_umlaut.avg,
                },
            },
            "by_backend": {
                backend: {
                    "count": self._backend_counts.get(backend, 0),
                    "cer_avg": self._cer_stats.get(backend, RunningStats()).avg,
                    "wer_avg": self._wer_stats.get(backend, RunningStats()).avg,
                    "umlaut_avg": self._umlaut_stats.get(backend, RunningStats()).avg,
                    "time_avg_ms": self._time_stats.get(backend, RunningStats()).avg,
                }
                for backend in self._backends
                if backend in self._backend_counts
            },
        }


# Global instance getter
_service_instance: Optional[OCRQualityMetricsService] = None


def get_ocr_quality_metrics_service() -> OCRQualityMetricsService:
    """Get global OCR quality metrics service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = OCRQualityMetricsService()
    return _service_instance


async def record_ocr_quality(
    backend: str,
    confidence: float,
    processing_time_ms: float,
    has_umlauts: bool = False,
    german_quality_score: float = 1.0,
    document_type: str = "unknown",
) -> None:
    """
    Convenience function to record OCR quality metrics.

    Args:
        backend: OCR backend used
        confidence: OCR confidence score (0-1)
        processing_time_ms: Processing time in milliseconds
        has_umlauts: Whether umlauts were detected
        german_quality_score: German validation quality score (0-1)
        document_type: Document type
    """
    service = get_ocr_quality_metrics_service()
    await service.record_ocr_result(
        backend=backend,
        confidence=confidence,
        processing_time_ms=processing_time_ms,
        has_umlauts=has_umlauts,
        german_quality_score=german_quality_score,
        document_type=document_type,
    )
