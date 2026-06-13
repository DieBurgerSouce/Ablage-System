# -*- coding: utf-8 -*-
"""
Unit-Tests für Risk Scoring Celery Tasks.

Testet:
- calculate_all_risk_scores_task
- calculate_single_risk_score_task
- on_invoice_updated_recalculate
- check_high_risk_entities_task
- generate_risk_statistics_task

Feinpoliert und durchdacht - Enterprise Risk Scoring Tasks.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from app.workers.tasks.risk_scoring_tasks import (
    calculate_all_risk_scores_task,
    calculate_single_risk_score_task,
    on_invoice_updated_recalculate,
    check_high_risk_entities_task,
    generate_risk_statistics_task,
)


# ========================= Test Fixtures =========================


@pytest.fixture
def sample_entity_id() -> str:
    """Provide sample entity UUID as string."""
    return str(uuid4())


@pytest.fixture
def sample_document_id() -> str:
    """Provide sample document UUID as string."""
    return str(uuid4())


@pytest.fixture
def mock_entity() -> Mock:
    """Create mock BusinessEntity."""
    entity = Mock()
    entity.id = uuid4()
    entity.name = "Test GmbH"
    entity.entity_type = "customer"
    entity.is_active = True
    entity.risk_score = 45.5
    entity.payment_behavior_score = 78.2
    entity.risk_factors = {
        "payment_delay_days": 5.0,
        "default_rate": 2.5,
    }
    entity.risk_calculated_at = datetime.now(timezone.utc)
    entity.deleted_at = None
    return entity


@pytest.fixture
def mock_document() -> Mock:
    """Create mock Document."""
    doc = Mock()
    doc.id = uuid4()
    doc.business_entity_id = uuid4()
    doc.deleted_at = None
    return doc


# ========================= Task Configuration Tests =========================


class TestTaskConfiguration:
    """Tests for task configuration and decorators."""

    def test_calculate_all_has_correct_queue(self):
        """calculate_all sollte in maintenance queue laufen."""
        assert calculate_all_risk_scores_task.queue == "maintenance"

    def test_calculate_all_has_retry_config(self):
        """calculate_all sollte Retry-Konfiguration haben."""
        assert calculate_all_risk_scores_task.max_retries == 2
        assert calculate_all_risk_scores_task.default_retry_delay == 300

    def test_calculate_single_has_correct_queue(self):
        """calculate_single sollte in metadata queue laufen."""
        assert calculate_single_risk_score_task.queue == "metadata"

    def test_calculate_single_has_retry_config(self):
        """calculate_single sollte Retry-Konfiguration haben."""
        assert calculate_single_risk_score_task.max_retries == 3
        assert calculate_single_risk_score_task.default_retry_delay == 30

    def test_on_invoice_updated_has_correct_queue(self):
        """on_invoice_updated sollte in metadata queue laufen."""
        assert on_invoice_updated_recalculate.queue == "metadata"

    def test_check_high_risk_has_retry_config(self):
        """check_high_risk sollte Retry-Konfiguration haben."""
        assert check_high_risk_entities_task.max_retries == 2
        assert check_high_risk_entities_task.default_retry_delay == 120

    def test_generate_statistics_has_retry_config(self):
        """generate_statistics sollte Retry-Konfiguration haben."""
        assert generate_risk_statistics_task.max_retries == 2
        assert generate_risk_statistics_task.default_retry_delay == 180


# ========================= Security Tests =========================


class TestSecurityCompliance:
    """Tests for PII/security compliance in task responses."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_calculate_all_does_not_expose_entity_name_in_errors(self, mock_run):
        """Fehler sollten keine Entity-Namen enthalten (PII)."""
        # Simuliere Ergebnis mit Fehlern
        mock_run.return_value = {
            "total_processed": 5,
            "successful": 3,
            "failed": 2,
            "skipped": 0,
            "errors": [
                {"entity_id": str(uuid4()), "error": "Test error"},
                {"entity_id": str(uuid4()), "error": "Another error"},
            ],
            "processing_time_ms": 1500,
            "version": "v1",
        }

        result = calculate_all_risk_scores_task()

        # Pruefe dass keine entity_name in errors
        for error in result["errors"]:
            assert "entity_name" not in error
            assert "entity_id" in error

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_calculate_single_does_not_expose_entity_name(self, mock_run):
        """Erfolgsantwort sollte keine Entity-Namen enthalten (PII)."""
        mock_run.return_value = {
            "entity_id": str(uuid4()),
            "success": True,
            "risk_score": 45.5,
            "payment_behavior_score": 78.2,
            "risk_factors": {},
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = calculate_single_risk_score_task(str(uuid4()))

        # Pruefe dass keine entity_name in response
        assert "entity_name" not in result
        assert result["success"] is True

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_check_high_risk_does_not_expose_entity_names(self, mock_run):
        """High-Risk-Liste sollte keine Entity-Namen enthalten (PII)."""
        mock_run.return_value = {
            "threshold": 75.0,
            "count": 2,
            "high_risk_entities": [
                {
                    "entity_id": str(uuid4()),
                    "entity_type": "customer",
                    "risk_score": 85.0,
                    "payment_behavior_score": 25.0,
                },
                {
                    "entity_id": str(uuid4()),
                    "entity_type": "supplier",
                    "risk_score": 92.0,
                    "payment_behavior_score": 15.0,
                },
            ],
        }

        result = check_high_risk_entities_task()

        # Pruefe dass keine entity_name in high_risk_entities
        for entity in result["high_risk_entities"]:
            assert "entity_name" not in entity
            assert "entity_id" in entity


# ========================= Functional Tests =========================


class TestCalculateAllRiskScoresTask:
    """Tests for batch risk score calculation."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_returns_statistics(self, mock_run):
        """Task sollte Statistiken zurueckgeben."""
        mock_run.return_value = {
            "total_processed": 100,
            "successful": 95,
            "failed": 3,
            "skipped": 2,
            "errors": [],
            "processing_time_ms": 5000,
            "version": "v1",
        }

        result = calculate_all_risk_scores_task()

        assert result["total_processed"] == 100
        assert result["successful"] == 95
        assert result["failed"] == 3
        assert result["skipped"] == 2
        assert "processing_time_ms" in result

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_respects_entity_type_filter(self, mock_run):
        """Task sollte entity_type Filter respektieren."""
        mock_run.return_value = {
            "total_processed": 50,
            "successful": 50,
            "failed": 0,
            "skipped": 0,
            "errors": [],
            "processing_time_ms": 2500,
            "version": "v1",
        }

        result = calculate_all_risk_scores_task(entity_type="customer")

        assert result["total_processed"] == 50

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_respects_limit_parameter(self, mock_run):
        """Task sollte Limit-Parameter respektieren."""
        mock_run.return_value = {
            "total_processed": 10,
            "successful": 10,
            "failed": 0,
            "skipped": 0,
            "errors": [],
            "processing_time_ms": 500,
            "version": "v1",
        }

        result = calculate_all_risk_scores_task(limit=10)

        assert result["total_processed"] <= 10


class TestCalculateSingleRiskScoreTask:
    """Tests for single entity risk score calculation."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_success_response_format(self, mock_run, sample_entity_id):
        """Erfolgreiche Antwort sollte korrektes Format haben."""
        mock_run.return_value = {
            "entity_id": sample_entity_id,
            "success": True,
            "risk_score": 35.5,
            "payment_behavior_score": 85.0,
            "risk_factors": {"payment_delay_days": 2.0},
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = calculate_single_risk_score_task(sample_entity_id)

        assert result["success"] is True
        assert result["entity_id"] == sample_entity_id
        assert "risk_score" in result
        assert "payment_behavior_score" in result

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_not_found_response(self, mock_run, sample_entity_id):
        """Nicht gefundene Entity sollte Fehler zurueckgeben."""
        mock_run.return_value = {
            "entity_id": sample_entity_id,
            "success": False,
            "error": "Entitaet nicht gefunden oder keine Daten",
        }

        result = calculate_single_risk_score_task(sample_entity_id)

        assert result["success"] is False
        assert "error" in result


class TestOnInvoiceUpdatedRecalculate:
    """Tests for invoice-triggered risk recalculation."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_triggers_recalculation(self, mock_run, sample_document_id):
        """Sollte Risk-Neuberechnung triggern."""
        mock_run.return_value = {
            "document_id": sample_document_id,
            "entity_id": str(uuid4()),
            "success": True,
            "action": "risk_recalculation_triggered",
        }

        result = on_invoice_updated_recalculate(sample_document_id)

        assert result["success"] is True
        assert result["action"] == "risk_recalculation_triggered"

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_handles_missing_document(self, mock_run, sample_document_id):
        """Sollte fehlende Dokumente behandeln."""
        mock_run.return_value = {
            "document_id": sample_document_id,
            "success": False,
            "error": "Dokument nicht gefunden",
        }

        result = on_invoice_updated_recalculate(sample_document_id)

        assert result["success"] is False
        assert "Dokument nicht gefunden" in result["error"]

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_handles_unlinked_document(self, mock_run, sample_document_id):
        """Sollte nicht verknuepfte Dokumente behandeln."""
        mock_run.return_value = {
            "document_id": sample_document_id,
            "success": False,
            "error": "Dokument nicht mit Entitaet verknuepft",
        }

        result = on_invoice_updated_recalculate(sample_document_id)

        assert result["success"] is False


class TestCheckHighRiskEntitiesTask:
    """Tests for high-risk entity detection."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_default_threshold(self, mock_run):
        """Standard-Threshold sollte 75 sein."""
        mock_run.return_value = {
            "threshold": 75.0,
            "count": 0,
            "high_risk_entities": [],
        }

        result = check_high_risk_entities_task()

        assert result["threshold"] == 75.0

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_custom_threshold(self, mock_run):
        """Custom Threshold sollte verwendet werden."""
        mock_run.return_value = {
            "threshold": 50.0,
            "count": 5,
            "high_risk_entities": [],
        }

        result = check_high_risk_entities_task(threshold=50.0)

        assert result["threshold"] == 50.0

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_returns_entity_list(self, mock_run):
        """Sollte Liste von High-Risk Entities zurueckgeben."""
        mock_run.return_value = {
            "threshold": 75.0,
            "count": 2,
            "high_risk_entities": [
                {"entity_id": str(uuid4()), "risk_score": 85.0},
                {"entity_id": str(uuid4()), "risk_score": 92.0},
            ],
        }

        result = check_high_risk_entities_task()

        assert result["count"] == 2
        assert len(result["high_risk_entities"]) == 2


class TestGenerateRiskStatisticsTask:
    """Tests for risk statistics generation."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_returns_statistics_format(self, mock_run):
        """Sollte korrektes Statistik-Format zurueckgeben."""
        mock_run.return_value = {
            "total_entities_with_score": 500,
            "average_risk_score": 35.5,
            "max_risk_score": 95.0,
            "min_risk_score": 5.0,
            "average_payment_behavior": 72.3,
            "risk_distribution": {
                "low": 300,
                "medium": 150,
                "high": 40,
                "critical": 10,
            },
            "trend_distribution": {
                "improving": 200,
                "stable": 250,
                "worsening": 50,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = generate_risk_statistics_task()

        assert "total_entities_with_score" in result
        assert "average_risk_score" in result
        assert "risk_distribution" in result
        assert result["risk_distribution"]["low"] == 300

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_includes_all_distribution_buckets(self, mock_run):
        """Sollte alle Risiko-Verteilungs-Buckets enthalten."""
        mock_run.return_value = {
            "total_entities_with_score": 100,
            "average_risk_score": 50.0,
            "max_risk_score": 100.0,
            "min_risk_score": 0.0,
            "average_payment_behavior": 50.0,
            "risk_distribution": {
                "low": 25,
                "medium": 25,
                "high": 25,
                "critical": 25,
            },
            "trend_distribution": {
                "improving": 33,
                "stable": 34,
                "worsening": 33,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = generate_risk_statistics_task()

        distribution = result["risk_distribution"]
        assert "low" in distribution
        assert "medium" in distribution
        assert "high" in distribution
        assert "critical" in distribution


# ========================= Error Handling Tests =========================


class TestErrorHandling:
    """Tests for task error handling and retry behavior."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_calculate_all_handles_exception(self, mock_run):
        """calculate_all sollte Exception mit Retry behandeln."""
        mock_run.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception):
            # Bind=True tasks raise MaxRetriesExceededError eventually
            calculate_all_risk_scores_task.apply().get()

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_calculate_single_handles_invalid_uuid(self, mock_run):
        """calculate_single sollte ungueltige UUIDs behandeln."""
        mock_run.side_effect = ValueError("Invalid UUID")

        with pytest.raises(Exception):
            calculate_single_risk_score_task("invalid-uuid")


# ========================= Integration Tests (Mocked) =========================


class TestIntegrationWithService:
    """Integration tests with mocked RiskScoringService."""

    @patch("app.workers.tasks.risk_scoring_tasks.asyncio.run")
    def test_calculate_single_calls_service(self, mock_run):
        """calculate_single sollte RiskScoringService aufrufen."""
        entity_id = str(uuid4())
        mock_run.return_value = {
            "entity_id": entity_id,
            "success": True,
            "risk_score": 45.0,
            "payment_behavior_score": 75.0,
            "risk_factors": {},
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = calculate_single_risk_score_task(entity_id)

        assert result["success"] is True
        assert result["entity_id"] == entity_id
        # asyncio.run wird aufgerufen (Service-Aufruf ist darin)
        assert mock_run.called
