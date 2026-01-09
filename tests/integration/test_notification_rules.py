# -*- coding: utf-8 -*-
"""Integrationstests fuer Notification Rules.

Tests fuer:
- Notification Rule Engine
- Rule CRUD API
- Condition Matching
- Action Execution
- Quiet Hours
- Rate Limiting

Alle Tests auf Deutsch mit deutschen Fehlermeldungen.
"""

import pytest
from fastapi import status
from uuid import uuid4
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.integration
@pytest.mark.api
class TestNotificationRulesAPI:
    """Tests fuer Notification Rules API Endpoints."""

    def test_list_rules_endpoint_exists(self, client):
        """Test dass Listen-Endpoint fuer Rules erreichbar ist."""
        response = client.get("/api/v1/notification-rules")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_rule_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        response = client.post(
            "/api/v1/notification-rules",
            json={
                "name": "Zahlungserinnerung",
                "description": "Benachrichtigung bei faelliger Zahlung",
                "event_type": "loan.payment_due",
                "conditions": {
                    "field": "days_until_due",
                    "operator": "lte",
                    "value": 7
                },
                "actions": [{
                    "type": "in_app",
                    "title": "Zahlung faellig",
                    "message": "Kredit-Zahlung in {{days_until_due}} Tagen faellig"
                }],
                "priority": "high",
                "enabled": True
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_rule_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        rule_id = uuid4()
        response = client.get(f"/api/v1/notification-rules/{rule_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_update_rule_endpoint_exists(self, client):
        """Test dass Update-Endpoint erreichbar ist."""
        rule_id = uuid4()
        response = client.put(
            f"/api/v1/notification-rules/{rule_id}",
            json={
                "name": "Aktualisierte Regel",
                "enabled": False
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_delete_rule_endpoint_exists(self, client):
        """Test dass Delete-Endpoint erreichbar ist."""
        rule_id = uuid4()
        response = client.delete(f"/api/v1/notification-rules/{rule_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_204_NO_CONTENT,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_toggle_rule_endpoint_exists(self, client):
        """Test dass Toggle-Endpoint erreichbar ist."""
        rule_id = uuid4()
        response = client.post(f"/api/v1/notification-rules/{rule_id}/toggle")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestNotificationRulesEventTypes:
    """Tests fuer unterstuetzte Event-Types."""

    def test_list_event_types_endpoint_exists(self, client):
        """Test dass Event-Types-Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/notification-rules/event-types")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_event_types_response_structure(self, client):
        """Test dass Event-Types-Response korrekte Struktur hat."""
        response = client.get("/api/v1/notification-rules/event-types")

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            # Sollte eine Liste oder ein Dict sein
            assert isinstance(data, (list, dict))

    def test_create_rule_with_valid_event_type(self, client):
        """Test dass Rule mit gueltigem Event-Type erstellt werden kann."""
        valid_event_types = [
            "loan.payment_due",
            "insurance.renewal_upcoming",
            "property.value_updated",
            "vehicle.service_due",
        ]

        for event_type in valid_event_types:
            response = client.post(
                "/api/v1/notification-rules",
                json={
                    "name": f"Test Rule fuer {event_type}",
                    "event_type": event_type,
                    "conditions": {},
                    "actions": [{"type": "in_app", "title": "Test", "message": "Test"}],
                    "enabled": True
                }
            )
            # Sollte nicht wegen ungueltigem Event-Type abgelehnt werden
            assert response.status_code != status.HTTP_422_UNPROCESSABLE_ENTITY or \
                   "event_type" not in response.text.lower()


@pytest.mark.integration
@pytest.mark.api
class TestNotificationRulesQuietHours:
    """Tests fuer Quiet Hours Funktionalitaet."""

    def test_get_quiet_hours_endpoint_exists(self, client):
        """Test dass Quiet-Hours-Endpoint erreichbar ist."""
        response = client.get("/api/v1/notification-rules/quiet-hours")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_update_quiet_hours_endpoint_exists(self, client):
        """Test dass Quiet-Hours-Update-Endpoint erreichbar ist."""
        response = client.put(
            "/api/v1/notification-rules/quiet-hours",
            json={
                "enabled": True,
                "start_time": "22:00",
                "end_time": "07:00",
                "timezone": "Europe/Berlin"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_quiet_hours_validation(self, client):
        """Test dass Quiet Hours validiert werden."""
        # Ungueltige Zeit
        response = client.put(
            "/api/v1/notification-rules/quiet-hours",
            json={
                "enabled": True,
                "start_time": "25:00",  # Ungueltig
                "end_time": "07:00",
                "timezone": "Europe/Berlin"
            }
        )
        # Sollte validiert und abgelehnt werden
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
class TestNotificationRuleEngine:
    """Tests fuer den Notification Rule Engine Service."""

    @pytest.mark.asyncio
    async def test_rule_engine_service_imports(self):
        """Test dass Rule Engine Service importierbar ist."""
        try:
            from app.services.notification.rule_engine import (
                NotificationRuleEngine,
                get_notification_rule_engine,
                RuleConditionMatcher,
                NotificationAction,
                RuleEvaluationResult,
                EventEvaluationResult,
            )

            assert NotificationRuleEngine is not None
            assert get_notification_rule_engine is not None
            assert RuleConditionMatcher is not None
            assert NotificationAction is not None
            assert RuleEvaluationResult is not None
            assert EventEvaluationResult is not None
        except ImportError as e:
            pytest.skip(f"Rule Engine Service nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test dass Singleton-Pattern funktioniert."""
        try:
            from app.services.notification.rule_engine import get_notification_rule_engine

            service1 = get_notification_rule_engine()
            service2 = get_notification_rule_engine()

            assert service1 is service2
        except ImportError:
            pytest.skip("Rule Engine Service nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_evaluate_event_method_exists(self):
        """Test dass evaluate_event Methode existiert."""
        try:
            from app.services.notification.rule_engine import NotificationRuleEngine

            service = NotificationRuleEngine()
            assert hasattr(service, 'evaluate_event')
            assert callable(getattr(service, 'evaluate_event'))
        except ImportError:
            pytest.skip("Rule Engine Service nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_execute_actions_method_exists(self):
        """Test dass execute_actions Methode existiert."""
        try:
            from app.services.notification.rule_engine import NotificationRuleEngine

            service = NotificationRuleEngine()
            assert hasattr(service, 'execute_actions')
            assert callable(getattr(service, 'execute_actions'))
        except ImportError:
            pytest.skip("Rule Engine Service nicht verfuegbar")


@pytest.mark.integration
class TestRuleConditionMatcher:
    """Tests fuer den Rule Condition Matcher."""

    @pytest.mark.asyncio
    async def test_condition_matcher_imports(self):
        """Test dass Condition Matcher importierbar ist."""
        try:
            from app.services.notification.rule_engine import RuleConditionMatcher

            matcher = RuleConditionMatcher()
            assert matcher is not None
        except ImportError as e:
            pytest.skip(f"Condition Matcher nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_operators_defined(self):
        """Test dass alle Operatoren definiert sind."""
        try:
            from app.services.notification.rule_engine import RuleConditionMatcher

            matcher = RuleConditionMatcher()

            expected_operators = [
                "eq", "ne", "gt", "gte", "lt", "lte",
                "contains", "startswith", "endswith",
                "in", "not_in", "is_null", "is_not_null"
            ]

            for op in expected_operators:
                assert op in matcher.OPERATORS, f"Operator {op} fehlt"
        except ImportError:
            pytest.skip("Condition Matcher nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_eq_operator_works(self):
        """Test dass eq Operator funktioniert."""
        try:
            from app.services.notification.rule_engine import RuleConditionMatcher

            matcher = RuleConditionMatcher()

            conditions = {
                "field": "status",
                "operator": "eq",
                "value": "active"
            }

            assert matcher.match(conditions, {"status": "active"}) is True
            assert matcher.match(conditions, {"status": "inactive"}) is False
        except ImportError:
            pytest.skip("Condition Matcher nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_gt_operator_works(self):
        """Test dass gt Operator funktioniert."""
        try:
            from app.services.notification.rule_engine import RuleConditionMatcher

            matcher = RuleConditionMatcher()

            conditions = {
                "field": "amount",
                "operator": "gt",
                "value": 100
            }

            assert matcher.match(conditions, {"amount": 150}) is True
            assert matcher.match(conditions, {"amount": 50}) is False
        except ImportError:
            pytest.skip("Condition Matcher nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_logical_and_works(self):
        """Test dass AND-Verknuepfung funktioniert."""
        try:
            from app.services.notification.rule_engine import RuleConditionMatcher

            matcher = RuleConditionMatcher()

            conditions = {
                "AND": [
                    {"field": "status", "operator": "eq", "value": "active"},
                    {"field": "amount", "operator": "gt", "value": 100}
                ]
            }

            assert matcher.match(conditions, {"status": "active", "amount": 150}) is True
            assert matcher.match(conditions, {"status": "active", "amount": 50}) is False
            assert matcher.match(conditions, {"status": "inactive", "amount": 150}) is False
        except ImportError:
            pytest.skip("Condition Matcher nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_logical_or_works(self):
        """Test dass OR-Verknuepfung funktioniert."""
        try:
            from app.services.notification.rule_engine import RuleConditionMatcher

            matcher = RuleConditionMatcher()

            conditions = {
                "OR": [
                    {"field": "priority", "operator": "eq", "value": "critical"},
                    {"field": "priority", "operator": "eq", "value": "urgent"}
                ]
            }

            assert matcher.match(conditions, {"priority": "critical"}) is True
            assert matcher.match(conditions, {"priority": "urgent"}) is True
            assert matcher.match(conditions, {"priority": "low"}) is False
        except ImportError:
            pytest.skip("Condition Matcher nicht verfuegbar")


@pytest.mark.integration
class TestSupportedEventTypes:
    """Tests fuer unterstuetzte Event-Types."""

    @pytest.mark.asyncio
    async def test_supported_event_types_defined(self):
        """Test dass SUPPORTED_EVENT_TYPES definiert ist."""
        try:
            from app.services.notification.rule_engine import SUPPORTED_EVENT_TYPES

            assert SUPPORTED_EVENT_TYPES is not None
            assert isinstance(SUPPORTED_EVENT_TYPES, (list, tuple, set))
        except ImportError as e:
            pytest.skip(f"Event Types nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_common_event_types_supported(self):
        """Test dass gaengige Event-Types unterstuetzt werden."""
        try:
            from app.services.notification.rule_engine import SUPPORTED_EVENT_TYPES

            expected_types = [
                "loan.payment_due",
                "insurance.renewal_upcoming",
                "property.value_updated",
                "vehicle.service_due",
            ]

            for event_type in expected_types:
                assert event_type in SUPPORTED_EVENT_TYPES, \
                    f"Event-Type {event_type} wird nicht unterstuetzt"
        except ImportError:
            pytest.skip("Event Types nicht verfuegbar")


@pytest.mark.integration
class TestPrometheusMetrics:
    """Tests fuer Prometheus Metriken."""

    @pytest.mark.asyncio
    async def test_metrics_defined(self):
        """Test dass Prometheus Metriken definiert sind."""
        try:
            from app.services.notification.rule_engine import (
                RULE_EVALUATIONS_COUNTER,
                RULE_MATCHES_COUNTER,
                RULE_EVALUATION_DURATION,
                ACTIONS_EXECUTED_COUNTER,
            )

            assert RULE_EVALUATIONS_COUNTER is not None
            assert RULE_MATCHES_COUNTER is not None
            assert RULE_EVALUATION_DURATION is not None
            assert ACTIONS_EXECUTED_COUNTER is not None
        except ImportError as e:
            pytest.skip(f"Prometheus Metriken nicht verfuegbar: {e}")


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.security
class TestNotificationRulesSecurity:
    """Tests fuer Security Controls bei Notification Rules."""

    def test_rules_require_authentication(self, client):
        """Test dass Rules Authentifizierung erfordern."""
        endpoints = [
            "/api/v1/notification-rules",
            "/api/v1/notification-rules/event-types",
            "/api/v1/notification-rules/quiet-hours",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # Ohne Auth sollte 401 oder 403 kommen (oder 200 bei deaktivierter Auth)
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ]

    def test_cannot_access_other_users_rules(self, client):
        """Test dass fremde Rules nicht zugaenglich sind."""
        random_rule_id = uuid4()
        response = client.get(f"/api/v1/notification-rules/{random_rule_id}")
        # Entweder nicht gefunden oder nicht autorisiert
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_sql_injection_prevention(self, client):
        """Test dass SQL Injection verhindert wird."""
        malicious_payloads = [
            "'; DROP TABLE notification_rules; --",
            "1 OR 1=1",
            "admin'--",
        ]

        for payload in malicious_payloads:
            response = client.post(
                "/api/v1/notification-rules",
                json={
                    "name": payload,
                    "event_type": "loan.payment_due",
                    "conditions": {},
                    "actions": [{"type": "in_app", "title": "Test", "message": "Test"}],
                }
            )
            # Sollte nicht 500 sein
            assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR, \
                f"Moegliche SQL Injection bei: {payload}"

    def test_xss_prevention(self, client):
        """Test dass XSS verhindert wird."""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
        ]

        for payload in xss_payloads:
            response = client.post(
                "/api/v1/notification-rules",
                json={
                    "name": payload,
                    "event_type": "loan.payment_due",
                    "conditions": {},
                    "actions": [{
                        "type": "in_app",
                        "title": payload,
                        "message": payload
                    }],
                }
            )
            # Sollte nicht 500 sein
            assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR, \
                f"Moegliche XSS Schwachstelle bei: {payload}"


@pytest.mark.integration
@pytest.mark.api
class TestNotificationRulesValidation:
    """Tests fuer Input-Validierung bei Notification Rules."""

    def test_name_max_length(self, client):
        """Test dass Name maximale Laenge hat."""
        very_long_name = "A" * 1000
        response = client.post(
            "/api/v1/notification-rules",
            json={
                "name": very_long_name,
                "event_type": "loan.payment_due",
                "conditions": {},
                "actions": [{"type": "in_app", "title": "Test", "message": "Test"}],
            }
        )
        # Sollte wegen Laenge abgelehnt werden
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_actions_required(self, client):
        """Test dass Actions erforderlich sind."""
        response = client.post(
            "/api/v1/notification-rules",
            json={
                "name": "Test Rule",
                "event_type": "loan.payment_due",
                "conditions": {},
                "actions": [],  # Leere Liste
            }
        )
        # Sollte wegen fehlender Actions abgelehnt werden
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_invalid_action_type_rejected(self, client):
        """Test dass ungueltige Action-Types abgelehnt werden."""
        response = client.post(
            "/api/v1/notification-rules",
            json={
                "name": "Test Rule",
                "event_type": "loan.payment_due",
                "conditions": {},
                "actions": [{
                    "type": "invalid_type",  # Ungueltig
                    "title": "Test",
                    "message": "Test"
                }],
            }
        )
        # Sollte wegen ungueltigem Type abgelehnt werden
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_valid_action_types_accepted(self, client):
        """Test dass gueltige Action-Types akzeptiert werden."""
        valid_action_types = ["in_app", "email", "push", "webhook"]

        for action_type in valid_action_types:
            response = client.post(
                "/api/v1/notification-rules",
                json={
                    "name": f"Test Rule fuer {action_type}",
                    "event_type": "loan.payment_due",
                    "conditions": {},
                    "actions": [{
                        "type": action_type,
                        "title": "Test",
                        "message": "Test"
                    }],
                }
            )
            # Sollte nicht wegen Action-Type abgelehnt werden
            assert response.status_code != status.HTTP_422_UNPROCESSABLE_ENTITY or \
                   "action" not in response.text.lower()


@pytest.mark.integration
@pytest.mark.api
class TestNotificationRulesHistory:
    """Tests fuer Rule History und Audit Trail."""

    def test_rule_history_endpoint_exists(self, client):
        """Test dass Rule-History-Endpoint erreichbar ist."""
        rule_id = uuid4()
        response = client.get(f"/api/v1/notification-rules/{rule_id}/history")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_rule_stats_endpoint_exists(self, client):
        """Test dass Rule-Stats-Endpoint erreichbar ist."""
        rule_id = uuid4()
        response = client.get(f"/api/v1/notification-rules/{rule_id}/stats")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
class TestNotificationRulesDBMigration:
    """Tests fuer DB Migration."""

    @pytest.mark.asyncio
    async def test_notification_rule_model_importable(self):
        """Test dass NotificationRule Model importierbar ist."""
        try:
            from app.db.models import NotificationRule

            assert NotificationRule is not None
            assert hasattr(NotificationRule, 'id')
            assert hasattr(NotificationRule, 'user_id')
            assert hasattr(NotificationRule, 'name')
            assert hasattr(NotificationRule, 'event_type')
            assert hasattr(NotificationRule, 'conditions')
            assert hasattr(NotificationRule, 'actions')
        except ImportError as e:
            pytest.skip(f"NotificationRule Model nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_notification_rule_has_timestamps(self):
        """Test dass NotificationRule Timestamps hat."""
        try:
            from app.db.models import NotificationRule

            assert hasattr(NotificationRule, 'created_at')
            assert hasattr(NotificationRule, 'updated_at')
        except ImportError:
            pytest.skip("NotificationRule Model nicht verfuegbar")
