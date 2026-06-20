# -*- coding: utf-8 -*-
"""
Pytest Konfigurations- und Fixtures fuer SSO Config Service Tests.

WICHTIG: Diese conftest.py verwendet einen speziellen Ansatz:
1. Wir mocken das gesamte app.services.auth.sso Package
2. Dann importieren wir NUR das sso_config_service Modul direkt
3. Dies vermeidet die Import-Kette (OIDC, SAML Services, etc.)

Feinpoliert und durchdacht - Enterprise SSO Test Configuration.
"""

import sys
import importlib
import importlib.util
from unittest.mock import MagicMock, Mock, AsyncMock
from typing import TYPE_CHECKING
import os

# ========================= EARLY SETUP =========================
# Set DEBUG before any app imports
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-for-testing")
os.environ.setdefault("SSO_ENCRYPTION_KEY", "a" * 32)

# ========================= Mock problematische Module =========================
#
# WICHTIG (Test-Isolation / Pollution-Guard):
# Diese conftest mockt beim Import zahlreiche Module in sys.modules (echte Libs
# wie minio/surya/PIL und v.a. app.db.models). Ohne Wiederherstellung leckt das
# in nachfolgende Tests (z.B. test_supplier_verification_service: select(
# BusinessEntity.id) -> ArgumentError "Column expression ... expected", weil
# app.db.models ein MagicMock geworden ist).
# Loesung: Wir merken uns fuer JEDEN von uns mutierten sys.modules-Key den
# Original-Zustand und stellen ihn per session-scoped autouse-Fixture am Ende
# der SSO-Tests wieder her (siehe _restore_sys_modules_after_sso unten).

# Original-Zustand der von dieser conftest mutierten sys.modules-Keys merken.
# value=_MODULE_ABSENT bedeutet: Key existierte vorher nicht und muss am Ende
# wieder geloescht werden.
_MODULE_ABSENT = object()
_POLLUTED_MODULE_KEYS: dict = {}
# Falls app.db.models bereits ECHT geladen war: (modul, original_AppConfig)
# zum Wiederherstellen des nur-AppConfig-Patches im Teardown.
_SSO_ORIGINAL_APPCONFIG: list = []


def _remember_module_key(name: str) -> None:
    """Merkt den Original-Zustand eines sys.modules-Keys (idempotent)."""
    if name not in _POLLUTED_MODULE_KEYS:
        _POLLUTED_MODULE_KEYS[name] = sys.modules.get(name, _MODULE_ABSENT)


def _create_mock_module(name):
    """Erzeugt ein Mock-Modul und registriert es in sys.modules."""
    _remember_module_key(name)
    mock = MagicMock()
    sys.modules[name] = mock
    return mock

# Core ML/AI dependencies
_mocks = {}

# pgvector
if "pgvector" not in sys.modules:
    _mocks["pgvector"] = _create_mock_module("pgvector")
    _mocks["pgvector"].sqlalchemy = MagicMock()
    _mocks["pgvector"].sqlalchemy.Vector = MagicMock()
    _remember_module_key("pgvector.sqlalchemy")
    sys.modules["pgvector.sqlalchemy"] = _mocks["pgvector"].sqlalchemy

# tiktoken
if "tiktoken" not in sys.modules:
    _mocks["tiktoken"] = _create_mock_module("tiktoken")
    _mocks["tiktoken"].get_encoding = MagicMock(return_value=MagicMock())

# sentence_transformers
if "sentence_transformers" not in sys.modules:
    _mocks["sentence_transformers"] = _create_mock_module("sentence_transformers")
    _mocks["sentence_transformers"].SentenceTransformer = MagicMock()

# faiss
if "faiss" not in sys.modules:
    _mocks["faiss"] = _create_mock_module("faiss")

# torch
if "torch" not in sys.modules:
    _mocks["torch"] = _create_mock_module("torch")
    _mocks["torch"].cuda = MagicMock()
    _mocks["torch"].cuda.is_available = MagicMock(return_value=False)
    _mocks["torch"].device = MagicMock()

# transformers
if "transformers" not in sys.modules:
    _mocks["transformers"] = _create_mock_module("transformers")

# prometheus_client
if "prometheus_client" not in sys.modules:
    _mocks["prometheus_client"] = _create_mock_module("prometheus_client")
    _mocks["prometheus_client"].Counter = MagicMock(return_value=MagicMock())
    _mocks["prometheus_client"].Histogram = MagicMock(return_value=MagicMock())
    _mocks["prometheus_client"].Gauge = MagicMock(return_value=MagicMock())
    _mocks["prometheus_client"].Summary = MagicMock(return_value=MagicMock())
    _mocks["prometheus_client"].Info = MagicMock(return_value=MagicMock())

# pyotp
if "pyotp" not in sys.modules:
    _mocks["pyotp"] = _create_mock_module("pyotp")
    _mocks["pyotp"].TOTP = MagicMock()
    _mocks["pyotp"].random_base32 = MagicMock(return_value="JBSWY3DPEHPK3PXP")

# qrcode
if "qrcode" not in sys.modules:
    _mocks["qrcode"] = _create_mock_module("qrcode")
    _mocks["qrcode"].make = MagicMock()

# docling
if "docling" not in sys.modules:
    _mocks["docling"] = _create_mock_module("docling")
    _remember_module_key("docling.document_converter")
    sys.modules["docling.document_converter"] = MagicMock()

# numpy
if "numpy" not in sys.modules:
    _mocks["numpy"] = _create_mock_module("numpy")
    _mocks["numpy"].ndarray = MagicMock()
    _mocks["numpy"].array = MagicMock()

# Optional dependencies
# WICHTIG: 'surya' wurde aus dieser Liste ENTFERNT. surya ist im Backend-Image
# echt installiert und wird vom sso_config_service NICHT gebraucht. Es hier am
# Modul-Import (Collection) zu mocken leckte trotz package-scoped Teardown in
# tests/unit/test_surya_agent.py (anderes Package, unzuverlaessiges Teardown-
# Timing) -> 'surya' is not a package. Generell nur Module mocken, deren echte
# Lib NICHT installiert ist (find_spec), damit reale Libs nicht fuer andere
# Tests verfaelscht werden.
for mod_name in [
    "redis", "redis.asyncio", "minio", "celery", "asyncpg", "PIL", "PIL.Image",
    "httpx", "aiohttp", "openai", "anthropic", "langchain",
    "langchain.text_splitter", "langchain_core", "langchain_community",
    "pdf2image", "pypdf", "magic", "boto3", "botocore", "slack_sdk",
    "slack_sdk.web", "slack_sdk.webhook", "jwt", "aiosmtplib",
    "aioimaplib", "watchdog", "watchdog.observers", "watchdog.events"
]:
    if mod_name in sys.modules:
        continue
    # Echte Lib installiert? Dann NICHT mocken (verhindert Pollution realer Libs
    # fuer Tests, die sie echt brauchen). Nur fehlende Deps werden gemockt.
    try:
        if importlib.util.find_spec(mod_name) is not None:
            continue
    except (ImportError, ValueError, ModuleNotFoundError):
        pass
    _remember_module_key(mod_name)
    sys.modules[mod_name] = MagicMock()

# ========================= Ende Mock Section =========================

# ========================= Direct Module Import =========================
# Importiere sso_config_service direkt ohne den sso Package __init__
# zu triggern (der SAML/OIDC Services importiert)

import importlib.util
from pathlib import Path

def _load_sso_config_service_directly():
    """
    Laedt das sso_config_service Modul direkt ohne den sso Package __init__.

    Dies vermeidet das Problem, dass sso/__init__.py SAMLService importiert,
    der defusedxml.ElementTree.Element verwendet (was nicht existiert).
    """
    # Pfad zum Modul finden - vom conftest.py Standort aus:
    # tests/unit/services/auth/sso/conftest.py
    # -> ../../../../../../app/services/auth/sso/sso_config_service.py
    # = Ablage_System/app/services/auth/sso/sso_config_service.py
    conftest_path = Path(__file__).resolve()
    # Go up 6 levels: conftest -> sso -> auth -> services -> unit -> tests -> Ablage_System
    project_root = conftest_path.parent.parent.parent.parent.parent.parent
    module_path = project_root / "app" / "services" / "auth" / "sso" / "sso_config_service.py"

    if not module_path.exists():
        raise ImportError(f"Could not find sso_config_service.py at {module_path}. conftest at {conftest_path}, root at {project_root}")

    # Modul-Spec erstellen
    spec = importlib.util.spec_from_file_location(
        "sso_config_service_direct",
        str(module_path)
    )

    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create spec for {module_path}")

    # Modul laden
    module = importlib.util.module_from_spec(spec)

    # In sys.modules registrieren (damit interne Imports funktionieren)
    sys.modules["sso_config_service_direct"] = module

    # Vor dem Ausfuehren: Mock AppConfig in app.db.models
    # Dies verhindert, dass die SQLAlchemy-Modelle geladen werden
    mock_app_config_class = MagicMock()
    mock_app_config_class.return_value = MagicMock()

    # Mock key Attribut mit SQLAlchemy Column-like Verhalten
    mock_key = MagicMock()
    mock_key.like = MagicMock(return_value=MagicMock())  # Fuer LIKE queries
    mock_key.__eq__ = MagicMock(return_value=MagicMock())  # Fuer WHERE key == value
    mock_app_config_class.key = mock_key

    # app.db.models fuer die SSO-Tests mit Mock-AppConfig versehen.
    # WICHTIG (Pollution-Guard): Wenn das ECHTE app.db.models bereits geladen
    # ist, darf es NICHT durch ein MagicMock ersetzt werden (sonst werden
    # BusinessEntity/Document etc. zu Mocks -> MagicMock(spec=...) und
    # select(BusinessEntity.id) brechen in nachfolgenden Tests). In dem Fall
    # nur AppConfig patchen und das Original-Attribut zur Wiederherstellung
    # merken. Ist app.db.models noch nicht geladen, wird ein Mock-Modul gesetzt
    # und zum Teardown wieder entfernt (-> echtes Modul laedt frisch nach).
    if "app.db.models" not in sys.modules:
        _remember_module_key("app.db.models")
        models_mock = MagicMock()
        models_mock.AppConfig = mock_app_config_class
        sys.modules["app.db.models"] = models_mock
    else:
        _real_models = sys.modules["app.db.models"]
        _SSO_ORIGINAL_APPCONFIG.append(
            (_real_models, getattr(_real_models, "AppConfig", _MODULE_ABSENT))
        )
        _real_models.AppConfig = mock_app_config_class

    # Modul ausfuehren
    spec.loader.exec_module(module)

    # Nach dem Ausfuehren: Patch die SQLAlchemy-Imports im Modul
    # Wir ersetzen die 'select' Funktion mit einer Mock-Version
    mock_select = MagicMock(return_value=MagicMock())

    # AppConfig Mock fuer das Modul
    mock_app_config = MagicMock()
    mock_app_config.key = MagicMock()

    # Speichere die Original-Referenz fuer Tests die sie brauchen
    module._original_select = getattr(module, 'select', None)

    # Ueberschreibe select im Modul (es wird per 'from sqlalchemy import select' importiert)
    if hasattr(module, 'select'):
        module.select = mock_select

    return module


# Lade das Modul einmal bei conftest Import
# Dies ermoeglicht den Tests, es zu verwenden ohne selbst zu importieren
_sso_config_module = None

def get_sso_config_module():
    """Gibt das direkt geladene sso_config_service Modul zurueck."""
    global _sso_config_module
    if _sso_config_module is None:
        _sso_config_module = _load_sso_config_service_directly()
    return _sso_config_module


import pytest
from uuid import uuid4


@pytest.fixture(scope="package", autouse=True)
def _restore_sys_modules_after_sso():
    """Stellt die von dieser conftest mutierten sys.modules nach den SSO-Tests
    wieder her.

    Verhindert Test-Pollution: Diese conftest ersetzt beim Import u.a.
    app.db.models (und echte Libs wie minio/surya/PIL) durch MagicMocks. Ohne
    Wiederherstellung leckt das in spaeter laufende Tests und bricht reale
    SQLAlchemy-Queries (select(BusinessEntity.id) -> ArgumentError in
    test_supplier_verification_service).

    Scope=package: Teardown laeuft, wenn der letzte Test dieses SSO-Pakets
    fertig ist (vor Tests in Geschwister-Verzeichnissen wie external/), damit
    der reale app.db.models-Zustand rechtzeitig wiederhergestellt wird.
    """
    # Sicherstellen, dass das SSO-Modul (und damit der app.db.models-Patch)
    # geladen ist, BEVOR wir am Ende restoren.
    get_sso_config_module()
    yield
    # --- Teardown: Original-Zustand wiederherstellen ---
    for name, original in _POLLUTED_MODULE_KEYS.items():
        if original is _MODULE_ABSENT:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
    # Falls app.db.models real war und nur AppConfig gepatcht wurde:
    for models_module, original_appconfig in _SSO_ORIGINAL_APPCONFIG:
        if original_appconfig is _MODULE_ABSENT:
            if hasattr(models_module, "AppConfig"):
                try:
                    delattr(models_module, "AppConfig")
                except AttributeError:
                    pass
        else:
            models_module.AppConfig = original_appconfig


# Fixtures werden hier definiert, um in allen SSO-Tests verfuegbar zu sein
@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_company_id():
    """Sample company ID for multi-tenant tests."""
    return uuid4()


@pytest.fixture
def another_company_id():
    """Different company ID for isolation tests."""
    return uuid4()


@pytest.fixture
def sample_provider_id():
    """Sample provider ID."""
    return uuid4()


@pytest.fixture
def mock_settings_with_sso_key():
    """Mock settings with SSO_ENCRYPTION_KEY set."""
    mock = MagicMock()
    mock.SSO_ENCRYPTION_KEY = "a" * 32
    mock.SECRET_KEY = "fallback-secret-key"
    return mock


@pytest.fixture
def mock_settings_with_secret_key_only():
    """Mock settings with only SECRET_KEY set (no SSO_ENCRYPTION_KEY)."""
    mock = MagicMock()
    mock.SSO_ENCRYPTION_KEY = None
    mock.SECRET_KEY = "my-secret-key-for-derivation"
    return mock


@pytest.fixture
def mock_settings_no_keys():
    """Mock settings without any encryption keys."""
    mock = MagicMock()
    mock.SSO_ENCRYPTION_KEY = None
    mock.SECRET_KEY = None
    return mock
