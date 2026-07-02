# -*- coding: utf-8 -*-
"""Unit-Tests fuer W2.1: Search-Kaltstart-Degradation.

Testet das Timeout-Handling im Such-Endpoint (GET /api/v1/documents/search/):
Beim ersten HYBRID/SEMANTIC-Aufruf nach einem Backend-Recreate laedt das
Embedding-Modell lazy (>30s auf CPU) und laeuft in den serverseitigen
30s-Timeout. Statt hart mit 504 abzubrechen, degradiert der Endpoint einmalig
auf reine Volltextsuche (FTS) und markiert die Antwort mit ``degraded=True``.

Feinpoliert und durchdacht - Cold-Start-Degradation.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

from app.api.v1.documents import search_documents
from app.db.schemas import SearchResponse, SearchType, SortField, SortOrder

pytestmark = [pytest.mark.unit, pytest.mark.api]


def _fts_response() -> SearchResponse:
    """Baut eine minimale FTS-SearchResponse (degraded ist per Default False)."""
    return SearchResponse(
        query="Rechnung",
        search_type=SearchType.FTS,
        total=0,
        page=1,
        per_page=20,
        total_pages=0,
        results=[],
        took_ms=3,
        filters_applied={},
    )


async def _call_search(service_mock: Mock, search_type: SearchType) -> SearchResponse:
    """Ruft die Endpoint-Funktion direkt auf (umgeht FastAPI-Dependencies)."""
    request = MagicMock()
    request.headers.get.return_value = None
    request.client = None

    current_user = Mock(id=uuid4(), is_active=True)
    company = Mock(id=uuid4())
    db = AsyncMock()

    with patch("app.api.v1.documents.get_search_service", return_value=service_mock), \
         patch("app.services.search_analytics_service.get_search_analytics_service") as m_analytics, \
         patch("app.api.v1.search.save_search_to_history", new=AsyncMock()):
        m_analytics.return_value.log_search = AsyncMock(return_value=uuid4())
        return await search_documents(
            request=request,
            q="Rechnung",
            search_type=search_type,
            page=1,
            per_page=20,
            document_type=None,
            status=None,
            date_from=None,
            date_to=None,
            confidence_min=None,
            has_embedding=None,
            tags=None,
            sort_by=SortField.RELEVANCE,
            sort_order=SortOrder.DESC,
            highlight=True,
            similarity_threshold=0.5,
            use_synonyms=False,
            session_id=None,
            current_user=current_user,
            company=company,
            db=db,
        )


@pytest.mark.asyncio
async def test_hybrid_timeout_degrades_to_fts():
    """HYBRID-Timeout -> einmalige Degradation auf FTS + degraded-Flag."""
    service = Mock()
    service.search = AsyncMock(side_effect=[asyncio.TimeoutError(), _fts_response()])

    result = await _call_search(service, SearchType.HYBRID)

    assert result.degraded is True
    assert result.search_type == SearchType.FTS
    # Zwei Aufrufe: erst HYBRID (Timeout), dann FTS-Fallback
    assert service.search.await_count == 2
    first_kwargs = service.search.await_args_list[0].kwargs
    second_kwargs = service.search.await_args_list[1].kwargs
    assert first_kwargs["search_type"] == SearchType.HYBRID
    assert second_kwargs["search_type"] == SearchType.FTS


@pytest.mark.asyncio
async def test_semantic_timeout_degrades_to_fts():
    """SEMANTIC-Timeout -> ebenfalls FTS-Degradation."""
    service = Mock()
    service.search = AsyncMock(side_effect=[asyncio.TimeoutError(), _fts_response()])

    result = await _call_search(service, SearchType.SEMANTIC)

    assert result.degraded is True
    assert service.search.await_count == 2


@pytest.mark.asyncio
async def test_fts_timeout_raises_504():
    """Reine FTS-Suche kann nicht weiter degradiert werden -> 504."""
    from fastapi import HTTPException

    service = Mock()
    service.search = AsyncMock(side_effect=asyncio.TimeoutError())

    with pytest.raises(HTTPException) as exc_info:
        await _call_search(service, SearchType.FTS)

    assert exc_info.value.status_code == 504
    # Kein zweiter (Fallback-)Aufruf bei bereits reiner FTS-Suche
    assert service.search.await_count == 1


@pytest.mark.asyncio
async def test_success_not_degraded():
    """Erfolgreiche Suche ohne Timeout bleibt degraded=False."""
    ok_response = _fts_response()
    ok_response.search_type = SearchType.HYBRID
    service = Mock()
    service.search = AsyncMock(return_value=ok_response)

    result = await _call_search(service, SearchType.HYBRID)

    assert result.degraded is False
    assert service.search.await_count == 1
