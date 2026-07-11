# -*- coding: utf-8 -*-
"""Semantischer Such-Service fuer Dokumente.

Kombiniert pgvector Cosine-Aehnlichkeit mit dem bestehenden
EmbeddingService fuer natuerlichsprachliche Dokumentensuche.

Funktionen:
- Semantische Suche ueber alle Dokumente (natuerliche Sprache)
- Aehnliche Dokumente finden (Vektor-Aehnlichkeit)
- Embedding-Generierung nach OCR (Pipeline-Integration)
- Batch-Verarbeitung unverarbeiteter Dokumente
- Embedding-Abdeckungsstatistiken
"""

import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.db.models import Document
from app.services.embedding_service import (
    EmbeddingService,
    get_embedding_service,
)
from app.services.reranker_service import RerankerService, get_reranker_service

logger = structlog.get_logger(__name__)


# ============================================================================
# Ergebnis-Datenklassen
# ============================================================================


class SimilarDocumentResult:
    """Ergebnis fuer aehnliche Dokumente."""

    __slots__ = (
        "document_id", "filename", "document_type",
        "similarity", "created_at", "text_preview",
    )

    def __init__(
        self,
        document_id: uuid.UUID,
        filename: str,
        document_type: Optional[str],
        similarity: float,
        created_at: Optional[datetime],
        text_preview: Optional[str],
    ) -> None:
        self.document_id = document_id
        self.filename = filename
        self.document_type = document_type
        self.similarity = similarity
        self.created_at = created_at
        self.text_preview = text_preview


class SemanticSearchResult:
    """Ergebnis der semantischen Suche."""

    __slots__ = (
        "document_id", "filename", "original_filename",
        "document_type", "similarity", "created_at",
        "text_preview", "page_count",
    )

    def __init__(
        self,
        document_id: uuid.UUID,
        filename: str,
        original_filename: Optional[str],
        document_type: Optional[str],
        similarity: float,
        created_at: Optional[datetime],
        text_preview: Optional[str],
        page_count: Optional[int],
    ) -> None:
        self.document_id = document_id
        self.filename = filename
        self.original_filename = original_filename
        self.document_type = document_type
        self.similarity = similarity
        self.created_at = created_at
        self.text_preview = text_preview
        self.page_count = page_count


class EmbeddingCoverageStats:
    """Statistik zur Embedding-Abdeckung."""

    __slots__ = (
        "total_documents", "documents_with_embedding",
        "documents_without_embedding", "coverage_percent",
        "embedding_model", "oldest_embedding", "newest_embedding",
    )

    def __init__(
        self,
        total_documents: int,
        documents_with_embedding: int,
        documents_without_embedding: int,
        coverage_percent: float,
        embedding_model: str,
        oldest_embedding: Optional[datetime],
        newest_embedding: Optional[datetime],
    ) -> None:
        self.total_documents = total_documents
        self.documents_with_embedding = documents_with_embedding
        self.documents_without_embedding = documents_without_embedding
        self.coverage_percent = coverage_percent
        self.embedding_model = embedding_model
        self.oldest_embedding = oldest_embedding
        self.newest_embedding = newest_embedding


# ============================================================================
# Service
# ============================================================================


class SemanticSearchService:
    """Semantische Dokumentensuche mit Embeddings.

    Nutzt pgvector Cosine-Distance fuer Vektor-Aehnlichkeitssuche
    und den bestehenden EmbeddingService fuer Embedding-Generierung.
    """

    def __init__(self) -> None:
        self._embedding_service: Optional[EmbeddingService] = None
        self._reranker: Optional[RerankerService] = None

    def _get_embedding_service(self) -> EmbeddingService:
        """Lazy-load EmbeddingService."""
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _get_reranker(self) -> RerankerService:
        """Lazy-load RerankerService."""
        if self._reranker is None:
            self._reranker = get_reranker_service()
        return self._reranker

    # ========================================================================
    # Semantische Suche
    # ========================================================================

    async def semantic_search(
        self,
        query: str,
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        threshold: float = 0.5,
        document_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        rerank: bool = True,
    ) -> List[SemanticSearchResult]:
        """Natuerlichsprachliche Suche ueber Dokumente.

        Generiert ein Query-Embedding und sucht per pgvector
        Cosine-Distance nach den aehnlichsten Dokumenten.
        Optional mit Cross-Encoder Reranking.

        Args:
            query: Natuerlichsprachliche Suchanfrage
            session: Async SQLAlchemy Session
            user_id: Benutzer-ID fuer Zugriffsrechte
            limit: Maximale Ergebnisanzahl
            threshold: Minimaler Aehnlichkeitsscore (0-1)
            document_type: Optionaler Dokumenttyp-Filter
            date_from: Optionaler Datumsfilter (ab)
            date_to: Optionaler Datumsfilter (bis)
            rerank: Cross-Encoder Reranking aktivieren

        Returns:
            Liste von SemanticSearchResult sortiert nach Aehnlichkeit
        """
        start_time = time.perf_counter()
        embedding_service = self._get_embedding_service()

        # Query-Embedding generieren (mit Cache)
        query_embedding = await embedding_service.generate_query_embedding_cached(
            query
        )
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Dynamische Filter aufbauen
        filters = []
        params: dict = {
            "embedding": embedding_str,
            "user_id": str(user_id),
            "threshold": threshold,
            "limit": limit * 3 if rerank else limit,  # Mehr holen fuer Reranking
        }

        if document_type:
            filters.append("AND d.document_type = :doc_type")
            params["doc_type"] = document_type
        if date_from:
            filters.append("AND d.created_at >= :date_from")
            params["date_from"] = date_from
        if date_to:
            filters.append("AND d.created_at <= :date_to")
            params["date_to"] = date_to

        filter_clause = "\n                ".join(filters)

        search_query = text(f"""
            WITH accessible_docs AS (
                SELECT id AS document_id FROM documents
                WHERE owner_id = :user_id AND deleted_at IS NULL
                UNION
                SELECT document_id FROM document_access
                WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
            )
            SELECT
                d.id AS document_id,
                d.filename,
                d.original_filename,
                d.document_type,
                1 - (d.embedding <=> CAST(:embedding AS vector)) AS similarity,
                d.created_at,
                LEFT(d.extracted_text, 300) AS text_preview,
                d.page_count
            FROM documents d
            WHERE d.id IN (SELECT document_id FROM accessible_docs)
                AND d.embedding IS NOT NULL
                AND d.deleted_at IS NULL
                AND 1 - (d.embedding <=> CAST(:embedding AS vector)) >= :threshold
                {filter_clause}
            ORDER BY d.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        result = await session.execute(search_query, params)
        rows = result.fetchall()

        results = [
            SemanticSearchResult(
                document_id=row.document_id,
                filename=row.filename,
                original_filename=row.original_filename,
                document_type=row.document_type,
                similarity=float(row.similarity),
                created_at=row.created_at,
                text_preview=row.text_preview,
                page_count=row.page_count,
            )
            for row in rows
        ]

        # Optional: Cross-Encoder Reranking
        if rerank and len(results) > 1 and settings.RAG_RERANK_ENABLED:
            results = await self._rerank_results(query, results, limit)

        # Auf limit beschraenken (nach Reranking)
        results = results[:limit]

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "semantic_search_completed",
            query_length=len(query),
            result_count=len(results),
            threshold=threshold,
            reranked=rerank,
            elapsed_ms=round(elapsed_ms, 1),
        )

        return results

    async def _rerank_results(
        self,
        query: str,
        results: List[SemanticSearchResult],
        top_k: int,
    ) -> List[SemanticSearchResult]:
        """Reranke Ergebnisse mit Cross-Encoder."""
        try:
            reranker = self._get_reranker()
            documents = [r.text_preview or r.filename for r in results]

            reranked = await reranker.rerank_async(
                query=query,
                documents=documents,
                top_k=top_k,
            )

            # Ergebnisse nach Reranking-Score neu ordnen
            reordered: List[SemanticSearchResult] = []
            for ranked_item in reranked:
                if ranked_item.index < len(results):
                    item = results[ranked_item.index]
                    # Kombiniere Scores: 70% Semantic + 30% Rerank
                    item.similarity = (
                        0.7 * item.similarity
                        + 0.3 * max(0.0, min(1.0, ranked_item.score))
                    )
                    reordered.append(item)

            return reordered

        except Exception as e:
            logger.warning(
                "reranking_failed_fallback_to_semantic",
                **safe_error_log(e),
            )
            return results

    # ========================================================================
    # Aehnliche Dokumente
    # ========================================================================

    async def find_similar_documents(
        self,
        document_id: uuid.UUID,
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> List[SimilarDocumentResult]:
        """Finde aehnliche Dokumente basierend auf Vektor-Aehnlichkeit.

        Laedt das Embedding des Quelldokuments und sucht per pgvector
        Cosine-Distance nach aehnlichen Dokumenten.

        Args:
            document_id: ID des Quelldokuments
            session: Async SQLAlchemy Session
            user_id: Benutzer-ID fuer Zugriffsrechte
            limit: Maximale Ergebnisanzahl
            threshold: Minimaler Aehnlichkeitsscore (0-1)

        Returns:
            Liste von SimilarDocumentResult
        """
        start_time = time.perf_counter()

        # Quelldokument laden mit Zugriffspruefung
        source_doc = await session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )
        source = source_doc.scalar_one_or_none()

        if source is None:
            logger.warning(
                "similar_doc_source_not_found",
                document_id=str(document_id),
            )
            return []

        if source.embedding is None:
            logger.warning(
                "similar_doc_no_embedding",
                document_id=str(document_id),
            )
            return []

        embedding_str = "[" + ",".join(str(x) for x in source.embedding) + "]"

        similar_query = text("""
            WITH accessible_docs AS (
                SELECT id AS document_id FROM documents
                WHERE owner_id = :user_id AND deleted_at IS NULL
                UNION
                SELECT document_id FROM document_access
                WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
            )
            SELECT
                d.id AS document_id,
                d.filename,
                d.document_type,
                1 - (d.embedding <=> CAST(:embedding AS vector)) AS similarity,
                d.created_at,
                LEFT(d.extracted_text, 300) AS text_preview
            FROM documents d
            WHERE d.id IN (SELECT document_id FROM accessible_docs)
                AND d.id != :source_id
                AND d.embedding IS NOT NULL
                AND d.deleted_at IS NULL
                AND 1 - (d.embedding <=> CAST(:embedding AS vector)) >= :threshold
            ORDER BY d.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        result = await session.execute(
            similar_query,
            {
                "embedding": embedding_str,
                "user_id": str(user_id),
                "source_id": str(document_id),
                "threshold": threshold,
                "limit": limit,
            },
        )
        rows = result.fetchall()

        results = [
            SimilarDocumentResult(
                document_id=row.document_id,
                filename=row.filename,
                document_type=row.document_type,
                similarity=float(row.similarity),
                created_at=row.created_at,
                text_preview=row.text_preview,
            )
            for row in rows
        ]

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "find_similar_completed",
            source_document_id=str(document_id),
            result_count=len(results),
            elapsed_ms=round(elapsed_ms, 1),
        )

        return results

    # ========================================================================
    # Embedding-Generierung
    # ========================================================================

    async def embed_document(
        self,
        document_id: uuid.UUID,
        session: AsyncSession,
    ) -> bool:
        """Generiere Embedding fuer ein Dokument nach OCR.

        Laedt den extrahierten Text des Dokuments und generiert
        ein Embedding mit dem konfigurierten Modell.

        Args:
            document_id: Dokument-ID
            session: Async SQLAlchemy Session

        Returns:
            True wenn Embedding erfolgreich generiert
        """
        embedding_service = self._get_embedding_service()

        doc_result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = doc_result.scalar_one_or_none()

        if document is None:
            logger.warning(
                "embed_doc_not_found",
                document_id=str(document_id),
            )
            return False

        if not document.extracted_text:
            logger.warning(
                "embed_doc_no_text",
                document_id=str(document_id),
            )
            return False

        if document.embedding is not None:
            logger.debug(
                "embed_doc_already_has_embedding",
                document_id=str(document_id),
            )
            return True

        try:
            embedding = await embedding_service.generate_embedding_async(
                document.extracted_text, is_query=False
            )

            document.embedding = embedding
            document.embedding_updated_at = datetime.now(timezone.utc)
            document.embedding_model = settings.EMBEDDING_MODEL

            await session.commit()

            logger.info(
                "embed_doc_completed",
                document_id=str(document_id),
                dimension=len(embedding),
            )
            return True

        except Exception as e:
            logger.error(
                "embed_doc_failed",
                document_id=str(document_id),
                **safe_error_log(e),
            )
            await session.rollback()
            return False

    # ========================================================================
    # Batch-Verarbeitung
    # ========================================================================

    async def batch_embed_unprocessed(
        self,
        session: AsyncSession,
        batch_size: int = 100,
    ) -> int:
        """Batch-Verarbeitung: Embeddings fuer Dokumente ohne Vektor.

        Findet Dokumente mit extrahiertem Text aber ohne Embedding
        und generiert Embeddings in Batches.

        Args:
            session: Async SQLAlchemy Session
            batch_size: Anzahl Dokumente pro Batch

        Returns:
            Anzahl erfolgreich verarbeiteter Dokumente
        """
        embedding_service = self._get_embedding_service()

        # Dokumente ohne Embedding finden
        query = (
            select(Document.id, Document.extracted_text)
            .where(
                Document.embedding.is_(None),
                Document.extracted_text.isnot(None),
                Document.deleted_at.is_(None),
                Document.status == "completed",
            )
            .limit(batch_size)
        )

        result = await session.execute(query)
        docs = result.fetchall()

        if not docs:
            logger.info("batch_embed_no_unprocessed_docs")
            return 0

        logger.info(
            "batch_embed_starting",
            document_count=len(docs),
            batch_size=batch_size,
        )

        # Texte extrahieren
        doc_ids = [row.id for row in docs]
        texts = [row.extracted_text for row in docs]

        # Batch-Embeddings generieren
        try:
            embeddings = await embedding_service.generate_batch_embeddings_async(
                texts, is_query=False
            )
        except Exception as e:
            logger.error(
                "batch_embed_generation_failed",
                **safe_error_log(e),
            )
            return 0

        # Embeddings speichern
        success_count = 0
        now = datetime.now(timezone.utc)

        for doc_id, embedding in zip(doc_ids, embeddings):
            # Null-Vektor pruefen (Fallback bei OOM)
            if all(v == 0.0 for v in embedding):
                logger.warning(
                    "batch_embed_zero_vector_skipped",
                    document_id=str(doc_id),
                )
                continue

            try:
                await session.execute(
                    text("""
                        UPDATE documents
                        SET embedding = CAST(:embedding AS vector),
                            embedding_updated_at = :updated_at,
                            embedding_model = :model
                        WHERE id = :doc_id
                    """),
                    {
                        "embedding": "[" + ",".join(str(x) for x in embedding) + "]",
                        "updated_at": now,
                        "model": settings.EMBEDDING_MODEL,
                        "doc_id": str(doc_id),
                    },
                )
                success_count += 1
            except Exception as e:
                logger.error(
                    "batch_embed_update_failed",
                    document_id=str(doc_id),
                    **safe_error_log(e),
                )

        await session.commit()

        logger.info(
            "batch_embed_completed",
            total=len(docs),
            success=success_count,
            failed=len(docs) - success_count,
        )

        return success_count

    # ========================================================================
    # Statistiken
    # ========================================================================

    async def get_embedding_coverage(
        self,
        session: AsyncSession,
    ) -> EmbeddingCoverageStats:
        """Statistik: Wie viele Dokumente haben Embeddings?

        Args:
            session: Async SQLAlchemy Session

        Returns:
            EmbeddingCoverageStats mit Abdeckungsinformationen
        """
        # Gesamtanzahl (nicht geloescht, abgeschlossen)
        total_query = select(func.count(Document.id)).where(
            Document.deleted_at.is_(None),
            Document.status == "completed",
        )
        total_result = await session.execute(total_query)
        total_docs = total_result.scalar() or 0

        # Mit Embedding
        with_embedding_query = select(func.count(Document.id)).where(
            Document.deleted_at.is_(None),
            Document.status == "completed",
            Document.embedding.isnot(None),
        )
        with_result = await session.execute(with_embedding_query)
        with_embedding = with_result.scalar() or 0

        without_embedding = total_docs - with_embedding
        coverage = (with_embedding / total_docs * 100.0) if total_docs > 0 else 0.0

        # Zeitbereich der Embeddings
        date_query = select(
            func.min(Document.embedding_updated_at),
            func.max(Document.embedding_updated_at),
        ).where(
            Document.embedding.isnot(None),
            Document.deleted_at.is_(None),
        )
        date_result = await session.execute(date_query)
        date_row = date_result.first()

        oldest = date_row[0] if date_row else None
        newest = date_row[1] if date_row else None

        return EmbeddingCoverageStats(
            total_documents=total_docs,
            documents_with_embedding=with_embedding,
            documents_without_embedding=without_embedding,
            coverage_percent=round(coverage, 2),
            embedding_model=settings.EMBEDDING_MODEL,
            oldest_embedding=oldest,
            newest_embedding=newest,
        )


# ============================================================================
# Singleton
# ============================================================================

_semantic_search_service: Optional[SemanticSearchService] = None


def get_semantic_search_service() -> SemanticSearchService:
    """Gibt Singleton-Instanz des SemanticSearchService zurueck."""
    global _semantic_search_service
    if _semantic_search_service is None:
        _semantic_search_service = SemanticSearchService()
    return _semantic_search_service
