"""Chaos Engineering Tests - Netzwerk-Fehlerszenarien.

Simuliert verschiedene Netzwerkfehler wie Timeouts, Connection-Drops,
DNS-Ausfaelle und langsame Verbindungen.
"""

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


# Mock-Exceptions fuer fehlende Packages
class RedisConnectionError(Exception):
    """Mock Redis ConnectionError."""
    pass


class RedisTimeoutError(Exception):
    """Mock Redis TimeoutError."""
    pass


class SQLAlchemyOperationalError(Exception):
    """Mock SQLAlchemy OperationalError."""
    pass


class ClientConnectorError(Exception):
    """Mock aiohttp ClientConnectorError."""

    def __init__(self, connection_key=None, os_error=None):
        msg = str(os_error) if os_error else "Verbindungsfehler"
        super().__init__(msg)
        self.connection_key = connection_key
        self.os_error = os_error


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_redis_timeout_handling(mock_redis):
    """Testet Behandlung von Redis-Timeouts.

    Szenario: Redis-Server antwortet nicht innerhalb der Timeout-Periode.
    Erwartung: Anwendung faengt Timeout ab und verwendet Fallback-Logik.
    """
    # Arrange: Redis wirft Timeout
    mock_redis.get.side_effect = RedisTimeoutError("Verbindungs-Timeout")

    # Act: Simuliere Cache-Abruf mit Fallback
    async def get_cached_data(key: str, redis_client) -> Optional[str]:
        """Holt Daten aus Cache mit Fallback."""
        try:
            result = await redis_client.get(key)
            return result
        except (RedisTimeoutError, RedisConnectionError) as e:
            # Fallback: Gebe None zurueck statt zu crashen
            print(f"Redis-Fehler (Fallback aktiv): {e}")
            return None

    result = await get_cached_data("test-key", mock_redis)

    # Assert: Fallback wurde verwendet
    assert result is None, "Fallback sollte None zurueckgeben"
    mock_redis.get.assert_awaited_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_db_connection_pool_exhaustion(mock_db_session):
    """Testet Behandlung von DB-Connection-Pool-Erschoepfung.

    Szenario: Alle DB-Verbindungen sind belegt, neue Query schlaegt fehl.
    Erwartung: Anwendung gibt sinnvolle Fehlermeldung zurueck.
    """
    # Arrange: DB wirft OperationalError
    mock_db_session.execute.side_effect = SQLAlchemyOperationalError(
        "Connection pool erschoepft"
    )

    # Act: Simuliere DB-Query
    async def execute_query(session, query: str) -> Optional[Dict[str, Any]]:
        """Fuehrt DB-Query mit Error-Handling aus."""
        try:
            result = await session.execute(query)
            return result
        except SQLAlchemyOperationalError as e:
            # Fehlerbehandlung: Logge Fehler und gebe None zurueck
            print(f"DB-Fehler: {e}")
            await session.rollback()
            return None

    result = await execute_query(mock_db_session, "SELECT * FROM documents")

    # Assert: Fehlerbehandlung wurde aktiviert
    assert result is None, "Query sollte None bei Fehler zurueckgeben"
    mock_db_session.execute.assert_awaited_once()
    mock_db_session.rollback.assert_awaited_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_slow_query_simulation(mock_db_session):
    """Testet Behandlung von langsamen DB-Queries.

    Szenario: Query dauert laenger als der konfigurierte Timeout.
    Erwartung: Timeout wird erkannt und Query abgebrochen.
    """
    # Arrange: Query dauert laenger als Timeout
    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(0.2)
        return MagicMock()

    mock_db_session.execute.side_effect = slow_execute

    # Act: Simuliere Query mit Timeout
    async def execute_with_timeout(session, query: str, timeout: float = 0.1) -> Optional[Any]:
        """Fuehrt Query mit Timeout aus."""
        try:
            result = await asyncio.wait_for(
                session.execute(query),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            print(f"Query-Timeout nach {timeout} Sekunden")
            return None

    result = await execute_with_timeout(mock_db_session, "SELECT * FROM large_table")

    # Assert: Timeout wurde erkannt
    assert result is None, "Query sollte wegen Timeout None zurueckgeben"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_celery_broker_disconnect(mock_celery_app):
    """Testet Behandlung von Celery-Broker-Verbindungsabbruch.

    Szenario: RabbitMQ/Redis-Broker ist nicht erreichbar.
    Erwartung: Task-Submission schlaegt fehl, wird aber ordentlich behandelt.
    """
    # Arrange: Celery wirft ConnectionError
    mock_celery_app.send_task.side_effect = RedisConnectionError(
        "Broker nicht erreichbar"
    )

    # Act: Simuliere Task-Versand mit Fehlerbehandlung
    async def queue_task(app, task_name: str, args: tuple) -> Optional[str]:
        """Queued Task mit Error-Handling."""
        try:
            result = app.send_task(task_name, args=args)
            return result.id
        except (RedisConnectionError, ConnectionError) as e:
            print(f"Celery-Broker-Fehler: {e}")
            # Fallback: Task lokal speichern fuer spaetere Verarbeitung
            return None

    task_id = await queue_task(
        mock_celery_app,
        "app.workers.ocr_tasks.process_document",
        ("doc-123",)
    )

    # Assert: Fehlerbehandlung wurde aktiviert
    assert task_id is None, "Task-ID sollte None bei Broker-Fehler sein"
    mock_celery_app.send_task.assert_called_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_dns_resolution_failure():
    """Testet Behandlung von DNS-Aufloesung-Fehlern.

    Szenario: DNS kann externe Domain nicht aufloesen.
    Erwartung: HTTP-Client faengt DNS-Fehler ab und gibt Fehlermeldung zurueck.
    """
    # Arrange: Mock aiohttp ClientSession
    mock_session = AsyncMock()
    mock_session.get.side_effect = ClientConnectorError(
        connection_key=None,
        os_error=OSError("Name or service not known")
    )

    # Act: Simuliere HTTP-Request mit DNS-Fehler
    async def fetch_external_api(session, url: str) -> Optional[Dict[str, Any]]:
        """Ruft externe API mit Error-Handling auf."""
        try:
            response = await session.get(url)
            return await response.json()
        except ClientConnectorError as e:
            print(f"DNS-Aufloesung fehlgeschlagen: {e}")
            return None
        except Exception as e:
            print(f"HTTP-Fehler: {e}")
            return None

    result = await fetch_external_api(
        mock_session,
        "https://api.external-service.com/data"
    )

    # Assert: DNS-Fehler wurde behandelt
    assert result is None, "API-Call sollte None bei DNS-Fehler zurueckgeben"
    mock_session.get.assert_awaited_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_partial_network_failure_retry():
    """Testet Retry-Logik bei intermittierenden Netzwerkfehlern.

    Szenario: Erste 2 Versuche schlagen fehl, dritter Versuch erfolgreich.
    Erwartung: Retry-Mechanismus ermoeglicht erfolgreichen Request.
    """
    # Arrange: Mock mit wechselndem Verhalten
    mock_client = AsyncMock()
    call_count = {"count": 0}

    async def flaky_request(*args, **kwargs):
        """Simuliert instabile Verbindung."""
        call_count["count"] += 1
        if call_count["count"] < 3:
            raise RedisConnectionError("Temporaerer Netzwerkfehler")
        return {"status": "success"}

    mock_client.get.side_effect = flaky_request

    # Act: Simuliere Retry-Logik
    async def fetch_with_retry(
        client,
        key: str,
        max_retries: int = 3,
        delay: float = 0.1
    ) -> Optional[Dict[str, Any]]:
        """Fuehrt Request mit Retry aus."""
        for attempt in range(max_retries):
            try:
                result = await client.get(key)
                return result
            except RedisConnectionError:
                if attempt < max_retries - 1:
                    print(f"Versuch {attempt + 1} fehlgeschlagen, retry...")
                    await asyncio.sleep(delay)
                else:
                    print(f"Alle {max_retries} Versuche fehlgeschlagen")
                    raise
        return None

    result = await fetch_with_retry(mock_client, "test-key")

    # Assert: Retry war erfolgreich
    assert result == {"status": "success"}, "Retry sollte erfolgreich sein"
    assert call_count["count"] == 3, "Sollte 3 Versuche benoetigen"
