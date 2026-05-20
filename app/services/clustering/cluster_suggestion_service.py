# -*- coding: utf-8 -*-
"""Cluster-Vorschlags-Service.

Analysiert neue Dokumente per Embedding-Aehnlichkeit und schlaegt
passende Cluster/Entitaeten/Kategorien vor.

Nutzt pgvector Cosine-Distanz fuer hochperformante Vektorsuche.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import Document
from app.db.models_clustering import ClusterSuggestion, DocumentClusterMembership

logger = structlog.get_logger(__name__)


class ClusterSuggestionService:
    """Service fuer Cluster-Vorschlaege bei Dokument-Upload.

    Findet die aehnlichsten Dokumente per pgvector Cosine-Similarity
    und leitet daraus Vorschlaege fuer Cluster/Entity/Kategorie ab.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def suggest_for_document(
        self,
        document_id: UUID,
        company_id: UUID,
        top_k: int = 3,
    ) -> List[ClusterSuggestion]:
        """Findet die aehnlichsten Dokumente und leitet Vorschlaege ab.

        1. Holt Embedding des neuen Dokuments
        2. Cosine-Similarity mit allen Dokumenten der gleichen Company
        3. Gruppiert Ergebnisse nach Entity/Kategorie
        4. Erstellt Suggestions

        Args:
            document_id: UUID des neuen Dokuments
            company_id: UUID der Company (Mandanten-Isolation)
            top_k: Anzahl der Top-Vorschlaege (Standard: 3)

        Returns:
            Liste der erstellten ClusterSuggestion-Eintraege

        Raises:
            ValueError: Wenn Dokument nicht gefunden oder kein Embedding vorhanden
        """
        logger.info(
            "cluster_suggestion_starting",
            document_id=str(document_id),
            company_id=str(company_id),
            top_k=top_k,
        )

        # 1. Dokument mit Embedding laden
        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(
                f"Dokument {document_id} nicht gefunden oder kein Zugriff"
            )

        if document.embedding is None:
            raise ValueError(
                f"Dokument {document_id} hat kein Embedding. "
                "Bitte zuerst OCR und Embedding-Generierung ausfuehren."
            )

        # 2. Aehnlichste Dokumente per pgvector Cosine-Distanz finden
        # pgvector <=> Operator: Cosine Distance (0 = identisch, 2 = gegensaetzlich)
        # Similarity = 1 - distance
        similar_query = text("""
            SELECT
                d.id,
                d.filename,
                d.document_type,
                d.business_entity_id,
                1 - (d.embedding <=> :target_embedding) AS similarity
            FROM documents d
            WHERE d.company_id = :company_id
              AND d.id != :document_id
              AND d.embedding IS NOT NULL
              AND d.deleted_at IS NULL
            ORDER BY d.embedding <=> :target_embedding
            LIMIT :top_k
        """)

        similar_result = await self.session.execute(
            similar_query,
            {
                "target_embedding": str(document.embedding),
                "company_id": str(company_id),
                "document_id": str(document_id),
                "top_k": top_k,
            },
        )
        similar_rows = similar_result.fetchall()

        if not similar_rows:
            logger.info(
                "cluster_suggestion_no_similar_docs",
                document_id=str(document_id),
            )
            return []

        # 3. Vorschlaege erstellen basierend auf aehnlichen Dokumenten
        suggestions: List[ClusterSuggestion] = []
        for row in similar_rows:
            ref_doc_id = row[0]
            ref_filename = row[1]
            ref_doc_type = row[2]
            ref_entity_id = row[3]
            similarity = float(row[4])

            # Nur Vorschlaege mit Mindest-Aehnlichkeit
            if similarity < 0.3:
                continue

            # Cluster-Zuordnung des Referenz-Dokuments pruefen
            membership_result = await self.session.execute(
                select(DocumentClusterMembership.cluster_id).where(
                    DocumentClusterMembership.document_id == ref_doc_id,
                )
            )
            cluster_row = membership_result.first()
            suggested_cluster_id = cluster_row[0] if cluster_row else None

            suggestion = ClusterSuggestion(
                document_id=document_id,
                suggested_cluster_id=suggested_cluster_id,
                suggested_entity_id=ref_entity_id,
                suggested_category=ref_doc_type,
                similarity_score=similarity,
                reference_document_id=ref_doc_id,
                status="pending",
                company_id=company_id,
            )
            self.session.add(suggestion)
            suggestions.append(suggestion)

            logger.debug(
                "cluster_suggestion_created",
                document_id=str(document_id),
                reference_doc=str(ref_doc_id),
                similarity=round(similarity, 4),
                suggested_category=ref_doc_type,
            )

        await self.session.flush()

        logger.info(
            "cluster_suggestion_completed",
            document_id=str(document_id),
            suggestions_count=len(suggestions),
        )
        return suggestions

    async def accept_suggestion(
        self, suggestion_id: UUID
    ) -> ClusterSuggestion:
        """Nutzer akzeptiert einen Vorschlag.

        Setzt den Status auf 'accepted' und den Antwort-Zeitpunkt.

        Args:
            suggestion_id: UUID des Vorschlags

        Returns:
            Aktualisierter ClusterSuggestion-Eintrag

        Raises:
            ValueError: Wenn Vorschlag nicht gefunden
        """
        result = await self.session.execute(
            select(ClusterSuggestion).where(
                ClusterSuggestion.id == suggestion_id,
            )
        )
        suggestion = result.scalar_one_or_none()

        if not suggestion:
            raise ValueError(f"Vorschlag {suggestion_id} nicht gefunden")

        suggestion.status = "accepted"
        suggestion.responded_at = datetime.now(timezone.utc)
        await self.session.flush()

        logger.info(
            "cluster_suggestion_accepted",
            suggestion_id=str(suggestion_id),
            document_id=str(suggestion.document_id),
        )
        return suggestion

    async def reject_suggestion(
        self, suggestion_id: UUID
    ) -> ClusterSuggestion:
        """Nutzer lehnt einen Vorschlag ab.

        Setzt den Status auf 'rejected' und den Antwort-Zeitpunkt.

        Args:
            suggestion_id: UUID des Vorschlags

        Returns:
            Aktualisierter ClusterSuggestion-Eintrag

        Raises:
            ValueError: Wenn Vorschlag nicht gefunden
        """
        result = await self.session.execute(
            select(ClusterSuggestion).where(
                ClusterSuggestion.id == suggestion_id,
            )
        )
        suggestion = result.scalar_one_or_none()

        if not suggestion:
            raise ValueError(f"Vorschlag {suggestion_id} nicht gefunden")

        suggestion.status = "rejected"
        suggestion.responded_at = datetime.now(timezone.utc)
        await self.session.flush()

        logger.info(
            "cluster_suggestion_rejected",
            suggestion_id=str(suggestion_id),
            document_id=str(suggestion.document_id),
        )
        return suggestion

    async def get_pending_suggestions(
        self,
        company_id: UUID,
        document_id: Optional[UUID] = None,
    ) -> List[ClusterSuggestion]:
        """Alle offenen Vorschlaege fuer eine Company.

        Args:
            company_id: UUID der Company
            document_id: Optional UUID eines spezifischen Dokuments

        Returns:
            Liste der offenen ClusterSuggestion-Eintraege
        """
        query = select(ClusterSuggestion).where(
            ClusterSuggestion.company_id == company_id,
            ClusterSuggestion.status == "pending",
        )

        if document_id is not None:
            query = query.where(
                ClusterSuggestion.document_id == document_id,
            )

        query = query.order_by(ClusterSuggestion.similarity_score.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())
