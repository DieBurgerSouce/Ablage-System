# -*- coding: utf-8 -*-
"""
KI-Pipeline API Endpoints.

REST API fuer die KI-Pipeline Intelligence (Feature #4):
- Confidence-Reports und -Reviews
- Benutzer-Korrekturen mit Lern-Trigger
- Cross-Dokument-Matching und Diskrepanzen
- Dokumenten-Zusammenfassungen
- Lernstatistiken

Feinpoliert und durchdacht - Deutsche Praezision.
"""

import structlog
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_current_company_id
from app.core.safe_errors import safe_error_log
from app.db.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ki-pipeline", tags=["KI-Pipeline"])


# =============================================================================
# SCHEMAS
# =============================================================================


class FieldConfidenceResponse(BaseModel):
    """Confidence-Bewertung eines einzelnen Feldes."""
    model_config = ConfigDict(from_attributes=True)

    field_name: str
    extracted_value: str
    confidence_score: float
    confidence_level: str
    is_corrected: bool = False
    corrected_value: Optional[str] = None
    extraction_method: str = "ocr"


class ConfidenceReportResponse(BaseModel):
    """Gesamter Confidence-Report fuer ein Dokument."""
    document_id: str
    total_fields: int
    auto_accepted: int
    review_needed: int
    manual_required: int
    average_confidence: float
    fields: List[FieldConfidenceResponse]


class CorrectionRequest(BaseModel):
    """Anfrage fuer eine Feld-Korrektur."""
    field_name: str = Field(
        ...,
        description="Name des zu korrigierenden Feldes",
        max_length=200,
    )
    corrected_value: str = Field(
        ...,
        description="Korrigierter Wert",
        max_length=5000,
    )


class CorrectionResponse(BaseModel):
    """Antwort nach erfolgreicher Korrektur."""
    field_name: str
    original_value: Optional[str] = None
    corrected_value: str
    learning_triggered: bool


class AcceptAllResponse(BaseModel):
    """Antwort nach Auto-Accept aller High-Confidence Felder."""
    document_id: str
    accepted_count: int


class LearningProfileResponse(BaseModel):
    """Lernprofil-Informationen."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    profile_type: str
    profile_key: str
    correction_count: int
    confidence_boost: float
    has_overrides: bool


class LearningStatisticsResponse(BaseModel):
    """Statistiken zum Lernfortschritt."""
    total_profiles: int
    total_corrections: int
    profiles_with_active_rules: int
    average_confidence_boost: float
    profiles_by_type: Dict[str, int]


class CrossDocMatchResponse(BaseModel):
    """Cross-Document-Match Ergebnis."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_a_id: str
    document_b_id: str
    match_type: str
    match_score: float
    status: str
    discrepancy_count: int
    field_comparisons: List[Dict[str, object]]
    discrepancies: List[Dict[str, object]]


class DiscrepancyResponse(BaseModel):
    """Einzelne Diskrepanz."""
    match_id: str
    related_document_id: str
    field: str
    expected: str
    actual: str
    severity: str
    description: str


class DocumentSummaryResponse(BaseModel):
    """Dokumenten-Zusammenfassung."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    summary_text: str
    summary_template: str
    key_facts: Dict[str, object]
    generated_at: Optional[str] = None
    model_used: str


class GenerateSummaryRequest(BaseModel):
    """Anfrage zur Zusammenfassungs-Generierung."""
    document_type: Optional[str] = Field(
        None,
        description="Optionaler Dokumenttyp (auto-detect wenn leer)",
    )


# =============================================================================
# CONFIDENCE ENDPOINTS
# =============================================================================


@router.get(
    "/confidence/{document_id}",
    response_model=ConfidenceReportResponse,
    summary="Confidence-Report fuer Dokument",
    description="Gibt den vollstaendigen Confidence-Report mit allen Feldern zurueck.",
)
async def get_confidence_report(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConfidenceReportResponse:
    """Confidence-Report fuer ein Dokument abrufen."""
    from app.services.confidence_extraction_service import (
        get_confidence_extraction_service,
    )

    try:
        service = get_confidence_extraction_service()
        report = await service.get_document_confidence_report(db, document_id)

        return ConfidenceReportResponse(
            document_id=report.document_id,
            total_fields=report.total_fields,
            auto_accepted=report.auto_accepted,
            review_needed=report.review_needed,
            manual_required=report.manual_required,
            average_confidence=report.average_confidence,
            fields=[
                FieldConfidenceResponse(
                    field_name=f.field_name,
                    extracted_value=f.extracted_value,
                    confidence_score=f.confidence_score,
                    confidence_level=f.confidence_level,
                    is_corrected=f.is_corrected,
                    corrected_value=f.corrected_value,
                    extraction_method=f.extraction_method,
                )
                for f in report.fields
            ],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "confidence_report_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Confidence-Report konnte nicht erstellt werden",
        )


@router.get(
    "/confidence/{document_id}/review",
    response_model=List[FieldConfidenceResponse],
    summary="Felder zur manuellen Pruefung",
    description="Gibt Felder zurueck die manuelle Pruefung benoetigen (Score < 90%).",
)
async def get_fields_for_review(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[FieldConfidenceResponse]:
    """Felder die manuelle Pruefung benoetigen abrufen."""
    from app.services.confidence_extraction_service import (
        get_confidence_extraction_service,
    )

    try:
        service = get_confidence_extraction_service()
        fields = await service.get_low_confidence_fields(db, document_id)

        return [
            FieldConfidenceResponse(
                field_name=f.field_name,
                extracted_value=f.extracted_value or "",
                confidence_score=f.confidence_score,
                confidence_level=f.confidence_level,
                is_corrected=f.was_corrected,
                corrected_value=f.corrected_value,
                extraction_method=f.extraction_method,
            )
            for f in fields
        ]
    except Exception as e:
        logger.error(
            "review_fields_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pruefungsfelder konnten nicht geladen werden",
        )


@router.post(
    "/confidence/{document_id}/correct",
    response_model=CorrectionResponse,
    summary="Korrektur einreichen",
    description="Reicht eine Korrektur fuer ein extrahiertes Feld ein und triggert das Lernsystem.",
)
async def submit_correction(
    document_id: UUID,
    correction: CorrectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CorrectionResponse:
    """Korrektur fuer ein extrahiertes Feld einreichen."""
    from app.services.confidence_extraction_service import (
        get_confidence_extraction_service,
    )

    try:
        service = get_confidence_extraction_service()
        record = await service.apply_user_correction(
            db=db,
            document_id=document_id,
            field_name=correction.field_name,
            corrected_value=correction.corrected_value,
            user_id=current_user.id,
        )
        await db.commit()

        return CorrectionResponse(
            field_name=record.field_name,
            original_value=record.extracted_value,
            corrected_value=record.corrected_value or correction.corrected_value,
            learning_triggered=True,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "correction_failed",
            document_id=str(document_id),
            field_name=correction.field_name,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Korrektur konnte nicht gespeichert werden",
        )


@router.post(
    "/confidence/{document_id}/accept-all",
    response_model=AcceptAllResponse,
    summary="Alle High-Confidence Felder akzeptieren",
    description="Akzeptiert automatisch alle Felder mit Confidence >= 90%.",
)
async def accept_all_high_confidence(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AcceptAllResponse:
    """Alle High-Confidence Felder automatisch akzeptieren."""
    from app.services.confidence_extraction_service import (
        get_confidence_extraction_service,
    )

    try:
        service = get_confidence_extraction_service()
        accepted_count = await service.auto_accept_high_confidence(db, document_id)
        await db.commit()

        return AcceptAllResponse(
            document_id=str(document_id),
            accepted_count=accepted_count,
        )
    except Exception as e:
        logger.error(
            "accept_all_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auto-Accept fehlgeschlagen",
        )


# =============================================================================
# LEARNING ENDPOINTS
# =============================================================================


@router.get(
    "/learning/profiles",
    response_model=List[LearningProfileResponse],
    summary="Lernprofile auflisten",
    description="Listet alle Lernprofile fuer die aktuelle Firma auf.",
)
async def list_learning_profiles(
    profile_type: Optional[str] = Query(
        None,
        description="Filtern nach Typ: supplier oder document_type",
    ),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> List[LearningProfileResponse]:
    """Lernprofile der aktuellen Firma auflisten."""
    from app.db.models_ki_pipeline import LearningProfile
    from sqlalchemy import select, and_

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firma-ID erforderlich (X-Company-ID Header)",
        )

    try:
        conditions = [LearningProfile.company_id == company_id]
        if profile_type:
            conditions.append(LearningProfile.profile_type == profile_type)

        result = await db.execute(
            select(LearningProfile)
            .where(and_(*conditions))
            .order_by(LearningProfile.correction_count.desc())
            .limit(limit)
        )
        profiles = result.scalars().all()

        return [
            LearningProfileResponse(
                id=str(p.id),
                company_id=str(p.company_id),
                profile_type=p.profile_type,
                profile_key=p.profile_key,
                correction_count=p.correction_count or 0,
                confidence_boost=p.confidence_boost or 0.0,
                has_overrides=bool(p.field_overrides),
            )
            for p in profiles
        ]
    except Exception as e:
        logger.error(
            "list_profiles_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lernprofile konnten nicht geladen werden",
        )


@router.get(
    "/learning/statistics",
    response_model=LearningStatisticsResponse,
    summary="Lernstatistiken",
    description="Gibt Statistiken zum Lernfortschritt der aktuellen Firma zurueck.",
)
async def get_learning_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> LearningStatisticsResponse:
    """Lernstatistiken der aktuellen Firma abrufen."""
    from app.services.extraction_learning_service import (
        get_extraction_learning_service,
    )

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firma-ID erforderlich (X-Company-ID Header)",
        )

    try:
        service = get_extraction_learning_service()
        stats = await service.get_learning_statistics(db, company_id)

        return LearningStatisticsResponse(
            total_profiles=int(stats.get("total_profiles", 0)),
            total_corrections=int(stats.get("total_corrections", 0)),
            profiles_with_active_rules=int(stats.get("profiles_with_active_rules", 0)),
            average_confidence_boost=float(stats.get("average_confidence_boost", 0.0)),
            profiles_by_type=dict(stats.get("profiles_by_type", {})),
        )
    except Exception as e:
        logger.error(
            "learning_statistics_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lernstatistiken konnten nicht geladen werden",
        )


# =============================================================================
# CROSS-DOCUMENT ENDPOINTS
# =============================================================================


@router.get(
    "/cross-doc/{document_id}/matches",
    response_model=List[CrossDocMatchResponse],
    summary="Cross-Document Matches",
    description="Gibt alle Cross-Document-Matches fuer ein Dokument zurueck.",
)
async def get_cross_doc_matches(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> List[CrossDocMatchResponse]:
    """Cross-Document-Matches fuer ein Dokument abrufen."""
    from app.services.cross_document_intelligence_service import (
        get_cross_document_intelligence_service,
    )

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firma-ID erforderlich",
        )

    try:
        service = get_cross_document_intelligence_service()
        matches = await service.find_related_documents(
            db=db,
            company_id=company_id,
            document_id=document_id,
        )

        return [
            CrossDocMatchResponse(
                id=str(m.id),
                document_a_id=str(m.document_a_id),
                document_b_id=str(m.document_b_id),
                match_type=m.match_type,
                match_score=m.match_score,
                status=m.status,
                discrepancy_count=len(m.discrepancies or []),
                field_comparisons=m.field_comparisons or [],
                discrepancies=m.discrepancies or [],
            )
            for m in matches
        ]
    except Exception as e:
        logger.error(
            "cross_doc_matches_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cross-Document-Matches konnten nicht geladen werden",
        )


@router.get(
    "/cross-doc/{document_id}/discrepancies",
    response_model=List[DiscrepancyResponse],
    summary="Diskrepanzen fuer Dokument",
    description="Gibt alle erkannten Diskrepanzen fuer ein Dokument zurueck.",
)
async def get_discrepancies(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> List[DiscrepancyResponse]:
    """Diskrepanzen fuer ein Dokument abrufen."""
    from app.services.cross_document_intelligence_service import (
        get_cross_document_intelligence_service,
    )

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firma-ID erforderlich",
        )

    try:
        service = get_cross_document_intelligence_service()
        anomalies = await service.detect_anomalies(
            db=db,
            company_id=company_id,
            document_id=document_id,
        )

        return [
            DiscrepancyResponse(
                match_id=str(a.get("match_id", "")),
                related_document_id=str(a.get("related_document_id", "")),
                field=str(a.get("field", "")),
                expected=str(a.get("expected", "")),
                actual=str(a.get("actual", "")),
                severity=str(a.get("severity", "info")),
                description=str(a.get("description", "")),
            )
            for a in anomalies
        ]
    except Exception as e:
        logger.error(
            "discrepancies_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Diskrepanzen konnten nicht geladen werden",
        )


# =============================================================================
# SUMMARY ENDPOINTS
# =============================================================================


@router.get(
    "/summary/{document_id}",
    response_model=DocumentSummaryResponse,
    summary="Dokumenten-Zusammenfassung",
    description="Gibt die Zusammenfassung fuer ein Dokument zurueck.",
)
async def get_document_summary(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentSummaryResponse:
    """Zusammenfassung fuer ein Dokument abrufen."""
    from app.services.document_summary_service import (
        get_document_summary_service,
    )

    try:
        service = get_document_summary_service()
        summary = await service.get_summary(db, document_id)

        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Keine Zusammenfassung fuer dieses Dokument vorhanden",
            )

        return DocumentSummaryResponse(
            id=str(summary.id),
            document_id=str(summary.document_id),
            summary_text=summary.summary_text,
            summary_template=summary.summary_template,
            key_facts=summary.key_facts or {},
            generated_at=(
                summary.generated_at.isoformat()
                if summary.generated_at else None
            ),
            model_used=summary.model_used,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_summary_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Zusammenfassung konnte nicht geladen werden",
        )


@router.post(
    "/summary/{document_id}/generate",
    response_model=DocumentSummaryResponse,
    summary="Zusammenfassung generieren",
    description="Generiert oder regeneriert die Zusammenfassung fuer ein Dokument.",
)
async def generate_summary(
    document_id: UUID,
    request: Optional[GenerateSummaryRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> DocumentSummaryResponse:
    """Zusammenfassung fuer ein Dokument generieren/regenerieren."""
    from app.services.document_summary_service import (
        get_document_summary_service,
    )

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firma-ID erforderlich (X-Company-ID Header)",
        )

    try:
        service = get_document_summary_service()

        document_type = None
        if request:
            document_type = request.document_type

        summary = await service.generate_summary(
            db=db,
            document_id=document_id,
            company_id=company_id,
            document_type=document_type,
        )
        await db.commit()

        return DocumentSummaryResponse(
            id=str(summary.id),
            document_id=str(summary.document_id),
            summary_text=summary.summary_text,
            summary_template=summary.summary_template,
            key_facts=summary.key_facts or {},
            generated_at=(
                summary.generated_at.isoformat()
                if summary.generated_at else None
            ),
            model_used=summary.model_used,
        )
    except Exception as e:
        logger.error(
            "generate_summary_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Zusammenfassung konnte nicht generiert werden",
        )
