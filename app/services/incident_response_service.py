# -*- coding: utf-8 -*-
"""
Incident Response Automation Service für Ablage-System OCR.

Automatische Erkennung und Reaktion auf Sicherheitsvorfälle:
- Pattern-Erkennung (Brute-Force, Anomalien)
- Automatische Gegenmaßnahmen (IP-Sperre, Account-Lockout)
- Benachrichtigungen (Admin-Alerts, Webhook-Notifications)
- Incident-Tracking und Reporting

Feinpoliert und durchdacht - Enterprise-grade Security Response.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from uuid import UUID
import hashlib

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.core.audit_logger import SecurityEventType
from app.db.models import AuditLog, User

logger = structlog.get_logger(__name__)


class IncidentSeverity(str, Enum):
    """Schweregrad eines Sicherheitsvorfalls."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentType(str, Enum):
    """Typen von Sicherheitsvorfällen."""
    BRUTE_FORCE_ATTACK = "brute_force_attack"
    ACCOUNT_TAKEOVER_ATTEMPT = "account_takeover_attempt"
    SUSPICIOUS_IP_ACTIVITY = "suspicious_ip_activity"
    RATE_LIMIT_ABUSE = "rate_limit_abuse"
    UNAUTHORIZED_API_ACCESS = "unauthorized_api_access"
    DATA_EXFILTRATION_ATTEMPT = "data_exfiltration_attempt"
    SESSION_ANOMALY = "session_anomaly"
    ADMIN_ACCOUNT_COMPROMISE = "admin_account_compromise"
    DLQ_CRITICAL = "dlq_critical"  # Dead Letter Queue kritischer Zustand
    SYSTEM_HEALTH_CRITICAL = "system_health_critical"  # Allgemeine Systemprobleme


class ResponseAction(str, Enum):
    """Automatische Reaktionsmaßnahmen."""
    LOG_ONLY = "log_only"
    NOTIFY_ADMIN = "notify_admin"
    BLOCK_IP_TEMPORARY = "block_ip_temporary"
    BLOCK_IP_PERMANENT = "block_ip_permanent"
    LOCK_ACCOUNT = "lock_account"
    REVOKE_ALL_SESSIONS = "revoke_all_sessions"
    REVOKE_API_KEYS = "revoke_api_keys"
    NOTIFY_USER = "notify_user"
    REQUIRE_2FA = "require_2fa"


# Incident-Schwellenwerte (konfigurierbar)
INCIDENT_THRESHOLDS = {
    "failed_logins_threshold": getattr(settings, "INCIDENT_FAILED_LOGINS", 10),
    "failed_logins_window_minutes": getattr(settings, "INCIDENT_FAILED_LOGINS_WINDOW", 15),
    "rate_limit_threshold": getattr(settings, "INCIDENT_RATE_LIMIT_THRESHOLD", 50),
    "rate_limit_window_minutes": getattr(settings, "INCIDENT_RATE_LIMIT_WINDOW", 5),
    "unauthorized_access_threshold": getattr(settings, "INCIDENT_UNAUTHORIZED_THRESHOLD", 5),
    "suspicious_session_threshold": getattr(settings, "INCIDENT_SUSPICIOUS_SESSION_THRESHOLD", 3),
}

# Response-Regeln basierend auf Incident-Typ und Schweregrad
RESPONSE_RULES: Dict[IncidentType, Dict[IncidentSeverity, List[ResponseAction]]] = {
    IncidentType.BRUTE_FORCE_ATTACK: {
        IncidentSeverity.MEDIUM: [ResponseAction.NOTIFY_ADMIN, ResponseAction.BLOCK_IP_TEMPORARY],
        IncidentSeverity.HIGH: [ResponseAction.NOTIFY_ADMIN, ResponseAction.BLOCK_IP_TEMPORARY, ResponseAction.LOCK_ACCOUNT],
        IncidentSeverity.CRITICAL: [ResponseAction.NOTIFY_ADMIN, ResponseAction.BLOCK_IP_PERMANENT, ResponseAction.LOCK_ACCOUNT, ResponseAction.REVOKE_ALL_SESSIONS],
    },
    IncidentType.SUSPICIOUS_IP_ACTIVITY: {
        IncidentSeverity.LOW: [ResponseAction.LOG_ONLY],
        IncidentSeverity.MEDIUM: [ResponseAction.NOTIFY_ADMIN],
        IncidentSeverity.HIGH: [ResponseAction.NOTIFY_ADMIN, ResponseAction.BLOCK_IP_TEMPORARY],
    },
    IncidentType.RATE_LIMIT_ABUSE: {
        IncidentSeverity.MEDIUM: [ResponseAction.NOTIFY_ADMIN, ResponseAction.BLOCK_IP_TEMPORARY],
        IncidentSeverity.HIGH: [ResponseAction.NOTIFY_ADMIN, ResponseAction.BLOCK_IP_TEMPORARY, ResponseAction.REVOKE_API_KEYS],
    },
    IncidentType.UNAUTHORIZED_API_ACCESS: {
        IncidentSeverity.MEDIUM: [ResponseAction.NOTIFY_ADMIN, ResponseAction.REVOKE_API_KEYS],
        IncidentSeverity.HIGH: [ResponseAction.NOTIFY_ADMIN, ResponseAction.REVOKE_API_KEYS, ResponseAction.BLOCK_IP_TEMPORARY],
    },
    IncidentType.ADMIN_ACCOUNT_COMPROMISE: {
        IncidentSeverity.CRITICAL: [ResponseAction.NOTIFY_ADMIN, ResponseAction.LOCK_ACCOUNT, ResponseAction.REVOKE_ALL_SESSIONS, ResponseAction.REQUIRE_2FA],
    },
    IncidentType.SESSION_ANOMALY: {
        IncidentSeverity.MEDIUM: [ResponseAction.NOTIFY_USER, ResponseAction.REVOKE_ALL_SESSIONS],
        IncidentSeverity.HIGH: [ResponseAction.NOTIFY_ADMIN, ResponseAction.NOTIFY_USER, ResponseAction.REVOKE_ALL_SESSIONS],
    },
    IncidentType.DLQ_CRITICAL: {
        IncidentSeverity.HIGH: [ResponseAction.NOTIFY_ADMIN],
        IncidentSeverity.CRITICAL: [ResponseAction.NOTIFY_ADMIN],
    },
    IncidentType.SYSTEM_HEALTH_CRITICAL: {
        IncidentSeverity.MEDIUM: [ResponseAction.NOTIFY_ADMIN],
        IncidentSeverity.HIGH: [ResponseAction.NOTIFY_ADMIN],
        IncidentSeverity.CRITICAL: [ResponseAction.NOTIFY_ADMIN],
    },
}


class Incident:
    """Repräsentiert einen erkannten Sicherheitsvorfall."""

    def __init__(
        self,
        incident_type: IncidentType,
        severity: IncidentSeverity,
        description: str,
        ip_address: Optional[str] = None,
        user_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.id = hashlib.sha256(
            f"{datetime.now(timezone.utc).isoformat()}{incident_type}{ip_address}{user_id}".encode()
        ).hexdigest()[:16]
        self.type = incident_type
        self.severity = severity
        self.description = description
        self.ip_address = ip_address
        self.user_id = user_id
        self.details = details or {}
        self.created_at = datetime.now(timezone.utc)
        self.actions_taken: List[ResponseAction] = []

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert Incident zu Dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "severity": self.severity.value,
            "description": self.description,
            "ip_address": self.ip_address,
            "user_id": str(self.user_id) if self.user_id else None,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
            "actions_taken": [a.value for a in self.actions_taken],
        }


class IncidentResponseService:
    """Service für automatische Incident-Erkennung und -Reaktion."""

    def __init__(self):
        self.active_incidents: Dict[str, Incident] = {}
        self._blocked_ips: Dict[str, datetime] = {}  # IP -> Unblock-Zeit
        self._ip_block_duration = timedelta(hours=1)

    async def analyze_security_events(
        self,
        db: AsyncSession,
        window_minutes: int = 15
    ) -> List[Incident]:
        """
        Analysiert Security-Events und erkennt Incidents.

        Args:
            db: Datenbank-Session
            window_minutes: Zeitfenster für Analyse

        Returns:
            Liste erkannter Incidents
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        incidents: List[Incident] = []

        # 1. Brute-Force-Erkennung
        brute_force_incidents = await self._detect_brute_force(db, since)
        incidents.extend(brute_force_incidents)

        # 2. Rate-Limit-Missbrauch
        rate_limit_incidents = await self._detect_rate_limit_abuse(db, since)
        incidents.extend(rate_limit_incidents)

        # 3. Unauthorized Access Pattern
        unauthorized_incidents = await self._detect_unauthorized_access(db, since)
        incidents.extend(unauthorized_incidents)

        # Speichere aktive Incidents
        for incident in incidents:
            self.active_incidents[incident.id] = incident

        return incidents

    async def _detect_brute_force(
        self,
        db: AsyncSession,
        since: datetime
    ) -> List[Incident]:
        """Erkennt Brute-Force-Angriffe basierend auf fehlgeschlagenen Logins."""
        incidents = []
        threshold = INCIDENT_THRESHOLDS["failed_logins_threshold"]

        # Gruppiere fehlgeschlagene Logins nach IP
        result = await db.execute(
            select(
                AuditLog.ip_address,
                func.count(AuditLog.id).label("count")
            )
            .where(
                and_(
                    AuditLog.action == SecurityEventType.LOGIN_FAILED.value,
                    AuditLog.created_at >= since,
                    AuditLog.ip_address.isnot(None)
                )
            )
            .group_by(AuditLog.ip_address)
            .having(func.count(AuditLog.id) >= threshold)
        )

        for row in result:
            ip_address = row.ip_address
            count = row.count

            severity = IncidentSeverity.MEDIUM
            if count >= threshold * 2:
                severity = IncidentSeverity.HIGH
            if count >= threshold * 5:
                severity = IncidentSeverity.CRITICAL

            incident = Incident(
                incident_type=IncidentType.BRUTE_FORCE_ATTACK,
                severity=severity,
                description=f"Brute-Force-Angriff erkannt: {count} fehlgeschlagene Logins von IP {ip_address}",
                ip_address=ip_address,
                details={"failed_login_count": count, "threshold": threshold}
            )
            incidents.append(incident)

            logger.error(
                "brute_force_detected",
                ip_address=ip_address,
                failed_count=count,
                severity=severity.value,
                security_event=True
            )

        return incidents

    async def _detect_rate_limit_abuse(
        self,
        db: AsyncSession,
        since: datetime
    ) -> List[Incident]:
        """Erkennt wiederholte Rate-Limit-Überschreitungen."""
        incidents = []
        threshold = INCIDENT_THRESHOLDS["rate_limit_threshold"]

        result = await db.execute(
            select(
                AuditLog.ip_address,
                func.count(AuditLog.id).label("count")
            )
            .where(
                and_(
                    AuditLog.action == SecurityEventType.RATE_LIMIT_EXCEEDED.value,
                    AuditLog.created_at >= since,
                    AuditLog.ip_address.isnot(None)
                )
            )
            .group_by(AuditLog.ip_address)
            .having(func.count(AuditLog.id) >= threshold)
        )

        for row in result:
            ip_address = row.ip_address
            count = row.count

            severity = IncidentSeverity.MEDIUM
            if count >= threshold * 2:
                severity = IncidentSeverity.HIGH

            incident = Incident(
                incident_type=IncidentType.RATE_LIMIT_ABUSE,
                severity=severity,
                description=f"Rate-Limit-Missbrauch: {count} Überschreitungen von IP {ip_address}",
                ip_address=ip_address,
                details={"rate_limit_count": count}
            )
            incidents.append(incident)

        return incidents

    async def _detect_unauthorized_access(
        self,
        db: AsyncSession,
        since: datetime
    ) -> List[Incident]:
        """Erkennt Pattern von Unauthorized Access Attempts."""
        incidents = []
        threshold = INCIDENT_THRESHOLDS["unauthorized_access_threshold"]

        result = await db.execute(
            select(
                AuditLog.user_id,
                AuditLog.ip_address,
                func.count(AuditLog.id).label("count")
            )
            .where(
                and_(
                    AuditLog.action == SecurityEventType.UNAUTHORIZED_ACCESS.value,
                    AuditLog.created_at >= since
                )
            )
            .group_by(AuditLog.user_id, AuditLog.ip_address)
            .having(func.count(AuditLog.id) >= threshold)
        )

        for row in result:
            user_id = row.user_id
            ip_address = row.ip_address
            count = row.count

            incident = Incident(
                incident_type=IncidentType.UNAUTHORIZED_API_ACCESS,
                severity=IncidentSeverity.MEDIUM,
                description=f"Wiederholte Unauthorized Access Versuche: {count}",
                ip_address=ip_address,
                user_id=UUID(user_id) if user_id else None,
                details={"access_count": count}
            )
            incidents.append(incident)

        return incidents

    async def execute_response(
        self,
        incident: Incident,
        db: AsyncSession
    ) -> List[str]:
        """
        Führt automatische Reaktionsmaßnahmen für einen Incident aus.

        Args:
            incident: Erkannter Incident
            db: Datenbank-Session

        Returns:
            Liste der ausgeführten Aktionen
        """
        executed_actions: List[str] = []

        # Hole Response-Regeln
        rules = RESPONSE_RULES.get(incident.type, {})
        actions = rules.get(incident.severity, [ResponseAction.LOG_ONLY])

        for action in actions:
            try:
                result = await self._execute_action(action, incident, db)
                if result:
                    executed_actions.append(result)
                    incident.actions_taken.append(action)
            except Exception as e:
                logger.error(
                    "response_action_failed",
                    action=action.value,
                    incident_id=incident.id,
                    error=str(e)
                )

        logger.info(
            "incident_response_executed",
            incident_id=incident.id,
            incident_type=incident.type.value,
            severity=incident.severity.value,
            actions=executed_actions
        )

        return executed_actions

    async def _execute_action(
        self,
        action: ResponseAction,
        incident: Incident,
        db: AsyncSession
    ) -> Optional[str]:
        """Führt eine einzelne Reaktionsmaßnahme aus."""

        if action == ResponseAction.LOG_ONLY:
            logger.info(
                "incident_logged",
                incident_id=incident.id,
                type=incident.type.value,
                description=incident.description
            )
            return "Incident protokolliert"

        elif action == ResponseAction.NOTIFY_ADMIN:
            await self._notify_admin(incident)
            return "Admin benachrichtigt"

        elif action == ResponseAction.BLOCK_IP_TEMPORARY:
            if incident.ip_address:
                await self._block_ip(incident.ip_address, permanent=False)
                return f"IP {incident.ip_address} temporär gesperrt"

        elif action == ResponseAction.BLOCK_IP_PERMANENT:
            if incident.ip_address:
                await self._block_ip(incident.ip_address, permanent=True)
                return f"IP {incident.ip_address} permanent gesperrt"

        elif action == ResponseAction.LOCK_ACCOUNT:
            if incident.user_id:
                await self._lock_account(db, incident.user_id)
                return f"Account {str(incident.user_id)[:8]}... gesperrt"

        elif action == ResponseAction.REVOKE_ALL_SESSIONS:
            if incident.user_id:
                await self._revoke_sessions(db, incident.user_id)
                return f"Sessions für {str(incident.user_id)[:8]}... widerrufen"

        elif action == ResponseAction.REVOKE_API_KEYS:
            if incident.user_id:
                await self._revoke_api_keys(db, incident.user_id)
                return f"API-Keys für {str(incident.user_id)[:8]}... widerrufen"

        elif action == ResponseAction.NOTIFY_USER:
            if incident.user_id:
                await self._notify_user(db, incident)
                return f"Benutzer {str(incident.user_id)[:8]}... benachrichtigt"

        return None

    async def _notify_admin(self, incident: Incident) -> None:
        """Sendet Admin-Benachrichtigung über Incident."""
        try:
            from app.services.notification_service import NotificationService

            service = NotificationService()
            await service.send_admin_alert(
                title=f"Sicherheitsvorfall: {incident.type.value}",
                message=incident.description,
                severity=incident.severity.value,
                details=incident.to_dict()
            )
        except Exception as e:
            logger.warning("admin_notification_failed", error=str(e))

    async def _block_ip(self, ip_address: str, permanent: bool = False) -> None:
        """Blockiert eine IP-Adresse."""
        if permanent:
            # Bei permanenter Sperre: In Redis mit langem TTL speichern
            expiry = datetime.now(timezone.utc) + timedelta(days=365)
        else:
            expiry = datetime.now(timezone.utc) + self._ip_block_duration

        self._blocked_ips[ip_address] = expiry

        # Persistiere in Redis wenn verfügbar
        try:
            from app.core.redis_client import get_redis

            redis = await get_redis()
            if redis:
                ttl = int((expiry - datetime.now(timezone.utc)).total_seconds())
                await redis.setex(f"blocked_ip:{ip_address}", ttl, "1")
        except Exception as e:
            logger.warning("ip_block_redis_failed", ip=ip_address, error=str(e))

        logger.warning(
            "ip_blocked",
            ip_address=ip_address,
            permanent=permanent,
            until=expiry.isoformat()
        )

    async def _lock_account(self, db: AsyncSession, user_id: UUID) -> None:
        """Sperrt ein Benutzerkonto."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            user.is_active = False
            await db.commit()

            logger.warning("account_locked_incident_response", user_id=str(user_id)[:8])

    async def _revoke_sessions(self, db: AsyncSession, user_id: UUID) -> None:
        """Widerruft alle Sessions eines Benutzers."""
        try:
            from app.core.session_manager import get_session_manager

            session_manager = get_session_manager()
            await session_manager.revoke_all_sessions(db, user_id)
        except Exception as e:
            logger.warning("session_revoke_failed", user_id=str(user_id)[:8], error=str(e))

    async def _revoke_api_keys(self, db: AsyncSession, user_id: UUID) -> None:
        """Widerruft alle API-Keys eines Benutzers."""
        try:
            from app.services.api_key_service import get_api_key_service

            service = get_api_key_service()
            await service.revoke_all_keys(db, user_id)
        except Exception as e:
            logger.warning("api_key_revoke_failed", user_id=str(user_id)[:8], error=str(e))

    async def _notify_user(self, db: AsyncSession, incident: Incident) -> None:
        """Benachrichtigt den betroffenen Benutzer."""
        if not incident.user_id:
            return

        result = await db.execute(
            select(User).where(User.id == incident.user_id)
        )
        user = result.scalar_one_or_none()

        if user and user.email:
            try:
                from app.services.notification_service import NotificationService

                service = NotificationService()
                await service.send_security_alert(
                    user_email=user.email,
                    title="Sicherheitswarnung",
                    message=f"Wir haben ungewöhnliche Aktivitäten in Ihrem Konto festgestellt: {incident.description}"
                )
            except Exception as e:
                logger.warning("user_notification_failed", user_id=str(incident.user_id)[:8], error=str(e))

    def is_ip_blocked(self, ip_address: str) -> bool:
        """Prüft ob eine IP-Adresse blockiert ist."""
        if ip_address in self._blocked_ips:
            if self._blocked_ips[ip_address] > datetime.now(timezone.utc):
                return True
            else:
                # Sperre abgelaufen
                del self._blocked_ips[ip_address]
        return False

    def get_active_incidents(self) -> List[Dict[str, Any]]:
        """Gibt alle aktiven Incidents zurück."""
        return [incident.to_dict() for incident in self.active_incidents.values()]

    def get_blocked_ips(self) -> Dict[str, str]:
        """Gibt alle blockierten IPs mit Ablaufzeit zurück."""
        now = datetime.now(timezone.utc)
        return {
            ip: expiry.isoformat()
            for ip, expiry in self._blocked_ips.items()
            if expiry > now
        }


# Singleton-Instanz
_incident_response_service: Optional[IncidentResponseService] = None


def get_incident_response_service() -> IncidentResponseService:
    """Gibt IncidentResponseService-Singleton zurück."""
    global _incident_response_service
    if _incident_response_service is None:
        _incident_response_service = IncidentResponseService()
    return _incident_response_service


def report_system_incident(
    incident_type: IncidentType,
    severity: IncidentSeverity,
    description: str,
    details: Optional[Dict[str, Any]] = None
) -> Incident:
    """Meldet einen System-Incident (DLQ, Health etc.) - synchron aufrufbar.

    Diese Funktion kann von synchronen Celery Tasks aufgerufen werden.

    Args:
        incident_type: Art des Incidents (DLQ_CRITICAL, SYSTEM_HEALTH_CRITICAL)
        severity: Schweregrad (HIGH, CRITICAL)
        description: Beschreibung des Problems
        details: Zusätzliche Details als Dict

    Returns:
        Erstellter Incident

    Example:
        from app.services.incident_response_service import (
            report_system_incident, IncidentType, IncidentSeverity
        )
        report_system_incident(
            IncidentType.DLQ_CRITICAL,
            IncidentSeverity.CRITICAL,
            "DLQ enthält 500+ fehlgeschlagene Tasks",
            details={"count": 523, "poison_pills": 3}
        )
    """
    service = get_incident_response_service()
    incident = Incident(
        incident_type=incident_type,
        severity=severity,
        description=description,
        details=details or {}
    )

    # Speichere in aktiven Incidents
    service.active_incidents[incident.id] = incident

    # Logging mit strukturierten Daten
    log_method = logger.critical if severity == IncidentSeverity.CRITICAL else logger.error
    log_method(
        "system_incident_reported",
        incident_id=incident.id,
        incident_type=incident_type.value,
        severity=severity.value,
        description=description,
        details=details
    )

    # Admin-Benachrichtigung auslösen (async wird im Background gestartet)
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Wenn bereits ein Event Loop läuft, Task erstellen
            asyncio.create_task(service._notify_admin(incident))
        else:
            # Ansonsten synchron ausführen
            loop.run_until_complete(service._notify_admin(incident))
    except RuntimeError:
        # Kein Event Loop verfügbar - nur loggen
        logger.warning(
            "admin_notification_skipped",
            reason="no_event_loop",
            incident_id=incident.id
        )

    return incident
