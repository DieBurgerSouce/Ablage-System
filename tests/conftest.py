"""
Pytest configuration and fixtures for Ablage-System OCR tests.

This module provides shared fixtures for database, Redis, MinIO,
authentication, and API testing across the test suite.
"""

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from faker import Faker
from httpx import AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app

# Initialize Faker for test data generation
fake = Faker("de_DE")  # German locale

# =============================================================================
# Event Loop Configuration
# =============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def database_url() -> str:
    """Return database URL for testing (in-memory SQLite)."""
    return "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def async_engine(database_url: str):
    """Create async database engine for testing."""
    engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing."""
    async_session_maker = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


@pytest.fixture(scope="function")
def db_session(async_session: AsyncSession) -> AsyncSession:
    """Alias for async_session for simpler test imports."""
    return async_session


# =============================================================================
# FastAPI Test Client
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create FastAPI test client with database override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(
    client: AsyncClient,
    test_user: dict,
) -> AsyncClient:
    """Create authenticated FastAPI test client."""
    # Login to get token
    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": test_user["email"],
            "password": test_user["password"],
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Add authorization header
    client.headers = {
        **client.headers,
        "Authorization": f"Bearer {token}",
    }

    return client


# =============================================================================
# Redis Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def redis_client() -> MagicMock:
    """Create mock Redis client for testing."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.expire = AsyncMock(return_value=True)
    return mock_redis


# =============================================================================
# MinIO Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def minio_client() -> MagicMock:
    """Create mock MinIO client for testing."""
    mock_minio = MagicMock()
    mock_minio.bucket_exists = MagicMock(return_value=True)
    mock_minio.put_object = MagicMock(return_value=None)
    mock_minio.get_object = MagicMock()
    mock_minio.remove_object = MagicMock(return_value=None)
    mock_minio.list_objects = MagicMock(return_value=[])
    return mock_minio


# =============================================================================
# GPU Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def mock_gpu_manager() -> MagicMock:
    """Create mock GPU manager for testing."""
    mock_gpu = MagicMock()
    mock_gpu.is_available = MagicMock(return_value=True)
    mock_gpu.get_device_count = MagicMock(return_value=1)
    mock_gpu.get_memory_info = MagicMock(return_value={"total": 16000, "used": 8000, "free": 8000})
    mock_gpu.allocate_memory = MagicMock(return_value=True)
    mock_gpu.free_memory = MagicMock(return_value=True)
    return mock_gpu


@pytest.fixture(scope="function")
def gpu_available() -> bool:
    """Check if GPU is available for testing."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# =============================================================================
# Authentication Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def test_user() -> dict:
    """Create test user data."""
    return {
        "email": fake.email(),
        "password": fake.password(length=12),
        "full_name": fake.name(),
        "is_active": True,
        "is_superuser": False,
    }


@pytest.fixture(scope="function")
def test_admin_user() -> dict:
    """Create test admin user data."""
    return {
        "email": "admin@test.local",
        "password": "AdminPassword123!",
        "full_name": "Test Admin",
        "is_active": True,
        "is_superuser": True,
    }


@pytest.fixture(scope="function")
def test_token() -> str:
    """Create test JWT token."""
    from datetime import datetime, timedelta
    from jose import jwt

    payload = {
        "sub": "test@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    secret_key = os.getenv("JWT_SECRET", "test-secret-key")
    return jwt.encode(payload, secret_key, algorithm="HS256")


# =============================================================================
# Document Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def sample_document() -> bytes:
    """Create sample document data (PDF bytes)."""
    # Simple PDF header for testing
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n%%EOF"


@pytest.fixture(scope="function")
def sample_image() -> bytes:
    """Create sample image data (PNG bytes)."""
    # Minimal PNG file (1x1 pixel)
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.fixture(scope="function")
def german_text_samples() -> list[str]:
    """Return sample German text for validation testing."""
    return [
        "Müller GmbH & Co. KG",
        "Straße der 17. Juni 123",
        "Geburtsdatum: 15.03.1985",
        "Preis: 1.234,56 €",
        "IBAN: DE89 3704 0044 0532 0130 00",
        "USt-IdNr.: DE123456789",
        "Geschäftsführer: Jürgen Müßiggang",
        "Über­weisung",  # Contains soft hyphen
        "§ 1 Allgemeine Bestimmungen",
    ]


# =============================================================================
# OCR Backend Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def mock_ocr_backend() -> MagicMock:
    """Create mock OCR backend for testing."""
    mock_backend = MagicMock()
    mock_backend.process = AsyncMock(
        return_value={
            "text": "Extracted text from document",
            "confidence": 0.95,
            "language": "de",
        }
    )
    mock_backend.is_available = MagicMock(return_value=True)
    return mock_backend


@pytest.fixture(params=["deepseek", "got_ocr", "surya"])
def ocr_backend_name(request) -> str:
    """Parametrized fixture for testing all OCR backends."""
    return request.param


# =============================================================================
# Celery Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def celery_app_mock() -> MagicMock:
    """Create mock Celery app for testing."""
    mock_celery = MagicMock()
    mock_celery.send_task = MagicMock(return_value=MagicMock(id="test-task-id"))
    return mock_celery


# =============================================================================
# Environment Variables
# =============================================================================

@pytest.fixture(scope="function", autouse=True)
def test_env_vars(monkeypatch):
    """Set test environment variables."""
    env_vars = {
        "ENVIRONMENT": "testing",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "test-secret-key-for-testing-only",
        "JWT_SECRET": "test-jwt-secret-for-testing-only",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "test-access-key",
        "MINIO_SECRET_KEY": "test-secret-key",
        "GPU_ENABLED": "false",  # Disable GPU by default in tests
        "LOG_LEVEL": "WARNING",  # Reduce log noise in tests
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)


# =============================================================================
# Test Data Factories (using Faker)
# =============================================================================

@pytest.fixture(scope="function")
def user_factory():
    """Factory for creating test user data."""

    def _create_user(**kwargs) -> dict:
        defaults = {
            "email": fake.email(),
            "password": fake.password(length=12),
            "full_name": fake.name(),
            "is_active": True,
            "is_superuser": False,
        }
        defaults.update(kwargs)
        return defaults

    return _create_user


@pytest.fixture(scope="function")
def document_factory():
    """Factory for creating test document data."""

    def _create_document(**kwargs) -> dict:
        defaults = {
            "filename": fake.file_name(extension="pdf"),
            "file_size": fake.random_int(min=1024, max=10485760),
            "mime_type": "application/pdf",
            "language": "de",
            "status": "pending",
        }
        defaults.update(kwargs)
        return defaults

    return _create_document


# =============================================================================
# Cleanup Fixtures
# =============================================================================

@pytest.fixture(scope="function", autouse=True)
def cleanup_after_test():
    """Cleanup resources after each test."""
    yield
    # Cleanup code here if needed (close connections, delete temp files, etc.)
    pass


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")
    config.addinivalue_line("markers", "gpu: mark test as requiring GPU")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "database: mark test as requiring database")
    config.addinivalue_line("markers", "redis: mark test as requiring Redis")
    config.addinivalue_line("markers", "minio: mark test as requiring MinIO")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip GPU tests if GPU not available."""
    try:
        import torch

        gpu_available = torch.cuda.is_available()
    except ImportError:
        gpu_available = False

    if not gpu_available:
        skip_gpu = pytest.mark.skip(reason="GPU not available")
        for item in items:
            if "gpu" in item.keywords:
                item.add_marker(skip_gpu)
