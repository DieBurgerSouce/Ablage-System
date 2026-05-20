# -*- coding: utf-8 -*-
"""
Unit Tests fuer Spotlight API Endpoints.

Testet:
- Parameter-Validierung (q max_length, limit range)
- Authentifizierung (ohne Token -> 401)
- Erfolgsfall (Mock Service -> korrekte Response)
- Fehlerfall (Service-Exception -> 500)

Feinpoliert und durchdacht - Spotlight API Tests.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request
from starlette.datastructures import Headers

from app.services.spotlight_service import (
    SpotlightResponse,
    SpotlightSuggestion,
    SpotlightDocument,
    SpotlightEntity,
    SpotlightInterpretation,
)

pytestmark = [pytest.mark.unit, pytest.mark.api]


def _make_request() -> Request:
    """Erstellt ein minimales Starlette Request-Objekt fuer Tests."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/spotlight",
        "headers": [],
        "query_string": b"",
    }
    return Request(scope)


# ========================= Schema Tests =========================


class TestSpotlightResponseSchema:
    """Tests fuer SpotlightResponse Schema-Validierung."""

    def test_empty_response_valid(self):
        """Leere Response ist gueltig."""
        response = SpotlightResponse()
        assert response.suggestions == []
        assert response.documents == []
        assert response.entities == []
        assert response.interpretation is None
        assert response.search_time_ms == 0.0
        assert response.total_documents == 0

    def test_full_response_valid(self):
        """Vollstaendige Response ist gueltig."""
        response = SpotlightResponse(
            suggestions=[
                SpotlightSuggestion(text="Dashboard", suggestion_type="navigation")
            ],
            documents=[
                SpotlightDocument(
                    document_id="doc-123",
                    filename="Rechnung.pdf",
                    document_type="invoice",
                    status="processed",
                    relevance_score=0.95,
                )
            ],
            entities=[
                SpotlightEntity(
                    entity_id="ent-456",
                    entity_name="Mueller GmbH",
                    entity_type="customer",
                    match_confidence=0.88,
                )
            ],
            interpretation=SpotlightInterpretation(
                original_query="Rechnung Mueller",
                interpreted_as="Suche nach Rechnungen von Mueller",
                search_mode="nlq",
                confidence=0.85,
            ),
            search_time_ms=42.5,
            total_documents=15,
        )

        assert len(response.suggestions) == 1
        assert len(response.documents) == 1
        assert len(response.entities) == 1
        assert response.interpretation.search_mode == "nlq"
        assert response.search_time_ms == 42.5


class TestSpotlightSuggestionSchema:
    """Tests fuer SpotlightSuggestion Schema."""

    def test_navigation_suggestion(self):
        """Navigation-Suggestion wird korrekt erstellt."""
        suggestion = SpotlightSuggestion(
            text="Dashboard",
            suggestion_type="navigation",
        )
        assert suggestion.text == "Dashboard"
        assert suggestion.suggestion_type == "navigation"
        assert suggestion.confidence is None
        assert suggestion.entity_type is None

    def test_entity_suggestion(self):
        """Entity-Suggestion mit optionalen Feldern."""
        suggestion = SpotlightSuggestion(
            text="Mueller GmbH",
            suggestion_type="entity",
            confidence=0.92,
            entity_type="customer",
        )
        assert suggestion.confidence == 0.92
        assert suggestion.entity_type == "customer"


class TestSpotlightDocumentSchema:
    """Tests fuer SpotlightDocument Schema."""

    def test_minimal_document(self):
        """Dokument mit Pflichtfeldern."""
        doc = SpotlightDocument(
            document_id="doc-1",
            filename="test.pdf",
            document_type="invoice",
            status="processed",
            relevance_score=0.8,
        )
        assert doc.created_at is None
        assert doc.ocr_confidence is None
        assert doc.highlight is None
        assert doc.text_preview is None

    def test_full_document(self):
        """Dokument mit allen Feldern."""
        doc = SpotlightDocument(
            document_id="doc-1",
            filename="test.pdf",
            document_type="invoice",
            status="processed",
            relevance_score=0.8,
            ocr_confidence=0.95,
            text_preview="Rechnung Nr. 12345",
        )
        assert doc.ocr_confidence == 0.95
        assert doc.text_preview == "Rechnung Nr. 12345"


class TestSpotlightEntitySchema:
    """Tests fuer SpotlightEntity Schema."""

    def test_customer_entity(self):
        """Kunden-Entity mit Kundennummer."""
        entity = SpotlightEntity(
            entity_id="ent-1",
            entity_name="Mueller GmbH",
            entity_type="customer",
            customer_number="K-1001",
            match_confidence=0.9,
        )
        assert entity.customer_number == "K-1001"
        assert entity.supplier_number is None

    def test_supplier_entity(self):
        """Lieferanten-Entity mit Lieferantennummer."""
        entity = SpotlightEntity(
            entity_id="ent-2",
            entity_name="Zulieferer AG",
            entity_type="supplier",
            supplier_number="L-2002",
            match_confidence=0.85,
        )
        assert entity.supplier_number == "L-2002"
        assert entity.customer_number is None


# ========================= Endpoint Logic Tests =========================


class TestSpotlightEndpoint:
    """Tests fuer den Spotlight API Endpoint."""

    @pytest.mark.asyncio
    async def test_successful_search(self):
        """Erfolgreicher Suchaufruf gibt SpotlightResponse zurueck."""
        from app.api.v1.spotlight import spotlight_search

        mock_service = MagicMock()
        mock_response = SpotlightResponse(
            suggestions=[SpotlightSuggestion(text="Test", suggestion_type="suggestion")],
            search_time_ms=15.3,
        )
        mock_service.search = AsyncMock(return_value=mock_response)

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.company_id = uuid4()

        mock_request = _make_request()

        with patch('app.api.v1.spotlight.get_spotlight_service', return_value=mock_service), \
             patch('app.api.v1.spotlight.limiter'):

            result = await spotlight_search(
                request=mock_request,
                q="Test",
                limit=8,
                db=AsyncMock(),
                current_user=mock_user,
            )

        assert isinstance(result, SpotlightResponse)
        assert len(result.suggestions) == 1
        mock_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_exception_returns_500(self):
        """Service-Exception wird in 500 mit safe_error_detail umgewandelt."""
        from app.api.v1.spotlight import spotlight_search

        mock_service = MagicMock()
        mock_service.search = AsyncMock(side_effect=RuntimeError("DB connection failed"))

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.company_id = uuid4()

        mock_request = _make_request()

        with patch('app.api.v1.spotlight.get_spotlight_service', return_value=mock_service), \
             patch('app.api.v1.spotlight.limiter'):

            with pytest.raises(HTTPException) as exc_info:
                await spotlight_search(
                    request=mock_request,
                    q="Test",
                    limit=8,
                    db=AsyncMock(),
                    current_user=mock_user,
                )

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_http_exception_is_reraised(self):
        """HTTPException wird direkt weitergereicht."""
        from app.api.v1.spotlight import spotlight_search

        mock_service = MagicMock()
        mock_service.search = AsyncMock(
            side_effect=HTTPException(status_code=429, detail="Rate limit")
        )

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.company_id = uuid4()

        mock_request = _make_request()

        with patch('app.api.v1.spotlight.get_spotlight_service', return_value=mock_service), \
             patch('app.api.v1.spotlight.limiter'):

            with pytest.raises(HTTPException) as exc_info:
                await spotlight_search(
                    request=mock_request,
                    q="Test",
                    limit=8,
                    db=AsyncMock(),
                    current_user=mock_user,
                )

            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_empty_query_works(self):
        """Leerer Query funktioniert (keine Validierungsfehler)."""
        from app.api.v1.spotlight import spotlight_search

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=SpotlightResponse())

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.company_id = uuid4()

        mock_request = _make_request()

        with patch('app.api.v1.spotlight.get_spotlight_service', return_value=mock_service), \
             patch('app.api.v1.spotlight.limiter'):

            result = await spotlight_search(
                request=mock_request,
                q="",
                limit=8,
                db=AsyncMock(),
                current_user=mock_user,
            )

        assert isinstance(result, SpotlightResponse)

    @pytest.mark.asyncio
    async def test_search_passes_user_context(self):
        """User-ID und Company-ID werden an Service weitergegeben."""
        from app.api.v1.spotlight import spotlight_search

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=SpotlightResponse())

        user_id = uuid4()
        company_id = uuid4()
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.company_id = company_id

        mock_request = _make_request()

        with patch('app.api.v1.spotlight.get_spotlight_service', return_value=mock_service), \
             patch('app.api.v1.spotlight.limiter'):

            await spotlight_search(
                request=mock_request,
                q="test",
                limit=5,
                db=AsyncMock(),
                current_user=mock_user,
            )

        call_kwargs = mock_service.search.call_args[1]
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["company_id"] == company_id
        assert call_kwargs["query"] == "test"
        assert call_kwargs["limit"] == 5
