"""Unit-Tests fuer 'Meinten Sie?' Suchvorschlaege.

Testet pg_trgm-basierte Korrekturvorschlaege bei 0 Suchergebnissen.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Check if search service is available
try:
    from app.services.search_service import SearchService
    from app.db.schemas import SearchResponse

    SEARCH_SERVICE_AVAILABLE = True
except ImportError:
    SEARCH_SERVICE_AVAILABLE = False

requires_search_service = pytest.mark.skipif(
    not SEARCH_SERVICE_AVAILABLE,
    reason="Search service dependencies not installed"
)


class TestSearchResponseDidYouMean:
    """Tests fuer did_you_mean Feld im SearchResponse."""

    @requires_search_service
    def test_search_response_has_did_you_mean_field(self):
        """SearchResponse hat optionales did_you_mean Feld."""
        fields = SearchResponse.model_fields
        assert "did_you_mean" in fields
        assert fields["did_you_mean"].default is None

    @requires_search_service
    def test_search_response_did_you_mean_serialization(self):
        """did_you_mean wird korrekt serialisiert."""
        from app.db.schemas import SearchType

        response = SearchResponse(
            query="Rechung",
            search_type=SearchType.HYBRID,
            total=0,
            page=1,
            per_page=20,
            total_pages=0,
            results=[],
            took_ms=50,
            did_you_mean="Rechnung",
        )
        data = response.model_dump()
        assert data["did_you_mean"] == "Rechnung"

    @requires_search_service
    def test_search_response_did_you_mean_none_when_results_exist(self):
        """did_you_mean ist None wenn Ergebnisse vorhanden."""
        from app.db.schemas import SearchType

        response = SearchResponse(
            query="Rechnung",
            search_type=SearchType.HYBRID,
            total=5,
            page=1,
            per_page=20,
            total_pages=1,
            results=[],
            took_ms=50,
        )
        assert response.did_you_mean is None


class TestGetDidYouMean:
    """Tests fuer _get_did_you_mean Methode."""

    @requires_search_service
    @pytest.mark.asyncio
    async def test_returns_none_for_short_query(self):
        """Gibt None zurueck bei zu kurzer Query."""
        service = SearchService.__new__(SearchService)
        result = await service._get_did_you_mean(
            db=AsyncMock(),
            query="ab",
            user_id=uuid4()
        )
        assert result is None

    @requires_search_service
    @pytest.mark.asyncio
    async def test_returns_filename_suggestion(self):
        """Gibt Dateinamen-Vorschlag via pg_trgm zurueck."""
        service = SearchService.__new__(SearchService)

        # Mock DB mit Filename-Match
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.original_filename = "Rechnung_2024.pdf"
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await service._get_did_you_mean(
            db=mock_db,
            query="Rechung",
            user_id=uuid4()
        )
        assert result == "Rechnung_2024.pdf"

    @requires_search_service
    @pytest.mark.asyncio
    async def test_returns_tag_suggestion_as_fallback(self):
        """Gibt Tag-Vorschlag zurueck wenn kein Dateiname passt."""
        service = SearchService.__new__(SearchService)

        mock_db = AsyncMock()

        # Erster Aufruf (Filename): Kein Treffer
        mock_no_match = MagicMock()
        mock_no_match.first.return_value = None

        # Zweiter Aufruf (Tags): Treffer
        mock_tag_row = MagicMock()
        mock_tag_row.name = "Rechnung"
        mock_tag_match = MagicMock()
        mock_tag_match.first.return_value = mock_tag_row

        mock_db.execute.side_effect = [mock_no_match, mock_tag_match]

        result = await service._get_did_you_mean(
            db=mock_db,
            query="Rechung",
            user_id=uuid4()
        )
        assert result == "Rechnung"

    @requires_search_service
    @pytest.mark.asyncio
    async def test_falls_back_to_spellchecker(self):
        """Nutzt SymSpell als Fallback wenn pg_trgm keine Treffer hat."""
        service = SearchService.__new__(SearchService)

        mock_db = AsyncMock()
        # Alle DB-Queries liefern keine Treffer
        mock_no_match = MagicMock()
        mock_no_match.first.return_value = None
        mock_db.execute.return_value = mock_no_match

        with patch(
            "app.services.german_spellchecker.get_german_spellchecker"
        ) as mock_spellcheck:
            mock_checker = MagicMock()
            mock_checker.correct_word.return_value = "Rechnung"
            mock_spellcheck.return_value = mock_checker

            result = await service._get_did_you_mean(
                db=mock_db,
                query="Rechung",
                user_id=uuid4()
            )
            assert result == "Rechnung"

    @requires_search_service
    @pytest.mark.asyncio
    async def test_returns_none_when_no_suggestion_found(self):
        """Gibt None zurueck wenn keine Vorschlaege gefunden werden."""
        service = SearchService.__new__(SearchService)

        mock_db = AsyncMock()
        mock_no_match = MagicMock()
        mock_no_match.first.return_value = None
        mock_db.execute.return_value = mock_no_match

        with patch(
            "app.services.german_spellchecker.get_german_spellchecker"
        ) as mock_spellcheck:
            mock_checker = MagicMock()
            # SymSpell gibt gleiches Wort zurueck = keine Korrektur
            mock_checker.correct_word.return_value = "xyzabc"
            mock_spellcheck.return_value = mock_checker

            result = await service._get_did_you_mean(
                db=mock_db,
                query="xyzabc",
                user_id=uuid4()
            )
            assert result is None

    @requires_search_service
    @pytest.mark.asyncio
    async def test_handles_multi_word_query(self):
        """Verwendet erstes Wort bei Mehrwort-Queries."""
        service = SearchService.__new__(SearchService)

        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.original_filename = "Vertrag_Muster.pdf"
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await service._get_did_you_mean(
            db=mock_db,
            query="Vertag vom Januar",
            user_id=uuid4()
        )
        assert result == "Vertrag_Muster.pdf"

    @requires_search_service
    @pytest.mark.asyncio
    async def test_handles_db_exception_gracefully(self):
        """Faengt DB-Fehler graceful ab."""
        service = SearchService.__new__(SearchService)

        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB connection lost")

        with patch(
            "app.services.german_spellchecker.get_german_spellchecker"
        ) as mock_spellcheck:
            mock_checker = MagicMock()
            mock_checker.correct_word.return_value = "Rechnung"
            mock_spellcheck.return_value = mock_checker

            # Sollte nicht abstuerzen, sondern SymSpell-Fallback nutzen
            result = await service._get_did_you_mean(
                db=mock_db,
                query="Rechung",
                user_id=uuid4()
            )
            assert result == "Rechnung"
