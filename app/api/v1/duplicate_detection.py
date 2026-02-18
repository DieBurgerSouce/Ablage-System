# -*- coding: utf-8 -*-
"""
Duplikat-Erkennungs-API Endpoints fuer Ablage-System.

REST API fuer Duplikat-Erkennung:
- Einzelnes Dokument auf Duplikate pruefen
- Batch-Scan fuer alle Dokumente einer Firma ausloesen
- Duplikat-Statistiken abrufen
- Konfiguration aktualisieren

Feinpoliert und durchdacht - Deutsche Duplikat-Erkennung.
"""

from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.api.schemas.duplicate_detection import (
    BatchScanRequest,
    BatchScanResponse,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    DuplicateConfigResponse,
    DuplicateConfigUpdate,
    DuplicateMatch,
    DuplicateStatsResponse,
)
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import Document, User
from app.services.ai.duplicate_detection_service import get_duplicate_detection_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/duplicate-detection", tags=["Duplikat-Erkennung"])


def _candidate_to_match(candidate) -> DuplicateMatch:  # type: ignore[no-untyped-def]
    """Konvertiert einen DuplicateCandidate in ein DuplicateMatch Schema."""
    details: Optional[dict] = None
    if candidate.details:
        # Konvertiere alle Werte zu str fuer Schema-Konformitaet
        details = {k: str(v) for k, v in candidate.details.items()}

    return DuplicateMatch(
        document_id=candidate.document_id,
        duplicate_type=candidate.duplicate_type,
        similarity_score=candidate.similarity,
        matched_fields=candidate.matched_fields,
        details=details,
    )


@router.post(
    "/check",
    response_model=DuplicateCheckResponse,
    summary="Dokument auf Duplikate pruefen",
    description="Prueft ein einzelnes Dokument auf Duplikate (exakt, near, semantisch, Nummer, visuell).",
)
async def check_document_for_duplicates(
    request: DuplicateCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DuplicateCheckResponse:
    """Ein Dokument auf Duplikate pruefen."""
    try:
        service = get_duplicate_detection_service()
        # SECURITY: company_id aus Auth ableiten, nicht dem Client vertrauen
        result = await service.check_document(
            db=db,
            document_id=request.document_id,
            company_id=current_user.company_id,
            include_near=request.include_near,
        )

        candidates = [_candidate_to_match(c) for c in result.candidates]
        best_match = _candidate_to_match(result.best_match) if result.best_match else None

        logger.info(
            "duplicate_check_completed",
            document_id=str(request.document_id),
            has_duplicates=result.has_duplicates,
            candidate_count=len(candidates),
            processing_time_ms=result.processing_time_ms,
        )

        return DuplicateCheckResponse(
            has_duplicates=result.has_duplicates,
            candidates=candidates,
            best_match=best_match,
            processing_time_ms=result.processing_time_ms,
        )

    except Exception as e:
        logger.error(
            "duplicate_check_error",
            document_id=str(request.document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Duplikat-Pruefung"),
        )


@router.get(
    "/document/{document_id}",
    response_model=DuplicateCheckResponse,
    summary="Duplikat-Matches fuer ein Dokument abrufen",
    description="Gibt alle Duplikat-Kandidaten fuer ein spezifisches Dokument zurueck.",
)
async def get_document_duplicates(
    document_id: UUID,
    include_near: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DuplicateCheckResponse:
    """Duplikat-Matches fuer ein Dokument abrufen."""
    try:
        service = get_duplicate_detection_service()
        # SECURITY: company_id aus Auth ableiten (Multi-Tenant Enforcement)
        result = await service.check_document(
            db=db,
            document_id=document_id,
            company_id=current_user.company_id,
            include_near=include_near,
        )

        candidates = [_candidate_to_match(c) for c in result.candidates]
        best_match = _candidate_to_match(result.best_match) if result.best_match else None

        return DuplicateCheckResponse(
            has_duplicates=result.has_duplicates,
            candidates=candidates,
            best_match=best_match,
            processing_time_ms=result.processing_time_ms,
        )

    except Exception as e:
        logger.error(
            "duplicate_get_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Duplikat-Abfrage"),
        )


@router.post(
    "/batch-scan",
    response_model=BatchScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Asynchronen Batch-Duplikat-Scan starten",
    description="Loest einen asynchronen Batch-Scan fuer alle Dokumente einer Firma aus.",
)
async def trigger_batch_scan(
    request: BatchScanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BatchScanResponse:
    """Batch-Duplikat-Scan asynchron starten."""
    try:
        from app.workers.tasks.duplicate_detection_tasks import batch_scan_duplicates_task

        # SECURITY: company_id aus Auth ableiten, nicht dem Client vertrauen
        result = batch_scan_duplicates_task.delay(str(current_user.company_id))

        logger.info(
            "duplicate_batch_scan_triggered",
            company_id=str(current_user.company_id),
            task_id=result.id,
        )

        return BatchScanResponse(
            task_id=str(result.id),
            message="Batch-Scan gestartet",
        )

    except Exception as e:
        logger.error(
            "duplicate_batch_scan_error",
            company_id=str(current_user.company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Batch-Scan"),
        )


@router.get(
    "/stats",
    response_model=DuplicateStatsResponse,
    summary="Duplikat-Statistiken abrufen",
    description="Gibt Statistiken ueber gefundene Duplikate zurueck.",
)
async def get_duplicate_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DuplicateStatsResponse:
    """Duplikat-Statistiken abrufen."""
    try:
        # SECURITY: company_id aus Auth ableiten (Multi-Tenant Enforcement)
        company_id = current_user.company_id

        # Gesamtanzahl der Dokumente
        total_query = select(func.count(Document.id)).where(
            Document.deleted_at.is_(None),
            Document.company_id == company_id,
        )

        total_result = await db.execute(total_query)
        total_documents = total_result.scalar() or 0

        # Dokumente mit potential_duplicate Flag
        dup_query = select(Document).where(
            Document.deleted_at.is_(None),
            Document.metadata.isnot(None),
            Document.company_id == company_id,
        )

        dup_result = await db.execute(dup_query)
        all_docs = dup_result.scalars().all()

        # Filterung und Auswertung in Python (JSONB-Abfrage via Python fuer Portabilitaet)
        duplicates = [
            doc for doc in all_docs
            if (doc.metadata or {}).get("potential_duplicate") is True
        ]

        total_duplicates_found = len(duplicates)

        # Aufschluesselung nach Typ (aus duplicate_type in metadata)
        by_type: dict = {}
        similarities: list = []
        for doc in duplicates:
            meta = doc.metadata or {}
            dup_type = meta.get("duplicate_type", "unknown")
            by_type[dup_type] = by_type.get(dup_type, 0) + 1
            sim = meta.get("duplicate_similarity")
            if sim is not None:
                try:
                    similarities.append(float(sim))
                except (ValueError, TypeError):
                    pass

        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

        return DuplicateStatsResponse(
            total_documents=total_documents,
            total_duplicates_found=total_duplicates_found,
            by_type=by_type,
            avg_similarity=round(avg_similarity, 3),
        )

    except Exception as e:
        logger.error(
            "duplicate_stats_error",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Duplikat-Statistiken"),
        )


@router.put(
    "/config",
    response_model=DuplicateConfigResponse,
    summary="Duplikat-Erkennungs-Konfiguration aktualisieren",
    description="Aktualisiert die Aehnlichkeits-Schwellenwerte und Limits (nur Administratoren).",
)
async def update_duplicate_config(
    config_update: DuplicateConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DuplicateConfigResponse:
    """Konfiguration der Duplikat-Erkennung aktualisieren."""
    try:
        service = get_duplicate_detection_service()

        # Konfigurationsfelder des Singletons aktualisieren
        if config_update.min_similarity_near is not None:
            service.MIN_SIMILARITY_NEAR = config_update.min_similarity_near

        if config_update.min_similarity_semantic is not None:
            service.MIN_SIMILARITY_SEMANTIC = config_update.min_similarity_semantic

        if config_update.max_candidates is not None:
            service.MAX_CANDIDATES = config_update.max_candidates

        if config_update.max_text_length is not None:
            service.MAX_TEXT_LENGTH = config_update.max_text_length

        logger.info(
            "duplicate_config_updated",
            min_similarity_near=service.MIN_SIMILARITY_NEAR,
            min_similarity_semantic=service.MIN_SIMILARITY_SEMANTIC,
            max_candidates=service.MAX_CANDIDATES,
            max_text_length=service.MAX_TEXT_LENGTH,
        )

        return DuplicateConfigResponse(
            min_similarity_near=service.MIN_SIMILARITY_NEAR,
            min_similarity_semantic=service.MIN_SIMILARITY_SEMANTIC,
            max_candidates=service.MAX_CANDIDATES,
            max_text_length=service.MAX_TEXT_LENGTH,
        )

    except Exception as e:
        logger.error(
            "duplicate_config_update_error",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Konfigurationsupdate"),
        )
