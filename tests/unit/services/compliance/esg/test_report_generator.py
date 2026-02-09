# -*- coding: utf-8 -*-
"""
Unit Tests fuer ESGReportGeneratorService.

Testet:
- generate_report()
- get_reports()
- get_report_detail()
- update_report_status()
- publish_report()
- export_report()
- GRI/CSRD Compliance

Feinpoliert und durchdacht - ESG Report Generator Tests.
"""

from datetime import date, datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.report_generator import (
    ESGReportGenerator as ESGReportGeneratorService,
    get_esg_report_generator as get_report_generator_service,
)
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def report_service(mock_db: AsyncMock) -> ESGReportGeneratorService:
    """Create ESGReportGeneratorService instance with mocked db."""
    return ESGReportGeneratorService(mock_db)


@pytest.fixture
def sample_report_data(company_id: UUID):
    """Sample data for report generation."""
    return {
        "emissions": {
            "scope_1": 15360.0,
            "scope_2": 4200.0,
            "scope_3": 8550.0,
            "total": 28110.0,
        },
        "suppliers": {
            "total_assessed": 25,
            "avg_score": 75.5,
            "high_risk_count": 2,
        },
        "certifications": {
            "active": 12,
            "expiring_soon": 3,
        },
        "goals": {
            "total": 8,
            "on_track": 6,
            "progress_avg": 65.5,
        },
    }


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_report_generator_service Factory."""

    def test_get_report_generator_service_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte ESGReportGeneratorService-Instanz zurueckgeben."""
        service = get_report_generator_service(mock_db)

        assert isinstance(service, ESGReportGeneratorService)
        assert service.db is mock_db


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
        """Sollte neuen Bericht generieren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Mock data gathering
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        report = await report_service.generate_report(
            company_id=company_id,
            created_by_id=user_id,
            report_type="annual_sustainability",
            title="Nachhaltigkeitsbericht 2025",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            reporting_standard="GRI",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

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

        await report_service.generate_report(
            company_id=company_id,
            created_by_id=user_id,
            report_type="csrd_compliance",
            title="CSRD Nachhaltigkeitsbericht 2025",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            reporting_standard="CSRD",
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_report_aggregates_data(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
        sample_report_data,
    ):
        """Sollte Daten aus verschiedenen Quellen aggregieren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Mock multiple data sources
        emissions_mock = MagicMock()
        emissions_mock.total_co2_kg = sample_report_data["emissions"]["total"]

        mock_db.execute.return_value = create_mock_result(scalar_value=emissions_mock)

        await report_service.generate_report(
            company_id=company_id,
            created_by_id=user_id,
            report_type="annual_sustainability",
            title="Jahresbericht",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        )

        # Should have queried multiple data sources
        assert mock_db.execute.called


# ========================= Get Reports Tests =========================


class TestGetReports:
    """Tests fuer get_reports() Methode."""

    @pytest.mark.asyncio
    async def test_get_reports_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Berichte zurueckgeben."""
        reports = [sample_report]
        mock_db.execute.return_value = create_mock_result(scalars_list=reports)

        result = await report_service.get_reports(company_id=company_id)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_reports_filter_by_type(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte nach Berichtstyp filtern."""
        sample_report.report_type = "annual_sustainability"
        mock_db.execute.return_value = create_mock_result(scalars_list=[sample_report])

        result = await report_service.get_reports(
            company_id=company_id,
            report_type="annual_sustainability",
        )

        for r in result:
            assert r.report_type == "annual_sustainability"

    @pytest.mark.asyncio
    async def test_get_reports_filter_by_status(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte nach Status filtern."""
        sample_report.status = "published"
        mock_db.execute.return_value = create_mock_result(scalars_list=[sample_report])

        result = await report_service.get_reports(
            company_id=company_id,
            status="published",
        )

        for r in result:
            assert r.status == "published"


# ========================= Get Report Detail Tests =========================


class TestGetReportDetail:
    """Tests fuer get_report_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_report_detail_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Berichtsdetails zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        result = await report_service.get_report_detail(
            report_id=sample_report.id,
            company_id=company_id,
        )

        assert result is not None
        assert result.id == sample_report.id

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
    """Tests fuer update_report_status() Methode."""

    @pytest.mark.asyncio
    async def test_update_report_status_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Berichtsstatus aktualisieren."""
        sample_report.status = "draft"
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)
        mock_db.commit = AsyncMock()

        result = await report_service.update_report_status(
            report_id=sample_report.id,
            company_id=company_id,
            new_status="review",
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_report_status_with_approval(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte Status mit Genehmigung aktualisieren."""
        sample_report.status = "review"
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)
        mock_db.commit = AsyncMock()

        await report_service.update_report_status(
            report_id=sample_report.id,
            company_id=company_id,
            new_status="approved",
            approved_by_id=user_id,
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_report_status_not_found(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await report_service.update_report_status(
                report_id=uuid4(),
                company_id=company_id,
                new_status="review",
            )


# ========================= Publish Report Tests =========================


class TestPublishReport:
    """Tests fuer publish_report() Methode."""

    @pytest.mark.asyncio
    async def test_publish_report_success(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Bericht veroeffentlichen."""
        sample_report.status = "approved"
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)
        mock_db.commit = AsyncMock()

        result = await report_service.publish_report(
            report_id=sample_report.id,
            company_id=company_id,
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_report_not_approved(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht genehmigt."""
        sample_report.status = "draft"
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        with pytest.raises(ValueError, match="nicht genehmigt"):
            await report_service.publish_report(
                report_id=sample_report.id,
                company_id=company_id,
            )


# ========================= Export Report Tests =========================


class TestExportReport:
    """Tests fuer export_report() Methode."""

    @pytest.mark.asyncio
    async def test_export_report_pdf(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Bericht als PDF exportieren."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        with patch.object(
            report_service, "_generate_pdf", return_value=b"%PDF-1.4 content"
        ):
            content, filename = await report_service.export_report(
                report_id=sample_report.id,
                company_id=company_id,
                export_format="pdf",
            )

        assert content is not None
        assert filename.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_export_report_json(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Bericht als JSON exportieren."""
        sample_report.content = {"test": "data"}
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        content, filename = await report_service.export_report(
            report_id=sample_report.id,
            company_id=company_id,
            export_format="json",
        )

        assert filename.endswith(".json")

    @pytest.mark.asyncio
    async def test_export_report_csv(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte Bericht als CSV exportieren."""
        sample_report.content = {"emissions": [{"month": "2025-01", "value": 1000}]}
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        content, filename = await report_service.export_report(
            report_id=sample_report.id,
            company_id=company_id,
            export_format="csv",
        )

        assert filename.endswith(".csv")

    @pytest.mark.asyncio
    async def test_export_report_not_found(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await report_service.export_report(
                report_id=uuid4(),
                company_id=company_id,
                export_format="pdf",
            )


# ========================= GRI Compliance Tests =========================


class TestGRICompliance:
    """Tests fuer GRI-Konformitaet."""

    @pytest.mark.asyncio
    async def test_generate_gri_index(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte GRI-Index generieren."""
        sample_report.reporting_standard = "GRI"
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        gri_index = await report_service.generate_gri_index(
            report_id=sample_report.id,
            company_id=company_id,
        )

        # Starke Assertion: GRI-Index MUSS disclosures enthalten
        assert gri_index is not None, "generate_gri_index sollte ein Ergebnis zurueckgeben"
        assert "disclosures" in gri_index, \
            f"GRI-Index muss 'disclosures' enthalten, erhielt: {gri_index.keys() if isinstance(gri_index, dict) else type(gri_index)}"
        mock_db.execute.assert_called()  # Verifiziere, dass DB aufgerufen wurde

    @pytest.mark.asyncio
    async def test_validate_gri_compliance(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte GRI-Konformitaet validieren."""
        sample_report.reporting_standard = "GRI"
        sample_report.content = {
            "general_disclosures": {"GRI_2_1": True},
            "material_topics": ["emissions"],
        }
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        result = await report_service.validate_gri_compliance(
            report_id=sample_report.id,
            company_id=company_id,
        )

        # Starke Assertion: Result MUSS entweder is_compliant oder missing_disclosures enthalten
        assert result is not None, "validate_gri_compliance sollte ein Ergebnis zurueckgeben"
        assert "is_compliant" in result or "missing_disclosures" in result, \
            f"Ergebnis muss 'is_compliant' oder 'missing_disclosures' enthalten, erhielt: {result.keys()}"
        mock_db.execute.assert_called()  # Verifiziere, dass DB aufgerufen wurde


# ========================= CSRD Compliance Tests =========================


class TestCSRDCompliance:
    """Tests fuer CSRD-Konformitaet."""

    @pytest.mark.asyncio
    async def test_validate_csrd_requirements(
        self,
        report_service: ESGReportGeneratorService,
        mock_db: AsyncMock,
        sample_report,
        company_id: UUID,
    ):
        """Sollte CSRD-Anforderungen validieren."""
        sample_report.reporting_standard = "CSRD"
        sample_report.content = {
            "double_materiality": True,
            "climate_targets": True,
            "value_chain": True,
        }
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_report)

        result = await report_service.validate_csrd_requirements(
            report_id=sample_report.id,
            company_id=company_id,
        )

        assert mock_db.execute.called


# ========================= Template Tests =========================


class TestReportTemplates:
    """Tests fuer Berichtsvorlagen."""

    @pytest.mark.asyncio
    async def test_get_available_templates(
        self,
        report_service: ESGReportGeneratorService,
    ):
        """Sollte verfuegbare Vorlagen zurueckgeben."""
        templates = report_service.get_available_templates()

        assert len(templates) > 0
        assert any(t["type"] == "annual_sustainability" for t in templates)

    @pytest.mark.asyncio
    async def test_get_template_structure(
        self,
        report_service: ESGReportGeneratorService,
    ):
        """Sollte Vorlagenstruktur zurueckgeben."""
        structure = report_service.get_template_structure("annual_sustainability")

        assert "sections" in structure
        assert len(structure["sections"]) > 0
