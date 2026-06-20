# -*- coding: utf-8 -*-
"""
Unit Tests fuer SupplierSustainabilityService.

Testet gegen den ECHTEN Vertrag von
app.services.compliance.esg.supplier_sustainability:
- get_rating_criteria()
- calculate_scores()  (gewichteter ESG-Score aus Detail-Dicts)
- determine_risk_level()
- create_rating()
- get_ratings()
- get_latest_rating()
- get_risk_summary()

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
    RATING_CRITERIA,
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


# ========================= Rating Criteria Tests =========================


class TestRatingCriteria:
    """Tests fuer get_rating_criteria()."""

    def test_get_rating_criteria_structure(
        self, sustainability_service: SupplierSustainabilityService
    ):
        """Sollte E/S/G-Kriterien mit Gewichtungen zurueckgeben."""
        criteria = sustainability_service.get_rating_criteria()

        assert set(criteria.keys()) == {"environmental", "social", "governance"}
        # Gewichtungen der Hauptkategorien summieren sich auf 1.0
        total_weight = sum(c["weight"] for c in criteria.values())
        assert round(total_weight, 4) == 1.0
        # Jede Kategorie hat Unterkriterien
        for cat in criteria.values():
            assert "criteria" in cat
            assert len(cat["criteria"]) > 0


# ========================= Score Calculation Tests =========================


class TestCalculateScores:
    """Tests fuer calculate_scores() Methode."""

    def test_calculate_scores_full_details(
        self, sustainability_service: SupplierSustainabilityService
    ):
        """Sollte gewichtete Einzel- und Gesamtscores berechnen."""
        scores = sustainability_service.calculate_scores(
            environmental_details={
                "co2_emissions": 80,
                "energy_efficiency": 80,
                "waste_management": 80,
                "water_usage": 80,
                "certifications": 80,
            },
            social_details={
                "labor_standards": 70,
                "health_safety": 70,
                "human_rights": 70,
                "diversity": 70,
                "community": 70,
            },
            governance_details={
                "compliance": 90,
                "transparency": 90,
                "ethics": 90,
                "risk_management": 90,
                "data_protection": 90,
            },
        )

        # Bei gleichen Einzelwerten je Kategorie ist der Kategoriescore = der Wert
        assert scores["environmental_score"] == 80.0
        assert scores["social_score"] == 70.0
        assert scores["governance_score"] == 90.0
        # Gesamt = 80*0.35 + 70*0.35 + 90*0.30 = 28 + 24.5 + 27 = 79.5
        assert scores["overall_score"] == 79.5

    def test_calculate_scores_clamps_to_range(
        self, sustainability_service: SupplierSustainabilityService
    ):
        """Sollte Werte ausserhalb 0-100 begrenzen."""
        scores = sustainability_service.calculate_scores(
            environmental_details={"co2_emissions": 150},  # > 100 -> 100
            social_details={"labor_standards": -20},  # < 0 -> 0
            governance_details={"compliance": 50},
        )

        assert scores["environmental_score"] == 100.0
        assert scores["social_score"] == 0.0
        assert scores["governance_score"] == 50.0

    def test_calculate_scores_empty_details(
        self, sustainability_service: SupplierSustainabilityService
    ):
        """Sollte 0 zurueckgeben wenn keine Kriterien vorliegen."""
        scores = sustainability_service.calculate_scores({}, {}, {})

        assert scores["environmental_score"] == 0
        assert scores["social_score"] == 0
        assert scores["governance_score"] == 0
        assert scores["overall_score"] == 0


# ========================= Risk Level Tests =========================


class TestDetermineRiskLevel:
    """Tests fuer determine_risk_level() Methode (echte Schwellen)."""

    @pytest.mark.parametrize(
        "score,expected_risk",
        [
            (95.0, "low"),
            (80.0, "low"),
            (79.9, "medium"),
            (65.0, "medium"),
            (60.0, "medium"),
            (45.0, "high"),
            (40.0, "high"),
            (39.9, "critical"),
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
        """Sollte neue Lieferantenbewertung erstellen und persistieren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        rating = await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_details={
                "co2_emissions": 80,
                "energy_efficiency": 70,
                "waste_management": 75,
            },
            social_details={
                "labor_standards": 85,
                "health_safety": 80,
            },
            governance_details={
                "compliance": 90,
                "transparency": 85,
            },
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        # Score-Felder wurden gesetzt
        assert rating.overall_score is not None
        assert rating.risk_level is not None

    @pytest.mark.asyncio
    async def test_create_rating_high_scores_low_risk(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
        user_id: UUID,
    ):
        """Hohe Scores sollten zu Risikolevel 'low' fuehren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        rating = await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_details={"co2_emissions": 90, "energy_efficiency": 90},
            social_details={"labor_standards": 90, "health_safety": 90},
            governance_details={"compliance": 90, "transparency": 90},
        )

        assert rating.risk_level == "low"
        assert rating.overall_score >= 80

    @pytest.mark.asyncio
    async def test_create_rating_low_scores_set_risk_factors(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
        user_id: UUID,
    ):
        """Niedrige Einzelscores sollten Risikofaktoren erzeugen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        rating = await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_details={"co2_emissions": 30, "energy_efficiency": 30},
            social_details={"labor_standards": 35, "health_safety": 35},
            governance_details={"compliance": 40, "transparency": 40},
        )

        assert rating.risk_level in ("high", "critical")
        # < 50 in allen drei Kategorien -> drei Risikofaktoren
        assert len(rating.risk_factors) == 3

    @pytest.mark.asyncio
    async def test_create_rating_with_certifications(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
        user_id: UUID,
    ):
        """Sollte Zertifizierungen am Rating speichern."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        certifications = ["ISO 14001", "ISO 45001", "EcoVadis Gold"]

        rating = await sustainability_service.create_rating(
            company_id=company_id,
            entity_id=entity_id,
            assessed_by_id=user_id,
            environmental_details={"co2_emissions": 85},
            social_details={"labor_standards": 80},
            governance_details={"compliance": 90},
            certifications=certifications,
        )

        assert rating.certifications == certifications
        mock_db.add.assert_called_once()


# ========================= Get Ratings Tests =========================


class TestGetRatings:
    """Tests fuer get_ratings() Methode (gibt Dicts + total zurueck)."""

    @pytest.mark.asyncio
    async def test_get_ratings_success(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_ratings: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Bewertungen als Dict-Liste mit Gesamtanzahl zurueckgeben."""
        # Den Sample-Ratings die vom Service serialisierten Felder geben
        for r in sample_ratings:
            r.rating_date = date.today()
            r.valid_until = None
            r.risk_factors = []
            r.certifications = []
            r.assessment_method = "self_assessment"

        count_result = create_mock_result(scalar_value=len(sample_ratings))
        list_result = create_mock_result(scalars_list=sample_ratings)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await sustainability_service.get_ratings(company_id=company_id)

        assert total == len(sample_ratings)
        assert len(result) == len(sample_ratings)
        # Service liefert Dicts (keine ORM-Objekte)
        assert all(isinstance(r, dict) for r in result)
        assert "overall_score" in result[0]
        assert "risk_level" in result[0]

    @pytest.mark.asyncio
    async def test_get_ratings_filter_by_risk_level(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_ratings: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte risk_level-Filter an die Query weiterreichen."""
        high_risk = [r for r in sample_ratings if r.risk_level == "high"]
        for r in high_risk:
            r.rating_date = date.today()
            r.valid_until = None
            r.risk_factors = []
            r.certifications = []
            r.assessment_method = "self_assessment"

        count_result = create_mock_result(scalar_value=len(high_risk))
        list_result = create_mock_result(scalars_list=high_risk)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await sustainability_service.get_ratings(
            company_id=company_id,
            risk_level="high",
        )

        assert total == len(high_risk)
        for r in result:
            assert r["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_get_ratings_empty(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte leere Liste und total=0 zurueckgeben."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await sustainability_service.get_ratings(company_id=company_id)

        assert result == []
        assert total == 0


# ========================= Get Latest Rating Tests =========================


class TestGetLatestRating:
    """Tests fuer get_latest_rating() Methode."""

    @pytest.mark.asyncio
    async def test_get_latest_rating_success(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_rating,
        company_id: UUID,
        entity_id: UUID,
    ):
        """Sollte neueste Bewertung als Dict zurueckgeben."""
        sample_rating.rating_date = date.today()
        sample_rating.valid_until = None
        sample_rating.risk_factors = []
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_rating)

        result = await sustainability_service.get_latest_rating(
            company_id=company_id,
            entity_id=entity_id,
        )

        assert result is not None
        assert isinstance(result, dict)
        assert result["overall_score"] == sample_rating.overall_score

    @pytest.mark.asyncio
    async def test_get_latest_rating_not_found(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
        entity_id: UUID,
    ):
        """Sollte None zurueckgeben wenn keine Bewertung existiert."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await sustainability_service.get_latest_rating(
            company_id=company_id,
            entity_id=entity_id,
        )

        assert result is None


# ========================= Risk Summary Tests =========================


class TestGetRiskSummary:
    """Tests fuer get_risk_summary() Methode."""

    @pytest.mark.asyncio
    async def test_get_risk_summary_aggregates_by_risk(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        sample_ratings: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Lieferanten nach Risikolevel aggregieren."""
        mock_db.execute.return_value = create_mock_result(scalars_list=sample_ratings)

        summary = await sustainability_service.get_risk_summary(company_id=company_id)

        assert summary["total_suppliers"] == len(sample_ratings)
        # Sample enthaelt low/medium/high/critical -> high_risk_count = high + critical
        assert summary["high_risk_count"] == 2
        assert summary["by_risk_level"]["high"] == 1
        assert summary["by_risk_level"]["critical"] == 1
        assert summary["average_score"] is not None

    @pytest.mark.asyncio
    async def test_get_risk_summary_empty(
        self,
        sustainability_service: SupplierSustainabilityService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte sinnvolle Defaults bei keinen Lieferanten liefern."""
        mock_db.execute.return_value = create_mock_result(scalars_list=[])

        summary = await sustainability_service.get_risk_summary(company_id=company_id)

        assert summary["total_suppliers"] == 0
        assert summary["average_score"] is None
        assert summary["high_risk_count"] == 0
