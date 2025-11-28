"""
Circuit Breaker Pattern Implementation.

Provides fault tolerance for external services (Redis, Database, OCR Backends).
Prevents cascading failures by failing fast when services are unavailable.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service unavailable, requests fail immediately
- HALF_OPEN: Testing if service recovered
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    reset_timeout: float = 30.0  # Seconds before trying half-open
    half_open_max_calls: int = 3  # Max concurrent calls in half-open


@dataclass
class CircuitStats:
    """Statistics for circuit breaker monitoring."""

    failures: int = 0
    successes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0


# Service-specific configurations
SERVICE_CONFIGS: Dict[str, CircuitConfig] = {
    "redis": CircuitConfig(
        failure_threshold=5,
        success_threshold=2,
        reset_timeout=30.0,
    ),
    "database": CircuitConfig(
        failure_threshold=3,
        success_threshold=2,
        reset_timeout=60.0,
    ),
    "ocr_deepseek": CircuitConfig(
        failure_threshold=2,
        success_threshold=1,
        reset_timeout=120.0,
    ),
    "ocr_got": CircuitConfig(
        failure_threshold=2,
        success_threshold=1,
        reset_timeout=120.0,
    ),
    "ocr_surya": CircuitConfig(
        failure_threshold=5,
        success_threshold=2,
        reset_timeout=60.0,
    ),
    "ocr_surya_gpu": CircuitConfig(
        failure_threshold=3,
        success_threshold=1,
        reset_timeout=90.0,
    ),
    "minio": CircuitConfig(
        failure_threshold=3,
        success_threshold=2,
        reset_timeout=45.0,
    ),
}


class CircuitOpenError(Exception):
    """Raised when circuit is open and request is rejected."""

    def __init__(self, service_name: str, time_until_retry: float):
        self.service_name = service_name
        self.time_until_retry = time_until_retry
        super().__init__(
            f"Circuit breaker open for {service_name}. "
            f"Retry in {time_until_retry:.1f}s"
        )


class CircuitBreaker:
    """
    Circuit breaker for a single service.

    Usage:
        cb = CircuitBreaker("redis")
        result = await cb.call(redis_operation, *args, **kwargs)
    """

    def __init__(
        self,
        service_name: str,
        config: Optional[CircuitConfig] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            service_name: Service identifier
            config: Optional custom configuration
        """
        self.service_name = service_name
        self.config = config or SERVICE_CONFIGS.get(
            service_name, CircuitConfig()
        )
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._opened_at: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_available(self) -> bool:
        """Check if circuit allows requests."""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.config.half_open_max_calls
        if self._state == CircuitState.OPEN:
            # Check if reset timeout has passed
            if self._opened_at and time.time() - self._opened_at >= self.config.reset_timeout:
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "service": self.service_name,
            "state": self._state.value,
            "failures": self._stats.failures,
            "successes": self._stats.successes,
            "consecutive_failures": self._stats.consecutive_failures,
            "total_calls": self._stats.total_calls,
            "rejected_calls": self._stats.rejected_calls,
            "state_changes": self._stats.state_changes,
            "last_failure": (
                datetime.fromtimestamp(self._stats.last_failure_time).isoformat()
                if self._stats.last_failure_time
                else None
            ),
            "last_success": (
                datetime.fromtimestamp(self._stats.last_success_time).isoformat()
                if self._stats.last_success_time
                else None
            ),
        }

    async def call(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitOpenError: If circuit is open
            Exception: Original exception if function fails
        """
        async with self._lock:
            await self._check_state_transition()

            if not self.is_available:
                self._stats.rejected_calls += 1
                time_until_retry = (
                    self.config.reset_timeout - (time.time() - self._opened_at)
                    if self._opened_at
                    else self.config.reset_timeout
                )
                logger.warning(
                    "circuit_breaker_rejected",
                    service=self.service_name,
                    state=self._state.value,
                    time_until_retry=round(time_until_retry, 1),
                )
                raise CircuitOpenError(self.service_name, time_until_retry)

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        # Execute outside lock
        self._stats.total_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure(e)
            raise

    async def _check_state_transition(self) -> None:
        """Check and perform state transitions based on timeout."""
        if self._state == CircuitState.OPEN:
            if self._opened_at and time.time() - self._opened_at >= self.config.reset_timeout:
                await self._transition_to(CircuitState.HALF_OPEN)

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self._stats.successes += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls -= 1
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)

            logger.debug(
                "circuit_breaker_success",
                service=self.service_name,
                state=self._state.value,
                consecutive_successes=self._stats.consecutive_successes,
            )

    async def _on_failure(self, exception: Exception) -> None:
        """Handle failed call."""
        async with self._lock:
            self._stats.failures += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls -= 1
                # Any failure in half-open reopens the circuit
                await self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)

            logger.warning(
                "circuit_breaker_failure",
                service=self.service_name,
                state=self._state.value,
                consecutive_failures=self._stats.consecutive_failures,
                error_type=type(exception).__name__,
                error=str(exception),
            )

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to new state."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changes += 1

        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            self._half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._stats.consecutive_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._opened_at = None
            self._half_open_calls = 0
            self._stats.consecutive_failures = 0

        logger.info(
            "circuit_breaker_state_changed",
            service=self.service_name,
            old_state=old_state.value,
            new_state=new_state.value,
        )

    def reset(self) -> None:
        """Manually reset circuit to closed state."""
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._opened_at = None
        self._half_open_calls = 0
        logger.info("circuit_breaker_reset", service=self.service_name)


class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers.

    Singleton pattern for global access.
    """

    _instance: Optional["CircuitBreakerManager"] = None

    def __init__(self):
        """Initialize circuit breaker manager."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "CircuitBreakerManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_breaker(
        self,
        service_name: str,
        config: Optional[CircuitConfig] = None,
    ) -> CircuitBreaker:
        """
        Get or create circuit breaker for service.

        Args:
            service_name: Service identifier
            config: Optional custom configuration

        Returns:
            CircuitBreaker instance
        """
        async with self._lock:
            if service_name not in self._breakers:
                self._breakers[service_name] = CircuitBreaker(
                    service_name, config
                )
            return self._breakers[service_name]

    async def call(
        self,
        service_name: str,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute function through circuit breaker.

        Convenience method that gets breaker and calls function.

        Args:
            service_name: Service identifier
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result
        """
        breaker = await self.get_breaker(service_name)
        return await breaker.call(func, *args, **kwargs)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }

    def get_unhealthy_services(self) -> list[str]:
        """Get list of services with open circuits."""
        return [
            name
            for name, breaker in self._breakers.items()
            if breaker.state == CircuitState.OPEN
        ]

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()
        logger.info("all_circuit_breakers_reset")


# Convenience function for getting the global manager
def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get global circuit breaker manager instance."""
    return CircuitBreakerManager.get_instance()
