# -*- coding: utf-8 -*-
"""
Tests fuer Digital Twin Service.

Testet 360° Unternehmensansicht mit allen Sektionen.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List

from app.services.digital_twin_service import (
    DigitalTwinService,
    DigitalTwinSnapshot,
    FinancialHealthSection,
    RiskOverviewSection,
    DocumentPipelineSection,
    ComplianceSection,
    KeyMetricsSection,
    TrendSection,
)


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    return AsyncMock()


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid4()


@pytest.fixture
def digital_twin_service(mock_db):
    """Fixture fuer DigitalTwinService."""
    return DigitalTwinService(mock_db)


# =============================================================================
# Snapshot Tests
# =============================================================================


class TestDigitalTwinSnapshot:
    """Tests fuer vollstaendige Snapshot-Generierung."""

    @pytest.mark.asyncio
    async def test_get_snapshot_returns_all_sections(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_snapshot gibt alle Sektionen zurueck."""
        # Mock all section methods
        with patch.object(
            digital_twin_service,
            "_get_financial_health_section",
            return_value=FinancialHealthSection(
                health_score=75.0,
                cashflow_current_month=Decimal("10000.00"),
                cashflow_trend="stabil",
                open_receivables=Decimal("5000.00"),
                open_payables=Decimal("3000.00"),
                overdue_amount=Decimal("500.00"),
                liquidity_ratio=3.33,
            ),
        ):
            with patch.object(
                digital_twin_service,
                "_get_risk_overview_section",
                return_value=RiskOverviewSection(
                    average_risk_score=35.5,
                    high_risk_entities=2,
                    entities_with_worsening_trend=1,
                    top_risks=[],
                ),
            ):
                with patch.object(
                    digital_twin_service,
                    "_get_document_pipeline_section",
                    return_value=DocumentPipelineSection(
                        documents_today=10,
                        documents_this_week=50,
                        documents_this_month=200,
                        pending_ocr=5,
                        pending_review=3,
                        pending_approval=2,
                        auto_processed_rate=85.0,
                    ),
                ):
                    with patch.object(
                        digital_twin_service,
                        "_get_compliance_section",
                        return_value=ComplianceSection(
                            gdpr_score=85.0,
                            gobd_score=90.0,
                            retention_violations=0,
                            missing_audit_trails=0,
                            upcoming_deadlines=3,
                        ),
                    ):
                        with patch.object(
                            digital_twin_service,
                            "_get_key_metrics_section",
                            return_value=KeyMetricsSection(
                                total_documents=1000,
                                total_entities=50,
                                total_invoices=300,
                                average_processing_time_s=2.5,
                                ocr_accuracy_rate=94.5,
                                auto_categorization_rate=87.3,
                            ),
                        ):
                            with patch.object(
                                digital_twin_service,
                                "_get_trends_section",
                                return_value=TrendSection(
                                    document_volume_trend=[],
                                    revenue_trend=[],
                                    risk_trend=[],
                                ),
                            ):
                                snapshot = await digital_twin_service.get_snapshot(
                                    company_id
                                )

        assert isinstance(snapshot, DigitalTwinSnapshot)
        assert snapshot.financial_health.health_score == 75.0
        assert snapshot.risk_overview.average_risk_score == 35.5
        assert snapshot.document_pipeline.documents_today == 10
        assert snapshot.compliance_status.gdpr_score == 85.0
        assert snapshot.key_metrics.total_documents == 1000
        assert isinstance(snapshot.trends, TrendSection)
        assert isinstance(snapshot.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_snapshot_to_dict_serialization(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: Snapshot kann zu Dictionary serialisiert werden."""
        with patch.object(
            digital_twin_service,
            "_get_financial_health_section",
            return_value=FinancialHealthSection(
                health_score=80.0,
                cashflow_current_month=Decimal("5000.00"),
                cashflow_trend="steigend",
                open_receivables=Decimal("2000.00"),
                open_payables=Decimal("1000.00"),
                overdue_amount=Decimal("100.00"),
                liquidity_ratio=5.0,
            ),
        ):
            with patch.object(
                digital_twin_service,
                "_get_risk_overview_section",
                return_value=RiskOverviewSection(
                    average_risk_score=25.0,
                    high_risk_entities=1,
                    entities_with_worsening_trend=0,
                    top_risks=[],
                ),
            ):
                with patch.object(
                    digital_twin_service,
                    "_get_document_pipeline_section",
                    return_value=DocumentPipelineSection(
                        documents_today=5,
                        documents_this_week=30,
                        documents_this_month=100,
                        pending_ocr=2,
                        pending_review=1,
                        pending_approval=0,
                        auto_processed_rate=90.0,
                    ),
                ):
                    with patch.object(
                        digital_twin_service,
                        "_get_compliance_section",
                        return_value=ComplianceSection(
                            gdpr_score=95.0,
                            gobd_score=92.0,
                            retention_violations=0,
                            missing_audit_trails=0,
                            upcoming_deadlines=1,
                        ),
                    ):
                        with patch.object(
                            digital_twin_service,
                            "_get_key_metrics_section",
                            return_value=KeyMetricsSection(
                                total_documents=500,
                                total_entities=25,
                                total_invoices=150,
                                average_processing_time_s=1.8,
                                ocr_accuracy_rate=96.0,
                                auto_categorization_rate=92.0,
                            ),
                        ):
                            with patch.object(
                                digital_twin_service,
                                "_get_trends_section",
                                return_value=TrendSection(
                                    document_volume_trend=[
                                        {"month": "2026-01", "count": 100}
                                    ],
                                    revenue_trend=[
                                        {"month": "2026-01", "amount": 10000.0}
                                    ],
                                    risk_trend=[
                                        {"month": "2026-01", "avg_score": 30.0}
                                    ],
                                ),
                            ):
                                snapshot = await digital_twin_service.get_snapshot(
                                    company_id
                                )

        snapshot_dict = snapshot.to_dict()

        assert isinstance(snapshot_dict, dict)
        assert "timestamp" in snapshot_dict
        assert "financial_health" in snapshot_dict
        assert "risk_overview" in snapshot_dict
        assert "document_pipeline" in snapshot_dict
        assert "compliance_status" in snapshot_dict
        assert "key_metrics" in snapshot_dict
        assert "trends" in snapshot_dict

        # Check financial health serialization
        assert snapshot_dict["financial_health"]["health_score"] == 80.0
        assert snapshot_dict["financial_health"]["cashflow_current_month"] == 5000.0

    @pytest.mark.asyncio
    async def test_snapshot_with_no_documents(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: Snapshot mit leerer Datenbank."""
        with patch.object(
            digital_twin_service,
            "_get_financial_health_section",
            return_value=FinancialHealthSection(
                health_score=100.0,
                cashflow_current_month=Decimal("0.00"),
                cashflow_trend="stabil",
                open_receivables=Decimal("0.00"),
                open_payables=Decimal("0.00"),
                overdue_amount=Decimal("0.00"),
                liquidity_ratio=0.0,
            ),
        ):
            with patch.object(
                digital_twin_service,
                "_get_risk_overview_section",
                return_value=RiskOverviewSection(
                    average_risk_score=0.0,
                    high_risk_entities=0,
                    entities_with_worsening_trend=0,
                    top_risks=[],
                ),
            ):
                with patch.object(
                    digital_twin_service,
                    "_get_document_pipeline_section",
                    return_value=DocumentPipelineSection(
                        documents_today=0,
                        documents_this_week=0,
                        documents_this_month=0,
                        pending_ocr=0,
                        pending_review=0,
                        pending_approval=0,
                        auto_processed_rate=0.0,
                    ),
                ):
                    with patch.object(
                        digital_twin_service,
                        "_get_compliance_section",
                        return_value=ComplianceSection(
                            gdpr_score=100.0,
                            gobd_score=100.0,
                            retention_violations=0,
                            missing_audit_trails=0,
                            upcoming_deadlines=0,
                        ),
                    ):
                        with patch.object(
                            digital_twin_service,
                            "_get_key_metrics_section",
                            return_value=KeyMetricsSection(
                                total_documents=0,
                                total_entities=0,
                                total_invoices=0,
                                average_processing_time_s=0.0,
                                ocr_accuracy_rate=0.0,
                                auto_categorization_rate=0.0,
                            ),
                        ):
                            with patch.object(
                                digital_twin_service,
                                "_get_trends_section",
                                return_value=TrendSection(
                                    document_volume_trend=[],
                                    revenue_trend=[],
                                    risk_trend=[],
                                ),
                            ):
                                snapshot = await digital_twin_service.get_snapshot(
                                    company_id
                                )

        assert snapshot.key_metrics.total_documents == 0
        assert snapshot.document_pipeline.documents_today == 0
        assert snapshot.risk_overview.high_risk_entities == 0


# =============================================================================
# Section Tests
# =============================================================================


class TestDigitalTwinSection:
    """Tests fuer einzelne Sektionen abrufen."""

    @pytest.mark.asyncio
    async def test_get_section_financial_health(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_section fuer financial_health."""
        mock_section = FinancialHealthSection(
            health_score=75.0,
            cashflow_current_month=Decimal("10000.00"),
            cashflow_trend="stabil",
            open_receivables=Decimal("5000.00"),
            open_payables=Decimal("3000.00"),
            overdue_amount=Decimal("500.00"),
            liquidity_ratio=3.33,
        )

        with patch.object(
            digital_twin_service,
            "_get_financial_health_section",
            return_value=mock_section,
        ):
            result = await digital_twin_service.get_section(
                company_id, "financial_health"
            )

        assert isinstance(result, FinancialHealthSection)
        assert result.health_score == 75.0

    @pytest.mark.asyncio
    async def test_get_section_risk_overview(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_section fuer risk_overview."""
        mock_section = RiskOverviewSection(
            average_risk_score=40.0,
            high_risk_entities=3,
            entities_with_worsening_trend=2,
            top_risks=[
                {"entity_name": "Test GmbH", "risk_score": "65.0", "trend": "worsening"}
            ],
        )

        with patch.object(
            digital_twin_service,
            "_get_risk_overview_section",
            return_value=mock_section,
        ):
            result = await digital_twin_service.get_section(company_id, "risk_overview")

        assert isinstance(result, RiskOverviewSection)
        assert result.high_risk_entities == 3

    @pytest.mark.asyncio
    async def test_get_section_document_pipeline(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_section fuer document_pipeline."""
        mock_section = DocumentPipelineSection(
            documents_today=15,
            documents_this_week=80,
            documents_this_month=300,
            pending_ocr=10,
            pending_review=5,
            pending_approval=3,
            auto_processed_rate=88.0,
        )

        with patch.object(
            digital_twin_service,
            "_get_document_pipeline_section",
            return_value=mock_section,
        ):
            result = await digital_twin_service.get_section(
                company_id, "document_pipeline"
            )

        assert isinstance(result, DocumentPipelineSection)
        assert result.documents_today == 15

    @pytest.mark.asyncio
    async def test_get_section_compliance_status(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_section fuer compliance_status."""
        mock_section = ComplianceSection(
            gdpr_score=92.0,
            gobd_score=88.0,
            retention_violations=2,
            missing_audit_trails=1,
            upcoming_deadlines=5,
        )

        with patch.object(
            digital_twin_service,
            "_get_compliance_section",
            return_value=mock_section,
        ):
            result = await digital_twin_service.get_section(
                company_id, "compliance_status"
            )

        assert isinstance(result, ComplianceSection)
        assert result.gdpr_score == 92.0

    @pytest.mark.asyncio
    async def test_get_section_key_metrics(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_section fuer key_metrics."""
        mock_section = KeyMetricsSection(
            total_documents=2000,
            total_entities=100,
            total_invoices=600,
            average_processing_time_s=3.2,
            ocr_accuracy_rate=93.5,
            auto_categorization_rate=85.0,
        )

        with patch.object(
            digital_twin_service,
            "_get_key_metrics_section",
            return_value=mock_section,
        ):
            result = await digital_twin_service.get_section(company_id, "key_metrics")

        assert isinstance(result, KeyMetricsSection)
        assert result.total_documents == 2000

    @pytest.mark.asyncio
    async def test_get_section_trends(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_section fuer trends."""
        mock_section = TrendSection(
            document_volume_trend=[{"month": "2026-01", "count": 200}],
            revenue_trend=[{"month": "2026-01", "amount": 50000.0}],
            risk_trend=[{"month": "2026-01", "avg_score": 35.0}],
        )

        with patch.object(
            digital_twin_service,
            "_get_trends_section",
            return_value=mock_section,
        ):
            result = await digital_twin_service.get_section(company_id, "trends")

        assert isinstance(result, TrendSection)
        assert len(result.document_volume_trend) == 1

    @pytest.mark.asyncio
    async def test_get_section_invalid_section_name(
        self,
        digital_twin_service,
        company_id,
    ):
        """Test: get_section mit ungueltigem Sektionsnamen wirft ValueError."""
        with pytest.raises(ValueError, match="Unbekannte Sektion"):
            await digital_twin_service.get_section(company_id, "invalid_section")


# =============================================================================
# Financial Health Section Tests
# =============================================================================


class TestFinancialHealthSection:
    """Tests fuer Financial Health Sektion."""

    @pytest.mark.asyncio
    async def test_financial_health_section_structure(
        self,
        company_id,
    ):
        """Test: Financial Health Section hat korrekte Struktur."""
        section = FinancialHealthSection(
            health_score=75.0,
            cashflow_current_month=Decimal("15000.00"),
            cashflow_trend="steigend",
            open_receivables=Decimal("5000.00"),
            open_payables=Decimal("3000.00"),
            overdue_amount=Decimal("500.00"),
            liquidity_ratio=5.0,
        )

        assert isinstance(section, FinancialHealthSection)
        assert section.health_score == 75.0
        assert isinstance(section.cashflow_current_month, Decimal)
        assert isinstance(section.liquidity_ratio, float)
        assert section.cashflow_trend in ["steigend", "stabil", "fallend"]


# =============================================================================
# Risk Overview Section Tests
# =============================================================================


class TestRiskOverviewSection:
    """Tests fuer Risk Overview Sektion."""

    @pytest.mark.asyncio
    async def test_risk_overview_section_structure(
        self,
        company_id,
    ):
        """Test: Risk Overview Section hat korrekte Struktur."""
        section = RiskOverviewSection(
            average_risk_score=45.5,
            high_risk_entities=5,
            entities_with_worsening_trend=2,
            top_risks=[
                {
                    "entity_name": "Test GmbH",
                    "risk_score": "75.0",
                    "trend": "worsening",
                }
            ],
        )

        assert isinstance(section, RiskOverviewSection)
        assert section.average_risk_score == 45.5
        assert section.high_risk_entities == 5
        assert section.entities_with_worsening_trend == 2
        assert len(section.top_risks) == 1
        assert section.top_risks[0]["entity_name"] == "Test GmbH"
        assert section.top_risks[0]["trend"] in ["steigend", "stabil", "fallend", "worsening"]


# =============================================================================
# Document Pipeline Section Tests
# =============================================================================


class TestDocumentPipelineSection:
    """Tests fuer Document Pipeline Sektion."""

    @pytest.mark.asyncio
    async def test_document_pipeline_section_structure(
        self,
        company_id,
    ):
        """Test: Document Pipeline Section hat korrekte Struktur."""
        section = DocumentPipelineSection(
            documents_today=12,
            documents_this_week=65,
            documents_this_month=250,
            pending_ocr=8,
            pending_review=4,
            pending_approval=2,
            auto_processed_rate=80.0,
        )

        assert isinstance(section, DocumentPipelineSection)
        assert section.documents_today == 12
        assert section.documents_this_week == 65
        assert section.documents_this_month == 250
        assert section.pending_ocr == 8
        assert section.pending_review == 4
        assert section.pending_approval == 2
        assert section.auto_processed_rate == pytest.approx(80.0, rel=0.1)
        assert 0.0 <= section.auto_processed_rate <= 100.0
