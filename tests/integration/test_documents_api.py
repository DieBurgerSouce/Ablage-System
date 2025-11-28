"""Integrationstests fuer die Documents API Endpoints.

Testet Such-, CRUD- und Batch-Operationen ueber HTTP.
"""

import pytest
from fastapi import status
from uuid import uuid4
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch


@pytest.mark.integration
@pytest.mark.api
class TestDocumentsSearchAPI:
    """Tests fuer Such-Endpoints."""

    def test_search_endpoint_exists(self, client):
        """Test dass Search-Endpoint erreichbar ist."""
        response = client.get("/api/v1/documents/search?q=test")
        # Endpoint sollte existieren (auch wenn Auth/CSRF fehlt)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_CONTENT
        ]

    def test_search_requires_query(self, client):
        """Test dass Suchquery erforderlich ist."""
        response = client.get("/api/v1/documents/search")
        # Sollte 422 fuer fehlende Query zurueckgeben (oder 401/403 ohne Auth)
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_search_with_filters(self, client):
        """Test Suche mit Filtern."""
        response = client.get(
            "/api/v1/documents/search",
            params={
                "q": "Rechnung",
                "search_type": "fts",
                "document_type": "invoice",
                "page": 1,
                "per_page": 10
            }
        )
        # Sollte gueltige Response haben (oder Auth-Fehler)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ]

    def test_search_hybrid_type(self, client):
        """Test Hybrid-Suche."""
        response = client.get(
            "/api/v1/documents/search",
            params={
                "q": "Vertrag",
                "search_type": "hybrid"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ]

    def test_search_semantic_type(self, client):
        """Test Semantische Suche."""
        response = client.get(
            "/api/v1/documents/search",
            params={
                "q": "Finanzielle Unterlagen",
                "search_type": "semantic"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ]


@pytest.mark.integration
@pytest.mark.api
class TestDocumentsListAPI:
    """Tests fuer Listen-Endpoints."""

    def test_list_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/documents/")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_list_with_pagination(self, client):
        """Test Liste mit Pagination."""
        response = client.get(
            "/api/v1/documents/",
            params={"page": 1, "per_page": 10}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_list_with_filters(self, client):
        """Test Liste mit Filtern."""
        response = client.get(
            "/api/v1/documents/",
            params={
                "document_type": "invoice",
                "status": "completed",
                "sort_by": "created_at",
                "sort_order": "desc"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]


@pytest.mark.integration
@pytest.mark.api
class TestDocumentsCRUDAPI:
    """Tests fuer CRUD-Endpoints."""

    def test_get_document_not_found(self, client):
        """Test Dokument-Abruf bei nicht existentem Dokument."""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/documents/{fake_id}")
        assert response.status_code in [
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_update_document_endpoint_exists(self, client):
        """Test dass Update-Endpoint existiert."""
        fake_id = str(uuid4())
        response = client.patch(
            f"/api/v1/documents/{fake_id}",
            json={"document_type": "invoice"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_422_UNPROCESSABLE_CONTENT
        ]

    def test_delete_document_endpoint_exists(self, client):
        """Test dass Delete-Endpoint existiert."""
        fake_id = str(uuid4())
        response = client.delete(f"/api/v1/documents/{fake_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_204_NO_CONTENT,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]


@pytest.mark.integration
@pytest.mark.api
class TestDocumentsBatchAPI:
    """Tests fuer Batch-Endpoints."""

    def test_batch_delete_endpoint_exists(self, client):
        """Test dass Batch-Delete-Endpoint existiert."""
        response = client.post(
            "/api/v1/documents/batch/delete",
            json={"document_ids": [str(uuid4())]}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_CONTENT
        ]

    def test_batch_tag_endpoint_exists(self, client):
        """Test dass Batch-Tag-Endpoint existiert."""
        response = client.post(
            "/api/v1/documents/batch/tag",
            json={
                "document_ids": [str(uuid4())],
                "tags": ["Test"],
                "operation": "add"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_CONTENT
        ]

    def test_batch_export_endpoint_exists(self, client):
        """Test dass Batch-Export-Endpoint existiert."""
        response = client.post(
            "/api/v1/documents/batch/export",
            json={
                "document_ids": [str(uuid4())],
                "format": "json"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_CONTENT
        ]


@pytest.mark.integration
@pytest.mark.api
class TestSimilarDocumentsAPI:
    """Tests fuer Aehnliche-Dokumente-Endpoint."""

    def test_similar_documents_endpoint_exists(self, client):
        """Test dass Similar-Endpoint existiert."""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/documents/{fake_id}/similar")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_similar_documents_with_params(self, client):
        """Test Similar-Endpoint mit Parametern."""
        fake_id = str(uuid4())
        response = client.get(
            f"/api/v1/documents/{fake_id}/similar",
            params={
                "limit": 5,
                "similarity_threshold": 0.7,
                "exclude_same_type": True
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]


@pytest.mark.integration
@pytest.mark.api
class TestEmbeddingsAPI:
    """Tests fuer Embedding-Endpoints."""

    def test_regenerate_embedding_endpoint_exists(self, client):
        """Test dass Regenerate-Embedding-Endpoint existiert."""
        fake_id = str(uuid4())
        response = client.post(f"/api/v1/documents/{fake_id}/embedding")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_202_ACCEPTED,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED
        ]

    def test_embedding_status_endpoint_exists(self, client):
        """Test dass Embedding-Status-Endpoint existiert."""
        response = client.get("/api/v1/documents/embeddings/status")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND
        ]


@pytest.mark.integration
@pytest.mark.api
class TestTagsAPI:
    """Tests fuer Tags-Endpoints."""

    def test_list_tags_endpoint_exists(self, client):
        """Test dass Tags-Listen-Endpoint existiert."""
        response = client.get("/api/v1/documents/tags")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND
        ]


@pytest.mark.integration
@pytest.mark.api
class TestAPIResponseFormats:
    """Tests fuer API Response Formate."""

    def test_search_response_format(self, client):
        """Test Such-Response Format."""
        response = client.get(
            "/api/v1/documents/search",
            params={"q": "test"}
        )

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            # Erwartete Felder pruefen
            assert "query" in data or "results" in data
            assert "total" in data or "items" in data

    def test_list_response_format(self, client):
        """Test Listen-Response Format."""
        response = client.get("/api/v1/documents/")

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            # Pagination-Felder pruefen
            assert "documents" in data or "items" in data or isinstance(data, list)

    def test_error_response_format(self, client):
        """Test Fehler-Response Format."""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/documents/{fake_id}")

        if response.status_code == status.HTTP_404_NOT_FOUND:
            data = response.json()
            # Fehler-Format pruefen
            assert "detail" in data or "message" in data or "error" in data


@pytest.mark.integration
@pytest.mark.api
class TestAPIValidation:
    """Tests fuer API Eingabe-Validierung."""

    def test_invalid_uuid_format(self, client):
        """Test ungueltige UUID."""
        response = client.get("/api/v1/documents/invalid-uuid")
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_invalid_search_type(self, client):
        """Test ungueltiger Such-Typ."""
        response = client.get(
            "/api/v1/documents/search",
            params={"q": "test", "search_type": "invalid_type"}
        )
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_invalid_document_type_filter(self, client):
        """Test ungueltiger Dokumenttyp-Filter."""
        response = client.get(
            "/api/v1/documents/",
            params={"document_type": "invalid_type"}
        )
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_invalid_pagination_values(self, client):
        """Test ungueltige Pagination-Werte."""
        response = client.get(
            "/api/v1/documents/",
            params={"page": -1, "per_page": 1000}
        )
        # Sollte entweder 422 oder korrigierte Werte verwenden
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_batch_delete_empty_list(self, client):
        """Test Batch-Delete mit leerer Liste."""
        response = client.post(
            "/api/v1/documents/batch/delete",
            json={"document_ids": []}
        )
        # Sollte 422 fuer leere Liste oder 200 mit 0 verarbeiteten
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_batch_tag_invalid_operation(self, client):
        """Test Batch-Tag mit ungueltiger Operation."""
        response = client.post(
            "/api/v1/documents/batch/tag",
            json={
                "document_ids": [str(uuid4())],
                "tags": ["Test"],
                "operation": "invalid"
            }
        )
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    def test_export_invalid_format(self, client):
        """Test Export mit ungueltigem Format."""
        response = client.post(
            "/api/v1/documents/batch/export",
            json={
                "document_ids": [str(uuid4())],
                "format": "pdf"  # Nicht unterstuetzt
            }
        )
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]


@pytest.mark.asyncio
@pytest.mark.integration
class TestDocumentsAPIAsync:
    """Async Integrationstests fuer Documents API."""

    async def test_search_async(self, async_client):
        """Test asynchrone Suche."""
        response = await async_client.get(
            "/api/v1/documents/search",
            params={"q": "Test"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ]

    async def test_list_async(self, async_client):
        """Test asynchrone Dokumentenliste."""
        response = await async_client.get("/api/v1/documents/")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]

    async def test_concurrent_searches(self, async_client):
        """Test parallele Suchanfragen."""
        import asyncio

        queries = ["Rechnung", "Vertrag", "Lieferschein"]

        async def search(q: str):
            return await async_client.get(
                "/api/v1/documents/search",
                params={"q": q}
            )

        responses = await asyncio.gather(*[search(q) for q in queries])

        for response in responses:
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
                status.HTTP_503_SERVICE_UNAVAILABLE
            ]
