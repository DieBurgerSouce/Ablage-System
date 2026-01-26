# -*- coding: utf-8 -*-
"""
Alert Center Service for Ablage-System.

Zentrales Alert-Management mit:
- Alert-Erstellung aus verschiedenen Quellen
- Kategorisierung und Priorisierung
- Acknowledge/Dismiss/Escalate Workflow
- Email-Digest-Versand
- Statistiken und Dashboards

Feinpoliert und durchdacht - Enterprise-grade Alert Management.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, desc, asc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models_alert import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertStatus,
    AlertRule,
    AlertDigestSubscription,
)
from app.services.notification_service import (
    NotificationService,
    get_notification_service,
    NotificationPriority,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Alert Code Definitions
# =============================================================================

class AlertCodes:
    """Standardized alert codes for the system."""

    # Fraud Detection
    FRAUD_DUPLICATE_INVOICE = "FRAUD_001"
    FRAUD_PRICE_ANOMALY = "FRAUD_002"
    FRAUD_PHANTOM_SUPPLIER = "FRAUD_003"
    FRAUD_INTERNAL_PATTERN = "FRAUD_004"

    # Risk Intelligence
    RISK_HIGH_SCORE = "RISK_001"
    RISK_PAYMENT_DELAY = "RISK_002"
    RISK_INSOLVENCY_WARNING = "RISK_003"
    RISK_CREDIT_LIMIT = "RISK_004"

    # Compliance
    COMPLIANCE_GDPR_VIOLATION = "COMP_001"
    COMPLIANCE_GOBD_VIOLATION = "COMP_002"
    COMPLIANCE_RETENTION_EXPIRY = "COMP_003"
    COMPLIANCE_AUDIT_REQUIRED = "COMP_004"
    COMPLIANCE_DLP_VIOLATION = "COMP_005"

    # Deadlines
    DEADLINE_SKONTO_EXPIRING = "DEAD_001"
    DEADLINE_INVOICE_OVERDUE = "DEAD_002"
    DEADLINE_CONTRACT_EXPIRY = "DEAD_003"
    DEADLINE_APPROVAL_PENDING = "DEAD_004"

    # System
    SYSTEM_GPU_MEMORY = "SYS_001"
    SYSTEM_DISK_SPACE = "SYS_002"
    SYSTEM_OCR_FAILURE_RATE = "SYS_003"
    SYSTEM_BACKUP_FAILED = "SYS_004"
    SYSTEM_QUEUE_BACKLOG = "SYS_005"

    # Security
    SECURITY_LOGIN_FAILED = "SEC_001"
    SECURITY_SUSPICIOUS_ACCESS = "SEC_002"
    SECURITY_API_ABUSE = "SEC_003"
    SECURITY_MFA_DISABLED = "SEC_004"

    # Quality
    QUALITY_LOW_OCR_CONFIDENCE = "QUAL_001"
    QUALITY_UMLAUT_ISSUES = "QUAL_002"
    QUALITY_EXTRACTION_FAILED = "QUAL_003"

    # Workflow
    WORKFLOW_APPROVAL_ESCALATED = "WORK_001"
    WORKFLOW_DELEGATION_EXPIRING = "WORK_002"
    WORKFLOW_STEP_FAILED = "WORK_003"


# =============================================================================
# Alert Templates (German)
# =============================================================================

ALERT_TEMPLATES: Dict[str, Dict[str, str]] = {
    AlertCodes.FRAUD_DUPLICATE_INVOICE: {
        "title": "Moegliche Duplikat-Rechnung erkannt",
        "message": "Die Rechnung {invoice_number} von {vendor_name} ist moeglicherweise ein Duplikat.",
    },
    AlertCodes.FRAUD_PRICE_ANOMALY: {
        "title": "Preisanomalie erkannt",
        "message": "Der Preis fuer {item} weicht um {deviation}% vom historischen Durchschnitt ab.",
    },
    AlertCodes.RISK_HIGH_SCORE: {
        "title": "Hoher Risiko-Score",
        "message": "Der Geschaeftspartner hat einen Risiko-Score von {score}/100 erreicht.",
    },
    AlertCodes.DEADLINE_SKONTO_EXPIRING: {
        "title": "Skonto-Frist laeuft ab",
        "message": "Die Skonto-Frist fuer Rechnung {invoice_number} laeuft in {days} Tagen ab. Ersparnis: {savings} EUR.",
    },
    AlertCodes.DEADLINE_INVOICE_OVERDUE: {
        "title": "Rechnung ueberfaellig",
        "message": "Die Rechnung {invoice_number} ist seit {days} Tagen ueberfaellig. Betrag: {amount} EUR.",
    },
    AlertCodes.SYSTEM_GPU_MEMORY: {
        "title": "GPU-Speicher kritisch",
        "message": "GPU-Speicherauslastung bei {usage}%. Empfehlung: OCR-Queue reduzieren.",
    },
    AlertCodes.QUALITY_LOW_OCR_CONFIDENCE: {
        "title": "Niedrige OCR-Qualitaet",
        "message": "Das Dokument wurde mit nur {confidence}% Konfidenz erkannt. Manuelle Pruefung empfohlen.",
    },
    AlertCodes.COMPLIANCE_DLP_VIOLATION: {
        "title": "DLP-Richtlinien-Verletzung",
        "message": "Ein Zugriff wurde aufgrund von DLP-Richtlinien blockiert: {policy_name}.",
    },
}


# =============================================================================
# Alert Center Service
# =============================================================================

class AlertCenterService:
    """
    Central service for alert management.

    Handles creation, retrieval, acknowledgment, resolution,
    and escalation of alerts across all categories.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize alert center service."""
        self.session = session
        self._notification_service: Optional[NotificationService] = None

    @property
    def notification_service(self) -> NotificationService:
        """Lazy-load notification service."""
        if self._notification_service is None:
            self._notification_service = get_notification_service()
        return self._notification_service

    # =========================================================================
    # Alert Creation
    # =========================================================================

    async def create_alert(
        self,
        company_id: UUID,
        alert_code: str,
        category: AlertCategory,
        severity: AlertSeverity,
        title: str,
        message: str,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        available_actions: Optional[List[str]] = None,
        assigned_to_id: Optional[UUID] = None,
        auto_dismiss_hours: Optional[int] = None,
        recurrence_key: Optional[str] = None,
        send_email: bool = False,
        email_recipient: Optional[str] = None,
    ) -> Alert:
        """
        Create a new alert.

        Args:
            company_id: Company this alert belongs to
            alert_code: Standardized alert code (e.g., FRAUD_001)
            category: Alert category
            severity: Alert severity level
            title: Alert title
            message: Alert message/description
            source_type: Source system (e.g., "fraud_detection")
            source_id: Source identifier (e.g., document ID)
            document_id: Related document ID
            entity_id: Related business entity ID
            metadata: Additional metadata
            context: UI context data
            available_actions: List of available actions
            assigned_to_id: User to assign alert to
            auto_dismiss_hours: Hours until auto-dismiss (None = never)
            recurrence_key: Key for deduplication of recurring alerts
            send_email: Whether to send email notification
            email_recipient: Email address for notification

        Returns:
            Created Alert instance
        """
        # Check for recurrence deduplication
        if recurrence_key:
            existing = await self._find_active_by_recurrence_key(
                company_id, recurrence_key
            )
            if existing:
                logger.debug(
                    "alert_deduplicated",
                    recurrence_key=recurrence_key,
                    existing_id=str(existing.id),
                )
                return existing

        # Calculate auto-dismiss time
        auto_dismiss_at = None
        if auto_dismiss_hours:
            auto_dismiss_at = datetime.now(timezone.utc) + timedelta(
                hours=auto_dismiss_hours
            )

        # Create alert
        alert = Alert(
            company_id=company_id,
            alert_code=alert_code,
            category=category.value if isinstance(category, AlertCategory) else category,
            severity=severity.value if isinstance(severity, AlertSeverity) else severity,
            title=title,
            message=message,
            source_type=source_type,
            source_id=source_id,
            document_id=document_id,
            entity_id=entity_id,
            metadata=metadata or {},
            context=context or {},
            available_actions=available_actions or ["acknowledge", "dismiss"],
            assigned_to_id=assigned_to_id,
            auto_dismiss_at=auto_dismiss_at,
            recurrence_key=recurrence_key,
            is_recurring=recurrence_key is not None,
        )

        self.session.add(alert)
        await self.session.flush()

        logger.info(
            "alert_created",
            alert_id=str(alert.id),
            alert_code=alert_code,
            category=category,
            severity=severity,
        )

        # Send email notification if requested
        if send_email and email_recipient:
            await self._send_alert_email(alert, email_recipient)

        return alert

    async def create_alert_from_template(
        self,
        company_id: UUID,
        alert_code: str,
        context_data: Dict[str, Any],
        **kwargs: Any,
    ) -> Alert:
        """
        Create alert using a predefined template.

        Args:
            company_id: Company ID
            alert_code: Alert code (must have template)
            context_data: Data for template rendering
            **kwargs: Additional alert creation parameters

        Returns:
            Created Alert instance
        """
        template = ALERT_TEMPLATES.get(alert_code)
        if not template:
            raise ValueError(f"Keine Vorlage fuer Alert-Code: {alert_code}")

        # Render title and message
        title = template["title"].format(**context_data)
        message = template["message"].format(**context_data)

        # Determine category and severity from code prefix
        category, severity = self._parse_alert_code(alert_code)

        return await self.create_alert(
            company_id=company_id,
            alert_code=alert_code,
            category=category,
            severity=severity,
            title=title,
            message=message,
            context=context_data,
            **kwargs,
        )

    def _parse_alert_code(
        self, code: str
    ) -> Tuple[AlertCategory, AlertSeverity]:
        """Parse category and default severity from alert code."""
        prefix = code.split("_")[0]

        category_map = {
            "FRAUD": AlertCategory.FRAUD,
            "RISK": AlertCategory.RISK,
            "COMP": AlertCategory.COMPLIANCE,
            "DEAD": AlertCategory.DEADLINE,
            "SYS": AlertCategory.SYSTEM,
            "SEC": AlertCategory.SECURITY,
            "QUAL": AlertCategory.QUALITY,
            "WORK": AlertCategory.WORKFLOW,
        }

        # Default severity based on category
        severity_map = {
            "FRAUD": AlertSeverity.HIGH,
            "RISK": AlertSeverity.MEDIUM,
            "COMP": AlertSeverity.HIGH,
            "DEAD": AlertSeverity.MEDIUM,
            "SYS": AlertSeverity.MEDIUM,
            "SEC": AlertSeverity.HIGH,
            "QUAL": AlertSeverity.LOW,
            "WORK": AlertSeverity.MEDIUM,
        }

        category = category_map.get(prefix, AlertCategory.SYSTEM)
        severity = severity_map.get(prefix, AlertSeverity.MEDIUM)

        return category, severity

    # =========================================================================
    # Alert Retrieval
    # =========================================================================

    async def get_alert(
        self,
        alert_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[Alert]:
        """Get single alert by ID."""
        stmt = select(Alert).where(Alert.id == alert_id)

        if company_id:
            stmt = stmt.where(Alert.company_id == company_id)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_alerts(
        self,
        company_id: UUID,
        category: Optional[AlertCategory] = None,
        severity: Optional[AlertSeverity] = None,
        status: Optional[AlertStatus] = None,
        assigned_to_id: Optional[UUID] = None,
        source_type: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> Tuple[List[Alert], int]:
        """
        List alerts with filtering and pagination.

        Returns:
            Tuple of (alerts, total_count)
        """
        # Base query
        stmt = select(Alert).where(Alert.company_id == company_id)

        # Apply filters
        if category:
            cat_value = category.value if isinstance(category, AlertCategory) else category
            stmt = stmt.where(Alert.category == cat_value)

        if severity:
            sev_value = severity.value if isinstance(severity, AlertSeverity) else severity
            stmt = stmt.where(Alert.severity == sev_value)

        if status:
            status_value = status.value if isinstance(status, AlertStatus) else status
            stmt = stmt.where(Alert.status == status_value)

        if assigned_to_id:
            stmt = stmt.where(Alert.assigned_to_id == assigned_to_id)

        if source_type:
            stmt = stmt.where(Alert.source_type == source_type)

        if unread_only:
            stmt = stmt.where(Alert.status == AlertStatus.NEW.value)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.execute(count_stmt)
        total_count = total.scalar() or 0

        # Apply ordering
        order_column = getattr(Alert, order_by, Alert.created_at)
        if order_desc:
            stmt = stmt.order_by(desc(order_column))
        else:
            stmt = stmt.order_by(asc(order_column))

        # Apply pagination
        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        alerts = list(result.scalars().all())

        return alerts, total_count

    async def get_alert_counts(
        self,
        company_id: UUID,
        group_by: str = "category",
    ) -> Dict[str, int]:
        """
        Get alert counts grouped by category, severity, or status.

        Args:
            company_id: Company ID
            group_by: Field to group by (category, severity, status)

        Returns:
            Dictionary of group -> count
        """
        group_column = getattr(Alert, group_by, Alert.category)

        stmt = (
            select(group_column, func.count(Alert.id))
            .where(Alert.company_id == company_id)
            .where(Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]))
            .group_by(group_column)
        )

        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_dashboard_stats(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Get comprehensive alert statistics for dashboard.

        Returns:
            Dashboard statistics dictionary
        """
        # Count by status
        status_counts = await self.get_alert_counts(company_id, "status")

        # Count by category (only active alerts)
        stmt_category = (
            select(Alert.category, func.count(Alert.id))
            .where(Alert.company_id == company_id)
            .where(Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]))
            .group_by(Alert.category)
        )
        result = await self.session.execute(stmt_category)
        category_counts = {row[0]: row[1] for row in result.all()}

        # Count by severity (only active alerts)
        stmt_severity = (
            select(Alert.severity, func.count(Alert.id))
            .where(Alert.company_id == company_id)
            .where(Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]))
            .group_by(Alert.severity)
        )
        result = await self.session.execute(stmt_severity)
        severity_counts = {row[0]: row[1] for row in result.all()}

        # Critical alerts count
        stmt_critical = (
            select(func.count(Alert.id))
            .where(Alert.company_id == company_id)
            .where(Alert.severity == AlertSeverity.CRITICAL.value)
            .where(Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]))
        )
        result = await self.session.execute(stmt_critical)
        critical_count = result.scalar() or 0

        # Recent alerts (last 24h)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        stmt_recent = (
            select(func.count(Alert.id))
            .where(Alert.company_id == company_id)
            .where(Alert.created_at >= yesterday)
        )
        result = await self.session.execute(stmt_recent)
        recent_count = result.scalar() or 0

        return {
            "total_active": sum(
                status_counts.get(s, 0)
                for s in [AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value, AlertStatus.IN_PROGRESS.value]
            ),
            "new_count": status_counts.get(AlertStatus.NEW.value, 0),
            "acknowledged_count": status_counts.get(AlertStatus.ACKNOWLEDGED.value, 0),
            "in_progress_count": status_counts.get(AlertStatus.IN_PROGRESS.value, 0),
            "resolved_count": status_counts.get(AlertStatus.RESOLVED.value, 0),
            "critical_count": critical_count,
            "recent_24h_count": recent_count,
            "by_category": category_counts,
            "by_severity": severity_counts,
            "by_status": status_counts,
        }

    # =========================================================================
    # Alert Actions
    # =========================================================================

    async def acknowledge_alert(
        self,
        alert_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[Alert]:
        """Mark alert as acknowledged."""
        alert = await self.get_alert(alert_id, company_id)
        if not alert:
            return None

        if alert.status == AlertStatus.RESOLVED.value:
            logger.warning("cannot_acknowledge_resolved_alert", alert_id=str(alert_id))
            return alert

        alert.status = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by_id = user_id

        await self.session.flush()

        logger.info(
            "alert_acknowledged",
            alert_id=str(alert_id),
            user_id=str(user_id),
        )

        return alert

    async def dismiss_alert(
        self,
        alert_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None,
        company_id: Optional[UUID] = None,
    ) -> Optional[Alert]:
        """Dismiss alert (mark as not relevant)."""
        alert = await self.get_alert(alert_id, company_id)
        if not alert:
            return None

        alert.status = AlertStatus.DISMISSED.value
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by_id = user_id
        alert.resolution_note = reason or "Vom Benutzer verworfen"
        alert.resolution_action = "dismissed"

        await self.session.flush()

        logger.info(
            "alert_dismissed",
            alert_id=str(alert_id),
            user_id=str(user_id),
        )

        return alert

    async def resolve_alert(
        self,
        alert_id: UUID,
        user_id: UUID,
        resolution_note: Optional[str] = None,
        resolution_action: Optional[str] = None,
        company_id: Optional[UUID] = None,
    ) -> Optional[Alert]:
        """Resolve alert with optional note."""
        alert = await self.get_alert(alert_id, company_id)
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by_id = user_id
        alert.resolution_note = resolution_note
        alert.resolution_action = resolution_action or "resolved"

        await self.session.flush()

        logger.info(
            "alert_resolved",
            alert_id=str(alert_id),
            user_id=str(user_id),
            action=resolution_action,
        )

        return alert

    async def escalate_alert(
        self,
        alert_id: UUID,
        escalate_to_id: UUID,
        escalated_by_id: UUID,
        reason: Optional[str] = None,
        company_id: Optional[UUID] = None,
    ) -> Optional[Alert]:
        """Escalate alert to another user."""
        alert = await self.get_alert(alert_id, company_id)
        if not alert:
            return None

        alert.status = AlertStatus.ESCALATED.value
        alert.escalated_at = datetime.now(timezone.utc)
        alert.escalated_to_id = escalate_to_id
        alert.escalation_level += 1
        alert.assigned_to_id = escalate_to_id

        if reason:
            current_metadata = alert.alert_metadata or {}
            current_metadata["escalation_reason"] = reason
            alert.alert_metadata = current_metadata

        await self.session.flush()

        logger.info(
            "alert_escalated",
            alert_id=str(alert_id),
            escalated_to=str(escalate_to_id),
            level=alert.escalation_level,
        )

        return alert

    async def assign_alert(
        self,
        alert_id: UUID,
        assigned_to_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[Alert]:
        """Assign alert to a user."""
        alert = await self.get_alert(alert_id, company_id)
        if not alert:
            return None

        alert.assigned_to_id = assigned_to_id

        if alert.status == AlertStatus.NEW.value:
            alert.status = AlertStatus.ACKNOWLEDGED.value
            alert.acknowledged_at = datetime.now(timezone.utc)

        await self.session.flush()

        logger.info(
            "alert_assigned",
            alert_id=str(alert_id),
            assigned_to=str(assigned_to_id),
        )

        return alert

    async def bulk_action(
        self,
        alert_ids: List[UUID],
        action: str,
        user_id: UUID,
        company_id: UUID,
        **kwargs: Any,
    ) -> Dict[str, int]:
        """
        Perform bulk action on multiple alerts.

        Args:
            alert_ids: List of alert IDs
            action: Action to perform (acknowledge, dismiss, resolve)
            user_id: User performing the action
            company_id: Company ID
            **kwargs: Additional action parameters

        Returns:
            Statistics about the operation
        """
        success_count = 0
        error_count = 0

        for alert_id in alert_ids:
            try:
                if action == "acknowledge":
                    result = await self.acknowledge_alert(alert_id, user_id, company_id)
                elif action == "dismiss":
                    result = await self.dismiss_alert(
                        alert_id, user_id, kwargs.get("reason"), company_id
                    )
                elif action == "resolve":
                    result = await self.resolve_alert(
                        alert_id, user_id,
                        kwargs.get("resolution_note"),
                        kwargs.get("resolution_action"),
                        company_id,
                    )
                else:
                    error_count += 1
                    continue

                if result:
                    success_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(
                    "bulk_action_error",
                    alert_id=str(alert_id),
                    action=action,
                    error=str(e),
                )
                error_count += 1

        return {
            "success_count": success_count,
            "error_count": error_count,
            "total": len(alert_ids),
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _find_active_by_recurrence_key(
        self,
        company_id: UUID,
        recurrence_key: str,
    ) -> Optional[Alert]:
        """Find active alert with the same recurrence key."""
        stmt = (
            select(Alert)
            .where(Alert.company_id == company_id)
            .where(Alert.recurrence_key == recurrence_key)
            .where(Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _send_alert_email(
        self,
        alert: Alert,
        email: str,
    ) -> None:
        """Send email notification for alert."""
        try:
            priority = NotificationPriority.HIGH
            if alert.severity == AlertSeverity.CRITICAL.value:
                priority = NotificationPriority.CRITICAL
            elif alert.severity == AlertSeverity.LOW.value:
                priority = NotificationPriority.NORMAL

            subject = f"[{alert.severity.upper()}] {alert.title}"
            body = f"""
Alert: {alert.title}

Kategorie: {alert.category}
Schweregrad: {alert.severity}
Code: {alert.alert_code}

{alert.message}

Erstellt: {alert.created_at.strftime("%d.%m.%Y %H:%M")} Uhr

---
Ablage-System Alert Center
            """.strip()

            await self.notification_service.email.send(
                to_email=email,
                subject=subject,
                body=body,
            )

            alert.email_sent = True
            alert.email_sent_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(
                "alert_email_failed",
                alert_id=str(alert.id),
                error=str(e),
            )

    async def cleanup_auto_dismissed(self) -> int:
        """
        Cleanup alerts that have passed their auto-dismiss time.

        Uses bulk UPDATE for performance optimization (avoids N+1 queries).

        Returns:
            Number of alerts dismissed
        """
        now = datetime.now(timezone.utc)

        # Bulk UPDATE instead of fetch-and-loop pattern
        stmt = (
            update(Alert)
            .where(Alert.auto_dismiss_at <= now)
            .where(Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]))
            .values(
                status=AlertStatus.DISMISSED.value,
                resolution_note="Automatisch verworfen nach Zeitablauf",
                resolution_action="auto_dismissed",
                resolved_at=now,
            )
        )

        result = await self.session.execute(stmt)
        count = result.rowcount

        await self.session.flush()

        if count > 0:
            logger.info("alerts_auto_dismissed", count=count)

        return count


# =============================================================================
# Factory Function
# =============================================================================

def get_alert_center_service(session: AsyncSession) -> AlertCenterService:
    """Factory function to create AlertCenterService instance."""
    return AlertCenterService(session)
