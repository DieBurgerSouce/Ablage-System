# -*- coding: utf-8 -*-
"""
Unit Tests fuer ESGReportGenerator.

Testet die ECHTE API von app.services.compliance.esg.report_generator:
- get_report_templates() (staticmethod)
- generate_report()
- get_reports()  -> tuple[list[dict], int]
- get_report_detail()  -> dict | None
- update_report_status()  -> bool

Feinpoliert und durchdacht - ESG Report Generator Tests.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.report_generator import (
    ESGReportGenerator as ESGReportGeneratorService,
    get_esg_report_generator as get_report_generator_service,
    REPORT_TEMPLATES,
)
from app.db.models_esg import ReportStatus
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def report_service(mock_db: AsyncMock) -> ESGReportGeneratorService:
    """Erzeuge ESGReportGenerator-Instanz mit gemockter DB."""
    return ESGReportGeneratorService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_esg_report_generator Factory."""

    def test_get_report_generator_service_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte ESGReportGenerator-Instanz zurueckgeben."""
        service = get_report_generator_service(mock_db)

        assert isinstance(service, ESGReportGeneratorService)
        assert service.db is mock_db


# ========================= Template Tests =========================


class TestReportTemplates:
    """Tests fuer get_report_templates() (statischer Vertrag der Vorlagen)."""

    def test_get_report_templates_returns_known_templates(self):
        """Sollte die definierten Berichtsvorlagen zurueckgeben."""
        templates = ESGReportGeneratorService.get_report_templates()

        assert templates is REPORT_TEMPLATES
        # Die vier dokumentierten Typen muessen existieren
        for report_type in ("annual", "quarterly", "csrd", "dnk"):
            assert report_type in templates, f"Vorlage '{report_type}' fehlt"

    def test_template_structure_has_name_and_sections(self):
        """Jede Vorlage muss 'name' und nicht-leere 'sections' haben."""
        templates = ESGReportGeneratorService.get_report_templates()

        for report_type, template in templates.items():
            assert "name" in template, f"Vorlage '{report_type}' ohne 'name'"
            assert "sections" in template, f"Vorlage '{report_type}' ohne 'sections'"
            assert len(template["sections"]) > 0, f"Vorlage '{report_type}' ohne Sektionen"

    def test_annual_template_contains_carbon_section(self):
        """Die Jahresvorlage muss den CO2-Fussabdruck enthalten."""
        annual = ESGReportGeneratorService.get_report_templates()["annual"]

        assert "carbon_footprint" in annual["sections"]


# ========================= Generate Report Tests =========================


class TestGenerateReport:
    """Tests fuer generate_report() Methode."""

    @pytest.mark.asyncio
    async def test_generate_report_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte neuen Bericht generieren und persistieren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        # Leere Aggregations-Resultate fuer _collect_metrics
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        report = await report_service.generate_report(
            company_id=company_id,
            created_by_id=user_id,
            report_type="annual",
            title="Nachhaltigkeitsbericht 2025",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            reporting_standard="GRI",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        # Der zurueckgegebene Report traegt die uebergebenen Stammdaten
        assert report.company_id == company_id
        assert report.report_type == "annual"
        assert report.title == "Nachhaltigkeitsbericht 2025"
        assert report.reporting_standard == "GRI"
        assert report.created_by_id == user_id
        assert report.fiscal_year == 2025
        assert report.status == ReportStatus.DRAFT

    @pytest.mark.asyncio
    async def test_generate_report_with_csrd_standard(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte CSRD-konformen Bericht generieren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        report = await report_service.generate_report(
            company_id=company_id,
            created_by_id=user_id,
            report_type="csrd",
            title="CSRD Nachhaltigkeitsbericht 2025",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            reporting_standard="CSRD",
        )

        mock_db.add.assert_called_once()
        assert report.report_type == "csrd"
        assert report.reporting_standard == "CSRD"

    @pytest.mark.asyncio
    async def test_generate_report_default_title(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte ohne Titel einen Default-Titel aus Vorlage + Jahr bilden."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        report = await report_service.generate_report(
            company_id=company_id,
            created_by_id=user_id,
            report_type="annual",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        )

        expected = f"{REPORT_TEMPLATES['annual']['name']} 2025"
        assert report.title == expected

    @pytest.mark.asyncio
    async def test_generate_report_unknown_type_raises(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte bei unbekanntem Berichtstyp ValueError werfen."""
        with pytest.raises(ValueError, match="Unbekannter Berichtstyp"):
            await report_service.generate_report(
                company_id=company_id,
                created_by_id=user_id,
                report_type="does_not_exist",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
            )

        # Bei ungueltigem Typ darf nichts persistiert werden
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_report_aggregates_data(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte Daten aus verschiedenen Quellen abfragen (mehrere Queries)."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        await report_service.generate_report(
            company_id=company_id,
            created_by_id=user_id,
            report_type="annual",
            title="Jahresbericht",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        )

        # _collect_metrics fragt Emissionen, Lieferanten, Zertifikate und Ziele ab
        assert mock_db.execute.called
        assert mock_db.execute.await_count >= 4


# ========================= Get Reports Tests =========================


class TestGetReports:
    """Tests fuer get_reports() Methode (Rueckgabe: tuple[list[dict], int])."""

    @pytest.mark.asyncio
    async def test_get_reports_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Berichte als Dict-Liste plus Gesamtanzahl zurueckgeben."""
        # Erster execute() -> count, zweiter -> scalars().all()
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_report]),
        ]

        reports, total = await report_service.get_reports(company_id=company_id)

        assert total == 1
        assert len(reports) == 1
        assert isinstance(reports[0], dict)
        assert reports[0]["id"] == str(sample_report.id)
        assert reports[0]["report_type"] == sample_report.report_type

    @pytest.mark.asyncio
    async def test_get_reports_filter_by_type(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte den report_type-Filter durchreichen (im Ergebnis sichtbar)."""
        sample_report.report_type = "annual"
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_report]),
        ]

        reports, total = await report_service.get_reports(
            company_id=company_id,
            report_type="annual",
        )

        assert total == 1
        for r in reports:
            assert r["report_type"] == "annual"

    @pytest.mark.asyncio
    async def test_get_reports_filter_by_status(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte den status-Filter durchreichen (im Ergebnis sichtbar)."""
        sample_report.status = "published"
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_report]),
        ]

        reports, total = await report_service.get_reports(
            company_id=company_id,
            status="published",
        )

        assert total == 1
        for r in reports:
            assert r["status"] == "published"

    @pytest.mark.asyncio
    async def test_get_reports_empty(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte leere Liste und Total 0 zurueckgeben wenn keine Berichte existieren."""
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=0),
            create_mock_result(scalars_list=[]),
        ]

        reports, total = await report_service.get_reports(company_id=company_id)

        assert total == 0
        assert reports == []


# ========================= Get Report Detail Tests =========================


class TestGetReportDetail:
    """Tests fuer get_report_detail() Methode (Rueckgabe: dict | None)."""

    @pytest.mark.asyncio
    async def test_get_report_detail_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Berichtsdetails als Dict zurueckgeben."""
        # get_report_detail nutzt content_json, daher Attribut setzen
        sample_report.content_json = {"sections": {}}
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        result = await report_service.get_report_detail(
            report_id=sample_report.id,
            company_id=company_id,
        )

        assert result is not None
        assert isinstance(result, dict)
        assert result["id"] == str(sample_report.id)
        assert result["title"] == sample_report.title
        assert result["content"] == {"sections": {}}

    @pytest.mark.asyncio
    async def test_get_report_detail_not_found(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await report_service.get_report_detail(
            report_id=uuid4(),
            company_id=company_id,
        )

        assert result is None


# ========================= Update Report Status Tests =========================


class TestUpdateReportStatus:
    """Tests fuer update_report_status() Methode (Rueckgabe: bool)."""

    @pytest.mark.asyncio
    async def test_update_report_status_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Berichtsstatus auf einen gueltigen Wert aktualisieren."""
        sample_report.status = "draft"
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)
        mock_db.commit = AsyncMock()

        result = await report_service.update_report_status(
            report_id=sample_report.id,
            company_id=company_id,
            new_status=ReportStatus.IN_REVIEW.value,
        )

        assert result is True
        assert sample_report.status == ReportStatus.IN_REVIEW.value
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_report_status_approved_sets_approver(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
        user_id: UUID,
    ):
        """Status 'approved' sollte Genehmiger und Zeitstempel setzen."""
        sample_report.status = "in_review"
        sample_report.approved_at = None
        sample_report.approved_by_id = None
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)
        mock_db.commit = AsyncMock()

        result = await report_service.update_report_status(
            report_id=sample_report.id,
            company_id=company_id,
            new_status=ReportStatus.APPROVED,
            user_id=user_id,
        )

        assert result is True
        assert sample_report.status == ReportStatus.APPROVED
        assert sample_report.approved_by_id == user_id
        assert sample_report.approved_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_report_status_published_sets_timestamp(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Status 'published' sollte published_at setzen."""
        sample_report.status = "approved"
        sample_report.published_at = None
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)
        mock_db.commit = AsyncMock()

        result = await report_service.update_report_status(
            report_id=sample_report.id,
            company_id=company_id,
            new_status=ReportStatus.PUBLISHED,
        )

        assert result is True
        assert sample_report.status == ReportStatus.PUBLISHED
        assert sample_report.published_at is not None

    @pytest.mark.asyncio
    async def test_update_report_status_invalid_status_raises(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte bei ungueltigem Status ValueError werfen."""
        sample_report.status = "draft"
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        with pytest.raises(ValueError, match="Ungültiger Status"):
            await report_service.update_report_status(
                report_id=sample_report.id,
                company_id=company_id,
                new_status="review",  # kein gueltiger ReportStatus-Wert
            )

    @pytest.mark.asyncio
    async def test_update_report_status_not_found_returns_false(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte False zurueckgeben (nicht werfen), wenn der Bericht fehlt."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)
        mock_db.commit = AsyncMock()

        result = await report_service.update_report_status(
            report_id=uuid4(),
            company_id=company_id,
            new_status=ReportStatus.IN_REVIEW.value,
        )

        assert result is False
        mock_db.commit.assert_not_called()
