# -*- coding: utf-8 -*-
"""
Fraud Detection database models for Ablage-System.

Models for:
- IBAN baseline tracking (manipulation detection)
- Fraud scan results with ML indicators
- IBAN change verification workflow

Feinpoliert und durchdacht - Enterprise Fraud Detection.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    Float,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class FraudScanType(str, Enum):
    """Types of fraud scans."""
    CEO_FRAUD = "ceo_fraud"
    DUPLICATE_PAYMENT = "duplicate_payment"
    IBAN_MANIPULATION = "iban_manipulation"
    INTERNAL_IRREGULARITY = "internal_irregularity"
    GENERAL = "general"


class FraudRiskLevel(str, Enum):
    """Risk levels for fraud detection."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudScanStatus(str, Enum):
    """Status of fraud scan results."""
    PENDING = "pending"
    REVIEWED = "reviewed"
    FALSE_POSITIVE = "false_positive"
    CONFIRMED = "confirmed"
    INVESTIGATING = "investigating"


class IBANChangeStatus(str, Enum):
    """Status of IBAN change requests."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class IBANBaseline(Base):
    """
    IBAN baseline tracking for manipulation detection.

    Maintains a history of IBANs per entity to detect
    unauthorized changes to bank details.
    """
    __tablename__ = "iban_baselines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Entity reference
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Bank details
    iban = Column(String(34), nullable=False)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(255), nullable=True)

    # Tracking timestamps
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Verification status
    is_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    verification_method = Column(String(50), nullable=True)  # manual, bank_statement, api
    verified_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    entity = relationship("BusinessEntity", backref="iban_baselines")
    company = relationship("Company", backref="iban_baselines")
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index("ix_iban_baselines_entity_iban", "entity_id", "iban", unique=True),
        Index("ix_iban_baselines_company_entity", "company_id", "entity_id"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "iban_masked": f"{self.iban[:4]}...{self.iban[-4:]}" if self.iban else None,
            "bic": self.bic,
            "bank_name": self.bank_name,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "is_verified": self.is_verified,
            "is_active": self.is_active,
            "verification_method": self.verification_method,
        }


class FraudScanResult(Base):
    """
    Fraud scan results with risk scores and indicators.

    Stores detailed analysis results from fraud detection scans
    including ML model outputs and explainability data.
    """
    __tablename__ = "fraud_scan_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-tenant and references
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Scan metadata
    scan_type = Column(String(50), nullable=False, index=True)
    scan_source = Column(String(50), nullable=False)  # automated, manual, ocr_trigger

    # Risk assessment
    risk_score = Column(Float, nullable=False)  # 0.0 - 1.0
    risk_level = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False)  # 0.0 - 1.0

    # Detailed indicators
    indicators = Column(CrossDBJSON, default=dict, nullable=False)
    explanation = Column(CrossDBJSON, default=dict, nullable=False)

    # ML model info
    model_version = Column(String(50), nullable=True)
    features_used = Column(CrossDBJSON, default=list, nullable=True)

    # Review status
    status = Column(String(30), default=FraudScanStatus.PENDING.value, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_notes = Column(Text, nullable=True)

    # Alert linkage
    alert_id = Column(
        UUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="fraud_scan_results")
    document = relationship("Document", backref="fraud_scan_results")
    entity = relationship("BusinessEntity", backref="fraud_scan_results")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    alert = relationship("Alert", backref="fraud_scan_results")

    __table_args__ = (
        Index("ix_fraud_scan_results_company_type", "company_id", "scan_type"),
        Index("ix_fraud_scan_results_company_risk", "company_id", "risk_level"),
        Index("ix_fraud_scan_results_company_status", "company_id", "status"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 1", name="ck_fraud_scan_results_risk_score"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fraud_scan_results_confidence"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "scan_type": self.scan_type,
            "scan_source": self.scan_source,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "indicators": self.indicators,
            "explanation": self.explanation,
            "status": self.status,
            "document_id": str(self.document_id) if self.document_id else None,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class IBANChangeRequest(Base):
    """
    IBAN change verification workflow.

    Tracks IBAN change requests and their verification status
    to prevent unauthorized bank detail modifications.
    """
    __tablename__ = "iban_change_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # IBAN change details
    old_iban = Column(String(34), nullable=True)
    new_iban = Column(String(34), nullable=False)
    new_bic = Column(String(11), nullable=True)
    new_bank_name = Column(String(255), nullable=True)

    # Request metadata
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    detection_method = Column(String(50), nullable=False)  # ocr, manual_entry, import
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Risk assessment
    risk_score = Column(Float, nullable=True)
    risk_indicators = Column(CrossDBJSON, default=dict, nullable=True)

    # Verification workflow
    status = Column(String(30), default=IBANChangeStatus.PENDING.value, nullable=False)
    verification_required = Column(Boolean, default=True, nullable=False)
    verification_deadline = Column(DateTime(timezone=True), nullable=True)
    verification_method = Column(String(50), nullable=True)  # callback, document, bank_statement
    verified_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="iban_change_requests")
    entity = relationship("BusinessEntity", backref="iban_change_requests")
    source_document = relationship("Document", backref="iban_change_requests")
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index("ix_iban_change_requests_company_status", "company_id", "status"),
        Index("ix_iban_change_requests_entity", "entity_id"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "old_iban_masked": f"{self.old_iban[:4]}...{self.old_iban[-4:]}" if self.old_iban else None,
            "new_iban_masked": f"{self.new_iban[:4]}...{self.new_iban[-4:]}" if self.new_iban else None,
            "status": self.status,
            "verification_required": self.verification_required,
            "verification_deadline": self.verification_deadline.isoformat() if self.verification_deadline else None,
            "risk_score": self.risk_score,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }
