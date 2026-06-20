# -*- coding: utf-8 -*-
"""
Pytest configuration for integration tests.

Provides shared fixtures for:
- Temporary storage
- Database sessions
- Redis connections
- ML component mocking

Feinpoliert und durchdacht - Stabile Integration Test Infrastruktur.
"""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Generator
import asyncio
import sys

# Ensure app is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Einheitliche Test-DB-URL fuer Integrationstests:
# TEST_DATABASE_URL hat Vorrang (Docker/CI), sonst lokaler Fallback.
INTEGRATION_DB_FALLBACK_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5433/ablage_test"
)


def integration_db_url() -> str:
    """Liefert die Test-Datenbank-URL (env-gesteuert mit lokalem Fallback)."""
    return os.environ.get("TEST_DATABASE_URL", INTEGRATION_DB_FALLBACK_URL)


@pytest.fixture
def db_session() -> Generator:
    """Synchrone DB-Session fuer Schema-Verifikationstests.

    ``test_index_verification.py`` prueft Indizes/Constraints mit synchronen
    ``execute(...)``-Aufrufen, definierte aber keine eigene Fixture
    (17 Tests endeten als ERROR "fixture 'db_session' not found").
    Die asyncpg-URL wird fuer den synchronen Treiber umgeschrieben.
    Ohne erreichbares PostgreSQL wird sauber geskippt.
    """
    try:
        from sqlalchemy import create_engine
    except ImportError:
        pytest.skip("SQLAlchemy nicht verfuegbar")

    sync_url = integration_db_url().replace("+asyncpg", "+psycopg2")
    engine = None
    try:
        engine = create_engine(sync_url, pool_pre_ping=True)
        connection = engine.connect()
    except Exception as exc:
        if engine is not None:
            engine.dispose()
        pytest.skip(f"PostgreSQL-Testdatenbank nicht erreichbar: {exc}")
    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_storage() -> Generator[Path, None, None]:
    """Provide temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        # Create standard subdirectories
        (storage / "drift").mkdir()
        (storage / "ab_tests").mkdir()
        (storage / "shap").mkdir()
        (storage / "models").mkdir()
        yield storage


@pytest.fixture
def ml_test_features():
    """Provide standard test features for ML tests."""
    return {
        "quality_score": 0.85,
        "file_size_mb": 1.5,
        "complexity": "medium",
        "has_tables": True,
        "has_images": False,
        "language": "de",
        "page_count": 3,
        "dpi": 300,
    }


@pytest.fixture
def sample_document_batch():
    """Provide batch of sample documents for testing."""
    documents = []
    for i in range(20):
        documents.append({
            "id": f"doc_{i:04d}",
            "features": {
                "quality_score": 0.6 + (i % 4) * 0.1,
                "file_size_mb": 0.5 + i * 0.2,
                "complexity": ["low", "medium", "high", "very_high"][i % 4],
                "has_tables": i % 3 == 0,
                "language": ["de", "en"][i % 2],
            },
            "expected_backend": ["deepseek", "got_ocr", "surya"][i % 3],
        })
    return documents


@pytest.fixture
def mock_ocr_result():
    """Provide mock OCR processing result."""
    return {
        "success": True,
        "text": "Dies ist ein Beispieltext mit deutschen Umlauten: ä, ö, ü, ß",
        "confidence": 0.95,
        "processing_time_ms": 1250.0,
        "backend": "deepseek",
        "language": "de",
        "word_count": 11,
        "pages": 1,
    }


# Markers for test categorization
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "ml: mark test as ML-related"
    )
