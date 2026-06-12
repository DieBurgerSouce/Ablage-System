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

# G5: Cache fuer fehlgeschlagenen App-Startup (DB nicht verfuegbar). Verhindert,
# dass JEDER test_client-Test erneut ~20s auf den DB-Connect-Timeout wartet -
# nach dem ersten Fehlschlag wird sofort uebersprungen.
_APP_STARTUP_STATE: dict[str, str] = {}


@pytest.fixture(scope="session")
def _check_app_available():
    """Prueft ob die App verfuegbar ist."""
    if not APP_AVAILABLE:
        pytest.skip("App not available - run with docker-compose up backend")


@pytest.fixture(scope="session")
def _session_test_client(_check_app_available) -> Generator[TestClient, None, None]:
    """Session-weiter TestClient: EIN App-Lifespan fuer die gesamte Suite.

    WICHTIG (2026-06-12): Frueher startete JEDER Test einen eigenen
    TestClient-Lifespan. Die globale DB-Engine der App bleibt aber an den
    Event-Loop des ERSTEN Portals gebunden -> ab dem zweiten Lifespan
    schlugen DB-Zugriffe fehl (frueher: Startup-RuntimeError und
    Kaskaden-Skip "App-Startup nicht moeglich"; spaeter: 503 statt
    fachlicher Antworten). Eine echte App startet auch nur einmal - der
    Session-Client bildet das korrekt ab.
    """
    if not APP_AVAILABLE:
        pytest.skip("App not available")

    # G5 (2026-06-03): App-Startup (Lifespan) prueft die DB-Konnektivitaet und
    # wirft RuntimeError, wenn keine Datenbank erreichbar ist. Damit die
    # Security-Tests dann sauber UEBERSPRUNGEN statt mit ERROR abgebrochen werden
    # (kein Tarn-Skip - in CI mit DB laufen sie regulaer), faengt der Fixture den
    # Startup-Fehler explizit ab. Nach dem ersten Fehlschlag wird sofort
    # uebersprungen (Cache), um den ~20s-DB-Timeout nicht je Test zu wiederholen.
    if "startup_error" in _APP_STARTUP_STATE:
        pytest.skip(
            f"App-Startup nicht moeglich (Backend/DB nicht verfuegbar): "
            f"{_APP_STARTUP_STATE['startup_error']}"
        )
    client_cm = TestClient(app, raise_server_exceptions=False)
    try:
        client = client_cm.__enter__()
    except Exception as exc:  # Startup-Fehler (z.B. DB) -> Skip statt Error
        _APP_STARTUP_STATE["startup_error"] = str(exc)
        pytest.skip(f"App-Startup fehlgeschlagen (Backend/DB nicht verfuegbar): {exc}")
    try:
        yield client
    finally:
        client_cm.__exit__(None, None, None)


@pytest.fixture
def test_client(_session_test_client) -> TestClient:
    """
    ECHTER TestClient fuer Security Tests.

    NICHT den MagicMock aus den Test-Dateien verwenden!
    Dieser Fixture ueberschreibt alle lokalen Mock-Fixtures.
    """
    return _session_test_client


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

    # KORREKTUR (2026-06-12): get_current_user() loest den User aus der DB
    # auf - Tokens mit zufaelliger sub fuehrten immer zu 401 "Benutzer nicht
    # gefunden". Daher echten Testuser seeden (get-or-create, idempotent).
    return _company_auth_headers(
        company_id="00000000-0000-0000-0000-0000000000aa",
        company_name="Security-Test Company",
        email="security-test@ablage.local",
        username="security-test-user",
    )


@pytest.fixture
def auth_headers_admin(_check_app_available) -> Dict[str, str]:
    """Admin Auth-Headers fuer privilegierte Tests."""
    if not APP_AVAILABLE:
        return {"Authorization": "Bearer invalid-token"}

    # KORREKTUR (2026-06-12): echter geseedeter Superuser statt Random-sub
    # (siehe auth_headers).
    return _company_auth_headers(
        company_id="00000000-0000-0000-0000-0000000000aa",
        company_name="Security-Test Company",
        email="admin-test@ablage.local",
        username="security-test-admin",
        is_superuser=True,
    )


def _run_coro_isolated(coro):
    """Fuehrt eine Coroutine auf einem frischen, isolierten Loop aus.

    Bewusst OHNE ``asyncio.set_event_loop``: Der globale Current-Loop der
    Test-Session bleibt unberuehrt (keine Event-Loop-Pollution fuer
    nachfolgende async Tests).
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _get_or_create_company_user(
    company_id: str,
    company_name: str,
    email: str,
    username: str,
    is_superuser: bool = False,
) -> str:
    """Legt Company + User + UserCompany-Link idempotent in der echten DB an.

    HINTERGRUND (2026-06-12): get_current_user() loest den User IMMER aus der
    Datenbank auf. Tokens mit zufaelliger sub (uuid4) fuehrten daher zu
    401 "Benutzer nicht gefunden" - die Multi-Tenant-IDOR-Tests prueften nie
    die Mandanten-Isolation, sondern nur kaputte Authentifizierung.
    """
    from uuid import UUID as _UUID

    from sqlalchemy import select

    from app.core.config import settings
    from app.db.models import Company, User
    from app.db.models_cash_company import UserCompany

    engine = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, echo=False
    )
    try:
        session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_maker() as session:
            company_uuid = _UUID(company_id)

            company = await session.get(Company, company_uuid)
            if company is None:
                company = Company(id=company_uuid, name=company_name)
                session.add(company)

            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    email=email,
                    username=username,
                    hashed_password=get_password_hash("Security-Test-Pw-1!"),
                    full_name=f"Security Testuser {company_name}",
                    is_active=True,
                    is_superuser=is_superuser,
                )
                session.add(user)
                await session.flush()

            result = await session.execute(
                select(UserCompany).where(
                    UserCompany.user_id == user.id,
                    UserCompany.company_id == company_uuid,
                )
            )
            link = result.scalar_one_or_none()
            if link is None:
                session.add(
                    UserCompany(
                        user_id=user.id,
                        company_id=company_uuid,
                        role="member",
                        is_current=True,
                    )
                )

            await session.commit()
            return str(user.id)
    finally:
        await engine.dispose()


def _company_auth_headers(
    company_id: str,
    company_name: str,
    email: str,
    username: str,
    is_superuser: bool = False,
) -> Dict[str, str]:
    """Erzeugt Auth-Headers fuer einen ECHTEN (geseedeten) Company-User."""
    try:
        user_id = _run_coro_isolated(
            _get_or_create_company_user(
                company_id, company_name, email, username, is_superuser
            )
        )
    except Exception as exc:  # DB nicht erreichbar -> sauber skippen
        pytest.skip(
            f"Multi-Tenant-Testuser konnte nicht angelegt werden "
            f"(DB nicht verfuegbar?): {exc}"
        )

    user_data = {
        "sub": user_id,
        "email": email,
        "is_active": True,
        "is_superuser": is_superuser,
        "company_id": company_id,
    }
    token = create_access_token(data=user_data)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def seeded_auth_headers_factory():
    """Factory-Fixture: Auth-Headers fuer echte (geseedete) DB-User.

    Fuer Test-Module, die eigene Rollen-User brauchen (z.B.
    test_broken_access.py) - statt Tokens mit zufaelliger sub zu bauen,
    die an get_current_user() immer mit 401 scheitern.
    """
    return _company_auth_headers


@pytest.fixture
def auth_headers_company_a(_check_app_available) -> Dict[str, str]:
    """Auth-Headers fuer Company A (Multi-Tenant Tests, echter DB-User)."""
    if not APP_AVAILABLE:
        return {"Authorization": "Bearer invalid-token"}

    return _company_auth_headers(
        company_id="00000000-0000-0000-0000-000000000001",
        company_name="Security-Test Company A",
        email="user-a@company-a.local",
        username="security-test-user-a",
    )


@pytest.fixture
def auth_headers_company_b(_check_app_available) -> Dict[str, str]:
    """Auth-Headers fuer Company B (Multi-Tenant Tests, echter DB-User)."""
    if not APP_AVAILABLE:
        return {"Authorization": "Bearer invalid-token"}

    return _company_auth_headers(
        company_id="00000000-0000-0000-0000-000000000002",
        company_name="Security-Test Company B",
        email="user-b@company-b.local",
        username="security-test-user-b",
    )


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
