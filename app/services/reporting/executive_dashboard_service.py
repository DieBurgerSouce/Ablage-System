"""
Executive Dashboard Service

Service für Geschäftsführung Dashboard - KPIs, Trends, Abteilungsstatistiken.
Alle Abfragen sind read-only und optimiert für Reporting.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from uuid import UUID

from sqlalchemy import func, select, cast, Float, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.schemas.reporting import (
    KPIResponse,
    DepartmentBreakdown,
    TrendResponse,
    TrendDataPoint,
)
from app.db.models import Document, User

logger = structlog.get_logger(__name__)


class ExecutiveDashboardService:
    """Service für Executive Dashboard Reporting."""

    def __init__(self, db: AsyncSession, company_id: UUID):
        """
        Initialize service.

        Args:
            db: Database session
            company_id: Company ID für Multi-Tenant Isolation
        """
        self.db = db
        self.company_id = company_id

    async def get_kpis(self) -> KPIResponse:
        """
        Hole Key Performance Indicators.

        Returns:
            KPIResponse mit aktuellen KPIs und Trends

        Raises:
            Exception: Bei Datenbankfehlern
        """
        try:
            now = datetime.now(timezone.utc)
            current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

            # Dokumente aktueller Monat
            stmt_current = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.created_at >= current_month_start,
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_current)
            docs_current = result.scalar() or 0

            # Dokumente letzter Monat
            stmt_last = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.created_at >= last_month_start,
                    Document.created_at < current_month_start,
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_last)
            docs_last = result.scalar() or 0

            # Trend berechnen
            if docs_last > 0:
                docs_trend = ((docs_current - docs_last) / docs_last) * 100
            else:
                docs_trend = 100.0 if docs_current > 0 else 0.0

            # Durchschnittliche Verarbeitungszeit (aktueller Monat)
            stmt_proc_current = select(
                func.coalesce(func.avg(Document.processing_duration_ms), 0.0)
            ).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.created_at >= current_month_start,
                    Document.processing_duration_ms.isnot(None),
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_proc_current)
            proc_current = float(result.scalar() or 0.0)

            # Durchschnittliche Verarbeitungszeit (letzter Monat)
            stmt_proc_last = select(
                func.coalesce(func.avg(Document.processing_duration_ms), 0.0)
            ).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.created_at >= last_month_start,
                    Document.created_at < current_month_start,
                    Document.processing_duration_ms.isnot(None),
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_proc_last)
            proc_last = float(result.scalar() or 0.0)

            # Verarbeitungszeit-Trend (negativ = Verbesserung)
            if proc_last > 0:
                proc_trend = ((proc_current - proc_last) / proc_last) * 100
            else:
                proc_trend = 0.0

            # OCR Accuracy (aktueller Monat)
            stmt_ocr_current = select(
                func.coalesce(func.avg(Document.ocr_confidence), 0.0)
            ).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.created_at >= current_month_start,
                    Document.ocr_confidence.isnot(None),
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_ocr_current)
            ocr_current = float(result.scalar() or 0.0)

            # OCR Accuracy (letzter Monat)
            stmt_ocr_last = select(
                func.coalesce(func.avg(Document.ocr_confidence), 0.0)
            ).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.created_at >= last_month_start,
                    Document.created_at < current_month_start,
                    Document.ocr_confidence.isnot(None),
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_ocr_last)
            ocr_last = float(result.scalar() or 0.0)

            # OCR Accuracy Trend
            if ocr_last > 0:
                ocr_trend = ((ocr_current - ocr_last) / ocr_last) * 100
            else:
                ocr_trend = 0.0

            # Geschätzte Kosten pro Dokument (0.10 EUR pro Sekunde Verarbeitungszeit)
            cost_per_doc = (proc_current / 1000.0) * 0.10 if proc_current > 0 else 0.0

            # Aktive Benutzer (mindestens 1 Dokument hochgeladen im aktuellen Monat)
            stmt_users = select(func.count(func.distinct(Document.uploaded_by))).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.created_at >= current_month_start,
                    Document.uploaded_by.isnot(None),
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_users)
            active_users = result.scalar() or 0

            # Ausstehende Prüfungen (Status = PENDING oder PROCESSING)
            stmt_pending = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.status.in_(["PENDING", "PROCESSING"]),
                    Document.deleted_at.is_(None),
                )
            )
            result = await self.db.execute(stmt_pending)
            pending = result.scalar() or 0

            return KPIResponse(
                documents_this_month=docs_current,
                documents_last_month=docs_last,
                documents_trend_percent=round(docs_trend, 1),
                avg_processing_time_ms=round(proc_current, 0),
                processing_time_trend_percent=round(proc_trend, 1),
                ocr_accuracy=round(ocr_current, 3),
                ocr_accuracy_trend=round(ocr_trend, 1),
                cost_per_document=round(cost_per_doc, 2),
                active_users_count=active_users,
                pending_reviews=pending,
            )

        except Exception as e:
            logger.error("kpi_abruf_fehlgeschlagen", error=str(e), company_id=str(self.company_id))
            raise

    async def get_department_breakdown(self) -> List[DepartmentBreakdown]:
        """
        Hole Statistiken nach Abteilungen/Bereichen.

        Verwendet document_type als Proxy für Abteilung/Bereich.

        Returns:
            Liste von DepartmentBreakdown

        Raises:
            Exception: Bei Datenbankfehlern
        """
        try:
            # Gruppiere nach document_type (als Proxy für Abteilung)
            stmt = select(
                Document.document_type,
                func.count(Document.id).label("doc_count"),
                func.coalesce(func.avg(Document.processing_duration_ms), 0.0).label("avg_proc"),
                func.coalesce(func.avg(Document.ocr_confidence), 0.0).label("avg_acc"),
                func.sum(
                    case(
                        (Document.status.in_(["PENDING", "PROCESSING"]), 1),
                        else_=0
                    )
                ).label("pending_count"),
            ).where(
                and_(
                    Document.company_id == self.company_id,
                    Document.deleted_at.is_(None),
                )
            ).group_by(
                Document.document_type
            ).order_by(
                func.count(Document.id).desc()
            )

            result = await self.db.execute(stmt)
            rows = result.all()

            departments: List[DepartmentBreakdown] = []
            for row in rows:
                doc_type = row[0] or "Unbekannt"
                departments.append(
                    DepartmentBreakdown(
                        department=doc_type,
                        document_count=row[1] or 0,
                        avg_processing_time_ms=round(float(row[2] or 0.0), 0),
                        accuracy=round(float(row[3] or 0.0), 3),
                        pending_count=row[4] or 0,
                    )
                )

            return departments

        except Exception as e:
            logger.error("abteilungsstatistik_fehlgeschlagen", error=str(e), company_id=str(self.company_id))
            raise

    async def get_trend(self, metric: str, days: int = 30) -> TrendResponse:
        """
        Hole Trend-Daten für eine bestimmte Metrik.

        Args:
            metric: Metrik-Name (documents, processing_time, accuracy)
            days: Anzahl Tage zurück

        Returns:
            TrendResponse mit täglichen Datenpunkten

        Raises:
            ValueError: Bei ungültiger Metrik
            Exception: Bei Datenbankfehlern
        """
        try:
            now = datetime.now(timezone.utc)
            start_date = now - timedelta(days=days)

            # Bestimme Aggregationsfunktion basierend auf Metrik
            if metric == "documents":
                # Anzahl Dokumente pro Tag
                stmt = select(
                    func.date_trunc("day", Document.created_at).label("date"),
                    func.count(Document.id).label("value"),
                ).where(
                    and_(
                        Document.company_id == self.company_id,
                        Document.created_at >= start_date,
                        Document.deleted_at.is_(None),
                    )
                ).group_by(
                    func.date_trunc("day", Document.created_at)
                ).order_by(
                    func.date_trunc("day", Document.created_at)
                )
            elif metric == "processing_time":
                # Durchschnittliche Verarbeitungszeit pro Tag
                stmt = select(
                    func.date_trunc("day", Document.created_at).label("date"),
                    func.coalesce(func.avg(Document.processing_duration_ms), 0.0).label("value"),
                ).where(
                    and_(
                        Document.company_id == self.company_id,
                        Document.created_at >= start_date,
                        Document.processing_duration_ms.isnot(None),
                        Document.deleted_at.is_(None),
                    )
                ).group_by(
                    func.date_trunc("day", Document.created_at)
                ).order_by(
                    func.date_trunc("day", Document.created_at)
                )
            elif metric == "accuracy":
                # Durchschnittliche OCR-Genauigkeit pro Tag
                stmt = select(
                    func.date_trunc("day", Document.created_at).label("date"),
                    func.coalesce(func.avg(Document.ocr_confidence), 0.0).label("value"),
                ).where(
                    and_(
                        Document.company_id == self.company_id,
                        Document.created_at >= start_date,
                        Document.ocr_confidence.isnot(None),
                        Document.deleted_at.is_(None),
                    )
                ).group_by(
                    func.date_trunc("day", Document.created_at)
                ).order_by(
                    func.date_trunc("day", Document.created_at)
                )
            else:
                raise ValueError(f"Unbekannte Metrik: {metric}")

            result = await self.db.execute(stmt)
            rows = result.all()

            # Konvertiere zu TrendDataPoints
            data_points: List[TrendDataPoint] = []
            for row in rows:
                date_obj = row[0]
                value = float(row[1] or 0.0)
                data_points.append(
                    TrendDataPoint(
                        date=date_obj.strftime("%Y-%m-%d") if date_obj else "",
                        value=round(value, 2),
                    )
                )

            return TrendResponse(
                metric=metric,
                data=data_points,
                period_days=days,
            )

        except ValueError:
            raise
        except Exception as e:
            logger.error("trend_abruf_fehlgeschlagen", error=str(e), metric=metric, company_id=str(self.company_id))
            raise


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_kpis(company_id: UUID, db: AsyncSession) -> KPIResponse:
    """
    Hole KPIs für eine Company.

    Args:
        company_id: Company ID
        db: Database session

    Returns:
        KPIResponse
    """
    service = ExecutiveDashboardService(db=db, company_id=company_id)
    return await service.get_kpis()


async def get_department_breakdown(company_id: UUID, db: AsyncSession) -> List[DepartmentBreakdown]:
    """
    Hole Abteilungsstatistiken für eine Company.

    Args:
        company_id: Company ID
        db: Database session

    Returns:
        Liste von DepartmentBreakdown
    """
    service = ExecutiveDashboardService(db=db, company_id=company_id)
    return await service.get_department_breakdown()


async def get_trend(
    company_id: UUID,
    metric: str,
    days: int,
    db: AsyncSession
) -> TrendResponse:
    """
    Hole Trend-Daten für eine Company.

    Args:
        company_id: Company ID
        metric: Metrik-Name
        days: Anzahl Tage
        db: Database session

    Returns:
        TrendResponse
    """
    service = ExecutiveDashboardService(db=db, company_id=company_id)
    return await service.get_trend(metric=metric, days=days)
