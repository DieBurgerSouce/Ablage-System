# -*- coding: utf-8 -*-
"""
Tests fuer Training API Endpoints.

Testet alle Training API Endpunkte:
- Training Samples CRUD
- Benchmarks (Run, Compare, Backends)
- Corrections (Self-Learning)
- Training Batches
- Statistics
- Migration
- Bulk Processing
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from io import BytesIO

from fastapi import HTTPException


# ==================== Training Samples Tests ====================

class TestTrainingSamplesEndpoints:
    """Tests fuer Training Samples CRUD."""

    @pytest.fixture
    def mock_training_service(self):
        with patch('app.api.v1.training.get_ocr_training_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_admin_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "admin@example.com"
        user.role = "admin"
        return user

    @pytest.fixture
    def mock_editor_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "editor@example.com"
        user.role = "editor"
        return user

    @pytest.mark.asyncio
    async def test_list_training_samples(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Samples auflisten."""
        from app.api.v1.training import list_training_samples

        sample_id = uuid4()
        mock_training_service.list_training_samples = AsyncMock(return_value=(
            [MagicMock(
                id=sample_id,
                document_type="invoice",
                language="de",
                status="pending",
            )],
            1,
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await list_training_samples(
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.total == 1
            assert len(result.samples) == 1

    @pytest.mark.asyncio
    async def test_list_training_samples_with_filters(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Samples mit Filtern auflisten."""
        from app.api.v1.training import list_training_samples

        mock_training_service.list_training_samples = AsyncMock(return_value=([], 0))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            await list_training_samples(
                status="verified",
                language="de",
                document_type="invoice",
                has_ground_truth=True,
                verified_only=True,
                limit=100,
                offset=50,
                current_user=mock_admin_user,
                db=mock_db,
            )

            mock_training_service.list_training_samples.assert_called_once()
            call_args = mock_training_service.list_training_samples.call_args
            assert call_args.kwargs["status"] == "verified"
            assert call_args.kwargs["language"] == "de"

    @pytest.mark.asyncio
    async def test_create_training_sample(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Sample erstellen."""
        from app.api.v1.training import create_training_sample
        from app.db.schemas import TrainingSampleCreate

        sample_id = uuid4()
        mock_training_service.create_training_sample = AsyncMock(return_value=MagicMock(
            id=sample_id,
            document_type="invoice",
            language="de",
            status="pending",
        ))

        sample_data = MagicMock(spec=TrainingSampleCreate)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await create_training_sample(
                sample_data=sample_data,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.id == sample_id

    @pytest.mark.asyncio
    async def test_get_training_sample(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte einzelnes Training Sample zurueckgeben."""
        from app.api.v1.training import get_training_sample

        sample_id = uuid4()
        mock_training_service.get_training_sample = AsyncMock(return_value=MagicMock(
            id=sample_id,
            document_type="invoice",
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await get_training_sample(
                sample_id=sample_id,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.id == sample_id

    @pytest.mark.asyncio
    async def test_get_training_sample_not_found(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte 404 bei nicht gefundenem Sample werfen."""
        from app.api.v1.training import get_training_sample

        mock_training_service.get_training_sample = AsyncMock(return_value=None)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            with pytest.raises(HTTPException) as exc:
                await get_training_sample(
                    sample_id=uuid4(),
                    current_user=mock_admin_user,
                    db=mock_db,
                )

            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_training_sample(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Sample aktualisieren."""
        from app.api.v1.training import update_training_sample
        from app.db.schemas import TrainingSampleUpdate

        sample_id = uuid4()
        mock_training_service.update_training_sample = AsyncMock(return_value=MagicMock(
            id=sample_id,
            ground_truth_text="Korrigierter Text",
        ))

        update_data = MagicMock(spec=TrainingSampleUpdate)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await update_training_sample(
                sample_id=sample_id,
                update_data=update_data,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.ground_truth_text == "Korrigierter Text"

    @pytest.mark.asyncio
    async def test_verify_training_sample(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Sample verifizieren (Admin-only)."""
        from app.api.v1.training import verify_training_sample

        sample_id = uuid4()
        mock_training_service.verify_training_sample = AsyncMock(return_value=MagicMock(
            id=sample_id,
            status="verified",
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await verify_training_sample(
                sample_id=sample_id,
                approved=True,
                notes="Verifiziert",
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.status == "verified"

    @pytest.mark.asyncio
    async def test_delete_training_sample(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Sample loeschen."""
        from app.api.v1.training import delete_training_sample

        mock_training_service.delete_training_sample = AsyncMock(return_value=True)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            # Should not raise
            await delete_training_sample(
                sample_id=uuid4(),
                current_user=mock_admin_user,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_delete_training_sample_not_found(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte 404 bei nicht gefundenem Sample werfen."""
        from app.api.v1.training import delete_training_sample

        mock_training_service.delete_training_sample = AsyncMock(return_value=False)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            with pytest.raises(HTTPException) as exc:
                await delete_training_sample(
                    sample_id=uuid4(),
                    current_user=mock_admin_user,
                    db=mock_db,
                )

            assert exc.value.status_code == 404


# ==================== Benchmark Tests ====================

class TestBenchmarkEndpoints:
    """Tests fuer Benchmark-Endpoints."""

    @pytest.fixture
    def mock_benchmark_service(self):
        with patch('app.api.v1.training.get_benchmark_runner_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_admin_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_run_benchmark(self, mock_db, mock_admin_user):
        """Sollte Benchmark starten."""
        from app.api.v1.training import run_benchmark
        from app.db.schemas import BenchmarkRunRequest

        with patch('app.api.v1.training.run_benchmark_batch') as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-123")

            request = MagicMock(spec=BenchmarkRunRequest)
            request.sample_ids = [uuid4(), uuid4()]
            request.backends = ["deepseek", "got_ocr"]
            request.force_rerun = False

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await run_benchmark(
                    request=request,
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result.task_id == "task-123"
                assert result.success is True

    @pytest.mark.asyncio
    async def test_compare_backends(self, mock_benchmark_service, mock_db, mock_admin_user):
        """Sollte Backend-Vergleich zurueckgeben."""
        from app.api.v1.training import compare_backends

        mock_benchmark_service.get_backend_comparison = AsyncMock(return_value=MagicMock(
            backends=["deepseek", "got_ocr"],
            total_samples=100,
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await compare_backends(
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert "deepseek" in result.backends

    @pytest.mark.asyncio
    async def test_get_available_backends(self, mock_benchmark_service, mock_admin_user):
        """Sollte verfuegbare Backends zurueckgeben."""
        from app.api.v1.training import get_available_backends

        mock_benchmark_service.get_available_backends.return_value = [
            "deepseek", "got_ocr", "surya"
        ]

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await get_available_backends(current_user=mock_admin_user)

            assert "deepseek" in result["backends"]


# ==================== Corrections Tests ====================

class TestCorrectionsEndpoints:
    """Tests fuer Self-Learning Corrections."""

    @pytest.fixture
    def mock_training_service(self):
        with patch('app.api.v1.training.get_ocr_training_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_create_correction(self, mock_training_service, mock_db, mock_user):
        """Sollte Korrektur erstellen."""
        from app.api.v1.training import create_correction
        from app.db.schemas import CorrectionCreate

        correction_id = uuid4()
        mock_training_service.create_correction = AsyncMock(return_value=MagicMock(
            id=correction_id,
            original_text="Fehlertext",
            corrected_text="Korrigierter Text",
        ))

        correction_data = MagicMock(spec=CorrectionCreate)

        with patch('app.api.v1.training.get_current_active_user') as mock_auth:
            mock_auth.return_value = mock_user

            result = await create_correction(
                correction_data=correction_data,
                current_user=mock_user,
                db=mock_db,
            )

            assert result.id == correction_id

    @pytest.mark.asyncio
    async def test_list_corrections(self, mock_training_service, mock_db, mock_user):
        """Sollte Korrekturen auflisten (Admin-only)."""
        from app.api.v1.training import list_corrections

        mock_training_service.list_corrections = AsyncMock(return_value=(
            [MagicMock(id=uuid4())],
            10,
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            result = await list_corrections(
                current_user=mock_user,
                db=mock_db,
            )

            assert result.total == 10


# ==================== Training Batches Tests ====================

class TestTrainingBatchesEndpoints:
    """Tests fuer Training Batch Workflow."""

    @pytest.fixture
    def mock_training_service(self):
        with patch('app.api.v1.training.get_ocr_training_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_admin_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_list_training_batches(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Batches auflisten."""
        from app.api.v1.training import list_training_batches

        mock_training_service.list_training_batches = AsyncMock(return_value=(
            [MagicMock(id=uuid4(), name="Batch 1")],
            5,
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await list_training_batches(
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.total == 5

    @pytest.mark.asyncio
    async def test_create_training_batch(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Training Batch erstellen."""
        from app.api.v1.training import create_training_batch
        from app.db.schemas import BatchCreate

        batch_id = uuid4()
        mock_training_service.create_training_batch = AsyncMock(return_value=MagicMock(
            id=batch_id,
            name="Stichprobe Q1",
        ))

        batch_data = MagicMock(spec=BatchCreate)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await create_training_batch(
                batch_data=batch_data,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.id == batch_id

    @pytest.mark.asyncio
    async def test_get_training_batch(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte einzelnen Batch zurueckgeben."""
        from app.api.v1.training import get_training_batch

        batch_id = uuid4()
        mock_training_service.get_training_batch = AsyncMock(return_value=MagicMock(
            id=batch_id,
            items=[MagicMock(), MagicMock()],
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await get_training_batch(
                batch_id=batch_id,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.id == batch_id

    @pytest.mark.asyncio
    async def test_start_training_batch(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Batch starten."""
        from app.api.v1.training import start_training_batch

        batch_id = uuid4()
        mock_training_service.start_batch = AsyncMock(return_value=MagicMock(
            id=batch_id,
            status="in_progress",
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await start_training_batch(
                batch_id=batch_id,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.status == "in_progress"

    @pytest.mark.asyncio
    async def test_complete_training_batch(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Batch abschliessen."""
        from app.api.v1.training import complete_training_batch

        batch_id = uuid4()
        mock_training_service.complete_batch = AsyncMock(return_value=MagicMock(
            id=batch_id,
            status="completed",
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await complete_training_batch(
                batch_id=batch_id,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_get_next_batch_item(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte naechstes Batch-Item zurueckgeben."""
        from app.api.v1.training import get_next_batch_item

        item_id = uuid4()
        mock_training_service.get_next_batch_item = AsyncMock(return_value=MagicMock(
            id=item_id,
            status="pending",
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await get_next_batch_item(
                batch_id=uuid4(),
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.id == item_id

    @pytest.mark.asyncio
    async def test_get_next_batch_item_none_available(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte 404 wenn keine Items verfuegbar."""
        from app.api.v1.training import get_next_batch_item

        mock_training_service.get_next_batch_item = AsyncMock(return_value=None)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            with pytest.raises(HTTPException) as exc:
                await get_next_batch_item(
                    batch_id=uuid4(),
                    current_user=mock_admin_user,
                    db=mock_db,
                )

            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_batch_item(self, mock_training_service, mock_db, mock_admin_user):
        """Sollte Batch-Item aktualisieren."""
        from app.api.v1.training import update_batch_item
        from app.db.schemas import BatchItemUpdate

        item_id = uuid4()
        mock_training_service.update_batch_item = AsyncMock(return_value=MagicMock(
            id=item_id,
            status="reviewed",
        ))

        update_data = MagicMock(spec=BatchItemUpdate)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_admin_user

            result = await update_batch_item(
                batch_id=uuid4(),
                item_id=item_id,
                update_data=update_data,
                current_user=mock_admin_user,
                db=mock_db,
            )

            assert result.status == "reviewed"


# ==================== Statistics Tests ====================

class TestStatisticsEndpoints:
    """Tests fuer Statistics-Endpoints."""

    @pytest.fixture
    def mock_training_service(self):
        with patch('app.api.v1.training.get_ocr_training_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_feedback_service(self):
        with patch('app.api.v1.training.get_feedback_learning_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_training_overview(self, mock_training_service, mock_db, mock_user):
        """Sollte Training-Uebersicht zurueckgeben."""
        from app.api.v1.training import get_training_overview

        mock_training_service.get_training_overview_stats = AsyncMock(return_value=MagicMock(
            total_samples=1000,
            verified_samples=800,
            pending_samples=200,
        ))

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            result = await get_training_overview(
                current_user=mock_user,
                db=mock_db,
            )

            assert result.total_samples == 1000

    @pytest.mark.asyncio
    async def test_get_backend_stats(self, mock_training_service, mock_db, mock_user):
        """Sollte Backend-Statistiken zurueckgeben."""
        from app.api.v1.training import get_backend_stats

        mock_training_service.get_backend_stats = AsyncMock(return_value=[
            MagicMock(backend="deepseek", avg_cer=0.02),
            MagicMock(backend="got_ocr", avg_cer=0.03),
        ])

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            result = await get_backend_stats(
                days=30,
                current_user=mock_user,
                db=mock_db,
            )

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_trend_data(self, mock_feedback_service, mock_db, mock_user):
        """Sollte Trend-Daten zurueckgeben."""
        from app.api.v1.training import get_trend_data

        mock_feedback_service.get_trend_data = AsyncMock(return_value=[
            {"date": "2024-01-01", "cer": 0.02},
            {"date": "2024-01-02", "cer": 0.019},
        ])

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            result = await get_trend_data(
                current_user=mock_user,
                db=mock_db,
            )

            assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_get_learned_weights(self, mock_feedback_service, mock_db, mock_user):
        """Sollte gelernte Gewichte zurueckgeben."""
        from app.api.v1.training import get_learned_weights

        mock_weights = MagicMock()
        mock_weights.to_dict.return_value = {
            "deepseek": 0.4,
            "got_ocr": 0.35,
            "surya": 0.25,
        }
        mock_feedback_service.get_learned_weights = AsyncMock(return_value=mock_weights)

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            result = await get_learned_weights(
                current_user=mock_user,
                db=mock_db,
            )

            assert result["deepseek"] == 0.4

    @pytest.mark.asyncio
    async def test_get_backend_recommendation(self, mock_feedback_service, mock_db, mock_user):
        """Sollte Backend-Empfehlung zurueckgeben."""
        from app.api.v1.training import get_backend_recommendation

        mock_feedback_service.get_backend_recommendation = AsyncMock(
            return_value=("deepseek", 0.95)
        )

        with patch('app.api.v1.training.get_current_active_user') as mock_auth:
            mock_auth.return_value = mock_user

            result = await get_backend_recommendation(
                document_type="invoice",
                has_umlauts=True,
                has_tables=False,
                current_user=mock_user,
                db=mock_db,
            )

            assert result["recommended_backend"] == "deepseek"
            assert result["confidence"] == 0.95


# ==================== Migration Tests ====================

class TestMigrationEndpoints:
    """Tests fuer Migration-Endpoints."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_admin_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_get_migration_status(self, mock_db, mock_admin_user):
        """Sollte Migration-Status zurueckgeben."""
        from app.api.v1.training import get_migration_status

        with patch('app.api.v1.training.get_training_migration_service') as mock_getter:
            mock_service = MagicMock()
            mock_service.check_migration_sources = AsyncMock(return_value={
                "sqlite": True,
                "files": True,
            })
            mock_service.get_migration_stats.return_value = {
                "migrated": 500,
            }
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await get_migration_status(
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result["sources"]["sqlite"] is True

    @pytest.mark.asyncio
    async def test_migrate_from_sqlite_dry_run(self, mock_db, mock_admin_user):
        """Sollte SQLite-Migration simulieren."""
        from app.api.v1.training import migrate_from_sqlite

        with patch('app.api.v1.training.get_training_migration_service') as mock_getter:
            mock_service = MagicMock()
            mock_service.migrate_from_sqlite = AsyncMock(return_value={
                "dry_run": True,
                "would_migrate": 100,
            })
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await migrate_from_sqlite(
                    dry_run=True,
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_import_training_files(self, mock_db, mock_admin_user):
        """Sollte Training-Dateien importieren."""
        from app.api.v1.training import import_training_files

        with patch('app.api.v1.training.get_training_migration_service') as mock_getter:
            mock_service = MagicMock()
            mock_service.import_training_files = AsyncMock(return_value={
                "imported": 50,
                "skipped": 10,
            })
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await import_training_files(
                    language="de",
                    dry_run=False,
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result["imported"] == 50

    @pytest.mark.asyncio
    async def test_discover_training_files(self, mock_db, mock_admin_user):
        """Sollte Training-Dateien entdecken."""
        from app.api.v1.training import discover_training_files

        with patch('app.api.v1.training.get_training_migration_service') as mock_getter:
            mock_service = MagicMock()
            mock_service.discover_training_files = AsyncMock(return_value=[
                {"path": "/data/doc1.pdf"},
                {"path": "/data/doc2.tiff"},
            ])
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await discover_training_files(
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result["total"] == 2


# ==================== Bulk Processing Tests ====================

class TestBulkProcessingEndpoints:
    """Tests fuer Bulk Processing Endpoints."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_admin_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_list_bulk_processing_jobs(self, mock_db, mock_admin_user):
        """Sollte Bulk Processing Jobs auflisten."""
        from app.api.v1.training import list_bulk_processing_jobs

        with patch('app.api.v1.training.get_bulk_ocr_processing_service') as mock_getter:
            mock_service = MagicMock()
            mock_service.list_jobs = AsyncMock(return_value=(
                [MagicMock(id=uuid4(), name="Job 1")],
                5,
            ))
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await list_bulk_processing_jobs(
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result.total == 5

    @pytest.mark.asyncio
    async def test_create_bulk_processing_job_gpu(self, mock_db, mock_admin_user):
        """Sollte Bulk Processing Job mit GPU-Backend erstellen."""
        from app.api.v1.training import create_bulk_processing_job
        from app.db import schemas

        with patch('app.api.v1.training.get_bulk_ocr_processing_service') as mock_getter:
            job_id = uuid4()
            mock_service = MagicMock()
            mock_service.create_job = AsyncMock(return_value=MagicMock(
                id=job_id,
                total_documents=100,
            ))
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.run_bulk_processing_job') as mock_task:
                mock_task.delay = MagicMock()

                request = MagicMock(spec=schemas.BulkProcessingJobCreate)
                request.name = "Test Job"
                request.description = "Test Description"
                request.backends = ["deepseek"]  # GPU backend
                request.configuration = {}

                with patch('app.api.v1.training.require_any_role') as mock_role:
                    mock_role.return_value = lambda: mock_admin_user

                    result = await create_bulk_processing_job(
                        request=request,
                        current_user=mock_admin_user,
                        db=mock_db,
                    )

                    assert result.success is True
                    assert result.job_id == job_id
                    mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_bulk_processing_job_cpu(self, mock_db, mock_admin_user):
        """Sollte Bulk Processing Job mit CPU-Backend erstellen."""
        from app.api.v1.training import create_bulk_processing_job
        from app.db import schemas

        with patch('app.api.v1.training.get_bulk_ocr_processing_service') as mock_getter:
            job_id = uuid4()
            mock_service = MagicMock()
            mock_service.create_job = AsyncMock(return_value=MagicMock(
                id=job_id,
                total_documents=100,
            ))
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.run_bulk_processing_job_cpu') as mock_task:
                mock_task.delay = MagicMock()

                request = MagicMock(spec=schemas.BulkProcessingJobCreate)
                request.name = "CPU Job"
                request.description = "CPU-only job"
                request.backends = ["surya"]  # CPU backend
                request.configuration = {}

                with patch('app.api.v1.training.require_any_role') as mock_role:
                    mock_role.return_value = lambda: mock_admin_user

                    result = await create_bulk_processing_job(
                        request=request,
                        current_user=mock_admin_user,
                        db=mock_db,
                    )

                    assert result.success is True
                    mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_bulk_processing_job(self, mock_db, mock_admin_user):
        """Sollte einzelnen Bulk Processing Job zurueckgeben."""
        from app.api.v1.training import get_bulk_processing_job

        with patch('app.api.v1.training.get_bulk_ocr_processing_service') as mock_getter:
            job_id = uuid4()
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=MagicMock(
                id=job_id,
                status="running",
            ))
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await get_bulk_processing_job(
                    job_id=job_id,
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result.id == job_id

    @pytest.mark.asyncio
    async def test_get_bulk_processing_job_not_found(self, mock_db, mock_admin_user):
        """Sollte 404 bei nicht gefundenem Job werfen."""
        from app.api.v1.training import get_bulk_processing_job

        with patch('app.api.v1.training.get_bulk_ocr_processing_service') as mock_getter:
            mock_service = MagicMock()
            mock_service.get_job = AsyncMock(return_value=None)
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                with pytest.raises(HTTPException) as exc:
                    await get_bulk_processing_job(
                        job_id=uuid4(),
                        current_user=mock_admin_user,
                        db=mock_db,
                    )

                assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_bulk_processing_progress(self, mock_db, mock_admin_user):
        """Sollte Bulk Processing Fortschritt zurueckgeben."""
        from app.api.v1.training import get_bulk_processing_progress

        with patch('app.api.v1.training.get_bulk_ocr_processing_service') as mock_getter:
            mock_service = MagicMock()
            mock_service.get_progress = AsyncMock(return_value=MagicMock(
                processed=50,
                total=100,
                percentage=50.0,
            ))
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await get_bulk_processing_progress(
                    job_id=uuid4(),
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result.percentage == 50.0

    @pytest.mark.asyncio
    async def test_pause_bulk_processing_job(self, mock_db, mock_admin_user):
        """Sollte Bulk Processing Job pausieren."""
        from app.api.v1.training import pause_bulk_processing_job

        with patch('app.api.v1.training.get_bulk_ocr_processing_service') as mock_getter:
            job_id = uuid4()
            mock_service = MagicMock()
            mock_service.pause_job = AsyncMock(return_value=MagicMock(
                id=job_id,
                processed_documents=50,
                total_documents=100,
            ))
            mock_getter.return_value = mock_service

            with patch('app.api.v1.training.require_any_role') as mock_role:
                mock_role.return_value = lambda: mock_admin_user

                result = await pause_bulk_processing_job(
                    job_id=job_id,
                    current_user=mock_admin_user,
                    db=mock_db,
                )

                assert result.success is True
                assert result.processed_documents == 50


# ==================== Sample Preview Tests ====================

class TestSamplePreviewEndpoint:
    """Tests fuer Sample-Preview-Endpoint."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_sample_preview_not_found(self, mock_db, mock_user):
        """Sollte 404 bei nicht gefundenem Sample werfen."""
        from app.api.v1.training import get_sample_preview

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            with pytest.raises(HTTPException) as exc:
                await get_sample_preview(
                    sample_id=uuid4(),
                    current_user=mock_user,
                    db=mock_db,
                )

            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_sample_preview_no_file_path(self, mock_db, mock_user):
        """Sollte 404 bei fehlendem Dateipfad werfen."""
        from app.api.v1.training import get_sample_preview

        mock_sample = MagicMock()
        mock_sample.file_path = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sample
        mock_db.execute.return_value = mock_result

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            with pytest.raises(HTTPException) as exc:
                await get_sample_preview(
                    sample_id=uuid4(),
                    current_user=mock_user,
                    db=mock_db,
                )

            assert exc.value.status_code == 404
            assert "Dateipfad" in exc.value.detail


# ==================== Sample Benchmarks Tests ====================

class TestSampleBenchmarksEndpoint:
    """Tests fuer Sample-Benchmarks-Endpoint."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_sample_benchmarks(self, mock_db, mock_user):
        """Sollte Benchmarks fuer ein Sample zurueckgeben."""
        from app.api.v1.training import get_sample_benchmarks
        from datetime import datetime, timezone

        benchmark_id = uuid4()
        sample_id = uuid4()

        mock_benchmark = MagicMock()
        mock_benchmark.id = benchmark_id
        mock_benchmark.training_sample_id = sample_id
        mock_benchmark.backend_name = "deepseek"
        mock_benchmark.backend_version = "1.0"
        mock_benchmark.raw_text = "Test text"
        mock_benchmark.confidence_score = 0.95
        mock_benchmark.cer = 0.02
        mock_benchmark.wer = 0.05
        mock_benchmark.umlaut_accuracy = 0.99
        mock_benchmark.capitalization_accuracy = 0.98
        mock_benchmark.field_accuracies = {}
        mock_benchmark.error_patterns = []
        mock_benchmark.insertions = 1
        mock_benchmark.deletions = 2
        mock_benchmark.substitutions = 3
        mock_benchmark.processing_time_ms = 1500
        mock_benchmark.gpu_memory_mb = 4096
        mock_benchmark.processed_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_benchmark]
        mock_db.execute.return_value = mock_result

        with patch('app.api.v1.training.require_any_role') as mock_role:
            mock_role.return_value = lambda: mock_user

            result = await get_sample_benchmarks(
                sample_id=sample_id,
                current_user=mock_user,
                db=mock_db,
            )

            assert len(result) == 1
            assert result[0]["backend_name"] == "deepseek"
            assert result[0]["cer"] == 0.02
