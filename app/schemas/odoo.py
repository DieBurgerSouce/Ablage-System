"""
Pydantic Schemas für Odoo Integration.

Phase 6: Odoo Integration Deepening
- Webhook Payloads
- Extended Data Types (Projects, Timesheet, Inventory)
- AI Feedback Schemas

Feinpoliert und durchdacht - Type-Safe Odoo Integration.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


# =============================================================================
# Enums
# =============================================================================


class OdooWebhookEventType(str, Enum):
    """Typen von Odoo Webhook Events."""
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    INVOICE = "invoice"
    PAYMENT = "payment"
    PRODUCT = "product"
    PROJECT = "project"
    TIMESHEET = "timesheet"
    STOCK_MOVE = "stock_move"


class OdooWebhookAction(str, Enum):
    """Aktionen bei Odoo Webhooks."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class OdooFeedbackType(str, Enum):
    """Typen von AI-Feedback für Odoo."""
    RISK_SCORE = "risk_score"
    PAYMENT_SUGGESTION = "payment_suggestion"
    SKONTO_PREDICTION = "skonto_prediction"
    CREDIT_LIMIT_RECOMMENDATION = "credit_limit_recommendation"


class OdooWebhookStatus(str, Enum):
    """Status eines Webhook Events."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    IGNORED = "ignored"


class OdooFeedbackStatus(str, Enum):
    """Status eines AI-Feedback Push."""
    PENDING = "pending"
    PUSHING = "pushing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# Webhook Validation Patterns
# =============================================================================

# Regex für sichere Event-IDs (alphanumerisch + Bindestriche)
EVENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,253}[a-zA-Z0-9]$|^[a-zA-Z0-9]$")


# =============================================================================
# Base Webhook Schemas
# =============================================================================


class OdooWebhookHeader(BaseModel):
    """Header-Informationen eines Odoo Webhooks."""
    signature: str = Field(..., min_length=64, max_length=128, description="HMAC-SHA256 Signatur")
    timestamp: str = Field(..., description="Timestamp der Signatur")
    webhook_id: str = Field(..., description="Odoo Webhook ID")


class OdooWebhookPayload(BaseModel):
    """Basis-Payload eines Odoo Webhooks."""
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1, max_length=255, description="Eindeutige Event-ID für Idempotenz")
    event_type: OdooWebhookEventType = Field(..., description="Typ des Events")
    action: OdooWebhookAction = Field(..., description="Aktion (create/update/delete)")
    timestamp: datetime = Field(..., description="Zeitpunkt des Events in Odoo")
    record_id: int = Field(..., gt=0, description="ID des betroffenen Records in Odoo")
    data: Dict[str, object] = Field(default_factory=dict, description="Event-Daten")

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        """Validiert Event-ID gegen Injection."""
        if not EVENT_ID_PATTERN.match(v):
            raise ValueError("Ungültiges Event-ID Format")
        return v


# =============================================================================
# Entity-Specific Webhook Schemas
# =============================================================================


class OdooCustomerWebhook(BaseModel):
    """Webhook-Payload für Kunden-Events."""
    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., gt=0)
    name: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    mobile: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=500)
    street2: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=255)
    zip: Optional[str] = Field(None, max_length=20)
    country_id: Optional[List[Union[int, str]]] = None  # [id, name] tuple
    vat: Optional[str] = Field(None, max_length=50)
    company_type: Optional[str] = Field(None, max_length=50)
    customer_rank: Optional[int] = None
    write_date: Optional[str] = None


class OdooSupplierWebhook(BaseModel):
    """Webhook-Payload für Lieferanten-Events."""
    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., gt=0)
    name: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=255)
    zip: Optional[str] = Field(None, max_length=20)
    country_id: Optional[List[Union[int, str]]] = None
    vat: Optional[str] = Field(None, max_length=50)
    supplier_rank: Optional[int] = None
    write_date: Optional[str] = None


class OdooInvoiceWebhook(BaseModel):
    """Webhook-Payload für Rechnungs-Events."""
    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., gt=0)
    name: Optional[str] = Field(None, max_length=100)
    ref: Optional[str] = Field(None, max_length=255)
    move_type: Optional[str] = Field(None, max_length=50)
    state: Optional[str] = Field(None, max_length=50)
    partner_id: Optional[List[Union[int, str]]] = None  # [id, name] tuple
    invoice_date: Optional[str] = None
    invoice_date_due: Optional[str] = None
    amount_total: Optional[float] = None
    amount_residual: Optional[float] = None
    currency_id: Optional[List[Union[int, str]]] = None
    payment_state: Optional[str] = Field(None, max_length=50)
    write_date: Optional[str] = None


class OdooPaymentWebhook(BaseModel):
    """Webhook-Payload für Zahlungs-Events."""
    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., gt=0)
    name: Optional[str] = Field(None, max_length=100)
    payment_type: Optional[str] = Field(None, max_length=50)
    partner_id: Optional[List[Union[int, str]]] = None
    amount: Optional[float] = None
    currency_id: Optional[List[Union[int, str]]] = None
    date: Optional[str] = None
    state: Optional[str] = Field(None, max_length=50)
    move_id: Optional[List[Union[int, str]]] = None  # Related invoice
    write_date: Optional[str] = None


class OdooProductWebhook(BaseModel):
    """Webhook-Payload für Produkt-Events."""
    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., gt=0)
    name: Optional[str] = Field(None, max_length=500)
    default_code: Optional[str] = Field(None, max_length=100)  # SKU
    barcode: Optional[str] = Field(None, max_length=100)
    list_price: Optional[float] = None
    standard_price: Optional[float] = None
    categ_id: Optional[List[Union[int, str]]] = None
    type: Optional[str] = Field(None, max_length=50)
    active: Optional[bool] = None
    write_date: Optional[str] = None


# =============================================================================
# Extended Data Type Schemas (Projects, Timesheet, Inventory)
# =============================================================================


class OdooProject(BaseModel):
    """Odoo Projekt-Daten."""
    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., gt=0)
    name: str = Field(..., max_length=500)
    partner_id: Optional[List[Union[int, str]]] = None  # Customer
    user_id: Optional[List[Union[int, str]]] = None  # Project Manager
    date_start: Optional[str] = None
    date: Optional[str] = None  # End date
    active: bool = True
    stage_id: Optional[List[Union[int, str]]] = None
    task_count: Optional[int] = None
    description: Optional[str] = None
    write_date: Optional[str] = None


class OdooTimesheetEntry(BaseModel):
    """Odoo Zeiterfassungs-Eintrag."""
    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., gt=0)
    date: str = Field(..., description="Datum des Eintrags")
    employee_id: Optional[List[Union[int, str]]] = None
    project_id: Optional[List[Union[int, str]]] = None
    task_id: Optional[List[Union[int, str]]] = None
    name: Optional[str] = Field(None, max_length=500, description="Beschreibung")
    unit_amount: float = Field(..., ge=0, description="Stunden")
    account_id: Optional[List[Union[int, str]]] = None  # Analytic Account
    write_date: Optional[str] = None


class OdooStockMove(BaseModel):
    """Odoo Lagerbewegung."""
    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., gt=0)
    name: str = Field(..., max_length=500)
    product_id: List[Union[int, str]]  # [id, name]
    product_uom_qty: float = Field(..., ge=0)
    quantity_done: Optional[float] = Field(None, ge=0)
    location_id: Optional[List[Union[int, str]]] = None  # Source
    location_dest_id: Optional[List[Union[int, str]]] = None  # Destination
    state: Optional[str] = Field(None, max_length=50)
    date: Optional[str] = None
    origin: Optional[str] = Field(None, max_length=255)
    picking_id: Optional[List[Union[int, str]]] = None
    write_date: Optional[str] = None


class OdooProductCatalog(BaseModel):
    """Odoo Produkt-Katalog Eintrag (erweitert)."""
    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., gt=0)
    name: str = Field(..., max_length=500)
    default_code: Optional[str] = Field(None, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)
    list_price: Optional[float] = None
    standard_price: Optional[float] = None
    qty_available: Optional[float] = None
    virtual_available: Optional[float] = None
    categ_id: Optional[List[Union[int, str]]] = None
    uom_id: Optional[List[Union[int, str]]] = None
    type: Optional[str] = Field(None, max_length=50)
    active: bool = True
    write_date: Optional[str] = None


# =============================================================================
# AI Feedback Schemas
# =============================================================================


class RiskScoreFeedback(BaseModel):
    """Risk Score Feedback für Odoo."""
    score: float = Field(..., ge=0, le=100, description="Risiko-Score 0-100")
    payment_behavior_score: float = Field(..., ge=0, le=100, description="Zahlungsverhalten-Score")
    risk_level: str = Field(..., pattern="^(low|medium|high|critical)$")
    factors: Dict[str, object] = Field(default_factory=dict, description="Risikofaktoren (ohne PII)")
    calculated_at: datetime = Field(..., description="Berechnungszeitpunkt")


class PaymentSuggestionFeedback(BaseModel):
    """Zahlungsvorschlag Feedback für Odoo."""
    suggested_payment_term: str = Field(..., max_length=100, description="Empfohlene Zahlungsbedingung")
    suggested_credit_limit: Optional[float] = Field(None, ge=0, description="Empfohlenes Kreditlimit")
    reason: str = Field(..., max_length=500, description="Begründung")
    confidence: float = Field(..., ge=0, le=1, description="Konfidenz der Empfehlung")
    based_on_invoices: int = Field(..., ge=0, description="Anzahl analysierter Rechnungen")


class SkontoPredictionFeedback(BaseModel):
    """Skonto-Vorhersage Feedback für Odoo."""
    skonto_usage_probability: float = Field(..., ge=0, le=1, description="Wahrscheinlichkeit der Skonto-Nutzung")
    average_payment_days: float = Field(..., ge=0, description="Durchschnittliche Zahlungstage")
    recommended_skonto_percent: Optional[float] = Field(None, ge=0, le=10, description="Empfohlener Skonto-Prozentsatz")
    recommendation: str = Field(..., max_length=500, description="Empfehlung")


class OdooFeedbackPayload(BaseModel):
    """Payload für AI-Feedback Push zu Odoo."""
    model_config = ConfigDict(extra="forbid")

    entity_id: UUID = Field(..., description="Lokale Entity-ID")
    odoo_partner_id: int = Field(..., gt=0, description="Odoo Partner-ID")
    feedback_type: OdooFeedbackType = Field(..., description="Typ des Feedbacks")
    feedback_data: Union[RiskScoreFeedback, PaymentSuggestionFeedback, SkontoPredictionFeedback] = Field(
        ..., description="Feedback-Daten"
    )
    target_field: Optional[str] = Field(None, max_length=100, description="Zielfeld in Odoo")


# =============================================================================
# Vendor-Bill-Push Schemas (Phase 2 Neuausrichtung: Ablage -> Odoo)
# =============================================================================


class OdooVendorBillDraft(BaseModel):
    """Entwurfs-Lieferantenrechnung fuer den Push nach Odoo.

    Wird vom Eingangskanal (Scan/E-Mail -> OCR -> GoBD-Archiv) befuellt
    und via OdooConnector.create_vendor_bill_draft als account.move
    (move_type=in_invoice, implizit draft) angelegt. Der Betrag geht als
    eine Brutto-Sammelzeile; Steuer-/Kontenzuordnung erfolgt in Odoo.
    """
    model_config = ConfigDict(extra="forbid")

    partner_id: int = Field(..., gt=0, description="Odoo Partner-ID des Lieferanten")
    invoice_date: date = Field(..., description="Rechnungsdatum")
    ref: str = Field(..., min_length=1, max_length=255, description="Lieferanten-Rechnungsnummer")
    amount_total_brutto: Decimal = Field(..., gt=0, description="Bruttobetrag der Rechnung")
    currency: str = Field(default="EUR", pattern="^[A-Z]{3}$", description="ISO-4217-Waehrungscode")
    line_name: str = Field(..., min_length=1, max_length=500, description="Text der Brutto-Sammelzeile")
    narration: Optional[str] = Field(None, max_length=2000, description="Interne Notiz (Odoo narration)")


# =============================================================================
# Response Schemas
# =============================================================================


class OdooWebhookResponse(BaseModel):
    """Response nach Webhook-Verarbeitung."""
    success: bool
    event_id: str
    message: str = "Webhook empfangen"
    task_id: Optional[str] = None


class OdooWebhookEventResponse(BaseModel):
    """Response für Webhook Event Status."""
    id: str
    event_id: str
    event_type: str
    action: str
    status: str
    received_at: datetime
    processed_at: Optional[datetime]
    error_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class OdooFeedbackResponse(BaseModel):
    """Response für AI-Feedback Push."""
    id: str
    entity_id: str
    feedback_type: str
    status: str
    pushed_at: Optional[datetime]
    error_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class OdooSyncStatusResponse(BaseModel):
    """Response für Sync-Status eines Datentyps."""
    data_type: str
    last_sync_at: Optional[datetime]
    last_successful_sync_at: Optional[datetime]
    total_records_synced: int
    records_synced_today: int
    consecutive_failures: int
    is_paused: bool
    last_error: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Batch Request Schemas
# =============================================================================


class OdooBatchFeedbackRequest(BaseModel):
    """Batch-Request für mehrere AI-Feedbacks."""
    feedbacks: List[OdooFeedbackPayload] = Field(..., min_length=1, max_length=100)
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class OdooExtendedSyncRequest(BaseModel):
    """Request für erweiterte Datentyp-Synchronisation."""
    data_types: List[str] = Field(
        ...,
        min_length=1,
        description="Zu synchronisierende Datentypen"
    )
    since: Optional[datetime] = Field(None, description="Nur Änderungen seit")
    batch_size: int = Field(default=100, ge=10, le=500)

    @field_validator("data_types")
    @classmethod
    def validate_data_types(cls, v: List[str]) -> List[str]:
        """Validiert erlaubte Datentypen."""
        allowed = {"projects", "timesheet", "inventory", "products"}
        for dt in v:
            if dt not in allowed:
                raise ValueError(f"Unbekannter Datentyp: {dt}. Erlaubt: {allowed}")
        return v
