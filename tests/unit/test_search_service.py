"""Unit-Tests fuer den Search-Service.

Testet FTS, semantische und Hybrid-Suche mit Mocks.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import datetime
from typing import List

# Check if pgvector and search service are available
try:
    from app.services.search_service import SearchService
    from app.db.schemas import (
        SearchType, SearchFilters, SearchResponse, SearchResultItem,
        SortField, SortOrder, DocumentType, ProcessingStatus
    )
    SEARCH_SERVICE_AVAILABLE = True
except ImportError:
    SEARCH_SERVICE_AVAILABLE = False

requires_search_service = pytest.mark.skipif(
    not SEARCH_SERVICE_AVAILABLE,
    reason="Search service dependencies not installed (pgvector/sentence_transformers)"
)


class TestSearchEnums:
    """Tests fuer Such-Enums - keine externen Dependencies."""

    @pytest.mark.skipif(not SEARCH_SERVICE_AVAILABLE, reason="schemas not available")
    def test_search_type_values(self):
        """Test SearchType Werte."""
        from app.db.schemas import SearchType
        assert SearchType.FTS.value == "fts"
        assert SearchType.SEMANTIC.value == "semantic"
        assert SearchType.HYBRID.value == "hybrid"

    @pytest.mark.skipif(not SEARCH_SERVICE_AVAILABLE, reason="schemas not available")
    def test_sort_field_values(self):
        """Test SortField Werte."""
        from app.db.schemas import SortField
        assert SortField.RELEVANCE.value == "relevance"
        assert SortField.CREATED_AT.value == "created_at"
        assert SortField.UPDATED_AT.value == "updated_at"
        assert SortField.FILENAME.value == "filename"
        assert SortField.FILE_SIZE.value == "file_size"
        assert SortField.OCR_CONFIDENCE.value == "ocr_confidence"

    @pytest.mark.skipif(not SEARCH_SERVICE_AVAILABLE, reason="schemas not available")
    def test_sort_order_values(self):
        """Test SortOrder Werte."""
        from app.db.schemas import SortOrder
        assert SortOrder.ASC.value == "asc"
        assert SortOrder.DESC.value == "desc"

    @pytest.mark.skipif(not SEARCH_SERVICE_AVAILABLE, reason="schemas not available")
    def test_document_type_values(self):
        """Test DocumentType Werte."""
        from app.db.schemas import DocumentType
        assert DocumentType.INVOICE.value == "invoice"
        assert DocumentType.CONTRACT.value == "contract"
        assert DocumentType.LETTER.value == "letter"

    @pytest.mark.skipif(not SEARCH_SERVICE_AVAILABLE, reason="schemas not available")
    def test_processing_status_values(self):
        """Test ProcessingStatus Werte."""
        from app.db.schemas import ProcessingStatus
        assert ProcessingStatus.PENDING.value == "pending"
        assert ProcessingStatus.PROCESSING.value == "processing"
        assert ProcessingStatus.COMPLETED.value == "completed"
        assert ProcessingStatus.FAILED.value == "failed"


@requires_search_service
class TestSearchServiceModels:
    """Tests fuer Search-Modelle."""

    @pytest.fixture
    def sample_search_result_item(self):
        """Beispiel SearchResultItem."""
        return SearchResultItem(
            document_id=uuid4(),
            filename="test.pdf",
            original_filename="test_original.pdf",
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            file_size=1024,
            page_count=2,
            ocr_confidence=0.95,
            score=0.85,
            fts_rank=0.9,
            semantic_similarity=0.8,
            highlight="<mark>Rechnung</mark> 2024",
            text_preview="Rechnung 2024",
            tags=["Finanzen"],
            owner_id=uuid4()
        )

    def test_search_response_model(self, sample_search_result_item):
        """Test SearchResponse Modell."""
        response = SearchResponse(
            query="Rechnung",
            search_type=SearchType.HYBRID,
            total=1,
            page=1,
            per_page=20,
            total_pages=1,
            results=[sample_search_result_item],
            took_ms=50,
            filters_applied={}
        )

        assert response.query == "Rechnung"
        assert response.search_type == SearchType.HYBRID
        assert response.total == 1
        assert len(response.results) == 1

    def test_search_filters_model(self):
        """Test SearchFilters Modell."""
        filters = SearchFilters(
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            date_from=datetime(2024, 1, 1),
            confidence_min=0.8,
            has_embedding=True,
            language="de",
            tags=["Finanzen"]
        )

        assert filters.document_type == DocumentType.INVOICE
        assert filters.status == ProcessingStatus.COMPLETED
        assert filters.confidence_min == 0.8
        assert filters.has_embedding is True


@requires_search_service
class TestSearchServiceLogic:
    """Tests fuer SearchService Logik."""

    def test_truncate_text_short(self):
        """Test Text-Kuerzung mit kurzem Text."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                short_text = "Kurz"
                assert service._truncate_text(short_text, 100) == short_text

    def test_truncate_text_long(self):
        """Test Text-Kuerzung mit langem Text."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                long_text = "A" * 1000
                truncated = service._truncate_text(long_text, 100)
                assert len(truncated) == 100
                assert truncated.endswith("...")

    def test_truncate_text_none(self):
        """Test Text-Kuerzung mit None."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()
                assert service._truncate_text(None) is None

    def test_build_filter_sql_empty(self):
        """Test Filter-SQL ohne Filter."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()
                sql = service._build_filter_sql(None)
                assert sql == ""

    def test_build_filter_sql_with_filters(self):
        """Test Filter-SQL mit Filtern."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                filters = SearchFilters(
                    document_type=DocumentType.INVOICE,
                    status=ProcessingStatus.COMPLETED,
                    confidence_min=0.8
                )

                sql = service._build_filter_sql(filters)

                assert "document_type" in sql
                assert "status" in sql
                assert "ocr_confidence" in sql

    def test_get_filter_params_empty(self):
        """Test Filter-Parameter ohne Filter."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()
                params = service._get_filter_params(None)
                assert params == {}

    def test_get_filter_params_with_filters(self):
        """Test Filter-Parameter mit Filtern."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                filters = SearchFilters(
                    document_type=DocumentType.INVOICE,
                    language="de"
                )

                params = service._get_filter_params(filters)

                assert "filter_type" in params
                assert params["filter_type"] == "invoice"
                assert "filter_language" in params
                assert params["filter_language"] == "de"

    def test_sort_results_by_created_at(self):
        """Test Sortierung nach Erstelldatum."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                results = [
                    SearchResultItem(
                        document_id=uuid4(),
                        filename="doc1.pdf",
                        original_filename="doc1.pdf",
                        document_type=DocumentType.INVOICE,
                        status=ProcessingStatus.COMPLETED,
                        created_at=datetime(2024, 1, 1),
                        updated_at=datetime(2024, 1, 1),
                        file_size=1000,
                        score=0.5,
                        tags=[],
                        owner_id=uuid4()
                    ),
                    SearchResultItem(
                        document_id=uuid4(),
                        filename="doc2.pdf",
                        original_filename="doc2.pdf",
                        document_type=DocumentType.INVOICE,
                        status=ProcessingStatus.COMPLETED,
                        created_at=datetime(2024, 6, 1),
                        updated_at=datetime(2024, 6, 1),
                        file_size=2000,
                        score=0.8,
                        tags=[],
                        owner_id=uuid4()
                    )
                ]

                # Absteigend sortieren
                sorted_desc = service._sort_results(
                    results, SortField.CREATED_AT, SortOrder.DESC
                )
                assert sorted_desc[0].created_at > sorted_desc[1].created_at

                # Aufsteigend sortieren
                sorted_asc = service._sort_results(
                    results, SortField.CREATED_AT, SortOrder.ASC
                )
                assert sorted_asc[0].created_at < sorted_asc[1].created_at


@requires_search_service
@pytest.mark.asyncio
class TestSearchServiceAsync:
    """Async-Tests fuer SearchService."""

    async def test_load_tags_for_documents_empty(self):
        """Test Tag-Laden fuer leere Dokumentliste."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                mock_db = AsyncMock()
                result = await service._load_tags_for_documents(mock_db, [])

                assert result == {}
                mock_db.execute.assert_not_called()


@requires_search_service
class TestSearchServiceTagFiltering:
    """Tests fuer Tag-Filterung im SearchService."""

    def test_build_filter_sql_with_tags(self):
        """Test Filter-SQL mit Tag-Filter."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                filters = SearchFilters(
                    tags=["Finanzen", "2024"]
                )

                sql = service._build_filter_sql(filters)

                assert "document_tags" in sql
                assert "filter_tags" in sql
                assert "filter_tags_count" in sql

    def test_get_filter_params_with_tags(self):
        """Test Filter-Parameter mit Tags."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                filters = SearchFilters(
                    tags=["Finanzen", "Rechnung"]
                )

                params = service._get_filter_params(filters)

                assert "filter_tags" in params
                assert params["filter_tags"] == ["Finanzen", "Rechnung"]
                assert "filter_tags_count" in params
                assert params["filter_tags_count"] == 2

    def test_build_filter_sql_with_all_filters(self):
        """Test Filter-SQL mit allen Filtern."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                filters = SearchFilters(
                    document_type=DocumentType.INVOICE,
                    status=ProcessingStatus.COMPLETED,
                    date_from=datetime(2024, 1, 1),
                    date_to=datetime(2024, 12, 31),
                    confidence_min=0.8,
                    has_embedding=True,
                    language="de",
                    tags=["Test"]
                )

                sql = service._build_filter_sql(filters)

                assert "document_type" in sql
                assert "status" in sql
                assert "created_at" in sql
                assert "ocr_confidence" in sql
                assert "embedding IS NOT NULL" in sql
                assert "detected_language" in sql
                assert "document_tags" in sql


@requires_search_service
class TestSearchServiceGermanText:
    """Tests fuer deutsche Textverarbeitung im SearchService."""

    def test_truncate_text_with_umlauts(self):
        """Test Text-Kuerzung mit Umlauten."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                german_text = "Ärger über Öffentlichkeit und Übermütige äußern"
                result = service._truncate_text(german_text, 100)

                # Umlaute sollten erhalten bleiben
                assert "Ä" in result
                assert "Ö" in result
                assert "Ü" in result
                assert "ä" in result
                assert "ü" in result

    def test_sort_results_by_filename_german(self):
        """Test Sortierung nach Dateinamen mit deutschen Zeichen."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                results = [
                    SearchResultItem(
                        document_id=uuid4(),
                        filename="Ärger.pdf",
                        original_filename="Ärger.pdf",
                        document_type=DocumentType.INVOICE,
                        status=ProcessingStatus.COMPLETED,
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                        file_size=1000,
                        score=0.5,
                        tags=[],
                        owner_id=uuid4()
                    ),
                    SearchResultItem(
                        document_id=uuid4(),
                        filename="Angebot.pdf",
                        original_filename="Angebot.pdf",
                        document_type=DocumentType.INVOICE,
                        status=ProcessingStatus.COMPLETED,
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                        file_size=2000,
                        score=0.8,
                        tags=[],
                        owner_id=uuid4()
                    )
                ]

                sorted_asc = service._sort_results(
                    results, SortField.FILENAME, SortOrder.ASC
                )

                # Sortierung sollte funktionieren
                assert len(sorted_asc) == 2


@requires_search_service
class TestEmbeddingValidation:
    """Tests fuer Embedding-Validierung."""

    def test_validate_embedding_valid(self):
        """Test valide Embeddings."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                # Normale Werte
                valid_embedding = [0.1, 0.2, -0.3, 0.0, 1.0, -1.0]
                assert service._validate_embedding(valid_embedding) is True

    def test_validate_embedding_nan(self):
        """Test Embedding mit NaN-Werten."""
        import math
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                # Embedding mit NaN
                nan_embedding = [0.1, math.nan, 0.3]
                assert service._validate_embedding(nan_embedding) is False

    def test_validate_embedding_inf(self):
        """Test Embedding mit Inf-Werten."""
        import math
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                # Embedding mit Inf
                inf_embedding = [0.1, math.inf, 0.3]
                assert service._validate_embedding(inf_embedding) is False

                # Embedding mit -Inf
                neg_inf_embedding = [0.1, -math.inf, 0.3]
                assert service._validate_embedding(neg_inf_embedding) is False

    def test_validate_embedding_empty(self):
        """Test leeres Embedding."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                # Leeres Embedding ist technisch valide (alle Elemente erfuellen die Bedingung)
                empty_embedding: List[float] = []
                assert service._validate_embedding(empty_embedding) is True

    def test_validate_embedding_integer_values(self):
        """Test Embedding mit Integer-Werten (sollte valide sein)."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings") as mock_settings:
                mock_settings.HYBRID_FTS_WEIGHT = 0.6
                mock_settings.HYBRID_SEMANTIC_WEIGHT = 0.4
                mock_settings.SEMANTIC_SIMILARITY_THRESHOLD = 0.5

                service = SearchService()

                # Integer-Werte sollten auch akzeptiert werden
                int_embedding = [1, 2, 3, 0, -1]
                assert service._validate_embedding(int_embedding) is True


@requires_search_service
class TestSearchServiceCaching:
    """Tests fuer Such-Caching Funktionalitaet."""

    @pytest.fixture
    def mock_settings(self):
        """Mock Settings mit Cache aktiviert."""
        mock = MagicMock()
        mock.HYBRID_FTS_WEIGHT = 0.6
        mock.HYBRID_SEMANTIC_WEIGHT = 0.4
        mock.SEMANTIC_SIMILARITY_THRESHOLD = 0.5
        mock.SEARCH_CACHE_ENABLED = True
        mock.SEARCH_CACHE_TTL = 3600
        mock.SEARCH_EMBEDDING_CACHE_TTL = 86400
        mock.SEARCH_SIMILAR_CACHE_TTL = 1800
        return mock

    def test_generate_search_cache_key_basic(self, mock_settings):
        """Test Cache-Key Generierung fuer Suche."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings):
                service = SearchService()

                user_id = uuid4()
                cache_key = service._generate_search_cache_key(
                    query="test query",
                    user_id=user_id,
                    search_type=SearchType.HYBRID,
                    filters=None,
                    page=1,
                    per_page=20,
                    sort_by=SortField.RELEVANCE,
                    sort_order=SortOrder.DESC
                )

                # Key sollte strukturiert sein
                assert cache_key.startswith("search:")
                assert "hybrid" in cache_key
                assert str(user_id) in cache_key
                assert ":1:" in cache_key  # Page
                assert ":20:" in cache_key  # Per page
                assert ":nofilter" in cache_key

    def test_generate_search_cache_key_with_filters(self, mock_settings):
        """Test Cache-Key Generierung mit Filtern."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings):
                service = SearchService()

                user_id = uuid4()
                filters = SearchFilters(
                    document_type=DocumentType.INVOICE,
                    tags=["Finanzen"]
                )

                cache_key = service._generate_search_cache_key(
                    query="Rechnung",
                    user_id=user_id,
                    search_type=SearchType.FTS,
                    filters=filters,
                    page=2,
                    per_page=10,
                    sort_by=SortField.CREATED_AT,
                    sort_order=SortOrder.ASC
                )

                assert cache_key.startswith("search:")
                assert "fts" in cache_key
                assert "nofilter" not in cache_key  # Filter-Hash statt nofilter

    def test_generate_search_cache_key_deterministic(self, mock_settings):
        """Test dass gleiche Parameter gleichen Key erzeugen."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings):
                service = SearchService()

                user_id = uuid4()
                params = {
                    "query": "test",
                    "user_id": user_id,
                    "search_type": SearchType.HYBRID,
                    "filters": None,
                    "page": 1,
                    "per_page": 20,
                    "sort_by": SortField.RELEVANCE,
                    "sort_order": SortOrder.DESC
                }

                key1 = service._generate_search_cache_key(**params)
                key2 = service._generate_search_cache_key(**params)

                assert key1 == key2

    def test_generate_search_cache_key_different_queries(self, mock_settings):
        """Test dass unterschiedliche Queries unterschiedliche Keys erzeugen."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings):
                service = SearchService()

                user_id = uuid4()
                base_params = {
                    "user_id": user_id,
                    "search_type": SearchType.HYBRID,
                    "filters": None,
                    "page": 1,
                    "per_page": 20,
                    "sort_by": SortField.RELEVANCE,
                    "sort_order": SortOrder.DESC
                }

                key1 = service._generate_search_cache_key(query="Rechnung", **base_params)
                key2 = service._generate_search_cache_key(query="Vertrag", **base_params)

                assert key1 != key2

    def test_generate_similar_cache_key(self, mock_settings):
        """Test Cache-Key Generierung fuer aehnliche Dokumente."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings):
                service = SearchService()

                document_id = uuid4()
                user_id = uuid4()

                cache_key = service._generate_similar_cache_key(
                    document_id=document_id,
                    user_id=user_id,
                    limit=10,
                    threshold=0.6
                )

                assert cache_key.startswith("search:similar:")
                assert str(user_id) in cache_key
                assert str(document_id) in cache_key
                assert ":10:" in cache_key
                assert ":0.6" in cache_key

    def test_generate_embedding_cache_key(self, mock_settings):
        """Test Cache-Key Generierung fuer Query-Embeddings."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings):
                service = SearchService()

                cache_key = service._generate_embedding_cache_key("test query")

                assert cache_key.startswith("search:embedding:")
                # Hash sollte enthalten sein
                assert len(cache_key) > len("search:embedding:")

    def test_generate_embedding_cache_key_deterministic(self, mock_settings):
        """Test dass gleiche Queries gleichen Embedding-Key erzeugen."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings):
                service = SearchService()

                key1 = service._generate_embedding_cache_key("Rechnung 2024")
                key2 = service._generate_embedding_cache_key("Rechnung 2024")

                assert key1 == key2


@requires_search_service
@pytest.mark.asyncio
class TestSearchServiceCacheInvalidation:
    """Tests fuer Cache-Invalidierung."""

    @pytest.fixture
    def mock_settings_cache_enabled(self):
        """Mock Settings mit Cache aktiviert."""
        mock = MagicMock()
        mock.HYBRID_FTS_WEIGHT = 0.6
        mock.HYBRID_SEMANTIC_WEIGHT = 0.4
        mock.SEMANTIC_SIMILARITY_THRESHOLD = 0.5
        mock.SEARCH_CACHE_ENABLED = True
        mock.SEARCH_CACHE_TTL = 3600
        mock.SEARCH_EMBEDDING_CACHE_TTL = 86400
        mock.SEARCH_SIMILAR_CACHE_TTL = 1800
        return mock

    @pytest.fixture
    def mock_settings_cache_disabled(self):
        """Mock Settings mit Cache deaktiviert."""
        mock = MagicMock()
        mock.HYBRID_FTS_WEIGHT = 0.6
        mock.HYBRID_SEMANTIC_WEIGHT = 0.4
        mock.SEMANTIC_SIMILARITY_THRESHOLD = 0.5
        mock.SEARCH_CACHE_ENABLED = False
        mock.SEARCH_CACHE_TTL = 3600
        mock.SEARCH_EMBEDDING_CACHE_TTL = 86400
        mock.SEARCH_SIMILAR_CACHE_TTL = 1800
        return mock

    async def test_invalidate_user_search_cache_disabled(self, mock_settings_cache_disabled):
        """Test Invalidierung wenn Cache deaktiviert ist."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings_cache_disabled):
                service = SearchService()

                user_id = uuid4()
                count = await service.invalidate_user_search_cache(user_id)

                assert count == 0

    async def test_invalidate_user_search_cache_success(self, mock_settings_cache_enabled):
        """Test erfolgreiche User-Cache Invalidierung."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings_cache_enabled):
                service = SearchService()

                # Mock Redis Manager
                mock_redis = AsyncMock()
                mock_redis.invalidate_cache = AsyncMock(return_value=5)
                mock_redis.connect = AsyncMock()
                service._redis_manager = mock_redis

                user_id = uuid4()
                count = await service.invalidate_user_search_cache(user_id)

                assert count == 5
                mock_redis.invalidate_cache.assert_called_once()
                call_args = mock_redis.invalidate_cache.call_args[0][0]
                assert str(user_id) in call_args

    async def test_invalidate_user_search_cache_error_handling(self, mock_settings_cache_enabled):
        """Test Fehlerbehandlung bei Invalidierung."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings_cache_enabled):
                service = SearchService()

                # Mock Redis Manager mit Fehler
                mock_redis = AsyncMock()
                mock_redis.invalidate_cache = AsyncMock(side_effect=Exception("Redis error"))
                mock_redis.connect = AsyncMock()
                service._redis_manager = mock_redis

                user_id = uuid4()
                count = await service.invalidate_user_search_cache(user_id)

                # Sollte 0 zurueckgeben bei Fehler
                assert count == 0

    async def test_invalidate_document_cache_disabled(self, mock_settings_cache_disabled):
        """Test Document-Cache Invalidierung wenn Cache deaktiviert."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings_cache_disabled):
                service = SearchService()

                document_id = uuid4()
                user_id = uuid4()
                count = await service.invalidate_document_cache(document_id, user_id)

                assert count == 0

    async def test_invalidate_document_cache_success(self, mock_settings_cache_enabled):
        """Test erfolgreiche Document-Cache Invalidierung."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings_cache_enabled):
                service = SearchService()

                # Mock Redis Manager
                mock_redis = AsyncMock()
                # Erster Aufruf fuer similar, zweiter fuer user
                mock_redis.invalidate_cache = AsyncMock(side_effect=[3, 7])
                mock_redis.connect = AsyncMock()
                service._redis_manager = mock_redis

                document_id = uuid4()
                user_id = uuid4()
                count = await service.invalidate_document_cache(document_id, user_id)

                # 3 + 7 = 10
                assert count == 10

    async def test_invalidate_all_search_cache_disabled(self, mock_settings_cache_disabled):
        """Test All-Cache Invalidierung wenn Cache deaktiviert."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings_cache_disabled):
                service = SearchService()

                count = await service.invalidate_all_search_cache()

                assert count == 0

    async def test_invalidate_all_search_cache_success(self, mock_settings_cache_enabled):
        """Test erfolgreiche All-Cache Invalidierung."""
        with patch("app.services.search_service.get_embedding_service"):
            with patch("app.services.search_service.settings", mock_settings_cache_enabled):
                service = SearchService()

                # Mock Redis Manager
                mock_redis = AsyncMock()
                mock_redis.invalidate_cache = AsyncMock(return_value=100)
                mock_redis.connect = AsyncMock()
                service._redis_manager = mock_redis

                count = await service.invalidate_all_search_cache()

                assert count == 100
                mock_redis.invalidate_cache.assert_called_with("search:*")
