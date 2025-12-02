"""Batch-Service fuer Massenoperationen auf Dokumenten.

Optimierte Bulk-Operationen mit transaktionssicherer Verarbeitung.
"""

from typing import Optional, List, Dict, Set
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Tag, ProcessingStatus
from app.db.schemas import (
    BatchOperationResult,
    BatchOperationError,
    TagOperation,
    DocumentFilterForBulkUpdate,
    DocumentPartialUpdateRequest,
    BulkUpdateResult,
)

logger = structlog.get_logger(__name__)


class DocumentBatchService:
    """Service fuer Batch-Operationen auf Dokumenten.

    Bietet optimierte Bulk-Operationen mit:
    - Transaktionssicherheit (Rollback bei Fehlern)
    - Bulk-Loading (keine N+1 Queries)
    - Fehler-Tracking pro Dokument
    """

    async def batch_delete(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        user_id: UUID,
        dry_run: bool = False,
        soft_delete: bool = True
    ) -> BatchOperationResult:
        """Mehrere Dokumente loeschen (optimierte Bulk-Operation).

        Verwendet eine einzige Abfrage fuer effiziente Batch-Loeschung
        anstatt N+1 Einzelabfragen.

        Args:
            db: Datenbank-Session
            document_ids: Liste der zu loeschenden Dokument-IDs
            user_id: ID des ausfuehrenden Benutzers
            dry_run: Wenn True, wird nur simuliert (keine Loeschung)
            soft_delete: Wenn True (Standard), Soft-Delete fuer GDPR-Konformitaet

        Returns:
            BatchOperationResult mit Statistiken
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
                message="Keine Dokumente zum Loeschen angegeben",
                dry_run=dry_run
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

            # Bei dry_run: Nur zeigen was geloescht wuerde
            if dry_run:
                logger.info(
                    "batch_delete_dry_run",
                    total=len(document_ids),
                    would_delete=len(found_ids),
                    not_found=len(not_found_ids)
                )
                return BatchOperationResult(
                    success=True,
                    operation="delete",
                    total_requested=len(document_ids),
                    processed=len(found_ids),
                    failed=len(not_found_ids),
                    errors=errors,
                    message=f"[DRY RUN] {len(found_ids)} Dokument(e) wuerden geloescht",
                    dry_run=True,
                    affected_documents=list(found_ids) if found_ids else None
                )

            # Schritt 3: Bulk-Delete/Soft-Delete der gefundenen Dokumente
            processed = 0
            if found_ids:
                if soft_delete:
                    # GDPR-konformes Soft-Delete: Markiere als geloescht
                    now = datetime.now(timezone.utc)
                    update_stmt = update(Document).where(
                        and_(
                            Document.id.in_(list(found_ids)),
                            Document.owner_id == user_id
                        )
                    ).values(
                        deleted_at=now,
                        deleted_by_id=user_id,
                        status=ProcessingStatus.DELETED
                    )
                    update_result = await db.execute(update_stmt)
                    processed = update_result.rowcount
                else:
                    # Hard-Delete
                    delete_stmt = delete(Document).where(
                        and_(
                            Document.id.in_(list(found_ids)),
                            Document.owner_id == user_id
                        )
                    )
                    delete_result = await db.execute(delete_stmt)
                    processed = delete_result.rowcount

                await db.commit()

                # Cache invalidieren
                await self._invalidate_user_cache(user_id, "batch_delete")

            failed = len(not_found_ids)

        except Exception as e:
            logger.error(
                "batch_delete_failed",
                error=str(e),
                document_count=len(document_ids),
                dry_run=dry_run
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
                message="Batch-Loeschung fehlgeschlagen",
                dry_run=dry_run
            )

        success = failed == 0
        delete_type = "soft-geloescht (wiederherstellbar 30 Tage)" if soft_delete else "permanent geloescht"
        message = (
            f"{processed} Dokument(e) erfolgreich {delete_type}"
            if success else
            f"{processed} von {len(document_ids)} Dokument(en) {delete_type}, {failed} fehlgeschlagen"
        )

        logger.info(
            "batch_delete_completed",
            total=len(document_ids),
            processed=processed,
            failed=failed,
            dry_run=dry_run,
            soft_delete=soft_delete
        )

        return BatchOperationResult(
            success=success,
            operation="soft_delete" if soft_delete else "delete",
            total_requested=len(document_ids),
            processed=processed,
            failed=failed,
            errors=errors,
            message=message,
            dry_run=dry_run
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

        TRANSAKTIONSSICHER: Bei Fehlern wird Rollback durchgefuehrt.

        Args:
            db: Datenbank-Session
            document_ids: Liste der Dokument-IDs
            tags: Liste der Tag-Namen
            user_id: Benutzer-ID
            operation: ADD, REMOVE oder SET

        Returns:
            BatchOperationResult mit Statistiken
        """
        processed = 0
        failed = 0
        errors: List[BatchOperationError] = []

        try:
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

        except Exception as e:
            logger.error(
                "batch_tag_failed",
                error=str(e),
                document_count=len(document_ids),
                operation=operation.value
            )
            await db.rollback()
            return BatchOperationResult(
                success=False,
                operation=f"tag_{operation.value}",
                total_requested=len(document_ids),
                processed=0,
                failed=len(document_ids),
                errors=[BatchOperationError(
                    document_id=document_ids[0] if document_ids else None,
                    error=f"Batch-Tag-Operation fehlgeschlagen: {str(e)}",
                    error_code="TAG_TRANSACTION_ERROR"
                )],
                message="Batch-Tag-Operation fehlgeschlagen - Rollback durchgefuehrt"
            )

        # Cache invalidieren
        if processed > 0:
            await self._invalidate_user_cache(user_id, "batch_tag")

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

    async def bulk_update(
        self,
        db: AsyncSession,
        user_id: UUID,
        filter_criteria: DocumentFilterForBulkUpdate,
        updates: DocumentPartialUpdateRequest,
        dry_run: bool = False
    ) -> BulkUpdateResult:
        """Bulk-Update fuer mehrere Dokumente.

        Aktualisiert Dokumente basierend auf Filterkriterien.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            filter_criteria: Filter fuer zu aktualisierende Dokumente
            updates: Anzuwendende Aenderungen
            dry_run: Nur simulieren, nicht ausfuehren

        Returns:
            BulkUpdateResult mit Statistiken
        """
        errors: List[str] = []

        # Query mit Filtern aufbauen
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(Document.owner_id == user_id)
        )

        if filter_criteria.document_ids:
            query = query.where(Document.id.in_(filter_criteria.document_ids))

        if filter_criteria.document_type:
            query = query.where(
                Document.document_type == filter_criteria.document_type.value
            )

        if filter_criteria.status:
            query = query.where(
                Document.status == filter_criteria.status.value
            )

        if filter_criteria.date_from:
            query = query.where(Document.created_at >= filter_criteria.date_from)

        if filter_criteria.date_to:
            query = query.where(Document.created_at <= filter_criteria.date_to)

        if filter_criteria.tags:
            # Dokumente mit mindestens einem der Tags
            query = query.join(Document.tags).where(Tag.name.in_(filter_criteria.tags))

        # Dokumente laden
        result = await db.execute(query)
        documents = result.scalars().unique().all()

        total_matched = len(documents)
        total_updated = 0

        if dry_run:
            return BulkUpdateResult(
                total_matched=total_matched,
                total_updated=0,
                failed=0,
                dry_run=True,
                errors=[]
            )

        # Updates anwenden
        for doc in documents:
            try:
                if updates.document_type is not None:
                    doc.document_type = updates.document_type.value

                if updates.language is not None:
                    doc.detected_language = updates.language

                if updates.metadata is not None:
                    current_meta = doc.document_metadata or {}
                    current_meta.update(updates.metadata)
                    doc.document_metadata = current_meta

                # Tag-Operationen
                if updates.tags is not None:
                    tag_objects = await self._ensure_tags_exist(db, updates.tags)
                    doc.tags = tag_objects
                elif updates.add_tags is not None:
                    tag_objects = await self._ensure_tags_exist(db, updates.add_tags)
                    existing_ids = {t.id for t in doc.tags}
                    for tag in tag_objects:
                        if tag.id not in existing_ids:
                            doc.tags.append(tag)
                elif updates.remove_tags is not None:
                    current_tag_names = [t.name for t in doc.tags]
                    remaining_tags = [t for t in current_tag_names if t not in updates.remove_tags]
                    tag_objects = await self._ensure_tags_exist(db, remaining_tags)
                    doc.tags = tag_objects

                doc.updated_at = datetime.now(timezone.utc)
                total_updated += 1

            except Exception as e:
                errors.append(f"Dokument {doc.id}: {str(e)}")
                logger.warning(
                    "bulk_update_document_failed",
                    document_id=str(doc.id),
                    error=str(e)
                )

        await db.commit()

        logger.info(
            "bulk_update_completed",
            user_id=str(user_id),
            total_matched=total_matched,
            total_updated=total_updated,
            failed=len(errors)
        )

        # Cache invalidieren
        if total_updated > 0:
            await self._invalidate_user_cache(user_id, "bulk_update")

        return BulkUpdateResult(
            total_matched=total_matched,
            total_updated=total_updated,
            failed=len(errors),
            dry_run=False,
            errors=errors
        )

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

    async def _invalidate_user_cache(
        self,
        user_id: UUID,
        reason: str
    ) -> None:
        """Invalidiert Such-Caches nach Batch-Operationen."""
        try:
            from app.services.document_service import _get_search_service
            search_service = _get_search_service()
            if search_service:
                await search_service.invalidate_user_search_cache(
                    user_id, reason=reason
                )
        except Exception as e:
            logger.warning(
                "cache_invalidation_failed",
                user_id=str(user_id),
                reason=reason,
                error=str(e)
            )


# Singleton Instance
_batch_service: Optional[DocumentBatchService] = None


def get_document_batch_service() -> DocumentBatchService:
    """Document-Batch-Service-Instanz abrufen (singleton)."""
    global _batch_service
    if _batch_service is None:
        _batch_service = DocumentBatchService()
    return _batch_service
