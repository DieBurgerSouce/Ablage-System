# -*- coding: utf-8 -*-
"""
OCR Training API für Ablage-System OCR.

Endpoints für das OCR Training und Validation System:
- Training Samples CRUD
- Benchmark-Ausführung und Vergleich
- Stichproben-Batch-Workflow
- Self-Learning Korrekturen
- Training-Statistiken

Feinpoliert und durchdacht - Enterprise-grade OCR Training.
"""

from typing import Optional, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.schemas import (
    # Training Samples
    TrainingSampleCreate,
    TrainingSampleUpdate,
    TrainingSampleResponse,
    TrainingSampleListResponse,
    # Benchmarks
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BackendComparisonResponse,
    BenchmarkResponse,
    # Corrections
    CorrectionCreate,
    CorrectionResponse,
    CorrectionListResponse,
    # Batches
    BatchCreate,
    BatchResponse,
    BatchDetailResponse,
    BatchListResponse,
    BatchItemUpdate,
    BatchItemResponse,
    # Stats
    TrainingStatsResponse,
    TrainingOverviewStats,
    BackendStats,
    TrendResponse,
)
from app.api.dependencies import (
    get_current_active_user,
    get_db,
)
from app.core.rbac import require_role, require_any_role
from app.services.ocr_training_service import get_ocr_training_service
from app.services.benchmark_runner_service import get_benchmark_runner_service
from app.services.feedback_learning_service import get_feedback_learning_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/training", tags=["training"])


# ==================== Training Samples ====================

@router.get("/samples", response_model=TrainingSampleListResponse)
async def list_training_samples(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    language: Optional[str] = Query(None, description="Filter nach Sprache"),
    document_type: Optional[str] = Query(None, description="Filter nach Dokumenttyp"),
    has_ground_truth: Optional[bool] = Query(None, description="Hat Ground Truth Text"),
    verified_only: bool = Query(False, description="Nur verifizierte Samples"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    offset: int = Query(0, ge=0, description="Offset für Paginierung"),
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet Training Samples mit optionalen Filtern auf.

    Erfordert Editor- oder Admin-Rolle.
    """
    service = get_ocr_training_service()
    samples, total = await service.list_training_samples(
        db=db,
        status=status,
        language=language,
        document_type=document_type,
        has_ground_truth=has_ground_truth,
        verified_only=verified_only,
        limit=limit,
        offset=offset
    )

    return TrainingSampleListResponse(
        samples=[TrainingSampleResponse.model_validate(s) for s in samples],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/samples", response_model=TrainingSampleResponse, status_code=201)
async def create_training_sample(
    sample_data: TrainingSampleCreate,
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt ein neues Training Sample.

    Erfordert Editor- oder Admin-Rolle.
    """
    service = get_ocr_training_service()
    sample = await service.create_training_sample(
        db=db,
        sample_data=sample_data,
        user_id=current_user.id
    )

    return TrainingSampleResponse.model_validate(sample)


@router.get("/samples/{sample_id}", response_model=TrainingSampleResponse)
async def get_training_sample(
    sample_id: UUID = Path(..., description="Training Sample ID"),
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt ein einzelnes Training Sample mit Benchmarks.
    """
    service = get_ocr_training_service()
    sample = await service.get_training_sample(db=db, sample_id=sample_id)

    if not sample:
        raise HTTPException(status_code=404, detail="Training Sample nicht gefunden")

    return TrainingSampleResponse.model_validate(sample)


@router.put("/samples/{sample_id}", response_model=TrainingSampleResponse)
async def update_training_sample(
    sample_id: UUID,
    update_data: TrainingSampleUpdate,
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert ein Training Sample (Editor-Annotation).

    Erfordert Editor- oder Admin-Rolle.
    """
    service = get_ocr_training_service()
    sample = await service.update_training_sample(
        db=db,
        sample_id=sample_id,
        update_data=update_data,
        user_id=current_user.id
    )

    if not sample:
        raise HTTPException(status_code=404, detail="Training Sample nicht gefunden")

    return TrainingSampleResponse.model_validate(sample)


@router.post("/samples/{sample_id}/verify", response_model=TrainingSampleResponse)
async def verify_training_sample(
    sample_id: UUID,
    approved: bool = Query(..., description="Genehmigt oder abgelehnt"),
    notes: Optional[str] = Query(None, description="Optionale Notizen"),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin-Verifizierung eines annotierten Samples.

    Erfordert Admin-Rolle.
    """
    service = get_ocr_training_service()
    sample = await service.verify_training_sample(
        db=db,
        sample_id=sample_id,
        verifier_id=current_user.id,
        approved=approved,
        notes=notes
    )

    if not sample:
        raise HTTPException(status_code=404, detail="Training Sample nicht gefunden")

    return TrainingSampleResponse.model_validate(sample)


@router.delete("/samples/{sample_id}", status_code=204)
async def delete_training_sample(
    sample_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Löscht ein Training Sample.

    Erfordert Admin-Rolle.
    """
    service = get_ocr_training_service()
    deleted = await service.delete_training_sample(db=db, sample_id=sample_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Training Sample nicht gefunden")


@router.get("/samples/{sample_id}/benchmarks")
async def get_sample_benchmarks(
    sample_id: UUID = Path(..., description="Training Sample ID"),
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt alle Benchmark-Ergebnisse fuer ein spezifisches Sample.

    Gibt die OCR-Ergebnisse aller Backends fuer dieses Sample zurueck.
    """
    from app.db.models import OCRBackendBenchmark
    from sqlalchemy import select

    result = await db.execute(
        select(OCRBackendBenchmark)
        .where(OCRBackendBenchmark.training_sample_id == sample_id)
        .order_by(OCRBackendBenchmark.backend_name)
    )
    benchmarks = result.scalars().all()

    return [
        {
            "id": str(b.id),
            "training_sample_id": str(b.training_sample_id),
            "backend_name": b.backend_name,
            "backend_version": b.backend_version,
            "raw_text": b.raw_text,
            "confidence_score": b.confidence_score,
            "cer": b.cer,
            "wer": b.wer,
            "umlaut_accuracy": b.umlaut_accuracy,
            "capitalization_accuracy": b.capitalization_accuracy,
            "field_accuracies": b.field_accuracies,
            "error_patterns": b.error_patterns,
            "insertions": b.insertions,
            "deletions": b.deletions,
            "substitutions": b.substitutions,
            "processing_time_ms": b.processing_time_ms,
            "gpu_memory_mb": b.gpu_memory_mb,
            "processed_at": b.processed_at.isoformat() if b.processed_at else None,
        }
        for b in benchmarks
    ]


# ==================== Benchmarks ====================

@router.post("/benchmarks/run", response_model=BenchmarkRunResponse)
async def run_benchmark(
    request: BenchmarkRunRequest,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Startet einen Benchmark-Lauf für ausgewählte Samples.

    Führt OCR auf allen angegebenen Samples mit den gewählten Backends aus
    und berechnet Qualitätsmetriken gegen Ground Truth.

    Erfordert Admin-Rolle.
    """
    service = get_benchmark_runner_service()
    result = await service.run_benchmark(db=db, request=request)

    return result


@router.get("/benchmarks/compare", response_model=BackendComparisonResponse)
async def compare_backends(
    sample_ids: Optional[List[UUID]] = Query(None, description="Nur diese Samples"),
    languages: Optional[List[str]] = Query(None, description="Filter nach Sprachen"),
    document_types: Optional[List[str]] = Query(None, description="Filter nach Dokumenttypen"),
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Vergleicht alle OCR Backends anhand von Benchmark-Ergebnissen.

    Gibt aggregierte Metriken (CER, WER, Umlaut-Accuracy) pro Backend zurück.
    """
    service = get_benchmark_runner_service()
    result = await service.get_backend_comparison(
        db=db,
        sample_ids=sample_ids,
        languages=languages,
        document_types=document_types
    )

    return result


@router.get("/benchmarks/backends")
async def get_available_backends(
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Gibt Liste der verfügbaren OCR Backends zurück.
    """
    service = get_benchmark_runner_service()
    return {"backends": service.get_available_backends()}


# ==================== Corrections (Self-Learning) ====================

@router.post("/corrections", response_model=CorrectionResponse, status_code=201)
async def create_correction(
    correction_data: CorrectionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt eine OCR-Korrektur für Self-Learning.

    Alle Benutzer können Korrekturen einreichen.
    Diese werden automatisch für das Self-Learning verwendet.
    """
    service = get_ocr_training_service()
    correction = await service.create_correction(
        db=db,
        correction_data=correction_data,
        user_id=current_user.id
    )

    return CorrectionResponse.model_validate(correction)


@router.get("/corrections", response_model=CorrectionListResponse)
async def list_corrections(
    backend: Optional[str] = Query(None, description="Filter nach Backend"),
    correction_type: Optional[str] = Query(None, description="Filter nach Korrekturtyp"),
    unprocessed_only: bool = Query(False, description="Nur unverarbeitete"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet OCR-Korrekturen auf.

    Erfordert Admin-Rolle.
    """
    service = get_ocr_training_service()
    corrections, total = await service.list_corrections(
        db=db,
        backend=backend,
        correction_type=correction_type,
        unprocessed_only=unprocessed_only,
        limit=limit,
        offset=offset
    )

    return CorrectionListResponse(
        corrections=[CorrectionResponse.model_validate(c) for c in corrections],
        total=total,
        limit=limit,
        offset=offset
    )


# ==================== Training Batches ====================

@router.get("/batches", response_model=BatchListResponse)
async def list_training_batches(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet Training Batches auf.
    """
    service = get_ocr_training_service()
    batches, total = await service.list_training_batches(
        db=db,
        status=status,
        limit=limit,
        offset=offset
    )

    return BatchListResponse(
        batches=[BatchResponse.model_validate(b) for b in batches],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/batches", response_model=BatchResponse, status_code=201)
async def create_training_batch(
    batch_data: BatchCreate,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt einen neuen Training-Batch mit stratifizierter Stichprobe.

    Erfordert Admin-Rolle.
    """
    service = get_ocr_training_service()
    batch = await service.create_training_batch(
        db=db,
        batch_data=batch_data,
        user_id=current_user.id
    )

    return BatchResponse.model_validate(batch)


@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
async def get_training_batch(
    batch_id: UUID,
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt einen Batch mit allen Items.
    """
    service = get_ocr_training_service()
    batch = await service.get_training_batch(db=db, batch_id=batch_id)

    if not batch:
        raise HTTPException(status_code=404, detail="Training Batch nicht gefunden")

    return BatchDetailResponse.model_validate(batch)


@router.post("/batches/{batch_id}/start", response_model=BatchResponse)
async def start_training_batch(
    batch_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Startet einen Batch zur Validierung.

    Erfordert Admin-Rolle.
    """
    service = get_ocr_training_service()
    try:
        batch = await service.start_batch(db=db, batch_id=batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Training Batch nicht gefunden")
        return BatchResponse.model_validate(batch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batches/{batch_id}/complete", response_model=BatchResponse)
async def complete_training_batch(
    batch_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Markiert einen Batch als abgeschlossen.

    Erfordert Admin-Rolle.
    """
    service = get_ocr_training_service()
    batch = await service.complete_batch(db=db, batch_id=batch_id)

    if not batch:
        raise HTTPException(status_code=404, detail="Training Batch nicht gefunden")

    return BatchResponse.model_validate(batch)


@router.get("/batches/{batch_id}/next-item", response_model=BatchItemResponse)
async def get_next_batch_item(
    batch_id: UUID,
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt das nächste zu validierende Item für den aktuellen User.
    """
    service = get_ocr_training_service()
    item = await service.get_next_batch_item(
        db=db,
        batch_id=batch_id,
        user_id=current_user.id
    )

    if not item:
        raise HTTPException(status_code=404, detail="Keine weiteren Items verfügbar")

    return BatchItemResponse.model_validate(item)


@router.put("/batches/{batch_id}/items/{item_id}", response_model=BatchItemResponse)
async def update_batch_item(
    batch_id: UUID,
    item_id: UUID,
    update_data: BatchItemUpdate,
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert ein Batch Item (Validierungs-Workflow).
    """
    service = get_ocr_training_service()
    item = await service.update_batch_item(
        db=db,
        item_id=item_id,
        update_data=update_data,
        user_id=current_user.id
    )

    if not item:
        raise HTTPException(status_code=404, detail="Batch Item nicht gefunden")

    return BatchItemResponse.model_validate(item)


# ==================== Statistics ====================

@router.get("/stats/overview", response_model=TrainingOverviewStats)
async def get_training_overview(
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Übersichts-Statistiken für das Training Dashboard.
    """
    service = get_ocr_training_service()
    stats = await service.get_training_overview_stats(db=db)

    return stats


@router.get("/stats/backends", response_model=List[BackendStats])
async def get_backend_stats(
    days: int = Query(30, ge=1, le=365, description="Anzahl Tage für Analyse"),
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Performance-Statistiken für alle OCR Backends.
    """
    service = get_ocr_training_service()
    stats = await service.get_backend_stats(db=db, days=days)

    return stats


@router.get("/stats/trends", response_model=TrendResponse)
async def get_trend_data(
    backend: Optional[str] = Query(None, description="Filter nach Backend"),
    days: int = Query(30, ge=1, le=365, description="Anzahl Tage"),
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Trend-Daten für Dashboard-Visualisierung.
    """
    service = get_feedback_learning_service()
    data = await service.get_trend_data(db=db, backend=backend, days=days)

    return TrendResponse(data=data)


@router.get("/stats/learned-weights")
async def get_learned_weights(
    force_refresh: bool = Query(False, description="Cache umgehen"),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt die gelernten Backend-Gewichtungen.

    Erfordert Admin-Rolle.
    """
    service = get_feedback_learning_service()
    weights = await service.get_learned_weights(db=db, force_refresh=force_refresh)

    return weights.to_dict()


@router.get("/stats/backend-recommendation")
async def get_backend_recommendation(
    document_type: Optional[str] = Query(None),
    has_umlauts: bool = Query(False),
    has_tables: bool = Query(False),
    fields_needed: Optional[List[str]] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Empfiehlt bestes Backend basierend auf gelernten Patterns.
    """
    service = get_feedback_learning_service()
    backend, confidence = await service.get_backend_recommendation(
        db=db,
        document_type=document_type,
        has_umlauts=has_umlauts,
        has_tables=has_tables,
        fields_needed=fields_needed
    )

    return {
        "recommended_backend": backend,
        "confidence": round(confidence, 4)
    }


# ==================== Migration ====================

@router.get("/migration/status")
async def get_migration_status(
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Prüft verfügbare Migrationsquellen.

    Erfordert Admin-Rolle.
    """
    from app.services.training_migration_service import get_training_migration_service

    service = await get_training_migration_service(db)
    sources = await service.check_migration_sources()

    return {
        "sources": sources,
        "stats": service.get_migration_stats()
    }


@router.post("/migration/sqlite")
async def migrate_from_sqlite(
    dry_run: bool = Query(True, description="Nur prüfen, nicht migrieren"),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Migriert Daten aus SQLite Datenbank nach PostgreSQL.

    Erfordert Admin-Rolle.

    Args:
        dry_run: Bei True wird nur geprüft, nicht migriert
    """
    from app.services.training_migration_service import get_training_migration_service

    service = await get_training_migration_service(db)
    result = await service.migrate_from_sqlite(dry_run=dry_run)

    return result


@router.post("/migration/import-files")
async def import_training_files(
    language: str = Query("de", description="Standard-Sprache für importierte Dateien"),
    dry_run: bool = Query(True, description="Nur prüfen, nicht importieren"),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Trainingsdateien aus dem Trainings_Data Verzeichnis.

    Erfordert Admin-Rolle.

    Args:
        language: Standard-Sprache für neue Samples (de, en, nl, pl)
        dry_run: Bei True wird nur geprüft, nicht importiert
    """
    from app.services.training_migration_service import get_training_migration_service

    service = await get_training_migration_service(db)
    result = await service.import_training_files(language=language, dry_run=dry_run)

    return result


@router.get("/migration/discover-files")
async def discover_training_files(
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet verfügbare Trainingsdateien im Trainings_Data Verzeichnis.

    Erfordert Admin-Rolle.
    """
    from app.services.training_migration_service import get_training_migration_service

    service = await get_training_migration_service(db)
    files = await service.discover_training_files()

    return {
        "files": files,
        "total": len(files)
    }


# ============================================================================
# BULK OCR PROCESSING ENDPOINTS
# Massenverarbeitung aller Trainings-Dokumente durch alle Backends
# ============================================================================

@router.get("/bulk-processing/jobs", response_model=schemas.BulkProcessingJobListResponse)
async def list_bulk_processing_jobs(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet alle Bulk Processing Jobs.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    jobs, total = await service.list_jobs(status=status, limit=limit, offset=offset)

    return schemas.BulkProcessingJobListResponse(
        total=total,
        jobs=[schemas.BulkProcessingJobResponse.model_validate(job) for job in jobs]
    )


@router.post("/bulk-processing/jobs", response_model=schemas.BulkProcessingStartResponse)
async def create_bulk_processing_job(
    request: schemas.BulkProcessingJobCreate,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt und startet einen neuen Bulk Processing Job.

    Verarbeitet alle Trainings-Samples durch die angegebenen Backends.
    Der Job läuft im Hintergrund und kann pausiert/fortgesetzt werden.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)

    # Job erstellen
    job = await service.create_job(
        name=request.name,
        description=request.description,
        backends=request.backends,
        configuration=request.configuration,
        created_by_id=current_user.id
    )

    # Job starten (Celery Task)
    from app.workers.tasks.training_tasks import run_bulk_processing_job
    run_bulk_processing_job.delay(str(job.id))

    # Geschätzte Zeit berechnen (ca. 3s pro Dokument pro Backend)
    estimated_seconds = job.total_documents * len(request.backends) * 3
    estimated_hours = estimated_seconds / 3600

    return schemas.BulkProcessingStartResponse(
        success=True,
        job_id=job.id,
        message=f"Bulk Processing Job '{request.name}' gestartet",
        total_documents=job.total_documents,
        backends=request.backends,
        estimated_time_hours=round(estimated_hours, 1)
    )


@router.get("/bulk-processing/jobs/{job_id}", response_model=schemas.BulkProcessingJobResponse)
async def get_bulk_processing_job(
    job_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft Details eines Bulk Processing Jobs ab.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    job = await service.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bulk Processing Job {job_id} nicht gefunden"
        )

    return schemas.BulkProcessingJobResponse.model_validate(job)


@router.get("/bulk-processing/jobs/{job_id}/progress", response_model=schemas.BulkProcessingProgress)
async def get_bulk_processing_progress(
    job_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft den aktuellen Fortschritt eines Bulk Processing Jobs ab.

    Enthält Echtzeit-Statistiken wie Verarbeitungsrate und geschätzte Restzeit.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    progress = await service.get_progress(job_id)

    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bulk Processing Job {job_id} nicht gefunden"
        )

    return progress


@router.post("/bulk-processing/jobs/{job_id}/pause", response_model=schemas.BulkProcessingPauseResponse)
async def pause_bulk_processing_job(
    job_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Pausiert einen laufenden Bulk Processing Job.

    Der Job kann später mit /resume fortgesetzt werden.
    Der aktuelle Checkpoint wird gespeichert.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)

    try:
        job = await service.pause_job(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    remaining = job.total_documents - job.processed_documents

    return schemas.BulkProcessingPauseResponse(
        success=True,
        job_id=job_id,
        message=f"Job pausiert. {job.processed_documents} Dokumente verarbeitet.",
        processed_documents=job.processed_documents,
        remaining_documents=remaining,
        can_resume=True
    )


@router.post("/bulk-processing/jobs/{job_id}/resume", response_model=schemas.BulkProcessingResumeResponse)
async def resume_bulk_processing_job(
    job_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Setzt einen pausierten Bulk Processing Job fort.

    Die Verarbeitung wird vom letzten Checkpoint fortgesetzt.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    job = await service.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bulk Processing Job {job_id} nicht gefunden"
        )

    if job.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job kann nicht fortgesetzt werden. Status: {job.status}"
        )

    # Job fortsetzen (Celery Task)
    from app.workers.tasks.training_tasks import run_bulk_processing_job
    run_bulk_processing_job.delay(str(job_id), resume=True)

    # Status aktualisieren
    await service.update_job_status(job_id, "running")

    return schemas.BulkProcessingResumeResponse(
        success=True,
        job_id=job_id,
        message=f"Job wird fortgesetzt ab Backend '{job.current_backend}'",
        resume_from_backend=job.current_backend or job.backends[0],
        resume_from_document=job.current_document_index
    )


@router.post("/bulk-processing/jobs/{job_id}/cancel", response_model=schemas.BulkProcessingCancelResponse)
async def cancel_bulk_processing_job(
    job_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Bricht einen Bulk Processing Job ab.

    Bereits verarbeitete Dokumente bleiben erhalten.
    Der Job kann nicht fortgesetzt werden.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)

    try:
        job = await service.cancel_job(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return schemas.BulkProcessingCancelResponse(
        success=True,
        job_id=job_id,
        message=f"Job abgebrochen. {job.processed_documents} Dokumente wurden verarbeitet.",
        documents_processed_before_cancel=job.processed_documents
    )


# --- OCR Document Outputs ---

@router.get("/bulk-processing/samples/{sample_id}/outputs", response_model=schemas.OCRDocumentOutputListResponse)
async def get_sample_ocr_outputs(
    sample_id: UUID,
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft alle OCR-Outputs für ein Training-Sample ab.

    Zeigt die Ergebnisse aller Backends für ein bestimmtes Dokument.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    outputs = await service.get_sample_outputs(sample_id)

    successful = sum(1 for o in outputs if o.success)

    return schemas.OCRDocumentOutputListResponse(
        sample_id=sample_id,
        outputs=[schemas.OCRDocumentOutputResponse.model_validate(o) for o in outputs],
        total_backends=len(outputs),
        successful_backends=successful
    )


@router.get("/bulk-processing/outputs/{output_id}", response_model=schemas.OCRDocumentOutputResponse)
async def get_ocr_output(
    output_id: UUID,
    current_user: User = Depends(require_any_role("admin", "editor")),
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft einen einzelnen OCR-Output ab.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    output = await service.get_output(output_id)

    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OCR Output {output_id} nicht gefunden"
        )

    return schemas.OCRDocumentOutputResponse.model_validate(output)


# --- Quality Snapshots ---

@router.get("/bulk-processing/quality-snapshots/{backend_name}", response_model=schemas.QualitySnapshotListResponse)
async def get_quality_snapshots(
    backend_name: str,
    hours: int = Query(24, ge=1, le=168, description="Zeitraum in Stunden"),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft Quality Snapshots für ein Backend ab.

    Zeigt die Qualitätsentwicklung über Zeit.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    snapshots = await service.get_quality_snapshots(backend_name, hours=hours)

    return schemas.QualitySnapshotListResponse(
        backend_name=backend_name,
        snapshots=[schemas.OCRQualitySnapshotResponse.model_validate(s) for s in snapshots],
        total=len(snapshots)
    )


@router.post("/bulk-processing/quality-snapshots/create")
async def create_quality_snapshot(
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt manuell einen Quality Snapshot für alle Backends.

    Normalerweise werden Snapshots stündlich automatisch erstellt.

    Erfordert Admin-Rolle.
    """
    from app.workers.tasks.training_tasks import create_quality_snapshot as create_snapshot_task

    create_snapshot_task.delay()

    return {
        "success": True,
        "message": "Quality Snapshot Task gestartet"
    }


# --- Model Deployments ---

@router.get("/bulk-processing/deployments/{model_name}", response_model=schemas.ModelDeploymentListResponse)
async def get_model_deployments(
    model_name: str,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft alle Deployments für ein Model ab.

    Zeigt Versionshistorie und aktives Deployment.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)
    deployments = await service.get_model_deployments(model_name)

    active_version = None
    for d in deployments:
        if d.is_active:
            active_version = d.version
            break

    return schemas.ModelDeploymentListResponse(
        model_name=model_name,
        deployments=[schemas.ModelDeploymentResponse.model_validate(d) for d in deployments],
        active_version=active_version,
        total=len(deployments)
    )


@router.post("/bulk-processing/deployments", response_model=schemas.ModelDeploymentResponse)
async def create_model_deployment(
    request: schemas.ModelDeploymentCreate,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt ein neues Model Deployment.

    Wird für A/B Testing und Rollback-Tracking verwendet.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)

    deployment = await service.create_model_deployment(
        model_name=request.model_name,
        version=request.version,
        model_type=request.model_type,
        checkpoint_path=request.checkpoint_path,
        training_job_id=request.training_job_id,
        traffic_percentage=request.traffic_percentage,
        deployed_by_id=current_user.id
    )

    return schemas.ModelDeploymentResponse.model_validate(deployment)


@router.post("/bulk-processing/deployments/{deployment_id}/activate")
async def activate_model_deployment(
    deployment_id: UUID,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktiviert ein Model Deployment.

    Deaktiviert vorherige aktive Versionen des gleichen Models.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)

    try:
        deployment = await service.activate_deployment(deployment_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return {
        "success": True,
        "message": f"Deployment {deployment.version} für {deployment.model_name} aktiviert",
        "deployment_id": str(deployment_id)
    }


@router.post("/bulk-processing/deployments/{deployment_id}/rollback")
async def rollback_model_deployment(
    deployment_id: UUID,
    reason: str = Query(..., min_length=1, max_length=500, description="Grund für Rollback"),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Führt Rollback zu einer früheren Version durch.

    Deaktiviert aktuelles Deployment und aktiviert die angegebene Version.

    Erfordert Admin-Rolle.
    """
    from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service

    service = await get_bulk_ocr_processing_service(db)

    try:
        deployment = await service.rollback_deployment(deployment_id, reason)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return {
        "success": True,
        "message": f"Rollback zu {deployment.version} durchgeführt",
        "deployment_id": str(deployment_id),
        "reason": reason
    }


# ============================================================================
# BACKEND QUALITY REPORTS
# Qualitaetsanalyse und Schwachstellen-Erkennung pro Backend
# ============================================================================

@router.get("/quality-reports/{backend_name}")
async def get_backend_quality_report(
    backend_name: str,
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Generiert einen Qualitaetsbericht fuer ein Backend.

    Enthaelt:
    - Performance-Metriken (CER, WER, Umlaut-Accuracy)
    - Erkannte Schwaechen
    - Fehlermuster
    - Retraining-Empfehlungen

    Erfordert Admin-Rolle.
    """
    from app.services.backend_quality_report_service import get_backend_quality_report_service

    service = await get_backend_quality_report_service(db)
    report = await service.generate_backend_report(backend_name, days=days)

    return {
        "backend_name": report.backend_name,
        "report_date": report.report_date.isoformat(),
        "overall_quality_score": report.overall_quality_score,
        "trend_direction": report.trend_direction,
        "performance": {
            "avg_cer": report.performance.avg_cer,
            "avg_wer": report.performance.avg_wer,
            "avg_umlaut_accuracy": report.performance.avg_umlaut_accuracy,
            "avg_processing_time_ms": report.performance.avg_processing_time_ms,
            "p50_cer": report.performance.p50_cer,
            "p90_cer": report.performance.p90_cer,
            "p95_cer": report.performance.p95_cer,
            "p99_cer": report.performance.p99_cer,
            "total_samples": report.performance.total_samples,
            "verified_samples": report.performance.verified_samples,
            "failed_samples": report.performance.failed_samples,
        },
        "weaknesses": [
            {
                "category": w.category.value,
                "description": w.description,
                "severity": w.severity,
                "affected_sample_count": w.affected_sample_count,
                "affected_sample_percentage": w.affected_sample_percentage,
                "recommended_action": w.recommended_action,
            }
            for w in report.weaknesses
        ],
        "error_patterns": [
            {
                "pattern_type": p.pattern_type,
                "description": p.description,
                "occurrence_count": p.occurrence_count,
                "severity": p.severity,
                "examples": p.example_errors[:3],
            }
            for p in report.error_patterns
        ],
        "document_type_performance": [
            {
                "document_type": d.document_type,
                "sample_count": d.sample_count,
                "avg_cer": d.avg_cer,
                "avg_wer": d.avg_wer,
                "avg_umlaut_accuracy": d.avg_umlaut_accuracy,
                "is_weakness": d.is_weakness,
            }
            for d in report.document_type_performance
        ],
        "retraining_recommendations": [
            {
                "priority": r.priority.value,
                "focus_area": r.focus_area,
                "description": r.description,
                "estimated_improvement": r.estimated_improvement,
                "required_samples": r.required_samples,
            }
            for r in report.retraining_recommendations
        ],
        "comparison_to_best": report.comparison_to_best,
    }


@router.get("/quality-reports/comparison/all")
async def get_backend_comparison_report(
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Generiert einen Vergleichsbericht aller Backends.

    Zeigt:
    - Bestes Backend insgesamt
    - Bestes Backend fuer Umlaute
    - Bestes Backend fuer Geschwindigkeit
    - Empfehlungen

    Erfordert Admin-Rolle.
    """
    from app.services.backend_quality_report_service import get_backend_quality_report_service

    service = await get_backend_quality_report_service(db)
    report = await service.generate_comparison_report()

    return {
        "report_date": report.report_date.isoformat(),
        "backends": report.backends,
        "best_overall": report.best_overall,
        "best_for_umlauts": report.best_for_umlauts,
        "best_for_tables": report.best_for_tables,
        "best_for_speed": report.best_for_speed,
        "per_backend_scores": report.per_backend_scores,
        "recommendations": report.recommendations,
    }


@router.get("/quality-reports/{backend_name}/weaknesses")
async def get_backend_weaknesses(
    backend_name: str,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt nur die Schwaechen eines Backends zurueck.

    Erfordert Admin-Rolle.
    """
    from app.services.backend_quality_report_service import get_backend_quality_report_service

    service = await get_backend_quality_report_service(db)
    report = await service.generate_backend_report(backend_name, days=30)

    return {
        "backend_name": backend_name,
        "weaknesses": [
            {
                "category": w.category.value,
                "description": w.description,
                "severity": w.severity,
                "affected_sample_count": w.affected_sample_count,
                "recommended_action": w.recommended_action,
            }
            for w in report.weaknesses
        ],
        "total_weaknesses": len(report.weaknesses),
        "critical_count": sum(1 for w in report.weaknesses if w.severity > 0.5),
    }


@router.get("/quality-reports/{backend_name}/retraining-recommendations")
async def get_retraining_recommendations(
    backend_name: str,
    current_user: User = Depends(require_any_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Retraining-Empfehlungen fuer ein Backend zurueck.

    Erfordert Admin-Rolle.
    """
    from app.services.backend_quality_report_service import get_backend_quality_report_service

    service = await get_backend_quality_report_service(db)
    report = await service.generate_backend_report(backend_name, days=30)

    return {
        "backend_name": backend_name,
        "overall_quality_score": report.overall_quality_score,
        "recommendations": [
            {
                "priority": r.priority.value,
                "focus_area": r.focus_area,
                "description": r.description,
                "estimated_improvement": r.estimated_improvement,
                "required_samples": r.required_samples,
            }
            for r in report.retraining_recommendations
        ],
        "critical_recommendations": sum(
            1 for r in report.retraining_recommendations
            if r.priority.value == "critical"
        ),
    }


# ============================================================================
# UMLAUT VALIDATION ENDPOINTS
# Umlaut-spezifische Validierung und Korrektur
# ============================================================================

@router.post("/umlaut-validation/validate")
async def validate_umlauts(
    text: str = Query(..., description="Zu validierender Text"),
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Validiert Umlaute in einem Text.

    Erkennt potentielle Umlaut-Fehler und gibt Korrekturvorschlaege.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.umlaut_validation_service import get_umlaut_validation_service

    service = get_umlaut_validation_service()
    suggestions = service.detect_potential_umlaut_errors(text)

    return {
        "original_text": text,
        "has_issues": len(suggestions) > 0,
        "issue_count": len(suggestions),
        "suggestions": [
            {
                "original": s.original,
                "suggested": s.suggested,
                "position": s.position,
                "context": s.context,
                "confidence": s.confidence,
            }
            for s in suggestions
        ],
    }


@router.post("/umlaut-validation/auto-correct")
async def auto_correct_umlauts(
    text: str = Query(..., description="Zu korrigierender Text"),
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Korrigiert automatisch Umlaute in einem Text.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.umlaut_validation_service import get_umlaut_validation_service

    service = get_umlaut_validation_service()
    corrected = service.auto_correct_umlauts(text)

    return {
        "original_text": text,
        "corrected_text": corrected,
        "was_modified": text != corrected,
    }


@router.post("/umlaut-validation/compare")
async def compare_umlaut_consistency(
    ground_truth: str = Query(..., description="Ground Truth Text"),
    ocr_output: str = Query(..., description="OCR Output Text"),
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Vergleicht Umlaut-Konsistenz zwischen Ground Truth und OCR-Output.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.umlaut_validation_service import get_umlaut_validation_service

    service = get_umlaut_validation_service()
    result = service.validate_umlaut_consistency(ground_truth, ocr_output)

    return {
        "umlaut_accuracy": result.umlaut_accuracy,
        "total_umlauts_expected": result.total_umlauts_expected,
        "total_umlauts_found": result.total_umlauts_found,
        "missing_umlauts": result.missing_umlauts,
        "extra_umlauts": result.extra_umlauts,
        "suggestion_count": len(result.suggestions),
        "corrected_text": result.corrected_text,
    }


# =============================================================================
# Training Dataset Export Endpoints
# =============================================================================

@router.get(
    "/exports",
    response_model=schemas.ExportListResponse,
    summary="Liste alle Exports",
    tags=["training-export"]
)
async def list_exports(
    limit: int = Query(default=50, ge=1, le=200, description="Maximale Anzahl"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Listet alle vorhandenen Dataset-Exports auf.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.training_dataset_export_service import get_training_dataset_export_service

    service = await get_training_dataset_export_service(db)
    exports = await service.list_exports(limit=limit)

    return schemas.ExportListResponse(
        exports=[
            schemas.ExportListItemResponse(
                export_id=e["export_id"],
                created_at=e.get("created_at"),
                format=e.get("format"),
                total_samples=e.get("total_samples", 0),
                output_dir=e["output_dir"]
            )
            for e in exports
        ],
        total=len(exports)
    )


@router.post(
    "/exports",
    response_model=schemas.ExportResultResponse,
    summary="Erstelle Dataset-Export",
    tags=["training-export"]
)
async def create_export(
    config: schemas.ExportConfigRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Erstellt einen neuen Dataset-Export für Fine-Tuning.

    Unterstützte Formate:
    - deepseek_jsonl: JSONL für DeepSeek-Janus-Pro LoRA
    - surya_hf: HuggingFace Format für Surya-OCR
    - generic_jsonl: Allgemeines JSONL
    - csv: CSV-Format

    Erfordert Admin-Rolle.
    """
    from app.services.training_dataset_export_service import (
        get_training_dataset_export_service,
        ExportConfig,
        ExportFormat,
        SplitStrategy
    )

    service = await get_training_dataset_export_service(db)

    # Konfiguration erstellen
    export_config = ExportConfig(
        format=ExportFormat(config.format.value),
        split_ratio=config.split_ratio,
        split_strategy=SplitStrategy(config.split_strategy.value),
        filter_verified_only=config.filter_verified_only,
        min_umlaut_accuracy=config.min_umlaut_accuracy,
        min_cer=config.min_cer,
        include_metadata=config.include_metadata,
        include_image_base64=config.include_image_base64,
        image_reference_type=config.image_reference_type,
        seed=config.seed
    )

    result = await service.export_for_finetuning(export_config)

    return schemas.ExportResultResponse(
        success=result.success,
        export_id=result.export_id,
        output_dir=result.output_dir,
        format=schemas.ExportFormat(result.format.value),
        stats=schemas.ExportStatsResponse(
            total_samples=result.stats.total_samples,
            train_samples=result.stats.train_samples,
            val_samples=result.stats.val_samples,
            test_samples=result.stats.test_samples,
            samples_with_umlauts=result.stats.samples_with_umlauts,
            avg_text_length=result.stats.avg_text_length,
            document_types=result.stats.document_types,
            export_time_seconds=result.stats.export_time_seconds,
            output_size_bytes=result.stats.output_size_bytes
        ),
        files_created=result.files_created,
        errors=result.errors,
        warnings=result.warnings
    )


@router.post(
    "/exports/deepseek",
    response_model=schemas.ExportResultResponse,
    summary="Export für DeepSeek Fine-Tuning",
    tags=["training-export"]
)
async def export_for_deepseek(
    config: schemas.DeepSeekExportRequest,
    output_dir: str = Query(default="./exports/deepseek", description="Ausgabeverzeichnis"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Spezialisierter Export für DeepSeek-Janus-Pro LoRA Fine-Tuning.

    Erstellt JSONL-Dateien im Format:
    ```json
    {
      "image": "path/to/image.png",
      "conversations": [
        {"from": "human", "value": "<image>\\nExtrahiere..."},
        {"from": "gpt", "value": "Ground truth text..."}
      ],
      "metadata": {...}
    }
    ```

    Erfordert Admin-Rolle.
    """
    from app.services.training_dataset_export_service import get_training_dataset_export_service

    service = await get_training_dataset_export_service(db)

    result = await service.export_for_deepseek(
        output_dir=output_dir,
        prompt_type=config.prompt_type,
        include_structured=config.include_structured
    )

    return schemas.ExportResultResponse(
        success=result.success,
        export_id=result.export_id,
        output_dir=result.output_dir,
        format=schemas.ExportFormat(result.format.value),
        stats=schemas.ExportStatsResponse(
            total_samples=result.stats.total_samples,
            train_samples=result.stats.train_samples,
            val_samples=result.stats.val_samples,
            test_samples=result.stats.test_samples,
            samples_with_umlauts=result.stats.samples_with_umlauts,
            avg_text_length=result.stats.avg_text_length,
            document_types=result.stats.document_types,
            export_time_seconds=result.stats.export_time_seconds,
            output_size_bytes=result.stats.output_size_bytes
        ),
        files_created=result.files_created,
        errors=result.errors,
        warnings=result.warnings
    )


@router.post(
    "/exports/surya",
    response_model=schemas.ExportResultResponse,
    summary="Export für Surya Fine-Tuning",
    tags=["training-export"]
)
async def export_for_surya(
    config: schemas.SuryaExportRequest,
    output_dir: str = Query(default="./exports/surya", description="Ausgabeverzeichnis"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Spezialisierter Export für Surya-OCR HuggingFace Training.

    Erstellt:
    - JSONL-Dateien (train.jsonl, val.jsonl, test.jsonl)
    - Optional: HuggingFace Arrow-Dateien

    Format:
    ```json
    {
      "image": "path/to/image.png",
      "text": "Ground truth text...",
      "language": "de"
    }
    ```

    Erfordert Admin-Rolle.
    """
    from app.services.training_dataset_export_service import get_training_dataset_export_service

    service = await get_training_dataset_export_service(db)

    result = await service.export_for_surya(
        output_dir=output_dir,
        create_arrow_files=config.create_arrow_files
    )

    return schemas.ExportResultResponse(
        success=result.success,
        export_id=result.export_id,
        output_dir=result.output_dir,
        format=schemas.ExportFormat(result.format.value),
        stats=schemas.ExportStatsResponse(
            total_samples=result.stats.total_samples,
            train_samples=result.stats.train_samples,
            val_samples=result.stats.val_samples,
            test_samples=result.stats.test_samples,
            samples_with_umlauts=result.stats.samples_with_umlauts,
            avg_text_length=result.stats.avg_text_length,
            document_types=result.stats.document_types,
            export_time_seconds=result.stats.export_time_seconds,
            output_size_bytes=result.stats.output_size_bytes
        ),
        files_created=result.files_created,
        errors=result.errors,
        warnings=result.warnings
    )


@router.get(
    "/exports/{export_id}",
    summary="Export-Details abrufen",
    tags=["training-export"]
)
async def get_export_details(
    export_id: str = Path(..., description="Export-ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Ruft Details eines Exports ab (aus metadata.json).

    Erfordert Admin- oder Editor-Rolle.
    """
    from pathlib import Path as FilePath
    import json

    export_dir = FilePath("./exports") / export_id
    metadata_file = export_dir / "metadata.json"

    if not metadata_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export '{export_id}' nicht gefunden"
        )

    with open(metadata_file, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return metadata


@router.delete(
    "/exports/{export_id}",
    summary="Export löschen",
    tags=["training-export"]
)
async def delete_export(
    export_id: str = Path(..., description="Export-ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Löscht einen Export und alle zugehörigen Dateien.

    Erfordert Admin-Rolle.
    """
    from app.services.training_dataset_export_service import get_training_dataset_export_service

    service = await get_training_dataset_export_service(db)
    success = await service.delete_export(export_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export '{export_id}' nicht gefunden oder konnte nicht gelöscht werden"
        )

    return {"message": f"Export '{export_id}' erfolgreich gelöscht"}


# =============================================================================
# Quality Monitoring Endpoints
# =============================================================================

@router.get(
    "/quality/check",
    summary="Führe Qualitätscheck durch",
    tags=["quality-monitoring"]
)
async def run_quality_check(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Führt einen vollständigen Qualitätscheck durch und gibt Alerts zurück.

    Prüft:
    - CER pro Backend
    - Umlaut-Genauigkeit
    - Korrekturrate
    - Degradationserkennung

    Erfordert Admin-Rolle.
    """
    from app.services.quality_monitoring_service import get_quality_monitoring_service

    service = await get_quality_monitoring_service(db)
    alerts = await service.run_quality_check()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "alerts_count": len(alerts),
        "alerts": [
            {
                "type": a.alert_type.value,
                "severity": a.severity.value,
                "message": a.message,
                "metric_name": a.metric_name,
                "current_value": a.current_value,
                "threshold_value": a.threshold_value,
                "affected_backend": a.affected_backend,
                "recommended_action": a.recommended_action,
                "created_at": a.created_at
            }
            for a in alerts
        ]
    }


@router.get(
    "/quality/health/{model_name}",
    summary="Model-Gesundheitsstatus",
    tags=["quality-monitoring"]
)
async def get_model_health(
    model_name: str = Path(..., description="Modell-Name (deepseek, surya)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Holt den Gesundheitsstatus eines Modells.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.quality_monitoring_service import get_quality_monitoring_service

    service = await get_quality_monitoring_service(db)
    health = await service.get_model_health(model_name)

    return {
        "model_name": health.model_name,
        "version": health.version,
        "is_healthy": health.is_healthy,
        "health_score": health.health_score,
        "issues": health.issues,
        "metrics": health.metrics,
        "last_checked": health.last_checked
    }


@router.get(
    "/quality/retraining-recommendation",
    summary="Retraining-Empfehlung",
    tags=["quality-monitoring"]
)
async def get_retraining_recommendation(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Generiert eine Retraining-Empfehlung basierend auf aktuellen Metriken.

    Erfordert Admin-Rolle.
    """
    from app.services.quality_monitoring_service import get_quality_monitoring_service

    service = await get_quality_monitoring_service(db)
    recommendation = await service.get_retraining_recommendation()

    return {
        "should_retrain": recommendation.should_retrain,
        "urgency": recommendation.urgency,
        "reasons": recommendation.reasons,
        "estimated_samples_needed": recommendation.estimated_samples_needed,
        "focus_areas": recommendation.focus_areas,
        "last_training_date": recommendation.last_training_date
    }


@router.post(
    "/quality/snapshot/{backend_name}",
    summary="Erstelle Quality-Snapshot",
    tags=["quality-monitoring"]
)
async def create_quality_snapshot(
    backend_name: str = Path(..., description="Backend-Name"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Erstellt einen neuen Quality-Snapshot für ein Backend.

    Erfordert Admin-Rolle.
    """
    from app.services.quality_monitoring_service import get_quality_monitoring_service

    service = await get_quality_monitoring_service(db)
    snapshot = await service.create_quality_snapshot(backend_name)

    return {
        "timestamp": snapshot.timestamp,
        "backend_name": snapshot.backend_name,
        "avg_cer": snapshot.avg_cer,
        "avg_wer": snapshot.avg_wer,
        "umlaut_accuracy": snapshot.umlaut_accuracy,
        "correction_count": snapshot.correction_count,
        "sample_count": snapshot.sample_count,
        "processing_time_avg_ms": snapshot.processing_time_avg_ms
    }


@router.post(
    "/quality/rollback/{model_name}",
    summary="Model-Rollback durchführen",
    tags=["quality-monitoring"]
)
async def execute_model_rollback(
    model_name: str = Path(..., description="Modell-Name"),
    target_version: Optional[str] = Query(default=None, description="Ziel-Version (None = vorherige)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin")),
):
    """
    Führt einen Model-Rollback zu einer früheren Version durch.

    ACHTUNG: Diese Aktion aktiviert eine ältere Modell-Version!

    Erfordert Admin-Rolle.
    """
    from app.services.quality_monitoring_service import get_quality_monitoring_service

    service = await get_quality_monitoring_service(db)
    result = await service.execute_model_rollback(model_name, target_version)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Rollback fehlgeschlagen")
        )

    return result


@router.get(
    "/quality/alerts",
    summary="Alert-Historie abrufen",
    tags=["quality-monitoring"]
)
async def get_alert_history(
    hours: int = Query(default=24, ge=1, le=168, description="Stunden zurück"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_any_role("admin", "editor")),
):
    """
    Gibt die Alert-Historie der letzten Stunden zurück.

    Erfordert Admin- oder Editor-Rolle.
    """
    from app.services.quality_monitoring_service import get_quality_monitoring_service

    service = await get_quality_monitoring_service(db)
    alerts = service.get_alert_history(hours=hours)

    return {
        "hours": hours,
        "alerts_count": len(alerts),
        "alerts": [
            {
                "type": a.alert_type.value,
                "severity": a.severity.value,
                "message": a.message,
                "metric_name": a.metric_name,
                "current_value": a.current_value,
                "threshold_value": a.threshold_value,
                "affected_backend": a.affected_backend,
                "recommended_action": a.recommended_action,
                "created_at": a.created_at
            }
            for a in alerts
        ]
    }
