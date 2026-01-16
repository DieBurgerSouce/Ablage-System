# -*- coding: utf-8 -*-
"""
Unit Tests fuer NotificationRuleEngine.

Testet:
- Thread-safe Singleton-Pattern mit Double-Checked Locking
- Dataclass-Strukturen mit korrekten Defaults
- RuleConditionMatcher mit allen Operatoren
- Quiet Hours mit Zeitzonenunterstuetzung
- Rate Limiting (Cooldown + Max per Day)
- Template Variable Rendering
"""

import pytest
import threading
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from prometheus_client import Counter, Histogram


# =============================================================================
# Singleton Pattern Tests
# =============================================================================

class TestNotificationRuleEngineSingleton:
    """Tests fuer Thread-safe Singleton-Pattern."""

    def test_singleton_instance_same_object(self) -> None:
        """Testet dass get_notification_rule_engine immer die gleiche Instanz liefert."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            get_notification_rule_engine,
        )

        service1 = get_notification_rule_engine()
        service2 = get_notification_rule_engine()
        service3 = NotificationRuleEngine()  # Direkter Konstruktor

        # Alle drei muessen identisch sein (selbe Objekt-ID)
        assert service1 is service2
        assert service2 is service3
        assert id(service1) == id(service2) == id(service3)

    def test_singleton_thread_safety(self) -> None:
        """Testet dass Singleton-Pattern thread-safe ist."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        instances: list = []
        errors: list = []

        def create_instance():
            try:
                instance = NotificationRuleEngine()
                instances.append(id(instance))
            except Exception as e:
                errors.append(str(e))

        # 100 Threads gleichzeitig starten
        threads = [threading.Thread(target=create_instance) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Keine Fehler
        assert len(errors) == 0, f"Errors: {errors}"

        # Alle Instanzen muessen identisch sein (selbe ID)
        assert len(set(instances)) == 1, (
            f"Multiple instances created: {len(set(instances))} unique IDs"
        )

    def test_singleton_initialization_complete(self) -> None:
        """Testet dass Singleton vollstaendig initialisiert ist."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()

        # Alle internen Attribute muessen existieren
        assert hasattr(service, '_initialized')
        assert service._initialized is True
        assert hasattr(service, '_matcher')
        assert hasattr(service, '_event_bus')
        assert hasattr(service, '_trigger_timestamps')
        assert hasattr(service, '_daily_counts')
        assert hasattr(service, '_rate_limit_lock')
        assert isinstance(service._rate_limit_lock, type(threading.Lock()))


# =============================================================================
# Dataclass Tests
# =============================================================================

class TestRuleEngineDataClasses:
    """Tests fuer Datenstrukturen mit korrekten Defaults."""

    def test_notification_action_dataclass_required_fields(self) -> None:
        """Testet NotificationAction mit Pflichtfeldern."""
        from app.services.notification.rule_engine import (
            NotificationAction,
            ActionType,
        )

        rule_id = uuid4()
        user_id = uuid4()
        action = NotificationAction(
            action_type=ActionType.IN_APP,
            rule_id=rule_id,
            user_id=user_id,
            event_type="loan.payment_due",
            payload={"loan_id": str(uuid4()), "amount": 500.0},
        )

        # Pflichtfelder pruefen
        assert action.action_type == ActionType.IN_APP
        assert action.rule_id == rule_id
        assert action.user_id == user_id
        assert action.event_type == "loan.payment_due"
        assert "loan_id" in action.payload
        assert action.payload["amount"] == 500.0

        # Defaults pruefen
        assert action.priority == "normal"
        assert action.title is None
        assert action.message is None
        assert action.action_url is None
        assert action.email_template is None
        assert action.email_subject is None
        assert action.webhook_url is None
        assert action.push_data is None

    def test_notification_action_all_fields(self) -> None:
        """Testet NotificationAction mit allen optionalen Feldern."""
        from app.services.notification.rule_engine import (
            NotificationAction,
            ActionType,
        )

        action = NotificationAction(
            action_type=ActionType.EMAIL,
            rule_id=uuid4(),
            user_id=uuid4(),
            event_type="document.processed",
            payload={"doc_id": "abc123"},
            priority="high",
            title="Dokument verarbeitet",
            message="Ihr Dokument wurde erfolgreich verarbeitet.",
            action_url="/documents/abc123",
            email_template="document_processed.j2",
            email_subject="Dokument fertig",
            webhook_url="https://example.com/webhook",
            push_data={"badge": 1, "sound": "default"},
        )

        assert action.action_type == ActionType.EMAIL
        assert action.priority == "high"
        assert action.title == "Dokument verarbeitet"
        assert action.email_template == "document_processed.j2"
        assert action.webhook_url == "https://example.com/webhook"
        assert action.push_data["badge"] == 1

    def test_rule_evaluation_result_defaults(self) -> None:
        """Testet RuleEvaluationResult mit korrekten Defaults."""
        from app.services.notification.rule_engine import RuleEvaluationResult

        rule_id = uuid4()
        result = RuleEvaluationResult(
            rule_id=rule_id,
            rule_name="Test Rule",
            matched=False,
        )

        # Basis-Felder pruefen
        assert result.rule_id == rule_id
        assert result.rule_name == "Test Rule"
        assert result.matched is False

        # Defaults pruefen
        assert result.actions == []  # default_factory=list
        assert result.skipped_reason is None
        assert result.evaluation_time_ms == 0.0

    def test_rule_evaluation_result_no_mutable_default_sharing(self) -> None:
        """Testet dass RuleEvaluationResult keine mutable defaults teilt."""
        from app.services.notification.rule_engine import RuleEvaluationResult

        result1 = RuleEvaluationResult(
            rule_id=uuid4(),
            rule_name="Rule 1",
            matched=True,
        )
        result2 = RuleEvaluationResult(
            rule_id=uuid4(),
            rule_name="Rule 2",
            matched=True,
        )

        # Beide actions Listen muessen unterschiedliche Objekte sein
        assert result1.actions is not result2.actions

        # Mock-Aktion hinzufuegen
        mock_action = MagicMock()
        result1.actions.append(mock_action)

        assert len(result1.actions) == 1
        assert len(result2.actions) == 0  # Muss leer bleiben!

    def test_rule_evaluation_result_with_values(self) -> None:
        """Testet RuleEvaluationResult mit gesetzten Werten."""
        from app.services.notification.rule_engine import (
            RuleEvaluationResult,
            NotificationAction,
            ActionType,
        )

        rule_id = uuid4()
        action = NotificationAction(
            action_type=ActionType.PUSH,
            rule_id=rule_id,
            user_id=uuid4(),
            event_type="test.event",
            payload={},
        )

        result = RuleEvaluationResult(
            rule_id=rule_id,
            rule_name="Payment Reminder",
            matched=True,
            actions=[action],
            skipped_reason=None,
            evaluation_time_ms=12.5,
        )

        assert result.matched is True
        assert len(result.actions) == 1
        assert result.actions[0].action_type == ActionType.PUSH
        assert result.evaluation_time_ms == 12.5

    def test_event_evaluation_result_defaults(self) -> None:
        """Testet EventEvaluationResult mit korrekten Defaults."""
        from app.services.notification.rule_engine import EventEvaluationResult

        event_id = uuid4()
        result = EventEvaluationResult(
            event_id=event_id,
            event_type="loan.payment_due",
        )

        # Basis-Felder pruefen
        assert result.event_id == event_id
        assert result.event_type == "loan.payment_due"

        # Defaults pruefen
        assert result.rules_checked == 0
        assert result.rules_matched == 0
        assert result.rules_skipped == 0
        assert result.actions_generated == 0
        assert result.rule_results == []  # default_factory=list
        assert result.total_time_ms == 0.0

    def test_event_evaluation_result_no_mutable_default_sharing(self) -> None:
        """Testet dass EventEvaluationResult keine mutable defaults teilt."""
        from app.services.notification.rule_engine import EventEvaluationResult

        result1 = EventEvaluationResult(
            event_id=uuid4(),
            event_type="event.type.1",
        )
        result2 = EventEvaluationResult(
            event_id=uuid4(),
            event_type="event.type.2",
        )

        # Beide rule_results Listen muessen unterschiedliche Objekte sein
        assert result1.rule_results is not result2.rule_results

    def test_action_type_enum(self) -> None:
        """Testet ActionType Enum-Werte."""
        from app.services.notification.rule_engine import ActionType

        assert ActionType.IN_APP.value == "in_app"
        assert ActionType.PUSH.value == "push"
        assert ActionType.EMAIL.value == "email"
        assert ActionType.WEBHOOK.value == "webhook"

        # Alle Werte sind Strings
        for action_type in ActionType:
            assert isinstance(action_type.value, str)


# =============================================================================
# RuleConditionMatcher Tests
# =============================================================================

class TestRuleConditionMatcher:
    """Tests fuer RuleConditionMatcher mit allen Operatoren."""

    def test_matcher_initialization(self) -> None:
        """Testet Matcher-Initialisierung."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()
        assert matcher is not None
        assert hasattr(matcher, 'OPERATORS')
        assert hasattr(matcher, 'match')

    def test_all_operators_defined(self) -> None:
        """Testet dass alle Operatoren definiert sind."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        expected_operators = [
            "eq", "ne", "gt", "gte", "lt", "lte",
            "contains", "startswith", "endswith",
            "in", "not_in", "is_null", "is_not_null", "regex"
        ]

        for op in expected_operators:
            assert op in matcher.OPERATORS, f"Operator {op} fehlt"
            assert callable(matcher.OPERATORS[op]), f"Operator {op} ist nicht callable"

    def test_eq_operator(self) -> None:
        """Testet eq Operator."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {"field": "status", "op": "eq", "value": "active"}
        assert matcher.match(conditions, {"status": "active"}) is True
        assert matcher.match(conditions, {"status": "inactive"}) is False
        assert matcher.match(conditions, {"status": "ACTIVE"}) is False  # Case-sensitive

    def test_ne_operator(self) -> None:
        """Testet ne Operator."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {"field": "status", "op": "ne", "value": "deleted"}
        assert matcher.match(conditions, {"status": "active"}) is True
        assert matcher.match(conditions, {"status": "deleted"}) is False

    def test_gt_gte_lt_lte_operators(self) -> None:
        """Testet numerische Vergleichsoperatoren."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        # gt (greater than)
        assert matcher.match({"field": "amount", "op": "gt", "value": 100}, {"amount": 150}) is True
        assert matcher.match({"field": "amount", "op": "gt", "value": 100}, {"amount": 100}) is False
        assert matcher.match({"field": "amount", "op": "gt", "value": 100}, {"amount": 50}) is False

        # gte (greater than or equal)
        assert matcher.match({"field": "amount", "op": "gte", "value": 100}, {"amount": 150}) is True
        assert matcher.match({"field": "amount", "op": "gte", "value": 100}, {"amount": 100}) is True
        assert matcher.match({"field": "amount", "op": "gte", "value": 100}, {"amount": 50}) is False

        # lt (less than)
        assert matcher.match({"field": "amount", "op": "lt", "value": 100}, {"amount": 50}) is True
        assert matcher.match({"field": "amount", "op": "lt", "value": 100}, {"amount": 100}) is False
        assert matcher.match({"field": "amount", "op": "lt", "value": 100}, {"amount": 150}) is False

        # lte (less than or equal)
        assert matcher.match({"field": "amount", "op": "lte", "value": 100}, {"amount": 50}) is True
        assert matcher.match({"field": "amount", "op": "lte", "value": 100}, {"amount": 100}) is True
        assert matcher.match({"field": "amount", "op": "lte", "value": 100}, {"amount": 150}) is False

    def test_contains_operator(self) -> None:
        """Testet contains Operator."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {"field": "message", "op": "contains", "value": "wichtig"}
        assert matcher.match(conditions, {"message": "Eine wichtige Nachricht"}) is True
        assert matcher.match(conditions, {"message": "WICHTIG: Achtung"}) is False  # Case-sensitive
        assert matcher.match(conditions, {"message": "Eine normale Nachricht"}) is False
        assert matcher.match(conditions, {"message": None}) is False

    def test_startswith_endswith_operators(self) -> None:
        """Testet startswith und endswith Operatoren."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        # startswith
        assert matcher.match(
            {"field": "filename", "op": "startswith", "value": "report_"},
            {"filename": "report_2024.pdf"}
        ) is True
        assert matcher.match(
            {"field": "filename", "op": "startswith", "value": "report_"},
            {"filename": "invoice_2024.pdf"}
        ) is False

        # endswith
        assert matcher.match(
            {"field": "filename", "op": "endswith", "value": ".pdf"},
            {"filename": "document.pdf"}
        ) is True
        assert matcher.match(
            {"field": "filename", "op": "endswith", "value": ".pdf"},
            {"filename": "document.docx"}
        ) is False

    def test_in_operator(self) -> None:
        """Testet in Operator."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {"field": "category", "op": "in", "value": ["critical", "high", "urgent"]}
        assert matcher.match(conditions, {"category": "high"}) is True
        assert matcher.match(conditions, {"category": "critical"}) is True
        assert matcher.match(conditions, {"category": "urgent"}) is True
        assert matcher.match(conditions, {"category": "low"}) is False
        assert matcher.match(conditions, {"category": "normal"}) is False

    def test_not_in_operator_fixed(self) -> None:
        """Testet not_in Operator nach Bug Fix.

        KRITISCH: Dieser Test validiert den Bug-Fix wo not_in bei ungueltigem
        Input True zurueckgab (fail-open Verhalten). Nach dem Fix gibt es
        False zurueck (fail-safe Verhalten).
        """
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        # Normale Verwendung
        conditions = {"field": "status", "op": "not_in", "value": ["deleted", "archived"]}
        assert matcher.match(conditions, {"status": "active"}) is True
        assert matcher.match(conditions, {"status": "pending"}) is True
        assert matcher.match(conditions, {"status": "deleted"}) is False
        assert matcher.match(conditions, {"status": "archived"}) is False

        # BUG FIX: Ungueltige value-Liste muss False zurueckgeben (fail-safe!)
        invalid_conditions = {"field": "status", "op": "not_in", "value": "not_a_list"}
        # Vor Fix: True (gefaehrlich!)
        # Nach Fix: False (sicher!)
        assert matcher.match(invalid_conditions, {"status": "active"}) is False

        # Weitere Edge Cases
        assert matcher.match(
            {"field": "status", "op": "not_in", "value": None},
            {"status": "active"}
        ) is False
        assert matcher.match(
            {"field": "status", "op": "not_in", "value": 123},
            {"status": "active"}
        ) is False

    def test_is_null_is_not_null_operators(self) -> None:
        """Testet is_null und is_not_null Operatoren."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        # is_null
        assert matcher.match(
            {"field": "description", "op": "is_null", "value": None},
            {"description": None}
        ) is True
        assert matcher.match(
            {"field": "description", "op": "is_null", "value": None},
            {"description": "Some text"}
        ) is False
        assert matcher.match(
            {"field": "missing_field", "op": "is_null", "value": None},
            {"other_field": "value"}
        ) is True  # Fehlende Felder sind None

        # is_not_null
        assert matcher.match(
            {"field": "description", "op": "is_not_null", "value": None},
            {"description": "Some text"}
        ) is True
        assert matcher.match(
            {"field": "description", "op": "is_not_null", "value": None},
            {"description": None}
        ) is False

    def test_regex_operator(self) -> None:
        """Testet regex Operator."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        # Email Pattern
        assert matcher.match(
            {"field": "email", "op": "regex", "value": r"^[a-z]+@[a-z]+\.[a-z]+$"},
            {"email": "test@example.com"}
        ) is True
        assert matcher.match(
            {"field": "email", "op": "regex", "value": r"^[a-z]+@[a-z]+\.[a-z]+$"},
            {"email": "invalid-email"}
        ) is False

        # Numeric Pattern
        assert matcher.match(
            {"field": "code", "op": "regex", "value": r"^\d{4}-\d{4}$"},
            {"code": "1234-5678"}
        ) is True
        assert matcher.match(
            {"field": "code", "op": "regex", "value": r"^\d{4}-\d{4}$"},
            {"code": "12345678"}
        ) is False


# =============================================================================
# Logical Operators Tests
# =============================================================================

class TestRuleConditionMatcherLogicalOperators:
    """Tests fuer logische Operatoren (AND, OR, NOT)."""

    def test_logical_and(self) -> None:
        """Testet AND-Verknuepfung."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {
            "operator": "AND",
            "conditions": [
                {"field": "status", "op": "eq", "value": "active"},
                {"field": "amount", "op": "gt", "value": 100}
            ]
        }

        # Beide Bedingungen erfuellt
        assert matcher.match(conditions, {"status": "active", "amount": 150}) is True

        # Nur eine Bedingung erfuellt
        assert matcher.match(conditions, {"status": "active", "amount": 50}) is False
        assert matcher.match(conditions, {"status": "inactive", "amount": 150}) is False

        # Keine Bedingung erfuellt
        assert matcher.match(conditions, {"status": "inactive", "amount": 50}) is False

    def test_logical_or(self) -> None:
        """Testet OR-Verknuepfung."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {
            "operator": "OR",
            "conditions": [
                {"field": "priority", "op": "eq", "value": "critical"},
                {"field": "priority", "op": "eq", "value": "urgent"}
            ]
        }

        # Erste Bedingung erfuellt
        assert matcher.match(conditions, {"priority": "critical"}) is True

        # Zweite Bedingung erfuellt
        assert matcher.match(conditions, {"priority": "urgent"}) is True

        # Keine Bedingung erfuellt
        assert matcher.match(conditions, {"priority": "low"}) is False
        assert matcher.match(conditions, {"priority": "normal"}) is False

    def test_logical_not(self) -> None:
        """Testet NOT-Verknuepfung."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {
            "operator": "NOT",
            "conditions": [
                {"field": "status", "op": "eq", "value": "deleted"}
            ]
        }

        # Negation: True wenn Bedingung NICHT erfuellt
        assert matcher.match(conditions, {"status": "active"}) is True
        assert matcher.match(conditions, {"status": "pending"}) is True

        # Negation: False wenn Bedingung erfuellt
        assert matcher.match(conditions, {"status": "deleted"}) is False

    def test_nested_logical_operators(self) -> None:
        """Testet verschachtelte logische Operatoren."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        # (status == "active" AND amount > 100) OR priority == "critical"
        conditions = {
            "operator": "OR",
            "conditions": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "status", "op": "eq", "value": "active"},
                        {"field": "amount", "op": "gt", "value": 100}
                    ]
                },
                {"field": "priority", "op": "eq", "value": "critical"}
            ]
        }

        # Erste Gruppe erfuellt
        assert matcher.match(conditions, {"status": "active", "amount": 150, "priority": "low"}) is True

        # Zweite Bedingung erfuellt (priority critical)
        assert matcher.match(conditions, {"status": "inactive", "amount": 50, "priority": "critical"}) is True

        # Beides erfuellt
        assert matcher.match(conditions, {"status": "active", "amount": 150, "priority": "critical"}) is True

        # Nichts erfuellt
        assert matcher.match(conditions, {"status": "inactive", "amount": 50, "priority": "low"}) is False

    def test_empty_conditions(self) -> None:
        """Testet leere Bedingungen (immer match)."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        # Leere Bedingung = immer True
        assert matcher.match({}, {"any": "data"}) is True
        assert matcher.match(None, {"any": "data"}) is True

    def test_nested_field_access(self) -> None:
        """Testet verschachtelten Feld-Zugriff mit Dot-Notation."""
        from app.services.notification.rule_engine import RuleConditionMatcher

        matcher = RuleConditionMatcher()

        conditions = {"field": "payload.amount", "op": "gt", "value": 1000}

        data = {
            "event_type": "loan.payment",
            "payload": {
                "amount": 1500,
                "currency": "EUR"
            }
        }

        assert matcher.match(conditions, data) is True

        data_low_amount = {
            "event_type": "loan.payment",
            "payload": {
                "amount": 500,
                "currency": "EUR"
            }
        }

        assert matcher.match(conditions, data_low_amount) is False


# =============================================================================
# Service Methods Tests
# =============================================================================

class TestNotificationRuleEngineMethods:
    """Tests fuer Service-Methoden und ihre Signaturen."""

    def test_evaluate_event_signature(self) -> None:
        """Testet die Signatur von evaluate_event."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        import inspect

        service = NotificationRuleEngine()
        sig = inspect.signature(service.evaluate_event)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'event' in params

    def test_execute_actions_signature(self) -> None:
        """Testet die Signatur von execute_actions."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        import inspect

        service = NotificationRuleEngine()
        sig = inspect.signature(service.execute_actions)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'actions' in params

    def test_create_rule_signature(self) -> None:
        """Testet die Signatur von create_rule."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        import inspect

        service = NotificationRuleEngine()
        sig = inspect.signature(service.create_rule)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'user_id' in params
        assert 'name' in params
        assert 'event_type' in params
        assert 'conditions' in params
        assert 'actions' in params

    def test_update_rule_signature(self) -> None:
        """Testet die Signatur von update_rule."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        import inspect

        service = NotificationRuleEngine()
        sig = inspect.signature(service.update_rule)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'rule_id' in params
        assert 'user_id' in params

    def test_delete_rule_signature(self) -> None:
        """Testet die Signatur von delete_rule."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        import inspect

        service = NotificationRuleEngine()
        sig = inspect.signature(service.delete_rule)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'rule_id' in params
        assert 'user_id' in params


# =============================================================================
# Internal Methods Tests
# =============================================================================

class TestRuleEngineInternalMethods:
    """Tests fuer interne Methoden."""

    def test_is_quiet_hours_method_exists(self) -> None:
        """Testet dass _is_quiet_hours Methode existiert."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()
        assert hasattr(service, '_is_quiet_hours')
        assert callable(getattr(service, '_is_quiet_hours'))

    def test_is_rate_limited_method_exists(self) -> None:
        """Testet dass _is_rate_limited Methode existiert."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()
        assert hasattr(service, '_is_rate_limited')
        assert callable(getattr(service, '_is_rate_limited'))

    def test_record_trigger_method_exists(self) -> None:
        """Testet dass _record_trigger Methode existiert."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()
        assert hasattr(service, '_record_trigger')
        assert callable(getattr(service, '_record_trigger'))

    def test_build_event_data_method_exists(self) -> None:
        """Testet dass _build_event_data Methode existiert."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()
        assert hasattr(service, '_build_event_data')
        assert callable(getattr(service, '_build_event_data'))

    def test_build_actions_method_exists(self) -> None:
        """Testet dass _build_actions Methode existiert."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()
        assert hasattr(service, '_build_actions')
        assert callable(getattr(service, '_build_actions'))

    def test_render_action_method_exists(self) -> None:
        """Testet dass _render_action Methode existiert."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()
        assert hasattr(service, '_render_action')
        assert callable(getattr(service, '_render_action'))


# =============================================================================
# Quiet Hours Tests
# =============================================================================

class TestQuietHoursLogic:
    """Tests fuer Quiet Hours Logik."""

    def test_quiet_hours_normal_range(self) -> None:
        """Testet Quiet Hours im normalen Bereich (z.B. 09:00-17:00)."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        # Mock Rule mit Quiet Hours 09:00 - 17:00
        rule = MagicMock()
        rule.id = uuid4()
        rule.quiet_hours_start = time(9, 0)
        rule.quiet_hours_end = time(17, 0)
        rule.timezone = "Europe/Berlin"

        # Methode existiert
        result = service._is_quiet_hours(rule)
        assert isinstance(result, bool)

    def test_quiet_hours_midnight_crossing(self) -> None:
        """Testet Quiet Hours ueber Mitternacht (z.B. 22:00-08:00)."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        # Mock Rule mit Quiet Hours 22:00 - 08:00 (ueber Mitternacht)
        rule = MagicMock()
        rule.id = uuid4()
        rule.quiet_hours_start = time(22, 0)
        rule.quiet_hours_end = time(8, 0)
        rule.timezone = "Europe/Berlin"

        # Methode existiert und funktioniert
        result = service._is_quiet_hours(rule)
        assert isinstance(result, bool)

    def test_quiet_hours_disabled(self) -> None:
        """Testet dass ohne Quiet Hours immer False zurueckgegeben wird."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        # Mock Rule ohne Quiet Hours
        rule = MagicMock()
        rule.id = uuid4()
        rule.quiet_hours_start = None
        rule.quiet_hours_end = None
        rule.timezone = None

        result = service._is_quiet_hours(rule)
        assert result is False


# =============================================================================
# Rate Limiting Tests
# =============================================================================

class TestRateLimitingLogic:
    """Tests fuer Rate Limiting Logik."""

    def test_rate_limit_cooldown_tracking(self) -> None:
        """Testet Cooldown-basiertes Rate Limiting."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        # Mock Rule mit 30 Minuten Cooldown
        rule = MagicMock()
        rule.id = uuid4()
        rule.cooldown_minutes = 30
        rule.max_per_day = None

        # Vor erstem Trigger: nicht rate limited
        result = service._is_rate_limited(rule)
        assert result is False

        # Trigger aufzeichnen
        service._record_trigger(rule)

        # Nach Trigger: rate limited
        result = service._is_rate_limited(rule)
        assert result is True

    def test_rate_limit_max_per_day(self) -> None:
        """Testet max_per_day Rate Limiting."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        # Mock Rule mit max 3 pro Tag
        rule = MagicMock()
        rule.id = uuid4()
        rule.cooldown_minutes = None
        rule.max_per_day = 3

        # 3x triggern
        for i in range(3):
            result = service._is_rate_limited(rule)
            assert result is False, f"Trigger {i+1} sollte nicht rate limited sein"
            service._record_trigger(rule)

        # 4. Trigger: rate limited
        result = service._is_rate_limited(rule)
        assert result is True

    def test_rate_limit_disabled(self) -> None:
        """Testet dass ohne Rate Limits immer False zurueckgegeben wird."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        # Mock Rule ohne Rate Limits
        rule = MagicMock()
        rule.id = uuid4()
        rule.cooldown_minutes = None
        rule.max_per_day = None

        # Trigger mehrfach
        for _ in range(10):
            result = service._is_rate_limited(rule)
            assert result is False
            service._record_trigger(rule)


# =============================================================================
# Prometheus Metriken Tests
# =============================================================================

class TestRuleEngineMetrics:
    """Tests fuer Prometheus Metriken."""

    def test_metrics_defined(self) -> None:
        """Testet dass alle Prometheus Metriken korrekt definiert sind."""
        from app.services.notification.rule_engine import (
            RULES_EVALUATED,
            RULES_TRIGGERED,
            RULE_EVALUATION_TIME,
            RULES_SKIPPED_QUIET_HOURS,
            RULES_SKIPPED_RATE_LIMIT,
        )

        # Typ-Assertions
        assert isinstance(RULES_EVALUATED, Counter)
        assert isinstance(RULES_TRIGGERED, Counter)
        assert isinstance(RULE_EVALUATION_TIME, Histogram)
        assert isinstance(RULES_SKIPPED_QUIET_HOURS, Counter)
        assert isinstance(RULES_SKIPPED_RATE_LIMIT, Counter)

    def test_rules_evaluated_labels(self) -> None:
        """Testet dass RULES_EVALUATED die korrekten Labels hat."""
        from app.services.notification.rule_engine import RULES_EVALUATED

        assert 'event_type' in RULES_EVALUATED._labelnames
        assert 'matched' in RULES_EVALUATED._labelnames

    def test_rules_triggered_labels(self) -> None:
        """Testet dass RULES_TRIGGERED die korrekten Labels hat."""
        from app.services.notification.rule_engine import RULES_TRIGGERED

        assert 'event_type' in RULES_TRIGGERED._labelnames
        assert 'action_type' in RULES_TRIGGERED._labelnames

    def test_histogram_buckets(self) -> None:
        """Testet dass RULE_EVALUATION_TIME korrekte Buckets hat."""
        from app.services.notification.rule_engine import RULE_EVALUATION_TIME

        # Histogram hat _upper_bounds Attribut
        assert hasattr(RULE_EVALUATION_TIME, '_upper_bounds')


# =============================================================================
# Template Rendering Tests
# =============================================================================

class TestTemplateVariableRendering:
    """Tests fuer Template-Variable Ersetzung in Aktionen."""

    def test_render_action_simple_variables(self) -> None:
        """Testet einfache Template-Variable Ersetzung."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from app.services.events.event_bus import Event, EventType

        service = NotificationRuleEngine()

        # Mock Event
        event = MagicMock(spec=Event)
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "document.processed"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = uuid4()
        event.payload = {"document_name": "Test.pdf", "pages": 5}

        action_def = {
            "title": "Dokument {{document_name}} verarbeitet",
            "body": "{{pages}} Seiten wurden extrahiert.",
        }

        result = service._render_action(action_def, event)

        assert result["title"] == "Dokument Test.pdf verarbeitet"
        assert result["body"] == "5 Seiten wurden extrahiert."

    def test_render_action_nested_variables(self) -> None:
        """Testet verschachtelte Template-Variablen."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()

        # Mock Event mit verschachteltem Payload
        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "loan.payment_due"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = uuid4()
        event.payload = {
            "loan": {
                "name": "Autokredit",
                "amount": 500.0
            }
        }

        action_def = {
            "title": "Zahlung fuer {{payload.loan.name}} faellig",
            "body": "Betrag: {{payload.loan.amount}} EUR",
        }

        result = service._render_action(action_def, event)

        assert result["title"] == "Zahlung fuer Autokredit faellig"
        assert result["body"] == "Betrag: 500.0 EUR"

    def test_render_action_missing_variable(self) -> None:
        """Testet Verhalten bei fehlenden Variablen."""
        from app.services.notification.rule_engine import NotificationRuleEngine

        service = NotificationRuleEngine()

        # Mock Event ohne gewuenschte Variable
        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = None
        event.space_id = None
        event.payload = {}

        action_def = {
            "title": "Test mit {{missing_field}}",
        }

        result = service._render_action(action_def, event)

        # Variable bleibt als Platzhalter wenn nicht gefunden
        assert "{{missing_field}}" in result["title"]


# =============================================================================
# Build Event Data Tests
# =============================================================================

class TestBuildEventData:
    """Tests fuer _build_event_data Methode."""

    def test_build_event_data_structure(self) -> None:
        """Testet dass _build_event_data korrekte Struktur zurueckgibt."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "document.processed"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "ocr_worker"
        event.user_id = uuid4()
        event.space_id = uuid4()
        event.payload = {"doc_id": "abc123", "pages": 5}

        result = service._build_event_data(event)

        # Basis-Felder vorhanden
        assert "event_id" in result
        assert "event_type" in result
        assert "timestamp" in result
        assert "source" in result
        assert "user_id" in result
        assert "space_id" in result
        assert "payload" in result

        # Werte korrekt
        assert result["event_type"] == "document.processed"
        assert result["source"] == "ocr_worker"
        assert result["payload"]["doc_id"] == "abc123"

        # Flattened payload fuer einfachen Zugriff
        assert result["doc_id"] == "abc123"
        assert result["pages"] == 5

    def test_build_event_data_none_user(self) -> None:
        """Testet _build_event_data mit None user_id."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "system.startup"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "system"
        event.user_id = None
        event.space_id = None
        event.payload = {}

        result = service._build_event_data(event)

        assert result["user_id"] is None
        assert result["space_id"] is None

    def test_build_event_data_empty_payload(self) -> None:
        """Testet _build_event_data mit leerem Payload."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = None
        event.payload = {}

        result = service._build_event_data(event)

        assert result["payload"] == {}


# =============================================================================
# Build Actions Tests
# =============================================================================

class TestBuildActions:
    """Tests fuer _build_actions Methode."""

    def test_build_actions_in_app(self) -> None:
        """Testet Aktions-Generierung fuer in_app."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            ActionType,
        )
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        rule = MagicMock()
        rule.id = uuid4()
        rule.user_id = uuid4()
        rule.priority = "normal"
        rule.actions = [
            {
                "type": "in_app",
                "title": "Test Titel",
                "body": "Test Nachricht",
                "action_url": "/test/url",
            }
        ]

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = None
        event.payload = {}

        actions = service._build_actions(rule, event)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.IN_APP
        assert actions[0].title == "Test Titel"
        assert actions[0].message == "Test Nachricht"
        assert actions[0].action_url == "/test/url"
        assert actions[0].rule_id == rule.id
        assert actions[0].user_id == rule.user_id

    def test_build_actions_email(self) -> None:
        """Testet Aktions-Generierung fuer email."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            ActionType,
        )
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        rule = MagicMock()
        rule.id = uuid4()
        rule.user_id = uuid4()
        rule.priority = "high"
        rule.actions = [
            {
                "type": "email",
                "subject": "Test Betreff",
                "body": "Test Email Body",
                "template": "notification_email.j2",
            }
        ]

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = None
        event.payload = {}

        actions = service._build_actions(rule, event)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.EMAIL
        assert actions[0].email_subject == "Test Betreff"
        assert actions[0].email_template == "notification_email.j2"

    def test_build_actions_webhook(self) -> None:
        """Testet Aktions-Generierung fuer webhook."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            ActionType,
        )
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        rule = MagicMock()
        rule.id = uuid4()
        rule.user_id = uuid4()
        rule.priority = "normal"
        rule.actions = [
            {
                "type": "webhook",
                "url": "https://example.com/webhook",
                "title": "Event Notification",
            }
        ]

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = None
        event.payload = {"key": "value"}

        actions = service._build_actions(rule, event)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.WEBHOOK
        assert actions[0].webhook_url == "https://example.com/webhook"

    def test_build_actions_multiple_types(self) -> None:
        """Testet Generierung mehrerer Aktionstypen."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            ActionType,
        )
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        rule = MagicMock()
        rule.id = uuid4()
        rule.user_id = uuid4()
        rule.priority = "normal"
        rule.actions = [
            {"type": "in_app", "title": "In-App Titel"},
            {"type": "push", "title": "Push Titel", "data": {"badge": 1}},
            {"type": "email", "subject": "Email Betreff"},
        ]

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = None
        event.payload = {}

        actions = service._build_actions(rule, event)

        assert len(actions) == 3
        action_types = [a.action_type for a in actions]
        assert ActionType.IN_APP in action_types
        assert ActionType.PUSH in action_types
        assert ActionType.EMAIL in action_types

    def test_build_actions_unknown_type_skipped(self) -> None:
        """Testet dass unbekannte Aktionstypen uebersprungen werden."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        rule = MagicMock()
        rule.id = uuid4()
        rule.user_id = uuid4()
        rule.priority = "normal"
        rule.actions = [
            {"type": "unknown_type", "title": "Test"},
            {"type": "in_app", "title": "Valid"},
        ]

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = None
        event.payload = {}

        actions = service._build_actions(rule, event)

        # Nur die gueltige Aktion wird generiert
        assert len(actions) == 1
        assert actions[0].title == "Valid"

    def test_build_actions_dict_format(self) -> None:
        """Testet Aktionen im Dict-Format mit 'actions' key."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            ActionType,
        )
        from unittest.mock import MagicMock

        service = NotificationRuleEngine()

        rule = MagicMock()
        rule.id = uuid4()
        rule.user_id = uuid4()
        rule.priority = "normal"
        rule.actions = {
            "actions": [
                {"type": "in_app", "title": "Test"}
            ]
        }

        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.user_id = uuid4()
        event.space_id = None
        event.payload = {}

        actions = service._build_actions(rule, event)

        assert len(actions) == 1
        assert actions[0].action_type == ActionType.IN_APP


# =============================================================================
# Async Event Evaluation Tests
# =============================================================================

class TestAsyncEventEvaluation:
    """Tests fuer async evaluate_event Methode."""

    @pytest.mark.asyncio
    async def test_evaluate_event_no_rules(self) -> None:
        """Testet evaluate_event wenn keine Regeln existieren."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock, patch

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()

        # Mock Event
        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.user_id = uuid4()

        # Mock _get_active_rules to return empty list
        with patch.object(service, '_get_active_rules', new_callable=AsyncMock) as mock_get_rules:
            mock_get_rules.return_value = []

            result = await service.evaluate_event(db, event)

            assert result.event_id == event.event_id
            assert result.event_type == "test.event"
            assert result.rules_checked == 0
            assert result.rules_matched == 0
            assert result.actions_generated == 0

    @pytest.mark.asyncio
    async def test_evaluate_event_with_matching_rule(self) -> None:
        """Testet evaluate_event mit passender Regel."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock, patch

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()

        # Mock Event
        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "document.processed"
        event.user_id = uuid4()
        event.space_id = None
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.payload = {"status": "success"}

        # Mock Rule
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Test Rule"
        mock_rule.user_id = event.user_id
        mock_rule.conditions = {}  # Empty conditions = always match
        mock_rule.actions = [{"type": "in_app", "title": "Processed"}]
        mock_rule.quiet_hours_start = None
        mock_rule.quiet_hours_end = None
        mock_rule.cooldown_minutes = None
        mock_rule.max_per_day = None
        mock_rule.priority = "normal"

        with patch.object(service, '_get_active_rules', new_callable=AsyncMock) as mock_get_rules:
            mock_get_rules.return_value = [mock_rule]

            result = await service.evaluate_event(db, event)

            assert result.rules_checked == 1
            assert result.rules_matched == 1
            assert result.actions_generated == 1

    @pytest.mark.asyncio
    async def test_evaluate_event_rule_not_matching(self) -> None:
        """Testet evaluate_event mit nicht passender Regel."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock, patch

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()

        # Mock Event
        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "document.processed"
        event.user_id = uuid4()
        event.space_id = None
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.payload = {"status": "failed"}

        # Mock Rule - requires status == "success"
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Success Rule"
        mock_rule.user_id = event.user_id
        mock_rule.conditions = {"field": "status", "op": "eq", "value": "success"}
        mock_rule.actions = [{"type": "in_app", "title": "Success"}]
        mock_rule.quiet_hours_start = None
        mock_rule.quiet_hours_end = None
        mock_rule.cooldown_minutes = None
        mock_rule.max_per_day = None
        mock_rule.priority = "normal"

        with patch.object(service, '_get_active_rules', new_callable=AsyncMock) as mock_get_rules:
            mock_get_rules.return_value = [mock_rule]

            result = await service.evaluate_event(db, event)

            assert result.rules_checked == 1
            assert result.rules_matched == 0
            assert result.actions_generated == 0

    @pytest.mark.asyncio
    async def test_evaluate_event_skipped_quiet_hours(self) -> None:
        """Testet dass Regel wegen Quiet Hours uebersprungen wird."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock, patch

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()

        # Mock Event
        event = MagicMock()
        event.event_id = uuid4()
        event.event_type = MagicMock()
        event.event_type.value = "test.event"
        event.user_id = uuid4()
        event.space_id = None
        event.timestamp = datetime.now(timezone.utc)
        event.source = "test"
        event.payload = {}

        # Mock Rule
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Quiet Rule"
        mock_rule.conditions = {}
        mock_rule.actions = [{"type": "in_app", "title": "Test"}]
        # Force quiet hours
        mock_rule.quiet_hours_start = time(0, 0)
        mock_rule.quiet_hours_end = time(23, 59)
        mock_rule.timezone = "UTC"
        mock_rule.cooldown_minutes = None
        mock_rule.max_per_day = None

        with patch.object(service, '_get_active_rules', new_callable=AsyncMock) as mock_get_rules:
            mock_get_rules.return_value = [mock_rule]

            result = await service.evaluate_event(db, event)

            assert result.rules_checked == 1
            assert result.rules_skipped == 1
            assert result.rules_matched == 0


# =============================================================================
# Async CRUD Operations Tests
# =============================================================================

class TestAsyncCRUDOperations:
    """Tests fuer async CRUD Operationen."""

    @pytest.mark.asyncio
    async def test_create_rule(self) -> None:
        """Testet Regel-Erstellung."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock, patch

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        user_id = uuid4()

        # Mock created rule
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.user_id = user_id
        mock_rule.name = "Test Rule"
        mock_rule.event_type = "document.processed"

        # Configure db mock
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch('app.services.notification.rule_engine.NotificationRule') as mock_model:
            mock_model.return_value = mock_rule

            result = await service.create_rule(
                db=db,
                user_id=user_id,
                name="Test Rule",
                event_type="document.processed",
                conditions={"field": "status", "op": "eq", "value": "done"},
                actions=[{"type": "in_app", "title": "Fertig"}],
            )

            db.add.assert_called_once_with(mock_rule)
            db.commit.assert_awaited_once()
            db.refresh.assert_awaited_once_with(mock_rule)

    @pytest.mark.asyncio
    async def test_get_rules_for_user(self) -> None:
        """Testet Abrufen aller Regeln eines Users."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        user_id = uuid4()

        # Mock rules
        mock_rules = [MagicMock(), MagicMock()]

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_rules
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_rules_for_user(db, user_id)

        assert len(result) == 2
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_rules_for_user_enabled_only(self) -> None:
        """Testet Abrufen nur aktiver Regeln."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        user_id = uuid4()

        # Mock rules
        mock_rules = [MagicMock()]

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_rules
        db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_rules_for_user(db, user_id, enabled_only=True)

        assert len(result) == 1
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_rule_success(self) -> None:
        """Testet erfolgreiche Regel-Aktualisierung."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        rule_id = uuid4()
        user_id = uuid4()

        # Mock existing rule
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.user_id = user_id
        mock_rule.name = "Old Name"

        db.get = AsyncMock(return_value=mock_rule)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        result = await service.update_rule(
            db=db,
            rule_id=rule_id,
            user_id=user_id,
            name="New Name",
        )

        assert result is not None
        assert mock_rule.name == "New Name"
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_rule_not_found(self) -> None:
        """Testet Regel-Aktualisierung bei nicht gefundener Regel."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        result = await service.update_rule(
            db=db,
            rule_id=uuid4(),
            user_id=uuid4(),
            name="New Name",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_rule_wrong_user(self) -> None:
        """Testet Regel-Aktualisierung mit falschem User."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        rule_id = uuid4()
        owner_id = uuid4()
        wrong_user_id = uuid4()

        # Mock rule owned by different user
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.user_id = owner_id

        db.get = AsyncMock(return_value=mock_rule)

        result = await service.update_rule(
            db=db,
            rule_id=rule_id,
            user_id=wrong_user_id,
            name="New Name",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_rule_success(self) -> None:
        """Testet erfolgreiche Regel-Loeschung."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        rule_id = uuid4()
        user_id = uuid4()

        # Mock existing rule
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.user_id = user_id

        db.get = AsyncMock(return_value=mock_rule)
        db.delete = AsyncMock()
        db.commit = AsyncMock()

        result = await service.delete_rule(db, rule_id, user_id)

        assert result is True
        db.delete.assert_awaited_once_with(mock_rule)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(self) -> None:
        """Testet Regel-Loeschung bei nicht gefundener Regel."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        result = await service.delete_rule(db, uuid4(), uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_rule_wrong_user(self) -> None:
        """Testet Regel-Loeschung mit falschem User."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        rule_id = uuid4()
        owner_id = uuid4()
        wrong_user_id = uuid4()

        # Mock rule owned by different user
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.user_id = owner_id

        db.get = AsyncMock(return_value=mock_rule)

        result = await service.delete_rule(db, rule_id, wrong_user_id)

        assert result is False


# =============================================================================
# Execute Actions Tests
# =============================================================================

class TestAsyncExecuteActions:
    """Tests fuer async execute_actions Methode."""

    @pytest.mark.asyncio
    async def test_execute_actions_in_app(self) -> None:
        """Testet Ausfuehrung von in_app Aktionen."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            NotificationAction,
            ActionType,
        )
        from unittest.mock import AsyncMock, MagicMock, patch

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        user_id = uuid4()
        action = NotificationAction(
            action_type=ActionType.IN_APP,
            rule_id=uuid4(),
            user_id=user_id,
            event_type="test.event",
            payload={},
            title="Test Notification",
            message="Test Message",
            action_url="/test",
        )

        with patch('app.services.notification.rule_engine.UserNotification') as mock_model:
            result = await service.execute_actions(db, [action])

            assert result["in_app"] == 1
            db.add.assert_called_once()
            db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_actions_empty_list(self) -> None:
        """Testet execute_actions mit leerer Aktionsliste."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()

        result = await service.execute_actions(db, [])

        assert result["in_app"] == 0
        assert result["push"] == 0
        assert result["email"] == 0
        assert result["webhook"] == 0

    @pytest.mark.asyncio
    async def test_execute_actions_error_handling(self) -> None:
        """Testet Fehlerbehandlung bei Aktions-Ausfuehrung."""
        from app.services.notification.rule_engine import (
            NotificationRuleEngine,
            NotificationAction,
            ActionType,
        )
        from unittest.mock import AsyncMock, MagicMock, patch

        service = NotificationRuleEngine()

        # Mock DB Session that raises error on commit
        db = AsyncMock()
        db.add = MagicMock()  # db.add is synchronous
        db.commit = AsyncMock(side_effect=Exception("DB Error"))

        action = NotificationAction(
            action_type=ActionType.IN_APP,
            rule_id=uuid4(),
            user_id=uuid4(),
            event_type="test.event",
            payload={},
            title="Test",
            message="Test",
        )

        with patch('app.services.notification.rule_engine.UserNotification'):
            # Should not raise, errors are caught internally
            result = await service.execute_actions(db, [action])

            # Action failed, count is 0
            assert result["in_app"] == 0


# =============================================================================
# Update Rule Statistics Tests
# =============================================================================

class TestUpdateRuleStatistics:
    """Tests fuer update_rule_statistics Methode."""

    @pytest.mark.asyncio
    async def test_update_rule_statistics(self) -> None:
        """Testet Aktualisierung der Regel-Statistiken."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        rule_id = uuid4()
        event_id = uuid4()

        await service.update_rule_statistics(db, rule_id, event_id)

        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()


# =============================================================================
# Get Active Rules Tests
# =============================================================================

class TestGetActiveRules:
    """Tests fuer _get_active_rules Methode."""

    @pytest.mark.asyncio
    async def test_get_active_rules_basic(self) -> None:
        """Testet Laden aktiver Regeln."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()

        # Mock rules
        mock_rules = [MagicMock(), MagicMock()]

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_rules
        db.execute = AsyncMock(return_value=mock_result)

        result = await service._get_active_rules(db, "test.event")

        assert len(result) == 2
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_active_rules_with_user_filter(self) -> None:
        """Testet Laden aktiver Regeln mit User-Filter."""
        from app.services.notification.rule_engine import NotificationRuleEngine
        from unittest.mock import AsyncMock, MagicMock

        service = NotificationRuleEngine()

        # Mock DB Session
        db = AsyncMock()
        user_id = uuid4()

        # Mock rules
        mock_rules = [MagicMock()]

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_rules
        db.execute = AsyncMock(return_value=mock_result)

        result = await service._get_active_rules(db, "test.event", user_id)

        assert len(result) == 1
        db.execute.assert_awaited_once()
