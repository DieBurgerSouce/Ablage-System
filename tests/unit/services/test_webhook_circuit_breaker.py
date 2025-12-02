# -*- coding: utf-8 -*-
"""
Unit Tests for Webhook Circuit Breaker.

Tests the circuit breaker pattern implementation for webhook deliveries.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from app.services.webhook_dispatcher import (
    WebhookCircuitBreaker,
    CircuitState,
    DeliveryStatus,
    get_webhook_circuit_breaker,
)


# =============================================================================
# CIRCUIT BREAKER STATE TESTS
# =============================================================================


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions."""

    def test_initial_state_is_closed(self):
        """Neuer Circuit Breaker sollte im CLOSED Zustand sein."""
        cb = WebhookCircuitBreaker()
        state = cb.get_state("https://example.com/webhook")
        assert state == CircuitState.CLOSED

    def test_state_closed_after_few_failures(self):
        """Circuit sollte nach wenigen Fehlern noch CLOSED sein."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # 4 failures (under threshold of 5)
        for _ in range(4):
            cb.record_failure(url)

        assert cb.get_state(url) == CircuitState.CLOSED

    def test_state_opens_after_threshold(self):
        """Circuit sollte nach FAILURE_THRESHOLD Fehlern OPEN werden."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Trigger 5 failures (threshold)
        for _ in range(5):
            cb.record_failure(url)

        assert cb.get_state(url) == CircuitState.OPEN

    def test_is_allowed_when_closed(self):
        """Requests sollten bei CLOSED durchgelassen werden."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        assert cb.is_allowed(url) is True

    def test_is_not_allowed_when_open(self):
        """Requests sollten bei OPEN blockiert werden."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        assert cb.is_allowed(url) is False

    def test_success_resets_failure_count_when_closed(self):
        """Erfolg sollte Fehler-Zaehler bei CLOSED zuruecksetzen."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Add some failures
        for _ in range(3):
            cb.record_failure(url)

        # Record success
        cb.record_success(url)

        # Now 5 more failures should be needed to open
        for _ in range(4):
            cb.record_failure(url)

        assert cb.get_state(url) == CircuitState.CLOSED

        # One more failure should open it
        cb.record_failure(url)
        assert cb.get_state(url) == CircuitState.OPEN


class TestCircuitBreakerHalfOpen:
    """Test half-open state behavior."""

    def test_transitions_to_half_open_after_timeout(self):
        """Circuit sollte nach Timeout zu HALF_OPEN wechseln."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        assert cb.get_state(url) == CircuitState.OPEN

        # Simulate timeout by manipulating last_failure_time
        cb._last_failure_time[url] = datetime.now(timezone.utc) - timedelta(seconds=400)

        assert cb.get_state(url) == CircuitState.HALF_OPEN

    def test_half_open_allows_limited_calls(self):
        """HALF_OPEN sollte begrenzte Anzahl Test-Calls erlauben."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        # Simulate timeout
        cb._last_failure_time[url] = datetime.now(timezone.utc) - timedelta(seconds=400)

        # First HALF_OPEN_MAX_CALLS should be allowed
        for i in range(cb.HALF_OPEN_MAX_CALLS):
            assert cb.is_allowed(url) is True

        # Next should be blocked
        assert cb.is_allowed(url) is False

    def test_half_open_closes_on_success_threshold(self):
        """Circuit sollte nach SUCCESS_THRESHOLD Erfolgen zu CLOSED wechseln."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        # Transition to half-open
        cb._last_failure_time[url] = datetime.now(timezone.utc) - timedelta(seconds=400)
        cb.get_state(url)  # Trigger transition

        # Record successes
        for _ in range(cb.SUCCESS_THRESHOLD):
            cb.record_success(url)

        assert cb.get_state(url) == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        """Circuit sollte bei Fehler in HALF_OPEN sofort zu OPEN wechseln."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        # Transition to half-open
        cb._last_failure_time[url] = datetime.now(timezone.utc) - timedelta(seconds=400)
        cb.get_state(url)  # Trigger transition

        assert cb.get_state(url) == CircuitState.HALF_OPEN

        # Record a failure
        cb.record_failure(url)

        assert cb.get_state(url) == CircuitState.OPEN


# =============================================================================
# CIRCUIT BREAKER STATS TESTS
# =============================================================================


class TestCircuitBreakerStats:
    """Test circuit breaker statistics."""

    def test_get_stats_empty(self):
        """Stats sollten initial leer sein."""
        cb = WebhookCircuitBreaker()
        stats = cb.get_stats()

        assert stats["total_tracked"] == 0
        assert stats["by_state"]["closed"] == 0
        assert stats["by_state"]["open"] == 0
        assert stats["by_state"]["half_open"] == 0
        assert len(stats["open_circuits"]) == 0

    def test_get_stats_counts_states(self):
        """Stats sollten Zustaende korrekt zaehlen."""
        cb = WebhookCircuitBreaker()

        # Add URLs in different states
        cb._states["https://closed.example.com"] = CircuitState.CLOSED
        cb._states["https://open1.example.com"] = CircuitState.OPEN
        cb._states["https://open2.example.com"] = CircuitState.OPEN
        cb._last_failure_time["https://open1.example.com"] = datetime.now(timezone.utc)
        cb._last_failure_time["https://open2.example.com"] = datetime.now(timezone.utc)

        stats = cb.get_stats()

        assert stats["total_tracked"] == 3
        assert stats["by_state"]["closed"] == 1
        assert stats["by_state"]["open"] == 2
        assert len(stats["open_circuits"]) == 2

    def test_get_stats_includes_open_circuit_details(self):
        """Stats sollten Details zu offenen Circuits enthalten."""
        cb = WebhookCircuitBreaker()
        url = "https://failing.example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        stats = cb.get_stats()

        assert len(stats["open_circuits"]) == 1
        open_circuit = stats["open_circuits"][0]
        assert "failing.example.com" in open_circuit["url"]
        assert open_circuit["state"] == "open"
        assert open_circuit["failures"] == 5


# =============================================================================
# CIRCUIT BREAKER RESET TESTS
# =============================================================================


class TestCircuitBreakerReset:
    """Test circuit breaker reset functionality."""

    def test_reset_single_url(self):
        """Reset sollte einzelne URL zuruecksetzen."""
        cb = WebhookCircuitBreaker()
        url1 = "https://example1.com/webhook"
        url2 = "https://example2.com/webhook"

        # Open both circuits
        for _ in range(5):
            cb.record_failure(url1)
            cb.record_failure(url2)

        assert cb.get_state(url1) == CircuitState.OPEN
        assert cb.get_state(url2) == CircuitState.OPEN

        # Reset only url1
        cb.reset(url1)

        assert cb.get_state(url1) == CircuitState.CLOSED
        assert cb.get_state(url2) == CircuitState.OPEN

    def test_reset_all(self):
        """Reset ohne URL sollte alle zuruecksetzen."""
        cb = WebhookCircuitBreaker()
        url1 = "https://example1.com/webhook"
        url2 = "https://example2.com/webhook"

        # Open both circuits
        for _ in range(5):
            cb.record_failure(url1)
            cb.record_failure(url2)

        # Reset all
        cb.reset()

        assert cb.get_state(url1) == CircuitState.CLOSED
        assert cb.get_state(url2) == CircuitState.CLOSED
        assert len(cb._states) == 0


# =============================================================================
# GLOBAL CIRCUIT BREAKER TESTS
# =============================================================================


class TestGlobalCircuitBreaker:
    """Test global circuit breaker singleton."""

    def test_get_webhook_circuit_breaker_returns_singleton(self):
        """get_webhook_circuit_breaker sollte Singleton zurueckgeben."""
        cb1 = get_webhook_circuit_breaker()
        cb2 = get_webhook_circuit_breaker()

        assert cb1 is cb2

    def test_get_webhook_circuit_breaker_creates_instance(self):
        """get_webhook_circuit_breaker sollte Instanz erstellen."""
        cb = get_webhook_circuit_breaker()

        assert isinstance(cb, WebhookCircuitBreaker)


# =============================================================================
# METRICS INTEGRATION TESTS
# =============================================================================


class TestCircuitBreakerMetrics:
    """Test circuit breaker Prometheus metrics integration."""

    @patch("app.services.webhook_dispatcher.record_circuit_breaker_transition")
    @patch("app.services.webhook_dispatcher.update_circuit_breaker_metrics")
    def test_records_transition_closed_to_open(
        self, mock_update, mock_transition
    ):
        """Transition CLOSED -> OPEN sollte Metriken aktualisieren."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        mock_transition.assert_called_with("closed", "open")
        mock_update.assert_called()

    @patch("app.services.webhook_dispatcher.record_circuit_breaker_transition")
    @patch("app.services.webhook_dispatcher.update_circuit_breaker_metrics")
    def test_records_transition_open_to_half_open(
        self, mock_update, mock_transition
    ):
        """Transition OPEN -> HALF_OPEN sollte Metriken aktualisieren."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open the circuit
        for _ in range(5):
            cb.record_failure(url)

        mock_transition.reset_mock()
        mock_update.reset_mock()

        # Simulate timeout
        cb._last_failure_time[url] = datetime.now(timezone.utc) - timedelta(seconds=400)
        cb.get_state(url)  # Trigger transition

        mock_transition.assert_called_with("open", "half_open")
        mock_update.assert_called()

    @patch("app.services.webhook_dispatcher.record_circuit_breaker_transition")
    @patch("app.services.webhook_dispatcher.update_circuit_breaker_metrics")
    def test_records_transition_half_open_to_closed(
        self, mock_update, mock_transition
    ):
        """Transition HALF_OPEN -> CLOSED sollte Metriken aktualisieren."""
        cb = WebhookCircuitBreaker()
        url = "https://example.com/webhook"

        # Open and transition to half-open
        for _ in range(5):
            cb.record_failure(url)
        cb._last_failure_time[url] = datetime.now(timezone.utc) - timedelta(seconds=400)
        cb.get_state(url)

        mock_transition.reset_mock()
        mock_update.reset_mock()

        # Record enough successes to close
        for _ in range(cb.SUCCESS_THRESHOLD):
            cb.record_success(url)

        mock_transition.assert_called_with("half_open", "closed")
        mock_update.assert_called()


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================


class TestCircuitBreakerConfiguration:
    """Test circuit breaker configuration values."""

    def test_default_configuration(self):
        """Standardkonfiguration sollte korrekt sein."""
        cb = WebhookCircuitBreaker()

        assert cb.FAILURE_THRESHOLD == 5
        assert cb.SUCCESS_THRESHOLD == 2
        assert cb.OPEN_TIMEOUT_SECONDS == 300
        assert cb.HALF_OPEN_MAX_CALLS == 3


# =============================================================================
# DELIVERY STATUS ENUM TESTS
# =============================================================================


class TestDeliveryStatusEnum:
    """Test DeliveryStatus enum values."""

    def test_circuit_open_status_exists(self):
        """CIRCUIT_OPEN Status sollte existieren."""
        assert DeliveryStatus.CIRCUIT_OPEN.value == "circuit_open"

    def test_all_status_values(self):
        """Alle Status-Werte sollten korrekt sein."""
        assert DeliveryStatus.PENDING.value == "pending"
        assert DeliveryStatus.SUCCESS.value == "success"
        assert DeliveryStatus.FAILED.value == "failed"
        assert DeliveryStatus.RETRYING.value == "retrying"
        assert DeliveryStatus.CIRCUIT_OPEN.value == "circuit_open"
