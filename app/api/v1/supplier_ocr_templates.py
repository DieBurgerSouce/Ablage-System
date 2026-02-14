# -*- coding: utf-8 -*-
"""
Supplier OCR Templates API.

Vision 2026+ Feature #2: Dokumenten-Template-System (Lieferanten-spezifisch)
API fuer Lieferanten-spezifische OCR-Templates.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from app.core.types import JSONDict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_ocr_template import (
    FieldExtractionType,
    TemplateMatchingStrategy,
)
from app.services.ocr.supplier_template_service import SupplierTemplateService
from app.services.ocr.auto_template_service import get_auto_template_service

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/ocr-templates",
    tags=["Supplier OCR Templates"],
)


# =============================================================================
# Request/Response Schemas
# =============================================================================

class FieldDefinitionSchema(BaseModel):
    """Schema fuer eine Feld-Definition."""
    name: str = Field(..., min_length=1, max_length=100, description="Feldname")
    label: str = Field(..., min_length=1, max_length=255, description="Anzeigename")
    type: str = Field(
        default=FieldExtractionType.BOUNDING_BOX.value,
        description="Extraktionstyp"
    )
    coordinates: Optional[Dict[str, int]] = Field(
        None,
        description="Bounding Box Koordinaten (x, y, width, height)"
    )
    page: int = Field(default=1, ge=1, le=100, description="Seitennummer")
    anchor_text: Optional[str] = Field(None, max_length=255, description="Anker-Text")
    offset: Optional[Dict[str, int]] = Field(None, description="Offset relativ zum Anker")
    regex_pattern: Optional[str] = Field(None, max_length=500, description="Regex-Pattern")
    preprocessing: List[str] = Field(default_factory=list, description="Preprocessing-Schritte")
    validation_regex: Optional[str] = Field(None, max_length=500, description="Validierungs-Regex")
    confidence_boost: float = Field(default=0.0, ge=-0.5, le=0.5, description="Confidence-Boost")
    required: bool = Field(default=False, description="Pflichtfeld")


class TemplateCreate(BaseModel):
    """Schema fuer Template-Erstellung."""
    entity_id: uuid.UUID = Field(..., description="Lieferanten-ID")
    name: str = Field(..., min_length=1, max_length=255, description="Template-Name")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    document_type: str = Field(default="invoice_incoming", description="Dokumenttyp")
    matching_strategy: str = Field(
        default=TemplateMatchingStrategy.COMBINED.value,
        description="Matching-Strategie"
    )
    text_anchors: List[str] = Field(default_factory=list, description="Text-Anker fuer Matching")
    header_patterns: List[str] = Field(default_factory=list, description="Header-Patterns (Regex)")
    field_definitions: List[FieldDefinitionSchema] = Field(
        default_factory=list,
        description="Feld-Definitionen"
    )


class TemplateUpdate(BaseModel):
    """Schema fuer Template-Aktualisierung."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    document_type: Optional[str] = None
    matching_strategy: Optional[str] = None
    text_anchors: Optional[List[str]] = None
    header_patterns: Optional[List[str]] = None
    field_definitions: Optional[List[FieldDefinitionSchema]] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    auto_apply: Optional[bool] = None


class TemplateResponse(BaseModel):
    """Response fuer ein Template."""
    id: str
    entity_id: str
    company_id: str
    name: str
    description: Optional[str] = None
    document_type: str
    version: int
    matching_strategy: str
    text_anchors: List[str] = Field(default_factory=list)
    field_definitions: List[JSONDict] = Field(default_factory=list)
    training_document_count: int = 0
    accuracy_score: Optional[float] = None
    usage_count: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    average_confidence: Optional[float] = None
    is_active: bool = True
    is_verified: bool = False
    auto_apply: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TrainFromDocumentRequest(BaseModel):
    """Request fuer Template-Training."""
    document_id: uuid.UUID = Field(..., description="Dokument-ID")
    corrected_values: JSONDict = Field(..., description="Korrigierte Feldwerte")
    entity_id: Optional[uuid.UUID] = Field(None, description="Lieferanten-ID")
    template_id: Optional[uuid.UUID] = Field(None, description="Existierendes Template")


class TemplateMatchRequest(BaseModel):
    """Request fuer Template-Matching."""
    document_id: uuid.UUID = Field(..., description="Dokument-ID")
    entity_id: Optional[uuid.UUID] = Field(None, description="Optionale Entity-ID")
    ocr_text: Optional[str] = Field(None, description="OCR-Text fuer Matching")


class TemplateMatchResponse(BaseModel):
    """Response fuer Template-Matching."""
    matched: bool
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    confidence: float = 0.0
    strategy_used: Optional[str] = None
    candidates_count: int = 0


class TemplateStatisticsResponse(BaseModel):
    """Response fuer Template-Statistiken."""
    total_templates: int
    total_usage: int
    total_successful: int
    success_rate: float
    average_confidence: Optional[float] = None


class TemplateCandidateResponse(BaseModel):
    """Response fuer einen Template-Kandidaten."""
    entity_id: str
    company_id: str
    document_count: int
    matching_fields: List[str]
    avg_position_variance: float
    is_candidate: bool
    document_ids: List[str]


class GenerateFromCandidateRequest(BaseModel):
    """Request fuer Template-Generierung aus Kandidat."""
    entity_id: uuid.UUID = Field(..., description="Entity-ID des Kandidaten")
    document_ids: List[uuid.UUID] = Field(
        ..., min_length=3, description="Dokument-IDs fuer Template-Generierung"
    )
    name: Optional[str] = Field(None, max_length=255, description="Template-Name")


class TemplateTestRequest(BaseModel):
    """Request fuer Template-Test gegen ein Dokument."""
    document_id: uuid.UUID = Field(..., description="Dokument-ID zum Testen")


class TemplateTestResponse(BaseModel):
    """Response fuer Template-Test."""
    template_id: str
    template_name: str
    document_id: str
    used_template: bool
    match_confidence: float
    overall_confidence: float
    fields_extracted: int
    fields_failed: int
    processing_time_ms: int
    extractions: List[JSONDict]


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "",
    response_model=List[TemplateResponse],
    summary="Alle Templates auflisten",
    description="Listet alle OCR-Templates der Company auf.",
)
async def list_templates(
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter nach Lieferant"),
    active_only: bool = Query(True, description="Nur aktive Templates"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TemplateResponse]:
    """Listet alle OCR-Templates auf."""
    service = SupplierTemplateService(db)

    if entity_id:
        templates = await service.get_templates_for_entity(
            entity_id=entity_id,
            company_id=current_user.company_id,
            active_only=active_only,
        )
    else:
        # Alle Templates der Company laden
        from sqlalchemy import select
        from app.db.models_ocr_template import SupplierOCRTemplate

        query = select(SupplierOCRTemplate).where(
            SupplierOCRTemplate.company_id == current_user.company_id,
        )
        if active_only:
            query = query.where(SupplierOCRTemplate.is_active == True)

        result = await db.execute(query)
        templates = list(result.scalars().all())

    return [TemplateResponse(**t.to_dict()) for t in templates]


@router.post(
    "",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Template erstellen",
    description="Erstellt ein neues OCR-Template fuer einen Lieferanten.",
)
async def create_template(
    data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateResponse:
    """Erstellt ein neues OCR-Template."""
    # Validiere Matching-Strategie
    valid_strategies = [s.value for s in TemplateMatchingStrategy]
    if data.matching_strategy not in valid_strategies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltige matching_strategy. Erlaubt: {valid_strategies}"
        )

    # Validiere Feld-Typen
    valid_types = [t.value for t in FieldExtractionType]
    for field_def in data.field_definitions:
        if field_def.type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger Feldtyp '{field_def.type}'. Erlaubt: {valid_types}"
            )

    service = SupplierTemplateService(db)
    template = await service.create_template(
        entity_id=data.entity_id,
        company_id=current_user.company_id,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        document_type=data.document_type,
        matching_strategy=data.matching_strategy,
        text_anchors=data.text_anchors,
        field_definitions=[f.model_dump() for f in data.field_definitions],
    )

    return TemplateResponse(**template.to_dict())


@router.get(
    "/{template_id}",
    response_model=TemplateResponse,
    summary="Template abrufen",
    description="Holt ein spezifisches OCR-Template.",
)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateResponse:
    """Holt ein spezifisches Template."""
    service = SupplierTemplateService(db)
    template = await service.get_template(
        template_id=template_id,
        company_id=current_user.company_id,
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden"
        )

    return TemplateResponse(**template.to_dict())


@router.patch(
    "/{template_id}",
    response_model=TemplateResponse,
    summary="Template aktualisieren",
    description="Aktualisiert ein bestehendes OCR-Template.",
)
async def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateResponse:
    """Aktualisiert ein Template."""
    # Validierungen
    if data.matching_strategy:
        valid_strategies = [s.value for s in TemplateMatchingStrategy]
        if data.matching_strategy not in valid_strategies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltige matching_strategy. Erlaubt: {valid_strategies}"
            )

    if data.field_definitions:
        valid_types = [t.value for t in FieldExtractionType]
        for field_def in data.field_definitions:
            if field_def.type not in valid_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ungueltiger Feldtyp '{field_def.type}'. Erlaubt: {valid_types}"
                )

    update_data = data.model_dump(exclude_unset=True)
    if "field_definitions" in update_data:
        update_data["field_definitions"] = [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in update_data["field_definitions"]
        ]

    service = SupplierTemplateService(db)
    template = await service.update_template(
        template_id=template_id,
        company_id=current_user.company_id,
        **update_data,
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden"
        )

    return TemplateResponse(**template.to_dict())


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Template loeschen",
    description="Deaktiviert ein OCR-Template (Soft-Delete).",
)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loescht ein Template (Soft-Delete)."""
    service = SupplierTemplateService(db)
    deleted = await service.delete_template(
        template_id=template_id,
        company_id=current_user.company_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden"
        )


@router.post(
    "/train-from-document",
    response_model=TemplateResponse,
    summary="Template aus Dokument trainieren",
    description="Trainiert ein Template basierend auf korrigierten Dokumentwerten.",
)
async def train_from_document(
    data: TrainFromDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateResponse:
    """Trainiert ein Template aus einem korrigierten Dokument."""
    service = SupplierTemplateService(db)

    try:
        template = await service.train_from_document(
            document_id=data.document_id,
            company_id=current_user.company_id,
            user_id=current_user.id,
            corrected_values=data.corrected_values,
            entity_id=data.entity_id,
            template_id=data.template_id,
        )
        return TemplateResponse(**template.to_dict())

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "OCR-Vorlage")
        )


@router.post(
    "/match",
    response_model=TemplateMatchResponse,
    summary="Template-Matching durchfuehren",
    description="Findet das passende Template fuer ein Dokument.",
)
async def match_template(
    data: TemplateMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateMatchResponse:
    """Fuehrt Template-Matching fuer ein Dokument durch."""
    service = SupplierTemplateService(db)

    result = await service.find_matching_template(
        document_id=data.document_id,
        company_id=current_user.company_id,
        entity_id=data.entity_id,
        ocr_text=data.ocr_text,
    )

    return TemplateMatchResponse(
        matched=result.matched,
        template_id=str(result.template.id) if result.template else None,
        template_name=result.template.name if result.template else None,
        confidence=result.confidence,
        strategy_used=result.strategy_used,
        candidates_count=len(result.candidates_checked),
    )


@router.get(
    "/statistics/overview",
    response_model=TemplateStatisticsResponse,
    summary="Template-Statistiken",
    description="Holt Uebersichtsstatistiken zu allen Templates.",
)
async def get_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateStatisticsResponse:
    """Holt Template-Statistiken."""
    service = SupplierTemplateService(db)
    stats = await service.get_template_statistics(current_user.company_id)

    return TemplateStatisticsResponse(**stats)


@router.get(
    "/entities/{entity_id}",
    response_model=List[TemplateResponse],
    summary="Templates eines Lieferanten",
    description="Listet alle Templates eines spezifischen Lieferanten auf.",
)
async def get_entity_templates(
    entity_id: uuid.UUID,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TemplateResponse]:
    """Holt alle Templates eines Lieferanten."""
    service = SupplierTemplateService(db)
    templates = await service.get_templates_for_entity(
        entity_id=entity_id,
        company_id=current_user.company_id,
        active_only=active_only,
    )

    return [TemplateResponse(**t.to_dict()) for t in templates]


@router.get(
    "/field-types",
    summary="Verfuegbare Feldtypen",
    description="Listet alle verfuegbaren Extraktions-Typen auf.",
)
async def get_field_types() -> JSONDict:
    """Listet verfuegbare Feld-Extraktions-Typen auf."""
    return {
        "field_types": [
            {
                "value": t.value,
                "label": {
                    "bounding_box": "Bounding Box (Feste Position)",
                    "regex": "Regulaerer Ausdruck",
                    "anchor_relative": "Relativ zu Anker-Text",
                    "table_cell": "Tabellenzelle",
                    "semantic": "Semantische Erkennung",
                }.get(t.value, t.value),
            }
            for t in FieldExtractionType
        ],
        "matching_strategies": [
            {
                "value": s.value,
                "label": {
                    "logo_match": "Logo-Erkennung",
                    "layout_hash": "Layout-Fingerprint",
                    "text_anchor": "Text-Anker",
                    "header_pattern": "Header-Muster",
                    "combined": "Kombiniert (Empfohlen)",
                }.get(s.value, s.value),
            }
            for s in TemplateMatchingStrategy
        ],
        "preprocessing_options": [
            {"value": "trim", "label": "Whitespace entfernen"},
            {"value": "uppercase", "label": "Grossbuchstaben"},
            {"value": "lowercase", "label": "Kleinbuchstaben"},
            {"value": "extract_number", "label": "Nur Zahlen extrahieren"},
            {"value": "normalize_german_number", "label": "Deutsche Zahlen normalisieren (1.234,56 -> 1234.56)"},
            {"value": "remove_prefix:X", "label": "Prefix entfernen (X ersetzen)"},
            {"value": "remove_suffix:X", "label": "Suffix entfernen (X ersetzen)"},
        ],
    }


# =============================================================================
# Auto-Template Kandidaten & Generierung
# =============================================================================


@router.get(
    "/candidates",
    response_model=List[TemplateCandidateResponse],
    summary="Template-Kandidaten auflisten",
    description="Listet alle Lieferanten auf, die genug Dokumente fuer eine automatische Template-Generierung haben.",
)
async def list_template_candidates(
    min_documents: int = Query(3, ge=2, le=50, description="Mindestanzahl Dokumente"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TemplateCandidateResponse]:
    """Listet Template-Kandidaten auf."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung",
        )

    service = get_auto_template_service()

    try:
        candidates = await service.list_candidates(
            db=db,
            company_id=company_id,
            min_documents=min_documents,
        )
    except Exception as e:
        logger.error("candidate_listing_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Kandidaten-Abfrage"),
        )

    return [
        TemplateCandidateResponse(
            entity_id=str(c.entity_id),
            company_id=str(c.company_id),
            document_count=c.document_count,
            matching_fields=c.matching_fields,
            avg_position_variance=round(c.avg_position_variance, 6),
            is_candidate=c.is_candidate,
            document_ids=[str(did) for did in c.document_ids],
        )
        for c in candidates
    ]


@router.post(
    "/generate",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Template aus Kandidat generieren",
    description="Generiert ein OCR-Template aus einem Kandidaten mit ausreichend Dokumenten.",
)
async def generate_template_from_candidate(
    data: GenerateFromCandidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateResponse:
    """Generiert ein Template aus einem Kandidaten."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung",
        )

    service = get_auto_template_service()

    try:
        template = await service.generate_template(
            db=db,
            entity_id=data.entity_id,
            company_id=company_id,
            document_ids=data.document_ids,
            name=data.name,
        )

        # Auto-Aktivierung pruefen
        await service.check_and_auto_activate(db, template)

        await db.commit()

        return TemplateResponse(**template.to_dict())

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Template-Generierung"),
        )
    except Exception as e:
        logger.error("template_generation_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Template-Generierung"),
        )


@router.post(
    "/{template_id}/test",
    response_model=TemplateTestResponse,
    summary="Template gegen Dokument testen",
    description="Testet ein Template gegen ein Dokument und liefert A/B-Vergleich.",
)
async def test_template(
    template_id: uuid.UUID,
    data: TemplateTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateTestResponse:
    """Testet ein Template gegen ein Dokument."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung",
        )

    service = SupplierTemplateService(db)

    # Template laden
    template = await service.get_template(
        template_id=template_id,
        company_id=company_id,
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden",
        )

    # OCR-Ergebnis laden
    from sqlalchemy import select
    from app.db.models import OCRResult

    ocr_stmt = select(OCRResult).where(OCRResult.document_id == data.document_id)
    ocr_res = await db.execute(ocr_stmt)
    ocr_result_row = ocr_res.scalar_one_or_none()

    if not ocr_result_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein OCR-Ergebnis fuer dieses Dokument gefunden",
        )

    # OCR-Daten aufbereiten
    ocr_data: Dict[str, object] = {}
    if ocr_result_row.extracted_fields and isinstance(ocr_result_row.extracted_fields, dict):
        ocr_data["blocks"] = []
        for field_name, field_data in ocr_result_row.extracted_fields.items():
            if isinstance(field_data, dict):
                block: Dict[str, object] = {
                    "text": field_data.get("value", ""),
                    "confidence": field_data.get("confidence", 0.8),
                    "coordinates": field_data.get("bounding_box", {}),
                }
                ocr_data["blocks"].append(block)
    if ocr_result_row.raw_text:
        ocr_data["full_text"] = ocr_result_row.raw_text

    try:
        result = await service.apply_template_extraction(
            template=template,
            document_id=data.document_id,
            ocr_result=ocr_data,
        )

        extractions_list: List[JSONDict] = [
            {
                "field_name": e.field_name,
                "value": e.value,
                "confidence": round(e.confidence, 4),
                "source": e.source,
                "validation_passed": e.validation_passed,
            }
            for e in result.extractions
        ]

        return TemplateTestResponse(
            template_id=str(result.template_id) if result.template_id else "",
            template_name=result.template_name or "",
            document_id=str(data.document_id),
            used_template=result.used_template,
            match_confidence=round(result.match_confidence, 4),
            overall_confidence=round(result.overall_confidence, 4),
            fields_extracted=result.fields_extracted,
            fields_failed=result.fields_failed,
            processing_time_ms=result.processing_time_ms,
            extractions=extractions_list,
        )

    except Exception as e:
        logger.error(
            "template_test_failed",
            template_id=str(template_id),
            document_id=str(data.document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Template-Test"),
        )
