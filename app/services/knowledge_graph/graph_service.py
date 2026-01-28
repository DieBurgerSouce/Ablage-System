"""
Knowledge Graph Service

Baut Entity-Relationship Graph aus existierenden Daten:
- Entities (BusinessEntity)
- Documents
- Invoices
- Bank Transactions

Nutzt Adjacency-List Pattern (kein AGE erforderlich).

Feinpoliert und durchdacht - Enterprise Knowledge Graph.
"""

from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Tuple
from uuid import UUID
from collections import defaultdict, deque

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
    BankTransaction,
    DocumentEntityLink,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class GraphNode:
    """Node im Knowledge Graph."""

    id: str  # UUID als String
    label: str  # Anzeigename
    type: str  # entity, document, invoice, bank_account, transaction
    properties: Dict[str, str]  # Zusaetzliche Metadaten

    def to_dict(self) -> Dict[str, any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "properties": self.properties,
        }


@dataclass
class GraphEdge:
    """Edge im Knowledge Graph."""

    source: str  # Source Node ID
    target: str  # Target Node ID
    label: str  # Relationship Type
    properties: Dict[str, str]  # Zusaetzliche Metadaten

    def to_dict(self) -> Dict[str, any]:
        """Konvertiert zu Dictionary."""
        return {
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "properties": self.properties,
        }


@dataclass
class GraphData:
    """Kompletter Graph mit Nodes und Edges."""

    nodes: List[GraphNode]
    edges: List[GraphEdge]
    stats: Dict[str, int]

    def to_dict(self) -> Dict[str, any]:
        """Konvertiert zu Dictionary."""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "stats": self.stats,
        }


@dataclass
class PathData:
    """Kuerzester Pfad zwischen zwei Nodes."""

    path: List[str]  # Liste von Node IDs
    length: int  # Pfad-Laenge
    nodes: List[GraphNode]  # Nodes im Pfad
    edges: List[GraphEdge]  # Edges im Pfad

    def to_dict(self) -> Dict[str, any]:
        """Konvertiert zu Dictionary."""
        return {
            "path": self.path,
            "length": self.length,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }


@dataclass
class Community:
    """Community/Cluster von zusammenhaengenden Nodes."""

    id: str
    name: str
    node_count: int
    edge_count: int
    central_node: Optional[GraphNode]
    member_ids: List[str]

    def to_dict(self) -> Dict[str, any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "central_node": self.central_node.to_dict() if self.central_node else None,
            "member_ids": self.member_ids,
        }


# =============================================================================
# Knowledge Graph Service
# =============================================================================


class KnowledgeGraphService:
    """
    Knowledge Graph Service.

    Baut Graph aus existierenden Beziehungen:
    - Documents ← DocumentEntityLink → Entities
    - Invoices → Documents → Entities
    - BankTransactions → Entities
    """

    def __init__(self) -> None:
        """Initialisiert Service."""
        pass

    async def get_entity_graph(
        self,
        entity_id: UUID,
        depth: int,
        company_id: UUID,
        db: AsyncSession,
    ) -> GraphData:
        """
        Holt Graph um Entity herum.

        Args:
            entity_id: Start-Entity UUID
            depth: Graph-Tiefe (1-3)
            company_id: Company UUID
            db: Database session

        Returns:
            GraphData mit Nodes und Edges
        """
        logger.info(
            "knowledge_graph.get_entity_graph",
            entity_id=str(entity_id),
            depth=depth,
            company_id=str(company_id),
        )

        # Validiere Depth
        depth = max(1, min(depth, 3))  # Limit auf 1-3

        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []
        visited: Set[str] = set()

        # Start mit Entity
        entity = await db.get(BusinessEntity, entity_id)
        if not entity or entity.company_id != company_id:
            return GraphData(nodes=[], edges=[], stats={})

        # Add Start-Node
        start_node_id = f"entity_{entity_id}"
        nodes[start_node_id] = GraphNode(
            id=start_node_id,
            label=entity.name or "Unbekannt",
            type="entity",
            properties={
                "entity_type": entity.entity_type or "unknown",
                "risk_score": str(entity.risk_score or 0),
            },
        )

        # BFS (Breadth-First Search) fuer Graph-Expansion
        queue: deque[Tuple[str, int]] = deque([(start_node_id, 0)])
        visited.add(start_node_id)

        while queue:
            current_id, current_depth = queue.popleft()

            if current_depth >= depth:
                continue

            # Expandiere Node
            await self._expand_node(
                current_id,
                current_depth,
                company_id,
                nodes,
                edges,
                visited,
                queue,
                db,
            )

        stats = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "depth": depth,
            "entity_count": sum(1 for n in nodes.values() if n.type == "entity"),
            "document_count": sum(1 for n in nodes.values() if n.type == "document"),
        }

        return GraphData(
            nodes=list(nodes.values()),
            edges=edges,
            stats=stats,
        )

    async def _expand_node(
        self,
        node_id: str,
        current_depth: int,
        company_id: UUID,
        nodes: Dict[str, GraphNode],
        edges: List[GraphEdge],
        visited: Set[str],
        queue: deque,
        db: AsyncSession,
    ) -> None:
        """
        Expandiert einen Node (findet angrenzende Nodes).

        Args:
            node_id: Node ID
            current_depth: Aktuelle Tiefe
            company_id: Company UUID
            nodes: Node-Dictionary (wird erweitert)
            edges: Edge-Liste (wird erweitert)
            visited: Besuchte Nodes
            queue: BFS-Queue
            db: Database session
        """
        node_type, node_uuid_str = node_id.split("_", 1)
        node_uuid = UUID(node_uuid_str)

        if node_type == "entity":
            # Finde verknuepfte Dokumente
            doc_links_query = select(DocumentEntityLink).where(
                DocumentEntityLink.entity_id == node_uuid
            )
            doc_links_result = await db.execute(doc_links_query)
            doc_links = doc_links_result.scalars().all()

            for link in doc_links:
                doc_id = f"document_{link.document_id}"
                if doc_id not in visited:
                    # Add Document Node
                    doc = await db.get(Document, link.document_id)
                    if doc and doc.company_id == company_id:
                        nodes[doc_id] = GraphNode(
                            id=doc_id,
                            label=doc.filename or "Dokument",
                            type="document",
                            properties={
                                "document_type": doc.document_type or "unknown",
                                "status": doc.status or "unknown",
                            },
                        )
                        visited.add(doc_id)
                        queue.append((doc_id, current_depth + 1))

                        # Add Edge
                        edges.append(
                            GraphEdge(
                                source=node_id,
                                target=doc_id,
                                label="CONTAINS_DOCUMENT",
                                properties={"confidence": str(link.confidence or 0)},
                            )
                        )

            # Finde verknuepfte Rechnungen
            invoices_query = select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.entity_id == node_uuid,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            invoices_result = await db.execute(invoices_query)
            invoices = invoices_result.scalars().all()

            for invoice in invoices:
                invoice_id = f"invoice_{invoice.id}"
                if invoice_id not in visited:
                    nodes[invoice_id] = GraphNode(
                        id=invoice_id,
                        label=invoice.invoice_number or "Rechnung",
                        type="invoice",
                        properties={
                            "status": invoice.status.value if invoice.status else "unknown",
                            "amount": str(invoice.total_amount or 0),
                        },
                    )
                    visited.add(invoice_id)
                    queue.append((invoice_id, current_depth + 1))

                    edges.append(
                        GraphEdge(
                            source=node_id,
                            target=invoice_id,
                            label="ISSUED_TO",
                            properties={},
                        )
                    )

            # Finde Bank-Transaktionen
            transactions_query = select(BankTransaction).where(
                and_(
                    BankTransaction.linked_entity_id == node_uuid,
                    BankTransaction.company_id == company_id,
                )
            )
            transactions_result = await db.execute(transactions_query)
            transactions = transactions_result.scalars().all()

            for txn in transactions[:10]:  # Limit auf 10 Transaktionen
                txn_id = f"transaction_{txn.id}"
                if txn_id not in visited:
                    nodes[txn_id] = GraphNode(
                        id=txn_id,
                        label=f"{txn.amount} EUR",
                        type="transaction",
                        properties={
                            "purpose": txn.purpose or "",
                            "date": txn.value_date.isoformat() if txn.value_date else "",
                        },
                    )
                    visited.add(txn_id)

                    edges.append(
                        GraphEdge(
                            source=node_id,
                            target=txn_id,
                            label="PAID_VIA",
                            properties={},
                        )
                    )

        elif node_type == "document":
            # Finde verknuepfte Entities
            doc_links_query = select(DocumentEntityLink).where(
                DocumentEntityLink.document_id == node_uuid
            )
            doc_links_result = await db.execute(doc_links_query)
            doc_links = doc_links_result.scalars().all()

            for link in doc_links:
                entity_id = f"entity_{link.entity_id}"
                if entity_id not in visited:
                    entity = await db.get(BusinessEntity, link.entity_id)
                    if entity and entity.company_id == company_id:
                        nodes[entity_id] = GraphNode(
                            id=entity_id,
                            label=entity.name or "Unbekannt",
                            type="entity",
                            properties={
                                "entity_type": entity.entity_type or "unknown",
                            },
                        )
                        visited.add(entity_id)
                        queue.append((entity_id, current_depth + 1))

                        edges.append(
                            GraphEdge(
                                source=node_id,
                                target=entity_id,
                                label="REFERENCES",
                                properties={"confidence": str(link.confidence or 0)},
                            )
                        )

        elif node_type == "invoice":
            # Finde verknuepftes Dokument
            invoice = await db.get(InvoiceTracking, node_uuid)
            if invoice and invoice.document_id:
                doc_id = f"document_{invoice.document_id}"
                if doc_id not in visited:
                    doc = await db.get(Document, invoice.document_id)
                    if doc and doc.company_id == company_id:
                        nodes[doc_id] = GraphNode(
                            id=doc_id,
                            label=doc.filename or "Dokument",
                            type="document",
                            properties={
                                "document_type": doc.document_type or "unknown",
                            },
                        )
                        visited.add(doc_id)
                        queue.append((doc_id, current_depth + 1))

                        edges.append(
                            GraphEdge(
                                source=node_id,
                                target=doc_id,
                                label="BASED_ON",
                                properties={},
                            )
                        )

    async def explore(
        self,
        query: str,
        company_id: UUID,
        db: AsyncSession,
    ) -> GraphData:
        """
        Explore Graph basierend auf Suchbegriff.

        Args:
            query: Suchbegriff (Name, Rechnungsnummer, etc.)
            company_id: Company UUID
            db: Database session

        Returns:
            GraphData mit gefundenen Nodes und Edges
        """
        logger.info(
            "knowledge_graph.explore",
            query=query,
            company_id=str(company_id),
        )

        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []

        # Suche Entities
        entities_query = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id,
                or_(
                    BusinessEntity.name.ilike(f"%{query}%"),
                    BusinessEntity.primary_customer_number.ilike(f"%{query}%"),
                ),
            )
        ).limit(20)
        entities_result = await db.execute(entities_query)
        entities = entities_result.scalars().all()

        for entity in entities:
            entity_id = f"entity_{entity.id}"
            nodes[entity_id] = GraphNode(
                id=entity_id,
                label=entity.name or "Unbekannt",
                type="entity",
                properties={
                    "entity_type": entity.entity_type or "unknown",
                    "risk_score": str(entity.risk_score or 0),
                },
            )

            # Finde verknuepfte Dokumente
            doc_links_query = select(DocumentEntityLink).where(
                DocumentEntityLink.entity_id == entity.id
            ).limit(5)
            doc_links_result = await db.execute(doc_links_query)
            doc_links = doc_links_result.scalars().all()

            for link in doc_links:
                doc_id = f"document_{link.document_id}"
                if doc_id not in nodes:
                    doc = await db.get(Document, link.document_id)
                    if doc and doc.company_id == company_id:
                        nodes[doc_id] = GraphNode(
                            id=doc_id,
                            label=doc.filename or "Dokument",
                            type="document",
                            properties={
                                "document_type": doc.document_type or "unknown",
                            },
                        )

                        edges.append(
                            GraphEdge(
                                source=entity_id,
                                target=doc_id,
                                label="CONTAINS_DOCUMENT",
                                properties={"confidence": str(link.confidence or 0)},
                            )
                        )

        stats = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "query": query,
        }

        return GraphData(
            nodes=list(nodes.values()),
            edges=edges,
            stats=stats,
        )

    async def get_shortest_path(
        self,
        from_id: UUID,
        to_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[PathData]:
        """
        Findet kuerzesten Pfad zwischen zwei Nodes.

        Nutzt BFS (Breadth-First Search).

        Args:
            from_id: Start Node UUID
            to_id: Ziel Node UUID
            company_id: Company UUID
            db: Database session

        Returns:
            PathData mit Pfad, oder None wenn kein Pfad existiert
        """
        logger.info(
            "knowledge_graph.shortest_path",
            from_id=str(from_id),
            to_id=str(to_id),
            company_id=str(company_id),
        )

        # TODO: Implementiere BFS-Pathfinding
        # Fuer MVP: Vereinfacht - pruefe nur direkte Verbindung

        # Pruefe ob beide Entities existieren
        from_entity = await db.get(BusinessEntity, from_id)
        to_entity = await db.get(BusinessEntity, to_id)

        if not from_entity or not to_entity:
            return None

        if from_entity.company_id != company_id or to_entity.company_id != company_id:
            return None

        # Finde gemeinsame Dokumente
        from_docs_query = select(DocumentEntityLink.document_id).where(
            DocumentEntityLink.entity_id == from_id
        )
        from_docs_result = await db.execute(from_docs_query)
        from_docs = set(from_docs_result.scalars().all())

        to_docs_query = select(DocumentEntityLink.document_id).where(
            DocumentEntityLink.entity_id == to_id
        )
        to_docs_result = await db.execute(to_docs_query)
        to_docs = set(to_docs_result.scalars().all())

        common_docs = from_docs & to_docs

        if common_docs:
            # Direkter Pfad ueber gemeinsames Dokument
            doc_id = list(common_docs)[0]
            doc = await db.get(Document, doc_id)

            if doc:
                nodes = [
                    GraphNode(
                        id=f"entity_{from_id}",
                        label=from_entity.name or "Unbekannt",
                        type="entity",
                        properties={},
                    ),
                    GraphNode(
                        id=f"document_{doc_id}",
                        label=doc.filename or "Dokument",
                        type="document",
                        properties={},
                    ),
                    GraphNode(
                        id=f"entity_{to_id}",
                        label=to_entity.name or "Unbekannt",
                        type="entity",
                        properties={},
                    ),
                ]

                edges = [
                    GraphEdge(
                        source=f"entity_{from_id}",
                        target=f"document_{doc_id}",
                        label="CONTAINS_DOCUMENT",
                        properties={},
                    ),
                    GraphEdge(
                        source=f"document_{doc_id}",
                        target=f"entity_{to_id}",
                        label="REFERENCES",
                        properties={},
                    ),
                ]

                return PathData(
                    path=[f"entity_{from_id}", f"document_{doc_id}", f"entity_{to_id}"],
                    length=2,
                    nodes=nodes,
                    edges=edges,
                )

        return None

    async def get_communities(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[Community]:
        """
        Findet Communities/Cluster von zusammenhaengenden Nodes.

        Nutzt Union-Find fuer Connected Components.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            Liste von Communities
        """
        logger.info("knowledge_graph.get_communities", company_id=str(company_id))

        # TODO: Implementiere Community Detection
        # Fuer MVP: Vereinfacht - gruppiere Entities nach Dokumenten

        communities: List[Community] = []

        # Finde Entities mit gemeinsamen Dokumenten
        doc_links_query = select(DocumentEntityLink).limit(100)
        doc_links_result = await db.execute(doc_links_query)
        doc_links = doc_links_result.scalars().all()

        # Gruppiere nach document_id
        doc_to_entities: Dict[UUID, List[UUID]] = defaultdict(list)
        for link in doc_links:
            doc_to_entities[link.document_id].append(link.entity_id)

        # Erstelle Communities fuer Dokumente mit mehreren Entities
        for doc_id, entity_ids in doc_to_entities.items():
            if len(entity_ids) > 1:
                doc = await db.get(Document, doc_id)
                if doc and doc.company_id == company_id:
                    communities.append(
                        Community(
                            id=str(doc_id),
                            name=doc.filename or "Community",
                            node_count=len(entity_ids) + 1,  # Entities + Dokument
                            edge_count=len(entity_ids),
                            central_node=GraphNode(
                                id=f"document_{doc_id}",
                                label=doc.filename or "Dokument",
                                type="document",
                                properties={},
                            ),
                            member_ids=[f"entity_{e}" for e in entity_ids],
                        )
                    )

        return communities[:20]  # Limit auf 20 Communities
