"""
Circuit Breaker Pattern für Ablage-System OCR Backends.

Implementiert das Circuit Breaker Pattern zur Vermeidung von
Kaskadenfehlern:
- CLOSED: Normal operation, Fehler werden gezählt
- OPEN: Backend deaktiviert nach zu vielen Fehlern
- HALF_OPEN: Probe-Requests zum Testen der Wiederherstellung

Feinpoliert und durchdacht - Enterprise-grade Resilience.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar
from functools import wraps
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Zustände des Circuit Breakers."""
    CLOSED = "closed"      # Normal, Requests werden durchgelassen
    OPEN = "open"          # Offen, Requests werden blockiert
    HALF_OPEN = "half_open"  # Test-Phase nach Timeout


@dataclass
class CircuitStats:
    """Statistiken für einen Circuit Breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changed_at: float = field(default_factory=time.time)
    times_opened: int = 0
    times_half_opened: int = 0

    @property
    def failure_rate(self) -> float:
        """Berechne aktuelle Fehlerrate."""
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls

    @property
    def success_rate(self) -> float:
        """Berechne aktuelle Erfolgsrate."""
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "failure_rate": round(self.failure_rate, 4),
            "success_rate": round(self.success_rate, 4),
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "times_opened": self.times_opened,
            "times_half_opened": self.times_half_opened,
        }


class CircuitBreakerError(Exception):
    """Exception wenn Circuit offen ist."""

    def __init__(self, backend: str, state: CircuitState, retry_after: float):
        self.backend = backend
        self.state = state
        self.retry_after = retry_after
        super().__init__(
            f"Circuit für {backend} ist {state.value}. "
            f"Erneuter Versuch möglich in {retry_after:.1f}s"
        )


class CircuitBreaker:
    """
    Circuit Breaker für ein einzelnes OCR Backend.

    Konfigurierbare Parameter:
    - failure_threshold: Anzahl Fehler bis OPEN
    - recovery_timeout: Zeit in OPEN bevor HALF_OPEN
    - success_threshold: Erfolge in HALF_OPEN für CLOSED
    - failure_window: Zeitfenster für failure_threshold
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
        failure_window: float = 60.0,
        half_open_max_calls: int = 3
    ):
        """
        Initialisiere Circuit Breaker.

        Args:
            name: Name des Backends
            failure_threshold: Fehler bis OPEN
            recovery_timeout: Sekunden bis HALF_OPEN
            success_threshold: Erfolge für Wiederherstellung
            failure_window: Zeitfenster für Fehler
            half_open_max_calls: Max Calls in HALF_OPEN
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.failure_window = failure_window
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._failure_times: List[float] = []
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

        logger.info(
            "circuit_breaker_created",
            backend=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )

    @property
    def state(self) -> CircuitState:
        """Hole aktuellen Zustand."""
        return self._state

    @property
    def stats(self) -> CircuitStats:
        """Hole Statistiken."""
        return self._stats

    async def can_execute(self) -> bool:
        """
        Prüfe ob ein Request durchgeführt werden kann.

        Returns:
            True wenn Request erlaubt
        """
        async with self._lock:
            return await self._check_state()

    async def _check_state(self) -> bool:
        """Interne State-Prüfung (mit Lock gehalten)."""
        now = time.time()

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Prüfe ob Recovery-Timeout abgelaufen
            time_in_open = now - self._stats.state_changed_at

            if time_in_open >= self.recovery_timeout:
                # Wechsle zu HALF_OPEN
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            else:
                return False

        if self._state == CircuitState.HALF_OPEN:
            # Begrenzte Anzahl Calls in HALF_OPEN
            if self._half_open_calls < self.half_open_max_calls:
                return True
            else:
                return False

        return False

    def _transition_to(self, new_state: CircuitState) -> None:
        """Führe Zustandswechsel durch."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changed_at = time.time()

        if new_state == CircuitState.OPEN:
            self._stats.times_opened += 1
        elif new_state == CircuitState.HALF_OPEN:
            self._stats.times_half_opened += 1
            self._half_open_calls = 0

        logger.warning(
            "circuit_breaker_state_change",
            backend=self.name,
            old_state=old_state.value,
            new_state=new_state.value,
            consecutive_failures=self._stats.consecutive_failures
        )

    async def record_success(self) -> None:
        """Registriere erfolgreichen Call."""
        async with self._lock:
            self._stats.total_calls += 1
            self._stats.successful_calls += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

                # Prüfe ob genug Erfolge für CLOSED
                if self._stats.consecutive_successes >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    self._failure_times.clear()

            logger.debug(
                "circuit_breaker_success",
                backend=self.name,
                state=self._state.value,
                consecutive_successes=self._stats.consecutive_successes
            )

    async def record_failure(self, error: Optional[Exception] = None) -> None:
        """Registriere fehlgeschlagenen Call."""
        async with self._lock:
            now = time.time()

            self._stats.total_calls += 1
            self._stats.failed_calls += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = now
            self._failure_times.append(now)

            # Entferne alte Fehler außerhalb des Zeitfensters
            self._failure_times = [
                t for t in self._failure_times
                if now - t <= self.failure_window
            ]

            logger.warning(
                "circuit_breaker_failure",
                backend=self.name,
                state=self._state.value,
                consecutive_failures=self._stats.consecutive_failures,
                failures_in_window=len(self._failure_times),
                error=str(error) if error else None
            )

            if self._state == CircuitState.HALF_OPEN:
                # Ein Fehler in HALF_OPEN öffnet sofort wieder
                self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                # Prüfe ob Schwelle erreicht
                if len(self._failure_times) >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def get_retry_after(self) -> float:
        """Berechne Zeit bis nächster Versuch möglich."""
        if self._state == CircuitState.CLOSED:
            return 0.0

        time_since_state_change = time.time() - self._stats.state_changed_at
        remaining = self.recovery_timeout - time_since_state_change

        return max(0.0, remaining)

    def get_status(self) -> Dict[str, Any]:
        """Hole vollständigen Status."""
        return {
            "name": self.name,
            "state": self._state.value,
            "stats": self._stats.to_dict(),
            "retry_after": self.get_retry_after(),
            "config": {
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "success_threshold": self.success_threshold,
                "failure_window": self.failure_window,
            }
        }

    def reset(self) -> None:
        """Reset den Circuit Breaker."""
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._failure_times.clear()
        self._half_open_calls = 0

        logger.info(
            "circuit_breaker_reset",
            backend=self.name
        )


class CircuitBreakerRegistry:
    """
    Registry für alle Circuit Breakers im System.

    Ermöglicht zentrales Management aller Backend Circuit Breakers.
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._default_config = {
            "failure_threshold": 5,
            "recovery_timeout": 30.0,
            "success_threshold": 2,
            "failure_window": 60.0,
            "half_open_max_calls": 3,
        }

    def get_or_create(
        self,
        name: str,
        **kwargs
    ) -> CircuitBreaker:
        """
        Hole oder erstelle Circuit Breaker für Backend.

        Args:
            name: Backend-Name
            **kwargs: Optionale Konfiguration

        Returns:
            CircuitBreaker Instance
        """
        if name not in self._breakers:
            config = {**self._default_config, **kwargs}
            self._breakers[name] = CircuitBreaker(name=name, **config)

        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Hole Circuit Breaker wenn vorhanden."""
        return self._breakers.get(name)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Hole Status aller Circuit Breakers."""
        return {name: cb.get_status() for name, cb in self._breakers.items()}

    def get_open_circuits(self) -> List[str]:
        """Hole Liste der offenen Circuits."""
        return [
            name for name, cb in self._breakers.items()
            if cb.state == CircuitState.OPEN
        ]

    def reset_all(self) -> None:
        """Reset alle Circuit Breakers."""
        for cb in self._breakers.values():
            cb.reset()

        logger.info(
            "circuit_breakers_reset_all",
            count=len(self._breakers)
        )


# Singleton Registry
_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Hole Singleton-Instance der Registry."""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry


def circuit_breaker_protected(backend_name: str):
    """
    Decorator für Circuit Breaker geschützte Funktionen.

    Usage:
        @circuit_breaker_protected("deepseek")
        async def process_with_deepseek(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            registry = get_circuit_breaker_registry()
            cb = registry.get_or_create(backend_name)

            # Prüfe ob Aufruf erlaubt
            can_execute = await cb.can_execute()
            if not can_execute:
                raise CircuitBreakerError(
                    backend=backend_name,
                    state=cb.state,
                    retry_after=cb.get_retry_after()
                )

            # Führe aus und tracke Ergebnis
            try:
                result = await func(*args, **kwargs)
                await cb.record_success()
                return result

            except Exception as e:
                await cb.record_failure(e)
                raise

        return wrapper
    return decorator
