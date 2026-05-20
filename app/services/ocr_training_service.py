# -*- coding: utf-8 -*-
"""
OCR Training Service für Ablage-System OCR.

Zentraler Service für das OCR Training und Validation System mit:
- Ground Truth Sample Management (CRUD)
- Editor-Annotation und Admin-Verifikation Workflow
- Stratifizierte Stichproben-Batches
- Statistik-Aggregation

Feinpoliert und durchdacht - Enterprise-grade OCR Training Management.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import hashlib
import random

from sqlalchemy import select, and_, func, desc, asc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import (
    OCRTrainingSample,
    OCRBackendBenchmark,
    OCRValidationCorrection,
    OCRTrainingBatch,
    OCRTrainingBatchItem,
    OCRBackendStatsDaily,
    TrainingSampleStatus,
    CorrectionType,
    BatchType,
    BatchStatus,
    ItemStatus,
    User,
    Document,
)
from app.db.schemas import (
    TrainingSampleCreate,
    TrainingSampleUpdate,
    TrainingSampleResponse,
    TrainingSampleListResponse,
    CorrectionCreate,
    CorrectionResponse,
    BatchCreate,
    BatchResponse,
    BatchDetailResponse,
    BatchListResponse,
    BatchItemUpdate,
    BatchItemResponse,
    TrainingOverviewStats,
    TrainingStatsResponse,
    BackendStats,
    StratificationConfig,
)

logger = structlog.get_logger(__name__)


class OCRTrainingService:
    """
    Service für OCR Training Sample und Batch Management.

    Unterstützt:
    - Ground Truth Sample CRUD
    - Annotation/Verification Workflow
    - Stratified Batch Sampling
    - Training Statistics
    """

    # =========================================================================
    # TRAINING SAMPLE MANAGEMENT
    # =========================================================================

    async def create_training_sample(
        self,
        db: AsyncSession,
        sample_data: TrainingSampleCreate,
        user_id: Optional[UUID] = None
    ) -> OCRTrainingSample:
        """
        Erstellt ein neues Training Sample.

        Args:
            db: Datenbank-Session
            sample_data: Sample-Daten
            user_id: Optional - User der das Sample erstellt

        Returns:
            Erstelltes OCRTrainingSample
        """
        # Berechne File-Hash wenn nicht vorhanden
        file_hash = sample_data.file_hash
        if not file_hash:
            file_hash = hashlib.sha256(sample_data.file_path.encode()).hexdigest()

        # Prüfe auf Duplikat
        existing = await self._get_sample_by_hash(db, file_hash)
        if existing:
            logger.warning(
                "training_sample_duplicate",
                file_hash=file_hash[:12],
                existing_id=str(existing.id)[:8]
            )
            return existing

        sample = OCRTrainingSample(
            file_path=sample_data.file_path,
            file_hash=file_hash,
            thumbnail_path=sample_data.thumbnail_path,
            ground_truth_text=sample_data.ground_truth_text,
            language=sample_data.language,
            document_type=sample_data.document_type,
            difficulty=sample_data.difficulty,
            has_umlauts=sample_data.has_umlauts,
            has_fraktur=sample_data.has_fraktur,
            has_tables=sample_data.has_tables,
            has_handwriting=sample_data.has_handwriting,
            has_stamps=sample_data.has_stamps,
            has_signatures=sample_data.has_signatures,
            umlaut_words=sample_data.umlaut_words or [],
            extracted_fields=sample_data.extracted_fields or {},
            status=TrainingSampleStatus.PENDING.value,
        )

        db.add(sample)
        await db.commit()
        await db.refresh(sample)

        logger.info(
            "training_sample_created",
            sample_id=str(sample.id)[:8],
            language=sample.language,
            document_type=sample.document_type
        )

        return sample

    async def get_training_sample(
        self,
        db: AsyncSession,
        sample_id: UUID
    ) -> Optional[OCRTrainingSample]:
        """Holt ein Training Sample mit allen Relationen."""
        query = (
            select(OCRTrainingSample)
            .where(OCRTrainingSample.id == sample_id)
            .options(
                selectinload(OCRTrainingSample.benchmarks),
                selectinload(OCRTrainingSample.annotated_by),
                selectinload(OCRTrainingSample.verified_by)
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # Erlaubte Sortierfelder (Whitelist gegen SQL-Injection)
    ALLOWED_SORT_FIELDS = {
        "created_at": OCRTrainingSample.created_at,
        "updated_at": OCRTrainingSample.updated_at,
        "document_type": OCRTrainingSample.document_type,
        "status": OCRTrainingSample.status,
        "difficulty": OCRTrainingSample.difficulty,
        "business_priority": OCRTrainingSample.business_priority,
        "language": OCRTrainingSample.language,
    }

    async def list_training_samples(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        language: Optional[str] = None,
        document_type: Optional[str] = None,
        has_ground_truth: Optional[bool] = None,
        verified_only: bool = False,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[OCRTrainingSample], int]:
        """
        Listet Training Samples mit Filtern auf.

        Args:
            db: Database session
            status: Filter nach Status
            language: Filter nach Sprache
            document_type: Filter nach Dokumenttyp
            has_ground_truth: Filter nach Ground Truth vorhanden
            verified_only: Nur verifizierte Samples
            search: Volltextsuche in file_path und ground_truth_text
            sort_by: Sortierfeld (created_at, document_type, status, etc.)
            sort_order: Sortierreihenfolge (asc, desc)
            limit: Maximale Anzahl
            offset: Offset für Paginierung

        Returns:
            Tuple von (Samples, Total Count)
        """
        # Base Query
        query = select(OCRTrainingSample)
        count_query = select(func.count(OCRTrainingSample.id))

        # Filter anwenden
        filters = []
        if status:
            filters.append(OCRTrainingSample.status == status)
        if language:
            filters.append(OCRTrainingSample.language == language)
        if document_type:
            filters.append(OCRTrainingSample.document_type == document_type)
        if has_ground_truth is not None:
            if has_ground_truth:
                filters.append(OCRTrainingSample.ground_truth_text.isnot(None))
            else:
                filters.append(OCRTrainingSample.ground_truth_text.is_(None))
        if verified_only:
            filters.append(OCRTrainingSample.status == TrainingSampleStatus.VERIFIED.value)

        # Volltextsuche (LIKE Pattern, keine SQL-Injection durch parameterisierte Query)
        if search:
            search_pattern = f"%{search}%"
            filters.append(
                or_(
                    OCRTrainingSample.file_path.ilike(search_pattern),
                    OCRTrainingSample.ground_truth_text.ilike(search_pattern),
                    OCRTrainingSample.document_type.ilike(search_pattern),
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Total Count
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung (mit Whitelist-Validierung)
        sort_column = self.ALLOWED_SORT_FIELDS.get(sort_by, OCRTrainingSample.created_at)
        if sort_order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        # Paginated Results
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        samples = list(result.scalars().all())

        return samples, total

    async def update_training_sample(
        self,
        db: AsyncSession,
        sample_id: UUID,
        update_data: TrainingSampleUpdate,
        user_id: UUID
    ) -> Optional[OCRTrainingSample]:
        """
        Aktualisiert ein Training Sample (Editor-Annotation).

        Args:
            db: Datenbank-Session
            sample_id: Sample-ID
            update_data: Update-Daten
            user_id: User der die Änderung macht

        Returns:
            Aktualisiertes Sample oder None
        """
        sample = await self._get_sample(db, sample_id)
        if not sample:
            return None

        # Update Felder die gesetzt sind
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(sample, field, value)

        # Annotator tracken
        if update_data.ground_truth_text is not None:
            sample.annotated_by_id = user_id
            sample.annotated_at = datetime.now(timezone.utc)
            if sample.status == TrainingSampleStatus.PENDING.value:
                sample.status = TrainingSampleStatus.ANNOTATED.value

        await db.commit()
        await db.refresh(sample)

        logger.info(
            "training_sample_updated",
            sample_id=str(sample_id)[:8],
            updated_by=str(user_id)[:8],
            fields=list(update_dict.keys())
        )

        return sample

    async def verify_training_sample(
        self,
        db: AsyncSession,
        sample_id: UUID,
        verifier_id: UUID,
        approved: bool,
        notes: Optional[str] = None
    ) -> Optional[OCRTrainingSample]:
        """
        Admin-Verifizierung eines annotierten Samples.

        Args:
            db: Datenbank-Session
            sample_id: Sample-ID
            verifier_id: Admin-User-ID
            approved: Ob Sample genehmigt wird
            notes: Optionale Notizen

        Returns:
            Verifiziertes Sample oder None
        """
        sample = await self._get_sample(db, sample_id)
        if not sample:
            return None

        now = datetime.now(timezone.utc)
        sample.verified_by_id = verifier_id
        sample.verified_at = now

        if approved:
            sample.status = TrainingSampleStatus.VERIFIED.value
        else:
            sample.status = TrainingSampleStatus.REJECTED.value

        if notes:
            sample.annotation_notes = notes

        await db.commit()
        await db.refresh(sample)

        logger.info(
            "training_sample_verified",
            sample_id=str(sample_id)[:8],
            verifier_id=str(verifier_id)[:8],
            approved=approved
        )

        return sample

    async def delete_training_sample(
        self,
        db: AsyncSession,
        sample_id: UUID
    ) -> bool:
        """Löscht ein Training Sample."""
        sample = await self._get_sample(db, sample_id)
        if not sample:
            return False

        await db.delete(sample)
        await db.commit()

        logger.info("training_sample_deleted", sample_id=str(sample_id)[:8])
        return True

    # =========================================================================
    # VALIDATION CORRECTIONS (Self-Learning Feedback)
    # =========================================================================

    # Bekannte OCR-Backends für Validierung
    KNOWN_BACKENDS = {
        "deepseek", "deepseek-janus-pro",
        "got_ocr", "got-ocr", "got-ocr-2.0",
        "surya", "surya-gpu", "surya_gpu",
        "hybrid",
    }

    async def create_correction(
        self,
        db: AsyncSession,
        correction_data: CorrectionCreate,
        user_id: UUID
    ) -> OCRValidationCorrection:
        """
        Erstellt eine OCR-Korrektur für Self-Learning.

        Args:
            db: Datenbank-Session
            correction_data: Korrektur-Daten
            user_id: User der korrigiert

        Returns:
            Erstellte Korrektur

        Raises:
            ValueError: Bei ungültigen Korrektur-Daten
        """
        # Validierung: corrected_text nicht leer
        if not correction_data.corrected_text or not correction_data.corrected_text.strip():
            raise ValueError("Korrigierter Text darf nicht leer sein")

        # Validierung: original_text != corrected_text
        if correction_data.original_text == correction_data.corrected_text:
            raise ValueError("Korrigierter Text muss sich vom Original unterscheiden")

        # Validierung: backend_used ist bekannt (mit Normalisierung)
        backend = correction_data.backend_used
        if backend:
            backend_normalized = backend.lower().replace("_", "-")
            if backend_normalized not in self.KNOWN_BACKENDS and backend not in self.KNOWN_BACKENDS:
                logger.warning(
                    "unknown_backend_in_correction",
                    backend=backend,
                    known_backends=list(self.KNOWN_BACKENDS),
                )
                # Erlaube trotzdem, aber logge Warnung (könnte neues Backend sein)

        # Validierung: confidence_before im gültigen Bereich
        confidence = correction_data.confidence_before
        if confidence is not None:
            if not 0.0 <= confidence <= 1.0:
                logger.warning(
                    "invalid_confidence_in_correction",
                    confidence=confidence,
                )
                # Clamp auf gültigen Bereich
                confidence = max(0.0, min(1.0, confidence))

        correction = OCRValidationCorrection(
            document_id=correction_data.document_id,
            original_text=correction_data.original_text,
            corrected_text=correction_data.corrected_text,
            correction_type=correction_data.correction_type.value,
            field_corrected=correction_data.field_corrected,
            backend_used=correction_data.backend_used,
            confidence_before=confidence,
            applies_to_training=True,  # Automatisches Self-Learning
            learning_processed=False,
            corrector_id=user_id,
        )

        db.add(correction)
        await db.commit()
        await db.refresh(correction)

        logger.info(
            "ocr_correction_created",
            correction_id=str(correction.id)[:8],
            correction_type=correction_data.correction_type.value,
            backend=correction_data.backend_used
        )

        return correction

    async def list_corrections(
        self,
        db: AsyncSession,
        backend: Optional[str] = None,
        correction_type: Optional[str] = None,
        unprocessed_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[OCRValidationCorrection], int]:
        """Listet Korrekturen mit Filtern auf."""
        query = select(OCRValidationCorrection)
        count_query = select(func.count(OCRValidationCorrection.id))

        filters = []
        if backend:
            filters.append(OCRValidationCorrection.backend_used == backend)
        if correction_type:
            filters.append(OCRValidationCorrection.correction_type == correction_type)
        if unprocessed_only:
            filters.append(OCRValidationCorrection.learning_processed == False)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Total
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Results
        query = (
            query
            .order_by(desc(OCRValidationCorrection.created_at))
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        corrections = list(result.scalars().all())

        return corrections, total

    async def mark_corrections_processed(
        self,
        db: AsyncSession,
        correction_ids: List[UUID]
    ) -> int:
        """
        Markiert Korrekturen als verarbeitet (für Self-Learning).

        Returns:
            Anzahl markierter Korrekturen
        """
        now = datetime.now(timezone.utc)
        count = 0

        for correction_id in correction_ids:
            result = await db.execute(
                select(OCRValidationCorrection)
                .where(OCRValidationCorrection.id == correction_id)
            )
            correction = result.scalar_one_or_none()
            if correction and not correction.learning_processed:
                correction.learning_processed = True
                correction.learning_processed_at = now
                count += 1

        await db.commit()

        logger.info(
            "corrections_marked_processed",
            count=count,
            total_requested=len(correction_ids)
        )

        return count

    # =========================================================================
    # TRAINING BATCHES (Stichproben-Workflow)
    # =========================================================================

    async def create_training_batch(
        self,
        db: AsyncSession,
        batch_data: BatchCreate,
        user_id: UUID
    ) -> OCRTrainingBatch:
        """
        Erstellt einen neuen Training-Batch mit stratifizierter Stichprobe.

        Args:
            db: Datenbank-Session
            batch_data: Batch-Konfiguration
            user_id: Ersteller

        Returns:
            Erstellter Batch
        """
        batch = OCRTrainingBatch(
            name=batch_data.name,
            description=batch_data.description,
            batch_type=batch_data.batch_type.value if batch_data.batch_type else BatchType.STRATIFIED.value,
            stratification_config=batch_data.stratification_config.model_dump() if batch_data.stratification_config else None,
            target_size=batch_data.target_size,
            actual_size=0,
            status=BatchStatus.DRAFT.value,
            items_pending=0,
            items_completed=0,
            created_by_id=user_id,
        )

        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        # Generiere stratifizierte Stichprobe
        if batch_data.auto_populate:
            await self._populate_batch(
                db, batch,
                batch_data.stratification_config,
                batch_data.target_size
            )

        logger.info(
            "training_batch_created",
            batch_id=str(batch.id)[:8],
            name=batch.name,
            target_size=batch.target_size
        )

        return batch

    async def _populate_batch(
        self,
        db: AsyncSession,
        batch: OCRTrainingBatch,
        config: Optional[StratificationConfig],
        target_size: int
    ) -> None:
        """
        Befüllt einen Batch mit stratifizierten Samples.
        """
        # Query für verfügbare Samples
        base_query = (
            select(OCRTrainingSample)
            .where(
                and_(
                    OCRTrainingSample.status == TrainingSampleStatus.VERIFIED.value,
                    OCRTrainingSample.ground_truth_text.isnot(None)
                )
            )
        )

        # Stratifikation anwenden
        if config:
            if config.languages:
                base_query = base_query.where(
                    OCRTrainingSample.language.in_(config.languages)
                )
            if config.document_types:
                base_query = base_query.where(
                    OCRTrainingSample.document_type.in_(config.document_types)
                )
            if config.difficulties:
                base_query = base_query.where(
                    OCRTrainingSample.difficulty.in_(config.difficulties)
                )
            if config.require_umlauts:
                base_query = base_query.where(OCRTrainingSample.has_umlauts == True)
            if config.require_tables:
                base_query = base_query.where(OCRTrainingSample.has_tables == True)
            if config.require_handwriting:
                base_query = base_query.where(OCRTrainingSample.has_handwriting == True)

        result = await db.execute(base_query)
        all_samples = list(result.scalars().all())

        # Stratifizierte Zufallsauswahl mit deterministischem Seed
        # Seed basiert auf batch.id für Reproduzierbarkeit
        random.seed(str(batch.id))
        if len(all_samples) > target_size:
            selected_samples = random.sample(all_samples, target_size)
        else:
            selected_samples = all_samples
        random.seed()  # Reset seed nach Verwendung

        # Batch Items erstellen
        for idx, sample in enumerate(selected_samples, 1):
            item = OCRTrainingBatchItem(
                batch_id=batch.id,
                training_sample_id=sample.id,
                sequence_number=idx,
                status=ItemStatus.PENDING.value,
            )
            db.add(item)

        batch.actual_size = len(selected_samples)
        batch.items_pending = len(selected_samples)
        batch.status = BatchStatus.READY.value

        await db.commit()

        logger.info(
            "batch_populated",
            batch_id=str(batch.id)[:8],
            samples_added=len(selected_samples),
            target=target_size
        )

    async def get_training_batch(
        self,
        db: AsyncSession,
        batch_id: UUID
    ) -> Optional[OCRTrainingBatch]:
        """Holt einen Batch mit allen Items."""
        query = (
            select(OCRTrainingBatch)
            .where(OCRTrainingBatch.id == batch_id)
            .options(
                selectinload(OCRTrainingBatch.items),
                selectinload(OCRTrainingBatch.created_by)
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_training_batches(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[OCRTrainingBatch], int]:
        """Listet Training Batches auf."""
        query = select(OCRTrainingBatch)
        count_query = select(func.count(OCRTrainingBatch.id))

        if status:
            query = query.where(OCRTrainingBatch.status == status)
            count_query = count_query.where(OCRTrainingBatch.status == status)

        # Total
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Results
        query = (
            query
            .order_by(desc(OCRTrainingBatch.created_at))
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        batches = list(result.scalars().all())

        return batches, total

    async def start_batch(
        self,
        db: AsyncSession,
        batch_id: UUID
    ) -> Optional[OCRTrainingBatch]:
        """Startet einen Batch zur Validierung."""
        batch = await self._get_batch(db, batch_id)
        if not batch:
            return None

        if batch.status != BatchStatus.READY.value:
            raise ValueError(f"Batch kann nicht gestartet werden (Status: {batch.status})")

        batch.status = BatchStatus.IN_PROGRESS.value
        await db.commit()

        logger.info("training_batch_started", batch_id=str(batch_id)[:8])
        return batch

    async def complete_batch(
        self,
        db: AsyncSession,
        batch_id: UUID
    ) -> Optional[OCRTrainingBatch]:
        """Markiert einen Batch als abgeschlossen."""
        batch = await self._get_batch(db, batch_id)
        if not batch:
            return None

        batch.status = BatchStatus.COMPLETED.value
        batch.completed_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "training_batch_completed",
            batch_id=str(batch_id)[:8],
            items_completed=batch.items_completed
        )
        return batch

    async def update_batch_item(
        self,
        db: AsyncSession,
        item_id: UUID,
        update_data: BatchItemUpdate,
        user_id: UUID
    ) -> Optional[OCRTrainingBatchItem]:
        """Aktualisiert ein Batch Item (Validierungs-Workflow)."""
        result = await db.execute(
            select(OCRTrainingBatchItem)
            .where(OCRTrainingBatchItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None

        now = datetime.now(timezone.utc)

        # Status-Tracking
        if item.status == ItemStatus.PENDING.value and update_data.status:
            item.started_at = now
            item.assigned_to_id = user_id

        if update_data.status:
            item.status = update_data.status.value
            if update_data.status == ItemStatus.COMPLETED:
                item.completed_at = now

        if update_data.validation_notes:
            item.validation_notes = update_data.validation_notes

        if update_data.validation_time_seconds:
            item.validation_time_seconds = update_data.validation_time_seconds

        # Batch-Fortschritt aktualisieren
        batch = await self._get_batch(db, item.batch_id)
        if batch:
            # Zähle completed Items
            count_result = await db.execute(
                select(func.count(OCRTrainingBatchItem.id))
                .where(
                    and_(
                        OCRTrainingBatchItem.batch_id == item.batch_id,
                        OCRTrainingBatchItem.status == ItemStatus.COMPLETED.value
                    )
                )
            )
            completed = count_result.scalar() or 0
            batch.items_completed = completed
            batch.items_pending = batch.actual_size - completed

        await db.commit()
        await db.refresh(item)

        return item

    async def get_next_batch_item(
        self,
        db: AsyncSession,
        batch_id: UUID,
        user_id: UUID
    ) -> Optional[OCRTrainingBatchItem]:
        """
        Holt das nächste zu validierende Item für einen User.
        """
        # Suche nach bereits zugewiesenem Item
        result = await db.execute(
            select(OCRTrainingBatchItem)
            .where(
                and_(
                    OCRTrainingBatchItem.batch_id == batch_id,
                    OCRTrainingBatchItem.assigned_to_id == user_id,
                    OCRTrainingBatchItem.status == ItemStatus.IN_PROGRESS.value
                )
            )
        )
        item = result.scalar_one_or_none()
        if item:
            return item

        # Sonst nächstes pending Item
        result = await db.execute(
            select(OCRTrainingBatchItem)
            .where(
                and_(
                    OCRTrainingBatchItem.batch_id == batch_id,
                    OCRTrainingBatchItem.status == ItemStatus.PENDING.value
                )
            )
            .order_by(OCRTrainingBatchItem.sequence_number)
            .limit(1)
        )
        item = result.scalar_one_or_none()

        if item:
            item.assigned_to_id = user_id
            item.status = ItemStatus.IN_PROGRESS.value
            item.started_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(item)

        return item

    # =========================================================================
    # STATISTICS & ANALYTICS
    # =========================================================================

    async def get_training_overview_stats(
        self,
        db: AsyncSession
    ) -> TrainingOverviewStats:
        """
        Holt Übersichts-Statistiken für das Training Dashboard.
        """
        # Sample Counts by Status
        status_counts = {}
        for status in TrainingSampleStatus:
            result = await db.execute(
                select(func.count(OCRTrainingSample.id))
                .where(OCRTrainingSample.status == status.value)
            )
            status_counts[status.value] = result.scalar() or 0

        # Total Samples
        total_result = await db.execute(select(func.count(OCRTrainingSample.id)))
        total_samples = total_result.scalar() or 0

        # Verified Samples
        verified_samples = status_counts.get(TrainingSampleStatus.VERIFIED.value, 0)

        # Pending Annotations
        pending = status_counts.get(TrainingSampleStatus.PENDING.value, 0)

        # Active Batches
        active_result = await db.execute(
            select(func.count(OCRTrainingBatch.id))
            .where(OCRTrainingBatch.status == BatchStatus.IN_PROGRESS.value)
        )
        active_batches = active_result.scalar() or 0

        # Recent Corrections (letzte 24h)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        corrections_result = await db.execute(
            select(func.count(OCRValidationCorrection.id))
            .where(OCRValidationCorrection.created_at >= yesterday)
        )
        recent_corrections = corrections_result.scalar() or 0

        # Unprocessed Corrections
        unprocessed_result = await db.execute(
            select(func.count(OCRValidationCorrection.id))
            .where(OCRValidationCorrection.learning_processed == False)
        )
        unprocessed_corrections = unprocessed_result.scalar() or 0

        # Samples by Language
        lang_result = await db.execute(
            select(
                OCRTrainingSample.language,
                func.count(OCRTrainingSample.id)
            )
            .where(OCRTrainingSample.status == TrainingSampleStatus.VERIFIED.value)
            .group_by(OCRTrainingSample.language)
        )
        samples_by_language = {row[0]: row[1] for row in lang_result.all()}

        # Samples by Document Type
        type_result = await db.execute(
            select(
                OCRTrainingSample.document_type,
                func.count(OCRTrainingSample.id)
            )
            .where(
                and_(
                    OCRTrainingSample.status == TrainingSampleStatus.VERIFIED.value,
                    OCRTrainingSample.document_type.isnot(None)
                )
            )
            .group_by(OCRTrainingSample.document_type)
        )
        samples_by_type = {row[0]: row[1] for row in type_result.all()}

        return TrainingOverviewStats(
            total_samples=total_samples,
            verified_samples=verified_samples,
            pending_annotations=pending,
            active_batches=active_batches,
            recent_corrections_24h=recent_corrections,
            unprocessed_corrections=unprocessed_corrections,
            samples_by_language=samples_by_language,
            samples_by_document_type=samples_by_type,
        )

    async def get_backend_stats(
        self,
        db: AsyncSession,
        days: int = 30
    ) -> List[BackendStats]:
        """
        Holt Performance-Statistiken für alle OCR Backends.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Aggregiere Benchmarks pro Backend
        result = await db.execute(
            select(
                OCRBackendBenchmark.backend_name,
                func.count(OCRBackendBenchmark.id).label("samples_count"),
                func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
                func.avg(OCRBackendBenchmark.wer).label("avg_wer"),
                func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_umlaut"),
                func.avg(OCRBackendBenchmark.processing_time_ms).label("avg_time"),
            )
            .where(OCRBackendBenchmark.processed_at >= since)
            .group_by(OCRBackendBenchmark.backend_name)
        )

        stats = []
        for row in result.all():
            stats.append(BackendStats(
                backend_name=row[0],
                samples_processed=row[1],
                avg_cer=round(row[2], 4) if row[2] else None,
                avg_wer=round(row[3], 4) if row[3] else None,
                avg_umlaut_accuracy=round(row[4], 4) if row[4] else None,
                avg_processing_time_ms=int(row[5]) if row[5] else None,
            ))

        return stats

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _get_sample(
        self,
        db: AsyncSession,
        sample_id: UUID
    ) -> Optional[OCRTrainingSample]:
        """Holt ein Sample ohne Relationen."""
        result = await db.execute(
            select(OCRTrainingSample)
            .where(OCRTrainingSample.id == sample_id)
        )
        return result.scalar_one_or_none()

    async def _get_sample_by_hash(
        self,
        db: AsyncSession,
        file_hash: str
    ) -> Optional[OCRTrainingSample]:
        """Holt ein Sample anhand des File-Hashes."""
        result = await db.execute(
            select(OCRTrainingSample)
            .where(OCRTrainingSample.file_hash == file_hash)
        )
        return result.scalar_one_or_none()

    async def _get_batch(
        self,
        db: AsyncSession,
        batch_id: UUID
    ) -> Optional[OCRTrainingBatch]:
        """Holt einen Batch ohne Items."""
        result = await db.execute(
            select(OCRTrainingBatch)
            .where(OCRTrainingBatch.id == batch_id)
        )
        return result.scalar_one_or_none()


# Singleton
_ocr_training_service: Optional[OCRTrainingService] = None


def get_ocr_training_service() -> OCRTrainingService:
    """Gibt OCRTrainingService-Singleton zurück."""
    global _ocr_training_service
    if _ocr_training_service is None:
        _ocr_training_service = OCRTrainingService()
    return _ocr_training_service
