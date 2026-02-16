"""
API Endpoints für Stammdaten-Hygiene.

Erkennung und Korrektur von veralteten Stammdaten.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.db.models import User, EntityType
from app.services.master_data_hygiene_service import (
    MasterDataHygieneService,
    HygieneIssueType,
    HygieneIssueSeverity,
    get_master_data_hygiene_service,
)
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/hygiene", tags=["stammdaten-hygiene"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class HygieneIssueResponse(BaseModel):
    """Response für ein Hygiene-Issue."""

    id: UUID
    entity_id: UUID
    entity_name: str
    entity_type: str

    issue_type: str
    severity: str

    field_name: str
    current_value: Optional[str] = None
    suggested_value: Optional[str] = None

    source: str
    source_document_id: Optional[UUID] = None

    confidence: float
    auto_correctable: bool

    details: dict = Field(default_factory=dict)
    created_at: datetime


class HygieneReportResponse(BaseModel):
    """Response für einen Hygiene-Report."""

    total_entities_checked: int
    issues_found: int
    auto_correctable_count: int

    by_severity: dict
    by_type: dict

    issues: List[HygieneIssueResponse]

    scan_started_at: datetime
    scan_completed_at: Optional[datetime] = None


class ApplyCorrectionRequest(BaseModel):
    """Request für eine Korrektur."""

    entity_id: UUID
    field_name: str
    new_value: str


class ApplyCorrectionResponse(BaseModel):
    """Response für eine Korrektur."""

    success: bool
    message: str
    entity_id: Optional[str] = None
    field_name: Optional[str] = None


class DeactivateEntityRequest(BaseModel):
    """Request zum Deaktivieren einer Entity."""

    entity_id: UUID
    reason: str = Field(..., min_length=5, max_length=500)


class LexwareCompareRequest(BaseModel):
    """Request für Lexware-Delta-Vergleich."""

    company: str = Field(..., pattern="^(folie|messer)$")
    entity_type: str = Field(default="customer", pattern="^(customer|supplier)$")
    records: List[dict]


class LexwareDeltaResponse(BaseModel):
    """Response für Lexware-Delta."""

    issues_found: int
    issues: List[HygieneIssueResponse]


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/scan", response_model=HygieneReportResponse)
async def run_hygiene_scan(
    entity_types: Optional[str] = Query(
        None,
        description="Komma-separierte Entity-Typen (customer,supplier)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Führt einen vollständigen Hygiene-Scan durch.

    Prüft:
    - Inaktive Kunden/Lieferanten
    - Fehlende Pflichtdaten
    - Potentielle Duplikate
    """
    # Admin-Check
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Hygiene-Scans durchführen"
        )

    service = get_master_data_hygiene_service(db)

    # Entity-Typen parsen
    types_filter = None
    if entity_types:
        try:
            types_filter = [
                EntityType(t.strip())
                for t in entity_types.split(",")
                if t.strip()
            ]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Entity-Typ: {e}"
            )

    report = await service.run_full_scan(entity_types=types_filter)

    return HygieneReportResponse(
        total_entities_checked=report.total_entities_checked,
        issues_found=report.issues_found,
        auto_correctable_count=report.auto_correctable_count,
        by_severity=report.by_severity,
        by_type=report.by_type,
        issues=[
            HygieneIssueResponse(
                id=issue.id,
                entity_id=issue.entity_id,
                entity_name=issue.entity_name,
                entity_type=issue.entity_type,
                issue_type=issue.issue_type.value,
                severity=issue.severity.value,
                field_name=issue.field_name,
                current_value=issue.current_value,
                suggested_value=issue.suggested_value,
                source=issue.source,
                source_document_id=issue.source_document_id,
                confidence=issue.confidence,
                auto_correctable=issue.auto_correctable,
                details=issue.details,
                created_at=issue.created_at,
            )
            for issue in report.issues
        ],
        scan_started_at=report.scan_started_at,
        scan_completed_at=report.scan_completed_at,
    )


@router.post("/lexware-compare", response_model=LexwareDeltaResponse)
async def compare_lexware_data(
    request: LexwareCompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Vergleicht Lexware-Import mit bestehenden Daten.

    Erkennt Änderungen in:
    - Adressen
    - Bankdaten (IBAN, BIC)
    - Kontaktdaten
    """
    # Admin-Check
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Lexware-Vergleiche durchführen"
        )

    service = get_master_data_hygiene_service(db)

    entity_type = (
        EntityType.CUSTOMER if request.entity_type == "customer"
        else EntityType.SUPPLIER
    )

    issues = await service.compare_lexware_import(
        import_data=request.records,
        company=request.company,
        entity_type=entity_type,
    )

    return LexwareDeltaResponse(
        issues_found=len(issues),
        issues=[
            HygieneIssueResponse(
                id=issue.id,
                entity_id=issue.entity_id,
                entity_name=issue.entity_name,
                entity_type=issue.entity_type,
                issue_type=issue.issue_type.value,
                severity=issue.severity.value,
                field_name=issue.field_name,
                current_value=issue.current_value,
                suggested_value=issue.suggested_value,
                source=issue.source,
                source_document_id=issue.source_document_id,
                confidence=issue.confidence,
                auto_correctable=issue.auto_correctable,
                details=issue.details,
                created_at=issue.created_at,
            )
            for issue in issues
        ],
    )


@router.post("/extract-from-document")
async def extract_updates_from_document(
    document_id: UUID,
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extrahiert mögliche Stammdaten-Updates aus einem Dokument.

    Prüft OCR-Text auf:
    - Neue IBANs
    - Geänderte Adressen
    - Neue E-Mail-Adressen
    """
    from app.db.models import Document

    # Dokument laden
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    # OCR-Text holen
    ocr_text = document.ocr_full_text or ""

    if not ocr_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dokument hat keinen OCR-Text"
        )

    service = get_master_data_hygiene_service(db)

    issues = await service.extract_updates_from_document(
        document_id=document_id,
        entity_id=entity_id,
        ocr_text=ocr_text,
    )

    return {
        "issues_found": len(issues),
        "issues": [issue.to_dict() for issue in issues],
    }


@router.post("/apply-correction", response_model=ApplyCorrectionResponse)
async def apply_correction(
    issue_id: UUID,
    request: ApplyCorrectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Wendet eine Korrektur an.

    Benötigt Admin-Berechtigung für kritische Felder.
    """
    # Kritische Felder nur für Admins
    critical_fields = ["iban", "vat_id"]
    if request.field_name in critical_fields and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Feld '{request.field_name}' kann nur von Administratoren geändert werden"
        )

    service = get_master_data_hygiene_service(db)

    success = await service.apply_correction(
        issue_id=issue_id,
        entity_id=request.entity_id,
        field_name=request.field_name,
        new_value=request.new_value,
        approved_by=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Korrektur konnte nicht angewendet werden"
        )

    return ApplyCorrectionResponse(
        success=True,
        message="Korrektur erfolgreich angewendet",
        entity_id=str(request.entity_id),
        field_name=request.field_name,
    )


@router.post("/deactivate-entity", response_model=ApplyCorrectionResponse)
async def deactivate_entity(
    request: DeactivateEntityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deaktiviert eine Entity.

    Markiert die Entity als inaktiv statt sie zu löschen.
    """
    # Admin-Check
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Entities deaktivieren"
        )

    service = get_master_data_hygiene_service(db)

    success = await service.mark_entity_inactive(
        entity_id=request.entity_id,
        reason=request.reason,
        deactivated_by=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Entity konnte nicht deaktiviert werden"
        )

    return ApplyCorrectionResponse(
        success=True,
        message="Entity erfolgreich deaktiviert",
        entity_id=str(request.entity_id),
    )


@router.get("/issue-types")
async def get_issue_types(
    current_user: User = Depends(get_current_user),
):
    """Gibt alle verfügbaren Issue-Typen zurück."""
    return {
        "issue_types": [
            {
                "value": issue_type.value,
                "label": {
                    HygieneIssueType.ADDRESS_CHANGED: "Adresse geändert",
                    HygieneIssueType.ADDRESS_MISSING: "Adresse fehlt",
                    HygieneIssueType.ADDRESS_INCOMPLETE: "Adresse unvollständig",
                    HygieneIssueType.IBAN_CHANGED: "IBAN geändert",
                    HygieneIssueType.IBAN_MISSING: "IBAN fehlt",
                    HygieneIssueType.IBAN_INVALID: "IBAN ungültig",
                    HygieneIssueType.EMAIL_CHANGED: "E-Mail geändert",
                    HygieneIssueType.EMAIL_MISSING: "E-Mail fehlt",
                    HygieneIssueType.PHONE_CHANGED: "Telefon geändert",
                    HygieneIssueType.VAT_ID_CHANGED: "USt-IdNr geändert",
                    HygieneIssueType.VAT_ID_MISSING: "USt-IdNr fehlt",
                    HygieneIssueType.INACTIVE_CUSTOMER: "Inaktiver Kunde",
                    HygieneIssueType.INACTIVE_SUPPLIER: "Inaktiver Lieferant",
                    HygieneIssueType.POTENTIAL_DUPLICATE: "Mögliches Duplikat",
                    HygieneIssueType.LEXWARE_DELTA: "Lexware-Änderung",
                }.get(issue_type, issue_type.value),
            }
            for issue_type in HygieneIssueType
        ]
    }


@router.get("/severity-levels")
async def get_severity_levels(
    current_user: User = Depends(get_current_user),
):
    """Gibt alle verfügbaren Schweregrade zurück."""
    return {
        "severity_levels": [
            {
                "value": severity.value,
                "label": {
                    HygieneIssueSeverity.INFO: "Information",
                    HygieneIssueSeverity.LOW: "Niedrig",
                    HygieneIssueSeverity.MEDIUM: "Mittel",
                    HygieneIssueSeverity.HIGH: "Hoch",
                    HygieneIssueSeverity.CRITICAL: "Kritisch",
                }.get(severity, severity.value),
                "color": {
                    HygieneIssueSeverity.INFO: "gray",
                    HygieneIssueSeverity.LOW: "blue",
                    HygieneIssueSeverity.MEDIUM: "yellow",
                    HygieneIssueSeverity.HIGH: "orange",
                    HygieneIssueSeverity.CRITICAL: "red",
                }.get(severity, "gray"),
            }
            for severity in HygieneIssueSeverity
        ]
    }


# Import für select
from sqlalchemy import select
