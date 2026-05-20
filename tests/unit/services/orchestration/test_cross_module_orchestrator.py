# -*- coding: utf-8 -*-
"""
Unit Tests fuer CrossModuleOrchestrator.

Testet:
- Memory-Leak-Prevention (bounded deques)
- Event Handler Logik
- Conflict Prevention mit TTL
- Action Queuing und Execution
- Decision Recording

PHASE 0.7 CRITICAL FIX: 80%+ Coverage Ziel
"""

import asyncio
from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.cross_module_orchestrator import (
    CrossModuleOrchestrator,
    OrchestrationAction,
    OrchestrationDecision,
    CascadingImpact,
    ActionType,
    ActionPriority,
    ModuleType,
    get_cross_module_orchestrator,
    start_orchestrator,
    stop_orchestrator,
)
from app.services.events.event_bus import Event, EventType


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_orchestrator():
    """Reset Singleton vor und nach jedem Test."""
    # Reset vor Test
    CrossModuleOrchestrator._instance = None

    yield

    # Reset nach Test
    CrossModuleOrchestrator._instance = None


@pytest.fixture
def orchestrator(reset_orchestrator):
    """Frische Orchestrator-Instanz fuer jeden Test."""
    return CrossModuleOrchestrator()


@pytest.fixture
def mock_event():
    """Erstellt ein Mock-Event."""
    return Event(
        event_type=EventType.DOCUMENT_ANOMALY_DETECTED,
        payload={
            "anomaly_type": "unusual_amount",
            "severity": "critical",
            "document_id": str(uuid4()),
            "confidence": 0.9,
        },
        user_id=uuid4(),
        correlation_id=uuid4(),
    )


@pytest.fixture
def mock_finance_event():
    """Erstellt ein Finanz-Anomalie Event."""
    return Event(
        event_type=EventType.FINANCE_ANOMALY_DETECTED,
        payload={
            "anomaly_type": "unusual_amount",
            "amount": "1500.00",
            "expected_amount": "500.00",
            "deviation_percent": 200,
        },
        user_id=uuid4(),
    )


@pytest.fixture
def mock_budget_event():
    """Erstellt ein Budget-Ueberschreitungs-Event."""
    return Event(
        event_type=EventType.FINANCE_BUDGET_EXCEEDED,
        payload={
            "category": "Haushalt",
            "budget": "1000.00",
            "spent": "1750.00",
        },
        user_id=uuid4(),
        correlation_id=uuid4(),
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_orchestrator):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = CrossModuleOrchestrator()
        instance2 = CrossModuleOrchestrator()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_orchestrator):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_cross_module_orchestrator()
        instance2 = get_cross_module_orchestrator()

        assert instance1 is instance2

    def test_initialization_only_once(self, reset_orchestrator):
        """Initialisierung erfolgt nur einmal."""
        instance = CrossModuleOrchestrator()

        assert instance._initialized is True

        # Zweiter Aufruf sollte nicht re-initialisieren
        original_deque = instance._pending_actions
        instance2 = CrossModuleOrchestrator()

        assert instance2._pending_actions is original_deque


# =============================================================================
# Memory Management Tests
# =============================================================================

class TestMemoryManagement:
    """Tests fuer Memory-Leak Prevention."""

    @pytest.mark.asyncio
    async def test_pending_actions_bounded(self, orchestrator):
        """Pending Actions duerfen nicht unbegrenzt wachsen."""
        # Erstelle mehr Actions als maxlen erlaubt
        for i in range(12000):
            action = OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                priority=ActionPriority.NORMAL,
            )
            await orchestrator._queue_action(action)

        # Sollte auf maxlen begrenzt sein
        assert len(orchestrator._pending_actions) <= orchestrator._max_pending_actions
        assert len(orchestrator._pending_actions) == 10000

    def test_pending_actions_is_deque_with_maxlen(self, orchestrator):
        """Pending Actions ist eine bounded deque."""
        assert isinstance(orchestrator._pending_actions, deque)
        assert orchestrator._pending_actions.maxlen == 10000

    def test_decision_history_is_bounded(self, orchestrator):
        """Decision History ist eine bounded deque."""
        assert isinstance(orchestrator._decision_history, deque)
        assert orchestrator._decision_history.maxlen == 1000

    @pytest.mark.asyncio
    async def test_decision_history_bounded(self, orchestrator):
        """Decision History darf nicht unbegrenzt wachsen."""
        # Erstelle mehr Decisions als maxlen erlaubt
        for i in range(1200):
            decision = OrchestrationDecision(
                decision_id=uuid4(),
                reasoning=f"Test decision {i}",
            )
            await orchestrator._record_decision(decision)

        # Sollte auf maxlen begrenzt sein
        assert len(orchestrator._decision_history) <= 1000

    @pytest.mark.asyncio
    async def test_stale_entity_actions_cleanup(self, orchestrator):
        """Veraltete Entity-Actions werden bereinigt."""
        # Setup: Alte Eintraege erstellen
        old_timestamp = datetime.now(timezone.utc) - timedelta(hours=25)
        orchestrator._active_entity_actions["old_entity"] = (
            {"workflow"},
            old_timestamp
        )

        # Neuer Eintrag der bleiben soll
        new_timestamp = datetime.now(timezone.utc)
        orchestrator._active_entity_actions["new_entity"] = (
            {"notification"},
            new_timestamp
        )

        # Cleanup ausfuehren
        cleaned = await orchestrator._cleanup_stale_entity_actions()

        assert cleaned == 1
        assert "old_entity" not in orchestrator._active_entity_actions
        assert "new_entity" in orchestrator._active_entity_actions


# =============================================================================
# Conflict Prevention Tests
# =============================================================================

class TestConflictPrevention:
    """Tests fuer Action-Konflikt-Verhinderung."""

    def test_is_action_active_returns_false_for_unknown(self, orchestrator):
        """Unbekannte Entities haben keine aktiven Aktionen."""
        result = orchestrator._is_action_active("unknown_key", "workflow")

        assert result is False

    @pytest.mark.asyncio
    async def test_mark_action_active(self, orchestrator):
        """Aktion wird korrekt als aktiv markiert."""
        entity_key = "document_123"
        action_type = "workflow"

        await orchestrator._mark_action_active(entity_key, action_type)

        assert orchestrator._is_action_active(entity_key, action_type) is True
        assert orchestrator._is_action_active(entity_key, "other") is False

    @pytest.mark.asyncio
    async def test_mark_action_complete_removes_single(self, orchestrator):
        """Abgeschlossene Aktion wird entfernt, andere bleiben."""
        entity_key = "document_123"

        await orchestrator._mark_action_active(entity_key, "workflow")
        await orchestrator._mark_action_active(entity_key, "notification")

        await orchestrator._mark_action_complete(entity_key, "workflow")

        assert orchestrator._is_action_active(entity_key, "workflow") is False
        assert orchestrator._is_action_active(entity_key, "notification") is True

    @pytest.mark.asyncio
    async def test_mark_action_complete_removes_entry_when_empty(self, orchestrator):
        """Entry wird entfernt wenn keine Aktionen mehr aktiv."""
        entity_key = "document_123"

        await orchestrator._mark_action_active(entity_key, "workflow")
        await orchestrator._mark_action_complete(entity_key, "workflow")

        assert entity_key not in orchestrator._active_entity_actions

    def test_is_action_active_respects_ttl(self, orchestrator):
        """Alte Eintraege werden bei TTL-Check entfernt."""
        entity_key = "old_document"
        old_timestamp = datetime.now(timezone.utc) - timedelta(hours=25)

        orchestrator._active_entity_actions[entity_key] = (
            {"workflow"},
            old_timestamp
        )

        # Abfrage sollte False zurueckgeben UND Entry entfernen
        result = orchestrator._is_action_active(entity_key, "workflow")

        assert result is False
        assert entity_key not in orchestrator._active_entity_actions


# =============================================================================
# Event Handler Tests
# =============================================================================

class TestDocumentAnomalyHandler:
    """Tests fuer Document Anomaly Handler."""

    @pytest.mark.asyncio
    async def test_critical_anomaly_creates_workflow_and_notification(
        self, orchestrator, mock_event
    ):
        """Kritische Anomalie erstellt Workflow und Benachrichtigung."""
        actions = await orchestrator._handle_document_anomaly(mock_event)

        assert len(actions) == 2

        # Erste Aktion: Workflow
        workflow_action = actions[0]
        assert workflow_action.action_type == ActionType.TRIGGER_WORKFLOW
        assert workflow_action.priority == ActionPriority.CRITICAL
        assert "document_approval" in workflow_action.action_data["workflow_type"]

        # Zweite Aktion: Notification
        notification_action = actions[1]
        assert notification_action.action_type == ActionType.SEND_NOTIFICATION
        assert notification_action.priority == ActionPriority.HIGH

    @pytest.mark.asyncio
    async def test_medium_anomaly_creates_only_recommendation(self, orchestrator):
        """Mittlere Anomalie erstellt nur Empfehlung."""
        event = Event(
            event_type=EventType.DOCUMENT_ANOMALY_DETECTED,
            payload={
                "anomaly_type": "minor_discrepancy",
                "severity": "medium",
                "document_id": str(uuid4()),
                "confidence": 0.6,
            },
            user_id=uuid4(),
        )

        actions = await orchestrator._handle_document_anomaly(event)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.CREATE_RECOMMENDATION
        assert actions[0].priority == ActionPriority.NORMAL

    @pytest.mark.asyncio
    async def test_low_anomaly_creates_no_action(self, orchestrator):
        """Niedrige Anomalie erstellt keine Aktion."""
        event = Event(
            event_type=EventType.DOCUMENT_ANOMALY_DETECTED,
            payload={
                "anomaly_type": "minor",
                "severity": "low",
                "document_id": str(uuid4()),
                "confidence": 0.4,
            },
            user_id=uuid4(),
        )

        actions = await orchestrator._handle_document_anomaly(event)

        assert len(actions) == 0

    @pytest.mark.asyncio
    async def test_skips_if_action_already_active(self, orchestrator, mock_event):
        """Ueberspringt wenn bereits Aktion fuer Dokument laeuft."""
        doc_id = mock_event.payload["document_id"]

        # Simuliere aktive Aktion
        await orchestrator._mark_action_active(f"document_{doc_id}", "workflow")

        actions = await orchestrator._handle_document_anomaly(mock_event)

        assert len(actions) == 0


class TestFinanceAnomalyHandler:
    """Tests fuer Finance Anomaly Handler."""

    @pytest.mark.asyncio
    async def test_high_deviation_creates_critical_notification(
        self, orchestrator, mock_finance_event
    ):
        """Hohe Abweichung erstellt kritische Benachrichtigung."""
        actions = await orchestrator._handle_finance_anomaly(mock_finance_event)

        assert len(actions) == 2

        notification = actions[0]
        assert notification.action_type == ActionType.SEND_NOTIFICATION
        assert notification.priority == ActionPriority.CRITICAL

        task = actions[1]
        assert task.action_type == ActionType.CREATE_TASK

    @pytest.mark.asyncio
    async def test_moderate_deviation_creates_recommendation(self, orchestrator):
        """Moderate Abweichung (20-50%) erstellt Empfehlung."""
        event = Event(
            event_type=EventType.FINANCE_ANOMALY_DETECTED,
            payload={
                "anomaly_type": "unusual_amount",
                "amount": "625.00",
                "expected_amount": "500.00",
                "deviation_percent": 25,  # > 20 (not >=)
            },
            user_id=uuid4(),
        )

        actions = await orchestrator._handle_finance_anomaly(event)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.CREATE_RECOMMENDATION

    @pytest.mark.asyncio
    async def test_low_deviation_no_action(self, orchestrator):
        """Niedrige Abweichung (<20%) erstellt keine Aktion."""
        event = Event(
            event_type=EventType.FINANCE_ANOMALY_DETECTED,
            payload={
                "anomaly_type": "unusual_amount",
                "amount": "550.00",
                "expected_amount": "500.00",
                "deviation_percent": 10,
            },
            user_id=uuid4(),
        )

        actions = await orchestrator._handle_finance_anomaly(event)

        assert len(actions) == 0


class TestBudgetExceededHandler:
    """Tests fuer Budget Exceeded Handler."""

    @pytest.mark.asyncio
    async def test_massive_overage_creates_payment_pause_recommendation(
        self, orchestrator, mock_budget_event
    ):
        """Massive Ueberschreitung (>50%) schlaegt Zahlungspause vor."""
        actions = await orchestrator._handle_budget_exceeded(mock_budget_event)

        # Sollte Notification + Recommendation haben
        assert len(actions) == 2

        notification = actions[0]
        assert notification.action_type == ActionType.SEND_NOTIFICATION
        assert notification.priority == ActionPriority.HIGH

        recommendation = actions[1]
        assert recommendation.action_type == ActionType.CREATE_RECOMMENDATION
        assert "Zahlungspause" in recommendation.action_data["title"]

    @pytest.mark.asyncio
    async def test_moderate_overage_creates_notification_only(self, orchestrator):
        """Moderate Ueberschreitung (20-50%) erstellt nur Notification."""
        event = Event(
            event_type=EventType.FINANCE_BUDGET_EXCEEDED,
            payload={
                "category": "Essen",
                "budget": "500.00",
                "spent": "600.00",  # 20% over
            },
            user_id=uuid4(),
            correlation_id=uuid4(),
        )

        actions = await orchestrator._handle_budget_exceeded(event)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.SEND_NOTIFICATION


# =============================================================================
# Action Execution Tests
# =============================================================================

class TestActionExecution:
    """Tests fuer Action Execution."""

    @pytest.mark.asyncio
    async def test_queue_action_adds_to_deque(self, orchestrator):
        """Action wird zur Queue hinzugefuegt."""
        action = OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=ActionPriority.NORMAL,
        )

        initial_count = len(orchestrator._pending_actions)
        await orchestrator._queue_action(action)

        assert len(orchestrator._pending_actions) == initial_count + 1

    @pytest.mark.asyncio
    async def test_execute_action_updates_status(self, orchestrator):
        """Action-Status wird bei Ausfuehrung aktualisiert."""
        with patch.object(orchestrator, '_execute_notification', new_callable=AsyncMock):
            action = OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                priority=ActionPriority.NORMAL,
            )

            result = await orchestrator._execute_action(action)

            assert result is True
            assert action.status == "completed"
            assert action.executed_at is not None

    @pytest.mark.asyncio
    async def test_execute_action_handles_error(self, orchestrator):
        """Fehler bei Ausfuehrung werden korrekt behandelt."""
        with patch.object(
            orchestrator, '_execute_notification',
            new_callable=AsyncMock,
            side_effect=Exception("Test error")
        ):
            action = OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                priority=ActionPriority.NORMAL,
            )

            result = await orchestrator._execute_action(action)

            assert result is False
            assert action.status == "failed"
            assert "Test error" in action.error

    @pytest.mark.asyncio
    async def test_execute_notification_calls_service(self, orchestrator):
        """Notification ruft NotificationService auf."""
        with patch(
            'app.services.notification_service.get_notification_service'
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.notify = AsyncMock()
            mock_get_service.return_value = mock_service

            action = OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                target_entity_id=uuid4(),
                action_data={
                    "notification_type": "test",
                    "priority": "normal",
                },
            )

            await orchestrator._execute_notification(action)

            mock_service.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_pending_actions_sorts_by_priority(self, orchestrator):
        """Pending Actions werden nach Prioritaet sortiert."""
        # Erstelle Actions mit verschiedenen Prioritaeten
        low_action = OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            priority=ActionPriority.LOW,
        )
        critical_action = OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=ActionPriority.CRITICAL,
        )
        normal_action = OrchestrationAction(
            action_type=ActionType.CREATE_TASK,
            priority=ActionPriority.NORMAL,
        )

        await orchestrator._queue_action(low_action)
        await orchestrator._queue_action(critical_action)
        await orchestrator._queue_action(normal_action)

        # Mock alle Executions
        with patch.object(orchestrator, '_execute_action', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = True

            await orchestrator.process_pending_actions(max_actions=3)

            # Kritisch sollte zuerst ausgefuehrt werden
            calls = mock_execute.call_args_list
            first_action = calls[0][0][0]
            assert first_action.priority == ActionPriority.CRITICAL


# =============================================================================
# Decision Recording Tests
# =============================================================================

class TestDecisionRecording:
    """Tests fuer Decision Recording."""

    @pytest.mark.asyncio
    async def test_record_decision_adds_to_history(self, orchestrator):
        """Decision wird zur History hinzugefuegt."""
        decision = OrchestrationDecision(
            decision_id=uuid4(),
            reasoning="Test reasoning",
        )

        await orchestrator._record_decision(decision)

        assert decision in orchestrator._decision_history

    def test_generate_reasoning_combines_action_reasons(self, orchestrator, mock_event):
        """Reasoning kombiniert alle Action Reasons."""
        actions = [
            OrchestrationAction(reason="Erste Aktion"),
            OrchestrationAction(reason="Zweite Aktion"),
        ]

        reasoning = orchestrator._generate_reasoning(mock_event, actions)

        assert "Erste Aktion" in reasoning
        assert "Zweite Aktion" in reasoning
        assert " -> " in reasoning

    def test_generate_reasoning_empty_actions(self, orchestrator, mock_event):
        """Leere Actions geben Standard-Reasoning."""
        reasoning = orchestrator._generate_reasoning(mock_event, [])

        assert reasoning == "Keine Aktion erforderlich."

    def test_calculate_confidence_averages_actions(self, orchestrator, mock_event):
        """Confidence ist Durchschnitt der Action-Confidences."""
        actions = [
            OrchestrationAction(confidence=0.8),
            OrchestrationAction(confidence=0.6),
        ]

        confidence = orchestrator._calculate_confidence(mock_event, actions)

        assert confidence == 0.7

    def test_get_decision_history_respects_limit(self, orchestrator):
        """get_decision_history respektiert Limit."""
        # Fuege 50 Decisions hinzu
        for i in range(50):
            orchestrator._decision_history.append(
                OrchestrationDecision(reasoning=f"Decision {i}")
            )

        history = orchestrator.get_decision_history(limit=10)

        assert len(history) == 10
        # Sollte die letzten 10 sein
        assert history[0].reasoning == "Decision 40"
        assert history[-1].reasoning == "Decision 49"


# =============================================================================
# Public API Tests
# =============================================================================

class TestPublicAPI:
    """Tests fuer Public API."""

    def test_get_pending_actions_returns_list(self, orchestrator):
        """get_pending_actions gibt Liste zurueck."""
        result = orchestrator.get_pending_actions()

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_metrics_returns_dict(self, orchestrator):
        """get_metrics gibt Dictionary mit Metriken zurueck."""
        metrics = await orchestrator.get_metrics()

        assert "pending_actions_count" in metrics
        assert "pending_actions_max" in metrics
        assert "decision_history_count" in metrics
        assert "active_entity_actions" in metrics

    @pytest.mark.asyncio
    async def test_start_calls_subscribe_to_events(self, orchestrator):
        """start() abonniert Events."""
        with patch.object(orchestrator, '_subscribe_to_events', new_callable=AsyncMock) as mock_subscribe:
            with patch(
                'app.services.orchestration.cross_module_orchestrator.get_event_bus'
            ) as mock_get_bus:
                mock_get_bus.return_value = MagicMock()

                await orchestrator.start()

                mock_subscribe.assert_called_once()


# =============================================================================
# Start/Stop Functions Tests
# =============================================================================

class TestStartStopFunctions:
    """Tests fuer start_orchestrator und stop_orchestrator."""

    @pytest.mark.asyncio
    async def test_start_orchestrator_returns_instance(self, reset_orchestrator):
        """start_orchestrator gibt Instanz zurueck."""
        with patch.object(CrossModuleOrchestrator, 'start', new_callable=AsyncMock):
            with patch(
                'app.services.orchestration.cross_module_orchestrator.get_event_bus'
            ) as mock_get_bus:
                mock_get_bus.return_value = MagicMock()

                result = await start_orchestrator()

                assert isinstance(result, CrossModuleOrchestrator)

    @pytest.mark.asyncio
    async def test_stop_orchestrator_calls_stop(self, reset_orchestrator):
        """stop_orchestrator ruft stop() auf."""
        orchestrator = get_cross_module_orchestrator()

        with patch.object(orchestrator, 'stop', new_callable=AsyncMock) as mock_stop:
            await stop_orchestrator()

            mock_stop.assert_called_once()


# =============================================================================
# Data Classes Tests
# =============================================================================

class TestDataClasses:
    """Tests fuer Data Classes."""

    def test_orchestration_action_defaults(self):
        """OrchestrationAction hat sinnvolle Defaults."""
        action = OrchestrationAction()

        assert action.id is not None
        assert action.action_type == ActionType.SEND_NOTIFICATION
        assert action.priority == ActionPriority.NORMAL
        assert action.status == "pending"
        assert action.confidence == 1.0
        assert action.created_at is not None

    def test_orchestration_decision_defaults(self):
        """OrchestrationDecision hat sinnvolle Defaults."""
        decision = OrchestrationDecision()

        assert decision.decision_id is not None
        assert decision.actions == []
        assert decision.confidence == 1.0
        assert decision.created_at is not None

    def test_cascading_impact_structure(self):
        """CascadingImpact hat korrekte Struktur."""
        impact = CascadingImpact(
            source_module=ModuleType.FINANCE,
            source_entity_id=uuid4(),
            source_change="Budget ueberschritten",
            target_module=ModuleType.FINANCE,
            target_entity_ids=[uuid4()],
            impact_type="health_degradation",
            impact_description="Financial Health sinkt",
            estimated_magnitude="mittel",
        )

        assert impact.source_module == ModuleType.FINANCE
        assert impact.estimated_magnitude == "mittel"
        assert impact.suggested_actions == []


# =============================================================================
# Enums Tests
# =============================================================================

class TestEnums:
    """Tests fuer Enums."""

    def test_action_type_values(self):
        """ActionType hat erwartete Werte."""
        assert ActionType.TRIGGER_WORKFLOW.value == "trigger_workflow"
        assert ActionType.SEND_NOTIFICATION.value == "send_notification"
        assert ActionType.CREATE_RECOMMENDATION.value == "create_recommendation"

    def test_action_priority_values(self):
        """ActionPriority hat erwartete Werte."""
        assert ActionPriority.CRITICAL.value == "kritisch"
        assert ActionPriority.HIGH.value == "hoch"
        assert ActionPriority.NORMAL.value == "normal"
        assert ActionPriority.LOW.value == "niedrig"

    def test_module_type_values(self):
        """ModuleType hat erwartete Module."""
        modules = [m.value for m in ModuleType]

        assert "document" in modules
        assert "property" in modules
        assert "vehicle" in modules
        assert "insurance" in modules
        assert "loan" in modules
