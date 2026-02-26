"""Banking Domain Models - Modularisierung Phase 1.1.

Enthält alle Banking-, Mahnwesen- und E-Rechnungs-Modelle:
- EInvoiceFormat, EInvoiceProfile, EInvoiceDocument
- BankAccount, BankImport, BankTransaction
- PaymentBatch, PaymentOrder
- DunningRecord, MahnungHistory, MahnTask
- PhoneCallLog, DunningStageConfig, CustomerDunningOverride
- CashFlowEntry
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin

# =============================================================================
# E-INVOICING (ZUGFeRD / XRechnung)
# =============================================================================

class EInvoiceFormat(str, Enum):
    """Unterstützte E-Rechnungsformate."""
    ZUGFERD = "zugferd"
    XRECHNUNG_CII = "xrechnung_cii"  # UN/CEFACT Cross Industry Invoice
    XRECHNUNG_UBL = "xrechnung_ubl"  # Universal Business Language
    FACTURX = "facturx"


class EInvoiceProfile(str, Enum):
    """ZUGFeRD/Factur-X Profile (EN 16931 Konformitaet)."""
    MINIMUM = "MINIMUM"
    BASIC = "BASIC"
    BASIC_WL = "BASIC_WL"
    EN16931 = "EN16931"
    EXTENDED = "EXTENDED"
    XRECHNUNG = "XRECHNUNG"


class EInvoiceDocument(Base):
    """
    E-Rechnung Metadaten und XML-Speicherung.

    Speichert:
    - Extrahiertes oder generiertes XML (ZUGFeRD/XRechnung)
    - Validierungsergebnisse (KoSIT Validator)
    - Generierungsmetadaten
    - Leitweg-ID für schnellen B2G-Lookup

    Jedes Dokument kann null oder eine zugehoerige E-Rechnung haben.
    """
    __tablename__ = "einvoice_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zum Original-Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True  # 1:1 Beziehung
    )

    # E-Invoice Format Information
    format = Column(String(50), nullable=False)  # EInvoiceFormat Wert
    profile = Column(String(50), nullable=True)  # EInvoiceProfile Wert
    version = Column(String(20), nullable=True)  # z.B. "2.3.3", "3.0.2"

    # XML Speicherung
    xml_content = Column(Text, nullable=True)  # Der extrahierte oder generierte XML-Inhalt
    xml_hash = Column(String(64), nullable=True)  # SHA256 für Integritätsprüfung

    # Validierung
    is_valid = Column(Boolean, nullable=True)  # null = nicht validiert
    validation_timestamp = Column(DateTime(timezone=True), nullable=True)
    validation_errors = Column(CrossDBJSON, default=list)  # Liste von Validierungsfehlern
    validation_warnings = Column(CrossDBJSON, default=list)  # Liste von Warnungen
    validator_used = Column(String(50), nullable=True)  # "kosit", "mustang", "facturx"

    # Schema/Schematron Validierung separat
    schema_valid = Column(Boolean, nullable=True)  # XSD Schema-Validierung
    schematron_valid = Column(Boolean, nullable=True)  # Business Rules (Schematron)
    pdf_a_compliant = Column(Boolean, nullable=True)  # PDF/A-3 Konformitaet (bei ZUGFeRD)

    # B2G-spezifische Felder (schneller Lookup)
    leitweg_id = Column(String(100), nullable=True, index=True)  # BT-10 Buyer Reference

    # Generierungsmetadaten
    was_generated = Column(Boolean, default=False)  # True wenn wir die E-Rechnung erstellt haben
    was_extracted = Column(Boolean, default=False)  # True wenn aus PDF extrahiert
    generation_timestamp = Column(DateTime(timezone=True), nullable=True)
    generated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Originalquelle (wenn extrahiert)
    source_filename = Column(String(255), nullable=True)  # Original ZUGFeRD-PDF Name
    extraction_method = Column(String(50), nullable=True)  # "facturx", "mustang", "manual"

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="einvoice_data")
    generated_by = relationship("User", foreign_keys=[generated_by_id])
    transmissions = relationship("EInvoiceTransmission", back_populates="einvoice", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_einvoice_docs_document_id", "document_id"),
        Index("ix_einvoice_docs_format", "format"),
        Index("ix_einvoice_docs_leitweg_id", "leitweg_id"),
        Index("ix_einvoice_docs_is_valid", "is_valid"),
        Index("ix_einvoice_docs_was_generated", "was_generated"),
    )

    def mark_validated(
        self,
        is_valid: bool,
        validator: str,
        errors: Optional[List[Dict[str, Any]]] = None,
        warnings: Optional[List[Dict[str, Any]]] = None,
        schema_valid: Optional[bool] = None,
        schematron_valid: Optional[bool] = None
    ) -> None:
        """Markiert die E-Rechnung als validiert."""
        self.is_valid = is_valid
        self.validator_used = validator
        self.validation_timestamp = datetime.now()
        self.validation_errors = errors or []
        self.validation_warnings = warnings or []
        if schema_valid is not None:
            self.schema_valid = schema_valid
        if schematron_valid is not None:
            self.schematron_valid = schematron_valid

    def get_validation_summary(self) -> Dict[str, Any]:
        """Gibt eine Zusammenfassung der Validierung zurück."""
        return {
            "is_valid": self.is_valid,
            "validator": self.validator_used,
            "validated_at": self.validation_timestamp.isoformat() if self.validation_timestamp else None,
            "error_count": len(self.validation_errors) if self.validation_errors else 0,
            "warning_count": len(self.validation_warnings) if self.validation_warnings else 0,
            "schema_valid": self.schema_valid,
            "schematron_valid": self.schematron_valid,
            "pdf_a_compliant": self.pdf_a_compliant,
        }


# =============================================================================
# BANKING INTEGRATION MODELS
# =============================================================================

class BankAccount(SoftDeleteMixin, Base):
    """Bankkonto für Transaktions-Import und Zahlungen."""
    __tablename__ = "bank_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Multi-Tenant (Migration 232)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Konto-Identifikation
    account_name = Column(String(255), nullable=False)
    iban = Column(String(34), nullable=False)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(255), nullable=True)
    account_holder = Column(String(255), nullable=True)
    account_type = Column(String(50), default="checking")

    # FinTS (optional)
    blz = Column(String(8), nullable=True)
    fints_url = Column(String(500), nullable=True)
    fints_version = Column(String(10), default="3.0")
    login_id_encrypted = Column(String(500), nullable=True)
    pin_hash = Column(String(255), nullable=True)

    # TAN-Konfiguration
    tan_method = Column(String(50), nullable=True)
    tan_media = Column(String(100), nullable=True)
    tan_mechanism_id = Column(String(20), nullable=True)

    # Sync-Konfiguration
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_from_date = Column(DateTime(timezone=True), nullable=True)
    auto_sync_enabled = Column(Boolean, default=False)
    sync_interval_hours = Column(Integer, default=24)

    # Saldo
    current_balance = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    balance_date = Column(DateTime(timezone=True), nullable=True)
    currency = Column(String(3), default="EUR")

    # Status
    is_active = Column(Boolean, default=True)
    connection_status = Column(String(50), default="manual")
    last_error = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_bank_accounts_company_active", "company_id", "is_active"),
    )

    # Relationships
    user = relationship("User", backref="bank_accounts")
    company: Mapped["Company"] = relationship("Company", back_populates="bank_accounts")
    transactions = relationship("BankTransaction", back_populates="bank_account", cascade="all, delete-orphan")
    imports = relationship("BankImport", back_populates="bank_account")


class BankImport(Base):
    """Import-Historie für Kontoauszuege."""
    __tablename__ = "bank_imports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Multi-Tenant (Migration 232)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True)

    # Import-Details
    filename = Column(String(255), nullable=True)
    file_hash = Column(String(64), nullable=True)
    file_size = Column(Integer, nullable=True)

    # Format
    format = Column(String(50), nullable=False)
    format_variant = Column(String(100), nullable=True)

    # Ergebnis
    status = Column(String(50), default="pending")
    transaction_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    errors = Column(CrossDBJSON, default=list)

    # Zeitraum
    date_from = Column(DateTime(timezone=True), nullable=True)
    date_to = Column(DateTime(timezone=True), nullable=True)

    # Audit
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    processing_duration_ms = Column(Integer, nullable=True)

    # Relationships
    user = relationship("User", backref="bank_imports")
    company: Mapped["Company"] = relationship("Company", back_populates="bank_imports")
    bank_account = relationship("BankAccount", back_populates="imports")


class BankTransaction(Base):
    """Importierte Kontobewegungen."""
    __tablename__ = "bank_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)
    import_id = Column(UUID(as_uuid=True), ForeignKey("bank_imports.id", ondelete="SET NULL"), nullable=True)

    # Transaktions-ID
    transaction_id = Column(String(100), nullable=True)
    booking_date = Column(DateTime(timezone=True), nullable=False)
    value_date = Column(DateTime(timezone=True), nullable=False)

    # Betrag
    amount = Column(Numeric(15, 2), nullable=False)  # SECURITY: Numeric für Geldbetraege
    currency = Column(String(3), default="EUR")

    # Gegenpartei
    counterparty_name = Column(String(255), nullable=True)
    counterparty_iban = Column(String(34), nullable=True)
    counterparty_bic = Column(String(11), nullable=True)
    counterparty_bank_name = Column(String(255), nullable=True)

    # Verwendungszweck
    reference_text = Column(Text, nullable=True)
    end_to_end_id = Column(String(35), nullable=True)
    mandate_id = Column(String(35), nullable=True)
    creditor_id = Column(String(35), nullable=True)

    # Kategorisierung
    transaction_type = Column(String(50), nullable=True)
    booking_text = Column(String(100), nullable=True)
    prima_nota = Column(String(20), nullable=True)

    # Geparste Referenzen
    parsed_invoice_numbers = Column(CrossDBJSON, default=list)
    parsed_customer_numbers = Column(CrossDBJSON, default=list)
    parsed_references = Column(CrossDBJSON, default=list)

    # Reconciliation
    reconciliation_status = Column(String(50), default="unmatched")
    matched_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    matched_invoice_number = Column(String(100), nullable=True)
    match_confidence = Column(Float, nullable=True)
    match_method = Column(String(50), nullable=True)
    matched_at = Column(DateTime(timezone=True), nullable=True)
    matched_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Teilzahlungen
    allocated_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    remaining_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    is_partial_payment = Column(Boolean, default=False)
    parent_transaction_id = Column(UUID(as_uuid=True), ForeignKey("bank_transactions.id", ondelete="SET NULL"), nullable=True)

    # Rohdaten
    raw_data = Column(CrossDBJSON, nullable=True)

    # Audit
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    bank_account = relationship("BankAccount", back_populates="transactions")
    matched_document = relationship("Document", backref="matched_transactions")
    matched_by = relationship("User", foreign_keys=[matched_by_id])


class PaymentBatch(Base):
    """Sammelzahlungen."""
    __tablename__ = "payment_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Multi-Tenant (Migration 232)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)

    # Batch-Details
    batch_name = Column(String(255), nullable=True)
    batch_type = Column(String(50), nullable=False)
    payment_count = Column(Integer, default=0)
    total_amount = Column(Numeric(15, 2), default=0)  # SECURITY: Numeric für Geldbetraege
    currency = Column(String(3), default="EUR")

    # Ausführung
    requested_execution_date = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(String(50), default="draft")

    # TAN
    tan_required = Column(Boolean, default=False)
    tan_challenge = Column(Text, nullable=True)
    tan_challenge_data = Column(Text, nullable=True)

    # Freigabe
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # SEPA XML
    sepa_xml = Column(Text, nullable=True)
    sepa_message_id = Column(String(35), nullable=True)

    # Ergebnis
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    successful_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)

    # Fehler
    last_error = Column(Text, nullable=True)

    # GoBD Audit (wer hat erstellt/zuletzt bearbeitet)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    company: Mapped["Company"] = relationship("Company", back_populates="payment_batches")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    payments = relationship("PaymentOrder", back_populates="batch")


class PaymentOrder(Base):
    """SEPA-Zahlungsauftraege."""
    __tablename__ = "payment_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Multi-Tenant (Migration 232)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)

    # Verknüpfte Rechnung
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    invoice_number = Column(String(100), nullable=True)

    # Zahlungstyp
    payment_type = Column(String(50), nullable=False)
    sepa_type = Column(String(50), nullable=True)

    # Empfänger
    beneficiary_name = Column(String(140), nullable=False)
    beneficiary_iban = Column(String(34), nullable=False)
    beneficiary_bic = Column(String(11), nullable=True)

    # Betrag
    amount = Column(Numeric(15, 2), nullable=False)  # SECURITY: Numeric für Geldbetraege
    currency = Column(String(3), default="EUR")

    # Zahlungsdetails
    reference = Column(Text, nullable=True)
    end_to_end_id = Column(String(35), nullable=True)
    execution_date = Column(DateTime(timezone=True), nullable=True)

    # Lastschrift
    mandate_id = Column(String(35), nullable=True)
    mandate_date = Column(DateTime(timezone=True), nullable=True)
    sequence_type = Column(String(10), nullable=True)
    creditor_id = Column(String(35), nullable=True)

    # Batch
    batch_id = Column(UUID(as_uuid=True), ForeignKey("payment_batches.id", ondelete="SET NULL"), nullable=True)
    batch_sequence = Column(Integer, nullable=True)

    # Status
    status = Column(String(50), default="draft")

    # TAN
    tan_required = Column(Boolean, default=False)
    tan_challenge = Column(Text, nullable=True)
    tan_challenge_data = Column(Text, nullable=True)
    tan_entered_at = Column(DateTime(timezone=True), nullable=True)

    # Freigabe
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Übermittlung
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    bank_reference = Column(String(100), nullable=True)

    # Fehler
    last_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # Skonto
    uses_skonto = Column(Boolean, default=False)
    skonto_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    original_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    skonto_deadline = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    company: Mapped["Company"] = relationship("Company", back_populates="payment_orders")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    document = relationship("Document", backref="payment_orders")
    batch = relationship("PaymentBatch", back_populates="payments")


class DunningRecord(Base):
    """Mahnwesen-Tracking."""
    __tablename__ = "dunning_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Multi-Tenant (Migration 232)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Rechnungsreferenz
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    gross_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    outstanding_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    currency = Column(String(3), default="EUR")

    # Geschäftspartner
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)
    debtor_name = Column(String(255), nullable=True)
    debtor_email = Column(String(255), nullable=True)

    # Mahnstufe
    dunning_level = Column(Integer, default=0)

    # Gebühren
    reminder_fee = Column(Numeric(15, 2), default=0)  # SECURITY: Numeric für Geldbetraege
    late_interest_rate = Column(Numeric(7, 4), nullable=True)  # Prozentsatz mit 4 Nachkommastellen
    accrued_interest = Column(Numeric(15, 2), default=0)  # SECURITY: Numeric für Geldbetraege
    total_outstanding = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege

    # Timeline
    first_reminder_at = Column(DateTime(timezone=True), nullable=True)
    second_reminder_at = Column(DateTime(timezone=True), nullable=True)
    final_reminder_at = Column(DateTime(timezone=True), nullable=True)
    next_action_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(String(50), default="pending")

    # B2B/B2C Unterscheidung (BGB §286 Compliance)
    is_b2b = Column(Boolean, default=True, comment="B2B: +9% Zinsen, B2C: +5% Zinsen")
    b2b_pauschale_claimed = Column(Boolean, default=False, comment="EUR40 Pauschale nach §288 Abs. 5 BGB")

    # Mahnstopp (für Reklamationen/Disputes)
    mahnstopp = Column(Boolean, default=False, comment="Stoppt automatische Mahnung")
    mahnstopp_reason = Column(String(255), nullable=True)
    mahnstopp_until = Column(DateTime(timezone=True), nullable=True)

    # Loesung
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Teilzahlungen
    partial_payment_ids = Column(CrossDBJSON, default=list)

    # GoBD Audit (wer hat erstellt/zuletzt bearbeitet)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_dunning_records_company_status", "company_id", "status"),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    company: Mapped["Company"] = relationship("Company", back_populates="dunning_records")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    document = relationship("Document", backref="dunning_records")
    business_entity = relationship("BusinessEntity", backref="dunning_records")
    history_entries = relationship("MahnungHistory", back_populates="dunning_record", cascade="all, delete-orphan")
    tasks = relationship("MahnTask", back_populates="dunning_record", cascade="all, delete-orphan")
    phone_calls = relationship("PhoneCallLog", back_populates="dunning_record", cascade="all, delete-orphan")


# =============================================================================
# MAHNUNGSWESEN MODELS (Dunning System Extensions)
# =============================================================================


class MahnungHistory(Base):
    """Immutable Audit-Log für Mahnvorgaenge.

    WICHTIG: Diese Tabelle ist append-only!
    Ein Datenbank-Trigger sollte UPDATE und DELETE verhindern.
    """
    __tablename__ = "mahnung_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dunning_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dunning_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktion
    action_type = Column(String(50), nullable=False, comment="reminder_sent, escalated, phone_call, payment_received, etc.")
    mahn_stufe = Column(Integer, nullable=False, comment="Mahnstufe zum Zeitpunkt der Aktion")
    action_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Ausführender
    performed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Details
    notes = Column(Text, nullable=True)
    outcome = Column(String(50), nullable=True, comment="success, failed, pending, etc.")
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Zusätzliche Metadaten (JSON)
    # HINWEIS: 'metadata' ist in SQLAlchemy reserviert, daher 'action_metadata'
    action_metadata = Column(CrossDBJSON, default=dict)

    # Relationships
    dunning_record = relationship("DunningRecord", back_populates="history_entries")
    performed_by = relationship("User", foreign_keys=[performed_by_id])
    generated_document = relationship("Document", foreign_keys=[document_id])

    # Indexes
    __table_args__ = (
        Index("ix_mahnung_history_action_timestamp", "action_timestamp"),
        Index("ix_mahnung_history_action_type", "action_type"),
    )


class MahnTask(Base):
    """Aufgaben für das Mahnungswesen.

    Tasks werden vom täglichen Mahnlauf erstellt und erscheinen
    im Dashboard zur manuellen Bearbeitung.
    """
    __tablename__ = "mahn_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dunning_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dunning_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aufgabentyp
    task_type = Column(String(50), nullable=False, comment="reminder, escalate, phone_call, review, collection")

    # Zuweisung
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Fälligkeit
    due_date = Column(Date, nullable=False)

    # Status
    status = Column(String(20), default="pending", nullable=False, comment="pending, in_progress, completed, snoozed, cancelled")

    # Snooze (max 3x)
    snoozed_until = Column(Date, nullable=True)
    snooze_count = Column(Integer, default=0)
    snooze_reason = Column(String(255), nullable=True)

    # Abschluss
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completion_notes = Column(Text, nullable=True)

    # Priorität (1=hoechste, 5=niedrigste)
    priority = Column(Integer, default=3)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    dunning_record = relationship("DunningRecord", back_populates="tasks")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    completed_by = relationship("User", foreign_keys=[completed_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_mahn_tasks_status", "status"),
        Index("ix_mahn_tasks_due_date", "due_date"),
        Index("ix_mahn_tasks_assigned_user", "assigned_user_id"),
    )


class PhoneCallLog(Base):
    """Telefonkontakt-Protokoll für Mahnungswesen.

    Dokumentiert alle telefonischen Kontaktversuche und deren Ergebnis.
    """
    __tablename__ = "phone_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dunning_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dunning_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Anrufdaten
    called_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    called_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Kontakt
    contact_name = Column(String(255), nullable=False)
    phone_number = Column(String(50), nullable=True)

    # Ergebnis
    outcome = Column(String(50), nullable=False, comment="reached, not_reached, voicemail, callback_requested, payment_promised, dispute_raised")

    # Notizen
    notes = Column(Text, nullable=True)

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(Date, nullable=True)
    follow_up_notes = Column(String(255), nullable=True)

    # Relationship
    dunning_record = relationship("DunningRecord", back_populates="phone_calls")
    called_by = relationship("User", foreign_keys=[called_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_phone_call_logs_called_at", "called_at"),
    )


class DunningStageConfig(Base):
    """Konfigurierbare Mahnstufen.

    Admin kann eigene Mahnstufen definieren mit:
    - Tagen nach Fälligkeit
    - Aktionstyp (Email, Brief, Telefon)
    - Mahngebühr
    - Template
    """
    __tablename__ = "dunning_stage_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Stage-Definition
    stage_number = Column(Integer, nullable=False, comment="1-basiert: 1=erste Stufe")
    stage_name = Column(String(100), nullable=False, comment="z.B. Zahlungserinnerung, 1. Mahnung")

    # Trigger
    trigger_days_after_due = Column(Integer, nullable=False, comment="Tage nach Fälligkeit")

    # Aktion
    action_type = Column(String(50), nullable=False, comment="email, letter, phone, escalation")
    template_id = Column(UUID(as_uuid=True), nullable=True, comment="Template-ID für Dokument-Generierung")

    # Gebühren
    fee_amount = Column(Numeric(10, 2), default=0, comment="Mahngebühr in EUR")

    # Status
    is_active = Column(Boolean, default=True)

    # Sortierung (für Drag-and-Drop Reorder)
    sort_order = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="dunning_stage_configs")

    # Indexes und Constraints
    __table_args__ = (
        Index("ix_dunning_stage_configs_user_id", "user_id"),
        Index("ix_dunning_stage_configs_sort_order", "user_id", "sort_order"),
    )


class CustomerDunningOverride(Base):
    """Kundenspezifische Mahneinstellungen.

    Ermöglicht Sonderbehandlung für bestimmte Kunden:
    - Eigene Zahlungsfristen
    - Max. Mahnstufe
    - Ausschluss von automatischer Mahnung
    """
    __tablename__ = "customer_dunning_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )

    # Zahlungsbedingungen
    custom_payment_terms_days = Column(Integer, nullable=True, comment="Abweichende Zahlungsfrist")

    # Mahnung
    max_mahn_stufe = Column(Integer, nullable=True, comment="Max. Eskalationsstufe (z.B. 2 = nie Inkasso)")
    preferred_contact_method = Column(String(50), default="email", comment="email, phone, letter")

    # Ausschluss
    exclude_from_auto_dunning = Column(Boolean, default=False, comment="Keine automatischen Mahnungen")
    exclusion_reason = Column(String(255), nullable=True)

    # Notizen
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    business_entity = relationship("BusinessEntity", backref="dunning_override")

    # Indexes
    __table_args__ = (
        Index("ix_customer_dunning_overrides_entity", "business_entity_id"),
    )


class CashFlowEntry(Base):
    """Cash-Flow-Prognosen."""
    __tablename__ = "cash_flow_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True)

    # Eintragstyp
    entry_type = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)

    # Referenzen
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    payment_order_id = Column(UUID(as_uuid=True), ForeignKey("payment_orders.id", ondelete="SET NULL"), nullable=True)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("bank_transactions.id", ondelete="SET NULL"), nullable=True)

    # Datum
    expected_date = Column(DateTime(timezone=True), nullable=False)
    actual_date = Column(DateTime(timezone=True), nullable=True)

    # Betrag
    expected_amount = Column(Numeric(15, 2), nullable=False)  # SECURITY: Numeric für Geldbetraege
    actual_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric für Geldbetraege
    currency = Column(String(3), default="EUR")

    # Wahrscheinlichkeit
    probability = Column(Float, default=1.0)

    # Beschreibung
    description = Column(String(255), nullable=True)
    category = Column(String(50), nullable=True)

    # Status
    status = Column(String(50), default="expected")

    # Gegenpartei
    counterparty_name = Column(String(255), nullable=True)
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="cash_flow_entries")
    document = relationship("Document", backref="cash_flow_entries")
    payment_order = relationship("PaymentOrder", backref="cash_flow_entries")
    transaction = relationship("BankTransaction", backref="cash_flow_entries")
    business_entity = relationship("BusinessEntity", backref="cash_flow_entries")
