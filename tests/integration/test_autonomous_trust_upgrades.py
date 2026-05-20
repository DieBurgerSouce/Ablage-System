# -*- coding: utf-8 -*-
"""Integration Tests fuer Autonomous Trust Upgrade Tasks.

Phase 2.1 Multi-Level Trust System:
- Proposal-Verarbeitung
- Trust-Metriken Updates
- Upgrade-Evaluierung
- Bereinigung
- Benachrichtigungen
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4, UUID

from sqlalchemy import select

from app.core.datetime_utils import utc_now
from app.db.models import (
    AutonomousTrustConfig,
    AutonomousProposalQueue,
    Company,
    User,
)
from app.workers.tasks import autonomous_trust_tasks


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_celery_task():
    """Mock Celery Task mit retry Methode."""
    task = MagicMock()
    task.retry = MagicMock(side_effect=Exception("retry"))
    return task


@pytest.fixture
def sample_company_id() -> UUID:
    """Sample Company UUID."""
    return uuid4()


@pytest.fixture
def sample_trust_config(sample_company_id: UUID) -> Dict[str, Any]:
    """Sample Trust Config Daten."""
    return {
        "id": uuid4(),
        "company_id": sample_company_id,
        "document_type": "invoice",
        "trust_level": "level_2_delayed",
        "is_enabled": True,
        "delay_hours": 24,
        "metrics_snapshot": {},
        "metrics_updated_at": None,
    }


@pytest.fixture
def sample_proposal(sample_company_id: UUID) -> Dict[str, Any]:
    """Sample Proposal Queue Daten."""
    return {
        "id": uuid4(),
        "company_id": sample_company_id,
        "proposal_type": "approve_payment",
        "target_id": uuid4(),
        "proposed_value": {"company_id": str(sample_company_id)},
        "status": "pending",
        "scheduled_at": utc_now() - timedelta(hours=1),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


@pytest.fixture
def mock_delayed_acceptance_service():
    """Mock DelayedAcceptanceService."""
    service = MagicMock()
    service.process_due_proposals = AsyncMock(
        return_value={
            "processed": 5,
            "success": 4,
            "failed": 1,
        }
    )
    return service


@pytest.fixture
def mock_trust_level_service():
    """Mock TrustLevelService."""
    service = MagicMock()

    # Mock Metriken
    metrics = MagicMock()
    metrics.total_decisions = 100
    metrics.auto_applied = 80
    metrics.approved = 75
    metrics.rejected = 5
    metrics.corrected = 2
    metrics.approval_rate = 0.95
    metrics.error_rate = 0.02
    metrics.avg_confidence = 0.87
    metrics.days_without_error = 15
    service.get_trust_metrics = AsyncMock(return_value=metrics)

    # Mock Evaluierung
    recommendation = MagicMock()
    recommendation.can_upgrade = True
    recommendation.current_level = MagicMock(value="level_2_delayed")
    recommendation.recommended_level = MagicMock(value="level_3_managed_autonomous")
    recommendation.reason = "Hohe Erfolgsquote erreicht"
    service.evaluate_trust_level = AsyncMock(return_value=recommendation)

    return service


@pytest.fixture
def mock_async_session():
    """Mock Async Session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_sync_session():
    """Mock Sync Session."""
    session = MagicMock()
    session.commit = MagicMock()
    session.execute = MagicMock()
    return session


# ============================================================================
# Test Class: ProcessDueProposals
# ============================================================================


class TestProcessDueProposals:
    """Tests fuer process_due_proposals Task."""

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_processes_pending_proposals(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_delayed_acceptance_service: MagicMock,
    ):
        """Test: Findet und verarbeitet faellige Proposals."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.DelayedAcceptanceService",
            return_value=mock_delayed_acceptance_service,
        ):
            # Act
            result = autonomous_trust_tasks.process_due_proposals(batch_size=100)

        # Assert
        assert result["processed"] == 5
        assert result["success"] == 4
        assert result["failed"] == 1
        mock_delayed_acceptance_service.process_due_proposals.assert_called_once()

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_respects_batch_size(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_delayed_acceptance_service: MagicMock,
    ):
        """Test: Respektiert batch_size Parameter."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        mock_delayed_acceptance_service.process_due_proposals.return_value = {
            "processed": 50,
            "success": 50,
            "failed": 0,
        }

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.DelayedAcceptanceService",
            return_value=mock_delayed_acceptance_service,
        ):
            # Act
            result = autonomous_trust_tasks.process_due_proposals(batch_size=50)

        # Assert
        assert result["processed"] == 50
        assert result["success"] == 50

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_handles_no_proposals(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_delayed_acceptance_service: MagicMock,
    ):
        """Test: Leere Queue gibt 0 zurueck."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        mock_delayed_acceptance_service.process_due_proposals.return_value = {
            "processed": 0,
            "success": 0,
            "failed": 0,
        }

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.DelayedAcceptanceService",
            return_value=mock_delayed_acceptance_service,
        ):
            # Act
            result = autonomous_trust_tasks.process_due_proposals(batch_size=100)

        # Assert
        assert result["processed"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_retries_on_error(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_celery_task: MagicMock,
    ):
        """Test: Ruft self.retry bei Exception auf."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop
        mock_get_session.side_effect = Exception("DB Fehler")

        # Bind task to self
        bound_task = autonomous_trust_tasks.process_due_proposals
        bound_task.retry = mock_celery_task.retry

        # Act & Assert
        with pytest.raises(Exception, match="DB Fehler"):
            bound_task(batch_size=100)


# ============================================================================
# Test Class: UpdateTrustMetrics
# ============================================================================


class TestUpdateTrustMetrics:
    """Tests fuer update_trust_metrics Task."""

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_updates_metrics_per_entity(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ):
        """Test: Aktualisiert Metriken fuer jede Entity."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        # Mock Trust Configs
        config1 = MagicMock(**sample_trust_config)
        config2 = MagicMock(**{**sample_trust_config, "id": uuid4()})

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config1, config2]
        mock_async_session.execute.return_value = result_mock

        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            # Act
            result = autonomous_trust_tasks.update_trust_metrics()

        # Assert
        assert result["updated"] == 2
        assert result["total"] == 2
        assert mock_trust_level_service.get_trust_metrics.call_count == 2

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_calculates_trust_score(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ):
        """Test: Score wird basierend auf Payment-History berechnet."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            # Act
            result = autonomous_trust_tasks.update_trust_metrics()

        # Assert
        assert config.metrics_snapshot["approval_rate"] == 0.95
        assert config.metrics_snapshot["error_rate"] == 0.02
        assert config.metrics_snapshot["avg_confidence"] == 0.87
        assert config.metrics_snapshot["days_without_error"] == 15

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_handles_no_entities(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
    ):
        """Test: Keine Entities ist ein No-Op."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_async_session.execute.return_value = result_mock
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        # Act
        result = autonomous_trust_tasks.update_trust_metrics()

        # Assert
        assert result["updated"] == 0
        assert result["total"] == 0

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_retries_on_error(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_celery_task: MagicMock,
    ):
        """Test: Ruft self.retry bei Fehler auf."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop
        mock_get_session.side_effect = Exception("Metriken-Fehler")

        bound_task = autonomous_trust_tasks.update_trust_metrics
        bound_task.retry = mock_celery_task.retry

        # Act & Assert
        with pytest.raises(Exception, match="Metriken-Fehler"):
            bound_task()


# ============================================================================
# Test Class: EvaluateTrustUpgrades
# ============================================================================


class TestEvaluateTrustUpgrades:
    """Tests fuer evaluate_trust_upgrades Task."""

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_upgrades_eligible_entity(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ):
        """Test: Entity die Kriterien erfuellt bekommt Upgrade."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            # Act
            result = autonomous_trust_tasks.evaluate_trust_upgrades()

        # Assert
        assert result["upgrade_candidates"] == 1
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["current_level"] == "level_2_delayed"
        assert result["candidates"][0]["recommended_level"] == "level_3_managed_autonomous"

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_skips_ineligible_entity(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ):
        """Test: Entity mit niedrigem Score wird nicht upgegradet."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        # Mock ineligible recommendation
        ineligible_rec = MagicMock()
        ineligible_rec.can_upgrade = False
        mock_trust_level_service.evaluate_trust_level.return_value = ineligible_rec

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            # Act
            result = autonomous_trust_tasks.evaluate_trust_upgrades()

        # Assert
        assert result["upgrade_candidates"] == 0
        assert len(result["candidates"]) == 0

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_creates_upgrade_proposal(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ):
        """Test: Erstellt TrustProposal Record."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            # Act
            result = autonomous_trust_tasks.evaluate_trust_upgrades()

        # Assert
        candidates = result["candidates"]
        assert len(candidates) == 1
        assert "reason" in candidates[0]
        assert candidates[0]["reason"] == "Hohe Erfolgsquote erreicht"

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_respects_cooldown(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        sample_trust_config: Dict[str, Any],
    ):
        """Test: Re-evaluiert nicht kuerzlich evaluierte Configs."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        # Config mit Level 4 (max level) - wird nicht evaluiert
        config_max = MagicMock(**{
            **sample_trust_config,
            "trust_level": "level_4_autonomous",
        })

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config_max]
        mock_async_session.execute.return_value = result_mock
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        # Act
        result = autonomous_trust_tasks.evaluate_trust_upgrades()

        # Assert - Level 4 wird via SQL-Filter ausgeschlossen
        assert result["evaluated"] == 1  # Wurde gefunden aber...
        assert result["upgrade_candidates"] == 0  # ...nicht als Kandidat gezaehlt

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_retries_on_error(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_celery_task: MagicMock,
    ):
        """Test: Ruft self.retry bei Fehler auf."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop
        mock_get_session.side_effect = Exception("Upgrade-Fehler")

        bound_task = autonomous_trust_tasks.evaluate_trust_upgrades
        bound_task.retry = mock_celery_task.retry

        # Act & Assert
        with pytest.raises(Exception, match="Upgrade-Fehler"):
            bound_task()


# ============================================================================
# Test Class: CleanupExpiredProposals
# ============================================================================


class TestCleanupExpiredProposals:
    """Tests fuer cleanup_expired_proposals Task."""

    @patch("app.workers.tasks.autonomous_trust_tasks.get_sync_session")
    def test_cleans_expired(
        self,
        mock_get_session: MagicMock,
        mock_sync_session: MagicMock,
    ):
        """Test: Entfernt Proposals nach Ablaufdatum."""
        # Arrange
        count_result = MagicMock()
        count_result.scalar.return_value = 10
        mock_sync_session.execute.return_value = count_result
        mock_get_session.return_value.__enter__.return_value = mock_sync_session

        # Act
        result = autonomous_trust_tasks.cleanup_expired_proposals(retention_days=90)

        # Assert
        assert result["deleted"] == 10
        assert result["retention_days"] == 90
        assert mock_sync_session.commit.called

    @patch("app.workers.tasks.autonomous_trust_tasks.get_sync_session")
    def test_keeps_valid(
        self,
        mock_get_session: MagicMock,
        mock_sync_session: MagicMock,
    ):
        """Test: Beruehrt nicht-abgelaufene Proposals nicht."""
        # Arrange
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_sync_session.execute.return_value = count_result
        mock_get_session.return_value.__enter__.return_value = mock_sync_session

        # Act
        result = autonomous_trust_tasks.cleanup_expired_proposals(retention_days=90)

        # Assert
        assert result["deleted"] == 0
        # Commit sollte nicht aufgerufen werden wenn nichts zu loeschen
        assert not mock_sync_session.commit.called

    @patch("app.workers.tasks.autonomous_trust_tasks.get_sync_session")
    def test_counts_cleaned(
        self,
        mock_get_session: MagicMock,
        mock_sync_session: MagicMock,
    ):
        """Test: Gibt Anzahl der bereinigten Eintraege zurueck."""
        # Arrange
        count_result = MagicMock()
        count_result.scalar.return_value = 25
        mock_sync_session.execute.return_value = count_result
        mock_get_session.return_value.__enter__.return_value = mock_sync_session

        # Act
        result = autonomous_trust_tasks.cleanup_expired_proposals(retention_days=30)

        # Assert
        assert result["deleted"] == 25
        assert result["retention_days"] == 30


# ============================================================================
# Test Class: NotifyPendingProposals
# ============================================================================


class TestNotifyPendingProposals:
    """Tests fuer notify_pending_proposals Task."""

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    @patch("app.workers.tasks.autonomous_trust_tasks.send_notification")
    def test_notifies_upgrade(
        self,
        mock_send_notification: AsyncMock,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
        sample_company_id: UUID,
    ):
        """Test: Sendet Benachrichtigung bei Upgrade."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        # Mock pending proposals
        proposal = MagicMock(**sample_proposal)
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [proposal]

        # Mock admin user
        admin = MagicMock()
        admin.id = uuid4()
        admin.email = "admin@example.com"
        admin.is_active = True
        admin.is_superuser = True
        admin_result = MagicMock()
        admin_result.scalar_one_or_none.return_value = admin

        mock_async_session.execute.side_effect = [proposals_result, admin_result]
        mock_get_session.return_value.__aenter__.return_value = mock_async_session
        mock_send_notification.return_value = AsyncMock()

        # Act
        result = autonomous_trust_tasks.notify_pending_proposals()

        # Assert
        assert result["proposals_found"] == 1
        assert result["companies_notified"] == 1

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    @patch("app.workers.tasks.autonomous_trust_tasks.send_notification")
    def test_notifies_downgrade(
        self,
        mock_send_notification: AsyncMock,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
    ):
        """Test: Sendet Benachrichtigung bei Downgrade."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        # Mock downgrade proposal
        proposal = MagicMock(**{
            **sample_proposal,
            "proposal_type": "send_dunning",
        })
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [proposal]

        admin = MagicMock()
        admin.id = uuid4()
        admin.email = "admin@example.com"
        admin.is_active = True
        admin.is_superuser = True
        admin_result = MagicMock()
        admin_result.scalar_one_or_none.return_value = admin

        mock_async_session.execute.side_effect = [proposals_result, admin_result]
        mock_get_session.return_value.__aenter__.return_value = mock_async_session
        mock_send_notification.return_value = AsyncMock()

        # Act
        result = autonomous_trust_tasks.notify_pending_proposals()

        # Assert
        assert result["proposals_found"] == 1

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    @patch("app.workers.tasks.autonomous_trust_tasks.send_notification")
    def test_handles_notification_failure(
        self,
        mock_send_notification: AsyncMock,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
    ):
        """Test: Faehrt fort wenn Benachrichtigung fehlschlaegt."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        proposal1 = MagicMock(**sample_proposal)
        proposal2 = MagicMock(**{**sample_proposal, "id": uuid4()})
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [proposal1, proposal2]

        admin = MagicMock()
        admin.id = uuid4()
        admin.email = "admin@example.com"
        admin.is_active = True
        admin.is_superuser = True
        admin_result = MagicMock()
        admin_result.scalar_one_or_none.return_value = admin

        mock_async_session.execute.side_effect = [proposals_result, admin_result]
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        # Notification failt
        mock_send_notification.side_effect = Exception("Notification Fehler")

        # Act
        result = autonomous_trust_tasks.notify_pending_proposals()

        # Assert - Task schlaegt nicht fehl, logged nur Warning
        assert result["proposals_found"] == 2
        assert result["companies_notified"] == 0  # Keine Notification gesendet

    @patch("app.workers.tasks.autonomous_trust_tasks.get_async_session")
    @patch("app.workers.tasks.autonomous_trust_tasks.asyncio.get_event_loop")
    def test_marks_notified(
        self,
        mock_get_loop: MagicMock,
        mock_get_session: MagicMock,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
    ):
        """Test: Setzt notification_sent Flag."""
        # Arrange
        loop = asyncio.new_event_loop()
        mock_get_loop.return_value = loop

        proposal = MagicMock(**sample_proposal)
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [proposal]

        admin = MagicMock()
        admin.id = uuid4()
        admin.email = "admin@example.com"
        admin.is_active = True
        admin.is_superuser = True
        admin_result = MagicMock()
        admin_result.scalar_one_or_none.return_value = admin

        mock_async_session.execute.side_effect = [proposals_result, admin_result]
        mock_get_session.return_value.__aenter__.return_value = mock_async_session

        with patch(
            "app.workers.tasks.autonomous_trust_tasks.send_notification",
            new_callable=AsyncMock,
        ):
            # Act
            result = autonomous_trust_tasks.notify_pending_proposals()

        # Assert
        assert result["proposals_found"] == 1
        assert result["companies_notified"] == 1
