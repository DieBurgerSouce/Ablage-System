# -*- coding: utf-8 -*-
"""
Multi-Dimensional Classification API Endpoints.

Vision 2.0 Feature: Intelligente Dokumentenklassifikation
Endpoints fuer:
- Multi-Label Klassifikation (Typ, Dringlichkeit, Abteilung, Vertraulichkeit)
- Einzelne Dimensionen (Urgency, Department, Confidentiality)
- Batch-Klassifikation
- Statistiken

Feinpoliert und durchdacht.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.db.models import User, Company

from app.services.classification import (
    get_multi_label_classifier,
    UrgencyLevel,
    Department,
    ConfidentialityLevel,
)
from app.services.classification.urgency_classifier import get_urgency_classifier
from app.services.classification.department_router import get_department_router
from app.services.classification.confidentiality_classifier import get_confidentiality_classifier

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/classification", tags=["Classification"])


# =============================================================================
# Request/Response Schemas
# =============================================================================

class ClassificationRequest(BaseModel):
    """Request fuer Dokumenten-Klassifikation."""
    text: str = Field(..., min_length=1, max_length=100000, description="OCR-Text des Dokuments")
    document_date: Optional[datetime] = Field(None, description="Dokumentdatum fuer Fristberechnung")
    amount: Optional[Decimal] = Field(None, ge=0, description="Betrag fuer CFO-Approval Pruefung")
    is_incoming: bool = Field(True, description="True fuer eingehende, False fuer ausgehende Dokumente")


class BatchClassificationRequest(BaseModel):
    """Request fuer Batch-Klassifikation."""
    documents: List[ClassificationRequest] = Field(..., min_length=1, max_length=50)


class DocumentTypeResponse(BaseModel):
    """Dokumenttyp-Klassifikation."""
    type: str
    confidence: float
    alternatives: List[str]


class UrgencyResponse(BaseModel):
    """Dringlichkeits-Klassifikation."""
    level: str
    confidence: float
    deadline: Optional[datetime]
    days_until_deadline: Optional[int]
    reason: str


class DepartmentResponse(BaseModel):
    """Abteilungs-Routing."""
    primary: str
    confidence: float
    secondary: List[str]
    requires_cfo_approval: bool
    reason: str


class ConfidentialityResponse(BaseModel):
    """Vertraulichkeits-Klassifikation."""
    level: str
    confidence: float
    detected_pii_types: List[str]
    requires_encryption: bool
    access_restriction: str


class MultiLabelClassificationResponse(BaseModel):
    """Vollstaendige Multi-Label Klassifikation."""
    document_type: DocumentTypeResponse
    urgency: UrgencyResponse
    department: DepartmentResponse
    confidentiality: ConfidentialityResponse
    overall_confidence: float
    summary: str
    matched_indicators: Dict[str, List[str]]
    processing_time_ms: int


class ClassificationStatsResponse(BaseModel):
    """Klassifikations-Statistiken."""
    multi_label: JSONDict
    document_type: JSONDict
    urgency: JSONDict
    department: JSONDict
    confidentiality: JSONDict


class UrgencyLevelsResponse(BaseModel):
    """Verfuegbare Dringlichkeitsstufen."""
    levels: List[Dict[str, str]]


class DepartmentsResponse(BaseModel):
    """Verfuegbare Abteilungen."""
    departments: List[Dict[str, str]]


class ConfidentialityLevelsResponse(BaseModel):
    """Verfuegbare Vertraulichkeitsstufen."""
    levels: List[Dict[str, str]]


# =============================================================================
# Multi-Label Classification Endpoints
# =============================================================================

@router.post("/multi-label", response_model=MultiLabelClassificationResponse)
async def classify_multi_label(
    request: ClassificationRequest,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> MultiLabelClassificationResponse:
    """
    Fuehre vollstaendige Multi-Label Klassifikation durch.

    Klassifiziert ein Dokument nach allen Dimensionen:
    - **Dokumenttyp**: Rechnung, Vertrag, Bestellung, etc.
    - **Dringlichkeit**: Sofort, Normal, Kann warten
    - **Abteilung**: Buchhaltung, Einkauf, Vertrieb, etc.
    - **Vertraulichkeit**: Oeffentlich, Intern, Vertraulich, Streng Vertraulich

    Performance: < 50ms
    """
    classifier = get_multi_label_classifier()

    result = classifier.classify(
        text=request.text,
        document_date=request.document_date,
        amount=request.amount,
        is_incoming=request.is_incoming,
    )

    logger.info(
        "document_classified",
        company_id=str(company.company_id),
        user_id=str(current_user.id),
        document_type=result.document_type.value,
        urgency=result.urgency_level.value,
        department=result.primary_department.value,
        confidentiality=result.confidentiality_level.value,
    )

    return MultiLabelClassificationResponse(
        document_type=DocumentTypeResponse(
            type=result.document_type.value,
            confidence=result.document_type_confidence,
            alternatives=result.document_type_alternatives,
        ),
        urgency=UrgencyResponse(
            level=result.urgency_level.value,
            confidence=result.urgency_confidence,
            deadline=result.deadline,
            days_until_deadline=result.days_until_deadline,
            reason=f"Dringlichkeit: {result.urgency_level.value}",
        ),
        department=DepartmentResponse(
            primary=result.primary_department.value,
            confidence=result.department_confidence,
            secondary=[d.value for d in result.secondary_departments],
            requires_cfo_approval=result.requires_cfo_approval,
            reason=f"Zustaendig: {result.primary_department.value}",
        ),
        confidentiality=ConfidentialityResponse(
            level=result.confidentiality_level.value,
            confidence=result.confidentiality_confidence,
            detected_pii_types=result.detected_pii_types,
            requires_encryption=result.requires_encryption,
            access_restriction=result.access_restriction,
        ),
        overall_confidence=result.overall_confidence,
        summary=result.classification_summary,
        matched_indicators=result.matched_indicators,
        processing_time_ms=result.processing_time_ms,
    )


@router.post("/multi-label/batch", response_model=List[MultiLabelClassificationResponse])
async def classify_batch(
    request: BatchClassificationRequest,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[MultiLabelClassificationResponse]:
    """
    Klassifiziere mehrere Dokumente gleichzeitig.

    Maximal 50 Dokumente pro Anfrage.
    """
    classifier = get_multi_label_classifier()

    documents = [
        {
            "text": doc.text,
            "date": doc.document_date,
            "amount": doc.amount,
            "is_incoming": doc.is_incoming,
        }
        for doc in request.documents
    ]

    results = classifier.classify_batch(documents)

    logger.info(
        "batch_classification_complete",
        company_id=str(company.company_id),
        document_count=len(results),
    )

    return [
        MultiLabelClassificationResponse(
            document_type=DocumentTypeResponse(
                type=r.document_type.value,
                confidence=r.document_type_confidence,
                alternatives=r.document_type_alternatives,
            ),
            urgency=UrgencyResponse(
                level=r.urgency_level.value,
                confidence=r.urgency_confidence,
                deadline=r.deadline,
                days_until_deadline=r.days_until_deadline,
                reason=f"Dringlichkeit: {r.urgency_level.value}",
            ),
            department=DepartmentResponse(
                primary=r.primary_department.value,
                confidence=r.department_confidence,
                secondary=[d.value for d in r.secondary_departments],
                requires_cfo_approval=r.requires_cfo_approval,
                reason=f"Zustaendig: {r.primary_department.value}",
            ),
            confidentiality=ConfidentialityResponse(
                level=r.confidentiality_level.value,
                confidence=r.confidentiality_confidence,
                detected_pii_types=r.detected_pii_types,
                requires_encryption=r.requires_encryption,
                access_restriction=r.access_restriction,
            ),
            overall_confidence=r.overall_confidence,
            summary=r.classification_summary,
            matched_indicators=r.matched_indicators,
            processing_time_ms=r.processing_time_ms,
        )
        for r in results
    ]


# =============================================================================
# Single Dimension Endpoints
# =============================================================================

@router.post("/urgency", response_model=UrgencyResponse)
async def classify_urgency(
    request: ClassificationRequest,
    current_user: User = Depends(get_current_active_user),
) -> UrgencyResponse:
    """
    Klassifiziere nur die Dringlichkeit.

    Analysiert:
    - Erkannte Fristen und Deadlines
    - Mahnungen und Eskalationen
    - Keywords fuer Dringlichkeit
    """
    classifier = get_urgency_classifier()

    result = classifier.classify(
        text=request.text,
        document_date=request.document_date,
    )

    return UrgencyResponse(
        level=result.urgency_level.value,
        confidence=result.confidence,
        deadline=result.deadline,
        days_until_deadline=result.days_until_deadline,
        reason=result.reason,
    )


@router.post("/department", response_model=DepartmentResponse)
async def route_to_department(
    request: ClassificationRequest,
    current_user: User = Depends(get_current_active_user),
) -> DepartmentResponse:
    """
    Route Dokument zur zustaendigen Abteilung.

    Beruecksichtigt:
    - Dokumenttyp
    - Inhalt und Keywords
    - Betragsschwellen
    """
    router = get_department_router()

    result = router.route(
        text=request.text,
        amount=request.amount,
        is_incoming=request.is_incoming,
    )

    return DepartmentResponse(
        primary=result.primary_department.value,
        confidence=result.confidence,
        secondary=[d.value for d in result.secondary_departments],
        requires_cfo_approval=result.requires_cfo_approval,
        reason=result.reason,
    )


@router.post("/confidentiality", response_model=ConfidentialityResponse)
async def classify_confidentiality(
    request: ClassificationRequest,
    current_user: User = Depends(get_current_active_user),
) -> ConfidentialityResponse:
    """
    Klassifiziere die Vertraulichkeit.

    Erkennt:
    - Explizite Vertraulichkeits-Marker
    - PII (personenbezogene Daten)
    - Geschaeftsgeheimnisse
    """
    classifier = get_confidentiality_classifier()

    result = classifier.classify(text=request.text)

    return ConfidentialityResponse(
        level=result.level.value,
        confidence=result.confidence,
        detected_pii_types=result.detected_pii_types,
        requires_encryption=result.requires_encryption,
        access_restriction=result.access_restriction,
    )


# =============================================================================
# Reference Data Endpoints
# =============================================================================

@router.get("/urgency-levels", response_model=UrgencyLevelsResponse)
async def get_urgency_levels() -> UrgencyLevelsResponse:
    """
    Liste alle verfuegbaren Dringlichkeitsstufen.
    """
    level_descriptions = {
        UrgencyLevel.IMMEDIATE: "Sofort - Frist < 3 Tage oder kritisch",
        UrgencyLevel.NORMAL: "Normal - Frist 3-14 Tage",
        UrgencyLevel.CAN_WAIT: "Kann warten - Frist > 14 Tage oder keine",
    }

    return UrgencyLevelsResponse(
        levels=[
            {"value": level.value, "label": level.name, "description": level_descriptions[level]}
            for level in UrgencyLevel
        ]
    )


@router.get("/departments", response_model=DepartmentsResponse)
async def get_departments() -> DepartmentsResponse:
    """
    Liste alle verfuegbaren Abteilungen.
    """
    dept_descriptions = {
        Department.BUCHHALTUNG: "Finanzbuchhaltung, Rechnungswesen",
        Department.EINKAUF: "Beschaffung, Lieferanten",
        Department.VERTRIEB: "Verkauf, Kundenbeziehungen",
        Department.HR: "Personal, Mitarbeiter",
        Department.GESCHAEFTSFUEHRUNG: "Management, Strategie",
        Department.IT: "Technologie, Software",
        Department.RECHT: "Vertraege, Compliance",
        Department.ALLGEMEIN: "Allgemein zugeordnet",
    }

    return DepartmentsResponse(
        departments=[
            {"value": dept.value, "label": dept.name, "description": dept_descriptions[dept]}
            for dept in Department
        ]
    )


@router.get("/confidentiality-levels", response_model=ConfidentialityLevelsResponse)
async def get_confidentiality_levels() -> ConfidentialityLevelsResponse:
    """
    Liste alle verfuegbaren Vertraulichkeitsstufen.
    """
    level_descriptions = {
        ConfidentialityLevel.PUBLIC: "Oeffentlich zugaenglich",
        ConfidentialityLevel.INTERNAL: "Nur fuer Mitarbeiter",
        ConfidentialityLevel.CONFIDENTIAL: "Eingeschraenkter Zugriff",
        ConfidentialityLevel.STRICTLY_CONFIDENTIAL: "Nur autorisierte Personen",
    }

    return ConfidentialityLevelsResponse(
        levels=[
            {"value": level.value, "label": level.name, "description": level_descriptions[level]}
            for level in ConfidentialityLevel
        ]
    )


# =============================================================================
# Statistics Endpoints
# =============================================================================

@router.get("/stats", response_model=ClassificationStatsResponse)
async def get_classification_stats(
    current_user: User = Depends(get_current_active_user),
) -> ClassificationStatsResponse:
    """
    Hole Klassifikations-Statistiken.

    Zeigt Verteilung nach:
    - Dokumenttypen
    - Dringlichkeitsstufen
    - Abteilungen
    - Vertraulichkeitsstufen
    """
    classifier = get_multi_label_classifier()
    stats = classifier.get_stats()

    return ClassificationStatsResponse(**stats)


@router.post("/stats/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_classification_stats(
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Setze Klassifikations-Statistiken zurueck (Admin).
    """
    # Admin-Check: Nur Admins oder Manager duerfen Statistiken zuruecksetzen
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren koennen Statistiken zuruecksetzen",
        )

    classifier = get_multi_label_classifier()
    classifier.reset_stats()

    logger.info(
        "classification_stats_reset",
        user_id=str(current_user.id),
        user_role=current_user.role,
    )
