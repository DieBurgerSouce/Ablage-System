# -*- coding: utf-8 -*-
"""Clustering Celery Tasks.

Tasks fuer automatische Cluster-Vorschlaege, Centroid-Updates
und periodisches DBSCAN-Clustering.

Tasks:
- generate_cluster_suggestions: Nach OCR-Completion Vorschlaege generieren
- rebuild_cluster_centroids: Periodische Centroid-Neuberechnung
- auto_cluster_company: DBSCAN-Clustering fuer eine Company
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from celery.exceptions import SoftTimeLimitExceeded

from app.core.safe_errors import safe_error_log
from app.db.session import get_async_session_context
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine in a Celery task context."""
    return asyncio.run(coro)


# =============================================================================
# Cluster Suggestion Task
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.clustering_tasks.generate_cluster_suggestions",
    soft_time_limit=120,
    time_limit=150,
)
def generate_cluster_suggestions(
    self,
    document_id: str,
    company_id: str,
    top_k: int = 3,
) -> Dict[str, object]:
    """Generiert Cluster-Vorschlaege fuer ein neues Dokument.

    Typischerweise nach OCR-Completion getriggert, wenn das Embedding
    bereits generiert wurde.

    Args:
        document_id: UUID des Dokuments als String
        company_id: UUID der Company als String
        top_k: Anzahl der Top-Vorschlaege (Standard: 3)

    Returns:
        Dictionary mit Vorschlag-Ergebnissen
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)

    logger.info(
        "clustering_task_starting",
        task_id=task_id,
        document_id=document_id,
        company_id=company_id,
        top_k=top_k,
    )

    async def process_async() -> Dict[str, object]:
        from app.services.clustering.cluster_suggestion_service import (
            ClusterSuggestionService,
        )

        async with get_async_session_context() as session:
            try:
                service = ClusterSuggestionService(session)
                suggestions = await service.suggest_for_document(
                    document_id=UUID(document_id),
                    company_id=UUID(company_id),
                    top_k=top_k,
                )
                await session.commit()

                processing_time = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()

                suggestion_data = [
                    {
                        "suggestion_id": str(s.id),
                        "similarity_score": s.similarity_score,
                        "suggested_category": s.suggested_category,
                        "suggested_entity_id": str(s.suggested_entity_id)
                        if s.suggested_entity_id
                        else None,
                        "reference_document_id": str(s.reference_document_id)
                        if s.reference_document_id
                        else None,
                    }
                    for s in suggestions
                ]

                logger.info(
                    "clustering_task_completed",
                    task_id=task_id,
                    document_id=document_id,
                    suggestions_count=len(suggestions),
                    duration_seconds=processing_time,
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "company_id": company_id,
                    "suggestions_count": len(suggestions),
                    "suggestions": suggestion_data,
                    "processing_time_seconds": processing_time,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }

            except SoftTimeLimitExceeded:
                logger.error(
                    "clustering_task_timeout",
                    task_id=task_id,
                    document_id=document_id,
                )
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": "Zeitlimit ueberschritten",
                }

            except ValueError as e:
                # Dokument nicht gefunden oder kein Embedding
                logger.warning(
                    "clustering_task_skipped",
                    task_id=task_id,
                    document_id=document_id,
                    reason=str(e),
                )
                return {
                    "success": False,
                    "document_id": document_id,
                    "skipped": True,
                    "reason": str(e),
                }

            except Exception as e:
                logger.exception(
                    "clustering_task_failed",
                    task_id=task_id,
                    document_id=document_id,
                    **safe_error_log(e),
                )
                raise

    return _run_async(process_async())


# =============================================================================
# Centroid Rebuild Task (Periodic)
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.clustering_tasks.rebuild_cluster_centroids",
    soft_time_limit=600,
    time_limit=660,
)
def rebuild_cluster_centroids(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Periodische Neuberechnung aller Cluster-Centroids.

    Sollte taeglich via Celery Beat ausgefuehrt werden,
    z.B. nachts um 3:00 Uhr.

    Args:
        company_id: Optionale Company-UUID (None = alle Companies)

    Returns:
        Dictionary mit Update-Statistiken
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)

    logger.info(
        "rebuild_centroids_starting",
        task_id=task_id,
        company_id=company_id,
    )

    async def process_async() -> Dict[str, object]:
        from sqlalchemy import select

        from app.db.models_clustering import DocumentCluster
        from app.services.clustering.cluster_management_service import (
            ClusterManagementService,
        )

        async with get_async_session_context() as session:
            try:
                # Aktive Cluster laden
                query = select(DocumentCluster).where(
                    DocumentCluster.is_active.is_(True),
                )
                if company_id:
                    query = query.where(
                        DocumentCluster.company_id == UUID(company_id)
                    )

                result = await session.execute(query)
                clusters = result.scalars().all()

                service = ClusterManagementService(session)
                updated = 0
                failed = 0

                for cluster in clusters:
                    try:
                        await service.update_cluster_centroid(cluster.id)
                        updated += 1
                    except Exception as e:
                        logger.warning(
                            "centroid_update_failed",
                            cluster_id=str(cluster.id),
                            **safe_error_log(e),
                        )
                        failed += 1

                await session.commit()

                processing_time = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()

                logger.info(
                    "rebuild_centroids_completed",
                    task_id=task_id,
                    total_clusters=len(clusters),
                    updated=updated,
                    failed=failed,
                    duration_seconds=processing_time,
                )

                return {
                    "success": True,
                    "total_clusters": len(clusters),
                    "updated": updated,
                    "failed": failed,
                    "processing_time_seconds": processing_time,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }

            except SoftTimeLimitExceeded:
                logger.error(
                    "rebuild_centroids_timeout",
                    task_id=task_id,
                )
                return {
                    "success": False,
                    "error": "Zeitlimit ueberschritten",
                }

            except Exception as e:
                logger.exception(
                    "rebuild_centroids_failed",
                    task_id=task_id,
                    **safe_error_log(e),
                )
                raise

    return _run_async(process_async())


# =============================================================================
# Auto-Clustering Task
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.clustering_tasks.auto_cluster_company",
    soft_time_limit=900,
    time_limit=960,
)
def auto_cluster_company(
    self,
    company_id: str,
    min_cluster_size: int = 3,
    similarity_threshold: float = 0.7,
) -> Dict[str, object]:
    """Fuehrt automatisches Clustering fuer eine Company durch.

    Nutzt Greedy-Clustering auf Basis von pgvector Cosine-Distanzen.

    Args:
        company_id: UUID der Company als String
        min_cluster_size: Minimale Cluster-Groesse (Standard: 3)
        similarity_threshold: Mindest-Aehnlichkeit (Standard: 0.7)

    Returns:
        Dictionary mit Clustering-Ergebnissen
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)

    logger.info(
        "auto_cluster_starting",
        task_id=task_id,
        company_id=company_id,
        min_cluster_size=min_cluster_size,
        similarity_threshold=similarity_threshold,
    )

    async def process_async() -> Dict[str, object]:
        from app.services.clustering.cluster_management_service import (
            ClusterManagementService,
        )

        async with get_async_session_context() as session:
            try:
                service = ClusterManagementService(session)
                new_clusters = await service.auto_cluster_documents(
                    company_id=UUID(company_id),
                    min_cluster_size=min_cluster_size,
                    similarity_threshold=similarity_threshold,
                )
                await session.commit()

                processing_time = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()

                cluster_data = [
                    {
                        "cluster_id": str(c.id),
                        "name": c.name,
                        "document_count": c.document_count,
                        "avg_similarity": c.avg_similarity,
                    }
                    for c in new_clusters
                ]

                logger.info(
                    "auto_cluster_completed",
                    task_id=task_id,
                    company_id=company_id,
                    clusters_created=len(new_clusters),
                    duration_seconds=processing_time,
                )

                return {
                    "success": True,
                    "company_id": company_id,
                    "clusters_created": len(new_clusters),
                    "clusters": cluster_data,
                    "processing_time_seconds": processing_time,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }

            except SoftTimeLimitExceeded:
                logger.error(
                    "auto_cluster_timeout",
                    task_id=task_id,
                    company_id=company_id,
                )
                return {
                    "success": False,
                    "company_id": company_id,
                    "error": "Zeitlimit ueberschritten",
                }

            except Exception as e:
                logger.exception(
                    "auto_cluster_failed",
                    task_id=task_id,
                    company_id=company_id,
                    **safe_error_log(e),
                )
                raise

    return _run_async(process_async())
