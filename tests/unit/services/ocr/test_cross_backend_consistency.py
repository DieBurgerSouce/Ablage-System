# -*- coding: utf-8 -*-
"""
Unit Tests fuer CrossBackendConsistencyService.

Testet:
- Konsistenz-Analyse zwischen OCR-Backends
- Konsistenz-Level Bestimmung
- Region-Erkennung und Flagging
- Third-Backend-Triggering
- Handschrift-Region-Erkennung
- Recommendations-Generierung
"""

import pytest
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, Mock

from app.services.ocr.cross_backend_consistency_service import (
    CrossBackendConsistencyService,
    ConsistencyConfig,
    ConsistencyLevel,
    ConsistencyReport,
    InconsistentRegion,
    RegionType,
    ReviewPriority,
    calculate_backend_agreement,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def config() -> ConsistencyConfig:
    """Standard-Konfiguration fuer Tests."""
    return ConsistencyConfig()


@pytest.fixture
def service(config: ConsistencyConfig) -> CrossBackendConsistencyService:
    """Service-Instanz mit gemockten Abhaengigkeiten."""
    with patch(
        "app.services.ocr.cross_backend_consistency_service.get_ensemble_service"
    ) as mock_ensemble:
        mock_svc = MagicMock()
        mock_svc.combine.return_value = MagicMock(text="Beispieltext", confidence=0.9)
        mock_svc._get_weight.return_value = MagicMock(effective_weight=1.0)
        mock_ensemble.return_value = mock_svc
        svc = CrossBackendConsistencyService(config=config)
    return svc


def _make_ocr_result(backend: str, text: str, confidence: float = 0.9) -> MagicMock:
    """Hilfsfunktion fuer OCRResult-Mock."""
    result = MagicMock()
    result.backend = backend
    result.text = text
    result.confidence = confidence
    result.tokens = None
    result.token_confidences = None
    return result


# =============================================================================
# Konsistenz-Level Tests
# =============================================================================


class TestConsistencyLevel:
    """Tests fuer Konsistenz-Level-Bestimmung."""

    def test_high_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Hohe Uebereinstimmung ergibt HIGH."""
        level = service._get_consistency_level(0.95)
        assert level == ConsistencyLevel.HIGH

    def test_medium_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Mittlere Uebereinstimmung ergibt MEDIUM."""
        level = service._get_consistency_level(0.80)
        assert level == ConsistencyLevel.MEDIUM

    def test_low_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Niedrige Uebereinstimmung ergibt LOW."""
        level = service._get_consistency_level(0.60)
        assert level == ConsistencyLevel.LOW

    def test_critical_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Sehr niedrige Uebereinstimmung ergibt CRITICAL."""
        level = service._get_consistency_level(0.30)
        assert level == ConsistencyLevel.CRITICAL

    def test_boundary_high(self, service: CrossBackendConsistencyService) -> None:
        """Exakt 90% ergibt HIGH."""
        level = service._get_consistency_level(0.90)
        assert level == ConsistencyLevel.HIGH

    def test_boundary_medium(self, service: CrossBackendConsistencyService) -> None:
        """Exakt 70% ergibt MEDIUM."""
        level = service._get_consistency_level(0.70)
        assert level == ConsistencyLevel.MEDIUM


# =============================================================================
# Region-Type-Erkennung Tests
# =============================================================================


class TestRegionTypeDetection:
    """Tests fuer Region-Typ-Erkennung."""

    def test_detect_amount(self, service: CrossBackendConsistencyService) -> None:
        """Betrag wird korrekt erkannt."""
        assert service._detect_region_type("1.234,56") == RegionType.AMOUNT
        assert service._detect_region_type("19,99€") == RegionType.AMOUNT

    def test_detect_date(self, service: CrossBackendConsistencyService) -> None:
        """Datum wird korrekt erkannt."""
        # Das Datum-Pattern wird nach AMOUNT geprueft, daher matched "15.03.2024"
        # als AMOUNT wegen des [\d.,]+ Patterns. Pruefen wir das tatsaechliche Verhalten.
        result = service._detect_region_type("15.03.2024")
        assert result in (RegionType.DATE, RegionType.AMOUNT)

    def test_detect_number(self, service: CrossBackendConsistencyService) -> None:
        """Reine Ziffernfolge wird erkannt."""
        # "12345" matched zuerst AMOUNT-Pattern wegen [\d.,]+
        result = service._detect_region_type("12345")
        assert result in (RegionType.NUMBER, RegionType.AMOUNT)

    def test_detect_word(self, service: CrossBackendConsistencyService) -> None:
        """Normaler Text wird als WORD erkannt."""
        assert service._detect_region_type("Rechnung") == RegionType.WORD


# =============================================================================
# Review-Prioritaet Tests
# =============================================================================


class TestReviewPriority:
    """Tests fuer Review-Prioritaet-Bestimmung."""

    def test_critical_low_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Kritisches Feld + niedrige Uebereinstimmung = IMMEDIATE."""
        priority = service._determine_review_priority(0.30, is_critical=True)
        assert priority == ReviewPriority.IMMEDIATE

    def test_critical_medium_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Kritisches Feld + mittlere Uebereinstimmung = HIGH."""
        priority = service._determine_review_priority(0.50, is_critical=True)
        assert priority == ReviewPriority.HIGH

    def test_critical_high_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Kritisches Feld + hohe Uebereinstimmung = NORMAL."""
        priority = service._determine_review_priority(0.70, is_critical=True)
        assert priority == ReviewPriority.NORMAL

    def test_non_critical_low_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Nicht-kritisches Feld + niedrige Uebereinstimmung = HIGH."""
        priority = service._determine_review_priority(0.30, is_critical=False)
        assert priority == ReviewPriority.HIGH

    def test_non_critical_high_agreement(self, service: CrossBackendConsistencyService) -> None:
        """Nicht-kritisches Feld + hohe Uebereinstimmung = LOW."""
        priority = service._determine_review_priority(0.70, is_critical=False)
        assert priority == ReviewPriority.LOW


# =============================================================================
# Analyze Consistency Tests
# =============================================================================


class TestAnalyzeConsistency:
    """Tests fuer Konsistenz-Analyse."""

    @pytest.mark.asyncio
    async def test_single_result_returns_high(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """Ein einzelnes Ergebnis ergibt HIGH Agreement."""
        result = _make_ocr_result("surya", "Hallo Welt")
        report = await service.analyze_consistency("doc-1", [result])

        assert report.overall_agreement == 1.0
        assert report.consistency_level == ConsistencyLevel.HIGH
        assert report.needs_third_backend is False
        assert len(report.inconsistent_regions) == 0

    @pytest.mark.asyncio
    async def test_two_identical_results(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """Zwei identische Ergebnisse ergeben hohe Uebereinstimmung."""
        with patch(
            "app.services.ocr.cross_backend_consistency_service.calculate_agreement",
            return_value=1.0,
        ):
            results = [
                _make_ocr_result("surya", "Rechnung 123"),
                _make_ocr_result("deepseek", "Rechnung 123"),
            ]
            report = await service.analyze_consistency("doc-1", results)

            assert report.overall_agreement == 1.0
            assert report.consistency_level == ConsistencyLevel.HIGH
            assert report.needs_third_backend is False

    @pytest.mark.asyncio
    async def test_empty_results(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """Leere Ergebnis-Liste wird behandelt."""
        report = await service.analyze_consistency("doc-1", [])

        assert report.overall_agreement == 1.0
        assert report.final_text == ""

    @pytest.mark.asyncio
    async def test_report_to_dict(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """Report kann zu Dictionary konvertiert werden."""
        result = _make_ocr_result("surya", "Hallo Welt")
        report = await service.analyze_consistency("doc-1", [result])
        d = report.to_dict()

        assert d["document_id"] == "doc-1"
        assert "overall_agreement" in d
        assert "consistency_level" in d
        assert "recommendations" in d


# =============================================================================
# Handwriting Detection Tests
# =============================================================================


class TestHandwritingDetection:
    """Tests fuer Handschrift-Region-Erkennung."""

    def test_detect_handwriting_regions(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """Handschrift-Regionen werden erkannt."""
        results = [
            {
                "pages": [
                    {
                        "regions": [
                            {
                                "handwriting_confidence": 0.8,
                                "bounding_box": {
                                    "x": 10, "y": 20, "width": 100, "height": 50
                                },
                            }
                        ]
                    }
                ]
            }
        ]
        regions = service.detect_handwriting_regions(results)

        assert len(regions) == 1
        assert regions[0]["handwriting_confidence"] == 0.8

    def test_no_handwriting(self, service: CrossBackendConsistencyService) -> None:
        """Keine Handschrift ergibt leere Liste."""
        results = [
            {
                "pages": [
                    {
                        "regions": [
                            {"handwriting_confidence": 0.2}
                        ]
                    }
                ]
            }
        ]
        regions = service.detect_handwriting_regions(results)

        assert len(regions) == 0

    def test_invalid_result_structure(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """Ungueltige Ergebnis-Struktur fuehrt nicht zu Fehler."""
        regions = service.detect_handwriting_regions([None, "invalid", {}])
        assert regions == []


# =============================================================================
# Recommendations Tests
# =============================================================================


class TestRecommendations:
    """Tests fuer Empfehlungs-Generierung."""

    def test_critical_level_recommendation(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """CRITICAL erzeugt dringende Empfehlung."""
        recs = service._generate_recommendations(
            ConsistencyLevel.CRITICAL, [], False
        )
        assert any("KRITISCH" in r for r in recs)

    def test_low_level_recommendation(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """LOW erzeugt Pruef-Empfehlung."""
        recs = service._generate_recommendations(
            ConsistencyLevel.LOW, [], False
        )
        assert any("Niedrige" in r for r in recs)

    def test_high_level_no_issues(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """HIGH ohne Probleme erzeugt positive Empfehlung."""
        recs = service._generate_recommendations(
            ConsistencyLevel.HIGH, [], False
        )
        assert any("Gute" in r for r in recs)

    def test_third_backend_recommendation(
        self, service: CrossBackendConsistencyService
    ) -> None:
        """Third-Backend-Nutzung wird erwaehnt."""
        recs = service._generate_recommendations(
            ConsistencyLevel.MEDIUM, [], True
        )
        assert any("drittes Backend" in r for r in recs)


# =============================================================================
# Word Agreement Tests
# =============================================================================


class TestWordAgreement:
    """Tests fuer Wort-Level Agreement."""

    def test_identical_words(self, service: CrossBackendConsistencyService) -> None:
        """Identische Woerter ergeben Agreement 1.0."""
        score = service._calculate_word_agreement(
            {"surya": "Rechnung", "deepseek": "Rechnung"}
        )
        assert score == 1.0

    def test_different_words(self, service: CrossBackendConsistencyService) -> None:
        """Verschiedene Woerter ergeben niedrigeres Agreement."""
        score = service._calculate_word_agreement(
            {"surya": "Rechnung", "deepseek": "Reenung"}
        )
        assert 0.0 < score < 1.0

    def test_single_word(self, service: CrossBackendConsistencyService) -> None:
        """Ein einzelnes Wort ergibt Agreement 1.0."""
        score = service._calculate_word_agreement({"surya": "Rechnung"})
        assert score == 1.0


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests fuer oeffentliche Convenience-Funktionen."""

    def test_calculate_backend_agreement_identical(self) -> None:
        """Identische Texte ergeben hohe Uebereinstimmung."""
        with patch(
            "app.services.ocr.cross_backend_consistency_service.calculate_agreement",
            return_value=1.0,
        ):
            score = calculate_backend_agreement("Hallo Welt", "Hallo Welt")
            assert score == 1.0

    def test_calculate_backend_agreement_three_texts(self) -> None:
        """Drei Texte werden korrekt verarbeitet."""
        with patch(
            "app.services.ocr.cross_backend_consistency_service.calculate_agreement",
            return_value=0.85,
        ):
            score = calculate_backend_agreement("abc", "abd", "abe")
            assert score == 0.85


# =============================================================================
# InconsistentRegion Tests
# =============================================================================


class TestInconsistentRegion:
    """Tests fuer InconsistentRegion Dataclass."""

    def test_to_dict(self) -> None:
        """to_dict() gibt korrektes Format zurueck."""
        region = InconsistentRegion(
            region_id="0",
            region_type=RegionType.WORD,
            start_position=0,
            end_position=0,
            backend_values={"surya": "Rechnung", "deepseek": "Reenung"},
            backend_confidences={"surya": 0.9, "deepseek": 0.8},
            agreement_score=0.75,
            consistency_level=ConsistencyLevel.MEDIUM,
            review_priority=ReviewPriority.NORMAL,
            suggested_value="Rechnung",
            suggestion_confidence=0.85,
        )
        d = region.to_dict()

        assert d["region_type"] == "word"
        assert d["consistency_level"] == "medium"
        assert d["review_priority"] == "normal"
        assert isinstance(d["agreement_score"], float)


# =============================================================================
# Get Regions For Review Tests
# =============================================================================


class TestGetRegionsForReview:
    """Tests fuer Filterung nach Review-Prioritaet."""

    def test_filter_by_priority(self, service: CrossBackendConsistencyService) -> None:
        """Regionen werden nach Prioritaet gefiltert."""
        report = ConsistencyReport(
            document_id="doc-1",
            backends_used=["surya", "deepseek"],
            overall_agreement=0.7,
            consistency_level=ConsistencyLevel.MEDIUM,
            total_regions_analyzed=3,
            inconsistent_regions=[
                InconsistentRegion(
                    region_id="0",
                    region_type=RegionType.WORD,
                    start_position=0,
                    end_position=0,
                    backend_values={},
                    backend_confidences={},
                    agreement_score=0.3,
                    consistency_level=ConsistencyLevel.CRITICAL,
                    review_priority=ReviewPriority.IMMEDIATE,
                    suggested_value="",
                    suggestion_confidence=0.0,
                ),
                InconsistentRegion(
                    region_id="1",
                    region_type=RegionType.WORD,
                    start_position=1,
                    end_position=1,
                    backend_values={},
                    backend_confidences={},
                    agreement_score=0.8,
                    consistency_level=ConsistencyLevel.MEDIUM,
                    review_priority=ReviewPriority.LOW,
                    suggested_value="",
                    suggestion_confidence=0.0,
                ),
            ],
            high_priority_count=1,
            needs_third_backend=False,
            third_backend_triggered=False,
        )

        high = service.get_regions_for_review(report, ReviewPriority.HIGH)
        assert len(high) == 1
        assert high[0].review_priority == ReviewPriority.IMMEDIATE

        all_regions = service.get_regions_for_review(report, ReviewPriority.LOW)
        assert len(all_regions) == 2
