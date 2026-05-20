"""
Retry Strategy with Exponential Backoff.

Provides configurable retry logic for different workflow phases.
Supports exponential backoff with jitter to prevent thundering herd.
"""

import asyncio
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Set, Type, TypeVar, Union

import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class WorkflowPhase(str, Enum):
    """Workflow processing phases."""

    CLASSIFICATION = "classification"
    PREPROCESSING = "preprocessing"
    OCR = "ocr"
    POSTPROCESSING = "postprocessing"
    QA = "qa"
    STORAGE = "storage"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0  # Maximum delay cap
    exponential_base: float = 2.0  # Multiplier for exponential backoff
    jitter: float = 0.1  # Random jitter factor (0.0 - 1.0)


# Phase-specific retry configurations
PHASE_CONFIGS: Dict[WorkflowPhase, RetryConfig] = {
    WorkflowPhase.CLASSIFICATION: RetryConfig(
        max_retries=2,
        base_delay=0.5,
        max_delay=5.0,
    ),
    WorkflowPhase.PREPROCESSING: RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0,
    ),
    WorkflowPhase.OCR: RetryConfig(
        max_retries=2,
        base_delay=2.0,
        max_delay=60.0,
    ),
    WorkflowPhase.POSTPROCESSING: RetryConfig(
        max_retries=3,
        base_delay=0.5,
        max_delay=15.0,
    ),
    WorkflowPhase.QA: RetryConfig(
        max_retries=2,
        base_delay=0.5,
        max_delay=10.0,
    ),
    WorkflowPhase.STORAGE: RetryConfig(
        max_retries=5,
        base_delay=1.0,
        max_delay=30.0,
    ),
}

# Exceptions that should NOT be retried (permanent failures)
NON_RETRYABLE_EXCEPTIONS: Set[Type[Exception]] = {
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    PermissionError,
}


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(
        self,
        phase: str,
        max_retries: int,
        last_exception: Exception,
    ):
        self.phase = phase
        self.max_retries = max_retries
        self.last_exception = last_exception
        super().__init__(
            f"Alle {max_retries} Wiederholungsversuche für Phase '{phase}' fehlgeschlagen. "
            f"Letzter Fehler: {last_exception}"
        )


class RetryStrategy:
    """
    Retry strategy with exponential backoff and jitter.

    Usage:
        strategy = RetryStrategy()
        result = await strategy.execute_with_retry(
            my_async_func,
            phase=WorkflowPhase.OCR,
            arg1, arg2,
            kwarg1=value
        )
    """

    def __init__(
        self,
        default_config: Optional[RetryConfig] = None,
        non_retryable: Optional[Set[Type[Exception]]] = None,
    ):
        """
        Initialize retry strategy.

        Args:
            default_config: Default configuration for unlisted phases
            non_retryable: Additional exception types that should not be retried
        """
        self.default_config = default_config or RetryConfig()
        self.non_retryable = NON_RETRYABLE_EXCEPTIONS.copy()
        if non_retryable:
            self.non_retryable.update(non_retryable)

    def get_config(self, phase: WorkflowPhase) -> RetryConfig:
        """Get configuration for workflow phase."""
        return PHASE_CONFIGS.get(phase, self.default_config)

    def _calculate_delay(self, attempt: int, config: RetryConfig) -> float:
        """
        Calculate delay for retry attempt with exponential backoff and jitter.

        Args:
            attempt: Current attempt number (0-indexed)
            config: Retry configuration

        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = config.base_delay * (config.exponential_base ** attempt)

        # Apply max cap
        delay = min(delay, config.max_delay)

        # Add jitter (random variation to prevent thundering herd)
        if config.jitter > 0:
            jitter_range = delay * config.jitter
            delay = delay + random.uniform(-jitter_range, jitter_range)

        return max(0.0, delay)

    def _should_retry(
        self,
        exception: Exception,
        attempt: int,
        config: RetryConfig,
    ) -> bool:
        """
        Determine if operation should be retried.

        Args:
            exception: Exception that occurred
            attempt: Current attempt number
            config: Retry configuration

        Returns:
            True if should retry
        """
        # Check if exception is non-retryable
        for exc_type in self.non_retryable:
            if isinstance(exception, exc_type):
                logger.debug(
                    "retry_skipped_non_retryable",
                    exception_type=type(exception).__name__,
                )
                return False

        # Check if max retries exceeded
        if attempt >= config.max_retries:
            return False

        return True

    async def execute_with_retry(
        self,
        func: Callable[..., T],
        phase: WorkflowPhase,
        *args: object,
        config: Optional[RetryConfig] = None,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs: object,
    ) -> T:
        """
        Execute function with retry logic.

        Args:
            func: Async function to execute
            phase: Workflow phase for configuration
            *args: Function arguments
            config: Optional custom configuration
            on_retry: Optional callback on retry (attempt, exception)
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            RetryExhaustedError: If all retries exhausted
            Exception: Non-retryable exception
        """
        retry_config = config or self.get_config(phase)
        last_exception: Optional[Exception] = None
        start_time = time.time()

        for attempt in range(retry_config.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(
                        "retry_attempt",
                        phase=phase.value,
                        attempt=attempt,
                        max_retries=retry_config.max_retries,
                    )

                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Success
                if attempt > 0:
                    total_time = time.time() - start_time
                    logger.info(
                        "retry_succeeded",
                        phase=phase.value,
                        attempt=attempt,
                        total_time_seconds=round(total_time, 2),
                    )

                return result

            except Exception as e:
                last_exception = e

                # Check if should retry
                if not self._should_retry(e, attempt, retry_config):
                    if isinstance(e, tuple(self.non_retryable)):
                        logger.warning(
                            "non_retryable_exception",
                            phase=phase.value,
                            exception_type=type(e).__name__,
                            **safe_error_log(e),
                        )
                        raise
                    # Max retries reached
                    break

                # Calculate delay
                delay = self._calculate_delay(attempt, retry_config)

                logger.warning(
                    "retry_scheduled",
                    phase=phase.value,
                    attempt=attempt + 1,
                    max_retries=retry_config.max_retries,
                    delay_seconds=round(delay, 2),
                    error_type=type(e).__name__,
                    **safe_error_log(e),
                )

                # Call optional retry callback
                if on_retry:
                    on_retry(attempt, e)

                # Wait before retry
                await asyncio.sleep(delay)

        # All retries exhausted
        total_time = time.time() - start_time
        logger.error(
            "retry_exhausted",
            phase=phase.value,
            max_retries=retry_config.max_retries,
            total_time_seconds=round(total_time, 2),
            last_error_type=type(last_exception).__name__ if last_exception else None,
            last_error=str(last_exception) if last_exception else None,
        )

        raise RetryExhaustedError(
            phase=phase.value,
            max_retries=retry_config.max_retries,
            last_exception=last_exception,
        )


class RetryContext:
    """
    Context manager for retry tracking within a phase.

    Usage:
        async with RetryContext(phase=WorkflowPhase.OCR) as ctx:
            result = await ctx.execute(my_func, *args)
    """

    def __init__(
        self,
        phase: WorkflowPhase,
        strategy: Optional[RetryStrategy] = None,
    ):
        """Initialize retry context."""
        self.phase = phase
        self.strategy = strategy or RetryStrategy()
        self.attempt = 0
        self.start_time: Optional[float] = None
        self.exceptions: list[Exception] = []

    async def __aenter__(self) -> "RetryContext":
        """Enter context."""
        self.start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        if exc_val:
            self.exceptions.append(exc_val)

    async def execute(
        self,
        func: Callable[..., T],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Execute function with retry."""
        return await self.strategy.execute_with_retry(
            func, self.phase, *args, **kwargs
        )

    def get_stats(self) -> Dict[str, Union[str, int, float]]:
        """Get execution statistics."""
        return {
            "phase": self.phase.value,
            "attempts": self.attempt,
            "exceptions_count": len(self.exceptions),
            "total_time": (
                time.time() - self.start_time
                if self.start_time
                else 0
            ),
        }


# Global retry strategy instance
_global_strategy: Optional[RetryStrategy] = None


def get_retry_strategy() -> RetryStrategy:
    """Get global retry strategy instance."""
    global _global_strategy
    if _global_strategy is None:
        _global_strategy = RetryStrategy()
    return _global_strategy
