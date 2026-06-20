"""
Invoice Pipeline API Endpoints.

API für vollautomatischen Rechnungsworkflow (Feature #3):
- Rechnungen automatisch verarbeiten (OCR -> Entity -> Approval -> Payment)
- Pipeline-Status abfragen
- Manuelle Genehmigung mit Pipeline-Fortsetzung
- Dashboard-Statistiken
"""

from typing import Optional, List
from app.api.dependencies import get_user_company_id_dep  # F-31
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.middleware.company_context import require_company
from app.services.invoice_pipeline_service import (
    InvoicePipelineService,
    PipelineResult,
    PipelineStats,
    PipelineStage,
    PipelineStatus,
    get_invoice_pipeline_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/invoice-pipeline", tags=["Rechnungs-Pipeline"])


# ==================== Pydantic Schemas ====================


class PipelineResultResponse(BaseModel):
    """Antwort-Schema für Pipeline-Ergebnis."""

    document_id: UUID
    stage: str
    status: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence-Score (0-1)")
    actions_taken: List[str] = Field(..., description="Ausgeführte Aktionen (deutsch)")
    next_action: Optional[str] = Field(None, description="Nächster Schritt")
    processing_time_ms: int = Field(0, description="Verarbeitungszeit in Millisekunden")
    error_message: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_result(cls, result: PipelineResult) -> "PipelineResultResponse":
        """Erstellt Response aus PipelineResult."""
        return cls(
            document_id=result.document_id,
            stage=result.stage.value,
            status=result.status.value,
            confidence=result.confidence,
            actions_taken=result.actions_taken,
            next_action=result.next_action,
            processing_time_ms=result.processing_time_ms,
            error_message=result.error_message,
            metadata=result.metadata,
        )


class PipelineStatsResponse(BaseModel):
    """Antwort-Schema für Pipeline-Statistiken."""

    total_processed: int = Field(..., description="Gesamt verarbeitete Dokumente")
    successful: int = Field(..., description="Erfolgreich verarbeitet")
    needs_review: int = Field(..., description="Benötigen manuelle Prüfung")
    failed: int = Field(..., description="Fehlgeschlagen")
    escalated: int = Field(..., description="Eskaliert")
    avg_processing_time_ms: float = Field(..., description="Durchschn. Verarbeitungszeit (ms)")
    auto_approval_rate: float = Field(..., ge=0.0, le=100.0, description="Auto-Approval-Rate (%)")
    entity_linking_rate: float = Field(..., ge=0.0, le=100.0, description="Entity-Linking-Rate (%)")
    avg_confidence: float = Field(..., ge=0.0, le=1.0, description="Durchschn. Confidence")

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_stats(cls, stats: PipelineStats) -> "PipelineStatsResponse":
        """Erstellt Response aus PipelineStats."""
        return cls(
            total_processed=stats.total_processed,
            successful=stats.successful,
            needs_review=stats.needs_review,
            failed=stats.failed,
            escalated=stats.escalated,
            avg_processing_time_ms=stats.avg_processing_time_ms,
            auto_approval_rate=stats.auto_approval_rate,
            entity_linking_rate=stats.entity_linking_rate,
            avg_confidence=stats.avg_confidence,
        )


class MessageResponse(BaseModel):
    """Einfache Nachricht-Antwort."""

    message: str
    details: Optional[dict] = None


# ==================== Endpoints ====================


@router.post(
    "/{document_id}/process",
    response_model=PipelineResultResponse,
    summary="Rechnung verarbeiten",
    description="Führt vollautomatische Pipeline für Rechnung aus: OCR -> Entity -> Approval -> Payment"
)
async def process_invoice(
    document_id: UUID,
    company_id: UUID = Depends(get_user_company_id_dep),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PipelineResultResponse:
    """
    Führt die vollständige automatische Verarbeitung durch:

    1. OCR-Qualitaet prüfen
    2. Entity automatisch verknüpfen
    3. Dokument kategorisieren
    4. Auto-Approval prüfen
    5. Bei Genehmigung: Als zahlungsbereit markieren
    6. Bei Ablehnung: Eskalation mit Details

    **Rückgabewerte:**
    - `SUCCESS`: Dokument wurde vollständig verarbeitet und ist zahlungsbereit
    - `NEEDS_REVIEW`: Manuelle Prüfung erforderlich (siehe `next_action`)
    - `ESCALATED`: Wurde an Admin eskaliert
    - `FAILED`: Verarbeitung fehlgeschlagen (siehe `error_message`)
    """
    try:
        service = get_invoice_pipeline_service(db=db, company_id=company_id)
        result = await service.process_invoice(
            document_id=document_id,
            user_id=current_user.id,
        )

        logger.info(
            "invoice_pipeline_executed",
            document_id=str(document_id),
            status=result.status.value,
            stage=result.stage.value,
            user_id=str(current_user.id),
            company_id=str(company_id),
        )

        return PipelineResultResponse.from_result(result)

    except Exception as e:
        logger.error(
            "invoice_pipeline_api_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Rechnungs-Pipeline"),
        )


@router.get(
    "/{document_id}/status",
    response_model=PipelineResultResponse,
    summary="Pipeline-Status abrufen",
    description="Ruft den aktuellen Status der Pipeline für ein Dokument ab"
)
async def get_pipeline_status(
    document_id: UUID,
    company_id: UUID = Depends(get_user_company_id_dep),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PipelineResultResponse:
    """
    Ruft den aktuellen Pipeline-Status ab.

    Zeigt, welche Schritte bereits durchlaufen wurden und was als nächstes passieren muss.

    **Pipeline-Stufen:**
    - `ocr_complete`: OCR wurde durchgeführt
    - `entity_linked`: Entity wurde verknüpft
    - `categorized`: Dokument wurde kategorisiert
    - `approved`: Dokument wurde genehmigt
    - `payment_ready`: Bereit für Zahlung
    - `escalated`: Wurde eskaliert
    """
    try:
        service = get_invoice_pipeline_service(db=db, company_id=company_id)
        result = await service.get_pipeline_status(document_id=document_id)

        return PipelineResultResponse.from_result(result)

    except Exception as e:
        logger.error(
            "pipeline_status_api_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Pipeline-Status"),
        )


@router.post(
    "/{document_id}/approve",
    response_model=PipelineResultResponse,
    summary="Manuell genehmigen",
    description="Genehmigt eine Rechnung manuell und setzt Pipeline fort"
)
async def approve_invoice(
    document_id: UUID,
    company_id: UUID = Depends(get_user_company_id_dep),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PipelineResultResponse:
    """
    Genehmigt eine Rechnung manuell und setzt die Pipeline fort.

    Nach manueller Genehmigung wird das Dokument automatisch als zahlungsbereit markiert.

    **Verwendung:**
    - Für Dokumente mit Status `NEEDS_REVIEW`
    - Für Dokumente, die nicht automatisch genehmigt werden konnten
    - Überschreibt Auto-Approval-Regeln

    **Berechtigungen:**
    - Erfordert Genehmigungsrechte (siehe User-Rolle)
    """
    try:
        service = get_invoice_pipeline_service(db=db, company_id=company_id)
        result = await service.approve_and_continue(
            document_id=document_id,
            user_id=current_user.id,
        )

        logger.info(
            "invoice_manually_approved",
            document_id=str(document_id),
            user_id=str(current_user.id),
            company_id=str(company_id),
        )

        return PipelineResultResponse.from_result(result)

    except Exception as e:
        logger.error(
            "manual_approval_api_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Manuelle Genehmigung"),
        )


@router.get(
    "/stats",
    response_model=PipelineStatsResponse,
    summary="Pipeline-Statistiken",
    description="Zeigt Dashboard-Statistiken für die Rechnungs-Pipeline"
)
async def get_pipeline_stats(
    days: int = 30,
    company_id: UUID = Depends(get_user_company_id_dep),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PipelineStatsResponse:
    """
    Zeigt Pipeline-Statistiken für die letzten N Tage.

    **Metriken:**
    - Gesamt verarbeitete Dokumente
    - Erfolgsrate
    - Auto-Approval-Rate
    - Entity-Linking-Rate
    - Durchschnittliche Confidence
    - Dokumente, die manuelle Prüfung benötigen

    **Parameter:**
    - `days`: Anzahl Tage für Statistik (default: 30)
    """
    try:
        service = get_invoice_pipeline_service(db=db, company_id=company_id)
        stats = await service.get_pipeline_stats(days=days)

        logger.info(
            "pipeline_stats_retrieved",
            days=days,
            total_processed=stats.total_processed,
            company_id=str(company_id),
        )

        return PipelineStatsResponse.from_stats(stats)

    except Exception as e:
        logger.error(
            "pipeline_stats_api_error",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Pipeline-Statistiken"),
        )
