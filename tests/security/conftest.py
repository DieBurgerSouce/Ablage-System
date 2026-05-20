# -*- coding: utf-8 -*-
"""
Security Tests Conftest - Shared Fixtures for OWASP Security Testing.

WICHTIG: Diese Fixtures verwenden den ECHTEN TestClient und die echte App.
Die Mock-basierten Fixtures in den einzelnen Test-Dateien werden DEAKTIVIERT.

Fuer Enterprise-Grade Security Tests muessen wir gegen die echte Anwendung testen!
"""

import os
import sys
from pathlib import Path
from typing import Generator, Dict, Any
from uuid import uuid4

import pytest
import pytest_asyncio

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Set DEBUG before imports
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("TESTING", "true")

# Import with graceful fallback
try:
    from fastapi.testclient import TestClient
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.db.models import User, Company
    from app.core.security import get_password_hash, create_access_token
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    APP_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import app components: {e}")
    APP_AVAILABLE = False
    app = None


# =============================================================================
# TEST CLIENT FIXTURES (ECHTE APP!)
# =============================================================================


@pytest.fixture(scope="session")
def _check_app_available():
    """Prueft ob die App verfuegbar ist."""
    if not APP_AVAILABLE:
        pytest.skip("App not available - run with docker-compose up backend")


@pytest.fixture
def test_client(_check_app_available) -> Generator[TestClient, None, None]:
    """
    ECHTER TestClient fuer Security Tests.

    NICHT den MagicMock aus den Test-Dateien verwenden!
    Dieser Fixture ueberschreibt alle lokalen Mock-Fixtures.
    """
    if not APP_AVAILABLE:
        pytest.skip("App not available")

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest_asyncio.fixture
async def async_test_client(_check_app_available) -> AsyncClient:
    """Async Test Client fuer async Security Tests."""
    if not APP_AVAILABLE:
        pytest.skip("App not available")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# =============================================================================
# AUTHENTICATION FIXTURES
# =============================================================================


@pytest.fixture
def auth_headers(_check_app_available) -> Dict[str, str]:
    """
    Echte Auth-Headers mit gueltigem JWT Token.

    Fuer Security Tests brauchen wir echte Tokens um:
    - Rate Limiting zu testen
    - IDOR zu testen
    - Privilege Escalation zu testen
    """
    if not APP_AVAILABLE:
        return {"Authorization": "Bearer invalid-token"}

    # Erstelle einen echten Test-Token
    test_user_data = {
        "sub": str(uuid4()),
        "email": "security-test@ablage.local",
        "is_active": True,
        "is_superuser": False,
        "company_id": str(uuid4()),
    }
    token = create_access_token(data=test_user_data)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_admin(_check_app_available) -> Dict[str, str]:
    """Admin Auth-Headers fuer privilegierte Tests."""
    if not APP_AVAILABLE:
        return {"Authorization": "Bearer invalid-token"}

    admin_user_data = {
        "sub": str(uuid4()),
        "email": "admin-test@ablage.local",
        "is_active": True,
        "is_superuser": True,
        "company_id": str(uuid4()),
    }
    token = create_access_token(data=admin_user_data)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_company_a(_check_app_available) -> Dict[str, str]:
    """Auth-Headers fuer Company A (Multi-Tenant Tests)."""
    if not APP_AVAILABLE:
        return {"Authorization": "Bearer invalid-token"}

    company_a_id = "00000000-0000-0000-0000-000000000001"
    user_data = {
        "sub": str(uuid4()),
        "email": "user-a@company-a.local",
        "is_active": True,
        "is_superuser": False,
        "company_id": company_a_id,
    }
    token = create_access_token(data=user_data)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_company_b(_check_app_available) -> Dict[str, str]:
    """Auth-Headers fuer Company B (Multi-Tenant Tests)."""
    if not APP_AVAILABLE:
        return {"Authorization": "Bearer invalid-token"}

    company_b_id = "00000000-0000-0000-0000-000000000002"
    user_data = {
        "sub": str(uuid4()),
        "email": "user-b@company-b.local",
        "is_active": True,
        "is_superuser": False,
        "company_id": company_b_id,
    }
    token = create_access_token(data=user_data)
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# LOG CAPTURE FIXTURES
# =============================================================================


@pytest.fixture
def log_capture():
    """Capture log output fuer PII Leakage Tests."""
    import io
    import logging

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)

    # Capture all loggers
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)

    yield log_stream

    # Cleanup
    root_logger.removeHandler(handler)
    root_logger.setLevel(original_level)


# =============================================================================
# DATABASE FIXTURES (Optional - fuer Integration Tests)
# =============================================================================


@pytest_asyncio.fixture
async def test_db_session() -> AsyncSession:
    """
    Echte Datenbank-Session fuer Security Integration Tests.

    Benoetogt laufende PostgreSQL-Instanz (docker-compose up postgres).
    """
    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://ablage_admin:changeme@localhost:5433/ablage_test"
    )

    if "sqlite" in db_url.lower():
        pytest.skip("Security tests require PostgreSQL")

    try:
        engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
        async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session_maker() as session:
            yield session

        await engine.dispose()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")


# =============================================================================
# HELPER FIXTURES
# =============================================================================


@pytest.fixture
def random_uuid() -> str:
    """Generiert eine zufaellige UUID."""
    return str(uuid4())


@pytest.fixture
def test_user() -> Dict[str, Any]:
    """Test-User Daten fuer GDPR/PII Tests."""
    return {
        "id": str(uuid4()),
        "email": "test-user@ablage.local",
        "username": "testuser",
        "company_id": str(uuid4()),
        "is_active": True,
        "is_superuser": False,
    }


@pytest.fixture
def malicious_payloads() -> Dict[str, list]:
    """Sammlung von bekannten Angriffs-Payloads."""
    return {
        "sql_injection": [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "1 UNION SELECT * FROM users",
            "admin'--",
        ],
        "xss": [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>",
        ],
        "command_injection": [
            "; cat /etc/passwd",
            "| ls -la",
            "`whoami`",
            "$(cat /etc/passwd)",
        ],
        "path_traversal": [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "....//....//etc/passwd",
        ],
        "ssrf": [
            "http://127.0.0.1:8080",
            "http://localhost:6379",
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
        ],
    }


# =============================================================================
# MARKER CONFIGURATION
# =============================================================================


def pytest_configure(config):
    """Configure custom markers for security tests."""
    config.addinivalue_line(
        "markers", "owasp_a01: Broken Access Control tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a02: Cryptographic Failures tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a03: Injection tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a04: Insecure Design tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a05: Security Misconfiguration tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a06: Vulnerable Components tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a07: Authentication Failures tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a08: Software Integrity Failures tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a09: Logging Failures tests"
    )
    config.addinivalue_line(
        "markers", "owasp_a10: SSRF tests"
    )
    config.addinivalue_line(
        "markers", "pii_gdpr: PII/GDPR compliance tests"
    )
    config.addinivalue_line(
        "markers", "multi_tenant: Multi-tenant isolation tests"
    )
