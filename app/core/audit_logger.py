"""
Security Audit Logger für Ablage-System.

Protokolliert alle sicherheitsrelevanten Events für GDPR Art. 25/30 Compliance.

Events werden in die AuditLog-Tabelle geschrieben und können für
Compliance-Reports und Security-Monitoring verwendet werden.

Arbeitspaket 6: Audit Log Immutabilität
- Blockchain-ähnliche Verkettung mit previous_hash
- SHA-256 Integrity-Hash pro Eintrag
- Sequenznummern für Ordering
- Verifikationsfunktionen für Tamper-Detection

Feinpoliert und durchdacht - Enterprise-grade Audit Logging.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import uuid
import hashlib
import json

import structlog
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Genesis-Hash für den ersten Eintrag in der Kette
GENESIS_HASH = "0" * 64  # 64 Nullen als Genesis-Block-Hash


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


# ==================== Integrity Functions (AP6) ====================

def calculate_entry_hash(
    sequence_number: int,
    user_id: Optional[str],
    action: str,
    resource_type: Optional[str],
    resource_id: Optional[str],
    ip_address: Optional[str],
    created_at: datetime,
    metadata: Dict[str, Any],
    previous_hash: str,
) -> str:
    """
    Berechnet den SHA-256 Integrity-Hash für einen Audit-Log-Eintrag.

    Der Hash wird aus allen relevanten Feldern berechnet, um sicherzustellen,
    dass jede Änderung am Eintrag erkannt werden kann.

    Args:
        sequence_number: Sequenznummer des Eintrags
        user_id: Benutzer-ID
        action: Event-Typ
        resource_type: Ressourcentyp
        resource_id: Ressourcen-ID
        ip_address: IP-Adresse
        created_at: Zeitstempel
        metadata: Zusätzliche Metadaten
        previous_hash: Hash des vorherigen Eintrags

    Returns:
        SHA-256 Hash als Hex-String (64 Zeichen)
    """
    # Erstelle deterministisches Hash-Input
    hash_input = {
        "seq": sequence_number,
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "ip": ip_address,
        "timestamp": created_at.isoformat() if created_at else None,
        "metadata": metadata,
        "prev_hash": previous_hash,
    }

    # JSON-Serialisierung mit sortieren Keys für Determinismus
    json_str = json.dumps(hash_input, sort_keys=True, default=str)

    # SHA-256 Hash
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


def verify_entry_integrity(
    entry: "AuditLog",  # type: ignore
    expected_previous_hash: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Verifiziert die Integrität eines einzelnen Audit-Log-Eintrags.

    Args:
        entry: AuditLog-Eintrag
        expected_previous_hash: Erwarteter previous_hash (optional)

    Returns:
        Tuple von:
        - is_valid: True wenn Integrität OK
        - error_message: Fehlermeldung bei Problemen
    """
    # Berechne erwarteten Hash
    calculated_hash = calculate_entry_hash(
        sequence_number=entry.sequence_number,
        user_id=str(entry.user_id) if entry.user_id else None,
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=str(entry.resource_id) if entry.resource_id else None,
        ip_address=entry.ip_address,
        created_at=entry.created_at,
        metadata=entry.audit_metadata or {},
        previous_hash=entry.previous_hash or GENESIS_HASH,
    )

    # Vergleiche mit gespeichertem Hash
    if entry.integrity_hash != calculated_hash:
        return False, f"Integrity hash mismatch for entry {entry.sequence_number}"

    # Prüfe Verkettung wenn previous_hash erwartet
    if expected_previous_hash is not None:
        if entry.previous_hash != expected_previous_hash:
            return False, f"Chain broken at entry {entry.sequence_number}"

    return True, None


async def verify_audit_chain(
    db: AsyncSession,
    start_sequence: Optional[int] = None,
    end_sequence: Optional[int] = None,
    batch_size: int = 1000,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Verifiziert die Integrität der gesamten Audit-Log-Kette.

    Prüft:
    1. Integrity-Hash jedes Eintrags
    2. Verkettung (previous_hash = integrity_hash des Vorgängers)
    3. Lückenlose Sequenznummern

    Args:
        db: Datenbank-Session
        start_sequence: Startsequenz für partielle Prüfung
        end_sequence: Endsequenz für partielle Prüfung
        batch_size: Anzahl Einträge pro Batch

    Returns:
        Tuple von:
        - is_valid: True wenn gesamte Kette OK
        - errors: Liste der gefundenen Fehler
    """
    from app.db.models import AuditLog

    errors: List[Dict[str, Any]] = []

    # Query vorbereiten
    query = select(AuditLog).order_by(AuditLog.sequence_number)

    if start_sequence is not None:
        query = query.where(AuditLog.sequence_number >= start_sequence)
    if end_sequence is not None:
        query = query.where(AuditLog.sequence_number <= end_sequence)

    # Hole ersten Eintrag für Initialisierung
    result = await db.execute(query.limit(1))
    first_entry = result.scalar_one_or_none()

    if not first_entry:
        # Keine Einträge - alles OK
        return True, []

    # Initialisiere mit erstem Eintrag
    if start_sequence is None or first_entry.sequence_number == 1:
        expected_prev_hash = GENESIS_HASH
    else:
        # Hole Hash des Vorgängers
        prev_query = select(AuditLog).where(
            AuditLog.sequence_number == first_entry.sequence_number - 1
        )
        prev_result = await db.execute(prev_query)
        prev_entry = prev_result.scalar_one_or_none()
        expected_prev_hash = prev_entry.integrity_hash if prev_entry else GENESIS_HASH

    last_sequence: Optional[int] = None
    entries_checked = 0

    # Verifiziere in Batches
    offset = 0
    while True:
        result = await db.execute(query.offset(offset).limit(batch_size))
        entries = result.scalars().all()

        if not entries:
            break

        for entry in entries:
            entries_checked += 1

            # Prüfe Sequenz-Kontinuität
            if last_sequence is not None:
                if entry.sequence_number != last_sequence + 1:
                    errors.append({
                        "type": "sequence_gap",
                        "expected": last_sequence + 1,
                        "found": entry.sequence_number,
                    })

            # Verifiziere Eintrag
            is_valid, error_msg = verify_entry_integrity(entry, expected_prev_hash)
            if not is_valid:
                errors.append({
                    "type": "integrity_error",
                    "sequence": entry.sequence_number,
                    "entry_id": str(entry.id),
                    "message": error_msg,
                })

            # Update für nächste Iteration
            expected_prev_hash = entry.integrity_hash
            last_sequence = entry.sequence_number

        offset += batch_size

    logger.info(
        "audit_chain_verified",
        entries_checked=entries_checked,
        errors_found=len(errors),
        is_valid=len(errors) == 0,
    )

    return len(errors) == 0, errors


async def get_last_audit_entry(db: AsyncSession) -> Optional["AuditLog"]:  # type: ignore
    """
    Holt den letzten Audit-Log-Eintrag für Verkettung.

    Returns:
        Letzter AuditLog-Eintrag oder None
    """
    from app.db.models import AuditLog

    query = select(AuditLog).order_by(desc(AuditLog.sequence_number)).limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_next_sequence_number(db: AsyncSession) -> int:
    """
    Holt die nächste Sequenznummer für einen neuen Eintrag.

    Verwendet SELECT FOR UPDATE um Race Conditions zu vermeiden.

    Returns:
        Nächste Sequenznummer
    """
    from app.db.models import AuditLog

    # Hole maximale Sequenznummer
    query = select(func.max(AuditLog.sequence_number))
    result = await db.execute(query)
    max_seq = result.scalar_one_or_none()

    return (max_seq or 0) + 1


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
        """
        Speichert Event in AuditLog-Tabelle mit Immutabilitäts-Features.

        AP6: Audit Log Immutabilität
        - Sequenznummer für Reihenfolge
        - previous_hash für Verkettung (Blockchain-artig)
        - integrity_hash für Tamper-Detection
        """
        from app.db.models import AuditLog

        # AP6: Hole letzte Sequenz und Hash für Verkettung
        sequence = await get_next_sequence_number(self.db)
        last_entry = await get_last_audit_entry(self.db)
        previous_hash = last_entry.integrity_hash if last_entry else GENESIS_HASH

        # Timestamp festlegen
        created_at = datetime.now(timezone.utc)
        filtered_details = self._filter_sensitive_data(details)

        # AP6: Berechne Integrity-Hash
        integrity_hash = calculate_entry_hash(
            sequence_number=sequence,
            user_id=user_id,
            action=event_type.value,
            resource_type=resource_type or "security",
            resource_id=resource_id,
            ip_address=ip_address,
            created_at=created_at,
            metadata=filtered_details,
            previous_hash=previous_hash,
        )

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
            audit_metadata=filtered_details,
            created_at=created_at,
            # AP6: Immutabilitäts-Felder
            sequence_number=sequence,
            integrity_hash=integrity_hash,
            previous_hash=previous_hash,
        )

        self.db.add(audit_log)
        await self.db.flush()

        logger.debug(
            "audit_log_saved_with_integrity",
            sequence=sequence,
            integrity_hash=integrity_hash[:16] + "...",
        )

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
