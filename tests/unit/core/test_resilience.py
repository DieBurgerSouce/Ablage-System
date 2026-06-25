# -*- coding: utf-8 -*-
"""
Tests fuer app.core.resilience

Testet:
- CircuitBreaker State Machine
- Circuit Breaker Decorator (sync/async)
- Retry mit Backoff
- Bulkhead Concurrent Limits
- Registry Singleton
- OCR Circuit Breaker Helper
"""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest

from app.core.resilience import (
    Bulkhead,
    BulkheadFullError,
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    CircuitBreakerState,
    circuit_breaker,
    get_ocr_circuit_breaker,
    retry_with_backoff,
)


# =============================================================================
# CircuitBreaker Tests
# =============================================================================

class TestCircuitBreaker:
    """Tests fuer CircuitBreaker State Machine."""

    def test_initial_state_is_closed(self):
        """Circuit Breaker startet im CLOSED State."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0

    def test_can_execute_when_closed(self):
        """Calls sind erlaubt im CLOSED State."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        assert breaker.can_execute() is True

    def test_record_success_increments_count(self):
        """record_success() erhoeht success_count."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        breaker.record_success()
        assert breaker.success_count == 1

    def test_record_failure_increments_count(self):
        """record_failure() erhoeht failure_count."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        breaker.record_failure()
        assert breaker.failure_count == 1

    def test_transition_to_open_on_threshold(self):
        """Circuit oeffnet bei failure_threshold."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        # Record 2 failures -> still CLOSED
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.CLOSED

        # Third failure -> OPEN
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

    def test_cannot_execute_when_open(self):
        """Calls werden abgelehnt im OPEN State."""
        breaker = CircuitBreaker(name="test", failure_threshold=2)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.can_execute() is False

    def test_transition_to_half_open_after_timeout(self):
        """Circuit wechselt zu HALF_OPEN nach recovery_timeout."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout_seconds=0.1  # 100ms for fast test
        )

        # Open circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Check can_execute triggers transition
        assert breaker.can_execute() is True
        assert breaker.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """HALF_OPEN -> CLOSED nach successful calls."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout_seconds=0.1,
            half_open_max_calls=2
        )

        # Open circuit
        breaker.record_failure()
        breaker.record_failure()

        # Wait and transition to HALF_OPEN
        time.sleep(0.15)
        breaker.can_execute()
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        # Record successful calls
        breaker.record_success()
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        breaker.record_success()  # Second success
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """HALF_OPEN -> OPEN bei Fehler."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout_seconds=0.1
        )

        # Open circuit
        breaker.record_failure()
        breaker.record_failure()

        # Transition to HALF_OPEN
        time.sleep(0.15)
        breaker.can_execute()
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        # Record failure -> back to OPEN
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

    def test_reset_clears_counters(self):
        """reset() setzt Counters zurueck."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        breaker.record_failure()
        breaker.record_success()

        breaker.reset()
        assert breaker.failure_count == 0
        assert breaker.success_count == 0

    def test_thread_safety(self):
        """Circuit Breaker ist thread-safe."""
        breaker = CircuitBreaker(name="test", failure_threshold=100)

        def record_failures():
            for _ in range(10):
                breaker.record_failure()

        import threading
        threads = [threading.Thread(target=record_failures) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert breaker.failure_count == 50


# =============================================================================
# CircuitBreakerRegistry Tests
# =============================================================================

class TestCircuitBreakerRegistry:
    """Tests fuer CircuitBreakerRegistry Singleton."""

    def test_singleton_returns_same_instance(self):
        """get_instance() gibt immer dieselbe Instance zurueck."""
        registry1 = CircuitBreakerRegistry.get_instance()
        registry2 = CircuitBreakerRegistry.get_instance()
        assert registry1 is registry2

    def test_get_or_create_creates_new_breaker(self):
        """get_or_create() erstellt neuen Breaker."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker = registry.get_or_create("test_service")
        assert breaker.name == "test_service"

    def test_get_or_create_returns_existing_breaker(self):
        """get_or_create() gibt existierenden Breaker zurueck."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker1 = registry.get_or_create("test_service2")
        breaker2 = registry.get_or_create("test_service2")
        assert breaker1 is breaker2

    def test_get_all_states(self):
        """get_all_states() gibt States aller Breaker zurueck."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker1 = registry.get_or_create("service1")
        breaker2 = registry.get_or_create("service2")

        states = registry.get_all_states()
        assert "service1" in states
        assert "service2" in states
        assert states["service1"] == CircuitBreakerState.CLOSED
        assert states["service2"] == CircuitBreakerState.CLOSED


# =============================================================================
# Circuit Breaker Decorator Tests
# =============================================================================

class TestCircuitBreakerDecorator:
    """Tests fuer @circuit_breaker Decorator."""

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Async function wird normal ausgefuehrt."""
        call_count = 0

        @circuit_breaker("test_async", failure_threshold=2)
        async def async_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await async_func()
        assert result == "success"
        assert call_count == 1

    def test_sync_function_success(self):
        """Sync function wird normal ausgefuehrt."""
        call_count = 0

        @circuit_breaker("test_sync", failure_threshold=2)
        def sync_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = sync_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_function_opens_on_failures(self):
        """Circuit oeffnet nach Fehlern bei async function."""
        @circuit_breaker("test_open", failure_threshold=2)
        async def failing_func():
            raise ValueError("Test error")

        # First two calls fail
        with pytest.raises(ValueError):
            await failing_func()
        with pytest.raises(ValueError):
            await failing_func()

        # Third call is rejected (circuit OPEN)
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await failing_func()

        assert "test_open" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fallback_on_open_async(self):
        """Fallback wird bei OPEN Circuit aufgerufen (async)."""
        async def fallback_func():
            return "fallback"

        @circuit_breaker("test_fallback", failure_threshold=1, fallback=fallback_func)
        async def failing_func():
            raise ValueError("Test error")

        # First call fails
        with pytest.raises(ValueError):
            await failing_func()

        # Second call uses fallback
        result = await failing_func()
        assert result == "fallback"

    def test_fallback_on_open_sync(self):
        """Fallback wird bei OPEN Circuit aufgerufen (sync)."""
        def fallback_func():
            return "fallback"

        @circuit_breaker("test_fallback_sync", failure_threshold=1, fallback=fallback_func)
        def failing_func():
            raise ValueError("Test error")

        # First call fails
        with pytest.raises(ValueError):
            failing_func()

        # Second call uses fallback
        result = failing_func()
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_on_open_callback(self):
        """on_open callback wird bei Circuit OPEN aufgerufen."""
        callback_called = False

        def on_open_callback():
            nonlocal callback_called
            callback_called = True

        @circuit_breaker("test_callback", failure_threshold=1, on_open=on_open_callback)
        async def failing_func():
            raise ValueError("Test error")

        # First call fails
        with pytest.raises(ValueError):
            await failing_func()

        # Second call triggers on_open
        with pytest.raises(CircuitBreakerOpenError):
            await failing_func()

        assert callback_called is True


# =============================================================================
# Retry with Backoff Tests
# =============================================================================

class TestRetryWithBackoff:
    """Tests fuer @retry_with_backoff Decorator."""

    @pytest.mark.asyncio
    async def test_async_success_no_retry(self):
        """Erfolgreiche async function braucht kein Retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        async def async_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await async_func()
        assert result == "success"
        assert call_count == 1

    def test_sync_success_no_retry(self):
        """Erfolgreiche sync function braucht kein Retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def sync_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = sync_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_on_failure(self):
        """Async function wird bei Fehler retried."""
        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = await failing_func()
        assert result == "success"
        assert call_count == 3  # Initial + 2 retries

    def test_sync_retry_on_failure(self):
        """Sync function wird bei Fehler retried."""
        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = failing_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Exception wird geworfen nach max_retries."""
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        async def always_failing():
            raise ValueError("Permanent error")

        with pytest.raises(ValueError, match="Permanent error"):
            await always_failing()

    @pytest.mark.asyncio
    async def test_retryable_exceptions_filter(self):
        """Nur retryable_exceptions werden retried."""
        call_count = 0

        @retry_with_backoff(max_retries=3, retryable_exceptions=(IOError,))
        async def selective_retry():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Not retryable")
            return "success"

        # ValueError is not retryable -> immediate failure
        with pytest.raises(ValueError):
            await selective_retry()

        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Backoff Delay folgt exponential pattern."""
        delays = []

        @retry_with_backoff(
            max_retries=3,
            base_delay=0.1,
            exponential_base=2.0,
            jitter=False  # Disable jitter for predictable test
        )
        async def measure_backoff():
            # monotonic() statt time(): Wall-Clock kann rueckwaerts springen
            # (NTP-Resync, z.B. nach Reboot) -> negative Dauer -> Flake.
            delays.append(time.monotonic())
            if len(delays) < 3:
                raise ValueError("Retry")
            return "success"

        await measure_backoff()

        # Check delays are roughly exponential (with some tolerance)
        # First delay: ~0.1s, Second delay: ~0.2s
        if len(delays) >= 3:
            delay1 = delays[1] - delays[0]
            delay2 = delays[2] - delays[1]

            # Allow 50ms tolerance
            assert 0.05 < delay1 < 0.15
            assert 0.15 < delay2 < 0.25


# =============================================================================
# Bulkhead Tests
# =============================================================================

class TestBulkhead:
    """Tests fuer Bulkhead Pattern."""

    @pytest.mark.asyncio
    async def test_allows_concurrent_calls_up_to_limit(self):
        """Bulkhead erlaubt max_concurrent Calls."""
        bulkhead = Bulkhead(name="test", max_concurrent=2)

        call_count = 0

        async def task():
            nonlocal call_count
            async with bulkhead:
                call_count += 1
                await asyncio.sleep(0.05)

        # Run 2 concurrent tasks (should succeed)
        await asyncio.gather(task(), task())
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_rejects_calls_exceeding_limit(self):
        """Bulkhead wirft BulkheadFullError bei ueberschrittenem Limit."""
        bulkhead = Bulkhead(name="test", max_concurrent=1, max_queue=0)

        async def blocking_task():
            async with bulkhead:
                await asyncio.sleep(0.2)

        async def rejected_task():
            async with bulkhead:
                pass

        # Start blocking task
        task1 = asyncio.create_task(blocking_task())
        await asyncio.sleep(0.01)  # Let task1 acquire semaphore

        # Second task should be rejected (queue full)
        with pytest.raises(BulkheadFullError) as exc_info:
            await rejected_task()

        assert "test" in str(exc_info.value)

        await task1

    @pytest.mark.asyncio
    async def test_queue_allows_waiting_calls(self):
        """Bulkhead Queue erlaubt wartende Calls."""
        bulkhead = Bulkhead(name="test", max_concurrent=1, max_queue=2)

        results = []

        async def task(task_id):
            async with bulkhead:
                results.append(task_id)
                await asyncio.sleep(0.05)

        # Run 3 tasks (1 concurrent + 2 queued)
        await asyncio.gather(
            task("a"),
            task("b"),
            task("c")
        )

        assert len(results) == 3


# =============================================================================
# OCR Helper Tests
# =============================================================================

class TestOCRCircuitBreaker:
    """Tests fuer OCR-spezifische Circuit Breaker."""

    def test_get_ocr_circuit_breaker_creates_breaker(self):
        """get_ocr_circuit_breaker() erstellt Breaker mit OCR-Config."""
        breaker = get_ocr_circuit_breaker("deepseek")
        assert breaker.name == "ocr:deepseek"
        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout_seconds == 120.0

    def test_get_ocr_circuit_breaker_returns_same_instance(self):
        """Mehrere Calls geben dieselbe Breaker Instance zurueck."""
        breaker1 = get_ocr_circuit_breaker("got-ocr")
        breaker2 = get_ocr_circuit_breaker("got-ocr")
        assert breaker1 is breaker2


# =============================================================================
# Integration Tests
# =============================================================================

class TestResilienceIntegration:
    """Integration Tests fuer kombinierte Resilience Patterns."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_retry(self):
        """Circuit Breaker + Retry kombiniert."""
        call_count = 0

        @circuit_breaker("combined_test", failure_threshold=5)
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        async def flaky_service():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = await flaky_service()
        assert result == "success"
        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_bulkhead_with_circuit_breaker(self):
        """Bulkhead + Circuit Breaker kombiniert."""
        bulkhead = Bulkhead(name="limited_service", max_concurrent=1)

        @circuit_breaker("bulkhead_test", failure_threshold=2)
        async def limited_service():
            async with bulkhead:
                await asyncio.sleep(0.05)
                return "success"

        # Should succeed
        result = await limited_service()
        assert result == "success"
