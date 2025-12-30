"""Unit-Tests fuer den SearchAnalyticsService.

Testet Analytics-Logging, Statistiken und Reporting.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timedelta

# Check if dependencies are available
try:
    from app.services.search_analytics_service import (
        SearchAnalyticsService,
        get_search_analytics_service
    )
    from app.db.schemas import SearchType, SearchFilters, DocumentType, ProcessingStatus
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False

requires_analytics = pytest.mark.skipif(
    not ANALYTICS_AVAILABLE,
    reason="Search analytics dependencies not installed"
)


@requires_analytics
class TestSearchAnalyticsService:
    """Tests fuer SearchAnalyticsService."""

    @pytest.fixture
    def service(self):
        """Service-Instanz."""
        return SearchAnalyticsService()

    @pytest.fixture
    def mock_db(self):
        """Mock Database Session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_filters(self):
        """Beispiel-Filter."""
        return SearchFilters(
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            date_from=datetime(2024, 1, 1),
            tags=["Finanzen", "2024"]
        )

    @pytest.mark.asyncio
    async def test_log_search_basic(self, service, mock_db):
        """Test einfaches Search-Logging."""
        mock_db.commit = AsyncMock()
        mock_db.add = Mock()

        # Mock refresh to set the ID on the analytics object
        async def set_id_on_refresh(obj):
            obj.id = uuid4()
        mock_db.refresh = AsyncMock(side_effect=set_id_on_refresh)

        result = await service.log_search(
            db=mock_db,
            query="Rechnung 2024",
            search_type=SearchType.HYBRID,
            total_results=42,
            execution_time_ms=150,
            user_id=uuid4()
        )

        assert result is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_search_with_filters(self, service, mock_db, sample_filters):
        """Test Search-Logging mit Filtern."""
        mock_db.commit = AsyncMock()
        mock_db.add = Mock()

        # Mock refresh to set the ID on the analytics object
        async def set_id_on_refresh(obj):
            obj.id = uuid4()
        mock_db.refresh = AsyncMock(side_effect=set_id_on_refresh)

        result = await service.log_search(
            db=mock_db,
            query="Test",
            search_type=SearchType.FTS,
            total_results=10,
            execution_time_ms=50,
            filters=sample_filters
        )

        assert result is not None
        # Verify the analytics object was created with filter flags
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.has_document_type_filter is True
        assert added_obj.has_date_filter is True
        assert added_obj.has_tag_filter is True

    @pytest.mark.asyncio
    async def test_log_search_ip_anonymization(self, service, mock_db):
        """Test IP-Anonymisierung."""
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = Mock()

        await service.log_search(
            db=mock_db,
            query="Test",
            search_type=SearchType.SEMANTIC,
            total_results=5,
            execution_time_ms=100,
            ip_address="192.168.1.100"
        )

        added_obj = mock_db.add.call_args[0][0]
        # IP should be anonymized to x.x.0.0
        assert added_obj.ip_address == "192.168.0.0"

    @pytest.mark.asyncio
    async def test_log_search_ipv6_anonymization(self, service, mock_db):
        """Test IPv6-Anonymisierung."""
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = Mock()

        await service.log_search(
            db=mock_db,
            query="Test",
            search_type=SearchType.HYBRID,
            total_results=5,
            execution_time_ms=100,
            ip_address="2001:db8:85a3::8a2e:370:7334"
        )

        added_obj = mock_db.add.call_args[0][0]
        # IPv6 should be truncated to first 3 segments (48 bits)
        assert added_obj.ip_address == "2001:0db8:85a3::"

    @pytest.mark.asyncio
    async def test_log_search_query_truncation(self, service, mock_db):
        """Test Query-Kuerzung bei langen Anfragen."""
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = Mock()

        long_query = "A" * 1000  # Sehr lange Anfrage

        await service.log_search(
            db=mock_db,
            query=long_query,
            search_type=SearchType.FTS,
            total_results=0,
            execution_time_ms=50
        )

        added_obj = mock_db.add.call_args[0][0]
        assert len(added_obj.search_query) <= 500

    @pytest.mark.asyncio
    async def test_log_click_success(self, service, mock_db):
        """Test Klick-Logging."""
        analytics_id = uuid4()

        mock_analytics = Mock()
        mock_analytics.clicked_results = 0
        mock_analytics.first_click_position = None
        mock_analytics.downloaded_count = 0

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_analytics
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        await service.log_click(
            db=mock_db,
            analytics_id=analytics_id,
            result_position=3,
            is_download=False
        )

        assert mock_analytics.clicked_results == 1
        assert mock_analytics.first_click_position == 3
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_click_with_download(self, service, mock_db):
        """Test Klick-Logging mit Download."""
        analytics_id = uuid4()

        mock_analytics = Mock()
        mock_analytics.clicked_results = 1
        mock_analytics.first_click_position = 1
        mock_analytics.downloaded_count = 0

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_analytics
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        await service.log_click(
            db=mock_db,
            analytics_id=analytics_id,
            result_position=2,
            is_download=True
        )

        assert mock_analytics.clicked_results == 2
        # first_click_position should remain 1 (first click)
        assert mock_analytics.first_click_position == 1
        assert mock_analytics.downloaded_count == 1

    @pytest.mark.asyncio
    async def test_log_click_not_found(self, service, mock_db):
        """Test Klick-Logging fuer nicht existente Analytics."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Should not raise an error
        await service.log_click(
            db=mock_db,
            analytics_id=uuid4(),
            result_position=1
        )

        # commit should not be called
        mock_db.commit.assert_not_called()


@requires_analytics
class TestSearchAnalyticsServiceStatistics:
    """Tests fuer Statistik-Funktionen."""

    @pytest.fixture
    def service(self):
        """Service-Instanz."""
        return SearchAnalyticsService()

    @pytest.fixture
    def mock_db(self):
        """Mock Database Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_search_statistics_empty(self, service, mock_db):
        """Test Statistiken ohne Daten."""
        # Mock empty results
        mock_total_result = Mock()
        mock_total_result.one.return_value = Mock(
            total_searches=0,
            unique_users=0,
            avg_results=None,
            avg_execution_time=None,
            total_clicks=0
        )

        mock_zero_result = Mock()
        mock_zero_result.scalar.return_value = 0

        mock_type_result = Mock()
        mock_type_result.__iter__ = Mock(return_value=iter([]))

        mock_top_result = Mock()
        mock_top_result.__iter__ = Mock(return_value=iter([]))

        mock_filter_result = Mock()
        mock_filter_result.one.return_value = Mock(
            type_filter=0,
            date_filter=0,
            tag_filter=0,
            status_filter=0
        )

        mock_db.execute = AsyncMock(side_effect=[
            mock_total_result,
            mock_zero_result,
            mock_type_result,
            mock_top_result,
            mock_filter_result
        ])

        result = await service.get_search_statistics(mock_db, days=30)

        assert result["total_searches"] == 0
        assert result["unique_users"] == 0
        assert result["zero_result_rate"] == 0


@requires_analytics
class TestSearchAnalyticsServiceSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_returns_same_instance(self):
        """Test dass get_search_analytics_service Singleton zurueckgibt."""
        service1 = get_search_analytics_service()
        service2 = get_search_analytics_service()

        assert service1 is service2

    def test_singleton_is_search_analytics_service(self):
        """Test dass Singleton korrekte Klasse hat."""
        service = get_search_analytics_service()

        assert isinstance(service, SearchAnalyticsService)


@requires_analytics
class TestSearchAnalyticsFilters:
    """Tests fuer Filter-Analyse."""

    @pytest.fixture
    def service(self):
        """Service-Instanz."""
        return SearchAnalyticsService()

    @pytest.fixture
    def mock_db(self):
        """Mock Database Session."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = Mock()
        return db

    @pytest.mark.asyncio
    async def test_filter_flags_document_type(self, service, mock_db):
        """Test Document-Type Filter Flag."""
        filters = SearchFilters(document_type=DocumentType.CONTRACT)

        await service.log_search(
            db=mock_db,
            query="Vertrag",
            search_type=SearchType.FTS,
            total_results=5,
            execution_time_ms=50,
            filters=filters
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.has_document_type_filter is True
        assert added_obj.has_date_filter is False
        assert added_obj.has_tag_filter is False

    @pytest.mark.asyncio
    async def test_filter_flags_date_range(self, service, mock_db):
        """Test Date-Range Filter Flag."""
        filters = SearchFilters(
            date_from=datetime(2024, 1, 1),
            date_to=datetime(2024, 12, 31)
        )

        await service.log_search(
            db=mock_db,
            query="Test",
            search_type=SearchType.HYBRID,
            total_results=10,
            execution_time_ms=100,
            filters=filters
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.has_date_filter is True
        assert added_obj.has_document_type_filter is False

    @pytest.mark.asyncio
    async def test_filter_flags_tags(self, service, mock_db):
        """Test Tags Filter Flag."""
        filters = SearchFilters(tags=["Wichtig", "Archiv"])

        await service.log_search(
            db=mock_db,
            query="Dokument",
            search_type=SearchType.SEMANTIC,
            total_results=3,
            execution_time_ms=200,
            filters=filters
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.has_tag_filter is True
        assert "tags" in added_obj.filters_used
        assert added_obj.filters_used["tags"] == ["Wichtig", "Archiv"]

    @pytest.mark.asyncio
    async def test_filter_flags_status(self, service, mock_db):
        """Test Status Filter Flag."""
        filters = SearchFilters(status=ProcessingStatus.COMPLETED)

        await service.log_search(
            db=mock_db,
            query="Fertig",
            search_type=SearchType.FTS,
            total_results=20,
            execution_time_ms=30,
            filters=filters
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.has_status_filter is True

    @pytest.mark.asyncio
    async def test_all_filters_combined(self, service, mock_db):
        """Test alle Filter kombiniert."""
        filters = SearchFilters(
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            date_from=datetime(2024, 1, 1),
            tags=["Finanzen"]
        )

        await service.log_search(
            db=mock_db,
            query="Alles",
            search_type=SearchType.HYBRID,
            total_results=1,
            execution_time_ms=250,
            filters=filters
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.has_document_type_filter is True
        assert added_obj.has_status_filter is True
        assert added_obj.has_date_filter is True
        assert added_obj.has_tag_filter is True


@requires_analytics
class TestSearchAnalyticsGermanText:
    """Tests fuer deutsche Texte in Analytics."""

    @pytest.fixture
    def service(self):
        """Service-Instanz."""
        return SearchAnalyticsService()

    @pytest.fixture
    def mock_db(self):
        """Mock Database Session."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = Mock()
        return db

    @pytest.mark.asyncio
    async def test_german_umlauts_in_query(self, service, mock_db):
        """Test Umlaute in Suchanfrage."""
        await service.log_search(
            db=mock_db,
            query="Überweisung für Büroausstattung",
            search_type=SearchType.HYBRID,
            total_results=5,
            execution_time_ms=100
        )

        added_obj = mock_db.add.call_args[0][0]
        assert "Ü" in added_obj.search_query
        assert "ü" in added_obj.search_query

    @pytest.mark.asyncio
    async def test_german_eszett_in_query(self, service, mock_db):
        """Test ß in Suchanfrage."""
        await service.log_search(
            db=mock_db,
            query="Straße Großhandel",
            search_type=SearchType.FTS,
            total_results=3,
            execution_time_ms=50
        )

        added_obj = mock_db.add.call_args[0][0]
        assert "ß" in added_obj.search_query


@requires_analytics
class TestIPAnonymization:
    """Dedizierte Tests fuer IP-Anonymisierung."""

    @pytest.fixture
    def service(self):
        """Service-Instanz."""
        return SearchAnalyticsService()

    def test_anonymize_ip_ipv4_standard(self, service):
        """Test IPv4-Anonymisierung Standard."""
        result = service._anonymize_ip("192.168.1.100")
        assert result == "192.168.0.0"

    def test_anonymize_ip_ipv6_full(self, service):
        """Test IPv6-Anonymisierung mit vollstaendiger Adresse."""
        result = service._anonymize_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert result == "2001:0db8:85a3::"

    def test_anonymize_ip_ipv6_compressed(self, service):
        """Test IPv6-Anonymisierung mit komprimierter Adresse."""
        result = service._anonymize_ip("2001:db8:85a3::8a2e:370:7334")
        assert result == "2001:0db8:85a3::"

    def test_anonymize_ip_ipv6_localhost(self, service):
        """Test IPv6-Anonymisierung mit localhost."""
        result = service._anonymize_ip("::1")
        assert result == "0000:0000:0000::"

    def test_anonymize_ip_none(self, service):
        """Test Anonymisierung mit None."""
        result = service._anonymize_ip(None)
        assert result is None

    def test_anonymize_ip_empty_string(self, service):
        """Test Anonymisierung mit leerem String."""
        result = service._anonymize_ip("")
        assert result is None

    def test_anonymize_ip_invalid_format(self, service):
        """Test Anonymisierung mit ungueltigem Format."""
        result = service._anonymize_ip("not-an-ip")
        assert result is None

    def test_anonymize_ip_partial_ipv4(self, service):
        """Test Anonymisierung mit unvollstaendiger IPv4."""
        result = service._anonymize_ip("192.168.1")
        assert result is None
