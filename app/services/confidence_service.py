"""
Confidence Aggregation Service für Ablage-System OCR.

Zentraler Service für:
- Aggregation von Token-Level Confidence Scores
- Confidence-basierte Backend-Entscheidungen
- Quality Assessment für OCR-Ergebnisse
- Fallback-Trigger basierend auf Confidence-Schwellenwerten

Feinpoliert und durchdacht - Enterprise-grade Confidence Management.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import statistics
import structlog

logger = structlog.get_logger(__name__)


class ConfidenceLevel(Enum):
    """Klassifizierung der Confidence-Stufen."""
    EXCELLENT = "excellent"  # >= 0.95
    HIGH = "high"            # >= 0.85
    MEDIUM = "medium"        # >= 0.70
    LOW = "low"              # >= 0.50
    VERY_LOW = "very_low"    # < 0.50


class QualityDecision(Enum):
    """Entscheidungen basierend auf Confidence."""
    ACCEPT = "accept"              # Ergebnis akzeptieren
    ACCEPT_WITH_WARNING = "accept_with_warning"  # Akzeptieren mit Warnung
    REQUEST_REVIEW = "request_review"      # Manuelle Überprüfung anfordern
    RETRY_DIFFERENT_BACKEND = "retry_different_backend"  # Mit anderem Backend wiederholen
    REJECT = "reject"              # Ergebnis ablehnen


@dataclass
class ConfidenceMetrics:
    """Detaillierte Confidence-Metriken für ein OCR-Ergebnis."""
    overall_confidence: float
    confidence_level: ConfidenceLevel
    mean_token_confidence: float
    min_token_confidence: float
    max_token_confidence: float
    std_deviation: float
    total_tokens: int
    low_confidence_count: int
    low_confidence_ratio: float
    confidence_method: str
    backend: str
    quality_decision: QualityDecision
    should_fallback: bool
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für JSON-Serialisierung."""
        return {
            "overall_confidence": round(self.overall_confidence, 4),
            "confidence_level": self.confidence_level.value,
            "mean_token_confidence": round(self.mean_token_confidence, 4),
            "min_token_confidence": round(self.min_token_confidence, 4),
            "max_token_confidence": round(self.max_token_confidence, 4),
            "std_deviation": round(self.std_deviation, 4),
            "total_tokens": self.total_tokens,
            "low_confidence_count": self.low_confidence_count,
            "low_confidence_ratio": round(self.low_confidence_ratio, 4),
            "confidence_method": self.confidence_method,
            "backend": self.backend,
            "quality_decision": self.quality_decision.value,
            "should_fallback": self.should_fallback,
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class AggregatedConfidence:
    """Aggregierte Confidence über mehrere Backends."""
    backends_used: List[str]
    individual_scores: Dict[str, float]
    aggregated_confidence: float
    confidence_level: ConfidenceLevel
    best_backend: str
    worst_backend: str
    agreement_score: float  # Wie stark stimmen die Backends überein
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backends_used": self.backends_used,
            "individual_scores": {k: round(v, 4) for k, v in self.individual_scores.items()},
            "aggregated_confidence": round(self.aggregated_confidence, 4),
            "confidence_level": self.confidence_level.value,
            "best_backend": self.best_backend,
            "worst_backend": self.worst_backend,
            "agreement_score": round(self.agreement_score, 4),
            "recommendation": self.recommendation,
        }


class ConfidenceService:
    """
    Service für Confidence-Aggregation und Quality Assessment.

    Konfigurierbare Schwellenwerte für verschiedene Use Cases.
    """

    # Konfigurierbare Schwellenwerte
    DEFAULT_THRESHOLDS = {
        "excellent": 0.95,
        "high": 0.85,
        "medium": 0.70,
        "low": 0.50,
        "fallback_trigger": 0.65,  # Unter diesem Wert: Fallback empfohlen
        "reject_trigger": 0.30,    # Unter diesem Wert: Ablehnung empfohlen
        "low_confidence_token_threshold": 0.70,  # Token unter diesem Wert = "low confidence"
    }

    # Backend-spezifische Gewichtungen
    BACKEND_WEIGHTS = {
        "deepseek-janus-pro": 1.0,  # Beste Qualität für komplexe Dokumente
        "got-ocr-2.0": 0.95,        # Sehr gut für Formeln/Tabellen
        "surya": 0.85,              # CPU-Fallback
        "surya-gpu": 0.90,          # GPU-Variante
    }

    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        backend_weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialisiere ConfidenceService.

        Args:
            thresholds: Optionale custom Schwellenwerte
            backend_weights: Optionale custom Backend-Gewichtungen
        """
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.backend_weights = {**self.BACKEND_WEIGHTS, **(backend_weights or {})}

        logger.info(
            "confidence_service_initialized",
            thresholds=self.thresholds,
            backend_count=len(self.backend_weights)
        )

    def classify_confidence(self, confidence: float) -> ConfidenceLevel:
        """
        Klassifiziere einen Confidence-Wert.

        Args:
            confidence: Confidence-Wert zwischen 0 und 1

        Returns:
            ConfidenceLevel Enum
        """
        if confidence >= self.thresholds["excellent"]:
            return ConfidenceLevel.EXCELLENT
        elif confidence >= self.thresholds["high"]:
            return ConfidenceLevel.HIGH
        elif confidence >= self.thresholds["medium"]:
            return ConfidenceLevel.MEDIUM
        elif confidence >= self.thresholds["low"]:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def determine_quality_decision(
        self,
        confidence: float,
        min_confidence: float,
        low_confidence_ratio: float
    ) -> Tuple[QualityDecision, bool, Optional[str]]:
        """
        Bestimme Qualitätsentscheidung basierend auf Confidence-Metriken.

        Args:
            confidence: Overall Confidence
            min_confidence: Minimale Token-Confidence
            low_confidence_ratio: Anteil niedrig-konfidenter Tokens

        Returns:
            Tuple von (Decision, should_fallback, fallback_reason)
        """
        # Unter Reject-Schwelle
        if confidence < self.thresholds["reject_trigger"]:
            return (
                QualityDecision.REJECT,
                True,
                f"Confidence {confidence:.2%} unter Ablehnungsschwelle {self.thresholds['reject_trigger']:.0%}"
            )

        # Unter Fallback-Schwelle
        if confidence < self.thresholds["fallback_trigger"]:
            return (
                QualityDecision.RETRY_DIFFERENT_BACKEND,
                True,
                f"Confidence {confidence:.2%} unter Fallback-Schwelle {self.thresholds['fallback_trigger']:.0%}"
            )

        # Viele niedrig-konfidente Tokens
        if low_confidence_ratio > 0.3:
            return (
                QualityDecision.REQUEST_REVIEW,
                False,
                f"{low_confidence_ratio:.0%} der Tokens haben niedrige Confidence"
            )

        # Sehr niedrige Minimal-Confidence
        if min_confidence < 0.3 and confidence < self.thresholds["high"]:
            return (
                QualityDecision.ACCEPT_WITH_WARNING,
                False,
                f"Einige Tokens mit sehr niedriger Confidence ({min_confidence:.2%})"
            )

        # Alles gut
        return (QualityDecision.ACCEPT, False, None)

    def analyze_ocr_result(
        self,
        confidence: float,
        confidence_details: Optional[Dict[str, Any]] = None,
        backend: str = "unknown"
    ) -> ConfidenceMetrics:
        """
        Analysiere ein OCR-Ergebnis und erstelle detaillierte Metriken.

        Args:
            confidence: Overall Confidence Score
            confidence_details: Optionale Details aus Token-Level Analyse
            backend: Name des verwendeten Backends

        Returns:
            ConfidenceMetrics Objekt
        """
        # Extrahiere Token-Level Details wenn verfügbar
        if confidence_details:
            mean_conf = confidence_details.get("mean_confidence", confidence)
            min_conf = confidence_details.get("min_confidence", confidence)
            total_tokens = confidence_details.get("total_tokens", 0)
            low_conf_count = confidence_details.get("low_confidence_count", 0)
            conf_method = confidence_details.get("method", "token_logits")
            token_confs = confidence_details.get("token_confidences", [])

            # Berechne zusätzliche Statistiken
            if token_confs:
                max_conf = max(token_confs)
                std_dev = statistics.stdev(token_confs) if len(token_confs) > 1 else 0.0
            else:
                max_conf = confidence
                std_dev = 0.0

            low_conf_ratio = low_conf_count / total_tokens if total_tokens > 0 else 0.0
        else:
            # Fallback wenn keine Details verfügbar
            mean_conf = confidence
            min_conf = confidence
            max_conf = confidence
            std_dev = 0.0
            total_tokens = 0
            low_conf_count = 0
            low_conf_ratio = 0.0
            conf_method = "heuristic"

        # Klassifiziere Confidence Level
        conf_level = self.classify_confidence(confidence)

        # Bestimme Quality Decision
        decision, should_fallback, fallback_reason = self.determine_quality_decision(
            confidence, min_conf, low_conf_ratio
        )

        metrics = ConfidenceMetrics(
            overall_confidence=confidence,
            confidence_level=conf_level,
            mean_token_confidence=mean_conf,
            min_token_confidence=min_conf,
            max_token_confidence=max_conf,
            std_deviation=std_dev,
            total_tokens=total_tokens,
            low_confidence_count=low_conf_count,
            low_confidence_ratio=low_conf_ratio,
            confidence_method=conf_method,
            backend=backend,
            quality_decision=decision,
            should_fallback=should_fallback,
            fallback_reason=fallback_reason
        )

        logger.debug(
            "ocr_result_analyzed",
            backend=backend,
            confidence=confidence,
            level=conf_level.value,
            decision=decision.value,
            should_fallback=should_fallback
        )

        return metrics

    def aggregate_confidences(
        self,
        results: List[Dict[str, Any]],
        method: str = "weighted_average"
    ) -> AggregatedConfidence:
        """
        Aggregiere Confidence-Scores von mehreren Backends.

        Args:
            results: Liste von OCR-Ergebnissen mit confidence und backend
            method: Aggregationsmethode ("weighted_average", "max", "median")

        Returns:
            AggregatedConfidence Objekt
        """
        if not results:
            return AggregatedConfidence(
                backends_used=[],
                individual_scores={},
                aggregated_confidence=0.0,
                confidence_level=ConfidenceLevel.VERY_LOW,
                best_backend="",
                worst_backend="",
                agreement_score=0.0,
                recommendation="Keine Ergebnisse zum Aggregieren"
            )

        # Extrahiere Scores und Backends
        individual_scores = {}
        for result in results:
            backend = result.get("backend", "unknown")
            confidence = result.get("confidence", 0.0)
            individual_scores[backend] = confidence

        backends_used = list(individual_scores.keys())
        scores = list(individual_scores.values())

        # Aggregiere basierend auf Methode
        if method == "weighted_average":
            weighted_sum = 0.0
            weight_total = 0.0
            for backend, score in individual_scores.items():
                weight = self.backend_weights.get(backend, 0.8)
                weighted_sum += score * weight
                weight_total += weight
            aggregated = weighted_sum / weight_total if weight_total > 0 else 0.0
        elif method == "max":
            aggregated = max(scores)
        elif method == "median":
            aggregated = statistics.median(scores)
        else:
            aggregated = statistics.mean(scores)

        # Finde bestes und schlechtestes Backend
        best_backend = max(individual_scores, key=individual_scores.get)
        worst_backend = min(individual_scores, key=individual_scores.get)

        # Berechne Agreement Score (wie einheitlich sind die Ergebnisse)
        if len(scores) > 1:
            agreement = 1.0 - (statistics.stdev(scores) / max(statistics.mean(scores), 0.001))
            agreement = max(0.0, min(1.0, agreement))
        else:
            agreement = 1.0

        # Generiere Empfehlung
        conf_level = self.classify_confidence(aggregated)
        if conf_level in [ConfidenceLevel.EXCELLENT, ConfidenceLevel.HIGH]:
            recommendation = f"Verwende Ergebnis von {best_backend} (höchste Confidence)"
        elif agreement < 0.7:
            recommendation = "Backends uneinig - manuelle Überprüfung empfohlen"
        elif conf_level == ConfidenceLevel.MEDIUM:
            recommendation = f"Ergebnis akzeptabel, aber Überprüfung bei kritischen Daten empfohlen"
        else:
            recommendation = "Erneute Verarbeitung mit anderem Backend empfohlen"

        result = AggregatedConfidence(
            backends_used=backends_used,
            individual_scores=individual_scores,
            aggregated_confidence=aggregated,
            confidence_level=conf_level,
            best_backend=best_backend,
            worst_backend=worst_backend,
            agreement_score=agreement,
            recommendation=recommendation
        )

        logger.info(
            "confidences_aggregated",
            backends_count=len(backends_used),
            aggregated=aggregated,
            agreement=agreement,
            best=best_backend
        )

        return result

    def should_trigger_fallback(
        self,
        metrics: ConfidenceMetrics,
        document_type: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Prüfe ob ein Fallback zu einem anderen Backend nötig ist.

        Args:
            metrics: ConfidenceMetrics des aktuellen Ergebnisses
            document_type: Optionaler Dokumenttyp für spezifische Regeln

        Returns:
            Tuple von (should_fallback, reason)
        """
        # Expliziter Fallback aus Metriken
        if metrics.should_fallback:
            return True, metrics.fallback_reason or "Confidence zu niedrig"

        # Dokumenttyp-spezifische Regeln
        if document_type:
            type_thresholds = {
                "invoice": 0.80,    # Rechnungen brauchen hohe Genauigkeit
                "contract": 0.85,   # Verträge noch höher
                "letter": 0.65,     # Briefe toleranter
                "general": 0.70,
            }
            threshold = type_thresholds.get(document_type, 0.70)

            if metrics.overall_confidence < threshold:
                return True, f"Confidence {metrics.overall_confidence:.2%} unter Schwelle für {document_type} ({threshold:.0%})"

        # Sehr hohe Varianz deutet auf inkonsistente Erkennung hin
        if metrics.std_deviation > 0.3:
            return True, f"Hohe Token-Varianz ({metrics.std_deviation:.2f}) deutet auf inkonsistente Erkennung"

        return False, ""

    def get_recommended_backends(
        self,
        failed_backend: str,
        document_type: Optional[str] = None
    ) -> List[str]:
        """
        Empfehle alternative Backends nach fehlgeschlagenem Versuch.

        Args:
            failed_backend: Backend das fehlgeschlagen ist
            document_type: Optionaler Dokumenttyp

        Returns:
            Liste von empfohlenen Backends in Präferenzreihenfolge
        """
        # Backend-Fähigkeiten
        backend_strengths = {
            "deepseek-janus-pro": ["complex", "handwriting", "fraktur", "tables", "german"],
            "got-ocr-2.0": ["formulas", "tables", "markdown", "fast"],
            "surya-gpu": ["fast", "general", "german"],
            "surya": ["cpu_fallback", "general"],
        }

        # Dokumenttyp zu bevorzugten Backends
        type_preferences = {
            "invoice": ["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu"],
            "contract": ["deepseek-janus-pro", "surya-gpu"],
            "letter": ["surya-gpu", "surya", "deepseek-janus-pro"],
            "formula": ["got-ocr-2.0", "deepseek-janus-pro"],
            "general": ["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"],
        }

        # Hole Präferenzliste
        preferences = type_preferences.get(document_type or "general", type_preferences["general"])

        # Filtere das fehlgeschlagene Backend heraus
        recommendations = [b for b in preferences if b != failed_backend]

        logger.debug(
            "backends_recommended",
            failed_backend=failed_backend,
            document_type=document_type,
            recommendations=recommendations
        )

        return recommendations


# Singleton Instance
_confidence_service: Optional[ConfidenceService] = None


def get_confidence_service() -> ConfidenceService:
    """
    Hole Singleton-Instance des ConfidenceService.

    Returns:
        ConfidenceService Instance
    """
    global _confidence_service
    if _confidence_service is None:
        _confidence_service = ConfidenceService()
    return _confidence_service
