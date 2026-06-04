"""
API endpoints for automatic booking suggestions.

Provides endpoints for:
- Retrieving booking suggestions for documents
- Recording user feedback on suggestions
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.db.models import User
from app.middleware.company_context import get_current_company_id
from app.services.accounting.booking_suggestion_service import (
    get_booking_suggestion_service,
)

router = APIRouter(prefix="/booking-suggestions", tags=["Buchungsvorschläge"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class BookingSuggestionResponse(BaseModel):
    """Response model for a single booking suggestion."""

    model_config = ConfigDict(from_attributes=True)

    account_number: str = Field(..., description="Kontonummer")
    account_name: str = Field(..., description="Kontobezeichnung")
    cost_center: Optional[str] = Field(None, description="Kostenstelle")
    tax_rate: float = Field(..., description="Steuersatz in Prozent")
    tax_key: str = Field(..., description="Steuerschluessel")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Konfidenz des Vorschlags (0-1)"
    )
    reason: str = Field(..., description="Begruendung für den Vorschlag")
    based_on_count: int = Field(
        ..., ge=0, description="Anzahl ähnlicher historischer Buchungen"
    )


class BookingResultResponse(BaseModel):
    """Response model for booking suggestions result."""

    model_config = ConfigDict(from_attributes=True)

    document_id: str = Field(..., description="Dokument-ID")
    suggestions: List[BookingSuggestionResponse] = Field(
        ..., description="Liste der Buchungsvorschläge"
    )
    document_type: str = Field(..., description="Dokumenttyp")
    vendor_name: Optional[str] = Field(None, description="Lieferantenname")
    total_amount: Optional[float] = Field(None, description="Gesamtbetrag")
    currency: str = Field(default="EUR", description="Währung")
    chart_of_accounts: str = Field(..., description="Kontenrahmen (z.B. SKR03)")


class BookingFeedbackRequest(BaseModel):
    """Request model for booking feedback."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID = Field(..., description="Dokument-ID")
    accepted_account: str = Field(..., description="Akzeptierte Kontonummer")
    accepted_cost_center: Optional[str] = Field(
        None, description="Akzeptierte Kostenstelle"
    )
    accepted_tax_rate: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Akzeptierter Steuersatz in Prozent"
    )


class BookingFeedbackResponse(BaseModel):
    """Response model for booking feedback."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(..., description="Erfolgsstatus")
    message: str = Field(..., description="Statusmeldung")
    feedback_count: int = Field(..., description="Anzahl gespeicherter Feedbacks")


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/document/{document_id}",
    response_model=BookingResultResponse,
    summary="Buchungsvorschläge abrufen",
    description="Ruft automatische Buchungsvorschläge für ein Dokument ab",
)
async def get_booking_suggestions(
    document_id: UUID,
    chart: str = Query(
        default="SKR03",
        description="Kontenrahmen (SKR03 oder SKR04)",
        pattern="^(SKR03|SKR04)$",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BookingResultResponse:
    """
    Ruft Buchungsvorschläge für ein Dokument ab.

    Args:
        document_id: UUID des Dokuments
        chart: Kontenrahmen (SKR03 oder SKR04)
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        BookingResultResponse mit Vorschlägen

    Raises:
        HTTPException: Bei fehlenden Berechtigungen oder Fehlern
    """
    company_id = get_current_company_id()

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma im Kontext verfügbar",
        )

    service = get_booking_suggestion_service()

    try:
        result = await service.suggest_booking(
            db=db, document_id=document_id, company_id=company_id, chart=chart
        )

        # Convert BookingResult dataclass to response model
        suggestions = [
            BookingSuggestionResponse(
                account_number=s.account_number,
                account_name=s.account_name,
                cost_center=s.cost_center,
                tax_rate=float(s.tax_rate),
                tax_key=s.tax_key,
                confidence=s.confidence,
                reason=s.reason,
                based_on_count=s.based_on_count,
            )
            for s in result.suggestions
        ]

        return BookingResultResponse(
            document_id=str(result.document_id),
            suggestions=suggestions,
            document_type=result.document_type,
            vendor_name=result.vendor_name,
            total_amount=result.total_amount,
            currency=result.currency,
            chart_of_accounts=result.chart_of_accounts,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dokument nicht gefunden: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der Buchungsvorschläge: {str(e)}",
        )


@router.post(
    "/feedback",
    response_model=BookingFeedbackResponse,
    summary="Feedback speichern",
    description="Speichert Benutzer-Feedback zu einem Buchungsvorschlag",
    status_code=status.HTTP_201_CREATED,
)
async def submit_booking_feedback(
    feedback: BookingFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BookingFeedbackResponse:
    """
    Speichert Benutzer-Feedback zu einem Buchungsvorschlag.

    Das Feedback wird verwendet, um zukuenftige Vorschläge zu verbessern.

    Args:
        feedback: Feedback-Daten
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        BookingFeedbackResponse mit Erfolgsstatus

    Raises:
        HTTPException: Bei fehlenden Berechtigungen oder Fehlern
    """
    company_id = get_current_company_id()

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma im Kontext verfügbar",
        )

    service = get_booking_suggestion_service()

    try:
        result = await service.record_feedback(
            db=db,
            document_id=feedback.document_id,
            company_id=company_id,
            accepted_account=feedback.accepted_account,
            accepted_cost_center=feedback.accepted_cost_center,
            accepted_tax_rate=feedback.accepted_tax_rate,
        )

        return BookingFeedbackResponse(
            success=result["success"],
            message=result["message"],
            feedback_count=result["feedback_count"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dokument nicht gefunden: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Speichern des Feedbacks: {str(e)}",
        )
