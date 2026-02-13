# -*- coding: utf-8 -*-
"""
Document Versioning & Digital Signatures Models fuer Ablage-System (Vision 2026).

Dokumenten-Versionierung & Digitale Signaturen mit:
- DocumentVersion: Datei-Aenderungen mit Hash-Verifikation
- DocumentSignature: Elektronische und qualifizierte Signaturen
- SignatureRequest: Signatur-Workflow-Management

GoBD-konform: Unveraenderbarkeit durch Hash-Chain

Phase 1 der Vision 2026 Feature-Roadmap (Q1 2026).
"""

from datetime import datetime, date
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class VersionChangeType(str, Enum):
    """Typ der Dokumentenaenderung."""
    INITIAL = "initial"         # Erste Version
    EDIT = "edit"               # Manuelle Bearbeitung
    CORRECTION = "correction"   # Korrektur
    ANNOTATION = "annotation"   # Annotationen hinzugefuegt
    OCR_UPDATE = "ocr_update"   # OCR aktualisiert
    MERGE = "merge"             # Dokumente zusammengefuegt
    SPLIT = "split"             # Dokument aufgeteilt
    RESTORE = "restore"         # Von aelterer Version wiederhergestellt


class SignatureType(str, Enum):
    """Typ der digitalen Signatur."""
    ELECTRONIC = "electronic"   # Einfache elektronische Signatur (SES)
    ADVANCED = "advanced"       # Fortgeschrittene elektronische Signatur (AES)
    QUALIFIED = "qualified"     # Qualifizierte elektronische Signatur (QES)
    TIMESTAMP = "timestamp"     # Nur Zeitstempel (TSA)
    WITNESS = "witness"         # Zeugensignatur


class VerificationStatus(str, Enum):
    """Status der Signaturverifikation."""
    PENDING = "pending"     # Noch nicht verifiziert
    VALID = "valid"         # Gueltig
    INVALID = "invalid"     # Ungueltig
    EXPIRED = "expired"     # Abgelaufen
    REVOKED = "revoked"     # Widerrufen


class SignatureRequestStatus(str, Enum):
    """Status einer Signaturanfrage."""
    DRAFT = "draft"                     # Entwurf
    PENDING = "pending"                 # Wartend auf Start
    IN_PROGRESS = "in_progress"         # In Bearbeitung
    PARTIALLY_SIGNED = "partially_signed"  # Teilweise signiert
    COMPLETED = "completed"             # Abgeschlossen
    EXPIRED = "expired"                 # Abgelaufen
    CANCELLED = "cancelled"             # Abgebrochen


# ============================================================================
# Document Version Model
# ============================================================================


class DocumentVersion(Base):
    """Dokumentenversion - Trackt Datei-Aenderungen mit Hash-Verifikation.

    GoBD-Konformitaet:
    - Unveraenderbarkeit: SHA-256 Hash fuer jede Version
    - Nachvollziehbarkeit: Vollstaendige Versions-Kette
    - Hash-Chain: previous_version_id fuer Integritaetsnachweis

    Unterschied zu OCRResultVersion:
    - OCRResultVersion: Trackt OCR-Ergebnisse
    - DocumentVersion: Trackt die physische Datei
    """
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Document Reference
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Version Info
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # File Info
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)  # SHA-256
    hash_algorithm: Mapped[str] = mapped_column(String(20), nullable=False, default="SHA-256")
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Version Metadata
    change_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=VersionChangeType.EDIT.value
    )
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Previous Version (for chain verification)
    previous_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Created By
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    document = relationship("Document", backref="file_versions")
    company = relationship("Company")
    created_by = relationship("User")
    previous_version = relationship("DocumentVersion", remote_side=[id])
    signatures = relationship(
        "DocumentSignature",
        back_populates="version",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version"),
        Index("ix_doc_versions_document_id", "document_id"),
        Index("ix_doc_versions_company_id", "company_id"),
        Index("ix_doc_versions_is_current", "document_id", "is_current"),
        Index("ix_doc_versions_created_at", "created_at"),
        Index("ix_doc_versions_file_hash", "file_hash"),
    )

    def verify_hash(self, file_content: bytes) -> bool:
        """Verify file content against stored hash."""
        import hashlib

        if self.hash_algorithm == "SHA-256":
            computed_hash = hashlib.sha256(file_content).hexdigest()
        elif self.hash_algorithm == "SHA-384":
            computed_hash = hashlib.sha384(file_content).hexdigest()
        elif self.hash_algorithm == "SHA-512":
            computed_hash = hashlib.sha512(file_content).hexdigest()
        else:
            raise ValueError(f"Unsupported hash algorithm: {self.hash_algorithm}")

        return computed_hash.lower() == self.file_hash.lower()

    def __repr__(self) -> str:
        return f"<DocumentVersion doc={self.document_id} v{self.version_number}>"


# ============================================================================
# Document Signature Model
# ============================================================================


class DocumentSignature(Base):
    """Digitale Signatur eines Dokuments.

    Unterstuetzt:
    - Elektronische Signaturen (SES): Einfach, schnell
    - Fortgeschrittene Signaturen (AES): Mit Zertifikat
    - Qualifizierte Signaturen (QES): Rechtlich bindend (eIDAS)

    GoBD-Konformitaet:
    - Unveraenderbarkeit: Signatur bestaetigt Inhalt zum Zeitpunkt
    - Zeitstempel: TSA-Integration fuer rechtssichere Zeitnachweise
    """
    __tablename__ = "document_signatures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Document/Version Reference
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Signer Info
    signer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    signer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    signer_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Signature Type
    signature_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SignatureType.ELECTRONIC.value
    )

    # Signature Data (encrypted in app layer)
    signature_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Base64

    # Certificate Info (for qualified signatures)
    certificate_issuer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    certificate_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    certificate_valid_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    certificate_valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    certificate_info: Mapped[dict] = mapped_column(CrossDBJSON, default=dict)

    # Timestamp Authority
    tsa_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tsa_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Position on document
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position: Mapped[Optional[dict]] = mapped_column(CrossDBJSON, nullable=True)

    # Verification
    verification_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=VerificationStatus.PENDING.value
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_details: Mapped[dict] = mapped_column(CrossDBJSON, default=dict)

    # Validity
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    document = relationship("Document", backref="signatures")
    version = relationship("DocumentVersion", back_populates="signatures")
    company = relationship("Company")
    signer = relationship("User")

    __table_args__ = (
        Index("ix_doc_signatures_document_id", "document_id"),
        Index("ix_doc_signatures_version_id", "version_id"),
        Index("ix_doc_signatures_company_id", "company_id"),
        Index("ix_doc_signatures_signer_id", "signer_id"),
        Index("ix_doc_signatures_status", "verification_status"),
        Index("ix_doc_signatures_type", "signature_type"),
        Index("ix_doc_signatures_signed_at", "signed_at"),
    )

    @property
    def is_valid(self) -> bool:
        """Check if signature is currently valid."""
        if self.is_revoked:
            return False
        if self.verification_status != VerificationStatus.VALID.value:
            return False
        if self.valid_until and self.valid_until < datetime.now(self.valid_until.tzinfo):
            return False
        return True

    @property
    def is_qualified(self) -> bool:
        """Check if this is a qualified electronic signature."""
        return self.signature_type == SignatureType.QUALIFIED.value

    def __repr__(self) -> str:
        return f"<DocumentSignature {self.id} doc={self.document_id} signer={self.signer_name}>"


# ============================================================================
# Signature Request Model
# ============================================================================


class SignatureRequest(Base):
    """Signaturanfrage - Workflow fuer Mehrfach-Signaturen.

    Unterstuetzt:
    - Sequentielle Signaturen (Order)
    - Parallele Signaturen
    - Externe Unterzeichner (via Token)
    - Fristenmanagement mit Erinnerungen
    """
    __tablename__ = "signature_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Document Reference
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Requester
    requester_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Request Details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SignatureType.ELECTRONIC.value
    )

    # Signers (ordered list)
    signers: Mapped[List[dict]] = mapped_column(CrossDBJSON, default=list)
    # Format: [{"email": "...", "name": "...", "order": 1, "status": "pending", "signed_at": null}]

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SignatureRequestStatus.PENDING.value
    )
    current_signer_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_signers: Mapped[int] = mapped_column(Integer, nullable=False)

    # Deadline & Reminders
    deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_days: Mapped[List[int]] = mapped_column(CrossDBJSON, default=lambda: [7, 3, 1])
    last_reminder_sent: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Completion
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Access Token (for external signers)
    access_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    # Relationships defined in models_signature.py

    __table_args__ = (
        Index("ix_sig_requests_document_id", "document_id"),
        Index("ix_sig_requests_company_id", "company_id"),
        Index("ix_sig_requests_requester_id", "requester_id"),
        Index("ix_sig_requests_status", "status"),
        Index("ix_sig_requests_deadline", "deadline"),
        Index("ix_sig_requests_token", "access_token"),
        {"extend_existing": True},
    )

    @property
    def is_complete(self) -> bool:
        """Check if all signatures have been collected."""
        return self.status == SignatureRequestStatus.COMPLETED.value

    @property
    def is_expired(self) -> bool:
        """Check if request has expired."""
        if self.deadline and datetime.now(self.deadline.tzinfo) > self.deadline:
            return True
        return self.status == SignatureRequestStatus.EXPIRED.value

    @property
    def pending_signers(self) -> List[dict]:
        """Get list of signers who haven't signed yet."""
        return [s for s in self.signers if s.get("status") == "pending"]

    @property
    def signed_count(self) -> int:
        """Count of signers who have signed."""
        return len([s for s in self.signers if s.get("status") == "signed"])

    def __repr__(self) -> str:
        return f"<SignatureRequest {self.id} doc={self.document_id} status={self.status}>"
