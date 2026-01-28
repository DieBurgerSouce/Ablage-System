"""
API Router für External Data Enrichment.

Endpoints für Anreicherung von Geschäftspartnern mit externen Daten.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.external.enrichment_orchestrator import (
    EnrichmentOrchestrator,
    EnrichmentResult,
    SourceInfo,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class EnrichEntityRequest(BaseModel):
    """Request für Entity-Anreicherung."""

    sources: Optional[List[str]] = Field(
        None,
        description="Liste von Quellen (handelsregister, bundesanzeiger). None = alle",
    )


class EnrichmentResultResponse(BaseModel):
    """Enrichment-Result Response."""

    entity_id: UUID
    sources_queried: List[str]
    enriched_fields: Dict[str, Any]
    confidence: float
    cached: bool
    timestamp: datetime

    class Config:
        from_attributes = True


class SourceInfoResponse(BaseModel):
    """Source-Info Response."""

    name: str
    description: str
    available: bool
    last_checked: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/entity/{entity_id}", response_model=EnrichmentResultResponse)
async def enrich_entity(
    entity_id: UUID,
    request: EnrichEntityRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnrichmentResultResponse:
    """
    Reichert Geschäftspartner mit externen Daten an.

    Args:
        entity_id: BusinessEntity-ID
        request: Enrichment-Request mit Quellen
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        EnrichmentResult mit angereicherten Daten

    Raises:
        HTTPException 404: Entity nicht gefunden
        HTTPException 403: Keine Berechtigung
    """
    logger.info(
        "enrich_entity_requested",
        user_id=str(current_user.id),
        entity_id=str(entity_id),
        sources=request.sources,
    )

    try:
        orchestrator = EnrichmentOrchestrator()
        result = await orchestrator.enrich_entity(
            entity_id=entity_id,
            company_id=current_user.company_id,
            sources=request.sources,
            db=db,
        )

        return EnrichmentResultResponse(
            entity_id=result.entity_id,
            sources_queried=result.sources_queried,
            enriched_fields=result.enriched_fields,
            confidence=result.confidence,
            cached=result.cached,
            timestamp=result.timestamp,
        )

    except ValueError as e:
        # Entity nicht gefunden
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "enrich_entity_failed",
            error=str(e),
            entity_id=str(entity_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Datenanreicherung",
        )


@router.get("/sources", response_model=List[SourceInfoResponse])
async def get_available_sources(
    current_user: User = Depends(get_current_user),
) -> List[SourceInfoResponse]:
    """
    Gibt verfügbare Datenquellen zurück.

    Args:
        current_user: Aktueller Benutzer

    Returns:
        Liste von verfügbaren Datenquellen
    """
    logger.info(
        "get_sources_requested",
        user_id=str(current_user.id),
    )

    try:
        orchestrator = EnrichmentOrchestrator()
        sources = await orchestrator.get_available_sources()

        return [
            SourceInfoResponse(
                name=s.name,
                description=s.description,
                available=s.available,
                last_checked=s.last_checked,
            )
            for s in sources
        ]

    except Exception as e:
        logger.error("get_sources_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Datenquellen",
        )


@router.get("/results/{entity_id}", response_model=EnrichmentResultResponse)
async def get_cached_enrichment(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnrichmentResultResponse:
    """
    Gibt gecachte Enrichment-Ergebnisse zurück.

    Args:
        entity_id: BusinessEntity-ID
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        Gecachte Enrichment-Daten (aus Entity.metadata)

    Raises:
        HTTPException 404: Keine gecachten Daten gefunden
    """
    logger.info(
        "get_cached_enrichment_requested",
        user_id=str(current_user.id),
        entity_id=str(entity_id),
    )

    try:
        from sqlalchemy import select
        from app.db.models import BusinessEntity

        # Entity abrufen
        stmt = select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.company_id == current_user.company_id,
        )
        result = await db.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Geschäftspartner nicht gefunden",
            )

        # Enrichment-Daten aus Metadata
        enrichment_data = (
            entity.metadata.get("enrichment") if entity.metadata else None
        )
        if not enrichment_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Keine Enrichment-Daten gefunden",
            )

        # Response konstruieren
        return EnrichmentResultResponse(
            entity_id=entity_id,
            sources_queried=enrichment_data.get("sources", []),
            enriched_fields={
                k: v
                for k, v in entity.metadata.items()
                if k not in ["enrichment"]
            },
            confidence=0.8,  # Default
            cached=True,
            timestamp=datetime.fromisoformat(
                enrichment_data.get("last_updated", datetime.utcnow().isoformat())
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_cached_enrichment_failed",
            error=str(e),
            entity_id=str(entity_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der gecachten Daten",
        )
