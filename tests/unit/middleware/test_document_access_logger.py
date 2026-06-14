# -*- coding: utf-8 -*-
"""
Unit Tests fuer Document Access Logging Middleware.

Tests fuer:
- DocumentAccessLoggingMiddleware (GoBD-konformes Access Logging)
- extract_document_access_info (Path Pattern Matching)
- Context Variable Management
- IP Adress-Extraktion (inkl. Proxy-Support)
"""

import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.document_access_logger import (
    DocumentAccessLoggingMiddleware,
    extract_document_access_info,
    get_current_document_access,
    current_document_access,
    DOCUMENT_ACCESS_PATTERNS,
)
from app.db.models import DocumentAccessType


class TestExtractDocumentAccessInfo:
    """Tests fuer extract_document_access_info Funktion."""

    def test_view_document_metadata(self):
        """GET /api/v1/documents/{id} wird als VIEW erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}"

        result = extract_document_access_info(path, "GET")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.VIEW.value

    def test_download_document(self):
        """GET /api/v1/documents/{id}/download wird als DOWNLOAD erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/download"

        result = extract_document_access_info(path, "GET")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.DOWNLOAD.value

    def test_preview_document(self):
        """GET /api/v1/documents/{id}/preview wird als PREVIEW erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/preview"

        result = extract_document_access_info(path, "GET")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.PREVIEW.value

    def test_thumbnail_document(self):
        """GET /api/v1/documents/{id}/thumbnail wird als PREVIEW erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/thumbnail"

        result = extract_document_access_info(path, "GET")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.PREVIEW.value

    def test_ocr_access(self):
        """GET /api/v1/documents/{id}/ocr wird als OCR_ACCESS erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/ocr"

        result = extract_document_access_info(path, "GET")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.OCR_ACCESS.value

    def test_text_access(self):
        """GET /api/v1/documents/{id}/text wird als OCR_ACCESS erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/text"

        result = extract_document_access_info(path, "GET")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.OCR_ACCESS.value

    def test_export_post(self):
        """POST /api/v1/documents/{id}/export wird als EXPORT erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/export"

        result = extract_document_access_info(path, "POST")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.EXPORT.value

    def test_export_get_with_format(self):
        """GET /api/v1/documents/{id}/export/pdf wird als EXPORT erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/export/pdf"

        result = extract_document_access_info(path, "GET")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.EXPORT.value

    def test_share_document(self):
        """POST /api/v1/documents/{id}/share wird als SHARE erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/share"

        result = extract_document_access_info(path, "POST")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.SHARE.value

    def test_metadata_update_patch(self):
        """PATCH /api/v1/documents/{id} wird als METADATA_UPDATE erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}"

        result = extract_document_access_info(path, "PATCH")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.METADATA_UPDATE.value

    def test_metadata_update_put(self):
        """PUT /api/v1/documents/{id} wird als METADATA_UPDATE erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}"

        result = extract_document_access_info(path, "PUT")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.METADATA_UPDATE.value

    def test_annotation_create(self):
        """POST /api/v1/documents/{id}/annotations wird als ANNOTATION erkannt."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}/annotations"

        result = extract_document_access_info(path, "POST")

        assert result is not None
        assert result[0] == doc_id
        assert result[1] == DocumentAccessType.ANNOTATION.value

    def test_non_document_path_returns_none(self):
        """Nicht-Dokument-Pfade geben None zurueck."""
        paths = [
            "/api/v1/users/123",
            "/api/v1/companies",
            "/health",
            "/api/v1/documents",  # Liste, keine einzelne ID
            "/api/v1/folders/123/documents",
        ]

        for path in paths:
            result = extract_document_access_info(path, "GET")
            assert result is None, f"Pfad {path} sollte None zurueckgeben"

    def test_wrong_method_returns_none(self):
        """Falsche HTTP-Methode gibt None zurueck."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        # POST auf View-Endpoint (sollte GET sein)
        result = extract_document_access_info(
            f"/api/v1/documents/{doc_id}",
            "POST"
        )
        assert result is None

        # GET auf Share-Endpoint (sollte POST sein)
        result = extract_document_access_info(
            f"/api/v1/documents/{doc_id}/share",
            "GET"
        )
        assert result is None

    def test_invalid_uuid_format_no_match(self):
        """Ungueltige UUID-Formate werden nicht gematcht."""
        invalid_ids = [
            "123",
            "not-a-uuid",
            "12345678901234567890",
            "a1b2c3d4-e5f6-7890",  # Zu kurz
        ]

        for invalid_id in invalid_ids:
            result = extract_document_access_info(
                f"/api/v1/documents/{invalid_id}",
                "GET"
            )
            assert result is None, f"ID {invalid_id} sollte nicht matchen"

    def test_method_case_insensitive(self):
        """HTTP-Methode wird case-insensitive gematcht."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        path = f"/api/v1/documents/{doc_id}"

        for method in ["get", "Get", "GET"]:
            result = extract_document_access_info(path, method)
            assert result is not None, f"Methode {method} sollte matchen"


class TestDocumentAccessLoggingMiddlewareInit:
    """Tests fuer Middleware Initialisierung."""

    def test_init_with_get_db(self):
        """Middleware wird mit get_db Funktion initialisiert."""
        app = Mock()
        get_db = AsyncMock()

        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        assert middleware.app == app
        assert middleware.get_db == get_db

    def test_patterns_loaded(self):
        """Dokument-Access-Patterns sind geladen."""
        assert len(DOCUMENT_ACCESS_PATTERNS) > 0

        # Mindestens diese sollten vorhanden sein
        pattern_methods = [p[1] for p in DOCUMENT_ACCESS_PATTERNS]
        assert "GET" in pattern_methods
        assert "POST" in pattern_methods
        assert "PATCH" in pattern_methods


class TestDocumentAccessLoggingMiddlewareDispatch:
    """Tests fuer Middleware Dispatch."""

    @pytest.mark.asyncio
    async def test_non_document_path_bypasses_logging(self):
        """Nicht-Dokument-Pfade werden ohne Logging durchgereicht."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        request = Mock(spec=Request)
        request.url = Mock(path="/api/v1/users")
        request.method = "GET"

        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200
        # get_db sollte nicht aufgerufen worden sein
        get_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_request_logged(self):
        """Erfolgreicher Dokumentzugriff wird geloggt."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        company_id = uuid.uuid4()
        user_id = uuid.uuid4()

        request = Mock(spec=Request)
        request.url = Mock(path=f"/api/v1/documents/{doc_id}")
        request.method = "GET"
        request.headers = {"User-Agent": "TestBrowser/1.0"}
        request.client = Mock(host="192.168.1.100")
        request.state = Mock()
        request.state.user_id = user_id
        request.state.company_id = company_id

        response = Response(status_code=200)
        response.headers["Content-Length"] = "12345"
        call_next = AsyncMock(return_value=response)

        with patch('app.middleware.document_access_logger.DocumentAccessLoggingMiddleware._log_access') as mock_log:
            mock_log.return_value = None
            result = await middleware.dispatch(request, call_next)

        assert result.status_code == 200
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args.kwargs['document_id'] == doc_id
        assert call_args.kwargs['access_type'] == DocumentAccessType.VIEW.value
        assert call_args.kwargs['success'] is True

    @pytest.mark.asyncio
    async def test_failed_request_logged(self):
        """Fehlgeschlagener Dokumentzugriff wird geloggt."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        company_id = uuid.uuid4()

        request = Mock(spec=Request)
        request.url = Mock(path=f"/api/v1/documents/{doc_id}")
        request.method = "GET"
        request.headers = {}
        request.client = Mock(host="192.168.1.100")
        request.state = Mock()
        request.state.user_id = None
        request.state.company_id = company_id

        response = Response(status_code=404)
        call_next = AsyncMock(return_value=response)

        with patch('app.middleware.document_access_logger.DocumentAccessLoggingMiddleware._log_access') as mock_log:
            mock_log.return_value = None
            result = await middleware.dispatch(request, call_next)

        assert result.status_code == 404
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args.kwargs['success'] is False
        assert "HTTP 404" in call_args.kwargs['error_message']

    @pytest.mark.asyncio
    async def test_exception_logged_and_reraised(self):
        """Exceptions werden geloggt und weitergegeben."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        company_id = uuid.uuid4()

        request = Mock(spec=Request)
        request.url = Mock(path=f"/api/v1/documents/{doc_id}")
        request.method = "GET"
        request.headers = {}
        request.client = Mock(host="192.168.1.100")
        request.state = Mock()
        request.state.user_id = None
        request.state.company_id = company_id

        call_next = AsyncMock(side_effect=ValueError("Test Error"))

        with patch('app.middleware.document_access_logger.DocumentAccessLoggingMiddleware._log_access') as mock_log:
            mock_log.return_value = None
            with pytest.raises(ValueError, match="Test Error"):
                await middleware.dispatch(request, call_next)

        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args.kwargs['success'] is False
        # Quelle nutzt safe_error_detail -> loggt nur den Exception-TYP, nicht
        # die Roh-Message ("Test Error" waere ein PII-Leak, CLAUDE.md Regel 1).
        error_message = call_args.kwargs['error_message']
        assert "ValueError" in error_message
        assert "fehlgeschlagen" in error_message
        assert "Test Error" not in error_message

    @pytest.mark.asyncio
    async def test_context_cleared_after_request(self):
        """Context wird nach Request zurueckgesetzt."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        company_id = uuid.uuid4()

        request = Mock(spec=Request)
        request.url = Mock(path=f"/api/v1/documents/{doc_id}")
        request.method = "GET"
        request.headers = {}
        request.client = Mock(host="192.168.1.100")
        request.state = Mock()
        request.state.user_id = None
        request.state.company_id = company_id

        call_next = AsyncMock(return_value=Response(status_code=200))

        with patch('app.middleware.document_access_logger.DocumentAccessLoggingMiddleware._log_access'):
            await middleware.dispatch(request, call_next)

        # Context sollte zurueckgesetzt sein
        assert current_document_access.get() is None

    @pytest.mark.asyncio
    async def test_request_id_from_header(self):
        """X-Request-ID aus Header wird verwendet."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        company_id = uuid.uuid4()
        custom_request_id = "custom-request-123"

        request = Mock(spec=Request)
        request.url = Mock(path=f"/api/v1/documents/{doc_id}")
        request.method = "GET"
        request.headers = {"X-Request-ID": custom_request_id}
        request.client = Mock(host="192.168.1.100")
        request.state = Mock()
        request.state.user_id = None
        request.state.company_id = company_id

        call_next = AsyncMock(return_value=Response(status_code=200))

        with patch('app.middleware.document_access_logger.DocumentAccessLoggingMiddleware._log_access') as mock_log:
            mock_log.return_value = None
            await middleware.dispatch(request, call_next)

        call_args = mock_log.call_args
        assert call_args.kwargs['request_id'] == custom_request_id


class TestClientIPExtraction:
    """Tests fuer Client-IP Extraktion."""

    def test_x_forwarded_for_first_ip(self):
        """X-Forwarded-For - erste IP wird verwendet."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        request = Mock()
        request.headers = {
            "X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"
        }
        request.client = Mock(host="127.0.0.1")

        ip = middleware._get_client_ip(request)

        assert ip == "203.0.113.195"

    def test_x_real_ip_used(self):
        """X-Real-IP wird verwendet wenn X-Forwarded-For fehlt."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        request = Mock()
        request.headers = {"X-Real-IP": "203.0.113.50"}
        request.client = Mock(host="127.0.0.1")

        ip = middleware._get_client_ip(request)

        assert ip == "203.0.113.50"

    def test_direct_client_ip_fallback(self):
        """Direkte Client-IP als Fallback."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        request = Mock()
        request.headers = {}
        request.client = Mock(host="192.168.1.100")

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.100"

    def test_no_client_returns_none(self):
        """None wenn kein Client vorhanden."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        request = Mock()
        request.headers = {}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip is None

    def test_whitespace_trimmed(self):
        """Whitespace wird entfernt."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        request = Mock()
        request.headers = {"X-Real-IP": "  203.0.113.50  "}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "203.0.113.50"


class TestContentLengthExtraction:
    """Tests fuer Content-Length Extraktion."""

    def test_valid_content_length(self):
        """Gueltige Content-Length wird extrahiert."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        response = Response(status_code=200)
        response.headers["Content-Length"] = "12345"

        length = middleware._get_content_length(response)

        assert length == 12345

    def test_no_content_length_returns_none(self):
        """None oder 0 wenn Content-Length fehlt."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        response = Response(status_code=200)

        length = middleware._get_content_length(response)

        # Starlette Response gibt 0 zurueck wenn kein Content
        assert length is None or length == 0

    def test_invalid_content_length_returns_none(self):
        """None bei ungueltigem Content-Length."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        response = Response(status_code=200)
        response.headers["Content-Length"] = "invalid"

        length = middleware._get_content_length(response)

        assert length is None


class TestContextVariable:
    """Tests fuer Context Variable Management."""

    def test_default_value_is_none(self):
        """Default-Wert ist None."""
        current_document_access.set(None)
        assert current_document_access.get() is None

    def test_can_set_and_get_value(self):
        """Wert kann gesetzt und gelesen werden."""
        test_data = {
            "document_id": "test-123",
            "access_type": "VIEW",
        }

        current_document_access.set(test_data)

        assert current_document_access.get() == test_data

        # Cleanup
        current_document_access.set(None)

    def test_get_current_document_access_helper(self):
        """Helper-Funktion gibt Context-Wert zurueck."""
        test_data = {
            "document_id": "test-456",
            "access_type": "DOWNLOAD",
        }

        current_document_access.set(test_data)

        result = get_current_document_access()

        assert result == test_data

        # Cleanup
        current_document_access.set(None)

    def test_get_current_document_access_returns_none_when_empty(self):
        """Helper gibt None zurueck wenn leer."""
        current_document_access.set(None)

        result = get_current_document_access()

        assert result is None


class TestLogAccessMethod:
    """Tests fuer _log_access Methode."""

    @pytest.mark.asyncio
    async def test_skips_logging_without_company_id(self):
        """Logging wird uebersprungen ohne Company-ID."""
        app = Mock()
        get_db = AsyncMock()
        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        request = Mock()
        request.state = Mock()
        request.state.user_id = None
        request.state.company_id = None

        with patch('app.middleware.document_access_logger.logger') as mock_logger:
            await middleware._log_access(
                request=request,
                document_id="test-123",
                access_type="VIEW",
                request_id="req-123",
                ip_address="192.168.1.1",
                user_agent="Test",
                success=True,
            )

        mock_logger.warning.assert_called_once()
        assert "document_access_log_skipped_no_company" in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_calls_document_access_service(self):
        """Ruft DocumentAccessService auf."""
        app = Mock()

        # Mock database session als async context manager
        mock_db = AsyncMock()

        async def mock_get_db():
            yield mock_db

        # Wir muessen einen async context manager simulieren
        class MockDBContextManager:
            async def __aenter__(self):
                return mock_db

            async def __aexit__(self, *args):
                pass

        get_db = MagicMock(return_value=MockDBContextManager())

        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        company_id = uuid.uuid4()
        user_id = uuid.uuid4()
        doc_id = str(uuid.uuid4())

        request = Mock()
        request.state = Mock()
        request.state.user_id = user_id
        request.state.company_id = company_id

        # Patch the import inside the method
        with patch('app.services.document_access_service.document_access_service') as mock_service:
            mock_service.log_access = AsyncMock()
            await middleware._log_access(
                request=request,
                document_id=doc_id,
                access_type="VIEW",
                request_id="req-123",
                ip_address="192.168.1.1",
                user_agent="TestBrowser",
                success=True,
                bytes_transferred=1024,
            )

            mock_service.log_access.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_logging_errors_gracefully(self):
        """Logging-Fehler werden abgefangen."""
        app = Mock()

        # Mock database session that raises error
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(side_effect=Exception("DB Error"))
        get_db = MagicMock(return_value=mock_db)

        middleware = DocumentAccessLoggingMiddleware(app, get_db)

        company_id = uuid.uuid4()

        request = Mock()
        request.state = Mock()
        request.state.user_id = None
        request.state.company_id = company_id

        with patch('app.middleware.document_access_logger.logger') as mock_logger:
            # Should not raise, just log error
            await middleware._log_access(
                request=request,
                document_id="test-123",
                access_type="VIEW",
                request_id="req-123",
                ip_address="192.168.1.1",
                user_agent="Test",
                success=True,
            )

        mock_logger.error.assert_called_once()


class TestGoBDCompliance:
    """Tests fuer GoBD-Compliance Aspekte."""

    def test_all_access_types_have_patterns(self):
        """Alle wichtigen Access-Types haben Patterns."""
        access_types = [p[2] for p in DOCUMENT_ACCESS_PATTERNS]

        # Diese muessen fuer GoBD vorhanden sein
        required_types = [
            DocumentAccessType.VIEW.value,
            DocumentAccessType.DOWNLOAD.value,
            DocumentAccessType.EXPORT.value,
            DocumentAccessType.METADATA_UPDATE.value,
        ]

        for required in required_types:
            assert required in access_types, f"{required} fehlt in Patterns"

    def test_patterns_use_uuid_format(self):
        """Patterns verwenden UUID-Format fuer Document-IDs."""
        # UUID-Pattern: 8-4-4-4-12 hex digits
        uuid_regex = r'\[a-f0-9-\]\{36\}'

        for pattern, method, access_type in DOCUMENT_ACCESS_PATTERNS:
            pattern_str = pattern.pattern
            # Jedes Pattern sollte UUID-Format matchen
            assert '([a-f0-9-]{36})' in pattern_str, \
                f"Pattern fuer {access_type} verwendet kein UUID-Format"

    def test_metadata_update_tracked_separately(self):
        """Metadaten-Updates werden separat getrackt (GoBD-relevant)."""
        # PATCH und PUT sollten METADATA_UPDATE sein, nicht VIEW
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        for method in ["PATCH", "PUT"]:
            result = extract_document_access_info(
                f"/api/v1/documents/{doc_id}",
                method
            )
            assert result is not None
            assert result[1] == DocumentAccessType.METADATA_UPDATE.value

    def test_delete_not_allowed(self):
        """DELETE wird nicht als Access-Type erkannt (GoBD: keine Loeschung)."""
        doc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        result = extract_document_access_info(
            f"/api/v1/documents/{doc_id}",
            "DELETE"
        )

        # DELETE sollte nicht gematcht werden
        assert result is None


class TestMiddlewareExports:
    """Tests fuer Middleware Exports."""

    def test_middleware_exported(self):
        """DocumentAccessLoggingMiddleware ist exportiert."""
        from app.middleware.document_access_logger import DocumentAccessLoggingMiddleware
        assert DocumentAccessLoggingMiddleware is not None

    def test_extract_function_exported(self):
        """extract_document_access_info ist exportiert."""
        from app.middleware.document_access_logger import extract_document_access_info
        assert extract_document_access_info is not None

    def test_context_variable_exported(self):
        """current_document_access ist exportiert."""
        from app.middleware.document_access_logger import current_document_access
        assert current_document_access is not None

    def test_helper_function_exported(self):
        """get_current_document_access ist exportiert."""
        from app.middleware.document_access_logger import get_current_document_access
        assert get_current_document_access is not None

    def test_patterns_exported(self):
        """DOCUMENT_ACCESS_PATTERNS ist exportiert."""
        from app.middleware.document_access_logger import DOCUMENT_ACCESS_PATTERNS
        assert DOCUMENT_ACCESS_PATTERNS is not None
        assert len(DOCUMENT_ACCESS_PATTERNS) > 0
