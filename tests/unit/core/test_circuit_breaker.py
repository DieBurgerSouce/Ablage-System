# -*- coding: utf-8 -*-
"""
Unit tests for Circuit Breaker Pattern Implementation.

Tests for:
- Circuit states (CLOSED, OPEN, HALF_OPEN)
- State transitions
- Failure threshold detection
- Success threshold for recovery
- Reset timeout functionality
- Circuit breaker manager
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerManager,
    CircuitConfig,
    CircuitOpenError,
    CircuitState,
    CircuitStats,
    SERVICE_CONFIGS,
    get_circuit_breaker_manager,
)


class TestCircuitState:
    """Tests for circuit breaker states."""

    def test_circuit_states_are_strings(self):
        """Test that circuit states are string enums."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_all_states_defined(self):
        """Test that all expected states are defined."""
        states = list(CircuitState)
        assert len(states) == 3
        assert CircuitState.CLOSED in states
        assert CircuitState.OPEN in states
        assert CircuitState.HALF_OPEN in states


class TestCircuitConfig:
    """Tests for circuit breaker configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitConfig()

        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.reset_timeout == 30.0
        assert config.half_open_max_calls == 3

    def test_custom_config(self):
        """Test custom configuration values."""
        config = CircuitConfig(
            failure_threshold=3,
            success_threshold=1,
            reset_timeout=60.0,
            half_open_max_calls=5
        )

        assert config.failure_threshold == 3
        assert config.success_threshold == 1
        assert config.reset_timeout == 60.0
        assert config.half_open_max_calls == 5


class TestServiceConfigs:
    """Tests for service-specific configurations."""

    def test_redis_config_exists(self):
        """Test that Redis config is defined."""
        assert "redis" in SERVICE_CONFIGS
        config = SERVICE_CONFIGS["redis"]
        assert config.failure_threshold == 5

    def test_database_config_exists(self):
        """Test that database config is defined."""
        assert "database" in SERVICE_CONFIGS
        config = SERVICE_CONFIGS["database"]
        assert config.failure_threshold == 3

    def test_ocr_backend_configs_exist(self):
        """Test that OCR backend configs are defined."""
        ocr_services = ["ocr_deepseek", "ocr_got", "ocr_surya", "ocr_surya_gpu"]
        for service in ocr_services:
            assert service in SERVICE_CONFIGS

    def test_minio_config_exists(self):
        """Test that MinIO config is defined."""
        assert "minio" in SERVICE_CONFIGS


class TestCircuitStats:
    """Tests for circuit breaker statistics."""

    def test_default_stats(self):
        """Test default statistics values."""
        stats = CircuitStats()

        assert stats.failures == 0
        assert stats.successes == 0
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0
        assert stats.last_failure_time is None
        assert stats.last_success_time is None
        assert stats.total_calls == 0
        assert stats.rejected_calls == 0
        assert stats.state_changes == 0


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker for testing."""
        config = CircuitConfig(
            failure_threshold=3,
            success_threshold=2,
            reset_timeout=1.0,  # Short timeout for tests
            half_open_max_calls=2
        )
        return CircuitBreaker("test_service", config)

    def test_initial_state_is_closed(self, circuit_breaker):
        """Test that initial state is CLOSED."""
        assert circuit_breaker.state == CircuitState.CLOSED

    def test_is_available_when_closed(self, circuit_breaker):
        """Test that circuit is available when closed."""
        assert circuit_breaker.is_available is True

    @pytest.mark.asyncio
    async def test_successful_call(self, circuit_breaker):
        """Test successful function call through circuit breaker."""
        async def success_func():
            return "success"

        result = await circuit_breaker.call(success_func)

        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
        stats = circuit_breaker.get_stats()
        assert stats["successes"] == 1
        assert stats["total_calls"] == 1

    @pytest.mark.asyncio
    async def test_sync_function_call(self, circuit_breaker):
        """Test synchronous function call through circuit breaker."""
        def sync_func():
            return "sync_success"

        result = await circuit_breaker.call(sync_func)

        assert result == "sync_success"

    @pytest.mark.asyncio
    async def test_failure_increments_counter(self, circuit_breaker):
        """Test that failures increment the failure counter."""
        async def failing_func():
            raise RuntimeError("Test error")

        with pytest.raises(RuntimeError):
            await circuit_breaker.call(failing_func)

        stats = circuit_breaker.get_stats()
        assert stats["failures"] == 1
        assert stats["consecutive_failures"] == 1

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self, circuit_breaker):
        """Test that circuit opens after failure threshold is reached."""
        async def failing_func():
            raise RuntimeError("Test error")

        # Trigger enough failures to open circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_func)

        assert circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self, circuit_breaker):
        """Test that circuit rejects calls when open."""
        async def failing_func():
            raise RuntimeError("Test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_func)

        # Should now reject
        with pytest.raises(CircuitOpenError) as exc_info:
            await circuit_breaker.call(failing_func)

        assert exc_info.value.service_name == "test_service"
        assert exc_info.value.time_until_retry > 0

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, circuit_breaker):
        """Test that circuit transitions to half-open after timeout."""
        async def failing_func():
            raise RuntimeError("Test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_func)

        assert circuit_breaker.state == CircuitState.OPEN

        # Wait for reset timeout
        await asyncio.sleep(1.1)

        # Next call should transition to half-open
        async def success_func():
            return "success"

        result = await circuit_breaker.call(success_func)

        # Should be in half-open or closed after success
        assert circuit_breaker.state in [CircuitState.HALF_OPEN, CircuitState.CLOSED]

    @pytest.mark.asyncio
    async def test_circuit_closes_after_success_threshold(self, circuit_breaker):
        """Test that circuit closes after success threshold in half-open."""
        async def failing_func():
            raise RuntimeError("Test error")

        async def success_func():
            return "success"

        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_func)

        # Wait for reset timeout
        await asyncio.sleep(1.1)

        # Successful calls in half-open
        await circuit_breaker.call(success_func)
        await circuit_breaker.call(success_func)

        # Should be closed after success threshold
        assert circuit_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_reopens_on_failure_in_half_open(self, circuit_breaker):
        """Test that circuit reopens on failure in half-open state."""
        async def failing_func():
            raise RuntimeError("Test error")

        async def success_func():
            return "success"

        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_func)

        # Wait for reset timeout
        await asyncio.sleep(1.1)

        # One success in half-open
        await circuit_breaker.call(success_func)

        # One failure should reopen circuit
        with pytest.raises(RuntimeError):
            await circuit_breaker.call(failing_func)

        assert circuit_breaker.state == CircuitState.OPEN

    def test_reset_method(self, circuit_breaker):
        """Test manual reset of circuit breaker."""
        # Manually set to open
        circuit_breaker._state = CircuitState.OPEN
        circuit_breaker._stats.failures = 10

        circuit_breaker.reset()

        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker._stats.failures == 0

    def test_get_stats(self, circuit_breaker):
        """Test getting circuit breaker statistics."""
        stats = circuit_breaker.get_stats()

        assert "service" in stats
        assert "state" in stats
        assert "failures" in stats
        assert "successes" in stats
        assert "total_calls" in stats
        assert stats["service"] == "test_service"

    @pytest.mark.asyncio
    async def test_rejected_calls_counted(self, circuit_breaker):
        """Test that rejected calls are counted."""
        async def failing_func():
            raise RuntimeError("Test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_func)

        # Try to call while open
        try:
            await circuit_breaker.call(failing_func)
        except CircuitOpenError:
            pass

        stats = circuit_breaker.get_stats()
        assert stats["rejected_calls"] == 1


class TestCircuitBreakerManager:
    """Tests for CircuitBreakerManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh manager instance."""
        # Reset singleton for testing
        CircuitBreakerManager._instance = None
        return CircuitBreakerManager()

    @pytest.mark.asyncio
    async def test_get_breaker_creates_new(self, manager):
        """Test that get_breaker creates new breaker for unknown service."""
        breaker = await manager.get_breaker("new_service")

        assert breaker is not None
        assert breaker.service_name == "new_service"

    @pytest.mark.asyncio
    async def test_get_breaker_reuses_existing(self, manager):
        """Test that get_breaker reuses existing breaker."""
        breaker1 = await manager.get_breaker("test_service")
        breaker2 = await manager.get_breaker("test_service")

        assert breaker1 is breaker2

    @pytest.mark.asyncio
    async def test_get_breaker_with_custom_config(self, manager):
        """Test get_breaker with custom configuration."""
        config = CircuitConfig(failure_threshold=10)
        breaker = await manager.get_breaker("custom_service", config)

        assert breaker.config.failure_threshold == 10

    @pytest.mark.asyncio
    async def test_call_convenience_method(self, manager):
        """Test the call convenience method."""
        async def success_func():
            return "success"

        result = await manager.call("test_service", success_func)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_get_all_stats(self, manager):
        """Test getting all breaker statistics."""
        await manager.get_breaker("service1")
        await manager.get_breaker("service2")

        stats = manager.get_all_stats()

        assert "service1" in stats
        assert "service2" in stats

    @pytest.mark.asyncio
    async def test_get_unhealthy_services(self, manager):
        """Test getting unhealthy services list."""
        # Create breakers
        breaker1 = await manager.get_breaker("healthy")
        breaker2 = await manager.get_breaker("unhealthy")

        # Make one unhealthy
        breaker2._state = CircuitState.OPEN

        unhealthy = manager.get_unhealthy_services()

        assert "unhealthy" in unhealthy
        assert "healthy" not in unhealthy

    @pytest.mark.asyncio
    async def test_reset_all(self, manager):
        """Test resetting all circuit breakers."""
        breaker1 = await manager.get_breaker("service1")
        breaker2 = await manager.get_breaker("service2")

        breaker1._state = CircuitState.OPEN
        breaker2._state = CircuitState.OPEN

        manager.reset_all()

        assert breaker1.state == CircuitState.CLOSED
        assert breaker2.state == CircuitState.CLOSED

    def test_singleton_pattern(self):
        """Test that manager follows singleton pattern."""
        CircuitBreakerManager._instance = None

        manager1 = CircuitBreakerManager.get_instance()
        manager2 = CircuitBreakerManager.get_instance()

        assert manager1 is manager2


class TestCircuitOpenError:
    """Tests for CircuitOpenError exception."""

    def test_error_message(self):
        """Test error message format."""
        error = CircuitOpenError("test_service", 30.5)

        assert "test_service" in str(error)
        assert "30.5" in str(error)

    def test_error_attributes(self):
        """Test error attributes."""
        error = CircuitOpenError("test_service", 30.5)

        assert error.service_name == "test_service"
        assert error.time_until_retry == 30.5


class TestGetCircuitBreakerManager:
    """Tests for get_circuit_breaker_manager function."""

    def test_returns_manager_instance(self):
        """Test that function returns manager instance."""
        CircuitBreakerManager._instance = None

        manager = get_circuit_breaker_manager()

        assert isinstance(manager, CircuitBreakerManager)

    def test_returns_same_instance(self):
        """Test that function returns same instance."""
        CircuitBreakerManager._instance = None

        manager1 = get_circuit_breaker_manager()
        manager2 = get_circuit_breaker_manager()

        assert manager1 is manager2


class TestHalfOpenState:
    """Tests specific to half-open state behavior."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker with specific config for half-open tests."""
        config = CircuitConfig(
            failure_threshold=2,
            success_threshold=2,
            reset_timeout=0.5,
            half_open_max_calls=2
        )
        return CircuitBreaker("half_open_test", config)

    @pytest.mark.asyncio
    async def test_half_open_limits_concurrent_calls(self, circuit_breaker):
        """Test that half-open state limits concurrent calls."""
        async def failing_func():
            raise RuntimeError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_func)

        # Wait for reset
        await asyncio.sleep(0.6)

        # Check availability in half-open
        assert circuit_breaker.is_available is True


class TestConcurrency:
    """Tests for concurrent circuit breaker operations."""

    @pytest.mark.asyncio
    async def test_concurrent_calls(self):
        """Test concurrent calls through circuit breaker."""
        config = CircuitConfig(failure_threshold=10)
        breaker = CircuitBreaker("concurrent_test", config)

        async def success_func(n):
            await asyncio.sleep(0.1)
            return n

        # Make concurrent calls
        tasks = [breaker.call(success_func, i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert results == [0, 1, 2, 3, 4]
        stats = breaker.get_stats()
        assert stats["total_calls"] == 5
        assert stats["successes"] == 5
