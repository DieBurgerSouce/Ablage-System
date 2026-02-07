"""
SQLAlchemy Models fuer ESG-Reporting (Phase 7.4).

Environmental, Social, Governance Nachhaltigkeitsberichterstattung.
"""

from datetime import datetime, date
from typing import Optional
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, Date, Boolean, Float, Text,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class ESGScope(str, Enum):
    """CO2-Emissions-Scopes nach GHG Protocol."""
    SCOPE_1 = "scope_1"  # Direkte Emissionen
    SCOPE_2 = "scope_2"  # Indirekte Emissionen (Energie)
    SCOPE_3 = "scope_3"  # Weitere indirekte Emissionen


class ESGCategory(str, Enum):
    """ESG-Kategorien."""
    ENVIRONMENTAL = "environmental"
    SOCIAL = "social"
    GOVERNANCE = "governance"


class CertificationStatus(str, Enum):
    """Status einer Zertifizierung."""
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING = "pending"
    REVOKED = "revoked"


class ReportStatus(str, Enum):
    """Status eines ESG-Reports."""
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ESGCarbonFootprint(Base):
    """
    CO2-Fussabdruck-Eintraege.

    Erfasst Emissionen nach GHG Protocol Scopes.
    """
    __tablename__ = "esg_carbon_footprint"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zeitraum
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Scope nach GHG Protocol
    scope = Column(String(20), nullable=False)

    # Emissionsquelle
    source_category = Column(String(100), nullable=False)  # z.B. "Fuhrpark", "Heizung", "Strom"
    source_description = Column(String(255))

    # Verbrauchsdaten
    consumption_value = Column(Float, nullable=False)
    consumption_unit = Column(String(50), nullable=False)  # kWh, Liter, km, etc.

    # Berechnete Emissionen
    co2_equivalent_kg = Column(Float, nullable=False)  # CO2e in kg
    emission_factor = Column(Float)  # Verwendeter Emissionsfaktor
    emission_factor_source = Column(String(255))  # Quelle des Faktors

    # Optionale Verknuepfung mit Dokument (z.B. Rechnung)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        index=True
    )

    # Methodik
    calculation_method = Column(String(100))  # z.B. "GHG Protocol", "ISO 14064"
    data_quality = Column(String(20))  # high, medium, low, estimated

    # Audit-Trail
    recorded_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verified = Column(Boolean, default=False)
    verified_at = Column(DateTime(timezone=True))
    verified_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Metadaten
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    document = relationship("Document")
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index("ix_esg_carbon_footprint_period", "company_id", "period_start", "period_end"),
        Index("ix_esg_carbon_footprint_scope", "company_id", "scope"),
    )


class ESGSupplierRating(Base):
    """
    Nachhaltigkeitsbewertung von Lieferanten.

    Ermoeglicht Tracking und Vergleich der Lieferketten-Nachhaltigkeit.
    """
    __tablename__ = "esg_supplier_ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Verknuepfung mit Lieferant (Entity)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Bewertungszeitraum
    rating_date = Column(Date, nullable=False)
    valid_until = Column(Date)

    # Gesamt-Score (0-100)
    overall_score = Column(Float, nullable=False)

    # Einzel-Scores (0-100)
    environmental_score = Column(Float)
    social_score = Column(Float)
    governance_score = Column(Float)

    # Detaillierte Bewertungen (JSONB)
    environmental_details = Column(CrossDBJSON, default=dict)  # CO2, Ressourcen, Abfall
    social_details = Column(CrossDBJSON, default=dict)  # Arbeitsbedingungen, Menschenrechte
    governance_details = Column(CrossDBJSON, default=dict)  # Compliance, Transparenz

    # Risiko-Einschaetzung
    risk_level = Column(String(20))  # low, medium, high, critical
    risk_factors = Column(CrossDBJSON, default=list)  # Liste von Risikofaktoren

    # Zertifizierungen des Lieferanten
    certifications = Column(CrossDBJSON, default=list)  # ISO 14001, SA8000, etc.

    # Verbesserungsmassnahmen
    improvement_areas = Column(CrossDBJSON, default=list)
    action_plan = Column(Text)

    # Audit-Trail
    assessed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assessment_method = Column(String(100))  # self-assessment, audit, third-party

    # Metadaten
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    entity = relationship("BusinessEntity")
    assessed_by = relationship("User", foreign_keys=[assessed_by_id])

    __table_args__ = (
        Index("ix_esg_supplier_ratings_entity", "entity_id", "rating_date"),
        Index("ix_esg_supplier_ratings_score", "company_id", "overall_score"),
    )


class ESGCertification(Base):
    """
    Nachhaltigkeits-Zertifizierungen des Unternehmens.

    Tracking von ISO 14001, ISO 50001, EMAS, etc.
    """
    __tablename__ = "esg_certifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zertifizierungsdetails
    certification_type = Column(String(100), nullable=False)  # z.B. "ISO 14001", "EMAS"
    certification_name = Column(String(255), nullable=False)
    certification_body = Column(String(255))  # Zertifizierungsstelle
    certificate_number = Column(String(100))

    # Kategorie
    category = Column(String(20), nullable=False)  # environmental, social, governance

    # Gueltigkeit
    issue_date = Column(Date, nullable=False)
    expiry_date = Column(Date)
    status = Column(String(20), default=CertificationStatus.ACTIVE, nullable=False)

    # Scope
    scope_description = Column(Text)
    applicable_sites = Column(CrossDBJSON, default=list)  # Liste von Standorten

    # Verknuepfung mit Zertifikat-Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL")
    )

    # Audit-Historie
    last_audit_date = Column(Date)
    next_audit_date = Column(Date)
    audit_findings = Column(CrossDBJSON, default=list)

    # Erinnerungen
    reminder_days_before = Column(Integer, default=90)  # Erinnerung X Tage vor Ablauf
    reminder_sent_at = Column(DateTime(timezone=True))

    # Metadaten
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    document = relationship("Document")

    __table_args__ = (
        Index("ix_esg_certifications_type", "company_id", "certification_type"),
        Index("ix_esg_certifications_expiry", "company_id", "expiry_date"),
        Index("ix_esg_certifications_status", "company_id", "status"),
    )


class ESGReport(Base):
    """
    Nachhaltigkeitsberichte.

    Generierte Berichte fuer interne/externe Zwecke.
    """
    __tablename__ = "esg_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Berichtsdetails
    title = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False)  # annual, quarterly, csrd, dnk, custom
    reporting_standard = Column(String(100))  # GRI, CSRD, DNK, etc.

    # Berichtszeitraum
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    fiscal_year = Column(Integer)

    # Status
    status = Column(String(20), default=ReportStatus.DRAFT, nullable=False)

    # Inhalte (generiert)
    summary = Column(Text)
    content_json = Column(CrossDBJSON, default=dict)  # Strukturierte Inhalte

    # Kennzahlen-Zusammenfassung
    metrics_summary = Column(CrossDBJSON, default=dict)
    # z.B.: {
    #   "total_co2_emissions_kg": 12345.67,
    #   "scope_1_emissions_kg": 5000,
    #   "scope_2_emissions_kg": 7000,
    #   "scope_3_emissions_kg": 345.67,
    #   "supplier_avg_score": 72.5,
    #   "active_certifications": 3
    # }

    # Generiertes Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    pdf_path = Column(String(500))  # Pfad zum generierten PDF

    # Workflow
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True))

    # Metadaten
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    document = relationship("Document")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])

    __table_args__ = (
        Index("ix_esg_reports_period", "company_id", "period_start", "period_end"),
        Index("ix_esg_reports_status", "company_id", "status"),
        Index("ix_esg_reports_type", "company_id", "report_type"),
    )


class ESGGoal(Base):
    """
    Nachhaltigkeitsziele des Unternehmens.

    Tracking von Zielen und Fortschritt.
    """
    __tablename__ = "esg_goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zieldetails
    title = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(20), nullable=False)  # environmental, social, governance

    # Metriken
    metric_name = Column(String(100), nullable=False)  # z.B. "CO2-Reduktion"
    metric_unit = Column(String(50))  # z.B. "kg", "%"
    baseline_value = Column(Float)  # Ausgangswert
    baseline_year = Column(Integer)
    target_value = Column(Float, nullable=False)  # Zielwert
    target_year = Column(Integer, nullable=False)
    current_value = Column(Float)  # Aktueller Wert
    current_value_date = Column(Date)

    # Fortschritt
    progress_percentage = Column(Float)  # 0-100%
    on_track = Column(Boolean)

    # SDG-Verknuepfung (UN Sustainable Development Goals)
    sdg_goals = Column(CrossDBJSON, default=list)  # z.B. [7, 12, 13]

    # Status
    is_active = Column(Boolean, default=True)

    # Metadaten
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        Index("ix_esg_goals_category", "company_id", "category"),
        Index("ix_esg_goals_active", "company_id", "is_active"),
    )
