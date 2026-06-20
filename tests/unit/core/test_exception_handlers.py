# -*- coding: utf-8 -*-
"""
Unit Tests für Unified Exception Handlers.

Testet:
- Standardisierte Fehlerantworten
- Deutsche Fehlermeldungen
- HTTP-Status-Code-Mapping
- Sensible Datenfilterung

Created: 2025-11-30
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.core.exception_handlers import (
    create_error_response,
    _sanitize_details,
    _get_error_category,
    _translate_validation_error,
    _should_include_details,
    EXCEPTION_STATUS_CODES,
    ablage_system_exception_handler,
    http_exception_handler,
    generic_exception_handler,
)
from app.core.exceptions import (
    AblageSystemException,
    GPUOutOfMemoryError,
    GPUNotAvailableError,
    OCRProcessingError,
    DocumentNotFoundError,
    InvalidDocumentFormatError,
    FileSizeExceededError,
    DatabaseConnectionError,
    GDPRViolationError,
    UserNotFoundError,
)


pytestmark = [pytest.mark.unit]


class TestCreateErrorResponse:
    """Tests für create_error_response Funktion."""

    def test_basic_error_response(self):
        """Basis-Fehlerantwort enthält Pflichtfelder."""
        response = create_error_response(
            fehler="Testfehler",
            nachricht="Dies ist eine Testnachricht",
            status_code=400,
        )

        assert response["fehler"] == "Testfehler"
        assert response["nachricht"] == "Dies ist eine Testnachricht"
        assert response["status_code"] == 400
        assert "zeitstempel" in response

    def test_error_response_with_error_code(self):
        """Fehlerantwort mit Fehlercode."""
        response = create_error_response(
            fehler="GPU-Fehler",
            nachricht="GPU nicht verfügbar",
            status_code=503,
            fehler_code="E002",
        )

        assert response["fehler_code"] == "E002"

    def test_error_response_with_path(self):
        """Fehlerantwort mit Pfad."""
        response = create_error_response(
            fehler="Nicht gefunden",
            nachricht="Ressource nicht gefunden",
            status_code=404,
            pfad="/api/v1/documents/123",
        )

        assert response["pfad"] == "/api/v1/documents/123"

    def test_error_response_with_retry_after(self):
        """Fehlerantwort mit Retry-After."""
        response = create_error_response(
            fehler="Service nicht verfügbar",
            nachricht="Bitte später erneut versuchen",
            status_code=503,
            retry_after=60,
        )

        assert response["retry_after"] == 60

    def test_error_response_timestamp_is_utc(self):
        """Zeitstempel ist im ISO-Format mit UTC."""
        response = create_error_response(
            fehler="Test",
            nachricht="Test",
            status_code=400,
        )

        # Sollte ein gültiger ISO-Zeitstempel sein
        timestamp = response["zeitstempel"]
        assert "T" in timestamp
        # Sollte UTC sein (Z oder +00:00)
        assert timestamp.endswith("Z") or "+00:00" in timestamp


class TestSanitizeDetails:
    """Tests für _sanitize_details Funktion."""

    def test_removes_password(self):
        """Passwörter werden entfernt."""
        details = {"password": "geheim123", "user": "test"}
        safe = _sanitize_details(details)

        assert safe["password"] == "[REDACTED]"
        assert safe["user"] == "test"

    def test_removes_token(self):
        """Tokens werden entfernt."""
        details = {"access_token": "jwt.token.here", "type": "Bearer"}
        safe = _sanitize_details(details)

        assert safe["access_token"] == "[REDACTED]"

    def test_removes_api_key(self):
        """API-Keys werden entfernt."""
        details = {"api_key": "sk-123456", "rate_limit": 100}
        safe = _sanitize_details(details)

        assert safe["api_key"] == "[REDACTED]"

    def test_removes_iban(self):
        """IBANs werden entfernt."""
        details = {"iban": "DE89370400440532013000", "name": "Test"}
        safe = _sanitize_details(details)

        assert safe["iban"] == "[REDACTED]"

    def test_removes_email(self):
        """E-Mails werden entfernt."""
        details = {"email": "test@example.com", "status": "active"}
        safe = _sanitize_details(details)

        assert safe["email"] == "[REDACTED]"

    def test_truncates_long_strings(self):
        """Lange Strings werden gekürzt."""
        long_text = "A" * 500
        details = {"content": long_text}
        safe = _sanitize_details(details)

        assert len(safe["content"]) <= 203  # 200 + "..."
        assert safe["content"].endswith("...")

    def test_handles_nested_dicts(self):
        """Verschachtelte Dicts werden verarbeitet."""
        details = {
            "user": {
                "email": "test@example.com",
                "name": "Test User"
            }
        }
        safe = _sanitize_details(details)

        assert safe["user"]["email"] == "[REDACTED]"
        assert safe["user"]["name"] == "Test User"


class TestExceptionStatusCodes:
    """Tests für HTTP-Status-Code-Mapping."""

    def test_gpu_errors_are_503(self):
        """GPU-Fehler geben 503 zurück."""
        assert EXCEPTION_STATUS_CODES[GPUOutOfMemoryError] == 503
        assert EXCEPTION_STATUS_CODES[GPUNotAvailableError] == 503

    def test_document_not_found_is_404(self):
        """Dokument nicht gefunden gibt 404 zurück."""
        assert EXCEPTION_STATUS_CODES[DocumentNotFoundError] == 404

    def test_user_not_found_is_404(self):
        """Benutzer nicht gefunden gibt 404 zurück."""
        assert EXCEPTION_STATUS_CODES[UserNotFoundError] == 404

    def test_file_size_exceeded_is_413(self):
        """Dateigröße überschritten gibt 413 zurück."""
        assert EXCEPTION_STATUS_CODES[FileSizeExceededError] == 413

    def test_invalid_format_is_400(self):
        """Ungültiges Format gibt 400 zurück."""
        assert EXCEPTION_STATUS_CODES[InvalidDocumentFormatError] == 400

    def test_gdpr_violation_is_403(self):
        """GDPR-Verstoß gibt 403 zurück."""
        assert EXCEPTION_STATUS_CODES[GDPRViolationError] == 403

    def test_database_error_is_500(self):
        """Datenbankfehler gibt 500 zurück."""
        assert EXCEPTION_STATUS_CODES[DatabaseConnectionError] == 500


class TestGetErrorCategory:
    """Tests für _get_error_category Funktion."""

    def test_gpu_exception_category(self):
        """GPU-Exceptions haben Kategorie 'GPU-Fehler'."""
        exc = GPUNotAvailableError("Test")
        assert _get_error_category(exc) == "GPU-Fehler"

    def test_ocr_exception_category(self):
        """OCR-Exceptions haben Kategorie 'OCR-Fehler'."""
        exc = OCRProcessingError("doc123", "surya", "Test")
        assert _get_error_category(exc) == "OCR-Fehler"

    def test_document_exception_category(self):
        """Dokument-Exceptions haben Kategorie 'Dokumentfehler'."""
        exc = DocumentNotFoundError("doc123")
        assert _get_error_category(exc) == "Dokumentfehler"

    def test_database_exception_category(self):
        """Datenbank-Exceptions haben Kategorie 'Datenbankfehler'."""
        exc = DatabaseConnectionError("Connection refused")
        assert _get_error_category(exc) == "Datenbankfehler"

    def test_compliance_exception_category(self):
        """Compliance-Exceptions haben Kategorie 'Compliance-Fehler'."""
        exc = GDPRViolationError("consent_missing", "Keine Einwilligung")
        assert _get_error_category(exc) == "Compliance-Fehler"


class TestTranslateValidationError:
    """Tests für _translate_validation_error Funktion."""

    def test_translates_missing(self):
        """'missing' wird übersetzt."""
        result = _translate_validation_error("value_error.missing", "Field required")
        assert "fehlt" in result.lower()

    def test_translates_string_type(self):
        """'string_type' wird übersetzt."""
        result = _translate_validation_error("type_error.string_type", "String required")
        assert "text" in result.lower()

    def test_translates_int_type(self):
        """'int_type' wird übersetzt."""
        result = _translate_validation_error("type_error.int_type", "Integer required")
        assert "ganzzahl" in result.lower()

    def test_returns_original_if_unknown(self):
        """Unbekannte Fehler werden unverändert zurückgegeben."""
        result = _translate_validation_error("unknown_error", "Original message")
        assert result == "Original message"


class TestAblageSystemExceptionHandler:
    """Tests für ablage_system_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Mock Request für Tests."""
        request = Mock(spec=Request)
        request.url.path = "/api/v1/test"
        request.method = "GET"
        request.client = Mock()
        request.client.host = "127.0.0.1"
        # request.state.request_id wird sonst zu einem Mock (Mock(spec)
        # legt das Attribut automatisch an) und ist nicht JSON-serialisierbar
        request.state.request_id = None
        return request

    @pytest.mark.asyncio
    async def test_gpu_oom_returns_503(self, mock_request):
        """GPUOutOfMemoryError gibt 503 zurück."""
        exc = GPUOutOfMemoryError(
            message="GPU out of memory",
            required_gb=12.0,
            available_gb=8.0
        )

        response = await ablage_system_exception_handler(mock_request, exc)

        assert response.status_code == 503
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_document_not_found_returns_404(self, mock_request):
        """DocumentNotFoundError gibt 404 zurück."""
        exc = DocumentNotFoundError("doc123")

        response = await ablage_system_exception_handler(mock_request, exc)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_response_contains_german_message(self, mock_request):
        """Antwort enthält deutsche Meldung."""
        exc = DocumentNotFoundError("doc123")

        response = await ablage_system_exception_handler(mock_request, exc)

        import json
        content = json.loads(response.body.decode())
        assert content["nachricht"] == "Dokument nicht gefunden"

    @pytest.mark.asyncio
    async def test_response_contains_error_code(self, mock_request):
        """Antwort enthält Fehlercode."""
        exc = DocumentNotFoundError("doc123")

        response = await ablage_system_exception_handler(mock_request, exc)

        import json
        content = json.loads(response.body.decode())
        # DocumentNotFoundError nutzt error_code "DOC_003" (siehe app/core/exceptions.py)
        assert content["fehler_code"] == "DOC_003"


class TestHttpExceptionHandler:
    """Tests für http_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Mock Request für Tests."""
        request = Mock(spec=Request)
        request.url.path = "/api/v1/test"
        # Verhindert nicht-serialisierbaren Mock-request_id in der Response
        request.state.request_id = None
        return request

    @pytest.mark.asyncio
    async def test_404_german_translation(self, mock_request):
        """404 wird auf Deutsch übersetzt."""
        exc = HTTPException(status_code=404)

        response = await http_exception_handler(mock_request, exc)

        import json
        content = json.loads(response.body.decode())
        assert content["fehler"] == "Nicht gefunden"

    @pytest.mark.asyncio
    async def test_401_german_translation(self, mock_request):
        """401 wird auf Deutsch übersetzt."""
        exc = HTTPException(status_code=401)

        response = await http_exception_handler(mock_request, exc)

        import json
        content = json.loads(response.body.decode())
        assert content["fehler"] == "Nicht autorisiert"

    @pytest.mark.asyncio
    async def test_uses_detail_if_provided(self, mock_request):
        """Verwendet exc.detail wenn vorhanden."""
        exc = HTTPException(status_code=400, detail="Spezifischer Fehler")

        response = await http_exception_handler(mock_request, exc)

        import json
        content = json.loads(response.body.decode())
        assert content["nachricht"] == "Spezifischer Fehler"

    @pytest.mark.asyncio
    async def test_503_adds_retry_after(self, mock_request):
        """503 fügt Retry-After Header hinzu."""
        exc = HTTPException(status_code=503)

        response = await http_exception_handler(mock_request, exc)

        assert "Retry-After" in response.headers


class TestGenericExceptionHandler:
    """Tests für generic_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Mock Request für Tests."""
        request = Mock(spec=Request)
        request.url.path = "/api/v1/test"
        request.method = "POST"
        # Verhindert nicht-serialisierbaren Mock-request_id in der Response
        request.state.request_id = None
        return request

    @pytest.mark.asyncio
    async def test_returns_500(self, mock_request):
        """Gibt immer 500 zurück."""
        exc = ValueError("Test error")

        response = await generic_exception_handler(mock_request, exc)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_does_not_expose_internal_details(self, mock_request):
        """Gibt keine internen Details preis."""
        exc = ValueError("Internal database password: secret123")

        response = await generic_exception_handler(mock_request, exc)

        import json
        content = json.loads(response.body.decode())
        # Sollte keine internen Details enthalten
        assert "secret123" not in str(content)
        assert "password" not in str(content).lower()

    @pytest.mark.asyncio
    async def test_german_message(self, mock_request):
        """Gibt deutsche Meldung zurück."""
        exc = Exception("Unknown error")

        response = await generic_exception_handler(mock_request, exc)

        import json
        content = json.loads(response.body.decode())
        assert "unerwarteter Fehler" in content["nachricht"]


class TestErrorResponseConsistency:
    """Tests für konsistentes Response-Format."""

    def test_all_responses_have_required_fields(self):
        """Alle Antworten haben Pflichtfelder."""
        required_fields = {"fehler", "nachricht", "status_code", "zeitstempel"}

        response = create_error_response(
            fehler="Test",
            nachricht="Test",
            status_code=400,
        )

        assert required_fields.issubset(response.keys())

    def test_consistent_field_names_german(self):
        """Alle Feldnamen sind auf Deutsch."""
        response = create_error_response(
            fehler="Test",
            nachricht="Test",
            status_code=400,
            fehler_code="E001",
            pfad="/test",
            details={"test": "value"},
            retry_after=60,
        )

        # Keine englischen Feldnamen
        assert "error" not in response
        assert "message" not in response
        assert "timestamp" not in response
        assert "path" not in response
        assert "error_code" not in response

        # Deutsche Feldnamen vorhanden
        assert "fehler" in response
        assert "nachricht" in response
        assert "zeitstempel" in response
        assert "pfad" in response
        assert "fehler_code" in response
