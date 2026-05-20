# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Spotlight Service.

Testet:
- Kurze Queries (<2 chars): Nur Navigation-Items
- Normale Queries: Parallele Ausfuehrung
- Fehlerbehandlung: Partielle Ergebnisse bei Einzelfehlern
- Leere Ergebnisse: Korrekte Response-Struktur
- Timing: search_time_ms wird korrekt gesetzt

Feinpoliert und durchdacht - Spotlight Service Tests.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4, UUID

from app.services.spotlight_service import (
    SpotlightService,
    SpotlightResponse,
    SpotlightSuggestion,
    SpotlightDocument,
    SpotlightEntity,
    SpotlightInterpretation,
    NAVIGATION_ITEMS,
)

pytestmark = [pytest.mark.unit]


# ========================= Fixtures =========================


@pytest.fixture
def spotlight_service() -> SpotlightService:
    """Erstellt eine frische SpotlightService-Instanz."""
    return SpotlightService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def sample_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_company_id() -> UUID:
    return uuid4()


# ========================= Short Query Tests =========================


class TestSpotlightShortQueries:
    """Tests fuer kurze Queries (<2 Zeichen)."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_all_navigation(
        self, spotlight_service, mock_db, sample_user_id
    ):
        """Leerer Query gibt alle Navigation-Items zurueck."""
        result = await spotlight_service.search(
            db=mock_db, query="", user_id=sample_user_id
        )

        assert isinstance(result, SpotlightResponse)
        assert len(result.suggestions) == len(NAVIGATION_ITEMS)
        assert result.documents == []
        assert result.entities == []
        assert result.search_time_ms >= 0

    @pytest.mark.asyncio
    async def test_single_char_query_returns_filtered_navigation(
        self, spotlight_service, mock_db, sample_user_id
    ):
        """Einstelliger Query filtert Navigation-Items."""
        result = await spotlight_service.search(
            db=mock_db, query="D", user_id=sample_user_id
        )

        assert isinstance(result, SpotlightResponse)
        # "D" matched "Dashboard" und "Dokumente"
        for suggestion in result.suggestions:
            assert "d" in suggestion.text.lower()
        assert result.documents == []
        assert result.entities == []

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_all_navigation(
        self, spotlight_service, mock_db, sample_user_id
    ):
        """Query mit nur Leerzeichen wird wie leerer Query behandelt."""
        result = await spotlight_service.search(
            db=mock_db, query="   ", user_id=sample_user_id
        )

        assert len(result.suggestions) == len(NAVIGATION_ITEMS)
        assert result.documents == []


# ========================= Normal Query Tests =========================


class TestSpotlightNormalQueries:
    """Tests fuer normale Queries (>= 2 Zeichen)."""

    @pytest.mark.asyncio
    async def test_normal_query_executes_parallel_search(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Normaler Query fuehrt parallele Suche durch."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(return_value=["Rechnung 2024", "Rechnung 2023"])

        # Mock search result
        mock_search_result = Mock()
        mock_search_result.documents = []
        mock_search_result.total_documents = 0
        mock_search_result.query = "Rechnung"
        mock_search_result.interpretation = Mock(reasoning="Suche nach Rechnungen", confidence=0.9)
        mock_search_result.detected_type = Mock(value="keyword")
        mock_smart_search.search = AsyncMock(return_value=mock_search_result)

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(return_value=[])

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db,
                query="Rechnung",
                user_id=sample_user_id,
                company_id=sample_company_id,
                limit=8,
            )

        assert isinstance(result, SpotlightResponse)
        assert result.search_time_ms > 0
        # Autocomplete was called
        mock_smart_search.autocomplete.assert_called_once()
        # Document search was called
        mock_smart_search.search.assert_called_once()
        # Entity search was called
        mock_entity_search.smart_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_normal_query_returns_documents(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Normaler Query gibt Dokument-Ergebnisse zurueck."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(return_value=[])

        mock_doc = Mock()
        mock_doc.document_id = str(uuid4())
        mock_doc.filename = "Rechnung_2024.pdf"
        mock_doc.document_type = "invoice"
        mock_doc.status = "processed"
        mock_doc.score = 0.95
        mock_doc.extracted_text_preview = "Rechnung Nr. 12345"

        mock_search_result = Mock()
        mock_search_result.documents = [mock_doc]
        mock_search_result.total_documents = 1
        mock_search_result.query = "Rechnung"
        mock_search_result.interpretation = Mock(reasoning="Suche", confidence=0.8)
        mock_search_result.detected_type = Mock(value="keyword")
        mock_smart_search.search = AsyncMock(return_value=mock_search_result)

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(return_value=[])

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db, query="Rechnung", user_id=sample_user_id,
                company_id=sample_company_id,
            )

        assert len(result.documents) == 1
        assert result.documents[0].filename == "Rechnung_2024.pdf"
        assert result.documents[0].relevance_score == 0.95
        assert result.total_documents == 1

    @pytest.mark.asyncio
    async def test_normal_query_returns_entities(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Normaler Query gibt Entity-Ergebnisse zurueck."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(return_value=[])
        mock_search_result = Mock()
        mock_search_result.documents = []
        mock_search_result.total_documents = 0
        mock_search_result.query = "Mueller"
        mock_search_result.interpretation = Mock(reasoning="Suche", confidence=0.8)
        mock_search_result.detected_type = Mock(value="keyword")
        mock_smart_search.search = AsyncMock(return_value=mock_search_result)

        mock_entity = Mock()
        mock_entity.id = uuid4()
        mock_entity.display_name = "Mueller GmbH"
        mock_entity.name = "Mueller GmbH"
        mock_entity.entity_type = "CUSTOMER"
        mock_entity.primary_customer_number = "K-1001"
        mock_entity.primary_supplier_number = None

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(return_value=[
            (mock_entity, 0.92, "fuzzy")
        ])

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db, query="Mueller", user_id=sample_user_id,
                company_id=sample_company_id,
            )

        assert len(result.entities) == 1
        assert result.entities[0].entity_name == "Mueller GmbH"
        assert result.entities[0].entity_type == "customer"
        assert result.entities[0].match_confidence == 0.92


# ========================= Error Handling Tests =========================


class TestSpotlightErrorHandling:
    """Tests fuer Fehlerbehandlung mit partiellen Ergebnissen."""

    @pytest.mark.asyncio
    async def test_suggestion_failure_returns_partial_results(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Bei Suggestion-Fehler werden trotzdem Documents und Entities zurueckgegeben."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(side_effect=RuntimeError("DB timeout"))

        mock_search_result = Mock()
        mock_search_result.documents = []
        mock_search_result.total_documents = 0
        mock_search_result.query = "test"
        mock_search_result.interpretation = Mock(reasoning="Test", confidence=0.5)
        mock_search_result.detected_type = Mock(value="keyword")
        mock_smart_search.search = AsyncMock(return_value=mock_search_result)

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(return_value=[])

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db, query="test query", user_id=sample_user_id,
                company_id=sample_company_id,
            )

        # Should still succeed with partial results
        assert isinstance(result, SpotlightResponse)
        assert result.search_time_ms > 0

    @pytest.mark.asyncio
    async def test_document_search_failure_returns_partial_results(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Bei Dokument-Suche-Fehler werden trotzdem Suggestions zurueckgegeben."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(return_value=["suggestion1"])
        mock_smart_search.search = AsyncMock(side_effect=RuntimeError("Search engine down"))

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(return_value=[])

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db, query="test query", user_id=sample_user_id,
                company_id=sample_company_id,
            )

        assert isinstance(result, SpotlightResponse)
        assert result.documents == []
        assert result.total_documents == 0

    @pytest.mark.asyncio
    async def test_entity_search_failure_returns_partial_results(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Bei Entity-Suche-Fehler werden trotzdem Documents zurueckgegeben."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(return_value=[])
        mock_search_result = Mock()
        mock_search_result.documents = []
        mock_search_result.total_documents = 0
        mock_search_result.query = "test"
        mock_search_result.interpretation = Mock(reasoning="Test", confidence=0.5)
        mock_search_result.detected_type = Mock(value="keyword")
        mock_smart_search.search = AsyncMock(return_value=mock_search_result)

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(side_effect=RuntimeError("Entity DB down"))

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db, query="test query", user_id=sample_user_id,
                company_id=sample_company_id,
            )

        assert isinstance(result, SpotlightResponse)
        assert result.entities == []

    @pytest.mark.asyncio
    async def test_all_searches_fail_returns_empty_response(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Bei Totalausfall wird leere Response zurueckgegeben."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(side_effect=RuntimeError("fail"))
        mock_smart_search.search = AsyncMock(side_effect=RuntimeError("fail"))

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(side_effect=RuntimeError("fail"))

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db, query="test query", user_id=sample_user_id,
                company_id=sample_company_id,
            )

        assert isinstance(result, SpotlightResponse)
        assert result.documents == []
        assert result.entities == []
        assert result.total_documents == 0
        assert result.search_time_ms > 0


# ========================= Response Structure Tests =========================


class TestSpotlightResponseStructure:
    """Tests fuer korrekte Response-Struktur."""

    @pytest.mark.asyncio
    async def test_search_time_ms_is_set(
        self, spotlight_service, mock_db, sample_user_id
    ):
        """search_time_ms wird korrekt gesetzt."""
        result = await spotlight_service.search(
            db=mock_db, query="", user_id=sample_user_id
        )

        assert result.search_time_ms >= 0
        assert isinstance(result.search_time_ms, float)

    @pytest.mark.asyncio
    async def test_interpretation_is_returned(
        self, spotlight_service, mock_db, sample_user_id, sample_company_id
    ):
        """Interpretation wird bei normalen Queries zurueckgegeben."""
        mock_smart_search = MagicMock()
        mock_smart_search.autocomplete = AsyncMock(return_value=[])

        mock_search_result = Mock()
        mock_search_result.documents = []
        mock_search_result.total_documents = 0
        mock_search_result.query = "Rechnung von Mueller"
        mock_search_result.interpretation = Mock(
            reasoning="Suche nach Rechnungen von Mueller", confidence=0.85
        )
        mock_search_result.detected_type = Mock(value="nlq")
        mock_smart_search.search = AsyncMock(return_value=mock_search_result)

        mock_entity_search = MagicMock()
        mock_entity_search.smart_search = AsyncMock(return_value=[])

        with patch.object(spotlight_service, '_get_smart_search', return_value=mock_smart_search), \
             patch('app.services.spotlight_service.get_entity_search_service', return_value=mock_entity_search):

            result = await spotlight_service.search(
                db=mock_db, query="Rechnung von Mueller",
                user_id=sample_user_id, company_id=sample_company_id,
            )

        assert result.interpretation is not None
        assert result.interpretation.original_query == "Rechnung von Mueller"
        assert result.interpretation.search_mode == "nlq"
        assert result.interpretation.confidence == 0.85

    def test_navigation_items_are_correct(self):
        """Statische Navigation-Items haben korrekte Struktur."""
        assert len(NAVIGATION_ITEMS) >= 5
        for item in NAVIGATION_ITEMS:
            assert item.suggestion_type == "navigation"
            assert len(item.text) > 0


# ========================= Navigation Filter Tests =========================


class TestSpotlightNavigationFilter:
    """Tests fuer den Navigation-Filter."""

    def test_filter_empty_query_returns_all(self, spotlight_service):
        """Leerer Query gibt alle Navigation-Items zurueck."""
        result = spotlight_service._filter_navigation("")
        assert len(result) == len(NAVIGATION_ITEMS)

    def test_filter_matching_query(self, spotlight_service):
        """Passender Query filtert korrekt."""
        result = spotlight_service._filter_navigation("Dok")
        assert any("Dokumente" in item.text for item in result)

    def test_filter_no_match(self, spotlight_service):
        """Nicht-passender Query gibt leere Liste zurueck."""
        result = spotlight_service._filter_navigation("xyz")
        assert result == []

    def test_filter_case_insensitive(self, spotlight_service):
        """Filter ist case-insensitive."""
        result_lower = spotlight_service._filter_navigation("ein")
        result_upper = spotlight_service._filter_navigation("Ein")
        assert len(result_lower) == len(result_upper)
