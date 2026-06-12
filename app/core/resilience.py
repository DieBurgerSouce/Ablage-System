# -*- coding: utf-8 -*-
"""
Resilience Patterns: Circuit Breaker, Retry, Bulkhead.

Implementiert Enterprise Resilience Patterns für das Ablage-System:
- Circuit Breaker für Fehlerisolierung
- Retry mit Exponential Backoff
- Bulkhead für Ressourcen-Limitierung
- OCR-spezifische Resilience-Helper

Features:
- Thread-safe Circuit Breaker mit State-Machine
- Async/Sync Decorator Support
- Prometheus Metrics Integration
- Graceful Degradation mit Fallbacks

Feinpoliert und durchdacht - Enterprise Resilience.
"""

import asyncio
import functools
import random
import threading
import time
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple, TypeVar, Union

import structlog
from prometheus_client import Counter, Gauge

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Type variable für generische Decorators
T = TypeVar("T")
F = TypeVar("F", bound=Callable)


# =============================================================================
# Prometheus Metrics
# =============================================================================

circuit_breaker_state_changes = Counter(
    "circuit_breaker_state_changes_total",
    "Total circuit breaker state changes",
    ["name", "from_state", "to_state"]
)

circuit_breaker_calls = Counter(
    "circuit_breaker_calls_total",
    "Total circuit breaker calls",
    ["name", "state", "result"]
)

circuit_breaker_state_gauge = Gauge(
    "circuit_breaker_state",
    "Current circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["name"]
)

retry_attempts = Counter(
    "retry_attempts_total",
    "Total retry attempts",
    ["function", "attempt"]
)

bulkhead_rejections = Counter(
    "bulkhead_rejections_total",
    "Total bulkhead rejections",
    ["name"]
)


# =============================================================================
# Custom Exceptions
# =============================================================================

class CircuitBreakerOpenError(Exception):
    """Circuit Breaker ist geöffnet (Service nicht verfügbar)."""

    def __init__(self, service_name: str, retry_after_seconds: float):
        self.service_name = service_name
        self.retry_after_seconds = retry_after_seconds
        message = (
            f"Service '{service_name}' ist vorübergehend nicht verfügbar. "
            f"Bitte versuchen Sie es in {int(retry_after_seconds)} Sekunden erneut."
        )
        super().__init__(message)


class BulkheadFullError(Exception):
    """Bulkhead ist voll (Ressourcenlimit erreicht)."""

    def __init__(self, service_name: str, max_concurrent: int):
        self.service_name = service_name
        self.max_concurrent = max_concurrent
        message = (
            f"Service '{service_name}' hat das Limit von {max_concurrent} "
            f"gleichzeitigen Anfragen erreicht. Bitte versuchen Sie es später erneut."
        )
        super().__init__(message)


# =============================================================================
# Circuit Breaker State Machine
# =============================================================================

class CircuitBreakerState(str, Enum):
    """Circuit Breaker Zustaende."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failures detected, calls rejected
    HALF_OPEN = "half_open" # Testing if service recovered


class CircuitBreaker:
    """Thread-safe Circuit Breaker Implementation.

    State Machine:
    - CLOSED: Normal operation. Failures tracked.
    - OPEN: Service unavailable. All calls rejected.
    - HALF_OPEN: Testing recovery. Limited calls allowed.

    Transitions:
    - CLOSED -> OPEN: When failure_count >= failure_threshold
    - OPEN -> HALF_OPEN: After recovery_timeout_seconds
    - HALF_OPEN -> CLOSED: After half_open_max_calls successful calls
    - HALF_OPEN -> OPEN: On any failure in HALF_OPEN state

    Args:
        name: Circuit Breaker Name (für Metrics/Logging)
        failure_threshold: Anzahl Fehler bis OPEN (default: 5)
        recovery_timeout_seconds: Zeit bis HALF_OPEN Test (default: 60s)
        half_open_max_calls: Erfolgreiche Calls bis CLOSED (default: 3)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        # State tracking
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

        # Thread safety
        self._lock = threading.Lock()

        # Initialize metrics
        circuit_breaker_state_gauge.labels(name=self.name).set(0)

        logger.info(
            "circuit_breaker_initialized",
            name=self.name,
            failure_threshold=self.failure_threshold,
            recovery_timeout=self.recovery_timeout_seconds
        )

    @property
    def state(self) -> CircuitBreakerState:
        """Aktueller Circuit Breaker State."""
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        """Aktuelle Fehleranzahl."""
        with self._lock:
            return self._failure_count

    @property
    def success_count(self) -> int:
        """Aktuelle Erfolgsanzahl."""
        with self._lock:
            return self._success_count

    def can_execute(self) -> bool:
        """Prüft ob Call ausgeführt werden darf.

        Returns:
            True wenn Call erlaubt, False wenn Circuit OPEN
        """
        with self._lock:
            # Check if we need to transition from OPEN -> HALF_OPEN
            if self._state == CircuitBreakerState.OPEN:
                if self._last_failure_time is not None:
                    time_since_failure = time.time() - self._last_failure_time
                    if time_since_failure >= self.recovery_timeout_seconds:
                        self._transition_to(CircuitBreakerState.HALF_OPEN)
                        return True
                return False

            # CLOSED and HALF_OPEN allow execution
            return True

    def record_success(self) -> None:
        """Zeichne erfolgreichen Call auf."""
        with self._lock:
            self._success_count += 1

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_calls += 1
                logger.debug(
                    "circuit_breaker_half_open_success",
                    name=self.name,
                    half_open_calls=self._half_open_calls,
                    max_calls=self.half_open_max_calls
                )

                # Transition to CLOSED after enough successful calls.
                # WICHTIG: NICHT self.reset() aufrufen — das nimmt denselben
                # non-reentranten Lock erneut -> Selbst-Deadlock. Der Bug
                # fror jeden Recovery-Pfad (HALF_OPEN -> CLOSED) dauerhaft
                # ein (gefunden via haengender Unit-Suite, W3b 2026-06-12).
                if self._half_open_calls >= self.half_open_max_calls:
                    self._reset_locked()
                    self._transition_to(CircuitBreakerState.CLOSED)

            elif self._state == CircuitBreakerState.CLOSED:
                # Reset failure count on success in CLOSED state
                if self._failure_count > 0:
                    logger.debug(
                        "circuit_breaker_failure_count_reset",
                        name=self.name,
                        previous_failures=self._failure_count
                    )
                    self._failure_count = 0

            circuit_breaker_calls.labels(
                name=self.name,
                state=self._state.value,
                result="success"
            ).inc()

    def record_failure(self, exception: Optional[Exception] = None) -> None:
        """Zeichne fehlgeschlagenen Call auf.

        Args:
            exception: Optional Exception für Logging
        """
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            logger.warning(
                "circuit_breaker_failure",
                name=self.name,
                state=self._state.value,
                failure_count=self._failure_count,
                threshold=self.failure_threshold,
                exception_type=type(exception).__name__ if exception else None
            )

            circuit_breaker_calls.labels(
                name=self.name,
                state=self._state.value,
                result="failure"
            ).inc()

            # Transition logic
            if self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in HALF_OPEN -> back to OPEN
                self._transition_to(CircuitBreakerState.OPEN)

            elif self._state == CircuitBreakerState.CLOSED:
                # Check if we hit threshold
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitBreakerState.OPEN)

    def reset(self) -> None:
        """Reset Circuit Breaker counters."""
        with self._lock:
            self._reset_locked()

    def _reset_locked(self) -> None:
        """Reset-Logik fuer Aufrufer, die self._lock BEREITS halten."""
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        logger.info("circuit_breaker_reset", name=self.name)

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """Führe State Transition aus (internal, requires lock).

        Args:
            new_state: Ziel-State
        """
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state

        # Reset counters on state changes
        if new_state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state == CircuitBreakerState.CLOSED:
            self._failure_count = 0

        # Update metrics
        circuit_breaker_state_changes.labels(
            name=self.name,
            from_state=old_state.value,
            to_state=new_state.value
        ).inc()

        # State enum to int for gauge
        state_map = {
            CircuitBreakerState.CLOSED: 0,
            CircuitBreakerState.OPEN: 1,
            CircuitBreakerState.HALF_OPEN: 2
        }
        circuit_breaker_state_gauge.labels(name=self.name).set(
            state_map[new_state]
        )

        logger.info(
            "circuit_breaker_state_change",
            name=self.name,
            old_state=old_state.value,
            new_state=new_state.value,
            failure_count=self._failure_count
        )


# =============================================================================
# Circuit Breaker Registry (Singleton)
# =============================================================================

class CircuitBreakerRegistry:
    """Singleton Registry für Circuit Breakers.

    Verwaltet alle Circuit Breaker Instances zentral.
    """

    _instance: Optional["CircuitBreakerRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._breakers_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "CircuitBreakerRegistry":
        """Hole Singleton Instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = CircuitBreakerRegistry()
        return cls._instance

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3
    ) -> CircuitBreaker:
        """Hole existierenden oder erstelle neuen Circuit Breaker.

        Args:
            name: Circuit Breaker Name
            failure_threshold: Fehler-Threshold
            recovery_timeout_seconds: Recovery Timeout
            half_open_max_calls: Max Calls in HALF_OPEN

        Returns:
            CircuitBreaker Instance
        """
        with self._breakers_lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=failure_threshold,
                    recovery_timeout_seconds=recovery_timeout_seconds,
                    half_open_max_calls=half_open_max_calls
                )
            return self._breakers[name]

    def get_all_states(self) -> Dict[str, CircuitBreakerState]:
        """Hole States aller Circuit Breakers.

        Returns:
            Dict[name -> state]
        """
        with self._breakers_lock:
            return {
                name: breaker.state
                for name, breaker in self._breakers.items()
            }


# =============================================================================
# Circuit Breaker Decorator
# =============================================================================

def circuit_breaker(
    name: str,
    fallback: Optional[Callable] = None,
    on_open: Optional[Callable] = None,
    failure_threshold: int = 5,
    recovery_timeout_seconds: float = 60.0,
    half_open_max_calls: int = 3
) -> Callable[[F], F]:
    """Circuit Breaker Decorator für Funktionen.

    Works on both sync and async functions.

    Args:
        name: Circuit Breaker Name
        fallback: Optional Fallback-Funktion bei OPEN state
        on_open: Optional Callback wenn Circuit OPEN wird
        failure_threshold: Fehler bis OPEN
        recovery_timeout_seconds: Zeit bis HALF_OPEN
        half_open_max_calls: Erfolge bis CLOSED

    Returns:
        Decorated function

    Raises:
        CircuitBreakerOpenError: Wenn Circuit OPEN und kein Fallback

    Usage:
        @circuit_breaker("external_api", fallback=lambda: None)
        async def call_api():
            ...

        @circuit_breaker("ocr_backend", failure_threshold=3)
        def process_ocr(image):
            ...
    """
    registry = CircuitBreakerRegistry.get_instance()
    breaker = registry.get_or_create(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout_seconds=recovery_timeout_seconds,
        half_open_max_calls=half_open_max_calls
    )

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Check if circuit allows execution
            if not breaker.can_execute():
                logger.warning(
                    "circuit_breaker_open",
                    name=name,
                    function=func.__name__,
                    state=breaker.state.value
                )

                # Call on_open callback if provided
                if on_open is not None:
                    try:
                        if asyncio.iscoroutinefunction(on_open):
                            await on_open()
                        else:
                            on_open()
                    except Exception as e:
                        logger.warning(
                            "circuit_breaker_on_open_failed",
                            name=name,
                            exception=str(e)
                        )

                # Use fallback if provided
                if fallback is not None:
                    logger.debug("circuit_breaker_using_fallback", name=name)
                    if asyncio.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    return fallback(*args, **kwargs)

                # No fallback -> raise error
                raise CircuitBreakerOpenError(
                    service_name=name,
                    retry_after_seconds=breaker.recovery_timeout_seconds
                )

            # Execute function
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure(e)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Check if circuit allows execution
            if not breaker.can_execute():
                logger.warning(
                    "circuit_breaker_open",
                    name=name,
                    function=func.__name__,
                    state=breaker.state.value
                )

                # Call on_open callback if provided
                if on_open is not None:
                    try:
                        on_open()
                    except Exception as e:
                        logger.warning(
                            "circuit_breaker_on_open_failed",
                            name=name,
                            exception=str(e)
                        )

                # Use fallback if provided
                if fallback is not None:
                    logger.debug("circuit_breaker_using_fallback", name=name)
                    return fallback(*args, **kwargs)

                # No fallback -> raise error
                raise CircuitBreakerOpenError(
                    service_name=name,
                    retry_after_seconds=breaker.recovery_timeout_seconds
                )

            # Execute function
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure(e)
                raise

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]  # async_wrapper satisfies F
        return sync_wrapper  # type: ignore[return-value]  # sync_wrapper satisfies F

    return decorator


# =============================================================================
# Retry with Exponential Backoff
# =============================================================================

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[type, ...] = (Exception,)
) -> Callable[[F], F]:
    """Retry Decorator mit Exponential Backoff.

    Works on both sync and async functions.

    Args:
        max_retries: Maximale Anzahl Retries (default: 3)
        base_delay: Basis-Delay in Sekunden (default: 1.0)
        max_delay: Maximaler Delay in Sekunden (default: 60.0)
        exponential_base: Basis für Exponential Backoff (default: 2.0)
        jitter: Random Jitter hinzufuegen (default: True)
        retryable_exceptions: Tuple von Exception-Typen die retried werden

    Returns:
        Decorated function

    Backoff Formula:
        delay = min(base_delay * (exponential_base ** attempt), max_delay)
        if jitter: delay *= random.uniform(0.5, 1.5)

    Usage:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        async def call_api():
            ...

        @retry_with_backoff(max_retries=5, retryable_exceptions=(IOError,))
        def read_file():
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    # Max retries reached
                    if attempt >= max_retries:
                        logger.error(
                            "retry_max_attempts_exceeded",
                            function=func.__name__,
                            max_retries=max_retries,
                            exception_type=type(e).__name__,
                            exception_msg=str(e)
                        )
                        raise

                    # Calculate backoff delay
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    # Add jitter
                    if jitter:
                        delay *= random.uniform(0.5, 1.5)

                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=round(delay, 2),
                        exception_type=type(e).__name__
                    )

                    retry_attempts.labels(
                        function=func.__name__,
                        attempt=str(attempt + 1)
                    ).inc()

                    await asyncio.sleep(delay)

            # Should not reach here
            if last_exception:
                raise last_exception
            return None

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    # Max retries reached
                    if attempt >= max_retries:
                        logger.error(
                            "retry_max_attempts_exceeded",
                            function=func.__name__,
                            max_retries=max_retries,
                            exception_type=type(e).__name__,
                            exception_msg=str(e)
                        )
                        raise

                    # Calculate backoff delay
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    # Add jitter
                    if jitter:
                        delay *= random.uniform(0.5, 1.5)

                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=round(delay, 2),
                        exception_type=type(e).__name__
                    )

                    retry_attempts.labels(
                        function=func.__name__,
                        attempt=str(attempt + 1)
                    ).inc()

                    time.sleep(delay)

            # Should not reach here
            if last_exception:
                raise last_exception
            return None

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]  # async_wrapper satisfies F
        return sync_wrapper  # type: ignore[return-value]  # sync_wrapper satisfies F

    return decorator


# =============================================================================
# Bulkhead Pattern
# =============================================================================

class Bulkhead:
    """Bulkhead Pattern für Ressourcen-Limitierung.

    Limitiert die Anzahl gleichzeitiger Calls mit asyncio.Semaphore.

    Args:
        name: Bulkhead Name
        max_concurrent: Maximale gleichzeitige Calls
        max_queue: Maximale Warteschlange (0 = keine Queue)
    """

    def __init__(self, name: str, max_concurrent: int, max_queue: int = 0):
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue_count = 0
        self._lock = asyncio.Lock()

        logger.info(
            "bulkhead_initialized",
            name=self.name,
            max_concurrent=self.max_concurrent,
            max_queue=self.max_queue
        )

    async def __aenter__(self):
        """Async Context Manager Entry."""
        async with self._lock:
            # max_queue == 0 bedeutet laut Vertrag "keine Warteschlange":
            # Ist das Limit erreicht, wird SOFORT abgelehnt. Vorher wartete
            # der Aufrufer hier unbegrenzt am Semaphor (W3b 2026-06-12) —
            # das Bulkhead hat sein Limit also nie durchgesetzt.
            if self.max_queue == 0:
                if self._semaphore.locked():
                    bulkhead_rejections.labels(name=self.name).inc()
                    logger.warning(
                        "bulkhead_full_rejected",
                        name=self.name,
                        max_concurrent=self.max_concurrent
                    )
                    raise BulkheadFullError(
                        service_name=self.name,
                        max_concurrent=self.max_concurrent
                    )
                # Permit ist frei -> Acquire kehrt ohne Warten zurueck;
                # innerhalb des Locks gehalten, damit kein paralleler
                # Aufrufer zwischen Pruefung und Acquire grätscht.
                await self._semaphore.acquire()
                return self

            # Mit Warteschlange: Queue-Limit pruefen
            if self._queue_count >= self.max_queue:
                bulkhead_rejections.labels(name=self.name).inc()
                logger.warning(
                    "bulkhead_queue_full",
                    name=self.name,
                    queue_count=self._queue_count,
                    max_queue=self.max_queue
                )
                raise BulkheadFullError(
                    service_name=self.name,
                    max_concurrent=self.max_concurrent
                )
            self._queue_count += 1

        # Acquire semaphore (ausserhalb des Locks: Warten ist hier erlaubt)
        await self._semaphore.acquire()

        async with self._lock:
            self._queue_count -= 1

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async Context Manager Exit."""
        self._semaphore.release()


# =============================================================================
# OCR-Specific Helpers
# =============================================================================

# OCR Circuit Breaker Configuration
OCR_CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": 3,
    "recovery_timeout_seconds": 120.0,
    "half_open_max_calls": 2
}


def get_ocr_circuit_breaker(backend_name: str) -> CircuitBreaker:
    """Hole oder erstelle Circuit Breaker für OCR Backend.

    Pre-configured für OCR:
    - failure_threshold: 3 (schnelleres OPEN bei OCR-Fehlern)
    - recovery_timeout: 120s (mehr Zeit für GPU-Recovery)
    - half_open_max_calls: 2

    Args:
        backend_name: OCR Backend Name (z.B. "deepseek", "got-ocr", "surya")

    Returns:
        CircuitBreaker Instance

    Usage:
        breaker = get_ocr_circuit_breaker("deepseek")
        if breaker.can_execute():
            result = ocr_backend.process(image)
            breaker.record_success()
    """
    registry = CircuitBreakerRegistry.get_instance()
    return registry.get_or_create(
        name=f"ocr:{backend_name}",
        **OCR_CIRCUIT_BREAKER_CONFIG
    )
