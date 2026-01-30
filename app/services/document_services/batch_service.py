"""Document Batch Service - Bulk-Operationen.

Enthaelt optimierte Operationen fuer mehrere Dokumente:
- batch_delete: Mehrere Dokumente loeschen
- batch_tag: Tags fuer mehrere Dokumente setzen/hinzufuegen/entfernen
- bulk_update: Mehrere Dokumente aktualisieren
"""

from datetime import datetime, timezone
from typing import List
from uuid import UUID

import structlog
from sqlalchemy import select, and_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Tag
from app.db.schemas import (
    TagOperation,
    BatchOperationResult,
    BatchOperationError,
    DocumentFilterForBulkUpdate,
    DocumentPartialUpdateRequest,
    BulkUpdateResult,
)
from app.services.document_services.base import DocumentServiceBase
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class DocumentBatchService(DocumentServiceBase):
    """Service fuer Bulk-Operationen auf mehreren Dokumenten.

    Optimiert fuer effiziente Verarbeitung grosser Dokumentmengen
    mit minimalen Datenbankabfragen (vermeidet N+1).
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
            soft_delete: Wenn True (Standard), Soft-Delete fuer GDPR-Konformitaet.
                        Nach 30 Tagen erfolgt permanente Loeschung via Scheduled Task.

        Returns:
            BatchOperationResult mit Statistiken und ggf. betroffenen Dokumenten
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
                    # Status bleibt unveraendert - deleted_at ist das Kriterium fuer Soft-Delete
                    now = datetime.now(timezone.utc)
                    update_stmt = update(Document).where(
                        and_(
                            Document.id.in_(list(found_ids)),
                            Document.owner_id == user_id
                        )
                    ).values(
                        deleted_at=now,
                        deleted_by_id=user_id
                    )
                    update_result = await db.execute(update_stmt)
                    processed = update_result.rowcount
                else:
                    # Hard-Delete (nur fuer Admin oder nach Ablauf der Aufbewahrungsfrist)
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
                await self._invalidate_user_cache(
                    user_id,
                    reason="batch_soft_delete" if soft_delete else "batch_delete"
                )

            failed = len(not_found_ids)

        except Exception as e:
            logger.error(
                "batch_delete_failed",
                **safe_error_log(e),
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
                    error=safe_error_detail(e, "Batch-Loeschung"),
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
            user_id: ID des Benutzers
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
                        **safe_error_log(e),
                        error_code="TAG_ERROR"
                    ))

            await db.commit()

        except Exception as e:
            logger.error(
                "batch_tag_failed",
                **safe_error_log(e),
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
                    error=safe_error_detail(e, "Batch-Tags"),
                    error_code="TAG_TRANSACTION_ERROR"
                )],
                message="Batch-Tag-Operation fehlgeschlagen - Rollback durchgefuehrt"
            )

        # Such-Caches invalidieren (Tags beeinflussen Suchergebnisse)
        if processed > 0:
            await self._invalidate_user_cache(user_id, reason="batch_tag")

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
                # Felder aktualisieren
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
                    await self._update_document_tags(db, doc, updates.tags)
                elif updates.add_tags is not None:
                    current_tag_names = [t.name for t in doc.tags]
                    new_tag_names = list(set(current_tag_names + updates.add_tags))
                    await self._update_document_tags(db, doc, new_tag_names)
                elif updates.remove_tags is not None:
                    current_tag_names = [t.name for t in doc.tags]
                    remaining_tags = [t for t in current_tag_names if t not in updates.remove_tags]
                    await self._update_document_tags(db, doc, remaining_tags)

                doc.updated_at = datetime.now(timezone.utc)
                total_updated += 1

            except Exception as e:
                errors.append(f"Dokument {doc.id}: {safe_error_detail(e, 'Batch')}")
                logger.warning(
                    "bulk_update_document_failed",
                    document_id=str(doc.id),
                    **safe_error_log(e)
                )

        await db.commit()

        logger.info(
            "bulk_update_completed",
            user_id=str(user_id),
            total_matched=total_matched,
            total_updated=total_updated,
            failed=len(errors)
        )

        # Such-Caches invalidieren
        if total_updated > 0:
            await self._invalidate_user_cache(user_id, reason="bulk_update")

        return BulkUpdateResult(
            total_matched=total_matched,
            total_updated=total_updated,
            failed=len(errors),
            dry_run=False,
            errors=errors
        )


# Singleton-Instanz
_batch_service_instance: DocumentBatchService = None


def get_batch_service() -> DocumentBatchService:
    """Batch-Service-Instanz abrufen (Singleton)."""
    global _batch_service_instance
    if _batch_service_instance is None:
        _batch_service_instance = DocumentBatchService()
    return _batch_service_instance
