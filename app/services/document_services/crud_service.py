"""Document CRUD Service - Basis-Operationen.

Enthaelt:
- get_document: Einzelnes Dokument abrufen
- list_documents: Dokumente mit Filterung und Pagination auflisten
- update_document: Dokumentmetadaten aktualisieren
- partial_update_document: Partielle Aktualisierung (PATCH)
- delete_document: Dokument loeschen (hard delete)
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document
from app.db.schemas import (
    SearchFilters,
    SortField,
    SortOrder,
    DocumentType,
    DocumentDetailResponse,
    DocumentListResponseExtended,
)
from app.services.document_services.base import DocumentServiceBase
from app.services.document_services.filter_service import get_filter_service

logger = structlog.get_logger(__name__)


class DocumentCRUDService(DocumentServiceBase):
    """Service fuer Basis-CRUD-Operationen auf Dokumenten.

    Bietet standardmaessige Lese-, Schreib- und Loeschoperationen
    mit Unterstuetzung fuer Filterung und Pagination.
    """

    def __init__(self):
        """Initialisiere den CRUD-Service mit Filter-Service."""
        self._filter_service = get_filter_service()

    async def get_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID
    ) -> Optional[DocumentDetailResponse]:
        """Einzelnes Dokument mit allen Details abrufen.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            user_id: ID des Benutzers (fuer Zugriffskontrolle)

        Returns:
            DocumentDetailResponse oder None wenn nicht gefunden
        """
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(Document.id == document_id, Document.owner_id == user_id))
        )

        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        return self._to_detail_response(doc)

    async def list_documents(
        self,
        db: AsyncSession,
        user_id: UUID,
        filters: Optional[SearchFilters] = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: SortField = SortField.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC
    ) -> DocumentListResponseExtended:
        """Dokumente mit Filterung und Pagination auflisten.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers
            filters: Optionale Filterkriterien
            page: Seitennummer (1-basiert)
            per_page: Eintraege pro Seite
            sort_by: Sortierfeld
            sort_order: Sortierrichtung

        Returns:
            DocumentListResponseExtended mit paginierten Ergebnissen
        """
        # Basis-Query
        query = select(Document).where(Document.owner_id == user_id)
        count_query = select(func.count(Document.id)).where(Document.owner_id == user_id)

        # Filter anwenden
        if filters:
            filter_conditions = self._filter_service.build_filter_conditions(filters)
            if filter_conditions:
                query = query.where(and_(*filter_conditions))
                count_query = count_query.where(and_(*filter_conditions))

        # Sortierung
        sort_column = self._filter_service.get_sort_column(sort_by)
        if sort_order == SortOrder.DESC:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Tags laden
        query = query.options(selectinload(Document.tags))

        # Ausfuehren
        result = await db.execute(query)
        documents = result.scalars().all()

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        total_pages = math.ceil(total / per_page) if total > 0 else 0

        return DocumentListResponseExtended(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
            documents=[self._to_summary(doc) for doc in documents],
            filters_applied=filters.model_dump(exclude_none=True) if filters else {}
        )

    async def update_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID,
        document_type: Optional[DocumentType] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Optional[DocumentDetailResponse]:
        """Dokumentmetadaten aktualisieren.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            user_id: ID des Benutzers
            document_type: Neuer Dokumenttyp
            language: Neue Sprache
            tags: Neue Tags (ersetzt alle)
            metadata: Neue Metadaten (wird gemergt)

        Returns:
            Aktualisiertes DocumentDetailResponse oder None
        """
        # Dokument laden
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(Document.id == document_id, Document.owner_id == user_id))
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Felder aktualisieren
        if document_type is not None:
            doc.document_type = document_type.value

        if language is not None:
            doc.detected_language = language

        if metadata is not None:
            current_meta = doc.document_metadata or {}
            current_meta.update(metadata)
            doc.document_metadata = current_meta

        # Tags aktualisieren
        if tags is not None:
            await self._update_document_tags(db, doc, tags)

        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(doc)

        logger.info(
            "document_updated",
            document_id=str(document_id),
            user_id=str(user_id)
        )

        # Such-Caches invalidieren
        await self._invalidate_document_cache(document_id, user_id, reason="document_update")

        return self._to_detail_response(doc)

    async def partial_update_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID,
        updates: Dict[str, Any],
        tag_operation: Optional[str] = None,
        tag_values: Optional[List[str]] = None
    ) -> Optional[DocumentDetailResponse]:
        """Partielle Dokumentaktualisierung (PATCH).

        Aktualisiert nur die angegebenen Felder.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            user_id: Benutzer-ID
            updates: Dictionary mit Feldname -> Wert
            tag_operation: "set", "add", oder "remove"
            tag_values: Tags fuer die Operation

        Returns:
            Aktualisiertes DocumentDetailResponse oder None
        """
        # Dokument laden
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(Document.id == document_id, Document.owner_id == user_id))
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Felder aktualisieren
        if "document_type" in updates:
            doc.document_type = (
                updates["document_type"].value
                if hasattr(updates["document_type"], 'value')
                else updates["document_type"]
            )

        if "language" in updates:
            doc.detected_language = updates["language"]

        if "metadata" in updates:
            current_meta = doc.document_metadata or {}
            current_meta.update(updates["metadata"])
            doc.document_metadata = current_meta

        # Tag-Operationen
        if tag_operation and tag_values is not None:
            if tag_operation == "set":
                # Alle Tags ersetzen
                await self._update_document_tags(db, doc, tag_values)
            elif tag_operation == "add":
                # Tags hinzufuegen
                current_tag_names = [t.name for t in doc.tags]
                new_tag_names = list(set(current_tag_names + tag_values))
                await self._update_document_tags(db, doc, new_tag_names)
            elif tag_operation == "remove":
                # Tags entfernen
                current_tag_names = [t.name for t in doc.tags]
                remaining_tags = [t for t in current_tag_names if t not in tag_values]
                await self._update_document_tags(db, doc, remaining_tags)

        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(doc)

        logger.info(
            "document_partial_updated",
            document_id=str(document_id),
            user_id=str(user_id),
            updates=list(updates.keys()),
            tag_operation=tag_operation
        )

        # Such-Caches invalidieren
        await self._invalidate_document_cache(document_id, user_id, reason="partial_update")

        return self._to_detail_response(doc)

    async def delete_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID
    ) -> bool:
        """Dokument permanent loeschen (Hard Delete).

        Fuer GDPR-konformes Soft-Delete siehe DocumentGDPRService.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            user_id: ID des Benutzers

        Returns:
            True wenn erfolgreich, False wenn nicht gefunden
        """
        # Pruefen ob Dokument existiert und Benutzer berechtigt ist
        query = select(Document).where(
            and_(Document.id == document_id, Document.owner_id == user_id)
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return False

        # Dokument loeschen (CASCADE loescht Tags-Verknuepfungen)
        await db.delete(doc)
        await db.commit()

        logger.info(
            "document_deleted",
            document_id=str(document_id),
            user_id=str(user_id)
        )

        # Caches invalidieren
        await self._invalidate_document_cache(document_id, user_id, reason="document_delete")
        await self._invalidate_central_cache(str(document_id), change_type="delete")

        return True


# Singleton-Instanz
_crud_service_instance: DocumentCRUDService = None


def get_crud_service() -> DocumentCRUDService:
    """CRUD-Service-Instanz abrufen (Singleton)."""
    global _crud_service_instance
    if _crud_service_instance is None:
        _crud_service_instance = DocumentCRUDService()
    return _crud_service_instance
