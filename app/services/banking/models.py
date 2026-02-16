"""Pydantic schemas for Banking Integration.

Definiert alle Request/Response-Modelle für die Banking-API.
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
    BUSINESS = "business"  # Geschäftskonto
    CREDIT = "credit"  # Kreditkarte


class ImportFormat(str, Enum):
    """Unterstützte Import-Formate."""
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
    TRANSFER = "transfer"  # Überweisung
    DIRECT_DEBIT = "direct_debit"  # Lastschrift
    CARD = "card"  # Kartenzahlung
    CASH = "cash"  # Bargeld
    FEE = "fee"  # Gebühr
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
    CONFIRMED = "confirmed"  # Bestätigt
    REJECTED = "rejected"  # Abgelehnt
    FAILED = "failed"  # Fehlgeschlagen
    CANCELLED = "cancelled"  # Storniert


class PaymentType(str, Enum):
    """Zahlungsart."""
    TRANSFER = "transfer"  # Einzelüberweisung
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


class MahnTaskType(str, Enum):
    """Aufgabentyp im Mahnwesen."""
    REMINDER = "reminder"  # Mahnung versenden
    ESCALATE = "escalate"  # Eskalieren
    PHONE_CALL = "phone_call"  # Telefonkontakt
    REVIEW = "review"  # Prüfung
    COLLECTION = "collection"  # Inkasso


class MahnTaskStatus(str, Enum):
    """Status einer Mahnaufgabe."""
    PENDING = "pending"  # Ausstehend
    IN_PROGRESS = "in_progress"  # In Bearbeitung
    COMPLETED = "completed"  # Erledigt
    SNOOZED = "snoozed"  # Zurückgestellt
    CANCELLED = "cancelled"  # Abgebrochen


class PhoneCallOutcome(str, Enum):
    """Ergebnis eines Telefonkontakts."""
    REACHED = "reached"  # Erreicht
    NOT_REACHED = "not_reached"  # Nicht erreicht
    VOICEMAIL = "voicemail"  # Mailbox
    CALLBACK_REQUESTED = "callback_requested"  # Rückruf erbeten
    PAYMENT_PROMISED = "payment_promised"  # Zahlung zugesagt
    DISPUTE_RAISED = "dispute_raised"  # Reklamation


class DunningActionType(str, Enum):
    """Aktionstyp für Mahnstufen."""
    EMAIL = "email"  # E-Mail
    LETTER = "letter"  # Brief
    PHONE = "phone"  # Telefon
    ESCALATION = "escalation"  # Eskalation/Inkasso


class MahnungHistoryActionType(str, Enum):
    """Aktionstypen für Mahnung-History."""
    REMINDER_SENT = "reminder_sent"
    ESCALATED = "escalated"
    PHONE_CALL = "phone_call"
    PAYMENT_RECEIVED = "payment_received"
    PARTIAL_PAYMENT = "partial_payment"
    MAHNSTOPP_SET = "mahnstopp_set"
    MAHNSTOPP_LIFTED = "mahnstopp_lifted"
    B2B_PAUSCHALE_CLAIMED = "b2b_pauschale_claimed"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    NOTE_ADDED = "note_added"
    STATUS_CHANGED = "status_changed"


class ContactMethod(str, Enum):
    """Bevorzugte Kontaktmethode."""
    EMAIL = "email"
    PHONE = "phone"
    LETTER = "letter"


class CashFlowStatus(str, Enum):
    """Cash-Flow-Status."""
    EXPECTED = "expected"  # Erwartet
    CONFIRMED = "confirmed"  # Bestätigt
    COMPLETED = "completed"  # Abgeschlossen


class CashFlowEntryType(str, Enum):
    """Cash-Flow-Eintragstyp."""
    INVOICE_RECEIVABLE = "invoice_receivable"  # Forderung
    INVOICE_PAYABLE = "invoice_payable"  # Verbindlichkeit
    RECURRING = "recurring"  # Wiederkehrend
    MANUAL = "manual"  # Manuell
    ACTUAL = "actual"  # Ist-Wert


class TransactionSortField(str, Enum):
    """SECURITY: Erlaubte Sortierfelder für Transaktionen.

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
    """Basis-Schema für Bankkonten."""
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
        # Basis-Validierung (Ländercode + Prüfsumme)
        if not iban[:2].isalpha():
            raise ValueError("IBAN muss mit Ländercode beginnen")
        if not iban[2:4].isdigit():
            raise ValueError("IBAN muss Prüfsumme nach Ländercode haben")
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
    """Response-Schema für Bankkonto."""
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
    updated_at: Optional[datetime] = None


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
    """Schema für Import-Anfrage."""
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
    """Liste unterstützter Formate."""
    formats: List[Dict[str, Any]]


# =============================================================================
# TRANSACTION SCHEMAS
# =============================================================================

class BankTransactionResponse(BaseModel):
    """Response-Schema für Transaktion."""
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
    """Filter für Transaktionen."""
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
    """Match-Vorschläge für eine Transaktion."""
    transaction_id: UUID
    transaction_amount: Decimal
    suggestions: List[TransactionMatch]
    no_match_reason: Optional[str] = None


class MatchConfirmRequest(BaseModel):
    """Anfrage zur Bestätigung eines Matches."""
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

    # Empfänger
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
    """Response-Schema für Zahlungsauftrag."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    bank_account_id: UUID
    document_id: Optional[UUID]
    invoice_number: Optional[str]
    payment_type: PaymentType
    sepa_type: Optional[SEPAType]

    # Empfänger
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
    """Zahlungsvorschlag für fällige Rechnung."""
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
    """TAN-Bestätigung."""
    tan: str = Field(..., min_length=4, max_length=10)


class PaymentBatchCreate(BaseModel):
    """Schema zum Erstellen einer Sammelzahlung."""
    bank_account_id: UUID
    batch_name: Optional[str] = None
    payment_ids: List[UUID]
    execution_date: Optional[date] = None


class PaymentBatchResponse(BaseModel):
    """Response-Schema für Sammelzahlung."""
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
    """Response-Schema für Mahnfall."""
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

    # Gebühren
    reminder_fee: Decimal
    late_interest_rate: Optional[Decimal]
    accrued_interest: Decimal
    total_outstanding: Optional[Decimal]

    # BGB §286 - B2B/B2C Unterscheidung
    is_b2b: bool = True
    b2b_pauschale_claimed: bool = False

    # Mahnstopp (bei Reklamation)
    mahnstopp: bool = False
    mahnstopp_reason: Optional[str] = None
    mahnstopp_until: Optional[datetime] = None

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
    """Eintrag im Fälligkeitsbericht."""
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
    """Fälligkeitsbericht (Altersstruktur)."""
    as_of_date: date
    total_outstanding: Decimal
    currency: str

    # Altersgruppen
    current: Decimal  # Nicht fällig
    days_1_30: Decimal  # 1-30 Tage
    days_31_60: Decimal  # 31-60 Tage
    days_61_90: Decimal  # 61-90 Tage
    days_over_90: Decimal  # >90 Tage

    # Details
    entries: List[AgingReportEntry]


# =============================================================================
# MAHN-TASK SCHEMAS (Aufgabenverwaltung)
# =============================================================================

class MahnTaskCreate(BaseModel):
    """Schema zum Erstellen einer Mahnaufgabe."""
    dunning_record_id: UUID
    task_type: MahnTaskType
    due_date: date
    assigned_user_id: Optional[UUID] = None
    priority: int = Field(default=3, ge=1, le=5)


class MahnTaskResponse(BaseModel):
    """Response-Schema für Mahnaufgabe."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dunning_record_id: UUID
    task_type: MahnTaskType
    assigned_user_id: Optional[UUID]
    due_date: date
    status: MahnTaskStatus
    priority: int

    # Snooze (max 3x)
    snoozed_until: Optional[date]
    snooze_count: int
    snooze_reason: Optional[str]

    # Completion
    completed_at: Optional[datetime]
    completed_by_id: Optional[UUID]
    completion_notes: Optional[str]

    created_at: datetime
    updated_at: datetime

    # Erweiterte Infos (optional befuellt)
    invoice_number: Optional[str] = None
    debtor_name: Optional[str] = None
    outstanding_amount: Optional[Decimal] = None
    days_overdue: Optional[int] = None


class MahnTaskWithDunning(MahnTaskResponse):
    """Mahnaufgabe mit vollständigen Dunning-Details."""
    dunning_record: Optional[DunningRecordResponse] = None


class MahnTaskFilter(BaseModel):
    """Filter für Mahnaufgaben."""
    task_type: Optional[MahnTaskType] = None
    status: Optional[MahnTaskStatus] = None
    assigned_user_id: Optional[UUID] = None
    due_date_from: Optional[date] = None
    due_date_to: Optional[date] = None
    priority: Optional[int] = None
    include_snoozed: bool = False


class MahnTaskSnoozeRequest(BaseModel):
    """Anfrage zum Zurückstellen einer Aufgabe."""
    snooze_until: date
    reason: Optional[str] = Field(None, max_length=255)


class MahnTaskCompleteRequest(BaseModel):
    """Anfrage zum Abschließen einer Aufgabe."""
    notes: Optional[str] = None


class MahnTaskBulkCompleteRequest(BaseModel):
    """Anfrage zum Massenabschluss von Aufgaben."""
    task_ids: List[UUID]
    notes: Optional[str] = None


class MahnTaskSummary(BaseModel):
    """Zusammenfassung der Mahnaufgaben."""
    pending_count: int
    overdue_count: int
    due_today_count: int
    snoozed_count: int
    by_type: Dict[str, int]
    by_priority: Dict[int, int]


# =============================================================================
# PHONE CALL LOG SCHEMAS (Telefonprotokoll)
# =============================================================================

class PhoneCallLogCreate(BaseModel):
    """Schema zum Erstellen eines Telefonprotokolls."""
    dunning_record_id: UUID
    contact_name: str = Field(..., min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=50)
    outcome: PhoneCallOutcome
    notes: Optional[str] = None
    follow_up_required: bool = False
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = Field(None, max_length=255)


class PhoneCallLogResponse(BaseModel):
    """Response-Schema für Telefonprotokoll."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dunning_record_id: UUID
    called_at: datetime
    called_by_id: Optional[UUID]
    called_by_name: Optional[str] = None
    contact_name: str
    phone_number: Optional[str]
    outcome: PhoneCallOutcome
    notes: Optional[str]
    follow_up_required: bool
    follow_up_date: Optional[date]
    follow_up_notes: Optional[str]


class PhoneCallLogListResponse(BaseModel):
    """Liste von Telefonprotokollen."""
    items: List[PhoneCallLogResponse]
    total: int


# =============================================================================
# DUNNING STAGE CONFIG SCHEMAS (Mahnstufen-Konfiguration)
# =============================================================================

class DunningStageConfigCreate(BaseModel):
    """Schema zum Erstellen einer Mahnstufe."""
    stage_number: int = Field(..., ge=1, le=10)
    stage_name: str = Field(..., min_length=1, max_length=100)
    trigger_days_after_due: int = Field(..., ge=0)
    action_type: DunningActionType
    template_id: Optional[UUID] = None
    fee_amount: Decimal = Field(default=Decimal("0.00"), ge=0)


class DunningStageConfigUpdate(BaseModel):
    """Schema zum Aktualisieren einer Mahnstufe."""
    stage_name: Optional[str] = Field(None, min_length=1, max_length=100)
    trigger_days_after_due: Optional[int] = Field(None, ge=0)
    action_type: Optional[DunningActionType] = None
    template_id: Optional[UUID] = None
    fee_amount: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None


class DunningStageConfigResponse(BaseModel):
    """Response-Schema für Mahnstufe."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    stage_number: int
    stage_name: str
    trigger_days_after_due: int
    action_type: DunningActionType
    template_id: Optional[UUID]
    fee_amount: Decimal
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class DunningStageReorderRequest(BaseModel):
    """Anfrage zur Neuordnung der Mahnstufen."""
    stage_ids: List[UUID]


class DunningStagesListResponse(BaseModel):
    """Liste der Mahnstufen."""
    stages: List[DunningStageConfigResponse]
    interest_rate_b2b: Decimal
    interest_rate_b2c: Decimal
    b2b_pauschale: Decimal


# =============================================================================
# CUSTOMER DUNNING OVERRIDE SCHEMAS (Kundenspezifische Einstellungen)
# =============================================================================

class CustomerDunningOverrideCreate(BaseModel):
    """Schema zum Erstellen kundenspezifischer Mahneinstellungen."""
    business_entity_id: UUID
    custom_payment_terms_days: Optional[int] = Field(None, ge=0)
    max_mahn_stufe: Optional[int] = Field(None, ge=1, le=5)
    preferred_contact_method: ContactMethod = ContactMethod.EMAIL
    exclude_from_auto_dunning: bool = False
    exclusion_reason: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class CustomerDunningOverrideUpdate(BaseModel):
    """Schema zum Aktualisieren kundenspezifischer Mahneinstellungen."""
    custom_payment_terms_days: Optional[int] = Field(None, ge=0)
    max_mahn_stufe: Optional[int] = Field(None, ge=1, le=5)
    preferred_contact_method: Optional[ContactMethod] = None
    exclude_from_auto_dunning: Optional[bool] = None
    exclusion_reason: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class CustomerDunningOverrideResponse(BaseModel):
    """Response-Schema für kundenspezifische Mahneinstellungen."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_entity_id: UUID
    business_entity_name: Optional[str] = None
    custom_payment_terms_days: Optional[int]
    max_mahn_stufe: Optional[int]
    preferred_contact_method: ContactMethod
    exclude_from_auto_dunning: bool
    exclusion_reason: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# =============================================================================
# MAHNUNG HISTORY SCHEMAS (Audit-Log)
# =============================================================================

class MahnungHistoryResponse(BaseModel):
    """Response-Schema für Mahnung-History-Eintrag."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dunning_record_id: UUID
    action_type: MahnungHistoryActionType
    mahn_stufe: int
    action_timestamp: datetime
    performed_by_id: Optional[UUID]
    performed_by_name: Optional[str] = None
    notes: Optional[str]
    outcome: Optional[str]
    document_id: Optional[UUID]
    metadata: Optional[Dict[str, Any]] = None


class MahnungHistoryListResponse(BaseModel):
    """Liste von Mahnung-History-Einträgen."""
    items: List[MahnungHistoryResponse]
    total: int


# =============================================================================
# MAHNSTOPP SCHEMAS
# =============================================================================

class MahnstoppSetRequest(BaseModel):
    """Anfrage zum Setzen eines Mahnstopps."""
    reason: str = Field(..., min_length=1, max_length=255)
    until_date: Optional[date] = None


class MahnstoppLiftRequest(BaseModel):
    """Anfrage zum Aufheben eines Mahnstopps."""
    notes: Optional[str] = None


# =============================================================================
# BULK ACTION SCHEMAS
# =============================================================================

class BulkEscalateRequest(BaseModel):
    """Anfrage zur Masseneskalation."""
    dunning_ids: List[UUID]
    notes: Optional[str] = None


class BulkEscalateResponse(BaseModel):
    """Response der Masseneskalation."""
    total: int
    successful: int
    failed: int
    errors: List[Dict[str, str]]


class BulkSendReminderRequest(BaseModel):
    """Anfrage zum Massenversand von Mahnungen."""
    dunning_ids: List[UUID]
    send_email: bool = True
    send_letter: bool = False


class BulkSendReminderResponse(BaseModel):
    """Response des Massenversands."""
    total: int
    sent: int
    skipped: int  # Z.B. wegen Mahnstopp
    errors: List[Dict[str, str]]


# =============================================================================
# B2B PAUSCHALE SCHEMA
# =============================================================================

class B2BPauschaleClaimResponse(BaseModel):
    """Response nach Beanspruchung der B2B-Pauschale."""
    dunning_id: UUID
    pauschale_amount: Decimal
    already_claimed: bool
    success: bool
    message: str


# =============================================================================
# VERZUGSZINSEN SCHEMA
# =============================================================================

class VerzugszinsenCalculation(BaseModel):
    """Verzugszinsen-Berechnung."""
    principal: Decimal
    due_date: date
    as_of_date: date
    is_b2b: bool
    interest_rate: Decimal  # Z.B. 11.27 für B2B
    days_overdue: int
    interest_amount: Decimal
    total_with_interest: Decimal


# =============================================================================
# MAHNLAUF SCHEMAS (Daily Dunning Run)
# =============================================================================

class MahnlaufResult(BaseModel):
    """Ergebnis des täglichen Mahnlaufs."""
    run_date: date
    is_business_day: bool
    skipped_reason: Optional[str] = None
    candidates_found: int
    tasks_created: int
    skipped_mahnstopp: int
    skipped_excluded: int
    errors: List[Dict[str, str]]
    duration_seconds: float


# =============================================================================
# AUTO-MAHNLAUF SETTINGS SCHEMAS
# =============================================================================

class AutoDunningActionType(str, Enum):
    """Typ der automatischen Mahnlauf-Aktion."""
    ESCALATE = "escalate"
    SEND_REMINDER = "send_reminder"
    CREATE_TASK = "create_task"
    SKIP = "skip"


class AutomaticDunningAction(BaseModel):
    """Einzelne Aktion aus dem automatischen Mahnlauf."""
    dunning_id: UUID
    invoice_number: Optional[str] = None
    debtor_name: Optional[str] = None
    current_level: int
    new_level: int
    action_type: AutoDunningActionType
    action_description: str
    days_overdue: int
    outstanding_amount: Decimal
    currency: str = "EUR"
    skipped: bool = False
    skip_reason: Optional[str] = None
    scheduled_at: datetime


class LevelIntervals(BaseModel):
    """Intervalle in Tagen pro Mahnstufe."""
    level_1: int = Field(default=7, ge=1, le=90, description="Tage bis 1. Mahnung")
    level_2: int = Field(default=14, ge=1, le=90, description="Tage bis 2. Mahnung")
    level_3: int = Field(default=21, ge=1, le=90, description="Tage bis 3. Mahnung")


class AutoDunningSettingsResponse(BaseModel):
    """Response-Schema für Auto-Mahnlauf-Einstellungen."""
    enabled: bool = Field(default=False, description="Automatische Eskalation aktiviert")
    run_time: str = Field(default="08:00", description="Uhrzeit für täglichen Mahnlauf (HH:MM)")
    exclude_weekends: bool = Field(default=True, description="Wochenenden ausschließen")
    exclude_holidays: bool = Field(default=True, description="Feiertage ausschließen")
    auto_send_email: bool = Field(default=False, description="Automatischer Email-Versand")
    min_amount: Decimal = Field(default=Decimal("10.00"), ge=0, description="Mindestbetrag für automatische Mahnung")
    max_auto_level: int = Field(default=2, ge=1, le=3, description="Maximale Mahnstufe für Automatik")
    level_intervals: LevelIntervals = Field(default_factory=LevelIntervals)
    last_run_at: Optional[datetime] = Field(default=None, description="Letzte Ausführung")
    next_run_at: Optional[datetime] = Field(default=None, description="Nächste geplante Ausführung")


class AutoDunningSettingsUpdate(BaseModel):
    """Request-Schema für Auto-Mahnlauf-Einstellungen Update."""
    enabled: Optional[bool] = None
    run_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")
    exclude_weekends: Optional[bool] = None
    exclude_holidays: Optional[bool] = None
    auto_send_email: Optional[bool] = None
    min_amount: Optional[Decimal] = Field(default=None, ge=0)
    max_auto_level: Optional[int] = Field(default=None, ge=1, le=3)
    level_intervals: Optional[LevelIntervals] = None


# =============================================================================
# CASH FLOW SCHEMAS
# =============================================================================

class CashFlowEntryResponse(BaseModel):
    """Response-Schema für Cash-Flow-Eintrag."""
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
    payment_pattern: str  # "puenktlich", "verzögert", "problematisch"
    recommended_probability: float  # Für Cash-Flow-Prognose


# =============================================================================
# DASHBOARD / KPI SCHEMAS
# =============================================================================

class BankingKPIs(BaseModel):
    """Banking-KPIs für Dashboard."""
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
    """Filter für Transaktions-Abfragen."""
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
