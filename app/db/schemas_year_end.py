# -*- coding: utf-8 -*-
"""
Pydantic Schemas für Jahresabschluss-Assistent.

Request- und Response-Modelle für die Jahresabschluss-API.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class YearEndStatusEnum(str, Enum):
    """Status eines Jahresabschluss-Durchlaufs."""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    EXPORTED = "exported"


class CheckItemStatusEnum(str, Enum):
    """Status eines Prüfpunkts."""
    PENDING = "pending"
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class GapCategoryEnum(str, Enum):
    """Kategorie einer Lücke."""
    MISSING_RECEIPT = "missing_receipt"
    UNMATCHED_TRANSACTION = "unmatched_transaction"
    MISSING_INVOICE = "missing_invoice"
    INCOMPLETE_DATA = "incomplete_data"
    AMOUNT_DISCREPANCY = "amount_discrepancy"


# =============================================================================
# Request Schemas
# =============================================================================


class YearEndSessionCreate(BaseModel):
    """Anfrage zum Erstellen einer Jahresabschluss-Session."""
    fiscal_year: int = Field(
        ...,
        ge=2000,
        le=2099,
        description="Geschäftsjahr (z.B. 2025)",
    )


class ResolveGapRequest(BaseModel):
    """Anfrage zum Beheben einer Lücke."""
    notes: str = Field(
        ...,
        min_length=1,
        description="Beschreibung der Loesung",
    )


class UpdateCheckItemRequest(BaseModel):
    """Anfrage zum Aktualisieren eines Prüfpunkts."""
    status: CheckItemStatusEnum
    notes: Optional[str] = Field(
        None,
        description="Optionale Anmerkungen",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class YearEndCheckItemResponse(BaseModel):
    """Antwort mit einem einzelnen Prüfpunkt."""
    id: UUID
    category: str
    check_name: str
    status: CheckItemStatusEnum
    details_json: Optional[Dict[str, object]] = None
    checked_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class YearEndGapResponse(BaseModel):
    """Antwort mit einer einzelnen Lücke."""
    id: UUID
    category: GapCategoryEnum
    month: Optional[int] = None
    description: str
    amount: Optional[Decimal] = None
    document_id: Optional[UUID] = None
    transaction_reference: Optional[str] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class YearEndSessionResponse(BaseModel):
    """Antwort mit einer Jahresabschluss-Session (Übersicht)."""
    id: UUID
    fiscal_year: int
    status: YearEndStatusEnum
    progress_percent: int = 0
    total_checks: int = 0
    passed_checks: int = 0
    warning_checks: int = 0
    failed_checks: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    report_generated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class YearEndSessionDetailResponse(BaseModel):
    """Antwort mit einer Jahresabschluss-Session inkl. Prüfpunkten und Lücken."""
    id: UUID
    fiscal_year: int
    status: YearEndStatusEnum
    progress_percent: int = 0
    total_checks: int = 0
    passed_checks: int = 0
    warning_checks: int = 0
    failed_checks: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    report_generated_at: Optional[datetime] = None
    notes: Optional[str] = None
    check_items: List[YearEndCheckItemResponse] = []
    gaps: List[YearEndGapResponse] = []
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class YearEndSessionListResponse(BaseModel):
    """Paginierte Liste von Jahresabschluss-Sessions."""
    items: List[YearEndSessionResponse]
    total: int
    page: int
    per_page: int


class YearEndReportResponse(BaseModel):
    """Antwort mit generiertem Steuerberater-Bericht."""
    session_id: UUID
    fiscal_year: int
    report_data: Dict[str, object]
    generated_at: datetime
