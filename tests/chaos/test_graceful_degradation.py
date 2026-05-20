"""Chaos Engineering Tests - Graceful Degradation.

Testet System-Resilience bei Teilausfaellen, Circuit-Breaker-Verhalten
und Failover-Mechanismen.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


class CircuitState(Enum):
    """Circuit-Breaker-Zustaende."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_ocr_backend_failover():
    """Testet automatisches Failover zwischen OCR-Backends.

    Szenario: GPU-OCR schlaegt fehl, System wechselt zu CPU-Backend.
    Erwartung: Nahtloser Wechsel ohne Datenverlust.
    """
    # Arrange: Mock OCR-Backends
    class OCRBackendManager:
        """Verwaltet OCR-Backend-Failover."""

        def __init__(self):
            self.backends = ["deepseek-gpu", "got-ocr-2", "surya-cpu"]
            self.current_index = 0
            self.attempts: List[str] = []

        async def process_document(self, doc_path: str) -> Dict[str, Any]:
            """Verarbeitet Dokument mit Failover."""
            last_error = None

            for backend in self.backends:
                self.attempts.append(backend)
                try:
                    result = await self._try_backend(backend, doc_path)
                    return result
                except Exception as e:
                    last_error = e
                    print(f"Backend {backend} fehlgeschlagen: {e}")
                    continue

            # Alle Backends fehlgeschlagen
            raise RuntimeError(f"Alle OCR-Backends fehlgeschlagen: {last_error}")

        async def _try_backend(self, backend: str, doc_path: str) -> Dict[str, Any]:
            """Versucht einzelnes Backend."""
            if backend == "deepseek-gpu":
                raise RuntimeError("GPU out of memory")
            elif backend == "got-ocr-2":
                raise RuntimeError("Model not loaded")
            else:  # surya-cpu
                return {
                    "text": "Rechnung Nr. 12345\nBetrag: 1.234,56 EUR",
                    "backend": backend,
                    "success": True
                }

    manager = OCRBackendManager()

    # Act: Verarbeite Dokument
    result = await manager.process_document("test.pdf")

    # Assert: CPU-Fallback war erfolgreich
    assert result["success"] is True, "Verarbeitung sollte erfolgreich sein"
    assert result["backend"] == "surya-cpu", "Sollte auf CPU-Backend gefallen sein"
    assert len(manager.attempts) == 3, "Sollte alle 3 Backends versuchen"
    assert manager.attempts == ["deepseek-gpu", "got-ocr-2", "surya-cpu"]


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_cache_miss_db_fallback(mock_redis, mock_db_session):
    """Testet Fallback zu DB bei Redis-Ausfall.

    Szenario: Redis ist nicht erreichbar, System liest direkt aus DB.
    Erwartung: Keine Unterbrechung fuer User, nur langsamere Response.
    """
    # Arrange: Redis wirft Fehler
    mock_redis.get.side_effect = ConnectionError("Redis nicht erreichbar")

    # Mock DB-Ergebnis
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock(
        id="doc-123",
        title="Test-Dokument",
        content="Cached content"
    )
    mock_db_session.execute.return_value = mock_result

    # Act: Simuliere Daten-Abruf mit Cache-Fallback
    async def get_document(
        doc_id: str,
        redis_client,
        db_session
    ) -> Optional[Dict[str, Any]]:
        """Holt Dokument aus Cache oder DB."""
        cache_key = f"doc:{doc_id}"

        # Versuche Cache
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                print("Cache-Hit")
                return {"source": "cache", "data": cached}
        except (ConnectionError, Exception) as e:
            print(f"Cache-Miss (Fehler: {e}), verwende DB-Fallback")

        # Fallback: DB-Query
        result = await db_session.execute(
            "SELECT * FROM documents WHERE id = :doc_id",
            {"doc_id": doc_id}
        )
        doc = result.scalar_one_or_none()

        if doc:
            return {
                "source": "database",
                "data": {
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content
                }
            }

        return None

    result = await get_document("doc-123", mock_redis, mock_db_session)

    # Assert: DB-Fallback wurde verwendet
    assert result is not None, "Sollte Dokument zurueckgeben"
    assert result["source"] == "database", "Sollte aus DB kommen"
    assert result["data"]["id"] == "doc-123"
    mock_db_session.execute.assert_awaited_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_partial_service_failure():
    """Testet System-Verfuegbarkeit bei Teilausfall.

    Szenario: Such-Service faellt aus, aber Upload/Download funktioniert.
    Erwartung: System bleibt fuer andere Features verfuegbar.
    """
    # Arrange: Mock Service-Status
    class ServiceHealthManager:
        """Verwaltet Service-Health-Status."""

        def __init__(self):
            self.services = {
                "upload": True,
                "download": True,
                "search": False,  # ausgefallen
                "ocr": True,
                "export": True
            }

        async def execute_operation(self, operation: str) -> Dict[str, Any]:
            """Fuehrt Operation aus wenn Service verfuegbar."""
            if operation in self.services:
                if self.services[operation]:
                    return {
                        "success": True,
                        "operation": operation,
                        "message": f"{operation} erfolgreich"
                    }
                else:
                    return {
                        "success": False,
                        "operation": operation,
                        "message": f"{operation}-Service temporaer nicht verfuegbar"
                    }

            return {
                "success": False,
                "operation": operation,
                "message": "Unbekannte Operation"
            }

        def get_health_status(self) -> Dict[str, Any]:
            """Gibt Health-Status zurueck."""
            available = sum(1 for status in self.services.values() if status)
            total = len(self.services)

            return {
                "overall_health": "degraded" if available < total else "healthy",
                "available_services": available,
                "total_services": total,
                "services": self.services
            }

    manager = ServiceHealthManager()

    # Act: Teste verschiedene Operationen
    upload_result = await manager.execute_operation("upload")
    search_result = await manager.execute_operation("search")
    health = manager.get_health_status()

    # Assert: Upload funktioniert, Search nicht
    assert upload_result["success"] is True, "Upload sollte funktionieren"
    assert search_result["success"] is False, "Search sollte fehlschlagen"
    assert health["overall_health"] == "degraded", "System sollte degraded sein"
    assert health["available_services"] == 4, "4 von 5 Services verfuegbar"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_concurrent_request_storm():
    """Testet System unter Last-Spitzen.

    Szenario: 100 gleichzeitige Requests.
    Erwartung: System bleibt stabil, keine Crashes, akzeptable Error-Rate.
    """
    # Arrange: Mock API-Handler mit Rate-Limiting
    class APIHandler:
        """Simuliert API mit Concurrency-Kontrolle."""

        def __init__(self, max_concurrent: int = 50):
            self.semaphore = asyncio.Semaphore(max_concurrent)
            self.request_count = 0
            self.success_count = 0
            self.error_count = 0
            self.max_concurrent_reached = 0
            self.current_concurrent = 0

        async def handle_request(self, request_id: int) -> Dict[str, Any]:
            """Behandelt einzelnen Request."""
            self.request_count += 1

            # Versuche Semaphore zu akquirieren
            try:
                async with self.semaphore:
                    self.current_concurrent += 1
                    self.max_concurrent_reached = max(
                        self.max_concurrent_reached,
                        self.current_concurrent
                    )

                    # Simuliere Verarbeitung
                    await asyncio.sleep(0.01)

                    self.current_concurrent -= 1
                    self.success_count += 1

                    return {
                        "request_id": request_id,
                        "status": "success"
                    }
            except Exception as e:
                self.error_count += 1
                return {
                    "request_id": request_id,
                    "status": "error",
                    "error": str(e)
                }

    handler = APIHandler(max_concurrent=50)

    # Act: Sende 100 gleichzeitige Requests
    tasks = [handler.handle_request(i) for i in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Assert: System blieb stabil
    assert len(results) == 100, "Alle Requests sollten abgeschlossen sein"
    assert handler.success_count >= 90, "Mindestens 90% sollten erfolgreich sein"
    assert handler.error_count <= 10, "Maximal 10% Fehlerrate erlaubt"
    assert handler.max_concurrent_reached <= 50, "Concurrency-Limit eingehalten"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_circuit_breaker_behavior():
    """Testet Circuit-Breaker-Mechanismus.

    Szenario: Service faellt wiederholt aus, Circuit-Breaker oeffnet sich.
    Erwartung: Schnelle Fehlerrueckgabe statt lange Timeouts.
    """
    # Arrange: Circuit-Breaker-Implementation
    class CircuitBreaker:
        """Circuit-Breaker-Pattern-Implementation."""

        def __init__(
            self,
            failure_threshold: int = 5,
            recovery_timeout: float = 10.0,
            success_threshold: int = 2
        ):
            self.failure_threshold = failure_threshold
            self.recovery_timeout = recovery_timeout
            self.success_threshold = success_threshold

            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time: Optional[datetime] = None

        async def call(self, func, *args, **kwargs) -> Any:
            """Fuehrt Funktion mit Circuit-Breaker aus."""
            if self.state == CircuitState.OPEN:
                # Preufe ob Recovery-Timeout abgelaufen
                if self.last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                    if elapsed >= self.recovery_timeout:
                        print("Circuit-Breaker: Wechsel zu HALF_OPEN")
                        self.state = CircuitState.HALF_OPEN
                        self.success_count = 0
                    else:
                        raise RuntimeError("Circuit-Breaker OPEN: Service unavailable")

            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except Exception:
                self._on_failure()
                raise

        def _on_success(self):
            """Behandelt erfolgreichen Call."""
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    print("Circuit-Breaker: Wechsel zu CLOSED")
                    self.state = CircuitState.CLOSED
                    self.success_count = 0

        def _on_failure(self):
            """Behandelt fehlgeschlagenen Call."""
            self.failure_count += 1
            self.last_failure_time = datetime.now(timezone.utc)

            if self.failure_count >= self.failure_threshold:
                print("Circuit-Breaker: Wechsel zu OPEN")
                self.state = CircuitState.OPEN

    # Mock failing service
    call_count = {"count": 0}

    async def failing_service():
        """Service der wiederholt fehlschlaegt."""
        call_count["count"] += 1
        raise RuntimeError("Service error")

    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2)

    # Act: Fuehre mehrere fehlerhafte Calls aus
    for i in range(5):
        try:
            await breaker.call(failing_service)
        except RuntimeError:
            pass  # Erwarteter Fehler

    # Assert: Circuit-Breaker oeffnete sich
    assert breaker.state == CircuitState.OPEN, "Circuit-Breaker sollte OPEN sein"
    assert call_count["count"] == 3, "Sollte nach 3 Fehlern stoppen"

    # Versuche weiteren Call -> sollte sofort fehlschlagen
    with pytest.raises(RuntimeError, match="Circuit-Breaker OPEN"):
        await breaker.call(failing_service)

    # Count sollte gleich bleiben (kein weiterer Call)
    assert call_count["count"] == 3, "Sollte keinen weiteren Call machen"

    # Warte auf Recovery-Timeout
    await asyncio.sleep(0.3)

    # Mock successful service
    async def working_service():
        """Service der funktioniert."""
        return {"status": "ok"}

    # Sollte jetzt HALF_OPEN sein und erfolgreichen Call erlauben
    result = await breaker.call(working_service)
    assert result == {"status": "ok"}
    assert breaker.state == CircuitState.HALF_OPEN, "Sollte HALF_OPEN sein"

    # Weiterer Erfolg -> zurueck zu CLOSED
    await breaker.call(working_service)
    assert breaker.state == CircuitState.CLOSED, "Sollte zu CLOSED zurueckkehren"
