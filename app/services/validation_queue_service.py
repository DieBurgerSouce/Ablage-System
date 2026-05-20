"""ValidationQueueService - Enterprise-Grade Validierungsqueue-Verwaltung.

Dieser Service verwaltet die Validierungswarteschlange für OCR-Ergebnisse
und extrahierte Daten. Er bietet CRUD-Operationen, Zuweisung an Editoren,
Genehmigung/Ablehnung sowie Batch-Operationen.

Verwendung:
    from app.services.validation_queue_service import get_validation_queue_service

    service = get_validation_queue_service(db)
    items = await service.get_queue_items(filters=filters, page=1, per_page=20)
"""
import uuid
from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from typing import Optional, List, Dict, Any, Tuple
import structlog

from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ValidationQueueItem,
    ValidationFieldReview,
    ValidationRule,
    ValidationStatus,
    SampleSource,
    Document,
    User
)
from app.db.schemas import (
    ValidationQueueItemCreate,
    ValidationQueueItemUpdate,
    ValidationQueueItemResponse,
    ValidationQueueItemDetail,
    ValidationQueueListResponse,
    ValidationQueueItemAssign,
    ValidationQueueItemApprove,
    ValidationQueueItemReject,
    BatchApproveRequest,
    BatchRejectRequest,
    BatchAssignRequest,
    ValidationBatchOperationResult as BatchOperationResult,  # Alias für Rückwärtskompatibilität
    ValidationQueueFilters,
    ValidationQueueSortOptions,
    ValidationStatusEnum,
    SampleSourceEnum,
    RejectionCategoryEnum,
)

logger = structlog.get_logger(__name__)


class ValidationQueueService:
    """Service für die Verwaltung der Validierungswarteschlange."""

    def __init__(self, db: AsyncSession):
        """Initialisiere den Service mit einer Datenbankverbindung."""
        self.db = db

    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================

    async def add_to_queue(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
        source: SampleSourceEnum = SampleSourceEnum.AUTOMATIC,
        priority: int = 5,
        created_by_id: Optional[uuid.UUID] = None,
        sample_rule_id: Optional[uuid.UUID] = None
    ) -> ValidationQueueItem:
        """Fuegt ein Dokument zur Validierungswarteschlange hinzu.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            source: Quelle der Stichprobenauswahl
            priority: Priorität (1-10, 1 = hoechste)
            created_by_id: ID des Erstellers
            sample_rule_id: ID der ausloesenden Regel (bei rule_based)

        Returns:
            Das erstellte ValidationQueueItem

        Raises:
            ValueError: Wenn das Dokument bereits in der Queue ist
            ValueError: Wenn das Dokument nicht zur Company gehoert
        """
        # SECURITY: Dokument mit company_id Validierung laden
        doc_result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            # SECURITY: Prüfen ob Dokument existiert aber falsche Company
            check_result = await self.db.execute(
                select(Document.company_id).where(Document.id == document_id)
            )
            actual_company_id = check_result.scalar_one_or_none()
            if actual_company_id and actual_company_id != company_id:
                logger.warning(
                    "cross_tenant_validation_queue_blocked",
                    document_id=str(document_id),
                    requested_company_id=str(company_id),
                    actual_company_id=str(actual_company_id),
                )
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        # Prüfen ob Dokument bereits in Queue (pending oder in_progress)
        existing = await self.db.execute(
            select(ValidationQueueItem).where(
                and_(
                    ValidationQueueItem.document_id == document_id,
                    ValidationQueueItem.status.in_([
                        ValidationStatus.PENDING.value,
                        ValidationStatus.IN_PROGRESS.value
                    ])
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Dokument {document_id} ist bereits in der Validierungswarteschlange")

        # Queue-Item erstellen
        queue_item = ValidationQueueItem(
            document_id=document_id,
            status=ValidationStatus.PENDING.value,
            priority=priority,
            sample_source=source.value,
            sample_rule_id=sample_rule_id,
            overall_confidence=document.ocr_confidence,
            document_type=document.document_type,
            document_name=document.original_filename,
            created_by_id=created_by_id
        )

        self.db.add(queue_item)
        await self.db.commit()
        await self.db.refresh(queue_item)

        logger.info(
            "validation_queue_item_created",
            queue_item_id=str(queue_item.id),
            document_id=str(document_id),
            source=source.value,
            priority=priority
        )

        return queue_item

    async def get_queue_item(
        self,
        item_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
        include_fields: bool = False
    ) -> Optional[ValidationQueueItem]:
        """Holt ein Queue-Item nach ID.

        SECURITY: company_id SOLLTE für Multi-Tenant Isolation angegeben werden.
        Die Validierung erfolgt über JOIN auf Document.company_id.

        Args:
            item_id: ID des Queue-Items
            company_id: ID der Company für Multi-Tenant Isolation
            include_fields: Ob Feld-Reviews mitgeladen werden sollen

        Returns:
            Das Queue-Item oder None
        """
        # SECURITY: Multi-Tenant Isolation via Join auf Document
        if company_id:
            query = (
                select(ValidationQueueItem)
                .join(Document, ValidationQueueItem.document_id == Document.id)
                .where(
                    and_(
                        ValidationQueueItem.id == item_id,
                        Document.company_id == company_id,
                    )
                )
            )
        else:
            query = select(ValidationQueueItem).where(ValidationQueueItem.id == item_id)

        if include_fields:
            query = query.options(selectinload(ValidationQueueItem.field_reviews))

        result = await self.db.execute(query)
        item = result.scalar_one_or_none()

        # SECURITY: Log Cross-Tenant Zugriffsversuch
        if company_id and not item:
            check_query = (
                select(Document.company_id)
                .join(ValidationQueueItem, ValidationQueueItem.document_id == Document.id)
                .where(ValidationQueueItem.id == item_id)
            )
            check_result = await self.db.execute(check_query)
            actual_company_id = check_result.scalar_one_or_none()
            if actual_company_id and actual_company_id != company_id:
                logger.warning(
                    "cross_tenant_validation_item_access_blocked",
                    item_id=str(item_id),
                    requested_company_id=str(company_id),
                    actual_company_id=str(actual_company_id),
                )

        return item

    async def get_queue_items(
        self,
        company_id: uuid.UUID,
        filters: Optional[ValidationQueueFilters] = None,
        sort_by: ValidationQueueSortOptions = ValidationQueueSortOptions.PRIORITY_DESC,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[ValidationQueueItem], int]:
        """Holt Queue-Items mit Filterung und Paginierung.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.
        Filtert Items über JOIN auf Document.company_id.

        Args:
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            filters: Filter-Optionen
            sort_by: Sortierung
            page: Seitennummer (1-basiert)
            per_page: Items pro Seite

        Returns:
            Tuple aus (Items, Gesamtanzahl)
        """
        # SECURITY: Multi-Tenant Isolation via Join auf Document
        query = (
            select(ValidationQueueItem)
            .join(Document, ValidationQueueItem.document_id == Document.id)
            .where(Document.company_id == company_id)
        )
        count_query = (
            select(func.count(ValidationQueueItem.id))
            .join(Document, ValidationQueueItem.document_id == Document.id)
            .where(Document.company_id == company_id)
        )

        # Filter anwenden
        if filters:
            conditions = []

            if filters.status:
                status_values = [s.value for s in filters.status]
                conditions.append(ValidationQueueItem.status.in_(status_values))

            if filters.assigned_to_id:
                conditions.append(ValidationQueueItem.assigned_to_id == filters.assigned_to_id)

            if filters.document_type:
                conditions.append(ValidationQueueItem.document_type.in_(filters.document_type))

            if filters.sample_source:
                source_values = [s.value for s in filters.sample_source]
                conditions.append(ValidationQueueItem.sample_source.in_(source_values))

            if filters.confidence_min is not None:
                conditions.append(ValidationQueueItem.overall_confidence >= filters.confidence_min)

            if filters.confidence_max is not None:
                conditions.append(ValidationQueueItem.overall_confidence <= filters.confidence_max)

            if filters.priority_min is not None:
                conditions.append(ValidationQueueItem.priority >= filters.priority_min)

            if filters.priority_max is not None:
                conditions.append(ValidationQueueItem.priority <= filters.priority_max)

            if filters.created_from:
                conditions.append(ValidationQueueItem.created_at >= filters.created_from)

            if filters.created_to:
                conditions.append(ValidationQueueItem.created_at <= filters.created_to)

            if filters.search:
                # Multi-Feld-Suche: document_name, document_type, validation_notes
                search_pattern = f"%{filters.search}%"
                search_conditions = or_(
                    ValidationQueueItem.document_name.ilike(search_pattern),
                    ValidationQueueItem.document_type.ilike(search_pattern),
                    ValidationQueueItem.validation_notes.ilike(search_pattern),
                    ValidationQueueItem.rejection_reason.ilike(search_pattern),
                )
                conditions.append(search_conditions)

            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

        # Sortierung
        sort_mapping = {
            ValidationQueueSortOptions.PRIORITY_ASC: ValidationQueueItem.priority.asc(),
            ValidationQueueSortOptions.PRIORITY_DESC: ValidationQueueItem.priority.desc(),
            ValidationQueueSortOptions.CONFIDENCE_ASC: ValidationQueueItem.overall_confidence.asc(),
            ValidationQueueSortOptions.CONFIDENCE_DESC: ValidationQueueItem.overall_confidence.desc(),
            ValidationQueueSortOptions.CREATED_ASC: ValidationQueueItem.created_at.asc(),
            ValidationQueueSortOptions.CREATED_DESC: ValidationQueueItem.created_at.desc(),
            ValidationQueueSortOptions.DOCUMENT_NAME: ValidationQueueItem.document_name.asc(),
        }
        query = query.order_by(sort_mapping.get(sort_by, ValidationQueueItem.priority.desc()))

        # Paginierung
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Ausführen
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return items, total

    async def update_queue_item(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
        update_data: ValidationQueueItemUpdate
    ) -> Optional[ValidationQueueItem]:
        """Aktualisiert ein Queue-Item.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_id: ID des Queue-Items
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            update_data: Zu aktualisierende Felder

        Returns:
            Das aktualisierte Queue-Item oder None
        """
        # SECURITY: Multi-Tenant Isolation
        item = await self.get_queue_item(item_id, company_id=company_id)
        if not item:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(item, key, value)

        item.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(item)

        logger.info(
            "validation_queue_item_updated",
            queue_item_id=str(item_id),
            updated_fields=list(update_dict.keys())
        )

        return item

    async def delete_queue_item(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> bool:
        """Löscht ein Queue-Item.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_id: ID des Queue-Items
            company_id: ID der Company (PFLICHT für Multi-Tenant)

        Returns:
            True wenn gelöscht, False wenn nicht gefunden
        """
        # SECURITY: Multi-Tenant Isolation
        item = await self.get_queue_item(item_id, company_id=company_id)
        if not item:
            return False

        await self.db.delete(item)
        await self.db.commit()

        logger.info("validation_queue_item_deleted", queue_item_id=str(item_id))
        return True

    # =========================================================================
    # ASSIGNMENT OPERATIONS
    # =========================================================================

    async def assign_to_editor(
        self,
        item_id: uuid.UUID,
        editor_id: uuid.UUID,
        company_id: uuid.UUID,
        priority: Optional[int] = None
    ) -> Optional[ValidationQueueItem]:
        """Weist ein Queue-Item einem Editor zu.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.
        Validiert auch, dass der Editor zur selben Company gehoert.

        Args:
            item_id: ID des Queue-Items
            editor_id: ID des Editors
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            priority: Optionale neue Priorität

        Returns:
            Das aktualisierte Queue-Item oder None
        """
        # SECURITY: Multi-Tenant Isolation
        item = await self.get_queue_item(item_id, company_id=company_id)
        if not item:
            return None

        # SECURITY: Prüfen ob Editor zur selben Company gehoert
        editor_result = await self.db.execute(
            select(User).where(
                and_(
                    User.id == editor_id,
                    User.company_id == company_id,
                )
            )
        )
        editor = editor_result.scalar_one_or_none()
        if not editor:
            raise ValueError(f"Editor {editor_id} nicht gefunden oder gehoert nicht zur Company")

        item.assigned_to_id = editor_id
        item.assigned_at = utc_now()
        item.status = ValidationStatus.IN_PROGRESS.value
        item.started_at = utc_now()

        if priority is not None:
            item.priority = priority

        item.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(item)

        logger.info(
            "validation_queue_item_assigned",
            queue_item_id=str(item_id),
            editor_id=str(editor_id)
        )

        return item

    async def unassign(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[ValidationQueueItem]:
        """Entfernt die Zuweisung eines Queue-Items.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_id: ID des Queue-Items
            company_id: ID der Company (PFLICHT für Multi-Tenant)

        Returns:
            Das aktualisierte Queue-Item oder None
        """
        # SECURITY: Multi-Tenant Isolation
        item = await self.get_queue_item(item_id, company_id=company_id)
        if not item:
            return None

        item.assigned_to_id = None
        item.assigned_at = None
        item.status = ValidationStatus.PENDING.value
        item.started_at = None
        item.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(item)

        logger.info("validation_queue_item_unassigned", queue_item_id=str(item_id))
        return item

    # =========================================================================
    # APPROVAL / REJECTION
    # =========================================================================

    async def approve_item(
        self,
        item_id: uuid.UUID,
        validated_by_id: uuid.UUID,
        company_id: uuid.UUID,
        notes: Optional[str] = None
    ) -> Optional[ValidationQueueItem]:
        """Genehmigt ein Queue-Item.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_id: ID des Queue-Items
            validated_by_id: ID des validierenden Users
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            notes: Optionale Notizen

        Returns:
            Das aktualisierte Queue-Item oder None
        """
        # SECURITY: Multi-Tenant Isolation
        item = await self.get_queue_item(item_id, company_id=company_id, include_fields=True)
        if not item:
            return None

        now = utc_now()

        # Dauer berechnen
        duration = None
        if item.started_at:
            duration = int((now - item.started_at).total_seconds())

        # Korrekturen zaehlen
        corrections = 0
        umlaut_corrections = 0
        format_corrections = 0

        for field in item.field_reviews:
            if field.was_corrected:
                corrections += 1
            if field.umlaut_issues:
                umlaut_corrections += len(field.umlaut_issues)
            if field.format_issues:
                format_corrections += len(field.format_issues)

        item.status = ValidationStatus.APPROVED.value
        item.validated_by_id = validated_by_id
        item.validated_at = now
        item.completed_at = now
        item.validation_duration_seconds = duration
        item.validation_notes = notes
        item.corrections_made = corrections
        item.umlaut_corrections = umlaut_corrections
        item.format_corrections = format_corrections
        item.updated_at = now

        await self.db.commit()
        await self.db.refresh(item)

        logger.info(
            "validation_queue_item_approved",
            queue_item_id=str(item_id),
            validated_by_id=str(validated_by_id),
            duration_seconds=duration,
            corrections=corrections
        )

        return item

    async def reject_item(
        self,
        item_id: uuid.UUID,
        validated_by_id: uuid.UUID,
        company_id: uuid.UUID,
        reason: str,
        category: RejectionCategoryEnum = RejectionCategoryEnum.OTHER
    ) -> Optional[ValidationQueueItem]:
        """Lehnt ein Queue-Item ab.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_id: ID des Queue-Items
            validated_by_id: ID des validierenden Users
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            reason: Ablehnungsgrund
            category: Kategorie des Ablehnungsgrunds

        Returns:
            Das aktualisierte Queue-Item oder None
        """
        # SECURITY: Multi-Tenant Isolation
        item = await self.get_queue_item(item_id, company_id=company_id)
        if not item:
            return None

        now = utc_now()

        # Dauer berechnen
        duration = None
        if item.started_at:
            duration = int((now - item.started_at).total_seconds())

        item.status = ValidationStatus.REJECTED.value
        item.validated_by_id = validated_by_id
        item.validated_at = now
        item.completed_at = now
        item.validation_duration_seconds = duration
        item.rejection_reason = reason
        item.rejection_category = category.value
        item.updated_at = now

        await self.db.commit()
        await self.db.refresh(item)

        logger.info(
            "validation_queue_item_rejected",
            queue_item_id=str(item_id),
            validated_by_id=str(validated_by_id),
            category=category.value
        )

        return item

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    async def batch_approve(
        self,
        item_ids: List[uuid.UUID],
        validated_by_id: uuid.UUID,
        company_id: uuid.UUID,
        notes: Optional[str] = None
    ) -> BatchOperationResult:
        """Genehmigt mehrere Queue-Items.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_ids: Liste der Queue-Item IDs
            validated_by_id: ID des validierenden Users
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            notes: Optionale gemeinsame Notizen

        Returns:
            BatchOperationResult mit Erfolgs-/Fehlerstatistik
        """
        success_count = 0
        failed_items = []

        for item_id in item_ids:
            try:
                # SECURITY: company_id wird an approve_item weitergegeben
                result = await self.approve_item(item_id, validated_by_id, company_id, notes)
                if result:
                    success_count += 1
                else:
                    failed_items.append({
                        "id": str(item_id),
                        "error": "Item nicht gefunden"
                    })
            except Exception as e:
                failed_items.append({
                    "id": str(item_id), **safe_error_log(e)})

        logger.info(
            "validation_batch_approve_completed",
            success_count=success_count,
            failed_count=len(failed_items)
        )

        return BatchOperationResult(
            success_count=success_count,
            failed_count=len(failed_items),
            failed_items=failed_items,
            message=f"{success_count} Items genehmigt, {len(failed_items)} fehlgeschlagen"
        )

    async def batch_reject(
        self,
        item_ids: List[uuid.UUID],
        validated_by_id: uuid.UUID,
        company_id: uuid.UUID,
        reason: str,
        category: RejectionCategoryEnum = RejectionCategoryEnum.OTHER
    ) -> BatchOperationResult:
        """Lehnt mehrere Queue-Items ab.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_ids: Liste der Queue-Item IDs
            validated_by_id: ID des validierenden Users
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            reason: Gemeinsamer Ablehnungsgrund
            category: Kategorie des Ablehnungsgrunds

        Returns:
            BatchOperationResult mit Erfolgs-/Fehlerstatistik
        """
        success_count = 0
        failed_items = []

        for item_id in item_ids:
            try:
                # SECURITY: company_id wird an reject_item weitergegeben
                result = await self.reject_item(item_id, validated_by_id, company_id, reason, category)
                if result:
                    success_count += 1
                else:
                    failed_items.append({
                        "id": str(item_id),
                        "error": "Item nicht gefunden"
                    })
            except Exception as e:
                failed_items.append({
                    "id": str(item_id), **safe_error_log(e)})

        logger.info(
            "validation_batch_reject_completed",
            success_count=success_count,
            failed_count=len(failed_items),
            category=category.value
        )

        return BatchOperationResult(
            success_count=success_count,
            failed_count=len(failed_items),
            failed_items=failed_items,
            message=f"{success_count} Items abgelehnt, {len(failed_items)} fehlgeschlagen"
        )

    async def batch_assign(
        self,
        item_ids: List[uuid.UUID],
        editor_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> BatchOperationResult:
        """Weist mehrere Queue-Items einem Editor zu.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.

        Args:
            item_ids: Liste der Queue-Item IDs
            editor_id: ID des Editors
            company_id: ID der Company (PFLICHT für Multi-Tenant)

        Returns:
            BatchOperationResult mit Erfolgs-/Fehlerstatistik
        """
        success_count = 0
        failed_items = []

        for item_id in item_ids:
            try:
                # SECURITY: company_id wird an assign_to_editor weitergegeben
                result = await self.assign_to_editor(item_id, editor_id, company_id)
                if result:
                    success_count += 1
                else:
                    failed_items.append({
                        "id": str(item_id),
                        "error": "Item nicht gefunden"
                    })
            except Exception as e:
                failed_items.append({
                    "id": str(item_id), **safe_error_log(e)})

        logger.info(
            "validation_batch_assign_completed",
            success_count=success_count,
            failed_count=len(failed_items),
            editor_id=str(editor_id)
        )

        return BatchOperationResult(
            success_count=success_count,
            failed_count=len(failed_items),
            failed_items=failed_items,
            message=f"{success_count} Items zugewiesen, {len(failed_items)} fehlgeschlagen"
        )

    # =========================================================================
    # STATISTICS
    # =========================================================================

    async def get_queue_stats(self, company_id: uuid.UUID) -> Dict[str, int]:
        """Holt Statistiken zur Warteschlange.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.
        Zeigt nur Statistiken für die eigene Company.

        Args:
            company_id: ID der Company (PFLICHT für Multi-Tenant)

        Returns:
            Dictionary mit Statistiken
        """
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())

        # SECURITY: Base-Subquery für company_id Filter
        company_filtered_ids = (
            select(ValidationQueueItem.id)
            .join(Document, ValidationQueueItem.document_id == Document.id)
            .where(Document.company_id == company_id)
            .scalar_subquery()
        )

        # Pending count
        pending_result = await self.db.execute(
            select(func.count(ValidationQueueItem.id)).where(
                and_(
                    ValidationQueueItem.status == ValidationStatus.PENDING.value,
                    ValidationQueueItem.id.in_(company_filtered_ids),
                )
            )
        )
        pending_count = pending_result.scalar() or 0

        # In Progress count
        in_progress_result = await self.db.execute(
            select(func.count(ValidationQueueItem.id)).where(
                and_(
                    ValidationQueueItem.status == ValidationStatus.IN_PROGRESS.value,
                    ValidationQueueItem.id.in_(company_filtered_ids),
                )
            )
        )
        in_progress_count = in_progress_result.scalar() or 0

        # Approved today
        approved_result = await self.db.execute(
            select(func.count(ValidationQueueItem.id)).where(
                and_(
                    ValidationQueueItem.status == ValidationStatus.APPROVED.value,
                    ValidationQueueItem.validated_at >= today_start,
                    ValidationQueueItem.id.in_(company_filtered_ids),
                )
            )
        )
        approved_today = approved_result.scalar() or 0

        # Rejected today
        rejected_result = await self.db.execute(
            select(func.count(ValidationQueueItem.id)).where(
                and_(
                    ValidationQueueItem.status == ValidationStatus.REJECTED.value,
                    ValidationQueueItem.validated_at >= today_start,
                    ValidationQueueItem.id.in_(company_filtered_ids),
                )
            )
        )
        rejected_today = rejected_result.scalar() or 0

        return {
            "pending": pending_count,
            "in_progress": in_progress_count,
            "approved_today": approved_today,
            "rejected_today": rejected_today
        }

    async def get_my_assigned_items(
        self,
        editor_id: uuid.UUID,
        company_id: uuid.UUID,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[ValidationQueueItem], int]:
        """Holt alle einem Editor zugewiesenen Items mit Pagination.

        SECURITY: company_id ist PFLICHT für Multi-Tenant Isolation.
        Filtert Items zusätzlich über Document.company_id.

        Args:
            editor_id: ID des Editors
            company_id: ID der Company (PFLICHT für Multi-Tenant)
            status: Optionaler Status-Filter (String-Wert)
            limit: Maximale Anzahl der Items
            offset: Offset für Pagination

        Returns:
            Tuple aus (Liste der zugewiesenen Items, Gesamtanzahl)
        """
        # SECURITY: Multi-Tenant Isolation via Join auf Document
        base_conditions = [
            ValidationQueueItem.assigned_to_id == editor_id,
            Document.company_id == company_id,  # Multi-Tenant Filter
        ]

        if status:
            base_conditions.append(ValidationQueueItem.status == status)

        # Count Query mit Join
        count_query = (
            select(func.count(ValidationQueueItem.id))
            .join(Document, ValidationQueueItem.document_id == Document.id)
            .where(and_(*base_conditions))
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Items Query mit Pagination und Join
        query = (
            select(ValidationQueueItem)
            .join(Document, ValidationQueueItem.document_id == Document.id)
            .where(and_(*base_conditions))
        )
        query = query.order_by(ValidationQueueItem.priority.asc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total


def get_validation_queue_service(db: AsyncSession) -> ValidationQueueService:
    """Factory-Funktion für den ValidationQueueService.

    Args:
        db: Async-Datenbankverbindung

    Returns:
        ValidationQueueService Instanz
    """
    return ValidationQueueService(db)
