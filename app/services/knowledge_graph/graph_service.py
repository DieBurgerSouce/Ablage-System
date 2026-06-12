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
from typing import Any, List, Dict, Set, Optional, Tuple
from uuid import UUID
from collections import defaultdict, deque

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
    BankAccount,
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
    properties: Dict[str, str]  # Zusätzliche Metadaten

    def to_dict(self) -> Dict[str, Any]:
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
    properties: Dict[str, str]  # Zusätzliche Metadaten

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "stats": self.stats,
        }


@dataclass
class PathData:
    """Kürzester Pfad zwischen zwei Nodes."""

    path: List[str]  # Liste von Node IDs
    length: int  # Pfad-Länge
    nodes: List[GraphNode]  # Nodes im Pfad
    edges: List[GraphEdge]  # Edges im Pfad

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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

        # BFS (Breadth-First Search) für Graph-Expansion
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
            # Finde verknüpfte Dokumente
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

            # Finde verknüpfte Rechnungen
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

            # Finde Bank-Transaktionen. BankTransaction hat KEINE Spalten
            # linked_entity_id/company_id: Entity-Bezug via gematchtes
            # Dokument, Company-Scope via BankAccount-JOIN.
            transactions_query = (
                select(BankTransaction)
                .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
                .join(Document, BankTransaction.matched_document_id == Document.id)
                .where(
                    and_(
                        Document.business_entity_id == node_uuid,
                        BankAccount.company_id == company_id,
                    )
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
                            "purpose": txn.reference_text or "",
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
            # Finde verknüpfte Entities
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
            # Finde verknüpftes Dokument
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

        # Escape SQL LIKE wildcards to prevent injection
        safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        # Suche Entities
        entities_query = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id,
                or_(
                    BusinessEntity.name.ilike(f"%{safe_query}%"),
                    BusinessEntity.primary_customer_number.ilike(f"%{safe_query}%"),
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

            # Finde verknüpfte Dokumente
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
        Findet kürzesten Pfad zwischen zwei Nodes.

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

        # Prüfe ob beide Entities existieren
        from_entity = await db.get(BusinessEntity, from_id)
        to_entity = await db.get(BusinessEntity, to_id)

        if not from_entity or not to_entity:
            return None

        if from_entity.company_id != company_id or to_entity.company_id != company_id:
            return None

        # BFS-Pathfinding mit max_depth zur Performance-Begrenzung
        max_depth = 6
        path_result = await self._bfs_shortest_path(
            from_id=from_id,
            to_id=to_id,
            company_id=company_id,
            max_depth=max_depth,
            db=db,
        )

        if path_result:
            return path_result

        # Fallback: Direkte Verbindung prüfen
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

    async def _bfs_shortest_path(
        self,
        from_id: UUID,
        to_id: UUID,
        company_id: UUID,
        max_depth: int,
        db: AsyncSession,
    ) -> Optional[PathData]:
        """
        BFS-Algorithmus für kürzesten Pfad zwischen Entities.

        Findet Pfade über Dokumente und andere Entities.

        Args:
            from_id: Start-Entity UUID
            to_id: Ziel-Entity UUID
            company_id: Company UUID
            max_depth: Maximale Pfadtiefe
            db: Database session

        Returns:
            PathData wenn Pfad gefunden, sonst None
        """
        from collections import deque

        # BFS Queue: (current_node_id, node_type, path, depth)
        queue = deque([(from_id, "entity", [from_id], 0)])
        visited = {f"entity_{from_id}"}

        while queue:
            current_id, current_type, path, depth = queue.popleft()

            if depth >= max_depth:
                continue

            if current_type == "entity":
                # Finde alle Dokumente dieser Entity
                doc_links = await db.execute(
                    select(DocumentEntityLink.document_id).where(
                        DocumentEntityLink.entity_id == current_id
                    )
                )
                doc_ids = doc_links.scalars().all()

                for doc_id in doc_ids:
                    doc_key = f"document_{doc_id}"
                    if doc_key in visited:
                        continue

                    visited.add(doc_key)
                    new_path = path + [doc_id]
                    queue.append((doc_id, "document", new_path, depth + 1))

            elif current_type == "document":
                # Finde alle Entities dieses Dokuments
                entity_links = await db.execute(
                    select(DocumentEntityLink.entity_id).where(
                        DocumentEntityLink.document_id == current_id
                    )
                )
                entity_ids = entity_links.scalars().all()

                for entity_id in entity_ids:
                    # Ziel gefunden?
                    if entity_id == to_id:
                        final_path = path + [entity_id]
                        return await self._build_path_data(final_path, db)

                    entity_key = f"entity_{entity_id}"
                    if entity_key in visited:
                        continue

                    # Prüfe ob Entity zur gleichen Company gehoert
                    entity = await db.get(BusinessEntity, entity_id)
                    if entity and entity.company_id == company_id:
                        visited.add(entity_key)
                        new_path = path + [entity_id]
                        queue.append((entity_id, "entity", new_path, depth + 1))

        return None

    async def _build_path_data(
        self,
        path: List[UUID],
        db: AsyncSession,
    ) -> PathData:
        """
        Baut PathData aus Pfad-Liste.

        Args:
            path: Liste von UUIDs (alternierend Entity/Document)
            db: Database session

        Returns:
            PathData mit Nodes und Edges
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        path_ids: List[str] = []

        for i, uuid_val in enumerate(path):
            is_entity = (i % 2 == 0)  # Pfad beginnt mit Entity

            if is_entity:
                entity = await db.get(BusinessEntity, uuid_val)
                node_id = f"entity_{uuid_val}"
                label = entity.name if entity else "Unbekannt"
                node_type = "entity"
            else:
                doc = await db.get(Document, uuid_val)
                node_id = f"document_{uuid_val}"
                label = doc.filename if doc else "Dokument"
                node_type = "document"

            nodes.append(GraphNode(
                id=node_id,
                label=label,
                type=node_type,
                properties={},
            ))
            path_ids.append(node_id)

            # Edge zum vorherigen Node
            if i > 0:
                prev_node_id = path_ids[i - 1]
                edges.append(GraphEdge(
                    source=prev_node_id,
                    target=node_id,
                    label="CONNECTED_TO",
                    properties={},
                ))

        return PathData(
            path=path_ids,
            length=len(path) - 1,
            nodes=nodes,
            edges=edges,
        )

    async def get_communities(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[Community]:
        """
        Findet Communities/Cluster von zusammenhaengenden Nodes.

        Nutzt Union-Find für Connected Components.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            Liste von Communities
        """
        logger.info("knowledge_graph.get_communities", company_id=str(company_id))

        # Union-Find basierte Community Detection
        communities = await self._union_find_communities(company_id, db)

        if communities:
            logger.info(
                "knowledge_graph.communities_found",
                count=len(communities),
                company_id=str(company_id),
            )
            return communities[:20]  # Limit auf 20 Communities

        # Fallback: Gruppiere nach Dokumenten (Simple Approach)
        fallback_communities: List[Community] = []

        doc_links_query = select(DocumentEntityLink).limit(500)
        doc_links_result = await db.execute(doc_links_query)
        doc_links = doc_links_result.scalars().all()

        doc_to_entities: Dict[UUID, List[UUID]] = defaultdict(list)
        for link in doc_links:
            doc_to_entities[link.document_id].append(link.entity_id)

        for doc_id, entity_ids in doc_to_entities.items():
            if len(entity_ids) > 1:
                doc = await db.get(Document, doc_id)
                if doc and doc.company_id == company_id:
                    fallback_communities.append(
                        Community(
                            id=str(doc_id),
                            name=doc.filename or "Community",
                            node_count=len(entity_ids) + 1,
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

        return fallback_communities[:20]

    async def _union_find_communities(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[Community]:
        """
        Union-Find Algorithmus für Connected Components.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            Liste von Communities basierend auf Connected Components
        """
        # 1. Lade alle Entities der Company
        entities_query = select(BusinessEntity.id, BusinessEntity.name).where(
            BusinessEntity.company_id == company_id
        ).limit(1000)
        entities_result = await db.execute(entities_query)
        entities = {e.id: e.name for e in entities_result.all()}

        if not entities:
            return []

        # 2. Union-Find Datenstruktur
        parent: Dict[UUID, UUID] = {e: e for e in entities.keys()}
        rank: Dict[UUID, int] = {e: 0 for e in entities.keys()}

        def find(x: UUID) -> UUID:
            """Find mit Pfadkompression."""
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: UUID, y: UUID) -> None:
            """Union mit Rank-Optimierung."""
            root_x = find(x)
            root_y = find(y)
            if root_x != root_y:
                if rank[root_x] < rank[root_y]:
                    parent[root_x] = root_y
                elif rank[root_x] > rank[root_y]:
                    parent[root_y] = root_x
                else:
                    parent[root_y] = root_x
                    rank[root_x] += 1

        # 3. Finde Verbindungen über Dokumente
        doc_links_query = select(
            DocumentEntityLink.document_id,
            DocumentEntityLink.entity_id
        ).where(
            DocumentEntityLink.entity_id.in_(entities.keys())
        )
        doc_links_result = await db.execute(doc_links_query)
        doc_links = doc_links_result.all()

        # Gruppiere Entities nach Dokument
        doc_to_entities: Dict[UUID, List[UUID]] = defaultdict(list)
        for doc_id, entity_id in doc_links:
            doc_to_entities[doc_id].append(entity_id)

        # Union Entities die das gleiche Dokument teilen
        for doc_id, entity_ids in doc_to_entities.items():
            if len(entity_ids) > 1:
                first = entity_ids[0]
                for other in entity_ids[1:]:
                    union(first, other)

        # 4. Gruppiere nach Root
        root_to_members: Dict[UUID, List[UUID]] = defaultdict(list)
        for entity_id in entities.keys():
            root = find(entity_id)
            root_to_members[root].append(entity_id)

        # 5. Erstelle Communities
        communities: List[Community] = []
        community_idx = 0

        for root_id, member_ids in root_to_members.items():
            if len(member_ids) > 1:  # Nur echte Communities
                community_idx += 1

                # Finde zentralen Knoten (mit meisten Verbindungen)
                central_id = root_id
                max_connections = 0

                for member_id in member_ids:
                    # Zaehle Dokument-Verbindungen
                    connections = sum(
                        1 for doc_id, eid in doc_links
                        if eid == member_id
                    )
                    if connections > max_connections:
                        max_connections = connections
                        central_id = member_id

                central_name = entities.get(central_id, "Unbekannt")

                # Zaehle Edges (interne Verbindungen)
                edge_count = 0
                for doc_id, ent_ids in doc_to_entities.items():
                    members_in_doc = [e for e in ent_ids if e in member_ids]
                    if len(members_in_doc) > 1:
                        edge_count += len(members_in_doc) - 1

                communities.append(
                    Community(
                        id=f"community_{community_idx}",
                        name=f"Cluster: {central_name}",
                        node_count=len(member_ids),
                        edge_count=edge_count,
                        central_node=GraphNode(
                            id=f"entity_{central_id}",
                            label=central_name,
                            type="entity",
                            properties={"is_central": True},
                        ),
                        member_ids=[f"entity_{m}" for m in member_ids],
                    )
                )

        # Sortiere nach Größe (größte zuerst)
        communities.sort(key=lambda c: c.node_count, reverse=True)

        return communities

    # =========================================================================
    # Phase B: Financial Chain, Risk Network, Document Family
    # =========================================================================

    async def get_financial_chain(
        self,
        entity_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, object]:
        """
        Laedt Finanzketten fuer eine Entity.

        Findet Rechnungen, Zahlungen und berechnet Match-Status.
        """
        logger.info("knowledge_graph.get_financial_chain", entity_id=str(entity_id))

        entity = await db.get(BusinessEntity, entity_id)
        if not entity or entity.company_id != company_id:
            return {
                "entityId": str(entity_id),
                "entityName": "Unbekannt",
                "stages": [],
                "matchStatus": "none",
                "totalAmount": 0,
            }

        stages: List[Dict[str, object]] = []

        # Stage: Rechnungen
        invoices_query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.entity_id == entity_id,
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.deleted_at.is_(None),
            )
        ).limit(50)
        invoices_result = await db.execute(invoices_query)
        invoices = invoices_result.scalars().all()

        invoice_nodes: List[Dict[str, object]] = []
        total_amount = 0.0
        for inv in invoices:
            amount = float(inv.total_amount or 0)
            total_amount += amount
            invoice_nodes.append({
                "id": f"invoice_{inv.id}",
                "type": "invoice",
                "label": inv.invoice_number or "Rechnung",
                "data": {
                    "status": inv.status.value if inv.status else "unknown",
                    "amount": amount,
                    "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                },
            })

        if invoice_nodes:
            stages.append({
                "stage": "invoice",
                "label": "Rechnungen",
                "documents": invoice_nodes,
            })

        # Stage: Transaktionen/Zahlungen. BankTransaction hat KEINE Spalten
        # linked_entity_id/company_id: Entity-Bezug via gematchtes Dokument,
        # Company-Scope via BankAccount-JOIN.
        txns_query = (
            select(BankTransaction)
            .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
            .join(Document, BankTransaction.matched_document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    BankAccount.company_id == company_id,
                )
            )
            .limit(50)
        )
        txns_result = await db.execute(txns_query)
        txns = txns_result.scalars().all()

        payment_nodes: List[Dict[str, object]] = []
        for txn in txns:
            payment_nodes.append({
                "id": f"transaction_{txn.id}",
                "type": "payment",
                "label": f"{txn.amount} EUR",
                "data": {
                    "amount": float(txn.amount or 0),
                    "date": txn.value_date.isoformat() if txn.value_date else None,
                    "purpose": txn.reference_text or "",
                },
            })

        if payment_nodes:
            stages.append({
                "stage": "payment",
                "label": "Zahlungen",
                "documents": payment_nodes,
            })

        # Determine match status
        match_status = "none"
        if invoice_nodes and payment_nodes:
            match_status = "partial"
            paid_amount = sum(
                float(p["data"]["amount"])  # type: ignore[index]
                for p in payment_nodes
            )
            if paid_amount >= total_amount * 0.95:
                match_status = "full"

        return {
            "entityId": str(entity_id),
            "entityName": entity.name or "Unbekannt",
            "stages": stages,
            "matchStatus": match_status,
            "totalAmount": round(total_amount, 2),
        }

    async def get_risk_network(
        self,
        company_id: UUID,
        db: AsyncSession,
        focus_entity_id: Optional[UUID] = None,
    ) -> Dict[str, object]:
        """
        Laedt Risiko-Netzwerk mit Communities und Risk Scores.
        """
        logger.info("knowledge_graph.get_risk_network", company_id=str(company_id))

        # Lade Entities mit Risk Scores
        entities_query = select(BusinessEntity).where(
            BusinessEntity.company_id == company_id
        ).limit(100)
        entities_result = await db.execute(entities_query)
        entities = entities_result.scalars().all()

        nodes: List[Dict[str, object]] = []
        for entity in entities:
            # Berechne Transaktionsvolumen (Entity-Bezug via gematchtes
            # Dokument, Company-Scope via BankAccount-JOIN — siehe oben)
            vol_query = (
                select(BankTransaction.amount)
                .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
                .join(Document, BankTransaction.matched_document_id == Document.id)
                .where(
                    and_(
                        Document.business_entity_id == entity.id,
                        BankAccount.company_id == company_id,
                    )
                )
            )
            vol_result = await db.execute(vol_query)
            amounts = vol_result.scalars().all()
            volume = sum(abs(float(a or 0)) for a in amounts)

            nodes.append({
                "entityId": str(entity.id),
                "entityName": entity.name or "Unbekannt",
                "riskScore": float(entity.risk_score or 50),
                "transactionVolume": round(volume, 2),
                "communityId": "",
                "paymentBehaviorScore": 50.0,
                "industryRisk": 50.0,
                "lastAnomaly": None,
            })

        # Communities via Union-Find
        communities_list = await self.get_communities(company_id, db)

        communities: List[Dict[str, object]] = []
        for comm in communities_list:
            communities.append({
                "id": comm.id,
                "name": comm.name,
                "memberIds": comm.member_ids,
            })
            # Update community IDs on nodes
            for node in nodes:
                entity_key = f"entity_{node['entityId']}"
                if entity_key in comm.member_ids:
                    node["communityId"] = comm.id

        # Edges: Entities verbunden ueber gemeinsame Dokumente
        edges: List[Dict[str, object]] = []
        entity_docs: Dict[str, Set[str]] = defaultdict(set)

        node_entity_ids = [UUID(str(n["entityId"])) for n in nodes]
        if node_entity_ids:
            doc_links_query = select(
                DocumentEntityLink.entity_id,
                DocumentEntityLink.document_id,
            ).where(
                DocumentEntityLink.entity_id.in_(node_entity_ids)
            )
            doc_links_result = await db.execute(doc_links_query)

            for entity_id_val, doc_id_val in doc_links_result.all():
                entity_docs[str(entity_id_val)].add(str(doc_id_val))

        # Finde Entity-Paare mit gemeinsamen Dokumenten
        entity_id_keys = list(entity_docs.keys())
        for i in range(len(entity_id_keys)):
            for j in range(i + 1, len(entity_id_keys)):
                common = entity_docs[entity_id_keys[i]] & entity_docs[entity_id_keys[j]]
                if common:
                    edges.append({
                        "source": entity_id_keys[i],
                        "target": entity_id_keys[j],
                        "transactionCount": len(common),
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "communities": communities,
        }

    async def get_document_family(
        self,
        document_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, object]:
        """
        Laedt verwandte Dokumente gruppiert nach Beziehungstyp.
        """
        logger.info("knowledge_graph.get_document_family", document_id=str(document_id))

        root_doc = await db.get(Document, document_id)
        if not root_doc or root_doc.company_id != company_id:
            return {
                "rootDocument": None,
                "groups": [],
                "unlinkedCount": 0,
            }

        root_node: Dict[str, object] = {
            "id": f"document_{document_id}",
            "type": "document",
            "label": root_doc.filename or "Dokument",
            "data": {
                "document_type": root_doc.document_type or "unknown",
                "status": root_doc.status or "unknown",
                "created_at": root_doc.created_at.isoformat() if root_doc.created_at else None,
            },
        }

        # Finde alle Entities die mit diesem Dokument verknuepft sind
        entity_links_query = select(DocumentEntityLink).where(
            DocumentEntityLink.document_id == document_id
        )
        entity_links_result = await db.execute(entity_links_query)
        entity_links = entity_links_result.scalars().all()

        related_doc_ids: Set[UUID] = set()

        # Finde alle Dokumente der gleichen Entities
        for link in entity_links:
            other_docs_query = select(DocumentEntityLink.document_id).where(
                and_(
                    DocumentEntityLink.entity_id == link.entity_id,
                    DocumentEntityLink.document_id != document_id,
                )
            )
            other_docs_result = await db.execute(other_docs_query)
            for doc_id_row in other_docs_result.scalars().all():
                related_doc_ids.add(doc_id_row)

        # Gruppiere nach Dokumenttyp
        groups_by_type: Dict[str, List[Dict[str, object]]] = defaultdict(list)

        for rel_doc_id in related_doc_ids:
            doc = await db.get(Document, rel_doc_id)
            if doc and doc.company_id == company_id:
                doc_type = doc.document_type or "sonstiges"
                groups_by_type[doc_type].append({
                    "id": f"document_{rel_doc_id}",
                    "type": "document",
                    "label": doc.filename or "Dokument",
                    "data": {
                        "document_type": doc_type,
                        "status": doc.status or "unknown",
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    },
                })

        # Map document types to rings
        TYPE_RING_MAP: Dict[str, int] = {
            "vertrag": 1, "anlage": 1, "nachtrag": 1,
            "rechnung": 2, "lieferschein": 2, "bestellung": 2,
            "korrespondenz": 3, "email": 3, "sonstiges": 3,
        }
        TYPE_LABELS: Dict[str, str] = {
            "vertrag": "Vertraege", "anlage": "Anlagen", "nachtrag": "Nachtraege",
            "rechnung": "Rechnungen", "lieferschein": "Lieferscheine", "bestellung": "Bestellungen",
            "korrespondenz": "Korrespondenz", "email": "E-Mails", "sonstiges": "Sonstige",
        }

        groups: List[Dict[str, object]] = []
        for doc_type, docs in groups_by_type.items():
            ring = TYPE_RING_MAP.get(doc_type, 3)
            label = TYPE_LABELS.get(doc_type, doc_type.capitalize())
            groups.append({
                "ring": ring,
                "label": label,
                "documents": docs,
            })

        groups.sort(key=lambda g: g["ring"])  # type: ignore[arg-type]

        return {
            "rootDocument": root_node,
            "groups": groups,
            "unlinkedCount": 0,
        }
