# -*- coding: utf-8 -*-
"""
Unit Tests für OCR Training Service.

Testet:
- Training Sample CRUD
- Annotation/Verification Workflow
- Batch Management
- Statistik-Aggregation
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ocr_training_service import OCRTrainingService, get_ocr_training_service
from app.db.models import (
    OCRTrainingSample,
    OCRValidationCorrection,
    OCRTrainingBatch,
    OCRTrainingBatchItem,
    TrainingSampleStatus,
    CorrectionType,
    BatchType,
    BatchStatus,
    ItemStatus,
)
from app.db.schemas import (
    TrainingSampleCreate,
    TrainingSampleUpdate,
    CorrectionCreate,
    BatchCreate,
    BatchItemUpdate,
    StratificationConfig,
)


@pytest.fixture
def ocr_training_service() -> OCRTrainingService:
    """Fixture für OCRTrainingService."""
    return OCRTrainingService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Fixture für Mock-Datenbank-Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def sample_create_data() -> TrainingSampleCreate:
    """Fixture für Sample-Erstellungsdaten."""
    return TrainingSampleCreate(
        file_path="/test/document.pdf",
        ground_truth_text="Dies ist ein Testtext mit Umlauten: äöü ÄÖÜ ß",
        language="de",
        document_type="invoice",
        difficulty="medium",
        has_umlauts=True,
        has_fraktur=False,
        has_tables=True,
        has_handwriting=False,
        has_stamps=False,
        has_signatures=False,
        umlaut_words=["äöü", "Größe", "Überprüfung"],
    )


@pytest.fixture
def mock_sample() -> OCRTrainingSample:
    """Fixture für Mock-Sample."""
    sample = MagicMock(spec=OCRTrainingSample)
    sample.id = uuid4()
    sample.file_path = "/test/document.pdf"
    sample.file_hash = "abc123hash"
    sample.ground_truth_text = "Testtext"
    sample.language = "de"
    sample.document_type = "invoice"
    sample.status = TrainingSampleStatus.PENDING.value
    sample.created_at = datetime.now(timezone.utc)
    return sample


class TestOCRTrainingServiceSingleton:
    """Tests für Singleton-Pattern."""

    def test_get_ocr_training_service_returns_same_instance(self):
        """Singleton sollte immer dieselbe Instanz zurückgeben."""
        service1 = get_ocr_training_service()
        service2 = get_ocr_training_service()
        assert service1 is service2

    def test_service_is_instance_of_correct_class(self):
        """Service sollte korrekte Klasse sein."""
        service = get_ocr_training_service()
        assert isinstance(service, OCRTrainingService)


class TestTrainingSampleCRUD:
    """Tests für Training Sample CRUD-Operationen."""

    @pytest.mark.asyncio
    async def test_create_training_sample_success(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        sample_create_data: TrainingSampleCreate,
    ):
        """Neues Sample sollte erfolgreich erstellt werden."""
        # Mock: Kein Duplikat vorhanden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Mock refresh um Sample-ID zu setzen
        async def mock_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(timezone.utc)
        mock_db.refresh = mock_refresh

        sample = await ocr_training_service.create_training_sample(
            mock_db, sample_create_data
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert sample.file_path == sample_create_data.file_path
        assert sample.language == "de"
        assert sample.has_umlauts is True

    @pytest.mark.asyncio
    async def test_create_training_sample_returns_existing_on_duplicate(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        sample_create_data: TrainingSampleCreate,
        mock_sample: OCRTrainingSample,
    ):
        """Bei Duplikat (gleicher Hash) sollte existierendes Sample zurückgegeben werden."""
        # Mock: Duplikat vorhanden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sample
        mock_db.execute.return_value = mock_result

        result = await ocr_training_service.create_training_sample(
            mock_db, sample_create_data
        )

        assert result is mock_sample
        assert not mock_db.add.called

    @pytest.mark.asyncio
    async def test_get_training_sample_found(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_sample: OCRTrainingSample,
    ):
        """Vorhandenes Sample sollte gefunden werden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sample
        mock_db.execute.return_value = mock_result

        result = await ocr_training_service.get_training_sample(
            mock_db, mock_sample.id
        )

        assert result is mock_sample

    @pytest.mark.asyncio
    async def test_get_training_sample_not_found(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Nicht vorhandenes Sample sollte None zurückgeben."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await ocr_training_service.get_training_sample(
            mock_db, uuid4()
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_list_training_samples_with_filters(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_sample: OCRTrainingSample,
    ):
        """Samples sollten mit Filtern gelistet werden."""
        # Mock count result
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Mock samples result
        samples_result = MagicMock()
        samples_result.scalars.return_value.all.return_value = [mock_sample]

        mock_db.execute.side_effect = [count_result, samples_result]

        samples, total = await ocr_training_service.list_training_samples(
            mock_db,
            status=TrainingSampleStatus.PENDING.value,
            language="de",
            limit=10,
            offset=0,
        )

        assert total == 1
        assert len(samples) == 1
        assert samples[0] is mock_sample

    @pytest.mark.asyncio
    async def test_delete_training_sample_success(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_sample: OCRTrainingSample,
    ):
        """Vorhandenes Sample sollte gelöscht werden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sample
        mock_db.execute.return_value = mock_result

        result = await ocr_training_service.delete_training_sample(
            mock_db, mock_sample.id
        )

        assert result is True
        assert mock_db.delete.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_delete_training_sample_not_found(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Löschen eines nicht vorhandenen Samples sollte False zurückgeben."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await ocr_training_service.delete_training_sample(
            mock_db, uuid4()
        )

        assert result is False


class TestAnnotationVerificationWorkflow:
    """Tests für Annotation und Verification Workflow."""

    @pytest.mark.asyncio
    async def test_update_training_sample_sets_annotator(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_sample: OCRTrainingSample,
    ):
        """Update mit ground_truth_text sollte Annotator setzen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sample
        mock_db.execute.return_value = mock_result

        user_id = uuid4()
        update_data = TrainingSampleUpdate(
            ground_truth_text="Korrigierter Text mit Umlauten: äöü"
        )

        result = await ocr_training_service.update_training_sample(
            mock_db, mock_sample.id, update_data, user_id
        )

        assert mock_sample.annotated_by_id == user_id
        assert mock_sample.annotated_at is not None
        assert mock_sample.status == TrainingSampleStatus.ANNOTATED.value

    @pytest.mark.asyncio
    async def test_verify_training_sample_approved(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_sample: OCRTrainingSample,
    ):
        """Genehmigte Verifizierung sollte Status auf VERIFIED setzen."""
        mock_sample.status = TrainingSampleStatus.ANNOTATED.value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sample
        mock_db.execute.return_value = mock_result

        verifier_id = uuid4()

        result = await ocr_training_service.verify_training_sample(
            mock_db, mock_sample.id, verifier_id, approved=True
        )

        assert mock_sample.status == TrainingSampleStatus.VERIFIED.value
        assert mock_sample.verified_by_id == verifier_id
        assert mock_sample.verified_at is not None

    @pytest.mark.asyncio
    async def test_verify_training_sample_rejected(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_sample: OCRTrainingSample,
    ):
        """Abgelehnte Verifizierung sollte Status auf REJECTED setzen."""
        mock_sample.status = TrainingSampleStatus.ANNOTATED.value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sample
        mock_db.execute.return_value = mock_result

        verifier_id = uuid4()

        result = await ocr_training_service.verify_training_sample(
            mock_db, mock_sample.id, verifier_id,
            approved=False, notes="Falsche Annotation"
        )

        assert mock_sample.status == TrainingSampleStatus.REJECTED.value
        assert mock_sample.annotation_notes == "Falsche Annotation"


class TestValidationCorrections:
    """Tests für OCR-Korrekturen (Self-Learning)."""

    @pytest.mark.asyncio
    async def test_create_correction_success(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Korrektur sollte erfolgreich erstellt werden."""
        async def mock_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(timezone.utc)
        mock_db.refresh = mock_refresh

        correction_data = CorrectionCreate(
            document_id=uuid4(),
            original_text="Geschaft",
            corrected_text="Geschäft",
            correction_type=CorrectionType.UMLAUT,
            backend_used="deepseek",
            confidence_before=0.85,
        )

        user_id = uuid4()

        correction = await ocr_training_service.create_correction(
            mock_db, correction_data, user_id
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert correction.original_text == "Geschaft"
        assert correction.corrected_text == "Geschäft"
        assert correction.learning_processed is False

    @pytest.mark.asyncio
    async def test_list_corrections_unprocessed_only(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Nur unverarbeitete Korrekturen sollten gelistet werden."""
        mock_correction = MagicMock(spec=OCRValidationCorrection)
        mock_correction.learning_processed = False

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        corrections_result = MagicMock()
        corrections_result.scalars.return_value.all.return_value = [mock_correction]

        mock_db.execute.side_effect = [count_result, corrections_result]

        corrections, total = await ocr_training_service.list_corrections(
            mock_db, unprocessed_only=True
        )

        assert total == 1
        assert len(corrections) == 1
        assert corrections[0].learning_processed is False

    @pytest.mark.asyncio
    async def test_mark_corrections_processed(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Korrekturen sollten als verarbeitet markiert werden."""
        mock_correction = MagicMock(spec=OCRValidationCorrection)
        mock_correction.learning_processed = False
        correction_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_correction
        mock_db.execute.return_value = mock_result

        count = await ocr_training_service.mark_corrections_processed(
            mock_db, [correction_id]
        )

        assert count == 1
        assert mock_correction.learning_processed is True
        assert mock_correction.learning_processed_at is not None


class TestTrainingBatches:
    """Tests für Training Batch Management."""

    @pytest.fixture
    def mock_batch(self) -> OCRTrainingBatch:
        """Fixture für Mock-Batch."""
        batch = MagicMock(spec=OCRTrainingBatch)
        batch.id = uuid4()
        batch.name = "Test Batch"
        batch.status = BatchStatus.READY.value
        batch.target_size = 100
        batch.actual_size = 50
        batch.items_pending = 50
        batch.items_completed = 0
        return batch

    @pytest.mark.asyncio
    async def test_create_training_batch_success(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Batch sollte erfolgreich erstellt werden."""
        async def mock_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(timezone.utc)
        mock_db.refresh = mock_refresh

        batch_data = BatchCreate(
            name="Test Batch Q4",
            description="Quarterly validation batch",
            batch_type=BatchType.STRATIFIED,
            target_size=100,
            auto_populate=False,
        )

        user_id = uuid4()

        batch = await ocr_training_service.create_training_batch(
            mock_db, batch_data, user_id
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert batch.name == "Test Batch Q4"
        assert batch.target_size == 100

    @pytest.mark.asyncio
    async def test_start_batch_changes_status(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_batch: OCRTrainingBatch,
    ):
        """Batch starten sollte Status auf IN_PROGRESS ändern."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_batch
        mock_db.execute.return_value = mock_result

        result = await ocr_training_service.start_batch(
            mock_db, mock_batch.id
        )

        assert mock_batch.status == BatchStatus.IN_PROGRESS.value

    @pytest.mark.asyncio
    async def test_start_batch_fails_if_not_ready(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_batch: OCRTrainingBatch,
    ):
        """Batch starten sollte fehlschlagen wenn nicht READY."""
        mock_batch.status = BatchStatus.COMPLETED.value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_batch
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="kann nicht gestartet werden"):
            await ocr_training_service.start_batch(mock_db, mock_batch.id)

    @pytest.mark.asyncio
    async def test_complete_batch_sets_completed_at(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
        mock_batch: OCRTrainingBatch,
    ):
        """Batch abschließen sollte completed_at setzen."""
        mock_batch.status = BatchStatus.IN_PROGRESS.value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_batch
        mock_db.execute.return_value = mock_result

        result = await ocr_training_service.complete_batch(
            mock_db, mock_batch.id
        )

        assert mock_batch.status == BatchStatus.COMPLETED.value
        assert mock_batch.completed_at is not None


class TestStatistics:
    """Tests für Statistik-Funktionen."""

    @pytest.mark.asyncio
    async def test_get_training_overview_stats(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Übersichtsstatistiken sollten korrekt aggregiert werden."""
        # Wir müssen mehrere execute-Aufrufe mocken
        # Status counts, total, verified, pending, active batches, corrections, etc.

        def mock_execute_returns(values):
            """Helper um mehrere execute-Aufrufe zu mocken."""
            results = []
            for val in values:
                mock_result = MagicMock()
                if isinstance(val, int):
                    mock_result.scalar.return_value = val
                elif isinstance(val, list):
                    mock_result.all.return_value = val
                results.append(mock_result)
            return results

        # Mock für verschiedene Counts
        mock_db.execute.side_effect = [
            # Status counts (4 mal für jeden Status)
            MagicMock(scalar=MagicMock(return_value=10)),  # PENDING
            MagicMock(scalar=MagicMock(return_value=20)),  # ANNOTATED
            MagicMock(scalar=MagicMock(return_value=50)),  # VERIFIED
            MagicMock(scalar=MagicMock(return_value=5)),   # REJECTED
            # Total samples
            MagicMock(scalar=MagicMock(return_value=85)),
            # Active batches
            MagicMock(scalar=MagicMock(return_value=2)),
            # Recent corrections
            MagicMock(scalar=MagicMock(return_value=15)),
            # Unprocessed corrections
            MagicMock(scalar=MagicMock(return_value=8)),
            # Samples by language
            MagicMock(all=MagicMock(return_value=[("de", 40), ("en", 10)])),
            # Samples by type
            MagicMock(all=MagicMock(return_value=[("invoice", 30), ("contract", 20)])),
        ]

        stats = await ocr_training_service.get_training_overview_stats(mock_db)

        assert stats.total_samples == 85
        assert stats.verified_samples == 50
        assert stats.pending_annotations == 10
        assert stats.active_batches == 2
        assert stats.recent_corrections_24h == 15
        assert stats.unprocessed_corrections == 8
        assert "de" in stats.samples_by_language
        assert "invoice" in stats.samples_by_document_type


class TestGermanTextHandling:
    """Tests für deutsche Texte und Umlaute."""

    @pytest.mark.asyncio
    async def test_sample_with_umlauts_stored_correctly(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Samples mit Umlauten sollten korrekt gespeichert werden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        async def mock_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(timezone.utc)
        mock_db.refresh = mock_refresh

        sample_data = TrainingSampleCreate(
            file_path="/test/umlaut_doc.pdf",
            ground_truth_text="Größe: 5m², Höhe: 2,5m, Fläche: 12,5m²",
            language="de",
            has_umlauts=True,
            umlaut_words=["Größe", "Höhe", "Fläche"],
        )

        sample = await ocr_training_service.create_training_sample(
            mock_db, sample_data
        )

        assert "ö" in sample.ground_truth_text
        assert "ä" not in sample.ground_truth_text  # No ä in this text
        assert sample.umlaut_words == ["Größe", "Höhe", "Fläche"]

    @pytest.mark.asyncio
    async def test_umlaut_correction_tracked(
        self,
        ocr_training_service: OCRTrainingService,
        mock_db: AsyncMock,
    ):
        """Umlaut-Korrekturen sollten korrekt erfasst werden."""
        async def mock_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(timezone.utc)
        mock_db.refresh = mock_refresh

        correction_data = CorrectionCreate(
            document_id=uuid4(),
            original_text="Grosse Strasse",
            corrected_text="Große Straße",
            correction_type=CorrectionType.UMLAUT,
            field_corrected="address",
            backend_used="surya",
        )

        correction = await ocr_training_service.create_correction(
            mock_db, correction_data, uuid4()
        )

        assert correction.original_text == "Grosse Strasse"
        assert correction.corrected_text == "Große Straße"
        assert correction.correction_type == CorrectionType.UMLAUT.value
