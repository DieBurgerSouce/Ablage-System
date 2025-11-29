"""Document-Service fuer CRUD-Operationen und Batch-Verarbeitung.

Zentrale Service-Schicht fuer Dokumentenverwaltung mit Unterstuetzung
fuer Filterung, Pagination und Batch-Operationen.
"""

from typing import List, Optional, Dict, Tuple
from datetime import datetime, timezone
from uuid import UUID
import math
import json
import csv
import io
import zipfile

import structlog
from sqlalchemy import select, func, and_, or_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Tag, User, document_tags, ProcessingStatus
from app.db.schemas import (
    SearchFilters, SortField, SortOrder, DocumentType,
    DocumentSummary, DocumentDetailResponse, DocumentListResponseExtended,
    BatchOperationResult, BatchOperationError, BatchExportResult, ExportFormat,
    TagOperation, TagResponse
)
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Lazy import to avoid circular dependency
_search_service = None


def _get_search_service():
    """Lazy-load SearchService to avoid circular import."""
    global _search_service
    if _search_service is None:
        from app.services.search_service import get_search_service
        _search_service = get_search_service()
    return _search_service


class DocumentService:
    """Service fuer Dokumentenverwaltung.

    Bietet CRUD-Operationen, Filterung, Pagination und Batch-Operationen.
    """

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

        return True

    # ========== Batch-Operationen ==========

    async def batch_delete(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        user_id: UUID
    ) -> BatchOperationResult:
        """Mehrere Dokumente loeschen (optimierte Bulk-Operation).

        Verwendet eine einzige Abfrage fuer effiziente Batch-Loeschung
        anstatt N+1 Einzelabfragen.
        """
        errors: List[BatchOperationError] = []

        if not document_ids:
            return BatchOperationResult(
                success=True,
                operation="delete",
                total_requested=0,
                processed=0,
                failed=0,
                errors=[],
                message="Keine Dokumente zum Loeschen angegeben"
            )

        try:
            # Schritt 1: Finde alle Dokumente die existieren und dem Benutzer gehoeren
            query = select(Document.id).where(
                and_(
                    Document.id.in_(document_ids),
                    Document.owner_id == user_id
                )
            )
            result = await db.execute(query)
            found_ids = {row[0] for row in result.fetchall()}

            # Schritt 2: Identifiziere nicht gefundene Dokumente
            not_found_ids = set(document_ids) - found_ids
            for doc_id in not_found_ids:
                errors.append(BatchOperationError(
                    document_id=doc_id,
                    error="Dokument nicht gefunden oder keine Berechtigung",
                    error_code="NOT_FOUND"
                ))

            # Schritt 3: Bulk-Delete der gefundenen Dokumente
            processed = 0
            if found_ids:
                delete_stmt = delete(Document).where(
                    and_(
                        Document.id.in_(list(found_ids)),
                        Document.owner_id == user_id
                    )
                )
                delete_result = await db.execute(delete_stmt)
                processed = delete_result.rowcount
                await db.commit()

                # Such-Caches invalidieren
                try:
                    search_service = _get_search_service()
                    await search_service.invalidate_user_search_cache(
                        user_id, reason="batch_delete"
                    )
                except Exception as e:
                    logger.warning(
                        "cache_invalidation_on_batch_delete_failed",
                        error=str(e)
                    )

            failed = len(not_found_ids)

        except Exception as e:
            logger.error(
                "batch_delete_failed",
                error=str(e),
                document_count=len(document_ids)
            )
            await db.rollback()
            return BatchOperationResult(
                success=False,
                operation="delete",
                total_requested=len(document_ids),
                processed=0,
                failed=len(document_ids),
                errors=[BatchOperationError(
                    document_id=document_ids[0],
                    error=f"Batch-Loeschung fehlgeschlagen: {str(e)}",
                    error_code="DELETE_ERROR"
                )],
                message="Batch-Loeschung fehlgeschlagen"
            )

        success = failed == 0
        message = (
            f"{processed} Dokument(e) erfolgreich geloescht"
            if success else
            f"{processed} von {len(document_ids)} Dokument(en) geloescht, {failed} fehlgeschlagen"
        )

        logger.info(
            "batch_delete_completed",
            total=len(document_ids),
            processed=processed,
            failed=failed
        )

        return BatchOperationResult(
            success=success,
            operation="delete",
            total_requested=len(document_ids),
            processed=processed,
            failed=failed,
            errors=errors,
            message=message
        )

    async def batch_tag(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        tags: List[str],
        user_id: UUID,
        operation: TagOperation = TagOperation.ADD
    ) -> BatchOperationResult:
        """Tags fuer mehrere Dokumente setzen - optimiert mit Bulk-Loading."""
        processed = 0
        failed = 0
        errors: List[BatchOperationError] = []

        # Tags vorbereiten (erstellen falls nicht vorhanden)
        tag_objects = await self._ensure_tags_exist(db, tags)

        # BULK LOAD: Single query with IN clause instead of N+1 queries
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(
                Document.id.in_(document_ids),
                Document.owner_id == user_id
            ))
        )
        result = await db.execute(query)
        documents = {doc.id: doc for doc in result.scalars().all()}

        # Track not found documents
        not_found_ids = set(document_ids) - set(documents.keys())
        for doc_id in not_found_ids:
            failed += 1
            errors.append(BatchOperationError(
                document_id=doc_id,
                error="Dokument nicht gefunden oder keine Berechtigung",
                error_code="NOT_FOUND"
            ))

        # Process found documents (in-memory, no additional queries)
        for doc_id, doc in documents.items():
            try:
                # Tags aktualisieren basierend auf Operation
                if operation == TagOperation.SET:
                    doc.tags = tag_objects
                elif operation == TagOperation.ADD:
                    existing_ids = {t.id for t in doc.tags}
                    for tag in tag_objects:
                        if tag.id not in existing_ids:
                            doc.tags.append(tag)
                elif operation == TagOperation.REMOVE:
                    remove_ids = {t.id for t in tag_objects}
                    doc.tags = [t for t in doc.tags if t.id not in remove_ids]

                processed += 1

            except Exception as e:
                failed += 1
                errors.append(BatchOperationError(
                    document_id=doc_id,
                    error=str(e),
                    error_code="TAG_ERROR"
                ))

        await db.commit()

        # Such-Caches invalidieren (Tags beeinflussen Suchergebnisse)
        if processed > 0:
            try:
                search_service = _get_search_service()
                await search_service.invalidate_user_search_cache(user_id, reason="batch_tag")
            except Exception as e:
                logger.warning(
                    "cache_invalidation_on_batch_tag_failed",
                    error=str(e)
                )

        success = failed == 0
        op_name = {"add": "hinzugefuegt", "remove": "entfernt", "set": "gesetzt"}
        message = (
            f"Tags erfolgreich fuer {processed} Dokument(e) {op_name.get(operation.value, 'aktualisiert')}"
            if success else
            f"Tags fuer {processed} von {len(document_ids)} Dokument(en) aktualisiert, {failed} fehlgeschlagen"
        )

        logger.info(
            "batch_tag_completed",
            operation=operation.value,
            total=len(document_ids),
            processed=processed,
            failed=failed
        )

        return BatchOperationResult(
            success=success,
            operation=f"tag_{operation.value}",
            total_requested=len(document_ids),
            processed=processed,
            failed=failed,
            errors=errors,
            message=message
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

        Returns:
            Tuple von (export_bytes, content_type, result)
        """
        # Dokumente laden
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(
                Document.id.in_(document_ids),
                Document.owner_id == user_id
            ))
        )
        result = await db.execute(query)
        documents = result.scalars().all()

        found_ids = {doc.id for doc in documents}
        not_found = [doc_id for doc_id in document_ids if doc_id not in found_ids]

        errors = [
            BatchOperationError(
                document_id=doc_id,
                error="Dokument nicht gefunden oder keine Berechtigung",
                error_code="NOT_FOUND"
            )
            for doc_id in not_found
        ]

        # Export durchfuehren
        if format == ExportFormat.JSON:
            export_data, content_type = self._export_json(
                documents, include_text, include_metadata
            )
        elif format == ExportFormat.CSV:
            export_data, content_type = self._export_csv(
                documents, include_text, include_metadata
            )
        elif format == ExportFormat.PDF:
            export_data, content_type = self._export_pdf(
                documents, include_text, include_metadata
            )
        else:
            # ZIP mit einzelnen Dateien
            export_data, content_type = self._export_zip(
                documents, include_text, include_metadata
            )

        export_result = BatchExportResult(
            success=len(errors) == 0,
            operation="export",
            total_requested=len(document_ids),
            processed=len(documents),
            failed=len(errors),
            errors=errors,
            message=f"{len(documents)} Dokument(e) exportiert",
            download_url=None,  # Wird vom Router gesetzt
            expires_at=None,
            file_size_bytes=len(export_data),
            format=format
        )

        logger.info(
            "batch_export_completed",
            format=format.value,
            total=len(document_ids),
            exported=len(documents)
        )

        return export_data, content_type, export_result

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

    def _export_json(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als JSON."""
        export_data = []
        for doc in documents:
            item = {
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "file_size": doc.file_size,
                "page_count": doc.page_count,
                "ocr_confidence": doc.ocr_confidence,
                "tags": [t.name for t in doc.tags] if doc.tags else []
            }

            if include_text:
                item["extracted_text"] = doc.extracted_text

            if include_metadata:
                item["metadata"] = doc.document_metadata
                item["detected_language"] = doc.detected_language
                item["has_umlauts"] = doc.has_umlauts

            export_data.append(item)

        return json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"

    def _export_csv(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als CSV."""
        output = io.StringIO()
        fieldnames = [
            "id", "filename", "document_type", "status",
            "created_at", "file_size", "page_count", "ocr_confidence", "tags"
        ]

        if include_text:
            fieldnames.append("extracted_text")
        if include_metadata:
            fieldnames.extend(["detected_language", "has_umlauts"])

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for doc in documents:
            row = {
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else "",
                "file_size": doc.file_size or 0,
                "page_count": doc.page_count or 0,
                "ocr_confidence": doc.ocr_confidence or 0,
                "tags": ",".join(t.name for t in doc.tags) if doc.tags else ""
            }

            if include_text:
                # Text kuerzen fuer CSV
                text = doc.extracted_text or ""
                row["extracted_text"] = text[:1000] + "..." if len(text) > 1000 else text

            if include_metadata:
                row["detected_language"] = doc.detected_language or ""
                row["has_umlauts"] = str(doc.has_umlauts or False)

            writer.writerow(row)

        return output.getvalue().encode("utf-8"), "text/csv"

    def _export_zip(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als ZIP mit einzelnen JSON-Dateien."""
        output = io.BytesIO()

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in documents:
                item = {
                    "id": str(doc.id),
                    "filename": doc.filename,
                    "document_type": doc.document_type,
                    "status": doc.status,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "file_size": doc.file_size,
                    "page_count": doc.page_count,
                    "ocr_confidence": doc.ocr_confidence,
                    "tags": [t.name for t in doc.tags] if doc.tags else []
                }

                if include_text:
                    item["extracted_text"] = doc.extracted_text

                if include_metadata:
                    item["metadata"] = doc.document_metadata
                    item["detected_language"] = doc.detected_language
                    item["has_umlauts"] = doc.has_umlauts

                json_content = json.dumps(item, ensure_ascii=False, indent=2)
                filename = f"{doc.filename.rsplit('.', 1)[0]}_{doc.id}.json"
                zf.writestr(filename, json_content.encode("utf-8"))

        return output.getvalue(), "application/zip"

    def _export_pdf(
        self,
        documents: List[Document],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als PDF mit reportlab."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        )

        output = io.BytesIO()
        doc = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=2*cm,
            rightMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        # Styles definieren
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            textColor=colors.darkblue
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=15,
            textColor=colors.darkblue
        )
        text_style = ParagraphStyle(
            'CustomText',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            spaceAfter=6
        )

        elements = []

        # Titelseite
        elements.append(Paragraph("Ablage-System - Dokumentenexport", title_style))
        elements.append(Paragraph(
            f"Exportiert am: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC",
            text_style
        ))
        elements.append(Paragraph(f"Anzahl Dokumente: {len(documents)}", text_style))
        elements.append(Spacer(1, 30))

        # Jedes Dokument
        for idx, document in enumerate(documents):
            if idx > 0:
                elements.append(PageBreak())

            # Dokumenttitel
            safe_filename = document.filename.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            elements.append(Paragraph(f"Dokument: {safe_filename}", heading_style))

            # Metadaten-Tabelle
            metadata_rows = [
                ["Feld", "Wert"],
                ["ID", str(document.id)],
                ["Dateiname", document.filename or "Unbekannt"],
                ["Typ", document.document_type or "Sonstiges"],
                ["Status", document.status or "Unbekannt"],
                ["Erstellt", document.created_at.strftime("%d.%m.%Y %H:%M") if document.created_at else "-"],
                ["Groesse", f"{(document.file_size or 0) / 1024:.1f} KB"],
                ["Seiten", str(document.page_count or "-")],
                ["OCR-Konfidenz", f"{(document.ocr_confidence or 0) * 100:.1f}%"],
            ]

            # Optionale Metadaten
            if include_metadata:
                if document.detected_language:
                    metadata_rows.append(["Sprache", document.detected_language])
                if document.has_umlauts is not None:
                    metadata_rows.append(["Hat Umlaute", "Ja" if document.has_umlauts else "Nein"])
                if document.ocr_backend_used:
                    metadata_rows.append(["OCR-Backend", document.ocr_backend_used])

            # Tags
            if document.tags:
                tag_names = ", ".join(t.name for t in document.tags)
                metadata_rows.append(["Tags", tag_names])

            # Tabelle erstellen
            table = Table(metadata_rows, colWidths=[4*cm, 12*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (0, -1), colors.lightgrey),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 15))

            # Extrahierter Text
            if include_text and document.extracted_text:
                elements.append(Paragraph("Extrahierter Text:", heading_style))

                # Text aufbereiten (HTML-Entities und Zeilenumbrueche)
                text = document.extracted_text[:10000]  # Limit fuer sehr lange Texte
                if len(document.extracted_text) > 10000:
                    text += "... [Text gekuerzt]"

                # Sonderzeichen escapen
                text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                text = text.replace('\n', '<br/>')

                elements.append(Paragraph(text, text_style))

        # PDF generieren
        doc.build(elements)
        return output.getvalue(), "application/pdf"


# Dependency Injection
_document_service: Optional[DocumentService] = None


def get_document_service() -> DocumentService:
    """Document-Service-Instanz abrufen."""
    global _document_service
    if _document_service is None:
        _document_service = DocumentService()
    return _document_service
