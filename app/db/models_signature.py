# -*- coding: utf-8 -*-
"""
QES/eIDAS Signatur-Models für Ablage-System.

Qualifizierte Elektronische Signaturen (QES) nach eIDAS-Verordnung:
- SignatureRequest: Signaturanfrage für ein Dokument
- SignatureEntry: Einzelne Signatur eines Unterzeichners
- SignatureAuditLog: Audit-Trail für alle Signaturereignisse

Unterstützte Provider:
- D-Trust (qualifizierte Signaturen)
- sign-me (Fernsignaturen)
- Swisscom AIS (CH-Provider)
- Internal (einfache/fortgeschrittene Signaturen)

Phase 1 der Vision 2026 Feature-Roadmap.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON

# Import canonical SignatureRequest to avoid duplicate __tablename__
from app.db.models_versioning import SignatureRequest  # noqa: F401


# ============================================================================
# Enums
# ============================================================================


class SignatureLevel(str, Enum):
    """Signaturniveau nach eIDAS-Verordnung."""
    SIMPLE = "simple"            # Einfache elektronische Signatur
    ADVANCED = "advanced"        # Fortgeschrittene elektronische Signatur
    QUALIFIED = "qualified"      # Qualifizierte elektronische Signatur (QES)


class SignatureStatus(str, Enum):
    """Status einer Signatur oder Signaturanfrage."""
    PENDING = "pending"          # Ausstehend
    REQUESTED = "requested"      # Angefordert
    SIGNED = "signed"            # Signiert
    REJECTED = "rejected"        # Abgelehnt
    EXPIRED = "expired"          # Abgelaufen
    REVOKED = "revoked"          # Widerrufen


class SignatureProvider(str, Enum):
    """Signaturanbieter."""
    D_TRUST = "d_trust"          # D-Trust GmbH (Bundesdruckerei)
    SIGN_ME = "sign_me"          # sign-me (Fernsignatur)
    SWISSCOM_AIS = "swisscom_ais"  # Swisscom All-in Signing Service
    INTERNAL = "internal"        # Interne Signatur


# ============================================================================
# Models
# ============================================================================

# Add relationships to the imported SignatureRequest that reference
# the models defined below in this file.
if not hasattr(SignatureRequest, 'entries'):
    SignatureRequest.entries = relationship(
        "SignatureEntry",
        back_populates="signature_request",
        lazy="selectin",
        order_by="SignatureEntry.signing_order",
    )
if not hasattr(SignatureRequest, 'audit_logs'):
    SignatureRequest.audit_logs = relationship(
        "SignatureAuditLog",
        back_populates="signature_request",
        lazy="selectin",
        order_by="SignatureAuditLog.performed_at.desc()",
    )


class SignatureEntry(Base):
    """Einzelne Signatur eines Unterzeichners.

    Repraesentiert die Signatur oder den Signaturauftrag
    für einen individuellen Unterzeichner.
    """
    __tablename__ = "signature_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signature_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signature_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    signer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    signer_email = Column(String(255), nullable=False)
    signer_name = Column(String(255), nullable=False)
    signing_order = Column(Integer, default=1, nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default=SignatureStatus.PENDING.value,
    )
    signed_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    certificate_issuer = Column(String(255), nullable=True)
    certificate_serial = Column(String(255), nullable=True)
    signature_hash = Column(String(128), nullable=True)
    provider_reference = Column(String(255), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    signature_request = relationship(
        "SignatureRequest",
        back_populates="entries",
    )

    __table_args__ = (
        Index("ix_signature_entries_request_id", "signature_request_id"),
        Index("ix_signature_entries_signer_email", "signer_email"),
        Index("ix_signature_entries_company_id", "company_id"),
    )

    def __repr__(self) -> str:
        return f"<SignatureEntry(id={self.id}, signer='{self.signer_name}', status='{self.status}')>"


class SignatureAuditLog(Base):
    """Audit-Trail für alle Signaturereignisse.

    Unveränderliches Protokoll aller Aktionen im Zusammenhang
    mit Signaturanfragen (eIDAS-konform).
    """
    __tablename__ = "signature_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signature_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signature_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    action = Column(String(50), nullable=False)
    performed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    performed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    details_json = Column(CrossDBJSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    signature_request = relationship(
        "SignatureRequest",
        back_populates="audit_logs",
    )

    __table_args__ = (
        Index("ix_signature_audit_request_id", "signature_request_id"),
        Index("ix_signature_audit_company_id", "company_id"),
    )

    def __repr__(self) -> str:
        return f"<SignatureAuditLog(id={self.id}, action='{self.action}')>"
