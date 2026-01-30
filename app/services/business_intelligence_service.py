"""
Business Intelligence Service

Provides structured data analysis capabilities for the KI-Chat:
- Document searches with filters
- Financial analysis and trends
- Entity-based statistics
- Payment behavior predictions

This extends the RAG chat to answer business questions using
structured database queries in addition to document context.
"""

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, extract, case, desc, asc, text
from sqlalchemy.orm import selectinload

import structlog

from app.db.models import (
    Document,
    Invoice,
    BusinessEntity,
    User,
)
from app.core.config import settings
from app.core.safe_errors import safe_error_detail,  safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================

class QueryType(str, Enum):
    """Types of business intelligence queries."""
    DOCUMENT_SEARCH = "document_search"
    INVOICE_ANALYSIS = "invoice_analysis"
    ENTITY_STATISTICS = "entity_statistics"
    PAYMENT_PREDICTION = "payment_prediction"
    TREND_ANALYSIS = "trend_analysis"
    SUMMARY = "summary"


class TimeRange(str, Enum):
    """Predefined time ranges for analysis."""
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_QUARTER = "last_quarter"
    LAST_YEAR = "last_year"
    THIS_MONTH = "this_month"
    THIS_QUARTER = "this_quarter"
    THIS_YEAR = "this_year"
    ALL_TIME = "all_time"
    CUSTOM = "custom"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DocumentSearchResult:
    """Result of a document search query."""
    document_id: UUID
    filename: str
    document_type: Optional[str]
    entity_name: Optional[str]
    created_at: datetime
    match_reason: str
    relevance_score: float


@dataclass
class InvoiceAnalysisResult:
    """Result of invoice analysis."""
    total_count: int
    total_amount: Decimal
    paid_count: int
    paid_amount: Decimal
    open_count: int
    open_amount: Decimal
    overdue_count: int
    overdue_amount: Decimal
    average_payment_days: Optional[float]
    by_month: List[Dict[str, Any]]
    by_entity: List[Dict[str, Any]]


@dataclass
class EntityStatistics:
    """Statistics for a business entity."""
    entity_id: UUID
    entity_name: str
    entity_type: str
    document_count: int
    invoice_count: int
    total_revenue: Decimal
    total_open: Decimal
    average_payment_days: Optional[float]
    risk_score: Optional[int]
    last_activity: Optional[datetime]


@dataclass
class PaymentPrediction:
    """Payment prediction for an entity or invoice."""
    entity_id: Optional[UUID]
    entity_name: Optional[str]
    predicted_days: int
    confidence: float
    historical_avg_days: float
    recent_trend: str  # "improving", "stable", "worsening"
    factors: List[str]


@dataclass
class TrendDataPoint:
    """Single data point in a trend analysis."""
    period: str  # e.g., "2026-01", "Q1 2026"
    value: Decimal
    count: int
    change_percent: Optional[float]


@dataclass
class TrendAnalysisResult:
    """Result of trend analysis."""
    metric_name: str
    time_range: str
    data_points: List[TrendDataPoint]
    total: Decimal
    average: Decimal
    trend_direction: str  # "up", "down", "stable"
    change_percent: float


@dataclass
class BusinessIntelligenceResponse:
    """Unified response for BI queries."""
    query_type: QueryType
    summary: str  # Human-readable summary in German
    data: Any  # Type depends on query_type
    suggestions: List[str]  # Follow-up questions
    query_time_ms: int


# =============================================================================
# Service
# =============================================================================

class BusinessIntelligenceService:
    """
    Business Intelligence Service for structured data analysis.

    Integrates with KI-Chat to provide data-driven answers to business questions.
    """

    def __init__(self):
        self._query_patterns = self._init_query_patterns()

    def _init_query_patterns(self) -> Dict[str, List[str]]:
        """Initialize keyword patterns for query type detection."""
        return {
            QueryType.DOCUMENT_SEARCH: [
                "finde", "suche", "zeige", "dokumente", "rechnungen von",
                "vertraege", "alle dokumente", "liste",
            ],
            QueryType.INVOICE_ANALYSIS: [
                "rechnungen", "umsatz", "einnahmen", "ausgaben",
                "offene posten", "bezahlt", "unbezahlt", "faellig",
            ],
            QueryType.ENTITY_STATISTICS: [
                "kunde", "lieferant", "kunden", "lieferanten",
                "statistik", "uebersicht", "details zu",
            ],
            QueryType.PAYMENT_PREDICTION: [
                "wann zahlt", "zahlung erwartet", "prognose",
                "vorhersage", "zahlungsverhalten",
            ],
            QueryType.TREND_ANALYSIS: [
                "entwicklung", "trend", "verlauf", "im vergleich",
                "monatlich", "quartalsweise", "jaehrlich",
            ],
        }

    def detect_query_type(self, query: str) -> QueryType:
        """Detect the type of business query from natural language."""
        query_lower = query.lower()

        # Score each query type based on keyword matches
        scores: Dict[QueryType, int] = {qt: 0 for qt in QueryType}

        for query_type, keywords in self._query_patterns.items():
            for keyword in keywords:
                if keyword in query_lower:
                    scores[query_type] += 1

        # Return highest scoring type, default to SUMMARY
        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            return QueryType.SUMMARY
        return best_type

    def _get_time_range_dates(
        self,
        time_range: TimeRange,
        custom_start: Optional[date] = None,
        custom_end: Optional[date] = None,
    ) -> Tuple[date, date]:
        """Convert TimeRange enum to actual date range."""
        today = date.today()

        if time_range == TimeRange.CUSTOM and custom_start and custom_end:
            return custom_start, custom_end

        ranges = {
            TimeRange.LAST_7_DAYS: (today - timedelta(days=7), today),
            TimeRange.LAST_30_DAYS: (today - timedelta(days=30), today),
            TimeRange.LAST_QUARTER: (today - timedelta(days=90), today),
            TimeRange.LAST_YEAR: (today - timedelta(days=365), today),
            TimeRange.THIS_MONTH: (today.replace(day=1), today),
            TimeRange.THIS_QUARTER: (
                today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1),
                today
            ),
            TimeRange.THIS_YEAR: (today.replace(month=1, day=1), today),
            TimeRange.ALL_TIME: (date(2000, 1, 1), today),
        }

        return ranges.get(time_range, (today - timedelta(days=30), today))

    async def search_documents(
        self,
        db: AsyncSession,
        user_id: UUID,
        query: str,
        entity_name: Optional[str] = None,
        document_type: Optional[str] = None,
        time_range: TimeRange = TimeRange.ALL_TIME,
        limit: int = 20,
    ) -> BusinessIntelligenceResponse:
        """
        Search documents with filters based on natural language query.

        Examples:
        - "Finde alle Rechnungen von Mueller GmbH aus Q3"
        - "Zeige Vertraege aus den letzten 30 Tagen"
        """
        import time
        start_time = time.time()

        start_date, end_date = self._get_time_range_dates(time_range)

        # Build base query
        query_stmt = (
            select(Document)
            .where(Document.owner_id == user_id)
            .where(Document.created_at >= start_date)
            .where(Document.created_at <= end_date)
        )

        # Add entity filter if specified
        if entity_name:
            query_stmt = query_stmt.outerjoin(
                BusinessEntity,
                Document.entity_id == BusinessEntity.id
            ).where(
                BusinessEntity.name.ilike(f"%{entity_name}%")
            )

        # Add document type filter
        if document_type:
            query_stmt = query_stmt.where(
                Document.document_type.ilike(f"%{document_type}%")
            )

        # Search in filename or extracted text
        if query and len(query) > 3:
            search_pattern = f"%{query}%"
            query_stmt = query_stmt.where(
                or_(
                    Document.original_filename.ilike(search_pattern),
                    Document.extracted_text.ilike(search_pattern),
                )
            )

        query_stmt = query_stmt.order_by(desc(Document.created_at)).limit(limit)

        result = await db.execute(query_stmt)
        documents = result.scalars().all()

        # Build results
        results = []
        for doc in documents:
            results.append(DocumentSearchResult(
                document_id=doc.id,
                filename=doc.original_filename,
                document_type=doc.document_type,
                entity_name=None,  # Would need join
                created_at=doc.created_at,
                match_reason="Suchbegriff gefunden" if query else "Zeitraum-Filter",
                relevance_score=1.0,
            ))

        query_time_ms = int((time.time() - start_time) * 1000)

        # Generate summary
        summary = f"{len(results)} Dokumente gefunden"
        if entity_name:
            summary += f" fuer '{entity_name}'"
        if time_range != TimeRange.ALL_TIME:
            summary += f" im Zeitraum {start_date} bis {end_date}"

        return BusinessIntelligenceResponse(
            query_type=QueryType.DOCUMENT_SEARCH,
            summary=summary,
            data=[{
                "document_id": str(r.document_id),
                "filename": r.filename,
                "document_type": r.document_type,
                "created_at": r.created_at.isoformat(),
                "match_reason": r.match_reason,
            } for r in results],
            suggestions=[
                f"Zeige Details zu einem Dokument",
                f"Analysiere Rechnungen aus diesem Zeitraum",
            ],
            query_time_ms=query_time_ms,
        )

    async def analyze_invoices(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        entity_id: Optional[UUID] = None,
        time_range: TimeRange = TimeRange.THIS_YEAR,
    ) -> BusinessIntelligenceResponse:
        """
        Analyze invoices with aggregations and breakdowns.

        Examples:
        - "Wie viele Rechnungen sind offen?"
        - "Zeige Umsatz nach Monat"
        """
        import time
        start_time = time.time()

        start_date, end_date = self._get_time_range_dates(time_range)

        # Build base query
        base_filter = and_(
            Invoice.company_id == company_id,
            Invoice.invoice_date >= start_date,
            Invoice.invoice_date <= end_date,
        )

        if entity_id:
            base_filter = and_(base_filter, Invoice.entity_id == entity_id)

        # Get aggregates
        agg_query = select(
            func.count(Invoice.id).label("total_count"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("total_amount"),
            func.count(case((Invoice.status == "paid", 1))).label("paid_count"),
            func.coalesce(func.sum(case(
                (Invoice.status == "paid", Invoice.total_amount)
            )), 0).label("paid_amount"),
            func.count(case((Invoice.status != "paid", 1))).label("open_count"),
            func.coalesce(func.sum(case(
                (Invoice.status != "paid", Invoice.total_amount)
            )), 0).label("open_amount"),
        ).where(base_filter)

        agg_result = await db.execute(agg_query)
        agg_row = agg_result.fetchone()

        # Overdue count (due_date < today and not paid)
        overdue_query = select(
            func.count(Invoice.id).label("overdue_count"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("overdue_amount"),
        ).where(
            and_(
                base_filter,
                Invoice.status != "paid",
                Invoice.due_date < date.today(),
            )
        )
        overdue_result = await db.execute(overdue_query)
        overdue_row = overdue_result.fetchone()

        # Monthly breakdown
        monthly_query = select(
            func.date_trunc('month', Invoice.invoice_date).label("month"),
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("amount"),
        ).where(base_filter).group_by(
            func.date_trunc('month', Invoice.invoice_date)
        ).order_by(text("month"))

        monthly_result = await db.execute(monthly_query)
        by_month = [
            {
                "month": row.month.strftime("%Y-%m") if row.month else "Unknown",
                "count": row.count,
                "amount": float(row.amount),
            }
            for row in monthly_result.fetchall()
        ]

        # Top entities
        entity_query = select(
            Invoice.entity_id,
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("amount"),
        ).where(base_filter).group_by(
            Invoice.entity_id
        ).order_by(text("amount DESC")).limit(10)

        entity_result = await db.execute(entity_query)
        by_entity = [
            {
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "count": row.count,
                "amount": float(row.amount),
            }
            for row in entity_result.fetchall()
        ]

        query_time_ms = int((time.time() - start_time) * 1000)

        analysis = InvoiceAnalysisResult(
            total_count=agg_row.total_count,
            total_amount=Decimal(str(agg_row.total_amount)),
            paid_count=agg_row.paid_count,
            paid_amount=Decimal(str(agg_row.paid_amount)),
            open_count=agg_row.open_count,
            open_amount=Decimal(str(agg_row.open_amount)),
            overdue_count=overdue_row.overdue_count,
            overdue_amount=Decimal(str(overdue_row.overdue_amount)),
            average_payment_days=None,  # Would need additional query
            by_month=by_month,
            by_entity=by_entity,
        )

        # Generate summary
        summary = (
            f"Rechnungsanalyse: {analysis.total_count} Rechnungen mit "
            f"Gesamtvolumen {analysis.total_amount:,.2f} EUR. "
            f"Davon {analysis.open_count} offen ({analysis.open_amount:,.2f} EUR), "
            f"{analysis.overdue_count} ueberfaellig ({analysis.overdue_amount:,.2f} EUR)."
        )

        return BusinessIntelligenceResponse(
            query_type=QueryType.INVOICE_ANALYSIS,
            summary=summary,
            data={
                "total_count": analysis.total_count,
                "total_amount": float(analysis.total_amount),
                "paid_count": analysis.paid_count,
                "paid_amount": float(analysis.paid_amount),
                "open_count": analysis.open_count,
                "open_amount": float(analysis.open_amount),
                "overdue_count": analysis.overdue_count,
                "overdue_amount": float(analysis.overdue_amount),
                "by_month": by_month,
                "by_entity": by_entity,
            },
            suggestions=[
                "Zeige die ueberfaelligen Rechnungen",
                "Welcher Kunde hat die meisten offenen Posten?",
                "Wie hat sich der Umsatz im Vergleich zum Vorjahr entwickelt?",
            ],
            query_time_ms=query_time_ms,
        )

    async def get_entity_statistics(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        entity_name: Optional[str] = None,
        entity_id: Optional[UUID] = None,
    ) -> BusinessIntelligenceResponse:
        """
        Get statistics for a specific business entity.

        Examples:
        - "Zeige Details zu Mueller GmbH"
        - "Wie ist der Status von Kunde 12345?"
        """
        import time
        start_time = time.time()

        # Find entity
        entity_query = select(BusinessEntity).where(
            BusinessEntity.company_id == company_id
        )

        if entity_id:
            entity_query = entity_query.where(BusinessEntity.id == entity_id)
        elif entity_name:
            entity_query = entity_query.where(
                BusinessEntity.name.ilike(f"%{entity_name}%")
            )
        else:
            # Return top entities
            entity_query = entity_query.limit(10)

        result = await db.execute(entity_query)
        entities = result.scalars().all()

        if not entities:
            return BusinessIntelligenceResponse(
                query_type=QueryType.ENTITY_STATISTICS,
                summary=f"Keine Entitaet gefunden fuer '{entity_name or entity_id}'",
                data=[],
                suggestions=[
                    "Suche mit einem anderen Namen",
                    "Zeige alle Kunden",
                ],
                query_time_ms=int((time.time() - start_time) * 1000),
            )

        stats_list = []
        for entity in entities:
            # Get invoice statistics for this entity
            invoice_stats = await db.execute(
                select(
                    func.count(Invoice.id).label("invoice_count"),
                    func.coalesce(func.sum(Invoice.total_amount), 0).label("total_revenue"),
                    func.coalesce(func.sum(case(
                        (Invoice.status != "paid", Invoice.total_amount)
                    )), 0).label("total_open"),
                ).where(
                    and_(
                        Invoice.entity_id == entity.id,
                        Invoice.company_id == company_id,
                    )
                )
            )
            inv_row = invoice_stats.fetchone()

            # Get document count
            doc_count = await db.execute(
                select(func.count(Document.id)).where(
                    Document.entity_id == entity.id
                )
            )
            doc_count_val = doc_count.scalar() or 0

            stats = EntityStatistics(
                entity_id=entity.id,
                entity_name=entity.name,
                entity_type=entity.entity_type,
                document_count=doc_count_val,
                invoice_count=inv_row.invoice_count,
                total_revenue=Decimal(str(inv_row.total_revenue)),
                total_open=Decimal(str(inv_row.total_open)),
                average_payment_days=None,
                risk_score=entity.risk_score,
                last_activity=entity.updated_at,
            )
            stats_list.append(stats)

        query_time_ms = int((time.time() - start_time) * 1000)

        if len(stats_list) == 1:
            s = stats_list[0]
            summary = (
                f"{s.entity_name} ({s.entity_type}): "
                f"{s.invoice_count} Rechnungen, "
                f"Umsatz {s.total_revenue:,.2f} EUR, "
                f"Offen {s.total_open:,.2f} EUR"
            )
            if s.risk_score:
                summary += f", Risiko-Score {s.risk_score}"
        else:
            summary = f"{len(stats_list)} Entitaeten gefunden"

        return BusinessIntelligenceResponse(
            query_type=QueryType.ENTITY_STATISTICS,
            summary=summary,
            data=[{
                "entity_id": str(s.entity_id),
                "entity_name": s.entity_name,
                "entity_type": s.entity_type,
                "document_count": s.document_count,
                "invoice_count": s.invoice_count,
                "total_revenue": float(s.total_revenue),
                "total_open": float(s.total_open),
                "risk_score": s.risk_score,
                "last_activity": s.last_activity.isoformat() if s.last_activity else None,
            } for s in stats_list],
            suggestions=[
                f"Zeige Rechnungen von {stats_list[0].entity_name}" if stats_list else "Suche nach Kunden",
                "Wie ist das Zahlungsverhalten?",
            ],
            query_time_ms=query_time_ms,
        )

    async def predict_payment(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        entity_id: Optional[UUID] = None,
        entity_name: Optional[str] = None,
    ) -> BusinessIntelligenceResponse:
        """
        Predict payment behavior for an entity.

        Examples:
        - "Wann zahlt Mueller GmbH?"
        - "Zahlungsverhalten von Kunde X"
        """
        import time
        start_time = time.time()

        # Find entity
        entity_query = select(BusinessEntity).where(
            BusinessEntity.company_id == company_id
        )

        if entity_id:
            entity_query = entity_query.where(BusinessEntity.id == entity_id)
        elif entity_name:
            entity_query = entity_query.where(
                BusinessEntity.name.ilike(f"%{entity_name}%")
            )

        result = await db.execute(entity_query.limit(1))
        entity = result.scalar_one_or_none()

        if not entity:
            return BusinessIntelligenceResponse(
                query_type=QueryType.PAYMENT_PREDICTION,
                summary=f"Keine Entitaet gefunden fuer '{entity_name or entity_id}'",
                data=None,
                suggestions=["Suche mit einem anderen Namen"],
                query_time_ms=int((time.time() - start_time) * 1000),
            )

        # Calculate historical payment behavior
        # Get paid invoices with payment date
        paid_invoices = await db.execute(
            select(
                Invoice.invoice_date,
                Invoice.due_date,
                Invoice.paid_at,
            ).where(
                and_(
                    Invoice.entity_id == entity.id,
                    Invoice.status == "paid",
                    Invoice.paid_at.isnot(None),
                )
            ).order_by(desc(Invoice.paid_at)).limit(20)
        )

        payment_days = []
        for inv in paid_invoices.fetchall():
            if inv.paid_at and inv.invoice_date:
                days = (inv.paid_at.date() - inv.invoice_date).days
                payment_days.append(days)

        if payment_days:
            avg_days = sum(payment_days) / len(payment_days)
            recent_avg = sum(payment_days[:5]) / min(5, len(payment_days)) if payment_days else avg_days

            # Determine trend
            if len(payment_days) >= 5:
                if recent_avg < avg_days * 0.9:
                    trend = "improving"
                elif recent_avg > avg_days * 1.1:
                    trend = "worsening"
                else:
                    trend = "stable"
            else:
                trend = "stable"

            # Confidence based on data points
            confidence = min(0.9, 0.5 + len(payment_days) * 0.05)

            prediction = PaymentPrediction(
                entity_id=entity.id,
                entity_name=entity.name,
                predicted_days=int(recent_avg),
                confidence=confidence,
                historical_avg_days=avg_days,
                recent_trend=trend,
                factors=[
                    f"Basierend auf {len(payment_days)} historischen Zahlungen",
                    f"Durchschnitt: {avg_days:.1f} Tage",
                    f"Letzte 5: {recent_avg:.1f} Tage",
                ],
            )
        else:
            prediction = PaymentPrediction(
                entity_id=entity.id,
                entity_name=entity.name,
                predicted_days=30,  # Default assumption
                confidence=0.3,
                historical_avg_days=0,
                recent_trend="unknown",
                factors=["Keine historischen Zahlungsdaten vorhanden"],
            )

        query_time_ms = int((time.time() - start_time) * 1000)

        trend_text = {
            "improving": "verbessert sich",
            "worsening": "verschlechtert sich",
            "stable": "bleibt stabil",
            "unknown": "unbekannt",
        }

        summary = (
            f"Zahlungsprognose fuer {entity.name}: "
            f"Erwartete Zahlung in {prediction.predicted_days} Tagen "
            f"(Konfidenz: {prediction.confidence*100:.0f}%). "
            f"Trend: {trend_text[prediction.recent_trend]}."
        )

        return BusinessIntelligenceResponse(
            query_type=QueryType.PAYMENT_PREDICTION,
            summary=summary,
            data={
                "entity_id": str(prediction.entity_id),
                "entity_name": prediction.entity_name,
                "predicted_days": prediction.predicted_days,
                "confidence": prediction.confidence,
                "historical_avg_days": prediction.historical_avg_days,
                "recent_trend": prediction.recent_trend,
                "factors": prediction.factors,
            },
            suggestions=[
                f"Zeige offene Rechnungen von {entity.name}",
                "Mahnstufe erhoehen?",
            ],
            query_time_ms=query_time_ms,
        )

    async def analyze_trends(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        metric: str = "revenue",
        time_range: TimeRange = TimeRange.LAST_YEAR,
        group_by: str = "month",
    ) -> BusinessIntelligenceResponse:
        """
        Analyze trends for a given metric.

        Examples:
        - "Wie haben sich die Marketing-Ausgaben entwickelt?"
        - "Zeige Umsatzentwicklung pro Quartal"
        """
        import time
        start_time = time.time()

        start_date, end_date = self._get_time_range_dates(time_range)

        # Determine grouping function
        if group_by == "quarter":
            group_func = func.date_trunc('quarter', Invoice.invoice_date)
        elif group_by == "year":
            group_func = func.date_trunc('year', Invoice.invoice_date)
        else:
            group_func = func.date_trunc('month', Invoice.invoice_date)

        # Query based on metric
        query = select(
            group_func.label("period"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("value"),
            func.count(Invoice.id).label("count"),
        ).where(
            and_(
                Invoice.company_id == company_id,
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date <= end_date,
            )
        ).group_by(group_func).order_by(text("period"))

        result = await db.execute(query)
        rows = result.fetchall()

        data_points = []
        prev_value = None
        for row in rows:
            change_percent = None
            if prev_value and prev_value > 0:
                change_percent = ((float(row.value) - prev_value) / prev_value) * 100

            data_points.append(TrendDataPoint(
                period=row.period.strftime("%Y-%m") if row.period else "Unknown",
                value=Decimal(str(row.value)),
                count=row.count,
                change_percent=change_percent,
            ))
            prev_value = float(row.value)

        # Calculate totals and trend
        if data_points:
            total = sum(dp.value for dp in data_points)
            average = total / len(data_points)

            # Trend direction based on first vs last half
            mid = len(data_points) // 2
            first_half = sum(dp.value for dp in data_points[:mid]) if mid > 0 else Decimal(0)
            second_half = sum(dp.value for dp in data_points[mid:]) if mid > 0 else Decimal(0)

            if first_half > 0:
                change = ((second_half - first_half) / first_half) * 100
                if change > 10:
                    trend_direction = "up"
                elif change < -10:
                    trend_direction = "down"
                else:
                    trend_direction = "stable"
            else:
                trend_direction = "stable"
                change = 0
        else:
            total = Decimal(0)
            average = Decimal(0)
            trend_direction = "stable"
            change = 0

        query_time_ms = int((time.time() - start_time) * 1000)

        trend_text = {
            "up": "steigend",
            "down": "fallend",
            "stable": "stabil",
        }

        summary = (
            f"Trend-Analyse ({metric}): Gesamt {total:,.2f} EUR, "
            f"Durchschnitt {average:,.2f} EUR pro {group_by}. "
            f"Trend: {trend_text[trend_direction]} ({change:+.1f}%)."
        )

        return BusinessIntelligenceResponse(
            query_type=QueryType.TREND_ANALYSIS,
            summary=summary,
            data={
                "metric": metric,
                "time_range": f"{start_date} bis {end_date}",
                "total": float(total),
                "average": float(average),
                "trend_direction": trend_direction,
                "change_percent": float(change),
                "data_points": [{
                    "period": dp.period,
                    "value": float(dp.value),
                    "count": dp.count,
                    "change_percent": dp.change_percent,
                } for dp in data_points],
            },
            suggestions=[
                "Vergleiche mit Vorjahr",
                "Zeige nach Kunde aufgeschluesselt",
            ],
            query_time_ms=query_time_ms,
        )

    async def process_query(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        query: str,
    ) -> BusinessIntelligenceResponse:
        """
        Main entry point for processing business intelligence queries.

        Detects query type and routes to appropriate handler.
        """
        query_type = self.detect_query_type(query)

        logger.info(
            "bi_query_processing",
            user_id=str(user_id),
            query_type=query_type.value,
            query_length=len(query),
        )

        # Extract potential entity names (simple heuristic)
        entity_name = None
        for pattern in ["von ", "fuer ", "zu ", "kunde "]:
            if pattern in query.lower():
                idx = query.lower().find(pattern)
                remaining = query[idx + len(pattern):].strip()
                # Take first word/phrase as entity name
                words = remaining.split()
                if words:
                    entity_name = " ".join(words[:2])  # Take up to 2 words
                break

        # Route to appropriate handler
        try:
            if query_type == QueryType.DOCUMENT_SEARCH:
                return await self.search_documents(
                    db, user_id, query, entity_name=entity_name
                )
            elif query_type == QueryType.INVOICE_ANALYSIS:
                return await self.analyze_invoices(
                    db, user_id, company_id
                )
            elif query_type == QueryType.ENTITY_STATISTICS:
                return await self.get_entity_statistics(
                    db, user_id, company_id, entity_name=entity_name
                )
            elif query_type == QueryType.PAYMENT_PREDICTION:
                return await self.predict_payment(
                    db, user_id, company_id, entity_name=entity_name
                )
            elif query_type == QueryType.TREND_ANALYSIS:
                return await self.analyze_trends(
                    db, user_id, company_id
                )
            else:
                # Summary: combine multiple insights
                return await self.analyze_invoices(
                    db, user_id, company_id
                )
        except Exception as e:
            logger.error("bi_query_failed", **safe_error_log(e), query_type=query_type.value)
            return BusinessIntelligenceResponse(
                query_type=query_type,
                summary=safe_error_detail(e, "Analyse"),
                data=None,
                suggestions=["Versuchen Sie eine andere Frage"],
                query_time_ms=0,
            )


# =============================================================================
# Singleton
# =============================================================================

_bi_service: Optional[BusinessIntelligenceService] = None


def get_bi_service() -> BusinessIntelligenceService:
    """Get or create BusinessIntelligenceService singleton."""
    global _bi_service
    if _bi_service is None:
        _bi_service = BusinessIntelligenceService()
    return _bi_service
