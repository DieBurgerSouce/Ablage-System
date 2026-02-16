# -*- coding: utf-8 -*-
"""
API-Endpunkte für OCR-Confidence-Daten.

Stellt Wort-Level und Seiten-Level Confidence-Daten bereit
für Viewer-Heatmap-Visualisierung.

Feinpoliert und durchdacht - Enterprise OCR Confidence API.
"""

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.services.ocr.confidence_service import (
    OCRConfidenceService,
    DocumentConfidenceData,
    PageConfidence,
    WordConfidence
)
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ocr-confidence", tags=["OCR Confidence"])


# =============================================================================
# Response Models
# =============================================================================


class WordConfidenceResponse(BaseModel):
    """Wort-Level Confidence Response."""

    text: str = Field(..., description="Wort-Text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence-Score (0.0 - 1.0)")
    page: int = Field(..., ge=1, description="Seitennummer")
    x: float = Field(..., ge=0.0, le=1.0, description="X-Position (normalisiert 0-1)")
    y: float = Field(..., ge=0.0, le=1.0, description="Y-Position (normalisiert 0-1)")
    width: float = Field(..., ge=0.0, le=1.0, description="Breite (normalisiert 0-1)")
    height: float = Field(..., ge=0.0, le=1.0, description="Höhe (normalisiert 0-1)")

    model_config = ConfigDict(from_attributes=True)


class PageConfidenceResponse(BaseModel):
    """Seiten-Level Confidence Response."""

    page_number: int = Field(..., ge=1, description="Seitennummer")
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Gesamt-Confidence der Seite")
    words: List[WordConfidenceResponse] = Field(default_factory=list, description="Wort-Level Confidence-Daten")
    backend: str = Field(..., description="Verwendetes OCR-Backend")

    model_config = ConfigDict(from_attributes=True)


class DocumentConfidenceResponse(BaseModel):
    """Dokument-Level Confidence Response."""

    document_id: str = Field(..., description="Dokument-ID")
    total_pages: int = Field(..., ge=1, description="Gesamtanzahl Seiten")
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Gesamt-Confidence des Dokuments")
    pages: List[PageConfidenceResponse] = Field(default_factory=list, description="Seiten-Confidence-Daten")
    backend: str = Field(..., description="Verwendetes OCR-Backend")

    model_config = ConfigDict(from_attributes=True)


class ConfidenceSummaryResponse(BaseModel):
    """Schnelle Confidence-Zusammenfassung ohne Wort-Daten."""

    document_id: str = Field(..., description="Dokument-ID")
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Gesamt-Confidence")
    total_pages: int = Field(..., ge=1, description="Gesamtanzahl Seiten")
    backend: str = Field(..., description="Verwendetes OCR-Backend")
    page_averages: Dict[int, float] = Field(default_factory=dict, description="Durchschnitts-Confidence pro Seite")
    has_word_level_data: bool = Field(..., description="Sind Wort-Level Daten verfügbar?")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/{document_id}",
    response_model=DocumentConfidenceResponse,
    summary="Hole OCR-Confidence-Daten",
    description=(
        "Liefert detaillierte Wort-Level und Seiten-Level Confidence-Daten "
        "für Heatmap-Visualisierung im Document Viewer."
    )
)
async def get_document_confidence(
    document_id: UUID,
    page: Optional[int] = Query(
        None,
        ge=1,
        description="Spezifische Seitennummer (optional, sonst alle Seiten)"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentConfidenceResponse:
    """
    Hole OCR-Confidence-Daten für ein Dokument.

    **Zugriffsrechte**: Nur der Dokumenten-Owner kann die Daten abrufen.

    **Datenquellen** (in dieser Reihenfolge):
    1. ocr_results.bounding_boxes (primär, detaillierteste Daten)
    2. ocr_results.detected_layout (fallback für Layout-Daten)
    3. document.metadata (fallback für gespeicherte Confidence-Daten)
    4. document.ocr_confidence (minimaler Fallback)

    **Anwendungsfall**: Heatmap-Visualisierung im Viewer

    Args:
        document_id: Dokument-ID (UUID)
        page: Optional spezifische Seitennummer (None = alle Seiten)
        current_user: Aktueller authentifizierter Benutzer
        db: Database Session

    Returns:
        DocumentConfidenceResponse mit strukturierten Confidence-Daten

    Raises:
        404: Dokument nicht gefunden
        403: Keine Berechtigung für dieses Dokument
        500: Interner Serverfehler
    """
    try:
        logger.info(
            "get_confidence_data_request",
            document_id=str(document_id),
            user_id=str(current_user.id),
            page=page
        )

        # Service initialisieren
        service = OCRConfidenceService(db)

        # Confidence-Daten abrufen
        try:
            confidence_data = await service.get_confidence_data(
                document_id=document_id,
                user_id=current_user.id,
                page_number=page
            )
        except ValueError as e:
            error_msg = str(e)
            if "nicht gefunden" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dokument nicht gefunden"
                )
            elif "Keine Berechtigung" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Keine Berechtigung für dieses Dokument"
                )
            else:
                raise

        # Response erstellen
        response = _convert_to_response(confidence_data)

        logger.info(
            "get_confidence_data_success",
            document_id=str(document_id),
            pages_count=len(response.pages),
            total_words=sum(len(p.words) for p in response.pages),
            backend=response.backend
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_confidence_data_failed",
            document_id=str(document_id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "OCR-Confidence")
        )


@router.get(
    "/{document_id}/summary",
    response_model=ConfidenceSummaryResponse,
    summary="Hole Confidence-Zusammenfassung",
    description=(
        "Liefert eine schnelle Zusammenfassung der Confidence-Daten "
        "ohne detaillierte Wort-Level Informationen."
    )
)
async def get_confidence_summary(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> ConfidenceSummaryResponse:
    """
    Hole Confidence-Zusammenfassung für ein Dokument.

    Schnellere Alternative zu GET /{document_id} für Overview-Anzeigen.
    Liefert nur Seiten-Averages ohne Wort-Level Details.

    **Zugriffsrechte**: Nur der Dokumenten-Owner kann die Daten abrufen.

    **Anwendungsfall**: Schnelle Vorschau, Dashboard-Anzeige

    Args:
        document_id: Dokument-ID (UUID)
        current_user: Aktueller authentifizierter Benutzer
        db: Database Session

    Returns:
        ConfidenceSummaryResponse mit Zusammenfassungs-Daten

    Raises:
        404: Dokument nicht gefunden
        403: Keine Berechtigung für dieses Dokument
        500: Interner Serverfehler
    """
    try:
        logger.info(
            "get_confidence_summary_request",
            document_id=str(document_id),
            user_id=str(current_user.id)
        )

        # Service initialisieren
        service = OCRConfidenceService(db)

        # Summary abrufen
        try:
            summary = await service.get_confidence_summary(
                document_id=document_id,
                user_id=current_user.id
            )
        except ValueError as e:
            error_msg = str(e)
            if "nicht gefunden" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dokument nicht gefunden"
                )
            elif "Keine Berechtigung" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Keine Berechtigung für dieses Dokument"
                )
            else:
                raise

        response = ConfidenceSummaryResponse(**summary)

        logger.info(
            "get_confidence_summary_success",
            document_id=str(document_id),
            overall_confidence=response.overall_confidence,
            total_pages=response.total_pages,
            has_word_data=response.has_word_level_data
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_confidence_summary_failed",
            document_id=str(document_id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "OCR-Confidence")
        )


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_to_response(
    confidence_data: DocumentConfidenceData
) -> DocumentConfidenceResponse:
    """
    Konvertiert Service-Dataclass zu API-Response-Model.

    Args:
        confidence_data: DocumentConfidenceData vom Service

    Returns:
        DocumentConfidenceResponse für API
    """
    pages_response: List[PageConfidenceResponse] = []

    for page_data in confidence_data.pages:
        words_response: List[WordConfidenceResponse] = []

        for word_data in page_data.words:
            words_response.append(WordConfidenceResponse(
                text=word_data.text,
                confidence=word_data.confidence,
                page=word_data.page,
                x=word_data.x,
                y=word_data.y,
                width=word_data.width,
                height=word_data.height
            ))

        pages_response.append(PageConfidenceResponse(
            page_number=page_data.page_number,
            overall_confidence=page_data.overall_confidence,
            words=words_response,
            backend=page_data.backend
        ))

    return DocumentConfidenceResponse(
        document_id=confidence_data.document_id,
        total_pages=confidence_data.total_pages,
        overall_confidence=confidence_data.overall_confidence,
        pages=pages_response,
        backend=confidence_data.backend
    )
