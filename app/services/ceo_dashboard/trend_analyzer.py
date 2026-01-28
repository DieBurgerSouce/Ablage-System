"""
Trend Analyzer

Analysiert Trends ueber Zeit fuer CEO Dashboard Sparklines.
Aggregiert Daten fuer Charts und Visualisierungen.

Feinpoliert und durchdacht - Enterprise Trend Analysis.
"""

from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, InvoiceTracking, ProcessingStatus
from app.db.models_alert import Alert
from app.services.ceo_dashboard.digital_twin_service import TrendData, TrendDataPoint

logger = structlog.get_logger(__name__)


class TrendAnalyzer:
    """Analysiert Trends fuer Sparklines."""

    def __init__(self) -> None:
        """Initialisiert Analyzer."""
        pass

    async def analyze(
        self,
        company_id: UUID,
        days: int,
        db: AsyncSession,
    ) -> TrendData:
        """
        Analysiert Trends ueber angegebenen Zeitraum.

        Args:
            company_id: Company UUID
            days: Anzahl Tage (typisch 7, 30, 90)
            db: Database session

        Returns:
            TrendData mit Datenpunkten fuer Charts
        """
        logger.info("trend_analyzer.analyze", company_id=str(company_id), days=days)

        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)

        # Parallele Aggregation aller Metriken
        documents = await self._analyze_documents(company_id, start_date, now, days, db)
        invoices = await self._analyze_invoices(company_id, start_date, now, days, db)
        auto_rate = await self._analyze_auto_process_rate(company_id, start_date, now, days, db)
        alerts = await self._analyze_alerts(company_id, start_date, now, days, db)

        return TrendData(
            documents_processed=documents,
            invoice_volume=invoices,
            auto_process_rate=auto_rate,
            alert_count=alerts,
        )

    async def _analyze_documents(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
        days: int,
        db: AsyncSession,
    ) -> List[TrendDataPoint]:
        """
        Analysiert Dokument-Verarbeitung ueber Zeit.

        Returns:
            Liste von TrendDataPoints mit Anzahl verarbeiteter Dokumente pro Tag
        """
        data_points: List[TrendDataPoint] = []

        # Tagweise Aggregation
        for day_offset in range(days):
            day_start = start_date + timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)

            query = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= day_start,
                    Document.created_at < day_end,
                    Document.deleted_at.is_(None),
                )
            )
            result = await db.execute(query)
            count = result.scalar() or 0

            data_points.append(
                TrendDataPoint(
                    timestamp=day_start,
                    value=float(count),
                    label=day_start.strftime("%d.%m"),
                )
            )

        return data_points

    async def _analyze_invoices(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
        days: int,
        db: AsyncSession,
    ) -> List[TrendDataPoint]:
        """
        Analysiert Rechnungsvolumen ueber Zeit.

        Returns:
            Liste von TrendDataPoints mit Summe der Rechnungsbetraege pro Tag
        """
        data_points: List[TrendDataPoint] = []

        # Tagweise Aggregation
        for day_offset in range(days):
            day_start = start_date + timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)

            query = select(
                func.coalesce(func.sum(InvoiceTracking.total_amount), 0)
            ).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= day_start.date(),
                    InvoiceTracking.invoice_date < day_end.date(),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            result = await db.execute(query)
            total = result.scalar() or 0

            data_points.append(
                TrendDataPoint(
                    timestamp=day_start,
                    value=float(total),
                    label=day_start.strftime("%d.%m"),
                )
            )

        return data_points

    async def _analyze_auto_process_rate(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
        days: int,
        db: AsyncSession,
    ) -> List[TrendDataPoint]:
        """
        Analysiert Auto-Process Rate ueber Zeit.

        Returns:
            Liste von TrendDataPoints mit Rate (0-1) pro Tag
        """
        data_points: List[TrendDataPoint] = []

        # Tagweise Aggregation
        for day_offset in range(days):
            day_start = start_date + timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)

            query = select(
                func.count(Document.id).filter(
                    Document.status == ProcessingStatus.COMPLETED
                ).label("completed"),
                func.count(Document.id).label("total"),
            ).where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= day_start,
                    Document.created_at < day_end,
                    Document.deleted_at.is_(None),
                )
            )
            result = await db.execute(query)
            row = result.first()

            completed = row.completed if row else 0
            total = row.total if row else 0
            rate = completed / total if total > 0 else 0.0

            data_points.append(
                TrendDataPoint(
                    timestamp=day_start,
                    value=rate,
                    label=day_start.strftime("%d.%m"),
                )
            )

        return data_points

    async def _analyze_alerts(
        self,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
        days: int,
        db: AsyncSession,
    ) -> List[TrendDataPoint]:
        """
        Analysiert Alert-Count ueber Zeit.

        Returns:
            Liste von TrendDataPoints mit Anzahl neuer Alerts pro Tag
        """
        data_points: List[TrendDataPoint] = []

        # Tagweise Aggregation
        for day_offset in range(days):
            day_start = start_date + timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)

            query = select(func.count(Alert.id)).where(
                and_(
                    Alert.company_id == company_id,
                    Alert.created_at >= day_start,
                    Alert.created_at < day_end,
                )
            )
            result = await db.execute(query)
            count = result.scalar() or 0

            data_points.append(
                TrendDataPoint(
                    timestamp=day_start,
                    value=float(count),
                    label=day_start.strftime("%d.%m"),
                )
            )

        return data_points
