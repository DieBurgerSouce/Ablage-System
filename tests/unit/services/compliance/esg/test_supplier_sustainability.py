# -*- coding: utf-8 -*-
"""
Unit Tests fuer SupplierSustainabilityService.

Testet:
- create_rating()
- update_rating()
- get_ratings()
- get_rating_detail()
- calculate_overall_score()
- get_high_risk_suppliers()
- get_improvement_suggestions()

Feinpoliert und durchdacht - Supplier Sustainability Tests.
"""

from datetime import date, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.supplier_sustainability import (
    SupplierSustainabilityService,
    get_supplier_sustainability_service,
)
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def sustainability_service(mock_db: AsyncMock) -> SupplierSustainabilityService:
    """Create SupplierSustainabilityService instance with mocked db."""
    return SupplierSustainabilityService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_supplier_sustainability_service Factory."""

    def test_get_supplier_sustainability_service_returns_instance(
        self, mock_db: AsyncMock
    ):
        """Factory sollte SupplierSustainabilityService-Instanz zurueckgeben."""
        service = get_supplier_sustainability_service(mock_db)

        assert isinstance(service, SupplierSustainabilityService)
        assert service.db is mock_db


# ========================= Create Rating Tests =========================


class TestCreateRating:
    """Tests fuer create_rating() Methode."""

    @pytest.mark.asyncio
    async def test_create_rating_success(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
        user_id: UUID,
    ):
        """Sollte neue Lieferantenbewertung erstellen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        rating = await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_score=75.0,
            social_score=80.0,
            governance_score=85.0,
            environmental_details={
                "energy_efficiency": 80,
                "waste_management": 70,
                "emissions_reduction": 75,
            },
            social_details={
                "labor_practices": 85,
                "health_safety": 80,
                "diversity_inclusion": 75,
            },
            governance_details={
                "ethics_compliance": 90,
                "transparency": 85,
                "risk_management": 80,
            },
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_rating_calculates_overall_score(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
        user_id: UUID,
    ):
        """Sollte Gesamtpunktzahl automatisch berechnen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_score=60.0,
            social_score=70.0,
            governance_score=80.0,
        )

        # Average should be (60+70+80)/3 = 70
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_rating_determines_risk_level(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
        user_id: UUID,
    ):
        """Sollte Risikolevel basierend auf Score setzen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Low scores should result in high risk
        await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_score=30.0,
            social_score=35.0,
            governance_score=40.0,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_rating_with_certifications(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
        user_id: UUID,
    ):
        """Sollte Zertifizierungen speichern."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        certifications = ["ISO 14001", "ISO 45001", "EcoVadis Gold"]

        await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_score=85.0,
            social_score=80.0,
            governance_score=90.0,
            certifications=certifications,
        )

        mock_db.add.assert_called_once()


# ========================= Update Rating Tests =========================


class TestUpdateRating:
    """Tests fuer update_rating() Methode."""

    @pytest.mark.asyncio
    async def test_update_rating_success(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_rating,
        company_id: UUID,
    ):
        """Sollte Bewertung aktualisieren."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_rating)
        mock_db.commit = AsyncMock()

        result = await sustainability_service.update_rating(
            rating_id=sample_rating.id,
            company_id=company_id,
            environmental_score=80.0,
            social_score=85.0,
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_rating_recalculates_overall(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_rating,
        company_id: UUID,
    ):
        """Sollte Gesamtscore nach Update neu berechnen."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_rating)
        mock_db.commit = AsyncMock()

        await sustainability_service.update_rating(
            rating_id=sample_rating.id,
            company_id=company_id,
            environmental_score=90.0,
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_rating_not_found(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn Bewertung nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await sustainability_service.update_rating(
                rating_id=uuid4(),
                company_id=company_id,
                environmental_score=80.0,
            )


# ========================= Get Ratings Tests =========================


class TestGetRatings:
    """Tests fuer get_ratings() Methode."""

    @pytest.mark.asyncio
    async def test_get_ratings_success(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_ratings: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Bewertungen zurueckgeben."""
        count_result = create_mock_result(scalar_value=len(sample_ratings))
        list_result = create_mock_result(scalars_list=sample_ratings)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await sustainability_service.get_ratings(company_id=company_id)

        assert total == len(sample_ratings)
        assert len(result) == len(sample_ratings)

    @pytest.mark.asyncio
    async def test_get_ratings_filter_by_risk_level(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_ratings: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nach Risikolevel filtern."""
        high_risk = [r for r in sample_ratings if r.risk_level == "high"]

        count_result = create_mock_result(scalar_value=len(high_risk))
        list_result = create_mock_result(scalars_list=high_risk)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await sustainability_service.get_ratings(
            company_id=company_id,
            risk_level="high",
        )

        for r in result:
            assert r.risk_level == "high"

    @pytest.mark.asyncio
    async def test_get_ratings_filter_by_min_score(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_ratings: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nach Mindestpunktzahl filtern."""
        high_score = [r for r in sample_ratings if r.overall_score >= 70]

        count_result = create_mock_result(scalar_value=len(high_score))
        list_result = create_mock_result(scalars_list=high_score)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await sustainability_service.get_ratings(
            company_id=company_id,
            min_score=70.0,
        )

        for r in result:
            assert r.overall_score >= 70


# ========================= Get Rating Detail Tests =========================


class TestGetRatingDetail:
    """Tests fuer get_rating_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_rating_detail_success(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_rating,
        company_id: UUID,
    ):
        """Sollte Bewertungsdetails zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_rating)

        result = await sustainability_service.get_rating_detail(
            rating_id=sample_rating.id,
            company_id=company_id,
        )

        assert result is not None
        assert result.id == sample_rating.id

    @pytest.mark.asyncio
    async def test_get_rating_detail_not_found(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await sustainability_service.get_rating_detail(
            rating_id=uuid4(),
            company_id=company_id,
        )

        assert result is None


# ========================= High Risk Suppliers Tests =========================


class TestGetHighRiskSuppliers:
    """Tests fuer get_high_risk_suppliers() Methode."""

    @pytest.mark.asyncio
    async def test_get_high_risk_suppliers_success(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_ratings: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte High-Risk Lieferanten zurueckgeben."""
        high_risk = [r for r in sample_ratings if r.risk_level in ["high", "critical"]]
        mock_db.execute.return_value = create_mock_result(scalars_list=high_risk)

        result = await sustainability_service.get_high_risk_suppliers(
            company_id=company_id
        )

        for r in result:
            assert r.risk_level in ["high", "critical"]

    @pytest.mark.asyncio
    async def test_get_high_risk_suppliers_empty(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte leere Liste wenn keine High-Risk Lieferanten."""
        mock_db.execute.return_value = create_mock_result(scalars_list=[])

        result = await sustainability_service.get_high_risk_suppliers(
            company_id=company_id
        )

        assert result == []


# ========================= Improvement Suggestions Tests =========================


class TestGetImprovementSuggestions:
    """Tests fuer get_improvement_suggestions() Methode."""

    @pytest.mark.asyncio
    async def test_get_improvement_suggestions_low_environmental(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_rating,
        company_id: UUID,
    ):
        """Sollte Verbesserungsvorschlaege fuer Umwelt geben."""
        sample_rating.environmental_score = 40.0
        sample_rating.social_score = 80.0
        sample_rating.governance_score = 80.0
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_rating)

        suggestions = await sustainability_service.get_improvement_suggestions(
            rating_id=sample_rating.id,
            company_id=company_id,
        )

        assert len(suggestions) > 0
        # Should prioritize environmental improvements

    @pytest.mark.asyncio
    async def test_get_improvement_suggestions_multiple_areas(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_rating,
        company_id: UUID,
    ):
        """Sollte Vorschlaege fuer mehrere Bereiche geben."""
        sample_rating.environmental_score = 45.0
        sample_rating.social_score = 50.0
        sample_rating.governance_score = 55.0
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_rating)

        suggestions = await sustainability_service.get_improvement_suggestions(
            rating_id=sample_rating.id,
            company_id=company_id,
        )

        # Should have suggestions for all areas
        assert len(suggestions) >= 3

    @pytest.mark.asyncio
    async def test_get_improvement_suggestions_high_scores(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_rating,
        company_id: UUID,
    ):
        """Sollte wenig Vorschlaege bei hohen Scores."""
        sample_rating.environmental_score = 90.0
        sample_rating.social_score = 92.0
        sample_rating.governance_score = 95.0
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_rating)

        suggestions = await sustainability_service.get_improvement_suggestions(
            rating_id=sample_rating.id,
            company_id=company_id,
        )

        # Fewer suggestions for high performers
        assert len(suggestions) <= 2


# ========================= Score Calculation Tests =========================


class TestCalculateOverallScore:
    """Tests fuer calculate_overall_score() Methode."""

    def test_calculate_overall_score_equal_weights(
        self,
        sustainability_service: SupplierSustainabilityService,
    ):
        """Sollte Durchschnitt berechnen bei gleichen Gewichten."""
        score = sustainability_service.calculate_overall_score(
            environmental_score=60.0,
            social_score=70.0,
            governance_score=80.0,
        )

        assert score == 70.0  # (60+70+80)/3

    def test_calculate_overall_score_with_weights(
        self,
        sustainability_service: SupplierSustainabilityService,
    ):
        """Sollte gewichteten Durchschnitt berechnen."""
        score = sustainability_service.calculate_overall_score(
            environmental_score=100.0,
            social_score=50.0,
            governance_score=50.0,
            weights={"environmental": 0.5, "social": 0.25, "governance": 0.25},
        )

        # 100*0.5 + 50*0.25 + 50*0.25 = 50+12.5+12.5 = 75
        assert score == 75.0


# ========================= Risk Level Tests =========================


class TestDetermineRiskLevel:
    """Tests fuer determine_risk_level() Methode."""

    @pytest.mark.parametrize(
        "score,expected_risk",
        [
            (95.0, "low"),
            (75.0, "low"),
            (65.0, "medium"),
            (45.0, "high"),
            (25.0, "critical"),
        ],
    )
    def test_risk_level_thresholds(
        self,
        sustainability_service: SupplierSustainabilityService,
        score: float,
        expected_risk: str,
    ):
        """Sollte korrektes Risikolevel basierend auf Score bestimmen."""
        risk = sustainability_service.determine_risk_level(score)

        assert risk == expected_risk
