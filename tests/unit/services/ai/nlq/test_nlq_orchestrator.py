# -*- coding: utf-8 -*-
"""
Unit-Tests für NLQ 2.0 Orchestrator.

Testet:
- Query Cache (hit/miss)
- SQL Generation und Sanitization
- Query Execution
- Result Formatting
- Visualization Recommendations
- Feedback Submission

Feinpoliert und durchdacht - NLQ Tests.
"""

import pytest
import time
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from app.services.ai.nlq.nlq_orchestrator import (
    NLQOrchestrator,
    NLQResponse,
)
from app.services.ai.nlq.query_cache import (
    QueryCache,
    CachedResult,
)
from app.services.ai.nlq.result_formatter import (
    ResultFormatter,
    FormattedResult,
)
from app.services.ai.nlq.schema_introspector import SchemaIntrospector
from app.services.ai.nlq.sql_generator import SQLGenerationResult
from app.services.ai.nlq.sql_sanitizer import SanitizationResult


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_engine() -> AsyncMock:
    """Create mock SQLAlchemy engine."""
    engine = AsyncMock()
    return engine


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.ping = AsyncMock()
    return redis


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_user_id() -> UUID:
    """Provide sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_company_id() -> UUID:
    """Provide sample company UUID."""
    return uuid4()


@pytest.fixture
def sample_query_log_id() -> UUID:
    """Provide sample query log UUID."""
    return uuid4()


# ========================= QueryCache Tests =========================


class TestQueryCache:
    """Tests für Query Cache Service."""

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_redis):
        """Cache Miss sollte None zurückgeben."""
        # Arrange
        cache = QueryCache(mock_redis)
        mock_redis.get = AsyncMock(return_value=None)

        # Act
        result = await cache.get_cached("test query", "company-123")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, mock_redis):
        """Cache Roundtrip sollte funktionieren."""
        # Arrange
        cache = QueryCache(mock_redis)

        # Mock Redis setex
        mock_redis.setex = AsyncMock()

        # Mock Redis get (simulates cached data)
        import json
        cached_data = {
            "query_hash": "abc123",
            "natural_query": "Zeige alle Rechnungen",
            "generated_sql": "SELECT * FROM invoices",
            "columns": ["id", "amount"],
            "rows": [[1, 100.0], [2, 200.0]],
            "visualization_type": "table",
            "text_summary": "2 Ergebnisse gefunden",
            "total_rows": 2,
            "confidence": 0.95,
            "cached_at": time.time(),
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        # Act - Set
        await cache.set_cached(
            natural_query="Zeige alle Rechnungen",
            company_id="company-123",
            generated_sql="SELECT * FROM invoices",
            columns=["id", "amount"],
            rows=[(1, 100.0), (2, 200.0)],
            visualization_type="table",
            text_summary="2 Ergebnisse gefunden",
            confidence=0.95,
        )

        # Act - Get
        result = await cache.get_cached("Zeige alle Rechnungen", "company-123")

        # Assert
        assert result is not None
        assert result.natural_query == "Zeige alle Rechnungen"
        assert result.total_rows == 2
        assert len(result.columns) == 2

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, mock_redis):
        """Cache Invalidation sollte funktionieren."""
        # Arrange
        cache = QueryCache(mock_redis)
        mock_redis.delete = AsyncMock(return_value=1)

        # Act
        result = await cache.invalidate_cached("test query", "company-123")

        # Assert
        assert result is True
        mock_redis.delete.assert_called_once()


# ========================= ResultFormatter Tests =========================


class TestResultFormatter:
    """Tests für Result Formatter."""

    def test_result_formatting_kpi(self):
        """KPI-Formatting sollte einzelnen Wert formatieren."""
        # Arrange
        formatter = ResultFormatter()
        columns = ["total_revenue"]
        rows = [(125000.50,)]

        # Act
        result = formatter.format_result(
            query="Gesamtumsatz",
            columns=columns,
            rows=rows,
            viz_type="kpi",
        )

        # Assert
        assert result.visualization_type == "kpi"
        assert result.total_rows == 1
        assert "total_revenue" in result.text_summary
        assert result.visualization_config["type"] == "kpi"
        assert result.visualization_config["value"] == 125000.50

    def test_result_formatting_table(self):
        """Table-Formatting sollte tabellarische Daten formatieren."""
        # Arrange
        formatter = ResultFormatter()
        columns = ["customer_name", "invoice_amount", "invoice_date"]
        rows = [
            ("Test GmbH", 1000.0, "2024-01-15"),
            ("Mueller AG", 2500.0, "2024-01-20"),
        ]

        # Act
        result = formatter.format_result(
            query="Alle Rechnungen",
            columns=columns,
            rows=rows,
            viz_type="table",
        )

        # Assert
        assert result.visualization_type == "table"
        assert result.total_rows == 2
        assert len(result.data) == 2
        assert result.data[0]["customer_name"] == "Test GmbH"
        assert result.visualization_config["sortable"] is True

    def test_result_formatting_empty_results(self):
        """Leere Ergebnisse sollten korrekt behandelt werden."""
        # Arrange
        formatter = ResultFormatter()

        # Act
        result = formatter.format_result(
            query="Nichtexistente Daten",
            columns=[],
            rows=[],
            viz_type="table",
        )

        # Assert
        assert result.total_rows == 0
        assert "Keine Ergebnisse" in result.text_summary


# ========================= NLQOrchestrator Tests =========================


class TestNLQOrchestrator:
    """Tests für NLQ Orchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_cache_hit(
        self, mock_engine, mock_redis, mock_db_session, sample_user_id, sample_company_id
    ):
        """Cache Hit sollte cached result zurückgeben."""
        # Arrange
        orchestrator = NLQOrchestrator(mock_engine, mock_redis)

        # Mock Query Log
        mock_log = Mock()
        mock_log.id = uuid4()
        mock_db_session.add = Mock()
        mock_db_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', mock_log.id))

        # Mock cached result
        import json
        cached_data = {
            "query_hash": "abc123",
            "natural_query": "Zeige Umsatz",
            "generated_sql": "SELECT SUM(amount) FROM invoices",
            "columns": ["total"],
            "rows": [[125000.0]],
            "visualization_type": "kpi",
            "text_summary": "Umsatz: 125,000.00",
            "total_rows": 1,
            "confidence": 0.95,
            "cached_at": time.time(),
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        # Act
        result = await orchestrator.query(
            natural_query="Zeige Umsatz",
            user_id=sample_user_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result.was_cached is True
        assert result.natural_query == "Zeige Umsatz"
        assert result.result.total_rows == 1

    @pytest.mark.asyncio
    async def test_orchestrator_cache_miss(
        self, mock_engine, mock_redis, mock_db_session, sample_user_id, sample_company_id
    ):
        """Cache Miss sollte neue SQL generieren und cachen."""
        # Arrange
        orchestrator = NLQOrchestrator(mock_engine, mock_redis)

        # Mock cache miss
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        # Mock schema introspection
        with patch.object(orchestrator.introspector, 'get_schema_context') as mock_schema:
            mock_schema.return_value = {"tables": []}

            # Mock SQL generation
            with patch.object(orchestrator.generator, 'generate_sql') as mock_gen:
                mock_gen.return_value = SQLGenerationResult(
                    sql="SELECT COUNT(*) as total FROM invoices WHERE company_id = :company_id",
                    confidence=0.92,
                    explanation="Count all invoices",
                    model_used="qwen3:8b",
                    generation_time_ms=12,
                )

                # Mock sanitization
                with patch.object(orchestrator.sanitizer, 'sanitize') as mock_san:
                    mock_san.return_value = SanitizationResult(
                        safe=True,
                        sanitized_sql="SELECT COUNT(*) as total FROM invoices WHERE company_id = :company_id",
                        original_sql="SELECT COUNT(*) as total FROM invoices WHERE company_id = :company_id",
                        violations=[],
                    )

                    # Mock query execution
                    # `engine.begin()` muss SYNCHRON einen Async-Context-Manager
                    # liefern (Code: `async with self.engine.begin() as conn`),
                    # daher begin = MagicMock (kein AsyncMock).
                    mock_conn = AsyncMock()
                    mock_result = Mock()
                    mock_result.fetchall = Mock(return_value=[(42,)])
                    mock_result.keys = Mock(return_value=["total"])
                    mock_conn.execute = AsyncMock(return_value=mock_result)
                    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
                    mock_conn.__aexit__ = AsyncMock(return_value=None)
                    mock_engine.begin = MagicMock(return_value=mock_conn)

                    # Mock Query Log
                    mock_log = Mock()
                    mock_log.id = uuid4()
                    mock_db_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', mock_log.id))

                    # Act
                    result = await orchestrator.query(
                        natural_query="Wieviele Rechnungen gibt es?",
                        user_id=sample_user_id,
                        company_id=sample_company_id,
                        db=mock_db_session,
                    )

                    # Assert
                    assert result.was_cached is False
                    assert result.confidence == 0.92
                    mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestrator_invalid_sql(
        self, mock_engine, mock_redis, mock_db_session, sample_user_id, sample_company_id
    ):
        """Unsafe SQL sollte BusinessLogicError werfen."""
        # Arrange
        orchestrator = NLQOrchestrator(mock_engine, mock_redis)

        # Mock cache miss
        mock_redis.get = AsyncMock(return_value=None)

        # Mock schema introspection
        with patch.object(orchestrator.introspector, 'get_schema_context') as mock_schema:
            mock_schema.return_value = {"tables": []}

            # Mock SQL generation (malicious SQL)
            with patch.object(orchestrator.generator, 'generate_sql') as mock_gen:
                mock_gen.return_value = SQLGenerationResult(
                    sql="DROP TABLE users; --",
                    confidence=0.10,
                    explanation="Malicious query",
                    model_used="qwen3:8b",
                    generation_time_ms=8,
                )

                # Mock sanitization (reject)
                with patch.object(orchestrator.sanitizer, 'sanitize') as mock_san:
                    mock_san.return_value = SanitizationResult(
                        safe=False,
                        sanitized_sql="",
                        original_sql="DROP TABLE users; --",
                        violations=["DROP statement not allowed"],
                    )

                    # Act & Assert
                    from app.core.exceptions import BusinessLogicError
                    with pytest.raises(BusinessLogicError, match="SQL-Sicherheitsprüfung fehlgeschlagen"):
                        await orchestrator.query(
                            natural_query="Lösche alle Benutzer",
                            user_id=sample_user_id,
                            company_id=sample_company_id,
                            db=mock_db_session,
                        )

    @pytest.mark.asyncio
    async def test_visualization_recommendation_bar(self):
        """Bar Chart sollte für Vergleiche empfohlen werden."""
        # Arrange
        from app.services.ai.nlq.visualization_recommender import VisualizationRecommender
        recommender = VisualizationRecommender()

        # Act
        viz_type = recommender.recommend(
            query="Umsatz pro Monat",
            columns=["month", "revenue"],
            row_count=12,
        )

        # Assert
        assert viz_type in ["bar", "line"]  # Both valid for time series

    @pytest.mark.asyncio
    async def test_visualization_recommendation_line(self):
        """Line Chart sollte für Zeitreihen empfohlen werden."""
        # Arrange
        from app.services.ai.nlq.visualization_recommender import VisualizationRecommender
        recommender = VisualizationRecommender()

        # Act
        viz_type = recommender.recommend(
            query="Entwicklung des Umsatzes über Zeit",
            columns=["date", "total_revenue"],
            row_count=30,
        )

        # Assert
        assert viz_type == "line"

    @pytest.mark.asyncio
    async def test_feedback_submission(
        self, mock_engine, mock_redis, mock_db_session, sample_query_log_id
    ):
        """Feedback-Submission sollte Query Log updaten."""
        # Arrange
        orchestrator = NLQOrchestrator(mock_engine, mock_redis)

        # Mock Query Log
        mock_log = Mock()
        mock_log.id = sample_query_log_id
        mock_log.feedback_rating = None
        mock_log.feedback_comment = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_log)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await orchestrator.submit_feedback(
            query_log_id=sample_query_log_id,
            rating=5,
            comment="Sehr hilfreich!",
            db=mock_db_session,
        )

        # Assert
        assert mock_log.feedback_rating == 5
        assert mock_log.feedback_comment == "Sehr hilfreich!"
        mock_db_session.commit.assert_called_once()
