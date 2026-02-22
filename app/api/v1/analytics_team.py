"""
Analytics API Endpoints

Leichtgewichtige Endpoints für Analytics-Dashboard:
- /operations: Betriebsmetriken (Dokumente, OCR, Fehler, Verarbeitungszeiten)
- /finance: Finanzdaten (Offene Posten, Cashflow, Skonto, Mahnungen)
- /team-stats: Team-Produktivitaets-Statistiken pro Benutzer
- /team-workload: Heatmap-Daten (Wochentag x Stunde)
"""

from datetime import date, datetime, timezone, timedelta
from typing import Dict, List, Literal, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, AuditLog, User, ProcessingStatus
from app.api.dependencies import get_db, get_current_active_user, get_current_company_id
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# =============================================================================
# Pydantic Response Schemas
# =============================================================================


class DocumentsProcessedCount(BaseModel):
    """Dokument-Zaehler nach Zeitraum."""
    today: int = 0
    week: int = 0
    month: int = 0


class TopErrorEntry(BaseModel):
    """Haeufigster Fehlertyp."""
    error_type: str
    count: int


class OperationsResponse(BaseModel):
    """Response fuer Operations-Tab im Analytics-Dashboard."""
    documents_processed: DocumentsProcessedCount
    ocr_accuracy_percent: float = Field(0.0, description="OCR-Genauigkeit in Prozent (0-100)")
    ocr_accuracy_trend: Literal["up", "down", "neutral"] = "neutral"
    pending_approvals: int = 0
    oldest_approval_days: int = 0
    error_rate_percent: float = 0.0
    top_errors: List[TopErrorEntry] = Field(default_factory=list)
    avg_processing_time_ms: int = 0
    p95_processing_time_ms: int = 0
    auto_process_rate: float = Field(0.0, description="Automatisierungsrate (0-100)")


class CashflowTrendEntry(BaseModel):
    """Ein Datenpunkt im Cashflow-Trend."""
    date: str
    amount: float


class AgingBucketEntry(BaseModel):
    """Altersstruktur-Eintrag."""
    bucket: str
    count: int
    amount: float


class DunningStageEntry(BaseModel):
    """Mahnstufen-Eintrag."""
    stage: int
    count: int


class FinanceResponse(BaseModel):
    """Response fuer Finanzen-Tab im Analytics-Dashboard."""
    open_items_count: int = 0
    open_items_amount: float = 0.0
    cashflow_trend: List[CashflowTrendEntry] = Field(default_factory=list)
    skonto_realized: float = 0.0
    skonto_missed: float = 0.0
    overdue_count: int = 0
    overdue_amount: float = 0.0
    aging_buckets: List[AgingBucketEntry] = Field(default_factory=list)
    dunning_stages: List[DunningStageEntry] = Field(default_factory=list)


class UserStatEntry(BaseModel):
    """Team-Statistik pro Benutzer."""
    user_id: str
    username: str
    documents_processed: int
    avg_approval_time_hours: float
    ocr_corrections: int
    quality_score: float


class TeamStatsResponse(BaseModel):
    """Response fuer Team-Stats Endpoint."""
    user_stats: List[UserStatEntry]
    period: str
    total_documents: int


class WorkloadEntry(BaseModel):
    """Einzelner Workload-Heatmap-Eintrag."""
    user_id: str
    username: str
    day_of_week: int = Field(..., ge=0, le=6, description="0=Mo..6=So")
    hour: int = Field(..., ge=0, le=23)
    count: int


class TeamWorkloadResponse(BaseModel):
    """Response fuer Team-Workload Heatmap."""
    rows: List[WorkloadEntry]


def _get_period_start(period: str) -> datetime:
    """Berechnet den Startpunkt für den angegebenen Zeitraum."""
    now = datetime.now(timezone.utc)
    if period == "day":
        return now - timedelta(days=1)
    elif period == "week":
        return now - timedelta(weeks=1)
    elif period == "quarter":
        return now - timedelta(days=90)
    else:  # month (default)
        return now - timedelta(days=30)


@router.get(
    "/operations",
    response_model=OperationsResponse,
    summary="Betriebs-Metriken",
    description="Aggregierte Betriebsdaten fuer das Analytics-Dashboard (Operations-Tab)",
)
async def get_operations(
    period: Literal["day", "week", "month", "quarter"] = Query(
        "month", description="Zeitraum: day, week, month oder quarter",
    ),
    start_date: Optional[date] = Query(None, description="Starttermin (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Endtermin (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> OperationsResponse:
    """
    Holt Betriebs-Metriken fuer den Operations-Tab.

    **Enthaelt:**
    - Verarbeitete Dokumente (heute/Woche/Monat)
    - OCR-Genauigkeit + Trend
    - Ausstehende Genehmigungen
    - Fehlerquote + Top-Fehler
    - Verarbeitungszeiten (avg + P95)
    - Automatisierungsrate
    """
    logger.info(
        "analytics.get_operations",
        user_id=str(current_user.id),
        company_id=str(company_id),
        period=period,
    )

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # Period for trend comparison
    if start_date and end_date:
        period_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        period_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    else:
        period_start = _get_period_start(period)
        period_end = now

    base_filter = and_(
        Document.company_id == company_id,
        Document.deleted_at.is_(None),
    )

    try:
        # --- Documents processed: today / week / month ---
        doc_counts_result = await db.execute(
            select(
                func.count(Document.id).filter(Document.created_at >= today_start).label("today"),
                func.count(Document.id).filter(Document.created_at >= week_start).label("week"),
                func.count(Document.id).filter(Document.created_at >= month_start).label("month"),
            ).where(base_filter)
        )
        doc_counts = doc_counts_result.one()

        # --- OCR Accuracy (avg confidence in period) ---
        ocr_result = await db.execute(
            select(
                func.avg(Document.ocr_confidence).label("avg_confidence"),
            ).where(
                and_(
                    base_filter,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                    Document.ocr_confidence.isnot(None),
                )
            )
        )
        ocr_row = ocr_result.one()
        ocr_accuracy = round(float(ocr_row.avg_confidence or 0) * 100, 1)

        # OCR trend: compare current vs previous period
        period_duration = period_end - period_start
        prev_start = period_start - period_duration
        prev_ocr_result = await db.execute(
            select(func.avg(Document.ocr_confidence)).where(
                and_(
                    base_filter,
                    Document.created_at >= prev_start,
                    Document.created_at < period_start,
                    Document.ocr_confidence.isnot(None),
                )
            )
        )
        prev_ocr = float(prev_ocr_result.scalar() or 0)
        current_ocr = float(ocr_row.avg_confidence or 0)
        if prev_ocr > 0 and current_ocr > prev_ocr * 1.01:
            ocr_trend: Literal["up", "down", "neutral"] = "up"
        elif prev_ocr > 0 and current_ocr < prev_ocr * 0.99:
            ocr_trend = "down"
        else:
            ocr_trend = "neutral"

        # --- Pending approvals + oldest ---
        pending_approvals = 0
        oldest_approval_days = 0
        try:
            from app.db.models_privat_enterprise import ApprovalRequest, ApprovalStatus
            approval_result = await db.execute(
                select(
                    func.count(ApprovalRequest.id).label("count"),
                    func.min(ApprovalRequest.created_at).label("oldest"),
                ).where(
                    and_(
                        ApprovalRequest.company_id == company_id,
                        ApprovalRequest.status == ApprovalStatus.PENDING,
                    )
                )
            )
            approval_row = approval_result.one()
            pending_approvals = approval_row.count or 0
            if approval_row.oldest:
                oldest_approval_days = max(0, (now - approval_row.oldest).days)
        except Exception as e:
            logger.warning("analytics.operations.approvals_error", error_type=type(e).__name__)

        # --- Error rate + top errors ---
        error_result = await db.execute(
            select(
                func.count(Document.id).label("total"),
                func.count(Document.id).filter(
                    Document.status == ProcessingStatus.FAILED.value
                ).label("errors"),
            ).where(
                and_(
                    base_filter,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                )
            )
        )
        error_row = error_result.one()
        total_docs = error_row.total or 0
        error_count = error_row.errors or 0
        error_rate = round((error_count / max(total_docs, 1)) * 100, 1)

        # Top error types from audit log
        top_errors_list: List[TopErrorEntry] = []
        try:
            top_err_result = await db.execute(
                select(
                    AuditLog.action,
                    func.count(AuditLog.id).label("count"),
                ).where(
                    and_(
                        AuditLog.company_id == company_id,
                        AuditLog.created_at >= period_start,
                        AuditLog.created_at <= period_end,
                        AuditLog.success.is_(False),
                    )
                ).group_by(AuditLog.action)
                .order_by(func.count(AuditLog.id).desc())
                .limit(5)
            )
            for row in top_err_result.all():
                top_errors_list.append(TopErrorEntry(
                    error_type=row.action or "Unbekannt",
                    count=row.count,
                ))
        except Exception as e:
            logger.warning("analytics.operations.top_errors_error", error_type=type(e).__name__)

        # --- Processing times (avg + P95) ---
        timing_result = await db.execute(
            select(
                func.avg(Document.processing_duration_ms).label("avg_ms"),
                func.percentile_cont(0.95).within_group(
                    Document.processing_duration_ms
                ).label("p95_ms"),
            ).where(
                and_(
                    base_filter,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                    Document.processing_duration_ms.isnot(None),
                    Document.processing_duration_ms > 0,
                )
            )
        )
        timing_row = timing_result.one()
        avg_ms = int(timing_row.avg_ms or 0)
        p95_ms = int(timing_row.p95_ms or 0)

        # --- Auto-process rate ---
        auto_result = await db.execute(
            select(
                func.count(Document.id).label("total"),
                func.count(Document.id).filter(
                    Document.status == ProcessingStatus.COMPLETED.value
                ).label("completed"),
            ).where(
                and_(
                    base_filter,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                )
            )
        )
        auto_row = auto_result.one()
        auto_total = auto_row.total or 0
        auto_completed = auto_row.completed or 0
        auto_rate = round((auto_completed / max(auto_total, 1)) * 100, 1)

        return OperationsResponse(
            documents_processed=DocumentsProcessedCount(
                today=doc_counts.today or 0,
                week=doc_counts.week or 0,
                month=doc_counts.month or 0,
            ),
            ocr_accuracy_percent=ocr_accuracy,
            ocr_accuracy_trend=ocr_trend,
            pending_approvals=pending_approvals,
            oldest_approval_days=oldest_approval_days,
            error_rate_percent=error_rate,
            top_errors=top_errors_list,
            avg_processing_time_ms=avg_ms,
            p95_processing_time_ms=p95_ms,
            auto_process_rate=auto_rate,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "analytics.operations_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Betriebsdaten",
        )


@router.get(
    "/finance",
    response_model=FinanceResponse,
    summary="Finanz-Metriken",
    description="Aggregierte Finanzdaten fuer das Analytics-Dashboard (Finanzen-Tab)",
)
async def get_finance(
    period: Literal["day", "week", "month", "quarter"] = Query(
        "month", description="Zeitraum: day, week, month oder quarter",
    ),
    start_date: Optional[date] = Query(None, description="Starttermin (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Endtermin (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> FinanceResponse:
    """
    Holt Finanz-Metriken fuer den Finanzen-Tab.

    **Enthaelt:**
    - Offene Posten (Anzahl + Betrag)
    - Cashflow-Trend (letzte 30 Tage)
    - Skonto realisiert/verpasst
    - Ueberfaellige Posten
    - Altersstruktur (Aging Buckets)
    - Mahnstufen-Verteilung
    """
    logger.info(
        "analytics.get_finance",
        user_id=str(current_user.id),
        company_id=str(company_id),
        period=period,
    )

    now = datetime.now(timezone.utc)

    try:
        from app.db.models_entity_business import InvoiceTracking, InvoiceStatus

        doc_filter = and_(
            Document.company_id == company_id,
            Document.deleted_at.is_(None),
        )

        # --- Open items ---
        open_result = await db.execute(
            select(
                func.count(InvoiceTracking.id).label("count"),
                func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("total"),
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    doc_filter,
                    InvoiceTracking.status.in_([
                        InvoiceStatus.OPEN.value,
                        InvoiceStatus.SENT.value,
                        InvoiceStatus.PARTIAL.value,
                    ]),
                )
            )
        )
        open_row = open_result.one()
        open_count = open_row.count or 0
        open_amount = round(float(open_row.total or 0.0), 2)

        # --- Overdue items ---
        overdue_result = await db.execute(
            select(
                func.count(InvoiceTracking.id).label("count"),
                func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("total"),
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    doc_filter,
                    InvoiceTracking.due_date < now,
                    InvoiceTracking.status.in_([
                        InvoiceStatus.OPEN.value,
                        InvoiceStatus.SENT.value,
                        InvoiceStatus.OVERDUE.value,
                    ]),
                )
            )
        )
        overdue_row = overdue_result.one()
        overdue_count = overdue_row.count or 0
        overdue_amount = round(float(overdue_row.total or 0.0), 2)

        # --- Skonto realized / missed ---
        skonto_realized = 0.0
        skonto_missed = 0.0
        try:
            # Realized: skonto_used = True
            realized_result = await db.execute(
                select(
                    func.coalesce(func.sum(InvoiceTracking.skonto_amount), 0.0),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        doc_filter,
                        InvoiceTracking.skonto_used.is_(True),
                        InvoiceTracking.skonto_amount.isnot(None),
                    )
                )
            )
            skonto_realized = round(float(realized_result.scalar() or 0.0), 2)

            # Missed: skonto_deadline < now AND skonto_used = False AND still open/paid
            missed_result = await db.execute(
                select(
                    func.coalesce(func.sum(InvoiceTracking.skonto_amount), 0.0),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        doc_filter,
                        InvoiceTracking.skonto_used.is_(False),
                        InvoiceTracking.skonto_deadline.isnot(None),
                        InvoiceTracking.skonto_deadline < now,
                        InvoiceTracking.skonto_amount.isnot(None),
                    )
                )
            )
            skonto_missed = round(float(missed_result.scalar() or 0.0), 2)
        except Exception as e:
            logger.warning("analytics.finance.skonto_error", error_type=type(e).__name__)

        # --- Cashflow trend (paid invoices grouped by date, last 30 days) ---
        cashflow_trend: List[CashflowTrendEntry] = []
        try:
            thirty_days_ago = now - timedelta(days=30)
            trend_result = await db.execute(
                select(
                    func.date_trunc("day", InvoiceTracking.paid_at).label("pay_date"),
                    func.coalesce(func.sum(InvoiceTracking.paid_amount), 0.0).label("amount"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        doc_filter,
                        InvoiceTracking.paid_at >= thirty_days_ago,
                        InvoiceTracking.paid_at.isnot(None),
                        InvoiceTracking.status == InvoiceStatus.PAID.value,
                    )
                )
                .group_by(func.date_trunc("day", InvoiceTracking.paid_at))
                .order_by(func.date_trunc("day", InvoiceTracking.paid_at))
            )
            for row in trend_result.all():
                if row.pay_date:
                    cashflow_trend.append(CashflowTrendEntry(
                        date=row.pay_date.strftime("%Y-%m-%d"),
                        amount=round(float(row.amount or 0.0), 2),
                    ))
        except Exception as e:
            logger.warning("analytics.finance.cashflow_error", error_type=type(e).__name__)

        # --- Aging buckets ---
        aging_buckets: List[AgingBucketEntry] = []
        try:
            aging_result = await db.execute(
                select(
                    case(
                        (InvoiceTracking.due_date >= now, "Nicht faellig"),
                        (func.extract("day", now - InvoiceTracking.due_date) <= 30, "1-30 Tage"),
                        (func.extract("day", now - InvoiceTracking.due_date) <= 60, "31-60 Tage"),
                        (func.extract("day", now - InvoiceTracking.due_date) <= 90, "61-90 Tage"),
                        else_="Ueber 90 Tage",
                    ).label("bucket"),
                    func.count(InvoiceTracking.id).label("count"),
                    func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("amount"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        doc_filter,
                        InvoiceTracking.paid_at.is_(None),
                        InvoiceTracking.due_date.isnot(None),
                        InvoiceTracking.status.in_([
                            InvoiceStatus.OPEN.value,
                            InvoiceStatus.SENT.value,
                            InvoiceStatus.PARTIAL.value,
                            InvoiceStatus.OVERDUE.value,
                        ]),
                    )
                )
                .group_by("bucket")
            )
            for row in aging_result.all():
                aging_buckets.append(AgingBucketEntry(
                    bucket=row.bucket,
                    count=row.count or 0,
                    amount=round(float(row.amount or 0.0), 2),
                ))
        except Exception as e:
            logger.warning("analytics.finance.aging_error", error_type=type(e).__name__)

        # --- Dunning stages ---
        dunning_stages: List[DunningStageEntry] = []
        try:
            from app.db.models_banking import DunningRecord
            stages_result = await db.execute(
                select(
                    DunningRecord.dunning_level.label("stage"),
                    func.count(DunningRecord.id).label("count"),
                )
                .join(Document, DunningRecord.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        DunningRecord.status.notin_(["closed", "written_off"]),
                    )
                )
                .group_by(DunningRecord.dunning_level)
                .order_by(DunningRecord.dunning_level)
            )
            for row in stages_result.all():
                dunning_stages.append(DunningStageEntry(
                    stage=row.stage or 0,
                    count=row.count or 0,
                ))
        except Exception as e:
            logger.warning("analytics.finance.dunning_error", error_type=type(e).__name__)

        return FinanceResponse(
            open_items_count=open_count,
            open_items_amount=open_amount,
            cashflow_trend=cashflow_trend,
            skonto_realized=skonto_realized,
            skonto_missed=skonto_missed,
            overdue_count=overdue_count,
            overdue_amount=overdue_amount,
            aging_buckets=aging_buckets,
            dunning_stages=dunning_stages,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "analytics.finance_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Finanzdaten",
        )


@router.get(
    "/team-stats",
    response_model=TeamStatsResponse,
    summary="Team-Produktivitaets-Statistiken",
    description="Aggregierte Produktivitaetsdaten pro Benutzer für den angegebenen Zeitraum",
)
async def get_team_stats(
    period: Literal["day", "week", "month", "quarter"] = Query(
        "month",
        description="Zeitraum: day, week, month oder quarter",
    ),
    start_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Starttermin (YYYY-MM-DD). Ueberschreibt period.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Endtermin (YYYY-MM-DD). Ueberschreibt period.",
    ),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> TeamStatsResponse:
    """
    Holt Team-Produktivitaets-Statistiken.

    **Enthält pro Benutzer:**
    - documents_processed: Anzahl verarbeiteter Dokumente
    - avg_approval_time_hours: Durchschnittliche Freigabe-Dauer
    - ocr_corrections: Anzahl OCR-Korrekturen
    - quality_score: Qualitaets-Score (0-100)

    **Rollen:** Alle authentifizierten Benutzer (company-level)
    """
    logger.info(
        "analytics.get_team_stats",
        user_id=str(current_user.id),
        company_id=str(company_id),
        period=period,
    )

    if start_date and end_date:
        period_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        period_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    else:
        period_start = _get_period_start(period)
        period_end = datetime.now(timezone.utc)

    try:
        # Documents processed per user
        doc_result = await db.execute(
            select(
                Document.owner_id.label("user_id"),
                func.count(Document.id).label("documents_processed"),
                func.avg(Document.processing_duration_ms).label("avg_processing_ms"),
                func.avg(Document.ocr_confidence).label("avg_confidence"),
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                    Document.deleted_at.is_(None),
                )
            )
            .group_by(Document.owner_id)
        )
        doc_rows = doc_result.all()

        # OCR corrections per user (audit log entries with action containing 'ocr_correction')
        correction_result = await db.execute(
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("ocr_corrections"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.created_at <= period_end,
                    AuditLog.action.ilike("%ocr_correct%"),
                )
            )
            .group_by(AuditLog.user_id)
        )
        correction_rows = {
            str(row.user_id): row.ocr_corrections
            for row in correction_result.all()
        }

        # Approval actions per user (for avg approval time)
        approval_result = await db.execute(
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("approval_count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.created_at <= period_end,
                    AuditLog.action.ilike("%approv%"),
                    AuditLog.success.is_(True),
                )
            )
            .group_by(AuditLog.user_id)
        )
        approval_rows = {
            str(row.user_id): row.approval_count
            for row in approval_result.all()
        }

        # Get usernames
        user_ids = [row.user_id for row in doc_rows if row.user_id is not None]
        user_map: Dict[str, str] = {}
        if user_ids:
            user_result = await db.execute(
                select(User.id, User.username).where(User.id.in_(user_ids))
            )
            user_map = {
                str(row.id): row.username for row in user_result.all()
            }

        # Build response
        user_stats_list: List[UserStatEntry] = []
        total_documents = 0

        for row in doc_rows:
            if row.user_id is None:
                continue

            uid = str(row.user_id)
            doc_count = row.documents_processed or 0
            total_documents += doc_count
            avg_confidence = float(row.avg_confidence or 0)
            corrections = correction_rows.get(uid, 0)
            approvals = approval_rows.get(uid, 0)

            # Quality score: based on OCR confidence and correction ratio
            correction_ratio = corrections / max(doc_count, 1)
            quality_score = round(
                min(100, max(0, avg_confidence * 100 - correction_ratio * 10)),
                1,
            )

            # Estimate avg approval time (simplified: approvals / hours in period)
            period_hours = (datetime.now(timezone.utc) - period_start).total_seconds() / 3600
            avg_approval_hours = round(
                period_hours / max(approvals, 1), 1
            ) if approvals > 0 else 0

            user_stats_list.append(UserStatEntry(
                user_id=uid,
                username=user_map.get(uid, "Unbekannt"),
                documents_processed=doc_count,
                avg_approval_time_hours=avg_approval_hours,
                ocr_corrections=corrections,
                quality_score=quality_score,
            ))

        # Sort by documents_processed descending
        user_stats_list.sort(key=lambda x: x.documents_processed, reverse=True)

        return TeamStatsResponse(
            user_stats=user_stats_list,
            period=period,
            total_documents=total_documents,
        )

    except Exception as e:
        logger.error(
            "analytics.team_stats_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Team-Statistiken",
        )


@router.get(
    "/team-workload",
    response_model=TeamWorkloadResponse,
    summary="Team-Workload-Heatmap",
    description="Dokumentenverteilung nach Wochentag und Stunde für Heatmap-Visualisierung",
)
async def get_team_workload(
    period: Literal["day", "week", "month", "quarter"] = Query(
        "month",
        description="Zeitraum: day, week, month oder quarter",
    ),
    start_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Starttermin (YYYY-MM-DD). Überschreibt period.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Endtermin (YYYY-MM-DD). Überschreibt period.",
    ),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> TeamWorkloadResponse:
    """
    Holt Workload-Verteilung nach Wochentag (0=Mo..6=So) und Stunde (0-23).

    Ergebnis wird fuer Heatmap-Darstellung im Team-Tab verwendet.
    """
    logger.info(
        "analytics.get_team_workload",
        user_id=str(current_user.id),
        company_id=str(company_id),
        period=period,
    )

    if start_date and end_date:
        period_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        period_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    else:
        period_start = _get_period_start(period)
        period_end = datetime.now(timezone.utc)

    try:
        result = await db.execute(
            select(
                Document.owner_id.label("user_id"),
                func.extract("dow", Document.created_at).label("day_of_week_raw"),
                func.extract("hour", Document.created_at).label("hour"),
                func.count(Document.id).label("count"),
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                    Document.deleted_at.is_(None),
                )
            )
            .group_by(
                Document.owner_id,
                func.extract("dow", Document.created_at),
                func.extract("hour", Document.created_at),
            )
        )
        raw_rows = result.all()

        # Get usernames for all user_ids
        user_ids = list({row.user_id for row in raw_rows if row.user_id is not None})
        user_map: Dict[str, str] = {}
        if user_ids:
            user_result = await db.execute(
                select(User.id, User.username).where(User.id.in_(user_ids))
            )
            user_map = {str(row.id): row.username for row in user_result.all()}

        # PostgreSQL EXTRACT(dow) returns 0=Sunday..6=Saturday
        # Convert to ISO: 0=Monday..6=Sunday
        def pg_dow_to_iso(pg_dow: int) -> int:
            return (pg_dow - 1) % 7 if pg_dow > 0 else 6

        workload_rows: List[WorkloadEntry] = []
        for row in raw_rows:
            if row.user_id is None:
                continue
            uid = str(row.user_id)
            workload_rows.append(WorkloadEntry(
                user_id=uid,
                username=user_map.get(uid, "Unbekannt"),
                day_of_week=pg_dow_to_iso(int(row.day_of_week_raw)),
                hour=int(row.hour),
                count=row.count,
            ))

        return TeamWorkloadResponse(rows=workload_rows)

    except Exception as e:
        logger.error(
            "analytics.team_workload_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Workload-Daten",
        )
