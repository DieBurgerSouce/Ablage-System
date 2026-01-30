# -*- coding: utf-8 -*-
"""
Cross-Backend Consistency Service.

Ermöglicht:
- Token-Level Vergleich zwischen OCR-Backends
- Automatisches Einschalten eines 3. Backends bei niedrigem Agreement
- Flagging von Low-Agreement Regionen für manuelles Review
- Consistency-Tracking und Reporting

Feinpoliert und durchdacht - Qualitätssicherung durch Konsistenzprüfung.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import re

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.ensemble_voting import (

    OCRResult,
    EnsembleResult,
    EnsembleVotingService,
    get_ensemble_service,
    calculate_agreement,
    needleman_wunsch_align,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class ConsistencyLevel(str, Enum):
    """Konsistenz-Niveau zwischen Backends."""
    HIGH = "high"           # >90% Agreement
    MEDIUM = "medium"       # 70-90% Agreement
    LOW = "low"             # 50-70% Agreement
    CRITICAL = "critical"   # <50% Agreement


class ReviewPriority(str, Enum):
    """Priorität für manuelles Review."""
    IMMEDIATE = "immediate"    # Kritische Inkonsistenz
    HIGH = "high"              # Signifikante Abweichungen
    NORMAL = "normal"          # Geringe Abweichungen
    LOW = "low"                # Nur zur Info


class RegionType(str, Enum):
    """Typ einer inkonsistenten Region."""
    TEXT_BLOCK = "text_block"
    LINE = "line"
    WORD = "word"
    CHARACTER = "character"
    NUMBER = "number"
    DATE = "date"
    AMOUNT = "amount"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class InconsistentRegion:
    """Eine Region mit Inkonsistenz zwischen Backends."""
    region_id: str
    region_type: RegionType
    start_position: int
    end_position: int
    backend_values: Dict[str, str]  # backend -> text
    backend_confidences: Dict[str, float]  # backend -> confidence
    agreement_score: float
    consistency_level: ConsistencyLevel
    review_priority: ReviewPriority
    suggested_value: str
    suggestion_confidence: float
    context_before: str = ""
    context_after: str = ""
    is_critical_field: bool = False  # z.B. Betrag, Datum

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "region_type": self.region_type.value,
            "start_position": self.start_position,
            "end_position": self.end_position,
            "backend_values": self.backend_values,
            "backend_confidences": {k: round(v, 3) for k, v in self.backend_confidences.items()},
            "agreement_score": round(self.agreement_score, 3),
            "consistency_level": self.consistency_level.value,
            "review_priority": self.review_priority.value,
            "suggested_value": self.suggested_value,
            "suggestion_confidence": round(self.suggestion_confidence, 3),
            "context_before": self.context_before,
            "context_after": self.context_after,
            "is_critical_field": self.is_critical_field,
        }


@dataclass
class ConsistencyReport:
    """Bericht über Cross-Backend Konsistenz."""
    document_id: str
    backends_used: List[str]
    overall_agreement: float
    consistency_level: ConsistencyLevel
    total_regions_analyzed: int
    inconsistent_regions: List[InconsistentRegion]
    high_priority_count: int
    needs_third_backend: bool
    third_backend_triggered: bool
    third_backend_name: Optional[str] = None
    final_text: str = ""
    final_confidence: float = 0.0
    processing_time_ms: int = 0
    recommendations: List[str] = field(default_factory=list)
    analysis_timestamp: str = ""

    def __post_init__(self):
        if not self.analysis_timestamp:
            self.analysis_timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "backends_used": self.backends_used,
            "overall_agreement": round(self.overall_agreement, 3),
            "consistency_level": self.consistency_level.value,
            "total_regions_analyzed": self.total_regions_analyzed,
            "inconsistent_region_count": len(self.inconsistent_regions),
            "inconsistent_regions": [r.to_dict() for r in self.inconsistent_regions],
            "high_priority_count": self.high_priority_count,
            "needs_third_backend": self.needs_third_backend,
            "third_backend_triggered": self.third_backend_triggered,
            "third_backend_name": self.third_backend_name,
            "final_text": self.final_text,
            "final_confidence": round(self.final_confidence, 3),
            "processing_time_ms": self.processing_time_ms,
            "recommendations": self.recommendations,
            "analysis_timestamp": self.analysis_timestamp,
        }


@dataclass
class ConsistencyConfig:
    """Konfiguration für Cross-Backend Consistency."""
    # Agreement-Schwellenwerte
    high_agreement_threshold: float = 0.90
    medium_agreement_threshold: float = 0.70
    low_agreement_threshold: float = 0.50

    # Third-Backend Trigger
    trigger_third_backend_threshold: float = 0.80
    trigger_third_backend_on_critical: bool = True

    # Review-Schwellenwerte
    immediate_review_threshold: float = 0.40
    high_review_threshold: float = 0.60

    # Kritische Felder (Pattern)
    critical_field_patterns: List[str] = field(default_factory=lambda: [
        r"\d{1,3}[.,]\d{3}[.,]\d{2}",  # Beträge 1.234,56
        r"\d{1,2}\.\d{1,2}\.\d{2,4}",   # Datum DD.MM.YYYY
        r"[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}",  # IBAN
        r"\d{4,}",  # Längere Zahlen (Rechnungsnummer etc.)
    ])

    # Backend-Präferenzen für Third-Backend
    third_backend_preference: List[str] = field(default_factory=lambda: [
        "deepseek",
        "got_ocr",
        "surya_gpu",
        "surya_cpu",
    ])


# =============================================================================
# Cross-Backend Consistency Service
# =============================================================================


class CrossBackendConsistencyService:
    """
    Service zur Überprüfung der Konsistenz zwischen OCR-Backends.

    Features:
    - Token-Level Agreement-Berechnung
    - Automatisches Triggern eines 3. Backends
    - Region-basiertes Flagging für Review
    - Kritische Feld-Erkennung
    """

    def __init__(
        self,
        config: Optional[ConsistencyConfig] = None,
        db: Optional[AsyncSession] = None,
    ):
        """Initialisiere Cross-Backend Consistency Service."""
        self.config = config or ConsistencyConfig()
        self.db = db
        self._ensemble_service = get_ensemble_service()

        # Kompiliere kritische Patterns
        self._critical_patterns = [
            re.compile(p) for p in self.config.critical_field_patterns
        ]

        logger.info(
            "cross_backend_consistency_service_initialized",
            high_threshold=self.config.high_agreement_threshold,
            third_backend_threshold=self.config.trigger_third_backend_threshold,
        )

    async def analyze_consistency(
        self,
        document_id: str,
        results: List[OCRResult],
        trigger_third_backend: bool = True,
        third_backend_callback: Optional[Any] = None,
    ) -> ConsistencyReport:
        """
        Analysiert die Konsistenz zwischen OCR-Backend-Ergebnissen.

        Args:
            document_id: Dokument-ID
            results: Liste von OCR-Ergebnissen
            trigger_third_backend: Ob 3. Backend bei Bedarf getriggert werden soll
            third_backend_callback: Async-Funktion zum Aufrufen des 3. Backends

        Returns:
            ConsistencyReport mit Analyse-Ergebnissen
        """
        import time
        start_time = time.time()

        if len(results) < 2:
            # Mindestens 2 Ergebnisse für Konsistenz-Vergleich
            return ConsistencyReport(
                document_id=document_id,
                backends_used=[r.backend for r in results],
                overall_agreement=1.0,
                consistency_level=ConsistencyLevel.HIGH,
                total_regions_analyzed=0,
                inconsistent_regions=[],
                high_priority_count=0,
                needs_third_backend=False,
                third_backend_triggered=False,
                final_text=results[0].text if results else "",
                final_confidence=results[0].confidence if results else 0.0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                recommendations=["Nur ein Backend verwendet - keine Konsistenzprüfung möglich."],
            )

        backends_used = [r.backend for r in results]

        # 1. Gesamt-Agreement berechnen
        overall_agreement = calculate_agreement(results)
        consistency_level = self._get_consistency_level(overall_agreement)

        # 2. Region-Level Analyse
        inconsistent_regions = self._analyze_regions(results)

        # 3. High-Priority zählen
        high_priority_count = sum(
            1 for r in inconsistent_regions
            if r.review_priority in [ReviewPriority.IMMEDIATE, ReviewPriority.HIGH]
        )

        # 4. Prüfe ob 3. Backend nötig
        needs_third_backend = (
            overall_agreement < self.config.trigger_third_backend_threshold
            or (self.config.trigger_third_backend_on_critical and
                any(r.is_critical_field and r.agreement_score < 0.7 for r in inconsistent_regions))
        )

        # 5. Third Backend triggern falls gewünscht
        third_backend_triggered = False
        third_backend_name = None

        if needs_third_backend and trigger_third_backend and third_backend_callback:
            third_result = await self._trigger_third_backend(
                results, third_backend_callback
            )
            if third_result:
                results.append(third_result)
                third_backend_triggered = True
                third_backend_name = third_result.backend
                backends_used.append(third_result.backend)

                # Re-analyse mit 3. Backend
                overall_agreement = calculate_agreement(results)
                consistency_level = self._get_consistency_level(overall_agreement)
                inconsistent_regions = self._analyze_regions(results)

        # 6. Finales Ergebnis mit Ensemble Voting
        ensemble_result = self._ensemble_service.combine(
            results,
            method="character_level" if consistency_level in [ConsistencyLevel.LOW, ConsistencyLevel.CRITICAL]
            else "weighted"
        )

        # 7. Recommendations generieren
        recommendations = self._generate_recommendations(
            consistency_level, inconsistent_regions, third_backend_triggered
        )

        processing_time = int((time.time() - start_time) * 1000)

        logger.info(
            "consistency_analysis_complete",
            document_id=document_id,
            backends=backends_used,
            agreement=round(overall_agreement, 3),
            level=consistency_level.value,
            inconsistent_count=len(inconsistent_regions),
            high_priority=high_priority_count,
            third_backend=third_backend_triggered,
            processing_ms=processing_time,
        )

        return ConsistencyReport(
            document_id=document_id,
            backends_used=backends_used,
            overall_agreement=overall_agreement,
            consistency_level=consistency_level,
            total_regions_analyzed=len(inconsistent_regions) + self._count_consistent_regions(results),
            inconsistent_regions=inconsistent_regions,
            high_priority_count=high_priority_count,
            needs_third_backend=needs_third_backend,
            third_backend_triggered=third_backend_triggered,
            third_backend_name=third_backend_name,
            final_text=ensemble_result.text,
            final_confidence=ensemble_result.confidence,
            processing_time_ms=processing_time,
            recommendations=recommendations,
        )

    def _get_consistency_level(self, agreement: float) -> ConsistencyLevel:
        """Bestimmt das Konsistenz-Niveau basierend auf Agreement-Score."""
        if agreement >= self.config.high_agreement_threshold:
            return ConsistencyLevel.HIGH
        elif agreement >= self.config.medium_agreement_threshold:
            return ConsistencyLevel.MEDIUM
        elif agreement >= self.config.low_agreement_threshold:
            return ConsistencyLevel.LOW
        else:
            return ConsistencyLevel.CRITICAL

    def _analyze_regions(self, results: List[OCRResult]) -> List[InconsistentRegion]:
        """
        Analysiert Regionen auf Inkonsistenzen.

        Verwendet Needleman-Wunsch Alignment für präzisen Vergleich.
        """
        if len(results) < 2:
            return []

        inconsistent_regions: List[InconsistentRegion] = []
        texts = [r.text for r in results]

        # Referenz-Text (längster)
        reference_idx = max(range(len(texts)), key=lambda i: len(texts[i]))
        reference_text = texts[reference_idx]

        if not reference_text:
            return []

        # Aligniere alle Texte
        alignments: List[Tuple[str, str]] = []
        for i, text in enumerate(texts):
            if i == reference_idx:
                alignments.append((reference_text, reference_text))
            else:
                aligned_ref, aligned_other = needleman_wunsch_align(reference_text, text)
                alignments.append((aligned_ref, aligned_other))

        # Wort-weise Analyse
        words_by_backend = self._extract_words_with_positions(results)

        region_idx = 0
        for pos, word_data in enumerate(words_by_backend):
            if len(word_data) < 2:
                continue

            # Vergleiche Wörter an dieser Position
            unique_values = set(word_data.values())

            if len(unique_values) > 1:
                # Inkonsistenz gefunden
                agreement = self._calculate_word_agreement(word_data)

                # Prüfe ob kritisches Feld
                is_critical = any(
                    pattern.search(v) for v in word_data.values()
                    for pattern in self._critical_patterns
                )

                # Bestimme Region-Typ
                region_type = self._detect_region_type(list(word_data.values())[0])

                # Bestimme Review-Priorität
                priority = self._determine_review_priority(agreement, is_critical)

                # Suggestion mit gewichtetem Voting
                suggested, suggestion_conf = self._get_suggestion(word_data, results)

                # Kontext extrahieren
                context_before, context_after = self._extract_context(
                    reference_text, pos, words_by_backend
                )

                inconsistent_regions.append(InconsistentRegion(
                    region_id=f"{region_idx}",
                    region_type=region_type,
                    start_position=pos,
                    end_position=pos,
                    backend_values=word_data,
                    backend_confidences={
                        r.backend: r.confidence for r in results if r.backend in word_data
                    },
                    agreement_score=agreement,
                    consistency_level=self._get_consistency_level(agreement),
                    review_priority=priority,
                    suggested_value=suggested,
                    suggestion_confidence=suggestion_conf,
                    context_before=context_before,
                    context_after=context_after,
                    is_critical_field=is_critical,
                ))
                region_idx += 1

        return inconsistent_regions

    def _extract_words_with_positions(
        self, results: List[OCRResult]
    ) -> List[Dict[str, str]]:
        """Extrahiert Wörter mit Positionen für alle Backends."""
        # Tokenisiere alle Texte
        tokenized = {r.backend: r.text.split() for r in results}

        # Finde maximale Länge
        max_len = max(len(tokens) for tokens in tokenized.values()) if tokenized else 0

        # Erstelle Position-zu-Wort Mapping
        position_words: List[Dict[str, str]] = []

        for pos in range(max_len):
            words_at_pos = {}
            for backend, tokens in tokenized.items():
                if pos < len(tokens):
                    words_at_pos[backend] = tokens[pos]
            position_words.append(words_at_pos)

        return position_words

    def _calculate_word_agreement(self, word_data: Dict[str, str]) -> float:
        """Berechnet Agreement-Score für ein Wort."""
        if len(word_data) < 2:
            return 1.0

        words = list(word_data.values())

        # Paarweise Similarity
        similarities = []
        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                sim = SequenceMatcher(None, words[i].lower(), words[j].lower()).ratio()
                similarities.append(sim)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _detect_region_type(self, value: str) -> RegionType:
        """Erkennt den Typ einer Region basierend auf dem Wert."""
        value = value.strip()

        # Betrag
        if re.match(r"^[\d.,]+\s*€?$", value) or re.match(r"^€?\s*[\d.,]+$", value):
            return RegionType.AMOUNT

        # Datum
        if re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", value):
            return RegionType.DATE

        # Zahl
        if re.match(r"^\d+$", value):
            return RegionType.NUMBER

        # Standard: Wort
        return RegionType.WORD

    def _determine_review_priority(self, agreement: float, is_critical: bool) -> ReviewPriority:
        """Bestimmt die Review-Priorität."""
        if is_critical:
            if agreement < self.config.immediate_review_threshold:
                return ReviewPriority.IMMEDIATE
            elif agreement < self.config.high_review_threshold:
                return ReviewPriority.HIGH
            else:
                return ReviewPriority.NORMAL
        else:
            if agreement < self.config.immediate_review_threshold:
                return ReviewPriority.HIGH
            elif agreement < self.config.high_review_threshold:
                return ReviewPriority.NORMAL
            else:
                return ReviewPriority.LOW

    def _get_suggestion(
        self, word_data: Dict[str, str], results: List[OCRResult]
    ) -> Tuple[str, float]:
        """Generiert Suggestion mit gewichtetem Voting."""
        # Gewichtetes Voting
        scores: Dict[str, float] = {}

        for backend, word in word_data.items():
            # Finde Confidence für dieses Backend
            confidence = 0.8  # Default
            for r in results:
                if r.backend == backend:
                    confidence = r.confidence
                    break

            # Gewicht aus Ensemble-Service
            weight = self._ensemble_service._get_weight(backend).effective_weight
            score = confidence * weight

            if word not in scores:
                scores[word] = 0.0
            scores[word] += score

        if not scores:
            return "", 0.0

        # Bestes Wort
        best_word = max(scores.keys(), key=lambda w: scores[w])
        total_score = sum(scores.values())
        suggestion_conf = scores[best_word] / total_score if total_score > 0 else 0.0

        return best_word, suggestion_conf

    def _extract_context(
        self,
        reference_text: str,
        position: int,
        words_by_position: List[Dict[str, str]],
    ) -> Tuple[str, str]:
        """Extrahiert Kontext vor und nach einer Position."""
        context_size = 3  # Wörter

        # Kontext vor
        before_words = []
        for i in range(max(0, position - context_size), position):
            if i < len(words_by_position) and words_by_position[i]:
                # Nehme ersten verfügbaren Wert
                before_words.append(list(words_by_position[i].values())[0])
        context_before = " ".join(before_words)

        # Kontext nach
        after_words = []
        for i in range(position + 1, min(len(words_by_position), position + context_size + 1)):
            if i < len(words_by_position) and words_by_position[i]:
                after_words.append(list(words_by_position[i].values())[0])
        context_after = " ".join(after_words)

        return context_before, context_after

    def _count_consistent_regions(self, results: List[OCRResult]) -> int:
        """Zählt konsistente Regionen (Wörter mit vollem Agreement)."""
        words_by_pos = self._extract_words_with_positions(results)

        consistent = 0
        for word_data in words_by_pos:
            if len(set(word_data.values())) <= 1:
                consistent += 1

        return consistent

    async def _trigger_third_backend(
        self,
        existing_results: List[OCRResult],
        callback: Any,
    ) -> Optional[OCRResult]:
        """Triggert ein drittes Backend für bessere Konsistenz."""
        existing_backends = {r.backend for r in existing_results}

        # Finde verfügbares Backend nach Präferenz
        for preferred in self.config.third_backend_preference:
            if preferred not in existing_backends:
                try:
                    logger.info(
                        "triggering_third_backend",
                        backend=preferred,
                        existing=list(existing_backends),
                    )

                    # Callback aufrufen
                    result = await callback(preferred)

                    if result:
                        return result

                except Exception as e:
                    logger.error(
                        "third_backend_trigger_failed",
                        backend=preferred,
                        **safe_error_log(e),
                    )
                    continue

        return None

    def _generate_recommendations(
        self,
        consistency_level: ConsistencyLevel,
        regions: List[InconsistentRegion],
        third_backend_used: bool,
    ) -> List[str]:
        """Generiert Empfehlungen basierend auf der Analyse."""
        recommendations = []

        if consistency_level == ConsistencyLevel.CRITICAL:
            recommendations.append(
                "KRITISCH: Sehr niedrige Übereinstimmung zwischen Backends. "
                "Manuelles Review dringend empfohlen."
            )
        elif consistency_level == ConsistencyLevel.LOW:
            recommendations.append(
                "Niedrige Übereinstimmung erkannt. "
                "Bitte kritische Felder (Beträge, Daten) prüfen."
            )

        # Critical Fields
        critical_regions = [r for r in regions if r.is_critical_field]
        if critical_regions:
            recommendations.append(
                f"{len(critical_regions)} kritische Felder mit Inkonsistenzen gefunden. "
                "Diese sollten prioritär geprüft werden."
            )

        # Immediate Review
        immediate = [r for r in regions if r.review_priority == ReviewPriority.IMMEDIATE]
        if immediate:
            recommendations.append(
                f"{len(immediate)} Regionen erfordern sofortiges Review."
            )

        # Third Backend
        if third_backend_used:
            recommendations.append(
                "Ein drittes Backend wurde zur Verbesserung der Konsistenz hinzugezogen."
            )

        if not recommendations:
            recommendations.append("Gute Übereinstimmung zwischen Backends. Keine besonderen Maßnahmen erforderlich.")

        return recommendations

    def get_regions_for_review(
        self,
        report: ConsistencyReport,
        min_priority: ReviewPriority = ReviewPriority.NORMAL,
    ) -> List[InconsistentRegion]:
        """Filtert Regionen nach Review-Priorität."""
        priority_order = [
            ReviewPriority.IMMEDIATE,
            ReviewPriority.HIGH,
            ReviewPriority.NORMAL,
            ReviewPriority.LOW,
        ]

        min_idx = priority_order.index(min_priority)
        allowed_priorities = set(priority_order[:min_idx + 1])

        return [
            r for r in report.inconsistent_regions
            if r.review_priority in allowed_priorities
        ]


# =============================================================================
# Singleton
# =============================================================================


_consistency_service: Optional[CrossBackendConsistencyService] = None


def get_cross_backend_consistency_service(
    config: Optional[ConsistencyConfig] = None,
    db: Optional[AsyncSession] = None,
) -> CrossBackendConsistencyService:
    """Hole Cross-Backend Consistency Service Instanz."""
    global _consistency_service
    if _consistency_service is None or db is not None:
        _consistency_service = CrossBackendConsistencyService(config=config, db=db)
    return _consistency_service


# =============================================================================
# Convenience Functions
# =============================================================================


async def check_backend_consistency(
    document_id: str,
    ocr_results: List[Dict[str, Any]],
    trigger_third_backend: bool = False,
) -> Dict[str, Any]:
    """
    Convenience-Funktion zur Konsistenzprüfung.

    Args:
        document_id: Dokument-ID
        ocr_results: Liste von OCR-Ergebnissen als Dictionaries
        trigger_third_backend: Ob drittes Backend getriggert werden soll

    Returns:
        ConsistencyReport als Dictionary
    """
    service = get_cross_backend_consistency_service()

    # Konvertiere zu OCRResult
    results = [
        OCRResult(
            backend=r.get("backend", "unknown"),
            text=r.get("text", ""),
            confidence=r.get("confidence", 0.0),
            tokens=r.get("tokens"),
            token_confidences=r.get("token_confidences"),
        )
        for r in ocr_results
    ]

    report = await service.analyze_consistency(
        document_id=document_id,
        results=results,
        trigger_third_backend=trigger_third_backend,
    )

    return report.to_dict()


def calculate_backend_agreement(
    text1: str,
    text2: str,
    text3: Optional[str] = None,
) -> float:
    """
    Berechnet Agreement-Score zwischen 2-3 Texten.

    Args:
        text1: Erster Text
        text2: Zweiter Text
        text3: Optionaler dritter Text

    Returns:
        Agreement-Score (0-1)
    """
    texts = [text1, text2]
    if text3:
        texts.append(text3)

    results = [
        OCRResult(backend=f"backend_{i}", text=t, confidence=1.0)
        for i, t in enumerate(texts)
    ]

    return calculate_agreement(results)
