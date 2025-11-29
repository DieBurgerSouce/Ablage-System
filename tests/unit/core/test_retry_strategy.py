# -*- coding: utf-8 -*-
"""
Unit tests for Retry Strategy with Exponential Backoff.

Tests for:
- Retry configuration
- Exponential backoff calculation
- Jitter application
- Non-retryable exceptions
- Workflow phase-specific configs
- Retry exhaustion
- Retry context manager
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from app.core.retry_strategy import (
    RetryStrategy,
    RetryConfig,
    RetryContext,
    RetryExhaustedError,
    WorkflowPhase,
    PHASE_CONFIGS,
    NON_RETRYABLE_EXCEPTIONS,
    get_retry_strategy,
)


class TestWorkflowPhase:
    """Tests for WorkflowPhase enum."""

    def test_all_phases_defined(self):
        """Test that all expected workflow phases are defined."""
        phases = list(WorkflowPhase)
        expected = [
            "classification",
            "preprocessing",
            "ocr",
            "postprocessing",
            "qa",
            "storage"
        ]
        assert len(phases) == len(expected)
        for phase in expected:
            assert phase in [p.value for p in phases]

    def test_phases_are_strings(self):
        """Test that phases have string values."""
        assert WorkflowPhase.CLASSIFICATION.value == "classification"
        assert WorkflowPhase.OCR.value == "ocr"


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter == 0.1

    def test_custom_config(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0,
            jitter=0.2
        )

        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0
        assert config.jitter == 0.2


class TestPhaseConfigs:
    """Tests for phase-specific configurations."""

    def test_all_phases_have_config(self):
        """Test that all workflow phases have configurations."""
        for phase in WorkflowPhase:
            assert phase in PHASE_CONFIGS

    def test_ocr_phase_config(self):
        """Test OCR phase has appropriate config."""
        config = PHASE_CONFIGS[WorkflowPhase.OCR]
        assert config.max_retries == 2
        assert config.base_delay >= 1.0

    def test_storage_phase_config(self):
        """Test storage phase has higher retries."""
        config = PHASE_CONFIGS[WorkflowPhase.STORAGE]
        assert config.max_retries == 5  # More retries for storage


class TestNonRetryableExceptions:
    """Tests for non-retryable exception configuration."""

    def test_value_error_not_retryable(self):
        """Test that ValueError is not retryable."""
        assert ValueError in NON_RETRYABLE_EXCEPTIONS

    def test_type_error_not_retryable(self):
        """Test that TypeError is not retryable."""
        assert TypeError in NON_RETRYABLE_EXCEPTIONS

    def test_key_error_not_retryable(self):
        """Test that KeyError is not retryable."""
        assert KeyError in NON_RETRYABLE_EXCEPTIONS

    def test_permission_error_not_retryable(self):
        """Test that PermissionError is not retryable."""
        assert PermissionError in NON_RETRYABLE_EXCEPTIONS


class TestRetryStrategy:
    """Tests for RetryStrategy class."""

    @pytest.fixture
    def strategy(self):
        """Create a retry strategy for testing."""
        return RetryStrategy()

    def test_default_config(self, strategy):
        """Test default configuration is applied."""
        assert strategy.default_config is not None
        assert strategy.default_config.max_retries == 3

    def test_get_config_for_known_phase(self, strategy):
        """Test getting config for known phase."""
        config = strategy.get_config(WorkflowPhase.OCR)
        assert config == PHASE_CONFIGS[WorkflowPhase.OCR]

    def test_calculate_delay_exponential(self, strategy):
        """Test exponential backoff calculation."""
        config = RetryConfig(
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=100.0,
            jitter=0.0  # No jitter for predictable testing
        )

        delay0 = strategy._calculate_delay(0, config)
        delay1 = strategy._calculate_delay(1, config)
        delay2 = strategy._calculate_delay(2, config)

        assert delay0 == 1.0  # 1 * 2^0 = 1
        assert delay1 == 2.0  # 1 * 2^1 = 2
        assert delay2 == 4.0  # 1 * 2^2 = 4

    def test_calculate_delay_respects_max(self, strategy):
        """Test that max_delay is respected."""
        config = RetryConfig(
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=5.0,
            jitter=0.0
        )

        delay = strategy._calculate_delay(10, config)  # Would be 1024 without cap

        assert delay == 5.0

    def test_calculate_delay_with_jitter(self, strategy):
        """Test that jitter is applied."""
        config = RetryConfig(
            base_delay=10.0,
            exponential_base=1.0,
            max_delay=100.0,
            jitter=0.5  # 50% jitter
        )

        # Run multiple times to check jitter variance
        delays = [strategy._calculate_delay(0, config) for _ in range(10)]

        # Not all delays should be exactly the same
        unique_delays = set(delays)
        assert len(unique_delays) > 1  # Jitter should create variation

    def test_should_retry_respects_max_retries(self, strategy):
        """Test that max_retries is respected."""
        config = RetryConfig(max_retries=3)

        assert strategy._should_retry(RuntimeError(), 0, config) is True
        assert strategy._should_retry(RuntimeError(), 2, config) is True
        assert strategy._should_retry(RuntimeError(), 3, config) is False  # At max

    def test_should_retry_rejects_non_retryable(self, strategy):
        """Test that non-retryable exceptions are rejected."""
        config = RetryConfig(max_retries=10)

        assert strategy._should_retry(ValueError("test"), 0, config) is False
        assert strategy._should_retry(TypeError("test"), 0, config) is False
        assert strategy._should_retry(KeyError("test"), 0, config) is False

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self, strategy):
        """Test successful execution on first try."""
        call_count = 0

        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await strategy.execute_with_retry(
            success_func,
            WorkflowPhase.OCR
        )

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_retries_on_failure(self, strategy):
        """Test that retries occur on transient failures."""
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Transient error")
            return "success"

        config = RetryConfig(
            max_retries=5,
            base_delay=0.01,  # Fast retries for testing
            jitter=0.0
        )

        result = await strategy.execute_with_retry(
            fail_then_succeed,
            WorkflowPhase.OCR,
            config=config
        )

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_execute_with_retry_exhausted(self, strategy):
        """Test retry exhaustion raises RetryExhaustedError."""
        async def always_fail():
            raise RuntimeError("Persistent error")

        config = RetryConfig(
            max_retries=2,
            base_delay=0.01,
            jitter=0.0
        )

        with pytest.raises(RetryExhaustedError) as exc_info:
            await strategy.execute_with_retry(
                always_fail,
                WorkflowPhase.OCR,
                config=config
            )

        assert exc_info.value.phase == "ocr"
        assert exc_info.value.max_retries == 2
        assert isinstance(exc_info.value.last_exception, RuntimeError)

    @pytest.mark.asyncio
    async def test_execute_with_retry_non_retryable_immediate(self, strategy):
        """Test that non-retryable exceptions are raised immediately."""
        call_count = 0

        async def raise_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid input")

        with pytest.raises(ValueError):
            await strategy.execute_with_retry(
                raise_value_error,
                WorkflowPhase.OCR
            )

        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_execute_with_retry_sync_function(self, strategy):
        """Test that sync functions are supported."""
        def sync_func():
            return "sync_result"

        config = RetryConfig(max_retries=1, base_delay=0.01)

        result = await strategy.execute_with_retry(
            sync_func,
            WorkflowPhase.CLASSIFICATION,
            config=config
        )

        assert result == "sync_result"

    @pytest.mark.asyncio
    async def test_on_retry_callback(self, strategy):
        """Test that on_retry callback is called."""
        retry_calls = []

        async def fail_twice():
            if len(retry_calls) < 2:
                raise RuntimeError("Error")
            return "success"

        def on_retry(attempt, exception):
            retry_calls.append((attempt, str(exception)))

        config = RetryConfig(
            max_retries=3,
            base_delay=0.01,
            jitter=0.0
        )

        await strategy.execute_with_retry(
            fail_twice,
            WorkflowPhase.OCR,
            config=config,
            on_retry=on_retry
        )

        assert len(retry_calls) == 2

    @pytest.mark.asyncio
    async def test_execute_with_retry_passes_args_kwargs(self, strategy):
        """Test that args and kwargs are passed correctly."""
        async def func_with_args(a, b, c=None):
            return (a, b, c)

        config = RetryConfig(max_retries=1, base_delay=0.01)

        result = await strategy.execute_with_retry(
            func_with_args,
            WorkflowPhase.QA,
            1, 2, c="three",
            config=config
        )

        assert result == (1, 2, "three")


class TestRetryExhaustedError:
    """Tests for RetryExhaustedError exception."""

    def test_error_message_format(self):
        """Test error message format."""
        error = RetryExhaustedError(
            phase="ocr",
            max_retries=3,
            last_exception=RuntimeError("Last error")
        )

        message = str(error)
        assert "3" in message
        assert "ocr" in message
        assert "Last error" in message

    def test_error_attributes(self):
        """Test error attributes are set correctly."""
        last_error = ValueError("Test")
        error = RetryExhaustedError(
            phase="storage",
            max_retries=5,
            last_exception=last_error
        )

        assert error.phase == "storage"
        assert error.max_retries == 5
        assert error.last_exception is last_error


class TestRetryContext:
    """Tests for RetryContext context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_entry_exit(self):
        """Test context manager enter and exit."""
        async with RetryContext(phase=WorkflowPhase.OCR) as ctx:
            assert ctx.phase == WorkflowPhase.OCR
            assert ctx.start_time is not None

    @pytest.mark.asyncio
    async def test_execute_method(self):
        """Test execute method in context."""
        async def success_func():
            return "success"

        async with RetryContext(phase=WorkflowPhase.OCR) as ctx:
            result = await ctx.execute(success_func)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting execution statistics."""
        async with RetryContext(phase=WorkflowPhase.PREPROCESSING) as ctx:
            stats = ctx.get_stats()

        assert stats["phase"] == "preprocessing"
        assert "total_time" in stats

    @pytest.mark.asyncio
    async def test_custom_strategy(self):
        """Test using custom strategy in context."""
        custom_strategy = RetryStrategy(
            default_config=RetryConfig(max_retries=10)
        )

        async with RetryContext(
            phase=WorkflowPhase.STORAGE,
            strategy=custom_strategy
        ) as ctx:
            assert ctx.strategy is custom_strategy


class TestGetRetryStrategy:
    """Tests for get_retry_strategy function."""

    def test_returns_strategy_instance(self):
        """Test that function returns RetryStrategy instance."""
        # Reset global for testing
        import app.core.retry_strategy as module
        module._global_strategy = None

        strategy = get_retry_strategy()

        assert isinstance(strategy, RetryStrategy)

    def test_returns_same_instance(self):
        """Test that function returns same instance."""
        import app.core.retry_strategy as module
        module._global_strategy = None

        strategy1 = get_retry_strategy()
        strategy2 = get_retry_strategy()

        assert strategy1 is strategy2


class TestCustomNonRetryable:
    """Tests for custom non-retryable exceptions."""

    def test_add_custom_non_retryable(self):
        """Test adding custom non-retryable exception."""

        class CustomError(Exception):
            pass

        strategy = RetryStrategy(non_retryable={CustomError})

        assert CustomError in strategy.non_retryable
        assert ValueError in strategy.non_retryable  # Original still there

    @pytest.mark.asyncio
    async def test_custom_exception_not_retried(self):
        """Test that custom exception is not retried."""

        class MyCustomError(Exception):
            pass

        strategy = RetryStrategy(non_retryable={MyCustomError})
        call_count = 0

        async def raise_custom():
            nonlocal call_count
            call_count += 1
            raise MyCustomError("Custom error")

        with pytest.raises(MyCustomError):
            await strategy.execute_with_retry(
                raise_custom,
                WorkflowPhase.OCR
            )

        assert call_count == 1  # No retries


class TestTimingBehavior:
    """Tests for timing and delay behavior."""

    @pytest.mark.asyncio
    async def test_delays_between_retries(self):
        """Test that delays occur between retries."""
        strategy = RetryStrategy()
        call_times = []

        async def fail_and_record():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise RuntimeError("Error")
            return "success"

        config = RetryConfig(
            max_retries=5,
            base_delay=0.1,
            jitter=0.0
        )

        await strategy.execute_with_retry(
            fail_and_record,
            WorkflowPhase.QA,
            config=config
        )

        # Check delays between calls
        assert len(call_times) == 3
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        # First delay should be ~0.1s
        assert 0.05 < delay1 < 0.2
        # Second delay should be ~0.2s (exponential)
        assert 0.15 < delay2 < 0.3
