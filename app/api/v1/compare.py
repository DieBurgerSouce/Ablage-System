# -*- coding: utf-8 -*-
"""
Document Comparison API Endpoints.

Phase 9.1: Dream Features - Document Comparison

Ermoeglicht:
- Vergleich zweier Dokumente (Text, Struktur, visuell)
- Diff-Reports mit Unterschieden
- Aehnliche Dokumente finden
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.document_comparison_service import (
    ComparisonType,
    DocumentComparisonService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compare", tags=["Document Comparison"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class CompareDocumentsRequest(BaseModel):
    """Request fuer Dokumentenvergleich."""

    document_id_1: UUID = Field(..., description="ID des ersten Dokuments")
    document_id_2: UUID = Field(..., description="ID des zweiten Dokuments")
    comparison_type: ComparisonType = Field(
        default=ComparisonType.HYBRID,
        description="Art des Vergleichs (text, structured, visual, hybrid)",
    )


class TextDifferenceResponse(BaseModel):
    """Textunterschied."""

    type: str
    position_start: int
    position_end: int
    original_text: str
    new_text: str
    context_before: str
    context_after: str


class FieldChangeResponse(BaseModel):
    """Feldaenderung."""

    field_name: str
    category: str
    old_value: Optional[Any]
    new_value: Optional[Any]
    change_type: str
    significance: str


class ComparisonResultResponse(BaseModel):
    """Vergleichsergebnis."""

    document_id_1: UUID
    document_id_2: UUID
    comparison_type: str
    similarity_score: float
    text_similarity: float
    structure_similarity: float
    text_differences: List[TextDifferenceResponse]
    field_changes: List[FieldChangeResponse]
    summary: str
    compared_at: str


class SimilarDocumentResponse(BaseModel):
    """Aehnliches Dokument."""

    document_id: UUID
    filename: str
    document_type: Optional[str]
    similarity_score: float
    matching_fields: List[str]
    upload_date: str


class DiffReportResponse(BaseModel):
    """Diff-Report."""

    document_1_info: Dict[str, Any]
    document_2_info: Dict[str, Any]
    comparison_result: ComparisonResultResponse
    detailed_changes: List[Dict[str, Any]]
    visual_diff_available: bool
    recommendations: List[str]
    generated_at: str


class FindSimilarRequest(BaseModel):
    """Request fuer Aehnlichkeitssuche."""

    threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Mindest-Aehnlichkeit (0.0-1.0)",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximale Anzahl Ergebnisse",
    )
    include_same_entity: bool = Field(
        default=True,
        description="Dokumente derselben Entity einbeziehen",
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "/documents",
    response_model=ComparisonResultResponse,
    summary="Vergleiche zwei Dokumente",
    description="Fuehrt einen detaillierten Vergleich zweier Dokumente durch.",
)
async def compare_documents(
    request: CompareDocumentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonResultResponse:
    """
    Vergleicht zwei Dokumente und gibt Unterschiede zurueck.

    - **document_id_1**: ID des ersten Dokuments
    - **document_id_2**: ID des zweiten Dokuments
    - **comparison_type**: Art des Vergleichs (text, structured, visual, hybrid)

    Returns:
        ComparisonResultResponse mit Aehnlichkeitswerten und Unterschieden
    """
    service = DocumentComparisonService(db)

    try:
        result = await service.compare_documents(
            doc_id_1=request.document_id_1,
            doc_id_2=request.document_id_2,
            comparison_type=request.comparison_type,
            company_id=current_user.company_id,
        )

        # Convert to response model
        return ComparisonResultResponse(
            document_id_1=result.document_id_1,
            document_id_2=result.document_id_2,
            comparison_type=result.comparison_type.value,
            similarity_score=result.similarity_score,
            text_similarity=result.text_similarity,
            structure_similarity=result.structure_similarity,
            text_differences=[
                TextDifferenceResponse(
                    type=d.type.value,
                    position_start=d.position_start,
                    position_end=d.position_end,
                    original_text=d.original_text,
                    new_text=d.new_text,
                    context_before=d.context_before,
                    context_after=d.context_after,
                )
                for d in result.differences
            ],
            field_changes=[
                FieldChangeResponse(
                    field_name=f.field_name,
                    category=f.category.value,
                    old_value=f.old_value,
                    new_value=f.new_value,
                    change_type=f.change_type,
                    significance=f.significance,
                )
                for f in result.changed_fields
            ],
            summary=result.summary,
            compared_at=result.compared_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Dokumentenvergleich"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Dokumentenvergleich"),
        )
    except Exception as e:
        logger.error("Fehler beim Dokumentenvergleich", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vergleich fehlgeschlagen",
        )


@router.get(
    "/diff/{doc_id_1}/{doc_id_2}",
    response_model=DiffReportResponse,
    summary="Generiere Diff-Report",
    description="Erstellt einen detaillierten Diff-Report fuer zwei Dokumente.",
)
async def get_diff_report(
    doc_id_1: UUID,
    doc_id_2: UUID,
    comparison_type: ComparisonType = Query(
        default=ComparisonType.HYBRID,
        description="Art des Vergleichs",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiffReportResponse:
    """
    Generiert einen vollstaendigen Diff-Report.

    - **doc_id_1**: ID des ersten Dokuments
    - **doc_id_2**: ID des zweiten Dokuments
    - **comparison_type**: Art des Vergleichs

    Returns:
        DiffReportResponse mit vollstaendigem Report
    """
    service = DocumentComparisonService(db)

    try:
        report = await service.generate_diff_report(
            doc_id_1=doc_id_1,
            doc_id_2=doc_id_2,
            comparison_type=comparison_type,
            company_id=current_user.company_id,
        )

        # Convert comparison result
        result = report.comparison_result
        comparison_response = ComparisonResultResponse(
            document_id_1=result.document_id_1,
            document_id_2=result.document_id_2,
            comparison_type=result.comparison_type.value,
            similarity_score=result.similarity_score,
            text_similarity=result.text_similarity,
            structure_similarity=result.structure_similarity,
            text_differences=[
                TextDifferenceResponse(
                    type=d.type.value,
                    position_start=d.position_start,
                    position_end=d.position_end,
                    original_text=d.original_text,
                    new_text=d.new_text,
                    context_before=d.context_before,
                    context_after=d.context_after,
                )
                for d in result.differences
            ],
            field_changes=[
                FieldChangeResponse(
                    field_name=f.field_name,
                    category=f.category.value,
                    old_value=f.old_value,
                    new_value=f.new_value,
                    change_type=f.change_type,
                    significance=f.significance,
                )
                for f in result.changed_fields
            ],
            summary=result.summary,
            compared_at=result.compared_at.isoformat(),
        )

        return DiffReportResponse(
            document_1_info=report.document_1_info,
            document_2_info=report.document_2_info,
            comparison_result=comparison_response,
            detailed_changes=report.detailed_changes,
            visual_diff_available=report.visual_diff_available,
            recommendations=report.recommendations,
            generated_at=report.generated_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Differenzanalyse"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Differenzanalyse"),
        )
    except Exception as e:
        logger.error("Fehler bei Diff-Report-Generierung", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report-Generierung fehlgeschlagen",
        )


@router.get(
    "/similar/{doc_id}",
    response_model=List[SimilarDocumentResponse],
    summary="Finde aehnliche Dokumente",
    description="Sucht nach Dokumenten, die dem angegebenen Dokument aehnlich sind.",
)
async def find_similar_documents(
    doc_id: UUID,
    threshold: float = Query(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Mindest-Aehnlichkeit (0.0-1.0)",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximale Anzahl Ergebnisse",
    ),
    include_same_entity: bool = Query(
        default=True,
        description="Dokumente derselben Entity einbeziehen",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SimilarDocumentResponse]:
    """
    Findet aehnliche Dokumente basierend auf Inhalt und Struktur.

    - **doc_id**: ID des Referenzdokuments
    - **threshold**: Mindest-Aehnlichkeitsscore (0.8 = 80%)
    - **limit**: Maximale Anzahl Ergebnisse
    - **include_same_entity**: Auch Dokumente derselben Entity einbeziehen

    Returns:
        Liste aehnlicher Dokumente mit Aehnlichkeitswerten
    """
    service = DocumentComparisonService(db)

    try:
        similar_docs = await service.find_similar_documents(
            doc_id=doc_id,
            threshold=threshold,
            limit=limit,
            include_same_entity=include_same_entity,
            company_id=current_user.company_id,
        )

        return [
            SimilarDocumentResponse(
                document_id=doc.document_id,
                filename=doc.filename,
                document_type=doc.document_type,
                similarity_score=doc.similarity_score,
                matching_fields=doc.matching_fields,
                upload_date=doc.upload_date.isoformat(),
            )
            for doc in similar_docs
        ]

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Aehnlichkeitssuche"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Aehnlichkeitssuche"),
        )
    except Exception as e:
        logger.error("Fehler bei Aehnlichkeitssuche", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aehnlichkeitssuche fehlgeschlagen",
        )


@router.post(
    "/batch",
    response_model=List[ComparisonResultResponse],
    summary="Batch-Vergleich mehrerer Dokumente",
    description="Vergleicht ein Dokument mit mehreren anderen Dokumenten.",
)
async def batch_compare_documents(
    reference_doc_id: UUID = Query(..., description="Referenzdokument-ID"),
    compare_doc_ids: List[UUID] = Query(..., description="Zu vergleichende Dokument-IDs"),
    comparison_type: ComparisonType = Query(
        default=ComparisonType.HYBRID,
        description="Art des Vergleichs",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ComparisonResultResponse]:
    """
    Fuehrt einen Batch-Vergleich durch.

    - **reference_doc_id**: ID des Referenzdokuments
    - **compare_doc_ids**: Liste der zu vergleichenden Dokument-IDs
    - **comparison_type**: Art des Vergleichs

    Returns:
        Liste von Vergleichsergebnissen
    """
    if len(compare_doc_ids) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximal 20 Dokumente pro Batch-Vergleich erlaubt",
        )

    service = DocumentComparisonService(db)
    results = []

    for compare_id in compare_doc_ids:
        try:
            result = await service.compare_documents(
                doc_id_1=reference_doc_id,
                doc_id_2=compare_id,
                comparison_type=comparison_type,
                company_id=current_user.company_id,
            )

            results.append(
                ComparisonResultResponse(
                    document_id_1=result.document_id_1,
                    document_id_2=result.document_id_2,
                    comparison_type=result.comparison_type.value,
                    similarity_score=result.similarity_score,
                    text_similarity=result.text_similarity,
                    structure_similarity=result.structure_similarity,
                    text_differences=[
                        TextDifferenceResponse(
                            type=d.type.value,
                            position_start=d.position_start,
                            position_end=d.position_end,
                            original_text=d.original_text,
                            new_text=d.new_text,
                            context_before=d.context_before,
                            context_after=d.context_after,
                        )
                        for d in result.differences
                    ],
                    field_changes=[
                        FieldChangeResponse(
                            field_name=f.field_name,
                            category=f.category.value,
                            old_value=f.old_value,
                            new_value=f.new_value,
                            change_type=f.change_type,
                            significance=f.significance,
                        )
                        for f in result.changed_fields
                    ],
                    summary=result.summary,
                    compared_at=result.compared_at.isoformat(),
                )
            )
        except (ValueError, PermissionError) as e:
            logger.warning("Ueberspringe Dokument im Batch-Vergleich", **safe_error_log(e))
            continue
        except Exception as e:
            logger.error("Fehler bei Batch-Vergleich", **safe_error_log(e))
            continue

    return results


@router.get(
    "/duplicates",
    response_model=List[Dict[str, Any]],
    summary="Finde potenzielle Duplikate",
    description="Sucht nach potenziellen Duplikaten in der Dokumentenbasis.",
)
async def find_potential_duplicates(
    threshold: float = Query(
        default=0.95,
        ge=0.8,
        le=1.0,
        description="Mindest-Aehnlichkeit fuer Duplikat-Erkennung",
    ),
    days_back: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Zeitraum in Tagen",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximale Anzahl Ergebnisse",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Identifiziert potenzielle Duplikate basierend auf hoher Aehnlichkeit.

    - **threshold**: Mindest-Aehnlichkeit (Standard: 95%)
    - **days_back**: Zeitraum fuer Suche (Standard: 30 Tage)
    - **limit**: Maximale Anzahl Ergebnisse

    Returns:
        Liste von Duplikat-Paaren mit Aehnlichkeitswerten
    """
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from app.db.models import Document

    service = DocumentComparisonService(db)

    # Hole neueste Dokumente
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)

    stmt = (
        select(Document)
        .where(Document.company_id == current_user.company_id)
        .where(Document.created_at >= cutoff_date)
        .where(Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
        .limit(100)  # Beschraenke auf 100 fuer Performance
    )

    result = await db.execute(stmt)
    documents = result.scalars().all()

    duplicates = []
    checked_pairs = set()

    for i, doc1 in enumerate(documents):
        for doc2 in documents[i + 1 :]:
            pair_key = tuple(sorted([str(doc1.id), str(doc2.id)]))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            try:
                comparison = await service.compare_documents(
                    doc_id_1=doc1.id,
                    doc_id_2=doc2.id,
                    comparison_type=ComparisonType.HYBRID,
                    company_id=current_user.company_id,
                )

                if comparison.similarity_score >= threshold:
                    duplicates.append(
                        {
                            "document_1": {
                                "id": str(doc1.id),
                                "filename": doc1.filename,
                                "created_at": doc1.created_at.isoformat(),
                            },
                            "document_2": {
                                "id": str(doc2.id),
                                "filename": doc2.filename,
                                "created_at": doc2.created_at.isoformat(),
                            },
                            "similarity_score": comparison.similarity_score,
                            "recommendation": "Pruefung empfohlen"
                            if comparison.similarity_score < 0.99
                            else "Wahrscheinlich identisch",
                        }
                    )

                    if len(duplicates) >= limit:
                        break

            except Exception as e:
                logger.debug("Fehler bei Duplikat-Check", **safe_error_log(e))
                continue

        if len(duplicates) >= limit:
            break

    return duplicates
