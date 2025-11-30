"""
Security Audit Logger für Ablage-System.

Protokolliert alle sicherheitsrelevanten Events für GDPR Art. 25/30 Compliance.

Events werden in die AuditLog-Tabelle geschrieben und können für
Compliance-Reports und Security-Monitoring verwendet werden.

Feinpoliert und durchdacht - Enterprise-grade Audit Logging.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class SecurityEventType(str, Enum):
    """Typen von Security-Events für Audit-Logging."""

    # Authentication Events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_REVOKED = "token_revoked"

    # 2FA Events
    TWO_FA_SETUP_INITIATED = "2fa_setup_initiated"
    TWO_FA_ENABLED = "2fa_enabled"
    TWO_FA_DISABLED = "2fa_disabled"
    TWO_FA_BACKUP_USED = "2fa_backup_used"
    TWO_FA_BACKUP_REGENERATED = "2fa_backup_regenerated"
    TWO_FA_FAILED = "2fa_failed"

    # Account Events
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    ACCOUNT_DEACTIVATED = "account_deactivated"
    ACCOUNT_REACTIVATED = "account_reactivated"

    # Password Events
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    PASSWORD_RESET_FAILED = "password_reset_failed"

    # Permission Events
    ROLE_CHANGED = "role_changed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"

    # Security Violations
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    INVALID_TOKEN_USED = "invalid_token_used"
    UNAUTHORIZED_ACCESS = "unauthorized_access"

    # Admin Actions
    ADMIN_USER_CREATED = "admin_user_created"
    ADMIN_USER_UPDATED = "admin_user_updated"
    ADMIN_USER_DELETED = "admin_user_deleted"
    ADMIN_FORCE_LOGOUT = "admin_force_logout"


class SecurityAuditLogger:
    """
    Security Audit Logger für GDPR-konforme Protokollierung.

    Verwendung:
        audit = SecurityAuditLogger(db_session)
        await audit.log_login_success(user_id, ip_address)
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        """
        Initialisiert den Audit Logger.

        Args:
            db: Optional AsyncSession für Datenbankzugriff.
                Wenn None, wird nur strukturiertes Logging verwendet.
        """
        self.db = db

    async def log_event(
        self,
        event_type: SecurityEventType,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ) -> Optional[str]:
        """
        Protokolliert ein Security-Event.

        Args:
            event_type: Typ des Events
            user_id: Betroffene Benutzer-ID
            ip_address: Client-IP-Adresse
            user_agent: User-Agent des Clients
            resource_type: Typ der betroffenen Ressource
            resource_id: ID der betroffenen Ressource
            details: Zusätzliche Event-Details (KEINE SENSITIVEN DATEN!)
            severity: Event-Schweregrad (info, warning, error, critical)

        Returns:
            Audit-Log-ID oder None bei Fehler
        """
        # Strukturiertes Logging (immer)
        log_data = {
            "event": event_type.value,
            "user_id": user_id[:8] + "..." if user_id else None,
            "ip": ip_address,
            "resource_type": resource_type,
            "severity": severity,
        }

        # Details hinzufügen (sensitive Daten filtern)
        if details:
            safe_details = self._filter_sensitive_data(details)
            log_data["details"] = safe_details

        # Log basierend auf Severity
        if severity == "critical":
            logger.critical("security_audit", **log_data)
        elif severity == "error":
            logger.error("security_audit", **log_data)
        elif severity == "warning":
            logger.warning("security_audit", **log_data)
        else:
            logger.info("security_audit", **log_data)

        # In Datenbank speichern (falls Session vorhanden)
        if self.db:
            try:
                return await self._save_to_db(
                    event_type=event_type,
                    user_id=user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=details or {},
                )
            except Exception as e:
                logger.error(
                    "audit_log_db_error",
                    error=str(e),
                    event_type=event_type.value,
                )

        return None

    async def _save_to_db(
        self,
        event_type: SecurityEventType,
        user_id: Optional[str],
        ip_address: Optional[str],
        user_agent: Optional[str],
        resource_type: Optional[str],
        resource_id: Optional[str],
        details: Dict[str, Any],
    ) -> str:
        """Speichert Event in AuditLog-Tabelle."""
        from app.db.models import AuditLog

        audit_log = AuditLog(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id) if user_id else None,
            action=event_type.value,
            resource_type=resource_type or "security",
            resource_id=uuid.UUID(resource_id) if resource_id else None,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
            request_method=None,
            request_path=None,
            audit_metadata=self._filter_sensitive_data(details),
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(audit_log)
        await self.db.flush()

        return str(audit_log.id)

    def _filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filtert sensitive Daten aus dem Details-Dict.

        NIEMALS loggen:
        - Passwörter (auch Hashes)
        - Tokens
        - Secrets
        - PII (Vollständige E-Mail, etc.)
        """
        sensitive_keys = {
            "password", "passwd", "secret", "token", "key",
            "authorization", "auth", "credential", "totp",
            "backup_code", "hash", "salt",
        }

        filtered = {}
        for key, value in data.items():
            key_lower = key.lower()

            # Prüfe auf sensitive Keys
            if any(s in key_lower for s in sensitive_keys):
                filtered[key] = "[REDACTED]"
            # E-Mail maskieren
            elif key_lower == "email" and isinstance(value, str):
                filtered[key] = value[:3] + "***" if len(value) > 3 else "***"
            # User-ID kürzen
            elif key_lower in ("user_id", "userid") and isinstance(value, str):
                filtered[key] = value[:8] + "..." if len(value) > 8 else value
            else:
                filtered[key] = value

        return filtered

    # ==================== Convenience Methods ====================

    async def log_login_success(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Protokolliert erfolgreichen Login."""
        return await self.log_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

    async def log_login_failed(
        self,
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert fehlgeschlagenen Login."""
        return await self.log_event(
            event_type=SecurityEventType.LOGIN_FAILED,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"email": email, "reason": reason},
            severity="warning",
        )

    async def log_2fa_enabled(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert 2FA-Aktivierung."""
        return await self.log_event(
            event_type=SecurityEventType.TWO_FA_ENABLED,
            user_id=user_id,
            ip_address=ip_address,
        )

    async def log_2fa_disabled(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        used_backup: bool = False,
    ) -> Optional[str]:
        """Protokolliert 2FA-Deaktivierung."""
        return await self.log_event(
            event_type=SecurityEventType.TWO_FA_DISABLED,
            user_id=user_id,
            ip_address=ip_address,
            details={"used_backup_code": used_backup},
            severity="warning",
        )

    async def log_account_locked(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        lockout_duration_seconds: Optional[int] = None,
        failed_attempts: Optional[int] = None,
    ) -> Optional[str]:
        """Protokolliert Account-Sperrung."""
        return await self.log_event(
            event_type=SecurityEventType.ACCOUNT_LOCKED,
            user_id=user_id,
            ip_address=ip_address,
            details={
                "lockout_duration_seconds": lockout_duration_seconds,
                "failed_attempts": failed_attempts,
            },
            severity="warning",
        )

    async def log_brute_force_detected(
        self,
        ip_address: str,
        target_email: Optional[str] = None,
        attempts: int = 0,
    ) -> Optional[str]:
        """Protokolliert Brute-Force-Angriffserkennung."""
        return await self.log_event(
            event_type=SecurityEventType.BRUTE_FORCE_DETECTED,
            ip_address=ip_address,
            details={
                "target_email": target_email,
                "attempts": attempts,
            },
            severity="critical",
        )

    async def log_password_changed(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        forced_by_admin: bool = False,
    ) -> Optional[str]:
        """Protokolliert Passwort-Änderung."""
        return await self.log_event(
            event_type=SecurityEventType.PASSWORD_CHANGED,
            user_id=user_id,
            ip_address=ip_address,
            details={"forced_by_admin": forced_by_admin},
        )

    async def log_role_changed(
        self,
        user_id: str,
        admin_id: str,
        old_role: str,
        new_role: str,
        ip_address: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert Rollenänderung."""
        return await self.log_event(
            event_type=SecurityEventType.ROLE_CHANGED,
            user_id=user_id,
            ip_address=ip_address,
            details={
                "admin_id": admin_id,
                "old_role": old_role,
                "new_role": new_role,
            },
            severity="warning",
        )

    async def log_unauthorized_access(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert unberechtigten Zugriffsversuch."""
        return await self.log_event(
            event_type=SecurityEventType.UNAUTHORIZED_ACCESS,
            user_id=user_id,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            details={"reason": reason},
            severity="warning",
        )


# Singleton-Instance für globalen Zugriff (ohne DB)
_global_audit_logger: Optional[SecurityAuditLogger] = None


def get_audit_logger(db: Optional[AsyncSession] = None) -> SecurityAuditLogger:
    """
    Factory für SecurityAuditLogger.

    Args:
        db: Optional AsyncSession für Datenbankzugriff

    Returns:
        SecurityAuditLogger instance
    """
    global _global_audit_logger

    if db:
        # Mit DB-Session: Neuen Logger erstellen
        return SecurityAuditLogger(db)

    # Ohne DB: Singleton für strukturiertes Logging
    if _global_audit_logger is None:
        _global_audit_logger = SecurityAuditLogger()

    return _global_audit_logger
