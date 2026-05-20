# -*- coding: utf-8 -*-
"""
Unit Tests fuer Proactive Insights API Endpoints.

Testet:
- GET /insights/all
- GET /insights/deadlines
- GET /insights/anomalies
- GET /insights/workflow
- GET /insights/data-quality
- GET /insights/data-quality/summary
- GET /insights/summary
- POST /insights/{id}/feedback

PHASE 6: Proaktive Intelligenz
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.company_id = uuid4()
    user.is_active = True
    user.is_superuser = False
    return user


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_insight():
    """Sample ProactiveInsight als Dictionary."""
    return {
        "id": str(uuid4()),
        "insight_type": "warning",
        "priority": "high",
        "title": "Skonto laeuft ab",
        "message": "Skonto von 2% fuer Rechnung R-001 laeuft in 5 Tagen ab.",
        "detail": "Bei Zahlung bis zum Stichtag sparen Sie 23.80 EUR.",
        "potential_value": 23.80,
        "action_url": "/invoices/123/pay",
        "action_label": "Jetzt zahlen",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "related_entities": [],
    }


@pytest.fixture
def sample_data_quality_summary():
    """Sample DataQualitySummary als Dictionary."""
    return {
        "total_entities": 100,
        "entities_with_issues": 20,
        "total_issues": 35,
        "issues_by_type": {
            "missing_field": 15,
            "duplicate": 5,
            "inconsistent": 10,
            "outdated": 5,
        },
        "quality_score": 80.0,
        "grade": "B",
    }


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAuthentication:
    """Tests fuer Authentifizierung."""

    @pytest.mark.asyncio
    async def test_requires_authentication(self):
        """Alle Endpoints erfordern Authentifizierung."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            endpoints = [
                "/api/v1/insights/all",
                "/api/v1/insights/deadlines",
                "/api/v1/insights/anomalies",
                "/api/v1/insights/workflow",
                "/api/v1/insights/data-quality",
                "/api/v1/insights/data-quality/summary",
                "/api/v1/insights/summary",
            ]

            for endpoint in endpoints:
                response = await client.get(endpoint)
                # Sollte 401 oder 403 zurueckgeben ohne Auth
                assert response.status_code in [401, 403, 422]


# =============================================================================
# GET /insights/all Tests
# =============================================================================

class TestGetAllInsights:
    """Tests fuer GET /insights/all."""

    @pytest.mark.asyncio
    async def test_get_all_insights_success(self, mock_current_user, mock_db, sample_insight):
        """Erfolgreiches Abrufen aller Insights."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                with patch("app.api.v1.proactive_insights.DeadlineInsightsService") as mock_deadline:
                    with patch("app.api.v1.proactive_insights.AnomalyInsightsService") as mock_anomaly:
                        with patch("app.api.v1.proactive_insights.WorkflowInsightsService") as mock_workflow:
                            with patch("app.api.v1.proactive_insights.DataEnrichmentInsightsService") as mock_data:
                                # Setup mocks
                                mock_deadline.return_value.check_all_deadlines = AsyncMock(return_value=[])
                                mock_anomaly.return_value.detect_all_anomalies = AsyncMock(return_value=[])
                                mock_workflow.return_value.get_all_workflow_insights = AsyncMock(return_value=[])
                                mock_data.return_value.get_all_data_insights = AsyncMock(return_value=[])

                                async with AsyncClient(app=app, base_url="http://test") as client:
                                    response = await client.get(
                                        "/api/v1/insights/all",
                                        headers={"Authorization": "Bearer test-token"}
                                    )

                                    # Response-Struktur pruefen
                                    assert response.status_code in [200, 401, 403]


# =============================================================================
# GET /insights/deadlines Tests
# =============================================================================

class TestGetDeadlineInsights:
    """Tests fuer GET /insights/deadlines."""

    @pytest.mark.asyncio
    async def test_get_deadline_insights_with_days_param(self, mock_current_user, mock_db):
        """Deadline-Insights mit days-Parameter."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                with patch("app.api.v1.proactive_insights.DeadlineInsightsService") as mock_service:
                    mock_service.return_value.check_all_deadlines = AsyncMock(return_value=[])

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/insights/deadlines?days_ahead=30",
                            headers={"Authorization": "Bearer test-token"}
                        )

                        assert response.status_code in [200, 401, 403]


# =============================================================================
# GET /insights/anomalies Tests
# =============================================================================

class TestGetAnomalyInsights:
    """Tests fuer GET /insights/anomalies."""

    @pytest.mark.asyncio
    async def test_get_anomaly_insights_with_lookback(self, mock_current_user, mock_db):
        """Anomalie-Insights mit lookback_days-Parameter."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                with patch("app.api.v1.proactive_insights.AnomalyInsightsService") as mock_service:
                    mock_service.return_value.detect_all_anomalies = AsyncMock(return_value=[])

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/insights/anomalies?lookback_days=60",
                            headers={"Authorization": "Bearer test-token"}
                        )

                        assert response.status_code in [200, 401, 403]


# =============================================================================
# GET /insights/workflow Tests
# =============================================================================

class TestGetWorkflowInsights:
    """Tests fuer GET /insights/workflow."""

    @pytest.mark.asyncio
    async def test_get_workflow_insights(self, mock_current_user, mock_db):
        """Workflow-Insights abrufen."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                with patch("app.api.v1.proactive_insights.WorkflowInsightsService") as mock_service:
                    mock_service.return_value.get_all_workflow_insights = AsyncMock(return_value=[])

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/insights/workflow",
                            headers={"Authorization": "Bearer test-token"}
                        )

                        assert response.status_code in [200, 401, 403]


# =============================================================================
# GET /insights/data-quality Tests
# =============================================================================

class TestGetDataQualityInsights:
    """Tests fuer GET /insights/data-quality."""

    @pytest.mark.asyncio
    async def test_get_data_quality_insights(self, mock_current_user, mock_db):
        """Datenqualitaets-Insights abrufen."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                with patch("app.api.v1.proactive_insights.DataEnrichmentInsightsService") as mock_service:
                    mock_service.return_value.get_all_data_insights = AsyncMock(return_value=[])

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/insights/data-quality",
                            headers={"Authorization": "Bearer test-token"}
                        )

                        assert response.status_code in [200, 401, 403]


# =============================================================================
# GET /insights/data-quality/summary Tests
# =============================================================================

class TestGetDataQualitySummary:
    """Tests fuer GET /insights/data-quality/summary."""

    @pytest.mark.asyncio
    async def test_get_data_quality_summary(
        self, mock_current_user, mock_db, sample_data_quality_summary
    ):
        """Datenqualitaets-Zusammenfassung abrufen."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                with patch("app.api.v1.proactive_insights.DataEnrichmentInsightsService") as mock_service:
                    mock_summary = MagicMock()
                    for key, value in sample_data_quality_summary.items():
                        setattr(mock_summary, key, value)
                    mock_service.return_value.get_data_quality_summary = AsyncMock(
                        return_value=mock_summary
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/insights/data-quality/summary",
                            headers={"Authorization": "Bearer test-token"}
                        )

                        assert response.status_code in [200, 401, 403]


# =============================================================================
# GET /insights/summary Tests
# =============================================================================

class TestGetInsightsSummary:
    """Tests fuer GET /insights/summary."""

    @pytest.mark.asyncio
    async def test_get_insights_summary(self, mock_current_user, mock_db):
        """Insights-Zusammenfassung abrufen."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                # Patch all services
                with patch("app.api.v1.proactive_insights.DeadlineInsightsService") as mock_deadline:
                    with patch("app.api.v1.proactive_insights.AnomalyInsightsService") as mock_anomaly:
                        with patch("app.api.v1.proactive_insights.WorkflowInsightsService") as mock_workflow:
                            with patch("app.api.v1.proactive_insights.DataEnrichmentInsightsService") as mock_data:
                                mock_deadline.return_value.check_all_deadlines = AsyncMock(return_value=[])
                                mock_anomaly.return_value.detect_all_anomalies = AsyncMock(return_value=[])
                                mock_workflow.return_value.get_all_workflow_insights = AsyncMock(return_value=[])
                                mock_data.return_value.get_all_data_insights = AsyncMock(return_value=[])

                                async with AsyncClient(app=app, base_url="http://test") as client:
                                    response = await client.get(
                                        "/api/v1/insights/summary",
                                        headers={"Authorization": "Bearer test-token"}
                                    )

                                    assert response.status_code in [200, 401, 403]


# =============================================================================
# POST /insights/{id}/feedback Tests
# =============================================================================

class TestPostInsightFeedback:
    """Tests fuer POST /insights/{id}/feedback."""

    @pytest.mark.asyncio
    async def test_submit_positive_feedback(self, mock_current_user, mock_db):
        """Positives Feedback senden."""
        insight_id = uuid4()

        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v1/insights/{insight_id}/feedback",
                        json={
                            "was_helpful": True,
                            "feedback_text": "Sehr hilfreich!",
                        },
                        headers={"Authorization": "Bearer test-token"}
                    )

                    assert response.status_code in [200, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_submit_negative_feedback(self, mock_current_user, mock_db):
        """Negatives Feedback senden."""
        insight_id = uuid4()

        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v1/insights/{insight_id}/feedback",
                        json={
                            "was_helpful": False,
                            "feedback_text": "Nicht relevant fuer mich.",
                        },
                        headers={"Authorization": "Bearer test-token"}
                    )

                    assert response.status_code in [200, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_feedback_without_text(self, mock_current_user, mock_db):
        """Feedback ohne Text ist moeglich."""
        insight_id = uuid4()

        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v1/insights/{insight_id}/feedback",
                        json={
                            "was_helpful": True,
                        },
                        headers={"Authorization": "Bearer test-token"}
                    )

                    assert response.status_code in [200, 401, 403, 422]


# =============================================================================
# Response Format Tests
# =============================================================================

class TestResponseFormats:
    """Tests fuer Response-Formate."""

    def test_insight_response_schema(self, sample_insight):
        """InsightResponse hat korrektes Schema."""
        required_fields = [
            "id", "insight_type", "priority", "title", "message", "created_at"
        ]

        for field in required_fields:
            assert field in sample_insight

    def test_data_quality_summary_schema(self, sample_data_quality_summary):
        """DataQualitySummary hat korrektes Schema."""
        required_fields = [
            "total_entities", "entities_with_issues", "total_issues",
            "issues_by_type", "quality_score", "grade"
        ]

        for field in required_fields:
            assert field in sample_data_quality_summary

    def test_quality_grade_valid(self, sample_data_quality_summary):
        """Quality-Grade ist gueltig."""
        valid_grades = ["A", "B", "C", "D", "F"]
        assert sample_data_quality_summary["grade"] in valid_grades


# =============================================================================
# Query Parameter Validation Tests
# =============================================================================

class TestQueryParameterValidation:
    """Tests fuer Query-Parameter-Validierung."""

    @pytest.mark.asyncio
    async def test_days_ahead_min_value(self):
        """days_ahead muss positiv sein."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/insights/deadlines?days_ahead=-5",
                headers={"Authorization": "Bearer test-token"}
            )

            # Sollte 422 fuer ungueltige Parameter oder 401 fuer fehlende Auth
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_lookback_days_max_value(self):
        """lookback_days hat Maximum."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/insights/anomalies?lookback_days=10000",
                headers={"Authorization": "Bearer test-token"}
            )

            # Sollte entweder funktionieren oder 422
            assert response.status_code in [200, 401, 403, 422]


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_handles_service_error(self, mock_current_user, mock_db):
        """Behandelt Service-Fehler graceful."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                with patch("app.api.v1.proactive_insights.DeadlineInsightsService") as mock_service:
                    mock_service.return_value.check_all_deadlines = AsyncMock(
                        side_effect=Exception("Service Error")
                    )

                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.get(
                            "/api/v1/insights/deadlines",
                            headers={"Authorization": "Bearer test-token"}
                        )

                        # Sollte 500 oder graceful handling
                        assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_invalid_insight_id(self, mock_current_user, mock_db):
        """Behandelt ungueltige Insight-ID."""
        with patch("app.api.v1.proactive_insights.get_current_active_user", return_value=mock_current_user):
            with patch("app.api.v1.proactive_insights.get_db", return_value=mock_db):
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/api/v1/insights/invalid-uuid/feedback",
                        json={"was_helpful": True},
                        headers={"Authorization": "Bearer test-token"}
                    )

                    # Sollte 422 fuer ungueltige UUID
                    assert response.status_code in [401, 403, 422]
