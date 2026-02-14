# -*- coding: utf-8 -*-
"""
Tests fuer ML Dashboard Service.

Testet ML Progress Dashboard mit OCR-Self-Learning Metriken:
- Dashboard Snapshots
- Learning Curve
- Error Statistics
- Correction Impact
- Model Performance per Document Type
- Auto-Categorization Accuracy
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from typing import List, Dict, Any

from app.services.ml_dashboard_service import (
    MLDashboardService,
    get_ml_dashboard_service,
)
from app.db.models import Document, DocumentType
from app.db.models_ocr_feedback import OCRCorrectionFeedback


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    return AsyncMock()


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid4()


@pytest.fixture
def ml_dashboard_service(mock_db):
    """Fixture fuer MLDashboardService."""
    return MLDashboardService(session=mock_db)


# =============================================================================
# Dashboard Data Tests
# =============================================================================


class TestGetDashboardData:
    """Tests fuer get_dashboard_data."""

    @pytest.mark.asyncio
    async def test_dashboard_data_structure(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Dashboard Data hat korrekte Struktur."""
        # Mock all sub-methods
        mock_db.execute.return_value = MagicMock(
            all=MagicMock(return_value=[]),
            scalar=MagicMock(return_value=0),
        )

        dashboard_data = await ml_dashboard_service.get_dashboard_data(
            company_id, months=6
        )

        assert "period_months" in dashboard_data
        assert dashboard_data["period_months"] == 6
        assert "period_start" in dashboard_data
        assert "period_end" in dashboard_data
        assert "learning_curve" in dashboard_data
        assert "error_statistics" in dashboard_data
        assert "correction_impact" in dashboard_data
        assert "model_performance_by_type" in dashboard_data
        assert "categorization_accuracy" in dashboard_data

    @pytest.mark.asyncio
    async def test_dashboard_data_with_custom_months(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Dashboard Data mit benutzerdefinierter Monatsanzahl."""
        mock_db.execute.return_value = MagicMock(
            all=MagicMock(return_value=[]),
            scalar=MagicMock(return_value=0),
        )

        dashboard_data = await ml_dashboard_service.get_dashboard_data(
            company_id, months=12
        )

        assert dashboard_data["period_months"] == 12
        period_start = datetime.fromisoformat(dashboard_data["period_start"])
        period_end = datetime.fromisoformat(dashboard_data["period_end"])
        delta = period_end - period_start
        assert delta.days >= 360 - 10  # ~12 months with tolerance

    @pytest.mark.asyncio
    async def test_dashboard_data_with_empty_database(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Dashboard Data mit leerer Datenbank."""
        mock_db.execute.return_value = MagicMock(
            all=MagicMock(return_value=[]),
            scalar=MagicMock(return_value=0),
        )

        dashboard_data = await ml_dashboard_service.get_dashboard_data(
            company_id, months=6
        )

        assert isinstance(dashboard_data["learning_curve"], list)
        assert isinstance(dashboard_data["error_statistics"], dict)
        assert isinstance(dashboard_data["correction_impact"], dict)
        assert isinstance(dashboard_data["model_performance_by_type"], list)
        assert isinstance(dashboard_data["categorization_accuracy"], dict)


# =============================================================================
# Learning Curve Tests
# =============================================================================


class TestGetLearningCurve:
    """Tests fuer get_learning_curve."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data_points(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Gibt Liste von Datenpunkten zurueck."""
        # Mock correction query
        month_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_correction_result = MagicMock()
        mock_correction_result.all.return_value = [
            (month_dt, 10, 0.85, 0.92)  # month, correction_count, avg_before, avg_after
        ]

        # Mock document count query
        mock_doc_result = MagicMock()
        mock_doc_result.all.return_value = [
            (month_dt, 100)  # month, doc_count
        ]

        mock_db.execute.side_effect = [
            mock_correction_result,
            mock_doc_result,
        ]

        learning_curve = await ml_dashboard_service.get_learning_curve(
            company_id, months=6
        )

        assert isinstance(learning_curve, list)
        assert len(learning_curve) == 1

    @pytest.mark.asyncio
    async def test_learning_curve_data_point_structure(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Datenpunkt hat korrekte Struktur."""
        month_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_correction_result = MagicMock()
        mock_correction_result.all.return_value = [
            (month_dt, 15, 0.80, 0.90)
        ]

        mock_doc_result = MagicMock()
        mock_doc_result.all.return_value = [
            (month_dt, 150)
        ]

        mock_db.execute.side_effect = [
            mock_correction_result,
            mock_doc_result,
        ]

        learning_curve = await ml_dashboard_service.get_learning_curve(
            company_id, months=6
        )

        data_point = learning_curve[0]
        assert "month" in data_point
        assert "recognition_rate" in data_point
        assert "correction_count" in data_point
        assert "avg_confidence_before" in data_point
        assert "avg_confidence_after" in data_point
        assert "improvement" in data_point

    @pytest.mark.asyncio
    async def test_recognition_rate_calculation(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Erkennungsrate wird korrekt berechnet."""
        month_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # 20 corrections out of 200 documents = 10% correction rate
        # recognition_rate = 1 - (20/200) = 0.90 = 90%
        mock_correction_result = MagicMock()
        mock_correction_result.all.return_value = [
            (month_dt, 20, 0.85, 0.92)
        ]

        mock_doc_result = MagicMock()
        mock_doc_result.all.return_value = [
            (month_dt, 200)
        ]

        mock_db.execute.side_effect = [
            mock_correction_result,
            mock_doc_result,
        ]

        learning_curve = await ml_dashboard_service.get_learning_curve(
            company_id, months=6
        )

        data_point = learning_curve[0]
        assert data_point["recognition_rate"] == pytest.approx(90.0, rel=0.01)
        assert data_point["correction_count"] == 20

    @pytest.mark.asyncio
    async def test_improvement_calculation(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Verbesserung wird korrekt berechnet."""
        month_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Improvement = (avg_after - avg_before) * 100
        # = (0.95 - 0.85) * 100 = 10.0%
        mock_correction_result = MagicMock()
        mock_correction_result.all.return_value = [
            (month_dt, 10, 0.85, 0.95)
        ]

        mock_doc_result = MagicMock()
        mock_doc_result.all.return_value = [
            (month_dt, 100)
        ]

        mock_db.execute.side_effect = [
            mock_correction_result,
            mock_doc_result,
        ]

        learning_curve = await ml_dashboard_service.get_learning_curve(
            company_id, months=6
        )

        data_point = learning_curve[0]
        assert data_point["improvement"] == pytest.approx(10.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_empty_learning_curve(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Leere Learning Curve bei keinen Daten."""
        mock_correction_result = MagicMock()
        mock_correction_result.all.return_value = []

        mock_doc_result = MagicMock()
        mock_doc_result.all.return_value = []

        mock_db.execute.side_effect = [
            mock_correction_result,
            mock_doc_result,
        ]

        learning_curve = await ml_dashboard_service.get_learning_curve(
            company_id, months=6
        )

        assert learning_curve == []

    @pytest.mark.asyncio
    async def test_division_by_zero_guard_in_recognition_rate(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Division by Zero Guard bei recognition_rate."""
        month_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # 5 corrections but 0 documents -> should default to 1.0 (100%)
        mock_correction_result = MagicMock()
        mock_correction_result.all.return_value = [
            (month_dt, 5, 0.80, 0.90)
        ]

        mock_doc_result = MagicMock()
        mock_doc_result.all.return_value = []  # No documents

        mock_db.execute.side_effect = [
            mock_correction_result,
            mock_doc_result,
        ]

        learning_curve = await ml_dashboard_service.get_learning_curve(
            company_id, months=6
        )

        data_point = learning_curve[0]
        assert data_point["recognition_rate"] == 100.0  # 1.0 * 100


# =============================================================================
# Error Statistics Tests
# =============================================================================


class TestGetErrorStatistics:
    """Tests fuer get_error_statistics."""

    @pytest.mark.asyncio
    async def test_error_statistics_structure(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Error Statistics haben korrekte Struktur."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("umlaut", 30),
            ("digit_swap", 20),
        ]
        mock_db.execute.return_value = mock_result

        error_stats = await ml_dashboard_service.get_error_statistics(company_id)

        assert "total_corrections" in error_stats
        assert "error_types" in error_stats
        assert isinstance(error_stats["error_types"], list)

    @pytest.mark.asyncio
    async def test_error_type_fields(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Error Types haben korrekte Felder."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("umlaut", 50),
        ]
        mock_db.execute.return_value = mock_result

        error_stats = await ml_dashboard_service.get_error_statistics(company_id)

        error_type = error_stats["error_types"][0]
        assert "category" in error_type
        assert "description" in error_type
        assert "count" in error_type
        assert "percentage" in error_type
        assert error_type["category"] == "umlaut"
        assert error_type["count"] == 50

    @pytest.mark.asyncio
    async def test_error_percentage_calculation(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Error Percentages werden korrekt berechnet."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("umlaut", 30),
            ("digit_swap", 20),
            ("spacing", 50),
        ]
        mock_db.execute.return_value = mock_result

        error_stats = await ml_dashboard_service.get_error_statistics(company_id)

        # Total = 30 + 20 + 50 = 100
        assert error_stats["total_corrections"] == 100

        # Check percentages
        percentages = {et["category"]: et["percentage"] for et in error_stats["error_types"]}
        assert percentages["umlaut"] == pytest.approx(30.0, rel=0.01)
        assert percentages["digit_swap"] == pytest.approx(20.0, rel=0.01)
        assert percentages["spacing"] == pytest.approx(50.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_division_by_zero_guard_in_percentages(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Division by Zero Guard bei Percentages."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        error_stats = await ml_dashboard_service.get_error_statistics(company_id)

        assert error_stats["total_corrections"] == 0
        assert error_stats["error_types"] == []

    @pytest.mark.asyncio
    async def test_german_category_descriptions(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Deutsche Kategorie-Beschreibungen."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("umlaut", 10),
            ("digit_swap", 5),
            ("unknown", 2),
        ]
        mock_db.execute.return_value = mock_result

        error_stats = await ml_dashboard_service.get_error_statistics(company_id)

        descriptions = {et["category"]: et["description"] for et in error_stats["error_types"]}
        assert "Umlaut" in descriptions["umlaut"]
        assert "Ziffern" in descriptions["digit_swap"]
        assert "Unbekannt" in descriptions["unknown"]


# =============================================================================
# Correction Impact Tests
# =============================================================================


class TestGetCorrectionImpact:
    """Tests fuer get_correction_impact."""

    @pytest.mark.asyncio
    async def test_correction_impact_structure(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Correction Impact hat korrekte Struktur."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 100

        # Mock average query
        mock_avg_result = MagicMock()
        mock_avg_result.first.return_value = (0.85, 0.92)

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_avg_result,
        ]

        impact = await ml_dashboard_service.get_correction_impact(
            company_id, period_start
        )

        assert "correction_count" in impact
        assert "avg_confidence_before" in impact
        assert "avg_confidence_after" in impact
        assert "accuracy_improvement_percent" in impact
        assert "summary" in impact

    @pytest.mark.asyncio
    async def test_accuracy_improvement_calculation(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Accuracy Improvement wird korrekt berechnet."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # Improvement = (avg_after - avg_before) * 100
        # = (0.95 - 0.80) * 100 = 15.0%
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 50

        mock_avg_result = MagicMock()
        mock_avg_result.first.return_value = (0.80, 0.95)

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_avg_result,
        ]

        impact = await ml_dashboard_service.get_correction_impact(
            company_id, period_start
        )

        assert impact["avg_confidence_before"] == pytest.approx(0.80, rel=0.001)
        assert impact["avg_confidence_after"] == pytest.approx(0.95, rel=0.001)
        assert impact["accuracy_improvement_percent"] == pytest.approx(15.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_correction_impact_with_zero_corrections(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Correction Impact mit 0 Korrekturen."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_avg_result = MagicMock()
        mock_avg_result.first.return_value = (None, None)

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_avg_result,
        ]

        impact = await ml_dashboard_service.get_correction_impact(
            company_id, period_start
        )

        assert impact["correction_count"] == 0
        assert impact["avg_confidence_before"] == 0.0
        assert impact["avg_confidence_after"] == 0.0
        assert impact["accuracy_improvement_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_correction_impact_summary_german(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Summary ist auf Deutsch."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 75

        mock_avg_result = MagicMock()
        mock_avg_result.first.return_value = (0.85, 0.90)

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_avg_result,
        ]

        impact = await ml_dashboard_service.get_correction_impact(
            company_id, period_start
        )

        summary = impact["summary"]
        assert "Korrekturen" in summary
        assert "Genauigkeit" in summary
        assert "75" in summary  # correction_count


# =============================================================================
# Model Performance by Type Tests
# =============================================================================


class TestGetModelPerformanceByType:
    """Tests fuer get_model_performance_by_type."""

    @pytest.mark.asyncio
    async def test_returns_list_of_performance_metrics(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Gibt Liste von Performance-Metriken zurueck."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (DocumentType.INVOICE, 100, 10, 0.92),  # doc_type, count, corrections, avg_conf
        ]
        mock_db.execute.return_value = mock_result

        performance = await ml_dashboard_service.get_model_performance_by_type(
            company_id
        )

        assert isinstance(performance, list)
        assert len(performance) == 1

    @pytest.mark.asyncio
    async def test_performance_metric_structure(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Performance-Metrik hat korrekte Struktur."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (DocumentType.INVOICE, 150, 15, 0.94),
        ]
        mock_db.execute.return_value = mock_result

        performance = await ml_dashboard_service.get_model_performance_by_type(
            company_id
        )

        metric = performance[0]
        assert "document_type" in metric
        assert "document_count" in metric
        assert "correction_count" in metric
        assert "avg_confidence" in metric
        assert "accuracy_rate" in metric

    @pytest.mark.asyncio
    async def test_accuracy_rate_calculation(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Accuracy Rate wird korrekt berechnet."""
        # 200 documents, 20 corrections = 10% correction rate
        # accuracy_rate = 1 - (20/200) = 0.90 = 90%
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (DocumentType.INVOICE, 200, 20, 0.91),
        ]
        mock_db.execute.return_value = mock_result

        performance = await ml_dashboard_service.get_model_performance_by_type(
            company_id
        )

        metric = performance[0]
        assert metric["accuracy_rate"] == pytest.approx(90.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_division_by_zero_guard_in_accuracy_rate(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Division by Zero Guard bei accuracy_rate."""
        # 0 documents -> accuracy_rate should default to 1.0 (100%)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (DocumentType.INVOICE, 0, 0, 0.0),
        ]
        mock_db.execute.return_value = mock_result

        performance = await ml_dashboard_service.get_model_performance_by_type(
            company_id
        )

        metric = performance[0]
        assert metric["accuracy_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_multiple_document_types(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Mehrere Dokumenttypen."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (DocumentType.INVOICE, 100, 5, 0.95),
            (DocumentType.RECEIPT, 80, 8, 0.88),
            (DocumentType.CONTRACT, 50, 2, 0.96),
        ]
        mock_db.execute.return_value = mock_result

        performance = await ml_dashboard_service.get_model_performance_by_type(
            company_id
        )

        assert len(performance) == 3
        doc_types = {p["document_type"] for p in performance}
        assert DocumentType.INVOICE in doc_types
        assert DocumentType.RECEIPT in doc_types
        assert DocumentType.CONTRACT in doc_types


# =============================================================================
# Categorization Accuracy Tests
# =============================================================================


class TestGetCategorizationAccuracy:
    """Tests fuer get_categorization_accuracy."""

    @pytest.mark.asyncio
    async def test_categorization_accuracy_structure(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Categorization Accuracy hat korrekte Struktur."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # Mock queries: total_docs, auto_categorized, prev_total, prev_auto
        query_results = [
            MagicMock(scalar=MagicMock(return_value=200)),   # total_docs
            MagicMock(scalar=MagicMock(return_value=180)),   # auto_categorized
            MagicMock(scalar=MagicMock(return_value=150)),   # prev_total
            MagicMock(scalar=MagicMock(return_value=120)),   # prev_auto
        ]
        mock_db.execute.side_effect = query_results

        accuracy = await ml_dashboard_service.get_categorization_accuracy(
            company_id, period_start
        )

        assert "total_documents" in accuracy
        assert "auto_categorized" in accuracy
        assert "accuracy_rate_percent" in accuracy
        assert "trend_percent" in accuracy
        assert "trend_direction" in accuracy

    @pytest.mark.asyncio
    async def test_accuracy_rate_calculation(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Accuracy Rate wird korrekt berechnet."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # 180 out of 200 = 90% accuracy
        query_results = [
            MagicMock(scalar=MagicMock(return_value=200)),
            MagicMock(scalar=MagicMock(return_value=180)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=80)),
        ]
        mock_db.execute.side_effect = query_results

        accuracy = await ml_dashboard_service.get_categorization_accuracy(
            company_id, period_start
        )

        assert accuracy["accuracy_rate_percent"] == pytest.approx(90.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_trend_direction_up(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Trend direction 'up' bei steigender Accuracy."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # Current: 90% (180/200), Previous: 80% (80/100) -> trend = +10%
        query_results = [
            MagicMock(scalar=MagicMock(return_value=200)),
            MagicMock(scalar=MagicMock(return_value=180)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=80)),
        ]
        mock_db.execute.side_effect = query_results

        accuracy = await ml_dashboard_service.get_categorization_accuracy(
            company_id, period_start
        )

        assert accuracy["trend_direction"] == "up"
        assert accuracy["trend_percent"] > 0

    @pytest.mark.asyncio
    async def test_trend_direction_down(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Trend direction 'down' bei sinkender Accuracy."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # Current: 70% (70/100), Previous: 85% (85/100) -> trend = -15%
        query_results = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=70)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=85)),
        ]
        mock_db.execute.side_effect = query_results

        accuracy = await ml_dashboard_service.get_categorization_accuracy(
            company_id, period_start
        )

        assert accuracy["trend_direction"] == "down"
        assert accuracy["trend_percent"] < 0

    @pytest.mark.asyncio
    async def test_trend_direction_stable(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Trend direction 'stable' bei gleicher Accuracy."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # Current: 80% (80/100), Previous: 80% (80/100) -> trend = 0%
        query_results = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=80)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=80)),
        ]
        mock_db.execute.side_effect = query_results

        accuracy = await ml_dashboard_service.get_categorization_accuracy(
            company_id, period_start
        )

        assert accuracy["trend_direction"] == "stable"
        assert accuracy["trend_percent"] == pytest.approx(0.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_division_by_zero_guard_in_accuracy_rate(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Division by Zero Guard bei accuracy_rate."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # 0 total documents -> accuracy should be 0.0
        query_results = [
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
        ]
        mock_db.execute.side_effect = query_results

        accuracy = await ml_dashboard_service.get_categorization_accuracy(
            company_id, period_start
        )

        assert accuracy["accuracy_rate_percent"] == 0.0
        assert accuracy["trend_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_division_by_zero_guard_in_trend(
        self,
        ml_dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Division by Zero Guard bei trend mit prev_total=0."""
        period_start = datetime.now(timezone.utc) - timedelta(days=180)

        # Current period has data, previous period has 0 documents
        query_results = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=80)),
            MagicMock(scalar=MagicMock(return_value=0)),   # prev_total = 0
            MagicMock(scalar=MagicMock(return_value=0)),   # prev_auto = 0
        ]
        mock_db.execute.side_effect = query_results

        accuracy = await ml_dashboard_service.get_categorization_accuracy(
            company_id, period_start
        )

        # Should not crash, prev_accuracy defaults to 0
        assert accuracy["accuracy_rate_percent"] == pytest.approx(80.0, rel=0.01)
        assert accuracy["trend_percent"] == pytest.approx(80.0, rel=0.01)  # 80 - 0 = 80
        assert accuracy["trend_direction"] == "up"


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestGetMLDashboardService:
    """Tests fuer Factory-Funktion get_ml_dashboard_service."""

    @pytest.mark.asyncio
    async def test_factory_returns_service_instance(
        self,
        mock_db,
    ):
        """Test: Factory gibt MLDashboardService-Instanz zurueck."""
        service = get_ml_dashboard_service(mock_db)

        assert isinstance(service, MLDashboardService)
        assert service.session == mock_db
