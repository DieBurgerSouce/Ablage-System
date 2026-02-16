# -*- coding: utf-8 -*-
"""
Document Integrity (Hash-Chain) database models for Ablage-System.

Dokument-Integrität und Manipulationsschutz:
- SHA-256 Hashes pro Dokument
- Tägliche Merkle-Baeume für kryptographische Verifizierung
- Integritätsberichte für Compliance und Audits

Feinpoliert und durchdacht - Enterprise-grade Document Integrity.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Date,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class VerificationStatus(str, Enum):
    """Status der Dokumenten-Verifizierung."""

    UNVERIFIED = "unverified"    # Hash berechnet, aber nicht geprüft
    VERIFIED = "verified"        # Hash stimmt überein
    TAMPERED = "tampered"        # Hash weicht ab - Manipulation erkannt


class DocumentHash(Base):
    """
    SHA-256 Hash eines Dokuments.

    Speichert den kryptographischen Hash zur Integritätsprüfung.
    Ein Dokument hat genau einen aktiven Hash-Eintrag.
    """
    __tablename__ = "document_hashes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz (1:1)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Hash-Daten
    file_hash = Column(String(64), nullable=False)  # SHA-256 hex digest
    hash_algorithm = Column(String(20), nullable=False, default="sha-256")
    file_size_bytes = Column(BigInteger, nullable=False)

    # Zeitstempel der Hash-Berechnung
    computed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Verifizierung
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_status = Column(
        String(20),
        nullable=False,
        default=VerificationStatus.UNVERIFIED.value,
    )

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    document = relationship("Document", backref="integrity_hash")
    company = relationship("Company", backref="document_hashes")

    __table_args__ = (
        Index("ix_document_hashes_document_id", "document_id"),
        Index("ix_document_hashes_file_hash", "file_hash"),
        Index("ix_document_hashes_company_id", "company_id"),
    )

    def to_dict(self) -> dict:
        """Konvertiert in ein Dictionary für API-Responses."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "company_id": str(self.company_id),
            "file_hash": self.file_hash,
            "hash_algorithm": self.hash_algorithm,
            "file_size_bytes": self.file_size_bytes,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verification_status": self.verification_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MerkleTreeNode(Base):
    """
    Knoten eines täglichen Merkle-Baums.

    Merkle-Baeume ermöglichen effiziente kryptographische Verifizierung
    aller Dokumente eines Tages. Blatt-Knoten (level=0) referenzieren
    DocumentHash-Einträge, innere Knoten bilden die Baumstruktur.
    """
    __tablename__ = "merkle_tree_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Baum-Identifikation
    tree_date = Column(Date, nullable=False)  # Tag des Merkle-Baums

    # Knoten-Daten
    node_hash = Column(String(64), nullable=False)
    parent_hash = Column(String(64), nullable=True)  # null für Root
    level = Column(Integer, nullable=False)  # 0 = Blatt
    position = Column(Integer, nullable=False)  # Position in der Ebene

    # Blatt-Referenz (nur für level=0)
    document_hash_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_hashes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Root-Hash (nur auf Root-Knoten gesetzt)
    merkle_root = Column(String(64), nullable=True)

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    # Relationships defined in models.py main model

    __table_args__ = (
        Index("ix_merkle_tree_nodes_tree_date", "tree_date"),
        Index("ix_merkle_tree_nodes_company_date", "company_id", "tree_date"),
        Index("ix_merkle_tree_nodes_document_hash_id", "document_hash_id"),
        {"extend_existing": True},
    )

    def to_dict(self) -> dict:
        """Konvertiert in ein Dictionary."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "tree_date": self.tree_date.isoformat() if self.tree_date else None,
            "node_hash": self.node_hash,
            "parent_hash": self.parent_hash,
            "level": self.level,
            "position": self.position,
            "document_hash_id": str(self.document_hash_id) if self.document_hash_id else None,
            "merkle_root": self.merkle_root,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IntegrityReport(Base):
    """
    Integritätsbericht für Compliance und Audits.

    Fasst den Verifizierungsstatus aller Dokumente eines Unternehmens
    zusammen und speichert den Merkle-Root als Nachweis.
    """
    __tablename__ = "integrity_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Berichtsdaten
    report_date = Column(Date, nullable=False)
    total_documents = Column(Integer, nullable=False, default=0)
    verified_count = Column(Integer, nullable=False, default=0)
    tampered_count = Column(Integer, nullable=False, default=0)
    unverified_count = Column(Integer, nullable=False, default=0)

    # Merkle-Root des Berichts
    merkle_root = Column(String(64), nullable=False)

    # Detaillierte Ergebnisse
    report_data = Column(CrossDBJSON, default=dict)

    # Ersteller
    generated_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="integrity_reports")
    generator = relationship("User", backref="integrity_reports")

    __table_args__ = (
        Index("ix_integrity_reports_company_date", "company_id", "report_date"),
    )

    def to_dict(self) -> dict:
        """Konvertiert in ein Dictionary für API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "report_date": self.report_date.isoformat() if self.report_date else None,
            "total_documents": self.total_documents,
            "verified_count": self.verified_count,
            "tampered_count": self.tampered_count,
            "unverified_count": self.unverified_count,
            "merkle_root": self.merkle_root,
            "report_data": self.report_data or {},
            "generated_by": str(self.generated_by) if self.generated_by else None,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
