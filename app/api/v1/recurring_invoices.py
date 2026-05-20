# -*- coding: utf-8 -*-
"""
Wiederkehrende Rechnungen (Abo-Verwaltung) API Endpoints.

REST API für Abo-Erkennung und -Verwaltung:
- Automatische Erkennung wiederkehrender Rechnungsmuster
- CRUD für wiederkehrende Rechnungen
- Soll/Ist-Vergleiche
- Preisänderungs-Alerts
- Fehlende-Rechnungen-Erkennung
- Kündigungsfristen-Tracking

Phase 2.2 der Feature-Roadmap (Februar 2026).
"""

from datetime import date, datetime
from decimal import Decimal
import re
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_recurring_invoice import (
    RecurringInvoiceStatus,
    RecurringIntervalType,
    DetectionMethod,
    OccurrenceStatus,
    OccurrenceMatchMethod,
)
from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.services.finance.recurring_invoice_service import (
    get_recurring_invoice_service,
    RecurringInvoiceCreateRequest,
    RecurringInvoiceUpdateRequest,
    MatchInvoiceRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/recurring-invoices",
    tags=["Wiederkehrende Rechnungen"],
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class RecurringInvoiceCreateSchema(BaseModel):
    """Schema für manuelle Abo-Erstellung."""
    vendor_name: str = Field(..., min_length=1, max_length=255, description="Lieferantenname")
    interval_type: RecurringIntervalType = Field(
        default=RecurringIntervalType.MONTHLY,
        description="Intervall-Typ",
    )
    interval_months: int = Field(default=1, ge=1, le=60, description="Intervall in Monaten")
    expected_amount: Decimal = Field(..., gt=0, description="Erwarteter Betrag")
    currency: str = Field(default="EUR", max_length=3, description="Währung")
    tolerance_percent: float = Field(default=5.0, ge=0, le=100, description="Toleranz in Prozent")
    vendor_entity_id: Optional[UUID] = Field(None, description="Lieferanten-Entity-ID")
    first_seen_date: Optional[date] = Field(None, description="Erstes Auftreten")
    next_expected_date: Optional[date] = Field(None, description="Nächstes erwartetes Datum")
    cancellation_deadline: Optional[date] = Field(None, description="Kündigungsfrist")
    notice_period_days: Optional[int] = Field(None, ge=0, description="Kündigungsfrist in Tagen")
    auto_renewal: bool = Field(default=True, description="Automatische Verlängerung")
    category: Optional[str] = Field(None, max_length=100, description="Kategorie")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    document_type: Optional[str] = Field(None, max_length=100, description="Dokumenttyp")
    reference_pattern: Optional[str] = Field(None, max_length=255, description="Rechnungsnummer-Muster (Regex)")

    @field_validator("reference_pattern")
    @classmethod
    def validate_reference_pattern(cls, v: Optional[str]) -> Optional[str]:
        """Prüfe ob reference_pattern ein gültiger Regex ist."""
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Ungültiger regulaerer Ausdruck: {e}")
        return v


class RecurringInvoiceUpdateSchema(BaseModel):
    """Schema für Abo-Aktualisierung."""
    status: Optional[RecurringInvoiceStatus] = None
    expected_amount: Optional[Decimal] = Field(None, gt=0)
    interval_type: Optional[RecurringIntervalType] = None
    interval_months: Optional[int] = Field(None, ge=1, le=60)
    tolerance_percent: Optional[float] = Field(None, ge=0, le=100)
    cancellation_deadline: Optional[date] = None
    notice_period_days: Optional[int] = Field(None, ge=0)
    auto_renewal: Optional[bool] = None
    next_expected_date: Optional[date] = None
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    reference_pattern: Optional[str] = Field(None, max_length=255)

    @field_validator("reference_pattern")
    @classmethod
    def validate_reference_pattern(cls, v: Optional[str]) -> Optional[str]:
        """Prüfe ob reference_pattern ein gültiger Regex ist."""
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Ungültiger regulaerer Ausdruck: {e}")
        return v


class PriceHistoryEntry(BaseModel):
    """Einzelner Eintrag in der Preishistorie."""
    date: Optional[str] = None
    amount: Optional[Decimal] = None
    change_percent: Optional[float] = None


class RecurringInvoiceResponse(BaseModel):
    """Response-Schema für wiederkehrende Rechnung."""
    id: UUID
    company_id: UUID
    vendor_entity_id: Optional[UUID]
    vendor_name: str
    interval_type: RecurringIntervalType
    interval_months: int
    expected_amount: float
    currency: str
    tolerance_percent: float
    first_seen_date: Optional[date]
    last_seen_date: Optional[date]
    next_expected_date: Optional[date]
    cancellation_deadline: Optional[date]
    notice_period_days: Optional[int]
    auto_renewal: bool
    detection_confidence: float
    detection_method: DetectionMethod
    match_count: int
    price_history: List[PriceHistoryEntry]
    last_price_change_date: Optional[date]
    price_change_percent: Optional[float]
    status: RecurringInvoiceStatus
    price_increase_alerted: bool
    missing_invoice_alerted: bool
    category: Optional[str]
    description: Optional[str]
    document_type: Optional[str]
    reference_pattern: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class RecurringInvoiceListResponse(BaseModel):
    """Paginierte Liste wiederkehrender Rechnungen."""
    items: List[RecurringInvoiceResponse]
    total: int
    page: int
    page_size: int


class OccurrenceResponse(BaseModel):
    """Response-Schema für eine Abo-Instanz."""
    id: UUID
    recurring_invoice_id: UUID
    document_id: Optional[UUID]
    invoice_tracking_id: Optional[UUID]
    expected_date: date
    actual_date: Optional[date]
    expected_amount: float
    actual_amount: Optional[float]
    amount_deviation: Optional[float]
    status: OccurrenceStatus
    match_confidence: Optional[float]
    matched_at: Optional[datetime]
    matched_by: Optional[OccurrenceMatchMethod]
    period_start: Optional[date]
    period_end: Optional[date]
    notes: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecurringInvoiceDetailResponse(RecurringInvoiceResponse):
    """Detail-Response mit Vorkommen."""
    occurrences: List[OccurrenceResponse] = Field(default_factory=list)


class DetectedPatternResponse(BaseModel):
    """Response für erkanntes Abo-Muster."""
    vendor_name: str
    vendor_entity_id: Optional[UUID]
    interval_type: RecurringIntervalType
    interval_months: int
    average_amount: float
    occurrences_found: int
    confidence: float
    first_date: date
    last_date: date


class MissingInvoiceResponse(BaseModel):
    """Response für fehlende Rechnung."""
    recurring_invoice_id: UUID
    vendor_name: str
    expected_date: date
    expected_amount: float
    days_overdue: int


class PriceChangeResponse(BaseModel):
    """Response für Preisänderung."""
    recurring_invoice_id: UUID
    vendor_name: str
    old_amount: float
    new_amount: float
    change_percent: float
    change_date: date


class SollIstRowResponse(BaseModel):
    """Eine Zeile im Soll/Ist-Bericht."""
    recurring_invoice_id: UUID
    vendor_name: str
    category: Optional[str]
    expected_amount: float
    actual_amount: Optional[float]
    deviation: Optional[float]
    deviation_percent: Optional[float]
    status: OccurrenceStatus
    expected_date: date
    actual_date: Optional[date]


class SollIstReportResponse(BaseModel):
    """Soll/Ist-Vergleichsbericht."""
    company_id: UUID
    year: int
    month: int
    rows: List[SollIstRowResponse]
    total_expected: float
    total_actual: float
    total_deviation: float
    missing_count: int
    matched_count: int
    generated_at: date


class ManualMatchSchema(BaseModel):
    """Schema für manuelle Dokumentzuordnung."""
    document_id: UUID = Field(..., description="Dokument-ID")


# ============================================================================
# Helper Functions
# ============================================================================


def _build_recurring_response(r: "RecurringInvoice") -> RecurringInvoiceResponse:
    """Erstellt RecurringInvoiceResponse aus Model."""
    return RecurringInvoiceResponse(
        id=r.id,
        company_id=r.company_id,
        vendor_entity_id=r.vendor_entity_id,
        vendor_name=r.vendor_name,
        interval_type=r.interval_type,
        interval_months=r.interval_months,
        expected_amount=float(r.expected_amount or 0),
        currency=r.currency or "EUR",
        tolerance_percent=r.tolerance_percent or 5.0,
        first_seen_date=r.first_seen_date,
        last_seen_date=r.last_seen_date,
        next_expected_date=r.next_expected_date,
        cancellation_deadline=r.cancellation_deadline,
        notice_period_days=r.notice_period_days,
        auto_renewal=r.auto_renewal if r.auto_renewal is not None else True,
        detection_confidence=r.detection_confidence or 0.0,
        detection_method=r.detection_method,
        match_count=r.match_count or 0,
        price_history=[PriceHistoryEntry(**(entry if isinstance(entry, dict) else {})) for entry in (r.price_history or [])],
        last_price_change_date=r.last_price_change_date,
        price_change_percent=r.price_change_percent,
        status=r.status,
        price_increase_alerted=r.price_increase_alerted or False,
        missing_invoice_alerted=r.missing_invoice_alerted or False,
        category=r.category,
        description=r.description,
        document_type=r.document_type,
        reference_pattern=r.reference_pattern,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _build_occurrence_response(o: "RecurringInvoiceOccurrence") -> OccurrenceResponse:
    """Erstellt OccurrenceResponse aus Model."""
    return OccurrenceResponse(
        id=o.id,
        recurring_invoice_id=o.recurring_invoice_id,
        document_id=o.document_id,
        invoice_tracking_id=o.invoice_tracking_id,
        expected_date=o.expected_date,
        actual_date=o.actual_date,
        expected_amount=float(o.expected_amount or 0),
        actual_amount=float(o.actual_amount) if o.actual_amount is not None else None,
        amount_deviation=float(o.amount_deviation) if o.amount_deviation is not None else None,
        status=o.status,
        match_confidence=o.match_confidence,
        matched_at=o.matched_at,
        matched_by=o.matched_by,
        period_start=o.period_start,
        period_end=o.period_end,
        notes=o.notes,
        created_at=o.created_at,
    )


# ============================================================================
# Detection Endpoint
# ============================================================================


@router.post(
    "/detect",
    response_model=List[DetectedPatternResponse],
    summary="Wiederkehrende Muster erkennen",
    description="Analysiert Rechnungshistorie und erkennt Abo-Muster",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def detect_recurring_invoices(
    request: Request,  # Required for rate limiter
    min_occurrences: int = Query(3, ge=2, le=20, description="Minimale Anzahl Vorkommen"),
    lookback_months: int = Query(12, ge=3, le=36, description="Analysezeitraum in Monaten"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[DetectedPatternResponse]:
    """Erkennt wiederkehrende Rechnungsmuster aus der Rechnungshistorie."""
    service = get_recurring_invoice_service()

    try:
        patterns = await service.detect_recurring_invoices(
            db,
            company_id=current_user.company_id,
            min_occurrences=min_occurrences,
            lookback_months=lookback_months,
        )

        return [
            DetectedPatternResponse(
                vendor_name=p.vendor_name,
                vendor_entity_id=p.vendor_entity_id,
                interval_type=p.interval_type,
                interval_months=p.interval_months,
                average_amount=float(p.average_amount),
                occurrences_found=p.occurrences_found,
                confidence=p.confidence,
                first_date=p.first_date,
                last_date=p.last_date,
            )
            for p in patterns
        ]

    except Exception as e:
        logger.exception("recurring_detection_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler bei der Erkennung wiederkehrender Rechnungen",
        )


# ============================================================================
# CRUD Endpoints
# ============================================================================


@router.get(
    "",
    response_model=RecurringInvoiceListResponse,
    summary="Wiederkehrende Rechnungen auflisten",
    description="Listet alle wiederkehrenden Rechnungen der Firma",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def list_recurring_invoices(
    request: Request,  # Required for rate limiter
    status_filter: Optional[RecurringInvoiceStatus] = Query(
        None, alias="status", description="Status-Filter"
    ),
    page: int = Query(0, ge=0, description="Seite (0-basiert)"),
    page_size: int = Query(25, ge=1, le=100, description="Einträge pro Seite"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringInvoiceListResponse:
    """Listet wiederkehrende Rechnungen."""
    service = get_recurring_invoice_service()

    items, total = await service.list_recurring_invoices(
        db,
        company_id=current_user.company_id,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )

    return RecurringInvoiceListResponse(
        items=[_build_recurring_response(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{recurring_id}",
    response_model=RecurringInvoiceDetailResponse,
    summary="Wiederkehrende Rechnung abrufen",
    description="Ruft eine wiederkehrende Rechnung mit Vorkommen ab",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_recurring_invoice(
    request: Request,  # Required for rate limiter
    recurring_id: UUID = Path(..., description="Wiederkehrende-Rechnung-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringInvoiceDetailResponse:
    """Ruft eine wiederkehrende Rechnung ab."""
    service = get_recurring_invoice_service()

    recurring = await service.get_recurring_invoice(db, recurring_id)

    if not recurring:
        raise HTTPException(status_code=404, detail="Wiederkehrende Rechnung nicht gefunden")

    if recurring.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Rechnung")

    base = _build_recurring_response(recurring)
    occurrences = [_build_occurrence_response(o) for o in (recurring.occurrences or [])]

    return RecurringInvoiceDetailResponse(
        **base.model_dump(),
        occurrences=occurrences,
    )


@router.post(
    "",
    response_model=RecurringInvoiceResponse,
    status_code=201,
    summary="Wiederkehrende Rechnung erstellen",
    description="Erstellt manuell eine neue wiederkehrende Rechnung",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def create_recurring_invoice(
    request: Request,  # Required for rate limiter
    data: RecurringInvoiceCreateSchema,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringInvoiceResponse:
    """Erstellt eine neue wiederkehrende Rechnung."""
    service = get_recurring_invoice_service()

    try:
        recurring = await service.create_recurring_invoice(
            db,
            RecurringInvoiceCreateRequest(
                company_id=current_user.company_id,
                vendor_name=data.vendor_name,
                interval_type=data.interval_type,
                interval_months=data.interval_months,
                expected_amount=data.expected_amount,
                currency=data.currency,
                tolerance_percent=data.tolerance_percent,
                vendor_entity_id=data.vendor_entity_id,
                first_seen_date=data.first_seen_date,
                next_expected_date=data.next_expected_date,
                cancellation_deadline=data.cancellation_deadline,
                notice_period_days=data.notice_period_days,
                auto_renewal=data.auto_renewal,
                category=data.category,
                description=data.description,
                document_type=data.document_type,
                reference_pattern=data.reference_pattern,
            ),
        )

        return _build_recurring_response(recurring)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Abo-Validierung"))
    except Exception as e:
        logger.exception("recurring_create_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Erstellen der wiederkehrenden Rechnung")


@router.patch(
    "/{recurring_id}",
    response_model=RecurringInvoiceResponse,
    summary="Wiederkehrende Rechnung aktualisieren",
    description="Aktualisiert eine wiederkehrende Rechnung",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def update_recurring_invoice(
    request: Request,  # Required for rate limiter
    data: RecurringInvoiceUpdateSchema,
    recurring_id: UUID = Path(..., description="Wiederkehrende-Rechnung-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringInvoiceResponse:
    """Aktualisiert eine wiederkehrende Rechnung."""
    service = get_recurring_invoice_service()

    try:
        recurring = await service.update_recurring_invoice(
            db,
            recurring_id,
            RecurringInvoiceUpdateRequest(
                status=data.status,
                expected_amount=data.expected_amount,
                interval_type=data.interval_type,
                interval_months=data.interval_months,
                tolerance_percent=data.tolerance_percent,
                cancellation_deadline=data.cancellation_deadline,
                notice_period_days=data.notice_period_days,
                auto_renewal=data.auto_renewal,
                next_expected_date=data.next_expected_date,
                category=data.category,
                description=data.description,
                reference_pattern=data.reference_pattern,
            ),
        )

        return _build_recurring_response(recurring)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Abo-Aktualisierung"))
    except Exception as e:
        logger.exception("recurring_update_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Aktualisieren der wiederkehrenden Rechnung")


# ============================================================================
# Analysis Endpoints
# ============================================================================


@router.get(
    "/missing",
    response_model=List[MissingInvoiceResponse],
    summary="Fehlende Rechnungen",
    description="Listet überfällige / fehlende erwartete Rechnungen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_missing_invoices(
    request: Request,  # Required for rate limiter
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[MissingInvoiceResponse]:
    """Gibt fehlende/überfällige Rechnungen zurück."""
    service = get_recurring_invoice_service()

    try:
        missing = await service.check_missing_invoices(db, current_user.company_id)

        return [
            MissingInvoiceResponse(
                recurring_invoice_id=m.recurring_invoice_id,
                vendor_name=m.vendor_name,
                expected_date=m.expected_date,
                expected_amount=float(m.expected_amount),
                days_overdue=m.days_overdue,
            )
            for m in missing
        ]

    except Exception as e:
        logger.exception("missing_invoices_check_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler bei der Prüfung fehlender Rechnungen")


@router.get(
    "/price-changes",
    response_model=List[PriceChangeResponse],
    summary="Preisänderungen",
    description="Listet nicht-alertierte Preisänderungen bei Abos",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_price_changes(
    request: Request,  # Required for rate limiter
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[PriceChangeResponse]:
    """Gibt Preisänderungen bei wiederkehrenden Rechnungen zurück."""
    service = get_recurring_invoice_service()

    try:
        changes = await service.check_price_changes(db, current_user.company_id)

        return [
            PriceChangeResponse(
                recurring_invoice_id=c.recurring_invoice_id,
                vendor_name=c.vendor_name,
                old_amount=float(c.old_amount),
                new_amount=float(c.new_amount),
                change_percent=c.change_percent,
                change_date=c.change_date,
            )
            for c in changes
        ]

    except Exception as e:
        logger.exception("price_changes_check_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler bei der Prüfung von Preisänderungen")


@router.get(
    "/soll-ist",
    response_model=SollIstReportResponse,
    summary="Soll/Ist-Vergleich",
    description="Erstellt Soll/Ist-Bericht für wiederkehrende Rechnungen",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_soll_ist_report(
    request: Request,  # Required for rate limiter
    year: int = Query(..., ge=2000, le=2100, description="Jahr"),
    month: int = Query(..., ge=1, le=12, description="Monat"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SollIstReportResponse:
    """Gibt Soll/Ist-Vergleichsbericht zurück."""
    service = get_recurring_invoice_service()

    try:
        report = await service.get_soll_ist_report(
            db,
            company_id=current_user.company_id,
            year=year,
            month=month,
        )

        return SollIstReportResponse(
            company_id=report.company_id,
            year=report.year,
            month=report.month,
            rows=[
                SollIstRowResponse(
                    recurring_invoice_id=r.recurring_invoice_id,
                    vendor_name=r.vendor_name,
                    category=r.category,
                    expected_amount=float(r.expected_amount),
                    actual_amount=float(r.actual_amount) if r.actual_amount is not None else None,
                    deviation=float(r.deviation) if r.deviation is not None else None,
                    deviation_percent=r.deviation_percent,
                    status=r.status,
                    expected_date=r.expected_date,
                    actual_date=r.actual_date,
                )
                for r in report.rows
            ],
            total_expected=float(report.total_expected),
            total_actual=float(report.total_actual),
            total_deviation=float(report.total_deviation),
            missing_count=report.missing_count,
            matched_count=report.matched_count,
            generated_at=report.generated_at,
        )

    except Exception as e:
        logger.exception("soll_ist_report_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Erstellen des Soll/Ist-Berichts")


# ============================================================================
# Manual Match Endpoint
# ============================================================================


@router.post(
    "/{recurring_id}/match",
    response_model=OccurrenceResponse,
    summary="Dokument manuell zuordnen",
    description="Ordnet ein Dokument manuell einem Abo zu",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def manual_match_document(
    request: Request,  # Required for rate limiter
    data: ManualMatchSchema,
    recurring_id: UUID = Path(..., description="Wiederkehrende-Rechnung-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> OccurrenceResponse:
    """Ordnet ein Dokument manuell einem Abo zu."""
    service = get_recurring_invoice_service()

    try:
        occurrence = await service.manual_match_document(
            db, recurring_id, data.document_id,
        )

        return _build_occurrence_response(occurrence)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(e, "Manuelle Zuordnung"))
    except Exception as e:
        logger.exception("manual_match_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler bei der manuellen Zuordnung")
