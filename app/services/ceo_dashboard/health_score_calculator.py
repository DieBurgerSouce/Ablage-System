"""
Health Score Calculator

Berechnet Unternehmens-Gesundheits-Score aus mehreren Dimensionen:
- Financial (40%): Zahlungsverhalten, Liquiditaet
- Operations (25%): Verarbeitungsrate, Effizienz
- Risk (20%): Risiko-Entities, Alerts
- Compliance (15%): GDPR, Audit-Trail

Feinpoliert und durchdacht - Enterprise Health Scoring.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    InvoiceTracking,
    InvoiceStatus,
    ProcessingStatus,
    BusinessEntity,
    AuditLog,
)
from app.db.models_alert import Alert, AlertStatus, AlertSeverity
from app.services.ceo_dashboard.digital_twin_service import HealthScore

logger = structlog.get_logger(__name__)


# =============================================================================
# Gewichtungen
# =============================================================================

DIMENSION_WEIGHTS = {
    "financial": 0.40,  # Finanzielle Gesundheit
    "operations": 0.25,  # Operative Effizienz
    "risk": 0.20,  # Risikomanagement
    "compliance": 0.15,  # Compliance-Status
}


# =============================================================================
# Health Score Calculator
# =============================================================================


class HealthScoreCalculator:
    """Berechnet Unternehmens-Gesundheits-Score."""

    def __init__(self) -> None:
        """Initialisiert Calculator."""
        self.weights = DIMENSION_WEIGHTS

    async def calculate(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> HealthScore:
        """
        Berechnet Gesundheits-Score.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            HealthScore mit allen Dimensionen
        """
        logger.info("health_score.calculate", company_id=str(company_id))

        # Berechne einzelne Dimensionen
        financial = await self._calculate_financial(company_id, db)
        operations = await self._calculate_operations(company_id, db)
        risk = await self._calculate_risk(company_id, db)
        compliance = await self._calculate_compliance(company_id, db)

        # Gewichteter Gesamt-Score
        overall = (
            financial * self.weights["financial"]
            + operations * self.weights["operations"]
            + risk * self.weights["risk"]
            + compliance * self.weights["compliance"]
        )

        # Trend berechnen (Vergleich mit vor 7 Tagen)
        trend = await self._calculate_trend(company_id, overall, db)

        return HealthScore(
            overall=overall,
            financial=financial,
            operations=operations,
            risk=risk,
            compliance=compliance,
            trend=trend,
        )

    async def _calculate_financial(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> float:
        """
        Berechnet Financial Health (40%).

        Faktoren:
        - Zahlungsrate (paid/total): 50%
        - Ueberfaellige Quote: 30%
        - Durchschnittliche Zahlungsdauer: 20%

        Returns:
            Score 0-100
        """
        # Rechnungs-Statistiken
        invoices_query = select(
            func.count(InvoiceTracking.id).label("total"),
            func.count(InvoiceTracking.id).filter(
                InvoiceTracking.status == InvoiceStatus.PAID
            ).label("paid"),
            func.count(InvoiceTracking.id).filter(
                InvoiceTracking.status == InvoiceStatus.OVERDUE
            ).label("overdue"),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        result = await db.execute(invoices_query)
        row = result.first()

        if not row or row.total == 0:
            return 100.0  # Keine Rechnungen = kein Risiko

        total = row.total
        paid = row.paid
        overdue = row.overdue

        # 1. Zahlungsrate (50%)
        payment_rate = paid / total if total > 0 else 0
        payment_score = payment_rate * 100

        # 2. Ueberfaellige Quote (30%)
        overdue_rate = overdue / total if total > 0 else 0
        # Invers: weniger ueberfaellig = hoeher Score
        overdue_score = max(0, (1 - overdue_rate * 2)) * 100  # 50% overdue = 0 Score

        # 3. Durchschnittliche Zahlungsdauer (20%)
        # Query fuer durchschnittliche Zahlungsdauer (in Tagen)
        avg_payment_query = select(
            func.avg(
                func.extract(
                    'epoch',
                    InvoiceTracking.paid_at - InvoiceTracking.invoice_date
                ) / 86400  # Sekunden zu Tagen
            )
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status == InvoiceStatus.PAID,
                InvoiceTracking.paid_at.is_not(None),
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        avg_result = await db.execute(avg_payment_query)
        avg_days = avg_result.scalar() or 30.0

        # Zahlungsdauer-Score: 0-30 Tage = 100, >60 Tage = 0
        duration_score = max(0, min(100, (60 - avg_days) / 60 * 100))

        # Gewichteter Financial Score
        financial = (
            payment_score * 0.50
            + overdue_score * 0.30
            + duration_score * 0.20
        )

        logger.debug(
            "health_score.financial",
            company_id=str(company_id),
            total=total,
            paid=paid,
            overdue=overdue,
            payment_rate=payment_rate,
            avg_days=avg_days,
            score=financial,
        )

        return financial

    async def _calculate_operations(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> float:
        """
        Berechnet Operational Efficiency (25%).

        Faktoren:
        - Auto-Process Rate: 50%
        - Durchschnittliche Verarbeitungszeit: 30%
        - Fehlerrate: 20%

        Returns:
            Score 0-100
        """
        now = datetime.now(timezone.utc)
        last_30_days = now - timedelta(days=30)

        # Dokument-Statistiken (letzte 30 Tage)
        docs_query = select(
            func.count(Document.id).label("total"),
            func.count(Document.id).filter(
                Document.status == ProcessingStatus.COMPLETED
            ).label("completed"),
            func.count(Document.id).filter(
                Document.status == ProcessingStatus.FAILED
            ).label("failed"),
            func.avg(Document.processing_duration_ms).label("avg_duration"),
        ).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= last_30_days,
                Document.deleted_at.is_(None),
            )
        )
        result = await db.execute(docs_query)
        row = result.first()

        if not row or row.total == 0:
            return 100.0  # Keine Dokumente = kein Problem

        total = row.total
        completed = row.completed
        failed = row.failed
        avg_duration_ms = row.avg_duration or 5000

        # 1. Auto-Process Rate (50%)
        auto_rate = completed / total if total > 0 else 0
        auto_score = auto_rate * 100

        # 2. Durchschnittliche Verarbeitungszeit (30%)
        # 0-2s = 100, >10s = 0
        avg_duration_s = avg_duration_ms / 1000
        duration_score = max(0, min(100, (10 - avg_duration_s) / 10 * 100))

        # 3. Fehlerrate (20%)
        error_rate = failed / total if total > 0 else 0
        # Invers: weniger Fehler = hoeher Score
        error_score = max(0, (1 - error_rate * 10)) * 100  # 10% Fehler = 0 Score

        # Gewichteter Operations Score
        operations = (
            auto_score * 0.50
            + duration_score * 0.30
            + error_score * 0.20
        )

        logger.debug(
            "health_score.operations",
            company_id=str(company_id),
            total=total,
            completed=completed,
            failed=failed,
            auto_rate=auto_rate,
            avg_duration_s=avg_duration_s,
            score=operations,
        )

        return operations

    async def _calculate_risk(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> float:
        """
        Berechnet Risk Score (20%).

        Faktoren:
        - High-Risk Entities: 50%
        - Critical Alerts: 30%
        - Open Alerts: 20%

        Returns:
            Score 0-100
        """
        # 1. High-Risk Entities (Risk Score > 75)
        high_risk_query = select(func.count(BusinessEntity.id)).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.risk_score > 75,
            )
        )
        high_risk_result = await db.execute(high_risk_query)
        high_risk_count = high_risk_result.scalar() or 0

        total_entities_query = select(func.count(BusinessEntity.id)).where(
            BusinessEntity.company_id == company_id
        )
        total_entities_result = await db.execute(total_entities_query)
        total_entities = total_entities_result.scalar() or 0

        if total_entities > 0:
            high_risk_rate = high_risk_count / total_entities
            # Invers: weniger high-risk = hoeher Score
            high_risk_score = max(0, (1 - high_risk_rate * 5)) * 100  # 20% high-risk = 0
        else:
            high_risk_score = 100.0

        # 2. Critical Alerts
        critical_alerts_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.severity == AlertSeverity.CRITICAL,
                Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
            )
        )
        critical_result = await db.execute(critical_alerts_query)
        critical_count = critical_result.scalar() or 0

        # 0 Critical = 100, 5+ Critical = 0
        critical_score = max(0, min(100, (5 - critical_count) / 5 * 100))

        # 3. Open Alerts (alle Schweregrade)
        open_alerts_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS]),
            )
        )
        open_result = await db.execute(open_alerts_query)
        open_count = open_result.scalar() or 0

        # 0 Open = 100, 20+ Open = 0
        open_score = max(0, min(100, (20 - open_count) / 20 * 100))

        # Gewichteter Risk Score
        risk = (
            high_risk_score * 0.50
            + critical_score * 0.30
            + open_score * 0.20
        )

        logger.debug(
            "health_score.risk",
            company_id=str(company_id),
            high_risk_count=high_risk_count,
            total_entities=total_entities,
            critical_count=critical_count,
            open_count=open_count,
            score=risk,
        )

        return risk

    async def _calculate_compliance(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> float:
        """
        Berechnet Compliance Score (15%).

        Faktoren:
        - Audit Trail Completeness: 60%
        - Compliance Alerts: 40%

        Returns:
            Score 0-100
        """
        now = datetime.now(timezone.utc)
        last_30_days = now - timedelta(days=30)

        # 1. Audit Trail Completeness
        # Pruefe ob alle wichtigen Aktionen geloggt sind
        docs_count_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= last_30_days,
                Document.deleted_at.is_(None),
            )
        )
        docs_result = await db.execute(docs_count_query)
        docs_count = docs_result.scalar() or 0

        # Erwarte mindestens 3 Audit-Log-Eintraege pro Dokument (upload, process, update)
        expected_logs = docs_count * 3

        audit_logs_query = select(func.count(AuditLog.id)).where(
            and_(
                AuditLog.company_id == company_id,
                AuditLog.created_at >= last_30_days,
            )
        )
        audit_result = await db.execute(audit_logs_query)
        actual_logs = audit_result.scalar() or 0

        if expected_logs > 0:
            audit_completeness = min(1.0, actual_logs / expected_logs)
            audit_score = audit_completeness * 100
        else:
            audit_score = 100.0

        # 2. Compliance Alerts
        compliance_alerts_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.category == "compliance",
                Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
            )
        )
        compliance_result = await db.execute(compliance_alerts_query)
        compliance_count = compliance_result.scalar() or 0

        # 0 Compliance Alerts = 100, 5+ = 0
        compliance_score = max(0, min(100, (5 - compliance_count) / 5 * 100))

        # Gewichteter Compliance Score
        compliance = (
            audit_score * 0.60
            + compliance_score * 0.40
        )

        logger.debug(
            "health_score.compliance",
            company_id=str(company_id),
            docs_count=docs_count,
            expected_logs=expected_logs,
            actual_logs=actual_logs,
            compliance_count=compliance_count,
            score=compliance,
        )

        return compliance

    async def _calculate_trend(
        self,
        company_id: UUID,
        current_score: float,
        db: AsyncSession,
    ) -> str:
        """
        Berechnet Trend (improving, stable, declining).

        Vergleicht aktuellen Score mit Score von vor 7 Tagen.

        Returns:
            "improving", "stable", "declining"
        """
        # Fuer echte Implementierung: Score von vor 7 Tagen aus Cache/DB holen
        # Hier: Vereinfachte Logik basierend auf aktuellen Werten

        # Hole historischen Score aus AppConfig (vor 7 Tagen)
        historical_score = await self._get_historical_score(company_id, days_ago=7)

        if historical_score is not None:
            delta = current_score - historical_score
            if delta > 5:
                return "improving"
            elif delta < -5:
                return "declining"
            else:
                return "stable"

        # Fallback wenn keine Historie: basierend auf aktuellem Score
        if current_score >= 80:
            return "stable"
        elif current_score >= 60:
            return "improving"
        else:
            return "declining"

    async def _get_historical_score(
        self,
        company_id: UUID,
        days_ago: int = 7,
    ) -> Optional[float]:
        """Holt historischen Health Score aus AppConfig Cache."""
        from app.db.models import AppConfig
        from datetime import timedelta

        cache_key = f"health_score_history:{company_id}"
        target_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        try:
            result = await self.db.execute(
                select(AppConfig).where(AppConfig.key == cache_key)
            )
            config = result.scalar_one_or_none()

            if config and config.value and isinstance(config.value, dict):
                # History format: {"2026-01-25": 85.5, "2026-01-24": 82.0, ...}
                return config.value.get(target_date)

            return None
        except Exception:
            return None

    async def save_current_score(
        self,
        company_id: UUID,
        score: float,
    ) -> bool:
        """Speichert aktuellen Score fuer Trend-Berechnung."""
        from app.db.models import AppConfig

        cache_key = f"health_score_history:{company_id}"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            result = await self.db.execute(
                select(AppConfig).where(AppConfig.key == cache_key)
            )
            config = result.scalar_one_or_none()

            if config:
                history = config.value if isinstance(config.value, dict) else {}
                history[today] = score
                # Behalte nur letzte 30 Tage
                sorted_dates = sorted(history.keys(), reverse=True)[:30]
                config.value = {d: history[d] for d in sorted_dates}
            else:
                config = AppConfig(key=cache_key, value={today: score})
                self.db.add(config)

            await self.db.commit()
            return True
        except Exception:
            return False
