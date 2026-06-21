"""Pytest configuration and fixtures for Ablage-System tests."""

import os
import sys
import asyncio
import types
from typing import Generator, AsyncGenerator
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock


def _mock_gpu_modules() -> None:
    """Mock torch and related GPU modules if not installed locally.

    Erlaubt Unit-Tests ohne GPU-Abhaengigkeiten (torch, torchvision, etc.).
    Im Docker-Container mit GPU sind die echten Module installiert.
    """
    modules_to_mock = [
        "torch", "torch.cuda", "torch.nn", "torch.nn.functional",
        "torch.utils", "torch.utils.data", "torch.amp",
        "torchvision", "torchvision.transforms",
        "transformers", "transformers.models", "transformers.pipelines",
        "accelerate", "bitsandbytes",
        "sentence_transformers",
    ]
    for mod_name in modules_to_mock:
        if mod_name not in sys.modules:
            try:
                __import__(mod_name)
            except Exception:
                # Bewusst breit: Eine GPU-Lib kann INSTALLIERT, aber beim Import
                # defekt sein. Beispiel bitsandbytes -> triton waehlt bei
                # sichtbarem NVIDIA-Treiber den CUDA-Backend und versucht, den
                # Treiber-C-Code zur Import-Zeit zu kompilieren; ohne C-Compiler
                # wirft das einen ``RuntimeError`` (nicht ImportError/OSError).
                # Ein zu enges ``except`` liess diese Exception durch und brach
                # die gesamte Test-Collection ab (Schein-Rot der unit/security/
                # integ-Stufen). Fuer einen Offline-Unit-Lauf ist jede solche
                # GPU-Lib ohnehin nur ein Mock - also fallen wir generisch auf
                # den Mock zurueck, egal welche Import-Fehlerart auftritt.
                mock_mod = MagicMock()
                # torch.cuda.is_available() -> False fuer Tests
                if mod_name == "torch":
                    mock_mod.cuda.is_available.return_value = False
                    mock_mod.cuda.device_count.return_value = 0
                    mock_mod.__version__ = "0.0.0-mock"
                sys.modules[mod_name] = mock_mod


def _mock_weasyprint_if_unavailable() -> None:
    """Mockt weasyprint, falls native Bibliotheken (libgobject/pango/GTK) fehlen.

    Auf Windows-Entwicklungsmaschinen ohne GTK-Stack wirft ``import weasyprint``
    einen ``OSError`` (nicht nur ``ImportError``). Der app-seitige
    ``try/except ImportError`` in ``app/services/templates/template_engine.py``
    faengt diesen ``OSError`` NICHT -> dadurch bricht bereits
    ``from app.main import app``, und alle App-abhaengigen Security-/
    Integrationstests werden faelschlich uebersprungen statt ausgefuehrt
    (Schein-Gruen statt Test-Wahrheit).

    Cross-Stream-Fix (out of scope, app/**): ``except (ImportError, OSError)``
    um die weasyprint-Importe in den Template-Services. Bis dahin ueberbrueckt
    dieser test-seitige Mock das Problem. Ist die echte Bibliothek vorhanden
    (Docker/CI mit GTK), bleibt sie aktiv - der Mock greift nur als Fallback.
    """
    if "weasyprint" in sys.modules:
        return
    try:
        import weasyprint  # noqa: F401  # echte Bibliothek bevorzugen (Docker/CI)
    except (ImportError, OSError):
        sys.modules["weasyprint"] = MagicMock()


# Mock GPU modules BEFORE any app imports
_mock_gpu_modules()

# Mock weasyprint, falls native GTK-Libs fehlen (Windows) - sonst bricht app.main
_mock_weasyprint_if_unavailable()

# IMPORTANT: Set DEBUG=true BEFORE any app imports to pass CORS validation
# This must happen before pydantic_settings loads the .env file
os.environ.setdefault("DEBUG", "true")

# B4 (2026-05-19): Rate-Limiter (slowapi) im Unit-Test-Pfad deaktivieren.
# Ohne diesen Switch versucht slowapi sich an Redis (localhost:6380) zu binden
# und schlaegt mit ConnectionError fehl, sobald ein Endpoint mit
# @limiter.limit-Decorator direkt aus Tests aufgerufen wird.
try:
    from app.core.rate_limiting import limiter as _ratelimit_limiter
    _ratelimit_limiter.enabled = False
except Exception:
    pass

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
except (ImportError, Exception) as e:
    # App may not be importable in unit test mode
    app = None
    Base = None
    User = None
    Document = None
    APP_AVAILABLE = False

# Ensure all model modules are imported so SQLAlchemy mapper resolves string relationships.
# Without this, creating model instances (e.g. DomainEvent) fails with
# "expression 'ProcessDefinition' failed to locate a name".
# WICHTIG: importlib statt "import app.db...." verwenden! Ein nacktes
# "import app.db.bpmn_models.bpmn" bindet den Namen ``app`` in DIESEM Modul
# an das Paket-Modul und ueberschreibt damit die oben importierte
# FastAPI-Instanz -> client/async_client erhalten ein Modul statt der App
# ("TypeError: 'module' object is not callable").
try:
    import importlib

    importlib.import_module("app.db.bpmn_models.bpmn")  # ProcessDefinition, ProcessInstance, etc.
    importlib.import_module("app.db.bpmn_models.gobd")  # AuditChainEntry, DocumentArchive, etc.
    importlib.import_module("app.db.models_po_matching")  # PurchaseOrderMatch, MatchStatus
    importlib.import_module("app.db.models_gl_posting")  # JournalEntry, JournalEntryLine
except (ImportError, Exception):
    pass

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
        SECRET_KEY="test-secret-key-minimum-32-characters-for-jwt-signing",
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
            # Modelle nutzen pgvector/pg_trgm-Typen -> Extensions sicherstellen,
            # bevor create_all die Tabellen baut (idempotent).
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            await conn.run_sync(Base.metadata.create_all)

        async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session_maker() as session:
            yield session

        # Cleanup: DROP SCHEMA ... CASCADE statt metadata.drop_all - letzteres
        # scheitert an zyklischen FK-Abhaengigkeiten ohne benannte Constraints
        # (cash_entries/document_groups/documents/expense_reports) mit
        # "Can't sort tables for DROP". CASCADE loest alle Abhaengigkeiten sauber;
        # die Extensions werden im naechsten Setup via IF NOT EXISTS neu angelegt.
        #
        # NACHHALTIGKEITS-HINWEIS: DROP SCHEMA CASCADE nimmt ALLE Objekt-Locks in EINER
        # Transaktion. Bei ~480 Modell-Tabellen kann das max_locks_per_transaction
        # (PG-Default 64) ueberschreiten -> "out of shared memory / increase
        # max_locks_per_transaction" -> die db-Fixture skippt ("Database not available").
        # Ein frischer CI-Lauf (leere Test-DB) ist nicht betroffen; nur wiederholte
        # lokale Laeufe auf einer schon befuellten Test-DB. Dauerhafte Abhilfe: Postgres
        # mit `-c max_locks_per_transaction=256` starten (docker-compose). Lokaler
        # Workaround ohne DB-Reconfig: `DROP DATABASE ablage_test; CREATE DATABASE
        # ablage_test OWNER ablage_admin;` vor dem erneuten Lauf.
        async with engine.begin() as conn:
            await conn.exec_driver_sql("DROP SCHEMA public CASCADE")
            await conn.exec_driver_sql("CREATE SCHEMA public")

        await engine.dispose()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")


# API client fixtures
_APP_STARTUP_STATE: dict = {}


@pytest.fixture
def client(test_settings):
    """Create test client.

    G5 (2026-06-03): Der App-Startup (Lifespan) prueft die DB-Konnektivitaet und
    wirft ohne erreichbare Datenbank einen RuntimeError. Damit Tests dann sauber
    UEBERSPRUNGEN statt mit ERROR abgebrochen werden (in CI mit DB laufen sie
    regulaer), wird der Startup-Fehler abgefangen und nach dem ersten Fehlschlag
    gecacht (kein wiederholter ~20s-DB-Timeout je Test).
    """
    if not APP_AVAILABLE:
        pytest.skip("App not available")
    if "startup_error" in _APP_STARTUP_STATE:
        pytest.skip(
            f"App-Startup nicht moeglich (Backend/DB nicht verfuegbar): "
            f"{_APP_STARTUP_STATE['startup_error']}"
        )
    client_cm = TestClient(app)
    try:
        test_client = client_cm.__enter__()
    except Exception as exc:  # Startup-Fehler (z.B. DB) -> Skip statt Error
        _APP_STARTUP_STATE["startup_error"] = str(exc)
        pytest.skip(f"App-Startup fehlgeschlagen (Backend/DB nicht verfuegbar): {exc}")
    try:
        yield test_client
    finally:
        client_cm.__exit__(None, None, None)


@pytest_asyncio.fixture
async def async_client(test_settings):
    """Create async test client."""
    if not APP_AVAILABLE:
        pytest.skip("App not available")
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# Authentication fixtures
@pytest_asyncio.fixture
async def test_user(test_db):
    """Create a test user for authenticated requests."""
    if not APP_AVAILABLE:
        pytest.skip("App not available")

    from app.db.models import User
    from app.core.security import get_password_hash
    from uuid import uuid4

    user = User(
        id=uuid4(),
        email="test@ablage-system.local",
        username="testuser",
        hashed_password=get_password_hash("Test123!@#"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user):
    """Generate auth headers with valid JWT token."""
    if not APP_AVAILABLE:
        pytest.skip("App not available")

    from app.core.security import create_access_token

    access_token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {access_token}"}


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
_SESSION_EVENT_LOOP: "asyncio.AbstractEventLoop | None" = None


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    global _SESSION_EVENT_LOOP
    loop = asyncio.get_event_loop_policy().new_event_loop()
    _SESSION_EVENT_LOOP = loop
    yield loop
    _SESSION_EVENT_LOOP = None
    loop.close()


@pytest.fixture(autouse=True)
def _repair_global_event_loop() -> Generator[None, None, None]:
    """Stellt vor jedem Test einen funktionsfaehigen Current-Event-Loop sicher.

    Hintergrund (Test-Pollution, Vollsuiten-Lauf 2026-06-12: ~6900 Failures):
    pytest-asyncio 0.23 fuehrt async Tests auf dem *aktuellen* Loop aus
    (``asyncio.get_event_loop()`` in ``wrap_in_sync``), waehrend die
    session-scoped ``event_loop``-Fixture oben nur EINMAL als Current-Loop
    gesetzt wird. Viele Celery-Sync-Wrapper in ``app/workers/tasks/*`` nutzen
    das Muster ``new_event_loop() -> set_event_loop() -> close()`` OHNE den
    vorherigen Loop zu restaurieren; ``asyncio.run()`` setzt den Current-Loop
    am Ende auf ``None``. Ruft ein synchroner Test solchen App-Code auf
    (z.B. ``_run_async`` in duplicate_detection_tasks), ist der globale Loop
    danach geschlossen bzw. entfernt -> ALLE nachfolgenden async Tests der
    Session scheitern mit "Event loop is closed" / "There is no current event
    loop in thread 'MainThread'", obwohl jede Datei standalone gruen ist.

    Dieser Guard repariert den globalen Zustand pro Test: Ist der aktuelle
    Loop geschlossen oder nicht gesetzt, wird der Session-Loop (bevorzugt,
    identisch zum Standalone-Verhalten) oder ersatzweise ein frischer Loop
    als Current-Loop gesetzt.
    """
    import warnings as _warnings

    policy = asyncio.get_event_loop_policy()
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", DeprecationWarning)
            current = policy.get_event_loop()
    except RuntimeError:
        # set_event_loop(None) wurde aufgerufen (z.B. durch asyncio.run())
        current = None
    if current is None or current.is_closed():
        if _SESSION_EVENT_LOOP is not None and not _SESSION_EVENT_LOOP.is_closed():
            policy.set_event_loop(_SESSION_EVENT_LOOP)
        else:
            policy.set_event_loop(policy.new_event_loop())
    yield


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
