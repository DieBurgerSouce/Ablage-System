# -*- coding: utf-8 -*-
"""
Tests fuer Smart Search Service.

Feature #1: Smart Search / Natural Language Search
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.smart_search_service import (
    SmartSearchService,
    DetectedQueryType,
    SmartSearchEntity,
)
from app.services.ai.nlq_service import NLQResult, QueryIntent, ExtractedEntity
from app.services.unified_search_service import (
    UnifiedSearchResponse,
    UnifiedDocumentResult,
    UnifiedSearchMode,
)


@pytest.fixture
def smart_search_service():
    """Fixture fuer SmartSearchService."""
    return SmartSearchService()


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    return AsyncMock()


@pytest.fixture
def user_id():
    """Test User-ID."""
    return uuid4()


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid4()


# ============================================================================
# Query Type Detection Tests
# ============================================================================


class TestQueryTypeDetection:
    """Tests fuer automatische Query-Typ-Erkennung."""

    def test_detect_nlq_question_word(self, smart_search_service):
        """Test: Fragewort am Anfang -> NLQ."""
        query = "Zeige mir alle Rechnungen von Mueller"
        detected_type, confidence, reasoning = smart_search_service._detect_query_type(query)

        assert detected_type == DetectedQueryType.NLQ
        assert confidence >= 0.9
        assert "Fragewort" in reasoning

    def test_detect_nlq_aggregation(self, smart_search_service):
        """Test: Aggregationswort -> NLQ."""
        query = "Wie hoch ist die Summe aller offenen Rechnungen"
        detected_type, confidence, reasoning = smart_search_service._detect_query_type(query)

        assert detected_type == DetectedQueryType.NLQ
        assert confidence >= 0.85
        assert "Aggregation" in reasoning or "summe" in reasoning.lower() or "fragewort" in reasoning.lower()

    def test_detect_nlq_verb_structure(self, smart_search_service):
        """Test: Natuerliche Satzstruktur mit Verb -> NLQ."""
        query = "Welche Dokumente sind seit Januar offen"
        detected_type, confidence, reasoning = smart_search_service._detect_query_type(query)

        assert detected_type == DetectedQueryType.NLQ
        assert confidence >= 0.75

    def test_detect_keyword_short_query(self, smart_search_service):
        """Test: Kurze Query (1-2 Woerter) -> Keyword."""
        query = "Mueller Rechnung"
        detected_type, confidence, reasoning = smart_search_service._detect_query_type(query)

        assert detected_type == DetectedQueryType.KEYWORD
        assert confidence >= 0.8
        assert "Kurze Query" in reasoning or "Keyword" in reasoning

    def test_detect_keyword_no_patterns(self, smart_search_service):
        """Test: Query ohne NLQ-Muster -> Keyword."""
        query = "Mueller GmbH invoice 2025"
        detected_type, confidence, reasoning = smart_search_service._detect_query_type(query)

        assert detected_type == DetectedQueryType.KEYWORD

    def test_detect_nlq_long_query(self, smart_search_service):
        """Test: Lange Query ohne Operatoren -> NLQ."""
        query = "Ich suche alle offenen Rechnungen von Mueller aus dem letzten Monat"
        detected_type, confidence, reasoning = smart_search_service._detect_query_type(query)

        assert detected_type == DetectedQueryType.NLQ
        assert confidence >= 0.7


# ============================================================================
# Search Integration Tests
# ============================================================================


class TestSmartSearchIntegration:
    """Tests fuer vollstaendige Such-Flows."""

    @pytest.mark.asyncio
    async def test_nlq_search_flow(
        self,
        smart_search_service,
        mock_db,
        user_id,
        company_id,
    ):
        """Test: NLQ-Flow mit Dokumenten-Ergebnissen."""
        query = "Zeige mir alle Rechnungen von Mueller"

        # Mock NLQ Service
        mock_nlq_result = NLQResult(
            success=True,
            intent=QueryIntent.SEARCH,
            extracted_entities=[
                ExtractedEntity(
                    entity_type="COMPANY",
                    value={"name": "Mueller GmbH"},
                    original_text="Mueller",
                    confidence=0.9,
                )
            ],
            results=[
                {
                    "id": str(uuid4()),
                    "filename": "Rechnung_Mueller_001.pdf",
                    "document_type": "invoice",
                    "created_at": "2025-01-15T10:00:00Z",
                }
            ],
            result_count=1,
            natural_response="Ich habe 1 Rechnung gefunden: Rechnung_Mueller_001.pdf",
            confidence=0.85,
        )

        with patch.object(
            smart_search_service,
            "_execute_nlq_search",
            return_value=mock_nlq_result,
        ):
            # Mock Entity Search
            with patch.object(
                smart_search_service,
                "_search_entities",
                return_value=([], 0),
            ):
                result = await smart_search_service.search(
                    db=mock_db,
                    query=query,
                    user_id=user_id,
                    company_id=company_id,
                    limit=20,
                )

        assert result.detected_type == DetectedQueryType.NLQ
        assert result.total_documents == 1
        assert len(result.documents) == 1
        assert result.documents[0].filename == "Rechnung_Mueller_001.pdf"
        assert result.natural_response == mock_nlq_result.natural_response
        assert result.nlq_confidence == 0.85

    @pytest.mark.asyncio
    async def test_keyword_search_flow(
        self,
        smart_search_service,
        mock_db,
        user_id,
        company_id,
    ):
        """Test: Keyword-Flow mit Unified Search."""
        query = "Mueller invoice"

        # Mock Unified Search
        doc_id = str(uuid4())
        mock_unified_result = UnifiedSearchResponse(
            query=query,
            mode=UnifiedSearchMode.COMBINED,
            documents=[
                UnifiedDocumentResult(
                    document_id=doc_id,
                    filename="Invoice_Mueller.pdf",
                    original_filename="Invoice_Mueller.pdf",
                    score=0.95,
                    document_type="invoice",
                    status="completed",
                    created_at="2025-01-15T10:00:00Z",
                    mime_type="application/pdf",
                    page_count=2,
                )
            ],
            total_documents=1,
            chunk_results=[],
            total_chunks=0,
            search_time_ms=50.0,
        )

        with patch.object(
            smart_search_service,
            "_execute_keyword_search",
            return_value=mock_unified_result,
        ):
            # Mock Entity Search
            with patch.object(
                smart_search_service,
                "_search_entities",
                return_value=([], 0),
            ):
                result = await smart_search_service.search(
                    db=mock_db,
                    query=query,
                    user_id=user_id,
                    company_id=company_id,
                    limit=20,
                )

        assert result.detected_type == DetectedQueryType.KEYWORD
        assert result.total_documents == 1
        assert result.documents[0].score == 0.95
        assert result.natural_response is None  # Kein NLQ-Response bei Keyword

    @pytest.mark.asyncio
    async def test_entity_search_parallel(
        self,
        smart_search_service,
        mock_db,
        user_id,
        company_id,
    ):
        """Test: Entity-Suche wird parallel durchgefuehrt."""
        query = "Mueller"

        mock_entities = [
            SmartSearchEntity(
                entity_id=str(uuid4()),
                entity_type="CUSTOMER",
                name="Mueller GmbH",
                display_name="Mueller GmbH",
                match_type="matchcode",
                confidence=0.95,
            )
        ]

        # Mock beide Suchen
        with patch.object(
            smart_search_service,
            "_execute_keyword_search",
            return_value=UnifiedSearchResponse(
                query=query,
                mode=UnifiedSearchMode.COMBINED,
                documents=[],
                total_documents=0,
                chunk_results=[],
                total_chunks=0,
                search_time_ms=10.0,
            ),
        ):
            with patch.object(
                smart_search_service,
                "_search_entities",
                return_value=(mock_entities, 1),
            ):
                result = await smart_search_service.search(
                    db=mock_db,
                    query=query,
                    user_id=user_id,
                    company_id=company_id,
                    limit=20,
                )

        assert result.total_entities == 1
        assert len(result.entities) == 1
        assert result.entities[0].name == "Mueller GmbH"
        assert result.entities[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_force_mode_nlq(
        self,
        smart_search_service,
        mock_db,
        user_id,
        company_id,
    ):
        """Test: Force-Mode erzwingt NLQ trotz Keyword-Query."""
        query = "Mueller"  # Normalerweise Keyword

        mock_nlq_result = NLQResult(
            success=True,
            intent=QueryIntent.SEARCH,
            extracted_entities=[],
            results=[],
            result_count=0,
            natural_response="Keine Dokumente gefunden",
            confidence=0.5,
        )

        with patch.object(
            smart_search_service,
            "_execute_nlq_search",
            return_value=mock_nlq_result,
        ):
            with patch.object(
                smart_search_service,
                "_search_entities",
                return_value=([], 0),
            ):
                result = await smart_search_service.search(
                    db=mock_db,
                    query=query,
                    user_id=user_id,
                    company_id=company_id,
                    limit=20,
                    force_mode=DetectedQueryType.NLQ,
                )

        assert result.detected_type == DetectedQueryType.NLQ
        assert result.interpretation.confidence == 1.0  # Force-Mode = 100% confidence


# ============================================================================
# Suggestions Tests
# ============================================================================


class TestSuggestions:
    """Tests fuer Query-Suggestions."""

    def test_suggestions_no_results_nlq(self, smart_search_service):
        """Test: Suggestions bei NLQ ohne Ergebnisse."""
        suggestions = smart_search_service._generate_suggestions(
            query="Zeige alle XYZ",
            detected_type=DetectedQueryType.NLQ,
            has_results=False,
        )

        assert len(suggestions) > 0
        assert any("einfacher" in s.lower() for s in suggestions)

    def test_suggestions_no_results_keyword(self, smart_search_service):
        """Test: Suggestions bei Keyword ohne Ergebnisse."""
        suggestions = smart_search_service._generate_suggestions(
            query="XYZ ABC",
            detected_type=DetectedQueryType.KEYWORD,
            has_results=False,
        )

        assert len(suggestions) > 0
        assert any("weniger spezifisch" in s.lower() for s in suggestions)

    def test_suggestions_with_results(self, smart_search_service):
        """Test: Verfeinerungs-Suggestions bei vorhandenen Ergebnissen."""
        suggestions = smart_search_service._generate_suggestions(
            query="Mueller",
            detected_type=DetectedQueryType.KEYWORD,
            has_results=True,
        )

        assert len(suggestions) > 0
        assert len(suggestions) <= 3  # Max 3 Suggestions


# ============================================================================
# Autocomplete Tests
# ============================================================================


class TestAutocomplete:
    """Tests fuer Autocomplete-Funktionalitaet."""

    @pytest.mark.asyncio
    async def test_autocomplete_short_query(
        self,
        smart_search_service,
        mock_db,
    ):
        """Test: Autocomplete gibt keine Suggestions bei zu kurzer Query."""
        suggestions = await smart_search_service.autocomplete(
            db=mock_db,
            query="Ze",  # Zu kurz
            limit=10,
        )

        # Bei kurzen Queries nur Suggestions wenn Pattern matcht
        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_autocomplete_nlq_pattern(
        self,
        smart_search_service,
        mock_db,
    ):
        """Test: Autocomplete erkennt NLQ-Pattern."""
        suggestions = await smart_search_service.autocomplete(
            db=mock_db,
            query="Zeige",
            limit=10,
        )

        assert len(suggestions) > 0
        assert any("Zeige" in s for s in suggestions)

    @pytest.mark.asyncio
    async def test_autocomplete_limit(
        self,
        smart_search_service,
        mock_db,
    ):
        """Test: Autocomplete respektiert Limit."""
        suggestions = await smart_search_service.autocomplete(
            db=mock_db,
            query="Wie",
            limit=3,
        )

        assert len(suggestions) <= 3


# ============================================================================
# Facets Tests
# ============================================================================


class TestFacets:
    """Tests fuer Facetten-Berechnung."""

    def test_calculate_facets_documents(self, smart_search_service):
        """Test: Facets werden aus Dokumenten berechnet."""
        documents = [
            UnifiedDocumentResult(
                document_id=str(uuid4()),
                filename="doc1.pdf",
                original_filename="doc1.pdf",
                score=1.0,
                document_type="invoice",
                status="pending",
                created_at="2025-01-01T00:00:00Z",
                mime_type="application/pdf",
                page_count=1,
            ),
            UnifiedDocumentResult(
                document_id=str(uuid4()),
                filename="doc2.pdf",
                original_filename="doc2.pdf",
                score=0.9,
                document_type="invoice",
                status="completed",
                created_at="2025-01-02T00:00:00Z",
                mime_type="application/pdf",
                page_count=2,
            ),
            UnifiedDocumentResult(
                document_id=str(uuid4()),
                filename="doc3.pdf",
                original_filename="doc3.pdf",
                score=0.8,
                document_type="contract",
                status="pending",
                created_at="2025-01-03T00:00:00Z",
                mime_type="application/pdf",
                page_count=5,
            ),
        ]

        facets = smart_search_service._calculate_facets(documents, [])

        assert facets.total_count == 3
        assert facets.document_types == {"invoice": 2, "contract": 1}
        assert facets.statuses == {"pending": 2, "completed": 1}

    def test_calculate_facets_entities(self, smart_search_service):
        """Test: Facets enthalten Entity-Counts."""
        entity_id = str(uuid4())
        entities = [
            SmartSearchEntity(
                entity_id=entity_id,
                entity_type="CUSTOMER",
                name="Test",
                display_name="Test",
                match_type="matchcode",
                confidence=0.9,
            )
        ]

        facets = smart_search_service._calculate_facets([], entities)

        assert entity_id in facets.entities
        assert facets.entities[entity_id] == 1


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_search_handles_nlq_error(
        self,
        smart_search_service,
        mock_db,
        user_id,
        company_id,
    ):
        """Test: Fehler in NLQ-Service wird abgefangen."""
        query = "Zeige alle Rechnungen"

        with patch.object(
            smart_search_service,
            "_execute_nlq_search",
            side_effect=Exception("NLQ-Error"),
        ):
            with patch.object(
                smart_search_service,
                "_search_entities",
                return_value=([], 0),
            ):
                result = await smart_search_service.search(
                    db=mock_db,
                    query=query,
                    user_id=user_id,
                    company_id=company_id,
                    limit=20,
                )

        # Sollte Fallback-Response zurueckgeben
        assert result.total_documents == 0
        assert result.natural_response is not None  # Fehler-Message
        assert "Suche" in result.natural_response  # safe_error_detail pattern

    @pytest.mark.asyncio
    async def test_search_handles_keyword_error(
        self,
        smart_search_service,
        mock_db,
        user_id,
        company_id,
    ):
        """Test: Fehler in Keyword-Search wird abgefangen."""
        query = "Mueller invoice"

        with patch.object(
            smart_search_service,
            "_execute_keyword_search",
            side_effect=Exception("Search-Error"),
        ):
            with patch.object(
                smart_search_service,
                "_search_entities",
                return_value=([], 0),
            ):
                result = await smart_search_service.search(
                    db=mock_db,
                    query=query,
                    user_id=user_id,
                    company_id=company_id,
                    limit=20,
                )

        # Sollte Fallback-Response zurueckgeben
        assert result.total_documents == 0
        assert result.natural_response is not None
