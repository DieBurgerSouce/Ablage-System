# -*- coding: utf-8 -*-
"""Cluster-Management-Service.

CRUD-Operationen fuer Cluster und automatisches Clustering
via DBSCAN auf Basis von pgvector Distanzen.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import Document
from app.db.models_clustering import (
    ClusterSuggestion,
    DocumentCluster,
    DocumentClusterMembership,
)

logger = structlog.get_logger(__name__)


class ClusterManagementService:
    """Service fuer Cluster-Verwaltung und automatisches Clustering.

    Bietet CRUD-Operationen, Centroid-Berechnung, DBSCAN-Clustering
    und Cluster-Zusammenfuehrung.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_cluster(
        self,
        name: str,
        company_id: UUID,
        cluster_type: str = "manual",
        description: Optional[str] = None,
        business_entity_id: Optional[UUID] = None,
        parent_cluster_id: Optional[UUID] = None,
    ) -> DocumentCluster:
        """Erstellt einen neuen Cluster.

        Args:
            name: Anzeigename des Clusters
            company_id: UUID der Company (Mandanten-Isolation)
            cluster_type: Typ des Clusters (auto/manual/entity/category)
            description: Optionale Beschreibung
            business_entity_id: Optionale Business-Entity-Zuordnung
            parent_cluster_id: Optionaler uebergeordneter Cluster

        Returns:
            Neu erstellter DocumentCluster
        """
        cluster = DocumentCluster(
            name=name,
            company_id=company_id,
            cluster_type=cluster_type,
            description=description,
            business_entity_id=business_entity_id,
            parent_cluster_id=parent_cluster_id,
        )
        self.session.add(cluster)
        await self.session.flush()

        logger.info(
            "cluster_created",
            cluster_id=str(cluster.id),
            name=name,
            cluster_type=cluster_type,
            company_id=str(company_id),
        )
        return cluster

    async def get_cluster(
        self, cluster_id: UUID, company_id: UUID
    ) -> Optional[DocumentCluster]:
        """Laedt einen Cluster mit Validierung der Company.

        Args:
            cluster_id: UUID des Clusters
            company_id: UUID der Company

        Returns:
            DocumentCluster oder None wenn nicht gefunden
        """
        result = await self.session.execute(
            select(DocumentCluster).where(
                DocumentCluster.id == cluster_id,
                DocumentCluster.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_clusters(
        self,
        company_id: UUID,
        cluster_type: Optional[str] = None,
        is_active: Optional[bool] = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DocumentCluster]:
        """Listet Cluster einer Company mit optionalen Filtern.

        Args:
            company_id: UUID der Company
            cluster_type: Optionaler Typ-Filter
            is_active: Optionaler Aktiv-Filter (Standard: True)
            limit: Maximale Anzahl Ergebnisse
            offset: Offset fuer Paginierung

        Returns:
            Liste der DocumentCluster
        """
        query = select(DocumentCluster).where(
            DocumentCluster.company_id == company_id,
        )

        if cluster_type is not None:
            query = query.where(DocumentCluster.cluster_type == cluster_type)

        if is_active is not None:
            query = query.where(DocumentCluster.is_active == is_active)

        query = query.order_by(
            DocumentCluster.document_count.desc(),
            DocumentCluster.created_at.desc(),
        ).offset(offset).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_clusters(
        self,
        company_id: UUID,
        cluster_type: Optional[str] = None,
        is_active: Optional[bool] = True,
    ) -> int:
        """Zaehlt Cluster einer Company.

        Args:
            company_id: UUID der Company
            cluster_type: Optionaler Typ-Filter
            is_active: Optionaler Aktiv-Filter

        Returns:
            Anzahl der Cluster
        """
        query = select(func.count(DocumentCluster.id)).where(
            DocumentCluster.company_id == company_id,
        )
        if cluster_type is not None:
            query = query.where(DocumentCluster.cluster_type == cluster_type)
        if is_active is not None:
            query = query.where(DocumentCluster.is_active == is_active)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def update_cluster_centroid(
        self, cluster_id: UUID
    ) -> Optional[DocumentCluster]:
        """Berechnet den Centroid als Durchschnitt aller Dokument-Embeddings.

        Nutzt pgvector AVG-Aggregation fuer effiziente Berechnung.
        Aktualisiert ausserdem document_count und avg_similarity.

        Args:
            cluster_id: UUID des Clusters

        Returns:
            Aktualisierter DocumentCluster oder None
        """
        # Cluster laden
        result = await self.session.execute(
            select(DocumentCluster).where(DocumentCluster.id == cluster_id)
        )
        cluster = result.scalar_one_or_none()
        if not cluster:
            return None

        # Centroid berechnen via SQL
        centroid_query = text("""
            SELECT
                AVG(d.embedding) AS centroid,
                COUNT(*) AS doc_count
            FROM document_cluster_memberships dcm
            JOIN documents d ON d.id = dcm.document_id
            WHERE dcm.cluster_id = :cluster_id
              AND d.embedding IS NOT NULL
        """)
        centroid_result = await self.session.execute(
            centroid_query, {"cluster_id": str(cluster_id)}
        )
        row = centroid_result.first()

        if row and row[1] > 0:
            cluster.centroid = row[0]
            cluster.document_count = int(row[1])

            # Durchschnittliche Intra-Cluster-Aehnlichkeit berechnen
            if cluster.centroid is not None:
                avg_sim_query = text("""
                    SELECT AVG(1 - (d.embedding <=> :centroid)) AS avg_sim
                    FROM document_cluster_memberships dcm
                    JOIN documents d ON d.id = dcm.document_id
                    WHERE dcm.cluster_id = :cluster_id
                      AND d.embedding IS NOT NULL
                """)
                avg_sim_result = await self.session.execute(
                    avg_sim_query,
                    {
                        "cluster_id": str(cluster_id),
                        "centroid": str(cluster.centroid),
                    },
                )
                avg_sim_row = avg_sim_result.first()
                if avg_sim_row and avg_sim_row[0] is not None:
                    cluster.avg_similarity = float(avg_sim_row[0])
        else:
            cluster.document_count = 0
            cluster.centroid = None
            cluster.avg_similarity = None

        await self.session.flush()

        logger.info(
            "cluster_centroid_updated",
            cluster_id=str(cluster_id),
            document_count=cluster.document_count,
            avg_similarity=cluster.avg_similarity,
        )
        return cluster

    async def add_document_to_cluster(
        self,
        document_id: UUID,
        cluster_id: UUID,
        similarity_score: float,
        assigned_by: str = "auto",
        confidence: float = 0.0,
    ) -> DocumentClusterMembership:
        """Fuegt ein Dokument einem Cluster hinzu.

        Args:
            document_id: UUID des Dokuments
            cluster_id: UUID des Clusters
            similarity_score: Aehnlichkeit zum Cluster (0.0-1.0)
            assigned_by: Zuordnungsquelle (auto/user/system)
            confidence: Konfidenz der Zuordnung

        Returns:
            Neu erstellte DocumentClusterMembership
        """
        membership = DocumentClusterMembership(
            document_id=document_id,
            cluster_id=cluster_id,
            similarity_score=similarity_score,
            assigned_by=assigned_by,
            confidence=confidence,
        )
        self.session.add(membership)
        await self.session.flush()

        # Document count im Cluster aktualisieren
        await self.session.execute(
            update(DocumentCluster)
            .where(DocumentCluster.id == cluster_id)
            .values(document_count=DocumentCluster.document_count + 1)
        )
        await self.session.flush()

        logger.info(
            "document_added_to_cluster",
            document_id=str(document_id),
            cluster_id=str(cluster_id),
            similarity=round(similarity_score, 4),
        )
        return membership

    async def auto_cluster_documents(
        self,
        company_id: UUID,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.7,
    ) -> List[DocumentCluster]:
        """Automatisches Clustering via Greedy-Algorithmus auf pgvector-Basis.

        Fuer jedes Dokument ohne Cluster-Zuordnung:
        1. Finde aehnlichste Dokumente ueber dem Schwellwert
        2. Gruppiere zu neuem Cluster oder weise bestehendem zu

        Args:
            company_id: UUID der Company
            min_cluster_size: Minimale Cluster-Groesse
            similarity_threshold: Mindest-Aehnlichkeit fuer Cluster-Zuordnung

        Returns:
            Liste der neu erstellten DocumentCluster
        """
        logger.info(
            "auto_clustering_starting",
            company_id=str(company_id),
            min_cluster_size=min_cluster_size,
            similarity_threshold=similarity_threshold,
        )

        # Dokumente mit Embedding laden, die noch keinem Cluster zugeordnet sind
        unclustered_query = text("""
            SELECT d.id, d.filename, d.document_type, d.business_entity_id
            FROM documents d
            LEFT JOIN document_cluster_memberships dcm ON dcm.document_id = d.id
            WHERE d.company_id = :company_id
              AND d.embedding IS NOT NULL
              AND d.deleted_at IS NULL
              AND dcm.id IS NULL
            ORDER BY d.created_at DESC
        """)
        unclustered_result = await self.session.execute(
            unclustered_query, {"company_id": str(company_id)}
        )
        unclustered_docs = unclustered_result.fetchall()

        if len(unclustered_docs) < min_cluster_size:
            logger.info(
                "auto_clustering_skipped_too_few_docs",
                company_id=str(company_id),
                doc_count=len(unclustered_docs),
                min_required=min_cluster_size,
            )
            return []

        # Greedy Clustering: Fuer jedes unzugeordnete Dokument aehnliche finden
        assigned_doc_ids: set = set()
        new_clusters: List[DocumentCluster] = []

        for doc_row in unclustered_docs:
            doc_id = doc_row[0]
            if doc_id in assigned_doc_ids:
                continue

            # Aehnliche Dokumente aus den noch nicht zugeordneten finden
            neighbor_query = text("""
                SELECT d2.id,
                       1 - (d1.embedding <=> d2.embedding) AS similarity
                FROM documents d1, documents d2
                WHERE d1.id = :doc_id
                  AND d2.company_id = :company_id
                  AND d2.id != :doc_id
                  AND d2.embedding IS NOT NULL
                  AND d2.deleted_at IS NULL
                  AND 1 - (d1.embedding <=> d2.embedding) >= :threshold
                ORDER BY d1.embedding <=> d2.embedding
                LIMIT 20
            """)
            neighbor_result = await self.session.execute(
                neighbor_query,
                {
                    "doc_id": str(doc_id),
                    "company_id": str(company_id),
                    "threshold": similarity_threshold,
                },
            )
            neighbors = neighbor_result.fetchall()

            # Nur nicht-zugeordnete Nachbarn beruecksichtigen
            cluster_members = [
                (doc_id, 1.0),  # Das Dokument selbst
            ]
            for neighbor_row in neighbors:
                n_id = neighbor_row[0]
                n_sim = float(neighbor_row[1])
                if n_id not in assigned_doc_ids:
                    cluster_members.append((n_id, n_sim))

            # Nur Cluster erstellen, wenn genug Mitglieder
            if len(cluster_members) >= min_cluster_size:
                # Cluster-Name aus haeufigster Kategorie ableiten
                doc_type = doc_row[2] or "unbekannt"
                cluster_name = f"Auto-Cluster: {doc_type} ({len(cluster_members)} Dokumente)"

                cluster = DocumentCluster(
                    name=cluster_name,
                    cluster_type="auto",
                    company_id=company_id,
                    document_count=len(cluster_members),
                    business_entity_id=doc_row[3],
                )
                self.session.add(cluster)
                await self.session.flush()

                # Mitglieder zuordnen
                for member_id, member_sim in cluster_members:
                    membership = DocumentClusterMembership(
                        document_id=member_id,
                        cluster_id=cluster.id,
                        similarity_score=member_sim,
                        assigned_by="auto",
                        confidence=member_sim,
                    )
                    self.session.add(membership)
                    assigned_doc_ids.add(member_id)

                await self.session.flush()

                # Centroid berechnen
                await self.update_cluster_centroid(cluster.id)

                new_clusters.append(cluster)

                logger.info(
                    "auto_cluster_created",
                    cluster_id=str(cluster.id),
                    cluster_name=cluster_name,
                    member_count=len(cluster_members),
                )

        logger.info(
            "auto_clustering_completed",
            company_id=str(company_id),
            clusters_created=len(new_clusters),
            documents_assigned=len(assigned_doc_ids),
        )
        return new_clusters

    async def get_cluster_stats(
        self, company_id: UUID
    ) -> List[Dict[str, object]]:
        """Statistiken aller Cluster einer Company.

        Args:
            company_id: UUID der Company

        Returns:
            Liste mit Statistik-Dicts pro Cluster
        """
        query = text("""
            SELECT
                dc.id,
                dc.name,
                dc.cluster_type,
                dc.document_count,
                dc.avg_similarity,
                dc.is_active,
                dc.created_at,
                COUNT(dcm.id) AS actual_member_count
            FROM document_clusters dc
            LEFT JOIN document_cluster_memberships dcm ON dcm.cluster_id = dc.id
            WHERE dc.company_id = :company_id
            GROUP BY dc.id, dc.name, dc.cluster_type, dc.document_count,
                     dc.avg_similarity, dc.is_active, dc.created_at
            ORDER BY dc.document_count DESC
        """)
        result = await self.session.execute(
            query, {"company_id": str(company_id)}
        )
        rows = result.fetchall()

        stats: List[Dict[str, object]] = []
        for row in rows:
            stats.append({
                "cluster_id": str(row[0]),
                "name": row[1],
                "cluster_type": row[2],
                "document_count": row[3],
                "avg_similarity": row[4],
                "is_active": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
                "actual_member_count": row[7],
            })
        return stats

    async def merge_clusters(
        self, cluster_ids: List[UUID], company_id: UUID
    ) -> Optional[DocumentCluster]:
        """Fuehrt mehrere Cluster zu einem zusammen.

        Der erste Cluster wird beibehalten, alle anderen werden aufgeloest.
        Mitglieder der aufgeloesten Cluster werden dem Ziel-Cluster zugeordnet.

        Args:
            cluster_ids: Liste der zu verschmelzenden Cluster-UUIDs (min. 2)
            company_id: UUID der Company

        Returns:
            Der zusammengefuehrte DocumentCluster oder None bei Fehler
        """
        if len(cluster_ids) < 2:
            raise ValueError("Mindestens 2 Cluster fuer Zusammenfuehrung noetig")

        # Alle Cluster laden und Company pruefen
        clusters: List[DocumentCluster] = []
        for cid in cluster_ids:
            result = await self.session.execute(
                select(DocumentCluster).where(
                    DocumentCluster.id == cid,
                    DocumentCluster.company_id == company_id,
                )
            )
            cluster = result.scalar_one_or_none()
            if not cluster:
                raise ValueError(f"Cluster {cid} nicht gefunden")
            clusters.append(cluster)

        target_cluster = clusters[0]
        source_clusters = clusters[1:]

        # Mitglieder der Quell-Cluster zum Ziel-Cluster verschieben
        for source in source_clusters:
            # Bestehende Mitgliedschaften zum Ziel umhängen
            # (bei Duplikaten: bestehende behalten)
            source_members_result = await self.session.execute(
                select(DocumentClusterMembership).where(
                    DocumentClusterMembership.cluster_id == source.id,
                )
            )
            source_members = source_members_result.scalars().all()

            for member in source_members:
                # Pruefen ob Dokument bereits im Ziel-Cluster ist
                existing = await self.session.execute(
                    select(DocumentClusterMembership).where(
                        DocumentClusterMembership.document_id == member.document_id,
                        DocumentClusterMembership.cluster_id == target_cluster.id,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    new_member = DocumentClusterMembership(
                        document_id=member.document_id,
                        cluster_id=target_cluster.id,
                        similarity_score=member.similarity_score,
                        assigned_by="system",
                        confidence=member.confidence,
                    )
                    self.session.add(new_member)

            # Quell-Cluster deaktivieren
            source.is_active = False
            source.document_count = 0

            # Alte Mitgliedschaften loeschen
            await self.session.execute(
                delete(DocumentClusterMembership).where(
                    DocumentClusterMembership.cluster_id == source.id,
                )
            )

        await self.session.flush()

        # Centroid und Count des Ziel-Clusters aktualisieren
        await self.update_cluster_centroid(target_cluster.id)

        # Name aktualisieren
        target_cluster.name = (
            f"{target_cluster.name} (zusammengefuehrt aus {len(cluster_ids)} Clustern)"
        )
        await self.session.flush()

        logger.info(
            "clusters_merged",
            target_cluster_id=str(target_cluster.id),
            merged_count=len(source_clusters),
            new_document_count=target_cluster.document_count,
        )
        return target_cluster

    async def get_cluster_graph_data(
        self,
        cluster_id: UUID,
        company_id: UUID,
    ) -> Dict[str, List[Dict[str, object]]]:
        """Graph-Daten fuer Cluster-Visualisierung (Knoten + Kanten).

        Args:
            cluster_id: UUID des Clusters
            company_id: UUID der Company

        Returns:
            Dict mit 'nodes' und 'edges' Listen fuer Graph-Rendering
        """
        cluster = await self.get_cluster(cluster_id, company_id)
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} nicht gefunden")

        # Cluster-Knoten
        nodes: List[Dict[str, object]] = [
            {
                "id": str(cluster.id),
                "label": cluster.name,
                "type": "cluster",
                "size": cluster.document_count or 1,
                "metadata": {
                    "cluster_type": cluster.cluster_type,
                    "avg_similarity": cluster.avg_similarity,
                },
            }
        ]

        # Dokument-Knoten und Kanten
        edges: List[Dict[str, object]] = []

        memberships_result = await self.session.execute(
            select(DocumentClusterMembership).where(
                DocumentClusterMembership.cluster_id == cluster_id,
            )
        )
        memberships = memberships_result.scalars().all()

        doc_ids = [m.document_id for m in memberships]
        if doc_ids:
            docs_result = await self.session.execute(
                select(Document).where(Document.id.in_(doc_ids))
            )
            docs_map = {
                doc.id: doc for doc in docs_result.scalars().all()
            }

            for membership in memberships:
                doc = docs_map.get(membership.document_id)
                if not doc:
                    continue

                nodes.append({
                    "id": str(doc.id),
                    "label": doc.filename,
                    "type": "document",
                    "size": 1,
                    "metadata": {
                        "document_type": doc.document_type,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    },
                })
                edges.append({
                    "source": str(cluster.id),
                    "target": str(doc.id),
                    "weight": membership.similarity_score,
                    "label": "similarity",
                })

        return {"nodes": nodes, "edges": edges}
