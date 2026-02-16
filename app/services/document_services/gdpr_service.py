"""Document GDPR Service - Soft-Delete und Datenschutz.

Enthält GDPR-konforme Operationen:
- soft_delete_document: Dokument als gelöscht markieren
- restore_document: Soft-gelöschtes Dokument wiederherstellen
- list_deleted_documents: Gelöschte Dokumente auflisten
- permanently_delete_expired: Abgelaufene Dokumente löschen
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.db.schemas import (
    DocumentType,
    SoftDeleteResponse,
    RestoreDocumentResponse,
    DeletedDocumentSummary,
    DeletedDocumentsListResponse,
)
from app.services.document_services.base import DocumentServiceBase

logger = structlog.get_logger(__name__)


class DocumentGDPRService(DocumentServiceBase):
    """Service für GDPR-konforme Dokumentverwaltung.

    Implementiert Soft-Delete-Logik mit 30-Tage-Wiederherstellungsfrist
    gemäß GDPR-Anforderungen.
    """

    async def soft_delete_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None
    ) -> Optional[SoftDeleteResponse]:
        """Dokument soft-löschen (GDPR-konform).

        Markiert Dokument als gelöscht, entfernt es aber nicht.
        Nach 30 Tagen wird es permanent gelöscht (via Scheduled Task).

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            user_id: ID des Benutzers
            reason: Optionaler Löschgrund

        Returns:
            SoftDeleteResponse oder None wenn nicht gefunden
        """
        query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.owner_id == user_id,
                Document.deleted_at.is_(None)  # Noch nicht gelöscht
            )
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        now = datetime.now(timezone.utc)
        doc.deleted_at = now
        doc.deleted_by_id = user_id

        # Grund in Metadaten speichern
        if reason:
            meta = doc.document_metadata or {}
            meta["deletion_reason"] = reason
            doc.document_metadata = meta

        await db.commit()

        logger.info(
            "document_soft_deleted",
            document_id=str(document_id),
            user_id=str(user_id),
            reason=reason
        )

        # Such-Caches invalidieren
        await self._invalidate_document_cache(document_id, user_id, reason="soft_delete")
        await self._invalidate_central_cache(str(document_id), change_type="delete")

        return SoftDeleteResponse(
            document_id=doc.id,
            deleted_at=doc.deleted_at,
            deleted_by_id=doc.deleted_by_id,
            can_restore_until=now + timedelta(days=30)
        )

    async def restore_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID
    ) -> Optional[RestoreDocumentResponse]:
        """Soft-gelöschtes Dokument wiederherstellen.

        Stellt ein gelöschtes Dokument wieder her,
        solange die 30-Tage-Frist nicht abgelaufen ist.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            user_id: ID des Benutzers

        Returns:
            RestoreDocumentResponse oder None wenn nicht gefunden

        Raises:
            ValueError: Wenn die 30-Tage-Frist abgelaufen ist
        """
        # Nur gelöschte Dokumente des Benutzers finden
        query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.owner_id == user_id,
                Document.deleted_at.isnot(None)
            )
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Prüfen ob 30-Tage-Frist noch nicht abgelaufen
        days_since_deletion = (datetime.now(timezone.utc) - doc.deleted_at).days
        if days_since_deletion > 30:
            raise ValueError(
                f"Wiederherstellung nicht mehr möglich. "
                f"Dokument wurde vor {days_since_deletion} Tagen gelöscht."
            )

        now = datetime.now(timezone.utc)
        doc.deleted_at = None
        doc.deleted_by_id = None

        # Löschgrund aus Metadaten entfernen
        if doc.document_metadata and "deletion_reason" in doc.document_metadata:
            meta = doc.document_metadata.copy()
            del meta["deletion_reason"]
            doc.document_metadata = meta

        doc.updated_at = now
        await db.commit()

        logger.info(
            "document_restored",
            document_id=str(document_id),
            user_id=str(user_id)
        )

        return RestoreDocumentResponse(
            document_id=doc.id,
            restored_at=now
        )

    async def list_deleted_documents(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> DeletedDocumentsListResponse:
        """Alle soft-gelöschten Dokumente eines Benutzers auflisten.

        Zeigt gelöschte Dokumente mit Restzeit bis zur
        permanenten Löschung.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers

        Returns:
            DeletedDocumentsListResponse mit gelöschten Dokumenten
        """
        query = (
            select(Document)
            .where(
                and_(
                    Document.owner_id == user_id,
                    Document.deleted_at.isnot(None)
                )
            )
            .order_by(Document.deleted_at.desc())
        )
        result = await db.execute(query)
        documents = result.scalars().all()

        now = datetime.now(timezone.utc)
        summaries = []

        for doc in documents:
            days_since = (now - doc.deleted_at).days
            days_until_permanent = max(0, 30 - days_since)

            summaries.append(DeletedDocumentSummary(
                id=doc.id,
                filename=doc.filename,
                document_type=DocumentType(doc.document_type) if doc.document_type else DocumentType.OTHER,
                deleted_at=doc.deleted_at,
                deleted_by_id=doc.deleted_by_id,
                days_until_permanent_deletion=days_until_permanent,
                can_restore=days_until_permanent > 0
            ))

        return DeletedDocumentsListResponse(
            total=len(summaries),
            documents=summaries
        )

    async def permanently_delete_expired(
        self,
        db: AsyncSession,
        days_threshold: int = 30
    ) -> int:
        """Permanent löscht alle Dokumente, deren Soft-Delete abgelaufen ist.

        Sollte als Scheduled Task laufen (z.B. täglich um 03:00).

        Args:
            db: Datenbank-Session
            days_threshold: Anzahl Tage nach Soft-Delete (Standard: 30)

        Returns:
            Anzahl permanent gelöschter Dokumente
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        # Alle abgelaufenen Dokumente finden
        query = select(Document).where(
            and_(
                Document.deleted_at.isnot(None),
                Document.deleted_at < cutoff_date
            )
        )
        result = await db.execute(query)
        documents = result.scalars().all()

        count = len(documents)

        for doc in documents:
            await db.delete(doc)

        if count > 0:
            await db.commit()
            logger.info(
                "expired_documents_permanently_deleted",
                count=count,
                threshold_days=days_threshold
            )

        return count

    async def get_retention_info(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID
    ) -> Optional[dict]:
        """Gibt Informationen zur Aufbewahrungsfrist eines Dokuments zurück.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            user_id: ID des Benutzers

        Returns:
            Dict mit Aufbewahrungsinformationen oder None wenn nicht gefunden
        """
        query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.owner_id == user_id
            )
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        now = datetime.now(timezone.utc)

        if doc.deleted_at is None:
            return {
                "document_id": doc.id,
                "is_deleted": False,
                "can_restore": False,
                "deleted_at": None,
                "deletion_reason": None,
                "days_until_permanent_deletion": None
            }

        days_since = (now - doc.deleted_at).days
        days_until_permanent = max(0, 30 - days_since)
        deletion_reason = (
            doc.document_metadata.get("deletion_reason")
            if doc.document_metadata else None
        )

        return {
            "document_id": doc.id,
            "is_deleted": True,
            "can_restore": days_until_permanent > 0,
            "deleted_at": doc.deleted_at,
            "deletion_reason": deletion_reason,
            "days_until_permanent_deletion": days_until_permanent,
            "permanent_deletion_date": doc.deleted_at + timedelta(days=30)
        }


# Singleton-Instanz
_gdpr_service_instance: DocumentGDPRService = None


def get_gdpr_service() -> DocumentGDPRService:
    """GDPR-Service-Instanz abrufen (Singleton)."""
    global _gdpr_service_instance
    if _gdpr_service_instance is None:
        _gdpr_service_instance = DocumentGDPRService()
    return _gdpr_service_instance
