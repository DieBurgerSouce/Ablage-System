"""
GDPR Compliance Service - Art. 17 Löschrecht Implementation.

Implementiert das "Recht auf Löschung" (Right to Erasure) gemäß DSGVO Art. 17.

Features:
- Löschantrag einreichen mit 30-Tage-Frist
- Löschantrag zurückziehen
- Automatische Löschung nach Fristablauf
- Dokumenten-Anonymisierung/Löschung
- Audit-Log-Anonymisierung (nicht Löschung für Compliance)

Feinpoliert und durchdacht - DSGVO-konform.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload

from app.db.models import User, Document, APIKey, AuditLog
from app.core.exceptions import GDPRError, UserNotFoundError

logger = structlog.get_logger(__name__)

# GDPR Configuration
DELETION_GRACE_PERIOD_DAYS = 30  # 30 Tage Widerrufsfrist
REMINDER_DAYS_BEFORE = 7  # 7 Tage vor Löschung erinnern


class GDPRService:
    """Service für DSGVO-konforme Datenverwaltung."""

    async def request_deletion(
        self,
        db: AsyncSession,
        user_id: UUID,
        reason: Optional[str] = None
    ) -> datetime:
        """
        Art. 17 DSGVO - Löschantrag einreichen.

        Args:
            db: Database session
            user_id: User UUID
            reason: Optionaler Löschgrund

        Returns:
            Geplanter Löschzeitpunkt (30 Tage)

        Raises:
            UserNotFoundError: User nicht gefunden
            GDPRError: Bereits Löschantrag vorhanden
        """
        user = await db.get(User, user_id)
        if not user:
            raise UserNotFoundError(str(user_id))

        if user.deletion_requested_at:
            scheduled_date = user.deletion_scheduled_for
            if scheduled_date:
                formatted_date = scheduled_date.strftime('%d.%m.%Y')
                raise GDPRError(
                    f"Löschantrag bereits vorhanden. Geplante Löschung: {formatted_date}"
                )
            raise GDPRError("Löschantrag bereits vorhanden")

        now = datetime.now(timezone.utc)
        scheduled_deletion = now + timedelta(days=DELETION_GRACE_PERIOD_DAYS)

        user.deletion_requested_at = now
        user.deletion_scheduled_for = scheduled_deletion
        user.deletion_reason = reason
        user.deletion_confirmed = True

        await db.commit()

        logger.info(
            "gdpr_deletion_requested",
            user_id=str(user_id)[:8] + "...",
            scheduled_for=scheduled_deletion.isoformat(),
            reason=reason[:50] if reason else None
        )

        return scheduled_deletion

    async def cancel_deletion(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> bool:
        """
        Löschantrag zurückziehen (innerhalb der 30-Tage-Frist).

        Args:
            db: Database session
            user_id: User UUID

        Returns:
            True wenn erfolgreich

        Raises:
            GDPRError: Kein Antrag vorhanden oder Frist abgelaufen
        """
        user = await db.get(User, user_id)
        if not user or not user.deletion_requested_at:
            raise GDPRError("Kein aktiver Löschantrag vorhanden")

        now = datetime.now(timezone.utc)
        if user.deletion_scheduled_for and now >= user.deletion_scheduled_for:
            raise GDPRError("Löschfrist bereits abgelaufen, Abbruch nicht möglich")

        user.deletion_requested_at = None
        user.deletion_scheduled_for = None
        user.deletion_reason = None
        user.deletion_confirmed = False

        await db.commit()

        logger.info("gdpr_deletion_cancelled", user_id=str(user_id)[:8] + "...")
        return True

    async def get_deletion_status(
        self,
        user: User
    ) -> Dict[str, Any]:
        """
        Gibt den aktuellen Löschstatus zurück.

        Args:
            user: User Objekt

        Returns:
            Dict mit Löschstatus-Informationen
        """
        if not user.deletion_requested_at:
            return {
                "deletion_requested": False,
                "deletion_requested_at": None,
                "deletion_scheduled_for": None,
                "days_remaining": None,
                "can_cancel": False,
                "nachricht": "Kein aktiver Löschantrag vorhanden"
            }

        now = datetime.now(timezone.utc)
        if user.deletion_scheduled_for:
            days_remaining = (user.deletion_scheduled_for - now).days
            can_cancel = days_remaining > 0
            formatted_date = user.deletion_scheduled_for.strftime('%d.%m.%Y')
        else:
            days_remaining = None
            can_cancel = False
            formatted_date = "unbekannt"

        return {
            "deletion_requested": True,
            "deletion_requested_at": user.deletion_requested_at,
            "deletion_scheduled_for": user.deletion_scheduled_for,
            "days_remaining": max(0, days_remaining) if days_remaining is not None else None,
            "can_cancel": can_cancel,
            "nachricht": f"Löschung geplant für {formatted_date}"
        }

    async def execute_deletion(
        self,
        db: AsyncSession,
        user_id: UUID,
        hard_delete: bool = False
    ) -> Dict[str, Any]:
        """
        Führt die eigentliche Löschung durch.

        Args:
            db: Database session
            user_id: User UUID
            hard_delete: True = physische Löschung, False = Anonymisierung

        Returns:
            Dict mit Löschstatistiken
        """
        user = await db.get(User, user_id)
        if not user:
            raise UserNotFoundError(str(user_id))

        stats: Dict[str, int] = {
            "documents": 0,
            "api_keys": 0,
            "audit_logs": 0
        }

        # 1. Dokumente löschen/anonymisieren
        docs_result = await db.execute(
            select(Document).where(Document.owner_id == user_id)
        )
        documents = docs_result.scalars().all()
        stats["documents"] = len(documents)

        for doc in documents:
            if hard_delete:
                # TODO: MinIO-Datei löschen via storage_service
                # await storage_service.delete_file(doc.file_path)
                await db.delete(doc)
            else:
                # Soft-Delete / Anonymisierung
                doc.deleted_at = datetime.now(timezone.utc)
                doc.deleted_by_id = user_id
                doc.extracted_text = "[GELÖSCHT - GDPR Art. 17]"
                doc.document_metadata = {}
                doc.filename = f"deleted_{doc.id}"
                doc.original_filename = "[GELÖSCHT]"

        # 2. API Keys löschen
        api_keys_result = await db.execute(
            delete(APIKey).where(APIKey.user_id == user_id)
        )
        stats["api_keys"] = api_keys_result.rowcount

        # 3. Audit Logs anonymisieren (nicht löschen für Compliance)
        audit_result = await db.execute(
            select(AuditLog).where(AuditLog.user_id == user_id)
        )
        audit_logs = audit_result.scalars().all()
        stats["audit_logs"] = len(audit_logs)

        for log in audit_logs:
            log.user_id = None  # Anonymisieren
            log.ip_address = "0.0.0.0"
            log.user_agent = "[ANONYMISIERT - GDPR]"

        # 4. User löschen/anonymisieren
        if hard_delete:
            await db.delete(user)
        else:
            # Anonymisierung gemäß DSGVO
            user.email = f"deleted_{user_id}@anonymized.gdpr.local"
            user.username = f"deleted_{str(user_id)[:8]}"
            user.full_name = "[GELÖSCHT]"
            user.hashed_password = "DELETED_GDPR_ART17"
            user.is_active = False
            user.totp_secret = None
            user.totp_backup_codes = None
            user.totp_enabled = False
            user.deletion_requested_at = None
            user.deletion_scheduled_for = None
            user.deletion_confirmed = False

        await db.commit()

        logger.info(
            "gdpr_deletion_executed",
            user_id=str(user_id)[:8] + "...",
            hard_delete=hard_delete,
            stats=stats
        )

        return stats

    async def get_pending_deletions(
        self,
        db: AsyncSession
    ) -> List[User]:
        """
        Gibt alle User mit fälligen Löschanträgen zurück.

        Für den Celery-Task zur automatischen Löschung.

        Returns:
            Liste von Usern mit abgelaufener Löschfrist
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(User).where(
                User.deletion_scheduled_for <= now,
                User.deletion_confirmed == True
            )
        )
        return list(result.scalars().all())

    async def get_upcoming_deletions(
        self,
        db: AsyncSession,
        days_ahead: int = REMINDER_DAYS_BEFORE
    ) -> List[User]:
        """
        Gibt User zurück, deren Löschung in X Tagen ansteht.

        Für Erinnerungs-Emails.

        Args:
            db: Database session
            days_ahead: Tage vorher (default: 7)

        Returns:
            Liste von Usern
        """
        now = datetime.now(timezone.utc)
        reminder_date = now + timedelta(days=days_ahead)

        result = await db.execute(
            select(User).where(
                User.deletion_scheduled_for >= now,
                User.deletion_scheduled_for <= reminder_date,
                User.deletion_confirmed == True
            )
        )
        return list(result.scalars().all())


# Singleton-Instanz
_gdpr_service: Optional[GDPRService] = None


def get_gdpr_service() -> GDPRService:
    """Get global GDPR Service instance."""
    global _gdpr_service
    if _gdpr_service is None:
        _gdpr_service = GDPRService()
    return _gdpr_service
