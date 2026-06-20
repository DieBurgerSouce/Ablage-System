# -*- coding: utf-8 -*-
"""Unit tests for Knowledge Graph Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from app.services.knowledge_graph.graph_service import (
    KnowledgeGraphService,
    GraphNode,
    GraphEdge,
    GraphData,
    PathData,
    Community,
)
from app.db.models import BusinessEntity, Document, InvoiceTracking, DocumentEntityLink


# =============================================================================
# Entity Graph Tests
# =============================================================================


@pytest.mark.asyncio
async def test_entity_graph_basic():
    """Knowledge Graph sollte Graph um Entity korrekt aufbauen."""
    mock_db = AsyncMock()
    company_id = uuid4()
    entity_id = uuid4()

    # Mock Entity
    mock_entity = MagicMock(spec=BusinessEntity)
    mock_entity.id = entity_id
    mock_entity.company_id = company_id
    mock_entity.name = "Test GmbH"
    mock_entity.entity_type = "customer"
    mock_entity.risk_score = 50.0

    mock_db.get.return_value = mock_entity

    # Mock DocumentEntityLinks (2 Dokumente)
    doc_id_1 = uuid4()
    doc_id_2 = uuid4()
    link1 = MagicMock(spec=DocumentEntityLink)
    link1.entity_id = entity_id
    link1.document_id = doc_id_1
    link1.confidence = 0.95

    link2 = MagicMock(spec=DocumentEntityLink)
    link2.entity_id = entity_id
    link2.document_id = doc_id_2
    link2.confidence = 0.88

    doc_links_result = MagicMock()
    doc_links_result.scalars.return_value.all.return_value = [link1, link2]

    # Mock Documents
    mock_doc_1 = MagicMock(spec=Document)
    mock_doc_1.id = doc_id_1
    mock_doc_1.company_id = company_id
    mock_doc_1.filename = "rechnung.pdf"
    mock_doc_1.document_type = "invoice"
    mock_doc_1.status = "completed"

    mock_doc_2 = MagicMock(spec=Document)
    mock_doc_2.id = doc_id_2
    mock_doc_2.company_id = company_id
    mock_doc_2.filename = "lieferschein.pdf"
    mock_doc_2.document_type = "delivery_note"
    mock_doc_2.status = "completed"

    # Mock Invoices (empty)
    invoices_result = MagicMock()
    invoices_result.scalars.return_value.all.return_value = []

    # Mock Bank Transactions (empty)
    transactions_result = MagicMock()
    transactions_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        doc_links_result,
        invoices_result,
        transactions_result,
    ]

    # get() calls für Documents
    mock_db.get.side_effect = [
        mock_entity,  # Initial entity
        mock_doc_1,   # First document
        mock_doc_2,   # Second document
    ]

    service = KnowledgeGraphService()
    result = await service.get_entity_graph(entity_id, depth=1, company_id=company_id, db=mock_db)

    assert isinstance(result, GraphData)
    assert len(result.nodes) >= 3  # Entity + 2 Documents
    assert len(result.edges) >= 2  # 2 CONTAINS_DOCUMENT edges

    # Check Entity Node
    entity_node = next((n for n in result.nodes if "entity_" in n.id), None)
    assert entity_node is not None
    assert entity_node.label == "Test GmbH"
    assert entity_node.type == "entity"

    # Check Stats
    assert result.stats["node_count"] >= 3
    assert result.stats["edge_count"] >= 2


@pytest.mark.asyncio
async def test_entity_graph_depth_limit():
    """Knowledge Graph sollte Depth-Limit respektieren."""
    mock_db = AsyncMock()
    company_id = uuid4()
    entity_id = uuid4()

    mock_entity = MagicMock(spec=BusinessEntity)
    mock_entity.id = entity_id
    mock_entity.company_id = company_id
    mock_entity.name = "Test GmbH"
    mock_entity.entity_type = "customer"
    mock_entity.risk_score = 50.0

    mock_db.get.return_value = mock_entity

    # Mock empty results
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = empty_result

    service = KnowledgeGraphService()

    # Test Depth 0 -> sollte auf 1 erhöht werden
    result = await service.get_entity_graph(entity_id, depth=0, company_id=company_id, db=mock_db)
    assert result.stats["depth"] >= 1

    # Test Depth 5 -> sollte auf 3 begrenzt werden
    mock_db.reset_mock()
    mock_db.get.return_value = mock_entity
    mock_db.execute.return_value = empty_result

    result = await service.get_entity_graph(entity_id, depth=5, company_id=company_id, db=mock_db)
    assert result.stats["depth"] <= 3


@pytest.mark.asyncio
async def test_entity_graph_invalid_company():
    """Knowledge Graph sollte leeren Graph returnen für falsche Company."""
    mock_db = AsyncMock()
    company_id = uuid4()
    wrong_company_id = uuid4()
    entity_id = uuid4()

    mock_entity = MagicMock(spec=BusinessEntity)
    mock_entity.id = entity_id
    mock_entity.company_id = wrong_company_id  # Falsche Company
    mock_entity.name = "Test GmbH"

    mock_db.get.return_value = mock_entity

    service = KnowledgeGraphService()
    result = await service.get_entity_graph(entity_id, depth=1, company_id=company_id, db=mock_db)

    # Sollte leeren Graph returnen
    assert len(result.nodes) == 0
    assert len(result.edges) == 0


# =============================================================================
# Explore Tests
# =============================================================================


@pytest.mark.asyncio
async def test_explore_search():
    """Knowledge Graph Explore sollte Entities finden."""
    mock_db = AsyncMock()
    company_id = uuid4()
    query = "Mueller"

    # Mock gefundene Entities
    entity_id_1 = uuid4()
    entity_id_2 = uuid4()

    entity1 = MagicMock(spec=BusinessEntity)
    entity1.id = entity_id_1
    entity1.name = "Mueller GmbH"
    entity1.entity_type = "customer"
    entity1.risk_score = 30.0

    entity2 = MagicMock(spec=BusinessEntity)
    entity2.id = entity_id_2
    entity2.name = "Mueller & Partner"
    entity2.entity_type = "supplier"
    entity2.risk_score = 45.0

    entities_result = MagicMock()
    entities_result.scalars.return_value.all.return_value = [entity1, entity2]

    # Mock DocumentEntityLinks (1 pro Entity)
    doc_id_1 = uuid4()
    doc_id_2 = uuid4()

    link1 = MagicMock(spec=DocumentEntityLink)
    link1.entity_id = entity_id_1
    link1.document_id = doc_id_1
    link1.confidence = 0.95

    link2 = MagicMock(spec=DocumentEntityLink)
    link2.entity_id = entity_id_2
    link2.document_id = doc_id_2
    link2.confidence = 0.88

    doc_links_result_1 = MagicMock()
    doc_links_result_1.scalars.return_value.all.return_value = [link1]

    doc_links_result_2 = MagicMock()
    doc_links_result_2.scalars.return_value.all.return_value = [link2]

    # Mock Documents
    mock_doc_1 = MagicMock(spec=Document)
    mock_doc_1.id = doc_id_1
    mock_doc_1.company_id = company_id
    mock_doc_1.filename = "rechnung1.pdf"
    mock_doc_1.document_type = "invoice"

    mock_doc_2 = MagicMock(spec=Document)
    mock_doc_2.id = doc_id_2
    mock_doc_2.company_id = company_id
    mock_doc_2.filename = "rechnung2.pdf"
    mock_doc_2.document_type = "invoice"

    mock_db.execute.side_effect = [
        entities_result,
        doc_links_result_1,
        doc_links_result_2,
    ]

    mock_db.get.side_effect = [mock_doc_1, mock_doc_2]

    service = KnowledgeGraphService()
    result = await service.explore(query, company_id, mock_db)

    assert isinstance(result, GraphData)
    assert len(result.nodes) >= 4  # 2 Entities + 2 Docs
    assert len(result.edges) >= 2  # 2 CONTAINS_DOCUMENT edges
    assert result.stats["query"] == query

    # Check Entity Nodes
    entity_nodes = [n for n in result.nodes if n.type == "entity"]
    assert len(entity_nodes) == 2
    assert any("Mueller GmbH" in n.label for n in entity_nodes)


# =============================================================================
# Shortest Path Tests
# =============================================================================


@pytest.mark.asyncio
async def test_shortest_path_found():
    """Knowledge Graph sollte kürzesten Pfad zwischen Entities finden."""
    mock_db = AsyncMock()
    company_id = uuid4()
    from_id = uuid4()
    to_id = uuid4()
    doc_id = uuid4()

    # Mock Entities
    from_entity = MagicMock(spec=BusinessEntity)
    from_entity.id = from_id
    from_entity.company_id = company_id
    from_entity.name = "Mueller GmbH"

    to_entity = MagicMock(spec=BusinessEntity)
    to_entity.id = to_id
    to_entity.company_id = company_id
    to_entity.name = "Schmitt AG"

    mock_document = MagicMock(spec=Document)
    mock_document.id = doc_id
    mock_document.filename = "shared.pdf"

    # get_shortest_path nutzt zuerst _bfs_shortest_path (BFS ueber
    # DocumentEntityLinks). BFS-Ablauf fuer den 2-Hop-Pfad from -> doc -> to:
    #   execute #1: from-Entity -> Dokument-Links (document_id == doc_id)
    #   execute #2: doc-Dokument -> Entity-Links (enthaelt to_id -> Treffer)
    # Danach _build_path_data([from, doc, to]) -> 3x db.get.
    from_doc_links = MagicMock()
    from_doc_links.scalars.return_value.all.return_value = [doc_id]

    doc_entity_links = MagicMock()
    doc_entity_links.scalars.return_value.all.return_value = [to_id]

    # 2 initiale get() (Existenz-/Company-Pruefung) + 3 get() in _build_path_data
    mock_db.get.side_effect = [
        from_entity,  # get_shortest_path: from_entity
        to_entity,    # get_shortest_path: to_entity
        from_entity,  # _build_path_data: i=0 Entity
        mock_document,  # _build_path_data: i=1 Document
        to_entity,    # _build_path_data: i=2 Entity
    ]
    mock_db.execute.side_effect = [from_doc_links, doc_entity_links]

    service = KnowledgeGraphService()
    result = await service.get_shortest_path(from_id, to_id, company_id, mock_db)

    assert result is not None
    assert isinstance(result, PathData)
    assert result.length == 2  # Entity -> Doc -> Entity
    assert len(result.path) == 3
    assert len(result.nodes) == 3
    assert len(result.edges) == 2


@pytest.mark.asyncio
async def test_shortest_path_not_found():
    """Knowledge Graph sollte None returnen wenn kein Pfad existiert."""
    mock_db = AsyncMock()
    company_id = uuid4()
    from_id = uuid4()
    to_id = uuid4()

    # Mock Entities
    from_entity = MagicMock(spec=BusinessEntity)
    from_entity.id = from_id
    from_entity.company_id = company_id
    from_entity.name = "Mueller GmbH"

    to_entity = MagicMock(spec=BusinessEntity)
    to_entity.id = to_id
    to_entity.company_id = company_id
    to_entity.name = "Schmitt AG"

    # get_shortest_path: zuerst BFS (execute #1/#2), dann direkter Fallback
    # (execute #3/#4). Kein gemeinsames Dokument -> kein Pfad.
    doc_a = uuid4()
    doc_b = uuid4()

    # BFS execute #1: from-Entity -> Dokument-Links
    bfs_from_doc_links = MagicMock()
    bfs_from_doc_links.scalars.return_value.all.return_value = [doc_a]
    # BFS execute #2: doc_a -> Entity-Links (LEER -> kein to_id-Treffer)
    bfs_doc_entity_links = MagicMock()
    bfs_doc_entity_links.scalars.return_value.all.return_value = []

    # Fallback execute #3/#4: disjunkte Dokumentmengen -> common_docs leer
    from_docs_result = MagicMock()
    from_docs_result.scalars.return_value.all.return_value = [doc_a]
    to_docs_result = MagicMock()
    to_docs_result.scalars.return_value.all.return_value = [doc_b]  # Anderes Doc

    mock_db.get.side_effect = [from_entity, to_entity]
    mock_db.execute.side_effect = [
        bfs_from_doc_links,
        bfs_doc_entity_links,
        from_docs_result,
        to_docs_result,
    ]

    service = KnowledgeGraphService()
    result = await service.get_shortest_path(from_id, to_id, company_id, mock_db)

    assert result is None


# =============================================================================
# Community Detection Tests
# =============================================================================


@pytest.mark.asyncio
async def test_community_detection():
    """Knowledge Graph sollte Communities gruppieren."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock DocumentEntityLinks (3 Entities + 1 gemeinsames Dokument)
    doc_id = uuid4()
    entity_id_1 = uuid4()
    entity_id_2 = uuid4()
    entity_id_3 = uuid4()

    link1 = MagicMock(spec=DocumentEntityLink)
    link1.document_id = doc_id
    link1.entity_id = entity_id_1

    link2 = MagicMock(spec=DocumentEntityLink)
    link2.document_id = doc_id
    link2.entity_id = entity_id_2

    link3 = MagicMock(spec=DocumentEntityLink)
    link3.document_id = doc_id
    link3.entity_id = entity_id_3

    doc_links_result = MagicMock()
    doc_links_result.scalars.return_value.all.return_value = [link1, link2, link3]

    # Mock Document
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.company_id = company_id
    mock_doc.filename = "shared_contract.pdf"

    mock_db.execute.return_value = doc_links_result
    mock_db.get.return_value = mock_doc

    service = KnowledgeGraphService()
    result = await service.get_communities(company_id, mock_db)

    assert isinstance(result, list)
    assert len(result) > 0

    # Sollte Community mit 3 Entities finden
    community = result[0]
    assert isinstance(community, Community)
    assert community.node_count == 4  # 3 Entities + 1 Doc
    assert community.edge_count == 3
    assert len(community.member_ids) == 3


# =============================================================================
# Node & Edge Type Tests
# =============================================================================


@pytest.mark.asyncio
async def test_node_types():
    """Knowledge Graph sollte korrekte Node-Typen verwenden."""
    mock_db = AsyncMock()
    company_id = uuid4()
    entity_id = uuid4()

    mock_entity = MagicMock(spec=BusinessEntity)
    mock_entity.id = entity_id
    mock_entity.company_id = company_id
    mock_entity.name = "Test GmbH"
    mock_entity.entity_type = "customer"
    mock_entity.risk_score = 50.0

    # Mock Document Link
    doc_id = uuid4()
    link = MagicMock(spec=DocumentEntityLink)
    link.entity_id = entity_id
    link.document_id = doc_id
    link.confidence = 0.95

    doc_links_result = MagicMock()
    doc_links_result.scalars.return_value.all.return_value = [link]

    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.company_id = company_id
    mock_doc.filename = "test.pdf"
    mock_doc.document_type = "invoice"
    mock_doc.status = "completed"

    # Mock Invoice
    invoice_id = uuid4()
    mock_invoice = MagicMock(spec=InvoiceTracking)
    mock_invoice.id = invoice_id
    mock_invoice.invoice_number = "RE-001"
    mock_invoice.status = MagicMock(value="open")
    mock_invoice.total_amount = 1000.0

    invoices_result = MagicMock()
    invoices_result.scalars.return_value.all.return_value = [mock_invoice]

    # Mock Bank Transactions (empty)
    transactions_result = MagicMock()
    transactions_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        doc_links_result,
        invoices_result,
        transactions_result,
    ]

    mock_db.get.side_effect = [mock_entity, mock_doc]

    service = KnowledgeGraphService()
    result = await service.get_entity_graph(entity_id, depth=1, company_id=company_id, db=mock_db)

    # Check Node Types
    node_types = {n.type for n in result.nodes}
    assert "entity" in node_types
    assert "document" in node_types
    assert "invoice" in node_types


@pytest.mark.asyncio
async def test_edge_types():
    """Knowledge Graph sollte korrekte Edge-Typen verwenden."""
    mock_db = AsyncMock()
    company_id = uuid4()
    entity_id = uuid4()

    mock_entity = MagicMock(spec=BusinessEntity)
    mock_entity.id = entity_id
    mock_entity.company_id = company_id
    mock_entity.name = "Test GmbH"
    mock_entity.entity_type = "customer"

    # Mock Document Link
    doc_id = uuid4()
    link = MagicMock(spec=DocumentEntityLink)
    link.entity_id = entity_id
    link.document_id = doc_id
    link.confidence = 0.95

    doc_links_result = MagicMock()
    doc_links_result.scalars.return_value.all.return_value = [link]

    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.company_id = company_id
    mock_doc.filename = "test.pdf"

    # Mock Invoice
    invoice_id = uuid4()
    mock_invoice = MagicMock(spec=InvoiceTracking)
    mock_invoice.id = invoice_id
    mock_invoice.invoice_number = "RE-001"
    mock_invoice.status = MagicMock(value="open")
    mock_invoice.total_amount = 1000.0

    invoices_result = MagicMock()
    invoices_result.scalars.return_value.all.return_value = [mock_invoice]

    transactions_result = MagicMock()
    transactions_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        doc_links_result,
        invoices_result,
        transactions_result,
    ]

    mock_db.get.side_effect = [mock_entity, mock_doc]

    service = KnowledgeGraphService()
    result = await service.get_entity_graph(entity_id, depth=1, company_id=company_id, db=mock_db)

    # Check Edge Types
    edge_labels = {e.label for e in result.edges}
    assert "CONTAINS_DOCUMENT" in edge_labels
    assert "ISSUED_TO" in edge_labels
