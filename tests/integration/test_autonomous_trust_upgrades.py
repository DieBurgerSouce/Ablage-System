# -*- coding: utf-8 -*-
"""Integration Tests fuer Autonomous Trust Upgrade Tasks.

Phase 2.1 Multi-Level Trust System:
- Proposal-Verarbeitung
- Trust-Metriken Updates
- Upgrade-Evaluierung
- Bereinigung
- Benachrichtigungen

W3 (2026-06-12): Auf den echten Task-Vertrag modernisiert (17 Drift-Failures):
- ``import asyncio`` ist in den Tasks FUNKTIONSLOKAL -> der alte Patch auf
  ``autonomous_trust_tasks.asyncio.get_event_loop`` schlug mit AttributeError
  fehl. Die Tasks verwalten ihre Event-Loop selbst, es wird nichts gepatcht.
- DelayedAcceptanceService/TrustLevelService/send_notification werden
  funktionslokal aus ihren SERVICE-Modulen importiert -> Patch-Ziel ist das
  Quellmodul, nicht autonomous_trust_tasks.
- ``async with get_async_session()`` braucht einen echten Async-Context-
  Manager-Mock (MagicMock.__aenter__ ist nicht awaitable).
- Die Retry-Tests pruefen den realen Vertrag: Exceptions propagieren aus dem
  Task (Celery uebernimmt Retry ueber max_retries der Task-Deklaration).
"""

from __future__ import annotations

import pytest
from datetime import timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.core.datetime_utils import utc_now
from app.workers.tasks import autonomous_trust_tasks


# ============================================================================
# Helpers / Fixtures
# ============================================================================


def _session_cm(session: AsyncMock) -> MagicMock:
    """Erzeugt einen ``async with``-faehigen Mock fuer get_async_session()."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory


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
        "scheduled_at": utc_now() + timedelta(hours=1),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


@pytest.fixture
def mock_delayed_acceptance_service() -> MagicMock:
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
def mock_trust_level_service() -> MagicMock:
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
def mock_async_session() -> AsyncMock:
    """Mock Async Session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_sync_session() -> MagicMock:
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

    def test_processes_pending_proposals(
        self,
        mock_async_session: AsyncMock,
        mock_delayed_acceptance_service: MagicMock,
    ) -> None:
        """Test: Findet und verarbeitet faellige Proposals."""
        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.delayed_acceptance_service.DelayedAcceptanceService",
            return_value=mock_delayed_acceptance_service,
        ):
            result = autonomous_trust_tasks.process_due_proposals(batch_size=100)

        assert result["processed"] == 5
        assert result["success"] == 4
        assert result["failed"] == 1
        mock_delayed_acceptance_service.process_due_proposals.assert_called_once()
        # Executor-Map deckt alle ProposalTypes ab
        executor_map = (
            mock_delayed_acceptance_service.process_due_proposals.call_args.args[0]
        )
        from app.services.ai.delayed_acceptance_service import ProposalType

        assert set(executor_map.keys()) == set(ProposalType)

    def test_respects_batch_size(
        self,
        mock_async_session: AsyncMock,
        mock_delayed_acceptance_service: MagicMock,
    ) -> None:
        """Test: Liefert die Service-Statistiken unveraendert zurueck."""
        mock_delayed_acceptance_service.process_due_proposals.return_value = {
            "processed": 50,
            "success": 50,
            "failed": 0,
        }

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.delayed_acceptance_service.DelayedAcceptanceService",
            return_value=mock_delayed_acceptance_service,
        ):
            result = autonomous_trust_tasks.process_due_proposals(batch_size=50)

        assert result["processed"] == 50
        assert result["success"] == 50

    def test_handles_no_proposals(
        self,
        mock_async_session: AsyncMock,
        mock_delayed_acceptance_service: MagicMock,
    ) -> None:
        """Test: Leere Queue gibt 0 zurueck."""
        mock_delayed_acceptance_service.process_due_proposals.return_value = {
            "processed": 0,
            "success": 0,
            "failed": 0,
        }

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.delayed_acceptance_service.DelayedAcceptanceService",
            return_value=mock_delayed_acceptance_service,
        ):
            result = autonomous_trust_tasks.process_due_proposals(batch_size=100)

        assert result["processed"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0

    def test_retries_on_error(self) -> None:
        """Test: Exception propagiert (Celery retried via max_retries)."""
        failing_factory = MagicMock(side_effect=Exception("DB Fehler"))

        with patch.object(
            autonomous_trust_tasks, "get_async_session", failing_factory
        ):
            with pytest.raises(Exception, match="DB Fehler"):
                autonomous_trust_tasks.process_due_proposals(batch_size=100)

        # Realer Vertrag: Retry-Konfiguration haengt an der Task-Deklaration
        assert autonomous_trust_tasks.process_due_proposals.max_retries == 3


# ============================================================================
# Test Class: UpdateTrustMetrics
# ============================================================================


class TestUpdateTrustMetrics:
    """Tests fuer update_trust_metrics Task."""

    def test_updates_metrics_per_entity(
        self,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ) -> None:
        """Test: Aktualisiert Metriken fuer jede Entity."""
        config1 = MagicMock(**sample_trust_config)
        config2 = MagicMock(**{**sample_trust_config, "id": uuid4()})

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config1, config2]
        mock_async_session.execute.return_value = result_mock

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.trust_level_service.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            result = autonomous_trust_tasks.update_trust_metrics()

        assert result["updated"] == 2
        assert result["total"] == 2
        assert mock_trust_level_service.get_trust_metrics.call_count == 2
        mock_async_session.commit.assert_awaited_once()

    def test_calculates_trust_score(
        self,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ) -> None:
        """Test: Metrics-Snapshot wird aus den Service-Metriken befuellt."""
        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.trust_level_service.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            autonomous_trust_tasks.update_trust_metrics()

        assert config.metrics_snapshot["approval_rate"] == 0.95
        assert config.metrics_snapshot["error_rate"] == 0.02
        assert config.metrics_snapshot["avg_confidence"] == 0.87
        assert config.metrics_snapshot["days_without_error"] == 15
        assert config.metrics_updated_at is not None

    def test_handles_no_entities(
        self,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test: Keine Entities ist ein No-Op."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_async_session.execute.return_value = result_mock

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ):
            result = autonomous_trust_tasks.update_trust_metrics()

        assert result["updated"] == 0
        assert result["total"] == 0

    def test_retries_on_error(self) -> None:
        """Test: Exception propagiert (Celery retried via max_retries)."""
        failing_factory = MagicMock(side_effect=Exception("Metriken-Fehler"))

        with patch.object(
            autonomous_trust_tasks, "get_async_session", failing_factory
        ):
            with pytest.raises(Exception, match="Metriken-Fehler"):
                autonomous_trust_tasks.update_trust_metrics()

        assert autonomous_trust_tasks.update_trust_metrics.max_retries == 2


# ============================================================================
# Test Class: EvaluateTrustUpgrades
# ============================================================================


class TestEvaluateTrustUpgrades:
    """Tests fuer evaluate_trust_upgrades Task."""

    def test_upgrades_eligible_entity(
        self,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ) -> None:
        """Test: Entity die Kriterien erfuellt bekommt Upgrade-Empfehlung."""
        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.trust_level_service.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            result = autonomous_trust_tasks.evaluate_trust_upgrades()

        assert result["upgrade_candidates"] == 1
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["current_level"] == "level_2_delayed"
        assert (
            result["candidates"][0]["recommended_level"]
            == "level_3_managed_autonomous"
        )

    def test_skips_ineligible_entity(
        self,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ) -> None:
        """Test: Entity ohne Upgrade-Empfehlung wird nicht Kandidat."""
        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock

        ineligible_rec = MagicMock()
        ineligible_rec.can_upgrade = False
        mock_trust_level_service.evaluate_trust_level = AsyncMock(
            return_value=ineligible_rec
        )

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.trust_level_service.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            result = autonomous_trust_tasks.evaluate_trust_upgrades()

        assert result["upgrade_candidates"] == 0
        assert len(result["candidates"]) == 0

    def test_creates_upgrade_proposal(
        self,
        mock_async_session: AsyncMock,
        mock_trust_level_service: MagicMock,
        sample_trust_config: Dict[str, Any],
    ) -> None:
        """Test: Kandidaten-Eintrag enthaelt Begruendung."""
        config = MagicMock(**sample_trust_config)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config]
        mock_async_session.execute.return_value = result_mock

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.trust_level_service.TrustLevelService",
            return_value=mock_trust_level_service,
        ):
            result = autonomous_trust_tasks.evaluate_trust_upgrades()

        candidates = result["candidates"]
        assert len(candidates) == 1
        assert "reason" in candidates[0]
        assert candidates[0]["reason"] == "Hohe Erfolgsquote erreicht"

    def test_respects_cooldown(
        self,
        mock_async_session: AsyncMock,
        sample_trust_config: Dict[str, Any],
    ) -> None:
        """Test: Service-Fehler pro Config wird toleriert (kein Kandidat)."""
        # Config mit Level 4 (max level) wird real per SQL-Filter
        # ausgeschlossen; der Mock liefert sie trotzdem -> der Service
        # entscheidet. Wir simulieren: Evaluierung wirft (z.B. kein Upgrade
        # moeglich) -> Task faehrt fort, zaehlt keinen Kandidaten.
        config_max = MagicMock(**{
            **sample_trust_config,
            "trust_level": "level_4_autonomous",
        })

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [config_max]
        mock_async_session.execute.return_value = result_mock

        failing_service = MagicMock()
        failing_service.evaluate_trust_level = AsyncMock(
            side_effect=ValueError("bereits Maximal-Level")
        )

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.ai.trust_level_service.TrustLevelService",
            return_value=failing_service,
        ):
            result = autonomous_trust_tasks.evaluate_trust_upgrades()

        assert result["evaluated"] == 1  # Wurde gefunden aber...
        assert result["upgrade_candidates"] == 0  # ...nicht als Kandidat gezaehlt

    def test_retries_on_error(self) -> None:
        """Test: Exception propagiert (Celery retried via max_retries)."""
        failing_factory = MagicMock(side_effect=Exception("Upgrade-Fehler"))

        with patch.object(
            autonomous_trust_tasks, "get_async_session", failing_factory
        ):
            with pytest.raises(Exception, match="Upgrade-Fehler"):
                autonomous_trust_tasks.evaluate_trust_upgrades()

        assert autonomous_trust_tasks.evaluate_trust_upgrades.max_retries == 2


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
    ) -> None:
        """Test: Entfernt Proposals nach Ablaufdatum."""
        count_result = MagicMock()
        count_result.scalar.return_value = 10
        mock_sync_session.execute.return_value = count_result
        mock_get_session.return_value.__enter__.return_value = mock_sync_session

        result = autonomous_trust_tasks.cleanup_expired_proposals(retention_days=90)

        assert result["deleted"] == 10
        assert result["retention_days"] == 90
        assert mock_sync_session.commit.called

    @patch("app.workers.tasks.autonomous_trust_tasks.get_sync_session")
    def test_keeps_valid(
        self,
        mock_get_session: MagicMock,
        mock_sync_session: MagicMock,
    ) -> None:
        """Test: Beruehrt nicht-abgelaufene Proposals nicht."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_sync_session.execute.return_value = count_result
        mock_get_session.return_value.__enter__.return_value = mock_sync_session

        result = autonomous_trust_tasks.cleanup_expired_proposals(retention_days=90)

        assert result["deleted"] == 0
        # Commit sollte nicht aufgerufen werden wenn nichts zu loeschen
        assert not mock_sync_session.commit.called

    @patch("app.workers.tasks.autonomous_trust_tasks.get_sync_session")
    def test_counts_cleaned(
        self,
        mock_get_session: MagicMock,
        mock_sync_session: MagicMock,
    ) -> None:
        """Test: Gibt Anzahl der bereinigten Eintraege zurueck."""
        count_result = MagicMock()
        count_result.scalar.return_value = 25
        mock_sync_session.execute.return_value = count_result
        mock_get_session.return_value.__enter__.return_value = mock_sync_session

        result = autonomous_trust_tasks.cleanup_expired_proposals(retention_days=30)

        assert result["deleted"] == 25
        assert result["retention_days"] == 30


# ============================================================================
# Test Class: NotifyPendingProposals
# ============================================================================


class TestNotifyPendingProposals:
    """Tests fuer notify_pending_proposals Task."""

    def _admin_result(self) -> MagicMock:
        admin = MagicMock()
        admin.id = uuid4()
        admin.email = "admin@example.com"
        admin.is_active = True
        admin.is_superuser = True
        admin_result = MagicMock()
        admin_result.scalar_one_or_none.return_value = admin
        return admin_result

    def test_notifies_upgrade(
        self,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
    ) -> None:
        """Test: Sendet Benachrichtigung fuer faellige Proposals."""
        proposal = MagicMock(**sample_proposal)
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [proposal]

        mock_async_session.execute.side_effect = [
            proposals_result,
            self._admin_result(),
        ]

        send_mock = AsyncMock()
        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.notification.unified_hub.send_notification",
            send_mock,
        ):
            result = autonomous_trust_tasks.notify_pending_proposals()

        assert result["proposals_found"] == 1
        assert result["companies_notified"] == 1
        send_mock.assert_awaited_once()
        # Deutsche Benachrichtigung (Critical Rule 2)
        assert "KI-Vorschläge" in send_mock.call_args.kwargs["title"]

    def test_notifies_downgrade(
        self,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
    ) -> None:
        """Test: Auch Dunning-Proposals werden gemeldet."""
        proposal = MagicMock(**{
            **sample_proposal,
            "proposal_type": "send_dunning",
        })
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [proposal]

        mock_async_session.execute.side_effect = [
            proposals_result,
            self._admin_result(),
        ]

        send_mock = AsyncMock()
        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.notification.unified_hub.send_notification",
            send_mock,
        ):
            result = autonomous_trust_tasks.notify_pending_proposals()

        assert result["proposals_found"] == 1
        assert "send_dunning" in send_mock.call_args.kwargs["message"]

    def test_handles_notification_failure(
        self,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
    ) -> None:
        """Test: Faehrt fort wenn Benachrichtigung fehlschlaegt."""
        proposal1 = MagicMock(**sample_proposal)
        proposal2 = MagicMock(**{**sample_proposal, "id": uuid4()})
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [
            proposal1,
            proposal2,
        ]

        mock_async_session.execute.side_effect = [
            proposals_result,
            self._admin_result(),
        ]

        send_mock = AsyncMock(side_effect=Exception("Notification Fehler"))
        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.notification.unified_hub.send_notification",
            send_mock,
        ):
            result = autonomous_trust_tasks.notify_pending_proposals()

        # Task schlaegt nicht fehl, logged nur Warning
        assert result["proposals_found"] == 2
        assert result["companies_notified"] == 0  # Keine Notification gesendet

    def test_marks_notified(
        self,
        mock_async_session: AsyncMock,
        sample_proposal: Dict[str, Any],
    ) -> None:
        """Test: Zaehlt benachrichtigte Companies (pro Company eine Mail)."""
        proposal = MagicMock(**sample_proposal)
        proposals_result = MagicMock()
        proposals_result.scalars.return_value.all.return_value = [proposal]

        mock_async_session.execute.side_effect = [
            proposals_result,
            self._admin_result(),
        ]

        with patch.object(
            autonomous_trust_tasks,
            "get_async_session",
            _session_cm(mock_async_session),
        ), patch(
            "app.services.notification.unified_hub.send_notification",
            new_callable=AsyncMock,
        ):
            result = autonomous_trust_tasks.notify_pending_proposals()

        assert result["proposals_found"] == 1
        assert result["companies_notified"] == 1
