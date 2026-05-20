# -*- coding: utf-8 -*-
"""
Database models for PSD2/FinTS Banking Integration.

Phase 6: Multi-Bank Aggregation with PSD2 OAuth2 and FinTS PIN/TAN support.

SECURITY NOTES:
- All credentials are encrypted with AES-256-GCM
- Never log IBANs, account numbers, or balances
- PSD2 consent tokens have limited TTL
- TAN challenges expire after 5 minutes

Supported Banks:
- Sparkasse (FinTS 3.0)
- Volksbank (FinTS 3.0)
- Deutsche Bank (PSD2)
- Commerzbank (PSD2)
- DKB (FinTS)
- ING (PSD2)
- N26 (PSD2)
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Float, Numeric, Text,
    ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# Enums
# =============================================================================

class ConnectionType(str, Enum):
    """Bank connection type."""
    PSD2 = "psd2"       # PSD2 OpenBanking API
    FINTS = "fints"     # FinTS/HBCI
    MANUAL = "manual"   # Manual CSV/MT940 import only


class ConnectionStatus(str, Enum):
    """Connection status."""
    PENDING = "pending"           # Awaiting setup
    AWAITING_CONSENT = "awaiting_consent"  # PSD2: Waiting for user consent
    AWAITING_TAN = "awaiting_tan"          # FinTS: Waiting for TAN
    ACTIVE = "active"             # Connected and working
    EXPIRED = "expired"           # Credentials/consent expired
    ERROR = "error"               # Connection error
    SUSPENDED = "suspended"       # Temporarily suspended
    REVOKED = "revoked"           # User revoked access


class SyncStatus(str, Enum):
    """Sync operation status."""
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"


class PaymentInitiationStatus(str, Enum):
    """Payment initiation status for PSD2 PISP."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    AWAITING_SCA = "awaiting_sca"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ReconciliationMatchType(str, Enum):
    """How the transaction was matched."""
    AUTO_EXACT = "auto_exact"           # IBAN + amount exact match
    AUTO_REFERENCE = "auto_reference"   # Reference number match
    AUTO_SKONTO = "auto_skonto"         # Skonto deduction match
    AUTO_PARTIAL = "auto_partial"       # Partial payment match
    AUTO_FUZZY = "auto_fuzzy"           # Fuzzy matching
    MANUAL = "manual"                   # Manual assignment
    SPLIT = "split"                     # Multi-invoice split


# =============================================================================
# Bank Connection Model
# =============================================================================

class BankConnection(Base):
    """
    Multi-bank connection supporting PSD2 and FinTS.

    SECURITY:
    - Credentials are AES-256-GCM encrypted
    - PSD2 consent tokens stored encrypted
    - FinTS PIN/TAN never stored, only session-based
    """
    __tablename__ = "bank_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Bank Identification
    bank_code = Column(String(8), nullable=False, comment="BLZ (Bankleitzahl)")
    bank_name = Column(String(255), nullable=False)
    bic = Column(String(11), nullable=True)
    country_code = Column(String(2), default="DE")

    # Connection Type
    connection_type = Column(
        String(20),
        default=ConnectionType.FINTS.value,
        nullable=False
    )
    status = Column(
        String(30),
        default=ConnectionStatus.PENDING.value,
        nullable=False,
        index=True
    )

    # FinTS Configuration (encrypted)
    fints_url = Column(String(500), nullable=True)
    fints_version = Column(String(10), default="3.0")
    encrypted_credentials = Column(
        Text,
        nullable=True,
        comment="AES-256-GCM encrypted: {login_id, pin (session only)}"
    )
    selected_tan_method = Column(String(50), nullable=True)
    tan_media_name = Column(String(100), nullable=True)

    # PSD2 Configuration
    aspsp_id = Column(String(100), nullable=True, comment="ASPSP Identifier")
    consent_id = Column(String(100), nullable=True, comment="PSD2 Consent ID")
    consent_expires_at = Column(DateTime(timezone=True), nullable=True)
    consent_status = Column(String(50), nullable=True)

    # PSD2 OAuth2 Tokens (encrypted)
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Sync Configuration
    auto_sync_enabled = Column(Boolean, default=True)
    sync_interval_hours = Column(Integer, default=4)
    sync_from_date = Column(DateTime(timezone=True), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    next_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String(20), default=SyncStatus.IDLE.value)

    # Health Monitoring
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    is_healthy = Column(Boolean, default=True)

    # Feature Flags
    supports_balance = Column(Boolean, default=True)
    supports_transactions = Column(Boolean, default=True)
    supports_payment_initiation = Column(Boolean, default=False)
    supports_direct_debit = Column(Boolean, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", backref="bank_connections")
    created_by = relationship("User", foreign_keys=[created_by_id])
    accounts = relationship("ConnectedBankAccount", back_populates="connection", cascade="all, delete-orphan")
    sync_logs = relationship("BankSyncLog", back_populates="connection", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_bank_connections_company_status", "company_id", "status"),
        Index("ix_bank_connections_next_sync", "next_sync_at"),
        Index("ix_bank_connections_consent_expires", "consent_expires_at"),
    )


class ConnectedBankAccount(Base):
    """
    Individual bank account within a connection.

    A single bank connection can have multiple accounts (Girokonto, Sparkonto, etc.).
    """
    __tablename__ = "connected_bank_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_connections.id", ondelete="CASCADE"),
        nullable=False
    )

    # Account Identification (SECURITY: Sensitive data)
    iban = Column(String(34), nullable=False)
    bic = Column(String(11), nullable=True)
    account_number = Column(String(20), nullable=True, comment="Domestic account number")

    # Account Details
    account_name = Column(String(255), nullable=True)
    account_type = Column(String(50), default="checking")  # checking, savings, credit, loan
    currency = Column(String(3), default="EUR")
    product_name = Column(String(255), nullable=True, comment="Bank product name")

    # Balance (updated on each sync)
    current_balance = Column(Numeric(15, 2), nullable=True)
    available_balance = Column(Numeric(15, 2), nullable=True)
    credit_limit = Column(Numeric(15, 2), nullable=True)
    balance_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Configuration
    is_primary = Column(Boolean, default=False)
    auto_import = Column(Boolean, default=True)
    auto_reconcile = Column(Boolean, default=True)

    # Link to existing BankAccount (for reconciliation)
    legacy_bank_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="SET NULL"),
        nullable=True,
        comment="Link to existing BankAccount for migration"
    )

    # Statistics
    transaction_count = Column(Integer, default=0)
    last_transaction_date = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("BankConnection", back_populates="accounts")
    legacy_bank_account = relationship("BankAccount", foreign_keys=[legacy_bank_account_id])
    imported_transactions = relationship("ImportedTransaction", back_populates="account", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_connected_accounts_connection", "connection_id"),
        Index("ix_connected_accounts_iban", "iban"),
        UniqueConstraint("connection_id", "iban", name="uq_connection_iban"),
    )


class ImportedTransaction(Base):
    """
    Transactions imported via PSD2/FinTS.

    Separate from BankTransaction to allow parallel operation during migration.
    Will eventually replace BankTransaction.
    """
    __tablename__ = "imported_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("connected_bank_accounts.id", ondelete="CASCADE"),
        nullable=False
    )

    # Transaction Identification
    transaction_id = Column(String(100), nullable=True, comment="Bank's transaction ID")
    entry_reference = Column(String(100), nullable=True, comment="Entry reference")
    end_to_end_id = Column(String(35), nullable=True)

    # Dates
    booking_date = Column(DateTime(timezone=True), nullable=False)
    value_date = Column(DateTime(timezone=True), nullable=False)

    # Amount
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")

    # Counterparty (SECURITY: PII - never log)
    counterparty_name = Column(String(255), nullable=True)
    counterparty_iban = Column(String(34), nullable=True)
    counterparty_bic = Column(String(11), nullable=True)

    # Reference
    reference_text = Column(Text, nullable=True)
    mandate_reference = Column(String(35), nullable=True)
    creditor_id = Column(String(35), nullable=True)

    # Categorization
    transaction_type = Column(String(50), nullable=True)
    booking_text = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)

    # Reconciliation
    reconciliation_status = Column(String(30), default="pending")
    reconciliation_match_type = Column(String(30), nullable=True)
    reconciliation_confidence = Column(Float, nullable=True)
    matched_invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="SET NULL"),
        nullable=True
    )
    matched_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    matched_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True
    )
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    reconciled_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Partial Payment Support
    is_partial_payment = Column(Boolean, default=False)
    allocated_amount = Column(Numeric(15, 2), nullable=True)
    remaining_amount = Column(Numeric(15, 2), nullable=True)

    # Raw Data
    raw_data = Column(CrossDBJSON, nullable=True)

    # Audit
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    sync_log_id = Column(UUID(as_uuid=True), ForeignKey("bank_sync_logs.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    account = relationship("ConnectedBankAccount", back_populates="imported_transactions")
    matched_invoice = relationship("InvoiceTracking", foreign_keys=[matched_invoice_id])
    matched_document = relationship("Document", foreign_keys=[matched_document_id])
    matched_entity = relationship("BusinessEntity", foreign_keys=[matched_entity_id])
    reconciled_by = relationship("User", foreign_keys=[reconciled_by_id])
    split_allocations = relationship("TransactionSplitAllocation", back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_imported_tx_account_date", "account_id", "booking_date"),
        Index("ix_imported_tx_reconciliation", "reconciliation_status"),
        Index("ix_imported_tx_transaction_id", "transaction_id"),
        Index("ix_imported_tx_counterparty_iban", "counterparty_iban"),
        # Prevent duplicate imports
        UniqueConstraint("account_id", "transaction_id", "booking_date", "amount", name="uq_imported_tx_dedup"),
    )


class TransactionSplitAllocation(Base):
    """
    Allocation of a single transaction to multiple invoices (split payments).

    Example: Customer pays 3 invoices with one transfer.
    """
    __tablename__ = "transaction_split_allocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("imported_transactions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Target
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="CASCADE"),
        nullable=False
    )

    # Allocation
    allocated_amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    allocation_reason = Column(String(255), nullable=True)

    # Confidence
    match_confidence = Column(Float, nullable=True)
    match_method = Column(String(50), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    transaction = relationship("ImportedTransaction", back_populates="split_allocations")
    invoice = relationship("InvoiceTracking", foreign_keys=[invoice_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_split_allocation_transaction", "transaction_id"),
        Index("ix_split_allocation_invoice", "invoice_id"),
    )


class BankSyncLog(Base):
    """
    Sync operation log for audit and debugging.
    """
    __tablename__ = "bank_sync_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_connections.id", ondelete="CASCADE"),
        nullable=False
    )

    # Sync Details
    sync_type = Column(String(30), nullable=False)  # balance, transactions, full
    status = Column(String(20), nullable=False)  # started, success, failed

    # Results
    accounts_synced = Column(Integer, default=0)
    transactions_imported = Column(Integer, default=0)
    transactions_duplicates = Column(Integer, default=0)
    auto_reconciled_count = Column(Integer, default=0)

    # Period
    sync_from_date = Column(DateTime(timezone=True), nullable=True)
    sync_to_date = Column(DateTime(timezone=True), nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Error Tracking
    error_message = Column(Text, nullable=True)
    error_details = Column(CrossDBJSON, nullable=True)

    # Trigger
    triggered_by = Column(String(30), nullable=True)  # scheduled, manual, webhook
    triggered_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    connection = relationship("BankConnection", back_populates="sync_logs")
    triggered_by_user = relationship("User", foreign_keys=[triggered_by_user_id])

    __table_args__ = (
        Index("ix_sync_logs_connection_started", "connection_id", "started_at"),
        Index("ix_sync_logs_status", "status"),
    )


class PaymentInitiation(Base):
    """
    PSD2 Payment Initiation Service (PISP) requests.

    Supports SEPA Credit Transfer and SEPA Direct Debit.
    """
    __tablename__ = "payment_initiations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_connections.id", ondelete="SET NULL"),
        nullable=True
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("connected_bank_accounts.id", ondelete="SET NULL"),
        nullable=True
    )

    # Payment Type
    payment_type = Column(String(30), nullable=False)  # sepa_credit, sepa_direct_debit

    # Debtor (from)
    debtor_iban = Column(String(34), nullable=False)
    debtor_name = Column(String(140), nullable=True)

    # Creditor (to) - SECURITY: PII
    creditor_name = Column(String(140), nullable=False)
    creditor_iban = Column(String(34), nullable=False)
    creditor_bic = Column(String(11), nullable=True)

    # Amount
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")

    # Reference
    reference = Column(String(140), nullable=True)
    end_to_end_id = Column(String(35), nullable=True)

    # Execution
    requested_execution_date = Column(DateTime(timezone=True), nullable=True)

    # Linked Documents
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoice_tracking.id", ondelete="SET NULL"), nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Status
    status = Column(String(30), default=PaymentInitiationStatus.DRAFT.value)

    # PSD2 Response
    psd2_payment_id = Column(String(100), nullable=True)
    psd2_status = Column(String(50), nullable=True)
    sca_redirect_url = Column(Text, nullable=True)
    sca_status = Column(String(30), nullable=True)

    # TAN (FinTS)
    tan_required = Column(Boolean, default=False)
    tan_challenge = Column(Text, nullable=True)
    tan_method = Column(String(50), nullable=True)

    # Approval Workflow
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Execution Result
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    bank_reference = Column(String(100), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", backref="payment_initiations")
    connection = relationship("BankConnection")
    account = relationship("ConnectedBankAccount")
    invoice = relationship("InvoiceTracking", foreign_keys=[invoice_id])
    document = relationship("Document", foreign_keys=[document_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_payment_init_company_status", "company_id", "status"),
        Index("ix_payment_init_execution_date", "requested_execution_date"),
    )


class ReconciliationRule(Base):
    """
    Configurable rules for automatic transaction reconciliation.

    Rules are evaluated in priority order.
    """
    __tablename__ = "reconciliation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Rule Definition
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Integer, default=100, comment="Lower = higher priority")
    is_active = Column(Boolean, default=True)

    # Matching Conditions (JSON)
    conditions = Column(
        CrossDBJSON,
        nullable=False,
        comment="Matching conditions: [{field, operator, value}]"
    )

    # Action
    action = Column(String(30), nullable=False)  # auto_match, suggest, ignore
    auto_approve_threshold = Column(Float, default=0.95, comment="Min confidence for auto-match")

    # Target Entity (optional)
    default_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)

    # Statistics
    times_matched = Column(Integer, default=0)
    last_matched_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", backref="reconciliation_rules")
    default_entity = relationship("BusinessEntity", foreign_keys=[default_entity_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_recon_rules_company_priority", "company_id", "priority"),
        Index("ix_recon_rules_active", "is_active"),
    )


class SupportedBank(Base):
    """
    Catalog of supported banks with connection details.

    Pre-populated with German banks.
    """
    __tablename__ = "supported_banks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Bank Identification
    bank_code = Column(String(8), nullable=False, unique=True, comment="BLZ")
    bank_name = Column(String(255), nullable=False)
    bic = Column(String(11), nullable=True)
    country_code = Column(String(2), default="DE")

    # Connection Capabilities
    supports_psd2 = Column(Boolean, default=False)
    supports_fints = Column(Boolean, default=False)

    # PSD2 Configuration
    psd2_base_url = Column(String(500), nullable=True)
    psd2_sandbox_url = Column(String(500), nullable=True)
    aspsp_id = Column(String(100), nullable=True)

    # FinTS Configuration
    fints_url = Column(String(500), nullable=True)
    fints_version = Column(String(10), default="3.0")

    # Features
    supports_balance = Column(Boolean, default=True)
    supports_transactions = Column(Boolean, default=True)
    supports_payment_initiation = Column(Boolean, default=False)
    supports_batch_payment = Column(Boolean, default=False)
    supports_direct_debit = Column(Boolean, default=False)

    # TAN Methods (FinTS)
    available_tan_methods = Column(CrossDBJSON, default=list)

    # Logo/Branding
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(7), nullable=True, comment="Hex color")

    # Status
    is_active = Column(Boolean, default=True)
    maintenance_message = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_supported_banks_active", "is_active"),
        Index("ix_supported_banks_country", "country_code"),
    )
