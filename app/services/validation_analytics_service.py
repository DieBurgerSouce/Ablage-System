"""ValidationAnalyticsService - Statistiken und Analysen.

Dieser Service aggregiert und berechnet Statistiken fuer das
Validierungs-Dashboard.

Verwendung:
    from app.services.validation_analytics_service import get_validation_analytics_service

    service = get_validation_analytics_service(db)
    overview = await service.get_overview_stats()
"""
import uuid
from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from typing import Optional, List, Dict, Any
import structlog

from sqlalchemy import select, func, and_, or_, case, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ValidationQueueItem,
    ValidationFieldReview,
    ValidationAnalytics,
    ValidationStatus,
    User
)
from app.db.schemas import (
    ValidationAnalyticsOverview,
    EditorStats,
    EditorStatsListResponse,
    TrendDataPoint,
    TrendDataResponse,
    DocumentTypeStats,
    DocumentTypeStatsResponse,
    ConfidenceDistribution,
)

logger = structlog.get_logger(__name__)


class ValidationAnalyticsService:
    """Service fuer Validierungs-Statistiken und -Analysen."""

    def __init__(self, db: AsyncSession):
        """Initialisiere den Service."""
        self.db = db

    # =========================================================================
    # OVERVIEW STATS
    # =========================================================================

    async def get_overview_stats(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> ValidationAnalyticsOverview:
        """Holt Uebersichts-Statistiken.

        Args:
            date_from: Startdatum (optional)
            date_to: Enddatum (optional)

        Returns:
            ValidationAnalyticsOverview mit allen Metriken
        """
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # Queue Status Counts
        pending_count = await self._count_by_status(ValidationStatus.PENDING.value)
        in_progress_count = await self._count_by_status(ValidationStatus.IN_PROGRESS.value)

        # Today's counts
        approved_today = await self._count_completed_since(
            ValidationStatus.APPROVED.value, today_start
        )
        rejected_today = await self._count_completed_since(
            ValidationStatus.REJECTED.value, today_start
        )

        # Week/Month counts
        week_start_dt = datetime.combine(week_start, datetime.min.time())
        month_start_dt = datetime.combine(month_start, datetime.min.time())

        validated_this_week = await self._count_validated_since(week_start_dt)
        validated_this_month = await self._count_validated_since(month_start_dt)

        # Averages
        avg_time = await self._get_avg_validation_time()
        avg_corrections = await self._get_avg_corrections()

        # Confidence stats
        confidence_stats = await self._get_confidence_stats()

        # Top rejection categories
        top_rejections = await self._get_top_rejection_categories()

        return ValidationAnalyticsOverview(
            pending_count=pending_count,
            in_progress_count=in_progress_count,
            approved_today=approved_today,
            rejected_today=rejected_today,
            validated_this_week=validated_this_week,
            validated_this_month=validated_this_month,
            avg_validation_time_seconds=avg_time,
            avg_corrections_per_item=avg_corrections,
            avg_confidence_before=confidence_stats.get("avg_before"),
            avg_confidence_after=confidence_stats.get("avg_after"),
            confidence_improvement_percent=confidence_stats.get("improvement"),
            top_rejection_categories=top_rejections
        )

    async def _count_by_status(self, status: str) -> int:
        """Zaehlt Items nach Status."""
        result = await self.db.execute(
            select(func.count(ValidationQueueItem.id)).where(
                ValidationQueueItem.status == status
            )
        )
        return result.scalar() or 0

    async def _count_completed_since(self, status: str, since: datetime) -> int:
        """Zaehlt abgeschlossene Items seit einem Zeitpunkt."""
        result = await self.db.execute(
            select(func.count(ValidationQueueItem.id)).where(
                and_(
                    ValidationQueueItem.status == status,
                    ValidationQueueItem.validated_at >= since
                )
            )
        )
        return result.scalar() or 0

    async def _count_validated_since(self, since: datetime) -> int:
        """Zaehlt alle validierten Items seit einem Zeitpunkt."""
        result = await self.db.execute(
            select(func.count(ValidationQueueItem.id)).where(
                and_(
                    ValidationQueueItem.status.in_([
                        ValidationStatus.APPROVED.value,
                        ValidationStatus.REJECTED.value
                    ]),
                    ValidationQueueItem.validated_at >= since
                )
            )
        )
        return result.scalar() or 0

    async def _get_avg_validation_time(self) -> Optional[int]:
        """Berechnet durchschnittliche Validierungszeit."""
        result = await self.db.execute(
            select(func.avg(ValidationQueueItem.validation_duration_seconds)).where(
                ValidationQueueItem.validation_duration_seconds.isnot(None)
            )
        )
        avg = result.scalar()
        return int(avg) if avg else None

    async def _get_avg_corrections(self) -> Optional[float]:
        """Berechnet durchschnittliche Korrekturen pro Item."""
        result = await self.db.execute(
            select(func.avg(ValidationQueueItem.corrections_made)).where(
                ValidationQueueItem.status.in_([
                    ValidationStatus.APPROVED.value,
                    ValidationStatus.REJECTED.value
                ])
            )
        )
        avg = result.scalar()
        return round(float(avg), 2) if avg else None

    async def _get_confidence_stats(self) -> Dict[str, Optional[float]]:
        """Berechnet Confidence-Statistiken."""
        # Average before validation
        before_result = await self.db.execute(
            select(func.avg(ValidationQueueItem.overall_confidence)).where(
                ValidationQueueItem.overall_confidence.isnot(None)
            )
        )
        avg_before = before_result.scalar()

        # TODO: Average after would require storing post-validation confidence
        # For now, we estimate improvement based on corrections
        improvement = None
        if avg_before:
            avg_before = round(float(avg_before), 3)
            # Rough estimate: each correction improves confidence by 1%
            avg_corrections = await self._get_avg_corrections()
            if avg_corrections:
                improvement = round(avg_corrections * 0.01 * 100, 1)

        return {
            "avg_before": avg_before,
            "avg_after": None,  # Would need to be tracked separately
            "improvement": improvement
        }

    async def _get_top_rejection_categories(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Holt die haeufigsten Ablehnungskategorien."""
        result = await self.db.execute(
            select(
                ValidationQueueItem.rejection_category,
                func.count(ValidationQueueItem.id).label("count")
            )
            .where(
                and_(
                    ValidationQueueItem.status == ValidationStatus.REJECTED.value,
                    ValidationQueueItem.rejection_category.isnot(None)
                )
            )
            .group_by(ValidationQueueItem.rejection_category)
            .order_by(func.count(ValidationQueueItem.id).desc())
            .limit(limit)
        )

        rows = result.all()
        return [{"category": row[0], "count": row[1]} for row in rows]

    # =========================================================================
    # EDITOR STATS
    # =========================================================================

    async def get_editor_stats(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> EditorStatsListResponse:
        """Holt Statistiken pro Editor.

        Args:
            date_from: Startdatum
            date_to: Enddatum

        Returns:
            EditorStatsListResponse mit Editor-Statistiken
        """
        if not date_from:
            date_from = date.today() - timedelta(days=30)
        if not date_to:
            date_to = date.today()

        from_dt = datetime.combine(date_from, datetime.min.time())
        to_dt = datetime.combine(date_to, datetime.max.time())

        # Get editors with validations in period
        result = await self.db.execute(
            select(
                ValidationQueueItem.validated_by_id,
                func.count(ValidationQueueItem.id).label("total"),
                func.sum(case(
                    (ValidationQueueItem.status == ValidationStatus.APPROVED.value, 1),
                    else_=0
                )).label("approved"),
                func.sum(case(
                    (ValidationQueueItem.status == ValidationStatus.REJECTED.value, 1),
                    else_=0
                )).label("rejected"),
                func.avg(ValidationQueueItem.validation_duration_seconds).label("avg_time"),
                func.sum(ValidationQueueItem.corrections_made).label("corrections")
            )
            .where(
                and_(
                    ValidationQueueItem.validated_by_id.isnot(None),
                    ValidationQueueItem.validated_at >= from_dt,
                    ValidationQueueItem.validated_at <= to_dt
                )
            )
            .group_by(ValidationQueueItem.validated_by_id)
            .order_by(func.count(ValidationQueueItem.id).desc())
        )

        rows = result.all()
        editor_stats = []

        for row in rows:
            # Get editor name
            user_result = await self.db.execute(
                select(User.full_name, User.username).where(User.id == row[0])
            )
            user = user_result.one_or_none()
            editor_name = user[0] or user[1] if user else "Unbekannt"

            total = row[1] or 0
            approved = row[2] or 0
            rejected = row[3] or 0
            accuracy = round(approved / total * 100, 1) if total > 0 else None

            editor_stats.append(EditorStats(
                editor_id=row[0],
                editor_name=editor_name,
                items_validated=total,
                items_approved=approved,
                items_rejected=rejected,
                avg_validation_time_seconds=int(row[4]) if row[4] else None,
                corrections_made=row[5] or 0,
                accuracy_rate=accuracy
            ))

        return EditorStatsListResponse(
            editors=editor_stats,
            period_start=date_from,
            period_end=date_to
        )

    # =========================================================================
    # TREND DATA
    # =========================================================================

    async def get_trend_data(
        self,
        days: int = 30
    ) -> TrendDataResponse:
        """Holt Trend-Daten fuer Charts.

        Args:
            days: Anzahl der Tage

        Returns:
            TrendDataResponse mit Datenpunkten
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        # Get daily aggregates
        result = await self.db.execute(
            select(
                func.date(ValidationQueueItem.validated_at).label("day"),
                func.count(ValidationQueueItem.id).label("total"),
                func.sum(case(
                    (ValidationQueueItem.status == ValidationStatus.APPROVED.value, 1),
                    else_=0
                )).label("approved"),
                func.sum(case(
                    (ValidationQueueItem.status == ValidationStatus.REJECTED.value, 1),
                    else_=0
                )).label("rejected"),
                func.avg(ValidationQueueItem.validation_duration_seconds).label("avg_time")
            )
            .where(
                and_(
                    ValidationQueueItem.validated_at.isnot(None),
                    func.date(ValidationQueueItem.validated_at) >= start_date,
                    func.date(ValidationQueueItem.validated_at) <= end_date
                )
            )
            .group_by(func.date(ValidationQueueItem.validated_at))
            .order_by(func.date(ValidationQueueItem.validated_at))
        )

        rows = result.all()

        # Create data points for all days (fill gaps with zeros)
        data_dict = {row[0]: row for row in rows}
        data_points = []

        current_date = start_date
        while current_date <= end_date:
            row = data_dict.get(current_date)
            if row:
                data_points.append(TrendDataPoint(
                    date=current_date,
                    validated=row[1] or 0,
                    approved=row[2] or 0,
                    rejected=row[3] or 0,
                    avg_time_seconds=int(row[4]) if row[4] else None
                ))
            else:
                data_points.append(TrendDataPoint(
                    date=current_date,
                    validated=0,
                    approved=0,
                    rejected=0,
                    avg_time_seconds=None
                ))
            current_date += timedelta(days=1)

        return TrendDataResponse(
            data_points=data_points,
            group_by="day"
        )

    # =========================================================================
    # DOCUMENT TYPE STATS
    # =========================================================================

    async def get_document_type_stats(self) -> DocumentTypeStatsResponse:
        """Holt Statistiken pro Dokumenttyp.

        Returns:
            DocumentTypeStatsResponse
        """
        result = await self.db.execute(
            select(
                ValidationQueueItem.document_type,
                func.count(ValidationQueueItem.id).label("total"),
                func.sum(case(
                    (ValidationQueueItem.status == ValidationStatus.APPROVED.value, 1),
                    else_=0
                )).label("approved"),
                func.sum(case(
                    (ValidationQueueItem.status == ValidationStatus.REJECTED.value, 1),
                    else_=0
                )).label("rejected"),
                func.avg(ValidationQueueItem.overall_confidence).label("avg_confidence"),
                func.avg(
                    cast(ValidationQueueItem.corrections_made, Float) /
                    func.nullif(ValidationQueueItem.total_fields, 0)
                ).label("correction_rate")
            )
            .where(
                ValidationQueueItem.status.in_([
                    ValidationStatus.APPROVED.value,
                    ValidationStatus.REJECTED.value
                ])
            )
            .group_by(ValidationQueueItem.document_type)
            .order_by(func.count(ValidationQueueItem.id).desc())
        )

        rows = result.all()
        stats = []

        for row in rows:
            stats.append(DocumentTypeStats(
                document_type=row[0] or "Unbekannt",
                total_validated=row[1] or 0,
                approved=row[2] or 0,
                rejected=row[3] or 0,
                avg_confidence=round(float(row[4]), 3) if row[4] else None,
                correction_rate=round(float(row[5]) * 100, 1) if row[5] else None
            ))

        return DocumentTypeStatsResponse(document_types=stats)

    # =========================================================================
    # CONFIDENCE DISTRIBUTION
    # =========================================================================

    async def get_confidence_distribution(self) -> ConfidenceDistribution:
        """Berechnet die Konfidenz-Verteilung.

        Returns:
            ConfidenceDistribution mit Ranges und Statistiken
        """
        # Define ranges
        ranges = [
            {"min": 0.0, "max": 0.5, "label": "0-50%"},
            {"min": 0.5, "max": 0.7, "label": "50-70%"},
            {"min": 0.7, "max": 0.85, "label": "70-85%"},
            {"min": 0.85, "max": 0.95, "label": "85-95%"},
            {"min": 0.95, "max": 1.01, "label": "95-100%"},
        ]

        range_counts = []
        for r in ranges:
            result = await self.db.execute(
                select(func.count(ValidationQueueItem.id)).where(
                    and_(
                        ValidationQueueItem.overall_confidence >= r["min"],
                        ValidationQueueItem.overall_confidence < r["max"]
                    )
                )
            )
            count = result.scalar() or 0
            range_counts.append({
                "range": r["label"],
                "count": count,
                "min": r["min"],
                "max": r["max"]
            })

        # Get average and median
        avg_result = await self.db.execute(
            select(func.avg(ValidationQueueItem.overall_confidence)).where(
                ValidationQueueItem.overall_confidence.isnot(None)
            )
        )
        avg_confidence = avg_result.scalar()

        # Median is more complex - use percentile_cont if available
        # For simplicity, we'll use the average as approximation
        median_confidence = avg_confidence  # Simplified

        return ConfidenceDistribution(
            ranges=range_counts,
            avg_confidence=round(float(avg_confidence), 3) if avg_confidence else None,
            median_confidence=round(float(median_confidence), 3) if median_confidence else None
        )

    # =========================================================================
    # RECORD VALIDATION (Called after validation completes)
    # =========================================================================

    async def record_validation_completed(
        self,
        queue_item: ValidationQueueItem
    ) -> None:
        """Zeichnet eine abgeschlossene Validierung auf.

        Aktualisiert die Analytics-Tabelle fuer Dashboard-Berichte.

        Args:
            queue_item: Das abgeschlossene Queue-Item
        """
        if not queue_item.validated_at:
            return

        today = queue_item.validated_at.date()

        # Find or create analytics record for today + editor
        result = await self.db.execute(
            select(ValidationAnalytics).where(
                and_(
                    ValidationAnalytics.date == today,
                    ValidationAnalytics.editor_id == queue_item.validated_by_id,
                    ValidationAnalytics.document_type == queue_item.document_type,
                    ValidationAnalytics.hour.is_(None)  # Daily aggregate
                )
            )
        )
        analytics = result.scalar_one_or_none()

        if not analytics:
            analytics = ValidationAnalytics(
                date=today,
                editor_id=queue_item.validated_by_id,
                document_type=queue_item.document_type
            )
            self.db.add(analytics)

        # Update counts
        analytics.items_validated = (analytics.items_validated or 0) + 1

        if queue_item.status == ValidationStatus.APPROVED.value:
            analytics.items_approved = (analytics.items_approved or 0) + 1
        elif queue_item.status == ValidationStatus.REJECTED.value:
            analytics.items_rejected = (analytics.items_rejected or 0) + 1
        elif queue_item.status == ValidationStatus.SKIPPED.value:
            analytics.items_skipped = (analytics.items_skipped or 0) + 1

        # Update time stats
        if queue_item.validation_duration_seconds:
            duration = queue_item.validation_duration_seconds
            analytics.total_validation_time_seconds = (
                (analytics.total_validation_time_seconds or 0) + duration
            )

            # Update min/max
            if analytics.min_validation_time_seconds is None:
                analytics.min_validation_time_seconds = duration
            else:
                analytics.min_validation_time_seconds = min(
                    analytics.min_validation_time_seconds, duration
                )

            if analytics.max_validation_time_seconds is None:
                analytics.max_validation_time_seconds = duration
            else:
                analytics.max_validation_time_seconds = max(
                    analytics.max_validation_time_seconds, duration
                )

            # Recalculate average
            analytics.avg_validation_time_seconds = (
                analytics.total_validation_time_seconds // analytics.items_validated
            )

        # Update corrections
        analytics.corrections_made = (
            (analytics.corrections_made or 0) + (queue_item.corrections_made or 0)
        )
        analytics.umlaut_corrections = (
            (analytics.umlaut_corrections or 0) + (queue_item.umlaut_corrections or 0)
        )
        analytics.format_corrections = (
            (analytics.format_corrections or 0) + (queue_item.format_corrections or 0)
        )

        analytics.updated_at = utc_now()
        await self.db.commit()

        logger.debug(
            "validation_analytics_recorded",
            date=str(today),
            editor_id=str(queue_item.validated_by_id) if queue_item.validated_by_id else None,
            document_type=queue_item.document_type
        )


def get_validation_analytics_service(db: AsyncSession) -> ValidationAnalyticsService:
    """Factory-Funktion fuer den ValidationAnalyticsService.

    Args:
        db: Async-Datenbankverbindung

    Returns:
        ValidationAnalyticsService Instanz
    """
    return ValidationAnalyticsService(db)
