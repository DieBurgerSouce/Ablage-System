"""Base-Klasse und gemeinsame Utilities für Document Services.

Enthält:
- SearchService-Integration (async-safe)
- Konvertierungsmethoden (Document -> Response)
- Tag-Verwaltung
- Cache-Invalidation
"""

import asyncio
from contextvars import ContextVar
from typing import TYPE_CHECKING, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Tag, ProcessingStatus
from app.db.schemas import (
    DocumentType,
    DocumentSummary,
    DocumentDetailResponse,
    TagResponse,
)
from app.core.cache import invalidate_on_document_change
from app.core.safe_errors import safe_error_log

if TYPE_CHECKING:
    from app.services.search_service import SearchService

logger = structlog.get_logger(__name__)

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
                **safe_error_log(e)
            )
            return None
    return service


def set_search_service(service: "SearchService") -> None:
    """Inject SearchService instance for current async context.

    Used for dependency injection in tests or application setup.
    """
    _search_service_ctx.set(service)


class DocumentServiceBase:
    """Basis-Service mit gemeinsamer Funktionalität.

    Stellt Konvertierungsmethoden, Tag-Verwaltung und
    Cache-Invalidierung bereit.
    """

    async def _ensure_tags_exist(
        self,
        db: AsyncSession,
        tag_names: List[str]
    ) -> List[Tag]:
        """Tags erstellen falls nicht vorhanden, vorhandene zurückgeben."""
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

        await db.flush()  # IDs für neue Tags generieren
        return tags

    async def _update_document_tags(
        self,
        db: AsyncSession,
        doc: Document,
        tag_names: List[str]
    ) -> None:
        """Dokument-Tags aktualisieren."""
        tag_objects = await self._ensure_tags_exist(db, tag_names)
        doc.tags = tag_objects

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

    async def _invalidate_document_cache(
        self,
        document_id,
        user_id,
        reason: str
    ) -> None:
        """Such-Cache für ein Dokument invalidieren."""
        try:
            search_service = _get_search_service()
            if search_service:
                await search_service.invalidate_document_cache(
                    document_id, user_id, reason=reason
                )
        except Exception as e:
            logger.warning(
                "cache_invalidation_failed",
                document_id=str(document_id),
                reason=reason,
                **safe_error_log(e)
            )

    async def _invalidate_user_cache(
        self,
        user_id,
        reason: str
    ) -> None:
        """Such-Cache für einen Benutzer invalidieren."""
        try:
            search_service = _get_search_service()
            if search_service:
                await search_service.invalidate_user_search_cache(
                    user_id, reason=reason
                )
        except Exception as e:
            logger.warning(
                "user_cache_invalidation_failed",
                user_id=str(user_id),
                reason=reason,
                **safe_error_log(e)
            )

    async def _invalidate_central_cache(
        self,
        document_id: str,
        change_type: str
    ) -> None:
        """Zentrale Cache-Invalidation (Cascade: doc, search, facets, stats)."""
        try:
            await invalidate_on_document_change(document_id, change_type=change_type)
        except Exception as e:
            logger.warning(
                "central_cache_invalidation_failed",
                document_id=document_id,
                change_type=change_type,
                **safe_error_log(e)
            )
