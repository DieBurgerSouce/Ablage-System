"""
Konfigurierbare Thresholds für OCR Pipeline.

Zentralisiert alle Performance-relevanten Schwellwerte:
- OCR Confidence Thresholds
- GPU Memory Thresholds
- Batch Processing Thresholds
- A/B Testing Thresholds
- Quality Assurance Thresholds

Alle Werte sind über Umgebungsvariablen konfigurierbar.

Feinpoliert und durchdacht - Enterprise OCR Configuration.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


def _get_env_float(key: str, default: float) -> float:
    """Hole Float-Wert aus Umgebungsvariable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(
            "invalid_env_float",
            key=key,
            value=value,
            using_default=default
        )
        return default


def _get_env_int(key: str, default: int) -> int:
    """Hole Int-Wert aus Umgebungsvariable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(
            "invalid_env_int",
            key=key,
            value=value,
            using_default=default
        )
        return default


def _get_env_bool(key: str, default: bool) -> bool:
    """Hole Bool-Wert aus Umgebungsvariable."""
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


@dataclass
class OCRConfidenceThresholds:
    """
    OCR Confidence Schwellwerte.

    Definiert Grenzen für die Klassifizierung von OCR-Ergebnissen.
    """

    # Minimale Confidence für "akzeptabel"
    # Ergebnisse darunter werden als fehlerhaft markiert
    minimum: float = field(
        default_factory=lambda: _get_env_float("OCR_CONFIDENCE_MIN", 0.3)
    )

    # Schwelle für "niedrige" Qualität (benötigt Review)
    low: float = field(
        default_factory=lambda: _get_env_float("OCR_CONFIDENCE_LOW", 0.6)
    )

    # Schwelle für "mittlere" Qualität (akzeptabel)
    medium: float = field(
        default_factory=lambda: _get_env_float("OCR_CONFIDENCE_MEDIUM", 0.75)
    )

    # Schwelle für "hohe" Qualität (zuverlässig)
    high: float = field(
        default_factory=lambda: _get_env_float("OCR_CONFIDENCE_HIGH", 0.9)
    )

    # Schwelle für "sehr hohe" Qualität (exzellent)
    excellent: float = field(
        default_factory=lambda: _get_env_float("OCR_CONFIDENCE_EXCELLENT", 0.95)
    )

    # Schwelle für automatische Annahme ohne Review
    auto_accept: float = field(
        default_factory=lambda: _get_env_float("OCR_CONFIDENCE_AUTO_ACCEPT", 0.85)
    )

    # Schwelle für automatische Ablehnung/Retry
    auto_reject: float = field(
        default_factory=lambda: _get_env_float("OCR_CONFIDENCE_AUTO_REJECT", 0.4)
    )

    def classify(self, confidence: float) -> str:
        """
        Klassifiziere Confidence-Wert.

        Args:
            confidence: Confidence-Score (0.0 - 1.0)

        Returns:
            Klassifikation: "rejected", "low", "medium", "high", "excellent"
        """
        if confidence < self.minimum:
            return "rejected"
        elif confidence < self.low:
            return "low"
        elif confidence < self.high:
            return "medium"
        elif confidence < self.excellent:
            return "high"
        else:
            return "excellent"

    def needs_review(self, confidence: float) -> bool:
        """Prüfe ob manuelle Review benötigt wird."""
        return confidence < self.auto_accept and confidence >= self.minimum

    def should_retry(self, confidence: float) -> bool:
        """Prüfe ob OCR wiederholt werden sollte."""
        return confidence < self.auto_reject


@dataclass
class GPUMemoryThresholds:
    """
    GPU Memory Schwellwerte.

    Für RTX 4080 mit 16GB VRAM optimiert.
    """

    # Maximale VRAM-Nutzung in Prozent
    max_usage_percent: float = field(
        default_factory=lambda: _get_env_float("GPU_MAX_USAGE_PERCENT", 85.0)
    )

    # Warnungs-Schwelle in Prozent
    warning_percent: float = field(
        default_factory=lambda: _get_env_float("GPU_WARNING_PERCENT", 75.0)
    )

    # Kritische Schwelle in Prozent (OOM-Risiko)
    critical_percent: float = field(
        default_factory=lambda: _get_env_float("GPU_CRITICAL_PERCENT", 90.0)
    )

    # Mindest-Reserve in GB für System
    min_reserve_gb: float = field(
        default_factory=lambda: _get_env_float("GPU_MIN_RESERVE_GB", 2.0)
    )

    # Maximale VRAM pro Backend in GB
    max_per_backend_gb: float = field(
        default_factory=lambda: _get_env_float("GPU_MAX_PER_BACKEND_GB", 12.0)
    )

    # OOM Recovery Timeout in Sekunden
    oom_recovery_timeout: int = field(
        default_factory=lambda: _get_env_int("GPU_OOM_RECOVERY_TIMEOUT", 30)
    )

    # Maximale OOM-Retries pro Operation
    max_oom_retries: int = field(
        default_factory=lambda: _get_env_int("GPU_MAX_OOM_RETRIES", 3)
    )

    def get_max_bytes(self, total_vram_bytes: int) -> int:
        """Berechne maximale nutzbare Bytes basierend auf Total-VRAM."""
        return int(total_vram_bytes * (self.max_usage_percent / 100))

    def get_status(self, usage_percent: float) -> str:
        """
        Bestimme Status basierend auf aktueller Nutzung.

        Returns:
            "ok", "warning", "critical"
        """
        if usage_percent >= self.critical_percent:
            return "critical"
        elif usage_percent >= self.warning_percent:
            return "warning"
        return "ok"


@dataclass
class BatchProcessingThresholds:
    """
    Batch Processing Schwellwerte.

    Kontrolliert adaptive Batch-Größen und Prefetching.
    """

    # Minimale Batch-Größe
    min_batch_size: int = field(
        default_factory=lambda: _get_env_int("BATCH_MIN_SIZE", 1)
    )

    # Maximale Batch-Größe
    max_batch_size: int = field(
        default_factory=lambda: _get_env_int("BATCH_MAX_SIZE", 32)
    )

    # Default Batch-Größe
    default_batch_size: int = field(
        default_factory=lambda: _get_env_int("BATCH_DEFAULT_SIZE", 4)
    )

    # Hysterese: Erfolgreiche Batches bis zur Erhöhung
    hysteresis_threshold: int = field(
        default_factory=lambda: _get_env_int("BATCH_HYSTERESIS_THRESHOLD", 100)
    )

    # Hysterese: Erhöhungsfaktor (z.B. 1.1 = +10%)
    hysteresis_increase_factor: float = field(
        default_factory=lambda: _get_env_float("BATCH_HYSTERESIS_INCREASE", 1.1)
    )

    # OOM: Reduktionsfaktor (z.B. 0.5 = -50%)
    oom_reduction_factor: float = field(
        default_factory=lambda: _get_env_float("BATCH_OOM_REDUCTION", 0.5)
    )

    # Prefetch Queue-Größe
    prefetch_queue_size: int = field(
        default_factory=lambda: _get_env_int("PREFETCH_QUEUE_SIZE", 10)
    )

    # Max Memory für Prefetch in Prozent des RAMs
    prefetch_max_memory_percent: int = field(
        default_factory=lambda: _get_env_int("PREFETCH_MAX_MEMORY_PERCENT", 25)
    )

    def calculate_optimal_batch(
        self,
        available_vram_gb: float,
        memory_per_doc_mb: int = 500
    ) -> int:
        """
        Berechne optimale Batch-Größe.

        Args:
            available_vram_gb: Verfügbarer VRAM in GB
            memory_per_doc_mb: Geschätzter Memory pro Dokument in MB

        Returns:
            Optimale Batch-Größe
        """
        available_mb = available_vram_gb * 1024
        optimal = int(available_mb * 0.85 / memory_per_doc_mb)
        return max(self.min_batch_size, min(optimal, self.max_batch_size))


@dataclass
class ABTestingThresholds:
    """
    A/B Testing Schwellwerte.

    Für statistische Signifikanz und Experiment-Kontrolle.
    """

    # Minimale Sample-Größe für Signifikanz
    min_sample_size: int = field(
        default_factory=lambda: _get_env_int("AB_MIN_SAMPLE_SIZE", 30)
    )

    # Konfidenzlevel für statistische Tests (z.B. 0.95 = 95%)
    confidence_level: float = field(
        default_factory=lambda: _get_env_float("AB_CONFIDENCE_LEVEL", 0.95)
    )

    # Minimaler Effekt für praktische Signifikanz (z.B. 0.02 = 2%)
    min_effect_size: float = field(
        default_factory=lambda: _get_env_float("AB_MIN_EFFECT_SIZE", 0.02)
    )

    # Maximale Experiment-Dauer in Tagen
    max_experiment_days: int = field(
        default_factory=lambda: _get_env_int("AB_MAX_EXPERIMENT_DAYS", 30)
    )

    # Traffic-Split für neues Variant (z.B. 0.5 = 50/50)
    default_traffic_split: float = field(
        default_factory=lambda: _get_env_float("AB_TRAFFIC_SPLIT", 0.5)
    )

    # Early Stopping bei klarem Gewinner
    early_stopping_enabled: bool = field(
        default_factory=lambda: _get_env_bool("AB_EARLY_STOPPING", True)
    )

    # Schwelle für Early Stopping (Posterior Probability)
    early_stopping_threshold: float = field(
        default_factory=lambda: _get_env_float("AB_EARLY_STOPPING_THRESHOLD", 0.99)
    )


@dataclass
class QualityAssuranceThresholds:
    """
    Quality Assurance Schwellwerte.

    Für OCR-Qualitätskontrolle und Human Review.
    """

    # Schwelle für automatische QA-Review
    review_threshold: float = field(
        default_factory=lambda: _get_env_float("QA_REVIEW_THRESHOLD", 0.7)
    )

    # Maximale Fehlerrate pro Batch bevor Eskalation
    max_error_rate: float = field(
        default_factory=lambda: _get_env_float("QA_MAX_ERROR_RATE", 0.1)
    )

    # Maximale Zeit für QA-Review in Stunden
    max_review_hours: int = field(
        default_factory=lambda: _get_env_int("QA_MAX_REVIEW_HOURS", 24)
    )

    # Sampling-Rate für Stichproben-QA (z.B. 0.05 = 5%)
    sampling_rate: float = field(
        default_factory=lambda: _get_env_float("QA_SAMPLING_RATE", 0.05)
    )

    # Mindest-Word-Confidence für deutsche Wörter
    german_word_min_confidence: float = field(
        default_factory=lambda: _get_env_float("QA_GERMAN_WORD_MIN_CONF", 0.7)
    )

    # Umlaut-Validierungs-Schwelle
    umlaut_validation_threshold: float = field(
        default_factory=lambda: _get_env_float("QA_UMLAUT_THRESHOLD", 0.8)
    )


@dataclass
class BackendSpecificThresholds:
    """
    Backend-spezifische Schwellwerte.

    Für DeepSeek, GOT-OCR, Surya etc.
    """

    # DeepSeek Thresholds
    deepseek_min_confidence: float = field(
        default_factory=lambda: _get_env_float("DEEPSEEK_MIN_CONFIDENCE", 0.6)
    )
    deepseek_vram_gb: float = field(
        default_factory=lambda: _get_env_float("DEEPSEEK_VRAM_GB", 12.0)
    )
    deepseek_batch_size: int = field(
        default_factory=lambda: _get_env_int("DEEPSEEK_BATCH_SIZE", 4)
    )

    # GOT-OCR Thresholds
    got_ocr_min_confidence: float = field(
        default_factory=lambda: _get_env_float("GOT_OCR_MIN_CONFIDENCE", 0.65)
    )
    got_ocr_vram_gb: float = field(
        default_factory=lambda: _get_env_float("GOT_OCR_VRAM_GB", 10.0)
    )
    got_ocr_batch_size: int = field(
        default_factory=lambda: _get_env_int("GOT_OCR_BATCH_SIZE", 8)
    )

    # Surya GPU Thresholds
    surya_gpu_min_confidence: float = field(
        default_factory=lambda: _get_env_float("SURYA_GPU_MIN_CONFIDENCE", 0.7)
    )
    surya_gpu_vram_gb: float = field(
        default_factory=lambda: _get_env_float("SURYA_GPU_VRAM_GB", 8.0)
    )
    surya_gpu_batch_size: int = field(
        default_factory=lambda: _get_env_int("SURYA_GPU_BATCH_SIZE", 16)
    )

    # Hybrid Agent Thresholds
    hybrid_fallback_confidence: float = field(
        default_factory=lambda: _get_env_float("HYBRID_FALLBACK_CONFIDENCE", 0.5)
    )
    hybrid_comparison_threshold: float = field(
        default_factory=lambda: _get_env_float("HYBRID_COMPARISON_THRESHOLD", 0.1)
    )

    def get_backend_config(self, backend: str) -> Dict[str, Any]:
        """Hole Konfiguration für spezifisches Backend."""
        configs = {
            "deepseek": {
                "min_confidence": self.deepseek_min_confidence,
                "vram_gb": self.deepseek_vram_gb,
                "batch_size": self.deepseek_batch_size,
            },
            "got_ocr": {
                "min_confidence": self.got_ocr_min_confidence,
                "vram_gb": self.got_ocr_vram_gb,
                "batch_size": self.got_ocr_batch_size,
            },
            "surya_gpu": {
                "min_confidence": self.surya_gpu_min_confidence,
                "vram_gb": self.surya_gpu_vram_gb,
                "batch_size": self.surya_gpu_batch_size,
            },
            "hybrid": {
                "fallback_confidence": self.hybrid_fallback_confidence,
                "comparison_threshold": self.hybrid_comparison_threshold,
            },
        }
        return configs.get(backend, {})


@dataclass
class ThresholdConfig:
    """
    Zentrale Threshold-Konfiguration.

    Aggregiert alle Threshold-Kategorien.
    """

    confidence: OCRConfidenceThresholds = field(
        default_factory=OCRConfidenceThresholds
    )
    gpu_memory: GPUMemoryThresholds = field(
        default_factory=GPUMemoryThresholds
    )
    batch_processing: BatchProcessingThresholds = field(
        default_factory=BatchProcessingThresholds
    )
    ab_testing: ABTestingThresholds = field(
        default_factory=ABTestingThresholds
    )
    quality_assurance: QualityAssuranceThresholds = field(
        default_factory=QualityAssuranceThresholds
    )
    backends: BackendSpecificThresholds = field(
        default_factory=BackendSpecificThresholds
    )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für JSON-Serialisierung."""
        import dataclasses
        return {
            "confidence": dataclasses.asdict(self.confidence),
            "gpu_memory": dataclasses.asdict(self.gpu_memory),
            "batch_processing": dataclasses.asdict(self.batch_processing),
            "ab_testing": dataclasses.asdict(self.ab_testing),
            "quality_assurance": dataclasses.asdict(self.quality_assurance),
            "backends": dataclasses.asdict(self.backends),
        }

    def validate(self) -> List[str]:
        """
        Validiere alle Thresholds auf Konsistenz.

        Returns:
            Liste von Validierungs-Fehlern
        """
        errors = []

        # Confidence Thresholds
        if self.confidence.minimum >= self.confidence.low:
            errors.append("OCR_CONFIDENCE_MIN muss kleiner als OCR_CONFIDENCE_LOW sein")
        if self.confidence.low >= self.confidence.medium:
            errors.append("OCR_CONFIDENCE_LOW muss kleiner als OCR_CONFIDENCE_MEDIUM sein")
        if self.confidence.medium >= self.confidence.high:
            errors.append("OCR_CONFIDENCE_MEDIUM muss kleiner als OCR_CONFIDENCE_HIGH sein")
        if self.confidence.high >= self.confidence.excellent:
            errors.append("OCR_CONFIDENCE_HIGH muss kleiner als OCR_CONFIDENCE_EXCELLENT sein")

        # GPU Thresholds
        if self.gpu_memory.warning_percent >= self.gpu_memory.critical_percent:
            errors.append("GPU_WARNING_PERCENT muss kleiner als GPU_CRITICAL_PERCENT sein")
        if self.gpu_memory.max_usage_percent > 100:
            errors.append("GPU_MAX_USAGE_PERCENT kann nicht über 100 sein")

        # Batch Thresholds
        if self.batch_processing.min_batch_size > self.batch_processing.max_batch_size:
            errors.append("BATCH_MIN_SIZE muss kleiner oder gleich BATCH_MAX_SIZE sein")
        if self.batch_processing.hysteresis_increase_factor <= 1.0:
            errors.append("BATCH_HYSTERESIS_INCREASE muss größer als 1.0 sein")
        if not (0 < self.batch_processing.oom_reduction_factor < 1):
            errors.append("BATCH_OOM_REDUCTION muss zwischen 0 und 1 liegen")

        # A/B Testing Thresholds
        if not (0 < self.ab_testing.confidence_level < 1):
            errors.append("AB_CONFIDENCE_LEVEL muss zwischen 0 und 1 liegen")
        if not (0 < self.ab_testing.default_traffic_split <= 1):
            errors.append("AB_TRAFFIC_SPLIT muss zwischen 0 und 1 liegen")

        return errors


# =============================================================================
# Singleton und Convenience-Funktionen
# =============================================================================

_threshold_config: Optional[ThresholdConfig] = None


def get_threshold_config() -> ThresholdConfig:
    """
    Hole Singleton-Instanz der ThresholdConfig.

    Returns:
        ThresholdConfig-Instanz
    """
    global _threshold_config
    if _threshold_config is None:
        _threshold_config = ThresholdConfig()

        # Validiere und logge Warnungen
        errors = _threshold_config.validate()
        if errors:
            for error in errors:
                logger.warning("threshold_validation_error", error=error)

        logger.info("threshold_config_loaded")

    return _threshold_config


def reload_threshold_config() -> ThresholdConfig:
    """
    Lade Threshold-Konfiguration neu (z.B. nach Env-Änderungen).

    Returns:
        Neu geladene ThresholdConfig
    """
    global _threshold_config
    _threshold_config = ThresholdConfig()
    logger.info("threshold_config_reloaded")
    return _threshold_config


# Convenience-Aliases
def get_confidence_thresholds() -> OCRConfidenceThresholds:
    """Hole OCR Confidence Thresholds."""
    return get_threshold_config().confidence


def get_gpu_thresholds() -> GPUMemoryThresholds:
    """Hole GPU Memory Thresholds."""
    return get_threshold_config().gpu_memory


def get_batch_thresholds() -> BatchProcessingThresholds:
    """Hole Batch Processing Thresholds."""
    return get_threshold_config().batch_processing


def get_ab_thresholds() -> ABTestingThresholds:
    """Hole A/B Testing Thresholds."""
    return get_threshold_config().ab_testing


def get_qa_thresholds() -> QualityAssuranceThresholds:
    """Hole Quality Assurance Thresholds."""
    return get_threshold_config().quality_assurance


def get_backend_thresholds(backend: str) -> Dict[str, Any]:
    """Hole Backend-spezifische Thresholds."""
    return get_threshold_config().backends.get_backend_config(backend)
