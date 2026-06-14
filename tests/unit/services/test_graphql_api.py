# -*- coding: utf-8 -*-
"""Unit tests for GraphQL-ähnliche API Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.api.v1.graphql_api import (
    GraphQLQueryRequest,
    GraphQLQueryResponse,
    GraphQLSchemaResponse,
    QueryBuilder,
    GRAPHQL_SCHEMAS,
)


# ============================================================================
# Query Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_query_entity_basic():
    """Test GraphQL query with basic field selection."""
    # Arrange
    request = GraphQLQueryRequest(
        entity_type="document",
        fields=["id", "filename", "status"],
        limit=10,
    )

    company_id = uuid4()
    mock_db = AsyncMock()

    # Mock query result
    mock_doc = MagicMock()
    mock_doc.id = uuid4()
    mock_doc.filename = "test.pdf"
    mock_doc.status = "completed"
    mock_doc.company_id = company_id

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_doc]
    mock_result.scalars.return_value = mock_scalars

    # Mock count query
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    # Setup execute to return different results for count vs data query
    execute_calls = [mock_count_result, mock_result]
    mock_db.execute = AsyncMock(side_effect=execute_calls)

    # Act
    items, total_count = await QueryBuilder.build_query(
        body=request,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(items) == 1
    assert total_count == 1
    assert items[0].filename == "test.pdf"


@pytest.mark.asyncio
async def test_query_entity_filter_eq():
    """Test GraphQL query with equality filter."""
    # Arrange
    request = GraphQLQueryRequest(
        entity_type="document",
        fields=["id", "status"],
        filters={"status": "completed"},
        limit=10,
    )

    company_id = uuid4()
    mock_db = AsyncMock()

    # Mock query result
    mock_doc = MagicMock()
    mock_doc.id = uuid4()
    mock_doc.status = "completed"

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_doc]
    mock_result.scalars.return_value = mock_scalars

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    execute_calls = [mock_count_result, mock_result]
    mock_db.execute = AsyncMock(side_effect=execute_calls)

    # Act
    items, total_count = await QueryBuilder.build_query(
        body=request,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(items) == 1
    assert items[0].status == "completed"


@pytest.mark.asyncio
async def test_query_entity_filter_like():
    """Test GraphQL query with LIKE pattern filter."""
    # Arrange
    request = GraphQLQueryRequest(
        entity_type="entity",
        fields=["id", "name"],
        filters={"name": "%GmbH%"},
        limit=10,
    )

    company_id = uuid4()
    mock_db = AsyncMock()

    # Mock query result
    mock_entity = MagicMock()
    mock_entity.id = uuid4()
    mock_entity.name = "Müller GmbH"

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_entity]
    mock_result.scalars.return_value = mock_scalars

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    execute_calls = [mock_count_result, mock_result]
    mock_db.execute = AsyncMock(side_effect=execute_calls)

    # Act
    items, total_count = await QueryBuilder.build_query(
        body=request,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(items) == 1
    assert "GmbH" in items[0].name


@pytest.mark.asyncio
async def test_query_entity_filter_in():
    """Test GraphQL query with IN list filter."""
    # Arrange
    status_list = ["open", "overdue"]
    request = GraphQLQueryRequest(
        entity_type="invoice",
        fields=["id", "status"],
        filters={"status": status_list},
        limit=10,
    )

    company_id = uuid4()
    mock_db = AsyncMock()

    # Mock query result - 2 invoices
    mock_inv1 = MagicMock()
    mock_inv1.id = uuid4()
    mock_inv1.status = "open"

    mock_inv2 = MagicMock()
    mock_inv2.id = uuid4()
    mock_inv2.status = "overdue"

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_inv1, mock_inv2]
    mock_result.scalars.return_value = mock_scalars

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 2

    execute_calls = [mock_count_result, mock_result]
    mock_db.execute = AsyncMock(side_effect=execute_calls)

    # Act
    items, total_count = await QueryBuilder.build_query(
        body=request,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(items) == 2
    assert total_count == 2
    assert items[0].status in status_list
    assert items[1].status in status_list


@pytest.mark.asyncio
async def test_query_entity_filter_gte_lte():
    """Test GraphQL query with range filter (gte/lte)."""
    # Arrange
    request = GraphQLQueryRequest(
        entity_type="entity",
        fields=["id", "risk_score"],
        filters={"risk_score": {"gte": 50, "lte": 75}},
        limit=10,
    )

    company_id = uuid4()
    mock_db = AsyncMock()

    # Mock query result
    mock_entity = MagicMock()
    mock_entity.id = uuid4()
    mock_entity.risk_score = 60.5

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_entity]
    mock_result.scalars.return_value = mock_scalars

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    execute_calls = [mock_count_result, mock_result]
    mock_db.execute = AsyncMock(side_effect=execute_calls)

    # Act
    items, total_count = await QueryBuilder.build_query(
        body=request,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(items) == 1
    assert 50 <= items[0].risk_score <= 75


def test_query_invalid_entity_type():
    """Test GraphQL query rejects unknown entity types."""
    # Act & Assert
    with pytest.raises(ValueError, match="Ungültiger Entity-Typ"):
        GraphQLQueryRequest(
            entity_type="malicious_type",
            fields=["id"],
            limit=10,
        )


def test_query_invalid_field_name():
    """Test GraphQL query rejects SQL injection in field names."""
    # Arrange - Field mit SQL Injection Versuch
    malicious_fields = [
        "id; DROP TABLE documents;--",
        "id' OR '1'='1",
        "../../../etc/passwd",
        "id\x00null",
    ]

    for bad_field in malicious_fields:
        # Act & Assert
        with pytest.raises(ValueError, match="Ungültiger Feldname"):
            GraphQLQueryRequest(
                entity_type="document",
                fields=["id", bad_field],
                limit=10,
            )


@pytest.mark.asyncio
async def test_schema_discovery():
    """Test GraphQL schema discovery returns available entity types and fields."""
    # Arrange - Schema sollte vordefiniert sein
    assert "document" in GRAPHQL_SCHEMAS
    assert "entity" in GRAPHQL_SCHEMAS
    assert "invoice" in GRAPHQL_SCHEMAS
    assert "alert" in GRAPHQL_SCHEMAS

    # Act
    doc_schema = GRAPHQL_SCHEMAS["document"]

    # Assert
    assert doc_schema.type_name == "Document"
    assert len(doc_schema.fields) > 0

    # Check wichtige Felder
    field_names = [f.name for f in doc_schema.fields]
    assert "id" in field_names
    assert "filename" in field_names
    assert "status" in field_names
    assert "ocr_text" in field_names


@pytest.mark.asyncio
async def test_query_company_isolation():
    """Test GraphQL query auto-injects company_id filter."""
    # Arrange
    request = GraphQLQueryRequest(
        entity_type="document",
        fields=["id", "filename"],
        limit=10,
    )

    company_id = uuid4()
    other_company_id = uuid4()
    mock_db = AsyncMock()

    # Mock nur Dokumente der company_id zurueckgeben
    mock_doc = MagicMock()
    mock_doc.id = uuid4()
    mock_doc.filename = "allowed.pdf"
    mock_doc.company_id = company_id

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_doc]
    mock_result.scalars.return_value = mock_scalars

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    execute_calls = [mock_count_result, mock_result]
    mock_db.execute = AsyncMock(side_effect=execute_calls)

    # Act
    items, total_count = await QueryBuilder.build_query(
        body=request,
        company_id=company_id,
        db=mock_db,
    )

    # Assert - sollte nur die Dokumente der richtigen Company zurueckgeben
    assert len(items) == 1
    assert items[0].company_id == company_id


@pytest.mark.asyncio
async def test_query_pagination():
    """Test GraphQL query pagination with limit/offset."""
    # Arrange
    request = GraphQLQueryRequest(
        entity_type="document",
        fields=["id"],
        limit=5,
        offset=10,
    )

    company_id = uuid4()
    mock_db = AsyncMock()

    # Mock 5 results (page 2)
    mock_docs = []
    for i in range(5):
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_docs.append(mock_doc)

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_docs
    mock_result.scalars.return_value = mock_scalars

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 25  # Total count

    execute_calls = [mock_count_result, mock_result]
    mock_db.execute = AsyncMock(side_effect=execute_calls)

    # Act
    items, total_count = await QueryBuilder.build_query(
        body=request,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(items) == 5
    assert total_count == 25


def test_query_field_projection():
    """Test QueryBuilder projects only requested fields."""
    # Arrange
    mock_item = MagicMock()
    mock_item.id = uuid4()
    mock_item.filename = "test.pdf"
    mock_item.status = "completed"
    mock_item.ocr_text = "Sensitive data"
    mock_item.created_at = datetime.now(timezone.utc)

    requested_fields = ["id", "filename", "status"]

    # Act
    projected = QueryBuilder._project_fields(mock_item, requested_fields)

    # Assert
    assert set(projected.keys()) == set(requested_fields)
    assert "ocr_text" not in projected  # Nicht angefordert
    assert "created_at" not in projected
    assert projected["filename"] == "test.pdf"


def test_query_order_by_validation():
    """Test GraphQL query validates order_by field."""
    # Valid order_by
    request = GraphQLQueryRequest(
        entity_type="document",
        fields=["id"],
        order_by="created_at",
        order_desc=True,
        limit=10,
    )
    assert request.order_by == "created_at"

    # Invalid order_by with SQL injection
    with pytest.raises(ValueError, match="Ungültiges Sortierfeld"):
        GraphQLQueryRequest(
            entity_type="document",
            fields=["id"],
            order_by="created_at; DROP TABLE--",
            limit=10,
        )
