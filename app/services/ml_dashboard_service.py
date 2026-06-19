# -*- coding: utf-8 -*-
"""
ML Progress Dashboard Service.

Zeigt OCR-Self-Learning Fortschritt und Metriken:
- Erkennungsrate über Zeit (Learning Curve)
- Fehlertyp-Statistiken
- Korrektur-Impact
- Modell-Performance pro Dokumenttyp
- Auto-Kategorisierung Genauigkeit

Feinpoliert und durchdacht - Enterprise-Grade ML Dashboard.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, desc, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentType
from app.db.models_ocr_feedback import OCRCorrectionFeedback
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


def _as_naive_utc(dt: datetime) -> datetime:
    """F-31: Gibt einen naiven UTC-datetime zurueck.

    OCRCorrectionFeedback.created_at ist eine `TIMESTAMP WITHOUT TIME ZONE`-
    Spalte (naive UTC). Der Vergleich mit einem tz-aware `period_start`
    loest in asyncpg einen DataError aus (offset-naive vs offset-aware).
    Diese Helferfunktion normalisiert auf naives UTC fuer genau diese Vergleiche.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class MLDashboardService:
    """
    Service für ML Progress Dashboard.

    Zeigt OCR-Self-Learning Fortschritt und Metriken.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service."""
        self.session = session

    async def get_dashboard_data(
        self,
        company_id: UUID,
        months: int = 6,
    ) -> Dict[str, Any]:
        """
        Erstellt ML Dashboard Snapshot.

        Args:
            company_id: Company ID
            months: Zeitraum in Monaten

        Returns:
            Dashboard-Daten Dictionary
        """
        period_start = datetime.now(timezone.utc) - timedelta(days=months * 30)

        # Learning Curve
        learning_curve = await self.get_learning_curve(company_id, months)

        # Error Statistics
        error_stats = await self.get_error_statistics(company_id)

        # Correction Impact
        correction_impact = await self.get_correction_impact(company_id, period_start)

        # Model Performance per Document Type
        model_performance = await self.get_model_performance_by_type(company_id)

        # Auto-Categorization Accuracy
        categorization_accuracy = await self.get_categorization_accuracy(company_id, period_start)

        return {
            "period_months": months,
            "period_start": period_start.isoformat(),
            "period_end": datetime.now(timezone.utc).isoformat(),
            "learning_curve": learning_curve,
            "error_statistics": error_stats,
            "correction_impact": correction_impact,
            "model_performance_by_type": model_performance,
            "categorization_accuracy": categorization_accuracy,
        }

    async def get_learning_curve(
        self,
        company_id: UUID,
        months: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Erstellt Learning Curve (Erkennungsrate über Zeit).

        Args:
            company_id: Company ID
            months: Zeitraum in Monaten

        Returns:
            Liste von Datenpunkten (Monat, Genauigkeit)
        """
        period_start = datetime.now(timezone.utc) - timedelta(days=months * 30)

        # Aggregiere Korrekturen pro Monat
        query = (
            select(
                func.date_trunc(literal_column("'month'"), OCRCorrectionFeedback.created_at).label('month'),
                func.count(OCRCorrectionFeedback.id).label('correction_count'),
                func.avg(OCRCorrectionFeedback.confidence_before).label('avg_conf_before'),
                func.avg(OCRCorrectionFeedback.confidence_after).label('avg_conf_after')
            )
            .join(Document, OCRCorrectionFeedback.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    OCRCorrectionFeedback.created_at >= _as_naive_utc(period_start)
                )
            )
            .group_by(func.date_trunc(literal_column("'month'"), OCRCorrectionFeedback.created_at))
            .order_by(func.date_trunc(literal_column("'month'"), OCRCorrectionFeedback.created_at))
        )

        result = await self.session.execute(query)
        rows = result.all()

        # Berechne Gesamt-Dokumente pro Monat
        doc_query = (
            select(
                func.date_trunc(literal_column("'month'"), Document.created_at).label('month'),
                func.count(Document.id).label('doc_count')
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= period_start,
                    Document.status == "completed"
                )
            )
            .group_by(func.date_trunc(literal_column("'month'"), Document.created_at))
        )

        doc_result = await self.session.execute(doc_query)
        doc_counts = {row[0]: row[1] for row in doc_result.all()}

        # Berechne Erkennungsrate (inverse Korrekturrate)
        learning_curve = []
        for row in rows:
            month = row[0]
            correction_count = row[1]
            avg_conf_before = float(row[2]) if row[2] else 0.0
            avg_conf_after = float(row[3]) if row[3] else 0.0

            doc_count = doc_counts.get(month, 0)
            recognition_rate = 1.0 - (correction_count / doc_count) if doc_count > 0 else 1.0

            learning_curve.append({
                "month": month.isoformat() if month else None,
                "recognition_rate": round(recognition_rate * 100, 2),
                "correction_count": correction_count,
                "avg_confidence_before": round(avg_conf_before, 4),
                "avg_confidence_after": round(avg_conf_after, 4),
                "improvement": round((avg_conf_after - avg_conf_before) * 100, 2),
            })

        return learning_curve

    async def get_error_statistics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Erstellt Fehlertyp-Statistiken.

        Args:
            company_id: Company ID

        Returns:
            Fehler-Statistiken Dictionary
        """
        # Aggregiere nach Fehler-Kategorie
        query = (
            select(
                OCRCorrectionFeedback.error_category,
                func.count(OCRCorrectionFeedback.id).label('count')
            )
            .join(Document, OCRCorrectionFeedback.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    OCRCorrectionFeedback.error_category.isnot(None)
                )
            )
            .group_by(OCRCorrectionFeedback.error_category)
            .order_by(desc('count'))
        )

        result = await self.session.execute(query)
        rows = result.all()

        error_types = {}
        total = 0
        for row in rows:
            category = row[0]
            count = row[1]
            error_types[category] = count
            total += count

        # Berechne Prozentsätze
        error_percentages = {
            cat: round((count / total) * 100, 2) if total > 0 else 0.0
            for cat, count in error_types.items()
        }

        # Deutsche Beschreibungen
        category_descriptions = {
            "umlaut": "Umlaut-Fehler (ä, ö, ü)",
            "digit_swap": "Ziffern-Verwechslung",
            "spacing": "Leerzeichen-Probleme",
            "case": "Groß-/Kleinschreibung",
            "ocr_noise": "OCR-Rauschen",
            "unknown": "Unbekannt",
        }

        return {
            "total_corrections": total,
            "error_types": [
                {
                    "category": cat,
                    "description": category_descriptions.get(cat, cat),
                    "count": count,
                    "percentage": error_percentages[cat],
                }
                for cat, count in error_types.items()
            ],
        }

    async def get_correction_impact(
        self,
        company_id: UUID,
        period_start: datetime,
    ) -> Dict[str, Any]:
        """
        Berechnet Impact der Korrekturen auf Genauigkeit.

        Args:
            company_id: Company ID
            period_start: Start-Zeitpunkt

        Returns:
            Correction Impact Dictionary
        """
        # Zähle Korrekturen
        count_query = (
            select(func.count(OCRCorrectionFeedback.id))
            .join(Document, OCRCorrectionFeedback.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    OCRCorrectionFeedback.created_at >= _as_naive_utc(period_start)
                )
            )
        )
        correction_count = (await self.session.execute(count_query)).scalar() or 0

        # Durchschnittliche Confidence-Verbesserung
        avg_query = (
            select(
                func.avg(OCRCorrectionFeedback.confidence_before),
                func.avg(OCRCorrectionFeedback.confidence_after)
            )
            .join(Document, OCRCorrectionFeedback.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    OCRCorrectionFeedback.created_at >= _as_naive_utc(period_start)
                )
            )
        )
        avg_result = await self.session.execute(avg_query)
        avg_row = avg_result.first()

        avg_conf_before = float(avg_row[0]) if avg_row and avg_row[0] else 0.0
        avg_conf_after = float(avg_row[1]) if avg_row and avg_row[1] else 0.0

        # Accuracy Improvement
        accuracy_improvement = (avg_conf_after - avg_conf_before) * 100

        return {
            "correction_count": correction_count,
            "avg_confidence_before": round(avg_conf_before, 4),
            "avg_confidence_after": round(avg_conf_after, 4),
            "accuracy_improvement_percent": round(accuracy_improvement, 2),
            "summary": f"{correction_count} Korrekturen, {accuracy_improvement:+.1f}% Genauigkeit",
        }

    async def get_model_performance_by_type(
        self,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Liefert Modell-Performance pro Dokumenttyp.

        Args:
            company_id: Company ID

        Returns:
            Liste von Performance-Metriken pro Dokumenttyp
        """
        # Aggregiere nach Dokumenttyp
        query = (
            select(
                Document.document_type,
                func.count(Document.id).label('doc_count'),
                func.count(OCRCorrectionFeedback.id).label('correction_count'),
                func.avg(Document.ocr_confidence).label('avg_confidence')
            )
            .outerjoin(OCRCorrectionFeedback, Document.id == OCRCorrectionFeedback.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.status == "completed",
                    Document.document_type.isnot(None)
                )
            )
            .group_by(Document.document_type)
            .order_by(desc('doc_count'))
        )

        result = await self.session.execute(query)
        rows = result.all()

        performance_list = []
        for row in rows:
            doc_type = row[0]
            doc_count = row[1]
            correction_count = row[2] or 0
            avg_conf = float(row[3]) if row[3] else 0.0

            # Accuracy Rate (inverse correction rate)
            accuracy_rate = 1.0 - (correction_count / doc_count) if doc_count > 0 else 1.0

            performance_list.append({
                "document_type": doc_type,
                "document_count": doc_count,
                "correction_count": correction_count,
                "avg_confidence": round(avg_conf, 4),
                "accuracy_rate": round(accuracy_rate * 100, 2),
            })

        return performance_list

    async def get_categorization_accuracy(
        self,
        company_id: UUID,
        period_start: datetime,
    ) -> Dict[str, Any]:
        """
        Berechnet Auto-Kategorisierung Genauigkeit.

        Args:
            company_id: Company ID
            period_start: Start-Zeitpunkt

        Returns:
            Categorization Accuracy Dictionary
        """
        # Gesamt-Dokumente
        total_query = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= period_start,
                    Document.status == "completed"
                )
            )
        )
        total_docs = (await self.session.execute(total_query)).scalar() or 0

        # Automatisch kategorisierte Dokumente
        auto_query = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= period_start,
                    Document.status == "completed",
                    Document.document_type.notin_([DocumentType.UNKNOWN, DocumentType.OTHER])
                )
            )
        )
        auto_categorized = (await self.session.execute(auto_query)).scalar() or 0

        # Accuracy Rate
        accuracy_rate = (auto_categorized / total_docs) * 100 if total_docs > 0 else 0.0

        # Trend (Vergleich mit vorherigem Zeitraum)
        prev_period_start = period_start - (datetime.now(timezone.utc) - period_start)
        prev_total_query = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= prev_period_start,
                    Document.created_at < period_start,
                    Document.status == "completed"
                )
            )
        )
        prev_total = (await self.session.execute(prev_total_query)).scalar() or 0

        prev_auto_query = (
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= prev_period_start,
                    Document.created_at < period_start,
                    Document.status == "completed",
                    Document.document_type.notin_([DocumentType.UNKNOWN, DocumentType.OTHER])
                )
            )
        )
        prev_auto = (await self.session.execute(prev_auto_query)).scalar() or 0

        prev_accuracy = (prev_auto / prev_total) * 100 if prev_total > 0 else 0.0
        trend = accuracy_rate - prev_accuracy

        return {
            "total_documents": total_docs,
            "auto_categorized": auto_categorized,
            "accuracy_rate_percent": round(accuracy_rate, 2),
            "trend_percent": round(trend, 2),
            "trend_direction": "up" if trend > 0 else "down" if trend < 0 else "stable",
        }


def get_ml_dashboard_service(session: AsyncSession) -> MLDashboardService:
    """Factory function für MLDashboardService."""
    return MLDashboardService(session)
