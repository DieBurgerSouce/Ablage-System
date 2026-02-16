# -*- coding: utf-8 -*-
"""
Consent Management database models for Ablage-System.

Vision 2.0 Feature: Datenschutz-by-Design
Unterstützt:
- Einwilligungsverwaltung (DSGVO Art. 6, 7)
- Auftragsverarbeitung (DSGVO Art. 28)
- Automatisierte Entscheidungen (DSGVO Art. 22)
- Consent-Audit-Trail

Feinpoliert und durchdacht.
"""

import uuid
from datetime import datetime, date
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Date,
    Boolean,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class ConsentType(str, Enum):
    """Typen von Einwilligungen."""
    # DSGVO Grundlagen
    DATA_PROCESSING = "data_processing"           # Allgemeine Datenverarbeitung
    MARKETING = "marketing"                        # Marketing-Kommunikation
    ANALYTICS = "analytics"                        # Nutzungsanalyse
    PROFILING = "profiling"                       # Profilerstellung
    AUTOMATED_DECISIONS = "automated_decisions"   # Automatisierte Entscheidungen (Art. 22)

    # Geschäftsbezogen
    ORDER_PROCESSING = "order_processing"         # Auftragsverarbeitung (AVV Art. 28)
    THIRD_PARTY_SHARING = "third_party_sharing"  # Weitergabe an Dritte
    TAX_ADVISOR_ACCESS = "tax_advisor_access"    # Steuerberater-Zugang
    BANK_DATA_ACCESS = "bank_data_access"        # Bankdaten-Zugang
    CREDIT_CHECK = "credit_check"                 # Bonitaetsprüfung

    # Technisch
    COOKIE_ESSENTIAL = "cookie_essential"         # Notwendige Cookies
    COOKIE_FUNCTIONAL = "cookie_functional"       # Funktionale Cookies
    COOKIE_ANALYTICS = "cookie_analytics"         # Analyse-Cookies
    COOKIE_MARKETING = "cookie_marketing"         # Marketing-Cookies


class ConsentStatus(str, Enum):
    """Status einer Einwilligung."""
    PENDING = "pending"           # Angefragt, noch nicht entschieden
    GRANTED = "granted"           # Erteilt
    DENIED = "denied"             # Verweigert
    WITHDRAWN = "withdrawn"       # Widerrufen
    EXPIRED = "expired"           # Abgelaufen


class ConsentSource(str, Enum):
    """Quelle der Einwilligung."""
    WEB_FORM = "web_form"         # Online-Formular
    PAPER_FORM = "paper_form"     # Papier-Formular
    EMAIL = "email"               # E-Mail
    API = "api"                   # API-Aufruf
    CONTRACT = "contract"         # Vertrag/AVV
    VERBAL = "verbal"             # Muendlich (mit Dokumentation)
    INFERRED = "inferred"         # Abgeleitet (z.B. aus Vertrag)


class LegalBasis(str, Enum):
    """Rechtsgrundlage nach DSGVO Art. 6."""
    CONSENT = "consent"           # Art. 6(1)(a) - Einwilligung
    CONTRACT = "contract"         # Art. 6(1)(b) - Vertragserfuellung
    LEGAL_OBLIGATION = "legal_obligation"  # Art. 6(1)(c) - Rechtliche Verpflichtung
    VITAL_INTERESTS = "vital_interests"    # Art. 6(1)(d) - Lebenswichtige Interessen
    PUBLIC_INTEREST = "public_interest"    # Art. 6(1)(e) - Öffentliches Interesse
    LEGITIMATE_INTEREST = "legitimate_interest"  # Art. 6(1)(f) - Berechtigtes Interesse


class AuditAction(str, Enum):
    """Aktionen für Audit-Trail."""
    REQUESTED = "requested"       # Einwilligung angefragt
    GRANTED = "granted"           # Einwilligung erteilt
    DENIED = "denied"             # Einwilligung verweigert
    WITHDRAWN = "withdrawn"       # Einwilligung widerrufen
    RENEWED = "renewed"           # Einwilligung erneuert
    EXPIRED = "expired"           # Einwilligung abgelaufen
    MODIFIED = "modified"         # Einwilligung geändert
    ACCESSED = "accessed"         # Einwilligung geprüft
    EXPORTED = "exported"         # Einwilligung exportiert


class ConsentRecord(Base):
    """
    Einwilligungs-Datensatz.

    Speichert alle Einwilligungen mit vollständiger Historie.
    """
    __tablename__ = "consent_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Betroffene Person/Firma
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Einwilligungs-Details
    consent_type = Column(String(50), nullable=False, index=True)
    status = Column(
        String(20),
        nullable=False,
        default=ConsentStatus.PENDING.value,
        index=True,
    )
    legal_basis = Column(String(30), nullable=False, default=LegalBasis.CONSENT.value)

    # Wer hat eingewilligt
    grantor_name = Column(String(200), nullable=True)  # Name der Person
    grantor_role = Column(String(100), nullable=True)  # Rolle/Position
    grantor_email = Column(String(254), nullable=True)  # E-Mail für Kommunikation

    # Zeitstempel
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    granted_at = Column(DateTime(timezone=True), nullable=True)
    denied_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Quelle und Nachweis
    source = Column(String(30), nullable=False, default=ConsentSource.WEB_FORM.value)
    ip_address = Column(String(45), nullable=True)  # IPv4 oder IPv6
    user_agent = Column(String(500), nullable=True)

    # Dokumentation
    document_reference = Column(String(255), nullable=True)  # Verweis auf Dokument/Vertrag
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Scope der Einwilligung
    scope = Column(CrossDBJSON, default=dict)
    # Beispiel: {"data_categories": ["invoices", "payments"], "purposes": ["accounting", "tax"]}

    # Bedingungen und Einschränkungen
    conditions = Column(Text, nullable=True)  # Textuelle Bedingungen
    restrictions = Column(CrossDBJSON, default=list)  # Strukturierte Einschränkungen

    # Version (für Änderungsnachverfolgung)
    version = Column(Integer, default=1)
    previous_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consent_records.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Widerruf-Details
    withdrawal_reason = Column(Text, nullable=True)
    withdrawal_method = Column(String(50), nullable=True)

    # Notizen
    notes = Column(Text, nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    entity = relationship("BusinessEntity", backref="consent_records")
    user = relationship("User", foreign_keys=[user_id], backref="consent_records")
    document = relationship("Document", backref="consent_records")
    company = relationship("Company", backref="consent_records")
    previous_version = relationship("ConsentRecord", remote_side=[id])
    audit_logs = relationship("ConsentAuditLog", back_populates="consent_record", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_consent_records_entity_type", "entity_id", "consent_type"),
        Index("ix_consent_records_company_status", "company_id", "status"),
    )

    @property
    def is_valid(self) -> bool:
        """Prüfe ob Einwilligung aktuell gültig ist."""
        if self.status != ConsentStatus.GRANTED.value:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    @property
    def days_until_expiry(self) -> Optional[int]:
        """Tage bis Ablauf."""
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "consent_type": self.consent_type,
            "status": self.status,
            "legal_basis": self.legal_basis,
            "grantor_name": self.grantor_name,
            "grantor_role": self.grantor_role,
            "grantor_email": self.grantor_email,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "denied_at": self.denied_at.isoformat() if self.denied_at else None,
            "withdrawn_at": self.withdrawn_at.isoformat() if self.withdrawn_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source,
            "document_reference": self.document_reference,
            "document_id": str(self.document_id) if self.document_id else None,
            "scope": self.scope or {},
            "conditions": self.conditions,
            "restrictions": self.restrictions or [],
            "version": self.version,
            "is_valid": self.is_valid,
            "days_until_expiry": self.days_until_expiry,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DataProcessingAgreement(Base):
    """
    Auftragsverarbeitungsvertrag (AVV) nach DSGVO Art. 28.

    Dokumentiert Vereinbarungen mit Auftragsverarbeitern.
    """
    __tablename__ = "data_processing_agreements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Vertragsparteien
    controller_name = Column(String(255), nullable=False)  # Verantwortlicher
    processor_name = Column(String(255), nullable=False)   # Auftragsverarbeiter
    processor_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Vertragsnummer und Titel
    agreement_number = Column(String(50), nullable=True, unique=True)
    title = Column(String(255), nullable=False)

    # Zeitraum
    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date, nullable=True)
    auto_renewal = Column(Boolean, default=False)

    # Gegenstand der Verarbeitung
    subject_matter = Column(Text, nullable=True)  # Gegenstand der Verarbeitung
    processing_purposes = Column(CrossDBJSON, default=list)  # Zwecke
    data_categories = Column(CrossDBJSON, default=list)  # Datenkategorien
    data_subjects = Column(CrossDBJSON, default=list)  # Betroffenengruppen

    # Technische und organisatorische Massnahmen
    tom_reference = Column(String(255), nullable=True)  # Verweis auf TOM-Dokument
    tom_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Subunternehmer
    subprocessor_allowed = Column(Boolean, default=False)
    subprocessors = Column(CrossDBJSON, default=list)
    # Beispiel: [{"name": "AWS", "country": "DE", "purpose": "Hosting"}]

    # Internationale Übermittlung
    international_transfer = Column(Boolean, default=False)
    transfer_mechanisms = Column(CrossDBJSON, default=list)
    # Beispiel: ["EU-US DPF", "SCCs"]

    # Kontakt
    processor_dpo_name = Column(String(200), nullable=True)
    processor_dpo_email = Column(String(254), nullable=True)

    # Status
    status = Column(String(30), nullable=False, default="active")
    # Values: draft, pending_signature, active, terminated, expired

    # Dokumentation
    agreement_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Kündigungsdetails
    terminated_at = Column(DateTime(timezone=True), nullable=True)
    termination_reason = Column(Text, nullable=True)

    # Notizen
    notes = Column(Text, nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    processor_entity = relationship("BusinessEntity", backref="dpa_as_processor")
    tom_document = relationship("Document", foreign_keys=[tom_document_id])
    agreement_document = relationship("Document", foreign_keys=[agreement_document_id])
    company = relationship("Company", backref="data_processing_agreements")

    __table_args__ = (
        Index("ix_dpa_company_status", "company_id", "status"),
    )

    @property
    def is_active(self) -> bool:
        """Prüfe ob AVV aktiv ist."""
        if self.status != "active":
            return False
        if self.expiration_date and date.today() > self.expiration_date:
            return False
        return True

    @property
    def days_until_expiry(self) -> Optional[int]:
        """Tage bis Ablauf."""
        if not self.expiration_date:
            return None
        delta = self.expiration_date - date.today()
        return max(0, delta.days)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "controller_name": self.controller_name,
            "processor_name": self.processor_name,
            "processor_entity_id": str(self.processor_entity_id) if self.processor_entity_id else None,
            "agreement_number": self.agreement_number,
            "title": self.title,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "auto_renewal": self.auto_renewal,
            "subject_matter": self.subject_matter,
            "processing_purposes": self.processing_purposes or [],
            "data_categories": self.data_categories or [],
            "data_subjects": self.data_subjects or [],
            "subprocessor_allowed": self.subprocessor_allowed,
            "subprocessors": self.subprocessors or [],
            "international_transfer": self.international_transfer,
            "transfer_mechanisms": self.transfer_mechanisms or [],
            "processor_dpo_name": self.processor_dpo_name,
            "processor_dpo_email": self.processor_dpo_email,
            "status": self.status,
            "is_active": self.is_active,
            "days_until_expiry": self.days_until_expiry,
            "agreement_document_id": str(self.agreement_document_id) if self.agreement_document_id else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConsentAuditLog(Base):
    """
    Audit-Trail für Einwilligungen.

    Dokumentiert alle Aktionen an Einwilligungen für Compliance.
    """
    __tablename__ = "consent_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zur Einwilligung
    consent_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consent_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Aktion
    action = Column(String(30), nullable=False, index=True)

    # Wer hat die Aktion ausgeführt
    performed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    performed_by_name = Column(String(200), nullable=True)  # Fallback wenn User gelöscht
    performed_by_role = Column(String(100), nullable=True)

    # Zeitstempel
    performed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Details zur Aktion
    old_value = Column(CrossDBJSON, default=dict)  # Vorheriger Zustand
    new_value = Column(CrossDBJSON, default=dict)  # Neuer Zustand
    changes = Column(CrossDBJSON, default=dict)    # Was wurde geändert

    # Technische Details
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Notizen/Begruendung
    reason = Column(Text, nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    consent_record = relationship("ConsentRecord", back_populates="audit_logs")
    performed_by = relationship("User", foreign_keys=[performed_by_id])
    company = relationship("Company", backref="consent_audit_logs")

    __table_args__ = (
        Index("ix_consent_audit_company_time", "company_id", "performed_at"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "consent_record_id": str(self.consent_record_id),
            "action": self.action,
            "performed_by_id": str(self.performed_by_id) if self.performed_by_id else None,
            "performed_by_name": self.performed_by_name,
            "performed_by_role": self.performed_by_role,
            "performed_at": self.performed_at.isoformat() if self.performed_at else None,
            "old_value": self.old_value or {},
            "new_value": self.new_value or {},
            "changes": self.changes or {},
            "ip_address": self.ip_address,
            "reason": self.reason,
        }


class RetentionPolicy(Base):
    """
    Aufbewahrungsrichtlinie für Datenminimierung.

    Definiert Löschfristen nach Dokumenttyp und Kategorie.
    """
    __tablename__ = "retention_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Richtlinien-Details
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Was wird betroffen
    document_type = Column(String(50), nullable=True)  # Optional: spezifischer Dokumenttyp
    data_category = Column(String(50), nullable=True)  # Optional: Datenkategorie

    # Aufbewahrungsdauer
    retention_days = Column(Integer, nullable=False)
    # Beispiel: 3650 (10 Jahre für Buchhaltung)

    # Rechtsgrundlage
    legal_basis = Column(String(255), nullable=True)
    # Beispiel: "§257 HGB", "Art. 17 DSGVO"

    # Aktion nach Ablauf
    action_after_expiry = Column(String(30), default="archive")
    # Values: delete, archive, anonymize, review

    # Ausnahmen
    exceptions = Column(CrossDBJSON, default=list)
    # Beispiel: ["ongoing_legal_dispute", "tax_audit"]

    # Benachrichtigung vor Löschung
    notify_days_before = Column(Integer, default=30)
    notify_emails = Column(CrossDBJSON, default=list)

    # Status
    is_active = Column(Boolean, default=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="retention_policies")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_retention_policy_name"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "document_type": self.document_type,
            "data_category": self.data_category,
            "retention_days": self.retention_days,
            "retention_years": round(self.retention_days / 365, 1),
            "legal_basis": self.legal_basis,
            "action_after_expiry": self.action_after_expiry,
            "exceptions": self.exceptions or [],
            "notify_days_before": self.notify_days_before,
            "notify_emails": self.notify_emails or [],
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
