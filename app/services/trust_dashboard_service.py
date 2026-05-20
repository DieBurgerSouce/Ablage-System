# -*- coding: utf-8 -*-
"""
Trust/Security Dashboard Service.

Aggregiert Sicherheits- und Zugriffsdaten für Compliance-Dashboard:
- Zugriffsprotokolle (wer hat was gelesen)
- Export-Tracking (GDPR Art. 15)
- Anomalie-Erkennung
- Compliance-Score
- Security-Events

Feinpoliert und durchdacht - Enterprise-Grade Trust Dashboard.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Document, User
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class TrustDashboardService:
    """
    Service für Trust/Security Dashboard.

    Aggregiert Sicherheits- und Compliance-Metriken.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service."""
        self.session = session

    async def get_dashboard_snapshot(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Erstellt Snapshot des Trust Dashboards.

        Args:
            company_id: Company ID
            days: Zeitraum in Tagen

        Returns:
            Dashboard-Daten Dictionary
        """
        period_start = datetime.now(timezone.utc) - timedelta(days=days)

        # Parallel queries für Performance
        total_accesses, sensitive_accesses, export_count, anomaly_count, compliance_score = await self._gather_metrics(
            company_id, period_start
        )

        # Recent security events
        recent_events = await self._get_recent_security_events(company_id, limit=10)

        # Top accessed documents
        top_documents = await self._get_top_accessed_documents(company_id, period_start, limit=5)

        # User activity summary
        user_activity = await self._get_user_activity_summary(company_id, period_start)

        return {
            "period_days": days,
            "period_start": period_start.isoformat(),
            "period_end": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "total_accesses": total_accesses,
                "sensitive_accesses": sensitive_accesses,
                "export_count": export_count,
                "anomaly_count": anomaly_count,
                "compliance_score": compliance_score,
            },
            "recent_security_events": recent_events,
            "top_accessed_documents": top_documents,
            "user_activity_summary": user_activity,
        }

    async def _gather_metrics(
        self,
        company_id: UUID,
        period_start: datetime,
    ) -> tuple:
        """Sammelt Basis-Metriken."""
        # Total accesses
        access_query = (
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.action.in_(["document_view", "document_download", "document_export"])
                )
            )
        )
        total_accesses = (await self.session.execute(access_query)).scalar() or 0

        # Sensitive accesses (exports, admin actions)
        sensitive_query = (
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.action.in_(["document_export", "user_data_export", "admin_access"])
                )
            )
        )
        sensitive_accesses = (await self.session.execute(sensitive_query)).scalar() or 0

        # Exports
        export_query = (
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.action.like("%export%")
                )
            )
        )
        export_count = (await self.session.execute(export_query)).scalar() or 0

        # Anomalien (failed accesses, unusual patterns)
        anomaly_query = (
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.success == False  # noqa: E712
                )
            )
        )
        anomaly_count = (await self.session.execute(anomaly_query)).scalar() or 0

        # Compliance Score (0-100)
        # Basiert auf: Anzahl Verstöße, erfolgreiche Audits, etc.
        compliance_score = await self._calculate_compliance_score(
            company_id, period_start, anomaly_count, total_accesses
        )

        return total_accesses, sensitive_accesses, export_count, anomaly_count, compliance_score

    async def _calculate_compliance_score(
        self,
        company_id: UUID,
        period_start: datetime,
        anomaly_count: int,
        total_accesses: int,
    ) -> float:
        """
        Berechnet Compliance-Score (0-100).

        Faktoren:
        - Anomalie-Rate (je niedriger, desto besser)
        - Fehlerquote
        - Dokumentation (Audit-Log Vollständigkeit)
        """
        score = 100.0

        # Anomalie-Strafe
        if total_accesses > 0:
            anomaly_rate = anomaly_count / total_accesses
            score -= anomaly_rate * 30  # max -30 Punkte

        # Fehlerquote
        error_query = (
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.success == False  # noqa: E712
                )
            )
        )
        error_count = (await self.session.execute(error_query)).scalar() or 0

        if total_accesses > 0:
            error_rate = error_count / total_accesses
            score -= error_rate * 20  # max -20 Punkte

        # Clamp auf [0, 100]
        return max(0.0, min(100.0, score))

    async def _get_recent_security_events(
        self,
        company_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Hole letzte Security-Events."""
        query = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    or_(
                        AuditLog.action.in_(["login_failed", "suspicious_access", "admin_access"]),
                        AuditLog.success == False  # noqa: E712
                    )
                )
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )

        result = await self.session.execute(query)
        events = result.scalars().all()

        return [
            {
                "id": str(event.id),
                "action": event.action,
                "user_id": str(event.user_id) if event.user_id else None,
                "resource_type": event.resource_type,
                "resource_id": str(event.resource_id) if event.resource_id else None,
                "ip_address": event.ip_address,
                "success": event.success,
                "error_message": event.error_message,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]

    async def _get_top_accessed_documents(
        self,
        company_id: UUID,
        period_start: datetime,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Hole meist-zugriffene Dokumente."""
        query = (
            select(
                AuditLog.resource_id,
                func.count(AuditLog.id).label("access_count")
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.resource_type == "document",
                    AuditLog.action.in_(["document_view", "document_download"])
                )
            )
            .group_by(AuditLog.resource_id)
            .order_by(desc("access_count"))
            .limit(limit)
        )

        result = await self.session.execute(query)
        rows = result.all()

        # Hole Document-Namen
        doc_ids = [row[0] for row in rows]
        if not doc_ids:
            return []

        doc_query = select(Document).where(Document.id.in_(doc_ids))
        doc_result = await self.session.execute(doc_query)
        docs_map = {doc.id: doc for doc in doc_result.scalars().all()}

        return [
            {
                "document_id": str(row[0]),
                "access_count": row[1],
                "filename": docs_map[row[0]].filename if row[0] in docs_map else "Unbekannt",
            }
            for row in rows
        ]

    async def _get_user_activity_summary(
        self,
        company_id: UUID,
        period_start: datetime,
    ) -> Dict[str, Any]:
        """Erstellt User Activity Summary."""
        # Top 5 aktivste Benutzer
        query = (
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("action_count")
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.user_id.isnot(None)
                )
            )
            .group_by(AuditLog.user_id)
            .order_by(desc("action_count"))
            .limit(5)
        )

        result = await self.session.execute(query)
        rows = result.all()

        # Hole User-Namen
        user_ids = [row[0] for row in rows]
        if not user_ids:
            return {"top_users": []}

        user_query = select(User).where(User.id.in_(user_ids))
        user_result = await self.session.execute(user_query)
        users_map = {user.id: user for user in user_result.scalars().all()}

        return {
            "top_users": [
                {
                    "user_id": str(row[0]),
                    "username": users_map[row[0]].username if row[0] in users_map else "Unbekannt",
                    "action_count": row[1],
                }
                for row in rows
            ]
        }

    async def get_access_log(
        self,
        company_id: UUID,
        days: int = 30,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Hole Zugriffsprotokolle.

        Args:
            company_id: Company ID
            days: Zeitraum in Tagen
            limit: Maximale Anzahl
            offset: Pagination offset

        Returns:
            Liste von Zugriffen
        """
        period_start = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.action.in_(["document_view", "document_download", "document_export"])
                )
            )
            .order_by(desc(AuditLog.created_at))
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(query)
        logs = result.scalars().all()

        return [
            {
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]

    async def get_export_log(
        self,
        company_id: UUID,
        days: int = 30,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Hole Export-Logs (GDPR Art. 15).

        Args:
            company_id: Company ID
            days: Zeitraum in Tagen
            limit: Maximale Anzahl
            offset: Pagination offset

        Returns:
            Liste von Exporten
        """
        period_start = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.action.like("%export%")
                )
            )
            .order_by(desc(AuditLog.created_at))
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(query)
        logs = result.scalars().all()

        return [
            {
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "ip_address": log.ip_address,
                "metadata": log.audit_metadata or {},
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]

    async def get_anomalies(
        self,
        company_id: UUID,
        days: int = 7,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Erkenne Anomalien (ungewöhnliche Zugriffsmuster).

        Args:
            company_id: Company ID
            days: Zeitraum in Tagen
            limit: Maximale Anzahl

        Returns:
            Liste von Anomalien
        """
        period_start = datetime.now(timezone.utc) - timedelta(days=days)

        # Fehlerhafte Zugriffe
        query = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.success == False  # noqa: E712
                )
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )

        result = await self.session.execute(query)
        logs = result.scalars().all()

        anomalies = []
        for log in logs:
            # Kategorisiere Anomalie
            anomaly_type = "unknown"
            severity = "low"

            if log.action == "login_failed":
                anomaly_type = "failed_login"
                severity = "medium"
            elif "export" in log.action:
                anomaly_type = "failed_export"
                severity = "high"
            elif "admin" in log.action:
                anomaly_type = "failed_admin_action"
                severity = "critical"

            anomalies.append({
                "id": str(log.id),
                "type": anomaly_type,
                "severity": severity,
                "user_id": str(log.user_id) if log.user_id else None,
                "action": log.action,
                "error_message": log.error_message,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            })

        return anomalies


def get_trust_dashboard_service(session: AsyncSession) -> TrustDashboardService:
    """Factory function für TrustDashboardService."""
    return TrustDashboardService(session)
