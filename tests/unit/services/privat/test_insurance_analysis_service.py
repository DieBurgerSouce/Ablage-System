"""
Unit Tests fuer InsuranceAnalysisService.

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Methoden-Existenz
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class TestInsuranceAnalysisService:
    """Tests fuer InsuranceAnalysisService."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceAnalysisService,
        )

        service = InsuranceAnalysisService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_dataclass_imports(self) -> None:
        """Testet dass alle Datenklassen importierbar sind."""
        from app.services.privat.insurance_analysis_service import (
            CancellationDeadlineResult,
            CoverageGap,
            CoverageGapAnalysisResult,
            InsuranceAnalysisService,
            InsuranceKPIs,
            InsurancePremiumSummary,
        )

        assert InsuranceAnalysisService is not None
        assert CoverageGap is not None
        assert CoverageGapAnalysisResult is not None
        assert CancellationDeadlineResult is not None
        assert InsurancePremiumSummary is not None
        assert InsuranceKPIs is not None


class TestCoverageGapDataClass:
    """Tests fuer CoverageGap Datenstruktur."""

    @pytest.mark.asyncio
    async def test_coverage_gap_dataclass(self) -> None:
        """Testet CoverageGap Datenstruktur."""
        from app.services.privat.insurance_analysis_service import (
            CoverageGap,
        )

        gap = CoverageGap(
            insurance_type="haftpflicht",
            insurance_name="Privathaftpflicht",
            recommended_coverage=Decimal("10000000"),
            current_coverage=Decimal("5000000"),
            gap_amount=Decimal("5000000"),
            gap_percentage=Decimal("50.0"),
            severity="high",
            severity_label="Hoch",
            is_essential=True,
        )

        assert gap.insurance_type == "haftpflicht"
        assert gap.insurance_name == "Privathaftpflicht"
        assert gap.recommended_coverage == Decimal("10000000")
        assert gap.current_coverage == Decimal("5000000")
        assert gap.gap_amount == Decimal("5000000")
        assert gap.gap_percentage == Decimal("50.0")
        assert gap.severity == "high"
        assert gap.severity_label == "Hoch"
        assert gap.is_essential is True

    @pytest.mark.asyncio
    async def test_coverage_gap_analysis_result_dataclass(self) -> None:
        """Testet CoverageGapAnalysisResult Datenstruktur."""
        from app.services.privat.insurance_analysis_service import (
            CoverageGap,
            CoverageGapAnalysisResult,
        )

        gap = CoverageGap(
            insurance_type="haftpflicht",
            insurance_name="Privathaftpflicht",
            recommended_coverage=Decimal("10000000"),
            current_coverage=Decimal("5000000"),
            gap_amount=Decimal("5000000"),
            gap_percentage=Decimal("50.0"),
            severity="high",
            severity_label="Hoch",
            is_essential=True,
        )

        result = CoverageGapAnalysisResult(
            space_id=uuid4(),
            gaps=[gap],
            total_gap_count=1,
            critical_gaps=0,
            high_gaps=1,
            coverage_score=Decimal("75.0"),
            missing_essential=["rechtsschutz"],
        )

        assert len(result.gaps) == 1
        assert result.total_gap_count == 1
        assert result.high_gaps == 1
        assert result.coverage_score == Decimal("75.0")
        assert "rechtsschutz" in result.missing_essential


class TestCancellationDeadlineDataClass:
    """Tests fuer CancellationDeadlineResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_cancellation_deadline_result_dataclass(self) -> None:
        """Testet CancellationDeadlineResult Datenstruktur."""
        from app.services.privat.insurance_analysis_service import (
            CancellationDeadlineResult,
        )

        deadline = CancellationDeadlineResult(
            insurance_id=uuid4(),
            insurance_name="Allianz Haftpflicht",
            contract_end=date.today() + timedelta(days=120),
            cancellation_period_months=3,
            cancellation_deadline=date.today() + timedelta(days=30),
            days_until_deadline=30,
            is_urgent=False,
            is_approaching=True,
        )

        assert deadline.insurance_name == "Allianz Haftpflicht"
        assert deadline.cancellation_period_months == 3
        assert deadline.days_until_deadline == 30
        assert deadline.is_urgent is False
        assert deadline.is_approaching is True


class TestInsurancePremiumSummaryDataClass:
    """Tests fuer InsurancePremiumSummary Datenstruktur."""

    @pytest.mark.asyncio
    async def test_insurance_premium_summary_dataclass(self) -> None:
        """Testet InsurancePremiumSummary Datenstruktur."""
        from app.services.privat.insurance_analysis_service import (
            InsurancePremiumSummary,
        )

        summary = InsurancePremiumSummary(
            space_id=uuid4(),
            annual_total=Decimal("1585.00"),
            monthly_equivalent=Decimal("132.08"),
            by_type={"haftpflicht": Decimal("85.00"), "hausrat": Decimal("150.00")},
            insurance_count=5,
        )

        assert summary.annual_total == Decimal("1585.00")
        assert summary.monthly_equivalent == Decimal("132.08")
        assert summary.insurance_count == 5
        assert "haftpflicht" in summary.by_type


class TestInsuranceKPIsDataClass:
    """Tests fuer InsuranceKPIs Datenstruktur."""

    @pytest.mark.asyncio
    async def test_insurance_kpis_dataclass(self) -> None:
        """Testet InsuranceKPIs Datenstruktur."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceKPIs,
        )

        kpis = InsuranceKPIs(
            space_id=uuid4(),
            coverage_analysis=None,
            cancellation_deadlines=[],
            premium_summary=None,
        )

        assert kpis.space_id is not None
        assert kpis.coverage_analysis is None
        assert kpis.cancellation_deadlines == []
        assert kpis.premium_summary is None
        assert kpis.calculated_at is not None


class TestServiceMethodsExist:
    """Tests dass alle wichtigen Service-Methoden existieren."""

    @pytest.mark.asyncio
    async def test_service_has_analyze_coverage_gaps_method(self) -> None:
        """Testet dass Service analyze_coverage_gaps Methode hat."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceAnalysisService,
        )

        service = InsuranceAnalysisService()

        assert hasattr(service, "analyze_coverage_gaps")
        assert callable(getattr(service, "analyze_coverage_gaps"))

    @pytest.mark.asyncio
    async def test_service_has_calculate_cancellation_deadlines_method(self) -> None:
        """Testet dass Service calculate_cancellation_deadlines Methode hat."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceAnalysisService,
        )

        service = InsuranceAnalysisService()

        assert hasattr(service, "calculate_cancellation_deadlines")
        assert callable(getattr(service, "calculate_cancellation_deadlines"))

    @pytest.mark.asyncio
    async def test_service_has_calculate_premium_summary_method(self) -> None:
        """Testet dass Service calculate_premium_summary Methode hat."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceAnalysisService,
        )

        service = InsuranceAnalysisService()

        assert hasattr(service, "calculate_premium_summary")
        assert callable(getattr(service, "calculate_premium_summary"))

    @pytest.mark.asyncio
    async def test_service_has_analyze_all_method(self) -> None:
        """Testet dass Service analyze_all Methode hat."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceAnalysisService,
        )

        service = InsuranceAnalysisService()

        assert hasattr(service, "analyze_all")
        assert callable(getattr(service, "analyze_all"))

    @pytest.mark.asyncio
    async def test_service_has_analyze_single_insurance_method(self) -> None:
        """Testet dass Service analyze_single_insurance Methode hat."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceAnalysisService,
        )

        service = InsuranceAnalysisService()

        assert hasattr(service, "analyze_single_insurance")
        assert callable(getattr(service, "analyze_single_insurance"))


class TestGetServiceFunction:
    """Tests fuer get_insurance_analysis_service Factory."""

    @pytest.mark.asyncio
    async def test_get_service_function_exists(self) -> None:
        """Testet dass get_insurance_analysis_service existiert."""
        from app.services.privat.insurance_analysis_service import (
            get_insurance_analysis_service,
        )

        assert get_insurance_analysis_service is not None
        assert callable(get_insurance_analysis_service)

    @pytest.mark.asyncio
    async def test_get_service_returns_instance(self) -> None:
        """Testet dass get_insurance_analysis_service eine Instanz zurueckgibt."""
        from app.services.privat.insurance_analysis_service import (
            InsuranceAnalysisService,
            get_insurance_analysis_service,
        )

        service = get_insurance_analysis_service()

        assert isinstance(service, InsuranceAnalysisService)
