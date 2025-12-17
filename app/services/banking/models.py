"""Pydantic schemas for Banking Integration.

Definiert alle Request/Response-Modelle fuer die Banking-API.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


# =============================================================================
# ENUMS
# =============================================================================

class BankAccountType(str, Enum):
    """Kontotyp."""
    CHECKING = "checking"  # Girokonto
    SAVINGS = "savings"  # Sparkonto
    BUSINESS = "business"  # Geschaeftskonto
    CREDIT = "credit"  # Kreditkarte


class ImportFormat(str, Enum):
    """Unterstuetzte Import-Formate."""
    MT940 = "mt940"  # SWIFT Standard
    CAMT053 = "camt053"  # ISO 20022 XML
    CSV_GENERIC = "csv_generic"  # Generisches CSV
    CSV_SPARKASSE = "csv_sparkasse"
    CSV_VOLKSBANK = "csv_volksbank"
    CSV_DEUTSCHE_BANK = "csv_deutsche_bank"
    CSV_COMMERZBANK = "csv_commerzbank"
    CSV_ING = "csv_ing"
    CSV_N26 = "csv_n26"
    CSV_DKB = "csv_dkb"
    PDF = "pdf"  # PDF-Kontoauszug


class TransactionType(str, Enum):
    """Transaktionstyp."""
    TRANSFER = "transfer"  # Ueberweisung
    DIRECT_DEBIT = "direct_debit"  # Lastschrift
    CARD = "card"  # Kartenzahlung
    CASH = "cash"  # Bargeld
    FEE = "fee"  # Gebuehr
    INTEREST = "interest"  # Zinsen
    OTHER = "other"


class ReconciliationStatus(str, Enum):
    """Abgleich-Status."""
    UNMATCHED = "unmatched"  # Nicht zugeordnet
    MATCHED = "matched"  # Zugeordnet
    PARTIAL = "partial"  # Teilzahlung
    MANUAL = "manual"  # Manuell zugeordnet
    IGNORED = "ignored"  # Ignoriert


class PaymentStatus(str, Enum):
    """Zahlungsauftrag-Status."""
    DRAFT = "draft"  # Entwurf
    PENDING_APPROVAL = "pending_approval"  # Warten auf Freigabe
    APPROVED = "approved"  # Freigegeben
    PENDING_TAN = "pending_tan"  # Warten auf TAN
    SUBMITTED = "submitted"  # An Bank gesendet
    CONFIRMED = "confirmed"  # Bestaetigt
    REJECTED = "rejected"  # Abgelehnt
    FAILED = "failed"  # Fehlgeschlagen
    CANCELLED = "cancelled"  # Storniert


class PaymentType(str, Enum):
    """Zahlungsart."""
    TRANSFER = "transfer"  # Einzelueberweisung
    DIRECT_DEBIT = "direct_debit"  # Lastschrift
    BATCH = "batch"  # Sammelzahlung


class SEPAType(str, Enum):
    """SEPA-Nachrichtentyp."""
    PAIN_001 = "PAIN.001"  # Credit Transfer
    PAIN_008 = "PAIN.008"  # Direct Debit


class DunningLevel(int, Enum):
    """Mahnstufe."""
    NOT_STARTED = 0  # Nicht begonnen
    FIRST_REMINDER = 1  # 1. Mahnung
    SECOND_REMINDER = 2  # 2. Mahnung
    FINAL_REMINDER = 3  # Letzte Mahnung


class DunningStatus(str, Enum):
    """Mahnstatus."""
    PENDING = "pending"  # Ausstehend
    LEVEL_1_SENT = "level_1_sent"  # 1. Mahnung gesendet
    LEVEL_2_SENT = "level_2_sent"  # 2. Mahnung gesendet
    LEVEL_3_SENT = "level_3_sent"  # Letzte Mahnung gesendet
    PAID = "paid"  # Bezahlt
    PARTIALLY_PAID = "partially_paid"  # Teilweise bezahlt
    WRITTEN_OFF = "written_off"  # Abgeschrieben
    LEGAL = "legal"  # Rechtliche Schritte


class CashFlowDirection(str, Enum):
    """Cash-Flow-Richtung."""
    INFLOW = "inflow"  # Einnahme
    OUTFLOW = "outflow"  # Ausgabe


class CashFlowStatus(str, Enum):
    """Cash-Flow-Status."""
    EXPECTED = "expected"  # Erwartet
    CONFIRMED = "confirmed"  # Bestaetigt
    COMPLETED = "completed"  # Abgeschlossen


class CashFlowEntryType(str, Enum):
    """Cash-Flow-Eintragstyp."""
    INVOICE_RECEIVABLE = "invoice_receivable"  # Forderung
    INVOICE_PAYABLE = "invoice_payable"  # Verbindlichkeit
    RECURRING = "recurring"  # Wiederkehrend
    MANUAL = "manual"  # Manuell
    ACTUAL = "actual"  # Ist-Wert


class TransactionSortField(str, Enum):
    """SECURITY: Erlaubte Sortierfelder fuer Transaktionen.

    Whitelist zur Verhinderung von SQL-Injection durch
    validierte Feldnamen.
    """
    BOOKING_DATE = "booking_date"
    VALUE_DATE = "value_date"
    AMOUNT = "amount"
    COUNTERPARTY = "counterparty_name"
    REFERENCE = "reference"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


# =============================================================================
# BANK ACCOUNT SCHEMAS
# =============================================================================

class BankAccountBase(BaseModel):
    """Basis-Schema fuer Bankkonten."""
    account_name: str = Field(..., min_length=1, max_length=255)
    iban: str = Field(..., min_length=15, max_length=34)
    bic: Optional[str] = Field(None, max_length=11)
    bank_name: Optional[str] = Field(None, max_length=255)
    account_holder: Optional[str] = Field(None, max_length=255)
    account_type: BankAccountType = BankAccountType.CHECKING
    currency: str = Field(default="EUR", max_length=3)

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str) -> str:
        """Validiere und normalisiere IBAN."""
        # Entferne Leerzeichen und konvertiere zu Grossbuchstaben
        iban = v.replace(" ", "").upper()
        if len(iban) < 15 or len(iban) > 34:
            raise ValueError("IBAN muss zwischen 15 und 34 Zeichen lang sein")
        # Basis-Validierung (Laendercode + Pruefsumme)
        if not iban[:2].isalpha():
            raise ValueError("IBAN muss mit Laendercode beginnen")
        if not iban[2:4].isdigit():
            raise ValueError("IBAN muss Pruefsumme nach Laendercode haben")
        return iban


class BankAccountCreate(BankAccountBase):
    """Schema zum Erstellen eines Bankkontos."""
    # FinTS-Optionen (optional)
    blz: Optional[str] = Field(None, max_length=8)
    fints_url: Optional[str] = Field(None, max_length=500)
    login_id: Optional[str] = Field(None, max_length=255)


class BankAccountUpdate(BaseModel):
    """Schema zum Aktualisieren eines Bankkontos."""
    account_name: Optional[str] = Field(None, min_length=1, max_length=255)
    bank_name: Optional[str] = Field(None, max_length=255)
    account_holder: Optional[str] = Field(None, max_length=255)
    account_type: Optional[BankAccountType] = None
    is_active: Optional[bool] = None
    auto_sync_enabled: Optional[bool] = None
    sync_interval_hours: Optional[int] = Field(None, ge=1, le=168)  # 1h - 1 Woche


class BankAccountResponse(BankAccountBase):
    """Response-Schema fuer Bankkonto."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    is_active: bool
    connection_status: str
    current_balance: Optional[Decimal] = None
    balance_date: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    auto_sync_enabled: bool
    created_at: datetime
    updated_at: datetime


class BankAccountWithStats(BankAccountResponse):
    """Bankkonto mit Statistiken."""
    transaction_count: int = 0
    unmatched_count: int = 0
    pending_payments_count: int = 0
    total_in_this_month: Decimal = Decimal("0")
    total_out_this_month: Decimal = Decimal("0")


# =============================================================================
# IMPORT SCHEMAS
# =============================================================================

class BankImportCreate(BaseModel):
    """Schema fuer Import-Anfrage."""
    bank_account_id: Optional[UUID] = None
    format: Optional[ImportFormat] = None  # Auto-detect wenn nicht angegeben
    format_variant: Optional[str] = None


class BankImportPreview(BaseModel):
    """Vorschau vor dem Import."""
    format_detected: ImportFormat
    format_confidence: float
    transaction_count: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_credits: Decimal
    total_debits: Decimal
    sample_transactions: List[Dict[str, Any]]
    warnings: List[str] = []


class BankImportResponse(BaseModel):
    """Response nach erfolgreichem Import."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: Optional[str]
    format: ImportFormat
    format_variant: Optional[str]
    status: str
    transaction_count: int
    duplicate_count: int
    error_count: int
    date_from: Optional[date]
    date_to: Optional[date]
    imported_at: datetime
    processing_duration_ms: Optional[int]
    errors: List[Dict[str, Any]] = []


class SupportedFormatsResponse(BaseModel):
    """Liste unterstuetzter Formate."""
    formats: List[Dict[str, Any]]


# =============================================================================
# TRANSACTION SCHEMAS
# =============================================================================

class BankTransactionResponse(BaseModel):
    """Response-Schema fuer Transaktion."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bank_account_id: UUID
    transaction_id: Optional[str]
    booking_date: date
    value_date: date
    amount: Decimal
    currency: str
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    counterparty_bic: Optional[str]
    reference_text: Optional[str]
    transaction_type: Optional[TransactionType]
    booking_text: Optional[str]

    # Reconciliation
    reconciliation_status: ReconciliationStatus
    matched_document_id: Optional[UUID]
    matched_invoice_number: Optional[str]
    match_confidence: Optional[float]
    match_method: Optional[str]

    # Teilzahlung
    is_partial_payment: bool
    allocated_amount: Optional[Decimal]
    remaining_amount: Optional[Decimal]

    imported_at: datetime


class TransactionListResponse(BaseModel):
    """Paginierte Transaktionsliste."""
    items: List[BankTransactionResponse]
    total: int
    page: int
    page_size: int
    unmatched_count: int
    matched_count: int


class TransactionFilter(BaseModel):
    """Filter fuer Transaktionen."""
    bank_account_id: Optional[UUID] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    reconciliation_status: Optional[ReconciliationStatus] = None
    search_text: Optional[str] = None
    counterparty_iban: Optional[str] = None


# =============================================================================
# RECONCILIATION SCHEMAS
# =============================================================================

class TransactionMatch(BaseModel):
    """Vorgeschlagenes Match."""
    document_id: UUID
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    invoice_amount: Decimal
    business_entity_name: Optional[str]
    match_confidence: float
    match_reasons: List[str]


class ReconciliationSuggestions(BaseModel):
    """Match-Vorschlaege fuer eine Transaktion."""
    transaction_id: UUID
    transaction_amount: Decimal
    suggestions: List[TransactionMatch]
    no_match_reason: Optional[str] = None


class MatchConfirmRequest(BaseModel):
    """Anfrage zur Bestaetigung eines Matches."""
    document_id: UUID
    is_partial: bool = False
    allocated_amount: Optional[Decimal] = None


class TransactionSplitRequest(BaseModel):
    """Anfrage zum Aufteilen einer Transaktion."""
    splits: List[Dict[str, Any]]  # [{document_id, amount}, ...]


class ReconciliationResult(BaseModel):
    """Ergebnis eines Abgleichs."""
    transaction_id: UUID
    status: ReconciliationStatus
    matched_document_id: Optional[UUID]
    match_confidence: Optional[float]
    match_method: Optional[str]


class BatchReconciliationResult(BaseModel):
    """Ergebnis eines Batch-Abgleichs."""
    total_processed: int
    matched_count: int
    partial_count: int
    unmatched_count: int
    results: List[ReconciliationResult]


# =============================================================================
# PAYMENT SCHEMAS
# =============================================================================

class PaymentOrderCreate(BaseModel):
    """Schema zum Erstellen einer Zahlung."""
    bank_account_id: UUID
    document_id: Optional[UUID] = None
    payment_type: PaymentType = PaymentType.TRANSFER

    # Empfaenger
    beneficiary_name: str = Field(..., min_length=1, max_length=140)
    beneficiary_iban: str = Field(..., min_length=15, max_length=34)
    beneficiary_bic: Optional[str] = Field(None, max_length=11)

    # Betrag
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="EUR", max_length=3)

    # Details
    reference: Optional[str] = Field(None, max_length=140)
    execution_date: Optional[date] = None

    # Skonto
    use_skonto: bool = False


class PaymentOrderUpdate(BaseModel):
    """Schema zum Aktualisieren einer Zahlung."""
    beneficiary_name: Optional[str] = Field(None, min_length=1, max_length=140)
    beneficiary_iban: Optional[str] = Field(None, min_length=15, max_length=34)
    beneficiary_bic: Optional[str] = Field(None, max_length=11)
    amount: Optional[Decimal] = Field(None, gt=0)
    reference: Optional[str] = Field(None, max_length=140)
    execution_date: Optional[date] = None


class PaymentOrderResponse(BaseModel):
    """Response-Schema fuer Zahlungsauftrag."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    bank_account_id: UUID
    document_id: Optional[UUID]
    invoice_number: Optional[str]
    payment_type: PaymentType
    sepa_type: Optional[SEPAType]

    # Empfaenger
    beneficiary_name: str
    beneficiary_iban: str
    beneficiary_bic: Optional[str]

    # Betrag
    amount: Decimal
    currency: str

    # Details
    reference: Optional[str]
    execution_date: Optional[date]

    # Status
    status: PaymentStatus
    tan_required: bool

    # Skonto
    uses_skonto: bool
    skonto_amount: Optional[Decimal]
    original_amount: Optional[Decimal]
    skonto_deadline: Optional[date]

    # Audit
    approved_at: Optional[datetime]
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class PaymentSuggestion(BaseModel):
    """Zahlungsvorschlag fuer faellige Rechnung."""
    document_id: UUID
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    due_date: Optional[date]
    days_until_due: int
    gross_amount: Decimal
    currency: str
    beneficiary_name: Optional[str]
    beneficiary_iban: Optional[str]

    # Skonto
    has_skonto: bool
    skonto_percent: Optional[Decimal]
    skonto_deadline: Optional[date]
    skonto_amount: Optional[Decimal]
    amount_with_skonto: Optional[Decimal]
    skonto_days_remaining: Optional[int]


class TANChallenge(BaseModel):
    """TAN-Challenge von der Bank."""
    session_id: UUID
    challenge_text: str
    challenge_data: Optional[bytes] = None
    tan_method: str
    expires_at: datetime


class TANConfirmRequest(BaseModel):
    """TAN-Bestaetigung."""
    tan: str = Field(..., min_length=4, max_length=10)


class PaymentBatchCreate(BaseModel):
    """Schema zum Erstellen einer Sammelzahlung."""
    bank_account_id: UUID
    batch_name: Optional[str] = None
    payment_ids: List[UUID]
    execution_date: Optional[date] = None


class PaymentBatchResponse(BaseModel):
    """Response-Schema fuer Sammelzahlung."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    bank_account_id: UUID
    batch_name: Optional[str]
    batch_type: str
    payment_count: int
    total_amount: Decimal
    currency: str
    status: PaymentStatus
    requested_execution_date: Optional[date]
    submitted_at: Optional[datetime]
    completed_at: Optional[datetime]
    successful_count: int
    failed_count: int
    created_at: datetime


# =============================================================================
# DUNNING SCHEMAS
# =============================================================================

class DunningRecordResponse(BaseModel):
    """Response-Schema fuer Mahnfall."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    due_date: Optional[date]
    gross_amount: Optional[Decimal]
    outstanding_amount: Optional[Decimal]
    currency: str

    # Schuldner
    debtor_name: Optional[str]
    debtor_email: Optional[str]

    # Mahnung
    dunning_level: DunningLevel
    status: DunningStatus

    # Gebuehren
    reminder_fee: Decimal
    late_interest_rate: Optional[Decimal]
    accrued_interest: Decimal
    total_outstanding: Optional[Decimal]

    # Timeline
    first_reminder_at: Optional[datetime]
    second_reminder_at: Optional[datetime]
    final_reminder_at: Optional[datetime]
    next_action_at: Optional[datetime]

    created_at: datetime
    updated_at: datetime


class DunningEscalateRequest(BaseModel):
    """Anfrage zur Eskalation einer Mahnung."""
    send_reminder: bool = True
    reminder_fee: Optional[Decimal] = None


class AgingReportEntry(BaseModel):
    """Eintrag im Faelligkeitsbericht."""
    document_id: UUID
    invoice_number: Optional[str]
    debtor_name: Optional[str]
    invoice_date: Optional[date]
    due_date: Optional[date]
    days_overdue: int
    gross_amount: Decimal
    outstanding_amount: Decimal
    currency: str
    dunning_level: DunningLevel


class AgingReport(BaseModel):
    """Faelligkeitsbericht (Altersstruktur)."""
    as_of_date: date
    total_outstanding: Decimal
    currency: str

    # Altersgruppen
    current: Decimal  # Nicht faellig
    days_1_30: Decimal  # 1-30 Tage
    days_31_60: Decimal  # 31-60 Tage
    days_61_90: Decimal  # 61-90 Tage
    days_over_90: Decimal  # >90 Tage

    # Details
    entries: List[AgingReportEntry]


# =============================================================================
# CASH FLOW SCHEMAS
# =============================================================================

class CashFlowEntryResponse(BaseModel):
    """Response-Schema fuer Cash-Flow-Eintrag."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entry_type: CashFlowEntryType
    direction: CashFlowDirection
    expected_date: date
    actual_date: Optional[date]
    expected_amount: Decimal
    actual_amount: Optional[Decimal]
    currency: str
    probability: float
    description: Optional[str]
    category: Optional[str]
    status: CashFlowStatus
    counterparty_name: Optional[str]

    # Referenzen
    document_id: Optional[UUID]
    payment_order_id: Optional[UUID]
    transaction_id: Optional[UUID]


class CashFlowDayForecast(BaseModel):
    """Tages-Prognose."""
    date: date
    expected_in: Decimal
    expected_out: Decimal
    net_change: Decimal
    running_balance: Decimal
    entries: List[CashFlowEntryResponse]


class CashFlowForecast(BaseModel):
    """Cash-Flow-Prognose."""
    as_of_date: date
    current_balance: Decimal
    currency: str
    forecast_days: int

    # Zusammenfassung
    total_expected_in: Decimal
    total_expected_out: Decimal
    net_change: Decimal
    projected_balance: Decimal

    # Warnungen
    negative_balance_dates: List[date]
    low_balance_warning: bool

    # Tagesprognosen
    daily_forecast: List[CashFlowDayForecast]


class PaymentBehaviorAnalysis(BaseModel):
    """Analyse des Zahlungsverhaltens."""
    business_entity_id: UUID
    business_entity_name: str
    invoice_count: int
    avg_payment_days: float
    on_time_rate: float  # Anteil puenktlicher Zahlungen
    payment_pattern: str  # "puenktlich", "verzoegert", "problematisch"
    recommended_probability: float  # Fuer Cash-Flow-Prognose


# =============================================================================
# DASHBOARD / KPI SCHEMAS
# =============================================================================

class BankingKPIs(BaseModel):
    """Banking-KPIs fuer Dashboard."""
    # Kontostand
    total_balance: Decimal
    balance_by_account: Dict[str, Decimal]

    # Offene Posten
    open_receivables: Decimal  # Forderungen
    open_payables: Decimal  # Verbindlichkeiten
    overdue_receivables: Decimal

    # Abgleich
    unmatched_transaction_count: int
    reconciliation_rate: float  # 0-1

    # Zahlungen
    pending_payment_count: int
    pending_payment_amount: Decimal

    # Mahnwesen
    active_dunning_count: int
    dunning_amount: Decimal

    # Skonto
    skonto_opportunities_count: int
    potential_skonto_savings: Decimal

    # Periode
    period_start: date
    period_end: date
    period_inflow: Decimal
    period_outflow: Decimal


# =============================================================================
# FILTER & STATS SCHEMAS
# =============================================================================

class TransactionFilter(BaseModel):
    """Filter fuer Transaktions-Abfragen."""
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    transaction_type: Optional[TransactionType] = None
    reconciliation_status: Optional[ReconciliationStatus] = None
    search_text: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None


class TransactionStats(BaseModel):
    """Transaktions-Statistiken."""
    total_count: int
    total_credits: Decimal
    total_debits: Decimal
    unmatched_count: int
    matched_count: int
    partially_matched_count: int
    match_rate: float  # Prozentsatz 0-100
