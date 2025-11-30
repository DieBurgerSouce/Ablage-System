# -*- coding: utf-8 -*-
"""
Unit Tests fuer OCR Backend Circuit Breaker Service.

Testet das Circuit Breaker Pattern fuer OCR Backends:
- Zustandsuebergaenge (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Fehler-Tracking innerhalb Zeitfenster
- Recovery nach Timeout
- Registry fuer mehrere Backends
- Decorator-Pattern

Feinpoliert und durchdacht - Enterprise Circuit Breaker Testing.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, patch

from app.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitBreakerError,
    CircuitState,
    CircuitStats,
    get_circuit_breaker_registry,
    circuit_breaker_protected,
)


# =============================================================================
# CircuitState Tests
# =============================================================================


class TestCircuitState:
    """Tests fuer CircuitState Enum."""

    def test_all_states_exist(self):
        """Teste dass alle Zustaende definiert sind."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_state_count(self):
        """Teste Anzahl der Zustaende."""
        assert len(CircuitState) == 3


# =============================================================================
# CircuitStats Tests
# =============================================================================


class TestCircuitStats:
    """Tests fuer CircuitStats Dataclass."""

    def test_default_values(self):
        """Teste Standard-Werte."""
        stats = CircuitStats()

        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0
        assert stats.last_failure_time is None
        assert stats.last_success_time is None
        assert stats.times_opened == 0
        assert stats.times_half_opened == 0

    def test_failure_rate_zero_calls(self):
        """Teste Fehlerrate bei null Aufrufen."""
        stats = CircuitStats()
        assert stats.failure_rate == 0.0

    def test_failure_rate_calculation(self):
        """Teste Fehlerrate-Berechnung."""
        stats = CircuitStats(total_calls=100, failed_calls=25)
        assert stats.failure_rate == 0.25

    def test_success_rate_zero_calls(self):
        """Teste Erfolgsrate bei null Aufrufen."""
        stats = CircuitStats()
        assert stats.success_rate == 1.0

    def test_success_rate_calculation(self):
        """Teste Erfolgsrate-Berechnung."""
        stats = CircuitStats(total_calls=100, successful_calls=75)
        assert stats.success_rate == 0.75

    def test_to_dict(self):
        """Teste Konvertierung zu Dictionary."""
        stats = CircuitStats(
            total_calls=100,
            successful_calls=80,
            failed_calls=20,
            consecutive_failures=2,
            times_opened=1
        )

        d = stats.to_dict()

        assert d["total_calls"] == 100
        assert d["successful_calls"] == 80
        assert d["failed_calls"] == 20
        assert d["failure_rate"] == 0.2
        assert d["success_rate"] == 0.8
        assert d["times_opened"] == 1


# =============================================================================
# CircuitBreakerError Tests
# =============================================================================


class TestCircuitBreakerError:
    """Tests fuer CircuitBreakerError Exception."""

    def test_error_attributes(self):
        """Teste Error-Attribute."""
        error = CircuitBreakerError(
            backend="deepseek",
            state=CircuitState.OPEN,
            retry_after=30.0
        )

        assert error.backend == "deepseek"
        assert error.state == CircuitState.OPEN
        assert error.retry_after == 30.0

    def test_error_message(self):
        """Teste Error-Nachricht."""
        error = CircuitBreakerError(
            backend="got_ocr",
            state=CircuitState.OPEN,
            retry_after=15.5
        )

        message = str(error)
        assert "got_ocr" in message
        assert "open" in message
        assert "15.5" in message


# =============================================================================
# CircuitBreaker Tests
# =============================================================================


class TestCircuitBreaker:
    """Tests fuer CircuitBreaker Klasse."""

    @pytest.fixture
    def breaker(self):
        """Erstelle Circuit Breaker mit kurzen Timeouts fuer Tests."""
        return CircuitBreaker(
            name="test_backend",
            failure_threshold=3,
            recovery_timeout=0.5,  # 500ms fuer schnelle Tests
            success_threshold=2,
            failure_window=5.0,
            half_open_max_calls=2
        )

    def test_initial_state_is_closed(self, breaker):
        """Teste initialer Zustand ist CLOSED."""
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_can_execute_when_closed(self, breaker):
        """Teste Ausfuehrung erlaubt wenn CLOSED."""
        can_execute = await breaker.can_execute()
        assert can_execute is True

    @pytest.mark.asyncio
    async def test_record_success(self, breaker):
        """Teste Erfolg aufzeichnen."""
        await breaker.record_success()

        assert breaker.stats.total_calls == 1
        assert breaker.stats.successful_calls == 1
        assert breaker.stats.consecutive_successes == 1
        assert breaker.stats.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_record_failure(self, breaker):
        """Teste Fehler aufzeichnen."""
        await breaker.record_failure(RuntimeError("Test"))

        assert breaker.stats.total_calls == 1
        assert breaker.stats.failed_calls == 1
        assert breaker.stats.consecutive_failures == 1
        assert breaker.stats.consecutive_successes == 0

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self, breaker):
        """Teste Oeffnung nach Fehler-Schwelle."""
        # Simuliere 3 aufeinanderfolgende Fehler
        for _ in range(3):
            await breaker.record_failure(RuntimeError("Test"))

        assert breaker.state == CircuitState.OPEN
        assert breaker.stats.times_opened == 1

    @pytest.mark.asyncio
    async def test_blocks_execution_when_open(self, breaker):
        """Teste Blockierung wenn OPEN."""
        # Oeffne Circuit
        for _ in range(3):
            await breaker.record_failure(RuntimeError("Test"))

        can_execute = await breaker.can_execute()
        assert can_execute is False

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, breaker):
        """Teste Uebergang zu HALF_OPEN nach Timeout."""
        # Oeffne Circuit
        for _ in range(3):
            await breaker.record_failure(RuntimeError("Test"))

        assert breaker.state == CircuitState.OPEN

        # Warte auf Recovery Timeout
        await asyncio.sleep(0.6)

        # Sollte jetzt HALF_OPEN erlauben
        can_execute = await breaker.can_execute()
        assert can_execute is True
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_after_success_threshold_in_half_open(self, breaker):
        """Teste Schliessung nach Erfolgs-Schwelle in HALF_OPEN."""
        # Oeffne und warte auf HALF_OPEN
        for _ in range(3):
            await breaker.record_failure(RuntimeError("Test"))
        await asyncio.sleep(0.6)
        await breaker.can_execute()  # Transition zu HALF_OPEN

        # Erfolge in HALF_OPEN
        await breaker.record_success()
        await breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reopens_on_failure_in_half_open(self, breaker):
        """Teste Wiederoeffnung bei Fehler in HALF_OPEN."""
        # Oeffne und warte auf HALF_OPEN
        for _ in range(3):
            await breaker.record_failure(RuntimeError("Test"))
        await asyncio.sleep(0.6)
        await breaker.can_execute()

        # Ein Fehler sollte wieder oeffnen
        await breaker.record_failure(RuntimeError("Test"))

        assert breaker.state == CircuitState.OPEN
        assert breaker.stats.times_opened == 2

    @pytest.mark.asyncio
    async def test_failure_window_cleanup(self, breaker):
        """Teste Bereinigung alter Fehler ausserhalb des Zeitfensters."""
        # Kurzes Fenster setzen
        breaker.failure_window = 0.1

        # Fehler registrieren
        await breaker.record_failure(RuntimeError("Test"))
        await breaker.record_failure(RuntimeError("Test"))

        # Warte bis Fenster abgelaufen
        await asyncio.sleep(0.2)

        # Neuer Fehler sollte alte bereinigen
        await breaker.record_failure(RuntimeError("Test"))

        # Sollte nicht oeffnen da alte Fehler geloescht
        assert breaker.state == CircuitState.CLOSED

    def test_get_retry_after_when_closed(self, breaker):
        """Teste retry_after ist 0 wenn CLOSED."""
        assert breaker.get_retry_after() == 0.0

    @pytest.mark.asyncio
    async def test_get_retry_after_when_open(self, breaker):
        """Teste retry_after zeigt verbleibende Zeit."""
        for _ in range(3):
            await breaker.record_failure(RuntimeError("Test"))

        retry_after = breaker.get_retry_after()
        assert 0 < retry_after <= 0.5

    def test_reset(self, breaker):
        """Teste manuelles Zuruecksetzen."""
        breaker._state = CircuitState.OPEN
        breaker._stats.failed_calls = 100

        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failed_calls == 0

    def test_get_status(self, breaker):
        """Teste Status-Abfrage."""
        status = breaker.get_status()

        assert status["name"] == "test_backend"
        assert status["state"] == "closed"
        assert "stats" in status
        assert "config" in status
        assert status["config"]["failure_threshold"] == 3


# =============================================================================
# CircuitBreakerRegistry Tests
# =============================================================================


class TestCircuitBreakerRegistry:
    """Tests fuer CircuitBreakerRegistry."""

    @pytest.fixture
    def registry(self):
        """Erstelle frische Registry."""
        return CircuitBreakerRegistry()

    def test_get_or_create_new(self, registry):
        """Teste Erstellung neuer Breaker."""
        breaker = registry.get_or_create("new_backend")

        assert breaker is not None
        assert breaker.name == "new_backend"

    def test_get_or_create_returns_existing(self, registry):
        """Teste Rueckgabe existierender Breaker."""
        breaker1 = registry.get_or_create("backend1")
        breaker2 = registry.get_or_create("backend1")

        assert breaker1 is breaker2

    def test_get_or_create_with_custom_config(self, registry):
        """Teste Erstellung mit eigener Konfiguration."""
        breaker = registry.get_or_create(
            "custom",
            failure_threshold=10,
            recovery_timeout=60.0
        )

        assert breaker.failure_threshold == 10
        assert breaker.recovery_timeout == 60.0

    def test_get_returns_none_for_unknown(self, registry):
        """Teste get() gibt None fuer unbekannte Backends."""
        result = registry.get("unknown")
        assert result is None

    def test_get_returns_existing(self, registry):
        """Teste get() gibt existierenden Breaker zurueck."""
        registry.get_or_create("existing")
        breaker = registry.get("existing")

        assert breaker is not None

    @pytest.mark.asyncio
    async def test_get_all_status(self, registry):
        """Teste Abfrage aller Status."""
        registry.get_or_create("backend1")
        registry.get_or_create("backend2")

        all_status = registry.get_all_status()

        assert "backend1" in all_status
        assert "backend2" in all_status
        assert all_status["backend1"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_get_open_circuits(self, registry):
        """Teste Abfrage offener Circuits."""
        breaker1 = registry.get_or_create("healthy")
        breaker2 = registry.get_or_create("unhealthy")

        # Oeffne einen Circuit
        for _ in range(5):
            await breaker2.record_failure(RuntimeError("Test"))

        open_circuits = registry.get_open_circuits()

        assert "unhealthy" in open_circuits
        assert "healthy" not in open_circuits

    def test_reset_all(self, registry):
        """Teste Zuruecksetzen aller Circuits."""
        breaker1 = registry.get_or_create("b1")
        breaker2 = registry.get_or_create("b2")

        breaker1._state = CircuitState.OPEN
        breaker2._state = CircuitState.OPEN

        registry.reset_all()

        assert breaker1.state == CircuitState.CLOSED
        assert breaker2.state == CircuitState.CLOSED


# =============================================================================
# Singleton Tests
# =============================================================================


class TestRegistrySingleton:
    """Tests fuer Singleton-Pattern der Registry."""

    def test_get_circuit_breaker_registry_returns_singleton(self):
        """Teste dass Singleton zurueckgegeben wird."""
        import app.services.circuit_breaker as cb_module

        # Reset
        cb_module._registry = None

        registry1 = get_circuit_breaker_registry()
        registry2 = get_circuit_breaker_registry()

        assert registry1 is registry2


# =============================================================================
# Decorator Tests
# =============================================================================


class TestCircuitBreakerDecorator:
    """Tests fuer @circuit_breaker_protected Decorator."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset Registry vor jedem Test."""
        import app.services.circuit_breaker as cb_module
        cb_module._registry = None
        yield
        cb_module._registry = None

    @pytest.mark.asyncio
    async def test_decorator_success_path(self):
        """Teste Decorator bei erfolgreichem Aufruf."""
        @circuit_breaker_protected("test_decorator")
        async def successful_function():
            return "success"

        result = await successful_function()

        assert result == "success"

        # Pruefe dass Erfolg gezaehlt wurde
        registry = get_circuit_breaker_registry()
        breaker = registry.get("test_decorator")
        assert breaker.stats.successful_calls == 1

    @pytest.mark.asyncio
    async def test_decorator_failure_path(self):
        """Teste Decorator bei Fehler."""
        @circuit_breaker_protected("failing_backend")
        async def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_function()

        # Pruefe dass Fehler gezaehlt wurde
        registry = get_circuit_breaker_registry()
        breaker = registry.get("failing_backend")
        assert breaker.stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_decorator_raises_circuit_breaker_error_when_open(self):
        """Teste Decorator wirft CircuitBreakerError wenn offen."""
        @circuit_breaker_protected("open_test")
        async def some_function():
            raise RuntimeError("Test")

        # Oeffne Circuit durch Fehler
        registry = get_circuit_breaker_registry()
        breaker = registry.get_or_create("open_test", failure_threshold=2)

        for _ in range(2):
            await breaker.record_failure(RuntimeError("Test"))

        # Sollte CircuitBreakerError werfen
        with pytest.raises(CircuitBreakerError) as exc_info:
            await some_function()

        assert exc_info.value.backend == "open_test"
        assert exc_info.value.state == CircuitState.OPEN


# =============================================================================
# Concurrency Tests
# =============================================================================


class TestCircuitBreakerConcurrency:
    """Tests fuer Thread-Sicherheit."""

    @pytest.mark.asyncio
    async def test_concurrent_success_recording(self):
        """Teste gleichzeitige Erfolgsaufzeichnungen."""
        breaker = CircuitBreaker("concurrent_test")

        async def record_success():
            await breaker.record_success()

        # 100 gleichzeitige Erfolge
        await asyncio.gather(*[record_success() for _ in range(100)])

        assert breaker.stats.successful_calls == 100
        assert breaker.stats.total_calls == 100

    @pytest.mark.asyncio
    async def test_concurrent_failure_recording(self):
        """Teste gleichzeitige Fehleraufzeichnungen."""
        breaker = CircuitBreaker(
            "concurrent_fail",
            failure_threshold=200  # Hoch setzen um nicht zu oeffnen
        )

        async def record_failure():
            await breaker.record_failure(RuntimeError("Test"))

        # 50 gleichzeitige Fehler
        await asyncio.gather(*[record_failure() for _ in range(50)])

        assert breaker.stats.failed_calls == 50

    @pytest.mark.asyncio
    async def test_concurrent_state_checks(self):
        """Teste gleichzeitige Zustandsabfragen."""
        breaker = CircuitBreaker("state_check_test")

        async def check_state():
            return await breaker.can_execute()

        results = await asyncio.gather(*[check_state() for _ in range(50)])

        # Alle sollten True sein (CLOSED state)
        assert all(results)


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestCircuitBreakerWorkflow:
    """Integration-Tests fuer komplette Workflows."""

    @pytest.mark.asyncio
    async def test_complete_failure_recovery_workflow(self):
        """Teste kompletten Fehler-Recovery-Workflow."""
        breaker = CircuitBreaker(
            name="workflow_test",
            failure_threshold=3,
            recovery_timeout=0.3,
            success_threshold=2
        )

        # Phase 1: Normale Operationen
        for _ in range(5):
            await breaker.record_success()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.successful_calls == 5

        # Phase 2: Fehler fuehren zu OPEN
        for _ in range(3):
            await breaker.record_failure(RuntimeError("Backend down"))

        assert breaker.state == CircuitState.OPEN
        assert not await breaker.can_execute()

        # Phase 3: Warte und transition zu HALF_OPEN
        await asyncio.sleep(0.4)
        assert await breaker.can_execute()
        assert breaker.state == CircuitState.HALF_OPEN

        # Phase 4: Erfolge fuehren zu CLOSED
        await breaker.record_success()
        await breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_multiple_backends_independent(self):
        """Teste dass mehrere Backends unabhaengig sind."""
        registry = CircuitBreakerRegistry()

        deepseek = registry.get_or_create("deepseek", failure_threshold=3)
        got_ocr = registry.get_or_create("got_ocr", failure_threshold=3)
        surya = registry.get_or_create("surya", failure_threshold=3)

        # DeepSeek faellt aus
        for _ in range(3):
            await deepseek.record_failure(RuntimeError("DeepSeek error"))

        # Andere sollten noch funktionieren
        assert deepseek.state == CircuitState.OPEN
        assert got_ocr.state == CircuitState.CLOSED
        assert surya.state == CircuitState.CLOSED

        # GOT-OCR kann noch Erfolge verzeichnen
        await got_ocr.record_success()
        assert got_ocr.stats.successful_calls == 1

    @pytest.mark.asyncio
    async def test_flapping_prevention(self):
        """Teste dass schnelles Wechseln verhindert wird."""
        breaker = CircuitBreaker(
            name="flap_test",
            failure_threshold=2,
            recovery_timeout=0.2,
            success_threshold=3  # Braucht 3 Erfolge zum Schliessen
        )

        # Oeffne
        await breaker.record_failure(RuntimeError("1"))
        await breaker.record_failure(RuntimeError("2"))
        assert breaker.state == CircuitState.OPEN

        # Warte und gehe zu HALF_OPEN
        await asyncio.sleep(0.3)
        await breaker.can_execute()

        # Nur 1 Erfolg reicht nicht
        await breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN

        # Noch ein Erfolg
        await breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN

        # Dritter Erfolg schliesst
        await breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
