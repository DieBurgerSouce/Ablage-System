# -*- coding: utf-8 -*-
"""
Calendar API Endpoints.

REST API fuer Fristen- und Kalenderverwaltung:
- GET /deadlines - Alle Fristen
- GET /deadlines/summary - Zusammenfassung
- GET /deadlines/alerts - Dringende Fristen
- GET /calendar/month/{year}/{month} - Monats-Kalender
- GET /calendar/today - Heutige Fristen
"""

from datetime import datetime, date, timezone, timedelta
from typing import Optional, List
from uuid import UUID
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user
from app.services.calendar_service import (
    get_calendar_service,
    DeadlineCategory,
    DeadlineUrgency,
    DeadlineStatus,
    DeadlineItem,
    CalendarMonth,
    DeadlineSummary,
)


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/calendar", tags=["Calendar"])


# =============================================================================
# Response Models
# =============================================================================

class DeadlineResponse(BaseModel):
    """API Response fuer eine Frist."""
    id: str
    category: str
    title: str
    description: str
    deadline: datetime
    urgency: str
    status: str
    days_until: int
    document_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    contract_id: Optional[UUID] = None
    amount: Optional[float] = None
    currency: str = "EUR"
    metadata: dict = Field(default_factory=dict)


class DeadlineListResponse(BaseModel):
    """API Response fuer Fristen-Liste."""
    items: List[DeadlineResponse]
    total: int
    critical_count: int
    warning_count: int
    message: str


class DeadlineSummaryResponse(BaseModel):
    """API Response fuer Fristen-Zusammenfassung."""
    total_count: int
    critical_count: int
    warning_count: int
    upcoming_count: int
    scheduled_count: int
    overdue_count: int
    by_category: dict = Field(default_factory=dict)
    total_amount_at_risk: float
    next_deadline: Optional[DeadlineResponse] = None
    message: str


class CalendarDayResponse(BaseModel):
    """API Response fuer einen Kalendertag."""
    date: date
    deadlines: List[DeadlineResponse]
    deadline_count: int
    has_critical: bool
    total_amount_incoming: float
    total_amount_outgoing: float


class CalendarWeekResponse(BaseModel):
    """API Response fuer eine Kalenderwoche."""
    week_number: int
    year: int
    start_date: date
    end_date: date
    days: List[CalendarDayResponse]
    total_deadlines: int


class CalendarMonthResponse(BaseModel):
    """API Response fuer einen Kalendermonat."""
    month: int
    year: int
    weeks: List[CalendarWeekResponse]
    summary: dict = Field(default_factory=dict)
    message: str


class TodayResponse(BaseModel):
    """API Response fuer heutige Fristen."""
    date: date
    deadlines: List[DeadlineResponse]
    total_count: int
    critical_count: int
    total_amount_due: float
    message: str


# =============================================================================
# Helper Functions
# =============================================================================

def _deadline_to_response(deadline: DeadlineItem) -> DeadlineResponse:
    """Konvertiere DeadlineItem zu API Response."""
    return DeadlineResponse(
        id=deadline.id,
        category=deadline.category.value,
        title=deadline.title,
        description=deadline.description,
        deadline=deadline.deadline,
        urgency=deadline.urgency.value,
        status=deadline.status.value,
        days_until=deadline.days_until,
        document_id=deadline.document_id,
        entity_id=deadline.entity_id,
        invoice_id=deadline.invoice_id,
        contract_id=deadline.contract_id,
        amount=float(deadline.amount) if deadline.amount else None,
        currency=deadline.currency,
        metadata=deadline.metadata,
    )


# =============================================================================
# DEADLINE ENDPOINTS
# =============================================================================

@router.get(
    "/deadlines",
    response_model=DeadlineListResponse,
    summary="Alle Fristen auflisten",
    description="Listet alle Fristen fuer einen Zeitraum"
)
async def list_deadlines(
    start_date: Optional[date] = Query(None, description="Startdatum (default: heute - 7 Tage)"),
    end_date: Optional[date] = Query(None, description="Enddatum (default: heute + 90 Tage)"),
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    include_completed: bool = Query(False, description="Erledigte einschliessen"),
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DeadlineListResponse:
    """
    Listet alle Fristen auf.

    **Kategorien:**
    - skonto: Skonto-Fristen
    - payment_incoming: Erwartete Zahlungseingaenge
    - payment_outgoing: Faellige Zahlungen
    - tax: Steuertermine
    - contract: Vertragsfristen
    - dunning: Mahnfristen
    - custom: Benutzerdefinierte Fristen

    **Filter:**
    - start_date/end_date: Zeitraum
    - category: Nur bestimmte Kategorie
    - include_completed: Auch erledigte Fristen

    **Sortierung:**
    Nach Dringlichkeit (ueberfaellig zuerst, dann nach Datum)
    """
    service = get_calendar_service()

    # Kategorie validieren
    categories = None
    if category:
        try:
            categories = [DeadlineCategory(category)]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekannte Kategorie '{category}'. Gueltig: {[c.value for c in DeadlineCategory]}"
            )

    # Company ID aus User holen
    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    try:
        deadlines = await service.get_all_deadlines(
            db=db,
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            include_completed=include_completed,
            limit=limit,
        )

        items = [_deadline_to_response(d) for d in deadlines]
        critical = sum(1 for d in deadlines if d.urgency == DeadlineUrgency.CRITICAL)
        warning = sum(1 for d in deadlines if d.urgency == DeadlineUrgency.WARNING)

        logger.info(
            "deadlines_listed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            count=len(items),
            critical=critical,
        )

        return DeadlineListResponse(
            items=items,
            total=len(items),
            critical_count=critical,
            warning_count=warning,
            message=f"{len(items)} Fristen gefunden, {critical} kritisch"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("deadlines_list_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Fristen"
        )


@router.get(
    "/deadlines/summary",
    response_model=DeadlineSummaryResponse,
    summary="Fristen-Zusammenfassung",
    description="Aggregierte Statistiken zu allen Fristen"
)
async def get_deadline_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DeadlineSummaryResponse:
    """
    Holt eine Zusammenfassung aller aktuellen Fristen.

    **Enthaelt:**
    - Anzahl nach Dringlichkeitsstufe
    - Verteilung nach Kategorie
    - Gesamtbetrag gefaehrdeter Zahlungen
    - Naechste anstehende Frist
    """
    service = get_calendar_service()

    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    try:
        summary = await service.get_deadline_summary(db, company_id)

        next_deadline_response = None
        if summary.next_deadline:
            next_deadline_response = _deadline_to_response(summary.next_deadline)

        # Kategorie-Verteilung zu strings konvertieren
        by_category = {k.value: v for k, v in summary.by_category.items()}

        logger.info(
            "deadline_summary_retrieved",
            user_id=str(current_user.id),
            company_id=str(company_id),
            total=summary.total_count,
            critical=summary.critical_count,
        )

        return DeadlineSummaryResponse(
            total_count=summary.total_count,
            critical_count=summary.critical_count,
            warning_count=summary.warning_count,
            upcoming_count=summary.upcoming_count,
            scheduled_count=summary.scheduled_count,
            overdue_count=summary.overdue_count,
            by_category=by_category,
            total_amount_at_risk=float(summary.total_amount_at_risk),
            next_deadline=next_deadline_response,
            message=f"{summary.total_count} Fristen, {summary.critical_count} kritisch, {summary.overdue_count} ueberfaellig"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("deadline_summary_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Fristen-Zusammenfassung"
        )


@router.get(
    "/deadlines/alerts",
    response_model=DeadlineListResponse,
    summary="Dringende Fristen (Alerts)",
    description="Nur kritische und warnende Fristen fuer Benachrichtigungen"
)
async def get_deadline_alerts(
    days_ahead: int = Query(7, ge=1, le=30, description="Tage im Voraus"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DeadlineListResponse:
    """
    Holt nur dringende Fristen fuer Benachrichtigungen.

    **Enthaelt nur:**
    - Kritische Fristen (heute oder ueberfaellig)
    - Warnungen (innerhalb 3 Tagen)

    **Ideal fuer:**
    - Dashboard-Widgets
    - E-Mail-Benachrichtigungen
    - Push-Notifications
    """
    service = get_calendar_service()

    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    try:
        alerts = await service.get_upcoming_alerts(db, company_id, days_ahead)

        items = [_deadline_to_response(d) for d in alerts]
        critical = sum(1 for d in alerts if d.urgency == DeadlineUrgency.CRITICAL)
        warning = sum(1 for d in alerts if d.urgency == DeadlineUrgency.WARNING)

        logger.info(
            "deadline_alerts_retrieved",
            user_id=str(current_user.id),
            company_id=str(company_id),
            count=len(items),
            critical=critical,
        )

        return DeadlineListResponse(
            items=items,
            total=len(items),
            critical_count=critical,
            warning_count=warning,
            message=f"{critical} kritische und {warning} warnende Fristen"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("deadline_alerts_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Fristen-Alerts"
        )


# =============================================================================
# CALENDAR VIEW ENDPOINTS
# =============================================================================

@router.get(
    "/month/{year}/{month}",
    response_model=CalendarMonthResponse,
    summary="Kalender-Monatsansicht",
    description="Zeigt alle Fristen in einer Kalender-Monatsansicht"
)
async def get_calendar_month(
    year: int = Path(..., ge=2020, le=2100, description="Jahr"),
    month: int = Path(..., ge=1, le=12, description="Monat (1-12)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarMonthResponse:
    """
    Holt eine Kalender-Ansicht fuer einen Monat.

    **Struktur:**
    - Wochen mit Start/Ende
    - Tage mit Fristen
    - Betraege pro Tag (eingehend/ausgehend)
    - Zusammenfassung nach Kategorie
    """
    service = get_calendar_service()

    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    try:
        calendar_month = await service.get_calendar_month(db, company_id, year, month)

        # Zu Response-Models konvertieren
        weeks_response: List[CalendarWeekResponse] = []
        for week in calendar_month.weeks:
            days_response: List[CalendarDayResponse] = []
            for day in week.days:
                deadlines_response = [_deadline_to_response(d) for d in day.deadlines]
                days_response.append(CalendarDayResponse(
                    date=day.date,
                    deadlines=deadlines_response,
                    deadline_count=day.deadline_count,
                    has_critical=day.has_critical,
                    total_amount_incoming=float(day.total_amount_incoming),
                    total_amount_outgoing=float(day.total_amount_outgoing),
                ))

            weeks_response.append(CalendarWeekResponse(
                week_number=week.week_number,
                year=week.year,
                start_date=week.start_date,
                end_date=week.end_date,
                days=days_response,
                total_deadlines=week.total_deadlines,
            ))

        # Summary zu strings konvertieren
        summary = {k.value: v for k, v in calendar_month.summary.items()}

        logger.info(
            "calendar_month_retrieved",
            user_id=str(current_user.id),
            company_id=str(company_id),
            year=year,
            month=month,
        )

        return CalendarMonthResponse(
            month=month,
            year=year,
            weeks=weeks_response,
            summary=summary,
            message=f"Kalender fuer {month}/{year}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "calendar_month_failed",
            user_id=str(current_user.id),
            year=year,
            month=month,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Kalenders"
        )


@router.get(
    "/today",
    response_model=TodayResponse,
    summary="Heutige Fristen",
    description="Alle heute faelligen Fristen"
)
async def get_today_deadlines(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TodayResponse:
    """
    Holt alle heute faelligen Fristen.

    **Ideal fuer:**
    - Tages-Dashboard
    - Morgendliche Uebersicht
    - Quick-Actions
    """
    service = get_calendar_service()

    company_id = getattr(current_user, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    today = date.today()

    try:
        deadlines = await service.get_all_deadlines(
            db=db,
            company_id=company_id,
            start_date=today,
            end_date=today,
            limit=100,
        )

        items = [_deadline_to_response(d) for d in deadlines]
        critical = sum(1 for d in deadlines if d.urgency == DeadlineUrgency.CRITICAL)
        total_amount = sum(float(d.amount or 0) for d in deadlines)

        logger.info(
            "today_deadlines_retrieved",
            user_id=str(current_user.id),
            company_id=str(company_id),
            count=len(items),
        )

        return TodayResponse(
            date=today,
            deadlines=items,
            total_count=len(items),
            critical_count=critical,
            total_amount_due=total_amount,
            message=f"{len(items)} Fristen heute, {critical} kritisch"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("today_deadlines_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der heutigen Fristen"
        )
