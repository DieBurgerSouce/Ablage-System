"""
Document Repository für Dokumenten-spezifische Datenbankoperationen.

Erweitert BaseRepository um dokument-spezifische Queries.
"""

from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.repositories.base import BaseRepository
from app.db.models import Document, ProcessingStatus, Tag

logger = structlog.get_logger(__name__)


class DocumentRepository(BaseRepository[Document]):
    """
    Repository für Dokumenten-Operationen.

    Erweitert BaseRepository um:
    - Benutzer-spezifische Queries
    - Status-Filter
    - Volltextsuche
    - Statistiken
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert das Document Repository."""
        super().__init__(db, Document)

    async def get_by_owner(
        self,
        owner_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
        status: Optional[ProcessingStatus] = None,
        include_deleted: bool = False
    ) -> List[Document]:
        """
        Lädt alle Dokumente eines Benutzers.

        Args:
            owner_id: Benutzer-ID
            skip: Offset für Pagination
            limit: Maximale Anzahl
            status: Optionaler Status-Filter
            include_deleted: Gelöschte einbeziehen (default: False)

        Returns:
            Liste von Dokumenten
        """
        # N+1 Query Fix: Eager load tags to avoid separate query per document
        query = select(Document).where(Document.owner_id == owner_id).options(
            selectinload(Document.tags)
        )

        if not include_deleted:
            query = query.where(
                Document.deleted_at.is_(None)
            )

        if status:
            query = query.where(Document.status == status)

        query = query.order_by(Document.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_checksum(self, checksum: str) -> Optional[Document]:
        """
        Findet Dokument nach Checksum (Duplikatserkennung).

        Args:
            checksum: SHA256-Hash des Dokuments

        Returns:
            Dokument oder None
        """
        result = await self.db.execute(
            select(Document).where(Document.checksum == checksum)
        )
        return result.scalar_one_or_none()

    async def get_pending_processing(
        self,
        limit: int = 10,
        backend: Optional[str] = None
    ) -> List[Document]:
        """
        Lädt Dokumente, die auf Verarbeitung warten.

        Args:
            limit: Maximale Anzahl
            backend: Optionaler Backend-Filter

        Returns:
            Liste von Dokumenten
        """
        # N+1 FIX: Eager loading für häufig genutzte Relationships
        query = select(Document).where(
            Document.status == ProcessingStatus.PENDING
        ).options(
            selectinload(Document.tags),
            selectinload(Document.owner)
        )

        if backend:
            query = query.where(
                Document.document_metadata["ocr_backend_requested"].astext == backend
            )

        query = query.order_by(Document.created_at.asc())
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_by_owner(
        self,
        owner_id: UUID,
        status: Optional[ProcessingStatus] = None
    ) -> int:
        """
        Zählt Dokumente eines Benutzers.

        Args:
            owner_id: Benutzer-ID
            status: Optionaler Status-Filter

        Returns:
            Anzahl der Dokumente
        """
        query = select(func.count()).select_from(Document).where(
            Document.owner_id == owner_id
        )

        if status:
            query = query.where(Document.status == status)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_processing_stats(self, owner_id: Optional[UUID] = None) -> dict:
        """
        Ermittelt Verarbeitungsstatistiken.

        Args:
            owner_id: Optionale Benutzer-ID (None = global)

        Returns:
            Dictionary mit Statistiken
        """
        base_query = select(
            Document.status,
            func.count().label("count")
        )

        if owner_id:
            base_query = base_query.where(Document.owner_id == owner_id)

        base_query = base_query.group_by(Document.status)

        result = await self.db.execute(base_query)
        rows = result.all()

        stats = {
            "total": 0,
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
        }

        for row in rows:
            status_str = row.status.value if hasattr(row.status, 'value') else str(row.status)
            stats[status_str] = row.count
            stats["total"] += row.count

        return stats

    async def search_by_text(
        self,
        query_text: str,
        owner_id: Optional[UUID] = None,
        limit: int = 20
    ) -> List[Document]:
        """
        Volltextsuche in extrahiertem Text.

        Args:
            query_text: Suchbegriff
            owner_id: Optionaler Owner-Filter
            limit: Maximale Anzahl

        Returns:
            Liste von Dokumenten
        """
        # N+1 FIX: Eager loading für Suchresultate
        # Einfache ILIKE-Suche (für komplexere Suche: pg_trgm oder tsvector)
        query = select(Document).where(
            Document.extracted_text.ilike(f"%{query_text}%")
        ).options(
            selectinload(Document.tags),
            selectinload(Document.owner)
        )

        if owner_id:
            query = query.where(Document.owner_id == owner_id)

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_document_type(
        self,
        document_type: str,
        owner_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[Document]:
        """
        Lädt Dokumente nach Typ.

        Args:
            document_type: Dokumententyp (invoice, contract, etc.)
            owner_id: Optionaler Owner-Filter
            limit: Maximale Anzahl

        Returns:
            Liste von Dokumenten
        """
        # N+1 FIX: Eager loading für Typ-Abfragen
        query = select(Document).where(
            Document.document_type == document_type
        ).options(
            selectinload(Document.tags),
            selectinload(Document.owner)
        )

        if owner_id:
            query = query.where(Document.owner_id == owner_id)

        query = query.order_by(Document.created_at.desc())
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def soft_delete(self, id: UUID, deleted_by: UUID) -> bool:
        """
        Soft-Delete eines Dokuments (GDPR-konform).

        Args:
            id: Dokument-ID
            deleted_by: ID des löschenden Benutzers

        Returns:
            True wenn erfolgreich
        """
        doc = await self.get_by_id(id)
        if not doc:
            return False

        doc.is_deleted = True
        doc.deleted_at = datetime.now(timezone.utc)
        doc.deleted_by_id = deleted_by

        await self.db.commit()

        logger.info(
            "document_soft_deleted",
            document_id=str(id),
            deleted_by=str(deleted_by)
        )

        return True

    async def restore(self, id: UUID) -> bool:
        """
        Stellt ein soft-deleted Dokument wieder her.

        Args:
            id: Dokument-ID

        Returns:
            True wenn erfolgreich
        """
        doc = await self.get_by_id(id)
        if not doc or not doc.is_deleted:
            return False

        doc.is_deleted = False
        doc.deleted_at = None
        doc.deleted_by_id = None

        await self.db.commit()

        logger.info(
            "document_restored",
            document_id=str(id)
        )

        return True

    async def get_with_embeddings(
        self,
        owner_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[Document]:
        """
        Lädt Dokumente mit vorhandenen Embeddings.

        Args:
            owner_id: Optionaler Owner-Filter
            limit: Maximale Anzahl

        Returns:
            Liste von Dokumenten
        """
        # N+1 FIX: Eager loading für häufig genutzte Relationships
        query = select(Document).where(
            Document.embedding.isnot(None)
        ).options(
            selectinload(Document.tags),
            selectinload(Document.owner)
        )

        if owner_id:
            query = query.where(Document.owner_id == owner_id)

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_without_embeddings(
        self,
        status: ProcessingStatus = ProcessingStatus.COMPLETED,
        limit: int = 100
    ) -> List[Document]:
        """
        Lädt Dokumente ohne Embeddings (für Batch-Generierung).

        Args:
            status: Filter nach Status (default: COMPLETED)
            limit: Maximale Anzahl

        Returns:
            Liste von Dokumenten
        """
        query = select(Document).where(
            and_(
                Document.status == status,
                Document.embedding.is_(None),
                Document.extracted_text.isnot(None)
            )
        )

        query = query.order_by(Document.created_at.asc())
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())
