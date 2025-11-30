"""Pytest configuration and fixtures for Ablage-System tests."""

import os
import sys
import asyncio
from typing import Generator, AsyncGenerator
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# IMPORTANT: Set DEBUG=true BEFORE any app imports to pass CORS validation
# This must happen before pydantic_settings loads the .env file
os.environ.setdefault("DEBUG", "true")

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import application components - they may not be available for unit tests
try:
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool
    import redis
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

# Import application components with graceful fallback
try:
    from app.main import app
    from app.db.models import Base, User, Document
    APP_AVAILABLE = True
except ImportError as e:
    # App may not be importable in unit test mode
    app = None
    Base = None
    User = None
    Document = None
    APP_AVAILABLE = False

try:
    from app.core.config import Settings
    CONFIG_AVAILABLE = True
except ImportError:
    Settings = None
    CONFIG_AVAILABLE = False


# Test configuration
@pytest.fixture(scope="session")
def test_settings():
    """Override settings for testing."""
    if not CONFIG_AVAILABLE:
        pytest.skip("Settings not available")
    return Settings(
        TESTING=True,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/15",  # Use different DB for tests
        CELERY_TASK_ALWAYS_EAGER=True,  # Execute tasks synchronously in tests
        CELERY_TASK_EAGER_PROPAGATES=True,
        SECRET_KEY="test-secret-key",
        RATE_LIMIT_ENABLED=False,
        GERMAN_VALIDATION_ENABLED=True
    )


# Database fixtures
@pytest_asyncio.fixture
async def test_db():
    """Create test database.

    Note: The models use PostgreSQL-specific types (JSONB, UUID).
    For SQLite tests, we skip database creation and use mocks instead.
    For integration tests requiring database, use docker-compose with PostgreSQL.
    """
    if not SQLALCHEMY_AVAILABLE or not APP_AVAILABLE:
        pytest.skip("Database dependencies not available")

    # Skip for SQLite as models use PostgreSQL-specific types (JSONB, UUID)
    # Use PostgreSQL for database integration tests
    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://ablage_admin:changeme@localhost:5433/ablage_test"
    )

    # Check if we should skip database tests
    if "sqlite" in db_url.lower():
        pytest.skip("Models require PostgreSQL (JSONB, UUID types). Set TEST_DATABASE_URL.")

    try:
        engine = create_async_engine(
            db_url,
            poolclass=NullPool,
            echo=False
        )

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session_maker() as session:
            yield session

        # Cleanup
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await engine.dispose()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")


# API client fixtures
@pytest.fixture
def client(test_settings):
    """Create test client."""
    if not APP_AVAILABLE:
        pytest.skip("App not available")
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def async_client(test_settings):
    """Create async test client."""
    if not APP_AVAILABLE:
        pytest.skip("App not available")
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# Mock fixtures
@pytest.fixture
def mock_gpu_manager():
    """Mock GPU manager."""
    gpu_manager = Mock()
    gpu_manager.get_detailed_status.return_value = {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 4080",
        "device_id": 0,
        "memory_used_mb": 1024,
        "memory_total_mb": 16384,
        "utilization_percent": 10.0
    }
    return gpu_manager


@pytest.fixture
def mock_ocr_service():
    """Mock OCR service."""
    ocr_service = Mock()
    ocr_service.process_document = AsyncMock(return_value={
        "success": True,
        "text": "Beispieltext mit Umlauten: äöüß",
        "confidence": 0.95,
        "backend_used": "surya",
        "processing_time_ms": 1500,
        "has_umlauts": True,
        "german_validation_score": 0.85
    })
    return ocr_service


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_client = Mock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)
    return redis_client


# Sample data fixtures
@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "email": "test@ablage-system.local",
        "username": "testuser",
        "password": "Test123!@#",
        "full_name": "Test User"
    }


@pytest.fixture
def sample_document_data():
    """Sample document data for testing."""
    return {
        "filename": "test_document.pdf",
        "language": "de",
        "document_type": "invoice",
        "backend": "auto"
    }


@pytest.fixture
def sample_german_text():
    """Sample German text with umlauts."""
    return """
    Sehr geehrte Damen und Herren,
    
    hiermit übersenden wir Ihnen die Rechnung für die erbrachten Leistungen.
    
    Rechnungsnummer: RE-2024-001
    Datum: 15.03.2024
    Betrag: 1.234,56 €
    
    Bankverbindung:
    IBAN: DE89 3704 0044 0532 0130 00
    USt-IdNr.: DE123456789
    
    Mit freundlichen Grüßen
    Müller GmbH
    """


@pytest.fixture
def sample_pdf_file(tmp_path):
    """Create a sample PDF file for testing."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4

        pdf_path = tmp_path / "test.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        c.drawString(100, 750, "Test PDF Document")
        c.drawString(100, 700, "This is a test document with German text:")
        c.drawString(100, 650, "Aepfel, Oel, Ueberpruefung, Strasse")
        c.save()

        return pdf_path
    except ImportError:
        # Fallback: create a minimal PDF without reportlab
        pdf_path = tmp_path / "test.pdf"
        # Minimal valid PDF
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test PDF) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000206 00000 n
trailer << /Size 5 /Root 1 0 R >>
startxref
300
%%EOF"""
        pdf_path.write_bytes(pdf_content)
        return pdf_path


@pytest.fixture
def sample_image_file(tmp_path):
    """Create a sample image file for testing."""
    from PIL import Image, ImageDraw, ImageFont
    
    img_path = tmp_path / "test.png"
    img = Image.new('RGB', (800, 600), color='white')
    d = ImageDraw.Draw(img)
    
    # Add text
    d.text((10, 10), "Test Image", fill='black')
    d.text((10, 50), "German Text: Müller, Größe, Überprüfung", fill='black')
    
    img.save(img_path)
    return img_path


# Event loop configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Cleanup fixtures
@pytest.fixture(autouse=True)
async def cleanup_uploads(tmp_path):
    """Clean up uploaded files after each test."""
    yield
    # Cleanup logic here if needed


# Test markers
def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests"
    )
    config.addinivalue_line(
        "markers", "gpu: Tests requiring GPU"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests"
    )
    config.addinivalue_line(
        "markers", "api: API endpoint tests"
    )
    config.addinivalue_line(
        "markers", "performance: Performance tests"
    )
