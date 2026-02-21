# -*- coding: utf-8 -*-
"""Dokumenten-Clustering API Endpoints.

Enterprise Feature: Automatische Gruppierung aehnlicher Dokumente
fuer intelligente Ablage-Vorschlaege und Cluster-Visualisierung.

Endpoints:
- POST /documents/{id}/cluster-suggestions  - Vorschlaege generieren
- GET  /documents/{id}/cluster-suggestions  - Offene Vorschlaege abrufen
- POST /cluster-suggestions/{id}/accept     - Vorschlag akzeptieren
- POST /cluster-suggestions/{id}/reject     - Vorschlag ablehnen
- GET  /clusters                            - Cluster auflisten
- POST /clusters                            - Manuellen Cluster erstellen
- GET  /clusters/{id}                       - Cluster-Detail
- GET  /clusters/{id}/graph                 - Graph-Daten fuer Visualisierung
- POST /clusters/auto-generate              - Automatisches Clustering starten
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_current_company_id, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.clustering.cluster_suggestion_service import ClusterSuggestionService
from app.services.clustering.cluster_management_service import ClusterManagementService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Dokumenten-Clustering"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ClusterSuggestionResponse(BaseModel):
    """Einzelner Cluster-Vorschlag."""

    id: UUID
    document_id: UUID
    suggested_cluster_id: Optional[UUID] = None
    suggested_entity_id: Optional[UUID] = None
    suggested_category: Optional[str] = None
    similarity_score: float = Field(..., description="Aehnlichkeitswert (0-1)")
    reference_document_id: Optional[UUID] = None
    status: str
    responded_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClusterSuggestionListResponse(BaseModel):
    """Liste von Cluster-Vorschlaegen."""

    document_id: UUID
    suggestions: List[ClusterSuggestionResponse]
    total: int


class ClusterCreateRequest(BaseModel):
    """Request zum Erstellen eines manuellen Clusters."""

    name: str = Field(..., min_length=1, max_length=255, description="Cluster-Name")
    description: Optional[str] = Field(None, description="Optionale Beschreibung")
    cluster_type: str = Field("manual", description="Typ: manual, entity, category")
    business_entity_id: Optional[UUID] = Field(None, description="Optionale Entity-Zuordnung")
    parent_cluster_id: Optional[UUID] = Field(None, description="Optionaler uebergeordneter Cluster")


class ClusterResponse(BaseModel):
    """Einzelner Cluster."""

    id: UUID
    name: str
    description: Optional[str] = None
    cluster_type: str
    document_count: int
    avg_similarity: Optional[float] = None
    company_id: UUID
    business_entity_id: Optional[UUID] = None
    parent_cluster_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClusterListResponse(BaseModel):
    """Paginierte Cluster-Liste."""

    clusters: List[ClusterResponse]
    total: int
    limit: int
    offset: int


class GraphNodeResponse(BaseModel):
    """Knoten im Cluster-Graph."""

    id: str
    label: str
    type: str = Field(..., description="document oder cluster")
    size: int
    metadata: Dict[str, object] = Field(default_factory=dict)


class GraphEdgeResponse(BaseModel):
    """Kante im Cluster-Graph."""

    source: str
    target: str
    weight: float
    label: str


class ClusterGraphResponse(BaseModel):
    """Graph-Daten fuer Cluster-Visualisierung."""

    nodes: List[GraphNodeResponse]
    edges: List[GraphEdgeResponse]


class AutoClusterRequest(BaseModel):
    """Request fuer automatisches Clustering."""

    min_cluster_size: int = Field(3, ge=2, le=50, description="Minimale Cluster-Groesse")
    similarity_threshold: float = Field(
        0.7, ge=0.3, le=1.0, description="Mindest-Aehnlichkeit (0.3-1.0)"
    )


class AutoClusterResponse(BaseModel):
    """Ergebnis des automatischen Clusterings."""

    clusters_created: int
    clusters: List[ClusterResponse]
    message: str


class ClusterStatsResponse(BaseModel):
    """Statistik eines Clusters."""

    cluster_id: str
    name: str
    cluster_type: str
    document_count: int
    avg_similarity: Optional[float] = None
    is_active: bool
    created_at: Optional[str] = None
    actual_member_count: int


class MergeClustersRequest(BaseModel):
    """Request zum Zusammenfuehren von Clustern."""

    cluster_ids: List[UUID] = Field(
        ..., min_length=2, description="Mindestens 2 Cluster-UUIDs"
    )


# =============================================================================
# Cluster-Suggestion Endpoints
# =============================================================================


@router.post(
    "/documents/{document_id}/cluster-suggestions",
    response_model=ClusterSuggestionListResponse,
    summary="Cluster-Vorschlaege generieren",
    description="Analysiert ein Dokument und schlaegt aehnliche Cluster/Entitaeten/Kategorien vor.",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Vorschlaege erfolgreich generiert"},
        404: {"description": "Dokument nicht gefunden"},
        422: {"description": "Dokument hat kein Embedding"},
        429: {"description": "Rate Limit ueberschritten"},
    },
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def generate_cluster_suggestions(
    request: Request,
    document_id: UUID = Path(..., description="ID des Dokuments"),
    top_k: int = Query(3, ge=1, le=10, description="Anzahl Vorschlaege"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> ClusterSuggestionListResponse:
    """Generiert Cluster-Vorschlaege fuer ein Dokument."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    logger.info(
        "generate_cluster_suggestions_request",
        document_id=str(document_id),
        user_id=str(current_user.id),
        top_k=top_k,
    )

    try:
        service = ClusterSuggestionService(db)
        suggestions = await service.suggest_for_document(
            document_id=document_id,
            company_id=company_id,
            top_k=top_k,
        )
        await db.commit()

        return ClusterSuggestionListResponse(
            document_id=document_id,
            suggestions=[
                ClusterSuggestionResponse.model_validate(s) for s in suggestions
            ],
            total=len(suggestions),
        )

    except ValueError as e:
        error_msg = str(e)
        if "kein Embedding" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_msg,
        )
    except Exception as e:
        logger.error(
            "generate_cluster_suggestions_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Generieren der Cluster-Vorschlaege",
        )


@router.get(
    "/documents/{document_id}/cluster-suggestions",
    response_model=ClusterSuggestionListResponse,
    summary="Offene Vorschlaege abrufen",
    description="Gibt alle offenen (pending) Vorschlaege fuer ein Dokument zurueck.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_document_suggestions(
    request: Request,
    document_id: UUID = Path(..., description="ID des Dokuments"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> ClusterSuggestionListResponse:
    """Gibt offene Vorschlaege fuer ein Dokument zurueck."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    service = ClusterSuggestionService(db)
    suggestions = await service.get_pending_suggestions(
        company_id=company_id,
        document_id=document_id,
    )

    return ClusterSuggestionListResponse(
        document_id=document_id,
        suggestions=[
            ClusterSuggestionResponse.model_validate(s) for s in suggestions
        ],
        total=len(suggestions),
    )


@router.post(
    "/cluster-suggestions/{suggestion_id}/accept",
    response_model=ClusterSuggestionResponse,
    summary="Vorschlag akzeptieren",
    description="Akzeptiert einen Cluster-Vorschlag.",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def accept_suggestion(
    request: Request,
    suggestion_id: UUID = Path(..., description="ID des Vorschlags"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ClusterSuggestionResponse:
    """Akzeptiert einen Cluster-Vorschlag."""
    try:
        service = ClusterSuggestionService(db)
        suggestion = await service.accept_suggestion(suggestion_id)
        await db.commit()
        return ClusterSuggestionResponse.model_validate(suggestion)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "accept_suggestion_error",
            suggestion_id=str(suggestion_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Akzeptieren des Vorschlags",
        )


@router.post(
    "/cluster-suggestions/{suggestion_id}/reject",
    response_model=ClusterSuggestionResponse,
    summary="Vorschlag ablehnen",
    description="Lehnt einen Cluster-Vorschlag ab.",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def reject_suggestion(
    request: Request,
    suggestion_id: UUID = Path(..., description="ID des Vorschlags"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ClusterSuggestionResponse:
    """Lehnt einen Cluster-Vorschlag ab."""
    try:
        service = ClusterSuggestionService(db)
        suggestion = await service.reject_suggestion(suggestion_id)
        await db.commit()
        return ClusterSuggestionResponse.model_validate(suggestion)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "reject_suggestion_error",
            suggestion_id=str(suggestion_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Ablehnen des Vorschlags",
        )


# =============================================================================
# Cluster Management Endpoints
# =============================================================================


@router.get(
    "/clusters",
    response_model=ClusterListResponse,
    summary="Cluster auflisten",
    description="Listet alle Cluster einer Company paginiert und filterbar auf.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def list_clusters(
    request: Request,
    cluster_type: Optional[str] = Query(None, description="Typ-Filter: auto, manual, entity, category"),
    is_active: Optional[bool] = Query(True, description="Nur aktive Cluster"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    offset: int = Query(0, ge=0, description="Offset fuer Paginierung"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> ClusterListResponse:
    """Listet Cluster auf."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    service = ClusterManagementService(db)

    clusters = await service.list_clusters(
        company_id=company_id,
        cluster_type=cluster_type,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    total = await service.count_clusters(
        company_id=company_id,
        cluster_type=cluster_type,
        is_active=is_active,
    )

    return ClusterListResponse(
        clusters=[ClusterResponse.model_validate(c) for c in clusters],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/clusters",
    response_model=ClusterResponse,
    summary="Manuellen Cluster erstellen",
    description="Erstellt einen neuen manuellen Cluster.",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def create_cluster(
    request: Request,
    body: ClusterCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> ClusterResponse:
    """Erstellt einen manuellen Cluster."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    try:
        service = ClusterManagementService(db)
        cluster = await service.create_cluster(
            name=body.name,
            company_id=company_id,
            cluster_type=body.cluster_type,
            description=body.description,
            business_entity_id=body.business_entity_id,
            parent_cluster_id=body.parent_cluster_id,
        )
        await db.commit()
        return ClusterResponse.model_validate(cluster)
    except Exception as e:
        logger.error("create_cluster_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen des Clusters",
        )


@router.get(
    "/clusters/{cluster_id}",
    response_model=ClusterResponse,
    summary="Cluster-Detail",
    description="Gibt Details eines Clusters zurueck.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_cluster_detail(
    request: Request,
    cluster_id: UUID = Path(..., description="ID des Clusters"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> ClusterResponse:
    """Gibt Cluster-Details zurueck."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    service = ClusterManagementService(db)
    cluster = await service.get_cluster(cluster_id, company_id)

    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster {cluster_id} nicht gefunden",
        )

    return ClusterResponse.model_validate(cluster)


@router.get(
    "/clusters/{cluster_id}/graph",
    response_model=ClusterGraphResponse,
    summary="Cluster-Graph abrufen",
    description="Gibt Graph-Daten (Knoten + Kanten) fuer Cluster-Visualisierung zurueck.",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_cluster_graph(
    request: Request,
    cluster_id: UUID = Path(..., description="ID des Clusters"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> ClusterGraphResponse:
    """Gibt Graph-Daten fuer Cluster-Visualisierung zurueck."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    try:
        service = ClusterManagementService(db)
        graph_data = await service.get_cluster_graph_data(cluster_id, company_id)

        return ClusterGraphResponse(
            nodes=[GraphNodeResponse(**n) for n in graph_data["nodes"]],
            edges=[GraphEdgeResponse(**e) for e in graph_data["edges"]],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "get_cluster_graph_error",
            cluster_id=str(cluster_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Graph-Daten",
        )


@router.post(
    "/clusters/auto-generate",
    response_model=AutoClusterResponse,
    summary="Automatisches Clustering starten",
    description="Startet automatisches Clustering aller unzugeordneten Dokumente.",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def auto_generate_clusters(
    request: Request,
    body: AutoClusterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> AutoClusterResponse:
    """Startet automatisches Clustering."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    logger.info(
        "auto_cluster_request",
        user_id=str(current_user.id),
        company_id=str(company_id),
        min_cluster_size=body.min_cluster_size,
        similarity_threshold=body.similarity_threshold,
    )

    try:
        service = ClusterManagementService(db)
        new_clusters = await service.auto_cluster_documents(
            company_id=company_id,
            min_cluster_size=body.min_cluster_size,
            similarity_threshold=body.similarity_threshold,
        )
        await db.commit()

        return AutoClusterResponse(
            clusters_created=len(new_clusters),
            clusters=[ClusterResponse.model_validate(c) for c in new_clusters],
            message=f"{len(new_clusters)} Cluster automatisch erstellt",
        )
    except Exception as e:
        logger.error(
            "auto_generate_clusters_error",
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim automatischen Clustering",
        )


@router.post(
    "/clusters/merge",
    response_model=ClusterResponse,
    summary="Cluster zusammenfuehren",
    description="Fuehrt mehrere Cluster zu einem zusammen.",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def merge_clusters(
    request: Request,
    body: MergeClustersRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> ClusterResponse:
    """Fuehrt Cluster zusammen."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    try:
        service = ClusterManagementService(db)
        merged = await service.merge_clusters(body.cluster_ids, company_id)
        await db.commit()

        if not merged:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Zusammenfuehrung fehlgeschlagen",
            )

        return ClusterResponse.model_validate(merged)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "merge_clusters_error",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Zusammenfuehren der Cluster",
        )


@router.get(
    "/clusters/stats",
    response_model=List[ClusterStatsResponse],
    summary="Cluster-Statistiken",
    description="Gibt Statistiken aller Cluster einer Company zurueck.",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_cluster_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> List[ClusterStatsResponse]:
    """Gibt Cluster-Statistiken zurueck."""
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company-Kontext erforderlich",
        )

    service = ClusterManagementService(db)
    stats = await service.get_cluster_stats(company_id)
    return [ClusterStatsResponse(**s) for s in stats]
