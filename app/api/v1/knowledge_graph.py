"""
Knowledge Graph API Endpoints

REST API für Entity-Relationship Explorer:
- Entity-Graph mit konfigurierbarer Tiefe
- Graph-Exploration via Suche
- Shortest-Path zwischen Nodes
- Community Detection

Feinpoliert und durchdacht - Enterprise Knowledge Graph.
"""

from typing import List, Optional

from app.core.types import JSONDict
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
    response_model=JSONDict,
    summary="Entity-Graph",
    description="Holt Graph um Entity herum mit konfigurierbarer Tiefe"
)
async def get_entity_graph(
    entity_id: UUID,
    depth: int = Query(2, ge=1, le=3, description="Graph-Tiefe (1-3)"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
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
    response_model=JSONDict,
    summary="Graph-Exploration",
    description="Durchsucht Graph nach Entities und Beziehungen"
)
async def explore_graph(
    query: str = Query(..., min_length=2, max_length=100, description="Suchbegriff"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Explore Graph.

    **Sucht in:**
    - Entity-Namen
    - Kundennummern
    - Rechnungsnummern
    - Dokument-Titeln

    **Gibt zurück:** Gefundene Nodes mit direkten Verbindungen

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
    response_model=JSONDict,
    summary="Kürzester Pfad",
    description="Findet kürzesten Pfad zwischen zwei Entities"
)
async def get_shortest_path(
    from_id: UUID = Query(..., alias="from", description="Start-Entity UUID"),
    to_id: UUID = Query(..., alias="to", description="Ziel-Entity UUID"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Findet kürzesten Pfad.

    **Nutzt:** Breadth-First Search (BFS)

    **Gibt zurück:**
    - path: Liste von Node-IDs
    - length: Pfad-Länge
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
            detail="Fehler beim Berechnen des kürzesten Pfads",
        )


@router.get(
    "/communities",
    response_model=List[JSONDict],
    summary="Community Detection",
    description="Findet Communities/Cluster von zusammenhaengenden Entities"
)
async def get_communities(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> List[JSONDict]:
    """
    Findet Communities.

    **Community:** Gruppe von stark verbundenen Entities (z.B. via gemeinsame Dokumente)

    **Nutzt:** Union-Find für Connected Components

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


@router.get(
    "/financial-chain/{entity_id}",
    response_model=JSONDict,
    summary="Finanzkette",
    description="Laedt Finanzketten (Bestellung > Lieferschein > Rechnung > Zahlung) fuer Entity",
)
async def get_financial_chain(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Laedt Finanzketten fuer eine Entity."""
    logger.info(
        "knowledge_graph.get_financial_chain",
        entity_id=str(entity_id),
        user_id=str(current_user.id),
        company_id=str(company_id),
    )
    service = KnowledgeGraphService()
    try:
        result = await service.get_financial_chain(entity_id, company_id, db)
        return result
    except Exception as e:
        logger.error(
            "knowledge_graph.financial_chain_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Finanzkette",
        )


@router.get(
    "/risk-network",
    response_model=JSONDict,
    summary="Risiko-Netzwerk",
    description="Laedt Risiko-Netzwerk mit Communities und Risk Scores",
)
async def get_risk_network(
    entity_id: Optional[UUID] = Query(None, description="Optional: Focus-Entity"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Laedt Risiko-Netzwerk."""
    logger.info(
        "knowledge_graph.get_risk_network",
        entity_id=str(entity_id) if entity_id else None,
        user_id=str(current_user.id),
        company_id=str(company_id),
    )
    service = KnowledgeGraphService()
    try:
        result = await service.get_risk_network(company_id, db, focus_entity_id=entity_id)
        return result
    except Exception as e:
        logger.error(
            "knowledge_graph.risk_network_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Risiko-Netzwerks",
        )


@router.get(
    "/document-family/{document_id}",
    response_model=JSONDict,
    summary="Dokument-Familie",
    description="Laedt verwandte Dokumente gruppiert nach Beziehungstyp",
)
async def get_document_family(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Laedt Dokumentenfamilie."""
    logger.info(
        "knowledge_graph.get_document_family",
        document_id=str(document_id),
        user_id=str(current_user.id),
        company_id=str(company_id),
    )
    service = KnowledgeGraphService()
    try:
        result = await service.get_document_family(document_id, company_id, db)
        return result
    except Exception as e:
        logger.error(
            "knowledge_graph.document_family_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Dokumentenfamilie",
        )
