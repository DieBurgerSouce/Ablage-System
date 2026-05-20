"""DropShipment/Tax domain models - extracted from models.py (Modularisierung Phase 1.1).

Enthält:
- TransactionType, DropShipmentCompanyRole, MovingDelivery,
  ConfidenceLevel, VatCategoryType, ZmSubmissionStatus (Enums)
- DropShipmentClassification, DropShipmentPosition, VatIdRegistry,
  TransactionParty, ProofDocument, ClassificationAuditLog,
  DatevStreckengeschaeftAccount, ClassificationIndicator, ZmSubmission (SQLAlchemy Models)
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin

# =============================================================================
# STRECKENGESCHÄFT / DREIECKSGESCHÄFT MODELS
# =============================================================================


class TransactionType(str, Enum):
    """Classification type for drop shipment transactions."""
    STANDARD = "standard"              # Normal warehouse transaction
    DROP_SHIPMENT = "drop_shipment"    # Streckengeschäft (2 parties)
    TRIANGULAR_EU = "triangular_eu"    # EU Dreiecksgeschäft §25b UStG
    CHAIN_TRANSACTION = "chain_transaction"  # Reihengeschäft (3+ parties)
    UNKNOWN = "unknown"                # Needs manual classification


class DropShipmentCompanyRole(str, Enum):
    """Role of German company in the transaction."""
    FIRST_SUPPLIER = "first_supplier"    # Erster Lieferer
    INTERMEDIATE = "intermediate"         # Zwischenhändler (mittlerer Abnehmer)
    FINAL_BUYER = "final_buyer"          # Letzter Abnehmer
    NOT_APPLICABLE = "not_applicable"    # Standard transaction


class MovingDelivery(str, Enum):
    """Which delivery is the moving delivery (§3 Abs. 6a UStG)."""
    TO_INTERMEDIATE = "to_intermediate"      # Lieferung AN den Zwischenhändler
    FROM_INTERMEDIATE = "from_intermediate"  # Lieferung VOM Zwischenhändler
    UNDETERMINED = "undetermined"            # Noch nicht bestimmt


class ConfidenceLevel(str, Enum):
    """Classification confidence level."""
    DEFINITIVE = "definitive"       # 100% - ERP marker, legal reference
    HIGH = "high"                   # 90-99% - Strong indicators
    MEDIUM = "medium"               # 70-89% - Multiple weak indicators
    LOW = "low"                     # 50-69% - Single weak indicator
    MANUAL_REQUIRED = "manual_required"  # <50% - Conflicting signals


class VatCategoryType(str, Enum):
    """VAT treatment category for drop shipment."""
    STANDARD_DE = "standard_de"           # Normal German VAT (19% or 7%)
    INTRA_COMMUNITY = "intra_community"   # Innergemeinschaftliche Lieferung
    REVERSE_CHARGE = "reverse_charge"     # Steuerschuldnerschaft Empfänger
    EXPORT = "export"                     # Ausfuhr Drittland (steuerfrei)
    TRIANGULAR_MIDDLE = "triangular_middle"  # §25b Zwischenhändler
    TRIANGULAR_FINAL = "triangular_final"    # §25b Endabnehmer


class DropShipmentClassification(SoftDeleteMixin, Base):
    """
    Drop shipment classification at document level.
    Implements detection of Streckengeschäft, Dreiecksgeschäft (§25b UStG),
    and Reihengeschäfte (§3 Abs. 6a UStG).
    """
    __tablename__ = "drop_shipment_classifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    # Classification results
    transaction_type = Column(String(30), nullable=False, default=TransactionType.UNKNOWN.value)
    company_role = Column(String(30), nullable=False, default=DropShipmentCompanyRole.NOT_APPLICABLE.value)
    moving_delivery = Column(String(30), default=MovingDelivery.UNDETERMINED.value)
    vat_category = Column(String(30), nullable=False, default=VatCategoryType.STANDARD_DE.value)

    # Confidence and validation
    confidence_level = Column(String(20), nullable=False, default=ConfidenceLevel.MANUAL_REQUIRED.value)
    confidence_score = Column(Integer, nullable=False, default=0)
    is_validated = Column(Boolean, default=False)
    validated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Indicators that triggered classification (JSONB)
    indicators = Column(CrossDBJSON, nullable=False, default=list)
    conflicts = Column(CrossDBJSON, nullable=True)

    # EU parties involved (for triangular transactions)
    party_count = Column(Integer, default=2)
    eu_countries_involved = Column(CrossDBJSON, nullable=True)  # ["DE", "AT", "NL"]

    # DATEV integration
    datev_account_debit = Column(String(10), nullable=True)
    datev_account_credit = Column(String(10), nullable=True)
    datev_tax_code = Column(String(5), nullable=True)
    zm_relevant = Column(Boolean, default=False)
    zm_marker = Column(String(1), nullable=True)  # '1' for triangular

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Soft-Delete (GDPR/GoBD compliance)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="false")
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    document = relationship("Document", backref="drop_shipment_classification")
    deleter = relationship("User", foreign_keys=[deleted_by])
    validator = relationship("User", foreign_keys=[validated_by])
    positions = relationship("DropShipmentPosition", back_populates="classification",
                            cascade="all, delete-orphan")
    parties = relationship("TransactionParty", back_populates="classification",
                          cascade="all, delete-orphan")
    proof_documents = relationship("ProofDocument", back_populates="classification",
                                   cascade="all, delete-orphan")
    audit_logs = relationship("ClassificationAuditLog", back_populates="classification",
                             cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_classification_type", "transaction_type"),
        Index("ix_classification_confidence", "confidence_level", "is_validated"),
        Index("ix_classification_zm", "zm_relevant", "created_at"),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 100",
                       name="valid_confidence_score"),
        CheckConstraint("party_count >= 2 AND party_count <= 10",
                       name="valid_party_count"),
    )

    def __repr__(self) -> str:
        return f"<DropShipmentClassification {self.transaction_type} {self.confidence_level}>"


class DropShipmentPosition(Base):
    """
    Position-level classification for mixed invoices (Mischbestellungen).
    A single invoice can contain both warehouse and drop-shipment positions.
    """
    __tablename__ = "drop_shipment_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
                        nullable=False)

    # Position identification
    position_number = Column(Integer, nullable=False)
    article_number = Column(String(100), nullable=True)
    article_description = Column(Text, nullable=True)
    quantity = Column(Numeric(12, 3), nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True)
    line_total = Column(Numeric(12, 2), nullable=True)

    # Position-level classification
    is_drop_shipment = Column(Boolean, nullable=False, default=False)
    warehouse_code = Column(String(20), nullable=True)
    erp_position_type = Column(String(10), nullable=True)  # TAS, TAN, etc.

    # VAT treatment for this position
    vat_category = Column(String(30), nullable=True)
    vat_rate = Column(Numeric(5, 2), nullable=True)

    # DATEV account for this position
    datev_revenue_account = Column(String(10), nullable=True)
    datev_expense_account = Column(String(10), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="positions")
    document = relationship("Document")

    __table_args__ = (
        Index("ix_positions_drop_ship", "is_drop_shipment"),
        # Unique constraint: one entry per position per document
        # Note: handled in migration
    )

    def __repr__(self) -> str:
        return f"<DropShipmentPosition {self.position_number} drop={self.is_drop_shipment}>"


class VatIdRegistry(Base):
    """
    VAT ID registry for party identification and VIES validation.
    Caches EU VIES validation results.
    """
    __tablename__ = "vat_id_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vat_id = Column(String(20), nullable=False, unique=True)
    country_code = Column(String(2), nullable=False, index=True)
    company_name = Column(String(255), nullable=True)

    # Validation status (VIES check)
    is_valid = Column(Boolean, nullable=True)
    last_validated = Column(DateTime(timezone=True), nullable=True)
    validation_response = Column(CrossDBJSON, nullable=True)

    # Internal reference (links to BusinessEntity, which unifies customers and suppliers)
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    business_entity = relationship("BusinessEntity")

    def __repr__(self) -> str:
        return f"<VatIdRegistry {self.vat_id} valid={self.is_valid}>"


class TransactionParty(Base):
    """
    Party information extracted from documents for drop shipment classification.
    Tracks all parties in the transaction chain.
    """
    __tablename__ = "transaction_parties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)

    # Party role in the chain
    party_role = Column(String(30), nullable=False)  # seller, buyer, ship_to, bill_to, carrier
    sequence_number = Column(Integer, nullable=False)  # Position in chain: 1=first, 2=middle, 3=last

    # Party identification
    company_name = Column(String(255), nullable=True)
    vat_id = Column(String(20), nullable=True)
    country_code = Column(String(2), nullable=True)

    # Address
    street = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)

    # Source of extraction
    source_field = Column(String(50), nullable=True)  # invoice_address, delivery_address, cmr_consignee

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="parties")

    def __repr__(self) -> str:
        return f"<TransactionParty {self.party_role} {self.company_name}>"


class ProofDocument(Base):
    """
    Document evidence chain for proof archive.
    Tracks required proofs for tax-free treatment (Gelangensnachweis, CMR, etc.)
    """
    __tablename__ = "proof_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"),
                        nullable=True)

    # Proof type: invoice, delivery_note, cmr, gelangensbestätigung, speditionsauftrag, vat_id_proof
    proof_type = Column(String(50), nullable=False)

    is_present = Column(Boolean, default=False)
    is_complete = Column(Boolean, default=False)
    missing_fields = Column(CrossDBJSON, nullable=True)  # Array of missing field names

    # For CMR: Field 24 extraction
    cmr_field_24_signed = Column(Boolean, nullable=True)
    cmr_field_24_date = Column(Date, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="proof_documents")
    document = relationship("Document")

    def __repr__(self) -> str:
        return f"<ProofDocument {self.proof_type} present={self.is_present}>"


class ClassificationAuditLog(Base):
    """
    Immutable audit log for classification changes.
    Required for GoBD compliance and tax audit trail.
    """
    __tablename__ = "classification_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)

    # Action: created, auto_classified, manually_validated, overridden, exported_datev, zm_reported
    action = Column(String(50), nullable=False)

    previous_value = Column(CrossDBJSON, nullable=True)
    new_value = Column(CrossDBJSON, nullable=True)
    reason = Column(Text, nullable=True)

    performed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())

    # System info for audit
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="audit_logs")
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<ClassificationAuditLog {self.action} at {self.performed_at}>"


class DatevStreckengeschaeftAccount(Base):
    """
    DATEV account mapping configuration for drop shipment transactions.
    Maps company role and transaction type to SKR03/SKR04 accounts.
    """
    __tablename__ = "datev_streckengeschäft_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    kontenrahmen = Column(String(5), nullable=False)  # SKR03, SKR04
    company_role = Column(String(30), nullable=False)
    transaction_type = Column(String(30), nullable=False)

    # Account numbers
    revenue_account = Column(String(10), nullable=True)
    expense_account = Column(String(10), nullable=True)
    tax_code = Column(String(5), nullable=True)

    # UStVA mapping
    ustva_kennzahl = Column(String(5), nullable=True)
    zm_kennzeichen = Column(String(1), nullable=True)

    description_de = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        # Unique constraint for mapping lookup
        Index("ix_datev_account_lookup", "kontenrahmen", "company_role", "transaction_type"),
    )

    def __repr__(self) -> str:
        return f"<DatevStreckengeschäftAccount {self.kontenrahmen} {self.transaction_type}>"


class ClassificationIndicator(Base):
    """
    Classification indicator configuration.
    Defines detection patterns and weights for automatic classification.
    """
    __tablename__ = "classification_indicators"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    indicator_code = Column(String(50), nullable=False, unique=True)
    indicator_name_de = Column(String(100), nullable=False)
    indicator_name_en = Column(String(100), nullable=True)

    weight = Column(Integer, nullable=False, default=50)
    is_definitive = Column(Boolean, default=False)
    applies_to_incoming = Column(Boolean, default=True)
    applies_to_outgoing = Column(Boolean, default=True)

    detection_pattern = Column(Text, nullable=True)  # Regex pattern
    detection_field = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 100", name="valid_indicator_weight"),
    )

    def __repr__(self) -> str:
        return f"<ClassificationIndicator {self.indicator_code} weight={self.weight}>"


class ZmSubmissionStatus(str, Enum):
    """Status der ZM-Meldung."""
    DRAFT = "draft"               # Entwurf (noch nicht eingereicht)
    SUBMITTED = "submitted"       # Bei BZSt eingereicht
    CONFIRMED = "confirmed"       # Eingang bestätigt
    CORRECTED = "corrected"       # Korrigierte Meldung eingereicht
    CANCELLED = "cancelled"       # Storniert


class ZmSubmission(Base):
    """
    Zusammenfassende Meldung (ZM) Einreichungsstatus.
    Trackt den Status der monatlichen ZM-Meldung pro Periode.

    Die ZM muss bis zum 25. des Folgemonats beim BZSt eingereicht werden.
    """
    __tablename__ = "zm_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Periode (z.B. "2024-12" für Dezember 2024)
    period = Column(String(7), nullable=False, index=True)

    # User/Company
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"),
                       nullable=True)

    # Status und Submission Details
    status = Column(String(20), nullable=False, default=ZmSubmissionStatus.DRAFT.value)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # BZSt-Referenz (nach Einreichung)
    bzst_reference = Column(String(100), nullable=True)
    bzst_response_code = Column(String(20), nullable=True)
    bzst_response_message = Column(Text, nullable=True)

    # Inhalt der Meldung (Snapshot zum Zeitpunkt der Einreichung)
    total_amount = Column(Numeric(15, 2), nullable=True)
    record_count = Column(Integer, nullable=True)
    triangular_count = Column(Integer, nullable=True)
    countries_involved = Column(CrossDBJSON, nullable=True)  # ["AT", "NL", ...]

    # Deadline (25. des Folgemonats)
    deadline = Column(Date, nullable=False)
    is_late = Column(Boolean, default=False)

    # Korrektur-Referenz (falls dies eine Korrekturmeldung ist)
    original_submission_id = Column(UUID(as_uuid=True),
                                   ForeignKey("zm_submissions.id", ondelete="SET NULL"),
                                   nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    submitter = relationship("User", foreign_keys=[submitted_by])
    company = relationship("Company")
    original_submission = relationship("ZmSubmission", remote_side=[id])

    __table_args__ = (
        # Unique constraint: Eine Meldung pro Periode pro User
        Index("ix_zm_submission_period_user", "period", "user_id", unique=True),
        Index("ix_zm_submission_status", "status"),
        Index("ix_zm_submission_deadline", "deadline"),
    )

    def __repr__(self) -> str:
        return f"<ZmSubmission {self.period} status={self.status}>"
