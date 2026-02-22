# -*- coding: utf-8 -*-
"""
DATEV Booking Suggestion API.

Endpunkte für Buchungsvorschläge:
- Einzelne Buchungsvorschläge
- Batch-Vorschläge
- DATEV-Export

Vision 2.0 Feature: Erweiterte Integrationen
Feinpoliert und durchdacht.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional, List, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail
from app.db.models import User, Document, BusinessEntity
from app.services.datev.booking_suggestion_service import (
    BookingSuggestionService,
    BookingSuggestion,
    Kontenrahmen,
    Belegart,
)
from app.services.datev.scan_to_booking_orchestrator import (
    get_scan_to_booking_orchestrator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datev/bookings", tags=["DATEV Buchungsvorschläge"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class SuggestBookingRequest(BaseModel):
    """Request für einzelnen Buchungsvorschlag."""

    ocr_text: str = Field(..., min_length=1, description="OCR-Volltext")
    extracted_data: dict = Field(default_factory=dict, description="Strukturierte OCR-Daten")
    document_type: Optional[str] = Field(None, description="Dokumenttyp")
    entity_name: Optional[str] = Field(None, description="Geschäftspartner-Name")
    entity_id: Optional[UUID] = Field(None, description="Geschäftspartner-ID")
    kontenrahmen: str = Field("skr03", pattern="^(skr03|skr04)$", description="SKR03 oder SKR04")
    custom_account_mappings: Optional[dict] = Field(None, description="Benutzerdefinierte Konten-Zuordnungen")


class SuggestFromDocumentRequest(BaseModel):
    """Request für Buchungsvorschlag aus Dokument."""

    document_id: UUID = Field(..., description="Dokument-ID")
    kontenrahmen: str = Field("skr03", pattern="^(skr03|skr04)$")
    custom_account_mappings: Optional[dict] = None


class BatchSuggestRequest(BaseModel):
    """Request für Batch-Vorschläge."""

    document_ids: List[UUID] = Field(..., min_length=1, max_length=100)
    kontenrahmen: str = Field("skr03", pattern="^(skr03|skr04)$")
    custom_account_mappings: Optional[dict] = None


class ExportRequest(BaseModel):
    """Request für DATEV-Export."""

    document_ids: List[UUID] = Field(..., min_length=1, max_length=500)
    mandant_nr: str = Field(..., min_length=1, max_length=5, pattern="^[0-9]+$")
    berater_nr: str = Field(..., min_length=1, max_length=7, pattern="^[0-9]+$")
    wirtschaftsjahr: int = Field(..., ge=2000, le=2100)
    kontenrahmen: str = Field("skr03", pattern="^(skr03|skr04)$")
    include_uncertain: bool = Field(False, description="Unsichere Vorschläge einbeziehen")


class BookingSuggestionResponse(BaseModel):
    """Response für Buchungsvorschlag."""

    belegart: str
    belegdatum: date
    buchungstext: str
    betrag: float
    sollkonto: str
    habenkonto: str
    sollkonto_name: Optional[str] = None
    habenkonto_name: Optional[str] = None
    steuercode: Optional[str] = None
    steuersatz: Optional[float] = None
    steuerbetrag: Optional[float] = None
    nettobetrag: Optional[float] = None
    belegnummer: Optional[str] = None
    rechnungsnummer: Optional[str] = None
    gegenkonto_name: Optional[str] = None
    kostenstelle: Optional[str] = None
    kostentraeger: Optional[str] = None
    confidence: float
    confidence_details: dict
    warnings: List[str]
    requires_review: bool

    @classmethod
    def from_suggestion(cls, suggestion: BookingSuggestion) -> "BookingSuggestionResponse":
        """Konvertiere BookingSuggestion zu Response."""
        return cls(
            belegart=suggestion.belegart,
            belegdatum=suggestion.belegdatum,
            buchungstext=suggestion.buchungstext,
            betrag=float(suggestion.betrag),
            sollkonto=suggestion.sollkonto,
            habenkonto=suggestion.habenkonto,
            sollkonto_name=suggestion.sollkonto_name,
            habenkonto_name=suggestion.habenkonto_name,
            steuercode=suggestion.steuercode,
            steuersatz=suggestion.steuersatz,
            steuerbetrag=float(suggestion.steuerbetrag) if suggestion.steuerbetrag else None,
            nettobetrag=float(suggestion.nettobetrag) if suggestion.nettobetrag else None,
            belegnummer=suggestion.belegnummer,
            rechnungsnummer=suggestion.rechnungsnummer,
            gegenkonto_name=suggestion.gegenkonto_name,
            kostenstelle=suggestion.kostenstelle,
            kostentraeger=suggestion.kostentraeger,
            confidence=suggestion.confidence,
            confidence_details=suggestion.confidence_details,
            warnings=suggestion.warnings,
            requires_review=suggestion.requires_review,
        )


class BatchSuggestionResponse(BaseModel):
    """Response für Batch-Vorschläge."""

    total: int
    successful: int
    failed: int
    suggestions: List[BookingSuggestionResponse]
    errors: List[dict]


class ExportResponse(BaseModel):
    """Response für DATEV-Export."""

    content: str
    filename: str
    total_bookings: int
    skipped_uncertain: int
    total_amount: float


class AccountInfo(BaseModel):
    """Konto-Information."""

    konto: str
    name: str
    typ: str
    steuercode: Optional[str] = None
    keywords: List[str] = []


class KontenrahmenResponse(BaseModel):
    """Response für Kontenrahmen-Abruf."""

    kontenrahmen: str
    accounts: List[AccountInfo]


class BelegartResponse(BaseModel):
    """Response für Belegarten."""

    code: str
    name: str
    beschreibung: str


# ============================================================================
# API Endpoints
# ============================================================================


@router.post(
    "/suggest",
    response_model=BookingSuggestionResponse,
    summary="Buchungsvorschlag generieren",
    description="Generiert einen Buchungsvorschlag aus OCR-Text und extrahierten Daten.",
)
async def suggest_booking(
    request: SuggestBookingRequest,
    current_user: User = Depends(get_current_user),
) -> BookingSuggestionResponse:
    """
    Generiere Buchungsvorschlag aus OCR-Daten.

    Analysiert den OCR-Text und die extrahierten Daten,
    um einen passenden SKR03/SKR04 Buchungssatz vorzuschlagen.
    """
    service = BookingSuggestionService(kontenrahmen=request.kontenrahmen)

    suggestion = service.suggest_booking(
        ocr_text=request.ocr_text,
        extracted_data=request.extracted_data,
        document_type=request.document_type,
        entity_name=request.entity_name,
        entity_id=request.entity_id,
        custom_account_mappings=request.custom_account_mappings,
    )

    logger.info(
        f"Buchungsvorschlag generiert: {suggestion.belegart} "
        f"Confidence={suggestion.confidence:.2f}"
    )

    return BookingSuggestionResponse.from_suggestion(suggestion)


@router.post(
    "/suggest-from-document",
    response_model=BookingSuggestionResponse,
    summary="Buchungsvorschlag aus Dokument",
    description="Generiert einen Buchungsvorschlag basierend auf einem verarbeiteten Dokument.",
)
async def suggest_from_document(
    request: SuggestFromDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingSuggestionResponse:
    """
    Generiere Buchungsvorschlag aus bestehendem Dokument.

    Liest OCR-Text und extrahierte Daten aus dem Dokument
    und generiert einen Buchungsvorschlag.
    """
    # Dokument laden
    result = await db.execute(
        select(Document).where(
            Document.id == request.document_id,
            Document.company_id == current_user.company_id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    # Entity laden falls vorhanden
    entity_name = None
    entity_id = None
    if document.entity_id:
        entity_result = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.id == document.entity_id,
                BusinessEntity.company_id == current_user.company_id,
            )
        )
        entity = entity_result.scalar_one_or_none()
        if entity:
            entity_name = entity.name
            entity_id = entity.id

    # OCR-Text und Daten aus Dokument
    ocr_text = document.ocr_text or ""
    extracted_data = document.extracted_data or {}

    service = BookingSuggestionService(kontenrahmen=request.kontenrahmen)

    suggestion = service.suggest_booking(
        ocr_text=ocr_text,
        extracted_data=extracted_data,
        document_type=document.document_type,
        entity_name=entity_name,
        entity_id=entity_id,
        custom_account_mappings=request.custom_account_mappings,
    )

    return BookingSuggestionResponse.from_suggestion(suggestion)


@router.post(
    "/batch-suggest",
    response_model=BatchSuggestionResponse,
    summary="Batch-Buchungsvorschläge",
    description="Generiert Buchungsvorschläge für mehrere Dokumente.",
)
async def batch_suggest(
    request: BatchSuggestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchSuggestionResponse:
    """
    Generiere Buchungsvorschläge für mehrere Dokumente.

    Verarbeitet bis zu 100 Dokumente in einem Request.
    """
    # Dokumente laden
    result = await db.execute(
        select(Document).where(
            Document.id.in_(request.document_ids),
            Document.company_id == current_user.company_id,
        )
    )
    documents = {doc.id: doc for doc in result.scalars().all()}

    # Entity-IDs sammeln
    entity_ids = {doc.entity_id for doc in documents.values() if doc.entity_id}

    # Entities laden
    entities = {}
    if entity_ids:
        entity_result = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.id.in_(entity_ids),
                BusinessEntity.company_id == current_user.company_id,
            )
        )
        entities = {e.id: e for e in entity_result.scalars().all()}

    service = BookingSuggestionService(kontenrahmen=request.kontenrahmen)

    suggestions = []
    errors = []

    for doc_id in request.document_ids:
        if doc_id not in documents:
            errors.append({
                "document_id": str(doc_id),
                "error": "Dokument nicht gefunden",
            })
            continue

        doc = documents[doc_id]
        entity = entities.get(doc.entity_id) if doc.entity_id else None

        try:
            suggestion = service.suggest_booking(
                ocr_text=doc.ocr_text or "",
                extracted_data=doc.extracted_data or {},
                document_type=doc.document_type,
                entity_name=entity.name if entity else None,
                entity_id=entity.id if entity else None,
                custom_account_mappings=request.custom_account_mappings,
            )
            suggestions.append(BookingSuggestionResponse.from_suggestion(suggestion))
        except Exception as e:
            logger.error(f"Buchungsvorschlag fehlgeschlagen für {doc_id}: {e}")
            errors.append({
                "document_id": str(doc_id),
                "error": safe_error_detail(e, "Vorgang"),
            })

    return BatchSuggestionResponse(
        total=len(request.document_ids),
        successful=len(suggestions),
        failed=len(errors),
        suggestions=suggestions,
        errors=errors,
    )


@router.post(
    "/export",
    response_model=ExportResponse,
    summary="DATEV-Export",
    description="Exportiert Buchungsvorschläge im DATEV-Format.",
)
async def export_to_datev(
    request: ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    """
    Exportiere Buchungsvorschläge im DATEV-Format.

    Generiert eine DATEV-kompatible Exportdatei
    für den Import in DATEV-Systeme.
    """
    # Dokumente laden
    result = await db.execute(
        select(Document).where(
            Document.id.in_(request.document_ids),
            Document.company_id == current_user.company_id,
        )
    )
    documents = list(result.scalars().all())

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Dokumente gefunden",
        )

    # Entities laden
    entity_ids = {doc.entity_id for doc in documents if doc.entity_id}
    entities = {}
    if entity_ids:
        entity_result = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.id.in_(entity_ids),
                BusinessEntity.company_id == current_user.company_id,
            )
        )
        entities = {e.id: e for e in entity_result.scalars().all()}

    service = BookingSuggestionService(kontenrahmen=request.kontenrahmen)

    # Vorschläge generieren
    suggestions = []
    for doc in documents:
        entity = entities.get(doc.entity_id) if doc.entity_id else None

        try:
            suggestion = service.suggest_booking(
                ocr_text=doc.ocr_text or "",
                extracted_data=doc.extracted_data or {},
                document_type=doc.document_type,
                entity_name=entity.name if entity else None,
                entity_id=entity.id if entity else None,
            )
            suggestions.append(suggestion)
        except Exception as e:
            logger.warning(f"Überspringe Dokument {doc.id}: {e}")

    # Unsichere filtern wenn nicht gewünscht
    if not request.include_uncertain:
        original_count = len(suggestions)
        suggestions = [s for s in suggestions if s.confidence >= 0.5 or not s.requires_review]
        skipped = original_count - len(suggestions)
    else:
        skipped = 0

    # DATEV-Export generieren
    content = service.export_to_datev_format(
        suggestions=suggestions,
        mandant_nr=request.mandant_nr,
        berater_nr=request.berater_nr,
        wirtschaftsjahr=request.wirtschaftsjahr,
    )

    # Gesamtbetrag berechnen
    total_amount = sum(float(s.betrag) for s in suggestions)

    # Dateiname
    filename = f"EXTF_{request.mandant_nr}_{request.wirtschaftsjahr}_{date.today().strftime('%Y%m%d')}.csv"

    logger.info(
        f"DATEV-Export erstellt: {len(suggestions)} Buchungen, "
        f"Mandant={request.mandant_nr}, Jahr={request.wirtschaftsjahr}"
    )

    return ExportResponse(
        content=content,
        filename=filename,
        total_bookings=len(suggestions),
        skipped_uncertain=skipped,
        total_amount=total_amount,
    )


@router.get(
    "/kontenrahmen/{kontenrahmen}",
    response_model=KontenrahmenResponse,
    summary="Kontenrahmen abrufen",
    description="Gibt alle verfügbaren Konten eines Kontenrahmens zurück.",
)
async def get_kontenrahmen(
    kontenrahmen: str = Path(..., pattern="^(skr03|skr04)$"),
    current_user: User = Depends(get_current_user),
) -> KontenrahmenResponse:
    """
    Rufe Konten eines Kontenrahmens ab.

    Gibt alle vordefinierten Konten für SKR03 oder SKR04 zurück.
    """
    service = BookingSuggestionService(kontenrahmen=kontenrahmen)

    accounts = [
        AccountInfo(
            konto=acc.konto,
            name=acc.name,
            typ=acc.typ,
            steuercode=acc.steuercode,
            keywords=acc.keywords,
        )
        for acc in service.accounts.values()
    ]

    return KontenrahmenResponse(
        kontenrahmen=kontenrahmen,
        accounts=accounts,
    )


@router.get(
    "/belegarten",
    response_model=List[BelegartResponse],
    summary="Belegarten abrufen",
    description="Gibt alle verfügbaren Belegarten zurück.",
)
async def get_belegarten(
    current_user: User = Depends(get_current_user),
) -> List[BelegartResponse]:
    """
    Rufe alle verfügbaren Belegarten ab.
    """
    belegarten = [
        BelegartResponse(
            code=Belegart.EINGANGSRECHNUNG.value,
            name="Eingangsrechnung",
            beschreibung="Erhaltene Rechnung von Lieferanten",
        ),
        BelegartResponse(
            code=Belegart.AUSGANGSRECHNUNG.value,
            name="Ausgangsrechnung",
            beschreibung="Erstellte Rechnung an Kunden",
        ),
        BelegartResponse(
            code=Belegart.GUTSCHRIFT_EINGANG.value,
            name="Gutschrift Eingang",
            beschreibung="Erhaltene Gutschrift von Lieferanten",
        ),
        BelegartResponse(
            code=Belegart.GUTSCHRIFT_AUSGANG.value,
            name="Gutschrift Ausgang",
            beschreibung="Erstellte Gutschrift für Kunden",
        ),
        BelegartResponse(
            code=Belegart.BANK.value,
            name="Bankbeleg",
            beschreibung="Bankbuchung (Kontoauszug)",
        ),
        BelegartResponse(
            code=Belegart.KASSE.value,
            name="Kassenbeleg",
            beschreibung="Kassenbuchung",
        ),
        BelegartResponse(
            code=Belegart.SONSTIGES.value,
            name="Sonstiges",
            beschreibung="Sonstige Belege",
        ),
    ]

    return belegarten


@router.get(
    "/steuercodes",
    summary="Steuercodes abrufen",
    description="Gibt alle verfügbaren DATEV-Steuercodes zurück.",
)
async def get_steuercodes(
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """
    Rufe alle verfügbaren DATEV-Steuercodes ab.
    """
    return [
        {"code": "9", "satz": 19, "beschreibung": "19% USt/VSt"},
        {"code": "8", "satz": 7, "beschreibung": "7% USt/VSt"},
        {"code": "0", "satz": 0, "beschreibung": "Steuerfrei"},
        {"code": "91", "satz": 0, "beschreibung": "EU-Erwerb"},
        {"code": "94", "satz": 0, "beschreibung": "Reverse Charge"},
        {"code": "41", "satz": 0, "beschreibung": "Innergemeinschaftliche Lieferung"},
    ]


# ============================================================================
# Zero-Touch Stats & Auto-Booking API (Scan-to-Buchung)
# ============================================================================


class ZeroTouchStatsResponse(BaseModel):
    """Response fuer Zero-Touch-Buchungsquote."""

    total_processed: int
    auto_booked: int
    review_queue: int
    manual: int
    zero_touch_quote: float
    top_failure_reasons: List[Tuple[str, int]]
    trend_7d: Optional[float] = None


class ProcessBookingResponse(BaseModel):
    """Response fuer manuelle Buchungsausloesung."""

    document_id: str
    routing: str
    success: bool
    datev_booking_id: Optional[str] = None
    plausibility_score: float
    reason: str
    processing_time_ms: int


@router.get(
    "/zero-touch-stats",
    response_model=ZeroTouchStatsResponse,
    summary="Zero-Touch-Quote abrufen",
    description="Dashboard-Daten fuer die automatische Buchungsquote.",
)
async def get_zero_touch_stats(
    period_days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ZeroTouchStatsResponse:
    """
    Gibt Zero-Touch-Buchungsstatistiken zurueck.

    Zeigt wie viele Rechnungen automatisch gebucht, zur Pruefung
    vorgelegt oder manuell verarbeitet wurden.
    """
    orchestrator = get_scan_to_booking_orchestrator()

    stats = await orchestrator.get_zero_touch_stats(
        company_id=current_user.company_id,
        period_days=period_days,
        db=db,
    )

    return ZeroTouchStatsResponse(
        total_processed=stats.total_processed,
        auto_booked=stats.auto_booked,
        review_queue=stats.review_queue,
        manual=stats.manual,
        zero_touch_quote=stats.zero_touch_quote,
        top_failure_reasons=stats.top_failure_reasons,
        trend_7d=stats.trend_7d,
    )


@router.post(
    "/process-booking/{document_id}",
    response_model=ProcessBookingResponse,
    summary="Buchung manuell ausloesen",
    description="Startet den Scan-to-Buchung Workflow fuer ein einzelnes Dokument.",
)
async def process_booking(
    document_id: UUID = Path(..., description="Dokument-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessBookingResponse:
    """
    Loest den Buchungsworkflow fuer ein Dokument manuell aus.

    Fuehrt das Dokument durch die Plausibilitaetspruefung und
    erstellt bei Erfolg eine DATEV-Buchung.
    """
    orchestrator = get_scan_to_booking_orchestrator()

    result = await orchestrator.process_document_for_booking(
        document_id=document_id,
        company_id=current_user.company_id,
        db=db,
    )

    await db.commit()

    return ProcessBookingResponse(
        document_id=str(result.document_id),
        routing=result.routing,
        success=result.success,
        datev_booking_id=result.datev_booking_id,
        plausibility_score=result.plausibility_score,
        reason=result.reason,
        processing_time_ms=result.processing_time_ms,
    )
