"""Tests fuer ErrorStandardizationMiddleware und den Fehlercode-Katalog.

Prueft:
- Katalog-Integrität (frozen, eindeutige Codes, vollständige Einträge)
- StandardErrorResponse-Schema-Validierung
- Middleware-Verhalten (Correlation-ID, HTTP-Status, Body-Format)
"""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas.error_response import StandardErrorResponse
from app.core.error_catalog import (
    ERROR_CATALOG,
    EXCEPTION_TO_ERROR_CODE,
    ERR_API_002,
    ERR_AUTH_001,
    ERR_DOC_001,
    ErrorDefinition,
    get_error_definition,
)
from app.core.error_middleware import ErrorStandardizationMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Erstellt eine minimale FastAPI-App mit der Middleware fuer Tests."""
    app = FastAPI()
    app.add_middleware(ErrorStandardizationMiddleware)

    @app.get("/test-ok")
    async def test_ok():
        return {"status": "ok"}

    @app.get("/test-not-found")
    async def test_not_found():
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Test nicht gefunden")

    @app.get("/test-forbidden")
    async def test_forbidden():
        from app.core.exceptions import ForbiddenError

        raise ForbiddenError("Zugriff verweigert")

    @app.get("/test-validation")
    async def test_validation():
        from app.core.exceptions import ValidationError

        raise ValidationError("Pflichtfeld fehlt", details={"field": "name"})

    @app.get("/test-gpu-oom")
    async def test_gpu_oom():
        from app.core.exceptions import GPUOutOfMemoryError

        raise GPUOutOfMemoryError("GPU OOM", required_gb=12.0, available_gb=2.5)

    @app.get("/test-generic")
    async def test_generic():
        raise RuntimeError("Unexpected internal error")

    return app


# ---------------------------------------------------------------------------
# TestErrorCatalog
# ---------------------------------------------------------------------------


class TestErrorCatalog:
    def test_error_definition_is_frozen(self):
        """ErrorDefinition muss unveraenderlich sein (frozen dataclass)."""
        with pytest.raises((AttributeError, TypeError)):
            ERR_DOC_001.code = "changed"  # type: ignore[misc]

    def test_error_catalog_is_populated(self):
        """Der Katalog muss nach dem Import befuellt sein."""
        assert len(ERROR_CATALOG) > 0

    def test_error_catalog_contains_doc_001(self):
        assert "ERR-DOC-001" in ERROR_CATALOG

    def test_error_catalog_contains_auth_001(self):
        assert "ERR-AUTH-001" in ERROR_CATALOG

    def test_error_catalog_contains_gpu_errors(self):
        assert "ERR-GPU-001" in ERROR_CATALOG
        assert "ERR-GPU-002" in ERROR_CATALOG

    def test_error_catalog_contains_sys_errors(self):
        assert "ERR-SYS-001" in ERROR_CATALOG
        assert "ERR-SYS-002" in ERROR_CATALOG

    def test_get_error_definition_returns_correct_entry(self):
        defn = get_error_definition("ERR-DOC-001")
        assert defn is not None
        assert defn.http_status == 404
        assert "nicht gefunden" in defn.message_de

    def test_get_error_definition_returns_none_for_unknown(self):
        defn = get_error_definition("ERR-NONEXIST-999")
        assert defn is None

    def test_all_exception_mappings_resolve_to_valid_catalog_entries(self):
        """Alle Exception-Klassen-Mappings muessen auf gueltige Katalog-Eintraege zeigen."""
        for exc_name, code in EXCEPTION_TO_ERROR_CODE.items():
            defn = get_error_definition(code)
            assert defn is not None, (
                f"Fehlender Katalogeintrag fuer Code '{code}' "
                f"(gemappt von Exception '{exc_name}')"
            )

    def test_all_error_codes_are_unique(self):
        codes = [defn.code for defn in ERROR_CATALOG.values()]
        assert len(codes) == len(set(codes)), "Doppelte Fehlercodes im Katalog gefunden"

    def test_err_doc_001_http_status(self):
        defn = get_error_definition("ERR-DOC-001")
        assert defn is not None
        assert defn.http_status == 404

    def test_err_auth_002_http_status(self):
        defn = get_error_definition("ERR-AUTH-002")
        assert defn is not None
        assert defn.http_status == 403

    def test_err_gpu_001_http_status(self):
        defn = get_error_definition("ERR-GPU-001")
        assert defn is not None
        assert defn.http_status == 503

    def test_err_api_002_message_en(self):
        assert ERR_API_002.message_en == "Internal server error"

    def test_err_auth_001_message_de(self):
        assert "fehlgeschlagen" in ERR_AUTH_001.message_de.lower()


# ---------------------------------------------------------------------------
# TestStandardErrorResponse
# ---------------------------------------------------------------------------


class TestStandardErrorResponse:
    def test_minimal_schema_is_valid(self):
        resp = StandardErrorResponse(
            error_code="ERR-DOC-001",
            message="Document not found",
            message_de="Dokument nicht gefunden",
            correlation_id=str(uuid4()),
            timestamp=datetime.now().isoformat(),
        )
        assert resp.error_code == "ERR-DOC-001"
        assert resp.details is None
        assert resp.path is None

    def test_schema_with_optional_details_and_path(self):
        resp = StandardErrorResponse(
            error_code="ERR-API-001",
            message="Bad request",
            message_de="Ungueltiger Request",
            correlation_id=str(uuid4()),
            details={"field": "name", "reason": "required"},
            timestamp=datetime.now().isoformat(),
            path="/api/v1/test",
        )
        assert resp.details == {"field": "name", "reason": "required"}
        assert resp.path == "/api/v1/test"

    def test_schema_correlation_id_preserved(self):
        cid = str(uuid4())
        resp = StandardErrorResponse(
            error_code="ERR-SYS-001",
            message="Internal error",
            message_de="Interner Fehler",
            correlation_id=cid,
            timestamp=datetime.now().isoformat(),
        )
        assert resp.correlation_id == cid


# ---------------------------------------------------------------------------
# TestErrorMiddleware
# ---------------------------------------------------------------------------


class TestErrorMiddleware:
    def test_successful_request_returns_200(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-ok")
        assert resp.status_code == 200

    def test_successful_request_has_correlation_id_header(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-ok")
        assert "X-Correlation-ID" in resp.headers

    def test_not_found_returns_404(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-not-found")
        assert resp.status_code == 404

    def test_not_found_body_contains_required_fields(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-not-found")
        body = resp.json()
        assert "error_code" in body
        assert "correlation_id" in body
        assert "message_de" in body
        assert "timestamp" in body

    def test_not_found_error_code_is_err_doc_001(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-not-found")
        body = resp.json()
        assert body["error_code"] == "ERR-DOC-001"

    def test_forbidden_returns_403(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-forbidden")
        assert resp.status_code == 403

    def test_forbidden_error_code_is_err_auth_002(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-forbidden")
        body = resp.json()
        assert body["error_code"] == "ERR-AUTH-002"

    def test_validation_error_returns_422(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-validation")
        assert resp.status_code == 422

    def test_generic_error_returns_500(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-generic")
        assert resp.status_code == 500

    def test_generic_error_code_is_err_sys_001(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-generic")
        body = resp.json()
        assert body["error_code"] == "ERR-SYS-001"

    def test_generic_error_body_has_correlation_id(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-generic")
        body = resp.json()
        assert "correlation_id" in body

    def test_custom_correlation_id_is_preserved(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        custom_id = str(uuid4())
        resp = client.get("/test-ok", headers={"X-Correlation-ID": custom_id})
        assert resp.headers["X-Correlation-ID"] == custom_id

    def test_error_response_contains_path(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-not-found")
        body = resp.json()
        assert body.get("path") == "/test-not-found"

    def test_error_response_timestamp_is_iso_format(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-generic")
        body = resp.json()
        assert "timestamp" in body
        # Raises ValueError if not ISO format
        datetime.fromisoformat(body["timestamp"])

    def test_error_response_has_german_message(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-not-found")
        body = resp.json()
        assert "message_de" in body
        assert len(body["message_de"]) > 0

    def test_gpu_oom_returns_503(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-gpu-oom")
        assert resp.status_code == 503

    def test_gpu_oom_error_code_is_err_gpu_001(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-gpu-oom")
        body = resp.json()
        assert body["error_code"] == "ERR-GPU-001"

    def test_error_response_has_message_field(self):
        """Englische technische Fehlernachricht muss vorhanden sein."""
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/test-not-found")
        body = resp.json()
        assert "message" in body
        assert len(body["message"]) > 0
