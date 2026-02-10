"""
API-Endpunkte fuer Datenqualitaets-Ampel.

Bietet Qualitaetsbewertung und Ampel-Status fuer Dokumente.
"""

from typing import Dict, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.core.safe_errors import safe_error_log
from app.core.rate_limiting import limiter, get_user_identifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/document-quality", tags=["document-quality"])


# =============================================================================
# Response Models
# =============================================================================


class QualityDimensionResponse(BaseModel):
    """Einzelne Qualitaetsdimension."""
    name: str = Field(..., description="Name der Dimension")
    score: float = Field(..., description="Score 0.0-1.0")
    weight: float = Field(..., description="Gewichtung")
    details: str = Field(..., description="Beschreibung")
    sub_scores: Dict[str, float] = Field(default_factory=dict, description="Unter-Scores")


class DocumentQualityResponse(BaseModel):
    """Qualitaetsbewertung eines Dokuments."""
    document_id: str = Field(..., description="Dokument-ID")
    score: float = Field(..., description="Composite Score 0.0-1.0")
    ampel_color: str = Field(..., description="Ampel-Farbe: gruen/gelb/rot")
    ampel_label: str = Field(..., description="Ampel-Beschreibung")
    dimensions: List[QualityDimensionResponse] = Field(..., description="Einzelne Dimensionen")
    recommendations: List[str] = Field(..., description="Empfehlungen")


class AmpelKategorie(BaseModel):
    """Einzelne Ampel-Kategorie (gruen/gelb/rot)."""
    anzahl: int = Field(..., description="Anzahl Dokumente")
    prozent: float = Field(..., description="Prozentualer Anteil")


class AmpelVerteilung(BaseModel):
    """Ampel-Verteilung ueber alle Dokumente."""
    gruen: AmpelKategorie = Field(..., description="Gute Qualitaet")
    gelb: AmpelKategorie = Field(..., description="Mittlere Qualitaet")
    rot: AmpelKategorie = Field(..., description="Schlechte Qualitaet")


class CompanyQualityOverviewResponse(BaseModel):
    """Unternehmensweite Qualitaetsuebersicht."""
    total_documents: int = Field(..., description="Gesamtanzahl Dokumente")
    average_score: float = Field(..., description="Durchschnittlicher Score")
    verteilung: AmpelVerteilung = Field(..., description="Ampel-Verteilung")


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/{document_id}/score",
    response_model=DocumentQualityResponse,
    summary="Dokumenten-Qualitaet",
    description="Berechnet den Qualitaets-Score und Ampel-Status fuer ein Dokument.",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_document_quality_score(
    request: Request,  # Required for rate limiter
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentQualityResponse:
    """Qualitaets-Score fuer ein einzelnes Dokument."""
    from app.services.ocr.document_quality_score_service import get_document_quality_service

    service = get_document_quality_service()

    try:
        quality = await service.calculate_quality_score(str(document_id), db)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )
    except Exception as e:
        logger.error(
            "quality_score_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Qualitaetsbewertung fehlgeschlagen",
        )

    result_dict = quality.to_dict()
    return DocumentQualityResponse(
        document_id=result_dict["document_id"],
        score=result_dict["score"],
        ampel_color=result_dict["ampel_color"],
        ampel_label=result_dict["ampel_label"],
        dimensions=[QualityDimensionResponse(**d) for d in result_dict["dimensions"]],
        recommendations=result_dict["recommendations"],
    )


@router.get(
    "/overview",
    response_model=CompanyQualityOverviewResponse,
    summary="Qualitaets-Uebersicht",
    description="Unternehmensweite Ampel-Verteilung.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_company_quality_overview(
    request: Request,  # Required for rate limiter
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyQualityOverviewResponse:
    """Unternehmensweite Qualitaetsuebersicht."""
    from app.services.ocr.document_quality_score_service import get_document_quality_service

    service = get_document_quality_service()
    company_id = str(current_user.company_id) if hasattr(current_user, 'company_id') and current_user.company_id else str(current_user.id)

    try:
        overview = await service.get_company_quality_overview(company_id, db)
    except Exception as e:
        logger.error(
            "quality_overview_error",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Qualitaetsuebersicht konnte nicht berechnet werden",
        )

    result_dict = overview.to_dict()
    return CompanyQualityOverviewResponse(**result_dict)
