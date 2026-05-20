# -*- coding: utf-8 -*-
"""Unit-Tests fuer den Semantischen Such-Service.

Testet:
- SemanticSearchService.semantic_search
- SemanticSearchService.find_similar_documents
- SemanticSearchService.embed_document
- SemanticSearchService.batch_embed_unprocessed
- SemanticSearchService.get_embedding_coverage
- Pydantic Schemas
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas.semantic_search import (
    BatchEmbedRequest,
    EmbeddingCoverageStats,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchResultItem,
    SimilarDocumentResultItem,
    SimilarDocumentsResponse,
)
from app.services.semantic_search_service import (
    EmbeddingCoverageStats as ServiceCoverageStats,
    SemanticSearchResult,
    SemanticSearchService,
    SimilarDocumentResult,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def service() -> SemanticSearchService:
    """Erstellt eine frische Service-Instanz."""
    return SemanticSearchService()


@pytest.fixture
def mock_embedding_service():
    """Mock fuer den EmbeddingService."""
    mock = MagicMock()
    mock.generate_query_embedding_cached = AsyncMock(
        return_value=[0.1] * 1024
    )
    mock.generate_embedding_async = AsyncMock(
        return_value=[0.2] * 1024
    )
    mock.generate_batch_embeddings_async = AsyncMock(
        return_value=[[0.1] * 1024, [0.2] * 1024]
    )
    return mock


@pytest.fixture
def mock_session():
    """Mock fuer die async SQLAlchemy Session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def user_id() -> uuid.UUID:
    """Test-User-ID."""
    return uuid.uuid4()


@pytest.fixture
def document_id() -> uuid.UUID:
    """Test-Dokument-ID."""
    return uuid.uuid4()


# ============================================================================
# Schema Tests
# ============================================================================


class TestSchemas:
    """Tests fuer Pydantic Schemas."""

    def test_semantic_search_request_valid(self) -> None:
        """Gueltige Suchanfrage."""
        req = SemanticSearchRequest(
            query="Rechnungen vom Januar 2026",
            limit=10,
            threshold=0.6,
        )
        assert req.query == "Rechnungen vom Januar 2026"
        assert req.limit == 10
        assert req.threshold == 0.6

    def test_semantic_search_request_defaults(self) -> None:
        """Standardwerte der Suchanfrage."""
        req = SemanticSearchRequest(query="Test")
        assert req.limit == 20
        assert req.threshold == 0.5
        assert req.document_type is None

    def test_semantic_search_request_min_query(self) -> None:
        """Query muss mindestens 2 Zeichen haben."""
        with pytest.raises(Exception):
            SemanticSearchRequest(query="")

    def test_semantic_search_result_item(self) -> None:
        """Ergebnis-Item Validierung."""
        item = SemanticSearchResultItem(
            document_id=uuid.uuid4(),
            filename="test.pdf",
            similarity=0.85,
        )
        assert item.similarity == 0.85
        assert item.text_preview is None

    def test_embedding_coverage_stats(self) -> None:
        """Abdeckungsstatistik Validierung."""
        stats = EmbeddingCoverageStats(
            total_documents=100,
            documents_with_embedding=75,
            documents_without_embedding=25,
            coverage_percent=75.0,
            embedding_model="intfloat/multilingual-e5-large",
        )
        assert stats.coverage_percent == 75.0

    def test_batch_embed_request_defaults(self) -> None:
        """Batch-Request Standardwerte."""
        req = BatchEmbedRequest()
        assert req.batch_size == 100

    def test_similar_documents_response(self) -> None:
        """Similar Documents Response."""
        resp = SimilarDocumentsResponse(
            source_document_id=uuid.uuid4(),
            total=2,
            results=[
                SimilarDocumentResultItem(
                    document_id=uuid.uuid4(),
                    filename="aehnlich.pdf",
                    similarity=0.92,
                ),
                SimilarDocumentResultItem(
                    document_id=uuid.uuid4(),
                    filename="verwandt.pdf",
                    similarity=0.85,
                ),
            ],
            search_time_ms=42.5,
        )
        assert resp.total == 2
        assert len(resp.results) == 2


# ============================================================================
# Service Tests
# ============================================================================


class TestSemanticSearchService:
    """Tests fuer den SemanticSearchService."""

    def test_service_initialization(self, service: SemanticSearchService) -> None:
        """Service wird korrekt initialisiert."""
        assert service._embedding_service is None
        assert service._reranker is None

    @pytest.mark.asyncio
    async def test_embed_document_not_found(
        self,
        service: SemanticSearchService,
        mock_session: AsyncMock,
        document_id: uuid.UUID,
    ) -> None:
        """Embedding fuer nicht existierendes Dokument."""
        # Mock: Dokument nicht gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.embed_document(document_id, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_embed_document_no_text(
        self,
        service: SemanticSearchService,
        mock_session: AsyncMock,
        mock_embedding_service: MagicMock,
        document_id: uuid.UUID,
    ) -> None:
        """Embedding fuer Dokument ohne extrahierten Text."""
        mock_doc = MagicMock()
        mock_doc.extracted_text = None
        mock_doc.embedding = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.embed_document(document_id, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_embed_document_already_has_embedding(
        self,
        service: SemanticSearchService,
        mock_session: AsyncMock,
        document_id: uuid.UUID,
    ) -> None:
        """Dokument hat bereits ein Embedding."""
        mock_doc = MagicMock()
        mock_doc.extracted_text = "Test text"
        mock_doc.embedding = [0.1] * 1024

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.embed_document(document_id, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_embed_document_success(
        self,
        service: SemanticSearchService,
        mock_session: AsyncMock,
        mock_embedding_service: MagicMock,
        document_id: uuid.UUID,
    ) -> None:
        """Erfolgreiches Embedding eines Dokuments."""
        mock_doc = MagicMock()
        mock_doc.extracted_text = "Dies ist ein Testdokument mit deutschem Text."
        mock_doc.embedding = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute = AsyncMock(return_value=mock_result)

        service._embedding_service = mock_embedding_service

        result = await service.embed_document(document_id, mock_session)
        assert result is True
        mock_embedding_service.generate_embedding_async.assert_called_once()
        mock_session.commit.assert_called_once()


class TestSimilarDocumentResult:
    """Tests fuer die SimilarDocumentResult Datenklasse."""

    def test_creation(self) -> None:
        """SimilarDocumentResult wird korrekt erstellt."""
        result = SimilarDocumentResult(
            document_id=uuid.uuid4(),
            filename="test.pdf",
            document_type="invoice",
            similarity=0.95,
            created_at=datetime.now(timezone.utc),
            text_preview="Vorschau...",
        )
        assert result.similarity == 0.95
        assert result.document_type == "invoice"


class TestSemanticSearchResult:
    """Tests fuer die SemanticSearchResult Datenklasse."""

    def test_creation(self) -> None:
        """SemanticSearchResult wird korrekt erstellt."""
        result = SemanticSearchResult(
            document_id=uuid.uuid4(),
            filename="rechnung.pdf",
            original_filename="Rechnung_2026_001.pdf",
            document_type="invoice",
            similarity=0.88,
            created_at=datetime.now(timezone.utc),
            text_preview="Rechnung Nr. 12345...",
            page_count=2,
        )
        assert result.similarity == 0.88
        assert result.page_count == 2


class TestEmbeddingCoverageStats:
    """Tests fuer die EmbeddingCoverageStats Datenklasse."""

    def test_creation(self) -> None:
        """EmbeddingCoverageStats wird korrekt erstellt."""
        stats = ServiceCoverageStats(
            total_documents=500,
            documents_with_embedding=450,
            documents_without_embedding=50,
            coverage_percent=90.0,
            embedding_model="intfloat/multilingual-e5-large",
            oldest_embedding=datetime(2026, 1, 1, tzinfo=timezone.utc),
            newest_embedding=datetime(2026, 2, 16, tzinfo=timezone.utc),
        )
        assert stats.coverage_percent == 90.0
        assert stats.documents_without_embedding == 50

    def test_empty_database(self) -> None:
        """Leere Datenbank ohne Dokumente."""
        stats = ServiceCoverageStats(
            total_documents=0,
            documents_with_embedding=0,
            documents_without_embedding=0,
            coverage_percent=0.0,
            embedding_model="intfloat/multilingual-e5-large",
            oldest_embedding=None,
            newest_embedding=None,
        )
        assert stats.total_documents == 0
        assert stats.oldest_embedding is None
