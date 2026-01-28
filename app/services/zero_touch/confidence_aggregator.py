"""
Confidence Aggregation Service.

Aggregiert Confidence-Scores aus mehreren Quellen:
- OCR Confidence (Texterkennung)
- Classification Confidence (Dokumententyp)
- Extraction Confidence (Strukturierte Felder)
- Entity Matching Confidence (Geschaeftspartner-Zuordnung)

Jede Quelle hat eine Gewichtung fuer die Gesamtbewertung.
"""

from dataclasses import dataclass
from typing import List, Optional

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Confidence Weights (Gewichtungen)
# =============================================================================

DEFAULT_WEIGHTS = {
    "ocr_confidence": 0.25,           # OCR-Qualitaet
    "classification_confidence": 0.30, # Dokumententyp-Klassifizierung
    "extraction_confidence": 0.30,     # Feldextraktion
    "entity_confidence": 0.15,         # Geschaeftspartner-Zuordnung
}


@dataclass
class ConfidenceBreakdown:
    """Einzelne Confidence-Quelle mit Bewertung."""

    source: str
    confidence: float
    weight: float
    weighted_score: float


@dataclass
class AggregatedConfidence:
    """Aggregierte Confidence mit Details."""

    overall: float
    breakdown: List[ConfidenceBreakdown]
    auto_processable: bool
    threshold: float


class ConfidenceAggregator:
    """
    Service zum Aggregieren von Confidence-Scores.

    Kombiniert verschiedene Confidence-Quellen zu einem Gesamt-Score,
    der bestimmt, ob ein Dokument automatisch verarbeitet werden kann.
    """

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        auto_threshold: float = 0.90,
    ) -> None:
        """
        Initialisiert den Confidence Aggregator.

        Args:
            weights: Optional custom Gewichtungen. Falls None, werden DEFAULT_WEIGHTS verwendet.
            auto_threshold: Schwellwert fuer automatische Verarbeitung (0.0 - 1.0)
        """
        self._weights = weights or DEFAULT_WEIGHTS.copy()
        self._auto_threshold = auto_threshold

        # Validierung der Gewichtungen
        total_weight = sum(self._weights.values())
        if not (0.99 <= total_weight <= 1.01):  # Toleranz fuer Rundungsfehler
            logger.warning(
                "confidence_weights_sum_invalid",
                total_weight=total_weight,
                expected=1.0,
            )

    def aggregate(
        self,
        ocr_conf: float,
        class_conf: float,
        extract_conf: float,
        entity_conf: Optional[float] = None,
    ) -> AggregatedConfidence:
        """
        Aggregiert Confidence-Scores zu einem Gesamt-Score.

        Args:
            ocr_conf: OCR Confidence (0.0 - 1.0)
            class_conf: Classification Confidence (0.0 - 1.0)
            extract_conf: Extraction Confidence (0.0 - 1.0)
            entity_conf: Optional Entity Matching Confidence (0.0 - 1.0)

        Returns:
            AggregatedConfidence mit Gesamt-Score und Breakdown
        """
        # Input-Validierung
        self._validate_confidence(ocr_conf, "ocr_confidence")
        self._validate_confidence(class_conf, "classification_confidence")
        self._validate_confidence(extract_conf, "extraction_confidence")
        if entity_conf is not None:
            self._validate_confidence(entity_conf, "entity_confidence")

        # Gewichtungen anpassen, falls Entity Confidence fehlt
        weights = self._weights.copy()
        if entity_conf is None:
            # Gewicht proportional auf andere verteilen
            entity_weight = weights["entity_confidence"]
            del weights["entity_confidence"]

            # Neue Summe berechnen
            remaining_sum = sum(weights.values())

            # Proportional umverteilen
            for key in weights:
                weights[key] = weights[key] + (weights[key] / remaining_sum) * entity_weight

            logger.debug(
                "entity_confidence_missing_redistributed",
                original_weights=self._weights,
                adjusted_weights=weights,
            )

        # Breakdown erstellen
        breakdown: List[ConfidenceBreakdown] = []

        # OCR Confidence
        ocr_weighted = ocr_conf * weights["ocr_confidence"]
        breakdown.append(
            ConfidenceBreakdown(
                source="ocr",
                confidence=ocr_conf,
                weight=weights["ocr_confidence"],
                weighted_score=ocr_weighted,
            )
        )

        # Classification Confidence
        class_weighted = class_conf * weights["classification_confidence"]
        breakdown.append(
            ConfidenceBreakdown(
                source="classification",
                confidence=class_conf,
                weight=weights["classification_confidence"],
                weighted_score=class_weighted,
            )
        )

        # Extraction Confidence
        extract_weighted = extract_conf * weights["extraction_confidence"]
        breakdown.append(
            ConfidenceBreakdown(
                source="extraction",
                confidence=extract_conf,
                weight=weights["extraction_confidence"],
                weighted_score=extract_weighted,
            )
        )

        # Entity Confidence (falls vorhanden)
        if entity_conf is not None:
            entity_weighted = entity_conf * weights["entity_confidence"]
            breakdown.append(
                ConfidenceBreakdown(
                    source="entity",
                    confidence=entity_conf,
                    weight=weights["entity_confidence"],
                    weighted_score=entity_weighted,
                )
            )

        # Gesamt-Score berechnen
        overall = sum(item.weighted_score for item in breakdown)

        # Auto-Processable pruefen
        auto_processable = overall >= self._auto_threshold

        logger.info(
            "confidence_aggregated",
            overall=round(overall, 3),
            auto_processable=auto_processable,
            threshold=self._auto_threshold,
            ocr=round(ocr_conf, 3),
            classification=round(class_conf, 3),
            extraction=round(extract_conf, 3),
            entity=round(entity_conf, 3) if entity_conf is not None else None,
        )

        return AggregatedConfidence(
            overall=overall,
            breakdown=breakdown,
            auto_processable=auto_processable,
            threshold=self._auto_threshold,
        )

    def _validate_confidence(self, value: float, name: str) -> None:
        """
        Validiert einen Confidence-Wert.

        Args:
            value: Der zu validierende Wert
            name: Name des Werts (fuer Fehlermeldung)

        Raises:
            ValueError: Wenn der Wert nicht im Bereich [0.0, 1.0] liegt
        """
        if not (0.0 <= value <= 1.0):
            logger.error(
                "invalid_confidence_value",
                name=name,
                value=value,
            )
            raise ValueError(
                f"Ungültiger Confidence-Wert für {name}: {value}. "
                f"Muss zwischen 0.0 und 1.0 liegen."
            )

    def update_threshold(self, new_threshold: float) -> None:
        """
        Aktualisiert den Auto-Processing-Schwellwert.

        Args:
            new_threshold: Neuer Schwellwert (0.0 - 1.0)

        Raises:
            ValueError: Wenn der Schwellwert ungueltig ist
        """
        if not (0.0 <= new_threshold <= 1.0):
            raise ValueError(
                f"Ungültiger Schwellwert: {new_threshold}. "
                f"Muss zwischen 0.0 und 1.0 liegen."
            )

        old_threshold = self._auto_threshold
        self._auto_threshold = new_threshold

        logger.info(
            "confidence_threshold_updated",
            old_threshold=old_threshold,
            new_threshold=new_threshold,
        )

    def update_weights(self, new_weights: dict[str, float]) -> None:
        """
        Aktualisiert die Gewichtungen.

        Args:
            new_weights: Neue Gewichtungen

        Raises:
            ValueError: Wenn die Gewichtungen ungueltig sind
        """
        # Validierung
        required_keys = {"ocr_confidence", "classification_confidence", "extraction_confidence", "entity_confidence"}
        if set(new_weights.keys()) != required_keys:
            raise ValueError(
                f"Ungültige Gewichtungs-Keys. Erwartet: {required_keys}, "
                f"erhalten: {set(new_weights.keys())}"
            )

        total = sum(new_weights.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Gewichtungen müssen zu 1.0 summieren. Aktuell: {total}"
            )

        for key, value in new_weights.items():
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"Ungültige Gewichtung für {key}: {value}. "
                    f"Muss zwischen 0.0 und 1.0 liegen."
                )

        old_weights = self._weights.copy()
        self._weights = new_weights.copy()

        logger.info(
            "confidence_weights_updated",
            old_weights=old_weights,
            new_weights=new_weights,
        )
