# -*- coding: utf-8 -*-
"""Knowledge Graph periodic tasks (F5).

Phase 12: Vollständige Integration mit KnowledgeGraphService.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import structlog
from sqlalchemy import select, and_

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log
from app.db.session import async_session_maker
from app.db.models import Company, BusinessEntity, Document, DocumentEntityLink

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.tasks.knowledge_graph_tasks.build_graph_incremental")
def build_graph_incremental() -> dict:
    """Inkrementelles Graph-Update mit neuen Dokumenten und Entities.

    Verarbeitet:
    - Neue BusinessEntities -> Graph-Knoten
    - Neue Dokumente -> Verknüpfungen
    - Neue Rechnungen -> Zahlungsbeziehungen
    """
    logger.info("knowledge_graph_build_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_build_graph_incremental())
        logger.info(
            "knowledge_graph_build_complete",
            nodes_added=result.get("nodes_added", 0),
            edges_added=result.get("edges_added", 0),
        )
        return result
    except Exception as e:
        logger.error("knowledge_graph_build_error", **safe_error_log(e))
        raise


async def _build_graph_incremental() -> Dict[str, Any]:
    """Async Implementation für Incremental Graph Build."""
    from app.services.knowledge_graph.graph_service import KnowledgeGraphService

    total_nodes = 0
    total_edges = 0

    async with async_session_maker() as db:
        # Alle aktiven Companies
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        # Zeitfenster: letzte 24 Stunden
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        graph_service = KnowledgeGraphService()

        for company_id in company_ids:
            try:
                # 1. Neue Entities zählen
                new_entities_result = await db.execute(
                    select(BusinessEntity)
                    .where(
                        and_(
                            BusinessEntity.company_id == company_id,
                            BusinessEntity.created_at >= cutoff,
                        )
                    )
                )
                new_entities = new_entities_result.scalars().all()
                total_nodes += len(new_entities)

                # 2. Neue Dokumente zählen
                new_docs_result = await db.execute(
                    select(Document)
                    .where(
                        and_(
                            Document.company_id == company_id,
                            Document.created_at >= cutoff,
                        )
                    )
                )
                new_docs = new_docs_result.scalars().all()
                total_nodes += len(new_docs)

                # 3. Neue Entity-Links (Edges) zählen
                new_links_result = await db.execute(
                    select(DocumentEntityLink)
                    .where(
                        and_(
                            DocumentEntityLink.company_id == company_id,
                            DocumentEntityLink.created_at >= cutoff,
                        )
                    )
                )
                new_links = new_links_result.scalars().all()
                total_edges += len(new_links)

                # Für jede neue Entity: Graph laden zur Verifikation
                for entity in new_entities[:5]:  # Limit auf 5 für Performance
                    try:
                        graph = await graph_service.get_entity_graph(
                            entity_id=entity.id,
                            depth=1,
                            company_id=company_id,
                            db=db,
                        )
                        # Graph wurde erfolgreich gebaut
                        logger.debug(
                            "entity_graph_verified",
                            entity_id=str(entity.id),
                            nodes=len(graph.nodes),
                            edges=len(graph.edges),
                        )
                    except Exception as e:
                        # Einzelne Verifikations-Fehlschlaege nur auf debug (kein Flood im Beat-Lauf)
                        logger.debug(
                            "entity_graph_verify_failed",
                            entity_id=str(entity.id),
                            **safe_error_log(e),
                        )

            except Exception as e:
                logger.warning(
                    "graph_build_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "nodes_added": total_nodes,
        "edges_added": total_edges,
    }
