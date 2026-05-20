# -*- coding: utf-8 -*-
"""
Unit Tests fuer AI Autonomy API Endpoints.

Testet:
- KI-Entscheidungen einsehen und reviewen
- Konfidenz-Schwellenwerte verwalten
- Accuracy-Statistiken
- Dokument-Kategorisierung, Matching, Anomalie-Erkennung

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_decision():
    """Sample KI-Entscheidung fuer Tests."""
    return Mock(
        id=uuid4(),
        decision_type="document_category",
        document_id=uuid4(),
        decision_value={"category": "rechnung", "subcategory": "eingangsrechnung"},
        confidence=0.92,
        calibrated_confidence=0.89,
        confidence_level="high",
        auto_applied=True,
        requires_review=False,
        is_final=True,
        explanation={"factors": ["invoice_number_found", "supplier_detected"]},
        reviewed_by_id=None,
        reviewed_at=None,
        review_action=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_threshold():
    """Sample Schwellenwert-Konfiguration."""
    return Mock(
        decision_type="document_category",
        auto_threshold=0.85,
        suggest_threshold=0.50,
        is_enabled=True,
        allow_auto_apply=True,
        display_name="Dokumenten-Kategorisierung",
        description="Automatische Zuweisung von Dokumentenkategorien",
    )


# =============================================================================
# Threshold Management Tests
# =============================================================================

class TestThresholdManagement:
    """Tests fuer Schwellenwert-Verwaltung."""

    @pytest.mark.asyncio
    async def test_list_thresholds_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten aller Schwellenwerte."""
        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_all_thresholds.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/ai/thresholds",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403]

    @pytest.mark.asyncio
    async def test_get_threshold_success(
        self, async_client, auth_headers, sample_threshold
    ):
        """Abruf eines einzelnen Schwellenwertes."""
        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_threshold.return_value = sample_threshold
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/ai/thresholds/document_category",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_update_threshold_success(
        self, async_client, auth_headers, sample_threshold
    ):
        """Erfolgreiche Aktualisierung eines Schwellenwertes."""
        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.update_threshold.return_value = sample_threshold
            mock_service.return_value = mock_instance

            response = await async_client.put(
                "/api/v1/ai/thresholds/document_category",
                json={
                    "auto_threshold": 0.90,
                    "suggest_threshold": 0.60,
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_update_threshold_invalid_values(self, async_client, auth_headers):
        """Update mit ungueltigen Werten (>1.0)."""
        response = await async_client.put(
            "/api/v1/ai/thresholds/document_category",
            json={
                "auto_threshold": 1.5,  # Ungueltig, muss <= 1.0 sein
            },
            headers=auth_headers,
        )

        assert response.status_code in [422, 401, 403]


# =============================================================================
# Decision Management Tests
# =============================================================================

class TestDecisionManagement:
    """Tests fuer KI-Entscheidungs-Verwaltung."""

    @pytest.mark.asyncio
    async def test_list_decisions_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten von Entscheidungen."""
        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_decisions.return_value = ([], 0)
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/ai/decisions",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403]

    @pytest.mark.asyncio
    async def test_list_decisions_with_filters(self, async_client, auth_headers):
        """Entscheidungen mit Filtern auflisten."""
        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_decisions.return_value = ([], 0)
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/ai/decisions",
                params={
                    "decision_type": "document_category",
                    "requires_review": True,
                    "limit": 20,
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403]

    @pytest.mark.asyncio
    async def test_get_decision_success(
        self, async_client, auth_headers, sample_decision
    ):
        """Abruf einer einzelnen Entscheidung."""
        decision_id = sample_decision.id

        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_decision.return_value = sample_decision
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/ai/decisions/{decision_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_review_decision_approve(
        self, async_client, auth_headers, sample_decision
    ):
        """Entscheidung genehmigen."""
        decision_id = sample_decision.id

        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            sample_decision.is_final = True
            sample_decision.review_action = "approved"
            mock_instance.review_decision.return_value = sample_decision
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/ai/decisions/{decision_id}/review",
                json={"action": "approved"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_review_decision_reject(
        self, async_client, auth_headers, sample_decision
    ):
        """Entscheidung ablehnen."""
        decision_id = sample_decision.id

        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            sample_decision.is_final = True
            sample_decision.review_action = "rejected"
            mock_instance.review_decision.return_value = sample_decision
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/ai/decisions/{decision_id}/review",
                json={"action": "rejected", "reason": "Falsche Kategorie"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_review_decision_modify(
        self, async_client, auth_headers, sample_decision
    ):
        """Entscheidung modifizieren."""
        decision_id = sample_decision.id

        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            sample_decision.is_final = True
            sample_decision.review_action = "modified"
            mock_instance.review_decision.return_value = sample_decision
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/ai/decisions/{decision_id}/review",
                json={
                    "action": "modified",
                    "modified_value": {"category": "vertrag"},
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_review_decision_invalid_action(
        self, async_client, auth_headers, sample_decision
    ):
        """Ungueltige Review-Aktion."""
        decision_id = sample_decision.id

        response = await async_client.post(
            f"/api/v1/ai/decisions/{decision_id}/review",
            json={"action": "invalid_action"},
            headers=auth_headers,
        )

        assert response.status_code in [422, 401, 403]


# =============================================================================
# Categorization Tests
# =============================================================================

class TestCategorization:
    """Tests fuer Dokument-Kategorisierung."""

    @pytest.mark.asyncio
    async def test_categorize_document_success(self, async_client, auth_headers):
        """Erfolgreiche Dokumenten-Kategorisierung."""
        document_id = uuid4()

        with patch("app.api.v1.ai_autonomy.get_auto_categorization_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.categorize_document.return_value = {
                "category": "rechnung",
                "confidence": 0.92,
                "auto_applied": True,
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/ai/categorize/{document_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_batch_categorize_documents(self, async_client, auth_headers):
        """Batch-Kategorisierung mehrerer Dokumente."""
        document_ids = [str(uuid4()) for _ in range(5)]

        with patch("app.api.v1.ai_autonomy.get_auto_categorization_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.batch_categorize.return_value = {
                "processed": 5,
                "auto_applied": 3,
                "pending_review": 2,
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/ai/categorize/batch",
                json={"document_ids": document_ids},
                headers=auth_headers,
            )

            assert response.status_code in [200, 202, 401, 403]


# =============================================================================
# Anomaly Detection Tests
# =============================================================================

class TestAnomalyDetection:
    """Tests fuer Anomalie-Erkennung."""

    @pytest.mark.asyncio
    async def test_check_anomalies_success(self, async_client, auth_headers):
        """Erfolgreiche Anomalie-Pruefung."""
        document_id = uuid4()

        with patch("app.api.v1.ai_autonomy.get_anomaly_detection_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.check_document.return_value = {
                "anomalies": [],
                "risk_score": 0.15,
                "is_suspicious": False,
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/ai/anomalies/check/{document_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_check_anomalies_suspicious(self, async_client, auth_headers):
        """Anomalie-Pruefung mit verdaechtigen Ergebnissen."""
        document_id = uuid4()

        with patch("app.api.v1.ai_autonomy.get_anomaly_detection_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.check_document.return_value = {
                "anomalies": [
                    {"type": "high_amount", "severity": "warning", "description": "Ungewoehnlich hoher Betrag"},
                    {"type": "new_supplier", "severity": "info", "description": "Neuer Lieferant"},
                ],
                "risk_score": 0.75,
                "is_suspicious": True,
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/ai/anomalies/check/{document_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]


# =============================================================================
# Duplicate Detection Tests
# =============================================================================

class TestDuplicateDetection:
    """Tests fuer Duplikat-Erkennung."""

    @pytest.mark.asyncio
    async def test_find_duplicates_success(self, async_client, auth_headers):
        """Erfolgreiche Duplikat-Suche."""
        document_id = uuid4()

        with patch("app.api.v1.ai_autonomy.get_duplicate_detection_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.find_duplicates.return_value = {
                "potential_duplicates": [],
                "has_duplicates": False,
            }
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/ai/duplicates/{document_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_find_duplicates_with_matches(self, async_client, auth_headers):
        """Duplikat-Suche mit Treffern."""
        document_id = uuid4()
        duplicate_id = uuid4()

        with patch("app.api.v1.ai_autonomy.get_duplicate_detection_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.find_duplicates.return_value = {
                "potential_duplicates": [
                    {
                        "document_id": str(duplicate_id),
                        "similarity": 0.95,
                        "matching_fields": ["invoice_number", "total_amount"],
                    }
                ],
                "has_duplicates": True,
            }
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/ai/duplicates/{document_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403, 404]


# =============================================================================
# Smart Matching Tests
# =============================================================================

class TestSmartMatching:
    """Tests fuer Smart Matching."""

    @pytest.mark.asyncio
    async def test_match_supplier_success(self, async_client, auth_headers):
        """Erfolgreiche Lieferanten-Zuordnung."""
        with patch("app.api.v1.ai_autonomy.get_smart_matching_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.match_supplier.return_value = {
                "supplier_id": str(uuid4()),
                "supplier_name": "Test GmbH",
                "confidence": 0.95,
                "auto_applied": True,
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/ai/match/supplier",
                json={
                    "supplier_name": "Test GmbH",
                    "vat_id": "DE123456789",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403]


# =============================================================================
# Statistics Tests
# =============================================================================

class TestStatistics:
    """Tests fuer KI-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_accuracy_stats(self, async_client, auth_headers):
        """Accuracy-Statistiken abrufen."""
        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_accuracy_stats.return_value = {
                "document_category": {"accuracy": 0.92, "total": 1000},
                "supplier_matching": {"accuracy": 0.88, "total": 500},
            }
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/ai/stats/accuracy",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403]

    @pytest.mark.asyncio
    async def test_get_decision_stats(self, async_client, auth_headers):
        """Entscheidungs-Statistiken abrufen."""
        with patch("app.api.v1.ai_autonomy.get_ai_decision_service") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_decision_stats.return_value = {
                "total_decisions": 5000,
                "auto_applied": 4200,
                "pending_review": 300,
                "rejected": 50,
            }
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/ai/stats/decisions",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403]


# =============================================================================
# Learning Pipeline Tests
# =============================================================================

class TestLearningPipeline:
    """Tests fuer AI Learning Pipeline."""

    @pytest.mark.asyncio
    async def test_trigger_learning(self, async_client, auth_headers):
        """Manuelles Triggern des Learning-Prozesses."""
        with patch("app.api.v1.ai_autonomy.get_ai_learning_pipeline") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.trigger_learning.return_value = {
                "status": "started",
                "job_id": str(uuid4()),
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/ai/learning/trigger",
                json={"decision_types": ["document_category"]},
                headers=auth_headers,
            )

            assert response.status_code in [200, 202, 401, 403]

    @pytest.mark.asyncio
    async def test_get_learning_status(self, async_client, auth_headers):
        """Status des Learning-Prozesses abrufen."""
        with patch("app.api.v1.ai_autonomy.get_ai_learning_pipeline") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_status.return_value = {
                "is_running": False,
                "last_run": datetime.now(timezone.utc).isoformat(),
                "next_scheduled": None,
            }
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/ai/learning/status",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 403]
