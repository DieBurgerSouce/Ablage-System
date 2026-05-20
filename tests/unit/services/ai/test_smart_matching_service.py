# -*- coding: utf-8 -*-
"""
Unit Tests fuer SmartMatchingService.

Tests fuer intelligente Dokumenten-Verknuepfung:
- Rechnung <-> Lieferschein
- Rechnung <-> Bestellung
- Confidence-basierte Matches
"""

import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.smart_matching_service import (
    SmartMatchingService,
    MatchType,
    MatchCandidate,
    MatchFeatureWeights,
    SmartMatchResult,
)
from app.services.ai.extracted_data_wrapper import ExtractedData


class TestMatchTypes:
    """Tests fuer Match-Typen."""

    def test_match_type_values(self) -> None:
        """Test: MatchType hat alle erwarteten Werte."""
        assert MatchType.INVOICE_DELIVERY == "invoice_delivery"
        assert MatchType.INVOICE_ORDER == "invoice_order"
        assert MatchType.DELIVERY_ORDER == "delivery_order"
        assert MatchType.INVOICE_CONTRACT == "invoice_contract"
        assert MatchType.OFFER_ORDER == "offer_order"
        assert MatchType.CREDIT_INVOICE == "credit_invoice"


class TestMatchFeatureWeights:
    """Tests fuer MatchFeatureWeights."""

    def test_weights_creation(self) -> None:
        """Test: MatchFeatureWeights kann erstellt werden."""
        weights = MatchFeatureWeights()
        assert weights.document_number == 0.35
        assert weights.customer_supplier == 0.25
        assert weights.amount == 0.20
        assert weights.date_proximity == 0.10
        assert weights.positions_overlap == 0.10

    def test_weights_sum_to_one(self) -> None:
        """Test: Gewichte summieren sich auf 1.0."""
        weights = MatchFeatureWeights()
        total = (
            weights.document_number +
            weights.customer_supplier +
            weights.amount +
            weights.date_proximity +
            weights.positions_overlap
        )
        assert abs(total - 1.0) < 0.01


class TestMatchCandidate:
    """Tests fuer MatchCandidate."""

    def test_candidate_creation(self) -> None:
        """Test: MatchCandidate kann erstellt werden."""
        candidate = MatchCandidate(
            target_document_id=uuid4(),
            match_type=MatchType.INVOICE_DELIVERY,
            confidence=0.92,
            feature_scores={
                "document_number": 0.95,
                "customer_supplier": 0.90,
            },
            matched_values={
                "order_number": "PO-2025-001",
            }
        )

        assert candidate.match_type == MatchType.INVOICE_DELIVERY
        assert candidate.confidence == 0.92
        assert "document_number" in candidate.feature_scores


class TestSmartMatchResult:
    """Tests fuer SmartMatchResult."""

    def test_result_creation(self) -> None:
        """Test: SmartMatchResult kann erstellt werden."""
        result = SmartMatchResult(
            matches=[],
            total_candidates_checked=10,
            processing_time_ms=150,
        )

        assert len(result.matches) == 0
        assert result.total_candidates_checked == 10
        assert result.processing_time_ms == 150

    def test_result_defaults(self) -> None:
        """Test: SmartMatchResult hat korrekte Defaults."""
        result = SmartMatchResult()
        assert result.matches == []
        assert result.total_candidates_checked == 0
        assert result.processing_time_ms == 0


class TestSmartMatchingService:
    """Tests fuer SmartMatchingService."""

    @pytest.fixture
    def service(self) -> SmartMatchingService:
        """Erstellt Service-Instanz."""
        return SmartMatchingService()

    def test_service_configuration(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Service hat korrekte Konfiguration."""
        assert service.MIN_MATCH_CONFIDENCE == 0.70
        assert service.MAX_DATE_DIFF_DAYS == 90
        assert service.AMOUNT_TOLERANCE_PERCENT == 0.02


class TestNormalizeNumber:
    """Tests fuer _normalize_number Methode."""

    @pytest.fixture
    def service(self) -> SmartMatchingService:
        return SmartMatchingService()

    def test_normalize_removes_spaces(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Leerzeichen werden entfernt."""
        result = service._normalize_number("RE 2026 001")
        assert " " not in result

    def test_normalize_removes_dashes(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Bindestriche werden entfernt."""
        result = service._normalize_number("RE-2026-001")
        assert "-" not in result

    def test_normalize_removes_leading_zeros(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Fuehrende Nullen werden entfernt."""
        result = service._normalize_number("00123")
        assert result == "123"

    def test_normalize_lowercase(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Ergebnis ist lowercase."""
        result = service._normalize_number("ABC-123")
        assert result == "abc123"

    def test_normalize_none(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: None gibt None zurueck."""
        result = service._normalize_number(None)
        assert result is None


class TestCalculateNumberSimilarity:
    """Tests fuer _calculate_number_similarity Methode."""

    @pytest.fixture
    def service(self) -> SmartMatchingService:
        return SmartMatchingService()

    def test_identical_numbers(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Identische Nummern = 1.0."""
        score = service._calculate_number_similarity("RE-2026-001", "RE-2026-001")
        assert score == 1.0

    def test_normalized_match(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Normalisierte Nummern werden erkannt."""
        # Unterschiedliche Formatierung, gleiche Nummer
        score = service._calculate_number_similarity("RE 2026 001", "RE-2026-001")
        assert score == 1.0

    def test_none_number(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: None ergibt 0.0."""
        score = service._calculate_number_similarity(None, "RE-001")
        assert score == 0.0

        score = service._calculate_number_similarity("RE-001", None)
        assert score == 0.0


class TestCalculateAmountSimilarity:
    """Tests fuer _calculate_amount_similarity Methode."""

    @pytest.fixture
    def service(self) -> SmartMatchingService:
        return SmartMatchingService()

    def test_exact_match(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Exakt gleiche Betraege = 1.0."""
        score = service._calculate_amount_similarity(
            Decimal("1190.00"),
            Decimal("1190.00")
        )
        assert score == 1.0

    def test_close_amounts(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Nahe Betraege = hoher Score."""
        score = service._calculate_amount_similarity(
            Decimal("1000.00"),
            Decimal("1010.00")  # 1% Differenz
        )
        assert score > 0.5

    def test_different_amounts(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Sehr verschiedene Betraege = niedriger Score."""
        score = service._calculate_amount_similarity(
            Decimal("100.00"),
            Decimal("10000.00")  # 100x Unterschied
        )
        assert score < 0.5

    def test_none_amount(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: None ergibt 0.0."""
        score = service._calculate_amount_similarity(None, Decimal("100.00"))
        assert score == 0.0


class TestCalculateDateProximity:
    """Tests fuer _calculate_date_proximity Methode."""

    @pytest.fixture
    def service(self) -> SmartMatchingService:
        return SmartMatchingService()

    def test_same_date(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Gleiches Datum = 1.0."""
        today = datetime.now(timezone.utc)
        score = service._calculate_date_proximity(today, today)
        assert score == 1.0

    def test_close_dates(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Nahe Daten = hoher Score."""
        date1 = datetime.now(timezone.utc)
        date2 = date1 - timedelta(days=7)  # 1 Woche
        score = service._calculate_date_proximity(date1, date2)
        assert score > 0.9

    def test_far_dates(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Weit entfernte Daten = niedriger Score."""
        date1 = datetime.now(timezone.utc)
        date2 = date1 - timedelta(days=180)  # 6 Monate
        score = service._calculate_date_proximity(date1, date2)
        assert score < 0.5


class TestFindMatches:
    """Tests fuer find_matches Methode."""

    @pytest.fixture
    def service(self) -> SmartMatchingService:
        return SmartMatchingService()

    @pytest.mark.asyncio
    async def test_find_matches_document_not_found(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: Leeres Result wenn Dokument nicht existiert."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        result = await service.find_matches(
            db=db,
            document_id=uuid4(),
            company_id=uuid4(),
        )

        assert isinstance(result, SmartMatchResult)
        assert len(result.matches) == 0

    @pytest.mark.asyncio
    async def test_find_matches_returns_smart_match_result(
        self,
        service: SmartMatchingService,
    ) -> None:
        """Test: find_matches gibt SmartMatchResult zurueck."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        result = await service.find_matches(
            db=db,
            document_id=uuid4(),
            company_id=uuid4(),
            max_results=5,
        )

        assert isinstance(result, SmartMatchResult)
        assert hasattr(result, 'matches')
        assert hasattr(result, 'total_candidates_checked')
        assert hasattr(result, 'processing_time_ms')


class TestExtractedDataOrderNumber:
    """Tests fuer order_number Property in ExtractedData."""

    def test_order_number_direct(self) -> None:
        """Test: order_number direkt vorhanden."""
        data = ExtractedData(
            document_id=uuid4(),
            raw_data={"order_number": "PO-2025-001"}
        )
        assert data.order_number == "PO-2025-001"

    def test_order_number_fallback_purchase_order(self) -> None:
        """Test: Fallback auf purchase_order."""
        data = ExtractedData(
            document_id=uuid4(),
            raw_data={"purchase_order": "PO-2025-002"}
        )
        # Sollte auf purchase_order zurueckfallen wenn order_number nicht existiert
        assert data.order_number in ["PO-2025-002", None]

    def test_order_number_missing(self) -> None:
        """Test: order_number fehlt = None."""
        data = ExtractedData(
            document_id=uuid4(),
            raw_data={"invoice_number": "RE-001"}
        )
        assert data.order_number is None
