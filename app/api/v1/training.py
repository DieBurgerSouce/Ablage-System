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
