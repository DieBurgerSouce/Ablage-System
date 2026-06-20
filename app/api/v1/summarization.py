"""
API endpoints für AI-basierte Dokumentenzusammenfassungen.

Dieses Modul stellt REST-Endpoints für:
- Einzeldokument-Zusammenfassungen
- Dokument-Vergleiche
- CEO-Dashboard Briefings
"""

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.safe_errors import safe_error_detail
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.api.dependencies import get_user_company_id  # F-31
from app.db.models import User
from app.middleware.company_context import get_current_company_id
from app.services.ai.summarization_service import get_summarization_service

router = APIRouter(prefix="/summarization", tags=["Zusammenfassungen"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class SummarizationResponse(BaseModel):
    """Response für Dokumentenzusammenfassung."""

    summary: str = Field(..., description="Generierte Zusammenfassung")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Konfidenz-Score der Zusammenfassung"
    )
    cached: bool = Field(..., description="Wurde aus Cache geladen")
    model_used: str = Field(..., description="Verwendetes AI-Modell")
    generated_at: Optional[str] = Field(
        None, description="Zeitstempel der Generierung (ISO 8601)"
    )

    model_config = ConfigDict(from_attributes=True)


class ComparisonRequest(BaseModel):
    """Request für Dokument-Vergleich."""

    document_ids: List[UUID] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Liste der zu vergleichenden Dokument-IDs (2-5)",
    )
    comparison_type: str = Field(
        default="allgemein",
        description="Art des Vergleichs (allgemein, preise, konditionen, etc.)",
    )

    @field_validator("document_ids")
    @classmethod
    def validate_unique_ids(cls, v: List[UUID]) -> List[UUID]:
        """Stelle sicher, dass Dokument-IDs eindeutig sind."""
        if len(v) != len(set(v)):
            raise ValueError("Dokument-IDs müssen eindeutig sein")
        return v

    model_config = ConfigDict(from_attributes=True)


class ComparisonResponse(BaseModel):
    """Response für Dokument-Vergleich."""

    comparison: str = Field(..., description="Vergleichstext")
    documents: List[str] = Field(..., description="Vergleichene Dokumente (Namen)")
    differences: List[str] = Field(..., description="Hauptunterschiede")
    recommendation: Optional[str] = Field(None, description="Empfehlung")

    model_config = ConfigDict(from_attributes=True)


class BriefingResponse(BaseModel):
    """Response für CEO-Dashboard Briefing."""

    zeitraum: str = Field(..., description="Betrachteter Zeitraum")
    seit: str = Field(..., description="Start-Zeitstempel (ISO 8601)")
    neue_dokumente: int = Field(..., ge=0, description="Anzahl neuer Dokumente")
    nach_typ: Dict[str, int] = Field(..., description="Dokumente nach Typ gruppiert")
    highlights: List[str] = Field(..., description="Wichtigste Ereignisse")
    handlungsbedarf: List[str] = Field(..., description="Erforderliche Maßnahmen")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# API Endpoints
# ============================================================================


@router.get(
    "/document/{document_id}",
    response_model=SummarizationResponse,
    summary="Dokumentenzusammenfassung",
    description="Generiert oder lädt eine Zusammenfassung für ein Dokument",
)
async def summarize_document(
    document_id: UUID,
    length: str = Query(
        default="mittel",
        description="Länge der Zusammenfassung (kurz, mittel, lang)",
        pattern="^(kurz|mittel|lang)$",
    ),
    language: str = Query(
        default="de",
        description="Sprache der Zusammenfassung",
        pattern="^(de|en)$",
    ),
    force_refresh: bool = Query(
        default=False,
        description="Erzwinge Neu-Generierung (ignoriere Cache)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SummarizationResponse:
    """
    Generiert eine AI-basierte Zusammenfassung eines Dokuments.

    Args:
        document_id: UUID des Dokuments
        length: Gewünschte Länge (kurz, mittel, lang)
        language: Sprache (de, en)
        force_refresh: Cache ignorieren und neu generieren
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        SummarizationResponse mit Zusammenfassung und Metadaten

    Raises:
        HTTPException 404: Dokument nicht gefunden
        HTTPException 403: Keine Berechtigung
        HTTPException 500: Fehler bei der Generierung
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=403,
            detail="Keine Firma zugeordnet",
        )

    service = get_summarization_service()

    try:
        result = await service.summarize_document(
            db=db,
            document_id=document_id,
            company_id=company_id,
            length=length,
            language=language,
            force_refresh=force_refresh,
        )

        return SummarizationResponse(**result)

    except ValueError as e:
        # Dokument nicht gefunden oder keine Berechtigung
        raise HTTPException(status_code=404, detail=safe_error_detail(e, "Zusammenfassung"))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(e, "Zusammenfassung"))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der Zusammenfassungsgenerierung: {str(e)}",
        )


@router.post(
    "/compare",
    response_model=ComparisonResponse,
    summary="Dokument-Vergleich",
    description="Vergleicht 2-5 Dokumente und identifiziert Unterschiede",
)
async def compare_documents(
    request: ComparisonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ComparisonResponse:
    """
    Vergleicht mehrere Dokumente und extrahiert Unterschiede.

    Args:
        request: Vergleichsanfrage mit Dokument-IDs und Typ
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        ComparisonResponse mit Vergleichsergebnis

    Raises:
        HTTPException 400: Ungültige Anfrage
        HTTPException 404: Dokument(e) nicht gefunden
        HTTPException 403: Keine Berechtigung
        HTTPException 500: Fehler beim Vergleich
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=403,
            detail="Keine Firma zugeordnet",
        )

    service = get_summarization_service()

    try:
        result = await service.compare_documents(
            db=db,
            document_ids=request.document_ids,
            company_id=company_id,
            comparison_type=request.comparison_type,
        )

        return ComparisonResponse(**result)

    except ValueError as e:
        # Ungültige Anzahl oder nicht gefunden
        if "mindestens 2" in str(e).lower() or "maximal 5" in str(e).lower():
            raise HTTPException(status_code=400, detail=safe_error_detail(e, "Zusammenfassung"))
        raise HTTPException(status_code=404, detail=safe_error_detail(e, "Zusammenfassung"))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(e, "Zusammenfassung"))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Dokumenten-Vergleich: {str(e)}",
        )


@router.get(
    "/briefing",
    response_model=BriefingResponse,
    summary="CEO-Dashboard Briefing",
    description="Generiert ein Executive Summary über neue Dokumente und wichtige Ereignisse",
)
async def generate_briefing(
    period: str = Query(
        default="heute",
        description="Zeitraum (heute, woche, monat)",
        pattern="^(heute|woche|monat)$",
    ),
    focus: Optional[str] = Query(
        default=None,
        description="Thematischer Fokus (finanzen, verträge, kommunikation, etc.)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BriefingResponse:
    """
    Generiert ein KI-basiertes Briefing über neue Dokumente und Ereignisse.

    Args:
        period: Zeitraum (heute, woche, monat)
        focus: Optional thematischer Fokus
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        BriefingResponse mit Zusammenfassung und Handlungsbedarf

    Raises:
        HTTPException 403: Keine Berechtigung
        HTTPException 500: Fehler bei der Generierung
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=403,
            detail="Keine Firma zugeordnet",
        )

    service = get_summarization_service()

    try:
        result = await service.generate_briefing(
            db=db,
            company_id=company_id,
            period=period,
            focus=focus,
        )

        return BriefingResponse(**result)

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(e, "Zusammenfassung"))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der Briefing-Generierung: {str(e)}",
        )
