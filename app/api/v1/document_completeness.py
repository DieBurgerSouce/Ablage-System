# -*- coding: utf-8 -*-
"""
Belegprüfung API Endpoints.

REST API für Belegvollständigkeitsprüfung:
- Vollständigkeits-Report
- Quick Score
- Buchungen ohne Beleg
- Rechnungsnummern-Lücken
- Fehlende monatliche Rechnungen
- Plausibilitaetsprobleme
- Datumskonsistenz
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User
from app.services.compliance.document_completeness_service import (
    document_completeness_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/document-completeness",
    tags=["Belegprüfung"],
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class UnmatchedBookingResponse(BaseModel):
    """Bankbuchung ohne zugeordneten Beleg."""

    transaction_id: UUID
    booking_date: date
    amount: float
    description: str
    counterparty: Optional[str] = None
    suggested_action: str


class InvoiceGapResponse(BaseModel):
    """Lücke in einer Rechnungsnummern-Sequenz."""

    vendor_name: str
    vendor_entity_id: Optional[UUID] = None
    last_number: str
    expected_next: str
    found_next: str
    gap_count: int


class MissingMonthlyInvoiceResponse(BaseModel):
    """Fehlende monatliche Rechnung."""

    vendor_name: str
    vendor_entity_id: Optional[UUID] = None
    expected_month: date
    expected_amount: Optional[float] = None
    category: Optional[str] = None
    last_invoice_date: Optional[date] = None


class PlausibilityIssueResponse(BaseModel):
    """Plausibilitaetsproblem bei einem Beleg."""

    document_id: UUID
    issue_type: str
    description: str
    severity: str
    amount: Optional[float] = None
    average_amount: Optional[float] = None
    deviation_percent: Optional[float] = None


class DateIssueResponse(BaseModel):
    """Datumsinkonsistenz bei einem Beleg."""

    document_id: UUID
    issue_type: str
    description: str
    document_date: date
    booking_date: Optional[date] = None
    gap_days: Optional[int] = None


class CompletenessReportResponse(BaseModel):
    """Vollständiger Belegcheck-Report."""

    company_id: UUID
    period_start: date
    period_end: date
    overall_score: float
    generated_at: str
    summary: Dict[str, int]
    unmatched_bookings: List[UnmatchedBookingResponse]
    invoice_gaps: List[InvoiceGapResponse]
    missing_monthly: List[MissingMonthlyInvoiceResponse]
    plausibility_issues: List[PlausibilityIssueResponse]
    date_issues: List[DateIssueResponse]
    recommendations: List[str]


class ScoreResponse(BaseModel):
    """Schneller Vollständigkeits-Score."""

    company_id: UUID
    period_start: date
    period_end: date
    score: float = Field(ge=0, le=100, description="Vollständigkeits-Score (0-100)")


# ============================================================================
# Helper
# ============================================================================


def _decimal_to_float(val: Optional[Decimal]) -> Optional[float]:
    """Konvertiert Decimal zu float für JSON-Serialisierung."""
    if val is None:
        return None
    return float(val)


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/report",
    response_model=CompletenessReportResponse,
    summary="Belegcheck-Report",
    description="Generiert einen vollständigen Belegvollständigkeits-Report",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_completeness_report(
    request: Request,  # Required for rate limiter
    year: int = Query(..., ge=2000, le=2100, description="Berichtsjahr"),
    quarter: Optional[int] = Query(None, ge=1, le=4, description="Quartal"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Monat"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CompletenessReportResponse:
    """Generiert einen vollständigen Belegcheck-Report."""
    try:
        report = await document_completeness_service.generate_completeness_report(
            db,
            company_id=current_user.company_id,
            year=year,
            quarter=quarter,
            month=month,
        )

        return CompletenessReportResponse(
            company_id=report.company_id,
            period_start=report.period_start,
            period_end=report.period_end,
            overall_score=report.overall_score,
            generated_at=report.generated_at.isoformat(),
            summary=report.summary,
            unmatched_bookings=[
                UnmatchedBookingResponse(
                    transaction_id=ub.transaction_id,
                    booking_date=ub.booking_date,
                    amount=float(ub.amount),
                    description=ub.description,
                    counterparty=ub.counterparty,
                    suggested_action=ub.suggested_action,
                )
                for ub in report.unmatched_bookings
            ],
            invoice_gaps=[
                InvoiceGapResponse(
                    vendor_name=ig.vendor_name,
                    vendor_entity_id=ig.vendor_entity_id,
                    last_number=ig.last_number,
                    expected_next=ig.expected_next,
                    found_next=ig.found_next,
                    gap_count=ig.gap_count,
                )
                for ig in report.invoice_gaps
            ],
            missing_monthly=[
                MissingMonthlyInvoiceResponse(
                    vendor_name=mm.vendor_name,
                    vendor_entity_id=mm.vendor_entity_id,
                    expected_month=mm.expected_month,
                    expected_amount=_decimal_to_float(mm.expected_amount),
                    category=mm.category,
                    last_invoice_date=mm.last_invoice_date,
                )
                for mm in report.missing_monthly
            ],
            plausibility_issues=[
                PlausibilityIssueResponse(
                    document_id=pi.document_id,
                    issue_type=pi.issue_type,
                    description=pi.description,
                    severity=pi.severity,
                    amount=_decimal_to_float(pi.amount),
                    average_amount=_decimal_to_float(pi.average_amount),
                    deviation_percent=pi.deviation_percent,
                )
                for pi in report.plausibility_issues
            ],
            date_issues=[
                DateIssueResponse(
                    document_id=di.document_id,
                    issue_type=di.issue_type,
                    description=di.description,
                    document_date=di.document_date,
                    booking_date=di.booking_date,
                    gap_days=di.gap_days,
                )
                for di in report.date_issues
            ],
            recommendations=report.recommendations,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=safe_error_detail(e, "Belegcheck-Report"),
        )
    except Exception as e:
        logger.exception("completeness_report_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Erstellen des Belegcheck-Reports",
        )


@router.get(
    "/score",
    response_model=ScoreResponse,
    summary="Vollständigkeits-Score",
    description="Berechnet einen schnellen Vollständigkeits-Score (0-100)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_score(
    request: Request,  # Required for rate limiter
    period_start: date = Query(..., description="Beginn des Prüfzeitraums"),
    period_end: date = Query(..., description="Ende des Prüfzeitraums"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreResponse:
    """Berechnet den Vollständigkeits-Score."""
    if period_end < period_start:
        raise HTTPException(
            status_code=400,
            detail="Enddatum muss nach Startdatum liegen",
        )

    try:
        score = await document_completeness_service.get_completeness_score(
            db,
            company_id=current_user.company_id,
            period_start=period_start,
            period_end=period_end,
        )

        return ScoreResponse(
            company_id=current_user.company_id,
            period_start=period_start,
            period_end=period_end,
            score=score,
        )

    except Exception as e:
        logger.exception("completeness_score_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Berechnen des Vollständigkeits-Scores",
        )


@router.get(
    "/unmatched-bookings",
    response_model=List[UnmatchedBookingResponse],
    summary="Buchungen ohne Beleg",
    description="Findet Bankbuchungen ohne zugeordneten Beleg",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_unmatched_bookings(
    request: Request,  # Required for rate limiter
    period_start: date = Query(..., description="Beginn des Prüfzeitraums"),
    period_end: date = Query(..., description="Ende des Prüfzeitraums"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[UnmatchedBookingResponse]:
    """Findet Bankbuchungen ohne zugeordneten Beleg."""
    if period_end < period_start:
        raise HTTPException(
            status_code=400,
            detail="Enddatum muss nach Startdatum liegen",
        )

    try:
        bookings = await document_completeness_service.check_bookings_without_receipts(
            db,
            company_id=current_user.company_id,
            period_start=period_start,
            period_end=period_end,
        )

        return [
            UnmatchedBookingResponse(
                transaction_id=b.transaction_id,
                booking_date=b.booking_date,
                amount=float(b.amount),
                description=b.description,
                counterparty=b.counterparty,
                suggested_action=b.suggested_action,
            )
            for b in bookings
        ]

    except Exception as e:
        logger.exception("unmatched_bookings_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Suchen von Buchungen ohne Beleg",
        )


@router.get(
    "/invoice-gaps",
    response_model=List[InvoiceGapResponse],
    summary="Rechnungsnummern-Lücken",
    description="Prüft Lücken in Rechnungsnummern-Sequenzen pro Lieferant",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_invoice_gaps(
    request: Request,  # Required for rate limiter
    vendor_id: Optional[UUID] = Query(None, description="Lieferanten-ID (optional)"),
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Jahr (optional)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[InvoiceGapResponse]:
    """Prüft Lücken in Rechnungsnummern-Sequenzen."""
    try:
        gaps = await document_completeness_service.check_invoice_number_gaps(
            db,
            company_id=current_user.company_id,
            vendor_entity_id=vendor_id,
            year=year,
        )

        return [
            InvoiceGapResponse(
                vendor_name=g.vendor_name,
                vendor_entity_id=g.vendor_entity_id,
                last_number=g.last_number,
                expected_next=g.expected_next,
                found_next=g.found_next,
                gap_count=g.gap_count,
            )
            for g in gaps
        ]

    except Exception as e:
        logger.exception("invoice_gaps_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Prüfen der Rechnungsnummern",
        )


@router.get(
    "/missing-monthly",
    response_model=List[MissingMonthlyInvoiceResponse],
    summary="Fehlende monatliche Rechnungen",
    description="Findet fehlende monatliche Rechnungen (z.B. Miete, Strom)",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_missing_monthly(
    request: Request,  # Required for rate limiter
    year: int = Query(..., ge=2000, le=2100, description="Prüf-Jahr"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[MissingMonthlyInvoiceResponse]:
    """Findet fehlende monatliche Rechnungen."""
    try:
        missing = await document_completeness_service.check_missing_monthly_invoices(
            db,
            company_id=current_user.company_id,
            year=year,
        )

        return [
            MissingMonthlyInvoiceResponse(
                vendor_name=m.vendor_name,
                vendor_entity_id=m.vendor_entity_id,
                expected_month=m.expected_month,
                expected_amount=_decimal_to_float(m.expected_amount),
                category=m.category,
                last_invoice_date=m.last_invoice_date,
            )
            for m in missing
        ]

    except Exception as e:
        logger.exception("missing_monthly_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Suchen fehlender monatlicher Rechnungen",
        )


@router.get(
    "/plausibility",
    response_model=List[PlausibilityIssueResponse],
    summary="Plausibilitaetsprobleme",
    description="Prüft Plausibilitaet von Betraegen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_plausibility_issues(
    request: Request,  # Required for rate limiter
    period_start: date = Query(..., description="Beginn des Prüfzeitraums"),
    period_end: date = Query(..., description="Ende des Prüfzeitraums"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[PlausibilityIssueResponse]:
    """Prüft Plausibilitaet von Betraegen."""
    if period_end < period_start:
        raise HTTPException(
            status_code=400,
            detail="Enddatum muss nach Startdatum liegen",
        )

    try:
        issues = await document_completeness_service.check_amount_plausibility(
            db,
            company_id=current_user.company_id,
            period_start=period_start,
            period_end=period_end,
        )

        return [
            PlausibilityIssueResponse(
                document_id=i.document_id,
                issue_type=i.issue_type,
                description=i.description,
                severity=i.severity,
                amount=_decimal_to_float(i.amount),
                average_amount=_decimal_to_float(i.average_amount),
                deviation_percent=i.deviation_percent,
            )
            for i in issues
        ]

    except Exception as e:
        logger.exception("plausibility_check_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler bei der Plausibilitaetsprüfung",
        )


@router.get(
    "/date-issues",
    response_model=List[DateIssueResponse],
    summary="Datumskonsistenz-Probleme",
    description="Prüft Datumskonsistenz von Belegen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_date_issues(
    request: Request,  # Required for rate limiter
    period_start: date = Query(..., description="Beginn des Prüfzeitraums"),
    period_end: date = Query(..., description="Ende des Prüfzeitraums"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[DateIssueResponse]:
    """Prüft Datumskonsistenz von Belegen."""
    if period_end < period_start:
        raise HTTPException(
            status_code=400,
            detail="Enddatum muss nach Startdatum liegen",
        )

    try:
        issues = await document_completeness_service.check_date_consistency(
            db,
            company_id=current_user.company_id,
            period_start=period_start,
            period_end=period_end,
        )

        return [
            DateIssueResponse(
                document_id=i.document_id,
                issue_type=i.issue_type,
                description=i.description,
                document_date=i.document_date,
                booking_date=i.booking_date,
                gap_days=i.gap_days,
            )
            for i in issues
        ]

    except Exception as e:
        logger.exception("date_issues_check_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler bei der Datumskonsistenzprüfung",
        )
