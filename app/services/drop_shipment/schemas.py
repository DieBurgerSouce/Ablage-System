"""
Streckengeschäft API Schemas (Request/Response Models)
"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .models import (
    DropShipmentClassification,
    DropShipmentClassificationType,
    EuTransactionType,
    TaxTreatment,
    ProofDocumentType,
    ProofDocument,
)


# =============================================================================
# REQUEST MODELS
# =============================================================================

class ClassifyDocumentRequest(BaseModel):
    """Request für automatische Klassifikation"""
    document_id: UUID
    force_reclassify: bool = False


class ConfirmClassificationRequest(BaseModel):
    """Request für manuelle Bestätigung"""
    classification_id: UUID
    confirmed_type: Optional[DropShipmentClassificationType] = None
    notes: Optional[str] = None


class OverrideClassificationRequest(BaseModel):
    """Request für manuelle Korrektur"""
    classification_id: UUID
    new_classification_type: DropShipmentClassificationType
    eu_transaction_type: Optional[EuTransactionType] = None
    tax_treatment: Optional[TaxTreatment] = None
    moving_delivery_assigned_to: Optional[str] = None
    datev_account: Optional[str] = None
    datev_tax_code: Optional[str] = None
    reason: str = Field(..., min_length=10)


class LinkProofDocumentRequest(BaseModel):
    """Request für Belegnachweis-Verknüpfung"""
    classification_id: UUID
    proof_type: ProofDocumentType
    document_id: UUID


class MarkZmReportedRequest(BaseModel):
    """Request für ZM-Meldung markieren"""
    report_date: date


class DatevExportRequest(BaseModel):
    """Request für DATEV-Export"""
    classification_ids: list[UUID]
    export_format: str = Field("extf", pattern="^(extf|csv)$")
    kontenrahmen: str = Field("03", pattern="^(03|04)$")
    include_zm_data: bool = True


class BulkActionRequest(BaseModel):
    """Request für Bulk-Aktionen"""
    action: str = Field(..., pattern="^(confirm|export_datev|mark_zm_reported)$")
    classification_ids: list[UUID]


class DropShipmentListFilter(BaseModel):
    """Filter für Listen-Abfrage"""
    classification_type: Optional[list[DropShipmentClassificationType]] = None
    confidence_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_confirmed: Optional[bool] = None
    zm_relevant: Optional[bool] = None
    zm_reported: Optional[bool] = None
    eu_transaction_type: Optional[list[EuTransactionType]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search_query: Optional[str] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: str = "created_at"
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class ClassifyDocumentResponse(BaseModel):
    """Response für Klassifikation"""
    classification: DropShipmentClassification
    is_new: bool
    processing_time_ms: int


class DropShipmentListResponse(BaseModel):
    """Paginierte Listen-Response"""
    items: list[DropShipmentClassification]
    total: int
    page: int
    page_size: int
    total_pages: int


class ZmPendingResponse(BaseModel):
    """Response für ZM-relevante offene Meldungen"""
    items: list[DropShipmentClassification]
    current_period: str  # z.B. "2025-01"
    deadline: date  # 25. des Folgemonats
    days_remaining: int


class DatevExportResponse(BaseModel):
    """Response für DATEV-Export"""
    export_id: UUID
    file_name: str
    download_url: str
    record_count: int
    warnings: Optional[list[str]] = None


class BulkActionResponse(BaseModel):
    """Response für Bulk-Aktionen"""
    successful: list[UUID]
    failed: list[dict]  # [{id: UUID, error: str}]


class DocumentFlowValidationResponse(BaseModel):
    """Response für Dokumentenfluss-Validierung"""
    is_valid: bool
    issues: list[dict]  # [{severity, message, document_type}]


class RelatedDocumentsResponse(BaseModel):
    """Response für verknüpfte Dokumente"""
    purchase_orders: list[dict]
    delivery_notes: list[dict]
    cmr_documents: list[dict]
    invoices: list[dict]


class DropShipmentDashboardStats(BaseModel):
    """Dashboard-Statistiken"""
    total: int
    by_type: dict[str, int]
    pending_confirmation: int
    zm_pending: int
    proof_incomplete: int
    avg_confidence: float
    this_month: int
    last_month: int
