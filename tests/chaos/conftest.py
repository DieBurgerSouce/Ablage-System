"""Chaos Engineering Test Fixtures.

Gemeinsame Fixtures fuer alle Chaos-Tests zur Simulation von Systemausfaellen.
"""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_redis():
    """Mock Redis-Verbindung fuer Chaos-Tests.

    Simuliert eine Redis-Verbindung mit allen gaengigen Operationen.
    Kann zur Simulation von Verbindungsfehlern und Timeouts verwendet werden.
    """
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.ping = AsyncMock(return_value=True)
    redis.close = AsyncMock()
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def mock_db_session():
    """Mock Datenbank-Session fuer Chaos-Tests.

    Simuliert eine SQLAlchemy AsyncSession mit allen CRUD-Operationen.
    Kann zur Simulation von Verbindungsabbruechen und langsamen Queries verwendet werden.
    """
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()

    # Mock fuer Query-Ergebnisse
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock()
    result.all = MagicMock(return_value=[])
    session.execute.return_value = result

    return session


@pytest.fixture
def mock_minio():
    """Mock MinIO-Client fuer Chaos-Tests.

    Simuliert einen MinIO S3-kompatiblen Storage-Client.
    Kann zur Simulation von Upload/Download-Fehlern verwendet werden.
    """
    client = MagicMock()
    client.put_object = MagicMock()
    client.get_object = MagicMock()
    client.bucket_exists = MagicMock(return_value=True)
    client.remove_object = MagicMock()
    client.list_objects = MagicMock(return_value=[])
    client.stat_object = MagicMock()

    # Mock fuer erfolgreiche Uploads
    upload_result = MagicMock()
    upload_result.etag = "test-etag"
    client.put_object.return_value = upload_result

    return client


@pytest.fixture
def mock_gpu():
    """Mock GPU-Kontext fuer Chaos-Tests.

    Simuliert CUDA/GPU-Zugriff fuer Tests ohne echte GPU.
    Kann zur Simulation von OOM und Device-Fehlern verwendet werden.
    """
    gpu = MagicMock()
    gpu.memory_allocated = MagicMock(return_value=4 * 1024**3)  # 4GB
    gpu.memory_total = MagicMock(return_value=16 * 1024**3)  # 16GB
    gpu.is_available = MagicMock(return_value=True)
    gpu.device_count = MagicMock(return_value=1)
    gpu.get_device_properties = MagicMock()

    # Mock fuer Device-Properties
    props = MagicMock()
    props.total_memory = 16 * 1024**3
    props.name = "NVIDIA RTX 4080"
    gpu.get_device_properties.return_value = props

    return gpu


@pytest.fixture
def mock_celery_app():
    """Mock Celery-App fuer Chaos-Tests.

    Simuliert eine Celery-Anwendung fuer Task-Queue Tests.
    Kann zur Simulation von Broker-Verbindungsfehlern verwendet werden.
    """
    app = MagicMock()
    app.send_task = MagicMock()
    app.control = MagicMock()
    app.control.inspect = MagicMock()

    # Mock fuer erfolgreiches Task-Versenden
    task_result = MagicMock()
    task_result.id = "test-task-id"
    task_result.state = "PENDING"
    app.send_task.return_value = task_result

    return app


@pytest.fixture
def mock_fastapi_request():
    """Mock FastAPI-Request fuer Chaos-Tests.

    Simuliert einen HTTP-Request fuer API-Endpoint Tests.
    """
    request = MagicMock()
    request.headers = {"User-Agent": "chaos-test"}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.url = MagicMock()
    request.url.path = "/api/v1/test"
    return request


@pytest.fixture
def sample_document_data() -> Dict[str, Any]:
    """Beispiel-Dokumentdaten fuer Chaos-Tests.

    Returns:
        Dict mit Dokumentmetadaten fuer Tests
    """
    return {
        "id": "test-doc-123",
        "filename": "test-rechnung.pdf",
        "content_type": "application/pdf",
        "size": 1024 * 100,  # 100KB
        "user_id": "user-123",
        "category": "rechnung"
    }
