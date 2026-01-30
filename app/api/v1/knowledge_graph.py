"""
Knowledge Graph API Endpoints

REST API fuer Entity-Relationship Explorer:
- Entity-Graph mit konfigurierbarer Tiefe
- Graph-Exploration via Suche
- Shortest-Path zwischen Nodes
- Community Detection

Feinpoliert und durchdacht - Enterprise Knowledge Graph.
"""

from typing import Dict, List, Any, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, get_current_company_id
from app.services.knowledge_graph.graph_service import KnowledgeGraphService
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/knowledge-graph", tags=["Knowledge Graph"])


# =============================================================================
# Knowledge Graph Endpoints
# =============================================================================


@router.get(
    "/entity/{entity_id}",
    response_model=Dict[str, Any],
    summary="Entity-Graph",
    description="Holt Graph um Entity herum mit konfigurierbarer Tiefe"
)
async def get_entity_graph(
    entity_id: UUID,
    depth: int = Query(2, ge=1, le=3, description="Graph-Tiefe (1-3)"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Holt Graph um Entity.

    **Graph-Elemente:**
    - **Nodes**: Entities, Documents, Invoices, Transactions
    - **Edges**: CONTAINS_DOCUMENT, ISSUED_TO, PAID_VIA, REFERENCES

    **Parameter:**
    - **depth**: Graph-Tiefe (1 = direkt verbunden, 2 = 2nd degree, 3 = 3rd degree)

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "knowledge_graph.get_entity_graph",
        entity_id=str(entity_id),
        depth=depth,
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = KnowledgeGraphService()

    try:
        graph_data = await service.get_entity_graph(entity_id, depth, company_id, db)

        if not graph_data.nodes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity nicht gefunden oder keine Verbindungen vorhanden",
            )

        return graph_data.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "knowledge_graph.entity_graph_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Entity-Graphs",
        )


@router.get(
    "/explore",
    response_model=Dict[str, Any],
    summary="Graph-Exploration",
    description="Durchsucht Graph nach Entities und Beziehungen"
)
async def explore_graph(
    query: str = Query(..., min_length=2, max_length=100, description="Suchbegriff"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Explore Graph.

    **Sucht in:**
    - Entity-Namen
    - Kundennummern
    - Rechnungsnummern
    - Dokument-Titeln

    **Gibt zurueck:** Gefundene Nodes mit direkten Verbindungen

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "knowledge_graph.explore",
        query=query,
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = KnowledgeGraphService()

    try:
        graph_data = await service.explore(query, company_id, db)
        return graph_data.to_dict()
    except Exception as e:
        logger.error(
            "knowledge_graph.explore_failed",
            query=query,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Graph-Exploration",
        )


@router.get(
    "/shortest-path",
    response_model=Dict[str, Any],
    summary="Kuerzester Pfad",
    description="Findet kuerzesten Pfad zwischen zwei Entities"
)
async def get_shortest_path(
    from_id: UUID = Query(..., alias="from", description="Start-Entity UUID"),
    to_id: UUID = Query(..., alias="to", description="Ziel-Entity UUID"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Findet kuerzesten Pfad.

    **Nutzt:** Breadth-First Search (BFS)

    **Gibt zurueck:**
    - path: Liste von Node-IDs
    - length: Pfad-Laenge
    - nodes: Node-Details
    - edges: Edge-Details

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "knowledge_graph.shortest_path",
        from_id=str(from_id),
        to_id=str(to_id),
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = KnowledgeGraphService()

    try:
        path_data = await service.get_shortest_path(from_id, to_id, company_id, db)

        if not path_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kein Pfad zwischen Entities gefunden",
            )

        return path_data.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "knowledge_graph.shortest_path_failed",
            from_id=str(from_id),
            to_id=str(to_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Berechnen des kuerzesten Pfads",
        )


@router.get(
    "/communities",
    response_model=List[Dict[str, Any]],
    summary="Community Detection",
    description="Findet Communities/Cluster von zusammenhaengenden Entities"
)
async def get_communities(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Findet Communities.

    **Community:** Gruppe von stark verbundenen Entities (z.B. via gemeinsame Dokumente)

    **Nutzt:** Union-Find fuer Connected Components

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "knowledge_graph.get_communities",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = KnowledgeGraphService()

    try:
        communities = await service.get_communities(company_id, db)
        return [c.to_dict() for c in communities]
    except Exception as e:
        logger.error(
            "knowledge_graph.communities_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Community Detection",
        )
