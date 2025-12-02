"""Document-Service fuer CRUD-Operationen und Batch-Verarbeitung.

Zentrale Service-Schicht fuer Dokumentenverwaltung mit Unterstuetzung
fuer Filterung, Pagination und Batch-Operationen.

NOTE: Dieses Modul delegiert nun an spezialisierte Services:
- DocumentGDPRService: Soft-Delete, Restore, Permanent-Delete
- DocumentBatchService: Batch-Delete, Batch-Tag, Bulk-Update
- DocumentExportService: JSON, CSV, ZIP, PDF Export
"""

from typing import Any, List, Optional, Dict, Tuple
from datetime import datetime, timezone
from uuid import UUID
from functools import lru_cache
import math

import structlog
from sqlalchemy import select, func, and_, or_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Tag, User, document_tags, ProcessingStatus
from app.db.schemas import (
    SearchFilters, SortField, SortOrder, DocumentType, ProcessingStatus as SchemaProcessingStatus,
    DocumentSummary, DocumentDetailResponse, DocumentListResponseExtended,
    BatchOperationResult, BatchOperationError, BatchExportResult, ExportFormat,
    TagOperation, TagResponse,
    DocumentFilterForBulkUpdate, DocumentPartialUpdateRequest, BulkUpdateResult,
    SoftDeleteResponse, RestoreDocumentResponse, DeletedDocumentSummary, DeletedDocumentsListResponse
)
from datetime import timedelta
from app.core.config import settings
from app.core.cache import invalidate_on_document_change

# Split Service imports
from app.services.document_gdpr_service import (
    DocumentGDPRService,
    get_document_gdpr_service
)
from app.services.document_batch_service import (
    DocumentBatchService,
    get_document_batch_service
)
from app.services.document_export_service import (
    DocumentExportService,
    get_document_export_service
)

logger = structlog.get_logger(__name__)


# Thread-safe search service access using contextvars for async safety
import asyncio
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.search_service import SearchService

# Context variable for async-safe search service access
_search_service_ctx: ContextVar[Optional["SearchService"]] = ContextVar(
    "_search_service_ctx", default=None
)


def _get_search_service() -> Optional["SearchService"]:
    """Get SearchService instance - async-safe with lazy loading.

    Uses contextvars for thread/async safety instead of global state.
    Falls back to creating instance if not in context (backwards compatible).
    """
    service = _search_service_ctx.get()
    if service is None:
        try:
            from app.services.search_service import get_search_service
            service = get_search_service()
            _search_service_ctx.set(service)
        except ImportError as e:
            logger.warning(
                "search_service_import_failed",
                error_type="ImportError",
                error=str(e)
            )
            return None
    return service


def set_search_service(service: "SearchService") -> None:
    """Inject SearchService instance for current async context.

    Used for dependency injection in tests or application setup.
    """
    _search_service_ctx.set(service)


class DocumentService:
    """Service fuer Dokumentenverwaltung.

    Bietet CRUD-Operationen, Filterung, Pagination und Batch-Operationen.

    NOTE: Delegiert an spezialisierte Services fuer:
    - GDPR-Operationen (soft_delete, restore)
    - Batch-Operationen (batch_delete, batch_tag, bulk_update)
    - Export-Operationen (batch_export)
    """

    def __init__(self) -> None:
        """Initialisiert DocumentService mit Split-Services."""
        self._gdpr_service: Optional[DocumentGDPRService] = None
        self._batch_service: Optional[DocumentBatchService] = None
        self._export_service: Optional[DocumentExportService] = None

    @property
    def gdpr_service(self) -> DocumentGDPRService:
        """Lazy-loaded GDPR Service."""
        if self._gdpr_service is None:
            self._gdpr_service = get_document_gdpr_service()
        return self._gdpr_service

    @property
    def batch_service(self) -> DocumentBatchService:
        """Lazy-loaded Batch Service."""
        if self._batch_service is None:
            self._batch_service = get_document_batch_service()
        return self._batch_service

    @property
    def export_service(self) -> DocumentExportService:
        """Lazy-loaded Export Service."""
        if self._export_service is None:
            self._export_service = get_document_export_service()
        return self._export_service

    async def get_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID
    ) -> Optional[DocumentDetailResponse]:
        """Einzelnes Dokument mit allen Details abrufen."""
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
        """Dokumente mit Filterung und Pagination auflisten."""
        # Basis-Query
        query = select(Document).where(Document.owner_id == user_id)
        count_query = select(func.count(Document.id)).where(Document.owner_id == user_id)

        # Filter anwenden
        if filters:
            filter_conditions = self._build_filter_conditions(filters)
            if filter_conditions:
                query = query.where(and_(*filter_conditions))
                count_query = count_query.where(and_(*filter_conditions))

        # Sortierung
        sort_column = self._get_sort_column(sort_by)
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
        """Dokumentmetadaten aktualisieren."""
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
        try:
            search_service = _get_search_service()
            await search_service.invalidate_document_cache(
                document_id, user_id, reason="document_update"
            )
        except Exception as e:
            logger.warning(
                "cache_invalidation_on_update_failed",
                document_id=str(document_id),
                error=str(e)
            )

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

        Phase 2.1: Aktualisiert nur die angegebenen Felder.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            user_id: Benutzer-ID
            updates: Dictionary mit Feldname -> Wert
            tag_operation: "set", "add", oder "remove"
            tag_values: Tags fuer die Operation
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
            doc.document_type = updates["document_type"].value if hasattr(updates["document_type"], 'value') else updates["document_type"]

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
        try:
            search_service = _get_search_service()
            await search_service.invalidate_document_cache(
                document_id, user_id, reason="partial_update"
            )
        except Exception as e:
            logger.warning(
                "cache_invalidation_failed",
                document_id=str(document_id),
                error=str(e)
            )

        return self._to_detail_response(doc)

    async def bulk_update(
        self,
        db: AsyncSession,
        user_id: UUID,
        filter_criteria: DocumentFilterForBulkUpdate,
        updates: DocumentPartialUpdateRequest,
        dry_run: bool = False
    ) -> BulkUpdateResult:
        """Bulk-Update fuer mehrere Dokumente.

        NOTE: Delegiert an DocumentBatchService.

        Phase 2.2: Aktualisiert Dokumente basierend auf Filterkriterien.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            filter_criteria: Filter fuer zu aktualisierende Dokumente
            updates: Anzuwendende Aenderungen
            dry_run: Nur simulieren, nicht ausfuehren
        """
        return await self.batch_service.bulk_update(
            db, user_id, filter_criteria, updates, dry_run
        )

    async def delete_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID
    ) -> bool:
        """Dokument loeschen."""
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

        # Such-Caches invalidieren
        try:
            search_service = _get_search_service()
            await search_service.invalidate_document_cache(
                document_id, user_id, reason="document_delete"
            )
        except Exception as e:
            logger.warning(
                "cache_invalidation_on_delete_failed",
                document_id=str(document_id),
                error=str(e)
            )

        # Zentrale Cache-Invalidation (Cascade: doc, search, facets, stats)
        try:
            await invalidate_on_document_change(str(document_id), change_type="delete")
        except Exception as e:
            logger.warning(
                "central_cache_invalidation_failed",
                document_id=str(document_id),
                error=str(e)
            )

        return True

    # ========== Soft-Delete Operationen (GDPR Phase 2.3) ==========
    # NOTE: Delegiert an DocumentGDPRService

    async def soft_delete_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None
    ) -> Optional[SoftDeleteResponse]:
        """Dokument soft-loeschen (GDPR-konform).

        Phase 2.3: Markiert Dokument als geloescht, entfernt es aber nicht.
        Nach 30 Tagen wird es permanent geloescht (via Scheduled Task).

        NOTE: Delegiert an DocumentGDPRService.
        """
        return await self.gdpr_service.soft_delete_document(
            db, document_id, user_id, reason
        )

    async def restore_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID
    ) -> Optional[RestoreDocumentResponse]:
        """Soft-geloeschtes Dokument wiederherstellen.

        Phase 2.3: Stellt ein geloeschtes Dokument wieder her,
        solange die 30-Tage-Frist nicht abgelaufen ist.

        NOTE: Delegiert an DocumentGDPRService.
        """
        return await self.gdpr_service.restore_document(db, document_id, user_id)

    async def list_deleted_documents(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> DeletedDocumentsListResponse:
        """Alle soft-geloeschten Dokumente eines Benutzers auflisten.

        Phase 2.3: Zeigt geloeschte Dokumente mit Restzeit bis zur
        permanenten Loeschung.

        NOTE: Delegiert an DocumentGDPRService.
        """
        return await self.gdpr_service.list_deleted_documents(db, user_id)

    async def permanently_delete_expired(
        self,
        db: AsyncSession,
        days_threshold: int = 30
    ) -> int:
        """Permanent loescht alle Dokumente, deren Soft-Delete abgelaufen ist.

        Phase 2.3: Sollte als Scheduled Task laufen.

        NOTE: Delegiert an DocumentGDPRService.

        Returns: Anzahl geloeschter Dokumente
        """
        return await self.gdpr_service.permanently_delete_expired(db, days_threshold)

    # ========== Batch-Operationen ==========
    # NOTE: Delegiert an DocumentBatchService

    async def batch_delete(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        user_id: UUID,
        dry_run: bool = False,
        soft_delete: bool = True
    ) -> BatchOperationResult:
        """Mehrere Dokumente loeschen (optimierte Bulk-Operation).

        NOTE: Delegiert an DocumentBatchService.

        Args:
            db: Datenbank-Session
            document_ids: Liste der zu loeschenden Dokument-IDs
            user_id: ID des ausfuehrenden Benutzers
            dry_run: Wenn True, wird nur simuliert (keine Loeschung)
            soft_delete: Wenn True (Standard), Soft-Delete fuer GDPR-Konformitaet

        Returns:
            BatchOperationResult mit Statistiken
        """
        return await self.batch_service.batch_delete(
            db, document_ids, user_id, dry_run, soft_delete
        )

    async def batch_tag(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        tags: List[str],
        user_id: UUID,
        operation: TagOperation = TagOperation.ADD
    ) -> BatchOperationResult:
        """Tags fuer mehrere Dokumente setzen - optimiert mit Bulk-Loading.

        NOTE: Delegiert an DocumentBatchService.

        TRANSAKTIONSSICHER: Bei Fehlern wird Rollback durchgefuehrt.
        """
        return await self.batch_service.batch_tag(
            db, document_ids, tags, user_id, operation
        )

    async def batch_export(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        user_id: UUID,
        format: ExportFormat = ExportFormat.JSON,
        include_text: bool = True,
        include_metadata: bool = True
    ) -> Tuple[bytes, str, BatchExportResult]:
        """Mehrere Dokumente exportieren.

        NOTE: Delegiert an DocumentExportService.

        Returns:
            Tuple von (export_bytes, content_type, result)
        """
        return await self.export_service.batch_export(
            db, document_ids, user_id, format, include_text, include_metadata
        )

    # ========== Hilfsmethoden ==========

    def _build_filter_conditions(self, filters: SearchFilters) -> List:
        """SQLAlchemy-Filter-Bedingungen erstellen."""
        conditions = []

        if filters.document_type:
            conditions.append(Document.document_type == filters.document_type.value)

        if filters.status:
            conditions.append(Document.status == filters.status.value)

        if filters.date_from:
            conditions.append(Document.created_at >= filters.date_from)

        if filters.date_to:
            conditions.append(Document.created_at <= filters.date_to)

        if filters.confidence_min is not None:
            conditions.append(Document.ocr_confidence >= filters.confidence_min)

        if filters.has_embedding is not None:
            if filters.has_embedding:
                conditions.append(Document.embedding.isnot(None))
            else:
                conditions.append(Document.embedding.is_(None))

        if filters.language:
            conditions.append(Document.detected_language == filters.language)

        return conditions

    def _get_sort_column(self, sort_by: SortField):
        """Spalte fuer Sortierung ermitteln."""
        sort_map = {
            SortField.CREATED_AT: Document.created_at,
            SortField.UPDATED_AT: Document.updated_at,
            SortField.FILENAME: Document.filename,
            SortField.FILE_SIZE: Document.file_size,
            SortField.OCR_CONFIDENCE: Document.ocr_confidence,
            SortField.RELEVANCE: Document.created_at  # Fallback
        }
        return sort_map.get(sort_by, Document.created_at)

    async def _update_document_tags(
        self,
        db: AsyncSession,
        doc: Document,
        tag_names: List[str]
    ) -> None:
        """Dokument-Tags aktualisieren."""
        tag_objects = await self._ensure_tags_exist(db, tag_names)
        doc.tags = tag_objects

    async def _ensure_tags_exist(
        self,
        db: AsyncSession,
        tag_names: List[str]
    ) -> List[Tag]:
        """Tags erstellen falls nicht vorhanden, vorhandene zurueckgeben."""
        if not tag_names:
            return []

        # Vorhandene Tags laden
        query = select(Tag).where(Tag.name.in_(tag_names))
        result = await db.execute(query)
        existing_tags = {t.name: t for t in result.scalars().all()}

        tags = []
        for name in tag_names:
            if name in existing_tags:
                tags.append(existing_tags[name])
            else:
                # Neuen Tag erstellen
                new_tag = Tag(name=name)
                db.add(new_tag)
                tags.append(new_tag)

        await db.flush()  # IDs fuer neue Tags generieren
        return tags

    def _to_summary(self, doc: Document) -> DocumentSummary:
        """Document zu DocumentSummary konvertieren."""
        return DocumentSummary(
            id=doc.id,
            filename=doc.filename,
            document_type=DocumentType(doc.document_type) if doc.document_type else DocumentType.OTHER,
            status=ProcessingStatus(doc.status),
            file_size=doc.file_size or 0,
            page_count=doc.page_count,
            ocr_confidence=doc.ocr_confidence,
            created_at=doc.created_at,
            tags=[t.name for t in doc.tags] if doc.tags else [],
            has_embedding=doc.embedding is not None
        )

    def _to_detail_response(self, doc: Document) -> DocumentDetailResponse:
        """Document zu DocumentDetailResponse konvertieren."""
        return DocumentDetailResponse(
            id=doc.id,
            filename=doc.filename,
            original_filename=doc.original_filename,
            file_path=doc.file_path,
            file_size=doc.file_size or 0,
            mime_type=doc.mime_type,
            checksum=doc.checksum,
            document_type=DocumentType(doc.document_type) if doc.document_type else DocumentType.OTHER,
            status=ProcessingStatus(doc.status),
            page_count=doc.page_count,
            extracted_text=doc.extracted_text,
            ocr_backend_used=doc.ocr_backend_used,
            ocr_confidence=doc.ocr_confidence,
            processing_duration_ms=doc.processing_duration_ms,
            has_umlauts=doc.has_umlauts or False,
            german_validation_score=doc.german_validation_score,
            detected_language=doc.detected_language,
            document_metadata=doc.document_metadata or {},
            tags=[
                TagResponse(
                    id=t.id,
                    name=t.name,
                    description=t.description,
                    color=t.color,
                    created_at=t.created_at
                )
                for t in doc.tags
            ] if doc.tags else [],
            upload_date=doc.upload_date,
            processed_date=doc.processed_date,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            current_version_number=doc.current_version_number or 0,
            total_versions=doc.total_versions or 0,
            has_embedding=doc.embedding is not None,
            embedding_updated_at=doc.embedding_updated_at,
            embedding_model=doc.embedding_model,
            owner_id=doc.owner_id
        )

    # NOTE: Export helper methods (_export_json, _export_csv, _export_zip, _export_pdf)
    # wurden nach DocumentExportService verschoben


# Dependency Injection - Thread-safe singleton via lru_cache
@lru_cache(maxsize=1)
def get_document_service() -> DocumentService:
    """Document-Service-Instanz abrufen (thread-safe singleton)."""
    return DocumentService()
